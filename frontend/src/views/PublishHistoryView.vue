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
        <el-table-column prop="release_status" label="发布" width="90" />
        <el-table-column prop="file_status" label="附件" width="90" />
        <el-table-column prop="wiki_status" label="Wiki" width="90" />
        <el-table-column prop="index_status" label="索引" width="90" />
        <el-table-column prop="mail_status" label="邮件" width="90" />
        <el-table-column label="恢复" width="220" fixed="right">
          <template #default="scope">
            <el-button size="small" :loading="recoveringId === scope.row.id" @click="recover(scope.row.id, 'rebuild_index')">重建索引</el-button>
            <el-button size="small" type="warning" :loading="recoveringId === scope.row.id" @click="recover(scope.row.id, 'continue')">继续</el-button>
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

async function recover(id: number, action: 'rebuild_index' | 'continue') {
  recoveringId.value = id
  logs.value = []
  try {
    const result = await recoverPublishHistory(id, action)
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
  }
}

onMounted(loadHistory)
</script>
