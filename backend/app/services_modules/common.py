import json
from datetime import timezone

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from ..models import AccessPolicyState, OrganizationAccess, User, utcnow


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def iso(value):
    return aware(value).isoformat().replace("+00:00", "Z") if value else None


def _json_safe(obj):
    return json.loads(json.dumps(obj, default=str, ensure_ascii=False))


@event.listens_for(Session, "after_transaction_end")
def _authz_epoch_on_transaction_end(session: Session, transaction):
    if transaction.parent is not None:
        return
    session.info.pop("_authz_epoch_bumped", None)
    session.info.pop("_in_bump_authz_epoch", None)


@event.listens_for(Session, "before_flush")
def _authz_epoch_before_flush(session: Session, flush_context, instances):
    if (
        session.info.get("_authz_epoch_bumped")
        or session.info.get("_in_bump_authz_epoch")
    ):
        return
    should_bump = False
    flushing_new_del = (
        (session.new | session.deleted)
        if instances is None
        else [obj for obj in instances if obj in session.new or obj in session.deleted]
    )
    for obj in flushing_new_del:
        if isinstance(obj, (OrganizationAccess, User)):
            should_bump = True
            break
    if not should_bump:
        flushing_dirty = (
            session.dirty
            if instances is None
            else [obj for obj in instances if obj in session.dirty]
        )
        for obj in flushing_dirty:
            if isinstance(obj, OrganizationAccess):
                insp = inspect(obj)
                for attr in ("can_create", "read_all"):
                    if attr in insp.attrs and insp.attrs[attr].history.has_changes():
                        should_bump = True
                        break
                if should_bump:
                    break
            elif isinstance(obj, User):
                insp = inspect(obj)
                for attr in ("role", "team_id", "active", "permissions"):
                    if attr in insp.attrs and insp.attrs[attr].history.has_changes():
                        should_bump = True
                        break
                if should_bump:
                    break
    if should_bump:
        now = utcnow()
        st = None
        for obj in session.new:
            if isinstance(obj, AccessPolicyState):
                st = obj
                break
        if st is not None:
            st.epoch += 1
            st.updated_at = now
        else:
            st = session.get(AccessPolicyState, 1)
            if st is None:
                st = AccessPolicyState(singleton_id=1, epoch=2, updated_at=now)
                session.add(st)
            else:
                st.epoch = AccessPolicyState.epoch + 1
                st.updated_at = now
        session.info["_authz_epoch_bumped"] = True
