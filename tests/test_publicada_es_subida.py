"""«Publicada» = SUBIDA a la tienda (plan puerta-de-publicacion, F6). `paquete.publicada` era «la
carpeta tiene `ficha.json`»: una versión generada y nunca subida no se podía rehacer (ni su guion
ni su paquete). Hoy la subida deja `subida.json` y lo generado antes del cambio sigue intocable."""

# ruff: noqa: F811 — `falsa`, `paquete` y `repo_fabrica` son fixtures importados
from __future__ import annotations

import json

from test_publicar_tienda import (  # noqa: F401 — fixtures
    LLAVE,
    falsa,
    paquete,
    repo_fabrica,
)

from apolo.publicacion import fabrica, flujo
from apolo.publicacion import paquete as pq
from apolo.publicacion import tienda as tiendas
from apolo.publicacion.fabrica import Encargo


def _escribir(carpeta, nombre: str, datos) -> None:
    (carpeta / nombre).write_text(json.dumps(datos), encoding="utf-8")


def test_que_es_publicada(tmp_path):
    c = tmp_path / "x" / "1.0.0"
    c.mkdir(parents=True)
    assert not pq.publicada(c) and not pq.generada(c)
    _escribir(c, pq.FICHA_JSON, {})
    assert pq.generada(c) and pq.publicada(c)  # de antes del cambio: no se sabe, no se pisa
    _escribir(c, "generacion.json", {"registra_subida": True})
    assert not pq.publicada(c)  # generada hoy y nunca subida
    _escribir(c, pq.SUBIDA, {"publicada": False})
    assert not pq.publicada(c)  # en borrador: se puede regenerar y volver a subir
    _escribir(c, pq.SUBIDA, {"publicada": True})
    assert pq.publicada(c)
    (c / pq.SUBIDA).unlink()
    _escribir(c, fabrica.ESTADO, {"pasos": {"generar": {"estado": "hecho"}}})
    assert not pq.publicada(c)  # la fábrica no llegó a la tienda
    _escribir(c, fabrica.ESTADO, {"pasos": {"tienda": {"estado": "hecho",
                                                       "datos": {"publicada": True}}}})
    assert pq.publicada(c)


def test_subir_registra_la_subida(falsa, paquete):
    tiendas.subir(paquete, tienda=falsa.url, llave=LLAVE, eco=None, espera_s=0, borrador=True)
    sub = json.loads((paquete / pq.SUBIDA).read_text(encoding="utf-8"))
    assert sub["publicada"] is False and sub["url"].endswith("/maquinas/mesa-de-taller")
    assert not pq.publicada(paquete)
    tiendas.subir(paquete, tienda=falsa.url, llave=LLAVE, eco=None, espera_s=0)
    assert pq.publicada(paquete)
    assert pq.SUBIDA not in [p.name for p in tiendas.contenido(paquete)[1]]  # no se ofrece


def test_generada_y_no_subida_se_rehace(tmp_path, monkeypatch):
    raiz = tmp_path / "publicaciones"
    c = raiz / "mesa" / "1.0.0"
    c.mkdir(parents=True)
    _escribir(c, pq.FICHA_JSON, {})
    _escribir(c, "generacion.json", {"registra_subida": True})
    llamadas = []

    def generar(*_a, **kw):
        llamadas.append(kw["version"])
        return {"video": {"render": "navegador"}, "calidad": {"veredicto": "VERDE"},
                "tiempos_s": {}}

    monkeypatch.setattr(flujo, "generar", generar)
    salida = []
    e = Encargo(proyecto=7, carpeta=c, slug="mesa", version="1.0.0", raiz=raiz,
                tienda="https://apolocad.com", candado=tmp_path / "render.lock",
                eco=salida.append)
    assert "ya_estaba" not in fabrica.paso_generar(e) and llamadas == ["1.0.0"]
    assert any("no se subió a la tienda: la regenero" in s for s in salida)
    pq.exigir_no_publicada(c)  # flujo.guion y flujo.generar no la rechazan
    pq.registrar_subida(c, url="u", publicada_=True, maquina=1)
    assert fabrica.paso_generar(e) == {"ya_estaba": True} and llamadas == ["1.0.0"]
    # instalar (un paquete nuevo) borra el registro de una subida anterior en borrador
    pq.registrar_subida(c, url="u", publicada_=False, maquina=1)
    staging = c / ".tmp"
    staging.mkdir()
    pq.instalar(staging, c, {"slug": "mesa"}, {})
    assert not (c / pq.SUBIDA).exists() and not pq.publicada(c)
