"""Executor de `create_chain`: la cadena de rodillos RELACIONAL entre dos piñones colocados
(plan `docs/plans/cadenas-pinones.md`, D7). Sus params están en `models_transmision.py` y la
matemática, en `apolo/library/transmision.py` (pura).

`medir_transmision` es lo que el executor y la regla «transmisión por cadena»
(`services/transmision_rules.py`, D9) miden IGUAL: lee las anclas VIVAS de los dos piñones
(`eje`, `hilera_k`, `fase`, que `insert_component` llevó a mundo y que `transform`, `snap_to`,
los mates… transforman), valida el montaje y devuelve números puros (`Transmision`).

MARCO DEL LAZO (el de `transmision.camino_paso`): origen en el ancla `hilera_{a}` de A (su eje,
en el plano medio de la hilera), Z = el eje de A, X = hacia el eje de B proyectado en ese plano,
Y = Z × X. Ahí B queda en (C, 0) y la `fase` de cada piñón es el ángulo de su ancla `fase`. La
geometría se construye en ese marco y se coloca con la matriz (`Feature.matrix`): lazos con los
mismos números comparten `mesh_key` y la geometría ya construida (D7: un transportador de 30
lazos construye y tesela UNA vez).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .errors import CommandError
from .models_transmision import CreateChainParams
from .state import ExecContext

#: Tolerancias de montaje (D7): ejes paralelos e hileras coplanares.
TOL_PARALELO_DEG = 0.5
TOL_COPLANAR_MM = 1.0
#: Holgura mínima entre las puntas de los dientes de A y B (mm): con menos, los piñones se tocan.
HOLGURA_PUNTAS_MM = 3.0
#: Decimales de lo medido. La clave de la geometría y la geometría salen de los MISMOS valores
#: redondeados: dos lazos que sólo difieren en ruido numérico comparten la malla.
_DEC_MM = 4
_DEC_RAD = 6


def _sub(a, b) -> list[float]:
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _escala(a, k: float) -> list[float]:
    return [a[0] * k, a[1] * k, a[2] * k]


def _cruz(a, b) -> list[float]:
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _unit(a) -> list[float]:
    return _escala(a, 1.0 / math.sqrt(_dot(a, a)))


@dataclass(frozen=True)
class Transmision:
    """Lo que se mide de un `create_chain`: refs y números, sin OCCT."""

    cadena: str
    serie: str
    paso: float
    hileras: int             # de la CADENA (2 = doble)
    ref_a: str
    ref_b: str
    za: int
    zb: int
    centros: float           # mm entre los ejes, en el plano de la hilera
    eslabones: int           # el menor PAR cuyo centro exacto es ≥ `centros`
    centros_exactos: float   # mm para ese número de eslabones (la diferencia es la holgura)
    fase_a: float            # rad en el marco del lazo, módulo 2π/z
    fase_b: float
    marco: tuple             # 4x4 por filas: marco del lazo → mundo

    @property
    def largo_mm(self) -> float:
        return round(self.eslabones * self.paso, 3)

    def clave(self, detalle: str) -> str:
        """`mesh_key`: todo lo que define la geometría del lazo en su marco local."""
        return (f"cadena|{self.cadena}|{detalle}|{self.za}|{self.zb}|{self.centros:.{_DEC_MM}f}"
                f"|{self.fase_a:.{_DEC_RAD}f}|{self.fase_b:.{_DEC_RAD}f}|{self.eslabones}")


def _pinon(scene, fid: str, campo: str):
    from apolo.library.catalog import CATALOG

    feat = scene.get(fid)
    if feat is None:
        raise CommandError(
            f"No existe la pieza '{fid}' ({campo}): coloca los dos piñones ANTES de la cadena en "
            "el registro (insert_component con una ref PINON-…)"
        )
    comp = CATALOG.get(feat.component or "")
    anclas = feat.anchors or {}
    if comp is None or "z" not in comp.specs or "fase" not in anclas or "eje" not in anclas:
        raise CommandError(
            f"La pieza '{fid}' ({campo}) no es un piñón de catálogo con sus anclas: insértalo con "
            "insert_component y una ref PINON-…"
        )
    return feat, comp


def _compatible(cadena, comp, fid: str) -> None:
    sc, sp = cadena.specs, comp.specs
    if sp.get("serie") != sc.get("serie") or abs(float(sp["paso"]) - float(sc["paso"])) > 1e-6:
        raise CommandError(
            f"La cadena {cadena.ref} es {sc.get('serie')} (paso {sc['paso']:g}, rodillo "
            f"Ø{sc['rodillo']:g}) y el piñón '{fid}' ({comp.ref}) es {sp.get('serie')} (paso "
            f"{sp['paso']:g}, rodillo Ø{sp['rodillo']:g}): no son intercambiables. Usa la cadena "
            f"{sp.get('cadena')} o un piñón {sc.get('serie')}."
        )
    tipo = sp.get("tipo")
    if int(sc.get("hileras", 1)) == 2 and tipo != "duplex":
        raise CommandError(
            f"La cadena doble {cadena.ref} va sólo sobre piñón dúplex y '{fid}' ({comp.ref}) es "
            f"{tipo}: usa un piñón dúplex {sc.get('serie')} o una cadena simple."
        )
    if int(sc.get("hileras", 1)) == 1 and tipo == "duplex":
        raise CommandError(
            f"El piñón dúplex '{fid}' ({comp.ref}) lleva cadena doble ({sp.get('cadena')}); para "
            "dos cadenas simples en un mismo cubo usa un piñón doble-simple."
        )


def _hilera(feat, comp, fid: str, hilera: int, campo: str, doble: bool) -> list[float]:
    if doble and hilera != 1:
        raise CommandError(
            f"Con cadena doble, {campo} es 1: la cadena cubre las dos hileras del dúplex '{fid}'."
        )
    ancla = (feat.anchors or {}).get(f"hilera_{hilera}")
    if ancla is None:
        raise CommandError(
            f"El piñón '{fid}' ({comp.ref}) es {comp.specs.get('tipo')}: sólo tiene la hilera 1 "
            f"({campo} = 1)."
        )
    return list(ancla["origin"])


def _fase(feat, x, y, z: int) -> float:
    """Ángulo del ancla `fase` alrededor del eje del piñón, en el marco del lazo, módulo 2π/z
    (los z asientos son el mismo conjunto con cualquier asiento de referencia)."""
    v = _sub(feat.anchors["fase"]["origin"], feat.anchors["eje"]["origin"])
    paso_ang = 2.0 * math.pi / z
    f = round(math.atan2(_dot(v, y), _dot(v, x)) % paso_ang, _DEC_RAD)
    return 0.0 if paso_ang - f < 10.0 ** -_DEC_RAD else f


def medir_transmision(scene, p: CreateChainParams) -> Transmision:
    """Valida el montaje (norma, hileras, ejes paralelos, plano común, centros) con mensajes
    que dicen qué corregir y mide el lazo. Lanza `CommandError`."""
    from apolo.kernel.matrix import frame
    from apolo.library.catalog import CATALOG
    from apolo.library.transmision import eslabones_pares

    if p.pinon_a == p.pinon_b:
        raise CommandError("La cadena une dos piñones distintos: pinon_a y pinon_b son la misma pieza")
    cadena = CATALOG[p.cadena]
    sc = cadena.specs
    doble = int(sc.get("hileras", 1)) == 2
    fa, ca = _pinon(scene, p.pinon_a, "pinon_a")
    fb, cb = _pinon(scene, p.pinon_b, "pinon_b")
    _compatible(cadena, ca, p.pinon_a)
    _compatible(cadena, cb, p.pinon_b)
    oa = _hilera(fa, ca, p.pinon_a, p.hilera_a, "hilera_a", doble)
    ob = _hilera(fb, cb, p.pinon_b, p.hilera_b, "hilera_b", doble)

    z = _unit(fa.anchors["eje"]["axis"])
    angulo = math.degrees(math.acos(min(1.0, abs(_dot(z, _unit(fb.anchors["eje"]["axis"]))))))
    if angulo > TOL_PARALELO_DEG:
        raise CommandError(
            f"Los ejes de '{p.pinon_a}' y '{p.pinon_b}' no son paralelos ({angulo:.2f}° > "
            f"{TOL_PARALELO_DEG:g}°): dales el mismo giro (rotation de insert_component o transform)."
        )
    d = _sub(ob, oa)
    desfase = _dot(d, z)
    if abs(desfase) > TOL_COPLANAR_MM:
        raise CommandError(
            f"Las hileras no están en el mismo plano: la de '{p.pinon_b}' queda a {desfase:+.2f} mm "
            f"de la de '{p.pinon_a}' a lo largo del eje (tolerancia {TOL_COPLANAR_MM:g} mm): mueve "
            "un piñón por su eje esa distancia o elige la otra hilera."
        )
    if doble:  # la hilera 2 de cada dúplex tiene que caer en la 2.ª hilera de la cadena (−pt)
        for feat, fid in ((fa, p.pinon_a), (fb, p.pinon_b)):
            off = _dot(_sub(feat.anchors["hilera_2"]["origin"], oa), z) + float(sc["pt"])
            if abs(off) > TOL_COPLANAR_MM:
                raise CommandError(
                    f"La hilera 2 del dúplex '{fid}' no cae en la segunda hilera de la cadena "
                    f"(desfase {off:+.2f} mm): el piñón está volteado; gíralo 180° para que su cubo "
                    f"quede del mismo lado que el de '{p.pinon_a}'."
                )
    dp = _sub(d, _escala(z, desfase))
    centros = math.sqrt(_dot(dp, dp))
    de_a, de_b = float(ca.specs["de"]), float(cb.specs["de"])
    minimo = (de_a + de_b) / 2.0 + HOLGURA_PUNTAS_MM
    if centros <= minimo:
        raise CommandError(
            f"Los piñones están demasiado cerca: centros {centros:.1f} mm ≤ {minimo:.1f} mm (Ø "
            f"exteriores {de_a:g} y {de_b:g} más {HOLGURA_PUNTAS_MM:g} mm entre las puntas de los "
            "dientes): sepáralos."
        )
    x = _escala(dp, 1.0 / centros)
    y = _cruz(z, x)
    za, zb = int(ca.specs["z"]), int(cb.specs["z"])
    centros = round(centros, _DEC_MM)
    paso = float(sc["paso"])
    try:
        eslabones, exactos = eslabones_pares(paso, za, zb, centros)
    except ValueError as exc:
        raise CommandError(f"Cadena: {exc}") from exc
    marco = frame(tuple(oa), x, y, z)
    return Transmision(
        cadena=p.cadena, serie=str(sc.get("serie")), paso=paso, hileras=int(sc.get("hileras", 1)),
        ref_a=ca.ref, ref_b=cb.ref, za=za, zb=zb, centros=centros, eslabones=eslabones,
        centros_exactos=exactos, fase_a=_fase(fa, x, y, za), fase_b=_fase(fb, x, y, zb),
        marco=tuple(tuple(fila) for fila in marco),
    )


def geometria_lazo(t: Transmision, detalle: str):
    """El lazo en su marco local: rodillos sentados en los asientos de A y B
    (`transmision.rodillos_del_lazo`) y la cadena por esos centros, completa («eslabones», UN
    sólido) o sólo sus bandas de placas («simple»)."""
    from apolo.library.builders_transmision import cadena_bandas, cadena_por_rodillos
    from apolo.library.catalog import CATALOG
    from apolo.library.transmision import capas_cadena, rodillos_del_lazo

    s = CATALOG[t.cadena].specs
    try:
        capas = capas_cadena(s["ancho_interior"], s["espesor_placa"], s["ancho_sobre_perno"],
                             t.hileras, float(s.get("pt", 0.0)))
        lazo = rodillos_del_lazo(t.paso, t.za, t.zb, t.centros, t.fase_a, t.fase_b, t.eslabones)
        if detalle == "simple":
            return cadena_bandas(lazo.puntos, s["alto_placa"], capas)
        return cadena_por_rodillos(lazo.puntos, True, s["rodillo"], s["perno"], s["alto_placa"],
                                   capas)
    except (ValueError, RuntimeError) as exc:
        raise CommandError(f"Cadena: {exc}") from exc


def _exec_create_chain(ctx: ExecContext, cmd_id: str, p: CreateChainParams) -> None:
    """Cadena de rodillos entre dos piñones (D7): mide el lazo con las anclas VIVAS, reusa la
    geometría de un lazo idéntico (misma clave = mismos números) o la construye, la coloca con
    la matriz del marco del lazo y declara el contacto con cada piñón."""
    from apolo.assembly.connectivity import ConnectivityError, register_fastener
    from apolo.kernel.shapes import place_matrix

    from .registry import DEFINITIONS, Feature, register_definition

    t = medir_transmision(ctx.scene, p)
    clave = t.clave(p.detalle)
    base = DEFINITIONS.get(clave)
    if base is None:
        base = geometria_lazo(t, p.detalle)
    register_definition(clave, base)
    ctx.scene[cmd_id] = Feature(
        cmd_id, p.name, place_matrix(base, t.marco), cmd_id, component=p.cadena,
        cut_length=t.largo_mm, mesh_key=clave, matrix=[list(fila) for fila in t.marco],
    )
    for lado, fid in (("a", p.pinon_a), ("b", p.pinon_b)):
        try:
            register_fastener(ctx.fasteners, cmd_id, {
                "name": f"{cmd_id}_{lado}", "a": cmd_id, "b": fid, "kind": "contacto",
                "nota": f"{p.name}: la cadena apoya en su piñón",
            })
        except ConnectivityError as exc:
            raise CommandError(str(exc)) from exc
