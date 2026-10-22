"""La máquina andando CON PRODUCTO en el video de la fábrica (plan fabrica-de-publicaciones,
ajuste D10: «una faja moviéndose sin cajas no parece que se mueva»).

`elegir(doc, carpeta)` decide la marcha del guion (`{"duracion_s", "escenario"}`, video-realista
D5) en este orden:

  1. `marcha.json` en la carpeta de la versión o, si no, en la del slug (vale para todas sus
     versiones): la escribe el modelador para lo que no es un transportador. Es el escenario de
     la dinámica tal cual (lo mismo que `publicar guion --marcha`) u
     `{"escenario": {…}, "duracion_s": 10}`; `false` (o `null`) = esta máquina va SIN marcha;
  2. si no hay archivo, la automática de un transportador (`services.marcha_ejemplo`): cajas de
     los requisitos (o de ejemplo) que entran por la cola y viajan hasta la descarga.

Antes de ponerla en el guion la SIMULA en proceso sobre la copia del documento (la misma
dinámica que el navegador pedirá a la API al grabar): si falla, o si en la automática ninguna
caja avanza, el video sale sin marcha y lo avisa. Lo único que SÍ frena la fábrica (ajuste D13c):
que la faja que dibujará el visor no sea fiel al modelo (atraviesa una pieza o se aparta del
sólido de la banda): `PublicacionError` con la pieza y cuánto, nunca un «sin marcha» callado.
`verificar` hace la misma prueba con la marcha que ya trae un guion.

La simulación dura la parte de la marcha más lo que la máquina sigue andando en el video
después (`extra_s`: la tarjeta de cifras y la órbita final, `plan_navegador`), con el tope de
la dinámica (60 s); un escenario escrito a mano con su propia `duracion_s` la conserva.
"""

from __future__ import annotations

import json
from pathlib import Path

from apolo.publicacion.paquete import PublicacionError

MARCHA_JSON = "marcha.json"
#: Segundos de la marcha de un `marcha.json` que no los dice (los de `publicar guion --marcha`).
MARCHA_S = 8.0
#: Lo que el video sigue en 3D tras la marcha, cuando todavía no hay guion (cifras + órbita).
EXTRA_S = 14.0
DURACION_MAX_S = 60.0


def _eco_nulo(*_a, **_k):
    return None


def buscar(carpeta) -> Path | None:
    """El `marcha.json` que toca: el de la versión o el del slug."""
    carpeta = Path(carpeta)
    for ruta in (carpeta / MARCHA_JSON, carpeta.parent / MARCHA_JSON):
        if ruta.is_file():
            return ruta
    return None


def leer(ruta: Path) -> dict | None:
    """{"duracion_s", "escenario"} del archivo, o None si dice `false`/`null` (sin marcha).
    `PublicacionError` si no se lee o no tiene la forma."""
    try:
        # utf-8-sig: el `Set-Content -Encoding utf8` de PowerShell 5.1 escribe con BOM
        datos = json.loads(Path(ruta).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise PublicacionError(f"No pude leer {ruta}: {exc}") from None
    if datos is None or datos is False:
        return None
    if not isinstance(datos, dict):
        raise PublicacionError(f"{ruta} debe ser el escenario de la marcha (un objeto {{…}}), "
                               "{\"escenario\": {…}, \"duracion_s\": 10} o false.")
    if "escenario" in datos:
        sobra = set(datos) - {"escenario", "duracion_s"}
        dur = datos.get("duracion_s", MARCHA_S)
        if sobra or not isinstance(datos["escenario"], dict) or isinstance(dur, bool) \
                or not isinstance(dur, (int, float)) or dur <= 0:
            raise PublicacionError(f"{ruta}: con «escenario», el archivo es {{\"escenario\": "
                                   "{…}, \"duracion_s\": segundos > 0}"
                                   + (f"; sobra {', '.join(sorted(sobra))}" if sobra else ""))
        return {"duracion_s": float(dur), "escenario": datos["escenario"]}
    return {"duracion_s": MARCHA_S, "escenario": datos}


def extra_del_guion(g: dict) -> float:
    """Lo que el video sigue en 3D tras la marcha en ESTE guion (la marcha sigue andando)."""
    return sum(float((g.get(p) or {}).get("duracion_s") or 0.0) for p in ("cifras", "orbita"))


def elegir(doc, carpeta, *, extra_s: float = EXTRA_S, eco=print) -> dict | None:
    """La marcha probada para el guion, o None (avisado). Ver el docstring del módulo."""
    from apolo.services import marcha_ejemplo as me

    eco = eco or _eco_nulo
    ruta = buscar(carpeta)
    if ruta is not None:
        try:
            m = leer(ruta)
        except PublicacionError as exc:
            eco(f"Aviso: el video sale SIN la máquina andando: {exc}")
            return None
        if m is None:
            eco(f"{ruta} dice false: el video va sin la máquina andando.")
            return None
        esc = dict(m["escenario"])
        esc.setdefault("duracion_s", min(DURACION_MAX_S, m["duracion_s"] + extra_s))
        origen, minimo = f"la de {ruta}", None  # a mano: lo que se mueve lo decide el modelador
    else:
        try:
            auto = me.armar(doc, extra_s=extra_s)
        except me.SinMarcha as exc:
            eco(f"Aviso: el video sale SIN la máquina andando: {exc}. Para que ande, declara en "
                f"los requisitos el producto y la velocidad, o escribe {MARCHA_JSON} junto a "
                "ficha.yaml (el escenario de `simulate`).")
            return None
        m, esc = {"duracion_s": auto.duracion_s}, auto.escenario
        origen, minimo = f"automática ({auto.resumen})", 200.0
        if auto.asumido:
            eco("La marcha asume (decláralo en los requisitos para fijarlo): "
                + ", ".join(auto.asumido))
    try:
        prueba = me.probar(doc, esc, minimo_mm=minimo)
    except me.SinMarcha as exc:
        eco(f"Aviso: el video sale SIN la máquina andando: {exc}")
        return None
    except me.MarchaInfiel as exc:
        raise _infiel(exc) from None
    eco(f"Marcha {origen}: simulada en {prueba['segundos']} s, {prueba['productos']} "
        f"producto(s), el que más avanzó recorrió {prueba['avance_mm']} mm.")
    _eco_fiel(prueba, eco)
    return {"duracion_s": float(m["duracion_s"]), "escenario": esc}


def _infiel(exc) -> PublicacionError:
    """D13c: la marcha que el video dibujaría NO es la del modelo. Para: no cae a «sin marcha»."""
    return PublicacionError(
        f"La máquina andando del video NO es fiel al modelo: {exc}.\nEl visor dibuja la banda "
        "desde la sección de su sólido (fabrica-de-publicaciones, ajuste D13): si la sección no "
        "es un lazo cerrado (tramos sueltos que no se tocan), únelos en un sólido; si el modelo "
        f"es el que está mal, corrígelo. Para publicar SIN la máquina andando, escribe false en "
        f"{MARCHA_JSON} junto a ficha.yaml.")


def _eco_fiel(prueba: dict, eco) -> None:
    for f in prueba.get("fidelidad") or []:
        de = "la sección del modelo" if f["origen"] == "seccion" else "el casco de sus tambores"
        eco(f"La banda {f['pieza']} en marcha sale de {de} y no atraviesa nada (D13).")


def verificar(doc, m: dict, *, eco=print) -> None:
    """La marcha que YA trae un guion, probada contra el modelo (D13c): `PublicacionError` si no
    es fiel. Si ni siquiera simula, sólo avisa (el navegador dirá lo suyo al grabar)."""
    from apolo.services import marcha_ejemplo as me

    eco = eco or _eco_nulo
    try:
        _eco_fiel(me.probar(doc, m.get("escenario") or {}, minimo_mm=None), eco)
    except me.SinMarcha as exc:
        eco(f"Aviso: la máquina andando del guion no simula aquí: {exc}")
    except me.MarchaInfiel as exc:
        raise _infiel(exc) from None
