"""Testigos de la puerta de publicación: máquinas de referencia con su veredicto CONGELADO por
ítem (plan puerta-de-publicacion, D9 y D16). Un cambio de Apolo que mueve un veredicto se ve.

    python -B scripts/testigos.py --en-proceso              # los públicos, sin API (la app en proceso)
    python -B scripts/testigos.py --puerto 8123             # públicos y privados contra una API
    python -B scripts/testigos.py --puerto 8123 --congelar  # reescribe los veredictos (revisa el diff)
    python -B scripts/testigos.py --generar                 # rehace los .apolo públicos de su receta
    python -B scripts/testigos.py --exportar-tienda <apolo.db> [--ids 3,4]

- **Públicos** (`tests/data/testigos/`): modelos de las plantillas y piezas SINTÉTICAS. El repo es
  MIT y las máquinas de la tienda se venden: sus `.apolo` no entran aquí (D16).
  `tests/test_testigos.py` los corre en cada suite con la API en proceso (gravedad y marcha
  incluidas); los marcados `tortura` sólo con `-m torture`.
- **Privados** (`<apolo-fabrica>/testigos/`, repo privado; `--privados` o `APOLO_FABRICA`): las
  máquinas de la tienda, a mano contra una API. `--exportar-tienda` los saca de una base de uso
  abierta en SÓLO LECTURA (los ids que se pidan y el transportador de rodillos con cadena, por su
  nombre).

Cada testigo es `<nombre>.apolo` + `<nombre>.json` {testigo, descripcion, tortura, aprobado,
version_registro, firma, items: {id: estado}}. Sale con 1 si algún veredicto se movió (nombra el
ítem, de qué a qué y el detalle de ahora). Congelar es SIEMPRE a propósito (`--congelar`), nunca
automático, como el golden MCP.

Contra una API: SIEMPRE una levantada sobre una COPIA de la base (abrir cada `.apolo` con
`POST /api/project/open` crea un proyecto nuevo en ella); rehúsa el :8000 sin `--forzar`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
# Mide ESTE árbol: en un worktree el venv apunta al checkout principal (CLAUDE.md raíz).
if str(RAIZ / "core") not in sys.path:
    sys.path.insert(0, str(RAIZ / "core"))

DIR_PUBLICOS = RAIZ / "tests" / "data" / "testigos"
IDS_TIENDA = (3, 4)
_RODILLOS_CADENA = re.compile(r"rodillo.*cadena", re.I)

#: Lo que el cliente pide a la puerta (D15: carga, paquete y velocidad del encargo).
REQUISITOS = {"carga_kg": 15, "largo_paquete_mm": 400, "ancho_paquete_mm": 300,
              "velocidad_m_s": 0.3}


def _f(funcion: str, solucion: str, descartada: str, motivo: str) -> dict:
    return {"funcion": funcion, "solucion": solucion, "piezas": [],
            "descartadas": [{"solucion": descartada, "motivo": motivo}]}


#: D15 de la faja: cada familia de función con su solución y la alternativa que se descartó.
FUNCIONES_FAJA = [
    _f("transmision_flexible", "banda de PVC de 2 capas sobre cama de chapa",
       "banda sobre rodillos portantes", "con 15 kg la cama es más simple, barata y silenciosa"),
    _f("apoyo_rotativo", "chumaceras de brida UCF205 y tensores de carro UCT205-150 de catálogo",
       "soporte en C con eje fijo", "el tensor de carro es estándar de mercado y da 150 mm de "
       "carrera"),
    _f("accionamiento", "motorreductor en línea coaxial al eje motriz con acople flexible",
       "transmisión por cadena", "una cadena más que tensar, lubricar y resguardar"),
    _f("resguardo", "guardas de chapa atornilladas", "guardas soldadas",
       "impiden el mantenimiento de lo que cubren"),
    _f("estructura", "bastidor de tubo 4×2 con patas soldadas y pies niveladores",
       "perfil de aluminio", "más caro y con más flecha para el mismo canto"),
]


# ------------------------------------------------------------------ recetas de los públicos
#: D6 de puerta-sin-sobrediseno: lo que la plantilla trae y la puerta no pide, con su porqué (la
#: medición está en la bitácora del plan, § F3; corregir la plantilla o el modelo de peligros es
#: otra fase). La «Guarda del acople» ya no: desde la F3b el acople es peligro y ella lo resguarda.
JUSTIFICADAS_FAJA = [
    {"pieza": "c1_guarda_inf2_1", "porque": "cierra por abajo la ranura banda ↔ larguero del lado "
     "+Y, como su par del −Y: la plantilla cierra los dos lados por simetría"},
    {"pieza": "c1_guarda_inf2_2", "porque": "cierra por abajo la ranura banda ↔ larguero del lado "
     "+Y, como su par del −Y: la plantilla cierra los dos lados por simetría"},
]


def _faja():
    from apolo.doc import Document
    from apolo.services.puerta_publicacion import poner_justificadas

    d = Document("faja-de-banda")
    d.execute("create_belt_conveyor", {})  # v5: nace con sus cierres (sello de entrada)
    d.set_requirements(dict(REQUISITOS))
    d.funciones = [dict(f) for f in FUNCIONES_FAJA]
    poner_justificadas(d, [dict(j) for j in JUSTIFICADAS_FAJA])
    return d


def _rodillos():
    from apolo.doc import Document

    d = Document("transportador-de-rodillos")
    d.execute("create_roller_conveyor", {"largo": 1500})
    d.set_requirements(dict(REQUISITOS))
    return d


def _mensula():
    from apolo.doc import Document

    d = Document("mensula")
    m = d.execute("create_box", {"name": "Ménsula", "width": 120, "depth": 80, "height": 10,
                                 "position": {"x": 0, "y": 0, "z": 5}})
    d.execute("ground", {"name": "g0", "feature": m})
    return d


def _mensula_atornillada():
    from apolo.doc import Document

    d = Document("mensula-atornillada")
    base = d.execute("create_box", {"name": "Placa base", "width": 300, "depth": 200,
                                    "height": 12, "position": {"x": 0, "y": 0, "z": 6}})
    m = d.execute("create_box", {"name": "Ménsula", "width": 120, "depth": 80, "height": 10,
                                 "position": {"x": 0, "y": 0, "z": 17}})
    d.execute("ground", {"name": "g0", "feature": base})
    d.execute("join_bolted", {"a": m, "b": base, "size": "M10", "count": 2})
    return d


#: nombre → (receta, descripción, tortura)
RECETAS = {
    "faja": (_faja, "create_belt_conveyor v5 por defecto (con sus cierres: guardas inferiores bajo "
                    "la ranura banda-larguero, placas de cierre de los largueros y techo de cola "
                    "hasta la cama, F6) con requisitos y funciones D15: aprueba entera", False),
    "rodillos": (_rodillos, "create_roller_conveyor de 1500 mm con requisitos (sin D15): su "
                            "veredicto de hoy, con lo que falta", True),
    "mensula": (_mensula, "una ménsula suelta anclada: pieza estática que se aprueba", False),
    "mensula_atornillada": (_mensula_atornillada, "ménsula unida a una placa base anclada "
                                                  "con join_bolted M10: se aprueba", False),
}


def generar(carpeta: Path = DIR_PUBLICOS) -> list[Path]:
    """Reescribe los `.apolo` públicos desde sus recetas (después hay que `--congelar`)."""
    carpeta.mkdir(parents=True, exist_ok=True)
    out = []
    for nombre, (receta, _desc, _t) in RECETAS.items():
        ruta = carpeta / f"{nombre}.apolo"
        ruta.write_bytes(receta().to_apolo_bytes())
        out.append(ruta)
    return out


# ------------------------------------------------------------------ correr la puerta
def correr_en_proceso(doc) -> dict:
    """La puerta del endpoint (`POST /api/puerta-publicacion`) sobre `doc` con la app EN
    PROCESO: gravedad y marcha reales, sin base ni lifespan."""
    from fastapi.testclient import TestClient

    import apolo.api.main as api

    previo = api.DOC
    api.DOC = doc
    try:
        r = TestClient(api.app).post("/api/puerta-publicacion")
    finally:
        api.DOC = previo
    if r.status_code != 200:
        raise RuntimeError(f"la puerta respondió {r.status_code}: {r.text[:300]}")
    return r.json()


def correr_api(url: str, apolo: bytes, nombre: str, espera_s: float = 900.0) -> dict:
    """Abre el `.apolo` en la API (crea un proyecto en SU base) y corre la puerta como job."""
    import httpx

    with httpx.Client(base_url=url, timeout=120.0) as c:
        r = c.post("/api/project/open",
                   files={"file": (f"{nombre}.apolo", apolo, "application/zip")})
        r.raise_for_status()
        r = c.post("/api/puerta-publicacion", params={"async": "true"})
        r.raise_for_status()
        job, fin = r.json()["job_id"], time.monotonic() + espera_s
        while time.monotonic() < fin:
            j = c.get(f"/api/jobs/{job}", params={"wait_s": 30}).json()
            if j.get("estado") == "ok":
                return j["resultado"]
            if j.get("estado") == "error":
                raise RuntimeError(f"la puerta falló en la API: {j.get('error')}")
    raise RuntimeError(f"la puerta no terminó en {espera_s:.0f} s")


# ------------------------------------------------------------------ veredictos
def veredicto(resultado: dict) -> dict:
    """Lo que se congela de un resultado de la puerta: por ítem, su estado."""
    return {"aprobado": resultado["aprobado"], "version_registro": resultado["version_registro"],
            "firma": resultado.get("firma"),
            "items": {i["id"]: i["estado"] for i in resultado["items"]}}


def diferencias(congelado: dict, resultado: dict) -> list[str]:
    """Lo que se movió desde que se congeló ([] = igual), nombrando cada ítem."""
    actual = veredicto(resultado)
    detalle = {i["id"]: i.get("detalle", "") for i in resultado["items"]}
    out = []
    if congelado.get("firma") and congelado["firma"] != actual["firma"]:
        out.append(f"firma del modelo {congelado['firma']} → {actual['firma']}: el .apolo (o "
                   "lo que la firma lee) cambió desde que se congeló")
    if congelado.get("version_registro") != actual["version_registro"]:
        out.append(f"version_registro {congelado.get('version_registro')} → "
                   f"{actual['version_registro']}")
    antes, ahora = congelado.get("items") or {}, actual["items"]
    for iid in [*antes, *(k for k in ahora if k not in antes)]:
        if antes.get(iid) != ahora.get(iid):
            out.append(f"{iid}: {antes.get(iid, '(no estaba)')} → {ahora.get(iid, '(ya no está)')}"
                       + (f" — {detalle[iid][:200]}" if detalle.get(iid) else ""))
    if congelado.get("aprobado") != actual["aprobado"]:
        out.append(f"aprobado {congelado.get('aprobado')} → {actual['aprobado']}")
    return out


def leer(carpeta: Path) -> list[dict]:
    """Los testigos de una carpeta: [{nombre, apolo, json, congelado}] (sin JSON: None)."""
    out = []
    for ruta in sorted(carpeta.glob("*.apolo")):
        js = ruta.with_suffix(".json")
        out.append({"nombre": ruta.stem, "apolo": ruta, "json": js,
                    "congelado": json.loads(js.read_text(encoding="utf-8")) if js.is_file()
                    else None})
    return out


def congelar(t: dict, resultado: dict) -> None:
    previo = t["congelado"] or {}
    receta = RECETAS.get(t["nombre"]) if t["apolo"].parent == DIR_PUBLICOS else None
    datos = {"testigo": t["nombre"],
             "descripcion": receta[1] if receta else previo.get("descripcion", t["nombre"]),
             "tortura": receta[2] if receta else bool(previo.get("tortura")),
             **veredicto(resultado)}
    with open(t["json"], "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(datos, ensure_ascii=False, indent=1) + "\n")
    t["congelado"] = datos


# ------------------------------------------------------------------ exportar la tienda
def exportar_tienda(db: Path, destino: Path, ids=IDS_TIENDA) -> list[Path]:
    """Los `.apolo` de las máquinas de la tienda desde una base de uso en SÓLO LECTURA: los
    `ids` pedidos y el primer transportador de rodillos con cadena (por su nombre)."""
    con = sqlite3.connect(f"{db.resolve().as_uri()}?mode=ro", uri=True)
    try:
        filas = con.execute("SELECT id, name, data FROM projects ORDER BY id").fetchall()
    finally:
        con.close()
    elegidas = [f for f in filas if f[0] in set(ids)]
    rodillos = next((f for f in filas if _RODILLOS_CADENA.search(f[1] or "")), None)
    if rodillos is not None and rodillos not in elegidas:
        elegidas.append(rodillos)
    destino.mkdir(parents=True, exist_ok=True)
    out = []
    for pid, nombre, data in elegidas:
        slug = re.sub(r"[^a-z0-9]+", "-", (nombre or f"proyecto-{pid}").lower()).strip("-")
        ruta = destino / f"{slug}.apolo"
        ruta.write_bytes(bytes(data))
        out.append(ruta)
    return out


def dir_privados(arg: str | None) -> Path:
    if arg:
        return Path(arg)
    fabrica = os.environ.get("APOLO_FABRICA")
    return (Path(fabrica) if fabrica else RAIZ.parent / "apolo-fabrica") / "testigos"


# ------------------------------------------------------------------ CLI
def _correr(t: dict, url: str | None) -> dict:
    data = t["apolo"].read_bytes()
    if url:
        return correr_api(url, data, t["nombre"])
    from apolo.doc import Document

    return correr_en_proceso(Document.from_apolo_bytes(data))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    modo = ap.add_mutually_exclusive_group()
    modo.add_argument("--puerto", type=int, help="API sobre una COPIA de la base")
    modo.add_argument("--en-proceso", action="store_true", help="la app en este proceso")
    ap.add_argument("--congelar", action="store_true", help="reescribe los veredictos")
    ap.add_argument("--generar", action="store_true", help="rehace los .apolo públicos")
    ap.add_argument("--exportar-tienda", metavar="APOLO_DB",
                    help="exporta las máquinas de la tienda (base abierta en sólo lectura)")
    ap.add_argument("--ids", default=",".join(map(str, IDS_TIENDA)))
    ap.add_argument("--privados", help="carpeta de los testigos privados")
    ap.add_argument("--solo", help="nombre de un testigo")
    ap.add_argument("--forzar", action="store_true", help="permite el puerto 8000")
    a = ap.parse_args(argv)
    privados = dir_privados(a.privados)
    if a.exportar_tienda:
        ids = [int(x) for x in a.ids.split(",") if x.strip()]
        for ruta in exportar_tienda(Path(a.exportar_tienda), privados, ids):
            print(f"exportado {ruta}")
        if not (a.puerto or a.en_proceso):
            return 0
    if a.generar:
        for ruta in generar():
            print(f"generado {ruta.relative_to(RAIZ).as_posix()} (congélalo)")
        if not (a.puerto or a.en_proceso):
            return 0
    if a.puerto == 8000 and not a.forzar:
        print("El :8000 es la API de trabajo y abrir cada testigo crea un proyecto en su base: "
              "levanta una API sobre una COPIA de la base en otro puerto, o pasa --forzar.")
        return 2
    if not (a.puerto or a.en_proceso):
        ap.print_help()
        return 2
    url = f"http://127.0.0.1:{a.puerto}" if a.puerto else None
    testigos = leer(DIR_PUBLICOS) + (leer(privados) if privados.is_dir() else [])
    if a.solo:
        testigos = [t for t in testigos if t["nombre"] == a.solo]
    movidos = 0
    for t in testigos:
        t0 = time.perf_counter()
        resultado = _correr(t, url)
        dt = time.perf_counter() - t0
        if a.congelar:
            congelar(t, resultado)
            print(f"{t['nombre']}: congelado ({'APROBADO' if resultado['aprobado'] else 'NO aprobado'},"
                  f" {len(resultado['items'])} ítems, {dt:.1f} s)")
            continue
        difs = (diferencias(t["congelado"], resultado) if t["congelado"]
                else ["sin veredicto congelado: --congelar"])
        movidos += bool(difs)
        print(f"{t['nombre']}: {'IGUAL' if not difs else 'SE MOVIÓ'} ({dt:.1f} s)")
        for d in difs:
            print(f"  - {d}")
    return 1 if movidos else 0


if __name__ == "__main__":
    sys.exit(main())
