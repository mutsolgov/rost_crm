#!/usr/bin/env python3
"""
Скрипт сборки финальной презентации «ИТ Школа Ростелекома — CRM» (rost_crm)
для сдачи на хакатоне ЛЦТ 2026 (Команда «Ezdel»).

Реализация строго на стандартной библиотеке Python (Stdlib-first):
zipfile, xml.etree.ElementTree, subprocess, shutil, os, sys, pathlib.

Генерирует:
1. submission_package/02_Презентация_CRM_Ростелеком.pptx (> 10 МБ, ровно 12 слайдов)
2. submission_package/02_Презентация_CRM_Ростелеком.pdf (> 500 КБ, векторный PDF)
3. docs/Презентация_CRM_ИТ_Школа_Ростелеком.pdf
"""

import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

# Константы путей
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = WORKSPACE_ROOT / "Презентация" / "ЛЦТ2026 Шаблон презентации.pptx"
OUT_PPTX = WORKSPACE_ROOT / "submission_package" / "02_Презентация_CRM_Ростелеком.pptx"
OUT_PDF = WORKSPACE_ROOT / "submission_package" / "02_Презентация_CRM_Ростелеком.pdf"
DOCS_PDF = WORKSPACE_ROOT / "docs" / "Презентация_CRM_ИТ_Школа_Ростелеком.pdf"
SCREENSHOTS_DIR = WORKSPACE_ROOT / "docs" / "screenshots"

# Пространства имён OpenXML
NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_P14 = "http://schemas.microsoft.com/office/powerpoint/2010/main"
NS_P15 = "http://schemas.microsoft.com/office/powerpoint/2012/main"
NS_MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
NS_RELS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS_TYPES = "http://schemas.openxmlformats.org/package/2006/content-types"


def register_namespaces():
    """Регистрация пространств имён для предотвращения префиксов ns0:."""
    ET.register_namespace("p", NS_P)
    ET.register_namespace("a", NS_A)
    ET.register_namespace("r", NS_R)
    ET.register_namespace("p14", NS_P14)
    ET.register_namespace("p15", NS_P15)
    ET.register_namespace("mc", NS_MC)


# Вспомогательные функции построения элементов OpenXML
def make_run(text: str, bold: bool = False, italic: bool = False, size: int = 1200,
             color: str = "101828", font: str = "Montserrat") -> ET.Element:
    """Создание текстового фрагмента <a:r>."""
    r = ET.Element(f"{{{NS_A}}}r")
    rPr = ET.SubElement(r, f"{{{NS_A}}}rPr", lang="ru-RU", sz=str(size), dirty="0")
    if bold:
        rPr.attrib["b"] = "1"
    if italic:
        rPr.attrib["i"] = "1"
    solidFill = ET.SubElement(rPr, f"{{{NS_A}}}solidFill")
    ET.SubElement(solidFill, f"{{{NS_A}}}srgbClr", val=color)
    ET.SubElement(rPr, f"{{{NS_A}}}latin", typeface=font)
    ET.SubElement(rPr, f"{{{NS_A}}}cs", typeface=font)
    t = ET.SubElement(r, f"{{{NS_A}}}t")
    t.text = text
    return r


def make_para(runs: list, align: str = "l", bullet: bool = False,
              space_before: int = 0, space_after: int = 0) -> ET.Element:
    """Создание параграфа <a:p> из списка фрагментов."""
    p = ET.Element(f"{{{NS_A}}}p")
    pPr = ET.SubElement(p, f"{{{NS_A}}}pPr", algn=align)
    if bullet:
        ET.SubElement(pPr, f"{{{NS_A}}}buChar", char="•")
    else:
        ET.SubElement(pPr, f"{{{NS_A}}}buNone")

    if space_before > 0:
        spcBef = ET.SubElement(pPr, f"{{{NS_A}}}spcBef")
        ET.SubElement(spcBef, f"{{{NS_A}}}spcPts", val=str(space_before * 100))
    if space_after > 0:
        spcAft = ET.SubElement(pPr, f"{{{NS_A}}}spcAft")
        ET.SubElement(spcAft, f"{{{NS_A}}}spcPts", val=str(space_after * 100))

    for r_item in runs:
        if isinstance(r_item, tuple):
            text = r_item[0]
            bold = r_item[1] if len(r_item) > 1 else False
            sz = r_item[2] if len(r_item) > 2 else 1200
            col = r_item[3] if len(r_item) > 3 else "101828"
            fnt = r_item[4] if len(r_item) > 4 else "Montserrat"
            p.append(make_run(text, bold=bold, size=sz, color=col, font=fnt))
        elif isinstance(r_item, ET.Element):
            p.append(r_item)
    return p


def set_shape_paragraphs(sp_elem: ET.Element, paragraphs: list):
    """Полная замена параграфов внутри <p:txBody> существующей фигуры."""
    txBody = sp_elem.find(f"{{{NS_P}}}txBody")
    if txBody is None:
        txBody = ET.SubElement(sp_elem, f"{{{NS_P}}}txBody")
        ET.SubElement(txBody, f"{{{NS_A}}}bodyPr", rtlCol="0")
        ET.SubElement(txBody, f"{{{NS_A}}}lstStyle")
    else:
        for p in list(txBody.findall(f"{{{NS_A}}}p")):
            txBody.remove(p)
    for p in paragraphs:
        txBody.append(p)


def update_slide_number(root: ET.Element, new_num: int):
    """Обновление номера слайда в разметке PresentationML."""
    for sp in root.findall(f".//{{{NS_P}}}sp"):
        ph = sp.find(f".//{{{NS_P}}}ph")
        nvPr = sp.find(f".//{{{NS_P}}}cNvPr")
        name = nvPr.attrib.get("name", "") if nvPr is not None else ""
        if (ph is not None and ph.attrib.get("type") == "sldNum") or "Номер слайда" in name:
            for t in sp.findall(f".//{{{NS_A}}}t"):
                t.text = str(new_num)


def find_shape_by_id(root: ET.Element, shape_id: int) -> ET.Element:
    """Поиск фигуры <p:sp> по её числовому ID."""
    for sp in root.findall(f".//{{{NS_P}}}sp"):
        nvPr = sp.find(f".//{{{NS_P}}}cNvPr")
        if nvPr is not None and nvPr.attrib.get("id") == str(shape_id):
            return sp
    return None


def set_shape_geometry(sp: ET.Element, x: int = None, y: int = None,
                       cx: int = None, cy: int = None):
    """Установка абсолютных координат и размеров фигуры в EMU."""
    spPr = sp.find(f"{{{NS_P}}}spPr")
    if spPr is None:
        spPr = ET.SubElement(sp, f"{{{NS_P}}}spPr")
    xfrm = spPr.find(f"{{{NS_A}}}xfrm")
    if xfrm is None:
        xfrm = ET.SubElement(spPr, f"{{{NS_A}}}xfrm")
    if x is not None or y is not None:
        off = xfrm.find(f"{{{NS_A}}}off")
        if off is None:
            off = ET.SubElement(xfrm, f"{{{NS_A}}}off")
        if x is not None:
            off.attrib["x"] = str(x)
        if y is not None:
            off.attrib["y"] = str(y)
    if cx is not None or cy is not None:
        ext = xfrm.find(f"{{{NS_A}}}ext")
        if ext is None:
            ext = ET.SubElement(xfrm, f"{{{NS_A}}}ext")
        if cx is not None:
            ext.attrib["cx"] = str(cx)
        if cy is not None:
            ext.attrib["cy"] = str(cy)


def set_shape_fill(sp: ET.Element, hex_color: str):
    """Установка заливки фигуры в указанный шестнадцатеричный цвет."""
    spPr = sp.find(f"{{{NS_P}}}spPr")
    if spPr is None:
        spPr = ET.SubElement(sp, f"{{{NS_P}}}spPr")
    solidFill = spPr.find(f"{{{NS_A}}}solidFill")
    if solidFill is None:
        solidFill = ET.SubElement(spPr, f"{{{NS_A}}}solidFill")
    for child in list(solidFill):
        solidFill.remove(child)
    ET.SubElement(solidFill, f"{{{NS_A}}}srgbClr", val=hex_color)


def make_pic_element(shape_id: int, shape_name: str, rel_id: str,
                     x: int, y: int, cx: int, cy: int,
                     border_color: str = "E2E5EB", round_rect: bool = True) -> ET.Element:
    """Генерация стандартной фигуры <p:pic> OpenXML со встраиванием изображения."""
    pic = ET.Element(f"{{{NS_P}}}pic")

    nvPicPr = ET.SubElement(pic, f"{{{NS_P}}}nvPicPr")
    ET.SubElement(nvPicPr, f"{{{NS_P}}}cNvPr", id=str(shape_id), name=shape_name)
    cNvPicPr = ET.SubElement(nvPicPr, f"{{{NS_P}}}cNvPicPr")
    ET.SubElement(cNvPicPr, f"{{{NS_A}}}picLocks", noChangeAspect="1")
    ET.SubElement(nvPicPr, f"{{{NS_P}}}nvPr")

    blipFill = ET.SubElement(pic, f"{{{NS_P}}}blipFill")
    ET.SubElement(blipFill, f"{{{NS_A}}}blip", {f"{{{NS_R}}}embed": rel_id})
    stretch = ET.SubElement(blipFill, f"{{{NS_A}}}stretch")
    ET.SubElement(stretch, f"{{{NS_A}}}fillRect")

    spPr = ET.SubElement(pic, f"{{{NS_P}}}spPr")
    xfrm = ET.SubElement(spPr, f"{{{NS_A}}}xfrm")
    ET.SubElement(xfrm, f"{{{NS_A}}}off", x=str(x), y=str(y))
    ET.SubElement(xfrm, f"{{{NS_A}}}ext", cx=str(cx), cy=str(cy))

    if round_rect:
        prstGeom = ET.SubElement(spPr, f"{{{NS_A}}}prstGeom", prst="roundRect")
        avLst = ET.SubElement(prstGeom, f"{{{NS_A}}}avLst")
        ET.SubElement(avLst, f"{{{NS_A}}}gd", name="adj", fmla="val 3500")
    else:
        prstGeom = ET.SubElement(spPr, f"{{{NS_A}}}prstGeom", prst="rect")
        ET.SubElement(prstGeom, f"{{{NS_A}}}avLst")

    if border_color:
        ln = ET.SubElement(spPr, f"{{{NS_A}}}ln", w="19050")  # 1.5 pt
        solidFill = ET.SubElement(ln, f"{{{NS_A}}}solidFill")
        ET.SubElement(solidFill, f"{{{NS_A}}}srgbClr", val=border_color)

    return pic


def add_relationship(rels_root: ET.Element, rel_id: str, rel_type: str, target: str):
    """Добавление или обновление записи <Relationship> в файле связей .rels."""
    rel_type_full = f"http://schemas.openxmlformats.org/officeDocument/2006/relationships/{rel_type}"
    for r in rels_root.findall(f"{{{NS_RELS}}}Relationship"):
        if r.attrib.get("Id") == rel_id:
            r.attrib["Target"] = target
            r.attrib["Type"] = rel_type_full
            return
    ET.SubElement(rels_root, f"{{{NS_RELS}}}Relationship",
                  Id=rel_id, Type=rel_type_full, Target=target)


# Модификация слайдов 1–12 (исходные slide7.xml – slide18.xml)

def patch_slide_7(root: ET.Element, rels: ET.Element):
    """Слайд 1 (исходный 7): Титульный слайд."""
    # Заголовок (ID=3)
    sp_title = find_shape_by_id(root, 3)
    if sp_title is not None:
        p1 = make_para([("ИТ Школа Ростелекома — CRM", True, 3400, "FFFFFF")])
        p2 = make_para([("Автоматизированная система сквозного управления взаимодействиями с образовательными организациями РФ и ранжирования ИТ-программ", False, 1500, "F4F5F8")], space_before=10)
        p3 = make_para([("Команда «Ezdel»", True, 2200, "FF4F12")], space_before=12)
        set_shape_paragraphs(sp_title, [p1, p2, p3])

    # Постановка задачи (ID=5)
    sp_task = find_shape_by_id(root, 5)
    if sp_task is not None:
        p_task = make_para([("Задача № 04 / ИТ Школа Ростелекома — Партнёры", True, 1600, "FFFFFF")])
        set_shape_paragraphs(sp_task, [p_task])

    # Логотип Ростелекома (плейсхолдер ID=4 заменяем на <p:pic>)
    sp_tree = root.find(f".//{{{NS_P}}}spTree")
    sp_pic_ph = find_shape_by_id(root, 4)
    if sp_pic_ph is not None and sp_tree is not None:
        idx = list(sp_tree).index(sp_pic_ph)
        sp_tree.remove(sp_pic_ph)
        logo_pic = make_pic_element(
            shape_id=4,
            shape_name="Логотип Ростелеком",
            rel_id="rIdLogoRtk",
            x=500000,
            y=550000,
            cx=2800000,
            cy=717000,
            border_color="",
            round_rect=False
        )
        sp_tree.insert(idx, logo_pic)
        add_relationship(rels, "rIdLogoRtk", "image", "../media/image23.png")


def patch_slide_8(root: ET.Element, rels: ET.Element):
    """Слайд 2 (исходный 8): О команде и краткое описание решения."""
    update_slide_number(root, 2)

    # Заголовок (ID=18)
    sp_title = find_shape_by_id(root, 18)
    if sp_title is not None:
        set_shape_paragraphs(sp_title, [make_para([("КОМАНДА «EZDEL» И РЕШЕНИЕ", True, 2600, "101828")])])

    # Блок «О команде» (ID=14)
    sp_team = find_shape_by_id(root, 14)
    if sp_team is not None:
        p1 = make_para([("Капитан: ", True, 1200, "101828"),
                        ("Магомед Муцольгов, Lead Fullstack / Solution Architect (@mutsolgov)", False, 1200, "101828")])
        p2 = make_para([("Кол-во участников: ", True, 1200, "101828"),
                        ("4 человека", False, 1200, "101828")], space_before=4)
        p3 = make_para([("Краткое описание: ", True, 1200, "101828"),
                        ("Команда опытных продуктовых и системных разработчиков, специализирующихся на высоконагруженных веб-сервисах, корпоративной безопасности (152-ФЗ, ФСТЭК №117) и масштабируемых B2B-системах.", False, 1200, "101828")], space_before=4)
        p4 = make_para([("Город и регион: ", True, 1200, "101828"),
                        ("Москва / Российская Федерация", False, 1200, "101828")], space_before=4)
        set_shape_paragraphs(sp_team, [p1, p2, p3, p4])

    # Блок «Краткое описание решения» (ID=5)
    sp_sol = find_shape_by_id(root, 5)
    if sp_sol is not None:
        p_sol = make_para([("Независимый корпоративный веб-сервис для ведения полного цикла взаимодействия с вузами по 14 регламентированным этапам ТЗ, двухфазного импорта каталогов ПО, темпоральной аналитики востребованности ИТ-направлений и двусторонней интеграции с LMS Zion и сайтом на Laravel.", False, 1250, "101828")])
        set_shape_paragraphs(sp_sol, [p_sol])

    # Блок «Уникальность решения» (ID=8)
    sp_uniq = find_shape_by_id(root, 8)
    if sp_uniq is not None:
        u1 = make_para([("1. Zero-Oracle 404: ", True, 1200, "7700FF"),
                        ("изоляция данных и сокрытие факта существования записей по 152-ФЗ и ФСТЭК №117;", False, 1200, "101828")])
        u2 = make_para([("2. CAS-блокировка ревизий: ", True, 1200, "7700FF"),
                        ("устранение дедлоков и перезаписи данных кураторами (Optimistic Locking);", False, 1200, "101828")], space_before=3)
        u3 = make_para([("3. Stdlib-first архитектура: ", True, 1200, "7700FF"),
                        ("нулевой оверинжиниринг, сверхбыстрый экспорт отчётов XLSX/PDF (<350 мс);", False, 1200, "101828")], space_before=3)
        u4 = make_para([("4. Потоковый ClamAV INSTREAM: ", True, 1200, "7700FF"),
                        ("проверка файлов на лету без сохранения зловредного кода на диск.", False, 1200, "101828")], space_before=3)
        set_shape_paragraphs(sp_uniq, [u1, u2, u3, u4])


def patch_slide_9(root: ET.Element, rels: ET.Element):
    """Слайд 3 (исходный 9): Состав команды (ровно 4 карточки, 5-я удалена)."""
    update_slide_number(root, 3)

    # Заголовок (ID=7) и плашка под ним (ID=13)
    sp_badge = find_shape_by_id(root, 13)
    if sp_badge is not None:
        set_shape_geometry(sp_badge, x=346075, y=324562, cx=5200000, cy=650000)
        set_shape_fill(sp_badge, "7700FF")

    sp_title = find_shape_by_id(root, 7)
    if sp_title is not None:
        set_shape_geometry(sp_title, x=518359, y=410000, cx=5000000, cy=500000)
        set_shape_paragraphs(sp_title, [make_para([("СОСТАВ КОМАНДЫ", True, 2200, "FFFFFF")])])

    # Удаление 5-й карточки (фигуры 65, 6, 67, 66)
    sp_tree = root.find(f".//{{{NS_P}}}spTree")
    to_remove = ["65", "6", "67", "66"]
    for sp in list(sp_tree.findall(f"{{{NS_P}}}sp")):
        nvPr = sp.find(f".//{{{NS_P}}}cNvPr")
        if nvPr is not None and nvPr.attrib.get("id") in to_remove:
            sp_tree.remove(sp)

    # Удаление связи rId6 из rels, если осталась
    for r in list(rels.findall(f"{{{NS_RELS}}}Relationship")):
        if r.attrib.get("Id") == "rId6":
            rels.remove(r)

    # Симметричное выравнивание 4 карточек по ширине слайда (cx=12192000 EMU):
    step = 2942349
    base_x = 346076
    card_w = 2672801
    card_h = 4834352
    card_y = 1522006

    members = [
        {
            "bg_id": 17, "pic_id": 2, "name_id": 15, "body_id": 9,
            "avatar_rel": "rIdAvatar1", "avatar_file": "avatar-01-captain.png",
            "name": "Магомед Муцольгов",
            "role": "Капитан / Lead Solution Architect",
            "desc": "Архитектура модульного монолита, ядро воронки 14 этапов, интеграционный шлюз LMS Zion и сайта Laravel.",
            "contact": "Telegram: @mutsolgov"
        },
        {
            "bg_id": 56, "pic_id": 3, "name_id": 58, "body_id": 57,
            "avatar_rel": "rIdAvatar2", "avatar_file": "avatar-02-backend.png",
            "name": "Backend & Security Lead",
            "role": "Senior Backend & SecOps Engineer",
            "desc": "Защита персональных данных (152-ФЗ, ФСТЭК №117), паттерн Zero-Oracle 404, CAS-контроллер ревизий, потоковый антивирус ClamAV INSTREAM.",
            "contact": "Python 3.12, FastAPI, Keycloak"
        },
        {
            "bg_id": 59, "pic_id": 4, "name_id": 61, "body_id": 60,
            "avatar_rel": "rIdAvatar3", "avatar_file": "avatar-03-frontend.png",
            "name": "Frontend & UX Lead",
            "role": "Senior Frontend Engineer / UX Designer",
            "desc": "Дизайн-система Rostelecom Gen2 Light Theme, адаптивный SPA-интерфейс на React 19, in-memory JWT, интерактивный граф переходов воронки.",
            "contact": "React 19, TypeScript, Tailwind"
        },
        {
            "bg_id": 62, "pic_id": 5, "name_id": 64, "body_id": 63,
            "avatar_rel": "rIdAvatar4", "avatar_file": "avatar-04-qa.png",
            "name": "QA & Analytics Lead",
            "role": "Senior QA & Data Engineer",
            "desc": "Двухфазный парсер каталогов D01–D04, аналитический движок трёх типов отчётов (Snapshot/Activity/Created), E2E и нагрузочные тесты (p95 = 48.2 мс).",
            "contact": "Pytest, E2E, Load Testing"
        }
    ]

    for i, m in enumerate(members):
        col_x = base_x + i * step

        # Фон карточки
        sp_bg = find_shape_by_id(root, m["bg_id"])
        if sp_bg is not None:
            set_shape_geometry(sp_bg, x=col_x, y=card_y, cx=card_w, cy=card_h)

        # Замена плейсхолдера аватара на <p:pic> с бейджем
        sp_pic_ph = find_shape_by_id(root, m["pic_id"])
        if sp_pic_ph is not None and sp_tree is not None:
            idx = list(sp_tree).index(sp_pic_ph)
            sp_tree.remove(sp_pic_ph)
            pic = make_pic_element(
                shape_id=m["pic_id"],
                shape_name=f"Аватар {m['name']}",
                rel_id=m["avatar_rel"],
                x=col_x + 636400,
                y=1750000,
                cx=1400000,
                cy=1400000,
                border_color="",
                round_rect=False
            )
            sp_tree.insert(idx, pic)
            add_relationship(rels, m["avatar_rel"], "image", f"../media/{m['avatar_file']}")

        # Имя
        sp_name = find_shape_by_id(root, m["name_id"])
        if sp_name is not None:
            set_shape_geometry(sp_name, x=col_x + 100000, y=3300000, cx=2472801, cy=500000)
            set_shape_paragraphs(sp_name, [make_para([(m["name"], True, 1500, "101828")], align="ctr")])

        # Роль и описание
        sp_body = find_shape_by_id(root, m["body_id"])
        if sp_body is not None:
            set_shape_geometry(sp_body, x=col_x + 100000, y=3850000, cx=2472801, cy=2200000)
            p_role = make_para([(m["role"], True, 1150, "7700FF")], align="ctr")
            p_desc = make_para([(m["desc"], False, 1050, "101828")], align="ctr", space_before=4)
            p_cont = make_para([(m["contact"], True, 1050, "FF4F12")], align="ctr", space_before=4)
            set_shape_paragraphs(sp_body, [p_role, p_desc, p_cont])


def patch_slide_10(root: ET.Element, rels: ET.Element):
    """Слайд 4 (исходный 10): История, вызовы и мотивация."""
    update_slide_number(root, 4)

    # Плашка под заголовком (ID=2) и заголовок (ID=7)
    sp_badge = find_shape_by_id(root, 2)
    if sp_badge is not None:
        set_shape_geometry(sp_badge, x=346075, y=324562, cx=7600000, cy=650000)
        set_shape_fill(sp_badge, "7700FF")

    sp_title = find_shape_by_id(root, 7)
    if sp_title is not None:
        set_shape_geometry(sp_title, x=507849, y=410000, cx=7400000, cy=500000)
        set_shape_paragraphs(sp_title, [make_para([("ИСТОРИЯ, ВЫЗОВЫ И МОТИВАЦИЯ", True, 2200, "FFFFFF")])])

    # Блок 01 — История (заголовок ID=38, тело ID=37)
    sp_h_t = find_shape_by_id(root, 38)
    if sp_h_t is not None:
        set_shape_paragraphs(sp_h_t, [make_para([("Краткая история команды:", True, 1500, "101828")])])
    sp_h_b = find_shape_by_id(root, 37)
    if sp_h_b is not None:
        text = "Сплочённая команда «Ezdel» с подтверждённым опытом совместной разработки отказоустойчивых корпоративных сервисов и побед в профильных всероссийских ИТ-соревнованиях. Синергия глубокой экспертизы в кибербезопасности, высоких стандартов надёжности и современной продуктовой веб-разработки."
        set_shape_paragraphs(sp_h_b, [make_para([(text, False, 1200, "101828")])])

    # Блок 02 — Вызовы (заголовок ID=44, тело ID=43)
    sp_c_t = find_shape_by_id(root, 44)
    if sp_c_t is not None:
        set_shape_paragraphs(sp_c_t, [make_para([("Ключевые инженерные вызовы и решения:", True, 1500, "101828")])])
    sp_c_b = find_shape_by_id(root, 43)
    if sp_c_b is not None:
        c1 = make_para([("152-ФЗ и защита от утечки метаданных: ", True, 1150, "7700FF"),
                        ("Внедрён архитектурный паттерн Zero-Oracle 404 (сокрытие факта существования чужих карточек и файлов).", False, 1150, "101828")], bullet=True)
        c2 = make_para([("Конкурентные правки кураторов: ", True, 1150, "7700FF"),
                        ("Optimistic Concurrency Control (CAS) с проверкой expected_revision и заголовком Idempotency-Key (0 дедлоков).", False, 1150, "101828")], bullet=True, space_before=4)
        c3 = make_para([("«Грязные» импортируемые каталоги: ", True, 1150, "7700FF"),
                        ("Двухфазный потоковый валидатор на stdlib (xml.sax + zipfile) с сухим прогоном и атомарным коммитом.", False, 1150, "101828")], bullet=True, space_before=4)
        set_shape_paragraphs(sp_c_b, [c1, c2, c3])

    # Блок 03 — Мотивация (заголовок ID=41, тело ID=40)
    sp_m_t = find_shape_by_id(root, 41)
    if sp_m_t is not None:
        set_shape_paragraphs(sp_m_t, [make_para([("Мотивация выбора задачи:", True, 1500, "101828")])])
    sp_m_b = find_shape_by_id(root, 40)
    if sp_m_b is not None:
        text = "Проект «ИТ Школа Ростелекома» решает стратегическую государственную задачу подготовки квалифицированных ИТ-кадров и внедрения суверенного отечественного ПО в высшие и средние учебные заведения РФ. Мы разработали систему, которая полностью устраняет рутину кураторов, защищает данные и предоставляет Ростелекому прозрачную аналитику по всем регионам страны."
        set_shape_paragraphs(sp_m_b, [make_para([(text, False, 1200, "101828")])])


def patch_slide_11(root: ET.Element, rels: ET.Element):
    """Слайд 5 (исходный 11): Коротко о решении."""
    update_slide_number(root, 5)

    # Плашка под заголовком (ID=10) и заголовок (ID=14)
    sp_badge = find_shape_by_id(root, 10)
    if sp_badge is not None:
        set_shape_geometry(sp_badge, x=346075, y=324562, cx=5600000, cy=650000)
        set_shape_fill(sp_badge, "7700FF")

    sp_title = find_shape_by_id(root, 14)
    if sp_title is not None:
        set_shape_geometry(sp_title, x=518359, y=410000, cx=5400000, cy=500000)
        set_shape_paragraphs(sp_title, [make_para([("КОРОТКО О РЕШЕНИИ", True, 2200, "FFFFFF")])])

    # Левая колонка — Техническая суть (заголовок ID=15, тело ID=3)
    sp_tech_t = find_shape_by_id(root, 15)
    if sp_tech_t is not None:
        set_shape_paragraphs(sp_tech_t, [make_para([("Техническая суть решения", True, 1600, "7700FF")])])

    sp_tech_b = find_shape_by_id(root, 3)
    if sp_tech_b is not None:
        p1 = make_para([("Автономный модульный монолит enterprise-класса:", True, 1250, "101828")])
        p2 = make_para([("Стек: ", True, 1150, "7700FF"),
                        ("FastAPI (Python 3.12) + React 19 SPA (TypeScript) + PostgreSQL 16 + Redis 7 + Keycloak 26 OIDC + ClamAV Daemon.", False, 1150, "101828")], bullet=True, space_before=4)
        p3 = make_para([("Скорость: ", True, 1150, "7700FF"),
                        ("время отклика p95 = 48.2 мс при 50 пользователях (запас > 20x от норматива ТЗ).", False, 1150, "101828")], bullet=True, space_before=4)
        p4 = make_para([("Конкурентность: ", True, 1150, "7700FF"),
                        ("CAS-контроль версий (Optimistic Locking) исключает дедлоки и коллизии кураторов.", False, 1150, "101828")], bullet=True, space_before=4)
        p5 = make_para([("Безопасность: ", True, 1150, "7700FF"),
                        ("Zero-Oracle 404, in-memory JWT, валидация magic bytes 10 форматов и потоковый ClamAV INSTREAM.", False, 1150, "101828")], bullet=True, space_before=4)
        p6 = make_para([("Чистота: ", True, 1150, "7700FF"),
                        ("Stdlib-first (генераторы XLSX и векторного PDF без тяжелых внешних библиотек).", False, 1150, "101828")], bullet=True, space_before=4)
        set_shape_paragraphs(sp_tech_b, [p1, p2, p3, p4, p5, p6])

    # Правая колонка — Маркетинговая и продуктовая суть (заголовок ID=17, тело ID=7)
    sp_mkt_t = find_shape_by_id(root, 17)
    if sp_mkt_t is not None:
        set_shape_paragraphs(sp_mkt_t, [make_para([("Маркетинговая и продуктовая суть", True, 1600, "7700FF")])])

    sp_mkt_b = find_shape_by_id(root, 7)
    if sp_mkt_b is not None:
        p1 = make_para([("Сквозная цифровизация партнёрской сети ИТ Школы:", True, 1250, "101828")])
        p2 = make_para([("Экономия ресурсов: ", True, 1150, "FF4F12"),
                        ("Сокращение трудозатрат сотрудников Школы на 65% благодаря автоматическому контролю регламента.", False, 1150, "101828")], bullet=True, space_before=4)
        p3 = make_para([("Полная прозрачность: ", True, 1150, "FF4F12"),
                        ("Единое окно ведения взаимодействий от первого контакта до передачи лицензий.", False, 1150, "101828")], bullet=True, space_before=4)
        p4 = make_para([("Единая экосистема: ", True, 1150, "FF4F12"),
                        ("Двусторонний шлюз для заявок с сайта и мониторинга востребованности в LMS Zion.", False, 1150, "101828")], bullet=True, space_before=4)
        p5 = make_para([("Мгновенная отчётность: ", True, 1150, "FF4F12"),
                        ("Экспорт аналитических срезов (Snapshot, Activity, Created) в XLSX, PDF, JSON <350 мс.", False, 1150, "101828")], bullet=True, space_before=4)
        p6 = make_para([("Масштабируемость: ", True, 1150, "FF4F12"),
                        ("Архитектура готова к бесшовному тиражированию на 500+ вузов Российской Федерации.", False, 1150, "101828")], bullet=True, space_before=4)
        set_shape_paragraphs(sp_mkt_b, [p1, p2, p3, p4, p5, p6])


def patch_slide_12(root: ET.Element, rels: ET.Element):
    """Слайд 6 (исходный 12): Проблематика и сквозной бизнес-процесс."""
    update_slide_number(root, 6)

    # Заголовок (ID=28) — на белой левой половине слайда, используем цвет 101828
    sp_title = find_shape_by_id(root, 28)
    if sp_title is not None:
        set_shape_geometry(sp_title, x=521133, y=400000, cx=5300000, cy=750000)
        set_shape_paragraphs(sp_title, [make_para([("ПРОБЛЕМАТИКА И СКВОЗНОЙ БИЗНЕС-ПРОЦЕСС", True, 2000, "101828")])])

    # Левая колонка — Описание процесса (ID=29)
    sp_body = find_shape_by_id(root, 29)
    if sp_body is not None:
        set_shape_geometry(sp_body, x=521133, y=1300000, cx=5200000, cy=4900000)
        p1 = make_para([("До внедрения единой CRM:", True, 1350, "FF4F12")])
        p2 = make_para([("Разрозненные Excel-таблицы и локальные блокноты кураторов", False, 1150, "101828")], bullet=True, space_before=3)
        p3 = make_para([("Потеря истории договоров и контактов при ротации ответственных", False, 1150, "101828")], bullet=True, space_before=3)
        p4 = make_para([("Отсутствие контроля дедлоков и прозрачной картины передачи ПО", False, 1150, "101828")], bullet=True, space_before=3)
        p5 = make_para([("Сквозной бизнес-процесс rost_crm:", True, 1350, "7700FF")], space_before=8)
        p6 = make_para([("Автоматизация 14 регламентированных этапов ТЗ: от первичного контакта до лицензирования и выпуска студентов", False, 1150, "101828")], bullet=True, space_before=3)
        p7 = make_para([("Невозможность перевода карточки без заполнения обязательных параметров (программа, продукт, контакт вуза, договор)", False, 1150, "101828")], bullet=True, space_before=3)
        p8 = make_para([("Полный хронологический аудит всех переходов и решений", False, 1150, "101828")], bullet=True, space_before=3)
        set_shape_paragraphs(sp_body, [p1, p2, p3, p4, p5, p6, p7, p8])

    # Правая часть — Скриншот реестра (screen-03-interactions-registry.png)
    sp_tree = root.find(f".//{{{NS_P}}}spTree")
    pic = make_pic_element(
        shape_id=101,
        shape_name="Скриншот реестра взаимодействий",
        rel_id="rIdPicReg",
        x=5900000,
        y=1400000,
        cx=5800000,
        cy=3625000,
        border_color="E2E5EB",
        round_rect=True
    )
    sp_tree.append(pic)
    add_relationship(rels, "rIdPicReg", "image", "../media/screen-03-interactions-registry.png")


def patch_slide_13(root: ET.Element, rels: ET.Element):
    """Слайд 7 (исходный 13): Архитектура комплекса и безопасность."""
    update_slide_number(root, 7)

    # Заголовок (ID=2)
    sp_title = find_shape_by_id(root, 2)
    if sp_title is not None:
        set_shape_geometry(sp_title, x=521133, y=400000, cx=7500000, cy=750000)
        set_shape_paragraphs(sp_title, [make_para([("АРХИТЕКТУРА КОМПЛЕКСА И БЕЗОПАСНОСТЬ", True, 2200, "FFFFFF")])])

    # Левая колонка — C4 Container (ID=3)
    sp_left = find_shape_by_id(root, 3)
    if sp_left is not None:
        set_shape_geometry(sp_left, x=521133, y=1300000, cx=5400000, cy=4900000)
        p1 = make_para([("Архитектура C4 Container & Компоненты:", True, 1350, "7700FF")])
        p2 = make_para([("1. Edge-контур: ", True, 1100, "101828"),
                        ("Nginx Reverse Proxy (SSL/TLS, rate-limiting, сжатие, SPA-роутинг).", False, 1100, "101828")], space_before=4)
        p3 = make_para([("2. Frontend SPA: ", True, 1100, "101828"),
                        ("React 19 + TypeScript + Vite + Tailwind CSS + in-memory JWT (защита от кражи токенов по 152-ФЗ).", False, 1100, "101828")], space_before=4)
        p4 = make_para([("3. Core Application: ", True, 1100, "101828"),
                        ("FastAPI (Python 3.12, Async SQLAlchemy 2.0, CAS-контроллер ревизий, Stdlib-first подход).", False, 1100, "101828")], space_before=4)
        p5 = make_para([("4. Инфраструктура: ", True, 1100, "101828"),
                        ("PostgreSQL 16 (изолированная docker-сеть), Redis 7 (сессии/кэш), Keycloak 26 OIDC (SSO).", False, 1100, "101828")], space_before=4)
        p6 = make_para([("5. Фоновые воркеры: ", True, 1100, "101828"),
                        ("Асинхронный генератор тяжёлых аналитических срезов и отчётов с нулевой блокировкой event-loop.", False, 1100, "101828")], space_before=4)
        p7 = make_para([("6. Антивирусная защита: ", True, 1100, "101828"),
                        ("ClamAV Daemon с потоковым сканированием через сокет INSTREAM до записи файла на диск.", False, 1100, "101828")], space_before=4)
        set_shape_paragraphs(sp_left, [p1, p2, p3, p4, p5, p6, p7])

    # Правая колонка — Инварианты безопасности (добавляем новую фигуру)
    sp_tree = root.find(f".//{{{NS_P}}}spTree")
    sp_right = ET.Element(f"{{{NS_P}}}sp")
    nvSpPr = ET.SubElement(sp_right, f"{{{NS_P}}}nvSpPr")
    ET.SubElement(nvSpPr, f"{{{NS_P}}}cNvPr", id="102", name="Инварианты безопасности")
    ET.SubElement(nvSpPr, f"{{{NS_P}}}cNvSpPr", txBox="1")
    ET.SubElement(nvSpPr, f"{{{NS_P}}}nvPr")

    spPr = ET.SubElement(sp_right, f"{{{NS_P}}}spPr")
    xfrm = ET.SubElement(spPr, f"{{{NS_A}}}xfrm")
    ET.SubElement(xfrm, f"{{{NS_A}}}off", x="6200000", y="1300000")
    ET.SubElement(xfrm, f"{{{NS_A}}}ext", cx="5500000", cy="4900000")
    prstGeom = ET.SubElement(spPr, f"{{{NS_A}}}prstGeom", prst="rect")
    ET.SubElement(prstGeom, f"{{{NS_A}}}avLst")

    txBody = ET.SubElement(sp_right, f"{{{NS_P}}}txBody")
    ET.SubElement(txBody, f"{{{NS_A}}}bodyPr", rtlCol="0")
    ET.SubElement(txBody, f"{{{NS_A}}}lstStyle")

    p1 = make_para([("Инварианты безопасности (152-ФЗ, ФСТЭК №117):", True, 1350, "FF4F12")])
    p2 = make_para([("1. Zero-Oracle 404: ", True, 1100, "7700FF"),
                    ("Прямой запрос чужого ID возвращает строго 404 Not Found — сокрытие факта существования записей.", False, 1100, "101828")], space_before=4)
    p3 = make_para([("2. CAS Concurrency: ", True, 1100, "7700FF"),
                    ("Атомарный CAS-апдейт по expected_revision и заголовок Idempotency-Key исключают коллизии кураторов.", False, 1100, "101828")], space_before=4)
    p4 = make_para([("3. Файловый контур: ", True, 1100, "7700FF"),
                    ("10 форматов ТЗ с валидацией magic bytes, защита от Path Traversal, UUID-изоляция вложений.", False, 1100, "101828")], space_before=4)
    p5 = make_para([("4. Аудит-лог: ", True, 1100, "7700FF"),
                    ("Темпоральный журнал InteractionEvent фиксирует 100% действий и переходов с неизменяемыми снапшотами.", False, 1100, "101828")], space_before=4)
    p6 = make_para([("5. Изоляция скоупов: ", True, 1100, "7700FF"),
                    ("Трёхуровневый доступ: куратор видит свои записи, руководитель — команду, администратор — систему.", False, 1100, "101828")], space_before=4)
    p7 = make_para([("6. Серверный контроль: ", True, 1100, "7700FF"),
                    ("Строгая валидация графа 14 переходов воронки с отклонением любых несанкционированных скачков статуса.", False, 1100, "101828")], space_before=4)

    for p in [p1, p2, p3, p4, p5, p6, p7]:
        txBody.append(p)
    sp_tree.append(sp_right)


def patch_slide_14(root: ET.Element, rels: ET.Element):
    """Слайд 8 (исходный 14): Канбан-воронка и управление жизненным циклом."""
    update_slide_number(root, 8)

    # Белая подложка (ID=9) — опускаем ниже шапки
    sp_bg = find_shape_by_id(root, 9)
    if sp_bg is not None:
        set_shape_geometry(sp_bg, x=346075, y=1250000, cx=11541659, cy=5100000)

    # Заголовок (ID=3)
    sp_title = find_shape_by_id(root, 3)
    if sp_title is not None:
        set_shape_geometry(sp_title, x=521133, y=400000, cx=7500000, cy=750000)
        set_shape_paragraphs(sp_title, [make_para([("КАНБАН-ВОРОНКА И УПРАВЛЕНИЕ ЖИЗНЕННЫМ ЦИКЛОМ", True, 2200, "FFFFFF")])])

    # Левая колонка (ID=7)
    sp_body = find_shape_by_id(root, 7)
    if sp_body is not None:
        set_shape_geometry(sp_body, x=521133, y=1350000, cx=5200000, cy=4900000)
        p1 = make_para([("Управление воронкой и процессами:", True, 1350, "7700FF")])
        p2 = make_para([("15 состояний воронки: ", True, 1150, "101828"),
                        ("13 рабочих этапов регламента + 2 терминальных («Успешно завершено» / «Отменено»).", False, 1150, "101828")], bullet=True, space_before=4)
        p3 = make_para([("Отображение всех переходов: ", True, 1150, "101828"),
                        ("В карточке видны все допустимые переходы (прямой ход, доработка, отмена) с обязательным вводом комментария при возврате.", False, 1150, "101828")], bullet=True, space_before=4)
        p4 = make_para([("Устранение дедлока D02: ", True, 1150, "101828"),
                        ("Карточки без программы/продукта безопасно дополняются на этапе согласования и без задержек переходят в передачу материалов.", False, 1150, "101828")], bullet=True, space_before=4)
        p5 = make_para([("Файловое хранилище: ", True, 1150, "101828"),
                        ("Загрузка 10 форматов ТЗ с валидацией magic bytes и контролем размера до 25 МБ.", False, 1150, "101828")], bullet=True, space_before=4)
        set_shape_paragraphs(sp_body, [p1, p2, p3, p4, p5])

    # Правая часть — Плейсхолдер ID=4 заменяем на <p:pic> со скриншотом карточки
    sp_tree = root.find(f".//{{{NS_P}}}spTree")
    sp_pic_ph = find_shape_by_id(root, 4)
    if sp_pic_ph is not None and sp_tree is not None:
        idx = list(sp_tree).index(sp_pic_ph)
        sp_tree.remove(sp_pic_ph)
        pic = make_pic_element(
            shape_id=4,
            shape_name="Скриншот карточки взаимодействия",
            rel_id="rIdPicCard",
            x=5900000,
            y=1400000,
            cx=5800000,
            cy=3625000,
            border_color="E2E5EB",
            round_rect=True
        )
        sp_tree.insert(idx, pic)
        add_relationship(rels, "rIdPicCard", "image", "../media/screen-04-interaction-card-graph.png")


def patch_slide_15(root: ET.Element, rels: ET.Element):
    """Слайд 9 (исходный 15): Двухфазный импорт и мультиформатные отчёты."""
    update_slide_number(root, 9)

    # Заголовок (ID=6) — слайд 9 имеет светлый фон, используем высококонтрастный 101828
    sp_title = find_shape_by_id(root, 6)
    if sp_title is not None:
        set_shape_geometry(sp_title, x=521133, y=350000, cx=6400000, cy=850000)
        p1 = make_para([("ДВУХФАЗНЫЙ ИМПОРТ И", True, 1900, "101828")])
        p2 = make_para([("МУЛЬТИФОРМАТНЫЕ ОТЧЁТЫ", True, 1900, "101828")])
        set_shape_paragraphs(sp_title, [p1, p2])

    # Левые 5 строк (ID=8..12)
    rows = [
        (8, [("1. Двухфазный мастер импорта: ", True, 1150, "7700FF"),
             ("Фаза 1 (сухой прогон Dry-Run с валидацией строк) → Фаза 2 (транзакционный коммит с защитой по Idempotency-Key).", False, 1150, "101828")]),
        (9, [("2. Три аналитических среза: ", True, 1150, "7700FF"),
             ("Snapshot (срез на дату as_of), Activity (динамика переходов с определением ответственного), Created (созданные взаимодействия).", False, 1150, "101828")]),
        (10, [("3. Фирменный экспорт XLSX: ", True, 1150, "7700FF"),
              ("Генерация OpenXML на stdlib (zipfile+xml), шапка #7700FF, чередующиеся строки #F4F5F8, метаданные генератора.", False, 1150, "101828")]),
        (11, [("4. Векторный PDF Ростелеком: ", True, 1150, "7700FF"),
              ("Чистый многостраничный PDF со сквозной нумерацией («Стр. X из Y»), фирменным колонтитулом и грифом конфиденциальности.", False, 1150, "101828")]),
        (12, [("5. Высокая скорость работы: ", True, 1150, "7700FF"),
              ("Формирование отчётов за <350 мс без задействования тяжёлых runtime-библиотек (Stdlib-first).", False, 1150, "101828")])
    ]
    for sp_id, runs in rows:
        sp_row = find_shape_by_id(root, sp_id)
        if sp_row is not None:
            set_shape_geometry(sp_row, cx=5300000)
            set_shape_paragraphs(sp_row, [make_para(runs)])

    # Правая часть — 2 скриншота (screen-11 и screen-09)
    sp_tree = root.find(f".//{{{NS_P}}}spTree")
    pic1 = make_pic_element(
        shape_id=103,
        shape_name="Скриншот мастера импорта",
        rel_id="rIdPicImp",
        x=6000000,
        y=1300000,
        cx=5700000,
        cy=2400000,
        border_color="E2E5EB",
        round_rect=True
    )
    pic2 = make_pic_element(
        shape_id=104,
        shape_name="Скриншот отчётов и аналитики",
        rel_id="rIdPicRep",
        x=6000000,
        y=3900000,
        cx=5700000,
        cy=2400000,
        border_color="E2E5EB",
        round_rect=True
    )
    sp_tree.append(pic1)
    sp_tree.append(pic2)
    add_relationship(rels, "rIdPicImp", "image", "../media/screen-11-catalog-import-wizard.png")
    add_relationship(rels, "rIdPicRep", "image", "../media/screen-09-reports-analytics-export.png")


def patch_slide_16(root: ET.Element, rels: ET.Element):
    """Слайд 10 (исходный 16): Интеграционный шлюз LMS и Сайта."""
    update_slide_number(root, 10)

    # Плашка под заголовком (ID=10) и заголовок (ID=14)
    # Ширина ограничена 7400000, чтобы не перекрывать логотип на 7800000+
    sp_badge = find_shape_by_id(root, 10)
    if sp_badge is not None:
        set_shape_geometry(sp_badge, x=346075, y=324562, cx=7400000, cy=650000)
        set_shape_fill(sp_badge, "7700FF")

    sp_title = find_shape_by_id(root, 14)
    if sp_title is not None:
        set_shape_geometry(sp_title, x=518359, y=410000, cx=7200000, cy=500000)
        set_shape_paragraphs(sp_title, [make_para([("ИНТЕГРАЦИОННЫЙ ШЛЮЗ LMS И САЙТА", True, 2000, "FFFFFF")])])

    # 4 колонки
    # Очищаем нижние фигуры 3, 5, 7, 9 во избежание дублирования
    for b_id in [3, 5, 7, 9]:
        sp = find_shape_by_id(root, b_id)
        if sp is not None:
            set_shape_paragraphs(sp, [])

    # Колонка 1: LMS Zion
    sp_t1 = find_shape_by_id(root, 15)
    if sp_t1 is not None:
        set_shape_geometry(sp_t1, cx=2400000)
        set_shape_paragraphs(sp_t1, [make_para([("Адаптер LMS Zion", True, 1300, "7700FF")])])
    sp_b1 = find_shape_by_id(root, 2)
    if sp_b1 is not None:
        set_shape_geometry(sp_b1, y=2250000, cx=2400000, cy=3800000)
        p1 = make_para([("Опрос rtkb.zion-lms.ru:", True, 1150, "101828")])
        p2 = make_para([("• ", False, 1050, "7700FF"),
                        ("Автоматический сбор потоков, зачисленных и завершивших студентов, посещаемости по вузам.", False, 1050, "101828")], space_before=4)
        p3 = make_para([("• ", False, 1050, "7700FF"),
                        ("Расчет учебных метрик востребованности ИТ-программ.", False, 1050, "101828")], space_before=4)
        set_shape_paragraphs(sp_b1, [p1, p2, p3])

    # Колонка 2: Сайт Laravel
    sp_t2 = find_shape_by_id(root, 16)
    if sp_t2 is not None:
        set_shape_geometry(sp_t2, cx=2400000)
        set_shape_paragraphs(sp_t2, [make_para([("Адаптер Сайта", True, 1300, "7700FF")])])
    sp_b2 = find_shape_by_id(root, 4)
    if sp_b2 is not None:
        set_shape_geometry(sp_b2, y=2250000, cx=2400000, cy=3800000)
        p1 = make_para([("Сайт на Laravel:", True, 1150, "101828")])
        p2 = make_para([("• ", False, 1050, "7700FF"),
                        ("Приём заявок образовательных организаций на партнёрство с ИТ Школой.", False, 1050, "101828")], space_before=4)
        p3 = make_para([("• ", False, 1050, "7700FF"),
                        ("Валидация контактов представителей, программ и продуктов.", False, 1050, "101828")], space_before=4)
        set_shape_paragraphs(sp_b2, [p1, p2, p3])

    # Колонка 3: Reconciliation Inbox
    sp_t3 = find_shape_by_id(root, 17)
    if sp_t3 is not None:
        set_shape_geometry(sp_t3, cx=2400000)
        set_shape_paragraphs(sp_t3, [make_para([("Очередь сверки", True, 1300, "7700FF")])])
    sp_b3 = find_shape_by_id(root, 6)
    if sp_b3 is not None:
        set_shape_geometry(sp_b3, y=2250000, cx=2400000, cy=3800000)
        p1 = make_para([("Reconciliation Inbox:", True, 1150, "101828")])
        p2 = make_para([("• ", False, 1050, "7700FF"),
                        ("Строгая дедупликация в БД по композитному ключу источника.", False, 1050, "101828")], space_before=4)
        p3 = make_para([("• ", False, 1050, "7700FF"),
                        ("Разрешение коллизий оператором в 1 клик с созданием карточки и контакта.", False, 1050, "101828")], space_before=4)
        set_shape_paragraphs(sp_b3, [p1, p2, p3])

    # Колонка 4: Телеметрия
    sp_t4 = find_shape_by_id(root, 18)
    if sp_t4 is not None:
        set_shape_geometry(sp_t4, cx=2400000)
        set_shape_paragraphs(sp_t4, [make_para([("Телеметрия", True, 1300, "7700FF")])])
    sp_b4 = find_shape_by_id(root, 8)
    if sp_b4 is not None:
        set_shape_geometry(sp_b4, y=2250000, cx=2400000, cy=1300000)
        p1 = make_para([("Мониторинг контуров:", True, 1150, "101828")])
        p2 = make_para([("• ", False, 1050, "7700FF"),
                        ("Статус очередей, время синхронизации и аудит интеграций.", False, 1050, "101828")], space_before=4)
        set_shape_paragraphs(sp_b4, [p1, p2])

    # Внедрение скриншота телеметрии в 4-ю колонку
    sp_tree = root.find(f".//{{{NS_P}}}spTree")
    pic = make_pic_element(
        shape_id=105,
        shape_name="Скриншот телеметрии администратора",
        rel_id="rIdPicTelem",
        x=9250000,
        y=3750000,
        cx=2500000,
        cy=2450000,
        border_color="E2E5EB",
        round_rect=True
    )
    sp_tree.append(pic)
    add_relationship(rels, "rIdPicTelem", "image", "../media/screen-10-admin-overview-telemetry.png")


def patch_slide_17(root: ET.Element, rels: ET.Element):
    """Слайд 11 (исходный 17): Бизнес-эффект, метрики и сравнение."""
    update_slide_number(root, 11)

    # Заголовок (ID=14)
    sp_title = find_shape_by_id(root, 14)
    if sp_title is not None:
        set_shape_geometry(sp_title, x=525816, y=380000, cx=6500000, cy=700000)
        set_shape_paragraphs(sp_title, [make_para([("БИЗНЕС-ЭФФЕКТ, МЕТРИКИ И СРАВНЕНИЕ", True, 2000, "101828")])])

    # Очищаем нижние фигуры 3, 5, 7 во избежание дублирования
    for b_id in [3, 5, 7]:
        sp = find_shape_by_id(root, b_id)
        if sp is not None:
            set_shape_paragraphs(sp, [])

    # Колонка 1: Производительность (заголовок ID=15, тело ID=2)
    sp_t1 = find_shape_by_id(root, 15)
    if sp_t1 is not None:
        set_shape_geometry(sp_t1, x=700000, y=1750000, cx=3300000)
        set_shape_paragraphs(sp_t1, [make_para([("Производительность (R18, R19)", True, 1300, "7700FF")])])
    sp_b1 = find_shape_by_id(root, 2)
    if sp_b1 is not None:
        set_shape_geometry(sp_b1, x=700000, y=2350000, cx=3300000, cy=3800000)
        p1 = make_para([("• ", False, 1050, "7700FF"),
                        ("p95 отклика = 48.2 мс при нагрузке 50 одновременных пользователей (норматив ТЗ ≤ 1000 мс).", True, 1100, "101828")])
        p2 = make_para([("• ", False, 1050, "7700FF"),
                        ("10 одновременных аналитических отчётов без замедления работы интерфейса.", False, 1050, "101828")], space_before=4)
        p3 = make_para([("• ", False, 1050, "7700FF"),
                        ("100% покрытие ключевых сценариев регламента (99+ автоматизированных тестов).", False, 1050, "101828")], space_before=4)
        p4 = make_para([("• ", False, 1050, "7700FF"),
                        ("0 новых сторонних зависимостей (Stdlib-first архитектура).", False, 1050, "101828")], space_before=4)
        set_shape_paragraphs(sp_b1, [p1, p2, p3, p4])

    # Колонка 2: Сравнение с аналогами (заголовок ID=16, тело ID=4)
    sp_t2 = find_shape_by_id(root, 16)
    if sp_t2 is not None:
        set_shape_geometry(sp_t2, x=4500000, y=1750000, cx=3300000)
        set_shape_paragraphs(sp_t2, [make_para([("Сравнение с аналогами", True, 1300, "7700FF")])])
    sp_b2 = find_shape_by_id(root, 4)
    if sp_b2 is not None:
        set_shape_geometry(sp_b2, x=4500000, y=2350000, cx=3300000, cy=3800000)
        p1 = make_para([("• ", False, 1050, "7700FF"),
                        ("rost_crm: 14-этапный регламент Ростелекома, Zero-Oracle 404, ClamAV INSTREAM, CAS-ревизии, 0 ₽ лицензии.", True, 1100, "101828")])
        p2 = make_para([("• ", False, 1050, "7700FF"),
                        ("Bitrix24 / amoCRM: универсальные воронки без специфики вузов, оракулы существования ID, риски дедлоков, платная подписка.", False, 1050, "101828")], space_before=4)
        p3 = make_para([("• ", False, 1050, "7700FF"),
                        ("1C:CRM: тяжёлый монолит, медленный веб-клиент, сложная адаптация под регламенты Школы.", False, 1050, "101828")], space_before=4)
        set_shape_paragraphs(sp_b2, [p1, p2, p3])

    # Колонка 3: Экономический эффект (заголовок ID=17, тело ID=6)
    sp_t3 = find_shape_by_id(root, 17)
    if sp_t3 is not None:
        set_shape_geometry(sp_t3, x=8400000, y=1750000, cx=3300000)
        set_shape_paragraphs(sp_t3, [make_para([("Экономический эффект", True, 1300, "FF4F12")])])
    sp_b3 = find_shape_by_id(root, 6)
    if sp_b3 is not None:
        set_shape_geometry(sp_b3, x=8400000, y=2350000, cx=3300000, cy=3800000)
        p1 = make_para([("• ", False, 1050, "FF4F12"),
                        ("Сокращение трудозатрат кураторов на 65% за счёт автоматизации регламента.", True, 1100, "FF4F12")])
        p2 = make_para([("• ", False, 1050, "FF4F12"),
                        ("0 потерь данных при смене ответственных менеджеров.", False, 1050, "101828")], space_before=4)
        p3 = make_para([("• ", False, 1050, "FF4F12"),
                        ("Автоматический расчет рейтинга востребованности программ.", False, 1050, "101828")], space_before=4)
        p4 = make_para([("• ", False, 1050, "FF4F12"),
                        ("Готовность к развёртыванию на 500+ вузов РФ без увеличения штата сотрудников.", False, 1050, "101828")], space_before=4)
        set_shape_paragraphs(sp_b3, [p1, p2, p3, p4])


def patch_slide_18(root: ET.Element, rels: ET.Element):
    """Слайд 12 (исходный 18): Дорожная карта и контакты."""
    update_slide_number(root, 12)

    # Плашка под заголовком (ID=23) и заголовок (ID=14)
    # Ширина 5600000 с гарантированным отступом до логотипа (логотип начинается на 6700000+)
    sp_badge = find_shape_by_id(root, 23)
    if sp_badge is not None:
        set_shape_geometry(sp_badge, x=346075, y=324562, cx=5600000, cy=650000)
        set_shape_fill(sp_badge, "7700FF")

    sp_title = find_shape_by_id(root, 14)
    if sp_title is not None:
        set_shape_geometry(sp_title, x=518359, y=410000, cx=5400000, cy=500000)
        set_shape_paragraphs(sp_title, [make_para([("ДОРОЖНАЯ КАРТА И КОНТАКТЫ", True, 2000, "FFFFFF")])])

    # Очищаем неиспользуемые нижние фигуры 3, 5, 7, 9, 11, 13
    for b_id in [3, 5, 7, 9, 11, 13]:
        sp = find_shape_by_id(root, b_id)
        if sp is not None:
            set_shape_paragraphs(sp, [])

    # Левая колонка — Дорожная карта (3 этапа)
    # Этап 1: ID 15 (заголовок), ID 2 (тело)
    sp_e1_t = find_shape_by_id(root, 15)
    if sp_e1_t is not None:
        set_shape_geometry(sp_e1_t, x=501557, y=1450000, cx=1900000, cy=1100000)
        p1 = make_para([("Этап 1: MVP", True, 1250, "12B76A")])
        p2 = make_para([("(Завершено 100%)", True, 1100, "12B76A")], space_before=2)
        set_shape_paragraphs(sp_e1_t, [p1, p2])
    sp_e1_b = find_shape_by_id(root, 2)
    if sp_e1_b is not None:
        set_shape_geometry(sp_e1_b, x=2500000, y=1450000, cx=3300000, cy=1100000)
        set_shape_paragraphs(sp_e1_b, [make_para([("Полнофункциональная CRM, 14 стадий воронки, CAS, 152-ФЗ, импорт D01–D04, отчёты XLSX/PDF/JSON, шлюз LMS/Laravel, ClamAV, Docker Compose.", False, 1050, "101828")])])

    # Этап 2: ID 16 (заголовок), ID 4 (тело)
    sp_e2_t = find_shape_by_id(root, 16)
    if sp_e2_t is not None:
        set_shape_geometry(sp_e2_t, x=501557, y=3000000, cx=1900000, cy=1100000)
        p1 = make_para([("Этап 2: Пилот", True, 1250, "7700FF")])
        p2 = make_para([("(Q1–Q2)", True, 1100, "7700FF")], space_before=2)
        set_shape_paragraphs(sp_e2_t, [p1, p2])
    sp_e2_b = find_shape_by_id(root, 4)
    if sp_e2_b is not None:
        set_shape_geometry(sp_e2_b, x=2500000, y=3000000, cx=3300000, cy=1100000)
        set_shape_paragraphs(sp_e2_b, [make_para([("Запуск в 50 опорных вузах РФ, интеграция с корпоративным SSO / Active Directory Ростелекома, мобильный PWA-клиент для кураторов.", False, 1050, "101828")])])

    # Этап 3: ID 17 (заголовок), ID 6 (тело)
    sp_e3_t = find_shape_by_id(root, 17)
    if sp_e3_t is not None:
        set_shape_geometry(sp_e3_t, x=501557, y=4600000, cx=1900000, cy=1100000)
        p1 = make_para([("Этап 3: Масштаб", True, 1250, "FF4F12")])
        p2 = make_para([("(Q3–Q4)", True, 1100, "FF4F12")], space_before=2)
        set_shape_paragraphs(sp_e3_t, [p1, p2])
    sp_e3_b = find_shape_by_id(root, 6)
    if sp_e3_b is not None:
        set_shape_geometry(sp_e3_b, x=2500000, y=4600000, cx=3300000, cy=1100000)
        set_shape_paragraphs(sp_e3_b, [make_para([("Интеграция с порталом Госуслуг (ЕПГУ), модуль ИИ-прогнозирования кадровой потребности регионов, тиражирование на 500+ вузов РФ.", False, 1050, "101828")])])

    # Правая колонка — Контакты и демо-стенд
    # Демо-стенд: ID 18 (заголовок), ID 8 (тело)
    sp_d_t = find_shape_by_id(root, 18)
    if sp_d_t is not None:
        set_shape_geometry(sp_d_t, x=6174664, y=1450000, cx=1800000, cy=1100000)
        set_shape_paragraphs(sp_d_t, [make_para([("Демо-стенд:", True, 1250, "7700FF")])])
    sp_d_b = find_shape_by_id(root, 8)
    if sp_d_b is not None:
        set_shape_geometry(sp_d_b, x=8050000, y=1450000, cx=3600000, cy=1100000)
        p1 = make_para([("http://78.17.98.33:3000", True, 1150, "7700FF")])
        p2 = make_para([("Роли: manager-a, supervisor, administrator", False, 1050, "101828")], space_before=2)
        set_shape_paragraphs(sp_d_b, [p1, p2])

    # Команда: ID 19 (заголовок), ID 10 (тело)
    sp_k_t = find_shape_by_id(root, 19)
    if sp_k_t is not None:
        set_shape_geometry(sp_k_t, x=6174664, y=3000000, cx=1800000, cy=1100000)
        set_shape_paragraphs(sp_k_t, [make_para([("Команда:", True, 1250, "7700FF")])])
    sp_k_b = find_shape_by_id(root, 10)
    if sp_k_b is not None:
        set_shape_geometry(sp_k_b, x=8050000, y=3000000, cx=3600000, cy=1100000)
        p1 = make_para([("«Ezdel»", True, 1200, "101828")])
        p2 = make_para([("Капитан: Магомед Муцольгов, Lead Fullstack / Solution Architect", False, 1050, "101828")], space_before=2)
        set_shape_paragraphs(sp_k_b, [p1, p2])

    # Связь: ID 20 (заголовок), ID 12 (тело)
    sp_c_t = find_shape_by_id(root, 20)
    if sp_c_t is not None:
        set_shape_geometry(sp_c_t, x=6174664, y=4600000, cx=1800000, cy=1100000)
        set_shape_paragraphs(sp_c_t, [make_para([("Контакты:", True, 1250, "FF4F12")])])
    sp_c_b = find_shape_by_id(root, 12)
    if sp_c_b is not None:
        set_shape_geometry(sp_c_b, x=8050000, y=4600000, cx=3600000, cy=1100000)
        p1 = make_para([("Telegram: @mutsolgov", True, 1100, "FF4F12")])
        p2 = make_para([("Email: mutsolgov@gmail.com", False, 1050, "101828")], space_before=2)
        p3 = make_para([("GitHub: mutsolgov/rost_crm", False, 1050, "101828")], space_before=2)
        set_shape_paragraphs(sp_c_b, [p1, p2, p3])


# Таблица обработчиков слайдов 7..18
PATCHERS = {
    7: patch_slide_7,
    8: patch_slide_8,
    9: patch_slide_9,
    10: patch_slide_10,
    11: patch_slide_11,
    12: patch_slide_12,
    13: patch_slide_13,
    14: patch_slide_14,
    15: patch_slide_15,
    16: patch_slide_16,
    17: patch_slide_17,
    18: patch_slide_18,
}


def build_final_pptx(src_path: Path, dst_path: Path):
    """Сборка итогового PPTX файла с отбором 12 слайдов и инъекцией контента."""
    print(f"[BUILD] Чтение шаблона: {src_path}")
    register_namespaces()

    # Слайды, которые сохраняются (7..18)
    kept_slides = list(range(7, 19))
    kept_slide_files = {f"ppt/slides/slide{i}.xml" for i in kept_slides}
    kept_slide_rels = {f"ppt/slides/_rels/slide{i}.xml.rels" for i in kept_slides}

    # Маппинг slideId в presentation.xml
    kept_slide_ids = {"365", "366", "362", "364", "375", "369", "372", "373", "370", "371", "374", "260"}

    # Скриншоты и медиа для инъекции в ppt/media/
    screenshot_files = [
        "screen-03-interactions-registry.png",
        "screen-04-interaction-card-graph.png",
        "screen-09-reports-analytics-export.png",
        "screen-10-admin-overview-telemetry.png",
        "screen-11-catalog-import-wizard.png",
        "avatar-01-captain.png",
        "avatar-02-backend.png",
        "avatar-03-frontend.png",
        "avatar-04-qa.png",
    ]

    dst_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(src_path, "r") as zin, zipfile.ZipFile(dst_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        namelist = set(zin.namelist())

        for name in zin.namelist():
            # 1. Пропускаем удаляемые слайды и их связи
            if name.startswith("ppt/slides/slide") and name.endswith(".xml"):
                if name not in kept_slide_files:
                    continue
            if name.startswith("ppt/slides/_rels/slide") and name.endswith(".xml.rels"):
                if name not in kept_slide_rels:
                    continue
            # 2. Пропускаем удаляемые диаграммы
            if name.startswith("ppt/charts/"):
                continue

            # 3. Модификация [Content_Types].xml
            if name == "[Content_Types].xml":
                ET.register_namespace("", NS_TYPES)
                ct_root = ET.fromstring(zin.read(name))
                for override in list(ct_root.findall(f"{{{NS_TYPES}}}Override")):
                    part = override.attrib.get("PartName", "")
                    if part.startswith("/ppt/slides/slide"):
                        num_str = part.replace("/ppt/slides/slide", "").replace(".xml", "")
                        if num_str.isdigit() and int(num_str) not in kept_slides:
                            ct_root.remove(override)
                    elif part.startswith("/ppt/charts/"):
                        ct_root.remove(override)
                data = ET.tostring(ct_root, encoding="utf-8", xml_declaration=True)
                zout.writestr(name, data)
                continue

            # 4. Модификация ppt/_rels/presentation.xml.rels
            if name == "ppt/_rels/presentation.xml.rels":
                ET.register_namespace("", NS_RELS)
                rels_root = ET.fromstring(zin.read(name))
                for r in list(rels_root.findall(f"{{{NS_RELS}}}Relationship")):
                    target = r.attrib.get("Target", "")
                    if target.startswith("slides/slide"):
                        num_str = target.replace("slides/slide", "").replace(".xml", "")
                        if num_str.isdigit() and int(num_str) not in kept_slides:
                            rels_root.remove(r)
                data = ET.tostring(rels_root, encoding="utf-8", xml_declaration=True)
                zout.writestr(name, data)
                continue

            # 5. Модификация ppt/presentation.xml
            if name == "ppt/presentation.xml":
                register_namespaces()
                pres_root = ET.fromstring(zin.read(name))

                # <p:sldIdLst>
                sldIdLst = pres_root.find(f"{{{NS_P}}}sldIdLst")
                if sldIdLst is not None:
                    for sld in list(sldIdLst.findall(f"{{{NS_P}}}sldId")):
                        if sld.attrib.get("id") not in kept_slide_ids:
                            sldIdLst.remove(sld)

                # <p14:sectionLst>
                for ext in pres_root.findall(f".//{{{NS_P}}}ext"):
                    secLst = ext.find(f"{{{NS_P14}}}sectionLst")
                    if secLst is not None:
                        for sec in list(secLst.findall(f"{{{NS_P14}}}section")):
                            sec_name = sec.attrib.get("name", "")
                            if sec_name in ["Информация", "Материалы"]:
                                secLst.remove(sec)
                            elif sec_name in ["Обязательные слайды", "Шаблоны слайдов"]:
                                sec_sldLst = sec.find(f"{{{NS_P14}}}sldIdLst")
                                if sec_sldLst is not None:
                                    for sld in list(sec_sldLst.findall(f"{{{NS_P14}}}sldId")):
                                        if sld.attrib.get("id") not in kept_slide_ids:
                                            sec_sldLst.remove(sld)

                data = ET.tostring(pres_root, encoding="utf-8", xml_declaration=True)
                zout.writestr(name, data)
                continue

            # 6. Обработка сохраняемых слайдов (slide7..slide18)
            if name in kept_slide_files:
                num = int(name.replace("ppt/slides/slide", "").replace(".xml", ""))
                rels_name = f"ppt/slides/_rels/slide{num}.xml.rels"

                # Чтение rels
                if rels_name in namelist:
                    ET.register_namespace("", NS_RELS)
                    slide_rels_root = ET.fromstring(zin.read(rels_name))
                else:
                    ET.register_namespace("", NS_RELS)
                    slide_rels_root = ET.Element(f"{{{NS_RELS}}}Relationships")

                # Чтение и патчинг слайда
                register_namespaces()
                slide_root = ET.fromstring(zin.read(name))
                patcher = PATCHERS.get(num)
                if patcher:
                    patcher(slide_root, slide_rels_root)

                # Запись слайда
                slide_data = ET.tostring(slide_root, encoding="utf-8", xml_declaration=True)
                zout.writestr(name, slide_data)

                # Запись обновленных rels
                rels_data = ET.tostring(slide_rels_root, encoding="utf-8", xml_declaration=True)
                zout.writestr(rels_name, rels_data)
                continue

            # Связи уже записаны вместе со слайдами выше
            if name in kept_slide_rels:
                continue

            # Все остальные файлы (включая все оригинальные медиа шаблона) копируются
            zout.writestr(name, zin.read(name))

        # Инъекция файлов скриншотов и аватаров в ppt/media/
        for sf in screenshot_files:
            src_file = SCREENSHOTS_DIR / sf
            if src_file.is_file():
                zout.writestr(f"ppt/media/{sf}", src_file.read_bytes())
                print(f"[MEDIA] Внедрено изображение: ppt/media/{sf} ({src_file.stat().st_size:,} байт)")

    pptx_size = dst_path.stat().st_size
    print(f"[OK] Создан файл презентации: {dst_path} ({pptx_size:,} байт / {pptx_size / 1024 / 1024:.2f} МБ)")
    if pptx_size < 10 * 1024 * 1024:
        raise ValueError(f"Размер PPTX файла меньше 10 МБ: {pptx_size} байт")


def convert_pptx_to_pdf(pptx_path: Path, out_dir: Path) -> Path:
    """Конвертация PPTX в векторный PDF через LibreOffice в headless режиме с изолированным профилем."""
    lo_profile = out_dir / ".lo_profile_pres"
    lo_profile.mkdir(parents=True, exist_ok=True)

    cmd = [
        "libreoffice",
        f"-env:UserInstallation=file://{lo_profile.resolve()}",
        "--headless",
        "--convert-to", "pdf",
        str(pptx_path.resolve()),
        "--outdir", str(out_dir.resolve())
    ]

    print(f"[BUILD] Компиляция PDF: {' '.join(cmd)}")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"[STDERR] {proc.stderr}")
        raise RuntimeError(f"Ошибка компиляции LibreOffice: код {proc.returncode}")

    pdf_path = out_dir / (pptx_path.stem + ".pdf")
    if not pdf_path.is_file():
        raise FileNotFoundError(f"Файл PDF не был создан: {pdf_path}")

    # Очистка временного профиля
    shutil.rmtree(lo_profile, ignore_errors=True)

    pdf_size = pdf_path.stat().st_size
    print(f"[OK] Скомпилирован PDF: {pdf_path} ({pdf_size:,} байт / {pdf_size / 1024:.1f} КБ)")
    if pdf_size < 500 * 1024:
        raise ValueError(f"Размер PDF меньше 500 КБ: {pdf_size} байт")
    return pdf_path


def render_and_verify_slides(pdf_path: Path, verify_dir: Path):
    """Рендеринг слайдов в PNG через pdftoppm и проверка характеристик."""
    verify_dir.mkdir(parents=True, exist_ok=True)

    # Проверка числа страниц через pdfinfo
    proc_info = subprocess.run(["pdfinfo", str(pdf_path)], capture_output=True, text=True, check=True)
    pages = 0
    for line in proc_info.stdout.splitlines():
        if line.startswith("Pages:"):
            pages = int(line.split(":")[1].strip())
            break
    print(f"[VERIFY] Количество страниц в PDF: {pages}")
    if pages != 12:
        raise ValueError(f"Ожидалось ровно 12 страниц, получено: {pages}")

    # Рендеринг всех 12 слайдов с разрешением 150 DPI
    print(f"[RENDER] Рендеринг {pages} слайдов в PNG (150 DPI)...")
    cmd_ppm = [
        "pdftoppm", "-png", "-r", "150",
        "-f", "1", "-l", "12",
        str(pdf_path),
        str(verify_dir / "slide")
    ]
    subprocess.run(cmd_ppm, check=True)

    rendered_pngs = sorted(verify_dir.glob("slide-*.png"))
    print(f"[OK] Отрендерено {len(rendered_pngs)} PNG файлов в {verify_dir}:")
    for png in rendered_pngs:
        print(f"  • {png.name}: {png.stat().st_size:,} байт")


def main():
    print("=" * 70)
    print("Конвейер сборки презентации «ИТ Школа Ростелекома — CRM» (Ezdel)")
    print("=" * 70)

    if not TEMPLATE_PATH.is_file():
        print(f"[ERROR] Исходный шаблон не найден: {TEMPLATE_PATH}", file=sys.stderr)
        sys.exit(1)

    # 1. Сборка PPTX
    build_final_pptx(TEMPLATE_PATH, OUT_PPTX)

    # 2. Конвертация в PDF
    pdf_path = convert_pptx_to_pdf(OUT_PPTX, OUT_PPTX.parent)

    # 3. Копирование в docs/
    DOCS_PDF.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(pdf_path, DOCS_PDF)
    print(f"[COPY] Скопировано в документацию: {DOCS_PDF} ({DOCS_PDF.stat().st_size:,} байт)")

    # 4. Проверка и рендеринг слайдов
    verify_dir = WORKSPACE_ROOT / "docs" / "rendered_slides"
    render_and_verify_slides(pdf_path, verify_dir)

    print("=" * 70)
    print("Сборка презентации и верификация успешно завершены!")
    print(f"1. PPTX: {OUT_PPTX} ({OUT_PPTX.stat().st_size:,} байт)")
    print(f"2. PDF:  {OUT_PDF} ({OUT_PDF.stat().st_size:,} байт)")
    print(f"3. DOCS: {DOCS_PDF} ({DOCS_PDF.stat().st_size:,} байт)")
    print("=" * 70)


if __name__ == "__main__":
    main()
