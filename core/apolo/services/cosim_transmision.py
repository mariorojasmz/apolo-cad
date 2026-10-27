"""La transmisión motor → junta prismática de un escenario, contra el documento (plan
motor-a-eje-lineal D1, D3, D6).

`resolver(doc, esc)` da, por motor acoplado, el radio de su transmisión (mm) y si es
irreversible, y las hipótesis que el resultado lista. El radio sale del MODELO cuando se puede (la
pieza del piñón y su `d0` de catálogo) y si no, del número declarado con su fuente
(`cosim/transmision.py`). Un motor acoplado a una junta prismática SIN transmisión es 400 con la
forma y los piñones del documento (antes era «'placa' es para juntas de giro», sin salida); una
transmisión en una junta de giro también. Sin transmisiones devuelve vacío: el snapshot de
siempre. Sin locks: el llamador sostiene STATE_LOCK.
"""

from __future__ import annotations

from .errors import ServiceError


def _pinones(doc) -> list[str]:
    return [fid for fid, f in doc.scene.items()
            if str(getattr(f, "component", "") or "").upper().startswith("PINON-")]


def _pieza(doc, quien: str, donde: str):
    f = doc.scene.get(quien)
    if f is not None:
        return quien, f
    por_nombre = [(fid, x) for fid, x in doc.scene.items() if getattr(x, "name", None) == quien]
    if len(por_nombre) == 1:
        return por_nombre[0]
    pinones = _pinones(doc)
    raise ServiceError(400, f"{donde}.pinon: «{quien}» no es una pieza del documento"
                            + (" (hay varias con ese nombre: usa su id)" if por_nombre else "")
                            + f"; piñones de catálogo: {', '.join(pinones) or 'ninguno'}")


def _d0(doc, quien: str, donde: str) -> tuple[float, str]:
    from apolo.library.catalog import CATALOG

    fid, f = _pieza(doc, quien, donde)
    ref = getattr(f, "component", None)
    c = CATALOG.get(ref) if ref else None
    d0 = (getattr(c, "specs", None) or {}).get("d0") if c is not None else None
    if not d0:
        raise ServiceError(400, f"{donde}.pinon: la pieza {fid} ({ref or 'sin componente de catálogo'}) "
                                "no trae diámetro primitivo (d0) en su ficha: declara "
                                '{"diametro_primitivo_mm": d, "fuente": "…"}')
    return float(d0), f"piñón {fid} {ref}, d0 = {float(d0):g} mm de su ficha"


def resolver(doc, esc) -> tuple[dict, list[str]]:
    """({designación: (radio_mm, irreversible)}, hipótesis). `ServiceError(400)`."""
    from apolo.cosim.transmision import FORMA, radio_mm

    out, hipotesis = {}, []
    for des, a in esc.motores.items():
        donde = f"acoples.motores.{des}"
        j = (doc.joints or {}).get(a["junta"])
        t = a.get("transmision")
        if j is None:
            continue  # la junta que no existe la nombra la dinámica, con las móviles
        prismatica = j.get("type") == "prismatica"
        if t is None:
            if prismatica:
                pinones = _pinones(doc)
                raise ServiceError(400, f"{donde}: «{a['junta']}» es una junta PRISMÁTICA y el motor es "
                                        "rotativo: declara cómo la mueve, "
                                        f'"transmision": {FORMA}'
                                        + (f" (piñones de catálogo: {', '.join(pinones)})" if pinones else ""))
            continue
        if not prismatica:
            raise ServiceError(400, f"{donde}.transmision: es para una junta prismática; «{a['junta']}» es "
                                    f"{j.get('type')} (el motor ya la gira): quítala")
        if "pinon" in t:
            d0, origen = _d0(doc, t["pinon"], donde)
            r = radio_mm(t, d0)
        else:
            r = radio_mm(t)
            clave = "diametro_primitivo_mm" if "diametro_primitivo_mm" in t else "avance_mm"
            origen = f"{clave} = {t[clave]:g} declarado ({t['fuente']})"
        irrev = bool(t.get("irreversible", False))
        out[des] = (r, irrev)
        hipotesis.append(f"{des} → {a['junta']}: transmisión de r = {r:.3f} mm ({origen}); v = ω·r, "
                         "rígida y sin pérdidas"
                         + ("; irreversible: sin tensión la junta queda retenida (fricción = el tope "
                            "nominal del motor)" if irrev else "; reversible: sin par la carga la arrastra"))
    return out, hipotesis
