"""Cimiento de planos pro: registro de materiales (densidad, rayado, resolución)."""

from apolo.library import materials


def test_density_known_and_default():
    assert materials.density("madera") == 5.0e-7
    assert materials.density("acero ASTM A500 Gr.B") == 7.85e-6
    assert materials.density("vidrio templado") == 2.5e-6
    assert materials.density("material raro") == materials.DEFAULT_DENSITY


def test_density_polimeros():
    # banda PVC, engomado de tambor y bulto de carga: NO acero
    assert materials.density("pvc") == 1.4e-6
    assert materials.density("caucho") == 1.5e-6
    assert materials.density("carton") == 1.4e-7
    assert materials.density("pvc") != materials.DEFAULT_DENSITY


def test_hatch_pattern():
    assert materials.hatch_pattern("madera") == "madera"
    assert materials.hatch_pattern("acero") == "ansi31"
    assert materials.hatch_pattern(None) == materials.DEFAULT_HATCH


class _Feat:
    def __init__(self, name, component=None):
        self.name = name
        self.component = component


def test_resolve_material_custom_by_name():
    assert materials.resolve_material(_Feat("Vidrio H1")) == "vidrio"
    assert materials.resolve_material(_Feat("H1 larguero tras izq")) == "madera"
    assert materials.resolve_material(_Feat("H1 travesano sup")) == "madera"
    assert materials.resolve_material(_Feat("Tambor motriz")) == "acero"
    assert materials.resolve_material(_Feat("Pieza sin pista")) == "acero"  # default


def test_resolve_material_polimeros_por_nombre():
    assert materials.resolve_material(_Feat("Banda PVC 2mm 700 (lazo cerrado)")) == "pvc"
    assert materials.resolve_material(_Feat("Engomado lagging 6mm Ø114 OD (motriz)")) == "caucho"
