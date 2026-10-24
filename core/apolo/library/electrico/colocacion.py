"""Colocación de los aparatos de un tablero (plan V8.5 D2, D8; ajustes A1, A7, A13): reglas
deterministas, sin optimizador. PURA: no importa OCCT, el catálogo ni el `Document` (lo que sale
del catálogo lo arma `colocacion_catalogo.py`); la geometría la hace el layout (F1b).

**Marco**: el de la placa útil vista de frente. `u` hacia la derecha y `v` hacia arriba desde su
esquina inferior izquierda; `w` = profundidad desde el FRENTE de la placa hacia la puerta (la
cara interior de la puerta está en `w = fondo_util`). Un mando de puerta se proyecta en el
mismo (u, v): así se ve qué cae sobre qué con la puerta cerrada.

**Reglas** (`Reglas`, todas «criterio de diseño» y listadas en `Layout.supuestos`):
1. Canaletas verticales a los dos lados y una horizontal arriba, a todo el ancho.
2. A1 — la COLUMNA de placa: lo que va en placa (`montaje: placa`, el variador) se apila a la
   izquierda desde arriba, con una canaleta debajo de cada uno y otra vertical a su derecha; las
   filas de riel van a la derecha de esa canaleta.
3. Filas de riel de arriba abajo: alimentación (seccionador, ITM, fusible) → potencia
   (guardamotor, contactor, relé térmico, variador en riel) → control (PLC, fuente, relés, el
   resto) → borneras; dentro de cada fila, por designación. Una canaleta horizontal bajo cada
   fila. A13 — cada fila deja libre ≥ `reserva` de su riel: lo que no entra sigue en otra fila de
   la misma clase («control 2»).
4. A4 — un accesorio (`acopla_a`) va pegado a su aparato: por el frente suma fondo, abajo o
   arriba suma alto a la fila, a un lado suma ancho; no ocupa riel propio. Su aparato es el que
   nombra el override `acopla`, o el de la designación que es prefijo de la suya (-Q3A → -Q3),
   o el único de ese símbolo; si hay varios, error que pide el override.
5. A7 — los mandos de puerta en una cuadrícula desde arriba y desde el lado OPUESTO a la
   bisagra, en el orden Q (seccionador), S (mandos), P (señalización) y el resto; una celda donde
   lo de detrás del mando no deja `holgura_puerta_mm` sobre lo de la placa se salta.
6. Lo que sale de la placa no pasa `fondo_util − holgura_puerta_mm`.
7. D8 — overrides por designación, estrictos: `fila` (n.º de fila de riel desde arriba o la
   clase), `orden` (lugar en su fila, en la columna o en la puerta), `posicion` {u, v} (esquina
   inferior izquierda, fuera del flujo, sin solaparse con nada) y `acopla` (su aparato).

`colocar(aparatos, gabinete, gabinetes)`: con una ref, el `Layout` o `ColocacionError` con lo
que sobra y cuánto falta; con `"auto"`, el primer gabinete (de menor placa útil) donde entra.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .colocacion_modelo import (  # noqa: F401 — los tipos se re-exportan desde aquí
    CLASES,
    CLAVES_OVERRIDE,
    MONTAJES,
    Acople,
    Aparato,
    Canaleta,
    ColocacionError,
    Colocado,
    FilaRiel,
    Gabinete,
    Layout,
    Reglas,
    Riel,
    _NoEntra,
    clase_de,
    orden_natural,
    ordenar,
)
from .colocacion_puerta import colocar_puerta
from .referencias import sufijo_sugerencia

# ── overrides (D8) y acoples (A4): no dependen del gabinete ──────────────────────────────


def _validar_overrides(overrides: dict, aparatos: list[Aparato]) -> dict:
    nombres = [a.designacion for a in aparatos]
    if not isinstance(overrides, dict):
        raise ColocacionError(f"los overrides van por designación: {{«-Q1»: {{…}}}}, llegó {overrides!r}")
    for des, ov in overrides.items():
        if des not in nombres:
            raise ColocacionError(f"override «{des}»: no hay ese aparato en el tablero; aparatos: "
                                  f"{', '.join(sorted(nombres, key=orden_natural))}."
                                  f"{sufijo_sugerencia(des, nombres)}")
        if not isinstance(ov, dict) or not ov:
            raise ColocacionError(f"override «{des}»: se espera un mapa con {', '.join(CLAVES_OVERRIDE)}")
        for k in ov:
            if k not in CLAVES_OVERRIDE:
                raise ColocacionError(f"override «{des}»: clave desconocida «{k}»; válidas: "
                                      f"{', '.join(CLAVES_OVERRIDE)}.{sufijo_sugerencia(k, CLAVES_OVERRIDE)}")
        a = next(x for x in aparatos if x.designacion == des)
        if "fila" in ov:
            f = ov["fila"]
            ok = (isinstance(f, int) and not isinstance(f, bool) and f >= 1) or f in CLASES
            if not ok:
                raise ColocacionError(f"override «{des}».fila: un n.º de fila ≥ 1 o una clase "
                                      f"({', '.join(CLASES)}), llegó {f!r}")
            if a.montaje != "din" or a.acopla is not None:
                raise ColocacionError(f"override «{des}».fila: sólo un aparato de riel cambia de fila "
                                      f"(«{des}» es de {a.montaje if a.acopla is None else 'acople'})")
        if "orden" in ov and (isinstance(ov["orden"], bool) or not isinstance(ov["orden"], int)
                              or ov["orden"] < 1):
            raise ColocacionError(f"override «{des}».orden: se espera un entero ≥ 1, llegó {ov['orden']!r}")
        if "posicion" in ov:
            p = ov["posicion"]
            if not (isinstance(p, dict) and set(p) == {"u", "v"}
                    and all(isinstance(p[k], (int, float)) and not isinstance(p[k], bool) for k in p)):
                raise ColocacionError(f"override «{des}».posicion: se espera {{u, v}} en mm (esquina "
                                      f"inferior izquierda en la placa), llegó {p!r}")
            if "fila" in ov or a.acopla is not None:
                raise ColocacionError(f"override «{des}».posicion: va sola (fuera del flujo, sin "
                                      "`fila`) y no en un accesorio: éste sigue a su aparato")
        if "acopla" in ov and a.acopla is None:
            raise ColocacionError(f"override «{des}».acopla: «{des}» ({a.ref}) no es un accesorio "
                                  "que vaya pegado a otro aparato")
    return overrides


def resolver_acoples(aparatos: list[Aparato], overrides: dict) -> dict[str, str]:
    """{accesorio: su aparato} (regla 4). Error accionable si no hay o si es ambiguo."""
    out: dict[str, str] = {}
    for a in aparatos:
        if a.acopla is None:
            continue
        hosts = [h for h in aparatos if h.simbolo in a.acopla.simbolos and h.acopla is None]
        nombres = [h.designacion for h in hosts]
        pedido = (overrides.get(a.designacion) or {}).get("acopla")
        if pedido is not None:
            if pedido not in nombres:
                raise ColocacionError(f"override «{a.designacion}».acopla: «{pedido}» no es un aparato "
                                      f"de {', '.join(a.acopla.simbolos)} del tablero; candidatos: "
                                      f"{', '.join(nombres) or '(ninguno)'}.{sufijo_sugerencia(pedido, nombres)}")
            out[a.designacion] = pedido
            continue
        prefijo = [n for n in nombres if a.designacion.startswith(n)]
        if prefijo:
            out[a.designacion] = max(prefijo, key=len)
        elif len(hosts) == 1:
            out[a.designacion] = nombres[0]
        elif not hosts:
            raise ColocacionError(f"{a.designacion} ({a.ref}) va pegado a un aparato de "
                                  f"{', '.join(a.acopla.simbolos)} y el tablero no tiene ninguno")
        else:
            raise ColocacionError(f"{a.designacion} ({a.ref}): no sé a cuál va pegado ("
                                  f"{', '.join(nombres)}); pásalo en overrides: "
                                  f'{{"{a.designacion}": {{"acopla": "{nombres[0]}"}}}}')
    return out


# ── la placa ──────────────────────────────────────────────────────────────────────────────


@dataclass
class _Pila:
    """Un aparato de riel con sus accesorios: lo que ocupa en la fila."""
    host: Aparato
    frente: list[Aparato]
    abajo: list[Aparato]
    arriba: list[Aparato]
    izquierda: list[Aparato]
    derecha: list[Aparato]

    @property
    def ancho(self) -> float:
        centro = max([self.host.ancho] + [x.ancho for x in self.abajo + self.arriba + self.frente])
        return centro + sum(x.ancho for x in self.izquierda + self.derecha)

    @property
    def sube(self) -> float:
        return max([self.host.alto / 2] + [x.alto / 2 for x in self.izquierda + self.derecha]) \
            + sum(x.alto for x in self.arriba)

    @property
    def baja(self) -> float:
        return max([self.host.alto / 2] + [x.alto / 2 for x in self.izquierda + self.derecha]) \
            + sum(x.alto for x in self.abajo)


def _pilas(riel: list[Aparato], accesorios: list[Aparato], acoples: dict[str, str]) -> dict[str, _Pila]:
    pilas = {a.designacion: _Pila(a, [], [], [], [], []) for a in riel}
    for acc in sorted(accesorios, key=lambda x: (x.acopla.orden, orden_natural(x.designacion))):
        host = acoples[acc.designacion]
        if host not in pilas:
            raise ColocacionError(f"{acc.designacion} va pegado a {host}, que no es un aparato de "
                                  "riel: un accesorio sólo se acopla a un aparato del riel")
        getattr(pilas[host], acc.acopla.cara).append(acc)
    return pilas


def _colocar_pila(p: _Pila, u: float, v_riel: float, fila: str, w_base: float) -> list[Colocado]:
    """La pila con su riel en `v_riel` y su borde izquierdo en `u`."""
    out: list[Colocado] = []
    u_h = u + sum(x.ancho for x in p.izquierda)
    centro = max([p.host.ancho] + [x.ancho for x in p.abajo + p.arriba + p.frente])
    uc = u_h + (centro - p.host.ancho) / 2
    h = p.host
    out.append(Colocado(h.designacion, h.ref, "placa", uc, v_riel - h.alto / 2, h.ancho, h.alto,
                        w_base, w_base + h.fondo, fila, None, h.pieza))
    w = w_base + h.fondo
    for x in p.frente:
        out.append(Colocado(x.designacion, x.ref, "placa", uc + (h.ancho - x.ancho) / 2,
                            v_riel - x.alto / 2, x.ancho, x.alto, w, w + x.fondo, fila,
                            h.designacion, x.pieza))
        w += x.fondo
    v = v_riel - h.alto / 2
    for x in p.abajo:
        v -= x.alto
        out.append(Colocado(x.designacion, x.ref, "placa", uc + (h.ancho - x.ancho) / 2, v,
                            x.ancho, x.alto, w_base, w_base + x.fondo, fila, h.designacion, x.pieza))
    v = v_riel + h.alto / 2
    for x in p.arriba:
        out.append(Colocado(x.designacion, x.ref, "placa", uc + (h.ancho - x.ancho) / 2, v,
                            x.ancho, x.alto, w_base, w_base + x.fondo, fila, h.designacion, x.pieza))
        v += x.alto
    ui = u_h
    for x in p.izquierda:
        ui -= x.ancho
        out.append(Colocado(x.designacion, x.ref, "placa", ui, v_riel - x.alto / 2, x.ancho,
                            x.alto, w_base, w_base + x.fondo, fila, h.designacion, x.pieza))
    ud = u_h + centro
    for x in p.derecha:
        out.append(Colocado(x.designacion, x.ref, "placa", ud, v_riel - x.alto / 2, x.ancho,
                            x.alto, w_base, w_base + x.fondo, fila, h.designacion, x.pieza))
        ud += x.ancho
    return out


def _filas(pilas: dict[str, _Pila], overrides: dict, capacidad: float) -> list[tuple[str, list[_Pila]]]:
    """Filas de riel (regla 3): por clase, partidas por capacidad; luego los `fila` pedidos."""
    forzadas = {d: overrides[d]["fila"] for d in pilas if "fila" in (overrides.get(d) or {})}
    filas: list[tuple[str, list[_Pila]]] = []
    for clase in CLASES:
        miembros = ordenar([p.host for p in pilas.values() if p.host.clase == clase
                             and p.host.designacion not in forzadas], overrides)
        actual: list[_Pila] = []
        n = 1
        for a in miembros:
            p = pilas[a.designacion]
            if actual and sum(x.ancho for x in actual) + p.ancho > capacidad:
                filas.append((clase if n == 1 else f"{clase} {n}", actual))
                actual, n = [], n + 1
            actual.append(p)
        if actual:
            filas.append((clase if n == 1 else f"{clase} {n}", actual))
    for des, f in sorted(forzadas.items(), key=lambda kv: orden_natural(kv[0])):
        if isinstance(f, str):
            idx = next((i for i, (nombre, _) in enumerate(filas) if nombre.split()[0] == f), None)
            if idx is None:
                filas.append((f, []))
                idx = len(filas) - 1
        else:
            if f > len(filas):
                raise ColocacionError(f"override «{des}».fila {f}: el tablero tiene {len(filas)} "
                                      f"fila(s) de riel ({', '.join(n for n, _ in filas)})")
            idx = f - 1
        nombre, miembros = filas[idx]
        orden = (overrides[des] or {}).get("orden")
        pos = min(orden - 1, len(miembros)) if orden else len(miembros)
        miembros.insert(pos, pilas[des])
    return filas


def _colocar_placa(aps: list[Aparato], gab: Gabinete, r: Reglas, overrides: dict,
                   acoples: dict[str, str]) -> tuple[list, list, list, list, list[str]]:
    b, PW, PH = r.canaleta_ancho_mm, gab.placa_ancho, gab.placa_alto
    problemas: list[str] = []
    colocados: list[Colocado] = []
    rieles: list[Riel] = []
    canaletas = [Canaleta("v", 0, b, 0, PH), Canaleta("v", PW - b, PW, 0, PH),
                 Canaleta("h", 0, PW, PH - b, PH)]
    fijos = [a for a in aps if "posicion" in (overrides.get(a.designacion) or {})]
    columna = ordenar([a for a in aps if a.montaje == "placa" and a not in fijos], overrides)
    accesorios = [a for a in aps if a.acopla is not None]
    riel = [a for a in aps if a.montaje == "din" and a.acopla is None and a not in fijos]
    u_r0 = b
    if columna:  # A1
        wcol = max(a.ancho for a in columna)
        v = PH - b
        for a in columna:
            v0 = v - a.alto
            colocados.append(Colocado(a.designacion, a.ref, "placa", b + (wcol - a.ancho) / 2, v0,
                                      a.ancho, a.alto, 0.0, a.fondo, "columna", None, a.pieza))
            canaletas.append(Canaleta("h", 0, 2 * b + wcol, v0 - b, v0))
            v = v0 - b
        if v < 0:
            problemas.append(f"la columna de placa ({', '.join(a.designacion for a in columna)}) "
                             f"no entra en alto: faltan {-v:.0f} mm de placa")
        canaletas.append(Canaleta("v", b + wcol, 2 * b + wcol, 0, PH - b))
        u_r0 = 2 * b + wcol
    largo = (PW - b) - u_r0
    capacidad = largo * (1.0 - r.reserva)
    filas_info: list[FilaRiel] = []
    pilas = _pilas(riel, accesorios, acoples)
    anchas = [p for p in pilas.values() if p.ancho > capacidad]
    for p in anchas:
        problemas.append(f"{p.host.designacion} ({p.ancho:.0f} mm con sus accesorios) no entra en "
                         f"un riel de {largo:.0f} mm con la reserva de {r.reserva:.0%} "
                         f"(caben {capacidad:.0f} mm)")
    v_top = PH - b
    if not anchas:
        for nombre, miembros in _filas(pilas, overrides, capacidad):
            if not miembros:
                continue
            sube = max(p.sube for p in miembros)
            baja = max(p.baja for p in miembros)
            v_riel = v_top - sube
            u = u_r0
            for p in miembros:
                colocados += _colocar_pila(p, u, v_riel, nombre, r.riel_alto_mm)
                u += p.ancho
            ocupado = u - u_r0
            rieles.append(Riel(nombre, u_r0, PW - b, v_riel))
            filas_info.append(FilaRiel(nombre, largo, ocupado))
            if ocupado > capacidad + 1e-6:
                problemas.append(f"fila {nombre}: {ocupado:.0f} de {largo:.0f} mm de riel, reserva "
                                 f"{1 - ocupado / largo:.0%} < {r.reserva:.0%}: sobran "
                                 f"{ocupado - capacidad:.0f} mm de aparatos")
            v_bajo = v_riel - baja
            canaletas.append(Canaleta("h", u_r0 - b if columna else 0, PW, v_bajo - b, v_bajo))
            v_top = v_bajo - b
        if v_top < -1e-6:
            problemas.append(f"las filas de riel no entran en alto: faltan {-v_top:.0f} mm de "
                             f"placa ({PH:.0f} de alto útil)")
    for a in fijos:  # D8: fuera del flujo, sin solaparse con nada
        p = overrides[a.designacion]["posicion"]
        w0 = r.riel_alto_mm if a.montaje == "din" else 0.0
        c = Colocado(a.designacion, a.ref, "placa", float(p["u"]), float(p["v"]), a.ancho, a.alto,
                     w0, w0 + a.fondo, "fija", None, a.pieza)
        if c.u0 < 0 or c.v0 < 0 or c.u0 + c.ancho > PW or c.v0 + c.alto > PH:
            problemas.append(f"{a.designacion} en {{u: {c.u0:g}, v: {c.v0:g}}} sale de la placa útil "
                             f"({PW:g}×{PH:g})")
        choca = [x.designacion for x in colocados if x.solapa(c.u0, c.v0, c.u0 + c.ancho, c.v0 + c.alto)]
        choca += [f"canaleta {k.orientacion}" for k in canaletas
                  if c.u0 < k.u1 and k.u0 < c.u0 + c.ancho and c.v0 < k.v1 and k.v0 < c.v0 + c.alto]
        if choca:
            problemas.append(f"{a.designacion} en {{u: {c.u0:g}, v: {c.v0:g}}} se solapa con "
                             f"{', '.join(choca)}")
        if a.montaje == "din":
            rieles.append(Riel("fija", c.u0, c.u0 + c.ancho, c.v0 + c.alto / 2))
        colocados.append(c)
    tope = gab.fondo_util - r.holgura_puerta_mm
    for c in colocados:
        if c.w1 > tope + 1e-6:
            problemas.append(f"{c.designacion} sale {c.w1:.0f} mm de la placa y el fondo útil deja "
                             f"{tope:.0f} ({gab.fondo_util:.0f} − {r.holgura_puerta_mm:.0f} de holgura)")
    return colocados, rieles, canaletas, filas_info, problemas


# ── el tablero entero ─────────────────────────────────────────────────────────────────────


def _en(aps: list[Aparato], gab: Gabinete, r: Reglas, overrides: dict, acoples: dict) -> Layout:
    placa, rieles, canaletas, filas, problemas = _colocar_placa(
        [a for a in aps if a.montaje != "puerta"], gab, r, overrides, acoples)
    obstaculos = [(c.u0, c.v0, c.u0 + c.ancho, c.v0 + c.alto, c.w1, c.designacion) for c in placa]
    obstaculos += [(k.u0, k.v0, k.u1, k.v1, r.canaleta_alto_mm, f"la canaleta {k.orientacion}")
                   for k in canaletas]
    puerta, prob_puerta = colocar_puerta([a for a in aps if a.montaje == "puerta"], gab, r,
                                         overrides, obstaculos)
    problemas += prob_puerta
    if problemas:
        raise _NoEntra(problemas)
    return Layout(gab.ref, tuple(placa + puerta), tuple(rieles), tuple(canaletas), tuple(filas),
                  supuestos=r.supuestos())


def colocar(aparatos: list[Aparato], gabinete: str, gabinetes: list[Gabinete],
            overrides: dict | None = None, reglas: Reglas | None = None) -> Layout:
    """Coloca los aparatos de UNA ubicación en `gabinete` (una ref de `gabinetes` o `"auto"`)."""
    r = reglas or Reglas()
    overrides = _validar_overrides(dict(overrides or {}), aparatos)
    nombres = [a.designacion for a in aparatos]
    if len(set(nombres)) != len(nombres):
        repetidas = sorted({n for n in nombres if nombres.count(n) > 1})
        raise ColocacionError(f"designaciones repetidas en el tablero: {', '.join(repetidas)}")
    acoples = resolver_acoples(aparatos, overrides)
    por_area = sorted(gabinetes, key=lambda g: (g.area, g.ref))
    if not por_area:
        raise ColocacionError("no hay gabinetes con su interior declarado (`tablero.gabinete`)")
    if gabinete != "auto":
        gab = next((g for g in por_area if g.ref == gabinete), None)
        if gab is None:
            refs = [g.ref for g in por_area]
            raise ColocacionError(f"gabinete «{gabinete}» sin interior en el catálogo; gabinetes: "
                                  f"{', '.join(refs)} o «auto».{sufijo_sugerencia(gabinete, refs)}")
        try:
            return _en(aparatos, gab, r, overrides, acoples)
        except _NoEntra as exc:
            otro = next((g.ref for g in por_area
                         if g is not gab and _entra(aparatos, g, r, overrides, acoples)), None)
            pista = (f"; con «auto» entra en {otro}" if otro else
                     "; ningún gabinete del catálogo alcanza: reparte los aparatos en dos ubicaciones")
            raise ColocacionError(f"no entra en {gab.ref}: {'; '.join(exc.problemas)}{pista}") from None
    descartes: list[str] = []
    for gab in por_area:
        try:
            lay = _en(aparatos, gab, r, overrides, acoples)
        except _NoEntra as exc:
            descartes.append(f"{gab.ref}: {'; '.join(exc.problemas)}")
            continue
        avisos = tuple(f"auto: no entra en {d}" for d in descartes)
        return replace(lay, avisos=avisos + lay.avisos)
    raise ColocacionError("no entra en ningún gabinete del catálogo: " + " | ".join(descartes)
                          + "; reparte los aparatos en dos ubicaciones o suma un gabinete mayor")


def _entra(aparatos, gab, r, overrides, acoples) -> bool:
    try:
        _en(aparatos, gab, r, overrides, acoples)
    except _NoEntra:
        return False
    return True
