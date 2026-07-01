"""El criterio de diseño (capa 1 instrucciones + capa 2 guía) es fuente única y
llega a todos los clientes: módulo puro, endpoint HTTP, instrucciones del MCP y
prompt del agente de chat."""

from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.design import DESIGN_RULES, design_brief, design_guidelines


def test_module_has_full_decalogue_with_verification():
    g = design_guidelines()
    # Las 10 reglas no negociables, cada una con detalle y CON QUÉ se verifica en Apolo.
    assert len(g["reglas"]) == len(DESIGN_RULES) == 10
    for regla in g["reglas"]:
        assert regla["titulo"] and regla["detalle"] and regla["verificar"]
    # cubre los ejes que el usuario pidió: sujeción, herraje desmontable, geometría conforme.
    claves = {r["clave"] for r in g["reglas"]}
    assert {"sujecion", "uniones", "geometria", "fabricabilidad"} <= claves
    assert g["cuando_preguntar"]["asume"] and g["cuando_preguntar"]["pregunta"]
    assert g["ejemplos"]  # ejemplos por dominio (guarda, mueble, estructura)


def test_brief_is_general_not_only_conveyors():
    brief = design_brief()
    low = brief.lower()
    # principio rector + alcance general + remite a la guía completa.
    assert "ingeniero" in low and "cliente" in low
    assert "mueble" in low and "estructura" in low  # no es solo para fajas
    assert "get_design_guidelines" in brief


def test_endpoint_serves_guidelines():
    client = TestClient(api.app)
    r = client.get("/api/design-guidelines")
    assert r.status_code == 200
    data = r.json()
    assert data == design_guidelines()  # el endpoint es cliente fino del módulo


def test_mcp_instructions_embed_the_criterion():
    # El servidor MCP inyecta el decálogo en sus instrucciones (capa 1, siempre presente).
    from apolo.mcp_server import mcp

    instr = mcp.instructions or ""
    assert design_brief() in instr
    assert "CAD paramétrico Genix Apolo" in instr  # conserva las instrucciones técnicas


def test_chat_prompt_embeds_the_criterion():
    from apolo.agent.prompts import SYSTEM_PROMPT

    assert design_brief() in SYSTEM_PROMPT
