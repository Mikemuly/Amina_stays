"use client";

import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import { format, isSameDay, isToday, isTomorrow, isYesterday } from "date-fns";
import {
  AirVent, ArrowUpDown, BellRing, CircleCheck, CircleHelp, Clock, Construction, Droplets, Flame, House, Megaphone, MessageSquare, Pencil, RadioTower,
  Send, ShieldAlert, UserRound, Users, Waves, Wifi, X, Zap, type LucideIcon,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { ErrorBlock, LoadingBlock, PageHeader } from "@/components/host/common";
import { useNow } from "@/components/host/ops/lib";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent } from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { Badge, EmptyState } from "@/components/ui/misc";
import { get, post } from "@/lib/api";
import { fmtDateTime, plural } from "@/lib/format";
import { cn } from "@/lib/utils";

import { useInvalidateHost, useListings } from "./queries";
import { toGsm } from "./sms";
import { span } from "./support";
import type { NoticeKind, NoticePreview, NoticeRow, NoticesResponse } from "./types";
import { Callout, CharCount, ConfirmDialog, Field, NumberInput, PhonePreview, Segmented, SmsMeter, errorMessage, useDebounced } from "./ui";

type StatusFilter = "current" | "resolved" | "all";
type Meta = Omit<NoticesResponse, "notices">;

const SERVICE_ICON: Record<string, LucideIcon> = {
  power: Zap,
  water: Droplets,
  wifi: Wifi,
  ac: AirVent,
  gas: Flame,
  pool: Waves,
  lift: ArrowUpDown,
  road: Construction,
  network: RadioTower,
  security: ShieldAlert,
  other: CircleHelp,
};
// mirrors notices.services.default_title, for the title field's placeholder
const OUTAGE_TITLE: Record<string, string> = {
  power: "Power outage",
  water: "No water supply",
  wifi: "Wi-Fi down",
  ac: "Air conditioning not working",
  gas: "No cooking gas",
  pool: "Swimming pool closed",
  lift: "Lift out of service",
  road: "Road access blocked",
  network: "Mobile network problems",
  security: "Security incident",
  other: "Service disruption",
};
const KIND_HINT: Record<NoticeKind, string> = {
  outage: "Something has stopped working. Guests staying now, and those arriving before it's fixed, are texted straight away.",
  maintenance: "Work at a set time. Guests staying then get a heads-up a day before it starts, and a text when it's over.",
  advisory: "Something guests should know about, like road works or low water pressure.",
};
const MESSAGE_HINT: Record<string, string> = {
  power: "The backup generator runs lights, fans and the fridge — please switch off the AC and water heater.",
  water: "The tank is full, so taps and showers work — please keep showers short.",
  wifi: "The fibre provider is fixing a fault on our street. Mobile data works fine.",
};

const defaultTitle = (kind: NoticeKind, service: string, label: string) =>
  kind === "maintenance" ? `Planned maintenance: ${label}` : kind === "advisory" ? `Advisory: ${label}` : (OUTAGE_TITLE[service] ?? "Service disruption");

const pad = (n: number) => String(n).padStart(2, "0");
/** datetime-local value in the browser's zone, e.g. "2026-11-28T09:00". */
const toLocalInput = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
const isoOrNull = (local: string) => (local ? new Date(local).toISOString() : null);

const clockOf = (d: Date) => format(d, d.getMinutes() ? "h:mmaaa" : "haaa");
/** "2pm" today, "tomorrow 10am", else "Sat 28 Nov, 10am". */
function when(iso: string) {
  const d = new Date(iso);
  if (isToday(d)) return clockOf(d);
  if (isTomorrow(d)) return `tomorrow ${clockOf(d)}`;
  if (isYesterday(d)) return `yesterday ${clockOf(d)}`;
  return `${format(d, "EEE d MMM")}, ${clockOf(d)}`;
}
/** The backend's when_text for SMS previews: "2pm" today, else "Sat 28 Nov 2pm". */
const smsWhen = (d: Date) => (isToday(d) ? clockOf(d) : `${format(d, "EEE d MMM")} ${clockOf(d)}`);
const until = (start: string, end: string) => (isSameDay(new Date(start), new Date(end)) ? clockOf(new Date(end)) : when(end));

// ---------- page ----------

export function NoticesPage() {
  const [status, setStatus] = React.useState<StatusFilter>("current");
  const { data, isLoading, error, refetch, isFetching, isPlaceholderData } = useQuery({
    queryKey: ["host", "notices", status],
    queryFn: () => get<NoticesResponse>(`/api/host/notices?status=${status}`),
    refetchInterval: 30_000,
    placeholderData: keepPreviousData,
  });
  const current = useQuery({ queryKey: ["host", "notices", "current"], queryFn: () => get<NoticesResponse>("/api/host/notices?status=current"), refetchInterval: 30_000 });
  const live = current.data?.notices.length;

  return (
    <>
      <PageHeader
        title="Service alerts"
        subtitle="Tell guests about outages and planned work before they have to ask — by SMS, with a data bundle when the Wi-Fi or power is down."
      />

      {error && !data ? (
        <ErrorBlock error={error} retry={refetch} />
      ) : isLoading || !data ? (
        <LoadingBlock rows={6} />
      ) : (
        <div className="space-y-8">
          <Callout tone="info" icon={<Megaphone className="size-[18px]" />} title="Alerts reach guests on any phone">
            You or your staff can post one by SMS too — <Kw>OUTAGE POWER ALL generator on</Kw> — and close it with <Kw>RESTORED 12</Kw>. Guests check what&apos;s
            going on by texting <Kw>ALERTS</Kw> or on USSD under More → Service status. A guest who reports a problem an alert already covers gets the alert
            instead of a new work order.
          </Callout>

          <NewAlert meta={data} />

          <section aria-labelledby="alerts-heading">
            <div className="mb-4 flex flex-wrap items-center gap-3">
              <h2 id="alerts-heading" className="mr-auto text-lg font-bold tracking-tight">
                Alerts
              </h2>
              <Segmented<StatusFilter>
                label="Alert status"
                value={status}
                onChange={setStatus}
                options={[
                  { value: "current", label: "Current", count: live },
                  { value: "resolved", label: "Resolved" },
                  { value: "all", label: "All" },
                ]}
              />
            </div>
            {data.notices.length === 0 ? (
              <EmptyState icon={<CircleCheck className="size-5" />} title={status === "current" ? "Everything's running" : "Nothing here"}>
                {status === "current" ? "No outages or planned work right now. Post one above the moment something stops working." : "No alerts match this filter."}
              </EmptyState>
            ) : (
              <ul className={cn("space-y-3 transition-opacity", isFetching && isPlaceholderData && "opacity-60")}>
                {data.notices.map((n) => (
                  <NoticeCard key={n.id} n={n} dataServices={data.data_services} />
                ))}
              </ul>
            )}
          </section>
        </div>
      )}
    </>
  );
}

function Kw({ children }: { children: React.ReactNode }) {
  return <span className="rounded bg-white/80 px-1 font-mono text-[12.5px] font-semibold text-ink ring-1 ring-line-soft">{children}</span>;
}

// ---------- new alert ----------

function NewAlert({ meta }: { meta: Meta }) {
  const invalidate = useInvalidateHost();
  const { data: listings } = useListings();
  const [service, setService] = React.useState("power");
  const [kind, setKind] = React.useState<NoticeKind>("outage");
  const [unitIds, setUnitIds] = React.useState<number[]>([]);
  const [start, setStart] = React.useState<"now" | "later">("now");
  const [startsAt, setStartsAt] = React.useState("");
  const [expectedEnd, setExpectedEnd] = React.useState("");
  const [title, setTitle] = React.useState("");
  const [message, setMessage] = React.useState("");
  const [dataMb, setDataMb] = React.useState<number | null>(null);
  const [confirm, setConfirm] = React.useState(false);

  const later = kind === "maintenance" || start === "later";
  const showData = kind === "outage" && meta.data_services.includes(service);
  const serviceLabel = meta.services.find(([v]) => v === service)?.[1] ?? "Service";
  const mb = dataMb ?? meta.default_data_mb;
  const body = {
    kind,
    service,
    title: title.trim(),
    message: message.trim(),
    unit_ids: unitIds,
    starts_at: later ? isoOrNull(startsAt) : null,
    expected_end: isoOrNull(expectedEnd),
    data_mb: showData ? mb : 0,
  };
  const bodyKey = JSON.stringify(body);
  const debounced = useDebounced(bodyKey, 400);
  const missingStart = later && !startsAt;
  const preview = useQuery({
    queryKey: ["host", "notice-preview", debounced],
    queryFn: () => post<NoticePreview>("/api/host/notices/preview", JSON.parse(debounced)),
    enabled: !missingStart,
    retry: false,
    placeholderData: keepPreviousData,
  });
  const p = missingStart ? undefined : preview.data;
  const now = useNow(30_000);
  const planned = later && !!startsAt && now > 0 && new Date(startsAt).getTime() > now;

  const defaultStart = () => {
    const d = new Date();
    d.setDate(d.getDate() + 1);
    d.setHours(9, 0, 0, 0);
    return toLocalInput(d);
  };
  const pickKind = (k: NoticeKind) => {
    setKind(k);
    if (k === "maintenance" && !startsAt) setStartsAt(defaultStart());
  };
  const pickStart = (v: "now" | "later") => {
    setStart(v);
    if (v === "later" && !startsAt) setStartsAt(defaultStart());
  };
  const reset = () => {
    setService("power");
    setKind("outage");
    setUnitIds([]);
    setStart("now");
    setStartsAt("");
    setExpectedEnd("");
    setTitle("");
    setMessage("");
    setDataMb(null);
  };

  const create = useMutation({
    mutationFn: () => post<NoticeRow>("/api/host/notices", body),
    onSuccess: (n) => {
      if (n.status === "scheduled") {
        toast.success("Planned work scheduled", {
          description: n.notified ? `${plural(n.notified, "guest")} got a heads-up by SMS.` : "Guests staying then get a heads-up by SMS a day before it starts.",
        });
      } else {
        toast.success(n.notified ? `Alert sent to ${plural(n.notified, "guest")}` : "Alert posted", {
          description: n.notified ? "They'll get another SMS when you mark it resolved." : "Nobody is staying at those homes right now; guests who arrive while it's on are told.",
        });
      }
      setConfirm(false);
      reset();
      invalidate();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  const homes = listings ?? [];
  const toggleUnit = (id: number) => setUnitIds((ids) => (ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]));
  const homesText = unitIds.length === 0 ? "every home" : homes.filter((h) => unitIds.includes(h.id)).map((h) => h.name).join(", ");
  // only once the preview matches what's on screen, so the confirmation shows the SMS that will really go out
  const canSend = !missingStart && !!p && !preview.isError && !preview.isFetching && debounced === bodyKey;
  const audience = p ? (planned ? `${plural(p.guests, "guest")} staying then` : plural(p.guests, "guest")) : "";

  const phone =
    preview.isError && !missingStart ? (
      <Callout tone="warning" title="Can't preview this yet">
        {errorMessage(preview.error)}
      </Callout>
    ) : (
      <PhonePreview text={p?.sms ?? "The SMS guests get appears here."} footer={p ? plural(p.segments, "SMS part") : undefined} />
    );
  const previewPanel = (
    <div className="space-y-4">
      <div className="rounded-2xl border border-line-soft bg-white p-5">
        <p className="flex items-center gap-2 text-[15px]">
          <Users className="size-4 shrink-0 text-ink-2" />
          {p ? (
            <span>
              <b className="tabular-nums">{p.guests}</b> {p.guests === 1 ? "guest" : "guests"} will get this SMS
            </span>
          ) : (
            <span className="text-ink-2">{missingStart ? "Pick a start time" : "Counting guests…"}</span>
          )}
        </p>
        <p className="mt-1 text-[12.5px] text-ink-2">
          {planned ? "Staying while the work runs — texted a day before it starts." : "Staying now, or arriving before it's fixed."}
          {showData && mb > 0 && !planned && ` Each guest staying gets ${mb} MB of data.`}
        </p>
      </div>
      {phone}
    </div>
  );

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
      <section className="min-w-0 rounded-2xl border border-line-soft bg-white">
        <header className="border-b border-line-soft px-5 py-4 sm:px-6">
          <h2 className="flex items-center gap-2 text-[17px] font-bold tracking-tight">
            <BellRing className="size-5" /> New alert
          </h2>
          <p className="mt-0.5 text-[13.5px] text-ink-2">Only guests at the homes you pick are texted — and told again when it&apos;s over.</p>
        </header>
        <div className="space-y-6 px-5 py-5 sm:px-6">
          <div>
            <p className="mb-2 text-[13px] font-semibold">What&apos;s affected</p>
            <div role="radiogroup" aria-label="Service" className="flex flex-wrap gap-2">
              {meta.services.map(([value, label]) => {
                const Icon = SERVICE_ICON[value] ?? CircleHelp;
                const on = value === service;
                return (
                  <button
                    key={value}
                    type="button"
                    role="radio"
                    aria-checked={on}
                    onClick={() => setService(value)}
                    className={cn(
                      "inline-flex h-9 items-center gap-1.5 rounded-full border px-3 text-[13px] font-semibold transition",
                      on ? "border-ink bg-ink text-white" : "border-line text-ink-2 hover:border-ink-3 hover:text-ink",
                    )}
                  >
                    <Icon className="size-4" /> {label}
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <p className="mb-2 text-[13px] font-semibold">Type</p>
            <Segmented<NoticeKind>
              label="Type of alert"
              value={kind}
              onChange={pickKind}
              options={meta.kinds.map(([value, label]) => ({
                value,
                // "Planned maintenance" doesn't fit next to the others on a 360px phone
                label:
                  value === "maintenance" ? (
                    <>
                      <span className="min-[420px]:hidden">Planned</span>
                      <span className="hidden min-[420px]:inline">{label}</span>
                    </>
                  ) : (
                    label
                  ),
              }))}
            />
            <p className="mt-2 text-[13px] text-ink-2">{KIND_HINT[kind]}</p>
          </div>

          <div>
            <p className="mb-2 text-[13px] font-semibold">Which homes</p>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                aria-pressed={unitIds.length === 0}
                onClick={() => setUnitIds([])}
                className={cn("rounded-full border px-3 py-1.5 text-[13px] font-semibold", unitIds.length === 0 ? "border-ink bg-ink text-white" : "border-line text-ink-2 hover:border-ink-3")}
              >
                All homes
              </button>
              {homes.map((h) => {
                const on = unitIds.includes(h.id);
                return (
                  <button
                    key={h.id}
                    type="button"
                    aria-pressed={on}
                    onClick={() => toggleUnit(h.id)}
                    className={cn("rounded-full border px-3 py-1.5 text-[13px] font-semibold", on ? "border-ink bg-ink text-white" : "border-line text-ink-2 hover:border-ink-3")}
                  >
                    {h.name}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="grid gap-5 sm:grid-cols-2">
            <div className="min-w-0">
              <p className="mb-2 text-[13px] font-semibold">Starts</p>
              {kind === "maintenance" ? (
                <p className="mb-2 text-[13px] text-ink-2">Planned work needs a start time.</p>
              ) : (
                <Segmented<"now" | "later">
                  label="When it starts"
                  value={start}
                  onChange={pickStart}
                  options={[
                    { value: "now", label: "Now" },
                    { value: "later", label: "Later" },
                  ]}
                  className="mb-2"
                />
              )}
              {later && (
                <Input type="datetime-local" aria-label="Start time" value={startsAt} onChange={(e) => setStartsAt(e.target.value)} className="min-w-0" />
              )}
              {later && startsAt && !planned && <p className="mt-1.5 text-[13px] text-ink-2">That time has passed, so the alert starts straight away.</p>}
            </div>
            <Field label="Expected back (optional)" hint="Guests are told when to expect it fixed.">
              <Input type="datetime-local" value={expectedEnd} min={later && startsAt ? startsAt : undefined} onChange={(e) => setExpectedEnd(e.target.value)} className="min-w-0" />
            </Field>
          </div>

          <Field label="Title (optional)" hint="Leave blank for the standard title in the guest's language.">
            <Input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={100} placeholder={defaultTitle(kind, service, serviceLabel)} />
          </Field>

          <div>
            <Field
              label={
                <span className="flex items-center justify-between gap-3">
                  What guests should know <CharCount value={message} max={300} />
                </span>
              }
            >
              <Textarea value={message} onChange={(e) => setMessage(e.target.value)} rows={3} maxLength={300} placeholder={MESSAGE_HINT[service] ?? "The cause, what still works, what to do."} />
            </Field>
            <SmsMeter text={p?.sms ?? message} onFix={() => setMessage(toGsm(message))} className="mt-2" />
          </div>

          {showData && (
            <Field label="Data bundle for each guest staying" hint="Africa's Talking Mobile Data to each guest staying, so they stay connected. 0 = none." className="max-w-sm">
              <NumberInput value={mb} onValueChange={(v) => setDataMb(v ?? 0)} after="MB" />
            </Field>
          )}

          <div className="xl:hidden">{phone}</div>

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line-soft pt-4">
            <p className="text-[13px] text-ink-2" aria-live="polite">
              {missingStart ? (
                "Pick when it starts."
              ) : preview.isError ? (
                <span className="text-danger">{errorMessage(preview.error)}</span>
              ) : p ? (
                <>
                  <b className="text-ink tabular-nums">{audience}</b> {planned ? "will get a heads-up" : "will get this SMS"} · {homesText}
                </>
              ) : (
                "Counting guests…"
              )}
            </p>
            <Button variant="brand" onClick={() => setConfirm(true)} disabled={!canSend}>
              <Send className="size-4" /> {planned ? "Schedule alert" : "Send alert"}
            </Button>
          </div>
        </div>
      </section>

      <aside className="hidden min-w-0 xl:sticky xl:top-28 xl:block xl:self-start">{previewPanel}</aside>

      <ConfirmDialog
        open={confirm}
        onOpenChange={setConfirm}
        title={planned ? "Schedule this alert?" : `Text ${plural(p?.guests ?? 0, "guest")} now?`}
        confirmLabel={planned ? "Schedule" : "Send alert"}
        tone="brand"
        loading={create.isPending}
        onConfirm={() => create.mutate()}
      >
        <p>
          <b className="text-ink">{title.trim() || defaultTitle(kind, service, serviceLabel)}</b> at {homesText}.{" "}
          {planned ? "Guests staying then get this a day before it starts" : "Guests staying now get this straight away"}, and an SMS when you mark it resolved.
          {showData && mb > 0 && !planned && ` Each guest staying also gets ${mb} MB of mobile data.`}
        </p>
        {p && (
          <div className="rounded-xl bg-[#f2f2f7] p-3">
            <div className="rounded-[1rem] rounded-bl-[0.3rem] bg-white px-3.5 py-2 text-[14px] leading-snug whitespace-pre-wrap text-ink shadow-sm">{p.sms}</div>
          </div>
        )}
        <p className="text-[13px]">SMS can&apos;t be unsent. Replies come back to your inbox.</p>
      </ConfirmDialog>
    </div>
  );
}

// ---------- list ----------

const STATUS_META: Record<NoticeRow["status"], { label: string; tone: "danger" | "warning" | "ocean" | "success" | "neutral" }> = {
  active: { label: "Active", tone: "danger" },
  scheduled: { label: "Upcoming", tone: "ocean" },
  resolved: { label: "Resolved", tone: "success" },
  cancelled: { label: "Cancelled", tone: "neutral" },
};
const SOURCE_TEXT: Record<string, string> = { sms: "Posted by SMS", ussd: "Posted on USSD", staff: "Posted by staff" };

function NoticeCard({ n, dataServices }: { n: NoticeRow; dataServices: string[] }) {
  const invalidate = useInvalidateHost();
  const now = useNow(60_000);
  const [updating, setUpdating] = React.useState(false);
  const [resolving, setResolving] = React.useState(false);
  const [cancelling, setCancelling] = React.useState(false);
  const [note, setNote] = React.useState("");

  const resolve = useMutation({
    mutationFn: () => post<NoticeRow>(`/api/host/notices/${n.id}/resolve`, { note: note.trim() }),
    onSuccess: (r) => {
      const told = r.notified - n.notified;
      toast.success(`${r.title}: resolved`, { description: told ? `${plural(told, "guest")} told it's fixed.` : "Nobody was staying who needed telling." });
      setResolving(false);
      invalidate();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const cancel = useMutation({
    mutationFn: () => post<NoticeRow>(`/api/host/notices/${n.id}/cancel`),
    onSuccess: (r) => {
      const told = r.notified - n.notified;
      toast.success("Planned work cancelled", { description: told ? `${plural(told, "guest")} told it's off.` : undefined });
      setCancelling(false);
      invalidate();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  const Icon = SERVICE_ICON[n.service] ?? CircleHelp;
  const live = n.status === "active";
  const planned = n.status === "scheduled";
  const late = live && !!n.expected_end && now > 0 && Date.parse(n.expected_end) < now;
  const outage = n.kind === "outage";
  const stripe = live ? (outage ? "bg-danger" : "bg-warning") : planned ? "bg-ocean-500" : "bg-line";
  const iconCls = live ? (outage ? "bg-danger-50 text-danger" : "bg-warning-50 text-warning") : planned ? "bg-ocean-50 text-ocean-600" : "bg-surface text-ink-3";
  const st = STATUS_META[n.status] ?? STATUS_META.cancelled;
  const homes = n.all_homes ? "All homes" : n.units.map((u) => u.name).join(", ");
  const times = live
    ? `Since ${when(n.starts_at)}${n.expected_end ? ` · back by ${until(n.starts_at, n.expected_end)}` : ""}`
    : planned
      ? `Planned ${when(n.starts_at)}${n.expected_end ? ` – ${until(n.starts_at, n.expected_end)}` : ""}`
      : n.status === "resolved" && n.resolved_at
        ? `${when(n.starts_at)} – ${until(n.starts_at, n.resolved_at)} (${span(Date.parse(n.resolved_at) - Date.parse(n.starts_at))})`
        : `Was planned for ${when(n.starts_at)}`;
  const source = SOURCE_TEXT[n.source] ?? (n.created_by ? `Posted by ${n.created_by}` : null);

  return (
    <li className={cn("relative overflow-hidden rounded-2xl border bg-white", live && outage ? "border-danger/30" : "border-line-soft", !live && !planned && "opacity-90")}>
      <span className={cn("absolute inset-y-0 left-0 w-1", stripe)} aria-hidden />
      <div className="flex flex-wrap gap-x-4 gap-y-3 py-4 pr-4 pl-5 sm:pr-5 sm:pl-6">
        <span className={cn("hidden size-11 shrink-0 place-items-center rounded-full sm:grid", iconCls)}>
          <Icon className="size-5" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <Icon className={cn("size-4 sm:hidden", live ? (outage ? "text-danger" : "text-warning") : "text-ink-2")} aria-hidden />
            <span className="text-[15px] font-bold [overflow-wrap:anywhere]">{n.title}</span>
            <Badge tone={live && !outage ? "warning" : st.tone} dot={live}>
              {st.label}
            </Badge>
            <Badge>{n.kind_label}</Badge>
            <span className="text-[12px] text-ink-3">#{n.id}</span>
          </p>
          {n.message && <p className="mt-1 text-[14px] leading-relaxed text-ink-2 [overflow-wrap:anywhere]">{n.message}</p>}
          <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[12.5px] text-ink-2">
            <span className="inline-flex min-w-0 items-center gap-1 font-medium text-ink">
              <House className="size-3.5 shrink-0 text-ink-2" />
              <span className="[overflow-wrap:anywhere]">{homes}</span>
            </span>
            <span className="inline-flex items-center gap-1" title={`${fmtDateTime(n.starts_at)}${n.expected_end ? ` → ${fmtDateTime(n.expected_end)}` : ""}`}>
              <Clock className="size-3.5 shrink-0" /> {times}
            </span>
            <span className="inline-flex items-center gap-1">
              <MessageSquare className="size-3.5 shrink-0" /> {n.notified ? `${n.notified} SMS to guests` : "No guests texted yet"}
            </span>
            {n.data_mb > 0 && dataServices.includes(n.service) && (
              <span className="inline-flex items-center gap-1">
                <Wifi className="size-3.5 shrink-0" /> {n.data_mb} MB data per guest
              </span>
            )}
            {source && (
              <span className="inline-flex items-center gap-1">
                <UserRound className="size-3.5 shrink-0" /> {source}
              </span>
            )}
          </p>
          {late && (
            <p className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-warning-50 px-2.5 py-0.5 text-[12px] font-semibold text-warning">
              <Clock className="size-3.5" /> Past its expected end — still on? Set a new time or resolve it.
            </p>
          )}
          {n.resolution && (
            <p className="mt-2 text-[13px] text-ink-2 [overflow-wrap:anywhere]">
              <b className="font-semibold text-ink">Fixed:</b> {n.resolution}
            </p>
          )}
        </div>
        {(live || planned) && (
          <div className="flex w-full shrink-0 flex-wrap items-start gap-2 sm:w-auto sm:flex-col sm:items-stretch">
            <Button variant="soft" size="sm" onClick={() => setUpdating(true)}>
              <Pencil className="size-4" /> Update
            </Button>
            {live ? (
              <Button
                variant="dark"
                size="sm"
                onClick={() => {
                  setNote("");
                  setResolving(true);
                }}
              >
                <CircleCheck className="size-4" /> Resolve
              </Button>
            ) : (
              <Button variant="danger-outline" size="sm" onClick={() => setCancelling(true)}>
                <X className="size-4" /> Cancel
              </Button>
            )}
          </div>
        )}
      </div>

      <Dialog open={updating} onOpenChange={setUpdating}>
        {updating && <UpdateDialog n={n} onDone={() => setUpdating(false)} />}
      </Dialog>

      <ConfirmDialog
        open={resolving}
        onOpenChange={setResolving}
        title={`Resolve: ${n.title}`}
        confirmLabel="Mark resolved"
        loading={resolve.isPending}
        onConfirm={() => resolve.mutate()}
      >
        <p>Guests who were told it was down get “Good news: {n.title} at their home is over and everything is working again.” Your note is added to it.</p>
        <Field label="What fixed it? (optional)" hint={`${note.length}/240`}>
          <Textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} maxLength={240} placeholder="e.g. Kenya Power replaced the fuse on the transformer." autoFocus />
        </Field>
      </ConfirmDialog>

      <ConfirmDialog
        open={cancelling}
        onOpenChange={setCancelling}
        title="Cancel the planned work?"
        confirmLabel="Cancel it"
        tone="danger"
        loading={cancel.isPending}
        onConfirm={() => cancel.mutate()}
      >
        <p>
          <b className="text-ink">{n.title}</b> ({when(n.starts_at)}) is called off. Guests who already got a heads-up are told nothing changes for their stay.
        </p>
      </ConfirmDialog>
    </li>
  );
}

function UpdateDialog({ n, onDone }: { n: NoticeRow; onDone: () => void }) {
  const invalidate = useInvalidateHost();
  const original = n.expected_end ? toLocalInput(new Date(n.expected_end)) : "";
  const [message, setMessage] = React.useState(n.message);
  const [end, setEnd] = React.useState(original);
  const messageChanged = message.trim() !== n.message.trim();
  const endChanged = !!end && end !== original;
  const save = useMutation({
    mutationFn: () =>
      post<NoticeRow>(`/api/host/notices/${n.id}/update`, {
        ...(messageChanged ? { message: message.trim() } : {}),
        ...(endChanged ? { expected_end: isoOrNull(end) } : {}),
      }),
    onSuccess: (r) => {
      const told = r.notified - n.notified;
      toast.success(told ? `Update texted to ${plural(told, "guest")}` : "Alert updated", {
        description: told ? undefined : "Nobody has been told about it yet — guests told from now on get the new details.",
      });
      invalidate();
      onDone();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const { data: listings } = useListings();
  const eta = end ? ` Expected back by ${smsWhen(new Date(end))}.` : "";
  const home = n.units[0]?.name ?? listings?.[0]?.name ?? "the home";
  const sms = `Update - ${n.title} at ${home}: ${message.trim()}${eta}`;
  return (
    <DialogContent
      size="md"
      title="Update the alert"
      footer={
        <div className="flex justify-end gap-2">
          <DialogClose asChild>
            <Button variant="ghost">Cancel</Button>
          </DialogClose>
          <Button variant="dark" loading={save.isPending} disabled={!messageChanged && !endChanged} onClick={() => save.mutate()}>
            <Send className="size-4" /> Send update
          </Button>
        </div>
      }
    >
      <div className="space-y-4 px-6 py-5">
        <p className="text-[14px] text-ink-2">
          <b className="text-ink">{n.title}</b> · {n.all_homes ? "All homes" : n.units.map((u) => u.name).join(", ")}. Guests who were told about it get the update by SMS.
        </p>
        <div>
          <Field
            label={
              <span className="flex items-center justify-between gap-3">
                What guests should know <CharCount value={message} max={300} />
              </span>
            }
          >
            <Textarea value={message} onChange={(e) => setMessage(e.target.value)} rows={3} maxLength={300} autoFocus />
          </Field>
          <SmsMeter text={sms} onFix={() => setMessage(toGsm(message))} className="mt-2" />
        </div>
        <Field label="Expected back" hint={n.expected_end ? `Was ${when(n.expected_end)}.` : "No time given yet."}>
          <Input type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)} className="min-w-0" />
        </Field>
        <div className="rounded-xl bg-[#f2f2f7] p-3">
          <div className="rounded-[1rem] rounded-bl-[0.3rem] bg-white px-3.5 py-2 text-[14px] leading-snug whitespace-pre-wrap text-ink shadow-sm">{sms}</div>
        </div>
      </div>
    </DialogContent>
  );
}
