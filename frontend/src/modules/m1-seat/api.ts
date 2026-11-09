import type { components } from "@/api/types/m1-seat";
import type { Seat } from "@/core/rooms";

// M1 的客户端只有一个，定义在 core（M2、M3 选教室也要用）
export { seatApi } from "@/core/seatApi";
export type { OpenHour, Room, Seat } from "@/core/rooms";
export type RoomDetail = components["schemas"]["RoomDetail"];
export type RoomCreate = components["schemas"]["RoomCreate"];
export type RoomUpdate = components["schemas"]["RoomUpdate"];
export type SeatCreate = components["schemas"]["SeatCreate"];
export type SeatUpdate = components["schemas"]["SeatUpdate"];
export type Reservation = components["schemas"]["Reservation"];
export type ReservationDetail = components["schemas"]["ReservationDetail"];
export type SeatSearchItem = components["schemas"]["SeatSearchItem"];
export type SeatSettings = components["schemas"]["SeatSettings"];
export type UsageStats = components["schemas"]["UsageStats"];
export type RoomUsage = components["schemas"]["RoomUsage"];
export type CheckinCode = components["schemas"]["CheckinCodeOut"];
export type Violation = components["schemas"]["ViolationOut"];
export type SeatAvailability = components["schemas"]["SeatAvailability"];
export type StatusHistoryItem = components["schemas"]["StatusHistoryItem"];

export const outletLabel: Record<Seat["outlet"], string> = { none: "无", fixed: "固定", rail: "导轨" };
