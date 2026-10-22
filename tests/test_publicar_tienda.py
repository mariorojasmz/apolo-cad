"""`publicar subir` contra una tienda falsa (plan publicacion-tienda, F6).

Dos `http.server` en hilos: la tienda (las 6 rutas, con Bearer) y un «bucket» en OTRO puerto
(otro origen: la subida firmada no lleva el Bearer). La tienda guarda lo que el bucket recibió y
la confirmación compara tamaño y sha256 con lo declarado. Cada llamada queda registrada.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from apolo import paths
from apolo.publicacion import tienda as tiendas
from apolo.publicacion.tienda import LlaveFaltante, TiendaError

RAIZ_REPO = Path(__file__).resolve().parents[1]
LLAVE = "apolo_pub_" + "A" * 43
SLUG, VERSION = "mesa-de-taller", "1.0.0"
ROLES = {".png": "miniatura", ".mp4": "video", ".glb": "modelo_3d"}


class Falsa:
    """Estado compartido de la tienda y el bucket falsos, y lo que se puede torcer."""

    def __init__(self):
        self.llamadas: list[tuple[str, str]] = []
        self.subidas: dict[str, dict] = {}  # clave → lo declarado
        self.recibido: dict[str, bytes] = {}  # clave → lo que llegó al bucket
        self.auth_bucket: list[str | None] = []
        self.cabeceras_bucket: list[dict] = []
        self.errores_plan: list[str] = []
        self.falla_bucket: set[str] = set()  # nombres que el bucket rechaza
        self.confirmacion_409 = 0  # cuántas confirmaciones responden «todavía no llegó»
        self.disco = False  # subida a la propia tienda (fuera de producción)
        self.importada = None
        self.estado = None
        self.url = self.bucket = ""


def _handler(f: Falsa, es_bucket: bool):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *_a):
            pass

        def _json(self, status: int, cuerpo) -> None:
            data = json.dumps(cuerpo).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _cuerpo(self) -> bytes:
            assert "chunked" not in (self.headers.get("Transfer-Encoding") or "")
            return self.rfile.read(int(self.headers.get("Content-Length") or 0))

        def _subida(self, clave: str) -> None:
            datos = self._cuerpo()
            decl = f.subidas[clave]
            if decl["nombre"] in f.falla_bucket:
                return self._json(500, {"error": "el bucket se cayó"})
            assert self.headers.get("X-Firma") == f"firma-{clave}"
            assert self.headers.get("Content-Type") == decl["tipo"]
            f.recibido[clave] = datos
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_PUT(self):
            if es_bucket:
                f.llamadas.append(("PUT", "bucket"))
                f.auth_bucket.append(self.headers.get("Authorization"))
                f.cabeceras_bucket.append(dict(self.headers))
                return self._subida(self.path.rsplit("/", 1)[-1])
            self._api("PUT")

        def do_POST(self):
            self._api("POST")

        def _api(self, metodo: str):
            ruta = self.path.split("?")[0]
            f.llamadas.append((metodo, ruta))
            if self.headers.get("Authorization") != f"Bearer {LLAVE}":
                self._cuerpo()
                return self._json(401, {"error": "Llave inválida, vencida o revocada."})
            if ruta == "/api/archivos/subidas/disco":
                return self._subida(self.path.split("clave=")[1])
            cuerpo = json.loads(self._cuerpo() or b"{}")
            if ruta == "/api/maquina/importacion/revision":
                return self._json(200, _revision(f, cuerpo))
            if ruta == "/api/archivos/subidas":
                clave = f"k{len(f.subidas)}"
                f.subidas[clave] = cuerpo
                url = (f"{f.url}/api/archivos/subidas/disco?clave={clave}" if f.disco
                       else f"{f.bucket}/r2/{clave}")
                return self._json(200, {"clave": clave, "url": url, "metodo": "PUT", "headers": {
                    "Content-Type": cuerpo["tipo"], "X-Firma": f"firma-{clave}"}})
            if ruta == "/api/archivos/subidas/confirmacion":
                clave = cuerpo["clave"]
                if f.confirmacion_409 > 0:
                    f.confirmacion_409 -= 1
                    return self._json(409, {"error": "Todavía no llegó."})
                decl, datos = f.subidas[clave], f.recibido.get(clave)
                if datos is None or len(datos) != decl["tamano"] \
                        or hashlib.sha256(datos).hexdigest() != decl["sha256"]:
                    return self._json(422, {"error": "No coincide."})
                return self._json(201, {"ok": True, "archivo": {"id": f"a-{clave}"}})
            if ruta == "/api/maquina/importacion":
                f.importada = cuerpo
                return self._json(201, {"ok": True, "faltan": [], "maquina": {
                    "id": 7, "slug": cuerpo["ficha"]["slug"], "creada": True}})
            if ruta == "/api/maquina/7/estado":
                f.estado = cuerpo["estado"]
                return self._json(200, {"ok": True, "maquina": {"id": 7, "slug": SLUG}})
            self._json(404, {"error": f"no existe {ruta}"})

    return H


def _revision(f: Falsa, cuerpo: dict) -> dict:
    archivos, ignorados = [], []
    for n in cuerpo["nombres"]:
        suf = Path(n).suffix
        rol = ROLES.get(suf) or ("paquete_gratis" if n.endswith("-gratis.zip") else
                                 "paquete_completo" if n.endswith("-completo.zip") else None)
        if rol is None:
            ignorados.append(n)
            continue
        archivos.append({"nombre": n, "rol": rol,
                         "visibilidad": "privado" if rol == "paquete_completo" else "publico",
                         "requiereCuenta": rol == "paquete_completo"})
    roles = {a["rol"] for a in archivos}
    return {"ok": not f.errores_plan, "datos": cuerpo["ficha"], "existente": None, "plan": {
        "archivos": archivos, "ignorados": ignorados,
        "faltan": [r for r in ("miniatura", "paquete_gratis") if r not in roles],
        "errores": f.errores_plan}}


@pytest.fixture
def falsa():
    f = Falsa()
    servidores = [ThreadingHTTPServer(("127.0.0.1", 0), _handler(f, b)) for b in (False, True)]
    for s in servidores:
        threading.Thread(target=s.serve_forever, daemon=True).start()
    f.url, f.bucket = (f"http://127.0.0.1:{s.server_address[1]}" for s in servidores)
    yield f
    for s in servidores:
        s.shutdown()
        s.server_close()


FIRMA = "f1rma0de0prueba00000"


def calidad_aprobada(carpeta: Path, firma: str = FIRMA) -> dict:
    """Lo que deja la puerta de publicación aprobada (`calidad.json`) y el bloque `calidad` que
    `generar` pone en ficha.json (puerta-de-publicacion D8): sin ellos la tienda no recibe nada."""
    cal = {"aprobado": True, "firma": firma, "version_registro": "1",
           "conteos": {"OK": 3, "FALLA": 0, "SIN_EVALUAR": 0, "NO_APLICA": 2}, "items": []}
    (carpeta / "calidad.json").write_text(json.dumps(cal), encoding="utf-8")
    return {"aprobado": True, "forzado": False, "conteos": cal["conteos"],
            "version_registro": "1", "firma": firma}


@pytest.fixture
def paquete(tmp_path) -> Path:
    carpeta = tmp_path / SLUG / VERSION
    carpeta.mkdir(parents=True)
    (carpeta / "ficha.json").write_text(json.dumps(
        {"formato": 1, "titulo": "Mesa de taller", "slug": SLUG, "version": VERSION,
         "descripcion": "Una mesa.", "nivel": "gratis", "precio_usd": 0,
         "calidad": calidad_aprobada(carpeta)}), encoding="utf-8")
    (carpeta / "miniatura.png").write_bytes(b"\x89PNG" + b"m" * 100)
    (carpeta / "video.mp4").write_bytes(b"v" * (3 * 1024 * 1024 + 7))
    (carpeta / "vista-3d.glb").write_bytes(b"glTF" + b"g" * 50)
    (carpeta / f"{SLUG}-{VERSION}-gratis.zip").write_bytes(b"PK" + b"z" * 70)
    (carpeta / f"{SLUG}-{VERSION}-completo.zip").write_bytes(b"PK" + b"Z" * 90)
    for privado in ("ficha.yaml", "guion.json", "generacion.json", "youtube.txt"):
        (carpeta / privado).write_text("privado", encoding="utf-8")
    return carpeta


def _subir(f: Falsa, carpeta, **kw):
    return tiendas.subir(carpeta, tienda=f.url, llave=kw.pop("llave", LLAVE), eco=None,
                         espera_s=0, **kw)


def _rutas(f: Falsa) -> list[str]:
    return [r for _m, r in f.llamadas]


def test_flujo_completo_publica(falsa, paquete):
    r = _subir(falsa, paquete)
    assert r["publicada"] and r["url"] == f"{falsa.url}/maquinas/{SLUG}"
    assert falsa.estado == "publicada"
    roles = sorted(a["rol"] for a in falsa.importada["archivos"])
    assert roles == ["miniatura", "modelo_3d", "paquete_completo", "paquete_gratis", "video"]
    assert falsa.importada["ficha"]["slug"] == SLUG
    # lo privado de la carpeta no se ofrece; el bucket recibió todo sin el Bearer
    nombres = {d["nombre"] for d in falsa.subidas.values()}
    assert not nombres & {"ficha.yaml", "guion.json", "generacion.json", "youtube.txt"}
    assert len(falsa.recibido) == 5 and falsa.auth_bucket == [None] * 5
    completo = next(d for d in falsa.subidas.values() if d["nombre"].endswith("completo.zip"))
    assert completo["requiere_cuenta"] is True and completo["tipo"] == "application/zip"
    assert all("Content-Length" in c for c in falsa.cabeceras_bucket)
    assert _rutas(falsa)[0] == "/api/maquina/importacion/revision"
    assert _rutas(falsa)[-1] == "/api/maquina/7/estado"


def test_subida_a_la_propia_tienda_lleva_el_bearer(falsa, paquete):
    falsa.disco = True
    assert _subir(falsa, paquete)["publicada"]
    assert len(falsa.recibido) == 5 and not falsa.auth_bucket


def test_borrador_no_publica(falsa, paquete):
    r = _subir(falsa, paquete, borrador=True)
    assert not r["publicada"] and falsa.importada is not None and falsa.estado is None
    assert not any("estado" in ruta for ruta in _rutas(falsa))


def test_ensayo_no_sube(falsa, paquete):
    r = _subir(falsa, paquete, ensayo=True)
    assert len(r["plan"]["archivos"]) == 5
    assert _rutas(falsa) == ["/api/maquina/importacion/revision"]


def test_error_del_plan_aborta_antes_de_subir(falsa, paquete):
    falsa.errores_plan = ["El slug ya es de otra persona."]
    with pytest.raises(TiendaError, match="El slug ya es de otra persona"):
        _subir(falsa, paquete)
    assert _rutas(falsa) == ["/api/maquina/importacion/revision"]


def test_sin_miniatura_aborta(falsa, paquete):
    (paquete / "miniatura.png").unlink()
    with pytest.raises(TiendaError, match="miniatura"):
        _subir(falsa, paquete)
    assert _rutas(falsa) == ["/api/maquina/importacion/revision"]


def test_falla_una_subida_no_importa(falsa, paquete):
    falsa.falla_bucket = {"video.mp4"}
    with pytest.raises(TiendaError, match="video.mp4.*500(?s:.*)No importé"):
        _subir(falsa, paquete)
    assert falsa.importada is None and "/api/maquina/importacion" not in _rutas(falsa)


def test_confirmacion_409_reintenta(falsa, paquete):
    falsa.confirmacion_409 = 3  # el tope: la cuarta confirmación entra
    assert _subir(falsa, paquete)["publicada"]
    falsa.confirmacion_409 = 4
    falsa.importada = None
    with pytest.raises(TiendaError, match="409"):
        _subir(falsa, paquete)
    assert falsa.importada is None


def _ficha(carpeta: Path) -> dict:
    return json.loads((carpeta / "ficha.json").read_text(encoding="utf-8"))


def _con_ficha(carpeta: Path, **calidad) -> None:
    f = _ficha(carpeta)
    f["calidad"] = {**f["calidad"], **calidad}
    (carpeta / "ficha.json").write_text(json.dumps(f), encoding="utf-8")


@pytest.mark.parametrize(("estropear", "texto"), [
    (lambda c: (c / "calidad.json").unlink(), "no tiene calidad.json"),
    (lambda c: (c / "calidad.json").write_text(json.dumps(
        {"aprobado": False, "firma": FIRMA, "items": [
            {"id": "entrega.gravedad", "familia": "estructura", "estado": "FALLA",
             "titulo": "Estable con gravedad", "detalle": "2 piezas caen", "piezas": ["c3"]}]}),
        encoding="utf-8"), "(?s)no la aprobó.*entrega.gravedad.*2 piezas caen.*c3"),
    (lambda c: _con_ficha(c, forzado=True, aprobado=False), "--forzar"),
    (lambda c: _con_ficha(c, firma="otra"), "firma de ficha.json"),
    (lambda c: (c / "ficha.json").write_text(json.dumps(
        {k: v for k, v in _ficha(c).items() if k != "calidad"}), encoding="utf-8"),
     "bloque «calidad»"),
])
def test_la_tienda_no_recibe_un_paquete_sin_la_calidad_aprobada(falsa, paquete, estropear, texto):
    """D8/D11 de puerta-de-publicacion: sin calidad.json aprobado, generado con --forzar o con
    otra firma, `subir` se niega ANTES de llamar a la tienda (tampoco en ensayo)."""
    estropear(paquete)
    for ensayo in (False, True):
        with pytest.raises(tiendas.PublicacionError, match=texto):
            _subir(falsa, paquete, ensayo=ensayo)
    assert falsa.llamadas == []


def test_carpeta_publicada_toma_la_ultima_generada(paquete, tmp_path):
    (tmp_path / SLUG / "1.0.1").mkdir()  # sin ficha.json: no generada
    assert tiendas.carpeta_publicada(tmp_path, SLUG, None, eco=None) == paquete
    with pytest.raises(tiendas.PublicacionError, match="no está generada"):
        tiendas.carpeta_publicada(tmp_path, SLUG, "1.0.1", eco=None)


# ------------------------------------------------------------------ el CLI
def _cli():
    spec = importlib.util.spec_from_file_location("publicar_cli",
                                                  RAIZ_REPO / "scripts" / "publicar.py")
    mod = importlib.util.module_from_spec(spec)
    previo = sys.dont_write_bytecode
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = previo
    return mod


def _argv(f: Falsa, *extra) -> list[str]:
    return ["subir", "--slug", SLUG, "--version", VERSION, "--tienda", f.url, *extra]


def test_cli_sin_llave_no_toca_la_red(falsa, paquete, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(paths, "publicaciones_dir", lambda: tmp_path)
    monkeypatch.delenv(tiendas.LLAVE_ENV, raising=False)
    assert _cli().main(_argv(falsa)) == 2
    err = capsys.readouterr().err
    assert "APOLO_TIENDA_LLAVE" in err and "SetEnvironmentVariable" in err
    assert "Llaves de publicación" in err and falsa.llamadas == []
    with pytest.raises(LlaveFaltante):
        tiendas.llave_del_entorno({})


def test_cli_401_no_imprime_la_llave(falsa, paquete, tmp_path, monkeypatch, capsys):
    otra = "apolo_pub_" + "Zq9" * 14 + "x"
    monkeypatch.setattr(paths, "publicaciones_dir", lambda: tmp_path)
    monkeypatch.setenv(tiendas.LLAVE_ENV, otra)
    assert _cli().main(_argv(falsa)) == 2
    salida = capsys.readouterr()
    texto = salida.out + salida.err
    assert "no aceptó la llave" in salida.err and otra[:12] in salida.err
    assert otra not in texto and otra[12:] not in texto
    assert _rutas(falsa) == ["/api/maquina/importacion/revision"]


def test_cli_publica(falsa, paquete, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(paths, "publicaciones_dir", lambda: tmp_path)
    monkeypatch.setenv(tiendas.LLAVE_ENV, LLAVE)
    assert _cli().main(_argv(falsa)) == 0
    salida = capsys.readouterr().out
    assert f"Publicada: {falsa.url}/maquinas/{SLUG}" in salida and LLAVE not in salida
    assert falsa.estado == "publicada"
