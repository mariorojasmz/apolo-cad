---
estado: en curso
nota: contrato escrito por Claude el 2026-10-23 como la parte pública del ajuste A7 de un plan de seguridad funcional fuera del núcleo (aprobado por Mario; las alternativas de ingeniería las decide Claude, vetables); F1 mergeada (ESTOP-40-2NC y su caja, RESG-2NC con lengüeta, RS-2C-24VDC; modelos resguardo y rele_seguridad; pareja verde/roja de categoría 3 en los tests; sin bump de epoch); F1b mergeada (la máquina viva abre y cierra el resguardo, muestra el relé y su «no rearma», y la falla del relé pide su salida); revisión de diseño a ciegas hecha; líneas de referencia corregidas el 2026-10-26 (setas de 1 y 2 NC, resguardo de 2 NC, relé de seguridad → Siemens 3SK1, variadores → Delta MS300 con STO; `VFD-1K5-220` a 7,5 A: bitácora «Cifras de fichas y líneas corregidas»); F2b hecha en la rama del worktree, sin mergear (la puerta de entrega verifica en el 3D que la lengüeta entre en la ranura con el resguardo cerrado y salga abierto: ROJO si no; `VERSION_BATERIA` 2 → 3); falta F2 (verifica con Mario)
descripcion: mandos para funciones de seguridad de dos canales en el catálogo y en la co-simulación: seta de dos NC, interruptor de resguardo con actuador separado y relé de seguridad
---

# Mandos de seguridad de dos canales

## Estado y origen

- Para probar una parada de emergencia o un resguardo de **categoría 3** (ISO 13849-1: una falla
  no pierde la función) hacen falta dos canales independientes, cada uno con su contacto. Hoy el
  catálogo no los tiene, así que la co-simulación sólo puede probar la categoría 1.
- La medición que lo mostró (2026-10-23): `ESTOP-40` tiene un solo NC (`93_mandos.yaml`, bornes
  11-12). En el tablero de prueba del núcleo (`tests/tablero_electrico.py`) ese NC alimenta S1 y S2
  del STO en paralelo: un contacto 11-12 pegado deja los dos canales con 24 V y la parada se
  pierde. No hay interruptor de resguardo (ISO 14119) ni relé de seguridad.
- Con [cosim-fallas](cosim-fallas.md) ya se puede pegar UN contacto (falla de red `pegado`, D3) y
  ver si la máquina para igual. Con estos mandos, la pareja verde/roja tiene sentido: un NC pegado
  en una seta de dos canales → la otra rama corta (verde); en la de un canal → no corta (rojo).
- El cálculo de la norma (MTTFd, DCavg, PL) y los datos de fiabilidad de cada ref NO van aquí:
  viven fuera del núcleo. Este plan sólo trae los aparatos y su comportamiento.

## Lo que hay hoy

Rutas relativas a `core/apolo/`, medidas sobre `1b0a8ff`.

- `ESTOP-40` y `ESTOP-40-CAJA` en `library/data/93_mandos.yaml`: un NC de apertura positiva, builder
  `seta_emergencia`, modelo de co-sim `seta` (`cosim/modelos/mandos.py`, actuador `<des>.mano`).
- Los mandos de puerta (`123_mandos_puerta.yaml`) declaran su modelo en el YAML (`modelo: {tipo:
  pulsador|selector, retorno, posiciones, cierra_en}`); los contactos siguen al actuador y la red
  los cierra en `RedNodal._cerrados`.
- Las fallas de mandos de cosim-fallas: `trabado` en seta, pulsador y selector; `pegado` y
  `abierto` en un contacto (red).
- El variador lee S1 y S2 del STO y corta con cualquiera de los dos (`cosim/modelos/variador.py`);
  no detecta la discrepancia entre canales (cosim-fallas D10).

## Decisiones (para vetar)

- **D1 — Seta de dos NC.** `ESTOP-40-2NC` (puerta) y `ESTOP-40-CAJA-2NC` (en caja, para la
  máquina), iguales a las de un NC salvo el segundo bloque: bornes 11-12 y 21-22, los dos de
  apertura positiva (IEC 60947-5-1 Anexo K, ISO 13850), mismo builder (el bloque extra alarga la
  profundidad trasera del marco de montaje: `tablero.puerta.detras_mm`). Mismo modelo `seta`: los
  dos contactos siguen a `<des>.mano` y cada uno es una RAMA propia de la red, así que `pegado`
  pega uno solo.
- **D2 — Interruptor de resguardo con actuador separado** (ISO 14119 tipo 2): `RESG-2NC` (cuerpo
  y lengüeta), 2 NC de apertura positiva 11-12 y 21-22 que están CERRADOS con el resguardo cerrado
  (lengüeta adentro). Modelo de co-sim nuevo `resguardo`: actuador `<des>.cerrado` (bool), acciones
  `abrir` y `cerrar`; fallas `trabado` (el mecanismo no sigue a la lengüeta) y las de red de cada
  contacto. Se monta en la estructura (no en la puerta del tablero): su `montaje` y su marco
  siguen A3 de V8.5. Builder propio (cuerpo con la ranura y la lengüeta separada, para que el
  agente la ponga en la hoja del resguardo).
- **D3 — Relé de seguridad** `RS-2C-24VDC`: dos canales de entrada (S11-S12, S21-S22), rearme
  vigilado (S33-S34, actúa al SOLTAR el pulsador), tres NA de seguridad (13-14, 23-24, 33-34) y
  una salida de señal. Modelo `rele_seguridad`:
  - las salidas cierran sólo si los dos canales están cerrados y llega el flanco del rearme;
  - abren en cuanto abre cualquier canal;
  - no vuelven a cerrar hasta que los DOS canales hayan abierto y cerrado otra vez (así un canal
    pegado se nota en el ciclo siguiente: el relé no rearma). Es el comportamiento que publica
    la línea citada; la simultaneidad con tiempo (discrepancia en ms) NO se modela (cosim-fallas
    D10) y va como hipótesis del resultado.
  - fallas: `salida_pegada` (un NA de seguridad soldado, {salida}) y `detenido` (salidas a 0).
- **D4 — Genéricos, como el resto del catálogo**: `specs.linea_referencia` con el orden de una
  línea comercial, `cotas_verificadas: false`, costo de referencia. Sin datos de fiabilidad (B10d,
  PFHd): no son del núcleo.
- **D5 — Vigencia.** Refs, builder y modelos NUEVOS: no cambian la geometría ni la traza de nada
  existente. Sin bump de `GEOM_CACHE_EPOCH` (sólo se agrega YAML y un builder nuevo; se verifica
  que la huella de geometría de las refs de antes no cambie) ni de `COSIM_EPOCH` (los escenarios
  sin estos aparatos dan la misma huella, como en cosim-fallas D8).
- **D6 — Un tablero de prueba de categoría 3** en los tests: la faja de prueba con `ESTOP-40-2NC`,
  11-12 a S1 y 21-22 a S2 del STO (sin el paralelo de hoy), y otro con resguardo + relé de
  seguridad. Son los casos que la verificación de un plan de seguridad usa como pareja verde/roja.

## Alternativas descartadas

- **Un solo bloque NC con dos «canales» lógicos**: no es lo que se compra ni lo que se cablea; un
  contacto pegado tiene que afectar a UN canal físico.
- **Modelar la discrepancia en ms del relé**: sin ficha que la publique por ref, sería inventar
  (regla de [cosim](../../core/apolo/cosim/CLAUDE.md)); la verificación del rearme (los dos
  canales tienen que abrir y cerrar) sí es comportamiento publicado.
- **Interruptor de resguardo con bloqueo (ISO 14119 con solenoide)**: no lo pide ninguna función
  hoy; se agrega si una lo pide.

## Fases

- **F1 — Catálogo, builder y modelos** (`library`, `cosim` · M · ≈ 50 min): D1–D6. Tests: cada ref
  construye y entra en la colocación del tablero (V8.5); cada modelo con su gemelo (los dos
  canales; el rearme; un canal pegado que no deja rearmar); la faja de prueba de categoría 3:
  un NC pegado → para igual (verde); el de un canal con su NC pegado → no para (rojo); la huella
  de los escenarios de antes sin cambio.
- **F2b — ¿Entra la lengüeta?** (`library`, `services` · S): la puerta de entrega mide en el 3D
  que, con el resguardo cerrado, la lengüeta esté en la ranura de su interruptor y, con la junta de
  la hoja en su otro extremo, fuera. Nace de dos máquinas del 2026-10-27 con la lengüeta fuera y
  todo en verde (bitácora).
- **F2 — Verifica** (S): en la máquina viva, sobre una copia de la faja piloto recableada con la
  seta de dos NC, simular el NC pegado y apretar la seta. Mario lo ve.

## Lo que este plan NO hace

- El cálculo de ISO 13849 (PL, MTTFd, DCavg, CCF) ni datos de fiabilidad.
- Cortinas de luz, alfombras, mandos a dos manos (otro plan si una función los pide).
- Detectar la discrepancia entre canales en el variador.

## Riesgos

| riesgo | mitigación |
|---|---|
| La seta de dos NC cambia la de un NC | refs nuevas; las de hoy no se tocan (D1, D5) |
| El relé se modela con un comportamiento que la línea citada no tiene | sólo lo publicado (rearme vigilado, los dos canales); lo demás, hipótesis declarada (D3) |
| El bloque extra no entra en la puerta | la profundidad trasera va en el marco de montaje y la colocación (A7 de V8.5) lo respeta |

## Bitácora

### F1 (2026-10-24) — hecha, sin mergear

Catálogo, builder y modelos (D1–D6) sobre `bf69175`, rama `wip/mandos-seguridad-f1`. Suite
completa verde en el worktree (5037 pasan, 10 saltan; 25 nuevos en `test_mandos_seguridad.py` y
`test_mandos_seguridad_faja.py`) y `ruff` limpio. Catálogo 388 → 393 refs.
- **Refs**: `ESTOP-40-2NC` y `ESTOP-40-CAJA-2NC` (`93_mandos.yaml`, misma ficha que la de 1 NC
  con 21-22 y el modelo `seta`), `RESG-2NC` + `RESG-LENGUETA` (`93_mandos.yaml`, builder
  `interruptor_resguardo` en `library/builders_mandos.py`) y `RS-2C-24VDC`
  (`122_maniobra_control.yaml`). Modelos en `cosim/modelos/seguridad.py`.
- **D5, sin bumps**: `ESTOP-40` y `ESTOP-40-CAJA` dan el mismo volumen, caras, aristas y bbox que
  en `bf69175` (congelado en `tests/test_mandos_seguridad.py`); 11 escenarios del banco (marcha,
  seta, atasco, corte de fase, cable cortado, caída de red, atasco parcial, cajas, sensor pegado,
  la seta por variador y el NC de la seta pegado) dan la MISMA huella en `bf69175` y en la rama:
  sólo se actualizó la `HUELLA` de `test_cosim_epoch.py`.
- **La pareja verde/roja** (`tests/test_mandos_seguridad_faja.py`, faja del banco por variador,
  `-S0:11-12` pegado a 1,0 s y la seta apretada a 1,5 s, final a 2,2 s): con UN NC (11-12 en
  paralelo a S1 y S2) el STO no corta (`-T2.sto` false, par habilitado, 1800 rpm: ROJO); con DOS
  NC (11-12 a S1, 21-22 a S2) `-T2.sto` true y la faja baja a 1540 rpm igual que sana (VERDE).
  Con los dos NC pegados ya no para (la categoría 3 tolera una falla). Con resguardo + relé: abrir
  para; con `-B2:11-12` pegado para igual y, cerrado y rearmado, el relé no rearma
  (`-K2.espera_ciclo`); con el NA 13-14 soldado para por S2.
- **Decisiones de F1** (para vetar):
  - La lengüeta es una ref APARTE (`RESG-LENGUETA`, sin ficha eléctrica): así se compra y así el
    agente la pone en la hoja del resguardo. Anclas `ranura` (cuerpo) y `punta` (lengüeta).
  - Los NC del interruptor los mueve el actuador «-B2.abierto» (el interruptor se ACCIONA al sacar
    la lengüeta, IEC 60947-5-1 Anexo K); la señal publicada es `-B2.cerrado`. Función IEC 81346-2
    «B» (interruptor de posición). `trabado`: el resguardo se abre igual (`cerrado` lo dice) y los
    NC quedan donde estaban, o como diga el valor; reparado, vuelven a seguir a la lengüeta.
  - El segundo bloque de la seta va APILADO (alarga 14 mm el portacontactos: `detras_mm` 44 → 58,
    como pide D1); en la caja van adentro y la caja sube de 55 a 69 de alto. `bloques=1` (default)
    reproduce la geometría de antes.
  - Relé: S11, S21 y S33 salen de A1 por dentro (caminos `fijo`; la vigilancia de cruces entre
    canales no se modela); canales y rearme son cargas `entrada` a A2 con IEC 61131-2 tipo 1;
    funciona desde 85 % de Un; `t_conexion_ms` 50 y `t_desconexion_ms` 20 (orden de la ficha, sin
    verificar); sin alimentación abre y al volver arranca de cero (sin ciclo pendiente). El NC de
    señal 41-42 abre mientras algún NA de seguridad está cerrado (guía forzada) y con un NA
    soldado el relé NO rearma (lo publicado de los relés de guía forzada, EN 50205).
  - `rele_seguridad` lo indexa el tablero por `BORNES_ENTRADA` (genérico), no por su clase.
  - `PIDE` suma «salida» (opciones: las `salidas` de la ficha). `set_scenario` documenta las
    fallas nuevas (golden re-congelado, sólo esa descripción).
- Pendiente para F2:
  - La UI no conoce aún el tipo `resguardo` (`vivo_fotograma.MANDOS` no lo incluye: no se puede
    abrir el resguardo en la sesión viva) ni el `pide` «salida» (la falla `salida_pegada` del
    relé se ofrece sin campo y el servidor la rechaza sin valor). F2 sólo necesita la seta.
  - La verificación sobre una copia de la faja piloto recableada con `ESTOP-40-2NC`.

### F1b (2026-10-24): la máquina viva

Los dos huecos de F1 en la sesión viva, sobre `c6d8295`, rama `wip/vivo-resguardo`. `npm test`
490 → 495 y `npm run build` verdes; pytest 5073 → 5074 (un test nuevo en
`test_mandos_seguridad_faja.py`: el `inicio` con el resguardo como mando, la salida pegada con sus
opciones y abrir en vivo) y `ruff` limpio.
- **Backend**: `vivo_fotograma.MANDOS` suma `resguardo`. El `inicio` ya publicaba las `opciones`
  de `salida_pegada` del relé (`fallas._opciones`, desde F1): no hizo falta tocar `fallas.py`. Sin
  bump de `COSIM_EPOCH` (sólo cambia lo que ofrece la tabla del `inicio`, ni el paso ni las
  trazas): se actualizó la `HUELLA` de `test_cosim_epoch.py`.
- **UI**: el resguardo se maneja como el seccionador (`accionar.abreYCierra`): botón «Abrir» /
  «Cerrar», tapa cuadrada sin color (la ficha no trae `specs.color`) y clic en su pieza 3D si la
  tiene. «Simular falla» conoce el `pide` «salida» (lista «Bornes 13-14»…, de las `opciones` del
  `inicio`; manda el texto de los bornes, que es lo que lee `ReleSeguridad._salida`, y lo quita con
  el mismo). Rótulos: «Salida de seguridad soldada», «relé detenido», «interruptor trabado» y el
  trabado del resguardo queda en «Contactos cerrados / abiertos».
- Muestrario: «Mandos · resguardo y relé de seguridad» con la seta, el resguardo, el rearme `-S3`,
  el relé y el motor; abrir, cerrar y rearmar los mueven como el modelo (en corto, en
  `datosVivo.accionarLocal`). Pegando `-B2:11-12` en «Simular falla» y abriendo, cerrando y
  rearmando, el relé queda en «Salidas abiertas» con la nota. El relé y su falla también están en
  «Simular falla».
- **Decisiones de F1b** (para vetar):
  - La fila del mando dice su estado en la línea del tipo («Resguardo cerrado», «Resguardo
    abierto»); el seccionador gana lo mismo para que los dos mandos de abrir y cerrar se lean
    igual. Sin señal todavía, sólo el tipo.
  - El relé va en «Lecturas», la vista que ya mostraba motor, variador y contador: «Salidas
    cerradas / abiertas» como valor y, sólo cuando ES la razón (los dos canales cerrados y
    `espera_ciclo`), la nota «No rearma hasta que abran y cierren los dos canales.» bajo la fila,
    como la línea «Falla:». Con el resguardo abierto `espera_ciclo` también vale 1, pero ahí no
    explica nada: no se muestra. La etiqueta 3D lleva sólo el valor. `estado` (texto) no se muestra:
    lo dicen las salidas y la nota.
  - El rearme bloqueado por una salida soldada no tiene nota propia: la falla ya está en la barra.
  - `AccionarMando` (contexto de React, por defecto `sesion.accionar`) para que el muestrario
    maneje los mandos sin WebSocket; `ListaMandos` y `Lecturas` se exportan de `PanelMandos.tsx`.
- Pendiente: la revisión de diseño a ciegas del panel con el resguardo (ancho y angosto) y F2.
- **Revisión a ciegas (2026-10-24, en la rama `wip/cable-visor`, bitácora F4b de
  [V8.5](V8.5-tablero-3d.md)):** «Salidas cerradas / abiertas» era jerga → «Habilita la marcha» /
  «Corta la marcha»; la seta sólo decía su estado con la tapa → «Seta de emergencia presionada /
  liberada» en su línea, como el resguardo; dos verbos para lo mismo («Presionar» la seta,
  «Apretar» el pulsador) → «Presionar»; las lecturas iban en la caja de los mandos y parecían botones
  → fila plana. Queda, de toda la app: el encabezado en mayúsculas espaciadas («MANDOS») frente a los
  del tablero, y el peso de las cifras de las lecturas.

### Cifras de fichas y líneas corregidas (2026-10-26)

Una investigación de sólo lectura de las fichas oficiales (fiabilidad ISO 13849-1 de los aparatos
de seguridad del catálogo, para fuera del núcleo) encontró líneas de referencia que NO cumplen la
ref que las cita. Una ref es un ejemplo ([library](../../core/apolo/library/CLAUDE.md) § Catálogo):
la línea citada tiene que cumplir lo que la ref define. Las cifras de ficha que entraron en la misma
tanda están en la bitácora homónima de [datos-de-corte-y-acometida](datos-de-corte-y-acometida.md).
Los datos de fiabilidad (B10d, PFHd) siguen fuera del núcleo (D4).

**Qué se corrigió** (`specs.linea_referencia`; las fichas leídas son todas de dominio del
fabricante, y la cita exacta va en la `fuente` de cada ref):

| ref | citaba | la ficha dice | ahora cita |
|---|---|---|---|
| ESTOP-40, ESTOP-40-CAJA (1 NC) | XB5AS8445 | 1 NO + 1 NC | XB5AS8442 (1 NC) |
| ESTOP-40-2NC, ESTOP-40-CAJA-2NC | XB5AS8442 | 1 NC | XB5AS8444 (2 NC) |
| RESG-2NC | Schneider Preventa XCSPA592 | 1 NC + 1 NO | Telemecanique Sensors XCSPA792 (2 NC; la marca XCS ya no es de se.com) |
| RESG-LENGUETA | Schneider Preventa XCSZ11 | — | Telemecanique Sensors XCSZ11 |
| RS-2C-24VDC | Pilz PNOZ X2.8P / Schneider XPSAC5121 | el PNOZ X2.8P sólo arranca automático o manual; el XPSAC5121 está descatalogado (28-dic-2023) | Siemens SIRIUS 3SK1111-1AB30 («monitored start-up Yes», 3 NA + 1 NC, 24 V AC/DC) |
| GM-AUX-1NA1NC | TeSys GVAN11 / Siemens 3RV2901-1E | GVAN11 es de montaje LATERAL; la ref es un bloque frontal | TeSys GVAE11 («front mounting») / Siemens 3RV2901-1E (transversal) |
| VFD-1K5-220, VFD-2K2-220 | SINAMICS V20 / Delta MS300 (en comentarios y `fuente`) | el V20 de 1,5–2,2 kW a 230 V es de entrada MONOFÁSICA y no tiene STO | Delta MS300 VFD7A5MS23ANSAA / VFD11AMS23ANSAA (230 V 3F, «S: Integrated STO», Cat 3 PL d) / Siemens G120 CU240E-2 + PM240-2 200 V 3AC |

La `fuente` de la temperatura de las setas suma las fichas XB5AS8442 y XB5AS8444 (−40…70 °C, la
misma). Sin cambio de bornes, `modelo` ni geometría en setas, resguardo y auxiliar.

**Decisiones (para vetar).**
- **D-g, la corriente del variador es la de servicio PESADO de la ficha**: el modelo dispara por
  sobrecarga a 150 % durante 60 s, que es la sobrecarga HD del MS300 (la ND es 120 % / 60 s).
  `VFD-1K5-220` pasa de 8,5 A (no era de ninguna ficha: MS300 da 7,5 HD / 8 ND; el V20, 7,8) a
  **7,5 A** en `modelo.I_salida_A` y `specs.corriente_A`; `VFD-2K2-220` ya tenía 11 A, la HD del
  VFD11AMS23ANSAA. `I_entrada_A` (10 y 13) no está en el catálogo del MS300 (el manual pide aceptar
  términos de uso): sigue como estimación y entra a `a_confirmar`.
- **D-h, vigencia del cambio de `modelo`**: `I_salida_A` está en `electrico.modelo`, que entra a la
  firma del documento (`EN_FIRMA`: `modelo`). Se cambia igual, sin `COSIM_EPOCH` (no cambió
  código): un documento con `VFD-1K5-220` cambia de firma y sus resultados de escenario guardados
  quedan vencidos, que es lo correcto (su límite de corriente y su sobrecarga ahora disparan a
  otra corriente). Las 4 firmas del banco (`tests/test_firma_dispositivo.py`) usan el
  `VFD-2K2-220`, cuyo `modelo` no cambió: no se mueven. `a_confirmar` no entra a la firma.
- **D-i, lo que no se tocó del variador**: la envolvente (`params`; el MS300 de 2,2 kW es el frame C
  de 87 × 157 × 152 mm) y las caras de sus bornes (orden del V20 FSB): cambiarlas mueve la
  geometría (epoch) y el ruteo de la piloto. Quedan anotadas como pendientes en el YAML hasta
  leer el manual de la línea nueva.
- **D-j, el relé de seguridad cita sólo el 3SK1**: el PNOZ X2.8P no tiene rearme vigilado (la ref
  sí) y el reemplazo de Schneider (XPSBAC14AP, según su buscador) no se leyó. Su `modelo` no
  cambia: `U_min_pct` 85 coincide con el 3SK1 (0,85 Un); `t_conexion_ms` 50 y `t_desconexion_ms` 20
  son más lentos que los del 3SK1 (arranque vigilado 15 típ. / 20 máx.; caída 10 típ.), del lado
  seguro para la prueba virtual, y cambiarlos movería la firma del tablero con relé de seguridad
  del banco. Los bornes siguen genéricos (familia PNOZ/XPSAC; el 3SK1 los nombra distinto) y la
  caja (22,5 × 114 × 99) no se tocó (el 3SK1 mide 22,5 × 100 × 121,6): `cotas_verificadas: false`.
- **D-k, el auxiliar del guardamotor**: la descripción y el acople (`cara: frente`) ya decían
  frontal; lo incoherente era la línea. Se corrige la línea, no la ref.

**Queda a confirmar.** El PFHd del STO del MS300 (en su manual de usuario, no leído); las caras de
bornes y la envolvente de los variadores con la línea nueva; `I_entrada_A`; los bornes del 3SK1.

**Vigencia.** Sin `GEOM_CACHE_EPOCH`, versión de comando ni `COSIM_EPOCH`. Sólo la firma de los
documentos que usan `VFD-1K5-220` (D-h).

### F2b (2026-10-27): ¿entra la lengüeta?

**Por qué.** Dos máquinas modeladas por MCP esta noche (una mezcladora con tapa y un tanque con
boca de inspección), cada una con su `RESG-2NC` y su `RESG-LENGUETA` en la hoja, dejaron la
lengüeta FUERA de la ranura con el resguardo cerrado (en una, 3,5 mm por encima del cabezal; en la
otra, la punta justo en la boca). El ERC, la puerta de entrega y la FAT dieron verde: la
co-simulación toma el contacto como cerrado sin mirar la geometría. Lo vio un revisor a ciegas con
`measure`. En la vida real la máquina no arranca, o el operario puentea el enclavamiento.

**Qué hace.** `library/enclavamiento.py` (puro) y `services/enclavamientos.py` (lee, empareja y
posa); entra en `delivery_check` como sección «enclavamiento del resguardo» SÓLO si la escena tiene
interruptores de resguardo o lengüetas (sin ellos, la puerta da lo de siempre).
- **Cerrado**: profundidad = (punta − boca) · eje de la ranura, con `insercion_min_mm` ≤
  profundidad ≤ fondo (16 mm), y la sección de la lengüeta (sus 4 esquinas en la punta y donde
  cruza la boca) dentro de la de la ranura. Error = ROJO.
- **Abierto**: con junta, en el valor de la junta más lejano al cerrado la lengüeta tiene que estar
  fuera (la punta no pasó la boca, o ninguna esquina cae en la sección de la ranura). Error = ROJO.
- **No verificable** = AMARILLO: interruptor sin lengüeta, lengüeta sin interruptor, pieza sin
  las anclas, emparejamiento ambiguo, y la lengüeta unida a una hoja que gira sin colgar de su
  junta (el modelo no la mueve al abrir). Sin junta en la hoja, `no_aplica` (nunca verde).

**Cifras de las dos máquinas** (sólo lectura de `C:\t\maq\…\apolo.db`, proyecto 1; el caso malo,
moviendo la lengüeta en una copia en memoria con `edit` de su `position.z` y regenerando):

| máquina | estado actual | lengüeta en la boca | 3,5 mm por encima | puerta actual |
|---|---|---|---|---|
| mezcladora-paletas-200l (-B1 c66 / c67, junta `j_tapa_carga` 0–100°) | entra 12,0 mm; abierta (100°) sale | ROJO | ROJO | AMARILLO por otras reglas; la sección, OK |
| tanque-agitador-500l (-B1 c44 / c45, junta `j_tapa_boca` 0–105°) | entra 12,5 mm; abierta (105°) sale | ROJO | ROJO | VERDE con la sección OK |

La sección tarda 16 ms de CPU en cada una (199 y 107 sólidos).

**Decisiones (para vetar).**
- **D-l, emparejamiento.** Interruptor = pieza cuya ficha nombra su actuador (`specs.actuador`);
  lengüeta = pieza cuya ref es el actuador de alguna ficha. Primero por DESIGNACIÓN (la del
  dispositivo que liga al interruptor o, sin carril, la de su nombre; la lengüeta cuyo nombre la
  lleva, si es una sola); el resto por cercanía (punta ↔ boca, la menor entre la pose de diseño y
  los extremos de la junta), de menor a mayor. Si otra pieza libre queda a menos de 20 mm más que
  la elegida (`AMBIGUO_MM`), aviso que las nombra; el par se evalúa igual.
- **D-m, el mínimo de inserción** es `specs.insercion_min_mm: 12` de `RESG-2NC`: **criterio de
  diseño, a confirmar** con la ficha de la línea (la cota del actuador insertado y su tolerancia no
  se pudieron leer: la página de producto de se.com no la publica en texto). Ranura de 16 mm menos
  4 mm de juego. Las dos máquinas corregidas quedan en 12,0 y 12,5 mm: pasan justo; si la ficha
  pide más, las dos caen en ROJO, que es lo correcto. Una ficha sin el dato usa 12
  (`INSERCION_MIN_DEFECTO`).
- **D-n, la tolerancia de alineación es la holgura del propio par** (±1 mm de ancho, ±0,5 mm de
  canto: ranura 20 × 4,5, lengüeta 18 × 3,5), medida en las esquinas: más allá la lengüeta choca
  con el cabezal. Con la lengüeta inclinada lo dicen las esquinas de la boca (5° por el canto ya
  no entra).
- **D-o, la geometría sale de las anclas que ya había** (`ranura`, `punta`, `fijacion_1/2`: el
  marco completo) y de las cotas del builder (`RESG_RANURA`, `RESG_LENGUETA`), nunca del bbox. No
  se agregó ninguna ancla: así un open caliente (la caché guarda las anclas de cada Feature) da lo
  mismo que uno frío y no hay bump de `GEOM_CACHE_EPOCH`. La geometría no cambió.
- **D-p, poses**: la de diseño y los extremos (`lower`, `upper`) de la primera junta no `fija`
  subiendo por la cadena de la lengüeta, con la FK del servidor (`feature_location`, las anclas
  con la misma `Location` que la forma). Cerrado = la de diseño si entra, si no el primer extremo
  en que entra (una hoja dibujada abierta); abierto = el valor más lejano al cerrado.
- **D-q, sólo en la puerta de entrega, no en el ERC**: el ERC entra a la puerta por su sección
  «eléctrico» y la misma falla saldría dos veces; además la verificación vale sin carril (un
  interruptor y su lengüeta sin `add_device`). `electrical_check` no la muestra.
- **D-r, `VERSION_BATERIA` 2 → 3**: chequeo nuevo del núcleo. Sólo se publica con extensiones
  («3+nombre.v»): una extensión que compare la cadena con «2+…» tiene que actualizarse.

**Verificación.** `tests/test_enclavamiento_resguardo.py` (16): bien puesta = OK; 3,5 mm por
encima, en la boca, corta (8 mm) y hasta el fondo = ROJO; corrida 1,5 mm de lado = ROJO y 0,9 mm
= OK; inclinada 5° = desalineada; con junta, abierta = fuera; dibujada abierta con junta
prismática = cerrado en el extremo; junta que no la saca = ROJO; unida a la hoja sin colgar de su
junta = aviso; sin lengüeta = aviso; sin resguardos = sin sección; dos pares a 30 mm sin
designación = aviso de ambigüedad, con ella no; la designación gana a la cercanía.
