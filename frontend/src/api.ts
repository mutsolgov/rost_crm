export class ApiError extends Error {
  constructor(
    message: string, public code: string = 'REQUEST_FAILED',
    public status: number = 0, public requestId?: string, public details?: unknown,
  ) { super(message); this.name = 'ApiError'; }
}

export class ApiClient {
  constructor(private authHeaders: () => Promise<Record<string, string>>) {}

  async raw(path: string, options: RequestInit = {}): Promise<Response> {
    const headers = new Headers(await this.authHeaders());
    headers.set('Accept', 'application/json');
    if (options.body !== undefined) headers.set('Content-Type', 'application/json');
    new Headers(options.headers).forEach((value, name) => headers.set(name, value));
    let response: Response;
    try {
      response = await fetch('/api/v1' + path, { ...options, headers, credentials: 'same-origin' });
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') throw error;
      throw new ApiError('Не удалось связаться с сервером. Проверьте соединение и повторите действие.', 'NETWORK_ERROR');
    }
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      const problem = body?.error;
      const fallback = response.status === 401
        ? 'Сессия недействительна. Войдите в систему повторно.'
        : 'Сервер не смог выполнить запрос.';
      throw new ApiError(problem?.message || fallback, problem?.code || 'HTTP_' + response.status,
        response.status, problem?.request_id, problem?.details ?? body?.detail);
    }
    return response;
  }

  async get<T>(path: string): Promise<T> {
    return (await this.raw(path)).json() as Promise<T>;
  }

  async post<T>(path: string, body: unknown, key?: string): Promise<T> {
    return (await this.raw(path, {
      method: 'POST', body: JSON.stringify(body),
      headers: key ? { 'Idempotency-Key': key } : {},
    })).json() as Promise<T>;
  }

  async download(path: string, body: unknown): Promise<void> {
    const response = await this.raw(path, { method: 'POST', body: JSON.stringify(body) });
    const blob = await response.blob();
    const name = response.headers.get('Content-Disposition')?.match(/filename="?([^";]+)"?/i)?.[1]
      || 'rtk-snapshot.json';
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = name.replace(/[\\/:*?"<>|]/g, '_');
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}

export function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : 'Произошла непредвиденная ошибка.';
}

export function makeMutationKey(): string {
  return crypto.randomUUID();
}

