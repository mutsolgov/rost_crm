# DISPATCH — Frontend Survey Explorer

## Mission
Analyze the current frontend implementation:
- frontend/src/styles.css
- frontend/src/views/InteractionPage.tsx
- frontend/src/api.ts or equivalent client
- frontend package.json, build setup
- Existing UI components, dialogs/modals, form state

Assess changes needed for:
- R3: Rostelecom Light Theme tokens in frontend/src/styles.css (--rtk-color-primary, hover, accent, background, card, border, text, muted, radii).
- R3: In InteractionPage.tsx, eliminate item.allowed_transitions[0] single-choice limitation. Render all allowed_transitions with appropriate variants (primary, secondary, danger), modal for comment_required transitions.
- R3: Add modal/form "Редактировать параметры" (program, product compatible with program, cycle_label, contact, contract) with PATCH /api/v1/interactions/{id}, expected_revision, Idempotency-Key, SPA reactive update and 409 handling.
- Verify TypeScript types and pnpm build requirements.

Write report to your working directory: handoff.md
