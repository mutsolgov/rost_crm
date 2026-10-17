"""Report generator and enterprise scalability verification suite."""
from app.files import ALLOWED_EXTENSIONS, sanitize_filename, validate_magic_bytes
from app.models import Interaction, User


def test_allowed_extensions_strictly_10_formats():
    expected = {"png", "jpeg", "pdf", "zip", "gzip", "rar", "doc", "docx", "xls", "xlsx"}
    assert set(ALLOWED_EXTENSIONS) == expected
    assert len(ALLOWED_EXTENSIONS) == 10


def test_file_extension_aliases_jpg_and_gz():
    # PNG valid header
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    _, ext_png = sanitize_filename("chart.png")
    assert ext_png == "png"
    assert validate_magic_bytes(ext_png, png_bytes) is True

    # JPG normalized to jpeg
    jpg_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 32
    _, ext_jpg = sanitize_filename("photo.jpg")
    assert ext_jpg == "jpeg"
    assert validate_magic_bytes(ext_jpg, jpg_bytes) is True

    # GZ normalized to gzip
    gz_bytes = b"\x1f\x8b\x08\x00" + b"\x00" * 32
    _, ext_gz = sanitize_filename("archive.gz")
    assert ext_gz == "gzip"
    assert validate_magic_bytes(ext_gz, gz_bytes) is True


def test_interaction_indexes_and_user_phone_column():
    table = Interaction.__table__
    indexed_cols = {col.name for idx in table.indexes for col in idx.columns}
    assert "program_id" in indexed_cols
    assert "product_id" in indexed_cols
    assert "state" in indexed_cols

    user_cols = {col.name for col in User.__table__.columns}
    assert "phone" in user_cols

    u = User(
        id="u-test-phone",
        keycloak_subject="u-test-phone-sub",
        name="Тест",
        email="t@rt.ru",
        role="manager",
        active=True,
        permissions=["interactions.read"],
    )
    u.phone = "+79991112233"
    assert u._phone == "+79991112233"
    assert u.phone == "+79991112233"
    assert "phone:+79991112233" not in (u.permissions or [])

    # Legacy backward compatibility check: when u._phone = None and u.permissions has 'phone:+79990001122'
    u_legacy = User(
        id="u-test-legacy",
        keycloak_subject="u-legacy-sub",
        name="Легаси",
        email="leg@rt.ru",
        role="manager",
        active=True,
        permissions=["interactions.read", "phone:+79990001122"],
    )
    u_legacy._phone = None
    assert u_legacy._phone is None
    assert u_legacy.phone == "+79990001122"


__all__ = [
    "test_allowed_extensions_strictly_10_formats",
    "test_file_extension_aliases_jpg_and_gz",
    "test_interaction_indexes_and_user_phone_column",
]
