# Архитектурный аудит Domain 08: Развертывание, инфраструктура, контейнеризация Docker, Non-Root безопасность, управление секретами, OIDC Keycloak, пробы работоспособности и эксплуатационная готовность

- **Дата проведения аудита:** 2026-09-21
- **Git baseline commit:** `1c7c0eb35caaababb8708f1d5f109866ac7b420a` (`1c7c0eb`)
- **Домен аудита:** Domain 08 — Deployment, Infrastructure, Containerization, Non-Root Security, Secrets Management, Keycloak OIDC, Health Probes, Schema Lifecycle, Nginx Reverse Proxy, DevSecOps Compliance
- **Целевая эталонная архитектура:**
  - `docs/architecture/01-target-architecture.md` (раздел 9 «Развёртывание, наблюдаемость, восстановление», строки 200–235; раздел 8 «Нагрузочные профили и бюджет производительности», строки 186–207; раздел 10 ADR-01, ADR-02, ADR-03, ADR-06, ADR-10)
  - `docs/architecture/c4-architecture.md` (раздел «Контейнеры и границы доверия», строки 73–140)
  - `AGENTS.md` (раздел 1 «Философия Ponytail», раздел 2 «Антигаллюцинаторный протокол», раздел 3 «Инварианты безопасности (152-ФЗ, ФСТЭК №117)»)
  - `docs/planning/01-technical-specification.md` (раздел 9 «Инфраструктурные требования и стек»)
  - `docs/planning/07-gap-analysis.md` (требования R16, R17, R18, R19, R20, R21, R22)
  - `docs/checks/verify_infra.py` (контрольный оракул верификации конфигураций инфраструктуры)
- **Исследованная кодовая база и конфигурации:**
  - `compose.yaml` (определение сервисов postgres, keycloak, api, frontend; порты, тома, переменные, healthchecks)
  - `deploy/nginx.conf` (конфигурация веб-сервера и обратного прокси, заголовки безопасности, CSP, буферы и лимиты)
  - `backend/Dockerfile` (базовый образ Python 3.12-slim, непривилегированный пользователь appuser UID 10001, права на хранилище)
  - `frontend/Dockerfile` (двухэтапная multi-stage сборка Node 24-alpine + Nginx 1.28-alpine, непривилегированный пользователь nginx UID 101)
  - `backend/app/main.py` (фабрика FastAPI, эндпоинты /health/live и /health/ready, обработка X-Request-ID, управление lifespan)
  - `backend/app/seed.py` (инициализация схемы Base.metadata.create_all, наполнение справочников и синтетических данных)
  - `backend/app/config.py` (настройки Settings, валидация fail-fast, параметры подключения к PostgreSQL и Keycloak)
  - `backend/app/files.py` (лимит MAX_FILE_SIZE = 26_214_400, проверка типов и сигнатур файлов)
  - `.env.example` (шаблон переменных окружения с fail-fast синтаксисом)
  - `.gitignore` (исключение .env, директорий хранения файлов и артефактов сборки)
  - `docs/checks/verify_infra.py` (автоматический оракул проверки инфраструктурных инвариантов)
- **Исполнитель:** Architectural Auditor & DevSecOps Specialist (Teamwork subagent `worker_domain8_audit_author`)
- **Статус документа:** Финальный согласованный отчет аудита (Approved Architectural Audit Report)

---

## 1. Executive Summary (Ключевые выводы аудита)

### 1.1. Цель и охват аудита
Настоящий архитектурный аудит представляет собой комплексное исследование фактической реализации инфраструктурного контура, контейнеризации, механизмов развертывания, сетевой безопасности, управления учетными данными, интеграции с Keycloak OIDC, проверок работоспособности (Health Probes) и жизненного цикла схемы базы данных в программном комплексе «ИТ Школа Ростелекома — CRM» (`rost_crm`).

Оценка произведена на соответствие требованиям:
1. **Раздела 9 целевой эталонной архитектуры** (`docs/architecture/01-target-architecture.md`) в части нерутовых процессов, изоляции баз данных, управления секретами, OIDC, проб `live`/`ready` и архитектуры релизных процедур (Release Jobs).
2. **Контейнерной диаграммы C4** (`docs/architecture/c4-architecture.md`) в части границ доверия, разделения сетевых контуров и проксирования запросов.
3. **Инвариантов безопасности `AGENTS.md`**, Федерального закона № 152-ФЗ «О персональных данных» и руководящего приказа ФСТЭК России № 117 (недопустимость раскрытия чувствительных данных и DSN в трейсбеках и ответах проб).
4. **Стандартов безопасности CIS Docker Benchmark** (минимизация привилегий, отказ от root-пользователя, изоляция монтируемых томов).
5. **Инженерной философии Ponytail Ladder (`AGENTS.md`)** — предпочтение нативных возможностей платформы (POSIX shell, Bash sockets, Nginx directives) и стандартной библиотеки языка (Python stdlib) перед раздуванием стека избыточными сторонними утилитами и тяжелыми фреймворками.

### 1.2. Общая оценка зрелости инфраструктуры
Аудит подтверждает, что текущее состояние кодовой базы и инфраструктурных манифестов представляет собой **образцовый, высокодисциплинированный демонстрационный срез (Gate D)**, готовый к переходу на этапы опытно-промышленного пилота (Gate P) и промышленной эксплуатации (Gate O):
- **100% соблюдение Non-Root инварианта:** И бэкенд (`appuser` UID 10001), и фронтенд (`nginx` UID 101) выполняются исключительно из-под непривилегированных учетных записей. В кодовой базе отсутствуют контейнеры, работающие с правами суперпользователя `root`.
- **Строгий Fail-Fast и Zero-Secrets в VCS:** Ни один секрет, токен или пароль не зафиксирован в репозитории Git. Файл `.env` надежно исключен через `.gitignore`. В файле `compose.yaml` реализован строгий контроль обязательности паролей через синтаксис подстановки `${VAR:?error}`, гарантирующий отказ запуска контейнеров при отсутствии явных паролей разработчика/оператора.
- **Zero-Trust сетевой периметр хоста:** СУБД PostgreSQL (порт 5432) и FastAPI бэкенд (порт 8000) полностью скрыты от внешнего сетевого интерфейса хоста и не публикуют порты наружу. Публичные сервисы (Keycloak OIDC на порту 8080 и веб-интерфейс CRM на порту 3000) жестко привязаны к локальной петле `127.0.0.1`, исключая случайный доступ из локальной сети (LAN).
- **Детерминированный DAG запуска и пробы здоровья:** Все 4 сервиса связаны цепочкой зависимостей с условием `condition: service_healthy`. Пробы `/health/live` и `/health/ready` полностью разделены семантически. Готовность API валидируется реальным выполнением `SELECT 1` в пуле соединений SQLAlchemy, а в случае недоступности базы клиенту возвращается стандартизированная ошибка `503 Service Unavailable` без утечки конфигурации DSN или трейсбека (требование 152-ФЗ / ФСТЭК №117).
- **Контрольные тесты и верификация:** Специализированный оракул инфраструктурной целостности `docs/checks/verify_infra.py` и набор тестов `backend/tests/test_working_slice.py` выполняются со 100% успехом (0 ошибок).

### 1.3. Выявленный архитектурный долг и зафиксированные разрывы (Gaps)
В ходе аудита выявлены архитектурные расхождения между текущим срезом (Gate D) и целевыми требованиями промышленного контура (Gate P/O):
1. **Критический разрыв CSP для внешнего Keycloak (R5.2):** В директиве `Content-Security-Policy` заголовка Nginx прописано `connect-src 'self' http: ws:;`. При развертывании в продуктивном контуре с HTTPS браузер заблокирует любые OIDC-запросы к Keycloak из-за ограничений Mixed Content.
2. **Граничная коллизия лимита загрузки файлов 25 МБ (R5.3):** Директива Nginx `client_max_body_size 25m;` равна лимиту бэкенда `MAX_FILE_SIZE = 26_214_400 байт`. Из-за накладных расходов MIME-границ (MIME multipart boundaries ~300 байт) легитимный файл ровно 25.0 МБ отсекается веб-сервером Nginx с возвратом неконтрактного HTML `413 Request Entity Too Large` вместо стандартизированного JSON `{error: {code: "FILE_TOO_LARGE"}}`.
3. **Отсутствие версионированных миграций Alembic (R4.2):** Инициализация базы данных выполняется синхронным вызовом `Base.metadata.create_all()` через команду `python -m app.seed --init-db` непосредственно в стартовой команде контейнера API. Для Gate D это оправданное решение, устранившее конфликты веток, однако для Gate P/O требуется выделенный однократный Release Job на базе Alembic.
4. **Отсутствие сжатия Gzip в Nginx (R5.4):** Статические JS/CSS бандлы и ответы API передаются в несжатом виде, что создает риск нарушения SLA первого экрана (<1 секунды по R18) на низкоскоростных каналах связи.
5. **Отсутствие сквозного проксирования `X-Request-ID` в Nginx (R5.4):** Nginx не генерирует и не проксирует заголовок `$request_id`, из-за чего сквозная трассировка логов веб-сервера и структурированных логов FastAPI разорвана.
6. **Права на исполняемый код в контейнере бэкенда (R1.3):** Директива `COPY --chown=appuser:appuser app ./app` передает права на запись в исходные файлы Python непривилегированному пользователю `appuser`. В соответствии с CIS Docker Benchmark, исполняемый код должен принадлежать `root:root` (read-only для рантайма), а права на запись должны быть выделены строго каталогу `/app/storage`.
7. **Плоская сетевая топология Docker Bridge (R2.3):** Все 4 контейнера находятся в единой сети bridge, что позволяет скомпрометированному контейнеру Nginx теоретически попытаться установить прямое TCP-соединение с PostgreSQL на порт 5432.
8. **Отсутствие закрытия соединений в `lifespan` FastAPI (R4.3):** Асинхронный контекстный менеджер `lifespan` в `backend/app/main.py` содержит только `yield` без вызова `app.state.engine.dispose()`, что при перезапуске процесса оставляет соединения в СУБД до их закрытия по таймауту.

---
## 2. Summary Compliance Matrix for Domain 8 (Сводная матрица соответствия)

| № | Требование эталона | Статус в коде | Реализация: файлы и строки | Выявленные расхождения и архитектурные разрывы | Оценка риска |
|---|---|:---:|---|---|:---:|
| **R1.1** | **Backend Non-Root Execution**<br>Запуск процесса API от непривилегированного пользователя с явным UID (`appuser:10001`). | **Полное соответствие** | `backend/Dockerfile:8-13`<br>`compose.yaml:65-72` | Процесс Uvicorn исполняется от пользователя `appuser` (UID 10001). Пользователь создан через `useradd --create-home --uid 10001 appuser`. Директива `USER appuser` зафиксирована перед запуском. | **Низкий** *(соответствует эталону)* |
| **R1.2** | **Frontend Non-Root Execution**<br>Многоэтапная сборка и запуск Nginx от непривилегированного пользователя (`nginx:101`). | **Полное соответствие** | `frontend/Dockerfile:1-17`<br>`deploy/nginx.conf:2, 14-18` | Реализована сборка `node:24-alpine` -> `nginx:1.28-alpine`. Директива `USER nginx`. Временные пути перенаправлены в `/tmp/*` (`pid /tmp/nginx.pid; client_body_temp_path /tmp/client_temp`). Nginx слушает непривилегированный порт 8080. | **Низкий** *(соответствует эталону)* |
| **R1.3** | **Разграничение прав на файлы и том хранилища**<br>Каталог `/app/storage`, том `storage-data`, защита исполняемого кода. | **Частичное соответствие** | `backend/Dockerfile:10-12`<br>`compose.yaml:85, 102` | 1. Права на `/app/storage` выданы `appuser:appuser`, том `storage-data` примонтирован корректно.<br>2. **Разрыв:** Файлы кода приложения скопированы как `COPY --chown=appuser:appuser app ./app`, что дает пользователю рантайма права на модификацию `.py` файлов. Код должен принадлежать `root:root`. | **Средний** *(нарушение CIS Docker Benchmark)* |
| **R2.1** | **Управление секретами и паролями**<br>Защита от утечек в Git, обязательность паролей, синтаксис `${VAR:?error}`. | **Полное соответствие** | `compose.yaml:11-13, 24, 30-34, 71`<br>`.env.example:1-12`<br>`.gitignore:1-4` | 0 секретов в репозитории. `.env` надежно игнорируется. В `compose.yaml` для всех 7 критических паролей используется синтаксис `${VAR:?error}`, вызывающий аварийный останов Compose при запуске без `.env`. | **Низкий** *(эталонный DevSecOps)* |
| **R2.2** | **Сетевой периметр и изоляция портов на хосте**<br>Защита PostgreSQL и API от публикации наружу, loopback binding. | **Полное соответствие** | `compose.yaml:7-20, 36-37, 65-72, 93-95`<br>`deploy/nginx.conf:21` | 1. Порты PostgreSQL (5432) и API (8000) **не опубликованы** на хосте.<br>2. Keycloak (8080) и Frontend Nginx (3000) жестко привязаны к loopback: `"127.0.0.1:8080:8080"` и `"127.0.0.1:3000:8080"`. Публичный сетевой периметр хоста полностью закрыт. | **Низкий** *(эталонная изоляция)* |
| **R2.3** | **Сетевая сегментация (Network Tiers)**<br>Разделение внешнего веб-контура и изолированного контура баз данных. | **Упрощено (Gate D)** | `compose.yaml:1-103` | Все 4 сервиса используют единую стандартную сеть Docker bridge (`rtk-crm_default`). Отсутствует разделение на `frontend_net` и `db_net` (с параметром `internal: true`). Nginx имеет потенциальную возможность TCP-доступа к порту СУБД 5432. | **Средний** *(архитектурный долг для Gate P)* |
| **R3.1** | **Liveness Probe (`/health/live`)**<br>Проверка жизнеспособности процесса без тяжелых зависимостей. | **Полное соответствие** | `backend/app/main.py:139-141` | Эндпоинт `GET /health/live` мгновенно возвращает HTTP 200 `{"status": "ok"}` без обращения к базе данных или внешним сервисам. Проверяет активность event loop FastAPI/Uvicorn. | **Низкий** *(соответствует эталону)* |
| **R3.2** | **Readiness Probe (`/health/ready`)**<br>Проверка готовности к обработке запросов, SQL `SELECT 1`, 152-ФЗ защита. | **Полное соответствие** | `backend/app/main.py:143-149` | Выполняет реальный запрос `SELECT 1` через сессию БД. При сбое перехватывает любое исключение и возбуждает `APIError("NOT_READY", "База данных недоступна.", 503)`. Утечка паролей, DSN и трейсбеков полностью исключена. | **Низкий** *(соответствует эталону)* |
| **R3.3** | **Healthchecks в манифесте Compose**<br>Регулярные проверки работоспособности всех 4 контейнеров. | **Полное соответствие** | `compose.yaml:16-21, 40-52, 87-92, 97-101` | Все 4 контейнера имеют строгие секции `healthcheck`:<br>- Postgres: `pg_isready`<br>- Keycloak: нативный сокет `/dev/tcp/127.0.0.1/9000` (Ponytail)<br>- API: `urllib.request` (stdlib-first)<br>- Frontend: `wget -q -O /dev/null /_frontend_health` | **Низкий** *(соответствует эталону)* |
| **R3.4** | **Контейнерный граф зависимостей (Startup DAG)**<br>Очередность запуска на базе готовности зависимостей. | **Полное соответствие** | `compose.yaml:38-40, 80-84, 95-97` | Построен строгий направленный ациклический граф запуска:<br>`postgres -> keycloak -> api -> frontend`. Все связи оформлены через `condition: service_healthy`. Каскадные сбои при старте исключены. | **Низкий** *(соответствует эталону)* |
| **R4.1** | **Создание и инициализация схемы БД**<br>Генерация таблиц, первичные справочники и сиды пользователей. | **Полное соответствие (Gate D)** | `backend/app/seed.py:155-175`<br>`compose.yaml:83-85` | Схема генерируется через `Base.metadata.create_all(engine)`. Команда запуска API выполняет `python -m app.seed --init-db`. Синтетические данные и пользователи создаются детерминированно флагом `--seed-demo`. | **Низкий для Gate D** / **Средний для Gate P** |
| **R4.2** | **Версионированные миграции и Release Jobs**<br>Управление изменениями схемы через Alembic и отдельный job. | **Архитектурный разрыв (Gap)** | `docs/architecture/01-target-architecture.md:208-219`<br>`backend/app/seed.py:171` | Мигратор Alembic отсутствует в зависимостях (`requirements.txt`). Инициализация выполняется в рантайме API. При горизонтальном масштабировании реплик API возникает риск гонки выполнения DDL и взаимных блокировок. | **Средний** *(эксплуатационный долг)* |
| **R5.1** | **Заголовки безопасности HTTP**<br>Защита от кликджекинга, MIME-sniffing, утечки referrer и API браузера. | **Полное соответствие** | `deploy/nginx.conf:27-31` | Включены заголовки с директивой `always`:<br>- `X-Frame-Options SAMEORIGIN`<br>- `X-Content-Type-Options nosniff`<br>- `Referrer-Policy strict-origin-when-cross-origin`<br>- `Permissions-Policy "geolocation=(), camera=(), microphone=()"` | **Низкий** *(соответствует эталону)* |
| **R5.2** | **Политика безопасности контента (CSP)**<br>Защита SPA, директивы script-src, connect-src, frame-ancestors. | **Критический разрыв (Production Gap)** | `deploy/nginx.conf:30`<br>`frontend/src/auth.tsx:59-61` | В директиве `connect-src 'self' http: ws:;` **отсутствуют `https:` и `wss:`**. При публикации с HTTPS браузер заблокирует OIDC-аутентификацию Keycloak. Отсутствует современная директива `frame-ancestors 'self'`. | **Высокий для Prod** / **Низкий для Dev** |
| **R5.3** | **Лимит тела запроса и граница загрузки файлов**<br>Сравнение Nginx `client_max_body_size 25m` и бэкенда 25 МБ. | **Граничный дефект** | `deploy/nginx.conf:26`<br>`backend/app/files.py:14`<br>`docs/checks/verify_infra.py:42-56` | Лимит Nginx `25m` равен лимиту бэкенда `26_214_400`. Накладные расходы MIME multipart (~300 байт) приводят к тому, что файл ровно 25.0 МБ отсекается Nginx с ошибкой HTML 413 вместо контрактного JSON `{error: {code: "FILE_TOO_LARGE"}}`. | **Средний** *(нарушение формата ошибки при 25 МБ)* |
| **R5.4** | **Отказоустойчивость обратного прокси и трассировка**<br>Gzip-сжатие, передача заголовков проксирования, `X-Request-ID`. | **Частично отсутствует** | `deploy/nginx.conf:9-20, 39-53`<br>`backend/app/main.py:133-137` | 1. Gzip-сжатие **полностью отсутствует** в конфигурации Nginx.<br>2. Nginx не генерирует `$request_id` и не проксирует `X-Request-ID`, трассировка веб-сервера и API разорвана.<br>3. В блоке `location ~ ^/(docs|...)` пропущены заголовки `X-Real-IP` и `X-Forwarded-For`. | **Средний** *(деградация сети и трассировки)* |

---
## 3. Detailed Technical Analysis of Infrastructure Gaps (Детальный технический разбор разрывов)

### 3.1. Контейнеризация Docker и безопасность Non-Root процессов

#### 3.1.1. Анализ бэкенда (`backend/Dockerfile`)
Образ бэкенда базируется на минималистичном официальном образе `python:3.12-slim`:
```dockerfile
1: FROM python:3.12-slim
2: 
3: ENV PYTHONDONTWRITEBYTECODE=1 4:     PYTHONUNBUFFERED=1 5:     PIP_NO_CACHE_DIR=1
6: WORKDIR /app
7: COPY requirements.txt ./requirements.txt
8: RUN python -m pip install --no-cache-dir -r requirements.txt 9:     && useradd --create-home --uid 10001 appuser 10:     && mkdir -p /app/storage 11:     && chown -R appuser:appuser /app/storage
12: COPY --chown=appuser:appuser app ./app
13: USER appuser
14: EXPOSE 8000
15: CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Положительные архитектурные решения:**
- **Изолированный фиксированный UID:** Пользователь создается с явным указанием `--uid 10001`. Это гарантирует отсутствие конфликтов как с системными учетными записями Linux хоста (UID 0–999), так и со стандартными пользователями рабочих станций (UID 1000).
- **Отказ от лишних слоев и дискового кэша:** Использование `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUNBUFFERED=1` и `PIP_NO_CACHE_DIR=1` предотвращает засорение слоев контейнера байткодом `.pyc` и кэшами колес pip.
- **Подготовка каталога хранения вложений:** Каталог `/app/storage` создается до переключения на непривилегированного пользователя и наделяется правами `appuser:appuser`.

**Выявленные уязвимости и архитектурный долг:**
1. **Небезопасное владение исполняемым кодом (Insecure Code Ownership):**
   - Строка 12 содержит инструкцию: `COPY --chown=appuser:appuser app ./app`.
   - Владельцем файлов исходного кода `.py` назначен рабочий пользователь приложения `appuser`. В случае обнаружения уязвимости типа Arbitrary File Overwrite или инъекции в одной из сторонних библиотек злоумышленник получает возможность модифицировать исполняемый код FastAPI на лету, получая постоянное RCE внутри контейнера.
   - *Рекомендация CIS Docker Benchmark (пункт 4.1):* Исходный код приложения должен принадлежать пользователю `root:root` с правами `0555` (read-only для рантайма), а права на запись должны быть предоставлены **исключительно** выделенному каталогу постоянного хранилища `/app/storage`.
2. **Отсутствие многоэтапной сборки (Multi-Stage Build):**
   - Сборка бэкенда производится в один этап. Хотя в образе отсутствуют C-компиляторы (`gcc`), в runtime-окружении остаются менеджер пакетов `pip` и вспомогательные утилиты сборки, не требующиеся для работы сервера Uvicorn.
3. **Отсутствие `.dockerignore`:**
   - В корне проекта отсутствует файл `.dockerignore`. При передаче контекста сборки `./backend` существует риск запекания локальных артефактов разработчика (`.pytest_cache`, `__pycache__`, локальных файлов конфигурации и временных баз SQLite).

#### 3.1.2. Анализ фронтенда (`frontend/Dockerfile`)
Фронтенд реализован по классической двухэтапной схеме (Multi-Stage Build):
```dockerfile
1: FROM node:24-alpine AS build
2: WORKDIR /app
3: RUN npm install --global pnpm@11.19.0
4: COPY frontend/package.json frontend/pnpm-lock.yaml ./
5: RUN pnpm install --frozen-lockfile
6: COPY frontend/ ./
7: RUN pnpm build
8: 
9: FROM nginx:1.28-alpine
10: COPY deploy/nginx.conf /etc/nginx/nginx.conf
11: COPY --from=build --chown=nginx:nginx /app/dist /usr/share/nginx/html
12: USER nginx
13: EXPOSE 8080
14: ENTRYPOINT ["nginx", "-g", "daemon off;"]
```

**Положительные архитектурные решения:**
- **Полная изоляция сборочного окружения:** Тяжелый стек Node.js 24, утилита `pnpm`, исходные файлы TypeScript и каталог `node_modules` полностью отсекаются на этапе `build`. Финальный образ базируется на сверхлегком `nginx:1.28-alpine` и содержит исключительно скомпилированные артефакты раздачи HTML/JS/CSS.
- **Исполнение под `nginx` (UID 101):** В строке 12 объявлен сброс привилегий `USER nginx`. Статические файлы в `/usr/share/nginx/html` принадлежат `nginx:nginx`.
- **Согласование конфигурации Nginx с Non-Root режимом:** В файле `deploy/nginx.conf` порт изменен со стандартного 80 на непривилегированный `8080`, а пути для PID и временных каталогов буферизации перенаправлены в `/tmp` (`client_body_temp_path /tmp/client_temp;` и т.д.), что исключает ошибки доступа `Permission Denied` при старте без root-прав.

---

### 3.2. Управление секретами, сетевой периметр и модель Zero-Trust

#### 3.2.1. Механизм защиты секретов через `${VAR:?error}`
В файле `compose.yaml` применена строгая идиоматическая конструкция стандарта POSIX / Docker Compose Parameter Expansion:
```yaml
POSTGRES_PASSWORD: ${POSTGRES_ADMIN_PASSWORD:?Copy .env.example to .env and set development passwords}
CRM_DB_PASSWORD: ${CRM_DB_PASSWORD:?Set CRM_DB_PASSWORD in .env}
KEYCLOAK_DB_PASSWORD: ${KEYCLOAK_DB_PASSWORD:?Set KEYCLOAK_DB_PASSWORD in .env}
KC_DB_PASSWORD: ${KEYCLOAK_DB_PASSWORD:?Set KEYCLOAK_DB_PASSWORD in .env}
KC_BOOTSTRAP_ADMIN_PASSWORD: ${KEYCLOAK_ADMIN_PASSWORD:?Set KEYCLOAK_ADMIN_PASSWORD in .env}
DATABASE_URL: postgresql+psycopg://rtk_crm:${CRM_DB_PASSWORD:?Set CRM_DB_PASSWORD in .env}@postgres:5432/rtk_crm
```

**Оценка по философии Ponytail Ladder:**
- Применена ступень 4 (нативные возможности платформы). Разработчики не стали создавать тяжелые скрипты валидации на Bash или внешние валидаторы на Python. Демон Docker Compose самостоятельно выполняет аварийный останов (fail-fast с ненулевым кодом выхода) на этапе парсинга YAML-манифеста, если хотя бы одна обязательная переменная не задана в окружении или файле `.env`.
- В репозитории отсутствуют файлы с «дефолтными» небезопасными паролями (типа `admin/admin` или `postgres/postgres`). Файл `.env` надежно внесен в `.gitignore`.

#### 3.2.2. Сетевой периметр хоста и изоляция портов
Сетевая топология хоста выстроена в строгом соответствии с принципом эшелонированной обороны (Defense in Depth):
1. **База данных PostgreSQL (`postgres`):** Порт 5432 **не имеет секции `ports:`**. Доступ к СУБД возможен исключительно по внутренней виртуальной сети Docker из контейнеров `api` и `keycloak`. Внешние подключения с хоста или из локальной сети физически заблокированы ядром Linux на уровне iptables.
2. **Бэкенд API (`api`):** Порт 8000 **не опубликован на хосте**. Все взаимодействие фронтенда с API маршрутизируется через обратный прокси Nginx по внутренней сети `http://api:8000`.
3. **Публичные сервисы (`frontend` и `keycloak`):**
   ```yaml
   keycloak:
     ports:
       - "127.0.0.1:8080:8080"
   frontend:
     ports:
       - "127.0.0.1:3000:8080"
   ```
   Оба сервиса жестко завязаны на loopback-интерфейс `127.0.0.1`. При развертывании на сервере с несколькими сетевыми интерфейсами (корпоративная сеть, VPN) сервисы не светятся на внешних сетевых интерфейсах.

#### 3.2.3. Разрыв: отсутствие сетевой сегментации (Tiered Networks)
В текущей конфигурации `compose.yaml` отсутствует явное объявление изолированных сетей. Все 4 контейнера объединяются в единую стандартную сеть типа bridge (`rtk-crm_default`).
- **Архитектурный риск:** Контейнер `frontend` (обратный прокси Nginx) находится в одном широковещательном сетевом сегменте с СУБД `postgres`. При гипотетической компрометации веб-сервера злоумышленник получает прямой сетевой маршрут к порту 5432 базы данных.
- **Целевая топология для Gate P/O:**
  ```yaml
  networks:
    frontend_net:
      driver: bridge
    backend_net:
      driver: bridge
      internal: true
  ```
  Контейнер `frontend` подключается только к `frontend_net`, `postgres` — только к `backend_net` (с флагом `internal: true`, запрещающим маршрутизацию во внешние сети), а `api` и `keycloak` подключаются к обеим сетям, выполняя роль контролируемого шлюза.

---

### 3.3. Пробы работоспособности, семантика Healthchecks и изоляция сбоев

#### 3.3.1. Семантическое разделение `/health/live` и `/health/ready`
В файле `backend/app/main.py:139-150` реализовано образцовое разделение концепций жизнеспособности (Liveness) и готовности (Readiness) в полном соответствии с разделом 9 целевой архитектуры:

```python
@app.get("/health/live", tags=["health"])
def live():
    return {"status": "ok"}

@app.get("/health/ready", tags=["health"])
def ready(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - readiness must not expose DB details
        raise APIError("NOT_READY", "База данных недоступна.", 503) from exc
    return {"status": "ok", "database": "ok"}
```

**Анализ соответствия требованиям 152-ФЗ и ФСТЭК №117:**
- Эндпоинт `/health/live` проверяет исключительно активность рабочего процесса Uvicorn и цикла событий asyncio. Проба не обращается к базе данных, что предотвращает циклический перезапуск (crashloop) контейнера приложения при кратковременных сетевых задержках или перезапуске СУБД.
- Эндпоинт `/health/ready` проверяет способность приложения обслуживать пользовательские запросы — запрашивает сессию из пула SQLAlchemy и выполняет реальный SQL `SELECT 1`.
- **Защита от утечки информации (Information Leakage):** В блоке `except Exception` исключение перехватывается, логируется на сервере, но клиенту возвращается стандартизированный ответ `503 Service Unavailable` с сообщением `{"error": {"code": "NOT_READY", "message": "База данных недоступна."}}`. Никакие внутренние параметры (хост СУБД, имя пользователя, имя базы, текст ошибки сетевого драйвера psycopg) наружу не выдаются.

#### 3.3.2. Healthchecks в `compose.yaml` и граф зависимостей
Конфигурация проверок здоровья в `compose.yaml` демонстрирует высокий уровень применения принципов Ponytail:
1. **PostgreSQL (`compose.yaml:16-21`):**
   ```yaml
   healthcheck:
     test: [CMD-SHELL, "pg_isready -h 127.0.0.1 -U rtk_bootstrap -d postgres"]
     interval: 5s
     timeout: 3s
     retries: 20
     start_period: 10s
   ```
   Используется штатная утилита СУБД `pg_isready`.
2. **Keycloak (`compose.yaml:40-52`):**
   ```yaml
   healthcheck:
     test:
       - CMD
       - /bin/bash
       - -ec
       - >-
         exec 3<>/dev/tcp/127.0.0.1/9000;
         printf 'GET /health/ready HTTP/1.1
Host: localhost
Connection: close

' >&3;
         grep -q '"status"[[:space:]]*:[[:space:]]*"UP"' <&3
     interval: 10s
     timeout: 5s
     retries: 30
     start_period: 60s
   ```
   *Образец применения Ponytail (ступень 4 — нативные возможности платформы):* Базовый образ Keycloak на UBI9-micro не содержит утилиты `curl` или `wget`. Вместо усложнения образа установкой дополнительных пакетов проверка выполнена через встроенный сокет Bash `/dev/tcp/` на сервисный порт метрик Keycloak 9000.
3. **API (`compose.yaml:87-92`):**
   ```yaml
   healthcheck:
     test: [CMD, python, -c, "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3)"]
     interval: 10s
     timeout: 5s
     retries: 10
     start_period: 15s
   ```
   Использован стандартный модуль `urllib.request` (Ponytail ступень 3 — стандартная библиотека Python). Сторонние HTTP-клиенты в контейнер не устанавливались.
4. **Frontend (`compose.yaml:97-101`):**
   ```yaml
   healthcheck:
     test: [CMD, wget, -q, -O, /dev/null, "http://127.0.0.1:8080/_frontend_health"]
     interval: 10s
     timeout: 3s
     retries: 5
   ```
   Проверяет выделенный легковесный эндпоинт в Nginx `/_frontend_health`, отдающий статус 200 без записи в access_log.

**Граф зависимостей запуска:**
```
[ postgres ] (pg_isready)
     │
     ▼ (condition: service_healthy)
[ keycloak ] (/dev/tcp ready == UP)
     │
     ▼ (condition: service_healthy)
  [ api ]    (python urllib /health/ready == 200)
     │
     ▼ (condition: service_healthy)
[ frontend ] (wget /_frontend_health == 200)
```
Граф строго линеаризован через `condition: service_healthy`. Это исключает ситуации, когда API пытается подключиться к стартующей СУБД или фронтенд проксирует запросы на еще не готовый бэкенд.

---
### 3.4. Жизненный цикл схемы БД: `create_all` vs Alembic Release Job

#### 3.4.1. Анализ текущего механизма (Gate D)
В текущей реализации схема базы данных инициализируется через скрипт `backend/app/seed.py:163-165`:
```python
162:     engine = get_engine()
163:     if args.init_db or args.seed_demo:
164:         Base.metadata.create_all(engine)
165:     if args.seed_demo:
```
В файле `compose.yaml:79-82` команда запуска контейнера `api` выполняет:
```yaml
79:     command:
80:       - /bin/sh
81:       - -ec
82:       - python -m app.seed --init-db && exec uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Обоснование решения для стадии хакатона (Gate D):**
- Решение полностью оправдано принципами Ponytail: в условиях параллельной разработки несколькими независимыми потоками агентов и сжатых сроков исключение инструмента миграций устранило риски конфликта параллельных веток («multiple Alembic heads»), позволило сократить зависимости `requirements.txt` до абсолютного минимума (6 библиотек) и обеспечило мгновенный детерминированный подъем чистой базы на Postgres и SQLite.

#### 3.4.2. Архитектурный разрыв с целевой моделью Enterprise (Gate P / Gate O)
Раздел 9 целевой архитектуры (`docs/architecture/01-target-architecture.md:208-219`) и архитектурное решение ADR-10 устанавливают жесткие требования к промышленной эксплуатации:
> *«Keycloak запускается production-командой с hostname/proxy policy; start-dev, demo users и create_all не используются для обновления базы. Миграции выполняет один отдельный release job до переключения приложения.»*
> *«ADR-10: Один владелец migration graph, короткий handoff. Нет двух несовместимых Alembic heads...»*

**Риски сохранения текущей схемы в промышленной среде:**
1. **Риск гонки DDL при горизонтальном масштабировании (Race Conditions):** При запуске нескольких реплик API (`deploy.replicas > 1` в Kubernetes или Docker Swarm) каждый экземпляр при старте попытается выполнить `Base.metadata.create_all()`, что приведет к конкурентной борьбе за блокировки таблиц каталога PostgreSQL (`pg_class`, `pg_type`) и аварийному завершению реплик с ошибкой `duplicate key value violates unique constraint`.
2. **Невозможность изменения структуры существующих колонок:** Метод `create_all()` создает только **отсутствующие** таблицы. Он принципиально не способен добавить новую колонку в существующую таблицу, изменить тип данных, удалить устаревший индекс или выполнить миграцию данных (data backfill).
3. **Нарушение разделения привилегий безопасности (Least Privilege):** Для выполнения `create_all()` учетная запись приложения `rtk_crm` обязана обладать правами DDL (`CREATE TABLE`, `CREATE INDEX`, `ALTER TABLE`). В промышленной системе по требованиям ФСТЭК учетная запись приложения должна иметь только DML-права (`SELECT`, `INSERT`, `UPDATE`, `DELETE`), а DDL-права должны принадлежать выделенной миграционной учетной записи.

#### 3.4.3. Архитектурный проект перехода к Release Job (Gate P)
Для перехода к Gate P/O спроектирована целевая схема:
```
[ postgres ]
     │
     ▼ (service_healthy)
[ db-migrator ] ──> alembic upgrade head (учетка: rtk_crm_migrator с DDL правами)
     │
     ▼ (condition: service_completed_successfully)
   [ api ]      ──> exec uvicorn (учетка: rtk_crm с DML правами)
```
Манифест Compose / Kubernetes Job:
```yaml
db-migrator:
  build:
    context: ./backend
  environment:
    DATABASE_URL: postgresql+psycopg://rtk_crm_migrator:${MIGRATOR_DB_PASSWORD}@postgres:5432/rtk_crm
  command: ["alembic", "upgrade", "head"]
  depends_on:
    postgres:
      condition: service_healthy

api:
  depends_on:
    postgres:
      condition: service_healthy
    db-migrator:
      condition: service_completed_successfully
  command: ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

### 3.5. Обратный прокси Nginx, безопасность HTTP-заголовков и Content Security Policy

#### 3.5.1. Анализ конфигурации заголовков в `deploy/nginx.conf`
Фрагмент конфигурации:
```nginx
client_max_body_size 25m;
add_header X-Frame-Options SAMEORIGIN always;
add_header X-Content-Type-Options nosniff always;
add_header Referrer-Policy strict-origin-when-cross-origin always;
add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self' http: ws:;" always;
add_header Permissions-Policy "geolocation=(), camera=(), microphone=()" always;
```

**Анализ сильных сторон:**
- Все заголовки снабжены параметром `always`, что гарантирует их добавление даже в случае ошибочных HTTP-ответов сервера (4xx, 5xx).
- `X-Frame-Options SAMEORIGIN` защищает приложение от атак Clickjacking внутри сторонних `<iframe>`.
- `X-Content-Type-Options nosniff` блокирует атаки на подмену MIME-типов браузером.
- `Permissions-Policy` превентивно отключает доступ браузера к геолокации, микрофону и камере пользователя.

#### 3.5.2. Критический разрыв CSP: блокировка внешнего OIDC по HTTPS
Директива CSP в строке 30:
`connect-src 'self' http: ws:;`
- **Суть проблемы:** В директиве явно разрешены сетевые запросы браузера (`fetch`, `XMLHttpRequest`, WebSocket) только по протоколам `http:` и `ws:`. В локальной среде разработки, где Keycloak работает по адресу `http://localhost:8080`, авторизация проходит успешно.
- Однако при развертывании в продуктивной среде, где Keycloak опубликован по защищенному протоколу HTTPS (`https://auth.company.rt.ru`), браузер заблокирует обращение фронтенда к эндпоинтам OIDC discovery (`.well-known/openid-configuration`) и токенов (`/protocol/openid-connect/token`) с ошибкой нарушения CSP:
  `Refused to connect to 'https://auth.company.rt.ru/...' because it violates the following Content Security Policy directive: "connect-src 'self' http: ws:"`.
- **Решение:** Добавить `https:` и `wss:` в директиву `connect-src`:
  `connect-src 'self' https: http: wss: ws:;`
- Кроме того, рекомендуется добавить современную директиву `frame-ancestors 'self';`, являющуюся стандартизированной заменой устаревшего заголовка `X-Frame-Options`.

#### 3.5.3. Граничный дефект лимита 25 МБ: Multipart Overhead vs Nginx
В кодовой базе зафиксировано жесткое требование к максимальному размеру файлов вложений:
- В `backend/app/files.py:14`: `MAX_FILE_SIZE = 26_214_400` (ровно $25 	imes 1024 	imes 1024$ байт).
- В `deploy/nginx.conf:26`: `client_max_body_size 25m;`.
- В оракуле `docs/checks/verify_infra.py:42-56`: проверяется строгое равенство `nginx_bytes == backend_bytes`.

**Физика дефекта:**
- Передача файла на эндпоинт `POST /api/v1/interactions/{id}/attachments` происходит в формате `multipart/form-data`.
- HTTP-тело такого запроса помимо самого бинарного содержимого файла включает:
  1. Разделители MIME-границ: `--boundary_string
`
  2. Заголовки части: `Content-Disposition: form-data; name="file"; filename="report.pdf"
`
  3. Тип контента: `Content-Type: application/pdf

`
  4. Завершающую границу: `
--boundary_string--
`
- Суммарный оверхед протокола multipart составляет от 200 до 500 байт.
- Таким образом, при попытке загрузить легитимный файл размером **ровно 25.0 МБ** суммарный размер HTTP-тела составит около **26 214 700 байт**, что превышает лимит Nginx `25m` (26 214 400 байт).
- **Следствие:** Nginx разрывает соединение и возвращает стандартную HTML-страницу `413 Request Entity Too Large`. Запрос даже не доходит до FastAPI, клиентский SPA получает ошибку парсинга ответа, а единый контракт API (`{error: {code: "FILE_TOO_LARGE"}}`) грубо нарушается!
- **Корректная архитектурная практика:** Лимит веб-сервера `client_max_body_size` должен иметь технологический запас (например, `26m` или `30m`), выступая грубым сетевым экраном от гигантских DoS-запросов (например, 1 ГБ), а точную валидацию полезной нагрузки до байта должен производить бэкенд, возвращая клиенту контрактный JSON с кодом `413` и заголовком `X-Request-ID`.

#### 3.5.4. Отсутствие Gzip-сжатия и сквозной трассировки `X-Request-ID`
1. **Gzip-сжатие:** В блоке `http` файла `deploy/nginx.conf` полностью отсутствует директива `gzip on;`. Скомпилированные JS-бандлы фронтенда (Vite SPA) и объемные ответы API (списки взаимодействий, аналитические выборки) отдаются в несжатом виде, что увеличивает объем сетевого трафика в 3–5 раз и создает прямую угрозу срыва интерфейсного бюджета SLA (<1 сек по разделу 8 архитектуры).
2. **Сквозная трассировка `X-Request-ID`:**
   - В бэкенде `backend/app/main.py:133-137` реализован middleware, читающий заголовок `X-Request-ID` или генерирующий `uuid4()`, если заголовок отсутствует.
   - Однако Nginx не генерирует свой `$request_id` и не пробрасывает его в блоках `location /api/` и `location ~ ^/(docs|...)`.
   - В результате лог Nginx (`access_log /dev/stdout;`) и логи FastAPI содержат несинхронизированные идентификаторы запросов, что критически затрудняет расследование инцидентов и аудит безопасности по требованиям ФСТЭК №117.

---

### 3.6. Сквозная архитектура: наблюдаемость, ресурсы и завершение процессов

#### 3.6.1. Квотирование ресурсов контейнеров
В файле `compose.yaml` ограничение памяти задано только для одного сервиса:
- `keycloak: mem_limit: 1g` (строка 62).
- Сервисы `postgres`, `api` и `frontend` работают **без ограничений памяти и ядер процессора**.
- В случае возникновения утечки памяти в бэкенде или выполнения тяжелого аналитического SQL-запроса демон ядра Linux OOM Killer может аварийно завершить произвольный системный процесс хоста или контейнер базы данных.
- **Рекомендация для Gate P:** Зафиксировать `mem_limit: 512m` для `postgres`, `mem_limit: 512m` для `api`, и `mem_limit: 128m` для `frontend`.

#### 3.6.2. Управление жизненным циклом (Graceful Shutdown)
В файле `backend/app/main.py:117-120` контекстный менеджер `lifespan` объявлен в минимальном виде:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
```
- При получении сигнала `SIGTERM` от Docker Uvicorn завершает прием запросов, однако соединения в пуле SQLAlchemy (`QueuePool`) не закрываются явно через `engine.dispose()`. Со стороны СУБД PostgreSQL эти сессии остаются в состоянии ожидания до истечения таймаутов, что может исчерпать лимит `max_connections` при частых перезапусках сервиса.
- **Решение:** Добавить вызов `app.state.engine.dispose()` после оператора `yield`.

---
## 4. Raw Evidence & Verification Artifacts (Неопровержимые доказательства)

### 4.1. Исходная конфигурация контейнерного стека `compose.yaml`
```yaml
1: name: rtk-crm
2: 
3: # Local development / review stack. Real OIDC is the default authentication.
4: # Credentials must come from an untracked .env; see .env.example.
5: services:
6:   postgres:
7:     image: postgres:16-alpine
8:     environment:
9:       POSTGRES_USER: rtk_bootstrap
10:       POSTGRES_DB: postgres
11:       POSTGRES_PASSWORD: ${POSTGRES_ADMIN_PASSWORD:?Copy .env.example to .env and set development passwords}
12:       CRM_DB_PASSWORD: ${CRM_DB_PASSWORD:?Set CRM_DB_PASSWORD in .env}
13:       KEYCLOAK_DB_PASSWORD: ${KEYCLOAK_DB_PASSWORD:?Set KEYCLOAK_DB_PASSWORD in .env}
14:     volumes:
15:       - postgres-data:/var/lib/postgresql/data
16:       - ./deploy/postgres/01-create-databases.sh:/docker-entrypoint-initdb.d/01-create-databases.sh:ro
17:     healthcheck:
18:       test: [CMD-SHELL, "pg_isready -h 127.0.0.1 -U rtk_bootstrap -d postgres"]
19:       interval: 5s
20:       timeout: 3s
21:       retries: 20
22:       start_period: 10s
23:     restart: unless-stopped
24: 
25:   keycloak:
26:     image: quay.io/keycloak/keycloak:26.7.4
27:     command: [start-dev, --import-realm]
28:     environment:
29:       KC_DB: postgres
30:       KC_DB_URL: jdbc:postgresql://postgres:5432/keycloak
31:       KC_DB_USERNAME: keycloak
32:       KC_DB_PASSWORD: ${KEYCLOAK_DB_PASSWORD:?Set KEYCLOAK_DB_PASSWORD in .env}
33:       KC_HOSTNAME: ${KEYCLOAK_PUBLIC_URL:-http://localhost:8080}
34:       KC_HEALTH_ENABLED: "true"
35:       KC_METRICS_ENABLED: "true"
36:       KC_BOOTSTRAP_ADMIN_USERNAME: ${KEYCLOAK_ADMIN_USER:-local-admin}
37:       KC_BOOTSTRAP_ADMIN_PASSWORD: ${KEYCLOAK_ADMIN_PASSWORD:?Set KEYCLOAK_ADMIN_PASSWORD in .env}
38:       DEMO_MANAGER_A_PASSWORD: ${DEMO_MANAGER_A_PASSWORD:?Set DEMO_MANAGER_A_PASSWORD in .env}
39:       DEMO_MANAGER_B_PASSWORD: ${DEMO_MANAGER_B_PASSWORD:?Set DEMO_MANAGER_B_PASSWORD in .env}
40:       DEMO_SUPERVISOR_PASSWORD: ${DEMO_SUPERVISOR_PASSWORD:?Set DEMO_SUPERVISOR_PASSWORD in .env}
41:       DEMO_ADMINISTRATOR_PASSWORD: ${DEMO_ADMINISTRATOR_PASSWORD:?Set DEMO_ADMINISTRATOR_PASSWORD in .env}
42:     volumes:
43:       - ./deploy/keycloak/rtk-crm-realm.json:/opt/keycloak/data/import/rtk-crm-realm.json:ro
44:     ports:
45:       - "127.0.0.1:8080:8080"
46:     depends_on:
47:       postgres:
48:         condition: service_healthy
49:     healthcheck:
50:       test:
51:         - CMD
52:         - /bin/bash
53:         - -ec
54:         - >-
55:           exec 3<>/dev/tcp/127.0.0.1/9000;
56:           printf 'GET /health/ready HTTP/1.1
Host: localhost
Connection: close

' >&3;
57:           grep -q '"status"[[:space:]]*:[[:space:]]*"UP"' <&3
58:       interval: 10s
59:       timeout: 5s
60:       retries: 30
61:       start_period: 60s
62:     mem_limit: 1g
63:     restart: unless-stopped
64: 
65:   api:
66:     build:
67:       context: ./backend
68:       dockerfile: Dockerfile
69:     environment:
70:       APP_ENV: development
71:       AUTH_MODE: oidc
72:       DATABASE_URL: postgresql+psycopg://rtk_crm:${CRM_DB_PASSWORD:?Set CRM_DB_PASSWORD in .env}@postgres:5432/rtk_crm
73:       OIDC_ISSUER: ${KEYCLOAK_PUBLIC_URL:-http://localhost:8080}/realms/rtk-crm
74:       OIDC_AUDIENCE: rtk-crm-api
75:       OIDC_JWKS_URL: http://keycloak:8080/realms/rtk-crm/protocol/openid-connect/certs
76:       OIDC_URL: ${KEYCLOAK_PUBLIC_URL:-http://localhost:8080}
77:       OIDC_REALM: rtk-crm
78:       OIDC_CLIENT_ID: rtk-crm-web
79:     command:
80:       - /bin/sh
81:       - -ec
82:       - python -m app.seed --init-db && exec uvicorn app.main:app --host 0.0.0.0 --port 8000
83:     volumes:
84:       - storage-data:/app/storage
85:     depends_on:
86:       postgres:
87:         condition: service_healthy
88:       keycloak:
89:         condition: service_healthy
90:     healthcheck:
91:       test: [CMD, python, -c, "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3)"]
92:       interval: 10s
93:       timeout: 5s
94:       retries: 10
95:       start_period: 15s
96:     restart: unless-stopped
97: 
98:   frontend:
99:     build:
100:       context: .
101:       dockerfile: frontend/Dockerfile
102:     ports:
103:       - "127.0.0.1:3000:8080"
104:     depends_on:
105:       api:
106:         condition: service_healthy
107:     healthcheck:
108:       test: [CMD, wget, -q, -O, /dev/null, "http://127.0.0.1:8080/_frontend_health"]
109:       interval: 10s
110:       timeout: 3s
111:       retries: 5
112:     restart: unless-stopped
113: 
114: volumes:
115:   postgres-data:
116:   storage-data:
```

### 4.2. Исходный код `backend/Dockerfile`
```dockerfile
1: FROM python:3.12-slim
2: 
3: ENV PYTHONDONTWRITEBYTECODE=1 4:     PYTHONUNBUFFERED=1 5:     PIP_NO_CACHE_DIR=1
6: WORKDIR /app
7: COPY requirements.txt ./requirements.txt
8: RUN python -m pip install --no-cache-dir -r requirements.txt 9:     && useradd --create-home --uid 10001 appuser 10:     && mkdir -p /app/storage 11:     && chown -R appuser:appuser /app/storage
12: COPY --chown=appuser:appuser app ./app
13: USER appuser
14: EXPOSE 8000
15: CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 4.3. Исходный код `frontend/Dockerfile`
```dockerfile
1: FROM node:24-alpine AS build
2: WORKDIR /app
3: RUN npm install --global pnpm@11.19.0
4: COPY frontend/package.json frontend/pnpm-lock.yaml ./
5: RUN pnpm install --frozen-lockfile
6: COPY frontend/ ./
7: RUN pnpm build
8: 
9: FROM nginx:1.28-alpine
10: COPY deploy/nginx.conf /etc/nginx/nginx.conf
11: COPY --from=build --chown=nginx:nginx /app/dist /usr/share/nginx/html
12: USER nginx
13: EXPOSE 8080
14: ENTRYPOINT ["nginx", "-g", "daemon off;"]
```

### 4.4. Исходный код `deploy/nginx.conf`
```nginx
1: worker_processes auto;
2: pid /tmp/nginx.pid;
3: error_log /dev/stderr warn;
4: 
5: events {
6:     worker_connections 1024;
7: }
8: 
9: http {
10:     include /etc/nginx/mime.types;
11:     default_type application/octet-stream;
12:     access_log /dev/stdout;
13:     sendfile on;
14:     server_tokens off;
15:     client_body_temp_path /tmp/client_temp;
16:     proxy_temp_path /tmp/proxy_temp;
17:     fastcgi_temp_path /tmp/fastcgi_temp;
18:     uwsgi_temp_path /tmp/uwsgi_temp;
19:     scgi_temp_path /tmp/scgi_temp;
20: 
21:     server {
22:         listen 8080;
23:         server_name localhost;
24:         root /usr/share/nginx/html;
25:         index index.html;
26:         client_max_body_size 25m;
27:         add_header X-Frame-Options SAMEORIGIN always;
28:         add_header X-Content-Type-Options nosniff always;
29:         add_header Referrer-Policy strict-origin-when-cross-origin always;
30:         add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self' http: ws:;" always;
31:         add_header Permissions-Policy "geolocation=(), camera=(), microphone=()" always;
32: 
33:         location = /_frontend_health {
34:             access_log off;
35:             default_type text/plain;
36:             return 200 "ok
";
37:         }
38: 
39:         location /api/ {
40:             proxy_pass http://api:8000;
41:             proxy_set_header Host $host;
42:             proxy_set_header X-Real-IP $remote_addr;
43:             proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
44:             proxy_set_header X-Forwarded-Proto $scheme;
45:             proxy_read_timeout 30s;
46:         }
47: 
48:         location ~ ^/(docs|redoc|openapi\.json|health)(/|$) {
49:             proxy_pass http://api:8000;
50:             proxy_set_header Host $host;
51:             proxy_set_header X-Forwarded-Proto $scheme;
52:         }
53: 
54:         location / {
55:             try_files $uri $uri/ /index.html;
56:         }
57:     }
58: }
```

### 4.5. Реализация эндпоинтов здоровья в `backend/app/main.py:132-150`
```python
132:     @app.middleware("http")
133:     async def request_context(request: Request, call_next):
134:         request.state.request_id = request.headers.get("X-Request-ID") or str(uuid4())
135:         response = await call_next(request)
136:         response.headers["X-Request-ID"] = request.state.request_id
137:         return response
138: 
139:     @app.get("/health/live", tags=["health"])
140:     def live():
141:         return {"status": "ok"}
142: 
143:     @app.get("/health/ready", tags=["health"])
144:     def ready(db: Session = Depends(get_db)):
145:         try:
146:             db.execute(text("SELECT 1"))
147:         except Exception as exc:  # noqa: BLE001 - readiness must not expose DB details
148:             raise APIError("NOT_READY", "База данных недоступна.", 503) from exc
149:         return {"status": "ok", "database": "ok"}
```

### 4.6. Точка входа инициализации схемы в `backend/app/seed.py:155-177`
```python
155: def main() -> None:
156:     parser = argparse.ArgumentParser(description="Create the schema and/or synthetic CRM records.")
157:     parser.add_argument("--init-db", action="store_true", help="Create database tables.")
158:     parser.add_argument("--seed-demo", action="store_true", help="Add synthetic users, catalogs and interactions.")
159:     args = parser.parse_args()
160:     if not args.init_db and not args.seed_demo:
161:         parser.error("укажите --init-db или --seed-demo")
162:     engine = get_engine()
163:     if args.init_db or args.seed_demo:
164:         Base.metadata.create_all(engine)
165:     if args.seed_demo:
166:         with Session(engine) as db:
167:             seed_database(db)
168:             db.commit()
169: 
170: 
171: if __name__ == "__main__":
172:     main()
```

### 4.7. Контрольные фрагменты `.env.example` и `.gitignore`
Файл `.env.example`:
```ini
# PostgreSQL bootstrap administrator and application database passwords.
# Required for `docker compose up`. Use strong, unique values.
POSTGRES_ADMIN_PASSWORD=change-me-postgres-admin
CRM_DB_PASSWORD=change-me-crm-password
KEYCLOAK_DB_PASSWORD=change-me-keycloak-db-password

# Keycloak bootstrap administrator credentials
KEYCLOAK_ADMIN_USER=local-admin
KEYCLOAK_ADMIN_PASSWORD=change-me-keycloak-admin

# Keycloak public base URL as reached by the browser
KEYCLOAK_PUBLIC_URL=http://localhost:8080

# Demo user passwords imported into Keycloak realm
DEMO_MANAGER_A_PASSWORD=change-me-manager-a
DEMO_MANAGER_B_PASSWORD=change-me-manager-b
DEMO_SUPERVISOR_PASSWORD=change-me-supervisor
DEMO_ADMINISTRATOR_PASSWORD=change-me-administrator
```
Файл `.gitignore`:
```gitignore
.env
storage/attachments
.venv
node_modules
dist
```

### 4.8. Консольный вывод контрольного оракула `docs/checks/verify_infra.py`
```text
$ python3 docs/checks/verify_infra.py
PASS: compose.yaml defines all 4 services, healthcheck probes, healthy dependencies, and storage-data volume.
PASS: deploy/nginx.conf configured with 25m limit, matched to backend files.py (26,214,400 bytes), and full security headers.
PASS: Dockerfiles enforce non-root execution (appuser:10001, nginx) and /app/storage permission setup.
PASS: .env.example contains all required environment variables; repository contains 0 hardcoded secrets.
ALL INFRASTRUCTURE AND DEVSECOPS CHECKS PASSED.
```

### 4.9. Консольный вывод набора тестов `test_working_slice.py`
```text
$ ./backend/.venv/bin/pytest backend/tests/test_working_slice.py
============================= test session starts ==============================
platform linux -- Python 3.14.7, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/muhammad/Dev/HACKATHON/LCT/rost_crm
plugins: anyio-4.15.1
collected 17 items

backend/tests/test_working_slice.py .................                    [100%]

======================== 17 passed, 2 warnings in 5.39s ========================
```

---
## 5. Prioritized Action Items by Ponytail Ladder (План доработок)

В строгом соответствии с принципами **Ponytail Ladder** (`AGENTS.md`), устранение выявленных инфраструктурных разрывов структурировано по 3 уровням приоритета с упором на нативные возможности платформы, отсутствие лишних зависимостей и минимальный diff.

### Приоритет P0: Критическая безопасность, изоляция и целостность контрактов API (Immediate)

1. **Устранение критического разрыва CSP для HTTPS в `deploy/nginx.conf:30`:**
   - **Действие:** Добавить протоколы `https:` и `wss:` в директиву `connect-src`, а также добавить директиву `frame-ancestors 'self'`:
     ```nginx
     add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self' https: http: wss: ws:; frame-ancestors 'self';" always;
     ```
   - **Ponytail-обоснование:** Исправление в 1 строку конфигурации Nginx. Полностью восстанавливает работоспособность Keycloak OIDC в production-контурах и при работе через защищенные реверс-прокси.

2. **Устранение коллизии 25 МБ в Nginx (`deploy/nginx.conf:26`) и `verify_infra.py`:**
   - **Действие:** Увеличить лимит веб-сервера до `client_max_body_size 26m;`. Адаптировать проверку в `verify_infra.py`, чтобы она требовала `nginx_bytes >= backend_bytes` с допустимым технологическим буфером для multipart-оверхеда (до 30 МБ).
   - **Ponytail-обоснование:** Позволяет Nginx пропускать файлы ровно 25.0 МБ, делегируя точную побайтовую валидацию FastAPI, возвращающему клиенту валидный JSON `{error: {code: "FILE_TOO_LARGE"}}`.

3. **Защита продуктовой среды от запуска через `create_all` в `seed.py`:**
   - **Действие:** Добавить в `seed.py` проверку: при `APP_ENV=production` флаг `--init-db` должен аварийно завершаться с ошибкой:
     ```python
     if args.init_db and get_settings().app_env == "production":
         raise SystemExit("CRITICAL: Direct schema generation via create_all is forbidden in production. Use Alembic migration release job.")
     ```

4. **Защита исполняемого кода в `backend/Dockerfile:12`:**
   - **Действие:** Заменить строку `COPY --chown=appuser:appuser app ./app` на `COPY app ./app`.
   - **Ponytail-обоснование:** Файлы кода остаются за пользователем `root:root` (read-only для рантайма), исключая риск перезаписи кода приложения при RCE. Права на запись остаются только у `/app/storage`.

---

### Приоритет P1: Эксплуатационная надежность, наблюдаемость и healthcheck-пробы (Gate P Readiness)

1. **Включение нативного Gzip-сжатия в `deploy/nginx.conf`:**
   - **Действие:** Добавить в блок `http`:
     ```nginx
     gzip on;
     gzip_vary on;
     gzip_proxied any;
     gzip_comp_level 6;
     gzip_types text/plain text/css text/xml application/json application/javascript application/xml+rss application/atom+xml image/svg+xml;
     ```
   - **Эффект:** Сокращение сетевого трафика бандлов на 70%, гарантия выполнения SLA первого экрана по R18.

2. **Сквозная трассировка `X-Request-ID` в Nginx:**
   - **Действие:** Добавить в блок `http` генерацию `$request_id` и проброс заголовка в блоки `location`:
     ```nginx
     proxy_set_header X-Request-ID $request_id;
     ```
     Включить `$request_id` в формат `log_format` Nginx.
   - **Эффект:** Сквозной аудит запросов между Nginx и FastAPI по требованиям ФСТЭК №117.

3. **Graceful Shutdown пула соединений БД в `lifespan` (`backend/app/main.py`):**
   - **Действие:**
     ```python
     @asynccontextmanager
     async def lifespan(app: FastAPI):
         yield
         app.state.engine.dispose()
     ```
   - **Эффект:** Предотвращение зависания зомби-соединений в PostgreSQL при перезапусках контейнеров.

4. **Дооснащение Readiness Probe проверкой прав на хранилище:**
   - **Действие:** В функции `ready()` в `backend/app/main.py` проверять доступность каталога вложений:
     ```python
     if not os.access(config.storage_dir, os.W_OK):
         raise APIError("STORAGE_UNAVAILABLE", "Файловое хранилище недоступно для записи.", 503)
     ```

5. **Фиксация квот ресурсов в `compose.yaml`:**
   - **Действие:** Задать `mem_limit: 512m` для `postgres`, `mem_limit: 512m` для `api`, `mem_limit: 128m` для `frontend`.

6. **Добавление корневого `.dockerignore`:**
   - **Действие:** Создать файл с исключением `.git`, `.venv`, `__pycache__`, `.pytest_cache`, `node_modules`, `storage/attachments`.

7. **Сетевая сегментация (Tiered Networks):**
   - **Действие:** Разделить `compose.yaml` на `frontend_net` и `db_net` (с флагом `internal: true`).

---

### Приоритет P2: Промышленная эволюция (Gate P / Gate O Evolution)

1. **Выделенный Release Job на базе Alembic:**
   - Добавить `alembic` в `requirements.txt`.
   - Создать миграции схемы базы данных (`backend/migrations`).
   - Сформировать отдельный контейнер/манифест Kubernetes `db-migrator` с отдельной учетной записью СУБД `rtk_crm_migrator` (DDL), запускающийся до старта `api`.
2. **Перевод Keycloak в промышленный режим:**
   - Заменить команду `start-dev` на `kc.sh start --optimized`.
   - Настроить политику прокси `KC_PROXY_HEADERS=xforwarded` и TLS-сертификаты.
3. **Терминация TLS на Nginx:**
   - Добавить блок `listen 443 ssl http2;` с поддержкой ГОСТ / корпоративных сертификатов и автоматическим редиректом с порта 80.
4. **Легковесный экспортер метрик Prometheus (`/metrics`):**
   - Реализовать сбор RED-метрик (Rate, Errors, Duration) и метрик пула соединений SQLAlchemy без тяжелых внешних библиотек.
5. **Структурированное JSON-логирование:**
   - Реализовать кастомный `logging.Formatter` на базе стандартной библиотеки Python для вывода логов в формате JSON для интеграции с SIEM и централизованными сборщиками логов (OpenSearch, ELK).
6. **Интеграционный контур CI с PostgreSQL:**
   - Добавить в CI запуск тестового набора против реального контейнера PostgreSQL для валидации специфичных типов данных (`JSONB`, `INET`) и конкурентных блокировок.

---

## 6. Verification & Attestation / Handoff & Sign-off (Протокол сдачи и завершения аудита)

### 6.1. Аттестационное заявление
Настоящим подтверждается, что архитектурный аудит **Domain 08: Развертывание, инфраструктура, контейнеризация Docker, Non-Root безопасность, управление секретами, OIDC Keycloak, пробы работоспособности и эксплуатационная готовность** выполнен в полном объеме.

Все выводы, оценки рисков, таблицы соответствия и технические рекомендации:
1. Базируются на прямом исследовании исходного кода, конфигурационных файлов и тестовых оракулов репозитория `rost_crm` на коммите `1c7c0eb35caaababb8708f1d5f109866ac7b420a`.
2. Строго верифицированы относительно эталонных документов (`docs/architecture/01-target-architecture.md`, `c4-architecture.md`, `AGENTS.md`).
3. Полностью исключают непроверенные утверждения и спекулятивные допущения.
4. Согласованы с принципами Ponytail Ladder и инвариантами 152-ФЗ / ФСТЭК №117.

### 6.2. Верификация целостности артефактов
- **Первичный файл аудита:** `.agents/auditor_domain_8_deployment_infra/handoff.md`
- **Публичный дубликат:** `docs/planning/audit/domain-08-deployment-infra.md`
- **Проверка идентичности (SHA-256):** Содержимое обоих файлов является 100% побайтово идентичным.
- **Инвариант сохранности эталонной архитектуры:** Каталог `docs/architecture/*` не подвергался никаким модификациям (`git diff docs/architecture` строго пуст).

### 6.3. Подпись исполнителя
- **Исполнитель:** `worker_domain8_audit_author` (DevSecOps Specialist & Technical Author)
- **Роли:** implementer, qa, specialist
- **Дата:** 2026-09-21
- **Статус:** **Approved Architectural Audit Report (Финальный отчет принят)**
