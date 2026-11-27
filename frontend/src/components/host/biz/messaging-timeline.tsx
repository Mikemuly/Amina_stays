"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlarmClock, CalendarCheck, CircleCheck, CircleMinus, Clock, DoorOpen, Eye, Gift, IdCard, KeyRound, Languages, Lock, Luggage, MessageSquareText,
  MoonStar, Navigation, PenLine, Smile, Sparkles, Star, Wallet, type LucideIcon,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { ErrorBlock, LoadingBlock } from "@/components/host/common";
import { usePayOptions } from "@/components/providers";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Badge, Skeleton } from "@/components/ui/misc";
import { Popover, PopoverContent, PopoverTrigger, Switch, Tooltip } from "@/components/ui/overlays";
import { get, patch, post } from "@/lib/api";
import { plural } from "@/lib/format";
import { cn } from "@/lib/utils";

import { useHostSettings } from "./queries";
import type { Automation, AutomationPreview, HostSettings } from "./types";
import { Callout, Field, NumberInput, PhonePreview, errorMessage, replaceSearchParams } from "./ui";

const KEY = ["host", "automations"];

type Anchor = Automation["anchor"];
type Phase = "booked" | "before" | "arrival" | "during" | "checkout" | "after";

const PHASES: { key: Phase; label: string }[] = [
  { key: "booked", label: "At booking" },
  { key: "before", label: "Before arrival" },
  { key: "arrival", label: "Arrival day" },
  { key: "during", label: "During the stay" },
  { key: "checkout", label: "Checkout" },
  { key: "after", label: "After the stay" },
];

const ICONS: Record<string, LucideIcon> = {
  booking_confirmed: CalendarCheck, pre_arrival: Luggage, id_request: IdCard, balance_due: Wallet, directions: Navigation, checkin_code: KeyRound,
  welcome_check: Smile, mid_stay: Sparkles, checkout_reminder: AlarmClock, checkout_thanks: DoorOpen, review_request: Star, rebook_offer: Gift,
};

interface TimelineNode {
  id: string;
  auto?: Automation;
  name: string;
  description: string;
  anchor: Anchor;
  offset: number;
  time: string;
  when: string;
  template: string;
  sort: number;
}

const toMinutes = (t: string) => {
  const [h, m] = (t || "00:00").split(":").map(Number);
  return (h || 0) * 60 + (m || 0);
};

const pad = (h: number) => `${String(h).padStart(2, "0")}:00`;

export function whenLabel(anchor: Anchor, offset: number, time: string) {
  let day: string;
  if (anchor === "confirmed") day = offset ? `${plural(Math.abs(offset), "day")} after booking` : "As soon as it's paid";
  else {
    const what = anchor === "check_in" ? "check-in" : "checkout";
    if (offset === 0) day = anchor === "check_in" ? "Arrival day" : "Checkout day";
    else if (offset === -1) day = `Day before ${what}`;
    else if (offset === 1) day = `Day after ${what}`;
    else day = `${Math.abs(offset)} days ${offset < 0 ? "before" : "after"} ${what}`;
  }
  return time ? `${day} · ${time}` : day;
}

function phaseOf(anchor: Anchor, offset: number): Phase {
  if (anchor === "confirmed") return "booked";
  if (anchor === "check_in") return offset < 0 ? "before" : offset === 0 ? "arrival" : "during";
  return offset <= 0 ? "checkout" : "after";
}

function delayText(minutes: number) {
  if (minutes < 60) return `${minutes} min`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m ? `${h}h ${m}m` : `${h}h`;
}

function buildNodes(autos: Automation[], s: HostSettings, methods: string): TimelineNode[] {
  const rank: Record<Anchor, number> = { confirmed: 0, check_in: 1, check_out: 2 };
  const node = (n: Omit<TimelineNode, "sort">): TimelineNode => ({ ...n, sort: rank[n.anchor] * 1_000_000 + n.offset * 1440 + toMinutes(n.time) });
  const checkout = s.default_checkout_time || "11:00";
  const reviewAt = toMinutes(checkout) + s.review_delay_minutes;
  const system: TimelineNode[] = [
    node({
      id: "booking_confirmed", name: "Booking confirmed", template: "booking_confirmed", anchor: "confirmed", offset: 0, time: "",
      when: `The moment the ${methods} payment succeeds`, description: "Dates, reference, amount paid, any balance due and the trip link.",
    }),
    node({
      id: "checkin_code", name: "Door code", template: "checkin_code", anchor: "check_in", offset: 0, time: s.code_release_time || "08:00",
      when: `Arrival day · ${s.code_release_time || "08:00"}`, description: "The door code for this stay's exact dates, followed by local tips.",
    }),
    node({
      id: "checkout_thanks", name: "Checkout thanks", template: "checkout_thanks", anchor: "check_out", offset: 0, time: checkout,
      when: "Checkout day · as they check out", description: "Sent when the guest replies CHECKOUT or the stay is checked out automatically.",
    }),
    {
      id: "review_request", name: "Review request", template: "review_request", anchor: "check_out", offset: 0, time: "",
      when: `Checkout day · ${delayText(s.review_delay_minutes)} after checkout`, description: "Asks for a 1–5 rating by SMS reply. Never during quiet hours.",
      sort: 2 * 1_000_000 + reviewAt,
    },
  ];
  const automated = autos.map((a) =>
    node({ id: a.key, auto: a, name: a.name, description: a.description, template: a.template_key, anchor: a.anchor, offset: a.offset_days, time: a.send_time, when: whenLabel(a.anchor, a.offset_days, a.send_time) }),
  );
  return [...system, ...automated].sort((a, b) => a.sort - b.sort);
}

export function TimelineTab() {
  const qc = useQueryClient();
  const autosQ = useQuery({ queryKey: KEY, queryFn: () => get<Automation[]>("/api/host/automations") });
  const settingsQ = useHostSettings();
  const { methods } = usePayOptions();
  const [preview, setPreview] = React.useState<Automation | null>(null);

  const update = useMutation({
    mutationFn: ({ id, ...body }: Partial<Automation> & { id: number }) => patch<Automation>(`/api/host/automations/${id}`, body),
    onMutate: async ({ id, ...body }) => {
      await qc.cancelQueries({ queryKey: KEY });
      const prev = qc.getQueryData<Automation[]>(KEY);
      qc.setQueryData<Automation[]>(KEY, (old) => old?.map((a) => (a.id === id ? { ...a, ...body } : a)));
      return { prev };
    },
    onError: (e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(KEY, ctx.prev);
      toast.error(errorMessage(e, "Couldn't update the automation."));
    },
    onSuccess: (a, vars) => {
      if ("enabled" in vars) toast.success(`${a.name} ${a.enabled ? "switched on" : "paused"}`);
      else toast.success(`${a.name}: ${whenLabel(a.anchor, a.offset_days, a.send_time).toLowerCase()}`);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ["host"] }),
  });

  if (autosQ.error || settingsQ.error) {
    return (
      <ErrorBlock
        error={autosQ.error ?? settingsQ.error}
        retry={() => {
          autosQ.refetch();
          settingsQ.refetch();
        }}
      />
    );
  }
  if (!autosQ.data || !settingsQ.data) return <LoadingBlock rows={6} />;

  const s = settingsQ.data;
  const nodes = buildNodes(autosQ.data, s, methods);
  const on = autosQ.data.filter((a) => a.enabled).length;
  const openTemplate = (key: string) => replaceSearchParams({ tab: "templates", key });

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_300px]">
      <div className="min-w-0">
        <ol className="relative before:absolute before:top-2 before:bottom-2 before:left-[21px] before:w-px before:bg-line">
          {PHASES.map((phase) => {
            const items = nodes.filter((n) => phaseOf(n.anchor, n.offset) === phase.key);
            if (!items.length) return null;
            return (
              <li key={phase.key} className="relative mt-7 first:mt-0">
                <div className="flex items-center gap-3 pb-3">
                  <span className="relative z-10 ml-[17px] size-[9px] rounded-full bg-ink-3 ring-4 ring-surface" />
                  <span className="ml-5 text-[12px] font-bold tracking-wider text-ink-2 uppercase">{phase.label}</span>
                </div>
                <ol className="space-y-3">
                  {items.map((n) => (
                    <NodeCard
                      key={n.id}
                      node={n}
                      settings={s}
                      busy={update.isPending && update.variables?.id === n.auto?.id}
                      onToggle={(enabled) => n.auto && update.mutate({ id: n.auto.id, enabled })}
                      onTiming={(offset_days, send_time) => n.auto && update.mutate({ id: n.auto.id, offset_days, send_time })}
                      onPreview={() => n.auto && setPreview(n.auto)}
                      onWording={() => openTemplate(n.template)}
                    />
                  ))}
                </ol>
              </li>
            );
          })}
        </ol>
      </div>

      <aside className="space-y-4 xl:sticky xl:top-6 xl:self-start">
        <div className="rounded-2xl border border-line-soft bg-white p-5">
          <p className="text-[13px] font-semibold text-ink-2">Automations on</p>
          <p className="mt-1 text-3xl font-bold tracking-tight tabular-nums">
            {on}
            <span className="text-lg font-semibold text-ink-3">/{autosQ.data.length}</span>
          </p>
          <ul className="mt-4 space-y-3 text-[13.5px] text-ink-2">
            <li className="flex gap-2.5">
              <Languages className="mt-0.5 size-4 shrink-0 text-ink" />
              In each guest&apos;s language — English, Kiswahili, Italian, German or French.
            </li>
            <li className="flex gap-2.5">
              <MoonStar className="mt-0.5 size-4 shrink-0 text-ink" />
              Never during quiet hours ({pad(s.quiet_hours_start)}–{pad(s.quiet_hours_end)} Kenya time) — they wait until morning.
            </li>
            <li className="flex gap-2.5">
              <MessageSquareText className="mt-0.5 size-4 shrink-0 text-ink" />
              Each message goes out once per booking, even if the scheduler restarts.
            </li>
          </ul>
        </div>
        <Callout tone="info">
          Guests can reply to any of these by SMS — BREAKFAST, ETA 3pm, ID, CHECKOUT, HELP — and Ask Amina handles it or relays it to your inbox.
        </Callout>
      </aside>

      <Dialog open={!!preview} onOpenChange={(v) => !v && setPreview(null)}>
        {preview && (
          <PreviewContent
            auto={preview}
            onWording={() => {
              setPreview(null);
              openTemplate(preview.template_key);
            }}
          />
        )}
      </Dialog>
    </div>
  );
}

function NodeCard({
  node: n, settings: s, busy, onToggle, onTiming, onPreview, onWording,
}: {
  node: TimelineNode;
  settings: HostSettings;
  busy: boolean;
  onToggle: (v: boolean) => void;
  onTiming: (offset: number, time: string) => void;
  onPreview: () => void;
  onWording: () => void;
}) {
  const Icon = ICONS[n.id] ?? MessageSquareText;
  const system = !n.auto;
  const enabled = n.auto ? n.auto.enabled : true;
  return (
    <li className="relative grid grid-cols-[44px_minmax(0,1fr)] gap-3">
      <div className="flex justify-center pt-4">
        <span
          className={cn(
            "relative z-10 grid size-11 place-items-center rounded-full border-2 bg-white ring-4 ring-surface transition-colors",
            system ? "border-ocean-500 text-ocean-600" : enabled ? "border-ink text-ink" : "border-line text-ink-3",
          )}
        >
          <Icon className="size-[18px]" />
        </span>
      </div>
      <div className={cn("rounded-2xl border bg-white p-4 transition-colors sm:p-5", enabled ? "border-line-soft" : "border-dashed border-line bg-white/70")}>
        <div className="flex items-start gap-4">
          <div className="min-w-0 flex-1">
            <p className="flex flex-wrap items-center gap-2">
              <span className={cn("text-[15px] font-bold", !enabled && "text-ink-2")}>{n.name}</span>
              {system && (
                <Badge tone="ocean">
                  <Lock className="size-3" /> System
                </Badge>
              )}
              {!enabled && <Badge>Paused</Badge>}
            </p>
            <p className="mt-1.5 inline-flex items-center gap-1.5 rounded-full bg-surface px-2.5 py-1 text-[12.5px] font-semibold text-ink">
              <Clock className="size-3.5" /> {n.when}
            </p>
            <p className="mt-2 text-[13.5px] leading-relaxed text-ink-2">{n.description}</p>
          </div>
          {n.auto ? (
            <Switch checked={enabled} disabled={busy} onCheckedChange={onToggle} aria-label={`${n.name}: ${enabled ? "on" : "off"}`} />
          ) : (
            <Tooltip content="Part of the booking flow, so it's always on. You can still change the wording.">
              <span className="grid size-8 place-items-center rounded-full bg-ocean-50 text-ocean-600" aria-label="Always on">
                <Lock className="size-4" />
              </span>
            </Tooltip>
          )}
        </div>

        {n.id === "checkin_code" && <CodeRules s={s} />}

        <div className="mt-3.5 flex flex-wrap gap-2">
          {n.auto && (
            <>
              <Button variant="soft" size="sm" onClick={onPreview}>
                <Eye className="size-4" /> Preview
              </Button>
              <TimingPopover auto={n.auto} quiet={[s.quiet_hours_start, s.quiet_hours_end]} onSave={onTiming} />
            </>
          )}
          <Button variant="ghost" size="sm" onClick={onWording}>
            <PenLine className="size-4" /> Edit wording
          </Button>
        </div>
      </div>
    </li>
  );
}

function CodeRules({ s }: { s: HostSettings }) {
  const { mpesa } = usePayOptions();
  const rules: [boolean, string, string][] = [
    [true, "Balance paid in full", mpesa ? "If not, an M-Pesa prompt for the balance goes out instead." : "If not, a payment link for the balance goes out by SMS instead."],
    [s.require_id_before_code, "Guest-register ID or passport received", "Required by the Tourism Act guest register."],
    [s.sim_swap_check, "No recent SIM swap on the guest's number", "Checked with Africa's Talking Insights to stop SIM-swap fraud."],
  ];
  return (
    <div className="mt-3.5 rounded-xl border border-ocean-100 bg-ocean-50/60 p-3.5">
      <p className="text-[13px] font-semibold text-ink">Released only when every check passes</p>
      <ul className="mt-2 space-y-2">
        {rules.map(([on, title, text]) => (
          <li key={title} className="flex gap-2 text-[13px]">
            {on ? <CircleCheck className="mt-px size-4 shrink-0 text-success" /> : <CircleMinus className="mt-px size-4 shrink-0 text-ink-3" />}
            <span className={cn(!on && "text-ink-3")}>
              <span className={cn("font-medium", on ? "text-ink" : "line-through")}>{title}</span>
              {on ? <span className="text-ink-2"> — {text}</span> : <span> — switched off in Settings</span>}
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-2.5 text-[12.5px] leading-relaxed text-ink-2">
        If a check fails the guest gets a friendly SMS saying what&apos;s missing, and a SIM swap raises a security alert so you can call them first.
      </p>
    </div>
  );
}

function TimingPopover({ auto, quiet, onSave }: { auto: Automation; quiet: [number, number]; onSave: (offset: number, time: string) => void }) {
  const [open, setOpen] = React.useState(false);
  const [offset, setOffset] = React.useState<number | null>(auto.offset_days);
  const [time, setTime] = React.useState(auto.send_time);
  const hour = Number((time || "00:00").split(":")[0]);
  const [qs, qe] = quiet;
  const inQuiet = !!time && (qs > qe ? hour >= qs || hour < qe : hour >= qs && hour < qe);
  const anchor = auto.anchor === "check_in" ? "check-in" : auto.anchor === "check_out" ? "checkout" : "booking";
  const changed = offset !== auto.offset_days || time !== auto.send_time;
  return (
    <Popover
      open={open}
      onOpenChange={(v) => {
        if (v) {
          setOffset(auto.offset_days);
          setTime(auto.send_time);
        }
        setOpen(v);
      }}
    >
      <PopoverTrigger asChild>
        <Button variant="soft" size="sm">
          <Clock className="size-4" /> Edit timing
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-[320px]">
        <p className="text-[15px] font-bold">When should it go out?</p>
        <div className="mt-3 grid grid-cols-2 gap-3">
          <Field label="Days" hint={`From ${anchor}: −1 = day before`}>
            <NumberInput value={offset} onValueChange={setOffset} aria-label="Days relative to the stay" className="h-10" />
          </Field>
          <Field label="Time (Kenya)">
            <Input type="time" value={time} onChange={(e) => setTime(e.target.value)} className="h-10" />
          </Field>
        </div>
        <p className="mt-3 rounded-lg bg-surface px-3 py-2 text-[13px] font-semibold">{whenLabel(auto.anchor, offset ?? 0, time)}</p>
        {inQuiet && <p className="mt-2 text-[12.5px] text-warning">That&apos;s inside quiet hours — it will wait until {pad(qe)}.</p>}
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button
            variant="dark"
            size="sm"
            disabled={!changed || offset === null}
            onClick={() => {
              if (offset === null) return;
              onSave(offset, time);
              setOpen(false);
            }}
          >
            Save timing
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}

function PreviewContent({ auto, onWording }: { auto: Automation; onWording: () => void }) {
  const [ref, setRef] = React.useState("");
  const [asked, setAsked] = React.useState("");
  const q = useQuery({
    queryKey: ["host", "automation-preview", auto.id, asked],
    queryFn: () => post<AutomationPreview>(`/api/host/automations/${auto.id}/preview`, asked ? { ref: asked } : {}),
  });
  const mismatch = !!asked && !!q.data?.ref && q.data.ref !== asked.toUpperCase();
  return (
    <DialogContent title={auto.name} size="lg">
      <div className="grid gap-8 px-6 py-6 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        {q.isLoading ? (
          <Skeleton className="mx-auto h-80 w-full max-w-[330px] rounded-[2.2rem]" />
        ) : q.error ? (
          <ErrorBlock error={q.error} retry={q.refetch} />
        ) : (
          <PhonePreview
            text={q.data?.text ?? ""}
            footer={q.data?.ref ? `Rendered for ${q.data.ref} · ${plural(q.data.segments ?? 1, "SMS part")}` : "No upcoming booking to preview with yet."}
          />
        )}
        <div className="space-y-4">
          <div>
            <p className="text-[13px] font-semibold text-ink-2">When</p>
            <p className="mt-0.5 text-[15px] font-semibold">{whenLabel(auto.anchor, auto.offset_days, auto.send_time)}</p>
            <p className="mt-2 text-[14px] text-ink-2">{auto.description}</p>
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              setAsked(ref.trim().toUpperCase());
            }}
          >
            <Field label="Preview with a booking" hint="Uses that guest's language, dates and home. Leave blank for the next upcoming stay.">
              <div className="flex gap-2">
                <Input value={ref} onChange={(e) => setRef(e.target.value)} placeholder="AMS-4821" className="h-10 font-mono uppercase" aria-label="Booking reference" />
                <Button type="submit" variant="dark" className="h-10" loading={q.isFetching}>
                  Render
                </Button>
              </div>
            </Field>
          </form>
          {mismatch && <p className="text-[13px] text-warning">No booking {asked} — showing {q.data?.ref} instead.</p>}
          <Button variant="soft" size="sm" onClick={onWording}>
            <PenLine className="size-4" /> Edit the wording
          </Button>
        </div>
      </div>
    </DialogContent>
  );
}
