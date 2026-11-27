"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Lock, Trash2 } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { ErrorBlock, PageHeader } from "@/components/host/common";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent } from "@/components/ui/dialog";
import { Field, Input, Select, Textarea } from "@/components/ui/input";
import { Badge, Skeleton, Spinner } from "@/components/ui/misc";
import { Tabs, TabsContent, TabsList, TabsTrigger, Tooltip } from "@/components/ui/overlays";
import { del, get, post, put, qs } from "@/lib/api";
import { fmtDate, fmtRange, kes, plural, toDate } from "@/lib/format";
import { cn } from "@/lib/utils";

import { ChannelIcon, ConfirmAction, HousekeepingDot, Segmented } from "./bits";
import { addDaysISO, daysBetween, useHostAction } from "./lib";
import { NewReservationButton } from "./new-reservation";
import type { CalBlock, CalBooking, CalendarResponse, CalUnit } from "./types";

const DAY_OPTIONS = [14, 21, 31] as const;
const CELL = { 14: 64, 21: 52, 31: 42 } as Record<number, number>;
const HATCH = "repeating-linear-gradient(135deg, var(--color-line-soft) 0 5px, #fff 5px 10px)";

const BAR_TONE: Record<string, string> = {
  held: "border-2 border-dashed border-warning bg-warning-50 text-warning",
  confirmed: "bg-ocean-500 text-white hover:bg-ocean-600",
  checked_in: "bg-success text-white hover:brightness-110",
  completed: "bg-line text-ink-2 hover:bg-[#d2d2d2]",
};

type Selection = { unitId: number; a: number; b: number };

export function CalendarView() {
  const [start, setStart] = React.useState<string | null>(null);
  const [days, setDays] = React.useState<number>(21);
  const q = useQuery({
    queryKey: ["host", "ops", "calendar", start ?? "today", days],
    queryFn: () => get<CalendarResponse>(`/api/host/calendar${qs({ start, days })}`),
    placeholderData: keepPreviousData,
    refetchInterval: 30_000,
  });
  const data = q.data;

  const shift = (n: number) => data && setStart(addDaysISO(data.start, n));

  return (
    <div>
      <PageHeader
        title="Calendar"
        subtitle="Every home, every night — drag across empty nights to block them or change the price."
        actions={<NewReservationButton variant="dark" />}
      />

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className="flex items-center rounded-full border border-line bg-white p-0.5">
            <Button variant="ghost" size="icon-sm" aria-label="Previous two weeks" onClick={() => shift(-14)} disabled={!data}>
              <ChevronLeft className="size-4" />
            </Button>
            <Button variant="ghost" size="sm" className="rounded-full" onClick={() => setStart(null)}>
              Today
            </Button>
            <Button variant="ghost" size="icon-sm" aria-label="Next two weeks" onClick={() => shift(14)} disabled={!data}>
              <ChevronRight className="size-4" />
            </Button>
          </div>
          <p className="text-[15px] font-semibold tabular-nums">
            {data ? `${fmtDate(data.start, "d MMM")} – ${fmtDate(addDaysISO(data.end, -1), "d MMM yyyy")}` : <span className="text-ink-3">Loading…</span>}
          </p>
          {q.isFetching && data && <Spinner className="size-4" />}
        </div>
        <Segmented label="Days shown" value={days} onChange={setDays} options={DAY_OPTIONS.map((d) => ({ value: d, label: `${d} days` }))} />
      </div>

      {q.error && !data ? (
        <ErrorBlock error={q.error} retry={() => q.refetch()} />
      ) : !data ? (
        <Skeleton className="h-[480px] rounded-2xl" />
      ) : (
        <Grid data={data} />
      )}

      <Legend />
    </div>
  );
}

function Legend() {
  const items: [string, React.ReactNode][] = [
    ["Held · awaiting payment", <span key="h" className="h-3 w-6 rounded-full border-2 border-dashed border-warning bg-warning-50" />],
    ["Confirmed", <span key="c" className="h-3 w-6 rounded-full bg-ocean-500" />],
    ["Checked in", <span key="i" className="h-3 w-6 rounded-full bg-success" />],
    ["Completed", <span key="d" className="h-3 w-6 rounded-full bg-line" />],
    ["Blocked / booked elsewhere", <span key="b" className="h-3 w-6 rounded-full border border-line" style={{ background: HATCH }} />],
    ["Custom price", <span key="p" className="text-xs font-bold text-brand-600 tabular-nums">4,500</span>],
  ];
  return (
    <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-[13px] text-ink-2">
      {items.map(([label, swatch]) => (
        <span key={label} className="inline-flex items-center gap-2">
          {swatch}
          {label}
        </span>
      ))}
      <span className="ml-auto text-xs text-ink-3">Nightly prices in KES</span>
    </div>
  );
}

// ---------- the grid ----------

const compactPrice = (p: number) => (p >= 10_000 ? `${Math.round(p / 1000)}k` : `${(p / 1000).toFixed(1).replace(/\.0$/, "")}k`);

function nightsTaken(unit: CalUnit, days: string[]) {
  const taken = new Set<number>();
  const mark = (from: string, to: string) => {
    const a = Math.max(0, daysBetween(days[0], from));
    const b = Math.min(days.length, daysBetween(days[0], to));
    for (let i = a; i < b; i++) taken.add(i);
  };
  unit.bookings.forEach((b) => mark(b.check_in, b.check_out));
  unit.blocks.forEach((b) => mark(b.start_date, b.end_date));
  return taken;
}

function Grid({ data }: { data: CalendarResponse }) {
  const N = data.days.length;
  const cell = CELL[N] ?? (N > 25 ? 42 : 52);
  const compact = cell < 56;
  const template = `var(--label) repeat(${N}, minmax(${cell}px, 1fr))`;
  const taken = React.useMemo(() => new Map(data.units.map((u) => [u.id, nightsTaken(u, data.days)])), [data]);

  const [sel, setSel] = React.useState<Selection | null>(null);
  const selRef = React.useRef<Selection | null>(null);
  const [dragging, setDragging] = React.useState(false);
  const [dialog, setDialog] = React.useState<{ unit: CalUnit; from: string; to: string } | null>(null);

  const openDialog = React.useCallback(
    (s: Selection) => {
      const unit = data.units.find((u) => u.id === s.unitId);
      if (!unit) return;
      const [a, b] = s.a <= s.b ? [s.a, s.b] : [s.b, s.a];
      setDialog({ unit, from: data.days[a], to: data.days[b] });
    },
    [data],
  );

  React.useEffect(() => {
    if (!dragging) return;
    const up = () => {
      setDragging(false);
      if (selRef.current) openDialog(selRef.current);
    };
    const cancel = () => {
      setDragging(false);
      selRef.current = null;
      setSel(null);
    };
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", cancel);
    return () => {
      window.removeEventListener("pointerup", up);
      window.removeEventListener("pointercancel", cancel);
    };
  }, [dragging, openDialog]);

  const extend = (unitId: number, i: number) => {
    if (!dragging || !sel || sel.unitId !== unitId) return;
    const busy = taken.get(unitId)!;
    const step = i >= sel.a ? 1 : -1;
    let b = sel.a;
    while (b !== i && !busy.has(b + step)) b += step;
    selRef.current = { ...sel, b };
    setSel(selRef.current);
  };

  const inSel = (unitId: number, i: number) => sel !== null && sel.unitId === unitId && i >= Math.min(sel.a, sel.b) && i <= Math.max(sel.a, sel.b);

  return (
    <>
      <div className="overflow-x-auto rounded-2xl border border-line-soft bg-white [--label:150px] md:[--label:208px]">
        <div style={{ minWidth: `calc(var(--label) + ${N * cell}px)` }} className="select-none">
          {/* header */}
          <div className="grid border-b border-line-soft" style={{ gridTemplateColumns: template }}>
            <div className="sticky left-0 z-20 flex items-end border-r border-line-soft bg-white px-4 pb-2.5 text-xs font-semibold text-ink-2">
              {plural(data.units.length, "home")}
            </div>
            {data.days.map((d, i) => {
              const date = toDate(d);
              const weekend = date.getDay() === 0 || date.getDay() === 6;
              const isToday = d === data.today;
              const monthStart = i === 0 || date.getDate() === 1;
              return (
                <div key={d} className={cn("flex flex-col items-center py-2", weekend && "bg-surface/70", isToday && "bg-brand-50/60")}>
                  <span className={cn("text-[10px] font-bold tracking-wider uppercase", monthStart ? "text-brand-600" : "text-ink-3")}>
                    {monthStart ? fmtDate(d, "MMM") : fmtDate(d, "EEE")}
                  </span>
                  <span
                    className={cn(
                      "mt-1 grid size-7 place-items-center rounded-full text-[13px] font-semibold tabular-nums",
                      isToday ? "bg-ink text-white" : weekend ? "text-ink" : "text-ink-2",
                    )}
                    aria-label={fmtDate(d, "EEEE d MMMM")}
                  >
                    {date.getDate()}
                  </span>
                </div>
              );
            })}
          </div>

          {/* one row per home */}
          {data.units.map((u) => {
            const busy = taken.get(u.id)!;
            return (
              <div key={u.id} className="grid border-b border-line-soft last:border-b-0" style={{ gridTemplateColumns: template }}>
                <UnitLabel unit={u} />
                <div className="relative" style={{ gridColumn: `2 / span ${N}` }}>
                  <div className="grid h-[72px]" style={{ gridTemplateColumns: `repeat(${N}, minmax(0, 1fr))` }}>
                    {data.days.map((d, i) => {
                      const date = toDate(d);
                      const weekend = date.getDay() === 0 || date.getDay() === 6;
                      const isToday = d === data.today;
                      const base = cn(
                        "relative border-r border-line-soft/70 last:border-r-0",
                        weekend && "bg-surface/50",
                        isToday && "bg-brand-50/40",
                      );
                      if (busy.has(i)) return <div key={d} className={base} />;
                      const price = u.prices[d];
                      const custom = u.overrides.includes(d);
                      const label = `${u.name}, night of ${fmtDate(d, "EEE d MMM")}${price ? `, ${kes(price)}` : ""}${custom ? " (custom price)" : ""}`;
                      return (
                        <button
                          key={d}
                          type="button"
                          aria-label={label}
                          title={custom ? "Custom price" : undefined}
                          className={cn(base, "cursor-pointer transition-colors outline-none hover:bg-surface focus-visible:bg-surface focus-visible:ring-2 focus-visible:ring-ink focus-visible:ring-inset", inSel(u.id, i) && "bg-ink/10 hover:bg-ink/10")}
                          onPointerDown={(e) => {
                            if (e.button !== 0) return;
                            e.preventDefault();
                            selRef.current = { unitId: u.id, a: i, b: i };
                            setSel(selRef.current);
                            setDragging(true);
                          }}
                          onPointerEnter={() => extend(u.id, i)}
                          onClick={(e) => {
                            if (e.detail === 0) openDialog({ unitId: u.id, a: i, b: i });
                          }}
                        >
                          {price !== undefined && (
                            <span className={cn("absolute right-1.5 bottom-1.5 text-[11px] tabular-nums", custom ? "font-bold text-brand-600" : "text-ink-3")}>
                              {compact ? compactPrice(price) : price.toLocaleString("en-KE")}
                            </span>
                          )}
                        </button>
                      );
                    })}
                  </div>
                  {u.blocks.map((b) => (
                    <BlockBar key={`b${b.id}`} block={b} unit={u} days={data.days} />
                  ))}
                  {u.bookings.map((b) => (
                    <BookingBar key={b.ref} booking={b} days={data.days} />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {dialog && (
        <RangeDialog
          key={`${dialog.unit.id}-${dialog.from}-${dialog.to}`}
          unit={dialog.unit}
          from={dialog.from}
          to={dialog.to}
          days={data.days}
          onClose={() => {
            setDialog(null);
            selRef.current = null;
            setSel(null);
          }}
        />
      )}
    </>
  );
}

function UnitLabel({ unit: u }: { unit: CalUnit }) {
  return (
    <div className="sticky left-0 z-20 flex items-center gap-3 border-r border-line-soft bg-white px-3 md:px-4">
      {u.cover ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={u.cover} alt="" className="hidden size-11 shrink-0 rounded-lg object-cover md:block" />
      ) : (
        <span className="hidden size-11 shrink-0 rounded-lg bg-surface md:block" />
      )}
      <div className="min-w-0">
        <p className="truncate text-[13px] font-semibold md:text-sm">{u.name}</p>
        <p className="mt-0.5 flex items-center gap-1.5 text-xs text-ink-2">
          <HousekeepingDot status={u.housekeeping} />
          <span className="truncate">{u.area}</span>
          {u.status === "paused" && <Badge className="px-1.5 py-0 text-[10px]">Paused</Badge>}
        </p>
      </div>
    </div>
  );
}

/** Where a stay sits on the strip: from the middle of the check-in day to the middle of the check-out day. */
function barGeometry(from: string, to: string, days: string[]) {
  const N = days.length;
  const i = daysBetween(days[0], from);
  const j = daysBetween(days[0], to);
  const left = (i + 0.5) / N;
  const right = (j + 0.5) / N;
  if (right <= 0 || left >= 1) return null;
  const clipL = left < 0;
  const clipR = right > 1;
  const l = Math.max(0, left);
  const r = Math.min(1, right);
  const inset = (clipL ? 0 : 2) + (clipR ? 0 : 2);
  return {
    style: { left: `calc(${l * 100}% + ${clipL ? 0 : 2}px)`, width: `calc(${(r - l) * 100}% - ${inset}px)` },
    rounded: cn("rounded-full", clipL && "rounded-l-none", clipR && "rounded-r-none"),
    cells: (r - l) * N,
  };
}

function BookingBar({ booking: b, days }: { booking: CalBooking; days: string[] }) {
  const g = barGeometry(b.check_in, b.check_out, days);
  if (!g) return null;
  const tone = BAR_TONE[b.status] ?? BAR_TONE.confirmed;
  const tip = (
    <span className="block">
      <span className="block font-bold">
        {b.guest} · {b.ref}
      </span>
      <span className="block text-white/80">
        {fmtRange(b.check_in, b.check_out)} · {plural(b.nights, "night")} · {kes(b.total)}
      </span>
      <span className="block text-white/80">
        {b.status === "held" ? "Held — awaiting payment" : b.status.replace("_", " ")}
        {b.balance_due > 0 && b.status !== "completed" ? ` · ${kes(b.balance_due)} due` : ""}
      </span>
    </span>
  );
  return (
    <Tooltip content={tip}>
      <Link
        href={`/host/reservations/${b.ref}`}
        aria-label={`${b.ref}: ${b.guest}, ${fmtRange(b.check_in, b.check_out)}`}
        className={cn("absolute top-2 z-10 flex h-9 items-center gap-1.5 overflow-hidden px-2.5 text-[12.5px] font-semibold shadow-sm transition", tone, g.rounded)}
        style={g.style}
        onPointerDown={(e) => e.stopPropagation()}
      >
        {g.cells >= 1.2 && <ChannelIcon channel={b.channel} className="size-3.5 shrink-0 opacity-80" />}
        <span className="truncate">{b.guest}</span>
        {g.cells >= 3.5 && <span className="shrink-0 font-medium opacity-75">· {plural(b.nights, "night")}</span>}
        {b.balance_due > 0 && b.status !== "completed" && g.cells >= 2.5 && (
          <span className="ml-auto size-1.5 shrink-0 rounded-full bg-current opacity-90" aria-label="Balance due" />
        )}
      </Link>
    </Tooltip>
  );
}

function blockLabel(b: CalBlock) {
  if (b.external) return b.source || b.note.split(":")[0] || "Booked elsewhere";
  return b.reason_label;
}

function BlockBar({ block: b, unit, days }: { block: CalBlock; unit: CalUnit; days: string[] }) {
  const g = barGeometry(b.start_date, b.end_date, days);
  if (!g) return null;
  const label = blockLabel(b);
  const cls = cn(
    "absolute top-2 z-10 flex h-9 items-center gap-1.5 overflow-hidden border border-line px-2.5 text-[12.5px] font-semibold text-ink-2",
    g.rounded,
  );
  const content = (
    <>
      {g.cells >= 2.5 && (b.external ? <Lock className="size-3.5 shrink-0" /> : <Trash2 className="size-3.5 shrink-0 opacity-60" />)}
      <span className="truncate">{label}</span>
      {b.note && !b.external && g.cells >= 3 && <span className="truncate font-medium opacity-75">· {b.note}</span>}
    </>
  );
  if (b.external) {
    return (
      <Tooltip content={`${b.note || label} — synced by iCal. Manage it on the other platform.`}>
        <span className={cn(cls, "cursor-default")} style={{ ...g.style, background: HATCH }} onPointerDown={(e) => e.stopPropagation()}>
          {content}
        </span>
      </Tooltip>
    );
  }
  return (
    <ConfirmAction
      title="Remove this block?"
      confirmLabel="Remove block"
      tone="danger"
      success={`${unit.name} is bookable again for those nights`}
      run={() => del(`/api/host/blocks/${b.id}`)}
      trigger={(open) => (
        <button
          type="button"
          className={cn(cls, "cursor-pointer hover:border-ink-3")}
          style={{ ...g.style, background: HATCH }}
          onPointerDown={(e) => e.stopPropagation()}
          onClick={open}
          aria-label={`${label} block on ${unit.name}, ${fmtRange(b.start_date, b.end_date)}. Remove`}
        >
          {content}
        </button>
      )}
    >
      {unit.name} · {fmtDate(b.start_date)} → {fmtDate(b.end_date)} ({plural(daysBetween(b.start_date, b.end_date), "night")}, {label.toLowerCase()}
      {b.note ? `: ${b.note}` : ""}). Those nights open up for booking on every channel straight away.
    </ConfirmAction>
  );
}

// ---------- block dates / set price ----------

function RangeDialog({ unit, from, to, days, onClose }: { unit: CalUnit; from: string; to: string; days: string[]; onClose: () => void }) {
  const [tab, setTab] = React.useState("block");
  const [first, setFirst] = React.useState(from);
  const [last, setLast] = React.useState(to);
  const [reason, setReason] = React.useState("owner");
  const [note, setNote] = React.useState("");
  const [price, setPrice] = React.useState("");

  const valid = Boolean(first && last && last >= first);
  const end = valid ? addDaysISO(last, 1) : "";
  const nights = valid ? daysBetween(first, end) : 0;
  const clash = valid
    ? [...unit.bookings.map((b) => [b.check_in, b.check_out]), ...unit.blocks.map((b) => [b.start_date, b.end_date])].some(([a, b]) => a < end && b > first)
    : false;
  const visible = days.filter((d) => d >= first && d < end);
  const prices = visible.map((d) => unit.prices[d]).filter((p): p is number => p !== undefined);
  const lo = prices.length ? Math.min(...prices) : null;
  const hi = prices.length ? Math.max(...prices) : null;
  const customCount = visible.filter((d) => unit.overrides.includes(d)).length;

  const block = useHostAction(() => post("/api/host/blocks", { unit: unit.id, start_date: first, end_date: end, reason, note: note.trim() }), {
    success: `${unit.name} blocked for ${plural(nights, "night")}`,
    onSuccess: onClose,
  });
  const setPrices = useHostAction(
    () => put("/api/host/prices", { unit: unit.id, start: first, end, price: price.trim() === "" ? null : Number(price) }),
    {
      success: price.trim() === "" ? `Prices back to automatic for ${plural(nights, "night")}` : `${kes(Number(price))} a night set for ${plural(nights, "night")}`,
      onSuccess: onClose,
    },
  );

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent
        size="sm"
        title={unit.name}
        description="Block dates or set a nightly price"
        footer={
          <div className="flex justify-end gap-2">
            <DialogClose asChild>
              <Button variant="ghost">Cancel</Button>
            </DialogClose>
            {tab === "block" ? (
              <Button variant="dark" loading={block.isPending} disabled={!valid || clash} onClick={() => block.mutate()}>
                Block {nights ? plural(nights, "night") : "dates"}
              </Button>
            ) : (
              <Button
                variant="dark"
                loading={setPrices.isPending}
                disabled={!valid || (price.trim() !== "" && !(Number(price) > 0))}
                onClick={() => setPrices.mutate()}
              >
                {price.trim() === "" ? "Reset to automatic" : "Save price"}
              </Button>
            )}
          </div>
        }
      >
        <div className="px-6 pt-5 pb-6">
          <div className="grid grid-cols-2 gap-3">
            <Field label="First night">
              <Input type="date" value={first} onChange={(e) => setFirst(e.target.value)} />
            </Field>
            <Field label="Last night">
              <Input type="date" value={last} min={first} onChange={(e) => setLast(e.target.value)} />
            </Field>
          </div>
          <p className={cn("mt-2 text-[13px]", valid ? "text-ink-2" : "text-danger")}>
            {valid ? (
              <>
                {plural(nights, "night")} · free again on the morning of {fmtDate(end)}
              </>
            ) : (
              "The last night can't be before the first."
            )}
          </p>

          <Tabs value={tab} onValueChange={setTab} className="mt-5">
            <TabsList>
              <TabsTrigger value="block">Block dates</TabsTrigger>
              <TabsTrigger value="price">Set nightly price</TabsTrigger>
            </TabsList>
            <TabsContent value="block" className="space-y-4 pt-5 outline-none">
              <Field label="Reason">
                <Select value={reason} onChange={(e) => setReason(e.target.value)}>
                  <option value="owner">Owner use</option>
                  <option value="maintenance">Maintenance</option>
                  <option value="other">Other</option>
                </Select>
              </Field>
              <Field label="Note" hint="Only you and your team see this.">
                <Textarea className="min-h-20" maxLength={160} placeholder="e.g. Repainting the balcony" value={note} onChange={(e) => setNote(e.target.value)} />
              </Field>
              {clash && (
                <p className="rounded-xl bg-warning-50 px-4 py-3 text-[13px] font-medium text-warning">
                  Some of these nights are already booked or blocked. Pick only free nights to block.
                </p>
              )}
            </TabsContent>
            <TabsContent value="price" className="space-y-4 pt-5 outline-none">
              <Field
                label="Nightly price (KES)"
                hint={
                  lo !== null
                    ? `Currently ${lo === hi ? kes(lo) : `${kes(lo)} – ${kes(hi)}`}${customCount ? ` · ${customCount} custom` : ""}. Leave empty to go back to automatic pricing.`
                    : "Leave empty to go back to automatic pricing."
                }
              >
                <Input type="number" inputMode="numeric" min={0} step={100} placeholder={String(unit.base_price)} value={price} onChange={(e) => setPrice(e.target.value)} />
              </Field>
              {clash && <p className="text-[13px] text-ink-2">Existing bookings keep the price they were booked at.</p>}
            </TabsContent>
          </Tabs>
        </div>
      </DialogContent>
    </Dialog>
  );
}
