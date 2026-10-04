"""Cadenas de cotas (stack-up, V7.3) de un documento: las DECLARADAS en
`Document.stackups` (nominales '=expr' y eslabones `{id, eje}` medidos del bbox VIVO) y las
AUTO del patrón de pernos, evaluadas con el motor puro `library/engineering/stackup.py`, más
las reglas que de ellas salen para la memoria de cálculo. El llamador sostiene STATE_LOCK.
Reglas: `services/CLAUDE.md` § Stack-up."""

from __future__ import annotations


def resolve_nominal(val, variables: dict) -> float:
    """Un nominal puede ser número o '=expr' (sigue a las variables del proyecto)."""
    from apolo.commands.expressions import eval_expression

    if isinstance(val, str) and val.strip().startswith("="):
        return float(eval_expression(val.strip()[1:], variables))
    return float(val)


def stackup_link_from_feature(doc, fid: str, eje: str, tol) -> dict | None:
    """Eslabón medido del BBOX VIVO de una pieza (la cadena se re-mide sola). El tol es
    el declarado, o el fit de la pieza (por nombre), o ISO 2768-m por defecto."""
    feat = doc.scene.get(fid)
    if feat is None:
        return None
    bb = feat.shape.bounding_box()
    span = {"x": bb.max.X - bb.min.X, "y": bb.max.Y - bb.min.Y,
            "z": bb.max.Z - bb.min.Z}.get(str(eje).lower())
    if span is None:
        return None
    return {"nombre": f"{feat.name} ({eje})", "nominal_mm": round(float(span), 4),
            "tol": tol or {"iso2768": "m"}}


def evaluate_stackups(doc, scope: str = "all") -> list[dict]:
    """Evalúa las cadenas DECLARADAS (`doc.stackups`, resolviendo nominales '=expr' y
    eslabones por id contra el bbox vivo) y, si scope incluye auto, las cadenas
    AUTO del patrón de pernos. Llamar bajo STATE_LOCK. Devuelve [{name, tipo, ...}].

    AISLAMIENTO POR CADENA (cierre de la auditoría V7.3): una cadena que no evalúa
    (tol desconocida, '=expr' roto, fit fuera de tabla) sale como entrada `{error}` —
    JAMÁS lanza, para que una cadena mala no oculte a las demás ni tumbe GET/memoria.
    Una cadena con piezas FALTANTES no se evalúa parcial (el cierre de una cadena
    incompleta no significa nada): entrada `{error}` con los ids que faltan."""
    from apolo.library.engineering.stackup import stack_up

    variables = dict(doc.variables_resolved)
    out: list[dict] = []
    if scope in ("all", "declared"):
        for name, spec in sorted(doc.stackups.items()):
            try:
                eslabones = []
                faltan = []
                for e in spec.get("eslabones", []):
                    if e.get("id"):
                        link = stackup_link_from_feature(doc, e["id"], e.get("eje", "x"), e.get("tol"))
                        if link is None:
                            faltan.append(e["id"])
                            continue
                        link["sentido"] = e.get("sentido", 1)
                        if e.get("nombre"):
                            link["nombre"] = e["nombre"]
                        eslabones.append(link)
                    else:
                        eslabones.append({
                            "nombre": e.get("nombre", "eslabón"),
                            "nominal_mm": resolve_nominal(e["nominal_mm"], variables),
                            "sentido": e.get("sentido", 1), "tol": e.get("tol") or {"pm": 0.0},
                        })
                if faltan:  # cadena INCOMPLETA → error honesto, nunca veredicto parcial
                    out.append({
                        "name": name, "tipo": "declarada", "faltan": faltan,
                        "error": f"piezas no encontradas: {', '.join(faltan)} — la cadena "
                                 "no se evalúa incompleta (re-declárala o repón las piezas)",
                    })
                    continue
                if not eslabones:
                    out.append({"name": name, "tipo": "declarada",
                                "error": "sin eslabones resolubles"})
                    continue
                rep = stack_up(eslabones, spec.get("requisito") or None)
                rep.update({"name": name, "tipo": "declarada"})
                out.append(rep)
            except Exception as exc:  # noqa: BLE001 — aislamiento por cadena
                out.append({"name": name, "tipo": "declarada", "error": str(exc)})
    if scope in ("all", "auto"):
        out.extend(auto_bolt_stackups(doc))
    return out


def auto_bolt_stackups(doc) -> list[dict]:
    """Cadenas AUTO del patrón de pernos (V7.3 C). Un `join_bolted` taladra AMBAS piezas
    a la vez → los barrenos quedan alineados POR CONSTRUCCIÓN (cadena cerrada, sin holgura
    de posición que verificar). Un perno DECLARADO a mano (fasten con `size`) une dos
    patrones taladrados por separado, pero Apolo NO conoce sus tolerancias de posición
    reales → se reporta la HOLGURA de paso disponible (Ø_paso−Ø_perno)/2 como dato
    INFORMATIVO (sin veredicto: fabricar la demanda sería inventar). Llamar bajo
    STATE_LOCK."""
    from apolo.library.engineering.bolts import clearance_hole_mm, nominal_diameter_mm

    cmd_type = {c["id"]: c.get("type") for c in doc.commands}
    out: list[dict] = []
    for name, f in sorted(doc.fasteners.items()):
        if f.get("kind") != "perno" or not f.get("size"):
            continue
        size = str(f["size"])
        # SOLO el comando join_bolted garantiza taladrado conjunto (V7.3 auditoría:
        # un fasten MANUAL que el usuario nombre «jb_x» NO debe heredar el veredicto)
        es_join = cmd_type.get(f.get("command_id")) == "join_bolted"
        if es_join:
            out.append({
                "name": f"pernos {name}", "tipo": "auto-perno",
                "cerrada_por_construccion": True, "ok_peor_caso": True,
                "detalle": f"{size}: barrenos taladrados a la vez en ambas piezas "
                           "(join_bolted) → alineados por construcción, sin holgura de posición.",
            })
            continue
        try:
            clear, d = clearance_hole_mm(size), nominal_diameter_mm(size)
        except KeyError as exc:  # size fuera de tabla: entrada informativa, NO desaparición
            out.append({"name": f"pernos {name}", "tipo": "auto-perno", "informativo": True,
                        "detalle": f"{size}: sin broca de paso tabulada ({exc}); sin dato."})
            continue
        holgura = round((clear - d) / 2.0, 4)
        out.append({
            "name": f"pernos {name}", "tipo": "auto-perno",
            "cerrada_por_construccion": False, "informativo": True,
            "holgura_mm": holgura,
            "detalle": f"{size}: holgura de paso {holgura:g} mm/lado disponible (broca "
                       f"Ø{clear:g}). Declara la tolerancia de posición de los patrones "
                       "(set_stackup) para verificar el ensamble.",
        })
    return out


def stackup_rules(doc) -> list[dict]:
    """Reglas de memoria (con `calc`) de las cadenas de cotas para `calc_report`. Vacío
    si no hay cadenas declaradas ni pernos → la sección no aparece. Llamar bajo STATE_LOCK."""
    from apolo.library.engineering.stackup import stackup_rule

    rules: list[dict] = []
    chains = evaluate_stackups(doc, "all")  # aislada por cadena: nunca lanza
    for c in chains:
        if c.get("error"):
            if c.get("tipo") == "declarada":
                # V7.3 auditoría: una cadena declarada que no evalúa (pieza borrada,
                # '=expr' roto) APARECE como aviso — patrón vigencia-FEA, nunca silencio.
                rules.append({
                    "regla": f"cadena de cotas · {c['name']}",
                    "estado": "aviso",
                    "detalle": f"La cadena declarada no se pudo evaluar: {c['error']}",
                })
            continue
        if c.get("tipo") == "declarada":
            rules.append(stackup_rule(c["name"], c))
        elif c.get("cerrada_por_construccion"):
            rules.append({
                "regla": f"cadena de cotas · {c['name']}",
                "estado": "ok", "detalle": c["detalle"],
                "calc": {
                    "titulo": f"Ensamble de pernos — {c['name']}",
                    "entradas": {"método": "taladrado conjunto (join_bolted)"},
                    "formula": "barrenos alineados por construcción",
                    "sustitucion": "—", "resultado": "cierra por construcción",
                    "criterio": "sin holgura de posición requerida",
                    "norma": "ISO 2768-1 (no aplica: patrón único)",
                },
            })
        # los pernos manuales INFORMATIVOS (sin veredicto) NO van a la memoria como páginas
        # (serían decenas de bajo valor); están en GET /api/stackup para el agente.
    return rules
