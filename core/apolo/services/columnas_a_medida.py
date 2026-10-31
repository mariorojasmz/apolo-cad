"""La COLUMNA que no es perfil de catálogo (plan puerta-fuera-de-catalogo, D7): montante o poste de
madera, tubo o barra de `run_script`. La detección general (base, carga que baja) es la de
`columnas_rules`; aquí lo propio de la pieza a medida. El llamador sostiene STATE_LOCK.

- **Candidata**: a medida, de material estructural, VERTICAL, de ≥ 300 mm, esbelta (largo ≥ 10 ×
  su menor dimensión: más corta no pandea, E.010 Art. 27.1 a) y que TRABAJA (algo apoya en ella:
  un vecino más lejos de tierra). La de rol «pata» sigue con la regla de las patas.
- **Sección** (`seccion_medida`): la madera, rectángulo macizo o redonda; el metal, sólo tubo o
  barra redonda (una chapa vertical, un panel o una ménsula no son columnas). La madera que trabaja
  con una sección que no se reconoce, o sin clase, sale no evaluada (SIN_EVALUAR justificable).
- **Criterio** por material: metal, `columna.regla_columna` (Euler/Johnson, FS ≥ 3); madera,
  `columna_madera.regla_columna_madera` (E.010 o EN 1995 § 6.3.2).
"""

from __future__ import annotations

LARGO_MIN_MM = 300.0
ESBELTEZ_MIN = 10.0


def candidata(fid, f, caja, det, catalog, vertical: str | None,
              plantillas: tuple = ()) -> dict | None:
    """{crit, material, largo, sec} | {motivo} (no evaluada) | None (no es columna a medida).
    Las piezas de una plantilla de máquina no (`vigas_a_medida.de_plantilla`)."""
    from apolo.library.engineering.madera_calculo import criterio
    from apolo.library.lints import _is_bolt
    from apolo.library.materials import resolve_material

    from .seccion_medida import medir_seccion
    from .vigas_a_medida import _herraje, es_de_plantilla

    if catalog.get(getattr(f, "component", None) or "") is not None or _is_bolt(f, catalog):
        return None
    if es_de_plantilla(f, plantillas):
        return None
    lo, hi = caja
    ext = [hi[k] - lo[k] for k in range(3)]
    largo, d_min = ext[2], min(ext[0], ext[1])
    if max(range(3), key=lambda k: ext[k]) != 2 or largo < LARGO_MIN_MM:
        return None
    if d_min <= 0 or largo < ESBELTEZ_MIN * d_min:
        return None
    nivel = det["nivel"]
    if fid not in nivel or not any(nivel.get(m, -1) > nivel[fid]
                                   and not _herraje(m, det["scene"], catalog)
                                   for m in det["graph"]["adj"].get(fid, ())):
        return None
    material = resolve_material(f, catalog, vertical)
    crit = criterio(material, getattr(f, "name", "") or "")
    if crit.tipo == "no_estructural":
        return None
    sec = medir_seccion(f, 2, caja)
    if sec.get("inclinada"):
        return None  # como un perfil inclinado: no es columna de esta regla
    if crit.tipo == "metal":
        if "motivo" in sec or not (sec.get("circ") or sec.get("tubo_rect")):
            return None
    elif crit.tipo == "sin_clase":
        return {"motivo": crit.motivo}
    elif "motivo" in sec:
        return {"motivo": sec["motivo"]}
    elif sec.get("tubo_rect"):
        return {"motivo": "madera hueca: no es un rectángulo macizo ni una sección redonda"}
    return {"crit": crit, "material": material, "largo": largo, "sec": sec}


def regla(nombre: str, c: dict, *, k: float, apoyos: str, carga: float, resumen: dict,
          hip: list[str]) -> dict:
    """La regla de pandeo de la columna a medida con el criterio de su material. Con la cabeza
    libre (K de `columnas_rules`) puede no cumplir una columna que, arriostrada, sí: un montante
    de estantería lo sostienen sus entrepaños y su fondo, que la regla no ve. Si cumple con K = 1
    (articulada en los dos extremos sin desplazamiento, la columna arriostrada) sale NO EVALUADA,
    justificable con el arriostramiento escrito; si ni así, el error de su cálculo."""
    libre = _regla(nombre, c, k=k, apoyos=apoyos, carga=carga, resumen=resumen, hip=hip)
    if libre["estado"] == "ok":
        return libre
    arriostrada = _regla(nombre, c, k=K_ARRIOSTRADA, apoyos="arriostrada: articulada en los dos "
                         "extremos sin desplazamiento lateral", carga=carga, resumen=resumen,
                         hip=hip)
    if arriostrada["estado"] != "ok":
        return libre
    fs = (libre.get("calc") or {}).get("fs")
    return {**arriostrada, "estado": "aviso", "no_evaluada": True,
            "detalle": (f"{nombre}: con la cabeza libre (K = {k:g}) no cumple (FS {fs}); "
                        f"arriostrada (K = {K_ARRIOSTRADA:g}) sí — pandeo no evaluado: la regla "
                        "no ve el arriostramiento."),
            "recomendacion": "Arriostra la columna (fondo, diagonales, entrepaños unidos) y "
                             "justifícalo por escrito (set_justifications con esta regla y sus "
                             "piezas), o súbele la sección."}


K_ARRIOSTRADA = 1.0  # AISC 360-16 Comentario tabla C-A-7.1 caso (d) / E.010 Art. 26.4 (lef ≥ L)


def _regla(nombre: str, c: dict, *, k: float, apoyos: str, carga: float, resumen: dict,
           hip: list[str]) -> dict:
    from apolo.library.engineering.columna import regla_columna
    from apolo.library.engineering.columna_madera import regla_columna_madera

    crit, sec = c["crit"], c["sec"]
    seccion = f"{sec['forma']} (medida en cortes de la geometría)"
    if crit.tipo == "metal":
        return regla_columna(nombre, perfil=sec["forma"], area_mm2=sec["area"],
                             i_min_mm4=sec["i_min"], largo_mm=c["largo"], k=k, apoyos=apoyos,
                             carga_n=carga, material=c["material"], e_mpa=crit.valores["e"],
                             fy_mpa=crit.valores["fy"], fuente_seccion="sección medida",
                             resumen_carga=resumen, hipotesis=hip)
    return regla_columna_madera(nombre, seccion=seccion, area_mm2=sec["area"],
                                i_min_mm4=sec["i_min"], d_mm=sec["dmin"],
                                circular=bool(sec.get("circ")), largo_mm=c["largo"], k=k,
                                apoyos=apoyos, carga_n=carga, crit=crit, resumen_carga=resumen,
                                hipotesis=hip)


__all__ = ["candidata", "regla"]
