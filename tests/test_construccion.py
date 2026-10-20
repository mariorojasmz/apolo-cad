"""Pasos visuales, etapas y guion del video de construcción (plan publicacion-tienda, F1:
`services/construccion.py`, `services/rotulos.py` y `services/guion_video.py`).

Un proyecto chico en memoria con grupos (Bastidor; Transporte con Guardas adentro) recorre lo
que importa del D2 y el D4: qué comandos se saltan, el reemplazo en sitio detectado por `is`,
la booleana que hereda el nombre del objetivo, el transportador revelado por rol y las etapas
que siguen a los grupos. Las reglas de duración, fusión y capítulos (D15) se prueban además con
pasos sintéticos, sin geometría.
"""

from __future__ import annotations

import copy
import json

import pytest

from apolo.doc.document import Document
from apolo.services.construccion import (
    MAX_REVELADOS,
    TIEMPOS,
    Paso,
    Tiempos,
    compactar,
    diferencia,
    etapas,
    pasos_visuales,
    revelado,
)
from apolo.services.guion_video import (
    MAX_CIFRAS,
    GuionError,
    capitulos,
    cifras,
    duracion_total,
    guion,
    numero,
    validar_guion,
)
from apolo.services.rotulos import plural, rol, texto_etapa

NBSP = chr(0xA0)


def _proyecto() -> tuple[Document, dict]:
    d = Document("Transportador de prueba")
    d.execute("set_variable", {"name": "L", "expression": "800"})
    d.execute("set_variable", {"name": "A", "expression": "=L/2"})
    i = {}
    i["placa"] = d.execute("create_box", {"name": "Placa base", "width": "=L/2", "depth": 100,
                                          "height": 10, "position": {"x": 0, "y": 0, "z": -50}})
    i["agujero"] = d.execute("create_cylinder", {"name": "Agujero", "radius": 10, "height": 40,
                                                 "position": {"x": 0, "y": 0, "z": -50}})
    i["bool"] = d.execute("boolean_op", {"operation": "cut", "target": i["placa"],
                                         "tools": [i["agujero"]]})  # sin nombre: «Booleana»
    i["fillet"] = d.execute("fillet", {"feature": i["bool"], "radius": 2})
    i["pata"] = d.execute("create_box", {"name": "Pata", "width": 40, "depth": 40, "height": 300,
                                         "position": {"x": -300, "y": -150, "z": 150}})
    i["patas"] = d.execute("pattern_linear", {"feature": i["pata"], "count": 4,
                                              "spacing": {"x": 200, "y": 0, "z": 0}})
    i["fasten"] = d.execute("fasten", {"name": "f_pata", "a": i["bool"], "b": i["pata"],
                                       "kind": "perno", "size": "M10", "qty": 4})
    i["ground"] = d.execute("ground", {"name": "g_pata", "feature": i["pata"]})
    i["conv"] = d.execute("create_conveyor", {"largo": "=L", "ancho": "=A", "altura": 600,
                                              "paso": 100, "position": {"x": 0, "y": 600, "z": 0}})
    i["guarda"] = d.execute("create_box", {"name": "Guarda", "width": 300, "depth": 5,
                                           "height": 100, "position": {"x": 0, "y": 820, "z": 600}})
    i["mover"] = d.execute("transform", {"feature": i["guarda"],
                                         "translate": {"x": 0, "y": 0, "z": 20}})
    i["oculta"] = d.execute("create_box", {"name": "Plantilla", "width": 10, "depth": 10,
                                           "height": 10, "position": {"x": 0, "y": -400, "z": 0}})
    d.set_visibility(i["oculta"], False)
    d.execute("create_group", {"name": "Bastidor", "members": [
        i["placa"], i["agujero"], i["bool"], i["pata"], i["patas"]]})
    d.execute("create_group", {"name": "Transporte", "members": [i["conv"]]})
    d.execute("create_group", {"name": "Guardas", "parent": "Transporte",
                               "members": [i["guarda"]]})
    d.set_requirements({"carga_kg": 50, "velocidad_m_s": 0.35, "inclinacion_deg": 0,
                        "producto": "Cajas", "tipo_cambio": 3.7, "notas": "interno"})
    return d, i


@pytest.fixture(scope="module")
def proyecto():
    d, i = _proyecto()
    return d, i, pasos_visuales(d)


def _por_cmd(pasos) -> dict:
    return {p.cmd_id: p for p in pasos}


# ------------------------------------------------------------------ pasos visuales (D2)
def test_se_saltan_los_comandos_que_no_cambian_lo_visible(proyecto):
    d, i, pasos = proyecto
    visuales = [i[k] for k in ("placa", "agujero", "bool", "fillet", "pata", "patas", "conv",
                               "guarda", "mover")]
    assert [p.cmd_id for p in pasos] == visuales  # sin variables, fasten, ground, grupos
    assert [p.k for p in pasos] == [
        next(n for n, c in enumerate(d.commands, 1) if c["id"] == cid) for cid in visuales]
    # una pieza OCULTA no es un paso visual
    assert i["oculta"] not in _por_cmd(pasos)


def test_el_reemplazo_en_sitio_se_detecta_por_identidad(proyecto):
    _, i, pasos = proyecto
    redondeo, mover = _por_cmd(pasos)[i["fillet"]], _por_cmd(pasos)[i["mover"]]
    assert (redondeo.agregados, redondeo.quitados, redondeo.reemplazados) == ((), (), (i["bool"],))
    assert (mover.agregados, mover.quitados, mover.reemplazados) == ((), (), (i["guarda"],))


def test_diferencia_compara_por_id_y_por_is():
    from types import SimpleNamespace as F

    forma = object()
    antes = {"a": F(shape=forma, visible=True), "b": F(shape=object(), visible=True),
             "c": F(shape=object(), visible=True)}
    despues = {"a": F(shape=forma, visible=True), "b": F(shape=object(), visible=True),
               "d": F(shape=object(), visible=True), "e": F(shape=object(), visible=False)}
    assert diferencia(antes, despues) == (("d",), ("c",), ("b",))


def test_la_booleana_sin_nombre_hereda_el_del_objetivo(proyecto):
    _, i, pasos = proyecto
    corte = _por_cmd(pasos)[i["bool"]]
    assert corte.quitados == (i["placa"], i["agujero"]) and corte.agregados == (i["bool"],)
    assert corte.sustitucion == "Placa base" and corte.titulo == "Placa base"
    assert corte.roles == ("Placa base",)
    # y lo conserva en el redondeo que la trabaja después
    assert _por_cmd(pasos)[i["fillet"]].nombres[i["bool"]] == "Placa base"


def test_el_transportador_se_revela_por_rol_en_orden_de_creacion(proyecto):
    d, i, pasos = proyecto
    conv = _por_cmd(pasos)[i["conv"]]
    assert conv.titulo == "Transportador" and conv.tipo == "create_conveyor"
    assert conv.roles == ("Larguero", "Rodillo", "Pata", "Travesaño")
    assert [f for sub in conv.revelado for f in sub] == list(conv.agregados)
    creadas = [fid for fid, f in d.scene.items() if f.command_id == i["conv"]]
    assert list(conv.agregados) == creadas  # el orden de la escena es el de creación
    prefijos = ("rail", "rod", "leg", "brace")
    for sub, prefijo in zip(conv.revelado, prefijos):
        assert all(f.startswith(f"{i['conv']}_{prefijo}") for f in sub)
    assert len(conv.revelado[1]) == 7


def test_el_revelado_tiene_tope_y_conserva_el_orden():
    from types import SimpleNamespace as F

    escena = {f"c1_p{n}": F(name=f"Máquina · Pieza{chr(65 + n // 2)}", command_id="c1")
              for n in range(24)}  # 12 roles, dos piezas cada uno
    roles, listas = revelado(escena, list(escena))
    assert len(listas) == MAX_REVELADOS == len(roles)
    assert [f for sub in listas for f in sub] == list(escena)
    assert roles[0] == "PiezaA y PiezaB"


def test_grupo_del_paso_y_ruta_anidada(proyecto):
    _, i, pasos = proyecto
    por = _por_cmd(pasos)
    assert por[i["placa"]].grupos == ("Bastidor",)
    assert por[i["fillet"]].grupos == ("Bastidor",)  # el redondeo no es miembro: su pieza sí
    assert por[i["conv"]].grupos == ("Transporte",)
    assert por[i["mover"]].grupos == ("Transporte", "Guardas")


def test_un_log_con_run_script_recorre():
    d = Document("con script")
    d.execute("set_variable", {"name": "L", "expression": "30"})
    s = d.execute("run_script", {"name": "Pieza de script",
                                 "code": "result = Box(V['L'], 10, 10)"})
    pasos = pasos_visuales(d)
    assert [(p.cmd_id, p.agregados, p.titulo) for p in pasos] == [(s, (s,), "Pieza de script")]


# ------------------------------------------------------------------ roles y texto
@pytest.mark.parametrize("nombre, esperado", [
    ("Transportador · Rodillo (7)", "Rodillo"),
    ("Rodillo 7", "Rodillo"),
    ("Perno M10", "Perno M10"),
    ("Larguero (+Y)", "Larguero"),
    ("Torre (2) (copia)", "Torre"),
    ("Pata (1,2)", "Pata"),
    ("Pata (espejo)", "Pata"),
    ("Chumacera (UCP205)", "Chumacera (UCP205)"),
])
def test_rol(nombre, esperado):
    assert rol(nombre) == esperado


def test_rol_sin_nombre_usa_el_sufijo_del_id():
    assert rol("", "c3_rod7", "c3") == "rod"
    assert rol(None, "c9") == "c"


@pytest.mark.parametrize("singular, esperado", [
    ("Rodillo", "rodillos"), ("Unión", "uniones"), ("Motorreductor", "motorreductores"),
    ("Placa base", "placas base"), ("UCP", "UCP"), ("Luz", "luces"), ("Tornillos", "tornillos"),
    ("Riel", "rieles"), ("Travesaño", "travesaños"),
])
def test_plural(singular, esperado):
    assert plural(singular) == esperado


def test_el_rotulo_cuenta_lo_que_entra_y_no_la_herramienta(proyecto):
    _, i, pasos = proyecto
    por = _por_cmd(pasos)
    bastidor = [por[i[k]] for k in ("placa", "agujero", "bool", "fillet", "pata", "patas")]
    assert texto_etapa(bastidor) == "Se suman «Placa base» y 4 patas."
    # trabajar una pieza de una etapa anterior es «ajustar»
    assert texto_etapa([por[i["fillet"]]]) == "Se ajusta «Placa base»."
    assert texto_etapa([por[i["guarda"]], por[i["mover"]]]) == "Se suma «Guarda»."


# ------------------------------------------------------------------ etapas (D4)
def test_las_etapas_siguen_los_grupos(proyecto):
    _, i, pasos = proyecto
    es = etapas(pasos, 75)
    assert [e.titulo for e in es] == ["Bastidor", "Transporte"]  # Guardas se funde en su padre
    assert es[0].texto == "Se suman «Placa base» y 4 patas."
    assert es[1].texto.startswith("Se suman 2 largueros, 7 rodillos, 4 patas y 3 piezas más")
    # un paso del video por paso compacto (la pata y su patrón son uno), en orden
    assert [k for e in es for k in e.pasos] == [u[-1].k for u in compactar(pasos)]
    assert [p.k for e in es for u in compactar(pasos) if u[-1].k in e.pasos for p in u] == [
        p.k for p in pasos]
    assert i["guarda"] in es[1].ids and i["agujero"] in es[0].ids
    assert all(e.duracion_s >= TIEMPOS.etapa_min_s for e in es)


def _paso(k: int, grupos=(), titulo: str | None = None, subs: int = 1) -> Paso:
    """Un paso sintético; sin `titulo`, uno propio («P7»): dos pasos con el mismo título son
    del mismo patrón y se compactan (D2 de video-tienda-pulido)."""
    titulo = titulo or f"P{k}"
    ids = tuple(f"c{k}_{n}" for n in range(subs))
    roles = (titulo,) if subs == 1 else tuple(f"{titulo}-{n}" for n in range(subs))
    return Paso(k=k, cmd_id=f"c{k}", tipo="create_box", titulo=titulo, etiqueta=titulo,
                agregados=ids, quitados=(), reemplazados=(),
                revelado=tuple((f,) for f in ids), roles=roles,
                nombres={f: f"{titulo} {n}" for n, f in enumerate(ids)}, grupos=tuple(grupos))


def _sinteticos(grupos: int, por_grupo: int) -> list[Paso]:
    return [_paso(g * por_grupo + n + 1, (f"G{g}",)) for g in range(grupos)
            for n in range(por_grupo)]


def test_la_duracion_cae_cerca_del_objetivo():
    for objetivo in (50, 75, 90):
        es = etapas(_sinteticos(6, 10), objetivo)
        assert abs(sum(e.duracion_s for e in es) + TIEMPOS.fijos_s - objetivo) < 0.1


def test_un_log_corto_no_se_estira_mas_del_tope():
    es = etapas([_paso(1), _paso(2, titulo="Otra")], 75)
    assert len(es) == 1 and es[0].duracion_s == 2 * TIEMPOS.paso_max_s
    assert es[0].titulo == "P1 y Otra"


def test_el_superpaso_pesa_mas():
    es = etapas([_paso(1, ("A",), subs=5), _paso(2, ("B",))], 30, tiempos=Tiempos(paso_max_s=99))
    a, b = es if len(es) == 2 else (es[0], None)
    assert b is None or a.duracion_s == pytest.approx(3 * b.duracion_s)


def test_la_corta_se_funde_con_su_pariente():
    pasos = ([_paso(k, ("A",)) for k in range(1, 5)] + [_paso(5, ("B", "x"))]
             + [_paso(k, ("B",)) for k in range(6, 11)])
    es = etapas(pasos, 200, tiempos=Tiempos(paso_max_s=4.0))
    assert [e.titulo for e in es] == ["A", "B"]
    assert es[1].pasos == (5, 6, 7, 8, 9, 10)


def test_sin_grupo_la_clave_es_el_titulo_del_paso():
    pasos = [_paso(1, titulo="Base"), _paso(2, titulo="Base"), _paso(3, titulo="Torre")]
    es = etapas(pasos, 200, tiempos=Tiempos(paso_max_s=10.0))
    # las dos «Base» seguidas son un patrón: un solo paso del video, el último k
    assert [(e.titulo, e.pasos) for e in es] == [("Base", (2,)), ("Torre", (3,))]


def test_etapas_borde():
    assert etapas([], 75) == []
    for malo in (0, -5, True):
        with pytest.raises(ValueError, match="positiva"):
            etapas([_paso(1)], malo)


# ------------------------------------------------------------------ guion (D3)
def test_numero_a_la_espanola():
    assert numero(3000) == f"3{NBSP}000"
    assert numero(412.4) == "412"
    assert numero(0.35) == "0,35"
    assert numero(12.5) == "12,5"
    assert numero(5.0) == "5"


def test_cifras_de_la_maquina_y_de_los_requisitos(proyecto):
    d, _, _ = proyecto
    items = {c["etiqueta"]: c["valor"] for c in cifras(d)}
    assert items["Piezas"] == str(len(d.scene))  # también la oculta: es parte de la máquina
    assert items["Masa"].endswith(f"{NBSP}kg") and items["Medidas generales"].count("×") == 2
    assert items["Carga"] == f"50{NBSP}kg" and items["Velocidad"] == f"0,35{NBSP}m/s"
    assert items["Producto"] == "Cajas"
    assert "Inclinación" not in items  # 0°: nada que decir
    assert not {"tipo_cambio", "Tipo de cambio", "Notas"} & set(items)  # nunca precios (D11)


def test_el_guion_es_json_editable_y_valido(proyecto):
    d, _, pasos = proyecto
    g = guion(d, etapas(pasos))
    assert json.loads(json.dumps(g)) == g
    validar_guion(json.loads(json.dumps(g, ensure_ascii=False)), d)
    assert g["version"] == 1 and g["idioma"] == "es"
    assert g["titulo"] == "Transportador de prueba"
    assert g["video"] == {"ancho": 1920, "alto": 1080, "fps": 30}
    assert g["cierre"]["url"] == "" and g["orbita"]["duracion_s"] == TIEMPOS.orbita_s
    assert [e["titulo"] for e in g["etapas"]] == ["Bastidor", "Transporte"]
    assert 1 <= len(g["cifras"]["items"]) <= MAX_CIFRAS
    assert guion(d, [], titulo="Otro")["titulo"] == "Otro"


def test_un_guion_de_otra_version_del_log_se_rechaza(proyecto):
    d, _, pasos = proyecto
    g = guion(d, etapas(pasos))
    otro = Document.from_apolo_bytes(d.to_apolo_bytes())
    otro.execute("create_box", {"name": "Extra", "width": 5, "depth": 5, "height": 5})
    with pytest.raises(GuionError, match="otra versión del proyecto"):
        validar_guion(g, otro)


@pytest.mark.parametrize("editar, mensaje", [
    (lambda g: g["portada"].update(duracion=3), "clave desconocida «duracion»"),
    (lambda g: g["etapas"][0].update(duracion_s=-1), "etapas[0].duracion_s"),
    (lambda g: g["etapas"][1].update(pasos=[1]), "orden creciente"),
    (lambda g: g["etapas"][0].pop("texto"), "falta «texto»"),
    (lambda g: g["video"].update(ancho=1921), "par"),
    (lambda g: g.update(version=2), "no soportada"),
    (lambda g: g.update(titulo=""), "titulo: no puede quedar vacío"),
    (lambda g: g["cierre"].update(url="ftp://x"), "https://"),
    (lambda g: g["cifras"].update(items=[{"etiqueta": "a", "valor": "b"}] * 13), "hasta 12"),
    (lambda g: g["cifras"].update(items=[]), "no tiene cifras"),
    (lambda g: g["etapas"].append("nada"), "etapas[2]: debe ser un objeto"),
])
def test_validar_guion_rechaza_ediciones_mal_formadas(proyecto, editar, mensaje):
    d, _, pasos = proyecto
    g = copy.deepcopy(guion(d, etapas(pasos)))
    editar(g)
    with pytest.raises(GuionError, match="El guion tiene") as exc:
        validar_guion(g)
    assert mensaje in str(exc.value)


def test_validar_junta_todos_los_problemas(proyecto):
    d, _, pasos = proyecto
    g = guion(d, etapas(pasos))
    g["titulo"], g["video"]["fps"] = 7, 0
    with pytest.raises(GuionError, match="tiene 2 problemas"):
        validar_guion(g)


# ------------------------------------------------------------------ capítulos (D15)
def _cumple_d15(caps, total: float) -> bool:
    inicios = [s for s, _ in caps]
    largos = [b - a for a, b in zip(inicios, [*inicios[1:], int(total)])]
    return len(caps) >= 3 and inicios[0] == 0 and min(largos) >= 10


@pytest.mark.parametrize("objetivo", [50, 75])
def test_capitulos_del_proyecto(proyecto, objetivo):
    d, _, pasos = proyecto
    g = guion(d, etapas(pasos, objetivo))
    caps = capitulos(g)
    assert _cumple_d15(caps, duracion_total(g)), caps
    assert caps[0][1] == "Bastidor" and caps[-1][1] == "La máquina terminada"


@pytest.mark.parametrize("objetivo", [50, 90, 600])
def test_capitulos_corto_y_largo(proyecto, objetivo):
    d, _, _ = proyecto
    g = guion(d, etapas(_sinteticos(8, 12), objetivo))
    caps = capitulos(g)
    assert _cumple_d15(caps, duracion_total(g)), caps
    if objetivo == 600:
        assert len(caps) == 9  # una por grupo, más el cierre
    else:  # 8 grupos de ~8 s no caben: se funden de a pares
        assert 3 <= len(caps) < 9


def test_capitulos_funde_los_cortos_editados_a_mano(proyecto):
    d, _, _ = proyecto
    g = guion(d, etapas(_sinteticos(4, 10), 90))
    g["etapas"][1]["duracion_s"] = 3.0  # una persona la acortó
    caps = capitulos(g)
    assert _cumple_d15(caps, duracion_total(g))
    assert len(caps) == len(g["etapas"])  # una etapa menos, más el cierre


def test_sin_tres_capitulos_de_diez_segundos_no_hay_capitulos(proyecto):
    d, _, pasos = proyecto
    g = guion(d, etapas(pasos, 30))
    assert duracion_total(g) < 40 and capitulos(g) == []
    g["etapas"] = []
    assert capitulos(g) == []
