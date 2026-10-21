"""¿El escenario prueba una banda que no avanza? (plan V8.3 F6, defecto 1).

La dinámica simula como banda sólo la de `create_belt_conveyor` (auto) y las declaradas en
`mecanica.bandas` con su junta motriz; un lazo hecho a mano sin declarar queda FUERA (unido por
fijadores a un tambor que gira) o ESTÁTICO (sujeto al bastidor). `simulate` lo avisa, pero en un
escenario el aviso se perdía y las aserciones daban verde TRIVIAL: la caja no viaja, el atasco
no carga nada. Aquí es ERROR accionable, antes de simular, cuando el escenario:
  - pone productos sobre esa banda (su (x, y) cae dentro de la huella de la banda), o
  - tiene aserciones sobre ella o sobre una pieza que no se mueve («c119.v_m_s»).
Sin productos ni aserciones sobre ella, no es asunto del escenario: queda el aviso.

`bandas_quietas(scene, esc, dyn)` corre bajo el STATE_LOCK del llamador (lee bboxes OCCT). `dyn`
es la dinámica preparada o la PREVISIÓN de `prever` (F6b): las mismas bandas, cuerpos y avisos
sin cascos ni inercias, para rechazar en milisegundos lo que antes esperaba ~20 s.
"""

from __future__ import annotations

import json
import re
from types import SimpleNamespace

#: Rol de una banda (tras el último « · », como `library/rules._BANDA_RE`, sin «faja»: un rol
#: «Faja …» nombra la máquina, no el lazo).
_BANDA = re.compile(r"^(bandas?|cintas?)\b", re.I)
#: Holgura de la huella en planta (mm): una caja apoyada en el borde también va sobre la banda.
HOLGURA_MM = 5.0


def prever(scene: dict, joints: dict, fasteners: dict, grounds: dict, peticion: dict, *,
           mates=None) -> SimpleNamespace | None:
    """Lo que `prepare_dynamics` hará con las bandas (cuáles simula, qué cuerpos arma, qué queda
    fuera y por qué) con su MISMA lógica pura (`detectar_bandas`, `clasificar`), sin cascos.
    Toma TODAS las piezas no guía (la preparación descarta además las de volumen nulo): sus
    cuerpos son un superconjunto de los reales, así que nunca acusa de quieta a una banda que la
    dinámica sí simula. None si no puede preverlo (autodetección, petición inválida): decide la
    dinámica."""
    from apolo.physics.banda import detectar_bandas
    from apolo.physics.dinamica_cuerpos import clasificar
    from apolo.physics.dinamica_peticion import parse_peticion
    from apolo.physics.sim import PhysicsError

    try:
        pet = parse_peticion(peticion)
        if pet.con_autodeteccion:
            return None
        escena = {fid: f for fid, f in scene.items() if not getattr(f, "is_guide", False)}
        req, virtuales, avisos = detectar_bandas(escena, joints, pet.bandas, pet.auto_bandas)
    except PhysicsError:
        return None
    cls = clasificar(set(escena), {**joints, **virtuales}, fasteners, grounds, mates,
                     quitar={b[0] for b in req})
    avisos = avisos + cls.avisos + [f"'{fid}' queda FUERA de la simulación: {m}"
                                    for fid, m in sorted(cls.fuera.items())]
    avisos += [f"La banda '{b[0]}' no se simula: su junta motriz '{b[1]}' quedó fuera"
               for b in req if b[1] not in cls.cuerpos]
    return SimpleNamespace(bandas=[SimpleNamespace(pieza=b[0]) for b in req if b[1] in cls.cuerpos],
                           avisos=avisos,
                           cuerpos=[{"junta": n, "piezas": ps} for n, ps in cls.cuerpos.items()])


def _es_banda(fid: str, feat) -> bool:
    from apolo.library.materials import piece_role

    return fid.endswith("_banda") or bool(_BANDA.match(piece_role(getattr(feat, "name", "") or "")))


def _por_que(fid: str, dyn) -> str:
    """Por qué la pieza no avanza, con el aviso de la dinámica si lo dio."""
    for a in dyn.avisos:
        if a.startswith(f"'{fid}' queda FUERA de la simulación"):
            return a.split(": ", 1)[-1]
        if a.startswith(f"La banda '{fid}' no se mueve") or a.startswith(f"La banda '{fid}' no se simula"):
            return a
    junta = next((c["junta"] for c in dyn.cuerpos if fid in c["piezas"]), None)
    if junta:
        return f"gira como sólido rígido con la junta '{junta}' (no es un lazo que avanza)"
    return "es estática (sujeta al bastidor): su cara no avanza"


def _sobre(feat, productos: list) -> list[str]:
    try:
        bb = feat.shape.bounding_box()
    except Exception:  # noqa: BLE001 — sin bbox no se puede decir que esté encima
        return []
    out = []
    for p in productos:
        x, y, z = (list(p.get("posicion_mm") or []) + [None] * 3)[:3]
        if x is None or y is None:
            continue
        if (bb.min.X - HOLGURA_MM <= x <= bb.max.X + HOLGURA_MM
                and bb.min.Y - HOLGURA_MM <= y <= bb.max.Y + HOLGURA_MM
                and (z is None or z >= bb.min.Z - HOLGURA_MM)):
            out.append(str(p.get("nombre") or "producto"))
    return out


def bandas_quietas(scene: dict, esc, dyn) -> str | None:
    """El texto del error (qué banda, por qué no avanza, qué la usa y qué declarar), o None."""
    simuladas = {b.pieza for b in dyn.bandas}
    piezas_aser = {a["senal"].split(".")[0]: a["texto"] for a in esc.aserciones}
    problemas, quietas = [], []
    for fid in sorted(scene):
        feat = scene[fid]
        if fid in simuladas or getattr(feat, "is_guide", False):
            continue
        banda = _es_banda(fid, feat)
        sobre = _sobre(feat, esc.productos) if banda else []
        aser = piezas_aser.get(fid)
        if not sobre and not aser:
            continue
        que = []
        if sobre:
            que.append(f"el escenario pone {', '.join(sorted(set(sobre)))} encima")
        if aser:
            que.append(f"la aserción «{aser}» la mira")
        nombre = getattr(feat, "name", "") or fid
        problemas.append(f"'{fid}' («{nombre}») no avanza en esta simulación — {_por_que(fid, dyn)} — "
                         f"y {' y '.join(que)}: el escenario daría verde sin que nada se mueva")
        quietas.append((banda, fid))
    if not problemas:
        return None
    junta = next(iter(esc.motores.values()), {}).get("junta") or "<junta del tambor motriz>"
    fids = [f for b, f in quietas if b] or [f for _, f in quietas]
    ejemplo = {"mecanica": {"bandas": [{"pieza": f, "junta_motriz": junta} for f in fids]}}
    return ("mecánica: " + "; ".join(problemas) + ". Declara cada banda hecha a mano con la junta "
            "giratoria o continua de su tambor motriz en `mecanica.bandas` del escenario, p. ej. "
            f"{json.dumps(ejemplo, ensure_ascii=False)} (opcional: radio_mm, direccion_transporte, "
            "mu, mu_cama). Si la pieza no es una banda, saca sus productos o aserciones del escenario.")
