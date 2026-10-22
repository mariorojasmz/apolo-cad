r"""Publica una máquina terminada para la tienda: paquete gratis y completo, ficha y video de
cómo se construyó (plan `docs/plans/publicacion-tienda.md`, F4).

Dos pasos con un guion editable en medio (D3) y la ficha revisada antes de generar
(fabrica-de-publicaciones, F2):

    .\.venv\Scripts\python.exe -B scripts\publicar.py guion --project 38
        [--url http://127.0.0.1:8000] [--slug S] [--version 1.0.0] [--duracion 75] [--titulo T]
        [--modo montaje|diseño] [--marcha escenario.json [--marcha-s 8]] [--tienda URL]
    # revisa guion.json y completa ficha.yaml en data\publicaciones\<slug>\<version>\
    .\.venv\Scripts\python.exe -B scripts\publicar.py ficha --project 38 --revisar
        [--slug S] [--version V] [--tienda URL]
    .\.venv\Scripts\python.exe -B scripts\publicar.py generar --project 38
        [--musica C:\musica\pista.mp3 | --sin-musica] [--forzar] [--sin-gravedad] [--slug S]
        [--version V] [--render vtk|navegador] [--conservar-cuadros] [--nivel rapido|maximo]
        [--tienda URL]

`ficha --revisar` valida ficha.yaml (descripción, etiquetas, nivel, precio) y los límites de
YouTube del texto que saldría (los mismos de la tienda: título ≤ 100, descripción ≤ 5000 bytes
UTF-8, etiquetas ≤ 500 contando comas y comillas), lo imprime y sale con 2 si algo falla:
quien redacta la ficha la corre hasta que sale limpia. La URL de la máquina no se escribe: es
`<tienda>/maquinas/<slug>` (`--tienda` o `APOLO_TIENDA_URL`, por defecto apolocad.com) y va a
la ficha, al cierre del video y a la descripción, que además lleva el aviso de responsabilidad
con el enlace a `<tienda>/terminos#responsabilidad`.

Música (D9): sin `--musica`, la pista de `musica.archivo` de ficha.yaml o, si no hay, la menos
usada de la biblioteca `~\.apolo\musica\pistas.json` (`APOLO_MUSICA_DIR` la cambia), que se
acredita sola en la descripción; sin pistas, el video sale sin música y lo avisa.
`--sin-musica` fuerza silencio.

`--render navegador` (plan video-realista, D7) graba el video con el visor de Apolo en Edge o
Chrome sin ventana (con la GPU, nada se descarga); sin navegador o sin GPU avisa y usa VTK. Con
`--nivel maximo` traza cada cuadro con trazado de rayos (D6): horas por video, para la noche.
`--marcha` (en `guion`) suma la máquina andando: el JSON es el escenario de la simulación, el
mismo que recibe la tool `simulate`; sólo la graba el navegador.

Corre en su propio proceso, como cliente de la API viva (D1): abre el proyecto por HTTP (la UI
que tengas abierta cambia a ese proyecto), baja su `.apolo` y renderiza el video sobre una copia
propia; los entregables se piden a la API mientras el video se renderiza aquí (D6 de
video-tienda-pulido). Si a la API le falta ODA File Converter, `guion` y `generar` lo avisan al
empezar y el paquete sale sin DWG (D5). `-B`: un script que importa `apolo` escribe `.pyc` y la API con `--reload` se recarga y
blanquea el documento en memoria; este script lo desactiva igual al arrancar. La lógica vive en
`apolo.publicacion.flujo`; aquí sólo quedan los argumentos. Sale con 2 si se niega o falla.

Un tercer paso sube a la tienda (apolocad.com) el paquete que dejó `generar` y lo publica, sin
navegador (F6 del plan):

    $env:APOLO_TIENDA_LLAVE = 'apolo_pub_...'   # Mi cuenta → Llaves de publicación
    .\.venv\Scripts\python.exe -B scripts\publicar.py subir --project 38
        [--slug S] [--version V] [--tienda https://apolocad.com] [--borrador] [--ensayo]

La llave sale SÓLO de `APOLO_TIENDA_LLAVE` (como argumento quedaría en el historial); para que
quede en las consolas nuevas: `[Environment]::SetEnvironmentVariable('APOLO_TIENDA_LLAVE',
'apolo_pub_...','User')`. Nunca se imprime entera. `--project` busca el slug por el nombre del
proyecto en la API sin abrirlo; con `--slug` no hace falta la API. Sin `--version`, la última
versión generada. `--tienda` (o `APOLO_TIENDA_URL`) cambia la tienda; `--borrador` importa sin
publicar; `--ensayo` sólo pide la revisión e imprime el plan. La lógica, en
`apolo.publicacion.tienda`.

Y el video del mismo paquete va a YouTube, sin YouTube Studio (plan fabrica-de-publicaciones,
F1):

    .\.venv\Scripts\python.exe -B scripts\publicar.py youtube --slug S
        [--version V] [--publico] [--ensayo] [--forzar] [--reautorizar] [--tienda URL]

Necesita el cliente OAuth de escritorio en `~\.apolo\youtube\client_secret.json`
(`APOLO_YOUTUBE_DIR` cambia la carpeta). La primera vez abre el navegador: entra con la cuenta
del canal y elige «Apolo CAD»; el permiso queda en `token.json` de esa carpeta y las siguientes
no piden nada. Antes de subir imprime el canal. Sube PRIVADO (D4) salvo `--publico`, con la
miniatura y el texto de `youtube.txt`, y deja `youtube.json` (id y enlace) en la carpeta: si ya
existe no resube, salvo `--forzar`. `--ensayo` muestra canal, título, descripción y etiquetas
sin subir (sirve para autorizar la primera vez). `--reautorizar` pide el permiso de nuevo. Con
el cupo diario agotado sale con 2 y lo dice: se sigue al día siguiente. La lógica, en
`apolo.publicacion.youtube`.
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
    comunes.add_argument("--tienda", default=None,
                         help="la tienda de la URL de la máquina y del aviso (por defecto "
                              "APOLO_TIENDA_URL o https://apolocad.com)")
    g = sub.add_parser("guion", parents=[comunes],
                       help="escribe guion.json y el borrador de ficha.yaml para revisar")
    g.add_argument("--duracion", type=float, default=75.0,
                   help="duración objetivo del video en segundos (50 = clip de lanzamiento)")
    g.add_argument("--titulo", default=None, help="título del video (por defecto, el del proyecto)")
    g.add_argument("--modo", choices=("montaje", "diseño"), default="montaje",
                   help="orden del video: montaje = cómo se arma en el taller, desde las uniones "
                        "declaradas (el de la tienda); diseño = el orden en que se modeló")
    g.add_argument("--marcha", default=None,
                   help="JSON con el escenario de la simulación (el de `simulate`): suma la "
                        "máquina andando al video (sólo con --render navegador)")
    g.add_argument("--marcha-s", type=float, default=None,
                   help="segundos de la máquina andando (por defecto 8)")
    gen = sub.add_parser("generar", parents=[comunes],
                         help="puerta de entrega, entregables, video y paquete")
    gen.add_argument("--musica", default=None,
                     help="pista de música (tuya, con su licencia: D8); pisa musica.archivo y "
                          "la biblioteca")
    gen.add_argument("--sin-musica", action="store_true",
                     help="el video sale sin música (no usa la biblioteca)")
    gen.add_argument("--forzar", action="store_true",
                     help="publica aunque la puerta de entrega no esté en verde («con observaciones»)")
    gen.add_argument("--sin-gravedad", action="store_true",
                     help="la puerta de entrega sin simular la gravedad (más rápida)")
    gen.add_argument("--render", choices=("vtk", "navegador"), default="vtk",
                     help="quién dibuja el video: vtk (el de siempre) o navegador (el visor de "
                          "Apolo en Edge o Chrome sin ventana, con la GPU; cae a vtk sin ellos)")
    gen.add_argument("--conservar-cuadros", action="store_true",
                     help="con --render navegador, deja los cuadros en la carpeta de la grabación")
    gen.add_argument("--nivel", choices=("rapido", "maximo"), default="rapido",
                     help="con --render navegador: rapido (el visor en calidad alta) o maximo "
                          "(trazado de rayos por cuadro: horas por video, para correr de noche)")
    fi = sub.add_parser("ficha", help="revisa ficha.yaml y muestra el texto de YouTube que saldría")
    fi.add_argument("--project", type=int, default=None,
                    help="id del proyecto en Apolo (para el slug; sobra con --slug)")
    fi.add_argument("--url", default="http://127.0.0.1:8000", help="la API de Apolo")
    fi.add_argument("--slug", default=None, help="carpeta de la publicación")
    fi.add_argument("--version", default=None,
                    help="versión, X.Y.Z (por defecto, la única con guion sin publicar)")
    fi.add_argument("--tienda", default=None,
                    help="la tienda (por defecto APOLO_TIENDA_URL o https://apolocad.com)")
    fi.add_argument("--revisar", action="store_true", required=True,
                    help="valida la ficha y los límites de YouTube; sale con 2 si algo falla")
    sube = sub.add_parser("subir", help="sube el paquete generado a la tienda y lo publica "
                                         "(llave en APOLO_TIENDA_LLAVE)")
    sube.add_argument("--project", type=int, default=None,
                      help="id del proyecto en Apolo (para el slug; sobra con --slug)")
    sube.add_argument("--url", default="http://127.0.0.1:8000", help="la API de Apolo")
    sube.add_argument("--slug", default=None, help="carpeta de la publicación")
    sube.add_argument("--version", default=None,
                      help="versión a subir, X.Y.Z (por defecto, la última generada)")
    sube.add_argument("--tienda", default=None,
                      help="la tienda (por defecto APOLO_TIENDA_URL o https://apolocad.com)")
    sube.add_argument("--borrador", action="store_true", help="importa sin publicar")
    sube.add_argument("--ensayo", action="store_true",
                      help="sólo la revisión de la tienda y el plan: no sube nada")
    yt = sub.add_parser("youtube", help="sube el video del paquete generado a YouTube (privado)")
    yt.add_argument("--project", type=int, default=None,
                    help="id del proyecto en Apolo (para el slug; sobra con --slug)")
    yt.add_argument("--url", default="http://127.0.0.1:8000", help="la API de Apolo")
    yt.add_argument("--slug", default=None, help="carpeta de la publicación")
    yt.add_argument("--version", default=None,
                    help="versión a subir, X.Y.Z (por defecto, la última generada)")
    yt.add_argument("--tienda", default=None,
                    help="la tienda del enlace de la descripción si la ficha no trae url_tienda "
                         "(por defecto APOLO_TIENDA_URL o https://apolocad.com)")
    yt.add_argument("--publico", action="store_true",
                    help="sube PÚBLICO (sólo tras la auditoría de YouTube; por defecto, privado)")
    yt.add_argument("--ensayo", action="store_true",
                    help="muestra canal, título, descripción y etiquetas: no sube nada")
    yt.add_argument("--forzar", action="store_true",
                    help="sube aunque youtube.json diga que ya se subió (queda duplicado)")
    yt.add_argument("--reautorizar", action="store_true",
                    help="borra el permiso guardado y lo pide de nuevo en el navegador")
    return ap


def _carpeta(args, *, pendiente: bool = False):
    """La carpeta de la versión: el slug, de --slug o del nombre del proyecto en la API. Con
    `pendiente`, la versión con guion sin publicar (la de `ficha --revisar`)."""
    import httpx

    from apolo import paths
    from apolo.publicacion import paquete, tienda
    from apolo.publicacion.paquete import PublicacionError

    slug = args.slug
    if slug is None:
        if args.project is None:
            raise PublicacionError("Pasa --project (o --slug) para saber qué paquete usar.")
        with httpx.Client(base_url=args.url, timeout=30.0) as api:
            slug = tienda.slug_de_proyecto(api, args.project)
    raiz = paths.publicaciones_dir()
    if pendiente:
        version = args.version or paquete.version_pendiente(raiz, slug)
        return paquete.carpeta_version(raiz, slug, version)
    return tienda.carpeta_publicada(raiz, slug, args.version)


def _ficha(args) -> int:
    """`publicar ficha --revisar`: la lógica, en `apolo.publicacion.preparar.revisar`."""
    from apolo.publicacion import preparar, tienda
    from apolo.publicacion.ficha import FichaError
    from apolo.publicacion.paquete import PublicacionError

    try:
        preparar.revisar(_carpeta(args, pendiente=True),
                         tienda=tienda.url_de_la_tienda(args.tienda))
    except (FichaError, PublicacionError) as exc:
        print(f"\n{exc}", file=sys.stderr)
        return 2
    return 0


def _subir(args, cliente=None) -> int:
    """`publicar subir`: la llave y la tienda antes de tocar la red."""
    from apolo.publicacion import tienda
    from apolo.publicacion.paquete import PublicacionError

    try:
        llave = tienda.llave_del_entorno()
        url = tienda.url_de_la_tienda(args.tienda)
        tienda.subir(_carpeta(args), tienda=url, llave=llave, borrador=args.borrador,
                     ensayo=args.ensayo, cliente=cliente)
    except PublicacionError as exc:
        print(f"\n{exc}", file=sys.stderr)
        return 2
    return 0


def _youtube(args, cliente=None, abrir=None) -> int:
    """`publicar youtube`: la lógica, en `apolo.publicacion.youtube`."""
    from apolo.publicacion import tienda, youtube
    from apolo.publicacion.paquete import PublicacionError

    extra = {} if abrir is None else {"abrir": abrir}
    try:
        youtube.subir(_carpeta(args), tienda=tienda.url_de_la_tienda(args.tienda),
                      publico=args.publico, ensayo=args.ensayo, forzar=args.forzar,
                      reautorizar=args.reautorizar, cliente=cliente, **extra)
    except PublicacionError as exc:
        print(f"\n{exc}", file=sys.stderr)
        return 2
    return 0


def _escenario(ruta: str | None) -> dict | None:
    import json

    from apolo.publicacion.paquete import PublicacionError

    if ruta is None:
        return None
    try:
        # utf-8-sig: el `Set-Content -Encoding utf8` de PowerShell 5.1 escribe con BOM
        datos = json.loads(Path(ruta).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublicacionError(f"No pude leer el escenario de la marcha {ruta}: {exc}") from None
    if not isinstance(datos, dict):
        raise PublicacionError(f"El escenario de la marcha {ruta} debe ser un objeto JSON {{…}}.")
    return datos


def main(argv: list[str] | None = None, cliente=None, abrir=None) -> int:
    """`cliente`: un httpx.Client ya apuntado a la API (los tests pasan un TestClient); en
    `subir`, el que habla con la tienda; en `youtube`, con Google. `abrir`: cómo `youtube` abre
    el navegador (los tests simulan la vuelta)."""
    for flujo_ in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError):
            flujo_.reconfigure(encoding="utf-8", errors="replace")  # consola cp1252 de Windows
    args = _parser().parse_args(argv)
    if args.paso == "subir":
        return _subir(args, cliente=cliente)
    if args.paso == "youtube":
        return _youtube(args, cliente=cliente, abrir=abrir)
    if args.paso == "ficha":
        return _ficha(args)
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
                        duracion_s=args.duracion, titulo=args.titulo, modo=args.modo,
                        marcha=_escenario(args.marcha), marcha_s=args.marcha_s,
                        tienda=args.tienda)
        else:
            # D6 de video-tienda-pulido: con la API en otro proceso (la URL), los entregables
            # se piden mientras aquí se renderiza el video; un cliente prestado (los tests, con
            # la API en este proceso) va en serie
            flujo.generar(cliente, args.project, slug=args.slug, version=args.version,
                          musica=args.musica, forzar=args.forzar,
                          con_gravedad=not args.sin_gravedad, paralelo=propio,
                          render=args.render, conservar_cuadros=args.conservar_cuadros,
                          url=args.url, nivel=args.nivel, tienda=args.tienda,
                          sin_musica=args.sin_musica)
    except (PublicacionError, FichaError, GuionError, SaneoError, FfmpegNoEncontrado) as exc:
        print(f"\n{exc}", file=sys.stderr)
        return 2
    finally:
        if propio:
            cliente.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
