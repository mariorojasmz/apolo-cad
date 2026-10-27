---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: contrato escrito (2026-10-26) con la F0 medida en una faja de motor central; F0b hecha (10 hallazgos en la bitácora); F2 (sólo la cuña de ENTRADA cuando se conoce el sentido, registro v7) mergeada; faltan D11 (avisos justificables), F1 (el tensor cuenta lo que estira el lazo y suma los tensores), F3 (las piezas que sobran), F4 (adelgazar esa faja por MCP) y F5 (Mario la ve)
descripcion: La puerta de publicación deja de obligar al agente a poner tensores y guardas que no hacen falta, y avisa cuando una pieza de protección sobra
---

# La puerta de publicación no obliga a poner piezas que no hacen falta

## Estado y origen

Mario, mirando en el visor una faja de motor central (drive en Ω: tambor motriz abajo con dos
desvíos, 2 m × 500, banda PVC de 2 capas) que pasó varias rondas de corrección hasta aprobar la
puerta: «tiene placas que se fueron agregando por las rondas de validación… mira ese “Tensor de
carro de la banda, cola (-Y)”, es grande, también guardas adicionales que creo no eran
necesarias… ¿cómo es que se llegó a esto? Quiero que investigues la validación que está obligando
al agente a agregar cosas».

La investigación (F0, abajo) confirma que dos controles de la puerta piden MÁS de lo que la
física y la norma piden, y que nada detecta una pieza de protección que sobra.

## El problema / lo que hay hoy

1. **El tensor** (`library/calidad/tensor.py`). La regla pide una carrera ≥ 1 % del lazo + 20 mm
   (`carrera_requerida`, línea 44) y la compara con la carrera del MEJOR tensor (`_mejor`, línea
   77; `evaluar_lazo`, línea 124). Dos errores:
   - **Compara la carrera del tambor con lo que se estira la BANDA.** Un tambor que la banda
     abraza 180° y se corre `t` en la dirección de sus dos ramales alarga el lazo `2·t`; uno con
     menos abrazamiento, menos. La regla pide en el tambor lo que hay que recuperar en el lazo:
     el doble en un tensor de cola.
   - **No suma los tensores de un mismo lazo**: con tres tensores toma uno.

   Medido en la faja de motor central: lazo de 4738 mm → pide 67,4 mm. Tenía tres tensores del
   usuario (`create_take_up` en la cabeza y en los dos desvíos) de 24 mm cada uno → FALLA. El
   modelador, para aprobar, agregó en la cola dos unidades de carro `UCT205-150` (la ÚNICA carrera
   de esa familia en el catálogo: marco 317 × 199 mm), desproporcionadas para una faja de 2 m.
   Sólo el tensor de cabeza (≈ 180°) ya da ≈ 48 mm de lazo; con los desvíos, probablemente pasa
   sin la UCT (F1 lo calcula).

2. **Las cuñas banda ↔ tambor** (`library/seguridad/peligros.py`, líneas 15–17;
   `services/calidad_sondas.py::cunas`, línea 155). Se toman como peligro las DOS cuñas de cada
   tambor que la banda abraza, porque «el sentido de marcha no se conoce». El peligro de arrastre
   (ISO 12100, anexo B: atrapamiento/arrastre) está en el punto de ENTRADA, donde la banda y el
   tambor convergen; en la cuña de SALIDA se separan y no arrastran. Con el sentido conocido, la
   mitad de las cuñas no son peligro y sus resguardos no hacen falta.

   Medido (sondas sobre una copia, quitando cada pieza con sus `fasten`):

   | pieza quitada | `seguridad.resguardo_iso13857` |
   |---|---|
   | ninguna | OK (7 peligros resguardados) |
   | «Deflector anti-pellizco de cabeza (-Y)» (chapa 141 × 70 × 2) | FALLA: 1 sonda con el brazo doblado llega al tambor de cabeza |
   | «Guarda de transferencia de cabeza» (chapa 104 × ancho × 3) | FALLA: 1 sonda llega al tambor de cabeza |
   | «Guarda lateral de cabeza (-Y)» | **OK**: ninguna sonda la necesita |
   | las tres | FALLA: 6 sondas |

   Qué cuña bloquea cada una (entrada o salida) lo mide la F2: si es la de salida, sobra.

3. **Nada avisa que una pieza de protección sobra.** La «Guarda lateral de cabeza (-Y)» no la
   pide ningún control (fila 4 de la tabla): la agregó una ronda de corrección por un hallazgo del
   revisor ciego (LLM) y quedó. Una guarda de más no es insegura, pero cuesta, pesa y estorba el
   servicio; la puerta sólo mira que falte, nunca que sobre.

## Lo que se revisó antes de escribir esto

- `tensor.py` entero: `carrera_requerida` (banda 1 % + 20, cadena 3 %/2), `_mejor`,
  `agarre_en_carrera`. El 1 % viene de CEMA y fabricantes como ESTIRAMIENTO DEL LAZO: la cifra
  está bien, lo que falta es pasarla al tambor.
- `services/calidad_tensores.py`: reconoce `create_take_up` (carrera medida: 24 mm aquí),
  unidades de catálogo con `specs.carrera_mm` (UCT), las ranuras del motor de la plantilla de
  rodillos y el metadato `doc.tensores`. Cada tensor sabe su pieza móvil (`pernos[].movil`) y su
  eje.
- `library/ruta_faja_modelo.py` (D13 de la fábrica de videos, mergeado): de la SECCIÓN del sólido
  de la banda saca la línea media del lazo, qué tambores abraza (`envueltos`) y el abrazamiento.
  Ahí están los ramales que entran y salen de cada tambor: la dirección que hace falta para F1 y
  para el sentido de F2.
- `services/marcha_ejemplo._sentido`: el sentido de la marcha de ejemplo sale de la junta motriz
  respecto del centro de la banda (hacia la cabeza motriz). En un drive CENTRAL no decide nada:
  el motriz está al medio.
- `peligros.py` y `calidad_sondas.cunas`: las dos cuñas salen de los dos bordes del arco de
  contacto (`bordes`, signo ±1): elegir una es elegir un signo.
- `calidad/registro.py`: `VERSION_REGISTRO = "6"`; los testigos congelan el veredicto por ítem.

## Decisiones (para vetar)

- **D1 — El tensor se mide en LAZO, no en tambor.** Cada tensor da `Δlazo = t · Σ (d · ê_k)`,
  con `t` su carrera, `d` la dirección en que corre su pieza móvil y `ê_k` los vectores
  unitarios de los ramales libres que salen de su tambor hacia los vecinos (la derivada del largo
  del lazo respecto de la posición del tambor; geometría, sin norma). Un tensor de cola con 180°
  da `2·t`; un desvío, menos. Lo requerido sigue igual (1 % del lazo + 20 mm, cadena 3 %/2).
  Sin línea media del lazo (no hay sección cerrada) se usa el factor 1 de hoy y se dice.
- **D2 — Los tensores de un mismo lazo se SUMAN** (cada uno se ajusta por separado). El agarre en
  toda la carrera se sigue exigiendo a cada uno. La evidencia lista el aporte de cada tensor y
  cuáles alcanzan solos: un tensor que no hace falta se nombra (lo usa D6).
- **D3 — Sólo la cuña de ENTRADA cuando el sentido se conoce; las dos si no.** El sentido de cada
  banda sale, en este orden: (a) un escenario de prueba que la declara (`bandas[].
  direccion_transporte`); (b) el requisito nuevo `sentido_transporte` (vector, p. ej. `[1, 0, 0]`)
  con `reversible` (bool, por defecto falso); (c) la plantilla `create_belt_conveyor`, que lo
  conoce por construcción. Sin ninguno, o `reversible`, las dos cuñas, como hoy (nunca se adivina
  desde el nombre ni desde la junta en un drive central).
- **D4 — La cuña de entrada se elige con la línea media del lazo**: el borde del arco donde el
  ramal LLEGA al tambor en el sentido de marcha. No se mira el giro de la junta: un tambor de
  desvío gira al revés que el motriz y la banda es la que manda.
- **D5 — Ítem nuevo `diseno.sin_sobrantes`** (modo de falla general: protección o tensado que no
  sirve a ningún peligro ni requisito). Candidatas: las piezas que la puerta trata como guarda
  (`revisar_guardas`) y los tensores que D2 nombra como innecesarios. Una guarda sobra si, sin
  ella (y sin los `fasten` que sólo la nombran a ella), `resguardo_iso13857` sigue OK y ninguna
  otra pieza queda sin unión. **Voraz y en orden** (de la más pesada a la más liviana; lo quitado
  queda quitado) para que dos guardas que cubren el mismo hueco no salgan las dos «sobrantes».
- **D6 — Sobrante = FALLA, con salida justificada.** Una pieza de protección sin función se quita
  o se justifica en el metadato nuevo `justificadas` (`[{pieza, porque}]`: guía de producto,
  pedido del cliente, polvo…), como `marcha.json` en la fábrica: la decisión queda escrita y
  vetable. Un tensor sobrante NO es FALLA (quitarlo cambia los apoyos del eje): va como nota del
  ítem de tensión.
- **D7 — El costo se acota**: `diseno.sin_sobrantes` corre sólo en la puerta de publicación (no en
  `delivery_check`), reutiliza el análisis de la corrida (`contexto.una_vez`) y re-traza sólo los
  peligros que la guarda tocaba (las sondas que la guarda bloqueó). F0 midió ≈ 21–25 s por
  re-corrida completa en esta faja; la meta es ≤ 2× la puerta de hoy.
- **D9 — La prueba de «¿sobra?» es GENERAL, no de fajas.** Mario: «la gran mayoría [de las
  máquinas futuras] no serán con fajas». Además de las guardas y los tensores de D5, son
  candidatas TODAS las piezas que una ronda de corrección agregó (los comandos del log posteriores
  a la primera corrida de la puerta de esa máquina: placas, ménsulas, refuerzos, deflectores, de
  cualquier familia). Una sobra si, sin ella y sin los `fasten` que sólo la nombran, ningún ítem
  de la puerta empeora (mismo estado o mejor en todos). Así el criterio no depende del mecanismo:
  lo que se agregó para aprobar tiene que seguir siendo necesario para aprobar. Las piezas del
  diseño original no se prueban así (son decisión del cliente o del diseño); las agregadas, sí.
- **D10 — Cada umbral se audita contra su fuente** (F0b). Una regla no pide más que su norma o su
  cálculo sin decirlo: si es más estricta a propósito, la evidencia lo dice («criterio propio,
  más estricto que X porque …»). Las que dependen del servicio (vida L10, factor de servicio) se
  calculan con el servicio DECLARADO en los requisitos (horas por día, choques), no con una cifra
  fija para toda máquina. Lo que la auditoría encuentre exagerado entra como fase propia.
- **D11 — Un aviso se corrige o se JUSTIFICA, no se calla con una pieza.** Hoy un aviso es FALLA
  sin salida en `entrega.semaforo` (`calidad/puerta.py::semaforo_entrega`, decisión D2 del plan de
  la puerta), `riesgos.electrico` (`puerta.py::erc`) y `ingenieria.reglas`
  (`calidad/vida_util.py`, salvo las «informativas»). Verificado: la única forma de aprobar un aviso
  que no aplica es agregar algo (un perno en un barreno, un silenciador, un refuerzo). Con el mismo
  metadato `justificadas` de D6 (`[{regla o pieza, porque}]`), un aviso justificado por escrito
  pasa; un ERROR nunca se justifica. Es la regla que ya rige para el modelador («cada AMARILLO
  corregido o justificado») llevada a la puerta.
- **D8 — `VERSION_REGISTRO` sube a 7** y los testigos se re-congelan a propósito; cada cambio con
  su defecto sembrado (`tests/test_defectos_sembrados.py`): tensor de cola con 180° que aprueba
  con la mitad de la carrera de hoy, tres tensores que suman, cuña de salida sin guarda con
  sentido declarado, guarda que sobra.

## Alternativas descartadas

- **Sumar al catálogo UCT de menos carrera** (100 mm): achica la pieza pero deja la regla pidiendo
  el doble; se puede sumar después si un caso lo pide.
- **Bajar el 1 % a 0,5 %**: la cifra es la del estiramiento de servicio (CEMA, fabricantes); el
  error es dónde se compara, no el porcentaje.
- **Inferir el sentido del giro de la junta motriz**: en un drive central el motriz gira al revés
  que los tambores extremos y el signo de la junta depende de cómo se declaró: D3 sólo acepta
  fuentes que dicen el sentido de la BANDA.
- **Sobrante como aviso que no frena**: es lo que hay hoy (nada) y fue lo que dejó pasar la guarda
  lateral; el revisor LLM agrega piezas y el modelador las acepta sin costo visible.

## Fases

- **F0 — medir (hecho en parte, sólo lectura).** La tabla de arriba y el tensor (4738 mm, 67,4 mm,
  3 × 24 mm). Falta: el `Δlazo` de cada tensor de esa faja con D1; qué cuña bloquea cada guarda;
  lo mismo en `create_belt_conveyor` por defecto y en 2 variantes (una grande), y el costo de una
  re-corrida por guarda.
- **F0b — auditar los umbrales (S, sólo lectura).** Los 30 ítems de `calidad/registro.py`: la
  cifra de cada uno, su fuente y si pide más que ella (D10). Primeros sospechosos: vida
  L10 ≥ 20 000 h fija (es la de una máquina de 8 h/día a plena carga; una intermitente pide menos),
  factor de servicio ≥ 1,25 fijo (depende del tipo de carga) y FS de pandeo ≥ 3.
- **F1 — tensor en lazo y suma (M, `library/calidad` + `services/calidad_tensores`).** D1, D2, D8
  (su parte). Verifica: tests del tensor (cola 180°, desvío, tres que suman, sin sección → factor
  1), testigos re-congelados, la faja de F0 aprueba sin las UCT (en copia).
- **F2 — cuña de entrada (M, `library/seguridad` + `services/calidad_sondas` + `requisitos`).**
  D3, D4. Verifica: con sentido declarado, una cuña por tambor y la otra sin peligro; reversible y
  sin sentido, como hoy; `create_belt_conveyor` declara su sentido; defecto sembrado.
- **F3 — sobrantes (M, `library/calidad` + `services` + API + MCP).** D5–D7 y D9: el ítem, el
  metadato `justificadas` con su endpoint, la evidencia (qué peligro dejaba de cubrir cada pieza
  o «ninguno»); `publication_gate` lo muestra (golden). Verifica: guarda redundante = FALLA, par
  que cubre el mismo hueco = una sola sobrante, justificada = OK; costo medido.
- **F4 — adelgazar la faja de motor central (S, por MCP, fuera del núcleo).** Declarar el sentido,
  sacar las UCT (la cola vuelve a apoyos fijos si los tres tensores alcanzan), sacar lo que F3
  diga que sobra, puerta aprobada y `delivery_check` VERDE; antes/después de masa y costo.
- **F5 — Mario la ve en el visor.**

Dependencias: F1 y F2 son independientes; F3 usa D2 (F1) y es más útil con F2; F4 después de F3.

## Lo que este plan NO hace

- No cambia el umbral del estiramiento (1 % + 20 mm) ni el de la cadena.
- No revisa las demás reglas de la puerta (sondas, guardas atornilladas, agarre) más allá de la
  cuña; si F0 encuentra otra que sobrediseña, va como hallazgo a la bitácora.
- No cambia el prompt del revisor ciego: el sobrante lo atrapa la puerta, sea quien sea que lo
  agregó.

## Riesgos

- **Un sentido declarado mal deja sin guarda la cuña real.** Mitigación: el sentido de un
  escenario de prueba se verifica al correrlo (la caja avanza en esa dirección); el requisito
  suelto queda en la memoria y en la evidencia del ítem («sentido declarado por el requisito»).
- **D1 con una línea media rara (banda a mano mal cerrada)** da un factor falso. Mitigación: el
  factor se acota a [0, 2] por tambor y, fuera de eso, se usa 1 y se avisa.
- **El ítem de sobrantes alarga la puerta.** Mitigación: D7, y medirlo en F3 con la máquina grande
  de las variantes.

## Bitácora

### F0 (2026-10-26, parcial)

Sobre una copia de la faja de motor central (565 comandos, 338 sólidos): `controles_seguridad`
sin el ERC, ≈ 21–25 s por corrida en la laptop; resultados en la tabla de «El problema». El lazo
de la banda (sección del sólido) mide 4738 mm; tensores reconocidos: tres `create_take_up` de
24 mm (cabeza y desvíos) y dos `UCT205-150` de 150 mm agregados en las rondas de corrección. La
fidelidad de la cinta animada (D13 de la marcha) da OK sobre esa copia (desvío 4,4 mm).

### F0b (2026-10-26, auditoría de sólo lectura)

Informe completo fuera del repo (orquestador). El registro tiene 30 ítems. Hallazgos, de mayor a
menor sobrediseño posible; sólo el 2 lo verifiqué contra el código, los demás se verifican en su fase:

1. `riesgos.partes_moviles`: el brazo doblado (sonda de 20 mm que dobla el codo en cualquier
   punto) juzga toda abertura > 20 mm como ranura aunque sea cuadrada o redonda (ISO 13857 da otra
   tabla para esas); sin tope de altura de alcance; bisagras y palancas a mano y todo extremo de eje
   cuentan como peligro.
2. **Aviso = FALLA** sin salida (D11, verificado).
3. Una guarda soldada es FALLA (ISO 14120 admite la soldadura en el resguardo fijo) y el rol
   «guarda» sale del nombre.
4. FEA: FS ≥ 2 sobre el σ de von Mises PICO (las singularidades de la malla piden costillas).
5. Vuelco con margen del 10 % sin fuente y sin mirar si la máquina va anclada.
6. L10 ≥ 20 000 h fija para toda máquina, con la carga del tambor puesta en todos los rodamientos.
7. Motor: márgenes apilados (μ 0,33, ×1,3, arranque 1,6 contra el par nominal); la cifra de AGMA
   1,25 es la de carga uniforme de más de 10 h/día.
8. Cadena: servicio «moderado» por defecto + FS 1,2 + avisos geométricos.
9. Pandeo con K = 2 y FS 3; soldaduras al 0,7 del admisible.
10. Banda sin fin sin aceptar el vulcanizado en sitio; acceso de herramienta sólo con llave de boca.

Cada uno entra como fase propia (después de F3) o se descarta con su porqué, a la vista de Mario.
### F2 (2026-10-26)

Qué entró:
- `library/seguridad/cuna_entrada.py` (puro): el lazo de la línea media en el sentido de marcha
  (el ramal superior = el tramo recto más largo con la normal hacia afuera a < 60° de la
  vertical, avanza en el sentido de transporte), la LLEGADA a cada tambor (primer punto del tramo
  en contacto, con los tramos rectos densificados a ≤ r/10: un desvío también tiene vértices) y el
  borde del arco más cercano a ella.
- `services/calidad_cunas.py`: el sentido de cada banda (D3) y la sección del sólido de la banda
  en el plano ⟂ al eje de los tambores (`seccion_plano`, como la marcha visual); `cunas(…, hacia)`
  deja sólo el borde de entrada. Cuesta 62 ms en la faja de motor central.
- Requisitos `sentido_transporte` (vector de 3, texto «1, 0, 0» o eje con signo «+X»; se guarda
  unitario; un mal formado se rechaza al declarar) y `reversible` (sí/no). Docstring de
  `set_requirements` (golden re-congelado: sólo `list_tools`).
- Evidencia: cada peligro de cuña lleva `sentido` («cuña de entrada; sentido: escenario «X»» |
  «requisito sentido_transporte» | «plantilla create_belt_conveyor (c1): de la cola al motriz» |
  «desconocido: las dos cuñas» | «reversible (requisito): las dos cuñas») y su texto suma
  «(cuña de entrada)».
- `VERSION_REGISTRO` 6 → 7. Los cuatro testigos públicos se re-congelaron SÓLO por la versión:
  ningún veredicto por ítem se movió (la faja de la plantilla ahora declara su sentido y sus
  guardas cubren las cuñas de entrada; `sin_cierres` sigue en FALLA por ellas). Defecto sembrado
  `cuna_de_entrada_sin_guarda`: con el requisito +X y sin guardas, FALLA por la cuña de entrada
  (3 puntos por tambor, no 6).

Decisiones (vetables):
- **La plantilla no se tocó**: su sentido sale de los centros de SUS dos tambores en la escena
  (cola → motriz: la cabeza motriz tira), así sigue a un giro o traslado posterior y el executor
  no cambia (sin `version` ni epoch). Una faja de plantilla dentro de un `insert_project` no se
  reconoce (command_id sintético): las dos cuñas.
- Dos escenarios que declaran sentidos distintos para la misma banda = desconocido (las dos).
  `reversible` gana a toda fuente. El requisito vale para todas las bandas de la máquina.
- Si la llegada queda a < 2° de diferencia entre los dos bordes, o el sentido forma > 60° con el
  ramal superior, o la sección no da lazo: las dos cuñas, y la evidencia dice por qué.

Medido en la faja de motor central de la F0 (copia en memoria, base en sólo lectura). El sentido
es +X: la cola en x = 0, la cabeza en x = 2000 con la «Guarda de transferencia de cabeza» más
allá (x ≈ 2073), el motriz en x = 1000 entre los desvíos de x = 889 y 1111. Las llegadas salen
donde deben: a la cola por ABAJO, a la cabeza por ARRIBA, al desvío (+X) arriba del lado +X, al
motriz y al desvío (−X) del lado por donde sube o baja la banda; los cinco tambores con una cuña.
Para ver la otra cuña se declaró −X (la «entrada» de −X es la salida real):

| pieza quitada | sentido +X (cuñas de entrada) | sentido −X (= las de salida) |
|---|---|---|
| ninguna | OK (7 peligros) | OK |
| «Deflector anti-pellizco de cabeza (-Y)» (c644) | **FALLA**: 1 sonda con el brazo doblado llega a la cuña de ENTRADA de la cabeza | OK |
| «Guarda de transferencia de cabeza» (c426) | **OK** | FALLA: 1 sonda recta llega a la cuña de SALIDA de la cabeza |
| «Guarda lateral de cabeza (-Y)» (c427) | OK | OK |

≈ 14–16 s por corrida de `controles_seguridad` (sin ERC) en la laptop. Con el sentido declarado:
el deflector hace falta (entrada); la guarda de transferencia sólo resguardaba la cuña de salida
y, para `resguardo_iso13857`, sobra (F3 dirá si sirve a otro ítem: la transferencia de producto
no se modela como peligro); la guarda lateral no bloquea ninguna de las dos, como en la F0.
