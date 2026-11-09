<script setup lang="ts">
/**
 * 自习室可用性格子图：选自习室和日期，座位 × 整点的状态格子。
 * 绿色空闲、蓝色已约、橙色封闭（整室占用/维修）、灰色非开放。
 */
import { computed, onMounted, ref, watch } from "vue";

import { bizNow } from "@/core/format";
import { showError } from "@/core/http";
import { DEFAULT_OPEN_HOURS, openHoursOn, roomLabel, useRooms } from "@/core/rooms";

import { seatApi, type RoomDetail, type SeatAvailability } from "../api";

const { rooms, load: loadRooms } = useRooms({ is_study_room: true });
const roomId = ref<number>();
const date = ref(bizNow().date);
const detail = ref<RoomDetail | null>(null);
const availability = ref<SeatAvailability[]>([]);
const loading = ref(false);

const stateLabel: Record<string, string> = { free: "空闲", reserved: "已约", blocked: "封闭", closed: "未开放" };

/** 展示的整点列：该教室当天开放时间内的整点；当天没有开放时间时按默认范围显示（全部为未开放） */
const hours = computed(() => {
  const { open, close } = openHoursOn(detail.value?.open_hours ?? [], date.value) ?? DEFAULT_OPEN_HOURS;
  return Array.from({ length: close - open }, (_, i) => open + i);
});

const availabilityBySeat = computed(() => {
  const map = new Map<number, Map<number, string>>();
  for (const a of availability.value) {
    map.set(a.seat_id, new Map(a.hours.map((h) => [h.hour, h.state])));
  }
  return map;
});

function seatState(seatId: number, hour: number): string {
  return availabilityBySeat.value.get(seatId)?.get(hour) ?? "closed";
}

async function load() {
  if (roomId.value === undefined) return;
  loading.value = true;
  try {
    const [roomRes, availRes] = await Promise.all([
      seatApi.GET("/api/v1/seat/rooms/{room_id}", { params: { path: { room_id: roomId.value } } }),
      seatApi.GET("/api/v1/seat/rooms/{room_id}/availability", {
        params: { path: { room_id: roomId.value }, query: { date: date.value } },
      }),
    ]);
    detail.value = roomRes.data!;
    availability.value = availRes.data!;
  } catch (e) {
    showError(e);
  } finally {
    loading.value = false;
  }
}

// 选中第一个自习室后由 watch 触发首次加载
watch([roomId, date], () => void load());
onMounted(async () => {
  await loadRooms();
  roomId.value = rooms.value[0]?.id;
});
</script>

<template>
  <div>
    <el-form inline @submit.prevent="load">
      <el-form-item label="自习室">
        <el-select v-model="roomId" filterable style="width: 260px">
          <el-option v-for="r in rooms" :key="r.id" :label="roomLabel(r)" :value="r.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="日期">
        <el-date-picker v-model="date" type="date" value-format="YYYY-MM-DD" :clearable="false" />
      </el-form-item>
      <el-button type="primary" native-type="submit" :loading="loading">查询</el-button>
    </el-form>

    <div class="legend">
      <span v-for="(label, state) in stateLabel" :key="state" class="legend-item">
        <span class="cell" :class="`s-${state}`" />{{ label }}
      </span>
    </div>

    <el-table :data="detail?.seats ?? []" v-loading="loading" size="small">
      <el-table-column label="座位" prop="code" width="80" fixed />
      <el-table-column v-for="h in hours" :key="h" :label="`${h}点`" width="52" align="center">
        <template #default="{ row }">
          <span class="cell" :class="`s-${seatState(row.id, h)}`" :title="stateLabel[seatState(row.id, h)]" />
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.legend {
  margin-bottom: 12px;
  color: var(--el-text-color-secondary);
}
.legend-item {
  margin-right: 16px;
}
.cell {
  display: inline-block;
  width: 18px;
  height: 18px;
  border-radius: 3px;
  vertical-align: middle;
  background: var(--el-fill-color);
}
.s-free {
  background: var(--el-color-success-light-5);
}
.s-reserved {
  background: var(--el-color-primary-light-5);
}
.s-blocked {
  background: var(--el-color-warning-light-5);
}
.s-closed {
  background: var(--el-fill-color-dark);
}
</style>
