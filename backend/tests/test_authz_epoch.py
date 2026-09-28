"""Tests for Global Access Policy Epoch (TASK-O02).

Verifies:
1. Singleton model AccessPolicyState initialization and retrieval via get_authz_epoch().
2. Atomic increment of authz_epoch via bump_authz_epoch().
3. Automatic epoch bump on interaction reassignment (services.assign).
4. Automatic epoch bump on OrganizationAccess mutations (grant, modify, revoke).
5. Automatic epoch bump on User role, team_id, and active status mutations.
6. Verification that non-access mutations (e.g., user name, comments) do NOT bump the epoch.
7. 152-FZ isolation invariant: stale epoch detection for asynchronous operations.
8. Alembic migration 0003_authz_epoch singleton seeding and lifecycle.
"""
from pathlib import Path
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.errors import APIError
from app.models import AccessPolicyState, Base, Interaction, OrganizationAccess, User
from app.schemas import AssignmentCommand
from app.services import (
    assign,
    bump_authz_epoch,
    check_authz_epoch,
    ensure_authz_epoch_valid,
    get_authz_epoch,
    revoke_organization_access,
    set_organization_access,
    update_user_access,
)

BACKEND_DIR = Path(__file__).resolve().parents[1]
INI_PATH = str(BACKEND_DIR / "alembic.ini")


def test_authz_epoch_singleton_initialization_and_reading(tmp_path):
    """Verify get_authz_epoch creates singleton row with epoch=1 on unseeded DB and reads idempotently."""
    db_file = tmp_path / "test_init.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        # Table exists but has zero rows initially
        assert session.scalar(select(AccessPolicyState.singleton_id)) is None

        # First call creates singleton row with epoch=1
        epoch = get_authz_epoch(session)
        assert epoch == 1
        session.commit()

    with Session(engine) as session:
        # Verification that singleton exists with singleton_id=1, epoch=1
        state = session.get(AccessPolicyState, 1)
        assert state is not None
        assert state.singleton_id == 1
        assert state.epoch == 1
        assert state.updated_at is not None

        # Subsequent call returns same epoch without modifications
        assert get_authz_epoch(session) == 1


def test_bump_authz_epoch_atomic_increment(tmp_path):
    """Verify bump_authz_epoch increments epoch and updates updated_at."""
    db_file = tmp_path / "test_bump.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        e1 = get_authz_epoch(session)
        assert e1 == 1

        state_before = session.get(AccessPolicyState, 1)
        updated_before = state_before.updated_at

        # First bump
        e2 = bump_authz_epoch(session)
        assert e2 == 2
        assert get_authz_epoch(session) == 2
        session.commit()

    with Session(engine) as session:
        # Check persistence across sessions
        state = session.get(AccessPolicyState, 1)
        assert state.epoch == 2
        assert state.updated_at >= updated_before

        # Second bump
        e3 = bump_authz_epoch(session)
        assert e3 == 3
        assert get_authz_epoch(session) == 3
        session.commit()

    # Also test bump_authz_epoch on empty table
    db_file_empty = tmp_path / "test_bump_empty.db"
    engine_empty = create_engine(f"sqlite:///{db_file_empty}")
    Base.metadata.create_all(engine_empty)
    with Session(engine_empty) as session:
        e_first = bump_authz_epoch(session)
        assert e_first == 2
        assert get_authz_epoch(session) == 2


def test_assign_bumps_authz_epoch(app):
    """Verify that interaction reassignment (assign) bumps the authorization epoch."""
    with app.state.session_factory() as session:
        initial_epoch = get_authz_epoch(session)
        assert initial_epoch >= 1

        supervisor = session.get(User, "supervisor")
        assert supervisor is not None

        item = session.get(Interaction, "ix-1")
        assert item.owner_id == "manager-a"
        cur_rev = item.revision

        # Reassign to manager-b
        body = AssignmentCommand(owner_id="manager-b", expected_revision=cur_rev, reason="Перевод заявки")
        assign(session, supervisor, "ix-1", body, "key-assign-epoch-1")

        # Reload interaction and verify owner changed
        session.expire_all()
        item_updated = session.get(Interaction, "ix-1")
        assert item_updated.owner_id == "manager-b"

        # Verify epoch bumped
        new_epoch = get_authz_epoch(session)
        assert new_epoch == initial_epoch + 1

        # Idempotent replay must NOT bump epoch again
        replay = assign(session, supervisor, "ix-1", body, "key-assign-epoch-1")
        assert replay["owner_id"] == "manager-b"
        assert get_authz_epoch(session) == new_epoch


def test_assign_via_api_client_bumps_epoch(client, app):
    """Verify HTTP POST /api/v1/interactions/{id}/assign increments authz_epoch."""
    with app.state.session_factory() as session:
        epoch_before = get_authz_epoch(session)
        item = session.get(Interaction, "ix-2")
        expected_rev = item.revision

    resp = client.post(
        "/api/v1/interactions/ix-2/assignments",
        headers={
            "X-Demo-User": "supervisor",
            "Idempotency-Key": "idemp-http-assign-1",
        },
        json={
            "owner_id": "manager-b",
            "expected_revision": expected_rev,
            "reason": "Смена ответственного менеджера",
        },
    )
    assert resp.status_code == 200

    with app.state.session_factory() as session:
        epoch_after = get_authz_epoch(session)
        assert epoch_after == epoch_before + 1


def test_organization_access_mutations_bump_epoch(app):
    """Verify adding, modifying, and revoking OrganizationAccess bumps the epoch."""
    with app.state.session_factory() as session:
        epoch_0 = get_authz_epoch(session)

        # 1. Add new grant directly
        grant = OrganizationAccess(
            user_id="manager-a",
            organization_id="org-2",
            can_create=True,
            read_all=False,
        )
        session.add(grant)
        session.commit()

        epoch_1 = get_authz_epoch(session)
        assert epoch_1 == epoch_0 + 1

        # 2. Modify existing grant
        grant = session.get(OrganizationAccess, ("manager-a", "org-2"))
        grant.read_all = True
        session.commit()

        epoch_2 = get_authz_epoch(session)
        assert epoch_2 == epoch_1 + 1

        # 3. Delete grant directly
        grant = session.get(OrganizationAccess, ("manager-a", "org-2"))
        session.delete(grant)
        session.commit()

        epoch_3 = get_authz_epoch(session)
        assert epoch_3 == epoch_2 + 1

        # 4. Helper set_organization_access
        set_organization_access(session, "manager-b", "org-1", can_create=True, read_all=True)
        session.commit()

        epoch_4 = get_authz_epoch(session)
        assert epoch_4 == epoch_3 + 1

        # 5. Helper revoke_organization_access
        revoked = revoke_organization_access(session, "manager-b", "org-1")
        assert revoked is True
        session.commit()

        epoch_5 = get_authz_epoch(session)
        assert epoch_5 == epoch_4 + 1


def test_user_role_and_team_and_active_mutations_bump_epoch(app):
    """Verify changes to User role, team_id, and active status bump the epoch, while unrelated changes do not."""
    with app.state.session_factory() as session:
        epoch_0 = get_authz_epoch(session)

        user = session.get(User, "manager-a")

        # 1. Change role
        user.role = "supervisor"
        session.commit()
        epoch_1 = get_authz_epoch(session)
        assert epoch_1 == epoch_0 + 1

        # 2. Change team_id
        user.team_id = "south"
        session.commit()
        epoch_2 = get_authz_epoch(session)
        assert epoch_2 == epoch_1 + 1

        # 3. Change active status
        user.active = False
        session.commit()
        epoch_3 = get_authz_epoch(session)
        assert epoch_3 == epoch_2 + 1

        # 4. Unrelated attribute change: name
        user.name = "Обновленное Имя Пользователя"
        session.commit()
        epoch_4 = get_authz_epoch(session)
        assert epoch_4 == epoch_3, "Unrelated user name change must NOT bump authz_epoch"

        # 5. Helper update_user_access
        update_user_access(session, "manager-a", role="manager", team_id="north", active=True)
        session.commit()
        epoch_5 = get_authz_epoch(session)
        assert epoch_5 == epoch_4 + 1


def test_152_fz_isolation_and_stale_epoch_detection(app):
    """Verify 152-FZ security invariant: detection and rejection of stale authorization epoch."""
    with app.state.session_factory() as session:
        # Background worker receives task with captured epoch
        captured_epoch = get_authz_epoch(session)

        # Worker verifies validity before execution
        assert check_authz_epoch(session, captured_epoch) is True
        ensure_authz_epoch_valid(session, captured_epoch)

        # Concurrently, administrator revokes access or alters user role
        bump_authz_epoch(session)
        session.commit()

        # Worker detects stale authorization context
        assert check_authz_epoch(session, captured_epoch) is False

        with pytest.raises(APIError) as exc_info:
            ensure_authz_epoch_valid(session, captured_epoch)

        err = exc_info.value
        assert err.code == "REPORT_SCOPE_CHANGED"
        assert err.status_code == 403
        assert f"эпоха {captured_epoch}" in err.message


def test_alembic_migration_seeds_singleton_epoch(tmp_path):
    """Verify that Alembic migration 0003_authz_epoch creates table and seeds singleton (1, 1)."""
    db_file = tmp_path / "test_migration_seed.db"
    db_url = f"sqlite:///{db_file}"
    cfg = Config(INI_PATH)
    cfg.set_main_option("sqlalchemy.url", db_url)

    # Run upgrade head
    command.upgrade(cfg, "head")

    engine = create_engine(db_url)
    with engine.connect() as conn:
        row = conn.execute(text("SELECT singleton_id, epoch FROM access_policy_state")).mappings().one()
        assert row["singleton_id"] == 1
        assert row["epoch"] == 1

    with Session(engine) as session:
        assert get_authz_epoch(session) == 1


def test_user_permissions_mutation_bumps_epoch(app):
    """Verify updating User.permissions directly or via update_user_access increments epoch."""
    with app.state.session_factory() as session:
        epoch_0 = get_authz_epoch(session)
        user = session.get(User, "manager-b")

        # 1. Direct permissions change
        user.permissions = ["interactions.assign"]
        session.commit()
        epoch_1 = get_authz_epoch(session)
        assert epoch_1 == epoch_0 + 1

        # 2. Via update_user_access helper
        update_user_access(session, "manager-b", permissions=["interactions.assign", "users.manage"])
        session.commit()
        epoch_2 = get_authz_epoch(session)
        assert epoch_2 == epoch_1 + 1


def test_unflushed_state_and_user_creation_in_same_session(tmp_path):
    """Verify adding AccessPolicyState and User in the same session does not crash with UNIQUE constraint error."""
    db_file = tmp_path / "test_unflushed_combo.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        # Add singleton state and a new user together in session.new
        session.add(AccessPolicyState(singleton_id=1, epoch=1))
        session.add(User(id="new-manager", keycloak_subject="subj-new", name="New User", role="manager"))
        # Commit flushes both; before_flush must detect pending AccessPolicyState in session.new
        session.commit()

    with Session(engine) as session:
        # Initial epoch 1 bumped to 2 due to user creation in the same transaction
        assert get_authz_epoch(session) == 2


def test_bump_authz_epoch_with_unflushed_state(tmp_path):
    """Verify bump_authz_epoch safely handles pending AccessPolicyState in session.new."""
    db_file = tmp_path / "test_bump_unflushed.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(AccessPolicyState(singleton_id=1, epoch=1))
        session.add(User(id="u1", keycloak_subject="s1", name="U1", role="manager"))
        # Call bump_authz_epoch on session before committing
        e = bump_authz_epoch(session)
        assert e == 2
        session.commit()

    with Session(engine) as session:
        assert get_authz_epoch(session) == 2


def test_user_mutation_and_bump_authz_epoch_single_increment(tmp_path):
    """Verify that combining a dirty User mutation with bump_authz_epoch increments epoch by exactly 1."""
    db_file = tmp_path / "test_user_single_inc.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(AccessPolicyState(singleton_id=1, epoch=1))
        session.add(User(id="u1", keycloak_subject="s1", name="U1", role="manager"))
        session.commit()

    with Session(engine) as session:
        initial = get_authz_epoch(session)
        u = session.get(User, "u1")
        u.role = "supervisor"
        # User is dirty; bump_authz_epoch must not cause double-increment during autoflush
        bumped = bump_authz_epoch(session)
        assert bumped == initial + 1
        session.commit()

    with Session(engine) as session:
        assert get_authz_epoch(session) == initial + 1


def test_no_op_organization_access_does_not_bump_epoch(tmp_path):
    """Verify that updating OrganizationAccess with unchanged permissions does not bump the epoch."""
    db_file = tmp_path / "test_noop_grant.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(AccessPolicyState(singleton_id=1, epoch=1))
        grant = OrganizationAccess(user_id="u1", organization_id="org-1", can_create=True, read_all=False)
        session.add(grant)
        session.commit()
        epoch_before = get_authz_epoch(session)

    with Session(engine) as session:
        set_organization_access(session, "u1", "org-1", can_create=True, read_all=False)
        session.commit()
        epoch_after = get_authz_epoch(session)
        assert epoch_after == epoch_before, "Unchanged access grant must not bump authz_epoch"


def test_multiple_bump_authz_epoch_in_same_transaction(tmp_path):
    """Verify that multiple sequential bump_authz_epoch calls within the same transaction increment atomically."""
    db_file = tmp_path / "test_multi_bump.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(AccessPolicyState(singleton_id=1, epoch=1))
        session.commit()

    with Session(engine) as session:
        e1 = bump_authz_epoch(session)
        e2 = bump_authz_epoch(session)
        assert e1 == 2
        assert e2 == 3
        session.commit()

    with Session(engine) as session:
        assert get_authz_epoch(session) == 3


def test_transaction_rollback_reverts_bumped_epoch(tmp_path):
    """Verify that transaction rollback reverts bumped epoch and clears session context flags."""
    db_file = tmp_path / "test_rollback.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(AccessPolicyState(singleton_id=1, epoch=1))
        session.commit()

    with Session(engine) as session:
        assert get_authz_epoch(session) == 1
        bump_authz_epoch(session)
        assert get_authz_epoch(session) == 2
        session.rollback()

    with Session(engine) as session:
        assert get_authz_epoch(session) == 1


def test_uninitialized_db_user_creation_with_autoflush_false(tmp_path):
    """Verify creating a user on unseeded DB with autoflush=False and get_authz_epoch bumps epoch on commit."""
    db_file = tmp_path / "test_uninit_user.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)

    with Session(engine, autoflush=False) as session:
        # Table access_policy_state has 0 rows initially
        user = User(id="u-fresh", keycloak_subject="s-fresh", name="Fresh User", role="manager")
        session.add(user)
        # Calling get_authz_epoch creates singleton state without prematurely flushing user or losing the bump
        epoch_pending = get_authz_epoch(session)
        assert epoch_pending == 1
        assert user in session.new
        session.commit()

    with Session(engine) as session:
        # User creation bumped epoch from 1 to 2
        assert get_authz_epoch(session) == 2


def test_selective_flush_does_not_prematurely_bump_unrelated_pending_user(tmp_path):
    """Verify selective flush (objects=[...]) does not trigger epoch bump for unflushed User."""
    from app.models import Comment
    db_file = tmp_path / "test_selective_flush.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(AccessPolicyState(singleton_id=1, epoch=1))
        session.commit()

    with Session(engine, autoflush=False) as session:
        user = User(id="u-pending", keycloak_subject="s-pending", name="Pending User", role="manager")
        session.add(user)

        # Flushed an unrelated comment or state selectively
        st = session.get(AccessPolicyState, 1)
        session.flush(objects=[st])

        # User is still unflushed in session.new; epoch must NOT have bumped yet
        assert user in session.new
        assert get_authz_epoch(session) == 1

        # Now commit flushes User and bumps epoch
        session.commit()

    with Session(engine) as session:
        assert get_authz_epoch(session) == 2


def test_bump_authz_epoch_uses_identity_map_without_redundant_select(tmp_path):
    """Verify bump_authz_epoch correctly checks identity map and increments epoch atomically."""
    db_file = tmp_path / "test_idmap_bump.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(AccessPolicyState(singleton_id=1, epoch=1))
        session.commit()

    # Session where AccessPolicyState is NOT in identity map
    with Session(engine) as session:
        key = session.identity_key(AccessPolicyState, 1)
        assert key not in session.identity_map

        new_epoch = bump_authz_epoch(session)
        assert new_epoch == 2
        session.commit()

    with Session(engine) as session:
        assert get_authz_epoch(session) == 2



