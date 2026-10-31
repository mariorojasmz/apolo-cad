"""`add_joint` sobre la raíz de un patrón o un conjunto (D9 de puerta-fuera-de-catalogo).

`parent`/`child` aceptan lo mismo que `fasten` (`exec_uniones.resolver_conjunto`): la raíz de un
patrón = sus copias `{raíz}_{n}` (sin la fuente), `+` y corte. Se registra UNA junta por par,
`{name}[k]`, emparejada por posición como las uniones en lote, y se re-expande en cada
regenerate: al subir N nace la junta de la copia nueva y al bajarlo se va con su copia (una
junta que nombra la copia `c152_3` a mano queda colgando cuando el patrón ya no la crea).

Decisión (vetable): una junta por instancia, no una sola junta que arrastre las copias. Cada
copia gira sobre SU eje (los peldaños de una escalera, las puertas de un armario): una junta
única las movería como un cuerpo alrededor de un eje. El `origin` dado es el de la PRIMERA
instancia; el de la instancia k se traslada lo que se trasladó su pieza respecto de la primera
(el centro de su caja: exacto en un patrón lineal o de grupo, que sólo trasladan). El eje y los
límites son los mismos. Con `arrastrar`, cada junta materializa su propio arrastre.
"""

from __future__ import annotations

from .errors import CommandError


def _centro(scene: dict, fid: str) -> tuple[float, float, float]:
    c = scene[fid].shape.bounding_box().center()
    return (c.X, c.Y, c.Z)


def juntas_en_lote(ctx, cmd_id: str, p, pares: list[tuple[str, str]], registrar, arrastre) -> None:
    """Registra `{p.name}[k]` por cada par (padre_k, hijo_k). `registrar`/`arrastre` son
    `_register_joint`/`_joint_drag` de `exec_ensamblaje` (inyectados: sin ciclo de imports)."""
    scene, joints = ctx.scene, ctx.joints
    for fid in {x for par in pares for x in par}:
        if fid not in scene:
            raise CommandError(f"No existe el sólido '{fid}' en la escena")
    # lo que varía entre instancias: el hijo si es un conjunto, si no el padre
    varia = 1 if len({h for _, h in pares}) > 1 else 0
    base = _centro(scene, pares[0][varia])
    o0 = p.origin.tuple()
    for k, par in enumerate(pares):
        c = _centro(scene, par[varia])
        origen = [o0[i] + c[i] - base[i] for i in range(3)]
        nombre = f"{p.name}[{k}]"
        registrar(scene, joints, cmd_id, {
            "name": nombre, "type": p.type, "parent": par[0], "child": par[1],
            "origin": origen, "axis": list(p.axis.tuple()), "lower": p.lower, "upper": p.upper,
        })
        joints[nombre].update({"conjunto": p.name, "indice": k})
        if p.arrastrar:
            q = p.model_copy(update={"name": nombre, "parent": par[0], "child": par[1]})
            joints[nombre]["arrastre"] = arrastre(scene, joints, ctx.fasteners, ctx.grounds, cmd_id, q)
