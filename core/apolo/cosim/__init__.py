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
#: 6 (V8.9 F7b, defectos 5, 6 y 7): cada producto publica también `y_mm` y `z_mm` (trazas nuevas);
#: la colisión lleva un casco convexo por SÓLIDO de cada pieza (una pieza de varios sólidos cambia de
#: MJCF y de resultado); una aserción `==`/`!=` con un número contra un texto numérico («-QM2.posicion
#: == 14») se compara como texto en vez de dar error de tipo (otro veredicto con el MISMO documento).
#: 7 (pedidos-de-extensiones-iii F4, D11): el vástago de `create_pneumatic_cylinder` se mueve con la
#: masa MÓVIL de su ficha (`partes_de_cilindros`) y la armadura de la masa en carrera 0 ya no se
#: suma (el Ø63 × 800 pasa de 2,77 a 2,43 kg): un escenario SANO con aire cambia de resultado.
#: 8 (balance-de-producto, trabas de flujo): el producto RETIRADO por un sumidero se queda con la
#: posición en que se retiró (`<producto>.x_mm/y_mm/z_mm`, antes sin valor tras salir): un
#: escenario sano con sumideros cambia de trazas y «caja.x_mm >= … al_final» pasa de falla a pasa.
#: 9 (trabas-de-modelado D2b): la tornillería de un `join_bolted` declarado entra a la dinámica
#: (estática con su pieza estática o en el cuerpo de su pieza móvil) en vez de quedar FUERA: el
#: MJCF de toda máquina con `join_bolted` cambia (sus cabezas y tuercas chocan con el producto).
#: Y las aserciones `siempre`/`nunca` aceptan «hasta <ancla> [+ N s]» (D4; ningún escenario
#: guardado la usa).
COSIM_EPOCH = 9
