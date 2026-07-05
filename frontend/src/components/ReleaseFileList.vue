<template>
  <div v-if="files.length" class="full-row file-list-panel">
    <div class="muted">已选择 {{ files.length }} 个文件，总大小 {{ totalSizeText }}</div>
    <el-table :data="rows" border size="small" max-height="220">
      <el-table-column prop="name" label="文件名" min-width="260" show-overflow-tooltip />
      <el-table-column prop="sizeText" label="大小" width="120" />
      <el-table-column label="提示" width="160">
        <template #default="scope">
          <el-tag v-if="scope.row.duplicate" type="danger">文件名重复</el-tag>
          <el-tag v-else type="success">正常</el-tag>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { formatBytes, selectedFileRows, totalFileSize } from '../utils/releaseUi.js'

const props = defineProps<{ files: File[] }>()
const rows = computed(() => selectedFileRows(props.files))
const totalSizeText = computed(() => formatBytes(totalFileSize(props.files)))
</script>

<style scoped>
.file-list-panel { margin-top: 8px; }
</style>
