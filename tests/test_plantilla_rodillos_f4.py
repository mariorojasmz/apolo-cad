"""`create_roller_conveyor` v2: los defectos que el revisor de taller ciego halló en la
plantilla (plan `docs/plans/plantilla-rodillos-cadena.md`, F4 — D4 a D9).

La máquina de prueba es la de F3: 3 m, paso 95.25, TUBOR-2, MOTOR-037 y la ficha del encargo
(0.25 m/s, paquetes de 400 mm y 25 kg). Se arma una vez por módulo. Lo puro (cotas, velocidad,
reglas de `engineering_check`) se prueba sin OCCT.
"""

from __future__ import annotations

import math

import pytest

from apolo.commands.exec_rodillos_cadena import comandos_efectivos
from apolo.commands.registry import REGISTRY
from apolo.doc import Document
from apolo.library import rodillos_cadena as rc
from apolo.library.checks import hardware_ids
from apolo.library.rodillos_cadena_motriz import tensado_requerido
from apolo.library.rodillos_cadena_reglas import reglas_rodillos_cadena
from banco_guardas import Rayos, alcanza, interferencias_sin_tope

PARAMS_3M = {"largo": 3000, "velocidad_m_s": 0.25, "carga_kg": 200}
FICHA = {"carga_kg": 25, "largo_paquete_mm": 400, "ancho_paquete_mm": 400, "velocidad_m_s": 0.25}
#: Bboxes de la v1 (F2) del transportador de 1 m por defecto, medidos antes de F4: rodillos,
#: cadenas y motor de un log v1 no se mueven.
V1 = {
    "c1_motor": (808.663, -213.195, 508.231, 948.663, 272.005, 685.331),
    "c1_pinon_m": (814.413, 241.605, 523.251, 942.913, 267.005, 651.411),
    "c1_cad_m": (812.11, 254.5, 520.556, 964.534, 272.3, 761.009),
    "c1_pinon": (37.725, 259.795, 691.037, 104.502, 295.605, 758.163),
    "c1_pinons_9": (895.498, 259.795, 691.037, 962.275, 295.605, 758.163),
    "c1_tubo": (45.975, -250.0, 699.2, 96.775, 250.0, 750.0),
    "c1_tubos_9": (903.225, -250.0, 699.2, 954.025, 250.0, 750.0),
    "c1_cad0": (35.466, 283.1, 688.19, 202.534, 300.9, 761.01),
    "c1_cad8": (797.466, 283.1, 688.19, 964.534, 300.9, 761.01),
    "c1_eje": (65.375, -280.0, 718.6, 77.375, 330.9, 730.6),
    "c1_ejes_9": (922.625, -280.0, 718.6, 934.625, 330.9, 730.6),
    "c1_larg_p": (0.0, 310.9, 669.6, 1000.0, 385.9, 744.6),
}


def _disp(**kw) -> rc.Disposicion:
    p = dict(largo=3000, ancho_util=500, paso=95.25, rodillo="TUBOR-2", altura=750,
             carga_kg=200, motriz=True, motor="MOTOR-037", velocidad_m_s=0.25)
    p.update(kw)
    return rc.disposicion(**p)


def _bb(shape):
    b = shape.bounding_box()
    return (b.min.X, b.min.Y, b.min.Z, b.max.X, b.max.Y, b.max.Z)


@pytest.fixture(scope="module")
def tres():
    doc = Document("rodillos-3m")
    doc.execute("create_roller_conveyor", {**PARAMS_3M, "motor": "MOTOR-037", "mantenimiento": False})
    doc.set_requirements(dict(FICHA))
    return doc


def _moviles(doc) -> set:
    """Lo que corre con el motor al tensar: portamotor, orejas, base, motor, piñón y cárter."""
    ultima = len(_disp().estaciones) - 1
    return {f for f in doc.scene if f in {f"c1_trav_e{ultima}", "c1_oreja_m", "c1_oreja_p",
                                          "c1_base_motor", "c1_motor", "c1_pinon_m"}
            or f.startswith("c1_carter")}


def _gira(fid: str) -> bool:
    return fid.startswith(("c1_cad", "c1_pinon"))


def _guarda(fid: str) -> bool:
    """Las guardas de F4: cárter, guarda fija de la transmisión (D4) y bandeja (D5)."""
    return fid.startswith(("c1_carter", "c1_guarda_tr", "c1_bandeja", "c1_tapa_bandeja"))


# ------------------------------------------------------------------ D6: velocidad (puro)
def test_velocidad_025_da_025_mas_menos_10():
    d = _disp()
    assert d.velocidad_m_s == pytest.approx(0.25, rel=0.10)
    assert d.motriz.pinon == "PINON-ASA40-1-Z30"
    lenta = _disp(velocidad_m_s=0.15)  # otra velocidad, otro piñón (el más cercano que arma)
    assert lenta.motriz.z_pinon == 17 and lenta.velocidad_m_s == pytest.approx(0.15, rel=0.10)
    # sin velocidad (logs v1): el Z30 de siempre
    assert _disp(velocidad_m_s=None).motriz.pinon == rc.PINON_MOTRIZ


def test_una_velocidad_que_no_sale_dice_las_que_salen_y_que_motor_la_da():
    with pytest.raises(ValueError) as exc:
        _disp(velocidad_m_s=0.40)
    texto = str(exc.value)
    assert "salen, en m/s" in texto and "Z30 0.266" in texto
    assert "MOTOR-150 + piñón Z30 da 0.372 m/s" in texto  # y por qué no cabe con este ancho


# ------------------------------------------------------------------ D7: tensado (puro)
def test_el_recorrido_de_tensado_es_el_del_estirado_de_reemplazo():
    """+3 % del largo de la cadena / 2 en centros (Tsubaki/Renold) y −3 mm para el eslabón de
    unión; que las ranuras lo den sobre la línea de centros se mide en el 3D (abajo)."""
    m = _disp().motriz
    assert m.tensado_mm >= tensado_requerido(m.eslabones, 12.7) == pytest.approx(
        0.015 * m.eslabones * 12.7)
    assert m.montaje_mm == 3.0
    ranuras = m.oreja["ranuras"]
    assert [r["frena"] for r in ranuras] == ["montaje", "tensado"]  # cada sentido lo frena una
    for r in ranuras:  # los dos pernos caen sobre el eje de la pata
        assert r["perno"][0] == pytest.approx(0.0, abs=1e-6)


# ------------------------------------------------------------------ D9: reglas (puro)
def test_engineering_check_valida_la_plantilla_contra_la_ficha():
    params = {"largo": 3000, "ancho_util": 500, "paso": 95.25, "rodillo": "TUBOR-2",
              "altura": 750, "carga_kg": 200, "motriz": "cadena", "motor": "MOTOR-037",
              "velocidad_m_s": 0.25}
    reglas = {r["regla"]: r for r in reglas_rodillos_cadena(params, 25, 400, 0.25, 400)}
    assert set(reglas) == {"velocidad del producto", "apoyo del paquete", "capacidad de rodillo",
                           "ancho útil", "carga de diseño", "motor", "cadena",
                           "recorrido de tensado", "pies niveladores"}  # F5: los pies
    assert reglas["velocidad del producto"]["estado"] == "ok"
    assert reglas["apoyo del paquete"]["estado"] == "ok"  # 4 rodillos bajo 400 mm
    assert reglas["capacidad de rodillo"]["estado"] == "ok"
    assert reglas["carga de diseño"]["estado"] == "ok"  # 7 × 25 = 175 ≤ 200
    assert reglas["recorrido de tensado"]["estado"] == "ok"
    assert reglas["cadena"]["calc"]["fs"] == pytest.approx(1.09, abs=0.005)  # el FS que leyó F3
    assert reglas["cadena"]["estado"] == "aviso"  # < 1.2
    assert all("calc" in r for k, r in reglas.items() if k != "ancho útil")
    # la ficha llena de paquetes pasa la carga de la plantilla → error; velocidad lejos → aviso
    otras = {r["regla"]: r for r in reglas_rodillos_cadena(
        {**params, "carga_kg": 100}, 25, 400, 0.40, None)}
    assert otras["carga de diseño"]["estado"] == "error"
    assert otras["velocidad del producto"]["estado"] == "aviso"
    # un motor que no da el par nominal de la cadena: FS < 1 → error
    assert reglas_rodillos_cadena({**params, "largo": 4000, "ancho_util": 800, "paso": 120.65,
                                   "rodillo": "TUBOR-3", "altura": 900, "motor": "MOTOR-150",
                                   "velocidad_m_s": None}, 25, 400)[-2]["estado"] == "error"


# ------------------------------------------------------------------ la máquina de 3 m (OCCT)
def test_tres_metros_sin_interferencias(tres):
    """Guardas incluidas y sin excluir lo declarado (sólo la tornillería queda fuera), y sin el
    tope de 400 parejas de `interference_report`."""
    assert tres.check_integrity() == []
    formas = {f: x.shape for f, x in tres.scene.items()}
    assert interferencias_sin_tope(formas, hardware_ids(tres)) == []


def test_las_ranuras_de_las_orejas_dejan_correr_los_pernos(tres):
    """Cada perno (fijo a la pata) recorre en su ranura desde −3 (montaje) hasta +tensado
    sobre la línea de centros sin tocar la oreja (que se mueve con el portamotor)."""
    m = _disp().motriz
    a = math.radians(m.angulo_deg)
    for s in ("m", "p"):
        oreja = tres.scene[f"c1_oreja_{s}"].shape
        y = oreja.bounding_box().center().Y
        for xr, zr in (r["perno"] for r in m.oreja["ranuras"]):
            x0, z0 = m.portamotor["x"] + xr, m.portamotor["z"] + zr
            for k in range(11):
                t = -m.montaje_mm + (m.tensado_mm + m.montaje_mm) * k / 10.0
                # la oreja corre −t·ŵ al tensar: en su marco, el perno avanza +t·ŵ
                xp, zp = x0 + t * math.sin(a), z0 + t * math.cos(a)
                for ang in range(0, 360, 30):
                    q = (xp + 4.9 * math.cos(math.radians(ang)), y, zp + 4.9 * math.sin(math.radians(ang)))
                    assert not oreja.is_inside(q), (s, t, ang)
        # y el fondo de cada ranura frena: la A el acercamiento, la B el tensado
        (xa, za), (xb, zb) = (r["perno"] for r in m.oreja["ranuras"])
        for (x0, z0), t, lado in (((xa, za), -m.montaje_mm - 1.5, -1.0),
                                  ((xb, zb), m.tensado_mm + 1.5, 1.0)):
            xp = m.portamotor["x"] + x0 + t * math.sin(a) + lado * 4.9 * math.sin(a)
            zp = m.portamotor["z"] + z0 + t * math.cos(a) + lado * 4.9 * math.cos(a)
            assert oreja.is_inside((xp, y, zp)), (s, t)


def test_holgura_a_lo_que_gira_en_las_dos_puntas_del_recorrido(tres):
    """El conjunto que corre (portamotor, orejas, base, motor, piñón y cárter) en +3 mm
    (montaje) y en −tensado sobre la línea de centros: nada choca y ninguna guarda queda a
    menos de 3 mm de lo que gira. La cadena motriz se deforma con el recorrido: la mide
    `test_la_cadena_motriz_libra_la_guarda_fija` en 2D."""
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape

    m = _disp().motriz
    a = math.radians(m.angulo_deg)
    moviles = _moviles(tres)
    hechos = set()
    for t in (0.0, m.montaje_mm, -m.tensado_mm):
        mover = {f: tres.scene[f].shape.translate((t * math.sin(a), 0, t * math.cos(a)))
                 for f in moviles}
        forma = {f: mover.get(f, tres.scene[f].shape) for f in tres.scene}
        if t:
            assert interferencias_sin_tope(forma, hardware_ids(tres) | {"c1_cad_m"},
                                           focus=moviles) == [], t
        for g in (f for f in forma if _guarda(f)):
            bg = _bb(forma[g])
            for r in (f for f in forma if _gira(f) and f != "c1_cad_m"):
                if (g, r) in hechos and g not in moviles and r not in moviles:
                    continue  # lo que no corre se mide una vez
                hechos.add((g, r))
                br = _bb(forma[r])
                if any(bg[i] > br[i + 3] + 3.0 or br[i] > bg[i + 3] + 3.0 for i in range(3)):
                    continue
                dist = BRepExtrema_DistShapeShape(forma[g].wrapped, forma[r].wrapped).Value()
                assert dist >= 3.0 - 0.05, (t, g, r, dist)


def test_la_cadena_motriz_libra_la_guarda_fija():
    """En 2D (plano de la hilera 2): los ramales de la cadena motriz, con el motor en las dos
    puntas del recorrido, quedan ≥ 3 mm de las paredes de la guarda fija y del cárter."""
    from apolo.library.rodillos_cadena_motriz import _dist_segmento, _tangentes

    d = _disp()
    m, a = d.motriz, math.radians(d.motriz.angulo_deg)
    paredes = [e["puntos"] for e in d.guardas["fija"]["extremos"]]
    for t in (m.montaje_mm, -m.tensado_mm):
        motor = (m.x + t * math.sin(a), m.z + t * math.cos(a))
        cart = [[(x + t * math.sin(a), z + t * math.cos(a)) for x, z in e["puntos"]]
                for e in d.guardas["carter"]["extremos"]]
        for p, q in _tangentes(motor, m.r_envolvente, (d.xs[-1], d.h_eje), d.r_cadena):
            for pol in paredes + cart:
                for k in range(len(pol)):
                    u, v = pol[k], pol[(k + 1) % len(pol)]
                    for punto, (s0, s1) in ((u, (p, q)), (v, (p, q)), (p, (u, v)), (q, (u, v))):
                        assert _dist_segmento(punto, s0, s1) >= 3.0 - 1e-6, t


def test_una_sonda_de_dedo_no_alcanza_la_transmision(tres):
    """ISO 13857: el dedo entra hasta el nudillo por una abertura ≥ 8 mm. Una sonda recta de
    Ø8 no llega a ninguna cadena ni piñón desde abajo, desde el lado del motor (bajo los
    tubos) ni desde afuera (+Y)."""
    d = _disp()
    rayos = Rayos({f: x.shape for f, x in tres.scene.items()}, peligro=_gira)
    x_t, a2 = d.xs[-1] - 260.0, d.ancho_util / 2.0
    xs_largo = [x for x in range(0, int(d.largo), 9) if x < x_t] + [
        x_t + 3.5 * k for k in range(int((d.largo + 5 - x_t) / 3.5))]
    fallas = []
    for x in xs_largo:  # desde abajo
        for k in range(int((d.y_in_p + 6 - (a2 - 30)) / 3.5)):
            y = a2 - 30 + 3.5 * k
            if alcanza(rayos, (x, y, -50.0), (0, 0, 1)):
                fallas.append(("abajo", x, y))
    z_tubos = d.h_eje - d.d_rodillo / 2.0
    for x in (x for x in xs_largo if x >= x_t - 400):  # del lado del motor, bajo los tubos
        for k in range(int(z_tubos / 4.0)):
            if alcanza(rayos, (x, -1500.0, 4.0 * k), (0, 1, 0)):
                fallas.append(("motor", x, 4.0 * k))
    for x in xs_largo:  # desde afuera
        for k in range(int((d.guarda_z + 20 - (d.h_eje - 120)) / 4.0)):
            z = d.h_eje - 120 + 4.0 * k
            if alcanza(rayos, (x, 1500.0, z), (0, -1, 0)):
                fallas.append(("afuera", x, z))
    assert fallas == []
    # control: sin la bandeja ni la guarda de la transmisión, la misma sonda SÍ llega
    sin = Rayos({f: x.shape for f, x in tres.scene.items() if not _guarda(f)}, peligro=_gira)
    y_cad = d.y_pinon - 28.6  # plano de la hilera 2
    assert alcanza(sin, (d.xs[3] + d.paso / 2.0, y_cad, -50.0), (0, 0, 1))  # bajo un lazo
    from apolo.library.rodillos_cadena_motriz import _tangentes

    m = d.motriz  # el ramal +X de la cadena motriz, a media altura, visto desde el motor
    p, q = max(_tangentes((m.x, m.z), m.r_envolvente, (d.xs[-1], d.h_eje), d.r_cadena),
               key=lambda s: s[0][0] + s[1][0])
    assert alcanza(sin, ((p[0] + q[0]) / 2.0 - 1.0, -1500.0, (p[1] + q[1]) / 2.0), (0, 1, 0))
    # y sin el faldón, desde afuera por la luz entre el canto del ala y la chapa (la de F2)
    sin = Rayos({f: x.shape for f, x in tres.scene.items() if f != "c1_faldon"}, peligro=_gira)
    assert alcanza(sin, (d.xs[3] + d.paso / 2.0, 1500.0, d.h_eje + 30.0), (0, -1, 0))


def test_bandeja_en_tramos_y_travesanos_a_una_altura(tres):
    d = _disp()
    tramos = [f for f in tres.scene if f.startswith("c1_bandeja")]
    assert len(tramos) == math.ceil((d.guardas["fija"]["x_izq"] - 1.0) / 1000.0)
    for f in tramos:
        b = _bb(tres.scene[f].shape)
        assert b[3] - b[0] <= 1000.0
        assert b[2] == pytest.approx(d.h_eje - d.r_cadena - 5.0 - 2.0, abs=0.01)  # 5 mm bajo
    roscas = [c for c in comandos_efectivos(tres.commands, tres.variables_resolved)
              if c["id"].startswith("c1_rosca_bandeja")]
    assert len(roscas) == 2 * len(tramos)  # 2 M6 al alma por tramo
    zs = {round(_bb(x.shape)[2], 3) for f, x in tres.scene.items() if f.startswith("c1_trav_e")}
    assert len(zs) == 1  # D8: el mismo travesaño en todas las estaciones


def test_libre_lleva_el_travesano_a_media_pata():
    d = rc.disposicion(1000, 500, 95.25, "TUBOR-2", 750, 100, False, None)
    # F5: la pata arranca sobre la pila del pie nivelador
    assert {e.z_travesano for e in d.estaciones} == {d.pies.z_pata0 + d.pata_largo / 2.0}


def test_engineering_check_reconoce_la_plantilla(tres):
    """`/api/checks` (la tool `engineering_check`) valida la plantilla contra la ficha guardada;
    la memoria de cálculo usa las mismas dos funciones (`conveyor_params_from_doc` y
    `conveyor_engineering_check`)."""
    from fastapi.testclient import TestClient

    import apolo.api.main as api

    api.DOC = tres
    rep = TestClient(api.app).post("/api/checks", json={"interference_ids": ["c1_motor"]}).json()
    reglas = {r["regla"]: r for r in rep["ingenieria"]}
    assert "transportador" not in reglas  # «no hay ningún transportador» (F3)
    assert {"velocidad del producto", "motor", "cadena", "recorrido de tensado",
            "carga de diseño", "capacidad de rodillo", "apoyo del paquete"} <= set(reglas)
    assert reglas["velocidad del producto"]["estado"] == "ok"  # 0.266 contra 0.25: dentro de 10 %


def test_sujecion_declarada_verde_sin_truncar(tres):
    """La puerta de entrega (sin gravedad: la de los tres tamaños va con `-m torture`) da VERDE
    y revisa TODAS sus parejas candidatas (las guardas no la pasan del tope)."""
    from apolo.library.delivery import VERDE, delivery_report
    from apolo.services.delivery_inputs import delivery_inputs

    entradas = delivery_inputs(tres, expand=lambda v: [])
    assert entradas["interferencias_truncado"] is False
    rep = delivery_report(**entradas)
    assert rep["veredicto"] == VERDE and rep["avisos"] == [], rep


# ------------------------------------------------------------------ log v1 y caché
def test_un_log_v1_regenera_con_las_mismas_cotas():
    doc = Document("v1")  # los params de un log v1: sin velocidad_m_s
    # un log viejo no trae `taller` (F6): el sello sólo lo pone al comando que nace
    doc.execute("create_roller_conveyor", {"largo": 1000, "taller": False})
    assert doc.check_integrity() == []
    for fid, esperado in V1.items():
        assert _bb(doc.scene[fid].shape) == pytest.approx(esperado, abs=2e-3), fid
    assert "c1_guarda_tr" not in doc.scene and "c1_carter_int" in doc.scene  # guardas nuevas


def test_la_version_invalida_la_cache(monkeypatch):
    from apolo.doc.document import _cmd_sig

    cmd = {"id": "c1", "type": "create_roller_conveyor", "params": {"largo": 1000}}
    assert REGISTRY["create_roller_conveyor"].version >= 2  # v3 = F5
    v2 = _cmd_sig("", cmd)
    monkeypatch.setattr(REGISTRY["create_roller_conveyor"], "version", 1)
    assert _cmd_sig("", cmd) != v2
