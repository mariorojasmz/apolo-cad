"""La medida de cada pieza de la lista de corte (plan lista-de-corte-medida, D1–D4): lo que se
CORTA, medido sobre la forma, no lo que declaró su comando.

- **Perfil de catálogo** (`CATEGORIAS_PERFIL`): largo EXTERIOR y corte de cada extremo de
  `kernel/corte_barra.medir_barras`; la sección, de la ficha. Lo declarado (`Feature.miter`,
  `cut_length`) sólo se contrasta: si coincide, la fila conserva su orden de extremos (la de
  siempre); si no, manda lo medido y la fila lo dice en `aviso`. Un perfil que no se deja medir
  como barra (sin eje claro, sección que no cuadra con la ficha) cae a lo de antes.
- **Chapa plegada** (`Feature.chapa`, de `create_sheet_metal`): espesor de la chapa, contorno
  DESARROLLADO (`chapa_ficha.desarrollo`, el mismo de `export_flat_pattern` con su K) y pliegues.
- Lo demás (a medida, catálogo cortable que no es perfil), como siempre: la caja (o `cut_length`
  si va inclinado) y el inglete declarado.

`firma` separa en la lista lo que se corta distinto con las mismas medidas; los textos del corte
(`texto_angulos`, `detalle_corte`) son UNO para el CSV y los planos. `medidas` es la medida por
sólido que leen la lista de corte y la BOM (plan bom-de-compra-fiel D2: una fuente).
"""

from __future__ import annotations

from functools import lru_cache

#: Familias de catálogo que son una BARRA de sección constante (se miden: D1). Rodillos, tambores,
#: guías y lo demás cortable traen su propio dibujo y siguen por la caja.
CATEGORIAS_PERFIL = frozenset({"perfiles", "perfiles_abiertos", "tubos_circulares",
                               "tubos_estructurales"})
_TOL_ANG = 0.5  # °: lo declarado coincide con lo medido
_TOL_L = 1.0    # mm


def es_perfil(comp) -> bool:
    return comp is not None and comp.cuttable and comp.category in CATEGORIAS_PERFIL


def dims_ordenadas(solid) -> tuple[float, float, float]:
    """(espesor, ancho, largo) = extensiones del bbox en orden ascendente."""
    bb = solid.bounding_box()
    return tuple(sorted((  # type: ignore[return-value]
        round(bb.max.X - bb.min.X, 1),
        round(bb.max.Y - bb.min.Y, 1),
        round(bb.max.Z - bb.min.Z, 1),
    )))


@lru_cache(maxsize=256)
def seccion_catalogo(ref: str) -> tuple[float, float]:
    """(espesor, ancho) de la sección de un perfil cortable del catálogo: lo construye LARGO
    (1 m) para que el largo no se cuele entre los dos lados (un UPN-120 a 100 mm daba 55×100)."""
    from .catalog import build_component

    shape, _ = build_component(ref, 1000.0)
    return dims_ordenadas(shape)[:2]


def medidas(f, comp, mat, solidos: list, memo: dict) -> list:
    """Por sólido: (dims, firma, campos) MEDIDOS (perfil de catálogo o chapa con ficha) o None
    (la caja de siempre). Las instancias INTACTAS de una misma definición (`mesh_key` +
    `matrix`: copias rígidas) comparten la medida de la primera en `memo` (largo y cortes no
    cambian al moverla ni al reflejarla, D5)."""
    if getattr(f, "chapa", None) and len(solidos) == 1:
        return [fila_chapa(f, mat)]
    if es_perfil(comp):
        from apolo.kernel.corte_barra import medir_barras

        seccion = seccion_catalogo(comp.ref)
        clave = f.mesh_key if getattr(f, "mesh_key", None) and f.matrix is not None else None
        barras = memo.get(clave) if clave else None
        if barras is None:
            barras = medir_barras(f.shape, seccion)
            if clave:
                memo[clave] = barras
        return [fila_perfil(f, seccion, m) if m else None for m in barras]
    return [None] * len(solidos)


def _angulos_de(ext: dict) -> float | None:
    """α del extremo cortado por UN plano (0 = recto); None si no es un plano."""
    if ext["corte"] == "recto":
        return 0.0
    if ext["corte"] == "angulo":
        return ext["angulos"][0]
    return None


def _clave_extremo(ext: dict) -> tuple:
    return (ext["corte"], tuple(ext["angulos"]))


def _corte_de(extremos: list) -> str:
    cortes = {e["corte"] for e in extremos}
    if "especial" in cortes:
        return "especial"
    if "dos_planos" in cortes:
        return "despunte"
    return "inglete" if "angulo" in cortes else "recto"


def _coincide(declarado: tuple, medido: tuple) -> bool:
    a = sorted(float(x or 0.0) for x in declarado)
    b = sorted(float(x) for x in medido)
    return len(a) == len(b) and all(abs(x - y) <= _TOL_ANG for x, y in zip(a, b))


def fila_perfil(f, seccion: tuple, medida: dict) -> tuple[tuple, tuple, dict]:
    """(dims (t, w, l), firma, campos de la fila) de un perfil MEDIDO."""
    extremos = sorted(medida["extremos"], key=_clave_extremo)  # el orden no depende del espacio
    largo = medida["largo_mm"]
    planos = [_angulos_de(e) for e in extremos]
    corte = _corte_de(extremos)
    declarado = tuple(f.miter) if getattr(f, "miter", None) else None
    cut = getattr(f, "cut_length", None)
    difiere = []
    if None not in planos:
        if declarado is not None and _coincide(declarado, planos):
            angs = declarado  # la fila de siempre: el orden y los None del comando
        else:
            angs = tuple(planos) if corte != "recto" else (None, None)
            if declarado is not None or corte != "recto":
                difiere.append("∠" + "/".join(_txt(a) for a in (declarado or (0.0, 0.0))))
    else:
        angs = tuple(planos)
        difiere.append("∠" + "/".join(_txt(a) for a in (declarado or (0.0, 0.0))))
    if cut and abs(float(cut) - largo) > _TOL_L:
        difiere.insert(0, f"L {round(float(cut), 1):g}")
    campos = {"corte": corte, "angulo_1": angs[0], "angulo_2": angs[1]}
    if corte in ("despunte", "especial"):
        campos["extremos"] = [{"corte": e["corte"], "angulos": list(e["angulos"])} for e in extremos]
    if difiere:
        campos["aviso"] = (f"lo declarado por el comando ({', '.join(difiere)}) no es lo que se "
                           "midió en la pieza: la lista da lo medido")
    firma = ("medido",) + tuple(_clave_extremo(e) for e in extremos)
    if corte in ("recto", "inglete") and None not in planos:
        firma = tuple(angs) if corte == "inglete" else None  # la clave de siempre
    return (seccion[0], seccion[1], largo), firma, campos


def fila_chapa(f, material: str | None) -> tuple[tuple, tuple, dict] | None:
    """(dims, firma, campos) de una chapa con ficha; None si la ficha no despliega."""
    from .chapa_ficha import desarrollo

    try:
        d = desarrollo(f.chapa, material)
    except (ValueError, KeyError, TypeError):
        return None
    return ((d["espesor_mm"], d["ancho_mm"], d["largo_mm"]), ("chapa", d["pliegues"]),
            {"corte": "chapa", "angulo_1": None, "angulo_2": None, "pliegues": d["pliegues"]})


def _txt(a) -> str:
    return f"{a:g}°" if a is not None else "0°"


def _txt_extremo(e: dict) -> str:
    if e["corte"] == "especial":
        return "especial (ver plano)"
    if e["corte"] == "dos_planos":
        return "despunte " + "+".join(f"{a:g}°" for a in e["angulos"])
    return _txt(_angulos_de(e))


def texto_angulos(r: dict) -> str:
    """Los ángulos por extremo de una fila («45°/0°», «0°/especial (ver plano)»); vacío si es
    recta o chapa. La fuente ÚNICA del CSV y de los planos."""
    if r.get("extremos"):
        return "/".join(_txt_extremo(e) for e in r["extremos"])
    if r.get("corte") == "inglete":  # α None en un extremo = ese lado recto
        return "/".join(_txt(a) for a in (r.get("angulo_1"), r.get("angulo_2")))
    return ""


def texto_corte(r: dict) -> str:
    """La columna «Corte» del CSV: el tipo, y en la chapa sus pliegues."""
    if r.get("corte") == "chapa":
        n = r.get("pliegues", 0)
        return f"chapa ({n} pliegue{'s' if n != 1 else ''})" if n else "chapa"
    return r.get("corte", "recto")


def detalle_corte(r: dict) -> str:
    """Lo que el plano escribe tras L×An×Esp: «∠45°/0°», «desarrollo · 2 pliegues» o nada."""
    if r.get("corte") == "chapa":
        n = r.get("pliegues", 0)
        return "desarrollo" + (f" · {n} pliegue{'s' if n != 1 else ''}" if n else "")
    angs = texto_angulos(r)
    return f"∠{angs}" if angs else ""
