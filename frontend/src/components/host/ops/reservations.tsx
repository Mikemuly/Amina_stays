"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { CalendarSearch, Search, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";

import { ChannelBadge, ErrorBlock, PageHeader, StatusBadge, Table, Td, Tr } from "@/components/host/common";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { EmptyState, Skeleton, Spinner } from "@/components/ui/misc";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/overlays";
import { get, qs } from "@/lib/api";
import { CHANNEL_LABEL, fmtRange, kes, plural } from "@/lib/format";
import { cn } from "@/lib/utils";

import { BalanceChip, Countdown, GuestLine, RelTime, RiskChip } from "./bits";
import { fmtPhone, useDebounced } from "./lib";
import { NewReservationButton } from "./new-reservation";
import type { ReservationRow } from "./types";

const TABS = [
  { key: "all", label: "All", status: "" },
  { key: "upcoming", label: "Upcoming", status: "held,confirmed" },
  { key: "in_house", label: "In-house", status: "checked_in" },
  { key: "completed", label: "Completed", status: "completed" },
  { key: "cancelled", label: "Cancelled", status: "cancelled,refund_due" },
];
const CHANNELS = ["web", "ussd", "sms", "voice", "whatsapp", "walk_in", "airbnb", "booking_com"];
const LIMIT = 200;

export function ReservationsView() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const tab = TABS.find((t) => t.key === params.get("status")) ?? TABS[0];
  const channel = params.get("channel") ?? "";
  const from = params.get("from") ?? "";
  const to = params.get("to") ?? "";
  const [search, setSearch] = React.useState(params.get("q") ?? "");
  const q = useDebounced(search.trim(), 300);

  const setParams = (patch: Record<string, string>) => {
    const next = new URLSearchParams(params.toString());
    Object.entries(patch).forEach(([k, v]) => (v ? next.set(k, v) : next.delete(k)));
    const s = next.toString();
    router.replace(s ? `${pathname}?${s}` : pathname, { scroll: false });
  };

  const query = useQuery({
    queryKey: ["host", "ops", "reservations", tab.status, channel, q, from, to],
    queryFn: () => get<ReservationRow[]>(`/api/host/reservations${qs({ status: tab.status, channel, q, from, to, limit: LIMIT })}`),
    placeholderData: keepPreviousData,
    refetchInterval: 30_000,
  });
  const rows = query.data;
  const filtered = Boolean(channel || q || from || to);

  const live = (rows ?? []).filter((r) => !["cancelled", "expired", "refund_due"].includes(r.status));
  const booked = live.reduce((n, r) => n + r.total, 0);
  const outstanding = live.reduce((n, r) => n + (r.status === "completed" ? 0 : r.balance_due), 0);

  const open = (ref: string) => router.push(`/host/reservations/${ref}`);
  const clear = () => {
    setSearch("");
    setParams({ channel: "", from: "", to: "", q: "" });
  };

  return (
    <div>
      <PageHeader
        title="Reservations"
        subtitle="Every booking — website, USSD, SMS, voice calls and walk-ins — in one list."
        actions={<NewReservationButton />}
      />

      <Tabs value={tab.key} onValueChange={(v) => setParams({ status: v === "all" ? "" : v })}>
        <TabsList className="no-scrollbar overflow-x-auto">
          {TABS.map((t) => (
            <TabsTrigger key={t.key} value={t.key} className="shrink-0">
              {t.label}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <div className="relative min-w-[220px] flex-1 sm:max-w-sm">
          <Search className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-ink-3" />
          <Input
            type="search"
            aria-label="Search reservations"
            placeholder="Search guest, phone, home or ref"
            className="h-10 pl-10"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <Select aria-label="Channel" className="h-10 w-auto min-w-40 text-sm" value={channel} onChange={(e) => setParams({ channel: e.target.value })}>
          <option value="">All channels</option>
          {CHANNELS.map((c) => (
            <option key={c} value={c}>
              {CHANNEL_LABEL[c] ?? c}
            </option>
          ))}
        </Select>
        <div className="flex w-full items-center gap-1.5 rounded-lg border border-line bg-white pr-1 pl-3 sm:w-auto">
          <CalendarSearch className="size-4 shrink-0 text-ink-3" />
          <span className="hidden text-[13px] text-ink-2 sm:inline">Staying</span>
          <input
            type="date"
            aria-label="Staying from"
            className="h-9 min-w-0 flex-1 rounded-md bg-transparent px-1.5 text-sm outline-none focus-visible:ring-1 focus-visible:ring-ink sm:flex-none"
            value={from}
            onChange={(e) => setParams({ from: e.target.value })}
          />
          <span className="text-ink-3">→</span>
          <input
            type="date"
            aria-label="Staying until"
            className="h-9 min-w-0 flex-1 rounded-md bg-transparent px-1.5 text-sm outline-none focus-visible:ring-1 focus-visible:ring-ink sm:flex-none"
            value={to}
            min={from || undefined}
            onChange={(e) => setParams({ to: e.target.value })}
          />
        </div>
        {filtered && (
          <Button variant="ghost" size="sm" onClick={clear}>
            <X className="size-3.5" /> Clear
          </Button>
        )}
        <div className="ml-auto flex items-center gap-3 text-[13px] text-ink-2 tabular-nums">
          {query.isFetching && rows && <Spinner className="size-4" />}
          {rows && (
            <span>
              {plural(rows.length, "reservation")}
              {rows.length >= LIMIT && " (latest)"} · {kes(booked)} booked
              {outstanding > 0 && <span className="font-semibold text-warning"> · {kes(outstanding)} outstanding</span>}
            </span>
          )}
        </div>
      </div>

      <div className="mt-4">
        {query.error && !rows ? (
          <ErrorBlock error={query.error} retry={() => query.refetch()} />
        ) : !rows ? (
          <div className="space-y-2 rounded-2xl border border-line-soft bg-white p-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} className="h-12" />
            ))}
          </div>
        ) : rows.length === 0 ? (
          <EmptyState
            icon={<Search className="size-5" />}
            title={filtered ? "No reservations match" : `No ${tab.key === "all" ? "" : tab.label.toLowerCase() + " "}reservations`}
            action={
              filtered ? (
                <Button variant="soft" onClick={clear}>
                  Clear filters
                </Button>
              ) : (
                <NewReservationButton variant="dark" />
              )
            }
          >
            {filtered ? "Try another name, phone number or date range." : "New bookings from every channel will appear here."}
          </EmptyState>
        ) : (
          <>
            <div className={cn("hidden rounded-2xl border border-line-soft bg-white md:block", query.isPlaceholderData && "opacity-70")}>
              <Table head={["Reservation", "Guest", "Stay", "Channel", "Status", <span key="t" className="block text-right">Total</span>, "Risk"]}>
                {rows.map((r) => {
                  const owing = r.balance_due > 0 && !["cancelled", "refund_due", "expired", "completed"].includes(r.status);
                  return (
                    <Tr key={r.ref} onClick={() => open(r.ref)}>
                      <Td className="whitespace-nowrap">
                        <Link
                          href={`/host/reservations/${r.ref}`}
                          onClick={(e) => e.stopPropagation()}
                          className="block font-mono text-[13px] font-semibold hover:underline"
                        >
                          {r.ref}
                        </Link>
                        <span className="block text-xs text-ink-3">
                          <RelTime at={r.created_at} />
                        </span>
                      </Td>
                      <Td className="max-w-[210px]">
                        <GuestLine name={r.guest.name} phone={r.guest.phone} nationality={r.guest.nationality} showPhone />
                      </Td>
                      <Td className="max-w-[220px]">
                        <span className="block truncate font-medium">{r.unit.name}</span>
                        <span className="block text-[13px] whitespace-nowrap text-ink-2 tabular-nums">
                          {fmtRange(r.check_in, r.check_out)} · {plural(r.nights, "night")}
                        </span>
                      </Td>
                      <Td>
                        <ChannelBadge channel={r.channel} />
                      </Td>
                      <Td className="whitespace-nowrap">
                        <StatusBadge status={r.status} label={r.status === "held" ? "Held" : r.status_label} />
                        {r.status === "held" && r.hold_expires_at && (
                          <span className="mt-1 block text-xs text-ink-2">
                            <Countdown to={r.hold_expires_at} /> to pay
                          </span>
                        )}
                      </Td>
                      <Td className="text-right whitespace-nowrap tabular-nums">
                        <span className="block font-semibold">{kes(r.total)}</span>
                        {owing ? (
                          <span className="block text-xs font-semibold text-warning">{kes(r.balance_due)} due</span>
                        ) : r.amount_paid > 0 && !["cancelled", "refund_due"].includes(r.status) ? (
                          <span className="block text-xs text-success">Paid</span>
                        ) : (
                          <span className="block text-xs text-ink-3">{kes(r.amount_paid)} paid</span>
                        )}
                      </Td>
                      <Td>
                        {r.risk_score >= 40 ? <RiskChip score={r.risk_score} /> : <span className="text-xs text-ink-3">—</span>}
                      </Td>
                    </Tr>
                  );
                })}
              </Table>
            </div>

            <ul className="space-y-2 md:hidden">
              {rows.map((r) => (
                <li key={r.ref}>
                  <Link href={`/host/reservations/${r.ref}`} className="block rounded-2xl border border-line-soft bg-white p-4 active:bg-surface">
                    <div className="flex items-start justify-between gap-3">
                      <GuestLine name={r.guest.name} phone={r.guest.phone} nationality={r.guest.nationality} className="text-sm" />
                      <span className="shrink-0 text-sm font-semibold tabular-nums">{kes(r.total)}</span>
                    </div>
                    <p className="mt-1 text-[13px] text-ink-2">
                      {r.unit.name} · {fmtRange(r.check_in, r.check_out)} · {plural(r.nights, "night")}
                    </p>
                    <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
                      <StatusBadge status={r.status} label={r.status === "held" ? "Held" : r.status_label} />
                      <ChannelBadge channel={r.channel} />
                      {r.balance_due > 0 && !["cancelled", "refund_due", "expired", "completed"].includes(r.status) && (
                        <BalanceChip balance={r.balance_due} status={r.status} />
                      )}
                      <RiskChip score={r.risk_score} />
                      <span className="ml-auto font-mono text-xs text-ink-3">{r.ref}</span>
                    </div>
                    <p className="mt-1.5 text-xs text-ink-3">
                      {fmtPhone(r.guest.phone)} · booked <RelTime at={r.created_at} />
                    </p>
                  </Link>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}
