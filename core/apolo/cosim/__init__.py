"""Co-simulación de la máquina entera (plan V8.3): red, tablero, PLC, variadores, motores y física.

  - `modelos/`: un modelo de dispositivo por `electrico.modelo.tipo` del catálogo (F2), puro;
  - `red/`: la red de mando (MNA) y la de potencia (fasorial) (F3);
  - el planificador multi-tasa, el acople con MuJoCo y el worker en proceso aparte (F4).

Este `__init__` no importa nada: el worker de F4 importa sólo lo que usa, sin OCCT.
"""
