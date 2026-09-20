# Покрытие ТЗ, критерии проверки и открытые решения

Основание — исходный PDF «6. ИТ Школа Ростелекома», физические страницы с обложкой. R01–R29 сохраняют номера прежнего анализа; R30 выделяет учебную статистику из цели на странице 2. Это **матрица покрытия проектом**, а не заявление, что все требования уже реализованы.

Статус «частично» означает наличие конкретного кода, но не завершение всех сценариев требования. «Нет» — нет исполняемой реализации, даже если существует документ или UI-заглушка. Доказательства AC01–AC30 относятся к [сценариям приёмки](../planning/03-acceptance-scenarios.md); дополнения ниже обязательны для целевой версии. Задачи TD — в [roadmap](04-two-developer-roadmap.md).

## 1. Полная трассировка

| ID / страницы | Требование | Сейчас | Целевые данные/модуль | Задачи | Доказательство готовности |
|---|---|---|---|---|---|
| R01 / 3–4 | Каталоги учреждений, направлений, продуктов, ответственных в БД | Частично: ORM и чтение, полного CRUD нет | catalogs: organization/contact/vendor/direction/program/product; identity: app_user/organization_assignment | TD08–TD09 | AC01; create/update/archive, связи, restart, вуз и школа |
| R02 / 3–4 | Актуализация XLS/XLSX по согласованному mapping | Нет | imports: import_batch/row/target/application/mapping; CatalogCommands | TD12, TD14–TD15 | AC02–AC03; оба формата, preview, conflict, явный atomic batch, повтор без дублей |
| R03 / 4 | Все 10 перечисленных полей исходного Excel | Нет полного состава | vendor/product/contract/license/delivery/contact/assignment/comment | TD08, TD14 | AC01–AC03; каждое поле имеет target, дата/год лицензии не угадываются |
| R04 / 4–6 | Период, учреждение, направление/программа, продукт, ответственный, статус | Частично: параметры некоторых API, ограниченный UI | interaction queries + HistoricalQuery с единым filter DTO | TD10–TD11, TD19, TD21 | AC15; комбинации AND/OR, текущий/исторический режим, границы дат, нет утечки count |
| R05 / 3–4 | Визуальный путь и реальные переходы | Частично: один статический граф | workflow_version/state/transition + interaction/current_visit + state facts | TD10–TD11, TD16, TD30 | AC07; полный путь, optional rework, петля, terminal, сохранение после refresh |
| R06 / 4–5 | Создать/изменить workflow, переименовать статусы | Нет | draft/validate/publish, immutable version; migration_plan/item | TD16–TD18 | AC08; новый граф, ошибки, публикация, active instances, CAS migration, история старых labels |
| R07 / 4 | Комментарий при переходе | Частично: payload события; нужно единое представление comments | comment с event_id и исходным state_visit_id | TD10–TD11 | AC09; автор/время/визит, переход и комментарий атомарны, replay не дублирует |
| R08 / 4 | PNG/JPEG/PDF/ZIP/GZIP/RAR/DOC/DOCX/XLS/XLSX в статусах | Нет | files: attachment/link + typed contract/license links, scan job, private objects | TD12–TD13 | AC10; каждый формат, hash round-trip, MIME mismatch, quarantine, отзыв доступа |
| R09 / 4–5 | Отчёты за период, фильтры и выбранные колонки | Частично: snapshot, без полного выбора | report_definition/run/row/scope_item, snapshot/activity/created | TD19, TD21 | AC11–AC15; заранее рассчитанные строки/итоги, выбранные колонки, ранние незаполненные поля |
| R10 / 4–5 | Реальные XLS/XLSX/PDF | Нет, только JSON | report_artifact + отдельные renderer adapters | TD20–TD21 | AC16; файлы открываются, сигнатура соответствует типу, кириллица, разбиение XLS без потерь |
| R11 / 4 | Диаграммы и графики PNG/PDF | Частично UI counters, требуемого экспорта нет | analytics/reports: metric definitions, frozen chart series/artifacts | TD20, TD27–TD28 | AC17; численные итоги, единицы/легенда/период, PNG/PDF одного dataset |
| R12 / 4–6 | JSON pull API двух источников LMS и Laravel | Нет | integration_source/adapter/sync_run/inbox/checkpoint | TD22–TD24 | AC18; два настоящих test API, auth/pages/quotas, реальные протоколы сверки |
| R13 / 4 | Интеграция с existing/new workflow | Нет | external_identity/reconciliation/routing + domain commands | TD22–TD26 | AC19; existing/new/ambiguous/repeat/out-of-order, без обхода guards/ACL |
| R14 / 5 | Вход через Keycloak | Реализована основа, целевое окружение не подтверждено | OIDC/JWT + local active user/principal | TD05, TD34 | AC04; login/logout/expiry/refresh, audience, невалидная подпись, отключённый пользователь |
| R15 / 5–6 | 3 роли, видимость, назначить/сменить/снять ответственного учреждения | Частично: карточки, basic scope | teams/membership/grants/organization_assignment/owning_team | TD05, TD08–TD09, TD29 | AC05–AC06; scope на list/detail/jobs/files/exports, unassigned queue, technical admin |
| R16 / 5 | Изменения без reload/reset страницы | Частично основные экраны | React features + query invalidation + сохранение контекста | TD07, TD11, TD31 | AC21–AC22; сохранение фильтра/позиции/ввода, server conflict без потери текста |
| R17 / 5 | Кэш работы действий пользователя | Частично mutation key, трактовка требует согласования | UI preferences, memory draft, command_result, authz-aware cache | TD01, TD07 | AC22; replay после timeout; logout/user switch; согласованный набор восстанавливаемого состояния |
| R18 / 5 | Отклик примеров UI ≤1 с | Не доказано | HTTP/query optimization, pools, measured frontend render | TD10, TD19, TD33 | AC23; end-to-end max ≤1 с в согласованном профиле, p95/p99 дополнительно |
| R19 / 5 | 50 пользователей и ≥10 одновременно строящихся отчётов | Не доказано | isolated HTTP/report workers, DB resource budgets | TD06, TD20, TD33–TD34 | AC24; 50 sessions + overlap ≥10 running report executions, ресурсы/ошибки/длительности |
| R20 / 5 | Коды ошибок, понятный интерфейс | Частично APIError/request_id | platform error contract + feature form errors | TD01–TD02, TD07, TD32 | AC21; validation/auth/conflict/dependency errors, safe diagnostics и восстановление |
| R21 / 5 | Встроенные user/admin guides со скриншотами | Нет полного комплекта | versioned docs + React help по роли | TD35 | AC26; актуальные скриншоты, поиск/ссылки, встроенные инструкции и DOC/PDF |
| R22 / 6 | Допустимый стек React/Python/PostgreSQL | Основной стек выбран | Сохранение FastAPI/React/Postgres + ADR и inventory | TD03–TD04, TD36 | AC27; фактические зависимости/версии/лицензии и воспроизводимая сборка |
| R23 / 6 | Swagger всех методов, библиотеки/компоненты | Частично автоматически для текущего API | OpenAPI snapshot + generated client + inventory | TD01, TD36 | AC27; реальный auth, error schemas, все paths и pipeline schema diff |
| R24 / 6 | Отдельный сервис, JSON-файл, Docker | Частично Compose/JSON первого среза | самостоятельный deploy + versioned report JSON | TD20, TD34 | AC20/AC28; schema/result checksum и запуск без LMS для внутренних операций |
| R25 / 7 | Linux, читаемые исходники, комментарии сложной логики | Код есть, целевая установка не подтверждена | Linux CI/images/docs, пояснения temporal/lease/CAS | TD04, TD34, TD36 | AC28; install/build/upgrade с чистого Linux по инструкции |
| R26 / 7 | Обработка/ограничения/сборка/установка, архитектура в Archi | Частично старые документы; текущий пакет проектирует target | Архитектурный пакет + editable Archi exchange + ops docs | TD01, TD34–TD36 | AC29; модель импортируется в Archi, соответствует release, методы/лимиты документированы |
| R27 / 3–4, 7 | 152-ФЗ, ФСТЭК №117, 149-ФЗ и применимые нормы | Не доказано | AccessPolicy/audit/secrets/retention/backup + согласованный ИБ-контур | TD05, TD12, TD34, TD38–TD41 | AC30; определена применимость и собраны требуемые свидетельства, не декларация по наличию SSO |
| R28 / 7, 9 | Понятный desktop/mobile/tablet, контраст, группировка | Частично исходный UI | адаптивные feature routes, keyboard/focus/text alternatives | TD07 и UI-пакеты, TD32 | AC25; все основные действия на согласованных viewport, доступные ошибки/графы |
| R29 / 7, 9 | PPTX/PDF, четыре ссылки для сдачи | Нет завершённого комплекта | demo script/presentation/docs/repo/prototype access | TD37 | AC29; проверка четырёх ссылок с чужой учётной записи и репетиция |
| R30 / 2 | Заявки, обучающиеся, параллельные потоки; востребованность программ | Нет | learning facts + analytics metric_definition/observation/version | TD26–TD28 | AC31 ниже; agreed metric definitions, provenance и корректное различение людей/регистраций |

## 2. Разложение 14 пунктов исходного пути

Это связь бизнес-сценария с данными, не утверждение, что в системе всегда ровно 14 статусов. Базовый JSON имеет 13 рабочих состояний и два технических terminal; заказчик может создать другую последовательность.

| Шаг PDF | Предметные данные/действия | Обязательное доказательство |
|---|---|---|
| 1. Поиск контакта | organization_contact, interaction_contact | Контакт учреждения отделён от app_user, привязан к правильной организации |
| 2. Коммуникация/актуальность | комментарий/событие, интересующее направление, nullable program/product | Раннее взаимодействие возможно до выбора программы |
| 3. Встреча | state visit + comment/next action/due date | Дата/ответственный и итог доступны руководителю |
| 4. Обмен документами | contract + attachments к visit | Пакет файлов, автор и время, действующая ACL |
| 5. Корректировка | optional transition/rework visit | Пропуск допустим, возвращение создаёт новое посещение, старые файлы сохраняются |
| 6. Подписание | contract status/signed_on + license fields | Факт подписи не выводится только из названия статуса |
| 7. Передача | delivery/license/material refs | Передача материалов, лицензии и документации имеет отдельные факты/подтверждения |
| 8. Сопровождение | workflow stage, comment/control item | Видны этап, ответственный, просрочка и история |
| 9. Обучение преподавателей | stage + training/cohort type, материалы | Не смешивается автоматически с числом учащихся по программе |
| 10. Обновление программы | program metadata/version + visit evidence | Историческое название и текущая версия не искажают старый отчёт |
| 11. Занятия | learning cohort/registrations/metric observations | Учебная статистика приходит из согласованного источника |
| 12. Актуализация документов | новые версии/вложения, очередной visit | Старые документы не перезаписываются по storage key |
| 13. Повышение квалификации | повторный цикл/этап по разрешённому graph | Идентификаторы посещений/циклов не сливаются |
| 14. Контроль этапов | обзор/история/время в статусах/due dates/report | Руководитель видит ход работы на каждом этапе, не только terminal |

## 3. AC31 и дополнительные обязательные проверки

**AC31 — учебные показатели:** синтетический dataset содержит одну программу с двумя пересекающимися потоками, человека в двух программах, повторную и отозванную заявку, отменённое зачисление, позднее исправление и агрегированный источник без learner ID. До запуска вручную фиксируются ожидаемые заявки/активные регистрации/уникальные лица (где доказуемо)/одновременные потоки. Повтор inbox не меняет итоги; отсутствие сведений показано как «Нет данных». Aggregate и детальные записи одного охвата не суммируются дважды. Если невозможно свести лица между источниками, итог так и называется — число регистраций или показатель источника, не «уникальные люди».

Дополнения к старым AC:

- **AC05/06:** отозвать grant после создания report run; проверить запрет rows/charts/download всего старого результата, включая статистику без interaction. Снятие owner оставляет очередь команды доступной руководителю.
- **AC08:** publish новой версии не меняет живые карточки; migration preview → конфликт revision → partial result по карточкам; перенесённые повторно не применяются. Это не atomic import.
- **AC10:** scanner timeout, архив с лимитом проверки, MIME mismatch, path-like filename, оборванный upload; данные в quarantine не доступны. Проверить все десять форматов отдельно.
- **AC11–15:** поздний комментарий не меняет state; исправление имеет stable fact identity/order; несколько фактов с одинаковым временем; commit после knowledge cutoff; frozen run неизменяем; два формата имеют один dataset hash.
- **AC02/03:** невалидная строка/устаревший target откатывает весь подтверждённый bounded batch; большой файл требует явных отдельных пакетов; rollback не маркируется partial success.
- **AC18/19:** одинаковый delivery key с иным payload hash → конфликт; падение между durable inbox и checkpoint не теряет запись; брокер очищен → PG reconcile восстанавливает jobs; старый worker с истёкшим fencing token не публикует результат.
- **AC23/24:** одновременно реальные команды UI и 10 executing reports; в результатах отдельно HTTP, browser duration, queue wait, materialization/render, max/RSS/CPU/DB pool wait.

## 4. Вопросы заказчику, которые не останавливают старт разработки

У каждой неопределённости есть рабочее предположение и точка, после которой его нельзя использовать без подтверждения. Эти вопросы предназначены для встречи с заказчиком; сейчас не требуется останавливать разработку контуров/fixtures.

| ID | Неопределённость | Рабочее решение сейчас | Gate / кто решает |
|---|---|---|---|
| Q01 | Одна или несколько программ/продуктов в цикле | Один interaction = одна программа/один продукт (оба nullable на ранних этапах), несколько циклов допустимы | До реальной загрузки каталогов, заказчик; расширение many-to-many изменит grain отчёта |
| Q02 | «Срок действия лицензии (год)» — срок в годах или год окончания | Сохранять `term_raw`, отдельно typed years/date при однозначном mapping; не угадывать | Утверждение Excel mapping, владелец данных |
| Q03 | Один или несколько ответственных за учреждение | Один активный CRM manager на учреждение + множество контактов учреждения; owner карточки независим | Перед финальной UI/импорт-приёмкой, руководитель процесса |
| Q04 | Командная видимость и снятие владельца | Явная owning team карточки, owner nullable, перемещение пользователя не переносит карточки | Перед настройкой живых пользователей, владелец доступа |
| Q05 | Значение «отчёт за период» | Три явных режима snapshot/activity/created, `[from,to)`, labels/owner исторические, ACL текущая | Согласование эталона с аналитиком/заказчиком |
| Q06 | Реальные API LMS/Laravel | Два адаптера + внутренний envelope; mock маркирован; не предполагать URL, fields, auth и revision order | Перед TD23/TD24 и реальным R12/R13 |
| Q07 | Источник может менять workflow/назначения? | По умолчанию CRM владеет ими; только явные routing/command rules могут инициировать разрешённый переход | Integration contract owner, до записи реальных сообщений |
| Q08 | Формулы и идентичность учеников/потоков | Независимые метрики с definition/source/coverage; без произвольного сводного рейтинга, без лишних ПДн учащихся | R30/AC31, владельцы LMS и методики |
| Q09 | Offline и постоянные черновики | Memory cache + несекретные preferences, idempotent retry; нет автоматической offline-записи | UX/ИБ, перед приёмкой R17 |
| Q10 | Объём базы/файлов/отчёта/профиль сети | Синтетический профиль из 01, лимиты из 03, результаты маркируются предварительными | R18/R19, принимающая сторона |
| Q11 | Категории данных, hosting, применимость/подтверждение ИБ, сроки хранения | Закрытый synthetic стенд, configurable retention/backup, технические меры | Реальные данные/пилот, заказчик и ИБ |
| Q12 | S3-провайдер и операционная поддержка | StoragePort, поддерживаемая целевая реализация после compatibility spike | До deploy пилота, администратор заказчика |

## 5. Как отмечать фактический прогресс

Для каждого R хранить статус `planned → implemented → verified → accepted` и ссылку на PR/тестовый протокол/сборку. Внешнее условие добавляет `blocked_on Xnn` конкретному пакету; остальные продолжаются. Ни этот документ, ни mock API, ни красивый экран не переводят R в accepted. Список требований не сокращается для хакатона; для показа отдельно фиксируется честный набор готовых сценариев.
