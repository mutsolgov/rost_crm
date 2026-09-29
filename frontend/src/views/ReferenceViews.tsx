import { useEffect, useState } from 'react';
import { useAuth } from '../auth';
import { Button, Icon } from '../ui';

// Re-export CatalogPage and modals for backwards compatibility and clean modular separation
export { CatalogPage, ImportWizardModal, WorkflowMigratorModal, AssignOrganizationManagerModal } from './CatalogPage';

export type HelpTab = 'manager' | 'supervisor' | 'admin' | 'errors' | 'security';

export function isHelpTabAllowed(tab: HelpTab | string, role?: string | null): boolean {
  const t = typeof tab === 'string' ? tab.trim().toLowerCase() : '';
  if (t === 'errors' || t === 'security') return true;
  const r = typeof role === 'string' ? role.trim().toLowerCase() : '';
  const effRole = r || 'manager';
  if (t === 'manager') return effRole === 'manager' || effRole === 'supervisor' || effRole === 'administrator' || effRole === 'admin';
  if (t === 'supervisor') return effRole === 'supervisor' || effRole === 'administrator' || effRole === 'admin';
  if (t === 'admin' || t === 'administrator') return effRole === 'administrator' || effRole === 'admin';
  return false;
}

export function getInitialTab(role?: string | null): HelpTab {
  const r = typeof role === 'string' ? role.trim().toLowerCase() : '';
  if (r === 'supervisor') return 'supervisor';
  if (r === 'administrator' || r === 'admin') return 'admin';
  if (r === 'manager' || !r) return 'manager';
  return 'errors';
}

export type DemoErrorCode = "400" | "401" | "403" | "404" | "409" | "422" | "413" | "quarantine" | "500" | "502" | "503" | "504";

export interface SimulatedErrorSpec {
  statusText: string;
  envelope: {
    error: {
      code: string;
      message: string;
      request_id: string;
      details: Record<string, any>;
    };
  };
  remediation: string;
}

export const SIMULATED_ERRORS: Record<DemoErrorCode, SimulatedErrorSpec> = {
  "400": {
    statusText: "HTTP 400 Bad Request: Невалидный синтаксис запроса или неверный формат параметров.",
    envelope: {
      error: {
        code: "BAD_REQUEST",
        message: "Синтаксис запроса некорректен или переданы недопустимые параметры.",
        request_id: "req-sim-400-demo",
        details: { invalid_field: "format", reason: "Malformed payload structure" },
      },
    },
    remediation: "Проверьте формат введённых данных и корректность структуры отправляемых параметров.",
  },
  "401": {
    statusText: "HTTP 401 Unauthorized: Отсутствие или истечение срока действия JWT-токена.",
    envelope: {
      error: {
        code: "UNAUTHORIZED",
        message: "Токен сессии отсутствует, просрочен или не прошел проверку подписи.",
        request_id: "req-sim-401-demo",
        details: { auth_scheme: "Bearer", reason: "Token expired" },
      },
    },
    remediation: "Сессия истекла. Авторизуйтесь заново в системе (токен хранится исключительно in-memory, ввод сохранен).",
  },
  "403": {
    statusText: "HTTP 403 Forbidden: Попытка выполнения действия вне ролевых полномочий.",
    envelope: {
      error: {
        code: "FORBIDDEN",
        message: "У текущей роли недостаточно полномочий для выполнения данной операции.",
        request_id: "req-sim-403-demo",
        details: { required_role: "admin | supervisor", current_role: "manager" },
      },
    },
    remediation: "Обратитесь к администратору или руководителю для расширения прав доступа или назначения задачи.",
  },
  "404": {
    statusText: "HTTP 404 Not Found: Zero-Oracle сокрытие при обращении к чужому объекту (152-ФЗ).",
    envelope: {
      error: {
        code: "NOT_FOUND",
        message: "Запрашиваемый ресурс не найден в области видимости текущего пользователя.",
        request_id: "req-sim-404-demo",
        details: { resource_type: "interaction", scope_clause: "owner_isolation_enforced" },
      },
    },
    remediation: "Политика Zero-Oracle (152-ФЗ / ФСТЭК №117): сервер скрывает факт существования чужих данных. Проверьте правильность ID или запросите переназначение у руководителя.",
  },
  "409": {
    statusText: "HTTP 409 Conflict: CAS revision mismatch. Карточка была изменена другим пользователем. Введенные данные сохранены.",
    envelope: {
      error: {
        code: "REVISION_CONFLICT",
        message: "Карточка была изменена другим пользователем. Ожидаемая ревизия устарела.",
        request_id: "req-sim-409-demo",
        details: { expected_revision: 2, current_revision: 3 },
      },
    },
    remediation: "Откройте карточку в соседней вкладке, ознакомьтесь с правками коллеги, скорректируйте данные и повторите сохранение. Введённый текст не сброшен.",
  },
  "422": {
    statusText: "HTTP 422 Unprocessable Entity: Для перехода на этап «Передача материалов» требуется связка программы и продукта.",
    envelope: {
      error: {
        code: "VALIDATION_ERROR",
        message: "Нарушение инварианта бизнес-логики процесса.",
        request_id: "req-sim-422-demo",
        details: { stage: "materials_transfer", missing_fields: ["program_id", "product_id"] },
      },
    },
    remediation: "В модальном окне параметров свяжите валидную совместимую пару «программа + продукт» перед осуществлением перехода.",
  },
  "413": {
    statusText: "HTTP 413 Payload Too Large: Прикрепляемый файл превышает лимит 25 МБ.",
    envelope: {
      error: {
        code: "FILE_TOO_LARGE",
        message: "Размер загружаемого вложения превышает допустимый предел 25 МБ.",
        request_id: "req-sim-413-demo",
        details: { max_bytes: 26214400, actual_bytes: 31457280 },
      },
    },
    remediation: "Сожмите PDF или разбейте архив на тома размером до 25 МБ перед повторной отправкой.",
  },
  "quarantine": {
    statusText: "HTTP 422 File Quarantine: Формат файла заблокирован антивирусным шлюзом (обнаружен исполняемый код).",
    envelope: {
      error: {
        code: "FILE_TYPE_NOT_ALLOWED",
        message: "Файл отклонен шлюзом валидации: недопустимый MIME-тип или опасные magic bytes.",
        request_id: "req-sim-quarantine-demo",
        details: { detected_magic: "MZ executable header", allowed_formats: ["png", "jpeg", "pdf", "zip", "gzip", "rar", "doc", "docx", "xls", "xlsx"] },
      },
    },
    remediation: "Загружайте только легитимные файлы из 10 разрешённых форматов без маскировки исполняемых бинарных файлов.",
  },
  "500": {
    statusText: "HTTP 500 Internal Server Error: Внутренний сбой сервера обработки запроса.",
    envelope: {
      error: {
        code: "INTERNAL_SERVER_ERROR",
        message: "Произошла непредвиденная ошибка на стороне сервера.",
        request_id: "req-sim-500-demo",
        details: { subsystem: "core_engine", retryable: true },
      },
    },
    remediation: "Повторите попытку через несколько секунд. При сохранении ошибки передайте request_id дежурному администратору.",
  },
  "502": {
    statusText: "HTTP 502 Bad Gateway: Некорректный ответ внешнего сервиса интеграции (LMS Zion / Сайт).",
    envelope: {
      error: {
        code: "BAD_GATEWAY",
        message: "Внешний шлюз интеграции вернул некорректный ответ.",
        request_id: "req-sim-502-demo",
        details: { upstream_service: "rtkb.zion-lms.ru", http_status: 502 },
      },
    },
    remediation: "Внешний сервис временно недоступен или вернул поврежденный ответ. Пакет помещен в очередь сверки (Inbox), повторите синхронизацию позже.",
  },
  "503": {
    statusText: "HTTP 503 Service Unavailable: Сервер временно недоступен (техническое обслуживание).",
    envelope: {
      error: {
        code: "SERVICE_UNAVAILABLE",
        message: "Сервис временно перегружен или находится на регламентном обслуживании.",
        request_id: "req-sim-503-demo",
        details: { retry_after_seconds: 30 },
      },
    },
    remediation: "Сервер выполняет регламентные работы или находится под пиковой нагрузкой. Подождите 30 секунд и повторите отправку.",
  },
  "504": {
    statusText: "HTTP 504 Gateway Timeout: Превышен таймаут ожидания ответа внешнего интеграционного шлюза.",
    envelope: {
      error: {
        code: "GATEWAY_TIMEOUT",
        message: "Превышено максимальное время ожидания ответа от внешнего источника.",
        request_id: "req-sim-504-demo",
        details: { timeout_seconds: 15, target_endpoint: "https://rtkb.zion-lms.ru/api/sync" },
      },
    },
    remediation: "Внешний источник не ответил вовремя. Запрос переведен в асинхронную обработку. Ваши данные в форме сохранены.",
  },
};

export interface ScreenshotCallout {
  label: string;
  description: string;
}

export interface DocScreenshotItem {
  id: string;
  filename: string;
  src: string;
  screenNumber: string;
  title: string;
  subtitle: string;
  route: string;
  section: 'user' | 'sysadmin';
  category: 'auth' | 'manager' | 'supervisor' | 'errors' | 'admin' | 'security';
  caption: string;
  callouts: ScreenshotCallout[];
}

export const SCREENSHOTS_CATALOG: Record<string, DocScreenshotItem> = {
  'screen-01': {
    id: 'screen-01',
    filename: 'screen-01-login.png',
    src: '/docs/screenshots/screen-01-login.png',
    screenNumber: '01',
    title: 'Экран авторизации и выбор демонстрационных ролей',
    subtitle: 'Аутентификация через Keycloak OIDC и выбор контекста демонстрационного стенда',
    route: '#/',
    section: 'user',
    category: 'auth',
    caption: 'Стартовый экран системы с возможностью переключения ролей на демонстрационных данных и корпоративной авторизацией.',
    callouts: [
      { label: 'Выбор роли', description: 'Переключение между ролями: Менеджер партнерств, Руководитель, Администратор.' },
      { label: 'Брендинг Gen2', description: 'Соблюдение дизайн-системы Ростелеком: логотип, цвета #7700FF и #FF4F12.' },
      { label: 'Zero-Oracle защита', description: 'Авторизация и ограничения видимости проверяются на стороне сервера (152-ФЗ).' },
    ],
  },
  'screen-02': {
    id: 'screen-02',
    filename: 'screen-02-manager-overview.png',
    src: '/docs/screenshots/screen-02-manager-overview.png',
    screenNumber: '02',
    title: 'Рабочий стол менеджера (Воронка 15 этапов и KPI)',
    subtitle: 'Сводные показатели, карта воронки и оперативный фокус на ближайших задачах',
    route: '#/overview',
    section: 'user',
    category: 'manager',
    caption: 'Дашборд менеджера с метриками активных партнерств, прогрессом по этапам воронки и лентой недавних действий.',
    callouts: [
      { label: 'KPI-счетчики', description: 'Количество партнерств в работе, на подписании и завершенных циклов.' },
      { label: 'Воронка 15 этапов', description: 'Визуализация распределения взаимодействий по 4 фазам жизненного цикла.' },
      { label: 'Оперативный фокус', description: 'Карточки, требующие первоочередного внимания куратора.' },
    ],
  },
  'screen-03': {
    id: 'screen-03',
    filename: 'screen-03-interactions-registry.png',
    src: '/docs/screenshots/screen-03-interactions-registry.png',
    screenNumber: '03',
    title: 'Реестр взаимодействий с фильтрами и поиском',
    subtitle: 'Многокритериальная фильтрация, поиск по вузам и быстрый доступ к карточкам',
    route: '#/interactions',
    section: 'user',
    category: 'manager',
    caption: 'Табличный реестр карточек сотрудничества с фильтрами по этапам, датам и ответственным сотрудникам.',
    callouts: [
      { label: 'Панель фильтров', description: 'Фильтрация по текущему этапу, типу взаимодействия и датам создания.' },
      { label: 'Быстрый поиск', description: 'Поиск по наименованию образовательной организации и номеру договора.' },
      { label: 'Статусные бейджи', description: 'Цветовая индикация этапов воронки в соответствии с брендбуком.' },
    ],
  },
  'screen-04': {
    id: 'screen-04',
    filename: 'screen-04-interaction-card-graph.png',
    src: '/docs/screenshots/screen-04-interaction-card-graph.png',
    screenNumber: '04',
    title: 'Карточка взаимодействия с графом жизненного цикла',
    subtitle: 'Интерактивный граф 15 этапов, метаданные и доступные переходы',
    route: '#/interactions/:id',
    section: 'user',
    category: 'manager',
    caption: 'Детальная карточка партнерства с отображением графа состояний, кнопок переходов и привязанных документов.',
    callouts: [
      { label: 'Граф процесса', description: 'Отображение текущего положения в базовом процессе из 15 этапов.' },
      { label: 'Кнопки переходов', description: 'Primary (шаг вперед), Secondary (возврат на доработку), Danger (отмена).' },
      { label: 'Реквизиты', description: 'Сведения об организации, контакте, договоре и лицензии.' },
    ],
  },
  'screen-05': {
    id: 'screen-05',
    filename: 'screen-05-interaction-d02-prevent.png',
    src: '/docs/screenshots/screen-05-interaction-d02-prevent.png',
    screenNumber: '05',
    title: 'Редактирование параметров и предотвращение дедлока D02',
    subtitle: 'Обязательное связывание программы и продукта перед этапом «Передача материалов»',
    route: '#/interactions/:id (Modal)',
    section: 'user',
    category: 'manager',
    caption: 'Модальное окно редактирования параметров карточки с проверкой совместимости ИТ-программы и ИТ-продукта.',
    callouts: [
      { label: 'Совместимость пар', description: 'Выбор продукта, строго валидируемого по каталогу программ.' },
      { label: 'Защита от дедлока D02', description: 'Без заполненной пары программа+продукт переход на шаг 7 блокируется.' },
      { label: 'CAS-блокировка', description: 'Оптимистический контроль версий expected_revision исключает потерянные правки.' },
    ],
  },
  'screen-06': {
    id: 'screen-06',
    filename: 'screen-06-interaction-transition-rework.png',
    src: '/docs/screenshots/screen-06-interaction-transition-rework.png',
    screenNumber: '06',
    title: 'Модальное окно перехода с обязательным обоснованием',
    subtitle: 'Фиксация регламентных комментариев при возврате на доработку и отмене',
    route: '#/interactions/:id (Transition Modal)',
    section: 'user',
    category: 'manager',
    caption: 'Диалог подтверждения перехода с проверкой обязательного ввода комментария и защитой от потери текста при ошибках (AC21).',
    callouts: [
      { label: 'Обязательный комментарий', description: 'Кнопка подтверждения неактивна до ввода содержательного комментария.' },
      { label: 'Несбрасываемый ввод (AC21)', description: 'При сетевом сбое или 409 Conflict введённый текст остаётся в поле.' },
      { label: 'Запись в Audit Trail', description: 'Комментарий навечно фиксируется в аудит-логе с ревизией карточки.' },
    ],
  },
  'screen-07': {
    id: 'screen-07',
    filename: 'screen-07-attachments-and-audit.png',
    src: '/docs/screenshots/screen-07-attachments-and-audit.png',
    screenNumber: '07',
    title: 'Блок загрузки файлов (25 МБ, 10 форматов) и Audit Trail',
    subtitle: 'Валидация magic bytes, антивирусная проверка и неизменяемый аудит-лог',
    route: '#/interactions/:id#attachments',
    section: 'user',
    category: 'manager',
    caption: 'Зона прикрепления сопроводительных документов с проверкой расширений и хронологическая лента аудита.',
    callouts: [
      { label: 'Лимит 25 МБ', description: 'Клиентская и серверная валидация размера загружаемого документа.' },
      { label: '10 форматов ТЗ', description: 'png, jpeg, pdf, zip, gzip, rar, doc, docx, xls, xlsx с проверкой сигнатур.' },
      { label: 'Audit Trail', description: 'Последовательность событий sequence с фиксацией автора и временных меток.' },
    ],
  },
  'screen-08': {
    id: 'screen-08',
    filename: 'screen-08-supervisor-overview-reassign.png',
    src: '/docs/screenshots/screen-08-supervisor-overview-reassign.png',
    screenNumber: '08',
    title: 'Консоль руководителя и переназначение куратора (Reassign)',
    subtitle: 'Сквозной контроль подразделения (team_id) и мгновенный отзыв доступа (HTTP 404)',
    route: '#/overview (Supervisor)',
    section: 'user',
    category: 'supervisor',
    caption: 'Рабочее место руководителя с возможностью ротации ответственных менеджеров по карточкам подразделения.',
    callouts: [
      { label: 'Командный охват', description: 'Руководитель видит все карточки своего подразделения (team_id).' },
      { label: 'Диалог Reassign', description: 'Передача карточки коллеге с записью события owner_changed.' },
      { label: '152-ФЗ Zero-Oracle', description: 'Прежний менеджер мгновенно получает 404 Not Found при обращении к карточке.' },
    ],
  },
  'screen-09': {
    id: 'screen-09',
    filename: 'screen-09-reports-analytics-export.png',
    src: '/docs/screenshots/screen-09-reports-analytics-export.png',
    screenNumber: '09',
    title: 'Аналитический модуль отчётов (3 среза, экспорт XLSX/PDF)',
    subtitle: 'Срезы Snapshot, Activity, Created с выгрузкой в фирменном стиле Ростелеком',
    route: '#/reports',
    section: 'user',
    category: 'supervisor',
    caption: 'Генератор темпоральных аналитических срезов с настройкой колонок и экспортом в XLSX/PDF/JSON.',
    callouts: [
      { label: '3 темпоральных среза', description: 'Срез на дату (Snapshot), динамика переходов (Activity), созданные (Created).' },
      { label: 'Выбор метрик', description: 'Интерактивный выбор выводимых колонок таблицы.' },
      { label: 'Экспорт по брендбуку', description: 'Фирменная шапка #7700FF в Excel и векторный PDF с колонтитулами.' },
    ],
  },
  'screen-10': {
    id: 'screen-10',
    filename: 'screen-10-admin-overview-telemetry.png',
    src: '/docs/screenshots/screen-10-admin-overview-telemetry.png',
    screenNumber: '10',
    title: 'Панель администратора (Телеметрия LMS/Сайта и каталоги)',
    subtitle: 'Мониторинг очередей интеграций, статус коннекторов и счетчики справочников',
    route: '#/integrations',
    section: 'sysadmin',
    category: 'admin',
    caption: 'Консоль администратора платформы со статусом интеграционных контуров и очередью сверки Reconciliation Inbox.',
    callouts: [
      { label: 'Статус коннекторов', description: 'Мониторинг адаптеров LMS Zion и Сайта образовательных программ.' },
      { label: 'Reconciliation Inbox', description: 'Дедупликация входящих заявок и разрешение коллизий.' },
      { label: 'Каталоги платформы', description: 'Счётчики вузов, контактов, договоров и учебных потоков.' },
    ],
  },
  'screen-11': {
    id: 'screen-11',
    filename: 'screen-11-catalog-import-wizard.png',
    src: '/docs/screenshots/screen-11-catalog-import-wizard.png',
    screenNumber: '11',
    title: 'Мастер двухфазного импорта каталогов (XLSX / CSV)',
    subtitle: 'Фаза 1: Сухой прогон (Dry-Run Preview); Фаза 2: Транзакционный коммит',
    route: '#/catalogs (Import Wizard)',
    section: 'sysadmin',
    category: 'admin',
    caption: 'Мастер пакетной загрузки справочников с предварительной проверкой связей и защитой по Idempotency-Key.',
    callouts: [
      { label: 'Парсер таблиц', description: 'Автоматическое распознавание колонок вуза, контактов, договоров и программ.' },
      { label: 'Dry-Run предпросмотр', description: 'Проверка ошибок структуры данных до выполнения записи в БД.' },
      { label: 'Транзакционный коммит', description: 'Атомарное сохранение валидных записей в единой транзакции.' },
    ],
  },
  'screen-12': {
    id: 'screen-12',
    filename: 'screen-12-workflow-migrator.png',
    src: '/docs/screenshots/screen-12-workflow-migrator.png',
    screenNumber: '12',
    title: 'Мигратор версий процессов (v1 -> v2)',
    subtitle: 'Матрица сопоставления статусов, сухой прогон и блокировка коллизий',
    route: '#/catalogs (Workflow Migrator)',
    section: 'sysadmin',
    category: 'admin',
    caption: 'Инструмент миграции активных взаимодействий при обновлении версий жизненного цикла партнерств.',
    callouts: [
      { label: 'Матрица маппинга', description: 'Сопоставление старых и новых статусов процессов.' },
      { label: 'Защита от коллизий', description: 'Блокировка недопустимого перевода терминальных статусов в активные.' },
      { label: 'Сухой прогон', description: 'Оценка числа затронутых карточек перед фиксацией миграции.' },
    ],
  },
  'screen-13': {
    id: 'screen-13',
    filename: 'screen-13-error-diagnostic-center.png',
    src: '/docs/screenshots/screen-13-error-diagnostic-center.png',
    screenNumber: '13',
    title: 'Справочник кодов ошибок и симулятор сохранения ввода AC21',
    subtitle: 'Интерактивный симулятор обработки сбоев и канонический формат ошибок API',
    route: '#/help (Tab: Errors)',
    section: 'user',
    category: 'errors',
    caption: 'Диагностический центр с рекомендациями по устранению ошибок и живым тестом сохранения введённого текста.',
    callouts: [
      { label: 'Аккордеон ошибок', description: 'Разбор симптомов и действий при кодах 400, 401, 403, 404, 409, 413, 422, 500, 502, 503, 504.' },
      { label: 'Симулятор AC21', description: 'Эмуляция ошибок сервера для доказательства сохранения пользовательского ввода.' },
      { label: 'Канонический Envelope', description: 'Отображение точной JSON-структуры ошибки { error: { code, message, request_id } }.' },
    ],
  },
};

export function DocScreenshotCard({
  item,
  onOpenLightbox,
}: {
  item: DocScreenshotItem;
  onOpenLightbox: (item: DocScreenshotItem) => void;
}) {
  return (
    <figure className="doc-screenshot-card" id={`screenshot-${item.id}`}>
      <div className="doc-screenshot-header">
        <div className="doc-window-controls" aria-hidden="true">
          <span className="window-dot dot-red" />
          <span className="window-dot dot-yellow" />
          <span className="window-dot dot-green" />
        </div>
        <div className="doc-window-address-bar">
          <Icon name="shield" size={12} />
          <span>https://crm.school.rt.ru/{item.route.replace(/^#\/?/, '')}</span>
        </div>
        <div className="doc-screenshot-badge">Экран {item.screenNumber}</div>
      </div>

      <div
        className="doc-screenshot-viewport"
        onClick={() => onOpenLightbox(item)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onOpenLightbox(item);
          }
        }}
        title="Нажмите для полноэкранного просмотра (ESC)"
        aria-label={`Увеличить скриншот: ${item.title}`}
      >
        <img
          src={item.src}
          alt={item.title}
          className="doc-screenshot-img"
          loading="lazy"
        />
        <div className="doc-screenshot-zoom-overlay">
          <Icon name="search" size={22} />
          <span>Нажмите для увеличения</span>
        </div>
      </div>

      <figcaption className="doc-screenshot-caption">
        <div className="doc-screenshot-title-row">
          <strong>{item.title}</strong>
          <span className="doc-screenshot-route-badge">{item.route}</span>
        </div>
        <p className="doc-screenshot-subtitle">{item.caption}</p>

        {item.callouts && item.callouts.length > 0 && (
          <div className="doc-callouts-list">
            <span className="doc-callouts-label">Ключевые элементы экрана:</span>
            {item.callouts.map((callout, index) => (
              <div key={index} className="doc-callout-item">
                <span className="callout-badge">{index + 1}</span>
                <div className="callout-text">
                  <strong>{callout.label}:</strong> {callout.description}
                </div>
              </div>
            ))}
          </div>
        )}
      </figcaption>
    </figure>
  );
}

export function DocScreenshotLightbox({
  item,
  onClose,
}: {
  item: DocScreenshotItem | null;
  onClose: () => void;
}) {
  useEffect(() => {
    if (!item) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    window.addEventListener('keydown', handleKeyDown);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [item, onClose]);

  if (!item) return null;

  return (
    <div
      className="doc-lightbox-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          onClose();
        }
      }}
      role="dialog"
      aria-modal="true"
      aria-label={item.title}
    >
      <div className="doc-lightbox-container">
        <div className="doc-lightbox-header">
          <div className="doc-lightbox-title-block">
            <div className="doc-lightbox-eyebrow">ЭКРАН {item.screenNumber} · {item.route}</div>
            <h3>{item.title}</h3>
          </div>
          <button
            className="icon-button doc-lightbox-close-btn"
            onClick={onClose}
            aria-label="Закрыть полноэкранный просмотр (ESC)"
            title="Закрыть (ESC)"
          >
            <Icon name="close" size={22} />
          </button>
        </div>

        <div className="doc-lightbox-image-wrap">
          <img
            src={item.src}
            alt={item.title}
            className="doc-lightbox-image"
          />
        </div>

        <div className="doc-lightbox-footer">
          <p className="doc-lightbox-caption">{item.caption}</p>
          {item.callouts && item.callouts.length > 0 && (
            <div className="doc-lightbox-callouts">
              {item.callouts.map((c, i) => (
                <div key={i} className="doc-lightbox-callout-item">
                  <span className="callout-badge">{i + 1}</span>
                  <div><strong>{c.label}:</strong> {c.description}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export type GuideSection = 'USER_GUIDE' | 'SYSADMIN_GUIDE';

export function HelpPage() {
  const { me } = useAuth();
  const role = me?.role;

  const [guideSection, setGuideSection] = useState<GuideSection>('USER_GUIDE');
  const [activeTab, setActiveTab] = useState<HelpTab>(() => getInitialTab(role));
  const [openError, setOpenError] = useState<string | null>('409');
  const [lightboxScreenshot, setLightboxScreenshot] = useState<DocScreenshotItem | null>(null);

  // Guard against invalid activeTab (auto-fallback if tab is inaccessible for current role)
  useEffect(() => {
    if (!isHelpTabAllowed(activeTab, role)) {
      setActiveTab(getInitialTab(role));
    }
  }, [activeTab, role]);

  function handleSelectGuide(section: GuideSection) {
    setGuideSection(section);
    if (section === 'USER_GUIDE') {
      if (activeTab === 'admin' || activeTab === 'security') {
        setActiveTab('manager');
      }
    } else {
      if (activeTab !== 'admin' && activeTab !== 'security') {
        setActiveTab(isHelpTabAllowed('admin', role) ? 'admin' : 'security');
      }
    }
  }

  // AC21 Interactive Form Input Preservation Tester State
  const [demoTitle, setDemoTitle] = useState('Взаимодействие с МГТУ по программе «Сетевые технологии»');
  const [demoComment, setDemoComment] = useState('Направлен запрос на корректировку договора перед подписанием.');
  const [demoErrorType, setDemoErrorType] = useState<DemoErrorCode | '409' | '422' | '413' | 'quarantine'>('409');
  const [demoSimulatedError, setDemoSimulatedError] = useState<string | null>(null);
  const [demoPreserveSuccess, setDemoPreserveSuccess] = useState(false);
  const [demoEnvelope, setDemoEnvelope] = useState<any | null>(null);
  const [demoRemediation, setDemoRemediation] = useState<string | null>(null);

  function handleTriggerDemoError(e: React.FormEvent) {
    e.preventDefault();
    setDemoPreserveSuccess(true);
    const spec = SIMULATED_ERRORS[demoErrorType as DemoErrorCode] || SIMULATED_ERRORS['409'];
    setDemoSimulatedError(spec.statusText);
    setDemoEnvelope(spec.envelope);
    setDemoRemediation(spec.remediation);
  }

  return (
    <div className="help-center">
      <div className="page-heading help-page-heading">
        <div>
          <div className="eyebrow">БАЗА ЗНАНИЙ И ДОКУМЕНТАЦИЯ (ТЗ п. 5 / B34 / AC21)</div>
          <h1>Центр документации CRM</h1>
          <p>Встроенные руководства пользователя и системного администратора со скриншотами интерфейса.</p>
        </div>
        <div className="help-header-actions">
          <Button
            variant="secondary"
            className="help-print-btn"
            onClick={() => window.print()}
            title="Распечатать текущее руководство или сохранить в PDF (Ctrl+P / Cmd+P)"
          >
            <Icon name="download" size={16} />
            <span>Печать / PDF экспорт</span>
          </Button>
          <a
            href="/docs/USER_GUIDE.md"
            download="USER_GUIDE.md"
            className="button button-ghost help-download-btn"
            title="Скачать руководство пользователя в формате Markdown"
          >
            <Icon name="file" size={16} />
            <span>Скачать Markdown</span>
          </a>
          {me && (
            <div className="user-role-chip">
              <Icon name="shield" size={16} />
              <span>Ваша текущая роль: <strong>{me.role}</strong></span>
            </div>
          )}
        </div>
      </div>

      {/* Root Guide Selector Tabs (USER_GUIDE vs SYSADMIN_GUIDE) */}
      <div className="guide-mode-selector" role="tablist" aria-label="Разделы документации">
        <button
          role="tab"
          aria-selected={guideSection === 'USER_GUIDE'}
          className={`guide-mode-btn ${guideSection === 'USER_GUIDE' ? 'active' : ''}`}
          onClick={() => handleSelectGuide('USER_GUIDE')}
        >
          <Icon name="book" size={20} />
          <div>
            <strong>Руководство пользователя</strong>
            <small>КАМ-менеджер, руководитель направления, воронка 15 этапов, отчёты и регламенты при ошибках</small>
          </div>
        </button>

        <button
          role="tab"
          aria-selected={guideSection === 'SYSADMIN_GUIDE'}
          className={`guide-mode-btn ${guideSection === 'SYSADMIN_GUIDE' ? 'active' : ''}`}
          onClick={() => handleSelectGuide('SYSADMIN_GUIDE')}
        >
          <Icon name="shield" size={20} />
          <div>
            <strong>Руководство системного администратора</strong>
            <small>Развертывание, импорт каталогов, миграция процессов, интеграции LMS/Сайта, аудит 152-ФЗ</small>
          </div>
        </button>
      </div>

      {/* Role and Topic Tabs */}
      <div className="help-tabs" role="tablist">
        {isHelpTabAllowed('manager', role) && (
          <button
            role="tab"
            aria-selected={activeTab === 'manager'}
            className={`help-tab-btn ${activeTab === 'manager' ? 'active' : ''}`}
            onClick={() => { setActiveTab('manager'); setGuideSection('USER_GUIDE'); }}
          >
            <Icon name="layers" size={18} />
            <span>Менеджер</span>
            <b>15 этапов воронки</b>
          </button>
        )}

        {isHelpTabAllowed('supervisor', role) && (
          <button
            role="tab"
            aria-selected={activeTab === 'supervisor'}
            className={`help-tab-btn ${activeTab === 'supervisor' ? 'active' : ''}`}
            onClick={() => { setActiveTab('supervisor'); setGuideSection('USER_GUIDE'); }}
          >
            <Icon name="users" size={18} />
            <span>Руководитель</span>
            <b>Квоты и отчёты</b>
          </button>
        )}

        {isHelpTabAllowed('admin', role) && (
          <button
            role="tab"
            aria-selected={activeTab === 'admin'}
            className={`help-tab-btn ${activeTab === 'admin' ? 'active' : ''}`}
            onClick={() => { setActiveTab('admin'); setGuideSection('SYSADMIN_GUIDE'); }}
          >
            <Icon name="refresh" size={18} />
            <span>Администратор</span>
            <b>Импорт и миграции</b>
          </button>
        )}

        {isHelpTabAllowed('errors', role) && (
          <button
            role="tab"
            aria-selected={activeTab === 'errors'}
            className={`help-tab-btn ${activeTab === 'errors' ? 'active' : ''}`}
            onClick={() => { setActiveTab('errors'); setGuideSection('USER_GUIDE'); }}
          >
            <Icon name="alert" size={18} />
            <span>Справочник ошибок</span>
            <b>Коды HTTP / CAS</b>
          </button>
        )}

        {isHelpTabAllowed('security', role) && (
          <button
            role="tab"
            aria-selected={activeTab === 'security'}
            className={`help-tab-btn ${activeTab === 'security' ? 'active' : ''}`}
            onClick={() => { setActiveTab('security'); setGuideSection('SYSADMIN_GUIDE'); }}
          >
            <Icon name="shield" size={18} />
            <span>Безопасность 152-ФЗ</span>
            <b>ФСТЭК №117</b>
          </button>
        )}
      </div>

      {/* Tab 1: Менеджер */}
      {activeTab === 'manager' && isHelpTabAllowed('manager', role) && (
        <div className="help-tab-content">
          <div className="role-intro-banner">
            <div className="role-intro-icon">
              <Icon name="layers" size={28} />
            </div>
            <div>
              <h2>Регламент менеджера: Ведение воронки и карточек взаимодействий</h2>
              <p>
                Менеджер партнерств отвечает за полный жизненный цикл взаимодействия с вузом — от первого контакта до проведения занятий и завершения сотрудничества.
              </p>
            </div>
          </div>

          {/* Funnel Visual Map: 4 Phases & 15 Stages */}
          <div className="panel funnel-map-panel">
            <div className="panel-heading">
              <div>
                <h2>Карта воронки сотрудничества (15 этапов, 4 фазы)</h2>
                <p>Базовый декларативный процесс согласно спецификации ТЗ и эталону <code>04-base-workflow.json</code>.</p>
              </div>
              <span className="stage-chip chip-working">13 активных + 2 терминальных</span>
            </div>

            <div className="funnel-phases-grid">
              <div className="funnel-phase-card">
                <div className="phase-header">
                  <span className="badge-phase">Фаза 1</span>
                  <h3>Инициация</h3>
                </div>
                <ol className="phase-stages-list">
                  <li>
                    <span className="stage-num">1</span>
                    <div>
                      <strong>Поиск контактов</strong>
                      <small><code>contact_search</code> · Определение ответственных в вузе</small>
                    </div>
                  </li>
                  <li>
                    <span className="stage-num">2</span>
                    <div>
                      <strong>Уточнение потребности</strong>
                      <small><code>needs_clarification</code> · Выявление запроса вуза</small>
                    </div>
                  </li>
                  <li>
                    <span className="stage-num">3</span>
                    <div>
                      <strong>Встреча с вузом</strong>
                      <small><code>meeting</code> · Согласование условий партнерства</small>
                    </div>
                  </li>
                </ol>
              </div>

              <div className="funnel-phase-card">
                <div className="phase-header">
                  <span className="badge-phase">Фаза 2</span>
                  <h3>Договоры</h3>
                </div>
                <ol className="phase-stages-list">
                  <li>
                    <span className="stage-num">4</span>
                    <div>
                      <strong>Обмен документами</strong>
                      <small><code>document_exchange</code> · Подготовка пакета соглашений</small>
                    </div>
                  </li>
                  <li>
                    <span className="stage-num">5</span>
                    <div>
                      <strong>Корректировка</strong>
                      <small><code>document_revision</code> · Опциональная доработка договора</small>
                    </div>
                  </li>
                  <li>
                    <span className="stage-num">6</span>
                    <div>
                      <strong>Подписание документов</strong>
                      <small><code>document_signing</code> · Подписание (с возвратом на шаг 5)</small>
                    </div>
                  </li>
                </ol>
              </div>

              <div className="funnel-phase-card">
                <div className="phase-header">
                  <span className="badge-phase">Фаза 3</span>
                  <h3>Внедрение</h3>
                </div>
                <ol className="phase-stages-list">
                  <li>
                    <span className="stage-num">7</span>
                    <div>
                      <strong>Передача материалов</strong>
                      <small><code>materials_transfer</code> · Обязательны Программа + Продукт!</small>
                    </div>
                  </li>
                  <li>
                    <span className="stage-num">8</span>
                    <div>
                      <strong>Сопровождение</strong>
                      <small><code>deployment</code> · Консультации и техническая помощь</small>
                    </div>
                  </li>
                  <li>
                    <span className="stage-num">9</span>
                    <div>
                      <strong>Обучение преподавателей</strong>
                      <small><code>teacher_training</code> · Подготовка преподавателей вуза</small>
                    </div>
                  </li>
                </ol>
              </div>

              <div className="funnel-phase-card">
                <div className="phase-header">
                  <span className="badge-phase">Фаза 4</span>
                  <h3>Учебный процесс</h3>
                </div>
                <ol className="phase-stages-list">
                  <li>
                    <span className="stage-num">10</span>
                    <div>
                      <strong>Актуализация программы</strong>
                      <small><code>curriculum_update</code> · Включение продукта в план</small>
                    </div>
                  </li>
                  <li>
                    <span className="stage-num">11</span>
                    <div>
                      <strong>Ведение занятий</strong>
                      <small><code>classes</code> · Проведение лекций и лабораторных</small>
                    </div>
                  </li>
                  <li>
                    <span className="stage-num">12</span>
                    <div>
                      <strong>Обновление материалов</strong>
                      <small><code>materials_update</code> · Актуализация пособий</small>
                    </div>
                  </li>
                  <li>
                    <span className="stage-num">13</span>
                    <div>
                      <strong>Повышение квалификации</strong>
                      <small><code>teacher_upskilling</code> · Допускает возврат к занятиям</small>
                    </div>
                  </li>
                </ol>
              </div>
            </div>

            <div className="terminal-stages-bar">
              <strong>Терминальные исходы (необратимые состояния):</strong>
              <div style={{ display: 'flex', gap: '16px', marginTop: '6px' }}>
                <span className="stage-chip chip-terminal-success">
                  <Icon name="check" size={14} />
                  14. Завершено успешно (<code>completed</code>)
                </span>
                <span className="stage-chip chip-terminal-cancel">
                  <Icon name="close" size={14} />
                  15. Отменено (<code>cancelled</code>)
                </span>
              </div>
            </div>
          </div>

          {/* Manager Illustrated Workflows: Screens 01, 02, 03 */}
          <div className="doc-screenshots-section">
            <DocScreenshotCard item={SCREENSHOTS_CATALOG['screen-01']} onOpenLightbox={setLightboxScreenshot} />
            <DocScreenshotCard item={SCREENSHOTS_CATALOG['screen-02']} onOpenLightbox={setLightboxScreenshot} />
            <DocScreenshotCard item={SCREENSHOTS_CATALOG['screen-03']} onOpenLightbox={setLightboxScreenshot} />
          </div>

          {/* Scenario Cards Grid */}
          <div className="scenario-grid">
            <div className="scenario-card">
              <div className="scenario-card-header">
                <span className="scenario-step-badge">1</span>
                <h3>Создание и ведение карточки</h3>
              </div>
              <p>
                Взаимодействие создается для каждого отдельного цикла сотрудничества. При создании карточка автоматически закрепляется за текущим менеджером.
              </p>
              <ul className="scenario-bullet-list">
                <li>Реквизиты карточки редактируются через кнопку «Редактировать параметры».</li>
                <li>Каждое изменение проверяет версию карточки через CAS (<code>expected_revision</code>).</li>
                <li>История изменений фиксируется в аудит-логе с инкрементом ревизии.</li>
              </ul>
              <DocScreenshotCard item={SCREENSHOTS_CATALOG['screen-04']} onOpenLightbox={setLightboxScreenshot} />
            </div>

            <div className="scenario-card">
              <div className="scenario-card-header">
                <span className="scenario-step-badge">2</span>
                <h3>Переходы по воронке и кнопки</h3>
              </div>
              <p>
                В интерфейсе отображаются все допустимые альтернативные переходы с цветовой дифференциацией:
              </p>
              <div className="button-legend-box">
                <div>
                  <span className="legend-btn-sample primary">Фиолетовая кнопка</span>
                  <span>Прямой шаг вперед по этапу воронки (Primary)</span>
                </div>
                <div>
                  <span className="legend-btn-sample secondary">Серая кнопка</span>
                  <span>Возврат на доработку или повторный цикл (Secondary)</span>
                </div>
                <div>
                  <span className="legend-btn-sample danger">Красная кнопка</span>
                  <span>Отмена взаимодействия на текущем этапе (Danger)</span>
                </div>
              </div>
            </div>

            <div className="scenario-card">
              <div className="scenario-card-header">
                <span className="scenario-step-badge">3</span>
                <h3>Регламент обязательных комментариев</h3>
              </div>
              <p>
                Для фиксации причин отклонения или возврата система требует обязательного комментария:
              </p>
              <ul className="scenario-bullet-list">
                <li>При возврате на доработку (<code>rework</code>) ввод комментария <strong>обязателен</strong>.</li>
                <li>При отмене взаимодействия (<code>cancellation</code>) причина отмены <strong>обязательна</strong>.</li>
                <li>Текст комментария навечно сохраняется в аудит-логе с указанием автора и времени.</li>
              </ul>
              <DocScreenshotCard item={SCREENSHOTS_CATALOG['screen-06']} onOpenLightbox={setLightboxScreenshot} />
            </div>

            <div className="scenario-card">
              <div className="scenario-card-header">
                <span className="scenario-step-badge">4</span>
                <h3>Вложения и документы (25 МБ, 10 форматов)</h3>
              </div>
              <p>
                К карточке можно прикреплять договоры, соглашения, программы и сканы подписей:
              </p>
              <ul className="scenario-bullet-list">
                <li>Строгий лимит размера: <strong>до 25 МБ</strong> на файл.</li>
                <li>Ровно 10 разрешенных форматов ТЗ: <code>png, jpeg, pdf, zip, gzip, rar, doc, docx, xls, xlsx</code>.</li>
                <li>Проверка magic bytes: маскировка исполняемых файлов блокируется (HTTP 422).</li>
                <li>Файлы изолированы на сервере, скачивание защищено проверкой прав доступа.</li>
              </ul>
              <DocScreenshotCard item={SCREENSHOTS_CATALOG['screen-07']} onOpenLightbox={setLightboxScreenshot} />
            </div>

            <div className="scenario-card scenario-highlight warning">
              <div className="scenario-card-header">
                <span className="badge-warning">ВНИМАНИЕ (Дедлок D02)</span>
                <h3>Предотвращение дедлока D02</h3>
              </div>
              <p>
                <strong>Критическое правило:</strong> Карточка не может перейти на этап «Передача материалов и лицензии» (шаг 7), если в ней не выбрана пара ИТ-программы и ИТ-продукта!
              </p>
              <div className="action-hint-box">
                <Icon name="spark" size={16} />
                <span>
                  <strong>Решение:</strong> Нажмите «Редактировать параметры» на карточке, выберите совместимую программу и продукт из каталога, затем сохраните изменения. Дедлок будет устранен.
                </span>
              </div>
              <DocScreenshotCard item={SCREENSHOTS_CATALOG['screen-05']} onOpenLightbox={setLightboxScreenshot} />
            </div>

            <div className="scenario-card scenario-highlight important">
              <div className="scenario-card-header">
                <span className="badge-important">ВАЖНО (152-ФЗ / Scope)</span>
                <h3>Изоляция доступа и сокрытие данных</h3>
              </div>
              <p>
                В соответствии с требованиями 152-ФЗ менеджер видит исключительно закрепленные за ним карточки (<code>owner_id == user.id</code>).
              </p>
              <ul className="scenario-bullet-list">
                <li>Попытка запросить чужую карточку по прямому URL вернет <strong>строго HTTP 404 Not Found</strong> (сокрытие факта существования записи).</li>
                <li>JWT-токены удерживаются только в памяти вкладки (in-memory) без сохранения в localStorage.</li>
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* Tab 2: Руководитель */}
      {activeTab === 'supervisor' && isHelpTabAllowed('supervisor', role) && (
        <div className="help-tab-content">
          <div className="role-intro-banner supervisor">
            <div className="role-intro-icon">
              <Icon name="users" size={28} />
            </div>
            <div>
              <h2>Регламент руководителя: Управление командой, квоты и аналитический движок</h2>
              <p>
                Руководитель курирует взаимодействие менеджеров территориального подразделения (<code>team_id</code>), переназначает ответственных и выгружает аналитические отчеты.
              </p>
            </div>
          </div>

          <div className="scenario-grid">
            <div className="scenario-card">
              <div className="scenario-card-header">
                <span className="scenario-step-badge">1</span>
                <h3>Управление квотами и территориальный контроль</h3>
              </div>
              <p>
                Руководитель обладает полномочиями сквозного просмотра всех взаимодействий внутри своей команды:
              </p>
              <ul className="scenario-bullet-list">
                <li>Контроль распределения партнерств по вузам региона.</li>
                <li>Предотвращение дублирования контактов и параллельных переговоров.</li>
                <li>Соблюдение квот на подключение учебных заведений к ИТ-Школе.</li>
              </ul>
            </div>

            <div className="scenario-card">
              <div className="scenario-card-header">
                <span className="scenario-step-badge">2</span>
                <h3>Переназначение ответственного (Reassign)</h3>
              </div>
              <p>
                В случае отпуска, ротации или смены куратора карточка может быть переназначена новому менеджеру:
              </p>
              <ul className="scenario-bullet-list">
                <li>Переназначение доступно из карточки взаимодействия внутри своей команды.</li>
                <li><strong>Мгновенный отзыв доступа:</strong> Прежний менеджер немедленно теряет доступ к карточке (HTTP 404).</li>
                <li>В аудит-логе фиксируется событие передачи с указанием прежнего и нового владельца.</li>
              </ul>
              <DocScreenshotCard item={SCREENSHOTS_CATALOG['screen-08']} onOpenLightbox={setLightboxScreenshot} />
            </div>

            <div className="scenario-card">
              <div className="scenario-card-header">
                <span className="scenario-step-badge">3</span>
                <h3>Аналитический движок 3 срезов (AC11, AC14, AC16)</h3>
              </div>
              <p>
                В разделе «Отчеты» реализован движок построения темпоральных аналитических срезов:
              </p>
              <ul className="scenario-bullet-list">
                <li><strong>Срез на дату (Snapshot):</strong> Состояние портфеля партнерств на момент времени <code>T_as_of</code> с учетом горизонта <code>knowledge_cutoff</code>.</li>
                <li><strong>Динамика переходов (Activity):</strong> Переходы статусов за период с привязкой к историческому ответственному (<code>owner_at_event</code>).</li>
                <li><strong>Созданные карточки (Created):</strong> Привлечение новых вузов за выбранный интервал.</li>
              </ul>
              <DocScreenshotCard item={SCREENSHOTS_CATALOG['screen-09']} onOpenLightbox={setLightboxScreenshot} />
            </div>

            <div className="scenario-card">
              <div className="scenario-card-header">
                <span className="scenario-step-badge">4</span>
                <h3>Бинарный и векторный экспорт отчетов</h3>
              </div>
              <p>
                Генераторы отчетов формируют файлы строго по брендбуку ПАО «Ростелеком»:
              </p>
              <div className="export-formats-showcase">
                <div className="format-item">
                  <span className="format-badge format-xls">XLSX</span>
                  <div>
                    <strong>Microsoft Excel (.xlsx)</strong>
                    <small>Шапка #7700FF, чередование строк #F4F5F8, лист параметров фильтрации.</small>
                  </div>
                </div>
                <div className="format-item">
                  <span className="format-badge format-pdf">PDF</span>
                  <div>
                    <strong>Векторный PDF (.pdf)</strong>
                    <small>Колонтитул Ростелеком, альбомная ориентация, сквозная нумерация «Стр. X из Y».</small>
                  </div>
                </div>
                <div className="format-item">
                  <span className="format-badge format-doc">JSON</span>
                  <div>
                    <strong>Машиночитаемый JSON</strong>
                    <small>Структурированные DTO для межсистемной интеграции и BI-систем.</small>
                  </div>
                </div>
              </div>
            </div>

            <div className="scenario-card scenario-highlight important">
              <div className="scenario-card-header">
                <span className="badge-important">ВАЖНО</span>
                <h3>Шлюз интеграций и показатели LMS Zion</h3>
              </div>
              <p>
                Руководителю доступен раздел «Интеграции» для просмотра учебной метрики востребованности:
              </p>
              <ul className="scenario-bullet-list">
                <li>Количество активных учебных потоков в вузах команды.</li>
                <li>Число зачисленных студентов и процент успешного окончания.</li>
                <li>Сводные коэффициенты посещаемости по программам ИТ-Школы.</li>
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* Tab 3: Администратор */}
      {activeTab === 'admin' && isHelpTabAllowed('admin', role) && (
        <div className="help-tab-content">
          <div className="role-intro-banner admin">
            <div className="role-intro-icon">
              <Icon name="refresh" size={28} />
            </div>
            <div>
              <h2>Регламент администратора: Инфраструктура, импорт и миграции процессов</h2>
              <p>
                Администратор управляет справочниками, проводит двухфазный импорт из Excel, разрешает коллизии очереди сверки и выполняет миграции версий workflow.
              </p>
            </div>
          </div>

          <div className="scenario-grid">
            <div className="scenario-card">
              <div className="scenario-card-header">
                <span className="scenario-step-badge">0</span>
                <h3>Развертывание платформы и конфигурация окружения</h3>
              </div>
              <p>
                Платформа CRM разворачивается в изолированном Docker-окружении со строгим разделением сервисных контуров:
              </p>
              <ul className="scenario-bullet-list">
                <li><strong>Инфраструктура:</strong> FastAPI-сервер, Nginx reverse proxy, PostgreSQL 16 и Keycloak OIDC.</li>
                <li><strong>Конфигурация .env:</strong> Защита секретов, параметры подключения к БД и таймауты интеграционных адаптеров.</li>
                <li><strong>Безопасность портов:</strong> Сервис PostgreSQL доступен исключительно во внутренней сети контейнеров.</li>
              </ul>
            </div>

            <div className="scenario-card">
              <div className="scenario-card-header">
                <span className="scenario-step-badge">1</span>
                <h3>Двухфазный мастер импорта каталогов</h3>
              </div>
              <p>
                Загрузка организаций, контактов и договоров из файлов Excel (XLSX, XLS) и CSV:
              </p>
              <ul className="scenario-bullet-list">
                <li><strong>Фаза 1 (Dry-Run Preview):</strong> Сервер проверяет корректность типов, обязательных колонок и связей без внесения изменений в БД.</li>
                <li><strong>Фаза 2 (Transactional Commit):</strong> Применение валидных строк в единой транзакции с защитой от повторных отправок по <code>Idempotency-Key</code>.</li>
                <li>Автоматическое определение колонок: Вуз, Тип, Контакт, Телефон, Email, Программа, Продукт.</li>
              </ul>
              <DocScreenshotCard item={SCREENSHOTS_CATALOG['screen-11']} onOpenLightbox={setLightboxScreenshot} />
            </div>

            <div className="scenario-card">
              <div className="scenario-card-header">
                <span className="scenario-step-badge">2</span>
                <h3>Шлюз интеграций и Reconciliation Inbox</h3>
              </div>
              <p>
                Прием и нормализация пакетов данных от внешних контрагентов:
              </p>
              <ul className="scenario-bullet-list">
                <li>Коннекторы LMS Zion (<code>mock_lms</code>) и Сайта Laravel (<code>mock_website</code>).</li>
                <li>Строгая дедупликация по ключу <code>(source, entity_type, external_id, source_revision)</code>.</li>
                <li>Разрешение заявок вузов: привязка к существующему вузу, создание новой организации или отклонение.</li>
              </ul>
              <DocScreenshotCard item={SCREENSHOTS_CATALOG['screen-10']} onOpenLightbox={setLightboxScreenshot} />
            </div>

            <div className="scenario-card scenario-highlight warning">
              <div className="scenario-card-header">
                <span className="badge-warning">КРИТИЧЕСКАЯ ОПЕРАЦИЯ</span>
                <h3>Мигратор версий процессов (B17 / R06)</h3>
              </div>
              <p>
                Перевод активных взаимодействий между версиями графа (v1 → v2):
              </p>
              <ul className="scenario-bullet-list">
                <li>Матрица сопоставления статусов с блокировкой терминальных в активные.</li>
                <li>Сухой прогон (Dry-Run Preview) с подсчетом затронутых карточек и коллизий слияния.</li>
                <li>Транзакционный коммит с записью события <code>workflow_migrated</code> в аудит-лог.</li>
              </ul>
              <DocScreenshotCard item={SCREENSHOTS_CATALOG['screen-12']} onOpenLightbox={setLightboxScreenshot} />
            </div>

            <div className="scenario-card">
              <div className="scenario-card-header">
                <span className="scenario-step-badge">4</span>
                <h3>Управление матрицей программ и продуктов</h3>
              </div>
              <p>
                Обеспечение валидности пар программы и продукта в справочниках:
              </p>
              <ul className="scenario-bullet-list">
                <li>Поддержание связей <code>ProgramProductLink</code>.</li>
                <li>Предотвращение привязки несовместимых продуктов в карточках менеджеров.</li>
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* Tab 4: Справочник ошибок */}
      {activeTab === 'errors' && (
        <div className="help-tab-content">
          <div className="role-intro-banner">
            <div className="role-intro-icon">
              <Icon name="alert" size={28} />
            </div>
            <div>
              <h2>Интерактивный справочник кодов ошибок и диагностика</h2>
              <p>
                Каждая ошибка сопровождается четким планом действий. В соответствии с AC21, при любых ошибках валидации и конфликтах введенный пользователем текст сохраняется в памяти без сброса форм.
              </p>
            </div>
          </div>

          <DocScreenshotCard item={SCREENSHOTS_CATALOG['screen-13']} onOpenLightbox={setLightboxScreenshot} />

          {/* Accordion List */}
          <div className="error-accordion">
            {/* 409 Conflict */}
            <div className={`accordion-item ${openError === '409' ? 'open' : ''}`}>
              <button
                className="accordion-header"
                onClick={() => setOpenError(openError === '409' ? null : '409')}
                aria-expanded={openError === '409'}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <span className="error-code-badge badge-409">409 Conflict</span>
                  <strong>REVISION_CONFLICT / CAS Mismatch</strong>
                </div>
                <Icon name={openError === '409' ? 'chevron' : 'down'} size={18} />
              </button>
              {openError === '409' && (
                <div className="accordion-body">
                  <div className="error-body-grid">
                    <div>
                      <span className="eyebrow">СИМПТОМ И ПЕРВОПРИЧИНА</span>
                      <p>
                        Конфликт версий при одновременном редактировании. Переданная ревизия <code>expected_revision</code> устарела: другой менеджер или руководитель успел сохранить изменения в этой карточке.
                      </p>
                    </div>
                    <div>
                      <span className="eyebrow">ЧТО ДЕЛАТЬ ПОЛЬЗОВАТЕЛЮ</span>
                      <p>
                        Введенный вами текст в модальном окне <strong>не сбрасывается и сохраняется в памяти</strong>! Откройте карточку в соседней вкладке, ознакомьтесь с правками коллеги, скорректируйте данные и повторите сохранение.
                      </p>
                    </div>
                  </div>
                  <div className="error-invariant-note">
                    <Icon name="shield" size={16} />
                    <span>Инвариант: Оптимистическая CAS-блокировка исключает перезапись чужих изменений (Lost Update).</span>
                  </div>
                </div>
              )}
            </div>

            {/* 422 Unprocessable Entity - Mapping & Transitions */}
            <div className={`accordion-item ${openError === '422_mapping' ? 'open' : ''}`}>
              <button
                className="accordion-header"
                onClick={() => setOpenError(openError === '422_mapping' ? null : '422_mapping')}
                aria-expanded={openError === '422_mapping'}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <span className="error-code-badge badge-422">422 Unprocessable</span>
                  <strong>VALIDATION_ERROR / MAPPING_ERROR / Incompatible Subject</strong>
                </div>
                <Icon name={openError === '422_mapping' ? 'chevron' : 'down'} size={18} />
              </button>
              {openError === '422_mapping' && (
                <div className="accordion-body">
                  <div className="error-body-grid">
                    <div>
                      <span className="eyebrow">СИМПТОМ И ПЕРВОПРИЧИНА</span>
                      <p>
                        Нарушение инварианта бизнес-логики: попытка перевести терминальный статус (Завершено, Отменено) в рабочий при миграции, попытка перехода на «Передача материалов» без указания программы/продукта, либо несовместимая пара «программа + продукт».
                      </p>
                    </div>
                    <div>
                      <span className="eyebrow">ЧТО ДЕЛАТЬ ПОЛЬЗОВАТЕЛЮ</span>
                      <p>
                        В модальном окне редактирования параметров выберите совместимый ИТ-продукт для указанной ИТ-программы. В миграторе процессов сопоставьте терминальные статусы исключительно с терминальными статусами новой версии.
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* 413 Payload Too Large */}
            <div className={`accordion-item ${openError === '413' ? 'open' : ''}`}>
              <button
                className="accordion-header"
                onClick={() => setOpenError(openError === '413' ? null : '413')}
                aria-expanded={openError === '413'}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <span className="error-code-badge badge-413">413 Payload Too Large</span>
                  <strong>FILE_TOO_LARGE (Лимит 25 МБ)</strong>
                </div>
                <Icon name={openError === '413' ? 'chevron' : 'down'} size={18} />
              </button>
              {openError === '413' && (
                <div className="accordion-body">
                  <div className="error-body-grid">
                    <div>
                      <span className="eyebrow">СИМПТОМ И ПЕРВОПРИЧИНА</span>
                      <p>
                        Размер прикрепляемого документа превышает 25 МБ (26 214 400 байт). Защита дискового пространства и сетевого канала.
                      </p>
                    </div>
                    <div>
                      <span className="eyebrow">ЧТО ДЕЛАТЬ ПОЛЬЗОВАТЕЛЮ</span>
                      <p>
                        CRM проверяет размер файла на клиенте перед отправкой и блокирует передачу. Сожмите PDF или разбейте архив на тома размером до 25 МБ перед загрузкой.
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* 422 File Quarantine */}
            <div className={`accordion-item ${openError === '422_quarantine' ? 'open' : ''}`}>
              <button
                className="accordion-header"
                onClick={() => setOpenError(openError === '422_quarantine' ? null : '422_quarantine')}
                aria-expanded={openError === '422_quarantine'}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <span className="error-code-badge badge-422">422 File Quarantine</span>
                  <strong>FILE_TYPE_NOT_ALLOWED / Dangerous Magic Bytes</strong>
                </div>
                <Icon name={openError === '422_quarantine' ? 'chevron' : 'down'} size={18} />
              </button>
              {openError === '422_quarantine' && (
                <div className="accordion-body">
                  <div className="error-body-grid">
                    <div>
                      <span className="eyebrow">СИМПТОМ И ПЕРВОПРИЧИНА</span>
                      <p>
                        Расширение файла отсутствует в белом списке 10 форматов ТЗ либо его побайтовая сигнатура (magic bytes) содержит опасный исполняемый код (<code>MZ</code>, <code>ELF</code>, <code>#!</code>, <code>&lt;?php</code>, <code>&lt;script</code>).
                      </p>
                    </div>
                    <div>
                      <span className="eyebrow">ЧТО ДЕЛАТЬ ПОЛЬЗОВАТЕЛЮ</span>
                      <p>
                        Переименование <code>.exe</code> в <code>.pdf</code> блокируется сервером. Загружайте исключительно легитимные документы в 10 разрешенных форматах: <code>png, jpeg, pdf, zip, gzip, rar, doc, docx, xls, xlsx</code>.
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* 404 Not Found */}
            <div className={`accordion-item ${openError === '404' ? 'open' : ''}`}>
              <button
                className="accordion-header"
                onClick={() => setOpenError(openError === '404' ? null : '404')}
                aria-expanded={openError === '404'}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <span className="error-code-badge badge-404">404 Not Found</span>
                  <strong>NOT_FOUND / 152-ФЗ Scope Isolation</strong>
                </div>
                <Icon name={openError === '404' ? 'chevron' : 'down'} size={18} />
              </button>
              {openError === '404' && (
                <div className="accordion-body">
                  <div className="error-body-grid">
                    <div>
                      <span className="eyebrow">СИМПТОМ И ПЕРВОПРИЧИНА</span>
                      <p>
                        Карточка взаимодействия или вложение не найдены при обращении по прямому идентификатору.
                      </p>
                    </div>
                    <div>
                      <span className="eyebrow">ЧТО ДЕЛАТЬ ПОЛЬЗОВАТЕЛЮ</span>
                      <p>
                        <strong>Защита персональных данных:</strong> В соответствии со статьей 7 и 19 152-ФЗ, при попытке запроса чужой карточки сервер возвращает HTTP 404 вместо 403 Forbidden для сокрытия самого факта существования записи. Обратитесь к руководителю для переназначения ответственного.
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Interactive AC21 Form Input Preservation Demo Box */}
          <div className="panel input-preservation-demo-panel">
            <div className="panel-heading">
              <div>
                <h2>Интерактивная проверка сохранения ввода без сброса формы (AC21)</h2>
                <p>
                  Протестируйте поведение формы при серверных ошибках. Введенный пользователем текст сохраняется в React-состоянии и не теряется при возникновении ошибки сервера.
                </p>
              </div>
              <span className="stage-chip chip-working">Интерактивный тест AC21</span>
            </div>

            <form onSubmit={handleTriggerDemoError} className="demo-test-form">
              <div className="field">
                <span>Название / Заголовок взаимодействия:</span>
                <input
                  type="text"
                  value={demoTitle}
                  onChange={(e) => setDemoTitle(e.target.value)}
                  placeholder="Введите название взаимодействия..."
                  required
                />
              </div>

              <div className="field" style={{ marginTop: '10px' }}>
                <span>Обоснование / Комментарий к изменению:</span>
                <textarea
                  value={demoComment}
                  onChange={(e) => setDemoComment(e.target.value)}
                  placeholder="Введите обоснование перехода..."
                  style={{ minHeight: '65px' }}
                  required
                />
              </div>

              <div style={{ display: 'flex', gap: '14px', alignItems: 'center', marginTop: '12px', flexWrap: 'wrap' }}>
                <div className="field" style={{ minWidth: '220px' }}>
                  <span>Эмулируемая ошибка:</span>
                  <select
                    value={demoErrorType}
                    onChange={(e) => setDemoErrorType(e.target.value as any)}
                  >
                    <option value="400">400 Bad Request (Синтаксис / параметры)</option>
                    <option value="401">401 Unauthorized (JWT-токен)</option>
                    <option value="403">403 Forbidden (Ролевые права)</option>
                    <option value="404">404 Not Found (Zero-Oracle сокрытие)</option>
                    <option value="409">409 Conflict (CAS Mismatch)</option>
                    <option value="422">422 Unprocessable (Бизнес-правила)</option>
                    <option value="413">413 Payload Too Large (Файл &gt; 25 МБ)</option>
                    <option value="quarantine">422 File Quarantine (Magic Bytes)</option>
                    <option value="500">500 Internal Server Error (Сбой сервера)</option>
                    <option value="502">502 Bad Gateway (Шлюз LMS / Сайт)</option>
                    <option value="503">503 Service Unavailable (Обслуживание)</option>
                    <option value="504">504 Gateway Timeout (Таймаут шлюза)</option>
                  </select>
                </div>

                <Button type="submit" style={{ marginTop: '16px' }}>
                  <Icon name="spark" size={16} />
                  Симулировать ошибку и проверить сохранение
                </Button>
              </div>
            </form>

            {demoSimulatedError && (
              <div style={{ marginTop: '14px' }}>
                <div className="error-alert" style={{ marginBottom: '8px' }}>
                  <Icon name="alert" size={18} />
                  <div>
                    <strong>{demoSimulatedError}</strong>
                    <small>Сервер отклонил операцию. Пользовательские поля не сброшены.</small>
                  </div>
                </div>

                {demoRemediation && (
                  <div className="action-hint-box" style={{ marginBottom: '8px' }}>
                    <Icon name="help" size={16} />
                    <div>
                      <strong>Рекомендация по исправлению:</strong>
                      <span> {demoRemediation}</span>
                    </div>
                  </div>
                )}

                {demoEnvelope && (
                  <details style={{ marginBottom: '8px', background: '#fff', border: '1px solid var(--rtk-color-border)', borderRadius: 'var(--rtk-radius-md)', padding: '10px 14px' }}>
                    <summary style={{ cursor: 'pointer', fontWeight: 600, fontSize: '11px', color: 'var(--rtk-color-primary)' }}>
                      Канонический ответ API (Envelope JSON)
                    </summary>
                    <pre style={{ margin: '8px 0 0', padding: '10px', background: '#1e1b2e', color: '#a5f3fc', borderRadius: '6px', fontSize: '11px', overflowX: 'auto' }}>
                      {JSON.stringify(demoEnvelope, null, 2)}
                    </pre>
                  </details>
                )}

                {demoPreserveSuccess && (
                  <div className="success-alert">
                    <Icon name="check" size={18} />
                    <div>
                      <strong>AC21 соблюден: Введенный текст сохранен в форме!</strong>
                      <small>
                        Значение «{demoTitle}» и комментарий «{demoComment}» остались в полях ввода без стирания.
                      </small>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Tab 5: Безопасность 152-ФЗ */}
      {activeTab === 'security' && (
        <div className="help-tab-content">
          <div className="role-intro-banner security">
            <div className="role-intro-icon">
              <Icon name="shield" size={28} />
            </div>
            <div>
              <h2>Матрица соответствия 152-ФЗ и приказ ФСТЭК России №117</h2>
              <p>
                Архитектурные механизмы защиты персональных данных, регламент обезличивания и технические меры безопасности проекта.
              </p>
            </div>
          </div>

          <div className="scenario-grid">
            <div className="scenario-card">
              <div className="scenario-card-header">
                <span className="badge-important">УПД.3 / УПД.13</span>
                <h3>Сокрытие факта существования (HTTP 404)</h3>
              </div>
              <p>
                Менеджер имеет доступ исключительно к своим записям (<code>owner_id == user.id</code>), руководитель — к своей команде (<code>team_id</code>).
              </p>
              <ul className="scenario-bullet-list">
                <li>При попытке несанкционированного прямого обращения к чужому ID возвращается <strong>строго HTTP 404 Not Found</strong>.</li>
                <li>Исключается возможность сканирования и перебора IDOR для выявления персональных данных субъектов.</li>
              </ul>
            </div>

            <div className="scenario-card">
              <div className="scenario-card-header">
                <span className="badge-important">ИАФ.6 / ОДТ.5</span>
                <h3>In-Memory хранение JWT-токенов</h3>
              </div>
              <p>
                Полный запрет на запись аутентификационных токенов Keycloak в <code>localStorage</code> или <code>sessionStorage</code>:
              </p>
              <ul className="scenario-bullet-list">
                <li>Токен хранится исключительно в оперативной памяти JavaScript через React <code>useRef</code>.</li>
                <li>При закрытии вкладки или перезагрузке браузера токен физически уничтожается.</li>
                <li>Защита от кражи сессии при XSS-атаках.</li>
              </ul>
            </div>

            <div className="scenario-card">
              <div className="scenario-card-header">
                <span className="badge-important">ЗВК.1 / АВЗ.1</span>
                <h3>Изолированное хранилище файлов (10 форматов)</h3>
              </div>
              <p>
                Многоуровневая проверка загружаемых документов:
              </p>
              <ul className="scenario-bullet-list">
                <li>Белый список ровно 10 форматов ТЗ и лимит 25 МБ.</li>
                <li>Побайтовая валидация magic bytes (блокировка MZ, ELF, скриптов).</li>
                <li>Хранение под случайными UUID вне публичного веб-корня.</li>
                <li>Вычисление и сверка SHA-256 контрольной суммы.</li>
              </ul>
            </div>

            <div className="scenario-card">
              <div className="scenario-card-header">
                <span className="badge-important">РСБ.1 / РСБ.3</span>
                <h3>Неизменяемый аудит-лог (Audit Trail)</h3>
              </div>
              <p>
                Фиксация каждого значимого события в таблице <code>interaction_events</code>:
              </p>
              <ul className="scenario-bullet-list">
                <li>Монотонно возрастающая последовательность <code>sequence</code>.</li>
                <li>Снимок всех реквизитов карточки на момент события.</li>
                <li>Программный запрет на модификацию или удаление записей журнала.</li>
              </ul>
            </div>

            <div className="scenario-card">
              <div className="scenario-card-header">
                <span className="badge-important">ОПД.1 / ОПД.2</span>
                <h3>Регламент деперсонализации и архивации</h3>
              </div>
              <p>
                Порядок действий при завершении сотрудничества или отзыве согласия на обработку ПДн:
              </p>
              <ul className="scenario-bullet-list">
                <li>Псевдонимизация персональных данных контактов вуза при архивации карточки.</li>
                <li>Удаление персональных файлов с сохранением контрольной суммы SHA-256 в журнале аудита.</li>
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* Doc Screenshot Modal Lightbox */}
      <DocScreenshotLightbox
        item={lightboxScreenshot}
        onClose={() => setLightboxScreenshot(null)}
      />
    </div>
  );
}

export default HelpPage;

