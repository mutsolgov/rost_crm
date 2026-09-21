import { useEffect, useState, useMemo } from 'react';
import type { ApiClient } from '../api';
import { makeMutationKey } from '../api';
import {
  Avatar,
  Button,
  Count,
  EmptyState,
  ErrorAlert,
  Icon,
  Loading,
  Modal,
  PageHeader,
  formatDate,
} from '../ui';
import type {
  Catalogs,
  IntegrationInboxItem,
  IntegrationInboxResponse,
  IntegrationsStatusResponse,
  LearningMetricsSummaryResponse,
  ReconciliationAction,
  User,
} from '../types';

interface IntegrationsViewProps {
  api: ApiClient;
  catalogs?: Catalogs;
  me: User;
  navigate: (target: string) => void;
  openInteraction: (id: string) => void;
}

export function IntegrationsView({
  api,
  catalogs,
  me,
  navigate,
  openInteraction,
}: IntegrationsViewProps) {
  const [status, setStatus] = useState<IntegrationsStatusResponse | null>(null);
  const [statusLoading, setStatusLoading] = useState(true);
  const [statusError, setStatusError] = useState<unknown>(null);

  const [metrics, setMetrics] = useState<LearningMetricsSummaryResponse | null>(null);
  const [metricsLoading, setMetricsLoading] = useState(true);
  const [metricsError, setMetricsError] = useState<unknown>(null);

  const [inbox, setInbox] = useState<IntegrationInboxResponse | null>(null);
  const [inboxLoading, setInboxLoading] = useState(true);
  const [inboxError, setInboxError] = useState<unknown>(null);

  const [statusFilter, setStatusFilter] = useState<string>('pending');
  const [searchQuery, setSearchQuery] = useState('');
  const [page, setPage] = useState(1);
  const pageSize = 10;

  const [syncingSource, setSyncingSource] = useState<string | null>(null);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [resolveItem, setResolveItem] = useState<IntegrationInboxItem | null>(null);

  async function loadStatus() {
    setStatusLoading(true);
    setStatusError(null);
    try {
      const res = await api.getIntegrationsStatus();
      setStatus(res);
    } catch (err) {
      setStatusError(err);
    } finally {
      setStatusLoading(false);
    }
  }

  async function loadMetrics() {
    setMetricsLoading(true);
    setMetricsError(null);
    try {
      const res = await api.getIntegrationMetrics();
      setMetrics(res);
    } catch (err) {
      setMetricsError(err);
    } finally {
      setMetricsLoading(false);
    }
  }

  async function loadInbox(currentPage = page, filter = statusFilter) {
    setInboxLoading(true);
    setInboxError(null);
    try {
      const params: { status?: string; page: number; page_size: number } = {
        page: currentPage,
        page_size: pageSize,
      };
      if (filter && filter !== 'all') {
        params.status = filter;
      }
      const res = await api.getIntegrationInbox(params);
      setInbox(res);
    } catch (err) {
      setInboxError(err);
    } finally {
      setInboxLoading(false);
    }
  }

  function reloadAll() {
    loadStatus();
    loadMetrics();
    loadInbox(page, statusFilter);
  }

  useEffect(() => {
    loadStatus();
    loadMetrics();
  }, []);

  useEffect(() => {
    loadInbox(page, statusFilter);
  }, [page, statusFilter]);

  async function handleSync(source: string) {
    setSyncingSource(source);
    setSyncMessage(null);
    try {
      const res = await api.syncIntegrationSource(source);
      setSyncMessage(res.message);
      reloadAll();
    } catch (err) {
      setStatusError(err);
    } finally {
      setSyncingSource(null);
    }
  }

  const filteredItems = useMemo(() => {
    if (!inbox?.items) return [];
    if (!searchQuery.trim()) return inbox.items;
    const q = searchQuery.toLowerCase().trim();
    return inbox.items.filter(item => {
      const orgName = (item.payload.organization_name || '').toLowerCase();
      const repName = (item.payload.representative_name || '').toLowerCase();
      const progName = (item.payload.program_name || '').toLowerCase();
      const extId = (item.external_id || '').toLowerCase();
      const matchedName = (item.matched_organization_name || '').toLowerCase();
      return (
        orgName.includes(q) ||
        repName.includes(q) ||
        progName.includes(q) ||
        extId.includes(q) ||
        matchedName.includes(q)
      );
    });
  }, [inbox?.items, searchQuery]);

  const lmsAdapter = status?.adapters_by_source?.lms || status?.adapters?.find(a => a.source === 'lms');
  const websiteAdapter = status?.adapters_by_source?.website || status?.adapters?.find(a => a.source === 'website');

  const pendingCount = status?.total_pending ?? 0;
  const processedCount = status?.total_processed ?? 0;
  const rejectedCount = status?.total_rejected ?? 0;
  const totalCount = status?.total_inbox ?? 0;

  return (
    <div className="integrations-view">
      <PageHeader
        eyebrow="КОНТУР ИНТЕГРАЦИЙ И СВЕРКИ (B26–B29)"
        title="Шлюз интеграций и сверка"
        description="Мониторинг адаптеров внешних систем, агрегация показателей востребованности и обработка входящих партнерских заявок."
        action={
          <Button variant="secondary" onClick={reloadAll}>
            <Icon name="refresh" size={16} />
            Обновить данные
          </Button>
        }
      />

      {syncMessage && (
        <div className="success-alert" role="status">
          <Icon name="check" size={18} />
          <span>{syncMessage}</span>
          <button
            className="icon-button"
            style={{ marginLeft: 'auto' }}
            onClick={() => setSyncMessage(null)}
            aria-label="Закрыть"
          >
            <Icon name="close" size={14} />
          </button>
        </div>
      )}

      {statusError ? <ErrorAlert error={statusError} onRetry={loadStatus} /> : null}

      {/* SECTION 1: External System Status Cards */}
      <section className="integrations-adapters-grid" aria-label="Статус внешних адаптеров">
        {/* Card 1: LMS Zion */}
        <div className="adapter-card">
          <div className="adapter-card-header">
            <div className="adapter-title-group">
              <span className="eyebrow">СИСТЕМА ДИСТАНЦИОННОГО ОБУЧЕНИЯ</span>
              <h3>LMS Zion (Учебные метрики)</h3>
              <p>{lmsAdapter?.endpoint || 'https://rtkb.zion-lms.ru'}</p>
            </div>
            <div className="adapter-badges">
              <span className="stage-badge tone-purple">
                <i />
                {lmsAdapter?.mode === 'live' ? 'Боевой шлюз' : 'Эмуляция контракта'}
              </span>
              <span className="status-indicator-active">
                <i />
                {lmsAdapter?.status === 'ok' ? 'Подключено' : 'Активен'}
              </span>
            </div>
          </div>

          <div className="adapter-metrics-row">
            <div className="adapter-metric-item">
              <span>Всего метрик</span>
              <strong>{status?.total_metrics ?? '—'}</strong>
            </div>
            <div className="adapter-metric-item">
              <span>Когорт в базе</span>
              <strong>{metrics?.total_cohorts ?? '—'}</strong>
            </div>
            <div className="adapter-metric-item">
              <span>Зачислено</span>
              <strong>{metrics?.total_enrolled ?? '—'}</strong>
            </div>
            <div className="adapter-metric-item">
              <span>Завершили</span>
              <strong>{metrics?.total_completed ?? '—'}</strong>
            </div>
          </div>

          <div className="adapter-card-footer">
            <div className="adapter-last-sync">
              <Icon name="clock" size={14} />
              <span>
                {status?.last_synced_at
                  ? `Синхронизировано: ${formatDate(status.last_synced_at)}`
                  : 'Задержка ответа: ' + (lmsAdapter?.latency_ms ?? 14) + ' мс'}
              </span>
            </div>
            <Button
              variant="primary"
              disabled={syncingSource === 'lms'}
              onClick={() => handleSync('lms')}
            >
              {syncingSource === 'lms' ? (
                <>
                  <span className="spinner small" />
                  Синхронизация…
                </>
              ) : (
                <>
                  <Icon name="refresh" size={16} />
                  Синхронизировать сейчас
                </>
              )}
            </Button>
          </div>
        </div>

        {/* Card 2: Laravel Public Website */}
        <div className="adapter-card">
          <div className="adapter-card-header">
            <div className="adapter-title-group">
              <span className="eyebrow">ПОРТАЛ ОБРАЩЕНИЙ ВУЗОВ</span>
              <h3>Сайт ИТ Школы (Заявки)</h3>
              <p>{websiteAdapter?.endpoint || 'https://it-school.rt.ru'}</p>
            </div>
            <div className="adapter-badges">
              <span className="stage-badge tone-purple">
                <i />
                {websiteAdapter?.mode === 'live' ? 'Боевой шлюз' : 'Эмуляция контракта'}
              </span>
              <span className="status-indicator-active">
                <i />
                {websiteAdapter?.status === 'ok' ? 'Подключено' : 'Активен'}
              </span>
            </div>
          </div>

          <div className="adapter-metrics-row">
            <div className="adapter-metric-item">
              <span>Всего заявок</span>
              <strong>{totalCount}</strong>
            </div>
            <div className="adapter-metric-item pending">
              <span>Ожидают сверки</span>
              <strong>{pendingCount}</strong>
            </div>
            <div className="adapter-metric-item">
              <span>Сопоставлено</span>
              <strong>{processedCount}</strong>
            </div>
            <div className="adapter-metric-item">
              <span>Отклонено</span>
              <strong>{rejectedCount}</strong>
            </div>
          </div>

          <div className="adapter-card-footer">
            <div className="adapter-last-sync">
              <Icon name="clock" size={14} />
              <span>
                {status?.last_synced_at
                  ? `Синхронизировано: ${formatDate(status.last_synced_at)}`
                  : 'Задержка ответа: ' + (websiteAdapter?.latency_ms ?? 18) + ' мс'}
              </span>
            </div>
            <Button
              variant="primary"
              disabled={syncingSource === 'website'}
              onClick={() => handleSync('website')}
            >
              {syncingSource === 'website' ? (
                <>
                  <span className="spinner small" />
                  Синхронизация…
                </>
              ) : (
                <>
                  <Icon name="refresh" size={16} />
                  Синхронизировать сейчас
                </>
              )}
            </Button>
          </div>
        </div>
      </section>

      {/* SECTION 2: Learning Metrics Showcase */}
      <section className="panel" style={{ padding: '24px', marginBottom: '24px' }}>
        <div className="panel-heading">
          <div>
            <span className="eyebrow">ПОКАЗАТЕЛИ ВОСТРЕБОВАННОСТИ ПРОГРАММ (AC12)</span>
            <h2>Витрина данных учебного процесса</h2>
            <p>Агрегированные данные из LMS Zion по когортам, зачислениям и завершению курсов</p>
          </div>
          <span className="quiet-badge">
            {metrics?.by_program.length ?? 0} программ · {metrics?.by_organization.length ?? 0} вузов
          </span>
        </div>

        {metricsError ? <ErrorAlert error={metricsError} onRetry={loadMetrics} /> : null}

        {metricsLoading && !metrics ? (
          <Loading label="Загружаем метрики обучения…" />
        ) : metrics ? (
          <>
            <div className="stats-grid" style={{ marginTop: '20px' }}>
              <div className="stat-card">
                <div className="stat-card-top">
                  <span>Активные когорты</span>
                  <span className="stat-icon tone-purple">
                    <Icon name="users" size={18} />
                  </span>
                </div>
                <strong>
                  <Count value={metrics.total_cohorts} />
                </strong>
                <small>Учебных групп в текущем цикле</small>
              </div>

              <div className="stat-card">
                <div className="stat-card-top">
                  <span>Студентов зачислено</span>
                  <span className="stat-icon tone-blue">
                    <Icon name="chart" size={18} />
                  </span>
                </div>
                <strong>
                  <Count value={metrics.total_enrolled} />
                </strong>
                <small>Всего обучающихся по направлениям</small>
              </div>

              <div className="stat-card">
                <div className="stat-card-top">
                  <span>Завершили обучение</span>
                  <span className="stat-icon tone-green">
                    <Icon name="check" size={18} />
                  </span>
                </div>
                <strong>
                  <Count value={metrics.total_completed} />
                </strong>
                <small>Успешно освоили программу</small>
              </div>

              <div className="stat-card">
                <div className="stat-card-top">
                  <span>Средняя посещаемость</span>
                  <span className="stat-icon tone-orange">
                    <Icon name="clock" size={18} />
                  </span>
                </div>
                <strong>{metrics.avg_attendance_rate}%</strong>
                <small>Посещаемость занятий и вебинаров</small>
              </div>
            </div>

            {/* Breakdown Grid: By Program & By University */}
            <div className="metrics-breakdown-grid">
              {/* Left Column: Programs */}
              <div
                style={{
                  background: 'var(--rtk-color-card)',
                  border: '1px solid var(--rtk-color-border)',
                  borderRadius: 'var(--rtk-radius-md)',
                  padding: '18px',
                }}
              >
                <h3 style={{ margin: '0 0 12px', fontSize: '14px', color: 'var(--rtk-color-text)' }}>
                  Распределение по программам ИТ Школы
                </h3>
                {metrics.by_program.length === 0 ? (
                  <p style={{ color: 'var(--rtk-color-muted)', fontSize: '12px' }}>
                    Нет данных по программам. Запустите синхронизацию LMS.
                  </p>
                ) : (
                  metrics.by_program.map(prog => {
                    const maxEnrolled = Math.max(
                      1,
                      ...metrics.by_program.map(p => p.students_enrolled)
                    );
                    const pct = Math.min(100, Math.round((prog.students_enrolled / maxEnrolled) * 100));
                    return (
                      <div className="program-metric-row" key={prog.program_id}>
                        <div className="program-metric-header">
                          <strong>{prog.program_name}</strong>
                          <span style={{ color: 'var(--rtk-color-primary)', fontWeight: 600 }}>
                            {prog.active_cohorts} когорт
                          </span>
                        </div>
                        <div className="program-metric-stats">
                          <span>Зачислено: {prog.students_enrolled}</span>
                          <span>Завершили: {prog.students_completed}</span>
                          <span>Посещаемость: {prog.avg_attendance_rate}%</span>
                        </div>
                        <div className="program-metric-bar">
                          <div className="program-metric-fill" style={{ width: `${pct}%` }} />
                        </div>
                      </div>
                    );
                  })
                )}
              </div>

              {/* Right Column: Universities */}
              <div
                style={{
                  background: 'var(--rtk-color-card)',
                  border: '1px solid var(--rtk-color-border)',
                  borderRadius: 'var(--rtk-radius-md)',
                  padding: '18px',
                }}
              >
                <h3 style={{ margin: '0 0 12px', fontSize: '14px', color: 'var(--rtk-color-text)' }}>
                  Участие вузов-партнёров
                </h3>
                {metrics.by_organization.length === 0 ? (
                  <p style={{ color: 'var(--rtk-color-muted)', fontSize: '12px' }}>
                    Нет данных по организациям.
                  </p>
                ) : (
                  <div className="table-scroll">
                    <table className="data-table" style={{ fontSize: '11px' }}>
                      <thead>
                        <tr>
                          <th>ВУЗ / Партнёр</th>
                          <th style={{ textAlign: 'right' }}>Студентов</th>
                          <th style={{ textAlign: 'right' }}>Посещаемость</th>
                        </tr>
                      </thead>
                      <tbody>
                        {metrics.by_organization.map(org => (
                          <tr key={org.organization_id}>
                            <td>
                              <strong>{org.organization_name}</strong>
                              <span className="cell-secondary">{org.active_cohorts} когорт</span>
                            </td>
                            <td style={{ textAlign: 'right', fontWeight: 600 }}>
                              {org.students_enrolled}
                            </td>
                            <td style={{ textAlign: 'right', color: 'var(--rtk-color-muted)' }}>
                              {org.avg_attendance_rate}%
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          </>
        ) : null}
      </section>

      {/* SECTION 3: Reconciliation Inbox Table */}
      <section className="panel" style={{ padding: '24px' }}>
        <div className="panel-heading">
          <div>
            <span className="eyebrow">ОЧЕРЕДЬ ВХОДЯЩИХ ОБРАЩЕНИЙ (B29, AC29)</span>
            <h2>Сверка партнерских заявок с сайта</h2>
            <p>
              Входящие заявки от представителей образовательных организаций для проверки и привязки
            </p>
          </div>
        </div>

        {/* Filter Bar */}
        <div className="inbox-filter-bar" style={{ marginTop: '18px' }}>
          <div className="inbox-tabs" role="tablist" aria-label="Статус заявок">
            <button
              className={`inbox-tab-btn ${statusFilter === 'pending' ? 'active' : ''}`}
              onClick={() => {
                setStatusFilter('pending');
                setPage(1);
              }}
              role="tab"
              aria-selected={statusFilter === 'pending'}
            >
              <i style={{ display: 'inline-block', width: 6, height: 6, borderRadius: '50%', background: 'currentColor' }} />
              Требуют внимания <b>{pendingCount}</b>
            </button>
            <button
              className={`inbox-tab-btn ${statusFilter === 'processed' ? 'active' : ''}`}
              onClick={() => {
                setStatusFilter('processed');
                setPage(1);
              }}
              role="tab"
              aria-selected={statusFilter === 'processed'}
            >
              Сопоставлено <b>{processedCount}</b>
            </button>
            <button
              className={`inbox-tab-btn ${statusFilter === 'rejected' ? 'active' : ''}`}
              onClick={() => {
                setStatusFilter('rejected');
                setPage(1);
              }}
              role="tab"
              aria-selected={statusFilter === 'rejected'}
            >
              Отклонено <b>{rejectedCount}</b>
            </button>
            <button
              className={`inbox-tab-btn ${statusFilter === 'all' ? 'active' : ''}`}
              onClick={() => {
                setStatusFilter('all');
                setPage(1);
              }}
              role="tab"
              aria-selected={statusFilter === 'all'}
            >
              Все записи <b>{totalCount}</b>
            </button>
          </div>

          <div style={{ minWidth: '260px' }}>
            <div className="input-icon">
              <Icon name="search" size={16} />
              <input
                type="text"
                placeholder="Поиск по вузу или заявителю…"
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                aria-label="Поиск по очереди сверки"
              />
            </div>
          </div>
        </div>

        {inboxError ? <ErrorAlert error={inboxError} onRetry={() => loadInbox(page, statusFilter)} /> : null}

        {inboxLoading && !inbox ? (
          <Loading label="Загружаем очередь сверки…" />
        ) : !inbox || filteredItems.length === 0 ? (
          <EmptyState
            title="Заявок не найдено"
            description={
              statusFilter === 'pending'
                ? 'Нет входящих заявок, требующих обработки оператора.'
                : 'По выбранному фильтру записи отсутствуют.'
            }
            action={
              <Button variant="secondary" onClick={() => handleSync('website')}>
                <Icon name="refresh" size={16} />
                Синхронизировать сайт
              </Button>
            }
          />
        ) : (
          <>
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Дата получения</th>
                    <th>Источник</th>
                    <th>Организация / ВУЗ</th>
                    <th>Представитель / Контакт</th>
                    <th>Желаемая программа</th>
                    <th>Статус сверки</th>
                    <th style={{ textAlign: 'right' }}>Действие</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredItems.map(item => {
                    const p = item.payload;
                    const orgName = p.organization_name || '—';
                    const repName = p.representative_name || '—';
                    const repPos = p.representative_position;
                    const email = p.representative_email;
                    const phone = p.representative_phone;
                    const progName = p.program_name || 'Не указана';

                    return (
                      <tr key={item.id}>
                        <td>
                          <span className="cell-date">{formatDate(item.received_at)}</span>
                          <span className="cell-secondary">#{item.external_id}</span>
                        </td>
                        <td>
                          <span className="stage-badge tone-purple">
                            <i />
                            {item.source === 'website' ? 'Сайт' : item.source.toUpperCase()}
                          </span>
                        </td>
                        <td>
                          <strong>{orgName}</strong>
                          {item.matched_organization_name && (
                            <span className="cell-secondary" style={{ color: 'var(--rtk-color-success)' }}>
                              ✓ В базе: {item.matched_organization_name}
                            </span>
                          )}
                          {p.comments && (
                            <span
                              className="cell-cycle"
                              style={{ maxWidth: '240px', overflow: 'hidden', textOverflow: 'ellipsis' }}
                              title={String(p.comments)}
                            >
                              «{String(p.comments)}»
                            </span>
                          )}
                        </td>
                        <td>
                          <div className="table-person">
                            <Avatar name={repName} small />
                            <div>
                              <strong>{repName}</strong>
                              {repPos && <span className="cell-secondary">{repPos}</span>}
                              {(email || phone) && (
                                <span className="cell-cycle">
                                  {email} {phone ? `· ${phone}` : ''}
                                </span>
                              )}
                            </div>
                          </div>
                        </td>
                        <td>
                          <span className="cell-primary">{progName}</span>
                        </td>
                        <td>
                          <span className={`table-badge ${item.status}`}>
                            {item.status === 'pending' && 'Требует внимания'}
                            {item.status === 'processed' && 'Сопоставлено'}
                            {item.status === 'rejected' && 'Отклонено'}
                            {item.status === 'quarantined' && 'В карантине'}
                          </span>
                          {item.error_message && item.status === 'rejected' && (
                            <span className="cell-secondary" style={{ color: 'var(--rtk-color-danger)' }}>
                              Причина: {item.error_message}
                            </span>
                          )}
                        </td>
                        <td style={{ textAlign: 'right' }}>
                          {item.status === 'pending' ? (
                            <Button
                              variant="primary"
                              onClick={() => setResolveItem(item)}
                            >
                              <Icon name="check" size={14} />
                              Разрешить
                            </Button>
                          ) : item.matched_interaction_id ? (
                            <Button
                              variant="ghost"
                              onClick={() => openInteraction(item.matched_interaction_id!)}
                              title="Открыть созданное взаимодействие"
                            >
                              Карточка <Icon name="arrow" size={14} />
                            </Button>
                          ) : (
                            <span style={{ color: 'var(--rtk-color-muted)', fontSize: '11px' }}>
                              Обработано
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {inbox.total > pageSize && (
              <div className="pagination">
                <span>
                  Показано {filteredItems.length} из {inbox.total} записей
                </span>
                <div>
                  <Button
                    variant="ghost"
                    disabled={page <= 1}
                    onClick={() => setPage(p => Math.max(1, p - 1))}
                  >
                    Назад
                  </Button>
                  <span>
                    Страница {page} из {Math.ceil(inbox.total / pageSize)}
                  </span>
                  <Button
                    variant="ghost"
                    disabled={page >= Math.ceil(inbox.total / pageSize)}
                    onClick={() => setPage(p => p + 1)}
                  >
                    Вперёд
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </section>

      {/* SECTION 4: Resolution Modal Dialog */}
      {resolveItem && catalogs && (
        <ResolveModal
          api={api}
          catalogs={catalogs}
          me={me}
          item={resolveItem}
          onClose={() => setResolveItem(null)}
          onSuccess={(interactionId?: string) => {
            setResolveItem(null);
            reloadAll();
            if (interactionId) {
              openInteraction(interactionId);
            }
          }}
        />
      )}
    </div>
  );
}

// RESOLVE MODAL COMPONENT
interface ResolveModalProps {
  api: ApiClient;
  catalogs: Catalogs;
  me: User;
  item: IntegrationInboxItem;
  onClose: () => void;
  onSuccess: (interactionId?: string) => void;
}

function ResolveModal({
  api,
  catalogs,
  me,
  item,
  onClose,
  onSuccess,
}: ResolveModalProps) {
  const p = item.payload;
  const rawOrgName = p.organization_name || '';

  const matchedOrg = useMemo(() => {
    if (item.matched_organization_id) {
      return catalogs.organizations.find(o => o.id === item.matched_organization_id);
    }
    if (!rawOrgName) return undefined;
    return catalogs.organizations.find(
      o => o.name.toLowerCase() === rawOrgName.toLowerCase() || o.name.toLowerCase().includes(rawOrgName.toLowerCase())
    );
  }, [catalogs.organizations, item.matched_organization_id, rawOrgName]);

  const [action, setAction] = useState<ReconciliationAction>(
    matchedOrg ? 'link_existing' : 'create_new'
  );

  const [selectedOrgId, setSelectedOrgId] = useState(matchedOrg?.id || catalogs.organizations[0]?.id || '');

  const [newOrgName, setNewOrgName] = useState(rawOrgName);
  const [newOrgType, setNewOrgType] = useState('university');
  const [contactName, setContactName] = useState(p.representative_name || '');
  const [contactPosition, setContactPosition] = useState(p.representative_position || 'Представитель организации');
  const [contactEmail, setContactEmail] = useState(p.representative_email || '');
  const [contactPhone, setContactPhone] = useState(p.representative_phone || '');

  const [createInteraction, setCreateInteraction] = useState(true);
  const [ownerId, setOwnerId] = useState(
    catalogs.owners.find(o => o.id === me.id)?.id || catalogs.owners[0]?.id || ''
  );
  const [programId, setProgramId] = useState(
    catalogs.programs.find(prog => prog.id === p.program_id || prog.name === p.program_name)?.id ||
      catalogs.programs[0]?.id ||
      ''
  );
  const [interactionTitle, setInteractionTitle] = useState(`Заявка: ${rawOrgName || 'Партнёр'}`);

  const [rejectionReason, setRejectionReason] = useState('Не соответствует критериям партнерской программы');

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);

    try {
      let body: Record<string, unknown> = { action };

      if (action === 'reject') {
        body = {
          action: 'reject',
          reason: rejectionReason,
        };
      } else if (action === 'link_existing') {
        body = {
          action: 'link_existing',
          organization_id: selectedOrgId,
          representative_name: contactName,
          representative_position: contactPosition,
          representative_email: contactEmail,
          representative_phone: contactPhone,
          create_interaction: createInteraction,
          owner_id: createInteraction ? ownerId : undefined,
          program_id: createInteraction ? programId : undefined,
          interaction_title: createInteraction ? interactionTitle : undefined,
        };
      } else if (action === 'create_new') {
        body = {
          action: 'create_new',
          organization_name: newOrgName,
          organization_type: newOrgType,
          representative_name: contactName,
          representative_position: contactPosition,
          representative_email: contactEmail,
          representative_phone: contactPhone,
          create_interaction: createInteraction,
          owner_id: createInteraction ? ownerId : undefined,
          program_id: createInteraction ? programId : undefined,
          interaction_title: createInteraction ? interactionTitle : undefined,
        };
      }

      const res = await api.resolveInboxItem(item.id, body, makeMutationKey());
      onSuccess(res?.interaction_id || res?.matched_interaction_id);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      title={`Сверка заявки #${item.external_id}`}
      subtitle="Сопоставление входящего обращения с реестром организаций и создание взаимодействия"
      onClose={onClose}
      busy={busy}
      wide
    >
      <form onSubmit={handleSubmit}>
        <div className="modal-body">
          {error ? <ErrorAlert error={error} /> : null}

          {/* Inbound Data Summary */}
          <div className="inbound-data-card">
            <span className="eyebrow">ДАННЫЕ ВХОДЯЩЕГО ОБРАЩЕНИЯ</span>
            <div className="inbound-data-grid">
              <div className="inbound-data-item">
                <span>Организация</span>
                <strong>{p.organization_name || 'Не указана'}</strong>
              </div>
              <div className="inbound-data-item">
                <span>Представитель</span>
                <strong>{p.representative_name || 'Не указан'}</strong>
              </div>
              <div className="inbound-data-item">
                <span>Контакты</span>
                <strong>
                  {p.representative_email || '—'} {p.representative_phone ? `· ${p.representative_phone}` : ''}
                </strong>
              </div>
              <div className="inbound-data-item">
                <span>Запрошенная программа</span>
                <strong>{p.program_name || 'Не выбрана'}</strong>
              </div>
            </div>
            {p.comments && (
              <div style={{ marginTop: '8px', fontSize: '11px', color: 'var(--rtk-color-muted)' }}>
                <strong>Комментарий заявителя:</strong> {String(p.comments)}
              </div>
            )}
          </div>

          {/* Action Choice Cards */}
          <div className="choice-cards-container" role="radiogroup" aria-label="Вариант разрешения">
            <button
              type="button"
              className={`choice-card ${action === 'link_existing' ? 'active' : ''}`}
              onClick={() => setAction('link_existing')}
            >
              <div className="choice-card-radio">
                <input
                  type="radio"
                  name="action"
                  value="link_existing"
                  checked={action === 'link_existing'}
                  onChange={() => setAction('link_existing')}
                />
                Привязать к вузу
              </div>
              <p>Сопоставить с существующей организацией в каталоге</p>
            </button>

            <button
              type="button"
              className={`choice-card ${action === 'create_new' ? 'active' : ''}`}
              onClick={() => setAction('create_new')}
            >
              <div className="choice-card-radio">
                <input
                  type="radio"
                  name="action"
                  value="create_new"
                  checked={action === 'create_new'}
                  onChange={() => setAction('create_new')}
                />
                Новый вуз и контакт
              </div>
              <p>Создать новую организацию и добавить представителя</p>
            </button>

            <button
              type="button"
              className={`choice-card ${action === 'reject' ? 'active' : ''}`}
              onClick={() => setAction('reject')}
            >
              <div className="choice-card-radio">
                <input
                  type="radio"
                  name="action"
                  value="reject"
                  checked={action === 'reject'}
                  onChange={() => setAction('reject')}
                />
                Отклонить
              </div>
              <p>Отклонить заявку с указанием причины</p>
            </button>
          </div>

          {/* Conditional Options Form */}
          {action === 'link_existing' && (
            <div className="field">
              <span>Выберите существующую организацию *</span>
              <select
                value={selectedOrgId}
                onChange={e => {
                  setSelectedOrgId(e.target.value);
                  const org = catalogs.organizations.find(o => o.id === e.target.value);
                  if (org) {
                    setInteractionTitle(`Заявка: ${org.name}`);
                  }
                }}
                required
              >
                {catalogs.organizations.map(org => (
                  <option key={org.id} value={org.id}>
                    {org.name} ({org.type})
                  </option>
                ))}
              </select>
            </div>
          )}

          {action === 'create_new' && (
            <div className="form-grid">
              <label className="field span-2">
                <span>Название организации *</span>
                <input
                  type="text"
                  value={newOrgName}
                  onChange={e => {
                    setNewOrgName(e.target.value);
                    setInteractionTitle(`Заявка: ${e.target.value}`);
                  }}
                  required
                />
              </label>
              <label className="field">
                <span>Тип организации</span>
                <select value={newOrgType} onChange={e => setNewOrgType(e.target.value)}>
                  <option value="university">Высшее образование (ВУЗ)</option>
                  <option value="college">Среднее профессиональное (Колледж)</option>
                  <option value="partner">Партнёрская организация</option>
                  <option value="other">Другое</option>
                </select>
              </label>
              <label className="field">
                <span>ФИО представителя</span>
                <input
                  type="text"
                  value={contactName}
                  onChange={e => setContactName(e.target.value)}
                />
              </label>
              <label className="field">
                <span>Должность</span>
                <input
                  type="text"
                  value={contactPosition}
                  onChange={e => setContactPosition(e.target.value)}
                />
              </label>
              <label className="field">
                <span>Электронная почта</span>
                <input
                  type="email"
                  value={contactEmail}
                  onChange={e => setContactEmail(e.target.value)}
                />
              </label>
              <label className="field span-2">
                <span>Телефон</span>
                <input
                  type="text"
                  value={contactPhone}
                  onChange={e => setContactPhone(e.target.value)}
                />
              </label>
            </div>
          )}

          {action === 'reject' && (
            <label className="field">
              <span>Причина отклонения заявки *</span>
              <textarea
                value={rejectionReason}
                onChange={e => setRejectionReason(e.target.value)}
                rows={3}
                required
              />
            </label>
          )}

          {/* Interaction Creation Toggle (for link_existing and create_new) */}
          {(action === 'link_existing' || action === 'create_new') && (
            <div
              style={{
                marginTop: '18px',
                paddingTop: '16px',
                borderTop: '1px solid var(--rtk-color-border-subtle)',
              }}
            >
              <label
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  fontWeight: 600,
                  fontSize: '13px',
                  cursor: 'pointer',
                  marginBottom: '14px',
                }}
              >
                <input
                  type="checkbox"
                  checked={createInteraction}
                  onChange={e => setCreateInteraction(e.target.checked)}
                />
                Создать карточку взаимодействия в CRM
              </label>

              {createInteraction && (
                <div className="form-grid">
                  <label className="field span-2">
                    <span>Тема взаимодействия *</span>
                    <input
                      type="text"
                      value={interactionTitle}
                      onChange={e => setInteractionTitle(e.target.value)}
                      required
                    />
                  </label>
                  <label className="field">
                    <span>Ответственный менеджер *</span>
                    <select
                      value={ownerId}
                      onChange={e => setOwnerId(e.target.value)}
                      required
                    >
                      {catalogs.owners.map(owner => (
                        <option key={owner.id} value={owner.id}>
                          {owner.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="field">
                    <span>ИТ-программа</span>
                    <select
                      value={programId}
                      onChange={e => setProgramId(e.target.value)}
                    >
                      {catalogs.programs.map(prog => (
                        <option key={prog.id} value={prog.id}>
                          {prog.name}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="modal-actions">
          <Button type="button" variant="ghost" disabled={busy} onClick={onClose}>
            Отмена
          </Button>
          <Button type="submit" variant="primary" disabled={busy}>
            {busy ? (
              <>
                <span className="spinner small" />
                Сохранение…
              </>
            ) : action === 'reject' ? (
              'Отклонить обращение'
            ) : (
              'Подтвердить сверку'
            )}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
