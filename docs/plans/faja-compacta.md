---
estado: en curso
nota: contrato escrito por Claude con el criterio delegado (2026-10-28, vetable por número); falta F1 (plantilla create_belt_conveyor, criterio 9) y F2 (la mesa de sorteo manual de 12 puestos re-corrida con ella, por MCP)
descripcion: La faja ofrece motorreductor sinfín de eje hueco calzado en el tambor (motor a lo largo del larguero) y tensor de placa ranurada, con la carrera del tensor calculada y el carro al inicio
---

# Faja compacta: motor pegado al larguero y tensor liviano

## Estado y origen

Mario, mirando la «Mesa de sorteo manual 12 puestos» en el visor (2026-10-28):
- «¿amerita tan grande el «Faja central · Tensor de carro (2)»?» — es un UCT205-150 (317 × 199 mm,
  4,8 kg) en una faja liviana.
- «¿se podría apegar el motor al larguero? … dale elegancia y optimiza el espacio si es que se
  puede».

Hoy `create_belt_conveyor` sólo sabe montar un motorreductor coaxial (helicoidal o de ejes
paralelos) sobre una base de dos brazos y una ménsula soldada a la pata, con acople y guarda de
acople (F1b D9 de [faja-larga-en-tramos](faja-larga-en-tramos.md)): sobresale ~450 mm del
larguero. El catálogo ya tiene la familia NMRV (`31_motorreductores_sinfin.yaml`, eje hueco de
salida con `bore_d`), que la plantilla no ofrece.

La re-revisión a ciegas de la clasificadora (MEDIA) además midió en el tensor 75 mm de carrera
por lado con el carro CENTRADO, contra 103,5 mm que pide el 1 % de estiramiento de un lazo de
20,7 m más 20 mm de montaje.

## Decisiones (para vetar)

- **D1. Motorreductor de eje hueco en el tambor motriz** (`motor` acepta las refs NMRV): el
  reductor se calza en el extremo del eje motriz (eje vivo sobre sus dos chumaceras, como hoy)
  con chaveta; el motor queda **acostado a lo largo del larguero, hacia la cola**, por fuera del
  larguero y bajo el nivel de la banda; el par lo toma un **brazo de reacción** atornillado al
  larguero con buje elástico, anclaje desfasado del eje (criterio de la raíz: «Anti-giro de un
  shaft-mount»). Sin acople, base, brazos, ménsula ni guarda de acople. El extremo libre del eje
  hueco lleva su tapa. Va del lado opuesto a `lado_abierto` (con «ninguno», +Y como hoy).
- **D2. Calce y cuenta**: el `bore_d` del NMRV tiene que ser el `shaft_d` del tambor motriz; si
  no, error que nombra los NMRV que calzan. La relación sale de la velocidad de banda pedida (la
  relación de catálogo más cercana) y la cuenta de `rules_faja_motor` (η = 0,75 sinfín, ya
  reconocida) decide si el tamaño alcanza: si no, error con el tamaño siguiente. La plantilla no
  elige el tamaño sola: lo pide el modelador y la cuenta lo juzga.
- **D3. Tensor de placa ranurada** (`tensor: "placa-ranurada"`, opción por función para fajas
  livianas): chumacera de BRIDA de catálogo del Ø del eje de cola, apernada por ranuras a una
  placa soldada al larguero, y un perno empujador con contratuerca en una oreja soldada. El UCT
  queda para fajas cargadas. Sin pieza inventada: la placa y la oreja son chapa de la plantilla;
  chumacera, pernos y tuercas, de catálogo.
- **D4. Carrera calculada y carro al inicio**, para los dos tensores: carrera necesaria = 1 % del
  lazo + 20 mm de montaje (criterio de diseño; el 1 % es el estiramiento de servicio de una banda
  de tejido, a citar por F1 con su fuente o, sin ella, declarado como criterio). El tensor se
  elige con carrera ≥ esa (placa: la ranura se dimensiona; UCT: el de carrera suficiente, si no
  error) y el carro sale **al inicio de la carrera** (banda recién montada), no centrado.
- **D5. Criterio 9** (sello de entrada, `exec_faja.sellar`): D4 se aplica sólo a faja nueva; un
  log viejo (criterio ≤ 8) regenera igual. D1 y D3 son valores nuevos de `motor`/`tensor`: un log
  viejo no los trae. Sube la `version` de `create_belt_conveyor`.
- **D6. Todo pasa la puerta nueva**: las piezas nuevas declaran sus uniones y salen con
  `union.contacto_real` en OK (plan [uniones-que-tocan](uniones-que-tocan.md)), sondas ISO 13857
  y acceso de herramienta en verde. El test mide cuánto sobresale el conjunto motriz del larguero
  (meta: ≤ 200 mm, del orden de 150) y lo compara con el coaxial.

## Alternativas descartadas

- **Motor vertical bajo la cama** (sinfín con el motor hacia abajo): libera el costado pero choca
  con el retorno y obliga a subir la altura mínima de trabajo.
- **Elegir el NMRV solo**: el modelador elige y la cuenta juzga, como con los demás motores; una
  plantilla que cambia el motor sin que se lo pidan esconde el costo.

## Fases

- **F1 — plantilla (núcleo, M)**: D1–D6 con tests (NMRV-063 en el TAMBOR-102 de una faja de 4 m y
  de 12 m en dos tramos; calce que no coincide da error; tensor de placa con la ranura de la
  carrera calculada; UCT con el carro al inicio; un log v8 regenera igual; la puerta de cada
  variante sin FALLA nueva).
- **F2 — la mesa de sorteo (MCP, S)**: la «Mesa de sorteo manual 12 puestos» con NMRV y tensor de
  placa, revisada a ciegas y por la puerta.

## Lo que este plan NO hace

- Motor en la cola ni tambor motorizado (motor dentro del tambor): son otros montajes.
- El voladizo de 342 mm de la cola y el techo de la guarda de cola (los otros dos MEDIA de la
  re-revisión): quedan vetables, fuera de esta fase.

## Riesgos

- **Guardas**: el motor a lo largo del larguero puede tapar el acceso a los pernos del larguero o
  quedar en el camino de una sonda; D6 lo mide.
- **Par de arranque en el brazo de reacción**: la cuenta lo dimensiona con el arranque directo
  (2 × nominal, el mismo criterio que la base de hoy).

## Bitácora
