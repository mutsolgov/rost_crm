import json
from pathlib import Path


WORKFLOW_V1 = json.loads((Path(__file__).parent / "data" / "base-workflow.json").read_text(encoding="utf-8"))

V2_OPTIMIZED_TRANSITIONS = [
    {
        "code": "meeting_to_document_signing",
        "from": "meeting",
        "to": "document_signing",
        "kind": "forward",
        "comment_required": False,
        "condition_refs": [],
    },
    {
        "code": "materials_transfer_to_classes",
        "from": "materials_transfer",
        "to": "classes",
        "kind": "forward",
        "comment_required": False,
        "condition_refs": [],
    },
    {
        "code": "classes_to_completed",
        "from": "classes",
        "to": "completed",
        "kind": "forward",
        "comment_required": False,
        "condition_refs": [],
    },
    {
        "code": "deployment_to_materials_transfer",
        "from": "deployment",
        "to": "materials_transfer",
        "kind": "rework",
        "comment_required": True,
        "condition_refs": [],
    },
    {
        "code": "classes_to_teacher_training",
        "from": "classes",
        "to": "teacher_training",
        "kind": "rework",
        "comment_required": True,
        "condition_refs": [],
    },
    {
        "code": "document_signing_to_meeting",
        "from": "document_signing",
        "to": "meeting",
        "kind": "rework",
        "comment_required": True,
        "condition_refs": [],
    },
    {
        "code": "document_revision_to_meeting",
        "from": "document_revision",
        "to": "meeting",
        "kind": "rework",
        "comment_required": True,
        "condition_refs": [],
    },
]

WORKFLOW_V2 = {
    **WORKFLOW_V1,
    "version": 2,
    "name": "Взаимодействие с вузом по ИТ-программе и ИТ-продукту (Оптимизированный процесс v2)",
    "description": "Расширенный шаблон процесса сотрудничества с ускоренными переходами и циклами доработки.",
    "transitions": list(WORKFLOW_V1["transitions"]) + V2_OPTIMIZED_TRANSITIONS,
}

WORKFLOW_REGISTRY = {
    1: WORKFLOW_V1,
    2: WORKFLOW_V2,
}


def get_workflow(version: int = 1) -> dict:
    if version not in WORKFLOW_REGISTRY:
        raise KeyError(f"Unknown workflow version: {version}")
    return WORKFLOW_REGISTRY[version]


def get_states(version: int = 1) -> dict[str, dict]:
    wf = get_workflow(version)
    return {state["code"]: state for state in wf["states"]}


def get_transitions(version: int = 1) -> dict[str, dict]:
    wf = get_workflow(version)
    return {edge["code"]: edge for edge in wf["transitions"]}


def allowed_transitions(state: str, version: int = 1) -> list[dict]:
    transitions = get_transitions(version)
    states = get_states(version)
    return [
        {
            "code": edge["code"],
            "to": edge["to"],
            "name": states[edge["to"]]["name"],
            "kind": edge.get("kind", "forward"),
            "comment_required": edge["comment_required"],
            "condition_refs": edge["condition_refs"],
        }
        for edge in transitions.values()
        if edge["from"] == state
    ]


# Backwards compatibility exports
WORKFLOW = WORKFLOW_V1
STATES = {state["code"]: state for wf in WORKFLOW_REGISTRY.values() for state in wf["states"]}
TRANSITIONS = {edge["code"]: edge for wf in WORKFLOW_REGISTRY.values() for edge in wf["transitions"]}
TERMINAL_STATES = {key for key, state in STATES.items() if state["kind"] == "terminal"}
SUBJECT_REQUIRED_STATES = {
    "materials_transfer", "deployment", "teacher_training", "curriculum_update", "classes",
    "materials_update", "teacher_upskilling", "completed",
}


def load_workflow_versions(db) -> None:
    try:
        from sqlalchemy import select
        from .models import WorkflowVersion
        published_versions = list(db.scalars(
            select(WorkflowVersion).where(WorkflowVersion.is_published.is_(True))
        ))
        for pv in published_versions:
            if pv.definition and isinstance(pv.definition, dict):
                WORKFLOW_REGISTRY[pv.version] = pv.definition
    except Exception:
        pass
