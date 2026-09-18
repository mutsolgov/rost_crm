import type { Catalogs } from '../types';

export function CatalogPage({ catalogs }: { catalogs: Catalogs }) {
  return <><div className="page-heading"><div><div className="eyebrow">СПРАВОЧНАЯ ИНФОРМАЦИЯ</div><h1>Справочники</h1><p>Единые названия организаций, программ, продуктов и ответственных.</p></div></div><div className="reference-grid">{[['Организации', catalogs.organizations.map(item => item.name)], ['ИТ-программы', catalogs.programs.map(item => item.name)], ['ИТ-продукты', catalogs.products.map(item => item.name)], ['Ответственные', catalogs.owners.map(item => item.name)]].map(([title, entries]) => <section className="panel reference-card" key={title as string}><h2>{title as string}</h2><ul>{(entries as string[]).length ? (entries as string[]).map(entry => <li key={entry}>{entry}</li>) : <li>Нет доступных записей</li>}</ul></section>)}</div></>;
}

export function HelpPage() {
  return <><div className="page-heading"><div><div className="eyebrow">ПОДДЕРЖКА</div><h1>Помощь</h1><p>Подсказки по рабочему срезу CRM и правилам доступа.</p></div></div><section className="panel help-card"><h2>Как работать с карточкой</h2><ol><li>Создайте отдельное взаимодействие для каждого цикла сотрудничества.</li><li>Переводите карточку по этапам после фактического действия.</li><li>Используйте комментарий для возврата, отмены и важных решений.</li><li>История и отчёт фиксируют состояние на дату и не перезаписывают прошлые события.</li></ol><p className="form-hint">Внешний вход выполняется через Keycloak. Демонстрационный режим доступен только локально при явном APP_ENV=development и AUTH_MODE=demo.</p></section></>;
}
