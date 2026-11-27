"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Ban, CircleCheck, MessageSquareText, Phone, Plus, Search, ShieldAlert, Star, Users, X } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { ChannelBadge, ErrorBlock, PageHeader, StatusBadge, Table, Td, Tr } from "@/components/host/common";
import { Button } from "@/components/ui/button";
import { Dialog, SheetContent } from "@/components/ui/dialog";
import { Input, Select, Textarea } from "@/components/ui/input";
import { Avatar, Badge, Skeleton, Stars } from "@/components/ui/misc";
import { Switch, Tooltip } from "@/components/ui/overlays";
import { get, patch, qs } from "@/lib/api";
import { fmtDate, fmtRange, kes, plural } from "@/lib/format";
import { sized } from "@/lib/img";
import { COUNTRIES, cn } from "@/lib/utils";

import { useInvalidateHost } from "./queries";
import type { GuestDetail, GuestRow } from "./types";
import { ConfirmDialog, Field, Flag, Segmented, StatTile, countryName, errorMessage, isEqualJson, replaceSearchParams, reservationHref, useDebounced } from "./ui";

type Filter = "all" | "returning" | "blocked";

const LANGS: Record<string, string> = { en: "English", sw: "Kiswahili", fr: "Français", de: "Deutsch", it: "Italiano" };

export function GuestsPage() {
  const [q, setQ] = React.useState("");
  const [filter, setFilter] = React.useState<Filter>("all");
  // ?guest=<id> opens that profile, so reservations and the inbox can link straight to it
  const linked = Number(useSearchParams().get("guest")) || null;
  const [openId, setOpenIdState] = React.useState<number | null>(linked);
  const setOpenId = (id: number | null) => {
    setOpenIdState(id);
    replaceSearchParams({ guest: id === null ? null : String(id) });
  };
  const query = useDebounced(q.trim(), 250);
  const { data, isLoading, isFetching, error, refetch } = useQuery({
    queryKey: ["host", "guests", query, filter],
    queryFn: () => get<GuestRow[]>(`/api/host/guests${qs({ q: query, filter: filter === "all" ? "" : filter })}`),
    placeholderData: keepPreviousData,
  });
  const rows = data ?? [];
  const openRow = rows.find((r) => r.id === openId) ?? null;

  return (
    <>
      <PageHeader title="Guests" subtitle="One profile per phone number — whether they booked on the web, by USSD, SMS or a phone call." />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative w-full sm:w-80">
          <Search className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-ink-3" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name, phone or email" aria-label="Search guests" className="h-10 pl-10 text-sm" />
          {q && (
            <button type="button" aria-label="Clear search" onClick={() => setQ("")} className="absolute inset-y-0 right-2 my-auto grid size-7 place-items-center rounded-full text-ink-2 hover:bg-surface">
              <X className="size-3.5" />
            </button>
          )}
        </div>
        <Segmented<Filter>
          label="Guest filter"
          value={filter}
          onChange={setFilter}
          options={[
            { value: "all", label: "All guests" },
            { value: "returning", label: "Returning" },
            { value: "blocked", label: "Do-not-host" },
          ]}
        />
        <p className="ml-auto text-[13px] text-ink-2 tabular-nums">{isLoading ? "" : plural(rows.length, "guest")}</p>
      </div>

      {error ? (
        <ErrorBlock error={error} retry={refetch} />
      ) : (
        <div className={cn("overflow-hidden rounded-2xl border border-line-soft bg-white transition-opacity", isFetching && !isLoading && "opacity-70")}>
          {isLoading ? (
            <div className="space-y-3 p-5">
              {Array.from({ length: 8 }).map((_, i) => (
                <Skeleton key={i} className="h-11" />
              ))}
            </div>
          ) : (
            <Table
              head={["Guest", "From", "Stays", "Total spend", "Last stay", "Language", "First came via", "Tags", "ID", "SMS"]}
              empty={
                <span className="inline-flex flex-col items-center gap-2">
                  <Users className="size-5" />
                  {query ? `No guests match “${query}”.` : filter === "blocked" ? "No one is on the do-not-host list." : "No guests yet."}
                </span>
              }
              className="[&_table]:min-w-[1080px]"
            >
              {rows.map((g) => (
                <Tr key={g.id} onClick={() => setOpenId(g.id)} className={cn(g.blocked && "bg-danger-50/40")}>
                  <Td>
                    <div className="flex items-center gap-3">
                      <Avatar name={g.name || "Guest"} size={36} />
                      <div className="min-w-0">
                        <p className="flex items-center gap-2 font-semibold">
                          <span className="truncate">{g.name || "Unnamed guest"}</span>
                          {g.blocked && (
                            <Badge tone="danger">
                              <Ban className="size-3" /> Do not host
                            </Badge>
                          )}
                        </p>
                        <p className="font-mono text-[12px] text-ink-2">{g.phone}</p>
                      </div>
                    </div>
                  </Td>
                  <Td>
                    <Flag code={g.nationality} />
                  </Td>
                  <Td className="tabular-nums">
                    {g.stays ?? 0}
                    {(g.stays ?? 0) >= 2 && (
                      <Tooltip content="Returning guest">
                        <Star className="ml-1 inline size-3.5 fill-brand-500 text-brand-500" />
                      </Tooltip>
                    )}
                  </Td>
                  <Td className="font-semibold tabular-nums">{g.spend ? kes(g.spend) : <span className="font-normal text-ink-3">—</span>}</Td>
                  <Td className="whitespace-nowrap text-ink-2">{g.last_stay ? fmtDate(g.last_stay, "d MMM yyyy") : "—"}</Td>
                  <Td>
                    <span className="rounded-md bg-surface px-1.5 py-0.5 text-[11.5px] font-bold text-ink-2 uppercase">{g.lang}</span>
                  </Td>
                  <Td>{g.first_channel ? <ChannelBadge channel={g.first_channel} /> : <span className="text-ink-3">—</span>}</Td>
                  <Td>
                    <div className="flex max-w-44 flex-wrap gap-1">
                      {g.tags.slice(0, 2).map((t) => (
                        <span key={t} className="rounded-full bg-surface px-2 py-0.5 text-[11.5px] font-semibold text-ink-2">
                          {t}
                        </span>
                      ))}
                      {g.tags.length > 2 && <span className="text-[11.5px] text-ink-3">+{g.tags.length - 2}</span>}
                    </div>
                  </Td>
                  <Td>
                    {g.id_registered ? (
                      <Tooltip content="ID / passport on the guest register">
                        <CircleCheck className="size-[18px] text-success" aria-label="ID registered" />
                      </Tooltip>
                    ) : (
                      <span className="text-ink-3" aria-label="No ID">—</span>
                    )}
                  </Td>
                  <Td>
                    {g.opted_out ? (
                      <Badge tone="warning">Opted out</Badge>
                    ) : g.marketing_opt_in ? (
                      <Badge tone="success">Offers OK</Badge>
                    ) : (
                      <span className="text-[12px] text-ink-3">Service only</span>
                    )}
                  </Td>
                </Tr>
              ))}
            </Table>
          )}
        </div>
      )}
      <p className="mt-3 text-[12.5px] text-ink-2">
        “Opted out” guests replied STOP and get service messages only — never offers. “Offers OK” guests agreed to marketing when they booked.
      </p>

      <Dialog open={openId !== null} onOpenChange={(v) => !v && setOpenId(null)}>
        {openId !== null && <GuestSheet id={openId} row={openRow} />}
      </Dialog>
    </>
  );
}

function GuestSheet({ id, row }: { id: number; row: GuestRow | null }) {
  const { data: g, error, refetch } = useQuery({
    queryKey: ["host", "guest", id],
    queryFn: () => get<GuestDetail>(`/api/host/guests/${id}`),
  });
  if (g) return <GuestProfile key={g.id} guest={g} row={row} />;
  return (
    <SheetContent title={row?.name || row?.phone || "Guest"} width="max-w-xl">
      {error ? (
        <div className="p-6">
          <ErrorBlock error={error} retry={refetch} />
        </div>
      ) : (
        <div className="space-y-4 p-6">
          <Skeleton className="h-16" />
          <Skeleton className="h-24" />
          <Skeleton className="h-40" />
        </div>
      )}
    </SheetContent>
  );
}

function GuestProfile({ guest: g, row }: { guest: GuestDetail; row: GuestRow | null }) {
  const invalidate = useInvalidateHost();
  const base = React.useMemo(() => ({ name: g.name, email: g.email, nationality: g.nationality, lang: g.lang, notes: g.notes, tags: g.tags }), [g]);
  const [draft, setDraft] = React.useState(base);
  const [seen, setSeen] = React.useState(base);
  if (seen !== base) {
    setSeen(base);
    if (isEqualJson(seen, draft)) setDraft(base);
  }
  const [tagDraft, setTagDraft] = React.useState("");
  const [saving, setSaving] = React.useState(false);
  const [blockOpen, setBlockOpen] = React.useState(false);
  const [reason, setReason] = React.useState(g.block_reason);
  const [blocking, setBlocking] = React.useState(false);
  const dirty = !isEqualJson(base, draft);

  // The detail endpoint doesn't annotate totals, so use the list row (or derive from bookings).
  const live = g.bookings.filter((b) => ["confirmed", "checked_in", "completed"].includes(b.status));
  const stays = row?.stays ?? live.length;
  const spend = row?.spend ?? live.reduce((s, b) => s + b.total - b.balance_due, 0);
  const lastStay = row?.last_stay ?? live[0]?.check_in ?? null;

  const save = async () => {
    setSaving(true);
    try {
      await patch(`/api/host/guests/${g.id}`, { ...draft, host_notes: draft.notes });
      toast.success("Guest profile saved");
      invalidate();
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setSaving(false);
    }
  };

  const setBlocked = async (blocked: boolean) => {
    setBlocking(true);
    try {
      await patch(`/api/host/guests/${g.id}`, { is_blocked: blocked, block_reason: blocked ? reason.trim() : "" });
      toast.success(blocked ? `${g.name || g.phone} is on the do-not-host list` : `${g.name || g.phone} can book again`);
      setBlockOpen(false);
      invalidate();
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setBlocking(false);
    }
  };

  const addTag = () => {
    const t = tagDraft.trim().toLowerCase().slice(0, 24);
    if (!t || draft.tags.includes(t) || draft.tags.length >= 12) return setTagDraft("");
    setDraft({ ...draft, tags: [...draft.tags, t] });
    setTagDraft("");
  };

  return (
    <SheetContent
      title={g.name || g.phone}
      width="max-w-xl"
      footer={
        dirty ? (
          <div className="flex items-center justify-end gap-2">
            <span className="mr-auto text-[13px] text-ink-2">Unsaved changes</span>
            <Button variant="ghost" size="sm" onClick={() => setDraft(base)} disabled={saving}>
              Discard
            </Button>
            <Button variant="dark" size="sm" onClick={save} loading={saving}>
              Save profile
            </Button>
          </div>
        ) : undefined
      }
    >
      <div className="flex items-center gap-4 border-b border-line-soft px-6 py-5">
        <Avatar name={g.name || "Guest"} size={56} />
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-2 text-lg font-bold">
            {g.name || "Unnamed guest"}
            {g.blocked && <Badge tone="danger">Do not host</Badge>}
            {stays >= 2 && <Badge tone="brand">Returning</Badge>}
          </p>
          <p className="font-mono text-[13px] text-ink-2">{g.phone}</p>
        </div>
      </div>
      <div className="flex flex-wrap gap-2 px-6 pt-4">
        <Button asChild variant="soft" size="sm">
          <a href={`tel:${g.phone}`}>
            <Phone className="size-4" /> Call
          </a>
        </Button>
        {g.thread_id ? (
          <Button asChild variant="soft" size="sm">
            <Link href={`/host/inbox?t=${g.thread_id}`}>
              <MessageSquareText className="size-4" /> Open conversation
            </Link>
          </Button>
        ) : (
          <Tooltip content="No messages with this guest yet">
            <span>
              <Button variant="soft" size="sm" disabled>
                <MessageSquareText className="size-4" /> Open conversation
              </Button>
            </span>
          </Tooltip>
        )}
      </div>

      <div className="grid grid-cols-3 gap-3 px-6 pt-4">
        <StatTile label="Stays" value={stays} />
        <StatTile label="Spend" value={spend ? kes(spend) : "—"} />
        <StatTile label="Last stay" value={lastStay ? fmtDate(lastStay, "d MMM yy") : "—"} />
      </div>

      <SheetSection title="Profile">
        <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-[14px]">
          <Fact label="First came via">{g.first_channel ? <ChannelBadge channel={g.first_channel} /> : "—"}</Fact>
          <Fact label="Guest since">{fmtDate(g.joined, "d MMM yyyy")}</Fact>
          <Fact label="ID on register">
            {g.identity.last4 ? (
              <span className="inline-flex items-center gap-1.5">
                <CircleCheck className="size-4 text-success" /> {g.identity.type} {g.identity.last4}
              </span>
            ) : (
              <span className="text-warning">Not registered</span>
            )}
          </Fact>
          <Fact label="Marketing">{g.opted_out ? <span className="text-warning">Opted out (STOP)</span> : g.marketing_opt_in ? "Opted in" : "Service messages only"}</Fact>
        </dl>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <Field label="Name">
            <Input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} className="h-10" />
          </Field>
          <Field label="Email">
            <Input type="email" value={draft.email} onChange={(e) => setDraft({ ...draft, email: e.target.value })} className="h-10" />
          </Field>
          <Field label="Nationality">
            <Select value={draft.nationality} onChange={(e) => setDraft({ ...draft, nationality: e.target.value })} className="h-10">
              <option value="">Unknown</option>
              {(draft.nationality && !COUNTRIES.some(([c]) => c === draft.nationality) ? [[draft.nationality, countryName(draft.nationality)] as [string, string]] : [])
                .concat(COUNTRIES)
                .map(([c, n]) => (
                  <option key={c} value={c}>
                    {n}
                  </option>
                ))}
            </Select>
          </Field>
          <Field label="Messages in">
            <Select value={draft.lang} onChange={(e) => setDraft({ ...draft, lang: e.target.value })} className="h-10">
              {Object.entries(LANGS).map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </Select>
          </Field>
        </div>
      </SheetSection>

      <SheetSection title="Private notes" hint="Only your team sees these.">
        <Textarea value={draft.notes} onChange={(e) => setDraft({ ...draft, notes: e.target.value })} rows={3} placeholder="Prefers the ground floor, arrives late on the SGR…" />
        <div className="mt-3">
          <p className="mb-2 text-[13px] font-semibold">Tags</p>
          <div className="flex flex-wrap items-center gap-1.5">
            {draft.tags.map((t) => (
              <span key={t} className="inline-flex items-center gap-1 rounded-full bg-surface py-1 pr-1 pl-2.5 text-[12.5px] font-semibold text-ink">
                {t}
                <button type="button" aria-label={`Remove tag ${t}`} onClick={() => setDraft({ ...draft, tags: draft.tags.filter((x) => x !== t) })} className="grid size-5 place-items-center rounded-full hover:bg-line-soft">
                  <X className="size-3" />
                </button>
              </span>
            ))}
            <div className="flex items-center gap-1">
              <Input
                value={tagDraft}
                onChange={(e) => setTagDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === ",") {
                    e.preventDefault();
                    addTag();
                  }
                }}
                placeholder="vip, corporate, honeymoon…"
                aria-label="Add tag"
                className="h-8 w-48 rounded-full px-3 text-[13px]"
              />
              <Button type="button" variant="ghost" size="sm" onClick={addTag} disabled={!tagDraft.trim()} aria-label="Add tag">
                <Plus className="size-4" />
              </Button>
            </div>
          </div>
        </div>
      </SheetSection>

      <SheetSection title="Do not host">
        <div className={cn("rounded-xl border p-4", g.blocked ? "border-danger/30 bg-danger-50" : "border-line-soft")}>
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="flex items-center gap-2 text-[15px] font-semibold">
                <ShieldAlert className={cn("size-4", g.blocked ? "text-danger" : "text-ink-2")} />
                {g.blocked ? "This guest can't book" : "Block future bookings"}
              </p>
              <p className="mt-1 text-[13px] leading-relaxed text-ink-2">
                Refuses new bookings on every channel — website, USSD, SMS and voice — with a polite “please contact us”. Existing bookings aren&apos;t cancelled.
              </p>
              {g.blocked && g.block_reason && <p className="mt-2 text-[13px] text-ink">Reason: {g.block_reason}</p>}
            </div>
            <Switch checked={g.blocked} onCheckedChange={(v) => (v ? setBlockOpen(true) : setBlocked(false))} disabled={blocking} aria-label="Do not host" />
          </div>
        </div>
      </SheetSection>

      <SheetSection title={`Bookings · ${g.bookings.length}`}>
        {g.bookings.length === 0 ? (
          <p className="text-[14px] text-ink-2">No bookings yet.</p>
        ) : (
          <ul className="space-y-2">
            {g.bookings.map((b) => (
              <li key={b.ref}>
                <Link href={reservationHref(b.ref)} className="flex items-center gap-3 rounded-xl border border-line-soft p-2.5 transition hover:border-ink-3">
                  {b.unit.cover ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={sized(b.unit.cover, 160)} alt="" className="size-12 shrink-0 rounded-lg object-cover" />
                  ) : (
                    <span className="size-12 shrink-0 rounded-lg bg-surface" />
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[14px] font-semibold">{b.unit.name}</p>
                    <p className="text-[12.5px] text-ink-2">
                      {fmtRange(b.check_in, b.check_out)} {b.check_in.slice(0, 4)} · {plural(b.nights, "night")} · <span className="font-mono">{b.ref}</span>
                    </p>
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-1">
                    <StatusBadge status={b.status} label={b.status_label} />
                    <span className="text-[12.5px] font-semibold tabular-nums">{kes(b.total)}</span>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </SheetSection>

      {g.reviews.length > 0 && (
        <SheetSection title="Reviews they left">
          <ul className="space-y-3">
            {g.reviews.map((r) => (
              <li key={r.ref} className="rounded-xl bg-surface p-3.5">
                <div className="flex items-center justify-between gap-2">
                  <Stars rating={r.rating} />
                  <span className="font-mono text-[12px] text-ink-2">{r.ref}</span>
                </div>
                {r.comment && <p className="mt-1.5 text-[14px] leading-relaxed">“{r.comment}”</p>}
              </li>
            ))}
          </ul>
        </SheetSection>
      )}

      <ConfirmDialog
        open={blockOpen}
        onOpenChange={setBlockOpen}
        title="Add to the do-not-host list?"
        confirmLabel="Block future bookings"
        tone="danger"
        loading={blocking}
        onConfirm={() => setBlocked(true)}
      >
        <p>
          {g.name || g.phone} won&apos;t be able to book on the website, USSD, SMS or by phone. They&apos;re not told why. Existing bookings stay as they are.
        </p>
        <Field label="Reason (private)">
          <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Party in breach of house rules, AMS-4821" maxLength={200} />
        </Field>
      </ConfirmDialog>
    </SheetContent>
  );
}

function SheetSection({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section className="border-t border-line-soft px-6 py-5 first:border-t-0">
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <h3 className="text-[15px] font-bold">{title}</h3>
        {hint && <span className="text-[12px] text-ink-2">{hint}</span>}
      </div>
      {children}
    </section>
  );
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-[12px] font-semibold tracking-wide text-ink-3 uppercase">{label}</dt>
      <dd className="mt-0.5">{children}</dd>
    </div>
  );
}
