import { useState, useRef } from 'react';
import type { ApiClient } from '../api';
import { makeMutationKey } from '../api';
import { useAuth } from '../auth';
import { Button, ErrorAlert, Icon, Modal } from '../ui';
import type {
  Catalogs,
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
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [previewData, setPreviewData] = useState<ImportPreviewResponse | null>(null);
  const [commitData, setCommitData] = useState<ImportCommitResponse | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

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
  }

  async function handlePreview() {
    if (!file) return;
    setLoading(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const resp = await api.upload<ImportPreviewResponse>('/imports/organizations/preview', formData);
      setPreviewData(resp);
      setStep(2);
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
      let resp: ImportCommitResponse;
      if (previewData && previewData.preview_rows && previewData.preview_rows.length > 0) {
        const validRows = previewData.preview_rows.filter(r => r.is_valid).map(r => (r as any).data || r);
        resp = await api.post<ImportCommitResponse>(
          '/imports/organizations/commit',
          { rows: validRows },
          makeMutationKey()
        );
      } else if (file) {
        const formData = new FormData();
        formData.append('file', file);
        resp = await api.upload<ImportCommitResponse>(
          '/imports/organizations/commit',
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
                  Автоматическое сопоставление колонок: Вуз, Тип, Контакт, Телефон, Программа, Продукт
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
                    onClick={(e) => { e.stopPropagation(); setFile(null); }}
                  >
                    Сменить
                  </Button>
                </div>
              )}
            </div>

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
                    {previewData.errors.map((e, idx) => (
                      <li key={idx}>
                        Строка {e.row_index}: {e.message}
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
                    <tr>
                      <th>Статус</th>
                      <th>Строка</th>
                      <th>Организация</th>
                      <th>Тип</th>
                      <th>Контакт</th>
                      <th>Программа / Продукт</th>
                    </tr>
                  </thead>
                  <tbody>
                    {previewData.preview_rows.map((row, idx) => {
                      const data = (row as any).data || row;
                      return (
                        <tr key={idx}>
                          <td>
                            {row.is_valid ? (
                              <span className="stage-badge tone-green"><i />Корректно</span>
                            ) : (
                              <span className="stage-badge tone-orange"><i />Ошибка</span>
                            )}
                          </td>
                          <td>{row.row_index}</td>
                          <td><strong>{data.organization_name || '—'}</strong></td>
                          <td>{data.organization_type || '—'}</td>
                          <td>
                            <div>{data.contact_name || '—'}</div>
                            <small style={{ color: 'var(--rtk-color-muted)' }}>{data.contact_phone || data.contact_email || ''}</small>
                          </td>
                          <td>
                            <div>{data.program_name || data.program_id || '—'}</div>
                            <small style={{ color: 'var(--rtk-color-muted)' }}>{data.product_name || data.product_id || ''}</small>
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
              В базу данных записаны проверенные организации, контакты и договоры.
            </p>
            <div className="import-summary-cards" style={{ maxWidth: '400px', margin: '0 auto' }}>
              <div className="import-summary-card valid">
                <span className="eyebrow">ИМПОРТИРОВАНО</span>
                <strong>{commitData.created_organizations || commitData.imported_rows || 0}</strong>
              </div>
              <div className="import-summary-card total">
                <span className="eyebrow">ОБНОВЛЕНО</span>
                <strong>{commitData.updated_organizations || 0}</strong>
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
            <Button
              disabled={loading || !previewData || previewData.valid_count === 0}
              onClick={handleCommit}
            >
              {loading ? <span className="spinner small" /> : <Icon name="check" size={16} />}
              Применить импорт ({previewData?.valid_count || 0} записей)
            </Button>
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

  const isPrivileged = me && (me.role === 'supervisor' || me.role === 'administrator' || me.role === 'admin');

  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">СПРАВОЧНАЯ ИНФОРМАЦИЯ</div>
          <h1>Справочники</h1>
          <p>Единые реестры организаций, программ, продуктов, договоров и ответственных.</p>
        </div>
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
          {api && (
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
        {[
          ['Организации', catalogs.organizations.map((item) => item.name)],
          ['ИТ-программы', catalogs.programs.map((item) => item.name)],
          ['ИТ-продукты', catalogs.products.map((item) => `${item.name} (${item.vendor})`)],
          ['Ответственные', catalogs.owners.map((item) => item.name)],
          ['Направления', (catalogs.directions || []).map((item) => item.name)],
          ['Договоры', (catalogs.contracts || []).map((item) => `№ ${item.number} (${item.status})`)],
        ].map(([title, entries]) => (
          <section className="panel reference-card" key={title as string}>
            <h2>{title as string}</h2>
            <ul>
              {(entries as string[]).length ? (
                (entries as string[]).map((entry) => <li key={entry}>{entry}</li>)
              ) : (
                <li>Нет доступных записей</li>
              )}
            </ul>
          </section>
        ))}
      </div>

      {importOpen && api && (
        <ImportWizardModal
          api={api}
          onClose={() => setImportOpen(false)}
          onCompleted={() => {
            setImportOpen(false);
            if (onChanged) onChanged();
          }}
        />
      )}

      {migrationOpen && api && (
        <WorkflowMigratorModal
          api={api}
          onClose={() => setMigrationOpen(false)}
          onCompleted={() => {
            setMigrationOpen(false);
            if (onChanged) onChanged();
          }}
        />
      )}
    </>
  );
}

export default CatalogPage;

