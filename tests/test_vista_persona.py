"""Vista persona del registro de comandos (plan texto-agente-vs-persona, F1).

Dos lectores, un registro: el agente lee `command_schemas()` tal cual (D1: ni un byte
cambia) y la UI pide `GET /api/schemas?vista=persona`, que arma sobre una COPIA la pista,
el detalle, la pestaña y el schema sin historia (D2, D6, D7, D8).
"""

from __future__ import annotations

import copy
import json
import re

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.commands import REGISTRY, command_schemas, command_schemas_persona
from apolo.commands import vista_persona as vp
from apolo.commands.pistas import PESTANAS
from apolo.doc import Document

# = HISTORIA de ui/src/textoDeAyuda.test.ts (en JS `\b` y `\w` son ASCII)
VERSION = re.compile(r"\bV\d+(?:\.\d+)?[a-z]?(?:-[A-Z])?(?![\w.])", re.ASCII)


@pytest.fixture
def client():
    api.DOC = Document("t")
    return TestClient(api.app)


def _por_tipo(entradas):
    return {e["type"]: e for e in entradas}


# ── la vista del agente no cambia ─────────────────────────────────────────────


def test_vista_agente_es_la_de_siempre(client):
    base = client.get("/api/schemas")
    assert base.status_code == 200
    explicita = client.get("/api/schemas", params={"vista": "agente"})
    assert explicita.content == base.content
    assert base.json() == json.loads(json.dumps(command_schemas(), ensure_ascii=False))
    # la entrada del agente conserva su description y la raíz del schema la repite
    dh = _por_tipo(base.json())["drill_hole"]
    assert "V6.8-E" in dh["description"]
    assert dh["schema"]["description"] == dh["description"]


def test_pedir_la_vista_persona_no_muta_la_del_agente(client):
    antes = json.dumps(command_schemas(), ensure_ascii=False)
    antes_http = client.get("/api/schemas").content
    command_schemas_persona()
    client.get("/api/schemas", params={"vista": "persona"})
    assert json.dumps(command_schemas(), ensure_ascii=False) == antes
    assert client.get("/api/schemas").content == antes_http


def test_la_entrada_persona_trabaja_sobre_una_copia():
    for entrada in command_schemas():
        intacta = copy.deepcopy(entrada)
        vp._entrada_persona(entrada)
        assert entrada == intacta, entrada["type"]


def test_vista_desconocida_da_422(client):
    r = client.get("/api/schemas", params={"vista": "otra"})
    assert r.status_code == 422


def test_el_schema_de_un_comando_sigue_igual(client):
    r = client.get("/api/schemas/drill_hole")
    assert r.status_code == 200
    assert r.json() == json.loads(json.dumps(command_schemas("drill_hole")[0], ensure_ascii=False))


# ── la vista persona ──────────────────────────────────────────────────────────


def test_vista_persona_por_http(client):
    r = client.get("/api/schemas", params={"vista": "persona"})
    assert r.status_code == 200
    entradas = r.json()
    assert [e["type"] for e in entradas] == list(REGISTRY)
    for e in entradas:
        assert set(e) == {"type", "title", "category", "kind", "pestana", "pista", "detalle", "schema"}
        assert "description" not in e["schema"], e["type"]  # la raíz duplicada se va
        assert e["pista"], e["type"]


def test_sin_versiones_del_roadmap_en_ninguna_parte():
    payload = json.dumps(command_schemas_persona(), ensure_ascii=False)
    assert VERSION.findall(payload) == []
    # y el agente sí las tiene (si un día no, este test deja de probar algo)
    assert len(VERSION.findall(json.dumps(command_schemas(), ensure_ascii=False))) > 0


def test_rotulo_con_version_se_limpia():
    chapa = _por_tipo(command_schemas_persona())["create_sheet_metal"]
    assert chapa["schema"]["properties"]["flaps"]["title"] == "Pestañas ricas"


def test_detalle_solo_con_mas_de_una_frase():
    por_tipo = _por_tipo(command_schemas_persona())
    assert por_tipo["create_box"]["detalle"] == ""  # «Caja rectangular centrada en el origen.»
    dh = por_tipo["drill_hole"]["detalle"]
    assert dh.startswith("Taladro: avanza")
    assert "Entrada DECLARATIVA: en vez de" in dh
    assert "\n" not in dh  # las líneas cortadas por el ancho del código se unen


def test_detalle_conserva_parrafos_y_vinetas():
    tensor = _por_tipo(command_schemas_persona())["create_take_up"]["detalle"]
    assert "\n\nPARA QUÉ SIRVE:" in tensor
    lineas = tensor.splitlines()
    assert sum(ln.startswith("- ") for ln in lineas) == 5
    # la frase que sigue a la última viñeta (misma sangría que el guion) no es parte de ella
    assert lineas[-1] == "Editar cualquier parámetro regenera el conjunto entero."


def test_pista_cae_a_la_primera_frase_limpia(monkeypatch):
    monkeypatch.setattr(vp, "PISTAS", {})
    por_tipo = _por_tipo(command_schemas_persona())
    assert por_tipo["create_box"]["pista"] == "Caja rectangular centrada en el origen."
    assert por_tipo["insert_project"]["pista"] == (
        "Instancia un PROYECTO guardado COMPLETO como sub-ensamblaje (layouts multi-máquina)."
    )


def test_pista_explicita_gana(monkeypatch):
    monkeypatch.setattr(vp, "PISTAS", {"create_box": "Crea una caja."})
    assert _por_tipo(command_schemas_persona())["create_box"]["pista"] == "Crea una caja."


def test_x_unidad_en_los_campos():
    dh = _por_tipo(command_schemas_persona())["drill_hole"]["schema"]
    props = dh["properties"]
    assert props["diameter"]["x-unidad"] == "mm"
    assert props["depth"]["x-unidad"] == "mm"
    assert props["depth"]["description"] == "mm, 0 = pasante"  # la ⓘ conserva el texto
    assert "x-unidad" not in props["thread"]
    assert dh["$defs"]["SlideUV"]["properties"]["u"]["x-unidad"] == "mm"
    junta = _por_tipo(command_schemas_persona())["add_joint"]["schema"]["properties"]
    assert junta["lower"]["x-unidad"] == "grados o mm"


def test_x_pista_en_el_modelo_raiz_y_en_un_sub_modelo(monkeypatch):
    monkeypatch.setattr(
        vp, "PISTAS_CAMPO", {"DrillHoleParams.cara": "Raíz.", "SlideUV.u": "Sub-modelo."}
    )
    dh = _por_tipo(command_schemas_persona())["drill_hole"]["schema"]
    assert dh["properties"]["cara"]["x-pista"] == "Raíz."
    assert dh["$defs"]["SlideUV"]["properties"]["u"]["x-pista"] == "Sub-modelo."
    caja = _por_tipo(command_schemas_persona())["create_box"]["schema"]
    assert "x-pista" not in json.dumps(caja)


def test_pestana_de_cada_comando():
    categorias = {spec.category for spec in REGISTRY.values()}
    assert categorias <= set(PESTANAS), categorias - set(PESTANAS)
    for e in command_schemas_persona():
        assert e["pestana"] == PESTANAS[e["category"]], e["type"]
    por_tipo = _por_tipo(command_schemas_persona())
    assert por_tipo["thicken"]["pestana"] == {"orden": 3, "rotulo": "Superficies"}
    assert por_tipo["set_variable"]["pestana"] is None
    ordenes = [p["orden"] for p in PESTANAS.values() if p]
    assert len(ordenes) == len(set(ordenes))


# ── las piezas sueltas ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "crudo, limpio",
    [
        ("Pestañas ricas (V5.5)", "Pestañas ricas"),
        ("como sub-ensamblaje (layouts multi-máquina, V5.2b). Da", "como sub-ensamblaje (layouts multi-máquina). Da"),
        ("en UN comando (super-comando, V6.5b): taladra", "en UN comando (super-comando): taladra"),
        ("CARAS de un sólido (modelado directo, V5.3): quitar", "CARAS de un sólido (modelado directo): quitar"),
        ("Entrada DECLARATIVA (V6.8-E): en vez de `position`", "Entrada DECLARATIVA: en vez de `position`"),
        ("CARA-A-CARA (V6.8-E, pasa `cara` + `cara_target`)", "CARA-A-CARA (pasa `cara` + `cara_target`)"),
        ('"inglete" (V5.8) = marcos', '"inglete" = marcos'),
        ("con `flaps` (V5.5) los perfiles C/Z", "con `flaps` los perfiles C/Z"),
        ("en el PLANO de una cara (V6.8-E): u = eje", "en el PLANO de una cara: u = eje"),
        ("Tablas de diseño (V6.4c)", "Tablas de diseño"),
        ("nuevo desde V7.2 en adelante", "nuevo desde en adelante"),
        ("Motor 220V trifásico", "Motor 220V trifásico"),
        ("Vista 3D del conjunto", "Vista 3D del conjunto"),
        ("rosca M10x1.25 y V[\"largo\"]", "rosca M10x1.25 y V[\"largo\"]"),
    ],
)
def test_limpiar_historia(crudo, limpio):
    assert vp.limpiar_historia(crudo) == limpio


def test_limpiar_historia_normaliza_espacios():
    limpiar = vp.limpiar_historia
    doc = """Primera línea
        cortada por el ancho.

        PÁRRAFO NUEVO:
        - viñeta uno que sigue
          en la línea de abajo.
        - viñeta dos.
        Frase fuera de la viñeta."""
    assert limpiar(doc) == (
        "Primera línea cortada por el ancho.\n\n"
        "PÁRRAFO NUEVO:\n- viñeta uno que sigue en la línea de abajo.\n- viñeta dos.\n"
        "Frase fuera de la viñeta."
    )
    assert limpiar("  mm,   0 = pasante  ") == "mm, 0 = pasante"


@pytest.mark.parametrize(
    "descripcion, unidad",
    [
        ("mm", "mm"),
        ("mm, 0 = pasante", "mm"),
        ("mm entre ejes", "mm"),
        ("grados", "grados"),
        ("grados respecto a la padre", "grados"),
        ("grados o mm", "grados o mm"),
        ("mm; acepta =expresión", "mm"),
        ("[x,y,z] mm", None),
        ("altura del perfil en el plano XY (mm)", None),
        ("mmm", None),
        ("gradosx", None),
        ("", None),
        (None, None),
    ],
)
def test_unidad_de(descripcion, unidad):
    assert vp.unidad_de(descripcion) == unidad


def test_frases_y_primera_frase_como_el_gate_de_la_ui():
    # mismos casos que «cuenta frases como las cuenta una persona» de textoDeAyuda.test.ts
    assert vp.frases("Uno por línea, sin https://.") == 1
    assert vp.frases("Cuántos turnos máx. por corrida tolera el agente.") == 1
    assert vp.frases("Default 48. Se borra si nadie lo usa.") == 2
    assert vp.frases("Porcentaje de la base. 100 = la de siempre.") == 2
    assert vp.frases("¿Seguro? Sí.") == 2
    assert vp.frases("") == 0
    assert vp.primera_frase("Uno.\n  Dos. Tres.") == "Uno."
    assert vp.primera_frase("Sin punto final") == "Sin punto final"
    # «depth=0» no abre oración: el corte por primera frase no basta (D4)
    assert vp.primera_frase("en la dirección del eje. depth=0 lo hace pasante. Caladrillo") == (
        "en la dirección del eje. depth=0 lo hace pasante."
    )
