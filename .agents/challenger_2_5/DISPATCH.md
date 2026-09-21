# DISPATCH — challenger_2_5

## Task
You are challenger_2_5: File Limits, Persistence & Supply Chain Adversarial Challenger for rost_crm.
Your working directory is: /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/challenger_2_5
Authoritative Request: /home/muhammad/Dev/HACKATHON/LCT/rost_crm/ORIGINAL_REQUEST.md (see Section "## Follow-up — 2026-09-20T17:14:24Z")
Project Blueprint: /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/orchestrator_5/PROJECT.md

Empirically challenge:
1. File upload boundary consistency:
   - Verify `backend/app/files.py:14`: `MAX_FILE_SIZE = 26_214_400  # 25 MB`.
   - Verify `deploy/nginx.conf:26`: `client_max_body_size 25m;` (25 * 1024 * 1024 = 26,214,400 bytes).
   - Verify frontend upload limits in `frontend/src/views/InteractionPage.tsx:13` (`25 * 1024 * 1024`).
   - Confirm strict mathematical parity across all layers.
2. Container non-root execution and permission model:
   - In `backend/Dockerfile`, verify that `/app/storage` is created and `chown -R appuser:appuser /app/storage` happens BEFORE switching to `USER appuser`.
   - In `frontend/Dockerfile`, verify `USER nginx` and `--chown=nginx:nginx` for static assets.
3. Supply chain & Ponytail integrity challenge:
   - Check `backend/requirements.txt` strictly contains 6 packages.
   - Run adversarial search for any 3rd-party reporting libraries (`openpyxl`, `reportlab`, `xlsxwriter`, `weasyprint`, `pandas`, `pdfkit`) in `backend/app/` — must find 0.
   - Verify `git diff backend/requirements.txt frontend/package.json` is completely empty.
4. Run all verification oracles and test suite:
   - Run `python3 docs/checks/verify_infra.py`
   - Run `cd backend && .venv/bin/python -m pytest tests/ -q`

Write your handoff report to `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/challenger_2_5/handoff.md`.
Conclude with a clear verdict: `APPROVE` or `REQUEST_CHANGES`.
Send message to parent when completed.

## 2026-09-20T17:30:18Z
You are challenger_2_5.
Your working directory is: /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/challenger_2_5
Authoritative Request: /home/muhammad/Dev/HACKATHON/LCT/rost_crm/ORIGINAL_REQUEST.md (see Section "## Follow-up — 2026-09-20T17:14:24Z")
Read your detailed task in: /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/challenger_2_5/DISPATCH.md
Read the project contracts in: /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/orchestrator_5/PROJECT.md

Empirically challenge 25 MB file upload limit mathematical parity across all layers (nginx 25m, files.py 26_214_400, frontend), container non-root permission model, and Ponytail 0-dependency-growth invariant.
Run all tests and oracles.
Write your challenger report with verdict (APPROVE / REQUEST_CHANGES) to /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/challenger_2_5/handoff.md.
Send message to parent when completed.

