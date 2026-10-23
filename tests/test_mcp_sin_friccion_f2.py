"""mcp-sin-friccion F2 (plan `docs/plans/mcp-sin-friccion.md`): D4 y D5.

- D4: los errores y los recortes dicen cómo seguir: el 400 de `remove_commands` lista los
  dependientes y sugiere `con_dependientes=true`; la interferencia global truncada dice cuántas
  parejas faltan y cómo acotar (también la puerta de entrega); un `fasten` por conjuntos cuenta
  sus uniones en la respuesta de la mutación; `delivery_check` informa sus tiempos.
- D5: los nombres de subgrupo resuelven por su último tramo («Cadenas» →
  «Entrada/Cadenas») en todas las tools que aceptan grupos; `show_axes` no cambia el encuadre.
"""

from __future__ import annotations

import asyncio
import io
import json

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
import apolo.library.checks as checks
from apolo.doc import Document


def _caja(doc, nombre, x=0.0, lado=50):
    return doc.execute("create_box", {"name": nombre, "width": lado, "depth": lado,
                                      "height": lado, "position": {"x": x, "y": 0, "z": 0}})


class _SinLifespan:
    def __init__(self, cliente):
        self._cliente = cliente

    def __enter__(self):
        return self._cliente

    def __exit__(self, *exc):
        return False


@pytest.fixture
def mcp_tool():
    """`mcp_tool(nombre, args)` → el texto de la tool real contra la API en proceso."""
    pytest.importorskip("mcp")
    import apolo.mcp_server as mod
    from apolo.tools.destino import Destino, apuntar

    cliente = TestClient(api.app)

    def llamar(nombre: str, args: dict) -> str:
        with apuntar(Destino("http://testserver", lambda: _SinLifespan(cliente))):
            out = asyncio.run(mod.mcp.call_tool(nombre, args))
        bloques = out[0] if isinstance(out, tuple) else out
        return bloques[0].text

    return llamar


# ------------------------------------------------------------- D4: remove_commands dice cómo
def _maquina() -> tuple[Document, dict]:
    """A, B y C; A↔B atornilladas, A anclada, A y B en «Bastidor», una junta A↔C."""
    doc = Document("f2-cirugia")
    ids = {"A": _caja(doc, "A"), "B": _caja(doc, "B", 50), "C": _caja(doc, "C", 200)}
    ids["f"] = doc.execute("fasten", {"name": "f_ab", "a": ids["A"], "b": ids["B"]})
    ids["g"] = doc.execute("ground", {"name": "g_a", "feature": ids["A"]})
    ids["G"] = doc.execute("create_group", {"name": "Bastidor", "members": [ids["A"], ids["B"]]})
    ids["j"] = doc.execute("add_joint", {"name": "bisagra", "parent": ids["A"], "child": ids["C"]})
    api.DOC = doc
    return doc, ids


def _borrar(ids, **extra):
    return TestClient(api.app).post("/api/commands/remove", params={"detail": "diff"},
                                    json={"ids": ids, **extra})


def test_el_400_del_borrado_sugiere_con_dependientes_y_los_lista():
    doc, ids = _maquina()
    antes = json.dumps(doc.commands)
    r = _borrar([ids["A"]])
    assert r.status_code == 400
    texto = r.json()["detail"]
    # el error del documento sigue al frente (aquí, la junta: es la que se regenera primero)
    assert texto.startswith("Error al regenerar") and "No existe el sólido" in texto
    assert "con_dependientes=true" in texto
    assert f"f_ab ({ids['f']}, fasten)" in texto and f"g_a ({ids['g']}, ground)" in texto
    assert "Bastidor" in texto  # los grupos que editaría
    assert f"bisagra ({ids['j']}, add_joint)" in texto and "con_dependientes no arrastra" in texto
    assert json.dumps(doc.commands) == antes  # nada se borró


def test_un_patron_que_copia_lo_borrado_se_nombra_aunque_no_se_arrastre():
    """Medido en la piloto 74: borrar la fuente de un patrón falla en el patrón, no en una
    unión; sugerir sólo con_dependientes habría sido engañoso."""
    doc = Document("f2-patron")
    eje = _caja(doc, "Eje")
    patron = doc.execute("pattern_linear", {"feature": eje, "count": 3,
                                            "spacing": {"x": 100, "y": 0, "z": 0}})
    api.DOC = doc
    texto = _borrar([eje]).json()["detail"]
    assert f"{patron} (pattern_linear)" in texto  # sin `name`: su id y su tipo
    assert "Repite el borrado" not in texto  # no hay fasten/ground que arrastrar


def test_con_dependientes_el_400_nombra_solo_lo_que_no_se_arrastra():
    _, ids = _maquina()
    texto = _borrar([ids["A"]], con_dependientes=True).json()["detail"]
    assert f"bisagra ({ids['j']}, add_joint)" in texto
    assert "Repite el borrado" not in texto  # los fasten/ground ya iban en el borrado


def test_los_dependientes_se_recortan_con_conteo():
    doc = Document("f2-muchos")
    a = _caja(doc, "A")
    for k in range(12):
        b = _caja(doc, f"B{k}", 60 * (k + 1))
        doc.execute("fasten", {"name": f"f{k}", "a": a, "b": b})
    api.DOC = doc
    texto = _borrar([a]).json()["detail"]
    assert "12 unión(es)" in texto and "… y 4 más" in texto
    assert texto.count(", fasten)") == 8


def test_un_id_inexistente_da_su_error_sin_sugerencias():
    _maquina()
    texto = _borrar(["c999"]).json()["detail"]
    assert texto == "No existe el comando 'c999'"


def test_la_tool_remove_commands_trae_la_sugerencia(mcp_tool):
    _, ids = _maquina()
    with pytest.raises(Exception, match="con_dependientes=true"):
        mcp_tool("remove_commands", {"ids": [ids["A"]]})


# ------------------------------------------------------- D4: interferencia truncada
def _amontonadas(monkeypatch) -> Document:
    """5 cajas en el mismo sitio (10 parejas candidatas), 2 en un grupo; tope de 3 parejas (la
    página y también el chequeo global de la puerta, que escala con los sólidos: F6)."""
    monkeypatch.setattr(checks, "MAX_PAIRS", 3)
    monkeypatch.setattr(checks, "PAREJAS_POR_SOLIDO", 0)
    doc = Document("f2-truncado")
    ids = [_caja(doc, f"P{k}", 5.0 * k) for k in range(5)]
    doc.execute("create_group", {"name": "Zona", "members": ids[:2]})
    api.DOC = doc
    return doc


def test_el_reporte_truncado_dice_cuantas_parejas_faltan(monkeypatch):
    doc = _amontonadas(monkeypatch)
    rep = checks.interference_report(doc.scene)
    assert rep["truncado"] and rep["parejas_analizadas"] == 3
    assert rep["parejas_candidatas"] == 10 and rep["parejas_sin_revisar"] == 7


def test_sin_truncar_el_reporte_no_cambia():
    doc = Document("f2-holgado")
    _caja(doc, "A")
    _caja(doc, "B", 500)
    assert set(checks.interference_report(doc.scene)) == {
        "solidos", "parejas_analizadas", "truncado", "interferencias"}


def test_check_interference_truncado_dice_como_acotar(monkeypatch, mcp_tool):
    _amontonadas(monkeypatch)
    out = json.loads(mcp_tool("check_interference", {}))
    assert out["parejas_sin_revisar"] == 7
    texto = out["como_acotar"]
    assert "faltan 7" in texto and "check_interference(ids=[grupo])" in texto
    assert "Zona (2 piezas)" in texto and "Sin grupo: 3 piezas" in texto


def test_con_un_solo_grupo_raiz_nombra_sus_subgrupos():
    """Una plantilla sola (raíz sin miembros propios, como la que registra
    `create_roller_conveyor`): acotar por su raíz sería el global otra vez."""
    from types import SimpleNamespace

    from apolo.services.interferencias import como_acotar

    pieza = SimpleNamespace(command_id="c1_pata", group="Maquina/Patas")
    doc = SimpleNamespace(scene={"c1_pata": pieza}, groups={
        "Maquina": {"name": "Maquina", "parent": None, "members": []},
        "Maquina/Patas": {"name": "Maquina/Patas", "parent": "Maquina", "members": ["c1_pata"]}})
    texto = como_acotar(doc, {"parejas_analizadas": 3, "parejas_candidatas": 9,
                              "parejas_sin_revisar": 6})
    assert texto.endswith("Grupos: Maquina/Patas (1 piezas).")


def test_la_puerta_dice_cuantas_quedaron_sin_revisar(monkeypatch):
    _amontonadas(monkeypatch)
    rep = TestClient(api.app).post("/api/delivery-check", json={}).json()
    aviso = next(a for a in rep["avisos"] if a["regla"] == "interferencias · reporte truncado")
    assert "7 parejas candidatas quedaron SIN revisar" in aviso["detalle"]
    assert "check_interference(ids=[grupo])" in aviso["detalle"]


# ------------------------------------------------------------- D4: tiempos de la puerta
def test_delivery_check_informa_su_tiempo_total_y_por_regla():
    doc = Document("f2-tiempos")
    _caja(doc, "A")
    api.DOC = doc
    t = TestClient(api.app).post("/api/delivery-check", json={}).json()["tiempos_s"]
    assert {"interferencias", "sujecion", "lints", "integridad", "poses", "electrico",
            "acceso_herramienta", "escenarios"} <= set(t["por_regla"])
    assert t["total"] >= max(t["por_regla"].values()) >= 0


# ------------------------------------------------------- D4: fasten por conjuntos en el lote
def _lote_con_conjuntos() -> list[dict]:
    """En un documento vacío: c1 larguero, c2 eje, c3 su patrón (×4), c4 el fasten por
    conjuntos (un `$k` no vale dentro de un conjunto: se escriben los ids) y c5 uno suelto."""
    caja = {"width": 10, "depth": 10, "height": 10}
    return [
        {"type": "create_box", "params": {"name": "Larguero", "width": 1000, "depth": 20,
                                          "height": 40, "position": {"x": 500, "y": -20}}},
        {"type": "create_box", "params": {"name": "Eje", **caja, "position": {"x": 50}}},
        {"type": "pattern_linear", "params": {"feature": "$2", "count": 4,
                                              "spacing": {"x": 100, "y": 0, "z": 0}}},
        {"type": "fasten", "params": {"name": "eje_larguero", "a": "c2+c3", "b": "c1",
                                      "kind": "perno"}},
        {"type": "fasten", "params": {"name": "suelta", "a": "$1", "b": "$2"}},
    ]


def test_el_lote_cuenta_las_uniones_de_cada_fasten_por_conjuntos():
    api.DOC = Document("f2-lote")
    out = TestClient(api.app).post("/api/commands/batch",
                                   json={"actions": _lote_con_conjuntos()}).json()
    assert out["uniones_expandidas"] == {"total": 4, "por_fasten": [
        {"comando": "c4", "nombre": "eje_larguero", "kind": "perno", "uniones": 4}]}


def test_sin_conjuntos_la_respuesta_no_lleva_la_clave():
    api.DOC = Document("f2-sin-conjuntos")
    out = TestClient(api.app).post("/api/commands/batch",
                                   json={"actions": _lote_con_conjuntos()[:2]}).json()
    assert "uniones_expandidas" not in out


def test_run_batch_corto_trae_las_uniones_expandidas(mcp_tool):
    api.DOC = Document("f2-lote-mcp")
    out = json.loads(mcp_tool("run_batch", {"actions": _lote_con_conjuntos()}))
    assert out["uniones_expandidas"]["total"] == 4 and "solidos" in out


# ---------------------------------------------- D5: subgrupos de una plantilla real
@pytest.fixture(scope="module")
def dos_transportadores():
    """«Entrada» (motriz: tiene Cadenas) y «Salida» (libre): «Cadenas» es de uno solo y
    «Rodillos» de los dos. La primera va por el lote de la API (cuenta sus uniones)."""
    doc = Document("f2-subgrupos")
    api.DOC = doc
    lote = TestClient(api.app).post("/api/commands/batch", json={"actions": [
        {"type": "create_roller_conveyor", "params": {"largo": 1000, "name": "Entrada"}}]})
    assert lote.status_code == 200, lote.text
    doc.execute("create_roller_conveyor", {"largo": 1000, "motriz": "libre", "name": "Salida",
                                           "position": {"x": 1500}})
    return doc, lote.json()


@pytest.fixture
def activo(dos_transportadores):
    doc, _ = dos_transportadores
    api.DOC = doc
    return doc


def test_la_plantilla_en_un_lote_cuenta_sus_uniones(dos_transportadores):
    doc, lote = dos_transportadores
    en_conjunto = [f for f in doc.fasteners.values()
                   if "conjunto" in f and f["command_id"].startswith("c1_")]
    assert lote["uniones_expandidas"]["total"] == len(en_conjunto) > 0


def test_get_scene_resuelve_el_subgrupo_por_su_ultimo_tramo(activo, mcp_tool):
    from apolo.assembly.groups import group_features

    out = json.loads(mcp_tool("get_scene", {"ids": ["Cadenas"]}))
    esperadas = set(group_features(activo.scene, activo.groups, "Entrada/Cadenas"))
    assert {s["id"] for s in out["solidos"]} == esperadas and esperadas


def test_render_isolate_y_las_demas_aceptan_el_subgrupo(activo, mcp_tool):
    client = TestClient(api.app)
    r = client.get("/api/render.png", params={"isolate": "Cadenas", "fit": "Cadenas",
                                              "vtk_only": True, "shade": True})
    assert r.status_code in (200, 503), r.text  # 503 = sin OpenGL; nunca el 400 de antes
    conexiones = json.loads(mcp_tool("get_connections", {"ids": ["Cadenas"], "resumen": False}))
    assert conexiones["fasteners"]
    verify = json.loads(mcp_tool("verify", {"checks": [
        {"tipo": "volumen", "ids": ["Cadenas"], "min": 1}]}))
    assert verify["ok"], verify


def test_un_subgrupo_de_varios_grupos_da_400_con_los_candidatos(activo):
    client = TestClient(api.app)
    r = client.get("/api/render.png", params={"isolate": "Rodillos"})
    assert r.status_code == 400
    assert r.json()["detail"] == ("'Rodillos' es subgrupo de varios grupos: Entrada/Rodillos, "
                                  "Salida/Rodillos; pasa el nombre completo")
    r = client.get("/api/connectivity", params={"ids": "Rodillos", "resumen": "no"})
    assert r.status_code == 400 and "Salida/Rodillos" in r.json()["detail"]
    assert client.get("/api/scene", params={"ids": "Salida/Rodillos"}).json()["solidos"]


def test_isolate_sin_nada_dice_que_pasar():
    doc = Document("f2-isolate")
    _caja(doc, "Larguero")
    doc.execute("create_group", {"name": "Bastidor", "members": ["c1"]})
    api.DOC = doc
    r = TestClient(api.app).get("/api/render.png", params={"isolate": "Bastidr"})
    assert r.status_code == 400
    assert "(Bastidr)" in r.json()["detail"] and "¿Quisiste decir: Bastidor" in r.json()["detail"]


def test_resolve_group_puro():
    from apolo.assembly.groups import GroupError, resolve_group

    grupos = {n: {} for n in ("A", "A/Rodillos", "B/Rodillos", "A/Cadenas", "Cadenas2")}
    assert resolve_group(grupos, "A") == "A"
    assert resolve_group(grupos, "Cadenas") == "A/Cadenas"
    assert resolve_group(grupos, "Patas") is None
    with pytest.raises(GroupError, match="A/Rodillos, B/Rodillos"):
        resolve_group(grupos, "Rodillos")


# ----------------------------------------------------- D5: show_axes no cambia el encuadre
def test_show_axes_va_en_la_esquina_sin_mover_el_encuadre():
    np = pytest.importorskip("numpy")
    pytest.importorskip("vtk")
    from PIL import Image

    from apolo.kernel.render_vtk import LADO_TRIEDRO, extract_render_scene, render_snapshot_vtk

    doc = Document("f2-ejes")  # lejos del origen: los ejes del origen quedaban fuera de cuadro
    doc.execute("create_box", {"name": "A", "width": 100, "depth": 100, "height": 100,
                               "position": {"x": 3000, "y": 2000, "z": 500}})
    imgs = []
    for ejes in (False, True):
        try:
            png = render_snapshot_vtk(extract_render_scene(doc.scene, "iso", show_axes=ejes))
        except Exception as exc:  # noqa: BLE001 — sin contexto OpenGL
            pytest.skip(f"VTK sin OpenGL: {exc}")
        imgs.append(np.asarray(Image.open(io.BytesIO(png)).convert("RGB")).astype(int))
    sin, con = imgs
    alto, ancho, _ = sin.shape
    distinto = np.abs(con - sin).sum(axis=2) > 10
    ys, xs = np.nonzero(distinto)
    assert len(xs), "el triedro no se dibujó"
    lado = int(LADO_TRIEDRO * ancho) + 2
    assert xs.max() <= lado and ys.min() >= alto - lado  # sólo cambia la esquina inf. izquierda
    rojo = (con[..., 0] > 150) & (con[..., 1] < 80) & (con[..., 2] < 80)
    assert rojo[alto - lado:, :lado].any()  # el eje X (rojo) está en la esquina
