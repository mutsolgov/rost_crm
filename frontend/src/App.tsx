import { useState } from 'react';
import { useAuth } from './auth';
import { useResource, useRoute } from './hooks';
import { Avatar, Brand, Button, ErrorAlert, Icon, Loading, roleNames } from './ui';
import { CreateInteractionModal } from './forms';
import { Overview, Interactions } from './views/WorkspaceViews';
import { InteractionPage } from './views/InteractionPage';
import { Reports } from './views/Reports';
import { CatalogPage, HelpPage } from './views/ReferenceViews';
import { IntegrationsView } from './views/IntegrationsView';
import type { Catalogs, Workflow } from './types';


function LoginScreen() {
  const { config, loading, error, login, selectDemoUser, retry } = useAuth();
  const [selection, setSelection] = useState('');
  return <div className="login-screen">
    <div className="login-story"><Brand/><div className="login-story-content">
      <div className="eyebrow">СОТРУДНИЧЕСТВО С ОБРАЗОВАТЕЛЬНЫМИ ОРГАНИЗАЦИЯМИ</div>
      <h1>От первого контакта<br/>к новым компетенциям.</h1>
      <p>Общий контекст для команды. Прозрачный путь для каждого партнёрства.</p>
      <div className="login-path"><span><i/>Контакт</span><Icon name="arrow"/><span><i/>Внедрение</span><Icon name="arrow"/><span><i/>Обучение</span></div>
    </div><div className="login-story-footer">ИТ Школа · Партнёры <span>Первый рабочий срез</span></div></div>
    <div className="login-panel"><div className="login-box">
      <span className="login-icon"><Icon name="shield" size={28}/></span>
      <h2>{config?.auth_mode === 'demo' ? 'Демонстрационный стенд' : 'Вход в рабочее пространство'}</h2>
      <p>{config?.auth_mode === 'demo'
        ? 'Выберите роль, чтобы пройти рабочие сценарии на вымышленных данных.'
        : 'Используйте корпоративную учётную запись. Доступ к данным определяется вашими полномочиями.'}</p>
      <ErrorAlert error={error} onRetry={retry}/>
      {loading ? <Loading label="Подготавливаем вход…"/> : config?.auth_mode === 'demo'
        ? <form onSubmit={event => { event.preventDefault(); selectDemoUser(selection); }}>
          <label className="field"><span>Демонстрационный пользователь</span><select value={selection} onChange={event => setSelection(event.target.value)} required>
            <option value="">Выберите пользователя</option>
            {config.demo_users.map(user => <option key={user.id} value={user.id}>{user.name} · {roleNames[user.role] || user.role}</option>)}
          </select></label>
          <Button className="full-width" type="submit" disabled={!selection}>Открыть стенд<Icon name="arrow" size={18}/></Button>
          <div className="login-demo-note"><Icon name="alert" size={16}/>Режим разработки. Выбор роли не заменяет корпоративную авторизацию.</div>
        </form>
        : config && <Button className="full-width" onClick={login}>Войти через Keycloak<Icon name="arrow" size={18}/></Button>}
      <p className="login-footnote">Авторизация и ограничения доступа проверяются сервером.</p>
    </div></div>
  </div>;
}

function Workspace() {
  const auth = useAuth();
  const me = auth.me!;
  const { api, config } = auth;
  const route = useRoute();
  const [revision, setRevision] = useState(0);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const catalogs = useResource<Catalogs>(() => api.get('/catalogs'), [api, revision]);
  const workflow = useResource<Workflow>(() => api.get('/workflow'), [api]);
  const isPrivileged = me.role === 'supervisor' || me.role === 'administrator' || me.role === 'admin';
  const navigation = [
    { code: 'overview', name: 'Обзор', icon: 'grid' },
    { code: 'interactions', name: 'Взаимодействия', icon: 'layers' },
    { code: 'reports', name: 'Отчёты', icon: 'chart' },
    ...(isPrivileged ? [{ code: 'integrations', name: 'Интеграции', icon: 'refresh' }] : []),
    { code: 'catalogs', name: 'Справочники', icon: 'book' },
    { code: 'help', name: 'Помощь', icon: 'help' },
  ];
  const activeNav = route.path.split('/')[0] || 'overview';
  const selectedName = navigation.find(item => item.code === activeNav)?.name || 'Рабочее пространство';
  const navigate = (target: string) => { setMobileOpen(false); route.navigate(target); };
  const changed = () => setRevision(value => value + 1);
  const openInteraction = (id: string) => navigate('interactions/' + encodeURIComponent(id));
  const canCreate = !!catalogs.data?.organizations.length && !!catalogs.data?.owners.length;
  let interactionId = '';
  if (route.path.startsWith('interactions/')) {
    try { interactionId = decodeURIComponent(route.path.slice('interactions/'.length)); }
    catch { interactionId = ''; }
  }

  return <div className="app-shell">
    {mobileOpen && <button className="sidebar-scrim" aria-label="Закрыть меню" onClick={() => setMobileOpen(false)}/>}
    <aside className={'sidebar ' + (mobileOpen ? 'sidebar-open' : '')}>
      <a className="brand-link" href="#/overview" onClick={() => setMobileOpen(false)}><Brand/></a>
      <div className="sidebar-label">РАБОЧЕЕ ПРОСТРАНСТВО</div>
      <nav className="main-nav" aria-label="Основная навигация">{navigation.map(item =>
        <a key={item.code} href={'#/' + item.code} onClick={() => setMobileOpen(false)} className={activeNav === item.code ? 'active' : ''} aria-current={activeNav === item.code ? 'page' : undefined}>
          <Icon name={item.icon}/><span>{item.name}</span>{activeNav === item.code && <i/>}
        </a>)}
      </nav>
      <div className="sidebar-bottom">
        <div className="sidebar-note"><span className="sidebar-note-icon"><Icon name="layers" size={19}/></span><strong>Один партнёр.<br/>Несколько возможностей.</strong><p>Управляйте каждым циклом сотрудничества отдельно.</p></div>
        <a href="#/help" onClick={() => setMobileOpen(false)} className="slice-link"><span>Первый рабочий срез</span><Icon name="external" size={14}/></a>
      </div>
    </aside>
    <div className="main-shell">
      <header className="topbar">
        <div className="topbar-left"><button className="icon-button mobile-menu" aria-label="Открыть меню" onClick={() => setMobileOpen(true)}><Icon name="menu"/></button><span className="breadcrumb-root">Партнёры</span><Icon name="chevron" size={13}/><strong>{selectedName}</strong></div>
        <div className="account"><span className="scope-indicator"><i/>Ваша область доступа</span><div className="account-divider"/><Avatar name={me.name}/><div className="account-text"><strong>{me.name}</strong><small>{roleNames[me.role] || me.role}</small></div><button className="icon-button logout-button" title="Выйти" aria-label="Выйти" onClick={auth.logout}><Icon name="logout" size={18}/></button></div>
      </header>
      {config?.auth_mode === 'demo' && <div className="demo-strip"><div><span className="demo-label">ДЕМО</span><span>Вымышленные данные · режим разработки</span></div><label><span>Пользователь</span><select aria-label="Сменить демонстрационного пользователя" value={auth.demoUserId} onChange={event => auth.selectDemoUser(event.target.value)}>{config.demo_users.map(user => <option key={user.id} value={user.id}>{user.name} · {roleNames[user.role] || user.role}</option>)}</select></label></div>}
      <main className="page-content" id="main-content">
        {(catalogs.error || workflow.error) ? <ErrorAlert error={catalogs.error || workflow.error} onRetry={changed}/> : null}
        {!catalogs.data || !workflow.data ? ((!catalogs.error && !workflow.error) && <Loading label="Загружаем рабочее пространство…"/>) : <>
          {activeNav === 'overview' && <Overview api={api} revision={revision} me={me} onCreate={() => setCreateOpen(true)} canCreate={canCreate} openInteraction={openInteraction} navigate={navigate}/>}
          {activeNav === 'interactions' && (interactionId
            ? <InteractionPage key={interactionId} id={interactionId} api={api} catalogs={catalogs.data} workflow={workflow.data} me={me} revision={revision} onChanged={changed} onBack={() => navigate('interactions')}/>
            : <Interactions api={api} catalogs={catalogs.data} workflow={workflow.data} revision={revision} initialState={route.query.get('state') || ''} onCreate={() => setCreateOpen(true)} canCreate={canCreate} openInteraction={openInteraction}/>)}
          {activeNav === 'reports' && <Reports api={api} catalogs={catalogs.data} workflow={workflow.data}/>}
          {activeNav === 'integrations' && (isPrivileged
            ? <IntegrationsView api={api} catalogs={catalogs.data} me={me} navigate={navigate} openInteraction={openInteraction}/>
            : <div className="panel" style={{ padding: '32px', textAlign: 'center' }}>
                <h2>Доступ ограничен</h2>
                <p style={{ color: 'var(--rtk-color-muted)', maxWidth: '440px', margin: '8px auto 20px' }}>
                  Управление интеграциями и очередью сверки доступно только для руководителей и администраторов.
                </p>
                <Button onClick={() => navigate('overview')}>Вернуться к обзору</Button>
              </div>)}
          {activeNav === 'catalogs' && <CatalogPage catalogs={catalogs.data} api={api} onChanged={changed}/>}
          {activeNav === 'help' && <HelpPage/>}
          {!navigation.some(item => item.code === activeNav) && <div className="panel"><h2>Страница не найдена</h2><Button onClick={() => navigate('overview')}>Перейти к обзору</Button></div>}
        </>}
      </main>
      <footer className="page-footer"><span>ИТ Школа · Партнёры</span><span>Первый рабочий срез · v0.1</span></footer>
    </div>
    {createOpen && catalogs.data && <CreateInteractionModal api={api} catalogs={catalogs.data} me={me} onClose={() => setCreateOpen(false)} onSaved={item => { setCreateOpen(false); changed(); openInteraction(item.id); }}/>}
  </div>;
}
export default function App() {
  const { me } = useAuth();
  return me ? <Workspace key={me.id}/> : <LoginScreen/>;
}
