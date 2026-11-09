<script setup lang="ts">
/**
 * 整点时段选择：日期 + 开始整点 + 结束整点（不含）。对应后端的 HourRange 模型。
 * 可选整点见 core/rooms.ts 的 bookableHours：按所选日期取教室开放时间（未传入时默认 8–22 点），
 * 当天已开始的整点不可选；没有可选整点时提示，由页面在提交前用 bookableHours 拦截。
 * 开始整点最晚为关闭前一小时，结束整点最晚为关闭整点（可以是 24）。
 */
import { computed, watch } from "vue";

import { pickerDate } from "@/core/format";
import { bookableHours, type OpenHour } from "@/core/rooms";

export interface HourRange {
  date: string;
  start_hour: number;
  end_hour: number;
}

const model = defineModel<HourRange>({ required: true });
const props = defineProps<{
  maxHours?: number;
  openHours?: OpenHour[];
  /** 可选日期范围（YYYY-MM-DD，含两端） */
  minDate?: string;
  maxDate?: string;
}>();

const hours = computed(() => bookableHours(props.openHours, model.value.date));
const startOptions = computed(() => (hours.value ? range(hours.value.open, hours.value.close - 1) : []));
const endOptions = computed(() =>
  hours.value
    ? range(model.value.start_hour + 1, Math.min(hours.value.close, model.value.start_hour + (props.maxHours ?? 4)))
    : [],
);

function range(from: number, to: number) {
  return Array.from({ length: Math.max(0, to - from + 1) }, (_, i) => from + i);
}

function disabledDate(cell: Date) {
  const day = pickerDate(cell);
  return (props.minDate !== undefined && day < props.minDate) || (props.maxDate !== undefined && day > props.maxDate);
}

/** 可选整点是连续的，不在范围内的值取最近的一端 */
function nearest(value: number, options: number[]) {
  return Math.min(Math.max(value, options[0]!), options[options.length - 1]!);
}

// 日期或开放时间变化后，开始、结束整点不在可选范围内时调整到最近的可选值
watch(
  [startOptions, endOptions],
  () => {
    const m = model.value;
    if (startOptions.value.length > 0) m.start_hour = nearest(m.start_hour, startOptions.value);
    if (endOptions.value.length > 0) m.end_hour = nearest(m.end_hour, endOptions.value);
  },
  { immediate: true },
);
</script>

<template>
  <el-date-picker
    v-model="model.date"
    type="date"
    value-format="YYYY-MM-DD"
    placeholder="日期"
    :clearable="false"
    :disabled-date="disabledDate"
  />
  <el-select v-model="model.start_hour" style="width: 110px; margin-left: 8px">
    <el-option v-for="h in startOptions" :key="h" :label="`${h}:00`" :value="h" />
  </el-select>
  <span style="margin: 0 6px">至</span>
  <el-select v-model="model.end_hour" style="width: 110px">
    <el-option v-for="h in endOptions" :key="h" :label="`${h}:00`" :value="h" />
  </el-select>
  <el-text v-if="!hours" type="warning" style="margin-left: 8px">当天没有可选时段</el-text>
</template>
