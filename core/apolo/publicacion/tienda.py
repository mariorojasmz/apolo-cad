"""Sube un paquete ya generado a la tienda (apolocad.com) y lo publica, sin navegador (plan
publicacion-tienda, F6).

Cliente HTTP puro: lee la carpeta que dejó `publicar generar`
(`publicaciones_dir()/<slug>/<version>/`) y habla con la tienda con una «llave de
publicación» (`Authorization: Bearer apolo_pub_…`, de la variable `APOLO_TIENDA_LLAVE`). No
toca la API de Apolo ni el documento. Cuatro pasos, cada uno corta antes del siguiente:

  1. revisión (`POST /api/maquina/importacion/revision`): la tienda dice qué rol tiene cada
     archivo y qué falta; con errores, o sin miniatura o paquete gratis, no se sube nada;
  2. cada archivo del plan: pedir la subida firmada, mandarlo TAL CUAL la firma lo pide
     (método, url y cabeceras; el Bearer sólo si la url es de la propia tienda) y confirmarla.
     Si uno falla, no se importa: una máquina a medias es peor que ninguna;
  3. importar la ficha con los archivos subidos;
  4. publicarla (salvo `borrador`).

La llave nunca se imprime: en un error, a lo sumo su prefijo (`prefijo`). `Cliente` (Bearer,
errores, archivos por trozos) lo usa también el subidor de la cola de YouTube (`cola_youtube`).
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from apolo.publicacion import textos
from apolo.publicacion.paquete import FICHA_JSON, PublicacionError, publicada, versiones

LLAVE_ENV = "APOLO_TIENDA_LLAVE"
URL_ENV = "APOLO_TIENDA_URL"
TIENDA = textos.TIENDA
#: Lo que la tienda acepta, por extensión; el resto de la carpeta (ficha.yaml, guion.json,
#: generacion.json, youtube.txt, vista-3d.html) es privado o no va a la tienda.
MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
        ".mp4": "video/mp4", ".glb": "model/gltf-binary", ".zip": "application/zip"}
#: Sin estos roles la tienda no puede mostrar la máquina: se corta antes de subir.
ROLES_OBLIGATORIOS = ("miniatura", "paquete_gratis")
REINTENTOS_CONFIRMACION = 3
TROZO = 1 << 20  # 1 MiB por escritura: un video de cientos de MB no pasa por la memoria
PREFIJO = 12


class LlaveFaltante(PublicacionError):
    """No hay `APOLO_TIENDA_LLAVE`: el mensaje explica cómo crearla y ponerla."""


class TiendaError(PublicacionError):
    """La tienda rechazó un paso; el mensaje trae su `error` y sus `errores` tal cual."""

    def __init__(self, mensaje: str, status: int | None = None):
        super().__init__(mensaje)
        self.status = status


def prefijo(llave: str) -> str:
    """Lo único de la llave que se muestra: sus primeros 12 caracteres."""
    return llave[:PREFIJO] + "…"


def llave_del_entorno(entorno=None) -> str:
    entorno = os.environ if entorno is None else entorno
    llave = (entorno.get(LLAVE_ENV) or "").strip()
    if not llave:
        raise LlaveFaltante(
            f"Falta la llave de publicación ({LLAVE_ENV}).\n"
            "  1. Créala en la tienda: Mi cuenta → Llaves de publicación (se muestra una sola "
            "vez: cópiala).\n"
            "  2. Ponla en esta consola de PowerShell:\n"
            f"       $env:{LLAVE_ENV} = 'apolo_pub_...'\n"
            "     o, para que quede en las consolas nuevas:\n"
            f"       [Environment]::SetEnvironmentVariable('{LLAVE_ENV}','apolo_pub_...','User')\n"
            "  No la pases como argumento: quedaría en el historial.")
    return llave


def url_de_la_tienda(argumento: str | None, entorno=None) -> str:
    entorno = os.environ if entorno is None else entorno
    url = (argumento or entorno.get(URL_ENV) or TIENDA).strip().rstrip("/")
    if not url.startswith(("https://", "http://")):
        raise PublicacionError(f"La URL de la tienda debe empezar con https:// (llegó {url!r})")
    return url


# ------------------------------------------------------------------ dónde está el paquete
def slug_de_proyecto(cliente_api, proyecto: int) -> str:
    """El slug que `publicar guion` le dio al proyecto (el de su nombre), leído de la lista de
    proyectos de la API: sin abrirlo, así la UI no cambia de proyecto."""
    from apolo.publicacion.ficha import slug

    try:
        resp = cliente_api.get("/api/projects")
        resp.raise_for_status()
        lista = resp.json()
    except Exception as exc:  # noqa: BLE001 — conexión rechazada, 5xx, no es JSON
        raise PublicacionError(
            f"No pude leer el nombre del proyecto {proyecto} en la API de Apolo ({exc}). "
            "Levanta Apolo o pasa --slug (y --version) para subir sin la API.") from None
    nombre = next((p.get("name") for p in lista if p.get("id") == proyecto), None)
    if nombre is None:
        raise PublicacionError(f"La API de Apolo no tiene el proyecto {proyecto}.")
    return slug(nombre)


def carpeta_publicada(raiz, slug: str, version: str | None, eco=print) -> Path:
    """La carpeta de la versión a subir: la pedida o, sin `version`, la última generada (la que
    tiene `ficha.json`)."""
    raiz = Path(raiz)
    hechas = [v for v in versiones(raiz, slug) if publicada(raiz / slug / v)]
    if version is None:
        if not hechas:
            raise PublicacionError(f"No hay ningún paquete generado de «{slug}» en {raiz}: "
                                   "corre `publicar generar` primero (o pasa --slug si usaste "
                                   "otro).")
        version = hechas[-1]
        if len(hechas) > 1 and eco:
            eco(f"Subo la versión {version}, la última generada de «{slug}» "
                f"(hay {', '.join(hechas)}; elige otra con --version).")
    carpeta = raiz / slug / version
    if not publicada(carpeta):
        raise PublicacionError(f"{carpeta} no tiene {FICHA_JSON}: esa versión no está generada. "
                               "Corre `publicar generar` primero.")
    return carpeta


def contenido(carpeta: Path) -> tuple[dict, list[Path]]:
    """(ficha.json, archivos que se ofrecen a la tienda): los de la raíz de la carpeta con un
    tipo que la tienda acepta; la tienda decide sus roles."""
    try:
        ficha = json.loads((carpeta / FICHA_JSON).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublicacionError(f"No pude leer {carpeta / FICHA_JSON}: {exc}") from None
    archivos = sorted(p for p in carpeta.iterdir()
                      if p.is_file() and p.suffix.lower() in MIME)
    return ficha, archivos


def sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as fh:
        for trozo in iter(lambda: fh.read(TROZO), b""):
            h.update(trozo)
    return h.hexdigest()


# ------------------------------------------------------------------ cliente de la tienda
def _mensaje(resp) -> str:
    """El `error` de la tienda con sus `errores` y `campos`, tal cual."""
    try:
        datos = resp.json()
    except ValueError:
        return (resp.text or "").strip()[:500] or "(sin detalle)"
    if not isinstance(datos, dict):
        return str(datos)[:500]
    partes = [str(datos.get("error") or "(sin detalle)")]
    partes += [f"  - {e}" for e in datos.get("errores") or []]
    partes += [f"  - {k}: {v}" for k, v in (datos.get("campos") or {}).items()]
    return "\n".join(partes)


class Cliente:
    def __init__(self, url: str, llave: str, cliente=None, eco=print, espera_s: float = 2.0):
        import httpx

        self.url, self.llave, self.eco, self.espera_s = url, llave, eco, espera_s
        self._httpx = httpx
        self.propio = cliente is None
        self.c = cliente or httpx.Client(timeout=httpx.Timeout(60.0))

    def cerrar(self) -> None:
        if self.propio:
            self.c.close()

    def _bearer(self) -> dict:
        return {"Authorization": f"Bearer {self.llave}"}

    def mismo_origen(self, url: str) -> bool:
        a, b = urlsplit(url), urlsplit(self.url)
        return (a.scheme, a.hostname, a.port) == (b.scheme, b.hostname, b.port)

    def _enviar(self, metodo: str, url: str, que: str, **kw):
        try:
            return self.c.request(metodo, url, **kw)
        except self._httpx.HTTPError as exc:
            raise TiendaError(f"No pude {que}: la tienda {self.url} no responde ({exc}).") from None

    def _rechazo(self, resp, que: str) -> TiendaError:
        detalle = _mensaje(resp)
        if resp.status_code == 401:
            texto = (f"La tienda no aceptó la llave {prefijo(self.llave)} al {que}: está mal "
                     "copiada, vencida o revocada. Crea otra en Mi cuenta → Llaves de "
                     f"publicación y ponla en {LLAVE_ENV}.\n  La tienda dijo: {detalle}")
        elif resp.status_code == 403:
            texto = f"La llave {prefijo(self.llave)} no tiene permiso para {que}: {detalle}"
        else:
            texto = f"La tienda rechazó {que} ({resp.status_code}): {detalle}"
        return TiendaError(texto.replace(self.llave, prefijo(self.llave)), resp.status_code)

    def api(self, metodo: str, ruta: str, que: str, cuerpo: dict | None, *,
            reintentar: dict = None):
        """Una llamada JSON a la tienda con el Bearer (`cuerpo` None: sin cuerpo). `reintentar`:
        {status: veces} que se repiten con espera antes de rendirse."""
        pendientes = dict(reintentar or {})
        while True:
            resp = self._enviar(metodo, self.url + ruta, que, json=cuerpo, headers=self._bearer())
            if resp.status_code < 400:
                try:
                    return resp.json()
                except ValueError:
                    raise TiendaError(f"La tienda respondió a {que} sin JSON "
                                      f"({resp.status_code}): ¿es {self.url} la tienda?") from None
            if pendientes.get(resp.status_code, 0) > 0:
                pendientes[resp.status_code] -= 1
                time.sleep(self.espera_s)
                continue
            raise self._rechazo(resp, que)

    def mandar(self, ruta: Path, firma: dict) -> None:
        """El archivo con EXACTAMENTE el método, la url y las cabeceras firmados (más el
        Content-Length, que una subida firmada exige y evita el envío por trozos); el Bearer,
        sólo si la url es de la propia tienda (la subida a disco fuera de producción)."""
        url = urljoin(self.url + "/", firma["url"])
        cabeceras = dict(firma.get("headers") or {})
        if not any(k.lower() == "content-length" for k in cabeceras):
            cabeceras["Content-Length"] = str(ruta.stat().st_size)
        if self.mismo_origen(url):
            cabeceras.update(self._bearer())
        resp = self._enviar(firma.get("metodo") or "PUT", url, f"subir {ruta.name}",
                            content=_leer(ruta, self.eco), headers=cabeceras)
        if resp.status_code >= 400:
            raise TiendaError(f"La subida de {ruta.name} falló ({resp.status_code}): "
                              f"{(resp.text or '').strip()[:300] or '(sin detalle)'}",
                              resp.status_code)

    def bajar(self, url: str, destino: Path, que: str) -> Path:
        """Un archivo de la tienda (su URL pública, quizá en otro origen: el bucket) a disco, por
        trozos; el Bearer, sólo si la url es de la propia tienda (fabrica-de-publicaciones F3)."""
        url = urljoin(self.url + "/", url)
        propia = self.mismo_origen(url)
        try:
            with self.c.stream("GET", url, headers=self._bearer() if propia else {}) as resp:
                if resp.status_code >= 400:
                    resp.read()
                    if propia:
                        raise self._rechazo(resp, que)
                    raise TiendaError(f"No pude {que} ({resp.status_code}).", resp.status_code)
                with open(destino, "wb") as fh:
                    for trozo in resp.iter_bytes(TROZO):
                        fh.write(trozo)
        except self._httpx.HTTPError as exc:
            raise TiendaError(f"No pude {que}: no responde ({exc}).") from None
        return destino


def _leer(ruta: Path, eco):
    """El archivo por trozos desde disco, con el avance por consola si es grande."""
    total, hecho, ultimo = ruta.stat().st_size, 0, time.perf_counter()
    with open(ruta, "rb") as fh:
        for trozo in iter(lambda: fh.read(TROZO), b""):
            hecho += len(trozo)
            yield trozo
            if eco and total > 8 * TROZO and (time.perf_counter() - ultimo > 3 or hecho == total):
                ultimo = time.perf_counter()
                eco(f"    {ruta.name}: {100 * hecho // total} % "
                    f"({hecho / 1e6:.0f} de {total / 1e6:.0f} MB)")


# ------------------------------------------------------------------ los cuatro pasos
def _plan(t: Cliente, ficha: dict, archivos: list[Path], eco) -> dict:
    nombres = [p.name for p in archivos]
    r = t.api("POST", "/api/maquina/importacion/revision", "revisar la ficha",
              {"ficha": ficha, "nombres": nombres})
    plan = r.get("plan") or {}
    existente = r.get("existente")
    eco(f"Tienda {t.url}: «{ficha.get('titulo')}» {ficha.get('slug')} {ficha.get('version')}"
        + (f" — ya existe (estado {existente.get('estado', '?')}): se actualiza."
           if isinstance(existente, dict) else " — máquina nueva."))
    for a in plan.get("archivos") or []:
        eco(f"  {a['nombre']} → {a['rol']} ({a.get('visibilidad', '?')}"
            + (", con cuenta)" if a.get("requiereCuenta") else ")"))
    for n in plan.get("ignorados") or []:
        eco(f"  {n}: la tienda no lo usa")
    faltan = list(plan.get("faltan") or [])
    errores = list(plan.get("errores") or [])
    bloquean = [f for f in faltan if f in ROLES_OBLIGATORIOS]
    if faltan:
        eco("  falta: " + ", ".join(faltan))
    locales = set(nombres)
    errores += [f"la tienda pidió {a['nombre']}, que no está en la carpeta"
                for a in plan.get("archivos") or [] if a.get("nombre") not in locales]
    if errores or bloquean or r.get("ok") is False:
        lista = errores + [f"falta el archivo de rol {f}" for f in bloquean]
        raise TiendaError("La tienda no puede importar este paquete; no subí nada:\n  - "
                          + "\n  - ".join(lista or ["(la revisión no dio ok, sin detalle)"]))
    return plan


def _subir_archivo(t: Cliente, ruta: Path, a: dict, eco) -> dict:
    tamano = ruta.stat().st_size
    eco(f"  subiendo {ruta.name} ({tamano / 1e6:.1f} MB)…")
    firma = t.api("POST", "/api/archivos/subidas", f"pedir la subida de {ruta.name}", {
        "nombre": ruta.name, "tipo": MIME[ruta.suffix.lower()], "tamano": tamano,
        "sha256": sha256(ruta), "visibilidad": a.get("visibilidad"),
        "requiere_cuenta": bool(a.get("requiereCuenta"))})
    t.mandar(ruta, firma)
    r = t.api("POST", "/api/archivos/subidas/confirmacion", f"confirmar la subida de {ruta.name}",
              {"clave": firma["clave"]}, reintentar={409: REINTENTOS_CONFIRMACION})
    ident = (r.get("archivo") or {}).get("id")
    if ident is None:
        raise TiendaError(f"La tienda confirmó {ruta.name} sin darme su id: {r}")
    return {"archivo_id": ident, "rol": a["rol"]}


def subir(carpeta, *, tienda: str, llave: str, borrador: bool = False, ensayo: bool = False,
          eco=print, cliente=None, espera_s: float = 2.0) -> dict:
    """`publicar subir`: revisa, sube cada archivo, importa y (salvo `borrador`) publica.
    `ensayo`: sólo la revisión y el plan. `cliente`: un `httpx.Client` (los tests). Devuelve
    {plan, subidos, maquina, url, publicada}."""
    eco = eco or (lambda *_a, **_k: None)
    carpeta = Path(carpeta)
    ficha, archivos = contenido(carpeta)
    t = Cliente(tienda, llave, cliente=cliente, eco=eco, espera_s=espera_s)
    try:
        plan = _plan(t, ficha, archivos, eco)
        if ensayo:
            eco("Ensayo: no subí nada. Sin --ensayo, se suben los archivos de arriba"
                + (" y queda en borrador." if borrador else " y se publica."))
            return {"plan": plan, "subidos": [], "maquina": None, "url": None, "publicada": False}
        por_nombre = {p.name: p for p in archivos}
        subidos = []
        for a in plan.get("archivos") or []:
            try:
                subidos.append(_subir_archivo(t, por_nombre[a["nombre"]], a, eco))
            except TiendaError as exc:
                raise TiendaError(f"{exc}\nNo importé la máquina: una a medias es peor que "
                                  "ninguna. Vuelve a correr `publicar subir`.",
                                  exc.status) from None
        r = t.api("POST", "/api/maquina/importacion", "importar la máquina",
                  {"ficha": ficha, "archivos": subidos}, reintentar={409: 1})
        # la tienda contesta maquina {id, creada, estado}, sin slug: el slug es el de la ficha
        maquina = r.get("maquina") or {}
        slug = maquina.get("slug") or ficha.get("slug")
        eco(f"Importada: {slug} (id {maquina.get('id')}, "
            + ("nueva)." if maquina.get("creada") else "actualizada)."))
        if r.get("faltan"):
            eco("  la tienda dice que falta: " + ", ".join(r["faltan"]))
        url = f"{tienda}/maquinas/{slug}"
        if not borrador:
            try:
                maquina = t.api("PUT", f"/api/maquina/{maquina.get('id')}/estado",
                                "publicar la máquina",
                                {"estado": "publicada"}).get("maquina") or maquina
            except TiendaError as exc:
                raise TiendaError(f"{exc}\nLa máquina quedó importada en borrador ({url}): "
                                  "complétala en la tienda o corrige la ficha y vuelve a subir.",
                                  exc.status) from None
    finally:
        t.cerrar()
    eco(("Quedó en borrador (no se publicó): " if borrador else "Publicada: ") + url)
    return {"plan": plan, "subidos": subidos, "maquina": maquina, "url": url,
            "publicada": not borrador}
