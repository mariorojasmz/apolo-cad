"""Rutas sobre las piezas: visibilidad, boceto-guía, color, material, topología y medición.

Router de la API (F6b del plan `docs/plans/partir-api-main.md`): movidas tal cual desde
`main.py`. Los lotes de color/material validan TODO antes de tocar nada (un id malo → 404 con
sugerencia y cero efectos parciales); las lecturas (topología, grupos, masa, medida, cercanía)
no mutan.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apolo.state import STATE_LOCK

from ..common import _not_found, _state_or_error
from ..scene import groups_payload
from ..session import S

router = APIRouter()


class VisibilityIn(BaseModel):
    visible: bool


@router.post("/api/features/{feature_id}/visibility")
def set_visibility(feature_id: str, body: VisibilityIn) -> dict:
    # devuelve el command_id afectado → el cliente MCP recorta el retorno a la pieza
    def run():
        S.doc.set_visibility(feature_id, body.visible)
        return S.doc.scene[feature_id].command_id
    return _state_or_error(run)


class BulkVisibilityIn(BaseModel):
    ids: list[str]
    visible: bool


@router.post("/api/features/visibility")
def set_visibility_bulk(body: BulkVisibilityIn) -> dict:
    """Visibilidad en lote (aislar / mostrar todo) en una sola llamada."""
    def run():
        for fid in body.ids:
            S.doc.set_visibility(fid, body.visible)
        return sorted({S.doc.scene[fid].command_id for fid in body.ids if fid in S.doc.scene})
    return _state_or_error(run)


class SketchGuideIn(BaseModel):
    guide: bool


@router.post("/api/features/{feature_id}/sketch-guide")
def set_sketch_guide(feature_id: str, body: SketchGuideIn) -> dict:
    """Marca/desmarca un sólido (y las piezas de su comando) como boceto-guía (blockout):
    geometría de intención excluida de BOM/masa/interferencia/FEA que el agente consume."""
    def run():
        S.doc.set_sketch_guide(feature_id, body.guide)
        return S.doc.scene[feature_id].command_id
    return _state_or_error(run)


@router.get("/api/features/{feature_id}/topology")
def get_feature_topology(
    feature_id: str, only: str | None = None, min_mm: float = 0.0
) -> dict:
    """Caras y aristas de un sólido con su geometría (tipo, centro, normal/eje,
    longitud, radio) para elegir el SELECTOR declarativo. Incluye las ANCLAS de conexión
    con nombre (V6.3b) para matear por `{"mode":"ancla","name":...}`. `only` acota a
    `caras`|`aristas`|`anclas`; `min_mm` omite aristas/caras menores (micro-fillets, taladros
    diminutos = el grueso del ruido en piezas mecanizadas). Read-only."""
    from apolo.kernel.topology import feature_topology

    with STATE_LOCK:
        feat = S.doc.scene.get(feature_id)
        if feat is None:
            raise _not_found(feature_id)
        topo = feature_topology(feat.shape, only=only, min_mm=min_mm)
        anchors = feat.anchors or {}
    out = {"feature_id": feature_id, "name": feat.name, **topo}
    if only in (None, "", "anclas"):  # anclas solo en la vista completa o si se piden
        out["anchors"] = anchors
    return out


@router.get("/api/groups")
def get_groups_endpoint() -> dict:
    """Grupos/sub-ensamblajes del documento (con members faltantes). Read-only."""
    with STATE_LOCK:
        return {"groups": groups_payload()}


@router.get("/api/mass-properties")
def mass_properties(ids: str | None = None) -> dict:
    """Masa, centro de gravedad y bbox por pieza y del conjunto. Sin `ids`
    (CSV) analiza todas las visibles; con ids las incluye aunque estén ocultas.
    Catálogo pesa por ficha; a-medida por volumen × densidad. Read-only."""
    from apolo.library.engineering.mass import scene_mass_properties

    wanted = [s.strip() for s in ids.split(",") if s.strip()] if ids else None
    with STATE_LOCK:
        try:
            return scene_mass_properties(S.doc.scene, ids=wanted)
        except KeyError as exc:
            raise _not_found(exc.args[0]) from exc


class MeasureIn(BaseModel):
    a: str
    b: str
    face_a: dict | None = None  # selector de cara opcional para medir contra UNA cara de a
    face_b: dict | None = None


@router.post("/api/measure")
def measure_endpoint(body: MeasureIn) -> dict:
    """Distancia mínima (mm) y puntos más cercanos entre los sólidos a y b. Con face_a/face_b
    (selector declarativo) mide contra una cara concreta. Read-only."""
    from apolo.kernel.measure import measure_distance
    from apolo.kernel.selectors import SelectorError, resolve_faces

    with STATE_LOCK:
        fa = S.doc.scene.get(body.a)
        fb = S.doc.scene.get(body.b)
        if fa is None or fb is None:
            raise _not_found(body.a if fa is None else body.b)
        sa, sb = fa.shape, fb.shape
        try:
            if body.face_a:
                sa = resolve_faces(sa, body.face_a)[0]
            if body.face_b:
                sb = resolve_faces(sb, body.face_b)[0]
        except (SelectorError, IndexError) as exc:
            raise HTTPException(status_code=400, detail=f"Selector de cara inválido: {exc}") from exc
        try:
            res = measure_distance(sa, sb)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"a": body.a, "b": body.b, **res}


@router.get("/api/near")
def near_endpoint(
    point: str | None = None,
    feature: str | None = None,
    box: str | None = None,
    radius: float = 50.0,
    limit: int = 20,
) -> dict:
    """Features cercanas por caja envolvente, ordenadas de más cerca a más lejos (V6.5b).
    Exactamente UNO de: `point` (JSON [x,y,z] — «¿qué hay por aquí?»), `feature` (id —
    «¿qué rodea a X?», excluyéndolo) o `box` (JSON [[min],[max]] — «¿qué hay en esta región?»).
    `radius` (mm) + `limit`. Barrido O(n) sobre AABBs. Read-only."""
    from apolo.kernel.measure import features_near, features_near_box, features_near_feature

    dados = [k for k, v in (("point", point), ("feature", feature), ("box", box)) if v is not None]
    if len(dados) != 1:
        raise HTTPException(
            status_code=400, detail="Da EXACTAMENTE uno de: point, feature, box"
        )
    lim = limit if limit and limit > 0 else None
    with STATE_LOCK:
        if feature is not None:
            if feature not in S.doc.scene:
                raise _not_found(feature)
            cercanas = features_near_feature(S.doc.scene, feature, radius, limit=lim)
            modo = {"feature": feature}
        elif box is not None:
            try:
                bx = json.loads(box)
                assert (isinstance(bx, (list, tuple)) and len(bx) == 2
                        and all(len(p) == 3 for p in bx))
            except Exception as exc:
                raise HTTPException(
                    status_code=400, detail=f"box debe ser JSON [[min_x,min_y,min_z],[max...]]: {exc}"
                ) from exc
            cercanas = features_near_box(S.doc.scene, bx, radius, limit=lim)
            modo = {"box": bx}
        else:
            try:
                pt = json.loads(point)
                assert isinstance(pt, (list, tuple)) and len(pt) == 3
            except Exception as exc:
                raise HTTPException(
                    status_code=400, detail=f"point debe ser JSON [x,y,z]: {exc}"
                ) from exc
            cercanas = features_near(S.doc.scene, pt, radius, limit=lim)
            modo = {"point": pt}
    return {**modo, "radius": radius, "cercanas": cercanas}


class ColorIn(BaseModel):
    color: str | None = None  # null = volver al color automático


@router.post("/api/features/{feature_id}/color")
def set_feature_color(feature_id: str, body: ColorIn) -> dict:
    return _state_or_error(lambda: S.doc.set_color(feature_id, body.color))


class BulkColorIn(BaseModel):
    ids: list[str]
    color: str | None = None  # null = volver al color automático


@router.post("/api/features/color")
def set_color_bulk(body: BulkColorIn) -> dict:
    """Color en LOTE (V6.8-A): valida TODOS los ids ANTES de tocar nada (uno
    inexistente → 404 con sugerencia y CERO efectos parciales) y aplica en una
    pasada — un solo autosave/notify en vez de N llamadas."""
    if not body.ids:
        raise HTTPException(status_code=400, detail="La lista 'ids' no puede estar vacía")

    def run():
        for fid in body.ids:
            if fid not in S.doc.scene:
                raise _not_found(fid)
        for fid in body.ids:
            S.doc.set_color(fid, body.color)
        return sorted({S.doc.scene[fid].command_id for fid in body.ids})

    return _state_or_error(run)


class MaterialIn(BaseModel):
    material: str | None = None  # null = volver al material automático (heurística)


@router.post("/api/features/{feature_id}/material")
def set_feature_material(feature_id: str, body: MaterialIn) -> dict:
    def run():
        S.doc.set_material(feature_id, body.material)
        return S.doc.scene[feature_id].command_id
    return _state_or_error(run)


class BulkMaterialIn(BaseModel):
    ids: list[str]
    material: str | None = None  # null = volver al material automático (heurística)


@router.post("/api/features/material")
def set_material_bulk(body: BulkMaterialIn) -> dict:
    """Material en LOTE (V6.8-A) — mismo contrato que el color bulk: validar
    todo, aplicar todo, o 404 sin efectos parciales."""
    if not body.ids:
        raise HTTPException(status_code=400, detail="La lista 'ids' no puede estar vacía")

    def run():
        for fid in body.ids:
            if fid not in S.doc.scene:
                raise _not_found(fid)
        for fid in body.ids:
            S.doc.set_material(fid, body.material)
        return sorted({S.doc.scene[fid].command_id for fid in body.ids})

    return _state_or_error(run)


class VerticalIn(BaseModel):
    vertical: str  # 'metalmecanica' | 'carpinteria'


@router.post("/api/vertical")
def set_project_vertical(body: VerticalIn) -> dict:
    return _state_or_error(lambda: S.doc.set_vertical(body.vertical))
