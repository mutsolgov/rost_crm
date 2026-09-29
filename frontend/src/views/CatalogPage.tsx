import { useState, useRef, useEffect } from 'react';
import type { ApiClient } from '../api';
import { makeMutationKey } from '../api';
import { useAuth } from '../auth';
import { Button, ErrorAlert, Icon, Modal } from '../ui';
import type {
  Catalogs,
  Organization,
  ImportPreviewResponse,
  ImportCommitResponse,
  WorkflowMigrationPreview,
  WorkflowMigrationResult,
} from '../types';

export interface StateDefinition {
  code: string;
  name: string;
  kind: 'working' | 'terminal';
  step?: number;
  phase: string;
}

export const WORKFLOW_V1_STATES: StateDefinition[] = [
  { code: 'contact_search', name: '1. Поиск контактов', kind: 'working', step: 1, phase: 'Инициация' },
  { code: 'needs_clarification', name: '2. Уточнение потребности', kind: 'working', step: 2, phase: 'Инициация' },
  { code: 'meeting', name: '3. Встреча с вузом', kind: 'working', step: 3, phase: 'Инициация' },
  { code: 'document_exchange', name: '4. Обмен документами', kind: 'working', step: 4, phase: 'Договоры' },
  { code: 'document_revision', name: '5. Корректировка документов', kind: 'working', step: 5, phase: 'Договоры' },
  { code: 'document_signing', name: '6. Подписание документов', kind: 'working', step: 6, phase: 'Договоры' },
  { code: 'materials_transfer', name: '7. Передача материалов и лицензии', kind: 'working', step: 7, phase: 'Внедрение' },
  { code: 'deployment', name: '8. Сопровождение внедрения', kind: 'working', step: 8, phase: 'Внедрение' },
  { code: 'teacher_training', name: '9. Обучение преподавателей', kind: 'working', step: 9, phase: 'Внедрение' },
  { code: 'curriculum_update', name: '10. Актуализация учебной программы', kind: 'working', step: 10, phase: 'Учебный процесс' },
  { code: 'classes', name: '11. Ведение занятий', kind: 'working', step: 11, phase: 'Учебный процесс' },
  { code: 'materials_update', name: '12. Актуализация материалов', kind: 'working', step: 12, phase: 'Развитие' },
  { code: 'teacher_upskilling', name: '13. Повышение квалификации преподавателей', kind: 'working', step: 13, phase: 'Развитие' },
  { code: 'completed', name: 'Взаимодействие завершено', kind: 'terminal', phase: 'Финал' },
  { code: 'cancelled', name: 'Взаимодействие отменено', kind: 'terminal', phase: 'Финал' },
];

export const WORKFLOW_V2_STATES: StateDefinition[] = [
  { code: 'contact_search', name: '1. Поиск контактов', kind: 'working', step: 1, phase: 'Инициация' },
  { code: 'needs_clarification', name: '2. Уточнение потребности', kind: 'working', step: 2, phase: 'Инициация' },
  { code: 'meeting', name: '3. Встреча с вузом', kind: 'working', step: 3, phase: 'Инициация' },
  { code: 'document_exchange', name: '4. Обмен документами', kind: 'working', step: 4, phase: 'Договоры' },
  { code: 'document_revision', name: '5. Корректировка документов', kind: 'working', step: 5, phase: 'Договоры' },
  { code: 'document_signing', name: '6. Подписание документов', kind: 'working', step: 6, phase: 'Договоры' },
  { code: 'materials_transfer', name: '7. Передача материалов и лицензии', kind: 'working', step: 7, phase: 'Внедрение' },
  { code: 'deployment', name: '8. Сопровождение внедрения', kind: 'working', step: 8, phase: 'Внедрение' },
  { code: 'teacher_training', name: '9. Обучение преподавателей', kind: 'working', step: 9, phase: 'Внедрение' },
  { code: 'curriculum_update', name: '10. Актуализация учебной программы', kind: 'working', step: 10, phase: 'Учебный процесс' },
  { code: 'classes', name: '11. Ведение занятий', kind: 'working', step: 11, phase: 'Учебный процесс' },
  { code: 'materials_update', name: '12. Актуализация материалов', kind: 'working', step: 12, phase: 'Развитие' },
  { code: 'teacher_upskilling', name: '13. Повышение квалификации преподавателей', kind: 'working', step: 13, phase: 'Развитие' },
  { code: 'completed', name: 'Взаимодействие завершено', kind: 'terminal', phase: 'Финал' },
  { code: 'cancelled', name: 'Взаимодействие отменено', kind: 'terminal', phase: 'Финал' },
];

const DEFAULT_MAPPING: Record<string, string> = {
  contact_search: 'contact_search',
  needs_clarification: 'needs_clarification',
  meeting: 'meeting',
  document_exchange: 'document_exchange',
  document_revision: 'document_signing',
  document_signing: 'document_signing',
  materials_transfer: 'materials_transfer',
  deployment: 'deployment',
  teacher_training: 'teacher_training',
  curriculum_update: 'curriculum_update',
  classes: 'classes',
  materials_update: 'materials_update',
  teacher_upskilling: 'teacher_upskilling',
  completed: 'completed',
  cancelled: 'cancelled',
};

export function ImportWizardModal({
  api,
  onClose,
  onCompleted,
}: {
  api: ApiClient;
  onClose: () => void;
  onCompleted: () => void;
}) {
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [importType, setImportType] = useState<string>('auto');
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [previewData, setPreviewData] = useState<ImportPreviewResponse | null>(null);
  const [commitData, setCommitData] = useState<ImportCommitResponse | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [detectedTypeHint, setDetectedTypeHint] = useState<string | null>(null);

  const allowedExts = ['xlsx', 'xls', 'csv'];

  function validateAndSetFile(f: File) {
    setError(null);
    const ext = f.name.split('.').pop()?.toLowerCase() || '';
    if (!allowedExts.includes(ext)) {
      setError(`Недопустимый формат файла «.${ext}». Допустимы только файлы: XLSX, XLS, CSV.`);
      return;
    }
    if (f.size > 25 * 1024 * 1024) {
      setError(`Файл слишком большой (${(f.size / (1024 * 1024)).toFixed(1)} МБ). Лимит: 25 МБ.`);
      return;
    }
    setFile(f);

    const nameLower = f.name.toLowerCase();
    if (
      nameLower.includes('пользовател') ||
      nameLower.includes('слушател') ||
      nameLower.includes('learner') ||
      nameLower.includes('lms')
    ) {
      setDetectedTypeHint('lms_learners');
    } else if (importType === 'auto' && nameLower.includes('user')) {
      setDetectedTypeHint('Пользователи и ответственные сотрудники');
    } else {
      setDetectedTypeHint(null);
    }
  }

  const isLmsLearnersDetected =
    detectedTypeHint === 'lms_learners' ||
    previewData?.detected_type === 'lms_learners' ||
    (file ? (
      file.name.toLowerCase().includes('пользовател') ||
      file.name.toLowerCase().includes('слушател') ||
      file.name.toLowerCase().includes('learner') ||
      file.name.toLowerCase().includes('lms')
    ) : false);

  async function handlePreview() {
    if (!file) return;
    setLoading(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const qs = importType !== 'auto' ? `?import_type=${encodeURIComponent(importType)}` : '';
      const resp = await api.upload<ImportPreviewResponse>(`/imports/organizations/preview${qs}`, formData);
      setPreviewData(resp);
      setStep(2);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  async function rePreviewWithFormat(newType: string) {
    if (!file) return;
    setLoading(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const resp = await api.upload<ImportPreviewResponse>(
        `/imports/organizations/preview?import_type=${encodeURIComponent(newType)}`,
        formData
      );
      setPreviewData(resp);
      setImportType(newType);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  async function handleCommit() {
    if (!previewData && !file) return;
    setLoading(true);
    setError(null);
    try {
      const detected = previewData?.detected_type || (importType !== 'auto' ? importType : undefined);
      const qs = detected ? `?import_type=${encodeURIComponent(detected)}` : '';
      let resp: ImportCommitResponse;
      if (previewData && previewData.preview_rows && previewData.preview_rows.length > 0) {
        const validRows = previewData.preview_rows.filter(r => r.is_valid).map(r => (r as any).data || r);
        resp = await api.post<ImportCommitResponse>(
          `/imports/organizations/commit${qs}`,
          { rows: validRows },
          makeMutationKey()
        );
      } else if (file) {
        const formData = new FormData();
        formData.append('file', file);
        resp = await api.upload<ImportCommitResponse>(
          `/imports/organizations/commit${qs}`,
          formData,
          makeMutationKey()
        );
      } else {
        return;
      }
      setCommitData(resp);
      setStep(3);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Modal
      title="Мастер импорта каталогов"
      subtitle="Двухфазный импорт организаций, контактов и договоров из XLSX / CSV файлов"
      onClose={onClose}
      busy={loading}
      wide
    >
      <div className="modal-body" style={{ minHeight: '380px' }}>
        <div className="stepper">
          <div className={`stepper-step ${step === 1 ? 'active' : 'completed'}`}>
            <span className="stepper-badge">{step > 1 ? '✓' : '1'}</span>
            <span className="stepper-title">1. Выбор файла</span>
          </div>
          <div className={`stepper-line ${step > 1 ? 'completed' : ''}`} />
          <div className={`stepper-step ${step === 2 ? 'active' : step > 2 ? 'completed' : ''}`}>
            <span className="stepper-badge">{step > 2 ? '✓' : '2'}</span>
            <span className="stepper-title">2. Предпросмотр</span>
          </div>
          <div className={`stepper-line ${step > 2 ? 'completed' : ''}`} />
          <div className={`stepper-step ${step === 3 ? 'active' : ''}`}>
            <span className="stepper-badge">3</span>
            <span className="stepper-title">3. Применение</span>
          </div>
        </div>

        <ErrorAlert error={error} />

        {step === 1 && (
          <div>
            <div style={{ marginBottom: '14px' }}>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, marginBottom: '6px', color: '#344054' }}>
                Тип импортируемых данных
              </label>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '8px' }}>
                {[
                  { id: 'auto', label: 'Автоопределение', note: 'Вузы / Вендоры / Пользователи' },
                  { id: 'organizations', label: 'Организации / Вузы', note: '10-колоночный формат' },
                  { id: 'vendors', label: 'Вендоры и ПО', note: 'Вендоры.xlsx с продуктами' },
                  { id: 'users', label: 'Пользователи CRM', note: 'Загрузка пользователей.xlsx' },
                ].map(opt => (
                  <button
                    key={opt.id}
                    type="button"
                    onClick={() => {
                      setImportType(opt.id);
                      if (opt.id === 'auto' && file) {
                        const nameLower = file.name.toLowerCase();
                        if (nameLower.includes('пользовател') || nameLower.includes('user')) {
                          setDetectedTypeHint('Пользователи и ответственные сотрудники');
                        } else {
                          setDetectedTypeHint(null);
                        }
                      } else {
                        setDetectedTypeHint(null);
                      }
                    }}
                    style={{
                      padding: '10px 12px',
                      borderRadius: '8px',
                      textAlign: 'left',
                      border: importType === opt.id ? '2px solid var(--rtk-color-primary, #7700FF)' : '1px solid var(--rtk-color-border, #E4E7EC)',
                      background: importType === opt.id ? 'var(--rtk-color-primary-light, #F9F5FF)' : '#FFFFFF',
                      cursor: 'pointer',
                    }}
                  >
                    <div style={{ fontWeight: 600, fontSize: '13px', color: importType === opt.id ? 'var(--rtk-color-primary, #7700FF)' : '#101828' }}>
                      {opt.label}
                    </div>
                    <small style={{ fontSize: '11px', color: '#667085' }}>{opt.note}</small>
                  </button>
                ))}
              </div>
            </div>

            <div
              className={`dropzone ${isDragging ? 'active' : ''}`}
              onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setIsDragging(false);
                const dropped = e.dataTransfer.files?.[0];
                if (dropped) validateAndSetFile(dropped);
              }}
              onClick={() => fileInputRef.current?.click()}
            >
              <input
                type="file"
                ref={fileInputRef}
                style={{ display: 'none' }}
                accept=".xlsx,.xls,.csv"
                onChange={(e) => {
                  const sel = e.target.files?.[0];
                  if (sel) validateAndSetFile(sel);
                  e.target.value = '';
                }}
              />
              <div className="dropzone-icon">
                <Icon name="upload" size={24} />
              </div>
              <div className="dropzone-prompt">
                <strong>{file ? `Выбран файл: ${file.name}` : 'Перетащите таблицу импорта сюда'}</strong>
                <p>Поддерживаемые форматы: Microsoft Excel (.xlsx, .xls) и CSV (.csv)</p>
                <div className="dropzone-limit">
                  Автоматическое сопоставление колонок: Вузы, Вендоры, Продукты ПО, Пользователи CRM
                </div>
              </div>

              {file && (
                <div style={{ marginTop: '14px', display: 'flex', justifyContent: 'center', gap: '10px', alignItems: 'center' }}>
                  <span className="format-badge format-xls">
                    {file.name.split('.').pop()?.toUpperCase()}
                  </span>
                  <span style={{ fontSize: '12px', fontWeight: 600 }}>
                    {file.name} ({(file.size / 1024).toFixed(1)} КБ)
                  </span>
                  <Button
                    variant="ghost"
                    onClick={(e) => { e.stopPropagation(); setFile(null); setDetectedTypeHint(null); }}
                  >
                    Сменить
                  </Button>
                </div>
              )}
            </div>

            {isLmsLearnersDetected ? (
              <div
                className="warning-banner"
                style={{
                  marginTop: '14px',
                  background: 'var(--rtk-color-warning-bg, #FFFBEB)',
                  border: '1px solid #FCD34D',
                  padding: '16px',
                  borderRadius: '8px',
                }}
              >
                <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
                  <Icon name="alert" size={24} />
                  <div>
                    <strong style={{ fontSize: '14px', color: '#92400E' }}>
                      Распознан реестр слушателей LMS
                    </strong>
                    <p style={{ margin: '6px 0 12px', fontSize: '13px', color: '#B45309', lineHeight: 1.4 }}>
                      Распознан реестр слушателей LMS. Данные перенаправлены в подсистему Интеграций. Обучающиеся не добавляются в список сотрудников CRM и обрабатываются в очереди сверки.
                    </p>
                    <Button
                      variant="primary"
                      onClick={() => {
                        onClose();
                        window.location.hash = '#/integrations';
                      }}
                    >
                      <Icon name="arrow" size={16} />
                      Перейти в раздел «Интеграции»
                    </Button>
                  </div>
                </div>
              </div>
            ) : detectedTypeHint ? (
              <div
                className="info-note"
                style={{
                  marginTop: '14px',
                  background: 'var(--rtk-color-info-bg, #EFF8FF)',
                  border: '1px solid #B2DDFF',
                  color: '#175CD3',
                }}
              >
                <Icon name="users" size={16} />
                <p>
                  По имени файла автоматически распознан тип: <strong>{detectedTypeHint}</strong>
                </p>
              </div>
            ) : null}

            <div className="info-note" style={{ marginTop: '14px' }}>
              <Icon name="alert" size={16} />
              <p>
                На следующем шаге будет выполнен сухой прогон (Dry-Run): сервер проверит корректность всех полей и связей без изменения базы данных.
              </p>
            </div>
          </div>
        )}

        {step === 2 && previewData && (
          <div>
            {isLmsLearnersDetected && (
              <div
                className="warning-banner"
                style={{
                  marginBottom: '16px',
                  background: 'var(--rtk-color-warning-bg, #FFFBEB)',
                  border: '1px solid #FCD34D',
                  padding: '16px',
                  borderRadius: '8px',
                }}
              >
                <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
                  <Icon name="alert" size={24} />
                  <div>
                    <strong style={{ fontSize: '14px', color: '#92400E' }}>
                      Распознан реестр слушателей LMS
                    </strong>
                    <p style={{ margin: '6px 0 12px', fontSize: '13px', color: '#B45309', lineHeight: 1.4 }}>
                      Распознан реестр слушателей LMS. Данные перенаправлены в подсистему Интеграций. Обучающиеся не добавляются в список сотрудников CRM и обрабатываются в очереди сверки.
                    </p>
                    <Button
                      variant="primary"
                      onClick={() => {
                        onClose();
                        window.location.hash = '#/integrations';
                      }}
                    >
                      <Icon name="arrow" size={16} />
                      Перейти в раздел «Интеграции»
                    </Button>
                  </div>
                </div>
              </div>
            )}

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px', flexWrap: 'wrap', gap: '10px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <label
                  htmlFor="import-format-select"
                  style={{
                    fontSize: '12px',
                    fontWeight: 600,
                    color: 'var(--rtk-color-text-secondary, #475467)',
                    whiteSpace: 'nowrap',
                  }}
                >
                  Формат данных:
                </label>
                <select
                  id="import-format-select"
                  value={previewData.detected_type || 'organizations'}
                  onChange={(e) => rePreviewWithFormat(e.target.value)}
                  disabled={loading}
                  style={{
                    padding: '6px 12px',
                    fontSize: '12px',
                    fontWeight: 600,
                    borderRadius: 'var(--rtk-radius-md, 8px)',
                    border: '1px solid var(--rtk-color-border, #E2E5EB)',
                    background: 'var(--rtk-color-surface, #FFFFFF)',
                    color: 'var(--rtk-color-text, #101828)',
                    outline: 'none',
                    cursor: loading ? 'not-allowed' : 'pointer',
                  }}
                >
                  <option value="organizations">Образовательные организации (вузы, договоры)</option>
                  <option value="vendors">Вендоры и отечественное ПО</option>
                  <option value="users">Пользователи и ответственные сотрудники</option>
                  {previewData.detected_type === 'lms_learners' && (
                    <option value="lms_learners">Реестр слушателей LMS (контур интеграций)</option>
                  )}
                </select>
                {loading && <span className="spinner small" style={{ marginLeft: '4px' }} />}
              </div>
              <span style={{ fontSize: '12px', color: 'var(--rtk-color-muted)' }}>
                Проверено строк: {previewData.rows_total}
              </span>
            </div>

            <div className="import-summary-cards">
              <div className="import-summary-card total">
                <span className="eyebrow">ВСЕГО СТРОК</span>
                <strong>{previewData.rows_total}</strong>
              </div>
              <div className="import-summary-card valid">
                <span className="eyebrow">БЕЗ ОШИБОК</span>
                <strong>{previewData.valid_count}</strong>
              </div>
              <div className="import-summary-card error">
                <span className="eyebrow">С ОШИБКАМИ</span>
                <strong>{previewData.error_count}</strong>
              </div>
            </div>

            {previewData.errors && previewData.errors.length > 0 && (
              <div className="error-alert" style={{ marginBottom: '14px' }}>
                <Icon name="alert" size={18} />
                <div>
                  <strong>Обнаружены ошибки в строках импорта ({previewData.errors.length}):</strong>
                  <ul style={{ margin: '6px 0 0', paddingLeft: '18px', maxHeight: '100px', overflowY: 'auto' }}>
                    {previewData.errors.map((e: any, idx) => (
                      <li key={idx}>
                        {typeof e === 'string' ? e : `Строка ${e.row_index || e.row_number || idx + 1}: ${e.message || ''}`}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            )}

            {previewData.preview_rows && previewData.preview_rows.length > 0 && (
              <div className="table-scroll" style={{ maxHeight: '220px', border: '1px solid var(--rtk-color-border)', borderRadius: '8px' }}>
                <table className="data-table">
                  <thead>
                    {previewData.detected_type === 'vendors' ? (
                      <tr>
                        <th>Статус</th>
                        <th>Строка</th>
                        <th>Вендор</th>
                        <th>Продукты ПО</th>
                        <th>Контактное лицо</th>
                        <th>Контакты</th>
                      </tr>
                    ) : previewData.detected_type === 'users' ? (
                      <tr>
                        <th>Статус</th>
                        <th>Строка</th>
                        <th>ФИО</th>
                        <th>Email</th>
                        <th>Роль в CRM</th>
                        <th>Команда</th>
                      </tr>
                    ) : (
                      <tr>
                        <th>Статус</th>
                        <th>Строка</th>
                        <th>Организация</th>
                        <th>Тип</th>
                        <th>Контакт</th>
                        <th>Программа / Продукт</th>
                      </tr>
                    )}
                  </thead>
                  <tbody>
                    {previewData.preview_rows.map((row, idx) => {
                      const data = (row as any).data || (row as any).mapped_fields || row;
                      const isValid = row.is_valid;
                      const rowNum = (row as any).row_index || row.row_number || idx + 1;

                      if (previewData.detected_type === 'vendors') {
                        const vendor = data.vendor || data.name || row.organization_name || '—';
                        const prods = row.products || (data.products && Array.isArray(data.products) ? data.products : []) || [];
                        const contact = data.contact_name || row.contact_name || '—';
                        const pos = data.position || data.contact_position || '';
                        const contactInfo = [data.email || row.contact_email, data.phone || row.contact_phone].filter(Boolean).join(' · ');
                        return (
                          <tr key={idx}>
                            <td>
                              {isValid ? (
                                <span className="stage-badge tone-green"><i />Корректно</span>
                              ) : (
                                <span className="stage-badge tone-orange"><i />Ошибка</span>
                              )}
                            </td>
                            <td>{rowNum}</td>
                            <td><strong>{vendor}</strong></td>
                            <td>
                              {prods.length > 0 ? (
                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                                  {prods.map((p: string, pIdx: number) => (
                                    <span key={pIdx} className="stage-badge tone-purple" style={{ fontSize: '11px', padding: '2px 6px' }}>{p}</span>
                                  ))}
                                </div>
                              ) : (
                                <span>{data.product || data.product_name || '—'}</span>
                              )}
                            </td>
                            <td>
                              <div>{contact}</div>
                              {pos && <small style={{ color: 'var(--rtk-color-muted)' }}>{pos}</small>}
                            </td>
                            <td>
                              <small style={{ color: 'var(--rtk-color-muted)' }}>{contactInfo || '—'}</small>
                            </td>
                          </tr>
                        );
                      }

                      if (previewData.detected_type === 'users') {
                        const fullName = data.name || data.full_name || row.contact_name || '—';
                        const email = data.email || data.contact_email || '—';
                        const role = data.role || 'manager';
                        const team = data.team || '—';
                        return (
                          <tr key={idx}>
                            <td>
                              {isValid ? (
                                <span className="stage-badge tone-green"><i />Корректно</span>
                              ) : (
                                <span className="stage-badge tone-orange"><i />Ошибка</span>
                              )}
                            </td>
                            <td>{rowNum}</td>
                            <td><strong>{fullName}</strong></td>
                            <td>{email}</td>
                            <td>
                              <span className={`stage-badge ${role === 'supervisor' ? 'tone-orange' : role === 'administrator' ? 'tone-purple' : 'tone-blue'}`}>
                                {role === 'supervisor' ? 'Руководитель' : role === 'administrator' ? 'Администратор' : 'Менеджер'}
                              </span>
                            </td>
                            <td>{team}</td>
                          </tr>
                        );
                      }

                      const orgName = data.organization_name || data.name || (row as any).organization_name || '—';
                      const orgType = data.organization_type || data.org_type || data.type || (row as any).org_type || '—';
                      const contactName = data.contact_name || (row as any).contact_name || '—';
                      const contactInfo = data.contact_phone || data.phone || data.contact_email || data.email || '';
                      const progName = data.program_name || data.program || (row as any).program_name || '—';
                      const prodName = data.product_name || data.product || (row as any).product_name || '';
                      const vendorName = data.vendor || '';
                      const licenseInfo = data.license_term_years ? `${data.license_transfer_status || 'лицензия'} (${data.license_term_years} г.)` : '';
                      return (
                        <tr key={idx}>
                          <td>
                            {row.is_valid ? (
                              <span className="stage-badge tone-green"><i />Корректно</span>
                            ) : (
                              <span className="stage-badge tone-orange"><i />Ошибка</span>
                            )}
                          </td>
                          <td>{rowNum}</td>
                          <td><strong>{orgName}</strong></td>
                          <td>{orgType}</td>
                          <td>
                            <div>{contactName}</div>
                            {contactInfo && <small style={{ color: 'var(--rtk-color-muted)' }}>{contactInfo}</small>}
                            {data.manager && <small style={{ display: 'block', color: 'var(--rtk-color-muted)' }}>Менеджер: {data.manager}</small>}
                          </td>
                          <td>
                            <div>{progName}</div>
                            {(prodName || vendorName) && (
                              <small style={{ color: 'var(--rtk-color-muted)' }}>
                                {prodName}{vendorName ? ` (${vendorName})` : ''}
                              </small>
                            )}
                            {licenseInfo && <small style={{ display: 'block', color: 'var(--rtk-color-muted)' }}>{licenseInfo}</small>}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {step === 3 && commitData && (
          <div style={{ textAlign: 'center', padding: '30px 20px' }}>
            <div style={{ display: 'inline-flex', background: 'var(--rtk-color-success-bg)', color: 'var(--rtk-color-success)', padding: '16px', borderRadius: '50%', marginBottom: '16px' }}>
              <Icon name="check" size={32} />
            </div>
            <h2 style={{ fontSize: '20px', margin: '0 0 8px' }}>Импорт успешно применен!</h2>
            <p style={{ color: 'var(--rtk-color-muted)', maxWidth: '420px', margin: '0 auto 20px' }}>
              В базу данных записаны проверенные записи справочников и учетных записей.
            </p>
            <div className="import-summary-cards" style={{ maxWidth: '600px', margin: '0 auto' }}>
              {((commitData.created_organizations || 0) > 0 || (commitData.details?.organizations_created || 0) > 0) && (
                <div className="import-summary-card valid">
                  <span className="eyebrow">ОРГАНИЗАЦИЙ</span>
                  <strong>{commitData.created_organizations || commitData.details?.organizations_created || 0}</strong>
                </div>
              )}
              {((commitData.created_vendors || 0) > 0 || (commitData.details?.vendors_created || 0) > 0) && (
                <div className="import-summary-card valid">
                  <span className="eyebrow">ВЕНДОРОВ</span>
                  <strong>{commitData.created_vendors || commitData.details?.vendors_created || 0}</strong>
                </div>
              )}
              {((commitData.created_products || 0) > 0 || (commitData.details?.products_created || 0) > 0) && (
                <div className="import-summary-card total">
                  <span className="eyebrow">ПРОДУКТОВ ПО</span>
                  <strong>{commitData.created_products || commitData.details?.products_created || 0}</strong>
                </div>
              )}
              {((commitData.created_users || 0) > 0 || (commitData.details?.users_created || 0) > 0) && (
                <div className="import-summary-card valid">
                  <span className="eyebrow">ПОЛЬЗОВАТЕЛЕЙ</span>
                  <strong>{commitData.created_users || commitData.details?.users_created || 0}</strong>
                </div>
              )}
              {(commitData.created_contacts || 0) > 0 && (
                <div className="import-summary-card total">
                  <span className="eyebrow">КОНТАКТОВ</span>
                  <strong>{commitData.created_contacts}</strong>
                </div>
              )}
              {((commitData.created_licenses || 0) > 0 || (commitData.created_contracts || 0) > 0) && (
                <div className="import-summary-card valid">
                  <span className="eyebrow">ЛИЦЕНЗИЙ / ДОГОВОРОВ</span>
                  <strong>{(commitData.created_licenses || 0) + (commitData.created_contracts || 0)}</strong>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      <div className="modal-actions">
        {step === 1 && (
          <>
            <Button variant="ghost" onClick={onClose} disabled={loading}>
              Отмена
            </Button>
            <Button
              disabled={!file || loading}
              onClick={handlePreview}
            >
              {loading ? <span className="spinner small" /> : <Icon name="arrow" size={16} />}
              Далее: Проверить файл (Dry-Run)
            </Button>
          </>
        )}

        {step === 2 && (
          <>
            <Button variant="ghost" onClick={() => setStep(1)} disabled={loading}>
              <Icon name="back" size={16} />Назад
            </Button>
            {isLmsLearnersDetected ? (
              <Button
                variant="primary"
                onClick={() => {
                  onClose();
                  window.location.hash = '#/integrations';
                }}
              >
                <Icon name="arrow" size={16} />
                Перейти в раздел «Интеграции»
              </Button>
            ) : (
              <Button
                disabled={loading || !previewData || previewData.valid_count === 0}
                onClick={handleCommit}
              >
                {loading ? <span className="spinner small" /> : <Icon name="check" size={16} />}
                Применить импорт ({previewData?.valid_count || 0} записей)
              </Button>
            )}
          </>
        )}

        {step === 3 && (
          <Button onClick={onCompleted} disabled={loading}>
            <Icon name="check" size={16} />Завершить и обновить каталоги
          </Button>
        )}
      </div>
    </Modal>
  );
}

export function WorkflowMigratorModal({
  api,
  onClose,
  onCompleted,
}: {
  api: ApiClient;
  onClose: () => void;
  onCompleted: () => void;
}) {
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [fromVersion, setFromVersion] = useState<number>(1);
  const [toVersion, setToVersion] = useState<number>(2);
  const [statusMapping, setStatusMapping] = useState<Record<string, string>>({ ...DEFAULT_MAPPING });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [previewData, setPreviewData] = useState<WorkflowMigrationPreview | null>(null);
  const [commitResult, setCommitResult] = useState<WorkflowMigrationResult | null>(null);

  const fromStates = WORKFLOW_V1_STATES;
  const toStates = WORKFLOW_V2_STATES;
  const toTerminalCodes = new Set(toStates.filter(s => s.kind === 'terminal').map(s => s.code));

  // Inline validation: Terminal status mapped to working status is strictly prohibited!
  const validationErrors: Record<string, string> = {};
  for (const [srcCode, dstCode] of Object.entries(statusMapping)) {
    const srcState = fromStates.find(s => s.code === srcCode);
    if (srcState?.kind === 'terminal' && !toTerminalCodes.has(dstCode)) {
      validationErrors[srcCode] = `Терминальный статус «${srcState.name}» необратим и не может быть сопоставлен с рабочим статусом!`;
    }
  }

  const hasBlockingErrors = Object.keys(validationErrors).length > 0 || fromVersion === toVersion;

  function handleStatusChange(srcCode: string, targetCode: string) {
    setStatusMapping(prev => ({ ...prev, [srcCode]: targetCode }));
  }

  function handleResetDefault() {
    setStatusMapping({ ...DEFAULT_MAPPING });
    setError(null);
  }

  async function handlePreview() {
    if (hasBlockingErrors) return;
    setLoading(true);
    setError(null);
    try {
      const resp = await api.previewWorkflowMigration({
        from_version: fromVersion,
        to_version: toVersion,
        status_mapping: statusMapping,
      });
      setPreviewData(resp);
      setStep(2);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  async function handleCommit() {
    if (!previewData) return;
    setLoading(true);
    setError(null);
    try {
      const idempotencyKey = crypto.randomUUID();
      const resp = await api.commitWorkflowMigration(
        {
          from_version: fromVersion,
          to_version: toVersion,
          status_mapping: statusMapping,
        },
        idempotencyKey
      );
      setCommitResult(resp);
      setStep(3);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Modal
      title="Мигратор версий workflow"
      subtitle="Транзакционный перевод активных взаимодействий между версиями графа процессов (B17 / R06)"
      onClose={onClose}
      busy={loading}
      wide
    >
      <div className="modal-body" style={{ minHeight: '440px' }}>
        <div className="stepper">
          <div className={`stepper-step ${step === 1 ? 'active' : 'completed'}`}>
            <span className="stepper-badge">{step > 1 ? '✓' : '1'}</span>
            <span className="stepper-title">1. Матрица сопоставления</span>
          </div>
          <div className={`stepper-line ${step > 1 ? 'completed' : ''}`} />
          <div className={`stepper-step ${step === 2 ? 'active' : step > 2 ? 'completed' : ''}`}>
            <span className="stepper-badge">{step > 2 ? '✓' : '2'}</span>
            <span className="stepper-title">2. Предпросмотр (Dry-Run)</span>
          </div>
          <div className={`stepper-line ${step > 2 ? 'completed' : ''}`} />
          <div className={`stepper-step ${step === 3 ? 'active' : ''}`}>
            <span className="stepper-badge">3</span>
            <span className="stepper-title">3. Применение</span>
          </div>
        </div>

        <ErrorAlert error={error} />

        {step === 1 && (
          <div>
            <div className="migration-version-selector">
              <div className="field">
                <span>Исходная версия workflow:</span>
                <select
                  value={fromVersion}
                  onChange={(e) => setFromVersion(Number(e.target.value))}
                  disabled={loading}
                >
                  <option value={1}>Версия 1 (Базовый граф — 15 этапов, 29 переходов)</option>
                  <option value={2}>Версия 2 (Оптимизированный граф процессов)</option>
                </select>
              </div>
              <div className="version-arrow">
                <Icon name="arrow" size={20} />
              </div>
              <div className="field">
                <span>Целевая версия workflow:</span>
                <select
                  value={toVersion}
                  onChange={(e) => setToVersion(Number(e.target.value))}
                  disabled={loading}
                >
                  <option value={2}>Версия 2 (Оптимизированный граф процессов)</option>
                  <option value={1}>Версия 1 (Базовый граф — 15 этапов)</option>
                </select>
              </div>
            </div>

            {fromVersion === toVersion && (
              <div className="warning-banner" style={{ margin: '10px 0' }}>
                <Icon name="alert" size={16} />
                <span>Исходная и целевая версии не должны совпадать. Выберите разные версии.</span>
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', margin: '16px 0 10px' }}>
              <div>
                <strong style={{ fontSize: '14px' }}>Матрица сопоставления статусов</strong>
                <p style={{ fontSize: '11px', color: 'var(--rtk-color-muted)', margin: '2px 0 0' }}>
                  Назначьте соответствие для каждого статуса версии {fromVersion} в версии {toVersion}.
                </p>
              </div>
              <Button variant="ghost" onClick={handleResetDefault} style={{ fontSize: '11px' }}>
                <Icon name="refresh" size={14} />
                Рекомендуемый маппинг
              </Button>
            </div>

            <div className="migration-matrix-wrapper">
              <table className="data-table migration-matrix-table">
                <thead>
                  <tr>
                    <th style={{ width: '42%' }}>Статус версии v{fromVersion}</th>
                    <th style={{ width: '6%', textAlign: 'center' }}></th>
                    <th style={{ width: '52%' }}>Целевой статус версии v{toVersion}</th>
                  </tr>
                </thead>
                <tbody>
                  {fromStates.map((src) => {
                    const hasErr = !!validationErrors[src.code];
                    const selectedTarget = statusMapping[src.code] || src.code;
                    return (
                      <tr key={src.code} className={hasErr ? 'row-error' : ''}>
                        <td>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <span className={`stage-chip ${src.kind === 'terminal' ? 'chip-terminal' : 'chip-working'}`}>
                              {src.kind === 'terminal' ? 'Терминальный' : src.phase}
                            </span>
                            <span style={{ fontWeight: 600, fontSize: '12px' }}>{src.name}</span>
                          </div>
                        </td>
                        <td style={{ textAlign: 'center', color: 'var(--rtk-color-muted)' }}>
                          →
                        </td>
                        <td>
                          <select
                            className={`migration-select ${hasErr ? 'input-error' : ''}`}
                            value={selectedTarget}
                            onChange={(e) => handleStatusChange(src.code, e.target.value)}
                            disabled={loading}
                          >
                            {toStates.map((dst) => (
                              <option key={dst.code} value={dst.code}>
                                {dst.name} {dst.kind === 'terminal' ? ' [Терминальный]' : ''}
                              </option>
                            ))}
                          </select>
                          {hasErr && (
                            <div className="field-error-message">
                              <Icon name="alert" size={14} />
                              <span>{validationErrors[src.code]}</span>
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div className="info-note" style={{ marginTop: '14px' }}>
              <Icon name="shield" size={16} />
              <p>
                <strong>Инвариант целостности:</strong> Терминальные статусы («Завершено», «Отменено») необратимы согласно ТЗ. Перевод терминальных карточек в активные статусы запрещен на уровне схемы валидации.
              </p>
            </div>
          </div>
        )}

        {step === 2 && previewData && (
          <div>
            <div className="import-summary-cards">
              <div className="import-summary-card total">
                <span className="eyebrow">ЗАТРОНУТО КАРТОЧЕК</span>
                <strong>{previewData.affected_interactions_count ?? previewData.affected_count ?? 0}</strong>
              </div>
              <div className="import-summary-card valid">
                <span className="eyebrow">СТАТУСОВ В МАППИНГЕ</span>
                <strong>{Object.keys(statusMapping).length}</strong>
              </div>
              <div className={`import-summary-card ${previewData.collisions.length > 0 ? 'error' : 'valid'}`}>
                <span className="eyebrow">КОЛЛИЗИЙ</span>
                <strong>{previewData.collisions.length}</strong>
              </div>
            </div>

            <div className="warning-banner" style={{ margin: '14px 0' }}>
              <Icon name="alert" size={20} />
              <div>
                <strong>Внимание! Операция миграции является необратимой.</strong>
                <p style={{ margin: '3px 0 0', fontSize: '11px', lineHeight: 1.4 }}>
                  Все активные взаимодействия версии {previewData.from_version} будут транзакционно переведены на версию {previewData.to_version} с инкрементом ревизии (CAS) и фиксацией темпорального события <code>workflow_migrated</code> в аудит-логе. Архивные терминальные карточки сохранят свой статус.
                </p>
              </div>
            </div>

            {previewData.collisions.length > 0 && (
              <div className="collision-panel">
                <strong>Обнаружено объединение статусов (коллизии):</strong>
                <ul className="collision-list">
                  {previewData.collisions.map((col, idx) => (
                    <li key={idx} className="collision-item">
                      <span className="badge-warning">Слияние</span>
                      <span>
                        Исходные статусы <strong>[{col.source_statuses.join(', ')}]</strong> будут переведены в один целевой статус <strong>«{col.target_name || col.target_status}»</strong>.
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div style={{ marginTop: '16px' }}>
              <strong style={{ fontSize: '13px', display: 'block', marginBottom: '8px' }}>
                Ожидаемое распределение карточек:
              </strong>
              <div className="table-scroll" style={{ maxHeight: '180px', border: '1px solid var(--rtk-color-border)', borderRadius: '8px' }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Целевой статус v{toVersion}</th>
                      <th style={{ textAlign: 'right' }}>Количество взаимодействий</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(previewData.status_distribution_after || {}).length > 0 ? (
                      Object.entries(previewData.status_distribution_after).map(([code, count]) => {
                        const s = toStates.find(st => st.code === code);
                        return (
                          <tr key={code}>
                            <td>
                              <strong>{s?.name || code}</strong>
                              <small style={{ display: 'block', color: 'var(--rtk-color-muted)' }}>{code}</small>
                            </td>
                            <td style={{ textAlign: 'right', fontWeight: 700 }}>{count} шт.</td>
                          </tr>
                        );
                      })
                    ) : (
                      <tr>
                        <td colSpan={2} style={{ textAlign: 'center', color: 'var(--rtk-color-muted)' }}>
                          Нет активных карточек для миграции в текущей базе
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {step === 3 && commitResult && (
          <div style={{ textAlign: 'center', padding: '24px 20px' }}>
            <div style={{ display: 'inline-flex', background: 'var(--rtk-color-success-bg)', color: 'var(--rtk-color-success)', padding: '16px', borderRadius: '50%', marginBottom: '16px' }}>
              <Icon name="check" size={36} />
            </div>
            <h2 style={{ fontSize: '22px', margin: '0 0 8px' }}>Миграция процессов успешно выполнена!</h2>
            <p style={{ color: 'var(--rtk-color-muted)', maxWidth: '460px', margin: '0 auto 20px', fontSize: '13px' }}>
              Все взаимодействия обновлены на версию {commitResult.to_version}. В аудит-логе для каждой карточки создано темпоральное событие <code>workflow_migrated</code>.
            </p>
            <div className="import-summary-cards" style={{ maxWidth: '420px', margin: '0 auto' }}>
              <div className="import-summary-card valid">
                <span className="eyebrow">ПЕРЕВЕДЕНО КАРТОЧЕК</span>
                <strong>{commitResult.migrated_count}</strong>
              </div>
              <div className="import-summary-card total">
                <span className="eyebrow">НОВАЯ ВЕРСИЯ</span>
                <strong>v{commitResult.to_version}</strong>
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="modal-actions">
        {step === 1 && (
          <>
            <Button variant="ghost" onClick={onClose} disabled={loading}>
              Отмена
            </Button>
            <Button
              disabled={hasBlockingErrors || loading}
              onClick={handlePreview}
            >
              {loading ? <span className="spinner small" /> : <Icon name="arrow" size={16} />}
              Далее: Предпросмотр (Dry-Run)
            </Button>
          </>
        )}

        {step === 2 && (
          <>
            <Button variant="ghost" onClick={() => setStep(1)} disabled={loading}>
              <Icon name="back" size={16} />Назад к маппингу
            </Button>
            <Button
              disabled={loading}
              onClick={handleCommit}
            >
              {loading ? <span className="spinner small" /> : <Icon name="check" size={16} />}
              Применить миграцию процессов (Commit)
            </Button>
          </>
        )}

        {step === 3 && (
          <Button onClick={onCompleted} disabled={loading}>
            <Icon name="check" size={16} />Завершить и обновить
          </Button>
        )}
      </div>
    </Modal>
  );
}

export function AssignOrganizationManagerModal({
  api,
  organization,
  owners,
  onClose,
  onSaved,
}: {
  api: ApiClient;
  organization: Organization;
  owners: { id: string; name: string; role?: string }[];
  onClose: () => void;
  onSaved: (orgId: string, newOwnerId: string | null) => void;
}) {
  const [selectedUserId, setSelectedUserId] = useState<string>(organization.owner_id || '');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const managerOptions = owners.filter(o => !o.role || o.role === 'manager');

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const newOwnerId = selectedUserId ? selectedUserId : null;
      await api.updateOrganization(organization.id, { owner_id: newOwnerId });
      onSaved(organization.id, newOwnerId);
      onClose();
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Modal
      title="Назначение ответственного менеджера"
      subtitle={`Организация: ${organization.name}`}
      onClose={onClose}
      busy={loading}
    >
      <form onSubmit={handleSubmit}>
        <div className="modal-body" style={{ minHeight: '160px' }}>
          <ErrorAlert error={error} />

          <div style={{ marginBottom: '16px' }}>
            <p style={{ fontSize: '13px', color: 'var(--rtk-color-text-secondary, #475467)', margin: '0 0 12px' }}>
              Выберите ответственного сотрудника (менеджера) для кураторства образовательной организации.
            </p>
            <div className="field">
              <span>Ответственный менеджер</span>
              <select
                value={selectedUserId}
                onChange={(e) => setSelectedUserId(e.target.value)}
                disabled={loading}
                style={{ width: '100%', padding: '8px 12px', borderRadius: '8px', border: '1px solid var(--rtk-color-border)' }}
              >
                <option value="">Без ответственного (снять назначение)</option>
                {managerOptions.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="info-note" style={{ fontSize: '12px' }}>
            <Icon name="shield" size={16} />
            <p>
              При назначении ответственного сотруднику автоматически выдаются права <code>OrganizationAccess(read_all=True, can_create=True)</code> для работы с карточками вуза.
            </p>
          </div>
        </div>

        <div className="modal-actions">
          <Button variant="ghost" onClick={onClose} disabled={loading}>
            Отмена
          </Button>
          <Button type="submit" disabled={loading}>
            {loading ? <span className="spinner small" /> : <Icon name="check" size={16} />}
            Сохранить
          </Button>
        </div>
      </form>
    </Modal>
  );
}

export function CatalogPage({
  catalogs,
  api,
  onChanged,
}: {
  catalogs: Catalogs;
  api?: ApiClient;
  onChanged?: () => void;
}) {
  const { me } = useAuth();
  const [importOpen, setImportOpen] = useState(false);
  const [migrationOpen, setMigrationOpen] = useState(false);
  const [selectedOrgForManager, setSelectedOrgForManager] = useState<Organization | null>(null);
  const [localOrganizations, setLocalOrganizations] = useState<Organization[]>(catalogs.organizations);

  useEffect(() => {
    setLocalOrganizations(catalogs.organizations);
  }, [catalogs.organizations]);

  const isPrivileged = !!(me && (me.role === 'supervisor' || me.role === 'administrator' || me.role === 'admin'));

  function handleManagerSaved(orgId: string, newOwnerId: string | null) {
    setLocalOrganizations(prev => prev.map(o => o.id === orgId ? { ...o, owner_id: newOwnerId } : o));
    if (onChanged) onChanged();
  }

  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">СПРАВОЧНАЯ ИНФОРМАЦИЯ</div>
          <h1>Справочники</h1>
          <p>Единые реестры организаций, программ, продуктов, договоров и ответственных.</p>
        </div>
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
          {api && isPrivileged && (
            <Button variant="secondary" onClick={() => setImportOpen(true)}>
              <Icon name="upload" size={17} />
              Импорт каталогов
            </Button>
          )}
          {api && isPrivileged && (
            <Button onClick={() => setMigrationOpen(true)}>
              <Icon name="refresh" size={17} />
              Миграция процессов
            </Button>
          )}
        </div>
      </div>

      <div className="reference-grid">
        <section className="panel reference-card" key="Организации" style={{ gridColumn: 'span 2' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
            <h2 style={{ margin: 0 }}>Организации</h2>
            <span className="quiet-badge">{localOrganizations.length} записей</span>
          </div>
          <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
            {localOrganizations.length ? (
              localOrganizations.map((item) => {
                const assignedOwner = catalogs.owners.find(o => o.id === item.owner_id);
                return (
                  <li
                    key={item.id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '10px 12px',
                      borderBottom: '1px solid var(--rtk-color-border, #E2E5EB)',
                      gap: '12px',
                      flexWrap: 'wrap',
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: 600, fontSize: '13px' }}>{item.name}</div>
                      <div style={{ fontSize: '11px', color: 'var(--rtk-color-muted)', marginTop: '2px', display: 'flex', gap: '8px', alignItems: 'center' }}>
                        <span className="stage-badge tone-blue" style={{ fontSize: '10px', padding: '1px 6px' }}>{item.type || 'вуз'}</span>
                        <span>
                          Ответственный:{' '}
                          {assignedOwner ? (
                            <strong style={{ color: 'var(--rtk-color-text)' }}>{assignedOwner.name}</strong>
                          ) : item.owner_id ? (
                            <strong style={{ color: 'var(--rtk-color-text)' }}>{item.owner_id}</strong>
                          ) : (
                            <span style={{ color: '#D92D20', fontStyle: 'italic' }}>Без ответственного</span>
                          )}
                        </span>
                      </div>
                    </div>
                    {isPrivileged && api && (
                      <Button
                        variant="secondary"
                        style={{ fontSize: '11px', padding: '4px 10px', height: 'auto' }}
                        onClick={() => setSelectedOrgForManager(item)}
                      >
                        <Icon name="users" size={13} />
                        {item.owner_id ? 'Сменить ответственного' : 'Назначить ответственного'}
                      </Button>
                    )}
                  </li>
                );
              })
            ) : (
              <li>Нет доступных записей</li>
            )}
          </ul>
        </section>

        <section className="panel reference-card" key="ИТ-программы">
          <h2>ИТ-программы</h2>
          <ul>
            {catalogs.programs.length ? (
              catalogs.programs.map((item) => <li key={item.id}>{item.name}</li>)
            ) : (
              <li>Нет доступных записей</li>
            )}
          </ul>
        </section>

        <section className="panel reference-card" key="ИТ-продукты">
          <h2>ИТ-продукты</h2>
          <ul>
            {catalogs.products.length ? (
              catalogs.products.map((item) => <li key={item.id}>{`${item.name} (${item.vendor})`}</li>)
            ) : (
              <li>Нет доступных записей</li>
            )}
          </ul>
        </section>

        <section className="panel reference-card" key="Ответственные">
          <h2>Ответственные</h2>
          <ul>
            {catalogs.owners.filter(o => !o.role || ['manager', 'supervisor', 'administrator', 'admin'].includes(o.role)).length ? (
              catalogs.owners
                .filter(o => !o.role || ['manager', 'supervisor', 'administrator', 'admin'].includes(o.role))
                .map((owner) => {
                  const roleLabel =
                    owner.role === 'supervisor'
                      ? 'Руководитель'
                      : owner.role === 'administrator' || owner.role === 'admin'
                      ? 'Администратор'
                      : 'Менеджер';
                  const roleTone =
                    owner.role === 'supervisor'
                      ? 'tone-orange'
                      : owner.role === 'administrator' || owner.role === 'admin'
                      ? 'tone-purple'
                      : 'tone-blue';
                  return (
                    <li
                      key={owner.id}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '6px 0',
                      }}
                    >
                      <span>{owner.name}</span>
                      <span className={`stage-badge ${roleTone}`} style={{ fontSize: '11px' }}>
                        <i />
                        {roleLabel}
                      </span>
                    </li>
                  );
                })
            ) : (
              <li>Нет доступных записей</li>
            )}
          </ul>
        </section>

        <section className="panel reference-card" key="Направления">
          <h2>Направления</h2>
          <ul>
            {(catalogs.directions || []).length ? (
              (catalogs.directions || []).map((item) => <li key={item.id}>{item.name}</li>)
            ) : (
              <li>Нет доступных записей</li>
            )}
          </ul>
        </section>

        <section className="panel reference-card" key="Договоры">
          <h2>Договоры</h2>
          <ul>
            {(catalogs.contracts || []).length ? (
              (catalogs.contracts || []).map((item) => <li key={item.id}>{`№ ${item.number} (${item.status})`}</li>)
            ) : (
              <li>Нет доступных записей</li>
            )}
          </ul>
        </section>

        <section className="panel reference-card" key="Лицензии ПО">
          <h2>Лицензии ПО</h2>
          <ul>
            {(catalogs.licenses || []).length ? (
              (catalogs.licenses || []).map((lic) => {
                const prod = (catalogs.products || []).find((p) => p.id === lic.product_id);
                const prodName = prod ? prod.name : 'ПО';
                const statusLabel =
                  lic.transfer_status === 'transferred'
                    ? 'Передана'
                    : lic.transfer_status === 'pending'
                    ? 'Ожидает'
                    : lic.transfer_status === 'revoked'
                    ? 'Отозвана'
                    : lic.transfer_status || 'Черновик';
                const statusTone =
                  lic.transfer_status === 'transferred'
                    ? 'tone-green'
                    : lic.transfer_status === 'pending'
                    ? 'tone-orange'
                    : 'tone-gray';
                return (
                  <li
                    key={lic.id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '6px 0',
                    }}
                  >
                    <span>
                      <strong>{prodName}</strong>
                      {lic.term_years ? ` · ${lic.term_years} ${lic.term_years === 1 ? 'год' : lic.term_years < 5 ? 'года' : 'лет'}` : ''}
                    </span>
                    <span className={`stage-badge ${statusTone}`} style={{ fontSize: '11px' }}>
                      <i />
                      {statusLabel}
                    </span>
                  </li>
                );
              })
            ) : (
              <li>Нет доступных записей</li>
            )}
          </ul>
        </section>
      </div>

      {importOpen && api && isPrivileged && (
        <ImportWizardModal
          api={api}
          onClose={() => setImportOpen(false)}
          onCompleted={() => {
            setImportOpen(false);
            if (onChanged) onChanged();
          }}
        />
      )}

      {migrationOpen && api && isPrivileged && (
        <WorkflowMigratorModal
          api={api}
          onClose={() => setMigrationOpen(false)}
          onCompleted={() => {
            setMigrationOpen(false);
            if (onChanged) onChanged();
          }}
        />
      )}

      {selectedOrgForManager && api && (
        <AssignOrganizationManagerModal
          api={api}
          organization={selectedOrgForManager}
          owners={catalogs.owners}
          onClose={() => setSelectedOrgForManager(null)}
          onSaved={handleManagerSaved}
        />
      )}
    </>
  );
}

export default CatalogPage;

