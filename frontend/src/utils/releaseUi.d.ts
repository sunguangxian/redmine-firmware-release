export type ReleaseValidationInput = {
  projectId?: string
  selectedWikiTitle?: string
  requireSelectedVersion?: boolean
  versionName?: string
  releaseDate?: string
  commit?: string
  changelog?: string
  productLine?: string
  files?: File[]
  noticeEnabled?: boolean
  mailTo?: string[]
  manualMailTo?: string
  mailSubject?: string
  mailBody?: string
}

export function splitEmails(text: string): string[]
export function mergeEmails(groups: string[][]): string[]
export function changelogLines(text: string): string[]
export function uniqueItems(items: string[]): string[]
export function formatBytes(size: number): string
export function duplicateFileNames(files: File[]): Set<string>
export function selectedFileRows(files: File[]): Array<{ name: string; size: number; sizeText: string; duplicate: boolean }>
export function totalFileSize(files: File[]): number
export function releaseNameFromAttachments(names: string[], fallbackVersion: string, fallbackDate: string): string
export function buildMailSubject(scope: string, names: string[], versionName: string, releaseDate: string): string
export function buildMailBody(scope: string, names: string[], versionName: string, releaseDate: string, commit: string, changelogText: string): string
export function validateReleaseInput(input: ReleaseValidationInput): string[]
export function friendlyReleaseError(message: string): string
export function hasReleaseDraft(input: ReleaseValidationInput): boolean
