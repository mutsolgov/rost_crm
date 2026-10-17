"""Facade for CRM services providing 100% backward compatibility.

All business logic has been decomposed into `app.services_modules.*`.
This facade re-exports all 54 functions and constants for seamless imports
and monkeypatching in existing test suites and domain modules.
"""

from .models import CommandResult, utcnow
from .services_modules.common import (
    _authz_epoch_before_flush,
    _authz_epoch_on_transaction_end,
    _json_safe,
    aware,
    iso,
)
from .services_modules.idempotency import (
    begin_command,
    finish_command,
)
from .services_modules.interactions import (
    _advance_state_visit,
    add_comment,
    append_event,
    assign,
    attachment_dict,
    cas,
    catalogs,
    comment_dict,
    commit_workflow_migration,
    create_delivery,
    create_interaction,
    dashboard,
    delivery_dict,
    delivery_item_dict,
    detail,
    event_dict,
    get_interaction_deliveries,
    interaction_dict,
    list_interactions,
    preview_workflow_migration,
    transition,
    update_interaction,
    validate_filters,
    validate_subject,
)
from .services_modules.rbac import (
    allowed_owner,
    bump_authz_epoch,
    check_authz_epoch,
    ensure_authz_epoch_valid,
    get_authz_epoch,
    has_organization_access,
    permissions,
    require_permission,
    revoke_organization_access,
    scope_clause,
    scoped_interaction,
    set_organization_access,
    update_user_access,
    visible_organization_ids,
)
from .services_modules.reports import (
    activity,
    created_report,
    enqueue_background_job,
    freeze_report_dataset,
    get_background_job_scoped,
    get_frozen_report_rows,
    _mark_job_outbox_processed,
    process_background_job,
    snapshot,
)

__all__ = [
    # Group A: RBAC & Authorization (16 functions)
    "aware",
    "iso",
    "permissions",
    "require_permission",
    "get_authz_epoch",
    "bump_authz_epoch",
    "check_authz_epoch",
    "ensure_authz_epoch_valid",
    "set_organization_access",
    "revoke_organization_access",
    "update_user_access",
    "scope_clause",
    "scoped_interaction",
    "visible_organization_ids",
    "has_organization_access",
    "allowed_owner",
    # Group B: Common & Session Event Listeners (3 functions)
    "_authz_epoch_on_transaction_end",
    "_authz_epoch_before_flush",
    "_json_safe",
    # Group C: Idempotency (2 functions)
    "begin_command",
    "finish_command",
    # Group D: Interactions & Workflow (24 functions)
    "validate_subject",
    "attachment_dict",
    "delivery_item_dict",
    "delivery_dict",
    "interaction_dict",
    "event_dict",
    "comment_dict",
    "append_event",
    "detail",
    "cas",
    "create_interaction",
    "_advance_state_visit",
    "transition",
    "add_comment",
    "assign",
    "update_interaction",
    "get_interaction_deliveries",
    "create_delivery",
    "catalogs",
    "validate_filters",
    "list_interactions",
    "dashboard",
    "preview_workflow_migration",
    "commit_workflow_migration",
    # Group E: Reports & Background Jobs (9 functions)
    "snapshot",
    "activity",
    "created_report",
    "freeze_report_dataset",
    "get_frozen_report_rows",
    "enqueue_background_job",
    "_mark_job_outbox_processed",
    "process_background_job",
    "get_background_job_scoped",
    # Backward compatibility models
    "CommandResult",
    "utcnow",
]
