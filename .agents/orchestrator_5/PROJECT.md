# Project: Infrastructure & Supply Chain Security Audit Sprint (DevSecOps)

## Architecture
- **Reverse Proxy & Gateway**: Nginx 1.28-alpine container handling TLS termination, reverse proxying to FastAPI backend `/api/`, serving React SPA, enforcing HTTP security headers (CSP, Frame-Options, Content-Type-Options, Permissions-Policy) and 25 MB request body limit.
- **Backend API**: Python 3.12 / 3.14 FastAPI ASGI service running strictly as non-root `USER appuser` (uid 10001) with persistent file storage mounted at `/app/storage`.
- **Persistent Volume Architecture**: Named Docker volume `storage-data` bound to `/app/storage` in `api` container and `postgres-data` bound to PostgreSQL.
- **Container Orchestration**: Docker Compose (`compose.yaml`) with deterministic startup dependencies via `depends_on` condition `service_healthy` across PostgreSQL, Keycloak, Backend API, and Frontend.
- **Supply Chain Architecture**: Minimalist "Ponytail" footprint — strictly 6 production Python packages in `backend/requirements.txt`, stdlib-only XLSX/PDF/CSV engines, and 3 runtime Node.js packages in `frontend/package.json`.
- **Verification Infrastructure**: 4 automated, pure-stdlib verification oracles in `docs/checks/` (`verify_workflow.py`, `verify_reports.py`, `verify_plan.py`, `verify_infra.py`) plus 128 comprehensive pytest tests.

---

## Feature Inventory

| # | Feature | Description | Milestone | Source |
|---|---|---|---|---|
| F01 | Nginx Body Limit 25m | Update `deploy/nginx.conf` `client_max_body_size` from `2m;` to `25m;` for 25 MB parity | M1 | Survey (explorer_devsecops_5_1) |
| F02 | Nginx Security Headers | Add `X-Frame-Options: SAMEORIGIN`, `Content-Security-Policy`, `Permissions-Policy` to `deploy/nginx.conf` | M1 | Survey (explorer_devsecops_5_1) |
| F03 | Backend Non-Root Storage | In `backend/Dockerfile`, create `/app/storage` with `chown -R appuser:appuser /app/storage` before `USER appuser` | M1 | Survey (explorer_devsecops_5_1) |
| F04 | Frontend Dockerfile Hardening | In `frontend/Dockerfile`, ensure build `node:24-alpine`, runtime `nginx:1.28-alpine` under `USER nginx` with `--chown=nginx:nginx` | M1 | Survey (explorer_devsecops_5_1) |
| F05 | Named Volume storage-data | Add `storage-data` to root `volumes:` in `compose.yaml` and mount `storage-data:/app/storage` in `api` service | M1 | Survey (explorer_devsecops_5_1) |
| F06 | Healthcheck Dependencies | Verify `condition: service_healthy` dependencies and healthcheck parameters in `compose.yaml` | M1 | Survey (explorer_devsecops_5_1) |
| F07 | Python Dependencies Audit | Audit `backend/requirements.txt` (strictly 6 prod packages) and dev packages for 0 CVEs | M2 | Survey (explorer_supplychain_5_1) |
| F08 | Ponytail Stdlib Verification | Confirm 0 3rd-party reporting libraries, stdlib-only XLSX/PDF/CSV report engines | M2 | Survey (explorer_supplychain_5_1) |
| F09 | Node.js Dependencies Audit | Audit `frontend/package.json` (3 runtime, 5 dev) and `pnpm-lock.yaml` (69 pkgs) for 0 critical CVEs | M2 | Survey (explorer_supplychain_5_1) |
| F10 | Dependency Security Report | Create `docs/security/dependency-security-audit.md` with package registries, licenses, and 0-CVE proof | M2 | Survey (explorer_supplychain_5_1) |
| F11 | Environment & Secrets Audit | Update `.env.example` with documented optional backend parameters; verify 0 hardcoded secrets | M3 | Survey (explorer_infra_oracle_5_1) |
| F12 | Infrastructure Verification Oracle | Create executable `docs/checks/verify_infra.py` checking compose, nginx, files.py consistency, Dockerfiles | M3 | Survey (explorer_infra_oracle_5_1) |
| F13 | Regression & Oracle Gate | Execute all 128 backend pytest tests and 4 oracles (`verify_workflow`, `verify_reports`, `verify_plan`, `verify_infra`) | M3 | Survey (explorer_infra_oracle_5_1) |

---

## Milestones

| # | Name | Scope | Dependencies | Status |
|---|---|---|---|---|
| M1 | DevSecOps & Container Hardening | F01, F02, F03, F04, F05, F06 (`deploy/nginx.conf`, `backend/Dockerfile`, `frontend/Dockerfile`, `compose.yaml`) | None | DONE |
| M2 | Supply Chain Security & Dependency Audit | F07, F08, F09, F10 (`docs/security/dependency-security-audit.md`) | None | DONE |
| M3 | Infrastructure Automation & Verification | F11, F12, F13 (`.env.example`, `docs/checks/verify_infra.py`, test suite execution) | M1, M2 | DONE |

---

## Code Layout
- `deploy/nginx.conf`: Nginx reverse proxy configuration and HTTP security headers
- `backend/Dockerfile`: Multi-stage / non-root Python backend image specification
- `frontend/Dockerfile`: Multi-stage Node/Nginx frontend image specification
- `compose.yaml`: Multi-container local orchestration, network, and persistent storage
- `docs/security/dependency-security-audit.md`: Formal supply chain security and license audit document
- `.env.example`: Complete environment variable blueprint for deployment
- `docs/checks/verify_infra.py`: Executable standard-library infrastructure verification oracle
- `docs/checks/`: Existing specification verification oracles (`verify_workflow.py`, `verify_reports.py`, `verify_plan.py`)
- `backend/tests/`: Pytest integration, unit, and stress test suite (128 existing tests)

---

## Interface Contracts

### Nginx ↔ Backend File Limit
- Directives:
  - In `deploy/nginx.conf`: `client_max_body_size 25m;`
  - In `backend/app/files.py`: `MAX_FILE_SIZE = 26_214_400  # 25 MB`
  - In `frontend/src/views/InteractionPage.tsx`: `const MAX_FILE_SIZE = 25 * 1024 * 1024; // 25 MB`
- Invariant: `nginx.client_max_body_size == 25 * 1024 * 1024 bytes == backend.MAX_FILE_SIZE`

### Docker Storage Contract
- Mount point: `/app/storage` in container
- User: `USER appuser` (uid: 10001, gid: 10001)
- Host/Volume: Docker named volume `storage-data`
- Invariant: Directory `/app/storage` is pre-created and owned by `appuser:appuser` before `USER appuser` directive.

### Verification Oracle CLI Contract
- Command: `python3 docs/checks/verify_infra.py`
- Exit Code: 0 on success, 1 on failure
- Output: Standard `PASS: <component>` lines and `ALL INFRASTRUCTURE AND DEVSECOPS CHECKS PASSED.` on completion.
- Dependencies: Standard library only (no `pip install` required).
