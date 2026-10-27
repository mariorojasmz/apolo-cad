---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: contrato escrito (2026-10-26) con la F0 medida en una faja de motor central; F0b hecha (10 hallazgos en la bitácora); F1 (el tensor en lazo y sumado) y F2 (sólo la cuña de ENTRADA con sentido conocido) mergeadas, registro v7; F3 + D11 (las piezas que sobran y los avisos justificables, registro v8) mergeadas; F3b (falsos positivos y huecos en máquinas que no son fajas, registro v9) mergeada; F3c (union.agujeros, espárragos, factor de servicio declarado, flecha sin vigas, holgura funcional, lo eléctrico fuera de sobrantes, memo de masas, campo del codo compartido, get_job resumido; registro v10; la puerta del elevador 378 → 61 s) mergeada; F3d (lo que la entrega no evaluó se justifica por escrito, registro v11) hecha en su rama, sin mergear; faltan F4 (adelgazar esa faja por MCP), F5 (Mario la ve) y las poses de reposo (propuesta en § F3b)
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
- **F3b — falsos positivos y huecos en máquinas que no son fajas (M).** Lo que dieron una
  mezcladora, un tanque con agitador y un elevador modelados por MCP: bisagras de servicio como
  peligro, «tapas» como resguardo, la L10 sin las rpm declaradas, las funciones sin canal, el piso
  bajo la losa, el acople y la salida del motorreductor sin peligro, las poses de reposo
  (§ Bitácora F3b).
- **F3c — lo que la puerta no veía en esas tres máquinas (M).** La unión atornillada declarada sin
  agujeros (ítem nuevo `union.agujeros`), el espárrago soldado con su tuerca, el factor de servicio
  fuera de un transportador con el servicio declarado, la flecha sin vigas, el objetivo dentro de
  una holgura funcional y lo eléctrico como «agregado» a sobrante (§ Bitácora F3c).
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
### F1 (2026-10-26): el tensor en lazo y la suma

Hecho: `library/ruta_faja_modelo.py` suma `ramales`/`factor_lazo` (puros: el arco de contacto de
la línea media con el tambor, los dos ramales libres y |Σ d·ê_k|); `services/calidad_tensores_lazo.py`
(nuevo) arma el marco de la banda (eje = normal de sus caras laterales), corta su sección por el
centro del ancho con `seccion_plano` (el mismo corte de la marcha en el visor), saca la línea media
con `linea_media` y le pone a cada tensor `tambor`, `factor_lazo`, `abrazamiento_deg` y
`factor_motivo`; `library/calidad/tensor.py` suma por tambor, nombra los que no hacen falta y mide
el agarre de CADA tensor. `VERSION_REGISTRO` = "7". Lo requerido no cambió.

**La faja de motor central de la F0** (sólo lectura, con este código): lazo 4738,1 mm, pide 67,4.

| tensor | carrera | abrazamiento | factor | Δlazo |
|---|---|---|---|---|
| tambor de cabeza (`create_take_up`) | 24 mm | 180° | 2,00 | 48,0 mm |
| tambor de desvío +X (`create_take_up`) | 24 mm | 89,9° | 1,00 | 24,0 mm |
| tambor de desvío −X (`create_take_up`) | 24 mm | 89,9° | 1,00 | 24,0 mm |
| las dos `UCT205-150` de cola (un mismo tambor) | 150 mm | 180° | 2,00 | 300,0 mm (una vez) |

Con todo: 396 mm. **Sin las UCT: 96,0 ≥ 67,4 → el ítem pasa**; la nota además nombra un desvío
como prescindible (72 ≥ 67,4 sin él). `lazos(doc)` pasó de ≈ 2,1 a ≈ 2,2 s en esa faja (el corte de
la banda). La desproporción de la F0 era la regla: el lazo ya se tensaba con lo del usuario.

Testigos re-congelados (`--en-proceso --congelar`): sólo cambió `version_registro` 6 → 7 en los
cuatro; ningún veredicto se movió (la faja testigo ya pasaba con su UCT: 150 × 2 = 300 contra
≈ 104; los lazos de la de rodillos son cadenas, sin cambio). Defectos sembrados nuevos:
`tensor_a_medias` (0,45 × lo que pide en la cola = 0,9 en lazo: FALLA, el factor no da más de 2) y
`sin_tensor` (sin UCT ni metadato: SIN_EVALUAR, que bloquea, como hoy); `tensor_sin_carrera` sigue
en FALLA (20 mm × 2 = 40 contra ≈ 104).

Decisiones tomadas en la implementación (vetables):

- **Un tambor cuenta una vez.** Tensores cuyos centros caen a ≤ 10 mm en el plano del lazo mueven
  el mismo tambor (las dos UCT de un eje, o un take-up y un metadato sobre el mismo): un aporte,
  el menor del grupo. Sin esto D2 sumaba 600 mm por las dos UCT de cola.
- **El centro del tambor** es el de la pieza que corre: el eje del `create_take_up`, la caja de la
  unidad de catálogo (el builder `take_up_unit` tiene el agujero en su centro) o la pieza tensada
  del metadato (la primera que no es perno ni la banda). A más de 500 mm de la línea media no es un
  tambor que la banda toque: factor 1.
- **La dirección** es el eje del perno tensor medido; el `eje` del metadato; la de una UCT sale de
  su caja en el plano (calza con L × H del builder: la carrera va por L). Girada fuera de los ejes
  o sin dirección → factor 1 y la evidencia lo dice (`nota` del aporte).
- **Sin piso:** un tambor que corre ⟂ a sus ramales aporta 0 (antes, su carrera entera).
- **Cadenas sin cambio**: el mejor tensor contra 3 %·L/2 de centros. Ya está en centros (no tiene
  el error de la banda) y sumar sin agrupar por eje contaría dos veces los dos soportes de un eje.
- **«No hacen falta»**: voraz del de más carrera al de menos (el mecanismo más grande primero); va
  en el texto y en `evidencia.no_hacen_falta`, nunca como falla. Un tensor sin carrera medida no
  suma (si los demás no alcanzan, FALLA como hoy) y se lista en `sin_carrera`.
- **Agarre de cada tensor** del lazo (antes sólo del mejor): en la faja de F0 entran los tres
  take-up y pasan.

Hallazgo fuera del alcance: `tensores_reconocidos` toma por tensor toda ref de catálogo con
`specs.carrera_mm`, y los amortiguadores hidráulicos (`134_amortiguadores.yaml`) la tienen; uno
junto a una banda contaría como tensor (con factor 1, sin dirección). Conviene reconocer la unidad
por su familia (`take_up_unit`) o su categoría: va como fase propia si se confirma.

### F3 + D11 (2026-10-27): lo que sobra y los avisos justificables

Qué entró:
- **D11** — metadato `justificadas` (`[{regla?, pieza?, porque}]`, `library/calidad/justificadas.py`;
  setter `services/puerta_publicacion.poner_justificadas`, `GET|PUT /api/justificadas`, tool MCP
  `set_justifications`). `porque` < 20 caracteres, clave desconocida o pieza inexistente → 400. Un
  AVISO cuya `regla` (el texto exacto de `casos[].regla`) está justificada deja de bloquear en
  `entrega.semaforo`, `riesgos.electrico` y `ingenieria.reglas`; con `pieza`, sólo si TODAS las
  piezas del aviso lo están. Un error nunca (no se mira la lista). La evidencia lista lo justificado
  con su porqué. Entra a la firma del modelo sólo si hay (sin él, la firma de siempre).
- **D9, la primera corrida** — el endpoint de la puerta anota en el manifest `puerta_primera =
  {ultimo_comando, comandos}` la PRIMERA vez que corre (fuera de la firma: es un hecho histórico,
  no el modelo; un documento de sólo lectura no se anota). Candidatas (b) = las piezas cuyo comando
  raíz tiene número mayor. Sin el dato, ninguna «agregada».
- **D5 — `diseno.sin_sobrantes`** (familia proceso, `library/calidad/sobrantes.py`, medido por
  `services/calidad_sobrantes.py`, sólo en `reunir`: `delivery_check` no lo corre). Candidatas: los
  cuerpos de guarda de `revisar_guardas` + las agregadas; nunca la tornillería, lo que se mueve, la
  banda, los tensores reconocidos (D6: los que sobran siguen siendo nota de F1, que se copia como
  `nota_tensores_que_no_hacen_falta`) ni lo de menos de 10 g. Prueba voraz de la más pesada a la más
  liviana sobre una copia SUPERFICIAL (`doc_sin`: sin regenerar; sin la candidata, sus `fasten`/
  `ground` y la tornillería que sólo la unía), de lo barato a lo caro: sujeción → guardas → sondas
  rectas → ingeniería (si no es guarda) → brazo doblado. Sobrante = FALLA salvo `{pieza, porque}`.
- `VERSION_REGISTRO` 7 → 8. Testigos re-congelados (`--en-proceso --congelar`): los cuatro suman
  el ítem (faja OK, ménsulas NO_APLICA, rodillos FALLA) y la versión; ningún otro veredicto se movió.
- Golden MCP re-congelado: la tool nueva (y su 400) y el docstring de `publication_gate`.
- Defectos sembrados: `guarda_redundante` (una chapa por fuera de la guarda de cola, atornillada a
  ella: FALLA, sobra exactamente ella y la guarda la pide la cuña; justificada, OK), un aviso
  justificado (barreno sin perno en la ménsula: el AMARILLO pasa en la entrega y en la memoria) y un
  error justificado (el escombro: sigue ROJO).

Decisiones tomadas en la implementación (vetables):
- **Un apoyo no sobra.** Además de «nadie queda sin camino de carga», la candidata no puede
  sostener a una vecina que está más lejos que ella del piso en saltos de unión declarada
  (tornillería contraída). Sin esto salían «sobrantes» la segunda oreja de cada guarda, un ala de
  cada bandeja y una de las dos ménsulas de cuelgue del drive: el grafo no ve la palanca de una
  pieza colgada de un solo lado. Conservador a propósito: un falso «necesaria» cuesta poco; un
  falso «sobra» empuja al agente a quitar un apoyo.
- **Locación por objetivo** (D7): una candidata sólo re-traza los objetivos de un peligro a
  ≤ 1080 mm (brazo 850 + mano 230) de su caja; una sonda recta que llega lo hace a ≤ 850 mm de
  profundidad, así que lo que la para está a esa distancia. Un peligro que ya FALLA en la corrida
  no puede sumar sondas que llegan, por objetivo (sin esto las guardas de la de rodillos, cuya
  transmisión ya falla, salían todas «sobrantes»). Con 230 mm salían falsas las guardas inferiores
  de la faja de plantilla (cierran el paso del antebrazo a 400 mm de la cuña).
- **Ingeniería sin lints**: sin la pieza, los barrenos de su `join_bolted` quedan sin perno (la
  copia no regenera); se comparan los ítems de vida útil y estructura, no los lints.
- **Interferencias y gravedad no se re-corren**: quitar un sólido no crea un choque; la sujeción
  declarada es lo que la gravedad simula.
- **El campo de la muñeca por zona**: `CampoAlcance.libre_sin` rehace los voxeles libres sólo
  alrededor de lo quitado (el test lo compara con el campo entero: idéntico); el barrido del brazo
  sigue entero (≈ 3,4 s de los ≈ 5,6 s en la faja testigo).
- **Una vuelta más** (hasta 3): lo que pedían la sujeción o una guarda se re-prueba si algo sobró
  después (la guarda lateral que sostenía un deflector que sobró); lo que pedía un peligro no
  (quitar más sólo abre más).
- **Los defectos sembrados que miran otro ítem corren `reunir(sobrantes=False)`** (SIN_EVALUAR):
  presupuesto de la suite; la API lo corre siempre.

Medido en la faja de motor central de la F0 (copia en memoria, base en sólo lectura; candidatas
(b) desde c369, como si la primera corrida hubiera sido con el log hasta c368; laptop con otra
suite corriendo al lado). 42 candidatas (30 de guarda, 12 agregadas; 167 piezas posteriores a
c368, 125 de ellas tornillería).

| sentido | sobran | tiempo de la prueba |
|---|---|---|
| sin declarar (las dos cuñas, como la base) | «Guarda superior del drive (+X)» y «(−X)» (0,81 kg c/u, agregadas en la corrección), «Tapa del eje hueco del reductor (+Y)» (0,20 kg), «Oreja de guarda de cabeza (−Y)» y «de cola (−Y)» (sin perno propio: la guarda cuelga de la otra oreja) | 116–118 s |
| `sentido_transporte` +X | lo mismo + los dos «Deflector anti-pellizco de cola» (0,16 kg c/u: resguardaban la cuña de SALIDA de la cola) | 93 s |

- La «Guarda lateral de cabeza (−Y)» (c427), que la F0 halló sin función para las sondas, **no
  sobra**: sostiene al «Deflector anti-pellizco de cabeza (−Y)», que sí hace falta (con el brazo
  doblado llega a la cuña de entrada de la cabeza). Para quitarla hay que colgar el deflector de
  otra pieza (F4). Las laterales de cola, con +X, las pide la cuña de entrada de la cola.
- Las dos guardas de transferencia, las bandejas, los túneles y sus labios, las ménsulas del drive
  y las orejas con perno: necesarias (sujeción, apoyo o peligro). La «Tapa del eje hueco» sobra
  porque el extremo giratorio del eje hueco del reductor no es peligro en `peligros.py` (va de la
  mano del hallazgo del acople, abajo): justificable.
- Costo: la puerta entera (`reunir`, sin gravedad ni marcha) pasa de 50 s a 171 s (×3,4; la meta
  de D7 era ×2). Por etapa: sujeción 42 pruebas en 0,02 s; guardas 16 en 0,03 s; rectas 16 en
  26–30 s; ingeniería 5–6 en 8 s; brazo doblado 10–11 en 58–78 s (≈ 3,4 s del barrido del brazo
  más ≈ 1–3 s de sondas por prueba). Lo que queda para bajarlo: probar en un mismo campo las
  candidatas cuyas zonas (1080 mm) no se tocan, o el barrido del brazo por zona.
- La nota de F1 sale igual: no hacen falta las dos UCT de cola ni el take-up del desvío (−X).
- Faja testigo (plantilla, 4 m): 12 candidatas, 35 s de prueba (la puerta en proceso, con gravedad y
  marcha, ≈ 58 s); rodillos testigo: 13 candidatas, 17 s.

Hallazgos (fase propia, no se tocaron):
- La plantilla `create_belt_conveyor` (el testigo faja) trae tres guardas que la puerta no pide:
  las dos guardas inferiores del lado +Y (con las del −Y, el brazo no llega; medido también con
  `controles_seguridad` entero sin ellas: OK) y la «Guarda del acople» (el acople motor ↔ eje no es
  peligro en `peligros.py`: no es pieza propia). El testigo las justifica (`JUSTIFICADAS_FAJA` de
  `scripts/testigos.py`); toda faja de plantilla tendrá que hacer lo mismo hasta que se decida si
  sobran o si falta el peligro.
- En la de rodillos sobra la «tapa del extremo» de la guarda de la transmisión (13 g).

### F3b (2026-10-27): falsos positivos y huecos en máquinas que no son fajas

Medido sobre una foto de las tres máquinas de esta noche (las bases, en sólo lectura; las siguen
usando otros procesos: la revisión medida es la del momento), `controles_seguridad` sin el ERC y
`controlar_vida_util`, con el código de `main` (antes) y el de la rama (después):

| | mezcladora de paletas (219 sólidos) | tanque con agitador (120) | elevador de cajas (255) |
|---|---|---|---|
| peligros antes | extremo de eje 1, pieza giratoria 2 | transmisión 1, extremo 1, giratoria 2 | transmisión 2, extremo 2, giratoria 1 |
| peligros después | extremo 1, salida del motorreductor 1 | transmisión 1, extremo 1, salida 1 | transmisión 2, extremo 2, salida 1 |
| `partes_moviles` antes | FALLA: pilotos de la puerta del tablero (238 sondas), bisagra de la tapa de carga (110) | FALLA: tapa de la boca (53), pilotos (229) | FALLA: cadenas (10 y 15), eje loco (5), pilotos (149) |
| `partes_moviles` después | FALLA: salida del NMRV (138) | FALLA: salida del NMRV (117) | FALLA: cadenas (10 y 15), eje loco (5) |
| `resguardos_…` antes | FALLA (tapa de la bornera, «sólo apoyada») | FALLA (tapa plana soldada; bornera) | FALLA (bornera) |
| `resguardos_…` después | OK, 2 (no resguardan: bornera, tapa de ranura lado motor) | OK, 3 (la tapa plana es cerramiento: la boca de inspección cubre lo mismo) | OK, 1 (no resguarda: bornera) |
| L10 antes | SIN_EVALUAR «sin rpm» | SIN_EVALUAR «sin rpm» | SIN_EVALUAR «sin rpm» |
| L10 después | SIN_EVALUAR: 43 rpm (variable), sin carga declarada | 200 rpm (requisito), sin carga | 42,25 rpm (variable), sin carga |
| piso (`z_piso`) | −70 → 0 (los pernos de anclaje M12×100 entran en la losa) | 0 → 0 | 0 → 0 |
| segundos | 6,5 → 7,5 | 5,8 → 6,0 | 44,1 → 36,3 |

Qué entró, por punto:
1. **La junta de servicio** (`services/calidad_juntas.py`): una junta de giro está ACCIONADA si es
   `continua`, si un escenario la acopla a un motor o a un cilindro, si su padre es un actuador de
   catálogo (motorreductor, cilindro, amortiguador o resorte de gas) o si su cuerpo hijo está unido
   a uno. Si no, es de servicio: `peligros.de_giro` no la toma y lo que cuelga de ella no gira (los
   mandos de la puerta del tablero, la tapa de carga y la de la boca), pero su cuerpo sigue en
   `moviles` (no es resguardo fijo, no se le ata un cable). También sale de la familia D15
   «apoyo rotativo». Test: `test_puerta_f3b` (bisagra = sin peligro; continua, escenario y
   actuador = peligro).
2. **Resguardo** (`calidad_seguridad.resguardos`): el ítem juzga sólo las guardas que pararon una
   sonda de un peligro detectado o las declaradas en la función `resguardo` de `funciones`; las
   demás van en `no_resguardan`. Una soldada es cerramiento permanente (ISO 14120 §3.2) si a cada
   peligro que cubre también se llega por un resguardo MÓVIL (el cuerpo de una junta de servicio);
   detrás de una guarda atornillada sigue en FALLA. Sin guardas que resguarden, el control da
   NO_APLICA y el general lo da por cumplido (`vacio_ok`). Tests puros y uno con una «Tapa final de
   bornera» que no cubre nada; el defecto `guarda_soldada` sigue en FALLA.
3. **L10 con lo declarado** (`engineering_rules.rodamientos_declarados`): sin transportador, las
   rpm salen del requisito `rpm_salida`, la variable `rpm_salida`, las variables `rpm_motor` /
   `ratio_red` o el `rpm_salida` del motorreductor de catálogo (si todos coinciden); la carga, sólo
   del requisito nuevo `carga_rodamiento_n` (P equivalente por rodamiento). Sin ella, aviso que lo
   dice («L10 no calculable sin inventarla») y SIN_EVALUAR. Requisitos nuevos `rpm_salida` y
   `carga_rodamiento_n` (numéricos); docstring de `set_requirements`.
4. **Funciones**: `funciones` en `set_requirements` es 400 que apunta a la tool NUEVA
   `set_functions` (`PUT /api/funciones`, que ya existía sin tool). El validador acepta además la
   forma {funcion: {…}} y los sinónimos que escribieron los modeladores (`alternativas`,
   `alternativa`): los textos de la mezcladora y del tanque, que hoy rebotan, entran (4 funciones
   cada uno). La puerta lee `doc.funciones`, como antes; el texto viejo del requisito no se migra
   (puente implícito: no).
5. **El piso** (`calidad_seguridad.z_piso`): el apoyo más bajo de lo ANCLADO que no es tornillería
   (sin anclajes, lo más bajo que no es tornillería), también en la copia de la prueba de
   sobrantes. En la foto del elevador el piso ya estaba en 0 (las sondas a la cadena entran por el
   piso a z = 0, por debajo de la máquina: llegan a ≈ 190 mm del suelo, peligro real); el −25 del
   modelador sale de una revisión con anclajes bajo la losa, como los −70 de la mezcladora.
6. **El acople y la salida del motorreductor** (`library/seguridad/transmision_rigida.py`,
   `services/calidad_salidas.py`): gira el acople que une SIN soldar dos cuerpos que giran o uno con
   un motorreductor (el «Acople flexible» de la plantilla); la salida es peligro nuevo
   (`salida_motor`): donde un eje que gira cruza la caja de un motorreductor, puntos a r + 3 mm del
   eje, 1 mm afuera de la cara REAL de la caja (rayos contra sus sólidos), con la caja como
   «forman» (no estrecha el haz). En las tres máquinas el cubo del eje hueco del NMRV queda
   expuesto en la mezcladora (lado libre: el eje termina 20 mm dentro del cubo) y en el tanque
   (arriba y bajo la caja); en el elevador está resguardado. Defecto sembrado nuevo
   `acople_sin_guarda` (la faja testigo sin su «Guarda del acople»: FALLA).
7. **Poses de reposo: propuesta, no implementado.** Medido (una corrida de `controles_seguridad`
   sobre la copia posada por pose): mezcladora con la tapa de carga a 95° 11,5 s (las paletas al
   alcance: 2 sondas al extremo del eje), compuerta a 200 mm 11,3 s (nada cambia); tanque con la
   boca a 100° 7,5 s (1 sonda al acople); elevador con la plataforma arriba 54,4 s (cadenas 10 → 15
   y 15 → 22). Cada pose cuesta una corrida entera y en dos de las tres lo que aparece es una tapa
   ENCLAVADA abierta: con ella abierta la máquina para (ISO 14119), no es peligro. Propuesta para su
   fase: poses = las de reposo de `delivery_poses` más los extremos de las juntas ACCIONADAS que no
   giran (cilindros, plataformas); se excluye la pose con una junta de servicio abierta si su
   cuerpo lleva la lengüeta de un enclavamiento (lo verifica la fase de mandos de seguridad); y se
   re-trazan sólo los peligros a ≤ 1080 mm de lo que la pose movió (la localidad de D7).

`VERSION_REGISTRO` 8 → 9. Testigos re-congelados: sólo cambió la versión, y la firma de la faja
porque su `.apolo` se rehízo sin la justificación de la «Guarda del acople» (ahora la pide el
acople: no sobra); ningún veredicto por ítem se movió. Golden MCP re-congelado: la tool
`set_functions` (y su 400) y el docstring de `set_requirements`.

Decisiones tomadas en la implementación (vetables):
- **Accionada sin mirar nombres**: continua, escenario, actuador padre o unido al cuerpo hijo. Un
  brazo motorizado declarado `giratoria` sin escenario ni actuador modelado sale de servicio (falso
  negativo posible): se cierra declarando su escenario o modelando el actuador.
- **Resguardo por las sondas RECTAS**: las del brazo doblado no dicen qué las paró, así que una
  guarda que sólo para el brazo doblado no se juzga (si es soldada, pasa). Conservador en el
  sentido de no frenar; la prueba de sobrantes sigue usando `revisar_guardas` entero (lo
  conservador ahí es llamarla necesaria).
- **La L10 fuera de un transportador no usa `carga_kg`**: es el producto (550 kg de líquido en el
  tanque), no lo que carga el rodamiento de un agitador; repartirla entre sus rodamientos daba,
  en una cuenta a mano, del orden de 10⁴ h: una FALLA falsa. Sin `carga_rodamiento_n`, SIN_EVALUAR.
- **La salida del motorreductor se busca en la cara real**: la caja del NMRV incluye el motor
  cruzado al eje, que sobresale del reductor. Un eje que termina dentro del cubo deja el cubo
  abierto: peligro; un eje que lo atraviesa también (gira junto a la cara). La «Tapa del eje hueco
  del reductor» que la F3 halló sobrante en la faja de motor central debería pedirla ahora este
  peligro (no medido: esa faja no está en esta máquina; lo verá la F4).

### F3c (2026-10-27): lo que la puerta no veía en esas tres máquinas

Medido en SÓLO LECTURA sobre fotos de las bases (tanque: corrección final, 03:13; mezcladora,
03:33; elevador, 03:29; las siguen usando otros procesos) y la revisión 4 del tanque («antes de
corrección 3: uniones atornilladas con sus agujeros»), con `items_funcion_mecanica`,
`tool_access_report`, los hechos y `controles_seguridad` (sin ERC), antes (`main`) y después (en la
mezcladora y el elevador el «antes» de agarre, acceso, factor y flecha es la foto de 10 min antes,
la de las 03:21–03:22; las sondas, la misma foto):

| | mezcladora (219 sólidos) | tanque (121) | elevador (295) |
|---|---|---|---|
| `union.agujeros` (nuevo) | FALLA: 17 de 49 uniones (las UCF207 sobre los testeros, la brida del cilindro sobre la caja, la ménsula de reacción, los sellos, el panel neumático, bisagras y lengüetas de la tapa, soportes de interruptores); 5 de 5 anclajes OK | OK: 21 de 21 y 5 de 5 anclajes. Revisión 4: FALLA 8 de 18 (portasello, chumacera ↔ puente, lengüeta, bisagras, prisionero de la hélice) y las 5 placas de piso sin taladros | FALLA: 22 de 46 (respaldo de la plataforma, brazo de reacción, regleta de sensores sin los M18, bisagras de las puertas, actuadores) y 10 de 10 anclajes (placas con un Ø8,5 para M12 químicos) |
| agarre · retención · largo | OK (56) → OK | SIN_EVALUAR (8 de 12: los espárragos) → OK (12) | SIN_EVALUAR → SIN_EVALUAR: 12 «Perno de amarre …» sin cabeza modelada (el motivo ahora lo dice); los «Tope elástico … con espárrago» ya no son tornillería |
| `union.acceso_herramienta` | OK (92) → OK | SIN_EVALUAR (8 espárragos) → OK (16; los espárragos los aprieta su tuerca) | SIN_EVALUAR 22 → 20 (pernos sin cabeza, resortes y tuercas sin hexágono modelado) |
| `accionamiento.factor_servicio` | SIN_EVALUAR «declara carga y largo de paquete» → SIN_EVALUAR «declara `potencia_absorbida_kw` o `par_salida_nm`» | igual; con los 105 W de sus notas: FS = 0,55·0,75/0,105 = 3,93 ≥ 1,25, OK | igual que la mezcladora |
| `estructura.flecha` | OK (2 vigas; el detector contaba 9) | SIN_EVALUAR (contaba 7 «vigas»: rieles DIN y canaletas del tablero) → NO_APLICA | OK (6; contaba 16) |
| `riesgos.partes_moviles` | FALLA: 6 sondas a la salida del NMRV con sr 0,2–1,5 mm → OK: sus 4 objetivos caen en la rendija de 2,0 mm entre la «Chumacera lado motor» y la caja | OK → OK (3 peligros) | FALLA → FALLA (cadenas 10 y 15 sondas, eje loco 5: sin cambio, peligros reales) |
| candidatas a sobrante | 35 (31 «agregadas»: los aparatos del tablero rehecho al final) → 4 (0) | 14 → 14 | 41 (39) → 8 (6) |
| segundos (mecánica) | 5,1 → 3,8 | 2,9 → 3,0 | 9,7 → 9,3 |

Qué entró, por punto:
1. **`union.agujeros`** (ítem general nuevo, familia montaje; `library/calidad/agujeros.py`, medido
   por `services/calidad_agujeros.py`): cada pieza a medida de un `fasten kind=perno` del modelador
   (comandos `fasten` y `join_bolted`) tiene ≥ `qty` agujeros —caras cilíndricas INTERIORES,
   coaxiales = uno— de Ø entre 0,75·d y 1,6·d + 2 mm en la intersección de las cajas de las dos
   piezas; un anclaje con pernos en su nota («4 pernos de expansión M12», «2 tarugos M10», «anclajes
   químicos M12») los pide en su placa, tantos como dice la nota. `join_bolted` taladra: la ménsula testigo pasa.
   Defecto sembrado `placa_sin_agujeros`. Costo: una extracción de caras por pieza (≈ 0,1–0,4 s).
2. **El espárrago** (`library/esparrago.py`): rol anclado («Espárrago…», «Varilla roscada…») +
   vástago sin cabeza (sin hexágono, cilindros coaxiales de un Ø). Se mide desde su BASE hacia la
   punta donde va la tuerca (el sentido lo da la tuerca; sin ella, el extremo que apoya): cruza,
   retención con la tuerca (hilo fuera ≥ 2 pasos) y largo de la serie de espárragos. En el acceso de
   herramienta no se evalúa: lo aprieta su tuerca, que sí (`esparragos` en el reporte).
3. **Factor de servicio con lo declarado** (`library/engineering/servicio.py`,
   `engineering_rules.accionamiento_declarado`): sin transportador, regla «factor de servicio del
   accionamiento» = P·η / `potencia_absorbida_kw` o T_nominal / `par_salida_nm` (T de la ficha o de
   9550·P·η / rpm declaradas), contra el FS de su servicio: tabla AGMA por `tipo_carga` (uniforme |
   moderada | pesada) y `horas_dia` (≤ 3, ≤ 10, > 10), 1,25 sin servicio declarado. El umbral
   declarado vale también para la motorización de un transportador. Requisitos nuevos y docstring de
   `set_requirements` (golden: sólo `list_tools`).
4. **La flecha sin vigas**: el detector `vigas` de los hechos es `vigas_rules.detectar_vigas` (el
   criterio del control): NO_APLICA con el porqué.
5. **Holgura funcional** (`calidad_sondas.fuera_de_holguras`, punto del coordinador): un objetivo de
   ENGANCHE en el aire entre dos piezas a ≤ 4 mm sale de las sondas con su evidencia
   (`en_holgura`: punto, ancho, las dos piezas); si todos salen, el peligro es OK. La prueba de
   sobrantes lo vuelve a sondear si quita una de las dos paredes.
6. **Lo eléctrico no es «agregado»** (`calidad_sobrantes_candidatas.del_carril`, punto del
   coordinador): lo que dibuja un `layout_tablero`, las refs con ficha eléctrica, las piezas ligadas
   por `add_device` y las de rol eléctrico salen de las candidatas (b); una guarda sigue siendo (a).
   Las candidatas se mudaron a su módulo (el tope de 500 líneas).

`VERSION_REGISTRO` 9 → 10. Testigos re-congelados: suman `union.agujeros` (OK en los cuatro: en la
faja y los rodillos, nada que verificar o los anclajes de la plantilla con sus agujeros) y la
versión; ningún otro veredicto se movió.

Decisiones tomadas en la implementación (vetables):
- **Ítem propio, no dentro de `union.agarre`**: agarre mide la tornillería MODELADA; esto, lo
  DECLARADO que nadie modeló. Dos modos de falla, dos ítems.
- **Lo que no se juzga** (con su motivo en el insumo): catálogo y lo declarado «(compra…)» (el
  builder o el bloque a mano no siempre modelan los agujeros del fabricante: el sensor M18 de
  catálogo no, pero la regleta que lo recibe sí se juzga), tornillería y pasadores (rol anclado),
  cadena o banda, chapa perforada (la perforación no se modela: se lee del nombre), el eje de una
  unión con prisionero, la base sobre la que va soldado un espárrago (no la atraviesa), las uniones
  internas de una plantilla (las responde la plantilla) y las que dicen «sin perno» (cierres de
  palanca). «Punta roscada» = basta una pieza con el agujero.
- **El espárrago por el ROL**: la geometría de un espárrago es la de un pasador; el catálogo no los
  trae. «Perno …» sin cabeza modelada NO se lee como espárrago (el modelo está a medias y lo dice).
  «con espárrago» es mención (`lints._MENCION_RE`), como «p/ perno». La serie de largos (ISO 13918 /
  DIN 938) es criterio de compra, a confirmar con el proveedor; la varilla roscada se corta.
- **El factor de servicio no usa el `atasco`**: es una falla provocada para ver que la protección
  dispare; dimensionar contra él pediría un motor que nunca se protege. Ni `carga_kg` (el producto).
  La tabla de AGMA da 0,8 a ≤ 3 h/día de carga uniforme: el piso es 1,0 (criterio propio, más
  estricto: el par nominal de la ficha no se excede). Con varios motorreductores el requisito es de
  la máquina: aviso, SIN_EVALUAR (falta un requisito por motor).
- **Holgura ≤ 4 mm sólo en enganche**: por esa rendija el dedo no entra (ISO 13857 tabla 4 da 2 mm
  de penetración a la punta en e ≤ 4: toca el borde, no lo que gira adentro) y nada se arrastra
  (ISO 13854: 25 mm para el dedo). Una cuña o una cadena (atrapamiento) se abre hacia afuera: no se
  exime. Un punto dentro de un sólido no es rendija (la misma pieza a los dos lados).

**El costo de la puerta** (pedido del coordinador sobre su medición del elevador: 83–85 % de la
puerta en `diseno.sin_sobrantes`, el 92–94 % de eso sobre lo que dibuja `layout_tablero`):
7. **Memo de la geometría de masa** (`engineering/mass.memo_de_geometria`, abierto por
   `puerta_publicacion.reunir`): volumen, caja y COM de cada forma una vez por corrida, por
   `id(shape)` con `is`; el material y la masa se resuelven en cada llamada. ContextVar del hilo,
   vive lo que dura el `with`: fuera de la puerta, todo igual.
8. **El campo del brazo doblado una vez**: `controles_seguridad` deja en el `Contexto` su campo y su
   memo de nubes (`compartido`) y la prueba de sobrantes arranca de ellos (con lo ya quitado
   recalculado en su zona, `libre_sin`) en vez de re-teselar y rehacer el campo.
9. **`get_job` de la puerta resumido** (`tools/calidad.de_job`): como la tool; `detail="full"` da todo
   (golden: dos casos nuevos y los docstrings de `get_job` y `publication_gate`).

Medido en proceso (`reunir` + `evaluar`, gravedad dada por estable, sin marcha; código de `main`
contra el de la rama, las mismas fotos, una corrida cada uno, la PC sin otra suite):

| | mezcladora | tanque | elevador |
|---|---|---|---|
| puerta (pared / CPU) | 76,5 / 79,6 s → **18,5 / 20,4 s** | 20,1 / 21,1 s → **15,1 / 16,6 s** | 378,3 / 402,7 s → **60,8 / 73,9 s** |
| `sobrantes` | 62,1 s → 4,4 s | 9,2 s → 4,5 s | 322,2 s → 11,6 s |
| · candidatas (sobran) | 35 (29: el tablero) → 4 (1: «Tapa de ranura testero lado motor») | 14 (1) → 14 (1) | 41 (32) → 8 (2: los bujes antiaplastamiento de las orejas del tensor) |
| · ingeniería | 18,9 s (28 pruebas) → 0 | 1,8 s (2) → 0,2 s (2) | 201,5 s (32) → 2,8 s (2) |
| · codo | 40,2 s (30) → 3,9 s (2) | 6,8 s (2) → 3,7 s (2) | 50,8 s (29) → 0 |
| `fuentes.mecanica` · `memoria` | 3,8 · 0,9 s → 3,0 · 0,6 s | 1,7 · 0,9 s → 2,2 · < 0,5 s | 8,3 · 6,3 s → 3,0 · 3,6 s |
| payload completo (`get_job` ahora lo resume) | 31,0 → 30,4 kB | — | 52,2 → 58,5 kB (la evidencia de `union.agujeros`) |

Lo que más bajó es el punto 6 (el tablero ya no se prueba); el memo de masas se ve en la ingeniería
del tanque (1,8 → 0,2 s con las mismas 2 pruebas) y en `memoria`/`mecanica` del elevador. Queda
`fuentes.seguridad` (~35 s en el elevador: las sondas de F3).

**Propuesta, no implementada (riesgo alto): soltar `STATE_LOCK` entre candidatas.** La puerta
entera corre bajo el lock (el elevador lo tenía 6 min; ahora ~1 min). Soltarlo entre candidatas
exige: (a) tomar la `firma` del modelo al empezar y, al retomar el lock, abortar con 409 si cambió
(la puerta no da veredicto a medias); (b) que la copia superficial `doc_sin` no lea nada del
`Document` vivo después de soltar (hoy lee `doc.scene`, `doc.fasteners`, el catálogo y el manifest
en cada prueba: hay que congelarlos en la `Prueba` al empezar); (c) que el `Contexto` (campo,
sondas, memo de masas) no se comparta con otra corrida. Con 1 min de lock en la máquina más grande
medida, conviene esperar a que una máquina real lo pida.

Hallazgos fuera del alcance: en el elevador, 12 «Perno de amarre …» modelados como cilindros sin
cabeza y 8 tuercas y resortes sin hexágono siguen SIN_EVALUAR en agarre y acceso (es el modelo); las
17/22 uniones sin agujeros de la mezcladora y el elevador, y sus anclajes, son defectos reales que
sus modeladores tendrán que taladrar (o rehacer con `join_bolted`). Los «Bujes pasantes
antiaplastamiento» de las orejas del tensor del elevador salen sobrantes antes y después: sin
revisar (¿los pide algo que la puerta no mide, como el aplastamiento del tubo bajo la precarga?).


### F3d (2026-10-27): lo que la entrega no evaluó también se justifica

Medido en la mezcladora de paletas (base en SÓLO LECTURA, la usa otro proceso): `entrega.no_evaluado`
quedaba SIN_EVALUAR por «enclavamiento del resguardo: -B4 c361 … con su lengüeta c363 …: la hoja
del resguardo no tiene junta declarada: la apertura no se verifica» (la lengüeta va en el aro de
acople c362, suelto, con cierres de palanca). El modelador ya tenía `{regla: «enclavamiento del
resguardo», porque}` y `{regla, pieza: c361, porque}`: nada casaba porque
`puerta.no_aplica_justificado` no leía `justificadas` (sólo los tres hechos de `_JUSTIFICADOS`) y
la entrada llegaba como cadena suelta, sin regla ni piezas.

Qué entró:
- `no_aplica_justificado` lee `justificadas` (`justificadas.del_no_evaluado`): casa por el texto
  entero (el de `sin_justificar`, recortado a 300 como lo guarda el metadato), por la regla que da
  la entrega o por la SECCIÓN del texto (`justificadas.seccion`: lo que va antes del primer « (» o
  «: »). Con `pieza`, el criterio de D11: todas las piezas de la entrada. Un hecho de
  `_JUSTIFICADOS` sigue ganando; lo que tiene ítem propio (gravedad, acceso) sigue yendo allá. La
  evidencia lista cada justificación con su porqué; sin justificar, `como_justificar`
  (`[{regla, piezas?}]`), las piezas del ítem y el detalle dicen con qué regla.
- La entrega da, sólo si hay, `no_aplica_piezas: [{no_aplica, regla, piezas}]` (hoy: la apertura
  sin junta del enclavamiento, con el par interruptor + lengüeta); `no_aplica` sigue siendo la
  lista de textos de siempre.
- `VERSION_REGISTRO` 10 → 11. Testigos re-congelados: sólo la versión. Golden MCP: el docstring de
  `set_justifications` (sólo `list_tools`).
- Defecto sembrado sobre un modelo real (`test_enclavamiento_resguardo::test_la_apertura_sin_junta_
  se_justifica_por_escrito_en_la_puerta`: SIN_EVALUAR; justificada por la regla o por el par, OK;
  por una sola pieza del par, SIN_EVALUAR). La exención de `entrega.no_evaluado` en
  `test_defectos_sembrados` lo cita (ningún testigo lleva interruptor de resguardo).

Mezcladora, antes → después (`delivery_inputs` + `delivery_report` sin gravedad +
`no_aplica_justificado` con las `justificadas` de la base): SIN_EVALUAR → **OK** («1 chequeo(s) no
aplican, cada uno con su porqué», por la entrada `{regla: «enclavamiento del resguardo»}`). Con
sólo `{regla, pieza: c361}` sigue SIN_EVALUAR y el detalle pide c361 y c363.

Decisiones tomadas en la implementación (vetables):
- **Con `pieza`, todas las de la entrada** (D11), también en el par del enclavamiento: el
  interruptor solo no la cubre. Lo que pide es una línea más (`pieza: c363`) y la regla general
  sigue disponible; aflojarlo aquí abriría la puerta a que una pieza justifique entradas ajenas.
- **La sección cubre todas sus entradas**, como una `regla` sin `pieza` cubre todo aviso de esa
  regla: una justificación escrita por «enclavamiento del resguardo» vale para cada interruptor
  sin junta. Para acotarla, el par.
- **Sin cambiar la forma de `no_aplica`** (lista de textos que leen la UI, la tool y los tests): las
  piezas viajan en una clave aparte que sólo aparece si hay.
