"""La cifra principal de cada grupo de la máquina: las etiquetas de la vista 3D de la tienda
(plan vista-3d-web, F2 · D3).

`cifras_grupos(doc, ids)` junta las piezas `ids` (las que muestra el GLB) por su grupo RAÍZ (un
subgrupo cuenta para su raíz: las etiquetas no se apilan unas sobre otras) y da de cada grupo
una `CifraGrupo`: su nombre, su cifra en una línea, cuántas piezas trae, cuánto pesa y dónde
anclar la etiqueta. Las piezas sin grupo no llevan etiqueta.

**La cifra** sale de las plantillas de los rótulos del video (`rotulos.plantilla` sobre
`datos_rotulos`): sólo cifras leídas del catálogo, de la geometría o de un cálculo del
documento, nunca escritas a mano. Las piezas del grupo se juntan por BASE de rol («Rodillo»,
«Larguero») y se prueban en este orden: primero la base que declara potencia (de un
motorreductor se pregunta el motor), después de más a menos masa, y sólo las que pesan al
menos `PESO_MINIMO` del grupo (si no, «24 pernos M10» hablaría por un bastidor). La primera con
plantilla da la cifra: «20 rodillos Ø2" cada 95,25 mm», «2 largueros de ángulo L 75x6 de
2 000 mm». Una pieza sola va por su base; si la base ES el nombre del grupo, sólo la cifra
(«0,37 kW a 30 rpm» bajo «Motorreductor»). Sin plantilla, el conteo y la masa del grupo
(«11 piezas · 42,5 kg»).

**Las anclas** son puntos del TOPE (z máxima, mm del documento) de las piezas de la base
elegida: su centro en planta y, en una pieza larga (≥ `ALARGADA` veces su ancho), también a ¼
y ¾ de su largo. Siempre sobre una pieza real, no en el centro de la caja del grupo, que en un
bastidor cae en el aire entre los largueros. Van ordenadas de la más cercana al centro del
grupo en planta a la más lejana: quien las use toma la primera o, para que las etiquetas de
grupos vecinos no se tapen, la que más se aleje de las ya puestas (`publicacion.vista3d_html`).

Capa `services`: `doc` explícito, sin locks; corre en el proceso de la publicación.
"""

from __future__ import annotations

from dataclasses import dataclass

from apolo.services.rotulos import base, cifra, corta, plantilla, plural, rol

#: Fracción de la masa del grupo que una base necesita para hablar por él.
PESO_MINIMO = 0.10
#: Tope de la cifra: una etiqueta de la vista 3D va en una línea corta.
MAX_CIFRA = 60
#: Una pieza tan larga en planta (largo/ancho) ofrece también anclas a ¼ y ¾ de su largo.
ALARGADA = 3.0
MAX_ANCLAS = 24
_TILDES = str.maketrans("áéíóúÁÉÍÓÚ", "aeiouAEIOU")


@dataclass(frozen=True)
class CifraGrupo:
    grupo: str
    cifra: str
    piezas: int
    masa_kg: float
    anclas_mm: tuple  # candidatos (x, y, z) del documento, Z arriba; el preferido primero

    @property
    def ancla_mm(self) -> tuple:
        return self.anclas_mm[0]


def grupo_raiz(grupo: str | None, grupos: dict) -> str | None:
    """El grupo raíz de `grupo` (él mismo si no tiene padre); None si no existe."""
    visto: set[str] = set()
    while grupo is not None and grupo in grupos and grupo not in visto:
        visto.add(grupo)
        padre = (grupos.get(grupo) or {}).get("parent")
        if padre is None or padre not in grupos:
            return grupo
        grupo = padre
    return None


def _caja(shape) -> tuple[tuple, tuple] | None:
    try:
        bb = shape.bounding_box()
    except Exception:  # noqa: BLE001 — una pieza sin caja no ancla, no tumba la publicación
        return None
    return (bb.min.X, bb.min.Y, bb.min.Z), (bb.max.X, bb.max.Y, bb.max.Z)


def _llano(texto: str) -> str:
    return " ".join(texto.lower().translate(_TILDES).split())


def _texto(grupo: str, b: str, fids: list, frase) -> str:
    if len(fids) == 1:
        sujeto = "" if _llano(b) == _llano(grupo) else b
    else:
        sujeto = f"{len(fids)} {frase.sustantivo or plural(b)}"
    desc = frase.desc if sujeto else frase.desc.removeprefix("de ")
    texto = f"{sujeto} {desc}".strip()
    rico = texto + frase.detalle
    return rico if len(rico) <= MAX_CIFRA else corta(texto, MAX_CIFRA)


def _sobre(caja) -> list[tuple]:
    """Puntos del tope de una pieza: el centro y, si es larga en planta (≥ `ALARGADA` veces
    su ancho), también a ¼ y ¾ de su largo."""
    (x0, y0, _), (x1, y1, z1) = caja
    cx, cy, lx, ly = (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0
    puntos = [(cx, cy, z1)]
    if lx >= ALARGADA * max(ly, 1e-6):
        puntos += [(cx - lx / 4, cy, z1), (cx + lx / 4, cy, z1)]
    elif ly >= ALARGADA * max(lx, 1e-6):
        puntos += [(cx, cy - ly / 4, z1), (cx, cy + ly / 4, z1)]
    return puntos


def _anclas(elegidas: list, cajas: dict) -> tuple:
    """Los candidatos a ancla (regla en el docstring), del más cercano al centro del grupo en
    planta al más lejano."""
    todas = list(cajas.values())
    cx = (min(c[0][0] for c in todas) + max(c[1][0] for c in todas)) / 2
    cy = (min(c[0][1] for c in todas) + max(c[1][1] for c in todas)) / 2
    puntos = [p for f in elegidas if f in cajas for p in _sobre(cajas[f])]
    if not puntos:
        puntos = [(cx, cy, max(c[1][2] for c in todas))]
    puntos.sort(key=lambda p: (p[0] - cx) ** 2 + (p[1] - cy) ** 2)
    if len(puntos) > MAX_ANCLAS:  # repartidas, no las más cercanas: las lejanas separan
        puntos = [puntos[i * len(puntos) // MAX_ANCLAS] for i in range(MAX_ANCLAS)]
    return tuple(puntos)


def _cifra_grupo(grupo: str, fids: list, doc, datos, masas: dict) -> CifraGrupo | None:
    cajas = {f: c for f in fids if (c := _caja(doc.scene[f].shape)) is not None}
    if not cajas:
        return None
    bases: dict[str, list] = {}
    for f in fids:
        feat = doc.scene[f]
        bases.setdefault(base(rol(feat.name, f, feat.command_id)), []).append(f)
    total = sum(masas[f] for f in fids)

    def potencia(fs) -> bool:
        return any(isinstance(datos.piezas[f].specs.get("potencia_kW"), (int, float))
                   for f in fs if f in datos.piezas)

    orden = sorted(bases.items(), key=lambda kv: (not potencia(kv[1]),
                                                  -sum(masas[f] for f in kv[1])))
    for b, fs in orden:
        if not potencia(fs) and total > 0 and sum(masas[f] for f in fs) < PESO_MINIMO * total:
            continue
        frase = plantilla(b, fs, datos)
        if frase is not None:
            return CifraGrupo(grupo, _texto(grupo, b, fs, frase), len(fids), round(total, 3),
                              _anclas(fs, cajas))
    n = len(fids)
    texto = f"{n} pieza{'' if n == 1 else 's'}" + (f" · {cifra(total, 1)} kg" if total > 0 else "")
    return CifraGrupo(grupo, texto, n, round(total, 3), _anclas(orden[0][1], cajas))


def cifras_grupos(doc, ids, *, datos=None) -> list[CifraGrupo]:
    """Una `CifraGrupo` por grupo raíz con piezas entre `ids`, en el orden de la escena
    (reglas en el docstring del módulo). `datos`: los de `datos_rotulos(doc)` si ya están."""
    from apolo.library.catalog import CATALOG
    from apolo.library.engineering.mass import feature_mass
    from apolo.library.peso_ficha import partes_de_cilindros
    from apolo.services.datos_rotulos import datos_rotulos

    por_grupo: dict[str, list] = {}
    for fid in ids:
        raiz = grupo_raiz(doc.scene[fid].group, doc.groups)
        if raiz is not None:
            por_grupo.setdefault(raiz, []).append(fid)
    if not por_grupo:
        return []
    datos = datos if datos is not None else datos_rotulos(doc)
    material = doc.default_material()
    por_instancia: dict[tuple, float] = {}  # las instancias de un `mesh_key` pesan lo mismo
    partes = partes_de_cilindros(doc.scene)  # el vástago de un cilindro no pesa dos veces (V8.9)

    def masa(fid, feat) -> float:
        if fid in partes:
            return float(feature_mass(feat, CATALOG, material, partes[fid])["masa_kg"])
        clave = (feat.mesh_key, feat.component, feat.cut_length, feat.material)
        if feat.mesh_key is None:
            return float(feature_mass(feat, CATALOG, material)["masa_kg"])
        if clave not in por_instancia:
            por_instancia[clave] = float(feature_mass(feat, CATALOG, material)["masa_kg"])
        return por_instancia[clave]

    masas = {f: masa(f, doc.scene[f]) for fids in por_grupo.values() for f in fids}
    out = [_cifra_grupo(g, fids, doc, datos, masas) for g, fids in por_grupo.items()]
    return [c for c in out if c is not None]
