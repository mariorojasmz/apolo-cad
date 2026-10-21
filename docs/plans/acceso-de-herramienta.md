---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: sin pendientes de código: F3 verificada por MCP (2026-10-21): piloto VERDE 40/40 en ~53 s y ROJO al simular el ala de la rev. 3; la rev. 3 real no se re-midió (la copia no trae revisiones)
descripcion: Apolo avisa cuando una tuerca o un perno no se puede apretar porque la llave no entra
---

# Apolo avisa si la llave no entra

## Estado y origen

Mario (2026-10-09), mirando la piloto (proyecto 2): «las tuercas "Tuerca del eje" están bastante
cerca a la parte superior del larguero, tienen juego para girar?, ya que se tiene que ajustar y
desajustar con llave». Medido: 2.5 mm entre la tuerca M12 (s = 18) y el ala del UPN-100; una copa
de 18 mm necesita ~12.5 mm desde el eje y había 11.5. La máquina estaba en VERDE. Se corrigió
cambiando a ángulo L 75×6 (revisión 4). Parte de [revision-de-taller](revision-de-taller.md).

## El problema / lo que hay hoy

- `design/guidelines.py:54-59` pide «espacio para la herramienta», pero ningún chequeo lo mide.
- `check_interference` sólo ve sólidos que existen; el espacio que necesita una llave no es un
  sólido del modelo.
- La tornillería del catálogo ya sabe su llave: `109_tuercas.yaml` (`across_flats`) y
  `engineering/bolts.py` (`wrench_size_mm`).

## Decisiones (para vetar)

- **D1. Volumen de herramienta por fijador**: para cada tuerca o cabeza de perno (catálogo o
  `_is_bolt` por nombre) se arma un sólido FANTASMA coaxial: copa = cilindro Ø(s + 2·pared) ×
  (altura de la tuerca + 15 mm) hacia afuera; anillo = toro plano Ø(1.5·s) en el plano de la tuerca;
  Allen = cilindro Ø(llave) coaxial. Las medidas de pared y anillo salen de una tabla (ISO 2725 /
  DIN 3124 para copas; DIN 3113 para combinadas), no de constantes sueltas.
- **D2. Basta UNA herramienta libre** (copa O anillo O boca en algún ángulo de 60°): el chequeo
  pasa si alguna no interfiere con nada salvo su propia tuerca, perno y la pieza donde asienta.
- **D3. Severidad**: ninguna herramienta libre = ROJO en `delivery_check` (no se puede armar);
  sólo la boca libre = AVISO. La colisión con un sólido que GIRA cuenta igual (se arma parado).
- **D4. Cálculo en `library`** (puro: recibe shapes y datos de catálogo) y se llama desde
  `services/delivery`; nada nuevo en el MCP salvo el resultado dentro de `delivery_check`.

## Alternativas descartadas

- Una regla geométrica tipo «≥ 12 mm del eje a cualquier ala»: no ve el caso real (alas,
  piñones, piezas vecinas) y depende del tamaño de rosca.
- Simular la llave girando: caro; D2 con unos pocos ángulos alcanza.

## Fases

- **F0 (S, sólo lectura)**: medir en el proyecto 2 revisión 3 (UPN) y revisión 4 (ángulo) con un
  script: la 3 debe dar ROJO en las 40 tuercas y la 4, verde. Medir el costo (40 tuercas).
- **F1 (M, `library`)**: tabla de herramientas + constructor de fantasmas + chequeo, con tests
  (tuerca libre, tuerca bajo un ala, tuerca junto a un piñón).
- **F2 (S, `services`/`library/delivery.py`)**: integrar en la puerta de entrega con D3.
- **F3 (S, verificación)**: re-correr F0 por MCP; anotar los números en la bitácora.

## Lo que este plan NO hace

- No revisa si cabe la MANO ni la secuencia de montaje (eso queda para el revisor de taller).
- No cubre soldaduras inaccesibles.

## Riesgos

- Máquinas con miles de pernos → acotar a pernos con vecinos a < 50 mm (bbox) antes de la
  booleana; medir en F0.
- Falsos rojos con herraje modelado como caja → sólo se evalúan fijadores reconocidos.

## Bitácora

### F0 (2026-10-19)

- El piloto está en la base local como proyecto **74** (el «proyecto 2» del origen); sus
  revisiones 3 (UPN-100) y 4 (ángulo L 75×6) son las filas **124** y **125** de `revisions`.
  Script sólo lectura: `scripts/f0_acceso_herramienta.py --db data\apolo.db 124 125`.
- **124 (UPN-100): ROJO en las 40/40 «Tuerca del eje» M12** (ninguna copa, anillo ni boca);
  estorban «Larguero (+Y)» y «Larguero (−Y)», y nada más. **125 (L 75×6): las 40/40 libres con
  copa**.
- Costo, con la máquina cargada por otras suites (Windows): chequeo **9.6 s** en la 124 (todas
  rojas: prueba todas las herramientas) y **4.8 s** en la 125 (para en la copa), 40 tuercas,
  201 sólidos; la carga del documento, 7.0 s y 2.6 s. Referencia: `delivery_inputs` SIN este
  chequeo ya tarda ~53 s en la 125 (interferencias de 201 sólidos) → la puerta crece ~10-20 %.
- Lo medido por el camino: la 1.ª versión tardaba 33 s en la 124 (booleanas de ~47 ms contra el
  larguero entero de 4 m y una boca poligonizada de ~135 ms). Recortar cada vecino a la caja de
  alcance del fijador: de una vez, 29 s sólo en recortes (las cadenas); perezoso, ±10 % según la
  revisión → descartado por no pagar su complejidad. Lo que quedó: sectores = anillo exacto ∩/−
  cuña de 3 caras, fantasmas memoizados por corrida, bbox no óptima, cada herramienta para en
  el primer choque y la boca prueba primero lo COMÚN a sus 6 direcciones.
- No es test: carga + chequeo ~10-20 s por revisión y la BD no está en el repo (queda el script).

### F1 (2026-10-19)

- `library/herramientas.py` (tabla D1), `library/fijadores_geom.py` (reconocimiento),
  `library/fantasmas_herramienta.py` (fantasmas) y `library/acceso_herramienta.py`
  (`tool_access_report(scene, catalog=)`, puro, None sin tornillería de llave).
- Decisiones tomadas en la implementación (para vetar):
  - El fijador se reconoce del SÓLIDO (3 pares de caras paralelas a 60°, ⟂ a un eje; exterior
    o interior con un clasificador de sólido), no del catálogo: sirve igual a la tuerca de
    catálogo rotada, al perno de `join_bolted`, a la tornillería a medida y a un STEP. Lo que no
    tiene hexágono reconocible (o tiene una llave fuera de tabla) queda «no evaluado» →
    `no_aplica`, nunca verde. Candidatos: catálogo tuercas/pernos/tornillería o `_is_bolt` por
    nombre; los tirafondos (`tornilleria_madera`) no se aprietan con llave.
  - D2 «salvo la pieza donde asienta»: **no se excluye la pieza de asiento entera**. En el
    piloto el ala que estorba es del MISMO UPN contra el que asienta la tuerca: excluirlo daba
    verde falso. En su lugar todo fantasma arranca a 1 mm de la cara de asiento. Sí se excluye lo
    que pasa por el agujero (sonda Ø 0.4·s: su perno o su eje).
  - Lado de la tuerca: una sonda anular de 1 mm junto a cada cara decide dónde asienta; sin
    asiento visible la copa se prueba por los dos lados; con asiento en los dos, no hay copa.
  - **La boca y el mango barren ±15°** (giro mínimo con volteo): la boca es el anillo Ø b
    menos la parte de la abertura que sigue libre al girar, y el mango, el sector que barre.
    Con el ala del piloto el resultado no cambia sin el barrido (medido: el ala corta el anillo
    Ø41 en ±56° y la abertura sólo deja ±27°), pero sin él una llave que calza y no gira pasaría.
    El anillo lleva además el arranque del mango (largo = s) en alguna de 12 posiciones (12
    puntas); la boca, en las 6 normales de cara. La mano y el resto del mango quedan fuera (§ Lo
    que este plan NO hace).
  - Tabla: envolventes de referencia de catálogo comercial redondeadas hacia arriba, del orden
    de ISO 2725-1 / DIN 3124 (copas), DIN 3113 (combinadas) e ISO 2936 (Allen); no es copia de
    la norma. M12 (s 18): copa Ø25 (12.5 desde el eje, el número del origen), anillo Ø27.5.
  - Allen: el brazo corto de la L, coaxial (sin la copa con punta Allen).
  - No filtra por `visible` (ocultar es estado de vista); guías y superficies no estorban.
- Tests `tests/test_acceso_herramienta.py` (14): tabla; reconocimiento (tuerca rotada ×4,
  cabeza hex, Allen, cilindro/caja sin hexágono); tuerca libre (copa); **tuerca bajo un ala**
  (ala a 11.5 mm del eje: rojo, estorba sólo el ala; a 14 mm: copa); **tuerca junto a un piñón**
  (PINON-ASA40-1-Z15 con la punta a 0.4 mm de las esquinas: rojo; a 30 mm: copa); sólo boca
  (pasador en la abertura: aviso); cabeza de perno DIN 933 bajo un ala.

### F2 (2026-10-19)

- `delivery_report(acceso_herramienta=)`, sección 8 (D3): ninguna herramienta libre →
  bloqueante «acceso de herramienta · la llave no entra» (piezas + qué estorba); sólo boca →
  aviso «acceso de herramienta · sólo llave de boca»; no evaluados → `no_aplica`; todo libre →
  ok «acceso de herramienta (N fijador(es))». `services/delivery_inputs` lo pasa sólo si hay
  tornillería de llave: sin ella, los kwargs y el semáforo de siempre (test).
- Tests `tests/test_acceso_entrega.py` (7): agregador (None = idéntico, rojo, amarillo, verde,
  no evaluados), servicio (sin tornillería = kwargs de siempre; tuerca bajo ala = rojo con el
  nombre) y endpoint `POST /api/delivery-check`.
- Gate: pytest completo 2852 pasan + 1 saltado (+21 nuevos sobre los 2832), ruff limpio.
  Pendiente F3: re-correr F0 por MCP (`delivery_check` sobre el piloto) y anotar los números.

### F3 (2026-10-21): verificación por MCP — PASA CON OBSERVACIONES

**Cómo** (ola 5, 2026-10-21): una sesión NUEVA `claude -p --model opus` con sólo las tools `apolo-cad` + lectura del repo, contra una API de la flota en :8100 con el proyecto 78 (copia de la piloto 74). Una sesión para cinco verificaciones: 53 min, 114 turnos, USD 5,28.
- `delivery_check`: VERDE, acceso de herramienta 40 fijadores, 0 sin acceso, ~53 s (la tool no informa su tiempo).
- La copia no trae revisiones: la rev. 3 (40/40 rojas) se simuló con una placa de 6 mm a 11,5 mm de la tuerca c97 → ROJO «1 tuerca… estorban: Ala simulada UPN» en ~46 s.
