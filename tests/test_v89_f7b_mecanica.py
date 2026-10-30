"""V8.9 F7b: los defectos MECÁNICOS que encontró la verificación por MCP (F7 § 5).

Cada test es la reproducción de la bitácora (rojo antes del arreglo):
  3. `join_bolted` no podía sujetar los pies MS1 de `create_pneumatic_cylinder`: su patrón caía
     a 5,5 mm del agujero de fábrica (EN 1993-1-8 pide ≥ 10,8 con M8) → criterio 6;
  4. `gravity_test` dejaba caer las tuercas que `join_bolted` insertó y declaró (510,6 mm);
  5. el producto de la co-simulación sólo publicaba `x_mm` (un desvío lateral no se afirmaba);
  6. la co-simulación ponía UN casco convexo por pieza aunque la pieza fuera varios sólidos (un
     túnel en U de `run_script` tapaba su propia boca).
"""

from __future__ import annotations

import pytest

from apolo.commands.errors import CommandError
from apolo.doc.document import Document
from apolo.doc.errors import DocumentError


# ── 3. join_bolted atornilla los pies MS1 por sus agujeros ───────────────────────────────────


def _cilindro_sobre_placa() -> tuple[Document, str, str]:
    """La repro de la F7: Ø63 de 100 mm por pies a z 200 y una placa de 10 mm bajo los pies."""
    d = Document("pies")
    cid = d.execute("create_pneumatic_cylinder", {
        "ref": "CIL-ISO15552-63", "carrera": 100, "montaje": "pies", "eje": "+X", "puertos": "+Z",
        "position": {"x": 0, "y": 0, "z": 200}})
    bb = d.scene[f"{cid}_pie_delantero"].shape.bounding_box()
    placa = d.execute("create_box", {"name": "Placa de montaje", "width": 400, "depth": 500, "height": 10,
                                     "position": {"x": -110, "y": 0, "z": bb.min.Z - 5}})
    return d, cid, placa


def test_join_bolted_atornilla_el_pie_ms1_por_sus_agujeros():
    """Antes: «e = 5,53 mm del canto … pide ≥ 10,8» con M8 (6,1 < 7,92 con M6). Ahora va por los
    dos Ø9 del pie (AF = 50 entre sí, AG = 32 de la tapa: tabla LB de Flowtech TS3017), con la
    cabeza sobre el pie y la tuerca bajo la placa."""
    d, cid, placa = _cilindro_sobre_placa()
    pie = d.scene[f"{cid}_pie_delantero"]
    agujeros = sorted(v["origin"][:2] for k, v in pie.anchors.items() if "agujero" in k)
    jb = d.execute("join_bolted", {"a": f"{cid}_pie_delantero", "b": placa, "size": "M8"})
    assert d.commands[-1]["params"]["criterio"] == 7
    f = d.fasteners[f"jb_{jb}"]
    assert (f["size"], f["qty"]) == ("M8", 2)
    pernos = sorted(k for k in d.scene if k.startswith(f"{jb}_perno"))
    tuercas = sorted(k for k in d.scene if k.startswith(f"{jb}_tuerca"))
    assert len(pernos) == 2 and len(tuercas) == 2
    z_pie = pie.shape.bounding_box().min.Z
    for k, (x, y) in zip(pernos, agujeros, strict=True):
        c = d.scene[k].shape.bounding_box().center()
        assert (c.X, c.Y) == (pytest.approx(x, abs=0.05), pytest.approx(y, abs=0.05))
        assert d.scene[k].shape.bounding_box().max.Z > z_pie + 3  # la cabeza, sobre el ala del pie
    for k in tuercas:
        assert d.scene[k].shape.bounding_box().max.Z <= z_pie - 10 + 0.1  # bajo la placa


@pytest.mark.parametrize(("extra", "pide"), [({"size": "M10"}, "«M8»"), ({"size": "M8", "count": 3}, "count=2"),
                                             ({"size": "M8", "patron": [2, 2]}, "patron")])
def test_join_bolted_rechaza_lo_que_no_casa_con_los_agujeros(extra, pide):
    d, cid, placa = _cilindro_sobre_placa()
    with pytest.raises((CommandError, DocumentError), match=pide):
        d.execute("join_bolted", {"a": f"{cid}_pie_delantero", "b": placa, **extra})


def test_un_join_bolted_viejo_no_cambia():
    """El criterio 5 guardado no mira los agujeros previos (sigue fallando igual: un log viejo
    regenera con la misma geometría y sin `version`)."""
    d, cid, placa = _cilindro_sobre_placa()
    with pytest.raises((CommandError, DocumentError), match="EN 1993-1-8"):
        d.execute("join_bolted", {"a": f"{cid}_pie_delantero", "b": placa, "size": "M8", "criterio": 5})


# ── 4. gravity_test sostiene la tornillería de join_bolted ───────────────────────────────────


def test_gravity_test_no_deja_caer_las_tuercas_de_join_bolted():
    """La repro de la F7: Base a z 505, Placa encima, join_bolted M8 ×2, ground(Base) →
    `POST /api/assembly/stability {}` daba 4 piezas dinámicas y las dos tuercas caían 510,6 mm."""
    pytest.importorskip("mujoco")
    from fastapi.testclient import TestClient

    from apolo.api import main as api

    d = Document("gravedad")
    base = d.execute("create_box", {"name": "Base", "width": 400, "depth": 200, "height": 10,
                                    "position": {"x": 0, "y": 0, "z": 505}})
    placa = d.execute("create_box", {"name": "Placa", "width": 200, "depth": 100, "height": 8,
                                     "position": {"x": 0, "y": 0, "z": 514}})
    d.execute("join_bolted", {"a": placa, "b": base, "size": "M8", "count": 2})
    d.execute("ground", {"name": "piso", "feature": base})
    api.DOC = d
    r = TestClient(api.app).post("/api/assembly/stability", json={})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["n_dynamic"] == 0 and not res["fell"], res


# ── 5. el producto publica x, y, z ───────────────────────────────────────────────────────────


def test_el_producto_publica_su_posicion_en_los_tres_ejes():
    """Antes sólo `caja.x_mm`: «se desvió» no se podía afirmar por la y."""
    from types import SimpleNamespace

    from apolo.cosim.corrida import _mecanica

    integ = SimpleNamespace(arrastre=None, d=SimpleNamespace(xpos=[[1.5, -0.25, 0.9]]),
                            snap=SimpleNamespace(productos=[{"name": "p_caja"}], bandas=[]),
                            activo=[True], bid_prod=[0], retiro={})
    out = _mecanica(integ, [])
    assert out == {"caja.x_mm": 1500.0, "caja.y_mm": -250.0, "caja.z_mm": 900.0}
    # balance-de-producto, trabas de flujo: la retirada se queda donde salió; la que no nació, nada
    integ = SimpleNamespace(arrastre=None, d=SimpleNamespace(xpos=[[9.0, 9.0, 9.0], [9.0, 9.0, 9.0]]),
                            snap=SimpleNamespace(productos=[{"name": "p_caja_0"}, {"name": "p_caja_1"}],
                                                 bandas=[]),
                            activo=[False, False], bid_prod=[0, 1],
                            retiro={0: {"t": 6.2, "pos": [1400.3, -1.2, 850.4]}})
    out = _mecanica(integ, [])
    assert out == {"caja_0.x_mm": 1400.3, "caja_0.y_mm": -1.2, "caja_0.z_mm": 850.4}


# ── 11. open_project no vuelca la escena ─────────────────────────────────────────────────────


def test_open_project_no_lista_doscientos_solidos():
    """La F7: abrir la faja del desviador (208 sólidos) devolvía 63 kB (la regla de lectura es
    < 10 KB); la corrección 1 no lo pudo leer. El resumen por grupo ya va en el briefing."""
    import json

    from apolo.brief import MAX_SOLIDOS, brief_apertura

    feats = [{"id": f"c{k}", "name": f"Pieza larga de la faja número {k}", "visible": True,
              "bbox": [[0, 0, 0], [100, 200, 300]], "volume_mm3": 1e6, "command_id": f"c{k}",
              "component": None, "group": "Faja", "is_guide": False} for k in range(208)]
    briefing = {"resumen": {"grupos": [{"nombre": "Faja", "n_piezas": 208}], "variables": {"L": 4000}}}
    payload = {"document": {"name": "faja", "variables": {"L": 4000}}, "features": feats,
               "total_features": 208, "briefing": briefing}
    out = brief_apertura(payload)
    assert "solidos" not in out and out["solidos_omitidos"] == 208 and "get_scene" in out["seguir"]
    assert "variables" not in out and out["briefing"] == briefing
    assert len(json.dumps(out, ensure_ascii=False).encode()) < 2_000
    chico = brief_apertura({**payload, "features": feats[:MAX_SOLIDOS], "total_features": MAX_SOLIDOS})
    assert len(chico["solidos"]) == MAX_SOLIDOS  # un proyecto chico sigue listando sus piezas


# ── 6. un casco convexo por sólido ───────────────────────────────────────────────────────────


def test_una_pieza_de_varios_solidos_tiene_un_casco_por_solido():
    """La repro de la F7 (corrección 2): un túnel de dos paredes en UNA pieza. Con un casco por
    pieza, la caja que cae entre las paredes quedaba arriba, sobre el casco que las une; con uno
    por sólido, cae entre ellas hasta el piso."""
    pytest.importorskip("mujoco")
    from apolo.physics.dinamica import prepare_dynamics, simulate_dynamics
    from apolo.physics.hull import cascos

    d = Document("tunel")
    piso = d.execute("create_box", {"name": "Piso", "width": 800, "depth": 800, "height": 20,
                                    "position": {"x": 0, "y": 0, "z": -10}})
    p1 = d.execute("create_box", {"name": "Pared A", "width": 600, "depth": 20, "height": 300,
                                  "position": {"x": 0, "y": -160, "z": 150}})
    p2 = d.execute("create_box", {"name": "Pared B", "width": 600, "depth": 20, "height": 300,
                                  "position": {"x": 0, "y": 160, "z": 150}})
    union = d.execute("boolean_op", {"operation": "union", "target": p1, "tools": [p2]})
    fid = next(k for k, f in d.scene.items() if f.command_id == union)
    d.execute("ground", {"name": "g_piso", "feature": piso})
    d.execute("ground", {"name": "g_tunel", "feature": fid})
    assert len(list(d.scene[fid].shape.solids())) == 2 and len(cascos(d.scene[fid].shape)) == 2
    req = {"duracion_s": 0.8, "fps": 10, "productos": [
        {"nombre": "caja", "dims_mm": [150, 150, 100], "masa_kg": 2.0, "posicion_mm": [0, 0, 400]}]}
    snap = prepare_dynamics(d.scene, d.joints, d.fasteners, d.grounds, req, mates=d.mates)
    caja = simulate_dynamics(snap)["resumen"]["productos"]["p_caja"]
    assert caja["posicion_final_mm"][2] < 100, caja
