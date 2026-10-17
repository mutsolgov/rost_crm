# Mock-сервисы LMS и Веб-портала ИТ Школы РТК

Комплексное руководство по развертыванию, тестированию и интеграции тестовых микросервисов **LMS ИТ Школы РТК (Zion / Moodle)** и **Веб-сайта (Образовательный портал ИТ Школы)** для CRM «ИТ Школа Ростелекома».

---

## 1. Архитектура и назначение

В рамках чемпионата хакатона CRM интегрируется с двумя внешними информационными системами:
1. **LMS ИТ Школы РТК (LMS Zion / Moodle)** — поставщик образовательных метрик (прогресс, посещаемость, завершение курсов), реестра когорт и слушателей.
2. **Веб-сайт ИТ Школы РТК (Образовательный портал / Laravel)** — источник входящих заявок на обучение и партнерских обращений от организаций.

### Данные организаторов хакатона
Микросервисы инициализируются реальными данными организаторов, извлеченными скриптом `mock_services/seed.py`:
- `данные предоставленные организаторами/Загрузка пользователей.xlsx` — 5 реальных слушателей курсов (Черепанова С.В., Кричанов М.С., Григорьев С.С., Осипенко И.В., Иванов М.П.) с паспортными данными, СНИЛС и образовательными статусами.
- `данные предоставленные организаторами/Данные оплат.json` — 5 реальных оплаченных заказов (`ORD-20260313051569-OYJRVN`, `ORD-202605130654453-GDJIKG`, `ORD-20261721184559-AJIJEN`, `ORD-20260522061330-2LT0MG`, `ORD-20260904075403-ZXFSZX`) с потоками и суммами.
- `данные предоставленные организаторами/Вендоры.xlsx` — партнерские компании (ПАО «Ростелеком», ООО «Базис», ООО «ТДата», ООО «РТК ИТ Плюс», ООО «РТК ИТ») и их контактные лица.

### Принципы реализации
- **Zero External Dependencies**: Реализация микросервисов выполнена строго на **стандартной библиотеке Python 3** (`http.server`, `urllib.request`, `json`, `datetime`) — 0 сторонних зависимостей.
- **Ultra-lightweight Docker**: Минималистичные образы на базе `python:3.12-alpine`.
- **Zero-Code Switchover**: Полная поддержка мгновенного переключения CRM между мок-контейнерами, оффлайн-файлами и боевыми серверами организаторов исключительно через конфигурацию `.env`.

---

## 2. Быстрый старт через Docker

Оба сервиса оркестрируются файлом `mock_services/docker-compose.mock.yaml`.

### Запуск контейнеров
Выполните команду из корня репозитория:
```bash
docker compose -f mock_services/docker-compose.mock.yaml up -d --build
```

### Проверка статуса сервисов
```bash
docker compose -f mock_services/docker-compose.mock.yaml ps
```
Вывод:
```
NAME               IMAGE                     COMMAND                  SERVICE        CREATED         STATUS         PORTS
rtk-mock-lms       mock_services-mock-lms    "python -u app.py"       mock-lms       1 minute ago    Up 1 minute    0.0.0.0:8081->8081/tcp
rtk-mock-website   mock_services-mock-website "python -u app.py"      mock-website   1 minute ago    Up 1 minute    0.0.0.0:8082->8082/tcp
```

### Просмотр журналов
```bash
docker compose -f mock_services/docker-compose.mock.yaml logs -f
```

### Остановка сервисов
```bash
docker compose -f mock_services/docker-compose.mock.yaml down
```

---

## 3. Запуск без Docker (локально через Python)

Микросервисы можно запускать напрямую в локальном окружении Python (требуется Python 3.10+):

### Запуск LMS Mock Service (порт 8081):
```bash
python mock_services/lms/app.py --port 8081
```
Или с указанием переменных окружения:
```bash
PORT=8081 CRM_API_URL=http://localhost:8000 LMS_WEBHOOK_SECRET=rtk-lms-webhook-secret python mock_services/lms/app.py
```

### Запуск Website Mock Service (порт 8082):
```bash
python mock_services/website/app.py --port 8082
```
Или с указанием переменных окружения:
```bash
PORT=8082 CRM_API_URL=http://localhost:8000 WEBSITE_WEBHOOK_SECRET=rtk-website-webhook-secret python mock_services/website/app.py
```

### Параметры конфигурации сервисов
| Переменная | По умолчанию | Описание |
|---|---|---|
| `PORT` | 8081 (LMS) / 8082 (Website) | Порт прослушивания HTTP |
| `HOST` | `0.0.0.0` | Сетевой интерфейс привязки |
| `CRM_API_URL` | `http://localhost:8000` | Базовый URL CRM API для отправки вебхуков |
| `LMS_WEBHOOK_SECRET` | `rtk-lms-webhook-secret` | Секрет аутентификации вебхуков LMS (`X-Webhook-Secret`) |
| `WEBSITE_WEBHOOK_SECRET` | `rtk-website-webhook-secret` | Секрет аутентификации вебхуков Website (`X-Webhook-Secret`) |
| `SEED_DATA_PATH` | `./seed_data.json` | Путь к файлу исходных данных |

---

## 4. Перегенерация данных (`seed.py`)

Для повторного извлечения и нормализации данных из каталога `данные предоставленные организаторами/` запустите генератор:
```bash
python mock_services/seed.py
```
Скрипт использует исключительно стандартную библиотеку Python (`zipfile` и `xml.etree.ElementTree` для парсинга XLSX без `openpyxl`/`pandas`) и генерирует:
- `mock_services/lms/seed_data.json` — слушатели, когорты и метрики курсов.
- `mock_services/website/seed_data.json` — заявки и профили партнеров.

---

## 5. Спецификация API и curl-примеры

### 5.1. LMS Mock Service (порт 8081)

#### 1. Проверка работоспособности: `GET /api/v1/health`
```bash
curl -s http://127.0.0.1:8081/api/v1/health | jq .
```
Пример ответа (HTTP 200 OK):
```json
{
  "status": "ok",
  "healthy": true,
  "service": "rtk-lms-zion",
  "version": "1.4.0",
  "timestamp": "2026-10-07T12:00:00.000000+00:00",
  "learners_count": 5,
  "cohorts_count": 4
}
```

#### 2. Получение всех метрик обучения: `GET /api/v1/metrics`
```bash
curl -s http://127.0.0.1:8081/api/v1/metrics | jq .
```
Пример ответа (HTTP 200 OK):
```json
{
  "status": "ok",
  "items": [
    {
      "external_id": "zion-metric-org-1-devops-active_cohorts",
      "organization_id": "org-1",
      "program_id": "program-devops",
      "metric_code": "active_cohorts",
      "value": 4.0,
      "unit": "cohort",
      "as_of": "2026-10-07T10:00:00Z",
      "source_revision": "1"
    },
    {
      "external_id": "zion-metric-org-1-devops-attendance_rate",
      "organization_id": "org-1",
      "program_id": "program-devops",
      "metric_code": "attendance_rate",
      "value": 92.5,
      "unit": "percent",
      "as_of": "2026-10-07T10:00:00Z",
      "source_revision": "1"
    }
  ]
}
```

#### 3. Фильтрация метрик по дате: `GET /api/v1/metrics?since=...`
```bash
curl -s "http://127.0.0.1:8081/api/v1/metrics?since=2026-10-07T10:30:00Z" | jq .
```
Возвращаются только записи с датой `as_of >= since`.

#### 4. Реестр слушателей организаторов: `GET /api/v1/learners`
```bash
curl -s http://127.0.0.1:8081/api/v1/learners | jq .
```
Пример ответа (HTTP 200 OK):
```json
{
  "status": "ok",
  "total": 5,
  "items": [
    {
      "learner_id": "LNR-001",
      "full_name": "Черепанова Светлана Васильевна",
      "email": "cherepanona.s@test.ru",
      "phone": "+7 (999) 023-43-65",
      "course": "Анализ данных без программирования",
      "cohort": 1,
      "status": "enrolled",
      "progress_percent": 85.0
    }
  ]
}
```

#### 5. Симуляция отправки вебхука в CRM: `POST /api/v1/simulate/webhook`
Отправляет событие по сети на `${CRM_API_URL}/api/v1/webhooks/lms` с заголовком `X-Webhook-Secret`.
```bash
curl -s -X POST http://127.0.0.1:8081/api/v1/simulate/webhook \
  -H "Content-Type: application/json" \
  -d '{"metric_code": "attendance_rate", "value": 95.0, "program_id": "program-devops"}' | jq .
```
Пример ответа (HTTP 200 OK):
```json
{
  "status": "ok",
  "delivered": true,
  "details": {
    "target": "http://localhost:8000/api/v1/webhooks/lms",
    "status_code": 200,
    "response": "{\"status\":\"ok\",\"processed\":1,\"skipped\":0}"
  }
}
```

---

### 5.2. Website Mock Service (порт 8082)

#### 1. Проверка работоспособности: `GET /api/health`
> **ВАЖНО**: Эндпоинт проверки портала строго `/api/health` (**БЕЗ `/v1`**), в точном соответствии с контрактом `LiveWebsiteAdapter`!
```bash
curl -s http://127.0.0.1:8082/api/health | jq .
```
Пример ответа (HTTP 200 OK):
```json
{
  "status": "ok",
  "healthy": true,
  "service": "rtk-it-school-portal",
  "version": "2.1.0",
  "timestamp": "2026-10-07T12:00:00.000000+00:00",
  "total_applications": 5
}
```

#### 2. Список входящих заявок (заказов): `GET /api/v1/applications`
```bash
curl -s http://127.0.0.1:8082/api/v1/applications | jq .
```
Пример ответа (HTTP 200 OK):
```json
{
  "status": "ok",
  "items": [
    {
      "external_id": "ORD-20260313051569-OYJRVN",
      "order_number": "ORD-20260313051569-OYJRVN",
      "created_at": "2026-03-13T05:15:00Z",
      "organization_name": "ПАО «Ростелеком»",
      "representative_name": "Черепанова Светлана Васильевна",
      "representative_email": "cherepanona.s@test.ru",
      "representative_phone": "+7 (999) 023-43-65",
      "program_id": "program-data-analysis",
      "program_name": "Анализ данных без программирования",
      "cohort_id": "1",
      "status": "paid",
      "amount": 45000.0
    }
  ]
}
```

#### 3. Фильтрация заявок по дате создания: `GET /api/v1/applications?since=...`
```bash
curl -s "http://127.0.0.1:8082/api/v1/applications?since=2026-05-01T00:00:00Z" | jq .
```
Возвращаются только заявки с `created_at >= since`.

#### 4. Симуляция новой заявки и отправка вебхука: `POST /api/v1/simulate/application`
Добавляет новую заявку в память сервиса и передает вебхук на `${CRM_API_URL}/api/v1/webhooks/website` с заголовком `X-Webhook-Secret`.
```bash
curl -s -X POST http://127.0.0.1:8082/api/v1/simulate/application \
  -H "Content-Type: application/json" \
  -d '{
    "organization_name": "МГТУ им. Баумана",
    "representative_name": "Петров Петр Петрович",
    "representative_email": "petrov@bmstu.ru",
    "representative_phone": "+7 (999) 123-45-67",
    "program_name": "DevOps инженер"
  }' | jq .
```
Пример ответа (HTTP 200 OK):
```json
{
  "status": "ok",
  "delivered": true,
  "application": {
    "external_id": "ORD-20261007142035-A1B2C3",
    "organization_name": "МГТУ им. Баумана",
    "representative_name": "Петров Петр Петрович",
    "status": "submitted"
  }
}
```

---

## 6. Документация Zero-Code Switchover

Архитектура CRM поддерживает бесшовное переключение интеграционного контура **без перекомпиляции и без изменения программного кода CRM**. Выбор режима определяется переменными окружения в файле `.env`.

### 6.1. Матрица трех режимов интеграции

| Режим | Назначение | `LMS_INTEGRATION_MODE` | `LMS_BASE_URL` | `WEBSITE_INTEGRATION_MODE` | `WEBSITE_BASE_URL` |
|---|---|---|---|---|---|
| **Режим 1: Mock Containers** | Разработка, локальное тестирование, демо на данных организаторов | `live` | `http://127.0.0.1:8081` | `live` | `http://127.0.0.1:8082` |
| **Режим 2: Production Live** | Промышленная эксплуатация с боевыми порталами РТК | `live` | `https://lms.rt.ru/api` *(или https://rtkb.zion-lms.ru)* | `live` | `https://portal.rt.ru/api` *(или https://it-school.rt.ru)* |
| **Режим 3: Offline Mock File** | Автономная среда без внешних сетей (синтетические фикстуры) | `mock` | `https://rtkb.zion-lms.ru` | `mock` | `https://it-school.rt.ru` |

---

### 6.2. Пошаговые сценарии переключения

#### Сценарий 1: Переключение на Mock Containers (Dev / Demo)
1. Поднимите контейнеры мок-сервисов:
   ```bash
   docker compose -f mock_services/docker-compose.mock.yaml up -d --build
   ```
2. Установите в `.env`:
   ```ini
   LMS_INTEGRATION_MODE=live
   LMS_BASE_URL=http://127.0.0.1:8081
   LMS_API_TOKEN=mock-lms-token
   LMS_WEBHOOK_SECRET=rtk-lms-webhook-secret

   WEBSITE_INTEGRATION_MODE=live
   WEBSITE_BASE_URL=http://127.0.0.1:8082
   WEBSITE_API_TOKEN=mock-website-token
   WEBSITE_WEBHOOK_SECRET=rtk-website-webhook-secret
   ```
3. Перезапустите CRM бэкенд (или контейнер `api`).
4. Проверьте статус подключения через API:
   ```bash
   curl -s http://localhost:8000/api/v1/integrations/status -H "X-Demo-User: supervisor" | jq .
   ```
   Оба адаптера отобразят `"status": "ok"`, `"connected": true`, `"mode": "live"`.

#### Сценарий 2: Переключение на боевые серверы организаторов (Production Live)
1. Остановите локальные контейнеры мок-сервисов:
   ```bash
   docker compose -f mock_services/docker-compose.mock.yaml down
   ```
2. Обновите параметры в `.env`:
   ```ini
   LMS_INTEGRATION_MODE=live
   LMS_BASE_URL=https://lms.rt.ru/api
   LMS_API_TOKEN=prod-secret-lms-bearer-token
   LMS_WEBHOOK_SECRET=prod-lms-hmac-secret

   WEBSITE_INTEGRATION_MODE=live
   WEBSITE_BASE_URL=https://portal.rt.ru/api
   WEBSITE_API_TOKEN=prod-secret-website-bearer-token
   WEBSITE_WEBHOOK_SECRET=prod-website-hmac-secret
   ```
3. Перезапустите бэкенд CRM. Запросы автоматически направятся в боевые системы.

#### Сценарий 3: Возврат в автономный режим (Offline / Mock File Mode)
1. Установите в `.env`:
   ```ini
   LMS_INTEGRATION_MODE=mock
   WEBSITE_INTEGRATION_MODE=mock
   ```
2. CRM переключится на встроенные фикстуры без единого исходящего сетевого вызова.

---

## 7. Обработка данных и Reconciliation Inbox в CRM

При работе в режиме Live CRM выполняет полный цикл безопасной обработки интеграционных событий:
1. **Deduplication Key**: Каждое событие проверяется по уникальному составному ключу `(source, entity_type, external_id, source_revision)`. Дубликаты отсекаются с кодом 200 (`skipped: 1`) без ошибок базы данных.
2. **Reconciliation Queue**: Заявки с сайта попадают в таблицу `integration_inbox` со статусом `pending` и сопоставляются с организациями по алгоритму нечеткого поиска (fuzzy matching).
3. **Разрешение оператором**: Руководитель или администратор подтверждает заявку через UI или эндпоинт `POST /api/v1/integrations/inbox/{id}/resolve` с созданием взаимодействия в воронке.
4. **Криптографическая защита**: Вебхуки верифицируются через заголовок `X-Webhook-Secret` либо HMAC-SHA256 подпись `X-Signature-SHA256` за константное время `hmac.compare_digest`.
