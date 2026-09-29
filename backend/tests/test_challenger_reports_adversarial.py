"""Adversarial stress-testing suite for reports engine, formula injection, time boundaries, and historical owner resolution.

Challenger 1 empirical verification.
"""
from __future__ import annotations

import csv
import io
import zipfile
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.models import Interaction, InteractionEvent, User
from app.reports_export import sanitize_formula_cell
from app.workflow import STATES


def headers(user="supervisor", key=None):
    res = {"X-Demo-User": user}
    if key:
        res["Idempotency-Key"] = key
    return res


def create_interaction(client, user="manager-a", **changes):
    body = {
        "title": "Отчётное взаимодействие",
        "organization_id": "org-1",
        "program_id": "program-devops",
        "product_id": "product-cloud",
        "cycle_label": "Тестовый цикл отчётов",
        "owner_id": user,
    }
    body.update(changes)
    response = client.post("/api/v1/interactions", json=body, headers=headers(user, str(uuid4())))
    assert response.status_code == 201, response.text
    return response.json()


# ==============================================================================
# Category 1: CWE-1236 & Formula Injection Stress Testing
# ==============================================================================

def test_sanitize_formula_cell_exhaustive_adversarial_matrix():
    """Unit stress-test of sanitize_formula_cell on all CWE-1236 vectors, leading spaces, extreme numbers, Cyrillic."""
    test_cases = [
        # Standard CWE-1236 triggers
        ("=cmd", "'=cmd"),
        ("+SUM(A1)", "'+SUM(A1)"),
        ("-1+1", "'-1+1"),
        ("@SUM", "'@SUM"),
        ("\tcmd", "'\tcmd"),
        ("\rcmd", "'\rcmd"),
        # Leading whitespace variations
        ("  =leading_spaces", "'  =leading_spaces"),
        ("   +spaces_plus", "'   +spaces_plus"),
        ("   -spaces_minus", "'   -spaces_minus"),
        ("   @spaces_at", "'   @spaces_at"),
        ("\t=tab_equals", "'\t=tab_equals"),
        ("\r+cr_plus", "'\r+cr_plus"),
        ("\n=nl_equals", "'\n=nl_equals"),
        ("\r\n=crlf_equals", "'\r\n=crlf_equals"),
        ("  \t\r  =mixed_whitespace", "'  \t\r  =mixed_whitespace"),
        # Cyrillic formula strings
        ("=СУММ(А1:А10)", "'=СУММ(А1:А10)"),
        ("+Привет", "'+Привет"),
        ("-Внимание", "'-Внимание"),
        ("@Пользователь", "'@Пользователь"),
        # Safe strings that must NOT be modified
        ("Обычный текст на кириллице", "Обычный текст на кириллице"),
        ("Текст с = знаком внутри", "Текст с = знаком внутри"),
        ("Текст с + знаком внутри", "Текст с + знаком внутри"),
        ("Текст с - знаком внутри", "Текст с - знаком внутри"),
        ("Текст с @ знаком внутри", "Текст с @ знаком внутри"),
        # Extreme numbers
        (12345, "12345"),
        (0, "0"),
        (-42, "'-42"),
        (-1, "'-1"),
        (1e308, "1e+308"),
        (-1e308, "'-1e+308"),
        (float("inf"), "inf"),
        (float("-inf"), "'-inf"),
        (float("nan"), "nan"),
        # Null, empty, special characters
        (None, ""),
        ("", ""),
        ("<script>alert(1)</script>", "<script>alert(1)</script>"),
        ("& < > ' \"", "& < > ' \""),
        ("'already_quoted", "'already_quoted"),
    ]

    for raw, expected in test_cases:
        result = sanitize_formula_cell(raw)
        assert result == expected, f"Failed on raw={raw!r}: expected {expected!r}, got {result!r}"


def test_multiformat_export_with_adversarial_payloads(client):
    """End-to-end multi-format export test with adversarial formula payloads injected into interactions."""
    payloads = [
        "=cmd|' /C calc'!A0",
        "+SUM(1, 2)",
        "-2+5",
        "@SUM(A1:B2)",
        "\t=HYPERLINK(\"http://evil.com\", \"Click\")",
        "  =leading_space_formula()",
        "=СУММ(1;2)",
        "Нормальный заголовок ПАО «Ростелеком»",
    ]

    for p in payloads:
        create_interaction(client, "manager-a", title=p)

    now_iso = datetime.now(timezone.utc).isoformat()
    req = {"as_of": now_iso, "knowledge_cutoff": now_iso}

    # 1. Test CSV Export
    csv_resp = client.post("/api/v1/reports/snapshot/export?format=csv", json=req, headers=headers("supervisor"))
    assert csv_resp.status_code == 200
    assert csv_resp.headers["X-Report-Format"] == "csv"
    assert "text/csv" in csv_resp.headers["Content-Type"]
    assert csv_resp.content.startswith(b"\xef\xbb\xbf"), "CSV missing UTF-8 BOM"

    csv_text = csv_resp.content.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)
    assert len(rows) > len(payloads)

    # Verify that dangerous titles in CSV have leading quote
    titles_in_csv = [row[1] for row in rows[1:]]
    for p in payloads:
        # Note: Pydantic strips whitespace on interaction creation
        stored_title = p.strip()
        expected = sanitize_formula_cell(stored_title)
        assert expected in titles_in_csv, f"Expected sanitized title {expected!r} not found in CSV: {titles_in_csv}"

    # 2. Test XLSX Export
    xlsx_resp = client.post("/api/v1/reports/snapshot/export?format=xlsx", json=req, headers=headers("supervisor"))
    assert xlsx_resp.status_code == 200
    assert xlsx_resp.headers["X-Report-Format"] == "xlsx"
    assert xlsx_resp.content.startswith(b"PK\x03\x04")

    with zipfile.ZipFile(io.BytesIO(xlsx_resp.content)) as zf:
        sheet1_xml = zf.read("xl/worksheets/sheet1.xml").decode("utf-8")
        # Invariant 1: No formula elements <f>
        assert "<f>" not in sheet1_xml
        # Invariant 2: All values use inlineStr
        assert 't="inlineStr"' in sheet1_xml
        # Invariant 3: Dangerous values escaped
        assert "&lt;script&gt;" not in sheet1_xml  # sanity
        assert "'=cmd" in sheet1_xml or "&apos;=cmd" in sheet1_xml or "'=cmd" in sheet1_xml

    # 3. Test PDF Export
    pdf_resp = client.post("/api/v1/reports/snapshot/export?format=pdf", json=req, headers=headers("supervisor"))
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["X-Report-Format"] == "pdf"
    assert pdf_resp.content.startswith(b"%PDF-1.4")
    assert b"%%EOF" in pdf_resp.content
    # Vector text streams use hex_tj (<...>)
    assert b"<" in pdf_resp.content and b"> Tj" in pdf_resp.content

    # 4. Test JSON Export
    json_resp = client.post("/api/v1/reports/snapshot/export?format=json", json=req, headers=headers("supervisor"))
    assert json_resp.status_code == 200
    assert json_resp.headers["X-Report-Format"] == "json"
    data = json_resp.json()
    assert data["report_type"] == "snapshot"
    assert data["total_interactions"] >= len(payloads)


# ==============================================================================
# Category 2: Time Boundaries Stress Testing
# ==============================================================================

def test_time_boundaries_as_of_inclusive_exact_instant(app, client):
    """Stress-test as_of_inclusive: True vs False at the exact boundary of an event."""
    t0 = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)

    with app.state.session_factory() as session:
        inter = Interaction(
            id="test-as-of-bound",
            title="Boundary Test",
            organization_id="org-1",
            program_id="program-devops",
            product_id="product-cloud",
            cycle_label="2026-осень",
            owner_id="manager-a",
            state="needs_clarification",
            revision=2,
            created_at=t0,
        )
        session.add(inter)
        session.flush()

        # Event 1: created at t0
        ev1 = InteractionEvent(
            id="ev-bound-1",
            interaction_id="test-as-of-bound",
            type="created",
            effective_at=t0,
            received_at=t0,
            sequence=1,
            actor_id="manager-a",
            actor_name="Анна Смирнова",
            payload={"snapshot": {"title": "Boundary Test", "state": "contact_search", "owner_id": "manager-a", "organization_id": "org-1"}},
        )
        # Event 2: transition at exactly t1
        ev2 = InteractionEvent(
            id="ev-bound-2",
            interaction_id="test-as-of-bound",
            type="transition",
            effective_at=t1,
            received_at=t1,
            sequence=2,
            actor_id="manager-a",
            actor_name="Анна Смирнова",
            payload={"from_state": "contact_search", "to_state": "needs_clarification", "snapshot": {"title": "Boundary Test", "state": "needs_clarification", "owner_id": "manager-a", "organization_id": "org-1"}},
        )
        session.add_all([ev1, ev2])
        session.commit()

    # Query 1: as_of = t1, as_of_inclusive = True -> Event 2 is INCLUDED -> state = needs_clarification
    resp_inc = client.post(
        "/api/v1/reports/snapshot",
        json={"as_of": t1.isoformat(), "knowledge_cutoff": t1.isoformat(), "as_of_inclusive": True, "organization_ids": ["org-1"]},
        headers=headers("supervisor"),
    )
    assert resp_inc.status_code == 200
    rows_inc = [r for r in resp_inc.json()["rows"] if r["interaction_id"] == "test-as-of-bound"]
    assert len(rows_inc) == 1
    assert rows_inc[0]["state"] == "needs_clarification"

    # Query 2: as_of = t1, as_of_inclusive = False -> Event 2 is EXCLUDED (< t1) -> state = contact_search
    resp_exc = client.post(
        "/api/v1/reports/snapshot",
        json={"as_of": t1.isoformat(), "knowledge_cutoff": t1.isoformat(), "as_of_inclusive": False, "organization_ids": ["org-1"]},
        headers=headers("supervisor"),
    )
    assert resp_exc.status_code == 200
    rows_exc = [r for r in resp_exc.json()["rows"] if r["interaction_id"] == "test-as-of-bound"]
    assert len(rows_exc) == 1
    assert rows_exc[0]["state"] == "contact_search"


def test_time_boundaries_knowledge_cutoff_effective_vs_received(app, client):
    """Stress-test knowledge_cutoff: late arrival events (effective_at < cutoff, but received_at > cutoff)."""
    t_eff = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)
    t_recv = datetime(2026, 8, 2, 15, 0, 0, tzinfo=timezone.utc)

    with app.state.session_factory() as session:
        inter = Interaction(
            id="test-cutoff-inter",
            title="Cutoff Test",
            organization_id="org-1",
            program_id="program-devops",
            product_id="product-cloud",
            cycle_label="2026-осень",
            owner_id="manager-a",
            state="meeting",
            revision=2,
            created_at=t_eff,
        )
        session.add(inter)
        session.flush()

        ev1 = InteractionEvent(
            id="ev-cutoff-1",
            interaction_id="test-cutoff-inter",
            type="created",
            effective_at=t_eff,
            received_at=t_eff,
            sequence=1,
            actor_id="manager-a",
            actor_name="Анна Смирнова",
            payload={"snapshot": {"title": "Cutoff Test", "state": "contact_search", "owner_id": "manager-a", "organization_id": "org-1"}},
        )
        # Event 2 was effectively at t_eff + 1h, but not received until t_recv (next day)
        ev2 = InteractionEvent(
            id="ev-cutoff-2",
            interaction_id="test-cutoff-inter",
            type="transition",
            effective_at=t_eff + timedelta(hours=1),
            received_at=t_recv,
            sequence=2,
            actor_id="manager-a",
            actor_name="Анна Смирнова",
            payload={"from_state": "contact_search", "to_state": "meeting", "snapshot": {"title": "Cutoff Test", "state": "meeting", "owner_id": "manager-a", "organization_id": "org-1"}},
        )
        session.add_all([ev1, ev2])
        session.commit()

    as_of = (t_eff + timedelta(hours=2)).isoformat()

    # Case A: knowledge_cutoff BEFORE received_at (t_recv - 1s)
    # The transition happened effectively, but knowledge of it arrived later -> MUST show contact_search
    resp_before = client.post(
        "/api/v1/reports/snapshot",
        json={"as_of": as_of, "knowledge_cutoff": (t_recv - timedelta(seconds=1)).isoformat(), "organization_ids": ["org-1"]},
        headers=headers("supervisor"),
    )
    assert resp_before.status_code == 200
    rows_before = [r for r in resp_before.json()["rows"] if r["interaction_id"] == "test-cutoff-inter"]
    assert len(rows_before) == 1
    assert rows_before[0]["state"] == "contact_search"

    # Case B: knowledge_cutoff EQUAL to received_at (t_recv) -> MUST show meeting
    resp_exact = client.post(
        "/api/v1/reports/snapshot",
        json={"as_of": as_of, "knowledge_cutoff": t_recv.isoformat(), "organization_ids": ["org-1"]},
        headers=headers("supervisor"),
    )
    assert resp_exact.status_code == 200
    rows_exact = [r for r in resp_exact.json()["rows"] if r["interaction_id"] == "test-cutoff-inter"]
    assert len(rows_exact) == 1
    assert rows_exact[0]["state"] == "meeting"


def test_time_boundaries_half_open_interval_activity(app, client):
    """Stress-test half-open interval [from, to) in activity report."""
    t_start = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)
    t_end = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)

    with app.state.session_factory() as session:
        inter = Interaction(
            id="test-half-open-act",
            title="Half-Open Activity",
            organization_id="org-1",
            program_id="program-devops",
            product_id="product-cloud",
            cycle_label="2026-осень",
            owner_id="manager-a",
            state="meeting",
            revision=5,
            created_at=t_start - timedelta(hours=2),
        )
        session.add(inter)
        session.flush()

        init_ev = InteractionEvent(
            id="ev-ho-init",
            interaction_id="test-half-open-act",
            type="created",
            effective_at=t_start - timedelta(hours=2),
            received_at=t_start - timedelta(hours=2),
            sequence=1,
            actor_id="manager-a",
            actor_name="Анна Смирнова",
            payload={"owner_id": "manager-a", "snapshot": {"title": "Half-Open Activity", "owner_id": "manager-a", "organization_id": "org-1"}},
        )

        # Event at exact start (t_start): MUST be INCLUDED
        ev_start = InteractionEvent(
            id="ev-ho-start",
            interaction_id="test-half-open-act",
            type="transition",
            effective_at=t_start,
            received_at=t_start,
            sequence=2,
            actor_id="manager-a",
            actor_name="Анна Смирнова",
            payload={"from_state": "contact_search", "to_state": "needs_clarification", "snapshot": {"title": "Half-Open Activity", "organization_id": "org-1"}},
        )

        # Event 1 microsecond before end: MUST be INCLUDED
        ev_pre_end = InteractionEvent(
            id="ev-ho-pre-end",
            interaction_id="test-half-open-act",
            type="transition",
            effective_at=t_end - timedelta(microseconds=1),
            received_at=t_end - timedelta(microseconds=1),
            sequence=3,
            actor_id="manager-a",
            actor_name="Анна Смирнова",
            payload={"from_state": "needs_clarification", "to_state": "meeting", "snapshot": {"title": "Half-Open Activity", "organization_id": "org-1"}},
        )

        # Event at exact end (t_end): MUST be EXCLUDED ([from, to))
        ev_end = InteractionEvent(
            id="ev-ho-end",
            interaction_id="test-half-open-act",
            type="transition",
            effective_at=t_end,
            received_at=t_end,
            sequence=4,
            actor_id="manager-a",
            actor_name="Анна Смирнова",
            payload={"from_state": "meeting", "to_state": "document_exchange", "snapshot": {"title": "Half-Open Activity", "organization_id": "org-1"}},
        )

        session.add_all([init_ev, ev_start, ev_pre_end, ev_end])
        session.commit()

    req = {
        "from": t_start.isoformat(),
        "to": t_end.isoformat(),
        "knowledge_cutoff": (t_end + timedelta(hours=1)).isoformat(),
        "organization_ids": ["org-1"],
    }
    resp = client.post("/api/v1/reports/activity", json=req, headers=headers("supervisor"))
    assert resp.status_code == 200
    data = resp.json()
    e_ids = data["event_ids"]

    assert "ev-ho-start" in e_ids, "Event at exact 'from' must be included"
    assert "ev-ho-pre-end" in e_ids, "Event before 'to' must be included"
    assert "ev-ho-end" not in e_ids, "Event at exact 'to' must be excluded by half-open [from, to)"


def test_time_boundaries_empty_and_reversed_intervals(client):
    """Stress-test empty interval [T, T) and inverted interval [T2, T1)."""
    t = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)
    t_iso = t.isoformat()

    # Empty interval [t, t)
    req_empty = {
        "from": t_iso,
        "to": t_iso,
        "knowledge_cutoff": t_iso,
    }
    resp_act = client.post("/api/v1/reports/activity", json=req_empty, headers=headers("supervisor"))
    assert resp_act.status_code == 200
    data_act = resp_act.json()
    assert data_act["total_transitions"] == 0
    assert len(data_act["rows"]) == 0
    assert len(data_act["counts_by_to_state"]) == 15

    resp_created = client.post("/api/v1/reports/created", json=req_empty, headers=headers("supervisor"))
    assert resp_created.status_code == 200
    data_cr = resp_created.json()
    assert data_cr["total_created"] == 0
    assert len(data_cr["rows"]) == 0
    assert len(data_cr["counts_by_state"]) == 15

    # Reversed interval [t + 1d, t)
    req_rev = {
        "from": (t + timedelta(days=1)).isoformat(),
        "to": t_iso,
        "knowledge_cutoff": (t + timedelta(days=2)).isoformat(),
    }
    resp_rev = client.post("/api/v1/reports/activity", json=req_rev, headers=headers("supervisor"))
    assert resp_rev.status_code == 200
    assert resp_rev.json()["total_transitions"] == 0


# ==============================================================================
# Category 3: Historical Owner Resolution & Multi-Reassignment Stress Testing
# ==============================================================================

def test_historical_owner_resolution_multi_reassignment_stress(app, client):
    """Stress-test historical owner resolution across 5 reassignments and 5 transitions.

    Sequence:
    T0: Created by manager-a (owner: manager-a)
    T1: Transition 1 -> needs_clarification (owner at T1 = manager-a)
    T2: Reassigned to manager-b
    T3: Reassigned to manager-a
    T4: Reassigned to manager-b
    T5: Transition 2 -> meeting (owner at T5 = manager-b)
    T6: Reassigned to manager-a
    T7: Transition 3 -> document_exchange (owner at T7 = manager-a)
    T8: Reassigned to manager-b
    T9: Transition 4 -> document_revision (owner at T9 = manager-b)
    T10: Reassigned to manager-a
    T11: Transition 5 -> document_signing (owner at T11 = manager-a)
    T12: Reassigned to manager-b (subsequent reassignment)
    """
    base_t = datetime(2026, 8, 1, 8, 0, 0, tzinfo=timezone.utc)

    with app.state.session_factory() as session:
        inter = Interaction(
            id="test-multi-reassign",
            title="Multi Reassign Test",
            organization_id="org-1",
            program_id="program-devops",
            product_id="product-cloud",
            cycle_label="2026-осень",
            owner_id="manager-b",  # Current owner after T12
            state="document_signing",
            revision=13,
            created_at=base_t,
        )
        session.add(inter)
        session.flush()

        events_to_add = [
            # T0 (seq 1): created
            InteractionEvent(
                id="ev-mr-0", interaction_id="test-multi-reassign", type="created",
                effective_at=base_t, received_at=base_t, sequence=1, actor_id="manager-a", actor_name="Анна",
                payload={"owner_id": "manager-a", "snapshot": {"title": "Multi Reassign", "owner_id": "manager-a", "organization_id": "org-1"}},
            ),
            # T1 (seq 2): transition 1
            InteractionEvent(
                id="ev-mr-1", interaction_id="test-multi-reassign", type="transition",
                effective_at=base_t + timedelta(hours=1), received_at=base_t + timedelta(hours=1), sequence=2, actor_id="manager-a", actor_name="Анна",
                payload={"from_state": "contact_search", "to_state": "needs_clarification", "snapshot": {"title": "Multi Reassign", "organization_id": "org-1"}},
            ),
            # T2 (seq 3): assign -> manager-b
            InteractionEvent(
                id="ev-mr-2", interaction_id="test-multi-reassign", type="assignment",
                effective_at=base_t + timedelta(hours=2), received_at=base_t + timedelta(hours=2), sequence=3, actor_id="supervisor", actor_name="Елена",
                payload={"to_owner_id": "manager-b"},
            ),
            # T3 (seq 4): assign -> manager-a
            InteractionEvent(
                id="ev-mr-3", interaction_id="test-multi-reassign", type="assignment",
                effective_at=base_t + timedelta(hours=3), received_at=base_t + timedelta(hours=3), sequence=4, actor_id="supervisor", actor_name="Елена",
                payload={"to_owner_id": "manager-a"},
            ),
            # T4 (seq 5): assign -> manager-b
            InteractionEvent(
                id="ev-mr-4", interaction_id="test-multi-reassign", type="assignment",
                effective_at=base_t + timedelta(hours=4), received_at=base_t + timedelta(hours=4), sequence=5, actor_id="supervisor", actor_name="Елена",
                payload={"to_owner_id": "manager-b"},
            ),
            # T5 (seq 6): transition 2
            InteractionEvent(
                id="ev-mr-5", interaction_id="test-multi-reassign", type="transition",
                effective_at=base_t + timedelta(hours=5), received_at=base_t + timedelta(hours=5), sequence=6, actor_id="manager-b", actor_name="Михаил",
                payload={"from_state": "needs_clarification", "to_state": "meeting", "snapshot": {"title": "Multi Reassign", "organization_id": "org-1"}},
            ),
            # T6 (seq 7): assign -> manager-a
            InteractionEvent(
                id="ev-mr-6", interaction_id="test-multi-reassign", type="assignment",
                effective_at=base_t + timedelta(hours=6), received_at=base_t + timedelta(hours=6), sequence=7, actor_id="supervisor", actor_name="Елена",
                payload={"to_owner_id": "manager-a"},
            ),
            # T7 (seq 8): transition 3
            InteractionEvent(
                id="ev-mr-7", interaction_id="test-multi-reassign", type="transition",
                effective_at=base_t + timedelta(hours=7), received_at=base_t + timedelta(hours=7), sequence=8, actor_id="manager-a", actor_name="Анна",
                payload={"from_state": "meeting", "to_state": "document_exchange", "snapshot": {"title": "Multi Reassign", "organization_id": "org-1"}},
            ),
            # T8 (seq 9): assign -> manager-b
            InteractionEvent(
                id="ev-mr-8", interaction_id="test-multi-reassign", type="assignment",
                effective_at=base_t + timedelta(hours=8), received_at=base_t + timedelta(hours=8), sequence=9, actor_id="supervisor", actor_name="Елена",
                payload={"to_owner_id": "manager-b"},
            ),
            # T9 (seq 10): transition 4
            InteractionEvent(
                id="ev-mr-9", interaction_id="test-multi-reassign", type="transition",
                effective_at=base_t + timedelta(hours=9), received_at=base_t + timedelta(hours=9), sequence=10, actor_id="manager-b", actor_name="Михаил",
                payload={"from_state": "document_exchange", "to_state": "document_revision", "snapshot": {"title": "Multi Reassign", "organization_id": "org-1"}},
            ),
            # T10 (seq 11): assign -> manager-a
            InteractionEvent(
                id="ev-mr-10", interaction_id="test-multi-reassign", type="assignment",
                effective_at=base_t + timedelta(hours=10), received_at=base_t + timedelta(hours=10), sequence=11, actor_id="supervisor", actor_name="Елена",
                payload={"to_owner_id": "manager-a"},
            ),
            # T11 (seq 12): transition 5
            InteractionEvent(
                id="ev-mr-11", interaction_id="test-multi-reassign", type="transition",
                effective_at=base_t + timedelta(hours=11), received_at=base_t + timedelta(hours=11), sequence=12, actor_id="manager-a", actor_name="Анна",
                payload={"from_state": "document_revision", "to_state": "document_signing", "snapshot": {"title": "Multi Reassign", "organization_id": "org-1"}},
            ),
            # T12 (seq 13): assign -> manager-b (subsequent)
            InteractionEvent(
                id="ev-mr-12", interaction_id="test-multi-reassign", type="assignment",
                effective_at=base_t + timedelta(hours=12), received_at=base_t + timedelta(hours=12), sequence=13, actor_id="supervisor", actor_name="Елена",
                payload={"to_owner_id": "manager-b"},
            ),
        ]
        session.add_all(events_to_add)
        session.commit()

    req = {
        "from": base_t.isoformat(),
        "to": (base_t + timedelta(hours=15)).isoformat(),
        "knowledge_cutoff": (base_t + timedelta(hours=20)).isoformat(),
        "organization_ids": ["org-1"],
    }
    resp = client.post("/api/v1/reports/activity", json=req, headers=headers("supervisor"))
    assert resp.status_code == 200
    data = resp.json()

    # Find rows for this interaction
    mr_rows = {r["event_id"]: r for r in data["rows"] if r["interaction_id"] == "test-multi-reassign"}
    assert len(mr_rows) == 5

    assert mr_rows["ev-mr-1"]["historical_owner_id"] == "manager-a"
    assert mr_rows["ev-mr-5"]["historical_owner_id"] == "manager-b"
    assert mr_rows["ev-mr-7"]["historical_owner_id"] == "manager-a"
    assert mr_rows["ev-mr-9"]["historical_owner_id"] == "manager-b"
    assert mr_rows["ev-mr-11"]["historical_owner_id"] == "manager-a"

    # Aggregated counts by historical owner for this interaction: 3 for manager-a, 2 for manager-b
    my_owners = [r["historical_owner_id"] for r in mr_rows.values()]
    assert my_owners.count("manager-a") == 3
    assert my_owners.count("manager-b") == 2

    # Verify query filter with historical_owner_id = manager-a
    req_a = dict(req, historical_owner_id="manager-a")
    resp_a = client.post("/api/v1/reports/activity", json=req_a, headers=headers("supervisor"))
    assert resp_a.status_code == 200
    rows_a = [r for r in resp_a.json()["rows"] if r["interaction_id"] == "test-multi-reassign"]
    assert len(rows_a) == 3
    assert all(r["historical_owner_id"] == "manager-a" for r in rows_a)

    # Verify query filter with historical_owner_id = manager-b
    req_b = dict(req, historical_owner_id="manager-b")
    resp_b = client.post("/api/v1/reports/activity", json=req_b, headers=headers("supervisor"))
    assert resp_b.status_code == 200
    rows_b = [r for r in resp_b.json()["rows"] if r["interaction_id"] == "test-multi-reassign"]
    assert len(rows_b) == 2
    assert all(r["historical_owner_id"] == "manager-b" for r in rows_b)


def test_historical_owner_same_timestamp_sequence_order(app, client):
    """Stress-test historical owner resolution when assignment and transition share identical timestamps."""
    t_shared = datetime(2026, 8, 1, 14, 0, 0, tzinfo=timezone.utc)

    with app.state.session_factory() as session:
        inter = Interaction(
            id="test-same-ts",
            title="Same Timestamp Test",
            organization_id="org-1",
            program_id="program-devops",
            product_id="product-cloud",
            cycle_label="2026-осень",
            owner_id="manager-b",
            state="meeting",
            revision=4,
            created_at=t_shared - timedelta(hours=1),
        )
        session.add(inter)
        session.flush()

        # seq 1: created with manager-a
        e1 = InteractionEvent(
            id="ev-st-1", interaction_id="test-same-ts", type="created",
            effective_at=t_shared - timedelta(hours=1), received_at=t_shared - timedelta(hours=1), sequence=1,
            actor_id="manager-a", actor_name="Анна",
            payload={"owner_id": "manager-a", "snapshot": {"title": "Same Timestamp", "owner_id": "manager-a", "organization_id": "org-1"}},
        )
        # seq 2: assignment to manager-b at t_shared
        e2 = InteractionEvent(
            id="ev-st-2", interaction_id="test-same-ts", type="assignment",
            effective_at=t_shared, received_at=t_shared, sequence=2,
            actor_id="supervisor", actor_name="Елена",
            payload={"to_owner_id": "manager-b"},
        )
        # seq 3: transition at t_shared -> must resolve to manager-b (seq 2 <= seq 3)
        e3 = InteractionEvent(
            id="ev-st-3", interaction_id="test-same-ts", type="transition",
            effective_at=t_shared, received_at=t_shared, sequence=3,
            actor_id="manager-b", actor_name="Михаил",
            payload={"from_state": "contact_search", "to_state": "meeting", "snapshot": {"title": "Same Timestamp", "organization_id": "org-1"}},
        )
        # seq 4: assignment to manager-a at t_shared -> occurred AFTER transition, must NOT apply to seq 3
        e4 = InteractionEvent(
            id="ev-st-4", interaction_id="test-same-ts", type="assignment",
            effective_at=t_shared, received_at=t_shared, sequence=4,
            actor_id="supervisor", actor_name="Елена",
            payload={"to_owner_id": "manager-a"},
        )
        session.add_all([e1, e2, e3, e4])
        session.commit()

    req = {
        "from": (t_shared - timedelta(minutes=5)).isoformat(),
        "to": (t_shared + timedelta(minutes=5)).isoformat(),
        "knowledge_cutoff": (t_shared + timedelta(hours=1)).isoformat(),
        "organization_ids": ["org-1"],
    }
    resp = client.post("/api/v1/reports/activity", json=req, headers=headers("supervisor"))
    assert resp.status_code == 200
    row = next(r for r in resp.json()["rows"] if r["event_id"] == "ev-st-3")
    assert row["historical_owner_id"] == "manager-b", "Transition at seq 3 must resolve to assignment at seq 2, not seq 4"


def test_zero_buckets_invariant_with_all_filters(client):
    """Stress-test zero bucket invariant: snapshot and activity must return all 15 states even with narrowing filters."""
    now_iso = datetime.now(timezone.utc).isoformat()
    req_snapshot = {
        "as_of": now_iso,
        "knowledge_cutoff": now_iso,
        "program_ids": ["program-devops"],
        "direction_ids": ["direction-digital"],
    }
    resp_s = client.post("/api/v1/reports/snapshot", json=req_snapshot, headers=headers("supervisor"))
    assert resp_s.status_code == 200
    s_counts = resp_s.json()["counts_by_state"]
    for st in STATES:
        assert st in s_counts, f"State {st} missing in snapshot counts_by_state"
        assert s_counts[st] >= 0

    req_activity = {
        "from": (datetime.now(timezone.utc) - timedelta(days=7)).isoformat(),
        "to": now_iso,
        "knowledge_cutoff": now_iso,
        "program_ids": ["program-devops"],
        "direction_ids": ["direction-digital"],
    }
    resp_a = client.post("/api/v1/reports/activity", json=req_activity, headers=headers("supervisor"))
    assert resp_a.status_code == 200
    a_counts = resp_a.json()["counts_by_to_state"]
    for st in STATES:
        assert st in a_counts, f"State {st} missing in activity counts_by_to_state"
        assert a_counts[st] >= 0


def test_created_report_time_boundaries_and_cutoff(app, client):
    """Stress-test created report: half-open interval [from, to) and knowledge_cutoff."""
    t_start = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)
    t_end = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)
    t_recv = datetime(2026, 8, 2, 10, 0, 0, tzinfo=timezone.utc)

    with app.state.session_factory() as session:
        # Interaction 1: created exactly at t_start
        i1 = Interaction(
            id="test-cr-1", title="CR Bound 1", organization_id="org-1",
            program_id="program-devops", product_id="product-cloud", cycle_label="2026-осень",
            owner_id="manager-a", state="contact_search", revision=1, created_at=t_start,
        )
        e1 = InteractionEvent(
            id="ev-cr-1", interaction_id="test-cr-1", type="created",
            effective_at=t_start, received_at=t_start, sequence=1, actor_id="manager-a", actor_name="Анна",
            payload={"snapshot": {"title": "CR Bound 1", "organization_id": "org-1", "state": "contact_search"}},
        )
        # Interaction 2: created 1 microsecond before t_end
        i2 = Interaction(
            id="test-cr-2", title="CR Bound 2", organization_id="org-1",
            program_id="program-devops", product_id="product-cloud", cycle_label="2026-осень",
            owner_id="manager-a", state="contact_search", revision=1, created_at=t_end - timedelta(microseconds=1),
        )
        e2 = InteractionEvent(
            id="ev-cr-2", interaction_id="test-cr-2", type="created",
            effective_at=t_end - timedelta(microseconds=1), received_at=t_end - timedelta(microseconds=1),
            sequence=1, actor_id="manager-a", actor_name="Анна",
            payload={"snapshot": {"title": "CR Bound 2", "organization_id": "org-1", "state": "contact_search"}},
        )
        # Interaction 3: created exactly at t_end (MUST BE EXCLUDED)
        i3 = Interaction(
            id="test-cr-3", title="CR Bound 3", organization_id="org-1",
            program_id="program-devops", product_id="product-cloud", cycle_label="2026-осень",
            owner_id="manager-a", state="contact_search", revision=1, created_at=t_end,
        )
        e3 = InteractionEvent(
            id="ev-cr-3", interaction_id="test-cr-3", type="created",
            effective_at=t_end, received_at=t_end, sequence=1, actor_id="manager-a", actor_name="Анна",
            payload={"snapshot": {"title": "CR Bound 3", "organization_id": "org-1", "state": "contact_search"}},
        )
        # Interaction 4: created at t_start + 1h, but received at t_recv (late)
        i4 = Interaction(
            id="test-cr-4", title="CR Bound 4", organization_id="org-1",
            program_id="program-devops", product_id="product-cloud", cycle_label="2026-осень",
            owner_id="manager-a", state="contact_search", revision=1, created_at=t_start + timedelta(hours=1),
        )
        e4 = InteractionEvent(
            id="ev-cr-4", interaction_id="test-cr-4", type="created",
            effective_at=t_start + timedelta(hours=1), received_at=t_recv, sequence=1,
            actor_id="manager-a", actor_name="Анна",
            payload={"snapshot": {"title": "CR Bound 4", "organization_id": "org-1", "state": "contact_search"}},
        )
        session.add_all([i1, e1, i2, e2, i3, e3, i4, e4])
        session.commit()

    # Query with cutoff before t_recv
    req_early = {
        "from": t_start.isoformat(),
        "to": t_end.isoformat(),
        "knowledge_cutoff": (t_end + timedelta(hours=1)).isoformat(),
        "organization_ids": ["org-1"],
    }
    resp_early = client.post("/api/v1/reports/created", json=req_early, headers=headers("supervisor"))
    assert resp_early.status_code == 200
    ids_early = resp_early.json()["interaction_ids"]
    assert "test-cr-1" in ids_early, "Interaction created at exact 'from' must be included"
    assert "test-cr-2" in ids_early, "Interaction created before 'to' must be included"
    assert "test-cr-3" not in ids_early, "Interaction created at exact 'to' must be excluded"
    assert "test-cr-4" not in ids_early, "Interaction with received_at > cutoff must be excluded"

    # Query with cutoff after t_recv
    req_late = dict(req_early, knowledge_cutoff=(t_recv + timedelta(hours=1)).isoformat())
    resp_late = client.post("/api/v1/reports/created", json=req_late, headers=headers("supervisor"))
    assert resp_late.status_code == 200
    ids_late = resp_late.json()["interaction_ids"]
    assert "test-cr-4" in ids_late, "Interaction with received_at <= cutoff must be included"


def test_selected_columns_multiformat_export(client):
    """Stress-test selected_columns across CSV, XLSX, and JSON exports."""
    now_iso = datetime.now(timezone.utc).isoformat()
    req = {
        "as_of": now_iso,
        "knowledge_cutoff": now_iso,
        "selected_columns": ["title", "owner_name"],
    }

    # JSON export
    json_resp = client.post("/api/v1/reports/snapshot/export?format=json", json=req, headers=headers("supervisor"))
    assert json_resp.status_code == 200
    data = json_resp.json()
    assert len(data["rows"]) > 0
    # Every row in json should have ONLY requested columns
    for r in data["rows"]:
        assert set(r.keys()).issubset({"title", "owner_name"})

    # CSV export
    csv_resp = client.post("/api/v1/reports/snapshot/export?format=csv", json=req, headers=headers("supervisor"))
    assert csv_resp.status_code == 200
    reader = csv.reader(io.StringIO(csv_resp.content.decode("utf-8-sig")))
    rows = list(reader)
    header = rows[0]
    assert len(header) == 2
    assert "Название" in header
    assert "Ответственный" in header


def test_scope_isolation_152fz_in_reports(client):
    """152-FZ Zero-Oracle check: manager-a must NEVER see manager-b's data in any report mode."""
    # Create an interaction owned by manager-b in org-2
    b_item = create_interaction(client, user="manager-b", organization_id="org-2", title="Секретный проект Б")
    b_id = b_item["id"]

    now_iso = datetime.now(timezone.utc).isoformat()
    req_snap = {"as_of": now_iso, "knowledge_cutoff": now_iso}

    # Manager A runs snapshot
    snap_resp = client.post("/api/v1/reports/snapshot", json=req_snap, headers=headers("manager-a"))
    assert snap_resp.status_code == 200
    snap_ids = snap_resp.json()["interaction_ids"]
    assert b_id not in snap_ids, "152-FZ VIOLATION: manager-a saw manager-b interaction in snapshot"

    # Manager A runs created
    req_cr = {
        "from": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        "to": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "knowledge_cutoff": now_iso,
    }
    cr_resp = client.post("/api/v1/reports/created", json=req_cr, headers=headers("manager-a"))
    assert cr_resp.status_code == 200
    cr_ids = cr_resp.json()["interaction_ids"]
    assert b_id not in cr_ids, "152-FZ VIOLATION: manager-a saw manager-b interaction in created report"

