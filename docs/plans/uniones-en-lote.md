---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: Sólo el plan; nada construido. Espera saldo de tokens (Mario, 2026-10-10)
descripcion: El agente declara de una vez cómo se une cada pieza repetida («cada eje a su larguero») y la detección automática ya no suelda cadenas a la guarda
---

# Declarar las uniones de las piezas repetidas en una sola orden

## Estado y origen

En la piloto (proyecto 2), `declare_structure` declaró tipos de unión falsos (cadenas soldadas a
la guarda, entre otros). Hubo que borrar 419 comandos (c105–c523) por `POST
/api/commands/remove` y declarar a mano 226 uniones con un script REST que expandía los ids de
patrón uno por uno (`c57_1`…`c57_19`). Fue la parte más cara del modelado. Mario preguntó
«¿tienes mejoras para el MCP?»; esta fue la 4.

## El problema / lo que hay hoy

- `fasten` une dos piezas; una máquina con 20 rodillos × 10 uniones = 200 `fasten`.
- La autodetección decide el TIPO por contacto: lo que gira y toca algo sale «soldadura».
- El patrón (`c57_k`) no se puede nombrar como conjunto en una unión.

## Decisiones (para vetar)

- **D1. `fasten` acepta PATRONES en `a` y `b`**: `a: "c57"` (raíz del patrón) + `b: "c9"` =
  una unión por instancia; `a` y `b` del mismo patrón se emparejan por índice (eje k ↔ tuerca k).
  Un solo comando en el log, que se expande al regenerar (sigue el patrón cuando cambia
  `n_rod`). Un log viejo no cambia: el modo nuevo sólo se activa con una raíz de patrón.
- **D2. La autodetección no suelda lo que gira**: una pieza con junta, o de catálogo de
  transmisión (cadena, piñón, rodamiento), nunca recibe `soldadura`; propone `contacto` o
  `perno` y lo marca `a_revisar`.
- **D3. `declare_structure` en modo propuesta**: devuelve la lista sin aplicarla (`aplicar:
  false` por defecto en el MCP); el agente la corrige y la aplica en un lote.

## Fases

- **F0 (S, sólo lectura)**: sobre una copia del proyecto 2 sin uniones, contar cuántas propone
  hoy la autodetección y cuántas son de tipo falso.
- **F1 (M, `commands` + `assembly`)**: D1 con tests (cambiar `n_rod` re-expande).
- **F2 (S, `assembly`)**: D2.
- **F3 (S, `api` + MCP + golden)**: D3.
- **F4 (S, verificación)**: redeclarar la estructura del proyecto 2 con < 30 órdenes.

## Lo que este plan NO hace

- No cambia `ground` ni la puerta de entrega.

## Riesgos

- Emparejar por índice patrones de distinto largo → error accionable con los dos conteos.

## Bitácora
