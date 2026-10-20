"""`vista-3d.html` y sus etiquetas (plan vista-3d-tienda, F2 · D3 y D5).

Las cifras de cada grupo salen de las plantillas de los rótulos (`services/cifras_grupo.py`):
el motor por su potencia, los rodillos por su Ø y su paso, los perfiles por su largo de corte; un
grupo sin plantilla que pese, por su conteo y su masa. Cada etiqueta se ancla en el tope de una
pieza real, en las coordenadas del GLB (metros, Y arriba): se comprueba contra la caja del nodo
de su grupo en el GLB escrito. El HTML pide sus scripts en versiones FIJAS, no descarga el
modelo al abrirse y escapa lo que viene del documento.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

import numpy as np
import pytest

from apolo.doc import Document
from apolo.kernel.glb_resumen import resumen
from apolo.library.catalog import CATALOG
from apolo.publicacion import vista3d, vista3d_html
from apolo.services.cifras_grupo import PESO_MINIMO, cifras_grupos, grupo_raiz
from apolo.services.rotulos import cifra

GRUPO_RARO = 'Guarda <"A&B">'


@pytest.fixture(scope="module")
def doc() -> Document:
    d = Document("Faja de etiquetas")
    d.execute("set_variable", {"name": "largo", "expression": "1000"})
    lm = d.execute("insert_component", {
        "component": "ANG-75X6", "name": "Larguero (-Y)", "length": "=largo",
        "position": {"x": "=largo/2", "y": -300, "z": 700}, "rotation": {"x": 0, "y": -90, "z": -90}})
    lp = d.execute("insert_component", {
        "component": "ANG-75X6", "name": "Larguero (+Y)", "length": "=largo",
        "position": {"x": "=largo/2", "y": 300, "z": 700}, "rotation": {"x": 0, "y": 90, "z": 90}})
    tubo = d.execute("insert_component", {
        "component": "TUBOR-2", "name": "Tubo del rodillo", "length": 500,
        "position": {"x": 200, "y": 0, "z": 725}, "rotation": {"x": 90, "y": 180, "z": 0}})
    tubos = d.execute("pattern_linear", {"feature": tubo, "count": 4,
                                         "spacing": {"x": 100, "y": 0, "z": 0}})
    motor = d.execute("insert_component", {
        "component": "MOTOR-037", "name": "Transportador · Motorreductor",
        "position": {"x": 900, "y": 450, "z": 560}, "rotation": {"x": 0, "y": 0, "z": 90}})
    pinon = d.execute("create_cylinder", {"name": "Piñón", "radius": 40, "height": 20,
                                          "axis": "y", "position": {"x": 900, "y": 560, "z": 560}})
    placa = d.execute("create_box", {"name": "Placa base", "width": 400, "depth": 300,
                                     "height": 20, "position": {"x": 500, "y": 0, "z": 10}})
    escuadra = d.execute("insert_component", {
        "component": "ANG-75X6", "name": "Escuadra", "length": 50,
        "position": {"x": 650, "y": 0, "z": 60}})
    guarda = d.execute("create_box", {"name": "Tapa", "width": 300, "depth": 10, "height": 100,
                                      "position": {"x": 900, "y": 620, "z": 560}})
    oculta = d.execute("create_box", {"name": "Oculta", "width": 10, "depth": 10, "height": 10,
                                      "position": {"x": 0, "y": 0, "z": 900}})
    d.execute("create_box", {"name": "Suelta", "width": 50, "depth": 50, "height": 10,
                             "position": {"x": 1200, "y": 0, "z": 5}})
    for nombre, miembros, padre in (
            ("Bastidor", [lm, lp], None), ("Rodillos", [tubo, tubos], None),
            ("Transmisión", [motor], None), ("Piñonería", [pinon], "Transmisión"),
            ("Base", [placa, escuadra], None), (GRUPO_RARO, [guarda], None),
            ("Escondido", [oculta], None)):
        d.execute("create_group", {"name": nombre, "members": miembros,
                                   **({"parent": padre} if padre else {})})
    d.set_visibility(oculta, False)
    return d


@pytest.fixture(scope="module")
def cifras(doc) -> dict:
    return {c.grupo: c for c in cifras_grupos(doc, vista3d.ids_glb(doc))}


def test_cada_grupo_raiz_dice_su_cifra_del_documento(doc, cifras):
    # un subgrupo cuenta para su raíz; lo oculto y lo suelto no llevan etiqueta
    assert list(cifras) == ["Bastidor", "Rodillos", "Transmisión", "Base", GRUPO_RARO]
    assert grupo_raiz("Piñonería", doc.groups) == "Transmisión"
    assert grupo_raiz("no-existe", doc.groups) is None
    largo = cifra(doc.variables_resolved["largo"])
    assert cifras["Bastidor"].cifra == f"2 largueros de ángulo L 75x6 de {largo} mm"
    nominal = CATALOG["TUBOR-2"].specs["nominal"]
    assert cifras["Rodillos"].cifra == f"4 rodillos {nominal} cada 100 mm"
    motor = CATALOG["MOTOR-037"].specs
    # la base («Motorreductor») no es el grupo: va con su nombre; dos piezas en la raíz
    assert cifras["Transmisión"].cifra == (f"Motorreductor de {cifra(motor['potencia_kW'])} kW "
                                           f"a {cifra(motor['rpm_salida'])} rpm")
    assert cifras["Transmisión"].piezas == 2
    # la escuadra de catálogo pesa < PESO_MINIMO del grupo: no habla por la placa
    base = cifras["Base"]
    assert base.cifra == f"2 piezas · {cifra(base.masa_kg, 1)} kg"
    assert CATALOG["ANG-75X6"].weight * 0.05 < PESO_MINIMO * base.masa_kg
    assert cifras[GRUPO_RARO].cifra.startswith("1 pieza · ")


def test_si_la_base_es_el_grupo_va_sola_la_cifra():
    d = Document("Sólo motor")
    m = d.execute("insert_component", {"component": "MOTOR-037", "name": "Motorreductor"})
    d.execute("create_group", {"name": "Motorreductor", "members": [m]})
    (c,) = cifras_grupos(d, vista3d.ids_glb(d))
    motor = CATALOG["MOTOR-037"].specs
    assert c.cifra == f"{cifra(motor['potencia_kW'])} kW a {cifra(motor['rpm_salida'])} rpm"


def _grupos_del_glb(ruta) -> dict:
    """{nombre: caja} de los nodos de grupo raíz: los hijos directos de la raíz del GLB."""
    res = resumen(ruta)
    raiz = next(n["indice"] for n in res["nodos"] if n["padre"] is None)
    return {n["nombre"]: n["caja"] for n in res["nodos"] if n["padre"] == raiz}


def test_las_etiquetas_se_anclan_en_el_tope_de_una_pieza_del_grupo(doc, tmp_path, monkeypatch):
    monkeypatch.setattr(vista3d, "buscar_gltfpack", lambda: None)
    vista = vista3d.generar(doc, tmp_path / vista3d.ARCHIVO, titulo="Faja")
    ets = vista3d_html.etiquetas(doc, vista["piso_mm"])
    cajas = _grupos_del_glb(tmp_path / vista3d.ARCHIVO)
    assert [e["grupo"] for e in ets] == ["Bastidor", "Rodillos", "Transmisión", "Base",
                                         GRUPO_RARO]
    for e in ets:
        lo, hi = cajas[e["grupo"]]
        p = np.array(e["posicion_m"])
        assert (p >= lo - 1e-3).all() and (p <= hi + 1e-3).all(), (e, lo, hi)
    por = {e["grupo"]: e for e in ets}
    # sobre un larguero (y = ±300 mm → Z = ∓0.3 m en el GLB), no en el aire entre los dos
    assert abs(por["Bastidor"]["posicion_m"][2]) == pytest.approx(0.3, abs=0.05)
    assert por["Bastidor"]["posicion_m"][1] == pytest.approx(cajas["Bastidor"][1][1], abs=1e-3)
    x = por["Rodillos"]["posicion_m"][0]  # sobre un rodillo (x = 200…500 mm), no entre dos
    assert min(abs(x - r) for r in (0.2, 0.3, 0.4, 0.5)) < 1e-3, x
    assert len(vista3d_html.etiquetas(doc, vista["piso_mm"], maximo=2)) == 2


def test_las_etiquetas_de_grupos_superpuestos_se_separan():
    """Cadenas y guardas a lo largo de la misma faja preferirían el mismo punto: la más pesada
    se queda con su preferido y la otra toma su candidato más lejano."""
    from apolo.services.cifras_grupo import CifraGrupo

    largo = ((1000, 0, 700), (500, 0, 700), (1500, 0, 700))
    cadenas = CifraGrupo("Cadenas", "x", 19, 30.0, largo)
    guardas = CifraGrupo("Guardas", "y", 2, 8.0, ((1000, 10, 760), (500, 10, 760),
                                                  (1500, 10, 760)))
    sola = CifraGrupo("Motor", "z", 1, 12.0, ((1900, 0, 600),))
    assert vista3d_html.repartir([guardas, cadenas, sola]) == [
        (500, 10, 760), (1000, 0, 700), (1900, 0, 600)]
    assert vista3d_html.repartir([guardas]) == [(1000, 10, 760)]  # sola, su preferido


class _Leer(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags: list[tuple[str, dict]] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def test_el_html_fija_versiones_no_descarga_al_abrir_y_escapa(doc, tmp_path, monkeypatch):
    monkeypatch.setattr(vista3d, "buscar_gltfpack", lambda: None)
    vista = vista3d.generar(doc, tmp_path / vista3d.ARCHIVO, titulo="Faja")
    inf = vista3d_html.escribir(doc, tmp_path / vista3d_html.ARCHIVO, titulo='Faja "A" <1 m>',
                                ident="faja-a", vista=vista, poster="miniatura.png")
    texto = (tmp_path / vista3d_html.ARCHIVO).read_text(encoding="utf-8")
    assert inf["archivo"] == "vista-3d.html" and len(inf["etiquetas"]) == 5
    # toda URL externa va a jsDelivr con versión exacta (nada de «@latest» ni sin versión)
    urls = re.findall(r"https?://[^\s'\"<>]+", texto)
    assert urls and all(re.match(r"https://cdn\.jsdelivr\.net/npm/(@[\w-]+/)?[\w-]+@\d+\.\d+\.\d+/",
                                 u) for u in urls), urls
    assert vista3d_html.MESHOPT in texto and vista3d_html.MODEL_VIEWER in texto
    p = _Leer()
    p.feed(texto)
    (mv,) = [a for t, a in p.tags if t == "model-viewer"]
    assert "src" not in mv and mv["data-src"] == "vista-3d.glb"  # el GLB, recién al tocar
    assert mv["poster"] == "miniatura.png" and mv["loading"] == "eager"
    assert mv["ar-modes"] == "webxr scene-viewer quick-look" and mv["ar-scale"] == "fixed"
    assert mv["alt"] == 'Faja "A" <1 m> en 3D'  # escapado al escribir, intacto al leer
    hotspots = [a for t, a in p.tags if a.get("slot", "").startswith("hotspot-")]
    assert [h["data-position"] for h in hotspots] == [
        " ".join(f"{v:g}" for v in e["posicion_m"]) for e in inf["etiquetas"]]
    assert "Guarda &lt;&quot;A&amp;B&quot;&gt;" in texto and GRUPO_RARO not in texto
    # fuera del comentario de cabecera, ASCII puro: se pega en una página de cualquier codificación
    assert "<b>Transmisi&#243;n</b>" in texto
    assert texto.split("-->", 1)[1].isascii()
    assert "-0 " not in texto and "Larguero" not in texto  # D5: grupos, no piezas
    assert f"descarga {cifra(vista['bytes'] / 1e6, 2)} MB" in texto
    assert 'id="apolo-v3d-faja-a"' in texto and "getElementById('apolo-v3d-faja-a')" in texto
