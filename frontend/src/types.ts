export interface AppConfig {
  auth_mode: 'demo' | 'oidc';
  oidc: { url: string; realm: string; client_id: string } | null;
  demo_users: { id: string; name: string; role: string }[];
}
export interface User {
  id: string; name: string; role: string; permissions: string[];
  team_id: string | null; auth_mode: string;
}
export interface OrganizationContact {
  id: string;
  organization_id: string;
  full_name: string;
  position: string;
  email: string | null;
  phone: string | null;
  active: boolean;
}

export interface Contract {
  id: string;
  organization_id: string;
  number: string;
  signed_on: string | null;
  status: string;
  created_at: string;
}

export interface License {
  id: string;
  organization_id: string;
  product_id: string;
  contract_id: string | null;
  signed_on: string | null;
  term_years: number | null;
  transfer_status: string;
  created_at: string;
}

export interface ProgramProductLink {
  program_id: string;
  product_id: string;
}

export interface InteractionUpdatePayload {
  expected_revision: number;
  title?: string;
  program_id?: string | null;
  product_id?: string | null;
  cycle_label?: string;
  contact_id?: string | null;
  contract_id?: string | null;
  license_id?: string | null;
}

export interface Catalogs {
  organizations: { id: string; name: string; type: string }[];
  programs: { id: string; name: string; direction_id: string; direction_name: string }[];
  products: { id: string; name: string; vendor: string }[];
  owners: { id: string; name: string }[];
  directions: { id: string; name: string }[];
  contacts?: OrganizationContact[];
  contracts?: Contract[];
  licenses?: License[];
  program_products?: ProgramProductLink[];
}
export interface Workflow {
  name: string; version: number; initial_state: string;
  states: { code: string; name: string; kind: string; source_step?: number; outcome?: string }[];
  transitions?: Transition[];
}
export interface Interaction {
  id: string; title: string;
  organization_id: string; organization_name: string;
  program_id: string | null; program_name: string | null;
  product_id: string | null; product_name: string | null;
  direction_name: string | null; cycle_label: string;
  owner_id: string; owner_name: string; state: string; state_name: string;
  workflow_version: string | number; revision: number;
  contact_id?: string | null; contact_name?: string | null;
  contract_id?: string | null; contract_number?: string | null;
  license_id?: string | null; license_status?: string | null;
  created_at: string; updated_at: string; closed_at: string | null;
}
export interface Transition {
  code: string; to: string; name: string;
  comment_required: boolean; condition_refs: string[];
  kind?: 'forward' | 'skip_optional' | 'rework' | 'cycle' | 'cancellation' | string;
}
export interface WorkflowEvent {
  id: string; type: string; effective_at: string; received_at: string;
  sequence: number; actor_name: string;
  from_state?: string; to_state?: string; owner_id?: string; comment?: string;
}
export interface Comment {
  id: string; body: string; author_name: string; created_at: string;
  visit_id?: string; interaction_revision?: number;
}
export interface Attachment {
  id: string;
  interaction_id: string;
  visit_id: string;
  file_name: string;
  file_size: number;
  content_type: string;
  checksum: string;
  uploaded_by: string;
  uploaded_by_name?: string;
  created_at: string;
}

export interface InteractionDetail extends Interaction {
  allowed_transitions: Transition[];
  events: WorkflowEvent[];
  comments: Comment[];
  attachments?: Attachment[];
}
export interface InteractionList {
  items: Interaction[]; total: number; page: number; page_size: number;
}
export interface Dashboard {
  total_interactions: number; total_organizations: number;
  active_interactions: number; completed_interactions: number;
  counts_by_state: { code: string; name: string; count: number }[];
  recent_events: { interaction_id: string; title: string; event_type: string; actor_name: string; at: string }[];
  unassigned_program_count: number;
}
export interface SnapshotQuery {
  as_of: string; knowledge_cutoff?: string; as_of_inclusive: true;
  organization_ids: string[]; program_ids: string[];
  product_ids: string[]; owner_ids: string[];
}
export interface Snapshot {
  report_type: 'snapshot'; as_of: string; knowledge_cutoff: string;
  as_of_inclusive: boolean; generated_at: string;
  rows: {
    interaction_id: string; title: string; organization_name: string;
    program_name: string | null; product_name: string | null;
    state: string; state_name: string; owner_id: string; owner_name: string;
  }[];
  totals: { interactions: number; organizations: number; counts_by_state: Record<string, number> };
}

export interface ActivityQuery {
  from_date: string;
  to_date: string;
  knowledge_cutoff?: string;
  historical_owner_id?: string;
  organization_ids?: string[];
  program_ids?: string[];
  product_ids?: string[];
  owner_ids?: string[];
}

export interface ActivityRow {
  event_id: string;
  interaction_id: string;
  title: string;
  organization_name: string;
  from_state: string;
  to_state: string;
  transition_code: string;
  owner_at_event: string;
  owner_at_event_name: string;
  actor_name: string;
  effective_at: string;
}

export interface ActivityResult {
  report_type: 'activity';
  from_date: string;
  to_date: string;
  knowledge_cutoff: string;
  generated_at: string;
  rows: ActivityRow[];
  totals: { transitions: number; counts_by_to_state: Record<string, number> };
}

export interface CreatedQuery {
  from_date: string;
  to_date: string;
  knowledge_cutoff?: string;
  organization_ids?: string[];
  program_ids?: string[];
  product_ids?: string[];
  owner_ids?: string[];
}

export interface CreatedRow {
  interaction_id: string;
  title: string;
  organization_name: string;
  program_name: string | null;
  product_name: string | null;
  state: string;
  state_name: string;
  owner_id: string;
  owner_name: string;
  created_at: string;
}

export interface CreatedResult {
  report_type: 'created';
  from_date: string;
  to_date: string;
  knowledge_cutoff?: string;
  generated_at: string;
  rows: CreatedRow[];
  totals: { interactions: number; organizations: number; counts_by_state: Record<string, number> };
}

export interface ImportPreviewRow {
  row_number: number;
  organization_name: string;
  org_type: string;
  contact_name?: string;
  contact_position?: string;
  contact_email?: string;
  contact_phone?: string;
  program_name?: string;
  product_name?: string;
  is_valid: boolean;
  errors: string[];
}

export interface ImportPreviewResponse {
  rows_total: number;
  valid_count: number;
  error_count: number;
  preview_rows: ImportPreviewRow[];
  errors: string[];
}

export interface ImportCommitResponse {
  success: boolean;
  rows_total: number;
  imported_count: number;
  created_organizations: number;
  created_contacts: number;
  errors?: string[];
}

// ============================================================================
// Resilient Integrations Contour Types (B26-B29, TZ 7.2)
// ============================================================================

export type IntegrationSource = 'lms' | 'website';
export type IntegrationEntityType = 'learning_metric' | 'application';
export type InboxStatus = 'pending' | 'processed' | 'quarantined' | 'rejected';
export type ReconciliationAction = 'link_existing' | 'create_new' | 'reject';

export interface IntegrationAdapterStatus {
  status: 'ok' | 'degraded' | 'error' | string;
  mode: 'mock' | 'live' | string;
  source: 'lms' | 'website' | string;
  endpoint?: string;
  latency_ms?: number;
  error?: string | null;
}

export interface IntegrationsStatusResponse {
  adapters: IntegrationAdapterStatus[];
  adapters_by_source?: Record<string, IntegrationAdapterStatus>;
  total_inbox: number;
  total_pending: number;
  total_processed: number;
  total_quarantined: number;
  total_rejected: number;
  total_metrics: number;
  last_synced_at: string | null;
}

export interface IntegrationSyncResponse {
  source: string;
  received_count: number;
  processed_count: number;
  pending_count: number;
  skipped_count: number;
  quarantined_count: number;
  message: string;
}

export interface ApplicationPayload {
  organization_name?: string;
  organization_external_id?: string | null;
  representative_name?: string;
  representative_position?: string;
  representative_email?: string;
  representative_phone?: string;
  program_name?: string;
  program_id?: string;
  comments?: string;
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
  received_at: string;
  processed_at: string | null;
}

export interface IntegrationInboxResponse {
  items: IntegrationInboxItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface ReconcileResolveParams {
  action: ReconciliationAction | string;
  organization_id?: string;
  organization_name?: string;
  org_type?: string;
  organization_type?: string;
  contact_id?: string;
  contact_name?: string;
  representative_name?: string;
  representative_position?: string;
  email?: string;
  representative_email?: string;
  phone?: string;
  representative_phone?: string;
  owner_id?: string;
  program_id?: string;
  product_id?: string;
  title?: string;
  interaction_title?: string;
  create_interaction?: boolean;
  cycle_label?: string;
  reason?: string;
  [key: string]: unknown;
}

export interface LearningMetricItem {
  id: string;
  organization_id: string;
  organization_name: string;
  program_id: string;
  program_name: string;
  metric_code: string;
  value: number;
  unit: string;
  as_of: string;
  source: string;
  external_id: string;
}

export interface ProgramMetricSummary {
  program_id: string;
  program_name: string;
  active_cohorts: number;
  students_enrolled: number;
  students_completed: number;
  avg_attendance_rate: number;
}

export interface OrganizationMetricSummary {
  organization_id: string;
  organization_name: string;
  active_cohorts: number;
  students_enrolled: number;
  students_completed: number;
  avg_attendance_rate: number;
}

export interface LearningMetricsSummaryResponse {
  total_cohorts: number;
  total_enrolled: number;
  total_completed: number;
  avg_attendance_rate: number;
  by_program: ProgramMetricSummary[];
  by_organization: OrganizationMetricSummary[];
  metrics: LearningMetricItem[];
}

// Workflow Migration Types (Task B17, R06, AC08)

export interface StatusCollision {
  target_status: string;
  target_name?: string;
  source_statuses: string[];
  reason?: string;
}

export interface WorkflowMigrationPreview {
  from_version: number;
  to_version: number;
  affected_interactions_count: number;
  affected_count?: number;
  status_distribution_before: Record<string, number>;
  status_distribution_after: Record<string, number>;
  unmapped_statuses?: string[];
  collisions: StatusCollision[];
  warnings: string[];
  is_valid: boolean;
  errors?: string[];
}

export interface WorkflowMigrationResult {
  status?: string;
  success?: boolean;
  from_version: number;
  to_version: number;
  migrated_count: number;
  status_distribution?: Record<string, number>;
  timestamp?: string;
  details?: Array<{
    interaction_id: string;
    from_state: string;
    to_state: string;
    revision: number;
  }>;
  errors?: string[];
}

export interface WorkflowMigratePreviewPayload {
  from_version: number;
  to_version: number;
  status_mapping: Record<string, string>;
}

export interface WorkflowMigrateCommitPayload {
  from_version: number;
  to_version: number;
  status_mapping: Record<string, string>;
}

export type WorkflowMigratePreviewResponse = WorkflowMigrationPreview;
export type WorkflowMigrateCommitResponse = WorkflowMigrationResult;
