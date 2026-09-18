import { useState } from 'react';
import type { ApiClient } from '../api';
import { makeMutationKey } from '../api';
import { useResource } from '../hooks';
import { Avatar, Button, ErrorAlert, Icon, Loading, PageHeader, StageBadge, eventNames, formatDate } from '../ui';
import type { Catalogs, Interaction, InteractionDetail, User, Workflow } from '../types';

export function InteractionPage({ id, api, catalogs, workflow, me, revision, onChanged, onBack }: {
  id: string; api: ApiClient; catalogs: Catalogs; workflow: Workflow; me: User;
  revision: number; onChanged: () => void; onBack: () => void;
}) {
  const resource = useResource<InteractionDetail>(() => api.get('/interactions/' + encodeURIComponent(id)), [api, id, revision]);
  const [comment, setComment] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState('');
  const [owner, setOwner] = useState('');
  const [reason, setReason] = useState('');
  const item = resource.data;
  if (resource.loading && !item) return <Loading label="Загружаем карточку…"/>;
  if (resource.error || !item) return <><Button variant="ghost" onClick={onBack}><Icon name="back" size={17}/>К реестру</Button><ErrorAlert error={resource.error || 'Карточка не найдена.'} onRetry={onChanged}/></>;

  async function run(action: () => Promise<unknown>, success: string) {
    setBusy(true); setError(null); setNotice('');
    try { await action(); setNotice(success); onChanged(); }
    catch (problem) { setError(problem); }
    finally { setBusy(false); }
  }
  const transition = item.allowed_transitions[0];
  const selectedOwner = owner || item.owner_id;
  return <>
    <button className="back-link" onClick={onBack}><Icon name="back" size={17}/>Взаимодействия</button>
    <PageHeader eyebrow="КАРТОЧКА ВЗАИМОДЕЙСТВИЯ" title={item.title} description={item.organization_name}
      action={<StageBadge code={item.state} name={item.state_name}/>}/>
    <ErrorAlert error={error}/>{notice && <div className="success-alert"><Icon name="check" size={18}/>{notice}</div>}
    <div className="detail-grid">
      <section className="panel detail-main">
        <div className="detail-heading"><div><span className="eyebrow">ТЕКУЩИЙ ЭТАП</span><h2>{item.state_name}</h2></div><span className="quiet-badge">Revision {item.revision}</span></div>
        <div className="detail-facts">
          <div><span>Организация</span><strong>{item.organization_name}</strong></div>
          <div><span>ИТ-программа</span><strong>{item.program_name || 'Не определена'}</strong></div>
          <div><span>ИТ-продукт</span><strong>{item.product_name || 'Не определён'}</strong></div>
          <div><span>Цикл</span><strong>{item.cycle_label}</strong></div>
          <div><span>Ответственный</span><strong className="person-inline"><Avatar name={item.owner_name} small/>{item.owner_name}</strong></div>
          <div><span>Обновлено</span><strong>{formatDate(item.updated_at)}</strong></div>
        </div>
        {transition && <div className="action-block"><h3>Следующее действие</h3><p>Перевести карточку на этап «{transition.name}».</p>
          {transition.comment_required && <textarea value={comment} onChange={event => setComment(event.target.value)} placeholder="Комментарий обязателен" maxLength={5000}/>} 
          <Button disabled={busy} onClick={() => run(() => api.post<Interaction>('/interactions/' + encodeURIComponent(id) + '/transitions', {
            transition_code: transition.code, expected_revision: item.revision, comment: comment || null,
          }, makeMutationKey()), 'Этап обновлён')}>{busy ? 'Сохраняем…' : 'Перевести на следующий этап'}<Icon name="arrow" size={17}/></Button>
        </div>}
        {!transition && <div className="terminal-note"><Icon name="check" size={18}/>Карточка завершена. Новых переходов нет.</div>}
      </section>
      <aside className="detail-side">
        <section className="panel side-panel"><div className="panel-heading"><div><h2>Ответственный</h2><p>Текущий владелец карточки</p></div><Avatar name={item.owner_name}/></div><div className="owner-card"><strong>{item.owner_name}</strong><span>{item.owner_id}</span></div>
          {me.role === 'supervisor' && <><label className="field"><span>Передать менеджеру</span><select value={selectedOwner} onChange={event => setOwner(event.target.value)}>{catalogs.owners.filter(candidate => candidate.id !== item.owner_id).map(candidate => <option key={candidate.id} value={candidate.id}>{candidate.name}</option>)}</select></label><label className="field"><span>Причина передачи</span><textarea value={reason} onChange={event => setReason(event.target.value)} placeholder="Почему меняется ответственный"/></label><Button variant="secondary" disabled={busy || !reason.trim() || selectedOwner === item.owner_id} onClick={() => run(() => api.post('/interactions/' + encodeURIComponent(id) + '/assignments', { owner_id: selectedOwner, expected_revision: item.revision, reason: reason.trim() }, makeMutationKey()), 'Ответственный изменён')}>Передать карточку</Button></>}
        </section>
        <section className="panel side-panel"><div className="panel-heading"><div><h2>Комментарий</h2><p>Решение останется в истории</p></div><Icon name="message" size={20}/></div><textarea value={comment} onChange={event => setComment(event.target.value)} placeholder="Добавьте заметку…" maxLength={5000}/><Button variant="secondary" disabled={busy || !comment.trim()} onClick={() => run(() => api.post('/interactions/' + encodeURIComponent(id) + '/comments', { body: comment.trim(), expected_revision: item.revision }, makeMutationKey()), 'Комментарий добавлен')}>Добавить комментарий</Button></section>
      </aside>
    </div>
    <section className="panel timeline-panel"><div className="panel-heading"><div><span className="eyebrow">ИСТОРИЯ РЕШЕНИЙ</span><h2>События и комментарии</h2></div><span className="quiet-badge">{item.events.length} событий</span></div><div className="timeline">{item.events.map(event => <div className="timeline-item" key={event.id}><span className="timeline-dot"/><div><strong>{eventNames[event.type] || event.type}</strong><p>{event.comment || (event.to_state ? 'Этап: ' + (workflow.states.find(state => state.code === event.to_state)?.name || event.to_state) : '')}</p><small>{event.actor_name} · {formatDate(event.effective_at)}</small></div></div>)}{item.comments.map(entry => <div className="timeline-item" key={entry.id}><span className="timeline-dot tone-orange"/><div><strong>Комментарий</strong><p>{entry.body}</p><small>{entry.author_name} · {formatDate(entry.created_at)}</small></div></div>)}</div></section>
  </>;
}
