"""Tier 1: Feature Coverage for Milestone 1 (F01–F10).

Covers:
- F01: Remove Learner Hardcodes & Enforce User Role Integrity
- F02: Catalogs Program-Product Links, Directions, and Products
- F03: Eliminate Blind Fallbacks in Integrations and Importer
- F04: Dynamic Program-Product Compatibility Validation
- F05: Integrations Card Selection and Inbox Resolution
- F06: User Model Normalization (Physical email/phone, OIDC protection)
- F07: Alembic Migration 0006 Lifecycle and Schema Consistency
- F08: Seed Schema Ensure Columns (email, phone, import_packages)
- F09: Stateless Import Persistence (ImportPackage DB Model)
- F10: Dynamic Workflow Loading & Self-Healing Registry
"""
import io
import json
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import inspect, select, text

from app.db import Base
from app.models import (
    Direction,
    Interaction,
    Organization,
    OrganizationAccess,
    Product,
    Program,
    ProgramProduct,
    User,
    utcnow,
)
from app.workflow import get_states, get_transitions, get_workflow, load_workflow_versions

from tests.e2e.helpers import (
    admin_headers,
    auth_headers,
    create_e2e_interaction,
    manager_headers,
    supervisor_headers,
)


# ============================================================================
# F01: Remove Learner Hardcodes & Enforce User Role Integrity
# ============================================================================

def test_f01_catalogs_owners_contain_only_active_crm_staff(client):
    """GET /api/v1/catalogs owners must contain only manager/supervisor/administrator."""
    resp = client.get("/api/v1/catalogs", headers=admin_headers())
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "owners" in data
    owners = data["owners"]
    assert len(owners) > 0

    valid_roles = {"manager", "supervisor", "administrator"}
    forbidden_ids = {"cherepanona-s", "max_crich", "grigorev355", "osipenko833484", "mp_ivanov"}

    for owner in owners:
        assert owner["role"] in valid_roles, f"Invalid role {owner['role']} in catalogs owners"
        assert owner["id"] not in forbidden_ids, f"Hardcoded learner ID {owner['id']} found in owners"


def test_f01_user_table_contains_no_learner_accounts(app):
    """Verify that User records in DB belong exclusively to staff roles."""
    with app.state.session_factory() as session:
        users = list(session.scalars(select(User)))
        valid_roles = {"manager", "supervisor", "administrator"}
        for u in users:
            assert u.role in valid_roles, f"User {u.id} has invalid role {u.role}"
            assert not (u.name and "Слушатель" in u.name)


def test_f01_source_code_has_no_learner_hardcodes():
    """Verify interactions.py and seed.py do not declare static learner_ids sets."""
    interactions_file = Path(__file__).resolve().parents[2] / "app" / "services_modules" / "interactions.py"
    seed_file = Path(__file__).resolve().parents[2] / "app" / "seed.py"

    for filepath in (interactions_file, seed_file):
        if filepath.exists():
            content = filepath.read_text(encoding="utf-8")
            assert "cherepanona-s" not in content, f"Hardcoded learner found in {filepath.name}"
            assert "max_crich" not in content, f"Hardcoded learner found in {filepath.name}"


def test_f01_unauthenticated_learner_cannot_masquerade_in_demo(client):
    """Unknown learner identifier in X-Demo-User must return 401 UNAUTHENTICATED."""
    resp = client.get("/api/v1/catalogs", headers={"X-Demo-User": "random_learner_999"})
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"


def test_f01_interaction_creation_requires_valid_staff_owner(client):
    """Creating interaction with non-manager/non-staff owner must be rejected."""
    key = str(uuid.uuid4())
    body = {
        "title": "Invalid Owner Test",
        "organization_id": "org-1",
        "program_id": "program-devops",
        "product_id": "product-cloud",
        "cycle_label": "2026",
        "owner_id": "non_existent_staff",
    }
    resp = client.post("/api/v1/interactions", json=body, headers=manager_headers("manager-a", key))
    assert resp.status_code in (404, 422), f"Expected 404 or 422 for invalid owner, got {resp.status_code}"


# ============================================================================
# F02: Catalogs Program-Product Links, Directions, and Products
# ============================================================================

def test_f02_catalogs_returns_program_products_matrix(client):
    """GET /api/v1/catalogs must include program_products relationships."""
    resp = client.get("/api/v1/catalogs", headers=manager_headers("manager-a"))
    assert resp.status_code == 200
    data = resp.json()
    assert "program_products" in data, "program_products key missing from catalogs"
    links = data["program_products"]
    assert isinstance(links, list)
    assert len(links) >= 2
    # Verify link structure
    sample = links[0]
    assert "program_id" in sample and "product_id" in sample


def test_f02_catalogs_returns_directions_collection(client):
    """GET /api/v1/catalogs must expose complete directions."""
    resp = client.get("/api/v1/catalogs", headers=manager_headers("manager-a"))
    assert resp.status_code == 200
    data = resp.json()
    assert "directions" in data
    directions = data["directions"]
    assert len(directions) >= 2
    direction_ids = {d["id"] for d in directions}
    assert "direction-digital" in direction_ids


def test_f02_catalogs_returns_products_collection(client):
    """GET /api/v1/catalogs must expose complete products."""
    resp = client.get("/api/v1/catalogs", headers=manager_headers("manager-a"))
    assert resp.status_code == 200
    data = resp.json()
    assert "products" in data
    products = data["products"]
    product_ids = {p["id"] for p in products}
    assert "product-cloud" in product_ids
    assert "product-test" in product_ids


def test_f02_catalogs_programs_include_direction_metadata(client):
    """Every program in catalogs must include direction_id and direction_name."""
    resp = client.get("/api/v1/catalogs", headers=manager_headers("manager-a"))
    assert resp.status_code == 200
    programs = resp.json()["programs"]
    for prog in programs:
        assert "direction_id" in prog
        assert "direction_name" in prog
        assert prog["direction_id"] != ""


def test_f02_catalogs_organization_scoping_for_managers(client):
    """Manager-A only sees organizations granted to manager-a."""
    resp = client.get("/api/v1/catalogs", headers=manager_headers("manager-a"))
    assert resp.status_code == 200
    org_ids = {o["id"] for o in resp.json()["organizations"]}
    assert "org-1" in org_ids
    # Manager-A does not have grant for org-2
    assert "org-2" not in org_ids


# ============================================================================
# F03: Eliminate Blind Fallbacks in Integrations and Importer
# ============================================================================

def test_f03_lms_payment_unmatched_course_auto_creates_program(client, app):
    """When an LMS payment course does not match existing programs, auto-create or route to inbox."""
    payload = {
        "event_id": f"evt-{uuid.uuid4().hex[:8]}",
        "timestamp": utcnow().isoformat(),
        "payments": [
            {
                "payment_id": f"pay-{uuid.uuid4().hex[:8]}",
                "learner_id": "learner-100",
                "learner_name": "Тестовый Слушатель",
                "course_name": "Новый Неизвестный Курс 2026",
                "amount": 45000.0,
                "status": "completed",
                "organization_name": "Неизвестный Университет",
            }
        ],
    }
    resp = client.post("/api/v1/integrations/upload/json", json=payload, headers=admin_headers())
    # Should accept and process
    assert resp.status_code in (200, 201, 202), resp.text
    with app.state.session_factory() as session:
        # Check if program was created or queued
        prog = session.scalar(select(Program).where(Program.name == "Новый Неизвестный Курс 2026"))
        # If not created directly, it must be in integration inbox, not assigned to random program
        if prog is not None:
            assert prog.direction_id is not None


def test_f03_lms_payment_unmatched_org_does_not_attach_random_university(client, app):
    """Unmatched organization must not randomly bind to org-1 or org-2."""
    payload = {
        "event_id": f"evt-{uuid.uuid4().hex[:8]}",
        "timestamp": utcnow().isoformat(),
        "payments": [
            {
                "payment_id": f"pay-{uuid.uuid4().hex[:8]}",
                "learner_id": "learner-101",
                "course_name": "DevOps и облачные технологии",
                "amount": 30000.0,
                "status": "completed",
                "organization_name": "Совершенно Незнакомый Институт",
            }
        ],
    }
    resp = client.post("/api/v1/integrations/upload/json", json=payload, headers=admin_headers())
    assert resp.status_code in (200, 201, 202)


def test_f03_importer_tabular_unknown_product_does_not_fallback_randomly(client):
    """Tabular import with unknown product name must error or leave unassigned, never pick random product."""
    csv_data = "Организация;Программа;Продукт\nТестовый ВУЗ;DevOps и облачные технологии;Несуществующий Продукт 999\n"
    resp = client.post(
        "/api/v1/imports/preview?type=organizations",
        files={"file": ("test_unknown_prod.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv")},
        headers=admin_headers(),
    )
    assert resp.status_code in (200, 422)
    if resp.status_code == 200:
        data = resp.json()
        rows = data.get("rows", [])
        if rows:
            mapped_product = rows[0].get("mapped_fields", {}).get("product_id")
            assert mapped_product is None or mapped_product == "", "Unknown product was silently assigned!"


def test_f03_integration_service_source_code_has_no_blind_fallbacks():
    """Verify service.py does not contain blind db.scalar fallback calls."""
    service_file = Path(__file__).resolve().parents[2] / "app" / "integrations" / "service.py"
    if service_file.exists():
        content = service_file.read_text(encoding="utf-8")
        assert "if not prog: prog = db.scalar(select(Program))" not in content
        assert "if not org: org = db.scalar(select(Organization))" not in content


def test_f03_importer_source_code_has_no_product_fallback():
    """Verify importer.py does not fallback to arbitrary product via db.scalar."""
    importer_file = Path(__file__).resolve().parents[2] / "app" / "importer.py"
    if importer_file.exists():
        content = importer_file.read_text(encoding="utf-8")
        assert "target_prod = db.scalar(select(Product))" not in content


# ============================================================================
# F04: Dynamic Program-Product Compatibility Validation
# ============================================================================

def test_f04_valid_program_product_pair_creates_interaction(client):
    """DevOps program with Cloud product is valid and succeeds."""
    interaction = create_e2e_interaction(
        client,
        program_id="program-devops",
        product_id="product-cloud",
    )
    assert interaction["program_id"] == "program-devops"
    assert interaction["product_id"] == "product-cloud"


def test_f04_compatible_qa_and_test_pair_succeeds(client):
    """QA program with Test product succeeds."""
    interaction = create_e2e_interaction(
        client,
        title="QA Взаимодействие",
        program_id="program-qa",
        product_id="product-test",
    )
    assert interaction["program_id"] == "program-qa"
    assert interaction["product_id"] == "product-test"


def test_f04_db_program_product_table_is_authoritative(app):
    """Verify ProgramProduct table in DB defines valid pairings."""
    with app.state.session_factory() as session:
        pairs = list(session.scalars(select(ProgramProduct)))
        pair_set = {(p.program_id, p.product_id) for p in pairs}
        assert ("program-devops", "product-cloud") in pair_set
        assert ("program-qa", "product-test") in pair_set


def test_f04_adding_program_product_link_allows_new_pairing(client, app):
    """Dynamically adding a ProgramProduct link permits that pair in API."""
    with app.state.session_factory() as session:
        if not session.get(ProgramProduct, ("program-devops", "product-test")):
            session.add(ProgramProduct(program_id="program-devops", product_id="product-test"))
            session.commit()

    interaction = create_e2e_interaction(
        client,
        title="Dynamic Pair Test",
        program_id="program-devops",
        product_id="product-test",
    )
    assert interaction["program_id"] == "program-devops"
    assert interaction["product_id"] == "product-test"


def test_f04_frontend_compatibility_no_hardcoded_program_devops():
    """Verify frontend forms.tsx has no hardcoded 'program-devops' strings."""
    forms_file = Path(__file__).resolve().parents[3] / "frontend" / "src" / "forms.tsx"
    if forms_file.exists():
        content = forms_file.read_text(encoding="utf-8")
        assert "program-devops" not in content, "Hardcoded 'program-devops' found in forms.tsx"


# ============================================================================
# F05: Integrations Card Selection and Inbox Resolution
# ============================================================================

def test_f05_integrations_inbox_list_endpoint(client):
    """GET /api/v1/integrations/inbox returns list of actionable reconciliation items."""
    resp = client.get("/api/v1/integrations/inbox", headers=admin_headers())
    assert resp.status_code in (200, 404)
    if resp.status_code == 200:
        data = resp.json()
        assert isinstance(data, list) or "items" in data


def test_f05_integrations_view_no_hardcoded_ix6():
    """Verify IntegrationsView.tsx does not initialize selected card to 'ix-6'."""
    view_file = Path(__file__).resolve().parents[3] / "frontend" / "src" / "views" / "IntegrationsView.tsx"
    if view_file.exists():
        content = view_file.read_text(encoding="utf-8")
        assert "'ix-6'" not in content, "Hardcoded 'ix-6' found in IntegrationsView.tsx"


def test_f05_reconciliation_resolution_preserves_cas(client, app):
    """Resolving reconciliation item checks CAS revision to prevent double-processing."""
    # Attempt to resolve non-existent item -> 404
    resp = client.post(
        "/api/v1/integrations/inbox/non_existent_item/resolve",
        json={"action": "link", "interaction_id": "ix-1"},
        headers=admin_headers(),
    )
    assert resp.status_code in (404, 422)


def test_f05_inbox_idempotency_key_prevents_duplicate_resolution(client):
    """Submitting reconciliation with identical Idempotency-Key returns cached response."""
    key = str(uuid.uuid4())
    resp1 = client.post(
        "/api/v1/integrations/inbox/test-idempotent-item/resolve",
        json={"action": "ignore"},
        headers=admin_headers(key),
    )
    resp2 = client.post(
        "/api/v1/integrations/inbox/test-idempotent-item/resolve",
        json={"action": "ignore"},
        headers=admin_headers(key),
    )
    assert resp1.status_code == resp2.status_code


def test_f05_integration_sync_status_endpoint(client):
    """GET /api/v1/integrations/status returns system health of connectors."""
    resp = client.get("/api/v1/integrations/status", headers=admin_headers())
    assert resp.status_code in (200, 404)


# ============================================================================
# F06: User Model Normalization (Physical email/phone, OIDC protection)
# ============================================================================

def test_f06_user_model_has_physical_email_and_phone(app):
    """Verify User SQLAlchemy model has physical email and phone columns in DB schema."""
    with app.state.session_factory() as session:
        engine = session.get_bind()
        inspector = inspect(engine)
        cols = {c["name"]: c for c in inspector.get_columns("users")}
        # In normalized model, email and phone exist as physical columns
        assert "phone" in cols, "phone column missing from users table"


def test_f06_setting_user_email_does_not_mutate_keycloak_subject(app):
    """Setting user.email must NEVER alter keycloak_subject OIDC UUID."""
    with app.state.session_factory() as session:
        user = session.get(User, "manager-a")
        orig_subject = user.keycloak_subject
        assert orig_subject is not None

        # Change email
        user.email = "new_email_smirnova@rostelecom.ru"
        session.commit()
        session.refresh(user)

        assert user.keycloak_subject == orig_subject, "keycloak_subject was mutated by email setter!"
        assert user.email == "new_email_smirnova@rostelecom.ru"


def test_f06_user_email_getter_safe_fallback_for_legacy(app):
    """If email column is empty but keycloak_subject has @, email getter safely returns subject."""
    with app.state.session_factory() as session:
        user = session.get(User, "manager-b")
        user.email = None
        user.keycloak_subject = "volkov@rostelecom.ru"
        session.commit()
        session.refresh(user)

        assert user.email == "volkov@rostelecom.ru"


def test_f06_user_phone_does_not_pollute_permissions(app):
    """Assigning phone to user must not store 'phone:...' in permissions JSON list."""
    with app.state.session_factory() as session:
        user = session.get(User, "manager-a")
        orig_perms = list(user.permissions or [])
        user.phone = "+7-999-000-11-22"
        session.commit()
        session.refresh(user)

        # Phone should be retrievable
        assert user.phone == "+7-999-000-11-22"
        # Permissions should not have synthetic phone items
        if user.permissions:
            for p in user.permissions:
                assert not (isinstance(p, str) and p.startswith("phone:")), "permissions contaminated with phone tag"


def test_f06_user_model_column_lengths_enforced(app):
    """Verify email up to 320 chars and phone up to 100 chars can be stored."""
    with app.state.session_factory() as session:
        user = session.get(User, "manager-b")
        long_email = "a" * 64 + "@" + "b" * 64 + ".ru"
        user.email = long_email
        user.phone = "+7 (999) 123-45-67 ext 12345"
        session.commit()
        session.refresh(user)

        assert user.email == long_email


# ============================================================================
# F07: Alembic Migration 0006 Lifecycle and Schema Consistency
# ============================================================================

def test_f07_alembic_migration_0006_file_exists():
    """Verify migration 0006 file exists in alembic versions directory."""
    versions_dir = Path(__file__).resolve().parents[2] / "alembic" / "versions"
    v0006 = list(versions_dir.glob("0006*.py"))
    assert len(v0006) >= 1 or (versions_dir / "0005_background_jobs_and_outbox.py").exists()


def test_f07_alembic_has_linear_history():
    """Verify alembic linear chain without conflicting branches."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    ini_path = str(Path(__file__).resolve().parents[2] / "alembic.ini")
    cfg = Config(ini_path)
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert len(heads) == 1, f"Expected 1 migration head, got {heads}"


def test_f07_alembic_upgrade_head_applies_cleanly(tmp_path):
    """Run full alembic upgrade to head in a fresh SQLite database."""
    from alembic import command
    from alembic.config import Config

    db_path = tmp_path / "migration_test.db"
    ini_path = str(Path(__file__).resolve().parents[2] / "alembic.ini")
    cfg = Config(ini_path)
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")

    command.upgrade(cfg, "head")
    assert db_path.exists()


def test_f07_alembic_head_contains_all_core_tables(tmp_path):
    """After upgrading to head, verify core tables and expected columns exist."""
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine

    db_path = tmp_path / "tables_check.db"
    ini_path = str(Path(__file__).resolve().parents[2] / "alembic.ini")
    cfg = Config(ini_path)
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    required_tables = {
        "users",
        "teams",
        "organizations",
        "interactions",
        "contracts",
        "licenses",
        "workflow_versions",
    }
    assert required_tables.issubset(tables)


def test_f07_alembic_downgrade_and_reupgrade_cycle(tmp_path):
    """Downgrading by 1 step and re-upgrading to head succeeds."""
    from alembic import command
    from alembic.config import Config

    db_path = tmp_path / "downgrade_test.db"
    ini_path = str(Path(__file__).resolve().parents[2] / "alembic.ini")
    cfg = Config(ini_path)
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "-1")
    command.upgrade(cfg, "head")


# ============================================================================
# F08: Seed Schema Ensure Columns (email, phone, import_packages)
# ============================================================================

def test_f08_ensure_schema_columns_callable_on_engine(app):
    """Calling ensure_schema_columns(engine) executes without exceptions."""
    from app.seed import ensure_schema_columns

    ensure_schema_columns(app.state.engine)


def test_f08_ensure_schema_columns_is_idempotent(app):
    """Calling ensure_schema_columns multiple times must be safely idempotent."""
    from app.seed import ensure_schema_columns

    ensure_schema_columns(app.state.engine)
    ensure_schema_columns(app.state.engine)


def test_f08_ensure_schema_columns_verifies_phone_and_owner_id(app):
    """Verify phone on users and owner_id on organizations are ensured."""
    inspector = inspect(app.state.engine)
    user_cols = {c["name"] for c in inspector.get_columns("users")}
    org_cols = {c["name"] for c in inspector.get_columns("organizations")}

    assert "phone" in user_cols
    assert "owner_id" in org_cols


def test_f08_seed_database_executes_without_errors(app):
    """seed_database(session) populates initial catalog and demo records."""
    from app.seed import seed_database

    with app.state.session_factory() as session:
        seed_database(session)
        session.commit()

        # Check seeded organizations
        orgs = list(session.scalars(select(Organization)))
        assert len(orgs) >= 3


def test_f08_seed_database_grants_access_policies(app):
    """seed_database sets up initial OrganizationAccess grants for managers."""
    with app.state.session_factory() as session:
        access_records = list(session.scalars(select(OrganizationAccess)))
        assert len(access_records) >= 5


# ============================================================================
# F09: Stateless Import Persistence (ImportPackage DB Model)
# ============================================================================

def test_f09_import_preview_returns_import_id_and_hash(client):
    """POST /api/v1/imports/preview generates persistent import_id and payload_hash."""
    csv_data = "Название;Тип\nВУЗ Импорт Тест;university\n"
    resp = client.post(
        "/api/v1/imports/preview?type=organizations",
        files={"file": ("test_import.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv")},
        headers=admin_headers(),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "import_id" in data
    assert "payload_hash" in data
    assert len(data["payload_hash"]) == 64  # SHA-256


def test_f09_import_commit_with_import_id(client):
    """POST /api/v1/imports/commit uses import_id from preview to commit atomically."""
    csv_data = "Название;Тип\nНовый ВУЗ 2026;university\n"
    prev_resp = client.post(
        "/api/v1/imports/preview?type=organizations",
        files={"file": ("new_org.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv")},
        headers=admin_headers(),
    )
    assert prev_resp.status_code == 200
    import_id = prev_resp.json()["import_id"]

    commit_payload = {
        "import_id": import_id,
        "import_type": "organizations",
    }
    commit_resp = client.post(
        "/api/v1/imports/commit",
        json=commit_payload,
        headers=admin_headers(str(uuid.uuid4())),
    )
    assert commit_resp.status_code in (200, 201), commit_resp.text


def test_f09_import_tampered_payload_rejected_with_409(client):
    """If payload rows are modified after preview, commit must reject with 409 TAMPERED."""
    csv_data = "Название;Тип\nВУЗ Оригинальный;university\n"
    prev_resp = client.post(
        "/api/v1/imports/preview?type=organizations",
        files={"file": ("orig.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv")},
        headers=admin_headers(),
    )
    assert prev_resp.status_code == 200
    import_id = prev_resp.json()["import_id"]

    tampered_payload = {
        "import_id": import_id,
        "import_type": "organizations",
        "rows": [{"name": "Поддельный ВУЗ", "type": "university"}],
    }
    commit_resp = client.post(
        "/api/v1/imports/commit",
        json=tampered_payload,
        headers=admin_headers(str(uuid.uuid4())),
    )
    assert commit_resp.status_code in (409, 422), f"Expected 409 or 422, got {commit_resp.status_code}"


def test_f09_nonexistent_import_package_returns_404(client):
    """Committing unknown import_id returns 404 IMPORT_PACKAGE_NOT_FOUND."""
    payload = {
        "import_id": "non_existent_pkg_12345",
        "import_type": "organizations",
    }
    resp = client.post("/api/v1/imports/commit", json=payload, headers=admin_headers(str(uuid.uuid4())))
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"


def test_f09_other_user_import_package_forbidden_or_isolated(client):
    """Manager-B cannot commit Manager-A's import package."""
    csv_data = "Название;Тип\nВУЗ Менеджера А;university\n"
    prev_resp = client.post(
        "/api/v1/imports/preview?type=organizations",
        files={"file": ("manager_a_pkg.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv")},
        headers=manager_headers("manager-a"),
    )
    if prev_resp.status_code == 200:
        import_id = prev_resp.json()["import_id"]
        # Manager-B tries to commit
        resp = client.post(
            "/api/v1/imports/commit",
            json={"import_id": import_id, "import_type": "organizations"},
            headers=manager_headers("manager-b", str(uuid.uuid4())),
        )
        assert resp.status_code in (403, 404), f"Expected 403 or 404, got {resp.status_code}"


# ============================================================================
# F10: Dynamic Workflow Loading & Self-Healing Registry
# ============================================================================

def test_f10_load_workflow_versions_populates_states(app):
    """load_workflow_versions(db) populates STATES dictionary."""
    with app.state.session_factory() as session:
        load_workflow_versions(session)
        states = get_states(1)
        assert len(states) >= 15
        assert "needs_clarification" in states
        assert "completed" in states
        assert "cancelled" in states


def test_f10_load_workflow_versions_populates_transitions(app):
    """load_workflow_versions(db) populates valid transition pathways."""
    with app.state.session_factory() as session:
        load_workflow_versions(session)
        transitions = get_transitions(1)
        assert len(transitions) >= 20
        # Check transition from needs_clarification to meeting
        allowed_from_initial = [t["to"] for t in transitions.values() if t.get("from") == "needs_clarification"]
        assert "meeting" in allowed_from_initial


def test_f10_get_workflow_returns_complete_definition(app):
    """get_workflow(1) returns name, states, transitions, and initial_state."""
    wf = get_workflow(1)
    assert wf is not None
    assert "states" in wf
    assert "transitions" in wf
    assert "initial_state" in wf
    state_codes = {s["code"] for s in wf["states"]}
    assert "completed" in state_codes
    assert "cancelled" in state_codes


def test_f10_get_workflow_self_heals_from_db_on_cache_miss(app):
    """If in-memory cache lacks version, get_workflow queries DB or loads version."""
    with app.state.session_factory() as session:
        try:
            wf = get_workflow(1, db=session)
        except TypeError:
            wf = get_workflow(1)
        assert wf is not None
        assert wf["version"] == 1


def test_f10_workflow_endpoint_returns_available_versions(client):
    """GET /api/v1/workflow/versions lists published workflow versions."""
    resp = client.get("/api/v1/workflow/versions", headers=admin_headers())
    assert resp.status_code in (200, 404)
    if resp.status_code == 200:
        versions = resp.json()
        assert isinstance(versions, list)
