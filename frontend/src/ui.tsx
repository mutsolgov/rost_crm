import { useEffect, useId, useRef } from 'react';
import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { ApiError, messageOf } from './api';

export function Icon({ name, size = 20, className = '' }: { name: string; size?: number; className?: string }) {
  const paths: Record<string, ReactNode> = {
    grid: <><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></>,
    layers: <><path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="m3 12 9 5 9-5M3 16l9 5 9-5"/></>,
    chart: <><path d="M4 3v17h17M8 15v-4M13 15V7M18 15v-7"/></>,
    book: <><path d="M12 5v16M3 4h5c2 0 4 1 4 3 0-2 2-3 4-3h5v15h-5c-2 0-4 1-4 2 0-1-2-2-4-2H3V4Z"/></>,
    help: <><circle cx="12" cy="12" r="9"/><path d="M9.4 8.5a2.7 2.7 0 0 1 5.2 1c0 2-2.6 2-2.6 4M12 17h.01"/></>,
    plus: <path d="M12 5v14M5 12h14"/>,
    search: <><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/></>,
    arrow: <path d="M5 12h14m-6-6 6 6-6 6"/>,
    back: <path d="M19 12H5m6-6-6 6 6 6"/>,
    chevron: <path d="m9 5 7 7-7 7"/>,
    down: <path d="m6 9 6 6 6-6"/>,
    close: <path d="m6 6 12 12M6 18 18 6"/>,
    check: <path d="m5 12 4 4L19 6"/>,
    building: <><path d="M5 21V5l7-3 7 3v16M3 21h18M10 21v-5h4v5M8 7h1m6 0h1M8 11h1m6 0h1"/></>,
    users: <><circle cx="9" cy="8" r="3"/><path d="M3 20v-2a6 6 0 0 1 12 0v2M16 5a3 3 0 0 1 0 6M17 15a5 5 0 0 1 4 5"/></>,
    clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
    file: <><path d="M14 3H5v18h14V8l-5-5ZM14 3v6h5M8 13h8M8 17h5"/></>,
    download: <><path d="M12 3v12m-4-4 4 4 4-4M4 16v5h16v-5"/></>,
    logout: <><path d="M9 4H4v16h5M13 8l4 4-4 4M8 12h13"/></>,
    menu: <path d="M4 6h16M4 12h16M4 18h16"/>,
    refresh: <><path d="M20 10a8 8 0 0 0-14-5L3 8m0-5v5h5M4 14a8 8 0 0 0 14 5l3-3m0 5v-5h-5"/></>,
    shield: <><path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z"/><path d="m8 12 3 3 5-6"/></>,
    alert: <><path d="m12 3 10 18H2L12 3ZM12 9v5M12 17h.01"/></>,
    message: <><path d="M21 4H3v13h5l4 4v-4h9V4Z"/><path d="M7 8h10M7 12h6"/></>,
    filter: <><path d="M4 6h16M7 12h10M10 18h4"/><circle cx="8" cy="6" r="1"/><circle cx="15" cy="12" r="1"/></>,
    external: <><path d="M13 4h7v7M20 4 10 14M10 4H4v16h16v-6"/></>,
    spark: <path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z"/>,
  };
  return <svg className={className} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] || paths.file}</svg>;
}

export function Brand({ compact = false }: { compact?: boolean }) {
  return <div className={'brand ' + (compact ? 'brand-compact' : '')}>
    <span className="brand-mark" aria-hidden="true"><i/><b/></span>
    <span><strong>ИТ Школа</strong><small>Партнёры</small></span>
  </div>;
}

export function Button({ variant = 'primary', className = '', children, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'ghost' | 'danger'; children: ReactNode }) {
  return <button className={'button button-' + variant + ' ' + className} {...props}>{children}</button>;
}

export function ErrorAlert({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  if (!error) return null;
  const requestId = error instanceof ApiError ? error.requestId : undefined;
  const code = error instanceof ApiError ? error.code : undefined;
  const details = error instanceof ApiError ? error.details : null;
  return <div className="error-alert" role="alert">
    <Icon name="alert" size={19}/>
    <div><strong>{typeof error === 'string' ? error : messageOf(error)}</strong>
      {(code || requestId) && <small>{code}{requestId ? ' · Запрос ' + requestId : ''}</small>}
      {details != null && <details><summary>Подробности проверки</summary><pre>{typeof details === 'string' ? details : JSON.stringify(details, null, 2)}</pre></details>}
    </div>
    {onRetry && <Button variant="ghost" onClick={onRetry}><Icon name="refresh" size={16}/>Повторить</Button>}
  </div>;
}

export function Loading({ label = 'Загружаем данные…' }: { label?: string }) {
  return <div className="loading-state" role="status"><span className="spinner"/><span>{label}</span></div>;
}

export function EmptyState({ title, description, action, icon = 'layers' }: { title: string; description: string; action?: ReactNode; icon?: string }) {
  return <div className="empty-state"><span className="empty-icon"><Icon name={icon} size={28}/></span><h3>{title}</h3><p>{description}</p>{action}</div>;
}

export function Avatar({ name, small = false }: { name: string; small?: boolean }) {
  const initials = name.trim().split(/\s+/).slice(0, 2).map(part => part[0]).join('');
  return <span className={'avatar ' + (small ? 'avatar-small' : '')} aria-hidden="true">{initials || '—'}</span>;
}

export function StageBadge({ code, name }: { code: string; name: string }) {
  let tone = 'purple';
  if (code.startsWith('document') || code === 'materials_transfer') tone = 'orange';
  if (['deployment', 'teacher_training', 'curriculum_update'].includes(code)) tone = 'blue';
  if (['classes', 'materials_update', 'teacher_upskilling', 'completed'].includes(code)) tone = 'green';
  if (['cancelled', 'closed'].includes(code)) tone = 'gray';
  return <span className={'stage-badge tone-' + tone}><i/>{name}</span>;
}

export function Modal({ title, subtitle, children, onClose, busy = false, wide = false }: {
  title: string; subtitle?: string; children: ReactNode; onClose: () => void; busy?: boolean; wide?: boolean;
}) {
  const label = useId();
  const container = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const element = container.current;
    element?.querySelector<HTMLElement>('input, select, textarea, button')?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !busy) onCloseRef.current();
      if (event.key !== 'Tab' || !element) return;
      const focusable = Array.from(element.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], [tabindex="0"]'));
      const first = focusable[0], last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    document.addEventListener('keydown', keydown);
    return () => { document.body.style.overflow = overflow; document.removeEventListener('keydown', keydown); previous?.focus(); };
  }, [busy]);
  return <div className="modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget && !busy) onClose(); }}>
    <div ref={container} role="dialog" aria-modal="true" aria-labelledby={label} className={'modal ' + (wide ? 'modal-wide' : '')}>
      <div className="modal-heading"><div><h2 id={label}>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>
        <button className="icon-button" aria-label="Закрыть" disabled={busy} onClick={onClose}><Icon name="close"/></button>
      </div>
      {children}
    </div>
  </div>;
}

export function PageHeader({ eyebrow, title, description, action }: { eyebrow?: string; title: string; description?: string; action?: ReactNode }) {
  return <div className="page-heading"><div>{eyebrow && <div className="eyebrow">{eyebrow}</div>}<h1>{title}</h1>{description && <p>{description}</p>}</div>{action}</div>;
}
export function Count({ value }: { value: number }) { return <>{new Intl.NumberFormat('ru-RU').format(value)}</>; }
export function formatDate(value?: string | null, time = true): string {
  if (!value) return '—';
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return value;
  return date.toLocaleString('ru-RU', { day: '2-digit', month: 'short', year: 'numeric', ...(time ? { hour: '2-digit', minute: '2-digit' } : {}) });
}
export const roleNames: Record<string, string> = { manager: 'Менеджер', supervisor: 'Руководитель', administrator: 'Администратор' };
export const eventNames: Record<string, string> = {
  created: 'Создано взаимодействие', interaction_created: 'Создано взаимодействие',
  state_changed: 'Изменён этап', transition: 'Изменён этап',
  owner_changed: 'Назначен ответственный', assignment: 'Назначен ответственный',
  comment_added: 'Добавлен комментарий', comment: 'Добавлен комментарий',
  attachment_uploaded: 'Загружен файл', attachment_deleted: 'Удалён файл',
  delivery_recorded: 'Зафиксирована выдача ПО',
};

