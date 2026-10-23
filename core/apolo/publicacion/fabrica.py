"""`publicar fabrica`: una máquina modelada sale publicada en la tienda con un solo comando (plan
fabrica-de-publicaciones, F3 · D2, D5–D7).

Encadena ocho pasos sobre la carpeta de la versión (`publicaciones_dir()/<slug>/<version>/`):

  1. `guion`: `flujo.guion` si la carpeta no tiene `guion.json` (lo normal es que ya lo haya
     corrido el modelador al redactar la ficha). Con el navegador, el video lleva la máquina
     ANDANDO CON PRODUCTO (ajuste D10, `publicacion/marcha.py`): la de `marcha.json` o la
     automática de un transportador, simulada antes; a un guion que no la trae se le suma. Si
     no hay marcha posible, lo avisa y sigue (`marcha=False`: `--sin-marcha`); si la faja que
     dibujaría el visor no es fiel al modelo (ajuste D13c), PARA con la pieza que atraviesa y
     cuánto, también con la marcha que ya traía el guion. Un `guion.json` armado sobre otra
     versión del log se REHACE aquí (no en `generar`), conservando su marcha, título, subtítulo
     y lema (`publicacion/guion_vigente.py`, F6 de puerta-de-publicacion);
  2. `ficha`: `preparar.revisar` (= `publicar ficha --revisar`), la `familia` declarada (D10 de
     puerta-de-publicacion) y que la ficha sea del modelo de HOY (`ficha_vigente.py`, F6: la
     firma del log con que se redactó o re-validó, y su masa y medidas contra el modelo); si
     falla, PARA y dice qué falta: la ficha la redacta el modelador (D1), la fábrica no la
     inventa ni la re-sella;
  3. `calidad`: la puerta de publicación (plan puerta-de-publicacion, F1) en la API; deja
     `calidad.json` y `calidad.md` y PARA si no aprueba, con cada ítem que no pasó;
  4. `revision`: `revision.json` del revisor de taller sobre la firma de `calidad.json`, sin
     ALTA ni MEDIA abiertos (F4 · D6, `aprobacion.exigir_revision`); antes del video: si el
     modelo se corrige, no se graba dos veces;
  5. `generar`: `flujo.generar` con el navegador en nivel rápido (D2; si cae a VTK, lo dice),
     bajo el candado de render de la PC (D7: una GPU, una grabación a la vez). Se niega sin
     `calidad.json` aprobado sobre el mismo modelo. Con `ficha.json` en la carpeta ya está
     generado y no se rehace;
  6. `cuadros`: saca tres cuadros del video (armado, marcha, cierre) y PARA hasta que
     `cuadros.json` diga OK en los tres, para ESE video (F4 · D7);
  7. `familia`: con < 2 máquinas aprobadas de su familia, PARA hasta `publicar aprobar` (D10);
  8. `tienda`: `tienda.subir` (publica, o deja en borrador con `borrador`); se niega sin la
     calidad, la revisión, los cuadros o la familia aprobados. Ningún paso tiene `--forzar`
     (D11).

Cada paso queda en `estado.json` de la carpeta (hecho/fallo, cuándo, cuánto tardó, las últimas
líneas de su salida y el error). Volver a correrla salta lo hecho y retoma desde el paso que
falló (D6); `desde` fuerza a rehacer desde un paso. No toca YouTube (D5): una máquina publicada
entra sola a la cola de la tienda y la sube el subidor (`cola_youtube`).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from apolo.publicacion import paquete
from apolo.publicacion.paquete import GUION, PublicacionError

PASOS = ("guion", "ficha", "calidad", "revision", "generar", "cuadros", "familia", "tienda")
ESTADO = "estado.json"
LINEAS = 15  # de la salida de cada paso, en estado.json
RENDERS = ("navegador", "vtk")
#: Los errores con mensaje para la persona (PublicacionError y FfmpegNoEncontrado son
#: RuntimeError; FichaError, GuionError y SaneoError, ValueError): paran con el mensaje.
ESPERABLES = (RuntimeError, ValueError, OSError)


class FabricaError(PublicacionError):
    """La fábrica paró en un paso; el mensaje dice cuál, por qué y cómo seguir."""


@dataclass
class Encargo:
    """Lo que necesitan los pasos. `cliente`: el de la API de Apolo; `cliente_tienda`: el de la
    tienda (los tests); `paralelo`: entregables en paralelo con el video (sólo con la API en otro
    proceso, ver `flujo.generar`)."""

    proyecto: int
    carpeta: Path
    slug: str
    version: str
    raiz: Path
    tienda: str
    cliente: object = None
    url: str | None = None
    llave: str | None = None
    render: str = "navegador"
    borrador: bool = False
    paralelo: bool = False
    sin_esperar: bool = False
    marcha: bool = True
    candado: Path | None = None
    cliente_tienda: object = None
    eco: object = print
    datos: dict = field(default_factory=dict)


# ------------------------------------------------------------------ los pasos
def _sin_marcha_porque(e: Encargo) -> str | None:
    if not e.marcha:
        return "pediste --sin-marcha"
    if e.render != "navegador":
        return f"con --render {e.render} el video no anima la máquina andando"
    return None


def _marcha_en_guion(e: Encargo) -> float | None:
    """Suma la marcha (`publicacion/marcha.py`) al guion.json que dejó el modelador sin ella.
    Devuelve sus segundos, o None si el video va sin marcha (avisado)."""
    from apolo.publicacion import flujo, marcha
    from apolo.services.guion_video import MODO_MONTAJE, GuionError, validar_guion

    ruta = e.carpeta / GUION
    g = json.loads(ruta.read_text(encoding="utf-8"))
    if g.get("marcha") or g.get("modo") == MODO_MONTAJE:
        api = flujo._Api(e.cliente)
        api.abrir(e.proyecto)
        doc = flujo._documento(api.apolo())
    if g.get("marcha"):
        e.eco(f"{GUION} ya trae la máquina andando: la dejo como está y la pruebo contra el "
              "modelo (D13).")
        marcha.verificar(doc, g["marcha"], eco=e.eco)
        return float(g["marcha"].get("duracion_s") or 0.0)
    if g.get("modo") != MODO_MONTAJE:
        e.eco("Aviso: el guion es de diseño (el navegador graba el de montaje): sin la máquina "
              "andando.")
        return None
    m = marcha.elegir(doc, e.carpeta, extra_s=marcha.extra_del_guion(g), eco=e.eco)
    if m is None:
        return None
    try:
        validar_guion({**g, "marcha": m}, doc)
    except GuionError as exc:
        e.eco(f"Aviso: no sumo la máquina andando al guion: {exc}")
        return None
    ruta.write_text(json.dumps({**g, "marcha": m}, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    e.eco(f"Sumé {m['duracion_s']:g} s de la máquina andando a {GUION}.")
    return m["duracion_s"]


def paso_guion(e: Encargo) -> dict:
    from apolo.publicacion import flujo, marcha

    porque = _sin_marcha_porque(e)
    if porque:
        e.eco(f"Sin la máquina andando: {porque}.")
    if (e.carpeta / GUION).is_file():
        from apolo.publicacion import guion_vigente

        viejo = guion_vigente.leer(e.carpeta)
        firmas = guion_vigente.firma_vencida(e, viejo)
        if firmas:  # el modelo cambió después de armarlo: generar lo rechazaría (F6)
            return guion_vigente.rehacer(e, viejo, firmas, sin_marcha=porque)
        e.eco(f"{GUION} ya está en {e.carpeta} y es del modelo de hoy: no lo rehago.")
        return {"ya_estaba": True, "marcha_s": None if porque else _marcha_en_guion(e)}
    elegida: dict = {}

    def _marcha(doc):
        elegida["m"] = marcha.elegir(doc, e.carpeta, eco=e.eco)
        return elegida["m"]

    r = flujo.guion(e.cliente, e.proyecto, raiz=e.raiz, slug=e.slug, version=e.version,
                    tienda=e.tienda, eco=e.eco, marcha=None if porque else _marcha)
    m = elegida.get("m")
    return {"etapas": r["etapas"], "duracion_s": round(r["duracion_s"], 1),
            "marcha_s": m["duracion_s"] if m else None}


def paso_ficha(e: Encargo) -> dict:
    from apolo.publicacion import preparar
    from apolo.publicacion.ficha import FichaError

    try:
        preparar.revisar(e.carpeta, tienda=e.tienda, eco=e.eco)
    except (FichaError, PublicacionError) as exc:
        raise FabricaError(
            f"{exc}\nLa ficha la redacta el modelador (D1), no la fábrica: completa "
            f"{e.carpeta / paquete.FICHA_YAML}, revísala con `publicar ficha --revisar` hasta que "
            "salga limpia y vuelve a correr `publicar fabrica` (retoma desde la ficha).") from None
    from apolo.publicacion import aprobacion

    familia = aprobacion.familia(e.carpeta)
    if not familia:
        raise FabricaError(
            f"{e.carpeta / paquete.FICHA_YAML} no declara su «familia» (p. ej. «faja de banda», "
            "«transportador de rodillos»): las dos primeras máquinas de cada familia las aprueba "
            "Mario (plan puerta-de-publicacion, D10). Complétala y vuelve a correr `publicar "
            "fabrica` (retoma desde la ficha).")
    from apolo.publicacion import ficha_vigente

    try:
        vigente = ficha_vigente.exigir(e.carpeta, e.cliente, e.proyecto, eco=e.eco)
    except ValueError as exc:
        raise FabricaError(str(exc)) from None
    return {"familia": familia, "firma": vigente["firma"]}


def paso_calidad(e: Encargo) -> dict:
    """La puerta de publicación (plan puerta-de-publicacion, F1): corre en la API, deja
    `calidad.json` y `calidad.md` en la carpeta y PARA si no aprueba, con cada ítem que no pasó
    (Jidoka: ante un defecto la línea se para; no hay `--forzar` en la fábrica, D11)."""
    from apolo.publicacion import calidad, flujo
    from apolo.publicacion.ficha import FichaError, leer

    eco = e.eco or (lambda *_a, **_k: None)
    api = flujo._Api(e.cliente)
    api.abrir(e.proyecto)
    r = calidad.pedir(api, eco=eco)
    try:
        titulo = leer(e.carpeta / paquete.FICHA_YAML).get("titulo") or e.slug
    except (FichaError, OSError, ValueError):
        titulo = e.slug
    calidad.escribir(e.carpeta, r, titulo=titulo, proyecto=e.proyecto)
    c = r.get("conteos") or {}
    eco(f"Puerta de publicación: {'APROBADA' if r['aprobado'] else 'NO aprobada'} "
          f"({c.get('OK', 0)} cumplen, {c.get('FALLA', 0)} no cumplen, "
          f"{c.get('SIN_EVALUAR', 0)} sin evaluar, {c.get('NO_APLICA', 0)} no aplican).")
    if not r["aprobado"]:
        raise FabricaError(
            f"La puerta de publicación NO aprobó «{e.slug}» {e.version} (detalle en "
            f"{e.carpeta / calidad.CALIDAD_MD}):\n{calidad.fallas(r)}\nCorrige el MODELO (no el "
            "ítem) y vuelve a correr `publicar fabrica`: retoma desde «calidad».")
    return {"aprobado": True, "conteos": c, "firma": r.get("firma"),
            "version_registro": r.get("version_registro"),
            "segundos_api": (r.get("tiempos_s") or {}).get("total")}


def paso_revision(e: Encargo) -> dict:
    """D6: el veredicto del revisor de taller sobre la firma que aprobó la puerta."""
    from apolo.publicacion import aprobacion

    return aprobacion.exigir_revision(e.carpeta)


def paso_cuadros(e: Encargo) -> dict:
    """D7: los tres cuadros del video, revisados por un agente con visión."""
    from apolo.publicacion import aprobacion

    aprobacion.preparar_cuadros(e.carpeta, eco=e.eco)
    return aprobacion.exigir_cuadros(e.carpeta)


def paso_familia(e: Encargo) -> dict:
    """D10: familia nueva → Mario aprueba."""
    from apolo.publicacion import aprobacion

    return aprobacion.exigir_familia(e.carpeta, e.slug, e.version)


def paso_generar(e: Encargo) -> dict:
    from apolo.publicacion import flujo
    from apolo.publicacion.candado import Candado

    if paquete.publicada(e.carpeta):
        e.eco(f"{paquete.FICHA_JSON} ya está en {e.carpeta}: el paquete está generado, no lo "
              "rehago.")
        return {"ya_estaba": True}
    from apolo.publicacion import guion_vigente

    firmas = guion_vigente.firma_vencida(e, guion_vigente.leer(e.carpeta))
    if firmas:  # el guion se hizo en una corrida anterior y el modelo cambió después
        raise FabricaError(
            f"{GUION} se armó sobre otra versión del proyecto (firma {firmas[0]}; hoy "
            f"{firmas[1]}). Corre `publicar fabrica --desde guion`: rehace el guion conservando "
            "su marcha, título, subtítulo y lema, y vuelve a pasar la ficha, la calidad y la "
            "revisión sobre el modelo de hoy.")
    with Candado(e.candado, que=f"{e.slug} {e.version} (proyecto {e.proyecto})",
                 sin_esperar=e.sin_esperar, eco=e.eco) as c:
        r = flujo.generar(e.cliente, e.proyecto, raiz=e.raiz, slug=e.slug, version=e.version,
                          render=e.render, nivel="rapido", tienda=e.tienda, url=e.url,
                          paralelo=e.paralelo, eco=e.eco)
    usado = r["video"]["render"]
    if usado != e.render:
        e.eco(f"Aviso: el video salió con {usado}, no con {e.render} (D2: sin navegador o sin "
              "GPU, la fábrica cae a VTK). Más arriba está el porqué.")
    return {"render": usado, "pedido": e.render, "veredicto": r["calidad"]["veredicto"],
            "espera_candado_s": round(c.esperado_s, 1),
            "tiempos_s": {k: round(v, 1) for k, v in r["tiempos_s"].items()}}


def paso_tienda(e: Encargo) -> dict:
    from apolo.publicacion import tienda

    r = tienda.subir(e.carpeta, tienda=e.tienda, llave=e.llave, borrador=e.borrador, eco=e.eco,
                     cliente=e.cliente_tienda)
    return {"url": r["url"], "publicada": r["publicada"]}


PASOS_REALES = {"guion": paso_guion, "ficha": paso_ficha, "calidad": paso_calidad,
                "revision": paso_revision, "generar": paso_generar, "cuadros": paso_cuadros,
                "familia": paso_familia, "tienda": paso_tienda}


# ------------------------------------------------------------------ estado.json
def leer_estado(carpeta) -> dict | None:
    try:
        datos = json.loads((Path(carpeta) / ESTADO).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return datos if isinstance(datos, dict) and isinstance(datos.get("pasos"), dict) else None


def terminada(estado: dict | None) -> bool:
    """Llegó a la tienda (el último paso). Una versión publicada antes de que la fábrica tuviera
    los pasos de F4 sigue terminada: no se reabre sola."""
    return bool(estado) and (estado["pasos"].get(PASOS[-1]) or {}).get("estado") == "hecho"


def _guardar(carpeta: Path, estado: dict) -> None:
    carpeta.mkdir(parents=True, exist_ok=True)
    estado["actualizado"] = datetime.now().isoformat(timespec="seconds")
    tmp = carpeta / f".{ESTADO}.tmp"
    tmp.write_text(json.dumps(estado, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, carpeta / ESTADO)


def carpeta_de_trabajo(raiz, slug: str, version: str | None, *, desde: str | None = None) -> Path:
    """La versión que toca: la pedida; si no, una con la fábrica a medias (la última), con
    `desde` la última que pasó por la fábrica, la única con guion sin generar, o una nueva
    (`paquete.version_libre`: 1.0.0 si está libre)."""
    raiz = Path(raiz)
    if version:
        return paquete.carpeta_version(raiz, slug, version)
    todas = paquete.versiones(raiz, slug)
    estados = {v: leer_estado(paquete.carpeta_version(raiz, slug, v)) for v in todas}
    a_medias = [v for v in todas if estados[v] and not terminada(estados[v])]
    if not a_medias and desde is not None:
        a_medias = [v for v in todas if estados[v]]
    if a_medias:
        return paquete.carpeta_version(raiz, slug, a_medias[-1])
    pendientes = [v for v in todas if (paquete.carpeta_version(raiz, slug, v) / GUION).exists()
                  and not paquete.publicada(paquete.carpeta_version(raiz, slug, v))]
    if len(pendientes) > 1:
        raise PublicacionError(f"«{slug}» tiene varias versiones sin publicar "
                               f"({', '.join(pendientes)}): elige una con --version.")
    if pendientes:
        return paquete.carpeta_version(raiz, slug, pendientes[0])
    return paquete.carpeta_version(raiz, slug, paquete.version_libre(raiz, slug))


# ------------------------------------------------------------------ la cadena
def _ocultar(texto: str, llave: str | None) -> str:
    if not llave:
        return texto
    from apolo.publicacion.tienda import prefijo

    return texto.replace(llave, prefijo(llave))


def fabricar(e: Encargo, *, desde: str | None = None, pasos: dict | None = None,
             entorno=None) -> dict:
    """Corre los pasos que faltan y deja `estado.json`. `pasos`: {nombre: función(Encargo) →
    dict} para reemplazar alguno (los tests). Devuelve el estado final; si un paso falla, lo
    anota y lanza `FabricaError` con el error y cómo retomar."""
    from apolo.publicacion import tienda

    if desde is not None and desde not in PASOS:
        raise PublicacionError(f"Paso desconocido: {desde!r} (válidos: {', '.join(PASOS)})")
    if e.render not in RENDERS:
        raise PublicacionError(f"Render desconocido: {e.render!r} (válidos: {', '.join(RENDERS)})")
    pasos = {**PASOS_REALES, **(pasos or {})}
    eco = e.eco or (lambda *_a, **_k: None)
    estado = leer_estado(e.carpeta) or {"formato": 1, "pasos": {}}
    estado.update(proyecto=e.proyecto, slug=e.slug, version=e.version)
    if desde is not None:
        for p in PASOS[PASOS.index(desde):]:
            estado["pasos"].pop(p, None)
    hecho = {p for p in PASOS if (estado["pasos"].get(p) or {}).get("estado") == "hecho"}
    if "tienda" not in hecho and e.llave is None:
        e.llave = tienda.llave_del_entorno(entorno)  # antes de minutos de trabajo, no al final
    eco(f"Fábrica: «{e.slug}» {e.version} (proyecto {e.proyecto}) en {e.carpeta}")
    for p in PASOS:
        if p in hecho:
            eco(f"[{p}] hecho en una corrida anterior: lo salto.")
            continue
        lineas: list[str] = []

        def eco_paso(*a, _lineas=lineas, **_k):
            texto = " ".join(str(x) for x in a)
            _lineas.extend(texto.splitlines() or [""])
            eco(texto)

        e.eco = eco_paso
        eco(f"[{p}] …")
        inicio, t = datetime.now().isoformat(timespec="seconds"), time.perf_counter()
        try:
            datos = pasos[p](e) or {}
        except Exception as exc:  # noqa: BLE001 — se anota y sube: esperable o no, retoma aquí
            error = _ocultar(str(exc) or type(exc).__name__, e.llave)
            estado["pasos"][p] = {"estado": "fallo", "inicio": inicio,
                                  "segundos": round(time.perf_counter() - t, 1),
                                  "error": error,
                                  "salida": [_ocultar(x, e.llave) for x in lineas[-LINEAS:]]}
            _guardar(e.carpeta, estado)
            if not isinstance(exc, ESPERABLES):
                raise  # un error de programa: con su traza
            raise FabricaError(f"La fábrica paró en «{p}»:\n{error}\nEstado en "
                               f"{e.carpeta / ESTADO}; al volver a correr `publicar fabrica`, "
                               f"retoma desde «{p}».") from None
        finally:
            e.eco = eco
        estado["pasos"][p] = {"estado": "hecho", "inicio": inicio,
                              "segundos": round(time.perf_counter() - t, 1),
                              "datos": datos,
                              "salida": [_ocultar(x, e.llave) for x in lineas[-LINEAS:]]}
        _guardar(e.carpeta, estado)
    reporte(estado, eco)
    return estado


def reporte(estado: dict, eco=print) -> None:
    """Tiempos por paso, la URL de la tienda, si quedó publicada y qué sigue (YouTube, D5)."""
    pasos = estado["pasos"]
    eco(f"\nFábrica terminada: «{estado['slug']}» {estado['version']} "
        f"(proyecto {estado['proyecto']})")
    for p in PASOS:
        x = pasos.get(p) or {}
        datos = x.get("datos") or {}
        nota = ("ya estaba" if datos.get("ya_estaba") else
                "rehecho: el modelo cambió" if datos.get("rehecho") else
                f"video con {datos['render']}" if p == "generar" and "render" in datos else "")
        if p == "guion" and "marcha_s" in datos:
            nota += ("; " if nota else "") + (f"{datos['marcha_s']:g} s andando"
                                              if datos["marcha_s"] else "sin la máquina andando")
        if p == "generar" and datos.get("espera_candado_s"):
            nota += f"; esperó el candado {datos['espera_candado_s'] / 60:.1f} min"
        eco(f"  {p:<8} {x.get('segundos', 0):>7.1f} s  ({x.get('inicio', '?')})"
            + (f"  {nota}" if nota else ""))
    eco(f"  total    {sum((pasos.get(p) or {}).get('segundos', 0) for p in PASOS):>7.1f} s")
    t = (pasos.get("tienda") or {}).get("datos") or {}
    if t.get("publicada"):
        eco(f"Publicada en la tienda: {t.get('url')}")
        eco("YouTube: la máquina quedó en la cola de la tienda; la sube el subidor "
            "(`publicar youtube --cola`, tarea diaria en UNA sola PC), PRIVADA hasta la "
            "auditoría: pásala a pública en YouTube Studio cuando toque.")
    else:
        eco(f"Quedó en BORRADOR en la tienda: {t.get('url')}. No entra a la cola de YouTube "
            "hasta que la publiques (en la tienda, o `publicar subir` sin --borrador).")
