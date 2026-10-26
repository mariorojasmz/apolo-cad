"""La memoria de cálculo del aire y la puerta de entrega (plan V8.9 D9, D10; F4).

Se verifica:
  - un caso resuelto A MANO por regla, con su cita, contra lo que la memoria imprime: pandeo
    (Euler), energía de impacto y consumo (isoterma con volúmenes muertos y tubos, ISO 8778);
  - la memoria del caso canónico (el empujador de `neumatica_escena.py`) con sus cifras: fuerza,
    relación de carga, consumo, caudal pico, tiempo de carrera, pandeo, impacto, FRL y demanda;
  - con un escenario VIGENTE, la memoria toma el tiempo de carrera y la velocidad MEDIDOS en la
    co-simulación: sin regulador el vástago llega a ~4 m/s y la energía al fin de carrera la
    pone «NO CONFORME» (lo que la F3 dejó anunciado);
  - la puerta de entrega ROJA con un cilindro que pandea.
"""

from __future__ import annotations

import math

import pytest
from neumatica_escena import empujador, escenario

from apolo.library.neumatica import calculo as K
from apolo.services import escenarios as E
from apolo.services.memoria_reglas import reglas_memoria, veredicto_memoria

P_ATM = 1.01325  # ISO 2533 (la memoria lo declara como hipótesis)
SERVICIO = {"carrera_mm": 200, "velocidad_m_s": 0.5, "masa_kg": 2.0, "fuerza_N": 50, "ciclos_min": 20}


def aire(rules: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in rules:
        if r.get("medio") == "aire":
            out.setdefault(r["regla"], []).append(r)
    return out


@pytest.fixture(scope="module")
def canonico():
    d, cid = empujador(servicio=SERVICIO)
    d.set_requirements({"fugas_aire_pct": 10})
    return d, cid


# ── casos a mano, uno por regla ─────────────────────────────────────────────────────────────


def test_pandeo_a_mano_euler():
    """Ø16/6 (ISO 6432) con 400 mm libres, caso 1 (empotrado-libre, K = 2), a 6 bar.
    I = π·6⁴/64 = 63,62 mm⁴ · Lk = 800 mm · Pcr = π²·E·I/Lk² con E = 210 000 N/mm² (EN 1993-1-1
    § 3.2.6) = 206,0 N; el pistón empuja p·A = 0,6·π·16²/4 = 120,6 N → FS = 1,71 < 3: pandea."""
    I = math.pi * 6 ** 4 / 64
    pcr = math.pi ** 2 * 210000 * I / 800 ** 2
    assert pcr == pytest.approx(206.0, abs=0.1)
    F = 0.6 * math.pi * 16 ** 2 / 4
    r = K.pandeo_vastago(6, 400, 1, F)
    assert r["valor"]["Pcr_N"] == pytest.approx(pcr) and r["valor"]["fs"] == pytest.approx(1.708, abs=1e-3)
    assert r["estado"] == "error" and r["calc"]["formula"] == "Pcr = π²·E·I/(K·L)²"


def test_energia_de_impacto_a_mano():
    """Ø32 ISO 15552 (ficha Festo DSBC-32: 0,110 kg + 0,0009 kg/mm de masa móvil; 2,3 J admisibles
    de la amortiguación, manual SMC C96) con 200 mm y 2 kg de carga a 0,5 m/s:
    m = 0,110 + 0,18 + 2 = 2,29 kg · E = ½·m·v² = 0,2863 J ≤ 2,3 J. A 1,5 m/s: 2,576 J > 2,3 J."""
    m = 0.110 + 0.0009 * 200 + 2.0
    assert K.energia_impacto(m, 0.5, 2.3)["valor"]["E_J"] == pytest.approx(0.2863, abs=1e-4)
    assert K.energia_impacto(m, 1.5, 2.3)["estado"] == "error"
    assert 0.5 * m * 1.5 ** 2 == pytest.approx(2.5763, abs=1e-4)


def test_consumo_a_mano_isoterma():
    """Ø32/12 de 200 mm a 6 bar, con los volúmenes muertos de la ficha (A 4,0 · B 3,5 cm³) y 1 m
    de tubo PU Ø4 interior por cámara (12,566 cm³). Por cámara, ΔV_ANR = ((p_atm + p)·(V0 + A·s)
    − p_atm·V0)/p_ANR (balance isotermo; aire de referencia ANR de ISO 8778: 100 kPa, 20 °C):
    avance 1,2275 NL, retroceso 1,0658 NL → 2,2933 NL por ciclo; a 20 ciclos/min, 45,87 NL/min."""
    tubo = math.pi * 4 ** 2 / 4 * 1.0  # mm²·m = cm³
    A, Ab = math.pi * 32 ** 2 / 4, math.pi * (32 ** 2 - 12 ** 2) / 4
    av = ((P_ATM + 6) * (4.0 + tubo + A * 200 / 1000) - P_ATM * (4.0 + tubo)) / 1.0 / 1000
    rt = ((P_ATM + 6) * (3.5 + tubo + Ab * 200 / 1000) - P_ATM * (3.5 + tubo)) / 1.0 / 1000
    assert (av, rt) == (pytest.approx(1.2275, abs=1e-4), pytest.approx(1.0658, abs=1e-4))
    r = K.consumo_ciclo(32, 12, 200, 6, V_muerto_A_cm3=4.0, V_muerto_B_cm3=3.5, V_tubo_A_cm3=tubo,
                        V_tubo_B_cm3=tubo, ciclos_min=20)
    assert r["valor"]["ciclo_NL"] == pytest.approx(av + rt) == pytest.approx(2.2933, abs=1e-4)
    assert r["valor"]["NL_min"] == pytest.approx(45.87, abs=0.01)
    assert "ISO 8778" in r["calc"]["norma"]


def test_relacion_de_carga():
    assert K.relacion_carga(50, 482.5, 434.3)["estado"] == "ok"
    r = K.relacion_carga(400, 482.5, 434.3)  # η = 0,83 > 0,7 (criterio de diseño)
    assert r["estado"] == "aviso" and any("criterio de diseño" in h for h in r["hipotesis"])
    assert K.relacion_carga(450, 482.5, 434.3)["estado"] == "error"  # pasa la fuerza efectiva
    assert K.relacion_carga(400, 482.5, 434.3, tope=0.9)["estado"] == "ok"  # tope de la ficha


# ── la memoria del caso canónico ────────────────────────────────────────────────────────────


def test_la_memoria_del_empujador_con_sus_cifras(canonico):
    d, _ = canonico
    rules, _req = reglas_memoria(d)
    a = aire(rules)
    assert list(a) == ["fuerza del cilindro", "relación de carga", "consumo de aire", "caudal pico de la válvula",
                       "tiempo de carrera", "pandeo del vástago", "energía al fin de carrera",
                       "caudal de la unidad de mantenimiento", "demanda de aire"]
    assert all(r["estado"] == "ok" for v in a.values() for r in v), [
        (r["regla"], r["detalle"]) for v in a.values() for r in v if r["estado"] != "ok"]
    assert all(r["calc"]["norma"] and r["calc"]["formula"] for v in a.values() for r in v)
    (f,) = a["fuerza del cilindro"]
    assert f["calc"]["titulo"].startswith("-MM1 · Fuerza")
    assert "avance 483 N (434 N efectiva) · retroceso 415 N (373 N efectiva)" == f["calc"]["resultado"]
    (rc,) = a["relación de carga"]
    assert rc["calc"]["sustitucion"] == "η = 50 / 483 = 0.10"
    (c,) = a["consumo de aire"]
    assert "2.293 NL por ciclo" in c["calc"]["resultado"] and "45.9 NL/min a 20 ciclos/min" in c["calc"]["resultado"]
    (q,) = a["caudal pico de la válvula"]
    pico = math.pi * 32 ** 2 / 4 * 1e-6 * 0.5 * 60000 * (P_ATM + 6)  # A·v·(p_abs/p_ANR) en NL/min
    assert q["calc"]["resultado"].endswith(f"contra {pico:.0f} NL/min de pico") and "-QM2" in q["elementos"]
    (t,) = a["tiempo de carrera"]
    # cota de régimen con el escape de la G1/8 (C = 2,67 del Qn de Festo): v = C·p_ANR / A_escape
    C = 2.6715
    assert t["calc"]["resultado"].startswith(
        f"avance {C * 1000 / (math.pi * (32 ** 2 - 12 ** 2) / 4):.2f} m/s → 0.052 s · retroceso "
        f"{C * 1000 / (math.pi * 32 ** 2 / 4):.2f} m/s → 0.060 s")
    assert any("sin escenario vigente" in h for h in t["hipotesis"])
    (p,) = a["pandeo del vástago"]
    assert p["calc"]["fs"] == pytest.approx(27.3, abs=0.1)  # Ø12, 200 mm, caso 1: Pcr = 13 185 N
    (e,) = a["energía al fin de carrera"]
    assert e["calc"]["sustitucion"] == "E = ½·2.29·0.5² = 0.286 J"  # masa móvil de la ficha Festo DSBC-32
    (dm,) = a["demanda de aire"]
    assert dm["calc"]["resultado"].startswith("50.5 NL/min") and "fugas = 10 %" in dm["hipotesis"][0]


def test_sin_servicio_ni_fugas_la_memoria_dice_lo_que_omite():
    d, _ = empujador()
    a = aire(reglas_memoria(d)[0])
    assert list(a) == ["fuerza del cilindro", "alcance de la memoria del aire"]
    assert "-MM1 sin `servicio`" in a["alcance de la memoria del aire"][0]["detalle"]
    d2, _ = empujador(servicio={k: v for k, v in SERVICIO.items() if k != "velocidad_m_s"})
    a2 = aire(reglas_memoria(d2)[0])
    assert "energía al fin de carrera" not in a2 and "caudal pico de la válvula" not in a2
    (dm,) = a2["demanda de aire"]
    assert dm["estado"] == "aviso" and "fugas_aire_pct" in dm["recomendacion"]
    assert "sin velocidad" in a2["alcance de la memoria del aire"][0]["detalle"]


def test_sin_aire_la_memoria_no_cambia():
    from apolo.doc.document import Document

    d = Document("t")
    d.execute("create_box", {"name": "Placa", "width": 100, "depth": 100, "height": 10})
    assert aire(reglas_memoria(d)[0]) == {}


# ── con la co-simulación vigente ────────────────────────────────────────────────────────────


def test_con_escenario_vigente_la_memoria_usa_lo_medido(canonico):
    pytest.importorskip("mujoco")
    from apolo.cosim.planificador import correr
    from apolo.cosim.veredicto import evaluar
    from apolo.services.cosim_snapshot import snapshot_cosim

    d, cid = canonico
    esc = escenario(cid)
    E.poner(d, "empuja", esc)
    snap = snapshot_cosim(d, esc)
    res = correr(snap)
    comp = E.resultado_compacto(evaluar(snap.escenario.aserciones, res), res, firma=E.firma_documento(d),
                                hash_esc=E.hash_escenario(esc), simulacion=None)
    mm1 = comp["aire"]["cilindros"]["-MM1"]
    assert mm1["x_max_mm"] == pytest.approx(200, abs=2.5) and 0 < mm1["t_avance_s"] < 0.2
    assert mm1["v_max_m_s"] > 2.0 and mm1["t_retroceso_s"] > 0  # sin regulador: lo que da el escape
    assert 1.6 < comp["aire"]["frl"]["-AZ1"]["consumo_NL"] < 2.6
    assert E.guardar_resultado(d, "empuja", comp)
    try:
        a = aire(reglas_memoria(d)[0])
        (t,) = a["tiempo de carrera"]
        assert f"co-simulación «empuja»: avance {mm1['t_avance_s']:.3f} s" in t["calc"]["resultado"]
        (e,) = a["energía al fin de carrera"]
        # la velocidad medida pasa la declarada (0,5 m/s): la memoria toma la medida y la amortiguación
        # de 2,3 J no alcanza → NO CONFORME (la regla que la F3 anunció)
        assert e["estado"] == "error" and any("medida en el escenario «empuja»" in h for h in e["hipotesis"])
        assert e["calc"]["sustitucion"].startswith(f"E = ½·2.29·{mm1['v_max_m_s']:g}²")
        ver = veredicto_memoria(d)
        assert ver["veredicto"] == "NO CONFORME" and any(x["regla"] == "energía al fin de carrera" for x in ver["errores"])
        # vencido (otro escenario con el mismo nombre): ya no cuenta
        E.poner(d, "empuja", {**esc, "duracion_s": 2.5})
        (t2,) = aire(reglas_memoria(d)[0])["tiempo de carrera"]
        assert any("sin escenario vigente" in h for h in t2["hipotesis"])
    finally:
        E.quitar(d, "empuja")


# ── la puerta de entrega ────────────────────────────────────────────────────────────────────


def _bloqueantes(d) -> list[dict]:
    from apolo.library.delivery import delivery_report
    from apolo.services.delivery_inputs import delivery_inputs

    r = delivery_report(**delivery_inputs(d, expand=lambda ids: ids))
    return r["veredicto"], r["bloqueantes"]


def test_la_puerta_es_roja_con_un_cilindro_que_pandea():
    """Ø32/12 con 1500 mm de vástago libre, caso 1: Pcr = π²·210 000·1017,9/3000² = 234 N contra
    483 N del pistón (FS 0,49): error del ERC del aire → ROJO, como uno eléctrico (V8.1 D11)."""
    d, _ = empujador(servicio={"carrera_mm": 200, "largo_libre_mm": 1500})
    veredicto, bloq = _bloqueantes(d)
    pandeo = [b for b in bloq if b["regla"] == "eléctrico · pandeo del vástago"]
    assert veredicto == "ROJO" and pandeo and pandeo[0]["piezas"] == ["-MM1"]
    assert "FS = 0.49" in pandeo[0]["detalle"]
    _v, bloq_ok = _bloqueantes(empujador(servicio={"carrera_mm": 200})[0])
    assert not [b for b in bloq_ok if "pandeo" in b["regla"]]
