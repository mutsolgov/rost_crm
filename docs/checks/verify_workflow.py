"""Validate the proposed workflow data; does not execute CRM logic or mutate files."""

import json
import re
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "planning"
PATH = ROOT / "04-base-workflow.json"
WORKING = [
    "contact_search", "needs_clarification", "meeting", "document_exchange",
    "document_revision", "document_signing", "materials_transfer", "deployment",
    "teacher_training", "curriculum_update", "classes", "materials_update",
    "teacher_upskilling",
]
TERMINAL = {"completed", "cancelled"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique_codes(items, label):
    codes = [item["code"] for item in items]
    require(len(codes) == len(set(codes)), f"Duplicate {label} code")
    require(all(re.fullmatch(r"[a-z][a-z0-9_]*", code) for code in codes),
            f"Invalid stable {label} code")
    return set(codes)


def reachable(graph, start):
    seen = set()
    pending = [start]
    while pending:
        node = pending.pop()
        if node not in seen:
            seen.add(node)
            pending.extend(graph[node] - seen)
    return seen


def main():
    data = json.loads(PATH.read_text(encoding="utf-8-sig"))
    expected_metadata = {
        "schema_version": "1.0",
        "template_code": "rtk_university_cooperation",
        "version": 1,
        "approval_status": "proposal",
        "initial_state": "contact_search",
    }
    for field, expected in expected_metadata.items():
        require(data.get(field) == expected, f"Unexpected {field}")

    states = data["states"]
    state_codes = unique_codes(states, "state")
    require(state_codes == set(WORKING) | TERMINAL, "Unexpected state set")
    require(len(states) == 15, "Expected 15 states")
    for state in states:
        code = state["code"]
        require(state["kind"] == ("terminal" if code in TERMINAL else "working"),
                f"Wrong kind for {code}")
        if code in WORKING:
            require(state["source_step"] == WORKING.index(code) + 1,
                    f"Wrong source step for {code}")
        else:
            require("source_step" not in state, "Terminal is not an original step")

    conditions = data["condition_definitions"]
    condition_codes = unique_codes(conditions, "condition")
    require(condition_codes == {"program_and_product_identified"},
            "Unexpected conditions")
    condition = conditions[0]
    require(condition["approval_status"] == "proposal", "Condition must be proposed")
    require(condition["requirement_origin"] == "design_proposal",
            "Condition is not an explicit source requirement")
    require(condition["operator"] == "all", "Only declarative all operator allowed")
    require(condition["rules"] == [
        {"field": "interaction.program_id", "operator": "is_not_null"},
        {"field": "interaction.product_id", "operator": "is_not_null"},
    ], "Unexpected completeness rule")
    require(set(condition) == {
        "code", "description", "approval_status", "requirement_origin", "operator", "rules"
    }, "Unexpected condition field; executable expressions are not allowed")

    transitions = data["transitions"]
    transition_codes = unique_codes(transitions, "transition")
    require(not state_codes & transition_codes, "Codes must not collide")
    graph = defaultdict(set)
    reverse = defaultdict(set)
    pairs = set()
    chain = WORKING + ["completed"]
    main_pairs = set(zip(chain, chain[1:]))
    additional = {
        ("document_exchange", "document_signing"): "skip_optional",
        ("document_signing", "document_revision"): "rework",
        ("teacher_upskilling", "classes"): "cycle",
    }
    expected_pairs = main_pairs | set(additional) | {(s, "cancelled") for s in WORKING}
    for transition in transitions:
        require(set(transition) == {
            "code", "from", "to", "kind", "comment_required", "condition_refs"
        }, "Unexpected transition field")
        source, target = transition["from"], transition["to"]
        require(source in state_codes and target in state_codes,
                f"Dangling transition {transition['code']}")
        require(source not in TERMINAL, f"Terminal {source} has outgoing transition")
        pair = (source, target)
        require(pair not in pairs, f"Duplicate transition pair {pair}")
        pairs.add(pair)
        graph[source].add(target)
        reverse[target].add(source)
        expected_kind = ("cancellation" if target == "cancelled" else
                         additional.get(pair, "forward"))
        require(transition["kind"] == expected_kind, f"Wrong transition kind {pair}")
        require(transition["comment_required"] is
                (expected_kind in {"rework", "cycle", "cancellation"}),
                f"Wrong comment policy for {pair}")
        refs = transition["condition_refs"]
        require(set(refs) <= condition_codes, f"Dangling condition reference {pair}")
        require(refs == (["program_and_product_identified"]
                         if target == "materials_transfer" else []),
                f"Wrong transition conditions {pair}")
    require(pairs == expected_pairs, "Unexpected transition set")
    require(len(transitions) == 29, "Expected 29 transitions")
    initial = data["initial_state"]
    require(isinstance(initial, str) and initial in state_codes, "One initial required")
    require(not reverse[initial], "Initial state has unexpected incoming transitions")
    require(reachable(graph, initial) == state_codes, "Unreachable states")
    can_complete = reachable(reverse, "completed")
    can_cancel = reachable(reverse, "cancelled")
    require(set(WORKING) <= can_complete, "Working state cannot reach successful completion")
    require(set(WORKING) <= can_cancel, "Working state cannot reach cancellation")

    controls = data["cross_cutting_controls"]
    unique_codes(controls, "control")
    require(len(controls) == 1 and controls[0]["source_step"] == 14,
            "Source step 14 must be one cross-cutting control")
    require(controls[0]["applies_to"] == "all_working_states", "Control scope mismatch")
    require(controls[0]["approval_status"] == "proposal", "Control must be proposed")
    print("PASS: 13 working states, 2 terminal states, 29 transitions, 1 initial state.")
    print("PASS: unique codes, references, source mapping, required branches and policies.")
    print("PASS: every state is reachable; every working state can complete or cancel.")
    print("PASS: terminal states have no exits; conditions are declarative proposals.")


if __name__ == "__main__":
    main()
