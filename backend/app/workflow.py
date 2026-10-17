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


class TransitionDict(dict):
    """Dictionary of transitions keyed by code, but iterating yields transition objects directly."""

    def __iter__(self):
        return iter(self.values())


def _sync_globals() -> None:
    """Synchronize global STATES, TRANSITIONS, and TERMINAL_STATES from WORKFLOW_REGISTRY in-place."""
    new_states = {
        state["code"]: state
        for wf in WORKFLOW_REGISTRY.values()
        if isinstance(wf, dict) and "states" in wf
        for state in wf["states"]
    }
    new_transitions = {
        edge["code"]: edge
        for wf in WORKFLOW_REGISTRY.values()
        if isinstance(wf, dict) and "transitions" in wf
        for edge in wf["transitions"]
    }
    new_terminals = {
        key for key, state in new_states.items()
        if state.get("kind") == "terminal"
    }

    # In-place mutation ensures modules importing by reference stay updated
    STATES.clear()
    STATES.update(new_states)

    TRANSITIONS.clear()
    TRANSITIONS.update(new_transitions)

    TERMINAL_STATES.clear()
    TERMINAL_STATES.update(new_terminals)


# Backwards compatibility exports
WORKFLOW = WORKFLOW_V1
STATES: dict[str, dict] = {}
TRANSITIONS: dict[str, dict] = {}
TERMINAL_STATES: set[str] = set()
SUBJECT_REQUIRED_STATES = {
    "materials_transfer", "deployment", "teacher_training", "curriculum_update", "classes",
    "materials_update", "teacher_upskilling", "completed",
}
_sync_globals()


def load_workflow_versions(db=None) -> None:
    """Load all published workflow versions from DB into WORKFLOW_REGISTRY and sync globals."""
    def _do_load(session):
        from sqlalchemy import select
        from .models import WorkflowVersion
        published_versions = list(session.scalars(
            select(WorkflowVersion).where(WorkflowVersion.is_published.is_(True))
        ))
        for pv in published_versions:
            if pv.definition and isinstance(pv.definition, dict):
                WORKFLOW_REGISTRY[pv.version] = pv.definition
        _sync_globals()

    if db is not None:
        try:
            _do_load(db)
        except Exception:
            pass
    else:
        try:
            from sqlalchemy.orm import Session
            from .db import get_engine
            with Session(get_engine()) as session:
                _do_load(session)
        except Exception:
            pass


def get_workflow(version: int = 1, db=None) -> dict:
    """Retrieve workflow by version. If not in memory, dynamically load from DB."""
    if version not in WORKFLOW_REGISTRY:
        if db is not None:
            load_workflow_versions(db)
            if version not in WORKFLOW_REGISTRY:
                try:
                    from sqlalchemy import select
                    from .models import WorkflowVersion
                    wv = db.scalar(select(WorkflowVersion).where(WorkflowVersion.version == version))
                    if wv and wv.definition and isinstance(wv.definition, dict):
                        WORKFLOW_REGISTRY[wv.version] = wv.definition
                        _sync_globals()
                except Exception:
                    pass
        else:
            try:
                from sqlalchemy.orm import Session
                from .db import get_engine
                from sqlalchemy import select
                from .models import WorkflowVersion
                with Session(get_engine()) as session:
                    load_workflow_versions(session)
                    if version not in WORKFLOW_REGISTRY:
                        wv = session.scalar(select(WorkflowVersion).where(WorkflowVersion.version == version))
                        if wv and wv.definition and isinstance(wv.definition, dict):
                            WORKFLOW_REGISTRY[wv.version] = wv.definition
                            _sync_globals()
            except Exception:
                pass

    if version not in WORKFLOW_REGISTRY:
        raise KeyError(f"Unknown workflow version: {version}")

    wf = WORKFLOW_REGISTRY[version]
    if "terminal_states" not in wf:
        wf["terminal_states"] = [
            s["code"] for s in wf.get("states", [])
            if s.get("kind") == "terminal"
        ]
    return wf


def get_states(version: int = 1, db=None) -> dict[str, dict]:
    wf = get_workflow(version, db=db)
    return {state["code"]: state for state in wf.get("states", [])}


def get_transitions(version: int = 1, db=None) -> TransitionDict:
    wf = get_workflow(version, db=db)
    return TransitionDict({edge["code"]: edge for edge in wf.get("transitions", [])})


def allowed_transitions(state: str, version: int = 1, db=None) -> list[dict]:
    transitions = get_transitions(version, db=db)
    states = get_states(version, db=db)
    return [
        {
            "code": edge["code"],
            "to": edge["to"],
            "name": states[edge["to"]]["name"] if edge["to"] in states else edge.get("name", edge["to"]),
            "kind": edge.get("kind", "forward"),
            "comment_required": edge.get("comment_required", False),
            "condition_refs": edge.get("condition_refs", []),
        }
        for edge in transitions.values()
        if edge.get("from") == state
    ]

