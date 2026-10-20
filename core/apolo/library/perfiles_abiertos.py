"""Marco de los perfiles ABIERTOS del catálogo (canal U, viga I, ángulo L): sus anclas por
familia y su orientación declarativa (plan perfiles-con-acuerdo, D3 y D4).

Marco LOCAL de los builders (`builders.py`: `channel`, `i_beam`, `angle`), extruidos en Z y
centrados en su caja:

- canal U: alma en x = −b/2 … −b/2 + tw, alas hacia +x (abre hacia +x), altura h en Y;
- viga I: alma centrada en x = 0, altura h en Y, alas a lo ancho de X;
- ángulo L: talón (arista exterior del vértice) en (−leg/2, −leg/2); el ala 1 sale del talón
  hacia +x y el ala 2 hacia +y.

Anclas (coords LOCALES; `insert_component` las lleva a mundo con la pose y todo lo que mueve
la pieza las arrastra; un taladro las conserva aunque borre `Feature.matrix`). Las de CARA
tienen el origen sobre la cara y el eje = su normal saliente (lo que un mate `coincidente`
espera):

- U: `cara_alma_interior` (centro de la cara interior del alma, eje hacia la abertura),
  `dorso_alma` (cara exterior); I: `cara_alma_interior` (+x) y `cara_alma_opuesta` (−x);
- U/I con r1: `zona_plana` (centro de la zona plana de la cara interior del alma, eje = su
  normal) y `zona_plana_1` / `zona_plana_2`, los dos LÍMITES de esa zona (a `s` del canto de
  cada ala, `acuerdos.inicio_zona_plana_alma`) con el eje a lo largo de h hacia el centro: un
  asiento de radio ρ cabe si su centro queda a ≥ ρ de ambos medido sobre su eje;
- L: `talon` (eje = el largo), `cara_ala_1` / `cara_ala_2` (centro de la cara interior de cada
  ala, eje = su normal interior) y, con r1, `zona_plana_ala_1` / `zona_plana_ala_2` (centro de
  la zona plana [t + r1, leg − r2] de cada ala, misma normal).

Funciones PURAS: no conocen la escena ni el `Document`.
"""

from __future__ import annotations

from .acuerdos import inicio_zona_plana_alma, zona_plana_ala_angulo

# ------------------------------------------------------------------------- anclas (D4)


def _a(origin, axis) -> dict:
    return {"origin": [float(c) for c in origin], "axis": [float(c) for c in axis]}


def _zona_plana_alma(x_cara: float, normal: tuple, h: float, specs: dict | None) -> dict:
    s = inicio_zona_plana_alma(specs or {})
    if s is None:
        return {}
    m = h / 2.0 - s  # semiancho de la zona plana (> 0: lo valida `acuerdos.validar_acuerdo`)
    return {
        "zona_plana": _a((x_cara, 0, 0), normal),
        "zona_plana_1": _a((x_cara, -m, 0), (0, 1, 0)),
        "zona_plana_2": _a((x_cara, m, 0), (0, -1, 0)),
    }


def anclas_canal(h: float, b: float, tw: float, tf: float, specs: dict | None = None) -> dict:
    x_int = -b / 2.0 + tw
    return {
        "cara_alma_interior": _a((x_int, 0, 0), (1, 0, 0)),
        "dorso_alma": _a((-b / 2.0, 0, 0), (-1, 0, 0)),
        **_zona_plana_alma(x_int, (1, 0, 0), h, specs),
    }


def anclas_viga_i(h: float, b: float, tw: float, tf: float, specs: dict | None = None) -> dict:
    return {
        "cara_alma_interior": _a((tw / 2.0, 0, 0), (1, 0, 0)),
        "cara_alma_opuesta": _a((-tw / 2.0, 0, 0), (-1, 0, 0)),
        **_zona_plana_alma(tw / 2.0, (1, 0, 0), h, specs),
    }


def anclas_angulo(leg: float, t: float, specs: dict | None = None) -> dict:
    cara = -leg / 2.0 + t  # coordenada de la cara interior de cada ala
    out = {
        "talon": _a((-leg / 2.0, -leg / 2.0, 0), (0, 0, 1)),
        "cara_ala_1": _a((t / 2.0, cara, 0), (0, 1, 0)),
        "cara_ala_2": _a((cara, t / 2.0, 0), (1, 0, 0)),
    }
    zona = zona_plana_ala_angulo(specs or {})
    if zona is not None:
        medio = -leg / 2.0 + (zona[0] + zona[1]) / 2.0
        out["zona_plana_ala_1"] = _a((medio, cara, 0), (0, 1, 0))
        out["zona_plana_ala_2"] = _a((cara, medio, 0), (1, 0, 0))
    return out


#: Anclas por FAMILIA (builder → función de los params del builder + `specs` de norma). El
#: loader las une a las demás (`merge_anclas`) y le pasa `specs` porque la declaran.
ANCLAS = {"channel": anclas_canal, "i_beam": anclas_viga_i, "angle": anclas_angulo}

# --------------------------------------------------------------- orientación (D3)

_EJES = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}
_NOMBRE = {"channel": "canal U", "i_beam": "viga I", "angle": "ángulo L"}
#: claves de `orientacion` que pide (obligatorias, opcionales) cada familia
_CLAVES = {
    "channel": (("largo", "abre_hacia"), ()),
    "i_beam": (("largo", "canto"), ()),
    "angle": (("alas",), ("largo",)),
}


def _vec(d: str) -> tuple[float, float, float]:
    """'+x' / '-y' / 'z' → vector unitario del mundo (sin signo = +)."""
    signo = -1.0 if d.startswith("-") else 1.0
    eje = d.lstrip("+-").lower()
    if eje not in _EJES:
        raise ValueError(f"dirección '{d}' inválida (usa +x, -x, +y, -y, +z o -z)")
    return tuple(signo * c for c in _EJES[eje])


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b) -> tuple[float, float, float]:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _perpendiculares(a, b, que: str) -> None:
    if abs(_dot(a, b)) > 1e-9:
        raise ValueError(f"{que} deben ser perpendiculares")


def _euler(x, y, z) -> tuple[float, float, float]:
    from apolo.kernel.matrix import euler_from_matrix, frame

    rx, ry, rz = euler_from_matrix(frame((0.0, 0.0, 0.0), x, y, z))
    # los giros son rectos: se limpia el ruido de coma flotante (y el −0.0)
    return tuple(round(v, 6) + 0.0 for v in (rx, ry, rz))


def rotacion_por_orientacion(familia: str, orientacion: dict) -> tuple[float, float, float]:
    """Euler XYZ (grados, la convención de `rotation`) que deja un perfil abierto de la familia
    `familia` (builder del catálogo) como dice `orientacion`, por ejes del mundo:

    - canal U: `largo` + `abre_hacia` (del alma hacia la punta de las alas: el eje del ancla
      `cara_alma_interior`);
    - viga I: `largo` + `canto` (eje de la altura h);
    - ángulo L: `alas` = [hacia dónde sale el ala 1, el ala 2] desde el talón (`largo`, si
      viene, se comprueba: es el eje perpendicular a las dos).

    El signo de `largo` y de `canto` no cambia nada (el perfil es simétrico en esos ejes).
    ValueError con el porqué si la familia no es un perfil abierto o la orientación no cierra."""
    if familia not in _CLAVES:
        raise ValueError("orientacion sólo vale para perfiles abiertos del catálogo (canal U, "
                         "viga I, ángulo L); para lo demás usa rotation")
    nombre = _NOMBRE[familia]
    obligatorias, opcionales = _CLAVES[familia]
    dadas = {k for k, v in orientacion.items() if v is not None}
    faltan = [k for k in obligatorias if k not in dadas]
    sobran = sorted(dadas - set(obligatorias) - set(opcionales))
    if faltan or sobran:
        pide = " + ".join(obligatorias) + (f" (opcional: {', '.join(opcionales)})" if opcionales else "")
        raise ValueError(f"un {nombre} se orienta con {pide}"
                         + (f"; faltan: {', '.join(faltan)}" if faltan else "")
                         + (f"; no aplica: {', '.join(sobran)}" if sobran else ""))
    if familia == "angle":
        d1, d2 = (_vec(d) for d in orientacion["alas"])
        _perpendiculares(d1, d2, "las dos alas")
        z = _cross(d1, d2)
        if "largo" in dadas and abs(abs(_dot(_vec(orientacion["largo"]), z)) - 1.0) > 1e-9:
            raise ValueError("en un ángulo L el largo es el eje perpendicular a las dos alas")
        return _euler(d1, d2, z)
    largo = tuple(abs(c) for c in _vec(orientacion["largo"]))
    if familia == "channel":
        abre = _vec(orientacion["abre_hacia"])
        _perpendiculares(largo, abre, "largo y abre_hacia")
        return _euler(abre, _cross(largo, abre), largo)
    canto = tuple(abs(c) for c in _vec(orientacion["canto"]))
    _perpendiculares(largo, canto, "largo y canto")
    return _euler(_cross(canto, largo), canto, largo)

