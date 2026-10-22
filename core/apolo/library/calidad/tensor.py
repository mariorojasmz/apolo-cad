"""Control del TENSOR (plan puerta-de-publicacion, D3). Puro: recibe los lazos (bandas y cadenas)
con los tensores RECONOCIDOS que actúan sobre cada uno (los arma `services/calidad_tensores.py`)
y devuelve ítems de la ficha de calidad.

Un lazo (dict):

    {"id", "nombre", "tipo": "banda"|"cadena", "largo_mm": float|None, "motivo": str,
     "tensores": [{"tipo": "take_up"|"catalogo"|"plantilla"|"declarado", "id", "nombre",
                   "carrera_mm": float|None, "motivo": str,
                   "pernos": [{"insumo": <insumo de agarre>, "movil": fid,
                               "antes": mm, "despues": mm}]}]}

`pernos` son los pernos que MUEVEN la pieza tensada (`movil`): la pieza corre `antes` mm hacia la
cabeza y `despues` mm hacia la punta sobre el eje del perno (la carrera es la suma).

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
- **carrera**: banda ≥ 1 % del largo del lazo + 20 mm de montaje (estiramiento de servicio de una
  banda de PVC de 2 capas 0,5–1 %: CEMA y fabricantes); cadena ≥ 3 % del largo / 2 sobre la línea
  de centros (estirado de reemplazo del 3 %, Tsubaki/Renold: la regla de la plantilla);
- **agarre en toda la carrera**: cada perno tensor pasa el control de agarre con la pieza tensada
  en los DOS extremos de su carrera (`agarre.evaluar_perno` con la pieza corrida).
"""

from __future__ import annotations

from .agarre import evaluar_perno
from .item import FALLA, NO_APLICA, OK, SIN_EVALUAR, Item, peor, recortar

ESTIRAMIENTO_BANDA = 0.01   # 1 % del largo del lazo
MONTAJE_BANDA_MM = 20.0     # + 20 mm para montar la banda
ESTIRADO_CADENA = 0.03      # 3 % del largo; la carrera de centros es la mitad
_EJES = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}


def carrera_requerida(tipo: str, largo_mm: float) -> float:
    if tipo == "banda":
        return ESTIRAMIENTO_BANDA * largo_mm + MONTAJE_BANDA_MM
    return ESTIRADO_CADENA * largo_mm / 2.0


def _criterio(tipo: str) -> str:
    return ("carrera ≥ 1 %·L + 20 mm" if tipo == "banda"
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
    """El tensor de MÁS carrera (el que decide si el lazo se puede tensar)."""
    con = [t for t in tensores if t.get("carrera_mm") is not None]
    return max(con, key=lambda t: t["carrera_mm"]) if con else tensores[0]


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
    out = {"reconocido": (OK, f"{t['tipo']}: {t['nombre']}", nums)}
    carrera = t.get("carrera_mm")
    if largo is None:
        out["carrera"] = (SIN_EVALUAR, lazo.get("motivo") or "no se pudo medir el largo del lazo",
                          nums)
    elif carrera is None:
        out["carrera"] = (SIN_EVALUAR, t.get("motivo") or "el tensor no declara su carrera", nums)
    else:
        pide = carrera_requerida(tipo, largo)
        n = {**nums, "carrera_mm": round(carrera, 1), "pide_mm": round(pide, 1),
             "criterio": _criterio(tipo)}
        txt = f"carrera {carrera:.1f} mm; pide {pide:.1f} mm ({_criterio(tipo)})"
        out["carrera"] = (OK if carrera >= pide - 1e-6 else FALLA, txt, n)
    e, txt, casos = agarre_en_carrera(t)
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
        items.append(Item(
            iid, titulo, estado, modo, norma,
            evidencia={"lazos": len(res), "ok": sum(1 for e in estados if e == OK),
                       **({"centros_fijos": fijos, "mantenimiento": mant} if mant else {}),
                       **recortar(casos)},
            piezas=piezas,
            detalle=("no aplica a ningún lazo" if estado == NO_APLICA else
                     f"{len(res) - len(malos)} de {len(res)} lazos cumplen"),
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
