"""La memoria de cálculo NO es exclusiva del vertical transportadores (hallazgo del
SEGUNDO testigo, 2026-07-24): sin `carga_kg`/`largo_paquete_mm` se emiten las
verificaciones UNIVERSALES y se DECLARA lo omitido, en vez de un 400 que dejaba sin
memoria a cualquier proyecto que no fuera una faja."""
import io

from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc import Document


def _mueble():
    """Proyecto SIN requisitos de transportador: dos piezas atornilladas y con apoyo."""
    doc = Document("mueble")
    base = doc.execute("create_box", {"name": "Base madera", "width": 800, "depth": 400,
                                      "height": 20, "position": {"z": 10}})
    tapa = doc.execute("create_box", {"name": "Tapa madera", "width": 800, "depth": 400,
                                      "height": 20, "position": {"z": 500}})
    doc.execute("ground", {"name": "g1", "feature": base})
    doc.execute("fasten", {"name": "u1", "a": base, "b": tapa, "kind": "perno",
                           "size": "M8", "qty": 4})
    return doc


def _texto(pdf_bytes: bytes) -> str:
    from pypdf import PdfReader

    return " ".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(pdf_bytes)).pages)


def test_memoria_se_emite_sin_requisitos_de_transportador():
    api.DOC = _mueble()
    r = TestClient(api.app).get("/api/calc-report.pdf")
    assert r.status_code == 200, r.text[:200]
    assert r.content[:4] == b"%PDF" and len(r.content) > 5000


def test_alcance_omitido_va_DECLARADO_y_desaparece_con_requisitos():
    """Una memoria que calla lo que no verificó miente por ausencia."""
    doc = _mueble()
    api.DOC = doc
    client = TestClient(api.app)
    txt = _texto(client.get("/api/calc-report.pdf").content)
    assert "ALCANCE DE LA MEMORIA" in txt.upper()      # se declara lo omitido
    # con los requisitos del vertical declarados, el aviso NO aparece
    doc.requirements = {"carga_kg": 50.0, "largo_paquete_mm": 300.0}
    txt2 = _texto(client.get("/api/calc-report.pdf").content)
    assert "ALCANCE DE LA MEMORIA" not in txt2.upper()


def test_pieza_suelta_tambien_obtiene_memoria_con_avisos():
    """Sin uniones declaradas la memoria SIGUE emitiéndose (con sus avisos): es más útil
    para el ingeniero que un 400 — el 400 queda solo para el caso sin ninguna regla."""
    doc = Document("suelto")
    doc.execute("create_box", {"name": "Caja", "width": 100, "depth": 100, "height": 100})
    api.DOC = doc
    r = TestClient(api.app).get("/api/calc-report.pdf")
    assert r.status_code == 200 and r.content[:4] == b"%PDF"


def test_veredicto_no_concluyente_sin_verificaciones_ok():
    """«Aprobado» EXIGE que algo se haya verificado: 0 OK → NO CONCLUYENTE, nunca
    «APROBADO CON AVISOS» (hallazgo del segundo testigo: aprobar el vacío)."""
    from apolo.drawing.calc_report import _verdict

    assert _verdict([{"estado": "aviso"}, {"estado": "aviso"}]) == "NO CONCLUYENTE"
    assert _verdict([]) == "NO CONCLUYENTE"
    assert _verdict([{"estado": "ok"}, {"estado": "aviso"}]) == "APROBADO CON AVISOS"
    assert _verdict([{"estado": "ok"}]) == "APROBADO"
    assert _verdict([{"estado": "ok"}, {"estado": "error"}]) == "NO CONFORME"


def test_memoria_del_segundo_testigo_no_aprueba_el_vacio():
    """El proyecto sin uniones declaradas NO puede salir aprobado."""
    doc = Document("suelto")
    doc.execute("create_box", {"name": "Caja", "width": 100, "depth": 100, "height": 100})
    api.DOC = doc
    txt = _texto(TestClient(api.app).get("/api/calc-report.pdf").content).upper()
    assert "NO CONCLUYENTE" in txt and "VEREDICTO: APROBADO" not in txt
