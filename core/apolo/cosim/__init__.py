"""Co-simulación de la máquina entera (plan V8.3): red, tablero, PLC, variadores, motores y física.

  - `modelos/`: un modelo de dispositivo por `electrico.modelo.tipo` del catálogo (F2), puro;
  - `red/`: la red de mando (MNA) y la de potencia (fasorial) (F3);
  - raíz (F4): `planificador.correr(snap)` (multi-tasa, reloj virtual), `tablero` (modelos sobre
    las redes), `acople` (D8 con MuJoCo), `agenda` y `escenario` (D12), `trazas`, y el worker en
    proceso aparte (`worker`, `proceso`). El snapshot lo arma `services/cosim_snapshot.py`.

Este `__init__` no importa nada: el worker importa sólo lo que usa, sin OCCT.
"""

#: Versión del MOTOR de la co-simulación y de sus aserciones (V8.3 F6b, defecto 1). Entra a la
#: vigencia de un resultado de escenario junto con la firma del documento y el hash del
#: escenario (`services/escenarios.py`): un resultado guardado con otra versión queda
#: «vencido» (AMARILLO en la puerta). Se SUBE cuando un cambio de código puede cambiar el
#: resultado o el veredicto de un escenario con el MISMO documento (modelos, redes, planificador,
#: PLC, dinámica, snapshot, lectura o evaluación de aserciones); un refactor sin efecto no la
#: sube. `tests/test_cosim_epoch.py` obliga a decidir (regla en `cosim/CLAUDE.md`).
#: 4 (V8.4, cola en vivo): una caja de la cola nace sólo con su lugar de entrada libre
#: (`physics/dinamica_nacimiento.py`); un escenario cuya cola encimaba cajas cambia de trazas.
#: 5 (datos-de-corte-y-acometida F1c, D7/D11): la co-simulación lee el `esquema` de tierra de la red
#: del AJUSTE primero (antes lo ignoraba) y entiende TN-S, TN-C-S, TT (con `RA_ohm`, el PE unido a
#: tierra por 1/RA) e IT; la hipótesis de Icc ajustada ya no dice «SUPUESTA». Con el MISMO
#: documento un esquema ajustado cambia el resultado: todo resultado guardado queda vencido.
COSIM_EPOCH = 5
