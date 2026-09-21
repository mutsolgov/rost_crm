## 2026-09-21T08:39:20Z

You are the SWE Light Orchestrator (`swe_2`) executing in `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/swe_2/`.

Your mission is to execute the user request recorded in `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/ORIGINAL_REQUEST.md` under the latest section:
"Добавление декларативных моделей Delivery и DeliveryItem в backend/app/models.py".

## Context and Requirements
1. **R1. Декларативная модель `Delivery` (таблица `deliveries`)**:
   - В `backend/app/models.py` объявить класс `Delivery(Base)`:
     - `__tablename__ = "deliveries"`
     - `id`: `Mapped[str]` (первичный ключ String(64), default=`new_id`)
     - `organization_id`: `Mapped[str]` (ForeignKey `organizations.id`, index=True)
     - `interaction_id`: `Mapped[str | None]` (ForeignKey `interactions.id`, index=True, nullable=True)
     - `status`: `Mapped[str]` (String(32), default="draft") — draft | sent | confirmed | cancelled
     - `channel`: `Mapped[str]` (String(40), default="email")
     - `sent_at`: `Mapped[datetime | None]` (DateTime(timezone=True), nullable=True)
     - `confirmed_at`: `Mapped[datetime | None]` (DateTime(timezone=True), nullable=True)
     - `recipient_contact_id`: `Mapped[str | None]` (ForeignKey `organization_contacts.id`, nullable=True)
     - `recorded_by`: `Mapped[str]` (ForeignKey `users.id`, index=True)
     - `comment`: `Mapped[str | None]` (Text, nullable=True)
     - `created_at`: `Mapped[datetime]` (DateTime(timezone=True), default=`utcnow`)
     - `revision`: `Mapped[int]` (Integer, default=1)

2. **R2. Декларативная модель `DeliveryItem` (таблица `delivery_items`)**:
   - В `backend/app/models.py` объявить класс `DeliveryItem(Base)`:
     - `__tablename__ = "delivery_items"`
     - `id`: `Mapped[str]` (первичный ключ String(64), default=`new_id`)
     - `delivery_id`: `Mapped[str]` (ForeignKey `deliveries.id`, ondelete="CASCADE", index=True)
     - `item_kind`: `Mapped[str]` (String(32)) — material | document | license
     - `title`: `Mapped[str]` (String(250))
     - `attachment_id`: `Mapped[str | None]` (ForeignKey `attachments.id`, nullable=True)
     - `license_id`: `Mapped[str | None]` (ForeignKey `licenses.id`, nullable=True)
     - `material_version`: `Mapped[str | None]` (String(120), nullable=True)
     - `created_at`: `Mapped[datetime]` (DateTime(timezone=True), default=`utcnow`)

3. **R3. Регрессионный контроль и целостность БД**:
   - Экспорт и доступность `Delivery` и `DeliveryItem` через `backend/app/models.py`.
   - Полное прохождение существующего тестового набора (`153 passed, 0 failed`).
   - Добавить модульные тесты в `backend/tests/test_deliveries_models.py` для проверки валидности создания и сохранения записей `Delivery` и `DeliveryItem`.
   - Отсутствие циклических импортов и ошибок создания таблиц SQLite/PostgreSQL.
   - Проверка импорта моделей: `backend/.venv/bin/python -c "from app.models import Delivery, DeliveryItem; print("Models imported successfully")"`
   - 4 оракула верификации:
     * `python3 docs/checks/verify_infra.py`
     * `python3 docs/checks/verify_workflow.py`
     * `python3 docs/checks/verify_reports.py`
     * `python3 docs/checks/verify_plan.py`
   - Strict Ponytail principles: лаконичность, отсутствие лишних связей, строгая типизация SQLAlchemy 2.0.

## Working Directory & Handoff
- Working directory: `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/swe_2/`
- Maintain `progress.md` and `BRIEFING.md` in your working directory.
- Dispatch your implementer (`teamwork_preview_implementer` with flash) and reviewer (`teamwork_preview_reviewer` with flash) as specified in SWE Light loop.
- Deliver `handoff.md` and report back when finished.
