<script setup lang="ts">
/**
 * 签到屏页面：供教室屏幕展示当日签到码。每 60 秒自动刷新。
 * 学生在"我的预约"里输入该签到码完成签到。
 */
import { onBeforeUnmount, onMounted, ref } from "vue";

import { showError } from "@/core/http";

import { seatApi, type CheckinCode, type Room } from "../api";

const rooms = ref<Room[]>([]);
const roomId = ref<number>();
const code = ref<CheckinCode | null>(null);
const loading = ref(false);
const loadedAt = ref("");

const REFRESH_MS = 60_000;
let timer: number | undefined;

async function loadRooms() {
  try {
    const { data } = await seatApi.GET("/api/v1/seat/rooms", {
      params: { query: { is_study_room: true, page: 1, size: 100 } },
    });
    rooms.value = data!.items;
    if (roomId.value === undefined && rooms.value.length > 0) roomId.value = rooms.value[0]!.id;
    if (roomId.value !== undefined) await loadCode();
  } catch (e) {
    showError(e);
  }
}

async function loadCode() {
  if (roomId.value === undefined) return;
  loading.value = true;
  try {
    const { data } = await seatApi.GET("/api/v1/seat/rooms/{room_id}/checkin-code", {
      params: { path: { room_id: roomId.value } },
    });
    code.value = data!;
    loadedAt.value = new Date().toLocaleTimeString("zh-CN", { hour12: false });
  } catch (e) {
    showError(e);
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  void loadRooms();
  timer = window.setInterval(() => void loadCode(), REFRESH_MS);
});
onBeforeUnmount(() => window.clearInterval(timer));
</script>

<template>
  <div>
    <el-form inline @submit.prevent="loadCode">
      <el-form-item label="自习室">
        <el-select v-model="roomId" filterable style="width: 260px" @change="loadCode">
          <el-option v-for="r in rooms" :key="r.id" :label="`${r.building} ${r.name}`" :value="r.id" />
        </el-select>
      </el-form-item>
      <el-button type="primary" native-type="submit" :loading="loading">刷新</el-button>
    </el-form>

    <el-empty v-if="!code && !loading" description="选择自习室后显示签到码" />
    <div v-else class="screen" v-loading="loading">
      <div class="room">{{ rooms.find((r) => r.id === roomId)?.name ?? "" }}</div>
      <div class="label">请在本页对应自习室就座后，于预约开始前扫码或在"我的预约"输入签到码</div>
      <div class="code">{{ code?.code }}</div>
      <div class="meta">
        <div>日期：{{ code?.valid_date }}</div>
        <div class="qr">{{ code?.qr_payload }}</div>
        <div class="updated">更新于 {{ loadedAt }}，每分钟自动刷新</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.screen {
  text-align: center;
  padding: 40px 16px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
}
.room {
  font-size: 32px;
  font-weight: 600;
  margin-bottom: 8px;
}
.label {
  color: var(--el-text-color-secondary);
  margin-bottom: 16px;
}
.code {
  font-size: 88px;
  font-weight: 700;
  letter-spacing: 0.2em;
  font-family: ui-monospace, monospace;
  color: var(--el-color-primary);
}
.meta {
  margin-top: 16px;
  color: var(--el-text-color-secondary);
}
.qr {
  color: var(--el-text-color-placeholder);
  font-size: 13px;
  word-break: break-all;
}
.updated {
  font-size: 12px;
  margin-top: 8px;
}
</style>
