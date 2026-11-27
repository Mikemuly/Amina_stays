"use client";

import { useQueryClient } from "@tanstack/react-query";
import { AlertCircle, Landmark } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { useConfig } from "@/components/providers";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { post } from "@/lib/api";
import { kes } from "@/lib/format";
import type { TripPayment } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Stripe test mode: the cards that work there (no money moves). */
export function CardTestHint({ className }: { className?: string }) {
  return (
    <p className={cn("rounded-xl bg-surface p-3 text-[13px] text-ink-2", className)}>
      <b className="text-ink">Test mode</b> — pay with card <span className="font-mono text-ink">4242 4242 4242 4242</span>, any future date and any CVC. No money moves.
    </p>
  );
}

/** The newest payment if it failed (payments[] is newest first) — a pending retry hides an older failure. */
export function lastFailure(payments: TripPayment[] | undefined) {
  const p = payments?.[0];
  return p && p.status === "failed" ? p : undefined;
}

/** Plain-language reason for a failed payment plus the next step that fits it (M-Pesa result codes mapped server-side). */
export function FailureNotice({ payment: p, onRetry, onCard, onDeposit, depositAmount, busy }: {
  payment: TripPayment;
  onRetry?: () => void;
  onCard?: () => void;
  onDeposit?: () => void;
  depositAmount?: number;
  busy?: string | null;
}) {
  const s = p.suggest;
  const card = p.method === "card"; // a failed card payment is retried by card: there's no prompt to resend
  return (
    <div role="alert" className="rounded-2xl border border-danger/20 bg-danger-50 p-4 text-left">
      <p className="flex items-start gap-2 text-[15px] font-semibold text-danger"><AlertCircle className="mt-0.5 size-4 shrink-0" /> {p.failure_message || "That payment didn't go through."}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {s === "deposit" && onDeposit && <Button size="sm" variant="dark" onClick={onDeposit} loading={busy === "deposit"} disabled={!!busy}>Pay only the deposit{depositAmount ? ` (${kes(depositAmount)})` : ""}</Button>}
        {!card && p.retryable !== false && onRetry && <Button size="sm" variant={s === "deposit" ? "soft" : "dark"} onClick={onRetry} loading={busy === "mpesa" || busy === "pay"} disabled={!!busy}>{s === "wait" ? "Resend after a minute" : "Resend M-Pesa prompt"}</Button>}
        {onCard && (card ? p.retryable !== false : true) && <Button size="sm" variant={card ? "dark" : "soft"} onClick={onCard} loading={busy === "card"} disabled={!!busy}>{card ? "Try the card again" : "Pay by card"}</Button>}
      </div>
    </div>
  );
}

/** Lipa na M-Pesa Paybill fallback for when the STK prompt can't reach the phone, plus "I've paid" code matching. */
export function PaybillBox({ bookingRef, amount, defaultOpen = false }: { bookingRef: string; amount: number; defaultOpen?: boolean }) {
  const { data: config } = useConfig();
  const qc = useQueryClient();
  const [open, setOpen] = React.useState(defaultOpen);
  const [code, setCode] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const pb = config?.paybill;
  // Paybill confirmations arrive by callback; while the instructions are open, check every few seconds.
  React.useEffect(() => {
    if (!open || !pb) return;
    const id = setInterval(() => qc.invalidateQueries({ queryKey: ["trip", bookingRef] }), 5000);
    return () => clearInterval(id);
  }, [open, pb, qc, bookingRef]);
  if (!pb) return null;

  async function claim() {
    setBusy(true);
    try {
      const r = await post<{ status: "matched" | "pending_review"; message: string }>(`/api/bookings/${bookingRef}/claim`, { code: code.trim().toUpperCase() });
      if (r.status === "matched") toast.success(r.message || "Payment found — thank you!");
      else toast.message(r.message || "Thanks — Amina will match your payment shortly.");
      setCode("");
      await qc.invalidateQueries({ queryKey: ["trip", bookingRef] });
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)} className="text-sm font-semibold underline underline-offset-4">
        Prompt not arriving? Pay with Paybill instead
      </button>
    );
  }
  return (
    <div className="rounded-2xl border border-line-soft p-5 text-left">
      <p className="flex items-center gap-2 font-semibold"><Landmark className="size-4" /> Pay with M-Pesa Paybill</p>
      <ol className="mt-3 list-decimal space-y-1 pl-5 text-[15px] text-ink-2">
        <li>M-Pesa → Lipa na M-Pesa → <b className="text-ink">Pay Bill</b></li>
        <li>Business number <b className="font-mono text-ink">{pb.number}</b></li>
        <li>Account number <b className="font-mono text-ink">{bookingRef}</b></li>
        <li>Amount <b className="text-ink">{kes(amount)}</b>, then your PIN</li>
      </ol>
      <p className="mt-3 text-sm text-ink-2">It confirms here automatically. Paid already? Enter the M-Pesa code from your SMS:</p>
      <div className="mt-2 flex gap-2">
        <Input value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} placeholder="e.g. SKL3X7QW2P" maxLength={12} className="font-mono" aria-label="M-Pesa transaction code" />
        <Button onClick={claim} loading={busy} disabled={code.trim().length < 8}>I&apos;ve paid</Button>
      </div>
    </div>
  );
}
