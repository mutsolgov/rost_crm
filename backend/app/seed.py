from __future__ import annotations

import argparse
from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .db import Base, get_engine
from .models import (
    AccessPolicyState,
    Contract,
    Direction,
    Interaction,
    InteractionEvent,
    License,
    Organization,
    OrganizationAccess,
    OrganizationContact,
    Product,
    Program,
    ProgramProduct,
    Team,
    User,
    utcnow,
)
from .services import interaction_dict


USERS = [
    {"id": "manager-a", "keycloak_subject": "11111111-1111-4111-8111-111111111111", "name": "Анна Смирнова", "role": "manager", "team_id": "north"},
    {"id": "manager-b", "keycloak_subject": "22222222-2222-4222-8222-222222222222", "name": "Михаил Волков", "role": "manager", "team_id": "north"},
    {"id": "supervisor", "keycloak_subject": "33333333-3333-4333-8333-333333333333", "name": "Елена Соколова", "role": "supervisor", "team_id": "north"},
    {"id": "administrator", "keycloak_subject": "44444444-4444-4444-8444-444444444444", "name": "Администратор Демонстрационный", "role": "administrator", "team_id": None, "permissions": ["workflow.global_migrate"]},
]


def _get_or_add(db: Session, model, ident: str, **values):
    item = db.get(model, ident)
    if item is None:
        item = model(id=ident, **values)
        db.add(item)
    return item


def seed_database(db: Session) -> None:
    teams = {
        "north": "Команда Север",
        "south": "Команда Юг",
        "team-alpha": "Команда Альфа",
        "team-beta": "Команда Бета",
    }
    for ident, name in teams.items():
        _get_or_add(db, Team, ident, name=name)
    db.flush()

    directions = {
        "direction-digital": "Цифровые технологии",
        "direction-engineering": "Инженерные системы",
    }
    for ident, name in directions.items():
        _get_or_add(db, Direction, ident, name=name)
    programs = {
        "program-devops": ("DevOps и облачные технологии", "direction-digital"),
        "program-qa": ("Инженерия качества ПО", "direction-digital"),
    }
    for ident, (name, direction_id) in programs.items():
        _get_or_add(db, Program, ident, name=name, direction_id=direction_id)
    products = {
        "product-cloud": ("Облачная платформа", "Ростелеком"),
        "product-test": ("Среда тестирования", "Ростелеком"),
    }
    for ident, (name, vendor) in products.items():
        _get_or_add(db, Product, ident, name=name, vendor=vendor)
    db.flush()

    for program_id, product_id in (("program-devops", "product-cloud"), ("program-qa", "product-test")):
        if db.get(ProgramProduct, (program_id, product_id)) is None:
            db.add(ProgramProduct(program_id=program_id, product_id=product_id))

    organizations = {
        "org-1": ("Московский технический университет", "university"),
        "org-2": ("Северный университет прикладных наук", "university"),
        "org-3": ("Колледж цифровых профессий", "school"),
    }
    for ident, (name, type_) in organizations.items():
        _get_or_add(db, Organization, ident, name=name, type=type_)
    for data in USERS:
        user = db.get(User, data["id"])
        perms = data.get("permissions", [])
        user_kwargs = {k: v for k, v in data.items() if k != "permissions"}
        if user is None:
            db.add(User(**user_kwargs, permissions=perms))
        else:
            for key, value in user_kwargs.items():
                setattr(user, key, value)
            user.permissions = perms
            user.active = True
    db.flush()

    grants = {
        ("manager-a", "org-1"): (True, False),
        ("manager-b", "org-2"): (True, False),
        ("supervisor", "org-1"): (True, True),
        ("supervisor", "org-2"): (True, True),
        ("supervisor", "org-3"): (True, True),
    }
    for (user_id, organization_id), (can_create, read_all) in grants.items():
        grant = db.get(OrganizationAccess, (user_id, organization_id))
        if grant is None:
            db.add(OrganizationAccess(user_id=user_id, organization_id=organization_id, can_create=can_create, read_all=read_all))
        else:
            grant.can_create, grant.read_all = can_create, read_all
    db.flush()

    contacts = [
        ("contact-1", "org-1", "Иван Петров", "Декан факультета ИТ", "petrov@org1.ru", "+7-495-100-01", True),
        ("contact-2", "org-1", "Ольга Сидорова", "Зав. кафедрой ПО", "sidorova@org1.ru", "+7-495-100-02", True),
        ("contact-3", "org-2", "Сергей Кузнецов", "Проректор по цифровизации", "kuznetsov@org2.ru", "+7-812-200-01", True),
        ("contact-4", "org-3", "Дмитрий Морозов", "Руководитель ИТ-отделения", "morozov@org3.ru", "+7-495-300-01", True),
    ]
    for ident, org_id, full_name, pos, email, phone, active in contacts:
        _get_or_add(db, OrganizationContact, ident, organization_id=org_id, full_name=full_name,
                    position=pos, email=email, phone=phone, active=active)

    now = utcnow()
    contracts = [
        ("contract-1", "org-1", "ДОГ-2026/01", now - timedelta(days=60), "active", now - timedelta(days=60)),
        ("contract-2", "org-2", "ДОГ-2026/02", now - timedelta(days=45), "active", now - timedelta(days=45)),
        ("contract-3", "org-3", "ДОГ-2026/03", now - timedelta(days=30), "active", now - timedelta(days=30)),
    ]
    for ident, org_id, num, signed, status, created in contracts:
        _get_or_add(db, Contract, ident, organization_id=org_id, number=num, signed_on=signed,
                    status=status, created_at=created)

    licenses = [
        ("license-1", "org-1", "product-cloud", "contract-1", now - timedelta(days=50), 1, "transferred", now - timedelta(days=50)),
        ("license-2", "org-1", "product-test", "contract-1", now - timedelta(days=40), 2, "pending", now - timedelta(days=40)),
        ("license-3", "org-2", "product-cloud", "contract-2", now - timedelta(days=35), 1, "transferred", now - timedelta(days=35)),
        ("license-4", "org-2", "product-test", "contract-2", now - timedelta(days=20), 1, "pending", now - timedelta(days=20)),
    ]
    for ident, org_id, prod_id, cont_id, signed, term, transfer_status, created in licenses:
        _get_or_add(db, License, ident, organization_id=org_id, product_id=prod_id,
                    contract_id=cont_id, signed_on=signed, term_years=term,
                    transfer_status=transfer_status, created_at=created)
    db.flush()

    seeded = [
        ("ix-1", "Облачная лаборатория для первокурсников", "org-1", "program-devops", "product-cloud", "Весна 2026", "manager-a", "needs_clarification", "contact-1", None, None),
        ("ix-2", "Курс автоматизации тестирования", "org-1", "program-qa", "product-test", "Осень 2026", "manager-a", "meeting", "contact-2", None, None),
        ("ix-3", "Обновление программы DevOps", "org-1", "program-devops", "product-cloud", "2026/27", "manager-a", "document_exchange", "contact-1", "contract-1", None),
        ("ix-4", "Пилот облачной среды", "org-2", "program-devops", "product-cloud", "Весна 2026", "manager-b", "materials_transfer", "contact-3", "contract-2", "license-3"),
        ("ix-5", "Лаборатории контроля качества", "org-2", "program-qa", "product-test", "Осень 2026", "manager-b", "teacher_training", "contact-3", "contract-2", "license-4"),
        ("ix-6", "Программа цифровой практики", "org-3", "program-qa", "product-test", "2026/27", "manager-b", "classes", "contact-4", "contract-3", None),
    ]
    for index, (ident, title, organization_id, program_id, product_id, cycle, owner_id, state, contact_id, contract_id, license_id) in enumerate(seeded):
        if db.get(Interaction, ident) is not None:
            continue
        owner = db.get(User, owner_id)
        created = now - timedelta(days=28 - index * 3)
        item = Interaction(
            id=ident,
            title=title,
            organization_id=organization_id,
            program_id=program_id,
            product_id=product_id,
            contact_id=contact_id,
            contract_id=contract_id,
            license_id=license_id,
            cycle_label=cycle,
            owner_id=owner_id,
            team_id=owner.team_id,
            state=state,
            workflow_version=1,
            revision=1,
            visit_id=f"visit-{ident}",
            created_at=created,
            updated_at=created,
        )
        db.add(item)
        db.flush()
        payload = {"snapshot": interaction_dict(db, item), "visit_id": item.visit_id, "to_state": state, "owner_id": owner_id}
        db.add(InteractionEvent(
            interaction_id=item.id,
            type="created",
            effective_at=created,
            received_at=created,
            sequence=1,
            actor_id=owner_id,
            actor_name=owner.name,
            payload=payload,
        ))

    state = db.get(AccessPolicyState, 1)
    if state is None:
        db.add(AccessPolicyState(singleton_id=1, epoch=1, updated_at=utcnow()))
    else:
        state.epoch = 1
        state.updated_at = utcnow()
    db.flush()

    # R1: Domain purity - purge any legacy or mistaken learner records from User table
    learner_ids = ("cherepanona-s", "max_crich", "grigorev355", "osipenko833484", "mp_ivanov")
    learner_emails = (
        "cherepanona.s@test.ru",
        "max_crich@mail.ru",
        "grigorev355@gmail.com",
        "osipenko833484@mail.ru",
        "mp_ivanov@mail.ru",
    )
    for u in db.scalars(select(User).where(or_(User.id.in_(learner_ids), User.keycloak_subject.in_(learner_emails)))).all():
        db.delete(u)
    db.flush()


def ensure_schema_columns(engine) -> None:
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    with engine.begin() as conn:
        if inspector.has_table("organizations"):
            cols = {c["name"] for c in inspector.get_columns("organizations")}
            if "owner_id" not in cols:
                conn.execute(text("ALTER TABLE organizations ADD COLUMN owner_id VARCHAR(64) NULL"))
                try:
                    conn.execute(text("CREATE INDEX ix_organizations_owner_id ON organizations (owner_id)"))
                except Exception:
                    pass
        if inspector.has_table("learning_metrics"):
            cols = {c["name"] for c in inspector.get_columns("learning_metrics")}
            if "last_applied_revision" not in cols:
                conn.execute(text("ALTER TABLE learning_metrics ADD COLUMN last_applied_revision VARCHAR(64) NULL"))
        if inspector.has_table("workflow_versions"):
            cols = {c["name"] for c in inspector.get_columns("workflow_versions")}
            if "definition" not in cols:
                conn.execute(text("ALTER TABLE workflow_versions ADD COLUMN definition JSON NULL"))
            if "is_published" not in cols:
                conn.execute(text("ALTER TABLE workflow_versions ADD COLUMN is_published BOOLEAN NOT NULL DEFAULT FALSE"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the schema and/or synthetic CRM records.")
    parser.add_argument("--init-db", action="store_true", help="Create database tables.")
    parser.add_argument("--seed-demo", action="store_true", help="Add synthetic users, catalogs and interactions.")
    args = parser.parse_args()
    if not args.init_db and not args.seed_demo:
        parser.error("укажите --init-db или --seed-demo")
    engine = get_engine()
    if args.init_db or args.seed_demo:
        Base.metadata.create_all(engine)
        ensure_schema_columns(engine)
    if args.seed_demo:
        with Session(engine) as db:
            seed_database(db)
            db.commit()


if __name__ == "__main__":
    main()

