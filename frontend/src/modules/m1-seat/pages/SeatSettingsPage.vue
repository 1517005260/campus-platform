<script setup lang="ts">
/** 预约系统参数：单次最长时长、自动取消与提醒时机。 */
import { ElMessage } from "element-plus";
import { onMounted, reactive, ref } from "vue";

import { showError } from "@/core/http";

import { seatApi, type SeatSettings } from "../api";

const loading = ref(false);
const saving = ref(false);

const form = reactive<SeatSettings>({
  max_hours: 4,
  auto_cancel_min: 15,
  remind_before_min: 15,
  remind_late_min: 10,
});

const fields: { key: keyof SeatSettings; label: string; min: number; max: number; hint: string }[] = [
  { key: "max_hours", label: "单次最长时长（小时）", min: 1, max: 24, hint: "限制一次预约的最大小时数" },
  { key: "auto_cancel_min", label: "自动取消（分钟）", min: 1, max: 60, hint: "开始后未签到多少分钟自动取消并记违约" },
  { key: "remind_before_min", label: "开始前提醒（分钟）", min: 0, max: 120, hint: "开始前多少分钟发提醒通知" },
  { key: "remind_late_min", label: "开始后提醒（分钟）", min: 0, max: 60, hint: "开始后未签到多少分钟再次提醒" },
];

async function load() {
  loading.value = true;
  try {
    const { data } = await seatApi.GET("/api/v1/seat/settings");
    Object.assign(form, data!);
  } catch (e) {
    showError(e);
  } finally {
    loading.value = false;
  }
}

async function save() {
  saving.value = true;
  try {
    const { data } = await seatApi.PUT("/api/v1/seat/settings", { body: { ...form } });
    Object.assign(form, data!);
    ElMessage.success("已保存");
  } catch (e) {
    showError(e);
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>

<template>
  <el-card style="max-width: 640px" v-loading="loading">
    <el-form label-width="180px">
      <el-form-item v-for="f in fields" :key="f.key" :label="f.label">
        <el-input-number v-model="form[f.key]" :min="f.min" :max="f.max" />
        <div class="hint">{{ f.hint }}</div>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </el-form-item>
    </el-form>
  </el-card>
</template>

<style scoped>
.hint {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  margin-left: 12px;
}
</style>
