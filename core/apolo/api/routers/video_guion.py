"""El guion del video que graba el botón «Grabar video» del visor (plan video-realista, D5).

`POST /api/video/guion` arma, sobre el documento ACTIVO, el mismo guion de montaje que
`publicar guion --modo montaje` (con la última marcha simulada del proyecto, si la hay) y su plan
cuadro por cuadro (`services/plan_navegador.py`). La UI abre con los dos la sesión de
grabación (`video.py`). Vive aparte porque lee la escena bajo `STATE_LOCK`: la grabación es E/S
pura y no conoce el documento (D4). El CLI no pasa por aquí: arma el guion y el plan sobre su
propia copia del documento (D1 de publicacion-tienda).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apolo.state import STATE_LOCK

from ..session import S
from ..sims import MARCHAS

router = APIRouter()


class GuionIn(BaseModel):
    #: Duración objetivo del video entero (s), como `publicar guion --duracion`.
    duracion_s: float = 75.0
    titulo: str | None = None
    #: Sumar la máquina andando si el proyecto tiene una marcha simulada (la última).
    marcha: bool = True


@router.post("/api/video/guion")
def guion_del_documento(body: GuionIn | None = None) -> dict:
    """{guion, plan} de MONTAJE del documento activo, con la última marcha simulada del proyecto
    si la hay: lo que graba el botón «Grabar video»."""
    from apolo.services.plan_navegador import PlanError, plan
    from apolo.services.datos_rotulos import datos_rotulos
    from apolo.services.guion_video import MARCHA_S, MODO_MONTAJE, GuionError, validar_guion
    from apolo.services.guion_video import guion as armar
    from apolo.services.montaje_video import etapas_del_modo

    b = body or GuionIn()
    with STATE_LOCK:
        doc, proyecto = S.doc, S.project_id
        if not doc.scene:
            raise HTTPException(400, "El proyecto no tiene piezas: no hay video que grabar.")
        escenario = MARCHAS.ultimo_escenario(proyecto) if b.marcha else None
        marcha = {"duracion_s": MARCHA_S, "escenario": escenario} if escenario else None
        objetivo = max(b.duracion_s - (MARCHA_S if marcha else 0.0), 1.0)
        try:
            etapas = etapas_del_modo(doc, objetivo, MODO_MONTAJE, datos=datos_rotulos(doc))
            guion = armar(doc, etapas, titulo=b.titulo, modo=MODO_MONTAJE, marcha=marcha)
            validar_guion(guion, doc)
            p = plan(doc, guion, proyecto)
        except (GuionError, PlanError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from exc
    return {"guion": guion, "plan": p}
