# Handoff Report — explorer_devsecops_5_1

## 1. Observation

Direct investigation of target configuration files and related source modules revealed the following exact lines and settings:

### 1.1. `deploy/nginx.conf`
- **File path**: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/deploy/nginx.conf`
- **Line 26**: `client_max_body_size 2m;`
  - In conflict with ТЗ requirement R1 / Acceptance Criteria specifying attachment uploads up to 25 MB.
  - In `backend/app/files.py:14`: `MAX_FILE_SIZE = 26_214_400  # 25 MB`.
  - In `frontend/src/views/InteractionPage.tsx:13`: `const MAX_FILE_SIZE = 25 * 1024 * 1024; // 25 MB (152-ФЗ)`.
  - Any file upload between 2 MB and 25 MB is currently rejected by Nginx with `413 Request Entity Too Large` before reaching FastAPI.
- **Lines 27-28**:
  ```nginx
  add_header X-Content-Type-Options nosniff always;
  add_header Referrer-Policy strict-origin-when-cross-origin always;
  ```
- **Missing headers**:
  - `X-Frame-Options: SAMEORIGIN` (missing; required for Clickjacking mitigation).
  - `Content-Security-Policy` (missing; required with directives `default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self' http: ws:;`).
  - `Permissions-Policy: geolocation=(), camera=(), microphone=()` (missing).
- **Inheritance & Scope**:
  - `add_header` and `client_max_body_size` are defined at the `server` block level. None of the child `location` blocks (`/_frontend_health`, `/api/`, `~ ^/(docs...`, `/`) define their own `add_header`, meaning all headers defined in `server` block are properly inherited across all routes.
  - Temporary paths (lines 15-19) and pid (line 2) are directed to `/tmp/`, which is world-writable, allowing non-root execution.

### 1.2. `backend/Dockerfile`
- **File path**: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/backend/Dockerfile`
- **Lines 8-11**:
  ```dockerfile
  RUN python -m pip install --no-cache-dir -r requirements.txt \
      && useradd --create-home --uid 10001 appuser
  COPY --chown=appuser:appuser app ./app
  USER appuser
  ```
- **Findings**:
  - User creation: `useradd --create-home --uid 10001 appuser` is present.
  - Execution user: `USER appuser` is present.
  - **Defect**: The storage directory `/app/storage` is NOT created during the build!
  - Because `WORKDIR /app` is created by `root` with `0755` permissions, unprivileged `appuser` cannot create `/app/storage` at runtime if it does not already exist.
  - In `backend/app/files.py:113-114`:
    `target_dir = Path(storage_dir) / "attachments" / item.id`
    `target_dir.mkdir(parents=True, exist_ok=True)`
    Without a pre-existing writable `/app/storage`, this call fails with `PermissionError: [Errno 13] Permission denied`.

### 1.3. `frontend/Dockerfile`
- **File path**: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/frontend/Dockerfile`
- **Lines 1, 9, 12**:
  ```dockerfile
  FROM node:24-alpine AS build
  ...
  FROM nginx:1.28-alpine
  COPY deploy/nginx.conf /etc/nginx/nginx.conf
  COPY --from=build /app/dist /usr/share/nginx/html
  USER nginx
  EXPOSE 8080
  ENTRYPOINT ["nginx", "-g", "daemon off;"]
  ```
- **Findings**:
  - Multi-stage build stages match specifications: `node:24-alpine` for build, `nginx:1.28-alpine` for runtime.
  - Container executes under `USER nginx` (non-root).
  - `nginx.conf` sets `listen 8080` (unprivileged port > 1024), eliminating need for `CAP_NET_BIND_SERVICE`.
  - Improvement: In runtime stage, static build files should be explicitly chowned: `COPY --from=build --chown=nginx:nginx /app/dist /usr/share/nginx/html`.

### 1.4. `compose.yaml`
- **File path**: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/compose.yaml`
- **Lines 65-96 (`api` service)**:
  - Has `build`, `environment`, `command`, `depends_on`, `healthcheck`, `restart`.
  - **Defect**: NO `volumes:` mount for `/app/storage`. File uploads in `api` are currently written to ephemeral container storage and lost across rebuilds/restarts.
- **Lines 114-116 (`volumes:` section)**:
  ```yaml
  volumes:
    postgres-data:
  ```
  - **Defect**: Named volume `storage-data` is MISSING from top-level `volumes:`.
- **Healthcheck & depends_on audit**:
  - `postgres`: healthcheck `pg_isready -h 127.0.0.1 -U rtk_bootstrap -d postgres`, interval 5s, timeout 3s, retries 20, start_period 10s. (Valid)
  - `keycloak`: depends_on `postgres: condition: service_healthy`. Healthcheck checks `/health/ready` on 9000 for `"status": "UP"`, interval 10s, timeout 5s, retries 30, start_period 60s. (Valid)
  - `api`: depends_on `postgres: condition: service_healthy` AND `keycloak: condition: service_healthy`. Healthcheck checks `http://127.0.0.1:8000/health/ready`, interval 10s, timeout 5s, retries 10, start_period 15s. (Valid)
  - `frontend`: depends_on `api: condition: service_healthy`. Healthcheck checks `http://127.0.0.1:8080/_frontend_health`, interval 10s, timeout 3s, retries 5. (Valid)

---

## 2. Logic Chain

1. **Upload Size Parity**:
   - `backend/app/files.py` enforces a 25 MB limit (`MAX_FILE_SIZE = 26_214_400`).
   - Frontend UI forms enforce a 25 MB limit (`MAX_FILE_SIZE = 25 * 1024 * 1024`).
   - `deploy/nginx.conf` acts as the reverse proxy for all `/api/` traffic. Its current setting `client_max_body_size 2m;` rejects all attachments > 2 MB at the proxy layer with HTTP 413.
   - Updating `client_max_body_size` to `25m;` removes this bottleneck, establishing full contract alignment between Frontend, Nginx, and Backend.

2. **Defense-in-Depth HTTP Hardening**:
   - According to security standards (152-ФЗ, ФСТЭК №117, OWASP):
     - `X-Frame-Options: SAMEORIGIN` prevents clickjacking by forbidding embedding the application in third-party iframes.
     - `X-Content-Type-Options: nosniff` stops browsers from MIME-sniffing away from the declared content-type.
     - `Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self' http: ws:;` restricts unauthorized script injection and resource loading while supporting Keycloak OIDC and WebSockets.
     - `Permissions-Policy: geolocation=(), camera=(), microphone=()` blocks browser access to sensitive hardware sensors that are unnecessary for enterprise CRM operations.
   - Adding these headers with `always` directive ensures they are sent on both 2xx and error (4xx/5xx) responses.

3. **Non-Root Container Storage Permissions**:
   - `backend/Dockerfile` runs under `USER appuser` (uid 10001).
   - Because container filesystem root `/app` is owned by `root:root`, `appuser` cannot create `/app/storage` dynamically.
   - Pre-creating `/app/storage` during the build and running `chown -R appuser:appuser /app/storage` ensures the directory exists and has write permissions.
   - When Docker attaches named volume `storage-data` at `/app/storage`, Docker preserves the pre-existing container directory ownership (`appuser:appuser`), preventing volume permission conflicts.

4. **Persistence Architecture in Docker Compose**:
   - Adding `storage-data` to root `volumes:` and mounting `storage-data:/app/storage` in the `api` container ensures that uploaded documents, signed contracts, and material attachments are persisted across container restarts, migrations, and updates.
   - All services already enforce strict `condition: service_healthy` dependencies (`keycloak -> postgres`, `api -> postgres + keycloak`, `frontend -> api`), ensuring deterministic and error-free boot sequences.

---

## 3. Caveats

- **Nginx CSP & Inline Styles/Scripts**:
  - The requested CSP directives contain `'unsafe-inline'` for `script-src` and `style-src`. This is required for Vite production builds with inlined script/style chunks without complex nonce hashing. In future hardened stages, hashes or nonces can be adopted.
- **Named Volume Initialization**:
  - Named volumes inherit the image mount point ownership upon creation. If a volume was previously created with root ownership, running `docker compose down -v` or manually chowning the volume directory may be necessary in local test environments.
- No other caveats; scope is strictly container, proxy, and compose infrastructure.

---

## 4. Conclusion & Concrete Implementation Diffs

All changes are low-risk, non-breaking, and strictly adhere to Ponytail principles (0 new dependencies, native Docker and Nginx directives).

Below are the exact unified diffs to be applied by `worker_devsecops_5_1`:

### 4.1. Diff for `deploy/nginx.conf`
```diff
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
```

### 4.2. Diff for `backend/Dockerfile`
```diff
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
```

### 4.3. Diff for `frontend/Dockerfile`
```diff
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

### 4.4. Diff for `compose.yaml`
```diff
--- a/compose.yaml
+++ b/compose.yaml
@@ -80,6 +80,8 @@ services:
     command:
       - /bin/sh
       - -ec
       - python -m app.seed --init-db && exec uvicorn app.main:app --host 0.0.0.0 --port 8000
+    volumes:
+      - storage-data:/app/storage
     depends_on:
       postgres:
         condition: service_healthy
@@ -113,4 +115,5 @@ services:
 
 volumes:
   postgres-data:
+  storage-data:
```

---

## 5. Verification Method

### 5.1. Automated Test Suites and Oracles
Run the following verification commands to ensure zero regression:
```bash
# 1. Full backend pytest suite (128 passing tests)
cd backend && .venv/bin/python -m pytest tests/ -v

# 2. Existing domain and workflow oracles
python3 docs/checks/verify_workflow.py
python3 docs/checks/verify_reports.py
python3 docs/checks/verify_plan.py

# 3. New infrastructure oracle (once implemented by worker_infra_5_1)
python3 docs/checks/verify_infra.py
```

### 5.2. Docker Compose Syntax and Model Validation
Validate `compose.yaml` structure and variable resolution:
```bash
docker compose --env-file .env.example config
```
Verify that `services.api.volumes` contains `storage-data:/app/storage` and `volumes` contains `storage-data`.

### 5.3. Nginx Configuration Inspection
Verify presence of required directives in `deploy/nginx.conf`:
```bash
grep -E 'client_max_body_size 25m;' deploy/nginx.conf
grep -E 'X-Frame-Options SAMEORIGIN' deploy/nginx.conf
grep -E 'Content-Security-Policy' deploy/nginx.conf
grep -E 'Permissions-Policy' deploy/nginx.conf
```

### 5.4. Invalidation Conditions
- Any occurrence of `client_max_body_size 2m;` in `deploy/nginx.conf`.
- Missing `storage-data` in `compose.yaml`.
- Missing `/app/storage` creation in `backend/Dockerfile`.
- Container user in `backend/Dockerfile` not set to `USER appuser` (uid 10001).
- Container user in `frontend/Dockerfile` not set to `USER nginx`.
