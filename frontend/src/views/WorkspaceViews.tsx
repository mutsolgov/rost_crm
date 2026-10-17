import { useEffect, useState } from 'react';
import type { ApiClient } from '../api';
import { useDebounced, useResource } from '../hooks';
import { Avatar, Button, Count, EmptyState, ErrorAlert, Icon, Loading, PageHeader, StageBadge, eventNames, formatDate } from '../ui';
import type { Catalogs, Dashboard, Interaction, InteractionList, User, Workflow } from '../types';

export function InteractionTable({ items, openInteraction, compact = false }: { items: Interaction[]; openInteraction: (id: string) => void; compact?: boolean }) {
  return <div className="table-scroll"><table className={'data-table interaction-table ' + (compact ? 'compact-table' : '')}>
    <thead><tr><th>Взаимодействие / организация</th><th>ИТ-программа</th><th>Этап сотрудничества</th>{!compact && <th>Ответственный</th>}<th>{compact ? '' : 'Обновлено'}</th></tr></thead>
    <tbody>{items.map(item => <tr key={item.id} onClick={() => openInteraction(item.id)}>
      <td><button className="table-title" onClick={event => { event.stopPropagation(); openInteraction(item.id); }}>{item.title}</button><span className="cell-secondary">{item.organization_name}</span>{!compact && <span className="cell-cycle">{item.cycle_label}</span>}</td>
      <td><span className="cell-primary">{item.program_name || 'Не определена'}</span><span className="cell-secondary">{item.product_name || 'Продукт не выбран'}</span></td>
      <td><StageBadge code={item.state} name={item.state_name}/></td>
      {!compact && <td><div className="table-person"><Avatar name={item.owner_name} small/><span>{item.owner_name}</span></div></td>}
      <td>{compact ? <Icon name="chevron" size={17}/> : <span className="cell-date">{formatDate(item.updated_at, false)}</span>}</td>
    </tr>)}</tbody>
  </table></div>;
}

export function Overview({ api, revision, me, catalogs, onCreate, canCreate, openInteraction, navigate }: {
  api: ApiClient; revision: number; me: User; catalogs?: Catalogs; onCreate: () => void; canCreate: boolean;
  openInteraction: (id: string) => void; navigate: (path: string) => void;
}) {
  const [retry, setRetry] = useState(0);
  const isAdmin = me.role === 'administrator' || me.role === 'admin';
  const dashboard = useResource<Dashboard>(() => api.get('/dashboard'), [api, revision, retry]);
  const recent = useResource<InteractionList>(() => !isAdmin ? api.get('/interactions?page=1&page_size=5') : Promise.resolve({ items: [], total: 0, page: 1, page_size: 5 }), [api, revision, retry, isAdmin]);
  const data = dashboard.data;
  const date = new Date().toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' });

  if (isAdmin) {
    const stats = data?.system_stats;
    return <>
      <PageHeader
        eyebrow={'СИСТЕМНОЕ УПРАВЛЕНИЕ CRM · ' + date.toLocaleUpperCase('ru-RU')}
        title="Панель системного управления CRM"
        description={'Здравствуйте, ' + me.name.split(' ')[0] + '. Телеметрия платформы, управление каталогами и интеграционными потоками.'}
        action={<div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          <Button onClick={() => navigate('catalogs')}><Icon name="building" size={18}/>Каталоги</Button>
          <Button variant="secondary" onClick={() => navigate('integrations')}><Icon name="spark" size={18}/>Интеграции</Button>
        </div>}
      />
      <ErrorAlert error={dashboard.error} onRetry={() => setRetry(value => value + 1)}/>
      {!data ? (!dashboard.error && <Loading/>) : <>
        <div className="panel" style={{ padding: '18px 22px', marginBottom: '20px', background: '#F8F9FC', borderLeft: '4px solid var(--rtk-color-primary, #7700FF)', borderRadius: '8px' }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '14px' }}>
            <span style={{ color: 'var(--rtk-color-primary, #7700FF)', marginTop: '2px' }}><Icon name="shield" size={24}/></span>
            <div>
              <div style={{ fontWeight: 600, fontSize: '15px', color: '#101828', marginBottom: '4px' }}>
                Инвариант 152-ФЗ и ФСТЭК №117: Изоляция коммерческих воронок
              </div>
              <p style={{ margin: 0, fontSize: '13px', color: '#475467', lineHeight: '1.5' }}>
                Режим системного администратора: в соответствии с регламентом 152-ФЗ прямой доступ к коммерческим воронкам менеджеров изолирован. Используйте вкладки «Интеграции», «Справочники» и «Отчёты» для конфигурирования системы.
              </p>
            </div>
          </div>
        </div>

        <div className="stats-grid">
          {[
            { label: 'Всего пользователей', value: stats?.total_users ?? 0, icon: 'layers', tone: 'purple', note: 'Учётные записи платформы' },
            { label: 'Организаций в каталоге', value: stats?.total_organizations_catalog ?? 0, icon: 'building', tone: 'blue', note: 'Вузы, школы, вендоры' },
            { label: 'ИТ-продуктов и вендоров', value: stats?.total_products_catalog ?? 0, icon: 'check', tone: 'green', note: 'Отечественные решения' },
            { label: 'Заявок на сверку в очереди интеграций', value: stats?.total_inbox_pending ?? 0, icon: 'clock', tone: 'purple', note: 'Буфер входящих заявок' },
            { label: 'ИТ-программы обучения', value: stats?.total_programs_catalog ?? 0, icon: 'spark', tone: 'orange', note: 'Каталог направлений' },
            { label: 'Статус контура LMS', value: (stats?.lms_health_status === 'healthy' || stats?.lms_health_status === 'ok') ? 'В норме' : 'Внимание', icon: 'spark', tone: (stats?.lms_health_status === 'healthy' || stats?.lms_health_status === 'ok') ? 'green' : 'orange', note: 'Телеметрия синхронизации' },
          ].map(stat => <div className="stat-card" key={stat.label}>
            <div className="stat-card-top">
              <span>{stat.label}</span>
              <span className={'stat-icon tone-' + stat.tone}><Icon name={stat.icon} size={19}/></span>
            </div>
            <strong>{typeof stat.value === 'number' ? <Count value={stat.value}/> : stat.value}</strong>
          </div>)}
        </div>

        <div className="overview-grid">
          <section className="panel stage-panel">
            <div className="panel-heading">
              <div><span className="eyebrow">БЫСТРЫЙ ПЕРЕХОД</span><h2>Кнопки быстрых действий</h2></div>
              <span className="quiet-badge">4 действия</span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', padding: '16px 20px' }}>
              <button className="stage-bar-row" style={{ textAlign: 'left', padding: '12px 14px' }} onClick={() => navigate('catalogs')}>
                <div>
                  <span style={{ fontWeight: 600 }}>Импорт каталогов</span>
                  <small style={{ color: 'var(--rtk-color-muted)' }}>Вузы, вендоры, ИТ-продукты и пользователи CRM</small>
                </div>
                <Icon name="arrow" size={16}/>
              </button>
              <button className="stage-bar-row" style={{ textAlign: 'left', padding: '12px 14px' }} onClick={() => navigate('integrations')}>
                <div>
                  <span style={{ fontWeight: 600 }}>Шлюз интеграций</span>
                  <small style={{ color: 'var(--rtk-color-muted)' }}>LMS Zion, выгрузка оплат, сверка заявок и метрики</small>
                </div>
                <Icon name="arrow" size={16}/>
              </button>
              <button className="stage-bar-row" style={{ textAlign: 'left', padding: '12px 14px' }} onClick={() => navigate('catalogs')}>
                <div>
                  <span style={{ fontWeight: 600 }}>Миграция процессов v1/v2</span>
                  <small style={{ color: 'var(--rtk-color-muted)' }}>Маппинг статусов жизненного цикла и аудит миграций</small>
                </div>
                <Icon name="arrow" size={16}/>
              </button>
              <button className="stage-bar-row" style={{ textAlign: 'left', padding: '12px 14px' }} onClick={() => navigate('help')}>
                <div>
                  <span style={{ fontWeight: 600 }}>База знаний и регламенты</span>
                  <small style={{ color: 'var(--rtk-color-muted)' }}>Архитектура, ролевая модель и стандарты 152-ФЗ</small>
                </div>
                <Icon name="arrow" size={16}/>
              </button>
            </div>
            <div className="panel-footnote"><span className="legend-dot"/>Оперативный доступ к конфигурации CRM</div>
          </section>

          <section className="focus-panel">
            <span className="focus-symbol"><Icon name="shield" size={27}/></span>
            <span className="eyebrow">БЕЗОПАСНОСТЬ И АУДИТ</span>
            <h2>Строгая изоляция данных.<br/>Полный аудит операций.</h2>
            <p>Все изменяющие запросы требуют Idempotency-Key и CAS-проверку ревизий. Доступ к коммерческим воронкам разделен по ролевой модели.</p>
            <div className="focus-metric">
              <strong>{stats?.total_inbox_pending ?? 0}</strong>
              <span>заявок в буфере<br/>интеграций</span>
            </div>
            <button className="light-link" onClick={() => navigate('integrations')}>
              Открыть шлюз интеграций<Icon name="arrow" size={19}/>
            </button>
          </section>
        </div>

        <div className="overview-lower">
        <section className="panel platform-status-panel" style={{ padding: '22px' }}>
          <div className="panel-heading" style={{ marginBottom: '18px' }}>
            <div>
              <span className="eyebrow">МОНИТОРИНГ ПЛАТФОРМЫ</span>
              <h2>Статус системных контуров и каталогов</h2>
              <p>Оперативное состояние интеграционных шлюзов и наполнение каталогов CRM</p>
            </div>
            <span className="quiet-badge"><Icon name="shield" size={14}/> 152-ФЗ защищено</span>
          </div>

          <div className="platform-contours-grid">
            <div style={{ background: '#F8F9FC', padding: '14px 16px', borderRadius: '8px', border: '1px solid var(--rtk-color-border, #E2E5EB)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                <span style={{ fontSize: '13px', fontWeight: 600, color: '#101828' }}>Контур LMS Zion</span>
                <span className={'stage-badge ' + ((stats?.lms_health_status === 'healthy' || stats?.lms_health_status === 'ok') ? 'tone-green' : 'tone-orange')}>
                  <i/>{stats?.lms_health_status === 'healthy' || stats?.lms_health_status === 'ok' ? 'Подключён · В норме' : 'Внимание'}
                </span>
              </div>
              <small style={{ color: 'var(--rtk-color-muted, #475467)', fontSize: '11px', display: 'block' }}>Адаптер синхронизации учебных программ и групп</small>
            </div>

            <div style={{ background: '#F8F9FC', padding: '14px 16px', borderRadius: '8px', border: '1px solid var(--rtk-color-border, #E2E5EB)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                <span style={{ fontSize: '13px', fontWeight: 600, color: '#101828' }}>Контур Сайта ИТ Школы</span>
                <span className={'stage-badge ' + ((stats?.website_health_status === 'healthy' || stats?.website_health_status === 'ok') ? 'tone-green' : 'tone-orange')}>
                  <i/>{stats?.website_health_status === 'healthy' || stats?.website_health_status === 'ok' ? 'Подключён · В норме' : 'Внимание'}
                </span>
              </div>
              <small style={{ color: 'var(--rtk-color-muted, #475467)', fontSize: '11px', display: 'block' }}>Приём входящих заявок абитуриентов и партнёров</small>
            </div>
          </div>

          <div style={{ borderTop: '1px solid var(--rtk-color-border-subtle, #F0EDF4)', paddingTop: '16px' }}>
            <div style={{ fontSize: '12px', fontWeight: 650, color: 'var(--rtk-color-muted, #475467)', marginBottom: '12px', letterSpacing: '0.04em', textTransform: 'uppercase' }}>
              Записи в каталогах и буфере
            </div>
            <div className="platform-catalogs-grid">
              <div style={{ background: '#FFF', border: '1px solid var(--rtk-color-border, #E2E5EB)', borderRadius: '8px', padding: '12px 14px' }}>
                <span style={{ fontSize: '11px', color: 'var(--rtk-color-muted, #475467)', display: 'block' }}>Вузы и партнёры</span>
                <strong style={{ fontSize: '20px', color: '#101828', display: 'block', marginTop: '4px' }}>
                  <Count value={stats?.total_organizations_catalog ?? (catalogs?.organizations?.length ?? 0)}/>
                </strong>
              </div>
              <div style={{ background: '#FFF', border: '1px solid var(--rtk-color-border, #E2E5EB)', borderRadius: '8px', padding: '12px 14px' }}>
                <span style={{ fontSize: '11px', color: 'var(--rtk-color-muted, #475467)', display: 'block' }}>ИТ-программы</span>
                <strong style={{ fontSize: '20px', color: '#101828', display: 'block', marginTop: '4px' }}>
                  <Count value={stats?.total_programs_catalog ?? (catalogs?.programs?.length ?? 0)}/>
                </strong>
              </div>
              <div style={{ background: '#FFF', border: '1px solid var(--rtk-color-border, #E2E5EB)', borderRadius: '8px', padding: '12px 14px' }}>
                <span style={{ fontSize: '11px', color: 'var(--rtk-color-muted, #475467)', display: 'block' }}>ИТ-продукты</span>
                <strong style={{ fontSize: '20px', color: '#101828', display: 'block', marginTop: '4px' }}>
                  <Count value={stats?.total_products_catalog ?? (catalogs?.products?.length ?? 0)}/>
                </strong>
              </div>
              <div style={{ background: '#FFF', border: '1px solid var(--rtk-color-border, #E2E5EB)', borderRadius: '8px', padding: '12px 14px' }}>
                <span style={{ fontSize: '11px', color: 'var(--rtk-color-muted, #475467)', display: 'block' }}>Договоры</span>
                <strong style={{ fontSize: '20px', color: '#101828', display: 'block', marginTop: '4px' }}>
                  <Count value={stats?.total_contracts_catalog ?? (catalogs?.contracts?.length ?? 0)}/>
                </strong>
              </div>
            </div>
            <div style={{ marginTop: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: '#F5F2FB', padding: '12px 16px', borderRadius: '8px', flexWrap: 'wrap', gap: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px', color: '#4B3358' }}>
                <Icon name="clock" size={16}/>
                <span>Буфер интеграций: <strong>{stats?.total_inbox_pending ?? 0}</strong> заявок в очереди</span>
              </div>
              <button className="text-link" onClick={() => navigate('integrations')}>
                Открыть буфер сверки<Icon name="arrow" size={14}/>
              </button>
            </div>
          </div>
        </section>

        <section className="panel system-journal-panel" style={{ padding: '22px' }}>
          <div className="panel-heading" style={{ marginBottom: '18px' }}>
            <div>
              <span className="eyebrow">СИСТЕМНЫЙ ЖУРНАЛ</span>
              <h2>Системный журнал действий и импорта</h2>
              <p>Аудит конфигураций, импорт справочников и телеметрия</p>
            </div>
            <Icon name="clock" size={20}/>
          </div>
          <div className="activity-feed">
            {stats?.recent_system_events && stats.recent_system_events.length > 0 ? (
              stats.recent_system_events.map((evt, idx) => (
                <div className="activity-item" key={evt.id || idx}>
                  <span className="activity-dot" />
                  <div>
                    <span className="activity-type">{evt.type || evt.event_type || 'Система'}</span>
                    <strong>{evt.title}</strong>
                    <small>
                      {evt.description || evt.actor_name || ''}
                      {evt.received_at ? ` · ${new Date(evt.received_at).toLocaleString('ru-RU')}` : ''}
                    </small>
                  </div>
                </div>
              ))
            ) : (
              <div style={{ padding: '16px', color: 'var(--rtk-color-muted, #64748B)', textAlign: 'center' }}>
                События системного журнала отсутствуют
              </div>
            )}
          </div>
          <div style={{ marginTop: '16px', borderTop: '1px solid var(--rtk-color-border-subtle, #F0EDF4)', paddingTop: '14px', display: 'flex', justifyContent: 'space-between', gap: '10px' }}>
            <Button variant="secondary" onClick={() => navigate('catalogs')}><Icon name="building" size={16}/>Импорт каталогов</Button>
            <Button variant="ghost" onClick={() => navigate('integrations')}><Icon name="refresh" size={16}/>Шлюз интеграций</Button>
          </div>
        </section>
      </div>
      </>}
    </>;
  }

  return <>
    <PageHeader eyebrow={'РАБОЧИЙ ОБЗОР · ' + date.toLocaleUpperCase('ru-RU')} title="Партнёрства в движении" description={'Здравствуйте, ' + me.name.split(' ')[0] + '. Здесь всё, что важно для вашей работы с вузами.'}
      action={<Button onClick={onCreate} disabled={!canCreate}><Icon name="plus" size={18}/>Новое взаимодействие</Button>}/>
    <ErrorAlert error={dashboard.error} onRetry={() => setRetry(value => value + 1)}/>
    {!data ? (!dashboard.error && <Loading/>) : <>
      <div className="stats-grid">
        {[
          { label: 'Всего взаимодействий', value: data.total_interactions, icon: 'layers', tone: 'purple', note: 'В вашей области доступа' },
          { label: 'Активных процессов', value: data.active_interactions, icon: 'spark', tone: 'orange', note: 'Сотрудничество продолжается' },
          { label: 'Образовательных организаций', value: data.total_organizations, icon: 'building', tone: 'blue', note: 'Уникальные партнёры' },
          { label: 'Завершённых процессов', value: data.completed_interactions, icon: 'check', tone: 'green', note: 'Пройден полный цикл' },
        ].map(stat => <div className="stat-card" key={stat.label}><div className="stat-card-top"><span>{stat.label}</span><span className={'stat-icon tone-' + stat.tone}><Icon name={stat.icon} size={19}/></span></div><strong><Count value={stat.value}/></strong><small>{stat.note}</small></div>)}
      </div>
      <div className="overview-grid">
        <section className="panel stage-panel"><div className="panel-heading"><div><span className="eyebrow">ТЕКУЩЕЕ СОСТОЯНИЕ</span><h2>Этапы сотрудничества</h2></div><span className="quiet-badge">{data.total_interactions} процессов</span></div>
          {data.total_interactions === 0 ? <EmptyState title="Пока нет взаимодействий" description="Создайте первое взаимодействие или обратитесь к руководителю за доступом."/> : <div className="stage-bars">
            {data.counts_by_state.filter(stage => stage.count > 0).map(stage => <button key={stage.code} className="stage-bar-row" onClick={() => navigate('interactions?state=' + encodeURIComponent(stage.code))}><div><span>{stage.name}</span><strong>{stage.count}</strong></div><span className="bar-track"><i style={{ width: Math.max(3, stage.count / Math.max(1, ...data.counts_by_state.map(item => item.count)) * 100) + '%' }}/></span></button>)}
          </div>}
          <div className="panel-footnote"><span className="legend-dot"/>Количество взаимодействий на каждом этапе</div>
        </section>
        <section className="focus-panel"><span className="focus-symbol"><Icon name="layers" size={27}/></span><span className="eyebrow">ОБЩИЙ КОНТЕКСТ КОМАНДЫ</span><h2>Один взгляд.<br/>Весь путь партнёрства.</h2><p>Программа, ответственный и история решений — в одной карточке взаимодействия.</p>
          <div className="focus-metric"><strong>{data.unassigned_program_count}</strong><span>взаимодействий<br/>без выбранной программы</span></div>
          <button className="light-link" onClick={() => navigate('interactions')}>Открыть реестр<Icon name="arrow" size={19}/></button>
        </section>
      </div>
    </>}
    <div className="overview-lower">
      <section className="panel recent-panel"><div className="panel-heading"><div><h2>Взаимодействия в работе</h2><p>Быстрый переход к доступным карточкам</p></div><button className="text-link" onClick={() => navigate('interactions')}>Весь реестр<Icon name="arrow" size={16}/></button></div>
        <ErrorAlert error={recent.error} onRetry={() => setRetry(value => value + 1)}/>
        {!recent.data ? (!recent.error && <Loading/>) : recent.data.items.length ? <InteractionTable compact items={recent.data.items} openInteraction={openInteraction}/> : <EmptyState title="Реестр пока пуст" description="Все доступные вам взаимодействия появятся здесь." action={canCreate && <Button onClick={onCreate}>Создать взаимодействие</Button>}/>}
      </section>
      <section className="panel activity-panel"><div className="panel-heading"><div><h2>Последние изменения</h2><p>События вашей команды</p></div><Icon name="clock" size={20}/></div>
        {!data ? <Loading/> : data.recent_events.length === 0 ? <EmptyState title="Изменений пока нет" description="Здесь появятся события доступных взаимодействий." icon="clock"/> : <div className="activity-feed">{data.recent_events.slice(0, 6).map((event, index) => <button className="activity-item" key={event.interaction_id + event.at + index} onClick={() => openInteraction(event.interaction_id)}><span className="activity-dot"/><div><span className="activity-type">{eventNames[event.event_type] || 'Обновление взаимодействия'}</span><strong>{event.title}</strong><small>{event.actor_name} · {formatDate(event.at)}</small></div></button>)}</div>}
      </section>
    </div>
  </>;
}

const RTK_INTERACTIONS_FILTERS_KEY = 'rtk_interactions_filters';

interface InteractionFilters {
  q: string;
  organization_id: string;
  direction_id: string;
  program_id: string;
  product_id: string;
  owner_id: string;
  state: string;
}

let memoryFiltersCache: InteractionFilters | null = null;

function parseHashFilters(): Partial<InteractionFilters> {
  if (typeof window === 'undefined') return {};
  const hash = window.location.hash || '';
  const qIndex = hash.indexOf('?');
  if (qIndex === -1) return {};
  const searchParams = new URLSearchParams(hash.slice(qIndex + 1));
  const result: Partial<InteractionFilters> = {};
  const keys: (keyof InteractionFilters)[] = ['q', 'organization_id', 'direction_id', 'program_id', 'product_id', 'owner_id', 'state'];
  for (const k of keys) {
    const val = searchParams.get(k);
    if (val !== null) {
      result[k] = val;
    }
  }
  return result;
}

function getStoredFilters(fallbackState: string): InteractionFilters {
  try {
    const hashFilters = parseHashFilters();
    if (Object.values(hashFilters).some(Boolean)) {
      const fromHash: InteractionFilters = {
        q: hashFilters.q ?? '',
        organization_id: hashFilters.organization_id ?? '',
        direction_id: hashFilters.direction_id ?? '',
        program_id: hashFilters.program_id ?? '',
        product_id: hashFilters.product_id ?? '',
        owner_id: hashFilters.owner_id ?? '',
        state: hashFilters.state ?? fallbackState ?? '',
      };
      memoryFiltersCache = fromHash;
      return fromHash;
    }
    if (memoryFiltersCache) {
      return {
        q: typeof memoryFiltersCache.q === 'string' ? memoryFiltersCache.q : '',
        organization_id: typeof memoryFiltersCache.organization_id === 'string' ? memoryFiltersCache.organization_id : '',
        direction_id: typeof memoryFiltersCache.direction_id === 'string' ? memoryFiltersCache.direction_id : '',
        program_id: typeof memoryFiltersCache.program_id === 'string' ? memoryFiltersCache.program_id : '',
        product_id: typeof memoryFiltersCache.product_id === 'string' ? memoryFiltersCache.product_id : '',
        owner_id: typeof memoryFiltersCache.owner_id === 'string' ? memoryFiltersCache.owner_id : '',
        state: fallbackState || (typeof memoryFiltersCache.state === 'string' ? memoryFiltersCache.state : ''),
      };
    }
    if (typeof window !== 'undefined' && window.history && window.history.state) {
      let raw = window.history.state[RTK_INTERACTIONS_FILTERS_KEY];
      if (typeof raw === 'string') {
        try { raw = JSON.parse(raw); } catch { /* ignore parse error */ }
      }
      if (raw && typeof raw === 'object') {
        const restored: InteractionFilters = {
          q: typeof raw.q === 'string' ? raw.q : '',
          organization_id: typeof raw.organization_id === 'string' ? raw.organization_id : '',
          direction_id: typeof raw.direction_id === 'string' ? raw.direction_id : '',
          program_id: typeof raw.program_id === 'string' ? raw.program_id : '',
          product_id: typeof raw.product_id === 'string' ? raw.product_id : '',
          owner_id: typeof raw.owner_id === 'string' ? raw.owner_id : '',
          state: fallbackState || (typeof raw.state === 'string' ? raw.state : ''),
        };
        memoryFiltersCache = restored;
        return restored;
      }
    }
  } catch {
    // ignore history state access errors
  }
  return { q: '', organization_id: '', direction_id: '', program_id: '', product_id: '', owner_id: '', state: fallbackState || '' };
}

export function Interactions({ api, catalogs, workflow, revision, initialState, onCreate, canCreate, openInteraction }: {
  api: ApiClient; catalogs: Catalogs; workflow: Workflow; revision: number; initialState: string;
  onCreate: () => void; canCreate: boolean; openInteraction: (id: string) => void;
}) {
  const [filters, setFilters] = useState<InteractionFilters>(() => getStoredFilters(initialState));
  const [page, setPage] = useState(1);
  const [retry, setRetry] = useState(0);
  const q = useDebounced(filters.q);

  useEffect(() => {
    if (initialState) {
      setFilters(previous => (previous.state === initialState ? previous : { ...previous, state: initialState }));
      setPage(1);
    }
  }, [initialState]);

  useEffect(() => {
    const onHashChange = () => {
      const hash = window.location.hash || '';
      if (!hash.startsWith('#/interactions') && !hash.startsWith('#interactions')) return;
      const hashFilters = parseHashFilters();
      const next: InteractionFilters = {
        q: hashFilters.q ?? '',
        organization_id: hashFilters.organization_id ?? '',
        direction_id: hashFilters.direction_id ?? '',
        program_id: hashFilters.program_id ?? '',
        product_id: hashFilters.product_id ?? '',
        owner_id: hashFilters.owner_id ?? '',
        state: hashFilters.state ?? '',
      };
      setFilters(prev => {
        const isDiff = (
          prev.q !== next.q ||
          prev.organization_id !== next.organization_id ||
          prev.direction_id !== next.direction_id ||
          prev.program_id !== next.program_id ||
          prev.product_id !== next.product_id ||
          prev.owner_id !== next.owner_id ||
          prev.state !== next.state
        );
        if (isDiff) {
          setPage(1);
          return next;
        }
        return prev;
      });
    };
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  useEffect(() => {
    try {
      const searchParams = new URLSearchParams();
      if (filters.q) searchParams.set('q', filters.q);
      if (filters.organization_id) searchParams.set('organization_id', filters.organization_id);
      if (filters.direction_id) searchParams.set('direction_id', filters.direction_id);
      if (filters.program_id) searchParams.set('program_id', filters.program_id);
      if (filters.state) searchParams.set('state', filters.state);
      if (filters.product_id) searchParams.set('product_id', filters.product_id);
      if (filters.owner_id) searchParams.set('owner_id', filters.owner_id);

      const qs = searchParams.toString();
      const targetHash = qs ? `#/interactions?${qs}` : '#/interactions';
      const hasActive = Object.values(filters).some(Boolean);

      if (hasActive) {
        memoryFiltersCache = filters;
        if (typeof window !== 'undefined' && window.history?.replaceState) {
          window.history.replaceState(
            { ...(window.history.state || {}), [RTK_INTERACTIONS_FILTERS_KEY]: filters },
            '',
            targetHash
          );
        }
      } else {
        memoryFiltersCache = null;
        if (typeof window !== 'undefined' && window.history?.replaceState) {
          window.history.replaceState(
            { ...(window.history.state || {}), [RTK_INTERACTIONS_FILTERS_KEY]: null },
            '',
            '#/interactions'
          );
        }
      }
    } catch {
      // ignore history access errors
    }
  }, [filters]);

  const params = new URLSearchParams({ ...filters, q, page: String(page), page_size: '15' }).toString();
  const list = useResource<InteractionList>(() => api.get('/interactions?' + params), [api, params, revision, retry]);
  const update = (key: keyof typeof filters, value: string) => { setFilters(previous => ({ ...previous, [key]: value })); setPage(1); };
  const hasFilters = Object.values(filters).some(Boolean);
  const reset = () => {
    try {
      memoryFiltersCache = null;
      if (typeof window !== 'undefined' && window.history?.replaceState) {
        window.history.replaceState({ ...(window.history.state || {}), [RTK_INTERACTIONS_FILTERS_KEY]: null }, '', '#/interactions');
      }
    } catch {
      // ignore history access errors
    }
    setFilters({ q: '', organization_id: '', direction_id: '', program_id: '', product_id: '', owner_id: '', state: '' });
    setPage(1);
  };
  const totalPages = Math.max(1, Math.ceil((list.data?.total || 0) / 15));
  return <>
    <PageHeader eyebrow="ПАРТНЁРСКАЯ РАБОТА" title="Взаимодействия" description="Каждая программа и каждый цикл сотрудничества — отдельная история."
      action={canCreate ? <Button onClick={onCreate}><Icon name="plus" size={18}/>Новое взаимодействие</Button> : undefined}/>
    <section className="panel registry-panel">
      <div className="registry-toolbar"><div><span className="section-tab">Все взаимодействия{list.data && <b>{list.data.total}</b>}</span></div><span className="subtle-inline"><Icon name="shield" size={15}/>С учётом ваших прав</span></div>
      <div className="filter-grid">
        <label className="field search-field"><span>Поиск</span><div className="input-icon"><Icon name="search" size={18}/><input value={filters.q} onChange={event => update('q', event.target.value)} placeholder="Название или организация" type="search"/></div></label>
        <label className="field"><span>Организация</span><select value={filters.organization_id} onChange={event => update('organization_id', event.target.value)}><option value="">Все организации</option>{catalogs.organizations.map(item => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
        <label className="field"><span>ИТ-направление</span><select value={filters.direction_id} onChange={event => update('direction_id', event.target.value)}><option value="">Все направления</option>{catalogs.directions.map(item => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
        <label className="field"><span>ИТ-программа</span><select value={filters.program_id} onChange={event => update('program_id', event.target.value)}><option value="">Все программы</option>{catalogs.programs.map(item => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
        <label className="field"><span>Этап</span><select value={filters.state} onChange={event => update('state', event.target.value)}><option value="">Все этапы</option>{workflow.states.map(item => <option value={item.code} key={item.code}>{item.name}</option>)}</select></label>
        <label className="field"><span>ИТ-продукт</span><select value={filters.product_id} onChange={event => update('product_id', event.target.value)}><option value="">Все продукты</option>{catalogs.products.map(item => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
        <label className="field"><span>Ответственный</span><select value={filters.owner_id} onChange={event => update('owner_id', event.target.value)}><option value="">Все ответственные</option>{catalogs.owners.map(item => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
      </div>
      <div className="filter-footer"><span>{list.loading ? 'Обновляем выборку…' : 'Фильтры применяются автоматически'}</span>{hasFilters && <button className="text-link" onClick={reset}><Icon name="close" size={14}/>Сбросить фильтры</button>}</div>
      <ErrorAlert error={list.error} onRetry={() => setRetry(value => value + 1)}/>
      {!list.data ? (!list.error && <Loading/>) : list.data.items.length
        ? <><div className={list.loading ? 'table-updating' : ''}><InteractionTable items={list.data.items} openInteraction={openInteraction}/></div><div className="pagination"><span>Показано {(page - 1) * 15 + 1}–{Math.min(page * 15, list.data.total)} из {list.data.total}</span><div><Button variant="secondary" disabled={page <= 1 || list.loading} onClick={() => setPage(value => value - 1)} aria-label="Предыдущая страница"><Icon name="back" size={16}/></Button><span>{page} / {totalPages}</span><Button variant="secondary" disabled={page >= totalPages || list.loading} onClick={() => setPage(value => value + 1)} aria-label="Следующая страница"><Icon name="arrow" size={16}/></Button></div></div></>
        : <EmptyState title={hasFilters ? 'По этим фильтрам ничего не найдено' : 'Пока нет взаимодействий'} description={hasFilters ? 'Измените условия поиска или сбросьте фильтры.' : 'Создайте взаимодействие, чтобы начать работу с партнёром.'} action={hasFilters ? <Button variant="secondary" onClick={reset}>Сбросить фильтры</Button> : canCreate && <Button onClick={onCreate}>Создать взаимодействие</Button>}/>}
    </section>
  </>;
}

