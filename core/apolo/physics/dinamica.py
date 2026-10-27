"""Simulación dinámica en lote: la máquina se mueve de verdad (V8.2).

Dos fases, como `gravity_test` (V6.2c):
- `prepare_dynamics` (bajo `STATE_LOCK`): todo el trabajo OCCT —sujeción, cuerpos de junta,
  cascos, cápsulas, inercias, la superficie de la banda— horneado en un `DynamicsSnapshot` de
  datos puros con el MJCF listo.
- `simulate_dynamics` (bajo `PHYSICS_LOCK`): MuJoCo sobre esos datos. Física a `timestep`
  (1 ms) e intercambio cada `nstep` pasos (2): en cada intercambio se escriben consignas,
  fuerzas de banda y se leen los sensores; `mj_step(nstep)` retiene todo entre medias. El
  bucle es el `Integrador` de `dinamica_integrador.py` (sin OCCT: la co-simulación de V8.3 lo
  avanza de a un intercambio desde su worker); el snapshot, `dinamica_datos.py`.

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

import numpy as np

from apolo.physics import dinamica_modelo as dm
from apolo.physics.banda import detectar_bandas, superficie_banda
from apolo.physics.dinamica_cuerpos import (
    GIRATORIAS,
    clasificar,
    combinar_inercia,
    geometria_movil,
    inercia_eje,
    masas_de_ficha,
)
from apolo.physics.dinamica_datos import DynamicsSnapshot
from apolo.physics.dinamica_integrador import Integrador
from apolo.physics.dinamica_motores import inercia_minima, resolver_motores
from apolo.physics.dinamica_peticion import (
    MAX_PRODUCTOS,
    instancias_producto,
    parse_peticion,
    posicion_inicial,
)
from apolo.physics.hull import cascos
from apolo.physics.sensores import SensorDatos
from apolo.physics.sim import MM, PhysicsError

_ESTACION = (1000.0, 1000.0, 500.0)  # m: donde esperan los productos que aún no entran


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
    return _geoms_cascos(nombre, pm.cascos if pm.cascos is not None else [pm.vertices])


def _geoms_cascos(nombre: str, cascos_mm: list) -> list:
    """Una malla convexa por SÓLIDO (`hull.cascos`, V8.9 F7b): la primera con el nombre de la
    pieza (con un sólido, el MJCF de siempre) y las demás con «__k»."""
    out = []
    for k, verts in enumerate(cascos_mm):
        if len(verts) < 4:
            continue
        out.append(dm.GeomMJ("mesh", nombre if not out else f"{nombre}__{k}",
                             vertices=[tuple(c * MM for c in v) for v in verts]))
    return out


def _iniciales(pet, juntas: dict, cls) -> dict:
    """{junta: q0 en m | rad} de las juntas con `inicial` (plan motor-a-eje-lineal F4). Una junta
    que no existe o que quedó fuera de la simulación es error: arrancaría en la pose de diseño
    sin decirlo (la FK ignora los nombres desconocidos; aquí no)."""
    out = {}
    moviles = [n for n, j in juntas.items() if j.get("type") != "fija"]
    for n, op in pet.juntas.items():
        if op.inicial is None:
            continue
        q0 = posicion_inicial(n, op.inicial, juntas.get(n), moviles)
        if n not in cls.cuerpos:
            raise PhysicsError(f"juntas.{n}.inicial: '{n}' queda fuera de la simulación "
                               f"({cls.fuera.get(juntas[n].get('child'), 'su cuerpo no está sujeto')}): "
                               "no hay nada que poner en esa posición")
        out[n] = q0
    return out


def prepare_dynamics(scene, joints, fasteners, grounds, request: dict | None = None, *,
                     mates=None, duracion_max_s: float | None = None,
                     sujetas=None) -> DynamicsSnapshot:
    """FASE OCCT (bajo STATE_LOCK). `request` es la petición D3–D8 (ver `dinamica_peticion`).
    `duracion_max_s`: el tope de quien corre (la co-simulación pasa el de su escenario; None, el
    de la dinámica suelta). `sujetas`: la tornillería de las uniones declaradas
    (`dinamica_cuerpos.clasificar`). Lanza `PhysicsError` con un mensaje accionable si algo no sirve."""
    pet = parse_peticion(request, duracion_max_s=duracion_max_s)
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
                     quitar={b[0] for b in bandas_req}, sujetas=sujetas)
    avisos += cls.avisos
    fuera = sorted(cls.fuera.items())
    for fid, motivo in fuera[:20]:
        avisos.append(f"'{fid}' queda FUERA de la simulación: {motivo}")
    if len(fuera) > 20:
        avisos.append(f"… y {len(fuera) - 20} piezas más fuera de la simulación")

    snap = DynamicsSnapshot(xml=None, duracion_s=pet.duracion_s, timestep=pet.timestep,
                            nstep=pet.nstep, fps=pet.fps, gravedad=pet.gravedad,
                            modelo_banda=pet.modelo_banda,
                            sumideros=[(tuple(c * MM for c in z.punto_mm), tuple(z.normal))
                                       for z in pet.sumideros])
    if pet.flujo is not None:  # balance-de-producto D3: cada salida con su nombre
        snap.flujo = {**pet.flujo, "sumideros": [z.nombre or f"sumidero_{k + 1}"
                                                 for k, z in enumerate(pet.sumideros)]}
    mod = dm.ModeloMJ(timestep=pet.timestep, gravedad=pet.gravedad,
                      colisiones_maquina=pet.colisiones_maquina)
    padres_estaticos = {todas[n]["parent"] for n in cls.orden if cls.padre_cuerpo[n] is None} - {None}
    sostenes: set[str] = set()   # piezas estáticas con cuerpo propio (padres de junta)
    for fid in sorted(cls.estaticas):
        geoms = _geoms_cascos(dm.nombre_mj("e", fid), cascos(scene[fid].shape))
        if not geoms:
            continue
        propio = fid in padres_estaticos
        if propio:
            sostenes.add(fid)
        mod.estaticos.append(dm.EstaticoMJ(fid, geoms, dm.nombre_mj("s", fid) if propio else None))

    cuerpo_mj = {n: dm.nombre_mj("b", n) for n in cls.orden}
    radio_por_junta, inercia_por_junta = {}, {}
    masas = masas_de_ficha(scene) if cls.orden else {}
    for n in cls.orden:
        j = todas[n]
        piezas = cls.cuerpos[n]
        pms = [geometria_movil(scene[p], j, masas.get(p)) for p in piezas]
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

    snap.inicial = _iniciales(pet, todas, cls)
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
                                            kv=mot.kv, fuerza_max=mot.fuerza_max, gear=mot.gear))
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


def simulate_dynamics(snap: DynamicsSnapshot) -> dict:
    """FASE MuJoCo (bajo PHYSICS_LOCK): integra el snapshot y arma la salida D9. No toca OCCT.
    Es el bucle cerrado del `Integrador` (V8.3 F4 lo parte en intercambios sin cambiar esto)."""
    if snap.early is not None:
        return snap.early
    return Integrador(snap).correr()
