"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Ban, Banknote, CalendarCheck, CalendarPlus, ChevronRight, CircleCheck, CircleX, Clock, Coffee, CreditCard, Fingerprint, Hourglass, IdCard,
  KeyRound, Landmark, LogOut, type LucideIcon, Mail, MapPin, MessageSquare, Phone, Repeat, RotateCcw, Send, ShieldAlert, ShieldCheck,
  Smartphone, Sparkles, TimerOff, Undo2, Wallet, Wifi,
} from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { usePayOptions } from "@/components/providers";
import { ChannelBadge, ErrorBlock, KeyValue, Section, StatusBadge } from "@/components/host/common";
import { Icon } from "@/components/icon";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { Field, Input, Select, Textarea } from "@/components/ui/input";
import { Badge, EmptyState, Skeleton } from "@/components/ui/misc";
import { ApiError, get, patch, post } from "@/lib/api";
import { ago, CHANNEL_LABEL, fmtDate, fmtDateTime, hhmm, kes, plural, STATUS_TONE } from "@/lib/format";
import type { Trip } from "@/lib/types";
import { cn } from "@/lib/utils";

import { ConfirmAction, Countdown, Flag, GuestAvatar, Overline, RiskChip } from "./bits";
import { countryName, displayName, fmtPhone, kenyaDate, LANGUAGES, smsSegments, useHostAction, useNow } from "./lib";

export function ReservationView({ refId }: { refId: string }) {
  const ref = decodeURIComponent(refId).toUpperCase();
  const q = useQuery({
    queryKey: ["host", "ops", "reservation", ref],
    queryFn: () => get<Trip>(`/api/host/reservations/${encodeURIComponent(ref)}`),
    refetchInterval: 10_000,
    retry: (n, e) => !(e instanceof ApiError && e.status === 404) && n < 1,
  });

  if (q.error && !q.data) {
    if (q.error instanceof ApiError && q.error.status === 404) {
      return (
        <EmptyState
          icon={<CalendarCheck className="size-5" />}
          title={`We can't find ${ref}`}
          action={
            <Button asChild variant="dark">
              <Link href="/host/reservations">Back to reservations</Link>
            </Button>
          }
        >
          Check the reference — it looks like AMS-1234.
        </EmptyState>
      );
    }
    return <ErrorBlock error={q.error} retry={() => q.refetch()} />;
  }
  if (!q.data) return <DetailSkeleton />;
  const t = q.data;

  return (
    <div>
      <Header t={t} />
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_360px] xl:grid-cols-[minmax(0,1fr)_400px]">
        <div className="min-w-0 space-y-6">
          <StatusBanner t={t} />
          <GuestCard t={t} />
          <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
            <ScreeningCard t={t} />
            <NotesCard key={t.ref} t={t} />
          </div>
          <StayCard t={t} />
          <ChangesCard t={t} />
          <AddonsCard t={t} />
          <RegisterCard t={t} />
          <CodesCard t={t} />
          <TimelineCard t={t} />
        </div>
        <aside className="space-y-4 lg:sticky lg:top-6 lg:max-h-[calc(100dvh-3rem)] lg:self-start lg:overflow-y-auto lg:[scrollbar-width:thin]">
          <PaymentCard t={t} />
          <ActionsCard t={t} />
        </aside>
      </div>
    </div>
  );
}

function DetailSkeleton() {
  return (
    <div>
      <div className="mb-6 flex items-center gap-4">
        <Skeleton className="size-20 rounded-xl" />
        <div className="flex-1 space-y-2">
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-7 w-64" />
          <Skeleton className="h-4 w-96 max-w-full" />
        </div>
      </div>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_360px] xl:grid-cols-[minmax(0,1fr)_400px]">
        <div className="space-y-6">
          <Skeleton className="h-56 rounded-2xl" />
          <Skeleton className="h-40 rounded-2xl" />
          <Skeleton className="h-64 rounded-2xl" />
        </div>
        <Skeleton className="h-[520px] rounded-2xl" />
      </div>
    </div>
  );
}

// ---------- header & banners ----------

function Header({ t }: { t: Trip }) {
  const g = t.guest;
  const name = displayName(g?.name, g?.phone);
  return (
    <div className="mb-6">
      <Link href="/host/reservations" className="mb-3 inline-block text-[13px] font-semibold text-ink-2 hover:text-ink">
        ← Reservations
      </Link>
      <div className="flex flex-wrap items-start gap-4">
        {t.unit.photos[0] ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={t.unit.photos[0]} alt="" className="size-16 shrink-0 rounded-xl bg-surface object-cover sm:size-[76px]" />
        ) : (
          <span className="size-16 shrink-0 rounded-xl bg-surface sm:size-[76px]" />
        )}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-[13px] font-semibold text-ink-2">{t.ref}</span>
            <StatusBadge status={t.status} label={t.status_label} />
            <ChannelBadge channel={t.channel} />
          </div>
          <h1 className="mt-1 flex items-center gap-2 text-[26px] leading-tight font-bold tracking-tight">
            <span className="truncate">{name}</span>
            <Flag code={g?.nationality} className="text-[22px]" />
          </h1>
          <p className="mt-1 text-[15px] text-ink-2">
            <span className="font-semibold text-ink">{t.unit.name}</span> · {t.unit.area} · {fmtDate(t.check_in)} → {fmtDate(t.check_out)} ·{" "}
            {plural(t.nights, "night")} · {plural(t.guests, "guest")}
          </p>
          <p className="mt-0.5 text-[13px] text-ink-3">
            Booked {ago(t.created_at)} via {t.channel_label}
          </p>
        </div>
        {g && (
          <div className="flex w-full gap-2 sm:w-auto [&>*]:flex-1 sm:[&>*]:flex-none">
            <Button asChild variant="soft">
              <a href={`tel:${g.phone}`}>
                <Phone className="size-4" /> Call
              </a>
            </Button>
            <MessageDialog
              t={t}
              trigger={
                <Button variant="dark">
                  <MessageSquare className="size-4" /> Message
                </Button>
              }
            />
          </div>
        )}
      </div>
    </div>
  );
}

function StatusBanner({ t }: { t: Trip }) {
  if (t.status === "held" && t.hold_expires_at) {
    return (
      <Banner tone="warning" icon={Hourglass}>
        Waiting for payment of {kes(t.price.amount_due_now || t.price.total)} — the hold releases in <Countdown to={t.hold_expires_at} className="text-inherit" />.
      </Banner>
    );
  }
  if (t.status === "cancelled" || t.status === "refund_due") {
    const c = t.cancel_info;
    return (
      <Banner tone="danger" icon={Ban}>
        Cancelled{c?.by ? ` by ${c.by}` : ""}
        {c?.cancelled_at ? ` on ${fmtDateTime(c.cancelled_at)}` : ""}
        {c?.reason ? ` — “${c.reason}”` : ""}.
        {t.price.amount_refunded > 0 && ` ${kes(t.price.amount_refunded)} refunded.`}
      </Banner>
    );
  }
  if (t.status === "checked_in") {
    return (
      <Banner tone="success" icon={CircleCheck}>
        In the house — checks out {fmtDate(t.check_out)} by {hhmm(t.checkin.checkout_time)}.
      </Banner>
    );
  }
  return null;
}

function Banner({ tone, icon: I, children }: { tone: "warning" | "danger" | "success"; icon: LucideIcon; children: React.ReactNode }) {
  const tones = { warning: "bg-warning-50 text-warning", danger: "bg-danger-50 text-danger", success: "bg-success-50 text-success" };
  return (
    <div className={cn("flex items-start gap-3 rounded-2xl px-5 py-3.5 text-sm font-medium", tones[tone])}>
      <I className="mt-0.5 size-4 shrink-0" />
      <p>{children}</p>
    </div>
  );
}

// ---------- guest ----------

function GuestCard({ t }: { t: Trip }) {
  const g = t.guest;
  const verify = useHostAction(() => post(`/api/host/reservations/${t.ref}/verify-id`), { success: "ID marked as verified in person" });
  if (!g) return null;
  const name = displayName(g.name, g.phone);
  return (
    <Section
      title="Guest"
      action={
        <Link href={`/host/guests?guest=${g.id}`} className="text-[13px] font-semibold text-ink-2 hover:text-ink">
          Guest profile →
        </Link>
      }
    >
      <div className="flex flex-wrap items-start gap-4">
        <GuestAvatar name={g.name} size={56} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-lg font-bold">{name}</p>
            {g.stays > 1 ? <Badge tone="ocean">Returning · {plural(g.stays, "stay")}</Badge> : <Badge>First stay</Badge>}
            {g.blocked && <Badge tone="danger">Do not host</Badge>}
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
            <a href={`tel:${g.phone}`} className="font-medium tabular-nums hover:underline">
              {fmtPhone(g.phone)}
            </a>
            <a href={`tel:${g.phone}`} className="inline-flex items-center gap-1 text-[13px] font-semibold text-ocean-600 hover:underline">
              <Phone className="size-3.5" /> Call
            </a>
            <a href={`sms:${g.phone}`} className="inline-flex items-center gap-1 text-[13px] font-semibold text-ocean-600 hover:underline">
              <MessageSquare className="size-3.5" /> SMS
            </a>
            {g.email && (
              <a href={`mailto:${g.email}`} className="inline-flex items-center gap-1 text-[13px] text-ink-2 hover:underline">
                <Mail className="size-3.5" /> {g.email}
              </a>
            )}
          </div>
        </div>
      </div>

      <dl className="mt-5 grid grid-cols-1 gap-x-8 gap-y-4 border-t border-line-soft pt-5 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-[13px] text-ink-2">Nationality</dt>
          <dd className="mt-0.5 flex items-center gap-1.5 font-medium">
            {g.nationality ? (
              <>
                <Flag code={g.nationality} /> {countryName(g.nationality)}
              </>
            ) : (
              <span className="text-ink-3">Not given</span>
            )}
          </dd>
        </div>
        <div>
          <dt className="text-[13px] text-ink-2">Language</dt>
          <dd className="mt-0.5 font-medium">{LANGUAGES[g.lang] ?? g.lang ?? "English"}</dd>
        </div>
        <div className="sm:col-span-2">
          <dt className="text-[13px] text-ink-2">Identity document</dt>
          <dd className="mt-1 flex flex-wrap items-center gap-2 font-medium">
            {g.id_last4 ? (
              <span className="inline-flex items-center gap-1.5">
                <IdCard className="size-4 text-ink-2" /> {g.id_type || "ID"} <span className="font-mono text-[13px]">{g.id_last4}</span>
              </span>
            ) : (
              <span className="text-ink-3">No ID on file yet</span>
            )}
            {g.id_verified ? (
              <Badge tone="success">
                <ShieldCheck className="size-3" /> Verified in person
              </Badge>
            ) : (
              <Button size="sm" variant="soft" loading={verify.isPending} onClick={() => verify.mutate()}>
                <Fingerprint className="size-3.5" /> Verify ID in person
              </Button>
            )}
          </dd>
        </div>
        {g.tags.length > 0 && (
          <div className="sm:col-span-2">
            <dt className="text-[13px] text-ink-2">Tags</dt>
            <dd className="mt-1 flex flex-wrap gap-1.5">
              {g.tags.map((tag) => (
                <Badge key={tag}>{tag}</Badge>
              ))}
            </dd>
          </div>
        )}
        {g.notes && (
          <div className="sm:col-span-2">
            <dt className="text-[13px] text-ink-2">Guest notes</dt>
            <dd className="mt-1 rounded-xl bg-surface px-3.5 py-2.5 whitespace-pre-wrap">{g.notes}</dd>
          </div>
        )}
      </dl>
    </Section>
  );
}

const SIM_SWAP: Record<string, { label: string; tone: "neutral" | "ocean" | "success" | "danger" | "warning"; text: string }> = {
  "": { label: "Not checked yet", tone: "neutral", text: "Checked automatically before the door code is released." },
  Queued: { label: "Checking…", tone: "ocean", text: "Waiting for the mobile network to answer." },
  NoSwapDate: { label: "No recent SIM swap", tone: "success", text: "Safe to send the door code to this number." },
  Swapped: { label: "SIM recently swapped", tone: "danger", text: "Call the guest to verify before releasing the code." },
  Failed: { label: "Check failed", tone: "warning", text: "The network didn't answer — verify by phone if in doubt." },
};

function ScreeningCard({ t }: { t: Trip }) {
  const risk = t.risk ?? { score: 0, flags: [] };
  const level = risk.score >= 60 ? "High" : risk.score >= 40 ? "Medium" : "Low";
  const bar = risk.score >= 60 ? "bg-danger" : risk.score >= 40 ? "bg-warning" : "bg-success";
  const sim = SIM_SWAP[t.sim_swap_status ?? ""] ?? { label: t.sim_swap_status ?? "", tone: "neutral" as const, text: "" };
  return (
    <Section
      title={
        <span className="flex items-center gap-2">
          <ShieldAlert className="size-4 text-ink-2" /> Screening
        </span>
      }
      action={<RiskChip score={risk.score} always />}
    >
      <div className="flex items-baseline justify-between text-sm">
        <span className="font-semibold">{level} risk</span>
        <span className="text-ink-2 tabular-nums">{risk.score} / 100</span>
      </div>
      <div className="mt-2 h-2 overflow-hidden rounded-full bg-surface" role="meter" aria-valuenow={risk.score} aria-valuemin={0} aria-valuemax={100} aria-label="Risk score">
        <div className={cn("h-full rounded-full", bar)} style={{ width: `${Math.max(3, Math.min(100, risk.score))}%` }} />
      </div>
      {risk.flags.length ? (
        <ul className="mt-3 space-y-1.5 text-[13px]">
          {risk.flags.map((f) => (
            <li key={f.code} className="flex items-center gap-2">
              <span className="size-1.5 shrink-0 rounded-full bg-warning" /> {f.label}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-[13px] text-ink-2">No party or fraud signals on this booking.</p>
      )}
      <div className="mt-4 border-t border-line-soft pt-4">
        <div className="flex items-center justify-between gap-2">
          <span className="flex items-center gap-1.5 text-[13px] text-ink-2">
            <Smartphone className="size-3.5" /> SIM-swap check
          </span>
          <Badge tone={sim.tone}>{sim.label}</Badge>
        </div>
        {sim.text && <p className="mt-1.5 text-xs text-ink-3">{sim.text}</p>}
      </div>
    </Section>
  );
}

function NotesCard({ t }: { t: Trip }) {
  const saved = t.host_notes ?? "";
  const [value, setValue] = React.useState(saved);
  const dirty = value !== saved;
  const save = useHostAction(() => patch(`/api/host/reservations/${t.ref}`, { host_notes: value }), { success: "Notes saved" });
  return (
    <Section title="Private notes" action={dirty ? <span className="text-xs font-semibold text-warning">Unsaved</span> : null}>
      <Textarea
        aria-label="Private host notes"
        className="min-h-28 text-sm"
        placeholder="Only you and your team see these — gate codes given, late arrival agreed, anything to remember."
        value={value}
        onChange={(e) => setValue(e.target.value)}
      />
      <div className="mt-3 flex justify-end gap-2">
        {dirty && (
          <Button size="sm" variant="ghost" onClick={() => setValue(saved)}>
            Discard
          </Button>
        )}
        <Button size="sm" variant="dark" disabled={!dirty} loading={save.isPending} onClick={() => save.mutate()}>
          Save notes
        </Button>
      </div>
    </Section>
  );
}

// ---------- the stay ----------

const ARRIVAL_MODES: Record<string, string> = { flight: "Flight", sgr: "SGR train", car: "Car", bus: "Bus", ferry: "Ferry", local: "Already local" };

function StayCard({ t }: { t: Trip }) {
  const party = [plural(t.adults, "adult"), t.children ? plural(t.children, "child", "children") : "", t.infants ? plural(t.infants, "infant") : ""]
    .filter(Boolean)
    .join(" · ");
  return (
    <Section title="Stay details">
      <div className="grid grid-cols-1 gap-x-10 sm:grid-cols-2">
        <div className="divide-y divide-line-soft">
          <KeyValue label="Check-in">
            {fmtDate(t.check_in)} · from {hhmm(t.checkin.time)}
          </KeyValue>
          <KeyValue label="Check-out">
            {fmtDate(t.check_out)} · by {hhmm(t.checkin.checkout_time)}
          </KeyValue>
          <KeyValue label="Guests">{party}</KeyValue>
          <KeyValue label="Door access">{t.checkin.method}</KeyValue>
        </div>
        <div className="divide-y divide-line-soft">
          <KeyValue label="Arrival time">{t.arrival.eta || <span className="text-ink-3">Not shared yet</span>}</KeyValue>
          <KeyValue label="Arriving by">{t.arrival.mode ? (ARRIVAL_MODES[t.arrival.mode] ?? t.arrival.mode) : <span className="text-ink-3">—</span>}</KeyValue>
          <KeyValue label="Vehicle plate">
            {t.arrival.vehicle_plate ? <span className="font-mono">{t.arrival.vehicle_plate}</span> : <span className="text-ink-3">—</span>}
          </KeyValue>
          <KeyValue label="Trip purpose">{t.purpose ? t.purpose.replace(/_/g, " ") : <span className="text-ink-3">—</span>}</KeyValue>
        </div>
      </div>
      {t.arrival.special_requests && (
        <div className="mt-4 rounded-xl bg-sand-50 px-4 py-3 text-sm">
          <Overline className="mb-1 text-ink-2">Special requests</Overline>
          <p className="whitespace-pre-wrap">{t.arrival.special_requests}</p>
        </div>
      )}
      {t.checkin.address && (
        <p className="mt-4 flex items-start gap-2 text-[13px] text-ink-2">
          <MapPin className="mt-0.5 size-3.5 shrink-0" />
          <span>
            {t.checkin.address}
            {t.checkin.wifi_name && (
              <span className="ml-2 inline-flex items-center gap-1">
                · <Wifi className="size-3.5" /> {t.checkin.wifi_name}
              </span>
            )}
          </span>
        </p>
      )}
    </Section>
  );
}

function ChangesCard({ t }: { t: Trip }) {
  if (!t.changes?.length) return null;
  return (
    <Section title="Change requests" padded={false}>
      <ul className="divide-y divide-line-soft">
        {t.changes.map((c) => (
          <ChangeRow key={c.id} t={t} c={c} />
        ))}
      </ul>
    </Section>
  );
}

function ChangeRow({ t, c }: { t: Trip; c: NonNullable<Trip["changes"]>[number] }) {
  const decide = useHostAction((approve: boolean) => post(`/api/host/changes/${c.id}/decide`, { approve }), {
    success: (_, approve) => `Change ${approve ? "approved" : "declined"} — ${displayName(t.guest?.name, t.guest?.phone)} has been told by SMS`,
  });
  const guests = (s: { adults: number; children: number }) => plural(s.adults + s.children, "guest");
  return (
    <li className="flex flex-wrap items-center gap-3 px-5 py-4">
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold">
          {fmtDate(c.old.check_in, "d MMM")} – {fmtDate(c.old.check_out, "d MMM")} → {fmtDate(c.new.check_in, "d MMM")} – {fmtDate(c.new.check_out, "d MMM")}
          <span className="ml-2 font-medium text-ink-2 tabular-nums">{c.delta > 0 ? `+${kes(c.delta)}` : c.delta < 0 ? `−${kes(-c.delta)}` : "same price"}</span>
        </p>
        <p className="text-xs text-ink-2">
          {guests(c.old) !== guests(c.new) ? `${guests(c.old)} → ${guests(c.new)} · ` : ""}by {c.requested_by} · {ago(c.created_at)}
          {c.refund_amount > 0 && ` · refund ${kes(c.refund_amount)}`}
        </p>
      </div>
      {c.status === "pending_host" ? (
        <div className="flex gap-2">
          <Button size="sm" variant="soft" disabled={decide.isPending} loading={decide.isPending && decide.variables === false} onClick={() => decide.mutate(false)}>Decline</Button>
          <Button size="sm" variant="dark" disabled={decide.isPending} loading={decide.isPending && decide.variables === true} onClick={() => decide.mutate(true)}>Approve</Button>
        </div>
      ) : (
        <Badge tone={c.status === "applied" ? "success" : c.status === "pending_payment" ? "warning" : "neutral"}>{c.status_label}</Badge>
      )}
    </li>
  );
}

function AddonsCard({ t }: { t: Trip }) {
  if (!t.addons.length) return null;
  return (
    <Section title="Extras & requests" padded={false}>
      <ul className="divide-y divide-line-soft">
        {t.addons.map((a) => (
          <AddonRow key={a.id} addon={a} breakfast={a.code === "breakfast" ? t.breakfast?.summary : undefined} />
        ))}
      </ul>
    </Section>
  );
}

function AddonRow({ addon: a, breakfast }: { addon: Trip["addons"][number]; breakfast?: string }) {
  const decide = useHostAction((approve: boolean) => post(`/api/host/requests/${a.id}/decide`, { approve }), {
    success: (_, approve) => `${a.name} ${approve ? "approved" : "declined"} — the guest has been told by SMS`,
  });
  const details =
    breakfast ??
    Object.entries(a.details ?? {})
      .filter(([, v]) => v)
      .map(([k, v]) => `${k.replace(/_/g, " ")}: ${v}`)
      .join(" · ");
  return (
    <li className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center">
      <div className="flex min-w-0 flex-1 items-start gap-3">
        <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-surface text-ink">
          <Icon name={a.icon} className="size-[18px]" />
        </span>
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-2 text-sm font-semibold">
            {a.name}
            {a.quantity > 1 && <span className="font-normal text-ink-2">× {a.quantity}</span>}
            <StatusBadge status={a.status} />
          </p>
          {details && <p className="mt-0.5 text-[13px] text-ink-2">{details}</p>}
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-3 pl-12 sm:pl-0">
        <span className="text-sm font-semibold tabular-nums">{a.total ? kes(a.total) : "Free"}</span>
        {a.status === "requested" && (
          <>
            <Button size="sm" variant="soft" disabled={decide.isPending} loading={decide.isPending && decide.variables === false} onClick={() => decide.mutate(false)}>
              Decline
            </Button>
            <Button size="sm" variant="dark" disabled={decide.isPending} loading={decide.isPending && decide.variables === true} onClick={() => decide.mutate(true)}>
              Approve
            </Button>
          </>
        )}
      </div>
    </li>
  );
}

function RegisterCard({ t }: { t: Trip }) {
  return (
    <Section
      title="Guest register"
      padded={false}
      action={
        t.occupants.length && t.id_registered ? (
          <Badge tone="success">
            <CircleCheck className="size-3" /> TRA register complete
          </Badge>
        ) : t.require_id ? (
          <Badge tone="warning">ID needed before the door code</Badge>
        ) : null
      }
    >
      {t.occupants.length === 0 ? (
        <p className="px-5 py-6 text-center text-[13px] text-ink-2">
          No one registered yet. Guests add everyone staying from their trip page or by SMS — required for the TRA guest register.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-line-soft text-[12px] font-semibold tracking-wide text-ink-2 uppercase">
                <th className="px-5 py-2.5">Name</th>
                <th className="px-4 py-2.5">ID document</th>
                <th className="px-5 py-2.5">Nationality</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line-soft">
              {t.occupants.map((o) => (
                <tr key={o.id}>
                  <td className="px-5 py-3">
                    <span className="font-medium">{o.full_name}</span>
                    {o.is_lead && <Badge className="ml-2">Lead</Badge>}
                    {o.is_minor && <Badge className="ml-2" tone="ocean">Minor</Badge>}
                  </td>
                  <td className="px-4 py-3 text-ink-2">
                    {o.id_last4 ? (
                      <>
                        <span className="capitalize">{o.id_type.replace(/_/g, " ") || "ID"}</span> <span className="font-mono text-[13px]">{o.id_last4}</span>
                      </>
                    ) : (
                      <span className="text-ink-3">—</span>
                    )}
                  </td>
                  <td className="px-5 py-3">
                    {o.nationality ? (
                      <span className="inline-flex items-center gap-1.5">
                        <Flag code={o.nationality} /> {countryName(o.nationality)}
                      </span>
                    ) : (
                      <span className="text-ink-3">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Section>
  );
}

function CodesCard({ t }: { t: Trip }) {
  const codes = t.codes ?? [];
  return (
    <Section
      title={
        <span className="flex items-center gap-2">
          <KeyRound className="size-4 text-ink-2" /> Door codes
        </span>
      }
      padded={false}
    >
      {codes.length === 0 ? (
        <p className="px-5 py-6 text-center text-[13px] text-ink-2">A door code is generated when the booking is confirmed and sent on arrival day.</p>
      ) : (
        <ul className="divide-y divide-line-soft">
          {codes.map((c, i) => (
            <li key={`${c.code}-${i}`} className="flex flex-wrap items-center gap-x-5 gap-y-2 px-5 py-4">
              <span className={cn("font-mono text-xl font-semibold tracking-[0.2em] tabular-nums", c.revoked_at && "text-ink-3 line-through")}>{c.code}</span>
              <div className="min-w-0 flex-1 basis-40 text-[13px] text-ink-2">
                <p>
                  {fmtDateTime(c.valid_from)} → {fmtDateTime(c.valid_until)}
                </p>
                <p className="text-xs text-ink-3 capitalize">{c.provider}</p>
              </div>
              {c.revoked_at ? (
                <Badge>Revoked{c.revoke_reason ? ` · ${c.revoke_reason.replace(/_/g, " ")}` : ""}</Badge>
              ) : c.sent_at ? (
                <Badge tone="success" dot>
                  Active · sent {fmtDateTime(c.sent_at)}
                </Badge>
              ) : (
                <Badge tone="ocean" dot>
                  Ready · sends on arrival day
                </Badge>
              )}
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

const EVENT_ICON: Record<string, { icon: LucideIcon; cls: string }> = {
  held: { icon: Hourglass, cls: "bg-warning-50 text-warning" },
  confirmed: { icon: CalendarCheck, cls: "bg-ocean-50 text-ocean-600" },
  payment: { icon: Wallet, cls: "bg-success-50 text-success" },
  payment_requested: { icon: Smartphone, cls: "bg-surface text-ink-2" },
  payment_failed: { icon: CircleX, cls: "bg-danger-50 text-danger" },
  code_released: { icon: KeyRound, cls: "bg-ink text-white" },
  checked_out: { icon: LogOut, cls: "bg-surface text-ink-2" },
  cancelled: { icon: Ban, cls: "bg-danger-50 text-danger" },
  refund: { icon: Undo2, cls: "bg-warning-50 text-warning" },
  breakfast: { icon: Coffee, cls: "bg-brand-50 text-brand-600" },
  addon: { icon: Sparkles, cls: "bg-brand-50 text-brand-600" },
  eta: { icon: Clock, cls: "bg-ocean-50 text-ocean-600" },
  arrival: { icon: MapPin, cls: "bg-ocean-50 text-ocean-600" },
  expired: { icon: TimerOff, cls: "bg-surface text-ink-3" },
  reinstated: { icon: RotateCcw, cls: "bg-ocean-50 text-ocean-600" },
  register: { icon: IdCard, cls: "bg-surface text-ink-2" },
  airtime: { icon: Smartphone, cls: "bg-brand-50 text-brand-600" },
  data: { icon: Wifi, cls: "bg-ocean-50 text-ocean-600" },
};

function TimelineCard({ t }: { t: Trip }) {
  return (
    <Section title="Timeline">
      {t.timeline.length === 0 ? (
        <p className="text-center text-[13px] text-ink-2">Nothing has happened on this booking yet.</p>
      ) : (
        <ol className="relative">
          {t.timeline.map((e, i) => {
            const meta = EVENT_ICON[e.kind] ?? { icon: CircleCheck, cls: "bg-surface text-ink-2" };
            const last = i === t.timeline.length - 1;
            return (
              <li key={i} className="relative flex gap-4 pb-5 last:pb-0">
                {!last && <span className="absolute top-9 bottom-0 left-[17px] w-px bg-line-soft" aria-hidden />}
                <span className={cn("relative grid size-9 shrink-0 place-items-center rounded-full", meta.cls)}>
                  <meta.icon className="size-4" />
                </span>
                <div className="min-w-0 flex-1 pt-1.5">
                  <p className="text-sm font-medium">{e.text}</p>
                  <p className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-ink-2">
                    <time dateTime={e.created_at}>{fmtDateTime(e.created_at)}</time>
                    {e.channel && (
                      <span className="rounded-full border border-line-soft px-1.5 py-px text-[11px] font-semibold">{CHANNEL_LABEL[e.channel] ?? e.channel}</span>
                    )}
                  </p>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </Section>
  );
}

// ---------- money ----------

const METHOD_ICON: Record<string, LucideIcon> = { mpesa: Smartphone, card: CreditCard, cash: Banknote, bank: Landmark };

function PaymentCard({ t }: { t: Trip }) {
  const p = t.price;
  const payments = t.payments ?? [];
  const refunds = t.refunds ?? [];
  return (
    <section className="rounded-2xl border border-line-soft bg-white">
      <div className="flex items-center justify-between gap-3 border-b border-line-soft px-5 py-3.5">
        <h2 className="text-[15px] font-bold">Payment</h2>
        <div className="flex items-center gap-2">
          {["confirmed", "checked_in", "completed"].includes(t.status) && (
            <Link href={`/trips/${t.ref}/invoice`} className="text-[13px] font-semibold text-ink-2 underline-offset-4 hover:text-ink hover:underline">Invoice</Link>
          )}
          <Badge tone={p.payment_status === "paid" ? "success" : p.payment_status === "unpaid" ? "warning" : p.payment_status.includes("refund") ? "danger" : "ocean"}>
            {p.payment_status_label}
          </Badge>
        </div>
      </div>
      <div className="px-5 py-4">
        <ul className="space-y-2 text-sm">
          {p.lines.map((l, i) => (
            <li key={i} className="flex justify-between gap-4">
              <span className={cn("text-ink-2", l.amount < 0 && "text-success")}>{l.label}</span>
              <span className={cn("tabular-nums", l.amount < 0 && "text-success")}>
                {l.amount < 0 ? "−" : ""}
                {kes(Math.abs(l.amount))}
              </span>
            </li>
          ))}
        </ul>
        {!!p.pending?.length && (
          <ul className="mt-2 space-y-1 rounded-lg bg-surface px-3 py-2 text-[13px] text-ink-2">
            {p.pending.map((l, i) => (
              <li key={i} className="flex justify-between gap-4"><span>{l.label} · awaiting your OK</span><span className="tabular-nums">{kes(l.amount)}</span></li>
            ))}
          </ul>
        )}
        <div className="mt-3 space-y-1.5 border-t border-line-soft pt-3 text-sm">
          <div className="flex justify-between font-bold">
            <span>Total</span>
            <span className="tabular-nums">{kes(p.total)}</span>
          </div>
          <div className="flex justify-between text-ink-2">
            <span>Paid</span>
            <span className="tabular-nums">{kes(p.amount_paid)}</span>
          </div>
          {p.amount_refunded > 0 && (
            <div className="flex justify-between text-ink-2">
              <span>Refunded</span>
              <span className="tabular-nums">−{kes(p.amount_refunded)}</span>
            </div>
          )}
        </div>
        <div className={cn("mt-3 flex items-center justify-between rounded-xl px-4 py-3", p.balance_due > 0 ? "bg-warning-50" : "bg-surface")}>
          <div>
            <p className={cn("text-sm font-bold", p.balance_due > 0 ? "text-warning" : "text-ink")}>Balance due</p>
            {p.balance_due > 0 && p.payment_plan === "deposit" && <p className="text-xs text-ink-2">Due by {fmtDate(p.balance_due_date)}</p>}
          </div>
          <span className={cn("text-lg font-bold tabular-nums", p.balance_due > 0 ? "text-warning" : "text-ink")}>{kes(p.balance_due)}</span>
        </div>
      </div>

      {payments.length > 0 && (
        <div className="border-t border-line-soft px-5 py-4">
          <Overline className="mb-2">Payments</Overline>
          <ul className="space-y-2.5">
            {payments.map((pay) => {
              const M = METHOD_ICON[pay.method] ?? Wallet;
              return (
                <li key={pay.id} className="flex items-center gap-3 text-sm">
                  <span className="grid size-8 shrink-0 place-items-center rounded-full bg-surface text-ink-2">
                    <M className="size-4" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="font-medium">
                      {pay.method_label} · <span className="tabular-nums">{kes(pay.amount)}</span>
                    </p>
                    <p className="truncate text-xs text-ink-3">
                      {fmtDateTime(pay.created_at)}
                      {pay.reference ? ` · ${pay.reference}` : ""} · {pay.purpose}
                    </p>
                  </div>
                  <Badge tone={STATUS_TONE[pay.status] ?? "neutral"} className="capitalize">{pay.status}</Badge>
                </li>
              );
            })}
          </ul>
        </div>
      )}
      {refunds.length > 0 && (
        <div className="border-t border-line-soft px-5 py-4">
          <Overline className="mb-2">Refunds</Overline>
          <ul className="space-y-2.5">
            {refunds.map((r) => (
              <li key={r.id} className="flex items-center gap-3 text-sm">
                <span className="grid size-8 shrink-0 place-items-center rounded-full bg-warning-50 text-warning">
                  <Undo2 className="size-4" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="font-medium">
                    {r.method} · <span className="tabular-nums">{kes(r.amount)}</span>
                  </p>
                  <p className="truncate text-xs text-ink-3">
                    {fmtDateTime(r.created_at)}
                    {r.reference ? ` · ${r.reference}` : ""}
                  </p>
                </div>
                <Badge tone={STATUS_TONE[r.status] ?? "neutral"} className="capitalize">{r.status}</Badge>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

// ---------- actions ----------

function ActionRow({
  icon: I, label, hint, danger, ...props
}: { icon: LucideIcon; label: string; hint?: string; danger?: boolean } & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      title={hint}
      className={cn(
        "group flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left transition-colors outline-none hover:bg-surface focus-visible:ring-2 focus-visible:ring-ink disabled:pointer-events-none disabled:opacity-40",
        danger && "hover:bg-danger-50",
      )}
      {...props}
    >
      <span className={cn("grid size-8 shrink-0 place-items-center rounded-full", danger ? "bg-danger-50 text-danger" : "bg-surface text-ink group-hover:bg-white")}>
        <I className="size-4" />
      </span>
      <span className={cn("min-w-0 flex-1 truncate text-sm font-semibold", danger && "text-danger")}>{label}</span>
      <ChevronRight className="size-4 shrink-0 text-ink-3" />
    </button>
  );
}

function ActionsCard({ t }: { t: Trip }) {
  const g = t.guest;
  const name = displayName(g?.name, g?.phone);
  const active = ["held", "confirmed", "checked_in"].includes(t.status);
  const canRecord = !["cancelled", "expired", "refund_due"].includes(t.status);
  const requestBy = useRequestMethod(t);
  const now = useNow(60_000);
  const arrivalDay = now > 0 && kenyaDate(now) >= t.check_in;
  return (
    <section className="rounded-2xl border border-line-soft bg-white p-2">
      <h2 className="px-3 pt-2 pb-1 text-[15px] font-bold">Actions</h2>
      <MessageDialog t={t} trigger={<ActionRow icon={MessageSquare} label="Message guest" hint={`By SMS to ${fmtPhone(g?.phone)}`} />} />
      {active && (
        <RequestPaymentDialog
          t={t}
          trigger={
            <ActionRow
              icon={requestBy === "mpesa" ? Smartphone : CreditCard}
              label={t.price.balance_due > 0 ? `Request ${kes(t.price.balance_due)} ${requestBy === "mpesa" ? "by M-Pesa" : "by card"}` : "Request payment · nothing due"}
              hint={requestBy === "mpesa" ? "Sends an M-Pesa STK push to the guest's phone" : "Texts the guest a secure card payment link"}
              disabled={t.price.balance_due <= 0}
            />
          }
        />
      )}
      {canRecord && <RecordPaymentDialog t={t} trigger={<ActionRow icon={Banknote} label="Record cash or bank payment" hint="Taken at the door or by transfer" />} />}
      {t.status === "held" && (
        <ConfirmAction
          title="Confirm without payment?"
          confirmLabel="Confirm booking"
          success={`${t.ref} confirmed`}
          run={() => post(`/api/host/reservations/${t.ref}/confirm`)}
          trigger={(open) => <ActionRow icon={CalendarPlus} label="Confirm now, pay on arrival" hint="Stops the hold from expiring" onClick={open} />}
        >
          {name} keeps {t.unit.name} for {fmtDate(t.check_in)} → {fmtDate(t.check_out)} and gets the confirmation SMS. Collect the {kes(t.price.balance_due)} balance
          on arrival.
        </ConfirmAction>
      )}
      {t.status === "confirmed" && !arrivalDay && (
        <ActionRow icon={KeyRound} label={`Door code · sent ${fmtDate(t.check_in, "d MMM")}`} hint="Released automatically on the arrival morning" disabled />
      )}
      {t.status === "confirmed" && arrivalDay && (
        <ConfirmAction
          title="Release the door code now?"
          confirmLabel="Release code"
          success={`Door code sent to ${name} by SMS`}
          run={() => post(`/api/host/reservations/${t.ref}/release-code`, { force: true })}
          trigger={(open) => <ActionRow icon={KeyRound} label="Release door code now" hint="Skips balance, ID and SIM-swap checks" onClick={open} />}
        >
          {name} gets the {t.unit.name} door code by SMS straight away and the stay is marked as checked in.
          {t.price.balance_due > 0 && ` Note: ${kes(t.price.balance_due)} is still unpaid.`}
        </ConfirmAction>
      )}
      {t.status === "checked_in" && (
        <ConfirmAction
          title={`Check out ${name}?`}
          confirmLabel="Check out"
          success={`${name} checked out — turnover clean scheduled`}
          run={() => post(`/api/host/reservations/${t.ref}/check-out`)}
          trigger={(open) => <ActionRow icon={LogOut} label="Check out" hint="Deactivates the door code" onClick={open} />}
        >
          The door code is deactivated immediately, {name} gets a thank-you SMS and a turnover clean is assigned to housekeeping.
        </ConfirmAction>
      )}
      <ResendDialog t={t} trigger={<ActionRow icon={Repeat} label="Resend a message" hint="Confirmation, directions, door code…" />} />
      {t.can_cancel && <CancelDialog t={t} trigger={<ActionRow icon={Ban} label="Cancel booking" hint="Frees the dates and refunds the guest" danger />} />}
    </section>
  );
}

function FormDialog({
  trigger, title, children, submitLabel, dismissLabel = "Cancel", onSubmit, loading, disabled, tone = "dark", open, onOpenChange,
}: {
  trigger: React.ReactNode;
  title: string;
  children: React.ReactNode;
  submitLabel: string;
  dismissLabel?: string;
  onSubmit: () => void;
  loading?: boolean;
  disabled?: boolean;
  tone?: "dark" | "danger";
  open: boolean;
  onOpenChange: (o: boolean) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent
        size="sm"
        title={title}
        footer={
          <div className="flex justify-end gap-2">
            <DialogClose asChild>
              <Button variant="ghost">{dismissLabel}</Button>
            </DialogClose>
            <Button variant={tone === "danger" ? "danger" : "dark"} loading={loading} disabled={disabled} onClick={onSubmit}>
              {submitLabel}
            </Button>
          </div>
        }
      >
        <form
          className="space-y-4 px-6 py-5"
          onSubmit={(e) => {
            e.preventDefault();
            if (!disabled && !loading) onSubmit();
          }}
        >
          {children}
        </form>
      </DialogContent>
    </Dialog>
  );
}

function MessageDialog({ t, trigger }: { t: Trip; trigger: React.ReactNode }) {
  const [open, setOpen] = React.useState(false);
  const [text, setText] = React.useState("");
  const name = displayName(t.guest?.name, t.guest?.phone);
  const send = useHostAction(() => post(`/api/host/reservations/${t.ref}/message`, { text: text.trim() }), {
    success: `Message sent to ${name}`,
    onSuccess: () => {
      setText("");
      setOpen(false);
    },
  });
  const segments = smsSegments(text);
  return (
    <FormDialog
      open={open}
      onOpenChange={setOpen}
      trigger={trigger}
      title={`Message ${name}`}
      submitLabel="Send SMS"
      onSubmit={() => send.mutate()}
      loading={send.isPending}
      disabled={!text.trim()}
    >
      <Field label="Message" hint={`${text.length}/600 characters · ${plural(segments || 1, "SMS")} · replies land in your inbox`}>
        <Textarea
          autoFocus
          className="min-h-32"
          maxLength={600}
          placeholder={`Karibu ${name.split(" ")[0]}! …`}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && text.trim()) send.mutate();
          }}
        />
      </Field>
    </FormDialog>
  );
}

/** How Amina asks this guest for money: an M-Pesa prompt for a Kenyan number while M-Pesa is on, else a card link by SMS. */
function useRequestMethod(t: Trip): "mpesa" | "card" {
  const { mpesa } = usePayOptions();
  return mpesa && (t.guest?.phone ?? "").startsWith("+254") ? "mpesa" : "card";
}

function RequestPaymentDialog({ t, trigger }: { t: Trip; trigger: React.ReactNode }) {
  const [open, setOpen] = React.useState(false);
  const [amount, setAmount] = React.useState("");
  const method = useRequestMethod(t);
  const phone = t.guest?.phone ?? "";
  const value = amount.trim() === "" ? t.price.balance_due : Number(amount);
  const request = useHostAction(
    () => post(`/api/host/reservations/${t.ref}/request-payment`, { method, amount: amount.trim() === "" ? undefined : Number(amount) }),
    {
      success: method === "mpesa" ? `M-Pesa prompt for ${kes(value)} sent to ${fmtPhone(phone)}` : `Card payment link for ${kes(value)} texted to ${fmtPhone(phone)}`,
      onSuccess: () => {
        setAmount("");
        setOpen(false);
      },
    },
  );
  return (
    <FormDialog
      open={open}
      onOpenChange={setOpen}
      trigger={trigger}
      title={method === "mpesa" ? "Request M-Pesa payment" : "Send a card payment link"}
      submitLabel={method === "mpesa" ? `Send prompt for ${kes(value)}` : `Send link for ${kes(value)}`}
      onSubmit={() => request.mutate()}
      loading={request.isPending}
      disabled={!(value > 0)}
    >
      <p className="text-sm text-ink-2">
        {method === "mpesa" ? (
          <>An STK push pops up on <span className="font-semibold text-ink">{fmtPhone(phone)}</span>. The guest enters their M-Pesa PIN and the booking updates here the moment it&apos;s paid.</>
        ) : (
          <>We text <span className="font-semibold text-ink">{fmtPhone(phone)}</span> a link to a secure card checkout. The booking updates here the moment it&apos;s paid.</>
        )}
      </p>
      <Field label="Amount (KES)" hint={`Balance due: ${kes(t.price.balance_due)}`}>
        <Input type="number" inputMode="numeric" min={1} placeholder={String(t.price.balance_due)} value={amount} onChange={(e) => setAmount(e.target.value)} />
      </Field>
    </FormDialog>
  );
}

function RecordPaymentDialog({ t, trigger }: { t: Trip; trigger: React.ReactNode }) {
  const [open, setOpen] = React.useState(false);
  const [amount, setAmount] = React.useState("");
  const [method, setMethod] = React.useState("cash");
  const [reference, setReference] = React.useState("");
  const value = amount.trim() === "" ? t.price.balance_due : Number(amount);
  const record = useHostAction(
    () => post(`/api/host/reservations/${t.ref}/record-payment`, { amount: value, method, reference: reference.trim() }),
    {
      success: `${kes(value)} recorded`,
      onSuccess: () => {
        setAmount("");
        setReference("");
        setOpen(false);
      },
    },
  );
  return (
    <FormDialog
      open={open}
      onOpenChange={setOpen}
      trigger={trigger}
      title="Record a payment"
      submitLabel={`Record ${kes(value)}`}
      onSubmit={() => record.mutate()}
      loading={record.isPending}
      disabled={!(value > 0)}
    >
      <div className="grid grid-cols-2 gap-3">
        <Field label="Amount (KES)">
          <Input type="number" inputMode="numeric" min={1} placeholder={String(t.price.balance_due || "")} value={amount} onChange={(e) => setAmount(e.target.value)} />
        </Field>
        <Field label="Method">
          <Select value={method} onChange={(e) => setMethod(e.target.value)}>
            <option value="cash">Cash</option>
            <option value="bank">Bank transfer</option>
            <option value="mpesa">M-Pesa (till / paybill)</option>
            <option value="card">Card (POS)</option>
          </Select>
        </Field>
      </div>
      <Field label="Reference" hint="Receipt number, M-Pesa code or bank reference — optional.">
        <Input placeholder={method === "mpesa" ? "e.g. SKL4H2XY9P" : method === "bank" ? "e.g. FT2611250042" : "e.g. Receipt 0042"} value={reference} onChange={(e) => setReference(e.target.value)} />
      </Field>
    </FormDialog>
  );
}

const TEMPLATES: { key: string; label: string; text: string }[] = [
  { key: "booking_confirmed", label: "Booking confirmation", text: "Dates, home, amount paid and the trip link" },
  { key: "pre_arrival", label: "Pre-arrival check-in", text: "Breakfast, arrival time and travel questions" },
  { key: "directions", label: "Directions & Wi-Fi", text: "Directions, landmark and Wi-Fi details" },
  { key: "checkin_code", label: "Door code", text: "The current door code and check-in time" },
  { key: "local_tips", label: "Local tips", text: "Food, taxis and staying safe nearby" },
  { key: "checkout_reminder", label: "Check-out reminder", text: "Check-out time and how to leave the home" },
];

function ResendDialog({ t, trigger }: { t: Trip; trigger: React.ReactNode }) {
  const [open, setOpen] = React.useState(false);
  const [template, setTemplate] = React.useState(TEMPLATES[0].key);
  const tpl = TEMPLATES.find((x) => x.key === template) ?? TEMPLATES[0];
  const resend = useHostAction(() => post(`/api/host/reservations/${t.ref}/resend`, { template }), {
    success: `“${tpl.label}” sent again by SMS`,
    onSuccess: () => setOpen(false),
  });
  return (
    <FormDialog
      open={open}
      onOpenChange={setOpen}
      trigger={trigger}
      title="Resend a message"
      submitLabel="Send again"
      onSubmit={() => resend.mutate()}
      loading={resend.isPending}
    >
      <fieldset className="space-y-2">
        <legend className="sr-only">Message</legend>
        {TEMPLATES.map((x) => (
          <label
            key={x.key}
            className={cn(
              "flex cursor-pointer items-start gap-3 rounded-xl border px-4 py-3 transition-colors has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ink",
              template === x.key ? "border-ink bg-surface/60" : "border-line-soft hover:border-line",
            )}
          >
            <input type="radio" name="template" className="mt-1 accent-[#222]" checked={template === x.key} onChange={() => setTemplate(x.key)} />
            <span>
              <span className="block text-sm font-semibold">{x.label}</span>
              <span className="block text-xs text-ink-2">{x.text}</span>
            </span>
          </label>
        ))}
      </fieldset>
      <p className="flex items-center gap-2 text-xs text-ink-2">
        <Send className="size-3.5" /> Sent in the guest&apos;s language ({LANGUAGES[t.guest?.lang ?? "en"] ?? "English"}) to {fmtPhone(t.guest?.phone)}
      </p>
    </FormDialog>
  );
}

function CancelDialog({ t, trigger }: { t: Trip; trigger: React.ReactNode }) {
  const paid = Math.max(0, t.price.amount_paid - t.price.amount_refunded);
  const [open, setOpen] = React.useState(false);
  const [reason, setReason] = React.useState("");
  // When Amina cancels, the guest gets everything back by default; the policy amount is one tap away.
  const [refund, setRefund] = React.useState(String(paid));
  const onOpenChange = (o: boolean) => {
    if (o) {
      setRefund(String(paid));
      setReason("");
    }
    setOpen(o);
  };
  const amount = refund.trim() === "" ? 0 : Number(refund);
  const invalid = !(amount >= 0) || amount > paid;
  const cancel = useHostAction(() => post(`/api/host/reservations/${t.ref}/cancel`, { reason: reason.trim(), refund_amount: amount }), {
    success: `${t.ref} cancelled${amount ? ` — ${kes(amount)} refund started` : ""}`,
    onSuccess: () => setOpen(false),
  });
  return (
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      trigger={trigger}
      title={`Cancel ${t.ref}?`}
      submitLabel="Cancel booking"
      dismissLabel="Keep booking"
      tone="danger"
      onSubmit={() => cancel.mutate()}
      loading={cancel.isPending}
      disabled={invalid}
    >
      <div className="flex gap-3 rounded-xl bg-danger-50 px-4 py-3 text-[13px] text-danger">
        <ShieldAlert className="mt-0.5 size-4 shrink-0" />
        <p>
          This frees {fmtDate(t.check_in)} → {fmtDate(t.check_out)} at {t.unit.name} on every channel, deactivates the door code and texts{" "}
          {displayName(t.guest?.name, t.guest?.phone)}. It can&apos;t be undone.
          {paid > 0 && " Host cancellations of paid stays also send goodwill airtime to Kenyan numbers."}
        </p>
      </div>
      <Field label="Reason" hint="Shared with the guest in the cancellation SMS.">
        <Textarea className="min-h-20" maxLength={200} placeholder="e.g. Water outage at the building — very sorry!" value={reason} onChange={(e) => setReason(e.target.value)} />
      </Field>
      <Field
        label="Refund (KES)"
        error={amount > paid ? `The most you can refund is ${kes(paid)}.` : undefined}
        hint={
          <>
            {kes(paid)} paid so far. {t.cancellation.policy_text || t.cancellation.text}
            {t.cancellation.refund !== undefined && ` Policy refund: ${kes(t.cancellation.refund)}.`}
          </>
        }
      >
        <Input type="number" inputMode="numeric" min={0} max={paid} value={refund} onChange={(e) => setRefund(e.target.value)} />
      </Field>
      {paid > 0 && (
        <div className="-mt-1 flex flex-wrap gap-2">
          {t.cancellation.refund !== undefined && (
            <Button type="button" size="sm" variant="soft" onClick={() => setRefund(String(t.cancellation.refund))}>
              Policy refund · {kes(t.cancellation.refund)}
            </Button>
          )}
          <Button type="button" size="sm" variant="soft" onClick={() => setRefund(String(paid))}>
            Refund in full · {kes(paid)}
          </Button>
        </div>
      )}
    </FormDialog>
  );
}
