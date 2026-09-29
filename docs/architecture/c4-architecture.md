# Архитектурная документация C4: ИТ Школа Ростелекома — CRM (rost_crm)

**Проект:** «ИТ Школа Ростелекома — CRM» (`rost_crm`)  
**Версия документа:** 1.0 (задачи B36, R26, AC26)  
**Дата:** 2026-09-20  
**Автор:** Ведущий архитектор решений и информационной безопасности команды проекта («Ezdel»)

---

## 1. Введение и методология C4

Настоящий документ описывает архитектуру системы «ИТ Школа Ростелекома — CRM» (`rost_crm`) с использованием методологии **C4 (Context, Containers, Components, Code)**, разработанной Саймоном Брауном (Simon Brown). 

Архитектурная модель представлена на трех уровнях детализации с использованием формальных диаграмм Mermaid:
- **Уровень 1 (System Context):** Место системы во внешнем окружении, взаимодействие с пользователями и смежными корпоративными платформами.
- **Уровень 2 (Containers):** Высокоуровневая структура приложений, хранилищ данных и протоколы межконтейнерного взаимодействия.
- **Уровень 3 (Components):** Декомпозиция ядра бэкенда на взаимодействующие функциональные компоненты и сервисы.

Дополнительно приведены матрица ответственности компонентов, спецификация межсистемных интерфейсов и карта контуров безопасности (Trust Boundaries).

---

## 2. C4 Уровень 1: Системный контекст (System Context)

Диаграмма контекста демонстрирует систему `rost_crm` как единый «черный ящик», определяя ключевых пользователей и внешние интеграционные зависимости в контуре ПАО «Ростелеком».

```mermaid
C4Context
    title C4 Level 1: Системный контекст CRM «ИТ Школа Ростелекома — Партнёры»

    Person(manager, "Менеджер партнерств", "Сотрудник ПАО «Ростелеком». Ведет карточки взаимодействия, загружает документы, курирует этапы воронки")
    Person(supervisor, "Руководитель направления", "Руководитель территориального блока. Контролирует воронку команды, переназначает ответственных, анализирует отчеты XLSX/PDF")
    Person(admin, "Системный администратор", "Администратор CRM. Управляет пользователями, мигрирует версии процессов, запускает импорт каталогов, сверяет входящие заявки")
    Person_Ext(unirep, "Представитель вуза", "Контактное лицо образовательной организации (ректор, декан, преподаватель). Получает материалы, подписывает договоры")

    Enterprise_Boundary(b0, "Корпоративный контур ПАО «Ростелеком»") {
        System(crm, "ИТ Школа CRM (rost_crm)", "Централизованная система управления взаимодействиями с образовательными организациями, воронкой партнерств, документами и сквозной аналитикой")
        System_Ext(keycloak, "Корпоративный Keycloak (IDP)", "Единая точка федеративной аутентификации (OIDC / OAuth2), генерация RS256 JWT-токенов")
        System_Ext(lms, "LMS Zion (rtkb.zion-lms.ru)", "Внешняя образовательная платформа: активные учебные потоки, зачисленные студенты, метрики посещаемости")
        System_Ext(website, "Внешний сайт (Laravel)", "Публичный веб-портал приема заявок образовательных организаций на вступление в проект «ИТ Школа»")
    }

    Rel(manager, crm, "Ведение воронки, загрузка файлов, редактирование реквизитов", "HTTPS / JSON (REST API)")
    Rel(supervisor, crm, "Мониторинг команды, переназначение, экспорт отчетов", "HTTPS / JSON (REST API)")
    Rel(admin, crm, "Миграция workflow, пакетный импорт, очередь сверки заявок", "HTTPS / JSON (REST API)")
    Rel(unirep, manager, "Предоставление реквизитов, согласование программ", "Внесистемное взаимодействие (Email / Телефон)")

    Rel(crm, keycloak, "Проверка JWT, загрузка публичных ключей JWKS", "HTTPS / OIDC")
    Rel(crm, lms, "Сбор учебных метрик по потокам и студентам вузов", "HTTPS / REST API (DTO v1.0)")
    Rel(crm, website, "Прием пакетов заявок на партнерство", "HTTPS / Webhook (DTO v1.0)")
```

### 2.1. Описание участников и внешних систем
- **Менеджер партнерств (Роль `manager`):** Основной оператор воронки. Ограничен областью видимости своих взаимодействий (`Interaction.owner_id == user.id`).
- **Руководитель направления (Роль `supervisor`):** Куратор команды менеджеров. Обладает правами переназначения карточек и выгрузки сквозной аналитики по подразделению (`team_id`).
- **Системный администратор (Роль `administrator`):** Ответственный за эксплуатацию. Выполняет миграции процессов между версиями графа, пакетный импорт справочников и ручную сверку коллизий входящих заявок.
- **Корпоративный Keycloak (IDP):** Провайдер удостоверений. Поддерживает протокол OpenID Connect (OIDC) с потоком Authorization Code Flow + PKCE S256. В демонстрационном режиме эмулируется встроенным механизмом `demo_users`.
- **LMS Zion (`rtkb.zion-lms.ru`):** Внешняя учебная среда. Источник образовательных метрик (число потоков, зачисленные студенты, завершившие обучение). Подключается через адаптер `MockLMSAdapter` с поддержкой переключения на live-режим.
- **Внешний сайт (Laravel):** Публичный веб-портал. Поставляет входящие заявки от учебных заведений. Подключается через адаптер `MockWebsiteAdapter` с очередью нормализации и разрешения коллизий `Reconciliation Inbox`.

---

## 3. C4 Уровень 2: Контейнеры (Containers)

Контейнерный срез определяет состав развертываемых модулей системы, технологии реализации и протоколы межмодульного взаимодействия.

```mermaid
C4Container
    title C4 Level 2: Контейнерная архитектура CRM «ИТ Школа Ростелекома»

    Person(user, "Пользователь CRM", "Менеджер / Руководитель / Администратор")

    Container_Boundary(crm_boundary, "ИТ Школа Ростелекома — CRM (rost_crm)") {
        Container(spa, "Single-Page Application (SPA)", "React 18, TypeScript, Vite", "Пользовательский веб-интерфейс в дизайн-системе Rostelecom Gen2 Light. In-memory сессии JWT (без localStorage), реактивное обновление состояния без перезагрузки страницы.")
        Container(backend, "Backend API Application", "Python 3.12+, FastAPI, SQLAlchemy, Pydantic", "Ядро бизнес-логики: проверка прав RBAC/Scope, CAS-блокировка ревизий, движок воронки и миграций, аналитический движок XLSX/PDF, шлюз интеграций.")
        ContainerDb(db, "Реляционная база данных", "PostgreSQL 16 / SQLite 3", "Транзакционное хранилище сущностей, неизменяемого аудит-лога InteractionEvent, очереди сверки IntegrationInbox и витрины метрик LearningMetric.")
        Container(storage, "Изолированное файловое хранилище", "POSIX File System / Volume", "Безопасное хранилище вложений 10 форматов ТЗ. Файлы изолированы по каталогам под UUID, доступ исключительно через авторизованный API.")
    }

    System_Ext(keycloak, "Keycloak IDP", "OIDC Сервер аутентификации")
    System_Ext(lms, "LMS Zion", "Внешняя платформа обучения")
    System_Ext(website, "Сайт Laravel", "Внешний портал заявок")

    Rel(user, spa, "Интерактивная работа через браузер", "HTTPS / DOM")
    Rel(spa, keycloak, "Аутентификация PKCE S256, получение токена", "HTTPS / OIDC")
    Rel(spa, backend, "REST API вызовы /api/v1/", "HTTPS / JSON, In-Memory Bearer JWT, Idempotency-Key")
    Rel(backend, keycloak, "Валидация подписи JWT по JWKS", "HTTPS / RS256")
    Rel(backend, db, "Транзакции, CAS-запросы, аудит-лог", "SQLAlchemy ORM / SQL")
    Rel(backend, storage, "Сохранение и потоковая отдача файлов", "POSIX I/O / FileResponse")
    Rel(backend, lms, "Опрос адаптера учебных метрик", "HTTPS / REST API (DTO v1.0)")
    Rel(backend, website, "Прием пакетов заявок вузов", "HTTPS / Webhook (DTO v1.0)")
```

### 3.1. Характеристики контейнеров

| Контейнер | Технологический стек | Основные обязанности | Требования масштабирования и надежности |
|---|---|---|---|
| **Single-Page Application (SPA)** | React 18, TypeScript 5, Vite, CSS Modules | Рендеринг интерфейса в дизайн-системе Gen2 Light (`#7700FF`, `#FF4F12`), хранение JWT-токена в памяти (`useRef`), управление состоянием форм, предотвращение перезагрузки страницы (SPA). | Статический хостинг (Nginx/CDN), кеширование ассетов по хэшам файлов. Отсутствие состояния на сервере. |
| **Backend API Application** | Python 3.12+, FastAPI, Starlette, AnyIO | Обработка REST API `/api/v1/`, ролевая модель RBAC и Scope-изоляция (152-ФЗ), CAS-блокировка версий, генерация XLSX и векторных PDF, валидация файлов и magic bytes. | Горизонтальное масштабирование (Stateless Uvicorn workers). Асинхронный event loop. Benchmark: 50 конкурентных пользователей, $p95 \le 1.0\text{ с}$. |
| **Реляционная база данных** | PostgreSQL 16 (production) / SQLite 3 (dev/test) | Хранение структурированных данных, поддержка транзакционной целостности ACID, составные уникальные индексы дедупликации, хранение аудит-лога `InteractionEvent`. | Read-репликация для аналитических отчетов, регулярный WAL-архив и бэкап. |
| **Изолированное хранилище файлов** | Локальная ФС / Kubernetes PersistentVolume | Физическое хранение загруженных вложений (`storage/attachments/{id}/`). Размещение вне веб-рута Nginx. Изоляция файлов под UUID. | Квотирование дискового пространства, резервное копирование томов, контроль прав доступа на уровне POSIX (`0750`). |

---

## 4. C4 Уровень 3: Компоненты бэкенда (Components)

Диаграмма компонентов демонстрирует внутреннее устройство контейнера **Backend API Application (FastAPI)**, показывая модули сервисного слоя и потоки управления данными.

```mermaid
C4Component
    title C4 Level 3: Архитектура компонентов FastAPI Backend Application

    Container_Boundary(backend_boundary, "FastAPI Backend Core (backend/app/)") {
        Component(api_router, "API Router & Dispatcher", "main.py", "Маршрутизация REST-запросов /api/v1/, сериализация Pydantic-схем, обработка глобальных исключений APIError")
        Component(auth_guard, "Auth & Scope Guard", "services.py / auth.py", "Валидация JWT, маппинг ролей, инъекция скоупа (scope_clause), возврат 404 на чужие ресурсы")
        Component(workflow_engine, "Workflow Engine & Migrator", "workflow.py / services.py", "Управление графом состояний (13 рабочих + 2 терминальных), CAS-валидация ревизий, мигратор v1 -> v2")
        Component(reports_engine, "Analytical Reports Engine", "reports_export.py / services.py", "Расчет срезов snapshot/activity/created, генератор бинарных XLSX и векторных PDF")
        Component(file_service, "Secure File Service", "files.py", "Белый список 10 форматов, проверка magic bytes, отсечение PE/ELF/скриптов, лимит 25 МБ, SHA-256")
        Component(import_service, "Import Wizard Engine", "importer.py", "Двухфазный импорт каталогов (Dry-Run Preview и транзакционный Commit с Idempotency-Key)")
        Component(integration_engine, "Integrations Gateway & Inbox", "integrations/*", "Подключаемые адаптеры MockLMS / MockWebsite, нормализация DTO v1.0, Reconciliation Inbox")
        Component(audit_store, "Audit & Event Sourcing Store", "models.py / services.py", "Запись темпоральных событий InteractionEvent с монотонным sequence и полным снимком")
    }

    ContainerDb(database, "PostgreSQL Database", "Реляционные таблицы")
    Container(filestore, "Storage Volume", "storage/attachments/")

    Rel(api_router, auth_guard, "Аутентификация и проверка прав (RBAC/Scope)")
    Rel(api_router, workflow_engine, "Переход по воронке / миграция версий")
    Rel(api_router, reports_engine, "Запрос расчета и экспорта отчетов")
    Rel(api_router, file_service, "Загрузка / скачивание вложений")
    Rel(api_router, import_service, "Предпросмотр / коммит импорта каталогов")
    Rel(api_router, integration_engine, "Синхронизация и ручное разрешение заявок")

    Rel(workflow_engine, audit_store, "Логирование переходов и миграций")
    Rel(file_service, audit_store, "Логирование загрузки файлов")
    Rel(file_service, filestore, "Запись и чтение файлов под UUID")
    Rel(audit_store, database, "INSERT в interaction_events")
    Rel(workflow_engine, database, "CAS UPDATE в interactions")
    Rel(reports_engine, database, "Аналитические выборки и срезы")
    Rel(import_service, database, "Транзакционное создание вузов и контактов")
    Rel(integration_engine, database, "Запись в IntegrationInbox и LearningMetric")
```

---

## 5. Матрица ответственности компонентов ядра

| Компонент | Модуль кодовой базы | Зона ответственности | Входные данные | Выходные данные | Обработка отказов и ошибок |
|---|---|---|---|---|---|
| **API Router & Dispatcher** | `backend/app/main.py` | Входной шлюз REST API, демаршализация JSON, связывание с зависимостями сессии БД. | HTTP-запросы (JSON, multipart), заголовки | HTTP-ответы со стандартизированной структурой `{error: ...}` | Перехват `APIError`, возврат корректного HTTP-кода (400, 401, 403, 404, 409, 413, 422). |
| **Auth & Scope Guard** | `backend/app/services.py:28-65` | Извлечение контекста пользователя, вычисление разрешений, фильтрация Scope по ролям. | Bearer JWT / X-Demo-User | Объект `User`, предикат `scope_clause` | Отказ 401 при отсутствии токена, 403 при нехватке роли, **404 при выходе за Scope**. |
| **Workflow Engine & Migrator** | `backend/app/workflow.py`, `backend/app/services.py:67-150` | Проверка графа переходов, валидация связки «программа + продукт», двухверсионная миграция процессов. | ID карточки, целевой статус, `expected_revision`, маппинг статусов | Обновленная сущность `Interaction`, отчет о миграции | CAS-отказ 409 при конфликте ревизий, 422 при попытке маппинга терминального статуса в рабочий. |
| **Analytical Reports Engine** | `backend/app/reports_export.py`, `backend/app/services.py:220-350` | Расчет срезов портфеля на дату, расчет динамики активности за интервал, генерация XLSX и PDF. | Тип отчета, дата среза / интервал дат, формат (json/xlsx/pdf) | Бинарный поток XLSX (`PK\x03\x04`), PDF (`%PDF-`), JSON DTO | 422 при некорректном диапазоне дат. Fallback на AnyIO threadpool для тяжелых расчетов. |
| **Secure File Service** | `backend/app/files.py` | Валидация 10 расширений, проверка magic bytes, блокировка PE/ELF/скриптов, сохранение под UUID, SHA-256. | Multipart-поток, оригинальное имя файла | Сущность `Attachment`, поток `FileResponse` | 413 при размере > 25 МБ, 422 при несоответствии сигнатур, 404 при попытке скачать чужой файл. |
| **Import Wizard Engine** | `backend/app/importer.py` | Двухфазный импорт таблиц XLSX/CSV: сухой прогон с валидацией строк и транзакционный коммит. | Файл таблицы, заголовок `Idempotency-Key` | DTO предпросмотра (ошибки строк), сводка созданных записей | Ошибки валидации строк не ломают весь файл; возврат детализированного списка дефектов. |
| **Integrations Gateway & Inbox** | `backend/app/integrations/*` | Адаптеры к LMS Zion и Сайту Laravel, конверт DTO v1.0, очередь сверки заявок с защитой от дублей. | Входящие вебхуки, результаты поллинга адаптеров | Записи `IntegrationInbox`, `LearningMetric` | Автоматическая изоляция неизвестных вузов в статус `pending`; дедупликация повторов. |
| **Audit & Event Sourcing Store** | `backend/app/models.py:139-154`, `backend/app/services.py:154-165` | Формирование непрерывной темпоральной хроники изменений, сохранение полных снимков карточки. | Событие, субъект, полезная нагрузка, снимок | Строка таблицы `interaction_events` с уникальным `sequence` | Запрет мутаций на уровне БД. Неизменяемость исторического аудита. |

---

## 6. Спецификация межмодульных интерфейсов и протоколов

### 6.1. Аутентификация и сессия (Keycloak OIDC PKCE S256)
- **Протокол:** OpenID Connect Core 1.0 (Authorization Code Flow with Proof Key for Code Exchange).
- **Формат токена:** RS256 JWT, содержащий клеймы `preferred_username`, `email`, `resource_access.rost-crm.roles`.
- **Хранение токена:** Строго In-Memory в JavaScript (`keycloak.current`). Время жизни access-токена: 5 минут; автоматическое упреждающее обновление за 30 секунд до истечения (`updateToken(30)`).

### 6.2. Внутренний REST API (`/api/v1/`)
- **Формат обмена:** Application/JSON в кодировке UTF-8.
- **Единый конверт ошибок:**
  ```json
  {
    "error": {
      "code": "REVISION_CONFLICT",
      "message": "Карточка была изменена другим пользователем. Обновите данные.",
      "request_id": "req-8f92a1...",
      "details": { "current_revision": 4, "expected_revision": 3 }
    }
  }
  ```
- **Идемпотентность и CAS:** Изменяющие операции (`POST`, `PATCH`) поддерживают заголовок `Idempotency-Key: <UUID>` (до 200 символов) с дедупликацией через таблицу `command_results` и параметром `expected_revision` для оптимистической блокировки.

### 6.3. Интеграционный конверт DTO v1.0 (Внешние источники)
Все входящие пакеты от LMS Zion и Сайта на Laravel приводятся адаптерами к нормализованному конверту:
```json
{
  "schema_version": "1.0",
  "source": "website",
  "entity_type": "application",
  "external_id": "app-2026-09-0012",
  "source_revision": "1",
  "operation": "upsert",
  "effective_at": "2026-09-20T10:00:00Z",
  "received_at": "2026-09-20T10:00:02Z",
  "payload": {
    "organization_name": "Московский государственный технический университет",
    "contact_name": "Смирнов Алексей Викторович",
    "email": "smirnov@mgtu.ru",
    "phone": "+7-495-123-45-67",
    "program_code": "devops",
    "comment": "Заявка на подключение кафедры ИТ"
  }
}
```
Дедупликация выполняется на уровне БД по составному ограничению:
$$\text{Unique}(\text{source}, \text{entity\_type}, \text{external\_id}, \text{source\_revision})$$

---

## 7. Контуры безопасности и границы доверия (Trust Boundaries)

Архитектура системы разграничивает четыре изолированные зоны доверия:

1. **Публичная зона (Internet / Client Zone):**
   - Браузер пользователя.
   - Среда выполнения React SPA.
   - Угрозы: XSS, перехват локальных хранилищ, подмена клиентских скриптов.
   - Защитные меры: In-memory хранение токенов, CSP-заголовки, отсутствие чувствительных бизнес-правил на клиенте.

2. **Демилитаризованная зона и обратный прокси (DMZ / Ingress Zone):**
   - Nginx Reverse Proxy / Ingress Controller.
   - Терминация TLS 1.3, ограничение частоты запросов (Rate Limiting), отсечение аномальных размеров тела запроса (> 25 МБ).

3. **Защищенная зона приложений (Application Zone):**
   - FastAPI Backend Application.
   - Выполнение аутентификации, авторизации, валидации бизнес-логики и прав Scope (152-ФЗ).
   - Выполнение сигнатурного анализа файлов (magic bytes) и отсечение вредоносного кода до записи на диск.

4. **Доверенная зона данных и хранилища (Data & Storage Zone):**
   - СУБД PostgreSQL и файловый том `storage/attachments/`.
   - Доступ разрешен исключительно сервисному пользователю бэкенда по закрытой внутренней сети (Private Docker Network / VPC).
   - Запрещен любой прямой доступ извне. Файлы хранятся под UUID, исключая исполнение веб-сервером.
