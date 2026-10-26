"""Executor de `layout_tablero` (plan V8.5 F1b: D1, D2, D5, D8, A9, A15): el tablero en 3D desde su
circuito.

Lee el carril de SU ubicación (`ExecContext.carril`, `CommandSpec.lee_carril`: sólo lo que firma,
`doc/carril.lectura`), valida cada `add_device` con las variables del punto del log (A15), coloca
con `library/electrico/colocacion.py`, arma las cajas con `armado.py` y aquí sólo hace la
geometría (`tablero_geom.py`) y declara lo que la sostiene:

- piezas `{cmd}_gabinete` (cuerpo hueco, la ref del gabinete), `{cmd}_puerta`, `{cmd}_placa`,
  `{cmd}_riel_i`, `{cmd}_canaleta_i`, `{cmd}_tope_i{a|b}`, `{cmd}_tapa_i` y un cuerpo por aparato
  `{cmd}_d_<designación>` (en una bornera, `_k` por borne), todas con el command_id del
  comando (la puerta de publicación cruza sus pares, como en `create_belt_conveyor`);
- las uniones internas (`fasten` `{cmd}_u_<clave>`: placa a los espárragos, rieles y canaletas
  con tornillos, aparatos al riel por contacto, lo de placa con tornillos) y la junta GIRATORIA
  de la puerta `{cmd}_puerta` (0–110°, sin `arrastrar`) con una junta FIJA `{cmd}_jf_<clave>`
  por cada mando: la FK mueve sólo los hijos declarados. Por correr `fasten` y `add_joint` del
  registro es COMPUESTO;
- D5: la puerta abre sin chocar en TODO su recorrido (`recorrido_puerta.recorrer`, cada 1°) y
  sin chocar con el resto de la escena (`tablero_chequeos.vecinos`); si choca, error con la
  pieza, el ángulo y cuánto se mete.

A9 — un dispositivo con `pieza` NO se redibuja: el layout le reserva su lugar y EXIGE que su
pieza esté dentro del gabinete (un mando de puerta, en la puerta, y cuelga de ella por su junta
fija) y que no choque con lo que se arma (`tablero_chequeos.piezas_ligadas`). Un gabinete
declarado como dispositivo de la ubicación es la ref del gabinete con «auto»; ligado a una
pieza es error (el layout dibuja el gabinete hueco).

La huella D11 cubre sólo `_exec_layout_tablero`: cambiar la geometría de `armado.py`,
`colocacion*.py` o `tablero_geom.py` con los mismos params es subir su `version` a mano.
"""

from __future__ import annotations

from dataclasses import replace

from pydantic import ValidationError

from .errors import CommandError
from .models_tablero import LayoutTableroParams
from .spec import CommandSpec, run_executor
from .state import ExecContext

#: el tope de la junta de la puerta (D5)
ABRE_DEG = 110.0


def dispositivos(ctx: ExecContext, ubicacion: str) -> list:
    """Los `add_device` de la ubicación validados con las variables de ESTE punto del log (A15)."""
    from .registry import validate_params

    out = []
    for e in ctx.carril:
        if e["type"] != "add_device":
            continue
        try:
            out.append((e["id"], validate_params("add_device", dict(e["params"]), ctx.variables)))
        except CommandError as exc:
            raise CommandError(f"Tablero {ubicacion}: el dispositivo {e['id']} no valida en este "
                               f"punto del log ({exc}): revisa su `=expr` (se resuelve con las variables del "
                               "proyecto, A15)") from None
    return out


def _medir(cache: dict):
    from apolo.library.catalog import build_component

    def medir(ref: str):
        if ref not in cache:
            bb = build_component(ref)[0].bounding_box()
            cache[ref] = (bb.size.X, bb.size.Y, bb.size.Z)
        return cache[ref]
    return medir


def plan(p: LayoutTableroParams, devs: list):
    """(Layout, Armado, avisos) de unos params y sus dispositivos validados. Puro salvo la medida
    de las refs que no son cajas (bbox del catálogo). CommandError accionable si no entra."""
    from apolo.library.catalog import CATALOG
    from apolo.library.electrico.armado import REF_TAPA, ArmadoError, Interior, armar
    from apolo.library.electrico.colocacion import ColocacionError, Reglas, colocar
    from apolo.library.electrico.colocacion_catalogo import (
        aparatos_desde_catalogo,
        gabinetes_del_catalogo,
    )
    from apolo.library.electrico.ficha_tablero import apoyo_de

    from .tablero_geom import huecos_por_ref

    u = p.ubicacion
    gabs_decl = [(cid, d) for cid, d in devs
                 if CATALOG.get(d.ref) is not None and CATALOG[d.ref].electrico is not None
                 and CATALOG[d.ref].electrico.simbolo == "gabinete"]
    if len(gabs_decl) > 1:
        raise CommandError(f"Tablero {u}: la ubicación declara {len(gabs_decl)} gabinetes ("
                           f"{', '.join(d.designacion for _, d in gabs_decl)}): un tablero es un gabinete")
    gab_ref = p.gabinete
    if gabs_decl:
        _, g = gabs_decl[0]
        if g.pieza:
            raise CommandError(f"Tablero {u}: el gabinete {g.designacion} está ligado a la pieza "
                               f"«{g.pieza}»; el layout dibuja el gabinete hueco con su puerta: borra "
                               f"esa pieza (remove_commands) y quítale la `pieza` a {g.designacion}")
        if p.gabinete == "auto":
            gab_ref = g.ref
        elif p.gabinete != g.ref:
            raise CommandError(f"Tablero {u}: el circuito declara el gabinete {g.designacion} = "
                               f"{g.ref} y el layout pide {p.gabinete}: cambia uno de los dos "
                               "(o deja gabinete=«auto»)")
    decl = {cid for cid, _ in gabs_decl}
    entradas = [{"designacion": d.designacion, "ref": d.ref, "cantidad": d.cantidad, "pieza": d.pieza}
                for cid, d in devs if cid not in decl]
    reglas = Reglas(reserva=p.reserva)
    try:
        aparatos, avisos = aparatos_desde_catalogo(entradas, CATALOG, medir=_medir({}))
        gabinetes = gabinetes_del_catalogo(CATALOG)
        if p.bisagra:
            gabinetes = [replace(g, bisagra=p.bisagra) for g in gabinetes]
        if gab_ref != "auto" and gab_ref not in {g.ref for g in gabinetes}:
            raise ColocacionError(f"el gabinete {gab_ref} no tiene su interior en el catálogo "
                                  "(`tablero.gabinete`): elige otro o «auto»")
        lay = colocar(aparatos, gab_ref, gabinetes, p.overrides, reglas)
    except ColocacionError as exc:
        raise CommandError(f"Tablero {u}: {exc}") from None
    comp = CATALOG[lay.gabinete]
    gi, prm = comp.tablero.gabinete, comp.params or {}
    interior = Interior(lay.gabinete, float(prm["width"]), float(prm["depth"]), float(prm["height"]),
                        gi.placa_ancho_mm, gi.placa_alto_mm, gi.fondo_util_mm, gi.placa_fondo_mm,
                        gi.espesor_mm, gi.espesor_puerta_mm, p.bisagra or gi.bisagra)
    refs = {a.ref for a in aparatos}
    apoyos = {r: apoyo_de(CATALOG[r].familia, CATALOG[r].tablero) for r in refs}
    huecos = huecos_por_ref(refs, CATALOG)  # el Ø sale de cada ficha (pedidos-de-extensiones-ii D1)
    tapa = CATALOG.get(REF_TAPA)
    para = tuple(x.strip() for x in str((tapa.specs or {}).get("para", "")).split(",")) if tapa else ()
    cantidad = {d.designacion: int(d.cantidad or 1) for _, d in devs}
    unidades = {a.designacion: cantidad[a.designacion] for a in aparatos
                if CATALOG[a.ref].electrico.bornera}
    try:
        arm = armar(lay, interior, reglas, apoyos, huecos, para, unidades)
    except ArmadoError as exc:
        raise CommandError(f"Tablero {u}: {exc}") from None
    return lay, arm, list(avisos) + list(lay.avisos)


def _nombre(p: LayoutTableroParams, rol: str) -> str:
    return f"{p.name} {p.ubicacion} · {rol}"


def _exec_layout_tablero(ctx: ExecContext, cmd_id: str, p: LayoutTableroParams) -> None:
    from apolo.kernel.matrix import compose_place
    from apolo.kernel.shapes import place_matrix
    from apolo.library.catalog import CATALOG, build_component
    from apolo.library.electrico.recorrido_puerta import recorrer

    from . import tablero_chequeos as chequeos
    from . import tablero_geom as geom
    from .registry import REGISTRY, Feature, register_definition

    previas = dict(ctx.scene)  # lo que ya estaba: los vecinos de la puerta y las piezas de A9
    lay, arm, _avisos = plan(p, dispositivos(ctx, p.ubicacion))
    m_gab = compose_place(p.position.tuple(), p.rotation.tuple())
    bisagra = chequeos.bisagra_mundo(arm, m_gab, p)
    fid = {}  # clave → id de la pieza en la escena (la de A9, si está ligada)
    ligadas = chequeos.resolver_ligadas(arm, previas, p.ubicacion)
    propias = {"gabinete": (geom.cuerpo(arm), lay.gabinete, None),
               "puerta": (geom.puerta(arm), None, "acero"),
               "placa": (geom.placa(arm), None, "acero")}
    for pz in arm.piezas:
        if pz.clave in ligadas:
            fid[pz.clave] = ligadas[pz.clave]
            continue
        f = f"{cmd_id}_{pz.clave}"
        fid[pz.clave] = f
        if pz.clave in propias:
            forma, ref, material = propias[pz.clave]
            ctx.scene[f] = Feature(f, _nombre(p, pz.rol), place_matrix(forma, m_gab), cmd_id,
                                   component=ref, material=material)
            continue
        base, cut = build_component(pz.ref, pz.largo)
        key = f"comp|{pz.ref}|{cut if cut is not None else 'std'}"
        register_definition(key, base)
        m = geom.matriz_catalogo(pz, base, m_gab)
        rol = pz.rol if pz.designacion is None else f"{pz.rol} {CATALOG[pz.ref].name}"
        ctx.scene[f] = Feature(f, _nombre(p, rol), place_matrix(base, m), cmd_id, component=pz.ref,
                               cut_length=cut, mesh_key=key, matrix=m)
    chequeos.piezas_ligadas(arm, ligadas, ctx.scene, fid, m_gab, p.ubicacion)
    pasos = [("fasten", f"u_{pz.clave}",
              {"name": f"{cmd_id}_u_{pz.clave}", "a": fid[pz.clave], "b": fid[pz.union.soporte],
               "kind": pz.union.kind, "nota": pz.union.nota,
               **({"size": pz.union.size} if pz.union.size else {}),
               **({"qty": pz.union.qty} if pz.union.qty else {})})
             for pz in arm.piezas if pz.union is not None]
    pasos.append(("add_joint", "puerta", {
        "name": f"{cmd_id}_puerta", "type": "giratoria", "parent": fid["gabinete"],
        "child": fid["puerta"], "origin": dict(zip("xyz", bisagra[0])),
        "axis": dict(zip("xyz", bisagra[1])), "lower": 0, "upper": ABRE_DEG}))
    pasos += [("add_joint", f"jf_{pz.clave}", {
        "name": f"{cmd_id}_jf_{pz.clave}", "type": "fija", "parent": fid["puerta"],
        "child": fid[pz.clave]}) for pz in arm.moviles if pz.clave != "puerta"]
    for tipo, suf, params in pasos:
        spec = REGISTRY[tipo]
        try:
            run_executor(spec, ctx, f"{cmd_id}_{suf}", spec.model.model_validate(params, extra="forbid"))
        except (ValidationError, CommandError) as exc:
            raise CommandError(f"Tablero {p.ubicacion} ({tipo} {suf}): {exc}") from exc
    choque, n = recorrer(arm)
    if choque is not None:
        raise CommandError(
            f"Tablero {p.ubicacion}: la puerta choca al abrir: «{choque.movil}» contra "
            f"«{choque.fijo}» a {choque.angulo_deg:g}° (se mete {choque.penetracion_mm:g} mm); "
            "aleja ese mando de la bisagra (overrides {\"<designación>\": {\"posicion\": {u, v}}}) "
            "o cambia la `bisagra`")
    chequeos.vecinos(arm, ctx.scene, fid, previas, bisagra, p.ubicacion)
    ctx.joints[f"{cmd_id}_puerta"]["recorrido"] = {"de_deg": 0.0, "a_deg": ABRE_DEG,
                                                   "angulos_revisados": n, "choques": 0}


SPECS_TABLERO = [
    # v2 (pedidos-de-extensiones-ii D3): la puerta corta redondo toda ref con `specs.agujero`
    CommandSpec("layout_tablero", "Tablero armado", "electrico", LayoutTableroParams,
                _exec_layout_tablero, version=2, lee_carril=True, composite=True),  # corre fasten/add_joint
]
