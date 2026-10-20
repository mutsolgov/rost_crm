#!/usr/bin/env python3
"""Empirical Challenger Verification Script for Interactions Backend Localization (R1).

Verifies that recent_system_events in backend/app/services_modules/interactions.py:
1. Formats exact Russian localized titles for all 10 event types:
   - created -> f"Создано взаимодействие: {title}"
   - transition / state_changed -> f"Переход на этап «{to_st_name}»: {title}"
     * with known state from STATES (e.g. contact_search -> 'Поиск контактов')
     * with unknown state (e.g. custom_stage -> 'custom_stage')
     * with empty state (-> '')
   - assignment / owner_changed -> f"Назначен ответственный: {title}"
   - comment / comment_added -> f"Добавлен комментарий к: {title}"
   - attributes_corrected -> f"Обновлены реквизиты карточки: {title}"
   - attachment_uploaded -> with filename / with file_name / without filename
   - attachment_deleted -> with filename / with file_name / without filename
   - delivery_recorded -> with package title / without package title (fallback 'Пакет ПО')
   - workflow_migrated -> with versions / without versions (fallback '?')
   - unknown / fallback -> f"Системная операция: {title}"
2. Strictly preserves "type" and "event_type" without tampering.
3. Correctly preserves actor_name and ISO timestamps.
4. Operates end-to-end via FastAPI TestClient.
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

# Setup sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, Interaction, InteractionEvent, User
from app.services_modules.interactions import dashboard
from app.workflow import STATES
from fastapi.testclient import TestClient
from app.main import create_app
from app.config import Settings


def run_unit_empirical_tests():
    print("[1/2] Running Direct Unit Empirical Stress Tests on interactions.dashboard...")
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    admin_user = User(
        id="admin-test",
        keycloak_subject="sub-admin-test",
        role="administrator",
        name="Администратор Тестовый",
        active=True,
    )
    session.add(admin_user)

    test_interaction = Interaction(
        id="ix-emp-1",
        title="Тестовое взаимодействие с ИТ-Вузом",
        organization_id="org-emp-1",
        cycle_label="2026/2027",
        state="initial",
        owner_id="admin-test",
    )
    session.add(test_interaction)
    session.commit()

    # Define test cases for all 10 event types and variations
    test_cases = [
        # 1. created
        {
            "id": "evt-01",
            "type": "created",
            "actor": "Иванов И.И.",
            "payload": {},
            "expected_title": "Создано взаимодействие: Тестовое взаимодействие с ИТ-Вузом",
        },
        # 2a. transition with known state from STATES ("contact_search" -> "Поиск контактов")
        {
            "id": "evt-02a",
            "type": "transition",
            "actor": "Петров П.П.",
            "payload": {"from_state": "initial", "to_state": "contact_search"},
            "expected_title": "Переход на этап «Поиск контактов»: Тестовое взаимодействие с ИТ-Вузом",
        },
        # 2b. state_changed with unknown state ("custom_stage" -> "custom_stage")
        {
            "id": "evt-02b",
            "type": "state_changed",
            "actor": "Сидоров С.С.",
            "payload": {"from_state": "initial", "to_state": "custom_stage"},
            "expected_title": "Переход на этап «custom_stage»: Тестовое взаимодействие с ИТ-Вузом",
        },
        # 2c. transition with empty to_state
        {
            "id": "evt-02c",
            "type": "transition",
            "actor": "Сидоров С.С.",
            "payload": {"to_state": ""},
            "expected_title": "Переход на этап «»: Тестовое взаимодействие с ИТ-Вузом",
        },
        # 3a. assignment
        {
            "id": "evt-03a",
            "type": "assignment",
            "actor": "Координатор 1",
            "payload": {"owner_id": "manager-a"},
            "expected_title": "Назначен ответственный: Тестовое взаимодействие с ИТ-Вузом",
        },
        # 3b. owner_changed
        {
            "id": "evt-03b",
            "type": "owner_changed",
            "actor": "Координатор 2",
            "payload": {"owner_id": "manager-b"},
            "expected_title": "Назначен ответственный: Тестовое взаимодействие с ИТ-Вузом",
        },
        # 4a. comment
        {
            "id": "evt-04a",
            "type": "comment",
            "actor": "Куратор А",
            "payload": {"comment": "Требуется согласование учебного плана"},
            "expected_title": "Добавлен комментарий к: Тестовое взаимодействие с ИТ-Вузом",
        },
        # 4b. comment_added
        {
            "id": "evt-04b",
            "type": "comment_added",
            "actor": "Куратор Б",
            "payload": {"comment": "Согласование получено"},
            "expected_title": "Добавлен комментарий к: Тестовое взаимодействие с ИТ-Вузом",
        },
        # 5. attributes_corrected
        {
            "id": "evt-05",
            "type": "attributes_corrected",
            "actor": "Менеджер М",
            "payload": {"cycle_label": "Осенний семестр 2026"},
            "expected_title": "Обновлены реквизиты карточки: Тестовое взаимодействие с ИТ-Вузом",
        },
        # 6a. attachment_uploaded with filename
        {
            "id": "evt-06a",
            "type": "attachment_uploaded",
            "actor": "Инженер И",
            "payload": {"filename": "договор_партнерства.pdf"},
            "expected_title": "Загружен файл «договор_партнерства.pdf»: Тестовое взаимодействие с ИТ-Вузом",
        },
        # 6b. attachment_uploaded with file_name
        {
            "id": "evt-06b",
            "type": "attachment_uploaded",
            "actor": "Инженер И",
            "payload": {"file_name": "спецификация_курса.docx"},
            "expected_title": "Загружен файл «спецификация_курса.docx»: Тестовое взаимодействие с ИТ-Вузом",
        },
        # 6c. attachment_uploaded without filename
        {
            "id": "evt-06c",
            "type": "attachment_uploaded",
            "actor": "Инженер И",
            "payload": {},
            "expected_title": "Загружен файл: Тестовое взаимодействие с ИТ-Вузом",
        },
        # 7a. attachment_deleted with filename
        {
            "id": "evt-07a",
            "type": "attachment_deleted",
            "actor": "Инженер И",
            "payload": {"filename": "старый_черновик.pdf"},
            "expected_title": "Удалён файл «старый_черновик.pdf»: Тестовое взаимодействие с ИТ-Вузом",
        },
        # 7b. attachment_deleted with file_name
        {
            "id": "evt-07b",
            "type": "attachment_deleted",
            "actor": "Инженер И",
            "payload": {"file_name": "неактуальная_справка.docx"},
            "expected_title": "Удалён файл «неактуальная_справка.docx»: Тестовое взаимодействие с ИТ-Вузом",
        },
        # 7c. attachment_deleted without filename
        {
            "id": "evt-07c",
            "type": "attachment_deleted",
            "actor": "Инженер И",
            "payload": {},
            "expected_title": "Удалён файл: Тестовое взаимодействие с ИТ-Вузом",
        },
        # 8a. delivery_recorded with package title
        {
            "id": "evt-08a",
            "type": "delivery_recorded",
            "actor": "Логист Л",
            "payload": {"title": "Дистрибутив Ростелеком LMS v3.4"},
            "expected_title": "Выдача ПО (Дистрибутив Ростелеком LMS v3.4): Тестовое взаимодействие с ИТ-Вузом",
        },
        # 8b. delivery_recorded without package title
        {
            "id": "evt-08b",
            "type": "delivery_recorded",
            "actor": "Логист Л",
            "payload": {},
            "expected_title": "Выдача ПО (Пакет ПО): Тестовое взаимодействие с ИТ-Вузом",
        },
        # 9a. workflow_migrated with versions
        {
            "id": "evt-09a",
            "type": "workflow_migrated",
            "actor": "Архитектор А",
            "payload": {"from_version": 1, "to_version": 2},
            "expected_title": "Миграция процесса v1→v2: Тестовое взаимодействие с ИТ-Вузом",
        },
        # 9b. workflow_migrated without versions
        {
            "id": "evt-09b",
            "type": "workflow_migrated",
            "actor": "Архитектор А",
            "payload": {},
            "expected_title": "Миграция процесса v?→v?: Тестовое взаимодействие с ИТ-Вузом",
        },
        # 10. unknown/fallback
        {
            "id": "evt-10",
            "type": "custom_audit_op",
            "actor": "Системный демон",
            "payload": {"op": "deep_scan"},
            "expected_title": "Системная операция: Тестовое взаимодействие с ИТ-Вузом",
        },
    ]

    now = datetime.now(timezone.utc)
    for i, tc in enumerate(test_cases):
        event = InteractionEvent(
            id=tc["id"],
            interaction_id="ix-emp-1",
            sequence=i + 1,
            type=tc["type"],
            actor_id="admin-test",
            actor_name=tc["actor"],
            received_at=now,
            effective_at=now,
            payload=tc["payload"],
        )
        session.add(event)
    session.commit()

    # Call dashboard function directly
    dash_res = dashboard(session, admin_user)

    assert "system_stats" in dash_res, "system_stats key must be present in admin dashboard"
    system_stats = dash_res["system_stats"]
    assert "recent_system_events" in system_stats, "recent_system_events must be present in system_stats"
    events = system_stats["recent_system_events"]

    event_map = {e["id"]: e for e in events}

    print(f"Total events retrieved in recent_system_events: {len(events)} (expected {len(test_cases)})")

    for tc in test_cases:
        eid = tc["id"]
        assert eid in event_map, f"Event {eid} ({tc['type']}) missing from recent_system_events!"
        actual_evt = event_map[eid]

        # 1. Exact title check
        expected_title = tc["expected_title"]
        assert actual_evt["title"] == expected_title, (
            f"Title mismatch for event {eid} ({tc['type']}):\n"
            f"  Expected: '{expected_title}'\n"
            f"  Actual:   '{actual_evt['title']}'"
        )

        # 2. Invariant: type and event_type strictly unchanged
        assert actual_evt["type"] == tc["type"], f"Event {eid}: 'type' was modified! ({actual_evt['type']} != {tc['type']})"
        assert actual_evt["event_type"] == tc["type"], f"Event {eid}: 'event_type' was modified! ({actual_evt['event_type']} != {tc['type']})"

        # 3. Actor name and description check
        assert actual_evt["actor_name"] == tc["actor"], f"Event {eid}: actor_name mismatch"
        assert actual_evt["description"] == f"Пользователь: {tc['actor']}"

        # 4. Valid ISO timestamps
        assert "received_at" in actual_evt and actual_evt["received_at"].endswith("Z") or "+00:00" in actual_evt["received_at"]
        print(f"  [PASS] {tc['type']} ({eid}) -> '{actual_evt['title']}' [type={actual_evt['type']}]")

    print("[SUCCESS] All 10 event types (19 variations) verified with exact localized titles and intact types.")


def run_e2e_api_test():
    print("\n[2/2] Running E2E API Test via FastAPI TestClient on GET /api/v1/dashboard...")
    import tempfile
    from app.seed import seed_database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        app = create_app(Settings(
            database_url=f"sqlite:///{db_path.as_posix()}",
            app_env="development",
            auth_mode="demo",
        ))
        Base.metadata.create_all(app.state.engine)
        with app.state.session_factory() as session:
            seed_database(session)
            session.commit()

        client = TestClient(app)

        # Call dashboard as administrator
        resp = client.get("/api/v1/dashboard", headers={"X-Demo-User": "administrator"})
        assert resp.status_code == 200, f"Dashboard returned {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "system_stats" in data, "Dashboard response missing system_stats for administrator"
        recent = data["system_stats"]["recent_system_events"]
        assert isinstance(recent, list)
        print(f"E2E Admin Dashboard returned {len(recent)} recent system events.")
        for ev in recent[:5]:
            print(f"  - [{ev.get('type')}] {ev.get('title')} ({ev.get('description')})")
            assert "type" in ev
            assert "event_type" in ev
            assert "title" in ev
            assert "description" in ev

        app.state.engine.dispose()
    print("[SUCCESS] E2E API Test passed.")


if __name__ == "__main__":
    try:
        run_unit_empirical_tests()
        run_e2e_api_test()
        print("\nALL EMPIRICAL CHALLENGER TESTS PASSED SUCCESSFULLY.")
    except Exception as e:
        print(f"\n[FAIL] Empirical Challenger test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
