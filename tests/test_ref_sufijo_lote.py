"""`$k_<sufijo>` en un lote: las piezas hijas de un compuesto creado en el MISMO lote.

Un `layout_tablero` crea `{cmd}_gabinete`, `{cmd}_puerta`, `{cmd}_d_<designación>`… con el
command_id del comando (no hay pieza `{cmd}`): `$k` no alcanzaba ninguna y `$k_gabinete` viajaba
literal («no existe $5_gabinete»). Ahora `$k_<sufijo>` = `{id del comando k}_<sufijo>`, en los
params de las acciones siguientes y en las aserciones del contrato (`expect`).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from tablero_electrico import arranque_directo

import apolo.api.main as api
from apolo.batch import check_refs, es_ref, resolve_refs
from apolo.commands.errors import CommandError
from apolo.doc.document import Document


def test_la_referencia_con_sufijo_se_resuelve_al_id_del_hijo():
    assert es_ref("$3_gabinete") and es_ref("$3_d_K1") and es_ref("$3")
    assert not es_ref("$_x") and not es_ref("$3_") and not es_ref("$x3")
    assert resolve_refs({"a": "$2_gabinete", "b": ["$1"]}, ["c4", "c7"]) == {
        "a": "c7_gabinete", "b": ["c4"]}
    with pytest.raises(CommandError, match=r"\$0_gabinete"):
        check_refs([{"type": "fasten", "params": {"a": "$0_gabinete"}}])
    with pytest.raises(CommandError, match="el lote tiene 1"):
        check_refs([{"type": "fasten", "params": {"a": "$2_gabinete"}}])


def test_k_sufijo_alcanza_el_gabinete_de_un_layout_del_mismo_lote():
    api.DOC = Document("ref-sufijo")
    acciones = arranque_directo() + [
        {"type": "layout_tablero", "params": {"ubicacion": "TAB1", "position": {"z": 1200}}}]
    k = len(acciones)  # el layout
    acciones += [
        {"type": "create_box", "params": {"name": "Soporte del tablero", "width": 600,
                                          "depth": 300, "height": 20, "position": {"z": 100}}},
        {"type": "fasten", "params": {"name": "f_tablero", "a": f"${k}_gabinete",
                                      "b": f"${k + 1}", "kind": "perno", "size": "M8", "qty": 4}},
    ]
    r = TestClient(api.app).post("/api/commands/batch", json={
        "actions": acciones,
        "expect": [{"tipo": "distancia", "a": f"${k}_gabinete", "b": f"${k + 1}", "min": 100}],
    })
    assert r.status_code == 200, r.text
    cid = next(c["id"] for c in api.DOC.commands if c["type"] == "layout_tablero")
    assert api.DOC.fasteners["f_tablero"]["a"] == f"{cid}_gabinete"
    assert r.json()["contrato"]["ok"] is True
