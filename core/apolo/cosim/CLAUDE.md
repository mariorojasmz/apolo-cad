# Co-simulación (`core/apolo/cosim/`)

La máquina entera en virtual: red, tablero, PLC, variadores, motores y física
([V8.3](../../../docs/plans/V8.3-prueba-virtual.md)). Lo común del backend, en
[core/apolo](../CLAUDE.md).

## Modelos de dispositivo (`modelos/`)

- Uno por `electrico.modelo.tipo` del catálogo (`MODELOS`; la lista del YAML es
  `library/electrico/ficha.TIPOS_MODELO` y un test exige que coincidan). Tipo nuevo = clase aquí +
  la entrada allá.
- Estado EXPLÍCITO, `paso(dt, entradas) -> salidas` y `senales()` con los nombres de D10
  («-K1.cerrado»): determinista, sin reloj ni azar.
- Todo parámetro pasa por `Parametros`: falta → `ModeloIncompleto` con ref, clave y dónde
  completarla. Rango del catálogo = `ajustado` (lo fija el instalador en `add_device.ajustes`,
  obligatorio); banda de ficha = `de_banda` (punto medio DECLARADO en `hipotesis`). Nunca un
  default silencioso: una cifra nueva cita su norma o dice «criterio de diseño» en el YAML.
- Las curvas y umbrales de NORMA (IEC 60898-1, 60947-4-1, 60127-2, 61131-2) van en el código del
  modelo, no en el YAML.
- PURO y sin OCCT (`tests/test_capas_cosim.py`): de `apolo` sólo importa `cosim.modelos`, ni
  siquiera `apolo.library` (su `__init__` carga el catálogo y OCP, y el worker de F4 no debe).
  Por eso el motor recalcula la Kloss de `motor_induccion` y un test las ata.

## Redes (`red/`)

- Puro igual (numpy + LAPACK de scipy; ni `cosim.modelos`): lee el formato plano de `entrada.py`,
  que arma `services/cosim_red.py` del modelo de V8.1. Un dato nuevo del tablero entra por ahí.
- La alterna de MANDO va en la red de potencia (está unida a la red); el mando es la continua.
- Mando: `pedidas()` ANTES de `paso` y la fuente decide su U en el mismo paso (con atraso, un
  corto franco funde el fusible antes del límite). Cada paso es superposición sin resolver.
- Worker con BLAS de un hilo (`OPENBLAS_NUM_THREADS=1`): en 62×62 los hilos multiplican por 7.
