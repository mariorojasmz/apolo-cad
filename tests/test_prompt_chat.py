"""Gate de la guía única (plan chat-cliente-igual, F6: D9 y D10).

El chat de la app y el MCP reciben el MISMO criterio de ingeniería (`design_brief()`) y la
MISMA guía técnica (`GUIA_TECNICA`); el chat suma sus reglas (`REGLAS_CHAT`) y el MCP su aviso
de conexión. El prompt del chat no nombra tools que el chat no tiene: valen las del catálogo
(`tools/catalogo.py::CHAT`) y `propose_commands`; de `FUERA_DEL_CHAT`, sólo las de archivo y
sólo si `REGLAS_CHAT` explica por qué no están. Tampoco nombra las tools del chat viejo, que
desaparecen con la F5b.

La lista completa de tools sale del catálogo, sin importar el MCP: que el catálogo cubra
exactamente las tools del MCP lo garantiza `test_catalogo_chat.py`.
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

from apolo.commands import REGISTRY
from apolo.design import design_brief
from apolo.design.instrucciones import (
    AVISO_CONEXION,
    GUIA_TECNICA,
    REGLAS_CHAT,
    instrucciones_mcp,
    system_prompt_chat,
)
from apolo.tools import catalogo

RAIZ = Path(__file__).resolve().parents[1]
PROPONER = "propose_commands"  # la única tool propia del chat (D7, agent/herramientas.py)
#: Las tools del chat viejo (`agent/agent.py`) que no existen en el MCP.
VIEJAS = ("get_document", "execute_commands", "undo_last", "save_note")
#: Motivos de `FUERA_DEL_CHAT` que el chat sí puede explicarle a la persona (descarga en la app).
MOTIVOS_DE_ARCHIVO = (catalogo._ARCHIVO, catalogo._GIF)
#: Prefijos de un identificador que nombra una operación (tool o comando), no un parámetro.
VERBOS = ("get_", "set_", "check_", "run_", "edit_", "test_", "find_", "list_", "open_",
          "save_", "restore_", "export_", "apply_", "declare_", "delete_", "auto_", "resolve_",
          "render_", "pick_", "scan_", "propose_", "execute_", "undo_", "create_", "insert_",
          "add_", "sketch_")


def _nombra(texto: str, nombre: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(nombre)}(?!\w)", texto) is not None


def test_brief_y_guia_llegan_a_los_dos_clientes():
    chat, mcp = system_prompt_chat(), instrucciones_mcp()
    for parte in (design_brief(), GUIA_TECNICA):
        assert parte in chat and parte in mcp
    assert REGLAS_CHAT in chat and REGLAS_CHAT not in mcp
    assert AVISO_CONEXION in mcp and AVISO_CONEXION not in chat  # el chat corre dentro de la API


def test_el_chat_usa_la_guia_unica():
    from apolo.agent.prompts import SYSTEM_PROMPT

    assert SYSTEM_PROMPT == system_prompt_chat()


def test_no_nombra_tools_que_el_chat_no_tiene():
    chat = system_prompt_chat()
    todas = set(catalogo.CHAT) | set(catalogo.FUERA_DEL_CHAT)
    fuera = sorted(t for t in todas if _nombra(chat, t) and t not in catalogo.CHAT)
    for t in fuera:
        assert catalogo.FUERA_DEL_CHAT[t] in MOTIVOS_DE_ARCHIVO, (
            f"el prompt del chat nombra «{t}», que el chat no tiene ({catalogo.FUERA_DEL_CHAT[t]})")
        assert _nombra(REGLAS_CHAT, t), f"«{t}» está fuera del chat y REGLAS_CHAT no lo explica"


def test_no_nombra_las_tools_del_chat_viejo():
    chat = system_prompt_chat()
    assert [v for v in VIEJAS if _nombra(chat, v)] == []


def test_cada_operacion_que_nombra_existe():
    """Un identificador con verbo (get_…, create_…) es una tool del chat o un comando: atrapa
    la tool inventada o con una letra de más antes de que el modelo la intente."""
    conocidas = set(catalogo.CHAT) | {PROPONER} | set(REGISTRY)
    nombres = set(re.findall(r"(?<![\w.])[a-z]+(?:_[a-z0-9]+)+(?!\w)", system_prompt_chat()))
    raras = sorted(n for n in nombres if n.startswith(VERBOS) and n not in conocidas)
    assert raras == [], f"el prompt del chat nombra operaciones que no existen: {raras}"


def test_d10_aislar_es_isolate():
    """La guía decía «combínalo con set_visibility para aislar»: set_visibility muta el
    documento en vivo y render_view pide preferir `isolate` (D10)."""
    assert not _nombra(GUIA_TECNICA, "set_visibility")
    assert _nombra(GUIA_TECNICA, "isolate")


def test_las_reglas_sirven_tambien_al_chat_viejo():
    """TRANSITORIO (entre F6 y F5a el chat viejo corre con este prompt): cada tool que nombran
    las reglas existe en el chat viejo y en el nuevo. Se borra en la F5b junto con agent.py."""
    from apolo.agent import agent as viejo

    assert viejo.SYSTEM_PROMPT == system_prompt_chat()
    del_viejo = {t["name"] for t in viejo.build_tools(auto=False)}
    candidatas = set(catalogo.CHAT) | set(catalogo.FUERA_DEL_CHAT) | {PROPONER} | del_viejo
    nombradas = {t for t in candidatas if _nombra(REGLAS_CHAT, t)}
    assert nombradas == {PROPONER}
    assert nombradas <= del_viejo


def _tuteo():
    """Los detectores de voseo, usted y españolismos de `test_pistas.py` (leídos de los gates
    de la UI): el prompt también le habla a la persona por boca del modelo."""
    spec = importlib.util.spec_from_file_location("_pistas_gate", RAIZ / "tests" / "test_pistas.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.TUTEO["voseo"], mod.TUTEO["otro_registro"], mod.USTED


def test_tuteo_neutro_y_vocabulario_de_la_app():
    chat = system_prompt_chat()
    for detector in _tuteo():
        m = detector.search(chat)
        assert m is None, f"«{m.group(0)}» en el prompt del chat"
    # el modelo le habla a la persona con las palabras de la tabla de ui/CLAUDE.md
    for palabra in ("pieza", "unión", "junta", "croquis", "grupo", "variante", "revisión",
                    "lámina", "comando"):
        assert _nombra(REGLAS_CHAT, palabra), palabra


def test_bytes_estables_en_otro_proceso():
    """Va al principio de cada request del chat: si cambia entre procesos, la caché de prompt
    no sirve (D12)."""
    sha = hashlib.sha256(system_prompt_chat().encode("utf-8")).hexdigest()
    assert system_prompt_chat() == system_prompt_chat()
    sonda = ("import hashlib; from apolo.design.instrucciones import system_prompt_chat; "
             "print(hashlib.sha256(system_prompt_chat().encode('utf-8')).hexdigest())")
    entorno = {**os.environ, "PYTHONHASHSEED": "4242",
               "PYTHONPATH": os.pathsep.join([str(RAIZ / "core"), os.environ.get("PYTHONPATH", "")])}
    out = subprocess.run([sys.executable, "-B", "-c", sonda], capture_output=True, text=True,
                         env=entorno, timeout=120, cwd=RAIZ)
    assert out.returncode == 0, out.stderr[-2000:]
    assert out.stdout.strip().splitlines()[-1] == sha
