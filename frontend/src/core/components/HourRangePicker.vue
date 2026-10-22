<script setup lang="ts">
/** 整点时段选择：日期 + 开始整点 + 结束整点（不含）。对应后端的 HourRange 模型。 */
import { computed } from "vue";

export interface HourRange {
  date: string;
  start_hour: number;
  end_hour: number;
}

const model = defineModel<HourRange>({ required: true });
const props = defineProps<{ maxHours?: number; openHour?: number; closeHour?: number }>();

const open = computed(() => props.openHour ?? 8);
const close = computed(() => props.closeHour ?? 22);
const startOptions = computed(() => range(open.value, close.value));
const endOptions = computed(() =>
  range(model.value.start_hour + 1, Math.min(close.value, model.value.start_hour + (props.maxHours ?? 4))),
);

function range(from: number, to: number) {
  return Array.from({ length: Math.max(0, to - from + 1) }, (_, i) => from + i);
}
function onStartChange() {
  if (!endOptions.value.includes(model.value.end_hour)) model.value.end_hour = model.value.start_hour + 1;
}
</script>

<template>
  <el-date-picker v-model="model.date" type="date" value-format="YYYY-MM-DD" placeholder="日期" />
  <el-select v-model="model.start_hour" style="width: 100px; margin-left: 8px" @change="onStartChange">
    <el-option v-for="h in startOptions" :key="h" :label="`${h}:00`" :value="h" />
  </el-select>
  <span style="margin: 0 6px">至</span>
  <el-select v-model="model.end_hour" style="width: 100px">
    <el-option v-for="h in endOptions" :key="h" :label="`${h}:00`" :value="h" />
  </el-select>
</template>
