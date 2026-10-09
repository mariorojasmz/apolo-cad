"""Simulación dinámica en lote: la máquina se mueve de verdad (V8.2).

Dos fases, como `gravity_test` (V6.2c):
- `prepare_dynamics` (bajo `STATE_LOCK`): todo el trabajo OCCT —sujeción, cuerpos de junta,
  cascos, cápsulas, inercias, la superficie de la banda— horneado en un `DynamicsSnapshot` de
  datos puros con el MJCF listo.
- `simulate_dynamics` (bajo `PHYSICS_LOCK`): MuJoCo sobre esos datos. Física a `timestep`
  (1 ms) e intercambio cada `nstep` pasos (2): en cada intercambio se escriben consignas,
  fuerzas de banda y se leen los sensores; `mj_step(nstep)` retiene todo entre medias.

Salida por TIEMPO (D9): `fps` = fotogramas por SEGUNDO simulado (en `gravity_test`/`drop_test`
es el total: no se toca, lo usa la puerta de entrega). Poses 4×4 (mm, por filas) por cuerpo
(`piezas` = formato del animador de gravedad: cada pieza apunta al cuerpo que la mueve) y por
producto (`productos` = formato del animador de caída); trazas por junta con el MISMO signo
que `set_motion` (regla de la mano derecha sobre el eje); sensores; resumen y avisos.

Las piezas ocultas CUENTAN: ocultar es estado de vista, no saca la pieza de la máquina
(regla de `library`). No muta el documento ni importa `doc`/`api`.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

import numpy as np

from apolo.physics import dinamica_modelo as dm
from apolo.physics.banda import ArrastreBanda, detectar_bandas, eje_texto, superficie_banda
from apolo.physics.dinamica_cuerpos import (
    GIRATORIAS,
    clasificar,
    combinar_inercia,
    geometria_movil,
    inercia_eje,
)
from apolo.physics.dinamica_motores import ControlMotores, inercia_minima, resolver_motores
from apolo.physics.dinamica_peticion import MAX_PRODUCTOS, instancias_producto, parse_peticion
from apolo.physics.hull import hull_vertices
from apolo.physics.sensores import Fotoceldas, SensorDatos
from apolo.physics.sim import MM, PhysicsError, _pose_matrix, _require_mujoco

_LIMITE_TOL = (0.5, 0.5)       # grados | mm: «llegó al límite»
_ESTACION = (1000.0, 1000.0, 500.0)  # m: donde esperan los productos que aún no entran


@dataclass
class DynamicsSnapshot:
    xml: str | None
    duracion_s: float
    timestep: float
    nstep: int
    fps: int
    gravedad: float
    modelo_banda: str = "contacto"
    cuerpos: list = field(default_factory=list)     # [{name, junta, tipo, piezas, origen_mm}]
    juntas: dict = field(default_factory=dict)      # apolo → {mj, tipo, rango}
    piezas: list = field(default_factory=list)      # animador de gravedad
    productos: list = field(default_factory=list)   # animador de caída + estado inicial
    motores: list = field(default_factory=list)
    bandas: list = field(default_factory=list)
    sensores: list = field(default_factory=list)
    avisos: list = field(default_factory=list)
    early: dict | None = None


def _elegibles(scene) -> set:
    out = set()
    for fid, feat in scene.items():
        if getattr(feat, "is_guide", False):
            continue
        try:
            if float(feat.shape.volume) > 0:
                out.add(fid)
        except Exception:  # noqa: BLE001 — una pieza sin volumen no entra
            continue
    return out


def _cuaternion(rot_deg) -> tuple:
    """(w, x, y, z) de una rotación con la convención de `rotation` de Apolo (`Rotation` de
    build123d), para que un producto girado nazca como la pieza que se colocaría igual."""
    if not any(rot_deg):
        return (1.0, 0.0, 0.0, 0.0)
    from build123d import Rotation

    q = Rotation(*rot_deg).wrapped.Transformation().GetRotation()
    return (q.W(), q.X(), q.Y(), q.Z())


def _geoms_pieza(fid: str, pm) -> list:
    """Geometría de colisión de una pieza móvil (m, mundo): cápsula si gira sobre su eje."""
    nombre = dm.nombre_mj("g", fid)
    if pm.giro is not None:
        g = pm.giro
        c, e, r = g["centro"], g["eje"], g["radio"]
        medio = (g["s1"] - g["s0"]) / 2
        mid = c + e * (g["s0"] + g["s1"]) / 2
        if medio > r:
            a, b = mid - e * (medio - r), mid + e * (medio - r)
            return [dm.GeomMJ("capsule", nombre, desde=tuple(a * MM), hasta=tuple(b * MM), radio=r * MM)]
        a, b = mid - e * max(medio, 0.5), mid + e * max(medio, 0.5)
        return [dm.GeomMJ("cylinder", nombre, desde=tuple(a * MM), hasta=tuple(b * MM), radio=r * MM)]
    if len(pm.vertices) < 4:
        return []
    return [dm.GeomMJ("mesh", nombre, vertices=[tuple(c * MM for c in v) for v in pm.vertices])]


def prepare_dynamics(scene, joints, fasteners, grounds, request: dict | None = None, *,
                     mates=None) -> DynamicsSnapshot:
    """FASE OCCT (bajo STATE_LOCK). `request` es la petición D3–D8 (ver `dinamica_peticion`).
    Lanza `PhysicsError` con un mensaje accionable si algo no sirve."""
    pet = parse_peticion(request)
    avisos: list[str] = []
    ids = _elegibles(scene)
    escena = {fid: scene[fid] for fid in ids}
    bandas_req, virtuales, av = detectar_bandas(escena, joints, pet.bandas, pet.auto_bandas)
    avisos += av
    todas = {**joints, **virtuales}
    extra_edges, extra_grounds = [], []
    if pet.con_autodeteccion:
        from apolo.assembly.autodetect import detect_connections

        det = detect_connections(escena)
        extra_edges = [(c["a"], c["b"]) for c in det["fasteners"]]
        extra_grounds = [g["feature"] for g in det["grounds"]]
    cls = clasificar(ids, todas, fasteners, grounds, mates, extra_edges, extra_grounds,
                     quitar={b[0] for b in bandas_req})
    avisos += cls.avisos
    fuera = sorted(cls.fuera.items())
    for fid, motivo in fuera[:20]:
        avisos.append(f"'{fid}' queda FUERA de la simulación: {motivo}")
    if len(fuera) > 20:
        avisos.append(f"… y {len(fuera) - 20} piezas más fuera de la simulación")

    snap = DynamicsSnapshot(xml=None, duracion_s=pet.duracion_s, timestep=pet.timestep,
                            nstep=pet.nstep, fps=pet.fps, gravedad=pet.gravedad,
                            modelo_banda=pet.modelo_banda)
    mod = dm.ModeloMJ(timestep=pet.timestep, gravedad=pet.gravedad,
                      colisiones_maquina=pet.colisiones_maquina)
    padres_estaticos = {todas[n]["parent"] for n in cls.orden if cls.padre_cuerpo[n] is None} - {None}
    sostenes: set[str] = set()   # piezas estáticas con cuerpo propio (padres de junta)
    for fid in sorted(cls.estaticas):
        verts = hull_vertices(scene[fid].shape)
        if len(verts) < 4:
            continue
        g = dm.GeomMJ("mesh", dm.nombre_mj("e", fid), vertices=[tuple(c * MM for c in v) for v in verts])
        propio = fid in padres_estaticos
        if propio:
            sostenes.add(fid)
        mod.estaticos.append(dm.EstaticoMJ(fid, [g], dm.nombre_mj("s", fid) if propio else None))

    cuerpo_mj = {n: dm.nombre_mj("b", n) for n in cls.orden}
    radio_por_junta, inercia_por_junta = {}, {}
    for n in cls.orden:
        j = todas[n]
        piezas = cls.cuerpos[n]
        pms = [geometria_movil(scene[p], j) for p in piezas]
        masa, com, inercia = combinar_inercia(pms)
        giro_hijo = pms[0].giro
        if j["type"] in GIRATORIAS and giro_hijo is not None:
            radio_por_junta[n] = giro_hijo["radio"] * MM
        op = pet.juntas.get(n)
        origen = np.asarray(j["origin"], float) if j["type"] != "prismatica" else com
        eje = np.asarray(j["axis"], float) / np.linalg.norm(j["axis"])
        if j["type"] == "giratoria":
            rango = (math.radians(j["lower"]), math.radians(j["upper"]))
        elif j["type"] == "prismatica":
            rango = (j["lower"] * MM, j["upper"] * MM)
        else:
            rango = None
        inercia_por_junta[n] = (inercia_eje(masa, com, inercia, origen, eje) if j["type"] != "prismatica"
                                else masa) + (op.armadura if op else 0.0)
        im = inercia * 1e-6
        geoms = [g for p, pm in zip(piezas, pms) for g in _geoms_pieza(p, pm)]
        mod.cuerpos.append(dm.CuerpoMJ(
            nombre=cuerpo_mj[n], junta=dm.nombre_mj("j", n),
            tipo="slide" if j["type"] == "prismatica" else "hinge",
            padre=cuerpo_mj[cls.padre_cuerpo[n]] if cls.padre_cuerpo[n] else None,
            origen=tuple(origen * MM), eje=tuple(eje), rango=rango, masa=masa, com=tuple(com * MM),
            inercia=(im[0, 0], im[1, 1], im[2, 2], im[0, 1], im[0, 2], im[1, 2]), geoms=geoms,
            amortiguamiento=op.amortiguamiento if op else 0.0, friccion=op.friccion if op else 0.0,
            armadura=op.armadura if op else 0.0,
        ))
        padre = j["parent"]
        if cls.padre_cuerpo[n]:
            mod.excluir.append((cuerpo_mj[cls.padre_cuerpo[n]], cuerpo_mj[n]))
        elif padre in sostenes:
            mod.excluir.append((dm.nombre_mj("s", padre), cuerpo_mj[n]))
        snap.cuerpos.append({"name": cuerpo_mj[n], "junta": n, "tipo": j["type"], "piezas": piezas,
                             "origen_mm": [round(float(c), 3) for c in origen],
                             "eje": [round(float(c), 6) for c in eje], "masa_kg": round(masa, 4),
                             "inercia_eje_kgm2": round(inercia_por_junta[n], 6)})
        snap.juntas[n] = {"mj": dm.nombre_mj("j", n), "tipo": j["type"], "rango": rango}
        for p in piezas:
            snap.piezas.append({"name": cuerpo_mj[n], "id": p, "nombre": getattr(scene[p], "name", p),
                                "com": [round(float(c), 3) for c in origen]})

    bandas_por_junta = {}
    for k, (pieza, junta, radio, direccion, mu, mu_cama) in enumerate(bandas_req):
        if junta not in cls.cuerpos:
            avisos.append(f"La banda '{pieza}' no se simula: su junta motriz '{junta}' quedó fuera")
            continue
        cola = None
        cmd = pieza[: -len("_banda")] if pieza.endswith("_banda") else None
        tc = escena.get(f"{cmd}_tambor_cola") if cmd else None
        if tc is not None and (getattr(tc, "anchors", None) or {}).get("eje_cola"):
            cola = tc.anchors["eje_cola"]["origin"]
        b = superficie_banda(scene[pieza], todas[junta], radio, direccion, mu, mu_cama,
                             dm.nombre_mj("banda", k), cola=cola)
        mod.superficies.append(dm.GeomMJ("box", b.geom, pos=b.centro, medio=b.medio,
                                         xyaxes=b.d + b.a, extra='priority="1" condim="1"'))
        snap.bandas.append(b)
        bandas_por_junta[junta] = b
        cuerpo = next(c for c in mod.cuerpos if c.nombre == cuerpo_mj[junta])
        cuerpo.armadura += b.masa_banda * b.radio ** 2   # el lazo gira con el tambor
        inercia_por_junta[junta] += b.masa_banda * b.radio ** 2
        txt = (f"La banda '{pieza}' avanza hacia {b.avanza} con giro positivo de '{junta}' "
               f"(r = {b.radio / MM:.1f} mm; lazo de {b.masa_banda:.1f} kg, PVC salvo set_material)")
        avisos.append(txt + ("" if b.signo is None else
                             f"; direccion_transporte pide giro {'positivo' if b.signo > 0 else 'negativo'}"))

    snap.motores = resolver_motores(pet.motores, todas, set(cls.cuerpos), bandas_por_junta,
                                    radio_por_junta, inercia_por_junta, pet.timestep,
                                    {n: "su cuerpo no está sujeto" for n in todas if n not in cls.cuerpos})
    por_nombre = {c.nombre: c for c in mod.cuerpos}
    for mot in snap.motores:
        cuerpo = por_nombre[cuerpo_mj[mot.junta]]
        cuerpo.armadura += mot.armadura
        inercia_por_junta[mot.junta] += mot.armadura
        falta = inercia_minima(mot, pet.timestep) - inercia_por_junta[mot.junta]
        if falta > 0:
            cuerpo.armadura += falta
            inercia_por_junta[mot.junta] += falta
            avisos.append(
                f"Motor de '{mot.junta}': se suman {falta:.4g} de inercia (armadura) para que su "
                "tope de par no oscile a este timestep; da la inercia real (placa "
                "'inercia_rotor_kgm2' o juntas.armadura) o baja 'timestep'"
            )
        mod.actuadores.append(dm.ActuadorMJ(mot.nombre, dm.nombre_mj("j", mot.junta),
                                            "velocity" if mot.modo == "velocidad" else "motor",
                                            kv=mot.kv, fuerza_max=mot.fuerza_max))
        if mot.info.get("inferido"):
            avisos.append(f"Motor de '{mot.junta}': {mot.info['sentido']}")

    for c in snap.cuerpos:   # lazo de banda, rotor reflejado y mínimos: lo que suma al eje
        c["armadura_kgm2"] = round(por_nombre[c["name"]].armadura, 6)
    n_inst = 0
    for p in pet.productos:
        tiempos = instancias_producto(p, pet.duracion_s)
        for k, t0 in enumerate(tiempos):
            nombre = dm.nombre_mj("p", p.nombre if len(tiempos) == 1 else f"{p.nombre}_{k}")
            espera = t0 > 1e-12
            pos = np.asarray(p.posicion_mm, float) * MM
            estacion = (_ESTACION[0] + 5.0 * n_inst, _ESTACION[1], _ESTACION[2])
            n_inst += 1
            quat = _cuaternion(p.rotacion_deg)
            mod.productos.append(dm.ProductoMJ(
                nombre=nombre, medio=tuple(c / 2 * MM for c in p.dims_mm), masa=p.masa_kg,
                pos=estacion if espera else tuple(pos), friccion=p.friccion,
                quat=(1.0, 0.0, 0.0, 0.0) if espera else quat,
            ))
            w, dd, h = p.dims_mm
            snap.productos.append({
                "name": nombre, "producto": p.nombre, "w": w, "d": dd, "h": h,
                "x": p.posicion_mm[0], "y": p.posicion_mm[1], "z": p.posicion_mm[2],
                "rotacion_deg": list(p.rotacion_deg), "mass": p.masa_kg, "aparece_s": round(t0, 6),
                "vel_m_s": [c * MM for c in p.velocidad_mm_s], "estacion": estacion, "quat": quat,
            })
    if n_inst > MAX_PRODUCTOS:
        raise PhysicsError(f"{n_inst} productos: el máximo es {MAX_PRODUCTOS} (sube 'cada_s' o baja "
                           "'cantidad')")
    nombres = [p.nombre for p in mod.productos]
    if len(set(nombres)) != len(nombres):
        raise PhysicsError("dos productos quedan con el mismo nombre (sólo letras, números y _ "
                           f"cuentan): {sorted({n for n in nombres if nombres.count(n) > 1})}")
    snap.sensores = [SensorDatos(s.nombre, tuple(c * MM for c in s.origen), s.direccion,
                                 s.alcance_mm * MM) for s in pet.sensores]
    snap.avisos = avisos
    if not mod.cuerpos and not mod.productos:
        snap.early = {"frames": [], "piezas": [], "productos": [], "cuerpos": [], "juntas": {},
                      "sensores": {}, "resumen": {"duracion_s": 0.0}, "avisos": avisos,
                      "mensaje": "Nada que simular: no hay juntas móviles sujetas ni productos."}
        return snap
    snap.xml = dm.to_mjcf(mod)
    return snap


def _ids(mujoco, m, tipo, nombres):
    return [mujoco.mj_name2id(m, tipo, n) for n in nombres]


def simulate_dynamics(snap: DynamicsSnapshot) -> dict:
    """FASE MuJoCo (bajo PHYSICS_LOCK): integra el snapshot y arma la salida D9. No toca OCCT."""
    if snap.early is not None:
        return snap.early
    mujoco = _require_mujoco()
    try:
        m = mujoco.MjModel.from_xml_string(snap.xml)
    except Exception as exc:  # noqa: BLE001
        raise PhysicsError(f"No se pudo construir el mundo dinámico: {exc}") from exc
    d = mujoco.MjData(m)
    B = mujoco.mjtObj.mjOBJ_BODY
    cuerpos = [c["name"] for c in snap.cuerpos]
    bid_cuerpo = dict(zip(cuerpos, _ids(mujoco, m, B, cuerpos)))
    prods = snap.productos
    bid_prod = _ids(mujoco, m, B, [p["name"] for p in prods])
    qadr = [int(m.jnt_qposadr[m.body_jntadr[b]]) for b in bid_prod]
    vadr = [int(m.jnt_dofadr[m.body_jntadr[b]]) for b in bid_prod]
    juntas = {n: (int(m.jnt_qposadr[i]), int(m.jnt_dofadr[i]))
              for n, i in ((n, mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, j["mj"]))
                           for n, j in snap.juntas.items())}
    activo = [p["aparece_s"] <= 1e-12 for p in prods]
    for k, p in enumerate(prods):
        if activo[k]:
            d.qvel[vadr[k]: vadr[k] + 3] = p["vel_m_s"]

    motores = ControlMotores(mujoco, m, snap.motores)
    arrastre = (ArrastreBanda(mujoco, m, d, snap.bandas, [p["name"] for p in prods],
                              snap.modelo_banda, {n: v[1] for n, v in juntas.items()}, snap.gravedad,
                              snap.timestep * snap.nstep)
                if snap.bandas else None)
    nombre_cuerpo = {b: n for n, b in bid_cuerpo.items()}
    nombre_cuerpo.update({b: p["name"] for b, p in zip(bid_prod, prods)})
    fotos = Fotoceldas(mujoco, m, snap.sensores, nombre_cuerpo) if snap.sensores else None

    giro = {n: j["tipo"] != "prismatica" for n, j in snap.juntas.items()}
    trazas = {n: {"t": [], "q": [], "qd": [], "par": []} for n in snap.juntas}
    en_limite: dict[str, dict] = {}
    frames: list[dict] = []

    def q_apolo(n):
        qa, da = juntas[n]
        if giro[n]:
            return math.degrees(d.qpos[qa]), d.qvel[da] * 60.0 / (2 * math.pi)
        return d.qpos[qa] / MM, d.qvel[da] / MM

    def muestra(t):
        poses = {c: _pose_matrix(d.xpos[b], d.xquat[b]) for c, b in bid_cuerpo.items()}
        for k, b in enumerate(bid_prod):
            if activo[k]:
                poses[prods[k]["name"]] = _pose_matrix(d.xpos[b], d.xquat[b])
        frames.append({"t": round(t, 4), "poses": poses})
        for n in snap.juntas:
            q, qd = q_apolo(n)
            tr = trazas[n]
            tr["t"].append(round(t, 4))
            tr["q"].append(round(float(q), 4))
            tr["qd"].append(round(float(qd), 4))
            tr["par"].append(round(float(d.qfrc_actuator[juntas[n][1]]), 4))
            rango = snap.juntas[n]["rango"]
            if rango and n not in en_limite:
                lo, hi = ((math.degrees(rango[0]), math.degrees(rango[1])) if giro[n]
                          else (rango[0] / MM, rango[1] / MM))
                tol = _LIMITE_TOL[0 if giro[n] else 1]
                if q <= lo + tol or q >= hi - tol:
                    en_limite[n] = {"junta": n, "limite": round(lo if q <= lo + tol else hi, 3),
                                    "t": round(t, 4)}
        if fotos:
            fotos.muestrear(t)

    # los que esperan su hora quedan estacionados lejos (sin colisión ni salida): índices
    # vectorizados, rehechos sólo cuando entra un producto
    pendientes = sorted((k for k in range(len(prods)) if not activo[k]),
                        key=lambda k: prods[k]["aparece_s"])
    estacion: dict = {}

    def rehacer_estacion():
        ks = pendientes
        estacion["q"] = np.array([qadr[k] + i for k in ks for i in range(7)], dtype=int)
        estacion["qv"] = np.array([c for k in ks for c in (*prods[k]["estacion"], 1.0, 0.0, 0.0, 0.0)])
        estacion["v"] = np.array([vadr[k] + i for k in ks for i in range(6)], dtype=int)

    def estacionar():
        if pendientes:
            d.qpos[estacion["q"]] = estacion["qv"]
            d.qvel[estacion["v"]] = 0.0

    rehacer_estacion()
    mujoco.mj_forward(m, d)
    dt_int = snap.timestep * snap.nstep
    n_int = max(1, int(round(snap.duracion_s / dt_int)))
    paso_frame = 1.0 / snap.fps
    prox = 0.0
    if fotos:
        fotos.medir(d, 0.0)
    muestra(0.0)
    prox += paso_frame
    t0 = time.perf_counter()
    for _ in range(n_int):
        t = d.time
        if pendientes and prods[pendientes[0]]["aparece_s"] <= t + 1e-9:
            while pendientes and prods[pendientes[0]]["aparece_s"] <= t + 1e-9:
                k = pendientes.pop(0)
                p = prods[k]
                activo[k] = True
                d.qpos[qadr[k]: qadr[k] + 3] = (p["x"] * MM, p["y"] * MM, p["z"] * MM)
                d.qpos[qadr[k] + 3: qadr[k] + 7] = p["quat"]
                d.qvel[vadr[k]: vadr[k] + 6] = (*p["vel_m_s"], 0.0, 0.0, 0.0)
            rehacer_estacion()
        estacionar()
        motores.aplicar(d, t)
        if arrastre:
            arrastre.aplicar()
        mujoco.mj_step(m, d, nstep=snap.nstep)
        # MuJoCo REINICIA el estado ante una aceleración inválida: se mira su contador
        if d.warning[mujoco.mjtWarning.mjWARN_BADQACC].number or not np.all(np.isfinite(d.qacc)):
            raise PhysicsError(f"La simulación divergió cerca de t = {t:.3f} s: baja 'timestep' o "
                               "revisa productos que nacen dentro de la máquina o solapados")
        if fotos:
            fotos.medir(d, d.time)
        if d.time >= prox - 1e-9:
            muestra(d.time)
            while prox <= d.time + 1e-9:
                prox += paso_frame
    pared = time.perf_counter() - t0
    if frames[-1]["t"] < round(d.time, 4):
        muestra(d.time)
    return _salida(snap, d, frames, trazas, en_limite, fotos, arrastre, juntas, giro, activo,
                   bid_prod, vadr, pared)


def _salida(snap, d, frames, trazas, en_limite, fotos, arrastre, juntas, giro, activo, bid_prod,
            vadr, pared) -> dict:
    prods = snap.productos
    res_prod, caidos = {}, []
    for k, p in enumerate(prods):
        if not activo[k]:
            continue
        pos = [round(float(c) / MM, 1) for c in d.xpos[bid_prod[k]]]
        vel = [round(float(c) / MM, 2) for c in d.qvel[vadr[k]: vadr[k] + 3]]
        medio = max(p["w"], p["d"], p["h"]) / 2
        cayo = pos[2] < medio + 10.0 and p["z"] > medio + 60.0
        res_prod[p["name"]] = {"posicion_final_mm": pos, "velocidad_final_mm_s": vel, "cayo": cayo}
        if cayo:
            caidos.append(p["name"])
    res_juntas = {}
    for n in juntas:
        tr = trazas[n]
        res_juntas[n] = {"q_final": tr["q"][-1], ("velocidad_final_rpm" if giro[n] else
                                                  "velocidad_final_mm_s"): tr["qd"][-1],
                         "par_final": tr["par"][-1]}
    res_bandas = []
    for k, b in enumerate(snap.bandas):
        vb = arrastre.v_banda(k) if arrastre else 0.0
        hacia = eje_texto(np.asarray(b.e) * (1 if vb >= 0 else -1)) if abs(vb) > 1e-4 else "detenida"
        res_bandas.append({"pieza": b.pieza, "junta": b.junta, "radio_mm": round(b.radio / MM, 2),
                           "avanza_con_giro_positivo": b.avanza, "avanza_hacia": hacia,
                           "v_final_m_s": round(abs(vb), 5)})
    unidades = {n: ({"q": "grados", "qd": "rpm", "par": "N·m"} if giro[n]
                    else {"q": "mm", "qd": "mm/s", "par": "N"}) for n in juntas}
    return {
        "frames": frames,
        "piezas": snap.piezas,
        "cuerpos": snap.cuerpos,
        "productos": [{c: v for c, v in p.items() if c not in ("vel_m_s", "estacion", "quat")}
                      for p in prods],
        "juntas": {n: {**trazas[n], "unidades": unidades[n], "tipo": snap.juntas[n]["tipo"]}
                   for n in juntas},
        "sensores": fotos.salida() if fotos else {},
        "motores": [{"junta": mo.junta, "modo": mo.modo, "consigna": round(mo.consigna, 6),
                     "kv": round(mo.kv, 4), "tope": mo.fuerza_max, **mo.info} for mo in snap.motores],
        "resumen": {
            "duracion_s": round(float(d.time), 4), "timestep_s": snap.timestep,
            "intercambio_s": snap.timestep * snap.nstep, "fps": snap.fps,
            "t_pared_s": round(pared, 3),
            "factor_tiempo_real": round(float(d.time) / pared, 2) if pared > 0 else None,
            "juntas": res_juntas, "bandas": res_bandas, "productos": res_prod,
            "productos_caidos": caidos, "juntas_en_limite": list(en_limite.values()),
        },
        "avisos": snap.avisos,
    }
