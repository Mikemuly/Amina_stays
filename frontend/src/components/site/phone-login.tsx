"use client";

import { useQueryClient } from "@tanstack/react-query";
import { ShieldCheck } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { post } from "@/lib/api";
import type { Me } from "@/lib/types";

export function PhoneLogin({ onDone, title, subtitle, cta = "Continue" }: { onDone?: (me: Me) => void; title?: string; subtitle?: string; cta?: string }) {
  const qc = useQueryClient();
  const [step, setStep] = React.useState<"phone" | "code">("phone");
  const [phone, setPhone] = React.useState("");
  const [normalized, setNormalized] = React.useState("");
  const [code, setCode] = React.useState("");
  const [hint, setHint] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  async function requestCode(e?: React.FormEvent) {
    e?.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await post<{ phone: string; sandbox: boolean; simulator?: boolean; debug_code?: string }>("/api/auth/otp/request", { phone });
      setNormalized(r.phone);
      setStep("code");
      setHint(
        r.debug_code
          ? `Demo mode: your code is ${r.debug_code}`
          : r.simulator
            ? `Sandbox: the code was sent to the Africa's Talking simulator - open it as ${r.phone} to read it.`
            : r.sandbox
              ? "Sandbox: the code is printed in the server log."
              : null,
      );
      if (r.debug_code) setCode(r.debug_code);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function verify(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const me = await post<Me>("/api/auth/otp/verify", { phone: normalized, code });
      qc.setQueryData(["me"], me);
      await qc.invalidateQueries();
      toast.success(me.name ? `Karibu, ${me.name.split(" ")[0]}!` : "You're logged in");
      onDone?.(me);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      {title && <h3 className="text-[22px] font-bold tracking-tight">{title}</h3>}
      {subtitle && <p className="mt-1 text-[15px] text-ink-2">{subtitle}</p>}
      {step === "phone" ? (
        <form onSubmit={requestCode} className="mt-6 space-y-4">
          <Field label="Phone number" hint="Kenyan or international — we'll text you a 6-digit code. No password needed." error={error}>
            <Input
              autoFocus
              inputMode="tel"
              autoComplete="tel"
              placeholder="0712 345 678 or +44 7700 900123"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              required
            />
          </Field>
          <Button type="submit" variant="brand" size="lg" className="w-full" loading={busy}>
            {cta}
          </Button>
          <p className="flex items-start gap-2 text-[13px] text-ink-2">
            <ShieldCheck className="mt-0.5 size-4 shrink-0 text-ocean-600" />
            Booked with us by SMS, USSD or a phone call? It&apos;s the same account — just use that number.
          </p>
        </form>
      ) : (
        <form onSubmit={verify} className="mt-6 space-y-4">
          <Field label={`Enter the code sent to ${normalized}`} error={error} hint={hint}>
            <Input
              autoFocus
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              placeholder="••••••"
              className="text-center text-2xl tracking-[0.5em]"
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
              required
            />
          </Field>
          <Button type="submit" variant="brand" size="lg" className="w-full" loading={busy} disabled={code.length !== 6}>
            Verify &amp; continue
          </Button>
          <div className="flex justify-between text-[13px]">
            <button type="button" className="font-semibold underline" onClick={() => setStep("phone")}>
              Change number
            </button>
            <button type="button" className="font-semibold underline" onClick={() => requestCode()}>
              Resend code
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
