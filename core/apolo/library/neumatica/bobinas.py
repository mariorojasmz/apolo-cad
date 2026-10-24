"""Las bobinas de una electroválvula en el lado ELÉCTRICO (plan V8.9 D1, D6; F1b).

Una electroválvula es UN dispositivo del carril con sus vías (ficha `neumatico:`) y sus bobinas
(ficha `electrico:`): cada bobina es una carga `bobina` del mando, como la de un contactor, y la
red eléctrica la ve (tensión cruzada, borne suelto). La ficha neumática dice de qué LADO va cada
bobina (ISO 5599-3: la 14 conecta 1→4, la 12 conecta 1→2) y su tensión; la eléctrica, los bornes.
Este módulo es la convención que las une, y el loader la hace cumplir al cargar:

  - una bobina sola: bornes «A1» y «A2» (el marcado de bornes de la bobina de un aparato de
    maniobra, IEC 60947-1 anexo L, el mismo del contactor del catálogo), sea del lado 14 (una
    5/2 monoestable) o del 12 (una 3/2);
  - dos bobinas (biestable, 5/3): «14A1»/«14A2» y «12A1»/«12A2», el lado delante del borne
    («-QM1:14A1»), como se rotula una válvula de dos bobinas con su número de mando;
  - cada carga `bobina` de la ficha eléctrica es una de esas parejas, con la MISMA tensión que
    `modelo.tension_bobina`; no sobra ni falta ninguna.

Puro (biblioteca estándar): la tensión la normaliza quien llama (`normalizar`), así este paquete
no importa `library/electrico`.
"""

from __future__ import annotations

from collections.abc import Callable


def bornes_bobina(lados) -> dict[str, tuple[str, str]]:
    """{lado: (A1, A2)} de las bobinas de una válvula, por la convención del módulo."""
    lados = [str(x) for x in lados]
    if len(lados) == 1:
        return {lados[0]: ("A1", "A2")}
    return {lado: (f"{lado}A1", f"{lado}A2") for lado in lados}


def lados_con_bobina(ficha) -> tuple[str, ...]:
    """Los lados con bobina de una `FichaNeumatica` (vacío si no es electroválvula)."""
    m = getattr(ficha, "modelo", None) or {}
    return tuple(str(x) for x in m.get("bobinas") or ())


def verificar(neumatico, electrico, ref: str, normalizar: Callable[[str], str]) -> None:
    """Las bobinas de la ficha neumática contra las cargas de la eléctrica: `ValueError` con qué
    corregir. `normalizar(texto)` → la tensión en forma canónica («24 VDC»)."""
    lados = lados_con_bobina(neumatico)
    if not lados:
        if electrico is not None and any(c.tipo == "bobina" for c in electrico.cargas):
            raise ValueError(f"Componente '{ref}': la ficha neumática no declara `bobinas` y la eléctrica "
                             "tiene cargas de bobina: declara los lados con bobina («14», «12»)")
        return
    esperadas = bornes_bobina(lados)
    if electrico is None:
        ejemplo = "; ".join(f"{a1}/{a2} (bobina {lado})" for lado, (a1, a2) in esperadas.items())
        raise ValueError(f"Componente '{ref}': una electroválvula lleva su bloque `electrico:` con sus "
                         f"bobinas como cargas `bobina` del mando: bornes {ejemplo} (plan V8.9 D1)")
    tension = normalizar(neumatico.modelo["tension_bobina"])
    cargas = {tuple(c.bornes): c for c in electrico.cargas if c.tipo == "bobina"}
    for lado, par in esperadas.items():
        c = cargas.pop(par, None)
        if c is None:
            raise ValueError(f"Componente '{ref}': falta la carga `bobina` de la bobina {lado} entre los "
                             f"bornes {par[0]}–{par[1]} (V8.9 F1b: una bobina sola es A1/A2; dos, "
                             "14A1/14A2 y 12A1/12A2)")
        if normalizar(str(c.tension)) != tension:
            raise ValueError(f"Componente '{ref}': la bobina {lado} es de {c.tension} en la ficha eléctrica "
                             f"y de {neumatico.modelo['tension_bobina']} en la neumática: una sola tensión")
    if cargas:
        raise ValueError(f"Componente '{ref}': cargas de bobina que la ficha neumática no tiene: "
                         f"{', '.join('–'.join(b) for b in cargas)}")
