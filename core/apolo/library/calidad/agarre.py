"""Control de AGARRE de perno (plan puerta-de-publicacion, D3). Puro: recibe los «insumos de
perno» que mide `services/calidad_pernos.py` (lo que el eje de cada perno atraviesa) y devuelve
ítems de la ficha de calidad.

El insumo de un perno (dict; `t` = distancia sobre el eje desde la cara de asiento de la cabeza
hacia la punta, mm):

    {"fid", "nombre", "ref" (ficha o None), "cabeza": "hex"|"allen"|"esparrago", "madera_screw": bool,
     "d", "paso", "largo",                       # largo bajo cabeza, medido de la geometría
     "tramos": [{"fid", "nombre", "t0", "t1", "rol": "pieza"|"tuerca", "material",
                 "rosca": [(a, b)]}],            # material a radio < d/2: hilo enganchado
     "mas_alla": [{"fid", "t0", "rol"}],         # lo que el eje encuentra pasada la punta
     "esperadas": [fid],                         # las piezas que su `fasten` dice que une
     "evaluable": bool, "motivo": str}

Tres controles, cada uno un ítem que agrega todos los pernos (los casos que fallan van en la
evidencia con sus números):

- **cruza**: el perno entra en TODAS las piezas que une (las de su `fasten` si se conocen) y,
  si no tiene tuerca, no termina en el hueco entre dos paredes de una misma pieza (el M12×50 que
  entraba por UNA aleta del tensor: la otra aleta estaba pasada la punta).
- **retención**: con tuerca, le sobran ≥ 2 pasos de hilo; sin tuerca, la rosca engancha
  ≥ 1·d en acero y ≥ 1,5·d en aluminio o fundición (VDI 2230 / criterio de taller); en madera,
  ≥ 2/3 del largo dentro (DIN 571, el criterio de `fijacion.tornillo_madera`).
- **largo**: el largo es de la serie (ISO 4014/4017/4762; DIN 571) y el catálogo lo vende; el
  ESPÁRRAGO (`cabeza: "esparrago"`, t = 0 en su base y su tuerca en la punta: F3c), de la serie
  de espárragos, sin ficha.
"""

from __future__ import annotations

from ..largos_perno import en_catalogo, en_serie, largos_catalogo, ref_para
from .item import FALLA, NO_APLICA, OK, SIN_EVALUAR, Item, peor, recortar

HILOS_FUERA = 2.0          # pasos de hilo que deben sobrar fuera de la tuerca
K_ACERO = 1.0              # enganche ≥ k·d en una rosca en acero (VDI 2230, criterio de taller)
K_BLANDO = 1.5             # … en aluminio o fundición
FRACCION_MADERA = 2.0 / 3.0  # ≥ 2/3 del tornillo dentro de la madera (DIN 571)
_TOL = 0.05                # mm
_RESPALDO_MM = 200.0       # el respaldo silencioso de join_bolted criterio 1/2


def _k_material(material: str | None) -> float:
    m = (material or "").lower()
    return K_BLANDO if ("alumin" in m or "fundi" in m) else K_ACERO


def _corrido(t: dict, delta: float) -> dict:
    return {**t, "t0": t["t0"] + delta, "t1": t["t1"] + delta,
            "rosca": [(a + delta, b + delta) for a, b in t.get("rosca", [])]}


def _enganche(t: dict, largo: float) -> float:
    return sum(max(0.0, min(b, largo) - max(a, 0.0)) for a, b in t.get("rosca", []))


def rosca_enganchada(tramo: dict, largo: float, d: float) -> tuple[float, float]:
    """(enganche, pide) en mm de la rosca de UN tramo: el hilo dentro de la pieza hasta la punta
    del perno y el mínimo k·d por material (el de `agarre.retencion`). Lo usa la distancia al
    borde para la barra roscada, que no juzga con la tabla de chapas."""
    return _enganche(tramo, largo), _k_material(tramo.get("material")) * d


def evaluar_perno(p: dict, desplazar: dict | None = None) -> dict:
    """{"cruza", "retencion", "largo"} → (estado, texto, números) de UN perno. `desplazar`
    ({fid: Δt}) corre los tramos de una pieza a lo largo del eje: lo usa el tensor para ver el
    agarre en los dos extremos de su carrera."""
    if not p.get("evaluable", True):
        motivo = p.get("motivo") or "geometría del perno no reconocida"
        sin = (SIN_EVALUAR, motivo, {})
        return {"cruza": sin, "retencion": sin, "largo": sin}
    largo, d, paso = float(p["largo"]), float(p["d"]), float(p["paso"])
    tramos = [_corrido(t, (desplazar or {}).get(t["fid"], 0.0)) for t in p.get("tramos", [])]
    tramos.sort(key=lambda t: t["t0"])
    dentro = [t for t in tramos if t["t0"] < largo - _TOL]
    piezas = [t for t in dentro if t["rol"] != "tuerca"]
    tuercas = [t for t in dentro if t["rol"] == "tuerca"]
    out = {"largo": _largo(p, largo, d)}
    ids = {t["fid"] for t in piezas}
    nums = {"largo_mm": round(largo, 1), "d_mm": d, "piezas": [t["fid"] for t in piezas]}
    retencion, roscada = _retencion(p, largo, d, paso, piezas, tuercas, tramos)
    out["retencion"] = retencion
    if not piezas:
        out["cruza"] = (FALLA, "no atraviesa ninguna pieza", nums)
        return out
    faltan = [e for e in p.get("esperadas", []) if e not in ids]
    if faltan:
        out["cruza"] = (FALLA, f"no llega a {', '.join(faltan)}, que su unión dice que sujeta",
                        {**nums, "faltan": faltan})
        return out
    if not tuercas:  # sin tuerca: ¿termina entre dos paredes de una pieza que ya cruzó?
        corta = [m for m in p.get("mas_alla", []) if m["fid"] in ids and m["fid"] != roscada]
        if corta:
            m = corta[0]
            nombre = next(t["nombre"] for t in piezas if t["fid"] == m["fid"])
            out["cruza"] = (FALLA, f"termina entre dos paredes de {nombre}: la otra está "
                            f"{m['t0'] - largo:.0f} mm pasada la punta",
                            {**nums, "pared_sin_cruzar_mm": round(m["t0"], 1)})
            return out
    out["cruza"] = (OK, f"cruza {len(piezas)} pieza(s)", nums)
    return out


def _aviso_respaldo(largo: float) -> str:
    if abs(largo - _RESPALDO_MM) < 0.5:
        return (": largo de 200 mm, el respaldo silencioso de un join_bolted anterior al "
                "criterio 3 (vuelve a crear la unión)")
    return ""


def _retencion(p, largo, d, paso, piezas, tuercas, tramos) -> tuple[tuple, str | None]:
    lejos = sorted([m for m in [*tramos, *p.get("mas_alla", [])]
                    if m.get("rol") == "tuerca" and m["t0"] >= largo - _TOL],
                   key=lambda m: m["t0"])
    if not tuercas and lejos:  # su tuerca está pasada la punta: el perno no llega
        falta = lejos[0]["t0"] - largo
        return (FALLA, f"el perno no llega a su tuerca (le faltan {falta:.1f} mm)"
                + _aviso_respaldo(largo), {"falta_mm": round(falta, 1)}), None
    if tuercas:
        n = tuercas[0]
        sobra = largo - n["t1"]
        pide = HILOS_FUERA * paso
        nums = {"hilo_fuera_mm": round(sobra, 2), "pide_mm": round(pide, 2), "paso_mm": paso}
        if sobra >= pide - _TOL:
            return (OK, f"tuerca con {sobra:.1f} mm de hilo fuera", nums), None
        txt = (f"a la tuerca le sobran {sobra:.1f} mm de hilo (pide ≥ {HILOS_FUERA:g} pasos = "
               f"{pide:.1f} mm)" if sobra >= 0 else
               f"el perno no alcanza a cruzar la tuerca (le faltan {-sobra:.1f} mm)")
        return (FALLA, txt + _aviso_respaldo(largo), nums), None
    mejor = None
    for t in piezas:
        eng = _enganche(t, largo)
        if eng > 1e-6 and (mejor is None or eng > mejor[1]):
            mejor = (t, eng)
    if mejor is None:
        return (FALLA, "sin tuerca ni rosca: nada lo retiene", {"largo_mm": round(largo, 1)}), None
    t, eng = mejor
    if p.get("madera_screw"):
        pide, regla = FRACCION_MADERA * largo, "≥ 2/3 del largo dentro de la madera (DIN 571)"
    else:
        k = _k_material(t.get("material"))
        pide, regla = k * d, f"≥ {k:g}·d en {t.get('material') or 'acero'} (VDI 2230)"
    nums = {"enganche_mm": round(eng, 1), "pide_mm": round(pide, 1), "pieza_roscada": t["fid"]}
    if eng >= pide - _TOL:
        return (OK, f"engancha {eng:.1f} mm en {t['nombre']}", nums), t["fid"]
    return (FALLA, f"engancha {eng:.1f} mm en {t['nombre']}; pide {regla} = {pide:.1f} mm",
            nums), t["fid"]


def _largo(p: dict, largo: float, d: float) -> tuple:
    if p.get("cabeza") == "esparrago":
        return _largo_esparrago(p, largo, d)
    ref = p.get("ref") or ref_para(d, p.get("cabeza", "hex"))
    nums = {"largo_mm": round(largo, 1), "ref": ref}
    anclaje = _anclaje_de_catalogo(ref)
    if anclaje is not None:  # se compra por su ficha: el largo medido (sin la camisa) no es ISO
        return (OK, f"{ref}: anclaje de catálogo M{d:g}×{anclaje:g}", nums)
    if not en_serie(largo, ref):
        return (FALLA, f"{largo:.1f} mm no es un largo de la serie comercial", nums)
    if not en_catalogo(ref, largo):
        vende = largos_catalogo(ref)
        rango = f"vende {vende[0]:g}–{vende[-1]:g} mm" if vende else "no declara largos"
        return (FALLA, f"{ref}×{largo:g} no está en el catálogo ({ref} {rango})",
                {**nums, "catalogo_mm": vende})
    return (OK, f"{ref}×{largo:g}", nums)


def _anclaje_de_catalogo(ref: str | None) -> float | None:
    """El largo de ficha de un anclaje de expansión de catálogo (`ANCLA-EXP-*`), o None. Su largo
    no es de la serie de pernos: es el del fabricante (espárrago con camisa, sobresale `sobre` de
    la placa), y la pieza ES la ref, así que no hay largo que elegir."""
    from ..catalog import CATALOG

    comp = CATALOG.get(ref or "") if ref else None
    specs = (comp.specs or {}) if comp is not None else {}
    if specs.get("tipo") != "anclaje de expansión" or specs.get("length") is None:
        return None
    return float(specs["length"])


def _largo_esparrago(p: dict, largo: float, d: float) -> tuple:
    """El espárrago no tiene ficha de catálogo (se compra por su designación): su largo es de la
    serie de `esparrago.SERIE_ESPARRAGO_MM`; la varilla roscada se corta a medida (DIN 976-1)."""
    from ..esparrago import SERIE_ESPARRAGO_MM, es_varilla

    nums = {"largo_mm": round(largo, 1), "ref": None, "serie": "espárrago (ISO 13918 / DIN 938)"}
    if es_varilla(p.get("nombre")):
        return (OK, f"varilla roscada M{d:g}×{largo:.0f} cortada a medida (DIN 976-1)", nums)
    if not any(abs(largo - s) <= 0.5 for s in SERIE_ESPARRAGO_MM):
        return (FALLA, f"{largo:.1f} mm no es un largo de la serie de espárragos (ISO 13918 / "
                       f"DIN 938: {', '.join(f'{s:g}' for s in SERIE_ESPARRAGO_MM[:12])}…)", nums)
    return (OK, f"espárrago M{d:g}×{largo:.0f} (serie ISO 13918 / DIN 938; sin ficha de "
                "catálogo: se compra por su designación)", nums)


_CONTROLES = {
    "cruza": ("agarre.cruza", "Cada perno atraviesa todas las piezas que une",
              "unión que no sujeta: el perno queda corto (entra por una sola aleta o no llega "
              "a la pieza) y la pieza se suelta en servicio",
              "criterio de taller (camino de carga del perno)"),
    "retencion": ("agarre.retencion", "Tuerca con hilo fuera o rosca con enganche suficiente",
                  "la tuerca se sale o la rosca se barre bajo la precarga",
                  "VDI 2230 (enganche de rosca) · criterio de taller (≥ 2 hilos fuera de la "
                  "tuerca) · DIN 571 (madera)"),
    "largo": ("agarre.largo", "Largo de perno de la serie comercial y del catálogo",
              "perno que no se puede comprar o que el modelo dibujó de un largo inventado",
              "ISO 4014 / ISO 4017 / ISO 4762 (serie de largos) · DIN 571"),
}


def controlar_agarre(pernos: list[dict]) -> list[Item]:
    """Los tres ítems de agarre sobre todos los pernos del modelo (NO_APLICA sin pernos)."""
    if not pernos:
        return [Item(i, tit, NO_APLICA, modo, norma, detalle="el modelo no tiene tornillería")
                for i, tit, modo, norma in _CONTROLES.values()]
    res = [(p, evaluar_perno(p)) for p in pernos]
    items = []
    for clave, (iid, titulo, modo, norma) in _CONTROLES.items():
        estados = [r[clave][0] for _, r in res]
        malos = [(p, r[clave]) for p, r in res if r[clave][0] != OK]
        casos = [{"perno": p["fid"], "nombre": p.get("nombre"), "estado": e, "detalle": txt,
                  **nums} for p, (e, txt, nums) in malos]
        estado = peor(estados)
        n_ok = len(res) - len(malos)
        items.append(Item(
            iid, titulo, estado, modo, norma,
            evidencia={"evaluados": len(res), "ok": n_ok,
                       "fallan": sum(1 for _, (e, _t, _n) in malos if e == FALLA),
                       "sin_evaluar": sum(1 for _, (e, _t, _n) in malos if e == SIN_EVALUAR),
                       **recortar(casos)},
            piezas=list(dict.fromkeys(p["fid"] for p, _ in malos)),
            detalle=(f"{n_ok} de {len(res)} pernos cumplen" if malos
                     else f"los {len(res)} pernos cumplen"),
        ))
    return items
