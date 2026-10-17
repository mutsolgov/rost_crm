import { useState, useEffect, type FormEvent } from 'react';
import { useAuth } from '../auth';
import type { ApiClient } from '../api';
import type { Workflow, WorkflowVersionInfo } from '../types';
import { Button, ErrorAlert, Icon, Modal } from '../ui';

export interface WorkflowStateMeta {
  code: string;
  name: string;
  kind: 'working' | 'terminal';
  step?: number;
  phase: string;
  description: string;
  x: number;
  y: number;
}

export const WORKFLOW_STATES: WorkflowStateMeta[] = [
  // Phase 1: Контакт и потребность (x: 40)
  { code: 'contact_search', name: '1. Поиск контактов', kind: 'working', step: 1, phase: 'Инициация', description: 'Поиск контактов ответственного в вузе.', x: 40, y: 70 },
  { code: 'needs_clarification', name: '2. Уточнение потребности', kind: 'working', step: 2, phase: 'Инициация', description: 'Коммуникация с ответственным и уточнение программ по ИТ-направлениям.', x: 260, y: 70 },
  { code: 'meeting', name: '3. Встреча с вузом', kind: 'working', step: 3, phase: 'Инициация', description: 'Организация и проведение встречи с представителями вуза.', x: 480, y: 70 },

  // Phase 2: Документооборот (x: 40, y: 170)
  { code: 'document_exchange', name: '4. Обмен документами', kind: 'working', step: 4, phase: 'Договоры', description: 'Обмен необходимым пакетом документов для подписания.', x: 480, y: 170 },
  { code: 'document_revision', name: '5. Корректировка', kind: 'working', step: 5, phase: 'Договоры', description: 'Опциональная корректировка документов перед подписанием.', x: 260, y: 170 },
  { code: 'document_signing', name: '6. Подписание документов', kind: 'working', step: 6, phase: 'Договоры', description: 'Подписание пакета договоров и соглашений.', x: 40, y: 170 },

  // Phase 3: Внедрение и обучение (x: 40, y: 270)
  { code: 'materials_transfer', name: '7. Передача материалов', kind: 'working', step: 7, phase: 'Внедрение', description: 'Передача обучающих материалов, лицензии ИТ-продукта и документации.', x: 40, y: 270 },
  { code: 'deployment', name: '8. Сопровождение', kind: 'working', step: 8, phase: 'Внедрение', description: 'Сопровождение внедрения ИТ-продуктов в вузе.', x: 260, y: 270 },
  { code: 'teacher_training', name: '9. Обучение преподавателей', kind: 'working', step: 9, phase: 'Обучение', description: 'Обучение преподавателей вуза работе с продуктом.', x: 480, y: 270 },

  // Phase 4: Учебный процесс (x: 40, y: 370)
  { code: 'curriculum_update', name: '10. Актуализация программы', kind: 'working', step: 10, phase: 'Учебный процесс', description: 'Актуализация учебной программы по ИТ-направлению с учётом обучения.', x: 480, y: 370 },
  { code: 'classes', name: '11. Ведение занятий', kind: 'working', step: 11, phase: 'Учебный процесс', description: 'Ведение учебных занятий со студентами.', x: 260, y: 370 },
  { code: 'materials_update', name: '12. Обновление материалов', kind: 'working', step: 12, phase: 'Развитие', description: 'Актуализация документации по продукту и материалам.', x: 40, y: 370 },
  { code: 'teacher_upskilling', name: '13. Повышение квалификации', kind: 'working', step: 13, phase: 'Развитие', description: 'Повышение квалификации преподавателей (допускает возврат к занятиям).', x: 40, y: 470 },

  // Phase 5: Финальные исходы (x: 350 / 550, y: 470)
  { code: 'completed', name: 'Завершено успешно', kind: 'terminal', phase: 'Финал', description: 'Взаимодействие успешно завершено, все цели достигнуты.', x: 300, y: 470 },
  { code: 'cancelled', name: 'Отменено', kind: 'terminal', phase: 'Финал', description: 'Взаимодействие отменено на одном из этапов.', x: 500, y: 470 },
];

export interface EditableStage {
  code: string;
  name: string;
  kind: 'working' | 'terminal';
  step?: number;
  is_optional?: boolean;
}

export function generateDefinitionFromStages(stages: EditableStage[], version: number, name: string) {
  const workingStages = stages.filter(s => s.kind === 'working');
  const terminalStages = stages.filter(s => s.kind === 'terminal');

  const formattedStates = [
    ...workingStages.map((s, idx) => ({
      code: s.code,
      name: s.name,
      kind: 'working' as const,
      step: idx + 1,
    })),
    ...terminalStages.map(s => ({
      code: s.code,
      name: s.name,
      kind: 'terminal' as const,
    })),
  ];

  const transitions: any[] = [];
  for (let i = 0; i < workingStages.length - 1; i++) {
    const fromS = workingStages[i];
    const toS = workingStages[i + 1];
    transitions.push({
      code: `${fromS.code}_to_${toS.code}`,
      from: fromS.code,
      to: toS.code,
      kind: 'forward',
      comment_required: false,
      condition_refs: [],
    });
  }

  for (let i = 1; i < workingStages.length - 1; i++) {
    if (workingStages[i].is_optional) {
      const prevS = workingStages[i - 1];
      const nextS = workingStages[i + 1];
      transitions.push({
        code: `skip_${workingStages[i].code}`,
        from: prevS.code,
        to: nextS.code,
        kind: 'forward',
        comment_required: false,
        condition_refs: [],
      });
    }
  }

  const lastWorking = workingStages[workingStages.length - 1];
  if (lastWorking && terminalStages.some(t => t.code === 'completed')) {
    transitions.push({
      code: `${lastWorking.code}_to_completed`,
      from: lastWorking.code,
      to: 'completed',
      kind: 'forward',
      comment_required: false,
      condition_refs: [],
    });
  }

  if (terminalStages.some(t => t.code === 'cancelled')) {
    for (const ws of workingStages) {
      transitions.push({
        code: `cancel_from_${ws.code}`,
        from: ws.code,
        to: 'cancelled',
        kind: 'cancel',
        comment_required: true,
        condition_refs: [],
      });
    }
  }

  return {
    schema_version: '1.0',
    template_code: `rtk_custom_v${version}`,
    version,
    name,
    initial_state: workingStages[0]?.code || 'contact_search',
    states: formattedStates,
    transitions,
  };
}

function getDefaultDefinition(version: number, name: string) {
  return {
    schema_version: '1.0',
    template_code: `rtk_custom_v${version}`,
    version,
    name,
    initial_state: 'contact_search',
    states: [
      { code: 'contact_search', name: '1. Поиск контактов', kind: 'working', step: 1 },
      { code: 'needs_clarification', name: '2. Уточнение потребности', kind: 'working', step: 2 },
      { code: 'meeting', name: '3. Встреча с вузом', kind: 'working', step: 3 },
      { code: 'document_signing', name: '4. Подписание документов', kind: 'working', step: 4 },
      { code: 'completed', name: 'Завершено успешно', kind: 'terminal' },
      { code: 'cancelled', name: 'Отменено', kind: 'terminal' },
    ],
    transitions: [
      {
        code: 'contact_to_needs',
        from: 'contact_search',
        to: 'needs_clarification',
        kind: 'forward',
        comment_required: false,
        condition_refs: [],
      },
      {
        code: 'needs_to_meeting',
        from: 'needs_clarification',
        to: 'meeting',
        kind: 'forward',
        comment_required: false,
        condition_refs: [],
      },
      {
        code: 'meeting_to_signing',
        from: 'meeting',
        to: 'document_signing',
        kind: 'forward',
        comment_required: false,
        condition_refs: [],
      },
      {
        code: 'signing_to_completed',
        from: 'document_signing',
        to: 'completed',
        kind: 'forward',
        comment_required: false,
        condition_refs: [],
      },
      {
        code: 'cancel_from_contact',
        from: 'contact_search',
        to: 'cancelled',
        kind: 'cancel',
        comment_required: true,
        condition_refs: [],
      },
    ],
  };
}

export interface WorkflowGraphViewProps {
  currentState?: string;
  onSelectState?: (stateCode: string) => void;
  compact?: boolean;
  api?: ApiClient;
  defaultVersion?: number;
}

export function WorkflowGraphView({
  currentState,
  onSelectState,
  compact = false,
  api,
  defaultVersion = 1,
}: WorkflowGraphViewProps) {
  const auth = useAuth();
  const effectiveApi = api || auth?.api;
  const me = auth?.me;
  const isAdmin = me?.role === 'administrator' || me?.role === 'admin';

  const [versions, setVersions] = useState<WorkflowVersionInfo[]>([]);
  const [selectedVersion, setSelectedVersion] = useState<number>(defaultVersion);
  const [workflowData, setWorkflowData] = useState<Workflow | null>(null);
  const [selectedCode, setSelectedCode] = useState<string | null>(currentState || null);

  const [loading, setLoading] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [publishSuccess, setPublishSuccess] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);

  // Workflow version creation modal state
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [createVersion, setCreateVersion] = useState<number>(3);
  const [createName, setCreateName] = useState('');
  const [createDescription, setCreateDescription] = useState('');
  const [createDefinitionJson, setCreateDefinitionJson] = useState('');
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<unknown>(null);
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [editorMode, setEditorMode] = useState<'visual' | 'json'>('visual');
  const [editableStages, setEditableStages] = useState<EditableStage[]>([]);

  function updateStagesAndSyncJson(newStages: EditableStage[]) {
    setEditableStages(newStages);
    const def = generateDefinitionFromStages(newStages, createVersion, createName);
    setCreateDefinitionJson(JSON.stringify(def, null, 2));
    setJsonError(null);
  }

  function handleMoveStageUp(idx: number) {
    const working = editableStages.filter(s => s.kind === 'working');
    if (idx <= 0 || idx >= working.length) return;
    const newWorking = [...working];
    const temp = newWorking[idx - 1];
    newWorking[idx - 1] = newWorking[idx];
    newWorking[idx] = temp;
    const terminals = editableStages.filter(s => s.kind === 'terminal');
    updateStagesAndSyncJson([...newWorking, ...terminals]);
  }

  function handleMoveStageDown(idx: number) {
    const working = editableStages.filter(s => s.kind === 'working');
    if (idx < 0 || idx >= working.length - 1) return;
    const newWorking = [...working];
    const temp = newWorking[idx + 1];
    newWorking[idx + 1] = newWorking[idx];
    newWorking[idx] = temp;
    const terminals = editableStages.filter(s => s.kind === 'terminal');
    updateStagesAndSyncJson([...newWorking, ...terminals]);
  }

  function handleStageNameChange(code: string, newName: string) {
    const updated = editableStages.map(s => s.code === code ? { ...s, name: newName } : s);
    updateStagesAndSyncJson(updated);
  }

  function handleStageCodeChange(oldCode: string, newCode: string) {
    const cleanCode = newCode.trim().toLowerCase().replace(/[^a-z0-9_]/g, '_');
    const updated = editableStages.map(s => s.code === oldCode ? { ...s, code: cleanCode } : s);
    updateStagesAndSyncJson(updated);
  }

  function handleToggleOptional(code: string, isOpt: boolean) {
    const updated = editableStages.map(s => s.code === code ? { ...s, is_optional: isOpt } : s);
    updateStagesAndSyncJson(updated);
  }

  function handleAddStage() {
    const working = editableStages.filter(s => s.kind === 'working');
    const terminals = editableStages.filter(s => s.kind === 'terminal');
    const newIndex = working.length + 1;
    const newCode = `stage_custom_${newIndex}_${Date.now().toString().slice(-4)}`;
    const newStage: EditableStage = {
      code: newCode,
      name: `${newIndex}. Новый этап процесса`,
      kind: 'working',
      step: newIndex,
      is_optional: false,
    };
    updateStagesAndSyncJson([...working, newStage, ...terminals]);
  }

  function handleDeleteStage(code: string) {
    if (code === 'contact_search' || code === 'completed' || code === 'cancelled') return;
    const updated = editableStages.filter(s => s.code !== code);
    updateStagesAndSyncJson(updated);
  }

  function handleSwitchMode(targetMode: 'visual' | 'json') {
    if (targetMode === 'visual') {
      try {
        const parsed = JSON.parse(createDefinitionJson);
        if (parsed && Array.isArray(parsed.states)) {
          const mapped: EditableStage[] = parsed.states.map((s: any) => ({
            code: s.code,
            name: s.name,
            kind: s.kind || (['completed', 'cancelled'].includes(s.code) ? 'terminal' : 'working'),
            step: s.step,
            is_optional: false,
          }));
          setEditableStages(mapped);
        }
      } catch (err) {
        setJsonError('Не удалось синхронизировать визуальный конструктор: невалидный JSON.');
        return;
      }
    } else {
      const def = generateDefinitionFromStages(editableStages, createVersion, createName);
      setCreateDefinitionJson(JSON.stringify(def, null, 2));
    }
    setEditorMode(targetMode);
    setJsonError(null);
  }

  function handleOpenCreateModal() {
    const nextV = versions.length > 0 ? Math.max(...versions.map(v => v.version)) + 1 : 3;
    const initialName = `Оптимизированный процесс v${nextV}`;
    setCreateVersion(nextV);
    setCreateName(initialName);
    setCreateDescription(`Пользовательская версия процесса v${nextV}`);
    const defaultDef = getDefaultDefinition(nextV, initialName);
    const initialStages: EditableStage[] = defaultDef.states.map((s: any) => ({
      code: s.code,
      name: s.name,
      kind: s.kind as 'working' | 'terminal',
      step: s.step,
      is_optional: false,
    }));
    setEditableStages(initialStages);
    setEditorMode('visual');
    setCreateDefinitionJson(JSON.stringify(defaultDef, null, 2));
    setCreateError(null);
    setJsonError(null);
    setCreateModalOpen(true);
  }

  async function handleCreateSubmit(e: FormEvent) {
    e.preventDefault();
    if (!effectiveApi) return;
    setJsonError(null);
    setCreateError(null);

    let parsedDef: Record<string, unknown>;
    try {
      const rawJson = editorMode === 'visual'
        ? JSON.stringify(generateDefinitionFromStages(editableStages, createVersion, createName))
        : createDefinitionJson;
      parsedDef = JSON.parse(rawJson);
      if (!parsedDef || typeof parsedDef !== 'object' || Array.isArray(parsedDef)) {
        throw new Error('Ожидается JSON-объект в структуре definition.');
      }
    } catch (err: unknown) {
      setJsonError(err instanceof Error ? err.message : 'Некорректный синтаксис JSON.');
      return;
    }

    parsedDef.version = Number(createVersion);
    parsedDef.name = createName.trim();

    setCreating(true);
    try {
      await effectiveApi.post('/workflow/versions', {
        version: Number(createVersion),
        name: createName.trim(),
        description: createDescription.trim() || undefined,
        definition: parsedDef,
      });

      const updatedList = await effectiveApi.getWorkflowVersions();
      if (updatedList && updatedList.length > 0) {
        setVersions(updatedList);
      }
      setSelectedVersion(Number(createVersion));
      setCreateModalOpen(false);
    } catch (err) {
      setCreateError(err);
    } finally {
      setCreating(false);
    }
  }

  // Load versions list dynamically from GET /api/v1/workflow/versions
  useEffect(() => {
    if (!effectiveApi) return;
    let cancelled = false;
    (async () => {
      try {
        const list = await effectiveApi.getWorkflowVersions();
        if (!cancelled && list && list.length > 0) {
          setVersions(list);
        }
      } catch (err) {
        // Fallback gracefully to default if versions endpoint has issues
        console.warn('Workflow versions load warning:', err);
      }
    })();
    return () => { cancelled = true; };
  }, [effectiveApi]);

  // Load selected workflow version definition from GET /api/v1/workflow?version=X
  useEffect(() => {
    if (!effectiveApi) return;
    let cancelled = false;
    setLoading(true);
    setPublishSuccess(null);
    setError(null);
    (async () => {
      try {
        const wf = await effectiveApi.getWorkflow(selectedVersion);
        if (!cancelled && wf) {
          setWorkflowData(wf);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [effectiveApi, selectedVersion]);

  useEffect(() => {
    if (defaultVersion) {
      setSelectedVersion(defaultVersion);
    }
  }, [defaultVersion]);

  useEffect(() => {
    if (currentState) {
      setSelectedCode(currentState);
    }
  }, [currentState]);

  // Handle version publishing for administrators via POST /api/v1/workflow/versions/{version}/publish
  async function handlePublish() {
    if (!effectiveApi || !selectedVersion) return;
    setPublishing(true);
    setError(null);
    setPublishSuccess(null);
    try {
      await effectiveApi.publishWorkflowVersion(selectedVersion);
      setPublishSuccess(`Версия v${selectedVersion} успешно опубликована.`);
      setVersions(prev => prev.map(v => v.version === selectedVersion ? { ...v, is_published: true } : v));
      const wf = await effectiveApi.getWorkflow(selectedVersion);
      if (wf) setWorkflowData(wf);
    } catch (err) {
      setError(err);
    } finally {
      setPublishing(false);
    }
  }

  // Combine dynamic states from API with layout coordinates
  const statesToRender: WorkflowStateMeta[] = (workflowData?.states || WORKFLOW_STATES).map((st, idx) => {
    const existingMeta = WORKFLOW_STATES.find(s => s.code === st.code);
    const sourceStep = ('source_step' in st ? st.source_step : undefined) ?? ('step' in st ? st.step : undefined);
    if (existingMeta) {
      return {
        ...existingMeta,
        name: st.name || existingMeta.name,
        kind: (st.kind as 'working' | 'terminal') || existingMeta.kind,
        step: sourceStep ?? existingMeta.step ?? (idx + 1),
      };
    }
    const col = idx % 3;
    const row = Math.floor(idx / 3);
    return {
      code: st.code,
      name: st.name,
      kind: (st.kind as 'working' | 'terminal') || 'working',
      step: sourceStep ?? (idx + 1),
      phase: st.kind === 'terminal' ? 'Финал' : `Фаза ${row + 1}`,
      description: `Этап ${st.name} (${st.code})`,
      x: 40 + col * 220,
      y: 70 + row * 100,
    };
  });

  const selectedState = statesToRender.find(s => s.code === (selectedCode || currentState));
  const activeState = statesToRender.find(s => s.code === currentState);
  const currentVersionMeta = versions.find(v => v.version === selectedVersion);
  const canPublish = isAdmin && currentVersionMeta && !currentVersionMeta.is_published;

  const nodeWidth = 190;
  const nodeHeight = 56;

  return (
    <div className="workflow-graph-card">
      <div className="panel-heading" style={{ marginBottom: '14px', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <span className="eyebrow">АРХИТЕКТУРА ПРОЦЕССА</span>
          <h2 style={{ margin: '4px 0' }}>
            {workflowData ? workflowData.name : 'Граф жизненного цикла'} (версия v{selectedVersion})
          </h2>
          <p style={{ margin: 0, fontSize: '12px', color: 'var(--rtk-color-muted)' }}>
            {statesToRender.filter(s => s.kind !== 'terminal').length} рабочих этапов и {statesToRender.filter(s => s.kind === 'terminal').length} терминальных состояния
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
          {/* Version Selector Dropdown */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <label htmlFor="workflow-version-dropdown" style={{ fontSize: '12px', fontWeight: 600, color: 'var(--rtk-color-muted)' }}>
              Версия:
            </label>
            <select
              id="workflow-version-dropdown"
              value={selectedVersion}
              onChange={(e) => setSelectedVersion(Number(e.target.value))}
              disabled={loading || publishing}
              style={{
                padding: '5px 10px',
                borderRadius: 'var(--rtk-radius-md, 8px)',
                border: '1px solid var(--rtk-color-border, #E2E5EB)',
                fontSize: '12px',
                fontWeight: 600,
                background: 'var(--rtk-color-card, #FFFFFF)',
                color: 'var(--rtk-color-text, #101828)',
                cursor: 'pointer',
              }}
            >
              {versions.length > 0 ? (
                versions
                  .filter(v => isAdmin || v.is_published)
                  .map((v) => (
                    <option key={v.version} value={v.version}>
                      v{v.version} {v.name ? `(${v.name})` : ''} {v.is_published ? '✓ Опубликована' : '· Черновик'}
                    </option>
                  ))
              ) : (
                <>
                  <option value={1}>v1 (Базовый процесс 04-base-workflow)</option>
                  <option value={2}>v2 (Оптимизированный процесс)</option>
                </>
              )}
            </select>
          </div>

          {/* Admin Create Version Button */}
          {isAdmin && (
            <Button
              variant="secondary"
              disabled={loading || publishing || creating}
              onClick={handleOpenCreateModal}
              style={{ fontSize: '11px', padding: '5px 12px', height: 'auto' }}
              title="Создать новую версию процесса"
            >
              <Icon name="plus" size={14} />+ Создать версию процесса
            </Button>
          )}

          {/* Admin Publish Button */}
          {canPublish && (
            <Button
              variant="primary"
              disabled={publishing || loading}
              onClick={handlePublish}
              style={{ fontSize: '11px', padding: '5px 12px', height: 'auto' }}
            >
              {publishing ? <span className="spinner small" /> : <Icon name="check" size={14} />}
              Опубликовать версию
            </Button>
          )}

          {activeState && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '11px', color: 'var(--rtk-color-muted)' }}>Текущий статус:</span>
              <span
                className="quiet-badge"
                style={{
                  background: currentState === 'completed'
                    ? 'var(--rtk-color-success-bg)'
                    : currentState === 'cancelled'
                    ? 'var(--rtk-color-danger-bg)'
                    : 'var(--rtk-color-primary-subtle)',
                  color: currentState === 'completed'
                    ? 'var(--rtk-color-success)'
                    : currentState === 'cancelled'
                    ? 'var(--rtk-color-danger)'
                    : 'var(--rtk-color-primary-text)',
                  fontWeight: 700,
                }}
              >
                {activeState.name}
              </span>
            </div>
          )}
        </div>
      </div>

      {canPublish && (
        <div className="info-note" style={{ marginBottom: '14px' }}>
          <Icon name="alert" size={16} />
          <span>
            Версия v{selectedVersion} находится в статусе черновика. Чтобы граф стал доступен в системе, нажмите «Опубликовать версию».
          </span>
        </div>
      )}

      <ErrorAlert error={error} />
      {publishSuccess && (
        <div className="success-alert" style={{ marginBottom: '14px' }}>
          <Icon name="check" size={16} />
          {publishSuccess}
        </div>
      )}

      <div className="workflow-scroll-hint" role="note">
        <Icon name="info" size={15} />
        <span>Сдвиньте вправо для просмотра всех 14 этапов →</span>
      </div>

      <div className="workflow-graph-scroll">
        <svg
          viewBox="0 0 720 550"
          className="workflow-graph-svg"
          style={{ minWidth: compact ? '500px' : '680px', maxHeight: compact ? '400px' : '520px' }}
        >
          <defs>
            {/* Arrow marker for forward transitions */}
            <marker
              id="arrow-forward"
              viewBox="0 0 10 10"
              refX="8"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#8068c8" />
            </marker>

            {/* Arrow marker for active paths */}
            <marker
              id="arrow-active"
              viewBox="0 0 10 10"
              refX="8"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#FF4F12" />
            </marker>

            {/* Arrow marker for rework / loops */}
            <marker
              id="arrow-rework"
              viewBox="0 0 10 10"
              refX="8"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#DC6803" />
            </marker>

            {/* Arrow marker for cancellation */}
            <marker
              id="arrow-cancel"
              viewBox="0 0 10 10"
              refX="8"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#D92D20" />
            </marker>

            {/* Filter for glowing active node */}
            <filter id="glow-active" x="-20%" y="-20%" width="140%" height="140%">
              <feDropShadow dx="0" dy="0" stdDeviation="4" floodColor="#7700FF" floodOpacity="0.4" />
            </filter>
            <filter id="glow-accent" x="-20%" y="-20%" width="140%" height="140%">
              <feDropShadow dx="0" dy="0" stdDeviation="4" floodColor="#FF4F12" floodOpacity="0.5" />
            </filter>
          </defs>

          {/* Connectors (Edges) */}
          {/* Phase 1: 1 -> 2 -> 3 */}
          <line x1="230" y1="98" x2="256" y2="98" stroke="#B9AED9" strokeWidth="2" markerEnd="url(#arrow-forward)" />
          <line x1="450" y1="98" x2="476" y2="98" stroke="#B9AED9" strokeWidth="2" markerEnd="url(#arrow-forward)" />

          {/* Phase 1 to 2: 3 -> 4 */}
          <line x1="575" y1="126" x2="575" y2="166" stroke="#B9AED9" strokeWidth="2" markerEnd="url(#arrow-forward)" />

          {/* Phase 2: 4 -> 5 -> 6 and 4 -> 6 (skip) */}
          <line x1="480" y1="198" x2="454" y2="198" stroke="#B9AED9" strokeWidth="2" markerEnd="url(#arrow-forward)" />
          <line x1="260" y1="198" x2="234" y2="198" stroke="#B9AED9" strokeWidth="2" markerEnd="url(#arrow-forward)" />
          {/* 6 -> 5 Rework loop */}
          <path d="M 135 170 C 135 140, 355 140, 355 166" fill="none" stroke="#DC6803" strokeWidth="1.5" strokeDasharray="4 3" markerEnd="url(#arrow-rework)" />

          {/* Phase 2 to 3: 6 -> 7 */}
          <line x1="135" y1="226" x2="135" y2="266" stroke="#B9AED9" strokeWidth="2" markerEnd="url(#arrow-forward)" />

          {/* Phase 3: 7 -> 8 -> 9 */}
          <line x1="230" y1="298" x2="256" y2="298" stroke="#B9AED9" strokeWidth="2" markerEnd="url(#arrow-forward)" />
          <line x1="450" y1="298" x2="476" y2="298" stroke="#B9AED9" strokeWidth="2" markerEnd="url(#arrow-forward)" />

          {/* Phase 3 to 4: 9 -> 10 */}
          <line x1="575" y1="326" x2="575" y2="366" stroke="#B9AED9" strokeWidth="2" markerEnd="url(#arrow-forward)" />

          {/* Phase 4: 10 -> 11 -> 12 */}
          <line x1="480" y1="398" x2="454" y2="398" stroke="#B9AED9" strokeWidth="2" markerEnd="url(#arrow-forward)" />
          <line x1="260" y1="398" x2="234" y2="398" stroke="#B9AED9" strokeWidth="2" markerEnd="url(#arrow-forward)" />

          {/* 12 -> 13 */}
          <line x1="135" y1="426" x2="135" y2="466" stroke="#B9AED9" strokeWidth="2" markerEnd="url(#arrow-forward)" />

          {/* 13 -> 11 Cycle loop */}
          <path d="M 230 498 C 280 498, 355 450, 355 430" fill="none" stroke="#DC6803" strokeWidth="1.5" strokeDasharray="4 3" markerEnd="url(#arrow-rework)" />

          {/* 13 -> Completed */}
          <line x1="230" y1="498" x2="296" y2="498" stroke="#039855" strokeWidth="2" markerEnd="url(#arrow-forward)" />

          {/* Cancellation branch to 15 */}
          <path d="M 670 198 L 690 198 L 690 498 L 644 498" fill="none" stroke="#D92D20" strokeWidth="1.5" strokeDasharray="3 3" markerEnd="url(#arrow-cancel)" />

          {/* Render State Nodes */}
          {statesToRender.map((state) => {
            const isCurrent = currentState === state.code;
            const isSelected = selectedState?.code === state.code;
            const isCompleted = state.code === 'completed';
            const isCancelled = state.code === 'cancelled';

            let bgColor = '#FFFFFF';
            let strokeColor = '#E2E5EB';
            let textColor = '#101828';
            let strokeWidth = 1.5;
            let filter: string | undefined = undefined;

            if (isCurrent) {
              bgColor = '#FFF0EB';
              strokeColor = '#FF4F12';
              strokeWidth = 2.5;
              textColor = '#101828';
              filter = 'url(#glow-accent)';
            } else if (isCompleted) {
              bgColor = '#ECFDF3';
              strokeColor = '#039855';
              textColor = '#027A48';
            } else if (isCancelled) {
              bgColor = '#FEF3F2';
              strokeColor = '#D92D20';
              textColor = '#B42318';
            } else if (isSelected) {
              strokeColor = '#7700FF';
              strokeWidth = 2;
              filter = 'url(#glow-active)';
            }

            return (
              <g
                key={state.code}
                transform={`translate(${state.x}, ${state.y})`}
                style={{ cursor: 'pointer' }}
                onClick={() => {
                  setSelectedCode(state.code);
                  if (onSelectState) onSelectState(state.code);
                }}
              >
                {/* Node Box */}
                <rect
                  width={nodeWidth}
                  height={nodeHeight}
                  rx="10"
                  ry="10"
                  fill={bgColor}
                  stroke={strokeColor}
                  strokeWidth={strokeWidth}
                  filter={filter}
                />

                {/* Current Stage Indicator Dot */}
                {isCurrent && (
                  <circle cx="15" cy="20" r="5" fill="#FF4F12">
                    <animate attributeName="r" values="4;6;4" dur="1.5s" repeatCount="indefinite" />
                  </circle>
                )}

                {/* State Title */}
                <text
                  x={isCurrent ? 26 : 14}
                  y="24"
                  fill={textColor}
                  fontSize="12"
                  fontWeight={isCurrent ? '700' : '600'}
                  fontFamily="inherit"
                >
                  {state.name}
                </text>

                {/* Phase / Code Subtitle */}
                <text
                  x="14"
                  y="42"
                  fill={isCurrent ? '#FF4F12' : '#667085'}
                  fontSize="10"
                  fontWeight="500"
                  fontFamily="inherit"
                >
                  {isCurrent ? '● ТЕКУЩИЙ ЭТАП' : `${state.phase} · ${state.code}`}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      {/* Selected State Details Drawer */}
      {selectedState && (
        <div className="workflow-state-details">
          <div>
            <div className="workflow-state-header">
              <span className="eyebrow">{selectedState.phase.toUpperCase()}</span>
              <strong style={{ fontSize: '14px' }}>{selectedState.name}</strong>
              <code style={{ fontSize: '11px', color: 'var(--rtk-color-muted)' }}>({selectedState.code})</code>
            </div>
            <p style={{ margin: 0, fontSize: '12px', color: 'var(--rtk-color-muted)' }}>
              {selectedState.description}
            </p>
          </div>
          <div className="workflow-state-badge-group">
            {selectedState.kind === 'terminal' ? (
              <span
                className="format-badge"
                style={{
                  background: selectedState.code === 'completed' ? '#ECFDF3' : '#FEE4E2',
                  color: selectedState.code === 'completed' ? '#039855' : '#D92D20',
                }}
              >
                Терминальный исход
              </span>
            ) : (
              <span className="quiet-badge">Шаг {selectedState.step} из 13</span>
            )}
          </div>
        </div>
      )}

      {/* Workflow Version Creation Modal */}
      {createModalOpen && (
        <Modal
          title="Создание версии процесса"
          subtitle="Добавление новой архитектуры жизненного цикла и графа переходов"
          onClose={() => !creating && setCreateModalOpen(false)}
          busy={creating}
          wide
        >
          <form onSubmit={handleCreateSubmit}>
            <div className="modal-body">
              <ErrorAlert error={createError} />
              <div className="form-grid">
                <label className="field">
                  <span>Номер версии <b>*</b></span>
                  <input
                    type="number"
                    min="1"
                    value={createVersion}
                    onChange={e => setCreateVersion(Number(e.target.value))}
                    required
                    disabled={creating}
                  />
                </label>
                <label className="field span-2">
                  <span>Название <b>*</b></span>
                  <input
                    type="text"
                    value={createName}
                    onChange={e => setCreateName(e.target.value)}
                    placeholder="Например: Оптимизированный процесс v3"
                    required
                    maxLength={255}
                    disabled={creating}
                  />
                </label>
              </div>

              <label className="field">
                <span>Описание</span>
                <input
                  type="text"
                  value={createDescription}
                  onChange={e => setCreateDescription(e.target.value)}
                  placeholder="Краткое описание версии процесса"
                  maxLength={1000}
                  disabled={creating}
                />
              </label>

              {/* Mode Switcher */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', margin: '14px 0 8px' }}>
                <span style={{ fontWeight: 600, fontSize: '13px' }}>Архитектура этапов процесса:</span>
                <div style={{ display: 'flex', gap: '6px' }}>
                  <Button
                    type="button"
                    variant={editorMode === 'visual' ? 'primary' : 'secondary'}
                    onClick={() => handleSwitchMode('visual')}
                    style={{ fontSize: '12px', padding: '4px 10px' }}
                  >
                    Визуальный конструктор
                  </Button>
                  <Button
                    type="button"
                    variant={editorMode === 'json' ? 'primary' : 'secondary'}
                    onClick={() => handleSwitchMode('json')}
                    style={{ fontSize: '12px', padding: '4px 10px' }}
                  >
                    JSON-схема
                  </Button>
                </div>
              </div>

              {editorMode === 'visual' ? (
                <div className="visual-stage-editor" style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <div style={{ maxHeight: '320px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '8px', paddingRight: '4px' }}>
                    {editableStages.filter(s => s.kind === 'working').map((stage, wIdx, wArr) => {
                      const isFirst = wIdx === 0;
                      const isLast = wIdx === wArr.length - 1;
                      const isProtected = stage.code === 'contact_search';

                      return (
                        <div
                          key={stage.code}
                          className="stage-editor-card"
                          style={{
                            display: 'flex',
                            flexDirection: 'column',
                            gap: '6px',
                            padding: '10px 12px',
                            background: 'var(--rtk-color-surface-subtle, #F8FAFC)',
                            border: '1px solid var(--rtk-color-border-subtle, #E2E8F0)',
                            borderRadius: '8px',
                          }}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                              <span
                                style={{
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  justifyContent: 'center',
                                  width: '24px',
                                  height: '24px',
                                  borderRadius: '50%',
                                  background: '#FF4F12',
                                  color: '#fff',
                                  fontSize: '11px',
                                  fontWeight: 700,
                                }}
                              >
                                {wIdx + 1}
                              </span>
                              <input
                                type="text"
                                value={stage.name}
                                onChange={(e) => handleStageNameChange(stage.code, e.target.value)}
                                placeholder="Наименование этапа"
                                style={{ fontWeight: 600, fontSize: '13px', padding: '4px 8px', width: '260px' }}
                              />
                              <input
                                type="text"
                                value={stage.code}
                                onChange={(e) => handleStageCodeChange(stage.code, e.target.value)}
                                placeholder="Код (slug)"
                                disabled={isProtected}
                                style={{ fontSize: '11px', fontFamily: 'monospace', padding: '4px 8px', width: '160px', color: isProtected ? 'var(--rtk-color-muted)' : 'inherit' }}
                              />
                            </div>
                            <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
                              <Button
                                type="button"
                                variant="ghost"
                                onClick={() => handleMoveStageUp(wIdx)}
                                disabled={isFirst}
                                style={{ padding: '2px 6px', fontSize: '12px' }}
                                title="Переместить вверх"
                              >
                                ↑
                              </Button>
                              <Button
                                type="button"
                                variant="ghost"
                                onClick={() => handleMoveStageDown(wIdx)}
                                disabled={isLast}
                                style={{ padding: '2px 6px', fontSize: '12px' }}
                                title="Переместить вниз"
                              >
                                ↓
                              </Button>
                              {!isProtected && (
                                <Button
                                  type="button"
                                  variant="ghost"
                                  onClick={() => handleDeleteStage(stage.code)}
                                  style={{ color: '#D92D20', padding: '2px 6px', fontSize: '12px' }}
                                  title="Удалить этап"
                                >
                                  ✕
                                </Button>
                              )}
                            </div>
                          </div>
                          {!isFirst && !isLast && (
                            <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', color: 'var(--rtk-color-muted)' }}>
                              <input
                                type="checkbox"
                                checked={!!stage.is_optional}
                                onChange={(e) => handleToggleOptional(stage.code, e.target.checked)}
                              />
                              Опциональный шаг (возможность пропуска этапа в процессе)
                            </label>
                          )}
                        </div>
                      );
                    })}

                    {/* Terminal States (Read-only summary) */}
                    <div style={{ display: 'flex', gap: '8px', marginTop: '4px' }}>
                      {editableStages.filter(s => s.kind === 'terminal').map(t => (
                        <div
                          key={t.code}
                          style={{
                            flex: 1,
                            padding: '8px 12px',
                            background: t.code === 'completed' ? '#ECFDF3' : '#FEE4E2',
                            color: t.code === 'completed' ? '#039855' : '#D92D20',
                            borderRadius: '6px',
                            fontSize: '11px',
                            fontWeight: 600,
                            display: 'flex',
                            alignItems: 'center',
                            gap: '6px',
                          }}
                        >
                          <span>{t.code === 'completed' ? '✓' : '✕'}</span>
                          <span>{t.name} (терминальный статус)</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div style={{ marginTop: '8px' }}>
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={handleAddStage}
                      style={{ fontSize: '12px' }}
                    >
                      <Icon name="plus" size={14} />
                      Добавить этап процесса
                    </Button>
                  </div>
                </div>
              ) : (
                <label className="field">
                  <span>JSON-структура этапов и переходов (definition) <b>*</b></span>
                  <textarea
                    value={createDefinitionJson}
                    onChange={e => {
                      setCreateDefinitionJson(e.target.value);
                      setJsonError(null);
                    }}
                    rows={12}
                    style={{ fontFamily: 'monospace', fontSize: '12px', whiteSpace: 'pre' }}
                    required
                    disabled={creating}
                  />
                </label>
              )}
              {jsonError && (
                <div style={{ color: 'var(--rtk-color-danger, #D92D20)', fontSize: '12px', marginTop: '4px' }}>
                  {jsonError}
                </div>
              )}
            </div>

            <div className="modal-actions">
              <Button
                variant="secondary"
                type="button"
                onClick={() => setCreateModalOpen(false)}
                disabled={creating}
              >
                Отмена
              </Button>
              <Button type="submit" disabled={creating}>
                {creating ? (
                  <>
                    <span className="spinner small" />
                    Создание…
                  </>
                ) : (
                  <>
                    <Icon name="plus" size={16} />
                    Создать версию процесса
                  </>
                )}
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
