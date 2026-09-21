# Reviewer Round 3 Handoff Record

## Objective
Final adversarial verification and hardening of `backend/app/errors.py` against Contract C01 (`docs/architecture/05-contracts-and-parallel-development.md`) and Ponytail minimalism guidelines (`AGENTS.md`).

## Summary of Findings & Fixes in Round 3

### 1. Root-Cause Issue: Unhandled Serialization Crash on Non-Primitive Types in Error `details` and `field_errors`
- **Input:** Business exception containing non-primitive types in `details` or `field_errors`, e.g. `APIError("ITEM_ERROR", "Message", 422, details={"id": uuid4(), "timestamp": datetime.now(), "amount": Decimal("10.50"), "tags": {"active"}})`
- **Expected:** Endpoint returns HTTP 422 with the structured JSON error envelope containing stringified UUID, ISO datetime, numeric Decimal, and list of tags.
- **Actual:** Starlette's `JSONResponse` invoked stdlib `json.dumps()` without an encoder, raising `TypeError: Object of type UUID is not JSON serializable`. This uncaught exception bubbled up to the global 500 handler, masking the 422 domain error and returning a 500 `INTERNAL_ERROR` to the client.
- **Root Cause:** Direct instantiation of `JSONResponse({"error": error})` bypasses FastAPI's `jsonable_encoder`.
- **Fix:** Integrated FastAPI's native `jsonable_encoder` (no new dependencies) in `domain_error` for `details` and `field_errors`.

### 2. Root-Cause Issue: Unsafe String Status Code Crash in Starlette
- **Input:** `APIError("BAD_INPUT", "msg", status="400")` or `status_code="400"`.
- **Expected:** Response code 400.
- **Actual:** Starlette's `Response` initialization crashed with `TypeError: '<' not supported between instances of 'str' and 'int'`, escalating to a 500 handler failure.
- **Root Cause:** `actual_status` was stored without numeric coercion, and `status_code` setter lacked numeric coercion.
- **Fix:** Added `int(raw_status)` coercion with fallback to 422 in both constructor and property setter, as well as before passing to `JSONResponse`.

### 3. Root-Cause Issue: Case-Insensitive Header Collision on Wire
- **Input:** `APIError(..., headers={"x-request-id": "custom-uuid"})`.
- **Expected:** Single `x-request-id` header in HTTP response.
- **Actual:** Starlette raw headers contained duplicate entries `[(b'x-request-id', b'orig-id'), (b'x-request-id', b'custom-uuid')]`.
- **Root Cause:** Dict update with differing case keys preserves duplicate case keys in Starlette raw headers.
- **Fix:** Normalized header merge case-insensitively for `x-request-id`.

### 4. Root-Cause Issue: Tuple/List Header Iterables & Non-Dict Error Objects
- **Input:** Request where headers are list of tuples (e.g. raw ASGI scope headers), or validation errors where `e` is an object rather than a dict.
- **Expected:** Correlation ID extracted without failure, validation errors extracted gracefully.
- **Actual:** `AttributeError` on `.get()`.
- **Root Cause:** Assuming `headers` and `e` are always dicts with `.get()`.
- **Fix:** Added safe inspection for `(list, tuple)` in `_get_request_id`, and `getattr(e, ...)` fallback in `validation_error`.

## Verification Results
- `backend/.venv/bin/python -m pytest backend/tests/test_errors_c01.py -v`: 14 passed in 0.29s.
- `backend/.venv/bin/python -m pytest backend/tests/ -q`: 153 passed, 0 failed in 43.27s.
- `python3 docs/checks/verify_infra.py`: PASS
- `python3 docs/checks/verify_workflow.py`: PASS
- `python3 docs/checks/verify_reports.py`: PASS
- `python3 docs/checks/verify_plan.py`: PASS
