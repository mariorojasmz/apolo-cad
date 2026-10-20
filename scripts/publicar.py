r"""Publica una máquina terminada para la tienda: paquete gratis y completo, ficha y video de
cómo se construyó (plan `docs/plans/publicacion-tienda.md`, F4).

Dos pasos con un guion editable en medio (D3):

    .\.venv\Scripts\python.exe -B scripts\publicar.py guion --project 38
        [--url http://127.0.0.1:8000] [--slug S] [--version 1.0.0] [--duracion 75] [--titulo T]
        [--modo montaje|diseño]
    # revisa guion.json y completa ficha.yaml en data\publicaciones\<slug>\<version>\
    .\.venv\Scripts\python.exe -B scripts\publicar.py generar --project 38
        [--musica C:\musica\pista.mp3] [--forzar] [--sin-gravedad] [--slug S] [--version V]

Corre en su propio proceso, como cliente de la API viva (D1): abre el proyecto por HTTP (la UI
que tengas abierta cambia a ese proyecto), baja su `.apolo` y renderiza el video sobre una copia
propia. `-B`: un script que importa `apolo` escribe `.pyc` y la API con `--reload` se recarga y
blanquea el documento en memoria; este script lo desactiva igual al arrancar. La lógica vive en
`apolo.publicacion.flujo`; aquí sólo quedan los argumentos. Sale con 2 si se niega o falla.
"""

from __future__ import annotations

import argparse
import contextlib
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True  # = python -B (docstring)
if str(RAIZ / "core") not in sys.path:
    sys.path.insert(0, str(RAIZ / "core"))


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="publicar", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="paso", required=True)
    comunes = argparse.ArgumentParser(add_help=False)
    comunes.add_argument("--project", type=int, required=True, help="id del proyecto en Apolo")
    comunes.add_argument("--url", default="http://127.0.0.1:8000", help="la API de Apolo")
    comunes.add_argument("--slug", default=None,
                         help="carpeta y nombre de los zips (por defecto, del nombre del proyecto)")
    comunes.add_argument("--version", default=None,
                         help="versión del diseño, X.Y.Z (guion: 1.0.0 si está libre; generar: "
                              "la única sin publicar)")
    g = sub.add_parser("guion", parents=[comunes],
                       help="escribe guion.json y el borrador de ficha.yaml para revisar")
    g.add_argument("--duracion", type=float, default=75.0,
                   help="duración objetivo del video en segundos (50 = clip de lanzamiento)")
    g.add_argument("--titulo", default=None, help="título del video (por defecto, el del proyecto)")
    g.add_argument("--modo", choices=("montaje", "diseño"), default="montaje",
                   help="orden del video: montaje = cómo se arma en el taller, desde las uniones "
                        "declaradas (el de la tienda); diseño = el orden en que se modeló")
    gen = sub.add_parser("generar", parents=[comunes],
                         help="puerta de entrega, entregables, video y paquete")
    gen.add_argument("--musica", default=None,
                     help="pista de música (tuya, con su licencia: D8); pisa musica.archivo")
    gen.add_argument("--forzar", action="store_true",
                     help="publica aunque la puerta de entrega no esté en verde («con observaciones»)")
    gen.add_argument("--sin-gravedad", action="store_true",
                     help="la puerta de entrega sin simular la gravedad (más rápida)")
    return ap


def main(argv: list[str] | None = None, cliente=None) -> int:
    """`cliente`: un httpx.Client ya apuntado a la API (los tests pasan un TestClient)."""
    for flujo_ in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError):
            flujo_.reconfigure(encoding="utf-8", errors="replace")  # consola cp1252 de Windows
    args = _parser().parse_args(argv)
    import httpx

    from apolo.media.codificar import FfmpegNoEncontrado
    from apolo.publicacion import flujo
    from apolo.publicacion.entregables import TIMEOUT
    from apolo.publicacion.ficha import FichaError
    from apolo.publicacion.paquete import PublicacionError
    from apolo.publicacion.saneo import SaneoError
    from apolo.services.guion_video import GuionError

    print(f"Aviso: abro el proyecto {args.project} en Apolo ({args.url}): la UI que tengas "
          "abierta cambia a ese proyecto.")
    propio = cliente is None
    cliente = cliente or httpx.Client(base_url=args.url, timeout=TIMEOUT)
    try:
        if args.paso == "guion":
            flujo.guion(cliente, args.project, slug=args.slug, version=args.version,
                        duracion_s=args.duracion, titulo=args.titulo, modo=args.modo)
        else:
            flujo.generar(cliente, args.project, slug=args.slug, version=args.version,
                          musica=args.musica, forzar=args.forzar,
                          con_gravedad=not args.sin_gravedad)
    except (PublicacionError, FichaError, GuionError, SaneoError, FfmpegNoEncontrado) as exc:
        print(f"\n{exc}", file=sys.stderr)
        return 2
    finally:
        if propio:
            cliente.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
