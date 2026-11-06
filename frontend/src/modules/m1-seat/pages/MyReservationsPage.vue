<script setup lang="ts">
/**
 * 我的预约：签到、取消、一键复订；附我的违约记录。
 * 复订以历史预约为模板（同一座位），时段重新选择。
 * 签到、取消按钮只在后端允许的时间内显示：开始前可取消；开始前 15 分钟至开始后 auto_cancel_min 分钟可签到。
 */
import { ElMessage } from "element-plus";
import { onBeforeUnmount, onMounted, ref, watch } from "vue";

import HourRangePicker, { type HourRange } from "@/core/components/HourRangePicker.vue";
import PaginatedTable from "@/core/components/PaginatedTable.vue";
import { confirmAction, promptText } from "@/core/dialogs";
import { bizNow, fmtTime } from "@/core/format";
import { showError } from "@/core/http";
import { usePagedList } from "@/core/pagedList";

import { seatApi, type ReservationDetail, type SeatSettings } from "../api";

const tab = ref<"reservations" | "violations">("reservations");

const statusLabel: Record<string, string> = {
  booked: "已预约",
  checked_in: "已签到",
  completed: "已完成",
  cancelled: "已取消",
  no_show: "未签到（违约）",
};
const cancelReasonLabel: Record<string, string> = {
  USER: "本人取消",
  NO_CHECK_IN: "超时未签到",
  ADMIN_DISABLED: "管理员停用座位或教室",
  BLOCKED_BY_M2: "教室被整间借用",
  BLOCKED_BY_M3: "教室维修",
};
const statusOptions = Object.entries(statusLabel).map(([value, label]) => ({ value, label }));

/** 预约参数（复订时长上限、签到截止）；加载前按后端默认值 */
const settings = ref<SeatSettings>({ max_hours: 4, auto_cancel_min: 15, remind_before_min: 15, remind_late_min: 10 });

/** 当前时刻，每 30 秒刷新，用于按时间窗口显示签到、取消按钮 */
const now = ref(Date.now());
const timer = window.setInterval(() => (now.value = Date.now()), 30_000);
onBeforeUnmount(() => window.clearInterval(timer));

const MINUTE = 60_000;
/**
 * 开始前多少分钟起可签到，与后端 checkin_service.CHECKIN_EARLY_MINUTES 一致。
 * 后端只在签到码接口（seat:checkin_code，学生无权调用）返回 early_minutes，预约参数里没有，因此这里保留常量。
 */
const CHECKIN_EARLY_MINUTES = 15;
const canCancel = (r: ReservationDetail) => r.status === "booked" && now.value < Date.parse(r.start_at);
function canCheckIn(r: ReservationDetail) {
  const start = Date.parse(r.start_at);
  return (
    r.status === "booked" &&
    now.value >= start - CHECKIN_EARLY_MINUTES * MINUTE &&
    now.value < start + settings.value.auto_cancel_min * MINUTE
  );
}

/** ---- 预约记录 ---- */
const statusFilter = ref<ReservationDetail["status"]>();
const { items, total, page, size, loading, load, reload } = usePagedList((p) =>
  seatApi
    .GET("/api/v1/seat/reservations/mine", { params: { query: { status: statusFilter.value || undefined, ...p } } })
    .then((r) => r.data!),
);
watch(statusFilter, reload);

async function cancel(r: ReservationDetail) {
  if (!(await confirmAction(`取消 ${r.room.name} ${r.seat.code} 的预约？`))) return;
  try {
    await seatApi.POST("/api/v1/seat/reservations/{reservation_id}/cancel", {
      params: { path: { reservation_id: r.id } },
    });
    ElMessage.success("已取消");
    await load();
  } catch (e) {
    showError(e);
  }
}

async function checkIn(r: ReservationDetail) {
  const code = await promptText("输入教室屏幕上的签到码", "签到", { minLength: 1 });
  if (code === null) return;
  try {
    await seatApi.POST("/api/v1/seat/reservations/{reservation_id}/check-in", {
      params: { path: { reservation_id: r.id } },
      body: { code },
    });
    ElMessage.success("签到成功");
    await load();
  } catch (e) {
    showError(e);
  }
}

/** ---- 一键复订 ---- */
const rebooking = ref<ReservationDetail | null>(null);
const rebookRange = ref<HourRange>({ date: bizNow().date, start_hour: 14, end_hour: 16 });
const rebookSubmitting = ref(false);

async function rebook() {
  const r = rebooking.value;
  if (!r) return;
  rebookSubmitting.value = true;
  try {
    const { data } = await seatApi.POST("/api/v1/seat/reservations/{reservation_id}/rebook", {
      params: { path: { reservation_id: r.id } },
      body: { ...rebookRange.value },
    });
    ElMessage.success(`已复订 ${r.room.name} ${r.seat.code}，预约号 ${data!.id}`);
    rebooking.value = null;
    await load();
  } catch (e) {
    showError(e);
  } finally {
    rebookSubmitting.value = false;
  }
}

/** ---- 违约记录 ---- */
const {
  items: violations,
  total: violationsTotal,
  page: violationsPage,
  size: violationsSize,
  loading: violationsLoading,
  load: loadViolations,
} = usePagedList((p) => seatApi.GET("/api/v1/seat/violations/mine", { params: { query: p } }).then((r) => r.data!));
watch(tab, (t) => {
  if (t === "violations" && violations.value.length === 0) void loadViolations();
});

onMounted(async () => {
  void load();
  try {
    const { data } = await seatApi.GET("/api/v1/seat/settings");
    settings.value = data!;
  } catch (e) {
    showError(e);
  }
});
</script>

<template>
  <el-tabs v-model="tab">
    <el-tab-pane label="预约记录" name="reservations">
      <el-select v-model="statusFilter" clearable placeholder="全部状态" style="width: 160px; margin-bottom: 12px">
        <el-option v-for="o in statusOptions" :key="o.value" :label="o.label" :value="o.value" />
      </el-select>
      <PaginatedTable :data="items" :loading="loading" :total="total" v-model:page="page" v-model:size="size">
        <el-table-column label="自习室" prop="room.name" />
        <el-table-column label="座位" prop="seat.code" />
        <el-table-column label="开始">
          <template #default="{ row }">{{ fmtTime(row.start_at) }}</template>
        </el-table-column>
        <el-table-column label="结束">
          <template #default="{ row }">{{ fmtTime(row.end_at) }}</template>
        </el-table-column>
        <el-table-column label="状态">
          <template #default="{ row }">{{ statusLabel[row.status] ?? row.status }}</template>
        </el-table-column>
        <el-table-column label="取消原因" show-overflow-tooltip>
          <template #default="{ row }">{{
            row.cancel_reason ? (cancelReasonLabel[row.cancel_reason] ?? row.cancel_reason) : ""
          }}</template>
        </el-table-column>
        <el-table-column width="220">
          <template #default="{ row }">
            <el-button v-if="canCheckIn(row)" size="small" type="primary" @click="checkIn(row)">签到</el-button>
            <el-button v-if="canCancel(row)" size="small" @click="cancel(row)">取消</el-button>
            <el-button v-if="row.status !== 'booked'" size="small" @click="rebooking = row">一键复订</el-button>
          </template>
        </el-table-column>
      </PaginatedTable>
    </el-tab-pane>

    <el-tab-pane label="违约记录" name="violations">
      <PaginatedTable
        :data="violations"
        :loading="violationsLoading"
        :total="violationsTotal"
        v-model:page="violationsPage"
        v-model:size="violationsSize"
      >
        <el-table-column label="编号" prop="id" width="80" />
        <el-table-column label="关联预约号" prop="reservation_id" />
        <el-table-column label="记录时间">
          <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
        </el-table-column>
      </PaginatedTable>
    </el-tab-pane>
  </el-tabs>

  <el-dialog
    :model-value="rebooking !== null"
    :title="`复订 ${rebooking?.room.name} ${rebooking?.seat.code}`"
    width="420px"
    @close="rebooking = null"
  >
    <el-form label-width="60px">
      <el-form-item label="时段">
        <HourRangePicker
          v-model="rebookRange"
          :max-hours="settings.max_hours"
          :open-hours="rebooking?.room.open_hours"
          :min-date="bizNow().date"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="rebooking = null">取消</el-button>
      <el-button type="primary" :loading="rebookSubmitting" @click="rebook">复订</el-button>
    </template>
  </el-dialog>
</template>
