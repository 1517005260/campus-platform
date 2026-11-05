<script setup lang="ts">
/**
 * 提交整教室申请：选教室（M1 中允许整室借用的）、时段、用途与人数。
 * 提交前展示资格门槛结果，不满足时禁止提交。
 */
import { ElMessage } from "element-plus";
import { computed, onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";

import { showError } from "@/core/http";

import { roomApi, seatRoomsApi, type Eligibility } from "../api";

interface RoomOption {
  id: number;
  label: string;
}

const router = useRouter();
const rooms = ref<RoomOption[]>([]);
const eligible = ref<Eligibility | null>(null);
const submitting = ref(false);

const form = reactive({
  room_id: undefined as number | undefined,
  date: new Date().toISOString().slice(0, 10),
  start_hour: 18,
  end_hour: 20,
  purpose: "",
  attendees: 10,
});

/** 提交的起止时间（带本地时区偏移的 ISO 串） */
const startAt = computed(() =>
  new Date(`${form.date}T${String(form.start_hour).padStart(2, "0")}:00:00`).toISOString(),
);
const endAt = computed(() => new Date(`${form.date}T${String(form.end_hour).padStart(2, "0")}:00:00`).toISOString());

const hours = Array.from({ length: 24 }, (_, i) => i);

async function load() {
  try {
    const [roomsRes, eligRes] = await Promise.all([
      seatRoomsApi.GET("/api/v1/seat/rooms", {
        params: { query: { is_whole_bookable: true, page: 1, size: 100 } },
      }),
      roomApi.GET("/api/v1/room/eligibility"),
    ]);
    rooms.value = roomsRes.data!.items.map((r) => ({ id: r.id, label: `${r.building} ${r.name}（${r.capacity} 人）` }));
    eligible.value = eligRes.data!;
  } catch (e) {
    showError(e);
  }
}

async function submit() {
  if (!form.room_id) {
    ElMessage.warning("请选择教室");
    return;
  }
  submitting.value = true;
  try {
    const { data } = await roomApi.POST("/api/v1/room/applications", {
      body: {
        room_id: form.room_id,
        start_at: startAt.value,
        end_at: endAt.value,
        purpose: form.purpose,
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

onMounted(load);
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
          <el-option v-for="r in rooms" :key="r.id" :label="r.label" :value="r.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="日期" required>
        <el-date-picker v-model="form.date" type="date" value-format="YYYY-MM-DD" :clearable="false" />
      </el-form-item>
      <el-form-item label="时段" required>
        <el-select v-model="form.start_hour" style="width: 100px">
          <el-option v-for="h in hours" :key="h" :label="`${h}:00`" :value="h" />
        </el-select>
        <span style="margin: 0 8px">至</span>
        <el-select v-model="form.end_hour" style="width: 100px">
          <el-option v-for="h in hours" :key="h" :label="`${h}:00`" :value="h" />
        </el-select>
      </el-form-item>
      <el-form-item label="用途" required>
        <el-input
          v-model="form.purpose"
          type="textarea"
          :rows="2"
          maxlength="500"
          show-word-limit
          placeholder="如：班级读书会"
        />
      </el-form-item>
      <el-form-item label="参加人数" required>
        <el-input-number v-model="form.attendees" :min="1" />
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
