"""La colocación del tablero (plan V8.5 F1a: D2, D8, A1, A4, A7, A13): `library/electrico/colocacion*.py`.

- El circuito de la faja piloto (`tests/data/tablero_piloto.json`, congelado de la F0) entra en el
  gabinete de 500 × 400 gracias a la columna de placa del variador (A1), con cada fila de riel
  ≥ 20 % libre (A13) y los mandos de puerta fuera de lo profundo (A7); en el de 600 × 400 no
  entra (es angosto para la columna) y el error dice que con «auto» sí.
- Lo mismo sale del catálogo real (`colocacion_catalogo.py`).
- Casos sintéticos: no entra, «auto» que sube de talla, ninguno alcanza, filas que se parten por
  la reserva, accesorios pegados, la puerta sin lugar, el fondo, y los overrides (D8) válidos e
  inválidos.
"""

from __future__ import annotations

import json
import re
from itertools import combinations
from pathlib import Path

import pytest

from apolo.library.electrico.colocacion import (
    Acople,
    Aparato,
    ColocacionError,
    Gabinete,
    Reglas,
    clase_de,
    colocar,
)
from apolo.library.electrico.colocacion_catalogo import aparatos_desde_catalogo, gabinetes_del_catalogo

PILOTO = json.loads((Path(__file__).parent / "data" / "tablero_piloto.json").read_text(encoding="utf-8"))


def _del_fixture() -> tuple[list[Aparato], list[Gabinete]]:
    """Los aparatos del piloto con las cajas congeladas (mismo mapeo que el adaptador)."""
    aps = []
    for d in PILOTO["dispositivos"]:
        f = PILOTO["fichas"][d["ref"]]
        dx, dy, dz = f["caja"]
        ancho, alto, fondo = (dx, dy, dz) if f["familia"] == "seta_emergencia" else (dx, dz, dy)
        delante = 0.0
        if f["puerta"]:
            delante, fondo = f["puerta"]
        n = d.get("cantidad", 1) if f["bornera"] else 1
        aps.append(Aparato(d["designacion"], d["ref"], f["montaje"], ancho * n, alto, fondo,
                           clase_de(f["tipo"], f["bornera"]), f["funcion"], f["simbolo"], delante,
                           pieza=d.get("pieza")))
    gabs = [Gabinete(ref, g["placa_ancho"], g["placa_alto"], g["fondo_util"], g["espesor_puerta"],
                     g["bisagra"]) for ref, g in PILOTO["gabinetes"].items()]
    return aps, gabs


def _sin_choques(lay, r: Reglas | None = None) -> None:
    """Nada se pisa en 3D; cada mando de puerta deja la holgura sobre lo de la placa; todo en la placa."""
    r = r or Reglas()
    gab = {g.ref: g for g in _del_fixture()[1] + GABS}[lay.gabinete]
    cajas = [(a.u0, a.v0, a.w0, a.u0 + a.ancho, a.v0 + a.alto, a.w1, a.designacion) for a in lay.aparatos]
    for x, y in combinations(cajas, 2):
        assert not all(x[i] < y[i + 3] - 1e-6 and y[i] < x[i + 3] - 1e-6 for i in range(3)), (x[6], y[6])
    placa = [a for a in lay.aparatos if a.zona == "placa"]
    for p in (a for a in lay.aparatos if a.zona == "puerta"):
        for q in placa:
            if q.solapa(p.u0, p.v0, p.u0 + p.ancho, p.v0 + p.alto):
                assert p.w0 - q.w1 >= r.holgura_puerta_mm - 1e-6, (p.designacion, q.designacion)
        for k in lay.canaletas:
            if p.u0 < k.u1 and k.u0 < p.u0 + p.ancho and p.v0 < k.v1 and k.v0 < p.v0 + p.alto:
                assert p.w0 - r.canaleta_alto_mm >= r.holgura_puerta_mm - 1e-6, p.designacion
    for a in lay.aparatos:  # todo dentro de la placa útil y del fondo
        assert -1e-6 <= a.u0 and a.u0 + a.ancho <= gab.placa_ancho + 1e-6, a.designacion
        assert -1e-6 <= a.v0 and a.v0 + a.alto <= gab.placa_alto + 1e-6, a.designacion
        if a.zona == "placa":
            assert a.w1 <= gab.fondo_util - r.holgura_puerta_mm + 1e-6, a.designacion


# ── la faja piloto ────────────────────────────────────────────────────────────────────────
def test_la_faja_piloto_entra_en_el_500x400_con_la_columna_de_placa():
    aps, gabs = _del_fixture()
    lay = colocar(aps, "auto", gabs)
    assert lay.gabinete == "TABLERO-5040" and lay.avisos == ()
    assert lay.de("-T2").fila == "columna" and lay.de("-T2").pieza == "c1377"  # A1, A9 pasa
    assert [f.nombre for f in lay.filas] == ["alimentacion", "control", "bornera"]
    assert all(f.riel_mm == 235 and f.reserva >= 0.20 for f in lay.filas)  # A13
    control = next(f for f in lay.filas if f.nombre == "control")
    assert control.ocupado_mm == 182 and control.reserva == pytest.approx(0.2255, abs=1e-3)
    assert [a.designacion for a in lay.aparatos if a.fila == "alimentacion"] == ["-F1", "-F2"]
    assert {a.designacion for a in lay.aparatos if a.zona == "puerta"} == {
        "-Q1", "-S0", "-S1", "-S2", "-H1", "-H2"}
    # el seccionador arriba y lejos de la bisagra (izquierda): la celda de arriba a la derecha
    q1 = lay.de("-Q1")
    assert q1.u0 + q1.ancho / 2 == 450 - 40 and q1.v0 + q1.alto / 2 == 350 - 60
    _sin_choques(lay)
    assert lay.supuestos["reserva"] == 0.2 and lay.supuestos["paso_puerta_mm"] == [70, 80]
    assert colocar(aps, "TABLERO-5040", gabs) == lay  # determinista; la ref fija da lo mismo


def test_en_el_600x400_no_entra_y_dice_que_con_auto_si():
    aps, gabs = _del_fixture()
    with pytest.raises(ColocacionError) as exc:
        colocar(aps, "GAB-6040", gabs)
    msg = str(exc.value)
    assert msg.startswith("no entra en GAB-6040: ")
    assert "-K1 (110 mm con sus accesorios) no entra en un riel de 135 mm" in msg
    assert msg.endswith("con «auto» entra en TABLERO-5040")


def test_el_catalogo_da_lo_mismo_que_el_fixture():
    from apolo.library.catalog import CATALOG, build_component

    def medir(ref):
        bb = build_component(ref)[0].bounding_box()
        return bb.size.X, bb.size.Y, bb.size.Z

    aps, avisos = aparatos_desde_catalogo(PILOTO["dispositivos"], CATALOG, medir=medir)
    fijos, gabs = _del_fixture()
    def foto(lista):
        return [(a.designacion, round(a.ancho, 1), round(a.alto, 1), round(a.fondo, 1),
                 a.delante, a.clase, a.montaje, a.funcion, a.simbolo, a.pieza) for a in lista]

    assert avisos == [] and foto(aps) == foto(fijos)
    real, congelado = colocar(aps, "auto", gabinetes_del_catalogo(CATALOG)), colocar(fijos, "auto", gabs)
    assert real.gabinete == congelado.gabinete
    assert [(a.designacion, round(a.u0, 1), round(a.v0, 1)) for a in real.aparatos] == [
        (a.designacion, round(a.u0, 1), round(a.v0, 1)) for a in congelado.aparatos]


# ── casos sintéticos ──────────────────────────────────────────────────────────────────────
CHICO = Gabinete("CHICO", 300, 250, 160, 1.5, "izquierda")
MEDIO = Gabinete("MEDIO", 450, 350, 160, 1.5, "izquierda")
GRANDE = Gabinete("GRANDE", 550, 750, 205, 1.5, "derecha")
GABS = [GRANDE, CHICO, MEDIO]  # desordenados a propósito: «auto» va de menor a mayor placa


def ap(des, ancho=36.0, alto=90.0, fondo=75.0, montaje="din", clase="alimentacion", funcion="F",
       **kw) -> Aparato:
    return Aparato(des, kw.pop("ref", "REF"), montaje, ancho, alto, fondo, clase, funcion, **kw)


def itms(n: int) -> list[Aparato]:
    return [ap(f"-F{i}", ancho=54) for i in range(1, n + 1)]


def test_una_fila_que_pasa_la_reserva_sigue_en_otra_de_su_clase():
    lay = colocar(itms(6), "MEDIO", GABS)  # riel 400, caben 320 → 5 de 54 (270) y 1
    assert [(f.nombre, f.ocupado_mm) for f in lay.filas] == [("alimentacion", 270), ("alimentacion 2", 54)]
    assert lay.de("-F6").fila == "alimentacion 2" and lay.de("-F6").v0 < lay.de("-F1").v0
    _sin_choques(lay)


def test_con_ref_fija_no_entra_dice_cuanto_falta_y_auto_sube_de_talla():
    with pytest.raises(ColocacionError, match=r"^no entra en CHICO: las filas de riel no entran en "
                                              r"alto: faltan \d+ mm de placa \(250 de alto útil\); "
                                              r"con «auto» entra en MEDIO$"):
        colocar(itms(9), "CHICO", GABS)
    lay = colocar(itms(9), "auto", GABS)
    assert lay.gabinete == "MEDIO" and lay.avisos[0].startswith("auto: no entra en CHICO: ")


def test_auto_sin_gabinete_que_alcance():
    with pytest.raises(ColocacionError, match=r"no entra en ningún gabinete del catálogo: CHICO: .*"
                                              r"\| MEDIO: .*\| GRANDE: .*reparte los aparatos"):
        colocar(itms(200), "auto", GABS)


def test_gabinete_desconocido_sugiere():
    with pytest.raises(ColocacionError, match=r"gabinete «MEDO» sin interior.*¿Quisiste decir: MEDIO"):
        colocar(itms(1), "MEDO", GABS)


def test_lo_que_sale_de_mas_de_la_placa():
    with pytest.raises(ColocacionError, match=r"-F1 sale 158 mm de la placa y el fondo útil deja 150"):
        colocar([ap("-F1", fondo=150.5)], "MEDIO", GABS)


def test_la_columna_de_placa_y_las_clases_por_fila():
    aps = [ap("-T1", 140, 160, 145, "placa", "potencia", "T"), ap("-K1", 110, 100, 75, clase="control", funcion="K"),
           ap("-Q2", 45, 77, 93, clase="potencia", funcion="Q"), ap("-F1"), ap("-X1", 12.4, 42.5, 47, clase="bornera", funcion="X")]
    lay = colocar(aps, "GRANDE", GABS)
    assert lay.de("-T1").fila == "columna" and lay.de("-T1").u0 == 25
    assert [f.nombre for f in lay.filas] == ["alimentacion", "potencia", "control", "bornera"]
    assert all(r.u0 == 25 + 140 + 25 for r in lay.rieles)  # las filas, a la derecha de la columna
    v = [lay.de(d).v0 for d in ("-F1", "-Q2", "-K1", "-X1")]
    assert v == sorted(v, reverse=True)  # de arriba abajo
    _sin_choques(lay)


def test_los_accesorios_van_pegados_a_su_aparato():
    cont = ap("-Q3", 45, 77, 93, clase="potencia", funcion="Q", simbolo="contactor_3p")
    rt = ap("-F3", 45, 66, 70, clase="potencia", acopla=Acople(("contactor_3p",), "abajo"))
    aux = ap("-Q3A", 45, 40, 40, funcion="Q", acopla=Acople(("contactor_3p",), "frente"))
    lay = colocar([cont, rt, aux], "GRANDE", GABS)
    c, t, a = lay.de("-Q3"), lay.de("-F3"), lay.de("-Q3A")
    assert t.acoplado_a == "-Q3" and t.v0 + t.alto == pytest.approx(c.v0) and t.u0 == c.u0
    assert a.acoplado_a == "-Q3" and a.w0 == c.w1 and a.w1 == c.w1 + 40  # por el frente
    assert [f.ocupado_mm for f in lay.filas] == [45]  # no ocupan riel propio
    _sin_choques(lay)


def test_un_accesorio_ambiguo_pide_el_override():
    c1 = ap("-Q1", 45, 77, 93, clase="potencia", simbolo="contactor_3p")
    c2 = ap("-Q2", 45, 77, 93, clase="potencia", simbolo="contactor_3p")
    rt = ap("-F9", 45, 66, 70, acopla=Acople(("contactor_3p",), "abajo"))
    with pytest.raises(ColocacionError, match=r'-F9 \(REF\): no sé a cuál va pegado \(-Q1, -Q2\); '
                                              r'pásalo en overrides: \{"-F9": \{"acopla": "-Q1"\}\}'):
        colocar([c1, c2, rt], "GRANDE", GABS)
    lay = colocar([c1, c2, rt], "GRANDE", GABS, overrides={"-F9": {"acopla": "-Q2"}})
    assert lay.de("-F9").acoplado_a == "-Q2"
    with pytest.raises(ColocacionError, match=r"no tiene ninguno"):
        colocar([rt], "GRANDE", GABS)


def test_la_puerta_sin_lugar_dice_cuanto_falta():
    """A7: un aparato hondo cubre toda la puerta; el pulsador no tiene celda con holgura."""
    gab = Gabinete("G", 200, 200, 160, 1.5, "izquierda")
    hondo = ap("-T1", 150, 150, 145, "placa", "potencia", "T")
    puls = ap("-S1", 30, 30, 50, "puerta", funcion="S")
    with pytest.raises(ColocacionError, match=r"-S1: no hay lugar en la puerta sin chocar con lo de "
                                              r"la placa; la mejor celda deja lo de detrás \(50 mm\) "
                                              r"sobre -T1 y faltan 44 mm de fondo \(holgura 10\)"):
        colocar([hondo, puls], "G", [gab])
    lay = colocar([ap("-T1", 150, 150, 100, "placa", "potencia", "T"), puls], "G", [gab])
    assert lay.de("-S1").zona == "puerta"


def test_la_puerta_empieza_lejos_de_la_bisagra():
    puls = [ap(f"-S{i}", 30, 30, 50, "puerta", funcion="S") for i in (1, 2)]
    izq = colocar(puls, "MEDIO", GABS)
    der = colocar(puls, "GRANDE", GABS)
    assert izq.de("-S1").u0 > izq.de("-S2").u0 and izq.de("-S1").u0 + 15 == 450 - 40
    assert der.de("-S1").u0 < der.de("-S2").u0 and der.de("-S1").u0 + 15 == 40


# ── overrides (D8) ────────────────────────────────────────────────────────────────────────
def test_override_de_fila_y_orden():
    aps = itms(2) + [ap("-K1", 110, 100, 75, clase="control", funcion="K")]
    lay = colocar(aps, "MEDIO", GABS, overrides={"-F2": {"fila": 2, "orden": 1}})
    assert [a.designacion for a in sorted(lay.aparatos, key=lambda a: a.u0) if a.fila == "control"] == ["-F2", "-K1"]
    lay = colocar(aps, "MEDIO", GABS, overrides={"-F2": {"fila": "control"}, "-F1": {"orden": 1}})
    assert lay.de("-F2").fila == "control"
    lay = colocar(itms(3), "MEDIO", GABS, overrides={"-F3": {"orden": 1}})
    assert sorted(lay.aparatos, key=lambda a: a.u0)[0].designacion == "-F3"


def test_override_de_posicion_fija():
    lay = colocar(itms(2), "MEDIO", GABS, overrides={"-F2": {"posicion": {"u": 300, "v": 30}}})
    f2 = lay.de("-F2")
    assert (f2.u0, f2.v0, f2.fila) == (300, 30, "fija") and any(r.fila == "fija" for r in lay.rieles)
    with pytest.raises(ColocacionError, match=r"-F2 en \{u: 30, v: 230\} se solapa con -F1"):
        colocar(itms(2), "MEDIO", GABS, overrides={"-F2": {"posicion": {"u": 30, "v": 230}}})
    with pytest.raises(ColocacionError, match=r"sale de la placa útil \(450×350\)"):
        colocar(itms(2), "MEDIO", GABS, overrides={"-F2": {"posicion": {"u": 420, "v": 30}}})


MALOS = [
    ({"-F9": {"fila": 1}}, r"override «-F9»: no hay ese aparato en el tablero; aparatos: -F1, -F2, -S1\..*"
                           r"¿Quisiste decir: -F1"),
    ({"-F1": {"filas": 1}}, r"override «-F1»: clave desconocida «filas».*¿Quisiste decir: fila"),
    ({"-F1": {}}, r"override «-F1»: se espera un mapa"),
    ({"-F1": {"fila": 0}}, r"override «-F1»\.fila: un n\.º de fila ≥ 1 o una clase"),
    ({"-F1": {"fila": 5}}, r"override «-F1»\.fila 5: el tablero tiene 1 fila\(s\) de riel \(alimentacion\)"),
    ({"-S1": {"fila": 1}}, r"override «-S1»\.fila: sólo un aparato de riel cambia de fila"),
    ({"-F1": {"orden": "1"}}, r"override «-F1»\.orden: se espera un entero ≥ 1"),
    ({"-F1": {"posicion": {"x": 1, "y": 2}}}, r"override «-F1»\.posicion: se espera \{u, v\}"),
    ({"-F1": {"acopla": "-F2"}}, r"override «-F1»\.acopla: «-F1» \(REF\) no es un accesorio"),
    ({"-F1": {"fila": 1, "posicion": {"u": 1, "v": 2}}}, r"override «-F1»\.posicion: va sola"),
]


@pytest.mark.parametrize("overrides,mensaje", MALOS)
def test_override_invalido(overrides, mensaje):
    aps = itms(2) + [ap("-S1", 30, 30, 50, "puerta", funcion="S")]
    with pytest.raises(ColocacionError) as exc:
        colocar(aps, "MEDIO", GABS, overrides=overrides)
    assert re.search(mensaje, str(exc.value)), str(exc.value)


def test_designaciones_repetidas_y_montaje_de_campo():
    with pytest.raises(ColocacionError, match=r"designaciones repetidas en el tablero: -F1"):
        colocar([ap("-F1"), ap("-F1")], "MEDIO", GABS)
    with pytest.raises(ColocacionError, match=r"-M1: montaje «campo» no va dentro del tablero"):
        ap("-M1", montaje="campo")


# ── el adaptador del catálogo ─────────────────────────────────────────────────────────────
def test_el_adaptador_salta_el_gabinete_y_rechaza_lo_de_campo():
    from apolo.library.catalog import CATALOG

    aps, avisos = aparatos_desde_catalogo([{"designacion": "-U1", "ref": "GAB-6040"},
                                           {"designacion": "-X1", "ref": "BORNE-PASO-2.5", "cantidad": 4}],
                                          CATALOG)
    assert avisos == ["-U1 (GAB-6040) es el gabinete: no se coloca dentro de sí mismo"]
    assert [(a.designacion, a.ancho, a.clase) for a in aps] == [("-X1", pytest.approx(20.8), "bornera")]
    with pytest.raises(ColocacionError, match=r"-M1 \(MOTOR-075\) es de campo .* cámbiale la `ubicacion`"):
        aparatos_desde_catalogo([{"designacion": "-M1", "ref": "MOTOR-075"}], CATALOG)
    with pytest.raises(ColocacionError, match=r"«ITM-C16» no es una ref eléctrica.*ITM-C16-3P"):
        aparatos_desde_catalogo([{"designacion": "-F1", "ref": "ITM-C16"}], CATALOG)
    # la seta no es una caja: sin `medir` no hay cotas, y el error lista la ref a completar
    with pytest.raises(ColocacionError, match=r"sin cotas para colocar \(1\): ESTOP-40; completa"):
        aparatos_desde_catalogo([{"designacion": "-S0", "ref": "ESTOP-40"}], CATALOG)


def test_un_mando_de_puerta_sin_su_fondo_partido_no_se_coloca():
    from dataclasses import replace

    from apolo.library.catalog import CATALOG

    cat = dict(CATALOG)
    cat["PULS-22-VERDE-NA"] = replace(CATALOG["PULS-22-VERDE-NA"], tablero=None)
    with pytest.raises(ColocacionError, match=r"sin cotas para colocar \(1\): PULS-22-VERDE-NA;.*"
                                              r"`tablero\.puerta`"):
        aparatos_desde_catalogo([{"designacion": "-S1", "ref": "PULS-22-VERDE-NA"},
                                 {"designacion": "-S2", "ref": "PULS-22-ROJO-NC"}], cat)


def test_los_gabinetes_del_catalogo_van_de_menor_a_mayor():
    from apolo.library.catalog import CATALOG

    assert [g.ref for g in gabinetes_del_catalogo(CATALOG)] == ["TABLERO-5040", "GAB-6040", "GAB-8060"]


def test_la_colocacion_es_pura():
    """D15: sin OCCT, sin catálogo y sin `Document` (por AST, también los imports perezosos)."""
    import ast

    carpeta = Path(__file__).resolve().parents[1] / "core" / "apolo" / "library" / "electrico"
    prohibidos = ("build123d", "OCP", "apolo.doc", "apolo.kernel", "apolo.library.catalog",
                  "apolo.commands", "apolo.services")
    for nombre in ("colocacion.py", "colocacion_modelo.py", "colocacion_puerta.py",
                   "colocacion_catalogo.py", "ficha_tablero.py"):
        arbol = ast.parse((carpeta / nombre).read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            mods = [a.name for a in nodo.names] if isinstance(nodo, ast.Import) else (
                [nodo.module or ""] if isinstance(nodo, ast.ImportFrom) and not nodo.level else [])
            for m in mods:
                assert not m.startswith(prohibidos), f"{nombre} importa {m}"
            if isinstance(nodo, ast.ImportFrom) and nodo.level:
                assert (nodo.module or "") not in ("catalog", "loader", "builders"), nombre
