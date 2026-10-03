"""Gate de las pistas: el texto que la persona lee en cada diálogo de comando (plan
texto-agente-vs-persona, D13).

Los gates de texto de la UI (`ui/src/textoDeAyuda.test.ts`, `ui/src/tuteoNeutro.test.ts`)
recorren los literales de `src/` y NO ven el texto que llega de la API. Las pistas viven en
`core/apolo/commands/pistas.py` y las sirve `GET /api/schemas?vista=persona`: este gate les
aplica los MISMOS criterios, LEÍDOS de esos dos archivos (si el estándar de Caronte cambia de
forma, el parseo falla fuerte en vez de quedarse con una copia vieja).

Cada pista: una frase que termina en punto, ≤ 120 caracteres, sin versión del roadmap, sin
backticks ni identificadores con `_` ni `param=valor`, sin MAYÚSCULAS enfáticas (las siglas
sí), sin el vocabulario «No se dice» de ui/CLAUDE.md y sin voseo ni usted. Por diálogo, la
pista del comando más las de sus campos no pasan de 40 palabras (D5).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from apolo.commands import REGISTRY, command_schemas, command_schemas_persona
from apolo.commands import vista_persona as vp
from apolo.commands.pistas import PESTANAS, PISTAS, PISTAS_CAMPO

UI_SRC = Path(__file__).resolve().parents[1] / "ui" / "src"
TOPE_CARACTERES = 120
TOPE_PALABRAS_DIALOGO = 40

# ── Lo que se lee de los gates de la UI ───────────────────────────────────────


def _fuente(nombre: str) -> str:
    return (UI_SRC / nombre).read_text(encoding="utf-8")


def _bloque(fuente: str, patron: str, que: str) -> str:
    m = re.search(patron, fuente, re.S)
    assert m, f"no encuentro {que}: cambió el estándar de Caronte; re-aplicar el parseo"
    return m.group(1)


def _strings(bloque: str) -> list[str]:
    return re.findall(r"'([^']*)'", bloque)


def _lista(fuente: str, nombre: str) -> list[str]:
    return _strings(_bloque(fuente, rf"const {nombre} = \[(.*?)\];", f"`const {nombre} = [...]`"))


def _detectores_de_tuteo() -> dict:
    """VOSEO y OTRO_REGISTRO tal como los arma `tuteoNeutro.test.ts`."""
    f = _fuente("tuteoNeutro.test.ts")
    imperativos = _lista(f, "IMPERATIVOS")
    otras = _lista(f, "OTRAS")
    cliticos = _lista(f, "CLITICOS")
    sin_tilde = dict(re.findall(r"([áéí]): '([aei])'", _bloque(
        f, r"const SIN_TILDE[^=]*= \{(.*?)\};", "`const SIN_TILDE`")))
    no_es = set(_strings(_bloque(f, r"const NO_ES_VOSEO = new Set\(\[(.*?)\]\)", "`NO_ES_VOSEO`")))
    dobles = re.search(r"\.\.\.\[([^\]]*)\]\.flatMap\(\(a\) => \[([^\]]*)\]", f)
    assert dobles, "no encuentro el doble pronombre de CON_PRONOMBRE: re-aplicar el parseo"
    primeros, segundos = _strings(dobles.group(1)), _strings(dobles.group(2))
    con_pronombre = [
        forma
        for v in imperativos
        for forma in [v[:-1] + sin_tilde[v[-1]] + c for c in cliticos]
        + [v + a + b for a in primeros for b in segundos]
        if forma not in no_es
    ]
    sueltas = _strings(_bloque(f, r"\.\.\.CON_PRONOMBRE, (.*?)\]", "las formas sueltas de VOSEO"))
    voseo = re.compile(
        r"(?<![a-záéíóúñ])(" + "|".join(imperativos + otras + con_pronombre + sueltas)
        + r")(?![a-záéíóúñ])",
        re.I,
    )
    otro = re.compile(_bloque(f, r"const OTRO_REGISTRO =\s*/(.*?)/i;", "`const OTRO_REGISTRO`"), re.I)
    return {"imperativos": imperativos, "voseo": voseo, "otro_registro": otro}


def _criterios_de_ayuda() -> dict:
    """FIN_DE_ORACION y la versión del roadmap de `textoDeAyuda.test.ts`."""
    f = _fuente("textoDeAyuda.test.ts")
    fin = _bloque(f, r"const FIN_DE_ORACION = /(.*?)/g;", "`const FIN_DE_ORACION`")
    version = _bloque(f, r"'versión del roadmap en pantalla', re: /(.*?)/g", "la regla de versión")
    return {"fin": fin, "version": version}


TUTEO = _detectores_de_tuteo()
AYUDA = _criterios_de_ayuda()
FIN_DE_ORACION = re.compile(AYUDA["fin"])
VERSION = re.compile(AYUDA["version"], re.ASCII)  # en JS `\b` y `\w` son ASCII

# ── Detectores de la casa (los que no tienen par en la UI) ────────────────────

#: «No se dice» de ui/CLAUDE.md § «Una cosa, un nombre», tal como lo lista D13.
NO_SE_DICE = re.compile(
    r"(?<![\wáéíóúñ])(s[óo]lidos?|features?|sketch(?:es)?|joints?|fasteners?|fijador(?:es)?|"
    r"snapshots?|sub-?ensamblajes?|borrar|borra|remover)(?![\wáéíóúñ])",
    re.I,
)
USTED = re.compile(r"(?<![\wáéíóúñ])usted(?:es)?(?![\wáéíóúñ])", re.I)
IDENTIFICADOR = re.compile(r"[A-Za-z0-9]_[A-Za-z0-9]")
PARAM_VALOR = re.compile(r"[A-Za-z_]\w*\s*=\s*\S")
#: Siglas del oficio que van en mayúsculas; cualquier otra palabra en mayúsculas es énfasis.
SIGLAS = {"STEP", "BOM", "ISO", "DIN", "DXF", "DWG", "SVG", "PDF", "CSV", "URDF", "SDF", "IA", "FEA"}
MAYUSCULAS = re.compile(r"(?<![\wÁÉÍÓÚÜÑáéíóúüñ])[A-ZÁÉÍÓÚÜÑ]{2,}(?![\wÁÉÍÓÚÜÑáéíóúüñ])")


def faltas(texto: str) -> list[str]:
    """Las reglas que rompe una pista (vacío = cumple)."""
    out = []
    limpio = " ".join(texto.split())
    if 1 + len(FIN_DE_ORACION.findall(limpio)) != 1:
        out.append("más de una frase")
    if len(texto) > TOPE_CARACTERES:
        out.append(f"{len(texto)} > {TOPE_CARACTERES} caracteres")
    if not texto.endswith("."):
        out.append("no termina en punto")
    if texto != texto.strip() or "  " in texto or "\n" in texto:
        out.append("espacios sobrantes")
    if VERSION.search(texto):
        out.append("versión del roadmap")
    if "`" in texto:
        out.append("backticks")
    if IDENTIFICADOR.search(texto):
        out.append("identificador con _")
    if PARAM_VALOR.search(texto):
        out.append("param=valor")
    enfasis = [w for w in MAYUSCULAS.findall(texto) if w not in SIGLAS]
    if enfasis:
        out.append(f"mayúsculas enfáticas {enfasis}")
    if m := NO_SE_DICE.search(texto):
        out.append(f"«{m.group(0)}» no se dice")
    if m := TUTEO["voseo"].search(texto):
        out.append(f"voseo «{m.group(0)}»")
    if m := TUTEO["otro_registro"].search(texto) or USTED.search(texto):
        out.append(f"usted/españolismo «{m.group(0)}»")
    return out


# ── El gate ───────────────────────────────────────────────────────────────────


def test_una_pista_por_comando_y_ninguna_huerfana():
    assert set(PISTAS) - set(REGISTRY) == set(), "pistas de comandos que ya no existen"
    assert set(REGISTRY) - set(PISTAS) == set(), "comandos sin pista (escríbela en pistas.py)"


def test_las_pistas_de_campo_apuntan_a_campos_que_existen():
    modelos: dict[str, set[str]] = {}
    for spec, entrada in zip(REGISTRY.values(), command_schemas()):
        schema = entrada["schema"]
        modelos.setdefault(spec.model.__name__, set()).update(schema.get("properties", {}))
        for nombre, sub in schema.get("$defs", {}).items():
            modelos.setdefault(nombre, set()).update(sub.get("properties", {}))
    for clave in PISTAS_CAMPO:
        modelo, _, campo = clave.partition(".")
        assert modelo in modelos, f"{clave}: no hay modelo {modelo}"
        assert campo in modelos[modelo], f"{clave}: {modelo} no tiene el campo {campo}"


def test_cada_pista_de_campo_llega_a_su_dialogo():
    servidas = {
        p["x-pista"]
        for e in command_schemas_persona()
        for p in _propiedades(e["schema"])
        if "x-pista" in p
    }
    assert set(PISTAS_CAMPO.values()) <= servidas


@pytest.mark.parametrize(
    "clave, texto",
    [pytest.param(k, t, id=k) for k, t in sorted(PISTAS.items()) + sorted(PISTAS_CAMPO.items())],
)
def test_la_pista_cumple_el_estandar(clave, texto):
    assert faltas(texto) == [], f"{clave}: «{texto}»"


def test_presupuesto_por_dialogo():
    for e in command_schemas_persona():
        textos = [e["pista"]] + [p["x-pista"] for p in _propiedades(e["schema"]) if "x-pista" in p]
        palabras = sum(len(t.split()) for t in textos)
        assert palabras <= TOPE_PALABRAS_DIALOGO, f"{e['type']}: {palabras} palabras de pista"


def test_la_vista_persona_sirve_las_pistas_escritas():
    for e in command_schemas_persona():
        assert e["pista"] == PISTAS[e["type"]], e["type"]


def test_las_pestanas_cubren_todas_las_categorias():
    categorias = {spec.category for spec in REGISTRY.values()}
    assert categorias - set(PESTANAS) == set(), "categoría sin pestaña: se pierde del ribbon"
    for clave, pestana in PESTANAS.items():
        if pestana is not None:
            assert set(pestana) == {"orden", "rotulo"}, clave
            assert faltas(pestana["rotulo"] + ".") == [], clave


def _propiedades(nodo):
    """Toda entrada de `properties` a cualquier profundidad del schema."""
    if isinstance(nodo, dict):
        for p in (nodo.get("properties") or {}).values():
            if isinstance(p, dict):
                yield p
        for v in nodo.values():
            yield from _propiedades(v)
    elif isinstance(nodo, list):
        for v in nodo:
            yield from _propiedades(v)


# ── El gate se prueba a sí mismo ──────────────────────────────────────────────


def test_las_listas_del_tuteo_se_leyeron():
    assert len(TUTEO["imperativos"]) >= 40, "se leyeron muy pocos imperativos: cambió el formato"
    assert TUTEO["voseo"].search("Revisá el pedido")
    assert TUTEO["voseo"].search("Revisala y ajustá antes de guardar")
    assert TUTEO["voseo"].search("esto depende de vos")
    assert not TUTEO["voseo"].search("Revisa el pedido y elige una opción")
    assert TUTEO["otro_registro"].search("Seleccione un cliente")
    assert not TUTEO["otro_registro"].search("Elige un cliente")


def test_las_copias_del_backend_son_las_de_la_ui():
    # vista_persona cuenta frases y quita versiones con su copia de los regex de la UI
    assert vp.FIN_DE_ORACION.pattern == AYUDA["fin"]
    assert vp._V == AYUDA["version"]


@pytest.mark.parametrize(
    "texto, regla",
    [
        ("Hace un agujero. Y otra cosa.", "más de una frase"),
        ("x" * 121 + ".", "caracteres"),
        ("Hace un agujero", "no termina en punto"),
        ("Entrada por cara (V6.8-E).", "versión"),
        ("Usa `cara` para entrar.", "backticks"),
        ("Usa en_cara para entrar.", "identificador"),
        ("Con depth=0 es pasante.", "param=valor"),
        ("Rota lo MÍNIMO posible.", "mayúsculas"),
        ("Redondea las aristas de un sólido.", "no se dice"),
        ("Elegí la cara de entrada.", "voseo"),
        ("Seleccione la cara de entrada.", "usted"),
        ("Si usted quiere, gira la pieza.", "usted"),
    ],
)
def test_el_gate_rebota(texto, regla):
    assert any(regla in f for f in faltas(texto)), faltas(texto)


def test_el_gate_deja_pasar_lo_que_cumple():
    assert faltas("Importa un archivo STEP como una sola pieza o separado en varias.") == []
    assert faltas("Hace girar un croquis 2D alrededor del eje Z para crear una pieza.") == []
