---
estado: implementado   # implementado | en curso | sin verificar | descartado
nota: F1 mergeada y F2 verificada por MCP el 2026-10-21 (las tres uniones se montan); fricción chica al backlog
descripcion: Atornillar una pieza a un tubo cerrado, a una C de chapa o a madera da una unión que se puede montar: la fijación correcta, el largo por el espesor real y la tuerca del lado que se alcanza
---

# Atornillar a un perfil hueco o a madera da una unión que se puede montar

## Estado y origen

Lo halló la F4 de
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

### F1 — criterio de taller en `join_bolted` (2026-10-21)

- **Cómo regenera un log viejo** (Riesgos): campo OCULTO `criterio` (fuera del JSON Schema; ni
  la UI ni el agente lo eligen). Sin él → 1 = V6.5b/c tal cual (`exec_union._criterio_1`). Todo
  comando NUEVO nace con 2 por un **sello de entrada** (`CommandSpec.al_crear`, llamado desde
  `Document._append_record` vía `doc/sello.py`); el replay y los edits no sellan. Así el log viejo
  conserva params, firma y geometría: **sin `version` nueva ni bump de `GEOM_CACHE_EPOCH`**
  (sólo la huella D11). Medido: el mismo log (tubo + placa y C + placa, M6) regenerado con el
  código de `main` y con el de la rama da el MISMO volcado (nombres, refs, volúmenes, cajas y
  fijadores): `Perno M6×65` por la caja en los dos casos, como lo vio F4. Los YAML nuevos sólo
  agregan refs: ninguna geometría cacheada cambia.
- **D1** (`union_taller.py` + `kernel/rayo.py`): por cada punto del patrón, una varilla de
  0,1 mm intersecada con cada pieza da los tramos de material. Base = la más gruesa en el eje
  (empate → `a`). Perfil cerrado = el rayo vuelve a entrar en la base; obstáculo = otra pieza a
  menos de tuerca + 3 filetes + 15 mm (el largo libre de la copa) detrás de la pared. Ciega =
  remache DIN 7337 / ISO 15983 (`112_fijacion_ciega.yaml`, M6→Ø4.8, M8→Ø6.4), taladro sólo de la
  pared cercana. Tubo HSS 2″×2″×3,2 + placa: `Remache ciego Ø4.8×10` (antes M6×65 por las dos
  paredes).
- **D2/D3**: agarre = espesor de la pieza agregada + el de la pared que toca; L ≥ agarre + m +
  2·paso. C de 3 mm + placa de 1,5: **M6×12** (antes M6×65), cabeza bajo la placa, tuerca contra
  la cara interior del alma, con la placa a cualquier lado (`a`/`b` en los dos órdenes).
- **D4**: `madera` (oculto) = las piezas que eran de madera al crear la unión (override →
  catálogo → nombre con la guarda del vertical: `materials.resolve_material_vertical`, ahora
  también de la apariencia). Base de madera → DIN 571 (`113_tirafondos_hex.yaml`), sin tuerca,
  pretaladro ≈ 0,7·d; tablero de 18 + placa de 1,5: `Tornillo Ø6×16` (penetración 14,5 ≥ 2/3·16 y
  la punta a 3,5 mm de la cara de atrás). Entre los largos válidos, el más corto con ≥ 6·d dentro
  o, si la madera no da, el más largo.
- **D5** (`services/delivery_inputs.declarada_por_join_bolted`): la tornillería de un
  `join_bolted` con su fijador declarado no entra a «tornillería sin unión declarada»; un perno
  suelto sí sigue avisando.
- **D6** (`batch.py`): `check_refs` revisa los `$k` antes de tocar el documento; `$0` → «los
  resultados se numeran desde $1 (el primer comando del lote)», fuera de rango → el total del
  lote. El mensaje viejo decía «este lote tiene N» con N = las acciones ya procesadas (0 en la
  primera). `mcp_server.py` no se tocó.
- **Acceso de herramienta ok en las tres**: el DIN 571 (`llave: true`) entra como tornillería de
  llave; el remache (sin hexágono) se reconoce por su cilindro mayor y se le cruza la remachadora
  (nariz Ø16 × 25 + cabezal Ø32 hasta 120 mm, criterio de diseño en `herramientas.py`).
- **Tiempos** (mediana de 3, patrón 2×2, sólo el `execute`): tubo 179 → 272 ms, C 176 → 314 ms,
  madera 124 → 325 ms (criterio 1 → 2): los rayos y los asientos reales cuestan ~0,1–0,2 s.
- **Decisiones fuera de la letra**: (1) no hay tuerca remachable ni autorroscante: el remache
  cubre M6–M8 y cualquier agarre ≤ 30 − 0,7·d; M10+ sin acceso por detrás = error que dice qué
  hacer (una tuerca remachable necesita avellanar la placa, y un autorroscante ISO 7049 no pasa de
  Ø6,3). (2) La fijación ciega y el tornillo para madera declaran el fijador `perno` con `size`
  None y `fijacion` = su nombre: el chequeo de pernos M no les calcula una capacidad que no
  tienen. (3) El material se lee al CREAR la unión: cambiarlo después no la cambia (hay que
  recrearla); `preview` pasa `vertical` y `scene` al clon para sellar igual. (4) Madera agregada
  sobre una base sin acceso → error (un remache no sujeta madera).
- **Tests**: `tests/test_union_en_perfil_hueco.py` (18): uno o más por D sobre tubo HSS, C de
  3 mm, tablero y placa de 1,5; la puerta sin aviso y el acceso de herramienta ok en las tres; el
  log viejo byte a byte y su edit sin sellar; criterio fuera del schema; la vista previa. Los
  conteos de catálogo pasan de 362 a 370 refs. Suite completa verde.

### F2 (2026-10-21): verificación por MCP — las tres uniones se montan

La misma tarea de varias-maquinas F4 (placa de identificación en el lado de operación), con tres
`claude -p --model opus` a la vez en la laptop y las APIs en el escritorio (túnel SSH, copia de la
base): 101 s de pared, 2,30 USD, cero `database is locked`.

| máquina | fijación que eligió `join_bolted` | se monta |
|---|---|---|
| faja 38 (tubo cerrado) | remache ciego Ø4,8×8 DIN 7337: atraviesa 4,5 mm y sobran 3,4 adentro; cabeza del lado de la placa | sí (antes, cabeza dentro del tubo) |
| puerta 28 (madera) | tornillo para madera Ø6×40 DIN 571, sin tuerca: 38,5 mm dentro, sin asomar | sí, una vez declarada madera la jamba |
| faja 72 (C de chapa) | M6×12 DIN 933 + DIN 934: atraviesa 4,5 mm, la tuerca dentro de la C con acceso | sí (antes M6×60), puerta VERDE |

**Fricción que queda** (al [backlog](../backlog.md)):
- **`$0`.** Los tres modeladores volvieron a usar `$0`; ahora el 400 explica que la numeración
  arranca en `$1`, pero se pierde un lote.
- **Jamba sin material.** Una jamba de puerta sin material declarado se trata como acero (perno
  pasante M6×80): el vertical carpintería no la tiñe madera.
- **`measure`** no acepta la dirección «+Y».
- **`render_view`** con `zoom` 2,5 salió en blanco.
