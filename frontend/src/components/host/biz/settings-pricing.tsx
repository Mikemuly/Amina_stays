"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { format, parseISO } from "date-fns";
import { CalendarDays, CalendarRange, Pencil, Plus, Timer, Trash2, TrendingUp, type LucideIcon } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { ErrorBlock, LoadingBlock } from "@/components/host/common";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Input, Select } from "@/components/ui/input";
import { Badge, EmptyState } from "@/components/ui/misc";
import { Switch } from "@/components/ui/overlays";
import { del, get, patch, post } from "@/lib/api";
import { cn } from "@/lib/utils";

import { useInvalidateHost, useListings } from "./queries";
import type { AdjustType, PriceRule, RuleKind } from "./types";
import { Callout, ConfirmDialog, Field, IconButton, NumberInput, Segmented, compactKes, errorMessage, fieldErrors } from "./ui";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const KINDS: { value: RuleKind; label: string; icon: LucideIcon; text: string }[] = [
  { value: "season", label: "Season / event", icon: CalendarRange, text: "Festive season, Easter, August peak, Mombasa Carnival…" },
  { value: "weekday", label: "Days of the week", icon: CalendarDays, text: "e.g. Friday and Saturday nights" },
  { value: "last_minute", label: "Last-minute", icon: Timer, text: "Fill empty nights close to arrival" },
  { value: "early_bird", label: "Early bird", icon: TrendingUp, text: "Reward guests who book well ahead" },
];

type Draft = Omit<PriceRule, "id" | "unit_name" | "value"> & { value: number | null };

const n = (v: string | number | null) => (v === null || v === "" ? 0 : Number(v));
const signed = (v: number, unit = "") => `${v > 0 ? "+" : v < 0 ? "−" : ""}${unit}${Math.abs(v).toLocaleString("en-KE")}`;

function dateRange(start: string | null, end: string | null) {
  const thisYear = new Date().getFullYear();
  if (start && end) {
    const s = parseISO(start);
    const e = parseISO(end);
    return `${format(s, "d MMM")} – ${format(e, "d MMM")}${s.getFullYear() !== thisYear ? ` ${format(e, "yyyy")}` : ""}`;
  }
  if (start) return `from ${format(parseISO(start), "d MMM yyyy")}`;
  if (end) return `until ${format(parseISO(end), "d MMM yyyy")}`;
  return "";
}

function dayList(days: number[]) {
  const names = [...days].sort((a, b) => a - b).map((d) => DAYS[d]);
  if (names.length === 7) return "every night";
  return `${names.length > 1 ? `${names.slice(0, -1).join(", ")} & ${names[names.length - 1]}` : names[0]} nights`;
}

export function ruleSentence(r: Pick<Draft, "kind" | "adjust_type" | "start_date" | "end_date" | "weekdays" | "days_before" | "unit"> & { value: number | string | null }, unitName?: string) {
  const v = n(r.value);
  const amount = r.adjust_type === "percent" ? `${signed(v)}%` : r.adjust_type === "amount" ? `${signed(v, "KES ")} a night` : `KES ${v.toLocaleString("en-KE")} a night`;
  const who = r.unit ? (unitName ?? "one home") : "all homes";
  const parts: string[] = [];
  if (r.kind === "season" || r.kind === "weekday") {
    if (r.weekdays.length) parts.push(dayList(r.weekdays));
    const range = dateRange(r.start_date, r.end_date);
    if (range) parts.push(range);
    if (!parts.length) parts.push(r.kind === "weekday" ? "pick the nights" : "all year");
  } else if (r.kind === "last_minute") parts.push(`booked within ${r.days_before ?? "?"} days of arrival`);
  else parts.push(`booked ${r.days_before ?? "?"}+ days ahead`);
  return `${amount} ${r.adjust_type === "fixed" ? "for" : "on"} ${who}, ${parts.join(", ")}`;
}

function example(r: Pick<Draft, "adjust_type"> & { value: number | null }) {
  const base = 10_000;
  const v = n(r.value);
  const out = r.adjust_type === "percent" ? base * (1 + v / 100) : r.adjust_type === "amount" ? base + v : v;
  return `A KES 10,000 night becomes KES ${Math.max(0, Math.round(out)).toLocaleString("en-KE")}`;
}

export function PricingRulesTab() {
  const invalidate = useInvalidateHost();
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ["host", "price-rules"], queryFn: () => get<PriceRule[]>("/api/host/price-rules") });
  const { data: listings } = useListings();
  const [editing, setEditing] = React.useState<PriceRule | "new" | null>(null);
  const [removing, setRemoving] = React.useState<PriceRule | null>(null);

  const toggle = useMutation({
    mutationFn: (r: PriceRule) => patch<PriceRule>(`/api/host/price-rules/${r.id}`, { active: !r.active }),
    onSuccess: (r) => {
      toast.success(r.active ? `${r.name} is live` : `${r.name} paused`);
      invalidate();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const remove = useMutation({
    mutationFn: (r: PriceRule) => del(`/api/host/price-rules/${r.id}`),
    onSuccess: () => {
      toast.success("Rule deleted");
      setRemoving(null);
      invalidate();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  if (error) return <ErrorBlock error={error} retry={refetch} />;
  if (isLoading || !data) return <LoadingBlock rows={5} />;

  const unitName = (id: number | null) => (id ? listings?.find((l) => l.id === id)?.name : undefined);
  const rules = [...data].sort((a, b) => a.priority - b.priority || a.id - b.id);
  const groups: { title: string; kinds: RuleKind[] }[] = [
    { title: "Seasons & events", kinds: ["season"] },
    { title: "Days of the week", kinds: ["weekday"] },
    { title: "Last-minute & early bird", kinds: ["last_minute", "early_bird"] },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="grid max-w-3xl gap-3 sm:grid-cols-2">
          <Callout tone="info" title="How rules stack">
            Season and weekday rules adjust each night in priority order — higher numbers apply last, and a fixed price wins. Calendar overrides beat every rule.
          </Callout>
          <Callout tone="neutral" title="Discounts don't stack">
            Last-minute and early-bird rules are a % off the whole stay (use a negative value). If several match, the guest gets the best one.
          </Callout>
        </div>
        <Button variant="dark" onClick={() => setEditing("new")}>
          <Plus className="size-4" /> New rule
        </Button>
      </div>

      {rules.length === 0 ? (
        <EmptyState icon={<CalendarRange className="size-5" />} title="No pricing rules yet" action={<Button onClick={() => setEditing("new")}>Add a season</Button>}>
          The coast has strong seasons — festive, Easter and August usually carry 15–35% more.
        </EmptyState>
      ) : (
        groups.map((g) => {
          const items = rules.filter((r) => g.kinds.includes(r.kind));
          if (!items.length) return null;
          return (
            <section key={g.title}>
              <h2 className="mb-2.5 text-[12px] font-bold tracking-wider text-ink-2 uppercase">{g.title}</h2>
              <ul className="overflow-hidden rounded-2xl border border-line-soft bg-white">
                {items.map((r) => {
                  const v = Number(r.value);
                  const up = r.adjust_type === "fixed" ? null : v > 0;
                  return (
                    <li key={r.id} className={cn("flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-line-soft px-5 py-4 last:border-b-0", !r.active && "opacity-55")}>
                      <span
                        className={cn(
                          "grid h-10 min-w-16 shrink-0 place-items-center rounded-xl px-2 text-[14px] font-bold tabular-nums",
                          up === null ? "bg-surface text-ink" : up ? "bg-brand-50 text-brand-700" : "bg-success-50 text-success",
                        )}
                      >
                        {r.adjust_type === "percent" ? `${signed(v)}%` : r.adjust_type === "amount" ? signed(v) : compactKes(v)}
                      </span>
                      <div className="min-w-0 flex-1 basis-64">
                        <p className="flex flex-wrap items-center gap-2 text-[15px] font-semibold">
                          {r.name}
                          {r.unit && <Badge tone="ocean">{r.unit_name}</Badge>}
                        </p>
                        <p className="text-[13.5px] text-ink-2">{ruleSentence({ ...r, value: r.value }, unitName(r.unit) ?? r.unit_name)}</p>
                      </div>
                      <span className="text-[12px] text-ink-3 tabular-nums">Priority {r.priority}</span>
                      <Switch checked={r.active} onCheckedChange={() => toggle.mutate(r)} aria-label={`${r.name} active`} />
                      <div className="flex">
                        <IconButton label="Edit rule" onClick={() => setEditing(r)}>
                          <Pencil />
                        </IconButton>
                        <IconButton label="Delete rule" tone="danger" onClick={() => setRemoving(r)}>
                          <Trash2 />
                        </IconButton>
                      </div>
                    </li>
                  );
                })}
              </ul>
            </section>
          );
        })
      )}

      <Dialog open={editing !== null} onOpenChange={(v) => !v && setEditing(null)}>
        {editing !== null && <RuleEditor rule={editing === "new" ? null : editing} onDone={() => setEditing(null)} />}
      </Dialog>

      <ConfirmDialog
        open={!!removing}
        onOpenChange={(v) => !v && setRemoving(null)}
        title={`Delete “${removing?.name ?? "rule"}”?`}
        confirmLabel="Delete rule"
        tone="danger"
        loading={remove.isPending}
        onConfirm={() => removing && remove.mutate(removing)}
      >
        New quotes stop using it straight away. Existing bookings keep the price they were quoted.
      </ConfirmDialog>
    </div>
  );
}

function RuleEditor({ rule, onDone }: { rule: PriceRule | null; onDone: () => void }) {
  const invalidate = useInvalidateHost();
  const { data: listings } = useListings();
  const [d, setD] = React.useState<Draft>(() =>
    rule
      ? {
          unit: rule.unit, name: rule.name, kind: rule.kind, start_date: rule.start_date, end_date: rule.end_date, weekdays: rule.weekdays,
          days_before: rule.days_before, adjust_type: rule.adjust_type, value: Number(rule.value), priority: rule.priority, active: rule.active,
        }
      : { unit: null, name: "", kind: "season", start_date: null, end_date: null, weekdays: [], days_before: null, adjust_type: "percent", value: 20, priority: 10, active: true },
  );
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [saving, setSaving] = React.useState(false);
  const stay = d.kind === "last_minute" || d.kind === "early_bird";
  const discountOnly = stay && (d.adjust_type !== "percent" || (d.value ?? 0) >= 0);
  const unitName = d.unit ? listings?.find((l) => l.id === d.unit)?.name : undefined;

  const setKind = (kind: RuleKind) =>
    setD((x) => ({
      ...x,
      kind,
      ...(kind === "last_minute" || kind === "early_bird"
        ? { adjust_type: "percent" as AdjustType, value: x.value && x.value < 0 ? x.value : kind === "last_minute" ? -15 : -5, days_before: x.days_before ?? (kind === "last_minute" ? 3 : 90), weekdays: [], start_date: null, end_date: null }
        : { days_before: null, weekdays: kind === "weekday" && !x.weekdays.length ? [4, 5] : x.weekdays }),
    }));

  const save = async () => {
    setSaving(true);
    setErrors({});
    const body = { ...d, start_date: d.start_date || null, end_date: d.end_date || null };
    try {
      if (rule) await patch(`/api/host/price-rules/${rule.id}`, body);
      else await post("/api/host/price-rules", body);
      toast.success(rule ? "Rule updated" : "Rule added", { description: "New quotes on every channel use it straight away." });
      invalidate();
      onDone();
    } catch (e) {
      setErrors(fieldErrors(e));
      toast.error(errorMessage(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <DialogContent
      title={rule ? "Edit pricing rule" : "New pricing rule"}
      size="lg"
      footer={
        <div className="flex items-center justify-between gap-3">
          <label className="flex items-center gap-2.5 text-[14px] font-medium">
            <Switch checked={d.active} onCheckedChange={(v) => setD({ ...d, active: v })} aria-label="Active" /> Active
          </label>
          <Button variant="dark" onClick={save} loading={saving} disabled={!d.name.trim() || d.value === null || discountOnly}>
            {rule ? "Save rule" : "Add rule"}
          </Button>
        </div>
      }
    >
      <div className="space-y-5 px-6 py-5">
        <div className="rounded-xl bg-ink px-4 py-3.5 text-white">
          <p className="text-[11px] font-bold tracking-wider text-white/60 uppercase">Preview</p>
          <p className="mt-0.5 text-[15px] font-semibold">{ruleSentence(d, unitName)}</p>
          {!stay && d.value !== null && <p className="mt-0.5 text-[12.5px] text-white/70">{example(d)}</p>}
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Name" error={errors.name}>
            <Input value={d.name} onChange={(e) => setD({ ...d, name: e.target.value })} placeholder="Festive season" maxLength={60} />
          </Field>
          <Field label="Applies to" error={errors.unit}>
            <Select value={d.unit ?? ""} onChange={(e) => setD({ ...d, unit: e.target.value ? Number(e.target.value) : null })}>
              <option value="">All homes</option>
              {(listings ?? []).map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        <div>
          <p className="mb-2 text-[13px] font-semibold">Type</p>
          <div role="radiogroup" aria-label="Rule type" className="grid gap-2 sm:grid-cols-2">
            {KINDS.map((k) => (
              <button
                key={k.value}
                type="button"
                role="radio"
                aria-checked={d.kind === k.value}
                onClick={() => setKind(k.value)}
                className={cn("flex items-start gap-3 rounded-xl border px-3.5 py-3 text-left transition", d.kind === k.value ? "border-ink ring-1 ring-ink" : "border-line-soft hover:border-ink-3")}
              >
                <k.icon className="mt-0.5 size-[18px] shrink-0" />
                <span>
                  <span className="block text-[14px] font-semibold">{k.label}</span>
                  <span className="block text-[12.5px] text-ink-2">{k.text}</span>
                </span>
              </button>
            ))}
          </div>
        </div>

        {!stay ? (
          <>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="From" error={errors.start_date} hint={d.kind === "weekday" ? "Optional" : undefined}>
                <Input type="date" value={d.start_date ?? ""} onChange={(e) => setD({ ...d, start_date: e.target.value || null })} />
              </Field>
              <Field label="Until (inclusive)" error={errors.end_date} hint={d.kind === "weekday" ? "Optional" : undefined}>
                <Input type="date" value={d.end_date ?? ""} min={d.start_date ?? undefined} onChange={(e) => setD({ ...d, end_date: e.target.value || null })} />
              </Field>
            </div>
            <div>
              <p className="mb-2 text-[13px] font-semibold">{d.kind === "weekday" ? "Which nights" : "Only on these nights (optional)"}</p>
              <div className="flex flex-wrap gap-1.5">
                {DAYS.map((day, i) => {
                  const on = d.weekdays.includes(i);
                  return (
                    <button
                      key={day}
                      type="button"
                      aria-pressed={on}
                      onClick={() => setD({ ...d, weekdays: on ? d.weekdays.filter((x) => x !== i) : [...d.weekdays, i].sort((a, b) => a - b) })}
                      className={cn("h-9 w-12 rounded-lg border text-[13px] font-semibold transition", on ? "border-ink bg-ink text-white" : "border-line text-ink-2 hover:border-ink-3")}
                    >
                      {day}
                    </button>
                  );
                })}
              </div>
              {errors.weekdays && <p className="mt-1.5 text-[13px] text-danger">{errors.weekdays}</p>}
            </div>
          </>
        ) : (
          <Field
            label={d.kind === "last_minute" ? "Booked within" : "Booked at least"}
            error={errors.days_before}
            hint={d.kind === "last_minute" ? "Days before arrival — e.g. 3 fills this weekend's gaps." : "Days ahead — e.g. 90 for the festive season."}
            className="max-w-xs"
          >
            <NumberInput after="days" value={d.days_before} onValueChange={(v) => setD({ ...d, days_before: v })} />
          </Field>
        )}

        <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_140px]">
          <Field label="Adjustment" error={errors.adjust_type}>
            <Segmented<AdjustType>
              label="Adjustment type"
              className="flex w-full"
              value={d.adjust_type}
              onChange={(v) => setD({ ...d, adjust_type: v })}
              options={[
                { value: "percent", label: "%" },
                { value: "amount", label: "± KES" },
                { value: "fixed", label: "Fixed price" },
              ]}
            />
          </Field>
          <Field
            label="Value"
            error={errors.value}
            hint={d.adjust_type === "percent" ? "+20 = 20% more, −15 = 15% off" : d.adjust_type === "amount" ? "Per night; negative for less" : "The nightly price in KES"}
          >
            <NumberInput decimal value={d.value} onValueChange={(v) => setD({ ...d, value: v })} before={d.adjust_type === "percent" ? undefined : "KES"} after={d.adjust_type === "percent" ? "%" : undefined} />
          </Field>
          <Field label="Priority" error={errors.priority} hint="Higher applies last">
            <NumberInput value={d.priority} onValueChange={(v) => setD({ ...d, priority: v ?? 10 })} />
          </Field>
        </div>
        {discountOnly && (
          <Callout tone="warning">Last-minute and early-bird rules only work as a percentage discount — use a negative %, e.g. −15.</Callout>
        )}
      </div>
    </DialogContent>
  );
}
