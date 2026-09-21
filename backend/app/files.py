from __future__ import annotations

import hashlib
from pathlib import Path, PurePath
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from .errors import APIError
from .models import Attachment, User
from .services import append_event, iso, scoped_interaction, utcnow

MAX_FILE_SIZE = 26_214_400  # 25 MB

ALLOWED_EXTENSIONS = {
    "png", "jpeg", "jpg", "pdf", "zip", "gzip", "gz", "rar", "doc", "docx", "xls", "xlsx"
}

MIME_TYPES = {
    "png": "image/png",
    "jpeg": "image/jpeg",
    "jpg": "image/jpeg",
    "pdf": "application/pdf",
    "zip": "application/zip",
    "gzip": "application/gzip",
    "gz": "application/gzip",
    "rar": "application/vnd.rar",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xls": "application/vnd.ms-excel",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

DANGEROUS_SIGNATURES = [
    b"MZ",                 # Windows PE EXE/DLL
    b"\x7fELF",            # Linux ELF executable
    b"#!",                 # Shell script
    b"<?php",              # PHP script
    b"<script",            # HTML/JS script
    b"\xca\xfe\xba\xbe",   # Java class / Mach-O fat
    b"\xfe\xed\xfa\xce",   # Mach-O 32-bit
    b"\xfe\xed\xfa\xcf",   # Mach-O 64-bit
]


def sanitize_filename(filename: str) -> tuple[str, str]:
    """Sanitizes filename against path traversal and validates whitelist extension."""
    if "\x00" in filename:
        raise APIError("FILE_TYPE_NOT_ALLOWED", "Недопустимое имя файла.", 422)
    cleaned = PurePath(filename.replace("\\", "/")).name.strip()
    if not cleaned or cleaned in {".", ".."}:
        raise APIError("FILE_TYPE_NOT_ALLOWED", "Недопустимое имя файла.", 422)
    ext = cleaned.rsplit(".", 1)[-1].lower() if "." in cleaned else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise APIError(
            "FILE_TYPE_NOT_ALLOWED",
            f"Формат файла '{ext}' не входит в перечень 10 разрешенных форматов: "
            "png, jpeg, pdf, zip, gzip, rar, doc, docx, xls, xlsx.",
            422,
        )
    return cleaned, ext


def validate_magic_bytes(ext: str, data: bytes) -> bool:
    """Validates that file magic bytes match declared format and contain no dangerous headers."""
    if len(data) < 2:
        return False
    for sig in DANGEROUS_SIGNATURES:
        if data.startswith(sig):
            return False

    norm = ext.lower()
    if norm == "png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if norm in {"jpg", "jpeg"}:
        return data.startswith(b"\xff\xd8\xff")
    if norm == "pdf":
        return data.startswith(b"%PDF-")
    if norm in {"gz", "gzip"}:
        return data.startswith(b"\x1f\x8b")
    if norm == "rar":
        return data.startswith(b"Rar!\x1a\x07")
    if norm in {"doc", "xls"}:
        return data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
    if norm in {"zip", "docx", "xlsx"}:
        return data.startswith(b"PK\x03\x04") or data.startswith(b"PK\x05\x06") or data.startswith(b"PK\x07\x08")
    return False


def save_attachment(
    db: Session,
    user: User,
    interaction_id: str,
    raw_filename: str,
    file_bytes: bytes,
    storage_dir: str = "storage",
    content_type_header: str | None = None,
) -> Attachment:
    """Validates format, size, magic bytes, stores to isolated directory under UUID, inserts record and audit event."""
    item = scoped_interaction(db, user, interaction_id)

    if len(file_bytes) > MAX_FILE_SIZE:
        raise APIError("FILE_TOO_LARGE", "Размер файла превышает допустимый лимит 25 МБ.", 413)

    clean_name, ext = sanitize_filename(raw_filename)

    if not validate_magic_bytes(ext, file_bytes):
        raise APIError(
            "FILE_TYPE_NOT_ALLOWED",
            f"Содержимое файла не соответствует заявленному типу '{ext}' или содержит исполняемый код.",
            422,
        )

    target_dir = Path(storage_dir) / "attachments" / item.id
    target_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid4().hex}.{ext}"
    stored_path = target_dir / stored_name
    stored_path.write_bytes(file_bytes)

    checksum = hashlib.sha256(file_bytes).hexdigest()
    content_type = MIME_TYPES.get(ext, content_type_header or "application/octet-stream")

    attachment = Attachment(
        interaction_id=item.id,
        visit_id=item.visit_id,
        file_name=clean_name,
        file_path=str(stored_path),
        file_size=len(file_bytes),
        content_type=content_type,
        checksum=checksum,
        uploaded_by=user.id,
        created_at=utcnow(),
    )
    db.add(attachment)
    db.flush()

    append_event(
        db,
        item,
        user,
        "attachment_uploaded",
        utcnow(),
        attachment_id=attachment.id,
        file_name=clean_name,
        file_size=len(file_bytes),
        checksum=checksum,
    )

    return attachment


def get_attachment_or_404(db: Session, user: User, interaction_id: str, attachment_id: str) -> Attachment:
    """Retrieves attachment ensuring scoped access; returns 404 if interaction or file not accessible."""
    item = scoped_interaction(db, user, interaction_id)
    attachment = db.scalar(
        select(Attachment).where(
            Attachment.id == attachment_id,
            Attachment.interaction_id == item.id,
        )
    )
    if not attachment or not Path(attachment.file_path).is_file():
        raise APIError("NOT_FOUND", "Вложение не найдено.", 404)
    return attachment


def list_interaction_attachments(db: Session, user: User, interaction_id: str) -> list[Attachment]:
    """Lists attachments for scoped interaction."""
    item = scoped_interaction(db, user, interaction_id)
    return list(
        db.scalars(
            select(Attachment)
            .where(Attachment.interaction_id == item.id)
            .order_by(Attachment.created_at)
        )
    )


def attachment_dict(att: Attachment) -> dict:
    return {
        "id": att.id,
        "interaction_id": att.interaction_id,
        "visit_id": att.visit_id,
        "file_name": att.file_name,
        "file_size": att.file_size,
        "content_type": att.content_type,
        "checksum": att.checksum,
        "uploaded_by": att.uploaded_by,
        "created_at": iso(att.created_at),
    }
