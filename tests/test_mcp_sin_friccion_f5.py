"""mcp-sin-friccion F5 (plan `docs/plans/mcp-sin-friccion.md`): D7–D12, las fricciones que halló
la verificación por MCP de F4, cada una sobre la plantilla `create_roller_conveyor` de 3 m
generada aquí (330 sólidos, 429 uniones declaradas por la propia plantilla).

- D7: la propuesta no repite lo declarado (sobre la plantilla recién generada, nada); los tramos
  numerados de la bandeja y la tapa contra la estructura van con perno.
- D8: `declare_structure(aplicar=true)` escribe un `fasten` por conjunto, dimensionado.
- D9: `get_connections` resume por par de piezas, no por el nombre de la unión.
- D10: `check_interference(ids=…)` pagina, deja fuera lo declarado a pedido y no sugiere lo pedido.
- D11: el 400 de `remove_commands` no cuenta lo que el propio comando crea.
- D12: `create_project` da su id; el schema de un comando no repite su descripción;
  `engineering_check()` agrupa las reglas de la plantilla (≤ 5 KB).
"""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
import apolo.library.checks as checks
from apolo.assembly.autodetect import detect_structure
from apolo.assembly.groups import group_features
from apolo.doc import Document
from apolo.services.dimensionado import combinar, dimension
from apolo.services.estructura import (
    propuesta_estructura,
    unidas_por_lo_declarado,
    uniones_con_criterio,
)
from apolo.services.roles import rol_union


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


@pytest.fixture(scope="module")
def plantilla() -> Document:
    """La plantilla de 3 m, tal cual sale (la de la verificación F4). Las pruebas que mutan la
    devuelven como estaba (undo) o trabajan sobre una copia."""
    doc = Document("f5-plantilla-3m")
    doc.execute("create_roller_conveyor", {"largo": 3000})
    return doc


@pytest.fixture
def activa(plantilla) -> Document:
    api.DOC = plantilla
    return plantilla


def _id(doc, nombre: str) -> str:
    return next(fid for fid, f in doc.scene.items() if f.name.endswith(" · " + nombre))


def _ids(doc, prefijo: str) -> list[str]:
    return sorted(fid for fid, f in doc.scene.items()
                  if f.name.split(" · ")[-1].startswith(prefijo))


# ------------------------------------------------------- D7: la propuesta no repite lo declarado
def test_d7_sobre_la_plantilla_recien_generada_no_propone_nada(activa, mcp_tool):
    prop = propuesta_estructura(activa)
    assert prop["acciones"] == [] and prop["omitidas"] == []
    corta = json.loads(mcp_tool("declare_structure", {}))
    assert corta["n_fasteners"] == corta["n_grounds"] == corta["n_omitidas"] == 0  # F4: 182
    assert len(json.dumps(corta, ensure_ascii=False).encode()) < 600


def test_d7_tramos_numerados_y_tapa_contra_la_estructura_van_con_perno(plantilla):
    uniones = uniones_con_criterio(plantilla, detect_structure(plantilla.scene,
                                                               joints=plantilla.joints))
    tipo = {frozenset((u["a"], u["b"])): u["kind"] for u in uniones}
    tramos = [_id(plantilla, f"Bandeja de cadenas (tramo {k})") for k in (1, 2, 3)]
    assert tipo[frozenset(tramos[:2])] == tipo[frozenset(tramos[1:])] == "perno"
    tapa = _id(plantilla, "Tapa de la bandeja (alimentación)")
    larguero = _id(plantilla, "Larguero (+Y)")
    assert tipo[frozenset((tapa, larguero))] == "perno"
    # dos partes de la MISMA guarda siguen soldadas entre sí
    pared = _id(plantilla, "Guarda de la transmisión · pared exterior")
    extremo = next(f for f in _ids(plantilla, "extremo")
                   if "Guarda de la transmisión" in plantilla.scene[f].name)
    assert tipo[frozenset((pared, extremo))] == "soldadura"
    # y la propuesta sigue coincidiendo con las uniones que la plantilla declara (≥ 95 %)
    declarado = {frozenset((f["a"], f["b"])): f["kind"] for f in plantilla.fasteners.values()}
    detectados = {par: k for par, k in declarado.items() if par in tipo}
    aciertos = sum(1 for par, k in detectados.items() if tipo[par] == k)
    assert aciertos / len(detectados) >= 0.95, f"{aciertos}/{len(detectados)}"


@pytest.mark.parametrize("nombre, rol, cuerpo", [
    ("Bandeja de cadenas (tramo 1)", "guarda", "bandeja de cadenas (tramo 1)"),
    ("Tapa de la bandeja (alimentación)", "guarda", "tapa de la bandeja (alimentación)"),
    ("Guarda de la transmisión · tapa del extremo", "guarda", "guarda de la transmisión"),
    ("Guarda de la transmisión · extremo (+X)", "guarda", "guarda de la transmisión"),
    ("Tapa con rodamiento 6201 (+Y)", "rodamiento", "tapa con rodamiento 6201 (+y)"),
])
def test_d7_tapa_y_tramos_por_nombre(nombre, rol, cuerpo):
    assert rol_union(nombre) == (rol, cuerpo)


def test_d7_unidas_en_cadena_por_lo_declarado():
    unidas = unidas_por_lo_declarado([{"a": "x", "b": "y"}, {"a": "y", "b": "z"},
                                      {"a": "p", "b": "q"}])
    assert unidas("x", "z") and unidas("z", "x") and not unidas("x", "p")
    assert not unidas("x", "nueva") and not unidas("nueva", "otra")


# --------------------------------------------------- D8: lo aplicado es dimensionado y compacto
def test_d8_aplicar_escribe_un_fasten_por_conjunto_y_nada_sin_dimensionar(plantilla, mcp_tool):
    doc = Document.from_apolo_bytes(plantilla.to_apolo_bytes())
    doc.fasteners.clear()  # la plantilla sin sus uniones: la propuesta las declara todas
    api.DOC = doc
    propuestas = [a for a in propuesta_estructura(doc)["acciones"] if a["type"] == "fasten"]
    antes = len(doc.commands)
    out = json.loads(mcp_tool("declare_structure", {"aplicar": True}))
    nuevos = doc.commands[antes:]
    assert out["uniones_declaradas"] == len(propuestas) > 500
    assert out["ordenes"] == len(nuevos) < len(propuestas) / 3  # 609 uniones en 181 órdenes
    assert any("+" in c["params"]["a"] + c["params"]["b"] for c in nuevos)  # por conjuntos
    for c in nuevos:
        p = c["params"]
        if p["kind"] == "perno":
            assert p.get("size") and p.get("qty"), p
        elif p["kind"] == "soldadura":
            assert p.get("throat_mm") and p.get("length_mm"), p
    # cada unión propuesta quedó declarada con su tipo; el eje roscado, con su rosca
    por_par = {frozenset((f["a"], f["b"])): f for f in doc.fasteners.values()}
    assert all(por_par[frozenset((a["params"]["a"], a["params"]["b"]))]["kind"]
               == a["params"]["kind"] for a in propuestas)
    eje, larguero = _ids(doc, "Eje del rodillo")[0], _id(doc, "Larguero (-Y)")
    declarado = [f for f in doc.fasteners.values() if {f["a"], f["b"]} == {eje, larguero}
                 and "conjunto" in f and not f["command_id"].startswith("c1_")]
    assert declarado and (declarado[0]["size"], declarado[0]["qty"]) == ("M12", 1)
    # el log nuevo (fasten por conjuntos) regenera las mismas uniones
    otro = Document.from_apolo_bytes(doc.to_apolo_bytes())
    assert {(n, f["kind"], f.get("size"), f.get("length_mm")) for n, f in otro.fasteners.items()} \
        == {(n, f["kind"], f.get("size"), f.get("length_mm")) for n, f in doc.fasteners.items()}


def test_d8_dimension_por_defecto():
    doc = Document("dimension")
    doc.execute("create_box", {"name": "Larguero", "width": 1000, "depth": 40, "height": 40,
                               "position": {"z": 520}})
    doc.execute("create_box", {"name": "Pata", "width": 50, "depth": 40, "height": 500,
                               "position": {"z": 250}})
    doc.execute("create_cylinder", {"name": "Eje", "radius": 8.5, "height": 100, "axis": "y",
                                    "position": {"x": 300, "z": 520}})
    roles = {"c1": "estructura", "c2": "estructura", "c3": "eje", "g": "guarda"}
    assert dimension(doc, "c1", "c2", "soldadura", roles) == {"throat_mm": 3.0,
                                                             "length_mm": 180.0}
    assert dimension(doc, "c3", "c1", "perno", roles) == {"size": "M16", "qty": 1}  # Ø17
    assert dimension(doc, "c1", "c2", "perno", roles) == {"size": "M10", "qty": 2}
    assert dimension(doc, "c1", "c2", "contacto", roles) == {}
    assert combinar([{"size": "M12", "qty": 2}, {"size": "M8", "qty": 4}]) == {"size": "M8",
                                                                               "qty": 2}


# --------------------------------------------------------- D9: resumen por par de piezas
def test_d9_get_connections_agrupa_por_el_par_de_piezas(activa, mcp_tool):
    out = json.loads(mcp_tool("get_connections", {}))
    assert out["n_fijadores"] == len(activa.fasteners)
    filas = {(f["kind"], f["a"], f["b"]): f["n"] for f in out["resumen"]}
    # los ejes a los dos largueros (`c1_eje_larg_m[*]` y `…_p[*]`): una fila
    assert filas[("perno", "Eje del rodillo", "Larguero")] == 60
    assert sum(filas.values()) == len(activa.fasteners)
    for f in out["resumen"]:  # cada fila es UN par de patrones (F4: `auto_f_*` mezclaba 163)
        assert "patron" not in f and f["ejemplo"]["piezas"]


# ------------------------------------------------------- D10: interferencia acotada que cubre
def test_d10_check_interference_pagina_y_no_sugiere_lo_pedido(activa, mcp_tool, monkeypatch):
    """Medido con el tope real (400): 660 parejas, faltaban 260 y `como_acotar` sugería
    «Rodillos» otra vez (F4). Aquí, con páginas de 100 para que la prueba no tarde un minuto. Con
    el prefiltro exacto (F6 de puerta-de-publicacion) las que sólo comparten caja o se apoyan
    cara a cara ya no son candidatas: 482. Con el eje trabado de F6 de plantilla-rodillos-cadena
    (separadores y tapas con alojamiento junto al eje): 662."""
    monkeypatch.setattr(checks, "MAX_PAIRS", 100)
    uno = json.loads(mcp_tool("check_interference", {"ids": ["Rodillos"]}))
    assert uno["truncado"] and uno["parejas_candidatas"] == 662
    assert uno["desde_siguiente"] == 100 and uno["parejas_sin_revisar"] == 562
    texto = uno["como_acotar"]
    assert 'check_interference(ids=["Rodillos"], desde=100)' in texto
    assert "Grupos:" not in texto and "excluir_declaradas=true" in texto
    # la última página, directo en la librería (el endpoint suma ~8 s de reglas que no devuelve)
    ultima = checks.interference_report(
        activa.scene, exclude_pairs=checks.joint_pairs(activa) | checks.same_command_pairs(activa),
        exclude_ids=checks.hardware_ids(activa), desde=600,
        focus=set(group_features(activa.scene, activa.groups, "Transportador de rodillos/Rodillos")))
    assert not ultima["truncado"] and ultima["desde"] == 600
    assert ultima["parejas_analizadas"] == 62 and ultima["parejas_candidatas"] == 662
    sin = json.loads(mcp_tool("check_interference", {"ids": ["Rodillos"],
                                                     "excluir_declaradas": True}))
    assert 100 < sin["parejas_candidatas"] < 330  # las de tubo ↔ tapa, eje ↔ tapa… no cuentan
    assert "excluir_declaradas=true, desde=100" in sin["como_acotar"]


def test_d10_como_acotar_sugiere_los_subgrupos_de_lo_pedido():
    from types import SimpleNamespace

    from apolo.services.interferencias import como_acotar

    pieza = SimpleNamespace(command_id="c1_pata", group="M/Patas")
    doc = SimpleNamespace(scene={"c1_pata": pieza}, groups={
        "M": {"name": "M", "parent": None, "members": []},
        "M/Patas": {"name": "M/Patas", "parent": "M", "members": ["c1_pata"]}})
    rep = {"parejas_analizadas": 3, "parejas_candidatas": 9, "parejas_sin_revisar": 6,
           "desde_siguiente": 3}
    texto = como_acotar(doc, rep, ["M"])
    assert 'ids=["M"], desde=3' in texto and texto.endswith("Grupos: M/Patas (1 piezas).")
    assert "Grupos" not in como_acotar(doc, rep, ["Patas"])  # sin subgrupos: sólo paginar


# ------------------------------------------------------------ D11: dependientes de verdad
def test_d11_el_400_no_cuenta_lo_que_crea_la_plantilla(activa):
    caja = activa.execute("create_box", {"name": "Caja externa",
                                         "position": {"x": 0, "y": -900, "z": 300}})
    union = activa.execute("fasten", {"name": "externa", "a": caja, "b": "c1_larg_m"})
    try:
        r = TestClient(api.app).post("/api/commands/remove", params={"detail": "diff"},
                                     json={"ids": ["c1"]})
        assert r.status_code == 400
        texto = r.json()["detail"]
        assert f"externa ({union}, fasten)" in texto and "con_dependientes=true" in texto
        assert "c1_u_" not in texto and "no arrastra" not in texto  # F4: 106 internos
    finally:
        activa.undo()
        activa.undo()
    assert caja not in activa.scene


# ------------------------------------------------------- D12: respuestas que faltan o sobran
def test_d12_create_project_devuelve_su_id(tmp_path, mcp_tool):
    from apolo.projects import ProjectStore

    api.DOC = Document("f5-inicial")
    api.STORE = ProjectStore(tmp_path / "f5.db")
    api.PROJECT_ID = api.STORE.create(api.DOC)
    out = json.loads(mcp_tool("create_project", {"name": "Faja nueva"}))
    assert out["id"] == api.PROJECT_ID and out["id"] is not None and out["nombre"] == "Faja nueva"
    assert "total_solidos" in out


def test_d12_el_schema_de_un_comando_no_repite_su_descripcion(mcp_tool):
    texto = mcp_tool("get_command_schemas", {"command_type": "create_roller_conveyor"})
    out = json.loads(texto)
    assert "description" not in out["schema"] and out["description"]
    assert texto.count(json.dumps(out["description"], ensure_ascii=False)[:80]) == 1
    assert len(texto.encode()) < 7_500  # F4: 10,5 KB


def test_d12_engineering_check_agrupa_la_plantilla_en_menos_de_5_kb(activa, mcp_tool,
                                                                    monkeypatch):
    monkeypatch.setattr(checks, "MAX_PAIRS", 20)  # la interferencia no entra en esta salida
    texto = mcp_tool("engineering_check", {})
    out = json.loads(texto)
    assert len(texto.encode()) <= 5_000, len(texto.encode())  # F4: 14 KB
    lineas = {r["regla"]: r for r in out["estructura"]}
    assert lineas["unión apernada · Eje del rodillo ↔ Larguero"] == {
        "regla": "unión apernada · Eje del rodillo ↔ Larguero", "n": 60, "estado": "ok"}
    assert sum(out["conteo"]["estructura"].values()) > len(out["estructura"])
    # lo que no está ok conserva su detalle
    assert all(r.get("detalle") for r in out["estructura"] if r["estado"] != "ok")
