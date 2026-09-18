"""Independent acceptance oracle for the hand-authored synthetic report fixture.

This verifies the fixture, not the CRM implementation.
No application implementation or fixture-generation functions are imported.
"""
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "planning"
FIXTURE = ROOT / "05-report-fixture.json"

def instant(value):
    assert value.endswith("Z"), f"UTC suffix required: {value}"
    return datetime.fromisoformat(value.replace("Z", "+00:00"))

data = json.loads(FIXTURE.read_text(encoding="utf-8"))
assert data["synthetic_data"] is True
events = data["events"]
by_id = {e["event_id"]: e for e in events}
assert len(by_id) == len(events), "Duplicate canonical event_id"
interactions = {r["interaction_id"]: r for r in data["interactions"]}
scopes = {u["user_id"]: set(u["accessible_interaction_ids"]) for u in data["scope_now"]["users"]}
stage_codes = data["stage_codes"]
latest_allowed = instant("2026-09-15T12:00:00Z")
earliest_allowed = instant("2026-08-01T00:00:00Z")

for event in events:
    assert event["interaction_id"] in interactions
    assert earliest_allowed <= instant(event["effective_at"]) <= latest_allowed
    assert instant(event["effective_at"]) <= instant(event["received_at"]) <= latest_allowed

def key(event):
    return (instant(event["effective_at"]), event["sequence"])

# Validate complete canonical histories without using any expected report values.
for interaction_id in interactions:
    history = sorted((e for e in events if e["interaction_id"] == interaction_id), key=key)
    assert len({e["sequence"] for e in history}) == len(history)
    assert sum(e["type"] == "initial_state" for e in history) == 1
    state = None
    owner = None
    for event in history:
        if event["type"] == "initial_state":
            assert state is None
            state = event["state"]
        elif event["type"] == "assignment":
            owner = event["owner_id"]
        elif event["type"] == "transition":
            assert owner is not None, f"Missing historical owner: {event['event_id']}"
            assert state == event["from_state"], f"Broken canonical chain: {event['event_id']}"
            state = event["to_state"]
        else:
            raise AssertionError(f"Unknown event type: {event['type']}")
        assert state in stage_codes

deliveries = data["event_deliveries"]
for delivery in deliveries:
    assert delivery["event_id"] in by_id
    assert instant(by_id[delivery["event_id"]]["received_at"]) <= instant(delivery["delivered_at"]) <= latest_allowed
assert Counter(d["event_id"] for d in deliveries)["I2-T1"] == 2

def nonempty_counts(values):
    return dict(sorted(Counter(values).items()))

def stage_counts(values):
    count = Counter(values)
    return {stage: count[stage] for stage in stage_codes}

def known_history(interaction_id, as_of, cutoff):
    return sorted(
        (event for event in events
         if event["interaction_id"] == interaction_id
         and instant(event["effective_at"]) <= as_of
         and instant(event["received_at"]) <= cutoff),
        key=key,
    )

def compute_snapshot(query):
    rows = []
    as_of, cutoff = instant(query["as_of"]), instant(query["knowledge_cutoff"])
    for interaction_id in sorted(scopes[query["user_id"]]):
        state, owner = None, None
        for event in known_history(interaction_id, as_of, cutoff):
            if event["type"] == "initial_state":
                state = event["state"]
            elif event["type"] == "transition":
                state = event["to_state"]
            elif event["type"] == "assignment":
                owner = event["owner_id"]
        if state is None:
            continue
        if "historical_owner_id" in query and owner != query["historical_owner_id"]:
            continue
        rows.append({"interaction_id": interaction_id, "state": state, "historical_owner_id": owner})
    return {
        "interaction_ids": [row["interaction_id"] for row in rows],
        "rows": rows,
        "total_interactions": len(rows),
        "counts_by_state": stage_counts(row["state"] for row in rows),
        "counts_by_historical_owner": nonempty_counts(row["historical_owner_id"] for row in rows),
    }

def owner_at_event(transition, cutoff):
    assignments = [
        event for event in events
        if event["interaction_id"] == transition["interaction_id"]
        and event["type"] == "assignment"
        and key(event) <= key(transition)
        and instant(event["received_at"]) <= cutoff
    ]
    assert assignments, f"Missing known owner for {transition['event_id']}"
    return max(assignments, key=key)["owner_id"]

def compute_activity(query):
    start, end = instant(query["from"]), instant(query["to"])
    cutoff = instant(query["knowledge_cutoff"])
    selected = []
    for event in events:
        if event["type"] != "transition":
            continue
        if event["interaction_id"] not in scopes[query["user_id"]]:
            continue
        if not (start <= instant(event["effective_at"]) < end):
            continue
        if instant(event["received_at"]) > cutoff:
            continue
        owner = owner_at_event(event, cutoff)
        if "historical_owner_id" in query and owner != query["historical_owner_id"]:
            continue
        selected.append((event, owner))
    selected.sort(key=lambda pair: pair[0]["event_id"])
    interaction_ids = sorted({event["interaction_id"] for event, _ in selected})
    return {
        "event_ids": [event["event_id"] for event, _ in selected],
        "interaction_ids": interaction_ids,
        "total_transitions": len(selected),
        "total_interactions": len(interaction_ids),
        "counts_by_interaction": nonempty_counts(event["interaction_id"] for event, _ in selected),
        "counts_by_to_state": stage_counts(event["to_state"] for event, _ in selected),
        "counts_by_historical_owner": nonempty_counts(owner for _, owner in selected),
    }

seen_cases = set()
for case in data["expected_results"]:
    assert case["case_id"] not in seen_cases
    seen_cases.add(case["case_id"])
    query = case["query"]
    assert query["scope_at"] == "scope_now"
    actual = compute_snapshot(query) if case["report_type"] == "snapshot" else compute_activity(query)
    assert actual == case["expected"], json.dumps(
        {"case_id": case["case_id"], "expected": case["expected"], "actual": actual},
        ensure_ascii=False, indent=2,
    )
    print(f"PASS {case['case_id']} ({case['report_type']})")

# Cross-case checks catch a mistaken expectation shared by only one report.
expected = {case["case_id"]: case["expected"] for case in data["expected_results"]}
assert expected["FX-S01"]["interaction_ids"] == expected["FX-S02"]["interaction_ids"]
assert expected["FX-S01"]["counts_by_state"]["document_signing"] == 1
assert expected["FX-S02"]["counts_by_state"]["document_signing"] == 0
assert "I1" in expected["FX-S04"]["interaction_ids"]
assert "I1" not in expected["FX-S05"]["interaction_ids"]
assert expected["FX-S06"]["interaction_ids"] == ["I1"]
assert expected["FX-A01"]["event_ids"].count("I2-T1") == 1
assert "I1-T1" not in expected["FX-A01"]["event_ids"]
assert "I1-T2" in expected["FX-A01"]["event_ids"]
assert "I1-T3" not in expected["FX-A01"]["event_ids"]
assert "I1-T3" in expected["FX-A04"]["event_ids"]
assert all("I4" not in case["expected"]["interaction_ids"] for case in data["expected_results"])
print(f"VERIFIED {len(interactions)} interactions, {len(events)} canonical events, "
      f"{len(deliveries)} delivery examples, {len(seen_cases)} exact report cases")

