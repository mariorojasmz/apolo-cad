"""Aserciones `verify` (V6.5) sobre un documento: el lote de `/api/verify`, el CONTRATO
`expect` de los lotes (V6.5b, `$k` → feature_ids) y las poses de REPOSO de la puerta de
entrega (V6.9). El llamador sostiene STATE_LOCK e inyecta `expand` (la API resuelve los
nombres de grupo con `_expand_ids`). Reglas: `services/CLAUDE.md` § Aserciones."""

from __future__ import annotations

from .lookup import suggest_suffix


def verify_checks(doc, scene: dict, checks: list[dict], *, expand,
                  extra_exclude_pairs: set | None = None,
                  extra_exclude_ids: set | None = None) -> list[dict]:
    """Evalúa un lote de ASERCIONES `verify` (V6.5) sobre `scene` con la resolución de
    grupos (`expand`) y la interferencia acotada + exclusiones normales (hardware,
    parejas de junta, mismo super-comando). Fuente ÚNICA compartida por el endpoint
    /api/verify y el CONTRATO `expect` de los lotes (V6.5b). Llamar bajo STATE_LOCK.
    V6.8-C: `joint_values` por aserción (distancia/sin_interferencia) evalúa EN POSE —
    la pose usa `doc` (en ambos call sites `scene` ES doc.scene, post-regenerate).
    `extra_exclude_pairs`/`extra_exclude_ids` (V6.9): exclusiones ADICIONALES de
    interferencia que la puerta de entrega inyecta (pares con fasten declarado,
    tornillería a-medida) — None = semántica de contratos intacta."""
    from apolo.library import interference_report
    from apolo.library.checks import (
        hardware_ids, interpenetration_report, joint_pairs, same_command_pairs,
    )
    from apolo.library.verify import run_verify

    jpairs = joint_pairs(doc)
    excl_pairs = jpairs | same_command_pairs(doc) | (extra_exclude_pairs or set())
    excl_ids = hardware_ids(doc) | (extra_exclude_ids or set())

    def interference_fn(focus, shapes_override=None):
        focus_ids = expand(focus) if focus else None
        rep = interference_report(  # reporte COMPLETO: run_verify propaga `truncado`
            scene, focus=focus_ids, shapes_override=shapes_override,
            exclude_pairs=excl_pairs, exclude_ids=excl_ids,
        )
        if shapes_override is not None:  # pares con junta: interpenetración vs diseño,
            rep["interferencias"] = rep["interferencias"] + interpenetration_report(
                scene, shapes_override, jpairs  # mismo camino que /api/checks en pose
            )
        return rep

    _pose_cache: dict = {}

    def pose_fn(joint_values: dict):
        """Override posado de una aserción (V6.8-C). Valida los NOMBRES de junta (un
        typo jamás da verde en silencio) y cachea por valores: N aserciones sobre la
        misma pose posan UNA vez. Todo-cero = pose de diseño (sin override)."""
        desconocidas = sorted(set(map(str, joint_values)) - set(doc.joints))
        if desconocidas:
            validas = ", ".join(sorted(doc.joints)) or "ninguna declarada"
            raise ValueError(
                f"juntas desconocidas en joint_values: {', '.join(desconocidas)} "
                f"(válidas: {validas})"
            )
        vals = {str(k): float(v) for k, v in joint_values.items()}
        if not any(v != 0 for v in vals.values()):
            return None
        key = tuple(sorted(vals.items()))
        if key not in _pose_cache:
            from apolo.robotics.pose import posed_shapes

            _pose_cache[key] = posed_shapes(doc, vals)[0]
        return _pose_cache[key]

    return run_verify(
        scene, checks, expand=lambda v: expand(v) or [],
        interference_fn=interference_fn, suggest=lambda m: suggest_suffix(doc, m),
        pose_fn=pose_fn,
    )


def contract_verify(doc, expect: list[dict], *, expand):
    """Callback de CONTRATO para execute_many/edit_many (V6.5b, frente A): resuelve los `$k`
    de las aserciones contra los FEATURE_IDS reales del comando k-ésimo (V6.5c: un comando
    MULTI-sólido —join_bolted, create_*— expande a todos sus fids en campos de lista; en un
    campo de UN id exige que el comando haya creado UN solo sólido o falla con error
    accionable, nunca elige uno en silencio) y las evalúa con `verify_checks`. Corre DENTRO
    del lote (tras el regenerate) → si falla, el lote se revierte por completo. None si no
    hay aserciones (comportamiento byte-idéntico)."""
    if not expect:
        return None
    from apolo.batch import resolve_refs
    from apolo.commands.registry import CommandError

    _SINGULAR = ("id", "a", "b")  # campos de UN solo sólido en las aserciones

    def cb(scene: dict, created: list[str]) -> list[dict]:
        def fids_of(cmd_id: str) -> list[str]:
            return [fid for fid, f in scene.items()
                    if getattr(f, "command_id", None) == cmd_id]

        def resolve(tok, *, plural: bool):
            if not (isinstance(tok, str) and tok.startswith("$") and tok[1:].isdigit()):
                return tok
            cmd_id = resolve_refs(tok, created)  # valida rango (1-indexado) → command_id
            fids = fids_of(cmd_id)
            if not fids:
                raise CommandError(
                    f"La aserción usa '{tok}' pero el comando {cmd_id} no creó sólidos "
                    "(¿set_variable/fasten?) — aserta sobre una acción que cree geometría."
                )
            if plural:
                return fids
            if len(fids) == 1:
                return fids[0]
            listado = ", ".join(fids[:3]) + ("…" if len(fids) > 3 else "")
            raise CommandError(
                f"La aserción usa '{tok}' en un campo de UN sólido, pero el comando {cmd_id} "
                f"creó {len(fids)} ({listado}) — usa `ids` (acepta la referencia y se expande) "
                "o un fid concreto."
            )

        def resolve_spec(spec: dict) -> dict:
            out = {}
            for k, v in spec.items():
                if k == "ids" and isinstance(v, list):
                    acc: list = []
                    for tok in v:
                        r = resolve(tok, plural=True)
                        acc.extend(r) if isinstance(r, list) else acc.append(r)
                    out[k] = acc
                elif k in _SINGULAR:
                    out[k] = resolve(v, plural=False)
                else:
                    out[k] = v
            return out

        return verify_checks(doc, scene, [resolve_spec(s) for s in expect], expand=expand)

    return cb


def delivery_poses(doc, extra_pairs: set | None = None,
                   extra_ids: set | None = None, *, expand) -> list[dict] | None:
    """Poses de REPOSO de los estudios de movimiento declarados, evaluadas EN POSE
    (camino V6.8-C: `sin_interferencia` posada + interpenetración, caché por pose dentro
    del lote de verify_checks). REPOSO = donde el mecanismo DESCANSA: fotogramas
    EXTREMOS (primero/último) + DWELLS (mismos values en ≥2 fotogramas consecutivos);
    el TRÁNSITO interpolado (la espiga saltando dientes de la cremallera) no es una
    pose de entrega — se valida con scan_motion. Contacto de ASIENTO ≤ EXCESS_TOL_MM3
    (la pose rígida del FK no modela la complianza del apoyo: 2 mm³ de la barra en su
    muesca no son una colisión) se tolera y se DECLARA (`contactos_tolerados`).
    None = no hay estudios (el chequeo «no aplica» — jamás cuenta verde). Un estudio
    malformado (formato viejo sin `values`, valores no numéricos) produce {estudio,
    error}: la pose queda SIN verificar y la puerta lo DECLARA. Llamar bajo STATE_LOCK."""
    from apolo.library.checks import EXCESS_TOL_MM3

    if not doc.motion:
        return None
    metas: list[dict] = []
    errores: list[dict] = []
    vistos: set = set()
    for nombre, kfs in sorted(doc.motion.items()):
        cuadros: list[tuple] = []  # (t, vals) parseados del estudio
        for kf in kfs or []:
            values = kf.get("values") if isinstance(kf, dict) else None
            if not isinstance(values, dict):
                errores.append({"estudio": nombre, "error": "fotograma sin 'values' "
                                "(formato viejo — re-guarda el estudio con set_motion)"})
                cuadros = []
                break
            try:
                vals = {str(k): float(v) for k, v in values.items()}
            except (TypeError, ValueError):
                errores.append({"estudio": nombre,
                                "error": f"valores no numéricos en t={kf.get('t')}"})
                cuadros = []
                break
            cuadros.append((kf.get("t"), vals))
        if not cuadros:
            continue
        reposo = {0, len(cuadros) - 1}  # extremos: el estudio arranca y termina en reposo
        for i in range(len(cuadros) - 1):
            if cuadros[i][1] == cuadros[i + 1][1]:  # dwell = pose sostenida
                reposo.update((i, i + 1))
        for i in sorted(reposo):
            t, vals = cuadros[i]
            if not any(v != 0 for v in vals.values()):
                continue  # pose de diseño: la cubre el chequeo de interferencias
            key = tuple(sorted(vals.items()))
            if key in vistos:
                continue
            vistos.add(key)
            metas.append({"estudio": nombre, "t": t, "joint_values": vals})
    checks = [{"tipo": "sin_interferencia", "joint_values": m["joint_values"],
               "nombre": f"{m['estudio']}@t={m['t']}"} for m in metas]
    # MISMAS exclusiones que el chequeo de diseño de la puerta (fasten declarado +
    # tornillería): sin esto, un solape DECLARADO reaparecía como «colisión nueva»
    # en pose (asimetría cazada en el E2E del 38: banda↔travesaño, rodillo↔ménsula).
    resultados = (verify_checks(doc, doc.scene, checks, expand=expand,
                                extra_exclude_pairs=extra_pairs,
                                extra_exclude_ids=extra_ids) if checks else [])
    out: list[dict] = []
    for meta, res in zip(metas, resultados):
        if res.get("error"):
            out.append({**meta, "error": res["error"]})
            continue
        cols = res.get("colisiones") or []
        reales = [c for c in cols if c.get("volumen_mm3", 0) > EXCESS_TOL_MM3]
        entry = {**meta, "colisiones": reales}
        if len(cols) > len(reales):
            entry["contactos_tolerados"] = len(cols) - len(reales)
        out.append(entry)
    return out + errores
