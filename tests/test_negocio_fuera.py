"""El árbol público sólo lleva el núcleo: las palabras del negocio no entran (y sólo bajan).

Mario, 2026-10-23: el repo público es el núcleo y nada más; el trabajo del negocio (venta,
videos publicados, pedidos, repos privados) vive fuera. Plan
`docs/plans/nucleo-abierto-extensiones-privadas.md`, D13–D16.

**Trinquete** (el patrón de `tests/test_tamano_archivos.py`). Se recorren los archivos
VERSIONADOS (`git ls-files`) y se cuenta, por archivo, cuántas LÍNEAS nombran el negocio.
  - **Zona cero** (`docs/`, todo `CLAUDE.md`, `README*`, `CONTRIBUTING*`, `SECURITY*`,
    `.github/`): cero, sin excepciones.
  - **El resto** (código, tests, scripts, YAML, UI): cada archivo que hoy nombra el negocio
    está en `TOPES` con lo medido. Falla si un archivo sube, si aparece uno nuevo, si un tope
    quedó más alto que lo real (se baja en el mismo commit que limpia; en cero, se borra la
    entrada) o si un archivo declarado ya no existe. La F4d del plan lo lleva a cero.

**Palabras**: las genéricas van literales (`PALABRAS`, por subcadena, como el `git grep -i`
del plan). Los nombres propios del negocio (el dominio, un repo privado, otro proyecto del
titular) NO se escriben aquí: se comparan por sha256 de cada palabra en minúsculas
(`NOMBRES_SHA256`), tokenizando la línea (ver `palabras_de`).

Stdlib pura a propósito: NO importa `apolo` (en un worktree resolvería al checkout principal).
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

import pytest

# ── Configuración del proyecto ────────────────────────────────────────────────

RAIZ_REPO = Path(__file__).resolve().parents[1]

#: Este archivo no se cuenta (nombra las palabras para buscarlas).
ESTE = Path(__file__).resolve().relative_to(RAIZ_REPO).as_posix()

#: Palabras genéricas del negocio: subcadena, sin distinguir mayúsculas.
PALABRAS = re.compile(r"youtube|tienda|shorts|reels|marketplace|ped-1[0-9][0-9]", re.I)

#: sha256 (hex) de los nombres propios del negocio, en minúsculas y con `-` entre partes.
NOMBRES_SHA256: frozenset[str] = frozenset({
    "19929567792561477a83cd7e599165d2bb18bffffcc41b445edf8d9125f7f926",  # el dominio
    "6be94b76dddeb052c3f3957323259ffdf935070bf0fa9f70429b15558bac52ec",  # otro proyecto
    "7d18db5a63632847af9c32a27908081434fd9c0cfcd86618d85a57525debdf7b",  # repo de producción
})

#: Cuántas líneas nombran hoy el negocio en cada archivo fuera de la zona cero (ruta
#: relativa a la raíz, con `/`). Sólo bajan; en cero, se borra la entrada.
TOPES: dict[str, int] = {
    "core/apolo/api/routers/video.py": 2,
    "core/apolo/api/routers/video_guion.py": 1,
    "core/apolo/doc/prefijos.py": 1,
    "core/apolo/drawing/assembly_manual.py": 1,
    "core/apolo/entregables.py": 2,
    "core/apolo/kernel/glb.py": 1,
    "core/apolo/kernel/glb_zonas.py": 1,
    "core/apolo/kernel/render_comun.py": 1,
    "core/apolo/kernel/render_vivo.py": 1,
    "core/apolo/library/data/110_garruchas.yaml": 4,
    "core/apolo/media/__init__.py": 2,
    "core/apolo/media/cierre.py": 15,
    "core/apolo/media/codificar.py": 2,
    "core/apolo/media/composicion.py": 6,
    "core/apolo/media/grabacion.py": 1,
    "core/apolo/media/tarjetas.py": 2,
    "core/apolo/services/apariencia.py": 2,
    "core/apolo/services/cifras_grupo.py": 1,
    "core/apolo/services/construccion.py": 3,
    "core/apolo/services/datos_rotulos.py": 1,
    "core/apolo/services/guion_video.py": 11,
    "core/apolo/services/linea_tiempo.py": 2,
    "core/apolo/services/montaje.py": 1,
    "core/apolo/services/montaje_video.py": 2,
    "core/apolo/services/rotulos.py": 1,
    "core/apolo/tools/calidad.py": 1,
    "core/pyproject.toml": 1,
    "scripts/benchmark_package.py": 3,
    "scripts/testigos.py": 15,
    "tests/conftest.py": 3,
    "tests/data/mcp_golden/list_tools.json": 1,
    "tests/test_benchmark_entregables.py": 5,
    "tests/test_capas_media.py": 2,
    "tests/test_construccion.py": 3,
    "tests/test_f6_materiales_bom.py": 1,
    "tests/test_f6_revisores_fajas.py": 1,
    "tests/test_f6_tornilleria_bom.py": 1,
    "tests/test_kernel_glb.py": 1,
    "tests/test_media_cierre.py": 12,
    "tests/test_media_codificar.py": 1,
    "tests/test_media_composicion.py": 3,
    "tests/test_pistas.py": 2,
    "tests/test_prefijos.py": 1,
    "tests/test_puerta_tensor.py": 1,
    "tests/test_render_vivo.py": 1,
    "tests/test_rodillos_a_mano.py": 1,
    "tests/test_rodillos_a_mano_capacidad.py": 3,
    "tests/test_rodillos_a_mano_eje.py": 1,
    "tests/test_seta_render.py": 2,
    "tests/test_testigos.py": 3,
    "tests/test_video_navegador.py": 1,
    "tests/test_video_pulido.py": 2,
    "ui/src/tuteoNeutro.test.ts": 1,
    "ui/src/viewport/grabacion/grabador.ts": 1,
    "ui/src/viewport/grabacion/guion.ts": 1,
}

# ── Medición ──────────────────────────────────────────────────────────────────

_TOKEN = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+)*")


def sha(palabra: str) -> str:
    return hashlib.sha256(palabra.lower().encode("utf-8")).hexdigest()


def palabras_de(linea: str) -> set[str]:
    """Cada token de la línea (`[a-z0-9]` unidos por `-` o `_`) y cada tramo seguido de sus
    partes, unido con `-`: `apolo_x_y` da `apolo`, `x`, `y`, `apolo-x`, `x-y`, `apolo-x-y`."""
    out: set[str] = set()
    for token in _TOKEN.findall(linea.lower()):
        partes = re.split(r"[-_]", token)
        for i in range(len(partes)):
            for j in range(i + 1, len(partes) + 1):
                out.add("-".join(partes[i:j]))
    return out


def nombra_el_negocio(linea: str, nombres: frozenset[str] = NOMBRES_SHA256) -> bool:
    if PALABRAS.search(linea):
        return True
    return any(sha(p) in nombres for p in palabras_de(linea))


def contar(texto: str, nombres: frozenset[str] = NOMBRES_SHA256) -> int:
    """Líneas del texto que nombran el negocio."""
    return sum(1 for linea in texto.splitlines() if nombra_el_negocio(linea, nombres))


def en_zona_cero(rel: str) -> bool:
    nombre = rel.rsplit("/", 1)[-1]
    return (rel.startswith(("docs/", ".github/")) or nombre == "CLAUDE.md"
            or nombre.upper().startswith(("README", "CONTRIBUTING", "SECURITY")))


def versionados() -> list[str]:
    try:
        salida = subprocess.run(["git", "ls-files", "-z"], cwd=RAIZ_REPO, check=True,
                                capture_output=True).stdout
    except (OSError, subprocess.CalledProcessError):  # pragma: no cover - sin git
        pytest.skip("sin git: el trinquete recorre los archivos versionados")
    return sorted(r for r in salida.decode("utf-8").split("\0") if r)


def medir() -> dict[str, int]:
    """{ruta: líneas que nombran el negocio} de los archivos versionados de texto (> 0)."""
    out: dict[str, int] = {}
    for rel in versionados():
        if rel == ESTE:
            continue
        ruta = RAIZ_REPO / rel
        if not ruta.is_file():
            continue
        try:
            texto = ruta.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            continue  # binario
        n = contar(texto)
        if n:
            out[rel] = n
    return out


def revisar(medido: dict[str, int], topes: dict[str, int]) -> list[str]:
    """Los errores del trinquete (vacío = verde). Puro: lo prueban los casos de abajo."""
    errores: list[str] = []
    for rel, n in sorted(medido.items()):
        if en_zona_cero(rel):
            errores.append(f"{rel}: {n} línea(s) con el negocio en la zona cero (va a cero)")
            continue
        tope = topes.get(rel)
        if tope is None:
            errores.append(f'archivo nuevo con el negocio: "{rel}": {n} (sácalo; no se declara)')
        elif n > tope:
            errores.append(f"{rel}: subió de {tope} a {n} líneas con el negocio")
    for rel, tope in sorted(topes.items()):
        n = medido.get(rel, 0)
        if not (RAIZ_REPO / rel).is_file() and rel not in medido:
            errores.append(f"{rel} ya no existe: borra la entrada")
        elif n == 0:
            errores.append(f"{rel}: ya no nombra el negocio: borra la entrada")
        elif n < tope:
            errores.append(f"{rel}: bajó de {tope} a {n}: actualiza el tope")
    return errores


# ── Gate ──────────────────────────────────────────────────────────────────────


def test_el_arbol_publico_no_suma_negocio():
    errores = revisar(medir(), TOPES)
    assert not errores, "\n".join(errores)


# ── El trinquete mismo ────────────────────────────────────────────────────────


def test_verde_cuando_lo_medido_es_lo_declarado():
    assert revisar({"tests/test_paths.py": 2}, {"tests/test_paths.py": 2}) == []


def test_rojo_si_sube_si_aparece_o_si_el_tope_quedo_alto():
    topes = {"tests/test_paths.py": 2}
    assert any("subió" in e for e in revisar({"tests/test_paths.py": 3}, topes))
    assert any("bajó" in e for e in revisar({"tests/test_paths.py": 1}, topes))
    assert any("borra la entrada" in e for e in revisar({}, topes))
    assert any("archivo nuevo" in e for e in revisar({"core/apolo/paths.py": 1}, {}))


def test_rojo_en_la_zona_cero_aunque_se_declare():
    for rel in ("docs/plans/x.md", "core/apolo/kernel/CLAUDE.md", "README.es.md",
                ".github/workflows/ci.yml", "CONTRIBUTING.md", "SECURITY.md"):
        assert en_zona_cero(rel), rel
        assert revisar({rel: 1}, {rel: 1}), rel
    assert not en_zona_cero("core/apolo/media/cierre.py")


def test_palabras_genericas_y_nombres_por_hash():
    assert nombra_el_negocio("el video de YouTube")
    assert nombra_el_negocio("APOLO_TIENDA_URL")
    assert nombra_el_negocio("pedido PED-127")
    assert not nombra_el_negocio("la puerta de publicación del núcleo")
    # un nombre propio sólo se detecta por su hash, también dentro de un identificador
    secreto = frozenset({sha("palabra-secreta")})
    assert nombra_el_negocio("ver palabra-secreta/briefs", secreto)
    assert nombra_el_negocio("APOLO_PALABRA_SECRETA=1", secreto)
    assert nombra_el_negocio("https://palabra-secreta.com", frozenset({sha("palabra")}))
    assert not nombra_el_negocio("una palabra suelta y otra secreta", secreto)
    assert contar("a\nYouTube\nb\ntienda y tienda\n") == 2


def test_los_hashes_son_sha256_en_minusculas():
    assert all(re.fullmatch(r"[0-9a-f]{64}", h) for h in NOMBRES_SHA256)
    assert len(NOMBRES_SHA256) == 3
