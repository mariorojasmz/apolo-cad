"""La posición de USO se traba (plan plegables-en-la-puerta, F3: D5 y D6 con la Bitácora § F0).
Puro: valida lo que declara el fotograma de uso y juzga lo que mide
`services/calidad_trabas.py`.

El defecto: el tirante con gancho de la escalera de 3 peldaños salía «levantando el tirante unos
21 mm […] No tiene seguro ni traba»; su codo quedaba «alineado con los dos pivotes […] no hay
sobre-centro». Los modeladores que lo resolvieron (sobre-centro de 2° con pasador tope a 0,12 mm,
pletina tope doblada 2,3°, calzo de apertura y el peso de la persona) no tenían ítem que lo
pidiera ni lo midiera.

**Lo que se declara** (`set_motion`, en el fotograma `posicion: "uso"`, el único que lo acepta):

    "trabas": [{"grado": junta, "sentido": "+" | "-", "tipo": ..., "piezas": [ids],
                "nota": texto, "junta"?: junta}]

- `grado`: el GRADO DE LIBERTAD que la traba bloquea, nombrado por su junta MOTORA (la que
  cambia entre uso y guardado y ninguna restricción de lazo resuelve: la escalera tiene 5 juntas
  y 1 grado, la mesa 10 y 2). `junta` sola vale por `grado`.
- `sentido`: el sentido del GRADO que se bloquea («+» = su valor crece).
- `junta` (con `grado`): dónde actúa la traba si no es en la junta del grado: la rodilla de un
  sobre-centro, o la junta que un `tope` frena (su sentido sale de mover el grado con el lazo
  resuelto).
- `piezas`: las que hacen la traba (la pieza tope, el retén y lo que retiene).

**Cada grado que pliega, en sus DOS sentidos**, tiene una traba que la medida confirma; si no,
FALLA. Las juntas que no cambian entre uso y guardado no cuentan. Cómo se mide cada tipo (desde
la pose de uso, con los lazos resueltos):

- `tope`: con la junta movida `PASO` (3° o 3 mm, la prueba de pose de `calidad_movimiento`) en
  ese sentido, sin resolver el lazo, el volumen común de una pieza de la traba con otra que la
  junta mueve respecto de ella crece más que `TOL_VOL_MM3` **y** su distancia en uso es ≤
  `TOPE_DIST_MM` (el pasador de la escalera, a 0,12 mm, sólo llegaba a 2× `TOL_VOL_MM3`: un
  tope a 2 mm que la prueba aún alcanza no traba, deja juego);
- `sobre_centro` (D6): en cada lazo del grado (o el de la rodilla `junta`), 180° − ∠PKQ ≥
  `SOBRE_CENTRO_MIN_DEG` con P, K los orígenes posados de la junta del brazo y de la rodilla y Q
  el punto del `punto_coincidente` (F2); la rodilla pasa la recta PQ al plegar (en guardado está
  del otro lado: eso es «sobre» el centro) y su tope existe, medido como `tope` con la rodilla
  movida en el sentido que la dobla más. Sólo traba el sentido en que el grado PLIEGA;
- `tirante`: con el grado movido `PASO` en ese sentido, el lazo deja de cerrar (residuo >
  `RESIDUO_LAZO_MM`): la apertura de la escalera la limita el tirante, una prueba de tope no la ve;
- `retenida` (pasador, gancho, cerrojo): entre sus piezas hay un retén reconocido por su ROL
  (`ejes_giro.tipo_reten`: pasador de aletas, clip R, anillo) que toca (≤ `TOPE_DIST_MM`) otra
  pieza de la traba; un gancho sin retén FALLA (la escalera de 3);
- `peso` (la persona sentada cierra la tijera): AVISO que se justifica por escrito (regla
  `REGLA_PESO`), nunca OK solo.
"""

from __future__ import annotations

from .entrada import Entrada, hecho
from .item import FALLA, OK, SIN_EVALUAR, recortar
from .justificadas import citar, del_aviso
from .movimiento import RESIDUO_LAZO_MM

TIPOS = ("tope", "sobre_centro", "tirante", "retenida", "peso")
SENTIDOS = ("+", "-")
_CLAVES = ("grado", "junta", "sentido", "tipo", "piezas", "nota")
#: Lo que una pieza de la traba puede distar de lo que frena en la pose de uso (mm): más es juego.
TOPE_DIST_MM = 0.5
#: Lo que tiene que crecer el volumen común al mover la junta (mm³): el de la prueba de pose
#: (`services/calidad_movimiento.TOL_VOL_MM3`, el mismo número: lo vigila un test).
TOL_VOL_MM3 = 5.0
#: D6: el sobre-centro mínimo entre brazos, 180° − ∠PKQ. CRITERIO DE DISEÑO, no norma: EN 131,
#: EN 1730, EN 12521 y EN 15372 no publican una cifra (F0 § 2.5); los dos modeladores que lo
#: resolvieron usaron 2° y 2,3° y el revisor pidió «2–3°».
SOBRE_CENTRO_MIN_DEG = 2.0
#: La regla que se justifica por escrito (`justificadas`) para una traba por el peso.
REGLA_PESO = "traba por el peso de la persona"
NORMA = ("criterio de diseño (plan plegables-en-la-puerta D5/D6: la posición de uso se traba en "
         "los dos sentidos de cada grado que pliega; sobre-centro ≥ 2° entre brazos)")
COMO = ("declara en el fotograma \"posicion\": \"uso\" sus \"trabas\": [{\"grado\": junta, "
        "\"sentido\": \"+\" | \"-\", \"tipo\": tope | sobre_centro | tirante | retenida | peso, "
        "\"piezas\": [ids], \"nota\": \"…\"}], una por sentido de cada grado que pliega, y modela "
        "lo que traba: la pieza tope a ≤ 0,5 mm, la rodilla ≥ 2° pasada de la recta de sus "
        "pivotes, el lazo del tirante (add_constraint) o el retén del pasador o del gancho")


# ------------------------------------------------------------------ lo que se declara
def validar_trabas(valor, juntas: dict, escena) -> list[dict]:
    """Las trabas del fotograma de uso validadas; `ValueError` con la corrección."""
    if not isinstance(valor, list):
        raise ValueError("'trabas' es una lista de {grado, sentido, tipo, piezas, nota}")
    out = []
    for k, t in enumerate(valor):
        donde = f"trabas[{k}]"
        if not isinstance(t, dict):
            raise ValueError(f"{donde}: cada traba es un objeto {{grado, sentido, tipo, piezas, "
                             "nota}")
        extra = sorted(set(map(str, t)) - set(_CLAVES))
        if extra:
            raise ValueError(f"{donde}: clave(s) no reconocida(s) {extra}; válidas: "
                             + ", ".join(_CLAVES))
        limpio: dict = {}
        for clave in ("grado", "junta"):
            if t.get(clave) is None:
                continue
            j = str(t[clave]).strip()
            if j not in juntas:
                raise ValueError(f"{donde}.{clave}: la junta «{j}» no existe (válidas: "
                                 f"{', '.join(sorted(juntas)) or 'ninguna declarada'})")
            limpio[clave] = j
        if not limpio:
            raise ValueError(f"{donde}: di qué grado de libertad traba: \"grado\" (su junta "
                             "motora)")
        sentido = str(t.get("sentido", "")).strip()
        if sentido not in SENTIDOS:
            raise ValueError(f"{donde}.sentido: \"+\" o \"-\" (el sentido del grado que se "
                             f"bloquea), no «{t.get('sentido')}»")
        tipo = str(t.get("tipo", "")).strip().lower()
        if tipo not in TIPOS:
            raise ValueError(f"{donde}.tipo: {' | '.join(TIPOS)}, no «{t.get('tipo')}»")
        piezas = t.get("piezas") or []
        if not isinstance(piezas, list) or not all(isinstance(p, str) for p in piezas):
            raise ValueError(f"{donde}.piezas: lista de ids de pieza")
        faltan = [p for p in piezas if p not in escena]
        if faltan:
            raise ValueError(f"{donde}.piezas: no existen {', '.join(faltan)}")
        if tipo in ("tope", "sobre_centro", "retenida") and not piezas:
            raise ValueError(f"{donde}.piezas: un «{tipo}» nombra sus piezas (la pieza tope; el "
                             "retén y lo que retiene)")
        nota = t.get("nota")
        if nota is not None and not isinstance(nota, str):
            raise ValueError(f"{donde}.nota: texto")
        out.append({**limpio, "sentido": sentido, "tipo": tipo, "piezas": list(piezas),
                     **({"nota": nota.strip()} if nota and nota.strip() else {})})
    return out


# ------------------------------------------------------------------ cómo se juzga cada tipo
def _tope(m: dict | None) -> tuple[str, str]:
    """(estado, motivo) de una prueba de tope: {junta, valor, pares: [{a, b, dist_mm,
    comun_uso_mm3, comun_prueba_mm3}]} | {error}."""
    if not m or m.get("error"):
        return SIN_EVALUAR, f"no se midió el tope ({(m or {}).get('error', 'sin medida')})"
    pares = m.get("pares") or []
    if not pares:
        return FALLA, (f"con {m['junta']} = {m['valor']:+g} ninguna pieza de la traba toca algo que "
                       "esa junta mueva respecto de ella: no hay tope")
    validos = [p for p in pares if p.get("comun_prueba_mm3") is not None
               and p.get("comun_uso_mm3") is not None]
    if not validos:
        return SIN_EVALUAR, "OCCT no midió el volumen común de la prueba del tope"
    for p in validos:
        p["crece_mm3"] = round(p["comun_prueba_mm3"] - p["comun_uso_mm3"], 1)
    bloquea = [p for p in validos if p["crece_mm3"] > TOL_VOL_MM3]
    cerca = [p for p in bloquea if p["dist_mm"] <= TOPE_DIST_MM]
    if cerca:
        p = max(cerca, key=lambda x: x["crece_mm3"])
        return OK, (f"tope {p['a']} ↔ {p['b']} a {p['dist_mm']:g} mm: con {m['junta']} = "
                    f"{m['valor']:+g} el volumen común crece {p['crece_mm3']:g} mm³")
    if bloquea:
        p = min(bloquea, key=lambda x: x["dist_mm"])
        return FALLA, (f"el tope {p['a']} ↔ {p['b']} está a {p['dist_mm']:g} mm en uso (> "
                       f"{TOPE_DIST_MM:g}): deja juego, no traba")
    p = max(validos, key=lambda x: x["crece_mm3"])
    return FALLA, (f"con {m['junta']} = {m['valor']:+g} ninguna pieza de la traba bloquea (el "
                   f"volumen común {p['a']} ↔ {p['b']} crece {p['crece_mm3']:g} mm³ ≤ "
                   f"{TOL_VOL_MM3:g}): el tope no está en ese sentido")


def _sobre_centro(t: dict) -> tuple[str, str]:
    m = t.get("medida") or {}
    if t.get("pliega") and t["sentido"] != t["pliega"]:
        return FALLA, (f"un sobre-centro traba el sentido en que el grado PLIEGA ({t['grado']} "
                       f"pliega hacia «{t['pliega']}»); el otro lo traba un tope o un tirante")
    lazos = m.get("lazos") or []
    if not lazos:
        return FALLA, (f"ningún lazo declarado mueve {t['grado']}: el sobre-centro se mide en la "
                       "rodilla del lazo (add_constraint `distancia` + `punto_coincidente`)")
    for z in lazos:
        if z.get("error"):
            return SIN_EVALUAR, f"lazo {z['pivote']}: {z['error']}"
        if z["residuo_uso_mm"] > RESIDUO_LAZO_MM:
            return SIN_EVALUAR, (f"el lazo {z['pivote']} no cierra en uso (residuo "
                                 f"{z['residuo_uso_mm']:g} mm)")
        if z["angulo_deg"] < SOBRE_CENTRO_MIN_DEG:
            return FALLA, (f"la rodilla {z['rodilla']} del lazo {z['pivote']} queda a "
                           f"{z['angulo_deg']:g}° de la recta de sus pivotes (180° − ∠PKQ); el "
                           f"sobre-centro pide ≥ {SOBRE_CENTRO_MIN_DEG:g}°")
        if z.get("lado_guardado") is None:
            return SIN_EVALUAR, f"no se posó el guardado del lazo {z['pivote']}"
        if z["lado_guardado"] == z["lado_uso"]:
            return FALLA, (f"la rodilla {z['rodilla']} no pasa la recta de sus pivotes al plegar "
                           "(en guardado queda del mismo lado): no está sobre el centro, la carga "
                           "la pliega")
        e, mot = _tope(z.get("tope"))
        if e != OK:
            return e, f"tope de la rodilla {z['rodilla']}: {mot}"
    z = min(lazos, key=lambda x: x["angulo_deg"])
    return OK, (f"sobre-centro {z['angulo_deg']:g}° en la rodilla {z['rodilla']} "
                f"({len(lazos)} lazo(s)), con su tope")


def _tirante(m: dict) -> tuple[str, str]:
    if not m.get("lazos"):
        return FALLA, ("ningún lazo declarado mueve el grado: el tirante se mide en su lazo "
                       "(add_constraint `distancia` + `punto_coincidente`)")
    if m.get("error"):
        return SIN_EVALUAR, m["error"]
    if m["residuo_uso_mm"] > RESIDUO_LAZO_MM:
        return SIN_EVALUAR, f"el lazo no cierra en uso (residuo {m['residuo_uso_mm']:g} mm)"
    if m["residuo_prueba_mm"] > RESIDUO_LAZO_MM:
        hasta = m.get("hasta", m["valor"])
        return OK, (f"moviendo {m['grado']} hacia {m['valor']:+g} el lazo deja de cerrar a "
                    f"{hasta:+g} (residuo {m['residuo_prueba_mm']:g} mm): el tirante lo limita")
    return FALLA, (f"con {m['grado']} = {m['valor']:+g} el lazo sigue cerrando (residuo "
                   f"{m['residuo_prueba_mm']:g} mm): el tirante no limita ese sentido")


def _retenida(m: dict) -> tuple[str, str]:
    retenes = m.get("retenes") or []
    if not retenes:
        return FALLA, ("sin retén: ninguna pieza de la traba es un pasador de aletas, clip R o "
                       "anillo de retención (un gancho o un pasador suelto se sale)")
    if not m.get("retenidas"):
        return FALLA, "la traba nombra sólo el retén: suma la pieza que retiene (el pasador)"
    toca = [r for r in retenes if r.get("dist_mm") is not None and r["dist_mm"] <= TOPE_DIST_MM]
    if not toca:
        r = min(retenes, key=lambda x: x.get("dist_mm") if x.get("dist_mm") is not None else 1e9)
        return FALLA, (f"el retén {r['fid']} no toca lo que retiene ({r.get('dist_mm')} mm): no "
                       "retiene")
    return OK, f"{toca[0]['tipo']} {toca[0]['fid']} retiene {', '.join(m['retenidas'][:3])}"


def juzgar(t: dict) -> tuple[str, str]:
    """(estado, motivo) de una traba medida: OK | FALLA | SIN_EVALUAR | «aviso»."""
    if t.get("faltan"):
        return FALLA, f"piezas que ya no existen: {', '.join(t['faltan'])}"
    m = t.get("medida") or {}
    if m.get("error") and t["tipo"] not in ("sobre_centro", "tirante"):
        return SIN_EVALUAR, f"no se midió ({m['error']})"
    if t["tipo"] == "tope":
        return _tope(m)
    if t["tipo"] == "sobre_centro":
        return _sobre_centro(t)
    if t["tipo"] == "tirante":
        return _tirante(m)
    if t["tipo"] == "retenida":
        return _retenida(m)
    return "aviso", "la traba es el peso de la persona: no se mide"


# ------------------------------------------------------------------ el ítem
_PEOR_A_MEJOR = {FALLA: 0, SIN_EVALUAR: 1, "aviso": 2, OK: 3}


def traba(ins: dict) -> dict:
    """El control de `plegado.traba`. `ins["trabas"]` = {estudio, grados: [{grado, pliega,
    lazos}], trabas: [{indice, grado, sentido, tipo, piezas, junta?, nota?, pliega?,
    ignorada?, faltan?, medida}]} | {error} | None; `ins["justificadas"]` = el metadato."""
    datos = ins.get("trabas")
    if datos is None or datos.get("error"):
        return {"estado": SIN_EVALUAR, "detalle": "no se midieron las trabas del uso"
                + (f" ({datos['error']})" if datos else "")}
    if not datos.get("estudio"):
        return {"estado": SIN_EVALUAR, "detalle": "sin posición de uso válida que trabar (ver "
                                                  "plegado.posiciones)"}
    filas, js_usadas, avisos = [], [], []
    for t in datos.get("trabas") or []:
        if t.get("ignorada"):
            filas.append({**_fila(t), "estado": "ignorada", "motivo": t["ignorada"]})
            continue
        estado, motivo = juzgar(t)
        if estado == "aviso":
            js = del_aviso(REGLA_PESO, t.get("piezas") or [], ins.get("justificadas"))
            if js:
                js_usadas += js
                estado, motivo = OK, f"{motivo}; justificada por escrito"
            else:
                avisos.append({"regla": REGLA_PESO, "piezas": t.get("piezas") or []})
        filas.append({**_fila(t), "estado": estado, "motivo": motivo})
    sentidos = []
    for g in datos.get("grados") or []:
        for s in SENTIDOS:
            mias = [f for f in filas if f.get("grado") == g["grado"] and f["sentido"] == s
                    and f["estado"] != "ignorada"]
            if not mias:
                sentidos.append({"grado": g["grado"], "sentido": s, "estado": FALLA,
                                 "motivo": "sin traba declarada"})
                continue
            mejor = max(mias, key=lambda f: _PEOR_A_MEJOR[f["estado"]])
            sentidos.append({"grado": g["grado"], "sentido": s, "estado": mejor["estado"],
                             "motivo": f"{mejor['tipo']}: {mejor['motivo']}"})
    rec = recortar(filas)
    ev = {"estudio": datos["estudio"], "grados": datos.get("grados") or [],
          "sentidos": sentidos, "trabas": rec["casos"],
          **({"trabas_omitidas": rec["casos_omitidos"]} if "casos_omitidos" in rec else {}),
          "criterio": {"tope_dist_mm": TOPE_DIST_MM, "tol_vol_mm3": TOL_VOL_MM3,
                       "sobre_centro_min_deg": SOBRE_CENTRO_MIN_DEG,
                       "residuo_lazo_mm": RESIDUO_LAZO_MM}}
    if avisos:
        ev["avisos"] = avisos[:20]
    if js_usadas:
        ev["justificadas"] = citar(js_usadas)
    if not sentidos:
        return {"estado": SIN_EVALUAR, "evidencia": ev,
                "detalle": "ninguna junta motora cambia entre uso y guardado: no hay grado que "
                           "trabar (ver plegado.posiciones)"}
    malos = [s for s in sentidos if s["estado"] == FALLA]
    dudosos = [s for s in sentidos if s["estado"] in (SIN_EVALUAR, "aviso")]
    if malos or dudosos:
        partes = [f"{s['grado']} «{s['sentido']}»: {s['motivo']}" for s in (malos + dudosos)[:4]]
        resto = (f" (+{len(malos + dudosos) - 4} más en la evidencia)"
                 if len(malos + dudosos) > 4 else "")
        if malos:
            return {"estado": FALLA, "evidencia": ev,
                    "detalle": f"{len(malos)} sentido(s) de plegado sin traba que la medida "
                               f"confirme: {'; '.join(partes)}{resto}. "
                               f"{COMO[0].upper()}{COMO[1:]}"}
        return {"estado": SIN_EVALUAR, "evidencia": ev,
                "detalle": f"{len(dudosos)} sentido(s) sin confirmar: {'; '.join(partes)}{resto}. "
                           f"Una traba por el peso se justifica por escrito (regla «{REGLA_PESO}» "
                           "y sus piezas)"}
    return {"estado": OK, "evidencia": ev,
            "detalle": f"{len(sentidos) // 2} grado(s) de libertad trabados en uso en sus dos "
                       f"sentidos ({', '.join(sorted({s['grado'] for s in sentidos})[:6])})"}


def _fila(t: dict) -> dict:
    return {k: t[k] for k in ("indice", "grado", "junta", "sentido", "tipo", "piezas", "medida")
            if t.get(k) is not None}


ENTRADA = Entrada(
    "plegado.traba",
    "La posición de uso del plegable se traba en los dos sentidos de cada grado que pliega",
    "el producto plegable se cierra solo en uso (el gancho sin seguro sale, la rodilla alineada "
    "con sus pivotes se dobla con la carga) o se abre de más",
    NORMA, "función",
    hecho("plegable", "el encargo no dice que el producto se pliegue (requisito plegable)"),
    traba)
