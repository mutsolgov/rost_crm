import { useState } from 'react';

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

export interface WorkflowGraphViewProps {
  currentState?: string;
  onSelectState?: (stateCode: string) => void;
  compact?: boolean;
}

export function WorkflowGraphView({
  currentState,
  onSelectState,
  compact = false,
}: WorkflowGraphViewProps) {
  const [selectedCode, setSelectedCode] = useState<string | null>(currentState || null);

  const selectedState = WORKFLOW_STATES.find(s => s.code === (selectedCode || currentState));
  const activeState = WORKFLOW_STATES.find(s => s.code === currentState);

  const nodeWidth = 190;
  const nodeHeight = 56;

  return (
    <div className="workflow-graph-card">
      <div className="panel-heading" style={{ marginBottom: '14px' }}>
        <div>
          <span className="eyebrow">АРХИТЕКТУРА ПРОЦЕССА</span>
          <h2 style={{ margin: '4px 0' }}>Граф жизненного цикла (15 этапов)</h2>
          <p style={{ margin: 0, fontSize: '12px', color: 'var(--rtk-color-muted)' }}>
            13 рабочих этапов воронки партнерства и 2 терминальных состояния (04-base-workflow.json)
          </p>
        </div>
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

      <div style={{ overflowX: 'auto', padding: '10px 0' }}>
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
          {WORKFLOW_STATES.map((state) => {
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
        <div
          style={{
            marginTop: '14px',
            padding: '14px 18px',
            background: 'var(--rtk-color-background)',
            borderRadius: 'var(--rtk-radius-md)',
            border: '1px solid var(--rtk-color-border)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: '16px',
            flexWrap: 'wrap',
          }}
        >
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
              <span className="eyebrow">{selectedState.phase.toUpperCase()}</span>
              <strong style={{ fontSize: '14px' }}>{selectedState.name}</strong>
              <code style={{ fontSize: '11px', color: 'var(--rtk-color-muted)' }}>({selectedState.code})</code>
            </div>
            <p style={{ margin: 0, fontSize: '12px', color: 'var(--rtk-color-muted)' }}>
              {selectedState.description}
            </p>
          </div>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
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
    </div>
  );
}
