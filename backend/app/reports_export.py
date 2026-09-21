from __future__ import annotations

import csv
import io
import json
import xml.sax.saxutils as sax
import zipfile
from typing import Any

from fastapi import Response
from fastapi.responses import JSONResponse

from .errors import APIError
from .models import User


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


def _get_report_spec(report_type: str, report_data: dict, user: User):
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
        headers = ["ID события", "ID карточки", "Из этапа", "В этап", "Исторический ответственный", "Дата перехода"]
        fields = ["event_id", "interaction_id", "from_state_name", "to_state_name", "historical_owner_id", "effective_at"]
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

    rows = report_data.get("rows", [])
    return title, headers, fields, metadata, rows


def generate_xlsx_report(report_data: dict, report_type: str, user: User) -> bytes:
    """Generates standard Office Open XML (.xlsx) workbook using zipfile and XML."""
    title, headers, fields, metadata, rows = _get_report_spec(report_type, report_data, user)

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


def generate_pdf_report(report_data: dict, report_type: str, user: User) -> bytes:
    """Generates pure vector PDF 1.4 document with Rostelecom letterhead, paginated tables, and page numbers."""
    title, headers, fields, metadata, rows = _get_report_spec(report_type, report_data, user)

    page_w = 595.28
    page_h = 841.89
    margin_x = 36.0
    usable_w = page_w - 2 * margin_x
    col_w = usable_w / len(headers)

    p1_limit = 26
    pn_limit = 32

    paged_rows = []
    if not rows:
        paged_rows.append([])
    elif len(rows) <= p1_limit:
        paged_rows.append(rows)
    else:
        paged_rows.append(rows[:p1_limit])
        rem = rows[p1_limit:]
        while rem:
            paged_rows.append(rem[:pn_limit])
            rem = rem[pn_limit:]

    total_pages = len(paged_rows)

    text_corpus = (
        title
        + " "
        + " ".join(headers)
        + " ПАО «Ростелеком» · ИТ Школа КОНФИДЕНЦИАЛЬНО · ДСП Стр. из 0123456789 (продолжение)"
    )
    for k, v in metadata.items():
        text_corpus += f" {k} {v}"
    for r in rows:
        for f in fields:
            text_corpus += f" {r.get(f) or ''}"

    unique_chars = sorted(set(text_corpus))
    char_to_code: dict[str, int] = {}
    valid_chars: list[str] = []
    for i, c in enumerate(unique_chars):
        code = i + 32
        if code > 255:
            break
        char_to_code[c] = code
        valid_chars.append(c)

    def enc(s: Any) -> bytes:
        if s is None:
            s = ""
        s_str = str(s)
        res = bytearray()
        for ch in s_str:
            code = char_to_code.get(ch, 63 if 63 in char_to_code.values() else 32)
            if code == 40:  # (
                res.extend(b"\\(")
            elif code == 41:  # )
                res.extend(b"\\)")
            elif code == 92:  # \
                res.extend(b"\\\\")
            else:
                res.append(code)
        return bytes(res)

    cmap_lines = [
        "/CIDInit /ProcSet findresource begin",
        "12 dict begin",
        "begincmap",
        "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def",
        "/CMapName /Custom-ToUnicode def",
        "/CMapType 2 def",
        "1 begincodespacerange",
        "<00> <FF>",
        "endcodespacerange",
        f"{len(valid_chars)} beginbfchar",
    ]
    for c in valid_chars:
        cmap_lines.append(f"<{char_to_code[c]:02X}> <{ord(c):04X}>")
    cmap_lines.extend(
        [
            "endbfchar",
            "endcmap",
            "CMapName currentdict /CMap defineresource pop",
            "end",
            "end",
        ]
    )
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
            f"{margin_x:.2f} {page_h - 40:.2f} Td (".encode("ascii")
            + enc("ПАО «Ростелеком» · ИТ Школа")
            + b") Tj ET\n"
        )

        # Confidentiality badge
        s.write(b"BT /F1 9 Tf 0.8 0.25 0.1 rg\n")
        s.write(
            f"{page_w - margin_x - 130:.2f} {page_h - 40:.2f} Td (".encode("ascii")
            + enc("КОНФИДЕНЦИАЛЬНО · ДСП")
            + b") Tj ET\n"
        )

        curr_y = page_h - 58

        if page_idx == 1:
            # Report title
            s.write(b"BT /F1 13 Tf 0.05 0.08 0.15 rg\n")
            s.write(f"{margin_x:.2f} {curr_y:.2f} Td (".encode("ascii") + enc(title) + b") Tj ET\n")
            curr_y -= 18

            # Metadata block
            s.write(b"BT /F1 8.5 Tf 0.3 0.3 0.3 rg\n")
            for mk, mv in metadata.items():
                s.write(
                    f"{margin_x:.2f} {curr_y:.2f} Td (".encode("ascii")
                    + enc(f"{mk}: {mv}")
                    + b") Tj ET\n"
                )
                curr_y -= 12
            curr_y -= 6
        else:
            s.write(b"BT /F1 10 Tf 0.3 0.3 0.3 rg\n")
            s.write(
                f"{margin_x:.2f} {curr_y:.2f} Td (".encode("ascii")
                + enc(f"{title} (продолжение)")
                + b") Tj ET\n"
            )
            curr_y -= 16

        # Repeated Table Header on every page
        th_h = 22.0
        s.write(b"0.467 0 1 rg\n")  # #7700FF
        s.write(f"{margin_x:.2f} {curr_y - th_h:.2f} {usable_w:.2f} {th_h:.2f} re f\n".encode("ascii"))

        # Header text
        s.write(b"BT /F1 9 Tf 1 1 1 rg\n")  # White
        for ci, header in enumerate(headers):
            cx = margin_x + ci * col_w + 4
            cy = curr_y - 15
            h_text = header[:16] if len(header) > 16 else header
            s.write(f"1 0 0 1 {cx:.2f} {cy:.2f} Tm (".encode("ascii") + enc(h_text) + b") Tj\n")
        s.write(b"ET\n")
        curr_y -= th_h

        # Data rows
        row_h = 18.0
        for ri, r in enumerate(page_rows):
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
            for ci, field in enumerate(fields):
                cx = margin_x + ci * col_w + 4
                cy = curr_y - 13
                val = str(r.get(field) or "")
                if len(val) > 22:
                    val = val[:20] + ".."
                s.write(f"1 0 0 1 {cx:.2f} {cy:.2f} Tm (".encode("ascii") + enc(val) + b") Tj\n")
            s.write(b"ET\n")
            curr_y -= row_h

        # Footer divider and page number: "Стр. X из Y"
        s.write(b"0.886 0.898 0.922 RG 0.5 w\n")
        s.write(f"{margin_x:.2f} 45 m {margin_x + usable_w:.2f} 45 l S\n".encode("ascii"))
        s.write(b"BT /F1 8.5 Tf 0.3 0.3 0.3 rg\n")
        page_str = f"Стр. {page_idx} из {total_pages}"
        s.write(
            f"{margin_x + usable_w / 2 - 25:.2f} 30 Td (".encode("ascii")
            + enc(page_str)
            + b") Tj ET\n"
        )

        page_streams.append(s.getvalue())

    num_pages = total_pages
    first_page_obj = 5
    first_stream_obj = 5 + num_pages

    objects = []
    # 1: Catalog
    objects.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    # 2: Pages
    kids = " ".join(f"{first_page_obj + i} 0 R" for i in range(num_pages))
    objects.append(f"2 0 obj\n<< /Type /Pages /Kids [{kids}] /Count {num_pages} >>\nendobj\n".encode("latin1"))
    # 3: Font
    objects.append(b"3 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /ToUnicode 4 0 R >>\nendobj\n")
    # 4: ToUnicode CMap
    objects.append(f"4 0 obj\n<< /Length {len(cmap_data)} >>\nstream\n".encode("latin1") + cmap_data + b"\nendstream\nendobj\n")

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


def generate_csv_report(report_data: dict, report_type: str, user: User) -> bytes:
    """Generates UTF-8-SIG encoded CSV report with sanitized text cells against formula injection."""
    title, headers, fields, metadata, rows = _get_report_spec(report_type, report_data, user)
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


def export_report(report_data: dict, report_type: str, export_format: str, user: User) -> Response:
    """Exports report to requested format (json, xlsx, pdf, csv) with appropriate headers and mime types."""
    fmt = (export_format or "json").lower()
    if fmt == "json":
        response = JSONResponse(report_data)
        response.headers["Content-Disposition"] = f'attachment; filename="rtk-{report_type}.json"'
        response.headers["X-Report-Format"] = "json"
        return response
    elif fmt == "xlsx":
        xlsx_bytes = generate_xlsx_report(report_data, report_type, user)
        response = Response(
            content=xlsx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response.headers["Content-Disposition"] = f'attachment; filename="rtk-{report_type}.xlsx"'
        response.headers["X-Report-Format"] = "xlsx"
        return response
    elif fmt == "pdf":
        pdf_bytes = generate_pdf_report(report_data, report_type, user)
        response = Response(content=pdf_bytes, media_type="application/pdf")
        response.headers["Content-Disposition"] = f'attachment; filename="rtk-{report_type}.pdf"'
        response.headers["X-Report-Format"] = "pdf"
        return response
    elif fmt == "csv":
        csv_bytes = generate_csv_report(report_data, report_type, user)
        response = Response(content=csv_bytes, media_type="text/csv; charset=utf-8")
        response.headers["Content-Disposition"] = f'attachment; filename="rtk-{report_type}.csv"'
        response.headers["X-Report-Format"] = "csv"
        return response
    else:
        raise APIError(
            "VALIDATION_ERROR",
            f"Неподдерживаемый формат экспорта '{export_format}'. Допустимы: json, xlsx, pdf, csv.",
            422,
        )
