"""CLI de Genix Apolo CAD.

    apolo              levanta la API + la UI web en http://127.0.0.1:8000
    apolo --open       …y abre el navegador
    apolo-mcp          servidor MCP por stdio (lo lanza el cliente MCP, no tú)

`apolo-mcp` es un cliente fino de la API HTTP: necesita que `apolo` esté corriendo.
"""

from __future__ import annotations

import argparse
import sys
import threading
import webbrowser


def _version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("apolo-cad")
    except PackageNotFoundError:  # checkout sin instalar
        return "dev"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="apolo", description="Genix Apolo CAD — servidor de la API y la UI web."
    )
    parser.add_argument("--host", default="127.0.0.1", help="interfaz (por defecto 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="puerto (por defecto 8000)")
    parser.add_argument("--reload", action="store_true", help="recarga en caliente (desarrollo)")
    parser.add_argument("--open", action="store_true", help="abre el navegador al arrancar")
    parser.add_argument("--version", action="version", version=f"apolo-cad {_version()}")
    args = parser.parse_args(argv)

    from apolo import paths

    url = f"http://{args.host}:{args.port}"
    print(f"Genix Apolo CAD {_version()}")
    print(f"  datos : {paths.db_path()}")
    ui = paths.ui_dist()
    print(f"  UI    : {ui if ui is not None else 'no incluida (API headless — el MCP funciona igual)'}")
    print(f"  API   : {url}")

    if args.open:
        threading.Timer(1.5, webbrowser.open, args=(url,)).start()

    try:
        import uvicorn
    except ImportError:  # pragma: no cover — uvicorn es dependencia dura
        print("Falta uvicorn: pip install 'apolo-cad'", file=sys.stderr)
        return 1

    uvicorn.run("apolo.api.main:app", host=args.host, port=args.port, reload=args.reload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
