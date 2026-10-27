"""Control del TENSOR (plan puerta-de-publicacion, D3). Puro: recibe los lazos (bandas y cadenas)
con los tensores RECONOCIDOS que actúan sobre cada uno (los arma `services/calidad_tensores.py`)
y devuelve ítems de la ficha de calidad.

Un lazo (dict):

    {"id", "nombre", "tipo": "banda"|"cadena", "largo_mm": float|None, "motivo": str,
     "tensores": [{"tipo": "take_up"|"catalogo"|"plantilla"|"declarado", "id", "nombre",
                   "carrera_mm": float|None, "motivo": str,
                   "pernos": [{"insumo": <insumo de agarre>, "movil": fid,
                               "antes": mm, "despues": mm}],
                   # sólo en bandas (D1 de puerta-sin-sobrediseno, `services/calidad_tensores_lazo`):
                   "tambor": int|None, "factor_lazo": float|None, "abrazamiento_deg": float|None,
                   "factor_motivo": str}]}

`pernos` son los pernos que MUEVEN la pieza tensada (`movil`): la pieza corre `antes` mm hacia la
cabeza y `despues` mm hacia la punta sobre el eje del perno (la carrera es la suma).

`factor_lazo` es lo que alarga el LAZO cada mm que corre el tambor (|Σ d·ê_k| sobre los ramales
libres de su tambor: 2 en un tambor de cola con 180° que corre a lo largo de sus ramales, menos en
un desvío); None (sin línea media, sin dirección o fuera de [0, 2]) cuenta 1, como antes, y la
evidencia dice por qué. `tambor` agrupa los tensores que mueven el MISMO tambor (las dos UCT de un
eje): cuentan una vez, con el menor aporte del grupo.

Los requisitos:
- **reconocido**: todo lazo tiene un mecanismo de tensado reconocido (`create_take_up`, unidad
  de catálogo con su carrera de ficha, las ranuras del motor de la plantilla de rodillos o el
  metadato `tensores`); sin él, SIN_EVALUAR (no se sabe si se puede tensar). Excepción D3b: un
  lazo de cadena entre dos ruedas de ejes FIJOS (`centros_fijos` en el lazo: todo `create_chain`
  sin tensor, lo cree la plantilla de rodillos o el modelo a mano) va SIN tensor si sus centros
  son los exactos de sus eslabones dentro de `TOL_CENTROS_MM`: OK «sin tensor: centros exactos»,
  con el criterio de reemplazo al 3 % para el mantenimiento (precedente: los transportadores de
  rodillos vivos lazo a lazo comerciales van a centros fijos). Es un criterio GENERAL (D14), no de
  la plantilla: la F6 lo sacó de `create_roller_conveyor`;
- **carrera**: banda: lo que RECUPERAN del lazo sus tensores (Σ por tambor de carrera × factor:
  D1 y D2 de puerta-sin-sobrediseno; se ajustan por separado y se suman) ≥ 1 % del largo del lazo
  + 20 mm de montaje (estiramiento de servicio de una banda de PVC de 2 capas 0,5–1 %: CEMA y
  fabricantes). La evidencia lista el aporte de cada tambor y nombra los tensores que NO hacen
  falta (sin ellos el lazo sigue cumpliendo: voraz, del de más carrera al de menos), como nota.
  Cadena: carrera de centros del MEJOR tensor ≥ 3 % del largo / 2 (estirado de reemplazo del 3 %,
  Tsubaki/Renold: la regla de la plantilla; ya está en centros, sin factor ni suma);
- **agarre en toda la carrera**: cada perno tensor de CADA tensor del lazo pasa el control de
  agarre con la pieza tensada en los DOS extremos de su carrera (`agarre.evaluar_perno` con la
  pieza corrida).
"""

from __future__ import annotations

from .agarre import evaluar_perno
from .item import FALLA, MAX_CASOS, NO_APLICA, OK, SIN_EVALUAR, Item, peor, recortar

ESTIRAMIENTO_BANDA = 0.01   # 1 % del largo del lazo
MONTAJE_BANDA_MM = 20.0     # + 20 mm para montar la banda
ESTIRADO_CADENA = 0.03      # 3 % del largo; la carrera de centros es la mitad
_EJES = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}


def carrera_requerida(tipo: str, largo_mm: float) -> float:
    if tipo == "banda":
        return ESTIRAMIENTO_BANDA * largo_mm + MONTAJE_BANDA_MM
    return ESTIRADO_CADENA * largo_mm / 2.0


def _criterio(tipo: str) -> str:
    return ("lazo recuperado (Σ carrera × factor) ≥ 1 %·L + 20 mm" if tipo == "banda"
            else "carrera de centros ≥ 3 %·L / 2")


def agarre_en_carrera(t: dict) -> tuple[str, str, list]:
    """(estado, texto, casos) del agarre de los pernos de un tensor en los dos extremos."""
    if not t.get("pernos"):
        return NO_APLICA, "sin perno tensor modelado (mecanismo integrado o declarado)", []
    casos, estados = [], []
    for pr in t["pernos"]:
        p = pr["insumo"]
        for extremo, delta in (("hacia la cabeza", -float(pr["antes"])),
                               ("hacia la punta", float(pr["despues"]))):
            r = evaluar_perno(p, {pr["movil"]: delta})
            malos = [(k, r[k]) for k in ("cruza", "retencion") if r[k][0] != OK]
            e = peor([r["cruza"][0], r["retencion"][0]])
            estados.append(e)
            if malos:
                casos.append({"perno": p["fid"], "extremo": extremo, "desplazamiento_mm":
                              round(delta, 1), "estado": e,
                              "detalle": "; ".join(f"{k}: {v[1]}" for k, v in malos)})
    estado = peor(estados)
    return estado, ("en los dos extremos de la carrera" if estado == OK
                    else f"{len(casos)} extremo(s) sin agarre"), casos


def _mejor(tensores: list[dict]) -> dict:
    """El tensor de MÁS carrera (el que nombra el reconocimiento y decide en una cadena)."""
    con = [t for t in tensores if t.get("carrera_mm") is not None]
    return max(con, key=lambda t: t["carrera_mm"]) if con else tensores[0]


def _aporte(t: dict, tipo: str) -> dict:
    carrera = float(t["carrera_mm"])
    f = t.get("factor_lazo") if tipo == "banda" else 1.0
    a = {"tensor": t["id"], "nombre": t["nombre"], "carrera_mm": round(carrera, 1),
         "factor": 1.0 if f is None else f, "lazo_mm": carrera * (1.0 if f is None else f)}
    if t.get("abrazamiento_deg") is not None:
        a["abrazamiento_deg"] = t["abrazamiento_deg"]
    if f is None and tipo == "banda":
        a["nota"] = f"factor 1: {t.get('factor_motivo') or 'sin la línea media del lazo'}"
    return a


def aportes(tensores: list[dict], tipo: str) -> list[dict]:
    """Un aporte por TAMBOR (los tensores con carrera de un mismo `tambor` cuentan una vez, con el
    menor): [{tensor, nombre, carrera_mm, factor, lazo_mm, tensores, nombres, nota?}], en mm de
    lazo (en una cadena, de centros)."""
    grupos: dict = {}
    for t in tensores:
        if t.get("carrera_mm") is None:
            continue
        clave = t["id"] if t.get("tambor") is None else ("tambor", t["tambor"])
        grupos.setdefault(clave, []).append(_aporte(t, tipo))
    out = []
    for grupo in grupos.values():
        a = min(grupo, key=lambda x: x["lazo_mm"])
        out.append({**a, "tensores": [x["tensor"] for x in grupo],
                    "nombres": [x["nombre"] for x in grupo]})
    return out


def sobrantes(aps: list[dict], pide: float) -> list[dict]:
    """Los aportes que se pueden quitar y el lazo sigue cumpliendo (D2): voraz, del de más carrera
    (el mecanismo más grande) al de menos; lo quitado queda quitado."""
    total = sum(a["lazo_mm"] for a in aps)
    out = []
    for a in sorted(aps, key=lambda x: (-x["carrera_mm"], -x["lazo_mm"])):
        if total - a["lazo_mm"] >= pide - 1e-6:
            total -= a["lazo_mm"]
            out.append(a)
    return out


def _carrera(lazo: dict, tensores: list[dict], nums: dict) -> tuple:
    tipo = lazo["tipo"]
    pide = carrera_requerida(tipo, lazo["largo_mm"])
    aps = aportes(tensores, tipo)
    if tipo != "banda":  # cadena: el mejor, en centros (sin factor ni suma)
        aps = [max(aps, key=lambda a: a["lazo_mm"])]
    total = sum(a["lazo_mm"] for a in aps)
    estado = OK if total >= pide - 1e-6 else FALLA
    n = {**nums, "carrera_mm": round(max(a["carrera_mm"] for a in aps), 1),
         "pide_mm": round(pide, 1), "criterio": _criterio(tipo)}
    if tipo != "banda":
        return estado, f"carrera {total:.1f} mm; pide {pide:.1f} mm ({_criterio(tipo)})", n
    n["lazo_recuperado_mm"] = round(total, 1)
    n["aportes"] = [{**a, "lazo_mm": round(a["lazo_mm"], 1)} for a in aps]
    sin = [t["nombre"] for t in tensores if t.get("carrera_mm") is None]
    if sin:
        n["sin_carrera"] = sin
    partes = "; ".join(f"{a['nombre']}: {a['carrera_mm']:g} × {a['factor']:.2f} = "
                       f"{a['lazo_mm']:.1f}" for a in aps)
    txt = (f"los tensores recuperan {total:.1f} mm de lazo ({partes}); pide {pide:.1f} mm "
           f"({_criterio(tipo)})")
    if estado == OK and (sob := sobrantes(aps, pide)):
        n["no_hacen_falta"] = [nm for a in sob for nm in a["nombres"]]
        txt += f"; no hacen falta: {', '.join(n['no_hacen_falta'])}"
    return estado, txt, n


def _agarre(tensores: list[dict]) -> tuple[str, str, list]:
    """El agarre de CADA tensor del lazo (D2): el peor, con los casos de todos."""
    res = [(t, *agarre_en_carrera(t)) for t in tensores]
    estado = peor([e for _t, e, _x, _c in res])
    casos = [{"tensor": t["id"], **c} for t, _e, _x, cs in res for c in cs]
    if estado == NO_APLICA:
        return estado, res[0][2], casos
    con = sum(1 for _t, e, _x, _c in res if e != NO_APLICA)
    return estado, (f"en los dos extremos de la carrera ({con} tensor(es) con perno)"
                    if estado == OK else f"{len(casos)} extremo(s) sin agarre"), casos


def reemplazo_cadena(paso_mm: float) -> str:
    """El criterio de reemplazo de una cadena sin tensor (D3b), medible en el taller."""
    nueva = 20 * paso_mm
    return (f"reemplaza la cadena cuando se estire un 3 %: mide 20 pasos con la cadena tensa "
            f"(nueva {nueva:.1f} mm) y cámbiala al llegar a {nueva * (1 + ESTIRADO_CADENA):.1f} mm")


def centros_fijos(lazo: dict) -> tuple | None:
    """D3b: un lazo de cadena de centros FIJOS (sin tensor, de cualquier comando) se acepta si
    sus centros son los exactos de su número de eslabones y la holgura queda dentro de la
    tolerancia (`TOL_CENTROS_MM`). (estado, texto, números), o None si el lazo no trae la medida
    (no es una cadena o no se pudo medir)."""
    cf = lazo.get("centros_fijos")
    if lazo.get("tipo") != "cadena" or not cf:
        return None
    holgura = float(cf["exactos_mm"]) - float(cf["centros_mm"])
    nums = {"eslabones": cf["eslabones"], "centros_mm": round(float(cf["centros_mm"]), 4),
            "exactos_mm": round(float(cf["exactos_mm"]), 4), "holgura_mm": round(holgura, 4),
            "tolerancia_mm": cf["tolerancia_mm"]}
    if abs(holgura) <= float(cf["tolerancia_mm"]) + 1e-9:
        return (OK, "sin tensor: centros exactos; reemplazo de la cadena al 3 % de estiramiento",
                {**nums, "mantenimiento": reemplazo_cadena(float(cf["paso_mm"]))})
    return (SIN_EVALUAR, f"sin mecanismo de tensado reconocido y centros fijos a {holgura:+.3f} mm "
                         f"de los exactos de {cf['eslabones']} eslabones (tolerancia "
                         f"±{cf['tolerancia_mm']:g} mm): no hay con qué recoger esa holgura", nums)


def evaluar_lazo(lazo: dict) -> dict:
    """{"reconocido", "carrera", "agarre"} → (estado, texto, números) de UN lazo."""
    tipo, largo = lazo["tipo"], lazo.get("largo_mm")
    tensores = lazo.get("tensores") or []
    nums = {"lazo": lazo["id"], "tipo": tipo,
            "largo_mm": None if largo is None else round(largo, 1)}
    if not tensores:
        fijos = centros_fijos(lazo)
        if fijos is not None:
            e, txt, n = fijos
            return {"reconocido": (e, txt, {**nums, **n}), "carrera": (e, txt, {**nums, **n}),
                    "agarre": (NO_APLICA, "centros fijos: sin perno tensor", nums)}
        sin = (SIN_EVALUAR, "sin mecanismo de tensado reconocido", nums)
        return {"reconocido": sin, "carrera": sin, "agarre": sin}
    t = _mejor(tensores)
    nums = {**nums, "tensor": t["id"], "tensor_tipo": t["tipo"]}
    otros = f" (y {len(tensores) - 1} más)" if len(tensores) > 1 else ""
    out = {"reconocido": (OK, f"{t['tipo']}: {t['nombre']}{otros}", nums)}
    if largo is None:
        out["carrera"] = (SIN_EVALUAR, lazo.get("motivo") or "no se pudo medir el largo del lazo",
                          nums)
    elif t.get("carrera_mm") is None:
        out["carrera"] = (SIN_EVALUAR, t.get("motivo") or "el tensor no declara su carrera", nums)
    else:
        out["carrera"] = _carrera(lazo, tensores, nums)
    e, txt, casos = _agarre(tensores)
    out["agarre"] = (e, txt, {**nums, **recortar(casos)})
    return out


_CONTROLES = {
    "reconocido": ("tensor.reconocido", "Cada banda o cadena tiene un mecanismo de tensado",
                   "la banda patina o la cadena salta al estirarse: no hay con qué retensar",
                   "criterio de diseño (CEMA · fabricantes de cadena)"),
    "carrera": ("tensor.carrera", "La carrera del tensor cubre el estiramiento del lazo",
                "el tensor llega a tope antes de que el lazo deje de estirarse",
                "CEMA y fabricantes de banda (1 % + 20 mm) · Tsubaki/Renold (cadena 3 %)"),
    "agarre": ("tensor.agarre", "El perno tensor agarra en toda la carrera",
               "el perno tensor se sale de la pieza o pierde la rosca en un extremo de la carrera",
               "VDI 2230 · criterio de taller"),
}


def controlar_tensores(lazos: list[dict]) -> list[Item]:
    """Los tres ítems del tensor sobre todos los lazos (NO_APLICA sin bandas ni cadenas)."""
    if not lazos:
        return [Item(i, tit, NO_APLICA, modo, norma, detalle="el modelo no tiene bandas ni cadenas")
                for i, tit, modo, norma in _CONTROLES.values()]
    res = [(lz, evaluar_lazo(lz)) for lz in lazos]
    items = []
    for clave, (iid, titulo, modo, norma) in _CONTROLES.items():
        estados = [r[clave][0] for _, r in res]
        malos = [(lz, r[clave]) for lz, r in res if r[clave][0] not in (OK, NO_APLICA)]
        casos = [{"nombre": lz.get("nombre"), "estado": e, "detalle": txt, **n}
                 for lz, (e, txt, n) in malos]
        estado = peor(estados)
        piezas = list(dict.fromkeys(pz for lz, _ in malos for pz in lz.get("piezas", [lz["id"]])))
        # D3b: lo que el manual de mantenimiento debe decir (cadenas de centros fijos)
        mant = sorted({r[clave][2]["mantenimiento"] for _, r in res
                       if r[clave][0] == OK and "mantenimiento" in r[clave][2]})
        fijos = sum(1 for _, r in res if r[clave][0] == OK and "mantenimiento" in r[clave][2])
        # D2: lo que aporta cada tambor y los tensores que no hacen falta (nota, no falla)
        aps = [{"lazo": lz.get("nombre"), **a} for lz, r in res
               for a in r[clave][2].get("aportes", [])]
        sobran = [{"lazo": lz.get("nombre"), "tensores": r[clave][2]["no_hacen_falta"]}
                  for lz, r in res if r[clave][2].get("no_hacen_falta")]
        detalle = ("no aplica a ningún lazo" if estado == NO_APLICA else
                   f"{len(res) - len(malos)} de {len(res)} lazos cumplen")
        if sobran:
            detalle += "; no hacen falta: " + "; ".join(", ".join(s["tensores"]) for s in sobran)
        items.append(Item(
            iid, titulo, estado, modo, norma,
            evidencia={"lazos": len(res), "ok": sum(1 for e in estados if e == OK),
                       **({"centros_fijos": fijos, "mantenimiento": mant} if mant else {}),
                       **({"aportes": aps[:MAX_CASOS]} if aps else {}),
                       **({"aportes_omitidos": len(aps) - MAX_CASOS}
                          if len(aps) > MAX_CASOS else {}),
                       **({"no_hacen_falta": sobran} if sobran else {}),
                       **recortar(casos)},
            piezas=piezas, detalle=detalle,
        ))
    return items


def validar_tensores(valor) -> list[dict]:
    """El metadato `tensores` validado: [{piezas: [fid…], carrera_mm > 0, eje: "x"|"y"|"z" o
    [x, y, z], nota?}]. ValueError con la corrección (no se guarda a medias)."""
    if not isinstance(valor, list):
        raise ValueError("tensores es una lista de {piezas, carrera_mm, eje}")
    out = []
    for k, t in enumerate(valor):
        donde = f"tensores[{k}]"
        if not isinstance(t, dict):
            raise ValueError(f"{donde}: cada tensor es un objeto {{piezas, carrera_mm, eje}}")
        extra = set(t) - {"piezas", "carrera_mm", "eje", "nota"}
        if extra:
            raise ValueError(f"{donde}: clave(s) no reconocida(s) {sorted(extra)}; válidas: "
                             "piezas, carrera_mm, eje, nota")
        piezas = t.get("piezas")
        if (not isinstance(piezas, list) or not piezas
                or not all(isinstance(p, str) and p for p in piezas)):
            raise ValueError(f"{donde}.piezas: lista no vacía de ids (la pieza tensada, su perno, "
                             "el lazo)")
        try:
            carrera = float(t.get("carrera_mm"))
        except (TypeError, ValueError):
            raise ValueError(f"{donde}.carrera_mm: número en mm (> 0)") from None
        if carrera <= 0:
            raise ValueError(donde + ".carrera_mm: debe ser > 0")
        eje = t.get("eje")
        if isinstance(eje, str) and eje.lower().lstrip("+-") in _EJES:
            eje = eje.lower()
        elif (isinstance(eje, list) and len(eje) == 3
              and all(isinstance(x, (int, float)) for x in eje) and any(eje)):
            eje = [float(x) for x in eje]
        else:
            raise ValueError(f"{donde}.eje: 'x', 'y', 'z' o un vector [x, y, z] (la dirección "
                             "en que corre la pieza tensada)")
        limpio = {"piezas": list(piezas), "carrera_mm": carrera, "eje": eje}
        if t.get("nota"):
            limpio["nota"] = str(t["nota"])[:200]
        out.append(limpio)
    return out
