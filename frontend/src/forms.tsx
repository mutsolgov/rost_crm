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
    contact_id: '', comment: '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const mutation = useMutationKey();
  const compatibleProducts = catalogs.products.filter(prod => {
    if (!form.program_id) return true;
    if (catalogs.program_products && catalogs.program_products.length > 0) {
      return catalogs.program_products.some(pp => pp.program_id === form.program_id && pp.product_id === prod.id);
    }
    if (form.program_id === 'program-devops') return prod.id === 'product-cloud';
    if (form.program_id === 'program-qa') return prod.id === 'product-test';
    return true;
  });

  const update = (field: keyof typeof form, value: string) => {
    if (field === 'organization_id') {
      setForm(previous => ({ ...previous, organization_id: value, contact_id: '' }));
    } else if (field === 'program_id') {
      setForm(previous => {
        let nextProductId = previous.product_id;
        if (value && nextProductId) {
          const isStillCompatible = (catalogs.program_products && catalogs.program_products.length > 0)
            ? catalogs.program_products.some(pp => pp.program_id === value && pp.product_id === nextProductId)
            : (value === 'program-devops' ? nextProductId === 'product-cloud' : nextProductId === 'product-test');
          if (!isStillCompatible) nextProductId = '';
        }
        return { ...previous, program_id: value, product_id: nextProductId };
      });
    } else {
      setForm(previous => ({ ...previous, [field]: value }));
    }
  };
  const orgContacts = (catalogs.contacts || []).filter(c => c.organization_id === form.organization_id && c.active);

  async function submit(event: FormEvent) {
    event.preventDefault(); setError(null); setSaving(true);
    const body = {
      ...form,
      title: form.title.trim(),
      cycle_label: form.cycle_label.trim(),
      program_id: form.program_id || null,
      product_id: form.product_id || null,
      contact_id: form.contact_id || null,
      comment: form.comment.trim() || null,
    };
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
          <label className="field"><span>ИТ-продукт</span><select value={form.product_id} onChange={event => update('product_id', event.target.value)}><option value="">Пока не определён</option>{compatibleProducts.map(item => <option value={item.id} key={item.id}>{item.name} ({item.vendor})</option>)}</select></label>
          <label className="field"><span>Цикл сотрудничества <b>*</b></span><input value={form.cycle_label} onChange={event => update('cycle_label', event.target.value)} placeholder="Например: осень 2026" required maxLength={120}/></label>
          <label className="field"><span>Ответственный <b>*</b></span><select value={form.owner_id} onChange={event => update('owner_id', event.target.value)} required><option value="">Выберите менеджера</option>{catalogs.owners.map(item => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
          <label className="field span-2"><span>Контактное лицо от ВУЗа</span><select value={form.contact_id} onChange={event => update('contact_id', event.target.value)} disabled={!form.organization_id}><option value="">Не выбрано</option>{orgContacts.map(item => <option value={item.id} key={item.id}>{item.full_name}{item.position ? ` (${item.position})` : ''}</option>)}</select></label>
        </div>
        <label className="field"><span>Комментарий к старту взаимодействия</span><textarea value={form.comment} onChange={event => update('comment', event.target.value)} placeholder="Например: цели пилота, договоренности с кафедрой или ключевые задачи…" maxLength={5000} rows={3}/></label>
        <div className="info-note"><Icon name="layers" size={18}/><p>Начальный этап — <strong>поиск контактов</strong>. Программа и продукт нужны до передачи материалов; в текущем срезе заполните их при создании, если планируете пройти весь процесс.</p></div>
      </div>
      <div className="modal-actions"><Button variant="secondary" type="button" onClick={onClose} disabled={saving}>Отмена</Button><Button type="submit" disabled={saving}>{saving ? <><span className="spinner small"/>Сохраняем…</> : <><Icon name="plus" size={17}/>Создать взаимодействие</>}</Button></div>
    </form>
  </Modal>;
}

