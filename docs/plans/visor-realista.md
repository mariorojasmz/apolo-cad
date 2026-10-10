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
