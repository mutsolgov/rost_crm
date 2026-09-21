from __future__ import annotations

import csv
import io
import xml.etree.ElementTree as ET
import zipfile
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from .errors import APIError
from .models import (
    Contract,
    Organization,
    OrganizationAccess,
    OrganizationContact,
    Product,
    Program,
    ProgramProduct,
    User,
)
from .services import begin_command, finish_command, require_permission

COLUMN_SYNONYMS = {
    "name": [
        "название вуза", "название организации", "название", "организация",
        "вуз", "университет", "organization", "name", "оу", "university"
    ],
    "type": ["тип", "тип организации", "тип вуза", "type"],
    "manager": ["ответственный", "руководитель", "менеджер", "manager", "owner"],
    "contact_name": ["контактное лицо", "фио", "контакт", "contact", "contact_name", "full_name"],
    "position": ["должность", "position"],
    "email": ["email", "e-mail", "электронная почта", "почта"],
    "phone": ["телефон", "phone", "тел"],
    "program": ["программа", "program"],
    "product": ["продукт", "product"],
    "contract_number": ["номер договора", "договор", "contract", "contract_number"],
}


def _match_header(header_text: str) -> str | None:
    norm = header_text.strip().lower()
    for field, synonyms in COLUMN_SYNONYMS.items():
        if norm in synonyms:
            return field
    for field, synonyms in COLUMN_SYNONYMS.items():
        for syn in synonyms:
            if syn in norm or norm in syn:
                return field
def _find_organization(db: Session, name: str) -> Organization | None:
    if not name:
        return None
    org = db.scalar(select(Organization).where(Organization.name == name))
    if org is not None:
        return org
    name_norm = name.strip().lower()
    for o in db.scalars(select(Organization)).all():
        if o.name.strip().lower() == name_norm:
            return o
    return None


def _find_program(db: Session, name: str) -> Program | None:
    if not name:
        return None
    prog = db.scalar(select(Program).where(Program.name == name))
    if prog is not None:
        return prog
    name_norm = name.strip().lower()
    for p in db.scalars(select(Program)).all():
        if p.name.strip().lower() == name_norm:
            return p
    return None


def _find_product(db: Session, name: str) -> Product | None:
    if not name:
        return None
    prod = db.scalar(select(Product).where(Product.name == name))
    if prod is not None:
        return prod
    name_norm = name.strip().lower()
    for p in db.scalars(select(Product)).all():
        if p.name.strip().lower() == name_norm:
            return p
    return None


def _find_contact(db: Session, org_id: str, contact_name: str) -> OrganizationContact | None:
    if not contact_name:
        return None
    contact = db.scalar(
        select(OrganizationContact).where(
            OrganizationContact.organization_id == org_id,
            OrganizationContact.full_name == contact_name.strip(),
        )
    )
    if contact is not None:
        return contact
    c_norm = contact_name.strip().lower()
    for c in db.scalars(select(OrganizationContact).where(OrganizationContact.organization_id == org_id)).all():
        if c.full_name.strip().lower() == c_norm:
            return c
    return None


def parse_xlsx_stdlib(data: bytes) -> list[list[str]]:
    """Parses XLSX spreadsheet via stdlib zipfile and xml.etree.ElementTree."""
    zf = zipfile.ZipFile(io.BytesIO(data))
    shared: list[str] = []
    if "xl/sharedStrings.xml" in zf.namelist():
        tree = ET.fromstring(zf.read("xl/sharedStrings.xml"))
        ns = {"ns": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        for si in tree.findall(".//ns:si", ns):
            t = si.find("ns:t", ns)
            shared.append(t.text if t is not None and t.text else "")

    # Look for sheet1.xml
    sheet_name = "xl/worksheets/sheet1.xml"
    if sheet_name not in zf.namelist():
        # Fallback to first worksheet
        ws = [n for n in zf.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")]
        if not ws:
            raise APIError("FILE_TYPE_NOT_ALLOWED", "Лист таблицы не найден в XLSX файле.", 422)
        sheet_name = ws[0]

    tree = ET.fromstring(zf.read(sheet_name))
    ns = {"ns": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    rows: list[list[str]] = []

    for row_el in tree.findall(".//ns:row", ns):
        row_vals: list[str] = []
        for cell in row_el.findall("ns:c", ns):
            cell_type = cell.get("t")
            v = cell.find("ns:v", ns)
            val = ""
            if cell_type == "s" and v is not None and v.text:
                idx = int(v.text)
                val = shared[idx] if idx < len(shared) else ""
            elif cell_type == "inlineStr":
                t = cell.find(".//ns:t", ns)
                val = t.text if t is not None and t.text else ""
            elif v is not None and v.text:
                val = v.text
            row_vals.append(val)
        if any(cell.strip() for cell in row_vals):
            rows.append(row_vals)
    return rows


def parse_csv_stdlib(data: bytes) -> list[list[str]]:
    """Parses CSV text using stdlib csv with multi-encoding and delimiter detection."""
    text = None
    for enc in ("utf-8-sig", "utf-8", "cp1251", "latin1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise APIError("FILE_TYPE_NOT_ALLOWED", "Не удалось декодировать текстовый файл CSV.", 422)

    first_line = text.splitlines()[0] if text.splitlines() else ""
    delimiter = ";" if first_line.count(";") > first_line.count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    return [row for row in reader if any(cell.strip() for cell in row)]


def parse_tabular_file(data: bytes, filename: str) -> list[dict[str, str]]:
    """Parses uploaded tabular file (CSV or XLSX) into a list of normalized row dictionaries."""
    fn_lower = filename.lower()
    if fn_lower.endswith(".xlsx") or data.startswith(b"PK\x03\x04"):
        raw_rows = parse_xlsx_stdlib(data)
    else:
        raw_rows = parse_csv_stdlib(data)

    if not raw_rows:
        return []

    header_row = raw_rows[0]
    col_mapping: dict[int, str] = {}
    for idx, col_name in enumerate(header_row):
        matched = _match_header(col_name)
        if matched:
            col_mapping[idx] = matched

    # If no headers matched, treat row 0 as data if it has standard format, otherwise error
    if not col_mapping:
        raise APIError(
            "VALIDATION_ERROR",
            "Не удалось распознать заголовки колонок в таблице. Ожидаются: Название вуза, Тип, Контактное лицо, Договор.",
            422,
        )

    parsed_rows: list[dict[str, str]] = []
    for row in raw_rows[1:]:
        row_dict: dict[str, str] = {}
        for idx, val in enumerate(row):
            if idx in col_mapping:
                row_dict[col_mapping[idx]] = val.strip()
        if any(row_dict.values()):
            parsed_rows.append(row_dict)

    return parsed_rows


def preview_organizations_import(
    db: Session,
    user: User,
    file_bytes: bytes,
    filename: str,
) -> dict:
    """Dry-run parse without DB mutation, returns preview rows, validation results, and diagnostic errors."""
    require_permission(user, "organizations.create")
    parsed_rows = parse_tabular_file(file_bytes, filename)

    import_id = uuid4().hex
    preview_rows: list[dict] = []
    errors: list[dict] = []
    seen_names: set[str] = set()

    for idx, row in enumerate(parsed_rows, start=1):
        row_errors: list[str] = []
        name = row.get("name", "").strip()

        if not name:
            row_errors.append("Поле 'Название вуза' обязательно для заполнения.")
            errors.append({"row": idx, "field": "name", "message": "Поле 'Название вуза' обязательно."})

        # Duplicate check within payload
        name_lower = name.lower()
        if name_lower in seen_names:
            row_errors.append(f"Дубликат организации '{name}' в загружаемом файле.")
            errors.append({"row": idx, "field": "name", "message": f"Дубликат '{name}' внутри файла."})
        elif name:
            seen_names.add(name_lower)

        # Database existence check
        status = "create"
        if name:
            existing = _find_organization(db, name)
            if existing:
                status = "update"

        # Program & product compatibility check
        prog_name = row.get("program")
        prod_name = row.get("product")
        if prog_name or prod_name:
            prog = _find_program(db, prog_name) if prog_name else None
            prod = _find_product(db, prod_name) if prod_name else None
            if prog_name and not prog:
                row_errors.append(f"Программа '{prog_name}' не найдена в каталоге.")
                errors.append({
                    "row": idx,
                    "field": "program",
                    "message": f"Программа '{prog_name}' не найдена.",
                })
            if prod_name and not prod:
                row_errors.append(f"Продукт '{prod_name}' не найден в каталоге.")
                errors.append({
                    "row": idx,
                    "field": "product",
                    "message": f"Продукт '{prod_name}' не найден.",
                })
            if prog and prod:
                link = db.scalar(
                    select(ProgramProduct).where(
                        ProgramProduct.program_id == prog.id,
                        ProgramProduct.product_id == prod.id,
                    )
                )
                if not link:
                    row_errors.append(f"Программа '{prog_name}' не совместима с продуктом '{prod_name}'.")
                    errors.append({
                        "row": idx,
                        "field": "product",
                        "message": f"Программа '{prog_name}' и продукт '{prod_name}' не связаны.",
                    })

        # Type validation
        org_type = row.get("type", "university")
        if org_type not in {"university", "school", "other"}:
            org_type = "university"

        preview_rows.append({
            "row_index": idx,
            "row_number": idx,
            "status": status,
            "is_valid": len(row_errors) == 0,
            "errors": row_errors,
            "organization_name": name,
            "org_type": org_type,
            "contact_name": row.get("contact_name"),
            "program_name": row.get("program"),
            "product_name": row.get("product"),
            "data": {
                "name": name,
                "type": org_type,
                "contact_name": row.get("contact_name"),
                "position": row.get("position"),
                "email": row.get("email"),
                "phone": row.get("phone"),
                "program": row.get("program"),
                "product": row.get("product"),
                "contract_number": row.get("contract_number"),
            },
        })

    valid_count = sum(1 for r in preview_rows if r["is_valid"])
    error_count = sum(1 for r in preview_rows if not r["is_valid"])

    return {
        "import_id": import_id,
        "rows_total": len(preview_rows),
        "valid_count": valid_count,
        "error_count": error_count,
        "preview_rows": preview_rows,
        "errors": errors,
    }


def commit_organizations_import(
    db: Session,
    user: User,
    rows: list[dict],
    idempotency_key: str | None = None,
) -> dict:
    """Atomic transactional creation of Organizations, Contacts, Contracts protected by Idempotency-Key."""
    require_permission(user, "organizations.create")

    body_dict = {"rows": rows}
    saved, replay = begin_command(db, user, "import_organizations", idempotency_key, body_dict)
    if replay is not None:
        return replay

    created_orgs = 0
    updated_orgs = 0
    created_contacts = 0
    created_contracts = 0

    try:
        for row in rows:
            data = row.get("data") if "data" in row else row
            name = (data.get("name") or data.get("organization_name") or "").strip()
            if not name:
                continue

            org_type = data.get("type") or data.get("org_type") or "university"
            if org_type not in {"university", "school", "other"}:
                org_type = "university"

            org = _find_organization(db, name)
            if not org:
                org = Organization(name=name, type=org_type)
                db.add(org)
                db.flush()
                created_orgs += 1
                # Grant access to user
                access = OrganizationAccess(organization_id=org.id, user_id=user.id, read_all=True)
                db.add(access)
            else:
                updated_orgs += 1

            contact_name = data.get("contact_name")
            if contact_name and contact_name.strip():
                existing_contact = _find_contact(db, org.id, contact_name)
                if not existing_contact:
                    new_contact = OrganizationContact(
                        organization_id=org.id,
                        full_name=contact_name.strip(),
                        position=data.get("position") or data.get("contact_position") or "Представитель",
                        email=data.get("email") or data.get("contact_email"),
                        phone=data.get("phone") or data.get("contact_phone"),
                        active=True,
                    )
                    db.add(new_contact)
                    created_contacts += 1

            contract_num = data.get("contract_number")
            if contract_num and contract_num.strip():
                existing_contract = db.scalar(
                    select(Contract).where(
                        Contract.organization_id == org.id,
                        Contract.number == contract_num.strip(),
                    )
                )
                if not existing_contract:
                    new_contract = Contract(
                        organization_id=org.id,
                        number=contract_num.strip(),
                        status="active",
                    )
                    db.add(new_contract)
                    created_contracts += 1

        db.flush()
    except Exception:
        db.rollback()
        raise

    result = {
        "status": "committed",
        "success": True,
        "rows_total": len(rows),
        "imported_count": created_orgs + updated_orgs,
        "created_organizations": created_orgs,
        "updated_organizations": updated_orgs,
        "created_contacts": created_contacts,
        "created_contracts": created_contracts,
        "errors": [],
    }

    return finish_command(db, saved, result, None)

