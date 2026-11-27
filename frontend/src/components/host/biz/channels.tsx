"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Activity, CardSim, CircleCheck, CircleDashed, CircleX, CreditCard, Gift, Globe, KeyRound, MessageSquare, MessageSquareText, Phone, RefreshCw, Server,
  Smartphone, Wallet, Wifi, type LucideIcon,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { useConfig, usePayOptions } from "@/components/providers";
import { ErrorBlock, LoadingBlock, PageHeader, Table, Td, Tr } from "@/components/host/common";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/misc";
import { Tooltip } from "@/components/ui/overlays";
import { get } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

import type { AtProduct, ChannelsResponse } from "./types";
import { Callout, CopyField, errorMessage, humanize, since } from "./ui";

const PRODUCT_META: Record<string, { icon: LucideIcon; where: string; seen?: string; blurb: string }> = {
  sms: { icon: MessageSquareText, where: "SMS → Callback URLs", seen: "sms", blurb: "Two-way SMS: Ask Amina answers, books and relays questions." },
  ussd: { icon: Smartphone, where: "USSD → Service codes → Callback URL", seen: "ussd", blurb: "A menu on any phone — search dates, book and pay without data." },
  voice: { icon: Phone, where: "Voice → Phone numbers → Callback URL", seen: "voice", blurb: "Call Amina: an IVR to book, hear directions or press 9 for help." },
  airtime: { icon: Gift, where: "Airtime → Callback URLs → Status", blurb: "Goodwill airtime when Amina has to cancel a paid stay." },
  data: { icon: Wifi, where: "Mobile Data → Callback URL", blurb: "A welcome data bundle on check-in for Kenyan numbers." },
  insights: { icon: CardSim, where: "Insights → SIM swap → Callback URL", blurb: "Checks for a recent SIM swap before a door code goes out." },
  whatsapp: { icon: MessageSquare, where: "AT Chat (preview)", blurb: "Optional WhatsApp channel for international guests." },
  payments: { icon: Wallet, where: "Payments → Callback URL, or Daraja STK callback", seen: "payment", blurb: "M-Pesa STK push — the callback is the only proof of payment." },
  card: { icon: CreditCard, where: "Stripe Dashboard → Developers → Webhooks", seen: "payment", blurb: "Card payments on Stripe's hosted checkout — the webhook confirms each one at once." },
};

const JOBS: Record<string, { label: string; every: string; minutes?: number }> = {
  expire_holds: { label: "Release unpaid holds", every: "Every pass", minutes: 5 },
  outbox: { label: "Send queued SMS (outbox)", every: "Every pass", minutes: 5 },
  release_codes: { label: "Release door codes", every: "Every pass", minutes: 5 },
  automations: { label: "Guest message timeline", every: "Every pass", minutes: 5 },
  auto_checkout: { label: "Automatic checkout", every: "Every pass", minutes: 5 },
  reviews: { label: "Review requests", every: "Every pass", minutes: 5 },
  alert_followups: { label: "SOS follow-up calls", every: "Every pass", minutes: 5 },
  payments_reconcile: { label: "Reconcile payments", every: "Every 2 min", minutes: 10 },
  ical_sync: { label: "Airbnb / Booking.com iCal sync", every: "Every 15 min", minutes: 45 },
  host_digest: { label: "Morning digest to Amina", every: "Daily 07:00" },
  gate_list: { label: "Gate list to security", every: "Daily 07:30" },
  kitchen_sheet: { label: "Breakfast sheet to the cook", every: "Daily 18:00" },
  levy_reminder: { label: "Tourism levy reminder", every: "Daily 09:00 (acts on the 5th)" },
  retention: { label: "Erase expired guest IDs", every: "Daily 03:00" },
};

export function ChannelsPage() {
  const { data: config } = useConfig();
  const { mpesa, methods } = usePayOptions();
  const [withBalance, setWithBalance] = React.useState(false);
  const { data, isLoading, isFetching, error, refetch } = useQuery({
    queryKey: ["host", "channels", withBalance],
    queryFn: () => get<ChannelsResponse>(`/api/host/channels${withBalance ? "?balance=1" : ""}`),
  });

  const checkBalance = async () => {
    if (!withBalance) setWithBalance(true);
    else {
      const r = await refetch();
      if (r.error) toast.error(errorMessage(r.error));
    }
  };

  const ready = data?.products.filter((p) => p.ready).length ?? 0;
  const local = data?.products.some((p) => Object.values(p.callbacks).some((u) => /\/\/(localhost|127\.0\.0\.1)/.test(u)));

  const doors: { key: string; title: string; icon: LucideIcon; value: string; text: string; seen?: string | null }[] = [
    { key: "web", title: "Website", icon: Globe, value: config?.business.email?.split("@")[1] || "Web", text: `Smartphones & laptops — photos, maps, pay by ${methods}` },
    { key: "ussd", title: "USSD", icon: Smartphone, value: config?.channels.ussd_code || "Code not set", text: mpesa ? "Any phone, no data — dial, pick dates, pay by M-Pesa" : "Any phone, no data — dial, pick dates, get a pay link", seen: data?.last_seen.ussd },
    { key: "sms", title: "SMS · Ask Amina", icon: MessageSquareText, value: config?.channels.sms_number || "Shortcode not set", text: "Text in English or Kiswahili, any hour", seen: data?.last_seen.sms },
    { key: "voice", title: "Voice · Call Amina", icon: Phone, value: config?.channels.voice_number || "Number not set", text: "Press 1 to book, 9 for help — no reading needed", seen: data?.last_seen.voice },
  ];

  return (
    <>
      <PageHeader
        title="Africa's Talking"
        subtitle={`The rails under every channel — SMS, USSD, Voice, Airtime, Mobile Data and SIM-swap checks — plus ${mpesa ? "M-Pesa and card" : "card"} payments.`}
        actions={
          <>
            {data && (
              <Badge tone={data.sandbox ? "warning" : "success"} dot>
                {data.sandbox ? "Sandbox" : "Live"}
              </Badge>
            )}
            <Button variant="dark" onClick={checkBalance} loading={withBalance && isFetching}>
              <RefreshCw className="size-4" /> Check balance
            </Button>
          </>
        }
      />

      {error ? (
        <ErrorBlock error={error} retry={refetch} />
      ) : isLoading || !data ? (
        <LoadingBlock rows={6} />
      ) : (
        <div className="space-y-6">
          <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-ink via-[#1f2a2b] to-ocean-700 p-6 text-white sm:p-8">
            <div className="pointer-events-none absolute -top-24 -right-24 size-72 rounded-full bg-brand-500/20 blur-3xl" />
            <div className="relative max-w-2xl">
              <p className="text-[12px] font-bold tracking-[0.18em] text-white/60 uppercase">One platform · four doors</p>
              <h2 className="mt-2 text-2xl leading-tight font-bold tracking-tight sm:text-[28px]">Every guest can book — with or without a smartphone.</h2>
              <p className="mt-2 text-[15px] text-white/75">
                Each door leads to the same calendar, prices, {mpesa ? "M-Pesa checkout" : "secure checkout"} and guest profile. One phone number is one guest, whichever way they arrive.
              </p>
            </div>
            <div className="relative mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {doors.map((d) => (
                <div key={d.key} className="rounded-2xl bg-white/[0.07] p-4 ring-1 ring-white/10 backdrop-blur">
                  <div className="flex items-center gap-2.5">
                    <span className="grid size-9 place-items-center rounded-xl bg-white/10">
                      <d.icon className="size-[18px]" />
                    </span>
                    <span className="text-[14px] font-semibold">{d.title}</span>
                  </div>
                  <p className="mt-3 truncate font-mono text-[15px] font-semibold">{d.value}</p>
                  <p className="mt-1 text-[12.5px] leading-snug text-white/65">{d.text}</p>
                  <p className="mt-3 flex items-center gap-1.5 text-[12px] text-white/70">
                    <Activity className="size-3.5" />
                    {d.key === "web" ? "Always on" : d.seen ? `Last activity ${since(d.seen)}` : "No activity yet"}
                  </p>
                </div>
              ))}
            </div>
          </section>

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <AccountTile label="Account" value={data.username || "—"} hint={data.sandbox ? "Sandbox: free test traffic, simulator only" : "Live: real handsets and billing"} />
            <AccountTile
              label="API key"
              value={data.configured ? "Connected" : "Not configured"}
              ok={data.configured}
              hint={data.configured ? "AT_USERNAME + AT_API_KEY set" : "Set AT_USERNAME and AT_API_KEY — the demo runs in dry-run mode until then"}
            />
            <AccountTile
              label="Webhook secret"
              value={data.webhook_secret ? "Protected" : "Not set"}
              ok={data.webhook_secret}
              hint={data.webhook_secret ? "Callback URLs carry a secret path" : "Set AT_WEBHOOK_SECRET so nobody can forge callbacks"}
            />
            <AccountTile
              label="Balance"
              value={withBalance ? (isFetching ? "Checking…" : data.balance ?? "Unavailable") : "—"}
              hint={withBalance ? (data.balance ? "From the AT user endpoint" : "Needs a configured API key") : "Press “Check balance”"}
            />
          </div>

          {local && (
            <Callout tone="warning" title="Callback URLs point at localhost">
              Africa&apos;s Talking can&apos;t reach your laptop. Expose port 3000 with a tunnel (ngrok or cloudflared), set PUBLIC_URL to the tunnel address and
              restart — these URLs update automatically.
            </Callout>
          )}

          <section>
            <div className="mb-3 flex items-baseline justify-between gap-3">
              <h2 className="text-lg font-bold tracking-tight">Products</h2>
              <p className="text-[13px] text-ink-2">
                {ready} of {data.products.length} ready · paste each URL into the AT dashboard
              </p>
            </div>
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              {data.products.map((p) => (
                <ProductCard key={p.key} p={p} seen={PRODUCT_META[p.key]?.seen ? data.last_seen[PRODUCT_META[p.key].seen as string] : undefined} />
              ))}
            </div>
          </section>

          <section className="overflow-hidden rounded-2xl border border-line-soft bg-white">
            <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line-soft px-5 py-4">
              <div>
                <h2 className="flex items-center gap-2 text-[15px] font-bold">
                  <Server className="size-4" /> Scheduler health
                </h2>
                <p className="mt-0.5 text-[13px] text-ink-2">The background jobs that send the timeline, release codes and keep calendars in sync.</p>
              </div>
            </header>
            {data.jobs.length === 0 ? (
              <div className="p-5">
                <Callout tone="warning" title="The scheduler hasn't run yet">
                  Start it with <code className="rounded bg-white px-1.5 py-0.5 font-mono text-[12.5px] text-ink">python manage.py run_scheduler</code> (or
                  run <code className="rounded bg-white px-1.5 py-0.5 font-mono text-[12.5px] text-ink">manage.py tick</code> from cron) — without it no automated SMS,
                  door codes or iCal syncs go out. In the Demo Lab you can tick it by hand.
                </Callout>
              </div>
            ) : (
              <Table head={["Job", "Schedule", "Last run", "Status", "Runs"]}>
                {[...data.jobs]
                  .sort((a, b) => Object.keys(JOBS).indexOf(a.key) - Object.keys(JOBS).indexOf(b.key))
                  .map((j) => {
                    const meta = JOBS[j.key];
                    const stale = !!(meta?.minutes && j.last_run_at && (new Date().getTime() - new Date(j.last_run_at).getTime()) / 60000 > meta.minutes);
                    return (
                      <Tr key={j.key}>
                        <Td>
                          <span className="font-semibold">{meta?.label ?? humanize(j.key)}</span>
                          <span className="block font-mono text-[11.5px] text-ink-3">{j.key}</span>
                        </Td>
                        <Td className="text-ink-2">{meta?.every ?? "—"}</Td>
                        <Td className="whitespace-nowrap">
                          {j.last_run_at ? (
                            <Tooltip content={fmtDateTime(j.last_run_at)}>
                              <span className={cn(stale && "font-semibold text-warning")}>{since(j.last_run_at)}</span>
                            </Tooltip>
                          ) : (
                            <span className="text-ink-3">Never</span>
                          )}
                        </Td>
                        <Td>
                          {j.ok ? (
                            <Badge tone={stale ? "warning" : "success"} dot>
                              {stale ? "Stale" : "Healthy"}
                            </Badge>
                          ) : (
                            <Badge tone="danger" dot>
                              Failed
                            </Badge>
                          )}
                        </Td>
                        <Td className="tabular-nums">{j.runs.toLocaleString()}</Td>
                      </Tr>
                    );
                  })}
              </Table>
            )}
          </section>
        </div>
      )}
    </>
  );
}

function AccountTile({ label, value, hint, ok }: { label: string; value: React.ReactNode; hint?: string; ok?: boolean }) {
  return (
    <div className="rounded-2xl border border-line-soft bg-white p-4">
      <p className="text-[12px] font-semibold tracking-wide text-ink-2 uppercase">{label}</p>
      <p className="mt-1 flex items-center gap-1.5 text-[17px] font-bold">
        {ok === true && <CircleCheck className="size-4 text-success" />}
        {ok === false && <CircleDashed className="size-4 text-warning" />}
        <span className="truncate">{value}</span>
      </p>
      {hint && <p className="mt-1 text-[12.5px] leading-snug text-ink-2">{hint}</p>}
    </div>
  );
}

function ProductCard({ p, seen }: { p: AtProduct; seen?: string | null }) {
  const meta = PRODUCT_META[p.key] ?? { icon: KeyRound, where: "AT dashboard", blurb: "" };
  const callbacks = Object.entries(p.callbacks);
  return (
    <article className="flex min-w-0 flex-col rounded-2xl border border-line-soft bg-white p-5">
      <div className="flex items-start gap-3">
        <span className={cn("grid size-10 shrink-0 place-items-center rounded-xl", p.ready ? "bg-success-50 text-success" : "bg-surface text-ink-2")}>
          <meta.icon className="size-5" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-[15px] font-bold">{p.name}</h3>
            {p.ready ? (
              <Badge tone="success">
                <CircleCheck className="size-3" /> Ready
              </Badge>
            ) : (
              <Badge tone="warning">
                <CircleX className="size-3" /> Needs setup
              </Badge>
            )}
          </div>
          <p className="mt-0.5 text-[13px] text-ink-2">{meta.blurb}</p>
        </div>
      </div>
      <dl className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[12.5px]">
        <div>
          <dt className="inline text-ink-3">Setting: </dt>
          <dd className="inline font-medium [overflow-wrap:anywhere]">{p.detail}</dd>
        </div>
        {meta.seen && (
          <div>
            <dt className="inline text-ink-3">Last activity: </dt>
            <dd className="inline font-medium">{seen ? since(seen) : "none yet"}</dd>
          </div>
        )}
      </dl>
      {callbacks.length > 0 ? (
        <div className="mt-4 space-y-2.5 border-t border-line-soft pt-4">
          <p className="text-[12px] font-semibold text-ink-2">
            Paste into <span className="text-ink">{meta.where}</span>
          </p>
          {callbacks.map(([label, url]) => (
            <div key={label}>
              <p className="mb-1 text-[12px] font-medium text-ink-2">{label}</p>
              <CopyField value={url} label={`Copy ${label}`} />
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-4 border-t border-line-soft pt-4 text-[12.5px] text-ink-2">No callback needed.</p>
      )}
    </article>
  );
}
