from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import struct
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .errors import APIError
from .models import (
    Comment,
    Contract,
    Interaction,
    License,
    Organization,
    OrganizationAccess,
    OrganizationContact,
    Product,
    Program,
    ProgramProduct,
    Team,
    User,
    new_id,
    utcnow,
)
from .services import (
    append_event,
    begin_command,
    finish_command,
    has_organization_access,
    require_permission,
)
from .workflow import TERMINAL_STATES

_IMPORT_PACKAGES: dict[str, dict] = {}


def canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


COLUMN_SYNONYMS = {
    "name": [
        "название вуза", "название организации", "название", "организация",
        "вуз", "университет", "organization", "name", "оу", "university",
        "наименование вуза", "наименование организации", "образовательная организация",
        "институт", "академия",
    ],
    "type": ["тип", "тип организации", "тип вуза", "type"],
    "manager": [
        "фио менеджера", "ответственный", "руководитель", "менеджер", "manager",
        "owner", "менеджер проекта", "курирующий менеджер", "ответственный менеджер",
    ],
    "contact_name": [
        "ответственные от вуза", "ответственный от вуза", "контактное лицо от вуза",
        "контактное лицо", "фио", "контакт", "contact", "contact_name", "full_name",
        "представитель вуза", "куратор от вуза", "куратор", "представитель", "контакты",
        "контакты вуза", "фио сотрудника", "фио куратора", "контакт от вуза",
        "фио представителя", "представитель вендора", "контактное лицо вендора",
    ],
    "position": ["должность", "position", "должность контакта", "должность представителя"],
    "email": ["email", "e-mail", "электронная почта", "почта", "mail"],
    "phone": ["телефон", "phone", "тел", "тел.", "номер телефона", "контактный телефон"],
    "program": ["программа", "program", "ит-программа", "наименование программы", "образовательная программа"],
    "product": [
        "продукт", "product", "по", "программное обеспечение", "наименование по",
        "по/продукт", "продукт/по", "ит-продукт", "software", "продукт по",
        "наименование продукта", "лицензия по", "продукты", "программные продукты",
        "отечественное по",
    ],
    "vendor": [
        "вендор", "vendor", "производитель", "поставщик", "разработчик", "вендор по",
        "компания", "организация-вендор", "вендор/компания", "компания-вендор",
        "название вендора", "наименование вендора",
    ],
    "role": [
        "роль", "role", "роль пользователя", "роль в crm", "должность в crm",
        "тип учетной записи", "уровень доступа",
    ],
    "team": [
        "команда", "отдел", "team", "department", "подразделение", "группа",
    ],
    "contract_number": ["номер договора", "договор", "contract", "contract_number", "№ договора", "номер договора (контракта)", "контракт"],
    "license_signed_on": [
        "подписание лицензии", "дата подписания лицензии", "лицензия подписана",
        "license_signed_on", "дата лицензии", "дата подписания", "подписание",
        "дата заключения лицензии",
    ],
    "license_term_years": [
        "срок действия лицензии (год)", "срок действия лицензии", "срок действия",
        "срок лицензии", "срок действия (год)", "license_term_years", "term_years",
        "срок (год)", "срок (лет)", "срок действия (лет)", "срок лицензии (лет)",
        "срок действия лицензии (лет)", "срок лицензии (год)", "срок",
    ],
    "license_transfer_status": [
        "статус по передачи", "статус передачи", "статус передачи лицензии",
        "статус по передаче", "transfer_status", "license_transfer_status",
        "статус лицензии", "передача лицензии", "статус",
    ],
    "comment": [
        "комментарий", "комментарии", "комментарий к старту взаимодействия",
        "начальный комментарий", "заметка", "примечание", "примечания",
        "comment", "notes", "комментарии к старту", "заметки",
    ],
}


RUSSIAN_MONTHS = {
    "января": "01", "январь": "01", "янв": "01",
    "февраля": "02", "февраль": "02", "фев": "02",
    "марта": "03", "март": "03", "мар": "03",
    "апреля": "04", "апрель": "04", "апр": "04",
    "мая": "05", "май": "05",
    "июня": "06", "июнь": "06", "июн": "06",
    "июля": "07", "июль": "07", "июл": "07",
    "августа": "08", "август": "08", "авг": "08",
    "сентября": "09", "сентябрь": "09", "сен": "09", "сент": "09",
    "октября": "10", "октябрь": "10", "окт": "10",
    "ноября": "11", "ноябрь": "11", "ноя": "11",
    "декабря": "12", "декабрь": "12", "дек": "12",
}


def _parse_date(val: Any) -> datetime | None:
    if not val:
        return None
    if isinstance(val, bool):
        return None
    if isinstance(val, datetime):
        return val.replace(tzinfo=timezone.utc) if val.tzinfo is None else val
    if hasattr(val, "year") and hasattr(val, "month") and hasattr(val, "day"):
        return datetime(val.year, val.month, val.day, tzinfo=timezone.utc)
    from datetime import timedelta
    if isinstance(val, (int, float)):
        if 1900 <= val <= 2100:
            return datetime(int(val), 1, 1, tzinfo=timezone.utc)
        if 20000 <= val <= 80000:
            return datetime(1899, 12, 30, tzinfo=timezone.utc) + timedelta(days=float(val))
        return None
    val_str = str(val).strip()
    if not val_str:
        return None
    try:
        f = float(val_str)
        if 1900 <= f <= 2100:
            return datetime(int(f), 1, 1, tzinfo=timezone.utc)
        if 20000 <= f <= 80000:
            return datetime(1899, 12, 30, tzinfo=timezone.utc) + timedelta(days=f)
    except ValueError:
        pass
    val_str = re.sub(r"\s*(?:г\.?|года?)\s*$", "", val_str, flags=re.IGNORECASE).strip()
    val_lower = val_str.lower()
    for month_name, month_num in RUSSIAN_MONTHS.items():
        if month_name in val_lower:
            val_str = re.sub(r"\b" + month_name + r"\b", month_num, val_str, flags=re.IGNORECASE)
            break
    try:
        dt = datetime.fromisoformat(val_str.replace("Z", "+00:00"))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except Exception:
        pass
    norm_delims = re.sub(r"[/\s]+", ".", val_str)
    for fmt in (
        "%d.%m.%Y", "%Y.%m.%d", "%d.%m.%y",
        "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d",
        "%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M",
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
        "%Y",
    ):
        for candidate in (val_str, norm_delims):
            try:
                return datetime.strptime(candidate, fmt).replace(tzinfo=timezone.utc)
            except Exception:
                pass
    return None


def _parse_term_years(val: Any) -> int | None:
    if val is None or val == "":
        return None
    if isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        if 0 <= val <= 100:
            return int(round(val))
        return None
    val_str = str(val).strip()
    if not val_str:
        return None
    val_lower = val_str.lower()
    if any(w in val_lower for w in ("бессрочн", "вечн", "постоянн", "none", "null", "—", "n/a")) or val_lower == "-":
        return None
    if re.search(r"-\s*\d+", val_str) or "минус" in val_lower:
        return None
    try:
        f = float(val_str.replace(",", "."))
        if 0 <= f <= 100:
            return int(round(f))
        return None
    except ValueError:
        pass
    m = re.search(r"(?<![-\d])(\d+(?:[.,]\d+)?)(?!\s*[-–—])", val_str)
    if m:
        try:
            f = float(m.group(1).replace(",", "."))
            if 0 <= f <= 100:
                return int(round(f))
        except ValueError:
            pass
    return None


def _find_user(db: Session, manager_name: str) -> User | None:
    if not manager_name:
        return None
    m_norm = manager_name.strip().lower()
    m_tokens = set(m_norm.split())
    for u in db.scalars(select(User).where(User.active.is_(True))).all():
        u_name = (u.name or "").strip().lower()
        if (
            (u_name and (u_name == m_norm or set(u_name.split()) == m_tokens))
            or (u.id and u.id.strip().lower() == m_norm)
            or (u.keycloak_subject and u.keycloak_subject.strip().lower() == m_norm)
        ):
            return u
    return None


def _detect_file_type(headers: list[str], filename: str | None = None) -> str:
    cleaned = [h.strip().lower() for h in headers if h and h.strip()]

    # 1. LMS Learner identity & education document markers (Priority over generic user markers)
    learner_header_markers = ("снилс", "паспорт", "рождени", "регистрац", "диплом", "професси", "падеж")
    has_learner_marker = any(any(m in h for m in learner_header_markers) for h in cleaned)
    has_staff_role = any(any(r in h for r in ("роль", "команда", "отдел", "должность", "уровень доступа")) for h in cleaned)

    if filename:
        fn_lower = filename.lower()
        if any(m in fn_lower for m in ("слушател", "студент", "learner", "анкет")):
            return "lms_learners"
        if "загрузка пользователей" in fn_lower and not has_staff_role:
            return "lms_learners"
    if has_learner_marker:
        return "lms_learners"

    # 2. Filename vendor / user signatures
    if filename:
        fn_lower = filename.lower()
        if any(marker in fn_lower for marker in ("вендор", "vendor")):
            return "vendors"
        if any(marker in fn_lower for marker in ("сотрудник", "персонал", "кадр", "user", "пользовател")):
            return "users"

    # 3. Check for explicit university columns
    has_explicit_univ = any(
        any(u in h for u in ("название вуза", "наименование вуза", "название организации", "наименование организации"))
        for h in cleaned
    )

    # 4. Surname and user contact pair (Staff rosters without learner attributes)
    has_surname = any("фамилия" in h and "диплом" not in h and "падеж" not in h for h in cleaned)
    has_firstname = any("имя" in h and "диплом" not in h and "падеж" not in h for h in cleaned)
    has_email = any(any(e in h for e in ("email", "e-mail", "почт", "mail")) for h in cleaned)
    has_phone = any(
        any(p in h for p in ("телефон", "phone", "номер тел", "контактный тел")) or bool(re.search(r"\bтел\.?\b", h))
        for h in cleaned
    )
    has_user_pair = has_surname and (has_firstname or has_email or has_phone)
    has_role = any(any(r in h for r in ("роль", "отдел", "команда", "должность", "уровень доступа")) for h in cleaned)

    if (has_user_pair or has_role) and not has_explicit_univ:
        return "users"

    # 5. Vendor / product markers
    has_univ = any(
        any(u in h for u in ("вуз", "университет", "название вуза", "наименование вуза", "институт", "академия"))
        for h in cleaned
    )
    has_vendor = any(any(v in h for v in ("вендор", "компан", "производ", "поставщик", "разработчик")) for h in cleaned)
    has_prod = any(
        any(p in h for p in ("продукт", "программ", "software")) or h in ("по", "по/продукт", "ит-по", "софт")
        for h in cleaned
    )

    if (has_vendor or has_prod) and not has_univ:
        return "vendors"

    return "organizations"


def _parse_product_names(val: Any) -> list[str]:
    if not val:
        return []
    if isinstance(val, (list, tuple, set)):
        result = []
        for item in val:
            result.extend(_parse_product_names(item))
        return result
    if not str(val).strip():
        return []
    parts = re.split(r"[,;\r\n]+", str(val))
    result = []
    for p in parts:
        # Strip list enumeration prefixes (e.g. "1.", "1)", "-", "•"), preserving domestic names like "1C:ERP"
        cleaned = re.sub(r"^(?:\d+[\.\)\-]\s*|[\*\•\-\–—]\s*)", "", p.strip())
        cleaned = cleaned.strip("\"'«» \t")
        if cleaned.startswith("(") and cleaned.endswith(")"):
            cleaned = cleaned[1:-1].strip()
        elif cleaned.startswith("[") and cleaned.endswith("]"):
            cleaned = cleaned[1:-1].strip()
        cleaned = cleaned.strip("\"'«» \t")
        if cleaned:
            result.append(cleaned)
    return result


def _match_header(header_text: str, file_type: str | None = None) -> str | None:
    norm = header_text.strip().lower()
    norm_clean = norm.strip("\"'«»():;.")

    # High priority: email and phone in any file type (with boundary safety against Russian -тель suffixes)
    if any(e in norm for e in ("email", "e-mail", "почт", "mail")):
        return "email"
    if any(p in norm for p in ("телефон", "phone", "номер тел", "контактный тел")) or re.search(r"\bтел\.?\b", norm):
        return "phone"

    if file_type == "lms_learners":
        if "снилс" in norm:
            return "snils"
        if "серия" in norm and "паспорт" in norm:
            return "passport_series"
        if "номер" in norm and "паспорт" in norm:
            return "passport_number"
        if "кем выдан" in norm:
            return "passport_issued_by"
        if "код подразделен" in norm:
            return "passport_subdivision_code"
        if "дата выдачи" in norm and ("паспорт" in norm or "диплом" not in norm):
            return "passport_issued_date"
        if norm in ("пол", "gender"):
            return "gender"
        if "рождени" in norm:
            return "birth_date"
        if "регион" in norm and "регистрац" in norm:
            return "registration_region"
        if any(k in norm for k in ("населенный пункт", "город")) and "регистрац" in norm:
            return "registration_city"
        if "улиц" in norm:
            return "registration_street"
        if "дом" in norm:
            return "registration_house"
        if "квартир" in norm:
            return "registration_apartment"
        if "индекс" in norm:
            return "registration_postal_code"
        if "падеж" in norm:
            if "имя" in norm:
                return "first_name_dative"
            if "фамил" in norm:
                return "last_name_dative"
            if "отчеств" in norm:
                return "patronymic_dative"
        if "образовани" in norm:
            return "education"
        if "професси" in norm:
            return "profession"
        if "учебное заведение" in norm or ("вуз" in norm and "диплом" in norm):
            return "diploma_university"
        if "фамилия" in norm and "диплом" in norm:
            return "diploma_last_name"
        if "диплом" in norm:
            if "серия" in norm:
                return "diploma_series"
            if "регистрацион" in norm:
                return "diploma_reg_number"
            if "номер" in norm:
                return "diploma_number"
            if "дата" in norm:
                return "diploma_issue_date"
        if "отчеств" in norm:
            return "patronymic"
        if "фамил" in norm:
            return "last_name"
        if "имя" in norm:
            return "first_name"
        if any(f in norm for f in ("фио", "слушатель", "студент")):
            return "name"

    if file_type == "users" or file_type is None:
        if file_type == "users":
            if any(r in norm for r in ("роль", "role")):
                return "role"
            if any(t in norm for t in ("команд", "отдел", "подраздел", "team", "department")):
                return "team"

        # Separate FIO components (with exclusions for case forms and diploma fields)
        if any(s in norm for s in ("фамилия", "last_name", "surname")):
            if not any(ex in norm for ex in ("диплом", "падеж")):
                return "last_name"
            return None
        if any(p in norm for p in ("отчество", "patronymic")):
            if not any(ex in norm for ex in ("диплом", "падеж")):
                return "patronymic"
            return None
        if any(f in norm for f in ("имя", "first_name")):
            if not any(ex in norm for ex in ("диплом", "падеж")):
                return "first_name"
            return None

        if file_type == "users" and any(f in norm for f in ("фио", "сотрудник", "пользователь")):
            return "name"


    if file_type == "vendors":
        if any(p in norm for p in ("продукт", "программ", "софт", "software")) or re.search(r"\bпо\b", norm) or norm in ("по", "по/продукт", "ит-по"):
            return "product"
        if any(k in norm for k in ("контакт", "представител", "фио", "лицо")):
            return "contact_name"
        if any(v in norm for v in ("вендор", "компан", "производ", "поставщик", "разработчик")):
            return "vendor"

    for field, synonyms in COLUMN_SYNONYMS.items():
        if norm in synonyms or norm_clean in synonyms:
            return field

    # Priority semantic dispatch for ambiguous compound phrases
    if any(k in norm for k in ("куратор", "представитель", "контакт", "фио", "ответственн")):
        if any(m in norm for m in ("менеджер", "руководител", "owner")):
            return "manager"
        return "contact_name"

    # License signing date: must have license/contract context or specific signing phrase
    if any(k in norm for k in ("подписан", "заключен")):
        if "договор" in norm or "контракт" in norm:
            if "номер" in norm or "№" in norm or norm in ("договор", "контракт"):
                return "contract_number"
            return None
        if "лицензи" in norm:
            return "license_signed_on"
    if "дата" in norm and "лицензи" in norm:
        return "license_signed_on"

    # License term years: must have "срок"
    if "срок" in norm and any(w in norm for w in ("лицензи", "действи", "год", "лет")):
        return "license_term_years"

    # License transfer status: must have transfer/delivery or license status context
    if any(k in norm for k in ("передач", "передать", "передано")):
        return "license_transfer_status"
    if "статус" in norm and "лицензи" in norm:
        return "license_transfer_status"

    matches = []
    for field, synonyms in COLUMN_SYNONYMS.items():
        for syn in synonyms:
            if len(syn) <= 3:
                if re.search(r"(?:\b|_)" + re.escape(syn) + r"(?:\b|_)", norm):
                    if syn == "по":
                        if norm in ("по", "по (ит-продукт)", "по/продукт", "ит-по") or any(
                            w in norm for w in ("программ", "продукт", "вендор", "лицензи")
                        ):
                            matches.append((len(syn), field))
                    elif syn in ("тип", "оу"):
                        matches.append((len(syn), field))
            else:
                if syn in norm:
                    if syn in ("статус", "срок", "договор") and not any(w in norm for w in ("лицензи", "передач", "действи", "номер")):
                        continue
                    matches.append((len(syn), field))
                elif norm in syn and len(norm) >= 5:
                    matches.append((len(norm), field))
    if matches:
        matches.sort(key=lambda m: m[0], reverse=True)
        return matches[0][1]
    return None


def _find_organization(db: Session, name: str) -> Organization | None:
    if not name:
        return None
    name_norm = name.strip().lower().strip("\"'«»")
    for obj in db.new:
        if isinstance(obj, Organization):
            if obj.name and (obj.name == name or obj.name.strip().lower().strip("\"'«»") == name_norm or (obj.id and obj.id.lower() == name_norm)):
                return obj
    org = db.scalar(select(Organization).where(Organization.name == name))
    if org is not None:
        return org
    for o in db.scalars(select(Organization)).all():
        if o.name.strip().lower().strip("\"'«»") == name_norm or (o.id and o.id.lower() == name_norm):
            return o
    return None


def _find_program(db: Session, name: str) -> Program | None:
    if not name:
        return None
    name_norm = name.strip().lower().strip("\"'«»")
    for obj in db.new:
        if isinstance(obj, Program):
            if obj.name and (obj.name == name or obj.name.strip().lower().strip("\"'«»") == name_norm or (obj.id and obj.id.lower() == name_norm)):
                return obj
    prog = db.scalar(select(Program).where(Program.name == name))
    if prog is not None:
        return prog
    for p in db.scalars(select(Program)).all():
        if p.name.strip().lower().strip("\"'«»") == name_norm or (p.id and p.id.lower() == name_norm):
            return p
    return None


def _find_product(db: Session, name: str) -> Product | None:
    if not name:
        return None
    name_norm = name.strip().lower().strip("\"'«»")
    for obj in db.new:
        if isinstance(obj, Product):
            if obj.name and (obj.name == name or obj.name.strip().lower().strip("\"'«»") == name_norm or (obj.id and obj.id.lower() == name_norm)):
                return obj
    prod = db.scalar(select(Product).where(Product.name == name))
    if prod is not None:
        return prod
    for p in db.scalars(select(Product)).all():
        if p.name.strip().lower().strip("\"'«»") == name_norm or (p.id and p.id.lower() == name_norm):
            return p
    return None


def _find_team(db: Session, name: str) -> Team | None:
    if not name:
        return None
    norm = name.strip().lower()
    for obj in db.new:
        if isinstance(obj, Team):
            if (obj.name and obj.name.strip().lower() == norm) or (obj.id and obj.id.lower() == norm):
                return obj
    t = db.scalar(select(Team).where(Team.name == name)) or db.get(Team, name)
    if t is not None:
        return t
    for item in db.scalars(select(Team)).all():
        if item.name.strip().lower() == norm or (item.id and item.id.lower() == norm):
            return item
    return None


def _find_user_by_email_or_name(db: Session, email: str, name: str | None = None) -> User | None:
    if not email and not name:
        return None
    e_norm = email.strip().lower() if email else ""
    n_norm = name.strip().lower() if name else ""

    if e_norm:
        for obj in db.new:
            if isinstance(obj, User):
                subj = (obj.keycloak_subject or "").strip().lower()
                uid = (obj.id or "").strip().lower()
                if subj == e_norm or uid == e_norm:
                    return obj
    if n_norm:
        for obj in db.new:
            if isinstance(obj, User):
                if obj.name and obj.name.strip().lower() == n_norm:
                    return obj

    users = list(db.scalars(select(User)))
    # 1. Authoritative lookup by email / login first across all users
    if e_norm:
        for u in users:
            subj = (u.keycloak_subject or "").strip().lower()
            uid = (u.id or "").strip().lower()
            if subj == e_norm or uid == e_norm:
                return u
    # 2. Fallback to name only if no email match was found
    if n_norm:
        for u in users:
            if u.name and u.name.strip().lower() == n_norm:
                return u
    return None


def _extract_contact_details(val: str) -> dict[str, str | None]:
    if not val:
        return {"name": "", "position": None, "email": None, "phone": None}
    raw = val.strip()
    email_m = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", raw)
    email = email_m.group(0) if email_m else None
    cleaned = re.sub(r"[\w\.-]+@[\w\.-]+\.\w+", "", raw)
    phone_m = re.search(r"(?:\+7|8|7)[\d\s\(\)-]{9,18}\d", cleaned)
    phone = phone_m.group(0).strip() if phone_m else None
    if phone:
        cleaned = cleaned.replace(phone, "")
    pos = None
    pos_m = re.search(r"\(([^)]+)\)", cleaned)
    if pos_m:
        inside = pos_m.group(1).strip()
        if not re.search(r"[\w\.-]+@[\w\.-]+\.\w+", inside) and not re.search(r"\d{3,}", inside):
            pos = inside
            cleaned = cleaned.replace(pos_m.group(0), "")
    cleaned = re.sub(r"[\(\)\[\]]", " ", cleaned).strip()
    parts = [p.strip() for p in re.split(r"[,;—/:]+", cleaned) if p.strip()]
    name = parts[0] if parts else raw
    if not pos and len(parts) > 1:
        pos = parts[1]
    return {"name": name, "position": pos, "email": email, "phone": phone}


def _find_contact(db: Session, org_id: str, contact_name: str) -> OrganizationContact | None:
    if not contact_name:
        return None
    extracted = _extract_contact_details(contact_name)
    search_name = extracted["name"] or contact_name
    contact = db.scalar(
        select(OrganizationContact).where(
            OrganizationContact.organization_id == org_id,
            OrganizationContact.full_name == search_name.strip(),
        )
    )
    if contact is not None:
        return contact
    c_norm = search_name.strip().lower()
    c_tokens = set(c_norm.split())
    for c in db.scalars(select(OrganizationContact).where(OrganizationContact.organization_id == org_id)).all():
        c_db_norm = c.full_name.strip().lower()
        if c_db_norm == c_norm or set(c_db_norm.split()) == c_tokens:
            return c
    return None


def _col_letter_to_index(col_str: str) -> int:
    idx = 0
    for ch in col_str.upper():
        if "A" <= ch <= "Z":
            idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return max(0, idx - 1)


def parse_xlsx_stdlib(data: bytes) -> list[list[str]]:
    """Parses XLSX spreadsheet via stdlib zipfile and xml.etree.ElementTree."""
    zf = zipfile.ZipFile(io.BytesIO(data))
    shared: list[str] = []
    if "xl/sharedStrings.xml" in zf.namelist():
        tree = ET.fromstring(zf.read("xl/sharedStrings.xml"))
        ns_url = tree.tag.split("}")[0][1:] if tree.tag.startswith("{") else "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        ns = {"ns": ns_url}
        for si in tree.findall(".//ns:si", ns):
            text_parts = [t.text for t in si.findall(".//ns:t", ns) if t.text]
            shared.append("".join(text_parts))

    # Look for sheet1.xml
    sheet_name = "xl/worksheets/sheet1.xml"
    if sheet_name not in zf.namelist():
        # Fallback to first worksheet with natural numerical sorting
        ws = [n for n in zf.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")]
        if not ws:
            raise APIError("FILE_TYPE_NOT_ALLOWED", "Лист таблицы не найден в XLSX файле.", 422)
        ws.sort(key=lambda s: [int(t) if t.isdigit() else t for t in re.split(r'(\d+)', s)])
        sheet_name = ws[0]

    tree = ET.fromstring(zf.read(sheet_name))
    ns_url = tree.tag.split("}")[0][1:] if tree.tag.startswith("{") else "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    ns = {"ns": ns_url}
    rows: list[list[str]] = []

    for row_el in tree.findall(".//ns:row", ns):
        row_vals: list[str] = []
        for cell in row_el.findall("ns:c", ns):
            r_attr = cell.get("r", "")
            col_letters = "".join(filter(str.isalpha, r_attr))
            target_idx = _col_letter_to_index(col_letters) if col_letters else len(row_vals)

            while len(row_vals) < target_idx:
                row_vals.append("")

            cell_type = cell.get("t")
            v = cell.find("ns:v", ns)
            val = ""
            if cell_type == "s" and v is not None and v.text:
                idx = int(v.text)
                val = shared[idx] if idx < len(shared) else ""
            elif cell_type == "inlineStr":
                text_parts = [t.text for t in cell.findall(".//ns:t", ns) if t.text]
                val = "".join(text_parts)
            elif cell_type == "b" and v is not None and v.text:
                val = "1" if v.text == "1" else "0"
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
    if first_line.count("\t") > first_line.count(";") and first_line.count("\t") > first_line.count(","):
        delimiter = "\t"
    elif first_line.count(";") > first_line.count(","):
        delimiter = ";"
    else:
        delimiter = ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    return [row for row in reader if any(cell.strip() for cell in row)]


def _decode_rk(rk: int) -> float | int:
    if rk & 2:
        val = rk >> 2
        if val & 0x20000000:
            val -= 0x40000000
        if rk & 1:
            val /= 100
        return val
    else:
        raw = struct.pack("<Q", (rk & 0xFFFFFFFC) << 32)
        val = struct.unpack("<d", raw)[0]
        if rk & 1:
            val /= 100
        return int(val) if val.is_integer() else val


def parse_biff8_stdlib(data: bytes) -> list[list[str]]:
    """Parses binary Excel 97-2003 .xls (BIFF8) spreadsheet via pure stdlib struct."""
    if not data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        raise APIError("FILE_TYPE_NOT_ALLOWED", "Некорректная сигнатура OLE2 в XLS файле.", 422)

    sec_shift = struct.unpack_from("<H", data, 30)[0]
    sec_size = 1 << sec_shift if sec_shift else 512
    num_fat_sectors = struct.unpack_from("<I", data, 44)[0]
    first_dir_sector = struct.unpack_from("<I", data, 48)[0]
    first_minifat_sector = struct.unpack_from("<I", data, 60)[0]

    fat_sector_ids: list[int] = []
    for i in range(min(num_fat_sectors, 109)):
        sid = struct.unpack_from("<I", data, 76 + i * 4)[0]
        if sid < 0xFFFFFFFE:
            fat_sector_ids.append(sid)

    fat: list[int] = []
    for sid in fat_sector_ids:
        offset = (sid + 1) * sec_size
        if offset + sec_size <= len(data):
            entries = struct.unpack(f"<{sec_size // 4}I", data[offset : offset + sec_size])
            fat.extend(entries)

    def read_chain(start_sid: int, s_size: int = sec_size, fat_table: list[int] = fat, src: bytes = data, is_mini: bool = False, mini_buf: bytes = b"") -> bytes:
        out: list[bytes] = []
        sid = start_sid
        visited: set[int] = set()
        while sid < 0xFFFFFFFE and sid not in visited:
            visited.add(sid)
            if is_mini:
                off = sid * s_size
                if off + s_size <= len(mini_buf):
                    out.append(mini_buf[off : off + s_size])
                elif off < len(mini_buf):
                    out.append(mini_buf[off:])
            else:
                off = (sid + 1) * s_size
                if off + s_size <= len(src):
                    out.append(src[off : off + s_size])
                elif off < len(src):
                    out.append(src[off:])
            if sid < len(fat_table):
                sid = fat_table[sid]
            else:
                break
        return b"".join(out)

    dir_data = read_chain(first_dir_sector)
    entries: list[dict[str, Any]] = []
    for i in range(0, len(dir_data), 128):
        chunk = dir_data[i : i + 128]
        if len(chunk) < 128:
            break
        name_len = struct.unpack_from("<H", chunk, 64)[0]
        name = ""
        if name_len > 2:
            name = chunk[: name_len - 2].decode("utf-16le", errors="replace")
        entries.append({
            "name": name,
            "type": chunk[66],
            "start_sid": struct.unpack_from("<I", chunk, 116)[0],
            "size": struct.unpack_from("<Q", chunk, 120)[0],
        })

    root_entry = entries[0] if entries else None
    mini_stream = b""
    if root_entry and root_entry["start_sid"] < 0xFFFFFFFE:
        mini_stream = read_chain(root_entry["start_sid"])[: root_entry["size"]]

    minifat: list[int] = []
    if first_minifat_sector < 0xFFFFFFFE:
        mb = read_chain(first_minifat_sector)
        if len(mb) >= 4:
            minifat = list(struct.unpack(f"<{len(mb) // 4}I", mb))

    wb_entry = None
    for e in entries:
        if e["name"].lower() in ("workbook", "book"):
            wb_entry = e
            break
    if not wb_entry:
        raise APIError("FILE_TYPE_NOT_ALLOWED", "Поток Workbook не найден в XLS файле.", 422)

    if wb_entry["size"] < 4096 and mini_stream and minifat:
        wb_data = read_chain(wb_entry["start_sid"], s_size=64, fat_table=minifat, is_mini=True, mini_buf=mini_stream)[: wb_entry["size"]]
    else:
        wb_data = read_chain(wb_entry["start_sid"])[: wb_entry["size"]]

    records: list[tuple[int, bytes]] = []
    pos = 0
    while pos + 4 <= len(wb_data):
        rec_type, rec_len = struct.unpack_from("<HH", wb_data, pos)
        pos += 4
        rec_data = wb_data[pos : pos + rec_len]
        pos += rec_len
        records.append((rec_type, rec_data))

    sst_bytes = bytearray()
    i = 0
    while i < len(records):
        rec_type, rec_data = records[i]
        if rec_type == 0x00FC:
            sst_bytes.extend(rec_data)
            j = i + 1
            while j < len(records) and records[j][0] == 0x003C:
                sst_bytes.extend(records[j][1])
                j += 1
            break
        i += 1

    sst: list[str] = []
    if len(sst_bytes) >= 8:
        unique_count = struct.unpack_from("<I", sst_bytes, 4)[0]
        sp = 8
        for _ in range(unique_count):
            if sp >= len(sst_bytes):
                break
            cch = struct.unpack_from("<H", sst_bytes, sp)[0]
            flags = sst_bytes[sp + 2]
            sp += 3
            is_utf16 = bool(flags & 0x01)
            has_rich = bool(flags & 0x08)
            has_phonetic = bool(flags & 0x04)
            rt_runs = struct.unpack_from("<H", sst_bytes, sp)[0] if has_rich else 0
            if has_rich:
                sp += 2
            cb_ext = struct.unpack_from("<I", sst_bytes, sp)[0] if has_phonetic else 0
            if has_phonetic:
                sp += 4
            str_bytes = cch * 2 if is_utf16 else cch
            raw = sst_bytes[sp : sp + str_bytes]
            sp += str_bytes + (rt_runs * 4) + cb_ext
            sst.append(raw.decode("utf-16le" if is_utf16 else "latin-1", errors="replace"))

    cells: dict[tuple[int, int], str] = {}
    for rec_type, rec_data in records:
        if rec_type == 0x00FD and len(rec_data) >= 10:  # LABELSST
            r, c, xf, s_idx = struct.unpack_from("<HHHI", rec_data, 0)
            cells[(r, c)] = sst[s_idx] if s_idx < len(sst) else ""
        elif rec_type == 0x0204 and len(rec_data) >= 9:  # LABEL
            r, c, xf = struct.unpack_from("<HHH", rec_data, 0)
            cch = struct.unpack_from("<H", rec_data, 6)[0]
            flags = rec_data[8]
            is_utf16 = bool(flags & 0x01)
            raw_s = rec_data[9 : 9 + (cch * 2 if is_utf16 else cch)]
            cells[(r, c)] = raw_s.decode("utf-16le" if is_utf16 else "latin-1", errors="replace")
        elif rec_type == 0x0203 and len(rec_data) >= 14:  # NUMBER
            r, c, xf = struct.unpack_from("<HHH", rec_data, 0)
            num = struct.unpack_from("<d", rec_data, 6)[0]
            cells[(r, c)] = str(int(num)) if num.is_integer() else str(num)
        elif rec_type == 0x027E and len(rec_data) >= 10:  # RK
            r, c, xf, rk = struct.unpack_from("<HHHI", rec_data, 0)
            cells[(r, c)] = str(_decode_rk(rk))
        elif rec_type == 0x00BD and len(rec_data) >= 6:  # MULRK
            r, first_col = struct.unpack_from("<HH", rec_data, 0)
            last_col = struct.unpack_from("<H", rec_data, len(rec_data) - 2)[0]
            col_count = last_col - first_col + 1
            for c in range(col_count):
                if 4 + c * 6 + 6 <= len(rec_data):
                    xf, rk = struct.unpack_from("<HI", rec_data, 4 + c * 6)
                    cells[(r, first_col + c)] = str(_decode_rk(rk))

    if not cells:
        return []
    max_r = max(r for r, c in cells.keys())
    max_c = max(c for r, c in cells.keys())
    grid: list[list[str]] = []
    for r in range(max_r + 1):
        row = [cells.get((r, c), "") for c in range(max_c + 1)]
        if any(cell.strip() for cell in row):
            grid.append(row)
    return grid


def parse_tabular_file(data: bytes, filename: str | None = None, import_type: str | None = None) -> list[dict[str, str]]:
    """Parses uploaded tabular file (CSV, XLSX, or XLS) into a list of normalized row dictionaries."""
    fn_lower = (filename or "").lower()
    if fn_lower.endswith(".xlsx") or data.startswith(b"PK\x03\x04"):
        raw_rows = parse_xlsx_stdlib(data)
    elif fn_lower.endswith(".xls") or data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        raw_rows = parse_biff8_stdlib(data)
    else:
        raw_rows = parse_csv_stdlib(data)

    if not raw_rows:
        return []

    header_row = raw_rows[0]
    file_type = import_type if (import_type and import_type in ("organizations", "vendors", "users", "lms_learners")) else _detect_file_type(header_row, filename=filename)

    col_mapping: dict[int, str] = {}
    for idx, col_name in enumerate(header_row):
        matched = _match_header(col_name, file_type=file_type)
        if matched:
            col_mapping[idx] = matched

    if not col_mapping:
        raise APIError(
            "VALIDATION_ERROR",
            "Не удалось распознать заголовки колонок в таблице. Ожидаются: Название вуза, Вендор, ПО или ФИО/Роль.",
            422,
        )

    parsed_rows: list[dict[str, str]] = []
    for row in raw_rows[1:]:
        row_dict: dict[str, str] = {}
        for idx, val in enumerate(row):
            if idx in col_mapping:
                row_dict[col_mapping[idx]] = val.strip()
        if any(v for k, v in row_dict.items() if k != "_file_type"):
            row_dict["_file_type"] = file_type
            if file_type == "vendors":
                if "vendor" in row_dict and "name" not in row_dict:
                    row_dict["name"] = row_dict["vendor"]
                if "product" in row_dict:
                    row_dict["products"] = _parse_product_names(row_dict["product"])
            elif file_type == "users":
                if "contact_name" in row_dict and "name" not in row_dict:
                    row_dict["name"] = row_dict["contact_name"]

                full_name = " ".join(
                    filter(None, [row_dict.get("last_name"), row_dict.get("first_name"), row_dict.get("patronymic")])
                ).strip()
                if full_name:
                    row_dict["name"] = full_name
                    row_dict["full_name"] = full_name

                if not row_dict.get("role"):
                    row_dict["role"] = "manager"

                if "phone" in row_dict and row_dict["phone"]:
                    digits_phone = re.sub(r"\D", "", row_dict["phone"])
                    if digits_phone:
                        row_dict["phone"] = digits_phone
            elif file_type == "lms_learners":
                full_name = " ".join(
                    filter(None, [row_dict.get("last_name"), row_dict.get("first_name"), row_dict.get("patronymic")])
                ).strip()
                if full_name:
                    row_dict["name"] = full_name
                    row_dict["full_name"] = full_name

                if not row_dict.get("role"):
                    row_dict["role"] = "learner"

                if "phone" in row_dict and row_dict["phone"]:
                    digits_phone = re.sub(r"\D", "", row_dict["phone"])
                    if digits_phone:
                        row_dict["phone"] = digits_phone

            parsed_rows.append(row_dict)

    return parsed_rows


def preview_organizations_import(
    db: Session,
    user: User,
    file_bytes: bytes,
    filename: str | None = None,
    import_type: str | None = None,
) -> dict:
    """Dry-run parse without DB mutation, returns preview rows, validation results, and diagnostic errors."""
    require_permission(user, "organizations.create")
    parsed_rows = parse_tabular_file(file_bytes, filename=filename, import_type=import_type)

    import_id = uuid4().hex
    preview_rows: list[dict] = []
    errors: list[dict] = []

    file_type = import_type if (import_type and import_type in ("organizations", "vendors", "users", "lms_learners")) else (
        parsed_rows[0].get("_file_type") if parsed_rows else _detect_file_type([], filename=filename)
    )

    payload_hash = hashlib.sha256(canonical_json(parsed_rows).encode("utf-8")).hexdigest()
    _IMPORT_PACKAGES[import_id] = {
        "hash": payload_hash,
        "rows": parsed_rows,
        "type": file_type,
        "user_id": user.id,
        "created_at": utcnow(),
    }

    if file_type == "lms_learners":
        from .integrations.service import process_lms_learners_file
        ingest_res = process_lms_learners_file(db, user, file_bytes, filename=filename)
        return {
            "status": "success",
            "import_id": import_id,
            "payload_hash": payload_hash,
            "import_type": "lms_learners",
            "detected_type": "lms_learners",
            "redirect": "/integrations",
            "message": "Распознан реестр слушателей LMS. Данные перенаправлены в подсистему Интеграций (IntegrationInbox). Учетные записи операторов CRM не затронуты.",
            "rows_total": len(parsed_rows),
            "total_rows": len(parsed_rows),
            "valid_count": len(parsed_rows),
            "valid_rows": len(parsed_rows),
            "error_count": 0,
            "preview_rows": [],
            "rows": [],
            "errors": [],
            "users_created": 0,
            "users_updated": 0,
            "ingest_result": ingest_res,
        }


    if file_type == "vendors":
        seen_vendors = set()
        for idx, row in enumerate(parsed_rows, start=1):
            row_errors: list[str] = []
            vendor = (row.get("vendor") or row.get("company") or "").strip()

            if not vendor:
                row_errors.append("Поле 'Вендор' обязательно для заполнения.")
                errors.append({"row": idx, "field": "vendor", "message": "Поле 'Вендор' обязательно."})

            v_lower = vendor.lower()
            status = "create"
            if vendor:
                existing = db.scalar(select(Organization).where(func.lower(Organization.name) == v_lower))
                if existing:
                    status = "update"
                    if not has_organization_access(db, user, existing.id):
                        row_errors.append("Нет прав на изменение существующей организации.")
                        errors.append({"row": idx, "field": "vendor", "message": "Нет прав на изменение существующей организации."})
                elif v_lower in seen_vendors:
                    status = "update"
                seen_vendors.add(v_lower)

            raw_prods = row.get("product") or row.get("products") or ""
            prod_list = _parse_product_names(raw_prods)

            contact_raw = row.get("contact_name") or ""
            contact_details = _extract_contact_details(contact_raw)
            clean_contact = contact_details["name"] or contact_raw
            pos = row.get("position") or contact_details["position"] or "Представитель вендора"
            email = row.get("email") or contact_details["email"]
            phone = row.get("phone") or contact_details["phone"]

            vendor_data = {
                "import_type": "vendors",
                "vendor": vendor,
                "name": vendor,
                "organization_name": vendor,
                "type": "vendor",
                "products": prod_list,
                "product": raw_prods,
                "contact_name": clean_contact,
                "position": pos,
                "contact_position": pos,
                "email": email,
                "contact_email": email,
                "phone": phone,
                "contact_phone": phone,
            }
            preview_rows.append({
                "row_index": idx,
                "row_number": idx,
                "status": status,
                "is_valid": len(row_errors) == 0,
                "errors": row_errors,
                "warnings": [],
                "organization_name": vendor,
                "org_type": "vendor",
                "vendor": vendor,
                "products": prod_list,
                "product_name": ", ".join(prod_list) if prod_list else "",
                "contact_name": clean_contact,
                "contact_position": pos,
                "contact_phone": phone,
                "contact_email": email,
                "phone": phone,
                "email": email,
                "data": vendor_data,
                "mapped_fields": vendor_data,
                "raw_values": vendor_data,
            })

    elif file_type == "users":
        seen_emails = set()
        for idx, row in enumerate(parsed_rows, start=1):
            row_errors: list[str] = []
            name = (row.get("name") or row.get("full_name") or "").strip()
            email = (row.get("email") or "").strip()
            phone = (row.get("phone") or "").strip()
            clean_phone = re.sub(r"\D", "", phone) if phone else ""
            raw_role = (row.get("role") or "manager").strip()
            team = (row.get("team") or row.get("department") or "").strip()

            if not name:
                row_errors.append("Поле 'ФИО' обязательно для заполнения.")
                errors.append({"row": idx, "field": "name", "message": "Поле 'ФИО' обязательно."})
            if not email:
                row_errors.append("Поле 'Email' обязательно для заполнения.")
                errors.append({"row": idx, "field": "email", "message": "Поле 'Email' обязательно."})
            elif "@" not in email:
                row_errors.append(f"Некорректный email '{email}'.")
                errors.append({"row": idx, "field": "email", "message": f"Некорректный email '{email}'."})

            e_lower = email.lower()
            if e_lower in seen_emails:
                row_errors.append(f"Дубликат email '{email}' в загружаемом файле.")
                errors.append({"row": idx, "field": "email", "message": f"Дубликат '{email}' внутри файла."})
            elif email:
                seen_emails.add(e_lower)

            r_norm = raw_role.lower()
            if any(k in r_norm for k in ("руковод", "super", "начальник", "тимлид")):
                norm_role = "supervisor"
            elif any(k in r_norm for k in ("админ", "admin")):
                norm_role = "administrator"
            else:
                norm_role = "manager"

            status = "create"
            if email or name:
                existing = _find_user_by_email_or_name(db, email, name)
                if existing:
                    status = "update"

            user_data = {
                "import_type": "users",
                "name": name,
                "full_name": name,
                "email": email,
                "contact_email": email,
                "phone": clean_phone or phone,
                "contact_phone": clean_phone or phone,
                "role": norm_role,
                "team": team,
            }
            preview_rows.append({
                "row_index": idx,
                "row_number": idx,
                "status": status,
                "is_valid": len(row_errors) == 0,
                "errors": row_errors,
                "warnings": [],
                "organization_name": team or "CRM Пользователи",
                "org_type": "user",
                "full_name": name,
                "contact_name": name,
                "email": email,
                "contact_email": email,
                "phone": clean_phone or phone,
                "contact_phone": clean_phone or phone,
                "role": norm_role,
                "team": team,
                "data": user_data,
                "mapped_fields": user_data,
                "raw_values": user_data,
            })

    else:
        # Standard organizations import
        seen_names: set[str] = set()
        for idx, row in enumerate(parsed_rows, start=1):
            row_errors: list[str] = []
            name = row.get("name", "").strip()

            if not name:
                row_errors.append("Поле 'Название вуза' обязательно для заполнения.")
                errors.append({"row": idx, "field": "name", "message": "Поле 'Название вуза' обязательно."})

            name_lower = name.lower()
            if name_lower in seen_names:
                row_errors.append(f"Дубликат организации '{name}' в загружаемом файле.")
                errors.append({"row": idx, "field": "name", "message": f"Дубликат '{name}' внутри файла."})
            elif name:
                seen_names.add(name_lower)

            status = "create"
            if name:
                existing = _find_organization(db, name)
                if existing:
                    status = "update"
                    if not has_organization_access(db, user, existing.id):
                        row_errors.append("Нет прав на изменение существующей организации.")
                        errors.append({"row": idx, "field": "name", "message": "Нет прав на изменение существующей организации."})

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

            org_type = row.get("type", "university")
            if org_type not in {"university", "school", "other", "vendor"}:
                org_type = "university"

            contact_raw = row.get("contact_name") or ""
            contact_details = _extract_contact_details(contact_raw)
            contact_name = contact_details["name"] or contact_raw
            contact_pos = row.get("position") or contact_details["position"]
            contact_email = row.get("email") or contact_details["email"]
            contact_phone = row.get("phone") or contact_details["phone"]

            preview_rows.append({
                "row_index": idx,
                "row_number": idx,
                "status": status,
                "is_valid": len(row_errors) == 0,
                "errors": row_errors,
                "organization_name": name,
                "org_type": org_type,
                "manager": row.get("manager"),
                "contact_name": contact_name,
                "program_name": row.get("program"),
                "product_name": row.get("product"),
                "data": {
                    "import_type": "organizations",
                    "name": name,
                    "organization_name": name,
                    "type": org_type,
                    "org_type": org_type,
                    "organization_type": org_type,
                    "manager": row.get("manager"),
                    "contact_name": contact_name,
                    "position": contact_pos,
                    "contact_position": contact_pos,
                    "email": contact_email,
                    "contact_email": contact_email,
                    "phone": contact_phone,
                    "contact_phone": contact_phone,
                    "program": row.get("program"),
                    "program_name": row.get("program"),
                    "product": row.get("product"),
                    "product_name": row.get("product"),
                    "vendor": row.get("vendor"),
                    "contract_number": row.get("contract_number"),
                    "license_signed_on": row.get("license_signed_on"),
                    "license_term_years": row.get("license_term_years"),
                    "license_transfer_status": row.get("license_transfer_status"),
                    "comment": row.get("comment"),
                },
            })

    valid_count = sum(1 for r in preview_rows if r["is_valid"])
    error_count = sum(1 for r in preview_rows if not r["is_valid"])

    return {
        "status": "success",
        "import_id": import_id,
        "payload_hash": payload_hash,
        "import_type": file_type,
        "detected_type": file_type,
        "rows_total": len(preview_rows),
        "total_rows": len(preview_rows),
        "valid_count": valid_count,
        "valid_rows": valid_count,
        "error_count": error_count,
        "preview_rows": preview_rows,
        "rows": preview_rows,
        "errors": errors,
    }


def commit_organizations_import(
    db: Session,
    user: User,
    rows: list[dict],
    idempotency_key: str | None = None,
    import_type: str | None = None,
    filename: str | None = None,
    import_id: str | None = None,
) -> dict:
    """Atomic transactional creation of Organizations, Vendors, Products, Users, Contacts, Contracts, Licenses protected by Idempotency-Key."""
    require_permission(user, "organizations.create")

    if import_id:
        pkg = _IMPORT_PACKAGES.get(import_id)
        if not pkg:
            raise APIError("IMPORT_PACKAGE_NOT_FOUND", "Пакет импорта не найден или истек срок действия.", 404)
        if pkg["user_id"] != user.id and user.role != "administrator":
            raise APIError("FORBIDDEN", "Пакет принадлежит другому пользователю.", 403)
        if rows:
            curr_hash = hashlib.sha256(canonical_json(rows).encode("utf-8")).hexdigest()
            if curr_hash != pkg["hash"]:
                raise APIError("IMPORT_PACKAGE_TAMPERED", "Содержимое пакета импорта было изменено после проверки (Package Tampered).", 409)
        else:
            rows = pkg["rows"]
        if not import_type:
            import_type = pkg.get("type")

    body_dict = {"rows": rows, "import_type": import_type, "filename": filename, "import_id": import_id}
    saved, replay = begin_command(db, user, "import_organizations", idempotency_key, body_dict)
    if replay is not None:
        return replay

    created_orgs = 0
    updated_orgs = 0
    created_contacts = 0
    created_contracts = 0
    created_licenses = 0
    created_products = 0
    created_users = 0
    updated_users = 0
    created_vendors = 0
    errors: list[dict] = []

    first_row = rows[0] if rows else {}
    first_data = first_row.get("data") or first_row.get("mapped_fields") or first_row.get("raw_values") or first_row
    file_type = import_type or first_data.get("import_type") or first_data.get("_file_type")
    if not file_type and filename:
        detected = _detect_file_type([], filename=filename)
        if detected != "organizations":
            file_type = detected
    if not file_type:
        is_learner = (
            first_data.get("_file_type") == "lms_learners"
            or any(k in first_data for k in ("snils", "passport_series", "passport_number", "first_name_dative"))
        )
        is_user = (
            first_data.get("org_type") == "user"
            or "role" in first_data
            or ("email" in first_data and ("full_name" in first_data or "name" in first_data))
        )
        is_vendor = (
            first_data.get("type") == "vendor"
            or first_data.get("org_type") == "vendor"
            or "vendor" in first_data
            or "products" in first_data
        ) and not any(k in first_data for k in ("program", "contract_number", "license_signed_on"))
        if is_learner:
            file_type = "lms_learners"
        elif is_user:
            file_type = "users"
        elif is_vendor:
            file_type = "vendors"
        else:
            file_type = "organizations"

    try:
        if file_type == "lms_learners":
            result = {
                "status": "committed",
                "success": True,
                "import_type": "lms_learners",
                "detected_type": "lms_learners",
                "rows_total": len(rows),
                "imported_count": 0,
                "created_count": 0,
                "created_organizations": 0,
                "updated_organizations": 0,
                "created_contacts": 0,
                "created_contracts": 0,
                "created_licenses": 0,
                "created_products": 0,
                "created_users": 0,
                "updated_users": 0,
                "created_vendors": 0,
                "details": {
                    "products_created": 0,
                    "vendors_created": 0,
                    "organizations_created": 0,
                    "users_created": 0,
                },
                "errors": [],
                "message": "Распознан реестр слушателей LMS. Данные перенаправлены в подсистему Интеграций (IntegrationInbox). Учетные записи операторов CRM не затронуты.",
            }
            return finish_command(db, saved, result, None)

        if file_type == "vendors":
            for idx, row in enumerate(rows, start=1):
                data = row.get("data") or row.get("mapped_fields") or row.get("raw_values") or row
                vendor_name = (data.get("vendor") or data.get("company") or data.get("name") or data.get("organization_name") or row.get("vendor") or row.get("organization_name") or "").strip()
                if not vendor_name:
                    raise APIError("VALIDATION_ERROR", f"Строка {idx}: поле 'Вендор' обязательно для заполнения.", 422)

                vendor_org = _find_organization(db, vendor_name)
                if not vendor_org:
                    vendor_org = Organization(name=vendor_name, type="vendor", owner_id=user.id if user.role == "manager" else None)
                    db.add(vendor_org)
                    db.flush()
                    created_orgs += 1
                    created_vendors += 1
                    access = OrganizationAccess(organization_id=vendor_org.id, user_id=user.id, read_all=True, can_create=True)
                    db.add(access)
                else:
                    if not has_organization_access(db, user, vendor_org.id):
                        errors.append({"row": idx, "message": "Нет прав на изменение существующей организации."})
                        continue
                    updated_orgs += 1
                    if vendor_org.type != "vendor":
                        vendor_org.type = "vendor"

                contact_raw = data.get("contact_name") or data.get("contact") or ""
                if contact_raw.strip():
                    contact_details = _extract_contact_details(contact_raw)
                    clean_contact = contact_details["name"] or contact_raw.strip()
                    pos = data.get("position") or data.get("contact_position") or contact_details["position"] or "Представитель вендора"
                    ph = data.get("phone") or data.get("contact_phone") or contact_details["phone"]
                    em = data.get("email") or data.get("contact_email") or contact_details["email"]

                    existing_c = _find_contact(db, vendor_org.id, clean_contact)
                    if not existing_c:
                        new_c = OrganizationContact(
                            organization_id=vendor_org.id,
                            full_name=clean_contact,
                            position=pos,
                            email=em,
                            phone=ph,
                            active=True,
                        )
                        db.add(new_c)
                        created_contacts += 1
                    else:
                        if ph and not existing_c.phone:
                            existing_c.phone = ph
                        if em and not existing_c.email:
                            existing_c.email = em

                raw_prods = data.get("products") or data.get("product") or ""
                prod_names = raw_prods if isinstance(raw_prods, list) else _parse_product_names(str(raw_prods))
                for p_name in prod_names:
                    prod = _find_product(db, p_name)
                    if not prod:
                        prod = Product(
                            id=f"prod-{uuid4().hex[:8]}",
                            name=p_name,
                            vendor=vendor_name,
                        )
                        db.add(prod)
                        created_products += 1
                    else:
                        if not prod.vendor or prod.vendor != vendor_name:
                            prod.vendor = vendor_name

        elif file_type == "users":
            for idx, row in enumerate(rows, start=1):
                data = row.get("data") or row.get("mapped_fields") or row.get("raw_values") or row
                name = (data.get("name") or data.get("full_name") or "").strip()
                email = (data.get("email") or "").strip()
                phone = (data.get("phone") or data.get("contact_phone") or "").strip()
                clean_phone = re.sub(r"\D", "", phone) if phone else ""
                raw_role = (data.get("role") or "manager").strip()
                team_name = (data.get("team") or data.get("department") or "").strip()

                if not name:
                    raise APIError("VALIDATION_ERROR", f"Строка {idx}: поле 'ФИО' обязательно для заполнения.", 422)
                if not email or "@" not in email:
                    raise APIError("VALIDATION_ERROR", f"Строка {idx}: некорректный адрес email '{email}'.", 422)

                r_norm = raw_role.lower()
                if any(k in r_norm for k in ("руковод", "super", "начальник", "тимлид")):
                    norm_role = "supervisor"
                elif any(k in r_norm for k in ("админ", "admin")):
                    norm_role = "administrator"
                else:
                    norm_role = "manager"

                team_id = None
                if team_name:
                    t = _find_team(db, team_name)
                    if not t:
                        t = Team(id=f"team-{uuid4().hex[:8]}", name=team_name)
                        db.add(t)
                        db.flush()
                    team_id = t.id

                clean_email = email.lower()
                existing_u = _find_user_by_email_or_name(db, clean_email, name)
                if existing_u:
                    existing_u.name = name
                    existing_u.role = norm_role
                    if clean_phone:
                        existing_u.phone = clean_phone
                    if team_id:
                        existing_u.team_id = team_id
                    existing_u.active = True
                    updated_users += 1
                else:
                    slug = re.sub(r"[^a-zA-Z0-9_\-]+", "-", clean_email.split("@")[0]).strip("-")
                    uid = slug if slug and not db.get(User, slug) else f"user-{uuid4().hex[:8]}"
                    perms = [f"phone:{clean_phone}"] if clean_phone else []
                    new_u = User(
                        id=uid,
                        keycloak_subject=clean_email,
                        name=name,
                        role=norm_role,
                        team_id=team_id,
                        permissions=perms,
                        active=True,
                    )
                    if clean_phone:
                        new_u.phone = clean_phone
                    db.add(new_u)
                    created_users += 1


        else:
            # Standard organizations import
            for idx, row in enumerate(rows, start=1):
                data = row.get("data") or row.get("mapped_fields") or row.get("raw_values") or row
                name = (data.get("name") or data.get("organization_name") or "").strip()
                if not name:
                    raise APIError("VALIDATION_ERROR", f"Строка {idx}: поле 'Название вуза' обязательно для заполнения.", 422)

                org_type = data.get("type") or data.get("org_type") or "university"
                if org_type not in {"university", "school", "other", "vendor"}:
                    org_type = "university"

                org = _find_organization(db, name)
                if not org:
                    org = Organization(name=name, type=org_type, owner_id=user.id if user.role == "manager" else None)
                    db.add(org)
                    db.flush()
                    created_orgs += 1
                    access = OrganizationAccess(organization_id=org.id, user_id=user.id, read_all=True, can_create=True)
                    db.add(access)
                else:
                    if not has_organization_access(db, user, org.id):
                        errors.append({"row": idx, "message": "Нет прав на изменение существующей организации."})
                        continue
                    updated_orgs += 1

                new_contact = None
                existing_contact = None
                contact_name = data.get("contact_name")
                if contact_name and contact_name.strip():
                    contact_details = _extract_contact_details(contact_name)
                    clean_name = contact_details["name"] or contact_name.strip()
                    pos = data.get("position") or data.get("contact_position") or contact_details["position"]
                    em = data.get("email") or data.get("contact_email") or contact_details["email"]
                    ph = data.get("phone") or data.get("contact_phone") or contact_details["phone"]

                    existing_contact = _find_contact(db, org.id, clean_name)
                    if not existing_contact:
                        new_contact = OrganizationContact(
                            organization_id=org.id,
                            full_name=clean_name,
                            position=pos or "Представитель",
                            email=em,
                            phone=ph,
                            active=True,
                        )
                        db.add(new_contact)
                        created_contacts += 1
                    else:
                        if pos and (not existing_contact.position or existing_contact.position in ("Представитель", "Сотрудник")):
                            existing_contact.position = pos
                        if em and not existing_contact.email:
                            existing_contact.email = em
                        if ph and not existing_contact.phone:
                            existing_contact.phone = ph

                new_contract = None
                existing_contract = None
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

                manager_name = data.get("manager")
                manager_user = _find_user(db, manager_name) if manager_name else None
                if manager_user and manager_user.id != user.id:
                    mgr_access = db.get(OrganizationAccess, (manager_user.id, org.id))
                    if not mgr_access:
                        db.add(OrganizationAccess(organization_id=org.id, user_id=manager_user.id, read_all=True, can_create=True))
                    else:
                        mgr_access.read_all = True
                        mgr_access.can_create = True

                interaction = db.scalar(
                    select(Interaction)
                    .where(
                        Interaction.organization_id == org.id,
                        Interaction.state.not_in(TERMINAL_STATES),
                    )
                    .order_by(Interaction.created_at.desc())
                )
                if not interaction:
                    interaction = db.scalar(
                        select(Interaction)
                        .where(Interaction.organization_id == org.id)
                        .order_by(Interaction.created_at.desc())
                    )

                if manager_user and interaction and interaction.owner_id != manager_user.id and interaction.state not in TERMINAL_STATES:
                    old_owner = interaction.owner_id
                    interaction.owner_id = manager_user.id
                    if manager_user.team_id:
                        interaction.team_id = manager_user.team_id
                    append_event(
                        db,
                        interaction,
                        user,
                        "owner_changed",
                        utcnow(),
                        owner_id=manager_user.id,
                        previous_owner_id=old_owner,
                        comment="Импорт из файла",
                    )

                prod_name = data.get("product")
                vendor_name = data.get("vendor")
                license_signed = data.get("license_signed_on")
                license_term = data.get("license_term_years")
                license_status = data.get("license_transfer_status")

                prod = _find_product(db, prod_name) if prod_name else None
                if not prod and prod_name:
                    prod = Product(id=f"prod-{uuid4().hex[:8]}", name=prod_name, vendor=vendor_name or "Ростелеком")
                    db.add(prod)
                    db.flush()
                elif prod and vendor_name and not prod.vendor:
                    prod.vendor = vendor_name

                license_to_link = None
                if prod or license_signed or license_term or license_status:
                    target_prod = prod
                    if not target_prod and interaction and interaction.product_id:
                        target_prod = db.get(Product, interaction.product_id)
                    if not target_prod and data.get("program"):
                        prog = _find_program(db, data.get("program"))
                        if prog:
                            linked_prod_id = db.scalar(
                                select(ProgramProduct.product_id).where(ProgramProduct.program_id == prog.id)
                            )
                            if linked_prod_id:
                                target_prod = db.get(Product, linked_prod_id)
                    if not target_prod and vendor_name:
                        target_prod = db.scalar(select(Product).where(Product.vendor == vendor_name))
                    if not target_prod:
                        target_prod = db.scalar(select(Product))

                    if target_prod:
                        signed_on_dt = _parse_date(license_signed)
                        term_years_val = _parse_term_years(license_term)
                        contract_id = new_contract.id if new_contract else (existing_contract.id if existing_contract else None)

                        existing_license = db.scalar(
                            select(License).where(
                                License.organization_id == org.id,
                                License.product_id == target_prod.id,
                            )
                        )
                        if not existing_license:
                            new_license = License(
                                organization_id=org.id,
                                product_id=target_prod.id,
                                contract_id=contract_id,
                                signed_on=signed_on_dt,
                                term_years=term_years_val,
                                transfer_status=license_status or "pending",
                            )
                            db.add(new_license)
                            created_licenses += 1
                            license_to_link = new_license
                        else:
                            if contract_id and not existing_license.contract_id:
                                existing_license.contract_id = contract_id
                            if signed_on_dt:
                                existing_license.signed_on = signed_on_dt
                            if term_years_val is not None:
                                existing_license.term_years = term_years_val
                            if license_status:
                                existing_license.transfer_status = license_status
                            license_to_link = existing_license

                comment_text = (data.get("comment") or "").strip()
                contact_record = new_contact or existing_contact
                if comment_text and contact_record and not contact_record.notes:
                    contact_record.notes = comment_text

                if interaction:
                    prog_name_in_row = data.get("program") or data.get("program_name")
                    if prog_name_in_row and not interaction.program_id:
                        p_obj = _find_program(db, prog_name_in_row)
                        if p_obj:
                            interaction.program_id = p_obj.id

                    if comment_text:
                        already_commented = db.scalar(
                            select(Comment).where(
                                Comment.interaction_id == interaction.id,
                                Comment.body == comment_text,
                            )
                        )
                        if not already_commented:
                            comm = Comment(
                                id=new_id(),
                                interaction_id=interaction.id,
                                author_id=user.id,
                                author_name=user.name,
                                body=comment_text,
                                visit_id=interaction.visit_id,
                                created_at=utcnow(),
                            )
                            db.add(comm)
                            append_event(db, interaction, user, "comment_added", utcnow(), comment=comment_text, comment_id=comm.id)
                    if license_to_link and not interaction.license_id:
                        is_compatible = True
                        if interaction.product_id and license_to_link.product_id != interaction.product_id:
                            is_compatible = False
                        if interaction.program_id and not db.get(ProgramProduct, (interaction.program_id, license_to_link.product_id)):
                            is_compatible = False
                        if is_compatible:
                            interaction.license_id = license_to_link.id
                            if not interaction.product_id:
                                interaction.product_id = license_to_link.product_id
                    contract_ref = new_contract or existing_contract
                    if contract_ref and not interaction.contract_id:
                        interaction.contract_id = contract_ref.id
                    if contact_record and not interaction.contact_id:
                        interaction.contact_id = contact_record.id
                    interaction.updated_at = utcnow()

        db.flush()
    except Exception:
        db.rollback()
        raise

    tot_created = created_orgs + updated_orgs + created_users + updated_users + created_products
    result = {
        "status": "committed",
        "success": True,
        "import_type": file_type,
        "detected_type": file_type,
        "rows_total": len(rows),
        "imported_count": tot_created,
        "created_count": tot_created,
        "created_organizations": created_orgs,
        "updated_organizations": updated_orgs,
        "created_contacts": created_contacts,
        "created_contracts": created_contracts,
        "created_licenses": created_licenses,
        "created_products": created_products,
        "created_users": created_users,
        "updated_users": updated_users,
        "created_vendors": created_vendors,
        "details": {
            "products_created": created_products,
            "vendors_created": created_vendors,
            "organizations_created": created_orgs,
            "users_created": created_users,
        },
        "errors": errors,
    }

    return finish_command(db, saved, result, None)

