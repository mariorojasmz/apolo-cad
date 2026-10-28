"""El resguardo con interruptor abre por su junta (plan lo-que-se-mueve, F2: D3 y D4).

- D3: `services/resguardos.py` resuelve la junta de cada `add_device` resguardo (interruptor →
  lengüeta → junta móvil); el ítem `seguridad.resguardo_abre` falla sin ella (o con una `fija`) y
  sus extremos entran como poses de la puerta de entrega aunque no estén en `doc.motion`.
- D4: el mando del resguardo en el `inicio` del vivo trae `junta`, `abierto` y `cerrado`.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from apolo.doc import Document
from apolo.library.calidad.item import FALLA, OK
from apolo.library.calidad.resguardos import resguardo_abre
from apolo.library.delivery import ROJO, delivery_report
from apolo.services.assertions import delivery_poses
from apolo.services.delivery_inputs import delivery_inputs, exclusiones_declaradas
from apolo.services.resguardos import juntas_en_tabla, juntas_vivo, poses, resguardos


def _sin_grupos(ids):
    return ids


def _mover(doc, fid, delta):
    cmd = next(c for c in doc.commands if c["id"] == doc.scene[fid].command_id)
    pos = dict(cmd["params"].get("position") or {})
    doc.edit(cmd["id"], {"position": {k: float(pos.get(k, 0.0)) + delta[i]
                                      for i, k in enumerate("xyz")}}, merge=True)


def _resguardo(junta: str | None = "giratoria", dispositivo: bool = True) -> tuple:
    """El interruptor -B1 con su lengüeta dentro de la ranura (14 mm, como el par bueno de
    `test_enclavamiento_resguardo`), ligado a su dispositivo; la lengüeta cuelga de una junta de
    `junta` (None: de ninguna) con el eje 60 mm detrás de la boca."""
    doc = Document("resguardo")
    c = doc.execute("insert_component", {"component": "RESG-2NC", "name": "Interruptor de puerta -B1"})
    lg = doc.execute("insert_component", {"component": "RESG-LENGUETA", "name": "Lengüeta -B1",
                                          "rotation": {"x": 180}})
    boca = doc.scene[c].anchors["ranura"]["origin"]
    punta = doc.scene[lg].anchors["punta"]["origin"]
    _mover(doc, lg, [boca[0] - punta[0], boca[1] - punta[1], boca[2] - 14.0 - punta[2]])
    if dispositivo:
        doc.execute("add_device", {"ref": "RESG-2NC", "designacion": "-B1", "ubicacion": "+CAMPO",
                                   "pieza": c})
    if junta == "fija":
        doc.execute("add_joint", {"name": "j_puerta", "type": "fija", "parent": c, "child": lg})
    elif junta:
        doc.execute("add_joint", {"name": "j_puerta", "type": "giratoria", "parent": c, "child": lg,
                                  "origin": {"x": 0, "y": boca[1] + 60, "z": boca[2] + 20},
                                  "axis": {"x": 1}, "lower": 0, "upper": 90})
    return doc, c, lg


def _item(doc) -> dict:
    return resguardo_abre({"resguardos": resguardos(doc)})


# ── D3: la resolución y el ítem ──────────────────────────────────────────────────────────────


def test_sin_junta_falla_y_dice_que_hacer():
    doc, c, lg = _resguardo(None)
    (r,) = resguardos(doc)
    assert r == {"designacion": "-B1", "ref": "RESG-2NC", "interruptor": c, "lengueta": lg,
                 "junta": None, "motivo": "sin_junta"}
    it = _item(doc)
    assert it["estado"] == FALLA and it["piezas"] == [c, lg]
    assert "no cuelga de ninguna junta" in it["detalle"]
    assert "junta de revolución" in it["detalle"] and "prismática si es corredera" in it["detalle"]
    assert poses(doc) == []


def test_con_junta_fija_falla():
    doc, _c, _lg = _resguardo("fija")
    (r,) = resguardos(doc)
    assert r["junta"] is None and r["motivo"] == "fija"
    it = _item(doc)
    assert it["estado"] == FALLA and "sólo cuelga de juntas fijas" in it["detalle"]


def test_con_junta_de_revolucion_libre_pasa_y_sus_extremos_son_poses():
    doc, _c, lg = _resguardo()
    (r,) = resguardos(doc)
    assert (r["junta"], r["cerrado"], r["abierto"], r["tipo_junta"]) == ("j_puerta", 0.0, 90.0, "giratoria")
    it = _item(doc)
    assert it["estado"] == OK and "-B1 por j_puerta (0 → 90)" in it["detalle"]
    (p,) = poses(doc)  # el 0 es la pose de diseño: sólo el abierto
    assert p["joint_values"] == {"j_puerta": 90.0} and p["t"] == "abierto" and p["ids"] == [lg]
    # sin estudios declarados, la puerta de entrega igual posa el resguardo abierto
    assert not doc.motion
    pares, pernos = exclusiones_declaradas(doc)
    (pose,) = delivery_poses(doc, pares, pernos, expand=_sin_grupos)
    assert pose["estudio"].startswith("apertura del resguardo -B1") and pose["colisiones"] == []
    assert "ids" not in pose and pose["resguardo"] == "-B1"


def test_con_junta_que_choca_abierto_la_verificacion_en_pose_falla():
    from apolo.robotics.pose import posed_shapes

    doc, c, lg = _resguardo()
    bb = posed_shapes(doc, {"j_puerta": 90.0})[0][lg].bounding_box()
    centro = bb.center()
    tope = doc.execute("create_box", {"name": "Tope mal puesto", "width": 30, "depth": 30, "height": 30,
                                      "position": {"x": centro.X, "y": centro.Y, "z": centro.Z}})
    assert delivery_poses(Document("vacio"), expand=_sin_grupos) is None  # sin estudios ni resguardos
    kw = delivery_inputs(doc, expand=_sin_grupos)
    assert kw["interferencias"] == []  # cerrado no toca: el choque es sólo al abrir
    (pose,) = kw["poses"]
    assert {frozenset((x["a"], x["b"])) for x in pose["colisiones"]} == {frozenset((lg, tope))}
    rep = delivery_report(**kw)
    assert rep["veredicto"] == ROJO
    assert any(b["regla"] == "colisión en pose declarada" and "apertura del resguardo -B1" in b["detalle"]
               for b in rep["bloqueantes"])


def test_el_interruptor_en_la_hoja_tambien_vale_y_si_van_juntos_no():
    doc, c, lg = _resguardo(None)
    marco = doc.execute("create_box", {"name": "Marco", "width": 10, "depth": 10, "height": 10,
                                       "position": {"x": 200}})
    doc.execute("add_joint", {"name": "j_hoja", "type": "giratoria", "parent": marco, "child": c,
                              "axis": {"z": 1}, "lower": 0, "upper": 100})
    (r,) = resguardos(doc)
    assert r["junta"] == "j_hoja" and r["abierto"] == 100.0
    doc.execute("add_joint", {"name": "j_lengueta", "type": "fija", "parent": c, "child": lg})
    (r,) = resguardos(doc)  # la lengüeta sube por la cadena hasta j_hoja: la MISMA junta
    assert r["junta"] is None and r["motivo"] == "misma_junta"


def test_sin_lengueta_la_junta_del_interruptor_no_es_la_de_una_hoja():
    """Medido en el elevador: un RESG-2NC sobre la plataforma (un detector de cadena floja) se
    mueve con la junta del carro; sin lengüeta, esa junta no dice qué hoja abre: FALLA, nunca OK."""
    doc = Document("cadena-floja")
    carro = doc.execute("create_box", {"name": "Plataforma", "width": 200, "depth": 200, "height": 10})
    c = doc.execute("insert_component", {"component": "RESG-2NC", "name": "Cadena floja -B13",
                                         "position": {"z": 50}})
    doc.execute("add_device", {"ref": "RESG-2NC", "designacion": "-B13", "ubicacion": "+CAMPO",
                               "pieza": c})
    doc.execute("add_joint", {"name": "j_plataforma", "type": "prismatica", "parent": carro, "child": c,
                              "axis": {"z": 1}, "lower": 0, "upper": 1500})
    (r,) = resguardos(doc)
    assert r["junta"] is None and r["motivo"] == "sin_lengueta" and r["se_mueve_con"] == "j_plataforma"
    it = _item(doc)
    assert it["estado"] == FALLA and "un detector de cadena floja" in it["detalle"]
    assert poses(doc) == [] and juntas_vivo(doc) == {}  # el visor no mueve la plataforma al «abrir»


def test_sin_pieza_ligada_falla_y_sin_dispositivo_no_aplica():
    doc = Document("sin-pieza")
    doc.execute("add_device", {"ref": "RESG-2NC", "designacion": "-B1", "ubicacion": "+CAMPO"})
    (r,) = resguardos(doc)
    assert r["motivo"] == "sin_pieza" and _item(doc)["estado"] == FALLA
    doc, _c, _lg = _resguardo(None, dispositivo=False)  # un interruptor suelto no es un resguardo
    assert resguardos(doc) == []


# ── D4: el mando del vivo trae la junta ──────────────────────────────────────────────────────


def test_el_inicio_del_vivo_trae_la_junta_del_resguardo():
    from apolo.api.routers.cosim_vivo import _inicio

    doc, _c, _lg = _resguardo()
    juntas = juntas_vivo(doc)
    assert juntas == {"-B1": {"junta": "j_puerta", "abierto": 90.0, "cerrado": 0.0}}
    tabla = {"tipo": "tabla", "senales": [], "cuerpos": [], "productos": [], "juntas": [], "bandas": [],
             "pilotos": [], "dispositivos": [],
             "mandos": [{"designacion": "-B1", "tipo": "resguardo", "ref": "RESG-2NC",
                         "acciones": ["abrir", "cerrar"], "color": None, "senales": ["-B1.cerrado"]},
                        {"designacion": "-B2", "tipo": "resguardo", "ref": "RESG-2NC",
                         "acciones": ["abrir", "cerrar"], "color": None, "senales": ["-B2.cerrado"]}]}
    snap = SimpleNamespace(avisos=[], hipotesis=[], dinamica=SimpleNamespace(cuerpos=[]))
    prep = {"snap": snap, "vis": None, "proyecto": 1, "nombre": "marcha", "firma": "2:x", "juntas": juntas}
    ini = _inicio(prep, tabla, {"max_s": 60, "ritmo": 1.0}, None)
    b1, b2 = ini["mandos"]
    assert (b1["junta"], b1["abierto"], b1["cerrado"]) == ("j_puerta", 90.0, 0.0)
    assert "junta" not in b2  # sin junta, el mando como siempre
    assert juntas_en_tabla(tabla, {}) is tabla


@pytest.mark.parametrize("lower, upper, esperado", [(0, 90, (0.0, 90.0)), (-110, 0, (0.0, -110.0)),
                                                    (-180, 180, (0.0, 180.0)), (20, 90, (20.0, 90.0)),
                                                    (-120, 30, (0.0, -120.0))])
def test_cerrado_es_el_extremo_de_la_pose_de_diseno(lower, upper, esperado):
    from apolo.services.resguardos import extremos

    assert extremos({"lower": lower, "upper": upper}) == esperado
