"""El `guion.json` vencido de la fábrica (plan puerta-de-publicacion, F6): el guion se ata al log
del proyecto por su `documento.firma` (`services/guion_video.firma`); si el modelo cambió después
de armarlo, `generar` lo rechaza. La fábrica lo detecta en el paso `guion` y lo REHACE, en vez de
decir «ya está, no lo rehago» y caer minutos después en `generar`.

Qué se conserva del vencido (decisión F6):

  - la `marcha` que ya traía (escenario y segundos), probada de nuevo contra el modelo (D13c);
  - lo que no depende del log: `titulo`, `subtitulo`, `modo`, `video` (tamaño y fps) y el lema
    del cierre (`cierre.texto`). La URL del cierre se deriva otra vez (D1).
  - NO las etapas: sus pasos son ids y `k` del log viejo y sus rótulos llevan cifras leídas del
    documento (un rótulo nunca se escribe a mano, `services/rotulos.py`). Si un rótulo de una etapa
    con el mismo título difería del nuevo, se avisa: el vencido queda en `guion.vencido.json`.

Un guion sin `documento.firma` (uno a mano o de un test) no se juzga: se deja como está.
"""

from __future__ import annotations

import json
import os

from apolo.publicacion.paquete import GUION

VENCIDO = "guion.vencido.json"
#: Lo que se copia tal cual del guion vencido al nuevo (ver el docstring).
CONSERVA = ("subtitulo", "video")


def firma_vencida(e, g: dict) -> tuple[str, str] | None:
    """(firma del guion, firma del proyecto hoy) si no coinciden; None si está vigente o si el
    guion no trae firma."""
    from apolo.publicacion import flujo

    suya = (g.get("documento") or {}).get("firma") if isinstance(g, dict) else None
    if not suya:
        return None
    api = flujo._Api(e.cliente)
    api.abrir(e.proyecto)
    hoy = flujo._firma_de(api.apolo())
    return None if hoy == suya else (suya, hoy)


def leer(carpeta) -> dict:
    try:
        g = json.loads((carpeta / GUION).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return g if isinstance(g, dict) else {}


def _rotulos_perdidos(viejo: dict, nuevo: dict) -> list[str]:
    nuevos = {x.get("titulo"): x.get("texto") for x in nuevo.get("etapas") or []}
    return [x["titulo"] for x in viejo.get("etapas") or []
            if isinstance(x, dict) and x.get("titulo") in nuevos
            and x.get("texto") != nuevos[x["titulo"]]]


def rehacer(e, viejo: dict, firmas: tuple[str, str], *, sin_marcha: str | None) -> dict:
    """Rehace `guion.json` sobre el proyecto de hoy conservando lo que sigue valiendo. Devuelve
    los datos del paso `guion` de la fábrica."""
    from apolo.publicacion import flujo, marcha
    from apolo.services.guion_video import MODO_DISENO, validar_guion

    ruta, respaldo = e.carpeta / GUION, e.carpeta / VENCIDO
    e.eco(f"{GUION} se armó sobre otra versión del proyecto (firma {firmas[0]}; hoy "
          f"{firmas[1]}): lo rehago. El vencido queda en {respaldo.name}.")
    m_vieja = viejo.get("marcha") if isinstance(viejo.get("marcha"), dict) else None
    elegida: dict = {}

    def _marcha(doc):
        if m_vieja:
            return m_vieja
        elegida["m"] = marcha.elegir(doc, e.carpeta, eco=e.eco)
        return elegida["m"]

    os.replace(ruta, respaldo)
    try:
        r = flujo.guion(e.cliente, e.proyecto, raiz=e.raiz, slug=e.slug, version=e.version,
                        tienda=e.tienda, eco=e.eco, titulo=viejo.get("titulo") or None,
                        modo=viejo.get("modo") or MODO_DISENO,
                        marcha=None if sin_marcha else _marcha)
        g = json.loads(ruta.read_text(encoding="utf-8"))
        for clave in CONSERVA:
            if clave in viejo:
                g[clave] = viejo[clave]
        lema = (viejo.get("cierre") or {}).get("texto")
        if lema:
            g["cierre"]["texto"] = lema
        if m_vieja and not sin_marcha:
            g["marcha"] = m_vieja
        validar_guion(g)
        ruta.write_text(json.dumps(g, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except BaseException:
        os.replace(respaldo, ruta)  # el vencido vuelve: un reintento conserva lo mismo
        raise
    perdidos = _rotulos_perdidos(viejo, g)
    if perdidos:
        e.eco("Aviso: el rótulo de " + ", ".join(f"«{t}»" for t in perdidos) + " cambió con el "
              f"modelo; el que tenía está en {respaldo.name} (un rótulo sólo dice cifras del "
              "documento: revísalo antes de grabar).")
    if sin_marcha:
        marcha_s = None
    elif m_vieja:
        from apolo.publicacion import fabrica

        marcha_s = fabrica._marcha_en_guion(e)  # D13c: la que traía, probada contra el modelo
    else:
        m = elegida.get("m")
        marcha_s = m["duracion_s"] if m else None
    return {"rehecho": True, "firma_vieja": firmas[0], "etapas": r["etapas"],
            "duracion_s": round(r["duracion_s"], 1), "marcha_s": marcha_s}
