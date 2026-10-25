"""La memoria de cálculo del AIRE (plan V8.9 D10, F4): una verificación con su bloque `calc` por
cálculo, en la forma de las reglas de la memoria (`services/memoria_reglas.py` las suma).

`reglas(c, cosim=, fugas_pct=)` sobre el `Circuito` (`lineas.py`), por cilindro:
  - **fuerza** teórica de avance y retroceso y la efectiva con la fricción de los sellos (y, con
    `servicio.fuerza_N`, la **relación de carga**);
  - **consumo** por ciclo en NL ANR (isoterma con los volúmenes muertos de la ficha y los tubos de
    sus líneas) y por minuto con `servicio.ciclos_min`;
  - **caudal pico** que pide a su velocidad contra lo que pasa su válvula con Δp = 1 bar;
  - **tiempo de carrera**: la cota de régimen a mano (escape sónico, v = C·p_ANR / A_escape) y,
    con un escenario VIGENTE que lo movió, el medido en la co-simulación;
  - **pandeo** del vástago y **energía** al fin de carrera;
y de la máquina: el **caudal del FRL** (todos los picos a la vez) y la **demanda de aire** con el
% de fugas que se declare (el dato para el compresor).

La velocidad de cada cilindro es la MEDIDA en la co-simulación vigente si la hay y pasa la
declarada (la física manda: un cilindro sin regulador va a lo que dé el escape), si no la
declarada en el servicio; sin ninguna, lo que la pide queda fuera del alcance (dicho).
Estados como en el ERC: «ok», «aviso», «error». Puro (biblioteca estándar).
"""

from __future__ import annotations

from . import calculo as K
from . import cilindros as Z
from .lineas import Circuito, tipo

ALCANCE = "alcance de la memoria del aire"


def _fila(regla: str, des: str, r: dict, detalle: str, *, hip: list[str] | None = None,
          recomendacion: str | None = None, elementos: list[str] | None = None,
          valor: dict | None = None) -> dict:
    """Una verificación de la memoria. `valor`: las cifras con que se escribió (por defecto las del
    cálculo): el panel «Neumática» del visor las escribe para la persona (V8.9 F6) sin rehacer
    la cuenta."""
    calc = dict(r["calc"])
    calc["titulo"] = f"{des} · {calc['titulo']}" if des else calc["titulo"]
    out = {"regla": regla, "estado": r["estado"], "detalle": detalle}
    if recomendacion:
        out["recomendacion"] = recomendacion
    out.update({"elementos": list(elementos if elementos is not None else ([des] if des else [])),
                "medio": "aire", "calc": calc, "hipotesis": list(hip if hip is not None else r["hipotesis"])})
    v = valor if valor is not None else r.get("valor")
    if v is not None:
        out["valor"] = dict(v)
    return out


def _velocidad(cil, sim: dict | None) -> tuple[float | None, list[str]]:
    """(velocidad para el caudal y el impacto, hipótesis de dónde sale). La medida es el PICO de
    todos los escenarios vigentes (`sim["pico"]`, también uno de falla: el peor caso); un `sim`
    plano (sin `pico`) se lee como antes."""
    v_dec = cil.servicio.get("velocidad_m_s")
    pico = (sim or {}).get("pico") or sim or {}
    v_sim = pico.get("v_max_m_s")
    if v_sim and (not v_dec or v_sim > v_dec):
        extra = f", sobre los {v_dec:g} m/s de régimen declarados" if v_dec else ""
        return v_sim, [f"velocidad máxima medida en el escenario «{pico['escenario']}»: {v_sim:g} m/s{extra} "
                       "(muestreada: el pico real puede ser algo mayor)"]
    if v_dec:
        return v_dec, [f"velocidad declarada en el servicio: {v_dec:g} m/s"]
    return None, []


def _fuerza(c, cil) -> list[dict]:
    p, hip = Z.p_trabajo(c, cil)
    r = K.fuerzas_de_ficha(cil.neumatico, p)
    v = r["valor"]
    out = [_fila("fuerza del cilindro", cil.designacion, r,
                 f"{cil.designacion} empuja {v['F_avance_N']:.0f} N ({v['F_avance_ef_N']:.0f} N efectivos) y tira "
                 f"{v['F_retroceso_N']:.0f} N ({v['F_retroceso_ef_N']:.0f} N efectivos) a {p:g} bar.",
                 hip=hip + r["hipotesis"], valor={**v, "p_bar": p})]
    rc = Z.relacion(c, cil)
    if rc is not None:
        e = rc["valor"]
        out.append(_fila("relación de carga", cil.designacion, rc,
                         f"{cil.designacion}: {e['F_req_N']:g} N a vencer con {e['F_teorica_N']:.0f} N teóricos: "
                         f"η = {e['eta']:.2f} (tope {e['tope']:g}).",
                         recomendacion=None if rc["estado"] == "ok" else
                         "Un cilindro de más Ø, más presión (dentro de la ficha) o menos carga."))
    return out


def _consumo(c, cil) -> tuple[dict, float]:
    s, f = cil.servicio, cil.neumatico
    m = f.modelo
    p, hip = Z.p_trabajo(c, cil)
    VA, hA = Z.volumen_tubos(c, cil, "A")
    VB, hB = Z.volumen_tubos(c, cil, "B") if m["efecto"] == "doble" else (0.0, [])
    r = K.consumo_ciclo(m["D_mm"], m["d_mm"], s["carrera_mm"], p, V_muerto_A_cm3=m["V_muerto_A_cm3"],
                        V_muerto_B_cm3=m["V_muerto_B_cm3"], V_tubo_A_cm3=VA, V_tubo_B_cm3=VB,
                        ciclos_min=s.get("ciclos_min"), simple_efecto=m["efecto"] != "doble")
    hip += r["hipotesis"] + hA + hB + [f"{k} de la ficha a confirmar" for k in f.a_confirmar if k.startswith("V_muerto")]
    if not s.get("ciclos_min"):
        hip.append("sin cadencia declarada (servicio.ciclos_min): sólo el consumo por ciclo")
    v = r["valor"]
    txt = f"{cil.designacion} gasta {v['ciclo_NL']:.3f} NL por ciclo"
    if "NL_min" in v:
        txt += f" ({v['NL_min']:.1f} NL/min a {s['ciclos_min']:g} ciclos/min)"
    return _fila("consumo de aire", cil.designacion, r, txt + ".", hip=hip), v["ciclo_NL"]


def _caudal_pico(c, cil, vel, hip_v) -> tuple[list[dict], float]:
    m = cil.neumatico.modelo
    p, hip = Z.p_trabajo(c, cil)
    A, _Ab, _a = K.areas(m["D_mm"], m["d_mm"])
    q = K.caudal_pico(A, vel, p)
    v, _regs = Z.hacia_valvula(c, cil, "A")
    if v is None:
        return [], q
    cau = v.neumatico.caudal
    r = K.verificar_caudal(f"{v.designacion} ({v.ref})", cau.C, cau.b, q, p, K.DP_CAUDAL_BAR, m=cau.m)
    r["calc"]["entradas"]["velocidad"] = f"{vel:g} m/s (llenando A, Ø{m['D_mm']:g})"
    h = hip + hip_v + r["hipotesis"] + list(cau.hipotesis) + [
        f"Δp = {K.DP_CAUDAL_BAR:g} bar: criterio de diseño, el punto del caudal nominal (6 → 5 bar)",
        "la cámara se llena a la presión de red mientras avanza (pico conservador)"]
    d = r["valor"]
    return [_fila("caudal pico de la válvula", cil.designacion, r,
                  f"{cil.designacion} pide {d['q_pico_NL_min']:.0f} NL/min a {vel:g} m/s y {v.designacion} pasa "
                  f"{d['q_disponible_NL_min']:.0f} NL/min con Δp = {K.DP_CAUDAL_BAR:g} bar.", hip=h,
                  recomendacion=None if r["estado"] == "ok" else
                  "Una válvula de más caudal (C), menos velocidad (regulador por el escape) o tubos y racores "
                  "más grandes.", elementos=[cil.designacion, v.designacion],
                  valor={**d, "valvula": v.designacion, "v_m_s": vel})], q


def _tiempo(c, cil, sim) -> list[dict]:
    s, m = cil.servicio, cil.neumatico.modelo
    if m["efecto"] != "doble":
        return []
    A, Ab, _a = K.areas(m["D_mm"], m["d_mm"])
    vB, rB = Z.hacia_valvula(c, cil, "B")
    vA, rA = Z.hacia_valvula(c, cil, "A")
    if vB is None or vA is None:
        return []
    CB, bB, hB = Z.c_escape(vB, rB)
    CA, bA, hA = Z.c_escape(vA, rA)
    _p, hp = Z.p_trabajo(c, cil)
    av = K.regimen(CB, Ab, s["carrera_mm"], b=bB)
    rt = K.regimen(CA, A, s["carrera_mm"], b=bA)
    r = dict(av)
    r["estado"] = "aviso" if "aviso" in (av["estado"], rt["estado"]) else "ok"
    calc = dict(av["calc"], titulo="Tiempo de carrera")
    calc["entradas"] = {**calc["entradas"], "retroceso": f"escapa A ({A:.1f} mm²) con C = {CA:.3g}"}
    res = (f"avance {av['valor']['v_m_s']:.2f} m/s → {av['valor']['t_s']:.3f} s · retroceso "
           f"{rt['valor']['v_m_s']:.2f} m/s → {rt['valor']['t_s']:.3f} s (cota de régimen)")
    hip = hp + list(dict.fromkeys(av["hipotesis"] + rt["hipotesis"] + hB + hA))
    detalle = f"{cil.designacion}: cota a mano {av['valor']['t_s']:.3f} s de avance y {rt['valor']['t_s']:.3f} s de retroceso"
    if sim and sim.get("t_avance_s") is not None:
        med = f"avance {sim['t_avance_s']:.3f} s"
        if sim.get("t_retroceso_s") is not None:
            med += f", retroceso {sim['t_retroceso_s']:.3f} s"
        res += f" · co-simulación «{sim['escenario']}»: {med}"
        detalle += f"; la co-simulación vigente «{sim['escenario']}» midió {med}"
        hip.append(f"co-simulación: {sim.get('medicion', '')}")
        if sim.get("x_max_mm") is not None and sim["x_max_mm"] < s["carrera_mm"] - 2:
            r["estado"] = "aviso"
            detalle += f" — pero llegó sólo a {sim['x_max_mm']:.0f} de {s['carrera_mm']:g} mm"
    else:
        hip.append("sin escenario vigente que mueva el cilindro: sólo la cota a mano (corre uno con simulate)")
    calc["resultado"] = res
    r["calc"] = calc
    valor = {"carrera_mm": s["carrera_mm"], "t_avance_s": av["valor"]["t_s"], "t_retroceso_s": rt["valor"]["t_s"],
             "v_avance_m_s": av["valor"]["v_m_s"], "v_retroceso_m_s": rt["valor"]["v_m_s"]}
    if sim and sim.get("t_avance_s") is not None:
        valor["medido"] = {k: sim[k] for k in ("escenario", "t_avance_s", "t_retroceso_s", "x_max_mm", "v_max_m_s")
                           if sim.get(k) is not None}
    return [_fila("tiempo de carrera", cil.designacion, r, detalle + ".", hip=hip,
                  elementos=[cil.designacion, vB.designacion], valor=valor)]


def _pandeo(c, cil) -> dict:
    r, hip, F, p, largo = Z.pandeo(c, cil)
    v = r["valor"]
    return _fila("pandeo del vástago", cil.designacion, r,
                 f"{cil.designacion}: el vástago Ø{cil.neumatico.modelo['d_mm']:g} con {largo:g} mm libres admite "
                 f"{v['F_adm_N']:.0f} N y el pistón empuja {F:.0f} N a {p:g} bar (FS = {v['fs']:.2f}).", hip=hip,
                 valor={**v, "F_N": F, "p_bar": p, "largo_mm": largo},
                 recomendacion=None if r["estado"] == "ok" else
                 "Un cilindro de vástago mayor, menos carrera libre, un montaje más rígido o una guía.")


def _impacto(cil, vel, hip_v) -> dict:
    s, m = cil.servicio, cil.neumatico.modelo
    masa = K.masa_movil_kg(m, s["carrera_mm"], s.get("masa_kg") or 0.0)
    r = K.energia_impacto(masa, vel, m["E_amortiguacion_J"])
    hip = hip_v + [f"masa móvil de la ficha ({m['masa_movil_base_kg']:g} kg + {m['masa_movil_por_mm_kg']:g} kg/mm) "
                   f"+ carga declarada ({s.get('masa_kg') or 0:g} kg)",
                   "llega a esa velocidad: la amortiguación no se simula, se verifica (V8.9 D3)"]
    hip += [f"{k} de la ficha a confirmar" for k in cil.neumatico.a_confirmar if k.startswith(("E_amort", "masa"))]
    d = r["valor"]
    return _fila("energía al fin de carrera", cil.designacion, r,
                 f"{cil.designacion} llega con {d['E_J']:.2f} J ({masa:.2f} kg a {vel:g} m/s); su amortiguación "
                 f"admite {d['E_adm_J']:g} J.", hip=hip, valor={**d, "v_m_s": vel, "masa_kg": masa},
                 recomendacion=None if r["estado"] == "ok" else
                 "Regulador de caudal por el escape (menos velocidad), un amortiguador externo o un cilindro mayor.")


def _frl(c, picos: list[tuple[str, float]]) -> list[dict]:
    out = []
    total = sum(q for _d, q in picos)
    for f in [d for d in c.dispositivos.values() if tipo(d) == "frl"]:
        p = f.ajustes.get("p_regulada_bar")
        if p is None or not picos:
            continue
        cau = f.neumatico.caudal
        r = K.verificar_caudal(f"{f.designacion} ({f.ref})", cau.C, cau.b, total, p, K.DP_CAUDAL_BAR, m=cau.m)
        d = r["valor"]
        hip = r["hipotesis"] + list(cau.hipotesis) + [
            f"todos los cilindros a la vez ({', '.join(x for x, _q in picos)}): el peor caso",
            f"Δp = {K.DP_CAUDAL_BAR:g} bar: criterio de diseño, el punto del caudal nominal"]
        out.append(_fila("caudal de la unidad de mantenimiento", f.designacion, r,
                         f"{f.designacion} pasa {d['q_disponible_NL_min']:.0f} NL/min con Δp = {K.DP_CAUDAL_BAR:g} bar "
                         f"contra {d['q_pico_NL_min']:.0f} NL/min de pico.", hip=hip,
                         recomendacion=None if r["estado"] == "ok" else "Una unidad de mantenimiento de más caudal."))
    return out


def _demanda(consumos: list[tuple[str, float, float]], fugas_pct: float | None) -> list[dict]:
    if not consumos:
        return []
    r = K.demanda_aire(consumos, fugas_pct or 0.0)
    rec = None
    if fugas_pct is None:
        r["estado"] = "aviso"
        r["hipotesis"] = ["fugas SIN declarar: la demanda va sin ellas (declara fugas_aire_pct con set_requirements)"]
        rec = 'Declara el % de fugas de la red como hipótesis: set_requirements {"fugas_aire_pct": 10}.'
    d = r["valor"]
    return [_fila("demanda de aire", "", r,
                  f"La máquina pide {d['NL_min']:.1f} NL/min ({d['sin_fugas_NL_min']:.1f} sin fugas): el dato para "
                  "elegir el compresor y la red.", recomendacion=rec,
                  elementos=[n for n, _v, _c in consumos])]


def _alcance(sin_servicio: list[str], sin_vel: list[str], sin_cadencia: list[str]) -> list[dict]:
    partes = []
    if sin_servicio:
        partes.append(f"{', '.join(sin_servicio)} sin `servicio`: se omiten consumo, caudal, tiempo, pandeo e impacto")
    if sin_vel:
        partes.append(f"{', '.join(sin_vel)} sin velocidad (ni declarada ni de un escenario vigente): se omiten el "
                      "caudal pico y la energía al fin de carrera")
    if sin_cadencia:
        partes.append(f"{', '.join(sin_cadencia)} sin cadencia (servicio.ciclos_min): fuera de la demanda de aire")
    if not partes:
        return []
    return [{"regla": ALCANCE, "estado": "aviso", "detalle": "; ".join(partes) + ".",
             "recomendacion": "Declara add_device.servicio {carrera_mm, velocidad_m_s, masa_kg, caso_euler, "
                              "ciclos_min} o corre un escenario que mueva el cilindro.",
             "elementos": sin_servicio + sin_vel + sin_cadencia, "medio": "aire"}]


def reglas(c: Circuito, *, cosim: dict | None = None, fugas_pct: float | None = None) -> list[dict]:
    """Las verificaciones del aire para la memoria (`[]` sin cilindros). `cosim`: {designación:
    {escenario, x_max_mm, t_avance_s?, t_retroceso_s?, v_max_m_s?, medicion}} de la co-simulación
    vigente; `fugas_pct`: el % de fugas declarado (requisito `fugas_aire_pct`)."""
    cosim = cosim or {}
    out: list[dict] = []
    picos, consumos = [], []
    sin_servicio, sin_vel, sin_cadencia = [], [], []
    for cil in [d for d in c.dispositivos.values() if tipo(d) == "cilindro"]:
        out += _fuerza(c, cil)
        if not cil.servicio:
            sin_servicio.append(cil.designacion)
            continue
        sim = cosim.get(cil.designacion)
        fila, nl = _consumo(c, cil)
        out.append(fila)
        if cil.servicio.get("ciclos_min"):
            consumos.append((cil.designacion, nl, cil.servicio["ciclos_min"]))
        else:
            sin_cadencia.append(cil.designacion)
        vel, hip_v = _velocidad(cil, sim)
        if vel is not None:
            filas, q = _caudal_pico(c, cil, vel, hip_v)
            out += filas
            picos.append((cil.designacion, q))
        else:
            sin_vel.append(cil.designacion)
        out += _tiempo(c, cil, sim)
        out.append(_pandeo(c, cil))
        if vel is not None:
            out.append(_impacto(cil, vel, hip_v))
    out += _frl(c, picos) + _demanda(consumos, fugas_pct) + _alcance(sin_servicio, sin_vel, sin_cadencia)
    return out
