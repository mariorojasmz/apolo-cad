"""Texto PARA LA PERSONA del registro de comandos: sólo datos.

La `description` de cada modelo pydantic es del AGENTE (larga a propósito, con nombres de
parámetros) y no se toca: la leen el MCP y el agente de la app. Lo que lee una persona
vive aquí y lo sirve la vista persona (`vista_persona.py`, `GET /api/schemas?vista=persona`).
Plan: docs/plans/texto-agente-vs-persona.md (D3–D5, D8). Gate: `tests/test_pistas.py`.

Cómo se escribe una pista (ui/CLAUDE.md § «Texto y ayuda»): una frase que termina en punto,
≤ 120 caracteres, tuteo neutro latinoamericano, dice lo que el comando HACE por la persona
y usa el vocabulario de «Una cosa, un nombre» (pieza, croquis, junta, unión, grupo…).
"""

from __future__ import annotations

#: Pestaña del ribbon por categoría del `REGISTRY`: orden y rótulo. `None` = sin pestaña
#: (las variables tienen su botón propio). Toda categoría nueva tiene que estar aquí: con la
#: lista escrita a mano en la UI, la de superficies quedó sin pestaña (D8).
PESTANAS: dict[str, dict | None] = {
    "crear": {"orden": 1, "rotulo": "Crear"},
    "croquis": {"orden": 2, "rotulo": "Croquis"},
    "superficies": {"orden": 3, "rotulo": "Superficies"},
    "modificar": {"orden": 4, "rotulo": "Modificar"},
    "ensamblaje": {"orden": 5, "rotulo": "Ensamblar"},
    "biblioteca": {"orden": 6, "rotulo": "Biblioteca"},
    "robotica": {"orden": 7, "rotulo": "Robótica"},
    "variables": None,
}

#: Pista de cada comando, por tipo (D4). Un tipo sin pista cae a la primera frase limpia de
#: su descripción (red de transición): el gate exige una por comando. Agrupadas por pestaña.
PISTAS: dict[str, str] = {
    # crear
    "create_box": "Crea una pieza con forma de caja a partir de su ancho, fondo y alto.",
    "create_cylinder": "Crea una pieza cilíndrica con su radio y altura, a lo largo del eje que elijas.",
    "create_structural_profile": (
        "Crea un perfil de aluminio ranurado de sección comercial, cortado al largo que necesites."
    ),
    "create_revolve": (
        "Crea una pieza de revolución haciendo girar un perfil de puntos alrededor de un eje."
    ),
    "create_extrude_poly": "Crea una pieza extruyendo un polígono de puntos hasta la altura que indiques.",
    "import_step": "Importa un archivo STEP como una sola pieza o separado en varias.",
    "run_script": "Crea una pieza con un script de Python, para formas que las demás herramientas no cubren.",
    # croquis
    "sketch_extrude": "Extruye un croquis 2D con restricciones para convertirlo en una pieza.",
    "sketch_revolve": "Hace girar un croquis 2D alrededor del eje Z para crear una pieza de revolución.",
    "sketch_sweep": (
        "Crea una pieza haciendo recorrer un perfil de croquis por una trayectoria 3D o una hélice."
    ),
    "sketch_loft": (
        "Crea una pieza que pasa suavemente entre varios perfiles de croquis a distintas alturas."
    ),
    # superficies
    "boundary_surface": (
        "Crea una superficie a partir de un contorno cerrado de curvas, para darle espesor después."
    ),
    "fill_surface": "Tapa un hueco o cierra un borde de una pieza con un parche de superficie.",
    "thicken": "Da espesor a una superficie para convertirla en una pieza de pared que se puede fabricar.",
    # biblioteca
    "insert_component": "Inserta un componente del catálogo, con largo a medida si se puede cortar.",
    "insert_project": (
        "Inserta un proyecto guardado como un grupo dentro de este, para armar una planta con varias máquinas."
    ),
    "create_conveyor": (
        "Crea un transportador de rodillos completo: largueros, rodillos, patas, arriostrado y motor opcional."
    ),
    "create_belt_conveyor": (
        "Crea una faja de banda completa: bastidor, cama, tambores, banda, tensor, motorreductor y guardas."
    ),
    "create_take_up": (
        "Crea el rodillo de cola de una faja de banda, con su tensor tipo trotadora y un coronado opcional que la centra."
    ),
    "create_drive_roller": (
        "Crea el rodillo motriz de una faja tipo trotadora, con eje largo para acoplar el motorreductor."
    ),
    "create_weldment": (
        "Crea un bastidor soldado de perfiles con su lista de corte, con esquinas a tope o a inglete."
    ),
    "create_frame": (
        "Crea una estructura soldada de perfiles a partir de nodos y barras, como caballetes, trípodes o cerchas."
    ),
    "create_sheet_metal": (
        "Crea una pieza de chapa plegada con pestañas y taladros, lista para sacar su desplegado de corte."
    ),
    # robótica
    "create_robot_arm": "Crea un brazo robótico de 4 ejes con sus juntas listas para moverlo y exportarlo.",
    "add_joint": (
        "Crea una junta para que una pieza gire o se deslice respecto a otra, con sus límites de recorrido."
    ),
    # ensamblar
    "add_mate": (
        "Coloca una pieza respecto a otra por sus caras (a ras, a distancia o alineadas) y la mantiene así "
        "si la otra cambia."
    ),
    "add_rail_constraint": (
        "Obliga a un punto de una pieza móvil a seguir una recta, como un carro que corre por un riel."
    ),
    "add_constraint": (
        "Obliga a un punto de una pieza móvil a quedarse en una recta, un plano, un punto o a una distancia."
    ),
    "fasten": "Declara cómo están unidas dos piezas: perno, soldadura, pegado o contacto.",
    "ground": "Fija una pieza al piso: desde ahí se comprueba que todas las demás estén sujetas.",
    "join_bolted": "Atornilla dos piezas en contacto: taladra ambas y pone los pernos y tuercas de catálogo.",
    "create_group": "Reúne varias piezas en un grupo para moverlas y listarlas como una sola.",
    "transform_group": "Mueve o gira un grupo entero, con todas sus piezas, como si fuera una sola.",
    # modificar
    "boolean_op": (
        "Suma, resta o interseca piezas: el resultado queda en la pieza objetivo y las herramientas desaparecen."
    ),
    "fillet": "Redondea las aristas elegidas de una pieza con el radio que indiques.",
    "chamfer": "Achaflana las aristas elegidas de una pieza a la distancia que indiques.",
    "shell": "Vacía una pieza dejando paredes del espesor que indiques, con las caras elegidas abiertas.",
    "drill_hole": "Hace un agujero en una pieza, desde un punto o sobre una de sus caras.",
    "delete_faces": (
        "Elimina caras de una pieza, como un redondeo o un barreno, y cierra el hueco extendiendo las vecinas."
    ),
    "push_face": "Jala o empuja una cara plana de una pieza para añadirle o quitarle material.",
    "add_joinery": (
        "Talla el encaje de carpintería entre dos piezas de madera: espiga y mortaja, ranura, clavijas o rebaje."
    ),
    "transform": "Mueve o gira una pieza; el giro es alrededor de su propio centro.",
    "center_in": "Centra una pieza dentro de otra en los ejes que elijas y la recentra si la otra cambia.",
    "distribute": "Reparte varias piezas a distancias iguales entre dos posiciones de un eje.",
    "attach": (
        "Lleva una pieza hasta otra haciendo coincidir un punto de cada una, como su base con el tope de la otra."
    ),
    "snap_to": "Coloca una pieza junto a otra o cara contra cara, y la sigue si la otra se mueve.",
    "pattern_linear": "Crea copias de una pieza a distancias iguales en una dirección.",
    "pattern_circular": "Crea copias de una pieza repartidas por igual alrededor de un eje.",
    "pattern_group": "Repite en fila o en rejilla todas las piezas que creó un comando.",
    "mirror_feature": "Crea la copia simétrica de una pieza respecto a un plano.",
    "duplicate_feature": "Crea una copia de una pieza, desplazada la distancia que indiques.",
    "delete_feature": "Elimina una pieza del modelo.",
    # variables (sin pestaña: botón propio)
    "set_variable": (
        "Crea o cambia una variable que puedes usar en cualquier campo numérico; todo el modelo se actualiza con ella."
    ),
}

#: Pista de campo, por «Modelo.campo», SÓLO donde un campo anula a otro o depende de otro
#: (D5). Ninguna más: la pista en todos los campos está prohibida por ui/CLAUDE.md.
PISTAS_CAMPO: dict[str, str] = {
    "DrillHoleParams.cara": "Elige la cara o el punto de entrada, no ambos.",
    "DrillHoleParams.thread": "Con rosca se taladra a la broca de machuelo; el diámetro no se usa.",
    "JoinBoltedParams.patron": "Si llenas el patrón de filas por columnas, reemplaza al número de pernos.",
    "SketchSweepParams.path": "Déjala vacía si el barrido sigue una hélice.",
    "SheetMetalParams.flaps": (
        "Si defines pestañas aquí, reemplazan a los lados con pestaña, la altura y el ángulo de plegado."
    ),
    "SnapToParams.cara": (
        "Si eliges ambas caras, se apoyan cara contra cara y no se usan el lado ni el centrado."
    ),
}
