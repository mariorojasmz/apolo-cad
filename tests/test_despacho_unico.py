"""Despacho único de executors (plan estado-regen-y-params-estrictos, D3–D5).

Lo que se protege:
  - cada executor del `REGISTRY` recibe EXACTAMENTE `(ctx, cmd_id, p)`: una sola forma de
    llamada, sin flags `wants_*` que elijan entre 11 (una combinación sin rama propia caía
    en silencio en la primera que coincidiera) ni convenciones de transición;
  - `CommandSpec` rechaza al registrar lo que antes fallaba al ejecutar (kind inválido,
    executor no invocable);
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

ESPERADO = [(n, inspect.Parameter.POSITIONAL_OR_KEYWORD) for n in ("ctx", "cmd_id", "p")]


def _params(fn) -> list[tuple[str, object]]:
    return [(p.name, p.kind) for p in inspect.signature(fn).parameters.values()]


def test_cada_executor_recibe_exactamente_ctx_cmd_id_p():
    assert len(REGISTRY) == 53
    malos = [f"{tipo}: {_params(s.executor)}" for tipo, s in REGISTRY.items()
             if _params(s.executor) != ESPERADO]
    assert not malos, "executors con otra firma:\n" + "\n".join(malos)


@pytest.mark.parametrize("extra", [{"wants_joints": True}, {"convention": "scene"}])
def test_no_quedan_flags_ni_convenciones(extra):
    assert not [n for n in vars(REGISTRY["create_box"]) if n.startswith("wants_")]
    assert not hasattr(REGISTRY["create_box"], "convention")
    with pytest.raises(TypeError):
        CommandSpec("x", "X", "crear", REGISTRY["create_box"].model, lambda c, i, p: None,
                    **extra)


def test_commandspec_valida_el_kind_al_registrar():
    with pytest.raises(ValueError, match="kind"):
        CommandSpec("x", "X", "crear", REGISTRY["create_box"].model, lambda c, i, p: None,
                    kind="geometria")


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
                       lambda ctx, cmd_id, p: llamadas.append((ctx, cmd_id, p)))
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
