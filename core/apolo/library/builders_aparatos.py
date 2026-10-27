"""Builders de los APARATOS de tablero, uno por familia (plan aparatos-de-tablero-realistas, D1):
contactor, guardamotor, interruptor modular (ITM y diferencial), PLC compacto, fuente de riel,
relé de interfaz, borne de riel y variador compacto.

Cada uno toma la envolvente de la ficha (`width` × `depth` × `height`, la de la caja que la ref
tenía antes: D2) y la llena con la forma de su familia; el marco, la regla de la envolvente y las
piezas comunes están en `aparatos_forma.py`. Devuelven sus partes por ZONA de acabado
(`{zona: forma | [formas]}`, plan seta-de-emergencia D1): el YAML de cada ref dice el acabado de
cada zona (D4) y el loader las une en UN sólido. Las refs son EJEMPLOS: un builder sirve a todas
las de su familia, y quien fabrica con otra línea sólo cambia la ficha.

Nivel de detalle (D3): lo que se ve desde la puerta abierta a un metro (los bornes en su
alojamiento con el tornillo, la palanca o el mando, la ventana, la placa de datos, el clip del
riel y las ranuras de la cara de arriba); nada que se vea sólo de cerca o desde atrás (la ranura
de la cabeza del tornillo, la boca del conductor, el texto de la placa, el perfil interior del
clip, las ranuras de abajo). Un tornillo es un cilindro. Cada detalle cuesta caras, y las caras
cuestan al construir y al teselar (D5).

Módulo propio porque `builders.py` está congelado; `loader.py` une este registro con los demás.
"""

from __future__ import annotations

from .aparatos_forma import (
    bornes_en_hombro,
    caja,
    centros,
    cilindro_y,
    clip_din,
    perfil_modular,
    placa_de_datos,
    ranuras,
    tallar,
)

_SOLAPE = 0.5


def _validar(nombre: str, width: float, depth: float, height: float, minimo=(5.0, 30.0, 30.0)):
    for valor, eje, tope in zip((width, depth, height), ("width", "depth", "height"), minimo):
        if not isinstance(valor, (int, float)) or valor < tope:
            raise ValueError(f"{nombre}: {eje} {valor} mm es menor que {tope:g} (la forma no entra)")


def _nariz(h: float) -> float:
    """El alto del frente de un aparato modular: los 45 mm del recorte de la tapa (orden de DIN
    43880), menos si el aparato es bajo."""
    return min(45.0, h - 2 * min(20.0, 0.25 * h))


def _fila_hombro(xs, h, y_cara, alto_hombro, paso):
    """Bornes arriba y abajo en los hombros (los dos lados del aparato): (cortes, tornillos)."""
    ancho = min(11.0, 0.68 * paso)
    alto = min(12.0, 0.62 * alto_hombro)
    d_t = min(6.0, 0.5 * ancho, 0.6 * alto)
    cortes, tornillos = [], []
    for s in (1, -1):
        c, t = bornes_en_hombro(xs, y_cara, s * (h / 2 - alto_hombro / 2), alto, ancho, d_tornillo=d_t)
        cortes += c
        tornillos += t
    return cortes, tornillos


# ── interruptor modular: ITM y diferencial ─────────────────────────────────────────────────
TIPOS_MODULAR = ("itm", "diferencial")


def interruptor_modular(width: float, depth: float, height: float, polos: int | None = None,
                        tipo: str = "itm"):
    """ITM o diferencial de riel (perfil DIN 43880): bornes por polo arriba y abajo, palanca de
    puente en la nariz (en ON, arriba), placa de datos y, el diferencial, su botón de prueba.
    `polos` = los de la ficha; sin él, uno por módulo de 18 mm."""
    _validar("Interruptor modular", width, depth, height)
    if tipo not in TIPOS_MODULAR:
        raise ValueError(f"Interruptor modular: tipo «{tipo}» desconocido; usa {', '.join(TIPOS_MODULAR)}")
    w, d, h = float(width), float(depth), float(height)
    n_polos = int(polos) if polos else max(1, round(w / 18.0))

    def build(_length):
        n = _nariz(h)
        sale = min(6.0, 0.08 * d)
        hombro, frente = -d / 2 + min(44.0, 0.6 * d), d / 2 - sale
        cuerpo = perfil_modular(w, d, h, hombro=hombro, nariz=n, frente=frente)
        paso = w / n_polos
        xs = centros(n_polos, w)
        cortes, tornillos = _fila_hombro(xs, h, hombro, h / 2 - n / 2, paso)
        for k in range(1, n_polos):  # la junta entre polos, en el frente de la nariz
            x = -w / 2 + k * paso
            cortes.append(caja(x - 0.3, x + 0.3, frente - 0.6, frente + _SOLAPE, -n / 2 - _SOLAPE,
                               n / 2 + _SOLAPE))
        # la palanca: una por polo unidas por el puente, en ON (arriba)
        lx, lz = (-w / 2 + 0.25 * paso, w / 2 - 0.25 * paso), (0.08 * n, 0.3 * n)
        cortes.append(caja(lx[0] - 0.5, lx[1] + 0.5, frente - 3.5, frente + _SOLAPE, lz[0] - 0.5, lz[1] + 0.5))
        palanca = caja(*lx, frente - 4.0, d / 2, *lz)
        partes = {}
        x_placa = w / 2 - min(3.0, 0.15 * w)
        if tipo == "diferencial":
            dp = min(7.0, 0.3 * w)
            xb = w / 2 - max(dp, paso / 2)
            cortes.append(cilindro_y(xb, frente - 1.5, frente + _SOLAPE, -0.25 * n, dp + 1.0))
            partes["prueba"] = cilindro_y(xb, frente - 2.0, frente + min(2.5, sale - 0.5), -0.25 * n, dp)
            x_placa = xb - dp / 2 - 2.0
        c_placa, placa = placa_de_datos(-w / 2 + min(3.0, 0.15 * w), x_placa, -0.42 * n, -0.08 * n, frente)
        c_clip, clip = clip_din(w, d, h)
        cuerpo = tallar(cuerpo, cortes + [c_placa, c_clip])
        return {"cuerpo": cuerpo, "bornes": tornillos, "palanca": palanca, "placa": placa,
                "clip": clip, **partes}

    return build


# ── contactor ──────────────────────────────────────────────────────────────────────────────
def contactor(width: float, depth: float, height: float, polos: int = 3):
    """Contactor de riel: `polos` bornes de potencia + 1 auxiliar por lado en los hombros, la
    bobina A1/A2 arriba del frente, la ranura del bloque auxiliar frontal, la ventana del
    indicador, la placa de datos y el clip."""
    _validar("Contactor", width, depth, height)
    w, d, h = float(width), float(depth), float(height)

    def build(_length):
        hb = min(16.0, 0.2 * h)
        n = h - 2 * hb
        hombro = -d / 2 + 0.58 * d
        cuerpo = perfil_modular(w, d, h, hombro=hombro, nariz=n, frente=d / 2)
        paso = w / (polos + 1)
        cortes, tornillos = _fila_hombro(centros(polos + 1, w), h, hombro, hb, paso)
        # la bobina: A1 y A2 en el frente, arriba
        xb = (-w / 2 + 0.6 * paso, w / 2 - 0.6 * paso)
        c, t = bornes_en_hombro(xb, d / 2, n / 2 - min(6.0, 0.16 * n), min(9.0, 0.22 * n),
                                min(8.0, 0.6 * paso), d_tornillo=min(4.5, 0.4 * paso))
        cortes += c
        tornillos += t
        cortes.append(caja(-w / 2 + 0.25 * paso + 6, w / 2 - 0.25 * paso - 6, d / 2 - 2.0, d / 2 + _SOLAPE,
                           0.12 * n, 0.2 * n))  # la ranura del bloque auxiliar frontal
        c_ind, indicador = placa_de_datos(-0.18 * w, 0.18 * w, -0.06 * n, 0.08 * n, d / 2)
        c_placa, placa = placa_de_datos(-w / 2 + 5, w / 2 - 5, -0.42 * n, -0.14 * n, d / 2)
        c_clip, clip = clip_din(w, d, h)
        cuerpo = tallar(cuerpo, cortes + [c_ind, c_placa, c_clip])
        return {"cuerpo": cuerpo, "bornes": tornillos, "indicador": indicador, "placa": placa,
                "clip": clip}

    return build


# ── guardamotor ────────────────────────────────────────────────────────────────────────────
def guardamotor(width: float, depth: float, height: float, polos: int = 3):
    """Guardamotor de mando giratorio: bornes por polo arriba y abajo, el mando con su barra
    de agarre, el dial de ajuste de la corriente, la placa de datos y el clip."""
    _validar("Guardamotor", width, depth, height)
    w, d, h = float(width), float(depth), float(height)

    def build(_length):
        hb = min(18.0, 0.2 * h)
        n = h - 2 * hb
        sale = min(8.0, 0.1 * d)
        hombro, frente = -d / 2 + 0.55 * d, d / 2 - sale
        cuerpo = perfil_modular(w, d, h, hombro=hombro, nariz=n, frente=frente)
        cortes, tornillos = _fila_hombro(centros(polos, w), h, hombro, hb, w / polos)
        dk, zk = min(0.62 * w, 0.5 * n), 0.12 * n
        mando = [cilindro_y(0.0, frente - _SOLAPE, d / 2 - 3.0, zk, dk),
                 caja(-0.48 * dk, 0.48 * dk, d / 2 - 3.0 - _SOLAPE, d / 2, zk - 0.14 * dk, zk + 0.14 * dk)]
        da, xa, za = min(10.0, 0.22 * w), -0.22 * w, -0.3 * n
        cortes.append(cilindro_y(xa, frente - 1.5, frente + _SOLAPE, za, da + 1.0))
        ajuste = cilindro_y(xa, frente - 2.0, frente - 0.3, za, da)
        c_placa, placa = placa_de_datos(0.0, w / 2 - 3.0, -0.42 * n, -0.18 * n, frente)
        c_clip, clip = clip_din(w, d, h)
        cuerpo = tallar(cuerpo, cortes + [c_placa, c_clip])
        return {"cuerpo": cuerpo, "bornes": tornillos, "mando": mando, "ajuste": ajuste,
                "placa": placa, "clip": clip}

    return build


# ── relé de interfaz (módulo angosto) ──────────────────────────────────────────────────────
def rele_interfaz(width: float, depth: float, height: float, bornes_por_lado: int = 2):
    """Relé de interfaz angosto: `bornes_por_lado` bornes escalonados arriba y abajo, el relé
    enchufable al frente y el clip."""
    _validar("Relé de interfaz", width, depth, height, (3.0, 30.0, 30.0))
    w, d, h = float(width), float(depth), float(height)

    def build(_length):
        hb = 0.27 * h
        n = h - 2 * hb
        hombro, y_rele = -d / 2 + 0.55 * d, d / 2 - 0.3 * d
        cuerpo = perfil_modular(w, d, h, hombro=hombro, nariz=n, frente=y_rele)
        ancho, alto = w - 1.6, hb / (bornes_por_lado + 0.8)
        cortes, tornillos = [], []
        for k in range(bornes_por_lado):
            for s in (1, -1):
                zc = s * (h / 2 - alto * (0.9 + 1.2 * k))
                c, t = bornes_en_hombro([0.0], hombro, zc, alto, ancho, d_tornillo=min(3.5, 0.6 * ancho))
                cortes += c
                tornillos += t
        rele = caja(-w / 2 + 0.2, w / 2 - 0.2, y_rele - _SOLAPE, d / 2, -n / 2 + 1.0, n / 2 - 1.0)
        c_clip, clip = clip_din(w, d, h)
        cuerpo = tallar(cuerpo, cortes + [c_clip])
        return {"cuerpo": cuerpo, "bornes": tornillos, "rele": rele, "clip": clip}

    return build


# ── borne de riel ──────────────────────────────────────────────────────────────────────────
TIPOS_BORNE = ("paso", "pe", "fusible")
#: la zona del frente de cada tipo: el marcador blanco, la franja amarilla del PE o el
#: portafusible abatible
FRENTE_BORNE = {"paso": "marcador", "pe": "franja", "fusible": "portafusible"}


def borne_riel(width: float, depth: float, height: float, tipo: str = "paso"):
    """Borne de riel escalonado: un borne de tornillo por lado en el escalón y, al frente, el
    marcador (paso), la franja amarilla (PE) o el portafusible."""
    _validar("Borne de riel", width, depth, height, (3.0, 20.0, 20.0))
    if tipo not in TIPOS_BORNE:
        raise ValueError(f"Borne de riel: tipo «{tipo}» desconocido; usa {', '.join(TIPOS_BORNE)}")
    w, d, h = float(width), float(depth), float(height)

    def build(_length):
        from .aparatos_forma import prisma_yz

        y_a, y_b = -d / 2 + 0.45 * d, -d / 2 + 0.78 * d
        z2, z3 = 0.3 * h, 0.13 * h
        y_front = d / 2 if tipo == "paso" else y_b
        pts = [(-d / 2, -h / 2), (y_a, -h / 2), (y_a, -z2), (y_b, -z2), (y_b, -z3), (y_front, -z3),
               (y_front, z3), (y_b, z3), (y_b, z2), (y_a, z2), (y_a, h / 2), (-d / 2, h / 2)]
        cuerpo = prisma_yz(pts, w)
        cortes, tornillos = [], []
        alto = 0.8 * (z2 - z3)
        for s in (1, -1):
            c, t = bornes_en_hombro([0.0], y_b, s * (z2 + z3) / 2, alto, w - 1.6,
                                    d_tornillo=min(3.5, 0.6 * (w - 1.6)))
            cortes += c
            tornillos += t
        if tipo == "paso":
            c_m, frente = placa_de_datos(-w / 2 + 0.8, w / 2 - 0.8, -z3 + 1.0, z3 - 1.0, d / 2)
            cortes.append(c_m)
        else:
            frente = caja(-w / 2 + 0.15, w / 2 - 0.15, y_b - _SOLAPE, d / 2, -z3, z3)
        cuerpo = tallar(cuerpo, cortes)
        return {"cuerpo": cuerpo, "bornes": tornillos, FRENTE_BORNE[tipo]: frente}

    return build


# ── PLC compacto ───────────────────────────────────────────────────────────────────────────
def plc_compacto(width: float, depth: float, height: float):
    """PLC compacto: las borneras arriba y abajo bajo sus tapas, la franja de LEDs de E/S, los
    LEDs de estado, el puerto de red abajo a la izquierda, las ranuras de ventilación de arriba,
    la placa de datos y el clip."""
    _validar("PLC compacto", width, depth, height)
    w, d, h = float(width), float(depth), float(height)

    def build(_length):
        hb = 0.22 * h
        n = h - 2 * hb
        hombro = d / 2 - min(14.0, 0.18 * d)
        cuerpo = perfil_modular(w, d, h, hombro=hombro, nariz=n, frente=d / 2)
        alto_tapa = min(5.0, 0.4 * (d / 2 - hombro))
        tapas = [caja(-w / 2 + 1.5, w / 2 - 1.5, hombro - _SOLAPE, hombro + alto_tapa,
                      *sorted((s * (h / 2 - hb + 1.5), s * (h / 2 - 1.5)))) for s in (1, -1)]
        cortes = []
        c_v, ventana = placa_de_datos(-w / 2 + 6, w / 2 - 6, n / 2 - 0.24 * n, n / 2 - 0.08 * n, d / 2)
        cortes.append(c_v)
        leds = []
        for k in range(3):
            x = -w / 2 + 6 + k * min(6.0, 0.06 * w)
            c, led = placa_de_datos(x, x + min(3.0, 0.03 * w), 0.05 * n, 0.05 * n + 2.0, d / 2)
            cortes.append(c)
            leds.append(led)
        ancho_rj, alto_rj = min(16.0, 0.15 * w), min(14.0, 0.25 * n)
        cortes.append(caja(-w / 2 + 6, -w / 2 + 6 + ancho_rj, d / 2 - min(10.0, 0.15 * d), d / 2 + _SOLAPE,
                           -n / 2 + 3, -n / 2 + 3 + alto_rj))
        cortes += ranuras(-w / 2 + 6, w / 2 - 6, -d / 2 + 4, hombro - 4, h / 2)
        c_placa, placa = placa_de_datos(0.0, w / 2 - 6, -0.38 * n, -0.04 * n, d / 2)
        c_clip, clip = clip_din(w, d, h)
        cuerpo = tallar(cuerpo, cortes + [c_placa, c_clip])
        return {"cuerpo": cuerpo, "tapas": tapas, "ventana": ventana, "leds": leds,
                "placa": placa, "clip": clip}

    return build


# ── fuente de riel ─────────────────────────────────────────────────────────────────────────
def fuente_riel(width: float, depth: float, height: float, bornes_arriba: int = 2,
                bornes_abajo: int = 3):
    """Fuente conmutada de riel (perfil DIN 43880): la salida arriba y la entrada abajo, el LED
    de «DC OK», el potenciómetro de ajuste, ranuras de ventilación, la placa de datos y el clip."""
    _validar("Fuente de riel", width, depth, height)
    w, d, h = float(width), float(depth), float(height)

    def build(_length):
        n = _nariz(h)
        hombro = -d / 2 + min(44.0, 0.6 * d)
        cuerpo = perfil_modular(w, d, h, hombro=hombro, nariz=n, frente=d / 2)
        cortes, tornillos = [], []
        hb = h / 2 - n / 2
        for cant, arriba in ((bornes_arriba, True), (bornes_abajo, False)):
            s = 1 if arriba else -1
            paso = w / cant
            ancho = min(10.0, 0.7 * paso)
            alto = min(12.0, 0.62 * hb)
            c, t = bornes_en_hombro(centros(cant, w), hombro, s * (h / 2 - hb / 2), alto, ancho,
                                    d_tornillo=min(6.0, 0.5 * ancho, 0.6 * alto))
            cortes += c
            tornillos += t
        xl = w / 2 - 0.2 * w
        dl, dp = min(3.0, 0.08 * w), min(6.0, 0.12 * w)
        cortes += [cilindro_y(xl, d / 2 - 1.5, d / 2 + _SOLAPE, 0.3 * n, dl + 0.6),
                   cilindro_y(xl, d / 2 - 2.0, d / 2 + _SOLAPE, 0.05 * n, dp + 1.0)]
        led = cilindro_y(xl, d / 2 - 2.0, d / 2 - 0.3, 0.3 * n, dl)
        ajuste = [cilindro_y(xl, d / 2 - 2.5, d / 2 - 0.8, 0.05 * n, dp),
                  caja(xl - 0.45 * dp, xl + 0.45 * dp, d / 2 - 1.0, d / 2 - 0.3, 0.05 * n - 0.4, 0.05 * n + 0.4)]
        cortes += ranuras(-w / 2 + 3, w / 2 - 3, hombro + 2, d / 2 - 2, n / 2)
        c_placa, placa = placa_de_datos(-w / 2 + 3, xl - dp / 2 - 2, -0.4 * n, 0.4 * n, d / 2)
        c_clip, clip = clip_din(w, d, h)
        cuerpo = tallar(cuerpo, cortes + [c_placa, c_clip])
        return {"cuerpo": cuerpo, "bornes": tornillos, "led": led, "ajuste": ajuste, "placa": placa,
                "clip": clip}

    return build


# ── variador compacto ──────────────────────────────────────────────────────────────────────
def variador_compacto(width: float, depth: float, height: float):
    """Variador de frecuencia compacto de placa: el teclado arriba (pantalla, MARCHA verde, PARO
    rojo y la perilla de velocidad), la tapa de bornes abajo, la placa de datos y las ranuras de
    ventilación de arriba."""
    _validar("Variador compacto", width, depth, height)
    w, d, h = float(width), float(depth), float(height)

    def build(_length):
        from build123d import Box

        cuerpo = Box(w, d, h)
        m = min(8.0, 0.1 * w)
        y = d / 2
        tz = (h / 2 - 0.45 * h, h / 2 - 0.08 * h)
        c_t, teclado = placa_de_datos(-w / 2 + m, w / 2 - m, *tz, y)
        alto_t = tz[1] - tz[0]
        pantalla = caja(-0.3 * w, 0.3 * w, y - 1.0, y - 0.05, tz[1] - 0.45 * alto_t, tz[1] - 0.1 * alto_t)
        db = min(9.0, 0.09 * w)
        zb = tz[0] + 0.25 * alto_t
        marcha = cilindro_y(-0.25 * w, y - 1.0, y, zb, db)
        paro = cilindro_y(-0.05 * w, y - 1.0, y, zb, db)
        perilla = cilindro_y(0.22 * w, y - 1.0, y, zb, min(16.0, 0.16 * w))
        c_tapa, tapa = placa_de_datos(-w / 2 + m, w / 2 - m, -h / 2 + 0.06 * h, -h / 2 + 0.3 * h, y)
        c_placa, placa = placa_de_datos(-w / 2 + m, 0.1 * w, -0.16 * h, 0.0, y)
        cortes = [c_t, c_tapa, c_placa]
        cortes += ranuras(-w / 2 + m, w / 2 - m, -d / 2 + 6, d / 2 - 6, h / 2, paso=6.0, ancho=2.5,
                          prof=3.0)
        cuerpo = tallar(cuerpo, cortes)
        return {"cuerpo": cuerpo, "teclado": teclado, "pantalla": pantalla, "marcha": marcha,
                "paro": paro, "perilla": perilla, "tapa": tapa, "placa": placa}

    return build


BUILDERS = {"interruptor_modular": interruptor_modular, "contactor": contactor,
            "guardamotor": guardamotor, "rele_interfaz": rele_interfaz, "borne_riel": borne_riel,
            "plc_compacto": plc_compacto, "fuente_riel": fuente_riel,
            "variador_compacto": variador_compacto}
#: todos dan partes por zona (el YAML de sus refs declara `zonas:`)
ZONADOS = frozenset(BUILDERS)
