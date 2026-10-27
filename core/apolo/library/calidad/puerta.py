"""Controles de la puerta de PUBLICACIÓN sobre lo que YA existe (plan puerta-de-publicacion, D2 y
D7): la puerta de entrega con gravedad obligatoria, lo que ésta dejó sin evaluar, el acceso de
herramienta, los choques DENTRO de un super-comando (D13b del plan), la memoria de cálculo, el
tablero eléctrico, los escenarios de prueba y la marcha del video contra el modelo (D13 de la
fábrica). Puro: cada función recibe los insumos que `services/puerta_publicacion.py` reunió (datos,
nunca un `Document`) y devuelve `{estado, detalle, evidencia, piezas}`; el registro
(`registro.py`) le pone id, título, modo de falla, norma y familia.

Ninguno decide NO_APLICA: eso lo dice sólo el `aplica_si` de su entrada en el registro (D1).
"""

from __future__ import annotations

from .item import FALLA, OK, SIN_EVALUAR, recortar

VERDE = "VERDE"
#: Lo que la puerta de entrega declara en `no_aplica` y está JUSTIFICADO por un hecho del modelo:
#: (prefijo, hecho que lo justifica, porqué). Lo demás que deja sin evaluar bloquea.
_JUSTIFICADOS = (
    ("sujeción (proyecto de", "pocos_solidos", "proyecto chico: la sujeción se exige desde 5 sólidos"),
    ("poses (sin estudios", "sin_estudios", "sin estudios de movimiento: no hay poses que revisar"),
    ("poses (los estudios no declaran", "sin_poses", "los estudios no declaran poses de reposo"),
)
#: Lo que la puerta de entrega deja sin evaluar y tiene su PROPIO ítem en esta puerta.
_CON_ITEM_PROPIO = ("gravedad", "acceso de herramienta")


def _r(estado: str, detalle: str, evidencia: dict | None = None, piezas=()) -> dict:
    return {"estado": estado, "detalle": detalle, "evidencia": evidencia or {},
            "piezas": list(dict.fromkeys(piezas))[:40]}


def semaforo_entrega(ins: dict) -> dict:
    """La puerta de entrega en VERDE (con gravedad). AMARILLO también bloquea: un aviso de cierre
    es algo que el modelador no resolvió (D2), salvo que esté JUSTIFICADO por escrito
    (`justificadas`, D11 de puerta-sin-sobrediseno); un bloqueante nunca se justifica."""
    from .justificadas import citar, del_aviso
    from .nombres import REGLA_ENTREGA

    rep = ins["entrega"]
    v = rep.get("veredicto")
    if v == VERDE:
        return _r(OK, "puerta de entrega en VERDE",
                  {"chequeos_ok": (rep.get("resumen") or {}).get("chequeos_ok", [])})
    js = ins.get("justificadas") or []
    bloq, avisos, justificados, propios = list(rep.get("bloqueantes", [])), [], [], []
    for m in rep.get("avisos", []):
        # «nombres por función» no se repite aquí: la juzga su propio ítem
        # (`interfaz.nombres_por_funcion`), como la fuente «seguridad» descarta
        # `seguridad.electrico` por repetir `riesgos.electrico` (plan nombres-por-funcion A12)
        if str(m.get("regla") or "").startswith(REGLA_ENTREGA):
            propios.append(m.get("regla"))
            continue
        j = del_aviso(m.get("regla"), m.get("piezas"), js)
        (justificados.append({"regla": m.get("regla"), "justificacion": citar(j)}) if j
         else avisos.append(m))
    ev_j = {"justificados": justificados} if justificados else {}
    if propios:
        ev_j["con_item_propio"] = propios
    if not bloq and not avisos:
        extra = f" y {len(propios)} que juzga su propio ítem" if propios else ""
        return _r(OK, f"puerta de entrega en {v} con {len(justificados)} aviso(s) justificado(s) "
                      f"por escrito{extra}", {"veredicto": v, **ev_j})
    malos = [*bloq, *avisos]
    casos = [{"regla": m.get("regla"), "detalle": m.get("detalle"),
              "piezas": (m.get("piezas") or [])[:12]} for m in malos]
    piezas = [p for m in malos for p in (m.get("piezas") or [])]
    extra = f" ({len(justificados)} justificado(s))" if justificados else ""
    return _r(FALLA, f"puerta de entrega en {v}: {len(bloq)} bloqueante(s) y {len(avisos)} "
                     f"aviso(s){extra}", {"veredicto": v, **recortar(casos), **ev_j}, piezas)


def gravedad(ins: dict) -> dict:
    """La simulación de gravedad CORRIÓ (sin MuJoCo o si falla: SIN_EVALUAR, nunca la caída
    silenciosa a «sin gravedad») y nada cae."""
    g = ins.get("gravedad") or {}
    res = g.get("resultado")
    if res is None:
        return _r(SIN_EVALUAR, f"la gravedad no se simuló: {g.get('motivo') or 'sin motivo'}")
    caidas = res.get("fell") or []
    if caidas:
        peor = caidas[0]
        return _r(FALLA, f"{len(caidas)} pieza(s) caen (la peor: {peor.get('nombre')} "
                         f"{peor.get('caida_mm')} mm)",
                  recortar([{k: c.get(k) for k in ("id", "nombre", "caida_mm")} for c in caidas]),
                  [c.get("id") for c in caidas])
    return _r(OK, f"estable: {len(res.get('estables') or [])} pieza(s) quietas, "
                  f"{res.get('n_grounded')} anclada(s)",
              {"settled": res.get("settled"), "n_grounded": res.get("n_grounded")})


def no_aplica_justificado(ins: dict) -> dict:
    """Todo lo que la puerta de entrega dejó en `no_aplica` está justificado por el modelo (D1: «no
    se pudo ver» no es «está bien»). Lo que tiene su propio ítem (gravedad, acceso) va allá. Lo
    que ningún hecho justifica pasa si está JUSTIFICADO por escrito (`justificadas`, D11 de
    puerta-sin-sobrediseno: por el texto, su sección o, si nombra piezas, por esas piezas)."""
    from .justificadas import citar, del_no_evaluado, seccion

    hechos = ins.get("hechos") or {}
    js = ins.get("justificadas") or []
    con_piezas = {x.get("no_aplica"): x for x in (ins["entrega"].get("no_aplica_piezas") or [])}
    justificados, sin, piezas = [], [], []
    for texto in (ins["entrega"].get("no_aplica") or []):
        if texto.startswith(_CON_ITEM_PROPIO):
            continue
        regla = next((x for x in _JUSTIFICADOS if texto.startswith(x[0])), None)
        if regla is not None and hechos.get(regla[1]):
            justificados.append({"no_aplica": texto, "porque": regla[2]})
            continue
        np = con_piezas.get(texto) or {}
        j = del_no_evaluado(texto, np.get("piezas"), js, np.get("regla"))
        if j:
            justificados.append({"no_aplica": texto, "justificacion": citar(j)})
        else:
            sin.append(texto)
            piezas += np.get("piezas") or []
    if sin:
        como: dict[str, list] = {}
        for t in sin:
            np = con_piezas.get(t) or {}
            ps = como.setdefault(np.get("regla") or seccion(t), [])
            ps += [x for x in (np.get("piezas") or []) if x not in ps]
        pista = "; ".join(f"regla «{r}»" + (f" (con `pieza`, cada una de {', '.join(ps)})"
                                           if ps else "") for r, ps in list(como.items())[:3])
        return _r(SIN_EVALUAR, f"{len(sin)} chequeo(s) de la puerta de entrega sin evaluar ni "
                               "justificar: " + "; ".join(sin[:3]) + ". Verifícalo en el modelo "
                               f"o justifícalo por escrito con set_justifications: {pista}",
                  {"sin_justificar": sin, "justificados": justificados,
                   "como_justificar": [{"regla": r, **({"piezas": ps} if ps else {})}
                                       for r, ps in como.items()]}, piezas)
    return _r(OK, "nada quedó sin evaluar" if not justificados else
              f"{len(justificados)} chequeo(s) no aplican, cada uno con su porqué",
              {"justificados": justificados})


def acceso_herramienta(ins: dict) -> dict:
    """Todo fijador de llave EVALUADO y con herramienta que entre (un «no evaluado» se resuelve:
    D2). Sólo boca = FALLA también (la puerta de entrega lo deja en aviso)."""
    rep = ins.get("acceso") or {}
    sin = rep.get("sin_herramienta") or []
    boca = rep.get("solo_boca") or []
    no_ev = rep.get("no_evaluados") or []
    ev = {"evaluados": rep.get("evaluados", 0), "sin_herramienta": len(sin),
          "solo_boca": len(boca), "no_evaluados": len(no_ev)}
    if sin or boca:
        casos = [{"id": e.get("id"), "nombre": e.get("nombre"), "llave_mm": e.get("llave_mm"),
                  "bloquean": (e.get("bloquean") or [])[:5], "problema": problema}
                 for lista, problema in ((sin, "la llave no entra"), (boca, "sólo llave de boca"))
                 for e in lista]
        return _r(FALLA, f"{len(sin)} sin herramienta que entre y {len(boca)} sólo con llave de "
                         "boca", {**ev, **recortar(casos)}, [e.get("id") for e in [*sin, *boca]])
    if no_ev:
        casos = [{"id": e.get("id"), "nombre": e.get("nombre"), "motivo": e.get("motivo")}
                 if isinstance(e, dict) else {"id": str(e)} for e in no_ev]
        return _r(SIN_EVALUAR, f"{len(no_ev)} fijador(es) sin evaluar (hexágono no reconocido o "
                               "fuera de tabla): arregla el reconocimiento o el modelo",
                  {**ev, **recortar(casos)},
                  [c.get("id") for c in casos])
    return _r(OK, f"{ev['evaluados']} fijador(es) con copa o anillo que entra y gira", ev)


def interferencia_interna(ins: dict) -> dict:
    """Sin choques entre las piezas de un MISMO super-comando (D13b del plan: la puerta de entrega
    los excluye con `same_command_pairs` y escondió la banda de `create_belt_conveyor` en el piso).
    Lo declarado (juntas, `fasten`, herraje asentado) no cuenta; un asiento ≤ la tolerancia de
    contacto (`EXCESS_TOL_MM3`) se tolera y se DECLARA."""
    it = ins.get("interna") or {}
    choques = it.get("choques") or []
    ev = {"comandos": it.get("comandos", 0), "tolerancia_mm3": it.get("tolerancia_mm3"),
          "contactos_tolerados": len(it.get("tolerados") or [])}
    if it.get("sin_revisar"):
        ev["parejas_sin_revisar"] = it["sin_revisar"]
    if choques:
        peor = choques[0]
        return _r(FALLA, f"{len(choques)} choque(s) dentro de super-comandos; el peor: "
                         f"{peor['nombre_a']} ↔ {peor['nombre_b']} ({peor['volumen_mm3']:g} mm³)",
                  {**ev, **recortar(choques)}, [x for c in choques for x in (c["a"], c["b"])])
    return _r(OK, f"{ev['comandos']} super-comando(s) sin choques internos", ev)


def memoria(ins: dict) -> dict:
    """La memoria de cálculo no sale «NO CONFORME» (el veredicto de `drawing/calc_report.py`, sin
    componer el PDF). «NO CONCLUYENTE» (nada verificado) = SIN_EVALUAR."""
    m = ins.get("memoria") or {}
    if m.get("error"):
        return _r(SIN_EVALUAR, f"no se pudo armar la memoria: {m['error']}")
    v = m.get("veredicto")
    ev = {"veredicto": v, "reglas": m.get("reglas", 0), **recortar(m.get("errores") or [])}
    if v == "NO CONFORME":
        return _r(FALLA, f"memoria NO CONFORME: {len(m.get('errores') or [])} verificación(es) en "
                         "error", ev)
    if v == "NO CONCLUYENTE" or not v:
        return _r(SIN_EVALUAR, "la memoria no verificó nada (NO CONCLUYENTE)", ev)
    return _r(OK, f"memoria {v}", ev)


def erc(ins: dict) -> dict:
    """El tablero eléctrico sin errores ni avisos del ERC; un aviso JUSTIFICADO por escrito pasa
    (D11 de puerta-sin-sobrediseno), un error nunca."""
    from .justificadas import citar, del_aviso

    reglas = ins.get("electrico") or []
    js = ins.get("justificadas") or []
    malas, justificados = [], []
    for r in reglas:
        if r.get("estado") == "error":
            malas.append(r)
        elif r.get("estado") == "aviso":
            j = del_aviso(r.get("regla"), r.get("elementos"), js)
            (justificados.append({"regla": r.get("regla"), "justificacion": citar(j)}) if j
             else malas.append(r))
    ev = {"reglas": len(reglas), **({"justificados": justificados} if justificados else {})}
    if malas:
        casos = [{"regla": r.get("regla"), "estado": r.get("estado"),
                  "detalle": r.get("detalle")} for r in malas]
        return _r(FALLA, f"{len(malas)} regla(s) del ERC en error o aviso",
                  {**ev, **recortar(casos)},
                  [e for r in malas for e in (r.get("elementos") or [])])
    extra = f" ({len(justificados)} aviso(s) justificado(s))" if justificados else ""
    return _r(OK, f"{len(reglas)} regla(s) del ERC en orden{extra}", ev)


def escenarios(ins: dict) -> dict:
    """Cada escenario de prueba corrido, vigente y pasando: uno que falla = FALLA; sin correr,
    vencido o sin aserciones = SIN_EVALUAR."""
    filas = ins.get("escenarios") or []
    casos = [{"escenario": f.get("escenario"), "estado": f.get("estado"),
              "detalle": f.get("detalle")} for f in filas if f.get("estado") != "ok"]
    if any(f.get("estado") == "error" for f in filas):
        return _r(FALLA, "un escenario de prueba falla", recortar(casos))
    if casos:
        return _r(SIN_EVALUAR, f"{len(casos)} escenario(s) sin correr, vencidos o sin aserciones",
                  recortar(casos))
    return _r(OK, f"{len(filas)} escenario(s) pasan y están vigentes", {"escenarios": len(filas)})


def flujo_de_producto(ins: dict) -> dict:
    """El balance de producto al ritmo nominal (plan balance-de-producto, D9): lo que entra sale
    por sus salidas, sin perdidos, trabados ni retenidos. El margen sobre el nominal es evidencia,
    nunca veredicto (D8)."""
    f = ins.get("flujo") or {}
    ev = {k: f[k] for k in ("nominal", "escenarios", "margen") if f.get(k) is not None}
    estado = f.get("estado")
    if estado == "falla":
        return _r(FALLA, f.get("detalle", ""), ev)
    if estado == "ok":
        return _r(OK, f.get("detalle", ""), ev)
    if estado == "falta":
        return _r(SIN_EVALUAR, f"{f.get('detalle', '')} → {f.get('accion', '')}", ev)
    return _r(SIN_EVALUAR, f"el balance de producto no se evaluó ({f.get('detalle') or 'sin insumo'})", ev)


def soluciones_por_funcion(ins: dict) -> dict:
    """D15: cada familia de función que el modelo tiene (transmisión flexible, apoyo rotativo,
    accionamiento, resguardo, estructura de una máquina con partes móviles) cubierta por una
    función DECLARADA con su solución y ≥ 1 alternativa descartada con su motivo."""
    from .funciones import FAMILIAS_FUNCION, cobertura

    familias = (ins.get("hechos") or {}).get("familias_funcion") or {}
    cub = cobertura(familias, ins.get("funciones") or [])
    sin = [f for f, c in cub.items() if c is None]
    ev = {"familias": {f: {"piezas": len(familias[f]), "cubierta_por": cub[f]} for f in familias}}
    if sin:
        return _r(FALLA, "sin solución declarada para: " + ", ".join(
            f"{f} ({FAMILIAS_FUNCION.get(f, f)})" for f in sin) + ". Declara en `funciones` la "
            "solución elegida y al menos una alternativa descartada con su motivo",
            {**ev, "sin_declarar": sin}, [p for f in sin for p in familias[f][:6]])
    return _r(OK, f"{len(familias)} familia(s) de función con su solución y sus alternativas", ev)


def fabricabilidad(ins: dict) -> dict:
    """Cada pieza es de catálogo o un sólido real (cerrado, con volumen) con material y proceso
    resueltos: nada de geometría a medida que no se puede cortar ni mecanizar."""
    fab = ins.get("fabricacion") or {}
    malas = fab.get("malas") or []
    ev = {"piezas": fab.get("piezas", 0), "de_catalogo": fab.get("catalogo", 0),
          "procesos": fab.get("procesos") or {}, "elemento": "pieza"}
    if malas:
        return _r(FALLA, f"{len(malas)} pieza(s) a medida que no se pueden fabricar así: "
                         f"{malas[0].get('nombre')} ({malas[0].get('motivo')})",
                  {**ev, **recortar(malas)}, [m.get("id") for m in malas])
    return _r(OK, f"{ev['piezas']} pieza(s): {ev['de_catalogo']} de catálogo y el resto con "
                  "material y proceso", ev)


def marcha(ins: dict) -> dict:
    """La máquina andando del video es fiel al modelo (D13 de fabrica-de-publicaciones): la cinta
    animada sale de la sección del sólido y no atraviesa nada."""
    m = ins.get("marcha") or {}
    r = m.get("resultado")
    if r == "ok":
        return _r(OK, f"simulada en {m.get('segundos')} s; la banda animada es fiel al modelo",
                  {"fidelidad": m.get("fidelidad") or [], "avance_mm": m.get("avance_mm")})
    if r == "infiel":
        return _r(FALLA, f"la máquina andando no es fiel al modelo: {m.get('detalle')}",
                  {"motivo": m.get("detalle")})
    return _r(SIN_EVALUAR, f"la marcha no se pudo simular: {m.get('detalle') or 'sin motivo'}")
