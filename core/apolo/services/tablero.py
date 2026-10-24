"""El tablero armado de un documento (plan V8.5, D15): lo que `layout_tablero` dejó en la escena,
leído desde el `Document`. El llamador sostiene `STATE_LOCK`.

- `dibujados`: los dispositivos que el layout dibujó (designación → id de su cuerpo). Ya cuentan
  en la escena con su ref: la BOM del carril (`bom_electrico.filas_electricas`) y el aviso
  «pieza sin ligar» del ERC no los cuentan otra vez (F1b: sin esto el variador se cobraba dos
  veces, 280 + 280 USD, como un dispositivo sin ligar).
- `regla_orden` (el lint de D1/A15): la firma del layout cambia con cada aparato de su
  ubicación, y lo que venga después se re-ejecuta al editar uno. Después de él sólo caben el
  carril, otro layout y las uniones que sujetan el gabinete (`fasten`, `ground`,
  `create_group`): lo demás es aviso (los `set_variable` el documento los sube a la cabecera).

- `armados` (F2): el `Layout` y el `Armado` de cada layout vivo, RECALCULADOS desde su comando y
  el carril (la misma `plan` del executor, con las mismas variables y la misma lectura: D12, el
  ruteo no se cachea en la geometría);
- `ruteos` (F2, D3/D4): el ruteo de cada tablero (`library/electrico/ruteo.py`) con lo que sale
  del catálogo (la cara de cada borne, el Ø exterior de cada conductor, la sección útil de la
  canaleta) y el id de la canaleta más llena; `largos` = lo que la BOM compra por metro;
- `incluidas` (F2, D9): la puerta y la placa que vienen CON el gabinete del catálogo y no se
  cobran aparte (la puerta siempre; la placa si `specs.placa_montaje`).
Las reglas del ERC que salen del ruteo están en `tablero_reglas.py`.

Lo que lee el panel del visor (veredicto, ítems y detalle; F3b) está en `tablero_panel.py`, sobre
`ruteos` y los selectores de `tablero_reglas.py`: la única fuente para el visor,
`get_circuit tablero=true` y el ERC.
"""

from __future__ import annotations

from dataclasses import dataclass, field

LAYOUT = "layout_tablero"
#: lo que puede ir DESPUÉS del layout sin costo
DESPUES_SIN_COSTO = frozenset({LAYOUT, "fasten", "ground", "create_group"})


def _ubicacion(texto) -> str:
    t = str(texto or "").strip()
    return f"+{t}" if t and not t.startswith("+") else t


def layouts(doc) -> list[tuple[str, str]]:
    """[(id del comando, ubicación)] de los `layout_tablero` VIVOS (su gabinete está en la escena)."""
    return [(c["id"], _ubicacion((c.get("params") or {}).get("ubicacion")))
            for c in doc.commands
            if c.get("type") == LAYOUT and f"{c['id']}_gabinete" in doc.scene]


def dibujados(doc, m=None) -> dict[str, str]:
    """{designación: id del cuerpo} de los dispositivos que dibujó un layout (los ligados a una
    `pieza` no: ya cuentan por su pieza)."""
    from apolo.library.catalog import CATALOG
    from apolo.library.electrico.armado import clave_aparato

    from .electrico import modelo

    vivos = layouts(doc)
    if not vivos:
        return {}
    m = m if m is not None else modelo(doc)
    out: dict[str, str] = {}
    for cid, u in vivos:
        for d in m.dispositivos:
            if d.ubicacion != u or d.pieza:
                continue
            comp = CATALOG.get(d.ref)
            if comp is not None and comp.electrico is not None and comp.electrico.simbolo == "gabinete":
                out[d.designacion] = f"{cid}_gabinete"
                continue
            base = f"{cid}_{clave_aparato(d.designacion)}"
            for fid in (base, f"{base}_1"):
                if fid in doc.scene:
                    out[d.designacion] = fid
                    break
    return out


def piezas_del_layout(doc) -> set[str]:
    """Los ids de todo lo que armó un layout (sus piezas llevan su command_id)."""
    ids = {cid for cid, _ in layouts(doc)}
    return {fid for fid, f in doc.scene.items() if getattr(f, "command_id", None) in ids}


def regla_orden(doc) -> list[dict]:
    """Aviso del ERC: un `layout_tablero` que no es el último comando de la escena."""
    from apolo.doc.carril import es_carril

    filas = []
    cmds = doc.commands
    for i, c in enumerate(cmds):
        if c.get("type") != LAYOUT:
            continue
        despues = [x for x in cmds[i + 1:] if not es_carril(x) and x.get("type") not in DESPUES_SIN_COSTO]
        if not despues:
            continue
        lista = ", ".join(f"{x['id']} ({x.get('type')})" for x in despues[:5])
        lista += f" y {len(despues) - 5} más" if len(despues) > 5 else ""
        u = _ubicacion((c.get("params") or {}).get("ubicacion"))
        filas.append({
            "regla": "layout del tablero al final", "estado": "aviso",
            "detalle": (f"el layout_tablero {c['id']} ({u}) no es el último de la escena: después "
                        f"vienen {lista}. Editar un aparato de {u} re-ejecuta el layout Y esos "
                        f"{len(despues)} comando(s). "
                        f"Rehazlo al final: remove_commands(['{c['id']}']) y run_command "
                        "layout_tablero con los mismos params (sus uniones al gabinete, después)"),
            "recomendacion": "El layout del tablero va al final de la escena; detrás, sólo el carril "
                             "y las uniones que sujetan el gabinete (fasten, ground).",
            "norma": "criterio de diseño", "elementos": [c["id"], *(x["id"] for x in despues[:5])]})
    return filas


# ── F2: el armado recalculado, el ruteo y lo que viene con el gabinete ─────────────────────


@dataclass(frozen=True)
class Tablero:
    """Un tablero armado, leído: su comando, el armado recalculado y su ruteo."""
    cid: str
    ubicacion: str
    layout: object                  # colocacion_modelo.Layout
    armado: object                  # armado.Armado
    ruteo: object                   # ruteo.Ruteo
    canaleta_ref: str
    canaletas: dict = field(default_factory=dict)  # índice de Layout.canaletas → id de su pieza
    supuestos: tuple = ()
    params: object = None           # LayoutTableroParams validados (posición del gabinete: F3b)


def armados(doc) -> list[tuple[str, object, object, object]]:
    """[(id, params validados, Layout, Armado)] de los layouts vivos, recalculados con la MISMA
    `plan` del executor: las variables del documento (están en la cabecera del log, A15) y la
    misma lectura del carril (`doc/carril.lectura`)."""
    from apolo.commands.registry import validate_params
    from apolo.commands.state import ExecContext, RegenState
    from apolo.commands.tablero import dispositivos, plan
    from apolo.doc.carril import es_carril, lectura

    vivos = {cid for cid, _ in layouts(doc)}
    if not vivos:
        return []
    variables = dict(doc.variables_raw)
    carril = [c for c in doc.commands if es_carril(c)]
    out = []
    for cmd in doc.commands:
        if cmd.get("id") not in vivos:
            continue
        p = validate_params(LAYOUT, dict(cmd.get("params") or {}), variables)
        ctx = ExecContext(RegenState(variables=variables), {}, lectura(cmd, carril))
        lay, arm, _ = plan(p, dispositivos(ctx, p.ubicacion))
        out.append((cmd["id"], p, lay, arm))
    return out


def _diametros(m) -> tuple[dict, list[str]]:
    """{conductor id: Ø exterior en mm} y lo supuesto: la ref del conductor; un hilo de cable o
    un conductor con sólo su sección, el Ø del conductor suelto del catálogo de esa sección."""
    from apolo.library.catalog import CATALOG

    por_seccion = {}
    for comp in CATALOG.values():
        e = comp.electrico
        if e is not None and e.conductor is not None and not e.conductor.hilos and \
                (comp.params or {}).get("diameter"):
            por_seccion.setdefault(float(e.conductor.seccion_mm2), float(comp.params["diameter"]))
    cables = {c.designacion: c for c in m.cables}
    out, supuestos = {}, []
    for c in m.conductores:
        comp = CATALOG.get(c.tipo or "")
        if comp is not None and (comp.params or {}).get("diameter"):
            out[c.id] = float(comp.params["diameter"])
            continue
        seccion = c.seccion_mm2
        if seccion is None and c.cable in cables:
            seccion = cables[c.cable].seccion_mm2
        if seccion is not None and float(seccion) in por_seccion:
            out[c.id] = por_seccion[float(seccion)]
            if c.cable:
                supuestos.append("Ø de un hilo de cable = el del conductor suelto de su sección")
    return out, sorted(set(supuestos))


def _con_bornes(lay, m, u: str) -> tuple[dict, frozenset]:
    from apolo.library.catalog import CATALOG
    from apolo.library.electrico.bornes_pos import caras
    from apolo.library.electrico.ruteo import ConBornes

    disp = {d.designacion: d for d in m.dispositivos if d.ubicacion == u}
    gabinete = frozenset(des for des, d in disp.items() if CATALOG.get(d.ref) is not None
                         and CATALOG[d.ref].electrico is not None
                         and CATALOG[d.ref].electrico.simbolo == "gabinete")
    out = {}
    for c in lay.aparatos:
        d = disp.get(c.designacion)
        comp = CATALOG.get(c.ref)
        if d is None or comp is None or comp.electrico is None:
            continue
        t = comp.tablero
        frente = bool(t is not None and t.acopla_a is not None and t.acopla_a.cara == "frente")
        out[c.designacion] = ConBornes(c, caras(
            [(b.id, b.lado) for b in d.bornes], tipo=(d.modelo or {}).get("tipo"),
            montaje=comp.electrico.montaje, bornera=d.bornera, acopla_frente=frente,
            propias=t.bornes if t is not None else None), int(d.cantidad or 1) if d.bornera else 1)
    return out, gabinete


def pieza_canaleta(cid: str, arm, k, desde: float, hasta: float) -> str | None:
    """El id de la pieza de canaleta (las horizontales van cortadas) que contiene ese trozo."""
    mitad = (desde + hasta) / 2
    u, v = (mitad, (k.v0 + k.v1) / 2) if k.orientacion == "h" else ((k.u0 + k.u1) / 2, mitad)
    x, z = u - arm.interior.placa_ancho / 2, v - arm.interior.placa_alto / 2
    for pz in arm.piezas:
        c = pz.caja
        if pz.clave.startswith("canaleta_") and c.x0 - 1e-6 <= x <= c.x1 + 1e-6 and c.z0 - 1e-6 <= z <= c.z1 + 1e-6:
            return f"{cid}_{pz.clave}"
    return None


def ruteos(doc, m=None) -> list[Tablero]:
    """El ruteo de cada tablero armado (D3): largos de sus conductores y llenado de canaletas."""
    from apolo.library.catalog import CATALOG
    from apolo.library.electrico.armado import ref_canaleta
    from apolo.library.electrico.colocacion import Reglas
    from apolo.library.electrico.ruteo import Entrada, Marco, rutear

    vivos = armados(doc)
    if not vivos:
        return []
    from .electrico import modelo

    m = m if m is not None else modelo(doc)
    diam, sup = _diametros(m)
    entradas = [Entrada(c.id or c.etiqueta, tuple(c.puntos), diam.get(c.id), c.tipo == "puente",
                        c.cable, c.largo_m) for c in m.conductores]
    out = []
    for cid, p, lay, arm in vivos:
        reglas = Reglas(reserva=p.reserva)
        rc = ref_canaleta(reglas)
        ficha = CATALOG[rc].tablero.canaleta if CATALOG.get(rc) is not None else None
        g = CATALOG[lay.gabinete].tablero.gabinete
        i = arm.interior
        marco = Marco(i.placa_ancho, i.placa_alto, reglas.canaleta_alto_mm, i.bisagra,
                      (i.alto - i.placa_alto) / 2 - i.espesor, g.pasacables.cara,
                      ficha.seccion_util_mm2 if ficha else reglas.canaleta_ancho_mm * reglas.canaleta_alto_mm)
        aparatos, gabinete = _con_bornes(lay, m, p.ubicacion)
        r = rutear(lay, marco, aparatos, entradas, gabinete=gabinete)
        piezas = {ll.canaleta: pieza_canaleta(cid, arm, lay.canaletas[ll.canaleta], ll.desde, ll.hasta)
                  for ll in r.llenados}
        out.append(Tablero(cid, p.ubicacion, lay, arm, r, rc, piezas, tuple(sup), p))
    return out


def largos(tableros: list[Tablero]) -> dict[str, float]:
    """{conductor id: m} que la BOM compra por metro desde el ruteo: los que quedan DENTRO de un
    tablero, sin cable y sin largo declarado (el declarado manda y lo pone la BOM)."""
    out: dict[str, float] = {}
    for t in tableros:
        for r in t.ruteo.rutas:
            if not r.sale and r.cable is None and r.declarado_mm is None:
                out.setdefault(r.id, round(r.largo_mm / 1000.0, 3))
    return out


def incluidas(doc) -> dict[str, str]:
    """{id de la pieza: id del gabinete que la trae}: lo que el layout dibuja y se compra CON el
    gabinete del catálogo (D9, criterio de diseño): la PUERTA siempre (un gabinete de pared se
    vende con su puerta) y la PLACA de montaje si su ficha dice `specs.placa_montaje: true` (si
    no, se compra aparte y sale como pieza a medida)."""
    from apolo.library.catalog import CATALOG

    out = {}
    for cid, _ in layouts(doc):
        gab = f"{cid}_gabinete"
        comp = CATALOG.get(getattr(doc.scene[gab], "component", None) or "")
        if f"{cid}_puerta" in doc.scene:
            out[f"{cid}_puerta"] = gab
        if comp is not None and (comp.specs or {}).get("placa_montaje") and f"{cid}_placa" in doc.scene:
            out[f"{cid}_placa"] = gab
    return out
