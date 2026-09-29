#!/usr/bin/env python3
"""
High-Fidelity Screenshot Generator for Rostelecom CRM (SWE-29).
Generates 13 HiDPI (1440x900) screenshots matching the Gen2 Light Theme.
Outputs dual PNG copies:
  - frontend/public/docs/screenshots/*.png
  - docs/screenshots/*.png
"""

import os
import sys
import io
import struct
from pathlib import Path

# Graphic rendering imports
try:
    import gi
    gi.require_version('Rsvg', '2.0')
    from gi.repository import Rsvg
    import cairo
    HAS_RSVG_CAIRO = True
except Exception as e:
    HAS_RSVG_CAIRO = False
    print(f"Warning: Rsvg/Cairo not available ({e}), falling back to PIL/pure-renderer", file=sys.stderr)

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except Exception:
    HAS_PIL = False

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIRS = [
    REPO_ROOT / "frontend" / "public" / "docs" / "screenshots",
    REPO_ROOT / "docs" / "screenshots",
]
FONT_PATH = REPO_ROOT / "backend" / "app" / "fonts" / "LiberationSans-Regular.ttf"

# Color constants
PRIMARY = "#7700FF"
PRIMARY_HOVER = "#6C00E0"
PRIMARY_SUBTLE = "#F3EBFF"
PRIMARY_TEXT = "#5A00CC"
ACCENT = "#FF4F12"
ACCENT_SUBTLE = "#FFF0EB"
BG_MAIN = "#F4F5F8"
CARD_BG = "#FFFFFF"
BORDER = "#E2E5EB"
BORDER_SUBTLE = "#F0EDF4"
TEXT_MAIN = "#101828"
TEXT_MUTED = "#475467"
SUCCESS_BG = "#ECFDF3"
SUCCESS_TEXT = "#027A48"
SUCCESS_BORDER = "#A6F4C5"
WARNING_BG = "#FFFAEB"
WARNING_TEXT = "#B54708"
WARNING_BORDER = "#FEDF89"
ERROR_BG = "#FEF3F2"
ERROR_TEXT = "#B42318"
ERROR_BORDER = "#FECDCA"

def escape_xml(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&apos;")

def render_svg_to_png(svg_content: str, width: int = 1440, height: int = 900) -> bytes:
    """Renders SVG to PNG bytes using Cairo/Rsvg or PIL fallback."""
    if HAS_RSVG_CAIRO:
        handle = Rsvg.Handle.new_from_data(svg_content.encode("utf-8"))
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        cr = cairo.Context(surface)
        if hasattr(handle, "render_document"):
            viewport = Rsvg.Rectangle()
            viewport.x = 0
            viewport.y = 0
            viewport.width = width
            viewport.height = height
            handle.render_document(cr, viewport)
        else:
            handle.render_cairo(cr)
        buf = io.BytesIO()
        surface.write_to_png(buf)
        return buf.getvalue()
    elif HAS_PIL:
        # Emergency Pillow fallback
        img = Image.new("RGB", (width, height), color=(244, 245, 248))
        draw = ImageDraw.Draw(img)
        draw.text((100, 100), "Rostelecom CRM Screenshot", fill=(119, 0, 255))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    else:
        raise RuntimeError("Neither Rsvg/Cairo nor Pillow available for PNG rendering.")

def wrap_svg(inner_content: str, width: int = 1440, height: int = 900) -> str:
    return f"""<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <style>
      text {{ font-family: 'Liberation Sans', 'DejaVu Sans', Arial, sans-serif; }}
      .bold {{ font-weight: bold; }}
      .semibold {{ font-weight: 600; }}
      .muted {{ fill: {TEXT_MUTED}; }}
      .primary {{ fill: {PRIMARY}; }}
      .accent {{ fill: {ACCENT}; }}
    </style>
    <filter id="shadow" x="-5%" y="-5%" width="110%" height="115%" filterUnits="userSpaceOnUse">
      <feDropShadow dx="0" dy="2" stdDeviation="4" flood-color="#101828" flood-opacity="0.06"/>
    </filter>
    <filter id="modal-shadow" x="-10%" y="-10%" width="120%" height="120%" filterUnits="userSpaceOnUse">
      <feDropShadow dx="0" dy="12" stdDeviation="16" flood-color="#101828" flood-opacity="0.25"/>
    </filter>
  </defs>
  {inner_content}
</svg>"""

def get_window_chrome(url: str, title: str = "ИТ Школа Ростелеком — CRM") -> str:
    return f"""
  <!-- Browser Window Chrome -->
  <rect x="0" y="0" width="1440" height="42" fill="#EAEBED" stroke="{BORDER}" stroke-width="1"/>
  <circle cx="20" cy="21" r="5.5" fill="#FF5F56"/>
  <circle cx="38" cy="21" r="5.5" fill="#FFBD2E"/>
  <circle cx="56" cy="21" r="5.5" fill="#27C93F"/>
  <!-- URL Address Bar -->
  <rect x="140" y="8" width="1160" height="26" rx="6" fill="#FFFFFF" stroke="#D1D5DB" stroke-width="1"/>
  <path d="M156 16 L164 13 L172 16 L172 21 C172 25 164 28 164 28 C164 28 156 25 156 21 Z" fill="none" stroke="#12B76A" stroke-width="1.6"/>
  <path d="M161 20 L163.5 22.5 L167.5 17.5" fill="none" stroke="#12B76A" stroke-width="1.6"/>
  <text x="180" y="25" font-size="12" fill="{TEXT_MUTED}">{escape_xml(url)}</text>
  <text x="1330" y="25" font-size="11" fill="#98A2B3" text-anchor="end">152-ФЗ Защищено</text>
"""

def get_rostelecom_logo_svg(x: int, y: int, size: int = 28) -> str:
    scale = size / 40.0
    return f"""
  <g transform="translate({x}, {y}) scale({scale})">
    <path fill="{PRIMARY}" d="M0.81 38.1c-.01-.46.18-.9.51-1.33l1.09-1.09c.52-.53 1.08-1.09 1.9-1.9 0.92-.92 2.18-2.16 4.07-4.05l.01-.01 1.85-1.84.04-.04C13.34 24.8 17.7 20.46 24.11 14.08L10.04 0 2.07 7.97C-.31 10.35.01 11.91.01 15.11v21.88c0 .61.19 1.21.54 1.72.35.5.85.89 1.42 1.1-.34-.14-.64-.37-.85-.68-.21-.3-.32-.67-.32-1.04z"/>
    <path fill="{ACCENT}" d="M1.97 39.81c.02.01.05.02.07.03.02.01.05.01.08.02.29.09.59.14.89.14h15.62l-10.25-10.27-.01.01c-1.9 1.88-3.15 3.12-4.07 4.05-.82.82-1.38 1.38-1.9 1.9l-1.09 1.09c-.33.36-.52.83-.51 1.33 0 .37.11.73.32 1.04.21.31.5.54.85.68z"/>
  </g>
"""

def get_sidebar_and_topbar(
    active_nav: str,
    breadcrumbs: list[str],
    user_name: str = "Анна Смирнова",
    user_role: str = "Менеджер партнёрств",
    show_demo_strip: bool = True
) -> str:
    nav_items = [
        ("overview", "Обзор", "grid"),
        ("interactions", "Взаимодействия", "layers"),
        ("reports", "Отчёты", "chart"),
        ("integrations", "Интеграции", "refresh"),
        ("catalogs", "Справочники", "book"),
        ("help", "Помощь", "help"),
    ]
    # Filter for non-admin vs admin
    is_admin = ("Администратор" in user_role or "administrator" in user_role)
    if is_admin:
        nav_items = [item for item in nav_items if item[0] != "interactions"]

    # Sidebar items
    sidebar_items_svg = []
    y_nav = 135
    for code, label, icon in nav_items:
        is_active = (code == active_nav)
        if is_active:
            sidebar_items_svg.append(f"""
        <rect x="12" y="{y_nav}" width="216" height="38" rx="8" fill="{PRIMARY_SUBTLE}"/>
        <rect x="12" y="{y_nav+8}" width="3" height="22" rx="1.5" fill="{PRIMARY}"/>
        <text x="52" y="{y_nav+24}" font-size="14" font-weight="bold" fill="{PRIMARY}">{label}</text>
            """)
        else:
            sidebar_items_svg.append(f"""
        <text x="52" y="{y_nav+24}" font-size="14" fill="{TEXT_MUTED}">{label}</text>
            """)
        # Simple icon placeholders
        sidebar_items_svg.append(f"""<circle cx="32" cy="{y_nav+19}" r="7" fill="none" stroke="{'#7700FF' if is_active else '#98A2B3'}" stroke-width="1.6"/>""")
        y_nav += 44

    b_text = f"{breadcrumbs[0]} <tspan fill='#98A2B3'>/</tspan> <tspan font-weight='bold' fill='{TEXT_MAIN}'>{breadcrumbs[1]}</tspan>" if len(breadcrumbs) > 1 else breadcrumbs[0]

    avatar_initials = "".join([part[0] for part in user_name.split()[:2]])

    demo_strip_svg = ""
    main_top = 100
    if show_demo_strip:
        demo_strip_svg = f"""
    <!-- Demo Strip -->
    <rect x="240" y="98" width="1200" height="32" fill="#FFF8F5" stroke="#FFE4D6" stroke-width="1"/>
    <rect x="260" y="104" width="46" height="20" rx="4" fill="{ACCENT}"/>
    <text x="283" y="118" font-size="10" font-weight="bold" fill="#FFFFFF" text-anchor="middle">ДЕМО</text>
    <text x="316" y="118" font-size="12" fill="{TEXT_MUTED}">Вымышленные данные · Режим разработки (152-ФЗ)</text>
    <text x="1200" y="118" font-size="12" fill="{TEXT_MUTED}">Пользователь: <tspan font-weight="600" fill="{TEXT_MAIN}">{user_name}</tspan> ▾</text>
        """
        main_top = 130

    return f"""
  <!-- Sidebar -->
  <rect x="0" y="42" width="240" height="858" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1"/>
  <!-- Brand -->
  {get_rostelecom_logo_svg(24, 62, 30)}
  <text x="56" y="76" font-size="15" font-weight="bold" fill="{TEXT_MAIN}">Ростелеком</text>
  <text x="56" y="92" font-size="11" fill="{TEXT_MUTED}">ИТ Школа · Партнёры</text>

  <text x="24" y="122" font-size="10" font-weight="bold" fill="#98A2B3" letter-spacing="1">РАБОЧЕЕ ПРОСТРАНСТВО</text>
  {''.join(sidebar_items_svg)}

  <!-- Sidebar Bottom Note -->
  <g transform="translate(16, 750)">
    <rect x="0" y="0" width="208" height="88" rx="8" fill="#F8F9FC" stroke="{BORDER}" stroke-width="1"/>
    <text x="16" y="24" font-size="12" font-weight="bold" fill="{TEXT_MAIN}">Один партнёр.</text>
    <text x="16" y="40" font-size="12" font-weight="bold" fill="{TEXT_MAIN}">Несколько программ.</text>
    <text x="16" y="58" font-size="10" fill="{TEXT_MUTED}">Каждый цикл сотрудничества</text>
    <text x="16" y="70" font-size="10" fill="{TEXT_MUTED}">учитывается автономно.</text>
  </g>
  <text x="24" y="872" font-size="10" fill="#98A2B3">ИТ Школа v0.1 · Первый срез</text>

  <!-- Topbar -->
  <rect x="240" y="42" width="1200" height="56" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1"/>
  <text x="264" y="75" font-size="14" fill="{TEXT_MUTED}">{b_text}</text>

  <!-- Account Scope and User -->
  <circle cx="1120" cy="70" r="4" fill="#12B76A"/>
  <text x="1132" y="74" font-size="11" fill="{TEXT_MUTED}">Область доступа</text>
  <line x1="1230" y1="56" x2="1230" y2="84" stroke="{BORDER}" stroke-width="1"/>

  <circle cx="1256" cy="70" r="16" fill="{PRIMARY_SUBTLE}"/>
  <text x="1256" y="75" font-size="12" font-weight="bold" fill="{PRIMARY}" text-anchor="middle">{avatar_initials}</text>
  <text x="1280" y="67" font-size="13" font-weight="600" fill="{TEXT_MAIN}">{user_name}</text>
  <text x="1280" y="81" font-size="10" fill="{TEXT_MUTED}">{user_role}</text>

  {demo_strip_svg}
  <!-- Main Content Background Area -->
  <rect x="240" y="{main_top}" width="1200" height="{900 - main_top}" fill="{BG_MAIN}"/>
"""

# Generator 1: Login
def gen_screen_01_login() -> str:
    chrome = get_window_chrome("https://crm.school.rt.ru/", "Вход — ИТ Школа Ростелеком")
    content = f"""
  {chrome}
  <rect x="0" y="42" width="1440" height="858" fill="{BG_MAIN}"/>

  <!-- Left Story Panel (Brand gradient) -->
  <defs>
    <linearGradient id="grad-brand" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#7700FF"/>
      <stop offset="100%" stop-color="#4A00B0"/>
    </linearGradient>
  </defs>
  <rect x="80" y="90" width="620" height="730" rx="16" fill="url(#grad-brand)" filter="url(#shadow)"/>
  {get_rostelecom_logo_svg(130, 140, 48)}
  <text x="185" y="165" font-size="22" font-weight="bold" fill="#FFFFFF">Ростелеком</text>
  <text x="185" y="187" font-size="14" fill="#D8B4FE">ИТ Школа · Образовательные партнёрства</text>

  <rect x="130" y="240" width="360" height="28" rx="14" fill="rgba(255,255,255,0.15)"/>
  <text x="145" y="258" font-size="11" font-weight="600" fill="#FFFFFF" letter-spacing="1">СОТРУДНИЧЕСТВО С ОБРАЗОВАТЕЛЬНЫМИ ОРГАНИЗАЦИЯМИ</text>

  <text x="130" y="330" font-size="36" font-weight="bold" fill="#FFFFFF">От первого контакта</text>
  <text x="130" y="375" font-size="36" font-weight="bold" fill="#FFFFFF">к новым компетенциям.</text>

  <text x="130" y="430" font-size="16" fill="#E9D5FF" width="500">
    Единый цифровой контур взаимодействия с ведущими вузами страны.
  </text>
  <text x="130" y="455" font-size="16" fill="#E9D5FF">
    Прозрачный жизненный цикл, сквозная аналитика и строгий аудит.
  </text>

  <!-- Step Pathway -->
  <g transform="translate(130, 520)">
    <rect x="0" y="0" width="130" height="40" rx="8" fill="rgba(255,255,255,0.1)"/>
    <text x="65" y="25" font-size="13" font-weight="bold" fill="#FFFFFF" text-anchor="middle">1. Контакт</text>
    <text x="145" y="25" font-size="16" fill="#FFFFFF">→</text>
    <rect x="170" y="0" width="130" height="40" rx="8" fill="rgba(255,255,255,0.1)"/>
    <text x="235" y="25" font-size="13" font-weight="bold" fill="#FFFFFF" text-anchor="middle">2. Внедрение</text>
    <text x="315" y="25" font-size="16" fill="#FFFFFF">→</text>
    <rect x="340" y="0" width="130" height="40" rx="8" fill="rgba(255,255,255,0.1)"/>
    <text x="405" y="25" font-size="13" font-weight="bold" fill="#FFFFFF" text-anchor="middle">3. Обучение</text>
  </g>

  <line x1="130" y1="740" x2="630" y2="740" stroke="rgba(255,255,255,0.2)" stroke-width="1"/>
  <text x="130" y="770" font-size="12" fill="#D8B4FE">ИТ Школа · Партнёры | Конкурсный срез v0.1</text>

  <!-- Right Login Card -->
  <rect x="740" y="90" width="620" height="730" rx="16" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1" filter="url(#shadow)"/>

  <g transform="translate(800, 150)">
    <circle cx="28" cy="28" r="28" fill="{PRIMARY_SUBTLE}"/>
    <path d="M20 28 L28 20 L36 28 L36 36 C36 40 28 44 28 44 C28 44 20 40 20 36 Z" fill="none" stroke="{PRIMARY}" stroke-width="2"/>
    <text x="72" y="26" font-size="24" font-weight="bold" fill="{TEXT_MAIN}">Демонстрационный стенд</text>
    <text x="72" y="46" font-size="14" fill="{TEXT_MUTED}">Выберите учётную запись для входа в рабочее пространство:</text>

    <!-- Role selection cards -->
    <!-- Option 1: Manager A -->
    <rect x="0" y="80" width="500" height="72" rx="10" fill="#FFFFFF" stroke="{PRIMARY}" stroke-width="2"/>
    <circle cx="40" cy="116" r="18" fill="{PRIMARY_SUBTLE}"/>
    <text x="40" y="122" font-size="14" font-weight="bold" fill="{PRIMARY}" text-anchor="middle">АС</text>
    <text x="75" y="108" font-size="15" font-weight="bold" fill="{TEXT_MAIN}">Анна Смирнова</text>
    <text x="75" y="126" font-size="12" fill="{TEXT_MUTED}">Менеджер партнёрств · Доступ: карточки и реестр (org-1)</text>
    <rect x="420" y="104" width="60" height="24" rx="12" fill="{PRIMARY_SUBTLE}"/>
    <text x="450" y="120" font-size="11" font-weight="bold" fill="{PRIMARY}" text-anchor="middle">Вход</text>

    <!-- Option 2: Supervisor -->
    <rect x="0" y="165" width="500" height="72" rx="10" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1"/>
    <circle cx="40" cy="201" r="18" fill="#F0FDF4"/>
    <text x="40" y="207" font-size="14" font-weight="bold" fill="#16A34A" text-anchor="middle">ЕС</text>
    <text x="75" y="193" font-size="15" font-weight="bold" fill="{TEXT_MAIN}">Елена Соколова</text>
    <text x="75" y="211" font-size="12" fill="{TEXT_MUTED}">Руководитель направления · Сводная аналитика, Reassign, квоты</text>

    <!-- Option 3: Administrator -->
    <rect x="0" y="250" width="500" height="72" rx="10" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1"/>
    <circle cx="40" cy="286" r="18" fill="#FFF7ED"/>
    <text x="40" y="292" font-size="14" font-weight="bold" fill="{ACCENT}" text-anchor="middle">АД</text>
    <text x="75" y="278" font-size="15" font-weight="bold" fill="{TEXT_MAIN}">Администратор платформы</text>
    <text x="75" y="296" font-size="12" fill="{TEXT_MUTED}">Системное управление · Импорт Excel, мигратор v1/v2, интеграции</text>

    <!-- Keycloak Button -->
    <rect x="0" y="350" width="500" height="48" rx="8" fill="{PRIMARY}"/>
    <text x="250" y="380" font-size="15" font-weight="bold" fill="#FFFFFF" text-anchor="middle">Войти через Keycloak OIDC →</text>

    <!-- Security Note -->
    <rect x="0" y="425" width="500" height="70" rx="8" fill="#F8F9FC" stroke="{BORDER}" stroke-width="1"/>
    <text x="20" y="450" font-size="12" font-weight="bold" fill="{TEXT_MAIN}">Инварианты безопасности (152-ФЗ, ФСТЭК №117):</text>
    <text x="20" y="470" font-size="11" fill="{TEXT_MUTED}">
      • Токены JWT хранятся строго in-memory (отсутствуют в localStorage)
    </text>
    <text x="20" y="485" font-size="11" fill="{TEXT_MUTED}">
      • Zero-Oracle мандаты: попытка запроса чужого ресурса возвращает HTTP 404
    </text>
  </g>
"""
    return wrap_svg(content)

# Generator 2: Manager Overview
def gen_screen_02_manager_overview() -> str:
    chrome = get_window_chrome("https://crm.school.rt.ru/overview", "Рабочий стол менеджера — ИТ Школа Ростелеком")
    shell = get_sidebar_and_topbar("overview", ["Партнёры", "Рабочий обзор"])
    content = f"""
  {chrome}
  {shell}
  <!-- Main Page Area (Manager) -->
  <g transform="translate(270, 150)">
    <!-- Header -->
    <text x="0" y="20" font-size="11" font-weight="bold" fill="#98A2B3" letter-spacing="1">РАБОЧИЙ ОБЗОР · 29 СЕНТЯБРЯ 2026</text>
    <text x="0" y="50" font-size="24" font-weight="bold" fill="{TEXT_MAIN}">Партнёрства в движении</text>
    <text x="0" y="72" font-size="13" fill="{TEXT_MUTED}">Здравствуйте, Анна. Здесь всё, что важно для вашей работы с вузами.</text>

    <rect x="940" y="28" width="200" height="42" rx="8" fill="{PRIMARY}"/>
    <text x="1040" y="54" font-size="14" font-weight="bold" fill="#FFFFFF" text-anchor="middle">+ Новое взаимодействие</text>

    <!-- KPI Grid -->
    <g transform="translate(0, 95)">
      <!-- Card 1 -->
      <rect x="0" y="0" width="268" height="90" rx="10" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1" filter="url(#shadow)"/>
      <text x="20" y="26" font-size="12" fill="{TEXT_MUTED}">Всего взаимодействий</text>
      <text x="20" y="62" font-size="30" font-weight="bold" fill="{PRIMARY}">12</text>
      <text x="20" y="80" font-size="11" fill="#98A2B3">В вашей области доступа</text>
      <circle cx="236" cy="30" r="14" fill="{PRIMARY_SUBTLE}"/>

      <!-- Card 2 -->
      <rect x="290" y="0" width="268" height="90" rx="10" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1" filter="url(#shadow)"/>
      <text x="20" y="26" font-size="12" fill="{TEXT_MUTED}">Активных процессов</text>
      <text x="20" y="62" font-size="30" font-weight="bold" fill="{ACCENT}">9</text>
      <text x="20" y="80" font-size="11" fill="#98A2B3">Сотрудничество продолжается</text>
      <circle cx="526" cy="30" r="14" fill="{ACCENT_SUBTLE}"/>

      <!-- Card 3 -->
      <rect x="580" y="0" width="268" height="90" rx="10" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1" filter="url(#shadow)"/>
      <text x="20" y="26" font-size="12" fill="{TEXT_MUTED}">Образовательных организаций</text>
      <text x="20" y="62" font-size="30" font-weight="bold" fill="#0284C7">8</text>
      <text x="20" y="80" font-size="11" fill="#98A2B3">Уникальные партнёры</text>
      <circle cx="816" cy="30" r="14" fill="#E0F2FE"/>

      <!-- Card 4 -->
      <rect x="870" y="0" width="270" height="90" rx="10" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1" filter="url(#shadow)"/>
      <text x="20" y="26" font-size="12" fill="{TEXT_MUTED}">Завершённых процессов</text>
      <text x="20" y="62" font-size="30" font-weight="bold" fill="#16A34A">3</text>
      <text x="20" y="80" font-size="11" fill="#98A2B3">Пройден полный цикл</text>
      <circle cx="1106" cy="30" r="14" fill="#DCFCE7"/>
    </g>

    <!-- Two columns: Stage bars & Focus Panel -->
    <g transform="translate(0, 205)">
      <!-- Stage bars panel -->
      <rect x="0" y="0" width="700" height="230" rx="10" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1" filter="url(#shadow)"/>
      <text x="24" y="32" font-size="11" font-weight="bold" fill="#98A2B3" letter-spacing="1">ТЕКУЩЕЕ СОСТОЯНИЕ</text>
      <text x="24" y="54" font-size="17" font-weight="bold" fill="{TEXT_MAIN}">Этапы сотрудничества (Воронка)</text>
      <rect x="590" y="24" width="86" height="24" rx="12" fill="#F4F5F8"/>
      <text x="633" y="40" font-size="11" font-weight="600" fill="{TEXT_MUTED}" text-anchor="middle">12 процессов</text>

      <!-- Bars -->
      <text x="24" y="90" font-size="13" fill="{TEXT_MAIN}">1. Поиск контактов</text>
      <rect x="230" y="78" width="400" height="14" rx="7" fill="#F4F5F8"/>
      <rect x="230" y="78" width="100" height="14" rx="7" fill="{PRIMARY}"/>
      <text x="645" y="90" font-size="12" font-weight="bold" fill="{TEXT_MAIN}">1</text>

      <text x="24" y="118" font-size="13" fill="{TEXT_MAIN}">2. Уточнение потребности</text>
      <rect x="230" y="106" width="400" height="14" rx="7" fill="#F4F5F8"/>
      <rect x="230" y="106" width="200" height="14" rx="7" fill="{PRIMARY}"/>
      <text x="645" y="118" font-size="12" font-weight="bold" fill="{TEXT_MAIN}">2</text>

      <text x="24" y="146" font-size="13" fill="{TEXT_MAIN}">4. Обмен документами</text>
      <rect x="230" y="134" width="400" height="14" rx="7" fill="#F4F5F8"/>
      <rect x="230" y="134" width="200" height="14" rx="7" fill="{PRIMARY}"/>
      <text x="645" y="146" font-size="12" font-weight="bold" fill="{TEXT_MAIN}">2</text>

      <text x="24" y="174" font-size="13" fill="{TEXT_MAIN}">6. Подписание документов</text>
      <rect x="230" y="162" width="400" height="14" rx="7" fill="#F4F5F8"/>
      <rect x="230" y="162" width="100" height="14" rx="7" fill="{PRIMARY}"/>
      <text x="645" y="174" font-size="12" font-weight="bold" fill="{TEXT_MAIN}">1</text>

      <text x="24" y="202" font-size="13" fill="{TEXT_MAIN}">7. Передача материалов</text>
      <rect x="230" y="190" width="400" height="14" rx="7" fill="#F4F5F8"/>
      <rect x="230" y="190" width="300" height="14" rx="7" fill="{PRIMARY}"/>
      <text x="645" y="202" font-size="12" font-weight="bold" fill="{TEXT_MAIN}">3</text>

      <!-- Right Focus Panel -->
      <rect x="724" y="0" width="416" height="230" rx="10" fill="url(#grad-brand)" filter="url(#shadow)"/>
      <text x="750" y="32" font-size="11" font-weight="bold" fill="#D8B4FE" letter-spacing="1">ОБЩИЙ КОНТЕКСТ КОМАНДЫ</text>
      <text x="750" y="60" font-size="18" font-weight="bold" fill="#FFFFFF">Один взгляд.</text>
      <text x="750" y="82" font-size="18" font-weight="bold" fill="#FFFFFF">Весь путь партнёрства.</text>
      <text x="750" y="112" font-size="12" fill="#E9D5FF">Программа, ответственный и история решений</text>
      <text x="750" y="128" font-size="12" fill="#E9D5FF">— в единой карточке взаимодействия.</text>

      <rect x="750" y="150" width="160" height="56" rx="8" fill="rgba(255,255,255,0.15)"/>
      <text x="764" y="185" font-size="26" font-weight="bold" fill="#FFFFFF">0</text>
      <text x="795" y="175" font-size="11" fill="#FFFFFF">без выбранной</text>
      <text x="795" y="190" font-size="11" fill="#FFFFFF">программы (D02 OK)</text>

      <rect x="930" y="158" width="190" height="40" rx="8" fill="#FFFFFF"/>
      <text x="1025" y="183" font-size="13" font-weight="bold" fill="{PRIMARY}" text-anchor="middle">Открыть реестр →</text>
    </g>

    <!-- Recent interactions table -->
    <g transform="translate(0, 450)">
      <rect x="0" y="0" width="1140" height="250" rx="10" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1" filter="url(#shadow)"/>
      <text x="24" y="32" font-size="16" font-weight="bold" fill="{TEXT_MAIN}">Недавние взаимодействия</text>

      <!-- Table Header -->
      <rect x="0" y="48" width="1140" height="34" fill="#F8F9FC"/>
      <text x="24" y="70" font-size="11" font-weight="bold" fill="#98A2B3">ОРГАНИЗАЦИЯ И НАЗВАНИЕ</text>
      <text x="420" y="70" font-size="11" font-weight="bold" fill="#98A2B3">ИТ-ПРОГРАММА / ПРОДУКТ</text>
      <text x="720" y="70" font-size="11" font-weight="bold" fill="#98A2B3">ЭТАП ВОРОНКИ</text>
      <text x="960" y="70" font-size="11" font-weight="bold" fill="#98A2B3">ОБНОВЛЕНО</text>

      <!-- Row 1 -->
      <line x1="0" y1="82" x2="1140" y2="82" stroke="{BORDER}" stroke-width="1"/>
      <text x="24" y="108" font-size="13" font-weight="bold" fill="{PRIMARY}">Сотрудничество с МГТУ им. Баумана</text>
      <text x="24" y="124" font-size="11" fill="{TEXT_MUTED}">МГТУ им. Н.Э. Баумана · Цикл: 2026/2027</text>
      <text x="420" y="108" font-size="13" font-weight="600" fill="{TEXT_MAIN}">DevOps инженерия</text>
      <text x="420" y="124" font-size="11" fill="{TEXT_MUTED}">Облачная Платформа РТК</text>
      <rect x="720" y="98" width="180" height="26" rx="13" fill="{PRIMARY_SUBTLE}"/>
      <text x="810" y="115" font-size="11" font-weight="600" fill="{PRIMARY}" text-anchor="middle">7. Передача материалов</text>
      <text x="960" y="115" font-size="12" fill="{TEXT_MUTED}">Сегодня, 14:15</text>

      <!-- Row 2 -->
      <line x1="0" y1="136" x2="1140" y2="136" stroke="{BORDER}" stroke-width="1"/>
      <text x="24" y="162" font-size="13" font-weight="bold" fill="{PRIMARY}">Внедрение РТК Облако в НИУ ВШЭ</text>
      <text x="24" y="178" font-size="11" fill="{TEXT_MUTED}">НИУ ВШЭ · Цикл: 2026</text>
      <text x="420" y="162" font-size="13" font-weight="600" fill="{TEXT_MAIN}">Web-разработка</text>
      <text x="420" y="178" font-size="11" fill="{TEXT_MUTED}">РТК Сфера</text>
      <rect x="720" y="152" width="180" height="26" rx="13" fill="#FEF3F2"/>
      <text x="810" y="169" font-size="11" font-weight="600" fill="{ACCENT}" text-anchor="middle">6. Подписание документов</text>
      <text x="960" y="169" font-size="12" fill="{TEXT_MUTED}">Вчера, 17:30</text>

      <!-- Row 3 -->
      <line x1="0" y1="190" x2="1140" y2="190" stroke="{BORDER}" stroke-width="1"/>
      <text x="24" y="216" font-size="13" font-weight="bold" fill="{PRIMARY}">Практикум кибербезопасности МИФИ</text>
      <text x="24" y="232" font-size="11" fill="{TEXT_MUTED}">НИЯУ МИФИ · Цикл: 2026/2027</text>
      <text x="420" y="216" font-size="13" font-weight="600" fill="{TEXT_MAIN}">Информационная безопасность</text>
      <text x="420" y="232" font-size="11" fill="{TEXT_MUTED}">РТК Кибербезопасность</text>
      <rect x="720" y="206" width="180" height="26" rx="13" fill="#F0FDF4"/>
      <text x="810" y="223" font-size="11" font-weight="600" fill="#16A34A" text-anchor="middle">4. Обмен документами</text>
      <text x="960" y="223" font-size="12" fill="{TEXT_MUTED}">27.09.2026</text>
    </g>
  </g>
"""
    return wrap_svg(content)

# Generator 3: Interactions Registry
def gen_screen_03_interactions_registry() -> str:
    chrome = get_window_chrome("https://crm.school.rt.ru/interactions", "Реестр взаимодействий — ИТ Школа Ростелеком")
    shell = get_sidebar_and_topbar("interactions", ["Партнёры", "Реестр взаимодействий"])
    content = f"""
  {chrome}
  {shell}
  <g transform="translate(270, 150)">
    <!-- Header -->
    <text x="0" y="20" font-size="11" font-weight="bold" fill="#98A2B3" letter-spacing="1">ЕДИНЫЙ РЕЕСТР КАРТОЧЕК · ОБЛАСТЬ ДОСТУПА</text>
    <text x="0" y="50" font-size="24" font-weight="bold" fill="{TEXT_MAIN}">Реестр взаимодействий с вузами</text>
    <text x="0" y="72" font-size="13" fill="{TEXT_MUTED}">Управление всеми процессами партнёрства, фильтрация по этапам и договорам.</text>

    <rect x="940" y="28" width="200" height="42" rx="8" fill="{PRIMARY}"/>
    <text x="1040" y="54" font-size="14" font-weight="bold" fill="#FFFFFF" text-anchor="middle">+ Новое взаимодействие</text>

    <!-- Filter Bar Card -->
    <g transform="translate(0, 95)">
      <rect x="0" y="0" width="1140" height="64" rx="10" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1" filter="url(#shadow)"/>

      <!-- Search Input -->
      <rect x="16" y="14" width="320" height="36" rx="6" fill="#F8F9FC" stroke="{BORDER}" stroke-width="1"/>
      <circle cx="34" cy="32" r="5" fill="none" stroke="#98A2B3" stroke-width="1.5"/>
      <line x1="38" y1="36" x2="44" y2="42" stroke="#98A2B3" stroke-width="1.5"/>
      <text x="52" y="37" font-size="13" fill="#98A2B3">Поиск по вузу, названию, договору...</text>

      <!-- Dropdown 1: Organization -->
      <rect x="350" y="14" width="180" height="36" rx="6" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1"/>
      <text x="364" y="37" font-size="13" fill="{TEXT_MAIN}">Все организации</text>
      <text x="510" y="37" font-size="11" fill="{TEXT_MUTED}">▾</text>

      <!-- Dropdown 2: Program -->
      <rect x="544" y="14" width="180" height="36" rx="6" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1"/>
      <text x="558" y="37" font-size="13" fill="{TEXT_MAIN}">Все программы</text>
      <text x="704" y="37" font-size="11" fill="{TEXT_MUTED}">▾</text>

      <!-- Dropdown 3: Stage -->
      <rect x="738" y="14" width="200" height="36" rx="6" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1"/>
      <text x="752" y="37" font-size="13" fill="{TEXT_MAIN}">Все 15 этапов воронки</text>
      <text x="918" y="37" font-size="11" fill="{TEXT_MUTED}">▾</text>

      <!-- Reset button -->
      <rect x="952" y="14" width="172" height="36" rx="6" fill="#F4F5F8"/>
      <text x="1038" y="37" font-size="13" font-weight="600" fill="{TEXT_MUTED}" text-anchor="middle">Сбросить фильтры</text>
    </g>

    <!-- Table -->
    <g transform="translate(0, 175)">
      <rect x="0" y="0" width="1140" height="490" rx="10" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1" filter="url(#shadow)"/>

      <!-- Table Header -->
      <rect x="0" y="0" width="1140" height="42" rx="10" fill="#F8F9FC"/>
      <text x="24" y="26" font-size="11" font-weight="bold" fill="#98A2B3">ВЗАИМОДЕЙСТВИЕ / ОРГАНИЗАЦИЯ</text>
      <text x="410" y="26" font-size="11" font-weight="bold" fill="#98A2B3">ИТ-ПРОГРАММА И ПРОДУКТ</text>
      <text x="690" y="26" font-size="11" font-weight="bold" fill="#98A2B3">ЭТАП СОТРУДНИЧЕСТВА</text>
      <text x="910" y="26" font-size="11" font-weight="bold" fill="#98A2B3">КУРАТОР</text>
      <text x="1040" y="26" font-size="11" font-weight="bold" fill="#98A2B3">ОБНОВЛЕНО</text>

      <!-- Rows -->
      <!-- Row 1 -->
      <line x1="0" y1="42" x2="1140" y2="42" stroke="{BORDER}" stroke-width="1"/>
      <text x="24" y="68" font-size="14" font-weight="bold" fill="{PRIMARY}">Сотрудничество с МГТУ им. Баумана</text>
      <text x="24" y="86" font-size="11" fill="{TEXT_MUTED}">МГТУ им. Н.Э. Баумана · Договор № РТК-2026/089</text>
      <text x="410" y="68" font-size="13" font-weight="600" fill="{TEXT_MAIN}">DevOps инженерия</text>
      <text x="410" y="86" font-size="11" fill="{TEXT_MUTED}">Облачная Платформа РТК</text>
      <rect x="690" y="58" width="180" height="26" rx="13" fill="{PRIMARY_SUBTLE}"/>
      <text x="780" y="75" font-size="11" font-weight="600" fill="{PRIMARY}" text-anchor="middle">7. Передача материалов</text>
      <text x="910" y="75" font-size="13" fill="{TEXT_MAIN}">Анна Смирнова</text>
      <text x="1040" y="75" font-size="12" fill="{TEXT_MUTED}">Сегодня, 14:15</text>

      <!-- Row 2 -->
      <line x1="0" y1="104" x2="1140" y2="104" stroke="{BORDER}" stroke-width="1"/>
      <text x="24" y="130" font-size="14" font-weight="bold" fill="{PRIMARY}">Внедрение РТК Облако в НИУ ВШЭ</text>
      <text x="24" y="148" font-size="11" fill="{TEXT_MUTED}">НИУ ВШЭ · Договор № РТК-2026/104</text>
      <text x="410" y="130" font-size="13" font-weight="600" fill="{TEXT_MAIN}">Web-разработка</text>
      <text x="410" y="148" font-size="11" fill="{TEXT_MUTED}">РТК Сфера</text>
      <rect x="690" y="120" width="180" height="26" rx="13" fill="#FEF3F2"/>
      <text x="780" y="137" font-size="11" font-weight="600" fill="{ACCENT}" text-anchor="middle">6. Подписание документов</text>
      <text x="910" y="137" font-size="13" fill="{TEXT_MAIN}">Анна Смирнова</text>
      <text x="1040" y="137" font-size="12" fill="{TEXT_MUTED}">Вчера, 17:30</text>

      <!-- Row 3 -->
      <line x1="0" y1="166" x2="1140" y2="166" stroke="{BORDER}" stroke-width="1"/>
      <text x="24" y="192" font-size="14" font-weight="bold" fill="{PRIMARY}">Практикум по кибербезопасности НИЯУ МИФИ</text>
      <text x="24" y="210" font-size="11" fill="{TEXT_MUTED}">НИЯУ МИФИ · Договор № РТК-2026/112</text>
      <text x="410" y="192" font-size="13" font-weight="600" fill="{TEXT_MAIN}">Информационная безопасность</text>
      <text x="410" y="210" font-size="11" fill="{TEXT_MUTED}">РТК Кибербезопасность</text>
      <rect x="690" y="182" width="180" height="26" rx="13" fill="#F0FDF4"/>
      <text x="780" y="199" font-size="11" font-weight="600" fill="#16A34A" text-anchor="middle">4. Обмен документами</text>
      <text x="910" y="199" font-size="13" fill="{TEXT_MAIN}">Анна Смирнова</text>
      <text x="1040" y="199" font-size="12" fill="{TEXT_MUTED}">27.09.2026</text>

      <!-- Row 4 -->
      <line x1="0" y1="228" x2="1140" y2="228" stroke="{BORDER}" stroke-width="1"/>
      <text x="24" y="254" font-size="14" font-weight="bold" fill="{PRIMARY}">Цифровая кафедра СПбПУ</text>
      <text x="24" y="272" font-size="11" fill="{TEXT_MUTED}">СПбПУ · Договор в подготовке</text>
      <text x="410" y="254" font-size="13" font-weight="600" fill="{TEXT_MAIN}">DevOps инженерия</text>
      <text x="410" y="272" font-size="11" fill="{TEXT_MUTED}">Облачная Платформа РТК</text>
      <rect x="690" y="244" width="180" height="26" rx="13" fill="#EFF8FF"/>
      <text x="780" y="261" font-size="11" font-weight="600" fill="#0284C7" text-anchor="middle">3. Встреча с вузом</text>
      <text x="910" y="261" font-size="13" fill="{TEXT_MAIN}">Анна Смирнова</text>
      <text x="1040" y="261" font-size="12" fill="{TEXT_MUTED}">25.09.2026</text>

      <!-- Row 5 -->
      <line x1="0" y1="290" x2="1140" y2="290" stroke="{BORDER}" stroke-width="1"/>
      <text x="24" y="316" font-size="14" font-weight="bold" fill="{PRIMARY}">Образовательный трек МФТИ</text>
      <text x="24" y="334" font-size="11" fill="{TEXT_MUTED}">МФТИ · Инициация сотрудничества</text>
      <text x="410" y="316" font-size="13" font-weight="600" fill="{TEXT_MAIN}">Искусственный интеллект</text>
      <text x="410" y="334" font-size="11" fill="{TEXT_MUTED}">РТК AI Platform</text>
      <rect x="690" y="306" width="180" height="26" rx="13" fill="#FFF7ED"/>
      <text x="780" y="323" font-size="11" font-weight="600" fill="#EA580C" text-anchor="middle">2. Уточнение потребности</text>
      <text x="910" y="323" font-size="13" fill="{TEXT_MAIN}">Анна Смирнова</text>
      <text x="1040" y="323" font-size="12" fill="{TEXT_MUTED}">24.09.2026</text>

      <!-- Pagination -->
      <line x1="0" y1="430" x2="1140" y2="430" stroke="{BORDER}" stroke-width="1"/>
      <text x="24" y="460" font-size="13" fill="{TEXT_MUTED}">Показано 1–5 из 12 взаимодействий</text>

      <rect x="990" y="442" width="32" height="32" rx="6" fill="{PRIMARY}"/>
      <text x="1006" y="462" font-size="13" font-weight="bold" fill="#FFFFFF" text-anchor="middle">1</text>
      <rect x="1030" y="442" width="32" height="32" rx="6" fill="#F4F5F8"/>
      <text x="1046" y="462" font-size="13" fill="{TEXT_MAIN}" text-anchor="middle">2</text>
      <rect x="1070" y="442" width="32" height="32" rx="6" fill="#F4F5F8"/>
      <text x="1086" y="462" font-size="13" fill="{TEXT_MAIN}" text-anchor="middle">3</text>
    </g>
  </g>
"""
    return wrap_svg(content)

# Generator 4: Interaction Card & 15-Stage Graph
def gen_screen_04_interaction_card_graph() -> str:
    chrome = get_window_chrome("https://crm.school.rt.ru/interactions/ix-3", "Карточка ix-3 — ИТ Школа Ростелеком")
    shell = get_sidebar_and_topbar("interactions", ["Взаимодействия", "Карточка ix-3 (МГТУ)"])
    content = f"""
  {chrome}
  {shell}
  <g transform="translate(270, 150)">
    <!-- Header of Card -->
    <text x="0" y="20" font-size="11" font-weight="bold" fill="#98A2B3" letter-spacing="1">КАРТОЧКА ВЗАИМОДЕЙСТВИЯ · РЕВИЗИЯ rev: 4 (CAS)</text>
    <text x="0" y="50" font-size="24" font-weight="bold" fill="{TEXT_MAIN}">Сотрудничество с МГТУ им. Баумана</text>
    <rect x="470" y="30" width="180" height="26" rx="13" fill="{PRIMARY_SUBTLE}"/>
    <text x="560" y="47" font-size="12" font-weight="bold" fill="{PRIMARY}" text-anchor="middle">7. Передача материалов</text>

    <!-- Action Buttons Bar -->
    <g transform="translate(0, 75)">
      <!-- Primary Forward -->
      <rect x="0" y="0" width="260" height="40" rx="8" fill="{PRIMARY}"/>
      <text x="130" y="25" font-size="13" font-weight="bold" fill="#FFFFFF" text-anchor="middle">Перейти: 8. Сопровождение →</text>

      <!-- Secondary Rework -->
      <rect x="272" y="0" width="200" height="40" rx="8" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1.5"/>
      <text x="372" y="25" font-size="13" font-weight="600" fill="{TEXT_MAIN}" text-anchor="middle">Возврат на доработку</text>

      <!-- Danger Cancel -->
      <rect x="484" y="0" width="140" height="40" rx="8" fill="#FFFFFF" stroke="{ERROR_BORDER}" stroke-width="1.5"/>
      <text x="554" y="25" font-size="13" font-weight="600" fill="{ERROR_TEXT}" text-anchor="middle">Отменить (терм.)</text>

      <!-- Edit parameters -->
      <rect x="940" y="0" width="200" height="40" rx="8" fill="#FFFFFF" stroke="{PRIMARY}" stroke-width="1.5"/>
      <text x="1040" y="25" font-size="13" font-weight="bold" fill="{PRIMARY}" text-anchor="middle">Редактировать (D02)</text>
    </g>

    <!-- 15-Stage Workflow Pipeline Diagram -->
    <g transform="translate(0, 135)">
      <rect x="0" y="0" width="1140" height="270" rx="10" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1" filter="url(#shadow)"/>
      <text x="24" y="28" font-size="12" font-weight="bold" fill="{TEXT_MAIN}">Интерактивный граф жизненного цикла (13 рабочих + 2 терминальных состояния)</text>

      <!-- Phases layout -->
      <!-- Phase 1: Инициация -->
      <rect x="24" y="44" width="260" height="95" rx="8" fill="#F8F9FC" stroke="{BORDER}" stroke-width="1"/>
      <text x="36" y="62" font-size="11" font-weight="bold" fill="#98A2B3">ФАЗА 1: ИНИЦИАЦИЯ</text>
      <rect x="36" y="70" width="70" height="28" rx="6" fill="#DCFCE7"/>
      <text x="71" y="88" font-size="10" font-weight="bold" fill="#16A34A" text-anchor="middle">1. Контакт</text>
      <text x="110" y="88" font-size="12" fill="#98A2B3">→</text>
      <rect x="122" y="70" width="80" height="28" rx="6" fill="#DCFCE7"/>
      <text x="162" y="88" font-size="10" font-weight="bold" fill="#16A34A" text-anchor="middle">2. Потребность</text>
      <text x="206" y="88" font-size="12" fill="#98A2B3">→</text>
      <rect x="216" y="70" width="60" height="28" rx="6" fill="#DCFCE7"/>
      <text x="246" y="88" font-size="10" font-weight="bold" fill="#16A34A" text-anchor="middle">3. Встреча</text>

      <!-- Phase 2: Договоры -->
      <rect x="300" y="44" width="280" height="95" rx="8" fill="#F8F9FC" stroke="{BORDER}" stroke-width="1"/>
      <text x="312" y="62" font-size="11" font-weight="bold" fill="#98A2B3">ФАЗА 2: ДОГОВОРЫ</text>
      <rect x="312" y="70" width="76" height="28" rx="6" fill="#DCFCE7"/>
      <text x="350" y="88" font-size="10" font-weight="bold" fill="#16A34A" text-anchor="middle">4. Обмен док.</text>
      <text x="392" y="88" font-size="12" fill="#98A2B3">→</text>
      <rect x="402" y="70" width="84" height="28" rx="6" fill="#DCFCE7"/>
      <text x="444" y="88" font-size="10" font-weight="bold" fill="#16A34A" text-anchor="middle">5. Корректировка</text>
      <text x="490" y="88" font-size="12" fill="#98A2B3">→</text>
      <rect x="500" y="70" width="70" height="28" rx="6" fill="#DCFCE7"/>
      <text x="535" y="88" font-size="10" font-weight="bold" fill="#16A34A" text-anchor="middle">6. Подписание</text>

      <!-- Phase 3: Внедрение и обучение (CURRENT STAGE HIGHLIGHTED) -->
      <rect x="596" y="44" width="280" height="95" rx="8" fill="{PRIMARY_SUBTLE}" stroke="{PRIMARY}" stroke-width="1.5"/>
      <text x="608" y="62" font-size="11" font-weight="bold" fill="{PRIMARY}">ФАЗА 3: ВНЕДРЕНИЕ (ТЕКУЩИЙ ЭТАП)</text>
      <rect x="608" y="70" width="96" height="34" rx="6" fill="{PRIMARY}"/>
      <text x="656" y="91" font-size="10" font-weight="bold" fill="#FFFFFF" text-anchor="middle">7. Передача мат. ★</text>
      <text x="708" y="91" font-size="12" fill="{PRIMARY}">→</text>
      <rect x="718" y="70" width="74" height="28" rx="6" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1"/>
      <text x="755" y="88" font-size="10" fill="{TEXT_MUTED}" text-anchor="middle">8. Сопровожд.</text>
      <text x="796" y="88" font-size="12" fill="#98A2B3">→</text>
      <rect x="806" y="70" width="60" height="28" rx="6" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1"/>
      <text x="836" y="88" font-size="10" fill="{TEXT_MUTED}" text-anchor="middle">9. Обуч. преп.</text>

      <!-- Phase 4: Учебный процесс -->
      <rect x="892" y="44" width="224" height="95" rx="8" fill="#F8F9FC" stroke="{BORDER}" stroke-width="1"/>
      <text x="904" y="62" font-size="11" font-weight="bold" fill="#98A2B3">ФАЗА 4: УЧЕБНЫЙ ПРОЦЕСС</text>
      <rect x="904" y="70" width="94" height="28" rx="6" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1"/>
      <text x="951" y="88" font-size="10" fill="{TEXT_MUTED}" text-anchor="middle">10. Программа</text>
      <text x="1002" y="88" font-size="12" fill="#98A2B3">→</text>
      <rect x="1012" y="70" width="80" height="28" rx="6" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1"/>
      <text x="1052" y="88" font-size="10" fill="{TEXT_MUTED}" text-anchor="middle">11. Занятия</text>

      <!-- Terminal Stages line -->
      <g transform="translate(24, 155)">
        <text x="0" y="24" font-size="11" font-weight="bold" fill="#98A2B3">ДОПОЛНИТЕЛЬНЫЕ И ТЕРМИНАЛЬНЫЕ ЭТАПЫ:</text>
        <rect x="280" y="8" width="130" height="26" rx="6" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1"/>
        <text x="345" y="25" font-size="10" fill="{TEXT_MUTED}" text-anchor="middle">12. Обновление мат.</text>
        <rect x="424" y="8" width="140" height="26" rx="6" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1"/>
        <text x="494" y="25" font-size="10" fill="{TEXT_MUTED}" text-anchor="middle">13. Повыш. квалифик.</text>
        <rect x="700" y="8" width="160" height="26" rx="6" fill="#ECFDF3" stroke="{SUCCESS_BORDER}" stroke-width="1"/>
        <text x="780" y="25" font-size="10" font-weight="bold" fill="{SUCCESS_TEXT}" text-anchor="middle">14. Завершено успешно</text>
        <rect x="874" y="8" width="140" height="26" rx="6" fill="#FEF3F2" stroke="{ERROR_BORDER}" stroke-width="1"/>
        <text x="944" y="25" font-size="10" font-weight="bold" fill="{ERROR_TEXT}" text-anchor="middle">15. Отменено</text>
      </g>
    </g>

    <!-- Requisites Card -->
    <g transform="translate(0, 420)">
      <rect x="0" y="0" width="1140" height="270" rx="10" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1" filter="url(#shadow)"/>
      <text x="24" y="32" font-size="16" font-weight="bold" fill="{TEXT_MAIN}">Параметры и реквизиты взаимодействия</text>

      <!-- Grid 3x2 -->
      <g transform="translate(24, 55)">
        <text x="0" y="16" font-size="11" font-weight="bold" fill="#98A2B3">ОРГАНИЗАЦИЯ (ВУЗ)</text>
        <text x="0" y="36" font-size="15" font-weight="bold" fill="{PRIMARY}">МГТУ им. Н.Э. Баумана</text>
        <text x="0" y="52" font-size="12" fill="{TEXT_MUTED}">г. Москва · org-1</text>

        <text x="380" y="16" font-size="11" font-weight="bold" fill="#98A2B3">КОНТАКТНОЕ ЛИЦО В ВУЗЕ</text>
        <text x="380" y="36" font-size="15" font-weight="bold" fill="{TEXT_MAIN}">Смирнов Алексей Петрович</text>
        <text x="380" y="52" font-size="12" fill="{TEXT_MUTED}">Проректор по IT · devops@bmstu.ru</text>

        <text x="760" y="16" font-size="11" font-weight="bold" fill="#98A2B3">ИТ-ПРОГРАММА И ПРОДУКТ</text>
        <text x="760" y="36" font-size="15" font-weight="bold" fill="{TEXT_MAIN}">DevOps инженерия</text>
        <text x="760" y="52" font-size="12" fill="{PRIMARY}">Облачная Платформа РТК (совместимо)</text>
      </g>

      <line x1="24" y1="135" x2="1116" y2="135" stroke="{BORDER}" stroke-width="1"/>

      <g transform="translate(24, 150)">
        <text x="0" y="16" font-size="11" font-weight="bold" fill="#98A2B3">ДОГОВОР</text>
        <text x="0" y="36" font-size="14" font-weight="bold" fill="{TEXT_MAIN}">№ РТК-2026/089 от 15.09.2026</text>
        <text x="0" y="52" font-size="12" fill="#16A34A">Статус: подписан и активен</text>

        <text x="380" y="16" font-size="11" font-weight="bold" fill="#98A2B3">ЛИЦЕНЗИЯ НА ПРОДУКТ</text>
        <text x="380" y="36" font-size="14" font-weight="bold" fill="{TEXT_MAIN}">lic-rtk-cloud-089 (3 года)</text>
        <text x="380" y="52" font-size="12" fill="{PRIMARY}">Статус передачи: Передана</text>

        <text x="760" y="16" font-size="11" font-weight="bold" fill="#98A2B3">ОТВЕТСТВЕННЫЙ КУРАТОР</text>
        <text x="760" y="36" font-size="14" font-weight="bold" fill="{TEXT_MAIN}">Анна Смирнова</text>
        <text x="760" y="52" font-size="12" fill="{TEXT_MUTED}">Менеджер партнёрств (team_id: team-1)</text>
      </g>
    </g>
  </g>
"""
    return wrap_svg(content)

# Generator 5: D02 Deadlock Prevention Modal
def gen_screen_05_interaction_d02_prevent() -> str:
    base = gen_screen_04_interaction_card_graph()
    # Replace the outer closing tag with dimmed backdrop and modal
    modal_svg = f"""
  <!-- Dimmed Modal Backdrop -->
  <rect x="0" y="42" width="1440" height="858" fill="rgba(16, 24, 40, 0.65)"/>

  <!-- Centered Modal Dialog -->
  <g transform="translate(395, 120)" filter="url(#modal-shadow)">
    <rect x="0" y="0" width="650" height="660" rx="14" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1"/>

    <!-- Modal Header -->
    <rect x="0" y="0" width="650" height="64" rx="14" fill="#FFFFFF"/>
    <text x="28" y="40" font-size="18" font-weight="bold" fill="{TEXT_MAIN}">Редактировать параметры взаимодействия</text>
    <text x="610" y="38" font-size="18" fill="{TEXT_MUTED}" text-anchor="middle">✕</text>
    <line x1="0" y1="64" x2="650" y2="64" stroke="{BORDER}" stroke-width="1"/>

    <!-- D02 Prevention Banner -->
    <g transform="translate(28, 80)">
      <rect x="0" y="0" width="594" height="66" rx="8" fill="#ECFDF3" stroke="{SUCCESS_BORDER}" stroke-width="1"/>
      <circle cx="28" cy="33" r="14" fill="#D1FADF"/>
      <path d="M22 33 L26 37 L34 29" fill="none" stroke="#027A48" stroke-width="2"/>
      <text x="52" y="28" font-size="13" font-weight="bold" fill="{SUCCESS_TEXT}">Защита от дедлока D02: обязательная связка программы и продукта</text>
      <text x="52" y="46" font-size="11" fill="#065F46">Переход на этап «7. Передача материалов» заблокирован без валидной пары.</text>
    </g>

    <!-- Form Fields -->
    <g transform="translate(28, 165)">
      <!-- Field 1: Title -->
      <text x="0" y="14" font-size="12" font-weight="bold" fill="{TEXT_MAIN}">Название взаимодействия *</text>
      <rect x="0" y="24" width="594" height="38" rx="6" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1"/>
      <text x="14" y="48" font-size="13" fill="{TEXT_MAIN}">Сотрудничество с МГТУ им. Баумана</text>

      <!-- Field 2: Program -->
      <text x="0" y="86" font-size="12" font-weight="bold" fill="{TEXT_MAIN}">ИТ-программа обучения *</text>
      <rect x="0" y="96" width="594" height="38" rx="6" fill="#FFFFFF" stroke="{PRIMARY}" stroke-width="1.5"/>
      <text x="14" y="120" font-size="13" font-weight="bold" fill="{PRIMARY}">DevOps инженерия (program-devops)</text>
      <text x="565" y="120" font-size="11" fill="{PRIMARY}">▾</text>

      <!-- Field 3: Product (Validated) -->
      <text x="0" y="158" font-size="12" font-weight="bold" fill="{TEXT_MAIN}">ИТ-продукт вендора (строго совместимый) *</text>
      <rect x="0" y="168" width="594" height="38" rx="6" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1"/>
      <text x="14" y="192" font-size="13" fill="{TEXT_MAIN}">Облачная Платформа РТК (product-rtk-cloud)</text>
      <rect x="420" y="174" width="130" height="24" rx="4" fill="#ECFDF3"/>
      <text x="485" y="190" font-size="10" font-weight="bold" fill="{SUCCESS_TEXT}" text-anchor="middle">✓ Совместимо</text>
      <text x="565" y="192" font-size="11" fill="{TEXT_MUTED}">▾</text>

      <!-- Field 4: Contact -->
      <text x="0" y="230" font-size="12" font-weight="bold" fill="{TEXT_MAIN}">Контактное лицо вуза</text>
      <rect x="0" y="240" width="594" height="38" rx="6" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1"/>
      <text x="14" y="264" font-size="13" fill="{TEXT_MAIN}">Смирнов Алексей Петрович (Проректор по IT)</text>
      <text x="565" y="264" font-size="11" fill="{TEXT_MUTED}">▾</text>

      <!-- Field 5: Contract -->
      <text x="0" y="302" font-size="12" font-weight="bold" fill="{TEXT_MAIN}">Связанный договор</text>
      <rect x="0" y="312" width="594" height="38" rx="6" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1"/>
      <text x="14" y="336" font-size="13" fill="{TEXT_MAIN}">Договор № РТК-2026/089 от 15.09.2026 (активен)</text>
      <text x="565" y="336" font-size="11" fill="{TEXT_MUTED}">▾</text>

      <!-- Cycle label -->
      <text x="0" y="374" font-size="12" font-weight="bold" fill="{TEXT_MAIN}">Метка цикла сотрудничества</text>
      <rect x="0" y="384" width="594" height="38" rx="6" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1"/>
      <text x="14" y="408" font-size="13" fill="{TEXT_MAIN}">2026/2027-осень</text>
    </g>

    <!-- Modal Footer -->
    <line x1="0" y1="600" x2="650" y2="600" stroke="{BORDER}" stroke-width="1"/>
    <text x="28" y="632" font-size="11" fill="{TEXT_MUTED}">Оптимистическая блокировка: <tspan font-weight="bold">expected_revision = 4</tspan></text>
    <rect x="390" y="612" width="100" height="36" rx="6" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1"/>
    <text x="440" y="635" font-size="13" fill="{TEXT_MAIN}" text-anchor="middle">Отмена</text>
    <rect x="502" y="612" width="120" height="36" rx="6" fill="{PRIMARY}"/>
    <text x="562" y="635" font-size="13" font-weight="bold" fill="#FFFFFF" text-anchor="middle">Сохранить</text>
  </g>
</svg>"""
    return base.replace("</svg>", modal_svg)

# Generator 6: Transition Modal with Required Comment (Rework)
def gen_screen_06_interaction_transition_rework() -> str:
    base = gen_screen_04_interaction_card_graph()
    modal_svg = f"""
  <!-- Dimmed Modal Backdrop -->
  <rect x="0" y="42" width="1440" height="858" fill="rgba(16, 24, 40, 0.65)"/>

  <!-- Centered Modal Dialog -->
  <g transform="translate(420, 180)" filter="url(#modal-shadow)">
    <rect x="0" y="0" width="600" height="520" rx="14" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1"/>

    <!-- Modal Header -->
    <rect x="0" y="0" width="600" height="64" rx="14" fill="#FFFFFF"/>
    <text x="28" y="40" font-size="18" font-weight="bold" fill="{TEXT_MAIN}">Возврат на доработку (comment_required: true)</text>
    <text x="565" y="38" font-size="18" fill="{TEXT_MUTED}" text-anchor="middle">✕</text>
    <line x1="0" y1="64" x2="600" y2="64" stroke="{BORDER}" stroke-width="1"/>

    <!-- Transition target badge -->
    <g transform="translate(28, 85)">
      <rect x="0" y="0" width="544" height="42" rx="8" fill="#FFF7ED" stroke="#FEDF89" stroke-width="1"/>
      <text x="16" y="26" font-size="13" fill="#9A3412">Целевой этап: <tspan font-weight="bold">5. Корректировка документов</tspan></text>
      <rect x="420" y="10" width="110" height="22" rx="4" fill="#FEF3C7"/>
      <text x="475" y="25" font-size="10" font-weight="bold" fill="#B45309" text-anchor="middle">Цикл доработки</text>
    </g>

    <!-- Warning requirement banner -->
    <g transform="translate(28, 140)">
      <rect x="0" y="0" width="544" height="56" rx="8" fill="#F8F9FC" stroke="{BORDER}" stroke-width="1"/>
      <text x="16" y="24" font-size="12" font-weight="bold" fill="{TEXT_MAIN}">Регламентное требование:</text>
      <text x="16" y="42" font-size="11" fill="{TEXT_MUTED}">
        Возврат на доработку требует обязательного указания причины для сохранения в Audit Trail.
      </text>
    </g>

    <!-- Comment textarea -->
    <g transform="translate(28, 215)">
      <text x="0" y="14" font-size="12" font-weight="bold" fill="{TEXT_MAIN}">Обоснование возврата на доработку *</text>
      <rect x="0" y="24" width="544" height="120" rx="8" fill="#FFFFFF" stroke="{PRIMARY}" stroke-width="1.5"/>
      <text x="14" y="48" font-size="13" fill="{TEXT_MAIN}">
        Необходимо скорректировать пункт 4.2 соглашения о лицензиях
      </text>
      <text x="14" y="68" font-size="13" fill="{TEXT_MAIN}">
        на Облачную Платформу РТК по замечаниям правового управления
      </text>
      <text x="14" y="88" font-size="13" fill="{TEXT_MAIN}">
        МГТУ им. Н.Э. Баумана. Требуется уточнить количество пользователей.
      </text>
      <text x="530" y="134" font-size="11" fill="#98A2B3" text-anchor="end">184 / 1000 символов</text>
    </g>

    <!-- Invariant AC21 Notice -->
    <g transform="translate(28, 385)">
      <rect x="0" y="0" width="544" height="52" rx="8" fill="#ECFDF3" stroke="{SUCCESS_BORDER}" stroke-width="1"/>
      <text x="16" y="22" font-size="11" font-weight="bold" fill="{SUCCESS_TEXT}">Инвариант AC21: Сохранение пользовательского ввода</text>
      <text x="16" y="38" font-size="11" fill="#065F46">
        При сетевом сбое или конфликте 409 Conflict введённый текст не сбрасывается.
      </text>
    </g>

    <!-- Footer -->
    <line x1="0" y1="455" x2="600" y2="455" stroke="{BORDER}" stroke-width="1"/>
    <rect x="290" y="468" width="100" height="38" rx="6" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1"/>
    <text x="340" y="492" font-size="13" fill="{TEXT_MAIN}" text-anchor="middle">Отмена</text>

    <rect x="402" y="468" width="170" height="38" rx="6" fill="{ACCENT}"/>
    <text x="487" y="492" font-size="13" font-weight="bold" fill="#FFFFFF" text-anchor="middle">Подтвердить возврат</text>
  </g>
</svg>"""
    return base.replace("</svg>", modal_svg)

# Generator 7: Attachments & Audit Trail
def gen_screen_07_attachments_and_audit() -> str:
    chrome = get_window_chrome("https://crm.school.rt.ru/interactions/ix-3#attachments", "Вложения и аудит — ИТ Школа Ростелеком")
    shell = get_sidebar_and_topbar("interactions", ["Взаимодействия", "Вложения и Audit Trail"])
    content = f"""
  {chrome}
  {shell}
  <g transform="translate(270, 150)">
    <text x="0" y="20" font-size="11" font-weight="bold" fill="#98A2B3" letter-spacing="1">ДОКУМЕНТООБОРОТ И БЕЗОПАСНОСТЬ 152-ФЗ</text>
    <text x="0" y="50" font-size="24" font-weight="bold" fill="{TEXT_MAIN}">Вложения, файлы (25 МБ, 10 форматов) и Audit Trail</text>
    <text x="0" y="72" font-size="13" fill="{TEXT_MUTED}">Хранилище с проверкой magic bytes, ClamAV и хронологическая лента неизменяемых событий.</text>

    <!-- Attachments Section Card -->
    <g transform="translate(0, 95)">
      <rect x="0" y="0" width="1140" height="290" rx="10" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1" filter="url(#shadow)"/>
      <text x="24" y="32" font-size="16" font-weight="bold" fill="{TEXT_MAIN}">Сопроводительные документы взаимодействия</text>

      <!-- Drag & Drop Uploader -->
      <rect x="24" y="48" width="1092" height="74" rx="8" fill="#F8F9FC" stroke="{PRIMARY}" stroke-width="1.5" stroke-dasharray="6,4"/>
      <circle cx="56" cy="85" r="16" fill="{PRIMARY_SUBTLE}"/>
      <text x="56" y="90" font-size="14" fill="{PRIMARY}" text-anchor="middle">↑</text>
      <text x="86" y="80" font-size="13" font-weight="bold" fill="{PRIMARY}">Перетащите файлы сюда или нажмите для выбора на диске</text>
      <text x="86" y="98" font-size="11" fill="{TEXT_MUTED}">
        Лимит 25 МБ · 10 форматов ТЗ: PNG, JPEG, PDF, ZIP, GZIP, RAR, DOC, DOCX, XLS, XLSX · Проверка SHA-256
      </text>

      <!-- Table of files -->
      <g transform="translate(24, 136)">
        <rect x="0" y="0" width="1092" height="30" fill="#F4F5F8"/>
        <text x="14" y="20" font-size="11" font-weight="bold" fill="#98A2B3">ИМЯ ФАЙЛА / ФОРМАТ</text>
        <text x="380" y="20" font-size="11" font-weight="bold" fill="#98A2B3">РАЗМЕР</text>
        <text x="490" y="20" font-size="11" font-weight="bold" fill="#98A2B3">КОНТРОЛЬНАЯ СУММА SHA-256</text>
        <text x="820" y="20" font-size="11" font-weight="bold" fill="#98A2B3">ЗАГРУЗИЛ</text>
        <text x="990" y="20" font-size="11" font-weight="bold" fill="#98A2B3">ДЕЙСТВИЕ</text>

        <!-- File 1 -->
        <line x1="0" y1="30" x2="1092" y2="30" stroke="{BORDER}" stroke-width="1"/>
        <rect x="14" y="40" width="36" height="20" rx="4" fill="#FEF3F2"/>
        <text x="32" y="54" font-size="10" font-weight="bold" fill="#B42318" text-anchor="middle">PDF</text>
        <text x="58" y="54" font-size="13" font-weight="bold" fill="{TEXT_MAIN}">dogovor_rtk_mgtu_signed.pdf</text>
        <text x="380" y="54" font-size="12" fill="{TEXT_MUTED}">2.4 МБ</text>
        <text x="490" y="54" font-size="11" fill="#475467" font-family="monospace">e3b0c44298fc1c149afbf4c8996fb924...</text>
        <text x="820" y="54" font-size="12" fill="{TEXT_MAIN}">Анна Смирнова</text>
        <text x="990" y="54" font-size="12" font-weight="bold" fill="{PRIMARY}">Скачать ↓</text>

        <!-- File 2 -->
        <line x1="0" y1="72" x2="1092" y2="72" stroke="{BORDER}" stroke-width="1"/>
        <rect x="14" y="82" width="36" height="20" rx="4" fill="#EFF8FF"/>
        <text x="32" y="96" font-size="10" font-weight="bold" fill="#175CD3" text-anchor="middle">DOC</text>
        <text x="58" y="96" font-size="13" font-weight="bold" fill="{TEXT_MAIN}">tech_specification_v2.docx</text>
        <text x="380" y="96" font-size="12" fill="{TEXT_MUTED}">840 КБ</text>
        <text x="490" y="96" font-size="11" fill="#475467" font-family="monospace">7f83b1657ff1fc53b92dc18148a1d65d...</text>
        <text x="820" y="96" font-size="12" fill="{TEXT_MAIN}">Анна Смирнова</text>
        <text x="990" y="96" font-size="12" font-weight="bold" fill="{PRIMARY}">Скачать ↓</text>

        <!-- File 3 -->
        <line x1="0" y1="114" x2="1092" y2="114" stroke="{BORDER}" stroke-width="1"/>
        <rect x="14" y="124" width="36" height="20" rx="4" fill="#ECFDF3"/>
        <text x="32" y="138" font-size="10" font-weight="bold" fill="#027A48" text-anchor="middle">XLS</text>
        <text x="58" y="138" font-size="13" font-weight="bold" fill="{TEXT_MAIN}">licenses_distribution.xlsx</text>
        <text x="380" y="138" font-size="12" fill="{TEXT_MUTED}">320 КБ</text>
        <text x="490" y="138" font-size="11" fill="#475467" font-family="monospace">a1b2c3d4e5f6789012345678abcdef01...</text>
        <text x="820" y="138" font-size="12" fill="{TEXT_MAIN}">Анна Смирнова</text>
        <text x="990" y="138" font-size="12" font-weight="bold" fill="{PRIMARY}">Скачать ↓</text>
      </g>
    </g>

    <!-- Audit Trail Section Card -->
    <g transform="translate(0, 405)">
      <rect x="0" y="0" width="1140" height="280" rx="10" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1" filter="url(#shadow)"/>
      <text x="24" y="32" font-size="16" font-weight="bold" fill="{TEXT_MAIN}">Неизменяемый журнал аудита событий (Audit Trail)</text>
      <text x="950" y="32" font-size="12" fill="{TEXT_MUTED}">Всего записей: <tspan font-weight="bold">4 события</tspan></text>

      <!-- Timeline Entries -->
      <g transform="translate(24, 55)">
        <!-- Event 1 -->
        <circle cx="16" cy="16" r="6" fill="{PRIMARY}"/>
        <line x1="16" y1="26" x2="16" y2="60" stroke="{BORDER}" stroke-width="2"/>
        <text x="36" y="15" font-size="13" font-weight="bold" fill="{TEXT_MAIN}">
          Seq #4 · transition_executed (Переход на этап «7. Передача материалов»)
        </text>
        <text x="36" y="32" font-size="11" fill="{TEXT_MUTED}">
          29.09.2026, 14:15 · Инициатор: Анна Смирнова · CAS ревизия rev: 4
        </text>

        <!-- Event 2 -->
        <circle cx="16" cy="70" r="6" fill="#16A34A"/>
        <line x1="16" y1="80" x2="16" y2="114" stroke="{BORDER}" stroke-width="2"/>
        <text x="36" y="69" font-size="13" font-weight="bold" fill="{TEXT_MAIN}">
          Seq #3 · attributes_corrected (Устранение дедлока D02: назначена программа и продукт)
        </text>
        <text x="36" y="86" font-size="11" fill="{TEXT_MUTED}">
          29.09.2026, 11:30 · Инициатор: Анна Смирнова · payload: program-devops + product-rtk-cloud
        </text>

        <!-- Event 3 -->
        <circle cx="16" cy="124" r="6" fill="#0284C7"/>
        <line x1="16" y1="134" x2="16" y2="168" stroke="{BORDER}" stroke-width="2"/>
        <text x="36" y="123" font-size="13" font-weight="bold" fill="{TEXT_MAIN}">
          Seq #2 · attachment_uploaded (Загружен файл dogovor_rtk_mgtu_signed.pdf)
        </text>
        <text x="36" y="140" font-size="11" fill="{TEXT_MUTED}">
          28.09.2026, 16:45 · Инициатор: Анна Смирнова · Размер: 2.4 МБ · SHA-256 проверен
        </text>

        <!-- Event 4 -->
        <circle cx="16" cy="178" r="6" fill="#98A2B3"/>
        <text x="36" y="177" font-size="13" font-weight="bold" fill="{TEXT_MAIN}">
          Seq #1 · interaction_created (Создание карточки взаимодействия)
        </text>
        <text x="36" y="194" font-size="11" fill="{TEXT_MUTED}">
          25.09.2026, 10:00 · Инициатор: Анна Смирнова · Статус: 1. Поиск контактов
        </text>
      </g>
    </g>
  </g>
"""
    return wrap_svg(content)

# Generator 8: Supervisor Overview & Reassign
def gen_screen_08_supervisor_overview_reassign() -> str:
    chrome = get_window_chrome("https://crm.school.rt.ru/overview", "Консоль руководителя — ИТ Школа Ростелеком")
    shell = get_sidebar_and_topbar("overview", ["Партнёры", "Консоль руководителя (Supervisor)"], "Елена Соколова", "Руководитель направления")
    content = f"""
  {chrome}
  {shell}
  <g transform="translate(270, 150)">
    <text x="0" y="20" font-size="11" font-weight="bold" fill="#98A2B3" letter-spacing="1">СКВОЗНОЙ КОНТРОЛЬ ПОДРАЗДЕЛЕНИЯ · КОМАНДА team-1</text>
    <text x="0" y="50" font-size="24" font-weight="bold" fill="{TEXT_MAIN}">Управление кураторами и переназначение (Reassign)</text>
    <text x="0" y="72" font-size="13" fill="{TEXT_MUTED}">Контроль нагрузки менеджеров, ротация ответственных с мгновенным отзывом прав (HTTP 404).</text>

    <!-- Quota cards -->
    <g transform="translate(0, 95)">
      <rect x="0" y="0" width="360" height="110" rx="10" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1" filter="url(#shadow)"/>
      <text x="20" y="28" font-size="12" fill="{TEXT_MUTED}">Карточек в отделе (team-1)</text>
      <text x="20" y="66" font-size="32" font-weight="bold" fill="{PRIMARY}">24</text>
      <text x="20" y="90" font-size="11" fill="#16A34A">100% карточек охвачено контролем</text>

      <rect x="390" y="0" width="360" height="110" rx="10" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1" filter="url(#shadow)"/>
      <text x="20" y="28" font-size="12" fill="{TEXT_MUTED}">Менеджер Анна Смирнова</text>
      <text x="20" y="66" font-size="32" font-weight="bold" fill="{ACCENT}">12</text>
      <text x="20" y="90" font-size="11" fill="#98A2B3">Нагрузка: 50% объема команды</text>

      <rect x="780" y="0" width="360" height="110" rx="10" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1" filter="url(#shadow)"/>
      <text x="20" y="28" font-size="12" fill="{TEXT_MUTED}">Менеджер Борис Васильев</text>
      <text x="20" y="66" font-size="32" font-weight="bold" fill="#0284C7">4</text>
      <text x="20" y="90" font-size="11" fill="#16A34A">Свободный резерв для новых вузов</text>
    </g>

    <!-- Reassign Action Panel -->
    <g transform="translate(0, 230)">
      <rect x="0" y="0" width="1140" height="460" rx="10" fill="#FFFFFF" stroke="{PRIMARY}" stroke-width="1.5" filter="url(#shadow)"/>
      <rect x="0" y="0" width="1140" height="50" rx="10" fill="{PRIMARY_SUBTLE}"/>
      <text x="24" y="32" font-size="16" font-weight="bold" fill="{PRIMARY}">
        Панель ротации ответственного куратора (Reassign Protocol)
      </text>

      <!-- Target Interaction Card Header -->
      <g transform="translate(24, 75)">
        <text x="0" y="16" font-size="12" font-weight="bold" fill="#98A2B3">ВЫБРАННОЕ ВЗАИМОДЕЙСТВИЕ ДЛЯ ПЕРЕДАЧИ:</text>
        <text x="0" y="42" font-size="18" font-weight="bold" fill="{TEXT_MAIN}">Сотрудничество с МГТУ им. Баумана (ix-3)</text>
        <text x="0" y="62" font-size="13" fill="{TEXT_MUTED}">МГТУ им. Н.Э. Баумана · Этап: 7. Передача материалов · Текущий куратор: Анна Смирнова</text>
      </g>

      <!-- Reassign Form Controls -->
      <g transform="translate(24, 165)">
        <text x="0" y="14" font-size="13" font-weight="bold" fill="{TEXT_MAIN}">Назначить нового ответственного куратора *</text>
        <rect x="0" y="26" width="520" height="42" rx="6" fill="#FFFFFF" stroke="{PRIMARY}" stroke-width="1.5"/>
        <circle cx="24" cy="47" r="12" fill="#E0F2FE"/>
        <text x="24" y="52" font-size="11" font-weight="bold" fill="#0284C7" text-anchor="middle">БВ</text>
        <text x="46" y="52" font-size="14" font-weight="bold" fill="{TEXT_MAIN}">Борис Васильев</text>
        <text x="180" y="52" font-size="12" fill="{TEXT_MUTED}">(Менеджер партнёрств, 4 карточки в работе)</text>
        <text x="495" y="52" font-size="12" fill="{PRIMARY}">▾</text>

        <text x="0" y="96" font-size="13" font-weight="bold" fill="{TEXT_MAIN}">Обоснование переназначения (запись в Audit Trail) *</text>
        <rect x="0" y="108" width="1092" height="64" rx="6" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1"/>
        <text x="16" y="134" font-size="13" fill="{TEXT_MAIN}">
          Перераспределение нагрузки кураторов в связи с запуском нового регионального трека в СПбПУ.
        </text>

        <!-- 152-FZ Zero-Oracle Warning -->
        <g transform="translate(0, 190)">
          <rect x="0" y="0" width="1092" height="66" rx="8" fill="#FEF3F2" stroke="{ERROR_BORDER}" stroke-width="1"/>
          <circle cx="28" cy="33" r="14" fill="#FEE4E2"/>
          <text x="28" y="38" font-size="14" font-weight="bold" fill="{ERROR_TEXT}" text-anchor="middle">!</text>
          <text x="54" y="26" font-size="13" font-weight="bold" fill="{ERROR_TEXT}">
            Инвариант 152-ФЗ Zero-Oracle: Мгновенный отзыв доступа
          </text>
          <text x="54" y="46" font-size="11" fill="#7A271A">
            С момента фиксации переназначения прежний менеджер Анна Смирнова немедленно утратит доступ к карточке.
            Любая попытка прямого обращения по ID вернет HTTP 404 Not Found (сокрытие факта существования).
          </text>
        </g>

        <!-- Submit Button -->
        <rect x="850" y="270" width="242" height="44" rx="8" fill="{PRIMARY}"/>
        <text x="971" y="297" font-size="14" font-weight="bold" fill="#FFFFFF" text-anchor="middle">
          Передать карточку куратору →
        </text>
      </g>
    </g>
  </g>
"""
    return wrap_svg(content)

# Generator 9: Reports & Analytics Export
def gen_screen_09_reports_analytics_export() -> str:
    chrome = get_window_chrome("https://crm.school.rt.ru/reports", "Аналитика и экспорт — ИТ Школа Ростелеком")
    shell = get_sidebar_and_topbar("reports", ["Партнёры", "Аналитика и отчёты"])
    content = f"""
  {chrome}
  {shell}
  <g transform="translate(270, 150)">
    <text x="0" y="20" font-size="11" font-weight="bold" fill="#98A2B3" letter-spacing="1">ТЕМПОРАЛЬНЫЙ АНАЛИТИЧЕСКИЙ ДВИЖОК</text>
    <text x="0" y="50" font-size="24" font-weight="bold" fill="{TEXT_MAIN}">Отчёты и бинарная выгрузка данных (XLSX / PDF / JSON)</text>
    <text x="0" y="72" font-size="13" fill="{TEXT_MUTED}">Генерация срезов на дату, динамики переходов и экспорт по брендбуку Ростелеком.</text>

    <!-- 3 Modes Tabs -->
    <g transform="translate(0, 95)">
      <!-- Tab 1: Snapshot (ACTIVE) -->
      <rect x="0" y="0" width="220" height="40" rx="8" fill="{PRIMARY}"/>
      <text x="110" y="25" font-size="13" font-weight="bold" fill="#FFFFFF" text-anchor="middle">1. Срез на дату (Snapshot)</text>

      <!-- Tab 2: Activity -->
      <rect x="230" y="0" width="240" height="40" rx="8" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1"/>
      <text x="350" y="25" font-size="13" fill="{TEXT_MAIN}" text-anchor="middle">2. Динамика переходов (Activity)</text>

      <!-- Tab 3: Created -->
      <rect x="480" y="0" width="220" height="40" rx="8" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1"/>
      <text x="590" y="25" font-size="13" fill="{TEXT_MAIN}" text-anchor="middle">3. Созданные карточки (Created)</text>

      <!-- Export Buttons -->
      <rect x="800" y="0" width="105" height="40" rx="8" fill="#107C41"/>
      <text x="852" y="25" font-size="12" font-weight="bold" fill="#FFFFFF" text-anchor="middle">XLSX ↓</text>

      <rect x="915" y="0" width="105" height="40" rx="8" fill="#C4302B"/>
      <text x="967" y="25" font-size="12" font-weight="bold" fill="#FFFFFF" text-anchor="middle">PDF ↓</text>

      <rect x="1030" y="0" width="110" height="40" rx="8" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1"/>
      <text x="1085" y="25" font-size="12" font-weight="bold" fill="{TEXT_MAIN}" text-anchor="middle">JSON {{ }}</text>
    </g>

    <!-- Filter Card -->
    <g transform="translate(0, 150)">
      <rect x="0" y="0" width="1140" height="60" rx="8" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1" filter="url(#shadow)"/>
      <text x="20" y="35" font-size="12" font-weight="bold" fill="{TEXT_MAIN}">Дата среза (as_of):</text>
      <rect x="150" y="14" width="140" height="32" rx="6" fill="#F8F9FC" stroke="{BORDER}" stroke-width="1"/>
      <text x="164" y="35" font-size="12" fill="{TEXT_MAIN}">29.09.2026</text>

      <text x="320" y="35" font-size="12" font-weight="bold" fill="{TEXT_MAIN}">Knowledge Cutoff:</text>
      <rect x="440" y="14" width="180" height="32" rx="6" fill="#F8F9FC" stroke="{BORDER}" stroke-width="1"/>
      <text x="454" y="35" font-size="12" fill="{TEXT_MAIN}">2026-09-29T18:00:00Z</text>

      <text x="650" y="35" font-size="12" font-weight="bold" fill="{TEXT_MAIN}">Организация:</text>
      <rect x="750" y="14" width="200" height="32" rx="6" fill="#F8F9FC" stroke="{BORDER}" stroke-width="1"/>
      <text x="764" y="35" font-size="12" fill="{TEXT_MAIN}">Все партнёры (12 вузов)</text>
      <text x="930" y="35" font-size="11" fill="{TEXT_MUTED}">▾</text>
    </g>

    <!-- Interactive Funnel SVG Chart & Table -->
    <g transform="translate(0, 225)">
      <!-- Left: Stage Distribution Funnel Chart -->
      <rect x="0" y="0" width="460" height="460" rx="10" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1" filter="url(#shadow)"/>
      <text x="24" y="32" font-size="15" font-weight="bold" fill="{TEXT_MAIN}">Распределение процессов по фазам</text>

      <!-- SVG Funnel Bars -->
      <g transform="translate(24, 70)">
        <text x="0" y="20" font-size="13" font-weight="600" fill="{TEXT_MAIN}">Фаза 1: Инициация</text>
        <rect x="0" y="30" width="412" height="26" rx="6" fill="#F4F5F8"/>
        <rect x="0" y="30" width="137" height="26" rx="6" fill="{PRIMARY}"/>
        <text x="145" y="48" font-size="12" font-weight="bold" fill="{PRIMARY}">3 вуза (25%)</text>

        <text x="0" y="85" font-size="13" font-weight="600" fill="{TEXT_MAIN}">Фаза 2: Договоры</text>
        <rect x="0" y="95" width="412" height="26" rx="6" fill="#F4F5F8"/>
        <rect x="0" y="95" width="183" height="26" rx="6" fill="{PRIMARY_HOVER}"/>
        <text x="191" y="113" font-size="12" font-weight="bold" fill="{PRIMARY}">4 вуза (33%)</text>

        <text x="0" y="150" font-size="13" font-weight="600" fill="{TEXT_MAIN}">Фаза 3: Внедрение</text>
        <rect x="0" y="160" width="412" height="26" rx="6" fill="#F4F5F8"/>
        <rect x="0" y="160" width="137" height="26" rx="6" fill="{ACCENT}"/>
        <text x="145" y="178" font-size="12" font-weight="bold" fill="{ACCENT}">3 вуза (25%)</text>

        <text x="0" y="215" font-size="13" font-weight="600" fill="{TEXT_MAIN}">Фаза 4: Обучение</text>
        <rect x="0" y="225" width="412" height="26" rx="6" fill="#F4F5F8"/>
        <rect x="0" y="225" width="46" height="26" rx="6" fill="#0284C7"/>
        <text x="54" y="243" font-size="12" font-weight="bold" fill="#0284C7">1 вуз (8%)</text>

        <text x="0" y="280" font-size="13" font-weight="600" fill="{TEXT_MAIN}">Фаза 5: Завершено</text>
        <rect x="0" y="290" width="412" height="26" rx="6" fill="#F4F5F8"/>
        <rect x="0" y="290" width="46" height="26" rx="6" fill="#16A34A"/>
        <text x="54" y="308" font-size="12" font-weight="bold" fill="#16A34A">1 вуз (8%)</text>
      </g>

      <!-- Right: Data Table -->
      <rect x="480" y="0" width="660" height="460" rx="10" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1" filter="url(#shadow)"/>
      <text x="504" y="32" font-size="15" font-weight="bold" fill="{TEXT_MAIN}">Таблица среза данных (12 строк)</text>

      <g transform="translate(480, 50)">
        <rect x="0" y="0" width="660" height="32" fill="#7700FF"/>
        <text x="20" y="21" font-size="11" font-weight="bold" fill="#FFFFFF">ВУЗ / ОРГАНИЗАЦИЯ</text>
        <text x="240" y="21" font-size="11" font-weight="bold" fill="#FFFFFF">ИТ-ПРОГРАММА</text>
        <text x="440" y="21" font-size="11" font-weight="bold" fill="#FFFFFF">ЭТАП СРЕЗА</text>
        <text x="580" y="21" font-size="11" font-weight="bold" fill="#FFFFFF">ОТВЕТСТВ.</text>

        <!-- Rows -->
        <rect x="0" y="32" width="660" height="34" fill="#FFFFFF"/>
        <text x="20" y="54" font-size="12" font-weight="bold" fill="{TEXT_MAIN}">МГТУ им. Н.Э. Баумана</text>
        <text x="240" y="54" font-size="12" fill="{TEXT_MAIN}">DevOps инженерия</text>
        <text x="440" y="54" font-size="11" fill="{PRIMARY}">7. Передача мат.</text>
        <text x="580" y="54" font-size="11" fill="{TEXT_MUTED}">А. Смирнова</text>

        <rect x="0" y="66" width="660" height="34" fill="#F4F5F8"/>
        <text x="20" y="88" font-size="12" font-weight="bold" fill="{TEXT_MAIN}">НИУ ВШЭ</text>
        <text x="240" y="88" font-size="12" fill="{TEXT_MAIN}">Web-разработка</text>
        <text x="440" y="88" font-size="11" fill="{ACCENT}">6. Подписание</text>
        <text x="580" y="88" font-size="11" fill="{TEXT_MUTED}">А. Смирнова</text>

        <rect x="0" y="100" width="660" height="34" fill="#FFFFFF"/>
        <text x="20" y="122" font-size="12" font-weight="bold" fill="{TEXT_MAIN}">НИЯУ МИФИ</text>
        <text x="240" y="122" font-size="12" fill="{TEXT_MAIN}">Информационная безоп.</text>
        <text x="440" y="122" font-size="11" fill="#16A34A">4. Обмен док.</text>
        <text x="580" y="122" font-size="11" fill="{TEXT_MUTED}">А. Смирнова</text>

        <rect x="0" y="134" width="660" height="34" fill="#F4F5F8"/>
        <text x="20" y="156" font-size="12" font-weight="bold" fill="{TEXT_MAIN}">СПбПУ</text>
        <text x="240" y="156" font-size="12" fill="{TEXT_MAIN}">DevOps инженерия</text>
        <text x="440" y="156" font-size="11" fill="#0284C7">3. Встреча</text>
        <text x="580" y="156" font-size="11" fill="{TEXT_MUTED}">А. Смирнова</text>

        <rect x="0" y="168" width="660" height="34" fill="#FFFFFF"/>
        <text x="20" y="190" font-size="12" font-weight="bold" fill="{TEXT_MAIN}">МФТИ</text>
        <text x="240" y="190" font-size="12" fill="{TEXT_MAIN}">Искусственный интеллект</text>
        <text x="440" y="190" font-size="11" fill="#EA580C">2. Потребность</text>
        <text x="580" y="190" font-size="11" fill="{TEXT_MUTED}">А. Смирнова</text>
      </g>
    </g>
  </g>
"""
    return wrap_svg(content)

# Generator 10: Admin Overview & Telemetry
def gen_screen_10_admin_overview_telemetry() -> str:
    chrome = get_window_chrome("https://crm.school.rt.ru/overview", "Консоль администратора — ИТ Школа Ростелеком")
    shell = get_sidebar_and_topbar("overview", ["Партнёры", "Системное управление (Admin)"], "Администратор платформы", "Администратор системы")
    content = f"""
  {chrome}
  {shell}
  <g transform="translate(270, 150)">
    <text x="0" y="20" font-size="11" font-weight="bold" fill="#98A2B3" letter-spacing="1">СИСТЕМНОЕ УПРАВЛЕНИЕ CRM · 29 СЕНТЯБРЯ 2026</text>
    <text x="0" y="50" font-size="24" font-weight="bold" fill="{TEXT_MAIN}">Панель системного управления и телеметрия</text>
    <text x="0" y="72" font-size="13" fill="{TEXT_MUTED}">Телеметрия платформы, управление каталогами и интеграционными потоками.</text>

    <!-- 152-FZ Isolation Banner -->
    <g transform="translate(0, 95)">
      <rect x="0" y="0" width="1140" height="54" rx="8" fill="#F8F9FC" stroke="{PRIMARY}" stroke-width="1.5"/>
      <circle cx="28" cy="27" r="14" fill="{PRIMARY_SUBTLE}"/>
      <text x="28" y="32" font-size="13" font-weight="bold" fill="{PRIMARY}" text-anchor="middle">🛡</text>
      <text x="54" y="24" font-size="13" font-weight="bold" fill="{TEXT_MAIN}">
        Инвариант 152-ФЗ и ФСТЭК №117: Изоляция коммерческих воронок
      </text>
      <text x="54" y="42" font-size="11" fill="{TEXT_MUTED}">
        Режим администратора: прямой доступ к клиентским воронкам менеджеров изолирован. Управление через справочники и интеграции.
      </text>
    </g>

    <!-- 6 Telemetry Cards -->
    <g transform="translate(0, 165)">
      <rect x="0" y="0" width="176" height="85" rx="8" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1" filter="url(#shadow)"/>
      <text x="14" y="24" font-size="11" fill="{TEXT_MUTED}">Пользователей</text>
      <text x="14" y="56" font-size="26" font-weight="bold" fill="{PRIMARY}">14</text>
      <text x="14" y="74" font-size="9" fill="#98A2B3">Учётные записи</text>

      <rect x="192" y="0" width="176" height="85" rx="8" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1" filter="url(#shadow)"/>
      <text x="14" y="24" font-size="11" fill="{TEXT_MUTED}">Вузов в каталоге</text>
      <text x="14" y="56" font-size="26" font-weight="bold" fill="#0284C7">48</text>
      <text x="14" y="74" font-size="9" fill="#98A2B3">Образоват. орг.</text>

      <rect x="384" y="0" width="176" height="85" rx="8" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1" filter="url(#shadow)"/>
      <text x="14" y="24" font-size="11" fill="{TEXT_MUTED}">ИТ-продуктов</text>
      <text x="14" y="56" font-size="26" font-weight="bold" fill="#16A34A">12</text>
      <text x="14" y="74" font-size="9" fill="#98A2B3">Отечеств. ПО</text>

      <rect x="576" y="0" width="176" height="85" rx="8" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1" filter="url(#shadow)"/>
      <text x="14" y="24" font-size="11" fill="{TEXT_MUTED}">Буфер сверки</text>
      <text x="14" y="56" font-size="26" font-weight="bold" fill="{ACCENT}">3</text>
      <text x="14" y="74" font-size="9" fill="#98A2B3">Входящие заявки</text>

      <rect x="768" y="0" width="176" height="85" rx="8" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1" filter="url(#shadow)"/>
      <text x="14" y="24" font-size="11" fill="{TEXT_MUTED}">ИТ-программ</text>
      <text x="14" y="56" font-size="26" font-weight="bold" fill="#9333EA">6</text>
      <text x="14" y="74" font-size="9" fill="#98A2B3">Направления</text>

      <rect x="960" y="0" width="180" height="85" rx="8" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1" filter="url(#shadow)"/>
      <text x="14" y="24" font-size="11" fill="{TEXT_MUTED}">Контур LMS Zion</text>
      <text x="14" y="56" font-size="20" font-weight="bold" fill="#16A34A">В норме</text>
      <text x="14" y="74" font-size="9" fill="#98A2B3">Синхронизация OK</text>
    </g>

    <!-- Platform Contours & Quick Actions -->
    <g transform="translate(0, 270)">
      <!-- Left: Quick Actions -->
      <rect x="0" y="0" width="550" height="230" rx="10" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1" filter="url(#shadow)"/>
      <text x="24" y="32" font-size="15" font-weight="bold" fill="{TEXT_MAIN}">Инструменты конфигурации платформы</text>

      <rect x="24" y="50" width="502" height="38" rx="6" fill="#F8F9FC" stroke="{BORDER}" stroke-width="1"/>
      <text x="40" y="74" font-size="13" font-weight="bold" fill="{PRIMARY}">Импорт каталогов (XLSX / CSV)</text>
      <text x="490" y="74" font-size="12" fill="{PRIMARY}">→</text>

      <rect x="24" y="96" width="502" height="38" rx="6" fill="#F8F9FC" stroke="{BORDER}" stroke-width="1"/>
      <text x="40" y="120" font-size="13" font-weight="bold" fill="{PRIMARY}">Шлюз интеграций (LMS Zion &amp; Сайт)</text>
      <text x="490" y="120" font-size="12" fill="{PRIMARY}">→</text>

      <rect x="24" y="142" width="502" height="38" rx="6" fill="#F8F9FC" stroke="{BORDER}" stroke-width="1"/>
      <text x="40" y="166" font-size="13" font-weight="bold" fill="{PRIMARY}">Мигратор процессов (Workflow v1 → v2)</text>
      <text x="490" y="166" font-size="12" fill="{PRIMARY}">→</text>

      <rect x="24" y="188" width="502" height="34" rx="6" fill="#F8F9FC" stroke="{BORDER}" stroke-width="1"/>
      <text x="40" y="210" font-size="13" font-weight="bold" fill="{PRIMARY}">База знаний и регламенты 152-ФЗ</text>
      <text x="490" y="210" font-size="12" fill="{PRIMARY}">→</text>

      <!-- Right: Contours Status -->
      <rect x="580" y="0" width="560" height="230" rx="10" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1" filter="url(#shadow)"/>
      <text x="604" y="32" font-size="15" font-weight="bold" fill="{TEXT_MAIN}">Статус внешних контуров интеграции</text>

      <!-- Contour 1: LMS Zion -->
      <g transform="translate(604, 50)">
        <rect x="0" y="0" width="512" height="74" rx="8" fill="#F8F9FC" stroke="{BORDER}" stroke-width="1"/>
        <text x="16" y="26" font-size="13" font-weight="bold" fill="{TEXT_MAIN}">LMS Zion (rtkb.zion-lms.ru)</text>
        <rect x="360" y="12" width="136" height="22" rx="11" fill="#DCFCE7"/>
        <text x="428" y="27" font-size="10" font-weight="bold" fill="#16A34A" text-anchor="middle">● Подключен · 200 OK</text>
        <text x="16" y="48" font-size="11" fill="{TEXT_MUTED}">Адаптер учебных потоков: 48 когорт, 1 240 слушателей</text>
        <text x="16" y="64" font-size="10" fill="#98A2B3">Последняя сверка: 29.09.2026, 17:45</text>
      </g>

      <!-- Contour 2: Web portal -->
      <g transform="translate(604, 136)">
        <rect x="0" y="0" width="512" height="74" rx="8" fill="#F8F9FC" stroke="{BORDER}" stroke-width="1"/>
        <text x="16" y="26" font-size="13" font-weight="bold" fill="{TEXT_MAIN}">Сайт ИТ Школы (Laravel Gateway)</text>
        <rect x="360" y="12" width="136" height="22" rx="11" fill="#DCFCE7"/>
        <text x="428" y="27" font-size="10" font-weight="bold" fill="#16A34A" text-anchor="middle">● Подключен · 200 OK</text>
        <text x="16" y="48" font-size="11" fill="{TEXT_MUTED}">Прием входящих заявок абитуриентов и вузов: 3 в очереди</text>
        <text x="16" y="64" font-size="10" fill="#98A2B3">Сверка: активный вебхук</text>
      </g>
    </g>
  </g>
"""
    return wrap_svg(content)

# Generator 11: Catalog Import Wizard Modal
def gen_screen_11_catalog_import_wizard() -> str:
    chrome = get_window_chrome("https://crm.school.rt.ru/catalogs", "Импорт каталогов — ИТ Школа Ростелеком")
    shell = get_sidebar_and_topbar("catalogs", ["Партнёры", "Импорт каталогов"], "Администратор платформы", "Администратор системы")
    content = f"""
  {chrome}
  {shell}
  <!-- Dimmed Modal Backdrop -->
  <rect x="0" y="42" width="1440" height="858" fill="rgba(16, 24, 40, 0.65)"/>

  <!-- Centered Modal Dialog -->
  <g transform="translate(320, 110)" filter="url(#modal-shadow)">
    <rect x="0" y="0" width="800" height="680" rx="14" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1"/>

    <!-- Header -->
    <rect x="0" y="0" width="800" height="64" rx="14" fill="#FFFFFF"/>
    <text x="28" y="40" font-size="18" font-weight="bold" fill="{TEXT_MAIN}">Мастер двухфазного импорта справочников (XLSX / CSV)</text>
    <text x="765" y="38" font-size="18" fill="{TEXT_MUTED}" text-anchor="middle">✕</text>
    <line x1="0" y1="64" x2="800" y2="64" stroke="{BORDER}" stroke-width="1"/>

    <!-- 3-Step Stepper -->
    <g transform="translate(28, 80)">
      <!-- Step 1 (Done) -->
      <circle cx="20" cy="18" r="14" fill="#DCFCE7"/>
      <text x="20" y="23" font-size="12" font-weight="bold" fill="#16A34A" text-anchor="middle">✓</text>
      <text x="42" y="16" font-size="12" font-weight="bold" fill="{TEXT_MAIN}">Шаг 1: Файл</text>
      <text x="42" y="30" font-size="10" fill="{TEXT_MUTED}">Загружен partners.xlsx</text>

      <line x1="170" y1="18" x2="230" y2="18" stroke="{PRIMARY}" stroke-width="2"/>

      <!-- Step 2 (Active) -->
      <circle cx="250" cy="18" r="14" fill="{PRIMARY}"/>
      <text x="250" y="23" font-size="12" font-weight="bold" fill="#FFFFFF" text-anchor="middle">2</text>
      <text x="272" y="16" font-size="12" font-weight="bold" fill="{PRIMARY}">Шаг 2: Валидация (Preview)</text>
      <text x="272" y="30" font-size="10" fill="{PRIMARY}">Сухой прогон данных</text>

      <line x1="420" y1="18" x2="480" y2="18" stroke="{BORDER}" stroke-width="2"/>

      <!-- Step 3 (Pending) -->
      <circle cx="500" cy="18" r="14" fill="#F4F5F8"/>
      <text x="500" y="23" font-size="12" font-weight="bold" fill="#98A2B3" text-anchor="middle">3</text>
      <text x="522" y="16" font-size="12" font-weight="bold" fill="#98A2B3">Шаг 3: Коммит</text>
      <text x="522" y="30" font-size="10" fill="#98A2B3">Транзакция в БД</text>
    </g>

    <!-- Validation Summary Cards -->
    <g transform="translate(28, 145)">
      <rect x="0" y="0" width="235" height="60" rx="8" fill="#F8F9FC" stroke="{BORDER}" stroke-width="1"/>
      <text x="16" y="25" font-size="11" fill="{TEXT_MUTED}">Всего строк в таблице</text>
      <text x="16" y="48" font-size="22" font-weight="bold" fill="{TEXT_MAIN}">25</text>

      <rect x="255" y="0" width="235" height="60" rx="8" fill="#ECFDF3" stroke="{SUCCESS_BORDER}" stroke-width="1"/>
      <text x="16" y="25" font-size="11" fill="{SUCCESS_TEXT}">Готовы к импорту (валидны)</text>
      <text x="16" y="48" font-size="22" font-weight="bold" fill="{SUCCESS_TEXT}">23 строки</text>

      <rect x="510" y="0" width="234" height="60" rx="8" fill="#FEF3F2" stroke="{ERROR_BORDER}" stroke-width="1"/>
      <text x="16" y="25" font-size="11" fill="{ERROR_TEXT}">Предупреждений / коллизий</text>
      <text x="16" y="48" font-size="22" font-weight="bold" fill="{ERROR_TEXT}">2 строки</text>
    </g>

    <!-- Preview Table -->
    <g transform="translate(28, 225)">
      <text x="0" y="16" font-size="13" font-weight="bold" fill="{TEXT_MAIN}">Предварительный просмотр данных (Dry-Run Preview):</text>

      <rect x="0" y="28" width="744" height="28" fill="#F8F9FC"/>
      <text x="14" y="46" font-size="10" font-weight="bold" fill="#98A2B3">ВУЗ / НАИМЕНОВАНИЕ</text>
      <text x="230" y="46" font-size="10" font-weight="bold" fill="#98A2B3">КОНТАКТНОЕ ЛИЦО</text>
      <text x="430" y="46" font-size="10" font-weight="bold" fill="#98A2B3">НАПРАВЛЕНИЕ</text>
      <text x="610" y="46" font-size="10" font-weight="bold" fill="#98A2B3">РЕЗУЛЬТАТ</text>

      <!-- Row 1 -->
      <line x1="0" y1="56" x2="744" y2="56" stroke="{BORDER}" stroke-width="1"/>
      <text x="14" y="74" font-size="11" font-weight="bold" fill="{TEXT_MAIN}">МГТУ им. Н.Э. Баумана</text>
      <text x="230" y="74" font-size="11" fill="{TEXT_MUTED}">Смирнов А.П. (devops@bmstu.ru)</text>
      <text x="430" y="74" font-size="11" fill="{TEXT_MAIN}">DevOps инженерия</text>
      <rect x="610" y="62" width="110" height="20" rx="10" fill="#DCFCE7"/>
      <text x="665" y="76" font-size="10" font-weight="bold" fill="#16A34A" text-anchor="middle">✓ Валидно</text>

      <!-- Row 2 -->
      <line x1="0" y1="90" x2="744" y2="90" stroke="{BORDER}" stroke-width="1"/>
      <text x="14" y="108" font-size="11" font-weight="bold" fill="{TEXT_MAIN}">НИУ ВШЭ</text>
      <text x="230" y="108" font-size="11" fill="{TEXT_MUTED}">Иванов К.С. (hse@edu.ru)</text>
      <text x="430" y="108" font-size="11" fill="{TEXT_MAIN}">Web-разработка</text>
      <rect x="610" y="96" width="110" height="20" rx="10" fill="#DCFCE7"/>
      <text x="665" y="110" font-size="10" font-weight="bold" fill="#16A34A" text-anchor="middle">✓ Валидно</text>

      <!-- Row 3 -->
      <line x1="0" y1="124" x2="744" y2="124" stroke="{BORDER}" stroke-width="1"/>
      <text x="14" y="142" font-size="11" font-weight="bold" fill="{TEXT_MAIN}">НИЯУ МИФИ</text>
      <text x="230" y="142" font-size="11" fill="{TEXT_MUTED}">Соколов В.Д. (mephi@mephi.ru)</text>
      <text x="430" y="142" font-size="11" fill="{TEXT_MAIN}">Информационная безоп.</text>
      <rect x="610" y="130" width="110" height="20" rx="10" fill="#DCFCE7"/>
      <text x="665" y="144" font-size="10" font-weight="bold" fill="#16A34A" text-anchor="middle">✓ Валидно</text>

      <!-- Row 4 (Warning) -->
      <line x1="0" y1="158" x2="744" y2="158" stroke="{BORDER}" stroke-width="1"/>
      <text x="14" y="176" font-size="11" font-weight="bold" fill="{TEXT_MAIN}">Лицей № 1580 (дубликат)</text>
      <text x="230" y="176" font-size="11" fill="{TEXT_MUTED}">Петрова М.И. (-)</text>
      <text x="430" y="176" font-size="11" fill="{TEXT_MUTED}">Не указано</text>
      <rect x="610" y="164" width="110" height="20" rx="10" fill="#FEF3C7"/>
      <text x="665" y="178" font-size="10" font-weight="bold" fill="#B45309" text-anchor="middle">⚠ Дубликат</text>
    </g>

    <!-- Idempotency & Safety Notice -->
    <g transform="translate(28, 480)">
      <rect x="0" y="0" width="744" height="60" rx="8" fill="#F8F9FC" stroke="{BORDER}" stroke-width="1"/>
      <text x="16" y="24" font-size="12" font-weight="bold" fill="{TEXT_MAIN}">Транзакционная фиксация с защитой по Idempotency-Key:</text>
      <text x="16" y="44" font-size="11" fill="{TEXT_MUTED}">
        Ключ идемпотентности: <tspan font-family="monospace" fill="{PRIMARY}">imp-20260929-a41f9</tspan> · Ошибочные строки будут пропущены.
      </text>
    </g>

    <!-- Modal Footer -->
    <line x1="0" y1="610" x2="800" y2="610" stroke="{BORDER}" stroke-width="1"/>
    <rect x="470" y="625" width="100" height="38" rx="6" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1"/>
    <text x="520" y="649" font-size="13" fill="{TEXT_MAIN}" text-anchor="middle">Отмена</text>

    <rect x="585" y="625" width="185" height="38" rx="6" fill="{PRIMARY}"/>
    <text x="677" y="649" font-size="13" font-weight="bold" fill="#FFFFFF" text-anchor="middle">
      Применить импорт (23) →
    </text>
  </g>
"""
    return wrap_svg(content)

# Generator 12: Workflow Migrator Modal
def gen_screen_12_workflow_migrator() -> str:
    chrome = get_window_chrome("https://crm.school.rt.ru/catalogs", "Мигратор процессов — ИТ Школа Ростелеком")
    shell = get_sidebar_and_topbar("catalogs", ["Партнёры", "Мигратор процессов"], "Администратор платформы", "Администратор системы")
    content = f"""
  {chrome}
  {shell}
  <!-- Dimmed Modal Backdrop -->
  <rect x="0" y="42" width="1440" height="858" fill="rgba(16, 24, 40, 0.65)"/>

  <!-- Centered Modal Dialog -->
  <g transform="translate(345, 120)" filter="url(#modal-shadow)">
    <rect x="0" y="0" width="750" height="660" rx="14" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1"/>

    <!-- Header -->
    <rect x="0" y="0" width="750" height="64" rx="14" fill="#FFFFFF"/>
    <text x="28" y="40" font-size="18" font-weight="bold" fill="{TEXT_MAIN}">Мигратор версий жизненного цикла (Workflow v1 → v2)</text>
    <text x="715" y="38" font-size="18" fill="{TEXT_MUTED}" text-anchor="middle">✕</text>
    <line x1="0" y1="64" x2="750" y2="64" stroke="{BORDER}" stroke-width="1"/>

    <!-- Info Banner -->
    <g transform="translate(28, 80)">
      <rect x="0" y="0" width="694" height="60" rx="8" fill="#F8F9FC" stroke="{BORDER}" stroke-width="1"/>
      <text x="16" y="24" font-size="12" font-weight="bold" fill="{TEXT_MAIN}">Матрица сопоставления статусов процесса:</text>
      <text x="16" y="44" font-size="11" fill="{TEXT_MUTED}">
        Миграция переведет все активные карточки с версии 1 на версию 2. Терминальные статусы неизменны.
      </text>
    </g>

    <!-- Mapping Table -->
    <g transform="translate(28, 155)">
      <rect x="0" y="0" width="694" height="28" fill="#F8F9FC"/>
      <text x="14" y="18" font-size="10" font-weight="bold" fill="#98A2B3">СТАТУС ВЕРСИИ 1 (ТЕКУЩИЙ)</text>
      <text x="280" y="18" font-size="10" font-weight="bold" fill="#98A2B3">ЦЕЛЕВОЙ СТАТУС ВЕРСИИ 2</text>
      <text x="560" y="18" font-size="10" font-weight="bold" fill="#98A2B3">КАРТОЧЕК В БАЗЕ</text>

      <!-- Mapping Rows -->
      <line x1="0" y1="28" x2="694" y2="28" stroke="{BORDER}" stroke-width="1"/>
      <text x="14" y="48" font-size="12" font-weight="bold" fill="{TEXT_MAIN}">1. Поиск контактов</text>
      <text x="240" y="48" font-size="12" fill="{PRIMARY}">→</text>
      <text x="280" y="48" font-size="12" font-weight="bold" fill="{PRIMARY}">1. Поиск контактов</text>
      <text x="560" y="48" font-size="12" fill="{TEXT_MAIN}">1 карточка</text>

      <line x1="0" y1="62" x2="694" y2="62" stroke="{BORDER}" stroke-width="1"/>
      <text x="14" y="82" font-size="12" font-weight="bold" fill="{TEXT_MAIN}">2. Уточнение потребности</text>
      <text x="240" y="82" font-size="12" fill="{PRIMARY}">→</text>
      <text x="280" y="82" font-size="12" font-weight="bold" fill="{PRIMARY}">2. Уточнение потребности</text>
      <text x="560" y="82" font-size="12" fill="{TEXT_MAIN}">2 карточки</text>

      <line x1="0" y1="96" x2="694" y2="96" stroke="{BORDER}" stroke-width="1"/>
      <text x="14" y="116" font-size="12" font-weight="bold" fill="{TEXT_MAIN}">4. Обмен документами</text>
      <text x="240" y="116" font-size="12" fill="{PRIMARY}">→</text>
      <text x="280" y="116" font-size="12" font-weight="bold" fill="{PRIMARY}">4. Обмен документами</text>
      <text x="560" y="116" font-size="12" fill="{TEXT_MAIN}">2 карточки</text>

      <line x1="0" y1="130" x2="694" y2="130" stroke="{BORDER}" stroke-width="1"/>
      <text x="14" y="150" font-size="12" font-weight="bold" fill="{TEXT_MAIN}">5. Корректировка док.</text>
      <text x="240" y="150" font-size="12" fill="{PRIMARY}">→</text>
      <text x="280" y="150" font-size="12" font-weight="bold" fill="{PRIMARY}">6. Подписание документов</text>
      <text x="560" y="150" font-size="12" fill="{TEXT_MAIN}">1 карточка</text>

      <line x1="0" y1="164" x2="694" y2="164" stroke="{BORDER}" stroke-width="1"/>
      <text x="14" y="184" font-size="12" font-weight="bold" fill="{TEXT_MAIN}">7. Передача материалов</text>
      <text x="240" y="184" font-size="12" fill="{PRIMARY}">→</text>
      <text x="280" y="184" font-size="12" font-weight="bold" fill="{PRIMARY}">7. Передача материалов</text>
      <text x="560" y="184" font-size="12" fill="{TEXT_MAIN}">3 карточки</text>
    </g>

    <!-- Stats & Collision Guard -->
    <g transform="translate(28, 380)">
      <rect x="0" y="0" width="694" height="85" rx="8" fill="#ECFDF3" stroke="{SUCCESS_BORDER}" stroke-width="1"/>
      <circle cx="28" cy="28" r="14" fill="#DCFCE7"/>
      <text x="28" y="33" font-size="13" font-weight="bold" fill="#16A34A" text-anchor="middle">✓</text>
      <text x="54" y="24" font-size="13" font-weight="bold" fill="{SUCCESS_TEXT}">
        Проверка завершена: Коллизий маппинга не обнаружено
      </text>
      <text x="54" y="44" font-size="11" fill="#065F46">
        Всего затронуто 9 активных карточек. Терминальные статусы (Завершено, Отменено) изолированы.
      </text>
      <text x="54" y="60" font-size="10" fill="#047857">
        Каждая карточка получит аудиторское событие workflow_migrated с инкрементом CAS-ревизии.
      </text>
    </g>

    <!-- Security CAS note -->
    <g transform="translate(28, 485)">
      <text x="0" y="16" font-size="11" fill="{TEXT_MUTED}">
        Операция выполняется атомарно в единой транзакции с заголовком <tspan font-weight="bold">Idempotency-Key</tspan>.
      </text>
    </g>

    <!-- Modal Footer -->
    <line x1="0" y1="590" x2="750" y2="590" stroke="{BORDER}" stroke-width="1"/>
    <rect x="420" y="606" width="100" height="38" rx="6" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1"/>
    <text x="470" y="630" font-size="13" fill="{TEXT_MAIN}" text-anchor="middle">Отмена</text>

    <rect x="535" y="606" width="185" height="38" rx="6" fill="{PRIMARY}"/>
    <text x="627" y="630" font-size="13" font-weight="bold" fill="#FFFFFF" text-anchor="middle">
      Применить миграцию (9) →
    </text>
  </g>
"""
    return wrap_svg(content)

# Generator 13: Error Diagnostic Center & AC21 Simulator
def gen_screen_13_error_diagnostic_center() -> str:
    chrome = get_window_chrome("https://crm.school.rt.ru/help", "База знаний и диагностика ошибок — ИТ Школа Ростелеком")
    shell = get_sidebar_and_topbar("help", ["Партнёры", "База знаний и диагностика ошибок"])
    content = f"""
  {chrome}
  {shell}
  <g transform="translate(270, 150)">
    <text x="0" y="20" font-size="11" font-weight="bold" fill="#98A2B3" letter-spacing="1">ДИАГНОСТИЧЕСКИЙ ЦЕНТР И РЕГЛАМЕНТЫ CRM</text>
    <text x="0" y="50" font-size="24" font-weight="bold" fill="{TEXT_MAIN}">Справочник ошибок и симулятор сохранения ввода (AC21)</text>
    <text x="0" y="72" font-size="13" fill="{TEXT_MUTED}">Канонические ответы API, рекомендации по устранению и гарантия сохранения данных при сбоях.</text>

    <!-- Open Accordion Item: 409 Conflict -->
    <g transform="translate(0, 95)">
      <rect x="0" y="0" width="1140" height="210" rx="10" fill="#FFFFFF" stroke="{PRIMARY}" stroke-width="1.5" filter="url(#shadow)"/>
      <rect x="0" y="0" width="1140" height="48" rx="10" fill="{PRIMARY_SUBTLE}"/>
      <rect x="20" y="12" width="105" height="24" rx="4" fill="{PRIMARY}"/>
      <text x="72" y="28" font-size="11" font-weight="bold" fill="#FFFFFF" text-anchor="middle">409 Conflict</text>
      <text x="140" y="29" font-size="14" font-weight="bold" fill="{TEXT_MAIN}">REVISION_CONFLICT / Оптимистический CAS Mismatch</text>
      <text x="1110" y="29" font-size="14" fill="{PRIMARY}">▲</text>

      <!-- Accordion Content -->
      <g transform="translate(24, 65)">
        <text x="0" y="16" font-size="11" font-weight="bold" fill="#98A2B3">СИМПТОМ И ПЕРВОПРИЧИНА</text>
        <text x="0" y="38" font-size="13" fill="{TEXT_MAIN}">
          Конфликт параллельного редактирования: переданная версия expected_revision устарела.
        </text>
        <text x="0" y="56" font-size="13" fill="{TEXT_MAIN}">
          Другой менеджер или руководитель уже зафиксировал изменение карточки.
        </text>

        <text x="560" y="16" font-size="11" font-weight="bold" fill="#98A2B3">ЧТО ДЕЛАТЬ ПОЛЬЗОВАТЕЛЮ</text>
        <text x="560" y="38" font-size="13" fill="{TEXT_MAIN}">
          Введенный вами текст сохранен в форме и НЕ СБРАСЫВАЕТСЯ (инвариант AC21)!
        </text>
        <text x="560" y="56" font-size="13" fill="{TEXT_MAIN}">
          Ознакомьтесь с актуальной версией карточки и повторите сохранение.
        </text>

        <rect x="0" y="85" width="1092" height="44" rx="6" fill="#F8F9FC" stroke="{BORDER}" stroke-width="1"/>
        <text x="16" y="112" font-size="11" fill="{TEXT_MUTED}">
          🛡 Инвариант безопасности: Оптимистическая CAS-блокировка исключает потерю чужих правок (Lost Update).
        </text>
      </g>
    </g>

    <!-- Interactive AC21 Form Input Preservation Demo Panel -->
    <g transform="translate(0, 325)">
      <rect x="0" y="0" width="1140" height="375" rx="10" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1" filter="url(#shadow)"/>
      <text x="24" y="32" font-size="16" font-weight="bold" fill="{TEXT_MAIN}">
        Интерактивная проверка сохранения ввода без сброса формы (AC21)
      </text>
      <rect x="940" y="16" width="176" height="26" rx="13" fill="#DCFCE7"/>
      <text x="1028" y="33" font-size="11" font-weight="bold" fill="#16A34A" text-anchor="middle">✓ Интерактивный тест AC21</text>

      <!-- Simulated Form with preserved values -->
      <g transform="translate(24, 55)">
        <text x="0" y="16" font-size="12" font-weight="bold" fill="{TEXT_MAIN}">Название / Заголовок взаимодействия:</text>
        <rect x="0" y="26" width="520" height="36" rx="6" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1"/>
        <text x="14" y="49" font-size="13" fill="{TEXT_MAIN}">Взаимодействие с МГТУ по программе «Сетевые технологии»</text>

        <text x="0" y="82" font-size="12" font-weight="bold" fill="{TEXT_MAIN}">Обоснование / Комментарий куратора:</text>
        <rect x="0" y="92" width="520" height="54" rx="6" fill="#FFFFFF" stroke="{BORDER}" stroke-width="1"/>
        <text x="14" y="114" font-size="13" fill="{TEXT_MAIN}">Направлен запрос на корректировку договора перед подписанием.</text>

        <rect x="0" y="160" width="280" height="36" rx="6" fill="{PRIMARY}"/>
        <text x="140" y="183" font-size="12" font-weight="bold" fill="#FFFFFF" text-anchor="middle">
          ⚡ Симулировать ошибку и проверить сохранение
        </text>

        <!-- Right Side: Canonical Envelope & Success Indicator -->
        <g transform="translate(560, 0)">
          <!-- Error alert -->
          <rect x="0" y="0" width="532" height="48" rx="8" fill="#FEF3F2" stroke="{ERROR_BORDER}" stroke-width="1"/>
          <text x="16" y="22" font-size="12" font-weight="bold" fill="{ERROR_TEXT}">HTTP 409 Conflict: REVISION_CONFLICT</text>
          <text x="16" y="38" font-size="11" fill="#7A271A">Сервер отклонил операцию. Пользовательские поля не сброшены.</text>

          <!-- Canonical Envelope JSON Preview -->
          <rect x="0" y="58" width="532" height="120" rx="8" fill="#1E1B2E"/>
          <text x="16" y="78" font-size="10" font-family="monospace" fill="#A5F3FC">
            &#123;
          </text>
          <text x="32" y="96" font-size="10" font-family="monospace" fill="#F472B6">
            &quot;error&quot;: &#123;
          </text>
          <text x="48" y="114" font-size="10" font-family="monospace" fill="#FDE047">
            &quot;code&quot;: &quot;REVISION_CONFLICT&quot;, &quot;request_id&quot;: &quot;req-demo-409-cas&quot;,
          </text>
          <text x="48" y="132" font-size="10" font-family="monospace" fill="#FDE047">
            &quot;message&quot;: &quot;Interaction revision mismatch: expected 3, current 4&quot;
          </text>
          <text x="32" y="150" font-size="10" font-family="monospace" fill="#F472B6">
            &#125;
          </text>
          <text x="16" y="168" font-size="10" font-family="monospace" fill="#A5F3FC">
            &#125;
          </text>

          <!-- AC21 Success alert -->
          <rect x="0" y="190" width="532" height="60" rx="8" fill="#ECFDF3" stroke="{SUCCESS_BORDER}" stroke-width="1"/>
          <circle cx="24" cy="220" r="12" fill="#DCFCE7"/>
          <text x="24" y="225" font-size="12" font-weight="bold" fill="#16A34A" text-anchor="middle">✓</text>
          <text x="46" y="212" font-size="12" font-weight="bold" fill="{SUCCESS_TEXT}">AC21 соблюден: Введенный текст сохранен в форме!</text>
          <text x="46" y="232" font-size="11" fill="#065F46">
            Значения «Взаимодействие с МГТУ...» и комментарий остались в полях ввода.
          </text>
        </g>
      </g>
    </g>
  </g>
"""
    return wrap_svg(content)

# All 13 screens mapping
SCREENS = [
    ("screen-01-login.png", gen_screen_01_login, "Экран авторизации и выбор демонстрационных ролей"),
    ("screen-02-manager-overview.png", gen_screen_02_manager_overview, "Рабочий стол менеджера (Воронка 15 этапов и KPI)"),
    ("screen-03-interactions-registry.png", gen_screen_03_interactions_registry, "Реестр взаимодействий с фильтрами и поиском"),
    ("screen-04-interaction-card-graph.png", gen_screen_04_interaction_card_graph, "Карточка взаимодействия с графом жизненного цикла"),
    ("screen-05-interaction-d02-prevent.png", gen_screen_05_interaction_d02_prevent, "Редактирование параметров и предотвращение дедлока D02"),
    ("screen-06-interaction-transition-rework.png", gen_screen_06_interaction_transition_rework, "Модальное окно перехода с обязательным обоснованием"),
    ("screen-07-attachments-and-audit.png", gen_screen_07_attachments_and_audit, "Блок загрузки файлов (25 МБ, 10 форматов) и Audit Trail"),
    ("screen-08-supervisor-overview-reassign.png", gen_screen_08_supervisor_overview_reassign, "Консоль руководителя и переназначение куратора (Reassign)"),
    ("screen-09-reports-analytics-export.png", gen_screen_09_reports_analytics_export, "Аналитический модуль отчётов (3 среза, экспорт XLSX/PDF)"),
    ("screen-10-admin-overview-telemetry.png", gen_screen_10_admin_overview_telemetry, "Панель администратора (Телеметрия LMS/Сайта и каталоги)"),
    ("screen-11-catalog-import-wizard.png", gen_screen_11_catalog_import_wizard, "Мастер двухфазного импорта каталогов (XLSX / CSV)"),
    ("screen-12-workflow-migrator.png", gen_screen_12_workflow_migrator, "Мигратор версий процессов (v1 -> v2)"),
    ("screen-13-error-diagnostic-center.png", gen_screen_13_error_diagnostic_center, "Справочник кодов ошибок и симулятор сохранения ввода AC21"),
]

def main():
    print(f"=== Generating 13 HiDPI (1440x900) Screenshots ===")
    for d in OUTPUT_DIRS:
        d.mkdir(parents=True, exist_ok=True)
        print(f"Ensured target directory: {d}")

    total_generated = 0
    for idx, (filename, generator_fn, title) in enumerate(SCREENS, 1):
        print(f"[{idx:02d}/13] Rendering {filename} ({title})...", end="", flush=True)
        svg_code = generator_fn()
        png_data = render_svg_to_png(svg_code, 1440, 900)

        # Validate PNG bytes
        assert png_data[:8] == b"\x89PNG\r\n\x1a\n", f"Invalid PNG signature for {filename}"
        w, h = struct.unpack(">II", png_data[16:24])
        assert (w, h) == (1440, 900), f"Invalid dimensions {w}x{h} for {filename}"
        assert len(png_data) > 20000, f"File size too small ({len(png_data)} bytes) for {filename}"

        # Write to both target directories
        for target_dir in OUTPUT_DIRS:
            dest = target_dir / filename
            dest.write_bytes(png_data)

        print(f" OK ({len(png_data):,} bytes)")
        total_generated += 1

    print(f"\nSuccessfully generated {total_generated} screenshots ({total_generated * len(OUTPUT_DIRS)} files total) across {len(OUTPUT_DIRS)} directories.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
