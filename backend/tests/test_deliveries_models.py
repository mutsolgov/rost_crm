from datetime import datetime, timezone

import pytest
from sqlalchemy import insert, select, text, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateTable

from app.models import (
    Attachment,
    Delivery,
    DeliveryItem,
    Interaction,
    License,
    Organization,
    OrganizationContact,
    User,
)


def test_models_metadata_and_declarative_schema():
    """Verify that Delivery and DeliveryItem declare correct tables, columns, indexes, and FKs."""
    d_table = Delivery.__table__
    di_table = DeliveryItem.__table__

    assert d_table.name == "deliveries"
    assert di_table.name == "delivery_items"

    # Delivery columns
    col_names = {c.name for c in d_table.columns}
    expected_d_cols = {
        "id",
        "organization_id",
        "interaction_id",
        "status",
        "channel",
        "sent_at",
        "confirmed_at",
        "recipient_contact_id",
        "recorded_by",
        "comment",
        "created_at",
        "revision",
    }
    assert expected_d_cols.issubset(col_names)

    # Check Delivery primary key and column types
    assert d_table.columns["id"].primary_key is True
    assert d_table.columns["id"].type.length == 64
    assert d_table.columns["organization_id"].nullable is False
    assert d_table.columns["interaction_id"].nullable is True
    assert d_table.columns["status"].nullable is False
    assert d_table.columns["status"].type.length == 32
    assert d_table.columns["channel"].nullable is False
    assert d_table.columns["channel"].type.length == 40
    assert d_table.columns["sent_at"].nullable is True
    assert d_table.columns["confirmed_at"].nullable is True
    assert d_table.columns["recipient_contact_id"].nullable is True
    assert d_table.columns["recorded_by"].nullable is False
    assert d_table.columns["comment"].nullable is True
    assert d_table.columns["created_at"].nullable is False
    assert d_table.columns["revision"].nullable is False

    # Check Delivery foreign keys
    d_fks = {fk.target_fullname: fk for fk in d_table.foreign_keys}
    assert "organizations.id" in d_fks
    assert "interactions.id" in d_fks
    assert "organization_contacts.id" in d_fks
    assert "users.id" in d_fks

    # Check DeliveryItem columns
    di_col_names = {c.name for c in di_table.columns}
    expected_di_cols = {
        "id",
        "delivery_id",
        "item_kind",
        "title",
        "attachment_id",
        "license_id",
        "material_version",
        "created_at",
    }
    assert expected_di_cols.issubset(di_col_names)

    assert di_table.columns["id"].primary_key is True
    assert di_table.columns["id"].type.length == 64
    assert di_table.columns["delivery_id"].nullable is False
    assert di_table.columns["item_kind"].nullable is False
    assert di_table.columns["item_kind"].type.length == 32
    assert di_table.columns["title"].nullable is False
    assert di_table.columns["title"].type.length == 250
    assert di_table.columns["attachment_id"].nullable is True
    assert di_table.columns["license_id"].nullable is True
    assert di_table.columns["material_version"].nullable is True
    assert di_table.columns["material_version"].type.length == 120
    assert di_table.columns["created_at"].nullable is False

    # Check foreign keys and cascade on DeliveryItem
    fks = {fk.target_fullname: fk for fk in di_table.foreign_keys}
    assert "deliveries.id" in fks
    assert fks["deliveries.id"].ondelete == "CASCADE"
    assert "attachments.id" in fks
    assert "licenses.id" in fks

    # Check index flags
    assert d_table.columns["organization_id"].index is True
    assert d_table.columns["interaction_id"].index is True
    assert d_table.columns["recorded_by"].index is True
    assert di_table.columns["delivery_id"].index is True


def test_delivery_creation_defaults_and_persistence(app):
    """Verify creating a Delivery record with defaults."""
    with app.state.session_factory() as session:
        delivery = Delivery(
            organization_id="org-1",
            recorded_by="manager-a",
        )
        session.add(delivery)
        session.commit()
        delivery_id = delivery.id

    with app.state.session_factory() as session:
        loaded = session.get(Delivery, delivery_id)
        assert loaded is not None
        assert loaded.organization_id == "org-1"
        assert loaded.recorded_by == "manager-a"
        assert loaded.status == "draft"
        assert loaded.channel == "email"
        assert loaded.revision == 1
        assert loaded.interaction_id is None
        assert loaded.recipient_contact_id is None
        assert loaded.sent_at is None
        assert loaded.confirmed_at is None
        assert loaded.comment is None
        assert isinstance(loaded.created_at, datetime)


def test_delivery_and_delivery_items_persistence_with_all_kinds(app):
    """Verify persisting Delivery with items of all kinds (material, document, license)."""
    with app.state.session_factory() as session:
        # Create attachment to test attachment_id reference
        att = Attachment(
            id="att-test-deliv",
            interaction_id="ix-4",
            visit_id="visit-ix-4",
            file_name="guide.pdf",
            file_path="/storage/guide.pdf",
            file_size=1024,
            content_type="application/pdf",
            checksum="abc12345",
            uploaded_by="manager-b",
        )
        session.add(att)

        delivery = Delivery(
            organization_id="org-2",
            interaction_id="ix-4",
            recipient_contact_id="contact-3",
            recorded_by="manager-b",
            status="sent",
            channel="email",
            sent_at=datetime.now(timezone.utc),
            comment="Передача материалов и документов по пилоту",
        )
        session.add(delivery)
        session.flush()

        item_mat = DeliveryItem(
            delivery_id=delivery.id,
            item_kind="material",
            title="Методические материалы курса DevOps",
            material_version="v1.2",
            attachment_id=att.id,
        )
        item_doc = DeliveryItem(
            delivery_id=delivery.id,
            item_kind="document",
            title="Акт передачи неисключительных прав",
        )
        item_lic = DeliveryItem(
            delivery_id=delivery.id,
            item_kind="license",
            title="Электронная лицензия на платформу",
            license_id="license-3",
        )
        session.add_all([item_mat, item_doc, item_lic])
        session.commit()

        d_id = delivery.id
        mat_id = item_mat.id
        doc_id = item_doc.id
        lic_id = item_lic.id

    with app.state.session_factory() as session:
        loaded_d = session.get(Delivery, d_id)
        assert loaded_d is not None
        assert loaded_d.status == "sent"
        assert loaded_d.interaction_id == "ix-4"
        assert loaded_d.recipient_contact_id == "contact-3"
        assert loaded_d.sent_at is not None

        items = list(
            session.scalars(
                select(DeliveryItem).where(DeliveryItem.delivery_id == d_id)
            )
        )
        assert len(items) == 3

        loaded_mat = session.get(DeliveryItem, mat_id)
        assert loaded_mat.item_kind == "material"
        assert loaded_mat.title == "Методические материалы курса DevOps"
        assert loaded_mat.material_version == "v1.2"
        assert loaded_mat.attachment_id == "att-test-deliv"
        assert isinstance(loaded_mat.created_at, datetime)

        loaded_doc = session.get(DeliveryItem, doc_id)
        assert loaded_doc.item_kind == "document"
        assert loaded_doc.attachment_id is None
        assert loaded_doc.license_id is None

        loaded_lic = session.get(DeliveryItem, lic_id)
        assert loaded_lic.item_kind == "license"
        assert loaded_lic.license_id == "license-3"


def test_delivery_lifecycle_and_updates(app):
    """Verify delivery status transitions (draft -> sent -> confirmed)."""
    with app.state.session_factory() as session:
        delivery = Delivery(
            organization_id="org-1",
            recorded_by="manager-a",
        )
        session.add(delivery)
        session.commit()
        d_id = delivery.id

    # Update to sent
    sent_time = datetime.now(timezone.utc)
    with app.state.session_factory() as session:
        d = session.get(Delivery, d_id)
        d.status = "sent"
        d.sent_at = sent_time
        d.revision += 1
        session.commit()

    # Update to confirmed
    conf_time = datetime.now(timezone.utc)
    with app.state.session_factory() as session:
        d = session.get(Delivery, d_id)
        assert d.status == "sent"
        assert d.revision == 2
        d.status = "confirmed"
        d.confirmed_at = conf_time
        d.revision += 1
        session.commit()

    with app.state.session_factory() as session:
        d = session.get(Delivery, d_id)
        assert d.status == "confirmed"
        assert d.revision == 3
        assert d.sent_at is not None
        assert d.confirmed_at is not None


def test_delivery_cascade_deletion(app):
    """Verify that deleting a Delivery record cascades to its DeliveryItems."""
    with app.state.session_factory() as session:
        delivery = Delivery(
            organization_id="org-1",
            recorded_by="manager-a",
        )
        session.add(delivery)
        session.flush()

        item1 = DeliveryItem(
            delivery_id=delivery.id,
            item_kind="document",
            title="Документ 1",
        )
        item2 = DeliveryItem(
            delivery_id=delivery.id,
            item_kind="material",
            title="Материал 1",
        )
        session.add_all([item1, item2])
        session.commit()

        d_id = delivery.id
        item1_id = item1.id
        item2_id = item2.id

    # Verify items exist
    with app.state.session_factory() as session:
        assert session.get(DeliveryItem, item1_id) is not None
        assert session.get(DeliveryItem, item2_id) is not None

        # Delete delivery
        d = session.get(Delivery, d_id)
        session.delete(d)
        session.commit()

    # Verify items were cascade deleted
    with app.state.session_factory() as session:
        assert session.get(Delivery, d_id) is None
        assert session.get(DeliveryItem, item1_id) is None
        assert session.get(DeliveryItem, item2_id) is None


def test_delivery_foreign_key_constraints_enforced(app):
    """Adversarial check: SQLite foreign key enforcement triggers on invalid references."""
    with app.state.session_factory() as session:
        # Invalid organization_id
        with pytest.raises(IntegrityError):
            d_bad_org = Delivery(organization_id="non-existent-org", recorded_by="manager-a")
            session.add(d_bad_org)
            session.commit()
        session.rollback()

        # Invalid recorded_by
        with pytest.raises(IntegrityError):
            d_bad_user = Delivery(organization_id="org-1", recorded_by="non-existent-user")
            session.add(d_bad_user)
            session.commit()
        session.rollback()

        # Invalid interaction_id
        with pytest.raises(IntegrityError):
            d_bad_ix = Delivery(
                organization_id="org-1",
                recorded_by="manager-a",
                interaction_id="non-existent-interaction",
            )
            session.add(d_bad_ix)
            session.commit()
        session.rollback()

        # Invalid recipient_contact_id
        with pytest.raises(IntegrityError):
            d_bad_contact = Delivery(
                organization_id="org-1",
                recorded_by="manager-a",
                recipient_contact_id="non-existent-contact",
            )
            session.add(d_bad_contact)
            session.commit()
        session.rollback()

        # Create a valid delivery to test item FK constraints
        valid_d = Delivery(organization_id="org-1", recorded_by="manager-a")
        session.add(valid_d)
        session.commit()
        valid_d_id = valid_d.id

        # Invalid delivery_id on item
        with pytest.raises(IntegrityError):
            item_bad_deliv = DeliveryItem(
                delivery_id="non-existent-delivery",
                item_kind="document",
                title="Invalid Delivery FK",
            )
            session.add(item_bad_deliv)
            session.commit()
        session.rollback()

        # Invalid attachment_id on item
        with pytest.raises(IntegrityError):
            item_bad_att = DeliveryItem(
                delivery_id=valid_d_id,
                item_kind="material",
                title="Invalid Attachment FK",
                attachment_id="non-existent-att",
            )
            session.add(item_bad_att)
            session.commit()
        session.rollback()

        # Invalid license_id on item
        with pytest.raises(IntegrityError):
            item_bad_lic = DeliveryItem(
                delivery_id=valid_d_id,
                item_kind="license",
                title="Invalid License FK",
                license_id="non-existent-license",
            )
            session.add(item_bad_lic)
            session.commit()
        session.rollback()


def test_delivery_and_item_nullability_constraints(app):
    """Adversarial check: non-nullable columns reject None upon persistence."""
    with app.state.session_factory() as session:
        with pytest.raises(IntegrityError):
            d = Delivery(organization_id=None, recorded_by="manager-a")
            session.add(d)
            session.commit()
        session.rollback()

        with pytest.raises(IntegrityError):
            d = Delivery(organization_id="org-1", recorded_by=None)
            session.add(d)
            session.commit()
        session.rollback()

        valid_d = Delivery(organization_id="org-1", recorded_by="manager-a")
        session.add(valid_d)
        session.commit()
        v_id = valid_d.id

        with pytest.raises(IntegrityError):
            di = DeliveryItem(delivery_id=None, item_kind="material", title="Test")
            session.add(di)
            session.commit()
        session.rollback()

        with pytest.raises(IntegrityError):
            di = DeliveryItem(delivery_id=v_id, item_kind=None, title="Test")
            session.add(di)
            session.commit()
        session.rollback()

        with pytest.raises(IntegrityError):
            di = DeliveryItem(delivery_id=v_id, item_kind="material", title=None)
            session.add(di)
            session.commit()
        session.rollback()


def test_engine_level_raw_sql_cascade_deletion(app):
    """Verify that ON DELETE CASCADE works directly in SQLite via raw SQL DELETE."""
    with app.state.session_factory() as session:
        deliv = Delivery(organization_id="org-1", recorded_by="manager-a")
        session.add(deliv)
        session.flush()

        item1 = DeliveryItem(delivery_id=deliv.id, item_kind="material", title="Item 1")
        item2 = DeliveryItem(delivery_id=deliv.id, item_kind="license", title="Item 2")
        session.add_all([item1, item2])
        session.commit()
        d_id = deliv.id
        i1_id = item1.id
        i2_id = item2.id

    # In a clean session, execute raw SQL DELETE without loading items into ORM identity map
    with app.state.session_factory() as session:
        session.execute(text("DELETE FROM deliveries WHERE id = :id"), {"id": d_id})
        session.commit()

    with app.state.session_factory() as session:
        assert session.get(Delivery, d_id) is None
        assert session.get(DeliveryItem, i1_id) is None
        assert session.get(DeliveryItem, i2_id) is None


def test_postgresql_dialect_ddl_generation():
    """Verify that SQLAlchemy generates valid PostgreSQL DDL with correct types and constraints."""
    d_ddl = str(CreateTable(Delivery.__table__).compile(dialect=postgresql.dialect()))
    di_ddl = str(CreateTable(DeliveryItem.__table__).compile(dialect=postgresql.dialect()))

    # Delivery assertions
    assert "CREATE TABLE deliveries" in d_ddl
    assert "VARCHAR(64)" in d_ddl
    assert "VARCHAR(32)" in d_ddl
    assert "VARCHAR(40)" in d_ddl
    assert "TIMESTAMP WITH TIME ZONE" in d_ddl
    assert "FOREIGN KEY(organization_id) REFERENCES organizations (id)" in d_ddl
    assert "FOREIGN KEY(interaction_id) REFERENCES interactions (id)" in d_ddl
    assert "FOREIGN KEY(recipient_contact_id) REFERENCES organization_contacts (id)" in d_ddl
    assert "FOREIGN KEY(recorded_by) REFERENCES users (id)" in d_ddl

    # DeliveryItem assertions
    assert "CREATE TABLE delivery_items" in di_ddl
    assert "VARCHAR(250)" in di_ddl
    assert "VARCHAR(120)" in di_ddl
    assert "FOREIGN KEY(delivery_id) REFERENCES deliveries (id) ON DELETE CASCADE" in di_ddl
    assert "FOREIGN KEY(attachment_id) REFERENCES attachments (id)" in di_ddl
    assert "FOREIGN KEY(license_id) REFERENCES licenses (id)" in di_ddl


def test_delivery_default_uuid_uniqueness(app):
    """Verify that multiple deliveries created without explicit ID receive distinct UUID4s."""
    with app.state.session_factory() as session:
        d1 = Delivery(organization_id="org-1", recorded_by="manager-a")
        d2 = Delivery(organization_id="org-1", recorded_by="manager-a")
        session.add_all([d1, d2])
        session.commit()

        assert d1.id != d2.id
        assert len(d1.id) == 36
        assert len(d2.id) == 36
        assert d1.status == "draft"
        assert d2.status == "draft"
        assert d1.channel == "email"
        assert d2.channel == "email"
        assert d1.revision == 1
        assert d2.revision == 1


def test_delivery_parent_referential_integrity_restrict(app):
    """Adversarial check: deleting parent entities referenced by Delivery/DeliveryItem fails with IntegrityError."""
    with app.state.session_factory() as session:
        # Create an attachment
        att = Attachment(
            id="att-restrict-test",
            interaction_id="ix-4",
            visit_id="visit-ix-4",
            file_name="test.pdf",
            file_path="/test.pdf",
            file_size=500,
            content_type="application/pdf",
            checksum="chk123",
            uploaded_by="manager-a",
        )
        session.add(att)

        delivery = Delivery(
            organization_id="org-2",
            interaction_id="ix-4",
            recorded_by="manager-a",
        )
        session.add(delivery)
        session.flush()

        item = DeliveryItem(
            delivery_id=delivery.id,
            item_kind="material",
            title="Material with Attachment",
            attachment_id=att.id,
            license_id="license-3",
        )
        session.add(item)
        session.commit()

    # Attempting to delete the parent interaction (referenced by Delivery) must violate FK constraint
    with app.state.session_factory() as session:
        ix = session.get(Interaction, "ix-4")
        session.delete(ix)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    # Attempting to delete the parent attachment (referenced by DeliveryItem) must violate FK constraint
    with app.state.session_factory() as session:
        att = session.get(Attachment, "att-restrict-test")
        session.delete(att)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    # Attempting to delete the parent license (referenced by DeliveryItem) must violate FK constraint
    with app.state.session_factory() as session:
        lic = session.get(License, "license-3")
        session.delete(lic)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_delivery_cas_revision_update_and_cancellation(app):
    """Verify CAS revision check semantics and transition to 'cancelled' status."""
    with app.state.session_factory() as session:
        delivery = Delivery(
            organization_id="org-1",
            recorded_by="manager-a",
            status="draft",
        )
        session.add(delivery)
        session.commit()
        d_id = delivery.id

    with app.state.session_factory() as session:
        # CAS update with matching expected revision (1 -> 2) cancelling the delivery
        result = session.execute(
            update(Delivery)
            .where(Delivery.id == d_id, Delivery.revision == 1)
            .values(status="cancelled", revision=2)
        )
        session.commit()
        assert result.rowcount == 1

    with app.state.session_factory() as session:
        # Stale CAS update attempting revision 1 must affect 0 rows
        stale_result = session.execute(
            update(Delivery)
            .where(Delivery.id == d_id, Delivery.revision == 1)
            .values(status="sent", revision=3)
        )
        session.commit()
        assert stale_result.rowcount == 0

        # Verify delivery is cancelled and at revision 2
        d = session.get(Delivery, d_id)
        assert d.status == "cancelled"
        assert d.revision == 2


def test_delivery_core_insert_with_callable_defaults(app):
    """Verify that Core insert() evaluates callable defaults (new_id, utcnow) and column defaults."""
    with app.state.session_factory() as session:
        res = session.execute(
            insert(Delivery).values(
                organization_id="org-1",
                recorded_by="manager-a",
            )
        )
        session.commit()
        inserted_id = res.inserted_primary_key[0]

    with app.state.session_factory() as session:
        loaded = session.get(Delivery, inserted_id)
        assert loaded is not None
        assert len(loaded.id) == 36
        assert loaded.status == "draft"
        assert loaded.channel == "email"
        assert loaded.revision == 1
        assert isinstance(loaded.created_at, datetime)

        # Core insert of child item
        res_item = session.execute(
            insert(DeliveryItem).values(
                delivery_id=loaded.id,
                item_kind="document",
                title="Core Inserted Document",
            )
        )
        session.commit()
        item_id = res_item.inserted_primary_key[0]

    with app.state.session_factory() as session:
        loaded_item = session.get(DeliveryItem, item_id)
        assert loaded_item is not None
        assert len(loaded_item.id) == 36
        assert loaded_item.title == "Core Inserted Document"
        assert isinstance(loaded_item.created_at, datetime)


def test_delivery_complex_relational_joins_and_boundary_strings(app):
    """Verify maximum boundary string lengths and relational joins across 7 related tables."""
    max_title = "Т" * 250
    max_version = "v" * 120
    large_comment = "Комментарий " * 300

    with app.state.session_factory() as session:
        att = Attachment(
            id="att-boundary-test",
            interaction_id="ix-4",
            visit_id="visit-ix-4",
            file_name="boundary.docx",
            file_path="/storage/boundary.docx",
            file_size=2048,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            checksum="sha256-boundary-hash",
            uploaded_by="manager-b",
        )
        session.add(att)

        delivery = Delivery(
            organization_id="org-2",
            interaction_id="ix-4",
            recipient_contact_id="contact-3",
            recorded_by="manager-b",
            status="confirmed",
            channel="custom_courier_service",
            sent_at=datetime.now(timezone.utc),
            confirmed_at=datetime.now(timezone.utc),
            comment=large_comment,
            revision=5,
        )
        session.add(delivery)
        session.flush()

        item = DeliveryItem(
            delivery_id=delivery.id,
            item_kind="material",
            title=max_title,
            material_version=max_version,
            attachment_id=att.id,
            license_id="license-3",
        )
        session.add(item)
        session.commit()
        d_id = delivery.id
        item_id = item.id

    with app.state.session_factory() as session:
        # Multi-table join query
        stmt = (
            select(
                Delivery.id,
                Delivery.status,
                Delivery.channel,
                Delivery.comment,
                Organization.name.label("org_name"),
                User.name.label("user_name"),
                Interaction.title.label("ix_title"),
                OrganizationContact.full_name.label("contact_name"),
                DeliveryItem.title.label("item_title"),
                DeliveryItem.material_version,
                Attachment.file_name,
                License.transfer_status,
            )
            .join(Organization, Delivery.organization_id == Organization.id)
            .join(User, Delivery.recorded_by == User.id)
            .outerjoin(Interaction, Delivery.interaction_id == Interaction.id)
            .outerjoin(OrganizationContact, Delivery.recipient_contact_id == OrganizationContact.id)
            .join(DeliveryItem, Delivery.id == DeliveryItem.delivery_id)
            .outerjoin(Attachment, DeliveryItem.attachment_id == Attachment.id)
            .outerjoin(License, DeliveryItem.license_id == License.id)
            .where(Delivery.id == d_id)
        )
        row = session.execute(stmt).one()

        assert row.id == d_id
        assert row.status == "confirmed"
        assert row.channel == "custom_courier_service"
        assert row.comment == large_comment
        assert row.org_name == "Северный университет прикладных наук"
        assert row.user_name == "Михаил Волков"
        assert row.ix_title == "Пилот облачной среды"
        assert row.contact_name == "Сергей Кузнецов"
        assert row.item_title == max_title
        assert len(row.item_title) == 250
        assert row.material_version == max_version
        assert len(row.material_version) == 120
        assert row.file_name == "boundary.docx"
        assert row.transfer_status == "transferred"


def test_delivery_isolated_parent_referential_integrity(app):
    """Adversarial check: Delivery and DeliveryItem FKs alone block deletion of their specific parents."""
    with app.state.session_factory() as session:
        # Create unique isolated organization, user, contact, and interaction
        test_org = Organization(id="org-isolated", name="Изолированная Организация", type="school")
        test_user = User(id="user-isolated", keycloak_subject="sub-isolated", name="Изолированный Пользователь", role="manager")
        session.add_all([test_org, test_user])
        session.flush()

        test_contact = OrganizationContact(
            id="contact-isolated",
            organization_id="org-isolated",
            full_name="Изолированный Контакт",
            position="Директор",
        )
        test_ix = Interaction(
            id="ix-isolated",
            title="Изолированное Взаимодействие",
            organization_id="org-isolated",
            cycle_label="2026",
            owner_id="user-isolated",
            state="draft",
        )
        session.add_all([test_contact, test_ix])
        session.flush()

        # Create delivery referencing these isolated entities
        deliv = Delivery(
            id="deliv-isolated",
            organization_id="org-isolated",
            interaction_id="ix-isolated",
            recipient_contact_id="contact-isolated",
            recorded_by="user-isolated",
        )
        session.add(deliv)
        session.commit()

    # Attempting to delete the isolated contact (referenced ONLY by Delivery.recipient_contact_id)
    with app.state.session_factory() as session:
        contact = session.get(OrganizationContact, "contact-isolated")
        session.delete(contact)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    # Attempting to delete the isolated interaction (referenced ONLY by Delivery.interaction_id)
    with app.state.session_factory() as session:
        ix = session.get(Interaction, "ix-isolated")
        session.delete(ix)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    # Attempting to delete the isolated user (referenced by Delivery.recorded_by and Interaction.owner_id)
    with app.state.session_factory() as session:
        u = session.get(User, "user-isolated")
        session.delete(u)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    # Attempting to delete the isolated organization (referenced by Delivery.organization_id)
    with app.state.session_factory() as session:
        org = session.get(Organization, "org-isolated")
        session.delete(org)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_child_item_deletion_leaves_delivery_intact(app):
    """Verify that deleting a DeliveryItem does not cascade upwards to the Delivery."""
    with app.state.session_factory() as session:
        delivery = Delivery(organization_id="org-1", recorded_by="manager-a")
        session.add(delivery)
        session.flush()

        item = DeliveryItem(delivery_id=delivery.id, item_kind="document", title="Документ для удаления")
        session.add(item)
        session.commit()

        d_id = delivery.id
        i_id = item.id

    with app.state.session_factory() as session:
        item = session.get(DeliveryItem, i_id)
        session.delete(item)
        session.commit()

    with app.state.session_factory() as session:
        assert session.get(DeliveryItem, i_id) is None
        deliv = session.get(Delivery, d_id)
        assert deliv is not None
        assert deliv.organization_id == "org-1"


def test_delivery_bulk_operations_and_temporal_ordering(app):
    """Verify bulk instantiation uniqueness and Section 3 query pattern (organization_id, sent_at DESC)."""
    base_time = datetime(2026, 9, 21, 10, 0, 0, tzinfo=timezone.utc)
    count = 25

    with app.state.session_factory() as session:
        deliveries = []
        for i in range(count):
            d = Delivery(
                organization_id="org-1",
                recorded_by="manager-a",
                status="sent",
                channel="email",
                sent_at=base_time.replace(minute=i),
                comment=f"Тестовая доставка #{i} 🚀",
            )
            deliveries.append(d)
        session.add_all(deliveries)
        session.commit()

        d_ids = [d.id for d in deliveries]
        # Check all generated IDs are unique
        assert len(set(d_ids)) == count

    with app.state.session_factory() as session:
        # Query matching Section 3: IX(organization_id, sent_at DESC)
        stmt = (
            select(Delivery)
            .where(Delivery.organization_id == "org-1", Delivery.status == "sent")
            .order_by(Delivery.sent_at.desc())
        )
        results = list(session.scalars(stmt))
        assert len(results) >= count
        # Verify descending order of sent_at
        timestamps = [r.sent_at for r in results if r.sent_at is not None]
        assert timestamps == sorted(timestamps, reverse=True)
        # Verify unicode / emoji persistence
        assert "🚀" in results[0].comment

