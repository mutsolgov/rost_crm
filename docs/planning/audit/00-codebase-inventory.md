# Codebase Inventory: `rost_crm`

**Date**: 2026-09-21  
**Commit**: `1c7c0eb`  
**Git Tag**: `audit-baseline-2026-09-21`  
**Scope**: Factual Codebase Inventory (R1: Models & Database, R2: HTTP API & Schemas, R3: Services & Workflow, R4: Frontend Structure & Components, R5: Tests, Benchmarks & Test Execution)  
**Style**: Strictly neutral factual documentation without subjective evaluation or qualitative assessments.

---

## 1. Database Layer and SQLAlchemy Declarative Models (Section R1)

### 1.1 Database Engine, Session, and Metadata Configuration

Source files: `backend/app/db.py`, `backend/app/main.py` (lines 111–130), `backend/app/config.py` (lines 6–34).

#### Base Metadata Class (`backend/app/db.py:11-12`)
```python
class Base(DeclarativeBase):
    pass
```
All declarative models in the application inherit from this `Base` class and register their table metadata on `Base.metadata`.

#### Engine Configuration (`backend/app/db.py:15-29`)
- Function: `@lru_cache def get_engine(url=None)`
- Default connection URL: extracted from `get_settings().database_url` (`postgresql+psycopg://rtk:rtk@localhost:5432/rtk_crm` in `backend/app/config.py:15`).
- Pool options: `pool_pre_ping=True`.
- SQLite specific behavior:
  - If `url.startswith("sqlite")`: `connect_args={"check_same_thread": False, "timeout": 20}`.
  - If `":memory:" in url`: `poolclass=StaticPool`.
  - Event listener on connect (`@event.listens_for(engine, "connect")`):
    - Executes `PRAGMA foreign_keys=ON`.
    - Executes `PRAGMA busy_timeout=20000`.
- Environment constraint (`backend/app/config.py:27-28`):
  - `if self.database_url.startswith("sqlite") and self.app_env not in {"development", "test"}: raise RuntimeError("SQLite is an explicit development/test fallback only")`.

#### Session Management (`backend/app/db.py:32-34`, `backend/app/main.py:114`)
- Dependency `get_db(request: Request)`: yields `request.app.state.session_factory()`.
- Session factory instantiation (`backend/app/main.py:114`):
  `sessionmaker(bind=engine, class_=Session, expire_on_commit=False, autoflush=False)`.
- Metadata table creation helper (`backend/app/db.py:41-43`):
  `def init_db(): Base.metadata.create_all(get_engine())`.

---

### 1.2 Model Summary

- Total SQLAlchemy models inheriting from `Base`: 19 (all declared in `backend/app/models.py`).
- Total database tables in `Base.metadata`: 19.
- Schema migration files: No Alembic migrations or `.sql` migration scripts exist; table creation is managed via `Base.metadata.create_all()`.
- Global helper functions in `backend/app/models.py`:
  - `new_id()` (lines 10–11): returns `str(uuid4())`.
  - `utcnow()` (lines 14–15): returns `datetime.now(timezone.utc)`.

---

### 1.3 Detailed Specifications of All 19 Models

#### 1. `User`
- **Class**: `User`
- **Table Name**: `users` (`backend/app/models.py:19`)
- **Table Arguments**: None

| Column Name | Mapped Type | SQLAlchemy Type | Nullable | Primary Key | Default | Foreign Key | Indexes / Constraints |
|---|---|---|---|---|---|---|---|
| `id` | `Mapped[str]` | `String(64)` | `False` | `True` | None | None | Primary Key |
| `keycloak_subject` | `Mapped[str]` | `String(255)` | `False` | `False` | None | None | `unique=True` |
| `name` | `Mapped[str]` | `String(200)` | `False` | `False` | None | None | None |
| `role` | `Mapped[str]` | `String(32)` | `False` | `False` | None | None | None |
| `team_id` | `Mapped[str \| None]` | `String(64)` | `True` | `False` | None | None | None |
| `permissions` | `Mapped[list]` | `JSON` | `False` | `False` | `list` (callable) | None | None |
| `active` | `Mapped[bool]` | `Boolean` | `False` | `False` | `True` (scalar) | None | None |

- **Foreign Keys**: None
- **Unique Constraints**: Single-column unique constraint on `keycloak_subject`.
- **Indexes**: Unique index generated for `keycloak_subject`.

---

#### 2. `Organization`
- **Class**: `Organization`
- **Table Name**: `organizations` (`backend/app/models.py:30`)
- **Table Arguments**: None

| Column Name | Mapped Type | SQLAlchemy Type | Nullable | Primary Key | Default | Foreign Key | Indexes / Constraints |
|---|---|---|---|---|---|---|---|
| `id` | `Mapped[str]` | `String(64)` | `False` | `True` | `new_id` (callable) | None | Primary Key |
| `name` | `Mapped[str]` | `String(250)` | `False` | `False` | None | None | None |
| `type` | `Mapped[str]` | `String(32)` | `False` | `False` | `"university"` (scalar) | None | None |

- **Foreign Keys**: None
- **Unique Constraints**: None
- **Indexes**: Primary Key index on `id`.

---

#### 3. `OrganizationAccess`
- **Class**: `OrganizationAccess`
- **Table Name**: `organization_access` (`backend/app/models.py:37`)
- **Table Arguments**: None

| Column Name | Mapped Type | SQLAlchemy Type | Nullable | Primary Key | Default | Foreign Key | Indexes / Constraints |
|---|---|---|---|---|---|---|---|
| `user_id` | `Mapped[str]` | `String(64)` | `False` | `True` | None | `users.id` | PK (composite part 1) |
| `organization_id` | `Mapped[str]` | `String(64)` | `False` | `True` | None | `organizations.id` | PK (composite part 2) |
| `can_create` | `Mapped[bool]` | `Boolean` | `False` | `False` | `False` (scalar) | None | None |
| `read_all` | `Mapped[bool]` | `Boolean` | `False` | `False` | `False` (scalar) | None | None |

- **Foreign Keys**:
  - `user_id` -> `users.id`
  - `organization_id` -> `organizations.id`
- **Unique Constraints**: Composite Primary Key `(user_id, organization_id)`.
- **Indexes**: Composite Primary Key index.

---

#### 4. `Direction`
- **Class**: `Direction`
- **Table Name**: `directions` (`backend/app/models.py:45`)
- **Table Arguments**: None

| Column Name | Mapped Type | SQLAlchemy Type | Nullable | Primary Key | Default | Foreign Key | Indexes / Constraints |
|---|---|---|---|---|---|---|---|
| `id` | `Mapped[str]` | `String(64)` | `False` | `True` | None | None | Primary Key |
| `name` | `Mapped[str]` | `String(200)` | `False` | `False` | None | None | None |

- **Foreign Keys**: None
- **Unique Constraints**: None
- **Indexes**: Primary Key index on `id`.

---

#### 5. `Program`
- **Class**: `Program`
- **Table Name**: `programs` (`backend/app/models.py:51`)
- **Table Arguments**: None

| Column Name | Mapped Type | SQLAlchemy Type | Nullable | Primary Key | Default | Foreign Key | Indexes / Constraints |
|---|---|---|---|---|---|---|---|
| `id` | `Mapped[str]` | `String(64)` | `False` | `True` | None | None | Primary Key |
| `name` | `Mapped[str]` | `String(200)` | `False` | `False` | None | None | None |
| `direction_id` | `Mapped[str]` | `String(64)` | `False` | `False` | None | `directions.id` | Foreign Key |

- **Foreign Keys**: `direction_id` -> `directions.id`
- **Unique Constraints**: None
- **Indexes**: Primary Key index on `id`.

---

#### 6. `Product`
- **Class**: `Product`
- **Table Name**: `products` (`backend/app/models.py:58`)
- **Table Arguments**: None

| Column Name | Mapped Type | SQLAlchemy Type | Nullable | Primary Key | Default | Foreign Key | Indexes / Constraints |
|---|---|---|---|---|---|---|---|
| `id` | `Mapped[str]` | `String(64)` | `False` | `True` | None | None | Primary Key |
| `name` | `Mapped[str]` | `String(200)` | `False` | `False` | None | None | None |
| `vendor` | `Mapped[str]` | `String(200)` | `False` | `False` | None | None | None |

- **Foreign Keys**: None
- **Unique Constraints**: None
- **Indexes**: Primary Key index on `id`.

---

#### 7. `ProgramProduct`
- **Class**: `ProgramProduct`
- **Table Name**: `program_products` (`backend/app/models.py:65`)
- **Table Arguments**: None

| Column Name | Mapped Type | SQLAlchemy Type | Nullable | Primary Key | Default | Foreign Key | Indexes / Constraints |
|---|---|---|---|---|---|---|---|
| `program_id` | `Mapped[str]` | `String(64)` | `False` | `True` | None | `programs.id` | PK (composite part 1) |
| `product_id` | `Mapped[str]` | `String(64)` | `False` | `True` | None | `products.id` | PK (composite part 2) |

- **Foreign Keys**:
  - `program_id` -> `programs.id`
  - `product_id` -> `products.id`
- **Unique Constraints**: Composite Primary Key `(program_id, product_id)`.
- **Indexes**: Composite Primary Key index.

---

#### 8. `OrganizationContact`
- **Class**: `OrganizationContact`
- **Table Name**: `organization_contacts` (`backend/app/models.py:71`)
- **Table Arguments**: None

| Column Name | Mapped Type | SQLAlchemy Type | Nullable | Primary Key | Default | Foreign Key | Indexes / Constraints |
|---|---|---|---|---|---|---|---|
| `id` | `Mapped[str]` | `String(64)` | `False` | `True` | `new_id` (callable) | None | Primary Key |
| `organization_id` | `Mapped[str]` | `String(64)` | `False` | `False` | None | `organizations.id` | `index=True` (`ix_organization_contacts_organization_id`) |
| `full_name` | `Mapped[str]` | `String(250)` | `False` | `False` | None | None | None |
| `position` | `Mapped[str]` | `String(200)` | `False` | `False` | None | None | None |
| `email` | `Mapped[str \| None]` | `String(200)` | `True` | `False` | None | None | None |
| `phone` | `Mapped[str \| None]` | `String(100)` | `True` | `False` | None | None | None |
| `active` | `Mapped[bool]` | `Boolean` | `False` | `False` | `True` (scalar) | None | None |

- **Foreign Keys**: `organization_id` -> `organizations.id`
- **Unique Constraints**: None
- **Indexes**: `ix_organization_contacts_organization_id` on `['organization_id']`.

---

#### 9. `Contract`
- **Class**: `Contract`
- **Table Name**: `contracts` (`backend/app/models.py:82`)
- **Table Arguments**: None

| Column Name | Mapped Type | SQLAlchemy Type | Nullable | Primary Key | Default | Foreign Key | Indexes / Constraints |
|---|---|---|---|---|---|---|---|
| `id` | `Mapped[str]` | `String(64)` | `False` | `True` | `new_id` (callable) | None | Primary Key |
| `organization_id` | `Mapped[str]` | `String(64)` | `False` | `False` | None | `organizations.id` | `index=True` (`ix_contracts_organization_id`) |
| `number` | `Mapped[str]` | `String(100)` | `False` | `False` | None | None | None |
| `signed_on` | `Mapped[datetime \| None]` | `DateTime(timezone=True)` | `True` | `False` | None | None | None |
| `status` | `Mapped[str]` | `String(50)` | `False` | `False` | `"active"` (scalar) | None | None |
| `created_at` | `Mapped[datetime]` | `DateTime(timezone=True)` | `False` | `False` | `utcnow` (callable) | None | None |

- **Foreign Keys**: `organization_id` -> `organizations.id`
- **Unique Constraints**: None
- **Indexes**: `ix_contracts_organization_id` on `['organization_id']`.

---

#### 10. `License`
- **Class**: `License`
- **Table Name**: `licenses` (`backend/app/models.py:92`)
- **Table Arguments**: None

| Column Name | Mapped Type | SQLAlchemy Type | Nullable | Primary Key | Default | Foreign Key | Indexes / Constraints |
|---|---|---|---|---|---|---|---|
| `id` | `Mapped[str]` | `String(64)` | `False` | `True` | `new_id` (callable) | None | Primary Key |
| `organization_id` | `Mapped[str]` | `String(64)` | `False` | `False` | None | `organizations.id` | `index=True` (`ix_licenses_organization_id`) |
| `product_id` | `Mapped[str]` | `String(64)` | `False` | `False` | None | `products.id` | `index=True` (`ix_licenses_product_id`) |
| `contract_id` | `Mapped[str \| None]` | `String(64)` | `True` | `False` | None | `contracts.id` | `index=True` (`ix_licenses_contract_id`) |
| `signed_on` | `Mapped[datetime \| None]` | `DateTime(timezone=True)` | `True` | `False` | None | None | None |
| `term_years` | `Mapped[int \| None]` | `Integer` | `True` | `False` | None | None | None |
| `transfer_status` | `Mapped[str]` | `String(50)` | `False` | `False` | `"pending"` (scalar) | None | None |
| `created_at` | `Mapped[datetime]` | `DateTime(timezone=True)` | `False` | `False` | `utcnow` (callable) | None | None |

- **Foreign Keys**:
  - `organization_id` -> `organizations.id`
  - `product_id` -> `products.id`
  - `contract_id` -> `contracts.id`
- **Unique Constraints**: None
- **Indexes**:
  - `ix_licenses_organization_id` on `['organization_id']`
  - `ix_licenses_product_id` on `['product_id']`
  - `ix_licenses_contract_id` on `['contract_id']`

---

#### 11. `Interaction`
- **Class**: `Interaction`
- **Table Name**: `interactions` (`backend/app/models.py:104`)
- **Table Arguments**: None

| Column Name | Mapped Type | SQLAlchemy Type | Nullable | Primary Key | Default | Foreign Key | Indexes / Constraints |
|---|---|---|---|---|---|---|---|
| `id` | `Mapped[str]` | `String(64)` | `False` | `True` | `new_id` (callable) | None | Primary Key |
| `title` | `Mapped[str]` | `String(250)` | `False` | `False` | None | None | None |
| `organization_id` | `Mapped[str]` | `String(64)` | `False` | `False` | None | `organizations.id` | `index=True` (`ix_interactions_organization_id`) |
| `program_id` | `Mapped[str \| None]` | `String(64)` | `True` | `False` | None | `programs.id` | Foreign Key |
| `product_id` | `Mapped[str \| None]` | `String(64)` | `True` | `False` | None | `products.id` | Foreign Key |
| `cycle_label` | `Mapped[str]` | `String(100)` | `False` | `False` | None | None | None |
| `owner_id` | `Mapped[str]` | `String(64)` | `False` | `False` | None | `users.id` | `index=True` (`ix_interactions_owner_id`) |
| `contract_id` | `Mapped[str \| None]` | `String(64)` | `True` | `False` | None | `contracts.id` | `index=True` (`ix_interactions_contract_id`) |
| `license_id` | `Mapped[str \| None]` | `String(64)` | `True` | `False` | None | `licenses.id` | `index=True` (`ix_interactions_license_id`) |
| `contact_id` | `Mapped[str \| None]` | `String(64)` | `True` | `False` | None | `organization_contacts.id` | `index=True` (`ix_interactions_contact_id`) |
| `team_id` | `Mapped[str \| None]` | `String(64)` | `True` | `False` | None | None | `index=True` (`ix_interactions_team_id`) |
| `state` | `Mapped[str]` | `String(80)` | `False` | `False` | None | None | None |
| `workflow_version` | `Mapped[int]` | `Integer` | `False` | `False` | `1` (scalar) | None | None |
| `revision` | `Mapped[int]` | `Integer` | `False` | `False` | `1` (scalar) | None | None |
| `visit_id` | `Mapped[str]` | `String(64)` | `False` | `False` | `new_id` (callable) | None | None |
| `created_at` | `Mapped[datetime]` | `DateTime(timezone=True)` | `False` | `False` | `utcnow` (callable) | None | None |
| `updated_at` | `Mapped[datetime]` | `DateTime(timezone=True)` | `False` | `False` | `utcnow` (callable) | None | None |
| `closed_at` | `Mapped[datetime \| None]` | `DateTime(timezone=True)` | `True` | `False` | None | None | None |

- **Foreign Keys**:
  - `organization_id` -> `organizations.id`
  - `program_id` -> `programs.id`
  - `product_id` -> `products.id`
  - `owner_id` -> `users.id`
  - `contract_id` -> `contracts.id`
  - `license_id` -> `licenses.id`
  - `contact_id` -> `organization_contacts.id`
- **Unique Constraints**: None
- **Indexes**:
  - `ix_interactions_organization_id` on `['organization_id']`
  - `ix_interactions_owner_id` on `['owner_id']`
  - `ix_interactions_contract_id` on `['contract_id']`
  - `ix_interactions_license_id` on `['license_id']`
  - `ix_interactions_contact_id` on `['contact_id']`
  - `ix_interactions_team_id` on `['team_id']`

---

#### 12. `Attachment`
- **Class**: `Attachment`
- **Table Name**: `attachments` (`backend/app/models.py:126`)
- **Table Arguments**: None

| Column Name | Mapped Type | SQLAlchemy Type | Nullable | Primary Key | Default | Foreign Key | Indexes / Constraints |
|---|---|---|---|---|---|---|---|
| `id` | `Mapped[str]` | `String(64)` | `False` | `True` | `new_id` (callable) | None | Primary Key |
| `interaction_id` | `Mapped[str]` | `String(64)` | `False` | `False` | None | `interactions.id` | `index=True` (`ix_attachments_interaction_id`) |
| `visit_id` | `Mapped[str]` | `String(64)` | `False` | `False` | None | None | `index=True` (`ix_attachments_visit_id`) |
| `file_name` | `Mapped[str]` | `String(255)` | `False` | `False` | None | None | None |
| `file_path` | `Mapped[str]` | `String(500)` | `False` | `False` | None | None | None |
| `file_size` | `Mapped[int]` | `Integer` | `False` | `False` | None | None | None |
| `content_type` | `Mapped[str]` | `String(100)` | `False` | `False` | None | None | None |
| `checksum` | `Mapped[str]` | `String(64)` | `False` | `False` | None | None | None |
| `uploaded_by` | `Mapped[str]` | `String(64)` | `False` | `False` | None | `users.id` | Foreign Key |
| `created_at` | `Mapped[datetime]` | `DateTime(timezone=True)` | `False` | `False` | `utcnow` (callable) | None | None |

- **Foreign Keys**:
  - `interaction_id` -> `interactions.id`
  - `uploaded_by` -> `users.id`
- **Unique Constraints**: None
- **Indexes**:
  - `ix_attachments_interaction_id` on `['interaction_id']`
  - `ix_attachments_visit_id` on `['visit_id']`

---

#### 13. `InteractionEvent`
- **Class**: `InteractionEvent`
- **Table Name**: `interaction_events` (`backend/app/models.py:140`)
- **Table Arguments** (lines 141–144):
  - `UniqueConstraint("interaction_id", "sequence", name="uq_event_sequence")`
  - `Index("ix_event_temporal", "interaction_id", "effective_at", "received_at")`

| Column Name | Mapped Type | SQLAlchemy Type | Nullable | Primary Key | Default | Foreign Key | Indexes / Constraints |
|---|---|---|---|---|---|---|---|
| `id` | `Mapped[str]` | `String(64)` | `False` | `True` | `new_id` (callable) | None | Primary Key |
| `interaction_id` | `Mapped[str]` | `String(64)` | `False` | `False` | None | `interactions.id` | `index=True` (`ix_interaction_events_interaction_id`) |
| `type` | `Mapped[str]` | `String(64)` | `False` | `False` | None | None | None |
| `effective_at` | `Mapped[datetime]` | `DateTime(timezone=True)` | `False` | `False` | None | None | In `ix_event_temporal` |
| `received_at` | `Mapped[datetime]` | `DateTime(timezone=True)` | `False` | `False` | None | None | In `ix_event_temporal` |
| `sequence` | `Mapped[int]` | `Integer` | `False` | `False` | None | None | In `uq_event_sequence` |
| `actor_id` | `Mapped[str]` | `String(64)` | `False` | `False` | None | `users.id` | Foreign Key |
| `actor_name` | `Mapped[str]` | `String(200)` | `False` | `False` | None | None | None |
| `payload` | `Mapped[dict]` | `JSON` | `False` | `False` | None | None | None |

- **Foreign Keys**:
  - `interaction_id` -> `interactions.id`
  - `actor_id` -> `users.id`
- **Unique Constraints**: `uq_event_sequence` on `['interaction_id', 'sequence']`.
- **Indexes**:
  - `ix_interaction_events_interaction_id` on `['interaction_id']`
  - `ix_event_temporal` on `['interaction_id', 'effective_at', 'received_at']`

---

#### 14. `Comment`
- **Class**: `Comment`
- **Table Name**: `comments` (`backend/app/models.py:157`)
- **Table Arguments**: None

| Column Name | Mapped Type | SQLAlchemy Type | Nullable | Primary Key | Default | Foreign Key | Indexes / Constraints |
|---|---|---|---|---|---|---|---|
| `id` | `Mapped[str]` | `String(64)` | `False` | `True` | `new_id` (callable) | None | Primary Key |
| `interaction_id` | `Mapped[str]` | `String(64)` | `False` | `False` | None | `interactions.id` | `index=True` (`ix_comments_interaction_id`) |
| `author_id` | `Mapped[str]` | `String(64)` | `False` | `False` | None | `users.id` | Foreign Key |
| `author_name` | `Mapped[str]` | `String(200)` | `False` | `False` | None | None | None |
| `body` | `Mapped[str]` | `Text` | `False` | `False` | None | None | None |
| `visit_id` | `Mapped[str]` | `String(64)` | `False` | `False` | None | None | None |
| `created_at` | `Mapped[datetime]` | `DateTime(timezone=True)` | `False` | `False` | `utcnow` (callable) | None | None |

- **Foreign Keys**:
  - `interaction_id` -> `interactions.id`
  - `author_id` -> `users.id`
- **Unique Constraints**: None
- **Indexes**: `ix_comments_interaction_id` on `['interaction_id']`.

---

#### 15. `CommandResult`
- **Class**: `CommandResult`
- **Table Name**: `command_results` (`backend/app/models.py:168`)
- **Table Arguments** (line 169):
  - `UniqueConstraint("user_id", "operation", "key", name="uq_command_key")`

| Column Name | Mapped Type | SQLAlchemy Type | Nullable | Primary Key | Default | Foreign Key | Indexes / Constraints |
|---|---|---|---|---|---|---|---|
| `id` | `Mapped[str]` | `String(64)` | `False` | `True` | `new_id` (callable) | None | Primary Key |
| `user_id` | `Mapped[str]` | `String(64)` | `False` | `False` | None | `users.id` | Foreign Key, in `uq_command_key` |
| `operation` | `Mapped[str]` | `String(200)` | `False` | `False` | None | None | In `uq_command_key` |
| `key` | `Mapped[str]` | `String(200)` | `False` | `False` | None | None | In `uq_command_key` |
| `payload_hash` | `Mapped[str]` | `String(64)` | `False` | `False` | None | None | None |
| `response` | `Mapped[dict \| None]` | `JSON` | `True` | `False` | None | None | None |
| `resource_id` | `Mapped[str \| None]` | `String(64)` | `True` | `False` | None | None | None |
| `created_at` | `Mapped[datetime]` | `DateTime(timezone=True)` | `False` | `False` | `utcnow` (callable) | None | None |

- **Foreign Keys**: `user_id` -> `users.id`
- **Unique Constraints**: `uq_command_key` on `['user_id', 'operation', 'key']`.
- **Indexes**: Unique index generated for `uq_command_key`.

---

#### 16. `IntegrationInbox`
- **Class**: `IntegrationInbox`
- **Table Name**: `integration_inbox` (`backend/app/models.py:181`)
- **Table Arguments** (lines 182–186):
  - `UniqueConstraint("source", "entity_type", "external_id", "source_revision", name="uq_inbox_dedup")`
  - `Index("ix_inbox_source_status", "source", "status")`
  - `Index("ix_inbox_received_at", "received_at")`

| Column Name | Mapped Type | SQLAlchemy Type | Nullable | Primary Key | Default | Foreign Key | Indexes / Constraints |
|---|---|---|---|---|---|---|---|
| `id` | `Mapped[str]` | `String(64)` | `False` | `True` | `new_id` (callable) | None | Primary Key |
| `source` | `Mapped[str]` | `String(32)` | `False` | `False` | None | None | `index=True` (`ix_integration_inbox_source`), in `ix_inbox_source_status`, in UQ |
| `entity_type` | `Mapped[str]` | `String(64)` | `False` | `False` | None | None | `index=True` (`ix_integration_inbox_entity_type`), in UQ |
| `external_id` | `Mapped[str]` | `String(128)` | `False` | `False` | None | None | `index=True` (`ix_integration_inbox_external_id`), in UQ |
| `source_revision` | `Mapped[str]` | `String(64)` | `False` | `False` | None | None | In UQ |
| `payload` | `Mapped[dict]` | `JSON` | `False` | `False` | None | None | None |
| `status` | `Mapped[str]` | `String(32)` | `False` | `False` | `"pending"` (scalar) | None | `index=True` (`ix_integration_inbox_status`), in `ix_inbox_source_status` |
| `error_message` | `Mapped[str \| None]` | `Text` | `True` | `False` | None | None | None |
| `matched_organization_id` | `Mapped[str \| None]` | `String(64)` | `True` | `False` | None | `organizations.id` | `index=True` (`ix_integration_inbox_matched_organization_id`) |
| `matched_interaction_id` | `Mapped[str \| None]` | `String(64)` | `True` | `False` | None | `interactions.id` | `index=True` (`ix_integration_inbox_matched_interaction_id`) |
| `received_at` | `Mapped[datetime]` | `DateTime(timezone=True)` | `False` | `False` | `utcnow` (callable) | None | `index=True` (`ix_integration_inbox_received_at`), in `ix_inbox_received_at` |
| `processed_at` | `Mapped[datetime \| None]` | `DateTime(timezone=True)` | `True` | `False` | None | None | None |

- **Foreign Keys**:
  - `matched_organization_id` -> `organizations.id`
  - `matched_interaction_id` -> `interactions.id`
- **Unique Constraints**: `uq_inbox_dedup` on `['source', 'entity_type', 'external_id', 'source_revision']`.
- **Indexes**:
  - `ix_integration_inbox_source` on `['source']`
  - `ix_integration_inbox_entity_type` on `['entity_type']`
  - `ix_integration_inbox_external_id` on `['external_id']`
  - `ix_integration_inbox_status` on `['status']`
  - `ix_integration_inbox_matched_organization_id` on `['matched_organization_id']`
  - `ix_integration_inbox_matched_interaction_id` on `['matched_interaction_id']`
  - `ix_integration_inbox_received_at` on `['received_at']`
  - `ix_inbox_source_status` on `['source', 'status']`
  - `ix_inbox_received_at` on `['received_at']`

---

#### 17. `LearningMetric`
- **Class**: `LearningMetric`
- **Table Name**: `learning_metrics` (`backend/app/models.py:203`)
- **Table Arguments** (lines 204–208):
  - `UniqueConstraint("source", "external_id", name="uq_learning_metric_source_external")`
  - `Index("ix_metric_org_prog", "organization_id", "program_id")`
  - `Index("ix_metric_code_as_of", "metric_code", "as_of")`

| Column Name | Mapped Type | SQLAlchemy Type | Nullable | Primary Key | Default | Foreign Key | Indexes / Constraints |
|---|---|---|---|---|---|---|---|
| `id` | `Mapped[str]` | `String(64)` | `False` | `True` | `new_id` (callable) | None | Primary Key |
| `organization_id` | `Mapped[str]` | `String(64)` | `False` | `False` | None | `organizations.id` | `index=True` (`ix_learning_metrics_organization_id`), in `ix_metric_org_prog` |
| `program_id` | `Mapped[str]` | `String(64)` | `False` | `False` | None | `programs.id` | `index=True` (`ix_learning_metrics_program_id`), in `ix_metric_org_prog` |
| `metric_code` | `Mapped[str]` | `String(64)` | `False` | `False` | None | None | In `ix_metric_code_as_of` |
| `value` | `Mapped[float]` | `Float` | `False` | `False` | None | None | None |
| `unit` | `Mapped[str]` | `String(32)` | `False` | `False` | None | None | None |
| `as_of` | `Mapped[datetime]` | `DateTime(timezone=True)` | `False` | `False` | None | None | In `ix_metric_code_as_of` |
| `source` | `Mapped[str]` | `String(32)` | `False` | `False` | `"lms"` (scalar) | None | In `uq_learning_metric_source_external` |
| `external_id` | `Mapped[str]` | `String(128)` | `False` | `False` | None | None | In `uq_learning_metric_source_external` |
| `created_at` | `Mapped[datetime]` | `DateTime(timezone=True)` | `False` | `False` | `utcnow` (callable) | None | None |

- **Foreign Keys**:
  - `organization_id` -> `organizations.id`
  - `program_id` -> `programs.id`
- **Unique Constraints**: `uq_learning_metric_source_external` on `['source', 'external_id']`.
- **Indexes**:
  - `ix_learning_metrics_organization_id` on `['organization_id']`
  - `ix_learning_metrics_program_id` on `['program_id']`
  - `ix_metric_org_prog` on `['organization_id', 'program_id']`
  - `ix_metric_code_as_of` on `['metric_code', 'as_of']`

---

#### 18. `Delivery`
- **Class**: `Delivery`
- **Table Name**: `deliveries` (`backend/app/models.py:223`)
- **Table Arguments**: None

| Column Name | Mapped Type | SQLAlchemy Type | Nullable | Primary Key | Default | Foreign Key | Indexes / Constraints |
|---|---|---|---|---|---|---|---|
| `id` | `Mapped[str]` | `String(64)` | `False` | `True` | `new_id` (callable) | None | Primary Key |
| `organization_id` | `Mapped[str]` | `String(64)` | `False` | `False` | None | `organizations.id` | `index=True` (`ix_deliveries_organization_id`) |
| `interaction_id` | `Mapped[str \| None]` | `String(64)` | `True` | `False` | None | `interactions.id` | `index=True` (`ix_deliveries_interaction_id`) |
| `status` | `Mapped[str]` | `String(32)` | `False` | `False` | `"draft"` (scalar) | None | None |
| `channel` | `Mapped[str]` | `String(40)` | `False` | `False` | `"email"` (scalar) | None | None |
| `sent_at` | `Mapped[datetime \| None]` | `DateTime(timezone=True)` | `True` | `False` | None | None | None |
| `confirmed_at` | `Mapped[datetime \| None]` | `DateTime(timezone=True)` | `True` | `False` | None | None | None |
| `recipient_contact_id` | `Mapped[str \| None]` | `String(64)` | `True` | `False` | None | `organization_contacts.id` | Foreign Key |
| `recorded_by` | `Mapped[str]` | `String(64)` | `False` | `False` | None | `users.id` | `index=True` (`ix_deliveries_recorded_by`) |
| `comment` | `Mapped[str \| None]` | `Text` | `True` | `False` | None | None | None |
| `created_at` | `Mapped[datetime]` | `DateTime(timezone=True)` | `False` | `False` | `utcnow` (callable) | None | None |
| `revision` | `Mapped[int]` | `Integer` | `False` | `False` | `1` (scalar) | None | None |

- **Foreign Keys**:
  - `organization_id` -> `organizations.id`
  - `interaction_id` -> `interactions.id`
  - `recipient_contact_id` -> `organization_contacts.id`
  - `recorded_by` -> `users.id`
- **Unique Constraints**: None
- **Indexes**:
  - `ix_deliveries_organization_id` on `['organization_id']`
  - `ix_deliveries_interaction_id` on `['interaction_id']`
  - `ix_deliveries_recorded_by` on `['recorded_by']`

---

#### 19. `DeliveryItem`
- **Class**: `DeliveryItem`
- **Table Name**: `delivery_items` (`backend/app/models.py:240`)
- **Table Arguments**: None

| Column Name | Mapped Type | SQLAlchemy Type | Nullable | Primary Key | Default | Foreign Key | Indexes / Constraints |
|---|---|---|---|---|---|---|---|
| `id` | `Mapped[str]` | `String(64)` | `False` | `True` | `new_id` (callable) | None | Primary Key |
| `delivery_id` | `Mapped[str]` | `String(64)` | `False` | `False` | None | `deliveries.id` (ondelete="CASCADE") | `index=True` (`ix_delivery_items_delivery_id`) |
| `item_kind` | `Mapped[str]` | `String(32)` | `False` | `False` | None | None | None |
| `title` | `Mapped[str]` | `String(250)` | `False` | `False` | None | None | None |
| `attachment_id` | `Mapped[str \| None]` | `String(64)` | `True` | `False` | None | `attachments.id` | Foreign Key |
| `license_id` | `Mapped[str \| None]` | `String(64)` | `True` | `False` | None | `licenses.id` | Foreign Key |
| `material_version` | `Mapped[str \| None]` | `String(120)` | `True` | `False` | None | None | None |
| `created_at` | `Mapped[datetime]` | `DateTime(timezone=True)` | `False` | `False` | `utcnow` (callable) | None | None |

- **Foreign Keys**:
  - `delivery_id` -> `deliveries.id` with cascade deletion (`ondelete="CASCADE"`).
  - `attachment_id` -> `attachments.id`
  - `license_id` -> `licenses.id`
- **Unique Constraints**: None
- **Indexes**: `ix_delivery_items_delivery_id` on `['delivery_id']`.

---

## 2. HTTP API Specification and Pydantic Schemas (Section R2)

### 2.1 Application Initialization, Middleware, and Error Handlers

Source files: `backend/app/main.py`, `backend/app/errors.py`.

#### FastAPI Instance
Instantiated inside factory `create_app(settings: Settings | None = None) -> FastAPI` (`backend/app/main.py:111`):
- Metadata: `title="ИТ Школа · Партнёры API"`, `version="0.1.0"`.

#### HTTP Middleware (`backend/app/main.py:132-137`)
- Handler: `@app.middleware("http") async def request_context(request: Request, call_next)`
- Reads header `X-Request-ID` or generates `str(uuid4())` when absent.
- Assigns to `request.state.request_id`.
- Appends `X-Request-ID: <request_id>` to all HTTP responses.

#### Standard Exception Handlers (`backend/app/errors.py:75-150`)
Installed via `install_error_handlers(app)`:
1. `APIError` (`backend/app/errors.py:76-108`):
   - Returns JSON envelope: `{"error": {"code": str, "message": str, "request_id": str, "details": Any, "field_errors": list}}`.
   - Status: `exc.status_code` (default 422).
   - Injects `X-Request-ID` header.
2. `RequestValidationError` (`backend/app/errors.py:110-131`):
   - Translates Pydantic errors into uniform list `[{"field": str, "message": str}]`.
   - Returns HTTP 422 with `code="VALIDATION_ERROR"`.
3. `Exception` (`backend/app/errors.py:133-149`):
   - Catches unhandled server exceptions, logs stack trace via `logger.exception`.
   - Returns HTTP 500 with `code="INTERNAL_ERROR"` and `request_id`.

---

### 2.2 Authentication, Authorization, and Scope Isolation

Source files: `backend/app/auth.py`, `backend/app/services.py`.

#### Authentication Dependency (`backend/app/auth.py:20-46`)
- `current_user(db: Session = Depends(get_db), authorization: str | None = Header(None), x_demo_user: str | None = Header(None), config=Depends(runtime_settings)) -> User`:
  - When `config.auth_mode == "demo"`: requires header `X-Demo-User`; looks up `User` by primary key `x_demo_user`. Absence raises HTTP 401 `UNAUTHENTICATED`.
  - When `config.auth_mode == "oidc"`: requires header `Authorization: Bearer <token>`; validates RS256 token against `config.oidc_jwks_url` via `jwt.PyJWKClient` (cache lifespan 300s); validates claims `exp`, `iss`, `aud`, `sub`; matches `User.keycloak_subject == claims["sub"]`; verifies role presence in token claims (HTTP 403 `FORBIDDEN` if missing).
  - Validates `user.active is True`; raises HTTP 401 `UNAUTHENTICATED` if inactive.

#### Role-Based Permissions Matrix (`backend/app/services.py:27-37`)
- `manager`: `interactions.create`, `interactions.transition`, `interactions.comment`, `interactions.edit`, `reports.read`
- `supervisor`: `interactions.create`, `interactions.transition`, `interactions.comment`, `interactions.assign`, `interactions.edit`, `reports.read`, `organizations.create`, `integrations.manage`
- `administrator`: `workflow.manage`, `users.manage`, `organizations.create`, `reports.read`, `integrations.manage`

#### Scope Filtering and 152-FZ Isolation (`backend/app/services.py:45-58`)
- `scope_clause(user)`:
  - Role `manager`: `Interaction.owner_id == user.id` OR `Interaction.organization_id.in_(select(OrganizationAccess.organization_id).where(OrganizationAccess.user_id == user.id, OrganizationAccess.read_all == True))`.
  - Role `supervisor`: `Interaction.team_id == user.team_id` OR `Interaction.organization_id.in_(select(OrganizationAccess.organization_id).where(OrganizationAccess.user_id == user.id, OrganizationAccess.read_all == True))`.
  - Role `administrator`: `Interaction.organization_id.in_(select(OrganizationAccess.organization_id).where(OrganizationAccess.user_id == user.id, OrganizationAccess.read_all == True))`.
- `scoped_interaction(db, user, interaction_id)`:
  - Queries `Interaction` with `Interaction.id == interaction_id` filtered by `scope_clause(user)`.
  - If no record matches, raises HTTP 404 with `code="NOT_FOUND"` (does not disclose record existence).

---

### 2.3 Pydantic Schemas Inventory (`backend/app/schemas.py`)

All 13 schema classes declared in `backend/app/schemas.py`:

| Schema Name | Base Class | Fields and Types | Constraints / Validators |
|---|---|---|---|
| `Body` | `pydantic.BaseModel` | None | `model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)` |
| `InteractionCreate` | `Body` | `title: str`<br>`organization_id: str`<br>`program_id: str | None = None`<br>`product_id: str | None = None`<br>`cycle_label: str`<br>`owner_id: str`<br>`contact_id: str | None = None`<br>`contract_id: str | None = None`<br>`license_id: str | None = None` | `title`: min 1, max 250<br>`organization_id`: min 1, max 64<br>`cycle_label`: min 1, max 100<br>`owner_id`: min 1, max 64 |
| `InteractionUpdate` | `Body` | `expected_revision: int`<br>`title: str | None = None`<br>`program_id: str | None = None`<br>`product_id: str | None = None`<br>`cycle_label: str | None = None`<br>`contact_id: str | None = None`<br>`contract_id: str | None = None`<br>`license_id: str | None = None` | `expected_revision`: ge 1<br>`title`: min 1, max 250 (if set)<br>`cycle_label`: min 1, max 100 (if set) |
| `TransitionCommand` | `Body` | `transition_code: str`<br>`expected_revision: int`<br>`comment: str | None = None` | `transition_code`: min 1, max 180<br>`expected_revision`: ge 1<br>`comment`: max 5000 |
| `CommentCommand` | `Body` | `body: str`<br>`expected_revision: int` | `body`: min 1, max 5000<br>`expected_revision`: ge 1 |
| `AssignmentCommand` | `Body` | `owner_id: str`<br>`expected_revision: int`<br>`reason: str` | `owner_id`: min 1, max 64<br>`expected_revision`: ge 1<br>`reason`: min 1, max 5000 |
| `OrganizationCreate` | `Body` | `name: str`<br>`type: Literal["university", "school", "other"] = "university"` | `name`: min 1, max 250 |
| `SnapshotRequest` | `Body` | `as_of: datetime`<br>`knowledge_cutoff: datetime | None = None`<br>`as_of_inclusive: bool = True`<br>`historical_owner_id: str | None = None`<br>`organization_ids: list[str] = []`<br>`program_ids: list[str] = []`<br>`product_ids: list[str] = []`<br>`owner_ids: list[str] = []` | Field validator `timezone_required` on `as_of`, `knowledge_cutoff` requiring `tzinfo`<br>list fields: max_length 500 |
| `ActivityRequest` | `Body` | `from_date: datetime` (alias `from`)<br>`to_date: datetime` (alias `to`)<br>`knowledge_cutoff: datetime | None = None`<br>`historical_owner_id: str | None = None`<br>`organization_ids: list[str] = []`<br>`program_ids: list[str] = []`<br>`product_ids: list[str] = []`<br>`owner_ids: list[str] = []` | Field validator `timezone_required`<br>`populate_by_name=True`<br>list fields: max_length 500 |
| `CreatedReportRequest` | `Body` | `from_date: datetime` (alias `from`)<br>`to_date: datetime` (alias `to`)<br>`knowledge_cutoff: datetime | None = None`<br>`organization_ids: list[str] = []`<br>`owner_ids: list[str] = []`<br>`program_ids: list[str] = []`<br>`product_ids: list[str] = []` | Field validator `timezone_required`<br>`populate_by_name=True`<br>list fields: max_length 500 |
| `AttachmentRead` | `pydantic.BaseModel` | `id: str`<br>`interaction_id: str`<br>`visit_id: str`<br>`file_name: str`<br>`file_size: int`<br>`content_type: str`<br>`checksum: str`<br>`uploaded_by: str`<br>`created_at: str` | Direct DTO representation |
| `ImportCommitRequest` | `Body` | `import_id: str | None = None`<br>`rows: list[dict] = []` | Inherits `extra="forbid"`, `str_strip_whitespace=True` |
| `WorkflowMigrateRequest` | `Body` | `from_version: int`<br>`to_version: int`<br>`status_mapping: dict[str, str]` | `from_version`: ge 1<br>`to_version`: ge 1<br>`status_mapping`: min_length 1 |

---

### 2.4 Complete HTTP API Endpoints Catalog (`backend/app/main.py`)

A total of 32 route operations across 29 unique route paths:

| # | HTTP Method | Exact Route Path | Input Parameters (Path, Query, Headers, Body) | Applied Dependencies & Role Checks | Status Code | Response Type / Schema |
|---|---|---|---|---|---|---|
| 1 | `GET` | `/health/live` | None | None | 200 | `{"status": "ok"}` |
| 2 | `GET` | `/health/ready` | None | `Depends(get_db)` | 200 | `{"status": "ok", "database": "ok"}` (or 503 `NOT_READY`) |
| 3 | `GET` | `/api/v1/config` | None | `Depends(get_db)` | 200 | `{"auth_mode": str, "oidc": dict \| None, "demo_users": list[dict]}` |
| 4 | `GET` | `/api/v1/me` | Headers: `Authorization` or `X-Demo-User` | `user = Depends(current_user)` | 200 | `{"id": str, "name": str, "role": str, "team_id": str \| None, "permissions": list[str], "auth_mode": str}` |
| 5 | `GET` | `/api/v1/catalogs` | Headers: Auth | `Depends(get_db)`, `user = Depends(current_user)` | 200 | `{"organizations": list, "programs": list, "products": list, "owners": list, "directions": list, "contacts": list, "contracts": list, "licenses": list}` |
| 6 | `GET` | `/api/v1/workflow` | Query: `version: int = 1` (ge 1)<br>Headers: Auth | `user = Depends(current_user)` | 200 | `{"schema_version": str, "template_code": str, "version": int, "name": str, "initial_state": str, "states": dict, "transitions": dict}` (404 if version absent) |
| 7 | `POST` | `/api/v1/workflow/migrate/preview` | Body: `WorkflowMigrateRequest`<br>Headers: Auth | `Depends(get_db)`, `user = Depends(current_user)`<br>Role check: `user.role in ("supervisor", "administrator")` | 200 | `{"from_version": int, "to_version": int, "affected_interactions_count": int, "status_distribution_before": dict, "status_distribution_after": dict, "unmapped_statuses": list, "collisions": list, "warnings": list, "is_valid": bool}` |
| 8 | `POST` | `/api/v1/workflow/migrate/commit` | Header: `Idempotency-Key: str` (up to 200 chars)<br>Body: `WorkflowMigrateRequest`<br>Headers: Auth | `Depends(get_db)`, `user = Depends(current_user)`<br>Role check: `user.role in ("supervisor", "administrator")` | 200 | `{"status": "migrated", "from_version": int, "to_version": int, "migrated_count": int, "status_distribution": dict, "details": list[dict]}` |
| 9 | `GET` | `/api/v1/interactions` | Query: `q: str \| None`, `organization_id: str \| None`, `program_id: str \| None`, `product_id: str \| None`, `owner_id: str \| None`, `state: str \| None`, `page: int = 1` (ge 1), `page_size: int = 50` (1..100)<br>Headers: Auth | `Depends(get_db)`, `user = Depends(current_user)`<br>Data isolation: `scope_clause(user)` | 200 | `{"items": list[InteractionDict], "total": int, "page": int, "page_size": int}` |
| 10 | `GET` | `/api/v1/interactions/{interaction_id}` | Path: `interaction_id: str`<br>Headers: Auth | `Depends(get_db)`, `user = Depends(current_user)`<br>Scope check: `scoped_interaction` (404 if out of scope) | 200 | `InteractionDetailDict` (includes `allowed_transitions`, `events`, `comments`, `attachments`) |
| 11 | `PATCH` | `/api/v1/interactions/{interaction_id}` | Path: `interaction_id: str`<br>Header: `Idempotency-Key: str \| None`<br>Body: `InteractionUpdate`<br>Headers: Auth | `Depends(get_db)`, `user = Depends(current_user)`<br>Scope check: `scoped_interaction` (404)<br>Permission: `interactions.edit` (403)<br>CAS: `expected_revision` (409) | 200 | `InteractionDict` |
| 12 | `POST` | `/api/v1/interactions` | Header: `Idempotency-Key: str` (mandatory, 1..200 chars)<br>Body: `InteractionCreate`<br>Headers: Auth | `Depends(get_db)`, `user = Depends(current_user)`<br>Permission: `interactions.create` (403)<br>Access: `OrganizationAccess.can_create` (404)<br>Owner check: manager own-only (403), supervisor team-only (403) | 201 | `InteractionDict` |
| 13 | `POST` | `/api/v1/interactions/{interaction_id}/transitions` | Path: `interaction_id: str`<br>Header: `Idempotency-Key: str \| None`<br>Body: `TransitionCommand`<br>Headers: Auth | `Depends(get_db)`, `user = Depends(current_user)`<br>Scope check: `scoped_interaction` (404)<br>Permission: `interactions.transition` (403)<br>CAS: `expected_revision` (409) | 200 | `InteractionDict` |
| 14 | `POST` | `/api/v1/interactions/{interaction_id}/comments` | Path: `interaction_id: str`<br>Header: `Idempotency-Key: str \| None`<br>Body: `CommentCommand`<br>Headers: Auth | `Depends(get_db)`, `user = Depends(current_user)`<br>Scope check: `scoped_interaction` (404)<br>Permission: `interactions.comment` (403)<br>CAS: `expected_revision` (409) | 201 | `{"id": str, "body": str, "author_id": str, "author_name": str, "author": dict, "created_at": str, "visit_id": str, "interaction_revision": int, "revision": int}` |
| 15 | `POST` | `/api/v1/interactions/{interaction_id}/assignments` | Path: `interaction_id: str`<br>Header: `Idempotency-Key: str \| None`<br>Body: `AssignmentCommand`<br>Headers: Auth | `Depends(get_db)`, `user = Depends(current_user)`<br>Scope check: `scoped_interaction` (404)<br>Permission: `interactions.assign` (403)<br>Supervisor team check (403)<br>CAS: `expected_revision` (409) | 200 | `InteractionDict` |
| 16 | `GET` | `/api/v1/dashboard` | Headers: Auth | `Depends(get_db)`, `user = Depends(current_user)`<br>Data isolation: `scope_clause(user)` | 200 | `{"total_interactions": int, "total_organizations": int, "active_interactions": int, "completed_interactions": int, "counts_by_state": list[dict], "recent_events": list[dict], "unassigned_program_count": int}` |
| 17 | `POST` | `/api/v1/interactions/{interaction_id}/attachments` | Path: `interaction_id: str`<br>Body: `multipart/form-data` or raw binary (max 25 MB)<br>Headers: `Content-Type`, optional `Content-Disposition`, `X-File-Name`<br>Headers: Auth | `Depends(get_db)`, `user = Depends(current_user)`<br>Scope check: `scoped_interaction` (404)<br>Size check: >25MB (413)<br>Type check: magic bytes (422) | 201 | `{"id": str, "interaction_id": str, "visit_id": str, "file_name": str, "file_size": int, "content_type": str, "checksum": str, "uploaded_by": str, "created_at": str}` |
| 18 | `GET` | `/api/v1/interactions/{interaction_id}/attachments` | Path: `interaction_id: str`<br>Headers: Auth | `Depends(get_db)`, `user = Depends(current_user)`<br>Scope check: `scoped_interaction` (404) | 200 | `list[AttachmentDict]` |
| 19 | `GET` | `/api/v1/interactions/{interaction_id}/attachments/{attachment_id}/download` | Path: `interaction_id: str`, `attachment_id: str`<br>Headers: Auth | `Depends(get_db)`, `user = Depends(current_user)`<br>Scope check: `scoped_interaction` (404)<br>File existence: 404 if missing | 200 | Streaming `FileResponse` with `Content-Disposition: attachment; filename="..."` |
| 20 | `POST` | `/api/v1/reports/snapshot` | Body: `SnapshotRequest`<br>Headers: Auth | `Depends(get_db)`, `user = Depends(current_user)`<br>Permission: `reports.read` (403)<br>Scope filter: `scope_clause(user)` | 200 | `{"report_type": "snapshot", "as_of": str, "knowledge_cutoff": str, "as_of_inclusive": bool, "generated_at": str, "total_interactions": int, "interaction_ids": list, "counts_by_state": dict, "counts_by_historical_owner": dict, "rows": list[dict], "totals": dict}` |
| 21 | `POST` | `/api/v1/reports/snapshot/export` | Query: `format: str = "json"` ("json", "xlsx", "pdf")<br>Body: `SnapshotRequest`<br>Headers: Auth | `Depends(get_db)`, `user = Depends(current_user)`<br>Permission: `reports.read` (403) | 200 | JSON object OR binary `Response` (xlsx: `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`, pdf: `application/pdf`) |
| 22 | `POST` | `/api/v1/reports/activity` | Body: `ActivityRequest`<br>Headers: Auth | `Depends(get_db)`, `user = Depends(current_user)`<br>Permission: `reports.read` (403)<br>Scope filter: `scope_clause(user)` | 200 | `{"report_type": "activity", "from_date": str, "to_date": str, "knowledge_cutoff": str, "generated_at": str, "event_ids": list, "interaction_ids": list, "total_transitions": int, "total_interactions": int, "counts_by_interaction": dict, "counts_by_to_state": dict, "counts_by_historical_owner": dict, "rows": list[dict], "totals": dict}` |
| 23 | `POST` | `/api/v1/reports/activity/export` | Query: `format: str = "json"` ("json", "xlsx", "pdf")<br>Body: `ActivityRequest`<br>Headers: Auth | `Depends(get_db)`, `user = Depends(current_user)`<br>Permission: `reports.read` (403) | 200 | JSON object OR binary `Response` (xlsx / pdf) |
| 24 | `POST` | `/api/v1/reports/created` | Body: `CreatedReportRequest`<br>Headers: Auth | `Depends(get_db)`, `user = Depends(current_user)`<br>Permission: `reports.read` (403)<br>Scope filter: `scope_clause(user)` | 200 | `{"report_type": "created", "from_date": str, "to_date": str, "knowledge_cutoff": str, "generated_at": str, "total_created": int, "interaction_ids": list, "counts_by_organization": dict, "counts_by_owner": dict, "counts_by_state": dict, "rows": list[dict], "totals": dict}` |
| 25 | `POST` | `/api/v1/reports/created/export` | Query: `format: str = "json"` ("json", "xlsx", "pdf")<br>Body: `CreatedReportRequest`<br>Headers: Auth | `Depends(get_db)`, `user = Depends(current_user)`<br>Permission: `reports.read` (403) | 200 | JSON object OR binary `Response` (xlsx / pdf) |
| 26 | `POST` | `/api/v1/imports/organizations/preview` | Body: `multipart/form-data` or raw tabular file (`.xlsx`, `.xls`, `.csv`)<br>Headers: Auth | `Depends(get_db)`, `user = Depends(current_user)`<br>Permission: `organizations.create` (403) | 200 | `{"import_id": str, "rows_total": int, "valid_count": int, "error_count": int, "preview_rows": list[dict], "errors": list[dict]}` |
| 27 | `POST` | `/api/v1/imports/organizations/commit` | Header: `Idempotency-Key: str \| None`<br>Body: `multipart/form-data` file OR JSON `{"rows": list[dict]}`<br>Headers: Auth | `Depends(get_db)`, `user = Depends(current_user)`<br>Permission: `organizations.create` (403) | 200 | `{"status": "committed", "success": true, "rows_total": int, "imported_count": int, "created_organizations": int, "updated_organizations": int, "created_contacts": int, "created_contracts": int, "errors": list}` |
| 28 | `GET` | `/api/v1/integrations/status` | Headers: Auth | `Depends(get_db)`, `user = Depends(current_user)`, `config = Depends(get_settings)`<br>Permission: `integrations.manage` (403) | 200 | `{"adapters": list[dict], "adapters_by_source": dict, "total_inbox": int, "total_pending": int, "total_processed": int, "total_quarantined": int, "total_rejected": int, "total_metrics": int, "last_synced_at": str \| None}` |
| 29 | `POST` | `/api/v1/integrations/sync/{source}` | Path: `source: str` ("lms", "website")<br>Header: `Idempotency-Key: str \| None`<br>Headers: Auth | `Depends(get_db)`, `user = Depends(current_user)`, `config = Depends(get_settings)`<br>Permission: `integrations.manage` (403) | 200 | `{"source": str, "received_count": int, "processed_count": int, "pending_count": int, "skipped_count": int, "quarantined_count": int, "message": str}` |
| 30 | `GET` | `/api/v1/integrations/inbox` | Query: `source: str \| None`, `status: str \| None`, `page: int = 1` (ge 1), `page_size: int = 20` (1..100)<br>Headers: Auth | `Depends(get_db)`, `user = Depends(current_user)`<br>Permission: `integrations.manage` (403) | 200 | `{"items": list[InboxItemDict], "total": int, "page": int, "page_size": int}` |
| 31 | `POST` | `/api/v1/integrations/inbox/{id}/resolve` | Path: `id: str`<br>Header: `Idempotency-Key: str` (mandatory, 1..200 chars)<br>Body: JSON `{"action": "link_existing" \| "create_new" \| "reject", "params": dict}`<br>Headers: Auth | `Depends(get_db)`, `user = Depends(current_user)`<br>Permission: `integrations.manage` (403) | 200 | `{"id": str, "status": str, "action": str, "error_message": str \| None, "matched_organization_id": str \| None, "organization_id": str \| None, "organization_name": str \| None, "contact_id": str \| None, "matched_interaction_id": str \| None, "interaction_id": str \| None, "processed_at": str}` |
| 32 | `GET` | `/api/v1/integrations/metrics` | Query: `organization_id: str \| None`, `program_id: str \| None`<br>Headers: Auth | `Depends(get_db)`, `user = Depends(current_user)`<br>Permission: `reports.read` (403)<br>Manager scoping: `visible_organization_ids` | 200 | `{"total_cohorts": int, "total_enrolled": int, "total_completed": int, "avg_attendance_rate": float, "by_program": list[dict], "by_organization": list[dict], "metrics": list[dict]}` |

---

## 3. Service Modules and Factual Functions Inventory (Section R3)

### 3.1 Overview of Service Modules

Across the 8 service packages and modules under `backend/app/` at commit `1c7c0eb`:
- Total public callables and classes: 66.
- Functions performing database operations: 30.
- Functions supporting `Idempotency-Key`: 9.
- Functions supporting `expected_revision` (CAS): 6.

| Module | Public Callables / Classes Count | DB Access Functions | Idempotency-Key Support | expected_revision Support |
|---|---|---|---|---|
| `backend/app/auth.py` | 2 | 1 (`current_user`) | 0 | 0 |
| `backend/app/errors.py` | 2 (`APIError`, `install_error_handlers`) | 0 | 0 | 0 |
| `backend/app/files.py` | 6 | 3 (`save_attachment`, `get_attachment_or_404`, `list_interaction_attachments`) | 0 | 0 |
| `backend/app/workflow.py` | 4 | 0 | 0 | 0 |
| `backend/app/importer.py` | 5 | 2 (`preview_organizations_import`, `commit_organizations_import`) | 1 (`commit_organizations_import`) | 0 |
| `backend/app/reports_export.py` | 5 | 0 | 0 | 0 |
| `backend/app/integrations/base.py` | 3 (`NormalizedEnvelope`, `to_dict`, `BaseIntegrationAdapter`) | 0 | 0 | 0 |
| `backend/app/integrations/factory.py` | 1 (`get_adapter`) | 0 | 0 | 0 |
| `backend/app/integrations/mock_lms.py` | 1 class (`MockLMSAdapter`: 3 methods) | 0 | 0 | 0 |
| `backend/app/integrations/mock_website.py` | 1 class (`MockWebsiteAdapter`: 3 methods) | 0 | 0 | 0 |
| `backend/app/integrations/service.py` | 5 | 5 | 2 (`sync_source`, `reconcile_application`) | 0 |
| `backend/app/services.py` | 32 | 19 | 6 | 6 |
| **Total** | **66** | **30** | **9** | **6** |

---

### 3.2 `backend/app/auth.py`

#### 1. `jwks_client(url)` (lines 15–17)
- Arguments: `url: str`
- Return: `jwt.PyJWKClient`
- DB tables: None | DB operations: None | Idempotency-Key: No | CAS: No
- Description: Cached constructor returning `PyJWKClient` with `cache_jwk_set=True`, `lifespan=300`, `timeout=5`.

#### 2. `current_user(db: Session = Depends(get_db), authorization: str | None = Header(None), x_demo_user: str | None = Header(None), config=Depends(runtime_settings)) -> User` (lines 20–46)
- Arguments: `db: Session`, `authorization: str | None`, `x_demo_user: str | None`, `config`
- Return: `User`
- DB tables: `users` | DB operations: SELECT
- Idempotency-Key: No | CAS: No
- Description: Resolves authenticated user in `demo` or `oidc` modes. Verifies `user.active is True`.

---

### 3.3 `backend/app/errors.py`

#### 3. `APIError(self, code: str, message: str, status: int = 422, details=None, field_errors: list | None = None, headers: dict[str, str] | None = None, status_code: int | None = None)` (lines 14–46)
- Constructor for custom domain exception holding code, message, HTTP status, details, field errors, and headers.
- DB tables: None | DB operations: None | Idempotency-Key: No | CAS: No

#### 4. `install_error_handlers(app)` (lines 75–150)
- Arguments: `app` (FastAPI instance)
- Return: None
- DB tables: None | DB operations: None | Idempotency-Key: No | CAS: No
- Description: Registers exception handlers for `APIError`, `RequestValidationError`, and generic `Exception` formatting standard JSON error responses.

---

### 3.4 `backend/app/files.py`

#### 5. `sanitize_filename(filename: str) -> tuple[str, str]` (lines 47–63)
- Arguments: `filename: str`
- Return: `tuple[str, str]` (basename, extension)
- DB tables: None | DB operations: None | Idempotency-Key: No | CAS: No
- Description: Removes path separators, checks against allowed extensions (`png, jpeg, jpg, pdf, zip, gzip, gz, rar, doc, docx, xls, xlsx`).

#### 6. `validate_magic_bytes(ext: str, data: bytes) -> bool` (lines 65–89)
- Arguments: `ext: str`, `data: bytes`
- Return: `bool`
- DB tables: None | DB operations: None | Idempotency-Key: No | CAS: No
- Description: Validates binary file signatures against declared extension and rejects dangerous executable headers (`MZ`, `\x7fELF`, `#!`, `<?php`, `<script`).

#### 7. `save_attachment(db: Session, user: User, interaction_id: str, raw_filename: str, file_bytes: bytes, storage_dir: str = "storage", content_type_header: str | None = None) -> Attachment` (lines 91–150)
- Arguments: `db: Session`, `user: User`, `interaction_id: str`, `raw_filename: str`, `file_bytes: bytes`, `storage_dir: str = "storage"`, `content_type_header: str | None = None`
- Return: `Attachment`
- DB tables: `interactions`, `organization_access`, `attachments`, `interaction_events`, `organizations`, `users`, `programs`, `products`, `directions`, `organization_contacts`, `contracts`, `licenses`
- DB operations: SELECT, INSERT (`attachments`, `interaction_events`)
- Idempotency-Key: No | CAS: No
- Description: Validates interaction access via `scoped_interaction`, size (<= 25 MB), filename and magic bytes. Persists file to disk, creates `Attachment` record and logs `attachment_uploaded` audit event.

#### 8. `get_attachment_or_404(db: Session, user: User, interaction_id: str, attachment_id: str) -> Attachment` (lines 153–164)
- Arguments: `db: Session`, `user: User`, `interaction_id: str`, `attachment_id: str`
- Return: `Attachment`
- DB tables: `interactions`, `organization_access`, `attachments`
- DB operations: SELECT
- Idempotency-Key: No | CAS: No
- Description: Validates interaction access via `scoped_interaction` and fetches `Attachment` record (raises 404 if missing).

#### 9. `list_interaction_attachments(db: Session, user: User, interaction_id: str) -> list[Attachment]` (lines 167–176)
- Arguments: `db: Session`, `user: User`, `interaction_id: str`
- Return: `list[Attachment]`
- DB tables: `interactions`, `organization_access`, `attachments`
- DB operations: SELECT
- Idempotency-Key: No | CAS: No
- Description: Returns ordered attachments for a scoped interaction.

#### 10. `attachment_dict(att: Attachment) -> dict` (lines 179–190)
- Arguments: `att: Attachment`
- Return: `dict`
- DB tables: None | DB operations: None | Idempotency-Key: No | CAS: No
- Description: Formats `Attachment` model into dictionary representation.

---

### 3.5 `backend/app/workflow.py`

#### 11. `get_workflow(version: int = 1) -> dict` (lines 80–83)
- Arguments: `version: int = 1`
- Return: `dict` (workflow metadata, states, transitions)
- DB tables: None | DB operations: None | Idempotency-Key: No | CAS: No

#### 12. `get_states(version: int = 1) -> dict[str, dict]` (lines 86–88)
- Arguments: `version: int = 1`
- Return: `dict[str, dict]` (mapping of state codes to metadata)
- DB tables: None | DB operations: None | Idempotency-Key: No | CAS: No

#### 13. `get_transitions(version: int = 1) -> dict[str, dict]` (lines 91–93)
- Arguments: `version: int = 1`
- Return: `dict[str, dict]` (mapping of transition codes to transition definitions)
- DB tables: None | DB operations: None | Idempotency-Key: No | CAS: No

#### 14. `allowed_transitions(state: str, version: int = 1) -> list[dict]` (lines 96–109)
- Arguments: `state: str`, `version: int = 1`
- Return: `list[dict]` (list of allowed outgoing transitions)
- DB tables: None | DB operations: None | Idempotency-Key: No | CAS: No

---

### 3.6 `backend/app/importer.py`

#### 15. `parse_xlsx_stdlib(data: bytes) -> list[list[str]]` (lines 108–149)
- Arguments: `data: bytes`
- Return: `list[list[str]]`
- DB tables: None | DB operations: None | Idempotency-Key: No | CAS: No
- Description: Extracts spreadsheet rows from Open XML zip archive using `zipfile` and `xml.etree.ElementTree`.

#### 16. `parse_csv_stdlib(data: bytes) -> list[list[str]]` (lines 152–167)
- Arguments: `data: bytes`
- Return: `list[list[str]]`
- DB tables: None | DB operations: None | Idempotency-Key: No | CAS: No
- Description: Auto-detects encoding and delimiter and parses CSV records.

#### 17. `parse_tabular_file(data: bytes, filename: str) -> list[dict[str, str]]` (lines 170–205)
- Arguments: `data: bytes`, `filename: str`
- Return: `list[dict[str, str]]`
- DB tables: None | DB operations: None | Idempotency-Key: No | CAS: No
- Description: Routes to XLSX or CSV parser and normalizes row headers using synonym mappings.

#### 18. `preview_organizations_import(db: Session, user: User, file_bytes: bytes, filename: str) -> dict` (lines 208–320)
- Arguments: `db: Session`, `user: User`, `file_bytes: bytes`, `filename: str`
- Return: `dict` (`import_id`, `rows_total`, `valid_count`, `error_count`, `preview_rows`, `errors`)
- DB tables: `organizations`, `programs`, `products`, `program_products`
- DB operations: SELECT (dry-run)
- Idempotency-Key: No | CAS: No

#### 19. `commit_organizations_import(db: Session, user: User, rows: list[dict], idempotency_key: str | None = None) -> dict` (lines 323–415)
- Arguments: `db: Session`, `user: User`, `rows: list[dict]`, `idempotency_key: str | None = None`
- Return: `dict` (`status`, `success`, `rows_total`, `imported_count`, `created_organizations`, `updated_organizations`, `created_contacts`, `created_contracts`, `errors`)
- DB tables: `command_results`, `organizations`, `organization_access`, `organization_contacts`, `contracts`
- DB operations: SELECT, INSERT (`organizations`, `organization_access`, `organization_contacts`, `contracts`, `command_results`), UPDATE (`command_results`)
- Idempotency-Key: Yes (`operation="import_organizations"`) | CAS: No

---

### 3.7 `backend/app/reports_export.py`

#### 20. `sanitize_formula_cell(value: Any) -> str` (lines 17–29)
- Arguments: `value: Any`
- Return: `str`
- DB tables: None | DB operations: None | Idempotency-Key: No | CAS: No
- Description: Sanitizes spreadsheet cells against formula injection by prefixing with `'` if string starts with `=`, `+`, `-`, `@`, `\t`, `\r`.

#### 21. `generate_xlsx_report(report_data: dict, report_type: str, user: User) -> bytes` (lines 88–232)
- Arguments: `report_data: dict`, `report_type: str`, `user: User`
- Return: `bytes` (ZIP archive containing OpenXML spreadsheet)
- DB tables: None | DB operations: None | Idempotency-Key: No | CAS: No

#### 22. `generate_pdf_report(report_data: dict, report_type: str, user: User) -> bytes` (lines 234–485)
- Arguments: `report_data: dict`, `report_type: str`, `user: User`
- Return: `bytes` (Vector PDF 1.4 binary data)
- DB tables: None | DB operations: None | Idempotency-Key: No | CAS: No

#### 23. `generate_csv_report(report_data: dict, report_type: str, user: User) -> bytes` (lines 487–502)
- Arguments: `report_data: dict`, `report_type: str`, `user: User`
- Return: `bytes` (UTF-8-SIG encoded CSV data)
- DB tables: None | DB operations: None | Idempotency-Key: No | CAS: No

#### 24. `export_report(report_data: dict, report_type: str, export_format: str, user: User) -> Response` (lines 505–539)
- Arguments: `report_data: dict`, `report_type: str`, `export_format: str`, `user: User`
- Return: `Response` (FastAPI `JSONResponse` or binary `Response` with headers `Content-Disposition`, `X-Report-Format`)
- DB tables: None | DB operations: None | Idempotency-Key: No | CAS: No

---

### 3.8 `backend/app/integrations/*`

#### 25. `NormalizedEnvelope` (`backend/app/integrations/base.py:9-40`)
- Dataclass fields: `schema_version`, `source`, `entity_type`, `external_id`, `source_revision`, `operation`, `effective_at`, `received_at`, `payload`.
- Method: `to_dict(self) -> dict[str, Any]`
- DB tables: None | DB operations: None | Idempotency-Key: No | CAS: No

#### 26. `BaseIntegrationAdapter` (`backend/app/integrations/base.py:43-52`)
- Abstract base class with abstract methods:
  - `fetch_updates(self, since: datetime | None = None) -> list[NormalizedEnvelope]`
  - `health_check(self) -> dict[str, Any]`
- DB tables: None | DB operations: None | Idempotency-Key: No | CAS: No

#### 27. `get_adapter(source: str, settings: Settings | None = None) -> BaseIntegrationAdapter` (`backend/app/integrations/factory.py:9-24`)
- Arguments: `source: str`, `settings: Settings | None = None`
- Return: `BaseIntegrationAdapter` (instantiates `MockLMSAdapter` or `MockWebsiteAdapter`)
- DB tables: None | DB operations: None | Idempotency-Key: No | CAS: No

#### 28. `MockLMSAdapter` (`backend/app/integrations/mock_lms.py:9-160`)
- Class implementing `BaseIntegrationAdapter`.
- Methods: `__init__`, `health_check`, `fetch_updates`.
- DB tables: None | DB operations: None | Idempotency-Key: No | CAS: No

#### 29. `MockWebsiteAdapter` (`backend/app/integrations/mock_website.py:9-112`)
- Class implementing `BaseIntegrationAdapter`.
- Methods: `__init__`, `health_check`, `fetch_updates`.
- DB tables: None | DB operations: None | Idempotency-Key: No | CAS: No

#### 30. `get_integrations_status(db: Session, user: User, config: Settings | None = None) -> dict[str, Any]` (`backend/app/integrations/service.py:37-86`)
- Arguments: `db: Session`, `user: User`, `config: Settings | None = None`
- Return: `dict[str, Any]`
- DB tables: `integration_inbox`, `learning_metrics`
- DB operations: SELECT
- Idempotency-Key: No | CAS: No

#### 31. `sync_source(db: Session, user: User, source: str, config: Settings | None = None, idempotency_key: str | None = None) -> dict[str, Any]` (`backend/app/integrations/service.py:89-252`)
- Arguments: `db: Session`, `user: User`, `source: str`, `config: Settings | None = None`, `idempotency_key: str | None = None`
- Return: `dict[str, Any]`
- DB tables: `command_results`, `integration_inbox`, `organizations`, `programs`, `learning_metrics`
- DB operations: SELECT, INSERT (`integration_inbox`, `learning_metrics`, `command_results`), UPDATE (`learning_metrics`, `command_results`)
- Idempotency-Key: Yes (`operation=f"integrations.sync:{src}"`) | CAS: No

#### 32. `list_inbox_items(db: Session, user: User, source: str | None = None, status: str | None = None, page: int = 1, page_size: int = 20) -> dict[str, Any]` (`backend/app/integrations/service.py:255-317`)
- Arguments: `db: Session`, `user: User`, `source: str | None = None`, `status: str | None = None`, `page: int = 1`, `page_size: int = 20`
- Return: `dict[str, Any]` (`items`, `total`, `page`, `page_size`)
- DB tables: `integration_inbox`, `organizations`
- DB operations: SELECT
- Idempotency-Key: No | CAS: No

#### 33. `reconcile_application(db: Session, user: User, inbox_id: str, action: str, params: dict[str, Any] | None = None, idempotency_key: str | None = None) -> dict[str, Any]` (`backend/app/integrations/service.py:320-550`)
- Arguments: `db: Session`, `user: User`, `inbox_id: str`, `action: str`, `params: dict[str, Any] | None = None`, `idempotency_key: str | None = None`
- Return: `dict[str, Any]`
- DB tables: `command_results`, `integration_inbox`, `organizations`, `organization_access`, `organization_contacts`, `users`, `programs`, `products`, `program_products`, `interactions`, `interaction_events`
- DB operations: SELECT, INSERT (`organizations`, `organization_access`, `organization_contacts`, `interactions`, `interaction_events`, `command_results`), UPDATE (`integration_inbox`, `command_results`)
- Idempotency-Key: Yes (`operation=f"integrations.resolve:{inbox_id}"`) | CAS: No

#### 34. `get_learning_metrics_summary(db: Session, user: User, organization_id: str | None = None, program_id: str | None = None) -> dict[str, Any]` (`backend/app/integrations/service.py:553-692`)
- Arguments: `db: Session`, `user: User`, `organization_id: str | None = None`, `program_id: str | None = None`
- Return: `dict[str, Any]`
- DB tables: `organization_access`, `interactions`, `learning_metrics`, `organizations`, `programs`
- DB operations: SELECT
- Idempotency-Key: No | CAS: No

---

### 3.9 `backend/app/services.py`

#### 35. `aware(value)` (lines 19–20)
- Arguments: `value: datetime`
- Return: `datetime` with `timezone.utc`
- DB tables: None | DB operations: None | Idempotency-Key: No | CAS: No

#### 36. `iso(value)` (lines 23–24)
- Arguments: `value: datetime | None`
- Return: `str | None` (ISO 8601 string)
- DB tables: None | DB operations: None | Idempotency-Key: No | CAS: No

#### 37. `permissions(user)` (lines 27–37)
- Arguments: `user: User`
- Return: `list[str]` (sorted permissions)
- DB tables: None | DB operations: None | Idempotency-Key: No | CAS: No

#### 38. `require_permission(user, name)` (lines 40–42)
- Arguments: `user: User`, `name: str`
- Return: None (raises 403 `FORBIDDEN` if missing)
- DB tables: None | DB operations: None | Idempotency-Key: No | CAS: No

#### 39. `scope_clause(user)` (lines 45–51)
- Arguments: `user: User`
- Return: SQLAlchemy binary expression
- DB tables: `organization_access`, `interactions`
- DB operations: SQL criteria generation (subquery)
- Idempotency-Key: No | CAS: No

#### 40. `scoped_interaction(db, user, interaction_id)` (lines 54–58)
- Arguments: `db: Session`, `user: User`, `interaction_id: str`
- Return: `Interaction` (raises 404 `NOT_FOUND` if out of scope)
- DB tables: `interactions`, `organization_access`
- DB operations: SELECT
- Idempotency-Key: No | CAS: No

#### 41. `visible_organization_ids(db, user)` (lines 61–66)
- Arguments: `db: Session`, `user: User`
- Return: `set[str]`
- DB tables: `interactions`, `organization_access`
- DB operations: SELECT
- Idempotency-Key: No | CAS: No

#### 42. `validate_subject(db, program_id, product_id)` (lines 69–76)
- Arguments: `db: Session`, `program_id: str | None`, `product_id: str | None`
- Return: None (raises 422 `VALIDATION_ERROR` if incompatible)
- DB tables: `programs`, `products`, `program_products`
- DB operations: SELECT
- Idempotency-Key: No | CAS: No

#### 43. `allowed_owner(db, user, owner_id, *, creation=False)` (lines 78–92)
- Arguments: `db: Session`, `user: User`, `owner_id: str`, `creation: bool = False`
- Return: `User`
- DB tables: `users`
- DB operations: SELECT
- Idempotency-Key: No | CAS: No

#### 44. `attachment_dict(att)` (lines 95–106)
- Arguments: `att: Attachment`
- Return: `dict`
- DB tables: None | DB operations: None | Idempotency-Key: No | CAS: No

#### 45. `interaction_dict(db, item, attachments=None, lookup=None)` (lines 109–149)
- Arguments: `db: Session`, `item: Interaction`, `attachments: list | None = None`, `lookup: dict | None = None`
- Return: `dict`
- DB tables: `organizations`, `users`, `programs`, `products`, `directions`, `organization_contacts`, `contracts`, `licenses`, `attachments`
- DB operations: SELECT
- Idempotency-Key: No | CAS: No

#### 46. `event_dict(event)` (lines 153–166)
- Arguments: `event: InteractionEvent`
- Return: `dict`
- DB tables: None | DB operations: None | Idempotency-Key: No | CAS: No

#### 47. `comment_dict(comment)` (lines 169–178)
- Arguments: `comment: Comment`
- Return: `dict`
- DB tables: None | DB operations: None | Idempotency-Key: No | CAS: No

#### 48. `append_event(db, item, actor, kind, at, **extra)` (lines 181–191)
- Arguments: `db: Session`, `item: Interaction`, `actor: User`, `kind: str`, `at: datetime`, `**extra`
- Return: `InteractionEvent`
- DB tables: `interaction_events`, `organizations`, `users`, `programs`, `products`, `directions`, `organization_contacts`, `contracts`, `licenses`, `attachments`
- DB operations: SELECT, INSERT (`interaction_events`)
- Idempotency-Key: No | CAS: No

#### 49. `detail(db, user, interaction_id)` (lines 194–206)
- Arguments: `db: Session`, `user: User`, `interaction_id: str`
- Return: `dict` (complete interaction detail)
- DB tables: `interactions`, `organization_access`, `attachments`, `interaction_events`, `comments`, `organizations`, `users`, `programs`, `products`, `directions`, `organization_contacts`, `contracts`, `licenses`
- DB operations: SELECT
- Idempotency-Key: No | CAS: No

#### 50. `begin_command(db, user, operation, key, payload)` (lines 209–234)
- Arguments: `db: Session`, `user: User`, `operation: str`, `key: str`, `payload: Any`
- Return: `tuple[CommandResult, Any | None]`
- DB tables: `command_results`, `interactions`, `organization_access`
- DB operations: SELECT, INSERT (`command_results`)
- Idempotency-Key: Core idempotency handler (validates length <= 200, checks SHA-256 hash, returns replay if exists)
- CAS: No

#### 51. `finish_command(db, saved, response, resource_id)` (lines 237–240)
- Arguments: `db: Session`, `saved: CommandResult`, `response: Any`, `resource_id: str | None`
- Return: `response`
- DB tables: `command_results`
- DB operations: UPDATE (`command_results`)
- Idempotency-Key: Core idempotency finalizer | CAS: No

#### 52. `cas(db, item, expected_revision, **values)` (lines 243–251)
- Arguments: `db: Session`, `item: Interaction`, `expected_revision: int`, `**values`
- Return: None (raises 409 `REVISION_CONFLICT` if `rowcount != 1`)
- DB tables: `interactions`
- DB operations: CAS UPDATE (`update(Interaction).where(Interaction.id == item.id, Interaction.revision == expected_revision).values(revision=expected_revision + 1, **values)`)
- Idempotency-Key: No | CAS: Core CAS primitive

#### 53. `create_interaction(db, user, body, key)` (lines 254–289)
- Arguments: `db: Session`, `user: User`, `body: InteractionCreate`, `key: str | None`
- Return: `dict`
- DB tables: `command_results`, `organization_access`, `organizations`, `users`, `programs`, `products`, `program_products`, `organization_contacts`, `contracts`, `licenses`, `interactions`, `interaction_events`
- DB operations: SELECT, INSERT (`interactions`, `interaction_events`, `command_results`), UPDATE (`command_results`)
- Idempotency-Key: Yes (`operation="interactions.create"`) | CAS: No (initial revision = 1)

#### 54. `transition(db, user, interaction_id, body, key)` (lines 291–311)
- Arguments: `db: Session`, `user: User`, `interaction_id: str`, `body: InteractionTransition`, `key: str | None`
- Return: `dict`
- DB tables: `interactions`, `organization_access`, `command_results`, `programs`, `products`, `program_products`, `interaction_events`
- DB operations: SELECT, CAS UPDATE (`interactions`), INSERT (`interaction_events`, `command_results`), UPDATE (`command_results`)
- Idempotency-Key: Yes (`operation=f"transition:{item.id}"`) | CAS: Yes (`body.expected_revision`)

#### 55. `add_comment(db, user, interaction_id, body, key)` (lines 314–327)
- Arguments: `db: Session`, `user: User`, `interaction_id: str`, `body: CommentCreate`, `key: str | None`
- Return: `dict`
- DB tables: `interactions`, `organization_access`, `command_results`, `comments`, `interaction_events`
- DB operations: SELECT, CAS UPDATE (`interactions`), INSERT (`comments`, `interaction_events`, `command_results`), UPDATE (`command_results`)
- Idempotency-Key: Yes (`operation=f"comment:{item.id}"`) | CAS: Yes (`body.expected_revision`)

#### 56. `assign(db, user, interaction_id, body, key)` (lines 330–347)
- Arguments: `db: Session`, `user: User`, `interaction_id: str`, `body: AssignmentCreate`, `key: str | None`
- Return: `dict`
- DB tables: `interactions`, `organization_access`, `command_results`, `users`, `interaction_events`
- DB operations: SELECT, CAS UPDATE (`interactions`), INSERT (`interaction_events`, `command_results`), UPDATE (`command_results`)
- Idempotency-Key: Yes (`operation=f"assignment:{item.id}"`) | CAS: Yes (`body.expected_revision`)

#### 57. `update_interaction(db, user, interaction_id, body, key)` (lines 350–407)
- Arguments: `db: Session`, `user: User`, `interaction_id: str`, `body: InteractionUpdate`, `key: str | None`
- Return: `dict`
- DB tables: `interactions`, `organization_access`, `command_results`, `programs`, `products`, `program_products`, `organization_contacts`, `contracts`, `licenses`, `interaction_events`
- DB operations: SELECT, CAS UPDATE (`interactions`), INSERT (`interaction_events`, `command_results`), UPDATE (`command_results`)
- Idempotency-Key: Yes (`operation=f"update:{item.id}"`) | CAS: Yes (`body.expected_revision`)

#### 58. `catalogs(db, user)` (lines 410–444)
- Arguments: `db: Session`, `user: User`
- Return: `dict` (`organizations`, `programs`, `products`, `owners`, `directions`, `contacts`, `contracts`, `licenses`)
- DB tables: `organization_access`, `interactions`, `organizations`, `users`, `directions`, `organization_contacts`, `contracts`, `licenses`, `programs`, `products`
- DB operations: SELECT
- Idempotency-Key: No | CAS: No

#### 59. `validate_filters(db, user, organization_ids=(), program_ids=(), product_ids=(), owner_ids=())` (lines 447–455)
- Arguments: `db: Session`, `user: User`, `organization_ids`, `program_ids`, `product_ids`, `owner_ids`
- Return: None (raises 422 if invalid filter requested)
- DB tables: `organization_access`, `interactions`, `programs`, `products`, `users`
- DB operations: SELECT
- Idempotency-Key: No | CAS: No

#### 60. `list_interactions(db, user, q=None, organization_id=None, program_id=None, product_id=None, owner_id=None, state=None, page=1, page_size=50)` (lines 457–508)
- Arguments: `db: Session`, `user: User`, `q`, `organization_id`, `program_id`, `product_id`, `owner_id`, `state`, `page=1`, `page_size=50`
- Return: `dict` (`items`, `total`, `page`, `page_size`)
- DB tables: `interactions`, `organization_access`, `attachments`, `organizations`, `users`, `programs`, `directions`, `products`, `organization_contacts`, `contracts`, `licenses`
- DB operations: SELECT
- Idempotency-Key: No | CAS: No

#### 61. `dashboard(db, user)` (lines 511–523)
- Arguments: `db: Session`, `user: User`
- Return: `dict` (`total_interactions`, `total_organizations`, `active_interactions`, `completed_interactions`, `counts_by_state`, `recent_events`, `unassigned_program_count`)
- DB tables: `interactions`, `organization_access`, `interaction_events`
- DB operations: SELECT
- Idempotency-Key: No | CAS: No

#### 62. `snapshot(db, user, body)` (lines 526–579)
- Arguments: `db: Session`, `user: User`, `body: SnapshotReportRequest`
- Return: `dict` (snapshot report dataset)
- DB tables: `interactions`, `organization_access`, `programs`, `products`, `users`, `interaction_events`
- DB operations: SELECT
- Idempotency-Key: No | CAS: No

#### 63. `activity(db, user, body)` (lines 582–673)
- Arguments: `db: Session`, `user: User`, `body: ActivityReportRequest`
- Return: `dict` (activity report dataset with historical owner resolution)
- DB tables: `interactions`, `organization_access`, `programs`, `products`, `users`, `interaction_events`
- DB operations: SELECT
- Idempotency-Key: No | CAS: No

#### 64. `created_report(db, user, body)` (lines 676–738)
- Arguments: `db: Session`, `user: User`, `body: CreatedReportRequest`
- Return: `dict` (created interactions report dataset)
- DB tables: `interactions`, `organization_access`, `programs`, `products`, `users`, `interaction_events`
- DB operations: SELECT
- Idempotency-Key: No | CAS: No

#### 65. `preview_workflow_migration(db, user, from_version: int, to_version: int, status_mapping: dict[str, str]) -> dict` (lines 741–821)
- Arguments: `db: Session`, `user: User`, `from_version: int`, `to_version: int`, `status_mapping: dict[str, str]`
- Return: `dict` (`from_version`, `to_version`, `affected_interactions_count`, `status_distribution_before`, `status_distribution_after`, `unmapped_statuses`, `collisions`, `warnings`, `is_valid`)
- DB tables: `interactions`
- DB operations: SELECT (dry-run)
- Idempotency-Key: No | CAS: No

#### 66. `commit_workflow_migration(db, user, from_version: int, to_version: int, status_mapping: dict[str, str], idempotency_key: str | None) -> dict` (lines 824–935)
- Arguments: `db: Session`, `user: User`, `from_version: int`, `to_version: int`, `status_mapping: dict[str, str]`, `idempotency_key: str | None`
- Return: `dict` (`status`, `from_version`, `to_version`, `migrated_count`, `status_distribution`, `details`)
- DB tables: `command_results`, `interactions`, `interaction_events`
- DB operations: SELECT, CAS UPDATE (`interactions`), INSERT (`interaction_events`, `command_results`), UPDATE (`command_results`)
- Idempotency-Key: Yes (`operation=f"workflow_migration:{from_version}->{to_version}"`) | CAS: Yes (per affected interaction via `cas`)

---

## 4. Frontend Structure and Components (Section R4)

### 4.1 Routing and Screens (`frontend/src/App.tsx`)

#### Hash Router Implementation (`frontend/src/hooks.ts:42-51`, `frontend/src/App.tsx`)
- Hook `useRoute()` listens to `window.addEventListener('hashchange')`. Default hash: `#/overview`.
- Navigation method modifies `window.location.hash = '/' + target`.

#### Navigation Menu Items (`frontend/src/App.tsx:57-64`)
Condition for privileged items: `const isPrivileged = me.role === 'supervisor' || me.role === 'administrator' || me.role === 'admin';`.

1. `{ code: 'overview', name: 'Обзор', icon: 'grid' }` -> URL `#/overview`
2. `{ code: 'interactions', name: 'Взаимодействия', icon: 'layers' }` -> URL `#/interactions`
3. `{ code: 'reports', name: 'Отчёты', icon: 'chart' }` -> URL `#/reports`
4. `{ code: 'integrations', name: 'Интеграции', icon: 'refresh' }` (rendered only if `isPrivileged === true`) -> URL `#/integrations`
5. `{ code: 'catalogs', name: 'Справочники', icon: 'book' }` -> URL `#/catalogs`
6. `{ code: 'help', name: 'Помощь', icon: 'help' }` -> URL `#/help`

#### Screen Dispatching in `Workspace` (`frontend/src/App.tsx:101-118`)
- `activeNav = route.path.split('/')[0] || 'overview'`:
  - `activeNav === 'overview'` -> renders `<Overview ... />` (from `./views/WorkspaceViews`)
  - `activeNav === 'interactions'`:
    - If `route.path.startsWith('interactions/')`: renders `<InteractionPage id={interactionId} ... />` (from `./views/InteractionPage`)
    - Else: renders `<Interactions ... />` (from `./views/WorkspaceViews`)
  - `activeNav === 'reports'` -> renders `<Reports ... />` (from `./views/Reports`)
  - `activeNav === 'integrations'`:
    - If `isPrivileged`: renders `<IntegrationsView ... />` (from `./views/IntegrationsView`)
    - Else: renders access restricted panel
  - `activeNav === 'catalogs'` -> renders `<CatalogPage ... />` (imported from `./views/ReferenceViews`)
  - `activeNav === 'help'` -> renders `<HelpPage />` (imported from `./views/ReferenceViews`)
  - Fallback: renders "Страница не найдена" panel with navigation button.

#### Standalone Screens and Root Modals
- `<LoginScreen />` (`frontend/src/App.tsx:14-44`): Rendered when unauthenticated (`me === null`).
- `<CreateInteractionModal />` (`frontend/src/App.tsx:122`): Root modal controlled by state `createOpen`.

---

### 4.2 Views Catalog (`frontend/src/views/*`)

1. **`CatalogPage.tsx`**:
   - `ImportWizardModal` (line 76): 3-step modal for file upload, validation preview, and commit.
   - `WorkflowMigratorModal` (line 394): 3-step modal for target workflow selection, mapping preview, and commit.
   - `CatalogPage` (line 765): View for catalog browsing with modal trigger buttons.
   - Exported constants: `StateDefinition`, `WORKFLOW_V1_STATES`, `WORKFLOW_V2_STATES`.
2. **`IntegrationsView.tsx`**:
   - `IntegrationsView` (line 34): View with adapter cards (LMS Zion, Website), reconciliation inbox table, and learning metrics summary.
   - `ResolveModal` (line 775): Unexported modal dialog for application reconciliation.
3. **`InteractionPage.tsx`**:
   - `EditInteractionModal` (line 38): Modal for editing parameters (`PATCH /api/v1/interactions/{id}`).
   - `TransitionCommentModal` (line 191): Modal for mandatory comments during state transitions.
   - `InteractionPage` (line 252): Interaction detail view rendering attributes, transition action buttons, drag-and-drop file uploader, timeline events, and comments.
4. **`ReferenceViews.tsx`**:
   - Re-exports: `CatalogPage`, `ImportWizardModal`, `WorkflowMigratorModal` from `./CatalogPage`.
   - `HelpPage` (line 8): Interactive role-based knowledge base with tabs for Manager, Supervisor, Administrator, Error Codes, and 152-FZ security invariants.
5. **`Reports.tsx`**:
   - `StageFunnelDiagram` (line 30): SVG bar chart component for funnel stage counts and drop-offs.
   - `Reports` (line 156): View for Snapshot, Activity, and Created reports with XLSX, PDF, and JSON download actions.
6. **`WorkflowGraphView.tsx`**:
   - `WorkflowGraphView` (line 47): SVG flowchart visualizing 13 working stages and 2 terminal states.
   - Exported constants/types: `WORKFLOW_STATES`, `WorkflowStateMeta`, `WorkflowGraphViewProps`.
7. **`WorkspaceViews.tsx`**:
   - `InteractionTable` (line 7): Table listing interactions with sort and state badges.
   - `Overview` (line 20): Summary dashboard with metric cards, state counts, and recent activity.
   - `Interactions` (line 67): Registry view with search, filter controls, pagination, and interaction list.

---

### 4.3 Orphan, Unrouted, and Embedded Components

- **`WorkflowGraphView.tsx`**: Exists as an autonomous file in `frontend/src/views/`, but has no entry in the `navigation` array and is not routed in `App.tsx`. Its sole consumer is `InteractionPage.tsx` (lines 8, 533), where it is embedded as a child component inside the interaction detail screen.
- **Modal Dialog Components**: `ImportWizardModal`, `WorkflowMigratorModal`, `EditInteractionModal`, `TransitionCommentModal`, and `ResolveModal` are embedded dialogs controlled by parent state rather than standalone screens.
- **Sub-Components**: `StageFunnelDiagram` (rendered inside `Reports.tsx`) and `InteractionTable` (rendered inside `WorkspaceViews.tsx`).
- **Duplicate Export Pathway**: `CatalogPage` is exported from `CatalogPage.tsx` and re-exported through `ReferenceViews.tsx`. `App.tsx` imports it from `ReferenceViews.tsx`.

---

### 4.4 Authentication Token Storage (`frontend/src/auth.tsx`)

- **In-Memory Storage Mechanics**:
  - Keycloak client reference: `const keycloak = useRef<Keycloak | null>(null);` (`frontend/src/auth.tsx:31`).
  - Client instantiation: `keycloak.current = new Keycloak({ url: received.oidc.url, realm: received.oidc.realm, clientId: received.oidc.client_id });` (`frontend/src/auth.tsx:47-50`).
  - In OIDC mode, requests call `await client.updateToken(30)` in-memory and inject header `Authorization: 'Bearer ' + client.token` (`frontend/src/auth.tsx:78-82`).
  - In demo mode, `demoUserId` is held in React component state: `const [demoUserId, setDemoUserId] = useState('');` (`frontend/src/auth.tsx:27`). Requests inject header `'X-Demo-User': demoUserId` (`frontend/src/auth.tsx:74-77`).
- **Absence of Browser Persistence APIs**:
  - `localStorage`: 0 calls to `localStorage.setItem` or `localStorage.getItem` in the entire frontend source code. (The literal string appears only in documentation text inside `ReferenceViews.tsx`).
  - `sessionStorage`: 0 calls to `sessionStorage.setItem` or `sessionStorage.getItem`.
  - `document.cookie`: 0 calls reading or writing `document.cookie`.
  - HTTP requests configure `credentials: 'same-origin'` (`frontend/src/api.ts:51`).

---

### 4.5 API Client Methods (`frontend/src/api.ts`)

`ApiClient` defines 7 transport methods and 8 domain methods:
- Transport methods: `raw`, `get`, `post`, `patch`, `upload`, `download`, `downloadGet`.
  - Mutating methods accept or generate `Idempotency-Key` headers via `makeMutationKey()` (`crypto.randomUUID()`).
- Domain methods:
  - `getIntegrationsStatus()` -> `GET /integrations/status`
  - `syncIntegrationSource(source, key)` -> `POST /integrations/sync/{source}`
  - `syncIntegration(source, key)` -> delegate to `syncIntegrationSource`
  - `getIntegrationInbox(params)` -> `GET /integrations/inbox`
  - `resolveInboxItem(id, body, key)` -> `POST /integrations/inbox/{id}/resolve`
  - `getIntegrationMetrics(params)` -> `GET /integrations/metrics`
  - `previewWorkflowMigration(payload)` -> `POST /workflow/migrate/preview`
  - `commitWorkflowMigration(payload, key)` -> `POST /workflow/migrate/commit`

---

### 4.6 TypeScript Interfaces and Types Inventory (`frontend/src/types.ts`)

Total 37 types and interfaces declared:
- Auth & Config: `AppConfig`, `User`.
- Entities: `OrganizationContact`, `Contract`, `License`, `ProgramProductLink`, `Catalogs`.
- Interaction & Workflow: `InteractionUpdatePayload`, `Workflow`, `Interaction`, `Transition`, `WorkflowEvent`, `Comment`, `Attachment`, `InteractionDetail`, `InteractionList`, `Dashboard`.
- Reports: `SnapshotQuery`, `Snapshot`, `ActivityQuery`, `ActivityRow`, `ActivityResult`, `CreatedQuery`, `CreatedRow`, `CreatedResult`.
- Import: `ImportPreviewRow`, `ImportPreviewResponse`, `ImportCommitResponse`.
- Integrations: `IntegrationSource`, `IntegrationEntityType`, `InboxStatus`, `ReconciliationAction`, `IntegrationAdapterStatus`, `IntegrationsStatusResponse`, `IntegrationSyncResponse`, `ApplicationPayload`, `IntegrationInboxItem`, `IntegrationInboxResponse`, `ReconcileResolveParams`, `LearningMetricItem`, `ProgramMetricSummary`, `OrganizationMetricSummary`, `LearningMetricsSummaryResponse`.
- Migrations: `StatusCollision`, `WorkflowMigrationPreview`, `WorkflowMigrationResult`, `WorkflowMigratePreviewPayload`, `WorkflowMigrateCommitPayload`, `WorkflowMigratePreviewResponse`, `WorkflowMigrateCommitResponse`.

---

## 5. Test Suite Registry, Benchmarks, and Pytest Execution Output (Section R5)

### 5.1 Test Suite Inventory Overview

- Test runner: `pytest 9.1.1` under Python 3.14.7.
- Test directory: `backend/tests/`.
- Total test modules: 13 modules (`test_*.py`) + 1 shared fixture module (`conftest.py`).
- Total test functions (`def test_*`): 170.
- Test execution result: 170 passed, 0 failed, 2 deprecation warnings in 70.31 seconds.

Distribution by file:
- `backend/tests/test_adversarial_integrations.py`: 13 test cases
- `backend/tests/test_attachments.py`: 9 test cases
- `backend/tests/test_challenger_2_stress.py`: 26 test cases
- `backend/tests/test_challenger_migration_stress.py`: 16 test cases
- `backend/tests/test_core_concurrency_and_security.py`: 11 test cases
- `backend/tests/test_deliveries_models.py`: 17 test cases
- `backend/tests/test_errors_c01.py`: 14 test cases
- `backend/tests/test_import_wizard.py`: 5 test cases
- `backend/tests/test_integrations.py`: 12 test cases
- `backend/tests/test_interaction_patch.py`: 10 test cases
- `backend/tests/test_reports_multiformat.py`: 7 test cases
- `backend/tests/test_workflow_migration.py`: 13 test cases
- `backend/tests/test_working_slice.py`: 17 test cases

---

### 5.2 Test Cases and Invariants Catalog (All 170 Tests)

#### 1. `backend/tests/test_adversarial_integrations.py` (13 tests)
1. `test_deduplication_repeated_sequential_sync`: 10 sequential synchronizations of LMS and Website sources create 0 duplicate database rows; counts remain 12 `LearningMetric` and 16 `IntegrationInbox` records; composite key uniqueness `(source, entity_type, external_id, source_revision)` holds.
2. `test_deduplication_concurrent_sync_with_idempotency_key`: 4 concurrent synchronization calls sharing an `Idempotency-Key` return 200 or 409 without creating duplicate metrics or inbox records.
3. `test_deduplication_concurrent_sync_without_key_db_safety`: 4 concurrent uncoordinated synchronization calls without `Idempotency-Key` persist exactly 4 website inbox items via database unique constraints.
4. `test_deduplication_database_constraint_enforcement`: Database constraint `uq_inbox_dedup` on `IntegrationInbox` raises SQLAlchemy `IntegrityError` when attempting to insert rows with duplicate composite key values.
5. `test_deduplication_learning_metric_constraint`: Database unique constraint on `(source, external_id)` on table `learning_metrics` raises SQLAlchemy `IntegrityError` upon inserting duplicate records.
6. `test_reconciliation_conflict_on_already_resolved`: Attempting to resolve an already-processed or already-rejected inbox item returns HTTP 409 Conflict with error code `VALIDATION_ERROR`.
7. `test_reconciliation_cannot_resolve_learning_metric_inbox_item`: Invoking `/resolve` on an inbox item with `entity_type="learning_metric"` returns HTTP 409 or 422.
8. `test_reconciliation_unknown_action_returns_validation_error`: Invoking `/resolve` with an unrecognized action returns HTTP 400 or 422 with error code `VALIDATION_ERROR`.
9. `test_idempotency_key_replay_and_conflict_defense`: Sending an identical resolution request with the same `Idempotency-Key` returns cached HTTP 200 response; sending a modified payload with the same key returns HTTP 409 with error code `IDEMPOTENCY_CONFLICT`.
10. `test_idempotency_key_validation_boundaries`: Missing, empty, whitespace-only, or strings exceeding 200 characters in `Idempotency-Key` header return HTTP 400 or 422.
11. `test_rbac_manager_forbidden_on_all_integration_endpoints`: User with role `manager` receives HTTP 403 Forbidden with error code `FORBIDDEN` on `GET /status`, `POST /sync/lms`, `POST /sync/website`, `GET /inbox`, and `POST /inbox/{id}/resolve`.
12. `test_152_fz_manager_and_admin_isolation_on_reconciled_interaction`: An interaction created via inbox resolution is accessible by assigned owner (HTTP 200), returns HTTP 404 Not Found with error code `NOT_FOUND` for unassigned managers across GET, PATCH, comments, transitions, and attachments, and returns HTTP 404 for administrator users without explicit business scope.
13. `test_demand_metrics_scope_isolation_manager`: Calling `GET /api/v1/integrations/metrics` as `manager-a` returns metrics only for `org-1`; querying `org-2` returns 0 totals and empty lists.

#### 2. `backend/tests/test_attachments.py` (9 tests)
14. `test_upload_and_download_all_10_formats`: Upload and download for 10 extensions (`.png`, `.jpeg`, `.pdf`, `.zip`, `.gzip`, `.rar`, `.doc`, `.docx`, `.xls`, `.xlsx`) returns HTTP 201 for upload and HTTP 200 for download, computes 64-char SHA-256 checksum, sets `Content-Disposition`, and returns matching binary content.
15. `test_reject_dangerous_and_disallowed_formats`: Uploads with extensions `.exe`, `.sh`, `.php`, `.bat` return HTTP 422 with error code `FILE_TYPE_NOT_ALLOWED`.
16. `test_reject_magic_byte_mismatch`: Uploads with binary header signatures not matching declared extension return HTTP 422 with error code `FILE_TYPE_NOT_ALLOWED`.
17. `test_reject_file_too_large`: Uploads exceeding 25 MB return HTTP 413 with error code `FILE_TOO_LARGE`.
18. `test_path_traversal_sanitization`: Upload with relative traversal path (`../../../../etc/passwd.pdf`) sanitizes filename to basename `passwd.pdf` with HTTP 201.
19. `test_scope_isolation_152_fz`: Attempting to download, list, or upload attachments to an interaction owned by another manager returns HTTP 404 with error code `NOT_FOUND`.
20. `test_attachments_in_detail_and_events`: Uploading an attachment updates `attachments` list in interaction detail and appends an `attachment_uploaded` event in audit log.
21. `test_attachment_cross_interaction_access_returns_404`: Requesting an attachment using a URL with a different interaction ID returns HTTP 404 with error code `NOT_FOUND`.
22. `test_attachment_download_nonexistent_returns_404`: Requesting a non-existent attachment UUID returns HTTP 404 with error code `NOT_FOUND`.

#### 3. `backend/tests/test_challenger_2_stress.py` (26 tests)
23. `test_resolve_missing_idempotency_key`: Requesting `/inbox/{id}/resolve` without `Idempotency-Key` header returns HTTP 422 with error code `VALIDATION_ERROR`.
24. `test_resolve_empty_or_whitespace_idempotency_key`: Requesting `/inbox/{id}/resolve` with empty or whitespace-only `Idempotency-Key` header returns HTTP 422 with error code `VALIDATION_ERROR`.
25. `test_resolve_idempotency_key_length_limits`: `Idempotency-Key` headers of length 201 and 1000 return HTTP 422; header of length 200 characters returns HTTP 200.
26. `test_sync_idempotency_key_length_validation`: `Idempotency-Key` header exceeding 200 characters on `/sync/lms` returns HTTP 422 with error code `VALIDATION_ERROR`.
27. `test_resolve_malformed_body_structures`: Empty JSON body, JSON array body, or non-JSON content on `/inbox/{id}/resolve` returns HTTP 422.
28. `test_resolve_missing_or_blank_action`: Request body missing `action` attribute or containing whitespace-only action returns HTTP 422 with error code `VALIDATION_ERROR`.
29. `test_resolve_non_string_action_type_stress`: Passing integer `123` as `action` raises unhandled `AttributeError` returning HTTP 500 when server exceptions are not raised by test client.
30. `test_resolve_non_existent_inbox_id`: Resolving non-existent inbox item UUID returns HTTP 404 with error code `NOT_FOUND`.
31. `test_resolve_learning_metric_item_rejected`: Invoking `/resolve` on inbox item with `entity_type="learning_metric"` returns HTTP 422.
32. `test_unknown_reconciliation_actions`: Action strings `drop_db`, `unknown`, `DELETE`, SQL injection strings, `create_admin`, `accept`, `approve` return HTTP 422 with error code `VALIDATION_ERROR`.
33. `test_valid_actions_case_insensitivity`: Upper-case action string `REJECT` is processed identically to lower-case, returning HTTP 200.
34. `test_link_existing_non_existent_org_id`: Action `link_existing` with non-existent `organization_id` returns HTTP 404 with error code `NOT_FOUND`.
35. `test_link_existing_missing_org_id_on_unmatched_item`: Action `link_existing` without `organization_id` on unmatched inbox item returns HTTP 422 with error code `VALIDATION_ERROR`.
36. `test_link_existing_invalid_contact_for_org`: Action `link_existing` with contact ID not belonging to selected organization returns HTTP 422.
37. `test_link_existing_incompatible_program_and_product`: Action `link_existing` specifying incompatible program and product returns HTTP 422.
38. `test_create_new_whitespace_only_name_rejected`: Action `create_new` with whitespace-only organization name returns HTTP 422.
39. `test_create_new_empty_name_when_payload_has_no_name`: Action `create_new` with empty name on an inbox item without payload organization name returns HTTP 422.
40. `test_create_new_invalid_owner_id`: Action `create_new` specifying non-existent `owner_id` returns HTTP 404 or 422.
41. `test_metrics_empty_database_returns_clean_zeros`: Querying `/integrations/metrics` against empty table returns HTTP 200 with totals equal to 0, average attendance 0.0, and empty arrays.
42. `test_metrics_non_existent_filters_return_clean_zeros`: Filtering `/integrations/metrics` by non-existent `organization_id` or `program_id` returns HTTP 200 with 0 totals.
43. `test_metrics_sql_injection_probe`: SQL injection strings in query parameters of `/integrations/metrics` are parameterized and return HTTP 200 with 0 totals.
44. `test_manager_metrics_scoping_152_fz`: `manager-a` queries return only `org-1` metrics; querying `org-2` returns 0 metrics; `manager-b` returns only `org-2` and `org-3` metrics.
45. `test_manager_forbidden_from_all_administrative_endpoints`: Manager role receives HTTP 403 Forbidden with error code `FORBIDDEN` across `/status`, `/sync/lms`, `/sync/website`, `/inbox`, and `/inbox/{id}/resolve`.
46. `test_anonymous_requests_rejected_with_401`: Unauthenticated requests without identity headers return HTTP 401 with error code `UNAUTHENTICATED`.
47. `test_sync_unknown_source_rejected`: Triggering `/sync/{source}` with unknown source identifier returns HTTP 422 with error code `VALIDATION_ERROR`.
48. `test_sync_multiple_consecutive_runs_stability`: Executing 5 consecutive sync operations maintains counts of 12 LMS inbox records, 4 website inbox records, and 12 metric records in database.

#### 4. `backend/tests/test_challenger_migration_stress.py` (16 tests)
49. `test_stress_many_to_one_collision_preview_and_commit`: Mapping 5 distinct source states into target state `meeting` generates collision data in preview (HTTP 200), applies atomic updates upon commit (HTTP 200), increments card revisions, and logs `workflow_migrated` events with original states.
50. `test_stress_all_active_collapse_to_single_state`: Mapping all non-terminal states to `classes` succeeds on preview and commit, updating card `workflow_version` to 2 and setting allowed transitions to v2 targets.
51. `test_stress_many_to_one_collision_into_terminal_state`: Mapping active states to terminal state `cancelled` sets `closed_at`, empties `allowed_transitions`, and rejects subsequent transition attempts with HTTP 400, 409, or 422.
52. `test_stress_reject_unknown_source_and_target_statuses`: Status mappings containing non-existent source names, non-existent target names, SQL injection fragments, or path traversal strings return HTTP 422 with error code `VALIDATION_ERROR`.
53. `test_stress_reject_out_of_bounds_versions`: Migration versions (0, 2), (1, 0), (-1, 2), (1, -1), (1, 999), (999, 2), (100, 200) return HTTP 422 on preview and commit.
54. `test_stress_reject_empty_mapping`: Empty mapping dictionary returns HTTP 422 on `/workflow/migrate/preview`.
55. `test_stress_reject_commit_with_unmapped_active_card_statuses`: When an active interaction is in a status omitted from mapping, preview returns `is_valid=False` and commit returns HTTP 422 with error code `VALIDATION_ERROR`.
56. `test_stress_concurrent_migrations_same_idempotency_key`: 5 concurrent commit calls using same `Idempotency-Key` return HTTP 200 with identical response payloads and record exactly 1 `workflow_migrated` audit event per card.
57. `test_stress_sequential_migrations_different_keys_zero_leak`: Second migration invocation from v1 to v2 after all active cards are migrated returns HTTP 200 with `migrated_count=0` and empty details.
58. `test_stress_idempotency_key_boundary_limits`: `Idempotency-Key` header of 200 characters returns HTTP 200; 201 characters returns HTTP 422 on `/workflow/migrate/commit`.
59. `test_stress_reject_same_version_migration`: Migrations where `from_version == to_version` (1->1, 2->2) return HTTP 422 on preview and commit.
60. `test_stress_round_trip_migration_v1_to_v2_to_v1`: Round-trip migration v1 -> v2 -> v1 increments card revision by 2, restores v1 transition rules, and records two distinct `workflow_migrated` audit events.
61. `test_stress_cas_stale_revision_rejected_post_migration`: Operations (transition, PATCH, comment) providing pre-migration revision return HTTP 409 Conflict with error code `REVISION_CONFLICT` or `CONCURRENCY_CONFLICT`; operations providing post-migration revision succeed.
62. `test_stress_cas_tampering_arbitrary_revision_values`: Negative, zero, or out-of-range revision numbers return HTTP 409 or 422.
63. `test_stress_deep_history_comments_attachments_integrity`: Interaction with 3 historical transitions, 3 comments, and 2 attachments retains all comments, attachments, foreign keys, and strictly contiguous sequence indices post-migration with 1 appended `workflow_migrated` event.
64. `test_stress_rbac_strict_rejection_of_managers_and_anonymous`: Manager roles receive HTTP 403 Forbidden with error code `FORBIDDEN`, unauthenticated calls receive HTTP 401, and supervisor/admin roles receive HTTP 200 on preview and commit endpoints.

#### 5. `backend/tests/test_core_concurrency_and_security.py` (11 tests)
65. `test_cas_concurrency_parallel_race_twenty_threads_patch`: 20 concurrent threads submitting PATCH requests with same `expected_revision` yield exactly 1 HTTP 200 response and exactly 19 HTTP 409 Conflict responses with error code `REVISION_CONFLICT`; database revision increments by 1.
66. `test_cas_concurrency_parallel_race_twenty_threads_transition`: 20 concurrent threads submitting state transition requests with same `expected_revision` yield exactly 1 HTTP 200 response and exactly 19 HTTP 409 responses; state transitions once.
67. `test_scope_isolation_manager_cross_access_strict_404`: Cross-scope access attempts by `manager-a` on an interaction owned by `manager-b` return HTTP 404 Not Found with error code `NOT_FOUND` for GET detail, attachment download, comment submission, PATCH update, and transition.
68. `test_scope_isolation_after_reassignment_strict_404`: Reassigning an interaction from `manager-a` to `manager-b` results in immediate HTTP 404 Not Found for subsequent GET requests by `manager-a`.
69. `test_idempotency_caching_and_replay_without_side_effects`: Replaying requests with same `Idempotency-Key` returns cached HTTP 200 response without duplicating events or revisions; altering payload returns HTTP 409 with code `IDEMPOTENCY_CONFLICT`; omitting key returns HTTP 422.
70. `test_workflow_illegal_transition_rejections`: Transition to `materials_transfer` without program/product returns HTTP 422; cancellation without comment returns HTTP 422; transition from terminal state returns HTTP 409/422; skipping workflow steps returns HTTP 409/422; missing `expected_revision` returns HTTP 422.
71. `test_formula_injection_escaping_in_reports`: Titles starting with formula characters (`=`, `+`, `-`, `@`) are prefixed with single quote `'` in XLSX export without `<f>` executable formula tags.
72. `test_formula_injection_escaping_in_csv_export`: Titles starting with formula characters are escaped with leading `'` in CSV exports.
73. `test_file_security_path_traversal_null_bytes_and_oracle_defense`: Windows backslash traversal sequences are sanitized to basename; null-byte in filename returns HTTP 422; upload attempts of disallowed types or oversized files to another manager's card return strict HTTP 404 Not Found (zero-oracle defense); oversized file on caller's card returns HTTP 413.
74. `test_frontend_jwt_in_memory_audit`: Static file audit verifies that `localStorage.setItem`, `sessionStorage.setItem`, `localStorage[...]`, and `sessionStorage[...]` do not occur in `frontend/src/`.
75. `test_immutable_audit_log_temporal_integrity`: Successive mutating operations record an immutable `InteractionEvent` with strictly increasing contiguous sequence indices, actor names, ISO timestamps, and snapshot dictionaries.

#### 6. `backend/tests/test_deliveries_models.py` (17 tests)
76. `test_models_metadata_and_declarative_schema`: Declarative tables `deliveries` and `delivery_items` verify column names, lengths, nullability constraints, primary keys, foreign key targets, index flags, and `ON DELETE CASCADE` on `delivery_items.delivery_id`.
77. `test_delivery_creation_defaults_and_persistence`: Instantiating `Delivery` with minimal required fields persists default values `status="draft"`, `channel="email"`, `revision=1`, and autogenerated UUID.
78. `test_delivery_and_delivery_items_persistence_with_all_kinds`: Persisting `Delivery` with child `DeliveryItem` records of kinds `material`, `document`, and `license` links foreign keys to `Attachment` and `License`.
79. `test_delivery_lifecycle_and_updates`: Delivery transitions from `draft` to `sent` to `confirmed` increment revision and record `sent_at` and `confirmed_at` timestamps.
80. `test_delivery_cascade_deletion`: Deleting a `Delivery` ORM record cascades deletion to all child `DeliveryItem` records.
81. `test_delivery_foreign_key_constraints_enforced`: Inserting records with non-existent foreign key references (`organization_id`, `recorded_by`, `interaction_id`, `recipient_contact_id`, `delivery_id`, `attachment_id`, `license_id`) raises SQLAlchemy `IntegrityError`.
82. `test_delivery_and_item_nullability_constraints`: Setting non-nullable columns to `None` raises SQLAlchemy `IntegrityError`.
83. `test_engine_level_raw_sql_cascade_deletion`: Raw SQL `DELETE FROM deliveries WHERE id = :id` cascades deletion to `delivery_items` at database engine layer.
84. `test_postgresql_dialect_ddl_generation`: Compiling table DDL against `sqlalchemy.dialects.postgresql` generates valid PostgreSQL DDL syntax.
85. `test_delivery_default_uuid_uniqueness`: Creating multiple `Delivery` instances without explicit IDs produces distinct 36-character UUID4 strings.
86. `test_delivery_parent_referential_integrity_restrict`: Attempting to delete parent `Interaction`, `Attachment`, or `License` referenced by Delivery or Item raises SQLAlchemy `IntegrityError` (foreign key RESTRICT).
87. `test_delivery_cas_revision_update_and_cancellation`: CAS update via SQL `update(Delivery).where(Delivery.id == d_id, Delivery.revision == 1)` succeeds with rowcount=1; update with stale revision affects rowcount=0.
88. `test_delivery_core_insert_with_callable_defaults`: SQLAlchemy Core `insert(Delivery).values(...)` evaluates callable defaults for ID and timestamps.
89. `test_delivery_complex_relational_joins_and_boundary_strings`: Multi-table join across 7 tables executes correctly with maximum boundary string lengths (250 chars title, 120 chars material_version).
90. `test_delivery_isolated_parent_referential_integrity`: Deleting isolated parent records (`OrganizationContact`, `Interaction`, `User`, `Organization`) referenced by Delivery raises SQLAlchemy `IntegrityError`.
91. `test_child_item_deletion_leaves_delivery_intact`: Deleting a child `DeliveryItem` leaves parent `Delivery` intact.
92. `test_delivery_bulk_operations_and_temporal_ordering`: Bulk creation of 25 deliveries produces unique IDs, preserves Unicode emojis, and supports query sorting by `(organization_id, sent_at DESC)`.

#### 7. `backend/tests/test_errors_c01.py` (14 tests)
93. `test_api_error_attributes`: `APIError` initializes with code, message, default status 422, details, and empty field_errors list.
94. `test_domain_error_envelope_c01_compliance`: Error response body conforms to envelope `{error: {code, message, request_id, field_errors, details}}`, echoing `X-Request-ID`.
95. `test_request_validation_error_normalizes_loc`: `RequestValidationError` normalizes location tuples by stripping leading `"body"` component.
96. `test_unhandled_exception_returns_internal_error_500`: Unhandled server exceptions return HTTP 500 with code `INTERNAL_ERROR` and generic message, hiding database tables and exception tracebacks.
97. `test_validation_preserves_field_named_body`: Request payload containing schema attribute named `body` preserves `"body"` in normalized field error paths.
98. `test_empty_body_and_malformed_json`: Empty request body and malformed JSON payloads return HTTP 422 with code `VALIDATION_ERROR`.
99. `test_error_handlers_safe_with_mock_request`: Exception handlers execute without errors when invoked with mock request objects lacking Starlette Request attributes.
100. `test_query_path_header_validation_normalization`: Validation errors across query, path, and header parameters strip parameter location prefixes (`path.`, `query.`, `header.`).
101. `test_api_error_headers_and_status_code_alias`: `APIError` preserves custom HTTP headers (e.g. `Retry-After`) and provides bidirectional aliasing between `status` and `status_code`.
102. `test_validation_error_with_none_or_missing_loc_fields`: Validation errors containing `loc=None` or empty tuples normalize without throwing exceptions.
103. `test_domain_error_with_complex_types_in_details`: Detail dictionaries containing UUID, datetime, Decimal, and set objects are serialized to strings, floats, and lists.
104. `test_api_error_string_status_coercion`: Passing a string status value (e.g. `"400"`) is coerced to an integer HTTP status code.
105. `test_header_case_insensitive_deduplication`: Custom correlation ID header in exception headers overrides default without duplicate wire headers.
106. `test_validation_error_with_non_dict_error_objects`: Non-dict error objects with `loc` and `msg` attributes are parsed into field errors without errors.

#### 8. `backend/tests/test_import_wizard.py` (5 tests)
107. `test_csv_preview_dry_run_and_commit`: CSV preview dry-run returns row counts without database mutation; commit persists organizations, contacts, and contracts; Idempotency-Key replay returns identical response; altered payload returns HTTP 409 `IDEMPOTENCY_CONFLICT`.
108. `test_xlsx_preview_and_error_handling`: XLSX import parses sheets, detects missing names and duplicate rows, and reports errors with diagnostic messages.
109. `test_import_existing_organization_updates_and_adds_contracts`: Importing a file with an existing organization name sets row status to `"update"`, adds new contracts, and prevents duplicate organization records.
110. `test_import_incompatible_program_product_flagged`: Preview flags incompatible program and product combinations with validation error messages.
111. `test_import_commit_multipart_form_data`: Commit endpoint accepts direct `multipart/form-data` file uploads.

#### 9. `backend/tests/test_integrations.py` (12 tests)
112. `test_integrations_status_rbac`: Roles `supervisor` and `administrator` receive HTTP 200 on `/status`; role `manager` receives HTTP 403 Forbidden.
113. `test_lms_sync_and_learning_metrics`: Syncing LMS ingests 12 educational metric envelopes, persisting 12 `LearningMetric` records and 12 `IntegrationInbox` records.
114. `test_sync_deduplication_and_idempotency`: Repeat LMS sync calls skip existing envelopes without database constraint errors, maintaining 12 records.
115. `test_website_sync_creates_pending_inbox_items`: Syncing website creates 4 application envelopes in `pending` status, auto-matching known organizations by name.
116. `test_inbox_pagination_and_filtering`: Inbox items support filtering by `source` and `status` and pagination with `page` and `page_size`.
117. `test_reconcile_link_existing_with_interaction`: Reconciling with `link_existing` updates inbox status to `processed`, links organization, and creates an interaction in `contact_search` at revision 1.
118. `test_reconcile_create_new_organization`: Reconciling with `create_new` creates a new organization, contact, access grant, and interaction.
119. `test_reconcile_reject`: Reconciling with `reject` transitions inbox status to `rejected` and stores reason in `error_message`.
120. `test_reconcile_conflict_already_processed`: Attempting to resolve an already-resolved or rejected inbox item returns HTTP 409 Conflict.
121. `test_reconcile_idempotency_key_replay`: Repeating resolution with same `Idempotency-Key` returns cached response without duplicate interactions.
122. `test_learning_metrics_summary_aggregation`: `/metrics` aggregates cohort counts, student counts, average attendance rate, and supports filtering by organization and program.
123. `test_scope_isolation_152_fz_on_created_interaction`: Interaction created via inbox is accessible by assigned manager (HTTP 200) and returns HTTP 404 Not Found for unassigned managers.

#### 10. `backend/tests/test_interaction_patch.py` (10 tests)
124. `test_patch_resolves_deadlock_d02`: Card created without program/product transitions up to `document_signing`; transition to `materials_transfer` returns HTTP 422 `VALIDATION_ERROR`; PATCH assigns compatible program/product; subsequent transition to `materials_transfer` returns HTTP 200.
125. `test_patch_cas_conflict`: PATCH with stale or future `expected_revision` returns HTTP 409 `REVISION_CONFLICT`; matching revision increments revision by 1.
126. `test_patch_invalid_subject_combination`: Incompatible program/product combination, non-existent program, or non-existent product returns HTTP 422 `VALIDATION_ERROR`.
127. `test_patch_disallows_clearing_subject_in_late_states`: Clearing program or product to None when card is in `materials_transfer` or later returns HTTP 422 `VALIDATION_ERROR`.
128. `test_patch_idempotency_and_event_sequence`: Replaying PATCH with identical `Idempotency-Key` returns cached response and logs 1 `attributes_corrected` event; different body with same key returns HTTP 409 `IDEMPOTENCY_CONFLICT`; missing key returns HTTP 400 or 422.
129. `test_patch_scope_isolation_manager`: Manager B attempting PATCH on Manager A's card returns HTTP 404 `NOT_FOUND`; administrator receives HTTP 403 or 404.
130. `test_patch_scope_isolation_after_reassignment`: After supervisor reassigns card to Manager B, Manager A receives HTTP 404 `NOT_FOUND` on subsequent PATCH.
131. `test_patch_links_contact_contract_license`: Attaching contact, contract, and license succeeds; foreign organization entities or mismatched license product return HTTP 422 `VALIDATION_ERROR`.
132. `test_catalogs_returns_contracts_licenses_contacts`: `/api/v1/catalogs` returns contacts, contracts, and licenses scoped to visible organizations.
133. `test_patch_disallows_modifying_closed_interaction`: Attempting to PATCH a cancelled interaction returns HTTP 422 `VALIDATION_ERROR`.

#### 11. `backend/tests/test_reports_multiformat.py` (7 tests)
134. `test_snapshot_export_json_xlsx_pdf`: Exporting snapshot report supports JSON (valid JSON payload), XLSX (starts with `PK\x03\x04`, valid OpenXML structure), and PDF (starts with `%PDF-1.4`, ends with `%%EOF`).
135. `test_activity_report_and_exports`: Activity report calculates transitions in date interval, groups by to_state and historical owner, and exports to XLSX and PDF.
136. `test_created_report_and_exports`: Created report calculates interactions created in date interval, groups by organization, and exports to XLSX and PDF.
137. `test_unsupported_export_format_returns_422`: Requesting unsupported export format (e.g. `format=doc`) returns HTTP 422 with error code `VALIDATION_ERROR`.
138. `test_activity_report_historical_owner_resolution_after_reassignment`: Activity report resolves historical owner at event timestamp, attributing transitions to previous and current managers respectively.
139. `test_snapshot_zero_buckets_for_all_fifteen_states`: Snapshot report `counts_by_state` dictionary contains all 15 states (13 active + 2 terminal) as integer values >= 0.
140. `test_xlsx_formula_injection_defense`: Title starting with formula characters (`=HYPERLINK...`) is written as `t="inlineStr"` without `<f>` executable formula elements.

#### 12. `backend/tests/test_workflow_migration.py` (13 tests)
141. `test_workflow_endpoint_versioning`: `/api/v1/workflow` returns version 1 (15 states, 29 transitions) by default, version 2 (15 states, 36 transitions) with `version=2`, and HTTP 404 for unknown version.
142. `test_workflow_migrate_rbac_manager_forbidden`: Manager role receives HTTP 403 Forbidden with error code `FORBIDDEN` on `/workflow/migrate/preview` and `/workflow/migrate/commit`.
143. `test_workflow_migrate_rbac_supervisor_and_admin_allowed`: Supervisor and administrator roles receive HTTP 200 on preview.
144. `test_workflow_migrate_reject_terminal_to_active`: Mapping terminal states (`completed`, `cancelled`) to active states returns HTTP 422 `VALIDATION_ERROR`.
145. `test_workflow_migrate_reject_invalid_versions_and_statuses`: Same version, unknown version (99), or unknown target status returns HTTP 422.
146. `test_workflow_migrate_missing_idempotency_key`: Missing, whitespace, or >200 chars `Idempotency-Key` on commit returns HTTP 422.
147. `test_workflow_migrate_preview_calculation_and_collisions`: Preview calculates affected interaction counts, status distributions, and reports N-to-1 collisions.
148. `test_workflow_migrate_preview_unmapped_status`: Omitting an active status sets `is_valid=False`, lists unmapped statuses, and emits warnings.
149. `test_workflow_migrate_commit_atomic_execution`: Commit migrates cards atomically, increments revision, and updates `workflow_version` to 2.
150. `test_workflow_migrate_preserves_history_comments_attachments`: Migration preserves existing comments, attachments, and appends `workflow_migrated` audit event.
151. `test_workflow_migrate_idempotency_replay_and_conflict`: Replaying commit with same Idempotency-Key returns cached response; modified body with same key returns HTTP 409 `IDEMPOTENCY_CONFLICT`.
152. `test_v2_allowed_transitions_and_execution_after_migration`: Post-migration, cards unlock v2 fast-track transitions (`meeting_to_document_signing`).
153. `test_workflow_migrate_to_terminal_updates_closed_at`: Migrating active status to terminal status sets `closed_at` and removes allowed transitions.

#### 13. `backend/tests/test_working_slice.py` (17 tests)
154. `test_auth_requires_explicit_identity`: `/config` reports `demo` auth mode; missing identity returns HTTP 401; non-existent user returns HTTP 401; valid user returns user profile (HTTP 200).
155. `test_demo_and_sqlite_cannot_be_accidentally_enabled_in_production`: `create_app` raises `RuntimeError` when `app_env="production"` with `auth_mode="demo"` or `database_url="sqlite:///:memory:"`.
156. `test_health_and_openapi_are_real`: `/health/live`, `/health/ready`, `/openapi.json`, and `/docs` return HTTP 200; openapi schema contains expected transition endpoints.
157. `test_manager_scope_applies_to_list_direct_detail_and_dashboard`: Listing interactions for Manager A and Manager B returns disjoint sets; Manager A requesting Manager B's interaction returns HTTP 404; dashboard totals match scoped counts.
158. `test_technical_admin_has_no_implicit_business_scope`: Administrator listing interactions returns total=0; snapshot report returns empty rows.
159. `test_create_and_idempotent_replay_do_not_duplicate`: Creating interaction with same Idempotency-Key returns HTTP 201 with identical ID and exactly 1 `created` event; altering payload returns HTTP 409.
160. `test_creation_requires_key_and_does_not_allow_manager_to_assign_another_user`: Creation without Idempotency-Key returns HTTP 400 or 422; manager attempting to set another user as owner returns HTTP 403.
161. `test_transition_revision_and_idempotency_are_enforced`: Transition enforces `expected_revision`, increments revision by 1, logs `state_changed` event; replay with same key returns cached response; stale revision returns HTTP 409.
162. `test_forbidden_transition_cannot_skip_workflow`: Attempting to skip steps in workflow returns HTTP 409 or 422; interaction state remains unchanged.
163. `test_missing_program_and_product_prevent_late_stage`: Card without program and product can transition to `document_signing` but transition to `materials_transfer` returns HTTP 422.
164. `test_cancel_requires_comment_and_terminal_has_no_transition`: Cancellation transition requires non-empty comment; sets state to `cancelled`, records `closed_at`, empties `allowed_transitions`.
165. `test_comment_is_persisted_and_stale_comment_does_not_overwrite`: Adding comment persists comment body; replay returns 201; stale revision returns HTTP 409.
166. `test_reassignment_restricts_old_owner_and_keeps_historical_owner`: Reassigning owner requires supervisor role (manager gets HTTP 403); former owner loses access (HTTP 404); historical reports attribute state to owner at event time.
167. `test_idempotent_transition_replay_checks_current_access`: Replaying transition after card reassignment performs current access check, returning HTTP 404 for old owner.
168. `test_snapshot_effective_and_received_boundaries`: Snapshot report respects `as_of` timestamp boundary, `as_of_inclusive` flag, and `knowledge_cutoff` boundary.
169. `test_json_export_is_scoped_and_matches_report`: JSON export matches snapshot preview rows and totals, includes `Content-Disposition: attachment`, and restricts rows to caller scope.
170. `test_filter_intersection_pagination_and_input_validation`: Filtering by query search, owner_id, and state intersects filters; pagination handles page and page_size; invalid pagination (page=0, page_size=99999) returns HTTP 422.

---

### 5.3 Benchmarks Inventory (`backend/benchmarks/benchmark_load.py`)

- File: `backend/benchmarks/benchmark_load.py` (699 lines, 26,980 bytes).
- Description: Standalone asynchronous load testing tool implemented with `asyncio` and `httpx`. Evaluates response latency and concurrency limits under simultaneous interactive and analytical workloads.
- Command-line arguments:
  - `--url`: Live server base URL (default: `None`, triggers in-process ASGI mode).
  - `--in-process`: Force in-process ASGI execution.
  - `--duration`: Benchmark duration in seconds (default: `10`).
  - `--users`: Number of concurrent interactive user workers (default: `50`).
  - `--analysts`: Number of concurrent analytical report stream workers (default: `10`).
  - `--warmup`: Warmup period in seconds prior to metrics collection (default: `2`).
  - `--database-url`: Connection string (default: temporary SQLite database configured with WAL mode).
  - `--output`: Markdown report output path (default: `../docs/benchmarks/load-test-report.md`).
- Concurrency distribution:
  - 40 simulated managers: 20 `manager-a` querying `org-1` cards (`ix-1`, `ix-2`, `ix-3`), 20 `manager-b` querying `org-2` cards (`ix-4`, `ix-5`, `ix-6`).
  - 8 simulated supervisors: querying interaction registry, dashboard, and integration metrics.
  - 2 simulated administrators: querying integration status, reconciliation inbox, catalogs, and configuration.
  - 10 analytical report streams: querying snapshot reports, activity reports, created reports, and triggering XLSX and PDF binary exports.
- Target latency / SLA metrics:
  - P95 latency threshold: <= 1000 ms (1.0 s).
  - Concurrency capacity: >= 50 concurrent users + 10 analytical streams.
  - Error rate: 0.00% under concurrent execution.

---

### 5.4 Verbatim Pytest Terminal Execution Output

```text
============================= test session starts ==============================
platform linux -- Python 3.14.7, pytest-9.1.1, pluggy-1.6.0 -- /home/muhammad/Dev/HACKATHON/LCT/rost_crm/backend/.venv/bin/python
cachedir: .pytest_cache
rootdir: /home/muhammad/Dev/HACKATHON/LCT/rost_crm/backend
plugins: anyio-4.15.1
collecting ... collecting 0 items                                                             collected 170 items                                                            

tests/test_adversarial_integrations.py::test_deduplication_repeated_sequential_sync PASSED [  0%]
tests/test_adversarial_integrations.py::test_deduplication_concurrent_sync_with_idempotency_key PASSED [  1%]
tests/test_adversarial_integrations.py::test_deduplication_concurrent_sync_without_key_db_safety PASSED [  1%]
tests/test_adversarial_integrations.py::test_deduplication_database_constraint_enforcement PASSED [  2%]
tests/test_adversarial_integrations.py::test_deduplication_learning_metric_constraint PASSED [  2%]
tests/test_adversarial_integrations.py::test_reconciliation_conflict_on_already_resolved PASSED [  3%]
tests/test_adversarial_integrations.py::test_reconciliation_cannot_resolve_learning_metric_inbox_item PASSED [  4%]
tests/test_adversarial_integrations.py::test_reconciliation_unknown_action_returns_validation_error PASSED [  4%]
tests/test_adversarial_integrations.py::test_idempotency_key_replay_and_conflict_defense PASSED [  5%]
tests/test_adversarial_integrations.py::test_idempotency_key_validation_boundaries PASSED [  5%]
tests/test_adversarial_integrations.py::test_rbac_manager_forbidden_on_all_integration_endpoints PASSED [  6%]
tests/test_adversarial_integrations.py::test_152_fz_manager_and_admin_isolation_on_reconciled_interaction PASSED [  7%]
tests/test_adversarial_integrations.py::test_demand_metrics_scope_isolation_manager PASSED [  7%]
tests/test_attachments.py::test_upload_and_download_all_10_formats PASSED [  8%]
tests/test_attachments.py::test_reject_dangerous_and_disallowed_formats PASSED [  8%]
tests/test_attachments.py::test_reject_magic_byte_mismatch PASSED        [  9%]
tests/test_attachments.py::test_reject_file_too_large PASSED             [ 10%]
tests/test_attachments.py::test_path_traversal_sanitization PASSED       [ 10%]
tests/test_attachments.py::test_scope_isolation_152_fz PASSED            [ 11%]
tests/test_attachments.py::test_attachments_in_detail_and_events PASSED  [ 11%]
tests/test_attachments.py::test_attachment_cross_interaction_access_returns_404 PASSED [ 12%]
tests/test_attachments.py::test_attachment_download_nonexistent_returns_404 PASSED [ 12%]
tests/test_challenger_2_stress.py::test_resolve_missing_idempotency_key PASSED [ 13%]
tests/test_challenger_2_stress.py::test_resolve_empty_or_whitespace_idempotency_key PASSED [ 14%]
tests/test_challenger_2_stress.py::test_resolve_idempotency_key_length_limits PASSED [ 14%]
tests/test_challenger_2_stress.py::test_sync_idempotency_key_length_validation PASSED [ 15%]
tests/test_challenger_2_stress.py::test_resolve_malformed_body_structures PASSED [ 15%]
tests/test_challenger_2_stress.py::test_resolve_missing_or_blank_action PASSED [ 16%]
tests/test_challenger_2_stress.py::test_resolve_non_string_action_type_stress PASSED [ 17%]
tests/test_challenger_2_stress.py::test_resolve_non_existent_inbox_id PASSED [ 17%]
tests/test_challenger_2_stress.py::test_resolve_learning_metric_item_rejected PASSED [ 18%]
tests/test_challenger_2_stress.py::test_unknown_reconciliation_actions PASSED [ 18%]
tests/test_challenger_2_stress.py::test_valid_actions_case_insensitivity PASSED [ 19%]
tests/test_challenger_2_stress.py::test_link_existing_non_existent_org_id PASSED [ 20%]
tests/test_challenger_2_stress.py::test_link_existing_missing_org_id_on_unmatched_item PASSED [ 20%]
tests/test_challenger_2_stress.py::test_link_existing_invalid_contact_for_org PASSED [ 21%]
tests/test_challenger_2_stress.py::test_link_existing_incompatible_program_and_product PASSED [ 21%]
tests/test_challenger_2_stress.py::test_create_new_whitespace_only_name_rejected PASSED [ 22%]
tests/test_challenger_2_stress.py::test_create_new_empty_name_when_payload_has_no_name PASSED [ 22%]
tests/test_challenger_2_stress.py::test_create_new_invalid_owner_id PASSED [ 23%]
tests/test_challenger_2_stress.py::test_metrics_empty_database_returns_clean_zeros PASSED [ 24%]
tests/test_challenger_2_stress.py::test_metrics_non_existent_filters_return_clean_zeros PASSED [ 24%]
tests/test_challenger_2_stress.py::test_metrics_sql_injection_probe PASSED [ 25%]
tests/test_challenger_2_stress.py::test_manager_metrics_scoping_152_fz PASSED [ 25%]
tests/test_challenger_2_stress.py::test_manager_forbidden_from_all_administrative_endpoints PASSED [ 26%]
tests/test_challenger_2_stress.py::test_anonymous_requests_rejected_with_401 PASSED [ 27%]
tests/test_challenger_2_stress.py::test_sync_unknown_source_rejected PASSED [ 27%]
tests/test_challenger_2_stress.py::test_sync_multiple_consecutive_runs_stability PASSED [ 28%]
tests/test_challenger_migration_stress.py::test_stress_many_to_one_collision_preview_and_commit PASSED [ 28%]
tests/test_challenger_migration_stress.py::test_stress_all_active_collapse_to_single_state PASSED [ 29%]
tests/test_challenger_migration_stress.py::test_stress_many_to_one_collision_into_terminal_state PASSED [ 30%]
tests/test_challenger_migration_stress.py::test_stress_reject_unknown_source_and_target_statuses PASSED [ 30%]
tests/test_challenger_migration_stress.py::test_stress_reject_out_of_bounds_versions PASSED [ 31%]
tests/test_challenger_migration_stress.py::test_stress_reject_empty_mapping PASSED [ 31%]
tests/test_challenger_migration_stress.py::test_stress_reject_commit_with_unmapped_active_card_statuses PASSED [ 32%]
tests/test_challenger_migration_stress.py::test_stress_concurrent_migrations_same_idempotency_key PASSED [ 32%]
tests/test_challenger_migration_stress.py::test_stress_sequential_migrations_different_keys_zero_leak PASSED [ 33%]
tests/test_challenger_migration_stress.py::test_stress_idempotency_key_boundary_limits PASSED [ 34%]
tests/test_challenger_migration_stress.py::test_stress_reject_same_version_migration PASSED [ 34%]
tests/test_challenger_migration_stress.py::test_stress_round_trip_migration_v1_to_v2_to_v1 PASSED [ 35%]
tests/test_challenger_migration_stress.py::test_stress_cas_stale_revision_rejected_post_migration PASSED [ 35%]
tests/test_challenger_migration_stress.py::test_stress_cas_tampering_arbitrary_revision_values PASSED [ 36%]
tests/test_challenger_migration_stress.py::test_stress_deep_history_comments_attachments_integrity PASSED [ 37%]
tests/test_challenger_migration_stress.py::test_stress_rbac_strict_rejection_of_managers_and_anonymous PASSED [ 37%]
tests/test_core_concurrency_and_security.py::test_cas_concurrency_parallel_race_twenty_threads_patch PASSED [ 38%]
tests/test_core_concurrency_and_security.py::test_cas_concurrency_parallel_race_twenty_threads_transition PASSED [ 38%]
tests/test_core_concurrency_and_security.py::test_scope_isolation_manager_cross_access_strict_404 PASSED [ 39%]
tests/test_core_concurrency_and_security.py::test_scope_isolation_after_reassignment_strict_404 PASSED [ 40%]
tests/test_core_concurrency_and_security.py::test_idempotency_caching_and_replay_without_side_effects PASSED [ 40%]
tests/test_core_concurrency_and_security.py::test_workflow_illegal_transition_rejections PASSED [ 41%]
tests/test_core_concurrency_and_security.py::test_formula_injection_escaping_in_reports PASSED [ 41%]
tests/test_core_concurrency_and_security.py::test_formula_injection_escaping_in_csv_export PASSED [ 42%]
tests/test_core_concurrency_and_security.py::test_file_security_path_traversal_null_bytes_and_oracle_defense PASSED [ 42%]
tests/test_core_concurrency_and_security.py::test_frontend_jwt_in_memory_audit PASSED [ 43%]
tests/test_core_concurrency_and_security.py::test_immutable_audit_log_temporal_integrity PASSED [ 44%]
tests/test_deliveries_models.py::test_models_metadata_and_declarative_schema PASSED [ 44%]
tests/test_deliveries_models.py::test_delivery_creation_defaults_and_persistence PASSED [ 45%]
tests/test_deliveries_models.py::test_delivery_and_delivery_items_persistence_with_all_kinds PASSED [ 45%]
tests/test_deliveries_models.py::test_delivery_lifecycle_and_updates PASSED [ 46%]
tests/test_deliveries_models.py::test_delivery_cascade_deletion PASSED   [ 47%]
tests/test_deliveries_models.py::test_delivery_foreign_key_constraints_enforced PASSED [ 47%]
tests/test_deliveries_models.py::test_delivery_and_item_nullability_constraints PASSED [ 48%]
tests/test_deliveries_models.py::test_engine_level_raw_sql_cascade_deletion PASSED [ 48%]
tests/test_deliveries_models.py::test_postgresql_dialect_ddl_generation PASSED [ 49%]
tests/test_deliveries_models.py::test_delivery_default_uuid_uniqueness PASSED [ 50%]
tests/test_deliveries_models.py::test_delivery_parent_referential_integrity_restrict PASSED [ 50%]
tests/test_deliveries_models.py::test_delivery_cas_revision_update_and_cancellation PASSED [ 51%]
tests/test_deliveries_models.py::test_delivery_core_insert_with_callable_defaults PASSED [ 51%]
tests/test_deliveries_models.py::test_delivery_complex_relational_joins_and_boundary_strings PASSED [ 52%]
tests/test_deliveries_models.py::test_delivery_isolated_parent_referential_integrity PASSED [ 52%]
tests/test_deliveries_models.py::test_child_item_deletion_leaves_delivery_intact PASSED [ 53%]
tests/test_deliveries_models.py::test_delivery_bulk_operations_and_temporal_ordering PASSED [ 54%]
tests/test_errors_c01.py::test_api_error_attributes PASSED               [ 54%]
tests/test_errors_c01.py::test_domain_error_envelope_c01_compliance PASSED [ 55%]
tests/test_errors_c01.py::test_request_validation_error_normalizes_loc PASSED [ 55%]
tests/test_errors_c01.py::test_unhandled_exception_returns_internal_error_500 PASSED [ 56%]
tests/test_errors_c01.py::test_validation_preserves_field_named_body PASSED [ 57%]
tests/test_errors_c01.py::test_empty_body_and_malformed_json PASSED      [ 57%]
tests/test_errors_c01.py::test_error_handlers_safe_with_mock_request PASSED [ 58%]
tests/test_errors_c01.py::test_query_path_header_validation_normalization PASSED [ 58%]
tests/test_errors_c01.py::test_api_error_headers_and_status_code_alias PASSED [ 59%]
tests/test_errors_c01.py::test_validation_error_with_none_or_missing_loc_fields PASSED [ 60%]
tests/test_errors_c01.py::test_domain_error_with_complex_types_in_details PASSED [ 60%]
tests/test_errors_c01.py::test_api_error_string_status_coercion PASSED   [ 61%]
tests/test_errors_c01.py::test_header_case_insensitive_deduplication PASSED [ 61%]
tests/test_errors_c01.py::test_validation_error_with_non_dict_error_objects PASSED [ 62%]
tests/test_import_wizard.py::test_csv_preview_dry_run_and_commit PASSED  [ 62%]
tests/test_import_wizard.py::test_xlsx_preview_and_error_handling PASSED [ 63%]
tests/test_import_wizard.py::test_import_existing_organization_updates_and_adds_contracts PASSED [ 64%]
tests/test_import_wizard.py::test_import_incompatible_program_product_flagged PASSED [ 64%]
tests/test_import_wizard.py::test_import_commit_multipart_form_data PASSED [ 65%]
tests/test_integrations.py::test_integrations_status_rbac PASSED         [ 65%]
tests/test_integrations.py::test_lms_sync_and_learning_metrics PASSED    [ 66%]
tests/test_integrations.py::test_sync_deduplication_and_idempotency PASSED [ 67%]
tests/test_website_sync_creates_pending_inbox_items PASSED [ 67%]
tests/test_inbox_pagination_and_filtering PASSED   [ 68%]
tests/test_integrations.py::test_reconcile_link_existing_with_interaction PASSED [ 68%]
tests/test_integrations.py::test_reconcile_create_new_organization PASSED [ 69%]
tests/test_integrations.py::test_reconcile_reject PASSED                 [ 70%]
tests/test_integrations.py::test_reconcile_conflict_already_processed PASSED [ 70%]
tests/test_integrations.py::test_reconcile_idempotency_key_replay PASSED [ 71%]
tests/test_integrations.py::test_learning_metrics_summary_aggregation PASSED [ 71%]
tests/test_integrations.py::test_scope_isolation_152_fz_on_created_interaction PASSED [ 72%]
tests/test_interaction_patch.py::test_patch_resolves_deadlock_d02 PASSED [ 72%]
tests/test_interaction_patch.py::test_patch_cas_conflict PASSED          [ 73%]
tests/test_interaction_patch.py::test_patch_invalid_subject_combination PASSED [ 74%]
tests/test_interaction_patch.py::test_patch_disallows_clearing_subject_in_late_states PASSED [ 74%]
tests/test_interaction_patch.py::test_patch_idempotency_and_event_sequence PASSED [ 75%]
tests/test_interaction_patch.py::test_patch_scope_isolation_manager PASSED [ 75%]
tests/test_interaction_patch.py::test_patch_scope_isolation_after_reassignment PASSED [ 76%]
tests/test_interaction_patch.py::test_patch_links_contact_contract_license PASSED [ 77%]
tests/test_interaction_patch.py::test_catalogs_returns_contracts_licenses_contacts PASSED [ 77%]
tests/test_interaction_patch.py::test_patch_disallows_modifying_closed_interaction PASSED [ 78%]
tests/test_reports_multiformat.py::test_snapshot_export_json_xlsx_pdf PASSED [ 78%]
tests/test_reports_multiformat.py::test_activity_report_and_exports PASSED [ 79%]
tests/test_reports_multiformat.py::test_created_report_and_exports PASSED [ 80%]
tests/test_reports_multiformat.py::test_unsupported_export_format_returns_422 PASSED [ 80%]
tests/test_reports_multiformat.py::test_activity_report_historical_owner_resolution_after_reassignment PASSED [ 81%]
tests/test_reports_multiformat.py::test_snapshot_zero_buckets_for_all_fifteen_states PASSED [ 81%]
tests/test_reports_multiformat.py::test_xlsx_formula_injection_defense PASSED [ 82%]
tests/test_workflow_migration.py::test_workflow_endpoint_versioning PASSED [ 82%]
tests/test_workflow_migration.py::test_workflow_migrate_rbac_manager_forbidden PASSED [ 83%]
tests/test_workflow_migration.py::test_workflow_migrate_rbac_supervisor_and_admin_allowed PASSED [ 84%]
tests/test_workflow_migration.py::test_workflow_migrate_reject_terminal_to_active PASSED [ 84%]
tests/test_workflow_migration.py::test_workflow_migrate_reject_invalid_versions_and_statuses PASSED [ 85%]
tests/test_workflow_migration.py::test_workflow_migrate_missing_idempotency_key PASSED [ 85%]
tests/test_workflow_migration.py::test_workflow_migrate_preview_calculation_and_collisions PASSED [ 86%]
tests/test_workflow_migration.py::test_workflow_migrate_preview_unmapped_status PASSED [ 87%]
tests/test_workflow_migration.py::test_workflow_migrate_commit_atomic_execution PASSED [ 87%]
tests/test_workflow_migration.py::test_workflow_migrate_preserves_history_comments_attachments PASSED [ 88%]
tests/test_workflow_migration.py::test_workflow_migrate_idempotency_replay_and_conflict PASSED [ 88%]
tests/test_v2_allowed_transitions_and_execution_after_migration PASSED [ 89%]
tests/test_workflow_migration.py::test_workflow_migrate_to_terminal_updates_closed_at PASSED [ 90%]
tests/test_working_slice.py::test_auth_requires_explicit_identity PASSED [ 90%]
tests/test_working_slice.py::test_demo_and_sqlite_cannot_be_accidentally_enabled_in_production PASSED [ 91%]
tests/test_working_slice.py::test_health_and_openapi_are_real PASSED     [ 91%]
tests/test_working_slice.py::test_manager_scope_applies_to_list_direct_detail_and_dashboard PASSED [ 92%]
tests/test_working_slice.py::test_technical_admin_has_no_implicit_business_scope PASSED [ 92%]
tests/test_working_slice.py::test_create_and_idempotent_replay_do_not_duplicate PASSED [ 93%]
tests/test_working_slice.py::test_creation_requires_key_and_does_not_allow_manager_to_assign_another_user PASSED [ 94%]
tests/test_working_slice.py::test_transition_revision_and_idempotency_are_enforced PASSED [ 94%]
tests/test_working_slice.py::test_forbidden_transition_cannot_skip_workflow PASSED [ 95%]
tests/test_working_slice.py::test_missing_program_and_product_prevent_late_stage PASSED [ 95%]
tests/test_working_slice.py::test_cancel_requires_comment_and_terminal_has_no_transition PASSED [ 96%]
tests/test_working_slice.py::test_comment_is_persisted_and_stale_comment_does_not_overwrite PASSED [ 97%]
tests/test_working_slice.py::test_reassignment_restricts_old_owner_and_keeps_historical_owner PASSED [ 97%]
tests/test_working_slice.py::test_idempotent_transition_replay_checks_current_access PASSED [ 98%]
tests/test_working_slice.py::test_snapshot_effective_and_received_boundaries PASSED [ 98%]
tests/test_working_slice.py::test_json_export_is_scoped_and_matches_report PASSED [ 99%]
tests/test_working_slice.py::test_filter_intersection_pagination_and_input_validation PASSED [100%]

=============================== warnings summary ===============================
.venv/lib64/python3.14/site-packages/fastapi/testclient.py:1
  /home/muhammad/Dev/HACKATHON/LCT/rost_crm/backend/.venv/lib64/python3.14/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

.venv/lib64/python3.14/site-packages/starlette/testclient.py:53
  /home/muhammad/Dev/HACKATHON/LCT/rost_crm/backend/.venv/lib64/python3.14/site-packages/starlette/testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
================== 170 passed, 2 warnings in 70.31s (0:01:10) ==================
```
