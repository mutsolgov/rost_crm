"""Data seeder script for RTK IT School mock services.

Parses organizer data files using strictly Python stdlib (0 external dependencies):
1. 'данные предоставленные организаторами/Загрузка пользователей.xlsx'
2. 'данные предоставленные организаторами/Данные оплат.json'
3. 'данные предоставленные организаторами/Вендоры.xlsx'

Generates:
- mock_services/lms/seed_data.json
- mock_services/website/seed_data.json
"""
from __future__ import annotations

import io
import json
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


def col_letter_to_index(col_letters: str) -> int:
    """Converts Excel column letters (A, B, ..., Z, AA, AB) to 0-based index."""
    idx = 0
    for ch in col_letters.upper():
        if "A" <= ch <= "Z":
            idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return max(0, idx - 1)


def parse_xlsx_sheets_stdlib(data: bytes) -> dict[str, list[list[str]]]:
    """Parses all worksheets from an XLSX file using purely stdlib zipfile and xml.etree."""
    import zipfile

    zf = zipfile.ZipFile(io.BytesIO(data))
    namelist = set(zf.namelist())

    # 1. Parse shared strings table if present
    shared_strings: list[str] = []
    if "xl/sharedStrings.xml" in namelist:
        tree = ET.fromstring(zf.read("xl/sharedStrings.xml"))
        ns_url = (
            tree.tag.split("}")[0][1:]
            if tree.tag.startswith("{")
            else "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        )
        ns = {"ns": ns_url}
        for si in tree.findall(".//ns:si", ns):
            text_parts = [t.text for t in si.findall(".//ns:t", ns) if t.text]
            shared_strings.append("".join(text_parts))

    # 2. Parse relationship mappings (rId -> target xml path)
    rels_map: dict[str, str] = {}
    if "xl/_rels/workbook.xml.rels" in namelist:
        tree = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        for rel in tree:
            r_id = rel.get("Id")
            target = rel.get("Target")
            if r_id and target:
                if not target.startswith("xl/"):
                    target = "xl/" + target.lstrip("/")
                rels_map[r_id] = target

    # 3. Discover sheet names and ordered targets from workbook.xml
    sheets_info: list[tuple[str, str]] = []
    if "xl/workbook.xml" in namelist:
        tree = ET.fromstring(zf.read("xl/workbook.xml"))
        ns_url = (
            tree.tag.split("}")[0][1:]
            if tree.tag.startswith("{")
            else "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        )
        ns = {"ns": ns_url}
        for s in tree.findall(".//ns:sheet", ns):
            sheet_name = s.get("name", "Sheet")
            r_id = s.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            target = rels_map.get(r_id, f"xl/worksheets/sheet{s.get('sheetId', '1')}.xml")
            sheets_info.append((sheet_name, target))

    # Fallback if workbook.xml is absent or unlinked
    if not sheets_info:
        ws_files = [n for n in namelist if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")]
        ws_files.sort(key=lambda s: [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)])
        for idx, target in enumerate(ws_files, start=1):
            sheets_info.append((f"Sheet{idx}", target))

    # 4. Parse rows for each sheet
    result: dict[str, list[list[str]]] = {}
    for sheet_name, target_xml in sheets_info:
        if target_xml not in namelist:
            continue

        tree = ET.fromstring(zf.read(target_xml))
        ns_url = (
            tree.tag.split("}")[0][1:]
            if tree.tag.startswith("{")
            else "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        )
        ns = {"ns": ns_url}

        rows: list[list[str]] = []
        for row_el in tree.findall(".//ns:row", ns):
            row_vals: list[str] = []
            for cell in row_el.findall("ns:c", ns):
                r_attr = cell.get("r", "")
                col_letters = "".join(filter(str.isalpha, r_attr))
                target_idx = col_letter_to_index(col_letters) if col_letters else len(row_vals)

                # Pad empty cells in sparse rows
                while len(row_vals) < target_idx:
                    row_vals.append("")

                cell_type = cell.get("t")
                v = cell.find("ns:v", ns)
                val = ""

                if cell_type == "s" and v is not None and v.text:
                    idx = int(v.text)
                    val = shared_strings[idx] if idx < len(shared_strings) else ""
                elif cell_type == "inlineStr":
                    text_parts = [t.text for t in cell.findall(".//ns:t", ns) if t.text]
                    val = "".join(text_parts)
                elif cell_type == "b" and v is not None and v.text:
                    val = "1" if v.text == "1" else "0"
                elif v is not None and v.text:
                    val = v.text

                row_vals.append(val)

            if any(c.strip() for c in row_vals):
                rows.append(row_vals)

        result[sheet_name] = rows

    return result


def extract_organizer_data(base_dir: Path) -> dict[str, Any]:
    """Reads and parses the organizer raw files."""
    org_data_dir = base_dir / "данные предоставленные организаторами"

    # 1. Parse 'Данные оплат.json'
    payments_path = org_data_dir / "Данные оплат.json"
    with open(payments_path, "r", encoding="utf-8") as f:
        raw_payments = json.load(f)

    # Filter null elements
    paid_orders = [p for p in raw_payments if p and isinstance(p, dict)]

    # 2. Parse 'Загрузка пользователей.xlsx'
    users_path = org_data_dir / "Загрузка пользователей.xlsx"
    with open(users_path, "rb") as f:
        users_sheets = parse_xlsx_sheets_stdlib(f.read())
    users_rows = users_sheets.get("Лист1", [])

    learners_raw = []
    if users_rows:
        # Header is row 0
        for r in users_rows[1:]:
            if len(r) >= 5 and any(r):
                learners_raw.append({
                    "last_name": r[0].strip(),
                    "first_name": r[1].strip(),
                    "patronymic": r[2].strip() if len(r) > 2 else "",
                    "phone": r[3].strip() if len(r) > 3 else "",
                    "email": r[4].strip() if len(r) > 4 else "",
                })

    # 3. Parse 'Вендоры.xlsx'
    vendors_path = org_data_dir / "Вендоры.xlsx"
    with open(vendors_path, "rb") as f:
        vendors_sheets = parse_xlsx_sheets_stdlib(f.read())
    vendors_rows = vendors_sheets.get("Лист1", [])

    vendors_raw = []
    if vendors_rows:
        for r in vendors_rows[1:]:
            if len(r) >= 6 and any(r):
                vendors_raw.append({
                    "company": r[0].strip(),
                    "product": r[1].strip(),
                    "contact_person": r[2].strip(),
                    "phone": r[3].strip(),
                    "email": r[4].strip(),
                    "channel": r[5].strip(),
                })

    return {
        "paid_orders": paid_orders,
        "learners_raw": learners_raw,
        "vendors_raw": vendors_raw,
    }


def build_seed_datasets(extracted: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Builds LMS and Website seed datasets adhering strictly to schema contracts."""
    paid_orders = extracted["paid_orders"]
    learners_raw = extracted["learners_raw"]
    vendors_raw = extracted["vendors_raw"]

    # Map learners with orders
    # We match by clean phone digits (last 10 digits) or email
    def clean_digits(p: str) -> str:
        return "".join(filter(str.isdigit, p))[-10:]

    orders_by_phone = {clean_digits(o["Телефон"]): o for o in paid_orders}
    orders_by_email = {o["Email"].strip().lower(): o for o in paid_orders}

    # Course ID mappings
    course_slugs = {
        "Анализ данных без программирования": "program-data-analysis",
        "Инженер-тестировщик": "program-qa",
        "Управление ИТ-проектами на базе программного продукта ПАО «Ростелеком»": "program-project-management",
        "Промпт-инжиниринг": "program-prompt-engineering",
        "Python-разработчик с использованием инструментов ИИ": "program-python-ai",
    }

    # Learner progress presets matching survey specification
    learner_presets = {
        "Черепанова Светлана Васильевна": {
            "id": "lrn-001",
            "progress": 85.0,
            "tests_passed": 8,
            "tests_total": 10,
            "score": 85.0,
            "org_name": "ПАО «Ростелеком»",
            "created_at": "2026-03-13T05:15:00Z",
            "amount": 45000.0,
        },
        "Кричанов Максим Сергеевич": {
            "id": "lrn-002",
            "progress": 90.0,
            "tests_passed": 9,
            "tests_total": 10,
            "score": 90.0,
            "org_name": "ООО «Базис»",
            "created_at": "2026-05-13T06:54:00Z",
            "amount": 55000.0,
        },
        "Григорьев Станислав Семенович": {
            "id": "lrn-003",
            "progress": 65.0,
            "tests_passed": 6,
            "tests_total": 10,
            "score": 65.0,
            "org_name": "ПАО «Ростелеком»",
            "created_at": "2026-06-17T18:45:00Z",
            "amount": 60000.0,
        },
        "Осипенко Ирина Викторовна": {
            "id": "lrn-004",
            "progress": 45.0,
            "tests_passed": 4,
            "tests_total": 10,
            "score": 45.0,
            "org_name": "ООО «ТДата»",
            "created_at": "2026-05-22T06:13:00Z",
            "amount": 48000.0,
        },
        "Иванов Михаил Петрович": {
            "id": "lrn-005",
            "progress": 30.0,
            "tests_passed": 3,
            "tests_total": 10,
            "score": 30.0,
            "org_name": "ООО «РТК ИТ»",
            "created_at": "2026-09-04T07:54:00Z",
            "amount": 75000.0,
        },
    }

    # Build 5 enriched learners
    lms_learners = []
    for raw_l in learners_raw:
        full_name = f"{raw_l['last_name']} {raw_l['first_name']} {raw_l['patronymic']}".strip()
        ph_key = clean_digits(raw_l["phone"])
        em_key = raw_l["email"].strip().lower()

        order = orders_by_phone.get(ph_key) or orders_by_email.get(em_key)
        preset = learner_presets.get(full_name, {
            "id": f"lrn-{len(lms_learners)+1:03d}",
            "progress": 50.0,
            "tests_passed": 5,
            "tests_total": 10,
            "score": 50.0,
            "org_name": "ПАО «Ростелеком»",
            "created_at": "2026-01-01T00:00:00Z",
            "amount": 50000.0,
        })

        course_name = order["Курс"] if order else "Анализ данных без программирования"
        cohort_num = order["Номер потока"] if order else 1
        order_num = order["Номер заявки"] if order else f"ORD-{preset['id']}"
        phone_fmt = order["Телефон"] if order else raw_l["phone"]

        lms_learners.append({
            "id": preset["id"],
            "learner_id": preset["id"],
            "last_name": raw_l["last_name"],
            "first_name": raw_l["first_name"],
            "patronymic": raw_l["patronymic"],
            "full_name": full_name,
            "phone": raw_l["phone"],
            "phone_formatted": phone_fmt,
            "email": raw_l["email"],
            "order_id": order_num,
            "order_number": order_num,
            "course": course_name,
            "program_id": course_slugs.get(course_name, "program-devops"),
            "cohort": cohort_num,
            "cohort_id": cohort_num,
            "progress": preset["progress"],
            "progress_percent": preset["progress"],
            "tests_passed": preset["tests_passed"],
            "tests_total": preset["tests_total"],
            "score": preset["score"],
            "status": "active",
        })

    # Build 4 cohorts
    cohorts = [
        {
            "id": 1,
            "cohort_id": 1,
            "name": "Поток 1",
            "course": "Анализ данных без программирования, Инженер-тестировщик",
            "courses": ["Анализ данных без программирования", "Инженер-тестировщик"],
            "start_date": "2026-03-15T00:00:00Z",
        },
        {
            "id": 2,
            "cohort_id": 2,
            "name": "Поток 2",
            "course": "Управление ИТ-проектами на базе программного продукта ПАО «Ростелеком»",
            "courses": ["Управление ИТ-проектами на базе программного продукта ПАО «Ростелеком»"],
            "start_date": "2026-06-20T00:00:00Z",
        },
        {
            "id": 3,
            "cohort_id": 3,
            "name": "Поток 3",
            "course": "Промпт-инжиниринг",
            "courses": ["Промпт-инжиниринг"],
            "start_date": "2026-06-01T00:00:00Z",
        },
        {
            "id": 4,
            "cohort_id": 4,
            "name": "Поток 4",
            "course": "Python-разработчик с использованием инструментов ИИ",
            "courses": ["Python-разработчик с использованием инструментов ИИ"],
            "start_date": "2026-09-10T00:00:00Z",
        },
    ]

    # Partner organizations structured from 'Вендоры.xlsx'
    # 5 core enterprises: ПАО «Ростелеком», ООО «Базис», ООО «ТДата», ООО «РТК ИТ Плюс», ООО «РТК ИТ»
    partner_orgs = [
        {
            "company": "ПАО «Ростелеком»",
            "products": ["«RT.DataVision»"],
            "representative_name": "Кузнецов Дмитрий Сергеевич",
            "representative_phone": "+7 (922) 333-44-55",
            "representative_email": "kuznetsov.ds@example.ru",
            "channel": "Чат в ТГ",
        },
        {
            "company": "ООО «Базис»",
            "products": ["«Базис Dynamix»"],
            "representative_name": "Иванов Иван Иванович",
            "representative_phone": "+7 (900) 111-22-33",
            "representative_email": "ivanov.ii@example.ru",
            "channel": "Почта, Чат в ТГ",
        },
        {
            "company": "ООО «ТДата»",
            "products": ["«RT.DataLake»", "«RT.Warehouse»"],
            "representative_name": "Смирнова Анна Петровна",
            "representative_phone": "+7 (911) 222-33-44",
            "representative_email": "smirnova.ap@example.ru",
            "channel": "Чат в ТГ",
        },
        {
            "company": "ООО «РТК ИТ Плюс»",
            "products": ["«AKOLA»", "«Яга»"],
            "contacts": [
                {
                    "name": "Попова Мария Владимировна",
                    "phone": "+7 (933) 444-55-66",
                    "email": "popova.mv@example.ru",
                    "product": "«AKOLA»",
                },
                {
                    "name": "Соколов Алексей Андреевич",
                    "phone": "+7 (944) 555-66-77",
                    "email": "sokolov.aa@example.ru",
                    "product": "«Яга»",
                },
            ],
        },
        {
            "company": "ООО «РТК ИТ»",
            "products": ["«Web3Gate»", "«Аврора SDK»", "«Нейрошлюз»"],
            "contacts": [
                {
                    "name": "Лебедева Елена Дмитриевна",
                    "phone": "+7 (955) 666-77-88",
                    "email": "lebedeva.ed@example.ru",
                    "product": "«Web3Gate»",
                },
                {
                    "name": "Козлов Максим Игоревич",
                    "phone": "+7 (966) 777-88-99",
                    "email": "kozlov.mi@example.ru",
                    "product": "«Аврора SDK»",
                },
                {
                    "name": "Новикова Ольга Александровна",
                    "phone": "+7 (977) 888-99-00",
                    "email": "novikova.oa@example.ru",
                    "product": "«Нейрошлюз»",
                },
            ],
        },
    ]

    # Metrics matching LiveLMSAdapter specification
    lms_metrics = [
        {
            "external_id": "zion-metric-org-1-devops-active_cohorts",
            "organization_id": "org-1",
            "organization_name": "Московский технический университет",
            "program_id": "program-devops",
            "program_name": "DevOps и облачные технологии",
            "metric_code": "active_cohorts",
            "value": 2.0,
            "unit": "cohort",
            "as_of": "2026-10-07T10:00:00Z",
            "source_revision": "1",
        },
        {
            "external_id": "zion-metric-org-1-devops-students_enrolled",
            "organization_id": "org-1",
            "organization_name": "Московский технический университет",
            "program_id": "program-devops",
            "program_name": "DevOps и облачные технологии",
            "metric_code": "students_enrolled",
            "value": 45.0,
            "unit": "student",
            "as_of": "2026-10-07T10:00:00Z",
            "source_revision": "1",
        },
        {
            "external_id": "zion-metric-org-1-devops-students_completed",
            "organization_id": "org-1",
            "organization_name": "Московский технический университет",
            "program_id": "program-devops",
            "program_name": "DevOps и облачные технологии",
            "metric_code": "students_completed",
            "value": 38.0,
            "unit": "student",
            "as_of": "2026-10-07T10:00:00Z",
            "source_revision": "1",
        },
        {
            "external_id": "zion-metric-org-1-devops-attendance_rate",
            "organization_id": "org-1",
            "organization_name": "Московский технический университет",
            "program_id": "program-devops",
            "program_name": "DevOps и облачные технологии",
            "metric_code": "attendance_rate",
            "value": 91.5,
            "unit": "percent",
            "as_of": "2026-10-07T10:00:00Z",
            "source_revision": "1",
        },
        {
            "external_id": "zion-metric-org-2-qa-active_cohorts",
            "organization_id": "org-2",
            "organization_name": "Северный университет прикладных наук",
            "program_id": "program-qa",
            "program_name": "Инженерия качества ПО",
            "metric_code": "active_cohorts",
            "value": 1.0,
            "unit": "cohort",
            "as_of": "2026-10-07T11:00:00Z",
            "source_revision": "1",
        },
        {
            "external_id": "zion-metric-org-2-qa-students_enrolled",
            "organization_id": "org-2",
            "organization_name": "Северный университет прикладных наук",
            "program_id": "program-qa",
            "program_name": "Инженерия качества ПО",
            "metric_code": "students_enrolled",
            "value": 30.0,
            "unit": "student",
            "as_of": "2026-10-07T11:00:00Z",
            "source_revision": "1",
        },
        {
            "external_id": "zion-metric-org-2-qa-students_completed",
            "organization_id": "org-2",
            "organization_name": "Северный университет прикладных наук",
            "program_id": "program-qa",
            "program_name": "Инженерия качества ПО",
            "metric_code": "students_completed",
            "value": 26.0,
            "unit": "student",
            "as_of": "2026-10-07T11:00:00Z",
            "source_revision": "1",
        },
        {
            "external_id": "zion-metric-org-2-qa-attendance_rate",
            "organization_id": "org-2",
            "organization_name": "Северный университет прикладных наук",
            "program_id": "program-qa",
            "program_name": "Инженерия качества ПО",
            "metric_code": "attendance_rate",
            "value": 88.0,
            "unit": "percent",
            "as_of": "2026-10-07T11:00:00Z",
            "source_revision": "1",
        },
    ]

    # LMS Webhook simulation template
    lms_webhook_template = [
        {
            "schema_version": "1.0",
            "source": "lms",
            "entity_type": "learning_metric",
            "external_id": "zion-metric-org-1-devops-active_cohorts-v2",
            "source_revision": "2",
            "operation": "upsert",
            "effective_at": "2026-10-07T12:00:00Z",
            "payload": {
                "organization_id": "org-1",
                "program_id": "program-devops",
                "metric_code": "active_cohorts",
                "value": 3.0,
                "unit": "cohort",
                "as_of": "2026-10-07T12:00:00Z",
            },
        }
    ]

    lms_seed = {
        "service": "rtk-lms-zion",
        "version": "1.4.0",
        "as_of": "2026-10-07T12:00:00Z",
        "summary": {
            "learners_count": len(lms_learners),
            "cohorts_count": len(cohorts),
            "courses_count": len(course_slugs),
            "partner_companies_count": len(partner_orgs),
        },
        "metrics": lms_metrics,
        "learners": lms_learners,
        "cohorts": cohorts,
        "partner_organizations": partner_orgs,
        "webhook_simulation_templates": lms_webhook_template,
    }

    # Build Website applications from 5 paid orders
    website_applications = []
    for order in paid_orders:
        fio = f"{order['Фамилия']} {order['Имя']} {order.get('Отчество', '')}".strip()
        preset = learner_presets.get(fio, {
            "org_name": "ПАО «Ростелеком»",
            "created_at": "2026-03-13T05:15:00Z",
            "amount": 50000.0,
        })
        order_num = order["Номер заявки"]
        course_name = order["Курс"]
        cohort_num = order["Номер потока"]

        website_applications.append({
            "id": order_num,
            "external_id": order_num,
            "order_number": order_num,
            "created_at": preset["created_at"],
            "organization_name": preset["org_name"],
            "contact_name": fio,
            "representative_name": fio,
            "contact_email": order["Email"],
            "representative_email": order["Email"],
            "contact_phone": order["Телефон"],
            "representative_phone": order["Телефон"],
            "representative_position": "Слушатель курса",
            "program_name": course_name,
            "program_id": course_slugs.get(course_name, "program-devops"),
            "cohort": cohort_num,
            "cohort_id": cohort_num,
            "amount": preset["amount"],
            "payment_status": "paid",
            "status": "paid",
            "comments": f"Оплаченная заявка на курс '{course_name}', Поток {cohort_num}.",
            "source_revision": "1",
        })

    # Website Webhook simulation template
    website_webhook_template = [
        {
            "schema_version": "1.0",
            "source": "website",
            "entity_type": "application",
            "external_id": "ORD-20261007999999-NEWAPP",
            "source_revision": "1",
            "operation": "upsert",
            "effective_at": "2026-10-07T14:00:00Z",
            "payload": {
                "organization_name": "ПАО «Ростелеком»",
                "representative_name": "Новый Заявитель",
                "representative_email": "new.applicant@rt.ru",
                "representative_phone": "+7 (999) 777-88-99",
                "representative_position": "Куратор направления",
                "program_name": "DevOps и облачные технологии",
                "program_id": "program-devops",
                "comments": "Входящая заявка на поток слушателей через образовательный портал.",
            },
        }
    ]

    website_seed = {
        "service": "rtk-it-school-portal",
        "version": "2.1.0",
        "as_of": "2026-10-07T12:00:00Z",
        "summary": {
            "total_applications": len(website_applications),
            "partner_companies_count": len(partner_orgs),
        },
        "applications": website_applications,
        "partners": partner_orgs,
        "webhook_simulation_templates": website_webhook_template,
    }

    return lms_seed, website_seed


def main() -> None:
    """Main execution function for data seeding."""
    root_dir = Path(__file__).resolve().parent.parent
    extracted = extract_organizer_data(root_dir)
    lms_seed, website_seed = build_seed_datasets(extracted)

    lms_dir = root_dir / "mock_services" / "lms"
    website_dir = root_dir / "mock_services" / "website"
    lms_dir.mkdir(parents=True, exist_ok=True)
    website_dir.mkdir(parents=True, exist_ok=True)

    lms_file = lms_dir / "seed_data.json"
    website_file = website_dir / "seed_data.json"

    with open(lms_file, "w", encoding="utf-8") as f:
        json.dump(lms_seed, f, ensure_ascii=False, indent=2)
    print(f"Successfully generated LMS seed data: {lms_file}")

    with open(website_file, "w", encoding="utf-8") as f:
        json.dump(website_seed, f, ensure_ascii=False, indent=2)
    print(f"Successfully generated Website seed data: {website_file}")


if __name__ == "__main__":
    main()
