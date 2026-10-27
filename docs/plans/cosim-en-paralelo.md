---
estado: implementado
nota: sin pendientes (si la cola de jobs de la API también debe correr varias, es otro plan: D4)
descripcion: varias co-simulaciones corren a la vez (4 en una PC de 8 núcleos): una FAT virtual de 20 corridas tarda un tercio
---

# Las pruebas virtuales corren varias a la vez, no en fila

## Estado y origen

Medido la noche del 2026-10-27 por la sesión orquestadora: la FAT virtual de una extensión (20
corridas de la faja 77 con desviador) tardó 12 min en la PC de escritorio de 8 núcleos, 33–37 s
por corrida y todas en fila. La extensión ya lanza sus casos desde un pool de hilos; el núcleo los
ponía en fila.

## El problema / lo que hay hoy

- `core/apolo/cosim/proceso.py` (sobre `80d3351`) serializaba TODA co-simulación con
  `COSIM_LOCK = threading.Lock()`, tomado alrededor del `Popen` + `communicate` del worker.
- Cada corrida es su propio proceso (`python -m apolo.cosim.worker`, BLAS de un hilo) que recibe
  el snapshot por pickle y devuelve JSON: no comparte estado con nadie. El lock sólo cuidaba CPU y
  RAM.
- Usuarios de `COSIM_LOCK`: sólo `correr_en_proceso`, al que llegan `POST /api/cosim/run` (sync y
  job), `POST /api/cosim/plc/test`, la sesión viva vuelta escenario (`routers/cosim.py`) y
  `services/corrida_escenario.correr_corrida` (la API de extensiones). El vivo
  (`cosim/proceso_vivo.py`) no lo toma. Lo que guarda una corrida (`SIMULACIONES`, con su lock;
  el compacto al manifest, bajo `STATE_LOCK`) ya era seguro entre hilos.

## Decisiones (para vetar)

- **D1. `COSIM_LOCK` pasa a `threading.BoundedSemaphore(COSIM_PARALELO)`**, con
  `COSIM_PARALELO` de la variable `APOLO_COSIM_PARALELO` leída al importar (cambiarla = reiniciar
  la API, como `APOLO_PORT`). Se conserva el nombre: con 1 es exactamente el lock de antes. El
  límite de tiempo del worker cuenta desde que la corrida tiene su cupo, como antes.
- **D2. Default = mín(núcleos − 2, RAM / 4 ÷ 512 MB, 4), al menos 1.** El worker es de un hilo,
  así que una corrida ocupa un núcleo; dos quedan para la API (y su sandbox), la UI y el sistema.
  RAM: el pico medido de un worker es 145 MB (abajo); se reservan 512 MB (~3,5×, margen para una
  máquina más grande) y como mucho un cuarto de la RAM física (el resto, para el modelo OCCT de la
  API y los modeladores). Tope 4: la PC de escritorio corre a la vez APIs de modeladores, suites y
  revisores; más de 4 corridas se pide a mano con la variable. La RAM se lee sin `psutil` (no es
  dependencia del núcleo): `GlobalMemoryStatusEx` en Windows, `sysconf` en POSIX; si no se puede,
  cuentan sólo los núcleos. En la PC de escritorio (8 núcleos, 32 GB) da 4.
- **D3. Un valor inválido no tumba la API**: vacío → default; un entero de 1 a 64 → ese; otra cosa
  → el default con un `RuntimeWarning` que nombra la variable y el valor.
- **D4. `COSIM_JOBS` sigue con UN worker**: la cola de la API (agente y visor, también la puerta de
  publicación) corre un job a la vez, como siempre. La ganancia es para quien lanza varias
  corridas desde sus hilos (el pool de una extensión, peticiones sync simultáneas). Abrir varios
  workers en `COSIM_JOBS` cambia el orden que ve el agente y la memoria de la API: no entra aquí.
- **D5. `COSIM_EPOCH` no sube**: ninguna corrida cambia (proceso propio, mismo snapshot). La huella
  de `tests/test_cosim_epoch.py` se actualiza con su porqué; medido abajo: misma huella de trazas
  con 1, 2 y 4 a la vez.

## Alternativas descartadas

- Un `multiprocessing.Pool` o workers calientes reutilizados: el worker es UNA corrida por proceso a
  propósito (el estado de MuJoCo, del PLC y de los modelos no se arrastra, V8.3 D11); el arranque
  (~1 s) no es el costo.
- Leer la variable en cada corrida: un semáforo no cambia de tamaño en caliente sin una cuenta
  propia; reiniciar la API para cambiarla es lo que ya hacen las demás `APOLO_*` de proceso.

## Lo que este plan NO hace

- No toca el vivo (`proceso_vivo.py`, una sesión por API) ni la cola `COSIM_JOBS` (D4).
- No reparte la física dentro de una corrida (sigue siendo de un hilo).

## Bitácora

### 2026-10-27: implementado y medido

**Qué quedó**: `cosim/proceso.py` (semáforo, `paralelo`, `paralelo_por_defecto`, `_ram_total`),
docstrings que decían «en fila»/«serializa» (`services/corrida_escenario.py`,
`api/routers/cosim.py`, `api/common.py`), una línea en `core/apolo/cosim/CLAUDE.md`, la huella de
`tests/test_cosim_epoch.py` y `tests/test_cosim_paralelo.py` (con N = 2 dos corridas están dentro
a la vez; con N = 1 la segunda espera; el cupo vuelve aunque el worker no arranque; la variable y
el default; la API lee la variable al importar). El solape se mide con eventos sobre un `Popen`
falso, no con el reloj de pared.

**Medición** (PC de escritorio: i7-9700K, 8 núcleos sin HT, 32 GB; venv de `apolo-cad-pruebas`,
código del worktree). Escenario `flujo_nominal` (60 s simulados, el más largo de los 26) de
`C:\t\v89f13\faja-77-desviador-v6.apolo`, cargada en proceso con `preparar_corrida` y corrida con
`correr_corrida` desde 6 hilos. RSS = `peak_wset` de cada worker (psutil, cada 50 ms).

| | pared total | por corrida (`total_s`) | CPU de los workers | huellas |
|---|---|---|---|---|
| N = 1 | 203,5 s | 30,0–35,9 s | 188 s | 1 |
| N = 4 | 73,8 s (2,76×) | 33,6–40,5 s | 180 s | 1 |

- RSS pico de un worker: 141–145 MB en todas las corridas medidas (28) (el proceso de 372 MB que aparece
  en la medición es el `sandbox_worker` que regeneró el documento al cargarlo, no un worker de la
  co-simulación).
- Carga de la PC al medir (otros agentes): 67–76 % de CPU en los 3 s previos a cada tanda (APIs de
  modeladores en 8281–8283 y una suite con xdist), 9,8 GB libres. Una primera tanda con la PC al
  100 % dio N = 1 → 190 s y N = 4 → 107 s: el reparto empeora con la carga, pero no se pierde.
- Cada corrida tarda ~12 % más con 4 a la vez (caché y memoria compartidas) y la CPU total es la
  misma: la ganancia es de pared. A ese ritmo la FAT de 20 corridas pasa de 12 min a ~4.
- Huella de las trazas: 53a69cae… con N = 1 (1 corrida), N = 2 (2) y en cada tanda de 6.
