"""Builders de RODAJE del catálogo: garruchas de placa (giratoria, con freno total y fija).

Módulo propio porque `builders.py` está congelado por el trinquete de tamaño
(`tests/test_tamano_archivos.py`); `loader.py` une este registro con el de `builders.py` y
rechaza un nombre repetido. Mismo contrato que allá: cada builder es una *factory*
`(**params) -> ((length|None) -> shape)`.

MARCO CANÓNICO de la garrucha (`caster`), el que fija `position` en `insert_component`:

- ORIGEN en el centro de la cara SUPERIOR de la placa (la cara que se atornilla a la máquina),
  Z hacia arriba. La placa mide `placa_l` en X × `placa_w` en Y y ocupa z ∈ [−placa_t, 0].
  → `position` = el centro de la cara INFERIOR de la placa base de la pata.
- 4 agujeros pasantes Ø`agujero_d` en (±agujeros_x/2, ±agujeros_y/2). Si
  `agujeros_y_min != agujeros_y_max` son RANURAS (estadio) a lo largo de Y que cubren de
  y_min/2 a y_max/2 en cada lado (la placa admite cualquier separación entre filas del rango).
- Eje de la rueda paralelo a Y (la rueda rueda a lo largo de X). Giratoria y freno total: el
  centro de la rueda queda DETRÁS del eje de giro, en x = −avance. Fija: avance 0, rueda bajo
  el centro de la placa.
- Apoyo al piso en z = −altura (bbox.min.Z = −altura exacto); centro de la rueda en
  z = −altura + rueda_d/2.

Qué es REAL y qué REPRESENTATIVO: placa con sus agujeros/ranuras (lo que se taladra en la
máquina), rueda Ø×ancho, altura y avance son los de la ficha. Pista de giro, horquilla, eje y
pedal son REPRESENTATIVOS: se escalan del espacio libre `gap = altura − rueda_d − placa_t`
entre la placa y la rueda. Todo sale como UN solo sólido (las partes solapan 0.5–8 mm; regla
de `library/CLAUDE.md`).
"""

from __future__ import annotations

from build123d import Box, Cylinder, Pos, Rotation, SlotCenterToCenter, extrude

#: Tipos de garrucha que entiende `caster`.
TIPOS_GARRUCHA = ("giratoria", "freno_total", "fija")

#: Espacio libre mínimo entre la placa y la rueda (mm) para que quepa la horquilla.
GAP_MIN_MM = 6.0

_SOLAPE = 1.0     # solape entre partes contiguas (mm): ni tangentes (Compound) ni disjuntas
_HOLGURA = 2.5    # holgura entre la cara de la rueda y el brazo de la horquilla (mm)


def _validar(tipo, rueda_d, rueda_b, altura, placa_l, placa_w, placa_t,
             agujeros_x, agujeros_y_min, agujeros_y_max, agujero_d, avance) -> float:
    """Rechaza combinaciones imposibles con un mensaje que dice qué corregir. Devuelve `gap`."""
    if tipo not in TIPOS_GARRUCHA:
        raise ValueError(
            f"Garrucha: tipo desconocido '{tipo}'; usa uno de {', '.join(TIPOS_GARRUCHA)}"
        )
    medidas = {
        "rueda_d": rueda_d, "rueda_b": rueda_b, "altura": altura, "placa_l": placa_l,
        "placa_w": placa_w, "placa_t": placa_t, "agujeros_x": agujeros_x,
        "agujeros_y_min": agujeros_y_min, "agujero_d": agujero_d,
    }
    for nombre, valor in medidas.items():
        if not valor > 0:
            raise ValueError(f"Garrucha: {nombre} debe ser > 0 (vale {valor})")
    if agujeros_y_max < agujeros_y_min:
        raise ValueError(
            f"Garrucha: agujeros_y_max ({agujeros_y_max}) < agujeros_y_min ({agujeros_y_min})"
        )
    if avance < 0:
        raise ValueError(f"Garrucha: avance negativo ({avance}); la rueda va detrás, en x = −avance")
    if tipo == "fija" and avance != 0:
        raise ValueError(
            f"Garrucha fija con avance {avance}: una fija no gira, la rueda va bajo el centro "
            "de la placa (avance 0)"
        )
    gap = altura - rueda_d - placa_t
    if gap < GAP_MIN_MM:
        raise ValueError(
            f"Garrucha: altura {altura} mm no deja lugar a la horquilla: altura − rueda_d − "
            f"placa_t = {gap:.1f} mm (mínimo {GAP_MIN_MM:g} mm)"
        )
    return gap


def _agujeros(x: float, y_min: float, y_max: float, d: float, z_centro: float, alto: float) -> list:
    """Cortadores de los 4 agujeros (o ranuras en estadio a lo largo de Y) del patrón."""
    r = d / 2.0
    ya, yb = y_min / 2.0, y_max / 2.0
    largo = yb - ya
    cortadores = []
    for sx in (1.0, -1.0):
        for sy in (1.0, -1.0):
            if largo > 1e-6:  # ranura: estadio extruido (un sólido por ranura, no tres)
                ranura = extrude(SlotCenterToCenter(largo, d, rotation=90), amount=alto)
                cortadores.append(Pos(sx * x / 2.0, sy * (ya + yb) / 2.0, z_centro - alto / 2.0) * ranura)
            else:
                cortadores.append(Pos(sx * x / 2.0, sy * ya, z_centro) * Cylinder(r, alto))
    return cortadores


def caster(tipo: str, rueda_d: float, rueda_b: float, altura: float,
           placa_l: float, placa_w: float, placa_t: float,
           agujeros_x: float, agujeros_y_min: float, agujeros_y_max: float,
           agujero_d: float, avance: float):
    """Garrucha (rueda industrial) de PLACA: placa de montaje + horquilla + rueda, un sólido.

    `tipo` ∈ {"giratoria", "freno_total", "fija"} (otro → ValueError). Cotas de la ficha (mm):
    `rueda_d`×`rueda_b` = Ø y ancho de la rueda; `altura` = del piso a la cara superior de la
    placa; `placa_l` (X) × `placa_w` (Y) × `placa_t`; patrón de agujeros `agujeros_x` ×
    `agujeros_y_min`…`agujeros_y_max` (iguales = agujero redondo; distintos = ranura) de
    Ø`agujero_d`; `avance` = distancia horizontal del eje de giro al eje de la rueda (0 en la
    fija; ≠ 0 en la fija → ValueError).

    MARCO CANÓNICO: origen en el centro de la cara SUPERIOR de la placa, Z arriba; placa en
    z ∈ [−placa_t, 0]; agujeros en (±agujeros_x/2, ±agujeros_y/2); eje de la rueda paralelo a
    Y; rueda en x = −avance (giratoria/freno total) o x = 0 (fija); apoyo al piso en
    z = −altura; centro de la rueda en z = −altura + rueda_d/2.

    Partes REPRESENTATIVAS, escaladas del espacio libre `gap = altura − rueda_d − placa_t`
    (si `gap` < 6 mm → ValueError): pista de giro Ø 0.75·min(placa_l, placa_w) y alto
    0.35·gap (sólo giratoria/freno total), puente de horquilla de 0.3·gap, holgura ≥ 0.35·gap
    sobre la rueda; dos brazos a los lados de la rueda (holgura 2.5 mm) hasta el eje; eje a lo
    largo de Y que atraviesa rueda y brazos. Freno total: PEDAL a la altura del puente que
    sobresale hacia −X más allá del borde trasero de la rueda, sin tocarla.
    """
    gap = _validar(tipo, rueda_d, rueda_b, altura, placa_l, placa_w, placa_t,
                   agujeros_x, agujeros_y_min, agujeros_y_max, agujero_d, avance)
    gira = tipo != "fija"

    # --- cotas representativas (escaladas de gap y del Ø de la rueda) ---
    h_pista = 0.35 * gap if gira else 0.0           # pista de giro (rodamiento de la horquilla)
    r_pista = 0.75 * min(placa_l, placa_w) / 2.0
    h_puente = 0.30 * gap                            # puente (corona) de la horquilla
    brazo_t = min(8.0, max(4.0, 0.05 * rueda_d))     # espesor de chapa del brazo
    brazo_w = 0.40 * rueda_d                         # ancho del brazo a lo largo de X
    eje_d = max(10.0, 0.12 * rueda_d)

    xw = -avance                                     # centro de la rueda (x)
    zw = -altura + rueda_d / 2.0                     # centro de la rueda (z)
    y_brazo = rueda_b / 2.0 + _HOLGURA + brazo_t / 2.0
    medio_y_puente = rueda_b / 2.0 + _HOLGURA + brazo_t + _SOLAPE

    def build(_length=None):
        # --- placa de montaje (los agujeros se cortan al final) ---
        placa = Pos(0, 0, -placa_t / 2.0) * Box(placa_l, placa_w, placa_t)
        partes = []

        # --- pista de giro (giratoria/freno total): bajo el centro de la placa ---
        z_top_puente = -placa_t - h_pista + _SOLAPE
        if gira:
            alto = h_pista + _SOLAPE
            partes.append(Pos(0, 0, -placa_t - h_pista + alto / 2.0) * Cylinder(r_pista, alto))

        # --- puente de la horquilla: del eje de giro hasta sobre la rueda ---
        z_bot_puente = -placa_t - h_pista - h_puente
        x_lo = xw - brazo_w / 2.0 - _SOLAPE
        x_hi = xw + brazo_w / 2.0 + _SOLAPE
        if gira:  # llega hasta bajo la pista de giro
            x_hi = max(0.5 * r_pista, x_hi)
        alto_puente = z_top_puente - z_bot_puente
        z_mid_puente = (z_top_puente + z_bot_puente) / 2.0
        partes.append(Pos((x_lo + x_hi) / 2.0, 0, z_mid_puente) * Box(
            x_hi - x_lo, 2.0 * medio_y_puente, alto_puente))

        # --- brazos de la horquilla: del puente (solapados) hasta por debajo del eje ---
        z_top_brazo = z_bot_puente + _SOLAPE
        z_bot_brazo = zw - eje_d
        for sy in (1.0, -1.0):
            partes.append(Pos(xw, sy * y_brazo, (z_top_brazo + z_bot_brazo) / 2.0) * Box(
                brazo_w, brazo_t, z_top_brazo - z_bot_brazo))

        # --- eje (a lo largo de Y) que atraviesa brazos y rueda + rueda ---
        largo_eje = rueda_b + 2.0 * (_HOLGURA + brazo_t) + 6.0
        partes.append(Pos(xw, 0, zw) * Rotation(90, 0, 0) * Cylinder(eje_d / 2.0, largo_eje))
        partes.append(Pos(xw, 0, zw) * Rotation(90, 0, 0) * Cylinder(rueda_d / 2.0, rueda_b))

        # --- pedal del freno total: a la altura del puente, sale hacia −X tras la rueda ---
        if tipo == "freno_total":
            x_punta = xw - rueda_d / 2.0 - max(12.0, 0.12 * rueda_d)
            x_raiz = x_lo + 6.0                      # 6 mm dentro del puente
            partes.append(Pos((x_punta + x_raiz) / 2.0, 0, z_mid_puente) * Box(
                x_raiz - x_punta, max(20.0, 0.6 * rueda_b), 0.6 * alto_puente))

        # un fuse y un cut con todas las herramientas: N booleanas sueltas cuestan el doble.
        # Agujeros: atraviesan la placa y 0.5 mm por debajo (nada de abajo los tapa).
        cortadores = _agujeros(agujeros_x, agujeros_y_min, agujeros_y_max, agujero_d,
                               -placa_t / 2.0 + 0.25, placa_t + 1.5)
        cuerpo = placa.fuse(*partes)
        if hasattr(cuerpo, "cut"):  # partes disjuntas → ShapeList: lo rechaza el control de abajo
            cuerpo = cuerpo.clean().cut(*cortadores)
        if not hasattr(cuerpo, "volume") or len(cuerpo.solids()) != 1:
            raise RuntimeError("Garrucha: las partes no quedaron unidas en un solo sólido")
        return cuerpo.clean()

    return build


BUILDERS = {
    "caster": caster,  # garrucha de placa: giratoria / freno total / fija (marco: cara de montaje)
}
