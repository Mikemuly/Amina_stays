"use client";

import { Download, Landmark, Smartphone } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { StatusBadge, Table, Td, Tr } from "@/components/host/common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { post } from "@/lib/api";
import { fmtDate, fmtDateTime, kes, plural, relDay } from "@/lib/format";

import { useInvalidateHost } from "./queries";
import type { OutstandingRow, UnmatchedRow } from "./types";
import { TableCard, errorMessage, reservationHref } from "./ui";

const thisMonth = () => new Date().toISOString().slice(0, 7);

/** Monthly ledger export for the accountant (date, ref, guest, method, receipt, gross, refunded, net). */
export function LedgerExport() {
  const [month, setMonth] = React.useState(thisMonth);
  return (
    <div className="flex items-center gap-2">
      <Input type="month" value={month} max={thisMonth()} onChange={(e) => setMonth(e.target.value)} aria-label="Export month" className="h-9 w-40 text-sm" />
      <Button asChild size="sm" variant="soft">
        <a href={`/api/host/payments?export=csv&month=${month}`} download>
          <Download className="size-4" /> CSV
        </a>
      </Button>
    </div>
  );
}

/** Confirmed stays with money still owed — overdue first — with a one-tap request (an M-Pesa prompt, or a card link by SMS). */
export function OutstandingCard({ rows }: { rows: OutstandingRow[] }) {
  const invalidate = useInvalidateHost();
  const [busy, setBusy] = React.useState<string | null>(null);
  if (!rows.length) return null;
  async function request(r: OutstandingRow) {
    setBusy(r.ref);
    try {
      await post(`/api/host/reservations/${r.ref}/request-payment`, { amount: r.balance_due });
      toast.success(`Payment request for ${kes(r.balance_due)} sent to ${r.guest}`);
      invalidate();
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setBusy(null);
    }
  }
  const overdue = rows.filter((r) => r.overdue).length;
  return (
    <TableCard title="Balances due" description={`${plural(rows.length, "stay")} · ${kes(rows.reduce((s, r) => s + r.balance_due, 0))}${overdue ? ` · ${overdue} overdue` : ""}`}>
      <Table head={["Booking", "Guest", "Home", "Check-in", "Due", "Balance", ""]} className="[&_table]:min-w-[820px]">
        {rows.map((r) => (
          <Tr key={r.ref}>
            <Td><Link href={reservationHref(r.ref)} className="font-mono text-[13px] font-semibold hover:underline">{r.ref}</Link></Td>
            <Td className="max-w-40 truncate font-medium">{r.guest}</Td>
            <Td className="max-w-44 truncate text-ink-2">{r.unit}</Td>
            <Td className="whitespace-nowrap text-ink-2">{fmtDate(r.check_in, "EEE d MMM")}</Td>
            <Td className="whitespace-nowrap">{r.overdue ? <StatusBadge status="failed" label="Overdue" /> : <span className="text-ink-2">{r.due_on ? relDay(r.due_on) : "—"}</span>}</Td>
            <Td className="text-right font-semibold whitespace-nowrap tabular-nums">{kes(r.balance_due)}</Td>
            <Td className="text-right">
              <Button size="sm" variant="soft" loading={busy === r.ref} disabled={!!busy} onClick={() => request(r)}>
                <Smartphone className="size-4" /> Request
              </Button>
            </Td>
          </Tr>
        ))}
      </Table>
    </TableCard>
  );
}

/** Paybill payments whose account number didn't match a booking ref — matched by hand. */
export function UnmatchedCard({ rows }: { rows: UnmatchedRow[] }) {
  const invalidate = useInvalidateHost();
  const [refs, setRefs] = React.useState<Record<number, string>>({});
  const [busy, setBusy] = React.useState<number | null>(null);
  if (!rows.length) return null;
  async function match(r: UnmatchedRow) {
    setBusy(r.id);
    try {
      await post(`/api/host/payments/unmatched/${r.id}/match`, { ref: (refs[r.id] ?? "").trim().toUpperCase() });
      toast.success(`${kes(r.amount)} (${r.trans_id}) matched to ${(refs[r.id] ?? "").toUpperCase()}`);
      invalidate();
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setBusy(null);
    }
  }
  return (
    <TableCard title="Unmatched Paybill payments" description="The account number didn't match a booking — type the right ref to apply it.">
      <Table head={["Received", "M-Pesa code", "From", "Account typed", "Amount", "Apply to booking"]} className="[&_table]:min-w-[860px]">
        {rows.map((r) => (
          <Tr key={r.id}>
            <Td className="whitespace-nowrap text-ink-2">{fmtDateTime(r.received_at)}</Td>
            <Td><span className="inline-flex items-center gap-1.5 font-mono text-[12.5px]"><Landmark className="size-3.5 text-ink-3" />{r.trans_id}</span></Td>
            <Td className="whitespace-nowrap text-ink-2">{r.phone}</Td>
            <Td className="font-mono text-[12.5px] text-ink-2">{r.bill_ref || "—"}</Td>
            <Td className="text-right font-semibold whitespace-nowrap tabular-nums">{kes(r.amount)}</Td>
            <Td>
              <div className="flex items-center gap-2">
                <Input value={refs[r.id] ?? ""} onChange={(e) => setRefs({ ...refs, [r.id]: e.target.value })} placeholder="AMS-1234" aria-label={`Booking ref for ${r.trans_id}`} className="h-9 w-32 font-mono text-sm" />
                <Button size="sm" variant="dark" loading={busy === r.id} disabled={!!busy || !(refs[r.id] ?? "").trim()} onClick={() => match(r)}>Match</Button>
              </div>
            </Td>
          </Tr>
        ))}
      </Table>
    </TableCard>
  );
}
