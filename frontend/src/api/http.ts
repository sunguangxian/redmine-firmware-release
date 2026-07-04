import axios from 'axios'
import type { ContactTemplateConfig, LegacyMigrationJob, LegacyMigrationPreview, LegacyMigrationResult, MailSettings, MetaInfo, ProjectReleaseCategories, ReleaseDetail, ReleaseSummary, SessionInfo, WikiRefreshPreview, WikiRefreshResult } from '../types'

const http = axios.create({
  baseURL: '',
  withCredentials: true
})

export function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string') return detail
    return error.message
  }
  return error instanceof Error ? error.message : String(error)
}

export function errorLogs(error: unknown): string[] {
  if (!axios.isAxiosError(error)) return []
  const logs = error.response?.data?.logs
  return Array.isArray(logs) ? logs.filter((item) => typeof item === 'string') : []
}

export async function getMeta(): Promise<MetaInfo> {
  const { data } = await http.get('/api/meta')
  return data
}

export async function login(payload: { auth_mode: string; username: string; password: string; api_key: string; remember: boolean }): Promise<SessionInfo> {
  const { data } = await http.post('/api/auth/login', payload)
  return data
}

export async function getMe(): Promise<SessionInfo> {
  const { data } = await http.get('/api/auth/me')
  return data
}

export async function logout(): Promise<void> {
  await http.post('/api/auth/logout')
}

export async function listReleases(projectId: string, productLine = ''): Promise<ReleaseSummary[]> {
  const { data } = await http.get('/api/releases', { params: { project_id: projectId, product_line: productLine } })
  return data
}

export async function getProjectReleaseCategories(projectId: string): Promise<ProjectReleaseCategories> {
  const { data } = await http.get(`/api/projects/${encodeURIComponent(projectId)}/release-categories`)
  return data
}

export async function getReleaseDetail(projectId: string, wikiTitle: string): Promise<ReleaseDetail> {
  const { data } = await http.get('/api/releases/detail', { params: { project_id: projectId, wiki_title: wikiTitle } })
  return data
}

export async function publishRelease(form: FormData): Promise<{ ok: boolean; title: string; notice_message: string; releases: ReleaseSummary[]; logs: string[] }> {
  const { data } = await http.post('/api/releases/publish', form, { headers: { 'Content-Type': 'multipart/form-data' } })
  return data
}

export async function getMailSettings(): Promise<MailSettings> {
  const { data } = await http.get('/api/mail/settings')
  return data
}

export async function saveAdminMailSettings(payload: unknown): Promise<void> {
  await http.put('/api/mail/admin-settings', payload)
}

export async function saveUserInternalMailSettings(payload: unknown): Promise<void> {
  await http.put('/api/mail/user-internal-settings', payload)
}

export async function saveUserExternalMailSettings(payload: unknown): Promise<void> {
  await http.put('/api/mail/user-external-settings', payload)
}

export async function getContacts(scope: string): Promise<{ contacts_to: string[]; contacts_cc: string[]; contact_templates: ContactTemplateConfig[] }> {
  const { data } = await http.get('/api/mail/contacts', { params: { scope } })
  return data
}

export async function getWikiConfig(projectId: string): Promise<{ text: string; message: string }> {
  const { data } = await http.get(`/api/wiki-config/${encodeURIComponent(projectId)}`)
  return data
}

export async function generateWikiConfig(projectId: string, templateKey: string): Promise<{ text: string; message: string }> {
  const { data } = await http.post('/api/wiki-config/generate', { project_id: projectId, template_key: templateKey })
  return data
}

export async function checkWikiConfig(text: string): Promise<{ ok: boolean; message: string }> {
  const { data } = await http.post('/api/wiki-config/check', { text })
  return data
}

export async function saveWikiConfig(projectId: string, text: string): Promise<{ message: string }> {
  const { data } = await http.put(`/api/wiki-config/${encodeURIComponent(projectId)}`, { text })
  return data
}

export async function getWikiTemplates(): Promise<Array<[string, string]>> {
  const { data } = await http.get('/api/wiki-config/templates')
  return data
}

export async function previewWikiRefresh(projectId: string): Promise<WikiRefreshPreview> {
  const { data } = await http.get(`/api/wiki-config/${encodeURIComponent(projectId)}/refresh-preview`)
  return data
}

export async function refreshWikiIndex(projectId: string): Promise<WikiRefreshResult> {
  const { data } = await http.post(`/api/wiki-config/${encodeURIComponent(projectId)}/refresh`)
  return data
}

export async function previewLegacyMigration(payload: { project_id: string; entry_pages: string[] }): Promise<LegacyMigrationPreview> {
  const { data } = await http.post('/api/legacy-migration/preview', payload)
  return data
}

export async function executeLegacyMigration(payload: { project_id: string; entry_pages: string[] }): Promise<LegacyMigrationResult> {
  const { data } = await http.post('/api/legacy-migration/execute', payload)
  return data
}

export async function startLegacyMigrationJob(payload: { project_id: string; entry_pages: string[] }): Promise<LegacyMigrationJob> {
  const { data } = await http.post('/api/legacy-migration/execute-job', payload)
  return data
}

export async function getLegacyMigrationJob(jobId: string): Promise<LegacyMigrationJob> {
  const { data } = await http.get(`/api/legacy-migration/jobs/${encodeURIComponent(jobId)}`)
  return data
}
