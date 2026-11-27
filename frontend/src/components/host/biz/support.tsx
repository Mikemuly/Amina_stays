"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BellRing, CalendarDays, CircleCheck, CircleHelp, Headset, Inbox, LifeBuoy, MessageSquare, MessageSquareWarning, PhoneCall, Plus, Receipt, Reply,
  RotateCcw, Send, Star, StickyNote, ThumbsUp, Timer, UserRound, Wrench, type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { ChannelBadge, ErrorBlock, LoadingBlock, PageHeader, StatusBadge } from "@/components/host/common";
import { fmtPhone, useNow } from "@/components/host/ops/lib";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogTrigger, SheetContent } from "@/components/ui/dialog";
import { Input, Select, Textarea } from "@/components/ui/input";
import { Badge, EmptyState, Stars } from "@/components/ui/misc";
import { ApiError, get, post, qs } from "@/lib/api";
import { CHANNEL_LABEL, ago, fmtDateTime, plural } from "@/lib/format";
import { cn } from "@/lib/utils";

import { useHostSettings, useInvalidateHost } from "./queries";
import { toGsm } from "./sms";
import type { TicketCallResult, TicketCategory, TicketDetail, TicketEvent, TicketPriority, TicketRow, TicketsResponse } from "./types";
import { Callout, ConfirmDialog, Field, Segmented, SmsMeter, errorMessage, humanize, replaceSearchParams, reservationHref } from "./ui";

type StatusFilter = "open" | "resolved" | "all";

const CATEGORY: Record<TicketCategory, { label: string; icon: LucideIcon; placeholder: string }> = {
  complaint: { label: "Complaint", icon: MessageSquareWarning, placeholder: "Noise from the next plot after midnight" },
  callback: { label: "Call-back request", icon: PhoneCall, placeholder: "Please call me back" },
  billing: { label: "Billing & payments", icon: Receipt, placeholder: "Charged twice for breakfast" },
  booking: { label: "Booking & changes", icon: CalendarDays, placeholder: "Wants to add a night on Saturday" },
  feedback: { label: "Feedback", icon: ThumbsUp, placeholder: "Loved the welcome — more towels next time" },
  issue: { label: "Problem in the home", icon: Wrench, placeholder: "" },
  other: { label: "Other", icon: CircleHelp, placeholder: "What the guest needs" },
};
// "Problem in the home" tickets come from work orders (a guest reporting a fault), so they aren't opened by hand
const NEW_CATEGORIES: TicketCategory[] = ["complaint", "callback", "billing", "booking", "feedback", "other"];
const FILTER_CATEGORIES: TicketCategory[] = ["complaint", "callback", "issue", "billing", "booking", "feedback", "other"];
const PRIORITY: Record<TicketPriority, { label: string; tone: "danger" | "warning" | "neutral" }> = {
  urgent: { label: "Urgent", tone: "danger" },
  high: { label: "High", tone: "warning" },
  normal: { label: "Normal", tone: "neutral" },
  low: { label: "Low", tone: "neutral" },
};

const isOpen = (t: TicketRow) => t.status === "open" || t.status === "in_progress";
const ms = (iso?: string | null) => (iso ? Date.parse(iso) : Number.POSITIVE_INFINITY);

/** "4 min", "1 h 20 min", "2 d 3 h". */
export function span(millis: number) {
  const m = Math.max(1, Math.round(Math.abs(millis) / 60_000));
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  if (h < 24) return m % 60 ? `${h} h ${m % 60} min` : `${h} h`;
  return h % 24 ? `${Math.floor(h / 24)} d ${h % 24} h` : `${Math.floor(h / 24)} d`;
}

// overdue first, then by reply-by time, then answered ones, then the closed ones (latest first)
function rank(t: TicketRow) {
  if (!isOpen(t)) return 3;
  if (t.overdue) return 0;
  return t.first_response_at ? 2 : 1;
}
function byUrgency(a: TicketRow, b: TicketRow) {
  const r = rank(a) - rank(b);
  if (r) return r;
  if (rank(a) < 2) return ms(a.first_response_due) - ms(b.first_response_due) || b.id - a.id;
  if (rank(a) === 2) return ms(b.last_activity_at) - ms(a.last_activity_at) || b.id - a.id;
  return ms(b.resolved_at ?? b.created_at) - ms(a.resolved_at ?? a.created_at) || b.id - a.id;
}

// a guest without a name has their phone number as display name
const realName = (t: TicketRow) => {
  const n = t.guest?.name?.trim();
  return n && !/^\+?[\d\s]+$/.test(n) ? n : null;
};
const guestName = (t: TicketRow) => realName(t) ?? fmtPhone(t.phone);
const firstName = (t: TicketRow) => realName(t)?.split(/\s+/)[0] ?? "the guest";

function callToast(r: TicketCallResult) {
  if (r.placed) toast.success("Calling you now", { description: r.detail });
  else if (r.dry_run) toast("Call simulated", { description: r.detail });
  else toast.error(r.detail || "Couldn't start the call.");
}

// ---------- page ----------

export function SupportPage() {
  const invalidate = useInvalidateHost();
  const sp = useSearchParams();
  const openId = Number(sp.get("ticket")) || null;
  const setOpenId = (id: number | null) => replaceSearchParams({ ticket: id ? String(id) : null });
  const [status, setStatus] = React.useState<StatusFilter>("open");
  const [category, setCategory] = React.useState("");
  const now = useNow(30_000);

  const { data, isLoading, error, refetch, isFetching, isPlaceholderData } = useQuery({
    queryKey: ["host", "support", "tickets", status, category],
    queryFn: () => get<TicketsResponse>(`/api/host/support/tickets${qs({ status, category })}`),
    refetchInterval: 15_000,
    placeholderData: keepPreviousData,
  });
  const call = useMutation({
    mutationFn: (t: TicketRow) => post<TicketCallResult>(`/api/host/support/tickets/${t.id}/call`),
    onSuccess: (r) => {
      callToast(r);
      invalidate();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  const counts = data?.counts;
  const tickets = [...(data?.tickets ?? [])].sort(byUrgency);
  const current = data?.tickets.find((t) => t.id === openId);

  return (
    <>
      <PageHeader
        title="Support desk"
        subtitle="Complaints, call-back requests and questions from SMS, USSD, voice and the website — each with a reference and a reply-by time."
        actions={<NewTicketButton onCreated={(t) => setOpenId(t.id)} />}
      />

      <div className="space-y-6">
        {error && !data ? (
          <ErrorBlock error={error} retry={refetch} />
        ) : (
          <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
            <KpiTile label="Open" value={counts ? counts.open : "–"} hint={counts ? `${counts.resolved_7d} resolved in the last 7 days` : " "} icon={<Inbox className="size-4" />} tone="ocean" />
            <KpiTile
              label="Overdue"
              value={counts ? counts.overdue : "–"}
              hint={!counts ? " " : counts.overdue ? "Past their reply-by time" : "Everyone answered in time"}
              icon={<BellRing className="size-4" />}
              tone={counts?.overdue ? "danger" : "neutral"}
            />
            <KpiTile
              label="Avg. first reply"
              value={counts?.avg_first_response_min != null ? span(counts.avg_first_response_min * 60_000) : "–"}
              hint="Last 30 days"
              icon={<Timer className="size-4" />}
            />
            <KpiTile
              label="Satisfaction"
              value={
                counts?.csat != null ? (
                  <span className="inline-flex items-center gap-1.5">
                    {counts.csat.toFixed(1)}
                    <Star className="size-5 fill-ink text-ink" />
                  </span>
                ) : (
                  "–"
                )
              }
              hint={counts ? (counts.csat_count ? `${plural(counts.csat_count, "rating")} · last 90 days` : "No ratings yet") : " "}
              icon={<ThumbsUp className="size-4" />}
              tone="brand"
            />
          </div>
        )}

        <Callout tone="info" icon={<LifeBuoy className="size-[18px]" />} title="Every request gets a reference and a reply-by time">
          Guests text <Kw>COMPLAIN …</Kw>, <Kw>CALL ME</Kw>, <Kw>TICKETS</Kw> or a reference like <Kw>T12</Kw>; on USSD they choose Talk to Amina → Make a
          complaint or My requests; on a call they press 5 to leave a voice message; or they use the website. Complaints and call-backs are due in 30 minutes,
          most other requests in 2 hours. If nobody answers in time you get an SMS, then a phone call. You can answer from your phone too:{" "}
          <Kw>T12 your reply</Kw>, <Kw>CALL T12</Kw> or <Kw>RESOLVE T12</Kw>.
        </Callout>

        <div className="flex flex-wrap items-center gap-3">
          <Segmented<StatusFilter>
            label="Ticket status"
            value={status}
            onChange={setStatus}
            options={[
              { value: "open", label: "Open", count: counts?.open },
              { value: "resolved", label: "Resolved" },
              { value: "all", label: "All" },
            ]}
          />
          <Select aria-label="Filter by category" value={category} onChange={(e) => setCategory(e.target.value)} className="h-10 w-full text-sm sm:w-56">
            <option value="">Every kind of request</option>
            {FILTER_CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {CATEGORY[c].label}
              </option>
            ))}
          </Select>
          {data && <p className="hidden text-[13px] text-ink-2 sm:ml-auto sm:block">{plural(tickets.length, "ticket")}</p>}
        </div>

        {error && !data ? null : isLoading ? (
          <LoadingBlock rows={4} />
        ) : tickets.length === 0 ? (
          <EmptyState icon={<CircleCheck className="size-5" />} title={status === "open" ? "Nothing waiting" : "No tickets here"}>
            {status === "open"
              ? "No open requests. Complaints, call-back requests and questions show up here the moment a guest sends one."
              : "No tickets match this filter."}
          </EmptyState>
        ) : (
          <ul className={cn("space-y-3 transition-opacity", isFetching && isPlaceholderData && "opacity-60")}>
            {tickets.map((t) => (
              <TicketCard key={t.id} t={t} now={now} onOpen={() => setOpenId(t.id)} onCall={() => call.mutate(t)} calling={call.isPending && call.variables?.id === t.id} />
            ))}
          </ul>
        )}
      </div>

      <Dialog open={openId !== null} onOpenChange={(o) => !o && setOpenId(null)}>
        {openId !== null && <TicketSheet key={openId} id={openId} row={current} />}
      </Dialog>
    </>
  );
}

function Kw({ children }: { children: React.ReactNode }) {
  return <span className="rounded bg-white/80 px-1 font-mono text-[12.5px] font-semibold whitespace-nowrap text-ink ring-1 ring-line-soft">{children}</span>;
}

const KPI_TONES = {
  neutral: { box: "border-line-soft", icon: "bg-surface text-ink-2" },
  brand: { box: "border-line-soft", icon: "bg-brand-50 text-brand-600" },
  ocean: { box: "border-line-soft", icon: "bg-ocean-50 text-ocean-600" },
  warning: { box: "border-warning/30 bg-warning-50/50", icon: "bg-warning-50 text-warning" },
  danger: { box: "border-danger/30 bg-danger-50/60", icon: "bg-danger text-white" },
};

/** A KPI tile that fits two-up on a 360px phone (icons hide below sm) and can turn amber or red. */
export function KpiTile({
  label, value, hint, icon, tone = "neutral", children,
}: { label: React.ReactNode; value: React.ReactNode; hint?: React.ReactNode; icon?: React.ReactNode; tone?: keyof typeof KPI_TONES; children?: React.ReactNode }) {
  const t = KPI_TONES[tone];
  return (
    <div className={cn("min-w-0 rounded-2xl border bg-white p-4 sm:p-5", t.box)}>
      <div className="flex items-start justify-between gap-2">
        <p className="min-w-0 text-[13px] leading-snug font-medium text-ink-2 sm:text-sm">{label}</p>
        {icon && <span className={cn("hidden size-8 shrink-0 place-items-center rounded-full sm:grid", t.icon)}>{icon}</span>}
      </div>
      <p className={cn("mt-2 text-[22px] leading-none font-semibold tracking-tight tabular-nums [overflow-wrap:anywhere] sm:text-[26px]", tone === "danger" && "text-danger")}>{value}</p>
      {hint && <p className="mt-2 text-[12.5px] leading-snug text-ink-2">{hint}</p>}
      {children}
    </div>
  );
}

// ---------- reply-by ----------

type Sla = { text: string; tone: "danger" | "warning" | "neutral" | "success"; title?: string };

function sla(t: TicketRow, now: number): Sla | null {
  if (t.first_response_at) {
    return { text: `Answered in ${span(ms(t.first_response_at) - ms(t.created_at))}`, tone: "success", title: `First reply ${fmtDateTime(t.first_response_at)}` };
  }
  if (!isOpen(t) || !t.first_response_due) return null;
  const left = now ? ms(t.first_response_due) - now : t.overdue ? -60_000 : 60 * 60_000;
  const title = `Reply by ${fmtDateTime(t.first_response_due)}`;
  if (t.overdue || left <= 0) return { text: `Overdue by ${span(Math.min(left, -60_000))}`, tone: "danger", title };
  return { text: `Reply within ${span(left)}`, tone: left < 15 * 60_000 ? "warning" : "neutral", title };
}

const SLA_TONE = {
  danger: "bg-danger text-white",
  warning: "bg-warning-50 text-warning",
  neutral: "bg-surface text-ink-2",
  success: "bg-success-50 text-success",
};

function SlaChip({ t, now }: { t: TicketRow; now: number }) {
  const s = sla(t, now);
  if (!s) return null;
  const Icon = s.tone === "success" ? CircleCheck : s.tone === "danger" ? BellRing : Timer;
  return (
    <span title={s.title} className={cn("inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[12px] font-semibold whitespace-nowrap", SLA_TONE[s.tone])}>
      <Icon className="size-3.5" /> {s.text}
    </span>
  );
}

function SourceBadge({ channel }: { channel: string }) {
  if (channel === "host") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-line-soft bg-white px-2 py-0.5 text-xs font-semibold text-ink-2">
        <Headset className="size-3.5" /> Logged by the team
      </span>
    );
  }
  return <ChannelBadge channel={channel} />;
}

function TaskChip({ task }: { task: NonNullable<TicketRow["task"]> }) {
  return (
    <Link
      href="/host/tasks"
      className="inline-flex max-w-full items-center gap-1 rounded-full border border-line-soft bg-white px-2.5 py-0.5 text-[12px] font-semibold text-ink-2 hover:border-line hover:text-ink"
    >
      <Wrench className="size-3.5 shrink-0" />
      <span className="truncate">
        Work order #{task.id} · {humanize(task.status)}
        {task.assignee && ` · ${task.assignee}`}
      </span>
    </Link>
  );
}

function RatingChip({ rating, comment }: { rating: number; comment?: string }) {
  return (
    <span className={cn("inline-flex max-w-full items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[12px] font-semibold", rating <= 2 ? "bg-danger-50 text-danger" : "bg-surface text-ink")}>
      <Stars rating={rating} size={12} />
      <span className="tabular-nums">{rating}/5</span>
      {comment && <span className="truncate font-normal text-ink-2">“{comment}”</span>}
    </span>
  );
}

function escalationText(level: number) {
  return level >= 2 ? "Escalated to a phone call" : level === 1 ? "SMS reminder sent to you" : "";
}

// ---------- list card ----------

function TicketCard({ t, now, onOpen, onCall, calling }: { t: TicketRow; now: number; onOpen: () => void; onCall: () => void; calling: boolean }) {
  const cat = CATEGORY[t.category] ?? CATEGORY.other;
  const open = isOpen(t);
  const pr = PRIORITY[t.priority] ?? PRIORITY.normal;
  const stripe = !open ? "bg-line" : t.overdue || t.priority === "urgent" ? "bg-danger" : t.first_response_at ? "bg-ocean-500" : t.priority === "high" ? "bg-brand-500" : "bg-warning";
  const iconCls = !open ? "bg-surface text-ink-3" : t.overdue ? "bg-danger text-white" : t.first_response_at ? "bg-ocean-50 text-ocean-600" : "bg-brand-50 text-brand-600";
  const name = guestName(t);
  const showDescription = !!t.description.trim() && t.description.trim() !== t.subject.trim();
  return (
    <li className={cn("relative overflow-hidden rounded-2xl border bg-white", t.overdue ? "border-danger/40 shadow-soft" : "border-line-soft", !open && "opacity-90")}>
      <span className={cn("absolute inset-y-0 left-0 w-1", stripe)} aria-hidden />
      <div className="flex flex-wrap gap-x-4 gap-y-3 py-4 pr-4 pl-5 sm:pr-5 sm:pl-6">
        <span className={cn("hidden size-11 shrink-0 place-items-center rounded-full sm:grid", iconCls, t.overdue && "animate-pulse-ring")}>
          <cat.icon className="size-5" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="font-mono text-[13px] font-bold text-ink">{t.ref}</span>
            <span className="text-[14.5px] font-bold">{t.category_label}</span>
            <Badge tone={pr.tone}>{pr.label}</Badge>
            <StatusBadge status={t.status} label={t.status_label} />
          </p>
          <button type="button" onClick={onOpen} className="mt-1 block max-w-full text-left text-[15px] leading-snug font-semibold text-ink [overflow-wrap:anywhere] hover:underline">
            {t.subject}
          </button>
          {showDescription && <p className="mt-1.5 line-clamp-2 rounded-lg bg-surface px-3 py-2 text-[13.5px] text-ink-2 italic [overflow-wrap:anywhere]">“{t.description}”</p>}
          {t.recording_url && (
            <audio controls preload="none" src={t.recording_url} className="mt-2 h-10 w-full max-w-sm" aria-label={`Voice message for ${t.ref}`}>
              <a href={t.recording_url}>Listen to the voice message</a>
            </audio>
          )}
          <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[12.5px] text-ink-2">
            <SourceBadge channel={t.channel} />
            <span className="inline-flex min-w-0 items-center gap-1 font-medium text-ink">
              <UserRound className="size-3.5 shrink-0 text-ink-2" />
              <span className="[overflow-wrap:anywhere]">{name}</span>
            </span>
            {realName(t) && (
              <a href={`tel:${t.phone}`} className="tabular-nums hover:text-ink hover:underline">
                {fmtPhone(t.phone)}
              </a>
            )}
            {t.booking && (
              <Link href={reservationHref(t.booking)} className="font-mono font-semibold text-ink hover:underline">
                {t.booking}
              </Link>
            )}
            {t.unit && <span>{t.unit}</span>}
            <span title={fmtDateTime(t.created_at)}>{ago(t.created_at)}</span>
          </p>
          <div className="mt-2.5 flex flex-wrap items-center gap-2">
            <SlaChip t={t} now={now} />
            {open && !t.first_response_at && t.escalation_level > 0 && (
              <span className="inline-flex items-center gap-1 text-[12px] font-semibold text-danger">
                <BellRing className="size-3.5" /> {escalationText(t.escalation_level)}
              </span>
            )}
            {t.task && <TaskChip task={t.task} />}
            {t.rating != null && <RatingChip rating={t.rating} comment={t.rating_comment} />}
          </div>
          {!open && t.resolution && (
            <p className="mt-2 text-[13px] text-ink-2 [overflow-wrap:anywhere]">
              <b className="font-semibold text-ink">Resolved:</b> {t.resolution}
            </p>
          )}
        </div>
        <div className="flex w-full shrink-0 flex-wrap items-start gap-2 sm:w-auto sm:flex-col sm:items-stretch">
          <Button variant={open ? "dark" : "soft"} size="sm" onClick={onOpen}>
            {open ? (
              <>
                <Reply className="size-4" /> Reply
              </>
            ) : (
              "View"
            )}
          </Button>
          <Button variant="soft" size="sm" loading={calling} onClick={onCall}>
            {!calling && <PhoneCall className="size-4" />} Call guest
          </Button>
        </div>
      </div>
    </li>
  );
}

// ---------- detail sheet ----------

const EVENT: Record<TicketEvent["kind"], { icon: LucideIcon; label: string; cls: string }> = {
  created: { icon: Inbox, label: "Request opened", cls: "bg-brand-50 text-brand-600" },
  guest: { icon: MessageSquare, label: "Guest wrote", cls: "bg-brand-50 text-brand-600" },
  reply: { icon: Reply, label: "Reply sent by SMS", cls: "bg-ocean-50 text-ocean-600" },
  note: { icon: StickyNote, label: "Note", cls: "bg-surface text-ink-2" },
  status: { icon: CircleCheck, label: "Status", cls: "bg-success-50 text-success" },
  call: { icon: PhoneCall, label: "Call", cls: "bg-[#f3e8ff] text-[#7c3aed]" },
  escalated: { icon: BellRing, label: "Escalated", cls: "bg-danger-50 text-danger" },
  rating: { icon: Star, label: "Guest rated it", cls: "bg-warning-50 text-warning" },
  task: { icon: Wrench, label: "Work order", cls: "bg-surface text-ink-2" },
};

function TicketSheet({ id, row }: { id: number; row?: TicketRow }) {
  const qc = useQueryClient();
  const invalidate = useInvalidateHost();
  const { data: settings } = useHostSettings();
  const now = useNow(30_000);
  const key = ["host", "support", "ticket", id];
  const { data: t, error: fetchError, refetch, isPlaceholderData } = useQuery({
    queryKey: key,
    queryFn: () => get<TicketDetail>(`/api/host/support/tickets/${id}`),
    placeholderData: row ? { ...row, events: [] } : undefined,
    refetchInterval: 10_000,
    retry: (n, e) => !(e instanceof ApiError && e.status === 404) && n < 2,
  });
  const error = fetchError instanceof ApiError && fetchError.status === 404 ? new Error(`There's no ticket T${id}.`) : fetchError;
  const [reply, setReply] = React.useState("");
  const [resolving, setResolving] = React.useState(false);
  const [note, setNote] = React.useState("");

  const apply = (d: TicketDetail) => {
    qc.setQueryData(key, d);
    invalidate();
  };
  const send = useMutation({
    mutationFn: (text: string) => post<TicketDetail>(`/api/host/support/tickets/${id}/reply`, { text }),
    onSuccess: (d) => {
      toast.success(`Reply sent to ${firstName(d)} by SMS`);
      setReply("");
      apply(d);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const resolve = useMutation({
    mutationFn: (note: string) => post<TicketDetail>(`/api/host/support/tickets/${id}/resolve`, { note }),
    onSuccess: (d) => {
      toast.success(`${d.ref} resolved`, { description: d.category === "issue" ? undefined : `${humanize(firstName(d))} is told by SMS and asked to rate it 1–5.` });
      setResolving(false);
      apply(d);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const reopen = useMutation({
    mutationFn: () => post<TicketDetail>(`/api/host/support/tickets/${id}/reopen`),
    onSuccess: (d) => {
      toast.success(`${d.ref} reopened`);
      apply(d);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const call = useMutation({
    mutationFn: () => post<TicketCallResult>(`/api/host/support/tickets/${id}/call`),
    onSuccess: (r) => {
      callToast(r);
      apply(r.ticket);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  if (!t) {
    return (
      <SheetContent title="Ticket" width="max-w-xl">
        <div className="p-6">{error ? <ErrorBlock error={error} retry={refetch} /> : <LoadingBlock rows={5} />}</div>
      </SheetContent>
    );
  }

  const open = isOpen(t);
  const text = reply.trim();
  const hostName = settings?.host_name || "Amina";
  const submit = () => {
    if (text && !send.isPending) send.mutate(text);
  };
  const showDescription = !!t.description.trim() && t.description.trim() !== t.subject.trim();

  const footer = (
    <div className="space-y-2.5">
      <Textarea
        value={reply}
        onChange={(e) => setReply(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            submit();
          }
        }}
        rows={2}
        maxLength={600}
        placeholder={`Reply to ${firstName(t)} by SMS…`}
        aria-label="Reply by SMS"
        className="min-h-20"
      />
      {text && <SmsMeter text={`${hostName} (${t.ref}): ${text}`} onFix={() => setReply(toGsm(reply))} />}
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="soft" size="sm" loading={call.isPending} onClick={() => call.mutate()}>
          {!call.isPending && <PhoneCall className="size-4" />} Call guest
        </Button>
        {open ? (
          <Button
            variant="soft"
            size="sm"
            onClick={() => {
              setNote("");
              setResolving(true);
            }}
          >
            <CircleCheck className="size-4" /> Resolve
          </Button>
        ) : (
          <Button variant="soft" size="sm" loading={reopen.isPending} onClick={() => reopen.mutate()}>
            {!reopen.isPending && <RotateCcw className="size-4" />} Reopen
          </Button>
        )}
        <Button variant="dark" size="sm" className="ml-auto" disabled={!text} loading={send.isPending} onClick={submit}>
          {!send.isPending && <Send className="size-4" />} Send
        </Button>
      </div>
    </div>
  );

  return (
    <SheetContent title={`${t.ref} · ${t.category_label}`} width="max-w-xl" footer={footer}>
      <div className="space-y-6 p-5 sm:p-6">
        <div>
          <div className="flex flex-wrap items-center gap-1.5">
            <StatusBadge status={t.status} label={t.status_label} />
            <Badge tone={PRIORITY[t.priority]?.tone ?? "neutral"}>{PRIORITY[t.priority]?.label ?? humanize(t.priority)} priority</Badge>
            <SourceBadge channel={t.channel} />
          </div>
          <h3 className="mt-3 text-lg leading-snug font-bold [overflow-wrap:anywhere]">{t.subject}</h3>
          {showDescription && <p className="mt-2 rounded-xl bg-surface px-4 py-3 text-[14px] leading-relaxed whitespace-pre-wrap text-ink [overflow-wrap:anywhere]">{t.description}</p>}
          {t.recording_url && (
            <div className="mt-3">
              <p className="mb-1.5 text-[13px] font-semibold">Voice message</p>
              <audio controls preload="none" src={t.recording_url} className="h-10 w-full">
                <a href={t.recording_url}>Listen to the voice message</a>
              </audio>
            </div>
          )}
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <SlaChip t={t} now={now} />
            {open && !t.first_response_at && t.escalation_level > 0 && (
              <span className="inline-flex items-center gap-1 text-[12px] font-semibold text-danger">
                <BellRing className="size-3.5" /> {escalationText(t.escalation_level)}
              </span>
            )}
            {t.task && <TaskChip task={t.task} />}
            {t.rating != null && <RatingChip rating={t.rating} comment={t.rating_comment} />}
          </div>
        </div>

        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 rounded-xl border border-line-soft p-4 text-sm">
          <div className="min-w-0">
            <dt className="text-[12.5px] text-ink-2">Guest</dt>
            <dd className="mt-0.5 font-semibold [overflow-wrap:anywhere]">{realName(t) ?? <span className="font-normal text-ink-3">No name on file</span>}</dd>
            <dd>
              <a href={`tel:${t.phone}`} className="text-[13px] text-ink-2 tabular-nums hover:text-ink hover:underline">
                {fmtPhone(t.phone)}
              </a>
            </dd>
          </div>
          <div className="min-w-0">
            <dt className="text-[12.5px] text-ink-2">Stay</dt>
            <dd className="mt-0.5 font-semibold">
              {t.booking ? (
                <Link href={reservationHref(t.booking)} className="font-mono hover:underline">
                  {t.booking}
                </Link>
              ) : (
                <span className="font-normal text-ink-3">No booking linked</span>
              )}
            </dd>
            {t.unit && <dd className="text-[13px] text-ink-2">{t.unit}</dd>}
          </div>
          <div>
            <dt className="text-[12.5px] text-ink-2">Opened</dt>
            <dd className="mt-0.5 font-medium">{fmtDateTime(t.created_at)}</dd>
          </div>
          <div>
            <dt className="text-[12.5px] text-ink-2">{t.resolved_at ? "Resolved" : "Reply by"}</dt>
            <dd className="mt-0.5 font-medium">{fmtDateTime(t.resolved_at ?? t.first_response_due) || "—"}</dd>
          </div>
        </dl>

        {t.resolution && (
          <div className="rounded-xl border-l-2 border-success bg-success-50/60 px-4 py-3">
            <p className="text-[12px] font-bold tracking-wide text-success uppercase">Resolution</p>
            <p className="mt-1 text-[14px] leading-relaxed text-ink [overflow-wrap:anywhere]">{t.resolution}</p>
          </div>
        )}

        <section>
          <h4 className="mb-3 text-[13px] font-semibold">Timeline</h4>
          {isPlaceholderData ? (
            error ? (
              <ErrorBlock error={error} retry={refetch} />
            ) : (
              <LoadingBlock rows={3} />
            )
          ) : (
            <ol>
              {t.events.map((e, i) => (
                <TimelineItem key={e.id} e={e} last={i === t.events.length - 1} />
              ))}
            </ol>
          )}
        </section>
      </div>

      <ConfirmDialog
        open={resolving}
        onOpenChange={setResolving}
        title={`Resolve ${t.ref}`}
        confirmLabel="Mark resolved"
        loading={resolve.isPending}
        onConfirm={() => resolve.mutate(note.trim())}
      >
        <p>
          {t.category === "issue"
            ? "The ticket closes with its work order's note."
            : `${humanize(firstName(t))} gets an SMS that it's resolved, with your note, and is asked to rate the help 1–5.`}
        </p>
        <Field label="What was done? (optional, included in the SMS)" hint={`${note.length}/300`}>
          <Textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} maxLength={300} placeholder="e.g. Spoke to the neighbours — the music stops at 10pm from tonight." autoFocus />
        </Field>
      </ConfirmDialog>
    </SheetContent>
  );
}

function TimelineItem({ e, last }: { e: TicketEvent; last: boolean }) {
  const meta = EVENT[e.kind] ?? EVENT.note;
  const reopened = e.kind === "status" && e.text.startsWith("Reopened");
  const Icon = reopened ? RotateCcw : meta.icon;
  // the console records its own actions as "web"/"host": the actor's name already says who did it
  const showChannel = !!e.channel && e.kind !== "reply" && !(e.actor && (e.channel === "web" || e.channel === "host"));
  const bubble =
    e.kind === "reply"
      ? "rounded-xl rounded-tl-sm bg-ocean-50 px-3 py-2 text-ink"
      : e.kind === "created" || e.kind === "guest"
        ? "rounded-xl rounded-tl-sm bg-surface px-3 py-2 text-ink"
        : "text-ink-2";
  return (
    <li className="relative flex gap-3 pb-5 last:pb-0">
      {!last && <span className="absolute top-9 bottom-1 left-4 w-px bg-line-soft" aria-hidden />}
      <span className={cn("grid size-8 shrink-0 place-items-center rounded-full", reopened ? "bg-warning-50 text-warning" : meta.cls)}>
        <Icon className="size-4" />
      </span>
      <div className="min-w-0 flex-1 pt-1">
        <p className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-[13px]">
          <b className="font-semibold text-ink">{reopened ? "Reopened" : meta.label}</b>
          {e.actor && <span className="text-ink-2">by {e.actor}</span>}
          {showChannel && <span className="text-ink-2">· {CHANNEL_LABEL[e.channel] ?? humanize(e.channel)}</span>}
          <time dateTime={e.created_at} title={fmtDateTime(e.created_at)} className="ml-auto text-[12px] whitespace-nowrap text-ink-3">
            {ago(e.created_at)}
          </time>
        </p>
        {!reopened && e.text && <p className={cn("mt-1 text-[14px] leading-relaxed whitespace-pre-wrap [overflow-wrap:anywhere]", bubble)}>{e.text}</p>}
      </div>
    </li>
  );
}

// ---------- new ticket ----------

function NewTicketButton({ onCreated }: { onCreated: (t: TicketDetail) => void }) {
  const [open, setOpen] = React.useState(false);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="dark">
          <Plus className="size-4" strokeWidth={2.5} /> New ticket
        </Button>
      </DialogTrigger>
      {open && (
        <NewTicketForm
          onDone={(t) => {
            setOpen(false);
            onCreated(t);
          }}
        />
      )}
    </Dialog>
  );
}

function NewTicketForm({ onDone }: { onDone: (t: TicketDetail) => void }) {
  const invalidate = useInvalidateHost();
  const [phone, setPhone] = React.useState("");
  const [category, setCategory] = React.useState<TicketCategory>("complaint");
  const [subject, setSubject] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [booking, setBooking] = React.useState("");
  const create = useMutation({
    mutationFn: () =>
      post<TicketDetail>("/api/host/support/tickets", {
        phone: phone.trim(),
        category,
        subject: subject.trim(),
        description: description.trim(),
        booking: booking.trim() || undefined,
      }),
    onSuccess: (t) => {
      toast.success(`${t.ref} opened`, { description: "The guest got the reference and reply-by time by SMS." });
      invalidate();
      onDone(t);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const ready = !!phone.trim() && !!(subject.trim() || description.trim());
  return (
    <DialogContent
      size="md"
      title="New ticket"
      footer={
        <div className="flex justify-end gap-2">
          <DialogClose asChild>
            <Button variant="ghost">Cancel</Button>
          </DialogClose>
          <Button type="submit" form="new-ticket" variant="dark" loading={create.isPending} disabled={!ready}>
            Open ticket
          </Button>
        </div>
      }
    >
      <form
        id="new-ticket"
        className="grid grid-cols-1 gap-4 px-6 py-5 sm:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (ready) create.mutate();
        }}
      >
        <p className="text-[14px] text-ink-2 sm:col-span-2">For a complaint or request taken by phone or at the gate. The guest gets the reference by SMS and can follow it up on any channel.</p>
        <Field label="Guest's phone">
          <Input type="tel" inputMode="tel" autoComplete="off" placeholder="0712 345 678 or +44…" value={phone} onChange={(e) => setPhone(e.target.value)} autoFocus />
        </Field>
        <Field label="What it's about">
          <Select value={category} onChange={(e) => setCategory(e.target.value as TicketCategory)}>
            {NEW_CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {CATEGORY[c].label}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Subject" className="sm:col-span-2" hint="One line — it's quoted in the guest's SMS.">
          <Input maxLength={140} placeholder={CATEGORY[category].placeholder} value={subject} onChange={(e) => setSubject(e.target.value)} />
        </Field>
        <Field label="Details (optional)" className="sm:col-span-2">
          <Textarea className="min-h-20" maxLength={1000} placeholder="What the guest said, what they'd like done…" value={description} onChange={(e) => setDescription(e.target.value)} />
        </Field>
        <Field label="Booking (optional)" hint="Must be this guest's. Left blank, their current stay is linked.">
          <Input className="font-mono uppercase" placeholder="AMS-1234" value={booking} onChange={(e) => setBooking(e.target.value.toUpperCase())} />
        </Field>
      </form>
    </DialogContent>
  );
}
