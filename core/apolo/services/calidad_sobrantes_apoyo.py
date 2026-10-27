"""La candidata que es «apoyo de» otra pieza, ¿también tapa un peligro? (plan lo-que-se-mueve, D6).

`calidad_sobrantes.Prueba.probar` corta en la sujeción cuando la candidata sostiene a una vecina
más lejos del piso: es necesaria y su estado no cambia. Pero esa evidencia sola engaña a quien
rediseña: en la faja de motor central las capotas «de apoyo» también tapaban las cuñas y, al
quitarlas con lo que sostenían, las sondas llegaban (bitácora del plan). Aquí se corren igual las
sondas SIN ELLA Y SIN LO QUE APOYA (con la tornillería que sólo las unía): las rectas, la holgura
funcional y, si ninguna llega, el brazo doblado de los peligros resguardados — el mismo orden y
los mismos controles que `probar`. La evidencia gana `tambien_tapa: <peligro>` o
`solo_apoyo: true`. El llamador sostiene STATE_LOCK.
"""

from __future__ import annotations

import time

_SIN_ELLA = ": sin ella"


def tambien_tapa(prueba, r: set, apoya: list[str]) -> dict:
    """{"tambien_tapa": peligro} si una sonda llega sin `r` y sin lo que apoya; si no,
    {"solo_apoyo": True}. Suma su tiempo a la etapa «apoyo» de `prueba`."""
    from .calidad_codo import BandaEmpujable, sondas_con_codo
    from .calidad_sobrantes import N_DIRECCIONES, _arrastra, _cercanos, _dc_sin, _llegan
    from .calidad_sondas import Trazador

    t0 = time.perf_counter()
    try:
        dc0 = prueba.an["dc"]
        r2 = set(r)
        for x in apoya:
            r2 |= _arrastra(x, prueba.quitadas | r2, dc0["uniones"], prueba.hardware, prueba.jb)
        tocados = [(p, ks) for p in prueba.peligros if (ks := _cercanos(p, r2, dc0["piezas"]))]
        tocados.sort(key=lambda x: x[0]["estado"] == "FALLA")  # los que resguarda, primero
        hay_holgura = any(set(h["entre"]) & r2 for p in prueba.en_holgura
                          for h in p["en_holgura"])
        if not tocados and not hay_holgura:
            return {"solo_apoyo": True}
        dc = _dc_sin(dc0, prueba.quitadas | r2)
        tr, empuje = Trazador(dc["solidos"]), BandaEmpujable(dc, prueba.nubes)
        for p, ks in tocados:
            malo = prueba._rectas(p, ks, tr, dc, empuje)
            p.pop("_nuevas", None)  # lo medido aquí no es la base: la candidata no sobra
            if malo:
                return {"tambien_tapa": p["peligro"]}
        malo, tr, empuje = prueba._holguras(r2, dc, tr, empuje)
        if malo:
            return {"tambien_tapa": malo.rsplit(_SIN_ELLA, 1)[0]}
        doblar = [(p, ks) for p, ks in tocados if p["estado"] == "OK"]
        if doblar:
            campo = prueba._campo(dc, empuje, r2)
            for p, ks in doblar:
                sub = (p if len(p["objetivos"]) > 8 else
                       {**p, "objetivos": [p["objetivos"][k] for k in ks]})
                extra, _ms = sondas_con_codo(tr, campo, sub, N_DIRECCIONES, empuje)
                if _llegan(extra):
                    return {"tambien_tapa": p["peligro"]}
        return {"solo_apoyo": True}
    finally:
        prueba._cron("apoyo", t0)
