"""La ficha VENCIDA (plan puerta-de-publicacion, F6): salió publicada una ficha con la carrera, la
masa y las medidas de un modelo que ya había cambiado. La ficha se ata a la firma del log con que
se redactó (`ficha.firma.json`, lo sella `publicar guion`); el paso «ficha» de la fábrica PARA si
el modelo cambió, salvo que se re-valide (`publicar ficha --revisar --vigente`), y compara la masa
y las medidas que la descripción menciona con el modelo (±2 %)."""

# ruff: noqa: F811 — `tienda` es un fixture importado de otro test
from __future__ import annotations

import json

import pytest
from test_publicacion_e2e import _preparar, tienda  # noqa: F401 — `tienda` es un fixture

from apolo.publicacion import ficha_vigente as fv
from apolo.publicacion.guion_vigente import VENCIDO

CIFRAS = {"masa_kg": 260.6, "bbox_mm": [4000.0, 650.0, 900.0]}


# ── el verificador de cifras ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("texto", [
    "Faja de 4 m. Pesa 260 kg y mide 4000 × 650 × 900 mm.",
    "Peso aprox.: 261,5 kg. Medidas generales 4 x 0,65 x 0,9 m.",
    "La máquina pesa 260.6 kg; mide 650 × 4000 × 900 mm (A sobre X).",
    "Mueve paquetes de hasta 15 kg; carga de 30 kg por metro.",  # carga, no la masa
    "Sin cifras.",
])
def test_cifras_que_coinciden_o_no_se_comparan(texto):
    assert fv.problemas(texto, CIFRAS) == []


@pytest.mark.parametrize("texto, dice", [
    ("Pesa 252,4 kg.", "pesa 252,4 kg"),
    ("Masa de la máquina: 2.400 kg.", "2.400 kg"),
    ("Mide 4000 × 600 × 900 mm.", "4000 × 600 × 900 mm"),
    ("Mide 900 × 650 × 4000 mm.", "900 × 650 × 4000 mm"),  # la altura es Z
])
def test_cifras_viejas_se_marcan(texto, dice):
    (p,) = fv.problemas(texto, CIFRAS)
    assert dice.lower() in p.lower() and "el modelo" in p


# ── la firma de la ficha ───────────────────────────────────────────────────────────────


def test_la_ficha_se_data_por_su_sello_o_por_su_guion(tmp_path):
    assert fv.firma_de_la_ficha(tmp_path) == (None, "nada la data")
    (tmp_path / "guion.json").write_text(json.dumps({"documento": {"firma": "g"}}), "utf-8")
    assert fv.firma_de_la_ficha(tmp_path)[0] == "g"
    (tmp_path / VENCIDO).write_text(json.dumps({"documento": {"firma": "v"}}), "utf-8")
    assert fv.firma_de_la_ficha(tmp_path)[0] == "v"  # el guion se rehízo; la ficha, no
    fv.sellar(tmp_path, "s", "re-validada")
    assert fv.firma_de_la_ficha(tmp_path)[0] == "s"


def test_ficha_vencida_para_y_revalidada_pasa(tienda):
    prep = _preparar(tienda, tienda.verde)
    carpeta = prep["carpeta"]
    sello = json.loads((carpeta / fv.FIRMA).read_text(encoding="utf-8"))
    assert sello["firma"] == prep["g"]["documento"]["firma"] and sello["como"] == "redactada"
    assert fv.exigir(carpeta, tienda.c, tienda.verde, eco=None)["firma"] == sello["firma"]
    r = tienda.c.post("/api/commands", json={"type": "create_box", "params": {
        "name": "Estante", "width": 500, "depth": 300, "height": 15,
        "position": {"x": 0, "y": 0, "z": 150}}})
    assert r.status_code == 200, r.text
    with pytest.raises(ValueError, match=r"(?s)otra versión del modelo.*--revisar --vigente "
                                         rf"--project {tienda.verde}"):
        fv.exigir(carpeta, tienda.c, tienda.verde, eco=None)
    hoy = fv.revalidar(carpeta, tienda.c, tienda.verde, eco=None)["firma"]
    assert hoy != sello["firma"]
    assert fv.exigir(carpeta, tienda.c, tienda.verde, eco=None)["firma"] == hoy


def test_masa_de_la_descripcion_contra_el_modelo(tienda):
    prep = _preparar(tienda, tienda.verde)
    carpeta = prep["carpeta"]
    ficha = prep["ficha"]
    texto = ficha.read_text(encoding="utf-8")
    ficha.write_text(texto.replace('"Mesa de taller."', '"Mesa de taller. Pesa 999 kg."'),
                     encoding="utf-8")
    with pytest.raises(ValueError, match=r"«Pesa 999 kg» y el modelo pesa"):
        fv.exigir(carpeta, tienda.c, tienda.verde, eco=None)
    with pytest.raises(ValueError, match="no la re-sello"):
        fv.revalidar(carpeta, tienda.c, tienda.verde, eco=None)
    masa = fv.cifras_del_modelo(tienda.mesa)["masa_kg"]
    ficha.write_text(texto.replace('"Mesa de taller."', f'"Mesa de taller. Pesa {masa:.1f} kg."'),
                     encoding="utf-8")
    assert fv.exigir(carpeta, tienda.c, tienda.verde, eco=None)["cifras"]["masa_kg"] == masa
