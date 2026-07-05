export interface Project {
  id?: number
  name: string
  identifier: string
}

export interface SessionInfo {
  connected: boolean
  user_login: string
  is_admin: boolean
  projects: Project[]
}

export interface ReleaseSummary {
  title: string
  display_title?: string
  container_page?: string
  block_id?: string
  version: string
  date: string
  product_line: string
  summary: string
}

export interface ReleaseDetail {
  wiki_title: string
  version_name: string
  release_date: string
  commit: string
  product_line: string
  changelog: string
  files_info: string
}

export interface SmtpServerConfig {
  smtp_host: string
  smtp_port: number
  smtp_from: string
  use_tls: boolean
}

export interface ContactConfig {
  contacts: string[]
  contacts_to: string[]
  contacts_cc: string[]
}

export interface ContactPersonConfig {
  name: string
  email: string
}

export interface ContactTemplateConfig {
  name: string
  contacts_to: ContactPersonConfig[]
  contacts_cc: ContactPersonConfig[]
}

export interface MailSettings {
  is_admin: boolean
  admin: {
    internal_server: SmtpServerConfig
    external_server: SmtpServerConfig
    internal_contacts: ContactConfig
  }
  user_internal: {
    smtp_user: string
    smtp_password: string
    smtp_password_set: boolean
    smtp_from: string
    contacts_to: string[]
    contacts_cc: string[]
    contact_templates: ContactTemplateConfig[]
  }
  user_external: {
    smtp_user: string
    smtp_password: string
    smtp_password_set: boolean
    smtp_from: string
    contacts_to: string[]
    contacts_cc: string[]
    contact_templates: ContactTemplateConfig[]
  }
}

export interface MetaInfo {
  product_lines: string[]
  mail_scopes: Array<{ label: string; value: string }>
  today: string
}

export interface ProjectReleaseCategories {
  mode: string
  categories: Array<{ key: string; title: string }>
}

export interface WikiRefreshPreview {
  mode: string
  main_page: string
  release_count: number
  categories: Array<{
    key: string
    title: string
    hub: string
    list_page: string
    release_count: number
  }>
  pages_to_update: string[]
  parents_to_update: Array<{
    page: string
    from: string
    to: string
  }>
  uncategorized: Array<{
    page: string
    version: string
    date: string
  }>
  warnings: string[]
}

export interface WikiRefreshResult {
  ok: boolean
  updated_release_count: number
  preview: WikiRefreshPreview
  message: string
}

export interface LegacyMigrationPreview {
  project_id: string
  entry_pages: string[]
  release_detail_mode?: 'auto' | 'inline' | 'page'
  release_detail_mode_label?: string
  requested_release_detail_mode?: 'auto' | 'inline' | 'page'
  target_page_label?: string
  source_page_count: number
  model_count: number
  release_count: number
  attachment_ref_count: number
  matched_attachment_count: number
  versions_to_create: number
  existing_versions: number
  release_pages_to_create: number
  existing_release_pages: number
  project_files_to_upload: number
  existing_project_files: number
  can_read_project_files: boolean
  source_pages: Array<{
    title: string
    model: string
    release_count: number
    attachment_ref_count: number
    matched_attachment_count: number
  }>
  warnings: string[]
  problems: Array<{
    level: string
    source_page: string
    version: string
    message: string
  }>
}

export interface LegacyMigrationResult {
  ok: boolean
  preview: LegacyMigrationPreview
  created_versions: number
  uploaded_files: number
  updated_release_pages: number
  refreshed_release_count: number
  release_detail_mode?: 'inline' | 'page'
  release_detail_mode_label?: string
  message: string
}

export interface LegacyMigrationJob {
  job_id: string
  status: 'running' | 'succeeded' | 'failed'
  logs: string[]
  result?: LegacyMigrationResult | null
  error?: string
}
