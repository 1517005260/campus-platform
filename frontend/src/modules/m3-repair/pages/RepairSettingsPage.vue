<script setup lang="ts">
/**
 * 报修配置：故障分类、超时升级规则（状态 + 时长 + 通知权限）、代验收时长。
 */
import { ElMessage } from "element-plus";
import { computed, onMounted, reactive, ref } from "vue";

import { showError } from "@/core/http";

import { notifyPermLabel, orderStatusLabel, repairApi, type EscalationRule, type RepairSettings } from "../api";

const settings = reactive<RepairSettings>({
  admin_accept_after_hours: 72,
  categories: [],
  escalation_rules: [],
});
const loading = ref(false);
const saving = ref(false);

const ruleStatuses: ("dispatched" | "in_progress" | "pending_acceptance")[] = [
  "dispatched",
  "in_progress",
  "pending_acceptance",
];

async function load() {
  loading.value = true;
  try {
    const { data } = await repairApi.GET("/api/v1/repair/settings");
    Object.assign(settings, data!);
  } catch (e) {
    showError(e);
  } finally {
    loading.value = false;
  }
}

function addCategory() {
  settings.categories.push("");
}

/** 每个状态只能配置一条升级规则：新规则取第一个还没配置的状态，都配置了就不能再加 */
const unusedStatus = computed(() => ruleStatuses.find((st) => !settings.escalation_rules.some((r) => r.status === st)));

function addRule() {
  if (!unusedStatus.value) return;
  const rule: EscalationRule = { status: unusedStatus.value, timeout_hours: 24, notify_perm: "repair:manage" };
  settings.escalation_rules.push(rule);
}

async function save() {
  saving.value = true;
  try {
    const { data } = await repairApi.PUT("/api/v1/repair/settings", {
      body: {
        admin_accept_after_hours: settings.admin_accept_after_hours,
        categories: settings.categories.map((c) => c.trim()).filter(Boolean),
        escalation_rules: settings.escalation_rules,
      },
    });
    Object.assign(settings, data!);
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
  <el-card v-loading="loading" style="max-width: 720px">
    <el-form label-width="160px">
      <el-form-item label="代验收时长（小时）">
        <el-input-number v-model="settings.admin_accept_after_hours" :min="1" value-on-clear="min" />
        <span class="hint">报修人超过该时长未验收，管理员可代验收</span>
      </el-form-item>

      <el-form-item label="故障分类">
        <div v-for="(_, i) in settings.categories" :key="i" class="row">
          <el-input v-model="settings.categories[i]" maxlength="30" style="width: 140px" />
          <el-button
            link
            type="danger"
            :disabled="settings.categories.length <= 1"
            @click="settings.categories.splice(i, 1)"
          >
            删除
          </el-button>
        </div>
        <el-button link type="primary" @click="addCategory">添加分类</el-button>
      </el-form-item>

      <el-form-item label="超时升级规则">
        <div v-for="(r, i) in settings.escalation_rules" :key="i" class="row">
          <el-select v-model="r.status" style="width: 110px">
            <el-option
              v-for="s in ruleStatuses"
              :key="s"
              :label="orderStatusLabel[s]"
              :value="s"
              :disabled="settings.escalation_rules.some((o, j) => j !== i && o.status === s)"
            />
          </el-select>
          <span class="timeout">超时（小时）</span>
          <el-input-number v-model="r.timeout_hours" :min="1" value-on-clear="min" />
          <span class="timeout">通知</span>
          <el-select v-model="r.notify_perm" style="width: 200px">
            <el-option v-for="(label, perm) in notifyPermLabel" :key="perm" :label="label" :value="perm" />
          </el-select>
          <el-button link type="danger" @click="settings.escalation_rules.splice(i, 1)">删除</el-button>
        </div>
        <el-button link type="primary" :disabled="!unusedStatus" @click="addRule">添加规则</el-button>
      </el-form-item>

      <el-form-item>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </el-form-item>
    </el-form>
  </el-card>
</template>

<style scoped>
.row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.timeout {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.hint {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  margin-left: 12px;
}
</style>
