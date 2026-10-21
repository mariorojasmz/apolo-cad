"""Co-simulación de la máquina entera (plan V8.3): red, tablero, PLC, variadores, motores y física.

  - `modelos/`: un modelo de dispositivo por `electrico.modelo.tipo` del catálogo (F2), puro;
  - `red/`: la red de mando (MNA) y la de potencia (fasorial) (F3);
  - raíz (F4): `planificador.correr(snap)` (multi-tasa, reloj virtual), `tablero` (modelos sobre
    las redes), `acople` (D8 con MuJoCo), `agenda` y `escenario` (D12), `trazas`, y el worker en
    proceso aparte (`worker`, `proceso`). El snapshot lo arma `services/cosim_snapshot.py`.

Este `__init__` no importa nada: el worker importa sólo lo que usa, sin OCCT.
"""
