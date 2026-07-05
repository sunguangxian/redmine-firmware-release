<template>
  <el-dialog v-model="visible" title="执行日志" width="820px" destroy-on-close>
    <div class="release-log">
      <div v-for="(item, index) in logs" :key="index">{{ index + 1 }}. {{ item }}</div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ modelValue: boolean; logs: string[] }>()
const emit = defineEmits<{ (event: 'update:modelValue', value: boolean): void }>()

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})
</script>
