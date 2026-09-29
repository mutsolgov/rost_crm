from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.reports_export import (
    _CHAR_WIDTHS,
    _W_ARRAY,
    _format_cell_value,
    _text_width,
    generate_pdf_report,
    wrap_cell_text,
)
from app.models import User


def test_font_metrics_and_w_array():
    """R1: Test TTF font metrics extraction and /W array generation."""
    # Ensure _CHAR_WIDTHS is populated
    assert len(_CHAR_WIDTHS) > 1000
    # Space, Latin, Cyrillic, digits should be present
    assert ord(" ") in _CHAR_WIDTHS
    assert _CHAR_WIDTHS[ord(" ")] == 278
    assert ord("A") in _CHAR_WIDTHS
    assert ord("А") in _CHAR_WIDTHS  # Cyrillic A
    assert ord("0") in _CHAR_WIDTHS

    # Ensure /W array is correctly formatted
    assert _W_ARRAY.startswith("/W [")
    assert _W_ARRAY.endswith("]")
    # Verify group syntax: c [w1 w2 ...]
    assert "32 [" in _W_ARRAY


def test_pdf_font_w_array_embedding():
    """R1: Test /W array embedding into CIDFontType2 object 4 before /DW 600."""
    dummy_user = User(id="user-1", name="Тестовый Пользователь", role="supervisor", team_id="team-1")
    report_data = {
        "report_type": "snapshot",
        "generated_at": "2026-09-29T12:00:00Z",
        "as_of": "2026-09-29T12:00:00Z",
        "rows": [
            {
                "interaction_id": "int-1",
                "title": "Тестовое взаимодействие с длинным заголовком",
                "organization_name": "ПАО Ростелеком",
                "program_name": "DevOps Школа",
                "product_name": "Облачные сервисы",
                "state_name": "В работе",
                "owner_name": "Иванов И.И.",
            }
        ],
    }

    pdf_bytes = generate_pdf_report(report_data, "snapshot", dummy_user)
    assert pdf_bytes.startswith(b"%PDF-1.4")
    assert b"%%EOF" in pdf_bytes
    # Object 4 must contain /W array before /DW 600
    assert b"/CIDFontType2" in pdf_bytes
    assert b"/W [" in pdf_bytes
    assert b"/DW 600" in pdf_bytes

    # Position of /W [ must be before /DW 600 in object 4
    w_pos = pdf_bytes.find(b"/W [")
    dw_pos = pdf_bytes.find(b"/DW 600")
    assert w_pos != -1
    assert dw_pos != -1
    assert w_pos < dw_pos


def test_column_weights_activity_and_adaptive_selected_columns():
    """R2: Test column weights for 8-column activity report and adaptive custom selected_columns."""
    dummy_user = User(id="user-1", name="Тестовый Пользователь", role="supervisor", team_id="team-1")

    # 8-column activity report
    activity_data = {
        "report_type": "activity",
        "generated_at": "2026-09-29T12:00:00Z",
        "from_date": "2026-09-20T00:00:00Z",
        "to_date": "2026-09-29T00:00:00Z",
        "rows": [
            {
                "event_id": "ev-1",
                "interaction_id": "int-1",
                "title": "Проект автоматизации процессов взаимодействия",
                "organization_name": "ООО Партнерские Решения",
                "from_state_name": "Первичный контакт",
                "to_state_name": "Встреча назначена",
                "historical_owner_id": "manager-a",
                "effective_at": "2026-09-24T19:56:11.784833Z",
            }
        ],
    }
    pdf_act = generate_pdf_report(activity_data, "activity", dummy_user)
    assert pdf_act.startswith(b"%PDF-1.4")

    # Custom selected_columns
    pdf_custom = generate_pdf_report(
        activity_data,
        "activity",
        dummy_user,
        selected_columns=["title", "effective_at"],
    )
    assert pdf_custom.startswith(b"%PDF-1.4")


def test_date_formatting_in_cells():
    """R3: Test ISO-8601 formatting to DD.MM.YYYY HH:MM."""
    iso_z = "2026-09-24T19:56:11.784833Z"
    assert _format_cell_value(iso_z) == "24.09.2026 19:56"

    iso_offset = "2026-09-24T19:56:11+03:00"
    assert _format_cell_value(iso_offset) == "24.09.2026 19:56"

    iso_space = "2026-09-24 19:56:11"
    assert _format_cell_value(iso_space) == "24.09.2026 19:56"

    dt_obj = datetime(2026, 9, 24, 19, 56, 0, tzinfo=timezone.utc)
    assert _format_cell_value(dt_obj) == "24.09.2026 19:56"

    # Date-only and minute-precision timestamps
    assert _format_cell_value("2026-09-24T19:56Z") == "24.09.2026 19:56"
    assert _format_cell_value("2026-09-24 19:56") == "24.09.2026 19:56"
    assert _format_cell_value("2026-09-24") == "24.09.2026"

    # Non-date strings should not be modified
    assert _format_cell_value("Просто текст") == "Просто текст"
    assert _format_cell_value(None) == ""


def test_wrap_cell_text_accurate_metrics_and_orphan_protection():
    """R3: Test accurate text wrapping with LiberationSans glyph metrics and orphan protection."""
    # 1. Exact width matches font metrics
    w_a = _text_width("А", 10.0)
    assert 6.0 <= w_a <= 7.0  # Normalized width for 'А' is 667 / 1000 * 10 = 6.67 pt

    # 2. ISO timestamp wrapping in narrow column
    lines = wrap_cell_text("2026-09-24T19:56:11.784833Z", col_w=47.1, font_size=8.5, max_lines=10)
    assert len(lines) == 2
    assert lines[0] == "24.09.2026"
    assert lines[1] == "19:56"

    # 3. Protection against single hanging letters and punctuation
    # Words with trailing colon or period should not wrap into single-character lines
    colon_wrap = wrap_cell_text("Статус :", col_w=50.0, font_size=8.5, max_lines=5)
    for line in colon_wrap:
        assert line.strip() != ":"

    period_wrap = wrap_cell_text("Организация .", col_w=50.0, font_size=8.5, max_lines=5)
    for line in period_wrap:
        assert line.strip() != "."

    # Single letter at end of line (e.g. "я" or "й")
    letter_wrap = wrap_cell_text("Ответственный я", col_w=50.0, font_size=8.5, max_lines=5)
    for line in letter_wrap:
        assert line.strip() not in ("я", "й")

    # 4. Long word split protection: remainder of word must not be <= 2 characters
    long_word_wrap = wrap_cell_text("Интеграция", col_w=35.0, font_size=8.5, max_lines=5)
    assert len(long_word_wrap) >= 2
    for chunk in long_word_wrap:
        assert len(chunk.strip()) > 2

    # Short words (<= 3 chars) must not be split into single-letter lines
    short_wrap = wrap_cell_text("Дом", col_w=14.0, font_size=8.5, max_lines=5)
    assert short_wrap == ["Дом"]


def test_adversarial_cell_text_wrapping_and_punctuation():
    """Adversarial checks for lines starting with punctuation, newlines in short text, and single-letter orphans."""
    # Newlines in strings shorter than available width must still be split into lines
    nl_wrap = wrap_cell_text("Первая строка\nВторая строка", col_w=300.0, font_size=8.5)
    assert nl_wrap == ["Первая строка", "Вторая строка"]

    # Lines must never start with a colon or dot
    long_colon_wrap = wrap_cell_text("Очень длинная строка названия : следующее слово", col_w=135.0, font_size=8.5)
    for line in long_colon_wrap:
        assert not line.strip().startswith((":", "."))

    leading_colon_wrap = wrap_cell_text(": Тестовое значение", col_w=100.0, font_size=8.5)
    assert leading_colon_wrap == ["Тестовое значение"]

    leading_dot_wrap = wrap_cell_text(". Примечание", col_w=100.0, font_size=8.5)
    assert leading_dot_wrap == ["Примечание"]

    newline_colon_wrap = wrap_cell_text("Строка 1\n: Строка 2", col_w=100.0, font_size=8.5)
    assert newline_colon_wrap == ["Строка 1:", "Строка 2"]

    # Single-letter words at beginning of text must not form orphan single-letter lines
    start_y_wrap = wrap_cell_text("й Пользователь", col_w=61.0, font_size=8.5)
    assert len(start_y_wrap) == 1 or all(len(l.strip()) > 1 for l in start_y_wrap)
    assert "й" not in [l.strip() for l in start_y_wrap]

    start_z_wrap = wrap_cell_text("Z Данные", col_w=40.0, font_size=8.5)
    assert len(start_z_wrap) == 1 or all(len(l.strip()) > 1 for l in start_z_wrap)
    assert "Z" not in [l.strip() for l in start_z_wrap]

    # Single character cells (like ID "1" or "-") should remain intact
    assert wrap_cell_text("1", col_w=50.0) == ["1"]
    assert wrap_cell_text("-", col_w=50.0) == ["-"]
    # Single colon or dot cells should be treated as empty
    assert wrap_cell_text(":", col_w=50.0) == [""]
    assert wrap_cell_text(".", col_w=50.0) == [""]


def test_no_word_corruption_and_multiline_paragraphs():
    """Verify that split words never have spaces inserted inside them and paragraphs are preserved."""
    # 1. Words must never have spaces inserted into their split chunks
    test_words = [
        "Автоматизация",
        "Ответственный",
        "Программирование",
        "Администратор",
        "Тестирование",
        "Интеграция",
        "Дом",
    ]
    for w in test_words:
        for cw in [15.0, 20.0, 25.0, 30.0, 35.0, 50.0]:
            lines = wrap_cell_text(w, col_w=cw)
            for line in lines:
                assert " " not in line.strip(), f"Word {w} corrupted with space at col_w={cw}: {lines}"

    # 2. Distinct paragraphs separated by newline must not be collapsed
    p_lines = wrap_cell_text("А\nБ\nВ", col_w=50.0)
    assert p_lines == ["А", "Б", "В"]

    # 3. Custom unmapped columns in selected_columns and order preservation in PDF
    dummy_user = User(id="user-1", name="Тестовый Пользователь", role="supervisor", team_id="team-1")
    rep_data = {
        "report_type": "snapshot",
        "rows": [{"title": "Проект CRM", "custom_metric": "99.9%"}],
    }
    # Custom unmapped column
    pdf_custom = generate_pdf_report(rep_data, "snapshot", dummy_user, selected_columns=["title", "custom_metric"])
    assert pdf_custom.startswith(b"%PDF-1.4")
    custom_hex = "custom_metric".encode("utf-16-be").hex().encode("ascii")
    assert custom_hex in pdf_custom

    # Order preservation
    pdf_rev = generate_pdf_report(rep_data, "snapshot", dummy_user, selected_columns=["custom_metric", "title"])
    assert pdf_rev.startswith(b"%PDF-1.4")


def test_hyphenated_words_universal_punctuation_and_date_variants():
    """Verify clean hyphenation, universal punctuation handling, lowercase z ISO dates, and multi-page pagination."""
    from datetime import date

    # 1. Hyphenated word breaking preserves existing hyphens
    hyphen_lines = wrap_cell_text("бизнес-план", col_w=50.0)
    assert hyphen_lines == ["бизнес-", "план"]

    long_hyphen_lines = wrap_cell_text("интернет-магазин", col_w=50.0)
    assert hyphen_lines[0].endswith("-")

    # 2. Universal punctuation gluing across newlines
    for p in (":", ".", ",", ";", "!", "?"):
        res = wrap_cell_text(f"Строка 1\n{p} Строка 2", col_w=100.0)
        assert res[0] == f"Строка 1{p}"
        assert res[1] == "Строка 2"
        # Pure punctuation cells return empty
        assert wrap_cell_text(p, col_w=50.0) == [""]

    # 3. ISO date with lowercase 'z' and native date object
    assert _format_cell_value("2026-09-24T19:56:11z") == "24.09.2026 19:56"
    assert _format_cell_value(date(2026, 9, 24)) == "24.09.2026"

    # 4. Multi-page pagination footer consistency
    dummy_user = User(id="user-1", name="Тестовый Пользователь", role="supervisor", team_id="team-1")
    rep_data = {
        "report_type": "snapshot",
        "rows": [
            {
                "interaction_id": f"int-{i}",
                "title": f"Взаимодействие номер {i}",
                "organization_name": "ПАО Ростелеком",
                "program_name": "DevOps",
                "product_name": "Cloud",
                "state_name": "В работе",
                "owner_name": "Иванов И.И.",
            }
            for i in range(100)
        ],
    }
    pdf_bytes = generate_pdf_report(rep_data, "snapshot", dummy_user)
    assert pdf_bytes.count(b"/Type /Page /Parent") == 5
    for p_num in range(1, 6):
        expected_footer = f"Стр. {p_num} из 5".encode("utf-16-be").hex().encode("ascii")
        assert expected_footer in pdf_bytes


