"""La lámina ISO 1219 del circuito de aire de un documento (plan V8.9 F5, D11; P3: en el núcleo,
con cada bobina referida a su BORNE del tablero, nunca a una lámina eléctrica).

Lee el carril (`services/electrico.modelo`) y arma los datos puros que dibuja
`drawing/neumatica` (`CircuitoAire`):
  - los aparatos con ficha neumática (no los tubos), con un rótulo corto de su ficha;
  - el borne del tablero al que llega cada bobina: el otro extremo de la RED eléctrica de su
    borne A1 (`library/electrico/redes`), prefiriendo una bornera y, si no, un aparato en otra
    ubicación que la válvula; sin conductor, «sin cablear». El de un presostato, igual desde el
    borne de su NA (V8.9 F8);
  - `opciones` de quien la pide (tool `drawing`, spec `neumatica`): `ciclo` (el orden de los
    cilindros, de izquierda a derecha) y `detectores` ({"-BG1": {"cilindro": "-MM1", "en":
    "atras"}}), que el carril no declara. Cada error dice qué corregir.
Sin aire en el documento → 400 con lo que falta. El llamador sostiene STATE_LOCK.
"""

from __future__ import annotations

from .errors import ServiceError

POSICIONES = ("atras", "adelante")
SIN_CABLEAR = "sin cablear"
MANDOS = {"monoestable": "monoestable", "biestable": "biestable", "centro_cerrado": "centro cerrado",
          "centro_escape": "centro a escape", "centro_presion": "centro a presión"}

SIN_AIRE = ("El documento no tiene circuito de aire: no hay aparatos con ficha neumática en el "
            "carril. Declara el FRL, la válvula de corte con escape, las válvulas y los cilindros "
            "con add_device (categorías aire_comprimido, valvulas_neumaticas, cilindros_neumaticos) "
            "y únelos con add_tubo; después pide la lámina con spec {\"esquema\": \"neumatico\"}.")


def _rotulo(d) -> str:
    n = d.neumatico
    m = n.modelo
    if n.tipo == "cilindro":
        carrera = (d.servicio or {}).get("carrera_mm")
        base = f"Ø{m.get('D_mm', 0):g}/{m.get('d_mm', 0):g}"
        return base + (f" c{carrera:g}" if isinstance(carrera, (int, float)) and carrera else "")
    if n.tipo == "valvula":
        return f"{m.get('vias')}/{m.get('posiciones')} {MANDOS.get(m.get('mando'), m.get('mando', ''))}"
    if n.tipo == "frl":
        p = d.ajustes.get("p_regulada_bar")
        return f"p = {p:g} bar" if isinstance(p, (int, float)) else "p sin declarar"
    if n.tipo == "valvula_corte":
        return "con escape" if m.get("con_escape") else "sin escape"
    if n.tipo == "presostato":
        p = d.ajustes.get("p_conmuta_bar")
        return f"{p:g} bar" if isinstance(p, (int, float)) else ""
    return ""


def _borne_tablero(an, d, borne: str) -> str:
    """El otro extremo de la red del `borne` de `d` en el tablero («+TAB1-X1:3»)."""
    idx = an.red(d.designacion, borne)
    if idx is None or idx not in an.conectados:
        return SIN_CABLEAR
    candidatos = []
    for orden, (des, b) in enumerate(an.miembros[idx]):
        otro = an.dispositivos.get(des)
        if otro is None or des == d.designacion:
            continue
        rango = 0 if otro.bornera else (1 if otro.ubicacion and otro.ubicacion != d.ubicacion else 2)
        candidatos.append((rango, orden, f"{otro.ubicacion or ''}{des}:{b}"))
    return min(candidatos)[2] if candidatos else SIN_CABLEAR


def _bobinas(an, d) -> dict:
    from apolo.library.neumatica.bobinas import bornes_bobina, lados_con_bobina

    lados = lados_con_bobina(d.neumatico)
    if not lados:
        return {}
    return {lado: f"{a1}: {_borne_tablero(an, d, a1)}" for lado, (a1, _a2) in bornes_bobina(lados).items()}


def _contacto(an, d) -> str:
    """El NA de un presostato y el borne del tablero que lo lee («14: +TAB1-K1:I0.0»; V8.9 F8):
    el extremo de su contacto `señal` NA que no es el común. Sin contacto, «»."""
    if d.neumatico.tipo != "presostato":
        return ""
    na = next((c for c in d.caminos if c.accion == "señal" and c.tipo == "NA"), None)
    return f"{na.a}: {_borne_tablero(an, d, na.a)}" if na is not None else ""


def _salida_detector(d) -> str | None:
    """El borne de SALIDA de un sensor (el extremo de su contacto de señal: BK en uno de 3 hilos)."""
    for c in d.caminos:
        if c.accion == "señal":
            return c.a
    return d.bornes[0].id if d.bornes else None


def _detectores(m, an, cilindros: set, crudo) -> tuple:
    from apolo.drawing.neumatica import Detector

    if crudo in (None, {}):
        return ()
    if not isinstance(crudo, dict):
        raise ServiceError(400, 'neumatica.detectores: un objeto {"-BG1": {"cilindro": "-MM1", '
                                '"en": "atras"}}')
    todos = {d.designacion: d for d in m.dispositivos}
    out = []
    for des, cfg in crudo.items():
        d = todos.get(des)
        if d is None:
            raise ServiceError(400, f"neumatica.detectores: {des} no existe en el carril; declara el "
                                    "detector con add_device (categoría sensores)")
        cfg = cfg if isinstance(cfg, dict) else {}
        cil, en = cfg.get("cilindro"), cfg.get("en", "atras")
        if cil not in cilindros:
            raise ServiceError(400, f"neumatica.detectores.{des}.cilindro: «{cil}» no es un cilindro "
                                    f"del circuito; cilindros: {', '.join(sorted(cilindros)) or 'ninguno'}")
        if en not in POSICIONES:
            raise ServiceError(400, f"neumatica.detectores.{des}.en: «{en}»; vale «atras» (vástago "
                                    "retraído) o «adelante» (extendido)")
        salida = _salida_detector(d)
        out.append(Detector(des, cil, en, _borne_tablero(an, d, salida) if salida else SIN_CABLEAR))
    return tuple(out)


def circuito(doc, opciones: dict | None = None):
    """El `CircuitoAire` del documento con las `opciones` de la lámina."""
    from apolo.drawing.neumatica import Aparato, CircuitoAire
    from apolo.library.electrico.redes import analizar

    from .electrico import modelo
    from .neumatica import hay_aire

    m = modelo(doc)
    if not hay_aire(m):
        raise ServiceError(400, SIN_AIRE)
    opciones = opciones or {}
    desconocidas = sorted(set(opciones) - {"ciclo", "detectores"})
    if desconocidas:
        raise ServiceError(400, f"neumatica: claves no reconocidas {', '.join(desconocidas)}; "
                                "válidas: ciclo, detectores")
    an = analizar(m)
    aparatos = []
    for d in m.dispositivos:
        n = d.neumatico
        if n is None or n.tipo is None:
            continue  # lo eléctrico y los tubos
        aparatos.append(Aparato(d.designacion, n.tipo, dict(n.modelo), tuple(p.id for p in d.puertos),
                                _rotulo(d), _bobinas(an, d), _contacto(an, d)))
    cilindros = {a.designacion for a in aparatos if a.tipo == "cilindro"}
    ciclo = opciones.get("ciclo") or []
    if not isinstance(ciclo, list) or not all(isinstance(x, str) for x in ciclo):
        raise ServiceError(400, 'neumatica.ciclo: la lista de cilindros en el orden del ciclo, '
                                'p. ej. ["-MM1", "-MM2"]')
    malos = [x for x in ciclo if x not in cilindros]
    if malos or len(set(ciclo)) != len(ciclo):
        raise ServiceError(400, f"neumatica.ciclo: {', '.join(malos) or 'un cilindro repetido'}; "
                                f"cilindros: {', '.join(sorted(cilindros)) or 'ninguno'} (cada uno una vez)")
    tubos = tuple((t.desde, t.hasta) for t in m.tubos)
    return CircuitoAire(tuple(aparatos), tubos, tuple(ciclo),
                        _detectores(m, an, cilindros, opciones.get("detectores")))


def lamina(doc, opciones: dict | None = None, *, hoja: str = "A3", meta: dict | None = None):
    """La lámina ISO 1219 (`SheetModel`) del circuito de aire del documento."""
    from apolo.drawing.neumatica import lamina_neumatica

    c = circuito(doc, opciones)
    try:
        return lamina_neumatica(c, proyecto=getattr(doc, "name", "") or "Sin título", hoja=hoja, meta=meta)
    except ValueError as exc:
        raise ServiceError(400, str(exc)) from exc
