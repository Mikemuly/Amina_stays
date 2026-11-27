"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, Gift, MessageCircle, Smartphone, Wifi } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { get, post } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import type { Rewards } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Amina Rewards on the account page: points for stays and feedback, swapped for Africa's Talking airtime or mobile
 * data, and an invite code that pays airtime to both guests after the friend's first stay. */
export function RewardsSection() {
  const qc = useQueryClient();
  const { data: r } = useQuery({ queryKey: ["me", "rewards"], queryFn: () => get<Rewards>("/api/me/rewards") });
  const [busy, setBusy] = React.useState<string | null>(null);
  const [code, setCode] = React.useState("");
  const [copied, setCopied] = React.useState(false);
  const ref = React.useRef<HTMLElement>(null);

  // the header menu links to /account#rewards: scroll here once the section has data to show
  React.useEffect(() => {
    if (r && window.location.hash === "#rewards") ref.current?.scrollIntoView({ block: "start" });
  }, [r]);

  if (!r) return null;

  async function act(what: string, path: string, body: Record<string, string>) {
    setBusy(what);
    try {
      const next = await post<Rewards>(path, body);
      qc.setQueryData(["me", "rewards"], next);
      if (next.message) toast.success(next.message);
      return true;
    } catch (e) {
      toast.error((e as Error).message);
      return false;
    } finally {
      setBusy(null);
    }
  }

  const progress = Math.min(100, Math.round((r.points / Math.max(r.redeem.points, 1)) * 100));
  const share = encodeURIComponent(r.share_text);
  return (
    <section id="rewards" ref={ref} className="mt-12 scroll-mt-24 border-t border-line-soft pt-10">
      <h2 className="flex items-center gap-2 text-[22px] font-bold"><Gift className="size-5" /> Amina Rewards</h2>
      {!r.enabled ? (
        <p className="mt-3 text-ink-2">Rewards are paused at the moment - your points are safe.</p>
      ) : (
        <div className="mt-4 grid gap-4 lg:grid-cols-2 [&>*]:min-w-0">
          <div className="rounded-2xl border border-line-soft p-5">
            <p className="text-sm text-ink-2">Your points</p>
            <p className="mt-1 text-[40px] leading-none font-semibold tabular-nums">{r.points.toLocaleString()}</p>
            <div className="mt-4 h-2 overflow-hidden rounded-full bg-line-soft" aria-hidden>
              <div className="h-full rounded-full bg-brand-500 transition-[width]" style={{ width: `${progress}%` }} />
            </div>
            <p className="mt-2 text-[13px] text-ink-2">{r.redeem.why_not || `${r.redeem.points} points = KES ${r.redeem.airtime} airtime or ${r.redeem.data_mb} MB of data`}</p>
            <div className="mt-4 grid gap-2 sm:grid-cols-2">
              <Button
                variant="dark"
                disabled={!r.redeem.can_airtime}
                loading={busy === "airtime"}
                onClick={() => act("airtime", "/api/me/rewards/redeem", { kind: "airtime" })}
              >
                <Smartphone className="size-4" /> KES {r.redeem.airtime} airtime
              </Button>
              <Button
                variant="soft"
                disabled={!r.redeem.can_data}
                loading={busy === "data"}
                onClick={() => act("data", "/api/me/rewards/redeem", { kind: "data" })}
              >
                <Wifi className="size-4" /> {r.redeem.data_mb} MB data
              </Button>
            </div>
            <p className="mt-3 text-[12.5px] text-ink-2">
              {r.rules.points_per_100} point{r.rules.points_per_100 === 1 ? "" : "s"} for every KES 100 of a stay, {r.rules.review_points} for sharing
              feedback. Sent straight to your phone through Africa&apos;s Talking. By SMS: POINTS, REDEEM AIRTIME, REDEEM DATA.
            </p>
          </div>

          <div className="rounded-2xl border border-line-soft p-5">
            <p className="text-sm text-ink-2">Invite friends</p>
            <div className="mt-2 flex items-center gap-2">
              <span className="font-mono text-[22px] font-semibold tracking-wide">{r.code}</span>
              <button
                type="button"
                onClick={async () => {
                  await navigator.clipboard?.writeText(r.share_text).catch(() => undefined);
                  setCopied(true);
                  setTimeout(() => setCopied(false), 1500);
                }}
                className="grid size-9 place-items-center rounded-full hover:bg-surface"
                aria-label="Copy invite message"
              >
                {copied ? <Check className="size-4 text-success" /> : <Copy className="size-4" />}
              </button>
            </div>
            <p className="mt-2 text-[14px] text-ink-2">
              After a friend&apos;s first stay you get KES {r.rules.referral_airtime} airtime and they get KES {r.rules.referee_airtime}.
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <Button asChild size="sm" variant="soft">
                <a href={`https://wa.me/?text=${share}`} target="_blank" rel="noopener noreferrer"><MessageCircle className="size-4" /> WhatsApp</a>
              </Button>
              <Button asChild size="sm" variant="soft">
                <a href={`sms:?&body=${share}`}><Smartphone className="size-4" /> SMS</a>
              </Button>
            </div>
            {r.referred_by && (
              <p className="mt-4 rounded-xl bg-surface px-3 py-2 text-[13.5px]">
                Invited by {r.referred_by}
                {r.referral_status === "pending" ? ` - your KES ${r.rules.referee_airtime} airtime arrives after your first stay.` : " - thank you!"}
              </p>
            )}
            {r.can_enter_code && (
              <form
                className="mt-4 flex gap-2"
                onSubmit={async (e) => {
                  e.preventDefault();
                  if (await act("code", "/api/me/rewards/referral", { code })) setCode("");
                }}
              >
                <Input
                  value={code}
                  onChange={(e) => setCode(e.target.value.toUpperCase())}
                  placeholder="A friend's code"
                  aria-label="A friend's invite code"
                  className="min-w-0 flex-1 font-mono uppercase"
                  maxLength={16}
                />
                <Button type="submit" variant="dark" loading={busy === "code"} disabled={code.trim().length < 4}>Apply</Button>
              </form>
            )}
          </div>

          {r.history.length > 0 && (
            <ul className="divide-y divide-line-soft rounded-2xl border border-line-soft lg:col-span-2">
              {r.history.slice(0, 8).map((h, i) => (
                <li key={i} className="flex items-center gap-3 px-4 py-3 text-[14px]">
                  <div className="min-w-0 flex-1">
                    <p className="truncate">{h.text}</p>
                    <p className={cn("text-[12.5px] text-ink-2", (h.status === "Failed" || h.status === "Rejected") && "text-danger")}>
                      {fmtDate(h.created_at, "d MMM yyyy")}
                      {h.status ? ` · ${h.status}` : ""}
                    </p>
                  </div>
                  {h.kind === "points" ? (
                    <span className={cn("shrink-0 font-semibold tabular-nums", (h.points ?? 0) < 0 ? "text-ink-2" : "text-success")}>
                      {(h.points ?? 0) > 0 ? "+" : ""}{h.points}
                    </span>
                  ) : (
                    <span className="shrink-0 font-semibold">{h.amount_text}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
