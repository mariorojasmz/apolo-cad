"""Testigos de la puerta de publicación (plan puerta-de-publicacion, D9 y D16): cada máquina de
referencia PÚBLICA de `tests/data/testigos/` pasa por la puerta entera (el endpoint con la app en
proceso: gravedad y marcha reales) y su veredicto POR ÍTEM es el congelado. Si un cambio de Apolo
mueve uno, la suite se pone roja nombrando el ítem; si el cambio es deliberado, se revisa y se
re-congela a propósito: `python -B scripts/testigos.py --en-proceso --congelar`.

Las máquinas de la tienda (testigos PRIVADOS, en el repo apolo-fabrica) se corren a mano con el
mismo script contra una API."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from apolo.doc import Document


def _cargar_script():
    ruta = Path(__file__).resolve().parents[1] / "scripts" / "testigos.py"
    spec = importlib.util.spec_from_file_location("testigos_script", ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


T = _cargar_script()
TESTIGOS = T.leer(T.DIR_PUBLICOS)


def _param(t: dict):
    marcas = [pytest.mark.torture] if (t["congelado"] or {}).get("tortura") else []
    return pytest.param(t, id=t["nombre"], marks=marcas)


def test_cada_receta_publica_tiene_su_testigo_congelado():
    assert sorted(t["nombre"] for t in TESTIGOS) == sorted(T.RECETAS)
    sin = [t["nombre"] for t in TESTIGOS if t["congelado"] is None]
    assert not sin, f"testigos sin veredicto congelado (scripts/testigos.py --congelar): {sin}"
    # los que la suite corre siempre aprueban enteros: son el ejemplo bueno de cada defecto
    for t in TESTIGOS:
        c = t["congelado"]
        if not c["tortura"]:
            assert c["aprobado"] is True, t["nombre"]


@pytest.mark.parametrize("t", [_param(t) for t in TESTIGOS])
def test_el_veredicto_del_testigo_no_se_movio(t):
    resultado = T.correr_en_proceso(Document.from_apolo_bytes(t["apolo"].read_bytes()))
    difs = T.diferencias(t["congelado"], resultado)
    assert not difs, (f"el veredicto de «{t['nombre']}» se movió (si es deliberado: "
                      "scripts/testigos.py --en-proceso --congelar --solo "
                      f"{t['nombre']}):\n" + "\n".join(difs))


def test_diferencias_nombra_el_item_que_se_movio():
    congelado = {"aprobado": True, "version_registro": "2", "firma": "f",
                 "items": {"union.agarre": "OK", "estructura.flecha": "OK"}}
    resultado = {"aprobado": False, "version_registro": "2", "firma": "f",
                 "items": [{"id": "union.agarre", "estado": "FALLA", "detalle": "no llega"},
                           {"id": "estructura.flecha", "estado": "OK"},
                           {"id": "riesgos.nuevo", "estado": "OK"}]}
    assert T.diferencias(congelado, resultado) == [
        "union.agarre: OK → FALLA — no llega", "riesgos.nuevo: (no estaba) → OK",
        "aprobado True → False"]
    assert T.diferencias(congelado, {**resultado, "aprobado": True, "items": [
        {"id": "union.agarre", "estado": "OK"}, {"id": "estructura.flecha", "estado": "OK"}]}) == []
    otra = T.diferencias(congelado, {**resultado, "firma": "g", "items": []})
    assert otra[0].startswith("firma del modelo f → g")
    assert "union.agarre: OK → (ya no está)" in otra


def test_exportar_la_tienda_lee_la_base_sin_tocarla(tmp_path):
    import sqlite3

    db = tmp_path / "apolo.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE projects(id INTEGER PRIMARY KEY, name TEXT, data BLOB)")
    for pid, nombre in ((2, "transportador-rodillos-cadena-2m"), (3, "faja motor cabeza"),
                        (4, "faja-motor-central"), (5, "otra")):
        con.execute("INSERT INTO projects VALUES (?, ?, ?)", (pid, nombre, f"zip{pid}".encode()))
    con.commit()
    con.close()
    antes = db.read_bytes()
    out = T.exportar_tienda(db, tmp_path / "privados", (3, 4))
    assert [p.name for p in out] == ["faja-motor-cabeza.apolo", "faja-motor-central.apolo",
                                     "transportador-rodillos-cadena-2m.apolo"]
    assert out[2].read_bytes() == b"zip2" and db.read_bytes() == antes
