<script setup lang="ts">
import { ElMessage, ElMessageBox } from "element-plus";
import { computed, onMounted, reactive, ref } from "vue";

import { useAuthStore } from "@/core/auth/store";
import { fmtTime } from "@/core/format";
import { showError } from "@/core/http";

import { commonApi, type DeptOut, type RoleOut, type UserAdmin } from "../api";

const auth = useAuthStore();
const users = ref<UserAdmin[]>([]);
const total = ref(0);
const loading = ref(false);
const depts = ref<DeptOut[]>([]);
const roles = ref<RoleOut[]>([]);

const filters = reactive({
  keyword: "",
  dept_id: undefined as number | undefined,
  role: undefined as string | undefined,
  active: undefined as boolean | undefined,
});
const page = ref(1);
const size = 20;

const deptName = computed(() => Object.fromEntries(depts.value.map((d) => [d.id, d.name])));
const roleName = computed(() => Object.fromEntries(roles.value.map((r) => [r.code, r.name])));

async function load() {
  loading.value = true;
  try {
    const { data } = await commonApi.GET("/api/v1/admin/users", {
      params: { query: { ...filters, keyword: filters.keyword || undefined, page: page.value, size } },
    });
    users.value = data!.items;
    total.value = data!.total;
  } catch (e) {
    showError(e);
  } finally {
    loading.value = false;
  }
}

function search() {
  page.value = 1;
  load();
}

// ---- 新建 / 编辑资料 ----
const editDialog = ref(false);
const editing = ref<UserAdmin | null>(null); // null 表示新建
const form = reactive({
  username: "",
  name: "",
  email: "",
  dept_id: null as number | null,
  password: "",
  role_codes: [] as string[],
});
const saving = ref(false);

function openCreate() {
  editing.value = null;
  Object.assign(form, { username: "", name: "", email: "", dept_id: null, password: "", role_codes: [] });
  editDialog.value = true;
}

function openEdit(u: UserAdmin) {
  editing.value = u;
  Object.assign(form, {
    username: u.username,
    name: u.name,
    email: u.email ?? "",
    dept_id: u.dept_id,
    password: "",
    role_codes: [...u.roles],
  });
  editDialog.value = true;
}

async function save() {
  saving.value = true;
  const email = form.email.trim() || null;
  try {
    if (editing.value) {
      await commonApi.PATCH("/api/v1/admin/users/{user_id}", {
        params: { path: { user_id: editing.value.id } },
        body: { name: form.name, email, dept_id: form.dept_id, password: form.password || undefined },
      });
    } else {
      await commonApi.POST("/api/v1/admin/users", { body: { ...form, email } });
    }
    ElMessage.success("已保存");
    editDialog.value = false;
    await load();
  } catch (e) {
    showError(e);
  } finally {
    saving.value = false;
  }
}

// ---- 设置角色 ----
const roleDialog = ref(false);
const roleTarget = ref<UserAdmin | null>(null);
const roleCodes = ref<string[]>([]);

function openRoles(u: UserAdmin) {
  roleTarget.value = u;
  roleCodes.value = [...u.roles];
  roleDialog.value = true;
}

async function saveRoles() {
  try {
    await commonApi.PUT("/api/v1/admin/users/{user_id}/roles", {
      params: { path: { user_id: roleTarget.value!.id } },
      body: { role_codes: roleCodes.value },
    });
    ElMessage.success("角色已更新，用户重新登录后生效");
    roleDialog.value = false;
    await load();
  } catch (e) {
    showError(e);
  }
}

// ---- 停用 / 启用 ----
async function toggleActive(u: UserAdmin) {
  const action = u.active ? "停用" : "启用";
  try {
    await ElMessageBox.confirm(
      u.active ? `停用后 ${u.name} 不能再登录（已登录的会话到期前仍有效）。确认停用？` : `启用 ${u.name}？`,
      action,
    );
  } catch {
    return;
  }
  try {
    await commonApi.PATCH("/api/v1/admin/users/{user_id}", {
      params: { path: { user_id: u.id } },
      body: { active: !u.active },
    });
    ElMessage.success(`已${action}`);
    await load();
  } catch (e) {
    showError(e);
  }
}

onMounted(async () => {
  try {
    const [d, r] = await Promise.all([commonApi.GET("/api/v1/admin/depts"), commonApi.GET("/api/v1/admin/roles")]);
    depts.value = d.data!;
    roles.value = r.data!;
  } catch (e) {
    showError(e);
  }
  await load();
});
</script>

<template>
  <el-form inline @submit.prevent="search">
    <el-form-item>
      <el-input v-model="filters.keyword" placeholder="用户名或姓名" clearable style="width: 180px" />
    </el-form-item>
    <el-form-item>
      <el-select v-model="filters.dept_id" placeholder="院系" clearable style="width: 200px">
        <el-option v-for="d in depts" :key="d.id" :label="d.name" :value="d.id" />
      </el-select>
    </el-form-item>
    <el-form-item>
      <el-select v-model="filters.role" placeholder="角色" clearable style="width: 150px">
        <el-option v-for="r in roles" :key="r.code" :label="r.name" :value="r.code" />
      </el-select>
    </el-form-item>
    <el-form-item>
      <el-select v-model="filters.active" placeholder="状态" clearable style="width: 100px">
        <el-option label="启用" :value="true" />
        <el-option label="停用" :value="false" />
      </el-select>
    </el-form-item>
    <el-form-item>
      <el-button type="primary" native-type="submit">查询</el-button>
      <el-button @click="openCreate">新建用户</el-button>
    </el-form-item>
  </el-form>

  <el-table :data="users" v-loading="loading">
    <el-table-column label="ID" prop="id" width="60" />
    <el-table-column label="用户名" prop="username" width="140" />
    <el-table-column label="姓名" prop="name" width="140" />
    <el-table-column label="院系" width="170">
      <template #default="{ row }">{{ row.dept_id ? (deptName[row.dept_id] ?? row.dept_id) : "—" }}</template>
    </el-table-column>
    <el-table-column label="角色" min-width="200">
      <template #default="{ row }">
        <el-tag v-for="r in row.roles" :key="r" size="small" style="margin: 2px">{{ roleName[r] ?? r }}</el-tag>
      </template>
    </el-table-column>
    <el-table-column label="邮箱" prop="email" min-width="200" show-overflow-tooltip />
    <el-table-column label="状态" width="70">
      <template #default="{ row }">
        <el-tag :type="row.active ? 'success' : 'info'" size="small">{{ row.active ? "启用" : "停用" }}</el-tag>
      </template>
    </el-table-column>
    <el-table-column label="创建时间" width="170">
      <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
    </el-table-column>
    <el-table-column width="170">
      <template #default="{ row }">
        <el-button size="small" link type="primary" @click="openEdit(row)">编辑</el-button>
        <el-button size="small" link type="primary" @click="openRoles(row)">角色</el-button>
        <el-button
          size="small"
          link
          :type="row.active ? 'danger' : 'success'"
          :disabled="row.id === auth.user?.id"
          @click="toggleActive(row)"
        >
          {{ row.active ? "停用" : "启用" }}
        </el-button>
      </template>
    </el-table-column>
  </el-table>
  <el-pagination
    v-model:current-page="page"
    class="pager"
    layout="total, prev, pager, next"
    :page-size="size"
    :total="total"
    @current-change="load"
  />

  <el-dialog v-model="editDialog" :title="editing ? `编辑用户：${editing.username}` : '新建用户'" width="520px">
    <el-form label-width="80px">
      <el-form-item label="用户名">
        <el-input v-model="form.username" :disabled="!!editing" placeholder="学号或工号" />
      </el-form-item>
      <el-form-item label="姓名"><el-input v-model="form.name" /></el-form-item>
      <el-form-item label="邮箱"><el-input v-model="form.email" placeholder="接收提醒邮件，可为空" /></el-form-item>
      <el-form-item label="院系">
        <el-select v-model="form.dept_id" clearable placeholder="不属于任何院系" style="width: 100%">
          <el-option v-for="d in depts" :key="d.id" :label="d.name" :value="d.id" />
        </el-select>
      </el-form-item>
      <el-form-item :label="editing ? '重置密码' : '密码'">
        <el-input
          v-model="form.password"
          type="password"
          show-password
          :placeholder="editing ? '留空表示不修改' : '至少 8 位'"
        />
      </el-form-item>
      <el-form-item v-if="!editing" label="角色">
        <el-select v-model="form.role_codes" multiple style="width: 100%">
          <el-option v-for="r in roles" :key="r.code" :label="r.name" :value="r.code" />
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="editDialog = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="roleDialog" :title="`设置角色：${roleTarget?.name}`" width="520px">
    <el-checkbox-group v-model="roleCodes">
      <el-checkbox v-for="r in roles" :key="r.code" :value="r.code">{{ r.name }}</el-checkbox>
    </el-checkbox-group>
    <template #footer>
      <el-button @click="roleDialog = false">取消</el-button>
      <el-button type="primary" @click="saveRoles">保存</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.pager {
  margin-top: 12px;
  justify-content: flex-end;
}
</style>
