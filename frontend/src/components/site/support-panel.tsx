"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { MessageSquareWarning, PhoneCall, Star } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { useConfig } from "@/components/providers";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { Field, Select, Textarea } from "@/components/ui/input";
import { Badge } from "@/components/ui/misc";
import { get, post } from "@/lib/api";
import { ago } from "@/lib/format";
import type { SupportTicket } from "@/lib/types";
import { cn } from "@/lib/utils";

const CATEGORIES: [string, string][] = [
  ["complaint", "Something went wrong"],
  ["billing", "Billing or a payment"],
  ["booking", "My booking or dates"],
  ["feedback", "Feedback or an idea"],
  ["other", "Something else"],
];
const TONE: Record<SupportTicket["status"], "warning" | "ocean" | "success" | "neutral"> = {
  open: "warning",
  in_progress: "ocean",
  resolved: "success",
  closed: "neutral",
};

/** The guest's support requests (complaints, call-backs, questions) with a reference each - the same tickets they
 * can raise and follow by SMS (COMPLAIN, CALL ME, TICKETS), USSD (Talk to Amina) or a voice message (press 5). */
export function SupportPanel({ booking }: { booking?: string }) {
  const qc = useQueryClient();
  const { data: config } = useConfig();
  const key = ["support", booking ?? "all"];
  const { data: tickets, isLoading } = useQuery({
    queryKey: key,
    queryFn: () => get<SupportTicket[]>(`/api/support/tickets${booking ? `?booking=${encodeURIComponent(booking)}` : ""}`),
    refetchInterval: 20_000,
  });
  const [open, setOpen] = React.useState(false);
  const [form, setForm] = React.useState({ category: "complaint", description: "" });
  const [busy, setBusy] = React.useState<string | null>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: ["support"] });

  async function run(what: string, fn: () => Promise<SupportTicket>, done: (t: SupportTicket) => string) {
    setBusy(what);
    try {
      const t = await fn();
      toast.success(done(t));
      refresh();
      return t;
    } catch (e) {
      toast.error((e as Error).message);
      return null;
    } finally {
      setBusy(null);
    }
  }

  const callBack = () =>
    run(
      "callback",
      () => post<SupportTicket>("/api/support/tickets", { callback: true, booking }),
      (t) => `Got it - ${config?.business.host_name ?? "Amina"} will call you back (reference ${t.ref}).`,
    );
  const submit = async () => {
    const t = await run(
      "new",
      () => post<SupportTicket>("/api/support/tickets", { ...form, booking }),
      (t) => `Logged as ${t.ref} - we'll text you the reply.`,
    );
    if (t) {
      setOpen(false);
      setForm({ category: "complaint", description: "" });
    }
  };
  const rate = (t: SupportTicket, rating: number) =>
    run(
      `rate-${t.id}`,
      () => post<SupportTicket>(`/api/support/tickets/${t.id}/rate`, { rating }),
      () => (rating <= 2 ? "Thank you - we're sorry, and we'll call you to put it right." : "Thank you for rating us!"),
    );

  const sms = config?.channels.sms_number;
  return (
    <div>
      <div className="grid gap-3 sm:grid-cols-2">
        <button
          type="button"
          onClick={callBack}
          disabled={busy === "callback"}
          className="flex items-start gap-3 rounded-2xl border border-line-soft p-5 text-left transition-colors hover:border-ink disabled:opacity-60"
        >
          <PhoneCall className="size-6 shrink-0" />
          <span>
            <b className="block">Request a call back</b>
            <span className="text-sm text-ink-2">We ring you - no airtime needed</span>
          </span>
        </button>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <button type="button" className="flex items-start gap-3 rounded-2xl border border-line-soft p-5 text-left transition-colors hover:border-ink">
              <MessageSquareWarning className="size-6 shrink-0" />
              <span>
                <b className="block">Raise a complaint or request</b>
                <span className="text-sm text-ink-2">You get a reference and a reply-by time</span>
              </span>
            </button>
          </DialogTrigger>
          <DialogContent title="Raise a complaint or request" size="sm">
            <div className="space-y-4 p-6">
              <Field label="What's it about?">
                <Select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
                  {CATEGORIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </Select>
              </Field>
              <Field label="Tell us what happened">
                <Textarea
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                  rows={4}
                  maxLength={1000}
                  placeholder="e.g. The neighbours played loud music until 2am"
                />
              </Field>
              <Button className="w-full" size="lg" onClick={submit} loading={busy === "new"} disabled={form.description.trim().length < 3}>
                Send to {config?.business.host_name ?? "Amina"}
              </Button>
              <p className="text-center text-xs text-ink-2">For a problem in the home (water, power, Wi-Fi) use &quot;Something&apos;s not working&quot; on your trip.</p>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      {isLoading ? null : tickets && tickets.length > 0 ? (
        <ul className="mt-5 divide-y divide-line-soft rounded-2xl border border-line-soft">
          {tickets.map((t) => {
            const reply = [...t.events].reverse().find((e) => e.kind === "reply");
            return (
              <li key={t.id} className="p-4 sm:p-5">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-[13px] font-semibold">{t.ref}</span>
                  <span className="text-[13px] text-ink-2">{t.category_label}</span>
                  <Badge tone={TONE[t.status]} dot className="ml-auto">{t.status_label}</Badge>
                </div>
                <p className="mt-1.5 text-[15px] break-words">{t.subject}</p>
                {reply && (
                  <p className="mt-2 rounded-xl bg-surface px-3 py-2 text-[14px] text-ink">
                    <span className="text-ink-2">Reply · {ago(reply.created_at)}: </span>
                    {reply.text}
                  </p>
                )}
                {t.status === "resolved" && t.resolution && <p className="mt-2 text-[13.5px] text-ink-2">Resolved: {t.resolution}</p>}
                <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-2 text-[12.5px] text-ink-2">
                  <span>Raised {ago(t.created_at)}</span>
                  {t.can_rate && (
                    <span className="flex items-center gap-1">
                      How did we do?
                      {[1, 2, 3, 4, 5].map((n) => (
                        <button
                          key={n}
                          type="button"
                          aria-label={`${n} out of 5`}
                          disabled={busy === `rate-${t.id}`}
                          onClick={() => rate(t, n)}
                          className="grid size-8 place-items-center rounded-full hover:bg-surface"
                        >
                          <Star className="size-4 text-ink-2" />
                        </button>
                      ))}
                    </span>
                  )}
                  {t.rating && (
                    <span className="flex items-center gap-0.5" aria-label={`Rated ${t.rating} out of 5`}>
                      {[1, 2, 3, 4, 5].map((n) => (
                        <Star key={n} className={cn("size-3.5", n <= t.rating! ? "fill-ink text-ink" : "text-line")} />
                      ))}
                    </span>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="mt-4 text-[14px] text-ink-2">No requests yet.</p>
      )}
      <p className="mt-4 text-[13px] text-ink-2">
        No data? Text <b className="font-semibold text-ink">COMPLAIN</b> and what happened, <b className="font-semibold text-ink">CALL ME</b> or{" "}
        <b className="font-semibold text-ink">TICKETS</b>{sms ? <> to <b className="font-semibold text-ink">{sms}</b></> : ""}
        {config?.channels.ussd_code ? <>, or dial {config.channels.ussd_code} → Talk to Amina</> : ""}.
      </p>
    </div>
  );
}
