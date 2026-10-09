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


def test_piece_role_es_lo_que_sigue_al_ultimo_punto_medio():
    assert materials.piece_role("Faja de banda · Banda") == "Banda"
    assert materials.piece_role("Faja A · Faja de banda · Banda") == "Banda"  # insert_project
    assert materials.piece_role("Banda PVC 2mm 700 (lazo cerrado)") == "Banda PVC 2mm 700 (lazo cerrado)"
    assert materials.piece_role(None) == ""


def test_resolve_material_rol_banda_es_pvc():
    # nombres REALES: la banda de create_belt_conveyor, la misma dentro de un insert_project
    # y la del 38. Antes la primera caía al default (acero: ~100 kg de lazo en 3 m)
    for name in ("Faja de banda · Banda", "Faja A · Faja de banda · Banda", "Banda",
                 "Banda PVC 2mm 700 (lazo cerrado)", "Bandas de retorno",
                 "Banda (sobre tambor motriz)", "Banda 500x6000x4"):
        assert materials.resolve_material(_Feat(name)) == "pvc", name
    # el rol gana también sobre el default del vertical
    assert materials.resolve_material(_Feat("Faja de banda · Banda"), default="madera") == "pvc"


def test_resolve_material_banda_solo_mencionada_no_es_pvc():
    # el «banda» del super-comando o de un rol que sólo la menciona no cambia el material
    for name in ("Faja de banda · Cama de deslizamiento", "Faja de banda · Pata (1)",
                 "Faja de banda · Tambor motriz", "Cama de la banda", "Guarda de banda",
                 "Soporte de la banda (+Y)", "Bandeja de goteo"):
        assert materials.resolve_material(_Feat(name)) == "acero", name


def test_resolve_material_banda_metalica_explicita():
    assert materials.resolve_material(_Feat("Banda de malla de acero inox")) == "acero inoxidable"
    assert materials.resolve_material(_Feat("Banda metálica")) == "acero"
    assert materials.resolve_material(_Feat("Banda de alambre")) == "acero"
    assert materials.resolve_material(_Feat("Banda de caucho")) == "caucho"
