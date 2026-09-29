#!/usr/bin/env python3
"""
Empirical Verification Script for Presentation Deliverables.
Challenger 1 (Artifacts & Vector Empirical Stress Challenger).

Performs exhaustive verification of:
1. PPTX archive integrity, XML well-formedness, slide count, layout relationships, media assets.
2. PDF page count, file sizes, binary equality between submission and docs.
3. PDF rendering via pdftoppm (-r 150), dimensions, non-zero file sizes.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
PPTX_PATH = ROOT_DIR / "submission_package" / "02_Презентация_CRM_Ростелеком.pptx"
PDF_SUBMISSION_PATH = ROOT_DIR / "submission_package" / "02_Презентация_CRM_Ростелеком.pdf"
PDF_DOCS_PATH = ROOT_DIR / "docs" / "Презентация_CRM_ИТ_Школа_Ростелеком.pdf"
SCRATCH_DIR = ROOT_DIR / "scratch" / "challenger_pres_rendered"

NAMESPACES = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "ct": "http://schemas.openxmlformats.org/package/2006/content-types",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
}


def test_pptx():
    print("=" * 60)
    print("STEP 1: EMPIRICAL PPTX VERIFICATION")
    print("=" * 60)

    assert PPTX_PATH.exists(), f"PPTX deliverable not found at {PPTX_PATH}"
    pptx_size = PPTX_PATH.stat().st_size
    print(f"[PPTX Size] {pptx_size:,} bytes ({pptx_size / (1024*1024):.2f} MB)")
    assert pptx_size > 10_000_000, f"PPTX size {pptx_size} <= 10,000,000 bytes!"
    print(f"PASS: PPTX size is strictly > 10,000,000 bytes.")

    xml_count = 0
    xml_errors = []

    with zipfile.ZipFile(PPTX_PATH, "r") as z:
        file_list = z.namelist()
        print(f"[Archive Contents] Total entries in ZIP: {len(file_list)}")

        # 1. Parse every single XML and .rels file
        for name in file_list:
            if name.endswith(".xml") or name.endswith(".rels"):
                xml_count += 1
                try:
                    data = z.read(name)
                    ET.fromstring(data)
                except ET.ParseError as e:
                    xml_errors.append((name, str(e)))

        print(f"[XML Parse Test] Parsed {xml_count} XML/.rels files. Syntax errors: {len(xml_errors)}")
        if xml_errors:
            for fname, err in xml_errors:
                print(f"  FAIL XML syntax error in {fname}: {err}")
            raise AssertionError(f"Encountered {len(xml_errors)} XML syntax errors in PPTX archive.")
        print(f"PASS: 0 XML syntax errors across all {xml_count} XML/.rels files.")

        # 2. Validate presentation.xml slide count
        pres_xml_bytes = z.read("ppt/presentation.xml")
        pres_root = ET.fromstring(pres_xml_bytes)

        sld_id_lst = pres_root.find(".//p:sldIdLst", NAMESPACES)
        assert sld_id_lst is not None, "p:sldIdLst not found in ppt/presentation.xml!"
        sld_ids = sld_id_lst.findall("p:sldId", NAMESPACES)
        slide_count = len(sld_ids)
        print(f"[Slide Count] Exactly {slide_count} slides listed in ppt/presentation.xml sldIdLst.")
        assert slide_count == 12, f"Expected exactly 12 slides, found {slide_count}!"
        print(f"PASS: Exactly 12 slides defined in presentation.xml.")

        # 3. Check relationships in ppt/_rels/presentation.xml.rels
        rels_xml_bytes = z.read("ppt/_rels/presentation.xml.rels")
        rels_root = ET.fromstring(rels_xml_bytes)
        rel_map = {}
        for rel in rels_root.findall(".//pr:Relationship", NAMESPACES):
            r_id = rel.get("Id")
            target = rel.get("Target")
            r_type = rel.get("Type")
            rel_map[r_id] = (target, r_type)

        slide_files = []
        for idx, sld in enumerate(sld_ids, start=1):
            r_id = sld.get(f"{{{NAMESPACES['r']}}}id")
            assert r_id in rel_map, f"Slide relationship {r_id} not in presentation.xml.rels!"
            target, r_type = rel_map[r_id]
            norm_target = "ppt/" + target if not target.startswith("ppt/") else target
            norm_target = norm_target.replace("\\", "/")
            assert norm_target in file_list, f"Slide file {norm_target} missing from archive!"
            slide_files.append((idx, r_id, norm_target))
            print(f"  Slide {idx:02d}: rId={r_id} -> {norm_target} (EXISTS)")

        print(f"PASS: All 12 slide files exist and map correctly from presentation.xml.")

        # 4. Check slideLayout relationships and media references for each slide
        for sld_idx, r_id, sld_path in slide_files:
            sld_dir = os.path.dirname(sld_path)
            sld_base = os.path.basename(sld_path)
            sld_rels_path = f"{sld_dir}/_rels/{sld_base}.rels"

            assert sld_rels_path in file_list, f"Relationships file {sld_rels_path} missing!"
            srels_root = ET.fromstring(z.read(sld_rels_path))

            # Find slideLayout
            layout_found = False
            images_found = []
            for srel in srels_root.findall(".//pr:Relationship", NAMESPACES):
                sr_type = srel.get("Type", "")
                sr_target = srel.get("Target", "")
                if sr_type.endswith("slideLayout"):
                    layout_found = True
                    layout_path = os.path.normpath(os.path.join(sld_dir, sr_target))
                    assert layout_path in file_list, f"Referenced layout {layout_path} not found in zip!"
                elif sr_type.endswith("image"):
                    media_path = os.path.normpath(os.path.join(sld_dir, sr_target))
                    assert media_path in file_list, f"Referenced media {media_path} not found in zip!"
                    images_found.append(media_path)

            assert layout_found, f"Slide {sld_path} has no slideLayout relationship!"
            print(f"  Slide {sld_idx:02d} ({sld_base}): Layout confirmed. Linked images: {len(images_found)}")

        print(f"PASS: All 12 slides have valid layout relationships and existing media.")

        # 5. Validate ppt/media/ assets
        media_files = [f for f in file_list if f.startswith("ppt/media/")]
        print(f"[Media Assets] Total embedded media in ppt/media/: {len(media_files)}")
        assert len(media_files) > 0, "No media files found in ppt/media/!"
        total_media_size = 0
        for mf in sorted(media_files):
            mf_info = z.getinfo(mf)
            total_media_size += mf_info.file_size
            assert mf_info.file_size > 0, f"Media file {mf} is 0 bytes!"
        print(f"  Total media payload: {total_media_size:,} bytes ({total_media_size / (1024*1024):.2f} MB)")
        print(f"PASS: Embedded media assets verified ({len(media_files)} files, all > 0 bytes).")

    return True


def test_pdf():
    print("\n" + "=" * 60)
    print("STEP 2: EMPIRICAL PDF VERIFICATION")
    print("=" * 60)

    assert PDF_SUBMISSION_PATH.exists(), f"PDF deliverable not found at {PDF_SUBMISSION_PATH}"
    assert PDF_DOCS_PATH.exists(), f"Docs PDF copy not found at {PDF_DOCS_PATH}"

    sub_size = PDF_SUBMISSION_PATH.stat().st_size
    docs_size = PDF_DOCS_PATH.stat().st_size

    print(f"[Submission PDF Size] {sub_size:,} bytes ({sub_size / 1024:.2f} KB)")
    print(f"[Docs PDF Size]       {docs_size:,} bytes ({docs_size / 1024:.2f} KB)")

    assert sub_size > 500_000, f"Submission PDF size {sub_size} <= 500,000 bytes!"
    assert docs_size > 500_000, f"Docs PDF size {docs_size} <= 500,000 bytes!"
    print(f"PASS: Both PDF files strictly exceed 500,000 bytes threshold.")

    # Compare SHA-256 hashes
    sub_hash = hashlib.sha256(PDF_SUBMISSION_PATH.read_bytes()).hexdigest()
    docs_hash = hashlib.sha256(PDF_DOCS_PATH.read_bytes()).hexdigest()
    print(f"[Submission PDF SHA-256] {sub_hash}")
    print(f"[Docs PDF SHA-256]       {docs_hash}")
    assert sub_hash == docs_hash, f"PDF hash mismatch! Diff detected: {sub_hash} != {docs_hash}"
    print(f"PASS: 0 byte diff between submission PDF and docs PDF (exact binary match).")

    # Verify page count via pdfinfo
    res = subprocess.run(["pdfinfo", str(PDF_SUBMISSION_PATH)], capture_output=True, text=True, check=True)
    pdf_info = {}
    for line in res.stdout.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            pdf_info[k.strip()] = v.strip()

    pages = int(pdf_info.get("Pages", "0"))
    print(f"[Page Count] PDF reported pages: {pages}")
    assert pages == 12, f"Expected exactly 12 pages in PDF, got {pages}!"
    print(f"PASS: PDF contains exactly 12 pages.")

    print(f"  Page size: {pdf_info.get('Page size', 'unknown')}")
    print(f"  PDF version: {pdf_info.get('PDF version', 'unknown')}")
    return True


def test_pdf_rendering():
    print("\n" + "=" * 60)
    print("STEP 3: EMPIRICAL PDF RENDERING (pdftoppm -r 150)")
    print("=" * 60)

    if SCRATCH_DIR.exists():
        shutil.rmtree(SCRATCH_DIR)
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)

    prefix = str(SCRATCH_DIR / "slide")
    cmd = ["pdftoppm", "-png", "-r", "150", str(PDF_SUBMISSION_PATH), prefix]
    print(f"Executing: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)

    rendered_images = sorted(SCRATCH_DIR.glob("slide-*.png"))
    print(f"[Rendered Slides] Found {len(rendered_images)} rendered PNG slides.")
    assert len(rendered_images) == 12, f"Expected 12 rendered slides, found {len(rendered_images)}!"

    # Read dimensions from PNG IHDR chunk (without third party libraries)
    for idx, img_path in enumerate(rendered_images, start=1):
        fsize = img_path.stat().st_size
        assert fsize > 0, f"Rendered image {img_path.name} is empty (0 bytes)!"

        # Extract width & height from PNG header (bytes 16..24)
        with open(img_path, "rb") as f:
            header = f.read(24)
            assert header.startswith(b"\x89PNG\r\n\x1a\n"), f"{img_path.name} is not a valid PNG!"
            width = int.from_bytes(header[16:20], "big")
            height = int.from_bytes(header[20:24], "big")

        aspect_ratio = width / height if height > 0 else 0
        print(f"  Slide {idx:02d}: {img_path.name} | Size: {fsize:,} bytes | Dims: {width}x{height} | Aspect: {aspect_ratio:.2f}")

        # Widescreen check: 16:9 is 1.777...
        assert 1.70 <= aspect_ratio <= 1.85, f"Unexpected aspect ratio {aspect_ratio:.2f} on slide {idx}!"
        assert fsize > 100_000, f"Suspiciously small image file size {fsize} bytes on slide {idx}!"

    print(f"PASS: All 12 slides successfully rendered at 150 DPI without corruption.")
    return True


def main():
    try:
        test_pptx()
        test_pdf()
        test_pdf_rendering()
        print("\n" + "=" * 60)
        print("ALL EMPIRICAL CHALLENGER TESTS PASSED SUCCESSFULLY!")
        print("=" * 60)
        return 0
    except Exception as e:
        print(f"\nCHALLENGER VERIFICATION FAILED: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
