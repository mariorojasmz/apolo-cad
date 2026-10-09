"""Preparación del FEA de un documento (V5.6 pieza, V7.4 ensamblaje bonded): la fase (a) del
patrón dos-locks —validar, resolver material y selectores, derivar empotramiento y carga,
exportar los STEP del ensamblaje— y el historial de convergencia de malla. La coreografía
(STATE_LOCK, tmp dir, solve fuera del lock, guardia de proyecto, campo en memoria) es de la
API (plan `docs/plans/partir-api-main.md`, D8). El llamador sostiene STATE_LOCK. Los 400/404
salen como `ServiceError` con el texto EXACTO. `body` = los campos del modelo de la API
(`FeaStaticIn` / `FeaAssemblyIn`): services no importa sus modelos. Reglas:
`services/CLAUDE.md` § FEA."""

from __future__ import annotations

from pathlib import Path

from .errors import ServiceError
from .roles import BED_RE


def prepare_static(doc, body) -> dict:
    """Fase (a) del FEA de UNA pieza, salvo el STEP (lo exporta la API en su tmp dir): valida
    la pieza, resuelve material/σy/E/ρ y los selectores de empotramiento y cargas. Devuelve
    {feat, material, sy, e_mpa, rho, fixed, loads}. Llamar bajo STATE_LOCK."""
    from apolo.fea.mesher import FaceDesc
    from apolo.kernel.selectors import SelectorError, resolve_faces
    from apolo.library.catalog import CATALOG
    from apolo.library.materials import (
        density, has_yield, resolve_material, yield_strength, young_modulus,
    )

    from apolo.kernel.shapes import is_surface

    feat = doc.scene.get(body.feature_id)
    if feat is None:
        raise ServiceError(404, f"No existe la pieza '{body.feature_id}'")
    if is_surface(feat.shape):
        raise ServiceError(
            400,
            f"'{feat.name}' es una superficie (volumen 0); el FEA necesita un "
            f"sólido. Dale espesor con thicken antes de analizarla.",
        )
    if getattr(feat, "is_guide", False):
        raise ServiceError(
            400,
            f"'{feat.name}' es un boceto-guía (blockout), no una pieza a analizar.",
        )
    material = body.material or resolve_material(feat, CATALOG, doc.default_material())
    if body.yield_mpa is not None:
        sy = float(body.yield_mpa)
    elif has_yield(material):
        sy = yield_strength(material)
    else:
        raise ServiceError(
            400,
            f"El material '{material}' no tiene límite elástico tabulado: "
            f"pasa yield_mpa explícito (el FS saldría de un default y mentiría)",
        )
    e_mpa, rho = young_modulus(material), density(material)
    try:
        fixed = [FaceDesc.from_face(f) for f in resolve_faces(feat.shape, body.fixed)]
        loads = []
        for ld in body.loads:
            descs = [FaceDesc.from_face(f) for f in resolve_faces(feat.shape, ld.selector)]
            loads.append({"descs": descs, "force_n": ld.force_n,
                          "pressure_mpa": ld.pressure_mpa})
    except SelectorError as exc:
        raise ServiceError(400, str(exc)) from exc
    return {"feat": feat, "material": material, "sy": sy, "e_mpa": e_mpa, "rho": rho,
            "fixed": fixed, "loads": loads}


def resolve_assembly_scope(doc, body) -> tuple[list[str], str]:
    """`(fids, grupo)` del FEA de ensamblaje: un GRUPO (recursivo) o una lista de ids.
    Llamar bajo STATE_LOCK."""
    from apolo.assembly.groups import group_features

    if body.group:
        fids = group_features(doc.scene, doc.groups, body.group, recursive=True)
        grupo = body.group
        if not fids:
            raise ServiceError(404, f"El grupo '{body.group}' no existe o no tiene piezas")
    elif body.ids:
        fids = [f for f in body.ids if f in doc.scene]
        grupo = body.name or "selección"
        if not fids:
            raise ServiceError(404, "Ninguna de las piezas (ids) existe en la escena")
    else:
        raise ServiceError(400, "Da un group o una lista de ids")
    return fids, grupo


def prepare_assembly(doc, body, fids: list[str], grupo: str, tmp_dir: str) -> dict:
    """Fase (a) del FEA BONDED (V7.4): por pieza resuelve material/σy y exporta su STEP a
    `tmp_dir` (lo crea y lo borra la API); deriva el empotramiento (grounds ∩ grupo, o
    `fixed_pieces`) y la carga (requisitos sobre la cama, o `loads` explícitos). El herraje se
    EXCLUYE de la malla y su peso entra como carga sustituta DECLARADA. Devuelve los params
    de `run_assembly_analysis` y `uniones_empernadas` (cuántas declara la hipótesis). Llamar
    bajo STATE_LOCK."""
    from apolo.fea.mesher import FaceDesc
    from apolo.kernel import export_step_file
    from apolo.kernel.selectors import SelectorError, resolve_faces
    from apolo.kernel.shapes import is_surface
    from apolo.library.catalog import CATALOG
    from apolo.library.checks import FEA_HARDWARE_CATS, hardware_ids
    from apolo.library.engineering.mass import feature_mass
    from apolo.library.materials import (
        density, has_yield, resolve_material, yield_strength, young_modulus,
    )

    # exclusión FEA: herraje + motores/chumaceras/tuercas/tensores (geometría
    # representativa — mallarla mentiría rigidez y peso)
    hw = hardware_ids(doc, cats=FEA_HARDWARE_CATS)
    grounded = {g["feature"] for g in doc.grounds.values()}

    pieces_in: list[dict] = []
    excluded: list[dict] = []
    struct_ids: list[str] = []
    feat_by_id: dict = {}
    try:
        for fid in fids:
            feat = doc.scene.get(fid)
            if feat is None:
                continue
            feat_by_id[fid] = feat
            if is_surface(feat.shape) or getattr(feat, "is_guide", False):
                continue  # superficie/guía = geometría de construcción, fuera de la malla
            material = resolve_material(feat, CATALOG, doc.default_material())
            if fid in hw:
                fm = feature_mass(feat, CATALOG, doc.default_material())
                excluded.append({"name": feat.name, "masa_kg": fm["masa_kg"]})
                continue
            if has_yield(material):
                sy = yield_strength(material)
            elif body.yield_mpa is not None:
                sy = float(body.yield_mpa)
            else:
                raise ServiceError(
                    400,
                    f"'{feat.name}' es de '{material}' sin límite elástico tabulado: "
                    f"pasa yield_mpa de respaldo (el FS saldría de un default y mentiría)",
                )
            nu = 0.33 if "alumin" in material.lower() else 0.30
            step = str(Path(tmp_dir) / f"{fid}.step")
            export_step_file([feat.shape], step)
            pieces_in.append({
                "key": fid, "name": feat.name, "step_path": step,
                "e_mpa": young_modulus(material), "nu": nu, "yield_mpa": sy,
                "density_kg_mm3": density(material), "material": material,
                "volumen_mm3": round(float(feat.shape.volume), 1),
            })
            struct_ids.append(fid)

        if not pieces_in:
            raise ServiceError(
                400,
                "El grupo no tiene piezas sólidas estructurales (solo herraje/superficies).",
            )

        # empotramiento: base de las piezas con ground ∩ grupo (o fixed_pieces explícito)
        fix_ids = list(body.fixed_pieces) if body.fixed_pieces else [
            i for i in struct_ids if i in grounded]
        fix_ids = [i for i in fix_ids if i in feat_by_id]
        if not fix_ids:
            raise ServiceError(
                400,
                "Sin empotramiento: ancla a piso (ground) las patas/placas del grupo "
                "o pasa fixed_pieces con las piezas a fijar por su base.",
            )
        fixed = []
        for fid in fix_ids:
            fixed += [FaceDesc.from_face(f)
                      for f in resolve_faces(feat_by_id[fid].shape, {"mode": "cara", "face": "base"})]

        # cargas: explícitas, o auto (producto + herraje) sobre la cama/mesa
        carga = body.carga_kg if body.carga_kg is not None else (doc.requirements or {}).get("carga_kg")
        loads: list[dict] = []
        sub_applied = False
        if body.loads:
            for ld in body.loads:
                f = feat_by_id.get(ld.feature_id) or doc.scene.get(ld.feature_id)
                if f is None:
                    raise ServiceError(404,
                                       f"La carga referencia '{ld.feature_id}', ausente de la escena")
                descs = [FaceDesc.from_face(x) for x in resolve_faces(f.shape, ld.selector)]
                loads.append({"descs": descs, "force_n": ld.force_n, "pressure_mpa": ld.pressure_mpa})
        elif carga:
            bed_ids = [i for i in struct_ids if BED_RE.search(feat_by_id[i].name or "")]
            if not bed_ids:
                raise ServiceError(
                    400,
                    "No encuentro la cama/mesa que recibe la carga: nómbrala "
                    "(cama/mesa/deck/tablero) o pasa loads explícitos {feature_id, selector, force_n}.",
                )
            bed_descs = []
            for i in bed_ids:
                bed_descs += [FaceDesc.from_face(f)
                              for f in resolve_faces(feat_by_id[i].shape, {"mode": "cara", "face": "tope"})]
            hw_kg = sum(e["masa_kg"] for e in excluded)
            F = (float(carga) + hw_kg) * 9.81
            loads.append({"descs": bed_descs, "force_n": [0.0, 0.0, -F]})
            # SOLO esta rama mete el peso del herraje excluido como carga sustituta
            sub_applied = True
    except SelectorError as exc:
        raise ServiceError(400, str(exc)) from exc

    return {"grupo": grupo, "pieces": pieces_in, "fixed": fixed, "loads": loads,
            "excluded": excluded, "struct_ids": struct_ids,
            "substitute_applied": sub_applied,
            "uniones_empernadas": bolted_joints_in_mesh(doc, struct_ids)}


def bolted_joints_in_mesh(doc, mesh_ids: list[str]) -> int:
    """Fasteners `perno` (`fasten`, el `jb_*` de `join_bolted`) cuyas DOS piezas entran a la
    malla: el bonded los analiza PEGADOS sobre su superficie de contacto y el resumen debe
    decirlo (D8 de fea-chapa-empernada). Con una pieza fuera (herraje excluido, fuera del
    grupo) no hay junta en la malla. Una soldadura no cuenta: pegado es su hipótesis."""
    en_malla = set(mesh_ids)
    return sum(1 for f in doc.fasteners.values()
               if f.get("kind", "perno") == "perno"
               and f.get("a") in en_malla and f.get("b") in en_malla)


def merge_convergence(doc, key: str, resumen: dict) -> None:
    """Historial de CONVERGENCIA de malla (E3.7) en `resumen`, justo antes de guardarlo: si
    ya había un análisis del MISMO grupo con OTRO mesh_size, el run anterior pasa al
    historial (tope 3). Corre bajo STATE_LOCK (`before_save` de la persistencia)."""
    # CONVERGENCIA de malla (E3.7): si ya había un análisis del MISMO grupo con
    # OTRO mesh_size, el run anterior pasa al historial (tope 3) y la memoria
    # imprime la serie — refinar y ver la gobernante estabilizarse es el
    # argumento de firma
    prev = doc.fea.get(key)
    hist = list((prev or {}).get("convergencia") or [])
    if prev and prev.get("mesh_size_mm") not in (None, resumen.get("mesh_size_mm")):
        hist.append({k2: prev.get(k2) for k2 in
                     ("mesh_size_mm", "n_tets", "fs", "pieza_critica",
                      "desplazamiento_max_mm")})
    # el VIGENTE reemplaza cualquier entrada del historial con su MISMA malla
    # (evita imprimir dos veces el mismo size con geometrías de distinta fecha)
    hist = [h for h in hist if h.get("mesh_size_mm") != resumen.get("mesh_size_mm")]
    if hist:
        resumen["convergencia"] = hist[-3:]
