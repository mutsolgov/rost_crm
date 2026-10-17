from sqlalchemy import false, or_, select, update
from sqlalchemy.orm import Session

from ..errors import APIError
from ..models import AccessPolicyState, Interaction, Organization, OrganizationAccess, User, utcnow
from .common import aware, iso

__all__ = [
    "allowed_owner",
    "aware",
    "bump_authz_epoch",
    "check_authz_epoch",
    "ensure_authz_epoch_valid",
    "get_authz_epoch",
    "has_organization_access",
    "iso",
    "permissions",
    "require_permission",
    "revoke_organization_access",
    "scope_clause",
    "scoped_interaction",
    "set_organization_access",
    "update_user_access",
    "visible_organization_ids",
]


def permissions(user):
    defaults = {
        "manager": {"interactions.create", "interactions.transition", "interactions.comment",
                    "interactions.edit", "interactions.write", "reports.read"},
        "supervisor": {"interactions.create", "interactions.transition", "interactions.comment",
                       "interactions.assign", "interactions.edit", "interactions.write", "reports.read",
                       "organizations.create", "integrations.manage"},
        "administrator": {"workflow.manage", "workflow.global_migrate", "users.manage", "organizations.create", "reports.read",
                          "integrations.manage"},
    }
    return sorted(defaults.get(user.role, set()) | set(user.permissions or []))


def require_permission(user, name):
    if name not in permissions(user):
        raise APIError("FORBIDDEN", "Недостаточно прав для этого действия.", 403)


def get_authz_epoch(db: Session) -> int:
    st = None
    for obj in db.new:
        if isinstance(obj, AccessPolicyState):
            st = obj
            break
    if st is None:
        st = db.get(AccessPolicyState, 1)
    if st is None:
        st = AccessPolicyState(singleton_id=1, epoch=1, updated_at=utcnow())
        db.add(st)
        db.flush(objects=[st])
    return int(st.epoch)


def bump_authz_epoch(db: Session) -> int:
    now = utcnow()
    db.info["_in_bump_authz_epoch"] = True
    try:
        st_new = None
        for obj in db.new:
            if isinstance(obj, AccessPolicyState):
                st_new = obj
                break
        if st_new is not None:
            st_new.epoch += 1
            st_new.updated_at = now
            db.info["_authz_epoch_bumped"] = True
            db.flush(objects=[st_new])
            return int(st_new.epoch)

        db.flush()

        res = db.execute(
            update(AccessPolicyState)
            .where(AccessPolicyState.singleton_id == 1)
            .values(epoch=AccessPolicyState.epoch + 1, updated_at=now)
        )
        if res.rowcount == 0:
            state = AccessPolicyState(singleton_id=1, epoch=2, updated_at=now)
            db.add(state)
            db.info["_authz_epoch_bumped"] = True
            db.flush(objects=[state])
            return 2

        key = db.identity_key(AccessPolicyState, 1)
        state = db.identity_map.get(key)
        if state is not None:
            db.expire(state)
        db.info["_authz_epoch_bumped"] = True
        epoch = db.scalar(select(AccessPolicyState.epoch).where(AccessPolicyState.singleton_id == 1))
        return int(epoch)
    finally:
        db.info.pop("_in_bump_authz_epoch", None)


def check_authz_epoch(db: Session, request_authz_epoch: int) -> bool:
    return get_authz_epoch(db) == request_authz_epoch


def ensure_authz_epoch_valid(db: Session, request_authz_epoch: int) -> None:
    current = get_authz_epoch(db)
    if current != request_authz_epoch:
        raise APIError(
            "REPORT_SCOPE_CHANGED",
            f"Контекст прав доступа изменился (эпоха {request_authz_epoch} != {current}).",
            403,
        )


def set_organization_access(
    db: Session,
    user_id: str,
    organization_id: str,
    *,
    can_create: bool = False,
    read_all: bool = False,
) -> OrganizationAccess:
    grant = db.get(OrganizationAccess, (user_id, organization_id))
    if grant is None:
        grant = OrganizationAccess(
            user_id=user_id,
            organization_id=organization_id,
            can_create=can_create,
            read_all=read_all,
        )
        db.add(grant)
    else:
        grant.can_create = can_create
        grant.read_all = read_all
    db.flush()
    return grant


def revoke_organization_access(
    db: Session,
    user_id: str,
    organization_id: str,
) -> bool:
    grant = db.get(OrganizationAccess, (user_id, organization_id))
    if grant is not None:
        db.delete(grant)
        db.flush()
        return True
    return False


def update_user_access(
    db: Session,
    user_id: str,
    *,
    role: str | None = None,
    team_id: str | None = None,
    active: bool | None = None,
    permissions: list | None = None,
) -> User:
    user = db.get(User, user_id)
    if not user:
        raise APIError("NOT_FOUND", "Пользователь не найден.", 404)
    if role is not None:
        user.role = role
    if team_id is not None:
        user.team_id = team_id
    if active is not None:
        user.active = active
    if permissions is not None:
        user.permissions = permissions
    db.flush()
    return user


def scope_clause(user):
    granted = select(OrganizationAccess.organization_id).where(
        OrganizationAccess.user_id == user.id, OrganizationAccess.read_all.is_(True))
    own = Interaction.owner_id == user.id if user.role == "manager" else false()
    if user.role == "supervisor" and user.team_id:
        team_mgr_ids = select(User.id).where(User.team_id == user.team_id)
        team = or_(Interaction.team_id == user.team_id, Interaction.owner_id.in_(team_mgr_ids))
    else:
        team = false()
    return or_(own, team, Interaction.organization_id.in_(granted))


def scoped_interaction(db, user, interaction_id):
    interaction = db.scalar(select(Interaction).where(Interaction.id == interaction_id, scope_clause(user)))
    if not interaction:
        raise APIError("NOT_FOUND", "Взаимодействие не найдено.", 404)
    return interaction


def visible_organization_ids(db, user):
    if user.role in ("administrator", "admin"):
        return set(db.scalars(select(Organization.id)))
    scoped = set(db.scalars(select(Interaction.organization_id).where(scope_clause(user))))
    granted = set(db.scalars(select(OrganizationAccess.organization_id).where(
        OrganizationAccess.user_id == user.id,
        or_(OrganizationAccess.can_create.is_(True), OrganizationAccess.read_all.is_(True)))))
    owned = set()
    if user.role == "manager":
        owned = set(db.scalars(select(Organization.id).where(Organization.owner_id == user.id)))
    elif user.role == "supervisor":
        if user.team_id:
            owned = set(db.scalars(select(Organization.id).join(User, Organization.owner_id == User.id).where(User.team_id == user.team_id)))
            team_mgr_grants = set(db.scalars(
                select(OrganizationAccess.organization_id)
                .join(User, OrganizationAccess.user_id == User.id)
                .where(
                    User.team_id == user.team_id,
                    or_(OrganizationAccess.can_create.is_(True), OrganizationAccess.read_all.is_(True))
                )
            ))
            granted |= team_mgr_grants
        owned |= set(db.scalars(select(Organization.id).where(Organization.owner_id == user.id)))
    return scoped | granted | owned


def has_organization_access(db, user, org_id: str) -> bool:
    if user.role in ("administrator", "admin"):
        return True
    org = db.get(Organization, org_id)
    if org and org.owner_id == user.id:
        return True
    if org and user.role == "supervisor" and org.owner_id:
        org_owner = db.get(User, org.owner_id)
        if org_owner and org_owner.team_id and org_owner.team_id == user.team_id:
            return True
    grant = db.get(OrganizationAccess, (user.id, org_id))
    if grant and (grant.read_all or grant.can_create):
        return True
    return org_id in visible_organization_ids(db, user)


def allowed_owner(db, user, owner_id, *, creation=False):
    owner = db.get(User, owner_id)
    if not owner or not owner.active or owner.role != "manager":
        raise APIError("VALIDATION_ERROR", "Выберите активного менеджера.")
    if user.role == "manager":
        if not creation or owner.id != user.id:
            raise APIError("FORBIDDEN", "Менеджер может создать карточку только на себя.", 403)
    elif user.role == "supervisor":
        if not user.team_id or owner.team_id != user.team_id:
            raise APIError("FORBIDDEN", "Назначение разрешено только внутри своей команды.", 403)
    elif user.role == "administrator":
        require_permission(user, "interactions.assign")
    else:
        raise APIError("FORBIDDEN", "Назначение запрещено.", 403)
    return owner
