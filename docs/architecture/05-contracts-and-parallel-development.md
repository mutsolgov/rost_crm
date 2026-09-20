# Контракты модулей и правила параллельной разработки

Версия проектных контрактов: `architecture-v1`, 19.09.2026. Это спецификация будущих интерфейсов. Ниже не утверждается, что маршруты и классы уже реализованы. Начальные C01–C07 из roadmap детализированы здесь; конкретные DTO превращаются в Pydantic/OpenAPI в TD01–TD03.

## 1. Один источник контракта

HTTP: Pydantic request/response → FastAPI OpenAPI → сохранённый `contracts/openapi.json` → generated TypeScript → mocks/contract fixtures. Не поддерживать вручную независимые определения одинакового DTO в Python и `frontend/src/types.ts`. Пока генератор не подключён, примеры этого документа являются временным согласованным контрактом, а не отдельным сервером.

Domain ports: Python Protocol + DTO в `backend/app/contracts`; владелец предоставляет fake с теми же ошибками. События: `event_type + schema_version`, JSON Schema в `contracts/events`. Событие описывает произошедший факт; command просит совершить действие. Worker payload содержит ID, версию и контекст инициатора, а не ORM instance/JWT.

Изменение согласуется через небольшой PR: request/response/examples/error diff, смысл полей, влияние на БД и consumer. Backward-compatible optional fields добавляются в v1; переименование/смена значения — новая версия и compatibility adapter. Не создавать общий giant PR на оба модуля. Generated files пересоздаются командой, не редактируются двумя участниками вручную.

## 2. Общие транспортные правила

| Область | Контракт |
|---|---|
| URL | Существующий `/api/v1` сохраняется; URL ниже относительно этого префикса |
| IDs | Непрозрачные строки. Новые сущности генерируют UUID, существующие `manager-a`/другие legacy IDs не массово переименовываются. Публичный DTO не требует UUID для всех старых сущностей |
| Время | RFC3339 с timezone; хранение timestamptz UTC. Date для подписания/окончания лицензии, без выдуманного времени суток. Диапазоны `[from,to)` |
| Write | `Idempotency-Key` обязателен для POST-команд, upload/confirm/publish/export/cancel. PATCH/PUT также принимают ключ при наличии бизнес-эффекта. `expected_revision` для изменения существующего aggregate. Read-only POST `/report-query` не является командой и ключа не требует |
| Idempotency | Область `(principal_id, operation с target_id, key)`, hash канонического validated body. Тот же ключ/тело — прежний результат после повторной проверки ACL; иное тело — 409 |
| Revision | bigint >0, изменяется сервером. 409 сообщает безопасную текущую revision, клиент перечитывает ресурс и сохраняет ввод |
| Списки | bounded `limit` (проектно 50, max 200) и opaque cursor для новых больших реестров. Старый page/page_size сохраняется до миграции потребителя. Сортировка всегда с ID tie-breaker |
| Фильтры | AND между категориями, OR внутри списка ID; пустой массив = без ограничения по этой категории, но никогда не «все вне scope» |
| Optional | Поле отсутствует = не менять. `null` очищает только явно nullable поле. Пустая строка не автоматически очищает FK |
| Cache | `Cache-Control: private, no-store` для чувствительных ответов; browser query-cache управляется приложением и очищается при смене identity |
| Async | `202 + job_id + resource_id/status_url`. Не выдавать «успешно сформирован» до `succeeded` |
| Correlation | `X-Request-ID` ответа и `request_id` ошибки; server-generated ID при отсутствии/недопустимом входе. Логи/события/jobs связываются через correlation_id |

Проектное окно replay пользовательских команд — 7 дней; сервер публикует политику. Удаление command_result после окна не снимает предметные unique keys и отдельную бессрочность до retention для внешнего inbox/delivery. Повтор старой команды после окна не обещает восстановить прежний HTTP response; UI не переиспользует ключ нового намерения.

Пример ошибки (сообщение адаптируется для пользователя, code стабилен):

```json
{
  "error": {
    "code": "REVISION_CONFLICT",
    "message": "Карточка уже изменена. Обновите данные и повторите действие.",
    "request_id": "req-04d93e",
    "details": {"current_revision": 8},
    "field_errors": []
  }
}
```

| HTTP | Коды | Поведение UI/worker |
|---|---|---|
| 401 | `UNAUTHENTICATED`, `SESSION_EXPIRED` | Одно контролируемое refresh, затем вход; не бесконечный retry |
| 403 | `FORBIDDEN`, `USER_DISABLED` | Понятный отказ действию, без предложения обойти ограничения |
| 404 | `NOT_FOUND` | Недоступный ресурс не раскрывает существование |
| 409 | `REVISION_CONFLICT`, `IDEMPOTENCY_CONFLICT`, `IMPORT_PREVIEW_STALE`, `WORKFLOW_VERSION_CONFLICT`, `SOURCE_REVISION_CONFLICT`, `REPORT_SCOPE_CHANGED` | Не повторять автоматически с новым ключом; показать конфликт и перечитать |
| 413 | `FILE_TOO_LARGE`, `IMPORT_BATCH_TOO_LARGE` | Показать согласованный лимит и допустимый следующий шаг |
| 415 | `FILE_TYPE_UNSUPPORTED`, `FILE_SIGNATURE_MISMATCH` | Сохранить контекст, предложить выбрать подходящий файл |
| 422 | `VALIDATION_ERROR`, `WORKFLOW_GRAPH_INVALID`, `TRANSITION_NOT_ALLOWED`, `REPORT_PARAMETER_INVALID` | Привязать причины к полям/графу; входящие malformed JSON тоже нормализуются |
| 423 | `FILE_QUARANTINED` | Доступ закрыт до проверки; не ретраить скачивание в цикле |
| 429 | `RATE_LIMITED` | `Retry-After`, bounded backoff |
| 503 | `DEPENDENCY_UNAVAILABLE` | Контролируемый повтор с тем же ключом; проверить не завершилась ли команда |
| 500 | `INTERNAL_ERROR` | Без traceback/SQL/секрета пользователю, ссылка на request_id |

Error codes первого среза совместимы через adapter. Переименование старого кода — изменение контракта, а не косметическая правка. Дополнительные предметные коды модуль объявляет в OpenAPI/fixtures.

## 3. C01: actor, policy и UnitOfWork — A

```text
ActorContext {
  principal_id, user_id?, kind: user|service,
  permissions: set[str], authz_revision, correlation_id
}
AccessPolicy.require(actor, action, resource_ref, uow) -> None | DomainError
AccessPolicy.interaction_scope(actor, action, uow) -> SQL predicate
AccessPolicy.organization_scope(actor, action, uow) -> SQL predicate
UnitOfWork { session, commit(), rollback() }
```

Scope вычисляется в актуальной БД, не присылается доверенным JSON клиента. Actor в очереди — ссылка на principal; permissions пересчитываются при исполнении. Технический service worker выполняет разрешённый тип работы, но не присваивает пользователю все права.

Обычная application command открывает транзакцию. Для импорта/интеграции доступны internal команды `apply_in_uow(...)`, которые **не commit** сами; orchestrator владеет одной атомарной границей. Оба пути используют одни domain validators/policy/events. Error/failed diagnostics после rollback сохраняет отдельная служебная транзакция без объявления бизнес-успеха.

Границы доступа к каталогам: видимое название учреждения для фильтра ≠ разрешение редактировать контакты/договоры. `GET /me` возвращает permissions и authz revision; `GET /interactions/{id}` — `allowed_actions`/`allowed_transitions`. UI использует их для доступности кнопок, API повторяет проверку всегда.

## 4. C02: каталоги и команды предметного ядра — A → B

```text
CatalogQueries.get_catalogs(actor, filters, page)
CatalogCommands.create/update/archive_organization(actor, dto, key, uow?)
CatalogCommands.apply_catalog_change(actor, normalized_change, expected_revisions, uow)
OrganizationAssignmentCommands.assign/unassign(actor, organization_id, user_id?, reason, expected_revision, key)
InteractionCommands.create(actor, dto, key, uow?)
InteractionCommands.transition(actor, interaction_id, dto, key, uow?)
InteractionCommands.add_comment / assign / update_subject(...)
LearningFactCommands.apply(actor, canonical_fact, source_ref, uow)
```

Импорт B вызывает `CatalogCommands`/`InteractionCommands`/`LearningFactCommands`, не вставляет чужие ORM-строки. Данные из LMS A идут через те же команды. A поставляет в fixtures валидный и невалидный объект, CAS conflict, lost access и повторный key; B может закончить staging/UI без готового adapter LMS.

Основные маршруты (точные DTO утверждаются в TD01, endpoint coverage проверяется TD36):

| Ресурс | Read | Команды | Владелец |
|---|---|---|---|
| Учреждения | `/organizations`, `/{id}`, `/{id}/contacts`, `/{id}/assignments` | create/update/archive; contacts create/update/archive; assignments assign/unassign | A |
| Справочники | `/directions`, `/programs`, `/products`, `/vendors` | create/update/archive; program-product associations | A |
| Документы | `/organizations/{id}/contracts`, `/licenses`, `/deliveries` | create/update/archive, факт передачи, typed attachment link | A |
| Команды/пользователи | `/teams`, `/users`, `/permissions`, `/access-grants` | команды, membership preview/apply, grants, local enable/disable | A |
| Карточки | `/interactions`, `/{id}`, `/{id}/history`, `/{id}/visits` | create, update, transitions, comments, assignments, subject update | A |
| Контроль | `/dashboard`, `/interactions?overdue=true` | поля due date/control task в пределах выбранной модели | A |
| Учебные факты | `/learning/applications`, `/cohorts`, `/observations` | согласованные исправления с reason/source; ingestion internal port | A |

Не объявлять generic `DELETE` для истории и использованных версий. Archive сохраняет ссылки, запрещает новое использование при сохранении читабельности прошлых отчётов.

Новая команда перехода расширяет существующий `TransitionCommand` совместимо:

```json
{
  "transition_code": "documents_to_signing",
  "expected_revision": 7,
  "comment": "Комплект документов согласован.",
  "attachment_ids": ["a25de640-baf3-4934-abef-208c64d65eb1"]
}
```

`transition_code` в примере условный; фактический код берётся из `allowed_transitions` закреплённой версии. Вложение уже `clean`, принадлежит инициатору/доступному ресурсу, проходит проверку привязки. Источник комментария/файла — исходное посещение; событие перехода соединяет исходное и целевое. Новый статус не передаётся произвольно в PATCH.

Card DTO сохраняет существующие `state`, `state_name`, `workflow_version`, `revision`, дополнительно получает `workflow_version_id`, `state_key`, `current_visit_id`, `owning_team_id`, `owner_id: string|null`, `allowed_actions`, `allowed_transitions`. Новая nullable owner совместимость требует обновления consumer до снятия владельцев. Человек переводится между командами с preview; карточки переносятся отдельной командой, а не из-за неявного join текущего owner.team.

## 5. C03/C04: jobs и файлы — A → B

```text
JobService.enqueue(kind, payload_version, payload_ids, actor_ref, idempotency_key, uow) -> JobRef
JobService.request_cancel(actor, job_id, key) -> JobStatus
JobHandler.run(job_id, lease_token) -> persisted result
FileService.require_clean_linkable(actor, attachment_ids, target_ref, uow)
FileService.link_in_uow(actor, attachment_id, target_ref, uow)
StoragePort.put_stream / get_stream / stat / delete_version
```

Пример `GET /jobs/{id}`:

```json
{
  "id": "6c959de9-1ca9-42ef-a2a8-4bab03305d09",
  "kind": "report.materialize",
  "status": "running",
  "phase": "materializing",
  "processed_count": 400,
  "total_count": null,
  "cancel_requested": false,
  "result": null,
  "error": null
}
```

Единый enum jobs: `queued`, `running`, `retry_wait`, `succeeded`, `failed`, `cancelled`. `completed` может быть статусом import batch, но не вторым именем job success. Job list видит автор/уполномоченный оператор с текущим scope. B делает один `JobStatus` виджет для report/import/sync/scan/migration.

File API: `POST /attachments` multipart → pending scan; `GET /attachments/{id}`; `POST /interactions/{id}/attachments`; `GET /attachments/{id}/download`. Upload finalization не атомарна с объектным хранилищем: состояния `uploading/upload_failed/pending_scan/clean/infected/scan_error` плюс уборка временных объектов обязательны. Объект с ошибкой проверки остаётся в quarantine. Наличие байт в S3 не означает успешную привязку к карточке.

## 6. C05: редактируемый workflow — A → B

| Операция | Целевой контракт |
|---|---|
| Список/получение | `GET /workflow-templates`, `GET /workflow-templates/{id}/versions/{version_id}` |
| Создание draft | `POST /workflow-templates`, `POST /workflow-templates/{id}/versions` с `based_on_version_id?` |
| Изменение draft | `PUT /workflow-templates/{id}/versions/{version_id}` с graph и expected_revision |
| Валидация | `POST .../{version_id}/validate` → issues `{code,path,node_key?,transition_key?,message}` |
| Публикация | `POST .../{version_id}/publish` + expected_revision + key; immutable graph hash |
| Миграция | `POST /workflow-migrations/preview` → plan_id/hash/affected/conflicts; `POST /workflow-migrations/{id}/apply` → job |
| История переноса | `GET /workflow-migrations/{id}`, `/items` с применёнными/конфликтными карточками |

Структура graph содержит stable state keys, version-local labels, initial/terminal flags, transitions и разрешённые guards. Валидация: один initial, достижимость states, путь к terminal, отсутствие несуществующих концов ребра/дублирующих codes, guards по allowlist. Цикл допустим, если есть путь завершения; terminal не имеет обычного исходящего перехода. Draft может быть неполон, publish — нет.

B может сначала реализовать таблицу states/transitions и визуальное расположение; drag-and-drop — UI-представление той же схемы, не отдельный движок. Координаты узлов хранятся как display metadata, не меняют бизнес-семантику.

## 7. C06: исторический запрос, аналитика и отчёт — B → A

```text
HistoricalQuery.materialize(actor, report_request, cutoff, uow) -> FrozenDataset
AnalyticsQueries.calculate(actor, metric_definition_version, filters, uow) -> MetricDataset
ReportRenderer.render(frozen_rows, layout_version, locale) -> ArtifactBytes
ReportAccessPolicy.require_all_dependencies(actor, report_run_id, action)
```

Нельзя делать materialize из N независимых page requests к live REST API: так страницы будут отражать разные моменты БД. Read-port реализуется SQL-проекцией с согласованным snapshot. Canonical columns согласованы с моделью **одной** программы/продукта на взаимодействие: `organization_name`, `direction_name`, `program_name`, `product_name`, `state_name`, `owner_name`; обязательны nullable/«не определено». Multiselect в фильтре не делает строку many-to-many.

Параметры report request из [03](03-jobs-files-integrations-reports.md): `report_type`, `as_of` либо `from/to`, `as_of_inclusive`, `timezone`, `knowledge_cutoff?`, `filters` с organization/direction/program/product/owner/state, `columns`, `group_by`, `sort`. Статус задаётся ключом/версией либо согласованным semantic state mapping, а не совпадением переводимого label. Изменение фильтров = новый request/run; старый run неизменяем.

`POST /report-previews` создаёт frozen run/job; `GET /reports/{id}/rows/charts` и `POST /reports/{id}/exports` используют его. Для обычного интерактивного выбора `POST /report-query` выполняет read-only scoped query с bounded pagination/counts и возвращает `200 {rows,total,chart_summary?,query_fingerprint,observed_at,semantics_version,volatile:true}`; его отклик измеряется ≤1 секунды. Это текущая выборка, не сохранённый официальный отчёт. Экспорт доступен после materialization. Все форматы — XLS/XLSX/PDF/JSON, charts PNG/PDF — получают одинаковые данные/labels/definitions.

При создании сохраняются normalised scope descriptor и `authz_epoch` из PostgreSQL. Epoch транзакционно увеличивается при изменениях, влияющих на видимость: grants, membership, owner/owning_team, local active user. Если epoch изменился до materialization, задание получает `REPORT_SCOPE_CHANGED` и нужен новый запрос. Это консервативное правило не требует быстро сохранять сотни тысяч ID при приёме job и не допускает скрытого расширения/сокращения отчёта. Для небольшой команды пользователей допустима одна глобальная epoch; более адресное инвалидирование вводится при измеренной необходимости.

Перед публикацией/скачиванием проверяется **весь** сохранённый набор зависимостей run. Отозванная карточка/организация делает старый полный результат недоступным. Автоматически выдавать усечённый файл с прежним checksum/run_id нельзя: нужен новый run. Учебные агрегаты могут зависеть от organization без interaction, это отдельный typed scope item. Новые данные, пришедшие после запроса, отдельно ограничиваются cutoff/фактическим snapshot; epoch не заменяет временную семантику.

## 8. C07: источник и нормализованные факты — A → B

```text
SourceAdapter.check_connection()
SourceAdapter.fetch_page(cursor, watermark, limit) -> SourcePage
SourceAdapter.normalize(raw_record) -> CanonicalEnvelope
SourceAdapter.compare_revision(previous, incoming) -> older|equal|newer|unknown
CanonicalEnvelope {
  schema_version, source_id, entity_type, external_id, delivery_key,
  source_revision?, operation, effective_at?, payload
}
```

Это внутренний формат CRM, **не выдуманная схема API LMS/сайта**. `first_received_at` назначает CRM. External identity ключ — `(source_id, entity_type, external_id)`. Неизвестный порядок ревизий/неоднозначный match/неполная дата уходит в reconciliation; нельзя считать строковую revision лексикографически большей без контракта источника.

CRM владеет workflow/назначениями/доступом. Источник присылает учебный факт/заявку; routing rule определяет existing/new interaction, шаблон/версию/default owner. Если нет уверенного matching, ничего не создаётся повторно скрытно. Raw payload защищён тем же уровнем доступа/retention, что его содержимое; UI операторов видит безопасную диагностику.

A передаёт B примеры: новая заявка; повтор той же delivery; изменённая revision; старое событие; одинаковый delivery_key с иным hash; отсутствующая программа; aggregate без уникального learner key; два пересекающихся потока. B строит метрики и ручные ожидаемые результаты без зависимости от доступности реального LMS.

## 9. Общие файлы и миграции

| Зона | Единственный владелец записи | Как участвует второй |
|---|---|---|
| Composition root, config, deploy/compose, backend dependencies | A | B добавляет предложение/settings/renderer dependency в PR своего модуля; A интегрирует |
| `backend/app/contracts` | A как интегратор C01–C05/C07; B владелец семантики C06 | Обязательный review потребителя; новая версия fixture вместе со schema |
| `backend/alembic/versions` и revision chain | A | B присылает schema migration proposal со своей ORM/upgrade/backfill/checks; A выпускает очередной revision |
| `modules/{identity,catalogs,interactions,workflow,files,integrations,learning}` | A | B использует публичный port/fake, не изменяет repository напрямую |
| `modules/{imports,reports,analytics}` + весь React | B | A использует контракт/пишет integration fixture, передаёт изменение владельцу |
| `contracts/fixtures` | По пространству модуля | Нет редактирования одного общего fixtures.json на все функции |
| CI | B; runtime/deploy hooks A | Небольшие согласованные изменения по общей проверке |

Handoff миграции — в текущий или следующий рабочий день. A не должен ждать окончания всего модуля B для добавления его таблиц. Временный isolated test schema допустим в PR, merge требует одного Alembic head и проверки upgrade чистой и populated DB. Если A занят, ownership миграции явно передаётся B на конкретный PR; два параллельных независимых heads молча не допускаются.

## 10. Контрактные проверки до merge

Это требования к будущему CI, не утверждение, что проверки уже добавлены:

1. OpenAPI export имеет все реальные routes/request/response/errors; generated TS не отличается после повторной генерации.
2. Consumer fixtures валидируются DTO/JSON Schema; fake сообщает реальные enum/коды, не всегда успешный response.
3. Межмодульный import checker разрешает только facade/contracts; business modules не импортируют чужие ORM для записи.
4. PostgreSQL migration test: чистый upgrade, upgrade populated старого среза, один head, неизменность ID/истории и эталона.
5. Meaningful domain tests: race двух команд, повтор ключа, отзыв доступа, ошибочный graph, поздний факт, cross-organization FK, worker crash/replay, stale preview. Не тестировать простое наличие каждого поля отдельным тестом.
6. End-to-end контрактный smoke UI на fake и отдельно на настоящем API/OIDC. Отличие mock/real видно в протоколе.

Первый день: A фиксирует C01–C05/C07 и skeleton; B фиксирует C06/fixtures/React features. Затем A реализует domain/security/jobs/files, B — imports/reports/analytics и интерфейс. Результат каждого handoff — схема, примеры, перечень ошибок и исполняемый fake; устного «API скоро будет» недостаточно.
