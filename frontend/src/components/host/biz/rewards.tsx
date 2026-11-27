"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Coins, Gift, Hourglass, Smartphone, UserPlus, Users, Wifi, WifiOff, X, type LucideIcon } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { ErrorBlock, LoadingBlock, PageHeader, Table, Td, Tr } from "@/components/host/common";
import { fmtPhone } from "@/components/host/ops/lib";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/misc";
import { Tooltip } from "@/components/ui/overlays";
import { get, post, put } from "@/lib/api";
import { fmtDate, fmtDateTime, kes, plural } from "@/lib/format";
import { cn } from "@/lib/utils";

import { useHostSettings, useInvalidateHost } from "./queries";
import { KpiTile } from "./support";
import type { PayoutRow, PayoutStatus, ReferralRow, RewardsProgram, RewardsResponse } from "./types";
import { Callout, Field, FormCard, NumberInput, SaveBar, Segmented, SwitchRow, TableCard, errorMessage, fieldErrors, reservationHref } from "./ui";

const KEY = ["host", "rewards"];

type Tone = "neutral" | "brand" | "ocean" | "success" | "warning" | "danger";
const PAYOUT_STATUS: Record<PayoutStatus, { label: string; tone: Tone; tip?: string }> = {
  held: { label: "Waiting for approval", tone: "warning", tip: "Over this month's airtime budget: approve it to send, or reject it." },
  queued: { label: "Queued", tone: "ocean" },
  sent: { label: "Sent", tone: "ocean", tip: "Accepted by Africa's Talking; waiting for the network to confirm." },
  success: { label: "Delivered", tone: "success" },
  failed: { label: "Failed", tone: "danger" },
  rejected: { label: "Rejected", tone: "neutral", tip: "Not sent. Points spent on it were returned." },
  simulated: { label: "Simulated", tone: "neutral", tip: "No Africa's Talking key (or a demo guest), so nothing was actually sent." },
};
const REASON_ICON: Record<PayoutRow["reason"], LucideIcon> = { referral: UserPlus, referee: UserPlus, redeem: Coins, outage: WifiOff, manual: Gift };
const REFERRAL_TONE: Record<ReferralRow["status"], Tone> = { pending: "warning", rewarded: "success", void: "neutral" };

/** The guest's name, or null when the account only has a phone number (its display name is then the number). */
const nameOf = (p: PayoutRow) => (p.guest && !/^\+?[\d\s]+$/.test(p.guest) ? p.guest : null);

const mbText = (mb: number) => (mb >= 1024 ? `${(mb / 1024).toFixed(mb % 1024 ? 1 : 0)} GB` : `${mb.toLocaleString("en-KE")} MB`);

export function RewardsPage() {
  const { data, isLoading, error, refetch } = useQuery({ queryKey: KEY, queryFn: () => get<RewardsResponse>("/api/host/rewards"), refetchInterval: 30_000 });
  return (
    <>
      <PageHeader
        title="Rewards & airtime"
        subtitle="Points for stays and feedback, airtime for referrals and data bundles when the Wi-Fi fails — paid instantly through Africa's Talking."
        actions={<SendButton />}
      />
      {error && !data ? <ErrorBlock error={error} retry={refetch} /> : isLoading || !data ? <LoadingBlock rows={6} /> : <RewardsBody data={data} />}
    </>
  );
}

function RewardsBody({ data }: { data: RewardsResponse }) {
  const { stats: s, program: p } = data;
  const used = s.airtime_budget ? (s.airtime_month / s.airtime_budget) * 100 : 0;
  const worth = Math.floor(s.points_outstanding / Math.max(1, p.redeem_points)) * p.redeem_airtime;
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-3">
        <KpiTile label="Members" value={s.members.toLocaleString("en-KE")} hint={`of ${s.guests.toLocaleString("en-KE")} guests on file`} icon={<Users className="size-4" />} tone="ocean" />
        <KpiTile
          label="Points outstanding"
          value={s.points_outstanding.toLocaleString("en-KE")}
          hint={worth ? `Up to ${kes(worth)} of airtime if all redeemed` : "Nothing to redeem yet"}
          icon={<Coins className="size-4" />}
        />
        <KpiTile
          label="Airtime this month"
          value={kes(s.airtime_month)}
          hint={s.airtime_budget ? `of the ${kes(s.airtime_budget)} monthly budget` : "No monthly cap"}
          icon={<Smartphone className="size-4" />}
          tone={used >= 100 ? "warning" : "brand"}
        >
          {s.airtime_budget > 0 && (
            <div className="mt-2.5 h-1.5 overflow-hidden rounded-full bg-line-soft" role="progressbar" aria-label="Airtime budget used" aria-valuenow={Math.round(used)} aria-valuemin={0} aria-valuemax={100}>
              <div className={cn("h-full rounded-full", used >= 100 ? "bg-danger" : used >= 80 ? "bg-warning" : "bg-ink")} style={{ width: `${Math.min(100, used)}%` }} />
            </div>
          )}
        </KpiTile>
        <KpiTile label="Data this month" value={mbText(s.data_month_mb)} hint="Outage bundles, redemptions and gifts" icon={<Wifi className="size-4" />} />
        <KpiTile
          label="Referrals"
          value={s.referrals_completed}
          hint={s.referrals_pending ? `${s.referrals_pending} waiting for a first stay` : "Completed stays from invite codes"}
          icon={<UserPlus className="size-4" />}
        />
        <KpiTile
          label="Waiting for approval"
          value={s.payouts_held}
          hint={s.payouts_held ? "Over the monthly airtime budget" : "Nothing waiting"}
          icon={<Hourglass className="size-4" />}
          tone={s.payouts_held ? "warning" : "neutral"}
        />
      </div>

      {p.enabled ? (
        <Callout tone="info" icon={<Gift className="size-[18px]" />} title="How guests earn and spend">
          <ul className="mt-1 list-disc space-y-1 pl-4">
            <li>
              {plural(p.points_per_100, "point")} for every KES 100 of a completed stay, and {p.review_points} for sharing feedback afterwards.
            </li>
            <li>
              {p.redeem_points} points buy {kes(p.redeem_airtime)} of airtime or {p.redeem_data_mb} MB of data — by texting <Kw>POINTS</Kw>, <Kw>REDEEM AIRTIME</Kw> or{" "}
              <Kw>REDEEM DATA</Kw>, on USSD under More → Rewards, or from their account page.
            </li>
            <li>
              Every guest has an invite code. A friend who texts <Kw>REF CODE</Kw> gets {kes(p.referee_airtime)} and the guest who invited them {kes(p.referral_airtime)}, once
              the friend&apos;s first stay is complete.
            </li>
            <li>
              When the Wi-Fi or power fails, each guest staying gets {p.outage_data_mb ? `${p.outage_data_mb} MB of data` : "no data (switched off below)"} so they stay connected.
              {p.monthly_airtime_budget > 0 && ` Airtime beyond ${kes(p.monthly_airtime_budget)} a month waits for your approval.`}
            </li>
          </ul>
        </Callout>
      ) : (
        <Callout tone="warning" title="The rewards programme is off">
          Guests don&apos;t earn or redeem points and invite codes pay nothing. Outage data bundles and the airtime you send yourself still work.
        </Callout>
      )}

      <div className="grid gap-6 2xl:grid-cols-[minmax(0,1fr)_380px]">
        <PayoutsCard payouts={data.payouts} />
        <ReferralsCard referrals={data.referrals} />
      </div>

      <ProgramForm program={p} />
    </div>
  );
}

function Kw({ children }: { children: React.ReactNode }) {
  return <span className="rounded bg-white/80 px-1 font-mono text-[12.5px] font-semibold whitespace-nowrap text-ink ring-1 ring-line-soft">{children}</span>;
}

// ---------- payouts ----------

type PayoutFilter = "all" | "held" | "airtime" | "data";

function PayoutBadge({ p }: { p: PayoutRow }) {
  const meta = PAYOUT_STATUS[p.status] ?? { label: p.status_label, tone: "neutral" as Tone };
  const tip = p.status === "failed" && p.error ? p.error : meta.tip;
  const badge = (
    <Badge tone={meta.tone} dot>
      {meta.label}
    </Badge>
  );
  return tip ? (
    <Tooltip content={tip}>
      <span className="inline-flex cursor-help" tabIndex={0}>
        {badge}
      </span>
    </Tooltip>
  ) : (
    badge
  );
}

function KindIcon({ kind }: { kind: PayoutRow["kind"] }) {
  const Icon = kind === "data" ? Wifi : Smartphone;
  return (
    <span className={cn("grid size-8 shrink-0 place-items-center rounded-full", kind === "data" ? "bg-ocean-50 text-ocean-600" : "bg-brand-50 text-brand-600")}>
      <Icon className="size-4" />
    </span>
  );
}

function PayoutsCard({ payouts }: { payouts: PayoutRow[] }) {
  const invalidate = useInvalidateHost();
  const [filter, setFilter] = React.useState<PayoutFilter>("all");
  const act = useMutation({
    mutationFn: ({ p, action }: { p: PayoutRow; action: "approve" | "reject" }) => post<PayoutRow>(`/api/host/rewards/payouts/${p.id}/${action}`),
    onSuccess: (r, { action }) => {
      if (action === "reject") toast.success(`${r.amount_text} to ${nameOf(r) ?? fmtPhone(r.phone)} rejected`, { description: r.reason === "redeem" ? "The points went back to the guest." : undefined });
      else if (r.status === "failed") toast.error(`${r.amount_text} couldn't be sent`, { description: r.error });
      else toast.success(`${r.amount_text} approved and sent`, { description: r.status === "simulated" ? PAYOUT_STATUS.simulated.tip : undefined });
      invalidate();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  const held = payouts.filter((p) => p.status === "held").length;
  const rows = payouts
    .filter((p) => filter === "all" || (filter === "held" ? p.status === "held" : p.kind === filter))
    .sort((a, b) => Number(b.status === "held") - Number(a.status === "held") || b.id - a.id);
  const busy = (p: PayoutRow, action: "approve" | "reject") => act.isPending && act.variables?.p.id === p.id && act.variables.action === action;
  const actions = (p: PayoutRow) =>
    p.status === "held" && (
      <div className="flex gap-2">
        <Button variant="dark" size="sm" loading={busy(p, "approve")} disabled={act.isPending} onClick={() => act.mutate({ p, action: "approve" })}>
          {!busy(p, "approve") && <Check className="size-4" />} Approve
        </Button>
        <Button variant="ghost" size="sm" loading={busy(p, "reject")} disabled={act.isPending} onClick={() => act.mutate({ p, action: "reject" })}>
          {!busy(p, "reject") && <X className="size-4" />} Reject
        </Button>
      </div>
    );

  return (
    <TableCard
      className="min-w-0"
      title="Airtime & data sent"
      description="Every top-up through Africa's Talking — rewards, outage bundles and the ones you send yourself. The latest 100."
    >
      <div className="border-b border-line-soft px-5 py-3">
        <Segmented<PayoutFilter>
          label="Filter payouts"
          size="sm"
          value={filter}
          onChange={setFilter}
          options={[
            { value: "all", label: "All" },
            { value: "held", label: "Waiting", count: held },
            { value: "airtime", label: "Airtime" },
            { value: "data", label: "Data" },
          ]}
        />
      </div>
      {rows.length === 0 ? (
        <div className="px-5 py-10 text-center text-sm text-ink-2">{filter === "held" ? "Nothing waiting for your approval." : "Nothing sent yet."}</div>
      ) : (
        <>
          <ul className="divide-y divide-line-soft lg:hidden">
            {rows.map((p) => {
              const Reason = REASON_ICON[p.reason] ?? Gift;
              return (
                <li key={p.id} className={cn("flex gap-3 px-4 py-4", p.status === "held" && "bg-warning-50/50")}>
                  <KindIcon kind={p.kind} />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
                      <span className="text-[15px] font-bold tabular-nums">{p.amount_text}</span>
                      <PayoutBadge p={p} />
                    </div>
                    <p className="mt-0.5 text-[13.5px] [overflow-wrap:anywhere]">
                      <span className="font-semibold">{nameOf(p) ?? fmtPhone(p.phone)}</span>
                      {nameOf(p) && <span className="whitespace-nowrap text-ink-2"> · {fmtPhone(p.phone)}</span>}
                    </p>
                    <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[12.5px] text-ink-2">
                      <span className="inline-flex items-center gap-1">
                        <Reason className="size-3.5" /> {p.reason_label}
                      </span>
                      {p.booking && (
                        <Link href={reservationHref(p.booking)} className="font-mono font-semibold text-ink hover:underline">
                          {p.booking}
                        </Link>
                      )}
                      <span>{fmtDateTime(p.created_at)}</span>
                    </p>
                    {p.note && <p className="mt-1 text-[12.5px] text-ink-2 italic [overflow-wrap:anywhere]">“{p.note}”</p>}
                    {p.status === "failed" && p.error && <p className="mt-1 text-[12.5px] text-danger [overflow-wrap:anywhere]">{p.error}</p>}
                    {p.status === "held" && <div className="mt-3">{actions(p)}</div>}
                  </div>
                </li>
              );
            })}
          </ul>
          <Table head={["When", "Guest", "Reward", "For", "Status", ""]} className="hidden lg:block">
            {rows.map((p) => {
              const Reason = REASON_ICON[p.reason] ?? Gift;
              return (
                <Tr key={p.id} className={cn(p.status === "held" && "bg-warning-50/50")}>
                  <Td className="whitespace-nowrap text-ink-2">{fmtDateTime(p.created_at)}</Td>
                  <Td className="max-w-48">
                    {nameOf(p) ? (
                      <>
                        <span className="block truncate font-medium">{nameOf(p)}</span>
                        <span className="block text-[12.5px] whitespace-nowrap text-ink-2 tabular-nums">{fmtPhone(p.phone)}</span>
                      </>
                    ) : (
                      <span className="block font-medium whitespace-nowrap tabular-nums">{fmtPhone(p.phone)}</span>
                    )}
                  </Td>
                  <Td>
                    <span className="inline-flex items-center gap-2 font-semibold whitespace-nowrap tabular-nums">
                      <KindIcon kind={p.kind} /> {p.amount_text}
                    </span>
                  </Td>
                  <Td className="max-w-60">
                    <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
                      <Reason className="size-3.5 text-ink-2" /> {p.reason_label}
                    </span>
                    {(p.booking || p.note) && (
                      <span className="block truncate text-[12.5px] text-ink-2" title={p.note || undefined}>
                        {p.booking && (
                          <Link href={reservationHref(p.booking)} className="font-mono font-semibold text-ink hover:underline">
                            {p.booking}
                          </Link>
                        )}
                        {p.booking && p.note && " · "}
                        {p.note}
                      </span>
                    )}
                  </Td>
                  <Td>
                    <PayoutBadge p={p} />
                  </Td>
                  <Td className="text-right">{actions(p)}</Td>
                </Tr>
              );
            })}
          </Table>
        </>
      )}
    </TableCard>
  );
}

function ReferralsCard({ referrals }: { referrals: ReferralRow[] }) {
  return (
    <TableCard className="min-w-0 self-start" title="Referrals" description="Friends who joined with a guest's invite code.">
      {referrals.length === 0 ? (
        <div className="px-5 py-10 text-center text-sm text-ink-2">No referrals yet. Guests find their invite code by texting POINTS or on their account page.</div>
      ) : (
        <ul className="divide-y divide-line-soft">
          {referrals.map((r, i) => (
            <li key={`${r.code}-${r.referee}-${i}`} className="px-5 py-3.5">
              <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1.5">
                <p className="min-w-0 text-[14px] [overflow-wrap:anywhere]">
                  <b className="font-semibold">{r.referrer}</b> <span className="text-ink-2">invited</span> <b className="font-semibold">{r.referee}</b>
                </p>
                <Badge tone={REFERRAL_TONE[r.status] ?? "neutral"} dot>
                  {r.status_label}
                </Badge>
              </div>
              <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[12.5px] text-ink-2">
                {r.code && <span className="rounded bg-surface px-1.5 font-mono font-semibold text-ink">{r.code}</span>}
                {r.booking && (
                  <Link href={reservationHref(r.booking)} className="font-mono font-semibold text-ink hover:underline">
                    {r.booking}
                  </Link>
                )}
                {r.created_at && <span>joined {fmtDate(r.created_at, "d MMM yyyy")}</span>}
              </p>
            </li>
          ))}
        </ul>
      )}
    </TableCard>
  );
}

// ---------- programme ----------

type NumKey = Exclude<keyof RewardsProgram, "enabled">;
type Draft = { enabled: boolean } & Record<NumKey, number | null>;

const GROUPS: { title: string; text: string; fields: { key: NumKey; label: string; help: string; before?: string; after?: string; min?: number; max?: number }[] }[] = [
  {
    title: "Earning",
    text: "Points land when a stay is completed and after feedback.",
    fields: [
      { key: "points_per_100", label: "Points per KES 100 spent", help: "On every completed stay booked direct.", after: "points" },
      { key: "review_points", label: "Points for feedback", help: "After a stay, whatever the rating.", after: "points" },
    ],
  },
  {
    title: "Redeeming",
    text: "What a guest gets each time they swap points.",
    fields: [
      { key: "redeem_points", label: "Points per redemption", help: "At least 1.", after: "points", min: 1 },
      { key: "redeem_airtime", label: "Airtime per redemption", help: "Up to KES 1,000.", before: "KES", max: 1000 },
      { key: "redeem_data_mb", label: "Data per redemption", help: "Up to 5,000 MB.", after: "MB", max: 5000 },
    ],
  },
  {
    title: "Referrals",
    text: "Paid in airtime once the friend's first stay is complete.",
    fields: [
      { key: "referral_airtime", label: "To the guest who invites", help: "Up to KES 1,000.", before: "KES", max: 1000 },
      { key: "referee_airtime", label: "To the friend they invite", help: "Up to KES 1,000.", before: "KES", max: 1000 },
    ],
  },
  {
    title: "Outages & budget",
    text: "Keep guests online, and keep spending in check.",
    fields: [
      { key: "outage_data_mb", label: "Data per guest in an outage", help: "When the Wi-Fi or power fails. 0 = off.", after: "MB", max: 5000 },
      { key: "monthly_airtime_budget", label: "Monthly airtime budget", help: "Rewards beyond it wait for your approval. 0 = no cap.", before: "KES" },
    ],
  },
];
const NUM_KEYS = GROUPS.flatMap((g) => g.fields.map((f) => f.key));

function ProgramForm({ program }: { program: RewardsProgram }) {
  const qc = useQueryClient();
  const invalidate = useInvalidateHost();
  const [draft, setDraft] = React.useState<Draft>(program);
  const [seen, setSeen] = React.useState(program);
  if (seen !== program) {
    // fresh data from the server: take it, unless there are edits in progress
    setSeen(program);
    if ((Object.keys(seen) as (keyof RewardsProgram)[]).every((k) => seen[k] === draft[k])) setDraft(program);
  }
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [saving, setSaving] = React.useState(false);
  const changed = (["enabled", ...NUM_KEYS] as (keyof RewardsProgram)[]).filter((k) => draft[k] !== program[k]);
  const clientError = (f: (typeof GROUPS)[number]["fields"][number]) => {
    const v = draft[f.key];
    if (v === null) return "Enter a number.";
    if (f.min !== undefined && v < f.min) return `At least ${f.min.toLocaleString("en-KE")}.`;
    if (f.max !== undefined && v > f.max) return `At most ${f.max.toLocaleString("en-KE")}.`;
    return "";
  };
  const invalid = GROUPS.some((g) => g.fields.some((f) => clientError(f)));

  const save = async () => {
    if (saving) return;
    if (invalid) {
      toast.error("Check the highlighted numbers first.");
      return;
    }
    setSaving(true);
    try {
      const updated = await put<RewardsProgram>("/api/host/rewards/program", draft);
      qc.setQueryData<RewardsResponse>(KEY, (old) => old && { ...old, program: updated });
      setDraft(updated);
      setErrors({});
      toast.success("Rewards programme saved", { description: "Applies on SMS, USSD and the website straight away." });
      invalidate();
    } catch (e) {
      setErrors(fieldErrors(e));
      toast.error(errorMessage(e, "Couldn't save the programme."));
    } finally {
      setSaving(false);
    }
  };

  const set = (k: keyof Draft, v: number | boolean | null) => {
    setDraft((d) => ({ ...d, [k]: v }));
    if (errors[k]) setErrors((e) => Object.fromEntries(Object.entries(e).filter(([key]) => key !== k)));
  };

  return (
    <div>
      <FormCard id="programme" title="Programme rules" description="Changes apply on every channel straight away.">
        <div className="rounded-xl border border-line-soft p-4">
          <SwitchRow
            label="Rewards programme on"
            description="Guests earn points for stays and feedback, redeem them for airtime or data, and invite codes pay out. Outage data and the airtime you send yourself work either way."
            checked={draft.enabled}
            onCheckedChange={(v) => set("enabled", v)}
          />
        </div>
        <div className="grid gap-x-8 gap-y-7 lg:grid-cols-2">
          {GROUPS.map((g) => (
            <fieldset key={g.title} className="min-w-0">
              <legend className="text-[15px] font-bold">{g.title}</legend>
              <p className="mt-0.5 text-[13px] text-ink-2">{g.text}</p>
              <div className="mt-3 grid gap-4 sm:grid-cols-2">
                {g.fields.map((f) => {
                  const err = errors[f.key] || (draft[f.key] !== program[f.key] ? clientError(f) : "");
                  return (
                    <Field key={f.key} label={f.label} hint={f.help} error={err}>
                      <NumberInput
                        value={draft[f.key]}
                        onValueChange={(v) => set(f.key, v === null ? null : Math.max(0, Math.round(v)))}
                        before={f.before}
                        after={f.after}
                        className={cn(f.after && (f.after.length <= 2 ? "pr-11" : "pr-20"))}
                      />
                    </Field>
                  );
                })}
              </div>
            </fieldset>
          ))}
        </div>
        <p className="rounded-xl bg-surface px-4 py-3 text-[13.5px] text-ink-2">
          With these rules a KES 20,000 stay earns <b className="text-ink">{plural(Math.floor(200 * (draft.points_per_100 ?? 0)), "point")}</b>;{" "}
          {draft.redeem_points ? (
            <>
              every <b className="text-ink">{draft.redeem_points}</b> points buy <b className="text-ink">{kes(draft.redeem_airtime ?? 0)}</b> of airtime or{" "}
              <b className="text-ink">{draft.redeem_data_mb ?? 0} MB</b>.
            </>
          ) : (
            "set the points per redemption to see what they buy."
          )}
        </p>
      </FormCard>
      <SaveBar
        count={changed.length}
        saving={saving}
        onSave={save}
        onDiscard={() => {
          setDraft(program);
          setErrors({});
        }}
        saveLabel="Save programme"
      />
    </div>
  );
}

// ---------- send airtime or data ----------

function SendButton() {
  const [open, setOpen] = React.useState(false);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="dark">
          <Gift className="size-4" /> Send airtime or data
        </Button>
      </DialogTrigger>
      {open && <SendForm onDone={() => setOpen(false)} />}
    </Dialog>
  );
}

const SEND_LIMITS = {
  airtime: { min: 10, max: 1000, presets: [50, 100, 200, 500], fallback: 100 },
  data: { min: 50, max: 5000, presets: [100, 250, 500, 1000], fallback: 250 },
};

function SendForm({ onDone }: { onDone: () => void }) {
  const invalidate = useInvalidateHost();
  const { data: settings } = useHostSettings();
  const [phone, setPhone] = React.useState("");
  const [kind, setKind] = React.useState<"airtime" | "data">("airtime");
  const [amount, setAmount] = React.useState<number | null>(SEND_LIMITS.airtime.fallback);
  const [note, setNote] = React.useState("");
  const lim = SEND_LIMITS[kind];
  const amountText = amount === null ? "" : kind === "airtime" ? kes(amount) : `${amount.toLocaleString("en-KE")} MB`;
  const inRange = amount !== null && amount >= lim.min && amount <= lim.max;
  const send = useMutation({
    mutationFn: () => post<PayoutRow>("/api/host/rewards/send", { phone: phone.trim(), kind, amount, note: note.trim() }),
    onSuccess: (p) => {
      const who = nameOf(p) ?? fmtPhone(p.phone);
      if (p.status === "failed") toast.error(`${p.amount_text} to ${who} failed`, { description: p.error || undefined });
      else
        toast.success(`${p.amount_text}${p.kind === "data" ? " of data" : " airtime"} sent to ${who}`, {
          description: p.status === "simulated" ? `${PAYOUT_STATUS.simulated.tip} They still got the SMS saying it's from you.` : "They also got an SMS saying it's from you.",
        });
      invalidate();
      onDone();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const ready = !!phone.trim() && inRange;
  const sms = `${settings?.host_name || "Amina"} from ${settings?.business_name || "Amina Stays"} has sent you ${amountText || "…"}${note.trim() ? ` - ${note.trim()}` : ""}. Asante!`;

  return (
    <DialogContent
      size="md"
      title="Send airtime or data"
      footer={
        <div className="flex justify-end gap-2">
          <DialogClose asChild>
            <Button variant="ghost">Cancel</Button>
          </DialogClose>
          <Button type="submit" form="send-reward" variant="brand" loading={send.isPending} disabled={!ready}>
            <Gift className="size-4" /> Send {amountText}
          </Button>
        </div>
      }
    >
      <form
        id="send-reward"
        className="space-y-5 px-6 py-5"
        onSubmit={(e) => {
          e.preventDefault();
          if (ready && !send.isPending) send.mutate();
        }}
      >
        <p className="text-[14px] text-ink-2">A thank-you, or sorry for a rough night — topped up through Africa&apos;s Talking in seconds, with an SMS saying it&apos;s from you.</p>
        <Field label="Guest's phone" hint="Kenyan (+254) numbers only.">
          <Input type="tel" inputMode="tel" autoComplete="off" placeholder="0712 345 678" value={phone} onChange={(e) => setPhone(e.target.value)} autoFocus />
        </Field>
        <div>
          <p className="mb-2 text-[13px] font-semibold">What to send</p>
          <Segmented<"airtime" | "data">
            label="What to send"
            value={kind}
            onChange={(k) => {
              setKind(k);
              setAmount(SEND_LIMITS[k].fallback);
            }}
            options={[
              { value: "airtime", label: "Airtime" },
              { value: "data", label: "Mobile data" },
            ]}
          />
        </div>
        <div>
          <Field
            label="Amount"
            hint={`Between ${lim.min.toLocaleString("en-KE")} and ${lim.max.toLocaleString("en-KE")} ${kind === "airtime" ? "KES" : "MB"}.`}
            error={amount !== null && !inRange ? `Choose between ${lim.min.toLocaleString("en-KE")} and ${lim.max.toLocaleString("en-KE")} ${kind === "airtime" ? "KES" : "MB"}.` : undefined}
          >
            <NumberInput value={amount} onValueChange={setAmount} before={kind === "airtime" ? "KES" : undefined} after={kind === "data" ? "MB" : undefined} className={cn(kind === "data" && "pr-11")} />
          </Field>
          <div className="mt-2 flex flex-wrap gap-2">
            {lim.presets.map((v) => (
              <button
                key={v}
                type="button"
                onClick={() => setAmount(v)}
                aria-pressed={amount === v}
                className={cn(
                  "rounded-full border px-3 py-1 text-[13px] font-semibold tabular-nums transition",
                  amount === v ? "border-ink bg-ink text-white" : "border-line text-ink-2 hover:border-ink-3 hover:text-ink",
                )}
              >
                {kind === "airtime" ? kes(v) : `${v.toLocaleString("en-KE")} MB`}
              </button>
            ))}
          </div>
        </div>
        <Field label="Why (optional)" hint="Added to their SMS.">
          <Input value={note} onChange={(e) => setNote(e.target.value)} maxLength={120} placeholder="sorry about the noise last night" />
        </Field>
        <div className="rounded-xl bg-[#f2f2f7] p-3">
          <div className="max-w-[92%] rounded-[1rem] rounded-bl-[0.3rem] bg-white px-3.5 py-2 text-[14px] leading-snug text-ink shadow-sm [overflow-wrap:anywhere]">{sms}</div>
        </div>
      </form>
    </DialogContent>
  );
}
