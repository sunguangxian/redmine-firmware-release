import axios from 'axios'
import type { ContactTemplateConfig, LegacyMigrationJob, LegacyMigrationPreview, LegacyMigrationResult, MailSettings, MetaInfo, ProjectReleaseCategories, ReleaseDetail, ReleaseSummary, SessionInfo, WikiRefreshPreview, WikiRefreshResult } from '../types'

const http = axios.create({ baseURL: '', withCredentials: true })

export type PublishReleaseResult = { ok: boolean; title: string; notice_message: string; releases: ReleaseSummary[]; logs: string[]; publish_history_id: number; release_status: string; release_status_label: string; file_status: string; wiki_status: string; index_status: string; mail_status: string; mail_status_label: string; result_summary: string }
export type MailHistoryItem = { id: number; project_id: string; wiki_title: string; version_name: string; scope: string; subject: string; to_addrs: string[]; cc_addrs: string[]; attachment_count: number; sender_user: string; status: string; error_message: string; send_type: string; created_at: string }
export type RecoverAction = { action: 'rebuild_index' | 'continue'; label: string }
export type PublishHistoryItem = { id: number; project_id: string; wiki_title: string; version_name: string; action: string; release_status: string; file_status: string; wiki_status: string; index_status: string; mail_status: string; release_status_label?: string; file_status_label?: string; wiki_status_label?: string; index_status_label?: string; mail_status_label?: string; status_summary?: string; recover_actions?: RecoverAction[]; can_rebuild_index?: boolean; can_continue?: boolean; error_message: string; logs: string[]; created_at: string; updated_at: string }
export type LegacyReleaseDetailMode = 'auto' | 'inline' | 'page'
export type LegacyMigrationPayload = { project_id: string; entry_pages: string[]; release_detail_mode?: LegacyReleaseDetailMode }

export function errorMessage(error: unknown): string { if (axios.isAxiosError(error)) { const detail = error.response?.data?.detail; if (typeof detail === 'string') return detail; return error.message } return error instanceof Error ? error.message : String(error) }
export function errorLogs(error: unknown): string[] { if (!axios.isAxiosError(error)) return []; const logs = error.response?.data?.logs; return Array.isArray(logs) ? logs.filter((item) => typeof item === 'string') : [] }
export async function getMeta(): Promise<MetaInfo> { const { data } = await http.get('/api/meta'); return data }
export async function login(payload: { auth_mode: string; username: string; password: string; api_key: string; remember: boolean }): Promise<SessionInfo> { const { data } = await http.post('/api/auth/login', payload); return data }
export async function getMe(): Promise<SessionInfo> { const { data } = await http.get('/api/auth/me'); return data }
export async function logout(): Promise<void> { await http.post('/api/auth/logout') }
export async function listReleases(projectId: string, productLine = ''): Promise<ReleaseSummary[]> { const { data } = await http.get('/api/releases', { params: { project_id: projectId, product_line: productLine } }); return data }
export async function getProjectReleaseCategories(projectId: string): Promise<ProjectReleaseCategories> { const { data } = await http.get(`/api/projects/${encodeURIComponent(projectId)}/release-categories`); return data }
export async function getReleaseDetail(projectId: string, wikiTitle: string): Promise<ReleaseDetail> { const { data } = await http.get('/api/releases/detail', { params: { project_id: projectId, wiki_title: wikiTitle } }); return data }
export async function previewRelease(form: FormData): Promise<{ ok: boolean; summary: string; logs: string[] }> { const { data } = await http.post('/api/releases/preview', form, { headers: { 'Content-Type': 'multipart/form-data' } }); return data }
export async function publishRelease(form: FormData): Promise<PublishReleaseResult> { const { data } = await http.post('/api/releases/publish', form, { headers: { 'Content-Type': 'multipart/form-data' } }); return data }
export async function sendReleaseNotice(form: FormData): Promise<{ ok: boolean; message: string; logs: string[] }> { const { data } = await http.post('/api/releases/notice/send', form, { headers: { 'Content-Type': 'multipart/form-data' } }); return data }
export async function getMailSettings(): Promise<MailSettings> { const { data } = await http.get('/api/mail/settings'); return data }
export async function saveAdminMailSettings(payload: unknown): Promise<void> { await http.put('/api/mail/admin-settings', payload) }
export async function saveUserInternalMailSettings(payload: unknown): Promise<void> { await http.put('/api/mail/user-internal-settings', payload) }
export async function saveUserExternalMailSettings(payload: unknown): Promise<void> { await http.put('/api/mail/user-external-settings', payload) }
export async function testMailConnection(payload: { scope: string; smtp_user: string; smtp_password: string; smtp_from: string }): Promise<{ ok: boolean; message: string }> { const { data } = await http.post('/api/mail/test-connection', payload); return data }
export async function testAdminMailServer(payload: { scope: string; smtp_host: string; smtp_port: number; smtp_from: string; use_tls: boolean }): Promise<{ ok: boolean; message: string }> { const { data } = await http.post('/api/mail/admin-test-connection', payload); return data }
export async function getMailHistory(params: { project_id?: string; wiki_title?: string; version_name?: string; limit?: number }): Promise<{ ok: boolean; items: MailHistoryItem[] }> { const { data } = await http.get('/api/mail/history', { params }); return data }
export async function getPublishHistory(params: { project_id?: string; wiki_title?: string; limit?: number }): Promise<{ ok: boolean; items: PublishHistoryItem[] }> { const { data } = await http.get('/api/releases/publish-history', { params }); return data }
export async function recoverPublishHistory(id: number, action: 'rebuild_index' | 'continue'): Promise<{ ok: boolean; message: string; logs: string[] }> { const { data } = await http.post(`/api/releases/publish-history/${encodeURIComponent(id)}/recover`, { action }); return data }
export async function getContacts(scope: string): Promise<{ contacts_to: string[]; contacts_cc: string[]; contact_templates: ContactTemplateConfig[] }> { const { data } = await http.get('/api/mail/contacts', { params: { scope } }); return data }
export async function getWikiConfig(projectId: string): Promise<{ text: string; message: string }> { const { data } = await http.get(`/api/wiki-config/${encodeURIComponent(projectId)}`); return data }
export async function generateWikiConfig(projectId: string, templateKey: string): Promise<{ text: string; message: string }> { const { data } = await http.post('/api/wiki-config/generate', { project_id: projectId, template_key: templateKey }); return data }
export async function checkWikiConfig(text: string): Promise<{ ok: boolean; message: string }> { const { data } = await http.post('/api/wiki-config/check', { text }); return data }
export async function saveWikiConfig(projectId: string, text: string): Promise<{ message: string }> { const { data } = await http.put(`/api/wiki-config/${encodeURIComponent(projectId)}`, { text }); return data }
export async function getWikiTemplates(): Promise<Array<[string, string]>> { const { data } = await http.get('/api/wiki-config/templates'); return data }
export async function previewWikiRefresh(projectId: string): Promise<WikiRefreshPreview> { const { data } = await http.get(`/api/wiki-config/${encodeURIComponent(projectId)}/refresh-preview`); return data }
export async function refreshWikiIndex(projectId: string): Promise<WikiRefreshResult> { const { data } = await http.post(`/api/wiki-config/${encodeURIComponent(projectId)}/refresh`); return data }
export async function previewLegacyMigration(payload: LegacyMigrationPayload): Promise<LegacyMigrationPreview> { const { data } = await http.post('/api/legacy-migration/preview', payload); return data }
export async function executeLegacyMigration(payload: LegacyMigrationPayload): Promise<LegacyMigrationResult> { const { data } = await http.post('/api/legacy-migration/execute', payload); return data }
export async function startLegacyMigrationJob(payload: LegacyMigrationPayload): Promise<LegacyMigrationJob> { const { data } = await http.post('/api/legacy-migration/execute-job', payload); return data }
export async function getLegacyMigrationJob(jobId: string): Promise<LegacyMigrationJob> { const { data } = await http.get(`/api/legacy-migration/jobs/${encodeURIComponent(jobId)}`); return data }
