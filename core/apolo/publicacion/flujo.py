"""Los dos pasos del CLI de publicación (plan publicacion-tienda, D3): `guion` y `generar`.

Hablan con la API viva por HTTP (un `httpx.Client` con `base_url`; en los tests, el
`TestClient` de FastAPI) y trabajan sobre su PROPIA copia del documento, la que baja de
`GET /api/project/file` (D1): ni locks ni estado compartidos con la API.

  - `guion`: abre el proyecto, regenera su copia, recorre los pasos visuales y escribe
    `guion.json` y el borrador de `ficha.yaml` en la carpeta de la versión.
  - `generar`: valida ficha y guion (la firma del log tiene que ser la misma que cuando se
    armó el guion), pasa la puerta de entrega (D13), trae los entregables, sanea el `.apolo`,
    escribe `vista-3d.glb` (plan vista-3d-tienda), renderiza el video, escribe
    `vista-3d.html` (con la miniatura del video de póster), arma el paquete y
    comprueba al final que el proyecto no cambió mientras tanto. Los entregables los arma la
    API mientras aquí se hacen la vista 3D y el video (`paralelo`, D6 de video-tienda-pulido).

Los dos leen al empezar las capacidades que publica `GET /api/health` (hoy, `dwg`: ODA File
Converter) y avisan de lo que el paquete no va a traer (D5), en vez de fallar al final.

Abrir el proyecto lo cambia en la UI de Apolo: el CLI lo avisa al empezar.
"""

from __future__ import annotations

import contextlib
import copy
import io
import json
import shutil
import time
import zipfile
from pathlib import Path
from types import SimpleNamespace

from apolo.publicacion import ficha as fichas
from apolo.publicacion import paquete
from apolo.publicacion.entregables import NIVELES, EnFondo, Recolector, lista, omitidos
from apolo.publicacion.paquete import FICHA_YAML, GUION, PublicacionError

DURACION_S = 75.0
VERSION_INICIAL = "1.0.0"


class _Api:
    """Las pocas rutas de la API que usa la publicación, con errores en español."""

    def __init__(self, cliente):
        self.cliente = cliente
        self.sin_gravedad: str | None = None  # por qué la puerta corrió sin simular gravedad

    def _pedir(self, metodo: str, ruta: str, que: str, **kw):
        try:
            resp = self.cliente.request(metodo, ruta, **kw)
        except Exception as exc:  # noqa: BLE001 — conexión rechazada, timeout…
            raise PublicacionError(f"No pude {que}: la API no responde ({exc}). ¿Está Apolo "
                                   "corriendo en esa URL?") from exc
        if resp.status_code >= 400:
            try:
                detalle = resp.json().get("detail", resp.text)
            except Exception:  # noqa: BLE001 — no es JSON
                detalle = resp.text
            raise PublicacionError(f"No pude {que} ({resp.status_code}): {detalle}")
        return resp

    def abrir(self, proyecto: int) -> str:
        datos = self._pedir("POST", f"/api/projects/{proyecto}/open",
                            f"abrir el proyecto {proyecto}").json()
        return (datos.get("document") or {}).get("name") or f"proyecto-{proyecto}"

    def salud(self) -> dict:
        return self._pedir("GET", "/api/health", "leer la salud del documento").json()

    def apolo(self) -> bytes:
        return self._pedir("GET", "/api/project/file", "bajar el .apolo").content

    def puerta(self, con_gravedad: bool) -> dict:
        if con_gravedad:
            try:
                return self._pedir("POST", "/api/delivery-check",
                                   "pasar la puerta de entrega", json={"con_gravedad": True}).json()
            except PublicacionError as exc:  # sin MuJoCo, p. ej.: la puerta corre sin gravedad
                self.sin_gravedad = str(exc)  # y la declara en `no_aplica` (el LEEME lo dice)
        return self._pedir("POST", "/api/delivery-check", "pasar la puerta de entrega",
                           json={"con_gravedad": False}).json()


def _firma_de(data: bytes) -> str:
    """La firma del log de un `.apolo` sin regenerarlo (= `guion_video.firma`)."""
    from apolo.services.guion_video import firma

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return firma(SimpleNamespace(commands=json.loads(zf.read("commands.json"))))


def _documento(data: bytes):
    """La copia privada del documento (carga tolerante, como la API al abrir)."""
    from apolo.doc.document import Document

    return Document.from_apolo_bytes(data, tolerant=True)


def _eco_nulo(*_a, **_k):
    return None


def _de_la_tienda(proyecto: int, nombre: str) -> list:
    return [e for e in lista(proyecto, nombre) if set(NIVELES) & e.destinos]


def _avisos_de_capacidad(fuera: dict[str, str], entregables: list, cierre: str) -> list[str]:
    """Un aviso por entregable que la API no puede dar (D5 de video-tienda-pulido): dicho al
    EMPEZAR, con el porqué y el enlace de descarga, no tras minutos de trabajo."""
    por = {e.archivo: e for e in entregables}
    return [f"Aviso: el paquete saldrá SIN «{por[a].etiqueta}». {motivo.rstrip('.')}. {cierre}"
            for a, motivo in fuera.items()]


def guion(cliente, proyecto: int, *, raiz=None, slug: str | None = None,
          version: str | None = None, duracion_s: float = DURACION_S, titulo: str | None = None,
          eco=print, modo: str = "montaje") -> dict:
    """`publicar guion`: escribe `guion.json` y el borrador de `ficha.yaml`. Devuelve
    {carpeta, guion, ficha, etapas, duracion_s, capitulos}. `modo`: «montaje» (cómo se arma,
    D8 de video-tienda-pulido) o «diseño» (el orden del log)."""
    from apolo import paths
    from apolo.services.datos_rotulos import datos_rotulos
    from apolo.services.guion_video import MODOS, capitulos, duracion_total, validar_guion
    from apolo.services.guion_video import guion as armar_guion
    from apolo.services.montaje_video import etapas_del_modo

    if modo not in MODOS:
        raise PublicacionError(f"Modo de video desconocido: {modo!r} (válidos: {', '.join(MODOS)})")
    eco = eco or _eco_nulo
    api = _Api(cliente)
    t0 = time.perf_counter()
    nombre = api.abrir(proyecto)
    todos = _de_la_tienda(proyecto, nombre)
    avisos = _avisos_de_capacidad(omitidos(api.salud(), todos), todos,
                                  "Si lo haces antes de `publicar generar`, sale.")
    for aviso in avisos:
        eco(aviso)
    slug = slug or fichas.slug(nombre)
    raiz = Path(raiz or paths.publicaciones_dir())
    version = version or _version_libre(raiz, slug)
    carpeta = paquete.carpeta_version(raiz, slug, version)
    paquete.exigir_no_publicada(carpeta)
    if (carpeta / GUION).exists():
        raise PublicacionError(
            f"Ya hay un guion en {carpeta / GUION} (quizá ya editado a mano): no lo piso. "
            "Bórralo si quieres uno nuevo, o usa otra --version.")
    data = api.apolo()
    doc = _documento(data)
    if doc.regen_suppressed:
        eco(f"Aviso: {len(doc.regen_suppressed)} comando(s) no regeneran; la puerta de "
            "entrega lo marcará en rojo.")
    g = armar_guion(doc, etapas_del_modo(doc, duracion_s, modo, datos=datos_rotulos(doc)),
                    titulo=titulo, modo=modo)
    validar_guion(g, doc)
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / GUION).write_text(json.dumps(g, indent=2, ensure_ascii=False) + "\n",
                                 encoding="utf-8")
    if not (carpeta / FICHA_YAML).exists():
        (carpeta / FICHA_YAML).write_text(fichas.borrador(g["titulo"], slug, version),
                                          encoding="utf-8")
    veredicto = api.puerta(con_gravedad=False).get("veredicto")
    caps = capitulos(g)
    eco(f"Proyecto {proyecto} «{nombre}»: {len(doc.commands)} comandos, "
        f"{sum(len(e['pasos']) for e in g['etapas'])} pasos de {modo} en {len(g['etapas'])} "
        f"etapa(s); video de {duracion_total(g):.0f} s.")
    eco(f"Puerta de entrega hoy (sin gravedad): {veredicto}"
        + ("" if veredicto == paquete.VERDE else " — `generar` se negará sin --forzar"))
    eco(f"Escrito en {carpeta}:\n  {GUION}\n  {FICHA_YAML}")
    eco("Revisa antes de `publicar generar`:\n"
        "  - guion.json: el título y el texto (rótulo) de cada etapa, las cifras y el cierre;\n"
        "    las duraciones van en segundos. No cambies «documento»: ata el guion a este log.\n"
        "  - ficha.yaml: la descripción (obligatoria), etiquetas, nivel y precio, url_tienda\n"
        "    y, si vas a usar --musica, los datos de la pista.")
    eco("Capítulos para YouTube: " + (" · ".join(f"{s // 60:02d}:{s % 60:02d} {t}"
                                                for s, t in caps) or "ninguno (no cumplen D15)"))
    return {"carpeta": carpeta, "guion": carpeta / GUION, "ficha": carpeta / FICHA_YAML,
            "etapas": len(g["etapas"]), "duracion_s": duracion_total(g), "capitulos": caps,
            "avisos": avisos, "segundos": time.perf_counter() - t0}


def _version_libre(raiz: Path, slug: str) -> str:
    existentes = paquete.versiones(raiz, slug)
    if VERSION_INICIAL not in existentes:
        return VERSION_INICIAL
    ultima = existentes[-1]
    raise PublicacionError(f"«{slug}» ya tiene las versiones {', '.join(existentes)}: elige "
                           f"una nueva con --version (p. ej. {paquete.siguiente(ultima)}).")


def _version_pendiente(raiz: Path, slug: str) -> str:
    pendientes = [v for v in paquete.versiones(raiz, slug)
                  if (paquete.carpeta_version(raiz, slug, v) / GUION).exists()
                  and not paquete.publicada(paquete.carpeta_version(raiz, slug, v))]
    if len(pendientes) == 1:
        return pendientes[0]
    if not pendientes:
        raise PublicacionError(f"No hay ningún guion pendiente de «{slug}» en {raiz}: corre "
                               "`publicar guion` primero (o pasa --slug si usaste otro).")
    raise PublicacionError(f"«{slug}» tiene varias versiones sin publicar "
                           f"({', '.join(pendientes)}): elige una con --version.")


def generar(cliente, proyecto: int, *, raiz=None, slug: str | None = None,
            version: str | None = None, musica=None, forzar: bool = False,
            con_gravedad: bool = True, eco=print, paralelo: bool = False) -> dict:
    """`publicar generar`: valida, pasa la puerta, trae entregables, renderiza el video y
    arma el paquete. Devuelve el resumen (carpeta, tiempos, video, faltantes, saneo).

    `paralelo` (D6 de video-tienda-pulido): la API arma los entregables mientras aquí se
    renderiza el video. Sólo con la API en OTRO proceso (el CLI contra una URL): con la API en
    este mismo (el `TestClient` de los tests), su VTK y su OCCT correrían a la vez que los del
    video, que no toma locks (es dueño de su documento)."""
    from apolo import paths
    from apolo.media.codificar import buscar_ffmpeg, buscar_ffprobe
    from apolo.services.guion_video import GuionError, validar_guion

    eco = eco or _eco_nulo
    tiempos: dict[str, float] = {}
    t = time.perf_counter()
    api = _Api(cliente)
    nombre = api.abrir(proyecto)
    slug = slug or fichas.slug(nombre)
    raiz = Path(raiz or paths.publicaciones_dir())
    version = version or _version_pendiente(raiz, slug)
    carpeta = paquete.carpeta_version(raiz, slug, version)
    paquete.exigir_no_publicada(carpeta)
    if not (carpeta / GUION).exists():
        raise PublicacionError(f"No hay {GUION} en {carpeta}: corre `publicar guion` primero.")
    try:
        g = json.loads((carpeta / GUION).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PublicacionError(f"{GUION} no es JSON válido (¿una coma de más al editarlo?): "
                               f"{exc}") from None
    f = fichas.leer(carpeta / FICHA_YAML)
    pista = Path(musica) if musica else (
        Path(f["musica"]["archivo"]) if isinstance(f.get("musica"), dict)
        and f["musica"].get("archivo") else None)
    fichas.validar(f, con_musica=pista is not None)
    if (f["slug"], f["version"]) != (slug, version):
        raise PublicacionError(f"ficha.yaml dice {f['slug']} {f['version']} y la carpeta es "
                               f"{slug}/{version}: el slug y la versión los fija `publicar guion`.")
    if pista is not None and not pista.is_file():
        raise PublicacionError(f"No encuentro la música {pista}")
    salud = api.salud()
    todos = _de_la_tienda(proyecto, nombre)
    fuera = omitidos(salud, todos)
    for aviso in _avisos_de_capacidad(fuera, todos, "El resto sale igual y el LEEME dice qué "
                                      "falta."):
        eco(aviso)
    data = api.apolo()
    doc = _documento(data)
    try:
        validar_guion(g, doc)
    except GuionError as exc:
        raise PublicacionError(f"{exc}\n(el log del proyecto cambió desde `publicar guion`, o "
                               "el guion se editó mal)") from None
    tiempos["abrir y validar"] = time.perf_counter() - t

    t = time.perf_counter()
    calidad = paquete.calidad(api.puerta(con_gravedad), forzar=forzar)
    tiempos["puerta de entrega"] = time.perf_counter() - t
    if api.sin_gravedad:
        eco(f"Aviso: la gravedad no se simuló ({api.sin_gravedad}); el LEEME lo dice.")
    buscar_ffmpeg()
    buscar_ffprobe()  # antes de trabajar: sin con qué codificar ni medir, nada se toca

    staging = carpeta / paquete.TEMPORAL
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        resumen = _armar(cliente, todos, fuera, paralelo, doc, data, g, f, calidad, pista,
                         staging, tiempos, eco)
        if _firma_de(api.apolo()) != _firma_de(data) or \
                api.salud().get("project_id") != salud.get("project_id"):
            raise PublicacionError("El proyecto cambió (o se abrió otro) mientras se generaba: "
                                   "no se publica una mezcla. Vuelve a correr `publicar generar`.")
        paquete.instalar(staging, carpeta, resumen.pop("ficha_json"), {
            "proyecto": proyecto, "tiempos_s": tiempos, **resumen})
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    resumen.update(carpeta=carpeta, tiempos_s=tiempos, calidad=calidad)
    _imprimir(eco, resumen)
    return resumen


def _exigir(entregas: EnFondo) -> list[dict]:
    """Los registros de los entregables; si faltó uno que el paquete necesita, el error con
    todos los que faltaron (espera a que la API termine de intentarlos)."""
    registros = entregas.esperar()
    por_archivo = {e.archivo: e for e in entregas.entregables}
    graves = [r for r in registros if r["status"] != "ok" and not por_archivo[r["file"]].opcional]
    if graves:
        raise PublicacionError("Faltan entregables que el paquete necesita:\n" + "\n".join(
            f"  - {r['label']}: {r['note']}" for r in graves))
    return registros


def _armar(cliente, todos, fuera, paralelo, doc, data, g, f, calidad, pista, staging, tiempos,
           eco) -> dict:
    """Entregables (de la API) y lo local (saneo, vista 3D, video), en paralelo si `paralelo`
    (D6 de video-tienda-pulido), y el paquete. Sin paralelo, un entregable que falta corta
    ANTES del video; en paralelo, el video se aborta en cuanto la API falla uno."""
    from apolo.publicacion import textos
    from apolo.services.guion_video import capitulos

    rec = Recolector(cliente, staging / "entregables", eco=False)
    entregas = EnFondo(rec, todos, omitir=fuera, paralelo=paralelo)
    try:
        if entregas.grave.is_set():
            _exigir(entregas)
        apolo, informe_saneo, vista, video = _lo_local(doc, data, g, f, pista, staging, tiempos,
                                                       eco, entregas)
        t = time.perf_counter()
        registros = _exigir(entregas)
    except BaseException:
        entregas.cancelar()  # que no escriba más en `staging`: quien llama lo va a borrar
        with contextlib.suppress(Exception):
            entregas.esperar()
        raise
    tiempos["entregables"] = entregas.segundos
    if paralelo:  # lo que el video no alcanzó a tapar
        tiempos["espera de entregables"] = time.perf_counter() - t
    faltan = [r for r in registros if r["status"] != "ok"]

    t = time.perf_counter()
    caps = capitulos(g)
    try:
        (staging / "youtube.txt").write_text(textos.youtube(f, caps), encoding="utf-8")
    except ValueError as exc:  # la descripción no entra en la de YouTube
        raise PublicacionError(str(exc)) from exc
    glb, html = staging / vista["archivo"], staging / vista["html"]["archivo"]
    zips = paquete.armar(staging, staging / "entregables", todos, registros, ficha=f,
                         cifras=g["cifras"]["items"], calidad_=calidad,
                         variables=dict(doc.variables_raw), apolo=apolo,
                         extras=[(html, textos.VISTA_3D_HTML), (glb, textos.VISTA_3D_GLB),
                                 (video.miniatura, textos.VISTA_3D_POSTER)])
    publica = paquete.ficha_json(
        f, staging=staging, zips=zips, video=video.ruta, miniatura=video.miniatura,
        duracion_s=video.duracion_s, capitulos=caps,
        musica=fichas.musica_publica(f) if pista else None, calidad_=calidad,
        cifras=g["cifras"]["items"],
        vista_3d={"glb": glb, "html": html, "triangulos": vista["triangulos"],
                  "etiquetas": vista["html"]["etiquetas"]})
    tiempos["paquete"] = time.perf_counter() - t
    return {"ficha_json": publica, "faltantes": [f"{r['label']}: {r['note']}" for r in faltan],
            "saneo": informe_saneo, "registros": registros, "vista_3d": vista,
            "paralelo": paralelo,
            "video": {"fotogramas": video.fotogramas, "duracion_s": video.duracion_s,
                      "segundos": round(video.segundos, 2), "con_musica": video.con_musica,
                      "pasos_sin_prefijo": video.pasos_sin_prefijo},
            "zips": {nivel: str(ruta.name) for nivel, ruta in zips.items()},
            "bytes": {nivel: ruta.stat().st_size for nivel, ruta in zips.items()}}


def _lo_local(doc, data, g, f, pista, staging, tiempos, eco, entregas: EnFondo):
    """Lo que se hace aquí, sobre la copia propia del documento: saneo, vista 3D y video.
    Devuelve (apolo saneado, informe del saneo, vista 3D, informe del video)."""
    from apolo.media.codificar import ErrorCodificacion
    from apolo.publicacion import saneo, vista3d, vista3d_html
    from apolo.publicacion import video as videos

    t = time.perf_counter()
    apolo, informe_saneo = saneo.sanear_apolo(data, nombre=f["titulo"])
    tiempos["saneo"] = time.perf_counter() - t

    t = time.perf_counter()
    try:  # vista-3d-tienda D1-D2: sin gltfpack sale sin comprimir y lo dice `aviso`
        vista = vista3d.generar(doc, staging / vista3d.ARCHIVO, titulo=f["titulo"])
    except (ValueError, RuntimeError) as exc:  # nada visible, el escritor de OCCT falló
        raise PublicacionError(f"La vista 3D no salió: {exc}") from exc
    if vista["aviso"]:
        eco(f"Aviso (vista 3D): {vista['aviso']}")
    tiempos["vista 3d"] = time.perf_counter() - t

    t = time.perf_counter()
    if not g["cierre"]["url"] and f["url_tienda"]:
        g = copy.deepcopy(g)
        g["cierre"]["url"] = f["url_tienda"]
    ultimo = [-1.0]

    def progreso(hechos: int, total: int) -> None:
        if entregas.grave.is_set():  # la API no pudo con uno que el paquete necesita
            _exigir(entregas)
        if time.perf_counter() - ultimo[0] > 5:
            ultimo[0] = time.perf_counter()
            eco(f"  video: {hechos}/{total} fotogramas")

    if entregas.grave.is_set():
        _exigir(entregas)
    try:
        video = videos.renderizar(doc, g, staging, musica=pista, progreso=progreso)
    except (ValueError, ErrorCodificacion) as exc:  # escena vacía, guion de 0 s, ffmpeg falló
        raise PublicacionError(f"El video no salió: {exc}") from exc
    tiempos["video"] = time.perf_counter() - t

    t = time.perf_counter()  # vista-3d-tienda D3: el póster es la miniatura del video
    vista["html"] = vista3d_html.escribir(doc, staging / vista3d_html.ARCHIVO, titulo=f["titulo"],
                                          ident=f["slug"], vista=vista,
                                          poster=video.miniatura.name)
    tiempos["vista 3d"] += time.perf_counter() - t
    return apolo, informe_saneo, vista, video


def _imprimir(eco, r: dict) -> None:
    cal, v, s = r["calidad"], r["video"], r["saneo"]
    eco(f"Publicación lista en {r['carpeta']}")
    eco(f"  puerta de entrega: {cal['veredicto']}"
        + (" — publicada «con observaciones»" if cal["con_observaciones"] else ""))
    eco("  entregables: " + ("todos" if not r["faltantes"] else
                             "faltan " + "; ".join(r["faltantes"])))
    eco("  .apolo saneado: " + ("; ".join(s["quitado"]) or "no había nada que quitar"))
    for a in s["adjuntos"]:
        eco(f"  ¡revisa! adjunto {a['digest']} ({a['bytes']:,} B, usado por "
            f"{', '.join(a['usado_por']) or 'nadie'}): un STEP de proveedor puede no ser "
            "redistribuible.")
    for d in s["desconocido"]:
        eco(f"  ¡revisa! se quitó por desconocida: {d}")
    eco(f"  video: {v['fotogramas']} fotogramas, {v['duracion_s']:.1f} s"
        + (", con música" if v["con_musica"] else ", sin música")
        + (f"; pasos sin prefijo: {v['pasos_sin_prefijo']}" if v["pasos_sin_prefijo"] else ""))
    w = r["vista_3d"]
    eco(f"  vista 3D: {w['archivo']} ({w['bytes'] / 1e6:.2f} MB"
        + (f", {w['comprimido_con']}" if w["comprimido_con"] else ", SIN comprimir")
        + f"; {w['triangulos']:,} triángulos dibujados, tope {w['tope_triangulos']:,}) y "
        f"{w['html']['archivo']} con {len(w['html']['etiquetas'])} etiqueta(s)")
    eco("  zips: " + " · ".join(f"{r['zips'][n]} ({r['bytes'][n] / 1e6:.1f} MB)"
                                for n in r["zips"]))
    eco("  tiempos: " + " · ".join(f"{k} {x:.1f} s" for k, x in r["tiempos_s"].items())
        + (" (entregables en paralelo con la vista 3D y el video)" if r.get("paralelo") else ""))
    eco("Sube a mano a YouTube video.mp4 con miniatura.png y el texto de youtube.txt (D15); "
        "luego pon el enlace en url_video de ficha.json.")
    eco(f"Vista 3D: sube {w['archivo']}, {w['html']['poster']} y el trozo de "
        f"{w['html']['archivo']} a la tienda (cómo, en el comentario al principio del trozo).")
