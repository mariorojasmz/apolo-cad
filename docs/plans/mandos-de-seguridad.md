---
estado: en curso
nota: contrato escrito por Claude el 2026-10-23 como la parte pública del ajuste A7 de un plan de seguridad funcional fuera del núcleo (aprobado por Mario; las alternativas de ingeniería las decide Claude, vetables); falta F1
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
