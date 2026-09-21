import { useState } from 'react';
import { useAuth } from '../auth';
import { Button, ErrorAlert, Icon } from '../ui';

// Re-export CatalogPage and modals for backwards compatibility and clean modular separation
export { CatalogPage, ImportWizardModal, WorkflowMigratorModal } from './CatalogPage';

export function HelpPage() {
  const { me } = useAuth();

  const getInitialTab = (): 'manager' | 'supervisor' | 'admin' | 'errors' | 'security' => {
    if (me?.role === 'supervisor') return 'supervisor';
    if (me?.role === 'administrator' || me?.role === 'admin') return 'admin';
    return 'manager';
  };

  const [activeTab, setActiveTab] = useState<'manager' | 'supervisor' | 'admin' | 'errors' | 'security'>(getInitialTab);
  const [openError, setOpenError] = useState<string | null>('409');

  // AC21 Interactive Form Input Preservation Tester State
  const [demoTitle, setDemoTitle] = useState('Взаимодействие с МГТУ по программе «Сетевые технологии»');
  const [demoComment, setDemoComment] = useState('Направлен запрос на корректировку договора перед подписанием.');
  const [demoErrorType, setDemoErrorType] = useState<'409' | '422' | '413' | 'quarantine'>('409');
  const [demoSimulatedError, setDemoSimulatedError] = useState<string | null>(null);
  const [demoPreserveSuccess, setDemoPreserveSuccess] = useState(false);

  function handleTriggerDemoError(e: React.FormEvent) {
    e.preventDefault();
    setDemoPreserveSuccess(true);
    if (demoErrorType === '409') {
      setDemoSimulatedError('HTTP 409 Conflict: CAS revision mismatch. Карточка была изменена другим пользователем. Введенные данные сохранены.');
    } else if (demoErrorType === '422') {
      setDemoSimulatedError('HTTP 422 Unprocessable Entity: Для перехода на этап «Передача материалов» требуется связка программы и продукта.');
    } else if (demoErrorType === '413') {
      setDemoSimulatedError('HTTP 413 Payload Too Large: Прикрепляемый файл превышает лимит 25 МБ.');
    } else {
      setDemoSimulatedError('HTTP 422 File Quarantine: Формат файла заблокирован антивирусным шлюзом (обнаружен исполняемый код).');
    }
  }

  return (
    <div className="help-center">
      <div className="page-heading">
        <div>
          <div className="eyebrow">БАЗА ЗНАНИЙ И РЕГЛАМЕНТЫ (B34 / R21 / AC21)</div>
          <h1>Центр базы знаний CRM</h1>
          <p>Ролевые регламенты ведения воронки, справочник ошибок HTTP/CAS и стандарты безопасности 152-ФЗ.</p>
        </div>
        {me && (
          <div className="user-role-chip">
            <Icon name="shield" size={16} />
            <span>Ваша текущая роль: <strong>{me.role}</strong></span>
          </div>
        )}
      </div>

      {/* Role and Topic Tabs */}
      <div className="help-tabs" role="tablist">
        <button
          role="tab"
          aria-selected={activeTab === 'manager'}
          className={`help-tab-btn ${activeTab === 'manager' ? 'active' : ''}`}
          onClick={() => setActiveTab('manager')}
        >
          <Icon name="layers" size={18} />
          <span>Менеджер</span>
          <b>15 этапов воронки</b>
        </button>

        <button
          role="tab"
          aria-selected={activeTab === 'supervisor'}
          className={`help-tab-btn ${activeTab === 'supervisor' ? 'active' : ''}`}
          onClick={() => setActiveTab('supervisor')}
        >
          <Icon name="users" size={18} />
          <span>Руководитель</span>
          <b>Квоты и отчёты</b>
        </button>

        <button
          role="tab"
          aria-selected={activeTab === 'admin'}
          className={`help-tab-btn ${activeTab === 'admin' ? 'active' : ''}`}
          onClick={() => setActiveTab('admin')}
        >
          <Icon name="refresh" size={18} />
          <span>Администратор</span>
          <b>Импорт и миграции</b>
        </button>

        <button
          role="tab"
          aria-selected={activeTab === 'errors'}
          className={`help-tab-btn ${activeTab === 'errors' ? 'active' : ''}`}
          onClick={() => setActiveTab('errors')}
        >
          <Icon name="alert" size={18} />
          <span>Справочник ошибок</span>
          <b>Коды HTTP / CAS</b>
        </button>

        <button
          role="tab"
          aria-selected={activeTab === 'security'}
          className={`help-tab-btn ${activeTab === 'security' ? 'active' : ''}`}
          onClick={() => setActiveTab('security')}
        >
          <Icon name="shield" size={18} />
          <span>Безопасность 152-ФЗ</span>
          <b>ФСТЭК №117</b>
        </button>
      </div>

      {/* Tab 1: Менеджер */}
      {activeTab === 'manager' && (
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
      {activeTab === 'supervisor' && (
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
      {activeTab === 'admin' && (
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
                    <option value="409">409 Conflict (CAS Mismatch)</option>
                    <option value="422">422 Unprocessable (Бизнес-правила)</option>
                    <option value="413">413 Payload Too Large (Файл &gt; 25 МБ)</option>
                    <option value="quarantine">422 File Quarantine (Magic Bytes)</option>
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
    </div>
  );
}

export default HelpPage;

