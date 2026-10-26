"""La versión del motor de la co-simulación no se olvida (plan V8.3 F6b, defecto 1).

La vigencia de un resultado de escenario es firma del documento + hash del escenario +
`COSIM_EPOCH` (`apolo/cosim/__init__.py`). Si el código que produce o evalúa el resultado cambia
y la versión no sube, la puerta de entrega sigue en VERDE con resultados que el código nuevo
ya no daría (lo midió la re-verificación F6b: 3 de 4 escenarios «vigentes» fallaban).

Trinquete al estilo de `tests/test_contrato_comandos.py`: `HUELLA` guarda `(versión, huella del
código)`. Si la huella cambió y la versión no, falla y obliga a decidir:
  - el cambio puede cambiar el resultado o el veredicto de un escenario con el MISMO documento →
    sube `COSIM_EPOCH` (todos los resultados guardados quedan «vencidos»);
  - fue un refactor sin efecto → actualiza sólo la huella.
`python tests/test_cosim_epoch.py` imprime el literal para pegar.

La huella cubre el código del motor (`ARCHIVOS`); el catálogo eléctrico NO va aquí: sus fichas
entran a la firma del documento (`services/escenarios._fichas_electricas`), así un YAML vence
sólo los documentos que usan esa ref.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from apolo.cosim import COSIM_EPOCH

RAIZ = Path(__file__).resolve().parents[1] / "core" / "apolo"

#: Lo que decide el resultado de una co-simulación dado el documento y el escenario.
ARCHIVOS = (
    "cosim/**/*.py",
    "library/electrico/acoples.py",
    "plc/**/*.py",
    "physics/banda.py",
    "physics/dinamica.py",
    "physics/dinamica_arrastre.py",
    "physics/dinamica_control.py",
    "physics/dinamica_cuerpos.py",
    "physics/dinamica_datos.py",
    "physics/dinamica_flujo.py",
    "physics/dinamica_integrador.py",
    "physics/dinamica_modelo.py",
    "physics/dinamica_motores.py",
    "physics/dinamica_nacimiento.py",
    "physics/dinamica_peticion.py",
    "physics/hull.py",
    "physics/sensores.py",
    "physics/sim.py",
    "services/cosim_aire.py",
    "services/cosim_bandas.py",
    "services/cosim_red.py",
    "services/cosim_snapshot.py",
    "services/escenario_ajustes.py",
)

#: V8.4 F1 (sin subir): el paso compartido lote/vivo da la MISMA huella de trazas (la 77 en sus
#: tres casos de F0 y `tests/test_cosim_vivo.py` contra el bucle de V8.3); `sumideros` sólo deja
#: correr escenarios que antes eran 400 y el color/pieza del snapshot no entran al resultado.
#: V8.4 F4 (sin subir): `services/escenarios.py` sólo saca `validar_nombre` y `no_existe` a
#: públicos (los usa `sesion_viva.py`); la vigencia y la lectura no cambian.
#: 4 — V8.4, cola en vivo: la caja de la cola nace sólo con su lugar de entrada libre
#: (`physics/dinamica_nacimiento.py`). Los 5 escenarios de la 77 dan la misma huella (su banda
#: anda antes de que toque la segunda caja), pero un escenario cuya cola encimaba cajas cambia.
#: nucleo-abierto F1a (sin subir): el snapshot lleva los modelos de EXTENSIÓN del tablero
#: (`modelos_extension`, `extensiones`) y el worker los registra; sin extensiones van vacíos y
#: ningún resultado cambia. Su vigencia (la versión de la extensión) va en `services/escenarios`.
#: cosim-fallas F1a (sin subir, D8): las fallas a propósito (`Modelo.FALLAS`, el evento `falla`,
#: la máscara de contactos pegados) sólo actúan con un evento `falla`; sin él las salidas son las
#: de antes: 9 escenarios del banco (marcha, seta, atasco, fase, cable, cajas, sensor pegado,
#: caída de red, atasco parcial) dan la MISMA huella antes y después (bitácora del plan).
#: mandos-de-seguridad F1 (sin subir, D5): modelos NUEVOS (`resguardo`, `rele_seguridad`), el
#: tablero lee los que declaran `BORNES_ENTRADA` y el vocabulario `pide` suma «salida»; sin esos
#: aparatos nada cambia: 11 escenarios del banco (los 9 de arriba, la seta por variador y el NC de
#: la seta pegado) dan la MISMA huella que en bf69175 (bitácora del plan).
#: mandos-de-seguridad F1b (sin subir): `vivo_fotograma.MANDOS` suma `resguardo`; sólo cambia lo
#: que la tabla del `inicio` ofrece en vivo, no el paso ni ninguna traza.
#: V8.5 F5b (sin subir, D8): la red toma el largo CALCULADO (ruteo del tablero armado, recorrido
#: `por`) de lo que no declara `largo_m`; con todo declarado, o sin tablero armado ni `por` (el
#: banco y la 77 original), la entrada de la red es idéntica. Lo que sí cambia (un documento con
#: largos calculados y un resultado de antes) lo vence la firma v1 (`services/escenarios`).
#: V8.9 F3 (sin subir, D14): la co-simulación del aire (`cosim/neumatica`, la electroválvula, el
#: acople del cilindro, los eventos del aire, `services/cosim_aire.py`) sólo actúa con un circuito
#: de aire; el tablero cambió cómo saca de la red una carga con falla (por bobina) y suma el índice
#: de las válvulas, sin efecto sin ellas: 9 escenarios del banco (marcha, seta, atasco parcial,
#: contactor soldado y no_cierra, piloto fundido, corte de fase, cajas con seta y sensor pegado)
#: dan la MISMA huella que en 06d44ac. Un documento con válvulas cambia de firma por su ficha
#: eléctrica (el `modelo` nuevo de la bobina): sus resultados de antes quedan vencidos solos.
#: datos-de-corte-y-acometida F1b (sin subir, D11): modelo NUEVO (`diferencial`, la residual por
#: fasores), indexado aparte en el tablero; las demás protecciones siguen recibiendo los mismos
#: módulos (`_corriente` = |`_fasor`|, bit a bit). Ningún documento existente usa el tipo: 10
#: escenarios del banco (marcha, seta, atasco parcial, contactor soldado y no_cierra, piloto
#: fundido, corte de fase, corto entre fases, cajas con seta y sensor pegado) dan la MISMA huella
#: que en 194e119 (bitácora del plan).
#: 5 — datos-de-corte-y-acometida F1c (D7, D11): el esquema de tierra se lee del AJUSTE de la red
#: (antes se ignoraba) y la red entiende TN-S, TN-C-S, TT (con `RA_ohm`: el PE unido a tierra por
#: 1/RA, `FuenteRed.R_tierra_ohm`) e IT; con `Icc_kA` ajustado la hipótesis ya no dice «SUPUESTA».
#: Un documento con esos ajustes cambia de resultado con el MISMO log. Sin esquema la entrada de la
#: red es idéntica: 5 escenarios del banco (marcha, seta, caída de red, corto entre fases y el
#: variador) dan la MISMA huella que en 1f01d0a (bitácora del plan).
#: V8.9 F6 (sin subir): `vivo_fotograma.tabla` suma `valvulas` (las electroválvulas y su
#: accionamiento manual, sólo si hay); sólo cambia lo que el `inicio` ofrece en vivo, no el paso
#: ni ninguna traza (como la F1b de mandos-de-seguridad). La electroválvula con manual publica
#: `manual` (el lado enclavado, texto): sólo existe con válvulas; un escenario sin aire no cambia.
#: El FRL publica `p_red_bar` y la tabla del `inicio` lleva la carrera de cada cilindro: sólo con
#: aire, ninguna traza sin él.
#: 6 — V8.9 F7b (defectos 5, 6 y 7): el producto publica `y_mm`/`z_mm` (trazas nuevas en todo
#: escenario con productos); la colisión de la dinámica lleva un casco convexo por SÓLIDO
#: (`physics/hull.cascos`: una pieza de varios sólidos cambia de MJCF; con un sólido, el de antes);
#: «== 14» contra un texto numérico («-QM2.posicion») se compara como texto (antes, error de tipo).
#: Las analógicas de la mecánica guardan 0.0 en vez de -0.0 (`trazas.py`: la y de un producto
#: centrado cambiaba de signo de cero entre el vivo y el worker).
#: plc-en-el-lazo F1a (sin subir, D14): el lexer junta los comentarios en el árbol SÓLO si le
#: pasan una lista; los tokens no cambian: 154 programas (los de `test_plc_*`, el del banco y el
#: sintético) compilan idénticos y 6 escenarios del banco (marcha y seta por variador, seta, caída
#: de red, corte de fase, cajas con seta, atasco) dan la MISMA huella que en 833ce8e (bitácora).
#: plc-en-el-lazo F1b1 (sin subir, D14): la corrida usa una CARA del PLC (`cosim/puerto_plc.py`) y
#: el PLC de AFUERA (`cosim/externo.py`, `cosim/ritmo.py`) entra sólo si el PEDIDO lo trae
#: (`externos` del snapshot); con externo la corrida no es determinista ni se guarda (no es
#: vigente). Sin externo, `Corrida`, el bucle y el resultado son los de antes: 6 escenarios del
#: banco (marcha y seta por variador, seta en directo, caída de red, corte de fase, cajas con seta,
#: atasco) dan la MISMA huella y las mismas claves del resultado y del compacto que en 4f669f0.
#: plc-en-el-lazo F1c1 (sin subir, D10, D14): la acción `escribir` (la tabla de símbolos del
#: `Compilado`, `PLC.escribir`, la agenda con los PLC de la corrida) sólo actúa si el escenario la
#: trae; `leer` resuelve igual (y ahora también un elemento de un ARRAY global). Sin `escribir`:
#: 6 escenarios del banco (marcha y seta por variador, seta en directo, caída de red, corte de
#: fase, cajas con seta, atasco) dan la MISMA huella, claves y eventos que en fc734ea (bitácora).
#: plc-en-el-lazo F1b2 (sin subir, D8, D9, D14): la sesión EN VIVO con un PLC de afuera
#: (`cosim/vivo_lazo.py`: un intercambio por vez a ritmo de pared, la pausa por lazo cortado) y
#: la respuesta de una acción inyectada que corta el lazo (`agenda.py`) y el intercambio que
#: sigue desde el PLC que cortó (`Corrida._reanudar`) sólo actúan con `externos`; sin ellos el
#: vivo y el lote son los de antes: 6 escenarios del banco y una sesión viva cerrada como lote
#: dan la MISMA huella, claves y eventos que en 489af7d (bitácora).
#: pedidos-de-extensiones F2 (sin subir, D4): la regla de quién mueve un bloque auxiliar sale de
#: `services/cosim_red.py` a `library/electrico/acoples.py` (suma a `ARCHIVOS`), el carril la deja
#: en `Dispositivo.acoplado_a` y la red la LEE; la regla es la misma, byte a byte en su resultado:
#: la entrada de red de los cuatro tableros de `tablero_electrico.py` es idéntica (ramas,
#: actuadores, avisos) y 7 escenarios del banco (marcha, seta, caída de red y atasco parcial en
#: directo; seta, corte de fase y cajas con seta por variador) dan la MISMA huella, claves y
#: eventos que en ec4ac9b (bitácora del plan).
#: pedidos-de-extensiones F4 (sin subir, D8): el motor publica `U_V` (la tensión que ya usaba su
#: paso) y cada protección `I_disparo_A` SÓLO tras disparar (como `averia`; el diferencial,
#: `I_residual_disparo_mA`: dispara por la residual); `tipos.py` las tipa. Ningún valor que ya se
#: publicaba cambia: 11 escenarios del banco (marcha, seta, caída de red, atasco que dispara,
#: atasco parcial, cortos en el motor y en la fuente de 24 V y guardamotor `abierto` en directo;
#: seta, corte de fase y cajas con seta por variador) dan trazas SIN las señales nuevas, eventos,
#: finales, claves y veredicto por aserción IDÉNTICOS a 1ff0679, y los dos tableros de
#: `test_cosim_diferencial.py` con su corto a PE, las mismas señales paso a paso; la huella de
#: cada escenario cambia sólo por la traza nueva (bitácora del plan).
#: cotizacion-identificada-y-ajustes-por-escenario F2 (sin subir, D5–D6): el escenario acepta
#: `ajustes` de PRUEBA (`cosim/escenario.py` lee la forma, `services/escenario_ajustes.py` —suma a
#: `ARCHIVOS`— los valida y los pone encima en una COPIA del modelo del tablero, el snapshot los
#: lista en `CosimSnapshot.ajustes`). Sólo actúan si el escenario los trae y entran a SU hash: sin
#: ellos, 5 escenarios del banco (marcha con cajas, seta y atasco parcial por variador; marcha y
#: atasco parcial en directo) dan la MISMA huella, hipótesis, finales, claves del resultado y del
#: compacto, hash de escenario y firma del documento que en 712a9bd (bitácora del plan).
#: cotizacion-identificada-y-ajustes-por-escenario, pendientes de cierre (sin subir): la validación
#: de los ajustes de un aparato de aire sale del privado `commands/neumatica_eval._ajustes` a
#: `library/electrico/ajustes.validar_ajustes_neumaticos` (pública, pura) y
#: `services/escenario_ajustes.py` la llama con los rangos y el `modelo` en vez de fichas falsas;
#: es el mismo código, línea a línea: mismos valores validados y mismos errores (los tests de
#: neumática y de ajustes por escenario pasan sin tocar sus expectativas). Ningún resultado cambia.
#: V8.9 F8 (sin subir, D14): modelo NUEVO (`presostato`, `cosim/modelos/presostato.py`) que el
#: tablero indexa por `LEE_PRESION` (su contacto es el actuador «señal», como el de un sensor) y
#: la red de aire le da la presión de su línea (`RedAire.presion_bar`); el puerto de un
#: presostato no cuenta en la cadena de una cámara; su falla `pegado` sólo actúa con un evento
#: `falla`. Sin presostato nada de eso corre: 7 escenarios
#: del banco (marcha y atasco parcial en directo; marcha con cajas y atasco parcial por variador;
#: el empujador de aire, su corte de aire y la biestable con detector) dan la MISMA huella,
#: hipótesis, finales, claves del resultado, hash de escenario y firma del documento que en
#: 0afb41c (bitácora del plan).
#: pedidos-de-extensiones-ii, D-f de la F2 (sin subir): el aviso de `services/cosim_red.py` por un
#: punto que no resuelve nombra el conductor con `redes.nombre_conductor` (sus puntos y
#: `[hilo, red]`), no por su índice. Sólo cambia el TEXTO de ese aviso, que sale únicamente en un
#: circuito con una referencia rota; ningún valor, traza, evento ni veredicto se toca.
#: datos-de-corte-y-acometida, red de 220 V de Lima IT (sin subir): sólo el TEXTO del rechazo de un
#: corto a PE en IT (`fallas._PE_FUERA`: «la fuente no tiene punto a tierra», no «la estrella»): un
#: error de la petición, no un resultado. Que la red de Lima pase a IT de ficha cambia la ENTRADA de
#: la red (clave `esquema`, el PE sigue fuera como sin esquema) y lo vence la firma del documento
#: (su `modelo` entra a ella), no la época.
#: pedidos-de-extensiones-iii F2 (sin subir, D7): el variador detecta la DISCREPANCIA entre S1 y
#: S2 del STO (`STO_discrepancia_ms`, falla `sto_discrepancia` que se acusa con los dos canales o
#: cortando la red, como SINAMICS G120). Con S1 = S2 no actúa: 8 escenarios sanos (marcha, seta y
#: seta liberada por variador; la seta de dos NC; el relé de seguridad con el resguardo y con la
#: seta; la marcha en directo; el empujador de aire) dan la MISMA huella, finales e hipótesis que en
#: 9d3bb26. Lo que sí cambia (un canal pegado, un cableado de un solo canal) lo vence la firma: la
#: ficha del variador gana `STO_discrepancia_ms` y su `modelo` entra a ella.
#: 7 — pedidos-de-extensiones-iii F4 (D11): el vástago de un cilindro se mueve con la masa MÓVIL
#: de su ficha (`physics/dinamica_cuerpos.masas_de_ficha`) y `services/cosim_aire.py` ya no le
#: suma la masa en carrera 0 como armadura. El empujador de aire (sano) cambia de huella y de
#: final (x_mm del vástago −0,520 → −0,551 en reposo); los 7 escenarios eléctricos de la F2 dan la
#: MISMA huella y finales que en 9d3bb26.
#: balance-de-producto F1–F2 (sin subir, D12; sobre la 7 de pedidos-iii): el bloque `flujo` del escenario (`cosim/flujo.py`),
#: el rastreo del producto en el `Integrador` (`physics/dinamica_flujo.py`), los sumideros con
#: nombre y las señales `flujo.*` del veredicto sólo actúan con el bloque, que antes era 400 (clave
#: desconocida): ningún resultado guardado lo trae. Sin él, `_retirar` retira igual (sólo anota
#: cuál sumidero): 3 escenarios del banco (seta con cajas por variador, cajas con sumidero por
#: variador y en directo) dan la MISMA huella y la misma salida `mecanica` que en b9d774f.
#: 8 — balance-de-producto, trabas de flujo: el producto retirado por un sumidero conserva la
#: posición en que se retiró (`cosim/corrida._mecanica`). Sin sumidero, 2 escenarios del banco
#: (cajas por variador, marcha en directo) dan la MISMA huella, finales y eventos que en c826389;
#: con sumidero (cajas por variador y en directo) cambian sólo la huella y los finales `*_mm` de
#: las cajas que salieron. En el mismo cambio, sin efecto en ningún resultado: la dinámica de la
#: co-simulación toma el tope del ESCENARIO (300 s; antes un escenario de más de 60 s era 400 al
#: correr: ningún resultado guardado) y `flujo.ritmo_por_min` es el declarado (no entra al
#: snapshot).
HUELLA: tuple[int, str] = (8, "6d7524f32865d796")


def archivos() -> list[Path]:
    out = set()
    for patron in ARCHIVOS:
        hallados = list(RAIZ.glob(patron))
        assert hallados, f"el patrón {patron} no encuentra archivos: actualiza ARCHIVOS"
        out.update(hallados)
    return sorted(out)


def huella() -> str:
    """sha1 del código, sin depender de los finales de línea del checkout ni de la línea que
    declara la versión (subirla no es cambiar el motor)."""
    h = hashlib.sha1()
    for p in archivos():
        texto = p.read_text(encoding="utf-8").replace("\r\n", "\n")
        texto = "\n".join(ln for ln in texto.split("\n") if not ln.startswith("COSIM_EPOCH ="))
        h.update(p.relative_to(RAIZ).as_posix().encode())
        h.update(texto.encode("utf-8"))
    return h.hexdigest()[:16]


def problemas(declarada: tuple[int, str], version: int, actual: str) -> list[str]:
    v0, h0 = declarada
    if version < v0:
        return [f"COSIM_EPOCH BAJÓ de {v0} a {version}: nunca baja (un resultado viejo volvería a "
                "parecer vigente)"]
    if version > v0:
        return [f'subiste COSIM_EPOCH a {version}: declara HUELLA = ({version}, "{actual}")']
    if actual != h0:
        return [f"el código del motor de la co-simulación cambió y COSIM_EPOCH no (sigue en {v0})"]
    return []


def test_el_motor_no_cambia_sin_decidir_su_version():
    p = problemas(HUELLA, COSIM_EPOCH, huella())
    assert not p, (
        "Versión del motor de la co-simulación (V8.3 F6b):\n  " + "\n  ".join(p) + "\n"
        "Si el cambio puede cambiar el resultado o el veredicto de un escenario con el MISMO "
        "documento, sube COSIM_EPOCH (apolo/cosim/__init__.py): los resultados guardados quedan "
        "«vencidos». Si fue un refactor sin efecto, actualiza sólo la huella. Después pega el "
        "literal que imprime `python tests/test_cosim_epoch.py` (regla: core/apolo/cosim/CLAUDE.md)."
    )


def test_el_trinquete_distingue_los_tres_casos():
    assert problemas((2, "a"), 2, "a") == []
    assert "cambió" in problemas((2, "a"), 2, "b")[0]
    assert "subiste" in problemas((2, "a"), 3, "b")[0]
    assert "BAJÓ" in problemas((2, "a"), 1, "a")[0]


if __name__ == "__main__":
    print(f'HUELLA: tuple[int, str] = ({COSIM_EPOCH}, "{huella()}")')
