"""Lo comprado que entrega una función no SOBRA (registro v42, fix de la mesa de bolas).

La mesa de bolas de transferencia daba en v41 «96 pieza(s) sobran» de 212 candidatas: la rejilla
de bolas (un `pattern_group` agregado por una ronda de corrección) se probaba pieza por pieza y,
como ningún control de la puerta mide «transferir la caja», sin cada bola nada empeoraba. En v32 la
bola salía de las candidatas por accidente (la «tuerca» de su descripción la hacía tornillería, y
la v34 la volvió candidata con la tornillería por ROL). Ahora la regla es explícita y general
(`calidad_sobrantes_candidatas.entregan_funcion`): el componente COMPRADO que es la solución de una
función declarada (o recibe la carga útil) no es candidato, y las copias de su patrón siguen a la
raíz. Lo fabricado a medida y las guardas se siguen probando: la guarda duplicada sigue FALLA.
"""

from __future__ import annotations

from apolo.doc import Document
from apolo.library.calidad.item import FALLA, OK
from apolo.library.calidad.sobrantes import sin_sobrantes
from apolo.library.lints import es_nombre_de_tornilleria
from apolo.services import calidad_sobrantes as CS
from apolo.services import puerta_publicacion as pp
from apolo.services.raices import fuentes_de_copias, raiz_de

BOLA = ("Bola de transferencia (compra, 25 kg) — bola Ø25,4 acero templado, carcasa Ø38×22 "
        "acero zincado, esp. M8×15 ISO 261 con tuerca M8 ISO 4032")
_DESCARTADAS = [{"solucion": "Rodillos locos", "motivo": "giran en una sola dirección"}]


def _caja(d, nombre, w, dp, h, x, y, z) -> str:
    return d.execute("create_box", {"name": nombre, "width": w, "depth": dp, "height": h,
                                    "position": {"x": x, "y": y, "z": z}})


def _mesa() -> tuple[Document, str, str]:
    """Plancha anclada + una bola comprada atornillada; la primera corrida de la puerta; luego la
    corrección agrega la rejilla 3×3 (`pattern_group`) atornillada a la plancha."""
    d = Document("mesa de bolas")
    plancha = _caja(d, "Plancha porta-bolas", 400, 400, 3, 0, 0, 1.5)
    d.execute("ground", {"name": "piso", "feature": plancha})
    bola = _caja(d, BOLA, 30, 30, 20, -100, -100, 13)
    d.execute("fasten", {"name": "bola", "a": bola, "b": plancha, "kind": "perno", "size": "M8",
                         "qty": 1})
    assert CS.marcar_primera_corrida(d)
    rejilla = d.execute("pattern_group", {"source": bola, "count": 3, "spacing": {"x": 100},
                                          "count2": 3, "spacing2": {"y": 100}})
    copias = sorted(f for f, x in d.scene.items() if x.command_id == rejilla)
    assert len(copias) == 8
    d.execute("fasten", {"name": "rejilla", "a": "+".join(copias), "b": plancha,
                         "kind": "perno", "size": "M8", "qty": 1})
    return d, bola, plancha


def _sobrantes(d) -> tuple[dict, dict]:
    from apolo.services.calidad_seguridad import controles_f3

    ctx = pp.Contexto()
    controles_f3(d, contexto=ctx, electrico=False)
    s = CS.sobrantes(d, ctx)
    return s, sin_sobrantes({"sobrantes": s, "justificadas": []})


def _funcion(d, piezas, funcion="Transferencia omnidireccional de la caja"):
    pp.poner_funciones(d, [{"funcion": funcion, "solucion": "Bolas de transferencia M8",
                            "descartadas": _DESCARTADAS, "piezas": piezas}])


def test_la_bola_ya_no_es_tornilleria_por_la_tuerca_de_su_descripcion():
    """La causa de la regresión: desde la v34 (tornillería por ROL) la bola es una bola."""
    assert not es_nombre_de_tornilleria(BOLA)


def test_la_copia_de_un_patron_sigue_a_su_raiz():
    d, bola, _ = _mesa()
    fuentes = fuentes_de_copias(d)
    copias = [f for f in d.scene if f.startswith(d.commands[-2]["id"] + "_")]
    assert copias and all(fuentes[c] == bola and raiz_de(c, fuentes) == bola for c in copias)
    lineal = d.execute("pattern_linear", {"feature": copias[0], "count": 2,
                                          "spacing": {"x": 0, "y": 0, "z": 50}})
    assert raiz_de(f"{lineal}_1", fuentes_de_copias(d)) == bola  # el patrón de una copia
    assert raiz_de(bola, fuentes) == bola


def test_la_rejilla_comprada_que_entrega_la_funcion_no_sobra():
    d, bola, _ = _mesa()
    s, it = _sobrantes(d)  # sin la función declarada: la regresión de v41
    assert it["estado"] == FALLA and len(it["piezas"]) == 8, it["detalle"]
    assert "decláralo en `funciones`" in it["detalle"]

    _funcion(d, [bola])  # declarada la RAÍZ: cubre sus 8 copias
    s, it = _sobrantes(d)
    assert it["estado"] == OK and s["candidatas"] == 0, it["detalle"]
    assert s["por_etapa"]["ingenieria"]["pruebas"] == 0  # ni se prueban
    (fila,) = it["evidencia"]["no_candidatas_por_funcion"]
    assert fila["raiz"] == bola and fila["piezas"] == 8
    assert fila["funcion"] == "Transferencia omnidireccional de la caja"


def test_la_que_recibe_la_carga_util_tampoco():
    d, bola, _ = _mesa()
    rejilla = d.commands[-2]["id"]
    d.requirements = {**(d.requirements or {}), "carga_sobre": [bola, rejilla]}
    s, it = _sobrantes(d)
    assert it["estado"] == OK and s["candidatas"] == 0, it["detalle"]
    assert s["por_funcion"][0]["funcion"] == CS.entregan_funcion(d)[bola]


def test_la_guarda_duplicada_y_lo_fabricado_siguen_probandose():
    """Lo que la corrección agrega para aprobar se sigue probando: una guarda duplicada sobra; lo
    FABRICADO declarado en una función, o lo comprado declarado `resguardo`, no se exime."""
    d, bola, plancha = _mesa()
    guarda = _caja(d, "Guarda lateral (+X)", 3, 300, 60, 210, 0, 30)
    d.execute("fasten", {"name": "guarda", "a": guarda, "b": plancha, "kind": "perno",
                         "size": "M6", "qty": 2})
    placa = _caja(d, "Placa de tope", 3, 100, 40, -210, 0, 20)
    d.execute("fasten", {"name": "placa", "a": placa, "b": plancha, "kind": "perno",
                         "size": "M6", "qty": 2})
    _funcion(d, [bola, placa])
    funcionales = CS.entregan_funcion(d)
    assert placa not in funcionales and bola in funcionales
    s, it = _sobrantes(d)
    assert it["estado"] == FALLA and set(it["piezas"]) == {guarda, placa}, it["detalle"]
    assert not any(f.startswith(bola) or "Bola" in c["nombre"]
                   for c in s["sobrantes"] + s["necesarias"] for f in [c["id"]])

    _funcion(d, [bola], funcion="resguardo")  # una familia que la prueba sí mide
    assert CS.entregan_funcion(d) == {}
