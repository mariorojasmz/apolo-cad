"""Lo que la persona VE del circuito de aire (plan V8.9 D12, F6): la ÚNICA fuente del panel
«Neumática» del visor (`GET /api/neumatica`). No decide ninguna regla: cuenta en palabras de la
persona (sin comandos ni parámetros: ui/CLAUDE.md § Texto) lo que ya dicen el ERC neumático
(`neumatica.reglas`, el mismo de `electrical_check` y de la puerta de entrega) y la memoria del
aire (`neumatica.memoria`, la misma de `calc_report`), y señala DÓNDE (las piezas que encuadra la
cámara). El llamador sostiene `STATE_LOCK`.

- `veredicto`: UNO, con la regla de `tablero_panel.veredicto` (= `ui/src/diseno/atencion.ts`).
- `items`: lo que pide atención, cada uno con su frase y sus cifras escritas, las piezas del
  aparato y el texto crudo del cálculo en `tecnico`. Las reglas que la memoria repite por
  cilindro con la velocidad MEDIDA (el pico de los escenarios vigentes) (pandeo, energía al fin de carrera,
  relación de carga) salen de la memoria y no se duplican desde el ERC.
- `detalle.cilindros`: fuerza, consumo por ciclo y por minuto y tiempo de carrera de cada
  cilindro (medido en el escenario vigente NOMINAL —carrera completa, sin falla: F7b— o, sin él,
  la cota a mano), de las cifras de
  las filas de la memoria (`valor`); `detalle.maquina`: la demanda de aire.
- `esquema`: la lámina ISO 1219 para dibujar en línea (`neumatica_vista.esquema`).
Sin aire en el documento: `{"hay_aire": false}` (el panel muestra su estado vacío).
"""

from __future__ import annotations

import re

from .tablero_panel import NBSP, item, veredicto

FRASE_BIEN = "El circuito de aire cumple"
FRASE_PARCIAL = "El circuito de aire cumple lo que revisamos"
SEVERIDAD = {"error": "falla", "aviso": "aviso"}
#: reglas del ERC que la memoria repite por cilindro con la velocidad medida: el panel dice la suya
DE_LA_MEMORIA = {"pandeo del vástago", "energía al fin de carrera", "relación de carga", "amortiguador externo"}
#: reglas del ERC que se juntan en un ítem con la cuenta (un hallazgo por puerto o por tubo)
SE_JUNTAN = {"aislamiento del aire", "tubo sin puerto", "puerto libre", "escape sin silenciador"}


# ── cómo se escribe ────────────────────────────────────────────────────────────────────────


def n(valor: float, decimales: int = 0, unidad: str = "") -> str:
    """Una cifra como `cifra()` de la UI: coma decimal, espacio fino de miles, la unidad pegada con
    un espacio que no se corta («1,8 kN», «45,9 NL/min»)."""
    ent, _, dec = f"{abs(valor):.{decimales}f}".partition(".")
    miles = re.sub(r"\B(?=(\d{3})+(?!\d))", " ", ent)
    signo = "−" if valor < 0 and float(f"{abs(valor):.{decimales}f}") != 0 else ""
    num = f"{signo}{miles}{',' + dec if dec else ''}"
    return f"{num}{NBSP}{unidad}" if unidad else num


def fuerza(newton: float) -> str:
    return n(newton / 1000, 1, "kN") if abs(newton) >= 1000 else n(newton, 0, "N")


def limpio(texto: str) -> str:
    """El texto de una regla para la persona: sin comillas de código y con coma decimal."""
    t = re.sub(r"`([^`]*)`", r"\1", texto or "")
    return re.sub(r"(?<=\d)\.(?=\d)", ",", t).strip()


def _lista(cosas: list[str], tope: int = 3) -> str:
    if len(cosas) <= tope:
        return ", ".join(cosas[:-1]) + (" y " if len(cosas) > 1 else "") + cosas[-1] if cosas else ""
    return f"{', '.join(cosas[:tope])} y {len(cosas) - tope} más"


def _tecnico(filas: list[dict]) -> str:
    return " ".join(f"{f['detalle']}{(' ' + f['recomendacion']) if f.get('recomendacion') else ''}" for f in filas)


# ── las piezas que se señalan ──────────────────────────────────────────────────────────────


def piezas_de(doc, m) -> dict[str, list[str]]:
    """{designación: piezas} de cada aparato de aire ligado a su pieza: la ligada primero y luego
    las que creó el MISMO comando (el cilindro: cuerpo, vástago, accesorio y empujador)."""
    escena = getattr(doc, "scene", {}) or {}
    out: dict[str, list[str]] = {}
    for d in m.dispositivos:
        if getattr(d, "neumatico", None) is None or not d.pieza or d.pieza not in escena:
            continue
        cid = escena[d.pieza].command_id
        out[d.designacion] = [d.pieza] + [fid for fid, f in escena.items() if f.command_id == cid and fid != d.pieza]
    return out


def _de(elementos: list[str]) -> list[str]:
    out = []
    for e in elementos or []:
        des = e.rpartition(":")[0] if ":" in e else e
        if des and des not in out:
            out.append(des)
    return out


# ── lo que pide atención ───────────────────────────────────────────────────────────────────


def _frase_erc(regla: str, filas: list[dict]) -> tuple[str, str | None]:
    """(frase, detalle) de un hallazgo del ERC (o de varios juntos)."""
    f0 = filas[0]
    des = _de(f0.get("elementos") or [])
    uno = des[0] if des else ""
    k = len(filas)
    if regla == "aislamiento del aire":
        return ("El aire no se puede aislar para el mantenimiento",
                "Falta la válvula de corte con escape a la entrada, después del filtro-regulador, o alguna "
                "válvula no se alimenta desde ella: al cortar el aire, el que queda atrapado puede mover el cilindro.")
    if regla == "tubo sin puerto":
        return ("Un tubo no une dos puertos de aire" if k == 1 else f"{k} tubos no unen dos puertos de aire",
                "Cada tubo va de un puerto de aire a otro; las bobinas se cablean aparte.")
    if regla == "puerto libre":
        puertos = [e for f in filas for e in f.get("elementos") or []]
        return (f"El puerto {puertos[0]} no tiene tubo" if k == 1 else f"{k} puertos sin tubo: {_lista(puertos)}", None)
    if regla == "escape sin silenciador":
        return ("Un escape descarga sin silenciador" if k == 1 else f"{k} escapes descargan sin silenciador",
                "La descarga sin silenciador hace ruido.")
    if regla == "presión de trabajo":
        if f0["estado"] == "error":
            return f"{uno} recibe una presión fuera de su rango", limpio(f0["detalle"])
        if "no está declarada" in f0["detalle"]:
            return f"Falta la presión regulada de {uno}", "La fija el instalador en el filtro-regulador."
        return f"No sabemos qué presión les llega a {_lista(des)}", limpio(f0["detalle"])
    if regla == "servicio del cilindro":
        return (f"Falta el trabajo de {_lista(des)}",
                "Sin su carrera, su velocidad y su carga no revisamos el pandeo, el golpe al final ni el caudal.")
    if regla == "caudal de la válvula":
        return f"La válvula de {uno} no alcanza la velocidad pedida", limpio(f0["detalle"])
    if regla == "regulación de velocidad":
        return f"{uno} no regula su velocidad por el escape", limpio(f0["detalle"])
    texto = limpio(f0["detalle"])
    return texto.split(": ", 1)[0] if len(texto) > 90 else texto, texto


def _frase_memoria(f: dict) -> tuple[str, str | None]:
    regla, v = f["regla"], f.get("valor") or {}
    des = (f.get("elementos") or [""])[0]
    if regla == "pandeo del vástago" and "F_adm_N" in v and f.get("estado") != "error":
        # el aviso de λ bajo sin fy (calculo.pandeo_vastago): Euler puede sobreestimar, no pandea
        return (f"Falta el límite elástico del vástago de {des}",
                f"Es corto para la fórmula de Euler (λ = {n(v.get('lambda', 0), 0)}) y da un factor de seguridad "
                f"de {n(v['fs'], 2)}; sin el límite elástico no se verifica con Johnson. Declara el material del "
                "vástago.")
    if regla == "pandeo del vástago" and "F_adm_N" in v:
        return (f"El vástago de {des} pandea: admite {fuerza(v['F_adm_N'])} contra {fuerza(v['F_N'])}",
                f"Con {n(v.get('largo_mm', 0), 0, 'mm')} libres el factor de seguridad queda en "
                f"{n(v['fs'], 2)} y pedimos 3. Lo resuelve un vástago mayor, menos carrera libre, un montaje "
                "más rígido o una guía.")
    if regla == "energía al fin de carrera" and "E_J" in v:
        return (f"{des} llega a {n(v['v_m_s'], 2, 'm/s')} y su amortiguación admite {n(v['E_adm_J'], 1, 'J')}: "
                f"llega con {n(v['E_J'], 1, 'J')}",
                "Lo resuelve un regulador de caudal por el escape (menos velocidad), un amortiguador externo o un "
                "cilindro mayor.")
    if regla == "relación de carga" and "eta" in v:
        if f["estado"] == "error":
            return (f"{des} no mueve su carga: pide {fuerza(v['F_req_N'])} y empuja {fuerza(v['F_teorica_N'])} "
                    "teóricos", "Un cilindro de más diámetro, más presión (dentro de la ficha) o menos carga.")
        return (f"{des} va muy cargado: usa el {n(100 * v['eta'], 0, '%')} de su fuerza (tope "
                f"{n(100 * v['tope'], 0, '%')})", "Un cilindro de más diámetro o más presión le da margen.")
    if regla == "caudal pico de la válvula" and "q_pico_NL_min" in v:
        return (f"{v.get('valvula', 'La válvula')} pasa {n(v['q_disponible_NL_min'], 0, 'NL/min')} y {des} pide "
                f"{n(v['q_pico_NL_min'], 0, 'NL/min')} de pico",
                "Una válvula de más caudal, menos velocidad o tubos y racores más grandes.")
    if regla == "tiempo de carrera":
        med = v.get("medido") or {}
        if med.get("x_max_mm") is not None and med["x_max_mm"] < v.get("carrera_mm", 0) - 2:
            return (f"{des} no llega al final de su carrera: {n(med['x_max_mm'], 0)} de "
                    f"{n(v['carrera_mm'], 0, 'mm')}", f"Lo midió el escenario «{med.get('escenario', '')}».")
        return f"Revisa el tiempo de carrera de {des}", limpio(f["detalle"])
    if regla == "caudal de la unidad de mantenimiento" and "q_pico_NL_min" in v:
        return (f"{des} pasa {n(v['q_disponible_NL_min'], 0, 'NL/min')} y la máquina pide "
                f"{n(v['q_pico_NL_min'], 0, 'NL/min')} de pico", "Una unidad de mantenimiento de más caudal.")
    if regla == "amortiguador externo" and "n_max_ciclos_min" in v and "ciclos_min" in v:
        entran = (f["recomendacion"].split("Entra con estas cifras: ", 1)[1].rstrip(".")
                  if "Entra con estas cifras: " in (f.get("recomendacion") or "") else "")
        return (f"El amortiguador de {des} al {v.get('extremo', '')} recibe {n(v['ciclos_min'], 0)} golpes por minuto "
                f"y admite {n(v['n_max_ciclos_min'], 0)}",
                f"Entra uno de este tamaño: {entran}." if entran else
                "Ninguno del catálogo entra: menos ciclos, menos velocidad o menos presión.")
    if regla == "demanda de aire":
        sin = v.get("sin_fugas_NL_min", v.get("NL_min"))
        return ("Faltan las fugas de la red de aire",
                f"Sin ese dato, la demanda de la máquina va sin fugas: {n(sin or 0, 1, 'NL/min')}.")
    texto = limpio(f["detalle"])
    return texto, None


def items(erc: list[dict], mem: list[dict], m, piezas: dict[str, list[str]]) -> list[dict]:
    from apolo.library.neumatica.memoria import ALCANCE

    def donde(elementos) -> list[str]:
        return [p for des in _de(elementos) for p in piezas.get(des, [])]

    de_mem = {(f["regla"], (f.get("elementos") or [""])[0]) for f in mem}
    out: list[dict] = []
    grupos: dict[tuple, list[dict]] = {}
    for f in erc:
        if f["estado"] not in SEVERIDAD:
            continue
        if f["regla"] in DE_LA_MEMORIA and (f["regla"], (f.get("elementos") or [""])[0]) in de_mem:
            continue
        clave = (f["regla"], f["estado"]) if f["regla"] in SE_JUNTAN else (f["regla"], f["estado"], len(grupos))
        grupos.setdefault(clave, []).append(f)
    for i, (clave, filas) in enumerate(grupos.items()):
        frase, detalle = _frase_erc(clave[0], filas)
        els = [e for f in filas for e in f.get("elementos") or []]
        out.append(item(f"erc-{i}", SEVERIDAD[clave[1]], frase, piezas=donde(els), detalle=detalle,
                        tecnico=_tecnico(filas)))
    for i, f in enumerate(mem):
        if f["estado"] not in SEVERIDAD or f["regla"] == ALCANCE:
            continue
        frase, detalle = _frase_memoria(f)
        out.append(item(f"memoria-{i}", SEVERIDAD[f["estado"]], frase, piezas=donde(f.get("elementos")),
                        detalle=detalle, tecnico=_tecnico([f])))
    # lo que la memoria no pudo revisar por falta de velocidad (ni declarada ni medida): sin evaluar
    con_golpe = {(f.get("elementos") or [""])[0] for f in mem
                 if f["regla"] in ("energía al fin de carrera", "amortiguador externo")}
    for d in m.dispositivos:
        if getattr(d, "neumatico", None) is not None and d.neumatico.tipo == "cilindro" and d.servicio \
                and d.designacion not in con_golpe:
            out.append(item(f"sin-velocidad-{d.designacion}", "sin_evaluar",
                            f"Sin la velocidad de {d.designacion} no revisamos el golpe al final ni el caudal",
                            piezas=piezas.get(d.designacion, []),
                            detalle="Corre un escenario que lo mueva, o pídele al agente que declare su velocidad."))
    # el amortiguador externo sin cadencia ni capacidad: su energía por hora, sin evaluar
    for f in erc:
        if f["regla"] == "amortiguador externo" and "SIN EVALUAR" in f["detalle"]:
            des = (f.get("elementos") or [""])[0]
            out.append(item(f"sin-ritmo-{des}-{len(out)}", "sin_evaluar",
                            f"Sin la cadencia de {des} no revisamos los golpes por minuto ni la energía por hora de su amortiguador",
                            piezas=piezas.get(des, []),
                            detalle="Pídele al agente que declare la cadencia del cilindro o la capacidad de la máquina."))
    return out


# ── el detalle ─────────────────────────────────────────────────────────────────────────────


def cilindros(m, mem: list[dict], piezas: dict[str, list[str]]) -> list[dict]:
    por = {(f["regla"], (f.get("elementos") or [""])[0]): f.get("valor") or {} for f in mem}
    out = []
    for d in m.dispositivos:
        if getattr(d, "neumatico", None) is None or d.neumatico.tipo != "cilindro":
            continue
        des, mod = d.designacion, d.neumatico.modelo
        fila: dict = {"designacion": des, "ref": d.ref, "piezas": piezas.get(des, []),
                      "diametro_mm": mod.get("D_mm"), "vastago_mm": mod.get("d_mm")}
        if (d.servicio or {}).get("carrera_mm"):
            fila["carrera_mm"] = d.servicio["carrera_mm"]
        fz = por.get(("fuerza del cilindro", des))
        if fz:
            fila["fuerza"] = {k: fz[k] for k in ("F_avance_N", "F_avance_ef_N", "F_retroceso_N", "F_retroceso_ef_N",
                                                 "p_bar") if k in fz}
        co = por.get(("consumo de aire", des))
        if co:
            fila["consumo"] = {"ciclo_NL": co.get("ciclo_NL"), **({"NL_min": co["NL_min"]} if "NL_min" in co else {}),
                               **({"ciclos_min": d.servicio["ciclos_min"]} if d.servicio.get("ciclos_min") else {})}
        ti = por.get(("tiempo de carrera", des))
        if ti:
            med = ti.get("medido") or {}
            if med.get("t_avance_s") is not None:
                fila["tiempo"] = {"origen": "medido", "escenario": med.get("escenario", ""),
                                  "avance_s": med["t_avance_s"], "retroceso_s": med.get("t_retroceso_s")}
            else:
                fila["tiempo"] = {"origen": "estimado", "avance_s": ti["t_avance_s"], "retroceso_s": ti["t_retroceso_s"]}
        out.append(fila)
    return out


def panel(doc) -> dict:
    """El panel «Neumática» del documento (ver el docstring del módulo)."""
    from .electrico import modelo
    from .neumatica import hay_aire, memoria, reglas
    from .neumatica_vista import esquema

    m = modelo(doc)
    if not hay_aire(m):
        return {"hay_aire": False}
    erc, mem = reglas(m, doc), memoria(doc)
    piezas = piezas_de(doc, m)
    its = items(erc, mem, m, piezas)
    v = veredicto(its, FRASE_BIEN, FRASE_PARCIAL)
    n_reglas = len({f["regla"] for f in erc})
    n_calc = sum(1 for f in mem if "calc" in f)
    v["nota"] = f"Revisamos {n_reglas} reglas del circuito y {n_calc} cálculos de la memoria"
    demanda = next((f.get("valor") or {} for f in mem if f["regla"] == "demanda de aire"), {})
    esq = esquema(doc, m, piezas)
    return {
        "hay_aire": True,
        "veredicto": v,
        "items": its,
        "detalle": {"cilindros": cilindros(m, mem, piezas),
                    "maquina": {k: demanda[k] for k in ("NL_min", "sin_fugas_NL_min") if k in demanda}},
        "esquema": esq,
        "nombres": nombrar(doc, m, {s.get("designacion") for s in esq.get("simbolos") or ()}),
    }


def nombrar(doc, m, tambien: set | None = None) -> dict:
    """Plan nombres-por-funcion F1 (clave AGREGADA; F4 la muestra): {designación: {rotulo, origen,
    estados?, descripcion?}} de cada aparato de aire y de lo que dibuja el esquema (el detector de
    fin de carrera); la válvula trae sus `estados` por posición del carrete. Los textos de los
    ítems siguen con la designación."""
    from .nombres_aparatos import Nombres

    n = Nombres(doc, m)
    out = {}
    for d in m.dispositivos:
        if getattr(d, "neumatico", None) is None and d.designacion not in (tambien or ()):
            continue
        f = n.fila(d.designacion)
        out[d.designacion] = {k: f[k] for k in ("rotulo", "origen", "estados", "descripcion") if k in f}
    return out
