"""Un archivo de código fuente de `core/apolo` tiene como máximo 500 líneas.

Un módulo de miles de líneas mezcla responsabilidades: nadie lo lee entero, cada cambio
choca con el de otra sesión y partirlo después cuesta más que no dejarlo crecer
(CLAUDE.md § Escala — mandato de arquitectura). La auditoría de arquitectura del
2026-10-03 encontró 15 de 178 archivos por encima del tope (`api/main.py` con 4916).

**Trinquete** (el mismo patrón que `ui/src/textoDeAyuda.test.ts`). `EXCEPCIONES`
declara, archivo por archivo, CUÁNTAS líneas tiene hoy cada uno de los que ya pasan el
tope. El gate falla si:
  - un archivo NUEVO (o no declarado) pasa de 500 líneas;
  - un archivo declarado CRECE por encima de su número (no se sube el número: se saca
    código a otro módulo);
  - un archivo declarado BAJA y el número no se actualizó (la lista sólo se achica, en
    el mismo commit que lo achica; en ≤ 500, se borra la entrada);
  - un archivo declarado ya no existe.
Partir un archivo grande se hace con un plan (`docs/plans/`), no de pasada.

**Línea** = una línea del archivo como texto: CRLF y LF cuentan igual y el salto final
no suma una línea vacía. Es `len(texto.splitlines())` restringido a `\\r\\n` y `\\n`,
igual que `ui/src/tamanoArchivos.test.ts` (un `\\f` o un `\\u2028` dentro de un string
no parte la línea).

**Adoptarlo en un proyecto con archivos existentes**: correrlo una vez; el error lista
las entradas `"ruta": N,` de cada archivo no declarado que pasa el tope. Pegarlas en
`EXCEPCIONES` y desde ahí el número sólo baja.

Stdlib pura a propósito: NO importa `apolo` (en un worktree resolvería al checkout
principal y mediría otro árbol).
"""

from __future__ import annotations

import os
from pathlib import Path

# ── Configuración del proyecto ────────────────────────────────────────────────

RAIZ_REPO = Path(__file__).resolve().parents[1]

#: Carpeta que se recorre, relativa a la raíz del repo.
CARPETA = "core/apolo"

#: Nunca se recorren (el bundle de la UI empaquetado y los artefactos de build).
CARPETAS_IGNORADAS = {"__pycache__", "webui"}

TOPE = 500

#: Cuántas líneas tiene hoy cada archivo que ya pasa el tope (ruta relativa a la raíz
#: del repo, con `/`). Al achicar un archivo se baja su número; en ≤ 500, se borra.
EXCEPCIONES: dict[str, int] = {
    "core/apolo/agent/agent.py": 597,
    "core/apolo/api/main.py": 3535,
    "core/apolo/commands/models.py": 1509,
    "core/apolo/commands/registry.py": 2212,
    "core/apolo/doc/document.py": 1060,
    "core/apolo/drawing/sheet.py": 893,
    "core/apolo/kernel/render_vtk.py": 537,
    "core/apolo/library/builders.py": 847,
    "core/apolo/library/engineering/report.py": 558,
    "core/apolo/library/rules.py": 940,
    "core/apolo/mcp_server.py": 1429,
}

# ── Medición ──────────────────────────────────────────────────────────────────


def contar_lineas(texto: str) -> int:
    """Líneas de un texto: CRLF = LF y un único salto final no abre una línea vacía."""
    partes = texto.replace("\r\n", "\n").split("\n")
    if partes[-1] == "":
        partes.pop()
    return len(partes)


def _ignorada(nombre: str) -> bool:
    return nombre in CARPETAS_IGNORADAS or nombre.endswith(".egg-info") or nombre.startswith(".")


def fuentes() -> list[str]:
    """Los `.py` de CARPETA, como rutas relativas a la raíz del repo con `/`."""
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(RAIZ_REPO / CARPETA):
        dirnames[:] = [d for d in dirnames if not _ignorada(d)]
        for nombre in filenames:
            if nombre.endswith(".py"):
                out.append((Path(dirpath) / nombre).relative_to(RAIZ_REPO).as_posix())
    return sorted(out)


def lineas_de(rel: str) -> int:
    return contar_lineas((RAIZ_REPO / rel).read_bytes().decode("utf-8"))


# ── Gate ──────────────────────────────────────────────────────────────────────


def test_ningun_archivo_pasa_el_tope_mas_de_lo_declarado():
    nuevos: list[str] = []
    crecieron: list[str] = []
    for rel in fuentes():
        n = lineas_de(rel)
        declarado = EXCEPCIONES.get(rel)
        if declarado is None and n > TOPE:
            nuevos.append(f'    "{rel}": {n},')
        elif declarado is not None and n > declarado:
            crecieron.append(f"{rel}: {declarado} → {n} líneas")
    mensajes = []
    if nuevos:
        mensajes.append(
            f"Archivos de más de {TOPE} líneas sin declarar (parte el archivo; si adoptas "
            "el gate, pega estas entradas en EXCEPCIONES):\n" + "\n".join(nuevos)
        )
    if crecieron:
        mensajes.append(
            "Archivos congelados que CRECIERON (no subas el número: saca código a otro "
            "módulo):\n" + "\n".join(f"    {c}" for c in crecieron)
        )
    assert not mensajes, "\n\n".join(mensajes)


def test_trinquete_cada_excepcion_declara_exactamente_lo_que_queda():
    errores: list[str] = []
    for rel, declarado in EXCEPCIONES.items():
        if not (RAIZ_REPO / rel).is_file():
            errores.append(f"{rel} ya no existe: borra la entrada")
            continue
        n = lineas_de(rel)
        if n <= TOPE:
            errores.append(f"{rel}: ya cumple ({n} ≤ {TOPE}): borra la entrada")
        elif n < declarado:
            errores.append(f"{rel}: bajó de {declarado} a {n}: actualiza el número")
        # si CRECIÓ, lo reporta el gate de arriba
    assert not errores, "\n".join(errores)


# ── La medición misma ─────────────────────────────────────────────────────────


def test_cuenta_lineas_como_un_editor():
    assert contar_lineas("") == 0
    assert contar_lineas("a") == 1
    assert contar_lineas("a\nb") == 2
    assert contar_lineas("a\nb\n") == 2  # el salto final no suma
    assert contar_lineas("a\n\n") == 2  # una línea vacía real sí
    assert contar_lineas("\n") == 1


def test_crlf_y_lf_cuentan_igual():
    assert contar_lineas("a\r\nb\r\n") == contar_lineas("a\nb\n") == 2
    assert contar_lineas("a\r\nb") == 2
    assert contar_lineas("a\r\n\r\n") == contar_lineas("a\n\n") == 2


def test_coincide_con_splitlines_en_codigo_normal():
    for texto in ("", "x = 1\n", "x = 1\r\ny = 2\r\n", "a\n\nb", "def f():\n    pass\n\n"):
        assert contar_lineas(texto) == len(texto.splitlines())
