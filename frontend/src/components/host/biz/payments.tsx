"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Banknote, CircleAlert, Clock, CreditCard, HandCoins, Search, ShieldCheck, Smartphone, Undo2, X } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { ErrorBlock, KpiCard, PageHeader, StatusBadge, Table, Td, Tr } from "@/components/host/common";
import { usePayOptions } from "@/components/providers";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/misc";
import { Tooltip } from "@/components/ui/overlays";
import { get, post, qs } from "@/lib/api";
import { fmtDateTime, kes, plural } from "@/lib/format";
import { cn } from "@/lib/utils";

import { LedgerExport, OutstandingCard, UnmatchedCard } from "./payments-extras";
import { useInvalidateHost } from "./queries";
import type { LedgerResponse, PaymentRow, RefundRow } from "./types";
import { Callout, ConfirmDialog, Field, Segmented, TableCard, errorMessage, humanize, reservationHref, useDebounced } from "./ui";

type StatusFilter = "" | "success" | "pending" | "failed" | "expired" | "cancelled";
type MethodFilter = "all" | "mpesa" | "card" | "cash" | "bank";

const STATUS_LABEL: Record<string, string> = { success: "Paid", pending: "Pending", failed: "Failed", expired: "Expired", cancelled: "Cancelled", refunded: "Refunded" };
const PURPOSE_LABEL: Record<string, string> = { full: "Full payment", deposit: "Deposit", balance: "Balance", addon: "Add-on", change: "Date change" };
const REFUND_STATUS: Record<string, string> = { pending: "To send", success: "Sent", failed: "Failed" };

export function MethodChip({ method, label }: { method: string; label?: string }) {
  const meta: Record<string, { cls: string; icon: React.ComponentType<{ className?: string }>; text: string }> = {
    mpesa: { cls: "bg-success-50 text-success", icon: Smartphone, text: "M-Pesa" },
    card: { cls: "bg-[#eef2ff] text-[#1e40af]", icon: CreditCard, text: "Card" },
    cash: { cls: "bg-surface text-ink-2", icon: Banknote, text: "Cash" },
    bank: { cls: "bg-warning-50 text-warning", icon: HandCoins, text: "Bank" },
  };
  const m = meta[method] ?? { cls: "bg-surface text-ink-2", icon: Banknote, text: label ?? method };
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[12px] font-semibold whitespace-nowrap", m.cls)}>
      <m.icon className="size-3.5" />
      {label && !meta[method] ? label : m.text}
    </span>
  );
}

export function PaymentsPage() {
  const invalidate = useInvalidateHost();
  const { mpesa } = usePayOptions();
  const [status, setStatus] = React.useState<StatusFilter>("");
  const [method, setMethod] = React.useState<MethodFilter>("all");
  const [q, setQ] = React.useState("");
  const query = useDebounced(q.trim(), 300);
  const [sending, setSending] = React.useState<RefundRow | null>(null);
  const [reference, setReference] = React.useState("");
  const [saving, setSaving] = React.useState(false);

  // Unfiltered ledger for the totals header; the filtered one feeds the table (same request when no filter is set).
  const all = useQuery({ queryKey: ["host", "payments", "", ""], queryFn: () => get<LedgerResponse>("/api/host/payments") });
  const filtered = useQuery({
    queryKey: ["host", "payments", status, query],
    queryFn: () => get<LedgerResponse>(`/api/host/payments${qs({ status, q: query })}`),
    placeholderData: keepPreviousData,
  });

  const payments = (filtered.data?.payments ?? []).filter((p) => method === "all" || p.method === method);
  const refunds = all.data?.refunds ?? [];
  const sum = (rows: PaymentRow[]) => rows.reduce((s, p) => s + p.amount, 0);
  const ledger = all.data?.payments ?? [];
  const collected = sum(ledger.filter((p) => p.status === "success"));
  const pending = ledger.filter((p) => p.status === "pending");
  const failed = ledger.filter((p) => p.status === "failed");
  const refundsDue = refunds.filter((r) => r.status === "pending");

  const markSent = async () => {
    if (!sending) return;
    setSaving(true);
    try {
      await post(`/api/host/refunds/${sending.id}/sent`, { reference: reference.trim() });
      toast.success(`Refund of ${kes(sending.amount)} marked as sent`, { description: `Logged on ${sending.ref}'s timeline.` });
      setSending(null);
      setReference("");
      invalidate();
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <PageHeader title="Payments" subtitle={`Every ${mpesa ? "M-Pesa and card" : "card"} payment, matched to its booking automatically — plus refunds waiting to go out.`} />

      {all.error ? (
        <ErrorBlock error={all.error} retry={all.refetch} />
      ) : (
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {all.isLoading ? (
              Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-32 rounded-2xl" />)
            ) : (
              <>
                <KpiCard label="Collected" value={kes(collected)} hint={`${ledger.filter((p) => p.status === "success").length} successful payments`} icon={<ShieldCheck className="size-4" />} tone="ocean" />
                <KpiCard label="Pending" value={kes(sum(pending))} hint={pending.length ? `${plural(pending.length, "prompt")} awaiting the guest's PIN` : "Nothing waiting"} icon={<Clock className="size-4" />} />
                <KpiCard label="Failed" value={failed.length} hint={failed.length ? `${kes(sum(failed))} not collected` : "No failed payments"} icon={<CircleAlert className="size-4" />} />
                <KpiCard
                  label="Refunds to send"
                  value={kes(refundsDue.reduce((s, r) => s + r.amount, 0))}
                  hint={refundsDue.length ? plural(refundsDue.length, "refund") + " pending" : "All refunds sent"}
                  icon={<Undo2 className="size-4" />}
                  tone={refundsDue.length ? "brand" : "neutral"}
                />
              </>
            )}
          </div>

          <Callout tone="trust" title={`Only the ${mpesa ? "payment provider" : "card processor"}'s confirmation counts as proof of payment`}>
            A booking is confirmed when {mpesa ? "Safaricom (via Africa's Talking or Daraja) or the card processor" : "the card processor (Stripe)"} confirms the
            payment — never because of an SMS screenshot, which is easy to fake. Each reference below came straight from that confirmation.
          </Callout>

          <UnmatchedCard rows={all.data?.unmatched ?? []} />
          <OutstandingCard rows={all.data?.outstanding ?? []} />

          <TableCard
            title="Payments"
            description={filtered.data ? `${plural(payments.length, "payment")}${filtered.data.payments.length >= 300 ? " (latest 300)" : ""}` : undefined}
            action={
              <div className="flex flex-wrap items-center gap-2">
                <LedgerExport />
                <div className="relative w-full sm:w-64">
                  <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-3" />
                  <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={mpesa ? "Ref, phone or M-Pesa receipt" : "Ref, phone or payment reference"} aria-label="Search payments" className="h-9 pr-8 pl-9 text-sm" />
                  {q && (
                    <button type="button" aria-label="Clear search" onClick={() => setQ("")} className="absolute inset-y-0 right-1.5 my-auto grid size-6 place-items-center rounded-full text-ink-2 hover:bg-surface">
                      <X className="size-3.5" />
                    </button>
                  )}
                </div>
              </div>
            }
          >
            <div className="flex flex-wrap items-center gap-3 border-b border-line-soft px-5 py-3">
              <Segmented<StatusFilter>
                label="Payment status"
                size="sm"
                value={status}
                onChange={setStatus}
                options={[
                  { value: "", label: "All" },
                  { value: "success", label: "Paid" },
                  { value: "pending", label: "Pending" },
                  { value: "failed", label: "Failed" },
                  { value: "expired", label: "Expired" },
                ]}
              />
              <Segmented<MethodFilter>
                label="Payment method"
                size="sm"
                value={method}
                onChange={setMethod}
                options={[
                  { value: "all", label: "All methods" },
                  { value: "mpesa", label: "M-Pesa" },
                  { value: "card", label: "Card" },
                  { value: "cash", label: "Cash" },
                ]}
              />
            </div>
            {filtered.isLoading ? (
              <div className="space-y-3 p-5">
                {Array.from({ length: 6 }).map((_, i) => (
                  <Skeleton key={i} className="h-10" />
                ))}
              </div>
            ) : (
              <div className={cn("transition-opacity", filtered.isFetching && "opacity-70")}>
                <Table
                  head={["Date", "Booking", "Guest", "Home", "Method", "For", "Amount", "Status", "Receipt / reference"]}
                  empty={query ? `No payments match “${query}”.` : "No payments with this filter."}
                  className="[&_table]:min-w-[1040px]"
                >
                  {payments.map((p) => (
                    <Tr key={p.id}>
                      <Td className="whitespace-nowrap text-ink-2">{fmtDateTime(p.completed_at ?? p.created_at)}</Td>
                      <Td>
                        <Link href={reservationHref(p.ref)} className="font-mono text-[13px] font-semibold hover:underline">
                          {p.ref}
                        </Link>
                      </Td>
                      <Td className="max-w-40 truncate font-medium">{p.guest}</Td>
                      <Td className="max-w-44 truncate text-ink-2">{p.unit}</Td>
                      <Td>
                        <MethodChip method={p.method} label={p.method_label} />
                      </Td>
                      <Td className="whitespace-nowrap text-ink-2">{PURPOSE_LABEL[p.purpose] ?? humanize(p.purpose)}</Td>
                      <Td className="text-right font-semibold whitespace-nowrap tabular-nums">{kes(p.amount)}</Td>
                      <Td>
                        <StatusBadge status={p.status} label={STATUS_LABEL[p.status] ?? humanize(p.status)} />
                      </Td>
                      <Td>
                        {p.reference ? (
                          <span className="font-mono text-[12.5px]">{p.reference}</span>
                        ) : p.failure_reason ? (
                          <span className="text-[13px] text-danger">{p.failure_reason}</span>
                        ) : (
                          <span className="text-ink-3">—</span>
                        )}
                        {p.reference && p.failure_reason && <span className="block text-[12px] text-danger">{p.failure_reason}</span>}
                        {p.provider === "simulate" && (
                          <Tooltip content="Demo mode: payment simulated, no real money moved">
                            <span className="ml-1.5 rounded bg-surface px-1 text-[10.5px] font-bold text-ink-3 uppercase">sim</span>
                          </Tooltip>
                        )}
                      </Td>
                    </Tr>
                  ))}
                </Table>
              </div>
            )}
          </TableCard>

          <TableCard title="Refunds" description="Cancellations and late payments that need money sent back. Mark each one once it has gone out.">
            {all.isLoading ? (
              <div className="p-5">
                <Skeleton className="h-24" />
              </div>
            ) : (
              <Table head={["Date", "Booking", "Guest", "Amount", "Method", "Reason", "Status", "Reference", ""]} empty="No refunds — nice." className="[&_table]:min-w-[980px]">
                {refunds.map((r) => (
                  <Tr key={r.id} className={cn(r.status === "pending" && "bg-brand-50/40")}>
                    <Td className="whitespace-nowrap text-ink-2">{fmtDateTime(r.created_at)}</Td>
                    <Td>
                      <Link href={reservationHref(r.ref)} className="font-mono text-[13px] font-semibold hover:underline">
                        {r.ref}
                      </Link>
                    </Td>
                    <Td>
                      <span className="block font-medium">{r.guest}</span>
                      <span className="font-mono text-[12px] text-ink-2">{r.phone}</span>
                    </Td>
                    <Td className="font-semibold whitespace-nowrap tabular-nums">{kes(r.amount)}</Td>
                    <Td className="whitespace-nowrap text-ink-2">{r.method}</Td>
                    <Td className="max-w-52 text-ink-2">{r.reason || "—"}</Td>
                    <Td>
                      <StatusBadge status={r.status === "pending" ? "pending" : r.status} label={REFUND_STATUS[r.status] ?? humanize(r.status)} />
                    </Td>
                    <Td className="font-mono text-[12.5px]">{r.reference || <span className="font-sans text-ink-3">—</span>}</Td>
                    <Td className="text-right">
                      {r.status === "pending" && (
                        <Button
                          variant="dark"
                          size="sm"
                          onClick={() => {
                            setReference("");
                            setSending(r);
                          }}
                        >
                          Mark as sent
                        </Button>
                      )}
                    </Td>
                  </Tr>
                ))}
              </Table>
            )}
          </TableCard>
        </div>
      )}

      <ConfirmDialog
        open={!!sending}
        onOpenChange={(v) => !v && setSending(null)}
        title="Mark refund as sent"
        confirmLabel="Mark as sent"
        loading={saving}
        onConfirm={markSent}
      >
        {sending && (
          <>
            <p>
              Send <b className="text-ink">{kes(sending.amount)}</b> to {sending.guest} ({sending.phone}) by {sending.method}, then record the transaction reference
              here. The booking&apos;s refunded total is updated and the refund is logged on its timeline.
            </p>
            {/card/i.test(sending.method) ? (
              <Field label="Refund reference" hint="The refund ID from your card processor, e.g. Stripe's re_… (Payments › the payment › Refunds).">
                <Input value={reference} onChange={(e) => setReference(e.target.value.trim())} placeholder="re_3Nx…" className="font-mono" autoFocus />
              </Field>
            ) : (
              <Field label="M-Pesa / bank reference" hint="The M-Pesa B2C receipt (e.g. QK71XYZ9AB) or bank reference. Leave blank for cash.">
                <Input value={reference} onChange={(e) => setReference(e.target.value.toUpperCase())} placeholder="QK71XYZ9AB" className="font-mono" autoFocus />
              </Field>
            )}
          </>
        )}
      </ConfirmDialog>
    </>
  );
}
