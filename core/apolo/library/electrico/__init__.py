"""Modelo eléctrico puro de la máquina (V8 D15, plan V8.1 F2).

  - `tension`: texto de placa ↔ tensión estructurada y tensión entre polos;
  - `ficha`: el bloque `electrico:` del catálogo, validado al cargar;
  - `modelo`: dataclasses del modelo EVALUADO (dispositivo, conductor, cable, red);
  - `referencias`: `[=función][+ubicación]-dispositivo:borne` y el «¿quisiste decir…?»;
  - `redes`: union-find de puntos y propagación de fuentes en el peor caso;
  - `erc`: el chequeo eléctrico estático (D7).

Nunca recibe un `Document` ni importa `doc`, `api`, `kernel` ni OCP
(`tests/test_capas_electrico.py`): el carril del documento (F3) arma el modelo y se lo pasa.
"""
