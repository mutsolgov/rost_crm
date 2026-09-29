from __future__ import annotations

import csv
import io
import json
import struct
import xml.sax.saxutils as sax
import zipfile
import zlib
from datetime import date, datetime
from pathlib import Path
from typing import Any

from fastapi import Response
from fastapi.responses import JSONResponse

from .errors import APIError
from .models import User

_FONT_PATH = Path(__file__).parent / "fonts" / "LiberationSans-Regular.ttf"
_FONT_RAW = _FONT_PATH.read_bytes() if _FONT_PATH.exists() else b""
_FONT_ZLIB = zlib.compress(_FONT_RAW) if _FONT_RAW else b""


def _parse_ttf_font(ttf_bytes: bytes) -> tuple[bytes, dict[int, int], str]:
    if not ttf_bytes:
        return b"", {}, ""
    try:
        num_tables = struct.unpack(">H", ttf_bytes[4:6])[0]
        tables: dict[bytes, tuple[int, int]] = {}
        for i in range(num_tables):
            tag, check, off, length = struct.unpack(">4sIII", ttf_bytes[12 + i * 16 : 12 + (i + 1) * 16])
            tables[tag] = (off, length)

        if b"cmap" not in tables:
            return b"\x00" * 131072, {}, ""

        cmap_offset = tables[b"cmap"][0]
        num_sub = struct.unpack(">H", ttf_bytes[cmap_offset + 2 : cmap_offset + 4])[0]
        sub_off = None
        for i in range(num_sub):
            pid, eid, off = struct.unpack(">HHI", ttf_bytes[cmap_offset + 4 + i * 8 : cmap_offset + 12 + i * 8])
            fmt = struct.unpack(">H", ttf_bytes[cmap_offset + off : cmap_offset + off + 2])[0]
            if fmt == 4:
                sub_off = cmap_offset + off
                break
        if not sub_off:
            return b"\x00" * 131072, {}, ""

        fmt, length, lang, seg_count_x2 = struct.unpack(">HHHH", ttf_bytes[sub_off : sub_off + 8])
        seg_count = seg_count_x2 // 2
        end_counts = struct.unpack(f">{seg_count}H", ttf_bytes[sub_off + 14 : sub_off + 14 + seg_count * 2])
        start_counts = struct.unpack(f">{seg_count}H", ttf_bytes[sub_off + 16 + seg_count * 2 : sub_off + 16 + seg_count * 4])
        id_deltas = struct.unpack(f">{seg_count}h", ttf_bytes[sub_off + 16 + seg_count * 4 : sub_off + 16 + seg_count * 6])
        ro_offset = sub_off + 16 + seg_count * 6
        id_range_offsets = struct.unpack(f">{seg_count}H", ttf_bytes[ro_offset : ro_offset + seg_count * 2])

        mapping = [0] * 65536
        for i in range(seg_count):
            start = start_counts[i]
            end = end_counts[i]
            delta = id_deltas[i]
            ro = id_range_offsets[i]
            for c in range(start, end + 1):
                if c >= 65535:
                    continue
                if ro == 0:
                    gid = (c + delta) & 0xFFFF
                else:
                    glyph_offset = ro_offset + i * 2 + ro + (c - start) * 2
                    gid = struct.unpack(">H", ttf_bytes[glyph_offset : glyph_offset + 2])[0]
                    if gid != 0:
                        gid = (gid + delta) & 0xFFFF
                mapping[c] = gid

        cid_to_gid_bytes = struct.pack(f">{65536}H", *mapping)

        char_widths: dict[int, int] = {}
        w_array_str = ""
        if b"head" in tables and b"hhea" in tables and b"hmtx" in tables:
            head_off = tables[b"head"][0]
            units_per_em = struct.unpack(">H", ttf_bytes[head_off + 18 : head_off + 20])[0] or 1000

            hhea_off = tables[b"hhea"][0]
            num_hmetrics = struct.unpack(">H", ttf_bytes[hhea_off + 34 : hhea_off + 36])[0]

            hmtx_off = tables[b"hmtx"][0]
            if num_hmetrics > 0:
                for c in range(65536):
                    gid = mapping[c]
                    if gid != 0:
                        hmtx_idx = gid if gid < num_hmetrics else num_hmetrics - 1
                        adv = struct.unpack(">H", ttf_bytes[hmtx_off + hmtx_idx * 4 : hmtx_off + hmtx_idx * 4 + 2])[0]
                        char_widths[c] = round((adv * 1000) / units_per_em)

            groups: list[str] = []
            curr_start: int | None = None
            curr_widths: list[int] = []
            for c in sorted(char_widths.keys()):
                w = char_widths[c]
                if curr_start is None:
                    curr_start = c
                    curr_widths = [w]
                elif c == curr_start + len(curr_widths):
                    curr_widths.append(w)
                else:
                    inner_w = " ".join(str(x) for x in curr_widths)
                    groups.append(f"{curr_start} [{inner_w}]")
                    curr_start = c
                    curr_widths = [w]
            if curr_start is not None:
                inner_w = " ".join(str(x) for x in curr_widths)
                groups.append(f"{curr_start} [{inner_w}]")

            if groups:
                w_array_str = f"/W [{' '.join(groups)}]"

        return cid_to_gid_bytes, char_widths, w_array_str
    except Exception:
        return b"\x00" * 131072, {}, ""


def _build_cid_to_gid_map(ttf_bytes: bytes) -> bytes:
    cid_bytes, _, _ = _parse_ttf_font(ttf_bytes)
    return cid_bytes


_CID_TO_GID_BYTES, _CHAR_WIDTHS, _W_ARRAY = _parse_ttf_font(_FONT_RAW) if _FONT_RAW else (b"", {}, "")
_CID_TO_GID_ZLIB = zlib.compress(_CID_TO_GID_BYTES) if _CID_TO_GID_BYTES else b""


def _text_width(text: str, font_size: float = 8.5) -> float:
    return sum(_CHAR_WIDTHS.get(ord(c), 600) / 1000.0 * font_size for c in text)


_PUNCT_CHARS = (":", ".", ",", ";", "!", "?")


def _format_cell_value(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, datetime):
        return val.strftime("%d.%m.%Y %H:%M")
    if isinstance(val, date):
        return val.strftime("%d.%m.%Y")
    text = str(val).strip()
    if len(text) >= 10 and text[0:4].isdigit() and text[4] == "-" and text[5:7].isdigit() and text[7] == "-" and text[8:10].isdigit():
        try:
            if len(text) == 10:
                dt = datetime.fromisoformat(text)
                return dt.strftime("%d.%m.%Y")
            if text[10] in ("T", "t", " "):
                clean = (text[:-1] + "+00:00") if text.endswith(("Z", "z")) else text
                dt = datetime.fromisoformat(clean)
                return dt.strftime("%d.%m.%Y %H:%M")
        except Exception:
            pass
    return text


def _split_long_word(word: str, avail_w: float, font_size: float) -> list[str]:
    if len(word) <= 3 or _text_width(word, font_size) <= avail_w:
        return [word]
    if "-" in word:
        best_h = -1
        for idx, ch in enumerate(word):
            if ch == "-" and idx >= 2 and (len(word) - (idx + 1)) >= 3:
                if _text_width(word[: idx + 1], font_size) <= avail_w:
                    best_h = idx + 1
        if best_h > 0:
            part1 = word[:best_h]
            part2 = word[best_h:]
            return [part1] + _split_long_word(part2, avail_w, font_size)
    chunks: list[str] = []
    w = word
    while len(w) >= 6 and _text_width(w, font_size) > avail_w:
        k = len(w)
        while k > 3 and _text_width(w[:k], font_size) > avail_w:
            k -= 1
        rem_len = len(w) - k
        if 1 <= rem_len <= 2:
            needed = 3 - rem_len
            if k - needed >= 3:
                k -= needed
            else:
                break
        if k < 3:
            break
        chunks.append(w[:k])
        w = w[k:]
    if w:
        chunks.append(w)
    return chunks or [word]


def wrap_cell_text(text: Any, col_w: float, font_size: float = 8.5, max_lines: int = 10) -> list[str]:
    text_str = _format_cell_value(text)
    if not text_str:
        return [""]

    avail_w = max(10.0, col_w - 4.0)
    if "\n" not in text_str and not text_str.startswith(_PUNCT_CHARS) and _text_width(text_str, font_size) <= avail_w:
        return [text_str]

    raw_paras = text_str.split("\n")
    all_lines: list[str] = []

    for para in raw_paras:
        words = para.split()
        if not words:
            if not all_lines:
                all_lines.append("")
            continue

        glued_words: list[str] = []
        for w in words:
            if glued_words and w in _PUNCT_CHARS:
                glued_words[-1] += w
            else:
                glued_words.append(w)

        lines: list[str] = []
        curr = ""
        for w in glued_words:
            test = (curr + " " + w) if curr else w
            if _text_width(test, font_size) <= avail_w:
                curr = test
            else:
                if curr:
                    lines.append(curr)
                    curr = ""
                if _text_width(w, font_size) <= avail_w:
                    curr = w
                else:
                    chunks = _split_long_word(w, avail_w, font_size)
                    for chunk in chunks[:-1]:
                        lines.append(chunk)
                    curr = chunks[-1] if chunks else ""
        if curr:
            lines.append(curr)

        # Eliminate orphan single-character lines within paragraph
        if len(lines) > 1:
            i = len(lines) - 1
            while i >= 1 and len(lines) > 1:
                stripped = lines[i].strip()
                if len(stripped) == 1:
                    prev_words = lines[i - 1].split()
                    if len(prev_words) > 1:
                        moved = prev_words.pop()
                        cand = moved + " " + stripped
                        if _text_width(cand, font_size) <= avail_w:
                            lines[i - 1] = " ".join(prev_words)
                            lines[i] = cand
                            i -= 1
                            continue
                    sep = "" if stripped in _PUNCT_CHARS else " "
                    lines[i - 1] = lines[i - 1] + sep + stripped
                    lines.pop(i)
                i -= 1

            if len(lines) > 1 and len(lines[0].strip()) == 1:
                lines[1] = lines[0].strip() + " " + lines[1]
                lines.pop(0)

        all_lines.extend(lines)

    # Post-process all_lines to enforce typographic constraints
    idx = 0
    while idx < len(all_lines):
        while all_lines[idx] and all_lines[idx][0] in _PUNCT_CHARS:
            punc = all_lines[idx][0]
            if idx > 0:
                all_lines[idx - 1] = all_lines[idx - 1].rstrip() + punc
            all_lines[idx] = all_lines[idx][1:].lstrip()
        if not all_lines[idx]:
            all_lines.pop(idx)
            continue
        idx += 1

    if not all_lines:
        return [""]
    if len(all_lines) == 1 and all_lines[0].strip() in _PUNCT_CHARS:
        return [""]

    if len(all_lines) > max_lines:
        all_lines = all_lines[:max_lines]
        last = all_lines[-1]
        while last and _text_width(last + "..", font_size) > avail_w:
            last = last[:-1]
        all_lines[-1] = (last.rstrip(":.,;!? ") + "..") if last else ".."

    return all_lines or [""]


def sanitize_formula_cell(value: Any) -> str:
    """Escapes potential spreadsheet formula injection in cell values.

    Prepends a single quote (') if the value starts with dangerous formula triggers
    (=, +, -, @, \\t, \\r) even after stripping leading whitespace.
    """
    if value is None:
        return ""
    text = str(value)
    stripped = text.lstrip()
    if text.startswith(("=", "+", "-", "@", "\t", "\r")) or (stripped and stripped.startswith(("=", "+", "-", "@"))):
        return f"'{text}"
    return text


def _xml_escape(value: Any) -> str:
    safe_text = sanitize_formula_cell(value)
    return sax.escape(safe_text)


def _get_report_spec(report_type: str, report_data: dict, user: User, selected_columns: list[str] | None = None):
    if report_type == "snapshot":
        title = "Аналитический отчёт: Срез взаимодействий на дату"
        headers = ["ID", "Название", "Организация", "Программа", "Продукт", "Этап", "Ответственный"]
        fields = ["interaction_id", "title", "organization_name", "program_name", "product_name", "state_name", "owner_name"]
        metadata = {
            "Тип отчёта": "Snapshot (Срез на дату)",
            "Дата формирования": report_data.get("generated_at", ""),
            "Инициатор": f"{user.name} ({user.role})",
            "Срез на дату (as_of)": report_data.get("as_of", ""),
            "Отсечка актуальности (knowledge_cutoff)": report_data.get("knowledge_cutoff", ""),
            "Включая дату (as_of_inclusive)": str(report_data.get("as_of_inclusive", True)),
            "Всего взаимодействий": str(report_data.get("total_interactions", len(report_data.get("rows", [])))),
        }
    elif report_type == "activity":
        title = "Аналитический отчёт: Динамика переходов взаимодействий"
        headers = ["ID события", "ID карточки", "Название", "Организация", "Из этапа", "В этап", "Исторический ответственный", "Дата перехода"]
        fields = ["event_id", "interaction_id", "title", "organization_name", "from_state_name", "to_state_name", "historical_owner_id", "effective_at"]
        metadata = {
            "Тип отчёта": "Activity (Динамика переходов)",
            "Дата формирования": report_data.get("generated_at", ""),
            "Инициатор": f"{user.name} ({user.role})",
            "Период с": report_data.get("from_date", ""),
            "Период по": report_data.get("to_date", ""),
            "Отсечка актуальности (knowledge_cutoff)": report_data.get("knowledge_cutoff", ""),
            "Всего переходов": str(report_data.get("total_transitions", len(report_data.get("rows", [])))),
            "Всего затронуто взаимодействий": str(report_data.get("total_interactions", len(report_data.get("interaction_ids", [])))),
        }
    elif report_type == "created":
        title = "Аналитический отчёт: Созданные взаимодействия"
        headers = ["ID", "Название", "Организация", "Программа", "Продукт", "Ответственный", "Дата создания"]
        fields = ["interaction_id", "title", "organization_name", "program_name", "product_name", "owner_name", "created_at"]
        metadata = {
            "Тип отчёта": "Created (Созданные взаимодействия)",
            "Дата формирования": report_data.get("generated_at", ""),
            "Инициатор": f"{user.name} ({user.role})",
            "Период с": report_data.get("from_date", ""),
            "Период по": report_data.get("to_date", ""),
            "Отсечка актуальности (knowledge_cutoff)": report_data.get("knowledge_cutoff", ""),
            "Всего создано": str(report_data.get("total_created", len(report_data.get("rows", [])))),
        }
    else:
        title = f"Аналитический отчёт ({report_type})"
        headers = ["ID", "Данные"]
        fields = ["id", "title"]
        metadata = {"Тип отчёта": report_type, "Инициатор": f"{user.name} ({user.role})"}

    if selected_columns:
        extra_name_map = {
            "cycle_label": "Метка цикла",
            "owner_at_event_name": "Ответственный на момент перехода",
            "owner_at_event": "Ответственный на момент перехода",
            "actor_name": "Инициатор",
            "transition_code": "Код перехода",
            "organization_id": "ID организации",
            "program_id": "ID программы",
            "product_id": "ID продукта",
            "from_state": "Исходный этап",
            "to_state": "Целевой этап",
            "from_state_name": "Исходный этап",
            "to_state_name": "Целевой этап",
            "historical_owner_id": "Исторический ответственный",
            "created_at": "Дата создания",
            "effective_at": "Время события",
            "interaction_id": "ID карточки" if report_type == "activity" else "ID",
            "event_id": "ID события",
            "title": "Название",
            "organization_name": "Организация",
            "program_name": "Программа",
            "product_name": "Продукт",
            "state_name": "Этап",
            "owner_name": "Ответственный",
        }
        f_to_h = dict(zip(fields, headers))
        h_to_f = dict(zip(headers, fields))

        filtered_headers, filtered_fields = [], []
        seen = set()
        for col in selected_columns:
            if not col:
                continue
            if col in f_to_h:
                if col not in seen:
                    filtered_fields.append(col)
                    filtered_headers.append(f_to_h[col])
                    seen.add(col)
            elif col in h_to_f:
                f = h_to_f[col]
                if f not in seen:
                    filtered_fields.append(f)
                    filtered_headers.append(col)
                    seen.add(f)
            elif col in extra_name_map:
                if col not in seen:
                    filtered_fields.append(col)
                    filtered_headers.append(extra_name_map[col])
                    seen.add(col)
            else:
                if col not in seen:
                    filtered_fields.append(col)
                    filtered_headers.append(col)
                    seen.add(col)
        if filtered_fields:
            headers, fields = filtered_headers, filtered_fields

    rows = report_data.get("rows", [])
    return title, headers, fields, metadata, rows


def generate_xlsx_report(report_data: dict, report_type: str, user: User, selected_columns: list[str] | None = None) -> bytes:
    """Generates standard Office Open XML (.xlsx) workbook using zipfile and XML."""
    title, headers, fields, metadata, rows = _get_report_spec(report_type, report_data, user, selected_columns)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # [Content_Types].xml
        zf.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>""",
        )

        # _rels/.rels
        zf.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>""",
        )

        # xl/_rels/workbook.xml.rels
        zf.writestr(
            "xl/_rels/workbook.xml.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>""",
        )

        # xl/workbook.xml
        zf.writestr(
            "xl/workbook.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Отчёт" sheetId="1" r:id="rId1"/>
    <sheet name="Метаданные" sheetId="2" r:id="rId2"/>
  </sheets>
</workbook>""",
        )

        # xl/styles.xml
        # Fills: 2 = #7700FF (Purple), 3 = #F4F5F8 (Zebra light gray)
        # Fonts: 0 = default, 1 = bold white, 2 = bold black
        # Borders: 1 = thin #E2E5EB
        zf.writestr(
            "xl/styles.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="3">
    <font><sz val="11"/><color theme="1"/><name val="Calibri"/><family val="2"/></font>
    <font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/><family val="2"/></font>
    <font><b/><sz val="11"/><color rgb="FF101828"/><name val="Calibri"/><family val="2"/></font>
  </fonts>
  <fills count="4">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FF7700FF"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFF4F5F8"/></patternFill></fill>
  </fills>
  <borders count="2">
    <border><left/><right/><top/><bottom/><diagonal/></border>
    <border>
      <left style="thin"><color rgb="FFE2E5EB"/></left>
      <right style="thin"><color rgb="FFE2E5EB"/></right>
      <top style="thin"><color rgb="FFE2E5EB"/></top>
      <bottom style="thin"><color rgb="FFE2E5EB"/></bottom>
      <diagonal/>
    </border>
  </borders>
  <cellStyleXfs count="1">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>
  </cellStyleXfs>
  <cellXfs count="4">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
    <xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1"><alignment vertical="center"/></xf>
    <xf numFmtId="0" fontId="0" fillId="3" borderId="1" xfId="0" applyFill="1" applyBorder="1" applyAlignment="1"><alignment vertical="center"/></xf>
  </cellXfs>
</styleSheet>""",
        )

        def col_letter(col_idx: int) -> str:
            result = ""
            while col_idx >= 0:
                result = chr(col_idx % 26 + ord("A")) + result
                col_idx = col_idx // 26 - 1
            return result

        # Sheet 1: Report Data
        sheet1_lines = [
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
            "  <sheetData>",
            '    <row r="1">',
        ]
        for ci, h in enumerate(headers):
            ref = f"{col_letter(ci)}1"
            sheet1_lines.append(f'      <c r="{ref}" s="1" t="inlineStr"><is><t>{_xml_escape(h)}</t></is></c>')
        sheet1_lines.append("    </row>")

        for ri, r in enumerate(rows, start=2):
            style = "3" if ri % 2 == 1 else "2"
            sheet1_lines.append(f'    <row r="{ri}">')
            for ci, f in enumerate(fields):
                ref = f"{col_letter(ci)}{ri}"
                val = r.get(f)
                sheet1_lines.append(f'      <c r="{ref}" s="{style}" t="inlineStr"><is><t>{_xml_escape(val)}</t></is></c>')
            sheet1_lines.append("    </row>")

        sheet1_lines.extend(["  </sheetData>", "</worksheet>"])
        zf.writestr("xl/worksheets/sheet1.xml", "\n".join(sheet1_lines))

        # Sheet 2: Metadata
        sheet2_lines = [
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
            "  <sheetData>",
            '    <row r="1">',
            '      <c r="A1" s="1" t="inlineStr"><is><t>Параметр</t></is></c>',
            '      <c r="B1" s="1" t="inlineStr"><is><t>Значение</t></is></c>',
            "    </row>",
        ]
        for ri, (mk, mv) in enumerate(metadata.items(), start=2):
            style = "3" if ri % 2 == 1 else "2"
            sheet2_lines.append(f'    <row r="{ri}">')
            sheet2_lines.append(f'      <c r="A{ri}" s="{style}" t="inlineStr"><is><t>{_xml_escape(mk)}</t></is></c>')
            sheet2_lines.append(f'      <c r="B{ri}" s="{style}" t="inlineStr"><is><t>{_xml_escape(mv)}</t></is></c>')
            sheet2_lines.append("    </row>")
        sheet2_lines.extend(["  </sheetData>", "</worksheet>"])
        zf.writestr("xl/worksheets/sheet2.xml", "\n".join(sheet2_lines))

    return buf.getvalue()


def generate_pdf_report(report_data: dict, report_type: str, user: User, selected_columns: list[str] | None = None) -> bytes:
    """Generates pure vector PDF 1.4 document with Rostelecom letterhead, paginated tables, and page numbers."""
    title, headers, fields, metadata, rows = _get_report_spec(report_type, report_data, user, selected_columns)

    page_w = 595.28
    page_h = 841.89
    margin_x = 36.0
    usable_w = page_w - 2 * margin_x

    # Proportional column widths per report type (when using default fields)
    col_weights = {
        "snapshot": [0.08, 0.22, 0.22, 0.15, 0.13, 0.10, 0.10],
        "activity": [0.07, 0.08, 0.20, 0.20, 0.13, 0.13, 0.10, 0.09],
        "created": [0.08, 0.22, 0.22, 0.15, 0.13, 0.10, 0.10],
    }
    field_weight_hints = {
        "event_id": 0.07,
        "interaction_id": 0.08,
        "id": 0.08,
        "organization_id": 0.08,
        "program_id": 0.08,
        "product_id": 0.08,
        "transition_code": 0.08,
        "effective_at": 0.09,
        "created_at": 0.10,
        "state_name": 0.10,
        "historical_owner_id": 0.10,
        "cycle_label": 0.10,
        "owner_name": 0.10,
        "owner_at_event": 0.10,
        "from_state": 0.12,
        "to_state": 0.12,
        "from_state_name": 0.13,
        "to_state_name": 0.13,
        "actor_name": 0.12,
        "owner_at_event_name": 0.12,
        "product_name": 0.13,
        "program_name": 0.15,
        "organization_name": 0.20,
        "title": 0.20,
    }
    if not selected_columns and report_type in col_weights and len(col_weights[report_type]) == len(headers):
        weights = col_weights[report_type]
        col_widths = [usable_w * w for w in weights]
    elif fields and len(fields) == len(headers):
        raw_weights = [field_weight_hints.get(f, 0.12) for f in fields]
        total_w = sum(raw_weights) or 1.0
        col_widths = [usable_w * (w / total_w) for w in raw_weights]
    else:
        col_widths = [usable_w / len(headers)] * len(headers) if headers else [usable_w]

    col_x = [margin_x]
    for w in col_widths[:-1]:
        col_x.append(col_x[-1] + w)

    def hex_tj(s: Any) -> bytes:
        if s is None:
            s = ""
        return b"<" + str(s).encode("utf-16-be").hex().encode("ascii") + b">"

    # Dynamic row calculation and page partitioning
    paged_rows: list[list[dict]] = []
    current_page_rows: list[dict] = []

    p1_header_space = 58.0 + 18.0 + len(metadata) * 12.0 + 6.0 + 24.0
    pn_header_space = 58.0 + 16.0 + 24.0

    curr_avail_h = page_h - p1_header_space - 50.0

    for r in rows:
        cell_lines = [wrap_cell_text(r.get(f), col_widths[ci], font_size=8.5, max_lines=10) for ci, f in enumerate(fields)]
        max_lines_in_row = max(len(cl) for cl in cell_lines) if cell_lines else 1
        row_h = max(22.0, 8.0 + max_lines_in_row * 11.0)
        if curr_avail_h - row_h < 0 and current_page_rows:
            paged_rows.append(current_page_rows)
            current_page_rows = [r]
            curr_avail_h = page_h - pn_header_space - 50.0 - row_h
        else:
            current_page_rows.append(r)
            curr_avail_h -= row_h

    if current_page_rows or not paged_rows:
        paged_rows.append(current_page_rows)

    total_pages = len(paged_rows)

    cmap_lines = [
        "/CIDInit /ProcSet findresource begin",
        "12 dict begin",
        "begincmap",
        "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def",
        "/CMapName /Custom-ToUnicode def",
        "/CMapType 2 def",
        "1 begincodespacerange",
        "<0000> <FFFF>",
        "endcodespacerange",
        "1 beginbfrange",
        "<0000> <FFFF> <0000>",
        "endbfrange",
        "endcmap",
        "CMapName currentdict /CMap defineresource pop",
        "end",
        "end",
    ]
    cmap_data = "\n".join(cmap_lines).encode("ascii")

    page_streams = []
    for page_idx, page_rows in enumerate(paged_rows, start=1):
        s = io.BytesIO()

        # Rostelecom purple top accent bar (h=5 pt)
        s.write(b"0.467 0 1 rg\n")
        s.write(f"{margin_x:.2f} {page_h - 22:.2f} {usable_w:.2f} 5 re f\n".encode("ascii"))

        # Letterhead text
        s.write(b"BT /F1 11 Tf 0.1 0.1 0.1 rg\n")
        s.write(
            f"{margin_x:.2f} {page_h - 40:.2f} Td ".encode("ascii")
            + hex_tj("ПАО «Ростелеком» · ИТ Школа")
            + b" Tj ET\n"
        )

        # Confidentiality badge
        s.write(b"BT /F1 9 Tf 0.8 0.25 0.1 rg\n")
        s.write(
            f"{page_w - margin_x - 130:.2f} {page_h - 40:.2f} Td ".encode("ascii")
            + hex_tj("КОНФИДЕНЦИАЛЬНО · ДСП")
            + b" Tj ET\n"
        )

        curr_y = page_h - 58

        if page_idx == 1:
            # Report title
            s.write(b"BT /F1 13 Tf 0.05 0.08 0.15 rg\n")
            s.write(f"{margin_x:.2f} {curr_y:.2f} Td ".encode("ascii") + hex_tj(title) + b" Tj ET\n")
            curr_y -= 18

            # Metadata block with correct BT/ET per line
            for mk, mv in metadata.items():
                s.write(b"BT /F1 8.5 Tf 0.3 0.3 0.3 rg\n")
                s.write(
                    f"{margin_x:.2f} {curr_y:.2f} Td ".encode("ascii")
                    + hex_tj(f"{mk}: {mv}")
                    + b" Tj ET\n"
                )
                curr_y -= 12
            curr_y -= 6
        else:
            s.write(b"BT /F1 10 Tf 0.3 0.3 0.3 rg\n")
            s.write(
                f"{margin_x:.2f} {curr_y:.2f} Td ".encode("ascii")
                + hex_tj(f"{title} (продолжение)")
                + b" Tj ET\n"
            )
            curr_y -= 16

        # Repeated Table Header on every page
        th_h = 24.0
        s.write(b"0.467 0 1 rg\n")  # #7700FF
        s.write(f"{margin_x:.2f} {curr_y - th_h:.2f} {usable_w:.2f} {th_h:.2f} re f\n".encode("ascii"))

        # Header text
        s.write(b"BT /F1 8.5 Tf 1 1 1 rg\n")  # White
        for ci, header in enumerate(headers):
            cx = col_x[ci] + 4
            h_lines = wrap_cell_text(header, col_widths[ci], font_size=8.5, max_lines=2)
            if len(h_lines) == 1:
                cy = curr_y - 15.0
                s.write(f"1 0 0 1 {cx:.2f} {cy:.2f} Tm ".encode("ascii") + hex_tj(h_lines[0]) + b" Tj\n")
            else:
                for line_idx, line_text in enumerate(h_lines[:2]):
                    cy = curr_y - 9.5 - line_idx * 10.0
                    s.write(f"1 0 0 1 {cx:.2f} {cy:.2f} Tm ".encode("ascii") + hex_tj(line_text) + b" Tj\n")
        s.write(b"ET\n")
        curr_y -= th_h

        # Data rows
        for ri, r in enumerate(page_rows):
            cell_lines = [wrap_cell_text(r.get(f), col_widths[ci], font_size=8.5, max_lines=10) for ci, f in enumerate(fields)]
            max_lines_in_row = max(len(cl) for cl in cell_lines) if cell_lines else 1
            row_h = max(22.0, 8.0 + max_lines_in_row * 11.0)

            # Alternating zebra row
            if ri % 2 == 1:
                s.write(b"0.957 0.961 0.973 rg\n")  # #F4F5F8
                s.write(f"{margin_x:.2f} {curr_y - row_h:.2f} {usable_w:.2f} {row_h:.2f} re f\n".encode("ascii"))

            # Bottom row border
            s.write(b"0.886 0.898 0.922 RG 0.5 w\n")
            s.write(
                f"{margin_x:.2f} {curr_y - row_h:.2f} m {margin_x + usable_w:.2f} {curr_y - row_h:.2f} l S\n".encode(
                    "ascii"
                )
            )

            # Row cell values
            s.write(b"BT /F1 8.5 Tf 0.06 0.1 0.16 rg\n")
            for ci, c_lines in enumerate(cell_lines):
                cx = col_x[ci] + 4
                for line_idx, line_text in enumerate(c_lines):
                    cy = curr_y - 14.0 - line_idx * 11.0
                    s.write(f"1 0 0 1 {cx:.2f} {cy:.2f} Tm ".encode("ascii") + hex_tj(line_text) + b" Tj\n")
            s.write(b"ET\n")
            curr_y -= row_h

        # Footer divider and page number: "Стр. X из Y"
        s.write(b"0.886 0.898 0.922 RG 0.5 w\n")
        s.write(f"{margin_x:.2f} 45 m {margin_x + usable_w:.2f} 45 l S\n".encode("ascii"))
        s.write(b"BT /F1 8.5 Tf 0.3 0.3 0.3 rg\n")
        page_str = f"Стр. {page_idx} из {total_pages}"
        s.write(
            f"{margin_x + usable_w / 2 - 25:.2f} 30 Td ".encode("ascii")
            + hex_tj(page_str)
            + b" Tj ET\n"
        )

        page_streams.append(s.getvalue())

    num_pages = total_pages
    has_font = bool(_FONT_RAW)

    if has_font:
        first_page_obj = 9
        first_stream_obj = 9 + num_pages
    else:
        first_page_obj = 7
        first_stream_obj = 7 + num_pages

    objects = []
    # 1: Catalog
    objects.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    # 2: Pages
    kids = " ".join(f"{first_page_obj + i} 0 R" for i in range(num_pages))
    objects.append(f"2 0 obj\n<< /Type /Pages /Kids [{kids}] /Count {num_pages} >>\nendobj\n".encode("latin1"))

    if has_font:
        # 3: Font Type 0
        objects.append(
            b"3 0 obj\n<< /Type /Font /Subtype /Type0 /BaseFont /LiberationSans /Encoding /Identity-H /DescendantFonts [4 0 R] /ToUnicode 5 0 R >>\nendobj\n"
        )
        # 4: Descendant CIDFont
        w_part = f" {_W_ARRAY}" if _W_ARRAY else ""
        objects.append(
            f"4 0 obj\n<< /Type /Font /Subtype /CIDFontType2 /BaseFont /LiberationSans /CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> /FontDescriptor 6 0 R /CIDToGIDMap 7 0 R{w_part} /DW 600 >>\nendobj\n".encode(
                "latin1"
            )
        )
        # 5: ToUnicode CMap
        objects.append(f"5 0 obj\n<< /Length {len(cmap_data)} >>\nstream\n".encode("latin1") + cmap_data + b"\nendstream\nendobj\n")
        # 6: FontDescriptor
        objects.append(
            b"6 0 obj\n<< /Type /FontDescriptor /FontName /LiberationSans /Flags 32 /FontBBox [-200 -200 1000 900] /ItalicAngle 0 /Ascent 800 /Descent -200 /CapHeight 700 /StemV 80 /FontFile2 8 0 R >>\nendobj\n"
        )
        # 7: CIDToGIDMap stream
        objects.append(
            f"7 0 obj\n<< /Length {len(_CID_TO_GID_ZLIB)} /Filter /FlateDecode >>\nstream\n".encode("latin1")
            + _CID_TO_GID_ZLIB
            + b"\nendstream\nendobj\n"
        )
        # 8: FontFile2 stream
        objects.append(
            f"8 0 obj\n<< /Length {len(_FONT_ZLIB)} /Filter /FlateDecode /Length1 {len(_FONT_RAW)} >>\nstream\n".encode("latin1")
            + _FONT_ZLIB
            + b"\nendstream\nendobj\n"
        )
    else:
        # Fallback
        objects.append(
            b"3 0 obj\n<< /Type /Font /Subtype /Type0 /BaseFont /Helvetica /Encoding /Identity-H /DescendantFonts [4 0 R] /ToUnicode 5 0 R >>\nendobj\n"
        )
        objects.append(
            b"4 0 obj\n<< /Type /Font /Subtype /CIDFontType2 /BaseFont /Helvetica /CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> /FontDescriptor 6 0 R /DW 600 >>\nendobj\n"
        )
        objects.append(f"5 0 obj\n<< /Length {len(cmap_data)} >>\nstream\n".encode("latin1") + cmap_data + b"\nendstream\nendobj\n")
        objects.append(
            b"6 0 obj\n<< /Type /FontDescriptor /FontName /Helvetica /Flags 32 /FontBBox [-200 -200 1000 900] /ItalicAngle 0 /Ascent 800 /Descent -200 /CapHeight 700 /StemV 80 >>\nendobj\n"
        )

    # Pages
    for i in range(num_pages):
        page_obj_id = first_page_obj + i
        stream_obj_id = first_stream_obj + i
        p_obj = (
            f"{page_obj_id} 0 obj\n<< /Type /Page /Parent 2 0 R "
            f"/MediaBox [0 0 {page_w} {page_h}] "
            f"/Resources << /Font << /F1 3 0 R >> >> "
            f"/Contents {stream_obj_id} 0 R >>\nendobj\n".encode("latin1")
        )
        objects.append(p_obj)

    # Streams
    for i in range(num_pages):
        stream_obj_id = first_stream_obj + i
        stream_data = page_streams[i]
        s_obj = (
            f"{stream_obj_id} 0 obj\n<< /Length {len(stream_data)} >>\nstream\n".encode("latin1")
            + stream_data
            + b"\nendstream\nendobj\n"
        )
        objects.append(s_obj)

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for obj in objects:
        offsets.append(out.tell())
        out.write(obj)

    startxref = out.tell()
    total_objs = len(objects) + 1
    out.write(f"xref\n0 {total_objs}\n0000000000 65535 f \n".encode("latin1"))
    for off in offsets[1:]:
        out.write(f"{off:010d} 00000 n \n".encode("latin1"))
    out.write(f"trailer\n<< /Size {total_objs} /Root 1 0 R >>\nstartxref\n{startxref}\n%%EOF\n".encode("latin1"))

    return out.getvalue()


def generate_csv_report(report_data: dict, report_type: str, user: User, selected_columns: list[str] | None = None) -> bytes:
    """Generates UTF-8-SIG encoded CSV report with sanitized text cells against formula injection."""
    title, headers, fields, metadata, rows = _get_report_spec(report_type, report_data, user, selected_columns)
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)

    writer.writerow(headers)
    for r in rows:
        row_vals = []
        for f in fields:
            val = r.get(f)
            escaped = sanitize_formula_cell(val)
            row_vals.append(escaped)
        writer.writerow(row_vals)

    return buf.getvalue().encode("utf-8-sig")


def export_report(report_data: dict, report_type: str, export_format: str, user: User, selected_columns: list[str] | None = None) -> Response:
    """Exports report to requested format (json, xlsx, pdf, csv) with appropriate headers and mime types."""
    fmt = (export_format or "json").lower()
    if fmt == "json":
        data_to_send = dict(report_data)
        if selected_columns and "rows" in data_to_send:
            sel_set = set(selected_columns)
            data_to_send["rows"] = [{k: v for k, v in r.items() if k in sel_set} for r in data_to_send["rows"]]
        response = JSONResponse(data_to_send)
        response.headers["Content-Disposition"] = f'attachment; filename="rtk-{report_type}.json"'
        response.headers["X-Report-Format"] = "json"
        return response
    elif fmt in {"xlsx", "xls"}:
        xlsx_bytes = generate_xlsx_report(report_data, report_type, user, selected_columns)
        media_type = "application/vnd.ms-excel" if fmt == "xls" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        response = Response(
            content=xlsx_bytes,
            media_type=media_type,
        )
        response.headers["Content-Disposition"] = f'attachment; filename="rtk-{report_type}.{fmt}"'
        response.headers["X-Report-Format"] = fmt
        return response
    elif fmt == "pdf":
        pdf_bytes = generate_pdf_report(report_data, report_type, user, selected_columns)
        response = Response(content=pdf_bytes, media_type="application/pdf")
        response.headers["Content-Disposition"] = f'attachment; filename="rtk-{report_type}.pdf"'
        response.headers["X-Report-Format"] = "pdf"
        return response
    elif fmt == "csv":
        csv_bytes = generate_csv_report(report_data, report_type, user, selected_columns)
        response = Response(content=csv_bytes, media_type="text/csv; charset=utf-8")
        response.headers["Content-Disposition"] = f'attachment; filename="rtk-{report_type}.csv"'
        response.headers["X-Report-Format"] = "csv"
        return response
    else:
        raise APIError(
            "VALIDATION_ERROR",
            f"Неподдерживаемый формат экспорта '{export_format}'. Допустимы: json, xls, xlsx, pdf, csv.",
            422,
        )
