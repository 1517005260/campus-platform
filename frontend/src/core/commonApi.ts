/**
 * common 服务的唯一类型化客户端：core 用它登录、查未读通知，common 模块的页面经 modules/common/api.ts 使用同一个实例。
 */
import type { paths } from "@/api/types/common";
import { createApi } from "@/core/http";

export const commonApi = createApi<paths>();
