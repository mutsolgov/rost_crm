import { useState } from 'react';
import type { ApiClient } from '../api';
import { Button, ErrorAlert, Icon, Loading, PageHeader, StageBadge, formatDate } from '../ui';
import type {
  ActivityQuery,
  ActivityResult,
  Catalogs,
  CreatedQuery,
  CreatedResult,
  Snapshot,
  SnapshotQuery,
  Workflow,
} from '../types';

function isoNow() {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}

function isoDaysAgo(days: number) {
  const d = new Date();
  d.setDate(d.getDate() - days);
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}

type ReportMode = 'snapshot' | 'activity' | 'created';

export function StageFunnelDiagram({
  countsByState,
  states,
  title = 'Распределение взаимодействий по этапам воронки',
}: {
  countsByState: Record<string, number>;
  states: { code: string; name: string }[];
  title?: string;
}) {
  const stagesWithCounts = states.map((s, idx) => {
    const count = countsByState[s.code] || 0;
    return { ...s, count, index: idx };
  });

  const total = Object.values(countsByState).reduce((a, b) => a + b, 0);
  const maxCount = Math.max(1, ...stagesWithCounts.map(s => s.count));

  const barHeight = 26;
  const gap = 10;
  const chartHeight = Math.max(220, stagesWithCounts.length * (barHeight + gap) + 30);
  const maxBarWidth = 400;

  return (
    <div className="funnel-container">
      <div className="funnel-heading">
        <div>
          <span className="eyebrow">АНАЛИТИКА ВОРОНКИ</span>
          <h3 style={{ margin: '4px 0 0', fontSize: '15px' }}>{title}</h3>
        </div>
        <span className="quiet-badge">Всего учтено: {total}</span>
      </div>

      <svg
        viewBox={`0 0 740 ${chartHeight}`}
        className="funnel-svg"
        style={{ width: '100%', maxHeight: `${chartHeight}px` }}
      >
        <defs>
          <linearGradient id="funnelBarGrad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#7700FF" />
            <stop offset="100%" stopColor="#FF4F12" />
          </linearGradient>
        </defs>

        {stagesWithCounts.map((stage, i) => {
          const y = 15 + i * (barHeight + gap);
          const barWidth = stage.count > 0 ? Math.max(12, Math.round((stage.count / maxCount) * maxBarWidth)) : 0;
          const pctOfTotal = total > 0 ? Math.round((stage.count / total) * 100) : 0;
          const prevCount = i > 0 ? stagesWithCounts[i - 1].count : stage.count;
          const dropOff = (i > 0 && prevCount > stage.count) ? prevCount - stage.count : 0;

          const isTerminal = stage.code === 'completed' || stage.code === 'cancelled';
          const barColor = stage.code === 'completed'
            ? '#039855'
            : stage.code === 'cancelled'
            ? '#D92D20'
            : i % 2 === 0 ? '#7700FF' : '#9233EA';

          return (
            <g key={stage.code}>
              <text
                x="200"
                y={y + 17}
                textAnchor="end"
                fontSize="11"
                fontWeight="600"
                fill="var(--rtk-color-text)"
                fontFamily="inherit"
              >
                {stage.name.length > 25 ? stage.name.slice(0, 24) + '…' : stage.name}
              </text>

              <rect
                x="215"
                y={y}
                width={maxBarWidth}
                height={barHeight}
                rx="6"
                fill="#F0F2F6"
              />

              {barWidth > 0 && (
                <rect
                  x="215"
                  y={y}
                  width={barWidth}
                  height={barHeight}
                  rx="6"
                  fill={barColor}
                  opacity={0.92}
                />
              )}

              <text
                x={215 + Math.max(barWidth + 8, 12)}
                y={y + 17}
                fontSize="11"
                fontWeight="700"
                fill={barWidth > 320 ? '#FFFFFF' : 'var(--rtk-color-text)'}
                fontFamily="inherit"
              >
                {stage.count} {stage.count > 0 && `(${pctOfTotal}%)`}
              </text>

              {dropOff > 0 && !isTerminal && (
                <text
                  x="680"
                  y={y + 17}
                  fontSize="10"
                  fontWeight="600"
                  fill="#FF4F12"
                  textAnchor="end"
                  fontFamily="inherit"
                >
                  ↓ -{dropOff}
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}


export function Reports({
  api,
  catalogs,
  workflow,
}: {
  api: ApiClient;
  catalogs: Catalogs;
  workflow: Workflow;
}) {
  const [mode, setMode] = useState<ReportMode>('snapshot');

  const [asOf, setAsOf] = useState(isoNow());
  const [fromDate, setFromDate] = useState(isoDaysAgo(30));
  const [toDate, setToDate] = useState(isoNow());
  const [organizationId, setOrganizationId] = useState('');
  const [ownerId, setOwnerId] = useState('');
  const [historicalOwnerId, setHistoricalOwnerId] = useState('');

  const [snapshotResult, setSnapshotResult] = useState<Snapshot | null>(null);
  const [activityResult, setActivityResult] = useState<ActivityResult | null>(null);
  const [createdResult, setCreatedResult] = useState<CreatedResult | null>(null);

  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState('');

  const getSnapshotQuery = (): SnapshotQuery => ({
    as_of: new Date(asOf).toISOString(),
    knowledge_cutoff: new Date().toISOString(),
    as_of_inclusive: true,
    organization_ids: organizationId ? [organizationId] : [],
    program_ids: [],
    product_ids: [],
    owner_ids: ownerId ? [ownerId] : [],
  });

  const getActivityQuery = (): ActivityQuery => ({
    from_date: new Date(fromDate).toISOString(),
    to_date: new Date(toDate).toISOString(),
    knowledge_cutoff: new Date().toISOString(),
    organization_ids: organizationId ? [organizationId] : [],
    historical_owner_id: historicalOwnerId || undefined,
    program_ids: [],
    product_ids: [],
    owner_ids: [],
  });

  const getCreatedQuery = (): CreatedQuery => ({
    from_date: new Date(fromDate).toISOString(),
    to_date: new Date(toDate).toISOString(),
    knowledge_cutoff: new Date().toISOString(),
    organization_ids: organizationId ? [organizationId] : [],
    owner_ids: ownerId ? [ownerId] : [],
    program_ids: [],
    product_ids: [],
  });

  async function buildReport() {
    setLoading(true);
    setError(null);
    setNotice('');

    try {
      if (mode === 'snapshot') {
        const data = await api.post<Snapshot>('/reports/snapshot', getSnapshotQuery());
        setSnapshotResult(data);
      } else if (mode === 'activity') {
        const data = await api.post<ActivityResult>('/reports/activity', getActivityQuery());
        setActivityResult(data);
      } else if (mode === 'created') {
        const data = await api.post<CreatedResult>('/reports/created', getCreatedQuery());
        setCreatedResult(data);
      }
    } catch (problem) {
      setError(problem);
    } finally {
      setLoading(false);
    }
  }

  async function handleExport(format: 'xlsx' | 'pdf' | 'json') {
    setExporting(true);
    setError(null);
    try {
      if (mode === 'snapshot') {
        await api.download('/reports/snapshot/export', getSnapshotQuery(), format, `snapshot-report.${format}`);
      } else if (mode === 'activity') {
        await api.download('/reports/activity/export', getActivityQuery(), format, `activity-report.${format}`);
      } else if (mode === 'created') {
        await api.download('/reports/created/export', getCreatedQuery(), format, `created-report.${format}`);
      }
      setNotice(`Отчёт (${format.toUpperCase()}) успешно сформирован и загружен`);
    } catch (problem) {
      setError(problem);
    } finally {
      setExporting(false);
    }
  }

  const countsByState: Record<string, number> =
    mode === 'snapshot'
      ? snapshotResult?.totals.counts_by_state || {}
      : mode === 'activity'
      ? activityResult?.totals.counts_by_to_state || {}
      : createdResult?.totals.counts_by_state || {};

  const hasResult =
    (mode === 'snapshot' && !!snapshotResult) ||
    (mode === 'activity' && !!activityResult) ||
    (mode === 'created' && !!createdResult);

  return (
    <>
      <PageHeader
        eyebrow="КОНТРОЛЬ И АНАЛИТИКА"
        title="Отчёты и аналитика"
        description="Формирование срезов, динамики переходов и аналитических выгрузок в XLSX, PDF и JSON."
        action={
          <Button onClick={buildReport} disabled={loading}>
            <Icon name="chart" size={17} />
            {loading ? 'Строим отчёт…' : 'Построить отчёт'}
          </Button>
        }
      />

      <section className="panel" style={{ padding: 0, marginBottom: '16px' }}>
        <div className="report-tabs">
          <button
            type="button"
            className={`report-tab-btn ${mode === 'snapshot' ? 'active' : ''}`}
            onClick={() => { setMode('snapshot'); setError(null); }}
          >
            Срез на дату (Snapshot)
          </button>
          <button
            type="button"
            className={`report-tab-btn ${mode === 'activity' ? 'active' : ''}`}
            onClick={() => { setMode('activity'); setError(null); }}
          >
            Динамика переходов (Activity)
          </button>
          <button
            type="button"
            className={`report-tab-btn ${mode === 'created' ? 'active' : ''}`}
            onClick={() => { setMode('created'); setError(null); }}
          >
            Созданные карточки (Created)
          </button>
        </div>

        <div style={{ padding: '20px 24px' }}>
          {mode === 'snapshot' && (
            <div className="filter-grid">
              <label className="field">
                <span>Состояние на дату и время</span>
                <input
                  type="datetime-local"
                  value={asOf}
                  onChange={e => setAsOf(e.target.value)}
                />
              </label>
              <label className="field">
                <span>Организация</span>
                <select value={organizationId} onChange={e => setOrganizationId(e.target.value)}>
                  <option value="">Все доступные организации</option>
                  {catalogs.organizations.map(item => (
                    <option key={item.id} value={item.id}>{item.name}</option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>Ответственный</span>
                <select value={ownerId} onChange={e => setOwnerId(e.target.value)}>
                  <option value="">Все ответственные</option>
                  {catalogs.owners.map(item => (
                    <option key={item.id} value={item.id}>{item.name}</option>
                  ))}
                </select>
              </label>
            </div>
          )}

          {mode === 'activity' && (
            <div className="filter-grid">
              <label className="field">
                <span>Интервал «С даты»</span>
                <input
                  type="datetime-local"
                  value={fromDate}
                  onChange={e => setFromDate(e.target.value)}
                />
              </label>
              <label className="field">
                <span>Интервал «По дату»</span>
                <input
                  type="datetime-local"
                  value={toDate}
                  onChange={e => setToDate(e.target.value)}
                />
              </label>
              <label className="field">
                <span>Исторический ответственный</span>
                <select value={historicalOwnerId} onChange={e => setHistoricalOwnerId(e.target.value)}>
                  <option value="">Все ответственные на момент перехода</option>
                  {catalogs.owners.map(item => (
                    <option key={item.id} value={item.id}>{item.name}</option>
                  ))}
                </select>
              </label>
            </div>
          )}

          {mode === 'created' && (
            <div className="filter-grid">
              <label className="field">
                <span>Создано «С даты»</span>
                <input
                  type="datetime-local"
                  value={fromDate}
                  onChange={e => setFromDate(e.target.value)}
                />
              </label>
              <label className="field">
                <span>Создано «По дату»</span>
                <input
                  type="datetime-local"
                  value={toDate}
                  onChange={e => setToDate(e.target.value)}
                />
              </label>
              <label className="field">
                <span>Ответственный</span>
                <select value={ownerId} onChange={e => setOwnerId(e.target.value)}>
                  <option value="">Все ответственные</option>
                  {catalogs.owners.map(item => (
                    <option key={item.id} value={item.id}>{item.name}</option>
                  ))}
                </select>
              </label>
            </div>
          )}

          <p className="form-hint">
            {mode === 'snapshot' && 'Срез фиксирует состояние карточек и ответственных строго на выбранный момент времени.'}
            {mode === 'activity' && 'Динамика фиксирует все переходы и циклы за интервал с привязкой к историческому владельцу.'}
            {mode === 'created' && 'Отчёт фиксирует все новые карточки взаимодействий, зарегистрированные в выбранный период.'}
          </p>
        </div>
      </section>

      <ErrorAlert error={error} />
      {notice && (
        <div className="success-alert">
          <Icon name="check" size={18} />
          {notice}
        </div>
      )}

      {hasResult && (
        <section className="panel report-result" style={{ marginBottom: '20px' }}>
          <div className="panel-heading" style={{ flexWrap: 'wrap', gap: '14px' }}>
            <div>
              <span className="eyebrow">
                {mode === 'snapshot' && `СНИМОК СОСТОЯНИЯ · ${formatDate(snapshotResult!.as_of)}`}
                {mode === 'activity' && `ПЕРЕХОДЫ ЗА ПЕРИОД · ${formatDate(activityResult!.from_date)} — ${formatDate(activityResult!.to_date)}`}
                {mode === 'created' && `СОЗДАННЫЕ КАРТОЧКИ · ${formatDate(createdResult!.from_date)} — ${formatDate(createdResult!.to_date)}`}
              </span>
              <h2>Результат отчёта</h2>
            </div>

            <div className="export-toolbar">
              <Button
                variant="secondary"
                disabled={exporting}
                onClick={() => handleExport('xlsx')}
                title="Скачать отчёт в формате Microsoft Excel (OpenXML)"
              >
                <Icon name="download" size={16} />Скачать XLSX
              </Button>
              <Button
                variant="secondary"
                disabled={exporting}
                onClick={() => handleExport('pdf')}
                title="Скачать отчёт в формате векторного PDF с колонтитулами Ростелеком"
              >
                <Icon name="download" size={16} />Скачать PDF
              </Button>
              <Button
                variant="secondary"
                disabled={exporting}
                onClick={() => handleExport('json')}
                title="Скачать структурированные исходные данные в JSON"
              >
                <Icon name="download" size={16} />Скачать JSON
              </Button>
            </div>
          </div>

          <div className="report-metrics">
            {mode === 'snapshot' && snapshotResult && (
              <>
                <div><strong>{snapshotResult.totals.interactions}</strong><span>взаимодействий</span></div>
                <div><strong>{snapshotResult.totals.organizations}</strong><span>организаций</span></div>
                <div><strong>{Object.keys(snapshotResult.totals.counts_by_state).length}</strong><span>активных этапов</span></div>
              </>
            )}
            {mode === 'activity' && activityResult && (
              <>
                <div><strong>{activityResult.totals.transitions}</strong><span>совершённых переходов</span></div>
                <div><strong>{activityResult.rows.length}</strong><span>записей аудита</span></div>
                <div><strong>{Object.keys(activityResult.totals.counts_by_to_state).length}</strong><span>задействованных этапов</span></div>
              </>
            )}
            {mode === 'created' && createdResult && (
              <>
                <div><strong>{createdResult.totals.interactions}</strong><span>созданных карточек</span></div>
                <div><strong>{createdResult.totals.organizations}</strong><span>организаций</span></div>
                <div><strong>{Object.keys(createdResult.totals.counts_by_state).length}</strong><span>этапов</span></div>
              </>
            )}
          </div>

          <StageFunnelDiagram
            countsByState={countsByState}
            states={workflow.states}
            title={
              mode === 'snapshot'
                ? 'Распределение взаимодействий по этапам на дату среза'
                : mode === 'activity'
                ? 'Динамика переходов по целевым этапам процесса'
                : 'Распределение созданных взаимодействий по этапам'
            }
          />

          {mode === 'snapshot' && snapshotResult && (
            snapshotResult.rows.length ? (
              <div className="table-scroll" style={{ marginTop: '20px' }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Взаимодействие</th>
                      <th>Организация</th>
                      <th>Программа / Продукт</th>
                      <th>Текущий этап</th>
                      <th>Ответственный</th>
                    </tr>
                  </thead>
                  <tbody>
                    {snapshotResult.rows.map(row => (
                      <tr key={row.interaction_id}>
                        <td><strong>{row.title}</strong></td>
                        <td>{row.organization_name}</td>
                        <td>
                          {row.program_name || row.product_name ? (
                            <span>{row.program_name || '—'} / {row.product_name || '—'}</span>
                          ) : (
                            <span style={{ color: 'var(--rtk-color-caption)' }}>Не определены</span>
                          )}
                        </td>
                        <td><StageBadge code={row.state} name={row.state_name} /></td>
                        <td>{row.owner_name}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="empty-inline" style={{ marginTop: '20px' }}>
                На выбранный момент времени данных не обнаружено.
              </p>
            )
          )}

          {mode === 'activity' && activityResult && (
            activityResult.rows.length ? (
              <div className="table-scroll" style={{ marginTop: '20px' }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Время события</th>
                      <th>Взаимодействие</th>
                      <th>Организация</th>
                      <th>Переход этапа</th>
                      <th>Исторический ответственный</th>
                      <th>Инициатор</th>
                    </tr>
                  </thead>
                  <tbody>
                    {activityResult.rows.map(row => (
                      <tr key={row.event_id}>
                        <td>{formatDate(row.effective_at)}</td>
                        <td><strong>{row.title}</strong></td>
                        <td>{row.organization_name}</td>
                        <td>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <StageBadge code={row.from_state} name={row.from_state} />
                            <Icon name="arrow" size={14} />
                            <StageBadge code={row.to_state} name={row.to_state} />
                          </div>
                        </td>
                        <td><strong>{row.owner_at_event_name || row.owner_at_event}</strong></td>
                        <td>{row.actor_name}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="empty-inline" style={{ marginTop: '20px' }}>
                За выбранный период переходов не зафиксировано.
              </p>
            )
          )}

          {mode === 'created' && createdResult && (
            createdResult.rows.length ? (
              <div className="table-scroll" style={{ marginTop: '20px' }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Дата создания</th>
                      <th>Взаимодействие</th>
                      <th>Организация</th>
                      <th>Программа / Продукт</th>
                      <th>Этап</th>
                      <th>Ответственный</th>
                    </tr>
                  </thead>
                  <tbody>
                    {createdResult.rows.map(row => (
                      <tr key={row.interaction_id}>
                        <td>{formatDate(row.created_at)}</td>
                        <td><strong>{row.title}</strong></td>
                        <td>{row.organization_name}</td>
                        <td>
                          {row.program_name || row.product_name ? (
                            <span>{row.program_name || '—'} / {row.product_name || '—'}</span>
                          ) : (
                            <span style={{ color: 'var(--rtk-color-caption)' }}>Не определены</span>
                          )}
                        </td>
                        <td><StageBadge code={row.state} name={row.state_name} /></td>
                        <td>{row.owner_name}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="empty-inline" style={{ marginTop: '20px' }}>
                За выбранный период взаимодействий создано не было.
              </p>
            )
          )}
        </section>
      )}

      {!hasResult && !loading && (
        <div className="panel empty-report">
          <Icon name="chart" size={32} />
          <h2>Параметры отчёта настроены</h2>
          <p>Нажмите «Построить отчёт», чтобы рассчитать данные и открыть экспорт в XLSX, PDF и JSON.</p>
        </div>
      )}

      {loading && <Loading label="Рассчитываем аналитику по процессам…" />}
    </>
  );
}
