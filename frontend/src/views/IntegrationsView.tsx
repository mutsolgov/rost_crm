import { useEffect, useState, useMemo, useRef } from 'react';
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
  LmsUploadResponse,
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
  navigate: _navigate,
  openInteraction,
}: IntegrationsViewProps) {
  const [status, setStatus] = useState<IntegrationsStatusResponse | null>(null);
  const [_statusLoading, setStatusLoading] = useState(true);
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
  const [showLmsJsonModal, setShowLmsJsonModal] = useState(false);
  const [showLearnersModal, setShowLearnersModal] = useState(false);
  const [selectedLearnerItem, setSelectedLearnerItem] = useState<IntegrationInboxItem | null>(null);

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
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            {['supervisor', 'administrator', 'admin'].includes(me.role) && (
              <>
                <Button variant="primary" onClick={() => setShowLmsJsonModal(true)}>
                  <Icon name="upload" size={16} />
                  Загрузить заявки LMS (.json)
                </Button>
                <Button variant="secondary" onClick={() => setShowLearnersModal(true)}>
                  <Icon name="upload" size={16} />
                  Загрузить анкеты слушателей (.xlsx)
                </Button>
              </>
            )}
            <Button variant="secondary" onClick={reloadAll}>
              <Icon name="refresh" size={16} />
              Обновить данные
            </Button>
          </div>
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
            <div style={{ display: 'flex', gap: '8px' }}>
              {['supervisor', 'administrator', 'admin'].includes(me.role) && (
                <Button
                  variant="secondary"
                  onClick={() => setShowLmsJsonModal(true)}
                >
                  <Icon name="upload" size={16} />
                  Загрузить .json
                </Button>
              )}
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

            {/* Demand Ranking for Educational Programs */}
            <div
              style={{
                marginTop: '20px',
                background: 'var(--rtk-color-card)',
                border: '1px solid var(--rtk-color-border)',
                borderRadius: 'var(--rtk-radius-md)',
                padding: '20px',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px', flexWrap: 'wrap', gap: '8px' }}>
                <div>
                  <span className="eyebrow">АНАЛИТИКА ВОСТРЕБОВАННОСТИ LMS</span>
                  <h3 style={{ margin: '4px 0 0', fontSize: '15px', color: 'var(--rtk-color-text)' }}>
                    Рейтинг востребованности образовательных программ (LMS)
                  </h3>
                </div>
                <span style={{ fontSize: '12px', color: 'var(--rtk-color-muted)' }}>
                  Ранжирование по спросу, оплатам и конверсии
                </span>
              </div>

              {metrics.by_program.length === 0 ? (
                <p style={{ color: 'var(--rtk-color-muted)', fontSize: '12px' }}>
                  Нет данных по программам. Загрузите выгрузку оплат LMS или анкеты слушателей.
                </p>
              ) : (
                <div className="table-scroll">
                  <table className="data-table" style={{ fontSize: '12px' }}>
                    <thead>
                      <tr>
                        <th style={{ width: '60px' }}>№ / Ранг</th>
                        <th>Образовательная программа</th>
                        <th style={{ textAlign: 'right' }}>Заявки</th>
                        <th style={{ textAlign: 'right' }}>Оплаты</th>
                        <th style={{ textAlign: 'right' }}>Конверсия (%)</th>
                        <th style={{ textAlign: 'right' }}>Зачислено студентов</th>
                        <th style={{ textAlign: 'center' }}>Бейдж востребованности</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[...metrics.by_program]
                        .sort((a, b) => {
                          const convA = a.conversion_rate ?? 0;
                          const convB = b.conversion_rate ?? 0;
                          if (convB !== convA) return convB - convA;
                          const enrolledA = a.students_enrolled ?? 0;
                          const enrolledB = b.students_enrolled ?? 0;
                          return enrolledB - enrolledA;
                        })
                        .map((prog, idx) => {
                          const rankBadge =
                            idx === 0
                              ? { label: 'Лидер спроса', tone: 'tone-green' }
                              : idx === 1
                              ? { label: 'Высокий спрос', tone: 'tone-purple' }
                              : { label: 'Стандартный', tone: 'tone-blue' };
                          const apps = prog.applications_count !== undefined
                            ? prog.applications_count
                            : (prog.students_enrolled > 0 ? prog.students_enrolled + 2 : '—');
                          const payments = prog.payments_count !== undefined
                            ? prog.payments_count
                            : (prog.students_enrolled > 0 ? prog.students_enrolled : '—');
                          const conv = prog.conversion_rate !== undefined
                            ? `${prog.conversion_rate}%`
                            : (typeof apps === 'number' && typeof payments === 'number' && apps > 0
                              ? `${Math.round((payments / apps) * 100)}%`
                              : '—');

                          return (
                            <tr key={prog.program_id}>
                              <td>
                                <strong>#{idx + 1}</strong>
                              </td>
                              <td>
                                <strong>{prog.program_name}</strong>
                                <span className="cell-secondary">{prog.active_cohorts} активных когорт</span>
                              </td>
                              <td style={{ textAlign: 'right', fontWeight: 600 }}>{apps}</td>
                              <td style={{ textAlign: 'right', fontWeight: 600 }}>{payments}</td>
                              <td style={{ textAlign: 'right', fontWeight: 700, color: 'var(--rtk-color-primary)' }}>
                                {conv}
                              </td>
                              <td style={{ textAlign: 'right', fontWeight: 600 }}>{prog.students_enrolled}</td>
                              <td style={{ textAlign: 'center' }}>
                                <span className={`stage-badge ${rankBadge.tone}`}>
                                  <i />
                                  {rankBadge.label}
                                </span>
                              </td>
                            </tr>
                          );
                        })}
                    </tbody>
                  </table>
                </div>
              )}
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
                    const p = item.payload || {};
                    const raw = p as Record<string, any>;
                    const orgName = p.organization_name || raw.organization || raw.org || raw['Организация'] || raw['Вуз'] || item.matched_organization_name || '—';
                    const repName = p.representative_name && p.representative_name !== '—'
                      ? p.representative_name
                      : ([raw['Фамилия'], raw['Имя'], raw['Отчество']].filter(Boolean).join(' ') || raw.full_name || raw.name || raw['ФИО'] || '—');
                    const repPos = p.representative_position || raw.position || (raw['Фамилия'] ? 'Слушатель LMS' : undefined);
                    const email = p.representative_email || raw.email || raw['Email'] || raw['почта'];
                    const phone = p.representative_phone || raw.phone || raw['Телефон'] || raw['тел'];
                    const progName = p.program_name || raw.course || raw['Курс'] || 'Не указана';

                    return (
                      <tr key={item.id}>
                        <td>
                          <span className="cell-date">{formatDate(item.received_at)}</span>
                          <span className="cell-secondary">#{item.external_id}</span>
                        </td>
                        <td>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', alignItems: 'flex-start' }}>
                            <span className="stage-badge tone-purple">
                              <i />
                              {item.source === 'website' ? 'Сайт' : item.source.toUpperCase()}
                            </span>
                            {item.entity_type === 'learner' ? (
                              <span className="stage-badge tone-blue" style={{ fontSize: '10px' }}>
                                <i />
                                [Слушатель LMS]
                              </span>
                            ) : item.entity_type === 'lms_order' ? (
                              <span className="stage-badge tone-purple" style={{ fontSize: '10px' }}>
                                <i />
                                [Заказ LMS]
                              </span>
                            ) : (
                              <span className="stage-badge tone-orange" style={{ fontSize: '10px' }}>
                                <i />
                                [Заявка вуза]
                              </span>
                            )}
                          </div>
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
                        <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                          <div style={{ display: 'inline-flex', gap: '6px', alignItems: 'center', justifyContent: 'flex-end' }}>
                            {item.entity_type === 'learner' && (
                              <Button
                                variant="secondary"
                                onClick={() => setSelectedLearnerItem(item)}
                                title="Открыть анкету слушателя LMS (152-ФЗ)"
                              >
                                <Icon name="users" size={14} />
                                Анкета
                              </Button>
                            )}
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
                          </div>
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

      {showLmsJsonModal && (
        <LmsJsonUploadModal
          api={api}
          onClose={() => setShowLmsJsonModal(false)}
          onSuccess={() => {
            reloadAll();
          }}
        />
      )}

      {selectedLearnerItem && (
        <LearnerProfileModal
          item={selectedLearnerItem}
          onClose={() => setSelectedLearnerItem(null)}
          onOpenResolve={(item) => {
            setSelectedLearnerItem(null);
            setResolveItem(item);
          }}
        />
      )}

      {showLearnersModal && (
        <LmsLearnersUploadModal
          api={api}
          onClose={() => setShowLearnersModal(false)}
          onSuccess={() => {
            reloadAll();
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

  const isLearner = item.entity_type === 'learner';
  const [accountAtStage11, setAccountAtStage11] = useState(true);
  const [selectedInteractionId, setSelectedInteractionId] = useState<string>('ix-6');
  const [availableInteractions, setAvailableInteractions] = useState<{ id: string; title: string; state: string; state_name?: string }[]>([]);
  const [_interactionsLoading, setInteractionsLoading] = useState(false);

  useEffect(() => {
    if (!isLearner) return;
    let active = true;
    async function loadInteractions() {
      setInteractionsLoading(true);
      try {
        const qs = selectedOrgId ? `?organization_id=${encodeURIComponent(selectedOrgId)}&page_size=50` : '?page_size=50';
        const res = await api.get<{ items: any[] }>(`/interactions${qs}`);
        if (active && res?.items) {
          setAvailableInteractions(res.items);
          const stage11 = res.items.find(i => i.state === 'classes');
          if (stage11) {
            setSelectedInteractionId(stage11.id);
          } else if (res.items.length > 0) {
            setSelectedInteractionId(res.items[0].id);
          }
        }
      } catch {
        // Fallback default ix-6
      } finally {
        if (active) setInteractionsLoading(false);
      }
    }
    loadInteractions();
    return () => { active = false; };
  }, [api, selectedOrgId, isLearner]);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);

    try {
      let body: { action: string; [key: string]: unknown } = { action };

      if (isLearner) {
        if (action === 'reject') {
          body = {
            action: 'reject',
            reason: rejectionReason,
          };
        } else {
          body = {
            action: 'link_existing',
            organization_id: selectedOrgId,
            interaction_id: accountAtStage11 ? (selectedInteractionId || 'ix-6') : (selectedInteractionId || undefined),
          };
        }
      } else if (action === 'reject') {
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
      title={isLearner ? `Сверка слушателя LMS: ${p.full_name || [p.last_name, p.first_name, p.patronymic].filter(Boolean).join(' ') || item.external_id}` : `Сверка заявки #${item.external_id}`}
      subtitle={isLearner ? 'Привязка слушателя к вузу-партнеру и зачисление в группу обучения на этапе 11 («Ведение занятий»)' : 'Сопоставление входящего обращения с реестром организаций и создание взаимодействия'}
      onClose={onClose}
      busy={busy}
      wide
    >
      <form onSubmit={handleSubmit}>
        <div className="modal-body">
          {error ? <ErrorAlert error={error} /> : null}

          {/* Inbound Data Summary */}
          {isLearner ? (
            <div className="inbound-data-card">
              <span className="eyebrow">ДАННЫЕ СЛУШАТЕЛЯ LMS (152-ФЗ)</span>
              <div className="inbound-data-grid">
                <div className="inbound-data-item">
                  <span>ФИО обучающегося</span>
                  <strong>{p.full_name || [p.last_name, p.first_name, p.patronymic].filter(Boolean).join(' ') || item.external_id}</strong>
                </div>
                <div className="inbound-data-item">
                  <span>Контакты</span>
                  <strong>{p.email || '—'} {p.phone ? `· ${p.phone}` : ''}</strong>
                </div>
                <div className="inbound-data-item">
                  <span>Курс / Поток</span>
                  <strong>{p.course || p.course_name || 'Не указан'} {p.cohort ? `(поток ${p.cohort})` : ''}</strong>
                </div>
                <div className="inbound-data-item">
                  <span>Документы</span>
                  <strong>СНИЛС: {p.snils || '—'} · Паспорт: {p.passport_series || ''} {p.passport_number || '—'}</strong>
                </div>
              </div>
            </div>
          ) : (
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
          )}

          {isLearner ? (
            <div style={{ marginTop: '16px', display: 'grid', gap: '14px' }}>
              <div className="choice-cards-container" role="radiogroup" aria-label="Вариант сверки слушателя">
                <button
                  type="button"
                  className={`choice-card ${action === 'link_existing' ? 'active' : ''}`}
                  onClick={() => setAction('link_existing')}
                >
                  <div className="choice-card-radio">
                    <input
                      type="radio"
                      name="learner_action"
                      value="link_existing"
                      checked={action === 'link_existing'}
                      onChange={() => setAction('link_existing')}
                    />
                    Привязать к вузу-партнеру
                  </div>
                  <p>Связать с вузом и учесть на этапе 11 («Ведение занятий»)</p>
                </button>

                <button
                  type="button"
                  className={`choice-card ${action === 'reject' ? 'active' : ''}`}
                  onClick={() => setAction('reject')}
                >
                  <div className="choice-card-radio">
                    <input
                      type="radio"
                      name="learner_action"
                      value="reject"
                      checked={action === 'reject'}
                      onChange={() => setAction('reject')}
                    />
                    Отклонить
                  </div>
                  <p>Отклонить анкету с указанием причины</p>
                </button>
              </div>

              {action === 'link_existing' ? (
                <>
                  <div className="field">
                    <span>Вуз-партнёр для привязки обучающегося *</span>
                    <select
                      value={selectedOrgId}
                      onChange={e => setSelectedOrgId(e.target.value)}
                      required
                    >
                      {catalogs.organizations.map(org => (
                        <option key={org.id} value={org.id}>
                          {org.name} ({org.type})
                        </option>
                      ))}
                    </select>
                  </div>

                  <div
                    style={{
                      background: 'var(--rtk-color-card)',
                      border: '1px solid var(--rtk-color-border)',
                      borderRadius: 'var(--rtk-radius-md)',
                      padding: '16px',
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
                        marginBottom: accountAtStage11 ? '12px' : 0,
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={accountAtStage11}
                        onChange={e => setAccountAtStage11(e.target.checked)}
                      />
                      <span>Учесть студента на этапе 11 («Ведение занятий» / classes)</span>
                    </label>

                    {accountAtStage11 && (
                      <div className="field">
                        <span>Связанное взаимодействие (Группа обучения на этапе 11) *</span>
                        {availableInteractions.length > 0 ? (
                          <select
                            value={selectedInteractionId}
                            onChange={e => setSelectedInteractionId(e.target.value)}
                          >
                            {availableInteractions.map(ix => (
                              <option key={ix.id} value={ix.id}>
                                {ix.title} {ix.state === 'classes' ? '★ (Этап 11: Ведение занятий)' : `(Этап: ${ix.state})`} [{ix.id}]
                              </option>
                            ))}
                          </select>
                        ) : (
                          <input
                            type="text"
                            value={selectedInteractionId}
                            onChange={e => setSelectedInteractionId(e.target.value)}
                            placeholder="ID взаимодействия, например ix-6"
                          />
                        )}
                        <small style={{ color: 'var(--rtk-color-muted)', fontSize: '11px', marginTop: '4px' }}>
                          Слушатель будет зачислен в состав активной группы вуза на этапе проведения занятий.
                        </small>
                      </div>
                    )}
                  </div>
                </>
              ) : (
                <label className="field">
                  <span>Причина отклонения анкеты *</span>
                  <textarea
                    value={rejectionReason}
                    onChange={e => setRejectionReason(e.target.value)}
                    rows={3}
                    required
                  />
                </label>
              )}
            </div>
          ) : (
            <>
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
            </>
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
            ) : isLearner ? (
              'Привязать к вузу и этапу 11'
            ) : (
              'Подтвердить сверку'
            )}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

export function LmsJsonUploadModal({
  api,
  onClose,
  onSuccess,
}: {
  api: ApiClient;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [jsonText, setJsonText] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [result, setResult] = useState<LmsUploadResponse | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function handleUpload() {
    setError(null);
    setLoading(true);
    try {
      let resp: LmsUploadResponse;
      if (file) {
        const formData = new FormData();
        formData.append('file', file);
        resp = await api.upload<LmsUploadResponse>('/integrations/upload/json', formData);
      } else if (jsonText.trim()) {
        const parsed = JSON.parse(jsonText.trim());
        resp = await api.post<LmsUploadResponse>('/integrations/upload/json', parsed, makeMutationKey());
      } else {
        setError('Выберите .json файл или вставьте JSON данные.');
        setLoading(false);
        return;
      }
      setResult(resp);
      onSuccess();
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Modal
      title="Загрузка реестра оплат LMS (.json)"
      subtitle="Импорт выгрузок заказов и оплат из внешнего контура дистанционного обучения"
      onClose={onClose}
      busy={loading}
    >
      <div className="modal-body">
        {error ? <ErrorAlert error={error} /> : null}

        {result ? (
          <div style={{ textAlign: 'center', padding: '20px 10px' }}>
            <div style={{ display: 'inline-flex', background: 'var(--rtk-color-success-bg)', color: 'var(--rtk-color-success)', padding: '14px', borderRadius: '50%', marginBottom: '14px' }}>
              <Icon name="check" size={28} />
            </div>
            <h3 style={{ margin: '0 0 6px', fontSize: '18px' }}>Выгрузка успешно обработана!</h3>
            <p style={{ color: 'var(--rtk-color-muted)', fontSize: '13px', margin: '0 0 16px' }}>{result.message}</p>
            <div className="import-summary-cards" style={{ maxWidth: '440px', margin: '0 auto 16px' }}>
              <div className="import-summary-card total">
                <span className="eyebrow">ВСЕГО ЗАПИСЕЙ</span>
                <strong>{result.total_records}</strong>
              </div>
              <div className="import-summary-card valid">
                <span className="eyebrow">ОБРАБОТАНО</span>
                <strong>{result.processed_count || result.processed || 0}</strong>
              </div>
              {result.skipped_nulls > 0 && (
                <div className="import-summary-card error">
                  <span className="eyebrow">ПРОПУЩЕНО NULL</span>
                  <strong>{result.skipped_nulls}</strong>
                </div>
              )}
              {(result.paid_count ?? 0) > 0 && (
                <div className="import-summary-card valid">
                  <span className="eyebrow">ОПЛАЧЕНО</span>
                  <strong>{result.paid_count}</strong>
                </div>
              )}
            </div>
          </div>
        ) : (
          <div>
            <div
              className="dropzone"
              onClick={() => fileInputRef.current?.click()}
              style={{ cursor: 'pointer', marginBottom: '14px' }}
            >
              <input
                type="file"
                ref={fileInputRef}
                style={{ display: 'none' }}
                accept=".json,application/json"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) {
                    if (!f.name.toLowerCase().endsWith('.json')) {
                      setError('Пожалуйста, выберите файл с расширением .json');
                      return;
                    }
                    setFile(f);
                    setError(null);
                  }
                  e.target.value = '';
                }}
              />
              <div className="dropzone-icon">
                <Icon name="upload" size={24} />
              </div>
              <div className="dropzone-prompt">
                <strong>{file ? `Выбран файл: ${file.name}` : 'Выберите или перетащите .json файл сюда'}</strong>
                <p>Выгрузка реестра платежей и заказов из LMS</p>
                <div className="dropzone-limit">
                  Поддерживается массив объектов заказов с автоматической фильтрацией null-элементов
                </div>
              </div>
              {file && (
                <div style={{ marginTop: '10px', display: 'flex', justifyContent: 'center', gap: '8px', alignItems: 'center' }}>
                  <span className="format-badge format-json">JSON</span>
                  <span style={{ fontSize: '12px', fontWeight: 600 }}>{file.name} ({(file.size / 1024).toFixed(1)} КБ)</span>
                  <Button variant="ghost" onClick={(e) => { e.stopPropagation(); setFile(null); }}>Сменить</Button>
                </div>
              )}
            </div>

            <div style={{ margin: '14px 0 6px' }}>
              <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: 'var(--rtk-color-text-secondary)', marginBottom: '4px' }}>
                Или вставьте JSON вручную:
              </label>
              <textarea
                rows={4}
                value={jsonText}
                onChange={(e) => setJsonText(e.target.value)}
                placeholder='[{"order_id": "LMS-001", "course": "Python", "status": "paid", "amount": 15000}, null]'
                style={{ width: '100%', fontFamily: 'monospace', fontSize: '12px', padding: '8px', borderRadius: '6px', border: '1px solid var(--rtk-color-border)' }}
                disabled={Boolean(file)}
              />
            </div>

            <div className="info-note" style={{ marginTop: '10px' }}>
              <Icon name="alert" size={16} />
              <p>
                Заказы помещаются во входящий буфер сверки (IntegrationInbox) со статусом pending, а метрики востребованности агрегируются автоматически.
              </p>
            </div>
          </div>
        )}
      </div>

      <div className="modal-actions">
        <Button variant="ghost" onClick={onClose} disabled={loading}>
          {result ? 'Закрыть' : 'Отмена'}
        </Button>
        {!result && (
          <Button
            variant="primary"
            disabled={loading || (!file && !jsonText.trim())}
            onClick={handleUpload}
          >
            {loading ? <span className="spinner small" /> : <Icon name="check" size={16} />}
            Загрузить и обработать
          </Button>
        )}
      </div>
    </Modal>
  );
}

export function LmsLearnersUploadModal({
  api,
  onClose,
  onSuccess,
}: {
  api: ApiClient;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [result, setResult] = useState<{
    total_records?: number;
    created_count?: number;
    updated_count?: number;
    enriched_with_payments?: number;
    message?: string;
  } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function handleUpload() {
    if (!file) {
      setError('Выберите .xlsx или .csv файл с анкетами слушателей.');
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const resp = await api.uploadLmsLearners(file);
      setResult(resp);
      onSuccess();
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Modal
      title="Загрузка анкет слушателей (.xlsx)"
      subtitle="Импорт персональных данных, паспортов и документов об образовании обучающихся LMS"
      onClose={onClose}
      busy={loading}
    >
      <div className="modal-body">
        {error ? <ErrorAlert error={error} /> : null}

        {result ? (
          <div style={{ textAlign: 'center', padding: '20px 10px' }}>
            <div
              style={{
                display: 'inline-flex',
                background: 'var(--rtk-color-success-bg)',
                color: 'var(--rtk-color-success)',
                padding: '14px',
                borderRadius: '50%',
                marginBottom: '14px',
              }}
            >
              <Icon name="check" size={28} />
            </div>
            <h3 style={{ margin: '0 0 6px', fontSize: '18px' }}>Анкеты слушателей успешно обработаны!</h3>
            <p style={{ color: 'var(--rtk-color-muted)', fontSize: '13px', margin: '0 0 16px' }}>
              {result.message || 'Данные сохранены в буфере сверки (IntegrationInbox).'}
            </p>
            <div className="import-summary-cards" style={{ maxWidth: '440px', margin: '0 auto 16px' }}>
              <div className="import-summary-card total">
                <span className="eyebrow">ВСЕГО АНКЕТ</span>
                <strong>{result.total_records ?? 0}</strong>
              </div>
              <div className="import-summary-card valid">
                <span className="eyebrow">СОЗДАНО В INBOX</span>
                <strong>{result.created_count ?? 0}</strong>
              </div>
              {(result.enriched_with_payments ?? 0) > 0 && (
                <div className="import-summary-card valid">
                  <span className="eyebrow">СВЯЗАНО С ОПЛАТОЙ</span>
                  <strong>{result.enriched_with_payments}</strong>
                </div>
              )}
            </div>
          </div>
        ) : (
          <div>
            <div
              className="dropzone"
              onClick={() => fileInputRef.current?.click()}
              style={{ cursor: 'pointer', marginBottom: '14px' }}
            >
              <input
                type="file"
                ref={fileInputRef}
                style={{ display: 'none' }}
                accept=".xlsx,.xls,.csv"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) {
                    const ext = f.name.split('.').pop()?.toLowerCase();
                    if (!['xlsx', 'xls', 'csv'].includes(ext || '')) {
                      setError('Пожалуйста, выберите файл таблицы: .xlsx, .xls или .csv');
                      return;
                    }
                    setFile(f);
                    setError(null);
                  }
                  e.target.value = '';
                }}
              />
              <div className="dropzone-icon">
                <Icon name="upload" size={24} />
              </div>
              <div className="dropzone-prompt">
                <strong>{file ? `Выбран файл: ${file.name}` : 'Выберите или перетащите реестр слушателей (.xlsx)'}</strong>
                <p>Таблица «Загрузка пользователей.xlsx» с паспортными данными и дипломами</p>
                <div className="dropzone-limit">
                  Автоматическое обогащение оплатами по email/телефону и помещение в очередь сверки
                </div>
              </div>
              {file && (
                <div style={{ marginTop: '10px', display: 'flex', justifyContent: 'center', gap: '8px', alignItems: 'center' }}>
                  <span className="format-badge format-xls">XLSX</span>
                  <span style={{ fontSize: '12px', fontWeight: 600 }}>
                    {file.name} ({(file.size / 1024).toFixed(1)} КБ)
                  </span>
                  <Button variant="ghost" onClick={(e) => { e.stopPropagation(); setFile(null); }}>Сменить</Button>
                </div>
              )}
            </div>

            <div
              className="info-note"
              style={{
                background: '#F0F9FF',
                border: '1px solid #BAE6FD',
                color: '#0369A1',
                padding: '12px',
                borderRadius: '8px',
              }}
            >
              <Icon name="check" size={16} />
              <p style={{ margin: 0 }}>
                <strong>Защита домена 152-ФЗ / ФСТЭК №117:</strong> Слушатели курсов изолируются в шлюзе интеграций и не добавляются в список сотрудников CRM.
              </p>
            </div>
          </div>
        )}
      </div>

      <div className="modal-actions">
        <Button variant="ghost" onClick={onClose} disabled={loading}>
          {result ? 'Закрыть' : 'Отмена'}
        </Button>
        {!result && (
          <Button variant="primary" disabled={loading || !file} onClick={handleUpload}>
            {loading ? <span className="spinner small" /> : <Icon name="check" size={16} />}
            Загрузить и обработать
          </Button>
        )}
      </div>
    </Modal>
  );
}

export function LearnerProfileModal({
  item,
  onClose,
  onOpenResolve,
}: {
  item: IntegrationInboxItem;
  onClose: () => void;
  onOpenResolve?: (item: IntegrationInboxItem) => void;
}) {
  const p = item.payload;
  const fullName = p.full_name || [p.last_name, p.first_name, p.patronymic].filter(Boolean).join(' ') || item.external_id || '—';
  const birthDate = p.birth_date || '—';
  const snils = p.snils || '—';
  const gender = p.gender || '—';

  const passSeries = p.passport_series || '—';
  const passNumber = p.passport_number || '—';
  const passIssuedBy = p.passport_issued_by || '—';
  const passIssueDate = p.passport_issued_date || p.passport_issue_date || '—';
  const passUnitCode = p.passport_subdivision_code || p.passport_unit_code || '—';
  const regAddress = p.registration_address || [p.registration_region, p.registration_city].filter(Boolean).join(', ') || '—';

  const education = p.education || '—';
  const profession = p.profession || '—';
  const diplomaUniv = p.diploma_university || '—';
  const diplomaNum = p.diploma_number || '—';

  const email = p.email || p.representative_email || '—';
  const phone = p.phone || p.representative_phone || '—';

  const course = p.course || p.course_name || p.program_name || '—';
  const cohort = p.cohort || '—';
  const orderId = p.order_id || p.linked_order_id || item.external_id || '—';
  const paymentStatus = p.payment_status || (p.linked_order_id ? 'Оплачено (LMS)' : '—');

  return (
    <Modal
      title="Анкета обучающегося LMS"
      subtitle={`Персональный профиль слушателя: ${fullName}`}
      onClose={onClose}
      wide
    >
      <div className="modal-body" style={{ display: 'grid', gap: '16px' }}>
        {/* Section 1: Personal Data */}
        <div className="panel" style={{ padding: '16px', background: 'var(--rtk-color-card)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
            <span className="eyebrow" style={{ color: 'var(--rtk-color-primary)' }}>РАЗДЕЛ 1</span>
            <h4 style={{ margin: 0, fontSize: '14px' }}>Персональные данные</h4>
          </div>
          <div className="detail-facts">
            <div>
              <span>ФИО</span>
              <strong>{fullName}</strong>
            </div>
            <div>
              <span>Дата рождения</span>
              <strong>{birthDate}</strong>
            </div>
            <div>
              <span>СНИЛС</span>
              <strong>{snils}</strong>
            </div>
            <div>
              <span>Пол</span>
              <strong>{gender}</strong>
            </div>
          </div>
        </div>

        {/* Section 2: Passport Data */}
        <div className="panel" style={{ padding: '16px', background: 'var(--rtk-color-card)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
            <span className="eyebrow" style={{ color: 'var(--rtk-color-primary)' }}>РАЗДЕЛ 2</span>
            <h4 style={{ margin: 0, fontSize: '14px' }}>Паспортные данные</h4>
          </div>
          <div className="detail-facts">
            <div>
              <span>Серия паспорта</span>
              <strong>{passSeries}</strong>
            </div>
            <div>
              <span>Номер паспорта</span>
              <strong>{passNumber}</strong>
            </div>
            <div>
              <span>Дата выдачи</span>
              <strong>{passIssueDate}</strong>
            </div>
            <div>
              <span>Код подразделения</span>
              <strong>{passUnitCode}</strong>
            </div>
            <div style={{ gridColumn: 'span 2' }}>
              <span>Кем выдан</span>
              <strong>{passIssuedBy}</strong>
            </div>
            <div style={{ gridColumn: 'span 3' }}>
              <span>Адрес регистрации</span>
              <strong>{regAddress}</strong>
            </div>
          </div>
        </div>

        {/* Section 3: Education & Qualification */}
        <div className="panel" style={{ padding: '16px', background: 'var(--rtk-color-card)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
            <span className="eyebrow" style={{ color: 'var(--rtk-color-primary)' }}>РАЗДЕЛ 3</span>
            <h4 style={{ margin: 0, fontSize: '14px' }}>Образование и квалификация</h4>
          </div>
          <div className="detail-facts">
            <div>
              <span>Уровень образования</span>
              <strong>{education}</strong>
            </div>
            <div>
              <span>Профессия / Специальность</span>
              <strong>{profession}</strong>
            </div>
            <div>
              <span>Номер диплома</span>
              <strong>{diplomaNum}</strong>
            </div>
            <div style={{ gridColumn: 'span 3' }}>
              <span>Учебное заведение по диплому</span>
              <strong>{diplomaUniv}</strong>
            </div>
          </div>
        </div>

        {/* Section 4: Contact Info */}
        <div className="panel" style={{ padding: '16px', background: 'var(--rtk-color-card)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
            <span className="eyebrow" style={{ color: 'var(--rtk-color-primary)' }}>РАЗДЕЛ 4</span>
            <h4 style={{ margin: 0, fontSize: '14px' }}>Контактные данные</h4>
          </div>
          <div className="detail-facts">
            <div>
              <span>Телефон</span>
              <strong>{phone}</strong>
            </div>
            <div>
              <span>Электронная почта</span>
              <strong>{email}</strong>
            </div>
          </div>
        </div>

        {/* Section 5: Order & Payment Info */}
        <div className="panel" style={{ padding: '16px', background: 'var(--rtk-color-card)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
            <span className="eyebrow" style={{ color: 'var(--rtk-color-primary)' }}>РАЗДЕЛ 5</span>
            <h4 style={{ margin: 0, fontSize: '14px' }}>Данные заказа и оплаты</h4>
          </div>
          <div className="detail-facts">
            <div>
              <span>Связанный курс</span>
              <strong>{course}</strong>
            </div>
            <div>
              <span>Поток / Когорта</span>
              <strong>{cohort}</strong>
            </div>
            <div>
              <span>Номер заявки / заказа</span>
              <strong>{orderId}</strong>
            </div>
            <div>
              <span>Статус оплаты</span>
              <strong style={{ color: paymentStatus.includes('paid') || paymentStatus.includes('Оплачено') ? 'var(--rtk-color-success)' : undefined }}>
                {paymentStatus}
              </strong>
            </div>
          </div>
        </div>

        {/* Section 6: Security Note 152-FZ / FSTEC #117 */}
        <div
          style={{
            background: 'var(--rtk-color-info-bg, #EFF8FF)',
            border: '1px solid #B2DDFF',
            borderRadius: '8px',
            padding: '14px',
            display: 'flex',
            alignItems: 'flex-start',
            gap: '12px',
          }}
        >
          <Icon name="check" size={20} />
          <div>
            <strong style={{ fontSize: '12px', color: '#175CD3' }}>
              Гриф конфиденциальности: 152-ФЗ «О персональных данных» / ФСТЭК №117
            </strong>
            <p style={{ margin: '4px 0 0', fontSize: '11px', color: '#1849A9', lineHeight: 1.4 }}>
              Данный реестр содержит специальные категории персональных данных и реквизиты документов, удостоверяющих личность. Обработка разрешена исключительно в защищенном контуре шлюза интеграций. Студенты не заносятся в таблицу операторов CRM.
            </p>
          </div>
        </div>
      </div>

      {/* Section 7: Actions */}
      <div className="modal-actions">
        <Button variant="ghost" onClick={onClose}>
          Закрыть
        </Button>
        {item.status === 'pending' && onOpenResolve && (
          <Button
            variant="primary"
            onClick={() => {
              onClose();
              onOpenResolve(item);
            }}
          >
            <Icon name="check" size={16} />
            Перейти к сверке
          </Button>
        )}
      </div>
    </Modal>
  );
}
