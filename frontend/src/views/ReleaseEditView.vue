<template>
  <div>
    <el-card class="card">
      <div class="toolbar">
        <el-select v-model="projectId" placeholder="选择项目" filterable style="width: 320px" @change="reloadAll">
          <el-option v-for="project in projects" :key="project.identifier" :label="`${project.name} (${project.identifier})`" :value="project.identifier" />
        </el-select>
        <el-select v-model="filterProductLine" clearable placeholder="全部分类" style="width: 220px" @change="loadReleases">
          <el-option label="全部分类" value="" />
          <el-option v-for="item in meta.product_lines" :key="item" :label="item" :value="item" />
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
        <el-select v-model="form.product_line" class="full-row" clearable filterable allow-create placeholder="版本分类（可选）">
          <el-option v-for="item in meta.product_lines" :key="item" :label="item" :value="item" />
        </el-select>
        <el-input v-model="form.changelog" class="full-row" type="textarea" :rows="6" placeholder="每行一条变更说明" />
        <el-input v-model="filesInfo" class="full-row" type="textarea" :rows="4" readonly placeholder="已有附件" />
        <el-checkbox v-model="replaceAttachments" class="full-row">替换旧附件列表；不勾选则保留旧附件并追加新附件</el-checkbox>
        <el-upload class="full-row" drag multiple :auto-upload="false" :on-change="onFileChange" :on-remove="onFileRemove">
          <el-icon><UploadFilled /></el-icon>
          <div class="el-upload__text">拖入新增 .bin 固件文件，或点击选择</div>
        </el-upload>
      </div>

      <el-divider content-position="left">发布邮件（可选）</el-divider>
      <el-checkbox v-model="noticeEnabled">更新成功后发送邮件</el-checkbox>
      <div v-if="noticeEnabled" class="form-grid" style="margin-top: 12px">
        <el-radio-group v-model="mailScope" @change="loadContacts">
          <el-radio-button v-for="scope in meta.mail_scopes" :key="scope.value" :label="scope.value">{{ scope.label }}</el-radio-button>
        </el-radio-group>
        <div></div>
        <el-select v-model="mailTo" multiple filterable placeholder="选择收件人">
          <el-option v-for="item in contactsTo" :key="item" :label="item" :value="item" />
        </el-select>
        <el-select v-model="mailCc" multiple filterable placeholder="选择抄送">
          <el-option v-for="item in contactsCc" :key="item" :label="item" :value="item" />
        </el-select>
        <el-input v-model="manualMailTo" class="full-row" type="textarea" :rows="2" placeholder="手动输入收件人，可用逗号、分号、空格或换行分隔" />
        <el-input v-model="manualMailCc" class="full-row" type="textarea" :rows="2" placeholder="手动输入抄送，可用逗号、分号、空格或换行分隔" />
      </div>

      <div class="toolbar" style="margin-top: 16px">
        <el-button type="primary" :disabled="!selectedWikiTitle" :loading="publishing" @click="publish">更新到 Redmine</el-button>
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
import { errorLogs, errorMessage, getContacts, getReleaseDetail, listReleases, publishRelease } from '../api/http'
import type { MetaInfo, Project, ReleaseSummary } from '../types'

const props = defineProps<{ projects: Project[]; meta: MetaInfo; mailVersion: number }>()
const projectId = ref(props.projects[0]?.identifier || '')
const filterProductLine = ref('')
const selectedWikiTitle = ref('')
const releases = ref<ReleaseSummary[]>([])
const loadingReleases = ref(false)
const publishing = ref(false)
const status = ref('')
const logs = ref<string[]>([])
const filesInfo = ref('')
const replaceAttachments = ref(false)
const noticeEnabled = ref(false)
const mailScope = ref('internal')
const contactsTo = ref<string[]>([])
const contactsCc = ref<string[]>([])
const mailTo = ref<string[]>([])
const mailCc = ref<string[]>([])
const manualMailTo = ref('')
const manualMailCc = ref('')
const selectedFiles = ref<File[]>([])

const form = reactive({
  version_name: '',
  release_date: props.meta.today || new Date().toISOString().slice(0, 10),
  commit: '',
  product_line: '',
  changelog: ''
})

watch(
  () => props.projects,
  (value) => {
    if (!projectId.value && value.length) projectId.value = value[0].identifier
  },
  { immediate: true }
)

watch(
  () => props.meta,
  (value) => {
    if (!form.release_date && value.today) form.release_date = value.today
  },
  { immediate: true }
)

watch(() => props.mailVersion, loadContacts)

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

async function reloadAll() {
  selectedWikiTitle.value = ''
  await loadReleases()
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
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

async function loadContacts() {
  try {
    const data = await getContacts(mailScope.value)
    contactsTo.value = data.contacts_to
    contactsCc.value = data.contacts_cc
    mailTo.value = []
    mailCc.value = []
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

async function publish() {
  if (!projectId.value || !selectedWikiTitle.value) return ElMessage.warning('请选择要编辑的版本')
  publishing.value = true
  status.value = ''
  logs.value = ['已提交编辑请求，等待后端执行']
  try {
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
    selectedFiles.value.forEach((file) => data.append('files', file))
    const result = await publishRelease(data)
    releases.value = result.releases
    logs.value = result.logs || []
    status.value = `更新成功：${result.title}${result.notice_message ? '\n' + result.notice_message : ''}`
    ElMessage.success('更新成功')
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
  await loadReleases()
})
</script>
