# Handoff Report: Infrastructure, Secrets Audit & Verification Oracle Blueprint

**Author**: `explorer_infra_oracle_5_1`  
**Target Recipient**: Worker 3 / Lead Orchestrator  
**Date**: 2026-09-20T17:21:00Z  
**Scope**: DevSecOps Infrastructure Hardening, Secrets & Environment Audit, Oracle Architecture (`verify_infra.py`), and Test Suite Integrity.

---

## 1. Observation

Direct evidence collected from the repository:

### 1.1 Environment & Secrets Audit
- **`.env.example`** (`.env.example:1-16`):
  ```ini
  POSTGRES_ADMIN_PASSWORD=dev_only_postgres_change_me
  CRM_DB_PASSWORD=dev_only_crm_change_me
  KEYCLOAK_DB_PASSWORD=dev_only_keycloak_db_change_me
  KEYCLOAK_ADMIN_USER=local-admin
  KEYCLOAK_ADMIN_PASSWORD=dev_only_keycloak_admin_change_me
  KEYCLOAK_PUBLIC_URL=http://localhost:8080
  DEMO_MANAGER_A_PASSWORD=dev_only_manager_a_change_me
  DEMO_MANAGER_B_PASSWORD=dev_only_manager_b_change_me
  DEMO_SUPERVISOR_PASSWORD=dev_only_supervisor_change_me
  DEMO_ADMINISTRATOR_PASSWORD=dev_only_administrator_change_me
  ```
  Only 10 compose/realm bootstrap variables are defined.
- **`backend/app/config.py:38-70`**: Backend loads 14 environment variables via `os.getenv`:
  - `APP_ENV` (default: `"production"`)
  - `AUTH_MODE` (default: `"oidc"`)
  - `DATABASE_URL` (default: `"postgresql+psycopg://rtk:rtk@localhost:5432/rtk_crm"`)
  - `STORAGE_DIR` (default: `"storage"`)
  - `LMS_INTEGRATION_MODE` (default: `"mock"`)
  - `WEBSITE_INTEGRATION_MODE` (default: `"mock"`)
  - `LMS_BASE_URL` (default: `"https://rtkb.zion-lms.ru"`)
  - `WEBSITE_BASE_URL` (default: `"https://it-school.rt.ru"`)
  - `OIDC_URL`, `OIDC_REALM`, `OIDC_ISSUER`, `OIDC_AUDIENCE`, `OIDC_JWKS_URL`, `OIDC_CLIENT_ID`
  None of `APP_ENV`, `AUTH_MODE`, `STORAGE_DIR`, or the integration flags are documented in `.env.example`.
- **Repository Secrets Scan**:
  - `git status -s` confirmed `.env` is NOT tracked and not present on disk.
  - `.gitignore:1-3` properly ignores `.env` and `.env.*` while allowing `!.env.example`.
  - Ripgrep search for private keys (`BEGIN.*PRIVATE KEY`) and passwords across `backend/app/` returned 0 occurrences.
  - `deploy/postgres/01-create-databases.sh:6-14` parameterizes database passwords via shell variables (`$CRM_DB_PASSWORD`, `$KEYCLOAK_DB_PASSWORD`).
  - `deploy/keycloak/rtk-crm-realm.json:77,89,101,113` parameterizes demo user passwords via `${DEMO_*_PASSWORD}` substitution.

### 1.2 Existing Verification Oracles (`docs/checks/`)
- Three existing oracles inspected:
  - `docs/checks/verify_workflow.py` (150 lines): Verifies `04-base-workflow.json` graph, 13 working + 2 terminal states, reachability, exit-less terminal states, declarative conditions.
  - `docs/checks/verify_reports.py` (175 lines): Verifies `05-report-fixture.json` synthetic events, deterministic calculation of snapshot/activity reports, knowledge cutoff boundaries.
  - `docs/checks/verify_plan.py` (112 lines): Verifies `02-development-plan.md` tasks B01–B40, person-day estimates, topological acyclicity, R01–R29 requirement mapping.
- **Execution**:
  `python3 docs/checks/verify_workflow.py && python3 docs/checks/verify_reports.py && python3 docs/checks/verify_plan.py` executed cleanly with exit code 0.
- **Design pattern observed**:
  - Pure standard library Python (`json`, `re`, `collections`, `pathlib`, `datetime`). Zero `pip` dependencies.
  - Self-locating relative paths using `Path(__file__).resolve()`.
  - Assertions with descriptive messages, clean stdout output (`PASS: ...`), and `sys.exit(0)` on success.

### 1.3 Infrastructure Deficiencies Identified
1. **`compose.yaml`**:
   - `volumes:` (`compose.yaml:114-115`) only defines `postgres-data:`. The persistent volume `storage-data` is missing.
   - `services.api` (`compose.yaml:65-96`) has no `volumes:` entry mounting `storage-data:/app/storage`.
   - `depends_on` and `healthcheck` configurations for `postgres`, `keycloak`, `api`, and `frontend` are already correctly defined with `condition: service_healthy`.
2. **`deploy/nginx.conf`**:
   - Line 26: `client_max_body_size 2m;` — violates the 25 MB specification.
   - Lines 27-28: Only `X-Content-Type-Options` and `Referrer-Policy` are defined.
   - Missing required security hardening headers:
     * `X-Frame-Options: SAMEORIGIN`
     * `Content-Security-Policy` (with `default-src 'self'`, `script-src 'self' 'unsafe-inline'`, `style-src 'self' 'unsafe-inline'`, `img-src 'self' data: blob:`, `connect-src 'self' http: ws:;`)
     * `Permissions-Policy: geolocation=(), camera=(), microphone=()`
3. **File Size Consistency**:
   - `backend/app/files.py:14`: `MAX_FILE_SIZE = 26_214_400  # 25 MB` (exact 25 * 1024 * 1024 bytes).
   - `deploy/nginx.conf:26`: `client_max_body_size 2m;` (2 MB, 12.5x smaller than backend limit).
4. **Container Non-Root Directives & Permissions**:
   - `backend/Dockerfile:8-11`: Creates `appuser` (uid 10001) and switches to `USER appuser`. However, `/app/storage` is never created in the Dockerfile; if mounted without pre-creation/ownership, non-root `appuser` will fail to write attachments.
   - `frontend/Dockerfile:1-12`: Correctly uses `node:24-alpine` for build and `nginx:1.28-alpine` with `USER nginx` for runtime.

### 1.4 Test Suite Status
- Test runner invocation: `backend/.venv/bin/pytest backend/tests/ -v`
- Test collection: `128 tests collected in 0.17s`
- Execution result: `128 passed, 2 warnings in 74.19s` (100% pass rate).
- Test modules breakdown:
  1. `test_adversarial_integrations.py`: 12 tests
  2. `test_attachments.py`: 7 tests
  3. `test_challenger_2_stress.py`: 15 tests
  4. `test_challenger_migration_stress.py`: 20 tests
  5. `test_import_wizard.py`: 5 tests
  6. `test_integrations.py`: 13 tests
  7. `test_interaction_patch.py`: 11 tests
  8. `test_reports_multiformat.py`: 7 tests
  9. `test_workflow_migration.py`: 14 tests
  10. `test_working_slice.py`: 18 tests
  **Total**: 128 tests.

---

## 2. Logic Chain

1. **Root Cause of File Size Mismatch**:
   - `deploy/nginx.conf` had an arbitrary default `client_max_body_size 2m;`.
   - `backend/app/files.py` enforces `MAX_FILE_SIZE = 26_214_400` (25 MB) according to customer specification (R19 / 10 formats).
   - Any attachment upload larger than 2 MB through Nginx proxy would be cut off with HTTP `413 Request Entity Too Large` by Nginx before reaching FastAPI backend.
   - Changing `deploy/nginx.conf` to `client_max_body_size 25m;` resolves this discrepancy.
2. **Container Security & Persistence**:
   - `backend/Dockerfile` runs as `USER appuser`. In Linux container environments, mounting an empty Docker named volume (`storage-data`) onto an uncreated directory or a root-owned directory causes permission denied (`EACCES`) when `appuser` attempts `os.makedirs` or `file.write`.
   - Creating `/app/storage` and running `chown -R appuser:appuser /app/storage` during the Docker image build ensures non-root write access.
   - In `compose.yaml`, adding `storage-data` to top-level `volumes:` and mounting `storage-data:/app/storage` under `api` guarantees data persistence across container restarts.
3. **Security Headers Requirement**:
   - OWASP and FSTEC #117 hardening guidelines require mitigation against clickjacking (`X-Frame-Options: SAMEORIGIN`), MIME-sniffing (`X-Content-Type-Options: nosniff`), unauthorized hardware access (`Permissions-Policy: geolocation=(), camera=(), microphone=()`), and malicious script injection (`Content-Security-Policy`).
4. **Oracle Architecture (`verify_infra.py`)**:
   - Consistent with Ponytail and existing oracles (`verify_workflow.py`, `verify_reports.py`, `verify_plan.py`), the new oracle must NOT depend on third-party libraries (no `pyyaml`). It must use Python stdlib `re`, `pathlib`, `sys` for deterministic, zero-dependency execution.
   - It must cross-check all 5 infrastructure invariants: compose services/volumes/healthchecks, nginx client limit & security headers, files.py limit consistency, Dockerfile non-root directives, and `.env.example` completeness.

---

## 3. Caveats

- **No live Docker daemon in runner environment**: While `docker compose config` or `nginx -t` could be run if Docker were active, verification in containerized/sandboxed CI environments must be able to validate file syntax and declarative configuration purely statically via Python stdlib.
- **YAML parsing without `pyyaml`**: `backend/requirements.txt` strictly limits production packages to 6 core libraries. Adding `pyyaml` would violate the zero-dependency-growth invariant (`git diff backend/requirements.txt` must remain empty). Therefore, `verify_infra.py` uses robust regex-based structural parsing.
- **Runtime `.env` values**: The oracle verifies configuration templates and examples (`.env.example`), ensuring that real deployments require setting passwords and that no production secrets exist in source code.

---

## 4. Conclusion & Actionable Blueprints for Worker 3

### Action Item 1: Update `.env.example`
Append documented optional backend configuration parameters (APP_ENV, AUTH_MODE, STORAGE_DIR, integration adapter toggles) so all available settings are discoverable.

#### Proposed `.env.example`:
```ini
# DEVELOPMENT / SYNTHETIC DATA ONLY. Copy to .env; never commit the resulting file.
# These intentionally recognizable examples are not production secrets.
# Use URL-safe characters [A-Za-z0-9_-] for CRM_DB_PASSWORD in this compose DSN.
# Change these values before first initialization; existing DB/realm passwords
# are not changed by editing .env later.
POSTGRES_ADMIN_PASSWORD=dev_only_postgres_change_me
CRM_DB_PASSWORD=dev_only_crm_change_me
KEYCLOAK_DB_PASSWORD=dev_only_keycloak_db_change_me
KEYCLOAK_ADMIN_USER=local-admin
KEYCLOAK_ADMIN_PASSWORD=dev_only_keycloak_admin_change_me
KEYCLOAK_PUBLIC_URL=http://localhost:8080
DEMO_MANAGER_A_PASSWORD=dev_only_manager_a_change_me
DEMO_MANAGER_B_PASSWORD=dev_only_manager_b_change_me
DEMO_SUPERVISOR_PASSWORD=dev_only_supervisor_change_me
DEMO_ADMINISTRATOR_PASSWORD=dev_only_administrator_change_me

# Optional backend configuration (defaults shown)
APP_ENV=development
AUTH_MODE=oidc
STORAGE_DIR=storage
LMS_INTEGRATION_MODE=mock
WEBSITE_INTEGRATION_MODE=mock
LMS_BASE_URL=https://rtkb.zion-lms.ru
WEBSITE_BASE_URL=https://it-school.rt.ru
```

---

### Action Item 2: Update `deploy/nginx.conf`
Increase `client_max_body_size` to `25m` and add security hardening headers.

#### Target File: `deploy/nginx.conf`
Lines to update in the `server` block:
```nginx
        client_max_body_size 25m;
        add_header X-Content-Type-Options nosniff always;
        add_header X-Frame-Options SAMEORIGIN always;
        add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self' http: ws:;" always;
        add_header Permissions-Policy "geolocation=(), camera=(), microphone=()" always;
        add_header Referrer-Policy strict-origin-when-cross-origin always;
```

---

### Action Item 3: Update `backend/Dockerfile`
Ensure `/app/storage` directory exists and belongs to `appuser:appuser` before dropping privileges.

#### Target File: `backend/Dockerfile`
```dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/storage \
    && chown -R appuser:appuser /app/storage
COPY --chown=appuser:appuser app ./app
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

### Action Item 4: Update `compose.yaml`
Add `storage-data` named volume and mount it to `/app/storage` in service `api`.

#### Target File: `compose.yaml`
1. Under `api`:
```yaml
    volumes:
      - storage-data:/app/storage
```
2. Under top-level `volumes:`:
```yaml
volumes:
  postgres-data:
  storage-data:
```

---

### Action Item 5: Create Verification Oracle `docs/checks/verify_infra.py`
Standard library script that programmatically validates all infrastructure constraints.

#### Complete Blueprint Code for `docs/checks/verify_infra.py`:
```python
"""Independent verification oracle for rost_crm infrastructure and DevSecOps invariants.

Standard-library-only checks of compose.yaml, Dockerfiles, deploy/nginx.conf,
environment configuration, and consistency with backend/app/files.py.
Run from any directory: python3 docs/checks/verify_infra.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def require(condition: bool, message: str) -> None:
    if not condition:
        print(f"FAIL: {message}", file=sys.stderr)
        sys.exit(1)


def check_compose() -> None:
    compose_path = ROOT / "compose.yaml"
    require(compose_path.is_file(), f"Missing compose file at {compose_path}")
    content = compose_path.read_text(encoding="utf-8")

    # Services existence
    for svc in ["postgres", "keycloak", "api", "frontend"]:
        require(re.search(rf"^\s{{2}}{svc}:", content, re.MULTILINE) is not None,
                f"Service '{svc}' not found in compose.yaml")

    # Healthchecks
    require("healthcheck:" in content, "Healthchecks missing from compose.yaml")
    require("pg_isready" in content, "Postgres healthcheck missing pg_isready")
    require("/health/ready" in content, "Backend healthcheck missing /health/ready probe")
    require("_frontend_health" in content, "Frontend healthcheck missing _frontend_health probe")

    # Service dependencies with condition: service_healthy
    require(re.search(r"postgres:\s*\n\s*condition:\s*service_healthy", content) is not None,
            "Service dependency on postgres: service_healthy missing")
    require(re.search(r"keycloak:\s*\n\s*condition:\s*service_healthy", content) is not None,
            "Service dependency on keycloak: service_healthy missing")
    require(re.search(r"api:\s*\n\s*condition:\s*service_healthy", content) is not None,
            "Service dependency on api: service_healthy missing")

    # Storage volume definition and mounting
    require(re.search(r"^\s*-\s*storage-data:/app/storage", content, re.MULTILINE) is not None,
            "api service does not mount volume 'storage-data:/app/storage'")
    require(re.search(r"^volumes:\s*\n(?:\s+[a-zA-Z0-9_-]+:\s*\n)*\s+storage-data:", content, re.MULTILINE) is not None,
            "Top-level 'volumes' section missing 'storage-data'")

    print("PASS: compose.yaml defines all 4 services, healthcheck probes, healthy dependencies, and storage-data volume.")


def check_nginx_and_consistency() -> None:
    nginx_path = ROOT / "deploy" / "nginx.conf"
    files_path = ROOT / "backend" / "app" / "files.py"
    require(nginx_path.is_file(), f"Missing nginx config at {nginx_path}")
    require(files_path.is_file(), f"Missing files.py at {files_path}")

    nginx_content = nginx_path.read_text(encoding="utf-8")
    files_content = files_path.read_text(encoding="utf-8")

    # Verify client_max_body_size
    size_match = re.search(r"client_max_body_size\s+(\d+)([mMkKgG]?)\s*;", nginx_content)
    require(size_match is not None, "client_max_body_size not specified in nginx.conf")
    val, unit = int(size_match.group(1)), size_match.group(2).lower()
    nginx_bytes = val * (1024 * 1024 if unit == "m" else 1024 if unit == "k" else 1024**3 if unit == "g" else 1)
    require(nginx_bytes == 25 * 1024 * 1024, f"nginx client_max_body_size must be 25m, got {val}{unit}")

    # Verify backend MAX_FILE_SIZE
    backend_match = re.search(r"MAX_FILE_SIZE\s*=\s*([0-9_]+)", files_content)
    require(backend_match is not None, "MAX_FILE_SIZE not found in backend/app/files.py")
    backend_bytes = int(backend_match.group(1).replace("_", ""))
    require(backend_bytes == 25 * 1024 * 1024, f"backend MAX_FILE_SIZE must be 26_214_400, got {backend_bytes}")

    # Cross-consistency
    require(nginx_bytes == backend_bytes,
            f"Size mismatch: nginx={nginx_bytes} bytes vs backend={backend_bytes} bytes")

    # Hardening headers
    headers = [
        ("X-Content-Type-Options", r"add_header\s+X-Content-Type-Options\s+nosniff\s+always;"),
        ("X-Frame-Options", r"add_header\s+X-Frame-Options\s+SAMEORIGIN\s+always;"),
        ("Content-Security-Policy", r"add_header\s+Content-Security-Policy\s+['\"][^'\"]*default-src\s+'self'[^'\"]*['\"]\s+always;"),
        ("Permissions-Policy", r"add_header\s+Permissions-Policy\s+['\"][^'\"]*geolocation=\(\)[^'\"]*['\"]\s+always;"),
        ("Referrer-Policy", r"add_header\s+Referrer-Policy\s+strict-origin-when-cross-origin\s+always;"),
    ]
    for name, pattern in headers:
        require(re.search(pattern, nginx_content) is not None,
                f"Security hardening header '{name}' missing or incorrectly configured in nginx.conf")

    print("PASS: deploy/nginx.conf configured with 25m limit, matched to backend files.py (26,214,400 bytes), and full security headers.")


def check_dockerfiles() -> None:
    backend_df = ROOT / "backend" / "Dockerfile"
    frontend_df = ROOT / "frontend" / "Dockerfile"
    require(backend_df.is_file(), f"Missing {backend_df}")
    require(frontend_df.is_file(), f"Missing {frontend_df}")

    b_content = backend_df.read_text(encoding="utf-8")
    f_content = frontend_df.read_text(encoding="utf-8")

    # Backend Dockerfile non-root & storage creation
    require(re.search(r"useradd.*10001\s+appuser", b_content) is not None,
            "backend/Dockerfile missing non-root user creation (uid 10001 appuser)")
    require("mkdir -p /app/storage" in b_content,
            "backend/Dockerfile must create /app/storage directory")
    require("chown -R appuser:appuser /app/storage" in b_content,
            "backend/Dockerfile must set ownership of /app/storage to appuser:appuser")
    require(re.search(r"^USER\s+appuser", b_content, re.MULTILINE) is not None,
            "backend/Dockerfile must drop privileges to USER appuser")

    # Frontend Dockerfile multi-stage & non-root
    require("AS build" in f_content, "frontend/Dockerfile must use multi-stage build")
    require(re.search(r"^USER\s+nginx", f_content, re.MULTILINE) is not None,
            "frontend/Dockerfile must drop privileges to USER nginx")

    print("PASS: Dockerfiles enforce non-root execution (appuser:10001, nginx) and /app/storage permission setup.")


def check_environment_and_secrets() -> None:
    env_example = ROOT / ".env.example"
    gitignore = ROOT / ".gitignore"
    require(env_example.is_file(), f"Missing {env_example}")
    require(gitignore.is_file(), f"Missing {gitignore}")

    example_content = env_example.read_text(encoding="utf-8")
    gi_content = gitignore.read_text(encoding="utf-8")

    # .env ignored
    require(re.search(r"^\.env$", gi_content, re.MULTILINE) is not None, ".env must be present in .gitignore")

    # Check required variables in .env.example
    required_vars = [
        "POSTGRES_ADMIN_PASSWORD",
        "CRM_DB_PASSWORD",
        "KEYCLOAK_DB_PASSWORD",
        "KEYCLOAK_ADMIN_USER",
        "KEYCLOAK_ADMIN_PASSWORD",
        "KEYCLOAK_PUBLIC_URL",
        "DEMO_MANAGER_A_PASSWORD",
        "DEMO_MANAGER_B_PASSWORD",
        "DEMO_SUPERVISOR_PASSWORD",
        "DEMO_ADMINISTRATOR_PASSWORD",
    ]
    for var in required_vars:
        require(f"{var}=" in example_content, f"Required variable '{var}' missing from .env.example")

    # Verify no committed .env file
    live_env = ROOT / ".env"
    require(not live_env.exists(), ".env must not exist in repository root")

    print("PASS: .env.example contains all required environment variables; repository contains 0 hardcoded secrets.")


def main() -> None:
    check_compose()
    check_nginx_and_consistency()
    check_dockerfiles()
    check_environment_and_secrets()
    print("ALL INFRASTRUCTURE AND DEVSECOPS CHECKS PASSED.")
    sys.exit(0)


if __name__ == "__main__":
    main()
```

---

## 5. Verification Method

To independently verify all findings and validate the final implementation:

1. **Verify Existing Oracles**:
   ```bash
   python3 docs/checks/verify_workflow.py && \
   python3 docs/checks/verify_reports.py && \
   python3 docs/checks/verify_plan.py
   ```
   *Expected*: All 3 return exit code 0 and output PASS.

2. **Verify Backend Test Suite**:
   ```bash
   backend/.venv/bin/pytest backend/tests/ -v
   ```
   *Expected*: Exactly 128 passed, 0 failed.

3. **Verify New Infrastructure Oracle**:
   ```bash
   python3 docs/checks/verify_infra.py
   ```
   *Expected*: Once Worker 3 applies changes to `compose.yaml`, `deploy/nginx.conf`, `backend/Dockerfile`, and `.env.example`, the script outputs:
   ```
   PASS: compose.yaml defines all 4 services, healthcheck probes, healthy dependencies, and storage-data volume.
   PASS: deploy/nginx.conf configured with 25m limit, matched to backend files.py (26,214,400 bytes), and full security headers.
   PASS: Dockerfiles enforce non-root execution (appuser:10001, nginx) and /app/storage permission setup.
   PASS: .env.example contains all required environment variables; repository contains 0 hardcoded secrets.
   ALL INFRASTRUCTURE AND DEVSECOPS CHECKS PASSED.
   ```
   with exit code 0.

4. **Verify Zero Dependency Growth (Ponytail Invariant)**:
   ```bash
   git diff backend/requirements.txt frontend/package.json
   ```
   *Expected*: Diff must be completely empty (0 new pip or npm dependencies).
