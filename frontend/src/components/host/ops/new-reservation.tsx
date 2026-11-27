"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Banknote, CircleCheck, CircleAlert, Clock, CreditCard, Plus, Smartphone } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { SwitchRow, useDebounced } from "@/components/host/biz/ui";
import { useConfig, usePayOptions } from "@/components/providers";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { Field, Input, Select } from "@/components/ui/input";
import { Skeleton, Stepper } from "@/components/ui/misc";
import { post } from "@/lib/api";
import { fmtDate, kes, plural } from "@/lib/format";
import type { PaymentResult, Quote, Trip } from "@/lib/types";
import { cn } from "@/lib/utils";

import { Overline, Segmented } from "./bits";
import { addDaysISO, daysBetween, kenyaDate, useHostAction, useListings, useNow } from "./lib";

type PayMode = "mpesa" | "card" | "cash" | "none";

const PAY_MODES: { value: PayMode; title: string; text: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { value: "mpesa", title: "Request M-Pesa", text: "STK push to the guest's phone", icon: Smartphone },
  { value: "card", title: "Card link by SMS", text: "A secure checkout link to the guest's phone", icon: CreditCard },
  { value: "cash", title: "Cash received", text: "Record the amount taken now", icon: Banknote },
  { value: "none", title: "Pay on arrival", text: "Confirm now, collect later", icon: Clock },
];

export function NewReservationButton({
  variant = "brand", size = "md", className,
}: { variant?: "brand" | "dark" | "soft"; size?: "sm" | "md"; className?: string }) {
  const [open, setOpen] = React.useState(false);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant={variant} size={size} className={className}>
          <Plus className="size-4" strokeWidth={2.5} /> New reservation
        </Button>
      </DialogTrigger>
      {open && <NewReservationForm onDone={() => setOpen(false)} />}
    </Dialog>
  );
}

function NewReservationForm({ onDone }: { onDone: () => void }) {
  const router = useRouter();
  const now = useNow(60_000);
  const today = now ? kenyaDate(now) : "";
  const { data: listings, isLoading: loadingListings } = useListings();
  const homes = React.useMemo(() => (listings ?? []).filter((l) => l.status !== "draft"), [listings]);

  const [unitId, setUnitId] = React.useState("");
  const [checkIn, setCheckIn] = React.useState("");
  const [checkOut, setCheckOut] = React.useState("");
  const [phone, setPhone] = React.useState("");
  const [name, setName] = React.useState("");
  const [adults, setAdults] = React.useState(1);
  const [children, setChildren] = React.useState(0);
  const { data: config } = useConfig();
  const { mpesa } = usePayOptions();
  const [picked, setMode] = React.useState<PayMode>("mpesa");
  const mode: PayMode = !mpesa && picked === "mpesa" ? "card" : picked; // no M-Pesa here: the card link instead
  const payModes = PAY_MODES.filter((m) => mpesa || m.value !== "mpesa");
  const [amount, setAmount] = React.useState("");
  const [plan, setPlan] = React.useState<"full" | "deposit">("full");
  const [custom, setCustom] = React.useState(false);
  const [override, setOverride] = React.useState("");
  const [reason, setReason] = React.useState("");
  const [tried, setTried] = React.useState(false);

  const unit = homes.find((h) => String(h.id) === unitId) ?? homes[0];
  const ci = checkIn || today;
  const co = checkOut || (ci ? addDaysISO(ci, 1) : "");
  const nights = ci && co ? daysBetween(ci, co) : 0;
  const maxGuests = unit?.max_guests ?? 16;

  const quote = useQuery({
    queryKey: ["host", "ops", "quote", unit?.slug, ci, co, adults, children],
    queryFn: () => post<Quote>(`/api/listings/${unit!.slug}/quote`, { check_in: ci, check_out: co, adults, children }),
    enabled: Boolean(unit && ci && co && nights > 0),
    staleTime: 30_000,
    retry: false,
  });
  // with a custom price, the backend prices the stay exactly as the booking will be (cleaning, levy and VAT on top)
  const agreed = useDebounced(custom && Number(override) > 0 ? Math.round(Number(override)) : 0, 300);
  const agreedQuote = useQuery({
    queryKey: ["host", "ops", "quote", unit?.slug, ci, co, adults, children, "agreed", agreed],
    queryFn: () => post<Quote>(`/api/listings/${unit!.slug}/quote`, { check_in: ci, check_out: co, adults, children, price_override: agreed }),
    enabled: Boolean(quote.data && agreed > 0),
    placeholderData: keepPreviousData,
    staleTime: 30_000,
    retry: false,
  });
  const total = custom ? (agreed > 0 ? agreedQuote.data?.total : undefined) : quote.data?.total;

  const errors = {
    dates: !ci || !co ? "Choose the dates." : nights <= 0 ? "Check-out must be after check-in." : "",
    phone: phone.replace(/\D/g, "").length < 9 ? "Enter the guest's phone number." : "",
    amount: mode === "cash" && amount !== "" && Number(amount) <= 0 ? "Enter the amount received." : "",
    override: custom && !(Number(override) > 0) ? "Enter the price for the whole stay." : "",
    reason: custom && !reason.trim() ? "Say why — it goes on the booking's timeline." : "",
  };
  const valid = Boolean(unit) && !errors.dates && !errors.phone && !errors.amount && !errors.override && !errors.reason;

  const create = useHostAction(
    () =>
      post<{ booking: Trip; payment: PaymentResult }>("/api/host/reservations", {
        unit: unit!.id,
        check_in: ci,
        check_out: co,
        phone: phone.trim(),
        name: name.trim(),
        adults,
        children,
        payment: mode,
        amount: mode === "cash" ? Number(amount || total || 0) || undefined : undefined,
        payment_plan: mode === "mpesa" || mode === "card" ? plan : "full",
        price_override: custom ? Number(override) : null,
        override_reason: custom ? reason.trim() : "",
      }),
    {
      onSuccess: ({ booking, payment }) => {
        const note =
          payment?.error ??
          (mode === "mpesa"
            ? `M-Pesa prompt for ${kes(payment?.amount ?? 0)} sent to the guest's phone.`
            : mode === "card"
              ? "Card payment link sent by SMS."
              : mode === "cash"
                ? "Cash payment recorded."
                : "Confirmed — the guest pays on arrival.");
        if (payment?.error) toast.warning(`${booking.ref} created, but the payment request failed`, { description: note });
        else toast.success(`${booking.ref} created for ${booking.unit.name}`, { description: note });
        onDone();
        router.push(`/host/reservations/${booking.ref}`);
      },
    },
  );

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setTried(true);
    if (valid) create.mutate();
  };

  const problems = quote.data?.problems ?? [];

  return (
    <DialogContent
      size="lg"
      title="New reservation"
      description="Create a walk-in or phone booking"
      footer={
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="text-sm">
            {total !== undefined && nights > 0 ? (
              <span>
                <span className="font-bold tabular-nums">{kes(total)}</span>
                <span className="text-ink-2"> · {plural(nights, "night")}</span>
              </span>
            ) : (
              <span className="text-ink-2">{custom && nights > 0 ? "Enter the price for the stay" : "Choose a home and dates to see the price"}</span>
            )}
          </div>
          <Button type="submit" form="new-reservation" variant="dark" loading={create.isPending} disabled={tried && !valid}>
            Create reservation
          </Button>
        </div>
      }
    >
      <form id="new-reservation" onSubmit={submit} className="grid grid-cols-1 gap-x-8 gap-y-6 px-6 py-6 md:grid-cols-2" noValidate>
        <div className="space-y-5">
          <Overline>The stay</Overline>
          <Field label="Home">
            {loadingListings ? (
              <Skeleton className="h-11" />
            ) : (
              <Select value={unit ? String(unit.id) : ""} onChange={(e) => setUnitId(e.target.value)} aria-label="Home">
                {homes.map((h) => (
                  <option key={h.id} value={h.id}>
                    {h.name} · sleeps {h.max_guests}
                    {h.status === "paused" ? " (paused)" : ""}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Check-in">
              <Input type="date" value={ci} min={today || undefined} onChange={(e) => setCheckIn(e.target.value)} />
            </Field>
            <Field label="Check-out">
              <Input type="date" value={co} min={ci ? addDaysISO(ci, 1) : undefined} onChange={(e) => setCheckOut(e.target.value)} />
            </Field>
          </div>
          {tried && errors.dates && <p className="-mt-3 text-[13px] text-danger">{errors.dates}</p>}
          <div className="divide-y divide-line-soft rounded-xl border border-line-soft">
            <div className="flex items-center justify-between px-4 py-3">
              <div>
                <p className="text-sm font-semibold">Adults</p>
                <p className="text-[13px] text-ink-2">Age 13+</p>
              </div>
              <Stepper label="adults" value={adults} min={1} max={Math.max(1, maxGuests - children)} onChange={setAdults} />
            </div>
            <div className="flex items-center justify-between px-4 py-3">
              <div>
                <p className="text-sm font-semibold">Children</p>
                <p className="text-[13px] text-ink-2">Ages 2–12</p>
              </div>
              <Stepper label="children" value={children} min={0} max={Math.max(0, maxGuests - adults)} onChange={setChildren} />
            </div>
          </div>
          <QuoteStatus loading={quote.isFetching && !quote.data} error={quote.error} available={quote.data?.available} problems={problems} ci={ci} co={co} />
        </div>

        <div className="space-y-5">
          <Overline>The guest</Overline>
          <Field label="Phone number" error={tried ? errors.phone : undefined} hint="Booking updates and the door code go to this number by SMS.">
            <Input type="tel" inputMode="tel" autoComplete="off" placeholder="0712 345 678 or +44 7700 900123" value={phone} onChange={(e) => setPhone(e.target.value)} />
          </Field>
          <Field label="Name">
            <Input autoComplete="off" placeholder="Guest's full name" value={name} onChange={(e) => setName(e.target.value)} />
          </Field>

          <fieldset>
            <legend className="mb-2 text-[13px] font-semibold">Payment</legend>
            <div className="grid grid-cols-2 gap-2">
              {payModes.map((m) => (
                <label
                  key={m.value}
                  className={cn(
                    "relative flex cursor-pointer flex-col gap-1 rounded-xl border p-3 transition-colors has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ink",
                    mode === m.value ? "border-ink bg-surface/60 ring-1 ring-ink" : "border-line hover:border-ink-3",
                  )}
                >
                  <input type="radio" name="payment" value={m.value} checked={mode === m.value} onChange={() => setMode(m.value)} className="sr-only" />
                  <m.icon className="size-4.5 text-ink" />
                  <span className="text-sm font-semibold">{m.title}</span>
                  <span className="text-xs leading-snug text-ink-2">{m.text}</span>
                </label>
              ))}
            </div>
          </fieldset>
          {mode === "cash" && (
            <Field label="Amount received (KES)" error={tried ? errors.amount : undefined} hint={total ? `Full stay: ${kes(total)}` : undefined}>
              <Input type="number" inputMode="numeric" min={0} placeholder={total ? String(total) : "0"} value={amount} onChange={(e) => setAmount(e.target.value)} />
            </Field>
          )}
          {(mode === "mpesa" || mode === "card") && (
            <Segmented
              label="Charge now"
              size="sm"
              value={plan}
              onChange={setPlan}
              options={[
                { value: "full", label: "Full stay" },
                { value: "deposit", label: `${config?.deposit_percent ?? 30}% deposit` },
              ]}
            />
          )}
          <div className="rounded-xl border border-line-soft p-4">
            <SwitchRow label="Custom price" description="Repeat guest, long stay or a deal agreed on the phone." checked={custom} onCheckedChange={setCustom} />
            {custom && (
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <Field label="Price for the stay (KES)" error={tried ? errors.override : undefined} hint="Cleaning and levy are added on top.">
                  <Input type="number" inputMode="numeric" min={0} value={override} onChange={(e) => setOverride(e.target.value)} placeholder={quote.data ? String(quote.data.accommodation) : ""} />
                </Field>
                <Field label="Reason" error={tried ? errors.reason : undefined}>
                  <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Returning guest" />
                </Field>
              </div>
            )}
          </div>
        </div>
      </form>
    </DialogContent>
  );
}

function QuoteStatus({
  loading, error, available, problems, ci, co,
}: { loading: boolean; error: unknown; available?: boolean; problems: string[]; ci: string; co: string }) {
  if (!ci || !co) return null;
  if (loading) return <Skeleton className="h-12" />;
  if (error) return null;
  if (available === undefined) return null;
  return available ? (
    <p className="flex items-center gap-2 rounded-xl bg-success-50 px-4 py-3 text-[13px] font-medium text-success">
      <CircleCheck className="size-4 shrink-0" /> Available {fmtDate(ci)} → {fmtDate(co)}
    </p>
  ) : (
    <div className="flex gap-2 rounded-xl bg-warning-50 px-4 py-3 text-[13px] font-medium text-warning">
      <CircleAlert className="mt-px size-4 shrink-0" />
      <div>{problems.length ? problems.map((p) => <p key={p}>{p}</p>) : <p>Those dates may not be bookable.</p>}</div>
    </div>
  );
}
