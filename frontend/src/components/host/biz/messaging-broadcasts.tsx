"use client";

import { useQuery } from "@tanstack/react-query";
import { BedDouble, CalendarClock, Droplets, History, Hourglass, Megaphone, PartyPopper, Send, UserRound, Users, Zap, type LucideIcon } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { ErrorBlock, LoadingBlock, Table, Td, Tr } from "@/components/host/common";
import { Button } from "@/components/ui/button";
import { Select, Textarea } from "@/components/ui/input";
import { Badge } from "@/components/ui/misc";
import { Tooltip } from "@/components/ui/overlays";
import { get, post } from "@/lib/api";
import { fmtDateTime, plural } from "@/lib/format";
import { cn } from "@/lib/utils";

import { useHostSettings, useInvalidateHost, useListings } from "./queries";
import { smsInfo, toGsm } from "./sms";
import type { Audience, BroadcastRow } from "./types";
import { Callout, ConfirmDialog, Field, PhonePreview, SmsMeter, SwitchRow, TableCard, errorMessage } from "./ui";

const AUDIENCES: { value: Audience; title: string; text: string; icon: LucideIcon }[] = [
  { value: "in_house", title: "Staying now", text: "Guests checked in right now", icon: BedDouble },
  { value: "arriving", title: "Arriving soon", text: "Confirmed, arriving within 7 days", icon: CalendarClock },
  { value: "upcoming", title: "All upcoming", text: "Every confirmed or in-house guest", icon: Users },
  { value: "past", title: "Past guests", text: "Opted-in direct guests only", icon: History },
  { value: "waitlist", title: "Waitlist", text: "Waiting for dates to free up", icon: Hourglass },
  { value: "staff", title: "Your team", text: "Cleaners, cook, caretaker, security", icon: UserRound },
];

const PRESETS: { title: string; icon: LucideIcon; audience: Audience; marketing: boolean; body: string }[] = [
  {
    title: "Power outage — generator on",
    icon: Zap,
    audience: "in_house",
    marketing: false,
    body: "Hi from Amina Stays: Kenya Power has an outage in the area today. Our backup generator is on, so lights, Wi-Fi and the fridge keep working - please switch off the AC and water heater until mains power is back. Reply HELP if anything stops working.",
  },
  {
    title: "Water interruption — tank full",
    icon: Droplets,
    audience: "in_house",
    marketing: false,
    body: "Hi from Amina Stays: the county water supply is off in the area today. Our tank is full, so taps and showers work as normal - please keep showers short until supply is back. Reply HELP if the pressure drops.",
  },
  {
    title: "Festive season offer",
    icon: PartyPopper,
    audience: "past",
    marketing: true,
    body: "Karibu tena from Amina Stays! The coast is calling this festive season - book 3+ nights direct between 18 Dec and 3 Jan and breakfast is on us. Reply BOOK to see which homes are free.",
  },
];

const pad = (h: number) => `${String(h).padStart(2, "0")}:00`;
const STOP = " Reply STOP to opt out.";

export function BroadcastsTab() {
  const invalidate = useInvalidateHost();
  const { data: listings } = useListings();
  const { data: settings } = useHostSettings();
  const history = useQuery({ queryKey: ["host", "broadcasts"], queryFn: () => get<BroadcastRow[]>("/api/host/broadcasts") });
  const [audience, setAudience] = React.useState<Audience>("in_house");
  const [unit, setUnit] = React.useState("");
  const [body, setBody] = React.useState("");
  const [marketingSwitch, setMarketing] = React.useState(false);
  const [confirm, setConfirm] = React.useState(false);
  const [sending, setSending] = React.useState(false);

  const unitScoped = audience !== "waitlist" && audience !== "staff";
  const effectiveUnit = unitScoped ? unit : "";
  const marketing = marketingSwitch || audience === "past";
  const preview = useQuery({
    queryKey: ["host", "broadcast-preview", audience, effectiveUnit],
    queryFn: () => post<{ recipients: number }>("/api/host/broadcasts", { audience, unit: effectiveUnit || undefined, preview: true }),
  });
  const recipients = preview.data?.recipients;
  const finalBody = body.trim() + (marketing && body.trim() && !body.toLowerCase().includes("stop") ? STOP : "");
  const info = smsInfo(finalBody);

  const nairobiHour = Number(new Intl.DateTimeFormat("en-GB", { timeZone: "Africa/Nairobi", hour: "2-digit", hourCycle: "h23" }).format(new Date()));
  const promoStart = settings?.promo_window_start ?? 8;
  const promoEnd = settings?.promo_window_end ?? 18;
  const outsideWindow = marketing && !(promoStart <= nairobiHour && nairobiHour < promoEnd);
  const canSend = !!body.trim() && !!recipients && !outsideWindow;

  const send = async () => {
    setSending(true);
    try {
      const r = await post<{ id: number; recipients: number }>("/api/host/broadcasts", {
        audience,
        unit: effectiveUnit || undefined,
        body: body.trim(),
        is_marketing: marketing,
      });
      toast.success(`Sent to ${plural(r.recipients, "person", "people")}`, { description: "Delivery reports appear in each guest's conversation." });
      setBody("");
      setConfirm(false);
      invalidate();
    } catch (e) {
      toast.error(errorMessage(e, "Couldn't send the broadcast."));
    } finally {
      setSending(false);
    }
  };

  const audienceMeta = AUDIENCES.find((a) => a.value === audience);
  const unitName = listings?.find((l) => String(l.id) === effectiveUnit)?.name;

  return (
    <div className="space-y-6">
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <section className="rounded-2xl border border-line-soft bg-white">
          <header className="border-b border-line-soft px-5 py-4 sm:px-6">
            <h2 className="flex items-center gap-2 text-[17px] font-bold tracking-tight">
              <Megaphone className="size-5" /> New broadcast
            </h2>
            <p className="mt-0.5 text-[13.5px] text-ink-2">One SMS to many guests — works on every phone, no app or data needed.</p>
          </header>
          <div className="space-y-5 px-5 py-5 sm:px-6">
            <div>
              <p className="mb-2 text-[12px] font-semibold tracking-wide text-ink-2 uppercase">Start from a template</p>
              <div className="grid gap-2 sm:grid-cols-3">
                {PRESETS.map((p) => (
                  <button
                    key={p.title}
                    type="button"
                    onClick={() => {
                      setAudience(p.audience);
                      setMarketing(p.marketing);
                      setBody(p.body);
                    }}
                    className="flex items-center gap-2.5 rounded-xl border border-line-soft px-3 py-2.5 text-left text-[13px] font-semibold transition hover:border-ink-3 hover:bg-surface/60"
                  >
                    <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-surface">
                      <p.icon className="size-4" />
                    </span>
                    {p.title}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <p className="mb-2 text-[13px] font-semibold">Who gets it</p>
              <div role="radiogroup" aria-label="Audience" className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {AUDIENCES.map((a) => {
                  const active = a.value === audience;
                  return (
                    <button
                      key={a.value}
                      type="button"
                      role="radio"
                      aria-checked={active}
                      onClick={() => setAudience(a.value)}
                      className={cn(
                        "flex items-start gap-3 rounded-xl border px-3.5 py-3 text-left transition",
                        active ? "border-ink ring-1 ring-ink" : "border-line-soft hover:border-ink-3",
                      )}
                    >
                      <a.icon className={cn("mt-0.5 size-[18px] shrink-0", active ? "text-ink" : "text-ink-2")} />
                      <span>
                        <span className="block text-[14px] font-semibold">{a.title}</span>
                        <span className="block text-[12.5px] leading-snug text-ink-2">{a.text}</span>
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
              <Field label="Which homes" hint={unitScoped ? undefined : "Not used for the waitlist or your team."}>
                <Select value={effectiveUnit} onChange={(e) => setUnit(e.target.value)} disabled={!unitScoped}>
                  <option value="">All homes</option>
                  {(listings ?? []).map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.name}
                    </option>
                  ))}
                </Select>
              </Field>
              <div className="flex h-11 items-center gap-2 rounded-lg bg-surface px-4 text-[14px]" aria-live="polite">
                <Users className="size-4 text-ink-2" />
                {preview.isFetching && recipients === undefined ? (
                  <span className="text-ink-2">Counting…</span>
                ) : (
                  <span>
                    <b className="tabular-nums">{recipients ?? 0}</b> {recipients === 1 ? "recipient" : "recipients"}
                  </span>
                )}
              </div>
            </div>

            <Field label="Message">
              <Textarea value={body} onChange={(e) => setBody(e.target.value)} rows={5} placeholder="Hi from Amina Stays: …" className="text-[15px]" />
            </Field>
            <SmsMeter text={finalBody} onFix={() => setBody(toGsm(body))} />

            <div className="rounded-xl border border-line-soft p-4">
              <SwitchRow
                label="This is a promotion"
                checked={marketing}
                disabled={audience === "past"}
                onCheckedChange={setMarketing}
                description={
                  <>
                    Adds “Reply STOP to opt out”, sends only between {pad(promoStart)} and {pad(promoEnd)}, and skips anyone who opted out.
                    {audience === "past" && " Always on for past guests: only those who opted in are messaged, and Airbnb/Booking.com guests are never contacted off-platform."}
                  </>
                }
              />
            </div>

            {outsideWindow && (
              <Callout tone="warning" title="Outside the promotional window">
                It&apos;s {pad(nairobiHour)} in Mombasa. Promotional SMS can go out between {pad(promoStart)} and {pad(promoEnd)} — schedule this for the morning.
              </Callout>
            )}

            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line-soft pt-4">
              <p className="text-[13px] text-ink-2">
                {!recipients ? (
                  "No one matches this audience right now."
                ) : !body.trim() ? (
                  <>
                    <b className="text-ink tabular-nums">{recipients}</b> {recipients === 1 ? "person" : "people"} will get it — write your message.
                  </>
                ) : (
                  <>
                    ≈ <b className="text-ink tabular-nums">{(recipients * Math.max(info.segments, 1)).toLocaleString()}</b> SMS ({plural(Math.max(info.segments, 1), "part")} ×{" "}
                    {recipients})
                  </>
                )}
              </p>
              <Button variant="brand" onClick={() => setConfirm(true)} disabled={!canSend}>
                <Send className="size-4" /> Review & send
              </Button>
            </div>
          </div>
        </section>

        <aside className="space-y-4 xl:sticky xl:top-6 xl:self-start">
          <PhonePreview text={finalBody || "Your message appears here."} footer={`${info.encoding} · ${plural(Math.max(info.segments, 1), "SMS part")}`} />
          <Callout tone="trust">
            Service messages (outages, water, safety) go to everyone affected. Offers respect opt-outs, Kenyan promo hours and OTA rules automatically.
          </Callout>
        </aside>
      </div>

      <TableCard title="Sent broadcasts" description="The last 50, newest first.">
        {history.error ? (
          <div className="p-5">
            <ErrorBlock error={history.error} retry={history.refetch} />
          </div>
        ) : history.isLoading ? (
          <div className="p-5">
            <LoadingBlock rows={3} />
          </div>
        ) : (
          <Table head={["Sent", "Audience", "Message", "Recipients", "Type"]} empty="No broadcasts yet. Your first one will show up here.">
            {(history.data ?? []).map((b) => (
              <Tr key={b.id}>
                <Td className="whitespace-nowrap text-ink-2">{fmtDateTime(b.created_at)}</Td>
                <Td className="whitespace-nowrap">
                  <span className="font-semibold">{b.audience_label}</span>
                  {b.unit && <span className="block text-[12px] text-ink-2">{b.unit}</span>}
                </Td>
                <Td className="max-w-md">
                  <Tooltip content={<span className="block max-w-xs whitespace-pre-wrap">{b.body}</span>}>
                    <span className="line-clamp-2 text-ink-2">{b.body}</span>
                  </Tooltip>
                </Td>
                <Td className="font-semibold tabular-nums">{b.recipients}</Td>
                <Td>{b.is_marketing ? <Badge tone="brand">Promotion</Badge> : <Badge tone="ocean">Service</Badge>}</Td>
              </Tr>
            ))}
          </Table>
        )}
      </TableCard>

      <ConfirmDialog
        open={confirm}
        onOpenChange={setConfirm}
        title={`Send to ${plural(recipients ?? 0, "person", "people")}?`}
        confirmLabel="Send now"
        tone="brand"
        loading={sending}
        onConfirm={send}
      >
        <p>
          <b className="text-ink">{audienceMeta?.title}</b>
          {unitName ? ` at ${unitName}` : unitScoped ? " · all homes" : ""} · {marketing ? "promotion" : "service message"} ·{" "}
          {plural(Math.max(info.segments, 1), "SMS part")} each
        </p>
        <div className="rounded-xl bg-[#f2f2f7] p-3">
          <div className="rounded-[1rem] rounded-bl-[0.3rem] bg-white px-3.5 py-2 text-[14px] leading-snug whitespace-pre-wrap text-ink shadow-sm">{finalBody}</div>
        </div>
        <p className="text-[13px]">SMS can&apos;t be unsent. Replies come back to your inbox.</p>
      </ConfirmDialog>
    </div>
  );
}
