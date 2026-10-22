"""Preguntas de taller del revisor (plan revision-de-taller, F1: D2 y D3).

- `design/revision.py` es la fuente única: la pasada ESTRUCTURAL (contrafactual + marco de
  taller) va antes que las preguntas por pieza, y cada pregunta dice cómo se contesta.
- El revisor es de SÓLO LECTURA: toda tool que se le permite está en el catálogo del chat
  marcada como lectura (`tools/catalogo.py`); `open_project` es la única excepción, declarada.
- `docs/revisor-de-taller.md` es el prompt generado: si el módulo cambia y el archivo no, rojo
  (se regenera con `python -B scripts/plantilla_revisor.py`).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from apolo.design import revision
from apolo.tools import catalogo

RAIZ = Path(__file__).resolve().parents[1]
PLANTILLA = RAIZ / "docs" / "revisor-de-taller.md"


def test_la_pasada_estructural_es_la_de_d3_y_va_primero():
    claves = [p["clave"] for p in revision.PASADA_ESTRUCTURAL]
    assert claves == ["contrafactual", "marco_taller"]
    texto = revision.prompt_revisor()
    assert texto.index("Contrafactual de función") < texto.index("**Función**")
    # el contrafactual pregunta por lo que pasaría SIN el miembro (la lección de la F0)
    assert "si lo quitas" in revision.PASADA_ESTRUCTURAL[0]["pregunta"]
    assert "ENTRE" in revision.PASADA_ESTRUCTURAL[1]["pregunta"]


def test_las_preguntas_por_pieza_cubren_d3():
    claves = {p["clave"] for p in revision.PREGUNTAS_POR_PIEZA}
    assert claves == {"funcion", "material", "perfil_mercado", "montaje", "tensado",
                      "herramienta", "guardas", "ficha"}


def test_cada_pregunta_esta_completa_y_las_claves_no_se_repiten():
    todas = revision.PASADA_ESTRUCTURAL + revision.PREGUNTAS_POR_PIEZA
    for p in todas:
        assert set(p) == {"clave", "titulo", "pregunta", "como"}, p
        assert all(isinstance(v, str) and v.strip() for v in p.values()), p
        assert "?" in p["pregunta"], p["clave"]
    claves = [p["clave"] for p in todas]
    assert len(claves) == len(set(claves))


def test_formato_de_hallazgo_y_severidades_de_d2():
    assert revision.CAMPOS_HALLAZGO == ("pieza", "pregunta", "evidencia", "severidad")
    assert list(revision.SEVERIDADES) == ["ALTA", "MEDIA", "BAJA"]
    datos = revision.preguntas_taller()
    assert datos["campos_hallazgo"] == list(revision.CAMPOS_HALLAZGO)
    texto = revision.prompt_revisor()
    for campo in revision.CAMPOS_HALLAZGO:
        assert f'"{campo}"' in texto
    assert "Evidencia obligatoria" in texto


def test_el_revisor_solo_recibe_tools_de_lectura():
    for tool in revision.TOOLS_LECTURA:
        assert tool in catalogo.CHAT, f"{tool} no es una tool del catálogo"
        assert not catalogo.CHAT[tool].muta, f"{tool} muta el documento: no va al revisor"
    # la única que cambia algo (el documento activo) está declarada aparte
    assert revision.TOOL_APERTURA == "open_project"
    assert revision.TOOL_APERTURA in catalogo.FUERA_DEL_CHAT
    # sin el razonamiento del modelador (D2)
    assert "get_agent_notes" not in revision.TOOLS_LECTURA


def test_las_tools_que_nombra_el_prompt_son_las_permitidas():
    """Las tools que aparecen en «Cómo» existen y son de lectura: el prompt no puede empujar
    al revisor hacia una tool que muta."""
    conocidas = set(catalogo.CHAT) | set(catalogo.FUERA_DEL_CHAT)
    permitidas = set(revision.TOOLS_LECTURA) | {revision.TOOL_APERTURA}
    texto = " ".join(p["como"] for p in revision.PASADA_ESTRUCTURAL + revision.PREGUNTAS_POR_PIEZA)
    nombradas = {w for w in re.findall(r"[a-z]+(?:_[a-z]+)+", texto) if w in conocidas}
    assert nombradas, "el «Cómo» debería nombrar tools"
    assert nombradas <= permitidas, nombradas - permitidas


def test_prompt_reemplaza_los_marcadores():
    texto = revision.prompt_revisor(proyecto="74", ficha="carga 15 kg")
    assert "Proyecto: 74." in texto and "Ficha del encargo: carga 15 kg." in texto
    assert "{proyecto}" not in texto and "{ficha}" not in texto
    assert "{proyecto}" in revision.prompt_revisor()


def test_la_plantilla_en_docs_esta_sincronizada():
    actual = PLANTILLA.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert actual == revision.plantilla_revisor(), (
        "docs/revisor-de-taller.md está desactualizada: python -B scripts/plantilla_revisor.py"
    )


def test_el_modulo_es_puro():
    arbol = ast.parse(Path(revision.__file__).read_text(encoding="utf-8"))
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.ImportFrom):
            assert not (nodo.module or "").startswith("apolo"), nodo.module
        elif isinstance(nodo, ast.Import):
            assert not any(a.name.startswith("apolo") for a in nodo.names)
