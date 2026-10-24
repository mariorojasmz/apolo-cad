"""La API del núcleo que una extensión puede importar, declarada en UN lugar (plan
nucleo-abierto-extensiones-privadas, F1c). Lo de aquí es CONTRATO: quitar o renombrar un nombre de
`SUPERFICIE` o de `MODULOS` (o cambiar su firma de forma incompatible) sube
`extensiones.CONTRATO_EXTENSIONES`; agregar uno no. `tests/test_extensiones_api.py` falla si un
nombre declarado deja de existir.

Dos niveles:

- **`SUPERFICIE`**: lo que una extensión usa para enchufarse (el contrato de `extensiones.py`,
  sus comandos, sus tools, sus modelos de la co-sim y los trinquetes de su suite). Se re-exporta
  AQUÍ, perezoso: `from apolo.extensiones_api import CommandSpec` da el MISMO objeto que
  `apolo.commands.spec.CommandSpec` y sólo importa ese módulo al pedirlo (el MCP lee la extensión
  sin cargar OCCT, F1a).
- **`MODULOS`**: los módulos del núcleo que importa una extensión que hace TRABAJO de dominio (la
  fábrica de publicaciones, F4), con los nombres que usa de cada uno. No se re-exportan: se
  importan de su módulo, que no se movió; lo que aquí se declara es que esos nombres siguen
  existiendo.

Lo que no está aquí no es contrato: un refactor del núcleo lo puede cambiar sin aviso (el CI
nocturno del paquete privado es la red).
"""

from __future__ import annotations

import importlib

#: nombre público → «módulo:atributo» de donde sale (re-exportado perezoso por `__getattr__`).
SUPERFICIE: dict[str, str] = {
    # el contrato de extensiones
    "CONTRATO_EXTENSIONES": "apolo.extensiones:CONTRATO_EXTENSIONES",
    "Extension": "apolo.extensiones:Extension",
    "ExtensionRechazada": "apolo.extensiones:ExtensionRechazada",
    "KINDS_EXTENSION": "apolo.extensiones:KINDS_EXTENSION",
    # comandos (D3/D4): la spec, la pieza que deja el executor, sus params y su error
    "CommandError": "apolo.commands.errors:CommandError",
    "CommandSpec": "apolo.commands.spec:CommandSpec",
    "Feature": "apolo.commands.registry:Feature",
    "Vec3": "apolo.commands.models:Vec3",
    "make_box": "apolo.kernel:make_box",
    # los trinquetes de la suite de una extensión (los MISMOS del núcleo)
    "field_paths": "apolo.commands.strict:field_paths",
    "huella": "apolo.contrato_comandos:huella",
    "literal_campos": "apolo.contrato_comandos:literal_campos",
    "literal_versiones": "apolo.contrato_comandos:literal_versiones",
    "problemas_de_campos": "apolo.contrato_comandos:problemas_de_campos",
    "problemas_de_version": "apolo.contrato_comandos:problemas_de_version",
    # tools MCP y su lugar en el chat
    "EnChat": "apolo.tools.catalogo:EnChat",
    "FastMCPLimpio": "apolo.tools.fastmcp_limpio:FastMCPLimpio",
    # co-simulación
    "Modelo": "apolo.cosim.modelos:Modelo",
    # el documento
    "Document": "apolo.doc.document:Document",
    # la fachada del documento activo para las rutas de una extensión (F1d): lock, sesión,
    # guardia del documento, sólo lectura, autosave, jobs y sus datos del manifest (`ext`)
    "leer_documento": "apolo.api.fachada:leer_documento",
    "mutar_documento": "apolo.api.fachada:mutar_documento",
    "leer_ext": "apolo.api.fachada:leer_ext",
    "poner_ext": "apolo.api.fachada:poner_ext",
    "proyecto_activo": "apolo.api.fachada:proyecto_activo",
    "datos_ext": "apolo.doc.ext_manifest:leer",  # (doc, nombre): para quien ya tiene el `doc`
    # la puerta de publicación (F1d, `Extension.puerta`): sus entradas, el ítem y sus estados
    "Entrada": "apolo.library.calidad.registro:Entrada",
    "Fuente": "apolo.library.calidad.registro:Fuente",
    "General": "apolo.library.calidad.registro:General",
    "FAMILIAS_PUERTA": "apolo.library.calidad.registro:FAMILIAS",
    "siempre": "apolo.library.calidad.registro:siempre",
    "hay": "apolo.library.calidad.registro:hay",
    "hecho": "apolo.library.calidad.registro:hecho",
    "Item": "apolo.library.calidad.item:Item",
    "OK": "apolo.library.calidad.item:OK",
    "FALLA": "apolo.library.calidad.item:FALLA",
    "SIN_EVALUAR": "apolo.library.calidad.item:SIN_EVALUAR",
    "NO_APLICA": "apolo.library.calidad.item:NO_APLICA",
}

#: módulo → nombres que una extensión de dominio usa de él (medido sobre `publicacion/` en la F0 y
#: re-medido al mudarla en la F4a: `paths.publicaciones_dir`/`fabrica_dir` se fueron con ella, que
#: los arma con `data_dir`/`home`/`repo_root`; `entregables` se quedó en el núcleo).
MODULOS: dict[str, tuple[str, ...]] = {
    "apolo": ("__version__",),
    "apolo.entregables": ("COMPLETO", "EnFondo", "GRATIS", "NIVELES", "NUNCA_PUBLICAR",
                          "Recolector", "TIMEOUT", "lista", "omitidos"),
    "apolo.paths": ("data_dir", "home", "logs_dir", "repo_root"),
    "apolo.pruebas": ("api_falsa", "extensiones_aisladas"),
    "apolo.doc.document": ("Document",),
    "apolo.doc.prefijos": ("iter_prefijos",),
    "apolo.kernel.glb": ("PiezaGlb", "TOPE_TRIANGULOS", "ZonaGlb", "a_glb", "escribir_glb"),
    "apolo.kernel.glb_resumen": ("resumen",),
    "apolo.kernel.render_vivo": ("EscenaViva", "extraer_piezas"),
    "apolo.kernel.shapes": ("is_surface",),
    "apolo.media.cierre": ("cierre", "textos_cierre"),
    "apolo.media.codificar": ("Codificador", "ErrorCodificacion", "FfmpegNoEncontrado",
                              "buscar_ffmpeg", "buscar_ffprobe", "mezclar_musica", "sondear"),
    "apolo.media.composicion": ("ESTILO", "guardar_miniatura", "miniatura", "portada", "rotulo"),
    "apolo.media.tarjetas": ("miniatura",),
    "apolo.services.apariencia": ("apariencias_documento", "apariencias_render"),
    "apolo.services.cifras_grupo": ("cifras_grupos",),
    "apolo.services.construccion": ("diferencia", "peso_roles", "revelado"),
    "apolo.services.datos_rotulos": ("datos_rotulos",),
    "apolo.services.definiciones": ("definiciones_de",),
    "apolo.services.guion_video": ("GuionError", "MARCHA_S", "MODOS", "MODO_DISENO",
                                   "MODO_MONTAJE", "capitulos", "duracion_total", "firma",
                                   "guion", "masa_y_medidas", "sin_marcha", "validar_guion"),
    "apolo.services.linea_tiempo": ("AZIMUT_INICIAL", "ELEVACION", "apariciones",
                                    "azimut_construccion", "azimut_orbita", "entrada", "luz",
                                    "opacidad_rotulo", "reparto", "resalte", "total_fotogramas",
                                    "tramos"),
    "apolo.services.marcha_ejemplo": ("MarchaInfiel", "SinMarcha", "armar", "probar"),
    "apolo.services.montaje_video": ("etapas_del_modo",),
    "apolo.services.plan_navegador": ("PlanError", "plan"),
    "apolo.services.puerta_publicacion": ("firma_modelo",),
    "apolo.services.rotulos": ("cifra",),
}

def resolver(origen: str):
    """El objeto de «módulo:atributo» (importa el módulo)."""
    modulo, _, atributo = origen.partition(":")
    return getattr(importlib.import_module(modulo), atributo)


def __getattr__(nombre: str):
    if nombre in SUPERFICIE:
        valor = resolver(SUPERFICIE[nombre])
        globals()[nombre] = valor  # la próxima vez, sin pasar por aquí
        return valor
    raise AttributeError(f"module {__name__!r} has no attribute {nombre!r}: no es API para "
                         "extensiones (mira SUPERFICIE y MODULOS)")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(SUPERFICIE))
