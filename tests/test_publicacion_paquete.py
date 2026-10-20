"""Las piezas del paquete de tienda, sin API (plan publicacion-tienda, F4): el `.apolo`
saneado (D12), la puerta de calidad (D13), los capítulos de YouTube (D15), los zips sin lo
prohibido (D11) y la línea de tiempo del video."""

from __future__ import annotations

import io
import json
import re
import zipfile

import pytest

from apolo.doc.document import Document
from apolo.publicacion import linea_tiempo as lt
from apolo.publicacion import paquete, saneo, textos
from apolo.services.guion_video import capitulos, duracion_total

SECRETO = "nota interna: el cliente paga 30 % más"


def _origen() -> Document:
    d = Document("Faja de origen")
    d.execute("set_variable", {"name": "L", "expression": "500"})
    d.execute("create_box", {"name": "Base", "width": "=L", "depth": 100, "height": 20})
    d.agent_notes.append(SECRETO + " (embebida)")
    d.set_requirements({"carga_kg": 10, "tipo_cambio": 3.7})
    return d


def _layout() -> Document:
    d = Document("Layout interno")
    sub = d.add_attachment(_origen().to_apolo_bytes())
    d.execute("create_box", {"name": "Piso", "width": 2000, "depth": 1000, "height": 10,
                             "position": {"x": 0, "y": 0, "z": -10}})
    d.commands.append({"id": "c99", "type": "insert_project",
                       "params": {"project_id": 38, "attachment": sub, "name": "Faja",
                                  "overrides": {"L": 700}}})
    d.regenerate()
    d.agent_notes += [SECRETO, "otra nota"]
    d.set_requirements({"carga_kg": 50, "tipo_cambio": 3.7, "moneda": "PEN", "producto": "cajas"})
    return d


def _todo_el_texto(data: bytes) -> str:
    """Todo lo legible del .apolo, también adentro de los snapshots embebidos."""
    partes = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for n in zf.namelist():
            blob = zf.read(n)
            if blob[:2] == b"PK":
                partes.append(_todo_el_texto(blob))
            else:
                partes.append(blob.decode("utf-8", "replace"))
    return "\n".join(partes)


def test_el_apolo_saneado_no_trae_notas_ni_precios_y_regenera_igual():
    d = _layout()
    limpio, informe = saneo.sanear_apolo(d.to_apolo_bytes(), nombre="Layout de dos fajas")
    texto = _todo_el_texto(limpio)
    assert SECRETO not in texto and "agent_notes" not in texto
    assert "tipo_cambio" not in texto and "moneda" not in texto
    assert '"project_id"' not in texto  # apunta a la base de quien publica
    assert any("2 notas del agente" == q for q in informe["quitado"])
    assert any("embebido" in q for q in informe["quitado"])
    assert informe["adjuntos"] == [] and informe["desconocido"] == []
    # se abre y regenera IGUAL (mismas piezas y volúmenes), con el título público
    abierto = Document.from_apolo_bytes(limpio)
    assert abierto.name == "Layout de dos fajas" and abierto.agent_notes == []
    assert abierto.requirements == {"carga_kg": 50.0, "producto": "cajas"}
    assert set(abierto.scene) == set(d.scene)
    for fid, feat in d.scene.items():
        assert abierto.scene[fid].shape.volume == pytest.approx(feat.shape.volume)


def test_la_lista_blanca_cubre_el_manifest_de_hoy():
    """Una clave nueva del manifest obliga a decidir si es pública (D12): si no está en
    `MANIFEST_PUBLICO`, el saneo la quitaría en silencio y el comprador recibiría un diseño
    incompleto."""
    with zipfile.ZipFile(io.BytesIO(Document("x").to_apolo_bytes())) as zf:
        claves = set(json.loads(zf.read("manifest.json")))
    assert claves - {"agent_notes"} == set(saneo.MANIFEST_PUBLICO)


def test_lo_desconocido_se_quita_y_se_informa():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"app": "genix-apolo-cad", "version": 2,
                                                 "secreto_nuevo": 1}))
        zf.writestr("commands.json", "[]")
        zf.writestr("notas/privadas.txt", "x")
        zf.writestr("attachments/abc.bin", b"ISO-10303-21; un STEP de proveedor")
    limpio, informe = saneo.sanear_apolo(buf.getvalue())
    with zipfile.ZipFile(io.BytesIO(limpio)) as zf:
        assert sorted(zf.namelist()) == ["attachments/abc.bin", "commands.json", "manifest.json"]
        assert "secreto_nuevo" not in json.loads(zf.read("manifest.json"))
    assert informe["desconocido"] == ["entrada «notas/privadas.txt»",
                                      "clave «secreto_nuevo» del manifest"]
    assert informe["adjuntos"][0]["digest"] == "abc"  # un STEP: se publica, pero se avisa


# ------------------------------------------------------------------ puerta (D13)
_ROJO = {"veredicto": "ROJO", "bloqueantes": [{"regla": "sujeción · sin anclajes",
                                               "detalle": "6 sólidos y 0 anclajes"}],
         "avisos": [], "no_aplica": ["gravedad (opt-in)"], "resumen": {"chequeos_ok": ["interferencias"]}}


def test_la_puerta_roja_se_niega_y_forzada_queda_con_observaciones():
    with pytest.raises(paquete.PuertaRoja, match="sujeción · sin anclajes") as exc:
        paquete.calidad(_ROJO, forzar=False)
    assert "--forzar" in str(exc.value)
    cal = paquete.calidad(_ROJO, forzar=True)
    assert cal["con_observaciones"] and cal["observaciones"] == [
        "sujeción · sin anclajes: 6 sólidos y 0 anclajes"]
    ficha = {"titulo": "M", "version": "1.0.0", "descripcion": "d", "nivel": "gratis",
             "precio_usd": 0, "url_tienda": "", "licencias": {"gratis": "CC BY-NC 4.0",
                                                              "completo": "Otra"}}
    leeme = textos.leeme(ficha, "gratis", cifras=[], calidad=cal, archivos=[])
    assert "con observaciones" in leeme and "6 sólidos y 0 anclajes" in leeme
    assert "No evaluado: la estabilidad con gravedad" in leeme
    verde = paquete.calidad({**_ROJO, "veredicto": "VERDE", "bloqueantes": []}, forzar=False)
    assert not verde["con_observaciones"] and verde["observaciones"] == []


# ------------------------------------------------------------------ YouTube (D15)
def _guion_largo() -> dict:
    etapas = [{"titulo": t, "texto": "", "pasos": [i + 1], "duracion_s": s}
              for i, (t, s) in enumerate([("Bastidor", 12.0), ("Rodillos", 4.0),
                                          ("Transmisión <motor>", 14.0), ("Guardas", 11.0)])]
    return {"version": 1, "idioma": "es", "documento": {"nombre": "x", "comandos": 9, "firma": "f"},
            "titulo": "T", "subtitulo": "", "video": {"ancho": 320, "alto": 180, "fps": 30},
            "portada": {"duracion_s": 4.0}, "etapas": etapas,
            "cifras": {"titulo": "En cifras", "items": [{"etiqueta": "Piezas", "valor": "9"}],
                       "duracion_s": 6.0},
            "orbita": {"duracion_s": 8.0}, "cierre": {"texto": "Fin", "url": "", "duracion_s": 5.0}}


def _segundos(marca: str) -> int:
    partes = [int(x) for x in marca.split(":")]
    return sum(p * 60 ** i for i, p in enumerate(reversed(partes)))


def test_youtube_txt_trae_capitulos_que_youtube_acepta():
    g = _guion_largo()
    ficha = {"titulo": "Transportador", "descripcion": "Un transportador.",
             "url_tienda": "https://tienda.example/transportador", "etiquetas": ["a", "b"],
             "musica": {"titulo": "Pista", "autor": "Autor", "fuente": "YouTube",
                        "licencia": "Libre", "atribucion": "Música: Autor"}}
    txt = textos.youtube(ficha, capitulos(g))
    lineas = txt.splitlines()
    i = lineas.index("Capítulos:")
    caps = []
    for linea in lineas[i + 1:]:
        m = re.match(r"^(\d+:\d\d(?::\d\d)?) (.+)$", linea)
        if not m:
            break
        caps.append((_segundos(m.group(1)), m.group(2)))
    assert caps[0][0] == 0 and lineas[i + 1].startswith("00:00 ")
    assert len(caps) >= 3
    fin = int(duracion_total(g))
    largos = [b[0] - a[0] for a, b in zip(caps, caps[1:])] + [fin - caps[-1][0]]
    assert min(largos) >= 10, caps
    assert all("<" not in t and ">" not in t for _, t in caps)
    assert "https://tienda.example/transportador" in txt and "Música: «Pista» de Autor" in txt
    assert "Música: Autor" in txt and "a, b" in txt


def test_youtube_txt_sin_capitulos_lo_dice():
    g = _guion_largo()
    g["etapas"] = g["etapas"][:1]
    g["etapas"][0]["duracion_s"] = 2.0
    for parte in ("cifras", "orbita", "cierre"):
        g[parte]["duracion_s"] = 1.0
    assert capitulos(g) == []
    txt = textos.youtube({"titulo": "T", "descripcion": "d", "url_tienda": "", "etiquetas": []}, [])
    assert "Sin capítulos" in txt and "(pon aquí el enlace de la tienda)" in txt


# ------------------------------------------------------------------ zips (D11)
def test_comprimir_nunca_mete_precios(tmp_path):
    carpeta = tmp_path / "completo"
    (carpeta / "planos").mkdir(parents=True)
    (carpeta / "planos" / "juego.pdf").write_bytes(b"%PDF")
    ruta = paquete.comprimir(carpeta, tmp_path / "m-1.0.0-completo.zip")
    with zipfile.ZipFile(ruta) as zf:
        assert zf.namelist() == ["m-1.0.0-completo/planos/juego.pdf"]
    (carpeta / "cotizacion.pdf").write_bytes(b"%PDF")
    with pytest.raises(paquete.PublicacionError, match="no se publica nunca"):
        paquete.comprimir(carpeta, tmp_path / "otro.zip")


def test_la_vista_3d_entra_a_los_dos_zips_y_la_nombra_la_ficha(tmp_path):
    """Plan vista-3d-tienda, F3: el GLB, su HTML y el póster van a la raíz de los dos niveles
    (el HTML pide los otros dos al lado), el LEEME dice qué es cada uno y `ficha.json` los
    nombra con su sha256."""
    staging = tmp_path / ".generando"
    (staging / "entregables").mkdir(parents=True)
    web = {n: staging / n for n in ("vista-3d.glb", "vista-3d.html", "miniatura.png", "video.mp4")}
    for n, ruta in web.items():
        ruta.write_bytes(n.encode() * 10)
    ficha = {"titulo": "Mesa", "slug": "mesa", "version": "1.0.0", "descripcion": "d",
             "nivel": "gratis", "precio_usd": 0, "url_tienda": "", "etiquetas": [],
             "licencias": {"gratis": "CC BY-NC 4.0", "completo": textos.LICENCIA_PERSONAL}}
    cal = paquete.calidad({"veredicto": "VERDE", "resumen": {"chequeos_ok": []}}, forzar=False)
    zips = paquete.armar(staging, staging / "entregables", [], [], ficha=ficha, cifras=[],
                         calidad_=cal, variables={}, apolo=b"PK",
                         extras=[(web["vista-3d.html"], textos.VISTA_3D_HTML),
                                 (web["vista-3d.glb"], textos.VISTA_3D_GLB),
                                 (web["miniatura.png"], textos.VISTA_3D_POSTER)])
    for nivel, ruta in zips.items():
        with zipfile.ZipFile(ruta) as zf:
            dentro = {n.split("/", 1)[1]: zf.read(n) for n in zf.namelist()}
        assert {"vista-3d.glb", "vista-3d.html", "miniatura.png"} <= set(dentro), nivel
        assert dentro["vista-3d.glb"] == web["vista-3d.glb"].read_bytes()
        assert f"| `vista-3d.glb` | {textos.VISTA_3D_GLB} |" in dentro["LEEME.md"].decode()
    publica = paquete.ficha_json(
        ficha, staging=staging, zips=zips, video=web["video.mp4"], miniatura=web["miniatura.png"],
        duracion_s=1.0, capitulos=[], musica=None, calidad_=cal, cifras=[],
        vista_3d={"glb": web["vista-3d.glb"], "html": web["vista-3d.html"], "triangulos": 12,
                  "etiquetas": [{"grupo": "Bastidor", "cifra": "4 piezas", "posicion_m": [0, 1, 0]}]})
    assert publica["vista_3d"] == {"modelo": "vista-3d.glb", "html": "vista-3d.html",
                                   "poster": "miniatura.png", "bytes": 120, "triangulos": 12,
                                   "etiquetas": [{"grupo": "Bastidor", "cifra": "4 piezas"}]}
    por_nombre = {a["nombre"]: a for a in publica["archivos"]}
    assert por_nombre["vista-3d.html"]["sha256"] == paquete.sha256(web["vista-3d.html"])
    assert por_nombre["vista-3d.glb"]["nivel"] == "gratis"
    sin = paquete.ficha_json(ficha, staging=staging, zips=zips, video=web["video.mp4"],
                             miniatura=web["miniatura.png"], duracion_s=1.0, capitulos=[],
                             musica=None, calidad_=cal, cifras=[])
    assert "vista_3d" not in sin and "vista-3d.glb" not in {a["nombre"] for a in sin["archivos"]}


def test_una_version_publicada_no_se_pisa(tmp_path):
    carpeta = paquete.carpeta_version(tmp_path, "mesa", "1.0.3")
    carpeta.mkdir(parents=True)
    paquete.exigir_no_publicada(carpeta)
    (carpeta / paquete.FICHA_JSON).write_text("{}", encoding="utf-8")
    with pytest.raises(paquete.PublicacionError, match="--version 1.0.4"):
        paquete.exigir_no_publicada(carpeta)


# ------------------------------------------------------------------ línea de tiempo
def test_la_linea_de_tiempo_cuadra_con_la_duracion_del_guion():
    g = _guion_largo()
    plan = lt.tramos(g)
    assert [t.parte for t in plan] == ["portada"] + ["etapa"] * 4 + ["cifras", "orbita", "cierre"]
    assert lt.total_fotogramas(plan) == round(duracion_total(g) * 30)
    assert all(a.fin == b.inicio for a, b in zip(plan, plan[1:]))
    g["cifras"]["duracion_s"] = 0.0
    assert "cifras" not in [t.parte for t in lt.tramos(g)]


def test_reparto_y_revelado_escalonado():
    tramos = lt.reparto(100, 160, [1.0, 2.0, 3.0])
    assert tramos == [(100, 110), (110, 130), (130, 160)]
    assert lt.apariciones(0, 30, 3) == [0, 10, 20]
    assert lt.apariciones(0, 2, 4) == [0, 0, 1, 1]  # un paso corto revela de a varias


def test_efectos_de_la_linea_de_tiempo():
    assert lt.opacidad_rotulo(0, 0, 300, 30) < 0.1 and lt.opacidad_rotulo(150, 0, 300, 30) == 1.0
    assert lt.opacidad_rotulo(299, 0, 300, 30) < 0.1
    assert lt.luz(0, 900, 30) < 0.1 and lt.luz(450, 900, 30) == 1.0 and lt.luz(899, 900, 30) < 0.1
    assert lt.entrada(5, 5, 30) is not None and lt.entrada(100, 5, 30) is None
    assert lt.resalte(10, 10, 30) == 1.0 and lt.resalte(10 + 36, 10, 30) == 0.0
    assert lt.azimut_orbita(0, 0, 100, 10.0) == 10.0
    assert lt.azimut_orbita(50, 0, 100, 10.0) == pytest.approx(190.0)
