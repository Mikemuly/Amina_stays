import { addDays, differenceInCalendarDays, format, formatDistanceToNowStrict, isToday, isTomorrow, isYesterday, parseISO, startOfToday } from "date-fns";

export const kes = (n?: number | null) => `KES ${Math.round(n ?? 0).toLocaleString("en-KE")}`;

export function approx(n: number, rates?: Record<string, number>, currency = "USD") {
  const rate = rates?.[currency];
  if (!rate) return "";
  const symbol = { USD: "$", EUR: "€", GBP: "£" }[currency] ?? "";
  return `≈ ${symbol}${Math.round(n / rate).toLocaleString("en-KE")}`;
}

export const toDate = (d: string | Date) => (typeof d === "string" ? parseISO(d) : d);
export const iso = (d: Date) => format(d, "yyyy-MM-dd");

export const fmtDate = (d?: string | Date | null, pattern = "EEE d MMM") => (d ? format(toDate(d), pattern) : "");
export const fmtShort = (d?: string | Date | null) => fmtDate(d, "d MMM");
export const fmtLong = (d?: string | Date | null) => fmtDate(d, "EEEE, d MMMM yyyy");
export const fmtTime = (d?: string | Date | null) => (d ? format(toDate(d), "h:mm a") : "");
export const fmtDateTime = (d?: string | Date | null) => (d ? format(toDate(d), "d MMM, h:mm a") : "");

export function fmtRange(a?: string | null, b?: string | null) {
  if (!a || !b) return "";
  const da = toDate(a), db = toDate(b);
  if (da.getMonth() === db.getMonth() && da.getFullYear() === db.getFullYear()) return `${format(da, "d")} – ${format(db, "d MMM")}`;
  return `${format(da, "d MMM")} – ${format(db, "d MMM")}`;
}

/** Last day a stay can be cancelled for a full refund under our policies (null when the policy never refunds in full). */
export function freeCancelUntil(policy: string | undefined, checkIn?: string | null) {
  const days = { flexible: 1, moderate: 5, firm: 30 }[policy ?? ""];
  if (!days || !checkIn) return null;
  const until = addDays(toDate(checkIn), -days);
  return until >= startOfToday() ? until : null;
}

export const nightsBetween = (a?: string | null, b?: string | null) => (a && b ? differenceInCalendarDays(toDate(b), toDate(a)) : 0);

export function relDay(d?: string | null) {
  if (!d) return "";
  const x = toDate(d);
  if (isToday(x)) return "Today";
  if (isTomorrow(x)) return "Tomorrow";
  if (isYesterday(x)) return "Yesterday";
  return format(x, "EEE d MMM");
}

export function ago(d?: string | null) {
  if (!d) return "";
  return formatDistanceToNowStrict(toDate(d), { addSuffix: true });
}

export function clock(d?: string | null) {
  if (!d) return "";
  const x = toDate(d);
  return isToday(x) ? format(x, "HH:mm") : format(x, "d MMM");
}

export const plural = (n: number, one: string, many = one + "s") => `${n} ${n === 1 ? one : many}`;

export function hhmm(t?: string | null) {
  if (!t) return "";
  const [h, m] = t.split(":").map(Number);
  const suffix = h < 12 ? "am" : "pm";
  const h12 = h % 12 || 12;
  return `${h12}${m ? ":" + String(m).padStart(2, "0") : ""}${suffix}`;
}

export const STATUS_TONE: Record<string, "neutral" | "brand" | "ocean" | "success" | "warning" | "danger"> = {
  held: "warning", confirmed: "ocean", checked_in: "success", completed: "neutral", cancelled: "danger", expired: "neutral",
  refund_due: "danger", no_show: "danger", open: "warning", in_progress: "ocean", done: "success", acknowledged: "ocean", resolved: "neutral",
  pending: "warning", success: "success", failed: "danger", requested: "warning", declined: "danger", fulfilled: "success",
};

export const CHANNEL_LABEL: Record<string, string> = {
  web: "Website", ussd: "USSD", sms: "SMS", voice: "Voice", whatsapp: "WhatsApp", walk_in: "Walk-in", airbnb: "Airbnb", booking_com: "Booking.com",
};

export const CHANNEL_COLOR: Record<string, string> = {
  web: "#0e8388", ussd: "#b45309", sms: "#e8553e", voice: "#7c3aed", whatsapp: "#16a34a", walk_in: "#6a6a6a", airbnb: "#ff385c", booking_com: "#1e40af",
};
