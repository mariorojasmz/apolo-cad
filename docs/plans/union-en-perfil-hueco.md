---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: contrato escrito el 2026-10-21 (hito J de docs/hitos.md) con lo que halló varias-maquinas F4; nada implementado
descripcion: Atornillar una pieza a un tubo cerrado, a una C de chapa o a madera da una unión que se puede montar: la fijación correcta, el largo por el espesor real y la tuerca del lado que se alcanza
---

# Atornillar a un perfil hueco o a madera da una unión que se puede montar

## Estado y origen

Hito J de [docs/hitos.md](../hitos.md). Lo halló la F4 de
[varias-maquinas-a-la-vez](varias-maquinas-a-la-vez.md) (§ Bitácora): tres modeladores pusieron la
misma placa de identificación con `join_bolted` en tres máquinas, y en las tres la unión salió mal.

## El problema / lo que hay hoy

`join_bolted` taladra las dos piezas, inserta perno + tuerca de catálogo y declara el fijador.
Supone dos chapas macizas que se alcanzan por los dos lados:
- **Tubo cerrado** (larguero de la faja 38): la cabeza del perno queda DENTRO del tubo. No se puede
  montar: no hay acceso a la cara interior.
- **C de chapa** (larguero de la 72): el largo sale del bbox del perfil (50 mm) y no del espesor
  del alma (3 mm), así que da M6×60.
- **El lado de la tuerca**: queda del lado visible de la placa, no del lado de atrás.
- **Madera** (la puerta 28): no ofrece tornillo para madera.
- **La puerta** avisa que los pernos que insertó el propio `join_bolted` «no tienen unión
  declarada».
- **`$k`**: empieza en `$1`; dos de tres modeladores usaron `$0` y el lote falló sin decir que se
  numera desde 1.

## Decisiones (para vetar)

- **D1. La fijación sigue al acceso.** Cuando la pieza base es un perfil cerrado (tubo
  rectangular, redondo o cuadrado) o no hay acceso del lado de atrás (medido con el mismo rayo del
  acceso de herramienta), `join_bolted` usa una fijación ciega del catálogo, en este orden:
  remache ciego, tuerca remachable o autorroscante. Si el catálogo no tiene ninguna para ese
  diámetro, se agrega la familia (YAML de catálogo, con norma: ISO 15983 / DIN 7337 para el remache
  ciego, ISO 7049 para el autorroscante). Con acceso, perno pasante como hoy.
- **D2. El largo sale del espesor real.** El grip es la suma de los espesores de material que el
  perno atraviesa a lo largo de su eje (rayo por el centro del taladro), no el bbox. Un alma de
  3 mm + una placa de 1,5 mm da M6×12 o el largo comercial siguiente que deje 2–3 hilos fuera de
  la tuerca.
- **D3. La tuerca va del lado de atrás.** La cabeza va del lado de la pieza que se agrega (la
  placa) y la tuerca del lado de la base, salvo que ese lado no tenga acceso (→ D1).
- **D4. Madera → tornillo para madera.** Si el material de la base es madera (el que ya decide
  `set_material`/el vertical carpintería), `join_bolted` usa tornillo para madera (DIN 571 o el del
  catálogo `tornilleria_madera`) sin tuerca, con el largo por D2 dentro de la madera ≥ 2/3 del
  tornillo.
- **D5. Lo que inserta `join_bolted` cuenta como declarado.** La puerta de entrega no avisa «sin
  unión declarada» sobre la tornillería que el mismo `join_bolted` insertó y declaró.
- **D6. `$k` dice desde dónde numera.** Un `$0` en un lote es 400 con «los resultados se numeran
  desde $1 (el primer comando del lote)».

## Alternativas descartadas

- **Pedirle al agente que elija la fijación**: el criterio de taller es de Apolo, no del modelador
  (raíz § Criterio de ingeniería por defecto).

## Fases

- **F1 (M, `commands` + `library` + `services`)**: D1–D6, con un test por D sobre piezas reales: un
  tubo rectangular, una C de chapa, un tablero de madera y una placa de 1,5 mm. Un log viejo con
  `join_bolted` regenera igual: los params nuevos tienen un default que reproduce lo de hoy, o la
  `version` sube con su decisión de caché.
- **F2 (S, verificación por MCP)**: repetir la tarea de la placa en las tres máquinas (varias-maquinas
  F4) y que las tres uniones se puedan montar.

## Lo que este plan NO hace

- No cambia `fasten` ni las uniones ya declaradas en logs viejos.
- No agrega tools.

## Riesgos

- **Un log viejo cambia de tornillería al regenerar.** Mitigación: la elección nueva sólo corre
  con la `version` nueva del executor, o con un param que el log viejo no tiene; el test lo cubre.

## Bitácora
