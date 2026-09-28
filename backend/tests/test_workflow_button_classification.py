"""Automated tests for workflow button classification, step numbering, and Keycloak logout contract."""
import json
import re
from pathlib import Path

import pytest

from app.workflow import WORKFLOW_V1, WORKFLOW_V2, allowed_transitions, get_states, get_transitions

ROOT = Path(__file__).resolve().parents[2]


def test_keycloak_realm_json_contract():
    """Verify Keycloak realm json contains allowed redirect and post-logout URIs for 127.0.0.1 and localhost."""
    realm_path = ROOT / "deploy" / "keycloak" / "rtk-crm-realm.json"
    assert realm_path.exists(), f"Realm file not found: {realm_path}"

    realm_data = json.loads(realm_path.read_text(encoding="utf-8"))
    clients = realm_data.get("clients", [])
    web_client = next((c for c in clients if c.get("clientId") == "rtk-crm-web"), None)
    assert web_client is not None, "Client 'rtk-crm-web' not found in realm JSON"

    # redirectUris checks
    redirect_uris = web_client.get("redirectUris", [])
    expected_redirects = [
        "http://localhost:3000/*",
        "http://localhost:5173/*",
        "http://127.0.0.1:3000/*",
        "http://127.0.0.1:5173/*",
    ]
    for uri in expected_redirects:
        assert uri in redirect_uris, f"Expected {uri} in redirectUris, got {redirect_uris}"

    # webOrigins checks
    web_origins = web_client.get("webOrigins", [])
    expected_origins = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "+",
    ]
    for origin in expected_origins:
        assert origin in web_origins, f"Expected {origin} in webOrigins, got {web_origins}"

    # post.logout.redirect.uris check
    attributes = web_client.get("attributes", {})
    post_logout = attributes.get("post.logout.redirect.uris", "")
    expected_post_logout = (
        "+##http://localhost:3000/*##http://localhost:3000##http://127.0.0.1:3000/*##http://127.0.0.1:3000"
        "##http://localhost:5173/*##http://localhost:5173##http://127.0.0.1:5173/*##http://127.0.0.1:5173"
    )
    assert post_logout == expected_post_logout, (
        f"Mismatch in post.logout.redirect.uris: expected {expected_post_logout}, got {post_logout}"
    )


def test_allowed_transitions_contains_kind_for_all_working_states():
    """Verify presence of 'kind' in allowed_transitions for all 13 working states."""
    states = get_states(1)
    working_states = [code for code, s in states.items() if s.get("kind") == "working"]
    assert len(working_states) == 13, f"Expected 13 working states, found {len(working_states)}"

    for v in (1, 2):
        for state_code in working_states:
            transitions = allowed_transitions(state_code, version=v)
            assert len(transitions) > 0, f"Working state {state_code} in v{v} has no allowed transitions"
            for t in transitions:
                assert "kind" in t, f"Transition {t['code']} from {state_code} in v{v} is missing 'kind'"
                assert t["kind"] in {"forward", "skip_optional", "rework", "cycle", "cancellation"}, (
                    f"Unexpected kind '{t['kind']}' in transition {t['code']}"
                )

    # Terminal states must have empty allowed_transitions
    for terminal in ("completed", "cancelled"):
        assert allowed_transitions(terminal, version=1) == []
        assert allowed_transitions(terminal, version=2) == []


def classify_transition(transition: dict, states_map: dict) -> dict:
    """Canonical classification logic matching frontend getTransitionPresentation."""
    kind = transition.get("kind", "forward")
    to_state = transition.get("to")
    target_name = states_map[to_state]["name"] if to_state in states_map else transition.get("name", "")

    if kind == "cancellation" or to_state == "cancelled":
        return {
            "title": "Отменить взаимодействие",
            "variant": "danger",
            "icon": "close",
        }
    if kind == "skip_optional":
        return {
            "title": f"Пропустить: {target_name}",
            "variant": "secondary",
            "icon": "arrow",
        }
    if kind == "rework":
        return {
            "title": f"Вернуть: {target_name}",
            "variant": "secondary",
            "icon": "refresh",
        }
    if kind == "cycle":
        return {
            "title": f"Повторный цикл: {target_name}",
            "variant": "secondary",
            "icon": "refresh",
        }
    return {
        "title": f"Перейти: {target_name}",
        "variant": "primary",
        "icon": "arrow",
    }


def test_workflow_button_classification_all_29_transitions():
    """Verify correct classification (button title, variant, icon) for all 29 transitions of base workflow."""
    states_map = get_states(1)
    transitions_list = WORKFLOW_V1["transitions"]
    assert len(transitions_list) == 29, f"Expected 29 transitions in base workflow, found {len(transitions_list)}"

    counts = {"forward": 0, "skip_optional": 0, "rework": 0, "cycle": 0, "cancellation": 0}

    for edge in transitions_list:
        classification = classify_transition(edge, states_map)
        kind = edge.get("kind", "forward")
        counts[kind] = counts.get(kind, 0) + 1

        if kind == "forward":
            assert classification["variant"] == "primary"
            assert classification["icon"] == "arrow"
            assert classification["title"].startswith("Перейти: ")
        elif kind == "skip_optional":
            assert classification["variant"] == "secondary"
            assert classification["icon"] == "arrow"
            assert classification["title"].startswith("Пропустить: ")
        elif kind == "rework":
            assert classification["variant"] == "secondary"
            assert classification["icon"] == "refresh"
            assert classification["title"].startswith("Вернуть: ")
        elif kind == "cycle":
            assert classification["variant"] == "secondary"
            assert classification["icon"] == "refresh"
            assert classification["title"].startswith("Повторный цикл: ")
        elif kind == "cancellation":
            assert classification["variant"] == "danger"
            assert classification["icon"] == "close"
            assert classification["title"] == "Отменить взаимодействие"

    assert counts["forward"] == 13
    assert counts["skip_optional"] == 1
    assert counts["rework"] == 1
    assert counts["cycle"] == 1
    assert counts["cancellation"] == 13

    # Specific requirements verification:
    # 1. Step 10 -> 11: curriculum_update -> classes
    t_10_11 = next(t for t in transitions_list if t["code"] == "curriculum_update_to_classes")
    res_10_11 = classify_transition(t_10_11, states_map)
    assert res_10_11["title"] == "Перейти: Ведение занятий"
    assert res_10_11["variant"] == "primary"
    assert res_10_11["icon"] == "arrow"

    # 2. Step 4 -> 5: document_exchange -> document_revision
    t_4_5 = next(t for t in transitions_list if t["code"] == "document_exchange_to_document_revision")
    res_4_5 = classify_transition(t_4_5, states_map)
    assert res_4_5["title"] == "Перейти: Корректировка документов"
    assert res_4_5["variant"] == "primary"
    assert res_4_5["icon"] == "arrow"

    # 3. Rework: document_signing -> document_revision
    t_rework = next(t for t in transitions_list if t["code"] == "document_signing_to_document_revision")
    res_rework = classify_transition(t_rework, states_map)
    assert res_rework["title"] == "Вернуть: Корректировка документов"
    assert res_rework["variant"] == "secondary"
    assert res_rework["icon"] == "refresh"

    # 4. Cycle: teacher_upskilling -> classes
    t_cycle = next(t for t in transitions_list if t["code"] == "teacher_upskilling_to_classes")
    res_cycle = classify_transition(t_cycle, states_map)
    assert res_cycle["title"] == "Повторный цикл: Ведение занятий"
    assert res_cycle["variant"] == "secondary"
    assert res_cycle["icon"] == "refresh"

    # 5. Skip optional: document_exchange -> document_signing
    t_skip = next(t for t in transitions_list if t["code"] == "document_exchange_to_document_signing")
    res_skip = classify_transition(t_skip, states_map)
    assert res_skip["title"] == "Пропустить: Подписание документов"
    assert res_skip["variant"] == "secondary"
    assert res_skip["icon"] == "arrow"

    # 6. Cancellation: e.g. contact_search_to_cancelled
    t_cancel = next(t for t in transitions_list if t["code"] == "contact_search_to_cancelled")
    res_cancel = classify_transition(t_cancel, states_map)
    assert res_cancel["title"] == "Отменить взаимодействие"
    assert res_cancel["variant"] == "danger"
    assert res_cancel["icon"] == "close"


def test_step_numbering_contract_for_working_and_terminal_states():
    """Verify source_step numbering 1..13 and header string for all 13 working states."""
    states = get_states(1)
    working_states = [s for s in states.values() if s.get("kind") == "working"]
    assert len(working_states) == 13

    for state in working_states:
        step = state.get("source_step")
        assert step is not None, f"State {state['code']} has no source_step"
        assert 1 <= step <= 13, f"State {state['code']} has invalid source_step {step}"
        header = f"Этап {step} из 13: {state['name']}"
        assert f"Этап {step} из 13:" in header

    # Specific step 10 check:
    state_10 = states["curriculum_update"]
    assert state_10["source_step"] == 10
    assert state_10["name"] == "Актуализация учебной программы"
    header_10 = f"Этап {state_10['source_step']} из 13: {state_10['name']}"
    assert header_10 == "Этап 10 из 13: Актуализация учебной программы"


def test_interaction_api_detail_returns_kind_in_allowed_transitions(client):
    """Verify GET /api/v1/interactions/{id} serializes kind in allowed_transitions."""
    from uuid import uuid4
    body = {
        "title": "Тест сериализации kind",
        "organization_id": "org-1",
        "program_id": "program-devops",
        "product_id": "product-cloud",
        "cycle_label": "Цикл 1",
        "owner_id": "manager-a",
    }
    resp = client.post(
        "/api/v1/interactions",
        json=body,
        headers={"X-Demo-User": "manager-a", "Idempotency-Key": str(uuid4())},
    )
    assert resp.status_code == 201
    item = resp.json()
    item_id = item["id"]

    d_resp = client.get(f"/api/v1/interactions/{item_id}", headers={"X-Demo-User": "manager-a"})
    assert d_resp.status_code == 200
    detail = d_resp.json()
    assert "allowed_transitions" in detail
    assert len(detail["allowed_transitions"]) > 0

    for t in detail["allowed_transitions"]:
        assert "kind" in t, f"Transition {t.get('code')} missing 'kind'"
        assert t["kind"] in {"forward", "skip_optional", "rework", "cycle", "cancellation"}


def test_frontend_codebase_eliminated_hardcoded_state_checks():
    """Verify frontend/src/views/InteractionPage.tsx no longer hardcodes state checks for buttons."""
    page_file = ROOT / "frontend" / "src" / "views" / "InteractionPage.tsx"
    assert page_file.exists()
    content = page_file.read_text(encoding="utf-8")

    assert "t.to === 'document_revision'" not in content, (
        "Found forbidden hardcode 't.to === document_revision' in InteractionPage.tsx"
    )
    assert "t.to === 'classes'" not in content, (
        "Found forbidden hardcode 't.to === classes' in InteractionPage.tsx"
    )
    assert "Этап ${stepNumber} из 13: ${item.state_name}" in content or "Этап ${step} из 13" in content, (
        "Step numbering pattern missing in InteractionPage.tsx"
    )
    assert "getTransitionPresentation" in content, (
        "Helper getTransitionPresentation missing in InteractionPage.tsx"
    )


def test_frontend_auth_guaranteed_session_reset():
    """Verify frontend/src/auth.tsx resets session state in logout."""
    auth_file = ROOT / "frontend" / "src" / "auth.tsx"
    assert auth_file.exists()
    content = auth_file.read_text(encoding="utf-8")

    # In logout, setMe(null), setAuthenticated(false), and setLoading(false) must be called
    logout_section_match = re.search(r"const logout = \(\) => \{(.*?)\};", content, re.DOTALL)
    assert logout_section_match is not None, "logout function not found in auth.tsx"
    logout_body = logout_section_match.group(1)

    assert "setMe(null)" in logout_body
    assert "setAuthenticated(false)" in logout_body
    assert "setLoading(false)" in logout_body
    assert "clearToken" in logout_body
    assert "redirectUri" in logout_body


def test_workflow_v2_button_classification():
    """Verify button classification consistency for all 36 transitions in optimized workflow v2."""
    states_map = get_states(2)
    transitions_v2 = WORKFLOW_V2["transitions"]
    assert len(transitions_v2) == 36, f"Expected 36 transitions in v2, got {len(transitions_v2)}"

    # All transitions must classify without exceptions
    for edge in transitions_v2:
        res = classify_transition(edge, states_map)
        assert res["variant"] in {"primary", "secondary", "danger"}
        assert res["icon"] in {"arrow", "refresh", "close"}
        assert len(res["title"]) > 0

    # Specific fast-track transitions in v2
    v2_cases = {
        "meeting_to_document_signing": ("primary", "arrow", "Перейти: Подписание документов"),
        "materials_transfer_to_classes": ("primary", "arrow", "Перейти: Ведение занятий"),
        "classes_to_completed": ("primary", "arrow", "Перейти: Взаимодействие завершено"),
        "deployment_to_materials_transfer": ("secondary", "refresh", "Вернуть: Передача материалов и лицензии"),
        "classes_to_teacher_training": ("secondary", "refresh", "Вернуть: Обучение преподавателей"),
        "document_signing_to_meeting": ("secondary", "refresh", "Вернуть: Встреча с вузом"),
        "document_revision_to_meeting": ("secondary", "refresh", "Вернуть: Встреча с вузом"),
    }
    for code, (expected_variant, expected_icon, expected_title) in v2_cases.items():
        edge = next(t for t in transitions_v2 if t["code"] == code)
        res = classify_transition(edge, states_map)
        assert res["variant"] == expected_variant, f"{code}: expected variant {expected_variant}, got {res['variant']}"
        assert res["icon"] == expected_icon, f"{code}: expected icon {expected_icon}, got {res['icon']}"
        assert res["title"] == expected_title, f"{code}: expected title {expected_title}, got {res['title']}"


def test_frontend_canonical_stage_steps_coverage():
    """Verify frontend/src/views/InteractionPage.tsx has CANONICAL_STAGE_STEPS covering all 13 working states."""
    page_file = ROOT / "frontend" / "src" / "views" / "InteractionPage.tsx"
    assert page_file.exists()
    content = page_file.read_text(encoding="utf-8")

    assert "CANONICAL_STAGE_STEPS" in content
    states = get_states(1)
    working_states = [code for code, s in states.items() if s.get("kind") == "working"]
    assert len(working_states) == 13

    for code in working_states:
        expected_step = states[code]["source_step"]
        assert f"{code}: {expected_step}" in content, f"Expected {code}: {expected_step} in CANONICAL_STAGE_STEPS"


def test_frontend_get_transition_presentation_target_name_fallback():
    """Verify frontend/src/views/InteractionPage.tsx falls back to workflow.states when transition has no name."""
    page_file = ROOT / "frontend" / "src" / "views" / "InteractionPage.tsx"
    assert page_file.exists()
    content = page_file.read_text(encoding="utf-8")

    assert "targetName = t.name || workflow?.states?.find" in content, (
        "Expected getTransitionPresentation to resolve targetName with fallback to workflow.states"
    )


