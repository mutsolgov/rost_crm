# Handoff Report: Backend Architecture, Ponytail Revision, CAS Concurrency & Idempotency-Key

## 1. Observation
- Code inspection across `backend/app/` (`main.py`, `schemas.py`, `services.py`, `models.py`, `workflow.py`, `auth.py`, `db.py`, `seed.py`, `importer.py`, `reports_export.py`, `integrations/`):
  1. `backend/app/services.py:894-899`: `commit_workflow_migration` mutated interaction models directly via in-memory assignment:
     ```python
     item.workflow_version = to_version
     item.state = new_state
     item.revision = new_revision
     item.updated_at = now
     if new_state in to_terminal:
         item.closed_at = now
     ```
     This bypassed the atomic database CAS check implemented in `cas(db, item, expected_revision, ...)`.
  2. `backend/app/services.py:243-252`: `cas` helper was implemented as:
     ```python
     def cas(db, item, expected_revision, **values):
         result = db.execute(update(Interaction).where(Interaction.id == item.id,
                            Interaction.revision == expected_revision).values(
                                revision=expected_revision + 1, **values),
                            execution_options={"synchronize_session": False})
         if result.rowcount != 1:
             db.rollback()
             raise APIError("REVISION_CONFLICT", "Карточка изменена. Обновите данные.", 409)
         db.refresh(item)
     ```
     This strictly checks `Interaction.revision == expected_revision`, increments `revision = expected_revision + 1`, and on mismatch triggers `db.rollback()` followed by HTTP 409 `REVISION_CONFLICT`.
  3. Other mutating functions (`update_interaction`, `transition`, `assign`, `add_comment`) already called `cas(db, item, body.expected_revision, ...)` with Pydantic schema validation `expected_revision: int = Field(ge=1)`.
  4. `backend/app/services.py:209-234`: `begin_command` validates `Idempotency-Key`:
     ```python
     if not key or not key.strip() or len(key) > 200:
         raise APIError("VALIDATION_ERROR", "Нужен непустой заголовок Idempotency-Key (до 200 символов).")
     ```
     Subsequent calls with identical key and payload return `saved.response` immediately without repeating any mutations or side effects.
  5. Unused imports identified by AST analysis:
     - `main.py`: `JSONResponse`, `Response`, `ImportCommitRequest`, `interaction_dict`, `WORKFLOW`.
     - `services.py`: `datetime`, `TRANSITIONS`, `get_workflow`.
     - `auth.py`: `get_settings`.
     - `db.py`: `Session`.
     - `seed.py`: `select`.
     - `importer.py`: `func`.
     - `integrations/factory.py`: `TYPE_CHECKING`.
     - `integrations/service.py`: `or_`.
  6. Verification runs:
     - Full test suite: `cd backend && .venv/bin/python -m pytest tests/ -v` -> `139 passed, 2 warnings in 78.93s`.
     - Specification oracles: `python3 docs/checks/verify_infra.py && python3 docs/checks/verify_workflow.py && python3 docs/checks/verify_reports.py && python3 docs/checks/verify_plan.py` -> ALL PASS.

## 2. Logic Chain
1. Mutating operations must guarantee linearizability and optimistic concurrency control under parallel load. While `update_interaction`, `transition`, `assign`, and `add_comment` used `cas()`, `commit_workflow_migration` was mutating records in memory without an atomic CAS condition.
2. In `commit_workflow_migration`, changing the assignment to `cas(db, item, old_revision, workflow_version=to_version, state=new_state, updated_at=now, closed_at=now if new_state in to_terminal else item.closed_at)` enforces the invariant that if another transaction modifies any card during the migration, the database UPDATE rowcount will be 0, triggering immediate `db.rollback()` and raising HTTP 409 `REVISION_CONFLICT`.
3. In `begin_command`, validating `not key or not key.strip() or len(key) > 200` ensures all modifying operations reject blank, whitespace, and oversized keys with HTTP 422 `VALIDATION_ERROR`. If a valid key with identical payload is encountered, the cached `CommandResult.response` is served directly without re-executing logic or creating duplicate audit events.
4. Removing dead imports in `main.py`, `services.py`, `auth.py`, `db.py`, `seed.py`, `importer.py`, `integrations/factory.py`, and `integrations/service.py` adheres to the Ponytail Ladder (zero unnecessary baggage, minimal diff), while preserving 100% of docstrings, comments, type contracts, and tests.

## 3. Caveats
- No caveats. All 139 tests across the entire test suite pass without regressions, and all four oracle checks confirm full compliance with the specification.

## 4. Conclusion
- The backend architecture is clean, modular, and adheres to Ponytail principles with zero extraneous dependencies.
- CAS concurrency is uniformly enforced across all 5 mutating operations (`update_interaction`, `transition`, `assign`, `add_comment`, and `commit_workflow_migration`).
- `Idempotency-Key` validation (<= 200 characters) and the `CommandResult` caching mechanism are verified and tested against parallel thread races.

## 5. Verification Method
1. Run full test suite:
   ```bash
   cd backend && .venv/bin/python -m pytest tests/ -v
   ```
   Expected: 139 passed, 0 failed.
2. Run specification and compliance oracles:
   ```bash
   python3 docs/checks/verify_infra.py && \
   python3 docs/checks/verify_workflow.py && \
   python3 docs/checks/verify_reports.py && \
   python3 docs/checks/verify_plan.py
   ```
   Expected: ALL PASS.
3. Invalidation condition: Any failing test or oracle, or any mutation path bypassing atomic CAS or `Idempotency-Key` validation.
