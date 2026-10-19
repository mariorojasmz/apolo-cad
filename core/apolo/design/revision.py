"""Preguntas de taller del REVISOR: fuente única (plan revision-de-taller, D2 y D3).

El modelador ve lo que quiso hacer, no lo que hizo: antes de entregar una máquina la revisa un
SEGUNDO agente, de sólo lectura, con contexto fresco y sin el razonamiento del modelador. Este
módulo es lo que ese revisor pregunta y cómo lo reporta; `plantilla_revisor()` arma el prompt
autocontenido que vive en `docs/revisor-de-taller.md` (lo regenera
`scripts/plantilla_revisor.py` y `tests/test_revision_taller.py` exige que coincidan).

Dos pasadas, en orden (D3 reescrita tras la F0: la pregunta de función por pieza se contesta
con lo que la pieza HACE en el modelo, no con lo que pasaría sin ella, y dejó pasar un
travesaño que sobraba):

1. ESTRUCTURAL, miembro por miembro: el contrafactual de función y el marco de taller.
2. POR PIEZA ÚNICA (un rodillo, no los veinte): material, perfil de mercado, montaje,
   herramienta, guardas y ficha del encargo.

Puro: sin imports de `apolo`. El criterio de ingeniería del modelador sigue en
`guidelines.py`; aquí sólo está lo que se VERIFICA después.
"""

from __future__ import annotations

# ── Pasada 1: la estructura, miembro por miembro, ANTES que lo demás ──────────────────────
PASADA_ESTRUCTURAL: list[dict[str, str]] = [
    {
        "clave": "contrafactual",
        "titulo": "Contrafactual de función",
        "pregunta": "Lista TODOS los miembros estructurales (travesaños, riostras, patas, "
        "ménsulas, placas) y, por cada uno: si lo quitas, ¿qué carga pierde su camino o qué "
        "se desarma? Si otro miembro ya hace lo mismo (p. ej. ejes atornillados que ya amarran "
        "los largueros), sobra. Propón AGREGAR un miembro sólo después de justificar los que "
        "hay.",
        "como": "get_connections (qué une a qué) + near (vecinos) + render_view(isolate, "
        "zoom) del miembro con sus apoyos; la respuesta es lo que pasaría SIN él, no lo que "
        "hace con él.",
    },
    {
        "clave": "marco_taller",
        "titulo": "Marco de taller",
        "pregunta": "Por cada nudo pata–travesaño–larguero: ¿forma un marco cerrado con "
        "apoyo a tope (la carga baja por contacto, no por pernos a cortante)? ¿Algún miembro "
        "va montado ENCIMA de otro cuando iría ENTRE ellos? Compara los dos extremos de la "
        "máquina: si se resuelven distinto, uno de los dos está mal y lo dices sin elegir.",
        "como": "render_view(view frente/lateral, isolate el nudo, zoom) de CADA extremo + "
        "measure de las caras en contacto.",
    },
]

# ── Pasada 2: por pieza ÚNICA (las repetidas se revisan una vez) ─────────────────────────
PREGUNTAS_POR_PIEZA: list[dict[str, str]] = [
    {
        "clave": "funcion",
        "titulo": "Función",
        "pregunta": "¿Qué función cumple? Si la quitas, ¿qué deja de pasar? Si nada, sobra.",
        "como": "get_connections + near; la pasada 1 ya cubrió los miembros estructurales.",
    },
    {
        "clave": "material",
        "titulo": "Material",
        "pregunta": "¿El material que se ve es el que dice? Un perfil ranurado de extrusión, "
        "una forma de fundición o de madera no es acero aunque la BOM lo diga, ni se suelda "
        "a acero.",
        "como": "get_bom / get_scene(ids) (material declarado) contra render_view(isolate, "
        "zoom) de la sección.",
    },
    {
        "clave": "perfil_mercado",
        "titulo": "Perfil de mercado",
        "pregunta": "¿Existe ese perfil, chapa, eje o tornillo así en el mercado (sección, "
        "norma, largo de barra, métrica)?",
        "como": "get_catalog + get_bom (norma y referencia); una medida inventada sin "
        "referencia es hallazgo.",
    },
    {
        "clave": "montaje",
        "titulo": "Montaje y ajuste",
        "pregunta": "¿Cómo se arma y en qué orden? ¿Alguna pieza queda atrapada? Lo que se "
        "estira o se desgasta (cadena, faja), ¿se puede tensar o ajustar en servicio?",
        "como": "get_connections (secuencia de uniones) + render_view(section) del interior; "
        "busca ranuras o tensores donde haga falta ajuste.",
    },
    {
        "clave": "herramienta",
        "titulo": "Acceso de herramienta",
        "pregunta": "¿Entra la herramienta a cada fijador (llave, dado, soldadora) y tiene "
        "giro para apretar?",
        "como": "measure de la tuerca o cabeza al obstáculo más cercano contra la llave de "
        "esa métrica (M8 → 13 mm, M10 → 16, M12 → 18; el dado necesita ~1,5× esa entrecara de "
        "diámetro); render_view(isolate, zoom).",
    },
    {
        "clave": "guardas",
        "titulo": "Guardas",
        "pregunta": "¿Lo que gira o arrastra (cadenas, fajas, piñones, ejes salientes) está "
        "guardado por TODOS los lados accesibles, también por debajo? ¿La guarda se sostiene "
        "y se quita con herramienta?",
        "como": "render_view desde abajo y desde cada costado (azimuth/elevation) + measure "
        "de la abertura al punto de atrapamiento.",
    },
    {
        "clave": "ficha",
        "titulo": "Ficha del encargo",
        "pregunta": "¿Cumple la ficha (carga, ancho de producto, desarmable, instalación, "
        "entorno)? Lo que la ficha marca como asumido se revisa igual y se señala.",
        "como": "get_requirements + measure (ancho útil, alturas) + engineering_check.",
    },
]

#: Las cuatro claves de un hallazgo (D2), en este orden.
CAMPOS_HALLAZGO: tuple[str, ...] = ("pieza", "pregunta", "evidencia", "severidad")

SEVERIDADES: dict[str, str] = {
    "ALTA": "no se puede fabricar, armar u operar con seguridad tal como está (se cae, se "
    "rompe, no aprieta, atrapa una mano).",
    "MEDIA": "funciona, pero con un riesgo o un costo evitable (sobreesfuerzo, ajuste "
    "imposible en servicio, BOM que no sirve para comprar).",
    "BAJA": "terminación o mejora; no cambia si la máquina funciona.",
}

#: La ÚNICA tool que cambia algo: el documento activo de la API (es para todos los clientes).
TOOL_APERTURA = "open_project"

#: Tools de LECTURA que el revisor puede usar. Ninguna muta el documento: el test lo comprueba
#: contra `tools/catalogo.py`. Sin `get_agent_notes`: es el razonamiento del modelador (D2).
TOOLS_LECTURA: tuple[str, ...] = (
    "get_scene", "get_groups", "get_command", "get_connections", "get_requirements",
    "get_bom", "get_mass_properties", "get_catalog", "get_topology", "get_kinematics",
    "get_mates", "get_dof", "get_fit", "render_view", "measure", "near", "verify",
    "check_interference", "check_assembly", "gravity_test", "engineering_check", "cut_list",
)


def preguntas_taller() -> dict:
    """Las preguntas de taller como datos (pasada 1, pasada 2, formato y severidades)."""
    return {
        "pasada_estructural": PASADA_ESTRUCTURAL,
        "por_pieza": PREGUNTAS_POR_PIEZA,
        "campos_hallazgo": list(CAMPOS_HALLAZGO),
        "severidades": SEVERIDADES,
    }


def _lista(preguntas: list[dict[str, str]]) -> list[str]:
    return [f"{i}. **{p['titulo']}** (`{p['clave']}`): {p['pregunta']} *Cómo:* {p['como']}"
            for i, p in enumerate(preguntas, 1)]


def prompt_revisor(proyecto: str = "{proyecto}", ficha: str = "{ficha}") -> str:
    """El prompt AUTOCONTENIDO del revisor. Por defecto deja los marcadores `{proyecto}` (id
    del proyecto) y `{ficha}` (la ficha del encargo, o «la de get_requirements») para que la
    sesión que lo lanza los reemplace."""
    lineas = [
        "Eres el REVISOR DE TALLER de una máquina modelada en Genix Apolo CAD. Otro agente la "
        "modeló; tú no viste cómo ni por qué. Miras el modelo como lo miraría un maestro de "
        "taller que tiene que fabricarla, armarla y operarla, y devuelves lo que está mal con "
        "su prueba.",
        "",
        f"- Proyecto: {proyecto}.",
        f"- Ficha del encargo: {ficha}.",
        "",
        "### Reglas",
        "",
        "- **Sólo lectura.** La única llamada que cambia algo es `open_project` (el documento "
        "activo de la API, al empezar y una sola vez). Ninguna otra tool que mute: ni "
        "comandos, ni variables, ni visibilidad, ni requisitos, ni notas, ni revisiones.",
        "- **Revisas a ciegas.** No leas archivos del repositorio (`docs/`, planes, notas de "
        "sesión) ni `get_agent_notes`; ignora `notas_agente` del briefing de `open_project`: "
        "es el razonamiento del modelador.",
        "- **Tools permitidas:** `" + TOOL_APERTURA + "` y "
        + ", ".join(f"`{t}`" for t in TOOLS_LECTURA) + ".",
        "- **Evidencia obligatoria.** Cada hallazgo lleva un render (vista, ids aislados, "
        "zoom) o una medida (`measure` con sus ids y el valor). Lo que no tiene render ni "
        "medida no se reporta.",
        "- **Gasta poco.** Entra por `get_scene(summary=true)`; revisa UNA pieza de cada tipo "
        "(un rodillo, no los veinte); fotos aisladas y con zoom, no la máquina entera cada vez.",
        "- **Preguntas, no rediseñas.** Si dos soluciones son posibles, lo dices y no eliges: "
        "decide el cliente.",
        "",
        "### Pasada 1 — la estructura, miembro por miembro (primero)",
        "",
        *_lista(PASADA_ESTRUCTURAL),
        "",
        "### Pasada 2 — cada pieza única",
        "",
        *_lista(PREGUNTAS_POR_PIEZA),
        "",
        "### Severidad",
        "",
        *[f"- **{k}**: {v}" for k, v in SEVERIDADES.items()],
        "",
        "### Qué devuelves",
        "",
        "Una lista JSON de hallazgos, de ALTA a BAJA, cada uno con exactamente estas claves:",
        "",
        "```json",
        '[{"pieza": "<id> «nombre»", "pregunta": "<clave de la pregunta>", '
        '"evidencia": "<render o medida, con ids y valor>", "severidad": "ALTA|MEDIA|BAJA"}]',
        "```",
        "",
        "Después, en dos líneas: qué miembros cubrió la pasada 1 y qué piezas únicas la "
        "pasada 2, y lo que no pudiste revisar y por qué.",
    ]
    return "\n".join(lineas)


def plantilla_revisor() -> str:
    """El contenido EXACTO de `docs/revisor-de-taller.md`: cómo se usa + el prompt."""
    cabecera = [
        "<!-- Generado por scripts/plantilla_revisor.py desde core/apolo/design/revision.py: "
        "no se edita a mano. -->",
        "",
        "# Revisor de taller",
        "",
        "Antes de entregar una máquina, otro subagente la revisa con ojos de taller "
        "([plan](plans/revision-de-taller.md)). Se lanza en segundo plano, con contexto "
        "fresco, cuando el modelador terminó y nadie más usa la API (un documento activo para "
        "todos). Se le pasa el prompt de abajo con `{proyecto}` (id) y `{ficha}` (la ficha "
        "del encargo, o «la de get_requirements») reemplazados. Lo que encuentra y se confirma "
        "se corrige en el modelo y deja una regla en [defectos](defectos.md).",
        "",
        "## Prompt",
        "",
    ]
    return "\n".join(cabecera) + "\n" + prompt_revisor() + "\n"
