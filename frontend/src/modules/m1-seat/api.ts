import type { components, paths } from "@/api/types/m1-seat";
import { createApi } from "@/core/http";

export const seatApi = createApi<paths>();
export type Room = components["schemas"]["Room"];
export type Seat = components["schemas"]["Seat"];
export type Reservation = components["schemas"]["Reservation"];
export type ReservationDetail = components["schemas"]["ReservationDetail"];
export type SeatSearchItem = components["schemas"]["SeatSearchItem"];
