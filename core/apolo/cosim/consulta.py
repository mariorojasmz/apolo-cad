"""Lo que el agente lee de una co-simulación (plan V8.3 D13): el resumen compacto y las páginas
de `get_simulation`.

El resultado del worker pesa cientos de KB (las trazas del 73 en 12 s: 0,17 MB; el JSON entero,
0,41 MB). Al agente le llega primero `compacto` (veredicto, aserciones, resumen, los primeros
eventos) y lo demás lo pide por partes:
  - `resumen`: el compacto + los NOMBRES de las señales (discretas y analógicas);
  - `eventos`: paginados;
  - `final`: los valores al final, filtrados por señal;
  - `trazas`: las señales pedidas (nombre exacto, alias del PLC o patrón con `*`) en una ventana
    de tiempo, paginadas (cambios de una discreta o muestras de las analógicas).
Las hipótesis (F6b, defecto 3) se repetían enteras en cada corrida (~1,5 KB de 4–5): el compacto
las trae la PRIMERA vez que salen en el proyecto; si otra corrida ya mostró las mismas (mismo
`hipotesis_id`), sólo su id, cuántas son y en qué corrida salieron. `resumen` las da siempre
completas.
Puro: stdlib, sobre el JSON del resultado.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json

from .flujo import resumen as resumen_flujo
from .veredicto import Lector

EVENTOS_COMPACTO = 30
MAX_SENALES = 20
PARTES = ("resumen", "eventos", "final", "trazas")


def hipotesis_id(hipotesis: list) -> str:
    """Un id corto de la lista de hipótesis (las mismas, en el mismo orden → el mismo id)."""
    texto = json.dumps(list(hipotesis or []), ensure_ascii=False)
    return "h" + hashlib.sha1(texto.encode("utf-8")).hexdigest()[:8]


def _hipotesis(res: dict, vistas_en: str | None) -> dict:
    lista = res.get("hipotesis") or []
    hid = hipotesis_id(lista)
    if not lista or vistas_en is None:
        return {"hipotesis": lista, "hipotesis_id": hid}
    return {"hipotesis_id": hid, "hipotesis_repetidas": {
        "n": len(lista), "como_en": vistas_en,
        "ver": "las mismas que esa corrida: get_simulation(parte='resumen') las da completas"}}


def compacto(res: dict, ver: dict, *, simulacion: str, escenario: str | None,
             hipotesis_vistas_en: str | None = None) -> dict:
    """El resumen corto de una corrida. `hipotesis_vistas_en` = la corrida del proyecto que ya
    mostró estas mismas hipótesis (entonces van sólo por id)."""
    r = res.get("resumen") or {}
    eventos = res.get("eventos") or []
    return {
        "simulacion": simulacion, "escenario": escenario,
        "veredicto": ver["veredicto"], "n_fallidas": ver["n_fallidas"], "aserciones": ver["aserciones"],
        "resumen": {k: r[k] for k in ("duracion_s", "intercambios", "factor_tiempo_real", "t_pared_s",
                                      "huella", "senales", "determinista") if k in r},
        "eventos": eventos[:EVENTOS_COMPACTO], "n_eventos": len(eventos),
        "plc": res.get("plc") or {},
        # plc-en-el-lazo D7: sólo con un PLC externo (sin él, el compacto de siempre)
        **{k: res[k] for k in ("plc_externo", "lazo") if k in res},
        **({"veredicto_motivo": ver["motivo"]} if "motivo" in ver else {}),
        # balance-de-producto D11: sólo con el bloque `flujo` (sin él, el compacto de siempre)
        **({"flujo": f} if (f := resumen_flujo((res.get("mecanica") or {}).get("flujo"))) else {}),
        "avisos": res.get("avisos") or [], **_hipotesis(res, hipotesis_vistas_en),
        "aviso": res.get("aviso"),
        **({"proceso": {k: v for k, v in res["proceso"].items() if k in ("arranque_s", "total_s")}}
           if res.get("proceso") else {}),
    }


def _elegir(lec: Lector, senales) -> tuple[list[str], list[str]]:
    """(nombres, problemas): cada pedido es un nombre (o alias del PLC) o un patrón con `*`."""
    todos, out, problemas = lec.nombres(), [], []
    for s in senales or []:
        if any(c in s for c in "*?["):
            hallados = fnmatch.filter(todos, s)
            out += hallados
            if not hallados:
                problemas.append(f"«{s}» no casa con ninguna señal")
        else:
            n, motivo = lec.resolver(s)
            if n:
                out.append(n)
            else:
                problemas.append(motivo)
    return list(dict.fromkeys(out)), problemas


def _pagina(lista: list, offset: int, limite: int) -> tuple[list, dict]:
    return lista[offset: offset + limite], {"total": len(lista), "offset": offset,
                                            "truncado": offset + limite < len(lista)}


def parte(res: dict, base: dict, que: str, *, senales=None, desde_s=None, hasta_s=None,
          limite: int = 200, offset: int = 0) -> dict:
    """Una parte del resultado `res` (`base` = su compacto). `ValueError` si `que` no vale."""
    if que not in PARTES:
        raise ValueError(f"parte «{que}» no válida; partes: {', '.join(PARTES)}")
    lec = Lector(res)
    limite, offset = max(1, min(int(limite), 2000)), max(0, int(offset))
    if que == "resumen":
        base = {k: v for k, v in base.items() if k != "hipotesis_repetidas"}
        return {**base, "hipotesis": res.get("hipotesis") or [],
                "senales": {"discretas": sorted(lec.disc), "analogicas": sorted(lec.an)}}
    if que == "eventos":
        pag, meta = _pagina(res.get("eventos") or [], offset, limite)
        return {"simulacion": base["simulacion"], "eventos": pag, **meta}
    nombres, problemas = _elegir(lec, senales)
    if que == "final":
        final = lec.final if not senales else {n: lec.final.get(n) for n in nombres}
        return {"simulacion": base["simulacion"], "final": final,
                **({"problemas": problemas} if problemas else {})}
    if not senales:
        raise ValueError("`trazas` pide `senales`: nombres («-M1.rpm», «-K1.cuenta») o patrones "
                         "(«-M1.*»); la lista sale en la parte «resumen»")
    a = 0.0 if desde_s is None else float(desde_s)
    b = lec.dur if hasta_s is None else float(hasta_s)
    recortadas = nombres[MAX_SENALES:]
    nombres = nombres[:MAX_SENALES]
    discretas, an_n = {}, [n for n in nombres if n in lec.an]
    for n in nombres:
        if n in lec.disc:
            cambios = [[t, v] for t, v in lec.disc[n] if a - 1e-9 <= t <= b + 1e-9]
            previo = lec.valor_en(n, a)
            if not cambios or cambios[0][0] > a + 1e-9:
                cambios.insert(0, [a, previo])  # el valor vigente al abrir la ventana
            pag, meta = _pagina(cambios, offset, limite)
            discretas[n] = {"cambios": pag, **meta}
    idx = [k for k, t in enumerate(lec.t) if a - 1e-9 <= t <= b + 1e-9]
    pag, meta = _pagina(idx, offset, limite)
    analogicas = {"t": [lec.t[k] for k in pag],
                  "senales": {n: [lec.an[n][k] for k in pag] for n in an_n}, **meta} if an_n else {}
    return {"simulacion": base["simulacion"], "ventana_s": [a, b], "discretas": discretas,
            "analogicas": analogicas,
            **({"problemas": problemas} if problemas else {}),
            **({"senales_recortadas": len(recortadas)} if recortadas else {})}
