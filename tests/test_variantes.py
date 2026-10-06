"""Una variante cambia sólo sus variables (plan `docs/plans/variantes-solo-sus-variables.md`).

Las variantes son una tabla de diseño RECTANGULAR: cada una guarda sólo sus COLUMNAS (las
variables que la distinguen) y todas tienen las mismas. Lo que no es columna es común y
ninguna variante lo toca. El caso que lo disparó (proyecto 38): dos variantes guardadas como
foto completa en julio revertían en silencio el cambio de la pata de octubre.
"""

from __future__ import annotations

import importlib.util
import io
import json
import zipfile
from pathlib import Path

import pytest
from apolo.doc import Document, DocumentError
from apolo.doc import variantes as V
from apolo.kernel import bbox_payload

RAIZ = Path(__file__).resolve().parents[1]


def _modelo() -> Document:
    """Faja de juguete: largo (la columna de la tabla) y sección de la pata (diseño común)."""
    d = Document("variantes")
    d.execute("set_variable", {"name": "largo_total", "expression": "4000"})
    d.execute("set_variable", {"name": "sec_pata", "expression": "76.2"})
    d.execute("set_variable", {"name": "n_patas", "expression": "4"})
    d.execute("create_box", {"name": "Cama", "width": "=largo_total", "depth": 600, "height": 20})
    d.execute("create_box", {"name": "Pata", "width": "=sec_pata", "depth": "=sec_pata",
                             "height": "=200 * n_patas"})
    return d


def _foto(doc: Document) -> tuple:
    """Lo que debe volver bit-idéntico: variables, log y bbox de cada pieza."""
    return (dict(doc.variables_raw), json.dumps(doc.commands, sort_keys=True),
            sorted((fid, json.dumps(bbox_payload(f.shape))) for fid, f in doc.scene.items()))


def _set(doc: Document, nombre: str, expr: str) -> None:
    cid = next(c["id"] for c in doc.commands
               if c["type"] == "set_variable" and c["params"]["name"] == nombre)
    doc.edit(cid, {"name": nombre, "expression": expr})


def _con_manifest(doc: Document, **cambios) -> bytes:
    """El `.apolo` del documento con el manifest retocado (None = quitar la clave)."""
    with zipfile.ZipFile(io.BytesIO(doc.to_apolo_bytes())) as z:
        archivos = {n: z.read(n) for n in z.namelist()}
    manifest = json.loads(archivos["manifest.json"])
    for k, v in cambios.items():
        if v is None:
            manifest.pop(k, None)
        else:
            manifest[k] = v
    archivos["manifest.json"] = json.dumps(manifest).encode()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n, data in archivos.items():
            z.writestr(n, data)
    return buf.getvalue()


def _manifest(data: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return json.loads(z.read("manifest.json"))


# ── el caso real: una variante ya no revierte el diseño que cambió después ────


def test_aplicar_no_revierte_una_variable_que_no_es_columna():
    doc = _modelo()
    doc.save_configuration("4m estandar", ["largo_total"])
    doc.set_configuration("3.2m compacta", {"largo_total": "3200"})
    assert doc.configurations == {"4m estandar": {"largo_total": "4000"},
                                  "3.2m compacta": {"largo_total": "3200"}}

    _set(doc, "sec_pata", "50.8")  # cambio de diseño DESPUÉS de guardar las variantes
    doc.apply_configuration("3.2m compacta")
    assert doc.variables_raw["sec_pata"] == "50.8" and doc.variables_raw["largo_total"] == "3200"
    doc.apply_configuration("4m estandar")
    assert doc.variables_raw == {"largo_total": "4000", "sec_pata": "50.8", "n_patas": "4"}


def test_aplicar_devuelve_los_cambios_medidos_antes_y_deja_un_solo_undo():
    doc = _modelo()
    doc.save_configuration("4m", ["largo_total"])
    doc.set_configuration("3.2m", {"largo_total": "3200"})
    n_undo = len(doc._undo)
    hecho = doc.apply_configuration("3.2m")
    assert hecho == {"cambios": [{"variable": "largo_total", "antes": "4000", "despues": "3200"}],
                     "aviso": None}
    assert len(doc._undo) == n_undo + 1
    doc.undo()
    assert doc.variables_raw["largo_total"] == "4000"
    assert doc.apply_configuration("4m") == {"cambios": [], "aviso": None}  # ya estaba ahí


# ── D2: tabla rectangular con relleno ─────────────────────────────────────────


def test_una_columna_nueva_entra_en_las_demas_con_su_expresion_actual():
    doc = _modelo()
    doc.save_configuration("4m", ["largo_total"])
    doc.set_configuration("3.2m", {"largo_total": "3200", "n_patas": "3"})
    assert doc.configurations == {"4m": {"largo_total": "4000", "n_patas": "4"},
                                  "3.2m": {"largo_total": "3200", "n_patas": "3"}}
    doc.save_configuration("5m", ["sec_pata"])  # también al guardar desde la actual
    assert doc.configurations["5m"] == {"largo_total": "4000", "n_patas": "4", "sec_pata": "76.2"}
    assert all(set(f) == {"largo_total", "n_patas", "sec_pata"}
               for f in doc.configurations.values())


def test_aplicar_a_y_luego_b_vuelve_bit_identico():
    """El «bug inverso»: sin relleno, aplicar 3.2m (que fija n_patas) y volver a 4m dejaba
    las patas de la 3.2m."""
    doc = _modelo()
    doc.save_configuration("4m", ["largo_total"])
    doc.set_configuration("3.2m", {"largo_total": "3200", "n_patas": "3"})
    inicial = _foto(doc)

    doc.apply_configuration("3.2m")
    assert doc.variables_raw["n_patas"] == "3" and _foto(doc) != inicial
    doc.apply_configuration("4m")
    assert _foto(doc) == inicial
    doc.apply_configuration("3.2m")
    tres = _foto(doc)
    doc.apply_configuration("4m")
    doc.apply_configuration("3.2m")
    assert _foto(doc) == tres


# ── D3 / D4: guardar y editar ─────────────────────────────────────────────────


def test_la_primera_variante_sin_variables_da_un_error_accionable():
    doc = _modelo()
    with pytest.raises(DocumentError) as exc:
        doc.save_configuration("4m")
    assert str(exc.value) == V.SIN_COLUMNAS
    assert "dinos qué variables distinguen a esta variante" in str(exc.value)
    with pytest.raises(DocumentError, match="dinos qué variables"):
        doc.set_configuration("4m", {})  # nombre nuevo, sin columnas ni valores
    assert doc.configurations == {}


def test_guardar_valida_las_variables_y_sobrescribe_el_nombre():
    doc = _modelo()
    with pytest.raises(DocumentError, match="No existe la variable nada"):
        doc.save_configuration("4m", ["nada"])
    with pytest.raises(DocumentError, match="No existen las variables a, b"):
        doc.save_configuration("4m", ["b", "a"])
    doc.save_configuration("4m", ["largo_total"])
    _set(doc, "largo_total", "4100")
    doc.save_configuration("4m")  # mismo nombre: se sobrescribe con el valor actual
    assert doc.configurations == {"4m": {"largo_total": "4100"}}


def test_editar_valida_contra_el_resto_de_las_variables():
    doc = _modelo()
    doc.set_configuration("mitad", {"n_patas": "largo_total / 1000"})  # nombra otra variable
    assert doc.configurations == {"mitad": {"n_patas": "largo_total / 1000"}}
    with pytest.raises(DocumentError, match="inválida"):
        doc.set_configuration("mala", {"n_patas": "fantasma * 2"})
    doc.apply_configuration("mitad")
    assert doc.variables_resolved["n_patas"] == 4.0


# ── D7: quitar una columna ────────────────────────────────────────────────────


def test_quitar_una_columna_la_saca_de_todas_y_la_variable_queda():
    doc = _modelo()
    doc.set_configuration("3.2m", {"largo_total": "3200", "n_patas": "3"})
    doc.save_configuration("4m")
    doc.delete_configuration_column("n_patas")
    assert doc.configurations == {"3.2m": {"largo_total": "3200"}, "4m": {"largo_total": "4000"}}
    assert doc.variables_raw["n_patas"] == "4"
    with pytest.raises(DocumentError, match="no está en la tabla de variantes; están: largo_total"):
        doc.delete_configuration_column("n_patas")
    doc.delete_configuration_column("largo_total")
    with pytest.raises(DocumentError, match="está vacía"):
        doc.delete_configuration_column("largo_total")


# ── D6: avisos al aplicar ─────────────────────────────────────────────────────


def test_una_columna_de_una_variable_borrada_se_ignora_con_aviso():
    doc = Document("aviso")
    doc.execute("set_variable", {"name": "L", "expression": "100"})
    doc.execute("set_variable", {"name": "extra", "expression": "5"})
    doc.save_configuration("v", ["L", "extra"])
    doc.set_configuration("v", {"L": "200"})
    doc.remove_commands([c["id"] for c in doc.commands if c["params"]["name"] == "extra"])
    hecho = doc.apply_configuration("v")
    assert hecho["cambios"] == [{"variable": "L", "antes": "100", "despues": "200"}]
    assert "Se ignoraron extra" in hecho["aviso"]
    with pytest.raises(DocumentError, match="ya no es una variable del proyecto"):
        doc.save_configuration("otra")  # una variante nueva no puede tomar su valor actual


def test_una_variante_sin_columnas_avisa_que_no_cambia_nada():
    doc = _modelo()
    doc.save_configuration("v", ["largo_total"])
    doc.delete_configuration_column("largo_total")
    hecho = doc.apply_configuration("v")
    assert hecho["cambios"] == [] and "no cambia nada" in hecho["aviso"]


def test_los_textos_van_en_tuteo_neutro():
    spec = importlib.util.spec_from_file_location("_pistas_gate", RAIZ / "tests" / "test_pistas.py")
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    textos = [
        V.SIN_COLUMNAS,
        V.al_aplicar({"x": "1"}, {})["aviso"],
        V.al_aplicar({}, {})["aviso"],
    ]
    for fn in (lambda: V.guardar({}, "v", {}, ["x", "y"]),
               lambda: V.guardar({"a": {"x": "1"}}, "v", {}),
               lambda: V.quitar_columna({"a": {"x": "1"}}, "y"),
               lambda: V.quitar_columna({}, "y")):
        with pytest.raises(V.VarianteError) as exc:
            fn()
        textos.append(str(exc.value))
    for t in textos:
        for detector in (gate.TUTEO["voseo"], gate.TUTEO["otro_registro"], gate.USTED,
                         gate.NO_SE_DICE):
            assert not detector.search(t), (t, detector.search(t).group(0))


# ── D5: migración de las fotos viejas ─────────────────────────────────────────


def test_migrar_dos_variantes_que_difieren_en_una_variable():
    actuales = {"L": "4000", "W": "600", "H": "750"}
    fotos = {"4m": {"L": "4000", "W": "600", "H": "700"},
             "3.2m": {"L": "3200", "W": "600", "H": "700"}}
    assert V.migrar(fotos, actuales) == {"4m": {"L": "4000"}, "3.2m": {"L": "3200"}}


def test_migrar_una_sola_variante_compara_contra_el_log():
    assert V.migrar({"v": {"L": "3200", "W": "600"}}, {"L": "4000", "W": "600"}) == \
        {"v": {"L": "3200"}}


def test_migrar_variantes_identicas_deja_la_tabla_sin_columnas():
    fotos = {"a": {"L": "1", "W": "2"}, "b": {"L": "1", "W": "2"}}
    assert V.migrar(fotos, {"L": "9", "W": "9"}) == {"a": {}, "b": {}}


def test_migrar_descarta_las_variables_que_ya_no_existen():
    fotos = {"a": {"L": "1", "borrada": "5"}, "b": {"L": "2", "borrada": "6"}}
    assert V.migrar(fotos, {"L": "1"}) == {"a": {"L": "1"}, "b": {"L": "2"}}


def test_migrar_una_clave_ausente_vale_lo_actual():
    """Una foto sin la variable (creada después) no la tocaba al aplicarse: vale lo actual."""
    actuales = {"L": "4000", "n": "4"}
    assert V.migrar({"a": {"L": "4000", "n": "3"}, "b": {"L": "3200"}}, actuales) == \
        {"a": {"L": "4000", "n": "3"}, "b": {"L": "3200", "n": "4"}}
    assert V.migrar({"a": {"L": "4000", "n": "4"}, "b": {"L": "3200"}}, actuales) == \
        {"a": {"L": "4000"}, "b": {"L": "3200"}}


def test_migrar_compara_por_str_como_al_aplicar():
    assert V.migrar({"v": {"L": 4000}}, {"L": "4000"}) == {"v": {}}
    # textos distintos con el mismo valor: en la duda, la columna se conserva
    assert V.migrar({"v": {"L": "4000.0"}}, {"L": "4000"}) == {"v": {"L": "4000.0"}}


def test_migrar_el_proyecto_38_deja_solo_largo_total():
    """37 variables, dos fotos de julio que difieren sólo en `largo_total`; desde entonces
    cambió el diseño de la pata (que ninguna variante distingue)."""
    julio = {f"v{i:02d}": str(i * 10) for i in range(35)}
    julio |= {"largo_total": "4000", "sec_pata": "76.2"}
    actuales = {**julio, "sec_pata": "sec_larg_h", "v07": "=pata_cz + 2"}
    assert len(actuales) == 37
    fotos = {"4m estandar": dict(julio),
             "3.2m (prueba paramétrica)": {**julio, "largo_total": "3200"}}
    migrada = V.migrar(fotos, actuales)
    assert migrada == {"4m estandar": {"largo_total": "4000"},
                       "3.2m (prueba paramétrica)": {"largo_total": "3200"}}
    assert V.migrar(migrada, actuales) == migrada  # idempotente


def test_variables_del_log_el_ultimo_set_variable_gana():
    log = [{"id": "c1", "type": "set_variable", "params": {"name": "L", "expression": "1"}},
           {"id": "c2", "type": "create_box", "params": {"name": "L"}},
           {"id": "c3", "type": "set_variable", "params": {"name": "L", "expression": "2"}}]
    assert V.variables_del_log(log) == {"L": "2"}


def test_abrir_un_apolo_viejo_migra_las_fotos():
    doc = _modelo()
    fotos = {"4m": {"largo_total": "4000", "sec_pata": "60", "n_patas": "4", "borrada": "1"},
             "3.2m": {"largo_total": "3200", "sec_pata": "60", "n_patas": "4", "borrada": "2"}}
    viejo = _con_manifest(doc, configurations=fotos, configurations_format=None)
    abierto = Document.from_apolo_bytes(viejo)
    assert abierto.configurations == {"4m": {"largo_total": "4000"},
                                      "3.2m": {"largo_total": "3200"}}
    abierto.apply_configuration("3.2m")
    assert abierto.variables_raw["sec_pata"] == "76.2"  # la foto ya no revierte la pata
    # se persiste con la bandera: reabrir no vuelve a migrar
    assert _manifest(abierto.to_apolo_bytes())["configurations_format"] == V.FORMATO


def test_abrir_un_apolo_con_bandera_deja_la_tabla_intacta():
    doc = _modelo()
    tabla = {"a": {"largo_total": "4000", "sec_pata": "76.2"}}  # coincide con el log: sin migrar
    con_bandera = _con_manifest(doc, configurations=tabla, configurations_format=V.FORMATO)
    assert Document.from_apolo_bytes(con_bandera).configurations == tabla
    sin_bandera = _con_manifest(doc, configurations=tabla, configurations_format=None)
    assert Document.from_apolo_bytes(sin_bandera).configurations == {"a": {}}


def test_ida_y_vuelta_conserva_la_bandera_y_la_tabla():
    doc = _modelo()
    doc.save_configuration("4m", ["largo_total"])
    doc.set_configuration("3.2m", {"largo_total": "3200", "n_patas": "3"})
    data = doc.to_apolo_bytes()
    assert _manifest(data)["configurations_format"] == V.FORMATO
    vuelta = Document.from_apolo_bytes(data)
    assert vuelta.configurations == doc.configurations
    assert _manifest(vuelta.to_apolo_bytes()) == _manifest(data)


def test_un_apolo_sin_variantes_sigue_sin_variantes():
    doc = _modelo()
    assert Document.from_apolo_bytes(_con_manifest(doc, configurations_format=None)) \
        .configurations == {}
