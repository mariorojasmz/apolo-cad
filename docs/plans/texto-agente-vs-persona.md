---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: implementación delegada por Mario sin aprobación previa del contrato (ver Estado y origen); revisar D1–D13 al volver
descripcion: Cada diálogo de comando te dice en una frase qué hace, el detalle técnico queda a un clic y aparece la pestaña Superficies en el ribbon
---

# Texto del agente y texto de la persona — cada comando me dice en una frase qué hace

## Estado y origen

**Origen**: deuda declarada en `ui/CLAUDE.md` § «Texto y ayuda» al adoptar el estándar de textos
de Caronte: «Separar el texto del agente del de la persona es plan pendiente (toca backend + UI)».
Mario la priorizó en la lista de pendientes de la auditoría del 2026-10-03 y delegó su ejecución:
«me voy a ir por muchas horas, ejecuta todo los planes pendientes al final revisamos». Por eso el
contrato se implementa **sin aprobación previa**: las decisiones D1–D13 quedan para que las vete al
volver, y nada se mergea a `main` hasta entonces (rama de integración `worktree-auditoria-refactors`).

**Evidencia que lo dispara**:
- El diálogo «Taladro» pinta sobre el formulario los 589 caracteres de la descripción del agente
  (~95 palabras; el presupuesto del diálogo es ~40), con `position`, `cara`, `en_cara`, `axis`,
  `thread`, «depth=0» y «V6.8-E».
- Cada botón del ribbon lleva esa misma descripción entera en `title=`.
- Los 3 comandos de superficies (V5.11) no tienen pestaña en el ribbon: desde la UI no se pueden crear.

## El problema / lo que hay hoy

**Una sola fuente de texto para dos lectores.** `_schema_entry`
(`core/apolo/commands/registry.py:2281-2289`) manda el docstring del modelo dos veces: como
`description` del entry y como `description` raíz del schema. Lo consumen:

| Consumidor | Cómo lo lee | Dónde |
|---|---|---|
| UI, diálogo de comando | `<p className="hint">{schema.description}</p>`, entera, sobre el formulario | `ui/src/panels/CommandDialog.tsx:17` |
| UI, ribbon | `title={s.description}` en cada botón | `ui/src/panels/Ribbon.tsx:100` |
| UI, campos | `const unit = eff.description`, junto al rótulo como `.unit` | `ui/src/forms/SchemaForm.tsx:345` (usos :474, :491, :536) |
| MCP | `get_command_schemas` reenvía `/api/schemas` tal cual | `core/apolo/mcp_server.py:241-249` |
| Agente de la app | `build_tools` mete `__doc__` y `model_json_schema()` de los 53 comandos | `core/apolo/agent/agent.py:74-78` |

**Medido sobre `command_schemas()`** (criterios equivalentes a `textoDeAyuda.test.ts`; F0 re-mide
con el regex exacto):

| Qué | Medida |
|---|---|
| Comandos y categorías | 53 en 8: modificar 19, biblioteca 9, ensamblaje 8, crear 7, croquis 4, superficies 3, robotica 2, variables 1 |
| Descripciones de comando con versión del roadmap | **9/53**: `insert_project` V5.2b, `create_weldment` V5.8, `create_frame` V5.8, `create_sheet_metal` V5.5, `join_bolted` V6.5b, `drill_hole` V6.8-E, `delete_faces` V5.3, `push_face` V5.3, `snap_to` V6.8-E |
| Con identificadores entre backticks | **25/53** |
| Con más de una frase | **40/53** |
| Con más de 120 caracteres | **40/53**: mediana 246, máximo 1100 (`create_take_up`), total 18 679 |
| Descripciones de campo | 528 apariciones, 115 textos únicos. Con versión: 2 (`SlideUV`, «V6.8-E»). Con backticks: 22 (7 únicos). Más de una frase: 26 (8). Más de 120 car.: 34 (12). La más larga: formato de croquis, 1065 car. |
| Descripciones de campo pintadas junto al rótulo | **87**; **43 no son una unidad** («pernos en una fila…; ignorado si das `patron`», «EN DESUSO: …») |
| Rótulo visible con versión | `SheetMetalParams.flaps`: «Pestañas ricas (V5.5)» (`models.py:708`) |
| Versiones en el payload de `get_command_schemas()` | **21** en 138 650 bytes |
| Unidades en las descripciones | 86 descripciones empiezan con «mm» o «grados» |

**Ribbon**: `TABS` escrito a mano (`Ribbon.tsx:11-18`) con 6 categorías, sin `superficies`;
`boundary_surface`, `fill_surface` y `thicken` (`registry.py:2071-2073`) no aparecen en ninguna
pestaña ni tienen ícono (`ui/src/ui/icons.tsx:51`, `FALLBACK`). Los botones estáticos también
explican en `title=` (`Ribbon.tsx:70, 83, 91`).

**Registro y vocabulario**: 0 voseo y 0 usted en los schemas; el problema es el vocabulario:
«sólido» 46, «sólidos» 8, «feature(s)» 9, «fijador(es)» 7, «conjunto» 6, «joint» 4,
«sub-ensamblaje» 4, «sketch» 3, «snapshot» 2, «borrar» 1. Rótulos fuera de la tabla: 4 de comando
(«Fijador», «Borrar caras», «Grupo / sub-ensamblaje», «Mate») y 21 de campo.

**La regla escrita hoy («la pista es la PRIMERA frase») no alcanza**: sólo **18/53** primeras
frases, sin versión, cumplen 1 frase, ≤ 120 caracteres, sin backticks, sin `snake_case` y sin
vocabulario prohibido; y entre esas hay malas pistas («depth=0» no corta la frase en `drill_hole`).

## Lo que se revisó antes de escribir esto

- **El MCP y el agente leen el schema crudo** (`mcp_server.py:241-249`, `agent.py:74-78`): una
  clave nueva en el schema (`x-pista` vía `json_schema_extra`) o en el entry le llega al agente y
  rompe «payload byte-idéntico» (y suma tokens). **De aquí salen las dos vistas (D2).**
- **Trinquetes** (`tests/test_tamano_archivos.py`): `models.py` 1509, `registry.py` 2299,
  `api/main.py` 4913, `agent.py` 606, `mcp_server.py` 1517; UI `SchemaForm.tsx` 613. Ninguno
  puede crecer. **De aquí salen D3 y D12.**
- **`GET /api/schemas/{command_type}` está en `main.py:951`**: una ruta `/api/schemas/persona`
  daría 404. **De aquí sale el query param de D2.**
- **`SchemaForm` usa la `description` del campo como unidad** (`:345`): en la vista persona la
  unidad viaja aparte (`x-unidad`).
- **`.cmd-btn span` corta el rótulo a 80 px con elipsis** (`ui/src/styles.css:151`): `title=` con
  el nombre completo sí aporta, como permite `ui/CLAUDE.md`.
- **Los gates de texto de la UI no ven el texto dinámico**: el gate de pistas es de backend y
  aplica los mismos criterios (`FIN_DE_ORACION`, `HISTORIA`, listas de `tuteoNeutro.test.ts`).
- **Campos que anulan o dependen de otro**: `DrillHoleParams.cara`/`.thread`
  (`models.py:872-895`), `JoinBoltedParams.patron` (:1341), `SketchSweepParams.path` (:1084),
  `SheetMetalParams.flaps` (:707), `SnapToParams.cara` (:299). Criterio de D5.
- **Ningún otro lugar de la UI lee `CommandSchema.description`** (sólo `Ribbon.tsx:100` y
  `CommandDialog.tsx:17`): se puede quitar del tipo (D10).

## Decisiones (para vetar)

- **D1. El texto del agente no cambia ni un byte.** `GET /api/schemas`, `GET /api/schemas/{type}`,
  la tool `get_command_schemas` y `build_tools(auto=True|False)` quedan idénticos: F0 toma su huella
  sha256 y F1 y F5 la comparan. *Porqué*: el agente necesita las descripciones completas; quitarle
  la historia es otra decisión.
- **D2. Dos vistas del mismo registro.** Agente = la de hoy. Persona = `GET /api/schemas?vista=persona`,
  la única que pide la UI. En `main.py` cambian dos líneas, sin sumar:
  `get_schemas(vista: str = Query("agente", pattern="^(agente|persona)$"))`. Un valor desconocido
  da 422. *Porqué*: no cuesta líneas, no choca con `/{command_type}`, el default queda intacto.
- **D3. Las pistas viven al lado del registro, no dentro del modelo.** `commands/pistas.py` (sólo
  datos: `PISTAS[tipo]`, `PISTAS_CAMPO["Modelo.campo"]`, `PESTANAS[categoría]`) y
  `commands/vista_persona.py` (lógica: `command_schemas_persona()`, `limpiar_historia()`,
  `primera_frase()`, `unidad_de()`). *Porqué*: `models.py`/`registry.py` congelados y
  `json_schema_extra` cambiaría el payload del agente. Sigue siendo una sola fuente en el backend.
- **D4. Pista explícita para los 53 comandos**; la primera frase limpia queda sólo como red y
  transición. *Porqué*: sólo 18/53 primeras frases sirven. Tono de ejemplo: `drill_hole` «Hace un
  agujero en una pieza, desde un punto o sobre una de sus caras.»; `fasten` «Declara cómo están
  unidas dos piezas: perno, soldadura, pegado o contacto.»; `create_group` «Reúne varias piezas en
  un grupo para moverlas y listarlas como una sola.» («Reúne» y no «Junta»: junta es la articulación).
- **D5. Pista de campo sólo donde un campo anula o depende de otro** (los 6 de arriba). Presupuesto
  por diálogo, medido por el gate: pista del comando + pistas de sus campos ≤ 40 palabras.
- **D6. El texto completo va a pedido.** Comando: `detalle` (descripción limpia) en
  `<VerDetalle resumen="Detalle técnico">`, plegado, sólo si tiene más de una frase. Campo: su
  `description` limpia en la ⓘ (`<Ayuda>`), completa por la excepción de parámetros; la unidad
  visible como `x-unidad` (lista cerrada: «grados o mm», «mm», «grados»). Backticks → `<code>`.
- **D7. La historia se limpia en el servidor**: la vista persona quita las versiones del roadmap de
  todo `title`/`description` a cualquier profundidad, normaliza espacios y quita la `description`
  raíz duplicada. *Porqué*: ningún gate de la UI ve el texto dinámico; un pytest sí.
- **D8. Las pestañas del ribbon salen del backend** (`PESTANAS`: crear 1, croquis 2, superficies 3,
  modificar 4, ensamblaje 5 «Ensamblar», biblioteca 6, robotica 7 «Robótica», variables None). El
  gate exige que toda categoría del `REGISTRY` esté en `PESTANAS`. *Porqué*: con la lista a mano, una
  categoría nueva desaparece en silencio (pasó con V5.11).
- **D9. `title=` del ribbon = el nombre visible** (estáticos: «Croquis», «Catálogo», «Variables»).
- **D10. `CommandSchema` de la UI pierde `description`** y gana `pista`, `detalle`, `pestana`;
  `JsonSchema` gana `x-pista?`/`x-unidad?`. *Porqué*: `tsc` falla si una pantalla vuelve a pintar el
  texto del agente.
- **D11. Piezas mínimas**, una por archivo en `ui/src/ui/`: `Pista.tsx`, `Ayuda.tsx` (botón ⓘ
  `type="button"`, `aria-expanded`, abre un bloque `role="note"` en el flujo, nunca dentro de un
  `<label>`), `VerDetalle.tsx` (`<details>` nativo), `textoTecnico.tsx` (backticks → `<code>`). Sin
  `<EstadoVacio>` ni `useConfirmar`.
- **D12. Trinquetes: nada congelado crece.** `SchemaForm.tsx` BAJA (el envoltorio de campo sale a
  `ui/src/forms/Campo.tsx`); `main.py` 0 líneas netas; `models.py`, `registry.py`, `agent.py`,
  `mcp_server.py` intactos.
- **D13. Gate de backend `tests/test_pistas.py`**: `set(PISTAS) == set(REGISTRY)`; claves de
  `PISTAS_CAMPO` existentes; cada pista: 1 frase, ≤ 120 caracteres, termina en punto, sin versión,
  sin backticks, sin identificadores con `_`, sin `param=valor`, sin MAYÚSCULAS enfáticas fuera de
  siglas, sin las palabras «No se dice» de `ui/CLAUDE.md` (sólido/s, feature/s, sketch, joint/s,
  fastener/s, fijador/es, snapshot/s, sub-ensamblaje, borrar/borra, remover), sin voseo ni usted
  (listas LEÍDAS de `ui/src/tuteoNeutro.test.ts`; falla si trae < 40 imperativos); presupuesto D5;
  `PESTANAS` cubre las categorías.

## Alternativas descartadas

- `json_schema_extra={"x-pista": …}` en `models.py`: cambia el payload del MCP/agente y `models.py`
  está congelado.
- Un bloque `ui=` en `CommandSpec`: `registry.py` congelado y no cubre campos.
- Acortar las `description`: el agente las necesita completas.
- Cortar la primera frase en la UI (regla de hoy): sólo 18/53 sirven y seguiría llegando historia.
- Un mapa de pistas en TypeScript: rompe la fuente única.
- Ruta `/api/schemas/persona` o `APIRouter` nuevo: la ruta la captura `/{command_type}`.
- Limpiar las versiones en la UI: duplica el regex en TS y vitest no ve el texto dinámico.
- Pista en todos los campos: prohibido por `ui/CLAUDE.md`.
- Generar las pistas con el modelo en tiempo de ejecución: no determinista, cuesta y nadie las revisa.

## Fases

Cada fase la implementa un subagente opus en su worktree. La sesión principal lee el diff contra
este contrato y re-corre las suites. **Ajuste por la delegación**: no se mergea a `main` ni se
reinicia la API de Mario; la verificación en navegador se hace con una API levantada desde el
worktree de integración en el puerto 8001 (base vacía, `data/` del worktree), sin tocar :8000.

- **F0 — mide (sólo lectura, S).** Re-mide § El problema con el regex exacto; huellas sha256 de
  `/api/schemas`, `/api/schemas/drill_hole`, `command_schemas()`, `build_tools(True)` y
  `build_tools(False)`. Verifica: números y huellas en la bitácora.
- **F1 — vista persona en el backend (M · `commands`, `api`).** `vista_persona.py` + `pistas.py`
  (con `PESTANAS`, pistas vacías → red de D4), export en `commands/__init__.py`, las dos líneas de
  D2 en `main.py`, `copy.deepcopy` antes de inyectar. Tests `tests/test_vista_persona.py` (vista
  agente intacta; no-mutación; sin versiones en la vista persona; `limpiar_historia` con los casos
  medidos y «220V»/«Vista 3D» intactos; `unidad_de`; `detalle` vacío con una frase; `?vista=otra`
  → 422; `PESTANAS` cubre). Verifica: pytest completo; huellas = F0; trinquete sin tocar números.
- **F2 — las pistas (M · `commands`).** 53 pistas de comando + 6 de campo; `tests/test_pistas.py`
  (D13). Verifica: pytest; la tabla `tipo · rótulo · pista` en la bitácora para que Mario la lea.
- **F3 — piezas de texto y diálogo (M · `ui`).** `ui/src/ui/{Pista,Ayuda,VerDetalle,textoTecnico}.tsx`,
  `ui/src/forms/Campo.tsx`; `SchemaForm.tsx` usa `Campo` y baja (número actualizado en el mismo
  commit); `CommandDialog.tsx` = título + `<Pista>` + `<VerDetalle>` + formulario; `types.ts`
  (D10), `api.ts` (`?vista=persona`), `styles.css`. Verifica: `npm test` y `npm run build`; en
  preview, Taladro con ≤ 40 palabras visibles, la ⓘ abre en el flujo y no ejecuta el comando,
  «Detalle técnico» plegado, sin versiones; Propiedades con ⓘ por campo.
- **F4 — ribbon (S · `ui`).** `ui/src/panels/pestanas.ts` (`pestanasDe(schemas)`, pura) + test;
  `Ribbon.tsx` con pestañas derivadas y D9; íconos para las 3 superficies. Verifica: `npm test`,
  `npm run build`; en preview la pestaña «Superficies» con 3 botones y cada `title` = nombre.
- **F5 — cierre (S · docs).** `ui/CLAUDE.md` sin los dos ⚠️, con dónde vive cada pieza y la regla
  («la pista vive en `commands/pistas.py`, gate `tests/test_pistas.py`; la `description` es del
  agente»); `commands/CLAUDE.md` actualizado; comentario de `textoDeAyuda.test.ts`; conteos de la
  raíz. Huellas D1 = F0; `python tests/test_claude_md.py` dentro de los topes.

## Lo que este plan NO hace

- No cambia las `description` del agente (ni sus 9 versiones del roadmap).
- No renombra los rótulos fuera de vocabulario (4 de comando, 21 de campo): viajan en el payload
  del MCP; va como fix acotado aparte.
- No traduce opciones de enums ni cambia el botón «Ejecutar».
- No limpia Propiedades más allá de lo que hereda de `SchemaForm`.
- No crea `<EstadoVacio>` ni `useConfirmar`.
- No parte `models.py`, `registry.py`, `main.py` ni `SchemaForm.tsx` (sólo achica este último).
- No toca `GET /api/schemas/{type}`, las tools MCP ni su docstring («~77 KB» desactualizado).
- No toca los errores de validación con nombres de parámetros.

## Riesgos

- **La vista persona muta el dict del agente** (un `$defs` compartido): `deepcopy`, test de
  no-mutación y huellas F0 = F1 = F5.
- **La ⓘ ejecuta el comando** (`<button>` dentro de `<form>` es submit): `type="button"` + prueba.
- **La ⓘ dentro de un `<label>` se come el clic**: `Campo` la pone hermana del label.
- **Pistas desactualizadas** (campo renombrado, comando nuevo): el gate rechaza huérfanas y faltantes.
- **`SchemaForm` crece**: F3 extrae `Campo` y baja el número en el mismo commit.
- **El plan de partir `main.py` corre en la misma rama de integración**: el cambio aquí son 2
  líneas; si el endpoint se mueve a un router, van con él.
- **El ribbon sin pestañas hasta que cargan los schemas**: milisegundos; se verifica en preview.
- **Un cambio del estándar de Caronte rompe el parseo de `tuteoNeutro.test.ts`**: falla fuerte.
- **`limpiar_historia` borra algo legítimo**: sólo actúa sobre `title`/`description`, con casos
  «220V» y «Vista 3D».
- **Más densidad visual por las ⓘ**: sólo si la descripción dice algo más que la unidad.

## Bitácora

### F0 — medición (2026-10-03, base `112a4e4`)

Medido con `PYTHONPATH` al `core/` del worktree, sobre `command_schemas()`, con los regex
EXACTOS de los gates de la UI: `HISTORIA` de `textoDeAyuda.test.ts` compilado con `re.ASCII`
(en JS `\b` y `\w` son ASCII; sin el flag, Python los haría Unicode) y `FIN_DE_ORACION` sin
`re.ASCII` (el `\s` de JS es Unicode, como el de Python).

| Qué | Medida F0 | vs. el contrato |
|---|---|---|
| Comandos / categorías | 53 en 8 (modificar 19, biblioteca 9, ensamblaje 8, crear 7, croquis 4, superficies 3, robotica 2, variables 1) | = |
| Descripciones de comando con versión | 9/53, los mismos 9 tipos | = |
| Con backticks / más de una frase / > 120 car. | 25 / 40 / 40 (mediana 246, máx. 1100 `create_take_up`, total 18 679) | = |
| Descripciones de campo (toda `description` del schema salvo la raíz) | 424 apariciones, **115 únicas**; con versión 2 (1 única: `SlideUV`); backticks 16 (7); > 1 frase 21 (9); > 120 car. 24 (12); la más larga 1065 | únicas, versión, backticks, > 120 y máximo =; «528 apariciones» y «> 1 frase 8» no se reproducen (otro criterio de recorrido): se toman los de aquí |
| Pintadas junto al rótulo (simulación de `FieldView` en Python) | **87**, 43 no son una unidad exacta; 64 EMPIEZAN con «mm»/«grados»/«grados o mm» (las que `unidad_de` puede rotular) | = |
| Rótulo visible con versión | sólo «Pestañas ricas (V5.5)» | = |
| Versiones en el payload | 21 en 138 650 bytes | = |
| Vocabulario (textos únicos de títulos + descripciones) | sólido 46, sólidos 8, feature 4 + features 4, fijador 3 + fijadores 4, conjunto 6, joint 4, sub-ensamblaje 4, sketch 2, snapshot 2, borrar 1, borra 1 | ≈ (feature 8 vs 9, sketch 2 vs 3) |
| Primeras frases que ya servirían de pista | **18/53** (1 frase, ≤ 120, sin versión, sin backticks, sin `_`, sin vocabulario prohibido) | = |

**Huellas D1** (sha256 de los bytes; los `json.dumps` sin `indent`, el de `command_schemas()`
con `ensure_ascii=False`):

| Qué lee el agente | sha256 | bytes |
|---|---|---|
| `GET /api/schemas` | `487256b0a958a7eb74b0337f925a466325ea4d372075cc277c0867e6f3aed53b` | 130 475 |
| `GET /api/schemas/drill_hole` | `8a62d1be859f0f1c3620493c9bb0edeb0fc0f49b7eed6dfcf35d2006c36557ba` | 5 731 |
| `command_schemas()` | `0f0db3c8fbde13ee1202b9c6977557b0eaa4ada1635963cfe2a449aac2638feb` | 138 650 |
| `build_tools(True)` | `e5459ba9783de1ae782b1a3c7acc77d0869ebf58f50bbbc9dfbc3140240f6d92` | 156 869 |
| `build_tools(False)` | `c6c2dad2b0082e92e01c859b1dc706ba919e72c94eefce3a996f7b35bc14e863` | 156 579 |

### F1 — vista persona en el backend

- `core/apolo/commands/pistas.py` (sólo datos): `PESTANAS` con las 8 categorías (valor
  `{"orden", "rotulo"}` o `None` para `variables`), `PISTAS` y `PISTAS_CAMPO` vacíos (la red de
  D4 cubre hasta F2). `core/apolo/commands/vista_persona.py` (lógica): `command_schemas_persona()`,
  `limpiar_historia()`, `frases()`, `primera_frase()`, `unidad_de()`. Export en
  `commands/__init__.py`. 35 + 163 líneas.
- Cada entrada persona: `type, title, category, kind, pestana, pista, detalle, schema`, armada
  sobre `copy.deepcopy` de la del agente. El schema pierde la `description` raíz; todo
  `title`/`description` a cualquier profundidad pasa por `limpiar_historia`; cada campo cuya
  descripción EMPIEZA con «grados o mm»/«mm»/«grados» gana `x-unidad` (193 «mm», 73 «grados»,
  2 «grados o mm», contando los x/y/z de posición y rotación); `x-pista` donde `PISTAS_CAMPO`
  lo pide, en el modelo raíz o en un sub-modelo de `$defs`.
- `GET /api/schemas?vista=persona` → 53 entradas, 0 versiones del roadmap en todo el payload
  (130 774 bytes con el mismo `json.dumps` que dio 138 650 en el agente). `?vista=otra` → 422.
- Tests: `tests/test_vista_persona.py`, 44 casos (vista agente intacta por HTTP y en memoria,
  no-mutación, entrada sobre copia, 422, `/api/schemas/{type}` igual, claves de la entrada, sin
  versiones, rótulo «Pestañas ricas» limpio, detalle vacío con una frase, párrafos y viñetas,
  red de la primera frase, pista explícita gana, `x-unidad`, `x-pista` en raíz y en sub-modelo,
  `PESTANAS` cubre, 14 casos de `limpiar_historia` con «220V», «Vista 3D» y `V["largo"]`
  intactos, 13 de `unidad_de`, los casos de `frases` del gate de la UI).
- Huellas D1 después de F1: **las 5 idénticas a F0**. Trinquete de tamaño verde (`main.py`
  sigue en 4913).

**Desvíos del contrato, con su porqué:**
- `main.py`: cambian **tres** líneas, no dos (el import de `command_schemas_persona` + la firma
  + el `return`); 0 netas, como pide D12. Sin el import habría que sumar una línea o importar
  dentro de la función.
- La entrada persona **no lleva `description`**: D10 la quita del tipo de la UI y el texto ya
  viaja limpio en `detalle`; mandarla igual invitaba a volver a pintarla.
- `limpiar_historia` además de quitar versiones **normaliza** la docstring a texto: une las
  líneas cortadas por el ancho del código, conserva párrafos y viñetas «- …» (D6 pide el
  detalle «con viñetas»). Una línea que vuelve a la sangría del guion cierra la viñeta: sin
  esa regla, «Editar cualquier parámetro regenera el conjunto entero.» quedaba pegada a la
  última viñeta de `create_take_up`.
- La limpieza de versiones sólo se aplica si el texto trae una (el retoque de espacios
  alrededor del corte no toca textos sin historia).
