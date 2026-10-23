"""El guion del video hecho plan cuadro por cuadro para el navegador (plan video-realista, D5).

El navegador reproduce el MISMO guion que el video de VTK (`video.py`): las mismas partes, los
mismos fotogramas de cada una (`linea_tiempo.tramos`), el mismo reparto de cada etapa entre sus
tandas por peso de roles (`construccion.peso_roles`), el mismo escalonado de las piezas que entran
(`construccion.revelado` + `linea_tiempo.apariciones`), los mismos fundidos y la misma órbita. Lo
calcula ESTE módulo, con las mismas funciones; el navegador sólo lo dibuja. Así no hay dos guiones
que diverjan: una regla nueva del video entra en `linea_tiempo.py` y la reciben los dos.

Sólo el modo MONTAJE (D8 de video-montaje-pulido): cada paso es una tanda de piezas de la escena
final, que el navegador ya tiene. El modo diseño regenera prefijos del log y eso sólo lo hace VTK.

Lo que el navegador agrega (D5): la `marcha` del guion, la máquina andando después de las etapas,
con la órbita lenta de la construcción; y sigue andando en la vuelta final.

Puro: lee `doc.scene` (nombres y visibilidad) y el guion; ni locks ni E/S.
"""

from __future__ import annotations

from apolo.services import linea_tiempo as lt

VERSION = 1
#: Las partes que se dibujan en 3D; las demás son tarjetas (imágenes fijas de la API).
PARTES_3D = ("etapa", "marcha", "orbita")


class PlanError(ValueError):
    """El guion no se puede grabar en el navegador; el texto va tal cual a la persona."""


def _r(x: float) -> float:
    return round(float(x), 4)


def _cruza(previo: str | None, parte: str) -> bool:
    """¿Entra con fundido cruzado? Entre etapas, y de la última etapa a la marcha, la escena 3D
    sigue sin corte (como en `video.py`)."""
    return previo is not None and not (previo == "etapa" and parte in ("etapa", "marcha"))


def plan(doc, g: dict, proyecto: int | None = None) -> dict:
    """El plan del guion `g` (ya validado contra `doc`) para el navegador; `proyecto` = el id del
    proyecto que el visor tiene que tener abierto. `PlanError` si el guion no es de montaje o
    dura 0 s."""
    from apolo.services.construccion import diferencia, peso_roles, revelado
    from apolo.services.guion_video import MODO_MONTAJE

    if g.get("modo") != MODO_MONTAJE:
        raise PlanError("El navegador graba el video de MONTAJE (cómo se arma); el de diseño "
                        "regenera el log y sólo lo hace el render VTK. Arma el guion con "
                        "«--modo montaje».")
    fps = g["video"]["fps"]
    tramos = lt.tramos(g)
    total = lt.total_fotogramas(tramos)
    if total == 0:
        raise PlanError("El guion dura 0 s: no hay video que hacer.")
    escena = doc.scene
    visibles = {fid for fid, f in escena.items() if getattr(f, "visible", True)}
    az: list[float | None] = [None] * total
    mezcla: list[float | None] = [None] * total
    rotulo = [0.0] * total
    apariciones: list[dict] = []
    montado: dict = {}
    mostrados: set[str] = set()
    inicio_etapas = next((t.inicio for t in tramos if t.parte == "etapa"), 0)
    az_actual = lt.AZIMUT_INICIAL
    marcha = None
    salida, previo = [], None
    for t in tramos:
        cruza = _cruza(previo, t.parte)
        if cruza:
            for f in range(t.inicio, t.fin):
                mezcla[f] = lt.entrada(f, t.inicio, fps)
        if t.parte == "etapa":
            for f, ids in _apariciones_etapa(g["etapas"][t.etapa], t, escena, montado, visibles,
                                             mostrados, diferencia, revelado, peso_roles):
                apariciones.append({"cuadro": f, "ids": ids})
            for f in range(t.inicio, t.fin):
                az_actual = az[f] = lt.azimut_construccion(f, inicio_etapas, fps)
                rotulo[f] = lt.opacidad_rotulo(f, t.inicio, t.fin, fps)
        elif t.parte == "marcha":
            marcha = {"inicio": t.inicio, "fin": t.fin, "duracion_s": g["marcha"]["duracion_s"],
                      "escenario": g["marcha"].get("escenario")}
            for f in range(t.inicio, t.fin):
                az_actual = az[f] = lt.azimut_construccion(f, inicio_etapas, fps)
        elif t.parte == "orbita":
            desde = az_actual
            for f in range(t.inicio, t.fin):
                az_actual = az[f] = lt.azimut_orbita(f, t.inicio, t.fin, desde)
        salida.append({"parte": t.parte, "inicio": t.inicio, "fin": t.fin, "etapa": t.etapa,
                       "cruza": cruza})
        previo = t.parte
    marcha_t: list[float | None] = [None] * total
    if marcha is not None:
        tres_d = {f for t in tramos if t.parte in ("marcha", "orbita") for f in range(t.inicio, t.fin)}
        for f in tres_d:
            if f >= marcha["inicio"]:
                marcha_t[f] = _r((f - marcha["inicio"]) / fps)
    return {
        "version": VERSION,
        "titulo": g["titulo"],
        "proyecto": proyecto,
        "video": dict(g["video"]),
        "cuadros": total,
        "tramos": salida,
        "etapas": [{"titulo": e["titulo"], "texto": e["texto"]} for e in g["etapas"]],
        "ids": [f for f in escena if f in visibles],
        "apariciones": apariciones,
        "marcha": marcha,
        "camara": {"elevacion": lt.ELEVACION, "azimut_inicial": lt.AZIMUT_INICIAL},
        "resalte_s": lt.RESALTE_S,
        "cuadro": {
            "az": [None if a is None else _r(a) for a in az],
            "luz": [_r(lt.luz(f, total, fps)) for f in range(total)],
            "mezcla": [None if m is None else _r(m) for m in mezcla],
            "rotulo": [_r(o) for o in rotulo],
            "marcha_t": marcha_t,
        },
    }


def _apariciones_etapa(etapa: dict, t, escena: dict, montado: dict, visibles: set,
                       mostrados: set, diferencia, revelado, peso_roles):
    """(cuadro, ids nuevos) de una etapa: las tandas se suman a lo montado y sus piezas entran
    escalonadas por rol, con el reparto y las apariciones de `video._etapa`. Actualiza
    `montado` y `mostrados` en sitio (la etapa siguiente sigue desde ahí)."""
    pasos = []
    for tanda in etapa["pasos"]:
        previa = dict(montado)
        montado.update({f: escena[f] for f in tanda if f in escena})
        agregados, _quitados, _reemplazados = diferencia(previa, montado)
        roles, listas = revelado(montado, agregados)
        pasos.append((list(montado), listas, peso_roles(roles)))
    for (ids_montados, listas, _peso), (a, b) in zip(
            pasos, lt.reparto(t.inicio, t.fin, [p[2] for p in pasos])):
        if b <= a:
            continue
        vistas = {a: 0}
        vistas.update({fa: i + 1 for i, fa in enumerate(lt.apariciones(a, b, len(listas)))})
        for f in sorted(vistas):
            fuera = {fid for lista in listas[vistas[f]:] for fid in lista}
            nuevos = [fid for fid in ids_montados
                      if fid in visibles and fid not in fuera and fid not in mostrados]
            if nuevos:
                mostrados.update(nuevos)
                yield f, nuevos
