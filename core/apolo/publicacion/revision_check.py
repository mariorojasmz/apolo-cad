"""Lo NO determinista de la publicación, exigido de forma determinista (plan
puerta-de-publicacion, F4 · D6, D7, D10). Puro: recibe los JSON ya leídos y devuelve la lista
de problemas (vacía = pasa), cada uno con lo que hay que hacer.

- `problemas_revision(datos, firma)`: `revision.json`, el veredicto del revisor de taller (un
  LLM) sobre la MISMA firma del modelo que se publica. Formato en `design/revision.py`
  (`formato_revision`); sus constantes se copian aquí porque la publicación no importa `design`
  (`tests/test_fabrica_revision.py` exige que coincidan). ALTA y MEDIA bloquean hasta `cerrado`;
  sólo cierra OTRA revisión de la lista, posterior, sobre la versión corregida (otra firma), de
  un revisor que no es quien corrigió ni quien lo encontró. «Asumido» no cierra nada.
- `problemas_cuadros(datos, sha256)`: `cuadros.json`, el veredicto del agente con visión sobre
  los tres cuadros del video (armado, marcha, cierre) de ESE video (su sha256).
- `problemas_familia(registro, familia, slug, version, firma)` y `registrar`: D10, las dos
  primeras publicaciones de una familia las aprueba Mario (`familias.json` del repo privado).
"""

from __future__ import annotations

import re
import unicodedata

FORMATO = 1
#: Copias de `design/revision.py` (SEVERIDADES, ESTADOS_HALLAZGO, SEVERIDADES_QUE_BLOQUEAN,
#: CAMPOS_HALLAZGO, CAMPOS_REVISION).
SEVERIDADES = ("ALTA", "MEDIA", "BAJA")
BLOQUEAN = ("ALTA", "MEDIA")
ESTADOS = ("abierto", "corregido", "cerrado")
CAMPOS_HALLAZGO = ("pieza", "pregunta", "evidencia", "severidad")
CAMPOS_REVISION = ("id", "revisor", "firma", "fecha", "hallazgos")
#: Los tres momentos del video que revisa el agente con visión (D7), en orden.
MOMENTOS = ("armado", "marcha", "cierre")
VEREDICTOS = ("OK", "RECHAZADO")
#: Publicaciones aprobadas por Mario que hacen falta para que su familia ya no las pida (D10).
APROBADAS_MIN = 2
_ASUMIDO = re.compile(r"\basumid[oa]s?\b", re.IGNORECASE)


def _texto(v) -> bool:
    return isinstance(v, str) and bool(v.strip())


# ------------------------------------------------------------------ revisión de taller (D6)
def _revision_valida(r, i: int, ids: set) -> list[str]:
    donde = f"revisiones[{i}]"
    if not isinstance(r, dict):
        return [f"{donde}: debe ser un objeto con {', '.join(CAMPOS_REVISION)}"]
    out = [f"{donde}: falta «{c}»" for c in CAMPOS_REVISION if c not in r]
    out += [f"{donde}.{c}: debe ser texto no vacío" for c in ("id", "revisor", "firma", "fecha")
            if c in r and not _texto(r[c])]
    if "hallazgos" in r and not isinstance(r["hallazgos"], list):
        out.append(f"{donde}.hallazgos: debe ser una lista (vacía si no encontró nada)")
    if _texto(r.get("id")):
        if r["id"] in ids:
            out.append(f"{donde}.id: «{r['id']}» repetido (cada revisión tiene su id)")
        ids.add(r["id"])
    return out


def _cierre(h: dict, donde: str, i: int, revs: list[dict], por_id: dict) -> list[str]:
    """Problemas del cierre de un hallazgo ALTA/MEDIA marcado `cerrado`."""
    out = []
    origen = revs[i]
    if not _texto(h.get("corregido_por")):
        out.append(f"{donde}: falta «corregido_por» (quién corrigió el modelo): sin él no se "
                   "puede probar que no lo cerró el mismo")
    c = h.get("cerrado_por")
    if not isinstance(c, dict) or not _texto(c.get("revision")):
        return out + [f"{donde}: «cerrado_por» debe ser {{\"revision\": <id de la re-revisión>, "
                      "\"evidencia\": …}}: un hallazgo sólo lo cierra una re-revisión a ciegas"]
    if not _texto(c.get("evidencia")):
        out.append(f"{donde}: el cierre no trae «evidencia» (render o medida de la re-revisión)")
    if any(_ASUMIDO.search(str(x or "")) for x in (c.get("evidencia"), h.get("correccion"))):
        out.append(f"{donde}: «asumido» no cierra un hallazgo: corrige el modelo y que lo "
                   "verifique una re-revisión a ciegas")
    j = por_id.get(c["revision"])
    if j is None:
        return out + [f"{donde}: lo cierra «{c['revision']}», que no es ninguna revisión de "
                      "revision.json"]
    cierra = revs[j]
    if j <= i:
        out.append(f"{donde}: lo cierra «{c['revision']}», que no es POSTERIOR a la revisión que "
                   f"lo encontró («{origen.get('id')}»): ninguna revisión se cierra a sí misma")
    elif cierra.get("firma") == origen.get("firma"):
        out.append(f"{donde}: «{c['revision']}» revisó la misma firma ({origen.get('firma')}) que "
                   "lo encontró: la re-revisión es de la versión CORREGIDA")
    if cierra.get("revisor") == h.get("corregido_por"):
        out.append(f"{donde}: lo cierra «{cierra.get('revisor')}», el mismo que lo corrigió: la "
                   "re-revisión la hace otro agente, a ciegas")
    if j > i and cierra.get("revisor") == origen.get("revisor"):
        out.append(f"{donde}: lo cierra el mismo revisor que lo encontró "
                   f"(«{origen.get('revisor')}»): la re-revisión es con contexto fresco, a ciegas")
    return out


def _hallazgo(h, donde: str, i: int, revs: list[dict], por_id: dict) -> list[str]:
    if not isinstance(h, dict):
        return [f"{donde}: debe ser un objeto con {', '.join(CAMPOS_HALLAZGO)} y estado"]
    out = [f"{donde}: falta «{c}»" for c in (*CAMPOS_HALLAZGO, "estado") if c not in h]
    sev, estado = h.get("severidad"), h.get("estado")
    if "severidad" in h and sev not in SEVERIDADES:
        out.append(f"{donde}.severidad: {sev!r} (válidas: {', '.join(SEVERIDADES)})")
    if "estado" in h and estado not in ESTADOS:
        extra = (" — «asumido» no es un cierre: corrige el modelo y que lo verifique una "
                 "re-revisión a ciegas" if _ASUMIDO.search(str(estado)) else "")
        out.append(f"{donde}.estado: {estado!r} (válidos: {', '.join(ESTADOS)}){extra}")
    if sev not in BLOQUEAN or estado not in ESTADOS:
        return out
    pieza = f" «{h.get('pieza')}»" if h.get("pieza") else ""
    if estado != "cerrado":
        return out + [f"{donde}{pieza}: {sev} {estado}: bloquea hasta que una re-revisión a "
                      "ciegas de la versión corregida lo cierre"]
    return out + _cierre(h, f"{donde}{pieza}", i, revs, por_id)


def problemas_revision(datos, firma: str | None) -> list[str]:
    """Lo que impide publicar con este `revision.json` sobre el modelo de `firma`."""
    if datos is None:
        return ["no hay revision.json: el revisor de taller no revisó esta versión"]
    if not isinstance(datos, dict) or not isinstance(datos.get("revisiones"), list):
        return ["revision.json debe ser {\"formato\": 1, \"revisiones\": [...]} (formato en "
                "docs/revisor-de-taller.md)"]
    out = [] if datos.get("formato") == FORMATO else [
        f"revision.json: formato {datos.get('formato')!r} (se espera {FORMATO})"]
    revs = datos["revisiones"]
    if not revs:
        return out + ["revision.json no trae ninguna revisión"]
    ids: set = set()
    for i, r in enumerate(revs):
        out += _revision_valida(r, i, ids)
    if out:
        return out
    por_id = {r["id"]: i for i, r in enumerate(revs)}
    ultima = revs[-1]
    if not firma:
        out.append("no sé qué firma se publica (falta la firma de calidad.json)")
    elif ultima["firma"] != firma:
        out.append(f"la última revisión («{ultima['id']}») es de la firma {ultima['firma']} y lo "
                   f"que se publica es {firma}: el modelo cambió después; falta una re-revisión "
                   "a ciegas de ESTA versión")
    for i, r in enumerate(revs):
        for k, h in enumerate(r["hallazgos"]):
            out += _hallazgo(h, f"{r['id']}.hallazgos[{k}]", i, revs, por_id)
    return out


# ------------------------------------------------------------------ cuadros del video (D7)
def problemas_cuadros(datos, sha256: str | None) -> list[str]:
    """Lo que impide publicar con este `cuadros.json` para el video de `sha256`."""
    if datos is None:
        return ["no hay cuadros.json: nadie revisó los cuadros del video"]
    if not isinstance(datos, dict):
        return ["cuadros.json debe ser un objeto {video, cuadros, revisor, fecha}"]
    if not sha256:
        return ["no encuentro el video del paquete para compararlo con cuadros.json"]
    visto = (datos.get("video") or {}).get("sha256") if isinstance(datos.get("video"), dict) else None
    if visto != sha256:
        return [f"cuadros.json es de otro video (sha256 {str(visto)[:12]}…, el del paquete es "
                f"{sha256[:12]}…): sus veredictos no valen para éste"]
    out = []
    cuadros = {c.get("momento"): c for c in datos.get("cuadros") or [] if isinstance(c, dict)}
    for m in MOMENTOS:
        c = cuadros.get(m)
        if c is None:
            out.append(f"falta el cuadro «{m}»")
        elif c.get("veredicto") is None:
            out.append(f"el cuadro «{m}» ({c.get('archivo')}) no tiene veredicto")
        elif c.get("veredicto") not in VEREDICTOS:
            out.append(f"el cuadro «{m}»: veredicto {c.get('veredicto')!r} (válidos: "
                       f"{', '.join(VEREDICTOS)})")
        elif c["veredicto"] != "OK":
            out.append(f"el cuadro «{m}» fue RECHAZADO: {c.get('nota') or '(sin nota)'}")
    if not _texto(datos.get("revisor")):
        out.append("cuadros.json no dice quién revisó los cuadros («revisor»)")
    return out


# ------------------------------------------------------------------ familia nueva (D10)
def clave_familia(familia: str) -> str:
    """«Faja de banda» y «faja  de BANDA» son la misma familia."""
    plano = unicodedata.normalize("NFKD", familia or "").encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", plano.lower()).split())


def aprobadas(registro: dict | None, familia: str) -> list[dict]:
    fam = ((registro or {}).get("familias") or {}).get(clave_familia(familia)) or {}
    return [a for a in fam.get("aprobadas") or [] if isinstance(a, dict)]


def problemas_familia(registro: dict | None, familia, slug: str, version: str,
                      firma: str | None) -> list[str]:
    """Con < `APROBADAS_MIN` máquinas (slugs distintos) aprobadas de su familia, esta versión
    necesita su propia aprobación de Mario, sobre la misma firma."""
    if not _texto(familia):
        return ["la ficha (ficha.yaml) no declara su «familia» (p. ej. «faja de banda»)"]
    lista = aprobadas(registro, familia)
    if len({a.get("slug") for a in lista}) >= APROBADAS_MIN:
        return []
    if any(a.get("slug") == slug and a.get("version") == version and a.get("firma") == firma
           for a in lista):
        return []
    previas = [a for a in lista if a.get("slug") == slug and a.get("version") == version]
    otra = (f" (la aprobación de {slug} {version} era de la firma {previas[-1].get('firma')}: "
            "el modelo cambió)") if previas else ""
    return [f"la familia «{familia}» tiene {len({a.get('slug') for a in lista})} de "
            f"{APROBADAS_MIN} máquinas aprobadas: Mario mira esta versión y la aprueba con "
            f"`publicar.py aprobar --slug {slug} --version {version}`{otra}"]


def registrar(registro: dict | None, familia: str, *, slug: str, version: str, firma: str,
              por: str, fecha: str) -> dict:
    """El registro con la aprobación sumada (una por slug, versión y firma)."""
    reg = dict(registro or {})
    reg.setdefault("formato", FORMATO)
    familias = dict(reg.get("familias") or {})
    clave = clave_familia(familia)
    fam = dict(familias.get(clave) or {"nombre": familia.strip(), "aprobadas": []})
    lista = [a for a in fam.get("aprobadas") or []
             if not (a.get("slug") == slug and a.get("version") == version
                     and a.get("firma") == firma)]
    lista.append({"slug": slug, "version": version, "firma": firma, "por": por, "fecha": fecha})
    fam["aprobadas"] = lista
    familias[clave] = fam
    reg["familias"] = familias
    return reg
