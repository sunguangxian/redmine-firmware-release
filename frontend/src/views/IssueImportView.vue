<template>
  <div>
    <el-card class="card">
      <template #header>导入测试问题表</template>
      <p class="issue-import-hint">上传含「序号」和「故障概述」的 .xls / .xlsx。先解析预览，确认版本和指派人后再写入 Redmine。只有管理员可以使用。</p>
      <div class="toolbar">
        <el-select v-model="projectId" filterable placeholder="选择项目" style="width: 280px">
          <el-option v-for="project in projects" :key="project.identifier" :label="`${project.name} (${project.identifier})`" :value="project.identifier" />
        </el-select>
        <el-select v-model="versionId" filterable placeholder="目标版本" style="width: 220px">
          <el-option v-for="version in versions" :key="version.id" :label="versionLabel(version)" :value="version.id" />
        </el-select>
        <el-select v-model="assigneeId" filterable placeholder="指派给" style="width: 260px">
          <el-option v-for="assignee in assignees" :key="assignee.id" :label="assignee.name" :value="assignee.id" />
        </el-select>
        <el-input-number v-model="year" :min="2000" :max="2100" controls-position="right" />
        <span class="issue-import-year">月日日期使用该年份</span>
      </div>
      <el-upload class="full-row" drag :auto-upload="false" :show-file-list="false" accept=".xls,.xlsx" :disabled="busy" :on-change="onFile">
        <div class="el-upload__text">{{ filename || '拖入问题表，或点击选择 .xls / .xlsx' }}</div>
      </el-upload>
      <div class="toolbar issue-import-actions">
        <el-button type="primary" :loading="previewing" :disabled="!file || !projectId" @click="preview()">解析预览</el-button>
        <el-button type="success" :disabled="!canConfirm" @click="confirmVisible = true">确认导入</el-button>
      </div>
      <el-alert v-if="previewData" class="issue-import-summary" type="info" :closable="false" show-icon>
        <template #title>{{ summaryTitle }}</template>
        <div>{{ summaryDetail }}</div>
        <div>标题含「建议」的记为功能，其余记为错误。4-Very High / 3-High / 2-Medium 分别对应紧急 / 高 / 普通。相同标题的已有问题不会重复创建。</div>
      </el-alert>
      <el-alert v-for="warning in warnings" :key="warning" class="issue-import-summary" type="warning" :closable="false" show-icon :title="warning" />
    </el-card>

    <el-card v-if="previewData" class="card">
      <el-table ref="tableRef" :data="previewData.issues" border row-key="row_key" max-height="560" @selection-change="onSelection">
        <el-table-column type="selection" width="48" :selectable="canSelect" />
        <el-table-column label="序号" width="90">
          <template #default="scope">{{ scope.row.seq || '-' }}{{ scope.row.seq_note ? ' 重复' : '' }}</template>
        </el-table-column>
        <el-table-column prop="found_on" label="日期" width="120" />
        <el-table-column prop="priority_name" label="优先级" width="90" />
        <el-table-column prop="tracker_name" label="跟踪" width="80" />
        <el-table-column prop="subject" label="标题" min-width="280" show-overflow-tooltip />
        <el-table-column label="状态" width="180">
          <template #default="scope">
            <span v-if="scope.row.duplicate">已存在 #{{ scope.row.existing_id }}</span>
            <span v-else>将新建</span>
          </template>
        </el-table-column>
        <el-table-column type="expand" width="54">
          <template #default="scope">
            <pre class="issue-description">{{ scope.row.description }}</pre>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card v-if="result" class="card">
      <template #header>导入结果</template>
      <el-alert v-if="result.failed" type="error" :closable="false" show-icon :title="`停在「${result.failed.subject}」：${result.failed.error}`" />
      <p v-if="result.skipped.length">跳过 {{ result.skipped.length }} 条已存在的问题。</p>
      <el-table v-if="result.created.length" :data="result.created" border size="small">
        <el-table-column prop="id" label="问题" width="100">
          <template #default="scope"><a :href="scope.row.url" target="_blank" rel="noreferrer">#{{ scope.row.id }}</a></template>
        </el-table-column>
        <el-table-column prop="subject" label="标题" min-width="320" show-overflow-tooltip />
      </el-table>
    </el-card>

    <el-dialog v-model="confirmVisible" title="确认导入问题" width="640px">
      <p>将向项目 {{ projectId }} 创建 {{ selectedKeys.length }} 条问题。</p>
      <p>版本：{{ selectedVersionName }}</p>
      <p>指派给：{{ selectedAssigneeName }}</p>
      <p v-if="previewData?.counts.duplicate">另有 {{ previewData.counts.duplicate }} 条相同标题已存在，不会重复创建。</p>
      <template #footer>
        <el-button @click="confirmVisible = false">取消</el-button>
        <el-button type="primary" :loading="committing" @click="commit">确认执行</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { ElMessage, type TableInstance, type UploadFile } from 'element-plus'
import { commitIssueImport, errorMessage, getIssueImportOptions, previewIssueImport, type IssueImportAssignee, type IssueImportPreview, type IssueImportResult, type IssueImportRow, type IssueImportVersion } from '../api/http'
import type { Project } from '../types'

const props = defineProps<{ projects: Project[] }>()
const projectId = ref(props.projects[0]?.identifier || '')
const versions = ref<IssueImportVersion[]>([])
const assignees = ref<IssueImportAssignee[]>([])
const versionId = ref<number | undefined>(undefined)
const assigneeId = ref<number | undefined>(undefined)
const year = ref(new Date().getFullYear())
const file = ref<File | null>(null)
const filename = ref('')
const previewing = ref(false)
const committing = ref(false)
const confirmVisible = ref(false)
const previewData = ref<IssueImportPreview | null>(null)
const warnings = ref<string[]>([])
const result = ref<IssueImportResult | null>(null)
const selectedKeys = ref<string[]>([])
const tableRef = ref<TableInstance>()

const busy = computed(() => previewing.value || committing.value)
const canConfirm = computed(() => Boolean(previewData.value && file.value && projectId.value && versionId.value && assigneeId.value && selectedKeys.value.length && !busy.value))
const selectedVersionName = computed(() => versions.value.find((item) => item.id === versionId.value)?.name || '')
const selectedAssigneeName = computed(() => assignees.value.find((item) => item.id === assigneeId.value)?.name || '')
const summaryTitle = computed(() => {
  if (!previewData.value) return ''
  const counts = previewData.value.counts
  return `${previewData.value.filename}：共 ${counts.total} 条，可新建 ${counts.new} 条，已存在 ${counts.duplicate} 条`
})
const summaryDetail = computed(() => {
  const context = previewData.value?.context
  if (!context) return ''
  const extras = context.extra_versions.map((item) => `${item.name} ${item.value}`).join('，')
  return [
    context.title,
    context.software_version ? `软件 ${context.software_version}` : '',
    context.mcu ? `MCU ${context.mcu}` : '',
    extras,
    context.sample ? `样品 ${context.sample}` : '',
    context.suggested_version ? `表内版本 ${context.suggested_version}` : '',
  ].filter(Boolean).join('；')
})

watch(() => props.projects, (value) => {
  if (!projectId.value && value.length) projectId.value = value[0].identifier
}, { immediate: true })

watch(projectId, () => {
  previewData.value = null
  selectedKeys.value = []
  void loadOptions()
}, { immediate: true })

function versionLabel(version: IssueImportVersion): string {
  return version.status && version.status !== 'open' ? `${version.name}（${version.status}）` : version.name
}

function onFile(upload: UploadFile) {
  file.value = upload.raw || null
  filename.value = upload.name
  previewData.value = null
  result.value = null
  selectedKeys.value = []
}

function canSelect(row: IssueImportRow): boolean {
  return !row.duplicate && Boolean(row.priority_name)
}

function onSelection(rows: IssueImportRow[]) {
  const chosen = new Set(rows.map((row) => row.row_key))
  selectedKeys.value = (previewData.value?.issues || []).filter((row) => chosen.has(row.row_key)).map((row) => row.row_key)
}

async function loadOptions() {
  versions.value = []
  assignees.value = []
  if (!projectId.value) return
  try {
    const data = await getIssueImportOptions(projectId.value)
    versions.value = data.versions
    assignees.value = data.assignees
    warnings.value = data.warnings || []
    if (versionId.value && !versions.value.some((item) => item.id === versionId.value)) versionId.value = undefined
    if (assigneeId.value && !assignees.value.some((item) => item.id === assigneeId.value)) assigneeId.value = undefined
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

function formData(): FormData {
  const form = new FormData()
  form.append('project_id', projectId.value)
  form.append('year', String(year.value))
  form.append('file', file.value as File, filename.value)
  return form
}

async function preview(keepResult = false) {
  if (!file.value || !projectId.value) return
  previewing.value = true
  if (!keepResult) result.value = null
  try {
    const data = await previewIssueImport(formData())
    previewData.value = data
    warnings.value = data.warnings || []
    if (!versionId.value && data.suggested_version) versionId.value = data.suggested_version.id
    await nextTick()
    tableRef.value?.clearSelection()
    for (const row of data.issues) {
      if (canSelect(row)) tableRef.value?.toggleRowSelection(row, true)
    }
  } catch (error) {
    previewData.value = null
    ElMessage.error(errorMessage(error))
  } finally {
    previewing.value = false
  }
}

async function commit() {
  if (!canConfirm.value || !file.value) return
  committing.value = true
  try {
    const form = formData()
    form.append('assigned_to_id', String(assigneeId.value))
    form.append('version_id', String(versionId.value))
    form.append('row_keys_json', JSON.stringify(selectedKeys.value))
    const data = await commitIssueImport(form)
    result.value = data
    confirmVisible.value = false
    if (data.ok) ElMessage.success(`已创建 ${data.created.length} 条问题`)
    else ElMessage.error(data.failed?.error || '导入未完成')
    await preview(true)
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    committing.value = false
  }
}
</script>

<style scoped>
.issue-import-hint { margin: 0 0 12px; color: #526277; }
.issue-import-actions { margin-top: 12px; }
.issue-import-year { color: #6b7787; font-size: 13px; }
.issue-import-summary { margin-top: 12px; }
.issue-description { white-space: pre-wrap; margin: 0; font-family: inherit; line-height: 1.5; }
</style>
