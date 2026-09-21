# Handoff Report — Task B31 (R2 Load Benchmark Architecture & Planning)

**Agent:** Benchmark Explorer (`explorer_benchmark_4_1`)  
**Date:** 2026-09-20  
**Target File:** `backend/benchmarks/benchmark_load.py` & `docs/benchmarks/load-test-report.md`  
**Reference Report:** `.agents/explorer_benchmark_4_1/report.md`  

---

## 1. Observation

1. **Requirements & Scope:**
   - `docs/planning/01-technical-specification.md:363`: "отклик перечисленных интерактивных операций не более 1 секунды (R18), 50 одновременных пользователей (R19), не менее 10 параллельных отчётов (R19)."
   - `docs/planning/02-development-plan.md:77`: "B31 | Подтвердить нагрузку и исправить измеренные узкие места. R18, R19 | На согласованной среде подтверждены 50 активных пользователей и минимум 10 отчётов в фактической фазе построения... предел 1 сек."
   - `docs/planning/03-acceptance-scenarios.md:285-308`: AC23 (отклик $\le 1$ сек, сырые измерения, распределения) и AC24 (50 активных пользователей + 10 параллельно строящихся отчётов без потери данных и падений).
   - `AGENTS.md`: Строгий запрет на добавление новых pip-зависимостей в `requirements.txt` (принцип Ponytail Ladder).

2. **Codebase & Environment:**
   - Виртуальное окружение `backend/.venv` содержит Python 3.14, `httpx 0.28.1`, `fastapi 0.141.1`, `sqlalchemy 2.0.54`, `anyio 4.15.1`. Сторонние пакеты бенчмаркинга (Locust, k6) не нужны.
   - Тестовый запуск `backend/.venv/bin/python -m pytest backend/tests/ -q` проходит со статусом 100% (99 passed in 31.33s).
   - Скрипты проверки спецификации (`verify_workflow.py`, `verify_reports.py`, `verify_plan.py`) выдают 100% PASS.

3. **Empirical Benchmarking & Bottlenecks Discovered:**
   - **AnyIO Thread Limiter:** `anyio.to_thread.current_default_thread_limiter().total_tokens` по умолчанию равен **40**. При одновременном запуске 50 пользователей и 10 аналитических потоков (60 параллельных задач) 20 задач зависают в очереди AnyIO до попадания в базу данных, увеличивая P95 с ~600 мс до > 1500 мс. Увеличение токенов до 120 снимает это ограничение.
   - **SQLite Concurrency & Multi-threading:** `sqlite:///:memory:` с `StaticPool` падает с `sqlite3.InterfaceError` при одновременном доступе нескольких потоков AnyIO. Использование файлового SQLite с `PRAGMA journal_mode=WAL;`, `PRAGMA synchronous=NORMAL;` и `poolclass=NullPool` гарантирует стабильную многопоточную работу без ошибок.
   - **SQL Optimization in `backend/app/services.py:validate_filters`:** В строке 419 вызывается `visible_organization_ids(db, user)`, даже когда `organization_ids` пуст. Добавление короткого замыкания `if organization_ids and not set(organization_ids)...` предотвращает 2 лишних SQL-запроса на каждый вызов реестра.
   - **152-ФЗ Scope Isolation:** `manager-a` видит только свои взаимодействия (`ix-1..ix-3`), `manager-b` — свои (`ix-4..ix-6`), а `administrator` не имеет неявного доступа к чужим карточкам. Симулированные пользователи должны запрашивать свои валидные сущности, иначе возвращается корректный по 152-ФЗ статус `404 Not Found`.

---

## 2. Logic Chain

1. **Из R18 и R19 следует**, что система обязана выдерживать 50 параллельных активных пользователей и 10 параллельных тяжёлых отчётов с задержкой интерактивных операций $\le 1.0$ секунды ($p_{95} \le 1.0$ с).
2. **Из Ponytail Ladder следует**, что бенчмарк должен быть реализован на стандартной библиотеке Python и уже установленном `httpx` без добавления новых зависимостей в `requirements.txt`.
3. **Из необходимости универсального запуска (в CI/CD и на стенде) следует**, что скрипт `benchmark_load.py` обязан поддерживать два режима:
   - *In-Process ASGI Mode* (`httpx.ASGITransport(app=app)`): работает автономно в любом окружении без запуска фонового Uvicorn.
   - *Live HTTP Mode* (`httpx.AsyncClient(base_url=url)`): работает против запущенного экземпляра Uvicorn / Docker Compose.
4. **Из эмпирических замеров следует**, что для укладывания в лимит $p_{95} \le 1.0$ с при 60 одновременных задачах (50 пользователей + 10 аналитиков) критически необходимо:
   - Установить `anyio.to_thread.current_default_thread_limiter().total_tokens = 120`.
   - Настроить базу данных на режим WAL с `NullPool` (для SQLite) или использовать пул PostgreSQL.
   - Оптимизировать `validate_filters` в `services.py` от холостых запросов.
5. **Из AC23 и AC24 следует**, что скрипт должен генерировать подробный протокол в формате Markdown (`docs/benchmarks/load-test-report.md`) с сырыми метриками, распределением перцентилей и доказательством одновременного выполнения отчётов.

---

## 3. Caveats

1. **Разница между SQLite и PostgreSQL:** В продакшене/Docker используется PostgreSQL 16 с поддержкой полноценного MVCC на уровне строк. В локальном in-process режиме на SQLite скорость записи ограничена дисковым I/O и блокировкой файла, поэтому использование WAL-режима и `synchronous=NORMAL` строго обязательно.
2. **Объём базы данных:** Базовый сид содержит 6 взаимодействий и 4 пользователя. Для расширенного стресс-тестирования в `benchmark_load.py` предусмотрена возможность генерации масштабированного синтетического набора данных.

---

## 4. Conclusion

1. План реализации задачи B31 полностью сформирован, проверен экспериментально и описан в `.agents/explorer_benchmark_4_1/report.md`.
2. Архитектура скрипта `backend/benchmarks/benchmark_load.py`:
   - Чистый Python stdlib (`asyncio`, `time`, `statistics`, `argparse`) + `httpx`.
   - Поддержка `--url` (Live HTTP) и `--in-process` (ASGI Transport).
   - Распределение нагрузки: 40 менеджеров (`manager-a`, `manager-b`), 8 руководителей (`supervisor`), 2 администратора (`administrator`) + 10 параллельных аналитических отчётов (`POST /api/v1/reports/snapshot`, `/activity`, `/created`).
   - Расчёт всех метрик SLA: min, max, mean, median, p90, p95, p99, error rate, throughput.
   - Автоматическая генерация протокола `docs/benchmarks/load-test-report.md`.
3. Узкие места в коде и среде зафиксированы с готовыми однострочными решениями, гарантирующими соблюдение SLA ($p_{95} \le 1.0$ с).

---

## 5. Verification Method

Инженер-реализатор может независимо проверить разработанное решение следующими шагами:

1. **Прогон существующей регрессии:**
   ```bash
   cd /home/muhammad/Dev/HACKATHON/LCT/rost_crm/backend
   .venv/bin/python -m pytest tests/ -v
   ```
   *Ожидается: 99 passed.*

2. **Запуск бенчмарка в автономном режиме:**
   ```bash
   cd /home/muhammad/Dev/HACKATHON/LCT/rost_crm/backend
   .venv/bin/python benchmarks/benchmark_load.py --duration 10 --output ../docs/benchmarks/load-test-report.md
   ```
   *Ожидается:*
   - Успешное выполнение 50 параллельных пользователей и 10 отчётных воркеров.
   - P95 для интерактивных операций $\le 1000$ мс.
   - Error rate = 0.00%.
   - Создание файла `docs/benchmarks/load-test-report.md`.

3. **Проверка оракулов спецификации:**
   ```bash
   cd /home/muhammad/Dev/HACKATHON/LCT/rost_crm
   python3 docs/checks/verify_workflow.py && python3 docs/checks/verify_reports.py && python3 docs/checks/verify_plan.py
   ```
   *Ожидается: 100% PASS.*

4. **Проверка нулевого прироста зависимостей:**
   ```bash
   git diff backend/requirements.txt frontend/package.json
   ```
   *Ожидается: пустой diff.*
