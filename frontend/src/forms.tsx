import { useState } from 'react';
import type { FormEvent } from 'react';
import type { ApiClient } from './api';
import { useMutationKey } from './hooks';
import { Button, ErrorAlert, Icon, Modal } from './ui';
import type { Catalogs, Interaction, User } from './types';

export function CreateInteractionModal({ api, catalogs, me, onClose, onSaved }: {
  api: ApiClient; catalogs: Catalogs; me: User; onClose: () => void; onSaved: (interaction: Interaction) => void;
}) {
  const [form, setForm] = useState({
    title: '', organization_id: '', program_id: '', product_id: '',
    cycle_label: '', owner_id: me.role === 'manager' ? me.id : '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const mutation = useMutationKey();
  const update = (field: keyof typeof form, value: string) => setForm(previous => ({ ...previous, [field]: value }));
  async function submit(event: FormEvent) {
    event.preventDefault(); setError(null); setSaving(true);
    const body = { ...form, title: form.title.trim(), cycle_label: form.cycle_label.trim(), program_id: form.program_id || null, product_id: form.product_id || null };
    try {
      const created = await api.post<Interaction>('/interactions', body, mutation.forBody(body));
      mutation.clear(); onSaved(created);
    } catch (problem) { setError(problem); }
    finally { setSaving(false); }
  }
  return <Modal title="Новое взаимодействие" subtitle="Отдельный цикл сотрудничества с образовательной организацией" onClose={onClose} busy={saving} wide>
    <form onSubmit={submit}>
      <div className="modal-body"><ErrorAlert error={error}/>
        <label className="field"><span>Название взаимодействия <b>*</b></span><input autoFocus value={form.title} onChange={event => update('title', event.target.value)} placeholder="Например: внедрение облачной платформы" required maxLength={250}/></label>
        <div className="form-grid">
          <label className="field span-2"><span>Образовательная организация <b>*</b></span><select value={form.organization_id} onChange={event => update('organization_id', event.target.value)} required><option value="">Выберите организацию</option>{catalogs.organizations.map(item => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
          <label className="field"><span>ИТ-программа</span><select value={form.program_id} onChange={event => update('program_id', event.target.value)}><option value="">Пока не определена</option>{catalogs.programs.map(item => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
          <label className="field"><span>ИТ-продукт</span><select value={form.product_id} onChange={event => update('product_id', event.target.value)}><option value="">Пока не определён</option>{catalogs.products.map(item => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
          <label className="field"><span>Цикл сотрудничества <b>*</b></span><input value={form.cycle_label} onChange={event => update('cycle_label', event.target.value)} placeholder="Например: осень 2026" required maxLength={120}/></label>
          <label className="field"><span>Ответственный <b>*</b></span><select value={form.owner_id} onChange={event => update('owner_id', event.target.value)} required><option value="">Выберите менеджера</option>{catalogs.owners.map(item => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
        </div>
        <div className="info-note"><Icon name="layers" size={18}/><p>Начальный этап — <strong>поиск контактов</strong>. Программа и продукт нужны до передачи материалов; в текущем срезе заполните их при создании, если планируете пройти весь процесс.</p></div>
      </div>
      <div className="modal-actions"><Button variant="secondary" type="button" onClick={onClose} disabled={saving}>Отмена</Button><Button type="submit" disabled={saving}>{saving ? <><span className="spinner small"/>Сохраняем…</> : <><Icon name="plus" size={17}/>Создать взаимодействие</>}</Button></div>
    </form>
  </Modal>;
}

