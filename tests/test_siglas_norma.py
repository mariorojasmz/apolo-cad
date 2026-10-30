"""Las siglas de norma, en una fuente (`library/siglas_norma.py`). Ronda 9 de una máquina real:
«Bomba centrífuga EN 733 … (compra)» fallaba `bom.comprable` como compra sin norma porque la
norma de compra sólo reconocía DIN, ISO, ASME y ANSI."""

from __future__ import annotations

import pytest

from apolo.library import designacion_comercial as dc
from apolo.library.bom_comprable import motivo
from apolo.library.siglas_norma import NORMA_RE, SIGLAS_NORMA, norma
from apolo.services import rotulos


def _normas(texto):
    return [norma(m) for m in NORMA_RE.finditer(texto)]


@pytest.mark.parametrize("texto,esperada", [
    ("Bomba centrífuga EN 733 50-160", "EN 733"),
    ("Chapa EN 10088-2 1.4301", "EN 10088"),
    ("Tablero según IEC 60204-1", "IEC 60204"),
    ("Placa ASTM A36", "ASTM A36"),
    ("Brida ASME B16.5", "ASME B16.5"),
    ("Tubo UNE 19040", "UNE 19040"),
    ("Perno JIS B1180", "JIS B1180"),
    ("Cable NTP 370.252", "NTP 370.252"),
    ("Inox AISI 304", "AISI 304"),
    ("Eje SAE 1045", "SAE 1045"),
    ("Perno M10 din 933", "DIN 933"),  # las de antes siguen sin distinguir mayúsculas
])
def test_reconoce_la_sigla_con_su_numero(texto, esperada):
    assert _normas(texto) == [esperada]


@pytest.mark.parametrize("texto", [
    "tubo en acero", "Soporte en 3 tramos", "Guía en 2 piezas", "Perno EN M12", "Placa en A36",
])
def test_no_muerde_palabras_sueltas(texto):
    assert _normas(texto) == []


@pytest.mark.parametrize("nombre,esperada", [
    ("Bomba centrífuga EN 733 50-160 (compra)", "EN 733"),
    ("Motor trifásico IEC 60034-1 1.5 kW (compra)", "IEC 60034"),
    ("Tuerca M12 EN 10088-2", "EN 10088"),
    ("Válvula de bola DN40 AISI 316 ASME B16.11 (compra)", "ASME B16.11"),  # AISI es el grado
    ("Bisagra de la boca (pala 63 mm AISI 304, compra)", ""),
    ("Tubo en acero", ""),
])
def test_norma_de_compra(nombre, esperada):
    assert dc.norma_del_nombre(nombre) == esperada


def test_la_bomba_en_733_alcanza_para_comprar():
    nombre = "Bomba centrífuga EN 733 50-160 (compra)"
    fila = {"ref": "COMPRA", "descripcion": dc.nombre_de_compra(nombre),
            "norma": dc.norma_del_nombre(nombre)}
    assert motivo(fila) is None
    assert motivo({"ref": "COMPRA", "descripcion": "Bomba centrífuga (compra)"})  # sin norma, no


def test_una_sola_fuente():
    assert rotulos._NORMAS is SIGLAS_NORMA
    assert {"EN", "UNE", "ASTM", "AISI", "SAE", "JIS", "IEC", "NTP"} <= SIGLAS_NORMA
    assert rotulos.rol("Bomba EN 733") == "Bomba EN 733"  # el número de la norma no es instancia
