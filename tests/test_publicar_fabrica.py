"""`publicar fabrica` (plan fabrica-de-publicaciones, F3 · D6, D7): la cadena guion → ficha →
generar → tienda con `estado.json`, reanudación, la ficha en rojo que para, el candado de
render y el borrador.

Los pasos que necesitan la API y el video se reemplazan por falsos que escriben lo que el real
dejaría en la carpeta; la ficha usa el `preparar.revisar` real y la tienda, el `tienda.subir`
real contra la tienda falsa de `test_publicar_tienda.py`.
"""

# ruff: noqa: F811 — `falsa` es un fixture importado de otro test: los tests lo reciben por nombre
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from test_publicar_tienda import LLAVE, calidad_aprobada, falsa  # noqa: F401 — `falsa` es un fixture
from test_publicar_youtube import _cli

from apolo import paths
from apolo.publicacion import fabrica, flujo
from apolo.publicacion import ficha as fichas
from apolo.publicacion.candado import Candado, CandadoOcupado
from apolo.publicacion.fabrica import Encargo, FabricaError
from apolo.publicacion.tienda import LlaveFaltante

SLUG, VERSION = "mesa-de-taller", "1.0.0"
FICHA_OK = (fichas.borrador("Mesa de taller", SLUG, VERSION)
            .replace('descripcion: ""', 'descripcion: "Una mesa de taller soldada, con tablero."')
            .replace("etiquetas: []", 'etiquetas: ["mesa", "taller", "soldadura"]'))


class Pasos:
    """Pasos falsos: cuentan sus llamadas y dejan en la carpeta lo que dejaría el real (el guion,
    sin guion.json: `ficha --revisar` leería sus capítulos)."""

    def __init__(self, ficha: str = FICHA_OK):
        self.llamadas: list[str] = []
        self.ficha = ficha
        self.falla_generar = 0
        self.render = "navegador"
        self.calidades = 0  # la puerta de publicación (paso «calidad»), aparte de `llamadas`
        self.bloque = None

    def calidad(self, e: Encargo) -> dict:
        self.calidades += 1
        self.bloque = calidad_aprobada(e.carpeta)  # lo que deja la puerta aprobada
        return {"aprobado": True}

    def guion(self, e: Encargo) -> dict:
        self.llamadas.append("guion")
        e.carpeta.mkdir(parents=True, exist_ok=True)
        (e.carpeta / "ficha.yaml").write_text(self.ficha, encoding="utf-8")
        e.eco("guion escrito")
        return {"etapas": 0}

    def generar(self, e: Encargo) -> dict:
        self.llamadas.append("generar")
        if self.falla_generar:
            self.falla_generar -= 1
            e.eco("video: 10/100 fotogramas")
            raise fabrica.PublicacionError("El video no salió: se cortó la luz")
        f = {"formato": 1, "titulo": "Mesa de taller", "slug": SLUG, "version": VERSION,
             "descripcion": "Una mesa.", "nivel": "gratis", "precio_usd": 0,
             "calidad": self.bloque or calidad_aprobada(e.carpeta)}
        (e.carpeta / "ficha.json").write_text(json.dumps(f), encoding="utf-8")
        (e.carpeta / "miniatura.png").write_bytes(b"\x89PNG" + b"m" * 50)
        (e.carpeta / "video.mp4").write_bytes(b"v" * 300)
        (e.carpeta / f"{SLUG}-{VERSION}-gratis.zip").write_bytes(b"PK" + b"z" * 40)
        if self.render != e.render:
            e.eco(f"Aviso: el video salió con {self.render}")
        return {"render": self.render, "pedido": e.render}

    def dict(self) -> dict:
        return {"guion": self.guion, "calidad": self.calidad, "generar": self.generar}


def _encargo(tmp_path, tienda_url: str, **kw) -> Encargo:
    raiz = tmp_path / "publicaciones"
    kw.setdefault("llave", LLAVE)
    return Encargo(proyecto=7, carpeta=raiz / SLUG / VERSION, slug=SLUG, version=VERSION,
                   raiz=raiz, tienda=tienda_url, eco=kw.pop("eco", None), **kw)


def _estado(e: Encargo) -> dict:
    return json.loads((e.carpeta / fabrica.ESTADO).read_text(encoding="utf-8"))


# ------------------------------------------------------------------ la cadena
def test_cadena_completa_publica_y_deja_estado(tmp_path, falsa):
    p, salida = Pasos(), []
    e = _encargo(tmp_path, falsa.url, eco=salida.append)
    estado = fabrica.fabricar(e, pasos=p.dict())
    assert p.llamadas == ["guion", "generar"] and falsa.estado == "publicada"
    guardado = _estado(e)
    assert guardado == estado and fabrica.terminada(guardado)
    assert [guardado["pasos"][x]["estado"] for x in fabrica.PASOS] == ["hecho"] * 5
    assert guardado["pasos"]["tienda"]["datos"] == {"url": f"{falsa.url}/maquinas/{SLUG}",
                                                    "publicada": True}
    assert "guion escrito" in guardado["pasos"]["guion"]["salida"]
    texto = "\n".join(salida)
    assert f"Publicada en la tienda: {falsa.url}/maquinas/{SLUG}" in texto
    assert "cola de la tienda" in texto and "publicar youtube --cola" in texto
    for paso in fabrica.PASOS:
        assert f"  {paso}" in texto  # una fila de tiempos por paso
    assert LLAVE not in texto and LLAVE not in json.dumps(guardado)


def test_corte_a_mitad_retoma_desde_el_paso_que_fallo(tmp_path, falsa):
    p = Pasos()
    p.falla_generar = 1
    e = _encargo(tmp_path, falsa.url)
    with pytest.raises(FabricaError, match="(?s)paró en «generar».*se cortó la luz.*retoma"):
        fabrica.fabricar(e, pasos=p.dict())
    estado = _estado(e)
    assert estado["pasos"]["generar"]["estado"] == "fallo"
    assert "se cortó la luz" in estado["pasos"]["generar"]["error"]
    assert estado["pasos"]["generar"]["salida"] == ["video: 10/100 fotogramas"]
    assert "tienda" not in estado["pasos"] and falsa.importada is None
    # otra vez: guion y ficha no se repiten; generar y tienda sí
    assert fabrica.carpeta_de_trabajo(e.raiz, SLUG, None) == e.carpeta
    fabrica.fabricar(_encargo(tmp_path, falsa.url), pasos=p.dict())
    assert p.llamadas == ["guion", "generar", "generar"] and falsa.estado == "publicada"
    assert fabrica.terminada(_estado(e))


def test_ficha_en_rojo_para_la_cadena(tmp_path, falsa):
    p = Pasos(ficha=fichas.borrador("Mesa de taller", SLUG, VERSION))  # sin descripción
    e = _encargo(tmp_path, falsa.url)
    with pytest.raises(FabricaError, match="(?s)paró en «ficha».*descripcion.*modelador \\(D1\\)"):
        fabrica.fabricar(e, pasos=p.dict())
    assert p.llamadas == ["guion"] and falsa.llamadas == []
    estado = _estado(e)
    assert estado["pasos"]["ficha"]["estado"] == "fallo" and "generar" not in estado["pasos"]
    # el modelador la completa y la fábrica sigue desde la ficha
    (e.carpeta / "ficha.yaml").write_text(FICHA_OK, encoding="utf-8")
    fabrica.fabricar(_encargo(tmp_path, falsa.url), pasos=p.dict())
    assert p.llamadas == ["guion", "generar"] and falsa.estado == "publicada"


def test_borrador_no_publica_ni_entra_a_la_cola(tmp_path, falsa):
    salida = []
    e = _encargo(tmp_path, falsa.url, borrador=True, eco=salida.append)
    fabrica.fabricar(e, pasos=Pasos().dict())
    assert falsa.importada is not None and falsa.estado is None
    assert _estado(e)["pasos"]["tienda"]["datos"]["publicada"] is False
    assert any("Quedó en BORRADOR" in s and "No entra a la cola" in s for s in salida)


def test_desde_rehace_y_guion_existente_se_respeta(tmp_path, falsa):
    p = Pasos()
    e = _encargo(tmp_path, falsa.url)
    fabrica.fabricar(e, pasos=p.dict())
    salida = []
    fabrica.fabricar(_encargo(tmp_path, falsa.url, eco=salida.append), pasos=p.dict(),
                     desde="tienda")
    assert p.llamadas == ["guion", "generar"]  # sólo la tienda otra vez
    assert [r for _m, r in falsa.llamadas].count("/api/maquina/importacion") == 2
    assert any("[guion] hecho en una corrida anterior" in s for s in salida)
    # el paso real de guion no rehace un guion.json que ya está (el del modelador)
    e2 = _encargo(tmp_path, falsa.url, eco=salida.append)
    (e2.carpeta / "guion.json").write_text("{}", encoding="utf-8")
    # (un guion de diseño no lleva la máquina andando: ajuste D10, tests en test_fabrica_marcha)
    assert fabrica.paso_guion(e2) == {"ya_estaba": True, "marcha_s": None}
    assert (e2.carpeta / "guion.json").read_text(encoding="utf-8") == "{}"
    with pytest.raises(fabrica.PublicacionError, match="Paso desconocido"):
        fabrica.fabricar(e2, desde="youtube")


def test_sin_llave_falla_antes_de_trabajar(tmp_path):
    p = Pasos()
    e = _encargo(tmp_path, "https://apolocad.com", llave=None)
    with pytest.raises(LlaveFaltante):
        fabrica.fabricar(e, pasos=p.dict(), entorno={})
    assert p.llamadas == [] and not e.carpeta.exists()


def test_cae_a_vtk_y_lo_dice(tmp_path, falsa):
    p, salida = Pasos(), []
    p.render = "vtk"
    fabrica.fabricar(_encargo(tmp_path, falsa.url, eco=salida.append), pasos=p.dict())
    assert any("salió con vtk" in s for s in salida)


def test_carpeta_de_trabajo(tmp_path):
    raiz = tmp_path
    assert fabrica.carpeta_de_trabajo(raiz, SLUG, None).name == "1.0.0"  # nueva
    (raiz / SLUG / "1.0.0").mkdir(parents=True)
    (raiz / SLUG / "1.0.0" / "guion.json").write_text("{}", encoding="utf-8")
    (raiz / SLUG / "1.0.0" / "ficha.json").write_text("{}", encoding="utf-8")  # generada
    (raiz / SLUG / "1.0.1").mkdir()
    (raiz / SLUG / "1.0.1" / "guion.json").write_text("{}", encoding="utf-8")
    assert fabrica.carpeta_de_trabajo(raiz, SLUG, None).name == "1.0.1"  # la del guion pendiente
    # la generada con la tienda a medias gana (la fábrica la dejó así)
    (raiz / SLUG / "1.0.0" / fabrica.ESTADO).write_text(json.dumps(
        {"pasos": {"guion": {"estado": "hecho"}, "tienda": {"estado": "fallo"}}}),
        encoding="utf-8")
    assert fabrica.carpeta_de_trabajo(raiz, SLUG, None).name == "1.0.0"
    assert fabrica.carpeta_de_trabajo(raiz, SLUG, "2.0.0").name == "2.0.0"


# ------------------------------------------------------------------ el candado (D7)
def _ocupar(ruta: Path, *, pid: int | None = None, vence: float | None = None) -> None:
    import socket

    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps({"pid": pid or os.getpid(), "pc": socket.gethostname(),
                                "que": "faja 1.0.0 (proyecto 3)", "desde": time.time(),
                                "vence": vence or time.time() + 600, "ficha": "ajena"}),
                    encoding="utf-8")


def test_candado_ocupado_para_la_fabrica_sin_esperar(tmp_path, falsa, monkeypatch):
    candado = tmp_path / "render.lock"
    _ocupar(candado)
    llamado = []
    monkeypatch.setattr(flujo, "generar", lambda *a, **k: llamado.append(1))
    e = _encargo(tmp_path, falsa.url, candado=candado, sin_esperar=True)
    with pytest.raises(FabricaError, match="(?s)otra fábrica está grabando.*faja 1.0.0"):
        p = Pasos()
        fabrica.fabricar(e, pasos={"guion": p.guion, "calidad": p.calidad})
    assert llamado == [] and _estado(e)["pasos"]["generar"]["estado"] == "fallo"
    assert json.loads(candado.read_text(encoding="utf-8"))["ficha"] == "ajena"  # no lo tocó


def test_candado_espera_con_avisos_y_toma_al_soltarse(tmp_path):
    candado = tmp_path / "render.lock"
    _ocupar(candado)
    salida = []
    threading.Timer(0.3, candado.unlink).start()
    with Candado(candado, que="mesa", espera_s=0.05, aviso_s=10, eco=salida.append) as c:
        assert json.loads(candado.read_text(encoding="utf-8"))["que"] == "mesa"
        assert c.esperado_s > 0
    assert not candado.exists()  # lo suelta al salir
    assert sum("Espero: otra fábrica está grabando" in s for s in salida) == 1
    assert any("libre tras" in s for s in salida)


def test_candado_vencido_o_de_un_proceso_muerto_se_toma(tmp_path):
    candado = tmp_path / "render.lock"
    _ocupar(candado, vence=time.time() - 1)
    salida = []
    with Candado(candado, sin_esperar=True, eco=salida.append):
        pass
    assert any("venció" in s for s in salida)
    muerto = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"],
                            capture_output=True, text=True, check=True)
    _ocupar(candado, pid=int(muerto.stdout))
    with Candado(candado, sin_esperar=True, eco=salida.append):
        pass
    assert any("ya no existe" in s for s in salida)
    _ocupar(candado)  # el de este proceso, vivo: no se toma
    with pytest.raises(CandadoOcupado, match="--sin-esperar"):
        Candado(candado, sin_esperar=True, eco=None).tomar()


def test_paso_generar_real_toma_el_candado(tmp_path, monkeypatch):
    candado = tmp_path / "render.lock"
    visto = []

    def generar(*_a, **kw):
        visto.append((candado.exists(), kw["render"], kw["nivel"]))
        return {"video": {"render": "vtk"}, "calidad": {"veredicto": "VERDE"},
                "tiempos_s": {"video": 1.0}}

    monkeypatch.setattr(flujo, "generar", generar)
    salida = []
    e = _encargo(tmp_path, "https://apolocad.com", candado=candado, eco=salida.append)
    d = fabrica.paso_generar(e)
    assert visto == [(True, "navegador", "rapido")] and not candado.exists()
    assert d["render"] == "vtk" and any("cae a VTK" in s for s in salida)


# ------------------------------------------------------------------ el CLI
def test_cli_fabrica(tmp_path, falsa, monkeypatch, capsys):
    p = Pasos()
    monkeypatch.setattr(fabrica, "PASOS_REALES", {**fabrica.PASOS_REALES, **p.dict()})
    monkeypatch.setattr(paths, "publicaciones_dir", lambda: tmp_path)
    monkeypatch.setenv("APOLO_TIENDA_LLAVE", LLAVE)
    argv = ["fabrica", "--project", "7", "--slug", SLUG, "--tienda", falsa.url]
    assert _cli().main(argv) == 0
    out = capsys.readouterr().out
    assert f"Publicada en la tienda: {falsa.url}/maquinas/{SLUG}" in out and LLAVE not in out
    assert (tmp_path / SLUG / VERSION / fabrica.ESTADO).is_file()
    p.falla_generar = 1
    assert _cli().main([*argv, "--desde", "generar"]) == 2
    assert "paró en «generar»" in capsys.readouterr().err
