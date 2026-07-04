<template>
  <div>
    <el-card class="card">
      <div class="toolbar">
        <el-select v-model="projectId" placeholder="选择项目" filterable style="width: 320px" @change="reloadProject">
          <el-option v-for="project in projects" :key="project.identifier" :label="`${project.name} (${project.identifier})`" :value="project.identifier" />
        </el-select>
        <el-select v-model="filterProductLine" clearable placeholder="全部分类" style="width: 220px" @change="loadReleases">
          <el-option label="全部分类" value="" />
          <el-option v-for="item in projectCategories" :key="item.key" :label="item.title || item.key" :value="item.title || item.key" />
        </el-select>
        <el-button :loading="loadingReleases" @click="loadReleases">刷新列表</el-button>
      </div>

      <el-table class="release-table" :data="releases" border height="260">
        <el-table-column prop="version" label="版本" width="160" />
        <el-table-column prop="date" label="日期" width="130" />
        <el-table-column prop="product_line" label="分类" width="160" />
        <el-table-column prop="title" label="Wiki 页" min-width="240" />
        <el-table-column prop="summary" label="摘要" min-width="240" />
      </el-table>
    </el-card>

    <el-card class="card">
      <template #header>发布新版本</template>
      <div class="form-grid">
        <el-input v-model="form.version_name" placeholder="V5.3.8.3"><template #prepend>版本号</template></el-input>
        <el-input v-model="form.release_date" placeholder="YYYY-MM-DD"><template #prepend>发布日期</template></el-input>
        <el-input v-model="form.commit" class="full-row" placeholder="git commit hash"><template #prepend>Commit</template></el-input>
        <el-select v-model="form.product_line" class="full-row" clearable filterable placeholder="版本分类（可选）">
          <el-option v-for="item in projectCategories" :key="item.key" :label="item.title || item.key" :value="item.title || item.key" />
        </el-select>
        <el-input v-model="form.changelog" class="full-row" type="textarea" :rows="6" placeholder="每行一条变更说明" />
        <el-upload class="full-row" drag multiple :auto-upload="false" :on-change="onFileChange" :on-remove="onFileRemove">
          <el-icon><UploadFilled /></el-icon>
          <div class="el-upload__text">拖入 .bin 固件文件，或点击选择</div>
        </el-upload>
      </div>

      <el-divider content-position="left">发布邮件（可选）</el-divider>
      <el-checkbox v-model="noticeEnabled">发布成功后发送邮件</el-checkbox>
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
        <el-input v-model="mailSubject" class="full-row" placeholder="邮件主题" @input="mailContentEdited = true">
          <template #prepend>邮件主题</template>
        </el-input>
        <el-input v-model="mailBody" class="full-row" type="textarea" :rows="10" placeholder="邮件正文" @input="mailContentEdited = true" />
        <div class="full-row toolbar">
          <el-button @click="resetMailContent">重新生成邮件内容</el-button>
        </div>
      </div>

      <div class="toolbar" style="margin-top: 16px">
        <el-button type="primary" :loading="publishing" @click="publish">发布到 Redmine</el-button>
      </div>
      <el-alert v-if="status" class="card status-text" type="success" :closable="false" show-icon>
        <template #title>{{ status }}</template>
      </el-alert>
      <div v-if="logs.length" class="release-log">
        <div v-for="(item, index) in logs" :key="index">{{ index + 1 }}. {{ item }}</div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, type UploadFile, type UploadFiles } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import { errorLogs, errorMessage, getContacts, getProjectReleaseCategories, listReleases, publishRelease } from '../api/http'
import type { ContactTemplateConfig, MetaInfo, Project, ReleaseSummary } from '../types'

const props = defineProps<{ projects: Project[]; meta: MetaInfo; mailVersion: number }>()
const projectId = ref(props.projects[0]?.identifier || '')
const filterProductLine = ref('')
const releases = ref<ReleaseSummary[]>([])
const projectCategories = ref<Array<{ key: string; title: string }>>([])
const loadingReleases = ref(false)
const publishing = ref(false)
const status = ref('')
const logs = ref<string[]>([])
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

const form = reactive({
  version_name: '',
  release_date: props.meta.today || new Date().toISOString().slice(0, 10),
  commit: '',
  product_line: '',
  changelog: ''
})

watch(
  () => props.meta,
  (value) => {
    if (!form.release_date && value.today) form.release_date = value.today
  },
  { immediate: true }
)

watch(
  () => props.projects,
  (value) => {
    if (!projectId.value && value.length) projectId.value = value[0].identifier
  },
  { immediate: true }
)

watch(() => props.mailVersion, loadContacts)

watch(
  () => [
    noticeEnabled.value,
    projectId.value,
    mailScope.value,
    form.version_name,
    form.release_date,
    form.commit,
    form.product_line,
    form.changelog,
    selectedFiles.value.map((file) => file.name).join('|')
  ],
  () => {
    if (noticeEnabled.value && !mailContentEdited.value) generateMailContent()
  }
)

function onFileChange(_file: UploadFile, files: UploadFiles) {
  selectedFiles.value = files.map((item) => item.raw).filter(Boolean) as File[]
}

function onFileRemove(_file: UploadFile, files: UploadFiles) {
  selectedFiles.value = files.map((item) => item.raw).filter(Boolean) as File[]
}

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

async function reloadProject() {
  await loadCategories()
  await loadReleases()
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
    if (value && !seen.has(key)) {
      seen.add(key)
      result.push(value)
    }
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

function changelogLines(): string[] {
  return form.changelog.split(/\r?\n/).map((item) => item.trim()).filter(Boolean)
}

function attachmentNames(): string[] {
  return selectedFiles.value.map((file) => file.name).filter(Boolean)
}

function generatedMailSubject(): string {
  if (mailScope.value === 'external') {
    return `[Firmware Release][${projectId.value}] ${form.version_name} - ${form.product_line}`
  }
  return `[${projectId.value}] 固件版本发布 ${form.version_name} - ${form.product_line}`
}

function generatedMailBody(): string {
  const changelog = changelogLines().map((item, index) => `${index + 1}. ${item}`).join('\n') || '（无）'
  const attachments = attachmentNames()
    .map((name) => `- ${name}`)
    .join('\n') || (mailScope.value === 'external' ? '（本次邮件未附加文件，请联系相关人员获取固件文件）' : '（本次邮件未附加文件，请查看 Redmine 项目文件）')
  if (mailScope.value === 'external') {
    return [
      '您好，',
      '',
      '固件版本已发布，请查收。',
      '',
      `项目：${projectId.value}`,
      `版本：${form.version_name}`,
      `产品线：${form.product_line}`,
      `发布日期：${form.release_date}`,
      '',
      `变更说明：\n${changelog}`,
      '',
      `附件：\n${attachments}`,
      '',
      '如有问题，请联系技术支持人员。'
    ].join('\n')
  }
  return [
    '固件版本已发布。',
    '',
    `项目：${projectId.value}`,
    `版本：${form.version_name}`,
    `产品线：${form.product_line}`,
    `发布日期：${form.release_date}`,
    `Commit：${form.commit}`,
    '',
    `变更说明：\n${changelog}`,
    '',
    `附件：\n${attachments}`,
    '',
    'Wiki：{{wiki_url}}',
    '项目文件：{{files_url}}'
  ].join('\n')
}

function generateMailContent() {
  mailSubject.value = generatedMailSubject()
  mailBody.value = generatedMailBody()
}

function resetMailContent() {
  mailContentEdited.value = false
  generateMailContent()
}

async function publish() {
  if (!projectId.value) return ElMessage.warning('请选择项目')
  publishing.value = true
  status.value = ''
  logs.value = ['已提交发布请求，等待后端执行']
  try {
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
    const result = await publishRelease(data)
    releases.value = result.releases
    logs.value = result.logs || []
    status.value = `发布成功：${result.title}${result.notice_message ? '\n' + result.notice_message : ''}`
    ElMessage.success('发布成功')
  } catch (error) {
    const message = errorMessage(error)
    const backendLogs = errorLogs(error)
    logs.value = backendLogs.length ? [...backendLogs, `执行失败：${message}`] : [`执行失败：${message}`]
    ElMessage.error(errorMessage(error))
  } finally {
    publishing.value = false
  }
}

onMounted(async () => {
  await loadContacts()
  await loadCategories()
  await loadReleases()
})
</script>
