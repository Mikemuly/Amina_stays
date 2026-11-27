// Response shapes for the "Operate" section of the host console.
// Mirrors backend/apps/{bookings,insights,messaging,operations,properties,core,safety}/views.py.

import type { ChatMessage, TripCard } from "@/lib/types";

export interface ReservationRow {
  ref: string;
  status: string;
  status_label: string;
  channel: string;
  channel_label: string;
  unit: { id: number; name: string };
  guest: { id: number; name: string; phone: string; nationality: string };
  check_in: string;
  check_out: string;
  nights: number;
  guests: number;
  total: number;
  amount_paid: number;
  balance_due: number;
  payment_status: string;
  risk_score: number;
  created_at: string;
  hold_expires_at: string | null;
}

export interface Kpis {
  period: { start: string; end: string };
  occupancy: number;
  booked_nights: number;
  available_nights: number;
  room_revenue: number;
  adr: number;
  revpar: number;
  collected: number;
  refunded: number;
  by_method: Record<string, number>;
  bookings: number;
  by_channel: Record<string, { bookings: number; revenue: number }>;
  lead_time_days: number;
  avg_stay_nights: number;
  cancellation_rate: number;
  direct_share: number;
  addon_revenue: number;
  levy_due: number;
  response_minutes: number | null;
  auto_answer_rate: number;
  messages_in: number;
  reviews: number;
  rating: number | null;
}

export type TaskType = "turnover" | "maintenance" | "inspection" | "laundry" | "restock" | "guest_request" | "other";
export type TaskStatus = "open" | "in_progress" | "done" | "cancelled";
export type TaskPriority = "low" | "normal" | "high" | "urgent";

export interface TaskItem {
  id: number;
  unit_name: string | null;
  assignee_name: string | null;
  booking_ref: string | null;
  type_label: string;
  type: TaskType;
  title: string;
  description: string;
  category: string;
  priority: TaskPriority;
  status: TaskStatus;
  due_at: string | null;
  source: string;
  checklist: { item: string; done: boolean }[];
  completion_note: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  unit: number | null;
  booking: number | null;
  assignee: number | null;
  created_by: number | null;
}

export interface AlertItem {
  id: number;
  kind: string;
  kind_label: string;
  severity: string;
  status: string;
  source: string;
  phone: string;
  summary: string;
  details: string;
  call_status: string;
  calls_made: number;
  booking: string | null;
  created_at: string;
  acknowledged_at: string | null;
  resolved_at: string | null;
  resolution_note: string;
  resolved_by: string | null;
}

export interface ThreadRow {
  id: number;
  phone: string;
  status: string;
  needs_reply: boolean;
  unread: number;
  waiting_since: string | null;
  last_message_at: string | null;
  last_preview: string;
  guest: { id: number; name: string; lang: string; nationality: string; role: string } | null;
  booking: { ref: string; unit: string; status: string; check_in: string; check_out: string } | null;
}

export interface ThreadDetail {
  thread: ThreadRow;
  messages: ChatMessage[];
  bookings: TripCard[];
  quick_replies: string[];
}

export interface BreakfastRow {
  ref: string;
  unit: string;
  guest: string;
  people: number;
  style: string;
  style_label: string;
  dietary: string;
  time: string;
  notes: string;
}

export interface ActivityItem {
  id: number;
  kind: string;
  channel: string;
  title: string;
  detail?: string;
  booking_ref: string;
  phone?: string;
  actor?: string | null;
  created_at: string;
}

export interface TodayData {
  date: string;
  arrivals: ReservationRow[];
  departures: ReservationRow[];
  in_house: ReservationRow[];
  upcoming: ReservationRow[];
  holds: ReservationRow[];
  tasks: TaskItem[];
  alerts: AlertItem[];
  threads: ThreadRow[];
  breakfasts: BreakfastRow[];
  kpis: { week: Kpis; month: Kpis };
  activity: ActivityItem[];
}

export interface PendingRequest {
  id: number;
  kind?: "addon" | "change";
  addon: string;
  code: string;
  ref: string;
  unit: string;
  guest: string;
  details: Record<string, string>;
  total: number;
  created_at: string;
  change?: {
    old: { check_in: string; check_out: string; adults: number; children: number };
    new: { check_in: string; check_out: string; adults: number; children: number };
    delta: number;
    refund_amount: number;
  };
}

export interface LockRow {
  unit: { id: number; name: string; area: string; housekeeping: string; provider: string };
  state: "occupied" | "vacant";
  active: { code: string; ref: string; guest: string; valid_until: string; last_used_at: string | null } | null;
  next: { ref: string; valid_from: string } | null;
}

export interface CalBooking {
  ref: string;
  guest: string;
  check_in: string;
  check_out: string;
  status: string;
  channel: string;
  nights: number;
  total: number;
  balance_due: number;
}

export interface CalBlock {
  id: number;
  start_date: string;
  end_date: string;
  reason: string;
  reason_label: string;
  note: string;
  external: boolean;
  source: string | null;
}

export interface CalUnit {
  id: number;
  name: string;
  area: string;
  status: string;
  housekeeping: string;
  base_price: number;
  cover: string;
  bookings: CalBooking[];
  blocks: CalBlock[];
  prices: Record<string, number>;
  overrides: string[];
}

export interface CalendarResponse {
  start: string;
  end: string;
  days: string[];
  today: string;
  units: CalUnit[];
}

export interface HostListing {
  id: number;
  name: string;
  slug: string;
  area: string;
  status: string;
  max_guests: number;
  base_price: number;
  min_nights: number;
  housekeeping: string;
  photos: { id: number; src: string }[];
}

export interface StaffMember {
  id: number;
  phone: string;
  name: string;
  role: string;
  lang: string;
  is_active: boolean;
  unit_ids: number[];
  open_tasks: number;
}

export interface KitchenData {
  date: string;
  rows: BreakfastRow[];
  people: number;
  text: string | null;
}
