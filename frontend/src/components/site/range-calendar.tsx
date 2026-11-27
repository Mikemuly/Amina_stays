"use client";

import {
  addDays, addMonths, eachDayOfInterval, endOfMonth, endOfWeek, format, isBefore, isSameMonth, startOfMonth, startOfToday, startOfWeek,
} from "date-fns";
import { ChevronLeft, ChevronRight } from "lucide-react";
import * as React from "react";

import { iso, toDate } from "@/lib/format";
import { cn } from "@/lib/utils";

export type Range = { from?: string; to?: string };

/**
 * Two-month range picker (check-in → check-out), modelled on the best booking calendars:
 * nights that are taken are struck through, a taken night can still be a check-out day,
 * and the selection can't cross a taken night or break the minimum stay.
 */
export function RangeCalendar({
  value, onChange, unavailable, prices, minNights = 1, months = 2, className,
}: {
  value: Range;
  onChange: (r: Range) => void;
  unavailable?: Set<string>;
  prices?: Record<string, number>;
  minNights?: number;
  months?: 1 | 2;
  className?: string;
}) {
  const today = startOfToday();
  const [cursor, setCursor] = React.useState(() => startOfMonth(value.from ? toDate(value.from) : today));
  const [hover, setHover] = React.useState<string | null>(null);
  const blocked = React.useMemo(() => unavailable ?? new Set<string>(), [unavailable]);

  const firstBlockedAfter = React.useMemo(() => {
    if (!value.from || value.to) return null;
    let d = toDate(value.from);
    for (let i = 0; i < 400; i++) {
      if (blocked.has(iso(d))) return iso(d);
      d = addDays(d, 1);
    }
    return null;
  }, [value.from, value.to, blocked]);

  function state(day: Date) {
    const key = iso(day);
    const past = isBefore(day, today);
    const nightTaken = blocked.has(key);
    const selectingOut = !!value.from && !value.to;
    let disabled = past;
    if (selectingOut) {
      const from = value.from!;
      if (key <= from) disabled = past || nightTaken; // picking again resets check-in
      else if (firstBlockedAfter && key > firstBlockedAfter) disabled = true;
      else {
        const n = (toDate(key).getTime() - toDate(from).getTime()) / 86400000;
        if (n < minNights) disabled = true;
      }
    } else if (nightTaken) {
      disabled = true;
    }
    const end = value.to ?? (selectingOut ? hover : null);
    const inRange = !!value.from && !!end && key > value.from && key < end;
    return { key, past, nightTaken, disabled, isStart: key === value.from, isEnd: key === value.to, inRange, checkoutOnly: selectingOut && nightTaken && !disabled };
  }

  function pick(day: Date) {
    const key = iso(day);
    if (!value.from || value.to || key <= value.from) {
      if (blocked.has(key)) return;
      onChange({ from: key, to: undefined });
    } else {
      onChange({ from: value.from, to: key });
    }
  }

  return (
    <div className={cn("relative select-none", className)}>
      <button
        type="button"
        aria-label="Previous month"
        disabled={!isBefore(today, cursor)}
        onClick={() => setCursor(addMonths(cursor, -1))}
        className="absolute top-0 left-0 z-10 grid size-8 place-items-center rounded-full hover:bg-surface disabled:opacity-20"
      >
        <ChevronLeft className="size-4" />
      </button>
      <button
        type="button"
        aria-label="Next month"
        onClick={() => setCursor(addMonths(cursor, 1))}
        className="absolute top-0 right-0 z-10 grid size-8 place-items-center rounded-full hover:bg-surface"
      >
        <ChevronRight className="size-4" />
      </button>
      <div className="flex items-start gap-8">
        {Array.from({ length: months }).map((_, m) => {
          const month = addMonths(cursor, m);
          const days = eachDayOfInterval({ start: startOfWeek(startOfMonth(month), { weekStartsOn: 1 }), end: endOfWeek(endOfMonth(month), { weekStartsOn: 1 }) });
          return (
            <div key={m} className={cn("w-full min-w-[280px] flex-1", m === 1 && "hidden md:block")}>
              <div className="mb-4 flex h-8 items-center justify-center">
                <span className="text-base font-semibold">{format(month, "MMMM yyyy")}</span>
              </div>
              <div className="grid grid-cols-7 text-center text-xs font-medium text-ink-2">
                {["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"].map((d) => (
                  <div key={d} className="pb-2">{d}</div>
                ))}
              </div>
              <div className="grid grid-cols-7" onMouseLeave={() => setHover(null)}>
                {days.map((day) => {
                  if (!isSameMonth(day, month)) return <div key={day.toISOString()} className="h-12" />;
                  const s = state(day);
                  const price = prices?.[s.key];
                  return (
                    <div
                      key={s.key}
                      className={cn(
                        "relative h-12",
                        s.inRange && "bg-surface",
                        s.isStart && (value.to || hover) && "bg-gradient-to-r from-transparent from-50% to-surface to-50%",
                        s.isEnd && "bg-gradient-to-l from-transparent from-50% to-surface to-50%",
                      )}
                    >
                      <button
                        type="button"
                        disabled={s.disabled}
                        onClick={() => pick(day)}
                        onMouseEnter={() => setHover(s.key)}
                        aria-label={`${format(day, "EEEE d MMMM")}${s.nightTaken ? " (unavailable)" : ""}`}
                        aria-pressed={s.isStart || s.isEnd}
                        className={cn(
                          "absolute inset-0 m-auto flex size-12 flex-col items-center justify-center rounded-full text-sm font-medium transition-colors",
                          !s.disabled && "hover:ring-1 hover:ring-ink",
                          s.disabled && "cursor-default text-ink-disabled",
                          s.nightTaken && !s.checkoutOnly && "line-through decoration-ink-disabled",
                          (s.isStart || s.isEnd) && "bg-ink text-white hover:ring-0",
                        )}
                      >
                        <span>{format(day, "d")}</span>
                        {price && !s.disabled && !s.nightTaken && !(s.isStart || s.isEnd) && (
                          <span className="-mt-0.5 text-[9px] font-medium text-ink-2">{price >= 1000 ? `${Math.round(price / 100) / 10}k` : price}</span>
                        )}
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
