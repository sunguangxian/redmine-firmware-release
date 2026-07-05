<template>
  <div>
    <el-card class="card">
      <div class="toolbar">
        <el-select v-model="projectId" placeholder="选择项目" filterable style="width: 320px" @change="reloadAll">
          <el-option v-for="project in projects" :key="project.identifier" :label="`${project.name} (${project.identifier})`" :value="project.identifier" />
        </el-select>
        <el-select v-model="filterProductLine" clearable placeholder="全部分类" style="width: 220px" @change="loadReleases">
          <el-option label="全部分类" value="" />
          <el-option v-for="item in projectCategories" :key="item.key" :label="item.title || item.key" :value="item.title || item.key" />
        </el-select>
        <el-button :loading="loadingReleases" @click="loadReleases">刷新列表</el-button>
      </div>

      <el-select v-model="selectedWikiTitle" placeholder="选择要编辑的版本" filterable style="width: 100%; margin-bottom: 12px" @change="loadDetail">
        <el-option v-for="item in releases" :key="item.title" :label="`${item.version} - ${item.title}`" :value="item.title" />
      </el-select>

      <el-table :data="releases" border height="220">
        <el-table-column prop="version" label="版本" width="160" />
        <el-table-column prop="date" label="日期" width="130" />
        <el-table-column prop="product_line" label="分类" width="160" />
        <el-table-column prop="title" label="Wiki 页" min-width="240" />
        <el-table-column prop="summary" label="摘要" min-width="240" />
      </el-table>
    </el-card>

    <el-card class="card">
      <template #header>编辑版本</template>
      <div class="form-grid">
        <el-input v-model="form.version_name" placeholder="V5.3.8.3"><template #prepend>版本号</template></el-input>
        <el-input v-model="form.release_date" placeholder="YYYY-MM-DD"><template #prepend>发布日期</template></el-input>
        <el-input v-model="form.commit" class="full-row" placeholder="git commit hash"><template #prepend>Commit</template></el-input>
        <el-select v-model="form.product_line" class="full-row" clearable filterable placeholder="版本分类（可选）">
          <el-option v-for="item in projectCategories" :key="item.key" :label="item.title || item.key" :value="item.title || item.key" />
        </el-select>
        <el-input v-model="form.changelog" class="full-row" type="textarea" :rows="6" placeholder="每行一条变更说明" />
        <el-input v-model="filesInfo" class="full-row" type="textarea" :rows="4" readonly placeholder="已有附件" />
        <el-checkbox v-model="replaceAttachments" class="full-row">替换旧附件列表；不勾选则保留旧附件并追加新附件</el-checkbox>
        <el-upload class="full-row" drag multiple :auto-upload="false" :on-change="onFileChange" :on-remove="onFileRemove">
          <el-icon><UploadFilled /></el-icon>
          <div class="el-upload__text">拖入新增固件文件，或点击选择</div>
        </el-upload>
      </div>

      <el-divider content-position="left">发布邮件（可选）</el-divider>
      <el-checkbox v-model="noticeEnabled">更新成功后发送邮件</el-checkbox>
      <div v-if="noticeEnabled" class="form-grid" style="margin-top: 12px">
        <el-radio-group v-model="mailScope" @change="loadContacts">
          <el-radio-button v-for="scope in meta.mail_scopes" :key="scope.value" :label="scope.value">{{ scope.label }}</el-radio-button>
        </el-radio-group>
        <el-select v-model="selectedTemplateNames" multiple filterable placeholder="选择联系人模板" @change="applyContactTemplates">
          <el-option v-for="item in contactTemplates" :key="item.name" :label="item.name" :value="item.name" />
        </el-select>
        <el-select v-model="mailTo" multiple filterable placeholder="选择收件人">
          <el-option v-for="item in contactsTo" :key="item" :label="contactLabel(item)" :value="item" />
        </el-select>
        <el-select v-model="mailCc" multiple filterable placeholder="选择抄送">
          <el-option v-for="item in contactsCc" :key="item" :label="contactLabel(item)" :value="item" />
        </el-select>
        <el-input v-model="manualMailTo" class="full-row" type="textarea" :rows="2" placeholder="手动输入收件人，可用逗号、分号、空格或换行分隔" />
        <el-input v-model="manualMailCc" class="full-row" type="textarea" :rows="2" placeholder="手动输入抄送，可用逗号、分号、空格或换行分隔" />
        <el-input v-model="mailSubject" class="full-row" placeholder="邮件主题" @input="mailContentEdited = true"><template #prepend>邮件主题</template></el-input>
        <el-input v-model="mailBody" class="full-row" type="textarea" :rows="10" placeholder="邮件正文" @input="mailContentEdited = true" />
        <div class="full-row toolbar"><el-button @click="resetMailContent">重新生成邮件内容</el-button></div>
      </div>

      <div class="toolbar" style="margin-top: 16px">
        <el-button type="primary" :disabled="!selectedWikiTitle" :loading="publishing" @click="publish">预览并更新到 Redmine</el-button>
        <el-button v-if="canRetryNotice" :loading="retryingNotice" type="warning" @click="retryNotice">重发邮件</el-button>
        <el-button v-if="logs.length" @click="logDialogVisible = true">查看日志</el-button>
      </div>
      <el-alert v-if="status" class="card status-text" :type="canRetryNotice ? 'warning' : 'success'" :closable="false" show-icon>
        <template #title>{{ status }}</template>
      </el-alert>
    </el-card>

    <el-card v-if="selectedWikiTitle" class="card">
      <template #header>版本操作记录</template>
      <el-tabs>
        <el-tab-pane label="发布记录">
          <el-table :data="publishHistory" border height="260">
            <el-table-column prop="created_at" label="时间" width="160" />
            <el-table-column prop="action" label="操作" width="120" />
            <el-table-column label="发布" width="100"><template #default="scope">{{ statusLabel(scope.row, 'release_status') }}</template></el-table-column>
            <el-table-column label="附件" width="100"><template #default="scope">{{ statusLabel(scope.row, 'file_status') }}</template></el-table-column>
            <el-table-column label="Wiki" width="100"><template #default="scope">{{ statusLabel(scope.row, 'wiki_status') }}</template></el-table-column>
            <el-table-column label="索引" width="100"><template #default="scope">{{ statusLabel(scope.row, 'index_status') }}</template></el-table-column>
            <el-table-column label="邮件" width="100"><template #default="scope">{{ statusLabel(scope.row, 'mail_status') }}</template></el-table-column>
            <el-table-column prop="status_summary" label="状态摘要" min-width="260" show-overflow-tooltip />
            <el-table-column prop="error_message" label="错误" min-width="240" show-overflow-tooltip />
            <el-table-column label="恢复" width="180" fixed="right">
              <template #default="scope">
                <template v-if="(scope.row.recover_actions || []).length">
                  <el-button
                    v-for="action in scope.row.recover_actions"
                    :key="action.action"
                    link
                    type="primary"
                    :loading="recoveringHistoryId === scope.row.id && recoveringAction === action.action"
                    @click="recoverHistory(scope.row, action.action)"
                  >{{ action.label }}</el-button>
                </template>
                <span v-else>-</span>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
        <el-tab-pane label="邮件记录">
          <el-table :data="mailHistory" border height="220">
            <el-table-column prop="created_at" label="时间" width="160" />
            <el-table-column prop="send_type" label="类型" width="100" />
            <el-table-column prop="scope" label="范围" width="90" />
            <el-table-column prop="status" label="状态" width="90" />
            <el-table-column prop="subject" label="主题" min-width="220" />
            <el-table-column label="收件人" width="100"><template #default="scope">{{ scope.row.to_addrs?.length || 0 }}</template></el-table-column>
            <el-table-column prop="error_message" label="错误" min-width="240" />
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <el-dialog v-model="logDialogVisible" title="执行日志" width="820px" destroy-on-close>
      <div class="release-log"><div v-for="(item, index) in logs" :key="index">{{ index + 1 }}. {{ item }}</div></div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox, type UploadFile, type UploadFiles } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import {
  errorLogs,
  errorMessage,
  getContacts,
  getMailHistory,
  getProjectReleaseCategories,
  getPublishHistory,
  getReleaseDetail,
  listReleases,
  previewRelease,
  publishRelease,
  recoverPublishHistory,
  sendReleaseNotice,
  type MailHistoryItem,
  type PublishHistoryItem
} from '../api/http'
import type { ContactTemplateConfig, MetaInfo, Project, ReleaseSummary } from '../types'

const props = defineProps<{ projects: Project[]; meta: MetaInfo; mailVersion: number }>()
const projectId = ref(props.projects[0]?.identifier || '')
const filterProductLine = ref('')
const selectedWikiTitle = ref('')
const releases = ref<ReleaseSummary[]>([])
const projectCategories = ref<Array<{ key: string; title: string }>>([])
const publishHistory = ref<PublishHistoryItem[]>([])
const mailHistory = ref<MailHistoryItem[]>([])
const loadingReleases = ref(false)
const publishing = ref(false)
const retryingNotice = ref(false)
const recoveringHistoryId = ref<number | null>(null)
const recoveringAction = ref('')
const status = ref('')
const logs = ref<string[]>([])
const logDialogVisible = ref(false)
const canRetryNotice = ref(false)
const filesInfo = ref('')
const replaceAttachments = ref(false)
const noticeEnabled = ref(false)
const mailScope = ref('internal')
const contactsTo = ref<string[]>([])
const contactsCc = ref<string[]>([])
const contactTemplates = ref<ContactTemplateConfig[]>([])
const selectedTemplateNames = ref<string[]>([])
const mailTo = ref<string[]>([])
const mailCc = ref<string[]>([])
const manualMailTo = ref('')
const manualMailCc = ref('')
const mailSubject = ref('')
const mailBody = ref('')
const mailContentEdited = ref(false)
const selectedFiles = ref<File[]>([])
const form = reactive({ version_name: '', release_date: props.meta.today || new Date().toISOString().slice(0, 10), commit: '', product_line: '', changelog: '' })

watch(() => props.projects, (value) => { if (!projectId.value && value.length) projectId.value = value[0].identifier }, { immediate: true })
watch(() => props.meta, (value) => { if (!form.release_date && value.today) form.release_date = value.today }, { immediate: true })
watch(() => props.mailVersion, loadContacts)
watch(
  () => [noticeEnabled.value, projectId.value, mailScope.value, form.version_name, form.release_date, form.commit, form.product_line, form.changelog, selectedFiles.value.map((file) => file.name).join('|'), filesInfo.value, replaceAttachments.value],
  () => { if (noticeEnabled.value && !mailContentEdited.value) generateMailContent() }
)

function statusLabel(row: PublishHistoryItem, field: 'release_status' | 'file_status' | 'wiki_status' | 'index_status' | 'mail_status'): string {
  return String(row[`${field}_label`] || row[field] || '')
}

function onFileChange(_file: UploadFile, files: UploadFiles) { selectedFiles.value = files.map((item) => item.raw).filter(Boolean) as File[] }
function onFileRemove(_file: UploadFile, files: UploadFiles) { selectedFiles.value = files.map((item) => item.raw).filter(Boolean) as File[] }

async function loadReleases() {
  if (!projectId.value) return
  loadingReleases.value = true
  try {
    releases.value = await listReleases(projectId.value, filterProductLine.value)
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    loadingReleases.value = false
  }
}

async function reloadAll() {
  selectedWikiTitle.value = ''
  publishHistory.value = []
  mailHistory.value = []
  await loadCategories()
  await loadReleases()
}

async function loadCategories() {
  if (!projectId.value) return
  try {
    const data = await getProjectReleaseCategories(projectId.value)
    projectCategories.value = data.categories
    const values = new Set(projectCategories.value.map((item) => item.title || item.key))
    if (filterProductLine.value && !values.has(filterProductLine.value)) filterProductLine.value = ''
    if (form.product_line && !values.has(form.product_line)) form.product_line = ''
  } catch (error) {
    projectCategories.value = []
    ElMessage.error(errorMessage(error))
  }
}

async function loadDetail() {
  if (!projectId.value || !selectedWikiTitle.value) return
  try {
    const detail = await getReleaseDetail(projectId.value, selectedWikiTitle.value)
    form.version_name = detail.version_name
    form.release_date = detail.release_date
    form.commit = detail.commit
    form.product_line = detail.product_line
    form.changelog = detail.changelog
    filesInfo.value = detail.files_info
    selectedFiles.value = []
    canRetryNotice.value = false
    await loadHistories()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

async function loadHistories() {
  if (!projectId.value || !selectedWikiTitle.value) return
  const [publishData, mailData] = await Promise.all([
    getPublishHistory({ project_id: projectId.value, wiki_title: selectedWikiTitle.value, version_name: form.version_name, limit: 20 }),
    getMailHistory({ project_id: projectId.value, wiki_title: selectedWikiTitle.value, version_name: form.version_name, limit: 20 })
  ])
  publishHistory.value = publishData.items
  mailHistory.value = mailData.items
}

async function loadContacts() {
  try {
    const data = await getContacts(mailScope.value)
    contactsTo.value = data.contacts_to
    contactsCc.value = data.contacts_cc
    contactTemplates.value = data.contact_templates || []
    selectedTemplateNames.value = []
    mailTo.value = []
    mailCc.value = []
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

function mergeEmails(groups: string[][]): string[] {
  const seen = new Set<string>()
  const result: string[] = []
  groups.flat().forEach((email) => {
    const value = email.trim()
    const key = value.toLowerCase()
    if (value && !seen.has(key)) { seen.add(key); result.push(value) }
  })
  return result
}

function contactLabel(email: string): string {
  const key = email.trim().toLowerCase()
  for (const template of contactTemplates.value) {
    const contact = [...template.contacts_to, ...template.contacts_cc].find((item) => item.email.trim().toLowerCase() === key)
    if (contact) return `${contact.name || contact.email.split('@')[0]} <${contact.email}>`
  }
  return email
}

function applyContactTemplates() {
  const selected = contactTemplates.value.filter((item) => selectedTemplateNames.value.includes(item.name))
  mailTo.value = mergeEmails(selected.map((item) => item.contacts_to.map((contact) => contact.email)))
  mailCc.value = mergeEmails(selected.map((item) => item.contacts_cc.map((contact) => contact.email)))
}

function changelogLines(): string[] { return form.changelog.split(/\r?\n/).map((item) => item.trim()).filter(Boolean) }
function attachmentNames(): string[] {
  const selected = selectedFiles.value.map((file) => file.name).filter(Boolean)
  if (replaceAttachments.value || selected.length) return selected
  return filesInfo.value.split(/\r?\n/).map((line) => line.replace(/^-\s*/, '').trim().split(/\s+/)[0]).filter((item) => item && item !== '（无已有附件）')
}
function uniqueItems(items: string[]): string[] {
  const seen = new Set<string>()
  const result: string[] = []
  items.forEach((item) => { const value = item.trim(); const key = value.toLowerCase(); if (value && !seen.has(key)) { seen.add(key); result.push(value) } })
  return result
}
function releaseNameFromAttachments(names: string[]): string {
  const models: string[] = []
  let parsedVersion = ''
  let parsedDate = ''
  names.forEach((filename) => {
    const stem = filename.replace(/\.[A-Za-z0-9]+$/, '')
    const parts = stem.split('_').filter(Boolean)
    const versionIndex = parts.findIndex((part) => /^V?\d+(?:\.\d+)+$/i.test(part))
    const dateIndex = parts.findIndex((part) => /^\d{8}$|^\d{4}-\d{2}-\d{2}$/.test(part))
    if (versionIndex > 0) {
      const model = parts.slice(0, versionIndex).join('_')
      if (model) models.push(model)
      if (!parsedVersion) parsedVersion = parts[versionIndex]
      if (dateIndex > versionIndex && !parsedDate) parsedDate = parts[dateIndex]
    } else if (stem) models.push(stem)
  })
  const cleanModels = uniqueItems(models)
  const modelText = cleanModels.length > 4 ? `${cleanModels.slice(0, 4).join('/')} 等${cleanModels.length}个机型` : cleanModels.join('/')
  return [modelText, parsedVersion || form.version_name, parsedDate || form.release_date.replace(/-/g, '')].filter(Boolean).join(' ')
}
function generatedMailSubject(): string { const releaseName = releaseNameFromAttachments(attachmentNames()); return mailScope.value === 'external' ? `Firmware Release ${releaseName}` : `固件版本发布 ${releaseName}` }
function generatedMailBody(): string {
  const releaseName = releaseNameFromAttachments(attachmentNames())
  const changelog = changelogLines().map((item, index) => `${index + 1}. ${item}`).join('\n') || '（无）'
  const attachments = attachmentNames().map((name) => `- ${name}`).join('\n') || (mailScope.value === 'external' ? '（本次邮件未附加文件，请联系相关人员获取固件文件）' : '（本次邮件未附加文件，请查看 Redmine 项目文件）')
  if (mailScope.value === 'external') return ['您好，', '', '固件版本已发布，请查收。', '', `版本：${releaseName}`, `发布日期：${form.release_date}`, '', `变更说明：\n${changelog}`, '', `附件：\n${attachments}`, '', '如有问题，请联系技术支持人员。'].join('\n')
  return ['固件版本已发布。', '', `版本：${releaseName}`, `发布日期：${form.release_date}`, `Commit：${form.commit}`, '', `变更说明：\n${changelog}`, '', `附件：\n${attachments}`, '', 'Wiki：{{wiki_url}}', '项目文件：{{files_url}}'].join('\n')
}
function generateMailContent() { mailSubject.value = generatedMailSubject(); mailBody.value = generatedMailBody() }
function resetMailContent() { mailContentEdited.value = false; generateMailContent() }
function buildReleaseFormData(): FormData {
  const data = new FormData()
  data.append('project_id', projectId.value)
  data.append('version_name', form.version_name)
  data.append('release_date', form.release_date)
  data.append('commit', form.commit)
  data.append('product_line', form.product_line)
  data.append('changelog', form.changelog)
  data.append('replace_attachments', String(replaceAttachments.value))
  data.append('edit_title', selectedWikiTitle.value)
  data.append('notice_enabled', String(noticeEnabled.value))
  data.append('mail_scope', mailScope.value)
  data.append('mail_to', [mailTo.value.join(','), manualMailTo.value].filter(Boolean).join(','))
  data.append('mail_cc', [mailCc.value.join(','), manualMailCc.value].filter(Boolean).join(','))
  data.append('mail_subject', mailSubject.value)
  data.append('mail_body', mailBody.value)
  selectedFiles.value.forEach((file) => data.append('files', file))
  return data
}
function buildNoticeFormData(): FormData {
  const data = new FormData()
  data.append('project_id', projectId.value)
  data.append('wiki_title', selectedWikiTitle.value)
  data.append('version_name', form.version_name)
  data.append('mail_scope', mailScope.value)
  data.append('mail_to', [mailTo.value.join(','), manualMailTo.value].filter(Boolean).join(','))
  data.append('mail_cc', [mailCc.value.join(','), manualMailCc.value].filter(Boolean).join(','))
  data.append('mail_subject', mailSubject.value)
  data.append('mail_body', mailBody.value)
  selectedFiles.value.forEach((file) => data.append('files', file))
  return data
}
async function confirmPreview(): Promise<boolean> {
  const preview = await previewRelease(buildReleaseFormData())
  logs.value = preview.logs || []
  try {
    await ElMessageBox.confirm(preview.summary || '确认更新？', '更新前预览', { confirmButtonText: '确认更新', cancelButtonText: '取消', type: 'warning', customStyle: { whiteSpace: 'pre-line', maxWidth: '760px' } })
    return true
  } catch { return false }
}
async function publish() {
  if (!projectId.value || !selectedWikiTitle.value) return ElMessage.warning('请选择要编辑的版本')
  publishing.value = true
  status.value = ''
  canRetryNotice.value = false
  logs.value = ['正在生成更新前预览']
  logDialogVisible.value = true
  try {
    const confirmed = await confirmPreview()
    if (!confirmed) { logs.value = ['已取消更新']; return }
    logs.value = ['已确认更新，等待后端执行']
    const result = await publishRelease(buildReleaseFormData())
    releases.value = result.releases
    logs.value = result.logs || []
    selectedWikiTitle.value = result.title
    canRetryNotice.value = noticeEnabled.value && result.mail_status === 'failed'
    status.value = [`更新完成：${result.title}`, result.result_summary, result.notice_message].filter(Boolean).join('\n')
    await loadHistories()
    ElMessage.success('更新流程完成')
  } catch (error) {
    const message = errorMessage(error)
    const backendLogs = errorLogs(error)
    logs.value = backendLogs.length ? [...backendLogs, `执行失败：${message}`] : [`执行失败：${message}`]
    ElMessage.error(message)
  } finally {
    publishing.value = false
    logDialogVisible.value = true
  }
}
async function retryNotice() {
  if (!selectedWikiTitle.value) return ElMessage.warning('没有可重发邮件的版本')
  retryingNotice.value = true
  logs.value = ['正在重发邮件']
  logDialogVisible.value = true
  try {
    const result = await sendReleaseNotice(buildNoticeFormData())
    logs.value = result.logs || []
    status.value = `${status.value}\n邮件重发：成功，${result.message}`
    canRetryNotice.value = false
    await loadHistories()
    ElMessage.success('邮件重发成功')
  } catch (error) {
    const message = errorMessage(error)
    const backendLogs = errorLogs(error)
    logs.value = backendLogs.length ? [...backendLogs, `执行失败：${message}`] : [`执行失败：${message}`]
    ElMessage.error(message)
  } finally {
    retryingNotice.value = false
    logDialogVisible.value = true
  }
}
async function recoverHistory(row: PublishHistoryItem, action: 'rebuild_index' | 'continue') {
  try {
    const actionLabel = row.recover_actions?.find((item) => item.action === action)?.label || action
    await ElMessageBox.confirm(`确认执行恢复操作：${actionLabel}？`, '恢复发布记录', { confirmButtonText: '确认执行', cancelButtonText: '取消', type: 'warning' })
    recoveringHistoryId.value = row.id
    recoveringAction.value = action
    logs.value = [`正在执行恢复操作：${actionLabel}`]
    logDialogVisible.value = true
    const result = await recoverPublishHistory(row.id, action)
    logs.value = result.logs || []
    status.value = result.message
    await loadHistories()
    if (action === 'continue') await loadReleases()
    ElMessage.success(result.message)
  } catch (error) {
    const message = errorMessage(error)
    const backendLogs = errorLogs(error)
    if (message !== 'cancel') logs.value = backendLogs.length ? [...backendLogs, `执行失败：${message}`] : [`执行失败：${message}`]
    if (message !== 'cancel') ElMessage.error(message)
  } finally {
    recoveringHistoryId.value = null
    recoveringAction.value = ''
  }
}
onMounted(async () => { await loadContacts(); await loadCategories(); await loadReleases() })
</script>
