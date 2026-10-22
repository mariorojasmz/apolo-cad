"""Revisión y aprobación en el flujo de publicación (plan puerta-de-publicacion, F4 · D6, D7,
D10, D11): lo NO determinista (revisores LLM, Mario) se exige de forma determinista, sobre la
MISMA firma del modelo y el MISMO video que se publican.

- `revision.json`: ausente, de otra firma, ALTA abierta, cerrada por la misma revisión, por quien
  corrigió o por el que la encontró → PARA; cerrada por una re-revisión a ciegas → pasa;
  «asumido» no cierra.
- `cuadros.json`: de otro video o con un cuadro rechazado → PARA.
- Familia nueva: 0 o 1 máquinas aprobadas → PARA y `publicar aprobar` la destraba; sin el repo
  privado → PARA con el porqué.
- La fábrica para en cada paso nuevo y `tienda.subir` se niega en cada caso (antes de llamar a
  la tienda).
"""

# ruff: noqa: F811 — `falsa`, `paquete` y `repo_fabrica` son fixtures importados de otro test
from __future__ import annotations

import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from test_publicar_tienda import (  # noqa: F401 — fixtures
    FAMILIA,
    FIRMA,
    LLAVE,
    SLUG,
    VERSION,
    _cli,
    cuadros_aprobados,
    falsa,
    familia_aprobada,
    paquete,
    repo_fabrica,
)

from apolo import paths
from apolo.design import revision as design_rev
from apolo.publicacion import aprobacion, fabrica, tienda
from apolo.publicacion import revision_check as rc
from apolo.publicacion.aprobacion import AprobacionError
from apolo.publicacion.fabrica import Encargo, FabricaError
from apolo.publicacion.paquete import PublicacionError

F2 = "f1rma0corregida000000"


def _hallazgo(sev="ALTA", estado="abierto", **kw) -> dict:
    return {"pieza": "c12 «Perno tensor»", "pregunta": "tensado",
            "evidencia": "measure c12-c40: 38 mm de perno para 52 mm de paquete",
            "severidad": sev, "estado": estado, **kw}


def _rev(id_="r1", revisor="revisor-a", firma=FIRMA, hallazgos=()) -> dict:
    return {"id": id_, "revisor": revisor, "firma": firma, "fecha": "2026-10-22T10:00:00",
            "hallazgos": list(hallazgos)}


def _cerrado(revision="r2", **kw) -> dict:
    return _hallazgo(estado="cerrado", corregido_por="modelador-b",
                     cerrado_por={"revision": revision,
                                  "evidencia": "measure c12-c40: 70 mm, cruza las dos aletas"},
                     **kw)


def _doc(*revs) -> dict:
    return {"formato": 1, "revisiones": list(revs)}


# ------------------------------------------------------------------ D6: el validador puro
def test_las_constantes_son_las_de_design():
    assert rc.SEVERIDADES == tuple(design_rev.SEVERIDADES)
    assert rc.ESTADOS == design_rev.ESTADOS_HALLAZGO
    assert rc.BLOQUEAN == design_rev.SEVERIDADES_QUE_BLOQUEAN
    assert rc.CAMPOS_HALLAZGO == design_rev.CAMPOS_HALLAZGO
    assert rc.CAMPOS_REVISION == design_rev.CAMPOS_REVISION
    assert "revision.json" in design_rev.plantilla_revisor()


def test_sin_revision_o_de_otra_firma_para():
    assert "no hay revision.json" in rc.problemas_revision(None, FIRMA)[0]
    p = rc.problemas_revision(_doc(_rev(firma="otra")), FIRMA)
    assert len(p) == 1 and "falta una re-revisión a ciegas de ESTA versión" in p[0]
    assert "formato" in rc.problemas_revision({"revisiones": "x"}, FIRMA)[0]
    p = rc.problemas_revision(_doc({"id": "r1", "firma": FIRMA}), FIRMA)
    assert any("falta «revisor»" in x for x in p) and any("hallazgos" in x for x in p)


def test_baja_abierta_pasa_y_alta_o_media_abierta_para():
    assert rc.problemas_revision(_doc(_rev(hallazgos=[_hallazgo("BAJA")])), FIRMA) == []
    for sev in ("ALTA", "MEDIA"):
        for estado in ("abierto", "corregido"):
            p = rc.problemas_revision(_doc(_rev(hallazgos=[_hallazgo(sev, estado)])), FIRMA)
            assert len(p) == 1 and f"{sev} {estado}" in p[0] and "re-revisión" in p[0], p


def test_cerrada_por_una_re_revision_a_ciegas_pasa():
    doc = _doc(_rev("r1", "revisor-a", FIRMA, [_cerrado()]), _rev("r2", "revisor-c", F2))
    assert rc.problemas_revision(doc, F2) == []


@pytest.mark.parametrize(("cambio", "texto"), [
    # la misma revisión que lo encontró (o una anterior) no la cierra
    (lambda d: d["revisiones"][0]["hallazgos"][0]["cerrado_por"].update(revision="r1"),
     "no es POSTERIOR"),
    # la re-revisión es de la versión corregida: otra firma
    (lambda d: d["revisiones"][1].update(firma=FIRMA), "la misma firma"),
    # no la cierra quien corrigió
    (lambda d: d["revisiones"][1].update(revisor="modelador-b"), "el mismo que lo corrigió"),
    # ni el revisor que la encontró (no sería a ciegas)
    (lambda d: d["revisiones"][1].update(revisor="revisor-a"), "el mismo revisor que lo encontró"),
    (lambda d: d["revisiones"][0]["hallazgos"][0]["cerrado_por"].update(revision="r9"),
     "no es ninguna revisión"),
    (lambda d: d["revisiones"][0]["hallazgos"][0].pop("corregido_por"), "corregido_por"),
    (lambda d: d["revisiones"][0]["hallazgos"][0].update(cerrado_por="r2"), "cerrado_por"),
    (lambda d: d["revisiones"][0]["hallazgos"][0]["cerrado_por"].update(evidencia=""),
     "evidencia"),
])
def test_un_cierre_que_no_es_a_ciegas_no_cierra(cambio, texto):
    doc = _doc(_rev("r1", "revisor-a", FIRMA, [_cerrado()]), _rev("r2", "revisor-c", F2))
    cambio(doc)
    p = rc.problemas_revision(doc, F2)
    assert any(texto in x for x in p), p


def test_asumido_no_cierra():
    p = rc.problemas_revision(_doc(_rev(hallazgos=[_hallazgo(estado="asumido")])), FIRMA)
    assert any("«asumido» no es un cierre" in x for x in p), p
    doc = _doc(_rev("r1", "revisor-a", FIRMA, [_cerrado()]), _rev("r2", "revisor-c", F2))
    doc["revisiones"][0]["hallazgos"][0]["cerrado_por"]["evidencia"] = \
        "asumido: el catálogo no tiene el largo"
    assert any("«asumido» no cierra" in x for x in rc.problemas_revision(doc, F2))
    # en una BAJA tampoco es un estado válido
    p = rc.problemas_revision(_doc(_rev(hallazgos=[_hallazgo("BAJA", "asumido")])), FIRMA)
    assert any("asumido" in x for x in p)


def test_ids_repetidos_y_alta_de_la_ultima_revision():
    p = rc.problemas_revision(_doc(_rev("r1"), _rev("r1")), FIRMA)
    assert any("repetido" in x for x in p)
    # la ALTA que encuentra la última revisión no la puede cerrar nadie: bloquea
    doc = _doc(_rev("r1", "revisor-a", FIRMA, [_cerrado(revision="r1")]))
    assert any("no es POSTERIOR" in x for x in rc.problemas_revision(doc, FIRMA))


# ------------------------------------------------------------------ D7: cuadros
def _cuadros(sha="abc", **veredictos) -> dict:
    return {"formato": 1, "video": {"archivo": "video.mp4", "sha256": sha},
            "cuadros": [{"momento": m, "archivo": f"cuadros/{m}.png",
                         "veredicto": veredictos.get(m, "OK"), "nota": "la banda cruza la guarda"}
                        for m in rc.MOMENTOS], "revisor": "vision-1"}


def test_cuadros():
    assert rc.problemas_cuadros(_cuadros(), "abc") == []
    assert "otro video" in rc.problemas_cuadros(_cuadros(), "def")[0]
    p = rc.problemas_cuadros(_cuadros(marcha="RECHAZADO"), "abc")
    assert p == ["el cuadro «marcha» fue RECHAZADO: la banda cruza la guarda"]
    assert "no tiene veredicto" in rc.problemas_cuadros(_cuadros(cierre=None), "abc")[0]
    sin = _cuadros()
    sin["cuadros"].pop(0)
    sin["revisor"] = None
    p = rc.problemas_cuadros(sin, "abc")
    assert any("falta el cuadro «armado»" in x for x in p) and any("revisor" in x for x in p)
    assert "no hay cuadros.json" in rc.problemas_cuadros(None, "abc")[0]


def test_momentos_salen_del_guion():
    g = {"video": {"fps": 10}, "portada": {"duracion_s": 2}, "orbita": {"duracion_s": 4},
         "cierre": {"duracion_s": 4}, "marcha": {"duracion_s": 6},
         "etapas": [{"duracion_s": 10}, {"duracion_s": 8}]}
    assert aprobacion.momentos(g, 34.0) == [("armado", 16.0, "etapa"), ("marcha", 23.0, "marcha"),
                                           ("cierre", 32.0, "cierre")]
    g.pop("marcha")
    assert aprobacion.momentos(g, 28.0)[1] == ("marcha", 22.0, "orbita")
    assert aprobacion.momentos(None, 10.0) == [("armado", 4.0, "proporcion"),
                                              ("marcha", 7.5, "proporcion"),
                                              ("cierre", 9.7, "proporcion")]


def _ffmpeg():
    from apolo.publicacion.video import ffmpeg_disponible

    if not ffmpeg_disponible():
        pytest.skip("sin ffmpeg")
    from apolo.media.codificar import buscar_ffmpeg

    return buscar_ffmpeg()


def test_preparar_cuadros_saca_tres_pngs_y_respeta_los_veredictos(tmp_path):
    ffmpeg = _ffmpeg()
    carpeta = tmp_path / "v"
    carpeta.mkdir()
    subprocess.run([ffmpeg, "-v", "error", "-f", "lavfi", "-i", "testsrc=size=64x48:rate=10",
                    "-t", "3", "-pix_fmt", "yuv420p", "-y", str(carpeta / "video.mp4")],
                   check=True, capture_output=True)
    eco: list[str] = []
    d = aprobacion.preparar_cuadros(carpeta, eco=eco.append)
    assert [c["momento"] for c in d["cuadros"]] == list(rc.MOMENTOS)
    assert all((carpeta / c["archivo"]).is_file() and c["veredicto"] is None for c in d["cuadros"])
    with pytest.raises(AprobacionError, match="(?s)no tiene veredicto.*agente con visión"):
        aprobacion.exigir_cuadros(carpeta)
    # el agente con visión aprueba: se respeta, no se rehace
    for c in d["cuadros"]:
        c["veredicto"] = "OK"
    d["revisor"] = "vision-1"
    (carpeta / "cuadros.json").write_text(json.dumps(d), encoding="utf-8")
    assert aprobacion.preparar_cuadros(carpeta)["revisor"] == "vision-1"
    assert aprobacion.exigir_cuadros(carpeta)["revisor"] == "vision-1"
    # otro video: los veredictos ya no valen, se sacan de nuevo
    (carpeta / "video.mp4").write_bytes((carpeta / "video.mp4").read_bytes() + b"\0")
    with pytest.raises(AprobacionError, match="otro video"):
        aprobacion.exigir_cuadros(carpeta)


# ------------------------------------------------------------------ D10: familia
def test_familia_nueva_para_hasta_que_mario_aprueba():
    assert rc.problemas_familia({}, "", "a", "1.0.0", FIRMA)[0].startswith("la ficha")
    p = rc.problemas_familia({}, "Faja de banda", "a", "1.0.0", FIRMA)
    assert "0 de 2" in p[0] and "publicar.py aprobar --slug a --version 1.0.0" in p[0]
    reg = rc.registrar({}, "Faja de banda", slug="a", version="1.0.0", firma=FIRMA, por="Mario",
                       fecha="x")
    assert rc.problemas_familia(reg, "faja  de BANDA", "a", "1.0.0", FIRMA) == []
    # la aprobación es de ESA firma: si el modelo cambió, se vuelve a pedir
    assert "el modelo cambió" in rc.problemas_familia(reg, "Faja de banda", "a", "1.0.0", F2)[0]
    # 1 aprobada: la segunda máquina también la aprueba Mario
    assert "1 de 2" in rc.problemas_familia(reg, "Faja de banda", "b", "1.0.0", FIRMA)[0]
    reg = rc.registrar(reg, "Faja de banda", slug="b", version="1.0.0", firma=FIRMA, por="Mario",
                       fecha="x")
    # con 2 máquinas aprobadas, la familia ya no es nueva
    assert rc.problemas_familia(reg, "Faja de banda", "c", "1.0.0", F2) == []


def test_sin_repo_privado_para_con_el_porque(tmp_path, monkeypatch):
    monkeypatch.setenv("APOLO_FABRICA", str(tmp_path / "no-esta"))
    with pytest.raises(AprobacionError, match="(?s)No encuentro el repo privado apolo-fabrica"
                                              ".*APOLO_FABRICA.*Sin él no se publica"):
        aprobacion.registro()
    p = aprobacion.problemas_familia(tmp_path, SLUG, VERSION)
    assert len(p) == 1 and "apolo-fabrica" in p[0]


def test_fabrica_dir_por_defecto(monkeypatch):
    monkeypatch.delenv("APOLO_FABRICA", raising=False)
    raiz = paths.repo_root()
    esperado = (raiz.parent if raiz else paths.home()) / "apolo-fabrica"
    assert paths.fabrica_dir() == esperado


# ------------------------------------------------------------------ tienda.subir se niega
def _subir(f, carpeta, **kw):
    return tienda.subir(carpeta, tienda=f.url, llave=LLAVE, eco=None, espera_s=0, **kw)


def _escribir(ruta: Path, datos) -> None:
    ruta.write_text(json.dumps(datos), encoding="utf-8")


def _rev_alta(c):
    _escribir(c / "revision.json", _doc(_rev(hallazgos=[_hallazgo()])))


def _rev_misma(c):
    d = _doc(_rev("r1", "revisor-a", FIRMA, [_cerrado(revision="r1")]))
    _escribir(c / "revision.json", d)


def _sin_registro(c):
    shutil.rmtree(Path(paths.fabrica_dir()))


@pytest.mark.parametrize(("estropear", "texto"), [
    (lambda c: (c / "revision.json").unlink(), "revisión de taller: no hay revision.json"),
    (lambda c: _escribir(c / "revision.json", _doc(_rev(firma="otra"))), "ESTA versión"),
    (_rev_alta, "ALTA abierto"),
    (_rev_misma, "no es POSTERIOR"),
    (lambda c: (c / "revision.json").write_text("{roto", encoding="utf-8"), "no es JSON válido"),
    (lambda c: (c / "cuadros.json").unlink(), "no hay cuadros.json"),
    (lambda c: (c / "video.mp4").write_bytes(b"otro video"), "otro video"),
    (lambda c: _escribir(c / "cuadros.json", {**cuadros_aprobados(c), "cuadros": [
        {"momento": m, "veredicto": "RECHAZADO" if m == "cierre" else "OK", "nota": "negro"}
        for m in rc.MOMENTOS]}), "«cierre» fue RECHAZADO"),
    (lambda c: (Path(paths.fabrica_dir()) / "familias.json").unlink(), "0 de 2"),
    (_sin_registro, "No encuentro el repo privado"),
    (lambda c: (c / "ficha.yaml").write_text("familia: \"\"\n", encoding="utf-8"),
     "no declara su «familia»"),
])
def test_la_tienda_no_recibe_sin_revision_cuadros_ni_familia(falsa, paquete, estropear, texto):
    estropear(paquete)
    for ensayo in (False, True):
        with pytest.raises(PublicacionError, match=texto):
            _subir(falsa, paquete, ensayo=ensayo)
    assert falsa.llamadas == []


def test_una_familia_con_dos_maquinas_aprobadas_sube_sin_pedir(falsa, paquete, repo_fabrica):
    (repo_fabrica / "familias.json").unlink()
    familia_aprobada(repo_fabrica, slug="otra-mesa")
    with pytest.raises(PublicacionError, match="1 de 2"):
        _subir(falsa, paquete, ensayo=True)
    familia_aprobada(repo_fabrica, slug="mesa-chica")
    assert _subir(falsa, paquete)["publicada"]


# ------------------------------------------------------------------ la fábrica
def _encargo(paquete_: Path, url: str, eco=None) -> Encargo:
    return Encargo(proyecto=7, carpeta=paquete_, slug=SLUG, version=VERSION,
                   raiz=paquete_.parents[1], tienda=url, llave=LLAVE, eco=eco)


def _nada(_e):
    return {}


def _estado_hecho(carpeta: Path, hasta: str) -> None:
    """estado.json con los pasos hasta `hasta` (excluido) hechos, como los dejaría la fábrica."""
    pasos = {p: {"estado": "hecho", "segundos": 0.0} for p in
             fabrica.PASOS[:fabrica.PASOS.index(hasta)]}
    _escribir(carpeta / fabrica.ESTADO, {"formato": 1, "pasos": pasos})


@pytest.mark.parametrize(("estropear", "paso", "texto"), [
    (_rev_alta, "revision", "ALTA abierto.*retoma desde «revision»"),
    (lambda c: (c / "cuadros.json").write_text(json.dumps(
        {**json.loads((c / "cuadros.json").read_text(encoding="utf-8")), "revisor": ""}),
        encoding="utf-8"), "cuadros", "quién revisó.*retoma desde «cuadros»"),
    (lambda c: (Path(paths.fabrica_dir()) / "familias.json").unlink(), "familia",
     "Familia nueva.*0 de 2.*publicar.py aprobar --slug mesa-de-taller"),
])
def test_la_fabrica_para_en_cada_paso_nuevo(falsa, paquete, estropear, paso, texto):
    estropear(paquete)
    _estado_hecho(paquete, "revision")
    # generar no se rehace (ya hay ficha.json); los pasos de la API ya corrieron
    with pytest.raises(FabricaError, match=f"(?s)paró en «{paso}».*{texto}"):
        fabrica.fabricar(_encargo(paquete, falsa.url), pasos={"generar": _nada})
    estado = fabrica.leer_estado(paquete)
    assert estado["pasos"][paso]["estado"] == "fallo"
    assert "tienda" not in estado["pasos"] and falsa.llamadas == []


def test_aprobar_destraba_la_familia_y_publica(falsa, paquete, repo_fabrica, capsys,
                                               monkeypatch):
    (repo_fabrica / "familias.json").unlink()
    _estado_hecho(paquete, "revision")
    with pytest.raises(FabricaError, match="paró en «familia»"):
        fabrica.fabricar(_encargo(paquete, falsa.url), pasos={"generar": _nada})
    monkeypatch.setattr(paths, "publicaciones_dir", lambda: paquete.parents[1])
    assert _cli().main(["aprobar", "--slug", SLUG]) == 0  # la versión: la no terminada
    out = capsys.readouterr().out
    assert "Aprobada: «mesa-de-taller» 1.0.0" in out and "1 de 2" in out and "git -C" in out
    reg = json.loads((repo_fabrica / "familias.json").read_text(encoding="utf-8"))
    (a,) = rc.aprobadas(reg, FAMILIA)
    assert (a["slug"], a["version"], a["firma"], a["por"]) == (SLUG, VERSION, FIRMA, "Mario")
    estado = fabrica.fabricar(_encargo(paquete, falsa.url), pasos={"generar": _nada})
    assert fabrica.terminada(estado) and falsa.estado == "publicada"
    assert estado["pasos"]["familia"]["datos"] == {"familia": FAMILIA, "aprobadas": 1}


def test_aprobar_se_niega_si_falta_lo_demas(paquete, repo_fabrica, monkeypatch, capsys):
    (repo_fabrica / "familias.json").unlink()
    _rev_alta(paquete)
    monkeypatch.setattr(paths, "publicaciones_dir", lambda: paquete.parents[1])
    assert _cli().main(["aprobar", "--slug", SLUG, "--version", VERSION]) == 2
    assert "antes tiene que pasar todo lo demás" in capsys.readouterr().err
    assert not (repo_fabrica / "familias.json").exists()


def test_la_ficha_sin_familia_para_la_fabrica(tmp_path, monkeypatch):
    from apolo.publicacion import preparar

    monkeypatch.setattr(preparar, "revisar", lambda *a, **k: None)
    carpeta = tmp_path / SLUG / VERSION
    carpeta.mkdir(parents=True)
    (carpeta / "ficha.yaml").write_text('familia: ""\n', encoding="utf-8")
    with pytest.raises(FabricaError, match="no declara su «familia»"):
        fabrica.paso_ficha(_encargo(carpeta, "https://apolocad.com"))
    (carpeta / "ficha.yaml").write_text('familia: "Faja de banda"\n', encoding="utf-8")
    assert fabrica.paso_ficha(_encargo(carpeta, "https://apolocad.com")) == {
        "familia": "Faja de banda"}


def test_sin_forzar_en_la_fabrica_ni_en_la_tienda():
    """D11: ni la fábrica ni `subir` ni `aprobar` aceptan --forzar."""
    ap = _cli()._parser()
    for paso in (["fabrica", "--project", "7"], ["subir", "--slug", SLUG],
                 ["aprobar", "--slug", SLUG]):
        with pytest.raises(SystemExit):
            ap.parse_args([*paso, "--forzar"])
    import inspect

    for f in (fabrica.fabricar, tienda.subir, aprobacion.aprobar):
        assert "forzar" not in inspect.signature(f).parameters


def test_una_version_publicada_antes_de_f4_sigue_terminada():
    viejo = {"pasos": {p: {"estado": "hecho"} for p in
                       ("guion", "ficha", "calidad", "generar", "tienda")}}
    assert fabrica.terminada(viejo)
    assert not fabrica.terminada(copy.deepcopy({"pasos": {"guion": {"estado": "hecho"}}}))
