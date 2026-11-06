<script setup lang="ts">
/**
 * 工单看板：调度员派单（指定维修工、截止时间、是否下架教室），
 * 维修工开始维修/完工，报修人视角看状态与升级情况。
 */
import { ElMessage } from "element-plus";
import { onMounted, reactive, ref, watch } from "vue";

import PaginatedTable from "@/core/components/PaginatedTable.vue";
import { confirmAction } from "@/core/dialogs";
import { bizIso, bizWallTime, fmtTime, isPastDate } from "@/core/format";
import { showError } from "@/core/http";
import { usePagedList } from "@/core/pagedList";
import { useAuthStore } from "@/core/auth/store";

import OrderDetailDialog from "./OrderDetailDialog.vue";
import { orderStatusLabel, repairApi, type WorkOrder } from "../api";

const auth = useAuthStore();

/** ---- 列表与筛选 ---- */
const status = ref<WorkOrder["status"]>();
const escalated = ref(false);
const { items, total, page, size, loading, load, reload } = usePagedList((p) =>
  repairApi
    .GET("/api/v1/repair/orders", {
      params: { query: { status: status.value, escalated: escalated.value || undefined, ...p } },
    })
    .then((r) => r.data!),
);
watch([status, escalated], reload);

const statusOptions = Object.entries(orderStatusLabel).map(([value, label]) => ({ value, label }));

/** 开始维修、完工只有被指派的维修工能做（后端校验 NOT_ASSIGNEE） */
const isAssignee = (o: WorkOrder) => o.assignee !== null && o.assignee.id === auth.user?.id;

/** ---- 派单 ---- */
const dispatching = ref<WorkOrder | null>(null);

/** 默认处理截止：24 小时后（业务时区墙上时间，作为选择器的值） */
const defaultDeadline = () => bizWallTime(new Date(Date.now() + 24 * 3600 * 1000));

const dispatchForm = reactive({
  assignee_id: undefined as number | undefined,
  blocks_room: false,
  deadline: defaultDeadline(),
});
const dispatchSubmitting = ref(false);

function openDispatch(o: WorkOrder) {
  dispatching.value = o;
  dispatchForm.assignee_id = undefined;
  dispatchForm.blocks_room = false;
  dispatchForm.deadline = defaultDeadline();
}

async function dispatch() {
  if (!dispatching.value || !dispatchForm.assignee_id) {
    ElMessage.warning("请填写维修工用户 ID");
    return;
  }
  dispatchSubmitting.value = true;
  try {
    await repairApi.POST("/api/v1/repair/orders/{order_id}/dispatch", {
      params: { path: { order_id: dispatching.value.id } },
      body: {
        assignee_id: dispatchForm.assignee_id,
        blocks_room: dispatchForm.blocks_room,
        deadline_at: bizIso(dispatchForm.deadline),
      },
    });
    ElMessage.success("已派单");
    dispatching.value = null;
    await load();
  } catch (e) {
    showError(e);
  } finally {
    dispatchSubmitting.value = false;
  }
}

/** ---- 开始维修 / 完工 ---- */
async function start(o: WorkOrder) {
  if (!(await confirmAction(`开始维修工单 #${o.id}？${o.blocks_room ? "教室将同时下架。" : ""}`))) return;
  try {
    await repairApi.POST("/api/v1/repair/orders/{order_id}/start", {
      params: { path: { order_id: o.id } },
    });
    ElMessage.success("已开始维修");
    await load();
  } catch (e) {
    showError(e);
  }
}

const completing = ref<WorkOrder | null>(null);
const completeForm = reactive({ note: "", photos: "" });
const completeSubmitting = ref(false);

function openComplete(o: WorkOrder) {
  completing.value = o;
  completeForm.note = "";
  completeForm.photos = "";
}

async function complete() {
  if (!completing.value || completeForm.note.trim().length < 2) {
    ElMessage.warning("请填写完工说明");
    return;
  }
  completeSubmitting.value = true;
  try {
    await repairApi.POST("/api/v1/repair/orders/{order_id}/complete", {
      params: { path: { order_id: completing.value.id } },
      body: {
        note: completeForm.note.trim(),
        photos: completeForm.photos
          .split("\n")
          .map((p) => p.trim())
          .filter(Boolean),
      },
    });
    ElMessage.success("已完工，等待报修人验收");
    completing.value = null;
    await load();
  } catch (e) {
    showError(e);
  } finally {
    completeSubmitting.value = false;
  }
}

/** ---- 详情 ---- */
const detailVisible = ref(false);
const detailOrder = ref<WorkOrder | null>(null);

function showDetail(o: WorkOrder) {
  detailOrder.value = o;
  detailVisible.value = true;
}

onMounted(load);
</script>

<template>
  <el-form inline @submit.prevent="reload" style="margin-bottom: 4px">
    <el-form-item label="状态">
      <el-select v-model="status" clearable placeholder="全部" style="width: 130px">
        <el-option v-for="o in statusOptions" :key="o.value" :label="o.label" :value="o.value" />
      </el-select>
    </el-form-item>
    <el-form-item label="只看已升级">
      <el-switch v-model="escalated" />
    </el-form-item>
    <el-button type="primary" native-type="submit" :loading="loading">查询</el-button>
  </el-form>

  <PaginatedTable :data="items" :loading="loading" :total="total" v-model:page="page" v-model:size="size">
    <el-table-column label="工单号" prop="id" width="80" />
    <el-table-column label="报修人" prop="reporter.name" width="100" />
    <el-table-column label="教室" prop="room_id" width="80" />
    <el-table-column label="分类" prop="category" width="90" />
    <el-table-column label="维修人" width="100">
      <template #default="{ row }">{{ row.assignee?.name ?? "—" }}</template>
    </el-table-column>
    <el-table-column label="状态" width="100">
      <template #default="{ row }">{{ orderStatusLabel[row.status as WorkOrder["status"]] }}</template>
    </el-table-column>
    <el-table-column label="截止">
      <template #default="{ row }">{{ fmtTime(row.deadline_at) || "—" }}</template>
    </el-table-column>
    <el-table-column label="升级" width="70">
      <template #default="{ row }">
        <el-tag v-if="row.escalation_level > 0" size="small" type="danger">{{ row.escalation_level }}</el-tag>
        <span v-else>0</span>
      </template>
    </el-table-column>
    <el-table-column label="操作" width="210">
      <template #default="{ row }">
        <el-button size="small" link type="primary" @click="showDetail(row)">详情</el-button>
        <el-button
          v-if="auth.can('repair:dispatch') && row.status === 'submitted'"
          size="small"
          type="primary"
          @click="openDispatch(row)"
        >
          派单
        </el-button>
        <el-button
          v-if="row.status === 'dispatched' && isAssignee(row)"
          size="small"
          type="primary"
          @click="start(row)"
        >
          开始维修
        </el-button>
        <el-button
          v-if="row.status === 'in_progress' && isAssignee(row)"
          size="small"
          type="success"
          @click="openComplete(row)"
        >
          完工
        </el-button>
      </template>
    </el-table-column>
  </PaginatedTable>

  <el-dialog
    :model-value="dispatching !== null"
    :title="`派单 · 工单 #${dispatching?.id}`"
    width="460px"
    @close="dispatching = null"
  >
    <el-form label-width="100px">
      <el-form-item label="维修工 ID" required>
        <el-input-number v-model="dispatchForm.assignee_id" :min="1" />
        <span class="hint">拥有维修权限的用户编号</span>
      </el-form-item>
      <el-form-item label="处理截止" required>
        <el-date-picker
          v-model="dispatchForm.deadline"
          type="datetime"
          value-format="YYYY-MM-DDTHH:mm:ss"
          :clearable="false"
          :disabled-date="isPastDate"
        />
      </el-form-item>
      <el-form-item label="下架教室">
        <el-switch v-model="dispatchForm.blocks_room" />
        <span class="hint">开始维修时把整间教室下架（经 M1）</span>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dispatching = null">取消</el-button>
      <el-button type="primary" :loading="dispatchSubmitting" @click="dispatch">派单</el-button>
    </template>
  </el-dialog>

  <el-dialog
    :model-value="completing !== null"
    :title="`完工 · 工单 #${completing?.id}`"
    width="460px"
    @close="completing = null"
  >
    <el-form label-width="80px">
      <el-form-item label="完工说明" required>
        <el-input v-model="completeForm.note" type="textarea" :rows="3" maxlength="1000" show-word-limit />
      </el-form-item>
      <el-form-item label="照片">
        <el-input v-model="completeForm.photos" type="textarea" :rows="2" placeholder="图片链接，每行一个（可选）" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="completing = null">取消</el-button>
      <el-button type="primary" :loading="completeSubmitting" @click="complete">提交完工</el-button>
    </template>
  </el-dialog>

  <OrderDetailDialog v-model="detailVisible" :order="detailOrder" />
</template>

<style scoped>
.hint {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  margin-left: 12px;
}
</style>
