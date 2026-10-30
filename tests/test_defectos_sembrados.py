"""Defectos SEMBRADOS en la puerta de publicación (plan puerta-de-publicacion, D9 y D14): sobre un
testigo BUENO de `tests/data/testigos/` (que aprueba entero: `test_testigos.py`), una mutación
mínima de modelo —un perno corto, un tensor sin carrera, una guarda soldada…— y la puerta debe
atraparla en SU ítem general. Cada id general del registro tiene ≥ 1 defecto o una exención
escrita con su porqué: agregar un ítem sin su defecto pone roja la suite (8D: cada defecto nuevo de
producción suma aquí su testigo malo antes de corregirse).

Presupuesto: cada defecto corre `reunir` + `evaluar` sobre SU modelo mutado, con la gravedad dada
por estable y sin la marcha (lo caro; la gravedad real sólo en su propio defecto). La faja se
carga del `.apolo` por defecto (≈ 0,9 s) y su puerta tarda ≈ 1,8 s; la ménsula, ≈ 0,3 s."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pytest
from fastapi.testclient import TestClient
from tablero_electrico import arranque_directo, con_rotulos

import apolo.api.main as api
from apolo.doc import Document
from apolo.library.calidad.item import FALLA, OK, SIN_EVALUAR
from apolo.library.calidad.registro import REGISTRO, Entrada, Fuente, evaluar
from apolo.services import escenarios as E
from apolo.services import puerta_publicacion as pp
from apolo.services.calidad_tensores import poner_tensores

TESTIGOS = Path(__file__).resolve().parent / "data" / "testigos"

#: Ítems generales SIN defecto sembrado, cada uno con su porqué.
EXENTOS = {
    "entrega.no_evaluado": (
        "los `no_aplica` de la entrega en una faja, una ménsula o unos rodillos están justificados "
        "POR CONSTRUCCIÓN (sujeción con < 5 sólidos, poses sin estudios o sin poses: el mismo "
        "dato que el hecho; gravedad y acceso tienen ítem propio), y ningún testigo lleva "
        "interruptor de resguardo. Lo dispara la apertura de un enclavamiento sin junta: su "
        "defecto sembrado, sobre un modelo real, es test_enclavamiento_resguardo::test_la_"
        "apertura_sin_junta_se_justifica_por_escrito_en_la_puerta (puerta-sin-sobrediseno F3d); "
        "el caso puro: test_puerta_publicacion::test_lo_que_la_entrega_no_evaluo_se_justifica_"
        "o_bloquea"),
    "publicado.sustitutos_fieles": (
        "la cinta animada se DERIVA de la sección del sólido de la banda (D13 de la fábrica) y "
        "sólo se autodetecta la banda de create_belt_conveyor, de lazo convexo: ninguna mutación "
        "de un modelo la hace infiel sin falsear el código. Su defecto sembrado vive en "
        "test_ruta_faja_modelo (la faja en Ω con la regla vieja atraviesa la guarda y la fábrica "
        "no la acepta) y su traducción a FALLA en test_puerta_publicacion::"
        "test_memoria_marcha_erc_y_escenarios"),
}


def _base(nombre: str) -> Document:
    return Document.from_apolo_bytes((TESTIGOS / f"{nombre}.apolo").read_bytes())


def _id(doc, nombre: str) -> str:
    return next(fid for fid, f in doc.scene.items() if f.name == nombre)


def _caja(doc, nombre, w, dp, h, x, y, z) -> str:
    return doc.execute("create_box", {"name": nombre, "width": w, "depth": dp, "height": h,
                                      "position": {"x": x, "y": y, "z": z}})


def _editar_faja(doc, **cambios) -> None:
    (cmd,) = [c for c in doc.commands if c["type"] == "create_belt_conveyor"]
    doc.edit(cmd["id"], {**cmd["params"], **cambios})


# ------------------------------------------------------------------ mutaciones de la ménsula
def escombro(d):  # un bloque olvidado que entra en la placa base
    _caja(d, "Escombro", 40, 40, 40, 120, 60, 10)


def tapa_suelta(d):  # una pieza sin camino de carga: cae con la gravedad
    _caja(d, "Tapa suelta", 100, 100, 5, 0, 0, 200)


def cabeza_encajonada(d):  # cuatro paredes a 1 mm de la cabeza: la llave no entra
    bb = d.scene[_id(d, "Perno M10×35 DIN 933")].shape.bounding_box()
    cx, cy, top = (bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2, 22.0
    for k, (dx, dy, w, dp) in enumerate(((-11, 0, 4, 30), (11, 0, 4, 30),
                                         (0, -11, 30, 4), (0, 11, 30, 4))):
        _caja(d, f"Pared ({k})", w, dp, 40, cx + dx, cy + dy, top + 20)


def perno_por_una_aleta(d):  # el defecto del tensor publicado: cruza un ala de la C, no la otra
    d.execute("create_sheet_metal", {"name": "Soporte en C", "ancho": 100, "fondo": 100,
                                     "espesor": 3, "lados": ["frente", "atras"],
                                     "altura_pestana": 50, "position": {"x": 400, "y": 0, "z": 12}})
    _caja(d, "Eje roscado", 40, 50, 30, 400, 5, 37)
    d.execute("insert_component", {"component": "PERNO-HEX-M10", "rotation": {"x": -90},
                                   "position": {"x": 400, "y": 50, "z": 37}})


def perno_corto(d):  # M10×50 a mano por 46 mm de chapa: la tuerca no tiene hilo
    _caja(d, "Placa A", 120, 80, 36, 400, 0, 18)
    _caja(d, "Placa B", 120, 80, 10, 400, 0, 41)
    d.execute("insert_component", {"component": "PERNO-HEX-M10", "position": {"x": 400, "z": 46}})
    d.execute("insert_component", {"component": "TUERCA-M10", "position": {"x": 400, "z": -4}})


def pivote_sin_traba(d):  # hallazgos-del-revisor D8: el pivote de la escalera, DIN 934 simple
    a = _caja(d, "Brazo fijo", 120, 80, 10, 400, 0, 5)
    b = _caja(d, "Brazo que gira", 120, 80, 8, 400, 0, 14)
    jb = d.execute("join_bolted", {"a": a, "b": b, "size": "M10", "count": 1})
    bb = d.scene[next(f for f, x in d.scene.items() if x.command_id == jb
                      and x.component == "PERNO-HEX-M10")].shape.bounding_box()
    d.execute("add_joint", {"name": "pivote", "type": "giratoria", "parent": a, "child": b,
                            "origin": {"x": (bb.min.X + bb.max.X) / 2,
                                       "y": (bb.min.Y + bb.max.Y) / 2, "z": 0},
                            "axis": {"x": 0, "y": 0, "z": 1}})


def perno_a_medida(d):  # un perno M10×47 modelado a mano: ese largo no se compra
    _caja(d, "Placa A", 120, 80, 20, 400, 0, 10)
    _caja(d, "Placa B", 120, 80, 10, 400, 0, 25)
    r = 16 / math.sqrt(3)
    hexa = [[r * math.cos(math.radians(60 * k)), r * math.sin(math.radians(60 * k))]
            for k in range(6)]
    cab = d.execute("create_extrude_poly", {"name": "Cabeza", "points": hexa, "height": 6.4,
                                            "position": {"x": 400, "y": 0, "z": 33.2}})
    vas = d.execute("create_cylinder", {"name": "Perno M10×47 a medida", "radius": 5,
                                        "height": 47, "position": {"x": 400, "y": 0, "z": 6.5}})
    d.execute("boolean_op", {"name": "Perno M10×47 a medida", "operation": "union",
                             "target": vas, "tools": [cab]})
    d.execute("insert_component", {"component": "TUERCA-M10", "position": {"x": 400, "z": -4}})


def agujero_al_canto(d):  # F6: el revisor halló agujeros a 1,5 mm del canto de una placa
    a = _caja(d, "Placa A", 120, 80, 10, 400, 0, 5)
    b = _caja(d, "Placa B", 120, 80, 8, 400, 0, 14)
    for f, z in ((b, 18), (a, 10)):  # Ø11 a 6 mm del canto x = 340 (pide 1,2·11 = 13,2)
        d.execute("drill_hole", {"feature": f, "position": {"x": 346, "z": z}, "axis": "-z",
                                 "diameter": 11})
    d.execute("insert_component", {"component": "PERNO-HEX-M10",
                                   "position": {"x": 346, "z": 18}})
    d.execute("insert_component", {"component": "TUERCA-M10", "position": {"x": 346, "z": -4}})


def perno_en_la_testa_de_madera(d):
    """hallazgos-del-revisor D7: dos listones de madera con un M6 a 2,5·d de su testa (la zapata
    de la mesa plegable: «la testa se raja»). Con la tabla de chapas pasaba (e ≥ 1,2·d0)."""
    a = _caja(d, "Listón A", 300, 45, 20, 400, 0, 10)
    b = _caja(d, "Listón B", 300, 45, 20, 400, 0, 30)
    for f in (a, b):
        d.set_material(f, "madera")
        d.execute("drill_hole", {"feature": f, "position": {"x": 535, "z": 40}, "axis": "-z",
                                 "diameter": 6.6})
    d.execute("insert_component", {"component": "PERNO-HEX-M6", "length": 60,
                                   "position": {"x": 535, "z": 40}})
    d.execute("insert_component", {"component": "TUERCA-M6", "position": {"x": 535, "z": -2.5}})


def placa_sin_agujeros(d):
    """F3c de puerta-sin-sobrediseno: un `fasten` perno declara dos M8 entre una placa y la base,
    pero ninguna tiene los agujeros (la chumacera sobre el puente del tanque: pasaba las dos
    puertas y la encontró un revisor de taller)."""
    p = _caja(d, "Placa de la chumacera", 60, 60, 8, 100, 0, 16)
    d.execute("fasten", {"name": "f_chumacera", "a": p, "b": _id(d, "Placa base"),
                         "kind": "perno", "size": "M8", "qty": 2})


def pata_esbelta(d):  # 8 × 8 mm y 1,5 m: pandea con su propio peso y el de la máquina
    p = _caja(d, "Pata esbelta", 8, 8, 1500, 0, 90, 762)
    d.execute("ground", {"name": "gp", "feature": p})


def pie_sin_capacidad(d):
    """hallazgos-del-revisor D6: un pie nivelador de compra, anclado, sin carga nominal (la mesa de
    soldadura Ø28: nadie sabía si aguantaba 500 kg de carga y 291 kg de mesa)."""
    p = _caja(d, "Pie nivelador M12 (compra)", 60, 60, 12, 0, 300, 6)
    d.execute("ground", {"name": "gpie", "feature": p})


def tubo_abierto_higienico(d):
    """hallazgos-del-revisor D9: en equipo higiénico, un poste de tubo soldado a la placa base y
    abierto arriba (la pata de la mesa inox bajo su cubierta: el agua entra y no sale)."""
    afuera = _caja(d, "Poste", 40, 40, 200, 110, 0, 112)
    luz = _caja(d, "luz", 36, 36, 202, 110, 0, 112)
    d.execute("boolean_op", {"name": "Poste", "operation": "cut", "target": afuera, "tools": [luz]})
    d.execute("fasten", {"name": "w_poste", "a": _id(d, "Poste"), "b": _id(d, "Placa base"),
                         "kind": "soldadura", "throat_mm": 2})
    d.set_requirements({**(d.requirements or {}), "higienico": True})


def contrapeso_en_voladizo(d):  # 212 kg atornillados fuera de la huella de apoyo
    c = _caja(d, "Contrapeso", 300, 300, 300, 600, 0, 150)
    d.execute("fasten", {"name": "fc", "a": c, "b": _id(d, "Placa base"), "kind": "perno",
                         "size": "M10", "qty": 4})


def bloque_en_un_m6(d):  # casi 2 t colgando de un solo M6
    c = _caja(d, "Bloque colgado", 1000, 500, 500, 0, 400, 300)
    d.execute("fasten", {"name": "fb", "a": c, "b": _id(d, "Placa base"), "kind": "perno",
                         "size": "M6", "qty": 1})


def cordon_minimo(d):  # 212 kg en un cordón de a = 1 mm y 10 mm de largo
    c = _caja(d, "Bloque soldado", 300, 300, 300, 0, 260, 150)
    d.execute("fasten", {"name": "fs", "a": c, "b": _id(d, "Placa base"), "kind": "soldadura",
                         "throat_mm": 1, "length_mm": 10})


def riostra_que_no_toca(d):  # uniones-que-tocan: la riostra soldada a 5 mm de su placa
    r = _caja(d, "Riostra", 40, 40, 200, 100, 60, 117)  # la placa base acaba en z = 12
    d.execute("fasten", {"name": "fr", "a": r, "b": _id(d, "Placa base"), "kind": "soldadura",
                         "throat_mm": 3, "length_mm": 160})


def perno_sin_metrica(d):  # una unión apernada declarada sin métrica: no se puede verificar
    t = _caja(d, "Tapa", 100, 100, 5, 0, 0, 24.5)
    d.execute("fasten", {"name": "ft", "a": t, "b": _id(d, "Ménsula"), "kind": "perno"})


def superficie_sin_espesor(d):  # geometría de construcción que quedó en el modelo
    pts = [[200, 0, 0], [300, 0, 0], [300, 100, 0], [200, 100, 0]]
    d.execute("boundary_surface", {"name": "Chapa sin espesor", "curves": [
        {"points": [a, b]} for a, b in zip(pts, pts[1:] + pts[:1])]})


def material_sin_tabla(d):  # hallazgos-del-revisor D1: un «cedro» se pesaba como acero
    d.set_material(_id(d, "Ménsula"), "cedro")


def compra_sin_designacion(d):
    """hallazgos-del-revisor D4: la bola de transferencia de la mesa de bolas, «(compra)» sin norma,
    fabricante ni código: nadie sabe qué pedir."""
    _caja(d, "Bola de transferencia Ø25 (compra)", 30, 30, 30, 0, 0, 37)


def cadena_subdimensionada(d):  # ASA 40 simple con 3 kW a 60 rpm
    a, b = (d.execute("insert_component", {"component": "PINON-ASA40-1-Z15", "rotation": {"x": 90},
                                           "position": {"x": x, "y": 300, "z": 600}})
            for x in (0, 400))
    d.execute("create_chain", {"name": "Cadena", "pinon_a": a, "pinon_b": b,
                               "potencia_kw": 3.0, "rpm_a": 60})


def cadena_a_mano(d):
    """lo-que-se-mueve D1: el ramal de una cadena 08B por `insert_component` entre dos piñones (el
    elevador de la tanda nocturna: 3 tramos rectos que no envolvían el piñón ni seguían a su junta,
    y que ningún ítem veía)."""
    for x in (0, 400):
        d.execute("insert_component", {"component": "PINON-ASA40-1-Z15", "rotation": {"x": 90},
                                       "position": {"x": x, "y": 300, "z": 600}})
    d.execute("insert_component", {"component": "CADENA-ASA40-1",
                                   "position": {"x": 200, "y": 300, "z": 640}})


def resguardo_sin_junta(d):
    """lo-que-se-mueve D3: un interruptor de resguardo -B1 con su lengüeta, ligado a su
    dispositivo, y la hoja sin junta (las puertas de carga del elevador colgaban de bisagras sin
    junta: nadie verificó que abrieran sin chocar)."""
    c = d.execute("insert_component", {"component": "RESG-2NC", "name": "Interruptor de puerta -B1",
                                       "position": {"x": 600, "y": 0, "z": 100}})
    d.execute("insert_component", {"component": "RESG-LENGUETA", "name": "Lengüeta -B1",
                                   "rotation": {"x": 180}, "position": {"x": 600, "y": 0, "z": 160}})
    d.execute("add_device", {"ref": "RESG-2NC", "designacion": "-B1", "ubicacion": "+CAMPO",
                             "pieza": c})


def motor_sin_tierra(d):  # el tablero de arranque directo sin el PE del motor
    d.execute_many([c for c in arranque_directo()
                    if c["params"].get("puntos") != ["-X0:2", "-M1:PE"]])


def hilo_pe_suelto(d):
    """El arranque directo con el PE del motor por un conductor suelto: el motor llega a tierra
    («puesta a tierra» ok) pero el hilo verde-amarillo del cable -W1 queda sin conectar (el defecto
    del elevador que vio `pro_esquema`: 13 cables 5G con el PE suelto)."""
    d.execute_many([wire_pe_suelto(c) for c in arranque_directo()])


def wire_pe_suelto(c: dict) -> dict:
    if c["params"].get("puntos") == ["-X0:2", "-M1:PE"]:
        return {"type": "add_wire", "params": {"puntos": ["-X0:2", "-M1:PE"], "color": "GNYE"}}
    return c


def mando_sin_rotulo(d):
    """nombres-por-funcion A13: el tablero de arranque directo con el rótulo de cada mando y
    piloto menos uno (-S2, la marcha): quien opera no sabe qué hace ese botón."""
    d.execute_many(con_rotulos(arranque_directo(), {"-S1": "Paro", "-P1": "En marcha"}))


def escenario_que_falla(d):  # su último run, vigente, no llegó a las rpm
    esc = {"duracion_s": 2, "aserciones": ["-M1.rpm >= 1700 dentro_de 1 s desde pulsar -S1"],
           "acciones": [{"t": 0.3, "accion": "pulsar", "dispositivo": "-S1",
                         "actuador": "marcha", "durante_s": 0.2}]}
    E.poner(d, "arranque", esc)
    filas = [{"asercion": esc["aserciones"][0], "pasa": False, "detalle": "llegó a 0 rpm"}]
    E.guardar_resultado(d, "arranque", E.resultado_compacto(
        {"veredicto": "falla", "aserciones": filas}, {"resumen": {}},
        firma=E.firma_documento(d), hash_esc=E.hash_escenario(esc), simulacion=None))


def balance_que_no_cuadra(d):  # plan balance-de-producto: al ritmo nominal una caja se traba
    d.set_requirements({**d.requirements, "paquetes_por_minuto": 20})
    esc = {"duracion_s": 10, "flujo": {"ritmo_por_min": "nominal", "plazo_s": 8},
           "mecanica": {"sumideros": [{"nombre": "fin", "punto_mm": [1400, 0, 0], "normal": [1, 0, 0]}]},
           "eventos": [{"tipo": "producto", "nombre": "caja", "dims_mm": [150, 120, 100],
                        "posicion_mm": [-500, 0, 850]}],
           "aserciones": ["flujo.cuadra al_final"]}
    E.poner(d, "flujo", esc)
    esc = d.escenarios["flujo"]["escenario"]
    fl = {"plazo_s": 8.0, "sumideros": ["fin"], "entraron": 3, "salieron": 1, "por_sumidero": {"fin": 1},
          "perdidos": [], "retenidos": [], "sin_entrar": [], "cuadra": False,
          "trabados": [{"producto": "p_caja_1", "desde_s": 4.2, "t": 6.2, "pos_mm": [612.0, 0.0, 850.0]}]}
    filas = [{"asercion": "flujo.cuadra == true al_final", "pasa": False, "detalle": "al final vale false"}]
    E.guardar_resultado(d, "flujo", E.resultado_compacto(
        {"veredicto": "falla", "aserciones": filas}, {"resumen": {}, "mecanica": {"flujo": fl}},
        firma=E.firma_documento(d), hash_esc=E.hash_escenario(esc), simulacion=None))


# ------------------------------------------------------------------ mutaciones de la faja
def motor_movido(d):  # el motorreductor corrido 100 mm: choca dentro de la plantilla
    d.execute("transform", {"feature": _id(d, "Faja de banda · Motorreductor"),
                            "translate": {"x": 0, "y": -100, "z": 0}})


def tensor_sin_carrera(d):  # sin la UCT y un tensor declarado de 20 mm (pide ~104)
    _editar_faja(d, tensor="ninguno")
    poner_tensores(d, [{"piezas": [_id(d, "Faja de banda · Tambor de cola")], "carrera_mm": 20,
                        "eje": "x"}])


def sin_tensor(d):  # la cola sin UCT ni tensor declarado: no hay con qué retensar
    _editar_faja(d, tensor="ninguno")


def tensor_a_medias(d):  # D1 de puerta-sin-sobrediseno: la cola cuenta 2×, no más
    from apolo.library.calidad.tensor import carrera_requerida
    from apolo.services.calidad_tensores import lazos

    _editar_faja(d, tensor="ninguno")
    (lz,) = lazos(d, medir=False)
    pide = carrera_requerida("banda", lz["largo_mm"])  # 0,45·pide × 2 = 0,9 de lo que pide
    poner_tensores(d, [{"piezas": [_id(d, "Faja de banda · Tambor de cola")],
                        "carrera_mm": round(0.45 * pide, 1), "eje": "x"}])


def carga_de_300_kg(d):  # el encargo pide 300 kg: rodamientos, motor y memoria no dan
    d.set_requirements({**d.requirements, "carga_kg": 300})


def largueros_de_madera(d):  # el bastidor en madera: flecha fuera de L/240
    for i in (1, 2):
        d.set_material(_id(d, f"Faja de banda · Larguero ({i})"), "madera")


def guarda_soldada(d):
    d.execute("fasten", {"name": "guarda_soldada", "a": _id(d, "Faja de banda · Guarda lateral (1)"),
                         "b": _id(d, "Faja de banda · Larguero (1)"), "kind": "soldadura",
                         "throat_mm": 3, "length_mm": 100})


def chumacera_soldada(d):
    d.execute("fasten", {"name": "chumacera_soldada",
                         "a": _id(d, "Faja de banda · Chumacera motriz (−Y)"),
                         "b": _id(d, "Faja de banda · Placa porta-chumacera motriz (−Y)"),
                         "kind": "soldadura", "throat_mm": 3, "length_mm": 100})


def sin_empalme_de_campo(d):
    """faja-compacta F1b (D12, registro v20): sin su empalme de campo, la banda es sin fin y la
    atraviesan la cama y sus soportes: no se cambia sin desarmarlos (la re-revisión de la mesa de
    sorteo, MEDIA). La pieza se quita de la escena con su unión, como haría `remove_commands`."""
    g = _id(d, "Empalme de campo de la banda (grapas articuladas)")
    d.scene.pop(g)
    d.fasteners = {k: f for k, f in d.fasteners.items() if g not in (f.get("a"), f.get("b"))}


def travesano_en_el_lazo(d):  # un travesaño soldado a los dos largueros DENTRO del lazo
    b = _caja(d, "Travesaño interior", 40, 772, 40, 0, 0, 840)
    for k in (1, 2):
        d.execute("fasten", {"name": f"s{k}", "a": b, "b": _id(d, f"Faja de banda · Larguero ({k})"),
                             "kind": "soldadura", "throat_mm": 4, "length_mm": 80})
    # con el empalme de campo la banda se abre y sale igual: el defecto es el lazo SIN empalme
    # (al final: cada `execute` regenera la escena y lo traería de vuelta)
    sin_empalme_de_campo(d)


def sin_guardas(d):
    _editar_faja(d, guardas=False)


def cuna_de_entrada_sin_guarda(d):
    """puerta-sin-sobrediseno F2 (D3–D4, D8): con el sentido DECLARADO sólo cuenta la cuña de
    entrada de cada tambor; sin guardas, ésa queda al alcance y la puerta tiene que verlo."""
    d.set_requirements({**(d.requirements or {}), "sentido_transporte": [1, 0, 0]})
    _editar_faja(d, guardas=False)


def sin_cierres(d):
    """La v5 de create_belt_conveyor sin sus cierres = la v4 TAL CUAL (F6): sin la guarda inferior
    bajo la ranura banda ↔ larguero (35 mm, abierta por abajo entre las guardas de los tambores),
    sin las placas de cierre de los largueros y con el techo de cola sólo sobre el tambor. Por ahí
    el brazo entra al lazo y baja la mano a las cuñas: sólo se ve doblándolo."""
    assert any(f.name.endswith("Guarda inferior (1, tramo 1)") for f in d.scene.values()), \
        "el testigo faja ya no trae sus cierres (create_belt_conveyor v5)"
    _editar_faja(d, cierres=False)


def acople_sin_guarda(d):
    """F3b de puerta-sin-sobrediseno: el acople motor ↔ eje motriz gira expuesto si se saca su
    guarda (antes no era peligro: la plantilla tenía que justificarla). La plantilla no se puede
    recortar pieza a pieza: se quita de la escena con sus uniones, como haría `remove_commands`."""
    g = _id(d, "Faja de banda · Guarda del acople")
    d.scene.pop(g)
    d.fasteners = {k: f for k, f in d.fasteners.items() if g not in (f.get("a"), f.get("b"))}


def resguardo_sin_declarar(d):  # D15: nadie dijo por qué las guardas son así
    d.funciones = [f for f in d.funciones if f["funcion"] != "resguardo"]


def guarda_redundante(d):
    """puerta-sin-sobrediseno D5: una chapa por fuera de la guarda del tambor de cola, atornillada
    a ella, que cubre el MISMO hueco (la ronda de corrección que agrega y no quita)."""
    g = _id(d, "Faja de banda · Guarda del tambor de cola")
    bb = d.scene[g].shape.bounding_box()
    afuera = -1 if (bb.min.X + bb.max.X) / 2 < 0 else 1
    x = (bb.min.X - 3.5) if afuera < 0 else (bb.max.X + 3.5)
    c = _caja(d, "Guarda exterior de cola", 3, bb.max.Y - bb.min.Y, bb.max.Z - bb.min.Z, x,
              (bb.min.Y + bb.max.Y) / 2, (bb.min.Z + bb.max.Z) / 2)
    d.execute("fasten", {"name": "f_guarda_ext", "a": c, "b": g, "kind": "perno", "size": "M8",
                         "qty": 2})
    return c


@dataclass(frozen=True)
class Defecto:
    nombre: str
    base: str
    mutar: Callable
    atrapa: dict
    gravedad_real: bool = False


DEFECTOS = (
    Defecto("escombro", "mensula_atornillada", escombro, {"entrega.semaforo": FALLA}),
    Defecto("tapa_suelta", "mensula_atornillada", tapa_suelta, {"entrega.gravedad": FALLA},
            gravedad_real=True),
    Defecto("cabeza_encajonada", "mensula_atornillada", cabeza_encajonada,
            {"union.acceso_herramienta": FALLA}),
    Defecto("perno_por_una_aleta", "mensula_atornillada", perno_por_una_aleta,
            {"union.agarre": FALLA}),
    Defecto("perno_corto", "mensula_atornillada", perno_corto, {"union.retencion": FALLA}),
    Defecto("pivote_sin_traba", "mensula_atornillada", pivote_sin_traba,
            {"union.retencion": FALLA}),
    Defecto("perno_a_medida", "mensula_atornillada", perno_a_medida,
            {"union.largo_comercial": FALLA}),
    Defecto("agujero_al_canto", "mensula_atornillada", agujero_al_canto,
            {"union.distancia_al_borde": FALLA}),
    Defecto("perno_en_la_testa_de_madera", "mensula_atornillada", perno_en_la_testa_de_madera,
            {"union.distancia_al_borde": FALLA}),
    Defecto("placa_sin_agujeros", "mensula_atornillada", placa_sin_agujeros,
            {"union.agujeros": FALLA}),
    Defecto("pata_esbelta", "mensula_atornillada", pata_esbelta, {"estructura.pandeo": FALLA}),
    Defecto("pie_sin_capacidad", "mensula_atornillada", pie_sin_capacidad,
            {"apoyo.capacidad": FALLA}),
    Defecto("tubo_abierto_higienico", "mensula_atornillada", tubo_abierto_higienico,
            {"higiene.limpiable": FALLA}),
    Defecto("contrapeso_en_voladizo", "mensula_atornillada", contrapeso_en_voladizo,
            {"estructura.vuelco": FALLA}),
    Defecto("bloque_en_un_m6", "mensula_atornillada", bloque_en_un_m6,
            {"union.capacidad": FALLA}),
    Defecto("cordon_minimo", "mensula_atornillada", cordon_minimo, {"union.soldaduras": FALLA}),
    Defecto("riostra_que_no_toca", "mensula_atornillada", riostra_que_no_toca,
            {"union.contacto_real": FALLA}),
    Defecto("perno_sin_metrica", "mensula_atornillada", perno_sin_metrica,
            {"union.dimensionadas": FALLA}),
    Defecto("superficie_sin_espesor", "mensula", superficie_sin_espesor,
            {"fabricabilidad": FALLA}),
    Defecto("material_sin_tabla", "mensula", material_sin_tabla, {"material.conocido": FALLA}),
    Defecto("compra_sin_designacion", "mensula", compra_sin_designacion,
            {"bom.comprable": FALLA}),
    Defecto("cadena_subdimensionada", "mensula", cadena_subdimensionada,
            {"transmision.capacidad": FALLA}),
    Defecto("cadena_a_mano", "mensula", cadena_a_mano,
            {"transmision_flexible.de_su_comando": FALLA}),
    Defecto("resguardo_sin_junta", "mensula", resguardo_sin_junta,
            {"seguridad.resguardo_abre": FALLA}),
    Defecto("motor_sin_tierra", "mensula", motor_sin_tierra, {"riesgos.electrico": FALLA}),
    Defecto("hilo_pe_suelto", "mensula", hilo_pe_suelto, {"riesgos.electrico": FALLA}),
    Defecto("mando_sin_rotulo", "mensula", mando_sin_rotulo,
            {"interfaz.nombres_por_funcion": FALLA}),
    Defecto("escenario_que_falla", "mensula", escenario_que_falla,
            {"funcion.escenarios": FALLA}),
    Defecto("balance_que_no_cuadra", "faja", balance_que_no_cuadra,
            {"funcion.flujo_de_producto": FALLA}),
    Defecto("motor_movido", "faja", motor_movido, {"montaje.interferencia_interna": FALLA}),
    Defecto("tensor_sin_carrera", "faja", tensor_sin_carrera,
            {"transmision_flexible.tension": FALLA}),
    # sin tensor no hay qué medir: SIN_EVALUAR, que bloquea como FALLA (D1 de la puerta)
    Defecto("sin_tensor", "faja", sin_tensor,
            {"transmision_flexible.tension": SIN_EVALUAR}),
    Defecto("tensor_a_medias", "faja", tensor_a_medias,
            {"transmision_flexible.tension": FALLA}),
    Defecto("carga_de_300_kg", "faja", carga_de_300_kg,
            {"elementos_rodantes.l10": FALLA, "accionamiento.factor_servicio": FALLA,
             "ingenieria.reglas": FALLA, "memoria.veredicto": FALLA}),
    Defecto("largueros_de_madera", "faja", largueros_de_madera,
            {"estructura.flecha": FALLA, "memoria.veredicto": FALLA}),
    Defecto("guarda_soldada", "faja", guarda_soldada,
            {"riesgos.resguardos_desmontables_con_herramienta": FALLA}),
    Defecto("chumacera_soldada", "faja", chumacera_soldada, {"consumibles.reemplazables": FALLA}),
    Defecto("travesano_en_el_lazo", "faja", travesano_en_el_lazo,
            {"consumibles.reemplazables": FALLA}),
    Defecto("sin_empalme_de_campo", "faja", sin_empalme_de_campo,
            {"consumibles.reemplazables": FALLA}),
    Defecto("sin_guardas", "faja", sin_guardas, {"riesgos.partes_moviles": FALLA}),
    Defecto("sin_cierres", "faja", sin_cierres, {"riesgos.partes_moviles": FALLA}),
    Defecto("cuna_de_entrada_sin_guarda", "faja", cuna_de_entrada_sin_guarda,
            {"riesgos.partes_moviles": FALLA}),
    Defecto("acople_sin_guarda", "faja", acople_sin_guarda, {"riesgos.partes_moviles": FALLA}),
    Defecto("resguardo_sin_declarar", "faja", resguardo_sin_declarar,
            {"diseno.soluciones_por_funcion": FALLA}),
    Defecto("guarda_redundante", "faja", guarda_redundante, {"diseno.sin_sobrantes": FALLA}),
)


def generales() -> set[str]:
    """Los ids GENERALES del registro: las entradas y las claves del mapa de cada fuente."""
    out = set()
    for e in REGISTRO:
        out |= set(e.mapa) if isinstance(e, Fuente) else {e.id} if isinstance(e, Entrada) else set()
    return out


def _puerta(doc, gravedad_real: bool, sobrantes: bool = False) -> dict:
    """`sobrantes`: probar qué sobra (lo caro de una máquina con guardas, ~35 s en la faja) sólo
    en el defecto que lo mira."""
    if gravedad_real:  # el endpoint entero: la gravedad de MuJoCo (sin banda no hay marcha)
        api.DOC = doc
        r = TestClient(api.app).post("/api/puerta-publicacion")
        assert r.status_code == 200, r.text
        return r.json()
    ins = _insumos(doc, sobrantes)
    return evaluar(ins)


def _insumos(doc, sobrantes: bool = False) -> dict:
    ins = pp.reunir(doc, expand=lambda x: x, gravedad={
        "resultado": {"fell": [], "estables": list(doc.scene), "n_grounded": len(doc.grounds)},
        "motivo": ""}, sobrantes=sobrantes)
    ins["marcha"] = {"resultado": "sin_marcha", "detalle": "no se corre en los defectos"}
    return ins


# ------------------------------------------------------------------ cobertura
def test_cada_item_general_tiene_su_defecto_o_su_exencion():
    gen = generales()
    atrapados = {iid for d in DEFECTOS for iid in d.atrapa}
    assert atrapados <= gen, f"defectos con ids que el registro no tiene: {atrapados - gen}"
    assert set(EXENTOS) <= gen, f"exenciones de ids que ya no existen: {set(EXENTOS) - gen}"
    assert not atrapados & set(EXENTOS), "un ítem exento que ya tiene defecto: quita la exención"
    faltan = gen - atrapados - set(EXENTOS)
    assert not faltan, ("ítem(s) del registro sin defecto sembrado ni exención: "
                        f"{sorted(faltan)}. Suma su testigo malo a DEFECTOS (D9)")
    assert len({d.nombre for d in DEFECTOS}) == len(DEFECTOS)
    assert {d.base for d in DEFECTOS} <= {p.stem for p in TESTIGOS.glob("*.apolo")}


# ------------------------------------------------------------------ cada defecto, atrapado
@pytest.mark.parametrize("defecto", DEFECTOS, ids=lambda d: d.nombre)
def test_la_puerta_atrapa_el_defecto_sembrado(defecto):
    doc = _base(defecto.base)
    defecto.mutar(doc)
    r = _puerta(doc, defecto.gravedad_real, "diseno.sin_sobrantes" in defecto.atrapa)
    it = {i["id"]: i for i in r["items"]}
    obtenido = {iid: it[iid]["estado"] for iid in defecto.atrapa}
    assert obtenido == defecto.atrapa, {iid: it[iid]["detalle"] for iid in defecto.atrapa}
    assert r["aprobado"] is False


def test_el_pivote_sin_traba_falla_por_ser_eje_de_giro():
    """`pivote_sin_traba` falla POR la junta (D8 de hallazgos-del-revisor): la misma unión DIN 934
    sin la junta pasa, y la falla nombra la junta."""
    doc = _base("mensula_atornillada")
    pivote_sin_traba(doc)
    it = _item(_puerta(doc, False), "union.retencion")
    assert it["estado"] == FALLA
    assert [c["eje_de_giro"] for c in it["evidencia"]["casos"]] == ["pivote"], it["evidencia"]
    doc.remove_commands([doc.commands[-1]["id"]])  # sin la junta
    assert _item(_puerta(doc, False), "union.retencion")["estado"] == OK


def test_el_hilo_pe_suelto_bloquea_la_puerta_por_su_regla_y_no_se_justifica():
    """El ERROR del ERC «hilo de protección sin conectar» es el único error que tumba
    `riesgos.electrico` en `hilo_pe_suelto` (los avisos «aparato de campo sin pieza» son del
    tablero de prueba, sin piezas 3D) y pone la entrega en ROJO. Con todos los avisos justificados
    por escrito, el error sigue bloqueando: un error jamás se justifica."""
    doc = _base("mensula")
    hilo_pe_suelto(doc)
    r = _puerta(doc, False)
    it = _item(r, "riesgos.electrico")
    assert it["estado"] == FALLA
    casos = it["evidencia"]["casos"]
    assert [c["regla"] for c in casos if c["estado"] == "error"] == ["hilo de protección sin conectar"], casos
    assert {c["regla"] for c in casos if c["estado"] == "aviso"} == {"aparato de campo sin pieza"}
    assert "-W1" in it["piezas"]
    assert _item(r, "entrega.semaforo")["evidencia"]["veredicto"] == "ROJO"
    pp.poner_justificadas(doc, [{"regla": x, "porque": _PORQUE}
                                for x in ("hilo de protección sin conectar", "aparato de campo sin pieza")])
    it = _item(_puerta(doc, False), "riesgos.electrico")
    assert it["estado"] == FALLA and [c["regla"] for c in it["evidencia"]["casos"]] == [
        "hilo de protección sin conectar"], it["evidencia"]


# ------------------------------------------------------------------ el bug que destapó el testigo
def test_la_tornilleria_asentada_no_cae_en_la_gravedad_de_las_puertas():
    """La ménsula con `join_bolted` caía en la gravedad de las puertas: el casco CONVEXO del
    perno no cabe en su barreno y MuJoCo lo expulsaba (38 mm). Las puertas la tratan asentada,
    como su sujeción declarada; la simulación de siempre (`gravity_test`) no cambia."""
    from apolo.physics.stability import stability_test
    from apolo.services.delivery_inputs import exclusiones_declaradas

    d = _base("mensula_atornillada")
    args = (d.scene, d.joints, d.mates, d.fasteners, d.grounds)
    pernos = exclusiones_declaradas(d)[1]
    assert len(pernos) == 4
    crudo = stability_test(*args, seconds=0.5)
    assert {c["id"] for c in crudo["fell"]} & pernos  # el casco no cabe: lo expulsa
    assert stability_test(*args, seconds=0.5, asentadas=pernos)["fell"] == []
    api.DOC = d
    rep = TestClient(api.app).post("/api/delivery-check", json={"con_gravedad": True}).json()
    assert rep["veredicto"] == "VERDE", rep


# ------------------------------------------------------------------ la cuña de entrada (v7)
def test_con_sentido_declarado_la_cuna_de_entrada_sin_guarda_falla():
    """El defecto `cuna_de_entrada_sin_guarda` falla POR la cuña de entrada: cada peligro de cuña
    se sondea en un solo borde del arco (3 puntos a lo ancho, no 6) con el sentido del requisito,
    y al menos uno queda al alcance."""
    from apolo.services.calidad_seguridad import controles_seguridad

    d = _base("faja")
    cuna_de_entrada_sin_guarda(d)
    r = controles_seguridad(d, electrico=False)
    it = r["items"][0]
    cunas = [p for p in r["peligros"] if p.get("cuna")]
    assert cunas and all(len(p["objetivos"]) == 3 for p in cunas)
    ev = {p["id"]: p for p in it["evidencia"]["peligros"]}
    assert all(ev[p["id"]]["sentido"] == "cuña de entrada; sentido: requisito sentido_transporte"
               for p in cunas)
    assert it["estado"] == FALLA and any(ev[p["id"]]["estado"] == FALLA for p in cunas)


# ------------------------------------------------------------------ el hueco de las rectas (F6)
def test_las_rectas_no_ven_la_ranura_junto_a_la_banda():
    """8D del defecto de producción de la F6 (la cuña retorno ↔ desvío de la faja de motor
    central, a 60 mm de una ranura de 36 mm junto al borde de la banda): con sólo las sondas
    RECTAS, la v4 sin cierres sale resguardada —el hueco—; con el brazo doblado (ISO 13857 tabla 6)
    fallan las cuñas de los dos tambores, y sólo por las sondas dobladas."""
    from apolo.services.calidad_seguridad import controles_seguridad

    d = _base("faja")
    sin_cierres(d)
    rectas = controles_seguridad(d, electrico=False, brazo_doblado=False)["items"][0]
    assert rectas["estado"] == OK, rectas["detalle"]
    it = controles_seguridad(d, electrico=False)["items"][0]
    assert it["estado"] == FALLA
    malos = [p for p in it["evidencia"]["peligros"] if p["estado"] == FALLA]
    assert len(malos) == 2 and all(p["id"].startswith("atrapamiento:") for p in malos)
    assert all(p["n_brazo_doblado"] == p["n_alcanzan"] > 0 for p in malos)
    f = malos[0]["fallas"][0]
    assert f["via"] == "brazo doblado" and f["distancia_mm"] <= 850 and len(f["codo"]) == 3
    assert "con el brazo doblado" in it["detalle"]


# ------------------------------------------------------------------ puerta-sin-sobrediseno F3 + D11
_PORQUE = "barreno de drenaje del agua de lavado: va sin perno a propósito"


def _item(r: dict, iid: str) -> dict:
    return next(i for i in r["items"] if i["id"] == iid)


def test_de_dos_guardas_que_cubren_el_mismo_hueco_sobra_una_y_justificada_pasa():
    """D5 voraz: la chapa exterior (pesa más y se prueba antes) sobra porque la guarda de
    cola sigue cubriendo; la guarda, ya sin la chapa, la pide la cuña de cola. D6: justificada por
    escrito, la misma medición sale OK."""
    from apolo.library.calidad.registro import evaluar as evaluar_registro

    doc = _base("faja")
    extra = guarda_redundante(doc)
    ins = _insumos(doc, sobrantes=True)
    it = _item(evaluar_registro(ins), "diseno.sin_sobrantes")
    assert it["estado"] == FALLA and it["piezas"] == [extra], it["detalle"]
    nec = {c["id"]: c for c in it["evidencia"]["necesarias"]}
    guarda = _id(doc, "Faja de banda · Guarda del tambor de cola")
    assert nec[guarda]["la_pide"] in ("peligros", "sujeción"), nec[guarda]
    ins["justificadas"] = [*ins["justificadas"], {"pieza": extra, "porque": _PORQUE}]
    it = _item(evaluar_registro(ins), "diseno.sin_sobrantes")
    assert it["estado"] == OK and extra in [j["id"] for j in it["evidencia"]["justificadas"]]


def _barreno_sin_perno(d):  # un Ø9 en la placa base, lejos de la ménsula: aviso (lint)
    d.execute("drill_hole", {"feature": _id(d, "Placa base"), "position": {"x": 120, "y": 70,
                                                                          "z": 12},
                             "axis": "-z", "diameter": 9})


def test_un_aviso_justificado_deja_de_bloquear_y_un_error_nunca():
    """D11: el AMARILLO de un barreno sin perno (aviso de la entrega y de la memoria) pasa
    justificado por escrito; el ROJO de un choque, justificado igual, sigue bloqueando."""
    doc = _base("mensula_atornillada")
    _barreno_sin_perno(doc)
    r = _puerta(doc, False)
    sem = _item(r, "entrega.semaforo")
    assert sem["estado"] == FALLA and sem["evidencia"]["veredicto"] == "AMARILLO", sem
    reglas = sorted({c["regla"] for c in sem["evidencia"]["casos"]})
    pp.poner_justificadas(doc, [{"regla": x, "porque": _PORQUE} for x in reglas])
    r = _puerta(doc, False)
    for iid in ("entrega.semaforo", "ingenieria.reglas"):
        assert _item(r, iid)["estado"] == OK, _item(r, iid)["detalle"]
    assert _item(r, "entrega.semaforo")["evidencia"]["justificados"]

    doc = _base("mensula_atornillada")
    escombro(doc)
    pp.poner_justificadas(doc, [{"regla": "interferencias en diseño", "porque": _PORQUE}])
    sem = _item(_puerta(doc, False), "entrega.semaforo")
    assert sem["estado"] == FALLA and sem["evidencia"]["veredicto"] == "ROJO", sem


# ------------------------------------------------------------------ lo-que-se-mueve (F1)
def test_la_cadena_de_su_comando_pasa_y_la_hecha_a_mano_dice_que_comando_usar():
    """D1: la cadena de `create_chain` (la de `cadena_subdimensionada`) es OK en su ítem; la de
    `insert_component` falla nombrando la pieza, su comando y con qué modelarla. Sin cadenas, el
    testigo de la ménsula no aplica."""
    it = _item(_puerta(_base("mensula"), False), "transmision_flexible.de_su_comando")
    assert it["estado"] == "NO_APLICA", it
    doc = _base("mensula")
    cadena_subdimensionada(doc)
    it = _item(_puerta(doc, False), "transmision_flexible.de_su_comando")
    assert it["estado"] == OK, it["detalle"]
    assert [c["tipo"] for c in it["evidencia"]["cadenas"]] == ["create_chain"]
    assert it["evidencia"]["elementos"] == {"de_su_comando": 1}
    doc = _base("mensula")
    cadena_a_mano(doc)
    it = _item(_puerta(doc, False), "transmision_flexible.de_su_comando")
    (c,) = it["evidencia"]["cadenas"]
    assert it["estado"] == FALLA and it["piezas"] == [c["id"]] == it["evidencia"]["a_mano"]
    assert c["tipo"] == "insert_component" and c["ref"] == "CADENA-ASA40-1"
    assert "create_chain" in it["detalle"] and "create_hoist_chain" in it["detalle"]


def _placa_sobre(d, guarda: str) -> str:
    """Una placa de identificación atornillada SÓLO a `guarda`, por fuera: la guarda pasa a ser
    «apoyo de» ella (la placa queda un salto más lejos del piso) y la placa no es candidata."""
    g = _id(d, guarda)
    bb = d.scene[g].shape.bounding_box()
    x = (bb.min.X - 2.5) if (bb.min.X + bb.max.X) / 2 < 0 else (bb.max.X + 2.5)
    p = _caja(d, f"Placa de identificación ({guarda[-12:]})", 2, 80, 50, x,
              (bb.min.Y + bb.max.Y) / 2, (bb.min.Z + bb.max.Z) / 2)
    d.execute("fasten", {"name": f"f_placa_{len(d.fasteners)}", "a": p, "b": g, "kind": "perno",
                         "size": "M5", "qty": 2})
    return g


def test_la_guarda_que_es_apoyo_dice_si_tambien_tapa_un_peligro():
    """D6: la guarda del tambor de cola sostiene una placa: sigue siendo necesaria por la sujeción
    («es un apoyo de»), pero las sondas sin ella (la placa queda en su lugar) llegan a la cuña de cola y la
    evidencia lo dice (`tambien_tapa`); la tapa del tensor, que no resguarda nada (sobra en el
    testigo), con su placa es `solo_apoyo`. Se prueba cada una sola (la voraz entera de la faja
    tarda ~35 s)."""
    from apolo.services.calidad_seguridad import analisis, controles_f3
    from apolo.services.calidad_sobrantes import Prueba, _tornilleria

    doc = _base("faja")
    cola = _placa_sobre(doc, "Faja de banda · Guarda del tambor de cola")
    tapa = _placa_sobre(doc, "Faja de banda · Tapa del tensor (1)")
    ctx = pp.Contexto()
    controles_f3(doc, contexto=ctx, electrico=False)
    an = analisis(doc, ctx)
    hardware, jb = _tornilleria(doc, an["dc"]["piezas"])
    prueba = Prueba(doc, an, ctx.una_vez("f3.sondas", lambda: None), hardware, jb)
    m = prueba.probar(cola)
    assert m["control"] == "sujeción" and m["detalle"].startswith("es un apoyo de"), m
    assert "Tambor de cola" in m["tambien_tapa"] and "solo_apoyo" not in m, m
    m = prueba.probar(tapa)
    assert m["control"] == "sujeción" and m.get("solo_apoyo") is True, m
    assert prueba.quitadas == set() and prueba.etapa["apoyo"] == 2
