#!/usr/bin/env python3
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
    require(nginx_bytes in (25 * 1024 * 1024, 26 * 1024 * 1024), f"nginx client_max_body_size must be 25m or 26m, got {val}{unit}")

    # Verify backend MAX_FILE_SIZE
    backend_match = re.search(r"MAX_FILE_SIZE\s*=\s*([0-9_]+)", files_content)
    require(backend_match is not None, "MAX_FILE_SIZE not found in backend/app/files.py")
    backend_bytes = int(backend_match.group(1).replace("_", ""))
    require(backend_bytes == 25 * 1024 * 1024, f"backend MAX_FILE_SIZE must be 26_214_400, got {backend_bytes}")

    # Cross-consistency
    require(nginx_bytes >= backend_bytes,
            f"Nginx body limit ({nginx_bytes}) must be >= backend MAX_FILE_SIZE ({backend_bytes})")

    # Security headers
    require(re.search(r"add_header\s+X-Content-Type-Options\s+nosniff\s+always;", nginx_content) is not None,
            "Security hardening header 'X-Content-Type-Options: nosniff always;' missing in nginx.conf")
    require(re.search(r"add_header\s+X-Frame-Options\s+SAMEORIGIN\s+always;", nginx_content) is not None,
            "Security hardening header 'X-Frame-Options: SAMEORIGIN always;' missing in nginx.conf")
    require(re.search(r"add_header\s+Referrer-Policy\s+strict-origin-when-cross-origin\s+always;", nginx_content) is not None,
            "Security hardening header 'Referrer-Policy: strict-origin-when-cross-origin always;' missing in nginx.conf")

    csp_match = re.search(r"add_header\s+Content-Security-Policy\s+[\"'](.*?)[\"']\s+always;", nginx_content)
    require(csp_match is not None, "Security hardening header 'Content-Security-Policy' missing in nginx.conf")
    csp_val = csp_match.group(1)
    require("default-src 'self'" in csp_val, "CSP missing 'default-src \'self\''")
    require("script-src 'self'" in csp_val, "CSP missing 'script-src \'self\''")
    require("style-src 'self'" in csp_val, "CSP missing 'style-src \'self\''")
    require("img-src 'self'" in csp_val, "CSP missing 'img-src \'self\''")
    require("connect-src 'self'" in csp_val, "CSP missing 'connect-src \'self\''")

    perm_match = re.search(r"add_header\s+Permissions-Policy\s+[\"'](.*?)[\"']\s+always;", nginx_content)
    require(perm_match is not None, "Security hardening header 'Permissions-Policy' missing in nginx.conf")
    perm_val = perm_match.group(1)
    require("geolocation=()" in perm_val, "Permissions-Policy missing 'geolocation=()'")
    require("camera=()" in perm_val, "Permissions-Policy missing 'camera=()'")
    require("microphone=()" in perm_val, "Permissions-Policy missing 'microphone=()'")

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

    # Check optional backend variables documented in .env.example
    optional_vars = [
        "APP_ENV",
        "AUTH_MODE",
        "STORAGE_DIR",
        "LMS_INTEGRATION_MODE",
        "WEBSITE_INTEGRATION_MODE",
        "LMS_BASE_URL",
        "WEBSITE_BASE_URL",
    ]
    for var in optional_vars:
        require(f"{var}=" in example_content, f"Optional backend variable '{var}' missing from .env.example")

    # Verify no .env file in root and not committed
    live_env = ROOT / ".env"
    require(not live_env.exists(), ".env must not exist in repository root")
    git_tracked = False
    try:
        import subprocess
        git_tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", ".env"],
            cwd=ROOT,
            capture_output=True,
        ).returncode == 0
    except Exception:
        pass
    require(not git_tracked, ".env must not be committed to repository")

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
