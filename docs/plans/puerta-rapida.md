---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: F1 mergeada (D1–D3, veredictos idénticos; mesa 1651→304 s, lavadora 1615→421 s); F2 (Trazador compartido) por decidir con un perfil nuevo
descripcion: La puerta de publicación de una máquina grande tarda minutos y no media hora, con los mismos veredictos
---

# La puerta de una máquina grande tarda minutos, no media hora

## Estado y origen

La puerta de la «Mesa de sorteo manual 12 puestos» (490 piezas, faja de 5 tramos con la plantilla
`create_belt_conveyor` v8) tardó **1399 s**, de los que **1325 s** (95 %) fueron
`diseno.sin_sobrantes`; `fuentes.seguridad` 35 s y `entrega` 16 s (campo `tiempos_s` del
resultado de la puerta). Otra máquina grande, una lavadora de bandejas (461 piezas), da el mismo
perfil. Mientras la puerta corre, el modelador
espera: cada ronda de corrección cuesta media hora de reloj y de saldo.

La regla: **ningún veredicto cambia** (ni el estado de un ítem ni lo que dice su evidencia). Sólo
se deja de recalcular lo que ya se sabe o lo que no puede cambiar.

## El problema / lo que hay hoy

Medido con `scripts/medir_sobrantes.py` (cProfile; la fuente «seguridad» y luego `sobrantes`, como
`puerta_publicacion.reunir`) en el escritorio (i7 8 hilos, 32 GB), **con otras cargas en la PC** y
las dos máquinas medidas a la vez: cifras con perfilador (≈ 1,3× la pared real; `process_time` ≈
pared: el trabajo es de CPU de un hilo).

| | mesa de sorteo (fat6) | lavadora (corrección 1) |
|---|---|---|
| candidatas | 312 (23 guardas, 289 «agregadas») | 83 |
| sobran / necesarias / vueltas | 289 / 23 / 3 | 46 / 37 / 2 |
| `sobrantes` (perfilado) | 1737 s | 1517 s |
| rectas · ingeniería · codo · apoyo | 326 · 680 · 418 · 307 s | 298 · 135 · 211 · 869 s |
| costo por candidata | sobra 4,5 s; apoyo 1,8 s; peligro 6,6 s | sobra 12,4 s; apoyo 12,5–18,6 s |

Tres cosas se rehacen ENTERAS por cada candidata aunque sólo cambie la zona de lo quitado:

1. **`BandaEmpujable`** (`calidad_codo.py:89-105`): dos `cKDTree` sobre las nubes de TODA la
   máquina (18,3 M puntos en la mesa; 5 s por construcción). Se arma en cada `probar` con sondas
   (`calidad_sobrantes.py:311`, `:373`, `:408`) y en cada «apoyo de» (`calidad_sobrantes_apoyo.py:40`):
   109 veces en la mesa (434 s), 86 en la lavadora (**809 s, el 53 %**).
2. **El campo de la muñeca** (`calidad_sobrantes.py:264` → `alcance.py:143-147`): `libre_sin` ya
   rehace sólo la zona (5 s en 95 llamadas), pero `CampoAlcance.__init__` vuelve a barrer las 26
   direcciones dos veces sobre los 12 M voxeles: 5,7 s por campo, 545 s en la mesa y 287 s en la
   lavadora (con el `ndarray.copy` de `_recta`, 230 s).
3. **Las reglas de ingeniería** (`calidad_sobrantes.py:326-327` → `calidad_mecanica.reglas_de_ingenieria`):
   2 s de CPU por candidata no-guarda. Lo caro no depende de ella: la viga continua de cada viga
   (`viga_continua.py:159`, 25 092 llamadas, 245 s; 97,6 % repiten entradas), el volumen de la
   banda por forma (`rules_comun.py:65` sin memo, `VolumeProperties` 76 s), las `cotas` de la
   plantilla (`calidad_tensores.py:300`, 0,27 s por llamada, siempre las mismas) y lo alcanzable
   desde el piso, que `loads.hanging_load_kg` (`loads.py:37-44`) recalcula por CADA unión del
   mismo grafo (96 333 llamadas, 148 s).

Hallazgo aparte (no es de este plan): la mesa anotó `puerta_primera = {ultimo_comando: 6}` —la
primera corrida fue con la faja sola—, así que toda la mesa es «agregada»: 289 candidatas que
sobran y que el modelador tuvo que justificar una por una. Ver «Lo que este plan NO hace».

## Lo que se revisó antes de escribir esto

- `calidad_sobrantes.py` completo, `calidad_sobrantes_apoyo.py`, `calidad_sobrantes_candidatas.py`,
  `calidad_codo.py`, `calidad_sondas.py`, `alcance.py`, `calidad_seguridad.controles_seguridad`
  (qué deja en `compartido`: nubes y campo, NO el `Trazador` ni la `BandaEmpujable`).
- Experimentos (fuera del repo, con quitadas = ∅) que fijan las decisiones:
  - D1: de las candidatas que necesitan sondas, **58 de 79** (mesa) y **27 de 57** (lavadora) no
    tienen ningún punto a ≤ `EMPUJE_MM` + 1 de la banda; en 3 de cada una se comprobó `empujable`
    idéntico en todos los puntos de banda (1,15 M y 4,16 M). Para las CERCANAS, `empujable` con los
    árboles de la base y lo quitado enmascarado dio idéntico a la rehecha en 11 candidatas de las
    dos máquinas (todos los puntos de banda a ≤ 45 mm de lo quitado + 200 000 al azar), en
    **0,5–1,0 s contra 5 s (mesa) y 9–10 s (lavadora)**, consultas incluidas.
  - D2: en 8 guardas de la mesa y 6 candidatas de la lavadora, el campo local da `_prof`
    **idéntico** (`np.array_equal`) al entero, en **0,5–0,8 s contra 5,3–6,2 s** (mesa: S1/S2 de
    1,3–2,9 M voxeles de 12,1 M) y **0,4–1,6 s contra 3,3–5,7 s** (lavadora: hasta 4,9 M de 12,0 M).
  - D3: en 25 candidatas no-guarda de la mesa, `_vida` con los memos da el MISMO resultado
    (25/25) en **0,80 s contra 1,97 s** de CPU.
- Por qué es exacto el campo local (D2): quitar una pieza sólo LIBERA voxeles (`libre_nuevo ⊇
  libre`), así que brazo y antebrazo sólo bajan; un tramo recto que vale ≤ `ALCANCE_BRAZO_MM` mide
  ≤ 850 mm, o sea ≤ L = ⌈850/paso⌉ voxeles por eje. Lo que cambia del brazo está a ≤ L de un voxel
  que cambió de `libre` (S1), y lo que cambia del antebrazo, a ≤ L de lo que cambió en el brazo o
  en `libre` (S2). En cada caja, `mín(viejo, _recta(sub-caja))`; fuera, lo viejo. El redondeo es
  el mismo: `fl(mín(x, y) + p) = mín(fl(x + p), fl(y + p))` y cada cadena se suma en el mismo
  orden.

## Decisiones (para vetar)

- **D1. La `BandaEmpujable` no se reconstruye por candidata: los árboles son los de F3 y lo
  quitado se enmascara.** F3 deja su `BandaEmpujable` en `compartido` con el bloque de índices de
  cada pieza en cada árbol; la de una copia sin `q` es una VISTA (`sin(q)`) que, al consultar,
  descarta los vecinos de `q` (`query(k)` creciente con el mismo `distance_upper_bound`: el primer
  vecino no quitado, la misma distancia que daría el árbol rehecho). Si ningún punto de `r` queda a
  ≤ `EMPUJE_MM` + 1 de la banda, la vista ni siquiera enmascara: es la base tal cual. *Por qué*:
  la construcción cuesta 5–10 s y se hacía 109 veces (mesa) y 86 (lavadora, el 53 % de la prueba);
  medido idéntico en las dos variantes. Las `bandas` y las `guardas` no cambian de conjunto (ninguna
  banda es candidata; una guarda quitada sólo pierde sus puntos).
- **D2. El campo de la muñeca sin la candidata se recalcula sólo en las cajas S1/S2** (`alcance.py`:
  `CampoAlcance.sin_zona(libre_nuevo)` que guarda también el brazo; `calidad_sobrantes._sin_zona`
  la llama). Sin voxeles cambiados, el campo es el mismo objeto. Si la grilla cambia (la caja de la
  máquina se mueve), entero como hoy. *Por qué*: 8× más rápido e idéntico.
- **D3. Memos EXACTOS de lo que la ingeniería recalcula igual por candidata**, vivos lo que dura
  la corrida (como `mass.memo_de_geometria`, que ya abre `reunir`): volumen por forma
  (`_vol_safe`, la suma del `Compound`, `vigas_rules._masa_kg`) con referencia y `is`; `cotas` de
  la plantilla por sus argumentos; `viga_continua` por sus entradas (largo, EI, apoyos, cargas:
  dataclasses congeladas o tuplas de floats; el resultado no lo muta nadie: un test lo vigila); lo
  alcanzable desde el piso una vez por grafo en `hanging_load_kg`. *Por qué*: −59 % en la etapa,
  mismo resultado. Ningún memo vive fuera de la corrida (raíz: sin estado global salvo los puntos
  establecidos).
- **D4. Nada cambia de orden, de criterio ni de candidatas.** La voraz, sus vueltas, la evidencia
  `tambien_tapa`/`solo_apoyo` y `por_etapa` siguen igual; sólo cambian los `ms`. `VERSION_REGISTRO`
  no sube (ningún ítem ni umbral cambia).
- **D5. El gate de F1 es la igualdad, no la tolerancia**: la salida de `sobrantes` (sin `ms` ni
  `por_etapa.*.ms`) idéntica antes/después en los testigos y en las dos máquinas.

## Alternativas descartadas

- **Podar candidatas que ningún control puede empeorar**: ya está hecho donde es exacto (una guarda
  sin peligros cerca sólo corre sujeción y guardas, < 10 ms); una no-guarda siempre corre
  ingeniería, y probar que una pieza no mueve ninguna regla (vuelco, luces de viga) es tan caro
  como correrlas.
- **Correr las candidatas en paralelo (procesos)**: la voraz depende del orden (lo quitado queda
  quitado); se podría especular, pero OCCT no es thread-safe y cada proceso necesita su copia del
  documento. Se mide de nuevo tras F1.
- **Bajar la resolución del campo o las direcciones**: cambia veredictos.
- **Compartir el `Trazador` de F3 con una máscara de lo quitado** (en F1): exacto (mismo orden de
  caras), pero pesa 60 s en la mesa y sin medir su parte de construcción en la lavadora: va a F2
  con su medida.
- **Reusar la `BandaEmpujable` sólo cuando lo quitado está lejos de la banda**: exacto y trivial,
  pero en la lavadora 30 de 57 candidatas con sondas están cerca; la máscara cubre las dos.

## Fases

- **F0 (hecha)**: la medición de arriba; `scripts/medir_sobrantes.py` queda como herramienta.
- **F1 — D1 + D2 + D3** (`services/calidad_sobrantes.py`, `calidad_sobrantes_apoyo.py`,
  `calidad_codo.py`, `library/seguridad/alcance.py`, los memos en `library/engineering/` y
  `library/rules_comun.py`; M). Tests: el campo local contra el entero en una escena sintética con
  piso sólido y sin él (igualdad exacta, también sin voxeles cambiados y con la caja cambiada);
  `BandaEmpujable` reusada contra la rehecha; cada memo con su caso (mismo resultado, `is` en la
  forma). **Gate**: (a) suite completa verde; (b) `scripts/testigos.py --en-proceso` sin
  re-congelar (mismos veredictos por ítem); (c) `scripts/medir_sobrantes.py --sin-perfil --json`
  en las dos máquinas antes y después: la salida de `sobrantes` idéntica salvo `ms`, y el tiempo
  de sobrantes medido (estimado con los experimentos: la mesa de ~1325 a ~350 s y la lavadora de
  ~1500 a ~450 s; objetivo del gate: la mesa ≤ 450 s y la lavadora ≤ 600 s sin perfilador).
- **F2 (sólo si F1 lo justifica)**: el `Trazador` compartido con máscara (tras F1, el trazado de
  rayos es lo que queda: `_candidatas` + `_cruces` ≈ 290 s perfilados en la lavadora), con la
  misma vara.

## Lo que este plan NO hace

- No toca qué es candidata. Que la mesa anotara `puerta_primera` con 6 comandos (la faja sola) y
  pidiera justificar 289 piezas es un defecto de cuándo se anota la primera corrida
  (`marcar_primera_corrida`, D9 de [puerta-sin-sobrediseno](puerta-sin-sobrediseno.md)): cambiarlo
  cambia veredictos y va en su propio plan.
- No baja la exigencia de ningún control ni cambia la puerta de entrega (`entrega` 16 s).

## Riesgos

- **Un memo que devuelve un objeto que alguien muta** → resultados cruzados entre candidatas. Se
  memoiza sólo lo puro, la clave guarda la forma y verifica `is`, y un test congela que el
  resultado no se muta.
- **El campo local con una caja de grilla distinta** → se detecta con `misma_grilla` (como hoy) y
  se cae al entero.
- **La máscara con un bloque de índices corrido** (otra pieza enmascarada) → los bloques salen del
  mismo `nubes_de` que arma el árbol, en el mismo orden, y un test compara la vista contra la
  rehecha en una escena con banda, guardas y apoyos. El colchón de «lejos» sólo agranda «cerca».
- **Una consulta enmascarada lenta** (muchos vecinos quitados dentro del radio: k crece ×4) →
  medido ≤ 1 s con 380 000 consultas; `empujable` en la prueba consulta mucho menos.
- **Medir con la PC cargada** → las cifras de F1 se toman antes y después en la misma sesión y
  con `process_time`, además de la pared.

## Bitácora

- **F0 (2026-10-29)**: medido arriba. La mesa: 1737 s perfilado (1399 s el total real de su
  puerta). Lo caro no es «probar muchas candidatas» sino rehacer por cada una tres cosas enteras
  (árbol de la banda, campo de la muñeca, reglas de ingeniería) que sólo cambian en la zona de lo
  quitado o no cambian. Los tres prototipos (máscara de la banda, campo local, memos de
  ingeniería) se midieron fuera del repo con quitadas = ∅, contra el código actual: idénticos en
  todas las candidatas probadas (11, 14 y 25). En la lavadora la carga del `.apolo` tarda 219 s y la
  fuente «seguridad» 125 s: no son de este plan. La PC tenía otras cargas y las dos máquinas se
  midieron a la vez: las cifras de F1 se toman antes/después en la misma sesión.

### F1 (2026-10-29)

- **Qué entró.** D1: `BandaEmpujable.sin(q)` (`calidad_codo.py`) enmascara las filas de `q` en
  los árboles de la corrida (F3 deja su banda en `compartido["empuje"]`; `Prueba.empuje` la usa en
  `probar`, `_holguras`, la base de `_rectas`, el campo base y el «apoyo de»; con una banda en `q`,
  rehecha). La consulta enmascarada empieza con k = 1 y sólo los puntos cuyo vecino está quitado
  buscan más (k ×4): exacta para CUALQUIER punto (también los de un rayo que toca la banda), así
  que no hizo falta el atajo «lejos de la banda» del contrato. D2: `CampoAlcance.sin_zona` —
  recalcula en S1/S2 sólo si lo quitado LIBERA voxeles; si alguno se CIERRA (una banda que deja de
  empujarse al quitar su guarda) cae al campo entero, como antes: la monotonía del contrato no vale
  en ese caso. D3: `engineering/memo_corrida.py` (ContextVar que abre `mass.memo_de_geometria`):
  volumen por forma (`_vol_safe`, `vigas_rules._masa_kg`; `is`), `viga_continua` por sus entradas
  (clave `pickle`: distingue 1 de 1,0) y la carrera de la plantilla en `calidad_tensores`; lo
  alcanzable desde el piso, una vez por grafo en `_fastener_checks` (`loads.alcanzables`, sin memo).
- **Medido** (`scripts/medir_sobrantes.py --sin-perfil --json`, escritorio, las CUATRO corridas a
  la vez y con otras sesiones en la PC: pared ≈ CPU, el trabajo es de un hilo):

  | | mesa de sorteo (fat6) antes → después | lavadora (corrección 1) antes → después |
  |---|---|---|
  | `sobrantes` (pared) | 1650,8 → **303,5 s** | 1615,4 → **420,9 s** |
  | rectas · ingeniería · codo · apoyo | 348 · 425 · 506 · 368 → 12 · 143 · 112 · 35 s | 332 · 106 · 236 · 937 → 17 · 75 · 143 · 186 s |
  | veredicto (`sobrantes` sin `ms`) | idéntico | idéntico |

  Objetivo del gate (mesa ≤ 450 s, lavadora ≤ 600 s): cumplido. Lo que queda: la ingeniería de la
  mesa (143 s: 280 pruebas) y el brazo doblado (`sondas_con_codo` + `Trazador`) en las dos; el
  `Trazador` compartido (F2) se decide con un perfil nuevo.
- **Gate**: tests de igualdad por palanca (`tests/test_puerta_rapida.py`); `scripts/testigos.py
  --en-proceso` sin re-congelar: los cuatro públicos IGUAL (los privados no estaban en esta PC).
