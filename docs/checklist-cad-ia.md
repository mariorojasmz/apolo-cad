# Checklist — CAD 3D agente-nativo (MCP)

> Versión revisada del checklist propuesto por ChatGPT (2026-07-01), auditada contra el
> estado REAL de Apolo. Cada ítem se marca ✅ (hecho), 🟡 (parcial) o ❌ (falta), con la
> evidencia en el código. Los ❌/🟡 relevantes bajan a la sección "Brechas priorizadas".

## Veredicto sobre el checklist original

- **La dirección es correcta**: API-first, percepción visual para el agente, y sobre todo
  la recomendación final (modelo = grafo de conocimiento de ingeniería, no solo geometría)
  coinciden con los principios de arquitectura de Apolo.
- **Pero fue escrito a ciegas**: ~80 % de lo que propone **ya está implementado** en Apolo
  (55 tools MCP, 43 comandos, catálogo de 217 refs, validación estructural, render VTK con
  cámara libre). Su valor real no es como plan, sino como **auditoría de brechas**.
- **Mezcla dos cosas distintas**: "qué tan buena es la IA hoy" (columna irrelevante para
  decidir qué construir) con "qué debe exponer la plataforma" (lo único accionable). Esta
  versión elimina la primera y conserva la segunda.

---

## 1 · Modelado

| Capacidad | Estado | Evidencia en Apolo |
|---|---|---|
| Piezas simples y paramétricas | ✅ | Registry schema-driven, `=expresiones`, variables de proyecto |
| Editar dimensiones | ✅ | `edit_command` (PATCH merge), `edit_batch` atómico |
| Ensamblajes | ✅ | Mates por cara, juntas FK, `add_constraint` N-GDL, riel lazo cerrado |
| Reemplazar componentes | 🟡 | Cirugía por `commands/remove` + reinsertar; no hay "replace" de un paso que conserve juntas |
| Operaciones (extrude/corte/fillet/chaflán) | ✅ | + shell, revolve, sweep/loft/hélice, chapa con desplegado, joinery |
| Patrones y matrices | ✅ | `pattern_linear/circular/group`, `count` por expresión |
| Planos 2D automáticos | ✅ | Sistema A–G completo: auto-acotado, juego de planos, despiece, explosionada, manual de ensamblaje |
| Import/export STEP | ✅ | `import_step` (split), `export_step` |
| Export STL / OBJ / glTF | ❌ | Solo STEP expuesto; la teselación ya existe (render/física) → export de malla es barato |
| Export IGES | ❌ | OCCT lo trae; baja prioridad (STEP cubre interop) |

## 2 · Ingeniería

| Capacidad | Estado | Evidencia |
|---|---|---|
| Tornillería comercial | ✅ | DIN 933/912, tirafondos, familias `pernos`/`tuercas` |
| Rodamientos | ✅ | ISO 15 completo (41 refs) + chumaceras UCP/UCF/UCFL |
| Motorreductores | ✅ | Familia NMRV (bores verificados contra Motovario) + helicoidal en línea |
| Relaciones de transmisión | 🟡 | `engineering_check` valida velocidad/par de la faja; el análisis de capacidad de una transmisión (fajas en V, cadena) lo hace el agente a mano — no hay regla dedicada |
| Peso del ensamblaje | ✅ | `cut_list_totals`, `scene_weight_kg`, BOM con pesos, cajetín auto |
| Centro de gravedad / masa por pieza | ❌ | El COM existe interno (física/estabilidad) pero **no hay tool de consulta** (`get_mass_properties`) — brecha real y barata |
| Detección de interferencias | ✅ | `check_interference` + `interpenetration_report` en pose |
| Medición | ✅ | `measure` (gap OCCT), `near`, cota sobre el render |
| Piezas duplicadas | ❌ | No hay detector de geometría repetida no-instanciada |
| Equivalentes comerciales | ❌ | No hay "esta pieza a medida ≈ esta ref de catálogo" |

## 3 · Optimización (la categoría más floja del original — y la menos urgente)

| Capacidad | Estado | Nota |
|---|---|---|
| Optimizar material / merma | 🟡 | `nest_1d/2d` + `waste_*` ya optimizan corte; no hay costo monetario |
| Costos | ❌ | Falta `cost`/`price` en specs del catálogo + $/kg por material — prerequisito de casi todo lo demás de esta sección |
| Reducir piezas / detectar sobreingeniería | ❌ | Sin costo ni FEA es juicio del agente; el decálogo de `design/guidelines.py` ya lo empuja cualitativamente |
| Sugerir materiales | 🟡 | `materials.py` tiene densidad/E/σy; la sugerencia es criterio del agente |

## 4 · Ingeniería avanzada

| Capacidad | Estado | Nota |
|---|---|---|
| Chequeos analíticos (viga, eje, par, velocidad) | ✅ | `structural.py` + `engineering_check` (10 reglas en la faja) — esto cubre ~80 % de las decisiones por ~5 % del coste del FEA |
| FEA | ❌ deliberado | Aplazado por decisión de negocio (correcto; el original le da prioridad "Media" — debería ser "cuando el negocio lo pida") |
| Física de cuerpos rígidos | ✅ | MuJoCo: `gravity_test` (cascos convexos), `drop_test` |
| Tolerancias automáticas | 🟡 | `linear_dim` soporta ±tol y GD&T ligero en planos; no hay motor que las DECIDA |

## 5 · Funciones MCP de introspección (el original propone 28; Apolo tiene ~26)

Ya cubiertas: árbol/escena (`get_scene`, brief compacto con diff), parámetros
(`get_command`, `get_command_schemas`), topología caras/aristas (`get_topology`),
volumen/bbox, restricciones (`get_mates`, `get_kinematics`, `get_connections`),
historial (`list_revisions`, log de comandos), undo/redo, crear/borrar/duplicar/agrupar,
colisiones, medición, expresiones (`resolve_expression`), dry-run (`test_script`,
`test_sketch`), preview reversible, notas de agente.

Faltantes reales:

| Función | Prioridad | Nota |
|---|---|---|
| `get_mass_properties(id)` → masa, COM, inercia, área superficial | **Alta** | Todo existe interno (`_link_physics`, cutlist); solo falta exponerlo |
| Query filtrada (`find(material=…, tipo=…, nombre~…)`) | Media | Hoy el agente trae `get_scene` y filtra; a 500+ piezas una query servidor ahorra contexto |
| Renombrar como tool dedicada | Baja | Ya se puede vía `edit_command` |

## 6 · Percepción visual — **COMPLETO, y más allá del checklist**

Todo lo que pide el original existe: 4 vistas preset + **cámara libre**
(azimuth/elevation/roll/pan), isolate, highlight, xray, sección, zoom/fit, labels,
cota sobre el render, bordes nítidos, `pick_point` píxel→pieza exacto. Lo único que
falta del original:

| Función | Prioridad | Nota |
|---|---|---|
| Vista explosionada en el render 3D | Media | Ya existe en planos 2D (`drawing/explode.py`) y en el manual de ensamblaje; portar `explode_scene` a `render_view(explode=…)` es reuso directo |

## 7 · El grafo de conocimiento de ingeniería (la recomendación buena del original)

Apolo **ya es** en gran parte ese grafo — más de lo que el autor del checklist imagina:

| Pregunta del checklist | ¿Respondible hoy? | Cómo |
|---|---|---|
| ¿Qué piezas soportan la carga? | ✅ | Grafo de soporte dirigido (`detect_structure`) + `gravity_test` |
| ¿Qué piezas están soldadas/atornilladas? | ✅ | `fasten` con tipo (perno/soldadura/pegado/contacto) es dato de primera clase |
| ¿Qué piezas giran / se desplazan? | ✅ | Juntas revolutas/prismáticas + estudios de movimiento con nombre |
| ¿Qué piezas son comerciales vs fabricadas? | ✅ | BOM distingue catálogo (con norma) vs a-medida |
| ¿En qué orden se desmonta? | 🟡 | Manual de ensamblaje deriva secuencia del log (orden de modelado, no dependencia real) |
| ¿Qué pieza es la más costosa? | ❌ | Requiere costo en catálogo/materiales |
| ¿Qué requiere lubricación/mantenimiento? | ❌ | Requiere specs de mantenimiento en el catálogo |
| ¿Cuál es la FUNCIÓN de esta pieza? | 🟡 | Hoy es convención de nombre-por-ROL + heurística del árbol; no es propiedad estructurada consultable |

---

## Brechas priorizadas (lo único accionable del checklist)

1. ~~**`get_mass_properties`**~~ ✅ HECHO (2026-07-01, Frente A): tool + endpoint
   `/api/mass-properties` (masa/COG/bbox por pieza y conjunto), y el chequeo de vuelco
   (COG vs huella de apoyo) quedó como regla de `engineering_check`. También cerrados en
   el Frente A: memoria de cálculo PDF, requisitos de proyecto, batería analítica
   (pernos/soldaduras/L10/pandeo/banda-cama). Ver CLAUDE.md "FRENTE A".
2. ~~**Costo en el catálogo**~~ ✅ HECHO (2026-07-01, Frente B): `library/costing.py`
   (BOM costeado con fuente por fila), `COST_PER_KG_USD` en materials.py, `cost`
   referencial en familias clave del YAML, `get_costing` ("pieza más costosa") y
   cotización PDF `quotation` (margen/impuesto/precio de venta). Ver CLAUDE.md "FRENTE B".
3. **Campo `funcion`/`rol` estructurado por pieza** — hoy el rol vive en el nombre
   (convención) y en heurísticas regex del árbol. Promoverlo a propiedad consultable
   (como `set_material`) cierra la recomendación central del checklist con poco código.
4. **Export STL/glTF** — la teselación ya existe; abre impresión 3D y visores externos.
5. **Explosionada en render 3D** — reuso de `explode_scene` en `render_view`.
6. **Secuencia de desmontaje por dependencia** — reordenar el manual de ensamblaje por el
   grafo de soporte dirigido (ya existe) en vez del orden del log. Follow-up ya anotado.
7. **Query filtrada de escena** — solo cuando los modelos pasen de ~300 piezas.

## Qué NO hacer (donde el checklist original desorienta)

- **No perseguir la sección "Optimización" como bloque**: sin costo (brecha 2) es humo;
  con costo, la mitad sale gratis (el agente razona sobre el BOM costeado).
- **No subir la prioridad del FEA** ("Media" en el original): el analítico barato ya
  cubre las decisiones del vertical; FEA solo cuando el negocio lo pida (decisión vigente).
- **No añadir una tool MCP por cada fila**: el diseño thin (run_command/edit_command
  cubren TODO el registro) ya demostró ser correcto en la auditoría de 2026-06-15; las
  brechas son de LECTURA/metadatos, no de escritura.
- **No tratar "estado actual de la IA" como criterio**: lo que importa es qué expone la
  plataforma; la capacidad del modelo mejora sola con cada generación.
