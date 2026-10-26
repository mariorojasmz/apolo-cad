"""El balance de producto de un DOCUMENTO (plan balance-de-producto, D6–D10): el ritmo nominal, si
la máquina mueve producto y la regla de las puertas.

- `ritmo_nominal(doc)`: la capacidad nominal en productos por minuto = `requirements.
  paquetes_por_minuto` (D6: ya existe y la marcha de ejemplo la usa como ritmo);
- `resolver_ritmo(doc, esc)`: `flujo.ritmo_por_min: "nominal"` → el número de hoy (D7). Lo llaman
  `escenarios.poner` (se GUARDA el número: el hash del escenario lo cubre) y el snapshot (una
  corrida inline). Sin capacidad declarada, 400 con cómo declararla;
- `mueve_producto(doc, bandas=)`: productos en algún escenario, o bandas + tablero (D9: sin
  tablero no hay co-simulación);
- `evaluar(doc, mueve=)`: la regla general (D9): `ok` | `falta` | `falla` | `no_aplica`, con la
  acción que falta, las incidencias (producto, lugar, hora) y el margen como DATO (D8);
- `regla_entrega(doc)`: la fila de la puerta de entrega (D10), sólo con escenarios declarados.
Sin locks: el llamador sostiene STATE_LOCK.
"""

from __future__ import annotations

import copy

from .errors import ServiceError

CLAVE_RITMO = "paquetes_por_minuto"
ACCION = ("declara un escenario de flujo al ritmo nominal: set_scenario con "
          "«flujo»: {\"ritmo_por_min\": \"nominal\", \"plazo_s\": …}, los sumideros de "
          "mecanica.sumideros con «nombre» (las salidas) y la aserción «flujo.cuadra al_final»; "
          "córrelo con simulate(escenario=…)")


def ritmo_nominal(doc) -> float | None:
    v = (doc.requirements or {}).get(CLAVE_RITMO)
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else None


def resolver_ritmo(doc, esc):
    """El escenario con «nominal» reemplazado por la capacidad de hoy (una copia); sin
    «nominal», el MISMO objeto (un escenario sin flujo no cambia ni de identidad)."""
    if not isinstance(esc, dict):
        return esc
    f = esc.get("flujo")
    if not (isinstance(f, dict) and isinstance(f.get("ritmo_por_min"), str)
            and f["ritmo_por_min"].strip().lower() == "nominal"):
        return esc
    nominal = ritmo_nominal(doc)
    if nominal is None:
        raise ServiceError(400, "flujo: «ritmo_por_min»: «nominal» es la capacidad nominal del "
                                "documento y no está declarada: set_requirements "
                                f"{{\"{CLAVE_RITMO}\": 30}} (productos por minuto), o escribe el número")
    out = copy.deepcopy(esc)
    out["flujo"]["ritmo_por_min"] = nominal
    return out


def _con_productos(doc) -> bool:
    return any(isinstance(e, dict) and e.get("tipo") == "producto"
               for ent in doc.escenarios.values() for e in (ent["escenario"].get("eventos") or []))


def mueve_producto(doc, bandas: int | None = None) -> bool:
    """D9: productos en algún escenario, o bandas (`bandas` = cuántas, si el llamador ya las
    contó) con tablero."""
    if _con_productos(doc):
        return True
    from .electrico import tiene_carril

    if not tiene_carril(doc):
        return False
    if bandas is None:
        from .calidad_tensores import lazos_banda

        bandas = len(lazos_banda(doc))
    return bandas > 0


def _fila(doc, nombre: str, firma: str, cache: dict) -> dict | None:
    from apolo.cosim.escenario import EscenarioInvalido, leer_escenario

    from .escenarios import estado

    ent = doc.escenarios[nombre]
    esc = ent["escenario"]
    if not isinstance(esc, dict) or esc.get("flujo") is None:
        return None
    try:
        e = leer_escenario(esc)
    except EscenarioInvalido:
        return None
    fl = (ent.get("resultado") or {}).get("flujo") or {}
    return {"escenario": nombre, "ritmo_por_min": e.flujo["ritmo_por_min"],
            "balance_asertado": any(a["senal"] == "flujo.cuadra" for a in e.aserciones),
            "estado": estado(doc, nombre, firma, cache)["estado"],
            **({"cuadra": fl["cuadra"], "balance": fl.get("balance")} if "cuadra" in fl else {}),
            "_flujo": fl}


def evaluar(doc, *, mueve: bool | None = None, bandas: int | None = None) -> dict:
    """La regla general (D9): {estado: ok|falta|falla|no_aplica, detalle, accion?, nominal,
    escenarios, margen, incidencias?}."""
    from apolo.cosim.flujo import TOL_RITMO, incidencias

    from .escenarios import firma_documento

    if mueve is None:
        mueve = mueve_producto(doc, bandas)
    if not mueve:
        return {"estado": "no_aplica", "detalle": "la máquina no mueve producto que se pueda "
                "co-simular (sin productos en sus escenarios ni bandas con tablero)"}
    nominal = ritmo_nominal(doc)
    firma, cache = firma_documento(doc), {}
    filas = [f for f in (_fila(doc, n, firma, cache) for n in doc.escenarios) if f is not None]
    publicas = [{k: v for k, v in f.items() if k != "_flujo"} for f in filas]
    base = {"nominal": nominal, "escenarios": publicas}
    if nominal is None:
        return {**base, "estado": "falta", "detalle": "la máquina mueve producto y no declara su "
                "capacidad nominal", "accion": f"set_requirements {{\"{CLAVE_RITMO}\": <productos por "
                "minuto>}} y " + ACCION}
    al_nominal = [f for f in filas if f["ritmo_por_min"] and f["ritmo_por_min"] >= nominal * (1 - TOL_RITMO)
                  and f["balance_asertado"]]
    margen = [{"escenario": f["escenario"], "ritmo_por_min": f["ritmo_por_min"],
               "sobre_nominal_pct": round(100.0 * (f["ritmo_por_min"] / nominal - 1.0), 1),
               **({"cuadra": f["cuadra"], "balance": f["balance"]} if "cuadra" in f else
                  {"estado": f["estado"]})}
              for f in filas if f["ritmo_por_min"] and f["ritmo_por_min"] > nominal * (1 + TOL_RITMO)
              and not f["balance_asertado"]]
    base["margen"] = margen
    vigentes = [f for f in al_nominal if f["estado"] in ("pasa", "falla") and "cuadra" in f]
    rotos = [f for f in vigentes if not f["cuadra"]]
    if rotos:
        f = rotos[0]
        return {**base, "estado": "falla", "incidencias": incidencias(f["_flujo"]),
                "detalle": f"«{f['escenario']}» a {f['ritmo_por_min']:g}/min (nominal {nominal:g}/min): "
                           f"el balance no cuadra ({f.get('balance')}): {incidencias(f['_flujo'])}"}
    if vigentes:
        f = vigentes[0]
        return {**base, "estado": "ok", "detalle": f"«{f['escenario']}» a {f['ritmo_por_min']:g}/min "
                                                   f"(nominal {nominal:g}/min) cuadra: {f.get('balance')}"}
    if al_nominal:
        quien = ", ".join(f"«{f['escenario']}» ({f['estado']})" for f in al_nominal)
        return {**base, "estado": "falta", "detalle": f"el escenario de flujo al ritmo nominal no tiene "
                f"un resultado vigente: {quien}", "accion": "córrelo con simulate(escenario=…)"}
    bajos = [f"«{f['escenario']}» a {f['ritmo_por_min'] or 0:g}/min"
             + ("" if f["balance_asertado"] else " sin «flujo.cuadra»") for f in filas]
    return {**base, "estado": "falta", "accion": ACCION,
            "detalle": f"ningún escenario prueba el balance al ritmo nominal ({nominal:g}/min)"
                       + (f"; los de flujo: {', '.join(bajos)}" if bajos else "")}


def regla_entrega(doc) -> dict | None:
    """La fila de la puerta de entrega (D10): None sin escenarios o si la máquina no mueve
    producto (la puerta da lo de siempre); `error` si el balance vigente no cuadra; `aviso` si
    falta el escenario, la capacidad o su corrida; `ok` si cuadra."""
    if not doc.escenarios:
        return None
    r = evaluar(doc)
    estado = {"ok": "ok", "falla": "error", "falta": "aviso"}.get(r["estado"])
    if estado is None:
        return None
    return {"estado": estado, "detalle": r["detalle"] + (f" → {r['accion']}" if r.get("accion") else "")}
