"use client";

import { useQuery } from "@tanstack/react-query";
import { Award, CircleCheck, KeyRound, MapPin, MessageSquare, Reply, Sparkles, Star, Tag, Wand2 } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { ChannelBadge, ErrorBlock, LoadingBlock, PageHeader, Table, Td, Tr } from "@/components/host/common";
import { Button } from "@/components/ui/button";
import { Select, Textarea } from "@/components/ui/input";
import { Avatar, Badge, EmptyState, Stars } from "@/components/ui/misc";
import { get, post } from "@/lib/api";
import { fmtDate, plural } from "@/lib/format";
import { cn, flag } from "@/lib/utils";

import { useInvalidateHost } from "./queries";
import type { HostReview, HostReviewsResponse } from "./types";
import { Segmented, TableCard, countryName, errorMessage, reservationHref } from "./ui";

const CATEGORIES: { key: string; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { key: "cleanliness", label: "Cleanliness", icon: Sparkles },
  { key: "accuracy", label: "Accuracy", icon: CircleCheck },
  { key: "check_in", label: "Check-in", icon: KeyRound },
  { key: "communication", label: "Communication", icon: MessageSquare },
  { key: "location", label: "Location", icon: MapPin },
  { key: "value", label: "Value", icon: Tag },
];

type RatingFilter = "all" | "5" | "4" | "3" | "low";
const PAGE = 20;

const fmtRating = (r: number | null | undefined) => (r == null ? "–" : r.toFixed(2).replace(/0$/, ""));

export function ReviewsPage() {
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ["host", "reviews"], queryFn: () => get<HostReviewsResponse>("/api/host/reviews") });
  const [rating, setRating] = React.useState<RatingFilter>("all");
  const [unit, setUnit] = React.useState("");
  const [needsReply, setNeedsReply] = React.useState(false);
  const [limit, setLimit] = React.useState(PAGE);

  if (error) return <ErrorBlock error={error} retry={refetch} />;

  const reviews = data?.reviews ?? [];
  const units = [...(data?.by_unit ?? [])].sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0));
  const shown = reviews.filter(
    (r) =>
      (rating === "all" || (rating === "low" ? r.rating <= 2 : r.rating === Number(rating))) &&
      (!unit || r.unit === unit) &&
      (!needsReply || !r.host_response),
  );
  const unanswered = reviews.filter((r) => !r.host_response).length;
  const dist = [5, 4, 3, 2, 1].map((n) => ({ n, count: reviews.filter((r) => r.rating === n).length }));
  const maxDist = Math.max(1, ...dist.map((d) => d.count));
  const s = data?.summary;

  return (
    <>
      <PageHeader title="Reviews" subtitle="Verified stays only — every review comes from a completed booking, left by SMS reply or on the web." />

      {isLoading || !s ? (
        <LoadingBlock rows={5} />
      ) : (
        <div className="space-y-6">
          <div className="grid gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
            <section className="rounded-2xl border border-line-soft bg-white p-6">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-[13px] font-semibold text-ink-2">Overall rating</p>
                  <p className="mt-1 flex items-center gap-2 text-5xl leading-none font-bold tracking-tight tabular-nums">
                    {fmtRating(s.rating)}
                    <Star className="size-8 fill-ink text-ink" />
                  </p>
                  <p className="mt-2 text-[14px] text-ink-2">{plural(s.count, "review")} across {plural(units.length, "home")}</p>
                </div>
                {s.guest_favourite ? (
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-brand-50 px-3 py-1.5 text-[13px] font-bold text-brand-700">
                    <Award className="size-4" /> Guest favourite
                  </span>
                ) : (
                  <span className="max-w-40 text-right text-[12px] leading-snug text-ink-2">Guest favourite needs a 4.8+ average from 5+ reviews</span>
                )}
              </div>
              <ul className="mt-5 space-y-1.5">
                {dist.map((d) => (
                  <li key={d.n}>
                    <button
                      type="button"
                      onClick={() => setRating(d.n <= 2 ? "low" : (String(d.n) as RatingFilter))}
                      className="group flex w-full items-center gap-3 text-[13px]"
                      aria-label={`Show ${d.n}-star reviews`}
                    >
                      <span className="w-3 font-semibold tabular-nums">{d.n}</span>
                      <span className="h-2 flex-1 overflow-hidden rounded-full bg-line-soft">
                        <span className="block h-full rounded-full bg-ink transition-all group-hover:bg-brand-500" style={{ width: `${(d.count / maxDist) * 100}%` }} />
                      </span>
                      <span className="w-8 text-right text-ink-2 tabular-nums">{d.count}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>

            <section className="rounded-2xl border border-line-soft bg-white p-6">
              <p className="text-[13px] font-semibold text-ink-2">Category ratings</p>
              <div className="mt-4 grid gap-x-8 gap-y-4 sm:grid-cols-2">
                {CATEGORIES.map((c) => {
                  const v = s.categories[c.key];
                  return (
                    <div key={c.key} className="flex items-center gap-3">
                      <span className="grid size-9 shrink-0 place-items-center rounded-full bg-surface">
                        <c.icon className="size-4" />
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-baseline justify-between">
                          <span className="text-[14px] font-medium">{c.label}</span>
                          <span className="text-[14px] font-bold tabular-nums">{v ? v.toFixed(1) : "–"}</span>
                        </div>
                        <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-line-soft">
                          <div className={cn("h-full rounded-full", v && v < 4 ? "bg-warning" : "bg-ink")} style={{ width: `${((v ?? 0) / 5) * 100}%` }} />
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
              <p className="mt-5 text-[12.5px] text-ink-2">Guests rate categories on the web after an SMS review. Anything under 4.0 is highlighted.</p>
            </section>
          </div>

          <TableCard title="By home" description="Click a home to see only its reviews.">
            <Table head={["Home", "Rating", "Reviews", "Weakest area", ""]} empty="No reviews yet.">
              {units.map((u) => {
                const weakest = Object.entries(u.categories).sort((a, b) => a[1] - b[1])[0];
                return (
                  <Tr key={u.unit} onClick={() => setUnit(unit === u.unit ? "" : u.unit)} className={cn(unit === u.unit && "bg-surface")}>
                    <Td className="font-semibold">{u.unit}</Td>
                    <Td>
                      <span className="inline-flex items-center gap-2">
                        <Stars rating={u.rating ?? 0} />
                        <span className="font-semibold tabular-nums">{fmtRating(u.rating)}</span>
                      </span>
                    </Td>
                    <Td className="tabular-nums">{u.count}</Td>
                    <Td className="text-ink-2">
                      {weakest ? (
                        <span className={cn(weakest[1] < 4 && "font-semibold text-warning")}>
                          {CATEGORIES.find((c) => c.key === weakest[0])?.label ?? weakest[0]} {weakest[1].toFixed(1)}
                        </span>
                      ) : (
                        "–"
                      )}
                    </Td>
                    <Td className="text-right">
                      {u.guest_favourite && (
                        <Badge tone="brand">
                          <Award className="size-3" /> Guest favourite
                        </Badge>
                      )}
                    </Td>
                  </Tr>
                );
              })}
            </Table>
          </TableCard>

          <section>
            <div className="mb-4 flex flex-wrap items-center gap-3">
              <h2 className="mr-auto text-lg font-bold tracking-tight">
                {plural(shown.length, "review")}
                {unit && <span className="font-normal text-ink-2"> · {unit}</span>}
              </h2>
              <Segmented<RatingFilter>
                label="Filter by rating"
                size="sm"
                value={rating}
                onChange={(v) => {
                  setRating(v);
                  setLimit(PAGE);
                }}
                options={[
                  { value: "all", label: "All" },
                  { value: "5", label: "5★" },
                  { value: "4", label: "4★" },
                  { value: "3", label: "3★" },
                  { value: "low", label: "1–2★" },
                ]}
              />
              <Select value={unit} onChange={(e) => setUnit(e.target.value)} aria-label="Filter by home" className="h-9 w-52 text-sm">
                <option value="">All homes</option>
                {units.map((u) => (
                  <option key={u.unit} value={u.unit}>
                    {u.unit}
                  </option>
                ))}
              </Select>
              <button
                type="button"
                aria-pressed={needsReply}
                onClick={() => setNeedsReply((v) => !v)}
                className={cn(
                  "inline-flex h-9 items-center gap-1.5 rounded-full border px-3.5 text-[13px] font-semibold transition",
                  needsReply ? "border-ink bg-ink text-white" : "border-line-soft bg-white text-ink-2 hover:text-ink",
                )}
              >
                <Reply className="size-3.5" /> Needs a reply
                <span className={cn("tabular-nums", needsReply ? "text-white/70" : "text-ink-3")}>{unanswered}</span>
              </button>
            </div>

            {shown.length === 0 ? (
              <EmptyState icon={<Star className="size-5" />} title="No reviews match">
                Try another rating or home.
              </EmptyState>
            ) : (
              <ul className="space-y-3">
                {shown.slice(0, limit).map((r) => (
                  <ReviewCard key={r.id} review={r} />
                ))}
              </ul>
            )}
            {shown.length > limit && (
              <div className="mt-4 flex justify-center">
                <Button variant="soft" onClick={() => setLimit((l) => l + PAGE)}>
                  Show more ({shown.length - limit} left)
                </Button>
              </div>
            )}
          </section>
        </div>
      )}
    </>
  );
}

function suggestion(r: HostReview) {
  const first = r.guest.split(" ")[0];
  if (r.rating >= 4) return `Asante sana, ${first}! We're so glad you enjoyed ${r.unit}. Karibu tena — it would be lovely to host you again.`;
  return `Thank you for the honest feedback, ${first}. I'm sorry ${r.unit} fell short — we've already looked into it with the team. I'd love the chance to make it right on your next visit.`;
}

function ReviewCard({ review: r }: { review: HostReview }) {
  const invalidate = useInvalidateHost();
  const [open, setOpen] = React.useState(false);
  const [text, setText] = React.useState("");
  const [saving, setSaving] = React.useState(false);
  const low = r.rating <= 2;

  const submit = async () => {
    setSaving(true);
    try {
      await post(`/api/host/reviews/${r.id}/respond`, { text: text.trim() });
      toast.success("Response published", { description: "It appears under the review on the listing page." });
      setOpen(false);
      invalidate();
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <li className={cn("rounded-2xl border bg-white p-5", low ? "border-danger/30" : "border-line-soft")}>
      <div className="flex flex-wrap items-start gap-3">
        <Avatar name={r.guest} size={40} />
        <div className="min-w-0 flex-1 basis-40">
          <p className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[15px] font-semibold">
            <span className="min-w-0 [overflow-wrap:anywhere]">{r.guest}</span>
            {r.nationality && (
              <span className="text-[13px] font-normal text-ink-2" title={countryName(r.nationality)}>
                {flag(r.nationality)} {countryName(r.nationality)}
              </span>
            )}
          </p>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[13px] text-ink-2">
            <span className="font-medium text-ink">{r.unit}</span>·
            <Link href={reservationHref(r.ref)} className="font-mono hover:text-ink hover:underline">
              {r.ref}
            </Link>
            ·<span>{fmtDate(r.created_at, "d MMM yyyy")}</span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <ChannelBadge channel={r.channel} />
          {low && <Badge tone="danger">Worth a call</Badge>}
        </div>
      </div>

      <div className="mt-3 flex items-center gap-2">
        <Stars rating={r.rating} size={15} />
        <span className="text-[13px] font-semibold tabular-nums">{r.rating}.0</span>
      </div>
      {r.comment ? <p className="mt-2 text-[15px] leading-relaxed">{r.comment}</p> : <p className="mt-2 text-[14px] text-ink-3 italic">Rating only — no comment left.</p>}
      {Object.keys(r.categories).length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {CATEGORIES.filter((c) => r.categories[c.key]).map((c) => (
            <span key={c.key} className={cn("rounded-full px-2.5 py-0.5 text-[12px] font-medium", r.categories[c.key] < 4 ? "bg-warning-50 text-warning" : "bg-surface text-ink-2")}>
              {c.label} {r.categories[c.key]}
            </span>
          ))}
        </div>
      )}

      {r.host_response ? (
        <div className="mt-4 rounded-xl border-l-2 border-ocean-500 bg-ocean-50/60 px-4 py-3">
          <p className="text-[12px] font-bold tracking-wide text-ocean-700 uppercase">Your response</p>
          <p className="mt-1 text-[14px] leading-relaxed text-ink">{r.host_response}</p>
        </div>
      ) : open ? (
        <div className="mt-4 space-y-2">
          <Textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} placeholder={`Reply publicly to ${r.guest.split(" ")[0]}…`} aria-label="Your response" autoFocus />
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="ghost" size="sm" onClick={() => setText(suggestion(r))}>
              <Wand2 className="size-4" /> Suggest a reply
            </Button>
            <span className="text-[12px] text-ink-2">Public — shown under the review on the listing.</span>
            <div className="ml-auto flex gap-2">
              <Button variant="ghost" size="sm" onClick={() => setOpen(false)} disabled={saving}>
                Cancel
              </Button>
              <Button variant="dark" size="sm" onClick={submit} loading={saving} disabled={!text.trim()}>
                Publish response
              </Button>
            </div>
          </div>
        </div>
      ) : (
        <Button variant="soft" size="sm" className="mt-4" onClick={() => setOpen(true)}>
          <Reply className="size-4" /> Reply
        </Button>
      )}
    </li>
  );
}
