"""Lo que el ERC (`erc.py`) y la memoria (`memoria.py`) leen de un CILINDRO en su circuito (plan V8.9
D9, D10; F4): una sola cuenta para los dos, así la puerta de entrega y la memoria nunca dan cifras
distintas del mismo vástago.

  - `p_trabajo`: la presión que le llega (la máxima de sus líneas) o, sin FRL, la máxima de la
    ficha (el peor caso, declarado);
  - `hacia_valvula`: la válvula que manda un puerto, siguiendo la línea a través de los reguladores
    de caudal EN LÍNEA (cada uno con el puerto que da al cilindro);
  - `c_escape`: el C con que escapa una cámara (la vía de escape de la válvula, en serie con los
    reguladores del camino: 1/C² = Σ 1/Cᵢ², aproximación declarada, D3);
  - `volumen_tubos`: el volumen de los tubos de la línea de un puerto (se llena en cada carrera);
  - `relacion`: la relación de carga con `servicio.fuerza_N` (contra la teórica y la efectiva);
  - `pandeo`: el vástago con la fuerza teórica de avance, el caso de Euler y el largo libre del
    servicio (lo que falta, como hipótesis);
  - `choques`: el amortiguador externo de cada extremo (plan amortiguador-externo): velocidad de
    choque (`v_choque`), fuerza del cilindro (`fuerza_extremo`) y ciclos por hora (`ritmo`).

Puro (biblioteca estándar), sobre el `Circuito` de `lineas.py`.
"""

from __future__ import annotations

from . import amortiguador as A
from . import calculo as K
from .iso6358 import c_serie
from .lineas import Circuito, tipo

_HIP_SERIE = "componentes en serie por 1/C² = Σ 1/Cᵢ² (aproximación: ISO 6358-3 trae el método)"


def p_trabajo(c: Circuito, cil) -> tuple[float, list[str]]:
    """(presión manométrica que llega, hipótesis)."""
    pr = c.presion_de(cil)
    if pr is not None:
        return pr[1], []
    p = cil.neumatico.modelo["p_max_bar"]
    return p, [f"sin presión declarada: {p:g} bar, la máxima de la ficha (el peor caso)"]


def hacia_valvula(c: Circuito, cil, puerto: str):
    """(válvula con una vía de trabajo 2/4 en el camino del puerto, o None; [(regulador, puerto del
    regulador que da al cilindro)]). Atraviesa los reguladores de caudal en línea (1 ↔ 2)."""
    i0 = c.linea(cil.designacion, puerto)
    if i0 is None:
        return None, []
    vistas, cola, regs = {i0}, [i0], []
    while cola:
        i = cola.pop(0)
        for des, p in c.miembros[i]:
            d = c.dispositivos[des]
            if tipo(d) == "valvula" and p in ("2", "4"):
                return d, regs
            if tipo(d) == "regulador_caudal" and p in ("1", "2"):
                regs.append((d, p))
                j = c.linea(des, "1" if p == "2" else "2")
                if j is not None and j not in vistas:
                    vistas.add(j)
                    cola.append(j)
    return None, regs


def c_regulado(reg) -> tuple[float, list[str]]:
    """El C del sentido regulado (2 → 1): el ajuste declarado o, sin él, la máxima apertura."""
    if "C_regulado" in reg.ajustes:
        return float(reg.ajustes["C_regulado"]), []
    lo, hi = reg.neumatico.ajustes["C_regulado"]
    return hi, [f"{reg.designacion}: C_regulado sin declarar, la máxima apertura ({hi:g}) — la velocidad "
                f"real la fija quien lo ajusta"]


def c_escape(valvula, regs) -> tuple[float, float, list[str]]:
    """(C, b, hipótesis) con que escapa una cámara: la vía de escape de la válvula (o la de
    alimentación si la ficha no da la de escape) en serie con los reguladores del camino. Un
    regulador con su puerto 2 hacia el cilindro deja salir por su sentido REGULADO (regulación por
    el escape); con el 1, por el libre."""
    caudal = valvula.neumatico.escape or valvula.neumatico.caudal
    hip = list(caudal.hipotesis)
    if valvula.neumatico.escape is None:
        hip.append("C del escape = el de la alimentación (la ficha no da el de 4→5)")
    Cs = [caudal.C]
    for reg, lado in regs:
        if lado == "2":
            C, h = c_regulado(reg)
            Cs.append(C)
            hip += h
        else:
            Cs.append(reg.neumatico.caudal.C)
    if len(Cs) > 1:
        hip.append(_HIP_SERIE)
        return c_serie(*Cs), caudal.b, hip
    return caudal.C, caudal.b, hip


def volumen_tubos(c: Circuito, cil, puerto: str) -> tuple[float, list[str]]:
    """(cm³ de los tubos de la línea del puerto, hipótesis): los que se llenan con la cámara."""
    i = c.linea(cil.designacion, puerto)
    V, sin = 0.0, []
    for t in c.tubos:
        a = next((x for x in (t.desde, t.hasta) if ":" in x), "")
        des, _, p = a.rpartition(":")
        if i is None or c.linea(des, p) != i:
            continue
        if t.largo_m and t.D_int_mm:
            V += K.volumen_tubo_cm3(t.D_int_mm, t.largo_m)
        else:
            sin.append(t.etiqueta)
    hip = [f"tubo(s) {', '.join(sin)} sin largo declarado: su volumen no cuenta"] if sin else []
    return V, hip


def relacion(c: Circuito, cil) -> dict | None:
    """`calculo.relacion_carga` con la `servicio.fuerza_N` del cilindro (None sin ella), contra la
    fuerza teórica y la efectiva de avance a la presión que le llega."""
    s, m = cil.servicio, cil.neumatico.modelo
    if not s.get("fuerza_N"):
        return None
    p, hip = p_trabajo(c, cil)
    f = K.fuerzas(m["D_mm"], m["d_mm"], p, friccion_N=m.get("friccion_N"), friccion_pct=m.get("friccion_pct"))
    r = K.relacion_carga(s["fuerza_N"], f["valor"]["F_avance_N"], f["valor"]["F_avance_ef_N"],
                         tope=m.get("relacion_carga_max"))
    r["hipotesis"] = hip + r["hipotesis"] + [f"fricción de los sellos: {f['calc']['entradas']['fricción']}"]
    return r


def pandeo(c: Circuito, cil) -> tuple[dict, list[str], float, float, float]:
    """(resultado de `calculo.pandeo_vastago`, hipótesis completas, F, p, largo libre)."""
    s, m = cil.servicio, cil.neumatico.modelo
    p, hip = p_trabajo(c, cil)
    F = K.fuerzas(m["D_mm"], m["d_mm"], p, friccion_N=m.get("friccion_N"),
                  friccion_pct=m.get("friccion_pct"))["valor"]["F_avance_N"]
    caso = s.get("caso_euler") or 1
    largo = s.get("largo_libre_mm") or s["carrera_mm"]
    r = K.pandeo_vastago(m["d_mm"], largo, caso, F)
    hip = hip + r["hipotesis"] + ["la fuerza es la teórica de avance: el vástago bloqueado recibe toda la del pistón"]
    if not s.get("caso_euler"):
        hip.append("caso 1 de Euler (empotrado-libre, el más desfavorable): el servicio no declara el montaje")
    if not s.get("largo_libre_mm"):
        hip.append("largo libre = la carrera (a confirmar: el vástago fuera de la tapa suma)")
    return r, hip, F, p, largo


# ── amortiguador externo (plan amortiguador-externo D2–D5) ─────────────────────────────────


def amortiguadores(cil) -> dict[str, str]:
    """{extremo: ref} de los amortiguadores externos que declara el servicio (vacío: ninguno)."""
    s = cil.servicio or {}
    return {e: s[f"amortiguador_{e}"] for e in A.EXTREMOS if s.get(f"amortiguador_{e}")}


def v_choque(servicio: dict, v_medida: float | None = None) -> tuple[float | None, list[str]]:
    """(velocidad con que la carga llega al amortiguador, hipótesis) — D4: la MEDIDA (el pico de la
    co-simulación vigente) si la hay; si no, la de llegada declarada (`velocidad_llegada_m_s`,
    trabas-de-modelado D8, cuando exista) y, con sólo la de régimen, 2·v̄ como pide la ficha (SMC
    RB, nota 1 de «Type of Impact»: la de régimen es carrera / tiempo, una media)."""
    if v_medida:
        return v_medida, [f"velocidad de choque = la máxima medida en la co-simulación: {v_medida:g} m/s"]
    if servicio.get("velocidad_llegada_m_s"):
        v = servicio["velocidad_llegada_m_s"]
        return v, [f"velocidad de choque = la de llegada declarada: {v:g} m/s"]
    if servicio.get("velocidad_m_s"):
        v = servicio["velocidad_m_s"]
        return 2.0 * v, [f"velocidad de choque = 2·{v:g} m/s: la ficha pide 2·v̄ cuando v̄ sale del tiempo de "
                         "carrera (la de régimen declarada lo es); una medida en un escenario la reemplaza"]
    return None, []


def fuerza_extremo(c: Circuito, cil, extremo: str) -> tuple[float, list[str]]:
    """(fuerza teórica con que el cilindro empuja la carga contra el amortiguador, hipótesis): p·A
    al avance, p·A anular al retroceso, con la presión que le llega (la ficha: E2 = F1·S)."""
    m = cil.neumatico.modelo
    p, hip = p_trabajo(c, cil)
    A_, Ab, _a = K.areas(m["D_mm"], m["d_mm"])
    area = A_ if extremo == "avance" else Ab
    return p * 0.1 * area, hip + [f"F = p·{'A' if extremo == 'avance' else 'A anular'} teórica a {p:g} bar "
                                  "(la ficha: el empuje del cilindro durante la carrera del amortiguador)"]


def ritmo(cil, paquetes_min: float | None) -> tuple[float | None, str]:
    """(ciclos/min del cilindro, de dónde salen) para la energía por hora — D5: la cadencia del
    servicio si la declara; si no, la capacidad nominal (un ciclo por paquete); si no, None."""
    s = cil.servicio or {}
    if s.get("ciclos_min"):
        return float(s["ciclos_min"]), "la cadencia del servicio (servicio.ciclos_min)"
    if paquetes_min:
        return float(paquetes_min), "la capacidad nominal (requirements.paquetes_por_minuto, un ciclo por paquete)"
    return None, ""


def choques(c: Circuito, cil, fichas: dict | None, v: float, hip_v: list[str],
            paquetes_min: float | None) -> list[tuple[str, str, dict | None, dict | None]]:
    """[(extremo, ref, resultado por ciclo, resultado por hora)] de cada amortiguador declarado; sin
    la ficha de la ref (quien llama no la pasó), los resultados son None."""
    s, m = cil.servicio, cil.neumatico.modelo
    masa = K.masa_movil_kg(m, s["carrera_mm"], s.get("masa_kg") or 0.0)
    out = []
    for extremo, ref in amortiguadores(cil).items():
        f = (fichas or {}).get(ref)
        if f is None:
            out.append((extremo, ref, None, None))
            continue
        F, hip_f = fuerza_extremo(c, cil, extremo)
        r = A.choque(masa, v, F, f, extremo=extremo)
        r["hipotesis"] = hip_v + hip_f + [f"masa móvil de la ficha + carga declarada: {masa:g} kg"] + r["hipotesis"]
        r["calc"]["hipotesis"] = r["hipotesis"]
        n, origen = ritmo(cil, paquetes_min)
        out.append((extremo, ref, r, A.por_hora(r["valor"]["E_J"], n, f, extremo=extremo, origen=origen)))
    return out
