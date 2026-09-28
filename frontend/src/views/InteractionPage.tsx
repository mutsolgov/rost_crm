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

function formatTimelineCount(count: number): string {
  const mod10 = Math.abs(count) % 10;
  const mod100 = Math.abs(count) % 100;
  if (mod100 >= 11 && mod100 <= 19) return `${count} записей`;
  if (mod10 === 1) return `${count} запись`;
  if (mod10 >= 2 && mod10 <= 4) return `${count} записи`;
  return `${count} записей`;
}

const LATE_SUBJECT_STATES = new Set([
  'materials_transfer', 'deployment', 'teacher_training',
  'curriculum_update', 'classes', 'materials_update',
  'teacher_upskilling', 'completed',
]);

const CANONICAL_STAGE_STEPS: Record<string, number> = {
  contact_search: 1,
  needs_clarification: 2,
  meeting: 3,
  document_exchange: 4,
  document_revision: 5,
  document_signing: 6,
  materials_transfer: 7,
  deployment: 8,
  teacher_training: 9,
  curriculum_update: 10,
  classes: 11,
  materials_update: 12,
  teacher_upskilling: 13,
};

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
    license_id: item.license_id || '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const orgContacts = (catalogs.contacts || []).filter(c => c.organization_id === item.organization_id && c.active);
  const orgContracts = (catalogs.contracts || []).filter(c => c.organization_id === item.organization_id);
  const orgLicenses = (catalogs.licenses || []).filter(l => l.organization_id === item.organization_id && (!form.product_id || l.product_id === form.product_id));

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
      if (newProgramId && nextProductId) {
        const isStillCompatible = catalogs.program_products && catalogs.program_products.length > 0
          ? catalogs.program_products.some(pp => pp.program_id === newProgramId && pp.product_id === nextProductId)
          : (newProgramId === 'program-devops' ? nextProductId === 'product-cloud' : nextProductId === 'product-test');
        if (!isStillCompatible) nextProductId = '';
      }
      let nextLicenseId = prev.license_id;
      if (nextLicenseId) {
        const lic = (catalogs.licenses || []).find(l => l.id === nextLicenseId);
        if (lic) {
          if (nextProductId && lic.product_id !== nextProductId) {
            nextLicenseId = '';
          } else if (newProgramId) {
            const isLicCompatible = catalogs.program_products && catalogs.program_products.length > 0
              ? catalogs.program_products.some(pp => pp.program_id === newProgramId && pp.product_id === lic.product_id)
              : (newProgramId === 'program-devops' ? lic.product_id === 'product-cloud' : lic.product_id === 'product-test');
            if (!isLicCompatible) nextLicenseId = '';
          }
        }
      }
      return { ...prev, program_id: newProgramId, product_id: nextProductId, license_id: nextLicenseId };
    });
  };

  const handleProductChange = (newProductId: string) => {
    setForm(prev => {
      let nextLicenseId = prev.license_id;
      if (nextLicenseId && newProductId) {
        const lic = (catalogs.licenses || []).find(l => l.id === nextLicenseId);
        if (lic && lic.product_id !== newProductId) {
          nextLicenseId = '';
        }
      }
      return { ...prev, product_id: newProductId, license_id: nextLicenseId };
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
      license_id: form.license_id || null,
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
              <select value={form.product_id} onChange={e => handleProductChange(e.target.value)} required={isLateState}>
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
                {orgContacts.map(c => <option key={c.id} value={c.id}>{c.full_name}{c.position ? ` (${c.position})` : ''}</option>)}
              </select>
            </label>
            <label className="field span-2">
              <span>Договор сотрудничества</span>
              <select value={form.contract_id} onChange={e => setForm(f => ({ ...f, contract_id: e.target.value }))}>
                <option value="">Не привязан</option>
                {orgContracts.map(c => <option key={c.id} value={c.id}>№ {c.number} (статус: {c.status})</option>)}
              </select>
            </label>
            <label className="field span-2">
              <span>Лицензия ПО</span>
              <select value={form.license_id} onChange={e => setForm(f => ({ ...f, license_id: e.target.value }))}>
                <option value="">Не привязана</option>
                {orgLicenses.map(l => {
                  const prod = catalogs.products.find(p => p.id === l.product_id);
                  const prodName = prod ? `${prod.name} (${prod.vendor})` : l.product_id;
                  const termStr = l.term_years ? `${l.term_years} г.` : 'бессрочно';
                  return (
                    <option key={l.id} value={l.id}>
                      {prodName} — статус: {l.transfer_status}, срок: {termStr}
                    </option>
                  );
                })}
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
  const isCancel = transition.kind === 'cancellation' || transition.to === 'cancelled' || transition.code.endsWith('_to_cancelled');

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


export function DeleteAttachmentModal({
  attachment,
  onClose,
  onConfirm,
  busy,
  error,
}: {
  attachment: Attachment;
  onClose: () => void;
  onConfirm: () => void;
  busy: boolean;
  error: unknown;
}) {
  return (
    <Modal
      title="Удаление вложения"
      subtitle={`Файл: ${attachment.file_name}`}
      onClose={onClose}
      busy={busy}
    >
      <div className="modal-body">
        <ErrorAlert error={error} />
        <p style={{ fontSize: '15px', lineHeight: '1.5', margin: '0', color: '#101828' }}>
          Вы действительно хотите удалить файл «{attachment.file_name}» ({formatFileSize(attachment.file_size)})? Это действие нельзя отменить.
        </p>
      </div>
      <div className="modal-actions" style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
        <Button variant="ghost" onClick={onClose} disabled={busy}>
          Отмена
        </Button>
        <Button
          variant="danger"
          style={{ background: '#D92D20', borderColor: '#D92D20', color: '#FFFFFF' }}
          onClick={onConfirm}
          disabled={busy}
        >
          {busy ? <span className="spinner small" /> : <Icon name="close" size={16} />}
          {busy ? 'Удаление…' : 'Удалить вложение'}
        </Button>
      </div>
    </Modal>
  );
}

export function getTransitionPresentation(t: Transition, workflow?: Workflow) {
  const fallbackKind = workflow?.transitions?.find(edge => edge.code === t.code)?.kind;
  const kind = t.kind || fallbackKind || (t.to === 'cancelled' || t.code.endsWith('_to_cancelled') ? 'cancellation' : 'forward');
  const targetName = t.name || workflow?.states?.find(s => s.code === t.to)?.name || t.to || '';

  if (kind === 'cancellation' || t.to === 'cancelled') {
    return {
      title: 'Отменить взаимодействие',
      variant: 'danger' as const,
      icon: 'close' as const,
      className: 'transitions-cancellation',
    };
  }
  if (kind === 'skip_optional') {
    return {
      title: `Пропустить: ${targetName}`,
      variant: 'secondary' as const,
      icon: 'arrow' as const,
      className: '',
    };
  }
  if (kind === 'rework') {
    return {
      title: `Вернуть: ${targetName}`,
      variant: 'secondary' as const,
      icon: 'refresh' as const,
      className: '',
    };
  }
  if (kind === 'cycle') {
    return {
      title: `Повторный цикл: ${targetName}`,
      variant: 'secondary' as const,
      icon: 'refresh' as const,
      className: '',
    };
  }
  return {
    title: `Перейти: ${targetName}`,
    variant: 'primary' as const,
    icon: 'arrow' as const,
    className: '',
  };
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

  const [deleteAttachmentTarget, setDeleteAttachmentTarget] = useState<Attachment | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<unknown>(null);
  const [historyTab, setHistoryTab] = useState<'all' | 'comments' | 'stages'>('all');

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
      if (item?.revision !== undefined) {
        formData.append('expected_revision', String(item.revision));
      }
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

  async function handleOpenPreview(att: Attachment) {
    setError(null);
    const targetWindow = window.open('about:blank', '_blank');
    if (!targetWindow || targetWindow.closed) {
      setError(new Error('Браузер заблокировал открытие новой вкладки. Разрешите всплывающие окна или используйте «Скачать».'));
      return;
    }
    try {
      targetWindow.document.title = 'Загрузка: ' + att.file_name;
    } catch {
      // Cross-context or sandbox title restriction ignored
    }

    let cleanupFn: (() => void) | null = null;
    try {
      const { blobUrl, cleanup } = await api.previewAttachmentBlob(
        `/interactions/${encodeURIComponent(id)}/attachments/${encodeURIComponent(att.id)}/download?disposition=inline`
      );
      cleanupFn = cleanup;

      if (targetWindow.closed) {
        cleanup();
        return;
      }

      targetWindow.location.href = blobUrl;

      let cleaned = false;
      let pollTimer: number | undefined;
      let maxTimeout: number | undefined;

      const safeCleanup = () => {
        if (cleaned) return;
        cleaned = true;
        if (pollTimer !== undefined) window.clearInterval(pollTimer);
        if (maxTimeout !== undefined) window.clearTimeout(maxTimeout);
        cleanup();
      };

      // Lifecycle poller: immediately revokes blobUrl when user closes the preview tab
      let pollErrors = 0;
      pollTimer = window.setInterval(() => {
        try {
          if (targetWindow.closed) {
            safeCleanup();
          }
        } catch {
          pollErrors++;
          // If cross-origin or sandbox policy restricts inspecting .closed, stop polling
          // and let maxTimeout safely handle cleanup to avoid premature revocation while reading
          if (pollErrors > 3) {
            if (pollTimer !== undefined) window.clearInterval(pollTimer);
          }
        }
      }, 2000);

      // Safety upper bound: prevents memory leaks if preview tab stays open indefinitely (1 hour)
      maxTimeout = window.setTimeout(safeCleanup, 3600000);
    } catch (err) {
      if (cleanupFn) {
        try { cleanupFn(); } catch { /* ignore */ }
      }
      try {
        if (!targetWindow.closed) {
          targetWindow.close();
        }
      } catch {
        // Safe fallback if window is already detached
      }
      setError(err);
    }
  }

  async function handleDeleteAttachment() {
    if (!deleteAttachmentTarget || !item) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await api.deleteAttachment(id, deleteAttachmentTarget.id, item.revision);
      const name = deleteAttachmentTarget.file_name;
      setDeleteAttachmentTarget(null);
      setNotice(`Вложение «${name}» успешно удалено.`);
      attachmentsResource.reload();
      onChanged();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setDeleteError(new ApiError(
          'Карточка была изменена другим пользователем. Обновите данные перед удалением файла.',
          'REVISION_CONFLICT',
          409,
          err.requestId,
          err.details
        ));
      } else {
        setDeleteError(err);
      }
    } finally {
      setDeleting(false);
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
    if (!pendingTransition || !item) return;
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

  const isClosed = !!item.closed_at;
  const productVendor = item.product_vendor || catalogs.products.find(p => p.id === item.product_id)?.vendor;
  const boundLicense = item.license_id ? (catalogs.licenses || []).find(l => l.id === item.license_id) : null;
  const licenseStatus = item.license_status || boundLicense?.transfer_status;
  const licenseTermYears = item.license_term_years ?? boundLicense?.term_years;
  const licenseSignedOn = item.license_signed_on || boundLicense?.signed_on;

  const visibleEvents = (item.events || []).filter(e => e.type !== 'attachment_deleted');
  const comments = item.comments || [];

  const coveredCommentIds = new Set<string>();
  for (const e of visibleEvents) {
    const cid = (e as any).comment_id || (e as any).payload?.comment_id;
    if (cid) coveredCommentIds.add(String(cid));
  }

  const standaloneComments = comments.filter(c => {
    if (coveredCommentIds.has(c.id)) return false;
    return !visibleEvents.some(
      e => (e.type === 'comment_added' || e.type === 'comment') && e.comment && e.comment === c.body
    );
  });

  const allList = [
    ...visibleEvents.map(event => ({
      key: `event-${event.id}`,
      time: event.effective_at,
      sequence: event.sequence,
      type: event.type,
      isComment: event.type === 'comment_added' || event.type === 'comment',
      title: eventNames[event.type] || event.type,
      text: event.comment || (event.to_state ? 'Этап: ' + (workflow?.states?.find(state => state.code === event.to_state)?.name || event.to_state) : (event.file_name ? `Файл: ${event.file_name}` : '')),
      meta: `${event.actor_name} · ${formatDate(event.effective_at)}`,
    })),
    ...standaloneComments.map(entry => ({
      key: `comment-${entry.id}`,
      time: entry.created_at,
      sequence: undefined as number | undefined,
      type: 'comment',
      isComment: true,
      title: 'Комментарий',
      text: entry.body,
      meta: `${entry.author_name} · ${formatDate(entry.created_at)}`,
    })),
  ].sort((a, b) => {
    const tA = new Date(a.time).getTime() || 0;
    const tB = new Date(b.time).getTime() || 0;
    if (tA !== tB) return tA - tB;
    if (a.sequence !== undefined && b.sequence !== undefined) {
      return a.sequence - b.sequence;
    }
    return 0;
  });

  const timelineEntries = allList;

  const commentsList = allList.filter(
    item => item.type === 'comment_added' || item.type === 'comment'
  );

  const stagesList = allList.filter(
    item =>
      item.type === 'stage_transition' ||
      item.type === 'state_changed' ||
      item.type === 'assignment_changed' ||
      item.type === 'owner_changed' ||
      item.type === 'transition' ||
      item.type === 'assignment'
  );

  const displayedTimeline =
    historyTab === 'comments'
      ? commentsList
      : historyTab === 'stages'
        ? stagesList
        : allList;

  const currentStateMeta = workflow?.states?.find(s => s.code === item.state);
  const isTerminalStage = currentStateMeta?.kind === 'terminal' || item.state === 'completed' || item.state === 'cancelled';
  const stepNumber = currentStateMeta?.source_step ?? CANONICAL_STAGE_STEPS[item.state] ?? (
    workflow?.states
      ? workflow.states.filter(s => s.kind === 'working').findIndex(s => s.code === item.state) + 1
      : undefined
  );
  const stageHeaderTitle = (!isTerminalStage && stepNumber && stepNumber > 0)
    ? `Этап ${stepNumber} из 13: ${item.state_name}`
    : item.state_name;

  return <>
    <button className="back-link" onClick={onBack}><Icon name="back" size={17}/>Взаимодействия</button>
    <PageHeader eyebrow="КАРТОЧКА ВЗАИМОДЕЙСТВИЯ" title={item.title} description={item.organization_name}
      action={<StageBadge code={item.state} name={item.state_name}/>}/>
    <ErrorAlert error={error}/>{notice && <div className="success-alert"><Icon name="check" size={18}/>{notice}</div>}
    <div className="detail-grid">
      <section className="panel detail-main">
        <div className="detail-heading">
          <div><span className="eyebrow">ТЕКУЩИЙ ЭТАП</span><h2>{stageHeaderTitle}</h2></div>
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
          {productVendor && <div><span>Вендор ПО</span><strong>{productVendor}</strong></div>}
          <div><span>Цикл</span><strong>{item.cycle_label}</strong></div>
          <div><span>Контакт вуза</span><strong>{item.contact_name || 'Не указан'}</strong></div>
          <div><span>Договор</span><strong>{item.contract_number ? `№ ${item.contract_number}` : 'Не привязан'}</strong></div>
          <div><span>Лицензия</span><strong>{licenseStatus ? `Лицензия (${licenseStatus})` : 'Не привязана'}</strong></div>
          {licenseTermYears != null && (
            <div><span>Срок действия лицензии</span><strong>{licenseTermYears} {(() => {
              const r10 = Math.abs(licenseTermYears) % 10;
              const r100 = Math.abs(licenseTermYears) % 100;
              if (r100 >= 11 && r100 <= 19) return 'лет';
              if (r10 === 1) return 'год';
              if (r10 >= 2 && r10 <= 4) return 'года';
              return 'лет';
            })()}</strong></div>
          )}
          {licenseSignedOn && (
            <div><span>Подписание лицензии</span><strong>{formatDate(licenseSignedOn)}</strong></div>
          )}
          <div><span>Ответственный</span><strong className="person-inline"><Avatar name={item.owner_name} small/>{item.owner_name}</strong></div>
          <div><span>Обновлено</span><strong>{formatDate(item.updated_at)}</strong></div>
        </div>
        {item.allowed_transitions && item.allowed_transitions.length > 0 && (
          <div className="action-block">
            <h3>Доступные действия</h3>
            <p>Выберите следующее действие для перевода карточки по жизненному циклу:</p>
            <div className="transitions-group">
              {item.allowed_transitions.map(t => {
                const action = getTransitionPresentation(t, workflow);
                return (
                  <Button
                    key={t.code}
                    variant={action.variant}
                    disabled={busy}
                    className={action.className}
                    onClick={() => handleTransitionClick(t)}
                  >
                    <Icon name={action.icon} size={16}/>
                    {action.title}
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
          {me.role === 'supervisor' && !isClosed && <><label className="field"><span>Передать менеджеру</span><select value={owner} onChange={event => setOwner(event.target.value)}><option value="">Выберите менеджера</option>{(catalogs.owners || []).filter(candidate => candidate.id !== item.owner_id).map(candidate => <option key={candidate.id} value={candidate.id}>{candidate.name}</option>)}</select></label><label className="field"><span>Причина передачи</span><textarea value={reason} onChange={event => setReason(event.target.value)} placeholder="Почему меняется ответственный" maxLength={5000}/></label><Button variant="secondary" disabled={busy || !reason.trim() || !owner || owner === item.owner_id} onClick={() => run(async () => { await api.post('/interactions/' + encodeURIComponent(id) + '/assignments', { owner_id: owner, expected_revision: item.revision, reason: reason.trim() }, makeMutationKey()); setReason(''); setOwner(''); }, 'Ответственный изменён')}>Передать карточку</Button></>}
        </section>
        <section className="panel side-panel"><div className="panel-heading"><div><h2>Комментарий</h2><p>Решение останется в истории</p></div><Icon name="message" size={20}/></div><textarea value={comment} onChange={event => setComment(event.target.value)} placeholder="Добавьте заметку…" maxLength={5000}/><Button variant="secondary" disabled={busy || !comment.trim()} onClick={() => run(async () => { await api.post('/interactions/' + encodeURIComponent(id) + '/comments', { body: comment.trim(), expected_revision: item.revision }, makeMutationKey()); setComment(''); }, 'Комментарий добавлен')}>Добавить комментарий</Button></section>
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
          {attachmentsList.map((att) => {
            const ext = att.file_name.split('.').pop()?.toLowerCase() || '';
            const isPreviewable = ['pdf', 'png', 'jpg', 'jpeg'].includes(ext);
            const canDelete = att.uploaded_by === me.id || ['supervisor', 'administrator', 'admin'].includes(me.role);

            return (
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
                <div className="file-actions" style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                  {isPreviewable && (
                    <Button
                      variant="secondary"
                      onClick={() => handleOpenPreview(att)}
                      title="Безопасный предпросмотр файла"
                    >
                      <Icon name="search" size={16} />Просмотр
                    </Button>
                  )}
                  <Button
                    variant="secondary"
                    onClick={() => handleDownloadAttachment(att)}
                    title="Авторизованное скачивание файла"
                  >
                    <Icon name="download" size={16} />Скачать
                  </Button>
                  {canDelete && (
                    <Button
                      variant="ghost"
                      style={{ color: '#D92D20' }}
                      onClick={() => { setDeleteError(null); setDeleteAttachmentTarget(att); }}
                      title="Удалить файл из карточки"
                    >
                      <Icon name="close" size={16} />Удалить
                    </Button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <p className="empty-inline" style={{ marginTop: '12px' }}>
          К данному взаимодействию ещё не прикреплены файлы и документы.
        </p>
      )}
    </section>

    {/* Интерактивный граф жизненного цикла карточки */}
    <WorkflowGraphView currentState={item.state} />

    <section className="panel timeline-panel">
      <div className="panel-heading" style={{ flexWrap: 'wrap', gap: '16px', alignItems: 'center' }}>
        <div>
          <span className="eyebrow">ИСТОРИЯ РЕШЕНИЙ</span>
          <h2>События и комментарии</h2>
        </div>
        <div className="inbox-tabs" role="tablist" aria-label="Фильтр истории">
          <button
            type="button"
            className={`inbox-tab-btn ${historyTab === 'all' ? 'active' : ''}`}
            onClick={() => setHistoryTab('all')}
            role="tab"
            aria-selected={historyTab === 'all'}
            title={`Всего ${formatTimelineCount(timelineEntries.length)}`}
          >
            <span>Все</span>
            <b>{allList.length}</b>
          </button>
          <button
            type="button"
            className={`inbox-tab-btn ${historyTab === 'comments' ? 'active' : ''}`}
            onClick={() => setHistoryTab('comments')}
            role="tab"
            aria-selected={historyTab === 'comments'}
            title={`Комментарии (${formatTimelineCount(commentsList.length)})`}
          >
            <span>Комментарии</span>
            <b>{commentsList.length}</b>
          </button>
          <button
            type="button"
            className={`inbox-tab-btn ${historyTab === 'stages' ? 'active' : ''}`}
            onClick={() => setHistoryTab('stages')}
            role="tab"
            aria-selected={historyTab === 'stages'}
            title={`Этапы (${formatTimelineCount(stagesList.length)})`}
          >
            <span>Этапы workflow</span>
            <b>{stagesList.length}</b>
          </button>
        </div>
      </div>
      {displayedTimeline.length > 0 ? (
        <div className="timeline">
          {displayedTimeline.map(entry => (
            <div className="timeline-item" key={entry.key}>
              <span className={`timeline-dot${entry.isComment ? ' tone-orange' : ''}`} />
              <div>
                <strong>{entry.title}</strong>
                <p>{entry.text}</p>
                <small>{entry.meta}</small>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="empty-inline">В этой категории пока нет записей.</p>
      )}
    </section>

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


    {deleteAttachmentTarget && (
      <DeleteAttachmentModal
        attachment={deleteAttachmentTarget}
        busy={deleting}
        error={deleteError}
        onClose={() => setDeleteAttachmentTarget(null)}
        onConfirm={handleDeleteAttachment}
      />
    )}
  </>;
}

