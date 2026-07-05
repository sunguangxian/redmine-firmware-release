<template>
  <div>
    <el-card class="card">
      <div class="toolbar">
        <el-select v-model="projectId" placeholder="选择项目" filterable style="width: 320px" @change="loadHistory">
          <el-option v-for="project in projects" :key="project.identifier" :label="`${project.name} (${project.identifier})`" :value="project.identifier" />
        </el-select>
        <el-input v-model="wikiTitle" clearable placeholder="Wiki 页面，可选" style="width: 280px" />
        <el-button :loading="loading" @click="loadHistory">刷新</el-button>
      </div>
      <el-table :data="items" border height="520">
        <el-table-column prop="created_at" label="时间" width="160" />
        <el-table-column prop="project_id" label="项目" width="160" />
        <el-table-column prop="version_name" label="版本" width="140" />
        <el-table-column prop="wiki_title" label="Wiki" min-width="220" />
        <el-table-column prop="action" label="操作" width="110" />
        <el-table-column label="发布" width="90"><template #default="scope">{{ statusLabel(scope.row, 'release_status') }}</template></el-table-column>
        <el-table-column label="附件" width="90"><template #default="scope">{{ statusLabel(scope.row, 'file_status') }}</template></el-table-column>
        <el-table-column label="Wiki" width="90"><template #default="scope">{{ statusLabel(scope.row, 'wiki_status') }}</template></el-table-column>
        <el-table-column label="索引" width="90"><template #default="scope">{{ statusLabel(scope.row, 'index_status') }}</template></el-table-column>
        <el-table-column label="邮件" width="90"><template #default="scope">{{ statusLabel(scope.row, 'mail_status') }}</template></el-table-column>
        <el-table-column prop="status_summary" label="状态摘要" min-width="260" show-overflow-tooltip />
        <el-table-column prop="error_message" label="错误" min-width="220" show-overflow-tooltip />
        <el-table-column label="恢复" width="220" fixed="right">
          <template #default="scope">
            <template v-if="(scope.row.recover_actions || []).length">
              <el-button
                v-for="action in scope.row.recover_actions"
                :key="action.action"
                size="small"
                :type="action.action === 'continue' ? 'warning' : 'primary'"
                :loading="recoveringId === scope.row.id && recoveringAction === action.action"
                @click="recover(scope.row, action.action)"
              >{{ action.label }}</el-button>
            </template>
            <span v-else>-</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="logDialogVisible" title="恢复日志" width="820px" destroy-on-close>
      <div class="release-log"><div v-for="(item, index) in logs" :key="index">{{ index + 1 }}. {{ item }}</div></div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { errorLogs, errorMessage, getPublishHistory, recoverPublishHistory, type PublishHistoryItem } from '../api/http'
import type { Project } from '../types'

const props = defineProps<{ projects: Project[] }>()
const projectId = ref(props.projects[0]?.identifier || '')
const wikiTitle = ref('')
const items = ref<PublishHistoryItem[]>([])
const loading = ref(false)
const recoveringId = ref<number | null>(null)
const recoveringAction = ref('')
const logs = ref<string[]>([])
const logDialogVisible = ref(false)

watch(() => props.projects, (value) => { if (!projectId.value && value.length) projectId.value = value[0].identifier }, { immediate: true })

async function loadHistory() {
  loading.value = true
  try {
    const data = await getPublishHistory({ project_id: projectId.value, wiki_title: wikiTitle.value, limit: 100 })
    items.value = data.items
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    loading.value = false
  }
}

function statusLabel(row: PublishHistoryItem, field: 'release_status' | 'file_status' | 'wiki_status' | 'index_status' | 'mail_status'): string {
  const record = row as unknown as Record<string, unknown>
  return String(record[`${field}_label`] || record[field] || '')
}

async function recover(row: PublishHistoryItem, action: 'rebuild_index' | 'continue') {
  recoveringId.value = row.id
  recoveringAction.value = action
  logs.value = []
  try {
    const result = await recoverPublishHistory(row.id, action)
    logs.value = result.logs || []
    logDialogVisible.value = true
    ElMessage.success(result.message)
    await loadHistory()
  } catch (error) {
    const message = errorMessage(error)
    const backendLogs = errorLogs(error)
    logs.value = backendLogs.length ? [...backendLogs, `恢复失败：${message}`] : [`恢复失败：${message}`]
    logDialogVisible.value = true
    ElMessage.error(message)
  } finally {
    recoveringId.value = null
    recoveringAction.value = ''
  }
}

onMounted(loadHistory)
</script>
