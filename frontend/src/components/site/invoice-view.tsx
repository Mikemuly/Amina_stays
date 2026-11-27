"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Printer } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { Logo } from "@/components/host/shell";
import { useMe, usePayOptions } from "@/components/providers";
import { AuthGate } from "@/components/site/auth-gate";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/misc";
import { get, patch } from "@/lib/api";
import { fmtDate, kes } from "@/lib/format";
import type { Invoice } from "@/lib/types";

const KRA_PIN = /^[AP]\d{9}[A-Z]$/;

export function InvoiceView({ bookingRef }: { bookingRef: string }) {
  return (
    <AuthGate title="Log in to see this invoice" subtitle="Use the phone number the booking was made with.">
      <InvoiceBody bookingRef={bookingRef} />
    </AuthGate>
  );
}

function InvoiceBody({ bookingRef: ref }: { bookingRef: string }) {
  const qc = useQueryClient();
  const asHost = !!useMe().data?.is_host; // Amina opens the same invoice from the reservation page
  const { methods } = usePayOptions();
  const { data: inv, error, isLoading } = useQuery({ queryKey: ["invoice", ref], queryFn: () => get<Invoice>(`/api/bookings/${ref}/invoice`), retry: false });
  const [buyer, setBuyer] = React.useState<{ name: string; pin: string } | null>(null);
  const [saving, setSaving] = React.useState(false);
  const form = buyer ?? { name: inv?.buyer.name ?? "", pin: inv?.buyer.kra_pin ?? "" };
  const pinOk = !form.pin || KRA_PIN.test(form.pin);

  async function saveBuyer() {
    setSaving(true);
    try {
      qc.setQueryData(["invoice", ref], await patch<Invoice>(`/api/bookings/${ref}/invoice`, { buyer_name: form.name.trim(), buyer_kra_pin: form.pin.trim() }));
      setBuyer(null);
      toast.success("Invoice updated");
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="min-h-dvh bg-surface py-8 print:bg-white print:py-0">
      <div className="container-narrow max-w-[820px]">
        <div className="mb-6 flex flex-wrap items-center justify-between gap-3 print:hidden">
          <Link href={asHost ? `/host/reservations/${ref}` : `/trips/${ref}`} className="inline-flex items-center gap-2 text-sm font-semibold text-ink-2 hover:text-ink"><ArrowLeft className="size-4" /> {asHost ? "Back to the reservation" : "Back to the trip"}</Link>
          <Button variant="dark" size="sm" onClick={() => window.print()} disabled={!inv}><Printer className="size-4" /> Print or save as PDF</Button>
        </div>

        {isLoading ? (
          <Skeleton className="h-[900px] rounded-2xl" />
        ) : error || !inv ? (
          <div className="rounded-2xl bg-white p-10 text-center shadow-soft">
            <h1 className="text-xl font-bold">No invoice yet</h1>
            <p className="mt-2 text-ink-2">{(error as Error | null)?.message || "An invoice is issued once the booking is confirmed."}</p>
          </div>
        ) : (
          <>
            <article className="rounded-2xl bg-white p-8 shadow-soft sm:p-12 print:rounded-none print:p-0 print:shadow-none">
              <header className="flex flex-wrap items-start justify-between gap-6 border-b border-line-soft pb-8">
                <div>
                  <span className="flex items-center gap-2 text-lg font-bold"><Logo className="size-8 rounded-lg" /> {inv.seller.name}</span>
                  <p className="mt-3 text-sm whitespace-pre-line text-ink-2">{inv.seller.address}</p>
                  {inv.seller.kra_pin && <p className="mt-1 text-sm">KRA PIN <span className="font-mono">{inv.seller.kra_pin}</span></p>}
                  {inv.seller.tra_licence && <p className="text-sm">TRA licence <span className="font-mono">{inv.seller.tra_licence}</span></p>}
                </div>
                <div className="text-right">
                  <p className="text-2xl font-bold tracking-tight">{inv.seller.vat_registered ? "Tax invoice" : "Invoice"}</p>
                  <p className="mt-2 font-mono text-sm">{inv.number}</p>
                  <p className="text-sm text-ink-2">Issued {fmtDate(inv.issued_at, "d MMMM yyyy")}</p>
                  <p className="text-sm text-ink-2">Booking {ref}</p>
                </div>
              </header>

              <section className="grid gap-6 border-b border-line-soft py-8 sm:grid-cols-2">
                <div>
                  <p className="text-xs font-bold tracking-wide text-ink-2 uppercase">Billed to</p>
                  <p className="mt-2 font-semibold">{inv.buyer.name || "Guest"}</p>
                  <p className="text-sm text-ink-2">{inv.buyer.phone}</p>
                  {inv.buyer.kra_pin && <p className="text-sm">KRA PIN <span className="font-mono">{inv.buyer.kra_pin}</span></p>}
                </div>
                <div className="sm:text-right">
                  <p className="text-xs font-bold tracking-wide text-ink-2 uppercase">Amount due</p>
                  <p className="mt-2 text-3xl font-bold tracking-tight">{kes(inv.balance)}</p>
                  <p className="text-sm text-ink-2">{inv.balance > 0 ? `Pay by ${methods} from your trip page` : "Paid in full — thank you"}</p>
                </div>
              </section>

              {/* phones fold quantity and unit price under the description; wider screens and print get all four columns */}
              <table className="w-full text-[14px] sm:text-[15px] print:text-[15px]">
                <thead>
                  <tr className="border-b border-line-soft text-left text-xs tracking-wide text-ink-2 uppercase">
                    <th className="py-3 font-bold">Description</th>
                    <th className="hidden py-3 pl-4 text-right font-bold sm:table-cell print:table-cell">Qty</th>
                    <th className="hidden py-3 pl-6 text-right font-bold whitespace-nowrap sm:table-cell print:table-cell">Unit price</th>
                    <th className="py-3 pl-4 text-right font-bold sm:pl-6 print:pl-6">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {inv.lines.map((l, i) => (
                    <tr key={`${l.label}-${i}`} className="border-b border-line-soft">
                      <td className="py-3 pr-4">
                        {l.label}
                        <span className="mt-0.5 block text-[13px] text-ink-2 tabular-nums sm:hidden print:hidden">
                          {l.qty} × {kes(l.unit_price)}
                        </span>
                      </td>
                      <td className="hidden py-3 pl-4 text-right tabular-nums sm:table-cell print:table-cell">{l.qty}</td>
                      <td className="hidden py-3 pl-6 text-right tabular-nums whitespace-nowrap sm:table-cell print:table-cell">{kes(l.unit_price)}</td>
                      <td className="py-3 pl-4 text-right tabular-nums whitespace-nowrap sm:pl-6 print:pl-6">{kes(l.amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <dl className="ml-auto mt-6 max-w-xs space-y-2 text-[15px]">
                <div className="flex justify-between"><dt className="text-ink-2">Subtotal</dt><dd className="tabular-nums">{kes(inv.subtotal)}</dd></div>
                {inv.vat > 0 && <div className="flex justify-between"><dt className="text-ink-2">VAT</dt><dd className="tabular-nums">{kes(inv.vat)}</dd></div>}
                {inv.levy > 0 && <div className="flex justify-between"><dt className="text-ink-2">Tourism levy (2%)</dt><dd className="tabular-nums">{kes(inv.levy)}</dd></div>}
                <div className="flex justify-between border-t border-line-soft pt-2 font-bold"><dt>Total</dt><dd className="tabular-nums">{kes(inv.total)}</dd></div>
                <div className="flex justify-between"><dt className="text-ink-2">Paid</dt><dd className="tabular-nums">{kes(inv.paid)}</dd></div>
              </dl>

              {inv.payments.length > 0 && (
                <section className="mt-10">
                  <p className="text-xs font-bold tracking-wide text-ink-2 uppercase">Payments received</p>
                  <ul className="mt-3 space-y-1.5 text-sm">
                    {inv.payments.map((p, i) => (
                      <li key={`${p.reference}-${i}`} className="flex justify-between gap-4">
                        <span>{fmtDate(p.date, "d MMM yyyy")} · {p.method}{p.reference ? <span className="ml-2 font-mono text-ink-2">{p.reference}</span> : null}</span>
                        <span className="tabular-nums">{kes(p.amount)}</span>
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {inv.credit_notes.length > 0 && (
                <section className="mt-8">
                  <p className="text-xs font-bold tracking-wide text-ink-2 uppercase">Credit notes</p>
                  <ul className="mt-3 space-y-1.5 text-sm">
                    {inv.credit_notes.map((c) => (
                      <li key={c.number} className="flex justify-between gap-4">
                        <span><span className="font-mono">{c.number}</span> · {fmtDate(c.date, "d MMM yyyy")}{c.reason ? ` · ${c.reason}` : ""}</span>
                        <span className="tabular-nums text-success">−{kes(c.amount)}</span>
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              <footer className="mt-12 border-t border-line-soft pt-6 text-xs text-ink-2">
                <p>Accommodation in Mombasa, Kenya. Prices in Kenya shillings. The tourism levy is collected for the Tourism Fund.</p>
                <p className="mt-1">
                  eTIMS: {inv.etims.invoice_no ? <>transmitted · KRA invoice <span className="font-mono">{inv.etims.invoice_no}</span></> : `${inv.etims.status.replace(/_/g, " ")} — this invoice is eTIMS-ready and is transmitted to KRA from the host's system.`}
                </p>
              </footer>
            </article>

            <section className="mt-6 rounded-2xl bg-white p-6 shadow-soft print:hidden">
              <p className="font-semibold">{asHost ? "Invoicing a company?" : "Claiming this as a business expense?"}</p>
              <p className="mt-1 text-sm text-ink-2">
                {asHost ? "Add the company's name and KRA PIN to reissue this invoice in its name." : "Add your company name and KRA PIN and we'll reissue the invoice in your company's name."}
              </p>
              <div className="mt-4 grid gap-3 sm:grid-cols-[1fr_200px_auto] sm:items-end">
                <Field label="Name on invoice"><Input value={form.name} onChange={(e) => setBuyer({ ...form, name: e.target.value })} /></Field>
                <Field label="KRA PIN" error={pinOk ? undefined : "Format: A123456789Z"}><Input value={form.pin} onChange={(e) => setBuyer({ ...form, pin: e.target.value.toUpperCase() })} placeholder="P051234567X" className="font-mono" maxLength={11} /></Field>
                <Button onClick={saveBuyer} loading={saving} disabled={!buyer || !pinOk}>Update invoice</Button>
              </div>
            </section>
          </>
        )}
      </div>
    </main>
  );
}
