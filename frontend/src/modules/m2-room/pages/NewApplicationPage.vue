<script setup lang="ts">
/**
 * 提交整教室申请：选教室（M1 中允许整室借用的）、时段、用途与人数。
 * 可选日期按申请参数 advance_days_min ~ advance_days_max 限制，时段按教室当天的开放时间，当天不开放时不能提交；
 * 提交前展示资格门槛结果，不满足时禁止提交。
 */
import { ElMessage } from "element-plus";
import { computed, onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";

import HourRangePicker, { type HourRange } from "@/core/components/HourRangePicker.vue";
import { addDays, bizHourIso, bizNow } from "@/core/format";
import { showError } from "@/core/http";
import { bookableHours, roomLabel, useRooms } from "@/core/rooms";

import { roomApi, type Eligibility, type RoomSettings } from "../api";

/** 用途长度，与后端 ApplicationCreate.purpose 一致 */
const PURPOSE_MIN = 2;
const PURPOSE_MAX = 500;

const router = useRouter();
const { rooms, byId, load: loadRooms } = useRooms({ is_whole_bookable: true });
const eligible = ref<Eligibility | null>(null);
const submitting = ref(false);

/** 申请参数加载前按后端默认值 */
const settings = ref<Pick<RoomSettings, "advance_days_min" | "advance_days_max">>({
  advance_days_min: 1,
  advance_days_max: 30,
});
const today = bizNow().date;
const minDate = computed(() => addDays(today, settings.value.advance_days_min));
const maxDate = computed(() => addDays(today, settings.value.advance_days_max));

const form = reactive({
  room_id: undefined as number | undefined,
  range: { date: minDate.value, start_hour: 18, end_hour: 20 } as HourRange,
  purpose: "",
  attendees: 10,
});
const openHours = computed(() => (form.room_id === undefined ? undefined : byId.value.get(form.room_id)?.open_hours));

async function loadSettings() {
  try {
    const { data } = await roomApi.GET("/api/v1/room/settings");
    settings.value = data!;
    form.range.date = minDate.value;
  } catch (e) {
    showError(e);
  }
}

async function loadEligibility() {
  try {
    const { data } = await roomApi.GET("/api/v1/room/eligibility");
    eligible.value = data!;
  } catch (e) {
    showError(e);
  }
}

function formError(): string | null {
  if (!form.room_id) return "请选择教室";
  const { date } = form.range;
  if (date < minDate.value || date > maxDate.value) return `日期需在 ${minDate.value} 至 ${maxDate.value} 之间`;
  if (!bookableHours(openHours.value, date)) return "该教室在所选日期没有可选时段，请换一天";
  if (form.range.end_hour <= form.range.start_hour) return "请选择有效的时段";
  if (form.purpose.trim().length < PURPOSE_MIN) return `请填写用途（至少 ${PURPOSE_MIN} 个字）`;
  return null;
}

async function submit() {
  const error = formError();
  if (error) {
    ElMessage.warning(error);
    return;
  }
  const { date, start_hour, end_hour } = form.range;
  submitting.value = true;
  try {
    const { data } = await roomApi.POST("/api/v1/room/applications", {
      body: {
        room_id: form.room_id!,
        start_at: bizHourIso(date, start_hour),
        end_at: bizHourIso(date, end_hour),
        purpose: form.purpose.trim(),
        attendees: form.attendees,
      },
    });
    ElMessage.success(`已提交申请，申请号 ${data!.id}，等待审批`);
    await router.push("/room/mine");
  } catch (e) {
    showError(e);
  } finally {
    submitting.value = false;
  }
}

// 三个请求互不依赖，分开处理，任一失败不影响其他内容显示
onMounted(() => {
  void loadRooms();
  void loadEligibility();
  void loadSettings();
});
</script>

<template>
  <el-alert
    v-if="eligible && !eligible.eligible"
    type="warning"
    :title="`当前不能申请：${eligible.reasons.join('；')}`"
    :closable="false"
    style="margin-bottom: 16px"
  />

  <el-card style="max-width: 640px">
    <el-form label-width="90px">
      <el-form-item label="教室" required>
        <el-select v-model="form.room_id" filterable placeholder="选择允许整室借用的教室" style="width: 100%">
          <el-option v-for="r in rooms" :key="r.id" :label="`${roomLabel(r)}（${r.capacity} 人）`" :value="r.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="时段" required>
        <HourRangePicker
          v-model="form.range"
          :max-hours="24"
          :open-hours="openHours"
          :min-date="minDate"
          :max-date="maxDate"
        />
      </el-form-item>
      <el-form-item label="用途" required>
        <el-input
          v-model="form.purpose"
          type="textarea"
          :rows="2"
          :maxlength="PURPOSE_MAX"
          show-word-limit
          placeholder="如：班级读书会"
        />
      </el-form-item>
      <el-form-item label="参加人数" required>
        <el-input-number v-model="form.attendees" :min="1" value-on-clear="min" />
      </el-form-item>
      <el-form-item>
        <el-button
          type="primary"
          :loading="submitting"
          :disabled="eligible !== null && !eligible.eligible"
          @click="submit"
        >
          提交申请
        </el-button>
      </el-form-item>
    </el-form>
  </el-card>
</template>
