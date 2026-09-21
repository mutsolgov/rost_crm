# Context for Frontend & UX Lead (Iteration 2 Remediation)

- Working Directory: /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_frontend_4
- Objective: Remediate the Catalog Import Wizard contract and UI bindings identified by the Victory Auditor.
- Reference:
  - /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/auditor_victory_2/handoff.md
  - /home/muhammad/Dev/HACKATHON/LCT/rost_crm/ORIGINAL_REQUEST.md
  - frontend/src/views/ReferenceViews.tsx
  - frontend/src/types.ts
- Remediation Requirements:
  1. In `frontend/src/views/ReferenceViews.tsx` (`handleCommit`):
     - In `handleCommit`, obtain the valid rows from `previewData.preview_rows.filter(r => r.is_valid).map(r => r.data || r)` or send the file.
     - Even better, send JSON:
       ```typescript
       const validRows = previewData.preview_rows.filter(r => r.is_valid).map(r => r.data || {
         name: r.organization_name,
         type: r.org_type,
         contact_name: r.contact_name,
         position: r.contact_position,
         email: r.contact_email,
         phone: r.contact_phone,
         program: r.program_name,
         product: r.product_name,
       });
       const resp = await api.post<ImportCommitResponse>(
         '/imports/organizations/commit',
         { rows: validRows },
         makeMutationKey()
       );
       ```
  2. In `frontend/src/views/ReferenceViews.tsx` (preview table data binding):
     - Safely read both flat and nested properties:
       `row.row_number ?? row.row_index ?? (i + 1)`
       `row.organization_name || row.data?.name || '—'`
       `row.org_type || row.data?.type || '—'`
       `row.program_name || row.data?.program || '—'`
       `row.product_name || row.data?.product || '—'`
  3. In `frontend/src/views/ReferenceViews.tsx` (error formatting):
     - Fix `previewData.errors` rendering so it does NOT produce `[object Object]`.
     - Render: `previewData.errors.map(err => typeof err === 'string' ? err : `${err.field ? err.field + ': ' : ''}${err.message || JSON.stringify(err)}`).join('; ')`
  4. In `frontend/src/types.ts`:
     - Update `ImportPreviewRow` to include both flat properties (`organization_name`, `org_type`, `row_number`, `contact_name`, `program_name`, `product_name`) and optional `data` dictionary.
  5. Verify TypeScript syntax with `node --experimental-strip-types`.
- Output: handoff.md in /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/worker_frontend_4/handoff.md
