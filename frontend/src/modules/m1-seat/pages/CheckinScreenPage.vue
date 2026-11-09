<script setup lang="ts">
/**
 * 签到屏页面：供教室屏幕展示当日签到码与二维码。每 60 秒自动刷新。
 * 学生扫码或在"我的预约"里输入该签到码完成签到。
 */
import QRCode from "qrcode";
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

import { fmtTime } from "@/core/format";
import { showError } from "@/core/http";
import { roomLabel, useRooms } from "@/core/rooms";

import { seatApi, type CheckinCode } from "../api";

const { rooms, load: loadRooms, nameOf } = useRooms({ is_study_room: true });
const roomId = ref<number>();
const code = ref<CheckinCode | null>(null);
const qrImage = ref("");
const windowHint = computed(() =>
  code.value
    ? `请在预约开始前 ${code.value.early_minutes} 分钟至开始后 ${code.value.auto_cancel_min} 分钟内扫码或在"我的预约"输入签到码，超时未签到将自动取消并记违约`
    : "",
);
const loading = ref(false);
const loadedAt = ref("");

const REFRESH_MS = 60_000;
let timer: number | undefined;

async function loadCode() {
  if (roomId.value === undefined) return;
  loading.value = true;
  try {
    const { data } = await seatApi.GET("/api/v1/seat/rooms/{room_id}/checkin-code", {
      params: { path: { room_id: roomId.value } },
    });
    code.value = data!;
    qrImage.value = await QRCode.toDataURL(data!.qr_payload, { width: 240, margin: 1 });
    loadedAt.value = fmtTime(new Date());
  } catch (e) {
    showError(e);
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  await loadRooms();
  roomId.value = rooms.value[0]?.id;
  await loadCode();
  timer = window.setInterval(() => void loadCode(), REFRESH_MS);
});
onBeforeUnmount(() => window.clearInterval(timer));
</script>

<template>
  <div>
    <el-form inline @submit.prevent="loadCode">
      <el-form-item label="自习室">
        <el-select v-model="roomId" filterable style="width: 260px" @change="loadCode">
          <el-option v-for="r in rooms" :key="r.id" :label="roomLabel(r)" :value="r.id" />
        </el-select>
      </el-form-item>
      <el-button type="primary" native-type="submit" :loading="loading">刷新</el-button>
    </el-form>

    <el-empty v-if="!code && !loading" description="选择自习室后显示签到码" />
    <div v-else class="screen" v-loading="loading">
      <div class="room">{{ roomId !== undefined ? nameOf(roomId) : "" }}</div>
      <div v-if="code" class="label">{{ windowHint }}</div>
      <img v-if="qrImage" :src="qrImage" alt="签到二维码" class="qr" />
      <div class="code">{{ code?.code }}</div>
      <div class="meta">
        <div>日期：{{ code?.valid_date }}</div>
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
  width: 240px;
  height: 240px;
}
.updated {
  font-size: 12px;
  margin-top: 8px;
}
</style>
