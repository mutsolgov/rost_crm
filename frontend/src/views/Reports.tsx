import { useState } from 'react';
import type { ApiClient } from '../api';
import { Button, ErrorAlert, Icon, Loading, PageHeader, StageBadge, formatDate } from '../ui';
import type { Catalogs, Snapshot, SnapshotQuery, Workflow } from '../types';

function isoNow() { return new Date().toISOString().slice(0, 16); }

export function Reports({ api, catalogs, workflow: _workflow }: { api: ApiClient; catalogs: Catalogs; workflow: Workflow }) {
  const [asOf, setAsOf] = useState(isoNow());
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [ownerId, setOwnerId] = useState('');
  const [organizationId, setOrganizationId] = useState('');
  const query = (): SnapshotQuery => ({ as_of: new Date(asOf).toISOString(), knowledge_cutoff: new Date().toISOString(), as_of_inclusive: true, organization_ids: organizationId ? [organizationId] : [], program_ids: [], product_ids: [], owner_ids: ownerId ? [ownerId] : [] });
  async function build() { setLoading(true); setError(null); try { setSnapshot(await api.post<Snapshot>('/reports/snapshot', query())); } catch (problem) { setError(problem); } finally { setLoading(false); } }
  return <><PageHeader eyebrow="КОНТРОЛЬ И АНАЛИТИКА" title="Отчёты" description="Состояние доступных взаимодействий на выбранный момент времени." action={<Button onClick={build} disabled={loading}><Icon name="chart" size={17}/>{loading ? 'Строим…' : 'Построить отчёт'}</Button>}/>
    <section className="panel report-controls"><div className="filter-grid"><label className="field"><span>Состояние на дату</span><input type="datetime-local" value={asOf} onChange={event => setAsOf(event.target.value)}/></label><label className="field"><span>Организация</span><select value={organizationId} onChange={event => setOrganizationId(event.target.value)}><option value="">Все доступные</option>{catalogs.organizations.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label className="field"><span>Ответственный</span><select value={ownerId} onChange={event => setOwnerId(event.target.value)}><option value="">Все доступные</option>{catalogs.owners.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label></div><p className="form-hint">Отчёт учитывает исторические этап и ответственного, а доступ — текущие права пользователя.</p></section>
    <ErrorAlert error={error}/>{snapshot && <section className="panel report-result"><div className="panel-heading"><div><span className="eyebrow">СНИМОК · {formatDate(snapshot.as_of)}</span><h2>Результат отчёта</h2></div><Button variant="secondary" onClick={() => api.download('/reports/snapshot/export', query()).catch(setError)}><Icon name="download" size={17}/>Скачать JSON</Button></div><div className="report-metrics"><div><strong>{snapshot.totals.interactions}</strong><span>взаимодействий</span></div><div><strong>{snapshot.totals.organizations}</strong><span>организаций</span></div><div><strong>{Object.keys(snapshot.totals.counts_by_state).length}</strong><span>этапов</span></div></div>{snapshot.rows.length ? <div className="table-scroll"><table className="data-table"><thead><tr><th>Взаимодействие</th><th>Организация</th><th>Этап</th><th>Ответственный</th></tr></thead><tbody>{snapshot.rows.map(row => <tr key={row.interaction_id}><td><strong>{row.title}</strong></td><td>{row.organization_name}</td><td><StageBadge code={row.state} name={row.state_name}/></td><td>{row.owner_name}</td></tr>)}</tbody></table></div> : <p className="empty-inline">На выбранный момент доступных данных нет.</p>}</section>}
    {!snapshot && !loading && <div className="panel empty-report"><Icon name="chart" size={30}/><h2>Выберите дату и постройте снимок</h2><p>Результат можно посмотреть в таблице и скачать в согласованном JSON формате.</p></div>}
    {loading && <Loading label="Считаем историческое состояние…"/>}
  </>;
}
