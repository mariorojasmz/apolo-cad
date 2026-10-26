"""El presostato deja de ser un aparato mudo (plan V8.9 F8).

- La ref `PRESOSTATO-1-10BAR` con sus dos fichas: `neumatico:` (puerto 1, rango del ajuste,
  histéresis) y `electrico:` (contacto conmutado 11-12-14 movido por «señal», con el rating de la
  ficha Festo PEV-1/4-B leída después: `tests/test_v89_presostato_masa_ficha.py`); se designa -BP1.
- El ajuste `p_conmuta_bar`: dentro del rango de la ficha en `add_device` y como ajuste de PRUEBA
  de un escenario (`library/electrico/ajustes.validar_ajustes_neumaticos`, una sola regla).
- El modelo (`cosim/modelos/presostato.py`): cierra el NA al llegar a `p_conmuta_bar`, abre al
  bajar de `p_conmuta_bar − histeresis_bar`, conserva entre los dos; sin el ajuste,
  `ModeloIncompleto` con el ejemplo.
- En la co-simulación (`presostato_escena.py`): el integral del corte de aire (el presostato abre,
  el PLC lo ve y para la máquina antes de que el cilindro pierda fuerza), la histéresis sobre la
  cámara B con la presión de red que baja y sube, la toma, y el ajuste de prueba que deja el NA
  abierto.
- El ERC neumático: sin tubo, sin contacto cableado, sin ajuste o con una conmutación sobre la
  regulada es AVISO (y un presostato sin tubo no es «puerto libre»); la lámina ISO 1219 rotula su
  designación, su ajuste y el borne que lee su NA.
"""

from __future__ import annotations

import pytest

from apolo.cosim.modelos import ModeloIncompleto, crear_modelo
from apolo.doc.document import Document
from apolo.library.catalog import CATALOG
from apolo.services.cosim_aire import ficha_plana

REF = "PRESOSTATO-1-10BAR"


def _modelo(p_conmuta=4.0):
    c = CATALOG[REF]
    modelo = {**c.electrico.modelo, "aire": ficha_plana(c.neumatico)}
    return crear_modelo("-BP1", REF, modelo, {} if p_conmuta is None else {"p_conmuta_bar": p_conmuta})


# ── la ref ───────────────────────────────────────────────────────────────────────────────────


def test_la_ref_trae_sus_dos_fichas():
    c = CATALOG[REF]
    n, e = c.neumatico, c.electrico
    assert n.tipo == "presostato" and [(p.id, p.rol, p.rosca) for p in n.puertos] == [("1", "entrada", "G1/4")]
    # el ajuste es la FUNCIÓN de la ref (1–10 bar); la ficha leída (Festo PEV-1/4-B) da 12 de
    # máxima y la histéresis típica de un microrruptor conmutado (SMC IS3000): ya no a confirmar
    assert n.ajustes == {"p_conmuta_bar": (1.0, 10.0)}
    assert n.modelo["histeresis_bar"] == 0.5 and n.modelo["p_max_bar"] == 12.0
    assert n.a_confirmar == () and "PEV-1/4-B" in n.fuente and "IS3000" in n.fuente
    assert e.montaje == "campo" and e.modelo == {"tipo": "presostato", "contacto_A": 5, "contacto_V": 250}
    assert [(k.de, k.a, k.tipo, k.accion) for k in e.caminos] == [("11", "14", "NA", "señal"),
                                                                   ("11", "12", "NC", "señal")]
    assert e.a_confirmar == () and "PEV-1/4-B" in e.fuente


def _carril(p_conmuta=4.0, *, tubo_bp=True, cableado=True, p_regulada=6) -> Document:
    """El circuito del empujador sólo en el carril (sin geometría): FRL, corte, 5/2, cilindro, el
    presostato en la línea de alimentación y su NA a la I0.0 del PLC."""
    from neumatica_escena import dev, tubo, wire

    d = Document("presostato-carril")
    aj = {"ajustes": {"p_conmuta_bar": p_conmuta}} if p_conmuta is not None else {}
    cmds = [dev("FR-G14", ajustes={"p_regulada_bar": p_regulada}), dev("CORTE-ESC-G14"), dev("VAL-52-MONO-G18"),
            dev("SIL-G18"), dev("SIL-G18"), dev("SIL-G14"),
            dev("CIL-ISO15552-32", servicio={"carrera_mm": 200}), dev(REF, "-BP1", **aj),
            dev("FUENTE-24VDC-2.5A", "-T1", ubicacion="+TAB1"), dev("PLC-14DI-10DO-24VDC", "-K1", ubicacion="+TAB1"),
            tubo("-AZ1:2", "-QM1:1", "TUBO-PU-8", largo_m=0.5), tubo("-QM1:2", "-QM2:1", "TUBO-PU-8", largo_m=1.0),
            tubo("-QM2:4", "-MM1:A", largo_m=1.0), tubo("-QM2:2", "-MM1:B", largo_m=1.0),
            tubo("-QM2:3", "-RZ1:1"), tubo("-QM2:5", "-RZ2:1"), tubo("-QM1:3", "-RZ3:1")]
    if tubo_bp:
        cmds.append(tubo("-QM2:1", "-BP1:1", "TUBO-PU-4", largo_m=0.3))
    if cableado:
        cmds += [wire("-T1:L+", "-BP1:11"), wire("-BP1:14", "-K1:I0.0")]
    d.execute_many(cmds)
    return d


def test_add_device_lo_designa_bp_y_valida_su_ajuste():
    from apolo.services.electrico import modelo

    bp = next(x for x in modelo(_carril()).dispositivos if x.ref == REF)
    assert bp.designacion == "-BP1" and bp.ajustes == {"p_conmuta_bar": 4.0}
    d = Document("fuera")
    with pytest.raises(Exception, match=r"p_conmuta_bar de .*va entre 1 y 10 \(recibí 12\)"):
        d.execute("add_device", {"ref": REF, "ajustes": {"p_conmuta_bar": 12}})
    with pytest.raises(Exception, match="no tiene el ajuste «p_regulada_bar»"):
        d.execute("add_device", {"ref": REF, "ajustes": {"p_regulada_bar": 5}})


def test_el_ajuste_de_prueba_de_un_escenario_se_valida_igual():
    from apolo.services import escenario_ajustes
    from apolo.services.electrico import modelo
    from apolo.services.errors import ServiceError

    me = modelo(_carril())
    assert escenario_ajustes.validar(me, {"-BP1": {"p_conmuta_bar": 7}}) == {"-BP1": {"p_conmuta_bar": 7.0}}
    with pytest.raises(ServiceError, match=r"p_conmuta_bar de -BP1 \(PRESOSTATO-1-10BAR\) va entre 1 y 10"):
        escenario_ajustes.validar(me, {"-BP1": {"p_conmuta_bar": 0.5}})
    nuevo, usados = escenario_ajustes.aplicar(me, {"-BP1": {"p_conmuta_bar": 7}})
    assert usados == [{"dispositivo": "-BP1", "ajuste": "p_conmuta_bar", "valor": 7.0, "proyecto": 4.0}]
    assert next(x for x in me.dispositivos if x.designacion == "-BP1").ajustes == {"p_conmuta_bar": 4.0}


# ── el modelo ────────────────────────────────────────────────────────────────────────────────


def test_conmuta_con_histeresis():
    m = _modelo(4.0)
    assert (m.p_on, m.p_off) == (4.0, 3.5)
    m.iniciar(6.0)
    assert m.activo                                  # la máquina ya con aire
    estados = []
    for p in (6.0, 4.0, 3.6, 3.5, 3.49, 3.8, 3.99, 4.0, 3.0, None):
        m.paso(0.002, {"p_bar": p})
        estados.append(m.activo)
    # baja: sigue cerrado hasta BAJAR de 3,5; sube: abierto hasta LLEGAR a 4; sin presión, abre
    assert estados == [True, True, True, True, False, False, False, True, False, False]
    assert m.senales() == {"-BP1.activo": False, "-BP1.p_bar": 0.0}
    m.iniciar(3.8)
    assert not m.activo                              # entre umbrales, al empezar: bajo la conmutación


def test_sin_ajuste_no_se_simula_con_un_valor_inventado():
    with pytest.raises(ModeloIncompleto, match=r'falta el ajuste «p_conmuta_bar».*\{"p_conmuta_bar": 5\.5\}'):
        _modelo(None)
    with pytest.raises(ModeloIncompleto, match="ficha neumática del presostato"):
        crear_modelo("-BP1", REF, CATALOG[REF].electrico.modelo, {"p_conmuta_bar": 4})


def test_la_tabla_de_tipos_lo_conoce():
    from apolo.cosim.datos import DispositivoCosim
    from apolo.cosim.tipos import valores_iniciales

    c = CATALOG[REF]
    d = DispositivoCosim("-BP1", REF, {**c.electrico.modelo, "aire": ficha_plana(c.neumatico)}, {}, 1)
    assert valores_iniciales([d]) == {"-BP1.activo": False, "-BP1.p_bar": 0.0, "-BP1.averia": ""}


# ── el ERC y la lámina ───────────────────────────────────────────────────────────────────────


def _reglas(doc) -> list[dict]:
    from apolo.services.electrico import modelo
    from apolo.services.neumatica import reglas

    return [r for r in reglas(modelo(doc)) if r["regla"] in ("presostato", "puerto libre")]


def test_erc_un_presostato_bien_puesto_es_ok():
    filas = _reglas(_carril())
    assert [(r["regla"], r["estado"]) for r in filas] == [("puerto libre", "ok"), ("presostato", "ok")]


@pytest.mark.parametrize("kw,texto", [
    ({"tubo_bp": False}, "no tiene tubo: lee la atmósfera"),
    ({"cableado": False}, "su contacto no está cableado (11-14, 11-12)"),
    ({"p_conmuta": None}, "la presión de conmutación no está declarada (rango 1–10 bar)"),
    ({"p_conmuta": 7}, "conmuta a 7 bar y su línea recibe 6 bar de -AZ1: el NA no cerraría nunca"),
])
def test_erc_un_presostato_que_no_vigila_nada_es_aviso(kw, texto):
    filas = _reglas(_carril(**kw))
    pres = [r for r in filas if r["regla"] == "presostato"]
    assert [r["estado"] for r in pres] == ["aviso"] and texto in pres[0]["detalle"], pres
    assert pres[0]["elementos"][0] == "-BP1" and pres[0]["medio"] == "aire"
    # sin tubo no es «puerto libre» (un error): lo dice su propia regla, como aviso
    assert [r["estado"] for r in filas if r["regla"] == "puerto libre"] == ["ok"]


def test_sin_presostatos_el_erc_no_suma_filas():
    from neumatica_escena import dev, tubo

    from apolo.services.electrico import modelo
    from apolo.services.neumatica import reglas

    d = Document("sin")
    d.execute_many([dev("FR-G14", ajustes={"p_regulada_bar": 6}), dev("CORTE-ESC-G14"),
                    tubo("-AZ1:2", "-QM1:1", "TUBO-PU-8")])
    assert "presostato" not in {r["regla"] for r in reglas(modelo(d))}


def test_la_lamina_rotula_su_ajuste_y_el_borne_que_lo_lee():
    from apolo.services import neumatica_esquema as NE

    c = NE.circuito(_carril())
    bp = next(a for a in c.aparatos if a.designacion == "-BP1")
    assert (bp.tipo, bp.rotulo, bp.contacto) == ("presostato", "4 bar", "14: +TAB1-K1:I0.0")
    textos = [lab.text for lab in NE.lamina(_carril()).labels]
    assert {"-BP1", "4 bar", "14: +TAB1-K1:I0.0"} <= set(textos)
    sin = next(a for a in NE.circuito(_carril(cableado=False)).aparatos if a.designacion == "-BP1")
    assert sin.contacto == "14: sin cablear"
