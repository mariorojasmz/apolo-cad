# PLC virtual (`plc/`)

Compilador ST → Python y runtime de scan ([V8.3](../../../docs/plans/V8.3-prueba-virtual.md)
D4–D6). Puro: sólo stdlib, nada de `apolo` fuera de `plc` (`tests/test_capas_plc.py`). Los
bornes válidos los pasa quien compila (`compilar(fuente, bornes=…)`): aquí no se lee el catálogo.

- **Seguro por construcción, tres llaves**: el lexer rechaza `__` y todo identificador sale
  como `v_<nombre>`; `verificador.py` re-lee el Python con lista blanca; el `exec` va sin
  `__builtins__`. Emitir algo nuevo = ampliar la lista blanca en el mismo commit
  (`test_plc_seguridad.py`), nunca meter builtins al espacio de nombres. Los campos internos de
  un bloque llevan `_`: ST no los alcanza.
- **Determinista**: el reloj es el `t_ms` que da quien llama, nunca el de pared. El watchdog es
  un presupuesto de VUELTAS de bucle (`ITER_POR_MS` × watchdog_ms), no de tiempo: sin bucles,
  el scan es acotado (no hay recursión ni saltos atrás).
- Semántica elegida donde la norma deja margen (docstrings de `tipos.py`, `ayudas.py`,
  `bloques.py`): el desborde de INT/DINT da la vuelta AL GUARDAR; REAL es doble; `MOD 0 = 0` y
  `/ 0` entero es falla; `F_TRIG` no pulsa al arrancar. Cambiarla cambia las pruebas de máquina.
- Un bloque estándar nuevo: clase con `__slots__` + `INICIAL` + función `(inst, t)` en
  `bloques.py`, y su interfaz en `tipos.FB_ESTANDAR`.
- `Compilado` es picklable: el código objeto se rearma y RE-verifica al pedirlo.
- Los comentarios no son tokens: `tokenizar(fuente, comentarios=lista)` los junta como
  `ast_st.Comentario` y `parsear` los deja en `Unidad.comentarios`; el compilador NO los mira (el
  `Compilado` es el mismo con y sin juntarlos: `test_plc_comentarios.py`). Lo que una extensión
  importa de `plc` está en `extensiones_api.MODULOS`: quitar o renombrar sube
  `CONTRATO_EXTENSIONES`. [plc-en-el-lazo](../../../docs/plans/plc-en-el-lazo.md) (D1, D2)
- Rendimiento: ≤ 50 µs por scan con ~500 líneas (`test_plc_rendimiento.py`, `-m torture`).
  Las ayudas en línea (índice, `/` y `MOD` por constante) son por eso: no las saques.
