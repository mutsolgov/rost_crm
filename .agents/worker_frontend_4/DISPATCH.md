## 2026-09-19T19:24:54Z
You are the Frontend & UX Lead for the rost_crm project (Iteration 2: Remediation of Catalog Import Wizard).

Your working directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_frontend_4
Project workspace root: /home/muhammad/Dev/HACKATHON/LCT/rost_crm
Original user request file: /home/muhammad/Dev/HACKATHON/LCT/rost_crm/ORIGINAL_REQUEST.md

Read the following reference documents first:
- /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/auditor_victory_2/handoff.md (CRITICAL: Contains exact reproduction of Victory Auditor failure and patch recommendations)
- /home/muhammad/Dev/HACKATHON/LCT/rost_crm/ORIGINAL_REQUEST.md
- /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/orchestrator_2/PROJECT.md
- AGENTS.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

You EXCLUSIVELY OWN:
- frontend/src/views/ReferenceViews.tsx
- frontend/src/types.ts

Your mission:
1. In `frontend/src/views/ReferenceViews.tsx`:
   - In `handleCommit`: Send JSON payload with the validated rows from `previewData.preview_rows.filter(r => r.is_valid).map(r => r.data || r)` using `api.post('/imports/organizations/commit', { rows: validRows }, makeMutationKey())`.
   - In preview table rows (lines 210-230): Safely read both flat attributes and nested `data`:
     - Row number: `row.row_number ?? row.row_index ?? (i + 1)`
     - Organization name: `row.organization_name || row.data?.name || '—'`
     - Org type: `row.org_type || row.data?.type || '—'`
     - Program: `row.program_name || row.data?.program || '—'`
     - Product: `row.product_name || row.data?.product || '—'`
   - In error rendering (line 192): Do NOT join objects directly (`.join('; ')` creates `[object Object]`). Format each error:
     `previewData.errors.map(err => typeof err === 'string' ? err : `${err.field ? err.field + ': ' : ''}${err.message || JSON.stringify(err)}`).join('; ')`
2. In `frontend/src/types.ts`:
   - Ensure `ImportPreviewRow` includes both flat properties (`organization_name`, `org_type`, `row_number`, `contact_name`, `program_name`, `product_name`) and optional `data?: Record<string, any>`.
3. Verify TypeScript syntax:
   `node --experimental-strip-types frontend/src/types.ts`
   `node --experimental-strip-types frontend/src/api.ts`

Deliver your handoff report in:
/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_frontend_4/handoff.md
Send a message to parent when complete with summary and path to your handoff.
