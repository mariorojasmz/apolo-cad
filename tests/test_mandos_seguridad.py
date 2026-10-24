"""Mandos de seguridad de dos canales: catálogo, builder y modelos (plan mandos-de-seguridad F1:
D1–D5). La faja de categoría 3 está en `test_mandos_seguridad_faja.py`.

- Cada ref nueva construye UN sólido válido con su marco (D1, D2), es genérica (D4) y entra en la
  colocación del tablero (V8.5): la seta de puerta y el relé de riel se colocan; lo de campo (la
  seta en caja, el interruptor de resguardo) se rechaza con el motivo.
- La seta de 2 NC alarga lo de detrás de la puerta con su segundo bloque y la de 1 NC queda
  EXACTAMENTE como estaba (D5: sin bump de `GEOM_CACHE_EPOCH`).
- Cada modelo con su gemelo sano (D2, D3): el resguardo abre y cierra sus NC y, trabado, no los
  mueve; el relé arma con los dos canales al SOLTAR el rearme, abre con cualquiera, no rearma
  hasta que los dos ciclaron, y sus fallas (`salida_pegada`, `detenido`).
"""

from __future__ import annotations

import pytest

from apolo.cosim.fallas import catalogo
from apolo.cosim.modelos import crear_modelo
from apolo.library.catalog import CATALOG, build_component
from apolo.library.electrico.colocacion import ColocacionError, colocar
from apolo.library.electrico.colocacion_catalogo import aparatos_desde_catalogo, gabinetes_del_catalogo

DT = 0.002
NUEVAS = ["ESTOP-40-2NC", "ESTOP-40-CAJA-2NC", "RESG-2NC", "RESG-LENGUETA", "RS-2C-24VDC"]
#: (volumen mm³, caras, aristas, bbox) medidos sobre bf69175, antes de este plan (D5)
ANTES = {"ESTOP-40": (82998.213, 14, 25, (-30, -30, -44, 30, 30, 33)),
         "ESTOP-40-CAJA": (320733.94, 29, 64, (-36, -58, 0, 36, 36, 87.5))}


def _medir(ref):
    bb = build_component(ref)[0].bounding_box()
    return bb.size.X, bb.size.Y, bb.size.Z


# ── catálogo y builder ───────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("ref", NUEVAS)
def test_cada_ref_nueva_construye_un_solido_y_es_generica(ref):
    c = CATALOG[ref]
    shape = build_component(ref)[0]
    assert shape.is_valid and len(shape.solids()) == 1, ref
    s = c.specs
    assert s["linea_referencia"].startswith("orden de ") and s["cotas_verificadas"] is False
    assert s["cost"] > 0 and "verificar con el proveedor" in c.description.lower()
    assert not any(k in s for k in ("B10d", "PFHd", "MTTFd")), "la fiabilidad no es del núcleo (D4)"


@pytest.mark.parametrize("ref", sorted(ANTES))
def test_las_setas_de_un_nc_no_cambian_su_geometria(ref):
    volumen, caras, aristas, caja = ANTES[ref]
    s = build_component(ref)[0]
    bb = s.bounding_box()
    assert s.volume == pytest.approx(volumen, abs=1e-3)
    assert (len(s.faces()), len(s.edges())) == (caras, aristas)
    assert (bb.min.X, bb.min.Y, bb.min.Z, bb.max.X, bb.max.Y, bb.max.Z) == pytest.approx(caja, abs=1e-6)


def test_la_seta_de_dos_nc_lleva_un_contacto_por_canal():
    for ref in ("ESTOP-40-2NC", "ESTOP-40-CAJA-2NC"):
        e = CATALOG[ref].electrico
        assert e.parada_emergencia and e.modelo == {"tipo": "seta", "retorno": "retenido"}
        assert [(c.de, c.a, c.tipo, c.actuador) for c in e.caminos] == [
            ("11", "12", "NC", "mano"), ("21", "22", "NC", "mano")]
    assert CATALOG["ESTOP-40-CAJA-2NC"].electrico.montaje == "campo"


def test_el_segundo_bloque_alarga_lo_de_detras_de_la_puerta():
    uno, dos = (CATALOG[r].tablero.puerta for r in ("ESTOP-40", "ESTOP-40-2NC"))
    bb = build_component("ESTOP-40-2NC")[0].bounding_box()
    assert dos.delante_mm == uno.delante_mm == pytest.approx(bb.max.Z, abs=0.5)
    assert dos.detras_mm == pytest.approx(-bb.min.Z, abs=0.5) and dos.detras_mm == uno.detras_mm + 14
    caja1, caja2 = (build_component(r)[0].bounding_box() for r in ("ESTOP-40-CAJA", "ESTOP-40-CAJA-2NC"))
    assert caja2.size.Z - caja1.size.Z == pytest.approx(14)  # la caja sube para los dos bloques


def test_la_seta_de_dos_bloques_valida_sus_params():
    from apolo.library.builders_mandos import seta_emergencia

    with pytest.raises(ValueError, match="bloques 3 fuera de la serie"):
        seta_emergencia(bloques=3)
    with pytest.raises(ValueError, match="alto_caja ≥ 69"):
        seta_emergencia(montaje="caja", bloques=2)


def test_el_interruptor_de_resguardo_y_su_lengueta_casan_por_sus_anclas():
    cuerpo, lengueta = CATALOG["RESG-2NC"], CATALOG["RESG-LENGUETA"]
    assert cuerpo.familia == lengueta.familia == "interruptor_resguardo"
    assert cuerpo.electrico.funcion == "B" and cuerpo.electrico.montaje == "campo"
    assert lengueta.electrico is None and lengueta.specs["para"] == "RESG-2NC"
    assert cuerpo.specs["actuador"] == "RESG-LENGUETA"
    assert [(c.de, c.a, c.tipo, c.actuador) for c in cuerpo.electrico.caminos] == [
        ("11", "12", "NC", "abierto"), ("21", "22", "NC", "abierto")]
    ranura, punta = cuerpo.anchors["ranura"], lengueta.anchors["punta"]
    assert ranura["axis"] == [0.0, 0.0, -1.0] and punta["axis"] == [0.0, 0.0, 1.0]  # entra de frente
    bc = build_component("RESG-2NC")[0].bounding_box()
    assert ranura["origin"][2] == pytest.approx(bc.max.Z)  # la boca está en el frente del cuerpo
    assert punta["origin"][2] == pytest.approx(build_component("RESG-LENGUETA")[0].bounding_box().max.Z)
    # la lengüeta pasa por la ranura (4,5 × 20) con holgura
    from apolo.library.builders_mandos import RESG_LENGUETA, RESG_RANURA

    assert RESG_LENGUETA[0] < RESG_RANURA[0] and RESG_LENGUETA[1] < RESG_RANURA[1]


def test_lo_de_tablero_entra_en_la_colocacion_y_lo_de_campo_no():
    devs = [{"designacion": "-S0", "ref": "ESTOP-40-2NC"}, {"designacion": "-K2", "ref": "RS-2C-24VDC"},
            {"designacion": "-Q1", "ref": "SECC-25A-3P"}, {"designacion": "-F1", "ref": "ITM-C2-2P"}]
    aps, avisos = aparatos_desde_catalogo(devs, CATALOG, medir=_medir)
    assert avisos == []
    lay = colocar(aps, "auto", gabinetes_del_catalogo(CATALOG))
    s0, k2 = lay.de("-S0"), lay.de("-K2")
    assert s0.zona == "puerta" and k2.zona == "placa"
    assert (k2.ancho, k2.w1 - k2.w0) == (22.5, 114) and s0.w1 - s0.w0 == pytest.approx(33 + 58)
    for q in lay.aparatos:  # lo de detrás de la seta (el bloque extra incluido) no cae sobre la placa
        if q.zona == "placa" and q.solapa(s0.u0, s0.v0, s0.u0 + s0.ancho, s0.v0 + s0.alto):
            assert s0.w0 - q.w1 >= 10 - 1e-6, q.designacion
    for ref in ("ESTOP-40-CAJA-2NC", "RESG-2NC"):
        with pytest.raises(ColocacionError, match="es de campo"):
            aparatos_desde_catalogo([{"designacion": "-B9", "ref": ref}], CATALOG, medir=_medir)


# ── el interruptor de resguardo ──────────────────────────────────────────────────────────────


def _resguardo():
    return crear_modelo("-B2", "RESG-2NC", CATALOG["RESG-2NC"].electrico.modelo)


def test_el_resguardo_mueve_sus_nc_y_trabado_no():
    sano, malo = _resguardo(), _resguardo()
    assert sano.actuadores() == {"abierto": False} and sano.salidas() == {"cerrado": True}
    malo.fallar("trabado")
    for m in (sano, malo):
        m.accionar("abrir")
    assert sano.actuadores() == {"abierto": True} and sano.salidas() == {"cerrado": False}
    assert malo.actuadores() == {"abierto": False} and malo.salidas() == {"cerrado": False}
    assert malo.senales()["-B2.averia"] == "trabado" and "-B2.averia" not in sano.senales()
    malo.reparar("trabado")  # el mecanismo vuelve a seguir a la lengüeta (afuera)
    assert malo.actuadores() == {"abierto": True}
    malo.fallar("trabado", False)  # trabado con los contactos ABIERTOS: el resguardo cierra y no
    malo.accionar("cerrar")
    assert malo.actuadores() == {"abierto": True} and malo.salidas() == {"cerrado": True}


# ── el relé de seguridad ─────────────────────────────────────────────────────────────────────

ON, OFF = 24.0, 0.0


class Rele:
    """El relé con sus entradas a mano: `paso(s, c1, c2, rearme)` avanza s segundos."""

    def __init__(self):
        self.m = crear_modelo("-K2", "RS-2C-24VDC", CATALOG["RS-2C-24VDC"].electrico.modelo)

    def paso(self, s: float, c1=True, c2=True, rearme=False, alim=ON):
        e = {"S12": ON if c1 else OFF, "S22": ON if c2 else OFF, "S34": ON if rearme else OFF, "U_alim_V": alim}
        for _ in range(round(s / DT)):
            self.m.paso(DT, e)
        return self.m.salidas()

    def rearmar(self, **kw):
        self.paso(0.1, rearme=True, **kw)
        return self.paso(0.1, **kw)

    @property
    def contactos(self):
        return self.m.actuadores()


def test_el_rele_arma_al_soltar_el_rearme_con_los_dos_canales():
    r = Rele()
    assert r.paso(0.1)["salidas"] is False  # sin rearme no arma
    assert r.paso(0.2, rearme=True)["salidas"] is False  # apretado tampoco: actúa al SOLTAR
    r.paso(0.04)
    assert r.m.estado == "conectando"
    assert r.paso(0.02)["salidas"] is True and r.m.estado == "cerrado"  # tras t_conexion (50 ms)
    assert r.contactos == {"salida_13": True, "salida_23": True, "salida_33": True, "aux": True}
    falta = Rele()
    assert falta.rearmar(c2=False)["salidas"] is False  # con un canal abierto no arma
    sin_alim = Rele()
    assert sin_alim.rearmar(alim=18.0)["salidas"] is False  # bajo el 85 % de Un


def test_abre_con_cualquier_canal_y_no_rearma_hasta_que_los_dos_ciclen():
    for canal in ("c1", "c2"):
        r = Rele()
        r.rearmar()
        r.paso(0.01, **{canal: False})
        assert r.m.estado == "desconectando" and r.m.cerradas  # siguen cerradas t_desconexion
        out = r.paso(0.02, **{canal: False})
        assert out["salidas"] is False and out["espera_ciclo"] is True
        assert r.contactos == {"salida_13": False, "salida_23": False, "salida_33": False, "aux": False}
        # sólo abrió ESE canal (el otro, como pegado): vuelto a cerrar, el relé no rearma
        assert r.rearmar()["salidas"] is False and r.m.espera_ciclo
        otro = "c2" if canal == "c1" else "c1"
        r.paso(0.1, **{otro: False})  # el otro cicla también: ahora sí
        assert r.rearmar()["salidas"] is True and not r.m.espera_ciclo
    # la parada normal: abren los dos a la vez y rearma al primer intento
    r = Rele()
    r.rearmar()
    r.paso(0.1, c1=False, c2=False)
    assert r.rearmar()["salidas"] is True


def test_salida_pegada_queda_cerrada_y_no_deja_rearmar():
    sano, malo = Rele(), Rele()
    for r in (sano, malo):
        r.rearmar()
    malo.m.fallar("salida_pegada", "13-14")
    for r in (sano, malo):
        r.paso(0.1, c1=False, c2=False)
    assert sano.contactos == {"salida_13": False, "salida_23": False, "salida_33": False, "aux": False}
    assert malo.contactos == {"salida_13": True, "salida_23": False, "salida_33": False, "aux": True}
    for r in (sano, malo):
        r.paso(0.1)
    assert sano.rearmar()["salidas"] is True and malo.rearmar()["salidas"] is False
    assert malo.m.senales()["-K2.averia"] == "salida_pegada 13-14"
    malo.m.reparar("salida_pegada", {"salida": "13-14"})
    assert malo.rearmar()["salidas"] is True and malo.m.averia == ""
    with pytest.raises(ValueError, match="una de 13-14, 23-24, 33-34"):
        malo.m.fallar("salida_pegada", "43-44")


def test_detenido_abre_las_salidas_y_reparado_pide_el_rearme():
    r = Rele()
    r.rearmar()
    r.m.fallar("detenido")
    assert r.paso(0.01)["salidas"] is False and r.rearmar()["salidas"] is False
    r.m.reparar("detenido")
    assert r.paso(0.1)["salidas"] is False and r.rearmar()["salidas"] is True


def test_sin_alimentacion_abre_y_al_volver_arranca_de_cero():
    r = Rele()
    r.rearmar()
    assert r.paso(0.05, alim=OFF)["salidas"] is False
    assert r.paso(0.1)["salidas"] is False and r.rearmar()["salidas"] is True


def test_la_discrepancia_va_como_hipotesis_y_el_catalogo_ofrece_las_salidas():
    r = Rele()
    assert any("discrepancia" in h for h in r.m.hipotesis)

    class Tab:
        modelos = {"-K2": r.m, "-B2": _resguardo()}
        mando_red = pot_red = None

    fallas = {f["designacion"]: f["fallas"] for f in catalogo(Tab())["fallas"]}
    assert fallas["-K2"] == [{"falla": "salida_pegada", "pide": "salida", "opciones": ["13-14", "23-24", "33-34"]},
                             {"falla": "detenido", "pide": ""}]
    assert fallas["-B2"] == [{"falla": "trabado", "pide": "bool?"}]
