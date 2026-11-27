"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft, BedDouble, CalendarDays, Car, Check, CheckCircle2, ChevronRight, Clock, Copy, CreditCard, Croissant, KeyRound, LifeBuoy, LogOut, MapPin,
  MapPinned, MessageCircle, MessageSquareWarning, Phone, Printer, Receipt, ShieldAlert, ShieldCheck, Siren, Smartphone, Star, UserPlus, Wifi, Wrench,
} from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { Icon } from "@/components/icon";
import { useConfig, useMe, usePayOptions } from "@/components/providers";
import { AuthGate } from "@/components/site/auth-gate";
import { SiteHeader } from "@/components/site/header";
import { Photo } from "@/components/site/listing-card";
import { NearbyPlaces } from "@/components/site/guide-view";
import { FailureNotice, lastFailure, PaybillBox } from "@/components/site/payment-help";
import { ServiceNotices } from "@/components/site/service-notices";
import { SupportPanel } from "@/components/site/support-panel";
import { ChangeTrip, PendingChange } from "@/components/site/trip-change";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { Field, Input, Select, Textarea } from "@/components/ui/input";
import { Badge, Divider, Skeleton, Stepper } from "@/components/ui/misc";
import { api, ApiError, get, patch, post, put } from "@/lib/api";
import { ago, CHANNEL_LABEL, fmtDate, fmtDateTime, fmtLong, hhmm, kes, plural, relDay, STATUS_TONE } from "@/lib/format";
import type { Addon, ListingDetail, PaymentResult, Trip } from "@/lib/types";
import { cn, COUNTRIES } from "@/lib/utils";

const LocationMap = dynamic(() => import("@/components/site/maps").then((m) => m.LocationMap), {
  ssr: false,
  loading: () => <div className="h-[280px] animate-pulse bg-surface" />,
});

const STYLES: Record<string, string> = { swahili: "Swahili — mahamri, chai, mbaazi, fruit", continental: "Continental", english: "Full English", vegetarian: "Vegetarian / vegan" };
const ISSUES = [["water", "Water"], ["power", "Power / electricity"], ["wifi", "Wi-Fi"], ["ac", "Air conditioning / fan"], ["appliance", "Appliance"], ["plumbing", "Plumbing"], ["cleanliness", "Cleanliness"], ["noise", "Noise"], ["lock", "Door / lock"], ["pests", "Insects / pests"], ["other", "Something else"]];
const ADDON_STATUS: Record<string, string> = { requested: "Awaiting Amina", confirmed: "Confirmed", fulfilled: "Done", declined: "Declined", cancelled: "Cancelled" };
const ID_TYPES = [["passport", "Passport"], ["national_id", "Kenyan National ID"], ["alien_id", "Alien / Foreigner ID"], ["driving_licence", "Driving licence"]];

/** What happened to the guest's money on a cancelled or expired stay. */
function cancelledMoney(t: Trip) {
  const { amount_paid: paid, amount_refunded: sent, refund_pending: queued = 0 } = t.price;
  if (t.status === "refund_due") return "Your payment arrived after the hold expired — Amina is refunding you in full.";
  if (sent > 0 && queued > 0) return `${kes(sent)} has been refunded and another ${kes(queued)} is on its way to your original payment method.`;
  if (sent > 0) return `${kes(sent)} has been refunded to your original payment method.`;
  if (queued > 0) return `Your refund of ${kes(queued)} is being sent to your original payment method.`;
  if (paid > 0) return `The ${kes(paid)} you paid isn't refundable under the ${t.cancellation.policy} cancellation policy.`;
  return "No payment was taken.";
}

function due(d?: string | null) {
  const r = relDay(d);
  return r === "Today" || r === "Tomorrow" ? r.toLowerCase() : r;
}

function useNow(ms = 1000) {
  const [now, setNow] = React.useState(() => Date.now());
  React.useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(t);
  }, [ms]);
  return now;
}

function useTripAction(ref: string) {
  const qc = useQueryClient();
  const [busy, setBusy] = React.useState<string | null>(null);
  const run = React.useCallback(async <T,>(key: string, fn: () => Promise<T>, ok?: string) => {
    setBusy(key);
    try {
      const r = await fn();
      if (r && typeof r === "object" && "ref" in (r as object) && "status" in (r as object) && "unit" in (r as object)) qc.setQueryData(["trip", ref], r);
      else await qc.invalidateQueries({ queryKey: ["trip", ref] });
      if (ok) toast.success(ok);
      return r;
    } catch (e) {
      toast.error((e as Error).message);
      return undefined;
    } finally {
      setBusy(null);
    }
  }, [qc, ref]);
  return { busy, run };
}

export function TripView({ tripRef }: { tripRef: string }) {
  return (
    <AuthGate title="Log in to see this trip" subtitle="Use the phone number the booking was made with.">
      <TripHub tripRef={tripRef.toUpperCase()} />
    </AuthGate>
  );
}

function TripHub({ tripRef: ref }: { tripRef: string }) {
  const { data: t, error, isLoading } = useQuery({
    queryKey: ["trip", ref],
    queryFn: () => get<Trip>(`/api/bookings/${ref}`),
    refetchInterval: (q) => (q.state.data?.status === "held" || q.state.data?.payments.some((p) => p.status === "pending") ? 3000 : 30_000),
  });
  const { data: listing } = useQuery({ queryKey: ["listing", t?.unit.slug], queryFn: () => get<ListingDetail>(`/api/listings/${t!.unit.slug}`), enabled: !!t });

  if (isLoading) return <HubSkeleton />;
  if (error || !t) {
    return (
      <>
        <SiteHeader />
        <main className="container-narrow max-w-[720px] py-20 text-center">
          <h1 className="text-2xl font-bold">We couldn&apos;t find that trip</h1>
          <p className="mt-2 text-ink-2">{(error as ApiError | null)?.status === 404 ? "It may belong to a different phone number." : (error as Error)?.message}</p>
          <Button asChild className="mt-8"><Link href="/trips">Back to trips</Link></Button>
        </main>
      </>
    );
  }

  const active = ["confirmed", "checked_in"].includes(t.status);
  return (
    <>
      <SiteHeader />
      <main className="container-narrow max-w-[1160px] pt-6 pb-28 print:pt-0">
        <Link href="/trips" className="inline-flex items-center gap-2 text-sm font-semibold text-ink-2 hover:text-ink print:hidden">
          <ArrowLeft className="size-4" /> Trips
        </Link>
        <Hero trip={t} />
        <div className="mt-10 grid gap-12 lg:grid-cols-[minmax(0,1fr)_380px] lg:gap-16">
          <div className="min-w-0">
            <StatusPanel trip={t} />
            {active && <ServiceNotices unitSlug={t.unit.slug} className="mt-6" />}
            <PendingChange trip={t} />
            {t.status === "checked_in" && <DoorCode trip={t} />}
            {(t.status === "confirmed" || t.status === "held") && <Checklist trip={t} listing={listing} />}
            {active && <CheckinDetails trip={t} />}
            {active && listing?.breakfast_available && <Breakfast trip={t} />}
            {t.can_add_extras && listing && <Extras trip={t} listing={listing} />}
            {active && <Arrival trip={t} />}
            {["held", "confirmed", "checked_in"].includes(t.status) && <Register trip={t} />}
            {t.status === "checked_in" && <HelpDuringStay trip={t} />}
            {active && (
              <Section id="nearby" title="Near your home" icon={<MapPinned className="size-6" />}>
                <NearbyPlaces unitSlug={t.unit.slug} />
              </Section>
            )}
            {(active || t.status === "completed") && (
              <Section id="support" title="Support requests" icon={<MessageSquareWarning className="size-6" />}>
                <SupportPanel booking={t.ref} />
              </Section>
            )}
            {(t.can_review || t.review) && <ReviewSection trip={t} />}
            <Timeline trip={t} />
          </div>
          <aside>
            <div className="space-y-6 lg:sticky lg:top-28">
              <ReceiptCard trip={t} />
              <SupportCard trip={t} />
            </div>
          </aside>
        </div>
      </main>
    </>
  );
}

function Hero({ trip: t }: { trip: Trip }) {
  return (
    <div className="relative mt-4 overflow-hidden rounded-3xl bg-ink">
      <div className="aspect-[16/9] sm:aspect-[21/8]">
        <Photo src={t.unit.photos[0]} alt={t.unit.name} className="size-full opacity-90" sizes="(min-width: 1160px) 1160px, 100vw" priority />
      </div>
      <div className="absolute inset-0 bg-gradient-to-t from-black/75 via-black/20 to-transparent" />
      <div className="absolute inset-x-0 bottom-0 flex flex-wrap items-end justify-between gap-4 p-6 text-white sm:p-8">
        <div>
          <Badge tone={STATUS_TONE[t.status] ?? "neutral"} className="mb-3">{t.status_label}</Badge>
          <h1 className="text-[28px] leading-tight font-bold tracking-tight sm:text-[40px]">{t.unit.name}</h1>
          <p className="mt-1 text-white/85 sm:text-lg">{t.unit.area} · {fmtDate(t.check_in, "EEE d MMM")} – {fmtDate(t.check_out, "EEE d MMM yyyy")} · {plural(t.guests, "guest")}</p>
        </div>
        <div className="text-right text-sm text-white/80">
          <p>Booking ref</p>
          <p className="font-mono text-xl font-bold tracking-wider text-white">{t.ref}</p>
        </div>
      </div>
    </div>
  );
}

function StatusPanel({ trip: t }: { trip: Trip }) {
  const { data: config } = useConfig();
  const { mpesa } = usePayOptions();
  const now = useNow();
  const { busy, run } = useTripAction(t.ref);
  const pay = (method?: "mpesa" | "card", plan?: "deposit") =>
    run(plan ? "deposit" : method === "card" ? "card" : "pay", async () => {
      const r = await post<PaymentResult>(`/api/bookings/${t.ref}/pay`, { method, plan });
      if (r.method === "card" && r.checkout_url) window.location.href = r.checkout_url;
      return r;
    }, method === "card" ? undefined : "M-Pesa prompt sent — check your phone.");
  const failed = lastFailure(t.payments);

  if (t.status === "held") {
    const left = t.hold_expires_at ? Math.max(0, Math.floor((new Date(t.hold_expires_at).getTime() - now) / 1000)) : 0;
    const pending = t.payments.find((p) => p.status === "pending");
    return (
      <Panel tone="warning" icon={<Clock className="size-6" />} title={left ? `We're holding these dates for ${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}` : "Your hold has run out"}>
        <p>
          {!pending
            ? `Pay ${kes(t.price.amount_due_now)} to confirm.`
            : pending.method === "card"
              ? `Waiting for your card payment of ${kes(pending.amount)} — finish it on the secure checkout. This page updates by itself.`
              : `Waiting for your ${pending.method_label} payment of ${kes(pending.amount)}. Enter your PIN on your phone — this page updates by itself.`}
        </p>
        {failed && !pending && (
          <div className="mt-4">
            <FailureNotice payment={failed} busy={busy} onRetry={mpesa ? () => pay("mpesa") : undefined} onCard={() => pay("card")} onDeposit={t.price.payment_plan === "full" ? () => pay(mpesa ? "mpesa" : "card", "deposit") : undefined} />
          </div>
        )}
        <div className="mt-4 flex flex-wrap gap-2">
          {mpesa ? (
            <>
              <Button variant="brand" onClick={() => pay("mpesa")} loading={busy === "pay"}>{pending?.method === "mpesa" ? "Resend M-Pesa prompt" : `Pay ${kes(t.price.amount_due_now)} with M-Pesa`}</Button>
              <Button variant="soft" onClick={() => pay("card")} disabled={!!busy}>Pay by card</Button>
            </>
          ) : (
            <Button variant="brand" onClick={() => pay("card")} loading={busy === "card"} disabled={!!busy}>{`Pay ${kes(t.price.amount_due_now)} by card`}</Button>
          )}
          {config?.demo && <Button variant="ocean" onClick={() => run("sim", () => post(`/api/demo/pay/${t.ref}`), "Payment simulated")} loading={busy === "sim"}>Simulate payment (demo)</Button>}
        </div>
        <div className="mt-4"><PaybillBox bookingRef={t.ref} amount={t.price.amount_due_now} defaultOpen={failed?.suggest === "paybill"} /></div>
      </Panel>
    );
  }
  if (t.status === "confirmed") {
    const days = Math.ceil((new Date(`${t.check_in}T00:00:00`).getTime() - now) / 86_400_000);
    return (
      <Panel tone="ocean" icon={<CalendarDays className="size-6" />} title={days > 1 ? `${days} days to go` : days === 1 ? "See you tomorrow!" : "Arrival day — karibu!"}>
        <p>Check-in from <b>{hhmm(t.checkin.time)}</b> on {fmtLong(t.check_in)} · checkout by <b>{hhmm(t.checkin.checkout_time)}</b>. {t.checkin.method}.</p>
        {t.price.balance_due > 0 && (
          <div className="mt-4 space-y-3">
            <div className="flex flex-wrap items-center gap-3">
              <p className={cn("text-sm", t.price.balance_overdue && "font-semibold text-danger")}>
                {t.price.balance_overdue
                  ? <>Balance <b>{kes(t.price.balance_due)}</b> is overdue — your door code is sent once it&apos;s paid.</>
                  : <>Balance <b>{kes(t.price.balance_due)}</b> due {due(t.price.balance_due_date)}.</>}
              </p>
              {mpesa ? (
                <>
                  <Button size="sm" variant="dark" onClick={() => pay("mpesa")} loading={busy === "pay"}>Pay balance with M-Pesa</Button>
                  <Button size="sm" variant="soft" onClick={() => pay("card")} disabled={!!busy}>Card</Button>
                </>
              ) : (
                <Button size="sm" variant="dark" onClick={() => pay("card")} loading={busy === "card"} disabled={!!busy}>Pay balance by card</Button>
              )}
              {config?.demo && <Button size="sm" variant="ocean" onClick={() => run("sim", () => post(`/api/demo/pay/${t.ref}`), "Payment simulated")}>Simulate (demo)</Button>}
            </div>
            {failed && failed.purpose !== "change" && <FailureNotice payment={failed} busy={busy} onRetry={mpesa ? () => pay("mpesa") : undefined} onCard={() => pay("card")} />}
            <PaybillBox bookingRef={t.ref} amount={t.price.balance_due} defaultOpen={failed?.suggest === "paybill"} />
          </div>
        )}
      </Panel>
    );
  }
  if (t.status === "checked_in") {
    return (
      <Panel tone="success" icon={<BedDouble className="size-6" />} title="Welcome — enjoy your stay">
        <p>Checkout is by <b>{hhmm(t.checkin.checkout_time)}</b> on {fmtLong(t.check_out)}. Need anything? Message Amina or use the help options below.</p>
        <CheckoutButton trip={t} />
      </Panel>
    );
  }
  if (t.status === "completed") {
    return (
      <Panel tone="neutral" icon={<CheckCircle2 className="size-6" />} title="Thanks for staying with Amina">
        <p>Your stay ended on {fmtLong(t.check_out)}. We&apos;d love to have you back on the coast.</p>
        <Button asChild size="sm" variant="dark" className="mt-4"><Link href={`/stays/${t.unit.slug}`}>Book again</Link></Button>
      </Panel>
    );
  }
  return (
    <Panel tone="danger" icon={<ShieldAlert className="size-6" />} title={t.status === "expired" ? "This hold expired" : t.status_label}>
      <p>
        {cancelledMoney(t)}
      </p>
      <Button asChild size="sm" variant="dark" className="mt-4"><Link href={`/stays/${t.unit.slug}`}>Check other dates</Link></Button>
    </Panel>
  );
}

function Panel({ tone, icon, title, children }: { tone: "warning" | "ocean" | "success" | "neutral" | "danger"; icon: React.ReactNode; title: string; children: React.ReactNode }) {
  const tones = {
    warning: "bg-warning-50 border-warning/20 [&_.ico]:bg-warning [&_.ico]:text-white",
    ocean: "bg-ocean-50 border-ocean-600/15 [&_.ico]:bg-ocean-600 [&_.ico]:text-white",
    success: "bg-success-50 border-success/20 [&_.ico]:bg-success [&_.ico]:text-white",
    neutral: "bg-surface border-line-soft [&_.ico]:bg-ink [&_.ico]:text-white",
    danger: "bg-danger-50 border-danger/20 [&_.ico]:bg-danger [&_.ico]:text-white",
  };
  return (
    <section className={cn("flex gap-4 rounded-2xl border p-5 sm:p-6", tones[tone])}>
      <span className="ico grid size-11 shrink-0 place-items-center rounded-full">{icon}</span>
      <div className="min-w-0 flex-1 text-[15px] text-ink-2 [&_b]:text-ink">
        <h2 className="text-xl font-bold text-ink">{title}</h2>
        <div className="mt-1">{children}</div>
      </div>
    </section>
  );
}

function Section({ id, title, icon, children, action }: { id?: string; title: string; icon?: React.ReactNode; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <section id={id} className="scroll-mt-24 border-b border-line-soft py-9 last:border-0">
      <div className="mb-5 flex items-center justify-between gap-4">
        <h2 className="flex items-center gap-3 text-[22px] font-bold tracking-tight">{icon}{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

function Checklist({ trip: t, listing }: { trip: Trip; listing?: ListingDetail }) {
  const items = [
    { done: t.price.balance_due === 0 && t.status !== "held", label: t.price.balance_due === 0 ? "Paid in full" : `Pay the balance (${kes(t.price.balance_due)})`, hint: t.price.balance_due ? `Due ${due(t.price.balance_due_date)}` : "Thank you!", href: "#receipt" },
    { done: t.id_registered, label: t.id_registered ? "Guest register complete" : "Add your ID for the guest register", hint: t.require_id ? "Needed before your door code is sent" : "Required by Kenyan tourism law", href: "#register" },
    ...(listing?.breakfast_available ? [{ done: !!t.breakfast, label: t.breakfast ? `Breakfast: ${t.breakfast.summary}` : "Choose breakfast (optional)", hint: "Freshly made by Mama Zawadi", href: "#breakfast" }] : []),
    { done: !!t.arrival.eta, label: t.arrival.eta ? `Arriving around ${t.arrival.eta}` : "Tell us when you'll arrive", hint: "So someone's ready to welcome you", href: "#arrival" },
  ];
  const done = items.filter((i) => i.done).length;
  return (
    // the breakfast item depends on the listing, so count only once it has loaded (no "2 of 3" → "3 of 4" jump)
    <Section title="Before you arrive" action={listing && <span className="text-sm font-semibold text-ink-2">{done} of {items.length} done</span>}>
      <div className="h-1.5 overflow-hidden rounded-full bg-line-soft"><div className="h-full rounded-full bg-success transition-all" style={{ width: listing ? `${(done / items.length) * 100}%` : 0 }} /></div>
      <ul className="mt-5 divide-y divide-line-soft">
        {items.map((i) => (
          <li key={i.href}>
            <a href={i.href} className="flex items-center gap-4 py-3.5 hover:opacity-80">
              <span className={cn("grid size-7 shrink-0 place-items-center rounded-full border-2", i.done ? "border-success bg-success text-white" : "border-line")}>
                {i.done && <Check className="size-4" strokeWidth={3} />}
              </span>
              <span className="min-w-0 flex-1">
                <span className={cn("block font-semibold", i.done && "text-ink-2")}>{i.label}</span>
                <span className="block text-sm text-ink-2">{i.hint}</span>
              </span>
              {!i.done && <ChevronRight className="size-5 text-ink-2" />}
            </a>
          </li>
        ))}
      </ul>
      <p className="mt-4 flex items-start gap-2 rounded-xl bg-surface p-4 text-sm text-ink-2">
        <KeyRound className="mt-0.5 size-4 shrink-0 text-ink" />
        Your door code arrives by SMS on the morning of {fmtDate(t.check_in, "EEEE d MMM")} — once the balance is paid and the guest register is complete.{" "}
        {t.checkin.details_visible ? <>Directions and Wi-Fi are <a href="#checkin" className="font-semibold text-ink underline">below</a>.</> : <>Directions and Wi-Fi unlock here {fmtDateTime(t.checkin.reveal_at)}.</>}
      </p>
    </Section>
  );
}

function DoorCode({ trip: t }: { trip: Trip }) {
  const c = t.checkin;
  return (
    <section className="mt-6 overflow-hidden rounded-2xl bg-ink text-white">
      <div className="flex flex-wrap items-center justify-between gap-6 p-6 sm:p-8">
        <div>
          <p className="flex items-center gap-2 text-sm font-semibold text-white/70"><KeyRound className="size-4" /> Your door code</p>
          {c.code ? (
            <>
              <p className="mt-2 font-mono text-5xl font-bold tracking-[0.3em] tabular-nums">{c.code}</p>
              <p className="mt-2 text-sm text-white/70">Valid {fmtDateTime(c.code_valid_from)} – {fmtDateTime(c.code_valid_until)}</p>
            </>
          ) : (
            <p className="mt-2 max-w-md text-white/80">Your code will appear here and by SMS as soon as it&apos;s released{t.price.balance_due ? " — the balance needs paying first" : !t.id_registered ? " — add your ID to the guest register first" : ""}.</p>
          )}
        </div>
        {c.code && (
          <Button variant="soft" className="bg-white/10 text-white border-white/20 hover:border-white" onClick={() => navigator.clipboard?.writeText(c.code!).then(() => toast.success("Copied"))}>
            <Copy className="size-4" /> Copy
          </Button>
        )}
      </div>
      {c.wifi_name && (
        <div className="flex flex-wrap gap-x-10 gap-y-2 border-t border-white/10 px-6 py-4 text-sm sm:px-8">
          <span className="flex items-center gap-2"><Wifi className="size-4 text-white/60" /> {c.wifi_name}</span>
          <span>Password <b className="font-mono">{c.wifi_password}</b></span>
        </div>
      )}
    </section>
  );
}

function CheckinDetails({ trip: t }: { trip: Trip }) {
  const c = t.checkin;
  return (
    <Section id="checkin" title="Getting there & checking in" icon={<MapPin className="size-6" />}>
      {c.address && (
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="font-semibold">Address</p>
            <p className="text-ink-2">{c.address}</p>
          </div>
          {c.map_link && <Button asChild variant="soft" size="sm"><a href={c.map_link} target="_blank" rel="noreferrer">Open in Maps</a></Button>}
        </div>
      )}
      {c.location && <div className="mt-5 overflow-hidden rounded-2xl"><LocationMap lat={c.location.lat} lng={c.location.lng} exact height={280} /></div>}
      {c.details_visible ? (
        <dl className="mt-6 grid gap-6 sm:grid-cols-2">
          {c.directions && <Detail icon={<MapPin className="size-5" />} label="Directions" text={c.directions} wide />}
          {c.landmark && <Detail icon={<MapPin className="size-5" />} label="Look out for" text={c.landmark} />}
          {c.parking && <Detail icon={<Car className="size-5" />} label="Parking" text={c.parking} />}
          {c.wifi_name && <Detail icon={<Wifi className="size-5" />} label="Wi-Fi" text={`${c.wifi_name} · password ${c.wifi_password}`} />}
          <Detail icon={<KeyRound className="size-5" />} label="Check-in" text={`${c.method}. From ${hhmm(c.time)}; checkout by ${hhmm(c.checkout_time)}.`} />
          {c.house_manual && <Detail icon={<BedDouble className="size-5" />} label="House manual" text={c.house_manual} wide />}
          {c.local_tips && <Detail icon={<Star className="size-5" />} label="Amina's local tips" text={c.local_tips} wide />}
        </dl>
      ) : (
        <p className="mt-5 flex items-start gap-3 rounded-xl border border-dashed border-line p-4 text-[15px] text-ink-2">
          <Clock className="mt-0.5 size-5 shrink-0" />
          Directions, Wi-Fi and the house manual unlock here {fmtDateTime(c.reveal_at)} — 48 hours before check-in. We&apos;ll text you too.
        </p>
      )}
    </Section>
  );
}

function Detail({ icon, label, text, wide }: { icon: React.ReactNode; label: string; text: string; wide?: boolean }) {
  return (
    <div className={cn("flex gap-3", wide && "sm:col-span-2")}>
      <span className="mt-0.5 text-ink-2">{icon}</span>
      <div><dt className="font-semibold">{label}</dt><dd className="mt-0.5 whitespace-pre-line text-ink-2">{text}</dd></div>
    </div>
  );
}

function Breakfast({ trip: t }: { trip: Trip }) {
  const { busy, run } = useTripAction(t.ref);
  const b = t.breakfast;
  const [editing, setEditing] = React.useState(false);
  const [form, setForm] = React.useState({ style: b?.style ?? "swahili", people: b?.people ?? t.guests, time: b?.time ?? "08:00", dietary: b?.dietary ?? "", notes: b?.notes ?? "" });
  const diets = ["Halal", "Vegetarian", "Vegan", "Gluten-free", "Lactose-free", "Nut allergy"];
  const save = () => run("bf", () => put<Trip>(`/api/bookings/${t.ref}/breakfast`, form), "Breakfast saved — the kitchen has your order.").then((r) => r && setEditing(false));
  return (
    <Section id="breakfast" title="Breakfast" icon={<Croissant className="size-6" />}
      action={b && !editing ? <button className="font-semibold underline" onClick={() => setEditing(true)}>Change</button> : undefined}>
      {b && !editing ? (
        <div className="rounded-2xl bg-sand-50 p-5">
          <p className="font-semibold">{b.summary}</p>
          <p className="mt-1 text-sm text-ink-2">{b.dietary ? `${b.dietary} · ` : ""}Served on your veranda · change or cancel by 6pm the day before</p>
        </div>
      ) : (
        <div className="space-y-4">
          <p className="text-ink-2">Freshly made each morning and served on your veranda. Change or cancel up to 6pm the day before.</p>
          <div className="grid gap-2 sm:grid-cols-2">
            {Object.entries(STYLES).map(([k, v]) => (
              <button key={k} type="button" onClick={() => setForm({ ...form, style: k })} className={cn("rounded-xl border p-4 text-left text-[15px] transition", form.style === k ? "border-ink ring-1 ring-ink" : "border-line hover:border-ink")}>
                {v}
              </button>
            ))}
          </div>
          <div className="grid items-end gap-4 sm:grid-cols-2">
            <div className="rounded-xl border border-line p-3"><Stepper label="People" value={form.people} min={1} max={t.guests} onChange={(people) => setForm({ ...form, people })} /></div>
            <Field label="Time"><Input type="time" value={form.time} onChange={(e) => setForm({ ...form, time: e.target.value })} min="07:30" max="10:00" /></Field>
          </div>
          <div className="flex flex-wrap gap-2">
            {diets.map((d) => {
              const on = form.dietary.split(", ").includes(d);
              return (
                <button key={d} type="button" onClick={() => {
                  const cur = form.dietary.split(", ").filter(Boolean);
                  setForm({ ...form, dietary: (on ? cur.filter((x) => x !== d) : [...cur, d]).join(", ") });
                }} className={cn("rounded-full border px-3 py-1.5 text-sm", on ? "border-ink bg-ink text-white" : "border-line hover:border-ink")}>{d}</button>
              );
            })}
          </div>
          <Field label="Anything else? (optional)"><Input value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} placeholder="e.g. no chilli, extra fruit for the kids" /></Field>
          <div className="flex gap-2">
            <Button onClick={save} loading={busy === "bf"}>Save breakfast</Button>
            {b && <Button variant="ghost" onClick={() => run("bf-off", () => put<Trip>(`/api/bookings/${t.ref}/breakfast`, { style: "none" }), "Breakfast removed").then(() => setEditing(false))}>Remove</Button>}
            {editing && <Button variant="ghost" onClick={() => setEditing(false)}>Cancel</Button>}
          </div>
        </div>
      )}
    </Section>
  );
}

function Extras({ trip: t, listing }: { trip: Trip; listing: ListingDetail }) {
  const booked = new Set(t.addons.filter((a) => !["declined", "cancelled"].includes(a.status)).map((a) => a.code));
  const available = listing.addons.filter((a) => a.code !== "breakfast" && !booked.has(a.code));
  const mine = t.addons.filter((a) => a.code !== "breakfast");
  if (!available.length && !mine.length) return null;
  return (
    <Section id="extras" title="Extras & experiences" icon={<Star className="size-6" />}>
      {mine.length > 0 && (
        <ul className="mb-6 space-y-3">
          {mine.map((a) => (
            <li key={a.id} className="flex items-center gap-4 rounded-xl border border-line-soft p-4">
              <span className="grid size-10 place-items-center rounded-xl bg-sand-100"><Icon name={a.icon} className="size-5" /></span>
              <div className="min-w-0 flex-1">
                <p className="font-semibold">{a.name}</p>
                <p className="text-sm text-ink-2">{Object.values(a.details ?? {}).filter(Boolean).join(" · ") || kes(a.total)}</p>
              </div>
              <Badge tone={STATUS_TONE[a.status] ?? "neutral"}>{ADDON_STATUS[a.status] ?? a.status}</Badge>
            </li>
          ))}
        </ul>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        {available.map((a) => <ExtraCard key={a.code} trip={t} addon={a} />)}
      </div>
    </Section>
  );
}

function ExtraCard({ trip: t, addon: a }: { trip: Trip; addon: Addon }) {
  const { busy, run } = useTripAction(t.ref);
  const [details, setDetails] = React.useState<Record<string, string>>({});
  const [open, setOpen] = React.useState(false);
  const pickup = a.code === "airport_pickup" || a.code === "sgr_pickup";
  const timed = pickup || a.code === "early_checkin" || a.code === "late_checkout" || a.category === "experience";
  const qty = a.pricing === "per_guest" || a.pricing === "per_guest_night" ? t.guests : undefined;
  const add = () => run("add", () => post<Trip>(`/api/bookings/${t.ref}/extras`, { code: a.code, quantity: qty, details }), a.requires_approval ? "Requested — Amina will confirm by SMS." : `${a.name} added.`).then((r) => r && setOpen(false));
  return (
    <div className="flex flex-col rounded-2xl border border-line-soft p-4">
      <div className="flex items-start gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-sand-100"><Icon name={a.icon} className="size-5" /></span>
        <div className="min-w-0">
          <p className="font-semibold">{a.name}</p>
          <p className="text-sm text-ink-2">{a.short}</p>
        </div>
      </div>
      <div className="mt-4 flex items-center justify-between gap-3 pt-1">
        <p className="text-sm font-semibold">{a.price ? `${kes(a.price)} ${a.pricing_label}` : "Free"}</p>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild><Button size="sm" variant="soft">{a.requires_approval ? "Request" : "Add"}</Button></DialogTrigger>
          <DialogContent title={a.name} size="sm">
            <div className="space-y-4 p-6">
              <p className="text-[15px] text-ink-2">{a.description}</p>
              {pickup && <Field label={a.code === "airport_pickup" ? "Flight number" : "Train"}><Input value={details.flight ?? ""} onChange={(e) => setDetails({ ...details, flight: e.target.value.toUpperCase() })} placeholder={a.code === "airport_pickup" ? "KQ612" : "Madaraka Express"} /></Field>}
              {timed && <Field label={pickup ? "Arrival time" : "Preferred time"}><Input type="time" value={details.time ?? ""} onChange={(e) => setDetails({ ...details, time: e.target.value })} /></Field>}
              <Field label="Note (optional)"><Input value={details.note ?? ""} onChange={(e) => setDetails({ ...details, note: e.target.value })} /></Field>
              <p className="text-sm text-ink-2">{a.price ? `${kes(a.price)} ${a.pricing_label}` : "Free"} — added to your bill{a.requires_approval ? " once Amina confirms" : ""}.</p>
              <Button className="w-full" size="lg" onClick={add} loading={busy === "add"}>{a.requires_approval ? "Send request" : "Add to my stay"}</Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  );
}

function Arrival({ trip: t }: { trip: Trip }) {
  const { busy, run } = useTripAction(t.ref);
  const [form, setForm] = React.useState({ arrival_eta: t.arrival.eta, arrival_mode: t.arrival.mode, vehicle_plate: t.arrival.vehicle_plate, special_requests: t.arrival.special_requests });
  const dirty = form.arrival_eta !== t.arrival.eta || form.arrival_mode !== t.arrival.mode || form.vehicle_plate !== t.arrival.vehicle_plate || form.special_requests !== t.arrival.special_requests;
  return (
    <Section id="arrival" title="Your arrival" icon={<Car className="size-6" />}>
      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="Arrival time"><Input value={form.arrival_eta} onChange={(e) => setForm({ ...form, arrival_eta: e.target.value })} placeholder="e.g. 15:30" /></Field>
        <Field label="Arriving by">
          <Select value={form.arrival_mode} onChange={(e) => setForm({ ...form, arrival_mode: e.target.value })}>
            <option value="">Choose…</option><option value="flight">Flight (Moi Airport)</option><option value="sgr">SGR train</option><option value="car">Car / taxi</option><option value="bus">Bus</option><option value="local">Already in Mombasa</option>
          </Select>
        </Field>
        <Field label="Car plate" hint="Shared with the gate guard"><Input value={form.vehicle_plate} onChange={(e) => setForm({ ...form, vehicle_plate: e.target.value.toUpperCase() })} placeholder="KDA 123A" /></Field>
      </div>
      <Field label="Requests for Amina" className="mt-4"><Textarea value={form.special_requests} onChange={(e) => setForm({ ...form, special_requests: e.target.value })} placeholder="Celebrating? Travelling with a baby? Need a cot?" /></Field>
      <Button className="mt-4" disabled={!dirty} loading={busy === "arr"} onClick={() => run("arr", () => patch<Trip>(`/api/bookings/${t.ref}`, form), "Saved — Amina has your arrival details.")}>Save arrival details</Button>
    </Section>
  );
}

function Register({ trip: t }: { trip: Trip }) {
  const qc = useQueryClient();
  const { data: me } = useMe();
  const { busy, run } = useTripAction(t.ref);
  const [lead, setLead] = React.useState({ id_type: "passport", id_number: "", nationality: me?.nationality ?? "", consent: false });
  const [occ, setOcc] = React.useState({ full_name: "", id_type: "passport", id_number: "", nationality: "", is_minor: false });
  const others = t.occupants.filter((o) => !o.is_lead);
  const submitLead = () => run("id", async () => {
    const r = await post("/api/me/identity", lead);
    await qc.invalidateQueries({ queryKey: ["me"] });
    return r;
  }, "ID saved securely. Thank you!");
  const addOcc = () => run("occ", () => post<Trip>(`/api/bookings/${t.ref}/occupants`, { occupants: [occ] }), "Guest added").then((r) => r && setOcc({ full_name: "", id_type: "passport", id_number: "", nationality: "", is_minor: false }));
  return (
    <Section id="register" title="Guest register" icon={<ShieldCheck className="size-6" />}>
      <p className="text-[15px] text-ink-2">Kenyan law (Tourism Enterprises Regulations, 2025) requires every host to keep a register of guests. Numbers are stored encrypted and erased after the legal retention period — only the last four digits are ever shown.</p>
      <div className="mt-5 rounded-2xl border border-line-soft p-5">
        <div className="flex items-center justify-between gap-3">
          <p className="font-semibold">{me?.name || "Lead guest"} <span className="font-normal text-ink-2">· you</span></p>
          {t.id_registered ? <Badge tone="success"><Check className="size-3" /> {me?.identity?.type_label} {me?.identity?.last4}</Badge> : <Badge tone="warning">ID needed</Badge>}
        </div>
        {!t.id_registered && (
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            <Field label="Document"><Select value={lead.id_type} onChange={(e) => setLead({ ...lead, id_type: e.target.value })}>{ID_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select></Field>
            <Field label="Number"><Input value={lead.id_number} onChange={(e) => setLead({ ...lead, id_number: e.target.value })} /></Field>
            <Field label="Nationality"><Select value={lead.nationality} onChange={(e) => setLead({ ...lead, nationality: e.target.value })}><option value="">Select…</option>{COUNTRIES.map(([c, n]) => <option key={c} value={c}>{n}</option>)}</Select></Field>
            <label className="flex items-start gap-3 text-sm sm:col-span-3">
              <input type="checkbox" className="mt-0.5 size-4 accent-ink" checked={lead.consent} onChange={(e) => setLead({ ...lead, consent: e.target.checked })} />
              <span>I agree to my ID number being stored encrypted for the legally required guest register.</span>
            </label>
            <div className="sm:col-span-3"><Button onClick={submitLead} loading={busy === "id"} disabled={!lead.id_number || !lead.consent}>Save my ID</Button></div>
          </div>
        )}
      </div>
      {others.length > 0 && (
        <ul className="mt-3 space-y-3">
          {others.map((o) => (
            <li key={o.id} className="flex items-center justify-between gap-3 rounded-2xl border border-line-soft p-4">
              <span className="font-semibold">{o.full_name}{o.is_minor && <span className="font-normal text-ink-2"> · under 18</span>}</span>
              <span className="text-sm text-ink-2">{o.id_last4 ? `ID ${o.id_last4}` : o.is_minor ? "No ID needed" : "No ID yet"}</span>
            </li>
          ))}
        </ul>
      )}
      {t.guests > 1 && (
        <Dialog>
          <DialogTrigger asChild><Button variant="soft" className="mt-4"><UserPlus className="size-4" /> Add another guest</Button></DialogTrigger>
          <DialogContent title="Add a guest" size="sm">
            <div className="space-y-4 p-6">
              <Field label="Full name"><Input value={occ.full_name} onChange={(e) => setOcc({ ...occ, full_name: e.target.value })} /></Field>
              <label className="flex items-center gap-3 text-sm"><input type="checkbox" className="size-4 accent-ink" checked={occ.is_minor} onChange={(e) => setOcc({ ...occ, is_minor: e.target.checked })} /> Under 18</label>
              {!occ.is_minor && (
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label="Document"><Select value={occ.id_type} onChange={(e) => setOcc({ ...occ, id_type: e.target.value })}>{ID_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select></Field>
                  <Field label="Number"><Input value={occ.id_number} onChange={(e) => setOcc({ ...occ, id_number: e.target.value })} /></Field>
                </div>
              )}
              <Field label="Nationality"><Select value={occ.nationality} onChange={(e) => setOcc({ ...occ, nationality: e.target.value })}><option value="">Select…</option>{COUNTRIES.map(([c, n]) => <option key={c} value={c}>{n}</option>)}</Select></Field>
              <DialogClose asChild><Button className="w-full" size="lg" onClick={addOcc} disabled={!occ.full_name}>Add guest</Button></DialogClose>
            </div>
          </DialogContent>
        </Dialog>
      )}
    </Section>
  );
}

function HelpDuringStay({ trip: t }: { trip: Trip }) {
  const { busy, run } = useTripAction(t.ref);
  const [issue, setIssue] = React.useState({ category: "water", description: "" });
  const [issueOpen, setIssueOpen] = React.useState(false);
  const [sosDone, setSosDone] = React.useState(false);
  const report = () => run("issue", async () => {
    const r = await post<{ task: number | null; assignee: string | null; priority: string | null; ticket: string | null; known: string | null }>(`/api/bookings/${t.ref}/issues`, issue);
    if (r.known) toast.info(r.known, { duration: 12_000 }); // an outage we've already announced: no new work order
    else toast.success(`${r.assignee ? `${r.assignee} is on it` : "Reported - Amina will text you shortly"}${r.ticket ? ` (reference ${r.ticket})` : ""}. We'll text you updates.`);
    setIssueOpen(false);
    setIssue({ category: "water", description: "" });
    return r;
  });
  return (
    <Section id="help" title="Need help?" icon={<LifeBuoy className="size-6" />}>
      <div className="grid gap-3 sm:grid-cols-3">
        <Dialog open={issueOpen} onOpenChange={setIssueOpen}>
          <DialogTrigger asChild>
            <button className="flex flex-col items-start gap-3 rounded-2xl border border-line-soft p-5 text-left hover:border-ink">
              <Wrench className="size-6" /><span><b className="block">Something&apos;s not working</b><span className="text-sm text-ink-2">Water, power, Wi-Fi, AC…</span></span>
            </button>
          </DialogTrigger>
          <DialogContent title="Report a problem" size="sm">
            <div className="space-y-4 p-6">
              <Field label="What's it about?"><Select value={issue.category} onChange={(e) => setIssue({ ...issue, category: e.target.value })}>{ISSUES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select></Field>
              <Field label="Tell us what's happening"><Textarea value={issue.description} onChange={(e) => setIssue({ ...issue, description: e.target.value })} placeholder="e.g. No hot water in the main bathroom" /></Field>
              <Button className="w-full" size="lg" onClick={report} loading={busy === "issue"} disabled={!issue.description.trim()}>Send to Amina&apos;s team</Button>
            </div>
          </DialogContent>
        </Dialog>
        <Link href="/messages" className="flex flex-col items-start gap-3 rounded-2xl border border-line-soft p-5 hover:border-ink">
          <MessageCircle className="size-6" /><span><b className="block">Message Amina</b><span className="text-sm text-ink-2">Same thread as your SMS</span></span>
        </Link>
        <Dialog onOpenChange={(o) => !o && setSosDone(false)}>
          <DialogTrigger asChild>
            <button className="flex flex-col items-start gap-3 rounded-2xl border border-danger/30 bg-danger-50 p-5 text-left text-danger hover:border-danger">
              <Siren className="size-6" /><span><b className="block">Emergency</b><span className="text-sm">Alert Amina &amp; on-site team</span></span>
            </button>
          </DialogTrigger>
          <DialogContent title="Emergency help" size="sm">
            <div className="space-y-4 p-6">
              {sosDone ? (
                <div className="text-center">
                  <CheckCircle2 className="mx-auto size-12 text-success" />
                  <p className="mt-3 text-lg font-bold">Help is on the way</p>
                  <p className="mt-1 text-ink-2">Amina and the caretaker have been alerted and we&apos;re calling you now. If you are in danger, call <b className="text-ink">999</b> or <b className="text-ink">112</b>.</p>
                </div>
              ) : (
                <>
                  <p className="text-[15px] text-ink-2">If anyone is in immediate danger, call the police or an ambulance first:</p>
                  <div className="grid grid-cols-2 gap-2">
                    <Button asChild variant="danger" size="lg"><a href="tel:999"><Phone className="size-4" /> 999</a></Button>
                    <Button asChild variant="danger-outline" size="lg"><a href="tel:112"><Phone className="size-4" /> 112</a></Button>
                  </div>
                  <Divider />
                  <p className="text-[15px] text-ink-2">Or alert Amina, the caretaker and security at once. We&apos;ll call you straight back and keep escalating until someone answers.</p>
                  <Button variant="dark" size="lg" className="w-full" loading={busy === "sos"} onClick={() => run("sos", () => post(`/api/bookings/${t.ref}/sos`, { text: "SOS from trip page" })).then((r) => r && setSosDone(true))}>
                    <ShieldAlert className="size-4" /> Alert Amina now
                  </Button>
                  <p className="text-center text-xs text-ink-2">No data? Text HELP to our number from any phone.</p>
                </>
              )}
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </Section>
  );
}

function CheckoutButton({ trip: t }: { trip: Trip }) {
  const { busy, run } = useTripAction(t.ref);
  if (!t.can_checkout) return null;
  return (
    <Dialog>
      <DialogTrigger asChild><Button size="sm" variant="dark" className="mt-4"><LogOut className="size-4" /> Check out</Button></DialogTrigger>
      <DialogContent title="Ready to check out?" size="sm">
        <div className="space-y-4 p-6">
          <p className="text-[15px] text-ink-2">Please leave the keys inside, close the windows and switch off the AC. Your door code stops working once you check out.</p>
          <DialogClose asChild>
            <Button className="w-full" size="lg" loading={busy === "out"} onClick={() => run("out", () => post<Trip>(`/api/bookings/${t.ref}/checkout`), "Checked out — asante! Safe travels.")}>Check out now</Button>
          </DialogClose>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function ReviewSection({ trip: t }: { trip: Trip }) {
  const { busy, run } = useTripAction(t.ref);
  const [rating, setRating] = React.useState(0);
  const [comment, setComment] = React.useState("");
  const [cats, setCats] = React.useState<Record<string, number>>({});
  const CATS = [["cleanliness", "Cleanliness"], ["accuracy", "Accuracy"], ["checkin", "Check-in"], ["communication", "Communication"], ["location", "Location"], ["value", "Value"]];
  if (t.review) {
    return (
      <Section title="Your review" icon={<Star className="size-6" />}>
        <div className="flex gap-1">{[1, 2, 3, 4, 5].map((i) => <Star key={i} className={cn("size-5", i <= t.review!.rating ? "fill-ink" : "text-line")} />)}</div>
        {t.review.comment && <p className="mt-3 text-[15px]">&ldquo;{t.review.comment}&rdquo;</p>}
        {t.review.host_response && <div className="mt-4 rounded-xl bg-surface p-4 text-[15px]"><b>Response from Amina</b><p className="mt-1 text-ink-2">{t.review.host_response}</p></div>}
      </Section>
    );
  }
  return (
    <Section title="How was your stay?" icon={<Star className="size-6" />}>
      <div className="flex gap-2" role="radiogroup" aria-label="Overall rating">
        {[1, 2, 3, 4, 5].map((i) => (
          <button key={i} type="button" role="radio" aria-checked={rating === i} aria-label={`${i} star${i > 1 ? "s" : ""}`} onClick={() => setRating(i)}>
            <Star className={cn("size-9 transition", i <= rating ? "fill-brand-500 text-brand-500" : "text-line hover:text-ink-3")} strokeWidth={1.5} />
          </button>
        ))}
      </div>
      {rating > 0 && (
        <div className="mt-6 space-y-5 animate-slide-up">
          <div className="grid gap-3 sm:grid-cols-2">
            {CATS.map(([k, l]) => (
              <div key={k} className="flex items-center justify-between gap-3">
                <span className="text-[15px]">{l}</span>
                <span className="flex gap-1">
                  {[1, 2, 3, 4, 5].map((i) => (
                    <button key={i} type="button" aria-label={`${l} ${i}`} onClick={() => setCats({ ...cats, [k]: i })}>
                      <Star className={cn("size-4", i <= (cats[k] ?? 0) ? "fill-ink" : "text-line")} />
                    </button>
                  ))}
                </span>
              </div>
            ))}
          </div>
          <Field label="Tell future guests about your stay"><Textarea value={comment} onChange={(e) => setComment(e.target.value)} rows={4} placeholder="What did you love? Anything Amina could do better?" /></Field>
          <Button loading={busy === "review"} onClick={() => run("review", () => post<Trip>(`/api/bookings/${t.ref}/review`, { rating, comment, categories: cats }), "Thank you for your review!")}>Submit review</Button>
        </div>
      )}
    </Section>
  );
}

function Timeline({ trip: t }: { trip: Trip }) {
  if (!t.timeline.length) return null;
  return (
    <Section title="Activity" icon={<Clock className="size-6" />}>
      <ol className="relative space-y-5 border-l border-line pl-6">
        {[...t.timeline].reverse().map((e, i) => (
          <li key={i} className="relative">
            <span className="absolute top-1.5 -left-[29px] size-2.5 rounded-full bg-ink-3 ring-4 ring-white" />
            <p className="text-[15px]">{e.text}</p>
            <p className="text-xs text-ink-2">{fmtDateTime(e.created_at)}{e.channel && e.channel !== "system" ? ` · ${CHANNEL_LABEL[e.channel] ?? e.channel}` : ""}</p>
          </li>
        ))}
      </ol>
    </Section>
  );
}

function ReceiptCard({ trip: t }: { trip: Trip }) {
  const p = t.price;
  return (
    <div id="receipt" className="scroll-mt-24 rounded-2xl border border-line-soft p-6 shadow-soft">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-lg font-bold"><Receipt className="size-5" /> Payment</h2>
        <Badge tone={p.balance_due ? "warning" : "success"}>{p.payment_status_label}</Badge>
      </div>
      <div className="mt-5 space-y-2.5 text-[15px]">
        {p.lines.map((l) => (
          <div key={l.label} className={cn("flex justify-between gap-3", l.amount < 0 && "text-success")}><span className="text-ink-2">{l.label}</span><span className="shrink-0 whitespace-nowrap">{l.amount < 0 ? `−${kes(-l.amount)}` : kes(l.amount)}</span></div>
        ))}
        <Divider className="my-3" />
        <div className="flex justify-between font-bold"><span>Total</span><span>{kes(p.total)}</span></div>
        <div className="flex justify-between"><span className="text-ink-2">Paid</span><span>{kes(p.amount_paid)}</span></div>
        {p.amount_refunded > 0 && <div className="flex justify-between text-success"><span>Refunded</span><span>{kes(p.amount_refunded)}</span></div>}
        {p.balance_due > 0 && <div className={cn("flex justify-between font-semibold", p.balance_overdue ? "text-danger" : "text-warning")}><span>{p.balance_overdue ? "Overdue since" : "Balance due"} {due(p.balance_due_date)}</span><span>{kes(p.balance_due)}</span></div>}
        {!!p.pending?.length && (
          <div className="mt-3 rounded-xl bg-surface p-3 text-sm">
            <p className="font-semibold">Awaiting Amina&apos;s OK — not charged yet</p>
            {p.pending.map((l) => (
              <div key={l.label} className="mt-1 flex justify-between gap-3 text-ink-2"><span>{l.label}</span><span>{kes(l.amount)}</span></div>
            ))}
          </div>
        )}
      </div>
      {t.payments.length > 0 && (
        <ul className="mt-5 space-y-2 border-t border-line-soft pt-4 text-sm">
          {t.payments.map((x) => (
            <li key={x.id} className="flex items-center justify-between gap-3">
              <span className="flex min-w-0 items-center gap-2">{x.method === "card" ? <CreditCard className="size-3.5 shrink-0 text-ink-2" /> : <Smartphone className="size-3.5 shrink-0 text-ink-2" />} {x.method_label}{x.reference ? <span className="truncate font-mono text-xs text-ink-2">{x.reference}</span> : x.status === "failed" ? <span className="truncate text-xs text-danger">{x.failure_message ? "failed" : "not completed"}</span> : null}</span>
              <span className={cn("shrink-0", x.status === "success" ? "" : x.status === "failed" ? "text-danger line-through" : "text-warning")}>{kes(x.amount)}</span>
            </li>
          ))}
        </ul>
      )}
      <div className="mt-5 flex flex-wrap gap-2 print:hidden">
        <Button variant="soft" size="sm" onClick={() => window.print()}><Printer className="size-4" /> Print receipt</Button>
        {["confirmed", "checked_in", "completed"].includes(t.status) && <Button asChild variant="soft" size="sm"><Link href={`/trips/${t.ref}/invoice`}><Receipt className="size-4" /> Invoice</Link></Button>}
        {t.can_change && <ChangeTrip trip={t} />}
        {t.can_cancel && <CancelButton trip={t} />}
      </div>
      <p className="mt-4 text-xs text-ink-2">{t.cancellation.policy_text || t.cancellation.text}{t.tra_licence ? ` · TRA licence ${t.tra_licence}` : ""}</p>
    </div>
  );
}

function CancelButton({ trip: t }: { trip: Trip }) {
  const { busy, run } = useTripAction(t.ref);
  const [reason, setReason] = React.useState("");
  const [open, setOpen] = React.useState(false);
  const { data: quote } = useQuery({ queryKey: ["refund", t.ref], queryFn: () => get<{ refund: number; percent: number; text: string; policy_text?: string }>(`/api/bookings/${t.ref}/cancel`), enabled: open });
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button variant="ghost" size="sm" className="text-ink-2">Cancel booking</Button></DialogTrigger>
      <DialogContent title="Cancel your booking?" size="sm">
        <div className="space-y-4 p-6">
          {!quote ? <Skeleton className="h-16" /> : (
            <div className="rounded-xl bg-surface p-4">
              <p className="font-semibold">{quote.text}</p>
              {quote.policy_text && <p className="mt-1 text-sm text-ink-2">{quote.policy_text}</p>}
            </div>
          )}
          <Field label="Reason (optional)">
            <Select value={reason} onChange={(e) => setReason(e.target.value)}>
              <option value="">Prefer not to say</option><option>Change of plans</option><option>Found somewhere else</option><option>Travel restrictions</option><option>Illness</option><option>Booked by mistake</option>
            </Select>
          </Field>
          <Button variant="danger" size="lg" className="w-full" loading={busy === "cancel"} onClick={() => run("cancel", () => api(`/api/bookings/${t.ref}/cancel`, { method: "POST", body: { reason } }), "Booking cancelled.").then((r) => r && setOpen(false))}>
            Cancel booking{quote?.refund ? ` · refund ${kes(quote.refund)}` : ""}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function SupportCard({ trip: t }: { trip: Trip }) {
  return (
    <div className="rounded-2xl border border-line-soft p-6 print:hidden">
      <h2 className="text-lg font-bold">Manage this trip your way</h2>
      <ul className="mt-4 space-y-3 text-[15px]">
        <li className="flex gap-3"><MessageCircle className="mt-0.5 size-5 shrink-0 text-ink-2" /><span>SMS <b>{t.support.sms || "Amina's number"}</b> — try &ldquo;BREAKFAST&rdquo;, &ldquo;WIFI&rdquo; or &ldquo;ETA 4pm&rdquo;</span></li>
        {t.support.ussd && <li className="flex gap-3"><Smartphone className="mt-0.5 size-5 shrink-0 text-ink-2" /><span>Dial <b>{t.support.ussd}</b> → My booking (no data needed)</span></li>}
        {t.support.voice && <li className="flex gap-3"><Phone className="mt-0.5 size-5 shrink-0 text-ink-2" /><span>Call <b>{t.support.voice}</b> — English or Kiswahili</span></li>}
        <li className="flex gap-3"><Siren className="mt-0.5 size-5 shrink-0 text-danger" /><span>Emergency? Text <b>HELP</b> or call <b>999 / 112</b></span></li>
      </ul>
      <p className="mt-4 text-xs text-ink-2">Booked {ago(t.created_at)} via {t.channel_label}.</p>
    </div>
  );
}

function HubSkeleton() {
  return (
    <>
      <SiteHeader />
      <main className="container-narrow max-w-[1160px] pt-10">
        <Skeleton className="aspect-[21/8] rounded-3xl" />
        <div className="mt-10 grid gap-16 lg:grid-cols-[1fr_380px]">
          <div className="space-y-6"><Skeleton className="h-28 rounded-2xl" /><Skeleton className="h-60 rounded-2xl" /></div>
          <Skeleton className="h-80 rounded-2xl" />
        </div>
      </main>
    </>
  );
}
