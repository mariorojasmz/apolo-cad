"""Agente IA Nivel 1: configurador por tool use sobre el registro de comandos.

El agente propone lotes de comandos (tarjetas de acción); el cliente decide
ejecutarlos vía POST /api/commands/batch. Las tools del agente se generan del
mismo registro que alimenta la UI, de modo que IA y usuario comparten
exactamente las mismas operaciones.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator

from apolo.commands.registry import REGISTRY, CommandError, validate_params
from apolo.doc import Document

from .prompts import SYSTEM_PROMPT

DEFAULT_MODEL = os.environ.get("APOLO_MODEL", "claude-opus-4-8")
MAX_ITERATIONS = 10


def execute_actions_now(doc: Document, actions: list[dict]) -> dict:
    """Modo autónomo: ejecuta el lote sobre el documento (con autosave y aviso
    a los clientes) y devuelve un resumen para que el agente verifique."""
    from apolo.batch import execute_batch
    from apolo.state import STATE_LOCK

    with STATE_LOCK:
        created = execute_batch(doc, actions)
        try:
            from apolo.api import main as api_main

            api_main._autosave()
        except Exception:
            pass
        summary = {
            "ejecutado": True,
            "comandos_creados": created,
            "solidos_en_escena": len(doc.scene),
            "variables": dict(doc.variables_resolved),
        }
    try:
        from apolo.api import main as api_main

        api_main.WS.notify_changed()
    except Exception:
        pass
    return summary


def save_agent_note(doc: Document, text: str) -> None:
    from apolo.state import STATE_LOCK

    with STATE_LOCK:
        doc.agent_notes.append(text.strip()[:500])
        doc.agent_notes = doc.agent_notes[-30:]  # memoria acotada
        try:
            from apolo.api import main as api_main

            api_main._autosave()
        except Exception:
            pass


def build_tools(auto: bool = False) -> list[dict]:
    action_schema = {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "enum": list(REGISTRY.keys()),
                "description": "Tipo de comando",
            },
            "params": {
                "type": "object",
                "description": "Parámetros según el schema del comando",
            },
            "reason": {
                "type": "string",
                "description": "Justificación breve para el usuario",
            },
        },
        "required": ["type", "params", "reason"],
    }
    command_docs = "\n".join(
        f"- {spec.type}: {(spec.model.__doc__ or '').strip()} Schema: "
        f"{json.dumps(spec.model.model_json_schema(), ensure_ascii=False)}"
        for spec in REGISTRY.values()
    )
    batch_tool = (
        {
            "name": "execute_commands",
            "description": (
                "MODO AUTÓNOMO (aprobado por el usuario): ejecuta el lote de comandos "
                "INMEDIATAMENTE sobre el documento y devuelve un resumen. Después VERIFICA "
                "(check_interference, engineering_check, render_view) y corrige si hace falta "
                "(undo_last + nuevo lote). Usa '$k' para referenciar sólidos creados en el mismo "
                "lote.\nComandos disponibles:\n" + command_docs
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "actions": {"type": "array", "items": action_schema, "minItems": 1}
                },
                "required": ["actions"],
            },
        }
        if auto
        else None
    )

    extra_auto = (
        [
            {
                "name": "undo_last",
                "description": "Deshace la última mutación del documento (para corregir un lote erróneo en modo autónomo).",
                "input_schema": {"type": "object", "properties": {}},
            }
        ]
        if auto
        else []
    )

    note_tool = {
        "name": "save_note",
        "description": (
            "Guarda una nota persistente en la memoria del proyecto (decisiones de diseño, "
            "supuestos, pendientes). Las notas aparecen en get_document en futuras sesiones."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"text": {"type": "string", "maxLength": 500}},
            "required": ["text"],
        },
    }

    tools = [t for t in [batch_tool] if t] + extra_auto + [
        note_tool,
        {
            "name": "get_document",
            "description": "Devuelve el estado actual del documento: log de comandos y sólidos de la escena con sus dimensiones.",
            "input_schema": {"type": "object", "properties": {}},
        },
        {
            "name": "get_catalog",
            "description": (
                "Devuelve el catálogo de componentes de la biblioteca (perfiles, rodillos, "
                "motorreductores, patas, guardas, sensores) con referencias, especificaciones, "
                "pesos y si admiten longitud a medida. Úsalo antes de elegir componentes."
            ),
            "input_schema": {"type": "object", "properties": {}},
        },
        {
            "name": "test_sketch",
            "description": (
                "Resuelve un croquis restringido SIN tocar el documento y devuelve los puntos "
                "exactos o el diagnóstico de las restricciones en conflicto. Itera aquí hasta "
                "ok=true y SOLO entonces proponlo en sketch_extrude/sketch_revolve. El formato "
                "del croquis está en los schemas de esos comandos."
            ),
            "input_schema": {
                "type": "object",
                "properties": {"sketch": {"type": "object"}},
                "required": ["sketch"],
            },
        },
        {
            "name": "test_script",
            "description": (
                "Ejecuta un script build123d en el sandbox SIN tocar el documento y devuelve "
                "dimensiones y volumen del resultado (o el error). Itera aquí hasta que el "
                "script funcione y SOLO entonces proponlo con run_script. El script debe "
                "asignar `result`; dispone de build123d, math y V (variables del proyecto)."
            ),
            "input_schema": {
                "type": "object",
                "properties": {"code": {"type": "string", "description": "código Python build123d"}},
                "required": ["code"],
            },
        },
        {
            "name": "check_interference",
            "description": (
                "Detecta interferencias (solapes con volumen) entre los sólidos visibles de la "
                "escena mediante intersección booleana. El contacto cara a cara no cuenta. "
                "Con joint_values {nombre_junta: valor} comprueba la COLISIÓN EN POSE del "
                "mecanismo (p. ej. el brazo con el codo a -120°). Úsalo tras un montaje y para "
                "verificar el rango de movimiento de un robot."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "joint_values": {
                        "type": "object",
                        "description": "valores de junta (grados o mm) para posar el mecanismo",
                    }
                },
            },
        },
        {
            "name": "engineering_check",
            "description": (
                "Valida un transportador contra las reglas de ingeniería del vertical: apoyo "
                "del paquete (≥3 rodillos), capacidad por rodillo, ancho útil y potencia de "
                "motor requerida (con recomendación de catálogo). Pasa los parámetros del "
                "transportador que PLANEAS proponer para validarlo ANTES de proponerlo; si los "
                "omites, se valida el último create_conveyor del documento."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "carga_kg": {"type": "number", "description": "peso del paquete"},
                    "largo_paquete_mm": {"type": "number"},
                    "ancho_paquete_mm": {"type": "number"},
                    "velocidad_m_s": {"type": "number", "description": "0 = gravedad"},
                    "conveyor": {
                        "type": "object",
                        "description": "params de create_conveyor a validar (largo, ancho, paso, rodillo, motor)",
                    },
                },
                "required": ["carga_kg", "largo_paquete_mm", "velocidad_m_s"],
            },
        },
        {
            "name": "render_view",
            "description": (
                "Renderiza la escena actual a una imagen y te la devuelve para que la MIRES. "
                "Úsala para verificar visualmente proporciones, posiciones y montaje tras "
                "cambios importantes. Vistas: iso, frente, planta, lateral."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "view": {"type": "string", "enum": ["iso", "frente", "planta", "lateral"]}
                },
            },
        },
        {
            "name": "propose_commands",
            "description": (
                "Propone al usuario un lote ordenado de comandos CAD como tarjetas de acción. "
                "No se ejecuta nada hasta que el usuario acepte. Usa '$k' como id de feature "
                "para referirte al sólido creado por la k-ésima acción del lote.\n"
                "Comandos disponibles:\n" + command_docs
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "actions": {"type": "array", "items": action_schema, "minItems": 1}
                },
                "required": ["actions"],
            },
        },
    ]
    if auto:  # en modo autónomo se ejecuta directamente: propose_commands sobra
        tools = [t for t in tools if t["name"] != "propose_commands"]
    return tools


def document_summary(doc: Document) -> dict:
    """Resumen del documento para el agente. Toma el lock de estado para no
    leer formas OCCT mientras otra petición las regenera."""
    from apolo.kernel import bbox_payload
    from apolo.state import STATE_LOCK

    with STATE_LOCK:
        return _build_summary(doc, bbox_payload)


def _build_summary(doc: Document, bbox_payload) -> dict:
    return {
        "name": doc.name,
        "notas_del_proyecto": doc.agent_notes,
        "commands": doc.commands,
        "variables": {
            name: {"expression": doc.variables_raw.get(name), "value": value}
            for name, value in doc.variables_resolved.items()
        },
        "features": [
            {
                "id": f.id,
                "name": f.name,
                "visible": f.visible,
                "bbox": bbox_payload(f.shape),
                "volume_mm3": round(f.shape.volume, 1),
            }
            for f in doc.scene.values()
        ],
    }


def validate_actions(actions: list[dict], variables: dict | None = None) -> list[str]:
    """Valida cada acción contra su schema, simulando secuencialmente las
    variables que el propio lote define (set_variable seguido de su uso).
    Los placeholders '$k' pasan porque los campos de referencia a features
    son strings. Devuelve lista de errores."""
    errors = []
    pending_vars = dict(variables or {})
    for i, action in enumerate(actions, start=1):
        cmd_type = action.get("type")
        params = action.get("params") or {}
        try:
            validate_params(cmd_type, params, pending_vars)
            if cmd_type == "set_variable":
                pending_vars[params["name"]] = params["expression"]
        except CommandError as exc:
            errors.append(f"Acción {i}: {exc}")
    return errors


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _conveyor_params_from_doc(doc: Document) -> dict | None:
    from apolo.commands import resolve_params

    cmd = next((c for c in reversed(doc.commands) if c["type"] == "create_conveyor"), None)
    if cmd is None:
        return None
    defaults = {"largo": 2000, "ancho": 600, "altura": 750, "paso": 100, "rodillo": "RODILLO-50", "motor": "ninguno"}
    return {**defaults, **resolve_params(cmd["params"], doc.variables_resolved)}


def run_validation_tool(doc: Document, name: str, tool_input: dict):
    """Ejecuta una tool de validación. Devuelve str (JSON) o lista de bloques
    de contenido (para imágenes)."""
    from apolo.state import STATE_LOCK

    if name == "test_sketch":
        from apolo.commands import resolve_params
        from apolo.kernel.sketch_solver import SketchError, solve_sketch

        try:
            with STATE_LOCK:
                sketch = resolve_params(tool_input.get("sketch") or {}, dict(doc.variables_resolved))
            return json.dumps(solve_sketch(sketch), ensure_ascii=False)
        except (SketchError, Exception) as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)

    if name == "test_script":
        from apolo.sandbox import ScriptError, run_script_to_shape

        with STATE_LOCK:
            variables = dict(doc.variables_resolved)
        try:
            shape = run_script_to_shape(tool_input.get("code", ""), variables)
            from apolo.kernel import bbox_payload

            return json.dumps(
                {"ok": True, "volume_mm3": round(shape.volume, 1), "bbox": bbox_payload(shape)},
                ensure_ascii=False,
            )
        except ScriptError as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)

    if name == "check_interference":
        from apolo.library import interference_report
        from apolo.library.checks import hardware_ids, joint_pairs, same_command_pairs

        joint_values = tool_input.get("joint_values") or {}
        with STATE_LOCK:
            shapes_override = None
            warnings: list[str] = []
            if any(float(v) != 0 for v in joint_values.values()):
                from apolo.robotics.pose import posed_shapes

                shapes_override, warnings = posed_shapes(
                    doc, {k: float(v) for k, v in joint_values.items()}
                )
            report = interference_report(
                doc.scene, shapes_override=shapes_override,
                exclude_pairs=joint_pairs(doc) | same_command_pairs(doc),
                exclude_ids=hardware_ids(doc),
            )
            report["avisos_pose"] = warnings
            return json.dumps(report, ensure_ascii=False)

    if name == "engineering_check":
        from apolo.library import conveyor_engineering_check

        from apolo.library.rules import detect_conveyor

        with STATE_LOCK:
            conveyor = (
                tool_input.get("conveyor")
                or _conveyor_params_from_doc(doc)
                or detect_conveyor(doc.scene, doc.variables_resolved)
            )
        if not conveyor:
            return json.dumps(
                {"error": "No hay transportador en el documento ni parámetros 'conveyor' en la llamada"},
                ensure_ascii=False,
            )
        try:
            checks = conveyor_engineering_check(
                conveyor,
                carga_kg=float(tool_input["carga_kg"]),
                largo_paquete_mm=float(tool_input["largo_paquete_mm"]),
                velocidad_m_s=float(tool_input["velocidad_m_s"]),
                ancho_paquete_mm=(
                    float(tool_input["ancho_paquete_mm"]) if tool_input.get("ancho_paquete_mm") else None
                ),
            )
        except (KeyError, ValueError, TypeError) as exc:
            return json.dumps({"error": f"Parámetros inválidos: {exc}"}, ensure_ascii=False)
        return json.dumps({"conveyor": conveyor, "checks": checks}, ensure_ascii=False)

    if name == "render_view":
        import base64

        from apolo.kernel.render import render_scene_png

        view = tool_input.get("view", "iso")
        try:
            with STATE_LOCK:
                png = render_scene_png(doc.scene, view)
        except ValueError as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)
        return [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": base64.standard_b64encode(png).decode("ascii"),
                },
            },
            {"type": "text", "text": f"Render de la escena, vista {view} (unidades mm)."},
        ]

    return None


def chat_stream(
    doc: Document, messages: list[dict], model: str | None = None, auto: bool = False
) -> Iterator[str]:
    """Genera eventos SSE: {'type':'text'|'actions'|'tool'|'error'|'done', ...}.
    Con auto=True el agente ejecuta los lotes directamente (modo autónomo)."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        yield _sse(
            {
                "type": "error",
                "message": "Falta la variable de entorno ANTHROPIC_API_KEY: el asistente IA no está disponible.",
            }
        )
        yield _sse({"type": "done"})
        return

    import anthropic

    client = anthropic.Anthropic()
    tools = build_tools(auto=auto)
    convo = [{"role": m["role"], "content": m["content"]} for m in messages]
    if auto:
        convo.insert(
            0,
            {
                "role": "user",
                "content": "<system-reminder>El usuario ha activado el MODO AUTÓNOMO: ejecuta "
                "con execute_commands, verifica con las tools de validación y corrige si hace "
                "falta, sin pedir confirmación. Resume al final qué construiste y qué validaste."
                "</system-reminder>",
            },
        )

    try:
        for _ in range(MAX_ITERATIONS if not auto else MAX_ITERATIONS + 4):
            with client.messages.stream(
                model=model or DEFAULT_MODEL,
                max_tokens=16000,
                thinking={"type": "adaptive"},
                system=SYSTEM_PROMPT,
                tools=tools,
                messages=convo,
            ) as stream:
                for text in stream.text_stream:
                    yield _sse({"type": "text", "text": text})
                response = stream.get_final_message()

            if response.stop_reason != "tool_use":
                break

            convo.append({"role": "assistant", "content": response.content})
            tool_results = []
            proposed = False
            for block in response.content:
                if block.type != "tool_use":
                    continue
                if block.name == "get_document":
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(document_summary(doc), ensure_ascii=False),
                        }
                    )
                elif block.name == "get_catalog":
                    from apolo.library import catalog_payload

                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(catalog_payload(), ensure_ascii=False),
                        }
                    )
                elif block.name == "execute_commands":
                    actions = (block.input or {}).get("actions", [])
                    errors = validate_actions(actions, doc.variables_raw)
                    if errors:
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": "Parámetros inválidos, corrige y reintenta:\n" + "\n".join(errors),
                                "is_error": True,
                            }
                        )
                    else:
                        yield _sse({"type": "actions", "actions": actions, "executed": True})
                        try:
                            summary = execute_actions_now(doc, actions)
                            content = json.dumps(summary, ensure_ascii=False)
                            is_error = False
                        except Exception as exc:
                            content = f"El lote falló y se revirtió: {exc}"
                            is_error = True
                        yield _sse({"type": "tool", "name": "execute_commands"})
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": content,
                                **({"is_error": True} if is_error else {}),
                            }
                        )
                elif block.name == "undo_last":
                    from apolo.state import STATE_LOCK

                    try:
                        with STATE_LOCK:
                            doc.undo()
                        content = "Deshecho."
                    except Exception as exc:
                        content = f"No se pudo deshacer: {exc}"
                    yield _sse({"type": "tool", "name": "undo_last"})
                    tool_results.append(
                        {"type": "tool_result", "tool_use_id": block.id, "content": content}
                    )
                elif block.name == "save_note":
                    save_agent_note(doc, (block.input or {}).get("text", ""))
                    yield _sse({"type": "tool", "name": "save_note"})
                    tool_results.append(
                        {"type": "tool_result", "tool_use_id": block.id, "content": "Nota guardada."}
                    )
                elif block.name in ("test_script", "check_interference", "engineering_check", "render_view"):
                    yield _sse({"type": "tool", "name": block.name})
                    try:
                        content = run_validation_tool(doc, block.name, block.input or {})
                    except Exception as exc:  # la tool nunca debe tumbar el stream
                        content = json.dumps({"error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False)
                    tool_results.append(
                        {"type": "tool_result", "tool_use_id": block.id, "content": content}
                    )
                elif block.name == "propose_commands":
                    actions = (block.input or {}).get("actions", [])
                    errors = validate_actions(actions, doc.variables_raw)
                    if errors:
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": "Parámetros inválidos, corrige y vuelve a proponer:\n"
                                + "\n".join(errors),
                                "is_error": True,
                            }
                        )
                    else:
                        yield _sse({"type": "actions", "actions": actions})
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": "Propuesta mostrada al usuario; queda pendiente de su aceptación.",
                            }
                        )
                        proposed = True
            convo.append({"role": "user", "content": tool_results})
            if proposed:
                break
    except anthropic.APIError as exc:
        yield _sse({"type": "error", "message": f"Error del API de Claude: {exc.message}"})

    yield _sse({"type": "done"})
