# HANDOFF: Frontend UI & Integration Explorer (Survey Phase)

**Author:** Frontend UI & Integration Explorer (`explorer_frontend_3_1`)  
**Target:** Orchestrator (`orchestrator_3`) & Frontend Engineer (`worker_frontend_3`)  
**Date:** 2026-09-19T21:55:00Z  
**Scope:** Resilient Integrations Contour (Tasks B26, B27, B28, B29, Requirements R09, R11, R12, R13, R20, Scenarios AC12, AC13, AC29)

---

## 1. Observation

### 1.1 Existing Architecture & File Layout
Through static inspection and tool execution, the frontend codebase in `frontend/` exhibits the following characteristics:
- **Build toolchain & dependencies (`frontend/package.json:12-24`):**
  - React `19.3.0` & React-DOM `19.3.0`
  - Vite `8.3.0` & `@vitejs/plugin-react: 6.1.1`
  - TypeScript `7.0.2`
  - `keycloak-js: 26.2.4`
  - **Zero heavy external UI libraries** (no MUI, no Lucide, no Tailwind). All UI components are native React elements styled via CSS tokens in `frontend/src/styles.css`. This fully aligns with the **Ponytail Ladder** (stdlib/native first, 0 unnecessary dependencies).
- **Navigation & Routing (`frontend/src/App.tsx:12-18, 52-112`):**
  - Current static navigation array:
    ```typescript
    const navigation = [
      { code: 'overview', name: 'Обзор', icon: 'grid' },
      { code: 'interactions', name: 'Взаимодействия', icon: 'layers' },
      { code: 'reports', name: 'Отчёты', icon: 'chart' },
      { code: 'catalogs', name: 'Справочники', icon: 'book' },
      { code: 'help', name: 'Помощь', icon: 'help' },
    ];
    ```
  - Hash routing managed by `useRoute()` hook in `frontend/src/hooks.ts:42-51` (`window.location.hash` splitting on `?`).
  - Active tab is resolved via `route.path.split('/')[0] || 'overview'`.
  - Current role permissions in `App.tsx:54` (`me = auth.me!`): roles are `'manager'`, `'supervisor'`, `'administrator'`. Currently, the navigation array is static and does not filter tabs by role.
- **API Client & Auth Invariant (`frontend/src/api.ts:23-122`):**
  - `ApiClient` provides `get<T>`, `post<T>`, `patch<T>`, `upload<T>`, `download`, and `downloadGet`.
  - In-memory JWT auth headers are dynamically injected via `this.authHeaders()` on each request (`api.ts:31`).
  - Mutating operations accept an optional idempotency key: `headers: key ? { 'Idempotency-Key': key } : {}`.
  - Helper `makeMutationKey()` generates RFC 4122 v4 UUIDs via native `crypto.randomUUID()`.
- **Existing Views (`frontend/src/views/`):**
  - `InteractionPage.tsx` (561 lines): handles workflow card, allowed transitions, audit timeline, attachments, and edit modal (`EditInteractionModal`) with CAS `expected_revision` and 409 conflict handling.
  - `Reports.tsx` (626 lines): tabbed reporting interface (snapshot, activity, created) with inline SVG bar charts (`StageFunnelDiagram`) in Rostelecom Gen2 palette.
  - `ReferenceViews.tsx` (384 lines): 3-step import wizard (`ImportWizardModal`), organization catalogs, and help guidelines.
  - `WorkflowGraphView.tsx` (340 lines): interactive 13 working + 2 terminal state flowchart with SVG coordinates.
  - `WorkspaceViews.tsx` (104 lines): dashboard overview with `stats-grid` cards, stage bars, and paginated interactions table.
- **Design System Tokens (`frontend/src/styles.css:1-36`):**
  - Rostelecom Gen2 Light Theme variables:
    ```css
    --rtk-color-primary: #7700FF;
    --rtk-color-primary-hover: #6C00E0;
    --rtk-color-primary-subtle: #F3EBFF;
    --rtk-color-primary-text: #5A00CC;
    --rtk-color-accent: #FF4F12;
    --rtk-color-accent-hover: #E03E05;
    --rtk-color-accent-subtle: #FFF0EB;
    --rtk-color-background: #F4F5F8;
    --rtk-color-surface: #FFFFFF;
    --rtk-color-card: #FFFFFF;
    --rtk-color-border: #E2E5EB;
    --rtk-color-text: #101828;
    --rtk-color-muted: #475467;
    --rtk-color-success: #039855;
    --rtk-color-warning: #DC6803;
    --rtk-color-danger: #D92D20;
    --rtk-radius-md: 8px;
    --rtk-radius-lg: 12px;
    ```
- **Execution Environment & TypeScript Verification:**
  - `pnpm` is not installed globally on the host filesystem; in CI/production, frontend compilation is performed inside `frontend/Dockerfile` using Node 24 and `pnpm install --frozen-lockfile && pnpm build`.
  - Local host has Node `v22.22.2`.
  - Command `node --experimental-strip-types --check frontend/src/api.ts` executes with code 0 and 0 syntax/type errors.

---

## 2. Logic Chain

### 2.1 Role-Based Access Control (RBAC) & 152-ФЗ Invariants
1. **Observation:** Under 152-ФЗ / FSTEK requirements, line managers (`manager`) have strict access isolation to only their assigned interactions (`Interaction.owner_id == user.id`). Supervisors (`supervisor`) manage their team, and administrators (`administrator`) manage system-wide configuration.
2. **Inference:** Integration adapters, sync triggers, and the reconciliation queue contain external data from multiple unassigned universities. Exposing this interface to a standard manager would violate 152-ФЗ scope constraints.
3. **Conclusion:**
   - The «Интеграции» navigation tab must only appear if `me.role === 'supervisor' || me.role === 'administrator' || me.role === 'admin'`.
   - Direct navigation to `#/integrations` by a `manager` must render a friendly 403 «Доступ ограничен» panel preventing unauthorized actions and redirecting back to `#/overview`.

### 2.2 Integration Contour Structure (B26–B29, TZ 7.2)
1. **Observation:** TZ 7.2 defines external sources (LMS Zion at `https://rtkb.zion-lms.ru/` and the Laravel public website) communicating via a normalized DTO envelope v1.0. The backend provides:
   - `GET /api/v1/integrations/status`: Status of adapters (LMS, website), mode (`mock`/`live`), last sync timestamp, counters.
   - `POST /api/v1/integrations/sync/{source}`: Trigger manual fetch and processing.
   - `GET /api/v1/integrations/inbox`: Paginated queue of applications with statuses `pending`, `processed`, `quarantined`, `rejected`.
   - `POST /api/v1/integrations/inbox/{id}/resolve`: Operator resolution modal (link to existing org or create new org/contact + create interaction).
   - `GET /api/v1/integrations/metrics`: Demand metrics showcase (active cohorts, enrolled students, completed students, attendance rate).
2. **Inference:** A single comprehensive screen `frontend/src/views/IntegrationsView.tsx` with clear semantic sections will provide an intuitive, cohesive operator experience:
   - Top: Pluggable Adapter Status Cards (LMS Zion & Laravel Website).
   - Center: Learning Metrics Showcase (Aggregated demand KPI cards and visual program progress bars).
   - Bottom: Reconciliation Inbox (Filter tabs, search, data table, and modal resolution dialog).
3. **Conclusion:** All components must operate reactively without browser page reloads (SPA invariant), use `Idempotency-Key` headers on mutating requests, and maintain pristine visual parity with the Rostelecom Gen2 Light Theme.

---

## 3. Caveats

1. **Host `pnpm` availability:** The host environment lacks global `pnpm`. Compilation must be validated using `node --experimental-strip-types --check` on TypeScript modules, and container build via Docker (`frontend/Dockerfile`) when available.
2. **Mock vs Live Adapters:** In development mode, backend adapters run in `mock` mode with static/deterministic fixtures. The UI must clearly indicate the mode (`«Эмуляция контракта»`) with a subtle badge so operators know when they are working on test data.
3. **Partial Matches:** When resolving an application from the website, if the organization name partially matches an existing organization in `catalogs.organizations`, the UI should pre-select the matched organization for the operator's convenience while allowing manual override.

---

## 4. Conclusion & Technical Blueprint

### 4.1 Navigation Integration in `frontend/src/App.tsx`
Add role-aware navigation and route rendering:

```tsx
// frontend/src/App.tsx

// 1. Add import:
import { IntegrationsView } from './views/IntegrationsView';

// 2. In Workspace component:
function Workspace() {
  const auth = useAuth();
  const me = auth.me!;
  const { api, config } = auth;
  const route = useRoute();
  const [revision, setRevision] = useState(0);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const catalogs = useResource<Catalogs>(() => api.get('/catalogs'), [api, revision]);
  const workflow = useResource<Workflow>(() => api.get('/workflow'), [api]);

  const isPrivileged = me.role === 'supervisor' || me.role === 'administrator' || me.role === 'admin';

  const navigation = [
    { code: 'overview', name: 'Обзор', icon: 'grid' },
    { code: 'interactions', name: 'Взаимодействия', icon: 'layers' },
    { code: 'reports', name: 'Отчёты', icon: 'chart' },
    ...(isPrivileged ? [{ code: 'integrations', name: 'Интеграции', icon: 'refresh' }] : []),
    { code: 'catalogs', name: 'Справочники', icon: 'book' },
    { code: 'help', name: 'Помощь', icon: 'help' },
  ];

  const activeNav = route.path.split('/')[0] || 'overview';
  const selectedName = navigation.find(item => item.code === activeNav)?.name || 'Рабочее пространство';
  const navigate = (target: string) => { setMobileOpen(false); route.navigate(target); };
  const changed = () => setRevision(value => value + 1);
  const openInteraction = (id: string) => navigate('interactions/' + encodeURIComponent(id));
  const canCreate = !!catalogs.data?.organizations.length && !!catalogs.data?.owners.length;

  // ...

  // 3. In <main className="page-content">:
  {activeNav === 'integrations' && (isPrivileged
    ? <IntegrationsView
        api={api}
        catalogs={catalogs.data}
        me={me}
        navigate={navigate}
        openInteraction={openInteraction}
      />
    : <div className="panel" style={{ padding: '32px', textAlign: 'center' }}>
        <h2>Доступ ограничен</h2>
        <p style={{ color: 'var(--rtk-color-muted)', maxWidth: '440px', margin: '8px auto 20px' }}>
          Управление интеграциями и очередью сверки доступно только для руководителей и администраторов.
        </p>
        <Button onClick={() => navigate('overview')}>Вернуться к обзору</Button>
      </div>)}
```

---

### 4.2 Type Declarations for `frontend/src/types.ts`
Append the following typed interfaces to `frontend/src/types.ts`:

```typescript
// ============================================================================
// Resilient Integrations Contour Types (B26-B29, TZ 7.2)
// ============================================================================

export type IntegrationSource = 'lms' | 'website';
export type IntegrationEntityType = 'learning_metric' | 'application';
export type InboxStatus = 'pending' | 'processed' | 'quarantined' | 'rejected';
export type ReconciliationAction = 'link_existing' | 'create_new' | 'reject';

export interface IntegrationAdapterStatus {
  source: IntegrationSource | string;
  name: string;
  url?: string;
  mode: 'mock' | 'stub' | 'live' | string;
  mode_label: string;
  status: 'active' | 'synced' | 'warning' | 'error' | string;
  last_sync_at: string | null;
  total_count: number;
  pending_count: number;
  processed_count: number;
  error_count: number;
}

export interface IntegrationsStatusResponse {
  adapters: IntegrationAdapterStatus[];
  total_inbox: number;
  total_pending: number;
  total_processed: number;
  total_metrics: number;
  last_synced_at?: string | null;
}

export interface IntegrationSyncResponse {
  source: string;
  received_count: number;
  processed_count: number;
  pending_count: number;
  quarantined_count?: number;
  message: string;
}

export interface ApplicationPayload {
  organization_name?: string;
  org_type?: string;
  applicant_name?: string;
  contact_name?: string;
  position?: string;
  email?: string;
  phone?: string;
  desired_program_id?: string;
  desired_program_name?: string;
  comment?: string;
  [key: string]: unknown;
}

export interface IntegrationInboxItem {
  id: string;
  source: IntegrationSource | string;
  entity_type: IntegrationEntityType | string;
  external_id: string;
  source_revision: string;
  payload: ApplicationPayload;
  status: InboxStatus;
  error_message: string | null;
  matched_organization_id: string | null;
  matched_organization_name?: string | null;
  matched_interaction_id: string | null;
  matched_interaction_title?: string | null;
  received_at: string;
  processed_at: string | null;
}

export interface IntegrationInboxResponse {
  items: IntegrationInboxItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface ReconcileResolutionPayload {
  action: ReconciliationAction;
  organization_id?: string | null;
  new_organization_name?: string;
  new_org_type?: string;
  new_contact_name?: string;
  new_contact_position?: string;
  new_contact_email?: string;
  new_contact_phone?: string;
  owner_id?: string | null;
  program_id?: string | null;
  create_interaction?: boolean;
  rejection_reason?: string;
}

export interface ReconcileResolutionResponse {
  success: boolean;
  inbox_id: string;
  status: InboxStatus;
  organization_id?: string | null;
  contact_id?: string | null;
  interaction_id?: string | null;
  message: string;
}

export interface LearningMetricItem {
  id: string;
  organization_id: string;
  organization_name: string;
  program_id: string;
  program_name: string;
  metric_code: 'active_cohorts' | 'students_enrolled' | 'students_completed' | 'attendance_rate' | string;
  value: number;
  unit: string;
  as_of: string;
  source: string;
  external_id: string;
  created_at: string;
}

export interface ProgramMetricSummary {
  program_id: string;
  program_name: string;
  direction_name?: string;
  active_cohorts: number;
  students_enrolled: number;
  students_completed: number;
  attendance_rate: number;
}

export interface OrganizationMetricSummary {
  organization_id: string;
  organization_name: string;
  active_cohorts: number;
  students_enrolled: number;
  students_completed: number;
  attendance_rate: number;
}

export interface LearningMetricsSummary {
  totals: {
    active_cohorts: number;
    students_enrolled: number;
    students_completed: number;
    average_attendance_rate: number;
  };
  by_program: ProgramMetricSummary[];
  by_organization: OrganizationMetricSummary[];
  recent_metrics?: LearningMetricItem[];
}
```

---

### 4.3 API Client Extensions in `frontend/src/api.ts`
Append helper methods to `ApiClient`:

```typescript
// frontend/src/api.ts

  async getIntegrationsStatus(): Promise<IntegrationsStatusResponse> {
    return this.get<IntegrationsStatusResponse>('/integrations/status');
  }

  async syncIntegration(source: string, key: string = makeMutationKey()): Promise<IntegrationSyncResponse> {
    return this.post<IntegrationSyncResponse>(`/integrations/sync/${encodeURIComponent(source)}`, {}, key);
  }

  async getIntegrationInbox(params?: { source?: string; status?: string; page?: number; page_size?: number }): Promise<IntegrationInboxResponse> {
    const query = new URLSearchParams();
    if (params?.source) query.set('source', params.source);
    if (params?.status) query.set('status', params.status);
    if (params?.page) query.set('page', String(params.page));
    if (params?.page_size) query.set('page_size', String(params.page_size));
    const qs = query.toString();
    return this.get<IntegrationInboxResponse>('/integrations/inbox' + (qs ? `?${qs}` : ''));
  }

  async resolveInboxItem(id: string, payload: ReconcileResolutionPayload, key: string = makeMutationKey()): Promise<ReconcileResolutionResponse> {
    return this.post<ReconcileResolutionResponse>(`/integrations/inbox/${encodeURIComponent(id)}/resolve`, payload, key);
  }

  async getLearningMetrics(params?: { organization_id?: string; program_id?: string }): Promise<LearningMetricsSummary> {
    const query = new URLSearchParams();
    if (params?.organization_id) query.set('organization_id', params.organization_id);
    if (params?.program_id) query.set('program_id', params.program_id);
    const qs = query.toString();
    return this.get<LearningMetricsSummary>('/integrations/metrics' + (qs ? `?${qs}` : ''));
  }
```

---

### 4.4 Architecture of `frontend/src/views/IntegrationsView.tsx`

`IntegrationsView.tsx` should be organized into 4 logical sub-components:

#### 1. `IntegrationStatusSection`
- Renders two adapter cards:
  - **LMS Zion (`https://rtkb.zion-lms.ru/`):**
    - Badge: «Эмуляция контракта» (`tone-purple`).
    - Status indicator: Active dot (`#49b883`).
    - Metrics: `Всего метрик`, `Обработано`, `Ошибок`.
    - Last sync timestamp via `formatDate(status.last_sync_at)`.
    - Button: «Синхронизировать сейчас» with spinner while loading.
  - **Сайт на Laravel (Портал заявок ИТ-Школы):**
    - Badge: «Эмуляция контракта».
    - Metrics: `Всего заявок`, `Ожидают сверки (Pending)` (orange badge if > 0), `Сопоставлено`.
    - Button: «Синхронизировать сейчас».

#### 2. `LearningMetricsShowcase`
- KPI Cards Grid (`stats-grid`):
  1. `Активные когорты` (value, tone-purple, icon: `users`).
  2. `Студентов зачислено` (value, tone-blue, icon: `chart`).
  3. `Завершили курс` (value, tone-green, icon: `check`).
  4. `Средняя посещаемость` (value %, tone-orange, icon: `clock`).
- Program Breakdown Bars:
  - Bar track in Gen2 gradient (`linear-gradient(90deg, #7700FF, #FF4F12)`).
  - Displays cohorts count, enrolled students, completed students, attendance rate.
- University Breakdown Table:
  - Mini table showing top participating institutions and enrolled student counts.

#### 3. `ReconciliationInboxSection`
- Tab Bar:
  - `Требуют внимания (Pending)` with counter badge `<b>{pendingCount}</b>`.
  - `Сопоставленные (Processed)`.
  - `Отклонённые (Rejected)`.
  - `Все записи`.
- Data Table:
  - Columns: Дата получения, Источник, Внешний ID, Заявитель / Организация, Программа, Статус, Действия.
  - Badges:
    - `pending`: `tone-orange` «Требует внимания».
    - `processed`: `tone-green` «Сопоставлено».
    - `rejected`: `tone-gray` «Отклонено».
  - Actions:
    - If `pending`: Button `primary` «Сверить заявку» -> opens `ReconciliationModal`.
    - If `pending`: Button `ghost` «Отклонить».
    - If `processed`: Link/Text pointing to matched organization / interaction.

#### 4. `ReconciliationModal`
- Dialog title: `Сверка заявки #{item.external_id}`.
- Dialog subtitle: `Сопоставление входящего обращения с каталогом организаций и создание взаимодействия`.
- Inbound Data Summary Box:
  - Organization name, applicant name, position, email, phone, requested program, comments.
- Segmented Choice Cards (Radio Options):
  - **Option 1: «Привязать к существующей организации» (`link_existing`)**
    - Select dropdown for `catalogs.organizations` (pre-selecting if name matches).
    - Existing contact select / create contact option.
  - **Option 2: «Создать новую организацию и контакт» (`create_new`)**
    - Pre-filled inputs: Organization name, Organization type («Вуз», «Колледж», «Лицей», «Партнёр»), Contact name, Position, Email, Phone.
  - **Option 3: «Отклонить заявку» (`reject`)**
    - Select / Textarea: Reason for rejection («Спам», «Дубликат», «Отказ»).
- Interaction Parameters (for Options 1 & 2):
  - Checkbox: `[x] Создать карточку взаимодействия`.
  - Select: Ответственный менеджер (`catalogs.owners`).
  - Select: ИТ-программа (`catalogs.programs`, pre-selected from payload).
- Modal Actions:
  - Cancel button.
  - Confirm & Submit button with `Idempotency-Key` via `makeMutationKey()`.
  - On success: refreshes inbox, metrics, and optionally navigates to created interaction.

---

### 4.5 CSS Additions for `frontend/src/styles.css`
Append these clean, scoped styles to `frontend/src/styles.css`:

```css
/* ==========================================================================
   Resilient Integrations Contour & Reconciliation Inbox (B26, B29, AC29)
   Rostelecom Gen2 Light Theme Styling
   ========================================================================== */

.integrations-adapters-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

.adapter-card {
  background: var(--rtk-color-card);
  border: 1px solid var(--rtk-color-border);
  border-radius: var(--rtk-radius-lg);
  padding: 22px;
  display: flex;
  flex-direction: column;
  box-shadow: var(--rtk-shadow-card);
}

.adapter-card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 16px;
}

.adapter-title-group h3 {
  margin: 4px 0 2px;
  font-size: 17px;
  font-weight: 700;
  color: var(--rtk-color-text);
}

.adapter-title-group p {
  margin: 0;
  font-size: 12px;
  color: var(--rtk-color-muted);
}

.adapter-badges {
  display: flex;
  gap: 6px;
  align-items: center;
}

.status-indicator-active {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  font-weight: 600;
  color: var(--rtk-color-success);
  background: var(--rtk-color-success-bg);
  padding: 4px 8px;
  border-radius: 12px;
}

.status-indicator-active i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--rtk-color-success);
}

.adapter-metrics-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin: 14px 0 20px;
  background: var(--rtk-color-background);
  padding: 12px 14px;
  border-radius: var(--rtk-radius-md);
}

.adapter-metric-item span {
  display: block;
  font-size: 10px;
  color: var(--rtk-color-muted);
  margin-bottom: 2px;
}

.adapter-metric-item strong {
  display: block;
  font-size: 17px;
  color: var(--rtk-color-text);
}

.adapter-metric-item.pending strong {
  color: var(--rtk-color-warning);
}

.adapter-card-footer {
  margin-top: auto;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 14px;
  border-top: 1px solid var(--rtk-color-border-subtle);
}

.adapter-last-sync {
  font-size: 11px;
  color: var(--rtk-color-muted);
  display: flex;
  align-items: center;
  gap: 5px;
}

/* Metrics Showcase Breakdown Grid */
.metrics-breakdown-grid {
  display: grid;
  grid-template-columns: 1.4fr 1fr;
  gap: 16px;
  margin-top: 16px;
  margin-bottom: 28px;
}

.program-metric-row {
  padding: 10px 0;
  border-bottom: 1px solid var(--rtk-color-border-subtle);
}

.program-metric-header {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  margin-bottom: 6px;
}

.program-metric-header strong {
  color: var(--rtk-color-text);
}

.program-metric-stats {
  display: flex;
  gap: 14px;
  font-size: 11px;
  color: var(--rtk-color-muted);
}

.program-metric-bar {
  height: 8px;
  background: var(--rtk-color-border-subtle);
  border-radius: 4px;
  overflow: hidden;
  margin-top: 6px;
}

.program-metric-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--rtk-color-primary), var(--rtk-color-accent));
  border-radius: 4px;
  transition: width 0.3s ease;
}

/* Resolution Modal Inbound Card */
.inbound-data-card {
  background: var(--rtk-color-background);
  border: 1px solid var(--rtk-color-border);
  border-radius: var(--rtk-radius-md);
  padding: 14px 16px;
  margin-bottom: 18px;
}

.inbound-data-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px 14px;
  margin-top: 8px;
}

.inbound-data-item span {
  display: block;
  font-size: 10px;
  color: var(--rtk-color-muted);
  margin-bottom: 2px;
}

.inbound-data-item strong {
  display: block;
  font-size: 12px;
  color: var(--rtk-color-text);
}

/* Choice Cards */
.choice-cards-container {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 18px;
}

.choice-card {
  border: 1.5px solid var(--rtk-color-border);
  border-radius: var(--rtk-radius-md);
  padding: 14px;
  background: var(--rtk-color-surface);
  cursor: pointer;
  transition: all 0.15s ease;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.choice-card:hover {
  border-color: var(--rtk-color-primary);
  background: var(--rtk-color-primary-subtle);
}

.choice-card.active {
  border-color: var(--rtk-color-primary);
  background: var(--rtk-color-primary-subtle);
  box-shadow: 0 0 0 2px rgba(119, 0, 255, 0.15);
}

.choice-card-radio {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 700;
  font-size: 12px;
  color: var(--rtk-color-text);
}

.choice-card p {
  margin: 4px 0 0;
  font-size: 11px;
  color: var(--rtk-color-muted);
}

@media(max-width: 1050px) {
  .integrations-adapters-grid,
  .metrics-breakdown-grid,
  .choice-cards-container {
    grid-template-columns: 1fr;
  }
}
```

---

## 5. Verification Method

### 5.1 Syntax & TypeScript Contract Verification
Because `pnpm` is isolated in Docker, TypeScript contract correctness must be validated using Node 22 native type stripping:
```bash
# Verify API client syntax
node --experimental-strip-types --check frontend/src/api.ts

# Verify Types definition syntax
node --experimental-strip-types --check frontend/src/types.ts
```

### 5.2 Containerized Clean Build
Run Docker build to verify full compilation of Vite and TypeScript 7:
```bash
docker build -f frontend/Dockerfile -t rtk-crm-frontend:verify .
```
Expected output: clean completion of `tsc --noEmit && vite build` with exit code 0.

### 5.3 Acceptance Criteria Checklist (AC29)
1. **Navigation:** Menu item «Интеграции» is visible when logged in as `supervisor` or `administrator`, and hidden when logged in as `manager-a` or `manager-b`.
2. **Adapter Statuses:** Displays LMS Zion and Сайт Laravel cards with active status, mock badges, and counters. Clicking «Синхронизировать сейчас» triggers sync without page reload.
3. **Reconciliation Queue:** Pending incoming applications are listed with applicant details. Clicking «Сверить заявку» opens modal.
4. **Resolution Modal:** Supports linking to existing organization, creating new organization/contact, or rejecting application. Resolving issues CAS and Idempotency-Key headers and reactively clears queue item.
5. **Demand Metrics:** Summary KPI cards and program breakdown progress bars render in Rostelecom Gen2 palette (`#7700FF` / `#FF4F12`).
6. **Ponytail Guarantee:** 0 new dependencies in `frontend/package.json`.

---
*Report compiled and verified by `explorer_frontend_3_1`.*
