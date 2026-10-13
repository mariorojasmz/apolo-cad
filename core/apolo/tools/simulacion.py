"""Tool MCP `simulate` (V8.2 D10): la máquina en marcha, por la API.

Vive fuera de `mcp_server.py` por el trinquete de tamaño (`tests/test_tamano_archivos.py`):
se registra en el MISMO `mcp` cuando `mcp_server.py` la importa al final, así que aparece en
`list_tools()` y en el chat como cualquier otra. Cliente fino: busca `mcp_server._api` en
CADA llamada (los tests lo parchean por nombre), arma el cuerpo, recorta para el agente lo
que es para animar (poses, trazas por fotograma, muestras de sensor) y escribe el GIF a
`path`. V8.3 la extiende con el tablero y los escenarios en vez de sumar otra tool.
"""

from __future__ import annotations

import json
from pathlib import Path

from apolo import mcp_server as _srv

#: Lo que el agente lee, en este orden. Lo demás de la API es para animar (poses, la lista de
#: piezas por cuerpo, los productos de entrada y las trazas q/q̇/par por fotograma de cada
#: junta; sus valores finales ya van en `resumen`), igual que las `muestras` de cada sensor.
_PARA_EL_AGENTE = ("mensaje", "resumen", "motores", "sensores", "avisos", "cuerpos")


@_srv.mcp.tool()
def simulate(
    motores: list[dict] | None = None,
    productos: list[dict] | None = None,
    sensores: list[dict] | None = None,
    duracion_s: float = 3.0,
    bandas: list[dict] | None = None,
    juntas: dict | None = None,
    con_autodeteccion: bool = False,
    opciones: dict | None = None,
    path: str | None = None,
) -> str:
    """Simula la máquina EN MARCHA (dinámica MuJoCo): las juntas giran o deslizan movidas por
    `motores`, los `productos` (cajas) viajan sobre la banda o los rodillos y los `sensores`
    (fotoceldas) los ven pasar. Lo sujeto a tierra (ground/fasten) es estático; una pieza sin
    sujeción ni junta queda FUERA con aviso (eso lo prueba gravity_test). Unidades: mm, kg, s.
    - motores: [{junta, modo: 'velocidad'|'par', ...}]. 'velocidad' pide UNA consigna: `valor`
      (rpm; mm/s si la junta es prismática), `v_superficie_m_s` (banda o rodillo) o `placa`
      {potencia_kW, rpm, frecuencia_hz?, polos?, tk_tn?, inercia_rotor_kgm2?} con
      `reduccion`, `eta` y `frecuencia_hz` (motor de inducción + reductor por Kloss).
      'par': `valor` en N·m (N si es prismática) y `rampa_s`. `desde_s` = arranque.
      `direccion_transporte` [x,y,z] FIJA hacia dónde avanza la banda: sin ella se usa el eje
      tal cual y un aviso dice hacia dónde fue.
    - productos: [{nombre, dims_mm [dx,dy,dz], posicion_mm [x,y,z] (centro), masa_kg?,
      velocidad_mm_s?, rotacion_deg?, friccion?, cada_s? (alimentación en serie), cantidad?,
      desde_s?}].
    - sensores: [{nombre, origen [x,y,z], direccion [x,y,z], alcance_mm?}]: un rayo que sólo
      ve lo que se mueve; devuelve sus flancos con el tiempo y cuántas cajas contó.
    - bandas: sólo si la banda no es la de create_belt_conveyor (esa se detecta, y si su
      tambor no tiene junta se usa la virtual '{comando}_eje_motriz'): [{pieza, junta_motriz,
      radio_mm?, direccion_transporte?, mu?, mu_cama?}].
    - juntas: {nombre: {amortiguamiento, friccion, armadura}}.
    - con_autodeteccion: cuenta los contactos geométricos como sujeción (exploración); por
      defecto sólo lo DECLARADO, como gravity_test.
    - opciones: fps, timestep (1 ms), nstep (2), gravedad, modelo_banda ('contacto' |
      'rapido'), colisiones_maquina, auto_bandas.
    duracion_s ≤ 60. Devuelve resumen (velocidades finales de juntas, bandas y productos,
    productos caídos, juntas en su límite, factor de tiempo real), motores (consigna, kv,
    tope), sensores, cuerpos y avisos. Con `path` escribe además un GIF de la marcha a tiempo
    real (corre la simulación otra vez). Read-only: NO modifica el modelo."""
    body: dict = dict(opciones or {})
    propios = {"motores": motores, "productos": productos, "sensores": sensores,
               "bandas": bandas, "juntas": juntas}
    repetidas = sorted(k for k in body if k in propios or k in ("duracion_s", "con_autodeteccion"))
    if repetidas:
        raise RuntimeError(f"{repetidas} van como parámetros de simulate, no dentro de 'opciones'")
    body.update({k: v for k, v in propios.items() if v})
    body["duracion_s"] = duracion_s
    body["con_autodeteccion"] = con_autodeteccion
    res = _srv._api("POST", "/api/physics/dynamics", json=body).json()
    out = {k: res[k] for k in _PARA_EL_AGENTE if k in res}
    out["sensores"] = {n: {k: v for k, v in s.items() if k != "muestras"}
                       for n, s in (res.get("sensores") or {}).items()}
    if path and not res.get("mensaje"):
        gif = _srv._api("POST", "/api/physics/dynamics.gif", json=body).content
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(gif)
        out["gif"] = str(target)
        out["bytes"] = len(gif)
    return json.dumps(out, ensure_ascii=False)
