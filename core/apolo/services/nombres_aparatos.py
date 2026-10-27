"""El nombre por FUNCIÓN de cada aparato, para MOSTRAR (plan nombres-por-funcion D3, D9–D11, A2,
A8, A11, A15). La única fuente de nombres del visor: «Marcha · -S1», nunca «-S1 · Pulsador».

Lee un `Document` explícito (el llamador sostiene `STATE_LOCK`), sin transporte. Nada de aquí
APRUEBA un rótulo: lo derivado se muestra y marca su `origen`; lo exige la puerta (F2) con el
criterio de `library/calidad/nombres.py`, sólo sobre lo DECLARADO.

La cadena de `rotulo_de` (D3), con su `origen`:
  1. «declarado»: `add_device.rotulo`;
  2. «pieza»: el nombre de la pieza ligada que escribió alguien (no la que generó un layout),
     limpio (A15: sin el prefijo « · », sin «(…)» ni designaciones, cortado a 30 en palabra);
  3. «derivado»: un relé de seguridad, «Seguridad de» + lo que vigila (A11: la CADENA SERIE de
     S12/S22 hacia atrás por los contactos, hasta la alimentación);
  4. «tipo»: el nombre FUNCIONAL de lo que su tipo ya nombra (A8: «Parada de emergencia»,
     «Interruptor general», «Panel de operador») o el tipo + su distintivo de catálogo
     («Pulsador verde»); en último caso, el nombre del catálogo.
Nunca la designación sola ni un id de comando. El ST y las variables del PLC no se leen.

`estados_de` (D9): los declarados sobre los de su tipo (seccionador «Encendido/Apagado»,
resguardo «Cerrado/Abierto», selector y válvula la posición tal cual, botonera su actuador).
`grupo_de` (D11): energía, seguridad (seta, resguardo y todo lo cableado a un relé de seguridad),
operación; pilotos y lecturas.
"""

from __future__ import annotations

import re

from apolo.library.electrico.estados import claves

TOPE_ROTULO = 30
ORIGENES = ("declarado", "pieza", "derivado", "tipo")
MANDOS = ("pulsador", "seta", "selector", "seccionador", "resguardo")  # = cosim/vivo_fotograma.MANDOS
#: A8: el tipo que YA es la función se muestra con su nombre funcional
FUNCIONALES = {"seta": "Parada de emergencia", "seccionador": "Interruptor general",
               "hmi": "Panel de operador", "valvula_corte": "Válvula de corte"}
TIPOS = {
    "red": "Red de suministro", "fuente": "Fuente", "itm": "Interruptor automático",
    "guardamotor": "Guardamotor", "rele_termico": "Relé térmico", "fusible": "Fusible",
    "contactor": "Contactor", "rele": "Relé", "plc": "PLC", "variador": "Variador", "motor": "Motor",
    "pulsador": "Pulsador", "selector": "Selector", "piloto": "Piloto", "sensor": "Sensor",
    "resguardo": "Interruptor de resguardo", "rele_seguridad": "Relé de seguridad",
    "electrovalvula": "Electroválvula", "diferencial": "Interruptor diferencial", "presostato": "Presostato",
    "cilindro": "Cilindro", "valvula": "Válvula", "frl": "Unidad de mantenimiento",
    "regulador_caudal": "Regulador de caudal", "silenciador": "Silenciador", "bloqueo_vastago": "Bloqueo de vástago",
}
CON_COLOR = ("pulsador", "piloto", "selector")
_COLOR = {"ambar": "ámbar"}  # `specs.color` de la ficha va sin tilde: así se lee
ESTADOS_TIPO = {"seccionador": {"cerrado": "Encendido", "abierto": "Apagado"},
                "resguardo": {"cerrado": "Cerrado", "abierto": "Abierto"}}
CANALES, REARME = ("S12", "S22"), "S34"  # cosim/modelos/seguridad.ReleSeguridad.BORNES_ENTRADA
_CONECTORES = {"de", "del", "la", "el", "los", "las", "y", "con", "para", "a", "por", "en", "sin"}
_DESIGNACION = re.compile(r"^[=+]?[\w.]*[-=+][A-Za-z]{1,3}\d+[A-Za-z]?(:\S*)?[,.;]?$")
_ID = re.compile(r"(?<![\w])c\d+(_\w*)?(?![\w])|_")
_MAX_SALTOS = 24


# ── texto ────────────────────────────────────────────────────────────────────────────────────


def humanizar(nombre: str) -> str:
    """«descargar_sin_recipiente» → «Descargar sin recipiente»; «c388_puerta» → «Puerta» (D14:
    el título de un escenario o de una junta sin pieza, nunca con el id de un comando)."""
    t = re.sub(r"^c\d+_", "", str(nombre or "").strip())
    t = " ".join(t.replace("_", " ").split())
    return t[:1].upper() + t[1:] if t else ""


def _cortar(texto: str, tope: int = TOPE_ROTULO) -> str:
    palabras = texto.split()
    out: list[str] = []
    for p in palabras:
        if len(" ".join(out + [p])) > tope:
            break
        out.append(p)
    while out and out[-1].lower() in _CONECTORES:
        out.pop()
    return " ".join(out)


def limpiar_nombre_pieza(nombre: str, designacion: str = "") -> str:
    """El nombre de una pieza como rótulo (A15): el último tramo « · », sin «(…)» ni designaciones
    («-B1», «=Faja1-B1», «+TAB1»), y DESPUÉS cortado a 30 en palabra. Vacío si no queda nada o si
    lo que queda es un identificador. Es texto: nunca aprueba."""
    t = str(nombre or "").rsplit(" · ", 1)[-1]
    t = re.sub(r"\([^()]*\)", " ", t)
    t = re.sub(r"\([^()]*$", " ", t)  # un paréntesis sin cerrar
    if designacion:
        t = t.replace(designacion, " ")
    palabras = [p for p in t.split() if not _DESIGNACION.match(p) and not p.startswith("+")]
    t = " ".join(palabras).strip(" ,;:-·")
    t = _cortar(t)
    if not re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]{3}", t) or _ID.search(t):
        return ""
    return t


def _minuscula(rotulo: str) -> str:
    """Para encadenar rótulos en una frase: «Tapa del tanque» → «tapa del tanque» (una sigla queda)."""
    return rotulo if len(rotulo) > 1 and rotulo[1].isupper() else rotulo[:1].lower() + rotulo[1:]


def _lista(cosas: list[str]) -> str:
    return cosas[0] if len(cosas) == 1 else ", ".join(cosas[:-1]) + " y " + cosas[-1]


# ── el aparato ───────────────────────────────────────────────────────────────────────────────


def tipo_de(d) -> str | None:
    """El tipo del aparato: el de su modelo eléctrico o, sólo de aire, el de su ficha neumática."""
    t = (d.modelo or {}).get("tipo")
    if t:
        return t
    neu = getattr(d, "neumatico", None)
    return getattr(neu, "tipo", None) if neu is not None else None


def _comp(ref: str):
    from apolo.library.catalog import CATALOG

    return CATALOG.get(ref)


def _por_tipo(d) -> str:
    """El paso 4 de D3: el nombre funcional (A8), el tipo con su color, o el nombre del catálogo."""
    t = tipo_de(d)
    if t in FUNCIONALES:
        return FUNCIONALES[t]
    comp = _comp(d.ref)
    if t in TIPOS:
        color = ((getattr(comp, "specs", None) or {}).get("color") if comp is not None else None)
        color = _COLOR.get(str(color), color) if color else None
        return f"{TIPOS[t]} {color}" if color and t in CON_COLOR else TIPOS[t]
    if getattr(d, "bornera", False):
        return "Bornera"
    if comp is not None and comp.electrico is not None and comp.electrico.simbolo == "gabinete":
        return "Gabinete"
    return (getattr(comp, "name", "") or "Aparato") if comp is not None else "Aparato"


class Nombres:
    """Los nombres de un documento, calculados UNA vez (el análisis de redes es de todo el
    tablero): `rotulo_de`, `estados_de`, `grupo_de`, `vigila`, `rearma_a`, `ramas` y `fila`."""

    def __init__(self, doc, m=None):
        from .electrico import modelo
        from .tablero import piezas_del_layout

        self.doc = doc
        self.m = m if m is not None else modelo(doc)
        self.disp = {d.designacion: d for d in self.m.dispositivos}
        escena = getattr(doc, "scene", {}) or {}
        self.escena = escena
        try:
            self.del_layout = piezas_del_layout(doc) if escena else set()
        except Exception:  # noqa: BLE001 — un layout roto no deja sin nombres al resto
            self.del_layout = set()
        self._analisis = None
        self._cadenas: dict = {}
        self._seguridad: set[str] | None = None

    # ── la cadena serie (A11) ────────────────────────────────────────────────────────────────

    @property
    def analisis(self):
        if self._analisis is None:
            from apolo.library.electrico.redes import analizar

            self._analisis = analizar(self.m)
        return self._analisis

    def _cadena(self, des: str, borne: str) -> list[str]:
        """Los aparatos en serie con el borne `borne` de `des`, desde la ALIMENTACIÓN hacia él:
        se camina de red en red por los contactos NA/NC hasta una red con potencial directo (la
        alimentación) o hasta que no hay más contactos. Sólo los operables (mandos y sensores)."""
        if (des, borne) in self._cadenas:
            return self._cadenas[(des, borne)]
        a = self.analisis
        inicio = a.red(des, borne)
        orden: list[str] = []
        if inicio is not None:
            vistos, frontera, saltos = {inicio}, [inicio], 0
            while frontera and saltos < _MAX_SALTOS:
                saltos += 1
                siguiente = []
                for r in frontera:
                    if r != inicio and a.directos(r):
                        continue  # la alimentación: ahí termina la serie
                    for otro_des, b in a.miembros[r]:
                        if otro_des == des:
                            continue
                        for c in a.dispositivos[otro_des].caminos:
                            if c.tipo not in ("NA", "NC") or b not in (c.de, c.a):
                                continue
                            if otro_des not in orden:
                                orden.append(otro_des)
                            r2 = a.red(otro_des, c.a if b == c.de else c.de)
                            if r2 is not None and r2 not in vistos:
                                vistos.add(r2)
                                siguiente.append(r2)
                frontera = siguiente
        out = [x for x in reversed(orden) if tipo_de(self.disp[x]) in MANDOS + ("sensor", "presostato")]
        self._cadenas[(des, borne)] = out
        return out

    def vigila(self, des: str) -> list[str]:
        """Lo que vigila un relé de seguridad: lo que está en serie con sus canales (S12, S22)."""
        out: list[str] = []
        for b in CANALES:
            out += [x for x in self._cadena(des, b) if x not in out]
        return out

    def rearma_a(self, des: str) -> list[str]:
        """Los relés de seguridad que rearma un mando: los que lo tienen en la serie de su S34."""
        return [k for k, d in self.disp.items()
                if tipo_de(d) == "rele_seguridad" and des in self._cadena(k, REARME)]

    def _de_seguridad(self) -> set[str]:
        if self._seguridad is None:
            s: set[str] = set()
            for k, d in self.disp.items():
                if tipo_de(d) == "rele_seguridad":
                    s.update(self.vigila(k))
                    s.update(self._cadena(k, REARME))
            self._seguridad = s
        return self._seguridad

    # ── nombres ──────────────────────────────────────────────────────────────────────────────

    def de_pieza(self, d) -> str:
        """El nombre de la pieza ligada (D3.2), si la escribió alguien; vacío si no."""
        if not d.pieza or d.pieza in self.del_layout or d.pieza not in self.escena:
            return ""
        return limpiar_nombre_pieza(getattr(self.escena[d.pieza], "name", "") or "", d.designacion)

    def rotulo_de(self, des: str, *, derivar: bool = True) -> tuple[str, str]:
        """(rótulo, origen) del aparato `des` (la cadena D3)."""
        d = self.disp.get(des)
        if d is None:
            return "", ""
        if getattr(d, "rotulo", ""):
            return d.rotulo, "declarado"
        pieza = self.de_pieza(d)
        if pieza:
            return pieza, "pieza"
        if derivar and tipo_de(d) == "rele_seguridad":
            vig = [_minuscula(self.rotulo_de(x, derivar=False)[0]) for x in self.vigila(des)]
            if vig:
                return f"Seguridad de {_lista(vig)}", "derivado"
        return _por_tipo(d), "tipo"

    def estados_de(self, des: str) -> dict[str, str]:
        """Los estados con nombre, en el orden de su ficha: los declarados sobre los de su tipo."""
        d = self.disp.get(des)
        if d is None:
            return {}
        t = tipo_de(d)
        neu = getattr(getattr(d, "neumatico", None), "modelo", None)
        ks = claves(d.modelo, neu)
        base = ESTADOS_TIPO.get(t, {})
        declarados = getattr(d, "estados", None) or {}
        return {k: declarados.get(k) or base.get(k) or (k.capitalize() if t == "pulsador" else k) for k in ks}

    def grupo_de(self, des: str) -> str:
        """D11: «energia», «seguridad», «operacion» (los mandos y la válvula manual), «pilotos» o
        «lecturas»."""
        d = self.disp.get(des)
        t = tipo_de(d) if d is not None else None
        if t == "seccionador":
            return "energia"
        if t in ("seta", "resguardo") or des in self._de_seguridad():
            return "seguridad"
        neu = getattr(getattr(d, "neumatico", None), "modelo", None) or {}
        if t in MANDOS or (t == "electrovalvula" and neu.get("manual")):
            return "operacion"
        return "pilotos" if t == "piloto" else "lecturas"

    def con_designacion(self, des: str) -> str:
        """«Interruptor general (-Q1)»: para una frase que nombra al aparato."""
        r, _ = self.rotulo_de(des)
        return f"{r} ({des})" if r else des

    def fila(self, des: str) -> dict:
        """Lo que la tabla del vivo y los paneles suman a la fila del aparato (claves AGREGADAS)."""
        d = self.disp.get(des)
        if d is None:
            return {}
        r, origen = self.rotulo_de(des)
        out: dict = {"rotulo": r, "origen": origen, "grupo": self.grupo_de(des)}
        est = self.estados_de(des)
        if est:
            out["estados"] = est
        if getattr(d, "descripcion", ""):
            out["descripcion"] = d.descripcion
        rearma = self.rearma_a(des)
        if rearma:
            out["rearma"] = rearma
        return out

    # ── cables y contactos ───────────────────────────────────────────────────────────────────

    def ramas(self) -> dict[str, str]:
        """{base del id de rama de un conductor: nombre por sus extremos} (`services/cosim_red`:
        «-W1.1» para el hilo de un cable, el id del comando si no). Nunca el id."""
        out: dict[str, str] = {}
        for c in self.m.conductores:
            base = f"{c.cable}.{c.hilo}" if c.cable else c.id
            if not base or len(c.puntos) < 2:
                continue
            a, b = (p.rsplit(":", 1)[0] for p in (c.puntos[0], c.puntos[-1]))
            ra = self.rotulo_de(a)[0] or a
            rb = self.rotulo_de(b)[0] or b
            out[base] = f"Cable {ra} → {rb}" if a != b else f"Puente en {ra}"
        return out


def nombre_junta(doc, nombre: str) -> str:
    """D15: una junta por su pieza HIJA («Tapa de carga»), sin prefijo; si no, su nombre humanizado."""
    j = (getattr(doc, "joints", {}) or {}).get(nombre) or {}
    hija = (getattr(doc, "scene", {}) or {}).get(j.get("child"))
    limpio = limpiar_nombre_pieza(getattr(hija, "name", "") or "") if hija is not None else ""
    return limpio or humanizar(nombre)


# ── la puerta y la entrega (F2) ──────────────────────────────────────────────────────────────


def insumo_puerta(doc) -> dict | None:
    """El insumo `nombres` de `library/calidad/nombres.py` (el ítem `interfaz.nombres_por_funcion`
    y la regla de `delivery_check`): una fila por aparato con lo DECLARADO (`rotulo`, `estados`),
    las claves de sus estados, sus piezas para encuadrar y la `sugerencia` (el nombre limpio de la
    pieza ligada: texto, nunca aprueba). None sin carril; `{"error"}` si no se pudo leer."""
    from .electrico import tiene_carril
    from .tablero import piezas_3d

    if not tiene_carril(doc):
        return None
    try:
        n = Nombres(doc)
        piezas = piezas_3d(doc, n.m)
        filas = []
        for des, d in n.disp.items():
            neu = getattr(getattr(d, "neumatico", None), "modelo", None) or {}
            comp = _comp(d.ref)
            fila = {"designacion": des, "tipo": tipo_de(d), "manual": bool(neu.get("manual")),
                    "ref": d.ref, "nombre_ficha": getattr(comp, "name", "") or "",
                    "rotulo": getattr(d, "rotulo", "") or "",
                    "estados": dict(getattr(d, "estados", None) or {}),
                    "claves": list(claves(d.modelo, neu or None)),
                    "piezas": [piezas[des]] if piezas.get(des) else []}
            sugerencia = n.de_pieza(d)
            if sugerencia:
                fila["sugerencia"] = sugerencia
            filas.append(fila)
        return {"aparatos": filas}
    except Exception as exc:  # noqa: BLE001 — no se pudo leer: SIN_EVALUAR, con el porqué
        return {"error": f"{type(exc).__name__}: {exc}"}


# ── la tabla del vivo ────────────────────────────────────────────────────────────────────────


def para_tabla(doc) -> dict:
    """Lo que `nombres_en_tabla` suma al `inicio` del vivo, armado bajo el lock del llamador."""
    n = Nombres(doc)
    neu = {des: claves(d.modelo, getattr(getattr(d, "neumatico", None), "modelo", None))
           for des, d in n.disp.items() if tipo_de(d) == "electrovalvula"}
    return {"aparatos": {des: n.fila(des) for des in n.disp},
            "posiciones": {des: list(ks) for des, ks in neu.items()},
            "ramas": n.ramas(),
            "contactos": {des: n.rotulo_de(des)[0] for des in n.disp},
            "juntas": {j: nombre_junta(doc, j) for j in (getattr(doc, "joints", {}) or {})}}


def nombres_en_tabla(tabla: dict, nombres: dict) -> dict:
    """La tabla del vivo con el nombre por función de cada fila (claves AGREGADAS: el contrato del
    `inicio` no sube su `version`). Pura; sin nombres, la tabla tal cual."""
    if not nombres:
        return tabla
    aparatos = nombres.get("aparatos") or {}
    out = dict(tabla)
    for lista in ("mandos", "pilotos", "dispositivos", "valvulas", "fallas"):
        filas = tabla.get(lista)
        if not filas:
            continue
        nuevas = []
        for f in filas:
            extra = dict(aparatos.get(f.get("designacion")) or {})
            if lista == "valvulas" and f.get("designacion") in (nombres.get("posiciones") or {}):
                extra["posiciones"] = nombres["posiciones"][f["designacion"]]
            if lista == "fallas":
                extra = {k: v for k, v in extra.items() if k in ("rotulo", "origen")}
            nuevas.append({**f, **{k: v for k, v in extra.items() if k not in f}})
        out[lista] = nuevas
    if tabla.get("ramas"):
        cond, rot = nombres.get("ramas") or {}, nombres.get("contactos") or {}
        filas = []
        for r in tabla["ramas"]:
            rid = str(r.get("id") or "")
            if r.get("tipo") == "contacto":
                des = r.get("dispositivo") or rid.partition(":")[0]
                nombre = f"Contacto {rid.partition(':')[2].split('#')[0]} · {rot.get(des) or des}"
            else:
                nombre = cond.get(rid.split("#")[0]) or "Cable"
            filas.append({**r, "nombre": nombre})
        out["ramas"] = filas
    if tabla.get("juntas"):
        juntas = nombres.get("juntas") or {}
        out["juntas"] = [{**j, "nombre": juntas.get(j.get("name")) or humanizar(j.get("name"))}
                         for j in tabla["juntas"]]
    return out
