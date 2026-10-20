---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: Sólo el plan; nada construido. Espera saldo de tokens y depende de V8.2 F2 (endpoint + tool `simulate`), hoy pausado
descripcion: Prendes la máquina y la ves andar en 3D como en la realidad: rodillos y tambores girando por su motor, la faja con su forma real corriendo, las cadenas eslabón por eslabón y las cajas viajando con física
---

# Ver la máquina andar como en la realidad

## Estado y origen

Mario (2026-10-10): «Quiero llevar a Apolo a un siguiente nivel 3D… quiero una emulación real,
por ejemplo ver fajas reales, no un pedazo rígido doblado, quiero que una máquina al prenderse se
mueva cada pieza según la física, quiero verlo en 3D en buen diseño o lo más parecido a la
realidad posible… podemos reemplazar el motor 3D actual y crear uno mejor». Se le recomendó NO
reemplazar el motor ni escribir una física propia, y poner el esfuerzo en el realismo visual y en
terminar V8.2; respondió «sí» al plan.

## El problema / lo que hay hoy

- **Física**: [V8.2](V8.2-maquina-se-mueve.md) F1 está en `main` (`physics/dinamica*.py`,
  `physics/banda.py`): MuJoCo con juntas, motores, banda como superficie que arrastra, productos y
  sensores, en lote. Faltan F2 (endpoint + tool `simulate`) y F3; pausado el 2026-10-09.
- **Visor**: three.js ya usa PBR (`ui/src/viewport/materials.ts`, `MeshStandardMaterial`), luz de
  ambiente sin assets (`environment.ts`, `RoomEnvironment`), tono ACES y sombras suaves
  (`scene-setup.ts:19-22`). Lo que falta para «parecer real» no es el motor: materiales por tipo
  (todo es un color + metalness/roughness genérico), sombra de contacto con el piso, y que la
  máquina SE MUEVA.
- **Dos renderizadores**: el visor (three.js) y el video de la tienda
  ([publicacion-tienda](publicacion-tienda.md), VTK en `kernel/render_vivo.py`) no comparten
  materiales: hoy se verían distintos.
- La faja se dibuja como un sólido rígido; las cadenas, como sólidos del CAD que no avanzan.

## Lo que se revisó antes de escribir esto

- Las herramientas del mercado (NVIDIA Omniverse/Isaac Sim, Rockwell Emulate3D, Siemens Process
  Simulate, Visual Components) modelan la faja transportadora como SUPERFICIE CON VELOCIDAD más
  una animación: la banda flexible con física completa es lenta y casi nunca cambia el resultado.
  Es la misma decisión que V8.2 D5.
- MuJoCo 3 trae cuerpos flexibles (`flexcomp`): la banda flexible real queda disponible para un
  estudio puntual (comba, tracking) sin cambiar de motor.

## Decisiones (para vetar)

- **D1. No hay motor de física propio**: MuJoCo (V8.2) calcula. La ventaja de Apolo es juntar
  CAD + física + tablero + PLC + IA, no el motor.
- **D2. No se reemplaza three.js**: lo que da realismo (materiales, luz, sombras) se logra con él;
  Unreal/Unity/Omniverse romperían «corre en el navegador, liviano, MIT». WebGPU se evalúa cuando
  three.js lo dé estable, sin cambiar de motor.
- **D3. Física donde cambia el resultado, animación donde sólo se ve**: cajas, torque, patinaje y
  sensores = física (V8.2). La piel de la faja, las cadenas, los engranajes y los rodillos que
  giran por su eje = animación CINEMÁTICA que se deriva del resultado físico (velocidad de la
  banda, ángulo de cada junta), así nunca contradice a la física.
- **D4. Calcular ≠ mirar**: el servidor simula y entrega una serie de tiempo (poses por cuerpo a
  50 Hz + velocidad de bandas y cadenas); el visor la reproduce a 60 fps interpolando, con línea
  de tiempo (play, pausa, velocidad, saltar). El resultado no entra al `.apolo` (se regenera) y
  se cachea por firma del documento + escenario.
- **D5. Una tabla de materiales para los dos renderizadores**: material/rol → parámetros PBR
  (acero pintado con el color del usuario, galvanizado, inoxidable cepillado, aluminio, caucho,
  PVC de banda, cadena pavonada, bronce). Fuente única en `library`, la leen el visor y VTK. Los
  mapas de relieve son PROCEDURALES (sin descargar texturas: CSP y licencias).
- **D6. Faja con su forma real**: la ruta sale de la geometría (tambores, rodillos, tensor) con
  envolvente en cada tambor y comba entre apoyos según la tensión de V8.2; la textura corre a la
  velocidad de la banda. Cadenas: eslabones instanciados (`InstancedMesh`) a lo largo de su lazo
  (`library/transmision`), avanzando con el ángulo del piñón.
- **D7. Presupuesto**: 60 fps con la piloto (≈ 200 piezas, 21 cadenas ≈ 1000 eslabones) en una
  laptop media; se mide en F0 y se respeta en cada fase.
- **D8. Módulos nuevos en `ui/src/viewport/`** (reproductor, faja, cadena): `Viewport.tsx` no
  crece (trinquete de tamaño).

## Alternativas descartadas

- Motor 3D propio o motor de juegos (Unreal/Unity con pixel streaming): años de trabajo o
  servidor con GPU por usuario; rompe la distribución por PyPI y el navegador.
- Banda flexible con física completa siempre encendida: lenta y sin cambio en lo que se decide.
- MuJoCo en el navegador (WASM) desde el inicio: atractivo para «empujar una caja con el mouse»,
  pero duplica la física; queda como opción después de D4.

## Fases

- **F0 (S, sólo lectura)**: capturas de la piloto (proyecto 2) en el visor y en VTK; medir fps
  con 1000 eslabones instanciados en un prototipo del scratchpad; listar qué juntas y motores le
  faltan a la piloto para que V8.2 la mueva (hoy no tiene juntas declaradas).
- **F1 (M, `library` + `ui` + `kernel`)**: tabla de materiales D5 usada por los dos
  renderizadores; piso con sombra de contacto.
- **F2 (M, `api` + `ui`)**: reproductor D4 sobre el resultado de `simulate` (requiere V8.2 F2).
- **F3 (M, `library` + `ui`)**: faja con forma real y cadenas que avanzan (D6).
- **F4 (S, `publicacion`)**: el video de la tienda cierra con «la máquina andando» (mismo
  resultado y mismos materiales, renderizado por VTK).
- **F5 (S, verificación)**: clip de 20 s de la piloto andando, cajas incluidas; lo juzga Mario.

## Lo que este plan NO hace

- Datos vivos sobre el 3D (cables, pilotos, tableros): es [V8](V8-maquina-viva.md) V8.4.
- Deformación de la estructura (eso es FEA estático, ya existe) ni fluidos.

## Riesgos

- Que el visor y VTK se vean distintos → D5 + una captura comparada en el test de F1.
- Que la animación contradiga a la física (caja que avanza más rápido que la banda) → D3: todo
  lo animado se deriva de la serie de tiempo física.
- Rendimiento con máquinas grandes → instancias, nivel de detalle y D7 como gate.

## Bitácora

### F1 (2026-10-19)

Hecha la tabla D5; el piso con sombra de contacto queda PENDIENTE (ver abajo).

- **Fuente única**: `core/apolo/library/apariencia.py` (`ACABADOS`, 17 acabados PBR
  metálico-rugoso: acero pintado, mecanizado, pavonado —la «cadena pavonada» de D5—, galvanizado,
  zincado, inox cepillado, cromado, aluminio, hierro fundido, bronce, latón, niquelado, caucho,
  PVC de banda, madera, vidrio, cartón). `acabado_de` decide por el material resuelto
  (`resolve_material`) y, en acero liso, por el ROL (eje/pasador/piñón/polea → mecanizado,
  cadena → pavonado) y la categoría de catálogo. Albedo: color asignado por el usuario > color
  propio del acabado > paleta (lo pintado se sigue distinguiendo por pieza).
- **Los dos lados**: `services/apariencia.apariencias_documento(doc)` aplica la tabla a un
  documento. El payload de escena manda `acabado` + `albedo` por pieza (también en las entradas
  `same` del delta: `set_material`/`set_color` no suben el rev) y el visor lee los parámetros de
  `ui/src/viewport/acabados.json`, copia GENERADA (`scripts/acabados_ui.py --escribir`) que
  `tests/test_apariencia.py` compara byte a byte. VTK recibe las apariencias como dato
  (`extract_render_scene(apariencias=)`, `EscenaViva(apariencias=)`, el kernel no importa
  `library`) en la foto de `render_view`, el GIF de movimiento, el GIF de dinámica y el video de
  la tienda. Como el render VTK no tiene luz por imagen, `render_comun.phong_de_pbr` traduce PBR
  → Phong, calibrado para que el acero pintado quede como el Phong de antes.
- **Relieves procedurales** (`ui/src/viewport/relieve.ts`): 6 tipos (pintura, cepillado,
  moteado, fundición, veta, tejido) generados con semilla fija, como `bumpMap`; las piezas no
  traen UV, así que `uvCaja` las proyecta en mm por la cara dominante. VTK no pinta relieve.
- **Guarda decidida aquí**: la palabra de carpintería del nombre («Larguero (+Y)») sólo pinta
  madera en el vertical madera; si no, los largueros de una faja de acero se veían de madera.
  La BOM y la masa siguen con la heurística de `resolve_material` (no se tocó: es de otra fase).
- **Captura comparada** (riesgo «el visor y VTK se ven distintos»): un test renderiza con VTK
  caucho, galvanizado y acero pintado y comprueba el tono de cada uno contra la tabla; otro
  comprueba que cada ítem del snapshot VTK lleva el color y el (metalness, roughness) del
  payload del visor.
- **Pendiente de F1 — piso con sombra de contacto**: el piso actual (`scene-setup.ts`) recibe la
  sombra de la luz direccional, que cae desplazada; una sombra de contacto de verdad necesita un
  pase propio (render desde abajo + desenfoque) dentro del bucle de render de `Viewport.tsx`,
  que está congelado en el trinquete de tamaño (1631 líneas). Va con su propio paso: sacar
  primero el bucle de render a un módulo y luego sumar el pase.
