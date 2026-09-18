import { createContext, useContext, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import Keycloak from 'keycloak-js';
import { ApiClient, ApiError, messageOf } from './api';
import type { AppConfig, User } from './types';

interface AuthContextValue {
  config: AppConfig | null;
  me: User | null;
  api: ApiClient;
  loading: boolean;
  error: string;
  demoUserId: string;
  selectDemoUser: (id: string) => void;
  login: () => void;
  logout: () => void;
  retry: () => void;
}
const AuthContext = createContext<AuthContextValue | null>(null);
const publicApi = new ApiClient(async () => ({}));

export function AuthProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [me, setMe] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [demoUserId, setDemoUserId] = useState('');
  const [oidcReady, setOidcReady] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [identityRevision, setIdentityRevision] = useState(0);
  const keycloak = useRef<Keycloak | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const received = await publicApi.get<AppConfig>('/config');
        if (cancelled) return;
        setConfig(received);
        if (received.auth_mode === 'demo') {
          setLoading(false);
          return;
        }
        if (received.auth_mode !== 'oidc' || !received.oidc) {
          throw new Error('Сервер не передал корректную конфигурацию входа.');
        }
        const client = new Keycloak({
          url: received.oidc.url, realm: received.oidc.realm, clientId: received.oidc.client_id,
        });
        keycloak.current = client;
        client.onAuthLogout = () => { setMe(null); setAuthenticated(false); };
        client.onTokenExpired = () => {
          client.updateToken(30).catch(() => {
            client.clearToken();
            setMe(null); setAuthenticated(false);
            setError('Сессия завершена. Войдите повторно.');
          });
        };
        const isAuthenticated = await client.init({
          onLoad: 'check-sso', pkceMethod: 'S256', checkLoginIframe: false,
        });
        if (cancelled) return;
        setAuthenticated(isAuthenticated);
        setOidcReady(true);
        if (!isAuthenticated) setLoading(false);
      } catch (problem) {
        if (!cancelled) { setError(messageOf(problem)); setLoading(false); }
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const api = useMemo(() => new ApiClient(async (): Promise<Record<string, string>> => {
    if (config?.auth_mode === 'demo') {
      if (!demoUserId) throw new ApiError('Выберите демонстрационного пользователя.', 'AUTH_REQUIRED', 401);
      return { 'X-Demo-User': demoUserId };
    }
    const client = keycloak.current;
    if (!client?.authenticated) throw new ApiError('Требуется вход через Keycloak.', 'AUTH_REQUIRED', 401);
    try { await client.updateToken(30); }
    catch { throw new ApiError('Не удалось обновить сессию. Войдите повторно.', 'SESSION_EXPIRED', 401); }
    return { Authorization: 'Bearer ' + client.token };
  }), [config?.auth_mode, demoUserId, oidcReady]);

  useEffect(() => {
    if (!config || (config.auth_mode === 'demo' ? !demoUserId : !oidcReady || !authenticated)) return;
    let cancelled = false;
    setLoading(true); setError(''); setMe(null);
    api.get<User>('/me').then(user => {
      if (!cancelled) setMe(user);
    }).catch(problem => {
      if (!cancelled) setError(messageOf(problem));
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => { cancelled = true; };
  }, [api, config, demoUserId, oidcReady, authenticated, identityRevision]);

  const selectDemoUser = (id: string) => {
    if (config?.auth_mode !== 'demo' || !config.demo_users.some(user => user.id === id)) return;
    setMe(null); setError(''); setLoading(true); setDemoUserId(id);
    setIdentityRevision(value => value + 1);
  };
  const login = () => {
    if (!keycloak.current) return;
    void keycloak.current.login({ redirectUri: window.location.origin }).catch(problem => setError(messageOf(problem)));
  };
  const logout = () => {
    if (config?.auth_mode === 'demo') {
      setMe(null); setDemoUserId(''); setLoading(false); setError('');
      return;
    }
    void keycloak.current?.logout({ redirectUri: window.location.origin })
      .catch(problem => setError(messageOf(problem)));
  };
  const retry = () => {
    if (!config || (config.auth_mode === 'oidc' && !oidcReady)) window.location.reload();
    else if (config.auth_mode === 'oidc' && !authenticated) login();
    else setIdentityRevision(value => value + 1);
  };

  return <AuthContext.Provider value={{
    config, me, api, loading, error, demoUserId, selectDemoUser, login, logout, retry,
  }}>{children}</AuthContext.Provider>;
}
export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error('AuthProvider is missing');
  return value;
}
