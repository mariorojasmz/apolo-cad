"""El EXTREMO de un eje que gira: cuándo NO es peligro (plan puerta-sin-sobrediseno, F3e). Puro:
juzga lo que mide `services/calidad_extremos.py`.

Fuente: OSHA 29 CFR 1910.219(c)(4)(i) (EE. UU., regulación pública): «Projecting shaft ends shall
present a smooth edge and end and shall not project more than one-half the diameter of the shaft
unless guarded by nonrotating caps or safety sleeves»; (c)(4)(ii): «Unused keyways shall be filled
up or covered». Cal/OSHA (8 CCR § 4051) dice lo mismo y fija DESDE DÓNDE se mide: «beyond the end
of the bearing». ISO 12100 anexo B nombra el enganche en lo que gira, pero ninguna norma ISO de
acceso público da un umbral; ésta es la cifra con fuente.

Un extremo de eje que gira NO es peligro si:
- es LISO: el eje es un cilindro de un solo Ø a lo largo de lo que sobresale (sin chavetero,
  plano, escalón ni rosca modelada: el radio medido en cada estación y ángulo es el mismo) y su
  cara de punta es plana (sin muesca);
- en lo que sobresale no hay otra pieza que gire con él ni tornillería (chaveta, prisionero,
  tuerca, collar, piñón): eso ya no es «smooth edge and end»;
- sobresale ≤ ½·d de la cara de su APOYO (la primera pieza que no gira a lo largo del eje, a
  r + 1 mm: la chumacera, el rodamiento, la placa que atraviesa).

Si no se puede medir (no se reconoce el eje en la punta, no hay apoyo a ½·d), SIGUE siendo
peligro: lo conservador es sondearlo, como antes de esta regla.
"""

from __future__ import annotations

NORMA = ("OSHA 29 CFR 1910.219(c)(4)(i)-(ii) (extremo liso que sobresale ≤ ½·d, chavetero "
         "cubierto); Cal/OSHA 8 CCR § 4051 (medido desde el apoyo)")
FRACCION_D = 0.5          # sobresale ≤ ½·d (1910.219(c)(4)(i))
TOL_LISO_MM = 0.3         # el radio medido no varía más que esto: un solo Ø
TOL_SALIENTE_MM = 0.05


def juzgar_extremo(m: dict) -> dict:
    """`m` = {d_mm, saliente_mm (None: sin apoyo a la vista), apoyo (nombre), radios: (min,
    max) del eje en lo que sobresale, punta: (min, max) de la cara de la punta, en_saliente:
    [nombres de lo que gira o es tornillería sobre lo que sobresale], motivo (si no se midió)}
    → {estado: "exento" | "peligro", motivo, d_mm, saliente_mm, limite_mm, apoyo, norma}."""
    base = {"d_mm": m.get("d_mm"), "saliente_mm": m.get("saliente_mm"),
            "apoyo": m.get("apoyo"), "norma": NORMA}
    if m.get("motivo"):
        return {**base, "estado": "peligro", "motivo": m["motivo"]}
    d = float(m["d_mm"])
    lim = FRACCION_D * d
    base["limite_mm"] = round(lim, 2)
    if m.get("en_saliente"):
        return {**base, "estado": "peligro",
                "motivo": "lleva " + ", ".join(m["en_saliente"][:3]) + " en el extremo: no es "
                          "un extremo liso"}
    r0, r1 = m.get("radios") or (0.0, 0.0)
    p0, p1 = m.get("punta") or (0.0, 0.0)
    if r1 - r0 > TOL_LISO_MM:
        return {**base, "estado": "peligro",
                "motivo": f"el eje no es liso en el extremo (radio de {r0:.1f} a {r1:.1f} mm: "
                          "chavetero, plano, escalón o rosca); un chavetero sin uso se cubre "
                          "(1910.219(c)(4)(ii))"}
    if p1 - p0 > TOL_LISO_MM:
        return {**base, "estado": "peligro",
                "motivo": "la cara de la punta no es plana (muesca de chavetero o saliente)"}
    s = m.get("saliente_mm")
    if s is None:
        return {**base, "estado": "peligro",
                "motivo": f"ningún apoyo que no gire a ≤ {lim:.1f} mm de la punta: sobresale "
                          f"más de ½·d (d = {d:.1f} mm)"}
    if s > lim + TOL_SALIENTE_MM:
        return {**base, "estado": "peligro",
                "motivo": f"sobresale {s:.1f} mm de {m.get('apoyo')}: más de ½·d = {lim:.1f} mm"}
    return {**base, "estado": "exento",
            "motivo": f"liso y sobresale {max(s, 0.0):.1f} mm de {m.get('apoyo')} "
                      f"(≤ ½·d = {lim:.1f} mm): no es peligro (1910.219(c)(4)(i))"}
