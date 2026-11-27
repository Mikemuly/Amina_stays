"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { toast } from "sonner";

import { get } from "@/lib/api";
import { fmtShort, toDate } from "@/lib/format";
import { COUNTRIES } from "@/lib/utils";

import type { HostListing, StaffMember } from "./types";

// ---------- a shared clock (one interval for every subscriber) ----------

const listeners = new Set<() => void>();
let timer: ReturnType<typeof setInterval> | undefined;

function subscribe(cb: () => void) {
  listeners.add(cb);
  timer ??= setInterval(() => listeners.forEach((l) => l()), 1000);
  return () => {
    listeners.delete(cb);
    if (!listeners.size && timer) {
      clearInterval(timer);
      timer = undefined;
    }
  };
}

/** Current time in ms, rounded down to `step` so components only re-render when the value they show changes. */
export function useNow(step = 1000) {
  const snapshot = React.useCallback(() => Math.floor(Date.now() / step) * step, [step]);
  return React.useSyncExternalStore(subscribe, snapshot, () => 0);
}

export function useDebounced<T>(value: T, ms = 300) {
  const [debounced, setDebounced] = React.useState(value);
  React.useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

// ---------- Kenya time ----------

const KE = "Africa/Nairobi";
const hourFmt = new Intl.DateTimeFormat("en-GB", { timeZone: KE, hour: "2-digit", hourCycle: "h23" });
const dateFmt = new Intl.DateTimeFormat("en-CA", { timeZone: KE, year: "numeric", month: "2-digit", day: "2-digit" });

export const kenyaHour = (ms: number) => Number(hourFmt.format(ms));
export const kenyaDate = (ms: number) => dateFmt.format(ms);

export function greeting(hour: number) {
  if (hour < 12) return "Habari za asubuhi";
  if (hour < 16) return "Habari za mchana";
  return "Habari za jioni";
}

export function addDaysISO(isoDate: string, n: number) {
  const d = toDate(isoDate);
  d.setDate(d.getDate() + n);
  const p = (x: number) => String(x).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export const daysBetween = (a: string, b: string) => Math.round((toDate(b).getTime() - toDate(a).getTime()) / 86_400_000);

// ---------- relative times ----------

export function relTime(iso: string | null | undefined, now: number) {
  if (!iso || !now) return "";
  const s = Math.max(0, Math.round((now - toDate(iso).getTime()) / 1000));
  if (s < 45) return "just now";
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} h ago`;
  const d = Math.round(h / 24);
  if (d < 7) return `${d} d ago`;
  return fmtShort(iso);
}

/** "12 min", "2 h 5 min", "3 d" — how long something has been waiting. */
export function duration(fromIso: string | null | undefined, now: number) {
  if (!fromIso || !now) return "";
  const m = Math.max(0, Math.floor((now - toDate(fromIso).getTime()) / 60_000));
  if (m < 1) return "under a minute";
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  if (h < 24) return m % 60 ? `${h} h ${m % 60} min` : `${h} h`;
  return `${Math.floor(h / 24)} d`;
}

export const minutesSince = (iso: string | null | undefined, now: number) =>
  iso && now ? Math.max(0, Math.floor((now - toDate(iso).getTime()) / 60_000)) : 0;

/** "due in 3 h" / "2 h overdue" */
export function dueText(iso: string | null | undefined, now: number) {
  if (!iso || !now) return { text: "", overdue: false };
  const diff = toDate(iso).getTime() - now;
  const m = Math.round(Math.abs(diff) / 60_000);
  const span = m < 60 ? `${m} min` : m < 60 * 24 ? `${Math.round(m / 60)} h` : `${Math.round(m / 1440)} d`;
  return diff >= 0 ? { text: `due in ${span}`, overdue: false } : { text: `${span} overdue`, overdue: true };
}

export function countdown(ms: number) {
  if (ms <= 0) return "0:00";
  const total = Math.floor(ms / 1000);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = String(total % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`;
}

// ---------- people & places ----------

export function fmtPhone(p?: string | null) {
  if (!p) return "";
  const ke = p.match(/^\+254(\d{3})(\d{3})(\d{3})$/);
  if (ke) return `+254 ${ke[1]} ${ke[2]} ${ke[3]}`;
  const uk = p.match(/^\+44(\d{4})(\d{6})$/);
  if (uk) return `+44 ${uk[1]} ${uk[2]}`;
  return p;
}

export const displayName = (name?: string | null, phone?: string | null) => name?.trim() || fmtPhone(phone) || "Guest";

export const countryName = (code?: string | null) =>
  code ? (COUNTRIES.find(([c]) => c === code.toUpperCase())?.[1] ?? code.toUpperCase()) : "";

export const LANGUAGES: Record<string, string> = { en: "English", sw: "Kiswahili", it: "Italiano", de: "Deutsch", fr: "Français" };

export const HOUSEKEEPING: Record<string, { label: string; tone: "success" | "warning" | "ocean" | "brand"; dot: string }> = {
  clean: { label: "Clean", tone: "success", dot: "bg-success" },
  dirty: { label: "Needs cleaning", tone: "warning", dot: "bg-warning" },
  cleaning: { label: "Cleaning", tone: "ocean", dot: "bg-ocean-500" },
  inspect: { label: "Needs inspection", tone: "brand", dot: "bg-brand-500" },
};

export const shortStyle = (label: string) => label.split(" (")[0];

/** Rough SMS segment count (GSM-7: 160/153, otherwise UCS-2: 70/67). */
export function smsSegments(text: string) {
  if (!text) return 0;
  const gsm = /^[\x0A\x0D\x20-\x7E£¥èéùìòÇØøÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ¤¡ÄÖÑÜ§¿äöñüà€]*$/.test(text);
  const [single, multi] = gsm ? [160, 153] : [70, 67];
  return text.length <= single ? 1 : Math.ceil(text.length / multi);
}

// ---------- data ----------

export function useListings() {
  return useQuery({
    queryKey: ["host", "ops", "listings"],
    queryFn: () => get<HostListing[]>("/api/host/listings"),
    staleTime: 5 * 60_000,
  });
}

export function useStaff() {
  return useQuery({
    queryKey: ["host", "ops", "staff"],
    queryFn: () => get<StaffMember[]>("/api/host/staff"),
    staleTime: 60_000,
  });
}

/** A host mutation: toast on success/failure and refresh every console query. */
export function useHostAction<TVars = void, TData = unknown>(
  fn: (vars: TVars) => Promise<TData>,
  opts: { success?: string | ((data: TData, vars: TVars) => string); onSuccess?: (data: TData, vars: TVars) => void } = {},
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: async (data, vars) => {
      const msg = typeof opts.success === "function" ? opts.success(data, vars) : opts.success;
      if (msg) toast.success(msg);
      opts.onSuccess?.(data, vars);
      await qc.invalidateQueries({ queryKey: ["host"] });
    },
    onError: (e) => {
      toast.error(e instanceof Error ? e.message : "Something went wrong. Please try again.");
    },
  });
}
