---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: Sólo el plan; nada construido. Espera saldo de tokens (Mario, 2026-10-10)
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
