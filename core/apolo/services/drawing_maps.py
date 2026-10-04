"""Mapas POR PIEZA que alimentan el juego de planos: datums funcionales y sistema GD&T,
tolerancias de posición y justificadas, fits ISO 286 y roscas — todos derivados de lo que
el documento DECLARA (uniones, taladros, nombres con fit, cadenas de cotas). `sheet_set_maps`
arma con ellos los kwargs de `drawing.sheet_set`. El llamador sostiene STATE_LOCK.
Reglas: `services/CLAUDE.md` § Mapas por pieza."""

from __future__ import annotations

from apolo.services.installation_data import installation_data
from apolo.services.stackup_eval import stackup_link_from_feature

_SHAFT_FIT_RE = None  # compilado perezoso en feature_fit_maps


def datum_candidates(doc) -> dict[str, list[tuple[float, float, str, str]]]:
    """{feature_id → [(peso, área, lado, motivo)]} ordenado por (peso, área) desc.
    Derivación común de las caras FUNCIONALES desde las uniones DECLARADAS (V7.5): cada
    lado es el que MIRA a una contraparte (soldadura > perno/tornillo > contacto). El eje
    del contacto = el de SOLAPE MÍNIMO entre las cajas (la normal de la cara), mismo
    espíritu que el anclaje de los símbolos de soldadura del GA. `motivo` = la unión que
    lo justifica (va a la leyenda de datums: sin ella el marco GD&T es decorativo).
    PROHIBIDO inferir por nombre (lección V7.2c de los brackets). Llamar bajo STATE_LOCK."""
    W = {"soldadura": 3.0, "perno": 2.0, "tornillo": 2.0}
    cand: dict[str, list[tuple[float, float, str, str]]] = {}
    for f in doc.fasteners.values():
        if not isinstance(f, dict):
            continue
        kind = (f.get("kind") or "contacto").lower()
        w = W.get(kind, 1.0)
        a, b = f.get("a"), f.get("b")
        for me, other in ((a, b), (b, a)):
            fa, fb = doc.scene.get(me), doc.scene.get(other)
            if fa is None or fb is None:
                continue
            try:
                ba, bb = fa.shape.bounding_box(), fb.shape.bounding_box()
            except Exception:
                continue
            mna = (ba.min.X, ba.min.Y, ba.min.Z); mxa = (ba.max.X, ba.max.Y, ba.max.Z)
            mnb = (bb.min.X, bb.min.Y, bb.min.Z); mxb = (bb.max.X, bb.max.Y, bb.max.Z)
            ov = [min(mxa[k], mxb[k]) - max(mna[k], mnb[k]) for k in range(3)]
            k = min(range(3), key=lambda i: ov[i])  # eje del contacto (solape mínimo)
            if ov[k] > 25.0:
                continue  # solape profundo en TODOS los ejes → no hay cara de contacto clara
            area = max(ov[(k + 1) % 3], 0.0) * max(ov[(k + 2) % 3], 0.0)
            sgn = "+" if (mnb[k] + mxb[k]) > (mna[k] + mxa[k]) else "-"
            motivo = f"{kind} a «{str(getattr(fb, 'name', other))[:26]}»"
            cand.setdefault(me, []).append((w, area, sgn + "xyz"[k], motivo))
    return {fid: sorted(e, key=lambda t: (-t[0], -t[1])) for fid, e in cand.items()}


def piece_datum_sides(doc) -> dict[str, list[str]]:
    """{feature_id → lados de sus caras FUNCIONALES, ordenados por peso: ["+z","-x",…]}.
    Se devuelve LISTA porque la cara por la que atraviesa un perno siempre es ⊥ a la vista
    que muestra sus círculos: la vista elige el PRIMER lado que proyecte como borde
    (p. ej. la cara de APOYO). Sin unión declarada → la pieza no entra (fallback de
    esquina, honesto)."""
    out: dict[str, list[str]] = {}
    for fid, entries in datum_candidates(doc).items():
        sides: list[str] = []
        for _, _, side, _m in entries:
            if side not in sides:
                sides.append(side)
        out[fid] = sides[:3]
    return out


def piece_datum_frame(doc) -> dict[str, list[tuple[str, str, str]]]:
    """Sistema de referencia GD&T por pieza (V7.6 A): {feature_id → [(letra, lado,
    motivo)]} con A = cara funcional de mayor peso, B = la siguiente ORTOGONAL a A, y
    C = la tercera ortogonal a ambas — el marco de referencia que exige un control de
    posición. Solo se emiten las letras que las uniones REALES justifican: una pieza con
    una sola cara de montaje se queda con «A» (inventar B/C sería mentir sobre cómo se
    posiciona la pieza). Llamar bajo STATE_LOCK."""
    out: dict[str, list[tuple[str, str, str]]] = {}
    for fid, entries in datum_candidates(doc).items():
        chosen: list[tuple[str, str, str]] = []
        used_axes: set[str] = set()
        for _w, _a, side, motivo in entries:
            axis = side[1]
            if axis in used_axes:       # B y C deben ser ORTOGONALES a los anteriores
                continue
            used_axes.add(axis)
            chosen.append(("ABC"[len(chosen)], side, motivo))
            if len(chosen) == 3:
                break
        if chosen:
            out[fid] = chosen
    return out


def piece_dim_tols(doc) -> dict[str, dict[str, tuple[float, str, str]]]:
    """Tolerancia de la COTA GENERAL por pieza y eje (V7.6 B): {feature_id → {"X"|"Y"|"Z"
    → (media_tol_mm, nombre_de_cadena, fuente)}}. Sale de los eslabones `{id, eje}` de las
    cadenas DECLARADAS (`Document.stackups`): si una cota participa en una cadena, la
    lámina rotula la tolerancia que el ANÁLISIS exige — no la genérica de ISO 2768 — y la
    nota remite a la memoria. Es la diferencia entre «tolerancia tabulada» y «tolerancia
    justificada».

    Solo se rotulan bandas SIMÉTRICAS (±t): una banda asimétrica (fit ISO 286) no cabe en
    el formato de cota general y ya viaja en su propio callout de Ø. Varias cadenas sobre
    la misma cota → gana la MÁS ESTRICTA (la que de verdad manda). Bajo STATE_LOCK."""
    from apolo.library.engineering.stackup import stack_up

    out: dict[str, dict[str, tuple[float, str, str]]] = {}
    for name, spec in sorted(getattr(doc, "stackups", {}).items()):
        for e in (spec.get("eslabones") or []):
            fid = e.get("id")
            if not fid or fid not in doc.scene:
                continue
            eje = str(e.get("eje", "x")).upper()
            try:
                link = stackup_link_from_feature(doc, fid, e.get("eje", "x"), e.get("tol"))
                if link is None:
                    continue
                det = stack_up([link])["eslabones"][0]
                lo, hi = float(det["dev_lo_mm"]), float(det["dev_hi_mm"])
                if abs(lo + hi) > 1e-9 or hi <= 0:
                    continue           # asimétrica (fit) o sin banda → va en su callout
                half = float(det["half_tol_mm"])
            except Exception:  # noqa: BLE001 — una cadena mala no tumba el juego de planos
                continue
            prev = out.setdefault(fid, {}).get(eje)
            if prev is None or half < prev[0]:
                out[fid][eje] = (half, str(name), str(det.get("fuente", "")))
    return out


def piece_pos_tols(doc) -> dict[str, dict[float, float]]:
    """Tolerancia de POSICIÓN por pieza y Ø (V7.6 A): {feature_id → {Ø_barreno → t_mm}}.
    `t` = presupuesto de ensamble de `bolt_pattern_budget` para el perno que ATRAVIESA
    ese barreno — fijo `(Ø_paso−Ø_perno)/2` o FLOTANTE `(Ø_paso−Ø_perno)` si hay tuerca
    en el mismo eje (el perno se acomoda en ambas piezas). Es el número que va DENTRO del
    marco de control ⌖; sin perno identificable en el eje NO se emite entrada — una
    tolerancia GD&T inventada es peor que su ausencia (el taller la fabrica). Varios
    pernos con el mismo Ø → gana el presupuesto MENOR (conservador). Bajo STATE_LOCK."""
    import re as _re

    from apolo.commands.expressions import resolve_params
    from apolo.library.catalog import CATALOG
    from apolo.library.engineering.bolts import CLEARANCE_HOLE_MM
    from apolo.library.engineering.stackup import bolt_pattern_budget
    from apolo.library.lints import _AXIS_VEC, _is_bolt, _perp_dist

    _M_RE = _re.compile(r"\bM(\d{1,2})(?:[×x]\d+)?\b")
    _NUT_RE = _re.compile(r"\btuerca[s]?\b", _re.I)
    # tabla ISO 273 INVERTIDA: Ø de paso → Ø nominal del perno (Ø13.5 = paso de un M12)
    _ISO273_INV = {round(v, 1): float(k.lstrip("M")) for k, v in CLEARANCE_HOLE_MM.items()}

    # 1) tornillería presente, POR SÓLIDO (un compound lleva N pernos: su centro conjunto
    #    no cae en el eje de ninguno — la lección de la brecha 1)
    herraje: list[tuple[tuple[float, float, float], float | None, bool]] = []
    for feat in doc.scene.values():
        if not getattr(feat, "visible", True) or not _is_bolt(feat, CATALOG):
            continue
        comp = CATALOG.get(getattr(feat, "component", None) or "")
        nombre = getattr(feat, "name", "") or ""
        d = None
        m = _M_RE.search(nombre)
        if m:
            d = float(m.group(1))
        elif comp is not None:
            try:
                d = float((comp.specs or {}).get("d"))
            except (TypeError, ValueError):
                d = None
        # d=None NO descarta: la pieza sigue siendo PRESENCIA de tornillería en el eje
        # (el Ø puede salir de la tabla ISO 273); solo se pierde como fuente de Ø
        es_tuerca = bool(_NUT_RE.search(nombre)) or (
            comp is not None and comp.category == "tuercas")
        try:
            solids = list(feat.shape.solids())
        except Exception:
            solids = []
        for s in solids or [feat.shape]:
            try:
                bb = s.bounding_box()
            except Exception:
                continue
            herraje.append((((bb.min.X + bb.max.X) / 2.0, (bb.min.Y + bb.max.Y) / 2.0,
                             (bb.min.Z + bb.max.Z) / 2.0), d, es_tuerca))
    if not herraje:
        return {}

    out: dict[str, dict[float, float]] = {}
    for cmd in doc.commands:
        if cmd.get("type") != "drill_hole":
            continue
        try:
            p = resolve_params(cmd.get("params", {}) or {}, doc.variables_resolved)
            if p.get("thread") or float(p.get("depth", 0) or 0) > 0:
                continue                               # roscado o ciego: no es de paso
            dia = float(p.get("diameter", 0))
            fid = cmd.get("params", {}).get("feature")
            if dia <= 0 or fid not in doc.scene:
                continue
            pos = p.get("position") or {}
            p0 = (float(pos.get("x", 0)), float(pos.get("y", 0)), float(pos.get("z", 0)))
            u = _AXIS_VEC.get(str(p.get("axis", "z")).lstrip("+-"), _AXIS_VEC["z"])
            tol = max(dia, 6.0)
            en_eje = [(d, nut) for c, d, nut in herraje if _perp_dist(c, p0, u) <= tol]
            if not en_eje:
                continue                               # sin tornillería en el eje → sin marco
            # Ø del perno: la tabla de paso ISO 273 es la fuente NORMATIVA (un barreno de
            # Ø13.5 ES el paso de un M12); si el Ø no está tabulado, el que declare la
            # tornillería del eje (catálogo o «M14» en su nombre)
            d_bolt = _ISO273_INV.get(round(dia, 1))
            if d_bolt is None:
                pernos = [d for d, nut in en_eje if not nut and d]
                d_bolt = min(pernos) if pernos else None
            if d_bolt is None or d_bolt >= dia:
                continue                               # sin Ø de perno fiable → sin marco
            flot = any(nut for _d, nut in en_eje)
            t = bolt_pattern_budget(dia, d_bolt, [], flotante=flot)["presupuesto_mm"]
            if t <= 0:
                continue
            key = round(dia, 1)
            prev = out.setdefault(fid, {}).get(key)
            out[fid][key] = t if prev is None else min(prev, t)
        except Exception:  # noqa: BLE001 — un comando raro no rompe el juego de planos
            continue
    return out


def feature_fit_maps(doc) -> dict[str, dict[float, str]]:
    """Fits ISO 286 POR feature (V7.2c): cada feature_id → {Ø_nominal → clase} de SU
    nombre («… Ø35 g6») + los drill_hole que la perforan con `fit`. Es la fuente para
    las LÁMINAS POR PIEZA: cada pieza rotula EL SUYO, sin que el fit de un eje pise al
    de otro que comparte Ø nominal (regresión del fix D — el 38 tiene DOS ejes Ø35, el
    motriz h7 y el tensor g6)."""
    import re

    global _SHAFT_FIT_RE
    if _SHAFT_FIT_RE is None:
        _SHAFT_FIT_RE = re.compile(
            r"Ø\s*(\d+(?:\.\d+)?)\s+((?:js|[gfhkmnp]))(\d{1,2})\b"
        )
    per: dict[str, dict[float, str]] = {}
    for fid, feat in doc.scene.items():
        m = _SHAFT_FIT_RE.search(getattr(feat, "name", "") or "")
        if m:
            per.setdefault(fid, {})[float(m.group(1))] = f"{m.group(2)}{m.group(3)}"
    for cmd in doc.commands:
        if cmd.get("type") == "drill_hole" and cmd.get("params", {}).get("fit"):
            try:
                dia = float(cmd["params"].get("diameter", 0))
            except (TypeError, ValueError):
                continue  # diámetro por "=expresión": se omite del mapa automático
            tgt = cmd["params"].get("feature")
            if dia > 0 and tgt and tgt in doc.scene:
                per.setdefault(tgt, {})[dia] = cmd["params"]["fit"]
    return per


def scene_fit_map(doc, scene) -> dict[float, str]:
    """Mapa Ø_nominal → clase ISO 286 para una VISTA de CONJUNTO/GA que abarca `scene`
    (V7.2c): mergea los fits por-feature (`feature_fit_maps`) y, ante CONFLICTO (mismo
    Ø con clases distintas en piezas distintas), OMITE ese Ø — en un GA un fit
    equivocado es PEOR que uno ausente (antes «el último gana» pisaba g6 con h7). Cada
    lámina por pieza no usa esto sino su mapa por-feature."""
    per = feature_fit_maps(doc)
    out: dict[float, str] = {}
    conflict: set[float] = set()
    for fid in scene:
        for dia, cls in per.get(fid, {}).items():
            if dia in out and out[dia] != cls:
                conflict.add(dia)
            else:
                out[dia] = cls
    for dia in conflict:
        out.pop(dia, None)
    return out


def hole_fit_map(doc) -> dict[float, str]:
    """Mapa AUTOMÁTICO Ø_nominal → clase ISO 286 para el CONJUNTO/GA (V5.4, endurecido
    en V7.2c): drill_hole con `fit` + NOMBRES «… Ø35 h7». Conflicto de Ø (dos ejes de
    igual Ø con fits distintos) → se OMITE ese Ø en vez de mentir. Las láminas por
    pieza usan `feature_fit_maps` (cada pieza, el suyo)."""
    return scene_fit_map(doc, doc.scene)


def hole_thread_map(doc) -> dict[float, str]:
    """Mapa AUTOMÁTICO Ø_broca → designación de rosca (V5.7) desde los comandos
    drill_hole con `thread`. El círculo HLR que sale al plano es el de la BROCA
    (M8 → Ø6.8) — si una broca coincide con el Ø de un agujero liso mapeado, gana
    la rosca (los círculos HLR no distinguen origen; mismo caveat que los fits)."""
    from apolo.library.engineering.threads import thread_designation, thread_spec

    out: dict[float, str] = {}
    for cmd in doc.commands:
        thr = cmd.get("params", {}).get("thread") if cmd.get("type") == "drill_hole" else None
        if thr:
            try:
                des = thread_designation(thr)
                out[thread_spec(des)["broca_mm"]] = des
            except KeyError:
                continue  # rosca inválida en un log viejo: no rompe el plano
    return out


def thread_schedule(doc) -> list[dict]:
    """Roscas agrupadas por designación para la CÉDULA del juego de planos (V5.7):
    [{designacion, etiqueta, cantidad, broca_mm, piezas, norma}]."""
    from apolo.library.engineering.threads import (
        format_thread_label, thread_designation, thread_spec,
    )

    groups: dict[str, dict] = {}
    for cmd in doc.commands:
        if cmd.get("type") != "drill_hole":
            continue
        thr = cmd.get("params", {}).get("thread")
        if not thr:
            continue
        try:
            des = thread_designation(thr)
            spec = thread_spec(des)
        except KeyError:
            continue
        g = groups.setdefault(des, {
            "designacion": des, "etiqueta": format_thread_label(des),
            "cantidad": 0, "broca_mm": spec["broca_mm"], "piezas": [], "norma": spec["norma"],
        })
        g["cantidad"] += 1
        feat = doc.scene.get(cmd.get("params", {}).get("feature"))
        name = getattr(feat, "name", None)
        if name and name not in g["piezas"]:
            g["piezas"].append(name)
    return sorted(groups.values(), key=lambda g: g["designacion"])


def sheet_set_maps(doc) -> dict:
    """Los kwargs de `drawing.sheet_set` que salen del DOCUMENTO —fits, datums, GD&T,
    tolerancias de posición y justificadas, instalación, roscas y soldadura—, comunes al
    juego en PDF y en DWG (D7 del plan partir-api-main: antes eran dos copias a mano). El
    cajetín (`meta`), los colores del viewport y el `shaded` del PDF los pone el endpoint.
    Llamar bajo STATE_LOCK."""
    return dict(
        hole_fits=hole_fit_map(doc) or None,
        piece_fits=feature_fit_maps(doc) or None,  # V7.2c: cada lámina, SU fit
        piece_datums=piece_datum_sides(doc) or None,  # V7.5: datum funcional
        piece_datum_frames=piece_datum_frame(doc) or None,  # V7.6: A-B-C
        piece_pos_tols=piece_pos_tols(doc) or None,  # V7.6: tol. de posición
        piece_dim_tols=piece_dim_tols(doc) or None,  # V7.6b: tol. justificada
        installation=installation_data(doc),  # V7.6c: lámina de obra
        hole_threads=hole_thread_map(doc) or None,
        thread_rows=thread_schedule(doc) or None,
        fasteners=doc.fasteners,  # V7.2 A: soldadura ISO 2553 en el conjunto
    )
