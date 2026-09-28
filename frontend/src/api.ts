import type {
  IntegrationsStatusResponse,
  IntegrationSyncResponse,
  IntegrationInboxResponse,
  ReconcileResolveParams,
  LearningMetricsSummaryResponse,
  WorkflowMigrationPreview,
  WorkflowMigrationResult,
  WorkflowMigratePreviewPayload,
  WorkflowMigrateCommitPayload,
  WorkflowVersionInfo,
  Workflow,
} from './types';

export class ApiError extends Error {
  code: string;
  status: number;
  requestId?: string;
  details?: unknown;

  constructor(
    message: string,
    code: string = 'REQUEST_FAILED',
    status: number = 0,
    requestId?: string,
    details?: unknown,
  ) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
    this.requestId = requestId;
    this.details = details;
  }
}

export class ApiClient {
  private authHeaders: () => Promise<Record<string, string>>;

  constructor(authHeaders: () => Promise<Record<string, string>>) {
    this.authHeaders = authHeaders;
  }

  async raw(path: string, options: RequestInit = {}): Promise<Response> {
    const headers = new Headers(await this.authHeaders());
    headers.set('Accept', 'application/json');
    if (options.body !== undefined && !(options.body instanceof FormData)) {
      headers.set('Content-Type', 'application/json');
    }
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

  async patch<T>(path: string, body: unknown, key?: string): Promise<T> {
    return (await this.raw(path, {
      method: 'PATCH', body: JSON.stringify(body),
      headers: key ? { 'Idempotency-Key': key } : {},
    })).json() as Promise<T>;
  }

  async upload<T>(path: string, formData: FormData, key?: string): Promise<T> {
    return (await this.raw(path, {
      method: 'POST',
      body: formData,
      headers: key ? { 'Idempotency-Key': key } : {},
    })).json() as Promise<T>;
  }

  async download(path: string, body: unknown, format?: string, fallbackName?: string): Promise<void> {
    const urlPath = format
      ? (path.includes('?') ? `${path}&format=${encodeURIComponent(format)}` : `${path}?format=${encodeURIComponent(format)}`)
      : path;
    const response = await this.raw(urlPath, {
      method: 'POST',
      body: JSON.stringify(body),
      headers: { Accept: '*/*' },
    });
    const blob = await response.blob();
    const defaultName = fallbackName || (format ? `report.${format}` : 'rtk-snapshot.json');
    const name = response.headers.get('Content-Disposition')?.match(/filename="?([^";]+)"?/i)?.[1]
      || defaultName;
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = name.replace(/[\\/:*?"<>|]/g, '_');
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async downloadGet(path: string, fallbackName: string = 'download'): Promise<void> {
    const response = await this.raw(path, {
      method: 'GET',
      headers: { Accept: '*/*' },
    });
    const blob = await response.blob();
    const name = response.headers.get('Content-Disposition')?.match(/filename="?([^";]+)"?/i)?.[1]
      || fallbackName;
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = name.replace(/[\\/:*?"<>|]/g, '_');
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async previewAttachmentBlob(path: string): Promise<{ blobUrl: string; cleanup: () => void }> {
    const normalizedPath = path.startsWith('/api/v1') ? path.slice(7) : path;
    const response = await this.raw(normalizedPath, {
      method: 'GET',
      headers: { Accept: '*/*' },
    });
    const blob = await response.blob();
    const blobUrl = URL.createObjectURL(blob);
    return {
      blobUrl,
      cleanup: () => {
        URL.revokeObjectURL(blobUrl);
      },
    };
  }

  async deleteAttachment(
    interactionId: string,
    attachmentId: string,
    expectedRevision?: number,
    key?: string,
  ): Promise<{ status: string; revision: number }> {
    const query = expectedRevision !== undefined ? `?expected_revision=${encodeURIComponent(expectedRevision)}` : '';
    const path = `/interactions/${encodeURIComponent(interactionId)}/attachments/${encodeURIComponent(attachmentId)}${query}`;
    const mutationKey = key || makeMutationKey();
    const response = await this.raw(path, {
      method: 'DELETE',
      headers: mutationKey ? { 'Idempotency-Key': mutationKey } : {},
    });
    return response.json() as Promise<{ status: string; revision: number }>;
  }


  async getIntegrationsStatus(): Promise<IntegrationsStatusResponse> {
    return this.get<IntegrationsStatusResponse>('/integrations/status');
  }

  async syncIntegrationSource(source: string, key: string = makeMutationKey()): Promise<IntegrationSyncResponse> {
    return this.post<IntegrationSyncResponse>(`/integrations/sync/${encodeURIComponent(source)}`, {}, key);
  }

  async syncIntegration(source: string, key: string = makeMutationKey()): Promise<IntegrationSyncResponse> {
    return this.syncIntegrationSource(source, key);
  }

  async getIntegrationInbox(params?: { source?: string; status?: string; page?: number; page_size?: number }): Promise<IntegrationInboxResponse> {
    const query = new URLSearchParams();
    if (params?.source) query.set('source', params.source);
    if (params?.status) query.set('status', params.status);
    if (params?.page) query.set('page', String(params.page));
    if (params?.page_size) query.set('page_size', String(params.page_size));
    const qs = query.toString();
    return this.get<IntegrationInboxResponse>('/integrations/inbox' + (qs ? `?${qs}` : ''));
  }

  async uploadLmsLearners(file: File, key: string = makeMutationKey()): Promise<any> {
    const formData = new FormData();
    formData.append('file', file);
    return this.upload<any>('/integrations/upload/learners', formData, key);
  }

  async resolveInboxItem(
    id: string,
    body: ReconcileResolveParams | { action: string; [key: string]: unknown },
    key: string = makeMutationKey(),
  ): Promise<any> {
    return this.post<any>(`/integrations/inbox/${encodeURIComponent(id)}/resolve`, body, key);
  }

  async getIntegrationMetrics(params?: { organization_id?: string; program_id?: string }): Promise<LearningMetricsSummaryResponse> {
    const query = new URLSearchParams();
    if (params?.organization_id) query.set('organization_id', params.organization_id);
    if (params?.program_id) query.set('program_id', params.program_id);
    const qs = query.toString();
    return this.get<LearningMetricsSummaryResponse>('/integrations/metrics' + (qs ? `?${qs}` : ''));
  }

  async previewWorkflowMigration(
    tokenOrBody: string | null | undefined | WorkflowMigratePreviewPayload,
    optionalBody?: WorkflowMigratePreviewPayload,
  ): Promise<WorkflowMigrationPreview> {
    let body: WorkflowMigratePreviewPayload;
    const headers: Record<string, string> = {};
    if (typeof tokenOrBody === 'string') {
      if (tokenOrBody) headers.Authorization = `Bearer ${tokenOrBody}`;
      body = optionalBody!;
    } else if (tokenOrBody && typeof tokenOrBody === 'object' && 'from_version' in tokenOrBody) {
      body = tokenOrBody as WorkflowMigratePreviewPayload;
    } else {
      body = optionalBody!;
    }
    const response = await this.raw('/workflow/migrate/preview', {
      method: 'POST',
      body: JSON.stringify(body),
      headers,
    });
    return response.json() as Promise<WorkflowMigrationPreview>;
  }

  async commitWorkflowMigration(
    tokenOrBody: string | null | undefined | WorkflowMigrateCommitPayload,
    bodyOrKey?: WorkflowMigrateCommitPayload | string,
    idempotencyKey?: string,
  ): Promise<WorkflowMigrationResult> {
    let body: WorkflowMigrateCommitPayload;
    let key = idempotencyKey || makeMutationKey();
    const headers: Record<string, string> = {};

    if (typeof tokenOrBody === 'string') {
      if (tokenOrBody) headers.Authorization = `Bearer ${tokenOrBody}`;
      body = bodyOrKey as WorkflowMigrateCommitPayload;
      if (idempotencyKey) key = idempotencyKey;
    } else if (tokenOrBody && typeof tokenOrBody === 'object' && 'from_version' in tokenOrBody) {
      body = tokenOrBody as WorkflowMigrateCommitPayload;
      if (typeof bodyOrKey === 'string') {
        key = bodyOrKey;
      }
    } else {
      body = bodyOrKey as WorkflowMigrateCommitPayload;
    }
    if (key) {
      headers['Idempotency-Key'] = key;
    }

    const response = await this.raw('/workflow/migrate/commit', {
      method: 'POST',
      body: JSON.stringify(body),
      headers,
    });
    return response.json() as Promise<WorkflowMigrationResult>;
  }

  async updateOrganization(organizationId: string, body: { owner_id: string | null }): Promise<any> {
    return this.patch<any>(`/organizations/${encodeURIComponent(organizationId)}`, body);
  }

  async getWorkflowVersions(): Promise<WorkflowVersionInfo[]> {
    return this.get<WorkflowVersionInfo[]>('/workflow/versions');
  }

  async getWorkflow(version?: number): Promise<Workflow> {
    const qs = version !== undefined ? `?version=${encodeURIComponent(version)}` : '';
    return this.get<Workflow>(`/workflow${qs}`);
  }

  async publishWorkflowVersion(version: number): Promise<any> {
    return this.post<any>(`/workflow/versions/${encodeURIComponent(version)}/publish`, {});
  }
}

export function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : 'Произошла непредвиденная ошибка.';
}

export function makeMutationKey(): string {
  return crypto.randomUUID();
}

