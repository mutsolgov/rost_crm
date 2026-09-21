# DISPATCH — 2026-09-20T20:15:25+03:00

## 2026-09-20T17:15:25Z
You are the Project Orchestrator (orchestrator_5) for rost_crm.
Your working directory is: /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/orchestrator_5
Project Root: /home/muhammad/Dev/HACKATHON/LCT/rost_crm
Authoritative Request: /home/muhammad/Dev/HACKATHON/LCT/rost_crm/ORIGINAL_REQUEST.md (see the section "## Follow-up — 2026-09-20T17:14:24Z")

Sprint: Infrastructure & Supply Chain Security Audit Sprint (DevSecOps)

Goal: Comprehensive audit and hardening of infrastructure and supply chain security for "ИТ Школа Ростелекома — CRM" (rost_crm) ahead of project defense.

Requested Team Composition: 3-agent engineering team:
1. DevSecOps & Архитектура контейнеризации (Worker):
   - Nginx hardening (`deploy/nginx.conf`): `client_max_body_size 25m;`, headers: `X-Frame-Options: SAMEORIGIN`, `X-Content-Type-Options: nosniff`, `Content-Security-Policy` (default-src 'self', script-src 'self' 'unsafe-inline', style-src 'self' 'unsafe-inline', img-src 'self' data: blob:, connect-src 'self' http: ws:), `Permissions-Policy: geolocation=(), camera=(), microphone=()`.
   - Backend Dockerfile (`backend/Dockerfile`): Ensure `/app/storage` is created before switching to unprivileged user, correct ownership (`chown -R appuser:appuser /app/storage`), strictly runs under `USER appuser` (uid 10001).
   - Frontend Dockerfile (`frontend/Dockerfile`): Multi-stage build on `node:24-alpine`, runtime on `nginx:1.28-alpine` under `USER nginx`.
   - Container orchestration (`compose.yaml`): Named volume `storage-data` in `volumes:`, attached to `api` (`storage-data:/app/storage`), check `depends_on` with `condition: service_healthy` (api depends on postgres & keycloak; frontend depends on api), verify healthcheck timeouts/intervals.

2. Инженер по безопасности библиотек и зависимостей (Worker):
   - Python dependencies (`backend/requirements.txt`, `backend/requirements-dev.txt`): Audit packages (`fastapi`, `uvicorn`, `SQLAlchemy`, `psycopg`, `PyJWT`, `pydantic`, `pytest`, `httpx`) for 0 CVEs. Confirm Ponytail compliance: strictly 6 core production packages in `backend/requirements.txt`, stdlib-based report generators (zipfile, xml.etree.ElementTree).
   - Node.js dependencies (`frontend/package.json`, `frontend/pnpm-lock.yaml`): Audit dependencies for 0 critical vulnerabilities.
   - Deliverable: Detailed audit document `docs/security/dependency-security-audit.md` with registry of libraries, versions, licenses (MIT/BSD/Apache), and confirmation of 0 CVEs.

3. Инженер автоматизации инфраструктуры (Worker):
   - Secret & environment audit: Verify `.env.example` has complete list of environment variables, verify 0 hardcoded secrets in repository.
   - Verification oracle: Implement executable `docs/checks/verify_infra.py` checking compose.yaml, deploy/nginx.conf, file size consistency between nginx.conf (25m) and backend `files.py` (25 MB), storage-data volume, non-root USER directives, security headers in nginx.conf.
   - DoD & Regression: Run 128 existing backend tests (`pytest tests/ -v`), run all oracles (`verify_workflow.py`, `verify_reports.py`, `verify_plan.py`, `verify_infra.py`).

Instructions:
- Maintain your `plan.md`, `progress.md`, and `BRIEFING.md` in `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/orchestrator_5/`.
- Decompose, assign, and coordinate with specialized subagents in their own subdirectories under `.agents/`.
- Adhere strictly to AGENTS.md, Ponytail Ladder, and security invariants.
- When all Acceptance Criteria are met and tests/oracles pass, report completion and victory claim back to Sentinel via send_message.
