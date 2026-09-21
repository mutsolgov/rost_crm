# DISPATCH — Frontend & UX Engineer (M2 / R3)

## Mission
Implement requirement R3 for tasks B15, B20:
- `frontend/src/styles.css`:
  - Add Rostelecom Gen2 Light Theme CSS variables to `:root`:
    `--rtk-color-primary: #7700FF`, hover `--rtk-color-primary-hover: #6C00E0`, `--rtk-color-accent: #FF4F12`, `--rtk-color-background: #F4F5F8`, `--rtk-color-card: #FFFFFF`, `--rtk-color-border: #E2E5EB`, `--rtk-color-text: #101828`, `--rtk-color-muted: #475467`, `--rtk-radius-md: 8px`, `--rtk-radius-lg: 12px`.
  - Update buttons, cards, panels, inputs, and tables to use these CSS variables.
- `frontend/src/types.ts`:
  - Add interfaces `OrganizationContact`, `Contract`, `License`, `ProgramProductLink`.
  - Extend `Catalogs` with `contacts`, `contracts`, `licenses`.
  - Extend `Interaction` with `contact_id`, `contact_name`, `contract_id`, `contract_number`, `license_id`, `license_status`.
  - Extend `Transition` with `kind`.
  - Add `InteractionUpdatePayload`.
- `frontend/src/api.ts`:
  - Add `patch<T>(path: string, body: unknown, key?: string): Promise<T>` method to `ApiClient` with `Idempotency-Key` header.
- `frontend/src/views/InteractionPage.tsx`:
  - Remove `item.allowed_transitions[0]` single-choice limitation.
  - Render ALL available transitions from `allowed_transitions` with semantic button variants (`primary` for forward/skip, `secondary` for rework/cycle, `danger` for cancel).
  - Open `TransitionCommentModal` for transitions with `comment_required: true` (mandatory non-empty comment).
  - Add "Редактировать параметры" button and modal dialog (`EditInteractionModal`):
    - Select program, filter compatible products, cycle_label, select organization contact and contract.
    - Submit `PATCH /api/v1/interactions/{id}` with `expected_revision: item.revision` and `Idempotency-Key: crypto.randomUUID()`.
    - Reactive SPA update on success without page reload (`window.location.reload()` is forbidden).
    - Friendly error message on 409 Conflict without clearing user-entered form data.
  - Extend `detail-facts` to display contact name, contract number, license status.

## Exclusive Write Ownership
You own exclusively:
- `frontend/src/styles.css`
- `frontend/src/types.ts`
- `frontend/src/api.ts`
- `frontend/src/views/InteractionPage.tsx`
(and any helper UI component in `frontend/src/` if strictly needed, e.g. `frontend/src/forms.tsx`).
Do NOT edit any backend files.

## References
- /home/muhammad/Dev/HACKATHON/LCT/rost_crm/ORIGINAL_REQUEST.md
- /home/muhammad/Dev/HACKATHON/LCT/rost_crm/AGENTS.md
- /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/orchestrator_1/PROJECT.md
- /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/explorer_frontend_survey_2/handoff.md
- Skill: /home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/skills/ponytail/SKILL.md

## Verification
Run build and typecheck:
`cd frontend && pnpm build`
Ensure zero TypeScript errors and successful production bundle build.
Write report to handoff.md.
