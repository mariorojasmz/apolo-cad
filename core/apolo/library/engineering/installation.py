"""Datos de INSTALACIÓN de una máquina (V7.6 fase C): lo que el cliente lleva a la obra
civil antes de que llegue el equipo — cuánto pesa cada apoyo, dónde van los anclajes, qué
holgura hay que dejar para el servicio y qué suministro hace falta.

Funciones PURAS (reciben números y dicts, nunca un ``Document``): la capa API resuelve la
geometría y aquí solo se calcula. El reparto de carga por apoyo usa el método elástico de
grupo (el mismo que un grupo de pernos con momento): con más de 3 apoyos el problema es
hiperestático y la hipótesis queda DECLARADA en el reporte — nunca implícita.
"""

from __future__ import annotations

G_M_S2 = 9.81


def anchor_loads(supports: list[dict], weight_n: float,
                 cog_xy: tuple[float, float] | None = None) -> dict:
    """Carga vertical por APOYO de un grupo, con el peso aplicado en el COG.

    `supports`: [{"id", "name", "x", "y"}] (centros en planta, mm). `weight_n`: peso
    TOTAL (N) = (masa propia + carga de diseño)·g. `cog_xy`: centro de gravedad en planta;
    None → se asume sobre el centroide de los apoyos (reparto uniforme).

    Método (reparto ELÁSTICO de grupo, análogo a un grupo de pernos con momento):

        R_i = W/N + W·e_y·(y_i−y_c)/Σ(y_j−y_c)² + W·e_x·(x_i−x_c)/Σ(x_j−x_c)²

    donde (x_c, y_c) es el centroide de los apoyos y **e** la excentricidad del COG
    respecto a él. HIPÓTESIS declarada: apoyos de rigidez IGUAL sobre piso rígido; con
    N > 3 el reparto real es hiperestático y depende de la nivelación y de la rigidez del
    piso — por eso el reporte publica también el uniforme y marca el apoyo gobernante.
    Un R_i NEGATIVO significa que ese apoyo LEVANTA: el anclaje trabaja a TRACCIÓN, dato
    crítico para la obra (se declara explícitamente, jamás se recorta a cero)."""
    if not supports:
        raise ValueError("se necesita al menos un apoyo para repartir la carga")
    n = len(supports)
    W = float(weight_n)
    xs = [float(s["x"]) for s in supports]
    ys = [float(s["y"]) for s in supports]
    xc, yc = sum(xs) / n, sum(ys) / n
    if cog_xy is None:
        ex = ey = 0.0
        cgx, cgy = xc, yc
    else:
        cgx, cgy = float(cog_xy[0]), float(cog_xy[1])
        ex, ey = cgx - xc, cgy - yc
    ixx = sum((y - yc) ** 2 for y in ys)     # Σ(y−yc)²: 0 si los apoyos se alinean en y
    iyy = sum((x - xc) ** 2 for x in xs)
    filas = []
    for s, x, y in zip(supports, xs, ys):
        r = W / n
        if ixx > 1e-9:
            r += W * ey * (y - yc) / ixx
        if iyy > 1e-9:
            r += W * ex * (x - xc) / iyy
        filas.append({
            "id": s.get("id"), "apoyo": s.get("name", s.get("id")),
            "x_mm": round(x, 1), "y_mm": round(y, 1),
            "carga_n": round(r, 1), "carga_kg": round(r / G_M_S2, 1),
            "traccion": r < 0.0,
        })
    gob = max(filas, key=lambda f: f["carga_n"])
    return {
        "n_apoyos": n,
        "peso_total_n": round(W, 1),
        "centroide_apoyos_mm": [round(xc, 1), round(yc, 1)],
        "cog_mm": [round(cgx, 1), round(cgy, 1)],
        "excentricidad_mm": [round(ex, 1), round(ey, 1)],
        "uniforme_kg": round(W / n / G_M_S2, 1),
        "gobernante": gob["apoyo"],
        "carga_max_kg": gob["carga_kg"],
        "hay_traccion": any(f["traccion"] for f in filas),
        "apoyos": filas,
        "hipotesis": (
            f"reparto elástico de grupo con el peso en el COG (excentricidad "
            f"{abs(ex):.0f}/{abs(ey):.0f} mm); apoyos de igual rigidez sobre piso rígido"
            + (f"; con {n} apoyos el reparto es hiperestático — el uniforme sería "
               f"{W / n / G_M_S2:.1f} kg/apoyo" if n > 3 else "")
        ),
    }


def installation_rows(data: dict) -> list[list[str]]:
    """Filas [concepto, valor, nota] de la tabla de DATOS DE INSTALACIÓN. `data` lo arma
    la capa API (masa, cargas, huella, alturas, holguras, suministro); aquí solo se
    formatea para la lámina — sin unidades inventadas ni ceros de relleno."""
    rows: list[list[str]] = []

    def add(concepto, valor, nota=""):
        if valor not in (None, ""):
            rows.append([str(concepto), str(valor), str(nota)])

    add("Masa de la máquina", f"{data['masa_kg']:g} kg", "vacía, sin producto")
    if data.get("carga_kg"):
        add("Carga de diseño", f"{data['carga_kg']:g} kg", "producto sobre la máquina")
    al = data.get("anclaje") or {}
    if al:
        add("Apoyos anclados", f"{al['n_apoyos']}", "ver huella acotada")
        add("Carga máx. por apoyo", f"{al['carga_max_kg']:g} kg",
            f"en «{str(al['gobernante'])[:22]}»")
        if al.get("hay_traccion"):
            add("AVISO", "un apoyo a TRACCIÓN", "el anclaje debe resistir arranque")
    hu = data.get("huella_mm") or {}
    if hu:
        add("Huella de anclaje", f"{hu['largo']:g} × {hu['ancho']:g} mm",
            "entre ejes de anclaje extremos")
    if data.get("altura_trabajo_mm"):
        add("Altura de transporte", f"{data['altura_trabajo_mm']:g} mm", "interfaz E/S")
    if data.get("altura_total_mm"):
        add("Altura total", f"{data['altura_total_mm']:g} mm", "punto más alto")
    for s in (data.get("servicio") or []):
        add(f"Holgura de servicio · {s['pieza'][:20]}", f"{s['holgura_mm']:g} mm",
            "extracción lateral")
    for e in (data.get("suministro") or []):
        add(e["concepto"], e["valor"], e.get("nota", ""))
    return rows
