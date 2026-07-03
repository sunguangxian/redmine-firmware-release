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
  contacts_to: string[]
  contacts_cc: string[]
}

export interface MailSettings {
  is_admin: boolean
  admin: {
    internal_server: SmtpServerConfig
    external_server: SmtpServerConfig
    internal_contacts: ContactConfig
  }
  user_external: {
    smtp_user: string
    smtp_password: string
    smtp_from: string
    contacts_to: string[]
    contacts_cc: string[]
  }
}

export interface MetaInfo {
  product_lines: string[]
  mail_scopes: Array<{ label: string; value: string }>
  today: string
}
