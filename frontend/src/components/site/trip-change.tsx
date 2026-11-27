"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, CalendarClock, Clock } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { usePayOptions } from "@/components/providers";
import { GuestPicker, type Guests } from "@/components/site/guest-picker";
import { FailureNotice, PaybillBox } from "@/components/site/payment-help";
import { RangeCalendar, type Range } from "@/components/site/range-calendar";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { Field, Textarea } from "@/components/ui/input";
import { Spinner } from "@/components/ui/misc";
import { get, post, qs } from "@/lib/api";
import { fmtDate, fmtRange, iso, kes, nightsBetween, plural, toDate } from "@/lib/format";
import type { CalendarData, ChangeQuote, ChangeRequest, ListingDetail, PaymentResult, Trip } from "@/lib/types";
import { cn } from "@/lib/utils";

const PENDING = ["pending_host", "pending_payment"];

function addDays(d: string, n: number) {
  const x = toDate(d);
  x.setDate(x.getDate() + n);
  return iso(x);
}

/** Nights a booking occupies, so the guest can move within (or overlap) their own dates. */
function ownNights(t: Trip) {
  const out = new Set<string>();
  for (let d = t.check_in; d < t.check_out; d = addDays(d, 1)) out.add(d);
  return out;
}

function afterChange(qc: ReturnType<typeof useQueryClient>, ref: string, r: { change: ChangeRequest; payment: PaymentResult | null; trip: Trip }) {
  qc.setQueryData(["trip", ref], r.trip);
  if (r.payment?.method === "card" && r.payment.checkout_url) {
    window.location.href = r.payment.checkout_url;
    return;
  }
  if (r.change.status === "applied") toast.success("Done — your stay is updated. We've sent the details by SMS.");
  else if (r.change.status === "pending_payment")
    toast.success(r.payment?.method === "mpesa" ? `M-Pesa prompt sent for ${kes(r.change.pay_now)} — your new dates are confirmed the moment you pay.` : `Pay ${kes(r.change.pay_now)} to confirm your new dates.`);
  else if (r.change.status === "pending_host") toast.success("Request sent — Amina will reply by SMS, usually within the hour.");
  else toast.message(r.change.status_label);
}

/** "Change dates or guests" (before arrival) or "Extend your stay" (in-house), priced live before the guest commits. */
export function ChangeTrip({ trip: t }: { trip: Trip }) {
  const qc = useQueryClient();
  const inHouse = t.status === "checked_in";
  const [open, setOpen] = React.useState(false);
  const [range, setRange] = React.useState<Range>({ from: t.check_in, to: t.check_out });
  const [guests, setGuests] = React.useState<Guests>({ adults: t.adults, children: t.children, infants: t.infants });
  const [note, setNote] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const { data: listing } = useQuery({ queryKey: ["listing", t.unit.slug], queryFn: () => get<ListingDetail>(`/api/listings/${t.unit.slug}`), enabled: open });
  const { data: cal } = useQuery({ queryKey: ["calendar", t.unit.slug], queryFn: () => get<CalendarData>(`/api/listings/${t.unit.slug}/calendar`), enabled: open });
  const unavailable = React.useMemo(() => {
    const mine = ownNights(t);
    return new Set((cal?.unavailable ?? []).filter((d) => !mine.has(d)));
  }, [cal, t]);

  const ready = !!(range.from && range.to);
  const changed = ready && (range.from !== t.check_in || range.to !== t.check_out || guests.adults !== t.adults || guests.children !== t.children);
  const params = { check_in: range.from, check_out: range.to, adults: guests.adults, children: guests.children };
  const { data: q, isFetching, error } = useQuery({
    queryKey: ["change-quote", t.ref, params],
    queryFn: () => get<ChangeQuote>(`/api/bookings/${t.ref}/change${qs(params)}`),
    enabled: open && changed,
    retry: false,
  });

  function reset(o: boolean) {
    setOpen(o);
    if (o) {
      setRange({ from: t.check_in, to: t.check_out });
      setGuests({ adults: t.adults, children: t.children, infants: t.infants });
      setNote("");
    }
  }

  async function submit() {
    setBusy(true);
    try {
      const r = await post<{ change: ChangeRequest; payment: PaymentResult | null; trip: Trip }>(`/api/bookings/${t.ref}/change`, { ...params, note });
      setOpen(false);
      afterChange(qc, t.ref, r);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const cta = !q ? "Check the price" : !q.available ? "Not available" : !q.instant ? "Send request to Amina" : q.pay_now > 0 ? `Confirm and pay ${kes(q.pay_now)}` : "Confirm change";

  return (
    <Dialog open={open} onOpenChange={reset}>
      <DialogTrigger asChild>
        <Button variant="soft" size="sm"><CalendarClock className="size-4" /> {inHouse ? "Extend your stay" : "Change dates or guests"}</Button>
      </DialogTrigger>
      <DialogContent title={inHouse ? "Extend your stay" : "Change your reservation"} size="md">
        <div className="space-y-6 p-6">
          {inHouse ? (
            <div>
              <p className="text-[15px] text-ink-2">Stay longer at {t.unit.name}. You check out on {fmtDate(t.check_out, "EEEE d MMM")} at the moment.</p>
              <div className="mt-4 flex flex-wrap gap-2">
                {[1, 2, 3, 7].map((n) => {
                  const to = addDays(t.check_out, n);
                  return (
                    <button key={n} type="button" onClick={() => setRange({ from: t.check_in, to })}
                      className={cn("rounded-full border px-4 py-2 text-sm font-medium", range.to === to ? "border-ink bg-ink text-white" : "border-line hover:border-ink")}>
                      +{plural(n, "night")}
                    </button>
                  );
                })}
              </div>
            </div>
          ) : (
            <>
              <div>
                <p className="mb-3 text-sm font-semibold">Dates</p>
                {cal ? (
                  <RangeCalendar value={range} onChange={setRange} unavailable={unavailable} prices={cal.prices} minNights={listing?.min_nights ?? 1} months={1} />
                ) : (
                  <div className="grid h-72 place-items-center"><Spinner /></div>
                )}
              </div>
              <div>
                <p className="text-sm font-semibold">Guests</p>
                <GuestPicker value={guests} onChange={setGuests} max={listing?.max_guests ?? t.guests} />
              </div>
            </>
          )}

          <div className="rounded-2xl border border-line-soft p-4">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="text-ink-2">{fmtRange(t.check_in, t.check_out)} · {plural(t.guests, "guest")}</span>
              <ArrowRight className="size-4 text-ink-3" />
              <span className="font-semibold">{ready ? `${fmtRange(range.from, range.to)} · ${plural(guests.adults + guests.children, "guest")}` : "Pick new dates"}</span>
            </div>
            {!changed ? (
              <p className="mt-3 text-sm text-ink-2">Choose new dates or guests to see the price.</p>
            ) : isFetching && !q ? (
              <p className="mt-3 flex items-center gap-2 text-sm text-ink-2"><Spinner className="size-4" /> Checking availability…</p>
            ) : error ? (
              <p className="mt-3 text-sm text-danger">{(error as Error).message}</p>
            ) : q && !q.available ? (
              <p className="mt-3 text-sm text-danger">{q.reason || "Those dates aren't available."}</p>
            ) : q ? (
              <div className="mt-3 space-y-1.5 text-[15px]">
                {q.lines.map((l) => (
                  <div key={l.label} className={cn("flex justify-between gap-4", l.amount < 0 && "text-success")}>
                    <span className={l.amount < 0 ? undefined : "text-ink-2"}>{l.label}</span>
                    <span className="shrink-0 whitespace-nowrap">{l.amount < 0 ? `−${kes(-l.amount)}` : kes(l.amount)}</span>
                  </div>
                ))}
                <div className="flex justify-between gap-4 border-t border-line-soft pt-2"><span>New total ({plural(q.nights || nightsBetween(range.from, range.to), "night")})</span><b>{kes(q.new_total)}</b></div>
                <div className="flex justify-between gap-4 text-sm text-ink-2"><span>Current total</span><span>{kes(q.old_total)}</span></div>
                <p className={cn("pt-2 font-semibold", q.delta > 0 ? "text-ink" : "text-success")}>
                  {q.delta > 0 ? `You pay ${kes(q.pay_now)} more` : q.delta < 0 ? (q.refund > 0 ? `We refund ${kes(q.refund)}` : "No refund under your cancellation policy") : "No change in price"}
                </p>
                {q.delta < 0 && q.policy_text && <p className="text-xs text-ink-2">{q.policy_text}</p>}
                {!q.instant && <p className="text-xs text-ink-2">Amina confirms changes personally — you only pay once she says yes.</p>}
              </div>
            ) : null}
          </div>

          <Field label="Note for Amina (optional)"><Textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Our flight moved to Saturday" className="min-h-16" /></Field>
          <Button className="w-full" size="lg" variant="brand" disabled={!q?.available || !changed || isFetching} loading={busy} onClick={submit}>{cta}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/** A change waiting on the guest's payment or on Amina's answer. */
export function PendingChange({ trip: t }: { trip: Trip }) {
  const qc = useQueryClient();
  const [busy, setBusy] = React.useState<string | null>(null);
  const { mpesa } = usePayOptions();
  const c = t.changes?.find((x) => PENDING.includes(x.status));
  if (!c) return null;
  const lastPay = t.payments.find((p) => p.purpose === "change");
  const failed = c.status === "pending_payment" && lastPay?.status === "failed" ? lastPay : undefined;

  async function act(kind: "mpesa" | "card" | "cancel") {
    setBusy(kind);
    try {
      if (kind === "cancel") {
        qc.setQueryData(["trip", t.ref], await post<Trip>(`/api/bookings/${t.ref}/change/${c!.id}/cancel`));
        toast.success("Change withdrawn — your original booking stands.");
      } else {
        const r = await post<PaymentResult>(`/api/bookings/${t.ref}/change/${c!.id}/pay`, { method: kind });
        if (r.method === "card" && r.checkout_url) window.location.href = r.checkout_url;
        else toast.success(r.message || "M-Pesa prompt sent — check your phone.");
        await qc.invalidateQueries({ queryKey: ["trip", t.ref] });
      }
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="mt-6 flex items-start gap-4 rounded-2xl border border-warning/30 bg-warning-50 p-5">
      <Clock className="mt-0.5 size-6 shrink-0 text-warning" />
      <div className="min-w-0 flex-1">
        <p className="font-semibold">{c.status === "pending_payment" ? `Pay ${kes(c.pay_now)} to confirm your new dates` : "Change requested — waiting for Amina"}</p>
        <p className="mt-1 text-sm text-ink-2">
          {fmtRange(c.old.check_in, c.old.check_out)} → <b className="text-ink">{fmtRange(c.new.check_in, c.new.check_out)}</b> · {plural(c.new.adults + c.new.children, "guest")}
          {c.status === "pending_host" && " · you only pay once she says yes"}
        </p>
        {failed && (
          <div className="mt-3">
            <FailureNotice payment={failed} busy={busy} onRetry={mpesa ? () => act("mpesa") : undefined} onCard={() => act("card")} />
          </div>
        )}
        <div className="mt-3 flex flex-wrap gap-2">
          {c.status === "pending_payment" && !failed && (mpesa ? (
            <>
              <Button size="sm" variant="dark" loading={busy === "mpesa"} disabled={!!busy} onClick={() => act("mpesa")}>Pay with M-Pesa</Button>
              <Button size="sm" variant="soft" loading={busy === "card"} disabled={!!busy} onClick={() => act("card")}>Card</Button>
            </>
          ) : (
            <Button size="sm" variant="dark" loading={busy === "card"} disabled={!!busy} onClick={() => act("card")}>{`Pay ${kes(c.pay_now)} by card`}</Button>
          ))}
          <Button size="sm" variant="ghost" loading={busy === "cancel"} disabled={!!busy} onClick={() => act("cancel")}>Withdraw</Button>
        </div>
        {c.status === "pending_payment" && (
          <div className="mt-3"><PaybillBox bookingRef={t.ref} amount={c.pay_now} defaultOpen={failed?.suggest === "paybill"} /></div>
        )}
      </div>
    </div>
  );
}
