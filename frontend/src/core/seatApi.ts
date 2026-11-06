/**
 * M1（自习座位）服务的唯一类型化客户端：m1-seat 模块经 modules/m1-seat/api.ts 使用；
 * M2 申请、M3 报修选教室和座位也读 M1 的教室，经 core/rooms.ts 共用同一个实例。
 */
import type { paths } from "@/api/types/m1-seat";
import { createApi } from "@/core/http";

export const seatApi = createApi<paths>();
