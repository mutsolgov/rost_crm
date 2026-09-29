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

function safeIso(val?: string, fallbackDaysAgo = 0): string {
  if (!val) {
    const d = new Date();
    if (fallbackDaysAgo > 0) d.setDate(d.getDate() - fallbackDaysAgo);
    return d.toISOString();
  }
  try {
    const d = new Date(val);
    if (isNaN(d.getTime())) {
      const fallback = new Date();
      if (fallbackDaysAgo > 0) fallback.setDate(fallback.getDate() - fallbackDaysAgo);
      return fallback.toISOString();
    }
    return d.toISOString();
  } catch {
    return new Date().toISOString();
  }
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


export interface ReportColumnDef {
  key: string;
  label: string;
}

export const SNAPSHOT_COLUMNS: ReportColumnDef[] = [
  { key: 'title', label: 'Взаимодействие' },
  { key: 'organization_name', label: 'Организация' },
  { key: 'program_name', label: 'Программа' },
  { key: 'product_name', label: 'Продукт' },
  { key: 'state_name', label: 'Этап' },
  { key: 'owner_name', label: 'Ответственный' },
  { key: 'cycle_label', label: 'Метка цикла' },
];

export const ACTIVITY_COLUMNS: ReportColumnDef[] = [
  { key: 'effective_at', label: 'Время события' },
  { key: 'title', label: 'Взаимодействие' },
  { key: 'organization_name', label: 'Организация' },
  { key: 'from_state_name', label: 'Исходный этап' },
  { key: 'to_state_name', label: 'Целевой этап' },
  { key: 'owner_at_event_name', label: 'Ответственный на момент перехода' },
  { key: 'actor_name', label: 'Инициатор' },
];

export const CREATED_COLUMNS: ReportColumnDef[] = [
  { key: 'created_at', label: 'Дата создания' },
  { key: 'title', label: 'Взаимодействие' },
  { key: 'organization_name', label: 'Организация' },
  { key: 'program_name', label: 'Программа' },
  { key: 'product_name', label: 'Продукт' },
  { key: 'owner_name', label: 'Ответственный' },
];

function ColumnSelector({
  columns,
  selected,
  onToggle,
  onSelectAll,
}: {
  columns: ReportColumnDef[];
  selected: string[];
  onToggle: (key: string) => void;
  onSelectAll: () => void;
}) {
  return (
    <div style={{ marginTop: '16px', paddingTop: '14px', borderTop: '1px solid var(--rtk-color-border)' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px', flexWrap: 'wrap', gap: '8px' }}>
        <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--rtk-color-text)' }}>
          Отображаемые колонки ({selected.length} из {columns.length}):
        </span>
        <button
          type="button"
          onClick={onSelectAll}
          style={{ fontSize: '12px', color: 'var(--rtk-color-primary)', background: 'none', border: 'none', cursor: 'pointer', padding: 0, fontWeight: 500 }}
        >
          Выбрать все
        </button>
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px 16px' }}>
        {columns.map(col => (
          <label key={col.key} style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '12px', cursor: 'pointer', userSelect: 'none' }}>
            <input
              type="checkbox"
              checked={selected.includes(col.key)}
              onChange={() => onToggle(col.key)}
            />
            <span>{col.label}</span>
          </label>
        ))}
      </div>
    </div>
  );
}

interface SnapshotFilters {
  asOf: string;
  organizationId: string;
  programId: string;
  ownerId: string;
  selectedColumns: string[];
}

interface ActivityFilters {
  fromDate: string;
  toDate: string;
  organizationId: string;
  programId: string;
  historicalOwnerId: string;
  selectedColumns: string[];
}

interface CreatedFilters {
  fromDate: string;
  toDate: string;
  organizationId: string;
  programId: string;
  ownerId: string;
  selectedColumns: string[];
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

  const [snapshotFilters, setSnapshotFilters] = useState<SnapshotFilters>({
    asOf: isoNow(),
    organizationId: '',
    programId: '',
    ownerId: '',
    selectedColumns: SNAPSHOT_COLUMNS.map(c => c.key),
  });

  const [activityFilters, setActivityFilters] = useState<ActivityFilters>({
    fromDate: isoDaysAgo(30),
    toDate: isoNow(),
    organizationId: '',
    programId: '',
    historicalOwnerId: '',
    selectedColumns: ACTIVITY_COLUMNS.map(c => c.key),
  });

  const [createdFilters, setCreatedFilters] = useState<CreatedFilters>({
    fromDate: isoDaysAgo(30),
    toDate: isoNow(),
    organizationId: '',
    programId: '',
    ownerId: '',
    selectedColumns: CREATED_COLUMNS.map(c => c.key),
  });

  const [snapshotResult, setSnapshotResult] = useState<Snapshot | null>(null);
  const [activityResult, setActivityResult] = useState<ActivityResult | null>(null);
  const [createdResult, setCreatedResult] = useState<CreatedResult | null>(null);

  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState('');

  const getSnapshotPayload = (): SnapshotQuery => ({
    as_of: safeIso(snapshotFilters.asOf),
    knowledge_cutoff: new Date().toISOString(),
    as_of_inclusive: true,
    organization_ids: snapshotFilters.organizationId ? [snapshotFilters.organizationId] : [],
    program_ids: snapshotFilters.programId ? [snapshotFilters.programId] : [],
    product_ids: [],
    owner_ids: snapshotFilters.ownerId ? [snapshotFilters.ownerId] : [],
    selected_columns: snapshotFilters.selectedColumns,
  });

  const getActivityPayload = (): ActivityQuery => ({
    from_date: safeIso(activityFilters.fromDate, 30),
    to_date: safeIso(activityFilters.toDate),
    knowledge_cutoff: new Date().toISOString(),
    organization_ids: activityFilters.organizationId ? [activityFilters.organizationId] : [],
    historical_owner_id: activityFilters.historicalOwnerId || undefined,
    program_ids: activityFilters.programId ? [activityFilters.programId] : [],
    product_ids: [],
    owner_ids: [],
    selected_columns: activityFilters.selectedColumns,
  });

  const getCreatedPayload = (): CreatedQuery => ({
    from_date: safeIso(createdFilters.fromDate, 30),
    to_date: safeIso(createdFilters.toDate),
    knowledge_cutoff: new Date().toISOString(),
    organization_ids: createdFilters.organizationId ? [createdFilters.organizationId] : [],
    owner_ids: createdFilters.ownerId ? [createdFilters.ownerId] : [],
    program_ids: createdFilters.programId ? [createdFilters.programId] : [],
    product_ids: [],
    selected_columns: createdFilters.selectedColumns,
  });

  async function buildReport() {
    setLoading(true);
    setError(null);
    setNotice('');

    try {
      if (mode === 'snapshot') {
        const q = getSnapshotPayload();
        const data = await api.post<Snapshot>('/reports/snapshot', q);
        setSnapshotResult(data);
      } else if (mode === 'activity') {
        const q = getActivityPayload();
        const data = await api.post<ActivityResult>('/reports/activity', q);
        setActivityResult(data);
      } else if (mode === 'created') {
        const q = getCreatedPayload();
        const data = await api.post<CreatedResult>('/reports/created', q);
        setCreatedResult(data);
      }
    } catch (problem) {
      setError(problem);
    } finally {
      setLoading(false);
    }
  }

  async function handleExport(format: 'xlsx' | 'pdf' | 'csv' | 'json') {
    setExporting(true);
    setError(null);
    try {
      if (mode === 'snapshot') {
        const payload = getSnapshotPayload();
        await api.download('/reports/snapshot/export', payload, format, `snapshot-report.${format}`);
      } else if (mode === 'activity') {
        const payload = getActivityPayload();
        await api.download('/reports/activity/export', payload, format, `activity-report.${format}`);
      } else if (mode === 'created') {
        const payload = getCreatedPayload();
        await api.download('/reports/created/export', payload, format, `created-report.${format}`);
      }
      setNotice(`Отчёт (${format.toUpperCase()}) успешно сформирован и загружен`);
    } catch (problem) {
      setError(problem);
    } finally {
      setExporting(false);
    }
  }

  function toggleColumn(reportMode: ReportMode, key: string) {
    if (reportMode === 'snapshot') {
      setSnapshotFilters(prev => {
        const exists = prev.selectedColumns.includes(key);
        const next = exists ? prev.selectedColumns.filter(k => k !== key) : [...prev.selectedColumns, key];
        return { ...prev, selectedColumns: next.length > 0 ? next : [key] };
      });
    } else if (reportMode === 'activity') {
      setActivityFilters(prev => {
        const exists = prev.selectedColumns.includes(key);
        const next = exists ? prev.selectedColumns.filter(k => k !== key) : [...prev.selectedColumns, key];
        return { ...prev, selectedColumns: next.length > 0 ? next : [key] };
      });
    } else if (reportMode === 'created') {
      setCreatedFilters(prev => {
        const exists = prev.selectedColumns.includes(key);
        const next = exists ? prev.selectedColumns.filter(k => k !== key) : [...prev.selectedColumns, key];
        return { ...prev, selectedColumns: next.length > 0 ? next : [key] };
      });
    }
  }

  function selectAllColumns(reportMode: ReportMode) {
    if (reportMode === 'snapshot') {
      setSnapshotFilters(prev => ({ ...prev, selectedColumns: SNAPSHOT_COLUMNS.map(c => c.key) }));
    } else if (reportMode === 'activity') {
      setActivityFilters(prev => ({ ...prev, selectedColumns: ACTIVITY_COLUMNS.map(c => c.key) }));
    } else if (reportMode === 'created') {
      setCreatedFilters(prev => ({ ...prev, selectedColumns: CREATED_COLUMNS.map(c => c.key) }));
    }
  }

  const countsByState: Record<string, number> =
    mode === 'snapshot'
      ? snapshotResult?.totals.counts_by_state || {}
      : mode === 'activity'
      ? activityResult?.totals.counts_by_to_state || {}
      : createdResult?.totals?.counts_by_state || {};

  const hasResult =
    (mode === 'snapshot' && !!snapshotResult) ||
    (mode === 'activity' && !!activityResult) ||
    (mode === 'created' && !!createdResult);

  const isSnapCol = (key: string) => snapshotFilters.selectedColumns.includes(key);
  const isActCol = (key: string) => activityFilters.selectedColumns.includes(key);
  const isCreatedCol = (key: string) => createdFilters.selectedColumns.includes(key);

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
            <>
              <div className="filter-grid">
                <label className="field">
                  <span>Состояние на дату и время</span>
                  <input
                    type="datetime-local"
                    value={snapshotFilters.asOf}
                    onChange={e => setSnapshotFilters(prev => ({ ...prev, asOf: e.target.value }))}
                  />
                </label>
                <label className="field">
                  <span>Организация</span>
                  <select
                    value={snapshotFilters.organizationId}
                    onChange={e => setSnapshotFilters(prev => ({ ...prev, organizationId: e.target.value }))}
                  >
                    <option value="">Все доступные организации</option>
                    {catalogs.organizations.map(item => (
                      <option key={item.id} value={item.id}>{item.name}</option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span>Программа</span>
                  <select
                    value={snapshotFilters.programId}
                    onChange={e => setSnapshotFilters(prev => ({ ...prev, programId: e.target.value }))}
                  >
                    <option value="">Все программы</option>
                    {catalogs.programs.map(item => (
                      <option key={item.id} value={item.id}>{item.name}</option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span>Ответственный</span>
                  <select
                    value={snapshotFilters.ownerId}
                    onChange={e => setSnapshotFilters(prev => ({ ...prev, ownerId: e.target.value }))}
                  >
                    <option value="">Все ответственные</option>
                    {catalogs.owners.map(item => (
                      <option key={item.id} value={item.id}>{item.name}</option>
                    ))}
                  </select>
                </label>
              </div>
              <ColumnSelector
                columns={SNAPSHOT_COLUMNS}
                selected={snapshotFilters.selectedColumns}
                onToggle={(key) => toggleColumn('snapshot', key)}
                onSelectAll={() => selectAllColumns('snapshot')}
              />
            </>
          )}

          {mode === 'activity' && (
            <>
              <div className="filter-grid">
                <label className="field">
                  <span>Интервал «С даты»</span>
                  <input
                    type="datetime-local"
                    value={activityFilters.fromDate}
                    onChange={e => setActivityFilters(prev => ({ ...prev, fromDate: e.target.value }))}
                  />
                </label>
                <label className="field">
                  <span>Интервал «По дату»</span>
                  <input
                    type="datetime-local"
                    value={activityFilters.toDate}
                    onChange={e => setActivityFilters(prev => ({ ...prev, toDate: e.target.value }))}
                  />
                </label>
                <label className="field">
                  <span>Организация</span>
                  <select
                    value={activityFilters.organizationId}
                    onChange={e => setActivityFilters(prev => ({ ...prev, organizationId: e.target.value }))}
                  >
                    <option value="">Все доступные организации</option>
                    {catalogs.organizations.map(item => (
                      <option key={item.id} value={item.id}>{item.name}</option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span>Программа</span>
                  <select
                    value={activityFilters.programId}
                    onChange={e => setActivityFilters(prev => ({ ...prev, programId: e.target.value }))}
                  >
                    <option value="">Все программы</option>
                    {catalogs.programs.map(item => (
                      <option key={item.id} value={item.id}>{item.name}</option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span>Исторический ответственный</span>
                  <select
                    value={activityFilters.historicalOwnerId}
                    onChange={e => setActivityFilters(prev => ({ ...prev, historicalOwnerId: e.target.value }))}
                  >
                    <option value="">Все ответственные на момент перехода</option>
                    {catalogs.owners.map(item => (
                      <option key={item.id} value={item.id}>{item.name}</option>
                    ))}
                  </select>
                </label>
              </div>
              <ColumnSelector
                columns={ACTIVITY_COLUMNS}
                selected={activityFilters.selectedColumns}
                onToggle={(key) => toggleColumn('activity', key)}
                onSelectAll={() => selectAllColumns('activity')}
              />
            </>
          )}

          {mode === 'created' && (
            <>
              <div className="filter-grid">
                <label className="field">
                  <span>Создано «С даты»</span>
                  <input
                    type="datetime-local"
                    value={createdFilters.fromDate}
                    onChange={e => setCreatedFilters(prev => ({ ...prev, fromDate: e.target.value }))}
                  />
                </label>
                <label className="field">
                  <span>Создано «По дату»</span>
                  <input
                    type="datetime-local"
                    value={createdFilters.toDate}
                    onChange={e => setCreatedFilters(prev => ({ ...prev, toDate: e.target.value }))}
                  />
                </label>
                <label className="field">
                  <span>Организация</span>
                  <select
                    value={createdFilters.organizationId}
                    onChange={e => setCreatedFilters(prev => ({ ...prev, organizationId: e.target.value }))}
                  >
                    <option value="">Все доступные организации</option>
                    {catalogs.organizations.map(item => (
                      <option key={item.id} value={item.id}>{item.name}</option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span>Программа</span>
                  <select
                    value={createdFilters.programId}
                    onChange={e => setCreatedFilters(prev => ({ ...prev, programId: e.target.value }))}
                  >
                    <option value="">Все программы</option>
                    {catalogs.programs.map(item => (
                      <option key={item.id} value={item.id}>{item.name}</option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span>Ответственный</span>
                  <select
                    value={createdFilters.ownerId}
                    onChange={e => setCreatedFilters(prev => ({ ...prev, ownerId: e.target.value }))}
                  >
                    <option value="">Все ответственные</option>
                    {catalogs.owners.map(item => (
                      <option key={item.id} value={item.id}>{item.name}</option>
                    ))}
                  </select>
                </label>
              </div>
              <ColumnSelector
                columns={CREATED_COLUMNS}
                selected={createdFilters.selectedColumns}
                onToggle={(key) => toggleColumn('created', key)}
                onSelectAll={() => selectAllColumns('created')}
              />
            </>
          )}

          <p className="form-hint" style={{ marginTop: '12px' }}>
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
                onClick={() => handleExport('csv')}
                title="Скачать отчёт в формате CSV с поддержкой Excel (UTF-8 BOM)"
              >
                <Icon name="download" size={16} />Скачать CSV
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
                <div><strong>{Object.values(snapshotResult.totals.counts_by_state || {}).filter(c => c > 0).length}</strong><span>активных этапов</span></div>
              </>
            )}
            {mode === 'activity' && activityResult && (
              <>
                <div><strong>{activityResult.totals.transitions}</strong><span>совершённых переходов</span></div>
                <div><strong>{activityResult.rows.length}</strong><span>записей аудита</span></div>
                <div><strong>{Object.values(activityResult.totals.counts_by_to_state || {}).filter(c => c > 0).length}</strong><span>задействованных этапов</span></div>
              </>
            )}
            {mode === 'created' && createdResult && (
              <>
                <div><strong>{createdResult?.totals?.interactions ?? createdResult?.rows?.length ?? 0}</strong><span>созданных карточек</span></div>
                <div><strong>{createdResult?.totals?.organizations ?? 0}</strong><span>организаций</span></div>
                <div><strong>{Object.values(createdResult?.totals?.counts_by_state || {}).filter(c => c > 0).length}</strong><span>этапов</span></div>
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
                      {isSnapCol('title') && <th>Взаимодействие</th>}
                      {isSnapCol('organization_name') && <th>Организация</th>}
                      {isSnapCol('program_name') && <th>Программа</th>}
                      {isSnapCol('product_name') && <th>Продукт</th>}
                      {isSnapCol('state_name') && <th>Текущий этап</th>}
                      {isSnapCol('owner_name') && <th>Ответственный</th>}
                      {isSnapCol('cycle_label') && <th>Метка цикла</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {snapshotResult.rows.map(row => (
                      <tr key={row.interaction_id}>
                        {isSnapCol('title') && <td><strong>{row.title}</strong></td>}
                        {isSnapCol('organization_name') && <td>{row.organization_name}</td>}
                        {isSnapCol('program_name') && <td>{row.program_name || '—'}</td>}
                        {isSnapCol('product_name') && <td>{row.product_name || '—'}</td>}
                        {isSnapCol('state_name') && <td><StageBadge code={row.state} name={row.state_name} /></td>}
                        {isSnapCol('owner_name') && <td>{row.owner_name}</td>}
                        {isSnapCol('cycle_label') && <td>{row.cycle_label || '—'}</td>}
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
                      {isActCol('effective_at') && <th>Время события</th>}
                      {isActCol('title') && <th>Взаимодействие</th>}
                      {isActCol('organization_name') && <th>Организация</th>}
                      {isActCol('from_state_name') && <th>Исходный этап</th>}
                      {isActCol('to_state_name') && <th>Целевой этап</th>}
                      {isActCol('owner_at_event_name') && <th>Ответственный на момент перехода</th>}
                      {isActCol('actor_name') && <th>Инициатор</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {activityResult.rows.map(row => (
                      <tr key={row.event_id}>
                        {isActCol('effective_at') && <td>{formatDate(row.effective_at)}</td>}
                        {isActCol('title') && <td><strong>{row.title || '—'}</strong></td>}
                        {isActCol('organization_name') && <td>{row.organization_name || '—'}</td>}
                        {isActCol('from_state_name') && (
                          <td>
                            <StageBadge code={row.from_state} name={row.from_state_name || row.from_state} />
                          </td>
                        )}
                        {isActCol('to_state_name') && (
                          <td>
                            <StageBadge code={row.to_state} name={row.to_state_name || row.to_state} />
                          </td>
                        )}
                        {isActCol('owner_at_event_name') && <td><strong>{row.owner_at_event_name || row.owner_at_event || '—'}</strong></td>}
                        {isActCol('actor_name') && <td>{row.actor_name || '—'}</td>}
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
                      {isCreatedCol('created_at') && <th>Дата создания</th>}
                      {isCreatedCol('title') && <th>Взаимодействие</th>}
                      {isCreatedCol('organization_name') && <th>Организация</th>}
                      {isCreatedCol('program_name') && <th>Программа</th>}
                      {isCreatedCol('product_name') && <th>Продукт</th>}
                      {isCreatedCol('owner_name') && <th>Ответственный</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {createdResult.rows.map(row => (
                      <tr key={row.interaction_id}>
                        {isCreatedCol('created_at') && <td>{formatDate(row.created_at)}</td>}
                        {isCreatedCol('title') && <td><strong>{row.title}</strong></td>}
                        {isCreatedCol('organization_name') && <td>{row.organization_name}</td>}
                        {isCreatedCol('program_name') && <td>{row.program_name || '—'}</td>}
                        {isCreatedCol('product_name') && <td>{row.product_name || '—'}</td>}
                        {isCreatedCol('owner_name') && <td>{row.owner_name}</td>}
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
          <p>Нажмите «Построить отчёт», чтобы рассчитать данные и открыть экспорт в XLSX, PDF, CSV и JSON.</p>
        </div>
      )}

      {loading && <Loading label="Рассчитываем аналитику по процессам…" />}
    </>
  );
}

