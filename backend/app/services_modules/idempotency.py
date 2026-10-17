import hashlib
import json

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..errors import APIError
from ..models import CommandResult
from .rbac import scoped_interaction


def begin_command(db, user, operation, key, payload):
    if not key or not key.strip() or len(key) > 200:
        raise APIError("VALIDATION_ERROR", "Нужен непустой заголовок Idempotency-Key (до 200 символов).")
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                       separators=(",", ":")).encode()).hexdigest()
    criteria = (CommandResult.user_id == user.id, CommandResult.operation == operation, CommandResult.key == key)
    saved = db.scalar(select(CommandResult).where(*criteria))
    if not saved:
        saved = CommandResult(user_id=user.id, operation=operation, key=key, payload_hash=digest)
        db.add(saved)
        try:
            # The unique key reserves this command inside the same transaction as its business effect.
            db.flush()
            return saved, None
        except IntegrityError:
            db.rollback()
            saved = db.scalar(select(CommandResult).where(*criteria))
            if not saved:
                raise APIError("IDEMPOTENCY_CONFLICT", "Команда выполняется; повторите запрос.", 409)
    if saved.payload_hash != digest:
        raise APIError("IDEMPOTENCY_CONFLICT", "Этот ключ уже использован с другим содержимым.", 409)
    if saved.resource_id:
        scoped_interaction(db, user, saved.resource_id)
    if saved.response is None:
        raise APIError("IDEMPOTENCY_CONFLICT", "Команда ещё выполняется.", 409)
    return saved, saved.response


def finish_command(db, saved, response, resource_id):
    saved.response, saved.resource_id = response, resource_id
    db.commit()
    return response
