import json
from pathlib import Path


WORKFLOW = json.loads((Path(__file__).parent / "data" / "base-workflow.json").read_text(encoding="utf-8"))
STATES = {state["code"]: state for state in WORKFLOW["states"]}
TRANSITIONS = {edge["code"]: edge for edge in WORKFLOW["transitions"]}
TERMINAL_STATES = {key for key, state in STATES.items() if state["kind"] == "terminal"}
SUBJECT_REQUIRED_STATES = {
    "materials_transfer", "deployment", "teacher_training", "curriculum_update", "classes",
    "materials_update", "teacher_upskilling", "completed",
}


def allowed_transitions(state):
    return [{"code": edge["code"], "to": edge["to"], "name": STATES[edge["to"]]["name"],
             "comment_required": edge["comment_required"], "condition_refs": edge["condition_refs"]}
            for edge in TRANSITIONS.values() if edge["from"] == state]
