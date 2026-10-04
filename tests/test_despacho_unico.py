"""Despacho único de executors (plan estado-regen-y-params-estrictos, D3–D5).

Lo que se protege:
  - cada executor del `REGISTRY` recibe EXACTAMENTE `(ctx, cmd_id, p)`: una sola forma de
    llamada, sin flags `wants_*` que elijan entre 11 (una combinación sin rama propia caía
    en silencio en la primera que coincidiera);
  - `CommandSpec` rechaza al registrar lo que antes fallaba al ejecutar (kind/convention
    inválidos);
  - el despacho lee `spec.executor` en cada llamada (los tests de tortura y de caché
    parchean el executor en caliente);
  - `ExecContext` entrega los dicts VIVOS del estado (un executor muta en sitio).
"""

from __future__ import annotations

import inspect

import pytest

from apolo.commands.registry import REGISTRY, CommandError, execute_command
from apolo.commands.spec import CommandSpec, run_executor
from apolo.commands.state import ExecContext, RegenState

# Los 15 que salían de la forma por defecto (flags `wants_*` o kind="vars"): migraron en F2.
MIGRADOS_F2 = {
    "set_variable", "import_step", "insert_project", "run_script", "create_robot_arm",
    "add_joint", "add_mate", "add_rail_constraint", "add_constraint", "fasten", "ground",
    "join_bolted", "create_group", "transform_group", "pattern_group",
}


def _params(fn) -> list[tuple[str, object]]:
    return [(p.name, p.kind) for p in inspect.signature(fn).parameters.values()]


def test_cada_executor_recibe_exactamente_su_convencion():
    malos = []
    for tipo, spec in REGISTRY.items():
        primero = "ctx" if spec.convention == "ctx" else "scene"
        esperado = [(n, inspect.Parameter.POSITIONAL_OR_KEYWORD) for n in (primero, "cmd_id", "p")]
        if _params(spec.executor) != esperado:
            malos.append(f"{tipo} ({spec.convention}): {_params(spec.executor)}")
    assert not malos, "executors con otra firma:\n" + "\n".join(malos)


def test_los_15_con_flags_ya_reciben_ctx():
    assert MIGRADOS_F2 <= set(REGISTRY)
    assert {t for t, s in REGISTRY.items() if s.convention == "ctx"} == MIGRADOS_F2
    assert len(REGISTRY) == 53


def test_no_quedan_flags_wants():
    spec = REGISTRY["create_box"]
    assert not [n for n in vars(spec) if n.startswith("wants_")]
    with pytest.raises(TypeError):
        CommandSpec("x", "X", "crear", REGISTRY["create_box"].model, lambda c, i, p: None,
                    wants_joints=True)


@pytest.mark.parametrize("campo, valor", [("kind", "geometria"), ("convention", "kwargs")])
def test_commandspec_valida_al_registrar(campo, valor):
    with pytest.raises(ValueError, match=campo):
        CommandSpec("x", "X", "crear", REGISTRY["create_box"].model, lambda c, i, p: None,
                    **{campo: valor})


def test_commandspec_exige_executor_invocable():
    with pytest.raises(ValueError, match="invocable"):
        CommandSpec("x", "X", "crear", REGISTRY["create_box"].model, None)


def test_el_despacho_lee_el_executor_en_cada_llamada():
    spec = REGISTRY["ground"]
    orig = spec.executor
    vistos = []

    def espia(ctx, cmd_id, p):
        vistos.append((type(ctx).__name__, cmd_id, p.name))
        return orig(ctx, cmd_id, p)

    st = RegenState()
    execute_command(st, "c1", "create_box", {"name": "B", "width": 10, "depth": 10, "height": 5})
    spec.executor = espia
    try:
        execute_command(st, "c2", "ground", {"name": "g", "feature": "c1"})
    finally:
        spec.executor = orig
    assert vistos == [("ExecContext", "c2", "g")]
    assert set(st.grounds) == {"g"}


def test_exec_context_entrega_los_dicts_vivos():
    st = RegenState(variables={"W": "2*L", "L": "20"})
    ctx = ExecContext(st, {"a": b"x"})
    for nombre in RegenState.field_names():
        assert getattr(ctx, nombre) is getattr(st, nombre), nombre
    assert ctx.attachments == {"a": b"x"}
    assert ctx.resolved_variables() == {"W": 40.0, "L": 20.0}
    with pytest.raises(AttributeError):
        ctx.state = RegenState()  # frozen: el contexto no se reemplaza a mitad del executor
    assert ExecContext(st).attachments == {}


def test_run_executor_pasa_el_contexto():
    llamadas = []
    spec = CommandSpec("x", "X", "crear", REGISTRY["create_box"].model,
                       lambda ctx, cmd_id, p: llamadas.append((ctx, cmd_id, p)), convention="ctx")
    ctx = ExecContext(RegenState())
    run_executor(spec, ctx, "c9", "modelo")
    assert llamadas == [(ctx, "c9", "modelo")]


def test_run_script_ve_las_variables_resueltas():
    st = RegenState()
    execute_command(st, "c1", "set_variable", {"name": "L", "expression": "30"})
    execute_command(st, "c2", "run_script", {
        "name": "S", "code": "result = Box(V['L'], 10, 10)",
    })
    bb = st.scene["c2"].shape.bounding_box()
    assert round(bb.max.X - bb.min.X) == 30


def test_import_step_lee_los_adjuntos_del_contexto():
    st = RegenState()
    with pytest.raises(CommandError, match="adjunto"):
        execute_command(st, "c1", "import_step", {"name": "S", "attachment": "nada"}, {})
