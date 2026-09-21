# Plan: Infrastructure & Supply Chain Security Audit Sprint (DevSecOps)

## Objective
Harden container orchestration, Nginx reverse proxy, and supply chain security for rost_crm, conduct comprehensive security & dependency audit (0 CVEs, Ponytail compliance), implement automated infrastructure verification oracle (`verify_infra.py`), and maintain 100% test pass rate on all tests and oracles.

## Work Breakdown

### Phase 0: Survey & Technical Mapping (3 Explorers)
- **explorer_devsecops_5_1**: Inspect `deploy/nginx.conf`, `backend/Dockerfile`, `frontend/Dockerfile`, `compose.yaml`. Identify exact differences from the security hardening requirements (client_max_body_size 25m, headers, /app/storage ownership, USER appuser/nginx, named volume storage-data, depends_on condition: service_healthy).
- **explorer_supplychain_5_1**: Inspect `backend/requirements.txt`, `backend/requirements-dev.txt`, `frontend/package.json`, `frontend/pnpm-lock.yaml`. Check package versions, licenses, CVE status, and Ponytail compliance (strictly 6 core prod packages, stdlib report generation).
- **explorer_infra_oracle_5_1**: Inspect `.env.example`, code for secrets, existing check oracles in `docs/checks/`, requirements for `verify_infra.py`, and test running setup.

### Phase 1: Implementation Track (3 Specialist Workers)
- **worker_devsecops_5_1**:
  - Update `deploy/nginx.conf` (client_max_body_size 25m, headers: X-Frame-Options, X-Content-Type-Options, CSP, Permissions-Policy).
  - Update `backend/Dockerfile` (create `/app/storage`, chown appuser:appuser, USER appuser uid 10001).
  - Update `frontend/Dockerfile` (node:24-alpine build, nginx:1.28-alpine runtime under USER nginx).
  - Update `compose.yaml` (volume storage-data, depends_on service_healthy for api and frontend).
- **worker_supplychain_5_1**:
  - Generate `docs/security/dependency-security-audit.md` with package registries, versions, licenses, 0 CVE evidence, and Ponytail compliance.
- **worker_infra_5_1**:
  - Audit `.env.example` ensuring all env vars are documented with 0 hardcoded secrets.
  - Implement `docs/checks/verify_infra.py` (executable, checking nginx.conf, compose.yaml, file size consistency with files.py 25 MB, storage-data volume, non-root users, security headers).
  - Run full regression suite: 128 existing tests + verify_workflow.py + verify_reports.py + verify_plan.py + verify_infra.py.

### Phase 2: Independent Verification & Audit Gate
- 2 Reviewers independently checking correctness and spec conformance.
- 2 Challengers checking edge cases and stress testing oracles.
- 1 Forensic Auditor verifying zero cheating / genuine implementation.

### Phase 3: Final Synthesis & Victory Claim
- Verify all ACs satisfied.
- Send completion message to parent Sentinel.
