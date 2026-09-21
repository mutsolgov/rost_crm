# Reviewer R1 Handoff: C01 Error Handling Alignment & Hardening

> [!WARNING] **Skepticism Disclaimer**
> Confident in the C01 error envelope schema, HTTP correlation headers, and test regression safety across all 146 tests, though raw socket disconnects during mid-stream body transmission remain tested at the ASGI level rather than live kernel TCP socket drops.

## 1. What the prior attempt got wrong

1. **Issue 1 (Missing `X-Request-ID` HTTP header on 500 responses):**
   - **Input:** Request triggering an unhandled server exception (e.g. unhandled `RuntimeError` or database failure).
   - **Expected:** HTTP 500 response includes `X-Request-ID` header matching `error.request_id` in response envelope, per Contract C01 correlation rules.
   - **Actual:** `response.headers` lacked the `X-Request-ID` header entirely.
   - **Root cause:** In Starlette, unhandled exceptions bypass `BaseHTTPMiddleware` on the error path and bubble directly to outer `ServerErrorMiddleware`. The previous `internal_error` handler did not specify `headers={"X-Request-ID": req_id}` on the returned `JSONResponse`.
   - **Fix:** Explicitly attached `headers={"X-Request-ID": req_id}` to `JSONResponse` in both `internal_error` and `domain_error`.

2. **Issue 2 (Loss of field name when payload field is named `"body"`):**
   - **Input:** Validation error on a model field named `body` (e.g. `comment.body` or top-level `body`).
   - **Expected:** Only the leading container prefix `"body"` is removed from `loc`, preserving the attribute name (`"body"` or `"comment.body"`).
   - **Actual:** Naive filter `[str(p) for p in e["loc"] if p != "body"]` stripped ALL occurrences of the string `"body"`, reducing `('body', 'body')` to empty string `""` and losing the field name.
   - **Root cause:** Universal exclusion filter instead of prefix-only stripping.
   - **Fix:** Stripped only the leading `"body"` element: `parts = loc[1:] if loc and loc[0] == "body" else loc`.

3. **Issue 3 (Fragile `request.state` access):**
   - **Input:** Request object without `.state` attribute (e.g. naked ASGI request or test mock).
   - **Expected:** Handler safely falls back to headers or generates a new `uuid4()`.
   - **Actual:** `getattr(request.state, "request_id", None)` raised `AttributeError` because `request.state` was accessed directly before checking if `state` existed.
   - **Root cause:** Chained `getattr` on an unverified attribute.
   - **Fix:** Safe two-step resolution: `state = getattr(request, "state", None)` then `getattr(state, "request_id", None)`.

4. **Issue 4 (Missing test coverage for edge cases):**
   - **Input:** Prior test suite only tested basic happy paths and basic validation.
   - **Expected:** Tests verifying `X-Request-ID` header on 500 responses, fields named `"body"`, malformed JSON, and naked mock request handling.
   - **Actual:** None of these edge cases were exercised in `test_errors_c01.py`.
   - **Root cause:** Incomplete test matrix.
   - **Fix:** Added unit tests covering all 4 edge cases in `backend/tests/test_errors_c01.py`.

## 2. What I changed
- `backend/app/errors.py`:
  - Enforced `headers={"X-Request-ID": req_id}` in `domain_error` and `internal_error`.
  - Replaced naive list comprehension with prefix-only stripping for `loc` in `validation_error`.
  - Added safe `request.state` fallback extraction.
- `backend/tests/test_errors_c01.py`:
  - Verified `X-Request-ID` header propagation in `test_unhandled_exception_returns_internal_error_500`.
  - Added `test_validation_preserves_field_named_body` verifying root and nested fields named `body`.
  - Added `test_empty_body_and_malformed_json` verifying malformed JSON and empty body payloads.
  - Added `test_error_handlers_safe_with_mock_request` verifying resilience against requests without `.state`.

## 3. Verification Record
- **Deep Verification (ran actual tests):**
  - `backend/.venv/bin/python -m pytest backend/tests/test_errors_c01.py -v`: 7 passed in 0.18s.
  - `backend/.venv/bin/python -m pytest backend/tests/ -q`: 146 passed, 0 failed in 45.57s.
  - `python3 docs/checks/verify_infra.py`: PASS.
  - `python3 docs/checks/verify_workflow.py`: PASS.
  - `python3 docs/checks/verify_reports.py`: PASS.
  - `python3 docs/checks/verify_plan.py`: PASS.
- **Shallow Verification (manual only):**
  - Inspected diff in `backend/app/errors.py` against Ponytail minimalism rules: clean 40-line diff, stdlib only, zero new dependencies.
- **Unverified aspects:**
  - Hard OS-level socket aborts during HTTP chunked transfer streaming.

## 4. Known Issues
- `Minor Robustness Risk`: If an upstream reverse proxy strips response headers from HTTP 500 responses before client delivery, clients would rely solely on the JSON body `error.request_id` (both are now populated).

## 5. Remaining risk & next step
- Task requirements R1–R4 and Acceptance Criteria are fully satisfied, hardened against edge cases, and 100% regression-free. Ready for final acceptance.
