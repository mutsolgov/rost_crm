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

export function Overview({ api, revision, me, onCreate, canCreate, openInteraction, navigate }: {
  api: ApiClient; revision: number; me: User; onCreate: () => void; canCreate: boolean;
  openInteraction: (id: string) => void; navigate: (path: string) => void;
}) {
  const [retry, setRetry] = useState(0);
  const dashboard = useResource<Dashboard>(() => api.get('/dashboard'), [api, revision, retry]);
  const recent = useResource<InteractionList>(() => api.get('/interactions?page=1&page_size=5'), [api, revision, retry]);
  const data = dashboard.data;
  const date = new Date().toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' });
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

export function Interactions({ api, catalogs, workflow, revision, initialState, onCreate, canCreate, openInteraction }: {
  api: ApiClient; catalogs: Catalogs; workflow: Workflow; revision: number; initialState: string;
  onCreate: () => void; canCreate: boolean; openInteraction: (id: string) => void;
}) {
  const [filters, setFilters] = useState({ q: '', organization_id: '', program_id: '', product_id: '', owner_id: '', state: initialState });
  const [page, setPage] = useState(1);
  const [retry, setRetry] = useState(0);
  const q = useDebounced(filters.q);
  useEffect(() => { setFilters(previous => ({ ...previous, state: initialState })); setPage(1); }, [initialState]);
  const params = new URLSearchParams({ ...filters, q, page: String(page), page_size: '15' }).toString();
  const list = useResource<InteractionList>(() => api.get('/interactions?' + params), [api, params, revision, retry]);
  const update = (key: keyof typeof filters, value: string) => { setFilters(previous => ({ ...previous, [key]: value })); setPage(1); };
  const hasFilters = Object.values(filters).some(Boolean);
  const reset = () => { setFilters({ q: '', organization_id: '', program_id: '', product_id: '', owner_id: '', state: '' }); setPage(1); };
  const totalPages = Math.max(1, Math.ceil((list.data?.total || 0) / 15));
  return <>
    <PageHeader eyebrow="ПАРТНЁРСКАЯ РАБОТА" title="Взаимодействия" description="Каждая программа и каждый цикл сотрудничества — отдельная история."
      action={<Button onClick={onCreate} disabled={!canCreate}><Icon name="plus" size={18}/>Новое взаимодействие</Button>}/>
    <section className="panel registry-panel">
      <div className="registry-toolbar"><div><span className="section-tab">Все взаимодействия{list.data && <b>{list.data.total}</b>}</span></div><span className="subtle-inline"><Icon name="shield" size={15}/>С учётом ваших прав</span></div>
      <div className="filter-grid">
        <label className="field search-field"><span>Поиск</span><div className="input-icon"><Icon name="search" size={18}/><input value={filters.q} onChange={event => update('q', event.target.value)} placeholder="Название или организация" type="search"/></div></label>
        <label className="field"><span>Организация</span><select value={filters.organization_id} onChange={event => update('organization_id', event.target.value)}><option value="">Все организации</option>{catalogs.organizations.map(item => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
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

