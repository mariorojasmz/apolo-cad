"""V7.6 E5 (manual): par de apriete CALCULADO + llave por paso, y orden intra-paso de
abajo hacia arriba (el residual «orden fino intra-grupo» declarado desde V7.2b)."""
import pytest

from apolo.doc import Document
from apolo.drawing.assembly_manual import _step_rows, _torque_note
from apolo.library.catalog import CATALOG
from apolo.library.engineering.bolts import tightening_torque_nm, wrench_size_mm


# --------------------------------------------------------------- par de apriete (puro)
@pytest.mark.parametrize("size,esperado", [("M8", 26), ("M12", 91), ("M14", 144), ("M16", 225)])
def test_torque_matches_commercial_tables(size, esperado):
    """T = K·d·(0.7·As·Ry) con K=0.2 (seco) reproduce las tablas comerciales 8.8 ±6 %."""
    assert tightening_torque_nm(size) == pytest.approx(esperado, rel=0.06)


def test_torque_depends_on_thread_condition():
    """La rosca lubricada alcanza la misma precarga con MENOS par (K 0.14 vs 0.20): por
    eso la condición se declara en la nota, nunca se asume."""
    seco = tightening_torque_nm("M12", condicion="seco")
    lub = tightening_torque_nm("M12", condicion="lubricado")
    assert lub < seco and lub / seco == pytest.approx(0.14 / 0.20, rel=1e-6)


def test_unknown_size_or_condition_raises():
    with pytest.raises(KeyError):
        tightening_torque_nm("M13")
    with pytest.raises(KeyError):
        tightening_torque_nm("M12", condicion="engrasado a ojo")


def test_wrench_size_is_the_hex_across_flats():
    assert wrench_size_mm("M12") == 18.0 and wrench_size_mm("M14") == 21.0


# ------------------------------------------------------------------ nota en el paso
def test_torque_note_lists_present_metrics():
    doc = Document("t")
    a = doc.execute("insert_component", {"component": "PERNO-HEX-M12",
                                         "position": {"x": 0, "y": 0, "z": 0}})
    b = doc.execute("insert_component", {"component": "PERNO-HEX-M16",
                                         "position": {"x": 60, "y": 0, "z": 0}})
    nota = _torque_note({"ids": [a, b]}, doc.scene, CATALOG)
    assert "M12 → 91 N·m (llave 18 mm)" in nota and "M16 → 225 N·m (llave 24 mm)" in nota
    assert "rosca seca" in nota                       # la condición va declarada


def test_no_metric_no_torque_note():
    """Sin métrica identificable NO se emite par: uno inventado aprieta de más o de
    menos y ambas cosas rompen la unión."""
    doc = Document("t")
    p = doc.execute("create_box", {"name": "Placa lisa", "width": 50, "depth": 50, "height": 5})
    assert _torque_note({"ids": [p]}, doc.scene, CATALOG) == ""


# ------------------------------------------------------------- orden intra-paso
def test_step_rows_are_bottom_up():
    """Dentro del paso, primero lo que va DEBAJO (z de la base), no el orden del log."""
    doc = Document("t")
    alto = doc.execute("create_box", {"name": "Zeta arriba", "width": 40, "depth": 40,
                                      "height": 20, "position": {"z": 500}})
    bajo = doc.execute("create_box", {"name": "Alfa abajo", "width": 40, "depth": 40,
                                      "height": 20, "position": {"z": 10}})
    medio = doc.execute("create_box", {"name": "Beta medio", "width": 40, "depth": 40,
                                       "height": 20, "position": {"z": 200}})
    filas = _step_rows({k: doc.scene[k] for k in (alto, bajo, medio)})
    assert [f.split("  ")[1][:5] for f in filas] == ["Alfa ", "Beta ", "Zeta "]
