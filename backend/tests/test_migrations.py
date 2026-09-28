"""Tests for Alembic versioned schema migrations (TASK-P01).

Verifies:
1. Online migration upgrade and downgrade lifecycle on SQLite.
2. Complete schema symmetry: all tables, foreign keys, and indexes created and cleanly dropped.
3. Offline migration DDL generation targeting PostgreSQL dialect.
4. Live PostgreSQL online migration lifecycle if a database is reachable.
5. Linear revision history and config file correctness.
"""
import io
import os
import re
from contextlib import redirect_stdout
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from app.models import Base
from app.seed import seed_database

BACKEND_DIR = Path(__file__).resolve().parents[1]
INI_PATH = str(BACKEND_DIR / "alembic.ini")

EXPECTED_TABLES = {
    "teams",
    "users",
    "organizations",
    "organization_access",
    "directions",
    "programs",
    "products",
    "program_products",
    "organization_contacts",
    "contracts",
    "licenses",
    "interactions",
    "attachments",
    "comments",
    "interaction_events",
    "command_results",
    "workflow_versions",
    "workflow_migration_dry_runs",
    "integration_inbox",
    "learning_metrics",
    "deliveries",
    "delivery_items",
    "access_policy_state",
    "state_visits",
    "report_runs",
    "report_rows",
    "background_jobs",
    "transactional_outbox",
}


def get_test_config(db_url: str) -> Config:
    """Create Alembic Config with specified database URL."""
    cfg = Config(INI_PATH)
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def test_alembic_config_and_linear_history():
    """Verify alembic.ini points to valid scripts and has exactly one head revision."""
    cfg = Config(INI_PATH)
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert len(heads) == 1, f"Expected exactly 1 migration head, got {heads}"
    assert heads[0] == "0005_background_jobs_and_outbox"

    base = script.get_base()
    assert base == "0001_initial_schema"


def test_sqlite_migration_lifecycle(tmp_path):
    """Test full upgrade, table inspection, downgrade, and re-upgrade on SQLite."""
    db_file = tmp_path / "test_migration.db"
    db_url = f"sqlite:///{db_file}"
    cfg = get_test_config(db_url)

    engine = create_engine(db_url)

    # 1. Upgrade to head
    command.upgrade(cfg, "head")

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    # Verify all expected domain and workflow tables exist
    missing = EXPECTED_TABLES - tables
    assert not missing, f"Missing tables after upgrade head: {missing}"
    assert "alembic_version" in tables

    # Verify column structures on key tables
    user_cols = {c["name"] for c in inspector.get_columns("users")}
    assert {"id", "keycloak_subject", "name", "role", "team_id", "permissions", "active"}.issubset(user_cols)

    interaction_cols = {c["name"] for c in inspector.get_columns("interactions")}
    assert {
        "id", "title", "organization_id", "owner_id", "state", "workflow_version", "revision"
    }.issubset(interaction_cols)

    wf_version_cols = {c["name"] for c in inspector.get_columns("workflow_versions")}
    assert {"id", "version", "name", "description", "created_at"}.issubset(wf_version_cols)

    contact_cols = {c["name"] for c in inspector.get_columns("organization_contacts")}
    assert {
        "id",
        "organization_id",
        "full_name",
        "position",
        "email",
        "phone",
        "active",
        "notes",
        "revision",
        "created_at",
        "updated_at",
        "archived_at",
    }.issubset(contact_cols)
    contact_col_map = {c["name"]: c for c in inspector.get_columns("organization_contacts")}
    assert contact_col_map["email"]["type"].length == 320
    assert contact_col_map["notes"]["nullable"] is True
    assert contact_col_map["revision"]["nullable"] is False
    assert contact_col_map["created_at"]["nullable"] is False
    assert contact_col_map["updated_at"]["nullable"] is False
    assert contact_col_map["archived_at"]["nullable"] is True

    # Verify indexes
    interaction_indexes = {ix["name"] for ix in inspector.get_indexes("interactions")}
    assert "ix_interactions_organization_id" in interaction_indexes
    assert "ix_interactions_owner_id" in interaction_indexes

    contact_indexes = {ix["name"]: ix for ix in inspector.get_indexes("organization_contacts")}
    assert "ix_org_contacts_active" in contact_indexes
    assert contact_indexes["ix_org_contacts_active"]["column_names"] == ["organization_id", "archived_at"]
    assert not contact_indexes["ix_org_contacts_active"]["unique"]

    contact_fks = inspector.get_foreign_keys("organization_contacts")
    assert any(
        fk["referred_table"] == "organizations" and fk["constrained_columns"] == ["organization_id"]
        for fk in contact_fks
    )

    # Verify access_policy_state columns and initial row
    state_cols = {c["name"] for c in inspector.get_columns("access_policy_state")}
    assert {"singleton_id", "epoch", "updated_at"}.issubset(state_cols)
    from sqlalchemy import text
    with engine.connect() as conn:
        state_row = conn.execute(text("SELECT singleton_id, epoch FROM access_policy_state")).mappings().one()
        assert state_row["singleton_id"] == 1
        assert state_row["epoch"] == 1

    # Verify temporal fact tables columns and foreign keys
    sv_cols = {c["name"] for c in inspector.get_columns("state_visits")}
    assert {"id", "interaction_id", "state", "entered_at", "exited_at", "duration_seconds"}.issubset(sv_cols)

    rr_cols = {c["name"] for c in inspector.get_columns("report_runs")}
    assert {
        "id", "requested_by", "report_type", "parameters", "parameters_hash",
        "knowledge_cutoff", "row_count", "dataset_checksum", "created_at"
    }.issubset(rr_cols)

    row_cols = {c["name"] for c in inspector.get_columns("report_rows")}
    assert {"id", "report_run_id", "ordinal", "row_data"}.issubset(row_cols)

    # Verify background_jobs and transactional_outbox columns
    job_cols = {c["name"] for c in inspector.get_columns("background_jobs")}
    assert {
        "id", "kind", "status", "progress", "requester_id", "authz_epoch",
        "parameters", "result_id", "error_message", "created_at", "updated_at"
    }.issubset(job_cols)

    outbox_cols = {c["name"] for c in inspector.get_columns("transactional_outbox")}
    assert {"id", "event_type", "payload", "status", "created_at", "processed_at"}.issubset(outbox_cols)

    # 2. Step downgrade to 0004_temporal_fact_tables (-1)
    command.downgrade(cfg, "-1")
    inspector_v4 = inspect(engine)
    assert not ({"background_jobs", "transactional_outbox"} & set(inspector_v4.get_table_names()))
    assert {"state_visits", "report_runs", "report_rows"}.issubset(set(inspector_v4.get_table_names()))

    # Step downgrade to 0003_authz_epoch (-1)
    command.downgrade(cfg, "-1")
    inspector_v3 = inspect(engine)
    assert not ({"state_visits", "report_runs", "report_rows"} & set(inspector_v3.get_table_names()))
    assert "access_policy_state" in set(inspector_v3.get_table_names())

    # Step downgrade to 0002_normalize_contacts (-1)
    command.downgrade(cfg, "-1")
    inspector_v2 = inspect(engine)
    assert "access_policy_state" not in set(inspector_v2.get_table_names())

    # Step downgrade to 0001_initial_schema (-1)
    command.downgrade(cfg, "-1")
    inspector_v1 = inspect(engine)
    v1_contact_cols = {c["name"] for c in inspector_v1.get_columns("organization_contacts")}
    assert not {"notes", "revision", "created_at", "updated_at", "archived_at"} & v1_contact_cols
    v1_contact_indexes = {ix["name"] for ix in inspector_v1.get_indexes("organization_contacts")}
    assert "ix_org_contacts_active" not in v1_contact_indexes
    v1_col_map = {c["name"]: c for c in inspector_v1.get_columns("organization_contacts")}
    assert v1_col_map["email"]["type"].length == 200

    # Re-upgrade to head before full base downgrade
    command.upgrade(cfg, "head")

    # 3. Downgrade to base
    command.downgrade(cfg, "base")

    inspector = inspect(engine)
    remaining_tables = set(inspector.get_table_names())
    # Only alembic_version (or empty set) should remain
    remaining_domain_tables = remaining_tables - {"alembic_version"}
    assert not remaining_domain_tables, f"Tables remained after downgrade base: {remaining_domain_tables}"

    # 4. Re-upgrade to head to prove repeatability
    command.upgrade(cfg, "head")
    re_tables = set(inspect(engine).get_table_names())
    assert EXPECTED_TABLES.issubset(re_tables)


def test_offline_postgresql_migration_ddl():
    """Verify offline SQL generation for PostgreSQL dialect during upgrade and downgrade."""
    pg_url = "postgresql+psycopg://rtk_crm:secret@localhost:5432/rtk_crm"
    cfg = get_test_config(pg_url)

    # 1. Offline upgrade SQL
    buf_up = io.StringIO()
    with redirect_stdout(buf_up):
        command.upgrade(cfg, "head", sql=True)
    up_sql = buf_up.getvalue()

    for table in EXPECTED_TABLES:
        assert f"CREATE TABLE {table}" in up_sql, f"Expected 'CREATE TABLE {table}' in offline PostgreSQL SQL"

    assert "INSERT INTO alembic_version" in up_sql
    assert "0001_initial_schema" in up_sql
    assert "0002_normalize_contacts" in up_sql
    assert "0003_authz_epoch" in up_sql
    assert "0004_temporal_fact_tables" in up_sql
    assert "0005_background_jobs_and_outbox" in up_sql
    assert "ix_org_contacts_active" in up_sql
    assert "CREATE INDEX ix_org_contacts_active ON organization_contacts (organization_id, archived_at)" in up_sql

    create_order = re.findall(r"CREATE TABLE\s+([a-zA-Z0-9_]+)\s*\(", up_sql)
    create_indices = {name: idx for idx, name in enumerate(create_order)}
    for table_name, table in Base.metadata.tables.items():
        if table_name not in create_indices:
            continue
        for fk in table.foreign_keys:
            target_table = fk.column.table.name
            if target_table == table_name or target_table not in create_indices:
                continue
            assert create_indices[target_table] < create_indices[table_name], (
                f"Creation order violation: {table_name} (idx {create_indices[table_name]}) references "
                f"target {target_table} (idx {create_indices[target_table]}) but is created before it"
            )

    # 2a. Offline downgrade SQL for 0005 -> 0004
    buf_down_0005 = io.StringIO()
    with redirect_stdout(buf_down_0005):
        command.downgrade(cfg, "0005_background_jobs_and_outbox:0004_temporal_fact_tables", sql=True)
    down_0005_sql = buf_down_0005.getvalue()
    assert "DROP TABLE transactional_outbox" in down_0005_sql
    assert "DROP TABLE background_jobs" in down_0005_sql
    assert "0004_temporal_fact_tables" in down_0005_sql

    # 2b. Offline downgrade SQL for 0004 -> 0003
    buf_down_0004 = io.StringIO()
    with redirect_stdout(buf_down_0004):
        command.downgrade(cfg, "0004_temporal_fact_tables:0003_authz_epoch", sql=True)
    down_0004_sql = buf_down_0004.getvalue()
    assert "DROP TABLE report_rows" in down_0004_sql
    assert "DROP TABLE report_runs" in down_0004_sql
    assert "DROP TABLE state_visits" in down_0004_sql
    assert "0003_authz_epoch" in down_0004_sql

    # 2c. Offline downgrade SQL for 0003 -> 0002
    buf_down_0003 = io.StringIO()
    with redirect_stdout(buf_down_0003):
        command.downgrade(cfg, "0003_authz_epoch:0002_normalize_contacts", sql=True)
    down_0003_sql = buf_down_0003.getvalue()
    assert "DROP TABLE access_policy_state" in down_0003_sql
    assert "0002_normalize_contacts" in down_0003_sql

    # 2d. Offline downgrade SQL for 0002 -> 0001
    buf_down_0002 = io.StringIO()
    with redirect_stdout(buf_down_0002):
        command.downgrade(cfg, "0002_normalize_contacts:0001_initial_schema", sql=True)
    down_0002_sql = buf_down_0002.getvalue()
    assert "ix_org_contacts_active" in down_0002_sql
    assert "0001_initial_schema" in down_0002_sql

    # 3. Offline downgrade SQL for 0001 -> base
    buf_down = io.StringIO()
    with redirect_stdout(buf_down):
        command.downgrade(cfg, "0001_initial_schema:base", sql=True)
    down_sql = buf_down.getvalue()

    for table in EXPECTED_TABLES - {"access_policy_state", "state_visits", "report_runs", "report_rows", "background_jobs", "transactional_outbox"}:
        assert f"DROP TABLE {table}" in down_sql, f"Expected 'DROP TABLE {table}' in offline PostgreSQL downgrade SQL"

    # 3. Verify that foreign key dependencies are strictly respected in drop order
    drop_order = re.findall(r"DROP TABLE\s+([a-zA-Z0-9_]+);", down_sql)
    table_indices = {name: idx for idx, name in enumerate(drop_order)}
    for table_name, table in Base.metadata.tables.items():
        if table_name not in table_indices:
            continue
        for fk in table.foreign_keys:
            target_table = fk.column.table.name
            if target_table == table_name or target_table not in table_indices:
                continue
            assert table_indices[table_name] < table_indices[target_table], (
                f"Drop order violation: {table_name} (idx {table_indices[table_name]}) references "
                f"{target_table} (idx {table_indices[target_table]}) but is not dropped before it"
            )

    # 4. Offline downgrade SQL for head -> base
    buf_down_full = io.StringIO()
    with redirect_stdout(buf_down_full):
        command.downgrade(cfg, "head:base", sql=True)
    down_full_sql = buf_down_full.getvalue()
    assert "ix_org_contacts_active" in down_full_sql
    for table in EXPECTED_TABLES:
        assert f"DROP TABLE {table}" in down_full_sql, f"Expected 'DROP TABLE {table}' in offline PostgreSQL full downgrade SQL"


def test_sqlite_migration_with_external_connection(tmp_path):
    """Verify online migration execution when connection is passed via config.attributes."""
    from sqlalchemy import text
    db_file = tmp_path / "test_external_conn.db"
    db_url = f"sqlite:///{db_file}"
    engine = create_engine(db_url)
    cfg = Config(INI_PATH)

    with engine.connect() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
        conn.commit()

        tables = set(inspect(conn).get_table_names())
        assert EXPECTED_TABLES.issubset(tables)

        command.downgrade(cfg, "base")
        conn.commit()

        remaining = set(inspect(conn).get_table_names()) - {"alembic_version"}
        assert not remaining


def test_sqlite_migration_batch_alter_with_referencing_child_foreign_keys(tmp_path):
    """Verify batch_alter_table succeeds on SQLite when child rows reference organization_contacts with FK=ON."""
    from sqlalchemy import text
    db_file = tmp_path / "test_fk_child.db"
    db_url = f"sqlite:///{db_file}"
    engine = create_engine(db_url)
    cfg = get_test_config(db_url)

    # 1. Upgrade to 0001
    command.upgrade(cfg, "0001_initial_schema")

    # 2. Insert records using 0001 schema with referencing foreign keys
    with engine.connect() as conn:
        conn.execute(text("INSERT INTO organizations (id, name, type) VALUES ('org-test', 'ВУЗ', 'university')"))
        conn.execute(text(
            "INSERT INTO organization_contacts (id, organization_id, full_name, position, email, phone, active) "
            "VALUES ('contact-test', 'org-test', 'ФИО', 'Должность', 'test@test.ru', '123', 1)"
        ))
        conn.execute(text(
            "INSERT INTO users (id, keycloak_subject, name, role, permissions, active) "
            "VALUES ('user-test', 'sub-test', 'Имя', 'manager', '[]', 1)"
        ))
        conn.execute(text(
            "INSERT INTO interactions (id, title, organization_id, owner_id, state, contact_id, cycle_label, "
            "visit_id, workflow_version, revision, created_at, updated_at) "
            "VALUES ('ix-test', 'Взаимодействие', 'org-test', 'user-test', 'lead', 'contact-test', '2026', "
            "'v-1', 1, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ))
        conn.commit()

    # 3. Upgrade to 0002 with PRAGMA foreign_keys=ON on external connection
    with engine.connect() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
        conn.commit()

        # Verify contact was altered and fields populated
        row = conn.execute(text(
            "SELECT id, notes, revision, created_at, updated_at, archived_at "
            "FROM organization_contacts WHERE id='contact-test'"
        )).mappings().one()
        assert row["id"] == "contact-test"
        assert row["revision"] == 1
        assert row["archived_at"] is None

        # Verify child row interaction still references contact
        ix_row = conn.execute(text("SELECT contact_id FROM interactions WHERE id='ix-test'")).mappings().one()
        assert ix_row["contact_id"] == "contact-test"

        # 4. Downgrade to 0001 with FK=ON
        command.downgrade(cfg, "0001_initial_schema")
        conn.commit()

        ix_row_v1 = conn.execute(text("SELECT contact_id FROM interactions WHERE id='ix-test'")).mappings().one()
        assert ix_row_v1["contact_id"] == "contact-test"


def test_sqlite_migration_lifecycle_with_seeded_data(tmp_path):
    """Verify downgrade and re-upgrade work cleanly when database contains seeded records."""
    db_file = tmp_path / "test_seeded_lifecycle.db"
    db_url = f"sqlite:///{db_file}"
    cfg = get_test_config(db_url)
    engine = create_engine(db_url)

    # 1. Upgrade
    command.upgrade(cfg, "head")

    # 2. Seed database with real relational records and foreign keys
    with Session(engine) as session:
        seed_database(session)

    # 3. Downgrade should cleanly drop all domain tables despite existing rows
    command.downgrade(cfg, "base")
    remaining = set(inspect(engine).get_table_names()) - {"alembic_version"}
    assert not remaining, f"Tables remained after downgrade with seeded data: {remaining}"

    # 4. Re-upgrade and re-seed
    command.upgrade(cfg, "head")
    with Session(engine) as session:
        seed_database(session)
    re_tables = set(inspect(engine).get_table_names())
    assert EXPECTED_TABLES.issubset(re_tables)


def test_postgresql_live_migration_if_available():
    """Run full live migration against PostgreSQL if an instance is reachable."""
    live_pg_url = os.getenv("TEST_POSTGRES_URL") or os.getenv("DATABASE_URL")
    if not live_pg_url or not live_pg_url.startswith("postgresql"):
        pytest.skip("No live PostgreSQL URL configured; skipping live Postgres test")

    try:
        engine = create_engine(live_pg_url, connect_args={"connect_timeout": 2})
        with engine.connect():
            pass
    except Exception as exc:
        pytest.skip(f"PostgreSQL server not reachable: {exc}")

    cfg = get_test_config(live_pg_url)
    command.upgrade(cfg, "head")

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert EXPECTED_TABLES.issubset(tables)

    command.downgrade(cfg, "base")
    remaining = set(inspect(engine).get_table_names()) - {"alembic_version"}
    assert not remaining


def test_alembic_check_schema_matches_metadata(tmp_path):
    """Verify that Base.metadata and migration head have zero schema drift via alembic check."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    db_file = tmp_path / "test_check.db"
    db_url = f"sqlite:///{db_file}"
    cfg = get_test_config(db_url)

    command.upgrade(cfg, "head")
    # command.check raises AutogenStatusException if new upgrade operations are detected
    command.check(cfg)

    # Explicitly verify column types (including email String(320)) have zero drift
    engine = create_engine(db_url)
    with engine.connect() as conn:
        mc = MigrationContext.configure(conn, opts={"compare_type": True})
        diff = compare_metadata(mc, Base.metadata)
        assert diff == [], f"Detected schema drift with compare_type=True: {diff}"


def test_database_url_resolution_and_precedence(monkeypatch, tmp_path):
    """Verify URL resolution order: explicit config > DATABASE_URL env > app settings."""
    # 1. DATABASE_URL from environment is used when config does not set sqlalchemy.url (db-migrator case)
    env_db = tmp_path / "test_env_url.db"
    env_url = f"sqlite:///{env_db}"
    monkeypatch.setenv("DATABASE_URL", env_url)
    cfg_env = Config(INI_PATH)
    command.upgrade(cfg_env, "head")

    tables_env = set(inspect(create_engine(env_url)).get_table_names())
    assert EXPECTED_TABLES.issubset(tables_env)

    # 2. Explicit config option takes priority over environment variable
    override_db = tmp_path / "test_precedence.db"
    override_url = f"sqlite:///{override_db}"
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://unreachable.host:5432/fake_db")
    cfg_override = get_test_config(override_url)
    command.upgrade(cfg_override, "head")

    tables_override = set(inspect(create_engine(override_url)).get_table_names())
    assert EXPECTED_TABLES.issubset(tables_override)


def test_organization_contact_lifecycle_and_active_filtering(tmp_path):
    """Verify OrganizationContact audit fields, revisioning, archiving, and active filtering."""
    from sqlalchemy import select
    from app.models import Organization, OrganizationContact, utcnow

    db_file = tmp_path / "test_contacts.db"
    db_url = f"sqlite:///{db_file}"
    cfg = get_test_config(db_url)
    engine = create_engine(db_url)

    # 1. Migrate database to head
    command.upgrade(cfg, "head")

    with Session(engine) as session:
        # Create organization
        org = Organization(id="org-c-test", name="Тестовый Университет", type="university")
        session.add(org)
        session.flush()

        # Create contact with exact RFC 5321 maximum length email (320 chars: 64 local + 1 @ + 255 domain)
        email_320 = "a" * 64 + "@" + "d" * (320 - 65 - 3) + ".ru"
        assert len(email_320) == 320

        contact1 = OrganizationContact(
            organization_id=org.id,
            full_name="Иванов Иван Иванович",
            position="Декан факультета",
            email=email_320,
            phone="+7 (999) 111-22-33",
            active=True,
            notes="Первичный контакт для пилотного проекта",
        )
        session.add(contact1)

        contact2 = OrganizationContact(
            organization_id=org.id,
            full_name="Петров Петр Петрович",
            position="Заведующий кафедрой",
            email="petrov@university.ru",
            phone="+7 (999) 222-33-44",
            active=True,
        )
        session.add(contact2)
        session.commit()

        # 2. Check defaults and fields
        assert contact1.revision == 1
        assert contact1.notes == "Первичный контакт для пилотного проекта"
        assert contact1.created_at is not None
        assert contact1.updated_at is not None
        assert contact1.archived_at is None
        assert contact1.email == email_320
        assert len(contact1.email) == 320

        # 3. Update revision and notes
        prev_updated_at = contact1.updated_at
        contact1.notes = "Обновлены контактные данные после встречи"
        contact1.revision += 1
        contact1.updated_at = utcnow()
        session.commit()

        c1_reloaded = session.get(OrganizationContact, contact1.id)
        assert c1_reloaded.revision == 2
        assert c1_reloaded.notes == "Обновлены контактные данные после встречи"
        assert c1_reloaded.updated_at >= prev_updated_at

        # 4. Filter active contacts using ix_org_contacts_active index pattern
        from sqlalchemy import text
        plan = session.execute(
            text(
                "EXPLAIN QUERY PLAN SELECT id FROM organization_contacts "
                "WHERE organization_id = :org_id AND archived_at IS NULL"
            ),
            {"org_id": org.id},
        ).fetchall()
        assert "ix_org_contacts_active" in " ".join(str(r) for r in plan)

        active_contacts = session.scalars(
            select(OrganizationContact)
            .where(
                OrganizationContact.organization_id == org.id,
                OrganizationContact.archived_at.is_(None),
            )
            .order_by(OrganizationContact.full_name)
        ).all()
        assert len(active_contacts) == 2

        # 5. Archive contact1
        contact1.archived_at = utcnow()
        session.commit()

        # Filter active contacts again - only contact2 is active
        active_after_archive = session.scalars(
            select(OrganizationContact)
            .where(
                OrganizationContact.organization_id == org.id,
                OrganizationContact.archived_at.is_(None),
            )
            .order_by(OrganizationContact.full_name)
        ).all()
        assert len(active_after_archive) == 1
        assert active_after_archive[0].id == contact2.id

        # All contacts include archived
        all_contacts = session.scalars(
            select(OrganizationContact)
            .where(OrganizationContact.organization_id == org.id)
            .order_by(OrganizationContact.full_name)
        ).all()
        assert len(all_contacts) == 2
        archived = [c for c in all_contacts if c.archived_at is not None]
        assert len(archived) == 1
        assert archived[0].id == contact1.id

        # Verify index utilization for archived queries
        plan_archived = session.execute(
            text(
                "EXPLAIN QUERY PLAN SELECT id FROM organization_contacts "
                "WHERE organization_id = :org_id AND archived_at IS NOT NULL"
            ),
            {"org_id": org.id},
        ).fetchall()
        assert "ix_org_contacts_active" in " ".join(str(r) for r in plan_archived)

        # 6. Unarchive contact1 and verify it returns to active set
        contact1.archived_at = None
        session.commit()
        active_after_restore = session.scalars(
            select(OrganizationContact)
            .where(
                OrganizationContact.organization_id == org.id,
                OrganizationContact.archived_at.is_(None),
            )
        ).all()
        assert len(active_after_restore) == 2


def test_upgrade_downgrade_with_existing_contact_data(tmp_path):
    """Verify upgrade and downgrade on database with pre-existing contact records."""
    import sqlalchemy as sa
    db_file = tmp_path / "test_contact_migration_data.db"
    db_url = f"sqlite:///{db_file}"
    cfg = get_test_config(db_url)
    engine = create_engine(db_url)

    # 1. Upgrade to 0001
    command.upgrade(cfg, "0001_initial_schema")

    # Insert raw contact row using 0001 schema
    with engine.connect() as conn:
        conn.execute(sa.text(
            "INSERT INTO organizations (id, name, type) VALUES ('org-pre', 'Старый ВУЗ', 'university')"
        ))
        conn.execute(sa.text(
            "INSERT INTO organization_contacts (id, organization_id, full_name, position, email, phone, active) "
            "VALUES ('c-pre-1', 'org-pre', 'Старый Контакт', 'Ректор', 'rector@old-univ.ru', '+79990000000', 1)"
        ))
        conn.commit()

    # 2. Upgrade to 0002_normalize_contacts
    command.upgrade(cfg, "head")

    # Verify existing row was populated with server defaults
    with engine.connect() as conn:
        stmt = sa.text(
            "SELECT id, full_name, email, notes, revision, created_at, updated_at, archived_at "
            "FROM organization_contacts WHERE id='c-pre-1'"
        )
        row = conn.execute(stmt).mappings().one()
        assert row["id"] == "c-pre-1"
        assert row["full_name"] == "Старый Контакт"
        assert row["email"] == "rector@old-univ.ru"
        assert row["notes"] is None
        assert row["revision"] == 1
        assert row["created_at"] is not None
        assert row["updated_at"] is not None
        assert row["archived_at"] is None

    # 3. Downgrade back to 0001
    command.downgrade(cfg, "0001_initial_schema")

    with engine.connect() as conn:
        stmt_v1 = sa.text("SELECT id, full_name, email FROM organization_contacts WHERE id='c-pre-1'")
        row = conn.execute(stmt_v1).mappings().one()
        assert row["id"] == "c-pre-1"
        assert row["full_name"] == "Старый Контакт"
        assert row["email"] == "rector@old-univ.ru"
