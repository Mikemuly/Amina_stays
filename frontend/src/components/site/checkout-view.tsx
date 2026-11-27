"use client";

import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, ChevronLeft, CreditCard, Lock, Smartphone } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { useConfig, useMe, usePayOptions } from "@/components/providers";
import { GuestPicker, guestsLabel, type Guests } from "@/components/site/guest-picker";
import { SiteHeader } from "@/components/site/header";
import { PhoneLogin } from "@/components/site/phone-login";
import { Photo, StarIcon, typeLabel } from "@/components/site/listing-card";
import { CardTestHint, FailureNotice, lastFailure, PaybillBox } from "@/components/site/payment-help";
import { RangeCalendar, type Range } from "@/components/site/range-calendar";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { Field, Input, Select, Textarea } from "@/components/ui/input";
import { Icon3D } from "@/components/ui/icon3d";
import { Skeleton, Spinner } from "@/components/ui/misc";
import { Switch } from "@/components/ui/overlays";
import { get, post } from "@/lib/api";
import { approx, fmtDate, fmtRange, fmtTime, freeCancelUntil, kes } from "@/lib/format";
import type { Addon, CalendarData, ListingDetail, PaymentResult, Quote, Trip } from "@/lib/types";
import { COUNTRIES, cn } from "@/lib/utils";

type Extra = { on: boolean; details: Record<string, string>; quantity?: number };
const STYLE_LABEL: Record<string, string> = { swahili: "Swahili — mahamri, chai, mbaazi, fruit", continental: "Continental", english: "Full English", vegetarian: "Vegetarian / vegan" };

export function CheckoutView({ slug }: { slug: string }) {
  const params = useSearchParams();
  const router = useRouter();
  const { data: me } = useMe();
  const { data: config } = useConfig();
  const pay = usePayOptions();
  const { data: l } = useQuery({ queryKey: ["listing", slug], queryFn: () => get<ListingDetail>(`/api/listings/${slug}`) });
  const { data: cal } = useQuery({ queryKey: ["calendar", slug], queryFn: () => get<CalendarData>(`/api/listings/${slug}/calendar`) });
  const [range, setRange] = React.useState<Range>({ from: params.get("check_in") || undefined, to: params.get("check_out") || undefined });
  const [guests, setGuests] = React.useState<Guests>({ adults: Number(params.get("adults") || 1), children: Number(params.get("children") || 0), infants: Number(params.get("infants") || 0) });
  const [plan, setPlan] = React.useState<"full" | "deposit">("full");
  const [extras, setExtras] = React.useState<Record<string, Extra>>({ breakfast: { on: false, details: { style: "swahili", time: "08:00", dietary: "" } } });
  const [form, setForm] = React.useState({ name: "", email: "", lang: "en", nationality: "", id_type: "", id_number: "", consent: false, eta: "", mode: "", plate: "", requests: "", marketing: false });
  const [method, setMethod] = React.useState<"mpesa" | "card">("mpesa");
  const [submitting, setSubmitting] = React.useState(false);
  const [result, setResult] = React.useState<{ booking: Trip; payment: PaymentResult } | null>(null);
  const [step, setStep] = React.useState<StepKey>("plan");
  // keep the login step (and the numbering) once it has been shown, even after logging in
  const [showLogin, setShowLogin] = React.useState(false);
  if (me && !me.authenticated && !showLogin) setShowLogin(true);

  // Prefill from the account once it loads (or when someone logs in on this page).
  const [prefilledFor, setPrefilledFor] = React.useState<number | null>(null);
  if (me?.authenticated && me.id !== undefined && me.id !== prefilledFor) {
    setPrefilledFor(me.id);
    setForm((f) => ({ ...f, name: f.name || me.name || "", email: f.email || me.email || "", lang: me.lang || f.lang, nationality: f.nationality || me.nationality || "" }));
    setMethod(me.phone?.startsWith("+254") ? "mpesa" : "card");
  }

  const addonList = Object.entries(extras).filter(([, e]) => e.on).map(([code, e]) => ({ code, quantity: e.quantity, details: e.details }));
  const ready = !!(range.from && range.to);
  const { data: q, isFetching } = useQuery({
    queryKey: ["quote", slug, range.from, range.to, guests.adults, guests.children, plan, JSON.stringify(addonList.map((a) => [a.code, a.quantity]))],
    queryFn: () => post<Quote>(`/api/listings/${slug}/quote`, { check_in: range.from, check_out: range.to, adults: guests.adults, children: guests.children, addons: addonList, payment_plan: plan }),
    enabled: ready,
    placeholderData: (prev) => prev,
  });

  if (result) return <PaymentFlow result={result} listing={l} />;
  if (!l) return <CheckoutSkeleton />;

  const kenyan = !!me?.phone?.startsWith("+254");
  const payMethod = pay.mpesa ? method : "card";
  const freeUntil = freeCancelUntil(l.cancellation.policy, range.from);
  const dueNow = q ? (plan === "deposit" && q.deposit_available ? q.deposit : q.total) : 0;

  async function submit() {
    if (!ready || !q) return toast.error("Choose your dates first.");
    if (q.available === false) return toast.error(q.problems?.[0] ?? "Those dates aren't available.");
    if (form.id_number && !form.consent) return toast.error("Please tick the consent box to store your ID for the guest register.");
    setSubmitting(true);
    try {
      const r = await post<{ booking: Trip; payment: PaymentResult }>("/api/bookings", {
        listing: slug, check_in: range.from, check_out: range.to, adults: guests.adults, children: guests.children, infants: guests.infants,
        addons: addonList, payment_plan: plan, payment_method: payMethod, arrival_eta: form.eta, arrival_mode: form.mode, vehicle_plate: form.plate,
        special_requests: form.requests, name: form.name, email: form.email, lang: form.lang, marketing_opt_in: form.marketing,
        identity: form.id_number ? { id_type: form.id_type, id_number: form.id_number, nationality: form.nationality, consent: form.consent } : undefined,
      });
      setResult(r);
      window.scrollTo({ top: 0 });
      if (r.payment.method === "card" && r.payment.checkout_url && !r.payment.error) window.location.href = r.payment.checkout_url;
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  const order: StepKey[] = showLogin ? ["login", "plan", "extras", "details", "pay"] : ["plan", "extras", "details", "pay"];
  const active: StepKey = me && !me.authenticated ? "login" : step;
  const state = (k: StepKey) => (k === active ? "active" : order.indexOf(k) < order.indexOf(active) ? "done" : "todo");
  const num = (k: StepKey) => order.indexOf(k) + 1;
  const chosen = l.addons.filter((a) => extras[a.code]?.on);
  const toDetails = () => setStep("details");
  const toPay = () => {
    if (form.id_number && !form.consent) return toast.error("Please tick the consent box to store your ID for the guest register.");
    if (!form.name.trim()) return toast.error("Add your full name — it goes on the guest register and your receipt.");
    setStep("pay");
  };

  return (
    <>
      <SiteHeader mode="minimal" width="narrow" />
      <main className="container-narrow max-w-[1136px] pt-6 pb-24 md:pt-12">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="icon" className="-ml-2" onClick={() => router.back()} aria-label="Back"><ChevronLeft className="size-5" /></Button>
          <h1 className="text-[26px] font-semibold tracking-tight md:text-[32px]">{q?.problems?.length ? "Check your trip" : "Confirm and pay"}</h1>
        </div>
        <div className="mt-6 grid gap-8 md:mt-10 lg:grid-cols-[minmax(0,1fr)_372px] lg:gap-20">
          <div className="min-w-0 space-y-4">
            {showLogin && (
              <StepCard n={num("login")} title="Log in or sign up" state={state("login")} summary={me?.phone ? `Logged in as ${me.phone}` : undefined}>
                <PhoneLogin title="" subtitle="Your booking, receipts and door code go to this number — on the web, USSD, SMS or voice." cta="Continue" />
              </StepCard>
            )}

            <StepCard
              n={num("plan")}
              title="Choose when to pay"
              state={state("plan")}
              summary={plan === "deposit" && q?.deposit_available ? `${kes(q.deposit)} today, ${kes(q.total - q.deposit)} on ${fmtDate(q.balance_due_date)}` : `Pay ${q ? kes(q.total) : "in full"} now`}
              onChange={() => setStep("plan")}
            >
              <div className="overflow-hidden rounded-xl border border-line">
                <PlanOption checked={plan === "full"} onSelect={() => setPlan("full")} title={`Pay ${q ? kes(q.total) : "in full"} now`} text="One payment and you're done." />
                <PlanOption
                  checked={plan === "deposit"}
                  disabled={!!q && !q.deposit_available}
                  onSelect={() => setPlan("deposit")}
                  title={`Pay part now, part later${q ? ` — ${kes(q.deposit)} today` : ""}`}
                  text={q?.deposit_available ? `${l.deposit_percent}% today and the rest (${kes(q.total - q.deposit)}) on ${fmtDate(q.balance_due_date)} — we'll send ${pay.mpesa ? "an M-Pesa prompt or a pay link" : "you a pay link by SMS"}. No extra fees.` : "Available for stays booked more than a day ahead."}
                />
              </div>
              <NextButton onClick={() => setStep("extras")} />
            </StepCard>

            <StepCard
              n={num("extras")}
              title="Make it yours"
              state={state("extras")}
              summary={chosen.length ? chosen.map((a) => a.name).join(" · ") : "No extras — you can add them later from your trip"}
              onChange={() => setStep("extras")}
            >
              <Extras listing={l} extras={extras} setExtras={setExtras} guests={guests.adults + guests.children} />
              <NextButton onClick={toDetails} label={chosen.length ? "Next" : "Skip for now"} />
            </StepCard>

            <StepCard
              n={num("details")}
              title="Guest details"
              state={state("details")}
              summary={[form.name || "Name to add", me?.identity?.last4 ? `${me.identity.type_label} on file` : form.id_number ? "ID added" : "ID can be added later", form.eta && `arriving ${form.eta}`].filter(Boolean).join(" · ")}
              onChange={() => setStep("details")}
            >
              <div className="space-y-8">
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="Full name"><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} autoComplete="name" placeholder="As on your ID or passport" /></Field>
                  <Field label="Email (optional)" hint="For receipts. Everything else comes by SMS."><Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} autoComplete="email" /></Field>
                  <Field label="Messages in" hint="Booking updates, directions and your door code.">
                    <Select value={form.lang} onChange={(e) => setForm({ ...form, lang: e.target.value })}>
                      <option value="en">English</option><option value="sw">Kiswahili</option><option value="it">Italiano</option><option value="de">Deutsch</option><option value="fr">Français</option>
                    </Select>
                  </Field>
                  <Field label="Nationality">
                    <Select value={form.nationality} onChange={(e) => setForm({ ...form, nationality: e.target.value })}>
                      <option value="">Select…</option>
                      {COUNTRIES.map(([c, n]) => <option key={c} value={c}>{n}</option>)}
                    </Select>
                  </Field>
                </div>

                <div className="rounded-xl bg-surface p-5">
                  <h3 className="flex items-center gap-2 font-semibold"><Icon3D name="clipboard" size={24} /> Guest register</h3>
                  {me?.identity?.last4 ? (
                    <p className="mt-2 flex flex-wrap items-center gap-2 text-sm text-ink-2">
                      <CheckCircle2 className="size-4 text-success" />
                      <span><b className="font-medium text-ink">{me.identity.type_label} {me.identity.last4}</b> is on file (stored encrypted) — nothing to do. Add other adult guests from your trip page.</span>
                    </p>
                  ) : (
                    <>
                      <p className="mt-2 text-sm text-ink-2">
                        Kenyan law asks every host to keep a guest register. Add it now and your door code is released automatically on arrival morning — or later from your trip page or by SMS (&ldquo;ID 12345678&rdquo;).
                      </p>
                      <div className="mt-4 grid gap-4 sm:grid-cols-2">
                        <Field label="Document">
                          <Select value={form.id_type} onChange={(e) => setForm({ ...form, id_type: e.target.value })}>
                            <option value="">Choose…</option><option value="passport">Passport</option><option value="national_id">Kenyan National ID</option><option value="alien_id">Alien / Foreigner ID</option><option value="driving_licence">Driving licence</option>
                          </Select>
                        </Field>
                        <Field label="Number"><Input value={form.id_number} onChange={(e) => setForm({ ...form, id_number: e.target.value })} placeholder="e.g. 28123456 or P1234567" /></Field>
                      </div>
                      <label className="mt-4 flex items-start gap-3 text-sm">
                        <input type="checkbox" className="mt-0.5 size-4 accent-ink" checked={form.consent} onChange={(e) => setForm({ ...form, consent: e.target.checked })} />
                        <span>I agree that Amina Stays stores my ID number <b className="font-medium">encrypted</b>, only for the guest register required by law, and erases it after the 5-year retention period (Data Protection Act 2019).</span>
                      </label>
                    </>
                  )}
                </div>

                <div>
                  <h3 className="font-semibold">Your arrival</h3>
                  <div className="mt-3 grid gap-4 sm:grid-cols-3">
                    <Field label="Arrival time"><Input type="time" value={form.eta} onChange={(e) => setForm({ ...form, eta: e.target.value })} /></Field>
                    <Field label="Arriving by">
                      <Select value={form.mode} onChange={(e) => setForm({ ...form, mode: e.target.value })}>
                        <option value="">Choose…</option><option value="flight">Flight (Moi Airport)</option><option value="sgr">SGR train</option><option value="car">Car / taxi</option><option value="bus">Bus</option><option value="local">Already in Mombasa</option>
                      </Select>
                    </Field>
                    <Field label="Car plate (optional)" hint="For the gate log"><Input value={form.plate} onChange={(e) => setForm({ ...form, plate: e.target.value.toUpperCase() })} placeholder="KDA 123A" /></Field>
                  </div>
                  <div className="mt-4">
                    <Field label="Message for Amina (optional)"><Textarea value={form.requests} onChange={(e) => setForm({ ...form, requests: e.target.value })} placeholder="Celebrating something? Travelling with a baby? Let us know." /></Field>
                  </div>
                </div>
              </div>
              <NextButton onClick={toPay} />
            </StepCard>

            <StepCard n={num("pay")} title="Pay and confirm" state={state("pay")}>
              <div role="radiogroup" aria-label="Payment method" className={cn("grid gap-3", pay.mpesa && "sm:grid-cols-2")}>
                {pay.mpesa && (
                  <MethodOption
                    checked={payMethod === "mpesa"} disabled={!!me?.authenticated && !kenyan} onSelect={() => setMethod("mpesa")}
                    icon={<Icon3D name="mobile-phone" size={30} />} title="M-Pesa" text={kenyan ? `A prompt will appear on ${me?.phone}` : "Needs a Kenyan (+254) number"}
                  />
                )}
                <MethodOption checked={payMethod === "card"} onSelect={() => setMethod("card")} icon={<Icon3D name="credit-card" size={30} />} title="Card" text="Visa, Mastercard and more — on a secure hosted checkout" />
              </div>
              {config?.payments.simulated && <p className="mt-3 text-[13px] text-ink-2">Demo mode: payments are simulated — no money moves.</p>}
              {pay.cardTest && payMethod === "card" && <CardTestHint className="mt-3" />}
              <div className="mt-8 space-y-5 border-t border-line pt-6 text-sm">
                <div>
                  <h3 className="text-base font-semibold">Cancellation policy</h3>
                  <p className="mt-1 text-ink-2">{l.cancellation.text}</p>
                </div>
                <div>
                  <h3 className="text-base font-semibold">Ground rules</h3>
                  <p className="mt-1 text-ink-2">Follow the house rules, no parties, register every adult guest, and treat Amina&apos;s home like your own.</p>
                </div>
                <p className="flex gap-3 rounded-xl bg-surface p-4 text-ink-2">
                  <Lock className="mt-0.5 size-4 shrink-0 text-ink" /> We only ever take payment through {pay.mpesa ? "the official M-Pesa prompt or our secure card page" : "our secure card checkout"}. We will never ask you to send money to a personal number.
                </p>
                <label className="flex items-start gap-3">
                  <input type="checkbox" className="mt-0.5 size-4 accent-ink" checked={form.marketing} onChange={(e) => setForm({ ...form, marketing: e.target.checked })} />
                  <span>Send me occasional offers by SMS (reply STOP any time).</span>
                </label>
              </div>
              <Button variant="brand" size="lg" className="mt-8 h-14 w-full text-base sm:w-auto sm:min-w-72" onClick={submit} loading={submitting} disabled={!me?.authenticated || !ready || !q || q.available === false}>
                {payMethod === "mpesa" ? `Pay ${kes(dueNow)} with M-Pesa` : `Pay ${kes(dueNow)} by card`}
              </Button>
            </StepCard>
          </div>

          <aside className="order-first lg:order-none">
            <div className="rounded-3xl border border-line p-6 lg:sticky lg:top-12">
              <div className="flex gap-4">
                <div className="size-[104px] shrink-0 overflow-hidden rounded-xl"><Photo src={l.photos[0]?.src} alt={l.name} className="size-full" sizes="120px" /></div>
                <div className="min-w-0 self-center">
                  <p className="text-base font-medium">{l.name}</p>
                  <p className="text-sm text-ink-2">{typeLabel(l.property_type)} in {l.area.name}</p>
                  {l.rating && <p className="mt-1 flex items-center gap-1 text-xs"><StarIcon className="size-2.5" /> {l.rating.toFixed(2)} ({l.reviews_count}){l.guest_favourite && <> · <b className="font-medium">Guest favourite</b></>}</p>}
                </div>
              </div>
              <div className="mt-6 border-t border-line pt-5">
                {freeUntil ? (
                  <p className="text-sm"><b className="font-semibold">Free cancellation</b><br /><span className="text-ink-2">Cancel before {fmtDate(freeUntil, "d MMMM")} for a full refund. {l.cancellation.label} policy.</span></p>
                ) : (
                  <p className="text-sm"><b className="font-semibold">{l.cancellation.label} cancellation</b><br /><span className="text-ink-2">{l.cancellation.text}</span></p>
                )}
              </div>
              <SummaryRow label="Dates" value={ready ? fmtRange(range.from, range.to) : "Choose dates"}>
                <Dialog>
                  <DialogTrigger asChild><Button variant="soft" size="sm" className="text-xs">Change</Button></DialogTrigger>
                  <DialogContent title="Change dates" size="lg">
                    <div className="p-6">
                      <RangeCalendar value={range} onChange={setRange} unavailable={new Set(cal?.unavailable ?? [])} prices={cal?.prices} minNights={l.min_nights} />
                    </div>
                  </DialogContent>
                </Dialog>
              </SummaryRow>
              <SummaryRow label="Guests" value={guestsLabel(guests)}>
                <Dialog>
                  <DialogTrigger asChild><Button variant="soft" size="sm" className="text-xs">Change</Button></DialogTrigger>
                  <DialogContent title="Guests" size="sm">
                    <div className="px-6 pb-4"><GuestPicker value={guests} onChange={setGuests} max={l.max_guests} /></div>
                  </DialogContent>
                </Dialog>
              </SummaryRow>
              {q?.problems?.length ? <p className="mt-4 rounded-xl bg-danger-50 p-3 text-sm text-danger">{q.problems.join(" ")}</p> : null}
              <div className="mt-5 border-t border-line pt-5">
                <p className="text-base font-medium">Price details</p>
                {!q ? (
                  <div className="mt-4 space-y-2"><Skeleton className="h-4" /><Skeleton className="h-4 w-2/3" /></div>
                ) : (
                  <div className={cn("mt-4 space-y-3 text-sm", isFetching && "opacity-60")}>
                    {q.lines.map((line) => (
                      <div key={line.label} className={cn("flex justify-between gap-4", line.amount < 0 && "text-success")}>
                        <span>{line.label}</span><span className="shrink-0 whitespace-nowrap">{line.amount < 0 ? `−${kes(-line.amount)}` : kes(line.amount)}</span>
                      </div>
                    ))}
                    <div className="flex justify-between border-t border-line pt-4 text-base font-semibold"><span>Total</span><span>{kes(q.total)}</span></div>
                    {!!q.pending?.length && (
                      <div className="rounded-xl bg-surface p-3">
                        <p className="font-medium">On request — charged only if Amina confirms</p>
                        {q.pending.map((line) => (
                          <div key={line.label} className="mt-1 flex justify-between gap-4 text-ink-2"><span>{line.label}</span><span className="shrink-0 whitespace-nowrap">{kes(line.amount)}</span></div>
                        ))}
                      </div>
                    )}
                    {plan === "deposit" && q.deposit_available && (
                      <div className="rounded-xl bg-surface p-3">
                        <div className="flex justify-between font-medium"><span>Due today</span><span>{kes(q.deposit)}</span></div>
                        <div className="mt-1 flex justify-between text-ink-2"><span>Due {fmtDate(q.balance_due_date)}</span><span>{kes(q.total - q.deposit)}</span></div>
                      </div>
                    )}
                    {config && <p className="text-right text-xs text-ink-2">{approx(q.total, config.currencies, "USD")} · {approx(q.total, config.currencies, "EUR")} · {approx(q.total, config.currencies, "GBP")}</p>}
                  </div>
                )}
              </div>
            </div>
          </aside>
        </div>
      </main>
    </>
  );
}

type StepKey = "login" | "plan" | "extras" | "details" | "pay";

/** One numbered checkout step: open while active, a one-line summary with "Change" once done. */
function StepCard({ n, title, state, summary, onChange, children }: {
  n: number; title: string; state: "active" | "done" | "todo"; summary?: string; onChange?: () => void; children: React.ReactNode;
}) {
  return (
    <section className={cn("p-6", state === "active" ? "rounded-3xl shadow-badge" : "rounded-[20px] border border-line")}>
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 className={cn("text-lg leading-6 font-semibold", state === "todo" && "text-ink-2")}>{n}. {title}</h2>
          {state === "done" && summary && <p className="mt-1 truncate text-sm text-ink-2">{summary}</p>}
        </div>
        {state === "done" && onChange && <Button variant="soft" size="sm" className="text-xs" onClick={onChange}>Change</Button>}
      </div>
      {state === "active" && <div className="mt-6 animate-fade-in">{children}</div>}
    </section>
  );
}

function NextButton({ onClick, label = "Next" }: { onClick: () => void; label?: string }) {
  return (
    <div className="mt-6 flex justify-end">
      <Button size="lg" onClick={onClick} className="px-8">{label}</Button>
    </div>
  );
}

function SummaryRow({ label, value, children }: { label: string; value: string; children: React.ReactNode }) {
  return (
    <div className="mt-5 flex items-center justify-between gap-4 border-t border-line pt-5">
      <div>
        <p className="text-sm font-medium">{label}</p>
        <p className="text-sm text-ink-2">{value}</p>
      </div>
      {children}
    </div>
  );
}

function PlanOption({ checked, onSelect, title, text, disabled }: { checked: boolean; onSelect: () => void; title: string; text: string; disabled?: boolean }) {
  return (
    <button type="button" disabled={disabled} onClick={onSelect} className={cn("flex w-full items-start justify-between gap-4 border-b border-line p-5 text-left last:border-0 disabled:opacity-40", checked && "bg-surface")}>
      <span>
        <span className="block font-semibold">{title}</span>
        <span className="mt-1 block text-sm text-ink-2">{text}</span>
      </span>
      <span className={cn("mt-1 grid size-6 shrink-0 place-items-center rounded-full border-2", checked ? "border-ink" : "border-ink-3")}>{checked && <span className="size-3 rounded-full bg-ink" />}</span>
    </button>
  );
}

function MethodOption({ checked, onSelect, icon, title, text, disabled }: { checked: boolean; onSelect: () => void; icon: React.ReactNode; title: string; text: string; disabled?: boolean }) {
  return (
    <button type="button" role="radio" aria-checked={checked} disabled={disabled} onClick={onSelect} className={cn("flex items-start gap-3 rounded-2xl border p-4 text-left transition disabled:opacity-40", checked ? "border-ink ring-1 ring-ink" : "border-line hover:border-ink")}>
      <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-surface">{icon}</span>
      <span><span className="block font-semibold">{title}</span><span className="block text-sm text-ink-2">{text}</span></span>
    </button>
  );
}

function Extras({ listing: l, extras, setExtras, guests }: { listing: ListingDetail; extras: Record<string, Extra>; setExtras: (e: Record<string, Extra>) => void; guests: number }) {
  const set = (code: string, patch: Partial<Extra>) => setExtras({ ...extras, [code]: { ...(extras[code] ?? { on: false, details: {} }), ...patch } });
  const list = l.addons.filter((a) => !["mid_stay_clean"].includes(a.code));
  return (
    <section>
      <p className="text-sm text-ink-2">Breakfast, pickups and experiences — added to one bill. Extras marked &ldquo;on request&rdquo; are confirmed by Amina by SMS.</p>
      <div className="mt-5 space-y-3">
        {list.map((a: Addon) => {
          const e = extras[a.code] ?? { on: false, details: {} };
          return (
            <div key={a.code} className={cn("rounded-xl border p-4 transition", e.on ? "border-ink shadow-[inset_0_0_0_1px_var(--color-ink)]" : "border-line")}>
              <div className="flex items-center gap-4">
                <div className="size-14 shrink-0 overflow-hidden rounded-lg bg-surface"><Photo src={a.photo_url} alt="" className="size-full" sizes="56px" /></div>
                <div className="min-w-0 flex-1">
                  <p className="font-medium">{a.name}</p>
                  <p className="truncate text-sm text-ink-2">{a.short}</p>
                  <p className="mt-0.5 text-sm font-medium">{a.price ? `${kes(a.price)} ${a.pricing_label}` : "Free"}{a.requires_approval && <span className="font-normal text-ink-2"> · on request</span>}</p>
                </div>
                <Switch checked={e.on} onCheckedChange={(v) => set(a.code, { on: v, quantity: a.pricing === "per_guest_night" || a.pricing === "per_guest" ? guests : undefined })} aria-label={`Add ${a.name}`} />
              </div>
              {e.on && a.code === "breakfast" && (
                <div className="mt-4 grid gap-3 border-t border-line-soft pt-4 sm:grid-cols-3">
                  <Field label="Style" className="sm:col-span-2">
                    <Select value={e.details.style} onChange={(ev) => set(a.code, { details: { ...e.details, style: ev.target.value } })}>
                      {Object.entries(STYLE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                    </Select>
                  </Field>
                  <Field label="Time"><Input type="time" value={e.details.time ?? "08:00"} onChange={(ev) => set(a.code, { details: { ...e.details, time: ev.target.value } })} /></Field>
                  <div className="sm:col-span-3">
                    <p className="mb-2 text-[13px] font-semibold">Dietary needs</p>
                    <div className="flex flex-wrap gap-2">
                      {(a.options.dietary ?? []).map((d) => {
                        const on = (e.details.dietary ?? "").split(", ").includes(d);
                        return (
                          <button key={d} type="button" onClick={() => {
                            const cur = (e.details.dietary ?? "").split(", ").filter(Boolean);
                            set(a.code, { details: { ...e.details, dietary: (on ? cur.filter((x) => x !== d) : [...cur, d]).join(", ") } });
                          }} className={cn("rounded-full border px-3 py-1.5 text-sm", on ? "border-ink bg-ink text-white" : "border-line hover:border-ink")}>
                            {d}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </div>
              )}
              {e.on && (a.code === "airport_pickup" || a.code === "sgr_pickup") && (
                <div className="mt-4 grid gap-3 border-t border-line-soft pt-4 sm:grid-cols-2">
                  <Field label={a.code === "airport_pickup" ? "Flight number" : "Train"}><Input value={e.details.flight ?? ""} onChange={(ev) => set(a.code, { details: { ...e.details, flight: ev.target.value.toUpperCase() } })} placeholder={a.code === "airport_pickup" ? "KQ612" : "Madaraka Express"} /></Field>
                  <Field label="Arrival time"><Input type="time" value={e.details.time ?? ""} onChange={(ev) => set(a.code, { details: { ...e.details, time: ev.target.value } })} /></Field>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}

function PaymentFlow({ result, listing }: { result: { booking: Trip; payment: PaymentResult }; listing?: ListingDetail }) {
  const { data: config } = useConfig();
  const payOpts = usePayOptions();
  const ref = result.booking.ref;
  const { data: trip } = useQuery({
    queryKey: ["trip", ref, "pay"],
    queryFn: () => get<Trip>(`/api/bookings/${ref}`),
    refetchInterval: (q) => (q.state.data && ["confirmed", "checked_in", "expired", "cancelled"].includes(q.state.data.status) ? false : 2000),
    initialData: result.booking,
  });
  const [now, setNow] = React.useState(() => Date.now());
  React.useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  const [busy, setBusy] = React.useState<string | null>(null);
  const status = trip?.status ?? "held";
  const p = result.payment;
  const left = trip?.hold_expires_at ? Math.max(0, Math.floor((new Date(trip.hold_expires_at).getTime() - now) / 1000)) : 0;
  const failed = lastFailure(trip?.payments);
  // A retry can change the amount (e.g. switching to the deposit), so show the prompt that is actually open.
  const payAmount = trip?.payments.find((x) => x.status === "pending")?.amount ?? p.amount;
  const [waitingSince, setWaitingSince] = React.useState(() => Date.now());

  async function retry(method?: "mpesa" | "card", plan?: "deposit") {
    setBusy(plan ? "deposit" : method ?? "mpesa");
    try {
      const r = await post<PaymentResult>(`/api/bookings/${ref}/pay`, { method, plan });
      setWaitingSince(Date.now());
      if (r.method === "card" && r.checkout_url) window.location.href = r.checkout_url;
      else toast.success(r.message || "We've sent a new M-Pesa prompt to your phone.");
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <SiteHeader />
      <main className="container-narrow max-w-[720px] py-16">
        {status === "confirmed" || status === "checked_in" ? (
          <div className="text-center animate-slide-up">
            <CheckCircle2 className="mx-auto size-16 text-success" strokeWidth={1.5} />
            <h1 className="mt-6 text-[32px] font-bold tracking-tight">You&apos;re booked!</h1>
            <p className="mt-2 text-lg text-ink-2">{listing?.name} · {fmtRange(trip?.check_in, trip?.check_out)} · Ref <b className="text-ink">{ref}</b></p>
            <div className="mx-auto mt-10 max-w-md space-y-4 text-left">
              {[
                ["Now", "Confirmation by SMS with your trip link"],
                ["3 days before", "We ask about breakfast, arrival time and travel"],
                ["Day before", "Directions, landmark and Wi-Fi by SMS"],
                ["Arrival morning", "Your door code arrives by SMS"],
              ].map(([when, what]) => (
                <div key={when} className="flex gap-4">
                  <span className="mt-1.5 size-2.5 shrink-0 rounded-full bg-brand-500" />
                  <p><b>{when}</b> — <span className="text-ink-2">{what}</span></p>
                </div>
              ))}
            </div>
            <Button asChild variant="brand" size="xl" className="mt-10"><Link href={`/trips/${ref}`}>View your trip</Link></Button>
          </div>
        ) : status === "expired" || status === "cancelled" ? (
          <div className="text-center">
            <h1 className="text-[28px] font-bold">Your hold expired</h1>
            <p className="mt-2 text-ink-2">We didn&apos;t receive payment in time, so the home was released. It may still be free — try again.</p>
            <Button asChild className="mt-8"><Link href={listing ? `/stays/${listing.slug}` : "/"}>Back to the listing</Link></Button>
          </div>
        ) : p.method === "card" ? (
          <div className="text-center">
            <CreditCard className="mx-auto size-14 text-ink-2" strokeWidth={1.4} />
            <h1 className="mt-6 text-[28px] font-bold">Finish paying by card</h1>
            <p className="mt-2 text-ink-2">We&apos;re holding {listing?.name} for you for {Math.floor(left / 60)}:{String(left % 60).padStart(2, "0")}.</p>
            {p.checkout_url && !p.error && <Button asChild variant="brand" size="xl" className="mt-8"><a href={p.checkout_url}>Open secure checkout</a></Button>}
            {p.error && (
              <>
                <p className="mt-4 text-danger">{p.error}</p>
                <Button variant="brand" size="xl" className="mt-6" onClick={() => retry("card")} loading={busy === "card"} disabled={!!busy}>Try again</Button>
              </>
            )}
            {payOpts.cardTest && <CardTestHint className="mx-auto mt-6 max-w-md" />}
          </div>
        ) : (
          <div className="text-center">
            <div className="relative mx-auto grid size-28 place-items-center rounded-[28px] border-4 border-ink bg-white">
              <Smartphone className="size-12" strokeWidth={1.3} />
              {!failed && <span className="absolute -top-2 -right-2 grid size-9 place-items-center rounded-full bg-brand-500 text-white animate-pulse-ring"><Spinner className="size-4 text-white" /></span>}
            </div>
            <h1 className="mt-8 text-[28px] font-bold tracking-tight">{failed ? "Payment not completed" : "Check your phone"}</h1>
            <p className="mx-auto mt-2 max-w-md text-lg text-ink-2">
              {failed
                ? <>Nothing was charged. Your dates for {listing?.name} are still held — try again below.</>
                : <>Enter your M-Pesa PIN to pay <b className="text-ink">{kes(payAmount)}</b> for {listing?.name}. Your booking confirms the moment it goes through.</>}
            </p>
            {p.error && !failed && <p className="mt-4 text-danger">{p.error}</p>}
            {failed && (
              <div className="mx-auto mt-6 max-w-md">
                <FailureNotice payment={failed} busy={busy} onRetry={() => retry("mpesa")} onCard={() => retry("card")}
                  onDeposit={trip?.price.payment_plan === "full" ? () => retry("mpesa", "deposit") : undefined} />
              </div>
            )}
            <p className="mt-6 text-sm text-ink-2">Holding your dates for <b className="text-ink tabular-nums">{Math.floor(left / 60)}:{String(left % 60).padStart(2, "0")}</b> · Ref {ref}</p>
            {!failed && (
              <div className="mt-8 flex flex-wrap justify-center gap-3">
                <Button variant="soft" onClick={() => retry("mpesa")} loading={busy === "mpesa"} disabled={!!busy}>Resend M-Pesa prompt</Button>
                <Button variant="soft" onClick={() => retry("card")} loading={busy === "card"} disabled={!!busy}>Pay by card instead</Button>
              </div>
            )}
            {config?.demo && (
              <div className="mt-4 flex flex-wrap justify-center gap-2">
                <Button variant="ocean" size="sm" onClick={async () => { await post(`/api/demo/pay/${ref}`); }}>Simulate payment (demo)</Button>
                <Button variant="ghost" size="sm" onClick={async () => { await post(`/api/demo/pay/${ref}`, { result: 1032 }); }}>Simulate “cancelled on phone”</Button>
                <Button variant="ghost" size="sm" onClick={async () => { await post(`/api/demo/pay/${ref}`, { result: 1 }); }}>Simulate “insufficient funds”</Button>
              </div>
            )}
            {(failed || now - waitingSince > 30_000) && (
              <div className="mx-auto mt-8 max-w-md"><PaybillBox bookingRef={ref} amount={trip?.price.amount_due_now || p.amount || 0} defaultOpen={failed?.suggest === "paybill"} /></div>
            )}
            <p className="mt-10 text-xs text-ink-2">The real prompt comes from M-Pesa, and we never ask you to pay a personal number · {fmtTime(new Date(now).toISOString())}</p>
          </div>
        )}
      </main>
    </>
  );
}

function CheckoutSkeleton() {
  return (
    <>
      <SiteHeader />
      <main className="container-narrow max-w-[1160px] pt-8">
        <Skeleton className="h-9 w-64" />
        <div className="mt-8 grid gap-20 lg:grid-cols-[1fr_420px]">
          <div className="space-y-6"><Skeleton className="h-40" /><Skeleton className="h-40" /></div>
          <Skeleton className="h-96 rounded-2xl" />
        </div>
      </main>
    </>
  );
}
