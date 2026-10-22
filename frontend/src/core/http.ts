/**
 * 统一 HTTP 层。各模块用 createApi<paths>() 得到一个带类型的客户端：
 *
 *   import type { paths } from "@/api/types/m1-seat";
 *   export const api = createApi<paths>();
 *   const { data } = await api.GET("/api/v1/seat/rooms", { params: { query: { page: 1 } } });
 *
 * 路径、参数、响应类型都来自 contracts/openapi（npm run gen:types），后端改接口前端编译即报错。
 * 请求自动带 token；后端的统一错误 {code, message, details, request_id} 转成 ApiError 抛出；
 * 401 时清除登录状态并跳转登录页。
 */
import createClient, { type Middleware } from "openapi-fetch";
import { ElMessage } from "element-plus";

import { useAuthStore } from "@/core/auth/store";

export interface ErrorBody {
  code: string;
  message: string;
  details?: unknown;
  request_id?: string | null;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public body: ErrorBody,
  ) {
    super(body.message);
  }
  get code() {
    return this.body.code;
  }
}

const auth: Middleware = {
  onRequest({ request }) {
    const token = useAuthStore().token;
    if (token) request.headers.set("Authorization", `Bearer ${token}`);
    return request;
  },
  async onResponse({ response }) {
    if (response.ok) return response;
    let body: ErrorBody;
    try {
      body = (await response.clone().json()) as ErrorBody;
    } catch {
      body = { code: `HTTP_${response.status}`, message: response.statusText };
    }
    if (response.status === 401 && body.code !== "LOGIN_FAILED") {
      useAuthStore().logout();
    }
    throw new ApiError(response.status, body);
  },
};

export function createApi<Paths extends object>() {
  const client = createClient<Paths>({ baseUrl: "/" });
  client.use(auth);
  return client;
}

/** 把接口错误展示给用户；非 ApiError 原样抛出。附带 request_id 便于反馈问题。 */
export function showError(e: unknown): void {
  if (e instanceof ApiError) {
    const rid = e.body.request_id ? `（请求 ID ${e.body.request_id.slice(0, 8)}）` : "";
    ElMessage.error(`${e.message}${rid}`);
    return;
  }
  throw e;
}
