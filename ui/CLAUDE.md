# UI de Apolo (React + three.js + Dockview)

Las convenciones técnicas de la UI (viewport, store, sync, layout) siguen por ahora en el
CLAUDE.md raíz, § Convenciones › UI; se mudan acá en el plan de poda del raíz.

**Todo texto que lee un usuario va de TÚ, en español neutro latinoamericano**: sin voseo, sin
usted, sin españolismos. Vale para los strings de la UI, los mensajes de error de la API que
llegan a pantalla y los prompts de agentes que le hablan al usuario. Gate `src/tuteoNeutro.test.ts`:
lo interno se declara en su `EXCEPCIONES` con la razón, o con `// voseo-interno` al final de la línea.

## Texto y ayuda: la pantalla se explica sola

**Nunca un texto para tapar una interfaz confusa**: si hay que explicar cómo funciona la
pantalla, primero se arregla el rótulo, el botón o el control.

### Cada texto contesta una pregunta, y cada pregunta tiene su lugar

| Pregunta | Nivel | Pieza | Visible | Tope |
|---|---|---|---|---|
| — (se entiende sola) | N0 | un buen rótulo o botón | — | — |
| ¿Qué tengo que hacer aquí? | N1 | `<Pista>` (pista bajo el campo o la acción) | siempre | 1 frase, ≤ 120 caracteres |
| ¿Qué significa esto? | N2 | `<Ayuda>` (ⓘ junto a la palabra) | a pedido | ≤ 3 frases, ≤ 60 palabras |
| ¿Cómo es por dentro? | N3 | `<VerDetalle>` (plegable en el lugar) | a pedido, plegado | con viñetas |
| ¿Cómo funciona esta pantalla? | N3 | «Cómo funciona» del panel (modal) | a pedido | ≤ 150 palabras, una por panel |

Se decide en ese orden: la primera respuesta que cierra, cierra. Un **error caro** (borrar
piezas, restaurar una revisión, aplicar una variante que regenera todo) no se advierte con un
párrafo: se confirma (`useConfirmar`, una sola pieza de confirmación para todo). La primera
vez en un panel la cubre `<EstadoVacio>` (qué va a aparecer + la acción), no un tour.

⚠️ **Estas piezas todavía NO existen en Apolo** (`<Pista>`, `<Ayuda>`, `<VerDetalle>`,
`<EstadoVacio>`, `useConfirmar`): se proponen en un plan antes de crearlas.

- **Presupuesto**: sin contar datos ni rótulos, el texto de ayuda visible por defecto de un
  panel o diálogo no pasa de ~40 palabras. **Una explicación, un lugar**: si el panel lo dice,
  el resto no lo repite.
- **El texto de los schemas es para el AGENTE, no para la persona.** Las `description` de los
  modelos pydantic de comandos son largas a propósito (el agente las necesita completas, con
  nombres de parámetros). En pantalla, la pista es la PRIMERA frase; el resto va a pedido (ⓘ o
  «Ver detalle»). Nunca una versión del roadmap («V6.8-E») en un texto que llega a la UI.
  ⚠️ Hoy NO se cumple: el diálogo de un comando pinta la descripción entera arriba del
  formulario (Taladro: 9 líneas con `position`, `cara` y «V6.8-E») y los botones del ribbon la
  llevan entera en `title=`. Separar el texto del agente del de la persona es plan pendiente
  (toca backend + UI).
- **Excepción de parámetros**: la ⓘ de un campo de comando lleva su texto operativo COMPLETO
  aunque pase el tope (es la documentación del parámetro); lo que se acorta es la pista.
- La **ⓘ se abre en el flujo**, no flota (se cortaría en los paneles de Dockview con
  `overflow`). ⚠️ **Nunca dentro de un `<label>`**: se come el clic del control.
- **`title=` sólo repite lo que ya se ve** (el nombre de un ícono del ribbon o del viewport).
  Lo que el usuario necesita —el motivo de un botón deshabilitado, un costo, qué hace el
  comando— va visible: en una tableta el `title` no existe.
- **Lo técnico suma detalle a pedido, no a la vista**: ids de pieza (`c45_2`), command ids,
  rutas, nombres de parámetros y JSON van en `<VerDetalle>`. Excepción deliberada: el árbol y
  el buscador muestran el id porque el usuario lo usa para hablar con el agente.

### Qué dice cada texto

| Texto | Dice | No dice |
|---|---|---|
| Botón | verbo + objeto: «Crear grupo», «Guardar revisión» | «Aceptar», «Continuar», «OK» |
| Estado | qué está pasando y qué te toca, en una frase | el mecanismo («para liberar el lock») |
| Estado vacío | qué va a aparecer aquí + la acción para empezar | «No hay datos» a secas |
| Error | qué pasó + qué hacer ahora | el stack, el código HTTP, la variable |
| Confirmación | título con el verbo, la consecuencia en una frase, el botón repite el verbo | «¿Estás seguro?» a secas |
| `placeholder` | un ejemplo del valor, inventado | el rótulo, instrucciones, datos reales de un cliente |

**Nunca en pantalla**: versiones del roadmap (V6.8-E, V7.2b) ni la historia («desde que…»,
«porque el backend…»); nombres de comandos o parámetros (`drill_hole`, `en_cara`), variables
de entorno, rutas o claves fuera de un `<VerDetalle>`; una instrucción de editar un archivo o
llamar a la API a mano (es la señal de que falta el control en la UI: se escala); un estado
crudo (`in_progress`, `suppressed`): se mapea a su etiqueta.

### Una cosa, un nombre

Cada concepto tiene UN nombre en toda la interfaz. La tabla se mantiene acá y se respeta en revisión:

| Concepto | Se dice | No se dice |
|---|---|---|
| un objeto 3D del modelo | **pieza** | sólido, feature, cuerpo |
| el dibujo 2D con restricciones | **croquis** | sketch, dibujo |
| las cajas rápidas para tantear volúmenes | **boceto** | maqueta (y no es un croquis) |
| la articulación que deja mover piezas | **junta** | articulación, joint |
| perno, soldadura o contacto declarado entre dos piezas | **unión** | fijador, fastener |
| piezas que se mueven y se listan juntas | **grupo** | conjunto; «sub-ensamblaje» sólo en la ⓘ |
| una foto guardada del proyecto | **revisión** | versión, snapshot |
| un juego de valores de las variables | **variante** | configuración |
| una operación del historial | **comando** | operación, acción |
| una hoja del juego de planos | **lámina** | hoja, página |
| la lista de piezas y compras | **BOM** (sigla del oficio, se acepta) | lista de materiales en un rótulo |
| lo que se pierde / lo que sale de una lista | **Eliminar** / **Quitar** | Borrar, Remover |
| el correo · la acción del mouse | **correo** · **haz clic** / **toca** | email, mail · pulsa, click, ratón |

La interfaz habla en **plural** («te avisamos»). Los nombres internos del código no aparecen
en la vista del usuario. Registro: tuteo neutro latinoamericano, sin voseo ni usted; nada de
inglés en rótulos ni `aria-label` (salvo las siglas de la tabla).

### Por tipo de pantalla

| Tipo en Apolo | Visible | A pedido | Nunca |
|---|---|---|---|
| Lista (árbol, historial, revisiones) | título, «Nuevo …», buscador, estado vacío con acción | ⓘ en el rótulo del filtro | párrafo sobre la lista |
| Ficha (Propiedades) | nombre, material, datos con rótulo | ⓘ; `<VerDetalle>` para ids y params crudos | JSON a la vista |
| Formulario (diálogo de comando, Requisitos) | rótulos claros; pista sólo donde la gente se equivoca | ⓘ del parámetro; validación al salir del campo | la descripción del agente entera arriba; pista en todos los campos |
| Proceso con decisión (Validar, delivery check, FEA) | el veredicto y qué te toca, en una frase; la decisión arriba con su costo | `<VerDetalle>` con el porqué; «Cómo funciona» | la decisión explicada en vez de mostrada |
| Tablero (BOM con costos, Física, Cinemática) | cifra + rótulo; el vacío dice por qué | ⓘ con qué mide | párrafo de metodología |
| Viewport y ribbon | ícono + rótulo corto | `title=` con el nombre | la descripción del comando en `title=` |
| Chat (Asistente IA) | el `placeholder` dice qué se puede pedir, con un ejemplo | — | párrafo de bienvenida |

### Los gates (`cd ui ; npm test`)

- **`src/textoDeAyuda.test.ts`** mide los literales (`subtitle=`, `hint=`, `<Pista>`, `<Ayuda>`)
  contra los topes de arriba, y la historia fuera de un comentario: «plan NNN» y la versión
  del roadmap («V6.8-E»). No ve el texto dinámico que llega de los schemas.
- **Trinquete**: su `EXCEPCIONES` declara cuántas violaciones le quedan a cada archivo. Falla si
  el número sube (texto nuevo que no cumple) y también si baja sin actualizarlo. La lista sólo
  se achica, en el mismo commit que limpia.
- **`src/tuteoNeutro.test.ts`** recorre `src/` entero y rebota voseo (también con pronombre
  pegado: «revisala»), «usted» y españolismos inconfundibles («pulsa», «ratón»). Lo que se
  enumera son las excepciones, con su razón; una excepción que ya no hace falta también falla.
- Los dos son copia del estándar de Caronte: al actualizarlos, traer la versión nueva y
  re-aplicar sólo el bloque «Configuración del proyecto».
- Los `*.test.ts` están fuera de `tsconfig.json` (usan `node:fs`; la app no carga los tipos de
  Node): vitest los corre sin chequeo de tipos.

### Limpiar lo que ya existe

Por panel, no todo de una: leer cada pantalla entera y clasificar cada texto en **jerga**
(nombres internos a la vista), **sobra** (describe la pantalla o explica el sistema),
**confuso**, **falta** (acción irreversible sin confirmar, info sólo en `title=`, vacío sin
acción), **inconsistente** (una cosa con varios nombres) o **registro**. Primero lo que
**miente** (texto que contradice lo que la pantalla hace) y lo que **evita un error caro**
escondido. El estándar es el criterio, no la lista: la lista envejece con la primera fase.
