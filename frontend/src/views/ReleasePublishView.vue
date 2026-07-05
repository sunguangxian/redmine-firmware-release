<template>
  <div>
    <el-card class="card">
      <div class="toolbar">
        <el-select v-model="projectId" :disabled="busy" placeholder="选择项目" filterable style="width: 320px" @change="reloadProject">
          <el-option v-for="project in projects" :key="project.identifier" :label="`${project.name} (${project.identifier})`" :value="project.identifier" />
        </el-select>
        <el-select v-model="filterProductLine" :disabled="busy" clearable placeholder="全部分类" style="width: 220px" @change="loadReleases">
          <el-option label="全部分类" value="" />
          <el-option v-for="item in projectCategories" :key="item.key" :label="item.title || item.key" :value="item.title || item.key" />
        </el-select>
        <el-button :disabled="busy" :loading="loadingReleases" @click="loadReleases">刷新列表</el-button>
      </div>

      <el-table class="release-table" :data="releases" border height="260">
        <el-table-column prop="version" label="版本" width="160" />
        <el-table-column prop="date" label="日期" width="130" />
        <el-table-column prop="product_line" label="分类" width="160" />
        <el-table-column label="Wiki 页" min-width="240">
          <template #default="{ row }">{{ row.display_title || row.title }}</template>
        </el-table-column>
        <el-table-column prop="summary" label="摘要" min-width="240" />
      </el-table>
    </el-card>

    <el-card class="card">
      <template #header>发布新版本</template>
      <div class="form-grid">
        <el-input v-model="form.version_name" :disabled="busy" placeholder="V5.3.8.3"><template #prepend>版本号</template></el-input>
        <el-input v-model="form.release_date" :disabled="busy" placeholder="YYYY-MM-DD"><template #prepend>发布日期</template></el-input>
        <el-input v-model="form.commit" :disabled="busy" class="full-row" placeholder="git commit hash"><template #prepend>Commit</template></el-input>
        <el-select v-model="form.product_line" :disabled="busy" class="full-row" clearable filterable placeholder="版本分类（可选）">
          <el-option v-for="item in projectCategories" :key="item.key" :label="item.title || item.key" :value="item.title || item.key" />
        </el-select>
        <el-input v-model="form.changelog" :disabled="busy" class="full-row" type="textarea" :rows="6" placeholder="每行一条变更说明" />
        <el-upload class="full-row" drag multiple :auto-upload="false" :disabled="busy" :on-change="onFileChange" :on-remove="onFileRemove">
          <el-icon><UploadFilled /></el-icon>
          <div class="el-upload__text">拖入固件文件，或点击选择</div>
        </el-upload>
        <ReleaseFileList :files="selectedFiles" />
      </div>

      <el-divider content-position="left">发布邮件（可选）</el-divider>
      <el-checkbox v-model="noticeEnabled" :disabled="busy">发布成功后发送邮件</el-checkbox>
      <div v-if="noticeEnabled" class="form-grid" style="margin-top: 12px">
        <el-radio-group v-model="mailScope" :disabled="busy" @change="loadContacts">
          <el-radio-button v-for="scope in meta.mail_scopes" :key="scope.value" :label="scope.value">{{ scope.label }}</el-radio-button>
        </el-radio-group>
        <el-select v-model="selectedTemplateNames" :disabled="busy" multiple filterable placeholder="选择联系人模板" @change="applyContactTemplates">
          <el-option v-for="item in contactTemplates" :key="item.name" :label="item.name" :value="item.name" />
        </el-select>
        <el-select v-model="mailTo" :disabled="busy" multiple filterable placeholder="选择收件人">
          <el-option v-for="item in contactsTo" :key="item" :label="contactLabel(item)" :value="item" />
        </el-select>
        <el-select v-model="mailCc" :disabled="busy" multiple filterable placeholder="选择抄送">
          <el-option v-for="item in contactsCc" :key="item" :label="contactLabel(item)" :value="item" />
        </el-select>
        <el-input v-model="manualMailTo" :disabled="busy" class="full-row" type="textarea" :rows="2" placeholder="手动输入收件人，可用逗号、分号、空格或换行分隔" />
        <el-input v-model="manualMailCc" :disabled="busy" class="full-row" type="textarea" :rows="2" placeholder="手动输入抄送，可用逗号、分号、空格或换行分隔" />
        <el-input v-model="mailSubject" :disabled="busy" class="full-row" placeholder="邮件主题" @input="mailContentEdited = true">
          <template #prepend>邮件主题</template>
        </el-input>
        <el-input v-model="mailBody" :disabled="busy" class="full-row" type="textarea" :rows="10" placeholder="邮件正文" @input="mailContentEdited = true" />
        <div class="full-row toolbar">
          <el-button :disabled="busy" @click="resetMailContent">重新生成邮件内容</el-button>
        </div>
      </div>

      <div class="toolbar" style="margin-top: 16px">
        <el-button type="primary" :disabled="busy" :loading="publishing" @click="publish">预览并发布到 Redmine</el-button>
        <el-button v-if="canRetryNotice" :disabled="busy" :loading="retryingNotice" type="warning" @click="retryNotice">重发邮件</el-button>
        <el-button v-if="logs.length" @click="logDialogVisible = true">查看日志</el-button>
      </div>
      <el-alert v-if="status" class="card status-text" :type="canRetryNotice ? 'warning' : 'success'" :closable="false" show-icon>
        <template #title>{{ status }}</template>
      </el-alert>
    </el-card>

    <ExecutionLogDialog v-model="logDialogVisible" :logs="logs" />
    <ReleasePreviewDialog v-model="previewDialogVisible" title="发布前预览" :plan="previewPlan" @confirm="confirmPreviewDialog" @cancel="cancelPreviewDialog" />
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, type UploadFile, type UploadFiles } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import ExecutionLogDialog from '../components/ExecutionLogDialog.vue'
import ReleaseFileList from '../components/ReleaseFileList.vue'
import ReleasePreviewDialog from '../components/ReleasePreviewDialog.vue'
import { errorLogs, errorMessage, getContacts, getProjectReleaseCategories, listReleases, previewRelease, publishRelease, sendReleaseNotice, type ReleasePlan } from '../api/http'
import type { ContactTemplateConfig, MetaInfo, Project, ReleaseSummary } from '../types'
import { buildMailBody, buildMailSubject, changelogLines, friendlyReleaseError, hasReleaseDraft, mergeEmails, splitEmails, validateReleaseInput } from '../utils/releaseUi.js'

const props = defineProps<{ projects: Project[]; meta: MetaInfo; mailVersion: number }>()
const emit = defineEmits<{ (event: 'dirty-change', value: boolean): void }>()
const projectId = ref(props.projects[0]?.identifier || '')
const filterProductLine = ref('')
const releases = ref<ReleaseSummary[]>([])
const projectCategories = ref<Array<{ key: string; title: string }>>([])
const loadingReleases = ref(false)
const publishing = ref(false)
const retryingNotice = ref(false)
const status = ref('')
const logs = ref<string[]>([])
const logDialogVisible = ref(false)
const previewDialogVisible = ref(false)
const previewPlan = ref<(ReleasePlan & { summary?: string }) | null>(null)
let previewResolver: ((value: boolean) => void) | null = null
const canRetryNotice = ref(false)
const lastPublishedTitle = ref('')
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
const busy = computed(() => publishing.value || retryingNotice.value)

const form = reactive({
  version_name: '',
  release_date: props.meta.today || new Date().toISOString().slice(0, 10),
  commit: '',
  product_line: '',
  changelog: ''
})

const isDirty = computed(() => hasReleaseDraft({
  versionName: form.version_name,
  releaseDate: form.release_date,
  commit: form.commit,
  productLine: form.product_line,
  changelog: form.changelog,
  files: selectedFiles.value,
  noticeEnabled: noticeEnabled.value,
  mailSubject: mailSubject.value,
  mailBody: mailBody.value,
}))

watch(isDirty, (value) => emit('dirty-change', value), { immediate: true })
watch(() => props.meta, (value) => { if (!form.release_date && value.today) form.release_date = value.today }, { immediate: true })
watch(() => props.projects, (value) => { if (!projectId.value && value.length) projectId.value = value[0].identifier }, { immediate: true })
watch(() => props.mailVersion, loadContacts)
watch(
  () => [noticeEnabled.value, projectId.value, mailScope.value, form.version_name, form.release_date, form.commit, form.product_line, form.changelog, selectedFiles.value.map((file) => file.name).join('|')],
  () => { if (noticeEnabled.value && !mailContentEdited.value) generateMailContent() }
)

function onBeforeUnload(event: BeforeUnloadEvent) {
  if (!isDirty.value && !publishing.value) return
  event.preventDefault()
  event.returnValue = ''
}

function onFileChange(_file: UploadFile, files: UploadFiles) { selectedFiles.value = files.map((item) => item.raw).filter(Boolean) as File[] }
function onFileRemove(_file: UploadFile, files: UploadFiles) { selectedFiles.value = files.map((item) => item.raw).filter(Boolean) as File[] }

async function loadReleases() {
  if (!projectId.value || busy.value) return
  loadingReleases.value = true
  try { releases.value = await listReleases(projectId.value, filterProductLine.value) } catch (error) { ElMessage.error(friendlyReleaseError(errorMessage(error))) } finally { loadingReleases.value = false }
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
    ElMessage.error(friendlyReleaseError(errorMessage(error)))
  }
}

async function reloadProject() { if (!busy.value) { await loadCategories(); await loadReleases() } }

async function loadContacts() {
  try {
    const data = await getContacts(mailScope.value)
    contactsTo.value = data.contacts_to
    contactsCc.value = data.contacts_cc
    contactTemplates.value = data.contact_templates || []
    selectedTemplateNames.value = []
    mailTo.value = []
    mailCc.value = []
  } catch (error) { ElMessage.error(friendlyReleaseError(errorMessage(error))) }
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

function attachmentNames(): string[] { return selectedFiles.value.map((file) => file.name).filter(Boolean) }
function generateMailContent() {
  mailSubject.value = buildMailSubject(mailScope.value, attachmentNames(), form.version_name, form.release_date)
  mailBody.value = buildMailBody(mailScope.value, attachmentNames(), form.version_name, form.release_date, form.commit, form.changelog)
}
function resetMailContent() { mailContentEdited.value = false; generateMailContent() }

function buildReleaseFormData(): FormData {
  const data = new FormData()
  data.append('project_id', projectId.value)
  data.append('version_name', form.version_name)
  data.append('release_date', form.release_date)
  data.append('commit', form.commit)
  data.append('product_line', form.product_line)
  data.append('changelog', form.changelog)
  data.append('replace_attachments', 'false')
  data.append('edit_title', '')
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
  data.append('wiki_title', lastPublishedTitle.value)
  data.append('version_name', form.version_name)
  data.append('mail_scope', mailScope.value)
  data.append('mail_to', [mailTo.value.join(','), manualMailTo.value].filter(Boolean).join(','))
  data.append('mail_cc', [mailCc.value.join(','), manualMailCc.value].filter(Boolean).join(','))
  data.append('mail_subject', mailSubject.value)
  data.append('mail_body', mailBody.value)
  selectedFiles.value.forEach((file) => data.append('files', file))
  return data
}

function validateBeforeSubmit(): boolean {
  const errors = validateReleaseInput({
    projectId: projectId.value,
    versionName: form.version_name,
    releaseDate: form.release_date,
    commit: form.commit,
    changelog: form.changelog,
    files: selectedFiles.value,
    noticeEnabled: noticeEnabled.value,
    mailTo: mailTo.value,
    manualMailTo: manualMailTo.value,
    mailSubject: mailSubject.value,
    mailBody: mailBody.value,
  })
  if (!errors.length) return true
  logs.value = errors.map((item) => `前端校验失败：${item}`)
  logDialogVisible.value = true
  ElMessage.warning(errors[0])
  return false
}

function confirmPreviewDialog() { previewResolver?.(true); previewResolver = null }
function cancelPreviewDialog() { previewResolver?.(false); previewResolver = null }

async function confirmPreview(): Promise<boolean> {
  const preview = await previewRelease(buildReleaseFormData())
  logs.value = preview.logs || []
  previewPlan.value = preview
  previewDialogVisible.value = true
  return new Promise((resolve) => { previewResolver = resolve })
}

function handleFailure(error: unknown) {
  const message = friendlyReleaseError(errorMessage(error))
  const backendLogs = errorLogs(error)
  logs.value = backendLogs.length ? [...backendLogs, `执行失败：${message}`] : [`执行失败：${message}`]
  ElMessage.error(message)
}

async function publish() {
  if (publishing.value) return
  if (!validateBeforeSubmit()) return
  publishing.value = true
  status.value = ''
  canRetryNotice.value = false
  logs.value = ['正在生成发布前预览']
  logDialogVisible.value = true
  try {
    const confirmed = await confirmPreview()
    if (!confirmed) { logs.value = ['已取消发布']; return }
    logs.value = ['已确认发布，等待后端执行']
    const result = await publishRelease(buildReleaseFormData())
    releases.value = result.releases
    logs.value = result.logs || []
    lastPublishedTitle.value = result.title
    canRetryNotice.value = noticeEnabled.value && result.mail_status === 'failed'
    status.value = [`发布完成：${result.title}`, result.result_summary, result.notice_message].filter(Boolean).join('\n')
    ElMessage.success('发布流程完成')
  } catch (error) {
    handleFailure(error)
  } finally { publishing.value = false; logDialogVisible.value = true }
}

async function retryNotice() {
  if (retryingNotice.value) return
  if (!lastPublishedTitle.value) return ElMessage.warning('没有可重发邮件的版本')
  retryingNotice.value = true
  logs.value = ['正在重发邮件']
  logDialogVisible.value = true
  try {
    const result = await sendReleaseNotice(buildNoticeFormData())
    logs.value = result.logs || []
    status.value = `${status.value}\n邮件重发：成功，${result.message}`
    canRetryNotice.value = false
    ElMessage.success('邮件重发成功')
  } catch (error) {
    handleFailure(error)
  } finally { retryingNotice.value = false; logDialogVisible.value = true }
}

onMounted(async () => {
  window.addEventListener('beforeunload', onBeforeUnload)
  await loadContacts(); await loadCategories(); await loadReleases()
})
onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', onBeforeUnload)
  emit('dirty-change', false)
})
</script>
