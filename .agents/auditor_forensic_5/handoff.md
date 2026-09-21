# Forensic Integrity Audit Report — DevSecOps & Supply Chain Sprint

## Forensic Audit Report

**Work Product**: Infrastructure, Container Hardening, and Supply Chain Security artifacts (`deploy/nginx.conf`, `backend/Dockerfile`, `frontend/Dockerfile`, `compose.yaml`, `.env.example`, `docs/checks/verify_infra.py`, `docs/security/dependency-security-audit.md`)  
**Profile**: General Project  
**Integrity Mode**: Development (Authoritative: `ORIGINAL_REQUEST.md` line 468)  
**Verdict**: **CLEAN**  

### Phase Results
- **Hardcoded Result Detection**: PASS — `docs/checks/verify_infra.py` contains 0 hardcoded booleans or test bypasses. Negative failure injection tests proved authentic assertion enforcement.
- **Facade Detection**: PASS — All directives in `deploy/nginx.conf`, `compose.yaml`, and Dockerfiles represent genuine container configurations and security policies.
- **Supply Chain Integrity**: PASS — Strictly 6 core production Python packages in `backend/requirements.txt` and 3 runtime Node.js packages in `frontend/package.json`. `git diff` is completely empty (0 dependency drift).
- **Test Integrity & Anti-Weakening**: PASS — 0 test files in `backend/tests/` were modified, commented out, or disabled. Only `backend/tests/conftest.py` had `sys.path` addition for agnostic runner invocation.
- **Oracle Integrity**: PASS — Existing specification oracles (`verify_workflow.py`, `verify_reports.py`, `verify_plan.py`) were untouched (0 git diff).
- **Behavioral Verification**: PASS — All 4 oracles passed (exit code 0). All 128 backend pytest tests passed (128 passed, 0 failed, exit code 0).

---

## 1. Observation

### 1.1. Dependency Drift Check
Tool command executed: `git diff backend/requirements.txt frontend/package.json`  
Verbatim output:
```
(empty output — exit code 0)
```
No external packages were introduced. The project adheres to Ponytail principles.

### 1.2. Existing Tests & Oracles Tampering Check
Tool command executed: `git diff backend/tests/`  
Verbatim output:
```diff
diff --git a/backend/tests/conftest.py b/backend/tests/conftest.py
index 1d6228c..d3141f1 100644
--- a/backend/tests/conftest.py
+++ b/backend/tests/conftest.py
@@ -1,5 +1,10 @@
+import sys
 from pathlib import Path
 
+backend_dir = Path(__file__).resolve().parent.parent
+if str(backend_dir) not in sys.path:
+    sys.path.insert(0, str(backend_dir))
+
 import pytest
 from fastapi.testclient import TestClient
```
Tool command executed: `git diff docs/checks/verify_workflow.py docs/checks/verify_reports.py docs/checks/verify_plan.py`  
Verbatim output:
```
(empty output — exit code 0)
```
Zero test logic was altered, deleted, weakened, or skipped. Existing oracles remained untouched.

### 1.3. Infrastructure File Modifications
Tool command executed: `git diff deploy/nginx.conf backend/Dockerfile frontend/Dockerfile compose.yaml .env.example`  
Verbatim output:
```diff
diff --git a/.env.example b/.env.example
index 99b5138..0d66023 100644
--- a/.env.example
+++ b/.env.example
@@ -13,3 +13,12 @@ DEMO_MANAGER_A_PASSWORD=dev_only_manager_a_change_me
 DEMO_MANAGER_B_PASSWORD=dev_only_manager_b_change_me
 DEMO_SUPERVISOR_PASSWORD=dev_only_supervisor_change_me
 DEMO_ADMINISTRATOR_PASSWORD=dev_only_administrator_change_me
+
+# Optional backend configuration (defaults shown)
+APP_ENV=development
+AUTH_MODE=oidc
+STORAGE_DIR=storage
+LMS_INTEGRATION_MODE=mock
+WEBSITE_INTEGRATION_MODE=mock
+LMS_BASE_URL=https://rtkb.zion-lms.ru
+WEBSITE_BASE_URL=https://it-school.rt.ru
diff --git a/backend/Dockerfile b/backend/Dockerfile
index 0db57b8..903203b 100644
--- a/backend/Dockerfile
+++ b/backend/Dockerfile
@@ -6,7 +6,9 @@ ENV PYTHONDONTWRITEBYTECODE=1 \
 WORKDIR /app
 COPY requirements.txt ./requirements.txt
 RUN python -m pip install --no-cache-dir -r requirements.txt \
-    && useradd --create-home --uid 10001 appuser
+    && useradd --create-home --uid 10001 appuser \
+    && mkdir -p /app/storage \
+    && chown -R appuser:appuser /app/storage
 COPY --chown=appuser:appuser app ./app
 USER appuser
 EXPOSE 8000
diff --git a/compose.yaml b/compose.yaml
index de11d32..2c3a912 100644
--- a/compose.yaml
+++ b/compose.yaml
@@ -82,6 +82,8 @@ services:
       - /bin/sh
       - -ec
       - python -m app.seed --init-db && exec uvicorn app.main:app --host 0.0.0.0 --port 8000
+    volumes:
+      - storage-data:/app/storage
     depends_on:
       postgres:
         condition: service_healthy
@@ -113,3 +115,4 @@ services:
 
 volumes:
   postgres-data:
+  storage-data:
diff --git a/deploy/nginx.conf b/deploy/nginx.conf
index face1b3..563099b 100644
--- a/deploy/nginx.conf
+++ b/deploy/nginx.conf
@@ -23,9 +23,12 @@ http {
         server_name localhost;
         root /usr/share/nginx/html;
         index index.html;
-        client_max_body_size 2m;
+        client_max_body_size 25m;
+        add_header X-Frame-Options SAMEORIGIN always;
         add_header X-Content-Type-Options nosniff always;
         add_header Referrer-Policy strict-origin-when-cross-origin always;
+        add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self' http: ws:;" always;
+        add_header Permissions-Policy "geolocation=(), camera=(), microphone=()" always;
 
         location = /_frontend_health {
             access_log off;
diff --git a/frontend/Dockerfile b/frontend/Dockerfile
index ef32861..e495dc2 100644
--- a/frontend/Dockerfile
+++ b/frontend/Dockerfile
@@ -8,7 +8,7 @@ RUN pnpm build
 
 FROM nginx:1.28-alpine
 COPY deploy/nginx.conf /etc/nginx/nginx.conf
-COPY --from=build /app/dist /usr/share/nginx/html
+COPY --from=build --chown=nginx:nginx /app/dist /usr/share/nginx/html
 USER nginx
 EXPOSE 8080
 ENTRYPOINT ["nginx", "-g", "daemon off;"]
```

### 1.4. Negative Failure Injection on `docs/checks/verify_infra.py`
To verify that `docs/checks/verify_infra.py` is not a facade or hardcoded dummy script, two negative tests were executed in an isolated temporary environment:

1. **Negative Test 1 (Missing compose.yaml)**:
   - Command: Subprocess execution of `verify_infra.py` in directory without `compose.yaml`
   - Result: Returncode = 1, Stderr: `FAIL: Missing compose file at /tmp/tmpqwqf0ohs/compose.yaml`
2. **Negative Test 2 (Corrupted Nginx body size limit: 2m instead of 25m)**:
   - Command: Subprocess execution of `verify_infra.py` with `client_max_body_size 2m;`
   - Result: Returncode = 1, Stderr: `FAIL: nginx client_max_body_size must be 25m, got 2m`

This proves `verify_infra.py` enforces real invariants and immediately fails if any requirement is violated.

### 1.5. Independent Execution of All 4 Verification Oracles
Tool command executed: `python3 docs/checks/verify_workflow.py && python3 docs/checks/verify_reports.py && python3 docs/checks/verify_plan.py && python3 docs/checks/verify_infra.py`  
Verbatim output:
```
PASS: 13 working states, 2 terminal states, 29 transitions, 1 initial state.
PASS: unique codes, references, source mapping, required branches and policies.
PASS: every state is reachable; every working state can complete or cancel.
PASS: terminal states have no exits; conditions are declarative proposals.
PASS FX-S01 (snapshot)
PASS FX-S02 (snapshot)
PASS FX-S03 (snapshot)
PASS FX-S04 (snapshot)
PASS FX-S05 (snapshot)
PASS FX-S06 (snapshot)
PASS FX-S07 (snapshot)
PASS FX-A01 (activity)
PASS FX-A02 (activity)
PASS FX-A03 (activity)
PASS FX-A04 (activity)
PASS FX-A05 (activity)
VERIFIED 6 interactions, 23 canonical events, 3 delivery examples, 12 exact report cases
PASS gate D: 29 tasks, 85-145 person-days
PASS gate P-ready: 38 tasks, 114-197 person-days
PASS gate P-done: 39 tasks, 118-204 person-days
PASS gate O: 40 tasks, 121-209 person-days
PASS: 40 tasks, no dependency cycles, all stage totals match.
PASS: R01-R29 mapped to existing tasks and 30 acceptance scenarios.
PASS: compose.yaml defines all 4 services, healthcheck probes, healthy dependencies, and storage-data volume.
PASS: deploy/nginx.conf configured with 25m limit, matched to backend files.py (26,214,400 bytes), and full security headers.
PASS: Dockerfiles enforce non-root execution (appuser:10001, nginx) and /app/storage permission setup.
PASS: .env.example contains all required environment variables; repository contains 0 hardcoded secrets.
ALL INFRASTRUCTURE AND DEVSECOPS CHECKS PASSED.
```
Exit code: 0.

### 1.6. Independent Execution of Full Pytest Suite (128 Tests)
Tool command executed: `backend/.venv/bin/python -m pytest backend/tests/ -v`  
Verbatim output summary:
```
================= 128 passed, 2 warnings in 104.73s (0:01:44) ==================
```
Exit code: 0. 100% of the 128 tests passed.

### 1.7. Supply Chain Security Document Inspection
Document: `docs/security/dependency-security-audit.md`
- Audited against installed packages via `backend/.venv/bin/pip list` and `frontend/package.json`.
- All 6 backend core production packages (`fastapi`, `uvicorn`, `SQLAlchemy`, `psycopg`, `PyJWT`, `pydantic`), 2 dev packages (`pytest`, `httpx`), and all 27 transitive packages are accurately catalogued with exact installed versions.
- All frontend packages (`keycloak-js 26.2.4`, `react 19.3.0`, `react-dom 19.3.0`, `vite 8.3.0`, `typescript 7.0.2`) and transitive packages in `pnpm-lock.yaml` (69 total) are documented.
- 0 CVE claims cross-referenced with known security advisories (e.g. nanoid 3.3.19 patch against CVE-2026-67213/67214; starlette 1.6.0; anyio 4.15.1).
- 0 third-party reporting libraries confirmed: XLSX (`backend/app/reports_export.py:generate_xlsx_report`) and PDF (`backend/app/reports_export.py:generate_pdf_report`) are built entirely on Python standard library modules (`zipfile`, `xml.sax`, `io`).

### 1.8. Secret Leak Detection
Tool command executed: `git grep -i -E "password\s*=\s*['\"][^'\"]+['\"]" -- ':!*.json' ':!*.md' ':!*.example'`  
Result: 0 committed plaintext passwords. Live `.env` file does not exist in repo root (`ls -la .env` returned code 2). `.gitignore` ignores `.env` and `.env.*`.

---

## 2. Logic Chain

1. **Premise**: An authentic implementation requires that all claimed enhancements (DevSecOps, supply chain security, verification scripts) correspond to actual, non-trivial changes in the codebase that enforce the intended behaviors.
2. **Observation**: `git diff` confirms exact, surgical modifications to `deploy/nginx.conf` (`client_max_body_size 25m;`, 5 security headers), `backend/Dockerfile` (`mkdir -p /app/storage && chown -R appuser:appuser /app/storage`, `USER appuser`), `frontend/Dockerfile` (`USER nginx`, `--chown=nginx:nginx`), and `compose.yaml` (`storage-data` volume mount, healthchecks, dependencies).
3. **Premise**: Integrity forbids test tampering, test weakening, or falsifying oracle outputs.
4. **Observation**: `git diff backend/tests/` reveals zero modifications to any test logic across all 128 tests (only a path resolution helper in `conftest.py`). The existing oracles (`verify_workflow.py`, `verify_reports.py`, `verify_plan.py`) have zero git diff.
5. **Premise**: A verification oracle (`verify_infra.py`) must be capable of failing if requirements are not met, rather than returning hardcoded success.
6. **Observation**: Negative failure injection tests proved that removing `compose.yaml` or altering `client_max_body_size` in `nginx.conf` causes `verify_infra.py` to immediately exit with code 1 and descriptive error messages.
7. **Premise**: Under the authoritative request and AGENTS.md Ponytail guidelines, zero new dependencies must be added to `backend/requirements.txt` or `frontend/package.json`.
8. **Observation**: `git diff backend/requirements.txt frontend/package.json` is completely empty.
9. **Premise**: Empirical execution of test suites and oracles must succeed without bypasses.
10. **Observation**: Direct execution of all 4 verification oracles yielded PASS (exit code 0), and execution of pytest over `backend/tests/` passed 128 out of 128 tests with zero failures.
11. **Conclusion**: The sprint deliverables are fully authentic, functional, and devoid of cheating, facades, or integrity violations.

---

## 3. Caveats

- Live deployment inside a real Docker daemon was not executed directly in this audit turn because Docker daemon access is sandboxed in this environment; however, static syntactic and architectural validation of `compose.yaml`, `Dockerfile`s, and `nginx.conf` was verified completely by `verify_infra.py` and direct code inspection.

---

## 4. Conclusion

**Verdict: CLEAN**

The sprint deliverables for Infrastructure & Supply Chain Security Audit (DevSecOps) strictly adhere to all project contracts, security invariants (152-FZ, non-root containers, CSP headers, 25 MB parity), and Ponytail architectural principles. No hardcoded test results, facade implementations, test weakening, or unauthorized dependency additions were found.

---

## 5. Verification Method

To independently verify these findings, run the following commands from the repository root:

1. **Verify zero dependency drift**:
   ```bash
   git diff backend/requirements.txt frontend/package.json
   # Output must be empty
   ```

2. **Verify zero test tampering**:
   ```bash
   git diff backend/tests/
   # Only conftest.py sys.path adjustment should be present
   ```

3. **Verify all 4 verification oracles**:
   ```bash
   python3 docs/checks/verify_workflow.py && \
   python3 docs/checks/verify_reports.py && \
   python3 docs/checks/verify_plan.py && \
   python3 docs/checks/verify_infra.py
   # All 4 must report PASS and exit code 0
   ```

4. **Verify full test suite (128 tests)**:
   ```bash
   backend/.venv/bin/python -m pytest backend/tests/ -v
   # All 128 tests must pass (100% OK)
   ```
