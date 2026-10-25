"""Las señales de un tablero y su tipo SIN correr la simulación (plan V8.3 F6b, defecto 2).

`set_scenario` aceptaba «-T2.falla == true» y el error de tipo aparecía recién en el veredicto,
tras 17 s de simulación. Aquí se arma la tabla {señal D10: valor en reposo} del tablero:
  - cada modelo (`modelos/`) armado con su ficha y sus ajustes (un ajuste obligatorio que falta
    toma el punto medio, como `ajustes_faltantes`: sólo importa el TIPO) da sus `senales()`, y
    el que toma fallas, su «averia» (texto, «» sin falla: cosim-fallas D5), y una protección su
    «I_disparo_A» (número: sólo existe tras disparar, plan pedidos-de-extensiones D7);
  - cada PLC con programa da sus variables («-K1.Main.cuenta») y «estado»/«falla» (textos), como
    las publica el planificador (`_fuentes_plc`).
`revisar(aserciones, valores)` cruza las aserciones con esa tabla, con las mismas reglas que el
veredicto (`Lector.resolver`, `concretar`, `tipo_incompatible`): un tipo que no casa es ERROR;
una señal que el dispositivo no da es AVISO (puede venir de la red o de la mecánica). Lo que no
nombra un dispositivo con modelo («c1_banda.v_m_s», «-W1.1.I_A») no se revisa.

Puro: de `apolo` importa `cosim` y `plc`, como el planificador.
"""

from __future__ import annotations

from .modelos import MODELOS, Fusible, RecolectorAjustes
from .modelos.protecciones import CorrienteDeDisparo
from .neumatica import MODELOS_AIRE
from .veredicto import Lector, tipo_incompatible


def valores_iniciales(dispositivos, programas=()) -> dict:
    """{señal: valor en reposo}. `dispositivos` con designacion, ref, modelo, ajustes y cantidad;
    `programas` con plc, compilado, ciclo_ms y ciclos (los de `electrico.modelo` o del snapshot)."""
    from apolo.plc import PLC, SIN_TENSION

    out: dict = {}
    for d in dispositivos:
        modelo = d.modelo or {}
        clase = MODELOS.get(modelo.get("tipo"))
        if clase is None and isinstance(modelo.get("aire"), dict):  # V8.9: cilindro, FRL, corte
            clase, modelo = MODELOS_AIRE.get(modelo["aire"].get("tipo")), modelo["aire"]
        if clase is None:
            continue
        p = RecolectorAjustes(d.designacion, d.ref, modelo, d.ajustes)
        try:
            m = clase(p, int(d.cantidad or 1)) if clase is Fusible else clase(p)
            out.update(m.senales())
            if m.FALLAS:  # la avería (cosim-fallas D5) es texto: «» sin falla
                out[f"{d.designacion}.averia"] = ""
            if isinstance(m, CorrienteDeDisparo):  # D7: un número que aparece al disparar
                out[f"{d.designacion}.I_disparo_A"] = 0.0
        except Exception:  # noqa: BLE001 — un modelo incompleto lo dice el snapshot; aquí no hay tipos
            continue
    for prog in programas:
        if getattr(prog, "compilado", None) is None:
            continue
        try:
            variables = PLC(prog.compilado, ciclo_ms=prog.ciclo_ms, ciclos=dict(prog.ciclos) or None).variables()
        except Exception:  # noqa: BLE001 — sin runtime no hay tipos que revisar
            continue
        out.update({f"{prog.plc}.{k}": v for k, v in variables.items()})
        out[f"{prog.plc}.estado"], out[f"{prog.plc}.falla"] = SIN_TENSION, ""
    return out


def revisar(aserciones: list[dict], valores: dict) -> tuple[list[str], list[str]]:
    """(errores, avisos) de las aserciones leídas (`leer_aserciones`) contra la tabla."""
    from .aserciones import concretar

    lec = Lector({"final": valores})
    con_tabla = {n.split(".")[0] for n in valores}
    errores, avisos = [], []
    for a in aserciones:
        des = a["senal"].split(".")[0]
        if des not in con_tabla:
            continue
        n, motivo = lec.resolver(a["senal"], "entre las que da el tablero")
        if n is None:
            avisos.append(f"«{a['texto']}»: {motivo}")
            continue
        tipo, ejemplo = lec.tipo(n)
        reposo = valores.get(n)
        a2, error = concretar(a, tipo, ejemplo)
        if not error and a.get("implicita") and tipo == "texto" and reposo:
            error = (f"«{n}» es un texto que en reposo ya vale «{reposo}»: la forma sin comparación "
                     f"(«no vacío») se cumpliría sin que pase nada; compárala con el texto que "
                     f"esperas («{n} == …»)")
        error = error or tipo_incompatible(n, a2["valor"], lec)
        if error:
            errores.append(f"«{a['texto']}»: {error}")
    return errores, avisos
