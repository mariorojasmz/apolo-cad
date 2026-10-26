"""ERC neumático: el chequeo estático del circuito de aire del carril (plan V8.9 D9, F1b).

`erc(modelo)` devuelve las reglas con la forma del ERC eléctrico (`library/electrico/erc.py`):
`{regla, estado: ok|aviso|error, detalle, recomendacion?, norma, elementos, medio: "aire"}` y,
en las de cálculo, su bloque `calc` (`calculo.py`). Una regla sin hallazgos da UN «ok»; con
hallazgos, un dict por hallazgo. Sin aire en el modelo, `[]`: el ERC de siempre.

Reglas (cada una con su norma o «criterio de diseño»):
  - **aislamiento del aire** (error): con cilindros o válvulas, falta la válvula de corte CON
    escape aguas abajo del FRL, o una válvula queda fuera de ella: al parar para mantenimiento,
    el aire queda atrapado y mueve el cilindro (ISO 4414, ISO 14118);
  - **tubo sin puerto** (error): un extremo de tubo que no es un puerto de aire (un dispositivo
    o un puerto que no existe, o un borne eléctrico: medio distinto);
  - **puerto libre** (error): un puerto de trabajo, de alimentación o de salida sin tubo. Los
    escapes y los pilotajes pueden quedar libres; la entrada del FRL (o de la válvula de corte
    si no hay FRL) es la TOMA de la máquina: la red de planta no se modela (D3);
  - **presión de trabajo** (error / aviso): la regulada del FRL fuera del rango [p_min, p_max]
    de la ficha de lo que alimenta (válvula, cilindro, corte) o sobre la máxima de un tubo;
    aviso si la presión no está declarada (FRL sin `p_regulada_bar`, o sin FRL aguas arriba);
  - **servicio del cilindro** (aviso): un cilindro sin `servicio` no se puede revisar;
  - **caudal de la válvula** (error): la velocidad pedida supera la cota de régimen con el
    escape de su válvula en bloqueo sónico, v = C·p_ANR / A_escape (D3: es una cota OPTIMISTA,
    sin tubos ni carga: si ni así llega, no llega). `servicio.velocidad_m_s` es la velocidad de
    RÉGIMEN que el ciclo necesita (≈ carrera / tiempo de avance), no el pico transitorio de una
    carrera con masa, que la supera por física (V8.9 F7b, defecto 2: 1,15 contra 0,95 m/s): el
    pico lo toma la memoria del escenario vigente (`memoria._velocidad`);
  - **pandeo del vástago** (error): Euler/Johnson con la fuerza teórica de avance (el vástago
    bloqueado recibe toda la fuerza del pistón) y FS ≥ 3;
  - **energía al fin de carrera** (error): ½·m·v² contra la admisible de la amortiguación;
  - **relación de carga** (F4; aviso / error): η = `servicio.fuerza_N` / fuerza teórica de avance
    sobre el tope de la ficha (`relacion_carga_max`) o, sin él, el criterio de diseño; error si
    la carga pasa la fuerza EFECTIVA (con la fricción): el vástago no la mueve;
  - **escape sin silenciador** y **regulación de velocidad** (F4; aviso): SÓLO si el catálogo
    ofrece silenciadores / reguladores de caudal (`disponibles`): sin refs darían un aviso en
    todo circuito que nadie puede resolver (D16 los trae);
  - **presostato** (F8; aviso, sólo si hay presostatos): sin línea de aire (su puerto 1 sin tubo:
    lee la atmósfera, su NA nunca cierra; por eso no es «puerto libre»), sin su contacto cableado
    (ningún contacto `señal` con sus dos bornes en un conductor: nadie lo lee; sólo con
    `cableado`, que da quien tiene la red eléctrica), sin el ajuste `p_conmuta_bar`, o una
    conmutación sobre la presión regulada que le llega (el NA no cerraría nunca).

Las cuentas de cada cilindro (presión, válvula a través de sus reguladores, C del escape,
pandeo) son las de `cilindros.py`, las mismas que usa la memoria (`memoria.py`).

Puro (biblioteca estándar): recibe el modelo del carril por sus atributos, nunca un documento.
"""

from __future__ import annotations

from . import calculo as K
from . import cilindros as Z
from .lineas import Circuito, analizar, aguas_abajo, tipo

CRITERIO = "criterio de diseño"
NORMAS = {
    "aislamiento del aire": "ISO 4414:2010 (aislamiento y descarga de la energía neumática) · "
                            "ISO 14118:2017 (prevención de la puesta en marcha inesperada)",
    "tubo sin puerto": CRITERIO,
    "puerto libre": CRITERIO,
    "presión de trabajo": f"{CRITERIO} (rango de trabajo de la ficha del fabricante)",
    "servicio del cilindro": CRITERIO,
    "caudal de la válvula": "ISO 6358-1:2013 (caudal en bloqueo sónico) · ISO 8778 (ANR)",
    "pandeo del vástago": f"Euler / Johnson · {CRITERIO} (FS ≥ {K.FS_PANDEO:g})",
    "energía al fin de carrera": f"{CRITERIO} (energía admisible de la ficha del fabricante)",
    "relación de carga": f"{CRITERIO} (tope de la ficha o η ≤ {K.RELACION_CARGA_MAX:g})",
    "escape sin silenciador": f"{CRITERIO} (ruido de la descarga)",
    "regulación de velocidad": f"{CRITERIO} (regulación por el escape en doble efecto)",
    "presostato": f"{CRITERIO} (un presostato que no ve su línea o que nadie lee no vigila nada)",
}
#: Roles de puerto que pueden quedar sin tubo (a la atmósfera o sin pilotaje externo).
LIBRES = ("escape", "pilotaje")


def _r(regla: str, estado: str, detalle: str, recomendacion: str | None = None,
       elementos: list[str] | None = None, calc: dict | None = None) -> dict:
    out = {"regla": regla, "estado": estado, "detalle": detalle}
    if recomendacion:
        out["recomendacion"] = recomendacion
    out["norma"] = NORMAS[regla]
    out["elementos"] = list(elementos or [])
    out["medio"] = "aire"
    if calc is not None:
        out["calc"] = calc
    return out


def _quien(d) -> str:
    return f"{d.designacion} ({d.ref})"


def _de_tipo(c: Circuito, *tipos: str) -> list:
    return [d for d in c.dispositivos.values() if tipo(d) in tipos]


def hay_aire(modelo) -> bool:
    return bool(getattr(modelo, "tubos", ())) or any(
        getattr(d, "neumatico", None) is not None for d in modelo.dispositivos)


# ── reglas ────────────────────────────────────────────────────────────────────


def _aislamiento(c: Circuito) -> list[dict]:
    actuadores = _de_tipo(c, "cilindro", "valvula")
    if not actuadores:
        return [_r("aislamiento del aire", "ok", "No hay cilindros ni válvulas: nada que aislar.")]
    cortes = [d for d in _de_tipo(c, "valvula_corte") if d.neumatico.modelo.get("con_escape")]
    if not cortes:
        sin = [d.designacion for d in _de_tipo(c, "valvula_corte")]
        extra = f" ({', '.join(sin)} no descarga: es de corte sin escape)" if sin else ""
        return [_r("aislamiento del aire", "error",
                   f"Hay {len(actuadores)} cilindro(s) y válvula(s) y ninguna válvula de corte CON escape"
                   f"{extra}: al cortar el aire para el mantenimiento, el que queda atrapado en los tubos "
                   "y las cámaras puede mover el cilindro.",
                   "Pon una válvula de corte con escape y candado (p. ej. CORTE-ESC-G14) a la entrada, "
                   "aguas abajo del FRL, y alimenta desde su puerto 2 todas las válvulas.",
                   [d.designacion for d in actuadores[:6]])]
    out = []
    frls = _de_tipo(c, "frl")
    tras_frl = aguas_abajo(c, {c.linea(f.designacion, "2") for f in frls} - {None})
    for corte in cortes:
        if frls and c.linea(corte.designacion, "1") not in tras_frl:
            out.append(_r("aislamiento del aire", "error",
                          f"{_quien(corte)} no queda aguas abajo de la unidad de mantenimiento "
                          f"({', '.join(f.designacion for f in frls)}): lo que queda entre las dos no se descarga.",
                          "Conecta la entrada 1 de la válvula de corte a la salida 2 del FRL.",
                          [corte.designacion]))
    tras_corte = aguas_abajo(c, {c.linea(k.designacion, "2") for k in cortes} - {None})
    for v in _de_tipo(c, "valvula"):
        if c.linea(v.designacion, "1") not in tras_corte:
            out.append(_r("aislamiento del aire", "error",
                          f"{_quien(v)} no se alimenta desde la válvula de corte con escape "
                          f"({', '.join(k.designacion for k in cortes)}): al cerrarla, esa válvula sigue con aire.",
                          "Alimenta su puerto 1 desde el puerto 2 de la válvula de corte (directo o por un "
                          "colector).", [v.designacion]))
    return out or [_r("aislamiento del aire", "ok",
                      f"Las válvulas se alimentan aguas abajo de {', '.join(k.designacion for k in cortes)} "
                      "(corte con escape).", elementos=[k.designacion for k in cortes])]


def _tubos(c: Circuito) -> list[dict]:
    out = [_r("tubo sin puerto", "error", f"tubo {t.etiqueta} ({t.ref}): {motivo}.",
              "Un tubo une dos PUERTOS de aire (get_catalog → `neumatico.puertos`); los bornes "
              "eléctricos se cablean con add_wire.", [t.desde, t.hasta]) for t, motivo in c.problemas]
    return out or [_r("tubo sin puerto", "ok", f"Los {len(c.tubos)} tubos unen dos puertos de aire.")]


def _libres(c: Circuito) -> list[dict]:
    hay_frl = bool(_de_tipo(c, "frl"))
    out, n = [], 0
    for d in c.dispositivos.values():
        for p in d.puertos:
            if p.rol in LIBRES or tipo(d) == "presostato":  # el presostato sin tubo: su regla (aviso)
                continue
            toma = (tipo(d) == "frl" and p.id == "1") or (tipo(d) == "valvula_corte" and p.id == "1" and not hay_frl)
            n += 1
            if toma or (d.designacion, p.id) in c.conectados:
                continue
            out.append(_r("puerto libre", "error",
                          f"{_quien(d)}: el puerto {p.id} ({p.rol}) no tiene tubo.",
                          "Conéctalo con add_tubo (o cambia la ref por una de menos vías si sobra).",
                          [f"{d.designacion}:{p.id}"]))
    return out or [_r("puerto libre", "ok", f"Los {n} puertos de trabajo y alimentación tienen tubo "
                                            "(la entrada del FRL es la toma de la máquina).")]


def _presion(c: Circuito) -> list[dict]:
    out = []
    frls = _de_tipo(c, "frl")
    for f in frls:
        if "p_regulada_bar" not in f.ajustes:
            lo, hi = f.neumatico.ajustes["p_regulada_bar"]
            out.append(_r("presión de trabajo", "aviso",
                          f"{_quien(f)}: la presión regulada no está declarada (rango {lo:g}–{hi:g} bar).",
                          'Declárala en add_device.ajustes ({"p_regulada_bar": 6}): la fija el instalador.',
                          [f.designacion]))
    sin = []
    for d in c.dispositivos.values():
        m = d.neumatico.modelo
        if tipo(d) == "frl" or "p_max_bar" not in m:
            continue
        pr = c.presion_de(d)
        if pr is None:
            sin.append(d.designacion)
            continue
        lo, hi, origen = pr
        if hi > m["p_max_bar"] or ("p_min_bar" in m and lo < m["p_min_bar"]):
            rango = f"{m.get('p_min_bar', 0):g}–{m['p_max_bar']:g}"
            p = hi if hi > m["p_max_bar"] else lo
            out.append(_r("presión de trabajo", "error",
                          f"{_quien(d)} recibe {p:g} bar de {', '.join(origen)} y su ficha trabaja entre {rango} bar.",
                          "Ajusta la presión regulada del FRL dentro del rango, o cambia la ref.",
                          [d.designacion, *origen]))
    for t in c.tubos:
        a = next((x for x in (t.desde, t.hasta) if ":" in x), None)
        des, _, puerto = (a or "").rpartition(":")
        linea = c.linea(des, puerto)
        pr = c.presion.get(linea) if linea is not None else None
        if pr is not None and t.p_max_bar is not None and pr[1] > t.p_max_bar:
            out.append(_r("presión de trabajo", "error",
                          f"el tubo {t.etiqueta} ({t.ref}) trabaja a {pr[1]:g} bar y su máxima es {t.p_max_bar:g} bar.",
                          "Baja la presión regulada o usa un tubo de más presión.", [t.desde, t.hasta]))
    if sin and (frls or _de_tipo(c, "cilindro", "valvula")):
        motivo = ("no les llega la presión de ningún FRL con su ajuste" if frls else
                  "no hay unidad de mantenimiento (FRL) que declare la presión de la máquina")
        out.append(_r("presión de trabajo", "aviso",
                      f"{', '.join(sin[:6])}{' y más' if len(sin) > 6 else ''}: {motivo}; su rango de presión no "
                      "se puede revisar.",
                      "Pon un FRL a la entrada (p. ej. FR-G14) con su p_regulada_bar y alimenta desde él.", sin[:6]))
    return out or [_r("presión de trabajo", "ok", "La presión regulada cae dentro del rango de cada ficha.")]


def _servicio(c: Circuito) -> list[dict]:
    cil = _de_tipo(c, "cilindro")
    sin = [d.designacion for d in cil if not d.servicio]
    if not cil:
        return [_r("servicio del cilindro", "ok", "No hay cilindros.")]
    if sin:
        return [_r("servicio del cilindro", "aviso",
                   f"{', '.join(sin)}: sin `servicio` no se revisan el pandeo del vástago, la energía al fin de "
                   "carrera ni el caudal de la válvula.",
                   'Declara add_device.servicio {"carrera_mm": …, "velocidad_m_s": …, "masa_kg": …, '
                   '"caso_euler": …}.', sin)]
    return [_r("servicio del cilindro", "ok", f"Los {len(cil)} cilindros declaran su servicio.")]


def _caudal(c: Circuito) -> list[dict]:
    out, n = [], 0
    for cil in _de_tipo(c, "cilindro"):
        s, m = cil.servicio, cil.neumatico.modelo
        if not s.get("velocidad_m_s"):
            continue
        n += 1
        A, Ab, _a = K.areas(m["D_mm"], m["d_mm"])
        # avance: escapa la cámara B (vástago) por la vía de la válvula que la manda; retroceso,
        # la A. Un simple efecto retrocede por su muelle: sólo el avance, por el lado que llena.
        lados = [("B", Ab, "avance"), ("A", A, "retroceso")] if m["efecto"] == "doble" else []
        for puerto, area, sentido in lados:
            v, regs = Z.hacia_valvula(c, cil, puerto)
            if v is None:
                out.append(_r("caudal de la válvula", "aviso",
                              f"{_quien(cil)}: ninguna válvula manda el puerto {puerto}; no se revisa el caudal.",
                              "Une el puerto del cilindro a la vía 2 o 4 de su válvula (directo o por su "
                              "regulador de caudal).", [cil.designacion]))
                break
            C, b, hip = Z.c_escape(v, regs)
            r = K.regimen(C, area, s["carrera_mm"], b=b)
            r["calc"]["hipotesis"] = r["hipotesis"] + hip + ["sin la pérdida de los tubos ni la carga: la cota es optimista"]
            vmax = r["valor"]["v_m_s"]
            if s["velocidad_m_s"] > vmax:
                out.append(_r("caudal de la válvula", "error",
                              f"{_quien(cil)} pide {s['velocidad_m_s']:g} m/s de régimen y el escape de {v.designacion} "
                              f"(C = {C:.2f}) da a lo sumo {vmax:.2f} m/s en el {sentido}.",
                              "Usa una válvula de más caudal (C), un cilindro de menos Ø o pide menos velocidad.",
                              [cil.designacion, v.designacion], calc=r["calc"]))
    return out or [_r("caudal de la válvula", "ok",
                      f"El escape de cada válvula alcanza la velocidad pedida ({n} cilindro(s) con velocidad)."
                      if n else "Ningún cilindro declara su velocidad.")]


def _pandeo(c: Circuito) -> list[dict]:
    out, n = [], 0
    for cil in _de_tipo(c, "cilindro"):
        if not cil.servicio:
            continue
        n += 1
        r, hip, F, p, largo = Z.pandeo(c, cil)
        if r["estado"] != "ok":
            v = r["valor"]
            out.append(_r("pandeo del vástago", r["estado"],
                          f"{_quien(cil)}: el vástago Ø{cil.neumatico.modelo['d_mm']:g} con {largo:g} mm libres "
                          f"admite {v['F_adm_N']:.0f} N y el pistón empuja {F:.0f} N a {p:g} bar (FS = {v['fs']:.2f}).",
                          "Un cilindro de vástago mayor, menos carrera libre, un montaje más rígido (caso 2–4) "
                          "o una guía del vástago.", [cil.designacion], calc={**r["calc"], "hipotesis": hip}))
    return out or [_r("pandeo del vástago", "ok",
                      f"Los vástagos de los {n} cilindro(s) con servicio no pandean (FS ≥ {K.FS_PANDEO:g})."
                      if n else "Ningún cilindro declara su servicio.")]


def _relacion(c: Circuito) -> list[dict]:
    out, n = [], 0
    for cil in _de_tipo(c, "cilindro"):
        r = Z.relacion(c, cil)
        if r is None:
            continue
        n += 1
        if r["estado"] != "ok":
            v = r["valor"]
            que = ("no la mueve: la carga pasa la fuerza efectiva (con la fricción de los sellos)"
                   if r["estado"] == "error" else f"pasa el tope de {v['tope']:g}")
            out.append(_r("relación de carga", r["estado"],
                          f"{_quien(cil)}: {v['F_req_N']:g} N contra {v['F_teorica_N']:.0f} N teóricos "
                          f"(η = {v['eta']:.2f}): {que}.",
                          "Un cilindro de más Ø, más presión (dentro de la ficha) o menos carga.",
                          [cil.designacion], calc={**r["calc"], "hipotesis": r["hipotesis"]}))
    return out or [_r("relación de carga", "ok",
                      f"Los {n} cilindro(s) con fuerza declarada quedan bajo su tope de relación de carga."
                      if n else "Ningún cilindro declara la fuerza a vencer (servicio.fuerza_N).")]


def _impacto(c: Circuito) -> list[dict]:
    out, n = [], 0
    for cil in _de_tipo(c, "cilindro"):
        s, m = cil.servicio, cil.neumatico.modelo
        if not s.get("velocidad_m_s"):
            continue
        n += 1
        masa = K.masa_movil_kg(m, s["carrera_mm"], s.get("masa_kg") or 0.0)
        r = K.energia_impacto(masa, s["velocidad_m_s"], m["E_amortiguacion_J"])
        if r["estado"] != "ok":
            v = r["valor"]
            hip = ["llega a la velocidad pedida (la amortiguación no se simula: V8.9 D3)"]
            out.append(_r("energía al fin de carrera", "error",
                          f"{_quien(cil)} llega con {v['E_J']:.2f} J ({masa:.2f} kg a {s['velocidad_m_s']:g} m/s) y "
                          f"su amortiguación admite {v['E_adm_J']:g} J.",
                          "Menos velocidad (regulador por el escape), un amortiguador externo o un cilindro "
                          "mayor.", [cil.designacion], calc={**r["calc"], "hipotesis": hip}))
    return out or [_r("energía al fin de carrera", "ok",
                      f"Los {n} cilindro(s) con velocidad llegan bajo la energía admisible."
                      if n else "Ningún cilindro declara su velocidad.")]


def _silenciadores(c: Circuito) -> list[dict]:
    """Escape de válvula sin silenciador (aviso: el ruido de la descarga). Una vía de escape libre
    descarga a la atmósfera por la rosca de la válvula."""
    out = []
    for v in _de_tipo(c, "valvula", "valvula_corte"):
        for p in v.puertos:
            if p.rol != "escape":
                continue
            i = c.linea(v.designacion, p.id)
            if not any(tipo(c.dispositivos[d]) == "silenciador" for d, _p in c.miembros[i]):
                out.append(_r("escape sin silenciador", "aviso",
                              f"{_quien(v)}: el escape {p.id} descarga sin silenciador (ruido de la descarga).",
                              f"Pon un silenciador en la vía de escape (add_device + add_tubo al puerto {p.id}).",
                              [f"{v.designacion}:{p.id}"]))
    return out or [_r("escape sin silenciador", "ok", "Cada escape de válvula lleva su silenciador.")]


def _regulacion(c: Circuito) -> list[dict]:
    """Cilindro sin regulación de velocidad (aviso): ningún regulador de caudal en el camino de sus
    puertos; o uno que regula la ENTRADA (su puerto 1 hacia el cilindro) en un doble efecto (la
    regulación va por el escape: el pistón queda entre dos cámaras con presión)."""
    out = []
    for cil in _de_tipo(c, "cilindro"):
        regs = [r for p in cil.puertos for r in Z.hacia_valvula(c, cil, p.id)[1]]
        if not regs:
            out.append(_r("regulación de velocidad", "aviso",
                          f"{_quien(cil)}: sin regulador de caudal, el vástago va a la velocidad que dé el "
                          "escape de su válvula y golpea al final.",
                          "Un regulador de caudal unidireccional en cada puerto, regulando el escape (su "
                          "puerto 2 hacia el cilindro).", [cil.designacion]))
        elif cil.neumatico.modelo["efecto"] == "doble" and any(lado == "1" for _reg, lado in regs):
            out.append(_r("regulación de velocidad", "aviso",
                          f"{_quien(cil)}: un regulador regula la ENTRADA del aire (su puerto 1 da al cilindro).",
                          "En doble efecto se regula el escape: da vuelta el regulador (puerto 2 hacia el "
                          "cilindro).", [cil.designacion]))
    return out or [_r("regulación de velocidad", "ok", "Cada cilindro regula su velocidad por el escape.")]


def _presostatos(c: Circuito, cableado=None) -> list[dict]:
    """Un presostato que no vigila nada (aviso; reglas en el docstring del módulo). Sin
    presostatos no da filas (el ERC de antes)."""
    pres = _de_tipo(c, "presostato")
    if not pres:
        return []
    out = []
    for d in pres:
        quien = _quien(d)
        puertos = [p.id for p in d.puertos]
        if not any((d.designacion, p) in c.conectados for p in puertos):
            out.append(_r("presostato", "aviso",
                          f"{quien}: su puerto {', '.join(puertos)} no tiene tubo: lee la atmósfera y su NA no "
                          "cierra nunca.",
                          "Únelo con add_tubo a la línea que vigila (la de alimentación, aguas abajo de la "
                          "válvula de corte con escape, para «hay aire en la máquina»).", [d.designacion]))
        señal = [(k.de, k.a) for k in getattr(d, "caminos", ()) if k.accion == "señal"]
        if cableado is not None and señal and not any(cableado(d.designacion, a) and cableado(d.designacion, b)
                                                      for a, b in señal):
            out.append(_r("presostato", "aviso",
                          f"{quien}: su contacto no está cableado ({', '.join(f'{a}-{b}' for a, b in señal)}): "
                          "nadie lee la presión.",
                          f"Cablea el contacto con add_wire a una entrada del PLC (p. ej. {señal[0][0]} a la "
                          f"alimentación de 24 V y {señal[0][1]} a la entrada).", [d.designacion]))
        rango = d.neumatico.ajustes.get("p_conmuta_bar")
        p_on = d.ajustes.get("p_conmuta_bar")
        if p_on is None and rango is not None:
            lo, hi = rango
            out.append(_r("presostato", "aviso",
                          f"{quien}: la presión de conmutación no está declarada (rango {lo:g}–{hi:g} bar).",
                          'Declárala en add_device.ajustes ({"p_conmuta_bar": 4}): la fija el instalador con '
                          "el tornillo del muelle.", [d.designacion]))
        pr = c.presion_de(d)
        if p_on is not None and pr is not None and p_on > pr[0]:
            out.append(_r("presostato", "aviso",
                          f"{quien} conmuta a {p_on:g} bar y su línea recibe {pr[0]:g} bar de "
                          f"{', '.join(pr[2])}: el NA no cerraría nunca.",
                          "Baja p_conmuta_bar bajo la presión regulada (con margen para la caída de la línea).",
                          [d.designacion, *pr[2]]))
    return out or [_r("presostato", "ok", f"Los {len(pres)} presostato(s) leen su línea y su contacto está "
                                          "cableado.", elementos=[d.designacion for d in pres])]


_REGLAS = (_aislamiento, _tubos, _libres, _presion, _servicio, _caudal, _pandeo, _impacto, _relacion)
#: Las reglas que piden una ref que el catálogo puede no tener (D16): sólo corren si el catálogo
#: ofrece ese tipo; si no, darían un aviso en TODO circuito sin forma de resolverlo.
_CON_CATALOGO = (("silenciador", _silenciadores), ("regulador_caudal", _regulacion))


def erc(modelo, circuito: Circuito | None = None, *, disponibles=frozenset(), cableado=None) -> list[dict]:
    """Las reglas de D9 sobre el circuito de aire del modelo; `[]` si no tiene aire. `disponibles`:
    los `modelo.tipo` neumáticos que ofrece el catálogo (`services/neumatica.py` los pasa): las
    reglas de silenciador y de regulación corren sólo si hay con qué cumplirlas. `cableado(des,
    borne) -> bool` (de la red eléctrica, `services/neumatica.py`): si llega un conductor al borne;
    sin él, la regla del presostato no revisa su contacto."""
    if not hay_aire(modelo):
        return []
    c = circuito or analizar(modelo)
    reglas = list(_REGLAS) + [f for t, f in _CON_CATALOGO if t in disponibles]
    return [r for regla in reglas for r in regla(c)] + _presostatos(c, cableado)
