"""Los textos de una publicación: LEEME, licencia, aviso de responsabilidad y `youtube.txt`
(plan publicacion-tienda, D11, D13 y D15). Puro: recibe datos, devuelve texto.

La validación va al LEEME en lenguaje humano, como argumento de venta, nunca como volcado del
JSON (D11): cada chequeo verde de la puerta de entrega es una frase; una publicación forzada
(D13) lo dice arriba, «con observaciones», con lo que quedó pendiente. La licencia nombra las
licencias y sus URL oficiales, no copia sus textos. `youtube.txt` junta lo que se pega a mano
en YouTube Studio (D15): título, descripción con el enlace a la tienda, capítulos, etiquetas y
créditos de la música.
"""

from __future__ import annotations

APOLO_URL = "https://github.com/mariorojasmz/apolo-cad"
#: Nombre → (nombre largo, resumen en español, código legal). Las Creative Commons 4.0.
LICENCIAS_CONOCIDAS = {
    f"CC {sigla} 4.0": (f"Creative Commons {nombre} 4.0 Internacional",
                        f"https://creativecommons.org/licenses/{ruta}/4.0/deed.es",
                        f"https://creativecommons.org/licenses/{ruta}/4.0/legalcode")
    for sigla, nombre, ruta in (
        ("BY", "Atribución", "by"),
        ("BY-SA", "Atribución-CompartirIgual", "by-sa"),
        ("BY-NC", "Atribución-NoComercial", "by-nc"),
        ("BY-NC-SA", "Atribución-NoComercial-CompartirIgual", "by-nc-sa"),
        ("BY-ND", "Atribución-SinDerivadas", "by-nd"),
        ("BY-NC-ND", "Atribución-NoComercial-SinDerivadas", "by-nc-nd"),
    )
}
LICENCIA_PERSONAL = "Licencia personal de fabricación"
#: Lo que es cada archivo de la vista 3D en la tabla del LEEME (plan vista-3d-tienda, F3).
VISTA_3D_HTML = ("Vista 3D para la web: gira la máquina y, en el celular, mírala a tamaño real. "
                 "Ábrela desde un servidor web (con doble clic el navegador no lee el .glb)")
VISTA_3D_GLB = "Modelo 3D liviano de la vista 3D (sólo apariencia, sin cotas)"
VISTA_3D_POSTER = "Portada de la vista 3D (y miniatura del video)"
MAX_DESCRIPCION_YOUTUBE = 5000
CON_OBSERVACIONES = "con observaciones"

#: Chequeo verde de la puerta de entrega → la frase del LEEME.
_FRASES_OK = {
    "interferencias": "Sin interferencias: ninguna pieza choca con otra en la posición de diseño.",
    "sujeción declarada": "Cada pieza tiene un camino de carga declarado hasta el piso "
                          "(anclajes y uniones): nada queda flotando.",
    "lints pre-entrega": "Sin olvidos de modelado: ningún barreno sin su perno ni piezas sueltas.",
    "salud del documento": "El modelo regenera completo, sin comandos suprimidos.",
    "gravedad": "Estable con gravedad: en la simulación física ninguna pieza cae.",
}


def frases_validacion(calidad: dict) -> list[str]:
    """La validación en frases para el LEEME (D11). `calidad` = `paquete.calidad(...)`."""
    frases = []
    for chequeo in calidad.get("chequeos_ok", []):
        if chequeo in _FRASES_OK:
            frases.append(_FRASES_OK[chequeo])
        elif chequeo.startswith("poses declaradas"):
            frases.append("Las posiciones de trabajo declaradas del mecanismo no chocan.")
    # de lo que no aplica, sólo interesa a quien fabrica la gravedad que no se simuló
    if any(n.startswith("gravedad") for n in calidad.get("no_aplica", [])):
        frases.append("No evaluado: la estabilidad con gravedad (la simulación física no corrió).")
    return frases


def _fila(texto: str, ancho: int = 400) -> str:
    texto = " ".join(str(texto).split())
    return texto if len(texto) <= ancho else texto[: ancho - 1] + "…"


def leeme(ficha: dict, nivel: str, *, cifras: list[dict], calidad: dict,
          archivos: list[tuple[str, str]], variables: dict | None = None,
          apolo: str | None = None, ausentes: list[str] = ()) -> str:
    """El LEEME.md de un nivel (`gratis` o `completo`): qué es, cifras, validación resumida,
    qué trae (y, en `ausentes`, lo que esta versión no trae) y, en el completo, cómo abrir el
    `.apolo`."""
    venta = ("también es gratis" if ficha["nivel"] == "gratis"
             else f"se vende por USD {ficha['precio_usd']:g}")
    lineas = [f"# {ficha['titulo']}", "",
              f"Versión {ficha['version']} · paquete {nivel} · diseñado en Apolo CAD", ""]
    if calidad.get("con_observaciones"):
        lineas += [f"> **Publicado {CON_OBSERVACIONES}.** La revisión de entrega de Apolo no "
                   f"quedó en verde ({calidad.get('veredicto')}); lo pendiente está en "
                   "«Validación». Revísalo antes de fabricar.", ""]
    lineas += [ficha["descripcion"].strip(), ""]
    if nivel == "gratis":
        lineas += ["Este es el paquete **gratis**: renders, plano de conjunto, lista de "
                   "materiales resumida y modelo 3D en STEP. El paquete **completo** (planos de "
                   "taller, lista de corte, memoria de cálculo, manual de ensamblaje y el modelo "
                   f"paramétrico de Apolo) {venta}"
                   + (f": {ficha['url_tienda']}" if ficha.get("url_tienda") else "") + ".", ""]
    if cifras:
        lineas += ["## En cifras", ""] + [f"- **{c['etiqueta']}**: {c['valor']}"
                                          for c in cifras] + [""]
    lineas += ["## Validación", ""]
    lineas += [f"- {f}" for f in frases_validacion(calidad)]
    for o in calidad.get("observaciones", []):
        lineas.append(f"- **Pendiente**: {_fila(o)}")
    lineas += ["", "## Qué trae este paquete", "", "| Archivo | Qué es |", "|---|---|"]
    lineas += [f"| `{ruta}` | {descripcion} |" for ruta, descripcion in archivos]
    for ausente in ausentes:
        lineas += ["", f"> {ausente}"]
    if nivel == "completo" and apolo:
        lineas += ["", "## Cómo abrir el modelo paramétrico", "",
                   f"`{apolo}` es el diseño completo: cada pieza sale de un comando y las cotas "
                   "cuelgan de variables. Cambia una variable y Apolo regenera el modelo; los "
                   "planos, la lista de corte y la memoria salen de nuevo del modelo cambiado.", "",
                   "1. Instala Apolo CAD (libre, MIT; requiere Python 3.11 o superior): "
                   "`pip install apolo-cad`.",
                   "2. Arráncalo con `apolo --open`: se abre en el navegador "
                   "(http://127.0.0.1:8000).",
                   f"3. En **Archivo → Abrir .apolo…** elige `{apolo}`.",
                   "4. Cambia las variables en el panel de variables y revisa el resultado "
                   "antes de fabricar.", ""]
        if variables:
            lineas += ["Variables del diseño:", ""]
            lineas += [f"- `{k}` = {v}" for k, v in variables.items()]
        lineas += ["", f"Apolo CAD: {APOLO_URL}"]
    lineas += ["", "## Licencia y responsabilidad", "",
               f"Licencia de este paquete: **{ficha['licencias'][nivel]}** (ver `LICENCIA.txt`). "
               "Lee `AVISO.txt` antes de fabricar: el diseño no está certificado."]
    return "\n".join(lineas).rstrip() + "\n"


def licencia(nombre: str, ficha: dict) -> str:
    """LICENCIA.txt: el nombre de la licencia, su resumen y su URL oficial (no el texto)."""
    origen = f"«{ficha['titulo']}», versión {ficha['version']}" + (
        f" ({ficha['url_tienda']})" if ficha.get("url_tienda") else "")
    autor = f"Diseño: {origen}"
    if nombre in LICENCIAS_CONOCIDAS:
        largo, resumen, legal = LICENCIAS_CONOCIDAS[nombre]
        cuerpo = [f"{nombre} — {largo}", "",
                  f"Resumen: {resumen}", f"Texto legal: {legal}", "",
                  f"Atribución: al compartir o adaptar, cita el diseño original: {origen}."]
        if "NC" in nombre:
            cuerpo.append("NoComercial: no puedes usar estos archivos con fines principalmente "
                          "comerciales (por ejemplo, venderlos).")
    elif nombre == LICENCIA_PERSONAL:
        cuerpo = [LICENCIA_PERSONAL, "",
                  "- Puedes fabricar las máquinas de este diseño y modificar los archivos para "
                  "fabricarlas.",
                  "- No puedes redistribuir, revender, publicar ni compartir los archivos "
                  "(planos, modelo 3D, .apolo), ni originales ni modificados.",
                  "", "Este resumen no reemplaza el texto legal de la licencia"
                  + (f", publicado en {ficha['url_tienda']}" if ficha.get("url_tienda") else "")
                  + "."]
    else:
        cuerpo = [nombre, "", "Los términos de esta licencia están en la página de la tienda"
                  + (f": {ficha['url_tienda']}" if ficha.get("url_tienda") else ".")]
    return "\n".join([autor, "", *cuerpo]).rstrip() + "\n"


def aviso() -> str:
    """AVISO.txt: responsabilidad. Igual en los dos niveles."""
    return "\n".join([
        "AVISO DE RESPONSABILIDAD",
        "",
        "Este diseño se entrega «tal cual», sin garantías de ningún tipo.",
        "",
        "- No está certificado por ninguna norma ni organismo. Las validaciones que trae "
        "(interferencias, sujeción, gravedad, memoria de cálculo) son automáticas y orientativas.",
        "- Antes de fabricar, haz verificar el diseño, los materiales, las uniones y los cálculos "
        "por un ingeniero de tu localidad, según las normas de tu país y tu aplicación.",
        "- Las guardas de seguridad son obligatorias: ninguna máquina con partes móviles debe "
        "operarse sin ellas, aunque el modelo no las muestre todas.",
        "- La fabricación, la instalación y el uso corren por tu cuenta y riesgo. El autor no "
        "responde por daños a personas o bienes derivados de este diseño.",
    ]) + "\n"


def _tiempo(s: int) -> str:
    h, resto = divmod(int(s), 3600)
    m, s = divmod(resto, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _sin_angulos(texto: str) -> str:
    return texto.replace("<", "‹").replace(">", "›")  # YouTube rechaza < y >


def youtube(ficha: dict, capitulos: list[tuple[int, str]]) -> str:
    """youtube.txt (D15). `capitulos` = `guion_video.capitulos(guion)` (vacío si no cumplen)."""
    desc = [ficha["descripcion"].strip(), ""]
    desc.append("Descarga los planos y el modelo 3D: "
                + (ficha["url_tienda"] or "(pon aquí el enlace de la tienda)"))
    if capitulos:
        desc += ["", "Capítulos:"] + [f"{_tiempo(s)} {_sin_angulos(t)}" for s, t in capitulos]
    musica = ficha.get("musica") or {}
    if musica.get("titulo"):
        desc += ["", f"Música: «{musica['titulo']}» de {musica.get('autor', '')} "
                     f"({musica.get('fuente', '')}) · Licencia: {musica.get('licencia', '')}"]
        if musica.get("atribucion"):
            desc.append(musica["atribucion"])
    desc += ["", f"Diseñado con Apolo CAD: {APOLO_URL}"]
    descripcion = "\n".join(desc)
    if len(descripcion) > MAX_DESCRIPCION_YOUTUBE:
        raise ValueError(f"La descripción para YouTube tiene {len(descripcion)} caracteres "
                         f"(máximo {MAX_DESCRIPCION_YOUTUBE}): acorta la de ficha.yaml")
    partes = ["TÍTULO", ficha["titulo"], "", "DESCRIPCIÓN", descripcion, "",
              "ETIQUETAS", ", ".join(ficha.get("etiquetas") or []), "",
              "MINIATURA", "miniatura.png (1280×720) — súbela como miniatura personalizada.", ""]
    if not capitulos:
        partes += ["(Sin capítulos: YouTube pide al menos 3 de 10 s o más, y este video no los "
                   "tiene.)", ""]
    return "\n".join(partes)
