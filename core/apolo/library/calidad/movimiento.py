"""`movimiento.coherente` (plan lo-fijo-que-gira-y-lo-que-cuelga, D1; ajustes D1a–D1d de su F0):
una unión RÍGIDA no une dos piezas que se mueven distinto. Puro: juzga lo que mide
`services/calidad_movimiento.py`.

El defecto: en la lavadora de bandejas la junta del eje motriz tenía como hija `fija` a la
chumacera del lado opuesto, empernada a su ménsula, y la carcasa del motorreductor iba arrastrada
con el eje aunque estaba empernada a su brazo de reacción quieto. Al simular giraban motor y
chumacera; en otra ronda, ocho resortes a gas modelados rígidos y quietos estaban empernados a la
puerta que abre. El modelo dice que gira algo atornillado a lo que no gira.

Cada unión perno, soldadura o pegado entre piezas que mueven juntas de movimiento distintas
(giratoria, continua, prismática; un `contacto` desliza y no se juzga), EN ORDEN:

1. **Eje de la junta** (`calidad_ejes_giro`): el perno o pasador que es el eje une sus dos
   cuerpos: es el pivote → OK.
2. **Bisagra** (D1b): las DOS piezas tienen una cara cilíndrica coaxial (± 1 mm) con la junta (las
   palas de una bisagra, el barril y su soporte) → OK. El pivote que CIERRA un lazo declarado con
   restricciones (`distancia` + `punto_coincidente`, D4 de plegables-en-la-puerta: el brazo del
   compás y el buje del tablero) cuenta como una junta más: OK si el lazo cierra en diseño y en
   cada pose de prueba (residuo ≤ `RESIDUO_LAZO_MM`), su `axis` está declarado y cierra sobre la
   pieza raíz; si no, SIN_EVALUAR con el porqué, nunca OK.
3. **Alojamiento arrastrado** (D1d): la pieza que se mueve con la junta es coaxial con ella y la
   otra no se mueve (la chumacera hija del eje empernada a su ménsula, la carcasa del motor) →
   FALLA, aunque la pose no la delate (una brida empernada cara a cara gira en su plano sin
   separarse ni solaparse).
4. **Prueba de pose relativa** (D1a): con cada junta distinta movida 3° o 3 mm, la distancia no
   crece más de 0,1 mm sobre la de diseño y el volumen común no crece más de 5 mm³ → OK (giran o
   deslizan una sobre otra). Sin medida → SIN_EVALUAR.
5. Si la pose las separa o las solapa, en una junta de SERVICIO (D1c: sin motor, cilindro,
   resorte ni escenario, `calidad_juntas`) es AVISO justificable cuando la pose sólo las SEPARA
   (el perno se quita para abrir o retirar, como el del recipiente de una mezcladora, o cierra un
   lazo que la FK no representa, como el compás de una mesa plegable) o cuando la pieza QUIETA es
   la coaxial (la bisagra de una pieza). Lo demás FALLA: una junta accionada (el motor arrancaría
   la unión) o una pieza que la pose mete en la otra (el resorte a gas quieto empernado a la
   puerta que abre: la puerta entra 11 cm³ en él al girar 3°).

Corregir es corregir la junta: sacar la pieza de la cadena (`fija` o `arrastrar`), declararla hija
de lo que la mueve, o modelar el pivote. No agrega piezas. Un AVISO se corrige o se justifica por
escrito (`justificadas.py`, regla `REGLA_AVISO` y la pieza), nunca se calla.
"""

from __future__ import annotations

from .entrada import Entrada, hay
from .item import FALLA, OK, SIN_EVALUAR, recortar
from .justificadas import citar, del_aviso

NORMA = ("criterio de diseño (D1 de lo-fijo-que-gira-y-lo-que-cuelga: lo que el modelo mueve "
         "es lo que se mueve en el taller)")
#: La regla que se justifica por escrito (`justificadas`): el texto EXACTO de la evidencia.
REGLA_AVISO = "unión rígida entre piezas que se mueven distinto"
COMO = ("corrige la junta: saca la pieza de lo que mueve la junta (su `fija` o el `arrastrar` "
        "que la arrastra), hazla hija de lo que de verdad la mueve o modela el pivote con su eje; "
        "si cierra un lazo, declara su pivote con add_constraint (`distancia` + "
        "`punto_coincidente` con su `axis`, cerrando en la pieza raíz); si la unión se quita "
        f"para mover (servicio), justifícalo por escrito (regla «{REGLA_AVISO}» y la pieza)")
#: Lo que `solve_constraints` puede dejar sin cerrar un lazo para que la pose valga (D4 de
#: plegables-en-la-puerta; la F0 midió ≤ 0,065 mm en el compás de la mesa de 1,8 m).
RESIDUO_LAZO_MM = 0.5


def _sin_eje(c: dict) -> tuple[str, str]:
    """(estado, motivo) del caso sin la excepción del eje. Estado OK | FALLA | SIN_EVALUAR |
    «aviso»."""
    juntas = ", ".join(c.get("juntas") or [])
    lazo = c.get("lazo")
    if lazo:  # el par se une en el pivote que cierra un lazo (D4)
        if lazo.get("estado") == OK:
            return OK, (f"bisagra del lazo: las dos piezas son coaxiales con el pivote "
                        f"{lazo['pivote']} que cierra el lazo y el lazo cierra en cada pose")
        return SIN_EVALUAR, f"pivote del lazo {lazo['pivote']}: {lazo.get('motivo')}"
    mueve, quieta = c.get("coaxial_mueve") or [], c.get("coaxial_quieta") or []
    if mueve and quieta:
        return OK, f"bisagra: las dos piezas son coaxiales con {juntas}"
    if mueve and c.get("quietas"):  # la que gira es coaxial; la otra no se mueve
        return FALLA, (f"alojamiento arrastrado: {mueve[0]} gira con {juntas} (es coaxial con ella) "
                       "y está unida rígida a una pieza que no se mueve")
    pose = c.get("pose")
    if pose is None:
        return SIN_EVALUAR, "no se pudo posar el par para la prueba de pose"
    if pose.get("sigue"):
        return OK, f"en pose ({juntas}) se siguen tocando sin solaparse más: giran una sobre otra"
    mal = next(p for p in pose["poses"] if not p["sigue"])
    medida = (f"con {mal['junta']} = {mal['valor']:g} la distancia pasa de "
              f"{pose['dist_diseno_mm']:g} a {mal['dist_mm']:g} mm y el volumen común de "
              f"{pose['comun_diseno_mm3']:g} a {mal['comun_mm3']} mm³")
    solapa = any(p.get("solapa") for p in pose["poses"])
    if c.get("servicio") and (quieta or not solapa):
        que = ("la bisagra está en la pieza quieta" if quieta else
               "la pose sólo las separa: la unión se quita para moverla o cierra un lazo")
        return "aviso", f"junta de servicio y {que} ({medida})"
    return FALLA, f"una pieza unida rígida a lo que mueve {juntas}: {medida}"


def resuelto_sin_eje(c: dict) -> bool:
    """¿El caso sale OK sin mirar el eje? (el servicio mide el eje sólo si hace falta)."""
    return _sin_eje(c)[0] == OK


def juzgar(c: dict) -> tuple[str, str]:
    if c.get("eje"):
        return OK, f"el perno o pasador es el eje de {c['eje']}: es el pivote"
    return _sin_eje(c)


def _texto(c: dict, motivo: str) -> str:
    return (f"{', '.join(c['uniones'])}: {c.get('nombre_a') or c['a']} ({c['a']}) ↔ "
            f"{c.get('nombre_b') or c['b']} ({c['b']}): {motivo}")


def coherente(ins: dict) -> dict:
    """El control del ítem: `ins["movimiento"]` = {juntas: {tipo: n}, casos: [{a, b, nombre_a,
    nombre_b, uniones, tipos, par_de_junta, juntas, quietas, coaxial_mueve, coaxial_quieta,
    servicio, pose: {dist_diseno_mm, comun_diseno_mm3, poses: [{junta, valor, dist_mm,
    comun_mm3, sigue, solapa}], sigue} | None, eje, lazo?: {pivote, estado, motivo, …}}],
    lazos?: [{nombre, estado, motivo?, motores, poses}]} (None: no se midió);
    `ins["justificadas"]` = el metadato."""
    datos = ins.get("movimiento")
    if datos is None or datos.get("error"):
        return {"estado": SIN_EVALUAR, "detalle": "no se midieron las uniones entre juntas"
                + (f" ({datos['error']})" if datos else "")}
    filas, malas, avisos, sin_medir, js_usadas = [], [], [], [], []
    for c in datos.get("casos") or []:
        estado, motivo = juzgar(c)
        if estado == "aviso":
            js = del_aviso(REGLA_AVISO, [c["a"], c["b"]], ins.get("justificadas"))
            if js:
                js_usadas += js
                estado = OK
            else:
                avisos.append((c, motivo))
        elif estado == FALLA:
            malas.append((c, motivo))
        elif estado == SIN_EVALUAR:
            sin_medir.append((c, motivo))
        filas.append({k: c.get(k) for k in ("uniones", "a", "b", "juntas")}
                     | {"estado": estado, "motivo": motivo})
    rec = recortar(sorted(filas, key=lambda f: f["estado"] == OK))  # lo malo, primero
    ev = {"juntas": datos.get("juntas") or {}, "uniones_entre_juntas": len(filas),
          "casos": rec["casos"], **({"casos_omitidos": rec["casos_omitidos"]}
                                    if "casos_omitidos" in rec else {})}
    if datos.get("lazos"):
        ev["lazos"] = datos["lazos"]
    if avisos:
        ev["avisos"] = [{"regla": REGLA_AVISO, "piezas": [c["a"], c["b"]]} for c, _m in avisos[:20]]
    if js_usadas:
        ev["justificadas"] = citar(js_usadas)
    if malas:
        partes = [_texto(c, m) for c, m in malas[:4]]
        resto = f" (+{len(malas) - 4} más en la evidencia)" if len(malas) > 4 else ""
        return {"estado": FALLA, "evidencia": ev,
                "piezas": list(dict.fromkeys(p for c, _m in malas for p in (c["a"], c["b"])))[:40],
                "detalle": f"{len(malas)} unión(es) rígida(s) entre piezas que se mueven distinto: "
                           f"{'; '.join(partes)}{resto}. {COMO[0].upper()}{COMO[1:]}"}
    if avisos or sin_medir:
        partes = [_texto(c, m) for c, m in (avisos + sin_medir)[:4]]
        return {"estado": SIN_EVALUAR, "evidencia": ev,
                "piezas": list(dict.fromkeys(p for c, _m in avisos + sin_medir
                                             for p in (c["a"], c["b"])))[:40],
                "detalle": f"{len(avisos)} aviso(s) y {len(sin_medir)} sin medir: "
                           f"{'; '.join(partes)}. {COMO[0].upper()}{COMO[1:]}"}
    n = sum((datos.get("juntas") or {}).values())
    return {"estado": OK, "evidencia": ev,
            "detalle": (f"{len(filas)} unión(es) rígida(s) entre juntas, todas coherentes"
                        if filas else f"{n} junta(s) de movimiento y ninguna unión rígida entre "
                                      "piezas que se mueven distinto")}


ENTRADA = Entrada(
    "movimiento.coherente",
    "Ninguna unión rígida une dos piezas que se mueven distinto",
    "el modelo hace girar algo que está atornillado a lo que no gira (una chumacera hija del eje "
    "empernada a su ménsula, un resorte quieto empernado a la puerta que abre): la simulación, el "
    "video y los choques en pose mienten y el taller no sabe qué se mueve",
    NORMA, "función",
    hay("juntas_de_movimiento", "sin juntas que muevan piezas (giratoria, continua o prismática)"),
    coherente, "juntas_de_movimiento")
