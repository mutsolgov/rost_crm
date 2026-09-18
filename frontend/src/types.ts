export interface AppConfig {
  auth_mode: 'demo' | 'oidc';
  oidc: { url: string; realm: string; client_id: string } | null;
  demo_users: { id: string; name: string; role: string }[];
}
export interface User {
  id: string; name: string; role: string; permissions: string[];
  team_id: string | null; auth_mode: string;
}
export interface Catalogs {
  organizations: { id: string; name: string; type: string }[];
  programs: { id: string; name: string; direction_id: string; direction_name: string }[];
  products: { id: string; name: string; vendor: string }[];
  owners: { id: string; name: string }[];
  directions: { id: string; name: string }[];
}
export interface Workflow {
  name: string; version: number; initial_state: string;
  states: { code: string; name: string; kind: string; source_step?: number }[];
}
export interface Interaction {
  id: string; title: string;
  organization_id: string; organization_name: string;
  program_id: string | null; program_name: string | null;
  product_id: string | null; product_name: string | null;
  direction_name: string | null; cycle_label: string;
  owner_id: string; owner_name: string; state: string; state_name: string;
  workflow_version: string | number; revision: number;
  created_at: string; updated_at: string; closed_at: string | null;
}
export interface Transition {
  code: string; to: string; name: string;
  comment_required: boolean; condition_refs: string[];
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
export interface InteractionDetail extends Interaction {
  allowed_transitions: Transition[];
  events: WorkflowEvent[];
  comments: Comment[];
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

