"""La clave `ext` del manifest (plan nucleo-abierto-extensiones-privadas, F1d): los datos de una
extensión sobreviven a CADA ruta que abre o guarda un `.apolo` —abrir por id (`store.load`),
autosave, carga tolerante, revisiones (guardar y restaurar), duplicar, exportar y subir, y el
adjunto de un `insert_project`—, también los de una extensión que no está instalada. Sin datos,
el manifest es el de siempre; lo que no es JSON plano o no tiene nombre de extensión se rechaza al
escribir y se descarta (sin lanzar) al abrir."""

from __future__ import annotations

import io
import json
import math
import zipfile

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc import Document, DocumentError, ext_manifest
from apolo.projects import ProjectStore

DATOS = {"version": 2, "tablero": {"lado": "izquierdo", "cotas": [1.5, 2, None, True]}}
AJENA = {"de": "otra extensión que aquí no está instalada"}


def _manifest(data: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return json.loads(z.read("manifest.json"))


def _contenido(data: bytes) -> dict[str, bytes]:
    """Lo que guarda el .apolo, entrada por entrada: los bytes del ZIP llevan además la HORA de
    cada entrada (resolución de 2 s), y dos escrituras iguales a un lado y otro de ese borde
    difieren sin que cambie nada (falló así en el CI)."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return {n: z.read(n) for n in z.namelist()}


def _con_ext(nombre: str = "Con ext") -> Document:
    d = Document(nombre)
    d.execute("create_box", {"name": "Base", "width": 100, "depth": 100, "height": 10})
    ext_manifest.poner(d, "ext-prueba", DATOS)
    ext_manifest.poner(d, "zeta", AJENA)
    return d


# ── el módulo (puro) ─────────────────────────────────────────────────────────────────────────

def test_sin_datos_el_manifest_es_el_de_siempre_y_un_apolo_viejo_abre():
    d = Document("x")
    d.execute("create_box", {"name": "B", "width": 10, "depth": 10, "height": 10})
    data = d.to_apolo_bytes()
    assert "ext" not in _manifest(data)
    assert Document.from_apolo_bytes(data).ext == {}
    ext_manifest.poner(d, "ext-prueba", DATOS)
    ext_manifest.poner(d, "ext-prueba", None)  # borrar deja el manifest como antes
    assert _contenido(d.to_apolo_bytes()) == _contenido(data)


def test_ida_y_vuelta_conserva_todas_las_extensiones():
    data = _con_ext().to_apolo_bytes()
    assert _manifest(data)["ext"] == {"ext-prueba": DATOS, "zeta": AJENA}
    for kw in ({}, {"tolerant": True}, {"regenerate": False}):
        assert Document.from_apolo_bytes(data, **kw).ext == {"ext-prueba": DATOS, "zeta": AJENA}


def test_leer_y_poner_devuelven_copias():
    d = _con_ext()
    leido = ext_manifest.leer(d, "ext-prueba")
    leido["version"] = 99
    assert d.ext["ext-prueba"]["version"] == 2
    assert ext_manifest.leer(d, "nadie") is None
    entrada = {"a": [1]}
    ext_manifest.poner(d, "zeta", entrada)
    entrada["a"].append(2)
    assert d.ext["zeta"] == {"a": [1]}


@pytest.mark.parametrize(("nombre", "datos", "msg"), [
    ("", {}, "no es un nombre de extensión"),
    ("con espacio", {}, "no es un nombre de extensión"),
    (3, {}, "no es un nombre de extensión"),
    ("ok", [1, 2], "tiene que ser un dict"),
    ("ok", "texto", "tiene que ser un dict"),
    ("ok", {"x": math.nan}, "sólo números finitos"),
    ("ok", {"x": (1, 2)}, "sólo JSON plano"),
    ("ok", {"x": {1: "a"}}, "las claves son texto"),
    ("ok", {"x": {"y": [object()]}}, r"ext\[ok\]\.x\.y\[0\] es object"),
    ("ok", {"x": "a" * (ext_manifest.TOPE_BYTES + 1)}, "el tope es"),
])
def test_poner_rechaza_lo_que_no_es_json_plano_sin_tocar_nada(nombre, datos, msg):
    d = _con_ext()
    antes = json.dumps(d.ext, sort_keys=True)
    with pytest.raises(DocumentError, match=msg):
        ext_manifest.poner(d, nombre, datos)
    assert json.dumps(d.ext, sort_keys=True) == antes


def test_con_las_conocidas_solo_escribe_la_extension_duena():
    d = Document("x")
    with pytest.raises(DocumentError, match="no es una extensión cargada"):
        ext_manifest.poner(d, "zeta", {"a": 1}, conocidas=["ext-prueba"])
    with pytest.raises(DocumentError, match="no es una extensión cargada"):
        ext_manifest.poner(d, "zeta", None, conocidas=["ext-prueba"])
    assert ext_manifest.poner(d, "ext-prueba", {"a": 1}, conocidas=["ext-prueba"]) == {"a": 1}


def test_la_carga_descarta_lo_mal_formado_sin_lanzar():
    d = _con_ext()
    data = d.to_apolo_bytes()
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as zin, zipfile.ZipFile(buf, "w") as zout:
        for n in zin.namelist():
            contenido = zin.read(n)
            if n == "manifest.json":
                m = json.loads(contenido)
                m["ext"].update({"mal nombre": {"a": 1}, "lista": [1], "ok": {"b": 2}})
                contenido = json.dumps(m)
            zout.writestr(n, contenido)
    abierto = Document.from_apolo_bytes(buf.getvalue(), tolerant=True)
    assert abierto.ext == {"ext-prueba": DATOS, "zeta": AJENA, "ok": {"b": 2}}
    roto = _manifest(data) | {"ext": "no es un dict"}
    assert ext_manifest.de_manifest(roto) == {}


def test_es_metadato_deshacer_no_lo_toca():
    d = _con_ext()
    d.execute("create_box", {"name": "Otra", "width": 5, "depth": 5, "height": 5})
    ext_manifest.poner(d, "ext-prueba", {"version": 3})
    d.undo()
    assert d.ext["ext-prueba"] == {"version": 3} and len(d.commands) == 1


# ── cada ruta de la API que abre o guarda ────────────────────────────────────────────────────

@pytest.fixture
def abierto(monkeypatch, tmp_path):
    """Un proyecto CON `ext` en un almacén temporal, abierto por la API (`store.load`)."""
    store = ProjectStore(tmp_path / "ext.db")
    pid = store.create(_con_ext())
    monkeypatch.setattr(api, "STORE", store)
    monkeypatch.setattr(api, "PROJECT_ID", None)
    monkeypatch.setattr(api, "DOC", Document("antes"))
    cliente = TestClient(api.app)
    assert cliente.post(f"/api/projects/{pid}/open").status_code == 200
    assert api.DOC.ext == {"ext-prueba": DATOS, "zeta": AJENA}
    return cliente, store, pid


def _esperado():
    return {"ext-prueba": DATOS, "zeta": AJENA}


def test_el_autosave_la_guarda(abierto):
    cliente, store, pid = abierto
    r = cliente.post("/api/commands", json={"type": "create_box", "params": {
        "name": "Nueva", "width": 20, "depth": 20, "height": 20}})
    assert r.status_code == 200, r.text
    api._flush_autosave(force=True)
    assert _manifest(store.load_bytes(pid))["ext"] == _esperado()
    assert store.load(pid, tolerant=True).ext == _esperado()


def test_las_revisiones_la_guardan_y_la_restauran(abierto):
    cliente, store, pid = abierto
    rev = cliente.post("/api/revisions", json={"note": "con ext"}).json()["id"]
    assert store.load_revision(rev)[1].ext == _esperado()
    api.DOC.ext.clear()  # el activo la pierde (en memoria)
    assert cliente.post(f"/api/revisions/{rev}/restore").status_code == 200
    assert api.DOC.ext == _esperado()


def test_duplicar_la_copia(abierto):
    cliente, store, pid = abierto
    nuevo = cliente.post(f"/api/projects/{pid}/duplicate").json()["id"]
    assert store.load(nuevo).ext == _esperado()


def test_exportar_y_subir_la_conservan(abierto):
    cliente, _store, _pid = abierto
    data = cliente.get("/api/project/file").content
    assert _manifest(data)["ext"] == _esperado()
    api.DOC = Document("otro")
    r = cliente.post("/api/project/open", files={"file": ("x.apolo", data, "application/zip")})
    assert r.status_code == 200, r.text
    assert api.DOC.ext == _esperado()


def test_el_adjunto_de_insert_project_lleva_la_del_donante(abierto):
    """El donante viaja ENTERO en el adjunto (`store.load_bytes`): su `ext` va ahí y no se
    mezcla con la del anfitrión (cada documento es dueño de la suya)."""
    cliente, store, pid = abierto
    anfitrion = store.create(Document("layout"))
    assert cliente.post(f"/api/projects/{anfitrion}/open").status_code == 200
    r = cliente.post("/api/commands", json={"type": "insert_project", "params": {
        "project_id": pid, "name": "Sub"}})
    assert r.status_code == 200, r.text
    (adjunto,) = api.DOC.attachments.values()
    assert _manifest(adjunto)["ext"] == _esperado()
    assert api.DOC.ext == {}
