"""Rótulos con datos de ingeniería y ritmo parejo del video de la tienda (plan
video-montaje-pulido, F1 · D1 y D2: `services/rotulos.py`, `services/datos_rotulos.py` y las
etapas de `services/construccion.py`).

La piloto (proyecto 2 en los planes) no está en la CI: una «piloto en miniatura» en memoria la
reproduce con sus mismos comandos —largueros de ángulo, ejes y tubos de rodillo en patrón a
`paso`, taladros seguidos en el larguero, patas, motorreductor y guarda de chapa, cada cosa en su
grupo— y una máquina sin rodillos comprueba que nada se rompe. Las plantillas se prueban además
con `DatosRotulo` sintéticos, cifra por cifra contra su fuente (Riesgos del plan).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from apolo.doc.document import Document
from apolo.library.catalog import CATALOG
from apolo.services.construccion import (
    MAX_REVELADOS,
    PESO_RETOQUE,
    TIEMPOS,
    Paso,
    Tiempos,
    compactar,
    etapas,
    pasos_visuales,
    peso_roles,
    revelado,
)
from apolo.services.datos_rotulos import datos_rotulos, fs_cadenas
from apolo.services.rotulos import (
    MAX_TEXTO_ROTULO,
    MAX_TITULO_GENERADO,
    DatosRotulo,
    Pieza,
    base,
    cifra,
    familia,
    paso_mm,
    plantilla,
    texto_etapa,
)

NBSP = chr(0xA0)
H = 725  # altura del eje de los rodillos, como en la piloto


def _miniatura() -> Document:
    """La piloto en chico: 8 rodillos a 95,25 mm en vez de 20, con sus mismos comandos."""
    d = Document("piloto en miniatura")
    for nombre, expr in (("largo", "1000"), ("paso", "95.25"), ("n_rod", "8"),
                         ("h_eje", str(H)), ("x0", "(largo - (n_rod - 1)*paso)/2")):
        d.execute("set_variable", {"name": nombre, "expression": expr})
    c = {}
    c["lm"] = d.execute("insert_component", {
        "component": "ANG-75X6", "name": "Larguero (-Y)", "length": "=largo",
        "position": {"x": "=largo/2", "y": -297.5, "z": "=h_eje - 17.5"},
        "rotation": {"x": 0, "y": -90, "z": -90}})
    c["lp"] = d.execute("insert_component", {
        "component": "ANG-75X6", "name": "Larguero (+Y)", "length": "=largo",
        "position": {"x": "=largo/2", "y": 349.5, "z": "=h_eje - 17.5"},
        "rotation": {"x": 0, "y": 90, "z": 90}})
    c["eje"] = d.execute("create_cylinder", {
        "name": "Eje del rodillo", "radius": 6, "height": 608, "axis": "y",
        "position": {"x": "=x0", "y": 26, "z": "=h_eje"}})
    c["tubo"] = d.execute("insert_component", {
        "component": "TUBOR-2", "name": "Tubo del rodillo", "length": 500,
        "position": {"x": "=x0", "y": 0, "z": "=h_eje"}, "rotation": {"x": 90, "y": 180, "z": 0}})
    c["taladros"] = [d.execute("drill_hole", {
        "feature": c["lm"], "position": {"x": f"=x0 + {i}*paso", "y": -255, "z": "=h_eje"},
        "axis": "-y", "diameter": 13, "depth": 0}) for i in range(3)]
    c["ejes"] = d.execute("pattern_linear", {"feature": c["eje"], "count": "=n_rod",
                                             "spacing": {"x": "=paso", "y": 0, "z": 0}})
    c["tubos"] = d.execute("pattern_linear", {"feature": c["tubo"], "count": "=n_rod",
                                              "spacing": {"x": "=paso", "y": 0, "z": 0}})
    c["patas"] = [d.execute("insert_component", {
        "component": "TUBO-2X2", "name": f"Pata ({lado}Y, alimentación)", "length": "=h_eje - 65",
        "position": {"x": 200, "y": y, "z": "=10 + (h_eje - 65)/2"}})
        for lado, y in (("-", -285), ("+", 337))]
    c["motor"] = d.execute("insert_component", {
        "component": "MOTOR-037", "name": "Motorreductor",
        "position": {"x": 900, "y": 150, "z": 560}, "rotation": {"x": 0, "y": 0, "z": 90}})
    c["guarda"] = d.execute("create_sheet_metal", {
        "name": "Guarda de cadenas", "ancho": "=largo", "fondo": 115, "espesor": 2,
        "lados": ["frente"], "altura_pestana": 14, "radio": 2, "holes": [],
        "position": {"x": "=largo/2", "y": 304.5, "z": "=h_eje + 45"},
        "rotation": {"x": 180, "y": 0, "z": 0}})
    for grupo, miembros in (("Bastidor", [c["lm"], c["lp"]]),
                            ("Rodillos", [c["eje"], c["tubo"], c["ejes"], c["tubos"]]),
                            ("Patas y travesaños", c["patas"]),
                            ("Motorreductor", [c["motor"]]), ("Guardas", [c["guarda"]])):
        d.execute("create_group", {"name": grupo, "members": miembros})
    d.set_requirements({"carga_kg": 100, "largo_paquete_mm": 400, "ancho_paquete_mm": 400,
                        "alto_paquete_mm": 300})
    return d


@pytest.fixture(scope="module")
def miniatura():
    d = _miniatura()
    return d, pasos_visuales(d), datos_rotulos(d)


# ------------------------------------------------------------------ D2: ritmo parejo
@pytest.mark.parametrize("objetivo", [50, 75, 90])
def test_la_miniatura_tiene_titulos_cortos_y_etapas_parejas(miniatura, objetivo):
    _, pasos, datos = miniatura
    es = etapas(pasos, objetivo, datos=datos)
    assert es
    for e in es:
        assert len(e.titulo) <= MAX_TITULO_GENERADO and "más" not in e.titulo, e.titulo
        assert TIEMPOS.etapa_min_s <= e.duracion_s <= TIEMPOS.etapa_max_s, e
        assert len(e.texto) <= MAX_TEXTO_ROTULO


def test_los_taladros_seguidos_son_un_solo_paso(miniatura):
    d, pasos, _ = miniatura
    k = {c["id"]: n for n, c in enumerate(d.commands, 1)}
    taladros = [p.k for p in pasos if p.tipo == "drill_hole"]
    assert len(taladros) == 3
    unidad = next(u for u in compactar(pasos) if u[0].tipo == "drill_hole")
    assert [p.k for p in unidad] == taladros
    es = etapas(pasos, 75)
    todos = [x for e in es for x in e.pasos]
    assert taladros[-1] in todos and not set(taladros[:-1]) & set(todos)
    # el patrón de los ejes es su propio paso: el de los tubos que lo sigue es otra familia
    patrones = [k[c["id"]] for c in d.commands if c["type"] == "pattern_linear"]
    assert len(patrones) == 2 and set(patrones) <= set(todos)


def test_el_rotulo_de_los_rodillos_lleva_su_diametro_y_su_paso(miniatura):
    d, pasos, datos = miniatura
    es = etapas(pasos, 75, datos=datos)
    texto = next(e.texto for e in es if "rodillos Ø" in e.texto)
    nominal = CATALOG["TUBOR-2"].specs["nominal"]
    assert f"7 rodillos {nominal} cada {cifra(d.variables_resolved['paso'])} mm" in texto
    assert "cada 95,25 mm" in texto
    # el porqué sale de los requisitos: 400 mm / 95,25 mm → 4 rodillos bajo cada paquete
    assert "Cada paquete de 400 mm apoya en 4 rodillos o más." in texto


def test_los_rotulos_de_la_miniatura_dicen_cifras_de_su_fuente(miniatura):
    d, pasos, datos = miniatura
    textos = " ".join(e.texto for e in etapas(pasos, 90, datos=datos))
    motor = CATALOG["MOTOR-037"].specs
    assert f"de {cifra(motor['potencia_kW'])} kW a {cifra(motor['rpm_salida'])} rpm" in textos
    assert f"2 largueros de ángulo L 75x6 de {cifra(d.variables_resolved['largo'])} mm" in textos
    assert f"de {cifra(H - 65)} mm" in textos  # las patas: h_eje − 65


def test_los_rotulos_caben_en_dos_lineas(miniatura):
    from apolo.media.composicion import ESTILO, maquetar_rotulo

    _, pasos, datos = miniatura
    for objetivo in (50, 75, 90):
        for e in etapas(pasos, objetivo, datos=datos):
            texto = [s for s, _x, _y, es_titulo in maquetar_rotulo(e.titulo, e.texto, ESTILO).lineas
                     if not es_titulo]
            assert len(texto) <= 2, (e.titulo, e.texto, texto)


def test_una_maquina_sin_rodillos_no_se_rompe():
    d = Document("sin rodillos")
    caja = d.execute("create_box", {"name": "Base", "width": 400, "depth": 300, "height": 10})
    torre = d.execute("create_box", {"name": "Torre", "width": 40, "depth": 40, "height": 300,
                                     "position": {"x": 0, "y": 0, "z": 155}})
    d.execute("fillet", {"feature": torre, "radius": 2})
    d.execute("create_group", {"name": "Estructura", "members": [caja, torre]})
    pasos = pasos_visuales(d)
    datos = datos_rotulos(d)
    assert datos.fs_cadena == {} and datos.requisitos == {}
    es = etapas(pasos, 75, datos=datos)
    assert [e.titulo for e in es] == ["Estructura"]
    assert es[0].texto == "Se suman la base y la torre."
    assert etapas(pasos, 75) == es  # sin plantilla que aplique, el texto de siempre


# ------------------------------------------------------------------ compactar y revelado
def _p(k, grupos=("G",), roles=("Pieza",), agregados=None, reemplazados=(), quitados=()):
    agregados = (f"c{k}",) if agregados is None else agregados
    nombres = {f: (roles or ("Pieza",))[0] for f in (*agregados, *reemplazados, *quitados)}
    return Paso(k=k, cmd_id=f"c{k}", tipo="x", titulo=roles[0] if roles else "Pieza",
                etiqueta="", agregados=tuple(agregados), quitados=tuple(quitados),
                reemplazados=tuple(reemplazados), revelado=(tuple(agregados),) if agregados else (),
                roles=tuple(roles) if agregados else (), nombres=nombres, grupos=tuple(grupos))


def test_compactar():
    cadenas = [_p(k, roles=("Cadena rodillo a rodillo",)) for k in range(1, 5)]
    taladros = [_p(k, roles=(), agregados=(), reemplazados=("c0",)) for k in range(5, 9)]
    pinon = _p(9, roles=("Piñón motriz",))
    retoque_pinon = _p(10, roles=(), agregados=(), reemplazados=("c9",))
    otro_grupo = _p(11, grupos=("H",), roles=("Piñón motriz",))
    booleana = _p(12, grupos=("H",), roles=("Piñón motriz",), quitados=("c11",))
    patas = [_p(13, roles=("Pata (-Y, alimentación)",)), _p(14, roles=("Pata (+Y, motriz)",))]
    us = compactar([*cadenas, *taladros, pinon, retoque_pinon, otro_grupo, booleana, *patas])
    assert [[p.k for p in u] for u in us] == [
        [1, 2, 3, 4], [5, 6, 7, 8], [9, 10], [11], [12], [13, 14]]


def test_un_patron_crece_en_oleadas():
    escena = {f"c1_{n}": SimpleNamespace(name="Cadena rodillo a rodillo", command_id="c1")
              for n in range(19)}
    roles, listas = revelado(escena, list(escena))
    assert len(listas) == MAX_REVELADOS and set(roles) == {"Cadena rodillo a rodillo"}
    assert [f for sub in listas for f in sub] == list(escena)
    assert max(map(len, listas)) - min(map(len, listas)) <= 1  # oleadas parejas
    assert peso_roles(roles) == 1.0  # crecer no hace más largo el paso
    assert revelado(escena, ["c1_0"]) == (("Cadena rodillo a rodillo",), (("c1_0",),))


@pytest.mark.parametrize("roles, esperado", [
    ((), PESO_RETOQUE),
    (("Rodillo",) * 8, 1.0),
    (("Pata (-Y, alimentación)", "Pata (+Y, motriz)"), 1.0),
    (("Larguero", "Rodillo", "Pata", "Travesaño"), 2.5),
])
def test_peso_por_familia(roles, esperado):
    assert peso_roles(roles) == esperado


@pytest.mark.parametrize("rol_, b, f", [
    ("Pata (-Y, alimentación)", "Pata", "pata"),
    ("Travesaño superior (alimentación)", "Travesaño superior", "travesaño"),
    ("Piñón doble-simple (desfasado)", "Piñón doble-simple", "piñon"),  # sólo las vocales
    ("Chumacera (UCP205)", "Chumacera", "chumacera"),
    ("Placa base", "Placa base", "placa"),
])
def test_base_y_familia(rol_, b, f):
    assert base(rol_) == b and familia(rol_) == f


# ------------------------------------------------------------------ títulos y duraciones (D2)
def _grupos(*cuantos) -> list[Paso]:
    nombres = ("Bastidor", "Rodillos", "Patas y travesaños", "Motorreductor y su base",
               "Guardas", "Cadenas")
    pasos, k = [], 0
    for g, n in enumerate(cuantos):
        for _ in range(n):
            k += 1
            pasos.append(_p(k, grupos=(nombres[g],), roles=(f"Pieza{k}",)))
    return pasos


def test_titulos_sin_y_mas_y_con_el_grupo_que_pesa():
    # tres grupos chicos se funden: los dos que más pesan (nunca una lista de tres)
    es = etapas(_grupos(1, 1, 3), 30)
    assert [e.titulo for e in es] == ["Bastidor · Patas y travesaños"]
    # si los dos no caben en 32, el que más pesa
    es = etapas(_grupos(0, 0, 3, 1), 30)
    assert [e.titulo for e in es] == ["Patas y travesaños"]
    # un nombre con «y» se separa con « · »
    es = etapas(_grupos(1, 0, 1), 30)
    assert es[0].titulo == "Bastidor · Patas y travesaños"
    es = etapas(_grupos(1, 1), 30)
    assert es[0].titulo == "Bastidor y rodillos"


def test_una_etapa_de_muchos_grupos_nombra_los_dos_que_pesan():
    """fabrica-de-publicaciones F2: el video real tituló «Patas y travesaños, Motorreductor y 2
    más» (cortado en el rótulo). Con cuatro grupos en una etapa, los dos que más pesan, en su
    orden y sin listas: cabe en la línea del título y es el capítulo de YouTube."""
    from apolo.media.composicion import ESTILO, maquetar_rotulo

    es = etapas(_grupos(0, 0, 0, 1, 3, 2), 30)
    assert [e.titulo for e in es] == ["Guardas y cadenas"]
    es = etapas(_grupos(0, 0, 2, 1, 1, 1), 30)
    assert [e.titulo for e in es] == ["Patas y travesaños"]  # el que pesa; «y» no se encadena
    for cuantos in ((40, 18, 19, 11, 5, 4), (1, 1, 1, 1, 1, 1), (3, 60, 2, 2, 1, 30)):
        for e in etapas(_grupos(*cuantos), 50):
            assert "," not in e.titulo and "más" not in e.titulo, e.titulo
            assert len(e.titulo) <= MAX_TITULO_GENERADO
            tit = [s for s, *_r, es_tit in maquetar_rotulo(e.titulo, e.texto, ESTILO).lineas
                   if es_tit]
            assert tit == [e.titulo], tit  # entra entero, sin «…»


def test_el_rotulo_cuenta_por_rol_sin_lados_ni_ejes():
    """El texto de la piloto real: «Se suman «Pata (-Y, alimentación)», «Pata (+Y,
    alimentación)», «Pata (-Y, motriz)» y 57 piezas más». Cada rol se cuenta y una pieza suelta
    va por su rol con artículo."""
    nombres = ["Pata (-Y, alimentación)", "Pata (+Y, alimentación)", "Pata (-Y, motriz)",
               "Pata (+Y, motriz)", "Travesaño (alimentación)", "Travesaño (motriz)",
               "Motorreductor", "Placa base (-Y)"]
    fids = [f"p{i}" for i in range(len(nombres))]
    paso = Paso(k=1, cmd_id="m", tipo="montaje", titulo="Patas", etiqueta="",
                agregados=tuple(fids), quitados=(), reemplazados=(), revelado=(tuple(fids),),
                roles=("Pata",), nombres=dict(zip(fids, nombres)), grupos=("Patas y travesaños",))
    texto = texto_etapa([paso])
    assert texto == "Se suman 4 patas, 2 travesaños, el motorreductor y la placa base.", texto
    assert "(" not in texto and "«" not in texto


@pytest.mark.parametrize("rol_, esperado", [
    ("Motorreductor", "el motorreductor"), ("Placa base", "la placa base"),
    ("Guarda de cadenas (+Y)", "la guarda de cadenas"), ("Base", "la base"),
    ("Eje motriz", "el eje motriz"), ("UCP 205", "el UCP 205"), ("Unión", "la unión"),
    ("Piñón motriz", "el piñón motriz"), ("Sistema de tensión", "el sistema de tensión"),
])
def test_con_articulo(rol_, esperado):
    from apolo.services.rotulos import con_articulo

    assert con_articulo(rol_) == esperado


def test_un_grupo_retocado_no_da_nombre_a_la_etapa():
    pasos = [_p(1, grupos=("Rodillos",), roles=("Eje",)),
             _p(2, grupos=("Bastidor",), roles=(), agregados=(), reemplazados=("c0",)),
             _p(3, grupos=("Rodillos",), roles=("Tubo",))]
    assert [e.titulo for e in etapas(pasos, 40)] == ["Rodillos"]


@pytest.mark.parametrize("cuantos, objetivo", [
    ((40, 18, 19, 11, 5, 4), 75), ((40, 18, 19, 11, 5, 4), 50), ((3, 60, 2, 2, 1, 30), 90),
    ((1,), 75), ((200, 1, 1, 1, 1, 1), 75),
])
def test_ninguna_etapa_pasa_de_15_ni_baja_de_6(cuantos, objetivo):
    es = etapas(_grupos(*cuantos), objetivo)
    assert all(TIEMPOS.etapa_min_s <= e.duracion_s <= TIEMPOS.etapa_max_s for e in es), es
    assert all(len(e.titulo) <= MAX_TITULO_GENERADO for e in es)
    total = sum(e.duracion_s for e in es) + TIEMPOS.fijos_s
    assert total <= objetivo + 0.1 or len(es) * TIEMPOS.etapa_min_s > objetivo - TIEMPOS.fijos_s


def test_con_poco_que_mostrar_el_video_sale_mas_corto_no_mas_lento():
    es = etapas(_grupos(2, 2), 600, tiempos=Tiempos())
    assert [e.duracion_s for e in es] == [8.0, 8.0]  # 2 pasos × paso_max_s, no 15


# ------------------------------------------------------------------ D1: plantillas puras
def _datos(**piezas) -> DatosRotulo:
    return DatosRotulo(piezas=piezas)


def _rodillos(n: int, paso: float, nominal='Ø2"') -> dict:
    return {f"t{i}": Pieza("Tubo del rodillo", ref="TUBOR-2", specs={"nominal": nominal,
                                                                     "od": 50.8},
                           largo_mm=500, centro=(100 + i * paso, 0, H), medidas=(50.8, 50.8, 500))
            for i in range(n)}


def test_plantilla_de_rodillos_con_eje_y_porque():
    piezas = _rodillos(20, 95.25)
    piezas["e0"] = Pieza("Eje del rodillo", medidas=(12, 12, 608))
    datos = DatosRotulo(piezas=piezas, requisitos={"largo_paquete_mm": 400})
    frase = plantilla("Tubo del rodillo", [f"t{i}" for i in range(20)], datos)
    assert (frase.sustantivo, frase.desc, frase.detalle) == (
        "rodillos", 'Ø2" cada 95,25 mm', " sobre ejes Ø12")
    assert frase.porque == "Cada paquete de 400 mm apoya en 4 rodillos o más."


def test_sin_paso_constante_no_hay_plantilla_de_rodillos():
    piezas = _rodillos(3, 100.0)
    piezas["t2"] = Pieza("Tubo del rodillo", ref="TUBOR-2", specs={"od": 50.8}, largo_mm=500,
                         centro=(500, 0, H), medidas=(50.8, 50.8, 500))
    frase = plantilla("Tubo del rodillo", list(piezas), DatosRotulo(piezas=piezas))
    assert frase is None or "cada" not in frase.desc  # cae al perfil del catálogo, sin paso
    assert paso_mm(list(piezas.values())) is None


def test_plantillas_del_catalogo_cifra_por_cifra():
    cad = CATALOG["CADENA-ASA40-1"]
    datos = DatosRotulo(piezas={
        "cm": Pieza("Cadena motriz", ref=cad.ref, specs=dict(cad.specs)),
        "p1": Pieza("Piñón motriz", ref="PINON-ASA40-1-Z30",
                    specs=dict(CATALOG["PINON-ASA40-1-Z30"].specs)),
        "n1": Pieza("Tuerca del eje (-Y)", ref="TUERCA-M12", specs=dict(CATALOG["TUERCA-M12"].specs)),
        "g1": Pieza("Guarda de cadenas", chapa_mm=2.0),
        "b1": Pieza("Base del motor"),
    }, fs_cadena={"cm": 1.0947})
    cadena = plantilla("Cadena motriz", ["cm"], datos)
    assert cadena.desc == cad.specs["serie"] == "ASA 40"
    assert cadena.porque == "Cadena motriz con factor de seguridad 1,09."
    assert plantilla("Piñón motriz", ["p1"], datos).desc == "ASA 40 Z30"
    assert plantilla("Tuerca del eje", ["n1"], datos).desc == "M12"
    assert plantilla("Guarda de cadenas", ["g1"], datos).desc == "de chapa de 2 mm"
    assert plantilla("Base del motor", ["b1"], datos) is None  # sin plantilla: el conteo


def test_tornilleria_que_ya_dice_su_metrica_no_la_repite():
    perno = {"d": 10, "norma": "DIN 933"}
    piezas = {f"b{i}": Pieza(f"Perno M10x25 DIN 933 ({i})", ref="PERNO-M10", specs=perno)
              for i in range(4)}
    datos = _datos(**piezas)
    assert plantilla("Perno M10x25 DIN 933", list(piezas), datos) is None
    assert plantilla("Perno de anclaje", list(piezas), datos).desc == "M10"
    pasos = [_p(1, roles=("Perno M10x25 DIN 933",), agregados=tuple(piezas))]
    assert texto_etapa(pasos, datos) == "Se suman 4 pernos M10x25 DIN 933."


def test_el_rotulo_concuerda_el_adjetivo():
    pasos = [_p(1, roles=("Pie nivelador",), agregados=tuple(f"p{i}" for i in range(4)))]
    assert texto_etapa(pasos) == "Se suman 4 pies niveladores."


def test_perfil_con_largos_distintos_da_el_rango():
    tubo = CATALOG["TUBO-2X2"]
    datos = _datos(a=Pieza("Travesaño", ref=tubo.ref, nombre_cat=tubo.name, largo_mm=571.2),
                   b=Pieza("Travesaño", ref=tubo.ref, nombre_cat=tubo.name, largo_mm=660))
    assert plantilla("Travesaño", ["a", "b"], datos).desc == (
        'de tubo HSS 2"x2" de 571,2 a 660 mm')


def test_la_plantilla_dispara_en_la_etapa_que_mas_piezas_agrega():
    piezas = _rodillos(8, 95.25)
    datos = DatosRotulo(piezas=piezas)
    uno = _p(1, roles=("Tubo del rodillo",), agregados=("t0",))
    resto = _p(2, roles=("Tubo del rodillo",), agregados=tuple(f"t{i}" for i in range(1, 8)))
    assert texto_etapa([uno], datos) == "Se suma el tubo del rodillo."  # 1 sola: sin paso
    from apolo.services.rotulos import textos_etapas

    primero, segundo = textos_etapas([[uno], [resto]], datos)
    assert primero == "Se suma el tubo del rodillo."
    assert segundo == 'Se suman 7 rodillos Ø2" cada 95,25 mm.'


def test_cifra():
    assert cifra(2000) == f"2{NBSP}000"
    assert cifra(95.25) == "95,25" and cifra(0.37) == "0,37" and cifra(660) == "660"
    assert cifra(1.0947) == "1,09" and cifra(12.0, 1) == "12"


# ------------------------------------------------------------------ datos del documento
def test_fs_de_las_cadenas_se_lee_de_la_regla(monkeypatch):
    from apolo.services import transmision_rules

    reglas = [
        {"calc": {"titulo": "Transmisión por cadena Cadena motriz", "fs": 1.09}},
        {"calc": {"titulo": "Transmisión por cadena Rodillo y rodillo y 18 lazo(s) iguales",
                  "fs": 3.2}},
        {"calc": {"titulo": "Transmisión por cadena Sin potencia", "fs": None}},
        {"regla": "cadena desfasada · x", "estado": "aviso"},
    ]
    monkeypatch.setattr(transmision_rules, "chain_rules", lambda doc: reglas)
    cmds = [{"id": "c1", "type": "create_chain", "params": {"name": "Cadena motriz"}},
            {"id": "c2", "type": "create_chain", "params": {"name": "Rodillo y rodillo"}},
            {"id": "c3", "type": "create_chain", "params": {"name": "Sin potencia"}},
            {"id": "c4", "type": "create_box", "params": {"name": "Cadena motriz"}}]
    doc = SimpleNamespace(commands=cmds, scene={"c1": 0, "c2": 0, "c3": 0, "c4": 0})
    assert fs_cadenas(doc) == {"c1": 1.09, "c2": 3.2}


def test_datos_de_la_miniatura(miniatura):
    d, _, datos = miniatura
    larguero = next(p for p in datos.piezas.values() if p.nombre == "Larguero (-Y)")
    assert larguero.largo_mm == pytest.approx(d.variables_resolved["largo"])
    assert larguero.nombre_cat == CATALOG["ANG-75X6"].name
    guarda = next(p for p in datos.piezas.values() if p.nombre == "Guarda de cadenas")
    assert guarda.chapa_mm == 2.0 and guarda.ref is None
    eje = next(p for p in datos.piezas.values() if p.nombre == "Eje del rodillo")
    assert eje.medidas[0] == pytest.approx(12, abs=0.01)
    assert datos.requisitos["largo_paquete_mm"] == 400
