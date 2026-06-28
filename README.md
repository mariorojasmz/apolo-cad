# Genix Apolo CAD

CAD paramétrico para maquinaria industrial y robótica con **diseño asistido por IA** como núcleo del producto.

## Arquitectura (Fases 1–6)

```
ui/        React + TypeScript + three.js  ─┐
                                           ├─►  core/apolo/api    FastAPI (REST + WebSocket)
core/apolo/agent   Agente Claude (tool use)┘            │
                                                        ▼
                                          core/apolo/doc        Documento = log de comandos
                                          core/apolo/commands   Registro (schemas pydantic)
                                          core/apolo/kernel     build123d / OpenCascade
```

Principios:
- **API-first / IA-nativa**: toda operación es un comando contra el kernel headless. La UI y el agente IA son dos clientes de la misma API.
- **El documento es el log de comandos** (event-sourcing): undo/redo, edición paramétrica de cualquier comando pasado y persistencia salen gratis.
- **UI dirigida por esquemas**: la toolbar, los diálogos y el panel de propiedades se generan del JSON Schema de cada comando. Añadir un comando al registro lo hace aparecer en la UI **y** en las tools del agente sin tocar nada más.
- **La IA nunca genera geometría**: propone lotes de comandos (tarjetas Aceptar/Rechazar) que el kernel ejecuta de forma determinista. Las referencias entre acciones de un lote usan `$k`.

## Sistema paramétrico (Fase 2)

- **Variables de proyecto** (`ƒx Variables` en la toolbar): cada variable es un comando `set_variable` en la cabecera del log. Cambiar una variable regenera todo el modelo.
- **Expresiones en cualquier campo numérico**: escribe `=L/2`, `=ancho - 2*perfil`, etc. Operadores `+ - * / ** %`, paréntesis, `pi` y funciones `sqrt sin cos tan abs min max floor ceil round` (trigonometría en grados). Evaluador AST con lista blanca: sin `eval`.
- **Vista previa en vivo** en Propiedades: los cambios se aplican con debounce y toda la sesión de ajustes ocupa **un solo paso de deshacer** (edición coalescente).
- **El agente IA diseña paramétrico**: define variables en sus lotes y referencia el resto de medidas con expresiones.
- **Viewport**: gizmo de mover/rotar (emite comandos `transform`), selección múltiple (Ctrl+clic y Shift+arrastrar para recuadro) y plano de sección X/Y/Z con deslizador.

## Biblioteca, ensamblajes y BOM (Fase 3)

- **Catálogo de componentes** (`📚 Catálogo` en la toolbar, `core/apolo/library/catalog.py`): perfiles, rodillos, motorreductores, patas, guardas y sensores, con geometría paramétrica, especificaciones y pesos. Filtros por categoría y búsqueda por specs. Los componentes cortables aceptan longitud a medida (también `=expresión`).
- **`create_conveyor` — plantilla de transportador como super-comando**: una sola entrada del historial genera bastidor (largueros 40x80), rodillos, 4 patas regulables, arriostrado y motor opcional. Seleccionar cualquier pieza muestra el formulario del transportador completo: cambiar largo/paso/rodillo regenera todo. Acepta expresiones (`largo: "=L"`).
- **`attach` — mates por anclas**: posiciona un sólido haciendo coincidir su ancla (`centro/base/tope/min_x/max_x/min_y/max_y`, calculadas de la caja envolvente) con la del destino, con desfase opcional. Cubre mates de coincidencia y distancia; la alineación de ejes por rotación llegará con la cinemática (F6).
- **BOM** (botón `BOM` en la barra superior): lista de materiales agrupada por referencia + longitud de corte con pesos unitarios y totales; export CSV (`/api/bom.csv`).
- **El agente IA usa la biblioteca**: tool `get_catalog`, prefiere componentes de catálogo, y para transportadores usa `create_conveyor` eligiendo rodillo por capacidad y paso por tamaño de paquete.

## Agente validador (Fase 4)

- **IA Nivel 2 — generación de código**: comando `run_script` que ejecuta scripts build123d en un **sandbox** (subproceso aislado con timeout de 60 s y caché por hash, `core/apolo/sandbox.py`); el script ve `V` (las variables del proyecto). El agente **prueba su código con la tool `test_script` antes de proponerlo** y la tarjeta de acción muestra el código completo para tu revisión — esa revisión humana es la frontera de seguridad.
- **IA Nivel 3 — bucle de validación**: tools `engineering_check` (reglas del vertical en `core/apolo/library/rules.py`: apoyo ≥3 rodillos, kg/rodillo vs capacidad, ancho útil, potencia de motor con recomendación de catálogo), `check_interference` (booleanas OCCT con prefiltro bbox) y `render_view` (**visión**: el agente mira un render PNG de la escena). El agente valida un transportador ANTES de proponerlo y verifica el montaje después de que aceptes.
- **Panel Validar** en la UI: datos del paquete → interferencias + reglas con recomendaciones.

## Planos 2D (Fase 5)

- Pestaña **Planos**: lámina generada al vuelo desde el modelo actual mediante **eliminación de líneas ocultas** (HLR de OpenCascade). Siempre sincronizada con la escena — no hay planos desfasados.
- Disposición en **primer diedro** (alzado, planta bajo el alzado, perfil a la derecha) + vista isométrica; **escala normalizada** (1:1…1:200) común a las vistas ortográficas; **cotas generales** por vista; marco y **cajetín** con proyecto, fecha, escala y lámina.
- Opciones: A3/A4 y líneas ocultas (a trazos). Export **SVG**, **DXF** (capas VISIBLE/OCULTA/COTAS/MARCO, importable en cualquier CAD) y **PDF** a tamaño real de papel (`core/apolo/drawing/`).

## Planos pro (Fase 12)

- **Callouts de taladros automáticos**: la proyección detecta los círculos de cada vista (centro y radio exactos del HLR), los agrupa por diámetro y rotula «4×Ø9», «Ø24»… con directriz. Los que quedarían ilegibles a la escala elegida se omiten solos.
- **CORTE A-A** (`section=true`): media vista seccionada por el plano central YZ con las **caras de corte rellenas** (sección plana exacta de OCCT, agujeros como anillos interiores) y la traza del plano con flechas y letras «A» en la planta. En DXF las caras van a la capa CORTE.
- **Globos + lista de materiales en lámina** (`bom=true`): tabla N.º/Ref/Descripción/Cant en el cuadrante del perfil y globos numerados sobre la planta con directriz a la pieza representante de cada fila.
- **Cotas por sólido** (`dims=id1,id2`): selecciona piezas en el árbol y acótalas individualmente sobre la planta (hasta 3, apiladas, con su nombre).
- Todo combinable desde la pestaña **Planos** (checkboxes) o por query string en `/api/drawing.svg|dxf|pdf` — el agente y el MCP generan las mismas láminas que la UI.

## Sketcher restringido (Fase 11)

- **Croquis 2D con solver de restricciones** (`core/apolo/kernel/sketch_solver.py`, mínimos cuadrados con scipy — sin dependencias nativas frágiles): dibuja **a ojo**, restringe (horizontal, vertical, longitud, distancia, coincidente, paralela, perpendicular, ángulo, radio, punto-en-línea, igual longitud, fijar) y el solver hace las posiciones **exactas** (tolerancia 1 µm, doble pasada). Los croquis imposibles fallan con diagnóstico de las restricciones en conflicto.
- **Comandos `sketch_extrude` y `sketch_revolve`**: el croquis vive en los parámetros del comando → edición paramétrica del perfil, undo y persistencia gratis. Líneas + arcos en lazo cerrado; círculos como agujeros. **Las cotas aceptan `=expresiones`** — cambiar una variable redimensiona el croquis y regenera el sólido.
- **Editor 2D** (`✏ Croquis` en la toolbar): herramientas punto/línea/círculo/selección, botones de restricción contextuales, «⚙ Resolver» con snap visual y diagnóstico, extruir/revolucionar, y «✏ Editar croquis…» desde Propiedades para piezas existentes.
- **El agente croquiza validando**: tool `test_sketch` (resuelve sin tocar el documento e itera sobre el diagnóstico antes de proponer).

## IA-first flagship (Fase 10)

- **Servidor MCP** (`core/apolo/mcp_server.py`): Apolo como tools estándar MCP — cualquier agente (Claude Code, Claude Desktop…) puede diseñar: 18 tools (escena, schemas, catálogo, comandos, lotes `$k`, variables, validaciones, **render con imagen para visión**, proyectos, BOM, STEP a archivo). Es un cliente fino de la API HTTP: las mismas operaciones que la UI, y los cambios aparecen **en vivo en el navegador**. El repo incluye `.mcp.json`; en Claude Code basta abrir el proyecto (requiere el servidor corriendo).
- **⚡ Modo auto** en el chat: el agente ejecuta los lotes directamente, **verifica** (interferencias, reglas, render) y **corrige** (`undo_last` + nuevo lote) sin pedir aprobación paso a paso. Opt-in por conmutador; todo queda en el historial y es deshacible.
- **Memoria de proyecto**: el agente guarda notas persistentes (`save_note`) en el documento — decisiones y supuestos que reaparecen en futuras sesiones.

## Producto (Fase 9)

- **Pantalla Inicio** (`⌂ Apolo CAD`): proyectos en SQLite con **autoguardado en cada operación** (el documento es el log de comandos: pesa KBs), plantillas (vacío / transportador / brazo), abrir/duplicar/borrar, y doble clic en el nombre para renombrar. Al arrancar se abre el último proyecto.
- **Revisiones**: instantáneas con nota, restaurables ("antes de cambiar el paso…").
- **Configuraciones (variantes)**: en `ƒx Variables`, guarda los valores actuales como variante ("2 metros", "3 metros") y aplícala con un clic — regenera el modelo entero en un solo paso de deshacer. La tabla de variantes de Fusion, sobre nuestro sistema de variables.
- **Medir** (`📏` en el viewport): distancia y ΔX/ΔY/ΔZ entre dos puntos clicados.
- **Apariencia**: color por pieza desde Propiedades (persistido en el `.apolo`).
- Base de datos en `data/apolo.db` (configurable con `APOLO_DB`).

## Ensamblajes reales (Fase 8)

- **Instancias**: las piezas repetidas comparten una geometría canónica (definición) y solo difieren en su matriz 4×4 (`core/apolo/kernel/matrix.py`). Un transportador de 47 piezas viaja como 5 definiciones (~64 KB en vez de cientos); el viewport comparte `BufferGeometry` entre ocurrencias. Las operaciones que alteran la geometría (fillet, taladro, booleana) convierten la pieza en única automáticamente.
- **Mates con orientación**: `attach` ahora también orienta (`align_my`/`align_to` gira la pieza sobre su centro para alinear ejes) antes de llevar ancla contra ancla.
- **Sub-ensamblajes en el árbol**: las piezas de un mismo comando (transportador, brazo, patrón) se agrupan en nodos colapsables; clic en la cabecera selecciona el conjunto.
- **Colisión en pose**: las interferencias se pueden comprobar con el mecanismo posado (`joint_values` en `/api/checks`, botón «💥 Colisión en pose» en Cinemática, y el agente vía `check_interference`). Los contactos padre-hijo de las juntas se excluyen (son por diseño), así el informe solo muestra colisiones reales.

## Modelado completo + import (Fase 7)

- **Selectores declarativos de aristas/caras** (`core/apolo/kernel/selectors.py`): nunca índices (adiós al *topological naming problem* clásico). Modos: todas, por dirección, por cara del bbox, por longitud, o "cerca de un punto" — que es lo que genera el clic 📍 en el viewport. El agente usa los semánticos ("aristas verticales" = dirección z); tú, el picking.
- **Operaciones nuevas**: redondeo (fillet), chaflán, vaciado (shell), taladro con caladrillo (sin referencias de cara: punto + eje + Ø, pasante o ciego), patrón circular, espejo, **revolución** (perfil [r,z]) y **polígono extruido** — piezas de revolución y prismáticas arbitrarias sin tocar el sandbox.
- **Import STEP** (botón en la barra superior): el archivo queda embebido en el documento (`.apolo` v2 con `attachments/`, retrocompatible) para que el log siga siendo reproducible. Opción de separar cada sólido en una pieza.
- Errores OCCT capturados con consejo ("radio imposible: prueba menor o menos aristas").

## Robótica (Fase 6)

- **Juntas cinemáticas como comandos** (`add_joint`): fija, giratoria, continua o prismática entre dos sólidos (padre → hijo), con validación de árbol (un padre por hijo, sin ciclos) e **integridad referencial**: no puedes borrar un sólido con juntas sin quitar antes la junta.
- **`create_robot_arm`**: brazo articulado de 4 ejes (giro de base, hombro, codo, muñeca) con sus juntas ya encadenadas, parametrizado por alcance.
- **Panel Cinemática**: deslizadores por junta que mueven el modelo en el viewport (cinemática directa client-side, solo previsualización — "Pose cero" restaura; el gizmo se desactiva mientras hay pose).
- **Export URDF y SDF** (`core/apolo/robotics/`): ZIP con `robot.urdf`/`model.sdf` + mallas STL por eslabón, masas e inercias estimadas, límites en radianes/metros. Compatible ROS/Gazebo/Isaac Sim.
- Pospuesto de la F6 original: el **sketcher PlaneGCS** (el vertical no lo ha exigido aún) y el **empaquetado Tauri** (requiere toolchain Rust; mejor como paso de distribución dedicado).

## Requisitos

- Python 3.11–3.13 (con wheels binarios de OCP/build123d)
- Node.js 18+
- Clave del API de Anthropic para el asistente IA (`ANTHROPIC_API_KEY`)

## Instalación

```powershell
# Núcleo Python
python -m venv .venv
.venv\Scripts\python -m pip install -e core
.venv\Scripts\python -m pip install pytest httpx   # para los tests

# UI
cd ui
npm install
npm run build    # genera ui/dist, que sirve el propio servidor
```

## Arranque

```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-..."   # opcional pero recomendado (asistente IA)
.venv\Scripts\python -m uvicorn apolo.api.main:app --port 8000
```

Abrir <http://localhost:8000>. Para desarrollo de la UI con recarga en vivo: `cd ui; npm run dev` (proxy a :8000) y abrir <http://localhost:5173>.

Variables opcionales: `APOLO_MODEL` (por defecto `claude-opus-4-8`).

## Prueba rápida

En el chat del asistente: *«crea un marco de perfil 40x40 de 2000×1000 mm»* → revisar la propuesta → **Aceptar todo** → el marco aparece en el viewport. Selecciona un larguero, cambia el largo en Propiedades y **Aplicar y regenerar**. **Exportar STEP** para abrirlo en cualquier CAD.

## Tests

```powershell
.venv\Scripts\python -m pytest tests
```

Cubren: kernel (volúmenes/bbox de cada comando), documento (undo/redo, edición paramétrica con regeneración, round-trip `.apolo`), expresiones y variables, biblioteca/BOM/transportador, sandbox y validaciones (reglas, interferencias, render), API completa y agente (tools, validación, SSE, degradación sin clave).

## Formato `.apolo`

ZIP con `manifest.json` (versión, nombre, unidades, visibilidad) y `commands.json` (el log completo). Abrir un archivo = reproducir su log.

## Hoja de ruta

- **F2** ✅ Variables de proyecto y expresiones (`=L/2`), vista previa en vivo, gizmo, selección por recuadro, secciones.
- **F3** ✅ Biblioteca de componentes del vertical, mates por anclas (`attach`), BOM con export CSV, transportador paramétrico (`create_conveyor`).
- **F4** ✅ Agente validador: sandbox `run_script` + `test_script`, reglas de ingeniería, interferencias y `render_view` con visión.
- **F5** ✅ Planos 2D: proyecciones HLR, lámina con escala normalizada, cotas y cajetín; export SVG/DXF/PDF.
- **F6** ✅ Robótica: juntas, brazo de 4 ejes, panel Cinemática y export URDF/SDF.
- **F7** ✅ Modelado completo: selectores de aristas/caras, fillet/chaflán/shell/taladro/patrones/espejo/revolución/polígono, import STEP con `.apolo` v2.
- **F8** ✅ Ensamblajes: instancias con definiciones compartidas, mates con orientación, árbol agrupado, colisión en pose.
- **F9** ✅ Producto: Inicio multiproyecto con autoguardado, revisiones, configuraciones, Medir, colores.
- **F10** ✅ IA-first: servidor MCP (18 tools, render con visión, `.mcp.json`), modo auto del chat, memoria de proyecto.
- **F11** ✅ Sketcher restringido: solver propio (scipy), croquis como comandos con cotas paramétricas, editor 2D, `test_sketch` del agente.
- **F12** ✅ Planos pro: callouts Ø automáticos, CORTE A-A con caras rellenas, globos + BOM en lámina, cotas por sólido.

**Camino a paridad-Fusion (V2): COMPLETADO.** Fuera de alcance deliberado: CAM, FEA real, PCB, nube multiusuario. Backlog opcional: empaquetado Tauri, plantillas AGV, sweep/loft desde croquis.
