"""`create_roller_conveyor` con `motriz: libre`: el paso de rodillos es libre dentro de un rango
(Ø del tubo + `HOLGURA_TUBOS` … `PASO_LIBRE_MAX`); con cadena sigue la lista de los lazos 1:1.
La familia «transportador de rodillos por gravedad» pide paso 75 y 100 mm."""

from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from apolo.commands.errors import CommandError
from apolo.commands.models_rodillos_cadena import CreateRollerConveyorParams
from apolo.doc import Document
from apolo.doc.errors import DocumentError
from apolo.library import rodillos_cadena as rc
from apolo.library.checks import hardware_ids
from banco_guardas import interferencias_sin_tope


def _libre(**kw) -> rc.Disposicion:
    p = dict(largo=1000, ancho_util=500, paso=75, rodillo="TUBOR-2", altura=750, carga_kg=100,
             motriz=False, motor=None)
    p.update(kw)
    return rc.disposicion(**p)


# ------------------------------------------------------------------ reglas (puras)
def test_el_rango_libre_sale_del_tubo():
    assert rc.rango_paso_libre("TUBOR-2") == pytest.approx((70.8, 300.0))
    assert rc.rango_paso_libre("TUBOR-3") == pytest.approx((96.2, 300.0))
    # el máximo: en el largo mínimo caben los 4 rodillos que pide la disposición
    assert len(_libre(largo=rc.LARGO_MIN, paso=rc.PASO_LIBRE_MAX).xs) == 4


@pytest.mark.parametrize("paso", [75.0, 100.0])
def test_libre_con_paso_de_la_familia_por_gravedad(paso):
    d = _libre(paso=paso, largo=2000)
    n = int((2000 - 2 * rc.MARGEN_EXTREMO) // paso) + 1
    assert len(d.xs) == n - n % 2 and len(d.xs) >= 4
    assert all(b - a == pytest.approx(paso) for a, b in zip(d.xs, d.xs[1:]))
    assert d.xs[0] == pytest.approx(d.largo - d.xs[-1])  # centrados
    assert d.xs[0] >= rc.MARGEN_EXTREMO
    assert paso - d.d_rodillo >= rc.HOLGURA_TUBOS
    assert d.motriz is None and d.separadores == () and d.eslabones_rr == 0


@pytest.mark.parametrize("kw, texto", [
    ({"paso": 70}, r"va de 70\.8 a 300 mm"),
    ({"paso": 301}, r"va de 70\.8 a 300 mm"),
    ({"paso": 75, "rodillo": "TUBOR-3"}, r"va de 96\.2 a 300 mm"),
])
def test_libre_fuera_de_rango_dice_el_rango_del_tubo(kw, texto):
    with pytest.raises(ValueError, match=texto):
        _libre(**kw)


def test_con_cadena_sigue_la_lista():
    with pytest.raises(ValueError, match="sólo cierran"):
        _libre(paso=75, motriz=True, motor="MOTOR-037")
    with pytest.raises(ValidationError, match=r"sólo cierran \[95\.25, 107\.95, 120\.65\] mm"):
        CreateRollerConveyorParams(paso=75)
    assert CreateRollerConveyorParams(paso=95.254).paso == 95.25  # se ajusta al exacto


def test_el_schema_dice_las_dos_reglas():
    p = CreateRollerConveyorParams(motriz="libre", paso=75)
    assert p.paso == 75
    with pytest.raises(ValidationError, match="va de 70.8 a 300"):
        CreateRollerConveyorParams(motriz="libre", paso=60)
    s = CreateRollerConveyorParams.model_json_schema()["properties"]["paso"]
    assert "enum" not in s
    assert "95.25" in s["description"] and "Libre" in s["description"]
    assert f"+ {rc.HOLGURA_TUBOS:g} mm a {rc.PASO_LIBRE_MAX:g} mm" in s["description"]


# ------------------------------------------------------------------ la máquina (OCCT)
@pytest.mark.parametrize("paso", [75, 100])
def test_libre_construye_sin_que_los_tubos_se_toquen(paso):
    doc = Document(f"rodillos-libres-{paso}")
    doc.execute("create_roller_conveyor", {"largo": 1000, "motriz": "libre", "paso": paso})
    assert doc.check_integrity() == []
    tubos = [f for fid, f in doc.scene.items() if re.fullmatch(r"c1_tubo(s_\d+)?", fid)]
    assert len(tubos) == len(_libre(paso=paso).xs)
    xs = sorted(f.shape.bounding_box().center().X for f in tubos)
    assert all(b - a == pytest.approx(paso, abs=1e-3) for a, b in zip(xs, xs[1:]))
    formas = {fid: f.shape for fid, f in doc.scene.items()}
    assert interferencias_sin_tope(formas, hardware_ids(doc)) == []


def test_libre_con_paso_chico_no_entra_al_log():
    doc = Document("rodillos-libres-chico")
    with pytest.raises((CommandError, DocumentError)) as exc:
        doc.execute("create_roller_conveyor", {"largo": 1000, "motriz": "libre", "paso": 60})
    # un validador de modelo no tiene loc: el mensaje va sin el «: » vacío delante
    assert "create_roller_conveyor: Value error, paso 60: con rodillos libres y tubo TUBOR-2 " \
           "va de 70.8 a 300 mm" in str(exc.value)
    assert doc.commands == []
