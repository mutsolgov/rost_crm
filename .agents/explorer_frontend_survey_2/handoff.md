# Архитектурный отчёт фронтенд-исследования (Baseline R4: Enterprise Core & Analytics Engine)

**Дата:** 19 сентября 2026 года  
**Роль:** Frontend Survey Explorer (`explorer_frontend_survey_2`)  
**Рабочая директория:** `/home/muhammad/Dev/HACKATHON/LCT/rost_crm/.agents/explorer_frontend_survey_2`  
**Цель исследования:** Установление точного технического базиса кодовой базы фронтенда для реализации пакета R4 (UI компонентов в стилистике Rostelecom Gen2 Light Theme: закрытые вложения, аналитический дашборд с 3 режимами и SVG-диаграммами, 3-шаговый мастер импорта каталогов, интерактивный граф процесса на 13+2 состояний).

---

## 1. Observation (Фактические наблюдения)

### 1.1. Карточка взаимодействия (`frontend/src/views/InteractionPage.tsx`)
- **Размер и структура файла:** 382 строки кода.
- **Текущий макет UI:**
  - Шапка: кнопка возврата `.back-link` (`InteractionPage.tsx:288`), `PageHeader` с eyebrow `"КАРТОЧКА ВЗАИМОДЕЙСТВИЯ"`, названием, вузом и бейджем текущего этапа `StageBadge` (`InteractionPage.tsx:289-290`).
  - Уведомления: `ErrorAlert` и `.success-alert` (`InteractionPage.tsx:291`).
  - Основная 2-колоночная сетка `.detail-grid` (`InteractionPage.tsx:292-355`):
    - Левая секция `.detail-main`:
      - Заголовок `.detail-heading` (`InteractionPage.tsx:294-304`): текущий этап, кнопка `«Редактировать параметры»` (`InteractionPage.tsx:298-300`), бейдж `Revision {item.revision}`.
      - Сетка параметров `.detail-facts` (3 колонки, 9 фактов) (`InteractionPage.tsx:305-315`): Организация, ИТ-программа, ИТ-продукт, Цикл, Контакт вуза (`item.contact_name`), Договор (`item.contract_number`), Лицензия (`item.license_status`), Ответственный (`Avatar` + `item.owner_name`), Дата обновления (`formatDate(item.updated_at)`).
      - Блок действий `.action-block` (`InteractionPage.tsx:316-341`): отображение всех допустимых переходов из `item.allowed_transitions` с классификацией кнопок (`danger` для отмены, `secondary` для циклов/доработок, `primary` для прямого перехода).
      - Для переходов с `comment_required: true` открывается `TransitionCommentModal` (`InteractionPage.tsx:168-227`).
    - Правая колонка `.detail-side` (`InteractionPage.tsx:349-354`):
      - Панель владельца `.side-panel` с передачей карточки руководителем (`me.role === 'supervisor'`).
      - Панель добавления комментария `.side-panel`.
  - Нижняя секция `.timeline-panel` (`InteractionPage.tsx:356`): объединённая хронология `events` и `comments`.
- **Статус работы с вложениями:**
  - **В `InteractionPage.tsx` блок вложений ПОЛНОСТЬЮ ОТСУТСТВУЕТ.**
  - Нет отображения загруженных файлов, нет бейджей форматов, нет кнопки авторизованного скачивания.
  - Нет формы drag-and-drop загрузки, нет клиентской валидации форматов и размера до 25 МБ.

---

### 1.2. Раздел отчётов (`frontend/src/views/Reports.tsx`)
- **Размер и структура файла:** 24 строки компактного кода.
- **Текущая функциональность:**
  - Поддерживается строго **один режим**: снимок на дату (`snapshot`) через вызов `POST /reports/snapshot` (`Reports.tsx:16`).
  - Фильтры: выбор даты/времени `asOf` (`<input type="datetime-local">`), организация `organizationId`, ответственный `ownerId` (`Reports.tsx:18`).
  - Экспорт: ровно одна кнопка `«Скачать JSON»` (`Reports.tsx:19`), вызывающая `api.download('/reports/snapshot/export', query())`.
  - Визуализация: 3 текстовых метрики (`totals.interactions`, `totals.organizations`, `counts_by_state.length`) и простая HTML-таблица (`Reports.tsx:19`).
- **Выявленные дефициты:**
  - Отсутствуют режимы `activity` («Динамика переходов») и `created` («Созданные карточки»).
  - Отсутствует панель скачивания с раздельными кнопками **Скачать XLSX**, **Скачать PDF**, **Скачать JSON**.
  - **Диаграммы и графики отсутствуют полностью** (нет SVG/Canvas визуализаций воронки или распределения по этапам).

---

### 1.3. Справочники и мастер импорта (`frontend/src/views/ReferenceViews.tsx`)
- **Размер и структура файла:** 10 строк кода.
- **Текущие представления:**
  - `CatalogPage({ catalogs }: { catalogs: Catalogs })`: отображает 4 карточки `.reference-card` со списками (Организации, ИТ-программы, ИТ-продукты, Ответственные).
  - `HelpPage()`: подсказки по работе с карточкой и авторизации.
- **Точка интеграции мастера импорта:**
  - В `CatalogPage` в настоящий момент передаётся только свойство `catalogs` (`App.tsx:103`).
  - Свойство `api` и коллбэк мутации данных `onChanged` в `CatalogPage` не передаются.
  - Кнопка вызова 3-шагового мастера импорта (`ImportWizardModal`) должна располагаться в шапке `CatalogPage` (в блоке `page-heading`), а сам компонент модального окна — открываться поверх страницы.

---

### 1.4. Граф жизненного цикла процесса (`WorkflowGraphView.tsx`)
- **Статус файла:** Файл `frontend/src/views/WorkflowGraphView.tsx` **в настоящий момент не существует в репозитории**.
- **Данные workflow:**
  - Бэкенд-эндпоинт `GET /api/v1/workflow` возвращает полную структуру `WORKFLOW` (`main.py:115-125`), включающую 15 состояний (13 рабочих + 2 терминальных) и 29 переходов из `docs/planning/04-base-workflow.json`.
  - В `App.tsx:61` объект `workflow` загружается на верхнем уровне (`useResource<Workflow>(() => api.get('/workflow'), [api])`).
  - Требуется создать компонент `WorkflowGraphView.tsx` на базе чистого SVG для визуализации 15 состояний воронки с динамической подсветкой активного этапа карточки (`item.state`), переходов и статусов.

---

### 1.5. Базовые модули: `api.ts`, `types.ts`, `styles.css`, `App.tsx`
- **`frontend/src/api.ts` (96 строк):**
  - Метод `raw(path, options)` в строке 33 принудительно устанавливает заголовок `Content-Type: application/json`:
    ```ts
    if (options.body !== undefined) headers.set('Content-Type', 'application/json');
    ```
    **Критическое ограничение для загрузки файлов:** при передаче объекта `FormData` (multipart/form-data) браузер обязан сам сформировать заголовок с `boundary`. Принудительная установка `application/json` ломает отправку файлов.
  - Метод `download(path, body)` в строке 73 выполняет строго `POST` запрос с телом JSON.
    **Ограничение:** скачивание вложений выполняется через `GET /interactions/{id}/attachments/{attachment_id}/download` с авторизационными заголовками. Необходима поддержка метода `downloadGet(path, fallbackName)` или обобщённого `downloadFile`.
  - Отсутствует специализированный метод `upload<T>(path: string, formData: FormData, key?: string): Promise<T>`.
- **`frontend/src/types.ts` (129 строк):**
  - Отсутствует интерфейс `Attachment` (метаданные файла, размер, тип, контрольная сумма, автор, дата).
  - Отсутствуют типы отчётов `ActivityQuery`, `ActivityResult`, `CreatedQuery`, `CreatedResult`.
  - Отсутствуют типы мастера импорта: `ImportPreviewResponse`, `ImportCommitResponse`.
  - В интерфейсе `Workflow` (`types.ts:67-70`) не типизирован массив `transitions`.
- **`frontend/src/styles.css` (49 строк, 20 764 байт):**
  - Токены темы Rostelecom Light Theme уже корректно объявлены в `:root` (`styles.css:1-36`):
    `--rtk-color-primary: #7700FF`, `--rtk-color-accent: #FF4F12`, `--rtk-color-background: #F4F5F8`, `--rtk-color-card: #FFFFFF`, `--rtk-color-border: #E2E5EB`, `--rtk-color-text: #101828`.
  - Отсутствуют специфичные CSS-стили для:
    - Секции вложений (dropzone, бейджи форматов `.format-pdf`, `.format-doc`, `.format-xls`, `.format-img`, `.format-archive`).
    - Переключателя 3 режимов отчётов и панели кнопок экспорта.
    - SVG-контейнера диаграммы распределения и воронки.
    - Индикатора шагов мастера импорта (Stepper шагов 1-2-3).
    - Узлов и связей интерактивного графа процесса.
- **`frontend/src/App.tsx` (117 строк):**
  - Маршрутизация построена на хэш-навигации (`useRoute()`, строки 62–73).
  - `CatalogPage` на строке 103 вызывается как `<CatalogPage catalogs={catalogs.data}/>`. Для работы импорта необходимо передавать `api={api}` и `onChanged={changed}`.

---

### 1.6. Сборка и проверка фронтенда (`package.json`, TypeScript)
- **`frontend/package.json`:**
  - Зависимости: строго минимальные (Ponytail):
    `dependencies: {"keycloak-js": "26.2.4", "react": "19.3.0", "react-dom": "19.3.0"}`
    `devDependencies: {"@types/react": "19.3.0", "@types/react-dom": "19.3.0", "@vitejs/plugin-react": "6.1.1", "typescript": "7.0.2", "vite": "8.3.0"}`
  - Скрипты:
    `"dev": "vite --host 127.0.0.1"`
    `"build": "tsc --noEmit && vite build --configLoader native"`
    `"typecheck": "tsc --noEmit"`
- **Особенности изолированной среды выполнения:**
  - В системной среде установлены Node.js `v22.22.2` и npm `10.9.7`.
  - `node_modules` в репозитории не закоммичены. Прямой доступ во внешнюю сеть к npm-реестру из песочницы заблокирован политиками безопасности.
  - Промышленная сборка осуществляется через Docker (`frontend/Dockerfile` на базе `node:24-alpine` с `pnpm install --frozen-lockfile && pnpm build`).
  - Конфигурация `tsconfig.json` требует строгой проверки типов: `"strict": true`, `"noUnusedLocals": true`, `"noUnusedParameters": true`.

---

## 2. Logic Chain (Логическая цепочка рассуждений)

```
[Observation 1.1: Отсутствие секции вложений в InteractionPage.tsx]
  ├──> Требуется добавить секцию «Вложения и документы» в карточку взаимодействия.
  ├──> Файлы классифицируются по 10 форматам ТЗ:
  │    • PDF: .pdf -> бейдж "PDF" (красно-бордовый оттенок)
  │    • DOC: .doc, .docx -> бейдж "DOC" (синий оттенок)
  │    • XLS: .xls, .xlsx -> бейдж "XLS" (зелёный оттенок)
  │    • IMG: .png, .jpeg, .jpg -> бейдж "IMG" (фиолетовый оттенок)
  │    • ARCHIVE: .zip, .gz, .rar -> бейдж "ZIP" (оранжевый оттенок)
  ├──> Drag-and-drop область на нативном HTML5 API (onDragOver, onDrop) + скрытый <input type="file">.
  └──> Клиентская предвалидация:
       1. Размер: file.size <= 25 * 1024 * 1024 байт (иначе немедленная ошибка без запроса к API).
       2. Расширение: whitelist из 10 расширений (иначе сообщение о недопустимом типе).

[Observation 1.2: Единственный режим отчёта и отсутствие графиков в Reports.tsx]
  ├──> Внедрение переключателя 3 режимов:
  │    • «Срез на дату (Snapshot)» -> as_of, knowledge_cutoff
  │    • «Динамика переходов (Activity)» -> from_date, to_date
  │    • «Созданные карточки (Created)» -> from_date, to_date
  ├──> Панель экспорта: 3 кнопки (Скачать XLSX, Скачать PDF, Скачать JSON),
  │    отправляющие format=xlsx|pdf|json на соответствующие эндпоинты.
  └──> Ponytail-диаграмма: чистый SVG (или Canvas) без сторонних пакетов (Recharts/Chart.js):
       • Распределение взаимодействий по этапам в корпоративных цветах #7700FF и #FF4F12.
       • Интерактивные подсказки (tooltip) и адаптивная векторная отрисовка.

[Observation 1.3: Каталоги в ReferenceViews.tsx и мастер импорта]
  ├──> В CatalogPage добавить кнопку действия «Импорт каталогов» в page-heading.
  ├──> Реализовать модальный 3-шаговый компонент ImportWizardModal:
  │    • Шаг 1: Загрузка файла (XLSX, XLS, CSV) с проверкой формата.
  │    • Шаг 2: Вызов POST /api/v1/imports/organizations/preview (dry-run) ->
  │             отображение таблицы строк, счётчиков валидных и ошибочных записей.
  │    • Шаг 3: Вызов POST /api/v1/imports/organizations/commit с Idempotency-Key ->
  │             прогресс-бар, отчёт об успехе и вызов onChanged() для обновления справочников.
  └──> В App.tsx передать в CatalogPage свойства: api={api} и onChanged={changed}.

[Observation 1.4: Отсутствие WorkflowGraphView.tsx]
  ├──> Создать компонент frontend/src/views/WorkflowGraphView.tsx.
  ├──> Отрисовка полного графа 13 рабочих + 2 терминальных состояний (15 узлов) из WORKFLOW.
  ├──> Подсветка текущего положения карточки (current_state) и доступных ветвей перехода.
  └──> Возможность встраивания как визуализатора этапов в InteractionPage и в обзорные экраны.

[Observation 1.5: Ограничения в api.ts и неполнота types.ts]
  ├──> В api.ts:
  │    • Исправить raw(): не устанавливать Content-Type: application/json, если body instanceof FormData.
  │    • Добавить метод upload<T>(path, formData, key).
  │    • Добавить метод downloadGet(path, fallbackName) для скачивания вложений.
  │    • Расширить download() параметрами формата и имени файла.
  └──> В types.ts добавить интерфейсы Attachment, ActivityResult, CreatedResult, ImportPreviewResponse, ImportCommitResponse.
```

---

## 3. Caveats (Ограничения и допущения)

1. **Изоляция сетевого окружения сборки:**
   - В текущей изолированной среде разработки отсутствует прямой доступ к npmjs.org, поэтому `pnpm install` / `npm install` не могут быть запущены без предварительно закешированных модулей или контейнеризации.
   - Любые изменения TypeScript должны проектироваться с абсолютной строгостью типов, чтобы при сборке в Docker (`pnpm build`) не возникало ошибок компиляции.
2. **Сторонние зависимости (Zero External Bloat / Ponytail):**
   - Строжайший запрет на установку библиотек графиков (`chart.js`, `recharts`, `d3`), библиотек драг-н-дропа (`react-dropzone`) или иконочных шрифтов.
   - Все визуализации строятся на нативных SVG-примитивах (`<svg>`, `<rect>`, `<path>`, `<circle>`, `<text>`) с использованием дизайн-токенов Ростелекома.
3. **Синхронизация с бэкендом R1–R3:**
   - Эндпоинты `/api/v1/interactions/{id}/attachments`, `/api/v1/reports/activity`, `/api/v1/reports/created`, `/api/v1/imports/organizations/*` разрабатываются параллельно бэкенд-командой. Фронтенд-контракты спроектированы в строгом соответствии со спецификацией ТЗ и эталонами `04-base-workflow.json` и `05-report-fixture.json`.

---

## 4. Conclusion (Архитектурное решение и план реализации)

Для реализации пакета R4 определены следующие точные технические решения:

### 4.1. Расширение `frontend/src/api.ts`
```ts
// 1. Защита multipart/form-data в raw():
if (options.body !== undefined && !(options.body instanceof FormData)) {
  headers.set('Content-Type', 'application/json');
}

// 2. Метод загрузки файлов:
async upload<T>(path: string, formData: FormData, key?: string): Promise<T> {
  const response = await this.raw(path, {
    method: 'POST',
    body: formData,
    headers: key ? { 'Idempotency-Key': key } : {},
  });
  return response.json() as Promise<T>;
}

// 3. Метод авторизованного скачивания GET:
async downloadGet(path: string, fallbackName = 'download'): Promise<void> {
  const response = await this.raw(path, { method: 'GET' });
  const blob = await response.blob();
  const disposition = response.headers.get('Content-Disposition');
  const name = disposition?.match(/filename="?([^";]+)"?/i)?.[1] || fallbackName;
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = name.replace(/[\\/:*?"<>|]/g, '_');
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
```

### 4.2. Расширение `frontend/src/types.ts`
```ts
export interface Attachment {
  id: string;
  interaction_id: string;
  visit_id: string;
  file_name: string;
  file_size: number;
  content_type: string;
  checksum: string;
  uploaded_by: string;
  uploaded_by_name?: string;
  created_at: string;
}

export interface ActivityQuery {
  from_date: string;
  to_date: string;
  knowledge_cutoff?: string;
  organization_ids?: string[];
  program_ids?: string[];
  product_ids?: string[];
  owner_ids?: string[];
}

export interface ActivityRow {
  event_id: string;
  interaction_id: string;
  title: string;
  organization_name: string;
  from_state: string;
  to_state: string;
  transition_code: string;
  owner_at_event: string;
  owner_at_event_name: string;
  actor_name: string;
  effective_at: string;
}

export interface ActivityResult {
  report_type: 'activity';
  from_date: string;
  to_date: string;
  knowledge_cutoff: string;
  generated_at: string;
  rows: ActivityRow[];
  totals: { transitions: number; counts_by_to_state: Record<string, number> };
}

export interface ImportPreviewRow {
  row_number: number;
  organization_name: string;
  org_type: string;
  contact_name?: string;
  contact_position?: string;
  contact_email?: string;
  contact_phone?: string;
  program_name?: string;
  product_name?: string;
  is_valid: boolean;
  errors: string[];
}

export interface ImportPreviewResponse {
  rows_total: number;
  valid_count: number;
  error_count: number;
  preview_rows: ImportPreviewRow[];
  errors: string[];
}

export interface ImportCommitResponse {
  success: boolean;
  rows_total: number;
  imported_count: number;
  created_organizations: number;
  created_contacts: number;
}
```

### 4.3. Компонент вложений в `InteractionPage.tsx`
- Создание секции `<AttachmentsSection interactionId={id} api={api} revision={revision} onChanged={onChanged}/>`.
- Бейджи форматов:
  ```tsx
  function formatBadge(filename: string) {
    const ext = filename.split('.').pop()?.toLowerCase() || '';
    if (ext === 'pdf') return <span className="format-badge format-pdf">PDF</span>;
    if (['doc', 'docx'].includes(ext)) return <span className="format-badge format-doc">DOC</span>;
    if (['xls', 'xlsx'].includes(ext)) return <span className="format-badge format-xls">XLS</span>;
    if (['png', 'jpeg', 'jpg'].includes(ext)) return <span className="format-badge format-img">IMG</span>;
    return <span className="format-badge format-archive">ZIP</span>;
  }
  ```
- Валидация размера: `const MAX_SIZE = 25 * 1024 * 1024;` (25 МБ).
- Валидация формата: whitelist `Set(['png', 'jpeg', 'jpg', 'pdf', 'zip', 'gz', 'gzip', 'rar', 'doc', 'docx', 'xls', 'xlsx'])`.
- Загрузка через `api.upload('/interactions/' + id + '/attachments', formData, makeMutationKey())`.
- Скачивание через `api.downloadGet('/interactions/' + id + '/attachments/' + file.id + '/download', file.file_name)`.

### 4.4. Модернизация `Reports.tsx`
- Вкладки переключения режимов (Snapshot / Activity / Created).
- Тулбар экспорта:
  - `<Button variant="secondary" onClick={() => exportReport('xlsx')}><Icon name="download"/>Скачать XLSX</Button>`
  - `<Button variant="secondary" onClick={() => exportReport('pdf')}><Icon name="download"/>Скачать PDF</Button>`
  - `<Button variant="secondary" onClick={() => exportReport('json')}><Icon name="download"/>Скачать JSON</Button>`
- Нативная SVG-диаграмма распределения (Funnel / Stage distribution):
  - Цвета: `#7700FF` (основной фиолетовый), `#FF4F12` (акцентный оранжевый), `#0088FF` (синий инфо), `#039855` (зелёный успех).
  - Отрисовка горизонтальных полос или ступеней воронки с процентным соотношением и количеством.

### 4.5. Мастер импорта `ImportWizardModal` в `ReferenceViews.tsx`
- Вызов из шапки `CatalogPage`: кнопка `<Button onClick={() => setImportOpen(true)}><Icon name="plus"/>Импорт организаций</Button>`.
- Шаг 1: Выбор файла (`.xlsx, .xls, .csv`), drag-and-drop.
- Шаг 2: Вызов `/imports/organizations/preview`, валидация данных, отображение сводки (Всего / Без ошибок / С ошибками) и таблицы предпросмотра с цветовой индикацией ошибок.
- Шаг 3: Вызов `/imports/organizations/commit` с прогресс-баром и кнопкой завершения, вызывающей `onChanged()`.

### 4.6. Создание `WorkflowGraphView.tsx`
- Визуализация полного жизненного цикла на 15 этапов (13 рабочих шагов в логических фазах + 2 терминальных исхода `completed` и `cancelled`).
- Фазы:
  1. *Инициация:* `contact_search`, `needs_clarification`, `meeting` (Фиолетовые тона).
  2. *Договоры и материалы:* `document_exchange`, `document_revision`, `document_signing`, `materials_transfer` (Оранжевые тона).
  3. *Внедрение и обучение:* `deployment`, `teacher_training`, `curriculum_update` (Синие тона).
  4. *Учебный процесс:* `classes`, `materials_update`, `teacher_upskilling` (Зелёные тона).
  5. *Финал:* `completed` (Зелёный успех), `cancelled` (Красный отказ).
- Отображение связей (прямые, возвраты на доработку, циклы, отмены) и подсветка активного состояния `currentState`.

---

## 5. Verification Method (Метод независимой верификации)

1. **Статический анализ исходных файлов:**
   - Проверить наличие и экспорт компонентов:
     `view_file: frontend/src/views/WorkflowGraphView.tsx`
     `view_file: frontend/src/views/InteractionPage.tsx`
     `view_file: frontend/src/views/Reports.tsx`
     `view_file: frontend/src/views/ReferenceViews.tsx`
   - Проверить методы `upload` и `downloadGet` в `frontend/src/api.ts`.
   - Проверить интерфейсы `Attachment`, `ActivityResult`, `ImportPreviewResponse` в `frontend/src/types.ts`.
2. **Проверка чистоты Ponytail:**
   - Убедиться, что в `package.json` не добавлено ни одной новой сторонней библиотеки (`git diff frontend/package.json`).
3. **Проверка дизайн-системы:**
   - Проверить, что все цвета в стилях используют переменные из `:root` (`--rtk-color-*`).
4. **Сквозная сборка и тесты бэкенда:**
   - Запустить валидаторы спецификаций:
     ```bash
     python3 docs/checks/verify_workflow.py
     python3 docs/checks/verify_reports.py
     python3 docs/checks/verify_plan.py
     ```
   - Запустить тесты бэкенда:
     ```bash
     pytest -v backend/tests/test_working_slice.py
     ```
5. **Критерии инвалидации (Что опровергнет отчёт):**
   - Наличие прямого хардкода цветов вне палитры Gen2.
   - Использование `localStorage` для хранения токенов.
   - Отсутствие клиентской проверки размера файла (25 МБ) или формата.
   - Отсутствие отображения любого из 15 состояний графа в `WorkflowGraphView`.
