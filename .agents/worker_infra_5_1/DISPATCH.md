# DISPATCH — worker_infra_5_1

## Task
You are worker_infra_5_1: Infrastructure Automation & Verification Engineer for rost_crm.
Your working directory is: /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_infra_5_1
Authoritative Request: /home/muhammad/Dev/HACKATHON/LCT/rost_crm/ORIGINAL_REQUEST.md (see Section "## Follow-up — 2026-09-20T17:14:24Z")
Project Blueprint & Contracts: /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/orchestrator_5/PROJECT.md
Explorer 3 Handoff & Blueprint: /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/explorer_infra_oracle_5_1/handoff.md

### Scope and Owned Files
You have EXCLUSIVE write ownership of:
1. `.env.example`
2. `docs/checks/verify_infra.py`

DO NOT modify any other files.

### Instructions:
1. Update `.env.example`:
   - Ensure complete coverage of all environment parameters.
   - Document optional backend configuration parameters (`APP_ENV`, `AUTH_MODE`, `STORAGE_DIR`, `LMS_INTEGRATION_MODE`, `WEBSITE_INTEGRATION_MODE`, `LMS_BASE_URL`, `WEBSITE_BASE_URL`) per the blueprint in Explorer 3 handoff.
   - Verify 0 hardcoded production secrets in repository.
2. Implement Verification Oracle `docs/checks/verify_infra.py`:
   - Pure Python standard library implementation (zero pip dependencies, no pyyaml).
   - Check `compose.yaml`: all 4 services (`postgres`, `keycloak`, `api`, `frontend`), healthcheck probes, `condition: service_healthy` dependencies, named volume `storage-data` and mount `storage-data:/app/storage`.
   - Check `deploy/nginx.conf`: `client_max_body_size 25m;`, security headers (`X-Frame-Options: SAMEORIGIN`, `X-Content-Type-Options: nosniff`, `Content-Security-Policy`, `Permissions-Policy: geolocation=(), camera=(), microphone=()`, `Referrer-Policy: strict-origin-when-cross-origin`).
   - Validate file size limit consistency between `deploy/nginx.conf` (`25m` == 26,214,400 bytes) and `backend/app/files.py` (`MAX_FILE_SIZE = 26_214_400`).
   - Check Dockerfiles: non-root `USER appuser` (uid 10001) and `/app/storage` directory creation/chown in `backend/Dockerfile`, multi-stage and non-root `USER nginx` in `frontend/Dockerfile`.
   - Check `.env.example` presence, required variables, and verify `.env` is absent and gitignored.
   - Output clear PASS lines and exit code 0 on success.
3. Execute and Verify:
   - Run `python3 docs/checks/verify_infra.py` -> must PASS with exit code 0.
   - Run `python3 docs/checks/verify_workflow.py && python3 docs/checks/verify_reports.py && python3 docs/checks/verify_plan.py` -> must all PASS.
   - Run `backend/.venv/bin/python -m pytest backend/tests/ -v` -> all 128 tests must pass (100%).
   - Verify `git diff backend/requirements.txt frontend/package.json` is empty (0 new dependencies).
4. Write comprehensive 5-component report to `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_infra_5_1/handoff.md`.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Send message to parent when completed.
