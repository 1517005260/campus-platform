<script setup lang="ts">
import { ElMessage, ElMessageBox } from "element-plus";
import { computed, onMounted, ref } from "vue";

import { showError } from "@/core/http";

import { commonApi, moduleLabel, type PermissionOut, type RoleOut } from "../api";

const roles = ref<RoleOut[]>([]);
const perms = ref<PermissionOut[]>([]);
const loading = ref(false);

/** 权限码按模块分组，供编辑对话框勾选 */
const permGroups = computed(() => {
  const groups = new Map<string, PermissionOut[]>();
  for (const p of perms.value) groups.set(p.module, [...(groups.get(p.module) ?? []), p]);
  return [...groups.entries()];
});
const permDesc = computed(() => Object.fromEntries(perms.value.map((p) => [p.code, p.description])));

async function load() {
  loading.value = true;
  try {
    const [r, p] = await Promise.all([
      commonApi.GET("/api/v1/admin/roles"),
      commonApi.GET("/api/v1/admin/permissions"),
    ]);
    roles.value = r.data!;
    perms.value = p.data!;
  } catch (e) {
    showError(e);
  } finally {
    loading.value = false;
  }
}

// ---- 新建 / 编辑 ----
const dialog = ref(false);
const editing = ref<RoleOut | null>(null); // null 表示新建
const form = ref({ code: "", name: "", perms: [] as string[] });
const saving = ref(false);

function openCreate() {
  editing.value = null;
  form.value = { code: "", name: "", perms: [] };
  dialog.value = true;
}

function openEdit(role: RoleOut) {
  editing.value = role;
  form.value = { code: role.code, name: role.name, perms: [...role.perms] };
  dialog.value = true;
}

async function save() {
  saving.value = true;
  try {
    if (editing.value) {
      await commonApi.PATCH("/api/v1/admin/roles/{code}", {
        params: { path: { code: editing.value.code } },
        body: { name: editing.value.builtin ? undefined : form.value.name, perms: form.value.perms },
      });
    } else {
      await commonApi.POST("/api/v1/admin/roles", { body: form.value });
    }
    ElMessage.success("已保存，相关用户重新登录后生效");
    dialog.value = false;
    await load();
  } catch (e) {
    showError(e);
  } finally {
    saving.value = false;
  }
}

async function remove(role: RoleOut) {
  try {
    await ElMessageBox.confirm(`删除角色"${role.name}"？`, "确认");
  } catch {
    return;
  }
  try {
    await commonApi.DELETE("/api/v1/admin/roles/{code}", { params: { path: { code: role.code } } });
    ElMessage.success("已删除");
    await load();
  } catch (e) {
    showError(e);
  }
}

onMounted(load);
</script>

<template>
  <div class="toolbar">
    <el-text type="info">预置角色不能删除、改名，可以调整权限；权限变化在用户下次登录后生效。</el-text>
    <el-button type="primary" @click="openCreate">新建角色</el-button>
  </div>
  <el-table :data="roles" v-loading="loading">
    <el-table-column label="编码" prop="code" width="160" />
    <el-table-column label="名称" width="150">
      <template #default="{ row }">
        {{ row.name }}
        <el-tag v-if="row.builtin" size="small" type="info">预置</el-tag>
      </template>
    </el-table-column>
    <el-table-column label="用户数" prop="user_count" width="80" />
    <el-table-column label="权限">
      <template #default="{ row }">
        <el-tooltip v-for="p in row.perms" :key="p" :content="permDesc[p] ?? p">
          <el-tag size="small" style="margin: 2px">{{ p }}</el-tag>
        </el-tooltip>
      </template>
    </el-table-column>
    <el-table-column width="130">
      <template #default="{ row }">
        <el-button size="small" link type="primary" @click="openEdit(row)">编辑</el-button>
        <el-button
          v-if="!row.builtin"
          size="small"
          link
          type="danger"
          :disabled="row.user_count > 0"
          :title="row.user_count > 0 ? '还有用户拥有该角色' : ''"
          @click="remove(row)"
        >
          删除
        </el-button>
      </template>
    </el-table-column>
  </el-table>

  <el-dialog v-model="dialog" :title="editing ? `编辑角色：${editing.name}` : '新建角色'" width="640px">
    <el-form label-width="80px">
      <el-form-item label="编码">
        <el-input v-model="form.code" :disabled="!!editing" placeholder="小写字母开头，如 lab_manager" />
      </el-form-item>
      <el-form-item label="名称">
        <el-input v-model="form.name" :disabled="editing?.builtin" />
      </el-form-item>
      <el-form-item label="权限">
        <el-checkbox-group v-model="form.perms">
          <div v-for="[module, items] in permGroups" :key="module" class="perm-group">
            <div class="perm-module">{{ moduleLabel[module] ?? module }}</div>
            <el-checkbox v-for="p in items" :key="p.code" :value="p.code">
              {{ p.code }}<span class="perm-desc">{{ p.description }}</span>
            </el-checkbox>
          </div>
        </el-checkbox-group>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialog = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.perm-group {
  width: 100%;
}
.perm-module {
  /* el-checkbox-group 把 font-size 设为 0 */
  font-size: var(--el-font-size-base);
  font-weight: 600;
  margin-top: 4px;
}
.perm-desc {
  margin-left: 6px;
  color: var(--el-text-color-secondary);
}
</style>
