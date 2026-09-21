import { useState, useRef } from 'react';
import type { FormEvent } from 'react';
import type { ApiClient } from '../api';
import { ApiError, makeMutationKey, messageOf } from '../api';
import { useResource } from '../hooks';
import { Avatar, Button, ErrorAlert, Icon, Loading, Modal, PageHeader, StageBadge, eventNames, formatDate } from '../ui';
import type { Attachment, Catalogs, Interaction, InteractionDetail, InteractionUpdatePayload, Transition, User, Workflow } from '../types';
import { WorkflowGraphView } from './WorkflowGraphView';

const ALLOWED_EXTENSIONS = new Set([
  'png', 'jpeg', 'jpg', 'pdf', 'zip', 'gz', 'gzip', 'rar', 'doc', 'docx', 'xls', 'xlsx'
]);
const MAX_FILE_SIZE = 25 * 1024 * 1024; // 25 MB (152-ФЗ)

function getFormatBadge(filename: string) {
  const ext = filename.split('.').pop()?.toLowerCase() || '';
  if (ext === 'pdf') return <span className="format-badge format-pdf">PDF</span>;
  if (ext === 'doc' || ext === 'docx') return <span className="format-badge format-doc">DOC</span>;
  if (ext === 'xls' || ext === 'xlsx') return <span className="format-badge format-xls">XLS</span>;
  if (['png', 'jpeg', 'jpg'].includes(ext)) return <span className="format-badge format-img">IMG</span>;
  if (['zip', 'gz', 'gzip', 'rar'].includes(ext)) return <span className="format-badge format-archive">ZIP</span>;
  return <span className="format-badge format-archive">{ext.toUpperCase() || 'FILE'}</span>;
}

function formatFileSize(bytes: number): string {
  if (!bytes && bytes !== 0) return '0 Б';
  if (bytes < 1024) return `${bytes} Б`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} КБ`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} МБ`;
}

const LATE_SUBJECT_STATES = new Set([
  'materials_transfer', 'deployment', 'teacher_training',
  'curriculum_update', 'classes', 'materials_update',
  'teacher_upskilling', 'completed',
]);

export function EditInteractionModal({
  item, api, catalogs, onClose, onSaved
}: {
  item: InteractionDetail;
  api: ApiClient;
  catalogs: Catalogs;
  onClose: () => void;
  onSaved: (updated: Interaction) => void;
}) {
  const isLateState = LATE_SUBJECT_STATES.has(item.state);
  const [form, setForm] = useState({
    title: item.title,
    program_id: item.program_id || '',
    product_id: item.product_id || '',
    cycle_label: item.cycle_label,
    contact_id: item.contact_id || '',
    contract_id: item.contract_id || '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const orgContacts = (catalogs.contacts || []).filter(c => c.organization_id === item.organization_id && c.active);
  const orgContracts = (catalogs.contracts || []).filter(c => c.organization_id === item.organization_id);

  const compatibleProducts = catalogs.products.filter(prod => {
    if (!form.program_id) return true;
    if (catalogs.program_products && catalogs.program_products.length > 0) {
      return catalogs.program_products.some(pp => pp.program_id === form.program_id && pp.product_id === prod.id);
    }
    if (form.program_id === 'program-devops') return prod.id === 'product-cloud';
    if (form.program_id === 'program-qa') return prod.id === 'product-test';
    return true;
  });

  const handleProgramChange = (newProgramId: string) => {
    setForm(prev => {
      let nextProductId = prev.product_id;
      if (newProgramId) {
        const isStillCompatible = catalogs.program_products && catalogs.program_products.length > 0
          ? catalogs.program_products.some(pp => pp.program_id === newProgramId && pp.product_id === nextProductId)
          : (newProgramId === 'program-devops' ? nextProductId === 'product-cloud' : nextProductId === 'product-test');
        if (!isStillCompatible) nextProductId = '';
      }
      return { ...prev, program_id: newProgramId, product_id: nextProductId };
    });
  };

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    if (isLateState && (!form.program_id || !form.product_id)) {
      setError(new Error('На текущем этапе нельзя оставить ИТ-программу или ИТ-продукт пустыми.'));
      return;
    }

    setSaving(true);
    const payload: InteractionUpdatePayload = {
      expected_revision: item.revision,
      title: form.title.trim(),
      program_id: form.program_id || null,
      product_id: form.product_id || null,
      cycle_label: form.cycle_label.trim(),
      contact_id: form.contact_id || null,
      contract_id: form.contract_id || null,
    };

    try {
      const key = makeMutationKey();
      const updated = await api.patch<Interaction>(
        '/interactions/' + encodeURIComponent(item.id),
        payload,
        key
      );
      onSaved(updated);
    } catch (problem) {
      if (problem instanceof ApiError && problem.status === 409) {
        setError(new ApiError(
          'Карточка была изменена другим пользователем. Пожалуйста, обновите карточку, чтобы увидеть актуальные данные.',
          'REVISION_CONFLICT',
          409,
          problem.requestId,
          problem.details
        ));
      } else {
        setError(problem);
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal title="Редактировать параметры взаимодействия" subtitle={`Организация: ${item.organization_name}`} onClose={onClose} busy={saving} wide>
      <form onSubmit={submit}>
        <div className="modal-body">
          <ErrorAlert error={error}/>
          <label className="field">
            <span>Название взаимодействия <b>*</b></span>
            <input value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} required maxLength={250}/>
          </label>
          <div className="form-grid">
            <label className="field">
              <span>ИТ-программа {isLateState && <b>*</b>}</span>
              <select value={form.program_id} onChange={e => handleProgramChange(e.target.value)} required={isLateState}>
                <option value="">{isLateState ? 'Выберите программу' : 'Пока не определена'}</option>
                {catalogs.programs.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </label>
            <label className="field">
              <span>ИТ-продукт {isLateState && <b>*</b>}</span>
              <select value={form.product_id} onChange={e => setForm(f => ({ ...f, product_id: e.target.value }))} required={isLateState}>
                <option value="">{isLateState ? 'Выберите продукт' : 'Пока не определён'}</option>
                {compatibleProducts.map(prod => <option key={prod.id} value={prod.id}>{prod.name} ({prod.vendor})</option>)}
              </select>
            </label>
            <label className="field">
              <span>Цикл сотрудничества <b>*</b></span>
              <input value={form.cycle_label} onChange={e => setForm(f => ({ ...f, cycle_label: e.target.value }))} required maxLength={100}/>
            </label>
            <label className="field">
              <span>Контактное лицо вуза</span>
              <select value={form.contact_id} onChange={e => setForm(f => ({ ...f, contact_id: e.target.value }))}>
                <option value="">Не указано</option>
                {orgContacts.map(c => <option key={c.id} value={c.id}>{c.full_name} ({c.position})</option>)}
              </select>
            </label>
            <label className="field span-2">
              <span>Договор сотрудничества</span>
              <select value={form.contract_id} onChange={e => setForm(f => ({ ...f, contract_id: e.target.value }))}>
                <option value="">Не привязан</option>
                {orgContracts.map(c => <option key={c.id} value={c.id}>№ {c.number} (статус: {c.status})</option>)}
              </select>
            </label>
          </div>
          {isLateState && (
            <div className="info-note">
              <Icon name="alert" size={18}/>
              <p>На этапе «{item.state_name}» наличие ИТ-программы и продукта обязательно для корректного исполнения процесса.</p>
            </div>
          )}
        </div>
        <div className="modal-actions">
          <Button variant="secondary" type="button" onClick={onClose} disabled={saving}>Отмена</Button>
          <Button type="submit" disabled={saving}>
            {saving ? <><span className="spinner small"/>Сохраняем…</> : <><Icon name="check" size={17}/>Сохранить параметры</>}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

export function TransitionCommentModal({
  transition, busy, onClose, onConfirm
}: {
  transition: Transition;
  busy: boolean;
  onClose: () => void;
  onConfirm: (comment: string) => Promise<void>;
}) {
  const [commentText, setCommentText] = useState('');
  const [error, setError] = useState<unknown>(null);
  const isCancel = transition.to === 'cancelled' || transition.code.endsWith('_to_cancelled');

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!commentText.trim()) return;
    setError(null);
    try {
      await onConfirm(commentText.trim());
    } catch (err) {
      setError(err);
    }
  }

  return (
    <Modal
      title={isCancel ? 'Отмена взаимодействия' : `Переход: «${transition.name}»`}
      subtitle="Для выполнения данного шага обязательно укажите причину или комментарий"
      onClose={onClose}
      busy={busy}
    >
      <form onSubmit={handleSubmit}>
        <div className="modal-body">
          <ErrorAlert error={error}/>
          <label className="field">
            <span>{isCancel ? 'Причина отмены' : 'Обоснование решения'} <b>*</b></span>
            <textarea
              autoFocus
              value={commentText}
              onChange={e => setCommentText(e.target.value)}
              placeholder={isCancel ? 'Укажите причину отмены взаимодействия…' : 'Укажите комментарий к переходу…'}
              required
              maxLength={5000}
            />
          </label>
        </div>
        <div className="modal-actions">
          <Button variant="secondary" type="button" onClick={onClose} disabled={busy}>Отмена</Button>
          <Button
            variant={isCancel ? 'danger' : 'primary'}
            type="submit"
            disabled={busy || !commentText.trim()}
          >
            {busy ? <span className="spinner small"/> : <Icon name="check" size={16}/>}
            {isCancel ? 'Подтвердить отмену' : 'Выполнить переход'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

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
  const [editOpen, setEditOpen] = useState(false);
  const [pendingTransition, setPendingTransition] = useState<Transition | null>(null);
  const [attRevision, setAttRevision] = useState(0);
  const attachmentsResource = useResource<Attachment[]>(
    () => api.get<Attachment[]>('/interactions/' + encodeURIComponent(id) + '/attachments'),
    [api, id, revision, attRevision]
  );

  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const item = resource.data;
  const attachmentsList = attachmentsResource.data || item?.attachments || [];

  async function handleFileUpload(file: File) {
    setUploadError(null);
    setUploadSuccess(null);

    const ext = file.name.split('.').pop()?.toLowerCase() || '';
    if (!ALLOWED_EXTENSIONS.has(ext)) {
      setUploadError(`Недопустимый формат файла «.${ext}». Разрешены ровно 10 форматов: png, jpeg, pdf, zip, gzip, rar, doc, docx, xls, xlsx.`);
      return;
    }

    if (file.size > MAX_FILE_SIZE) {
      setUploadError(`Размер файла «${file.name}» (${formatFileSize(file.size)}) превышает предельно допустимый лимит 25 МБ.`);
      return;
    }

    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      await api.upload('/interactions/' + encodeURIComponent(id) + '/attachments', formData, makeMutationKey());
      setUploadSuccess(`Файл «${file.name}» успешно загружен.`);
      setAttRevision(v => v + 1);
      onChanged();
    } catch (err) {
      setUploadError(messageOf(err));
    } finally {
      setUploading(false);
    }
  }

  async function handleDownloadAttachment(att: Attachment) {
    try {
      await api.downloadGet('/interactions/' + encodeURIComponent(id) + '/attachments/' + encodeURIComponent(att.id) + '/download', att.file_name);
    } catch (err) {
      setError(err);
    }
  }
  if (resource.loading && !item) return <Loading label="Загружаем карточку…"/>;
  if (resource.error || !item) return <><Button variant="ghost" onClick={onBack}><Icon name="back" size={17}/>К реестру</Button><ErrorAlert error={resource.error || 'Карточка не найдена.'} onRetry={onChanged}/></>;

  async function run(action: () => Promise<unknown>, success: string) {
    setBusy(true); setError(null); setNotice('');
    try { await action(); setNotice(success); onChanged(); }
    catch (problem) { setError(problem); }
    finally { setBusy(false); }
  }

  const handleTransitionClick = (t: Transition) => {
    if (t.comment_required) {
      setPendingTransition(t);
    } else {
      run(() => api.post<Interaction>(
        '/interactions/' + encodeURIComponent(id) + '/transitions',
        { transition_code: t.code, expected_revision: item.revision, comment: null },
        makeMutationKey()
      ), `Этап обновлён: ${t.name}`);
    }
  };

  async function handleConfirmComment(commentText: string) {
    if (!pendingTransition) return;
    const t = pendingTransition;
    setBusy(true);
    try {
      await api.post<Interaction>(
        '/interactions/' + encodeURIComponent(id) + '/transitions',
        { transition_code: t.code, expected_revision: item.revision, comment: commentText },
        makeMutationKey()
      );
      setPendingTransition(null);
      setNotice(`Этап обновлён: ${t.name}`);
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  const selectedOwner = owner || item.owner_id;
  const isClosed = !!item.closed_at;

  return <>
    <button className="back-link" onClick={onBack}><Icon name="back" size={17}/>Взаимодействия</button>
    <PageHeader eyebrow="КАРТОЧКА ВЗАИМОДЕЙСТВИЯ" title={item.title} description={item.organization_name}
      action={<StageBadge code={item.state} name={item.state_name}/>}/>
    <ErrorAlert error={error}/>{notice && <div className="success-alert"><Icon name="check" size={18}/>{notice}</div>}
    <div className="detail-grid">
      <section className="panel detail-main">
        <div className="detail-heading">
          <div><span className="eyebrow">ТЕКУЩИЙ ЭТАП</span><h2>{item.state_name}</h2></div>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            {!isClosed && (
              <Button variant="secondary" onClick={() => setEditOpen(true)} disabled={busy}>
                <Icon name="file" size={16}/>Редактировать параметры
              </Button>
            )}
            <span className="quiet-badge">Revision {item.revision}</span>
          </div>
        </div>
        <div className="detail-facts">
          <div><span>Организация</span><strong>{item.organization_name}</strong></div>
          <div><span>ИТ-программа</span><strong>{item.program_name || 'Не определена'}</strong></div>
          <div><span>ИТ-продукт</span><strong>{item.product_name || 'Не определён'}</strong></div>
          <div><span>Цикл</span><strong>{item.cycle_label}</strong></div>
          <div><span>Контакт вуза</span><strong>{item.contact_name || 'Не указан'}</strong></div>
          <div><span>Договор</span><strong>{item.contract_number ? `№ ${item.contract_number}` : 'Не привязан'}</strong></div>
          <div><span>Лицензия</span><strong>{item.license_status ? `Лицензия (${item.license_status})` : 'Не привязана'}</strong></div>
          <div><span>Ответственный</span><strong className="person-inline"><Avatar name={item.owner_name} small/>{item.owner_name}</strong></div>
          <div><span>Обновлено</span><strong>{formatDate(item.updated_at)}</strong></div>
        </div>
        {item.allowed_transitions && item.allowed_transitions.length > 0 && (
          <div className="action-block">
            <h3>Доступные действия</h3>
            <p>Выберите следующее действие для перевода карточки по жизненному циклу:</p>
            <div className="transitions-group">
              {item.allowed_transitions.map(t => {
                const isCancel = t.to === 'cancelled' || t.kind === 'cancellation' || t.code.endsWith('_to_cancelled');
                const isRework = t.kind === 'rework' || t.kind === 'cycle' || t.to === 'document_revision' || t.to === 'classes';
                const variant: 'primary' | 'secondary' | 'danger' = isCancel ? 'danger' : isRework ? 'secondary' : 'primary';

                return (
                  <Button
                    key={t.code}
                    variant={variant}
                    disabled={busy}
                    className={isCancel ? 'transitions-cancellation' : ''}
                    onClick={() => handleTransitionClick(t)}
                  >
                    {isCancel ? <Icon name="close" size={16}/> : isRework ? <Icon name="refresh" size={16}/> : <Icon name="arrow" size={16}/>}
                    {isCancel ? 'Отменить взаимодействие' : isRework ? `Вернуть: ${t.name}` : `Перейти: ${t.name}`}
                  </Button>
                );
              })}
            </div>
          </div>
        )}
        {(!item.allowed_transitions || item.allowed_transitions.length === 0) && (
          <div className="terminal-note">
            <Icon name="check" size={18}/>
            {item.state === 'cancelled' ? 'Взаимодействие отменено.' : 'Взаимодействие успешно завершено. Новых переходов нет.'}
          </div>
        )}
      </section>
      <aside className="detail-side">
        <section className="panel side-panel"><div className="panel-heading"><div><h2>Ответственный</h2><p>Текущий владелец карточки</p></div><Avatar name={item.owner_name}/></div><div className="owner-card"><strong>{item.owner_name}</strong><span>{item.owner_id}</span></div>
          {me.role === 'supervisor' && !isClosed && <><label className="field"><span>Передать менеджеру</span><select value={selectedOwner} onChange={event => setOwner(event.target.value)}>{catalogs.owners.filter(candidate => candidate.id !== item.owner_id).map(candidate => <option key={candidate.id} value={candidate.id}>{candidate.name}</option>)}</select></label><label className="field"><span>Причина передачи</span><textarea value={reason} onChange={event => setReason(event.target.value)} placeholder="Почему меняется ответственный"/></label><Button variant="secondary" disabled={busy || !reason.trim() || selectedOwner === item.owner_id} onClick={() => run(() => api.post('/interactions/' + encodeURIComponent(id) + '/assignments', { owner_id: selectedOwner, expected_revision: item.revision, reason: reason.trim() }, makeMutationKey()), 'Ответственный изменён')}>Передать карточку</Button></>}
        </section>
        <section className="panel side-panel"><div className="panel-heading"><div><h2>Комментарий</h2><p>Решение останется в истории</p></div><Icon name="message" size={20}/></div><textarea value={comment} onChange={event => setComment(event.target.value)} placeholder="Добавьте заметку…" maxLength={5000}/><Button variant="secondary" disabled={busy || !comment.trim()} onClick={() => run(() => api.post('/interactions/' + encodeURIComponent(id) + '/comments', { body: comment.trim(), expected_revision: item.revision }, makeMutationKey()), 'Комментарий добавлен')}>Добавить комментарий</Button></section>
      </aside>
    </div>

    {/* Секция «Вложения и документы» */}
    <section className="panel attachments-section" style={{ padding: '22px' }}>
      <div className="panel-heading">
        <div>
          <span className="eyebrow">ДОКУМЕНТООБОРОТ И ВЛОЖЕНИЯ</span>
          <h2>Вложения и документы</h2>
          <p>Файлы карточки, соглашения, акты и обучающие материалы (10 форматов ТЗ, до 25 МБ)</p>
        </div>
        <span className="quiet-badge">{attachmentsList.length} файлов</span>
      </div>

      {uploadError && (
        <div className="error-alert" style={{ marginTop: '12px' }}>
          <Icon name="alert" size={18} />
          <div><strong>Ошибка загрузки</strong><small>{uploadError}</small></div>
        </div>
      )}
      {uploadSuccess && (
        <div className="success-alert" style={{ marginTop: '12px' }}>
          <Icon name="check" size={18} />
          <div>{uploadSuccess}</div>
        </div>
      )}

      {/* Drag & Drop uploader area */}
      {!isClosed && (
        <div
          className={`dropzone ${isDragging ? 'active' : ''}`}
          onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setIsDragging(false);
            const dropped = e.dataTransfer.files?.[0];
            if (dropped) handleFileUpload(dropped);
          }}
          onClick={() => fileInputRef.current?.click()}
        >
          <input
            type="file"
            ref={fileInputRef}
            style={{ display: 'none' }}
            accept=".png,.jpeg,.jpg,.pdf,.zip,.gz,.gzip,.rar,.doc,.docx,.xls,.xlsx"
            onChange={(e) => {
              const selected = e.target.files?.[0];
              if (selected) handleFileUpload(selected);
              e.target.value = '';
            }}
          />
          <div className="dropzone-icon">
            <Icon name="upload" size={22} />
          </div>
          <div className="dropzone-prompt">
            <strong>{uploading ? 'Загрузка файла…' : 'Перетащите файл сюда или нажмите для выбора'}</strong>
            <p>Разрешённые форматы: PNG, JPEG, PDF, ZIP, GZIP, RAR, DOC, DOCX, XLS, XLSX</p>
            <div className="dropzone-limit">Максимальный размер одного файла: 25 МБ (152-ФЗ)</div>
          </div>
          <div style={{ marginTop: '12px' }}>
            <Button
              variant="secondary"
              disabled={uploading}
              onClick={(e) => { e.stopPropagation(); fileInputRef.current?.click(); }}
            >
              <Icon name="file" size={16} />Выбрать файл на компьютере
            </Button>
          </div>
        </div>
      )}

      {/* Attachments List */}
      {attachmentsList.length > 0 ? (
        <div className="file-list">
          {attachmentsList.map((att) => (
            <div key={att.id} className="file-item">
              <div className="file-item-left">
                {getFormatBadge(att.file_name)}
                <div className="file-meta">
                  <strong>{att.file_name}</strong>
                  <small>
                    {formatFileSize(att.file_size)} · Загрузил {att.uploaded_by_name || att.uploaded_by} · {formatDate(att.created_at)}
                  </small>
                </div>
              </div>
              <div className="file-actions">
                <Button
                  variant="secondary"
                  onClick={() => handleDownloadAttachment(att)}
                  title="Авторизованное скачивание файла"
                >
                  <Icon name="download" size={16} />Скачать
                </Button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="empty-inline" style={{ marginTop: '12px' }}>
          К данному взаимодействию ещё не прикреплены файлы и документы.
        </p>
      )}
    </section>

    {/* Интерактивный граф жизненного цикла карточки */}
    <WorkflowGraphView currentState={item.state} />

    <section className="panel timeline-panel"><div className="panel-heading"><div><span className="eyebrow">ИСТОРИЯ РЕШЕНИЙ</span><h2>События и комментарии</h2></div><span className="quiet-badge">{item.events.length} событий</span></div><div className="timeline">{item.events.map(event => <div className="timeline-item" key={event.id}><span className="timeline-dot"/><div><strong>{eventNames[event.type] || event.type}</strong><p>{event.comment || (event.to_state ? 'Этап: ' + (workflow.states.find(state => state.code === event.to_state)?.name || event.to_state) : '')}</p><small>{event.actor_name} · {formatDate(event.effective_at)}</small></div></div>)}{item.comments.map(entry => <div className="timeline-item" key={entry.id}><span className="timeline-dot tone-orange"/><div><strong>Комментарий</strong><p>{entry.body}</p><small>{entry.author_name} · {formatDate(entry.created_at)}</small></div></div>)}</div></section>

    {editOpen && (
      <EditInteractionModal
        item={item}
        api={api}
        catalogs={catalogs}
        onClose={() => setEditOpen(false)}
        onSaved={_updated => {
          setEditOpen(false);
          setNotice('Параметры взаимодействия успешно обновлены');
          onChanged();
        }}
      />
    )}

    {pendingTransition && (
      <TransitionCommentModal
        transition={pendingTransition}
        busy={busy}
        onClose={() => setPendingTransition(null)}
        onConfirm={handleConfirmComment}
      />
    )}
  </>;
}
