"""Reglas de ingeniería de un documento: lo que `/api/checks` y la memoria de cálculo
COMPARTEN de verdad (bases de diseño desde los requisitos, inclinación heredada, chequeo
estructural universal + FEA con vigencia) y los parámetros de la faja paramétrica, que usan
también la tool `engineering_check` del agente. Sus DIFERENCIAS son deliberadas y quedan en
cada endpoint (velocidad con `or` vs `is not None`, lints sólo en checks, stack-up y «alcance»
sólo en la memoria). El llamador sostiene STATE_LOCK. Reglas: `services/CLAUDE.md`."""

from __future__ import annotations


def conveyor_params_from_doc(doc) -> dict | None:
    """Los params del ÚLTIMO transportador paramétrico del log: un `create_conveyor` o un
    `create_roller_conveyor` (éste con `plantilla`, que `conveyor_engineering_check` valida con
    sus reglas propias contra la ficha; plan plantilla-rodillos-cadena D9)."""
    from apolo.commands import resolve_params

    tipos = ("create_conveyor", "create_roller_conveyor")
    cmd = next((c for c in reversed(doc.commands) if c["type"] in tipos), None)
    if cmd is None:
        return None
    params = resolve_params(cmd["params"], doc.variables_resolved)
    if cmd["type"] == "create_roller_conveyor":
        from apolo.commands.models_rodillos_cadena import CreateRollerConveyorParams

        try:
            params = CreateRollerConveyorParams.model_validate(params, extra="ignore").model_dump(
                exclude={"position"})
        except ValueError:  # params rotos: las reglas lo dicen como error, sin tumbar el chequeo
            pass
        return {"plantilla": cmd["type"], **params}
    defaults = {"largo": 2000, "ancho": 600, "altura": 750, "paso": 100, "rodillo": "RODILLO-50", "motor": "ninguno"}
    return {**defaults, **params}


def requirement_inputs(doc, carga_kg, largo_paquete_mm, ancho_paquete_mm) -> tuple:
    """`(req, carga, largo_paq, ancho_paq)`: los REQUISITOS guardados (bases de diseño)
    rellenan lo que la llamada no trae — los parámetros explícitos siempre GANAN."""
    req = doc.requirements or {}
    carga = carga_kg if carga_kg is not None else req.get("carga_kg")
    largo_paq = (largo_paquete_mm if largo_paquete_mm is not None
                 else req.get("largo_paquete_mm"))
    ancho_paq = (ancho_paquete_mm if ancho_paquete_mm is not None
                 else req.get("ancho_paquete_mm"))
    return req, carga, largo_paq, ancho_paq


def inherit_inclination(conveyor: dict | None, req: dict) -> None:
    """La faja hereda la inclinación de los requisitos si no declara la suya (muta)."""
    if conveyor and req.get("inclinacion_deg") and not conveyor.get("inclinacion_deg"):
        conveyor["inclinacion_deg"] = req["inclinacion_deg"]


def inherit_tensor(doc, conveyor: dict | None) -> None:
    """La adherencia de Eytelwein sabe si hay tensor por el RECONOCIMIENTO de la puerta de
    publicación (`calidad_tensores`: take-up, unidad de catálogo, ranuras de la plantilla o el
    metadato `tensores`), nunca por el nombre de una pieza (plan puerta-de-publicacion D3). Un
    `tiene_tensor` explícito del cliente gana (muta)."""
    if conveyor and "tiene_tensor" not in conveyor:
        from .calidad_tensores import tiene_tensor_reconocido

        conveyor["tiene_tensor"] = tiene_tensor_reconocido(doc)


def structure_rules(doc, carga, conveyor: dict | None) -> list[dict]:
    """Chequeo estructural UNIVERSAL (pernos/soldaduras/L10/pandeo/vuelco): aplica a
    cualquier ensamblaje, no exige carga ni faja detectada; más la flecha de las vigas del
    bastidor (`vigas_rules`), el pandeo de sus columnas (`columnas_rules`), la transmisión por cadena de cada `create_chain`, la
    capacidad de cada cadena de izaje (`izaje_rules`) y los
    resultados FEA guardados (con chequeo de vigencia). Llamar bajo STATE_LOCK."""
    from apolo.library.engineering.report import structure_engineering_check

    from .calidad_contacto import cordones_medidos
    from .columnas_rules import columna_rules
    from .fea_rules import fea_rules
    from .izaje_rules import hoist_rules
    from .transmision_rules import chain_rules
    from .vigas_rules import beam_rules

    rpm = (conveyor or {}).get("rpm_motor")
    declarados = None if rpm else rodamientos_declarados(doc)
    # la capacidad de cada cadena de izaje dimensiona los pasadores de sus amarres (F2a de
    # cadena-de-izaje): corre ANTES para que no cuenten «sin dimensionar»
    izaje, pasadores = hoist_rules(doc, carga)
    rules = structure_engineering_check(
        doc.scene, doc.fasteners, doc.grounds, doc.joints, doc.mates,
        carga_kg=carga or 0.0,
        rpm=rpm,
        belt_radial_n=(conveyor or {}).get("bearing_radial_n"),
        default_material=doc.default_material(),  # la masa de mass-properties (F6)
        rodamientos=declarados,
        uniones_verificadas=pasadores,
        cordones=cordones_medidos(doc),  # uniones-que-tocan D1b: el cordón que de verdad hay
    )
    rules += beam_rules(doc, carga)
    rules += columna_rules(doc, carga)  # F3f de puerta-sin-sobrediseno
    rules += chain_rules(doc)
    rules += izaje
    rules += fea_rules(doc)
    if conveyor is None:  # el transportador calcula su motorización con sus reglas
        rules += accionamiento_declarado(doc, declarados)
    return rules


def servicio_declarado(doc) -> tuple[float, str]:
    """(FS que pide el servicio declarado, de dónde sale): `library/engineering/servicio.py`."""
    from apolo.library.engineering.servicio import fs_requerido

    req = doc.requirements or {}
    return fs_requerido(req.get("tipo_carga"), _num(req.get("horas_dia")))


def accionamiento_declarado(doc, declarados: dict | None = None) -> list[dict]:
    """El factor de servicio de cada motorreductor de catálogo de una máquina que NO es
    transportador (F3c de puerta-sin-sobrediseno): lo que da la ficha contra lo que la máquina
    declara que pide (`potencia_absorbida_kw` o `par_salida_nm`), con el FS de su servicio. Sin
    motorreductor, nada; con varios, el requisito es de la máquina y no dice de cuál: aviso."""
    from apolo.library.catalog import CATALOG
    from apolo.library.engineering.servicio import REGLA, regla_factor_servicio

    motores = [(fid, f, c) for fid, f in doc.scene.items()
               if (c := CATALOG.get(getattr(f, "component", None) or "")) is not None
               and c.category in ("motorreductores", "motorreductores_sinfin")]
    if not motores:
        return []
    if len(motores) > 1:
        return [{"regla": REGLA, "estado": "aviso", "piezas": [m[0] for m in motores],
                 "detalle": f"{len(motores)} motorreductores: el requisito de lo que pide la "
                            "máquina no dice de cuál; el factor de servicio no se calcula"}]
    fid, f, c = motores[0]
    specs = c.specs or {}
    motor = {"fid": fid, "nombre": f.name or fid, "ref": c.ref,
             "potencia_kw": specs.get("potencia_kW") or specs.get("potencia_kw"),
             "torque_nm": specs.get("torque_Nm"),
             "sinfin": c.category == "motorreductores_sinfin"}
    rpm = (declarados if declarados is not None else rodamientos_declarados(doc) or {}).get("rpm")
    fs_req, origen = servicio_declarado(doc)
    return [regla_factor_servicio(motor, doc.requirements or {}, rpm, fs_req, origen)]


def _num(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x > 0 else None


def rodamientos_declarados(doc) -> dict | None:
    """Lo que la vida L10 de una máquina que NO es transportador lee de lo declarado (F3b de
    puerta-sin-sobrediseno; con transportador, sus rpm y su tensión de banda, como siempre) →
    {rpm, fuente, p_n?} o None sin rpm. Las rpm, en este orden: el requisito `rpm_salida`, la
    variable `rpm_salida`, las variables `rpm_motor` / `ratio_red`, y el `rpm_salida` de catálogo
    del motorreductor (si todos dicen lo mismo). La carga sólo del requisito `carga_rodamiento_n`
    (la carga radial equivalente por rodamiento): `carga_kg` es el producto, no lo que carga un
    rodamiento de un agitador o un eje de izaje, y no se reparte a ciegas."""
    from apolo.library.catalog import CATALOG

    req, var = doc.requirements or {}, doc.variables_resolved or {}
    rpm, fuente = _num(req.get("rpm_salida")), "requisito rpm_salida"
    if rpm is None:
        rpm, fuente = _num(var.get("rpm_salida")), "variable rpm_salida"
    if rpm is None and _num(var.get("rpm_motor")) and _num(var.get("ratio_red")):
        rpm = _num(var["rpm_motor"]) / _num(var["ratio_red"])
        fuente = "variables rpm_motor / ratio_red"
    if rpm is None:
        de_catalogo = {_num((c.specs or {}).get("rpm_salida")) for f in doc.scene.values()
                       if (c := CATALOG.get(getattr(f, "component", None) or "")) is not None
                       and c.category in ("motorreductores", "motorreductores_sinfin")}
        if len(de_catalogo) == 1 and None not in de_catalogo:
            rpm, fuente = de_catalogo.pop(), "rpm_salida del motorreductor de catálogo"
    if rpm is None:
        return None
    out = {"rpm": rpm, "fuente": fuente}
    if _num(req.get("carga_rodamiento_n")):
        out["p_n"] = _num(req["carga_rodamiento_n"])
    return out
