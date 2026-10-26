"""Builders geométricos genéricos del catálogo (data-driven).

Cada builder es una *factory* `(**params) -> ((length|None) -> shape)`: recibe
los parámetros fijos declarados en el YAML del componente y devuelve la función
que el catálogo invoca con la longitud de corte (o None). La forma se construye
centrada en el origen, eje Z hacia arriba (convención del kernel).

FACHADA (plan partir-nucleo-congelado-ii, F1): los builders viven por familia en
`builders_estructura`, `builders_accionamiento`, `builders_rodamientos`,
`builders_tornilleria` y `builders_carpinteria`; aquí se re-exportan por IDENTIDAD, para
siempre (`tests/test_rutas_viejas.py`), y queda `BUILDERS` con el mismo texto y orden. Un
builder NUEVO va a su módulo de familia (o uno propio) con su registro, que `loader.py` une;
los componentes del catálogo lo referencian por nombre (campo `builder`).
"""

from __future__ import annotations

from .builders_estructura import (  # noqa: F401
    profile, rect_tube, cylinder, box, leg, guard, leveling_foot, round_tube, angle, channel,
    i_beam,
)
from .builders_accionamiento import (  # noqa: F401
    roller, drum, motor, worm_gearmotor, pulley, v_pulley, tensioner, take_up,
)
from .builders_rodamientos import (  # noqa: F401
    sensor, bearing, linear_rail, linear_block, pillow_block, flange_bearing, endstop,
)
from .builders_tornilleria import (  # noqa: F401
    screw, _hex_prism, hex_bolt, hex_nut, socket_cap, wood_screw,
)
from .builders_carpinteria import (  # noqa: F401
    butt_hinge, piano_hinge, euro_hinge, pull_handle, knob, butt_hinge_half, spring_hinge,
    mortise_lock, magnetic_catch, door_rail, door_carriage, drawer_slide,
)


BUILDERS = {
    "profile": profile,
    "rect_tube": rect_tube,  # tubo estructural rectangular de acero (hueco)
    "cylinder": cylinder,
    "roller": roller,  # rodillo con eje pasante
    "drum": drum,  # tambor/polea motriz con eje
    "box": box,
    "motor": motor,
    "worm_gearmotor": worm_gearmotor,  # motorreductor sinfín-corona NMRV, eje hueco + motor perpendicular (frame IEC real)
    "leg": leg,
    "guard": guard,
    "sensor": sensor,
    "bearing": bearing,
    "screw": screw,
    "linear_rail": linear_rail,
    "linear_block": linear_block,
    "pulley": pulley,
    "v_pulley": v_pulley,  # polea en V (sheave) para faja de potencia, sección A/B (ISO 4183)
    "pillow_block": pillow_block,      # chumacera de pie UCP
    "flange_bearing": flange_bearing,  # chumacera de brida UCF/UCFL
    "endstop": endstop,
    "leveling_foot": leveling_foot,
    "tensioner": tensioner,
    "take_up": take_up,  # tensor tipo trotadora (faja de banda, sin chumacera)
    "hex_bolt": hex_bolt,  # perno cabeza hexagonal DIN 933 (comercial)
    "hex_nut": hex_nut,  # tuerca hexagonal DIN 934
    "socket_cap": socket_cap,  # tornillo Allen (cabeza cilíndrica + hexágono interior) DIN 912
    "round_tube": round_tube,  # tubo redondo de acero (hueco)
    "angle": angle,  # ángulo L de lados iguales
    "channel": channel,  # perfil U / canal (UPN)
    "i_beam": i_beam,  # viga doble T (IPE/IPN)
    # carpintería / herraje
    "butt_hinge": butt_hinge,  # bisagra de pala (libro)
    "butt_hinge_half": butt_hinge_half,  # media bisagra (articulación fiel: 2 mitades)
    "spring_hinge": spring_hinge,  # bisagra de resorte / soft-close
    "mortise_lock": mortise_lock,  # cerradura de embutir
    "magnetic_catch": magnetic_catch,  # tope/cierre magnético
    "piano_hinge": piano_hinge,  # bisagra continua (piano), cortable
    "euro_hinge": euro_hinge,  # bisagra europea de cazoleta (mueble)
    "pull_handle": pull_handle,  # tirador de barra
    "knob": knob,  # pomo
    "wood_screw": wood_screw,  # tirafondo
    "drawer_slide": drawer_slide,  # corredera de cajón, cortable
    "door_rail": door_rail,  # riel U para puerta corrediza/colgante (U-100), cortable
    "door_carriage": door_carriage,  # corredera colgante de 4 ruedas (D-100)
}
