"use client";

import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, CreditCard, Lock, XCircle } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Logo } from "@/components/host/shell";
import { CardTestHint } from "@/components/site/payment-help";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { Skeleton, Spinner } from "@/components/ui/misc";
import { get, post } from "@/lib/api";
import { fmtRange, kes } from "@/lib/format";

type CardSession = {
  ref: string; unit: string; check_in: string; check_out: string; amount: number; currency: string; status: string;
  booking_status: string; expires_at: string | null; expired: boolean; simulated: boolean;
  purpose?: string; change?: { check_in: string; check_out: string } | null;
  provider?: string; checkout_url?: string | null; test_mode?: boolean;
};

const CONFIRM_FOR_MS = 90_000; // how long the page keeps asking after the guest comes back from the checkout

const PURPOSE: Record<string, string> = { deposit: "Deposit", balance: "Balance", addon: "Extras", change: "Date change" };

/** /pay/card/<token>: the link guests get for a card payment. With Stripe it opens Stripe Checkout and is where
 * Stripe brings them back (?session_id=… paid, ?cancelled=1 not); each load asks Stripe through our API, so the
 * stay confirms here even without a webhook. With no card keys it's a simulated checkout, so demos run offline. */
export function CardPayView({ token }: { token: string }) {
  const params = useSearchParams();
  const returning = params.has("session_id");
  const cancelled = params.get("cancelled") === "1";
  const [openedAt] = React.useState(() => Date.now());
  const { data: s, refetch, isLoading, error } = useQuery({
    queryKey: ["card", token],
    queryFn: () => get<CardSession>(`/api/pay/card/${token}`),
    refetchInterval: (q) => (returning && q.state.data?.status === "pending" && Date.now() - openedAt < CONFIRM_FOR_MS ? 2000 : false),
  });
  const [waitedOut, setWaitedOut] = React.useState(false);
  React.useEffect(() => {
    if (!returning) return;
    const id = setTimeout(() => setWaitedOut(true), CONFIRM_FOR_MS + 500); // polling has stopped by then
    return () => clearTimeout(id);
  }, [returning]);
  const hosted = !!s && !s.simulated;
  const open = hosted && s.status === "pending" && !s.expired && !returning && !cancelled && !!s.checkout_url;
  React.useEffect(() => {
    if (open && s?.checkout_url) window.location.replace(s.checkout_url);
  }, [open, s?.checkout_url]);
  const [card, setCard] = React.useState({ number: "4084 0840 8408 4081", expiry: "12/30", cvc: "408", name: "" });
  const [busy, setBusy] = React.useState<string | null>(null);

  async function act(action: "pay" | "decline") {
    setBusy(action);
    try {
      await new Promise((r) => setTimeout(r, 900));
      await post(`/api/pay/card/${token}`, { action });
      await refetch();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="min-h-dvh bg-surface">
      <header className="border-b border-line-soft bg-white">
        <div className="container-narrow flex h-16 max-w-[560px] items-center justify-between">
          <span className="flex items-center gap-2 font-bold"><Logo className="size-8 rounded-lg" /> Amina Stays</span>
          <span className="flex items-center gap-1.5 text-sm text-ink-2"><Lock className="size-4" /> Secure checkout</span>
        </div>
      </header>
      <main className="container-narrow max-w-[560px] py-10">
        {isLoading ? (
          <Skeleton className="h-96 rounded-2xl" />
        ) : error || !s ? (
          <p className="rounded-2xl bg-white p-8 text-center">This payment link isn&apos;t valid. <Link className="underline" href="/trips">Go to your trips</Link></p>
        ) : s.status === "success" ? (
          <Result ok title="Payment successful" text={s.purpose === "change" ? `${kes(s.amount)} paid — your stay at ${s.unit} is now ${fmtRange(s.change?.check_in ?? s.check_in, s.change?.check_out ?? s.check_out)}. Details are on their way by SMS.` : `${kes(s.amount)} paid for ${s.unit}. Your confirmation is on its way by SMS.`} href={`/trips/${s.ref}`} />
        ) : s.expired ? (
          <Result title="This checkout has expired" text="The hold on these dates ran out before payment. The home may still be free — try booking again." href="/" cta="Back to Amina Stays" />
        ) : hosted ? (
          <Hosted s={s} open={open} returning={returning} cancelled={cancelled} waitedOut={waitedOut} />
        ) : (
          <div className="overflow-hidden rounded-2xl bg-white shadow-soft">
            <div className="border-b border-line-soft p-6">
              <p className="text-sm text-ink-2">
                {s.purpose && PURPOSE[s.purpose] ? `${PURPOSE[s.purpose]} · ` : ""}{s.unit} · {fmtRange(s.change?.check_in ?? s.check_in, s.change?.check_out ?? s.check_out)} · Ref {s.ref}
              </p>
              <p className="mt-1 text-[32px] font-bold tracking-tight">{kes(s.amount)}</p>
              {s.status === "failed" && <p className="mt-2 flex items-center gap-2 text-sm text-danger"><XCircle className="size-4" /> Your card was declined. Try again or use another card.</p>}
            </div>
            <div className="space-y-4 p-6">
              <Field label="Card number"><Input inputMode="numeric" value={card.number} onChange={(e) => setCard({ ...card, number: e.target.value })} autoComplete="cc-number" /></Field>
              <div className="grid grid-cols-2 gap-4">
                <Field label="Expiry"><Input value={card.expiry} onChange={(e) => setCard({ ...card, expiry: e.target.value })} autoComplete="cc-exp" /></Field>
                <Field label="CVC"><Input inputMode="numeric" value={card.cvc} onChange={(e) => setCard({ ...card, cvc: e.target.value })} autoComplete="cc-csc" /></Field>
              </div>
              <Field label="Name on card"><Input value={card.name} onChange={(e) => setCard({ ...card, name: e.target.value })} autoComplete="cc-name" /></Field>
              <Button variant="brand" size="xl" className="w-full" onClick={() => act("pay")} loading={busy === "pay"} disabled={!!busy}>
                <CreditCard className="size-5" /> Pay {kes(s.amount)}
              </Button>
              {s.simulated && (
                <div className="flex items-center justify-between gap-3 rounded-xl bg-surface p-3 text-xs text-ink-2">
                  <span>Demo checkout — no real card is charged.</span>
                  <button className="font-semibold underline" onClick={() => act("decline")} disabled={!!busy}>Simulate a decline</button>
                </div>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

/** A real provider's checkout (Stripe): opening it, waiting for it after the guest is back, or not finished. */
function Hosted({ s, open, returning, cancelled, waitedOut }: { s: CardSession; open: boolean; returning: boolean; cancelled: boolean; waitedOut: boolean }) {
  const what = `${s.purpose && PURPOSE[s.purpose] ? `${PURPOSE[s.purpose]} · ` : ""}${s.unit} · Ref ${s.ref}`;
  if (s.status !== "pending") {
    return <Result title="This payment didn't go through" text="Nothing was charged. Open your trip to pay again — or, if you booked by SMS, reply PAY for a new link." href={`/trips/${s.ref}`} />;
  }
  if (returning) {
    return waitedOut ? (
      <Result title="Still confirming your payment" text={`We haven't heard back from the card company yet. You'll get an SMS the moment ${kes(s.amount)} is confirmed — please don't pay again.`} href={`/trips/${s.ref}`} />
    ) : (
      <div role="status" className="rounded-2xl bg-white p-10 text-center shadow-soft">
        <Spinner className="mx-auto size-10" />
        <h1 className="mt-5 text-2xl font-bold">Confirming your payment…</h1>
        <p className="mt-2 text-ink-2">{kes(s.amount)} · {what}. This takes a few seconds.</p>
      </div>
    );
  }
  return (
    <div className="rounded-2xl bg-white p-8 shadow-soft">
      <p className="text-sm text-ink-2">{what}</p>
      <p className="mt-1 text-[32px] font-bold tracking-tight">{kes(s.amount)}</p>
      {cancelled ? (
        <p className="mt-2 flex items-center gap-2 text-sm text-ink-2"><XCircle className="size-4" /> Payment not finished — your card wasn&apos;t charged.</p>
      ) : (
        <p className="mt-2 flex items-center gap-2 text-sm text-ink-2" role="status">{open && <Spinner className="size-4" />} Opening the secure checkout…</p>
      )}
      {s.checkout_url && (
        <Button asChild variant="brand" size="xl" className="mt-6 w-full">
          <a href={s.checkout_url}><CreditCard className="size-5" /> {cancelled ? "Return to the secure checkout" : `Pay ${kes(s.amount)} by card`}</a>
        </Button>
      )}
      {s.test_mode && <CardTestHint className="mt-4" />}
      <p className="mt-6 text-center text-sm text-ink-2"><Link className="underline" href={`/trips/${s.ref}`}>View your trip</Link></p>
    </div>
  );
}

function Result({ ok, title, text, href, cta = "View your trip" }: { ok?: boolean; title: string; text: string; href: string; cta?: string }) {
  return (
    <div className="rounded-2xl bg-white p-10 text-center shadow-soft">
      {ok ? <CheckCircle2 className="mx-auto size-14 text-success" strokeWidth={1.5} /> : <XCircle className="mx-auto size-14 text-ink-3" strokeWidth={1.5} />}
      <h1 className="mt-5 text-2xl font-bold">{title}</h1>
      <p className="mt-2 text-ink-2">{text}</p>
      <Button asChild size="lg" className="mt-8"><Link href={href}>{cta}</Link></Button>
    </div>
  );
}
