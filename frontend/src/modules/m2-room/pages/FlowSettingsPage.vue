<script setup lang="ts">
/**
 * 审批流与申请参数配置：审批流按教室类型/院系匹配（priority 越大越优先），
 * 每级指定范围（院系/学校）、审批权限与超时时间；申请参数控制门槛。
 */
import { ElMessage, ElMessageBox } from "element-plus";
import { onMounted, reactive, ref } from "vue";

import { showError } from "@/core/http";

import { roomApi, type ApprovalFlow, type RoomSettings } from "../api";

const flows = ref<ApprovalFlow[]>([]);
const flowsLoading = ref(false);
const flowsSaving = ref(false);

const roomTypeOptions = [
  { value: "classroom", label: "教室" },
  { value: "library", label: "图书馆" },
  { value: "other", label: "其他" },
];
const scopeLabel: Record<string, string> = { dept: "院系", school: "学校" };

function emptyFlow(): ApprovalFlow {
  return {
    name: "新审批流",
    room_type: null,
    dept_scoped: null,
    priority: 0,
    levels: [{ level: 1, scope: "dept", approver_perm: "room:approve", timeout_hours: 48 }],
  };
}

function addLevel(flow: ApprovalFlow) {
  flow.levels.push({
    level: flow.levels.length + 1,
    scope: "dept",
    approver_perm: "room:approve",
    timeout_hours: 48,
  });
}

/** 删除级别后重排序号 */
function removeLevel(flow: ApprovalFlow, i: number) {
  flow.levels.splice(i, 1);
  flow.levels.forEach((l, idx) => (l.level = idx + 1));
}

async function loadFlows() {
  flowsLoading.value = true;
  try {
    const { data } = await roomApi.GET("/api/v1/room/flows");
    flows.value = data!;
  } catch (e) {
    showError(e);
  } finally {
    flowsLoading.value = false;
  }
}

async function saveFlows() {
  flowsSaving.value = true;
  try {
    await roomApi.PUT("/api/v1/room/flows", { body: flows.value });
    ElMessage.success("审批流已保存");
    await loadFlows();
  } catch (e) {
    showError(e);
  } finally {
    flowsSaving.value = false;
  }
}

async function removeFlow(i: number) {
  await ElMessageBox.confirm(`删除审批流「${flows.value[i]!.name}」？`, "确认");
  flows.value.splice(i, 1);
}

/** ---- 申请参数 ---- */
const settings = reactive<RoomSettings>({
  advance_days_min: 1,
  advance_days_max: 30,
  max_violations: 3,
  violation_window_days: 30,
});
const settingsLoading = ref(false);
const settingsSaving = ref(false);

const settingFields: { key: keyof RoomSettings; label: string; min: number; hint: string }[] = [
  { key: "advance_days_min", label: "至少提前（天）", min: 0, hint: "申请距使用日的最少天数" },
  { key: "advance_days_max", label: "最多提前（天）", min: 1, hint: "申请距使用日的最多天数" },
  { key: "max_violations", label: "违约次数上限", min: 0, hint: "窗口期内达到该次数不能申请" },
  { key: "violation_window_days", label: "违约统计窗口（天）", min: 1, hint: "违约次数统计的时间窗口" },
];

async function loadSettings() {
  settingsLoading.value = true;
  try {
    const { data } = await roomApi.GET("/api/v1/room/settings");
    Object.assign(settings, data!);
  } catch (e) {
    showError(e);
  } finally {
    settingsLoading.value = false;
  }
}

async function saveSettings() {
  settingsSaving.value = true;
  try {
    const { data } = await roomApi.PUT("/api/v1/room/settings", { body: { ...settings } });
    Object.assign(settings, data!);
    ElMessage.success("申请参数已保存");
  } catch (e) {
    showError(e);
  } finally {
    settingsSaving.value = false;
  }
}

onMounted(() => {
  void loadFlows();
  void loadSettings();
});
</script>

<template>
  <el-card header="审批流" v-loading="flowsLoading" style="margin-bottom: 16px">
    <el-empty v-if="flows.length === 0" description="暂无审批流" :image-size="60" />
    <div v-for="(flow, i) in flows" :key="i" class="flow">
      <div class="flow-head">
        <el-input v-model="flow.name" placeholder="审批流名称" style="width: 200px" />
        <el-select v-model="flow.room_type" clearable placeholder="适用类型：全部" style="width: 140px">
          <el-option v-for="o in roomTypeOptions" :key="o.value" :label="o.label" :value="o.value" />
        </el-select>
        <el-select v-model="flow.dept_scoped" clearable placeholder="院系限制：不限" style="width: 150px">
          <el-option label="仅本院系教室" :value="true" />
          <el-option label="全校教室" :value="false" />
        </el-select>
        <span class="priority">优先级</span>
        <el-input-number v-model="flow.priority" :min="0" />
        <el-button link type="danger" @click="removeFlow(i)">删除审批流</el-button>
      </div>

      <div v-for="(l, j) in flow.levels" :key="j" class="level-row">
        <el-tag size="small">第 {{ l.level }} 级</el-tag>
        <el-select v-model="l.scope" style="width: 110px">
          <el-option v-for="(label, value) in scopeLabel" :key="value" :label="label" :value="value" />
        </el-select>
        <el-input v-model="l.approver_perm" placeholder="审批权限码" style="width: 200px" />
        <span class="timeout">超时（小时）</span>
        <el-input-number v-model="l.timeout_hours" :min="1" />
        <el-button link type="danger" :disabled="flow.levels.length <= 1" @click="removeLevel(flow, j)">
          删除
        </el-button>
      </div>
      <el-button link type="primary" @click="addLevel(flow)">添加审批级</el-button>
    </div>

    <div style="margin-top: 12px">
      <el-button @click="flows.push(emptyFlow())">添加审批流</el-button>
      <el-button type="primary" :loading="flowsSaving" :disabled="flows.length === 0" @click="saveFlows">
        保存审批流
      </el-button>
    </div>
  </el-card>

  <el-card header="申请参数" v-loading="settingsLoading" style="max-width: 640px">
    <el-form label-width="170px">
      <el-form-item v-for="f in settingFields" :key="f.key" :label="f.label">
        <el-input-number v-model="settings[f.key]" :min="f.min" />
        <span class="hint">{{ f.hint }}</span>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :loading="settingsSaving" @click="saveSettings">保存参数</el-button>
      </el-form-item>
    </el-form>
  </el-card>
</template>

<style scoped>
.flow {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 12px;
  margin-bottom: 12px;
}
.flow-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.priority,
.timeout {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.level-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.hint {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  margin-left: 12px;
}
</style>
