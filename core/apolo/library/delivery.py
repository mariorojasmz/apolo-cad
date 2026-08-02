"""Puerta de ENTREGA (V6.9): el checklist de cierre como MECANISMO del sistema.

Origen: el test de generalización del camastro-v2 (proyecto 71) — un agente con el
decálogo en la memoria construyó 85 piezas sin un solo error de herramienta y aun
así ENTREGÓ cremalleras flotando en el aire con 0 anclajes declarados: verificó lo
que el prompt pedía por su letra y se saltó el resto. Un checklist en la memoria
del agente es DÉBIL; el que funciona es mecanismo (mismo patrón que los contratos
`expect` de V6.5b). Esta es la versión de FIN DE TRABAJO: una sola puerta de
salida que agrega los chequeos EXISTENTES en un semáforo accionable.

Agregador PURO estilo `verify.py`/`lints.py`: recibe RESULTADOS ya computados
(la capa API corre los motores y le pasa los datos), nunca un `Document`.
Regla de honestidad: un chequeo que no puede correr se declara en `no_aplica`,
JAMÁS cuenta como verde.
"""

from __future__ import annotations

VERDE, AMARILLO, ROJO = "VERDE", "AMARILLO", "ROJO"

# Umbral de sujeción (compartido con la alarma ambiental de la capa API): bajo esto
# —un croquis de 2-3 piezas— exigir anclajes sería ruido. Conservador a propósito:
# a 5 sólidos un proyecto ya es un ENSAMBLAJE y algo debe tocar tierra.
MIN_SOLIDOS_SUJECION = 5

# El texto de la alarma ambiental (retornos de mutación con 0 grounds): molesto a
# propósito, como la alarma del tren de aterrizaje — suena hasta que declares.
AVISO_SIN_ANCLAJES = (
    "0 anclajes declarados — nada tiene camino de carga a tierra. Declara la "
    "estructura (ground/fasten o declare_structure) y valida con delivery_check."
)

_MAX_PIEZAS = 12  # tope de nombres por regla; el conteo TOTAL siempre se declara


def _nombres(fids, nombre_de) -> list[str]:
    out = []
    for fid in list(fids)[:_MAX_PIEZAS]:
        nom = nombre_de(fid)
        out.append(f"{nom} ({fid})" if nom and nom != fid else str(fid))
    if len(fids) > _MAX_PIEZAS:
        out.append(f"… +{len(fids) - _MAX_PIEZAS} más")
    return out


def delivery_report(
    *,
    n_solidos: int,
    interferencias: list[dict],
    interferencias_truncado: bool = False,
    soundness: dict,
    tornilleria_flotante: list | tuple = (),
    lints: list[dict],
    integridad: list[str],
    suprimidos: list[dict],
    poses: list[dict] | None,
    gravedad: dict | None = None,
    nombre_de=None,
) -> dict:
    """Agrega los chequeos de cierre en un SEMÁFORO. Entradas (todas computadas por
    el llamador — aquí no corre ningún motor):
      - `interferencias`: entradas de `interference_report` en DISEÑO (con las
        exclusiones normales: hardware, parejas de junta, mismo super-comando);
        `interferencias_truncado` declara el recorte por MAX_PAIRS como aviso.
      - `soundness`: `soundness_report` del grafo DECLARADO (sin autodetect) —
        la puerta valida lo que el modelo DECLARA, no lo que el detector adivina;
        `tornilleria_flotante` = pernos/tuercas que el llamador FILTRÓ del floating
        (no son nodos estructurales: los representa su fasten) → aviso, no bloqueo.
      - `lints`: `predelivery_lints` (formato _check).
      - `integridad`/`suprimidos`: `check_integrity()` crudo + `regen_suppressed`.
      - `poses`: [{estudio, t, joint_values, colisiones | error, contactos_tolerados?}]
        — las poses de REPOSO de los estudios (extremos + dwells; el tránsito lo valida
        scan_motion) evaluadas EN POSE (camino V6.8-C), con los contactos de asiento
        ≤ tolerancia ya filtrados y CONTADOS por el llamador; None = no hay estudios
        declarados (no aplica).
      - `gravedad`: resultado de stability {fell, estables, settled} o None = no
        corrida (opt-in — MuJoCo es caro).
      - `nombre_de(fid) -> str`: nombre legible (inyectado; default identidad).
    Veredicto: ROJO si hay bloqueantes, AMARILLO si solo avisos, VERDE si nada.
    """
    nombre_de = nombre_de or (lambda fid: str(fid))
    bloqueantes: list[dict] = []
    avisos: list[dict] = []
    no_aplica: list[str] = []
    ok: list[str] = []

    # 1 · interferencias en pose de DISEÑO --------------------------------------
    if interferencias:
        piezas = []
        for c in interferencias:
            piezas.extend([c.get("a"), c.get("b")])
        peor = interferencias[0]  # interference_report ya ordena por volumen desc
        bloqueantes.append({
            "regla": "interferencias en diseño",
            "piezas": _nombres(sorted({p for p in piezas if p}), nombre_de),
            "detalle": f"{len(interferencias)} colisión(es); la peor: "
                       f"{peor.get('nombre_a')} ↔ {peor.get('nombre_b')} "
                       f"({peor.get('volumen_mm3')} mm³). Solo vale el contacto "
                       "INTENCIONAL — reposiciona o declara la unión que corresponda.",
        })
    else:
        ok.append("interferencias")
    if interferencias_truncado:  # sin caps silenciosos: el recorte jamás pasa por verde pleno
        avisos.append({
            "regla": "interferencias · reporte truncado", "piezas": [],
            "detalle": "el chequeo global recortó parejas candidatas (tope MAX_PAIRS) — "
                       "acota con check_interference(ids=...) por zonas para cubrir todo.",
        })

    # 2 · sujeción DECLARADA (soundness sin autodetect) -------------------------
    if not soundness.get("has_ground"):
        if n_solidos >= MIN_SOLIDOS_SUJECION:
            bloqueantes.append({
                "regla": "sujeción · sin anclajes",
                "piezas": [],
                "detalle": f"{n_solidos} sólidos y {AVISO_SIN_ANCLAJES}",
            })
        else:
            no_aplica.append(
                f"sujeción (proyecto de {n_solidos} sólido(s) sin anclajes — se "
                f"exige desde {MIN_SOLIDOS_SUJECION})"
            )
    elif soundness.get("floating"):
        flot = soundness["floating"]
        aisladas = set(soundness.get("isolated") or [])
        bloqueantes.append({
            "regla": "sujeción · piezas flotantes",
            "piezas": _nombres(flot, nombre_de),
            "detalle": f"{len(flot)} pieza(s) SIN camino de carga declarado a tierra"
                       + (f" ({len(aisladas)} sin ninguna unión)" if aisladas else "")
                       + " — caerían. Declara ground/fasten (o declare_structure) "
                       "o quítalas si son escombro.",
        })
    else:
        ok.append("sujeción declarada")
    if tornilleria_flotante:  # no bloquea (la representa su fasten) pero se DECLARA
        avisos.append({
            "regla": "sujeción · tornillería sin unión declarada",
            "piezas": _nombres(list(tornilleria_flotante), nombre_de),
            "detalle": f"{len(tornilleria_flotante)} perno(s)/tuerca(s) sin fasten en el "
                       "grafo declarado — normalmente los cubre su fasten/join_bolted; "
                       "revisa si falta declarar la unión que representan.",
        })

    # 3 · lints pre-entrega -----------------------------------------------------
    if lints:
        for lint in lints:
            avisos.append({
                "regla": lint.get("regla", "lint pre-entrega"),
                "piezas": [],
                "detalle": (lint.get("detalle", "") +
                            (f" → {lint['recomendacion']}" if lint.get("recomendacion") else "")),
            })
    else:
        ok.append("lints pre-entrega")

    # 4 · salud del documento ---------------------------------------------------
    issues = [i for i in integridad if not i.startswith("degradado")]
    degradados = [i for i in integridad if i.startswith("degradado")]
    if issues or suprimidos:
        detalle = []
        if issues:
            detalle.append(f"{len(issues)} violación(es) de integridad: "
                           + "; ".join(issues[:5]) + ("…" if len(issues) > 5 else ""))
        if suprimidos:
            listado = ", ".join(str(s.get("command_id", s)) for s in suprimidos[:5])
            detalle.append(f"{len(suprimidos)} comando(s) SUPRIMIDOS al cargar "
                           f"({listado}{'…' if len(suprimidos) > 5 else ''})")
        bloqueantes.append({
            "regla": "salud del documento", "piezas": [],
            "detalle": " · ".join(detalle) + " — repara antes de entregar.",
        })
    else:
        ok.append("salud del documento")
        if degradados:
            avisos.append({
                "regla": "salud · degradado", "piezas": [],
                "detalle": "; ".join(degradados[:5]) + ("…" if len(degradados) > 5 else ""),
            })

    # 5 · poses de los estudios declarados --------------------------------------
    if poses is None:
        no_aplica.append("poses (sin estudios de movimiento declarados)")
    else:
        con_colision = [p for p in poses if p.get("colisiones")]
        con_error = [p for p in poses if p.get("error")]
        for p in con_colision:
            cols = p["colisiones"]
            piezas = sorted({x for c in cols for x in (c.get("a"), c.get("b")) if x})
            bloqueantes.append({
                "regla": "colisión en pose declarada",
                "piezas": _nombres(piezas, nombre_de),
                "detalle": f"estudio '{p.get('estudio')}' t={p.get('t')} "
                           f"(joint_values={p.get('joint_values')}): "
                           f"{len(cols)} colisión(es) que en diseño no existen.",
            })
        for p in con_error:
            avisos.append({
                "regla": "pose no evaluable", "piezas": [],
                "detalle": f"estudio '{p.get('estudio')}': {p['error']} — la pose "
                           "quedó SIN verificar (no cuenta como verde).",
            })
        if poses and not con_colision and not con_error:
            tolerados = sum(p.get("contactos_tolerados", 0) for p in poses)
            ok.append(f"poses declaradas ({len(poses)})"
                      + (f" · contactos de asiento tolerados: {tolerados}" if tolerados else ""))
        elif not poses:
            no_aplica.append("poses (los estudios no declaran ninguna pose no-cero)")

    # 6 · gravedad (opt-in) -----------------------------------------------------
    if gravedad is None:
        no_aplica.append("gravedad (opt-in: con_gravedad=true — MuJoCo)")
    elif gravedad.get("fell"):
        caidas = gravedad["fell"]
        bloqueantes.append({
            "regla": "gravedad · piezas que caen",
            "piezas": _nombres([r["id"] for r in caidas], nombre_de),
            "detalle": f"{len(caidas)} pieza(s) caen en la simulación (la peor: "
                       f"{caidas[0].get('nombre')} {caidas[0].get('caida_mm')} mm).",
        })
    else:
        ok.append("gravedad")

    veredicto = ROJO if bloqueantes else (AMARILLO if avisos else VERDE)
    return {
        "veredicto": veredicto,
        "bloqueantes": bloqueantes,
        "avisos": avisos,
        "no_aplica": no_aplica,
        "resumen": {
            "n_solidos": n_solidos,
            "chequeos_ok": ok,
            "n_bloqueantes": len(bloqueantes),
            "n_avisos": len(avisos),
        },
    }
