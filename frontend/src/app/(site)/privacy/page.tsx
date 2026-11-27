import type { Metadata } from "next";
import Link from "next/link";

import { SiteHeader } from "@/components/site/header";

export const metadata: Metadata = { title: "Privacy & your data" };

const SECTIONS: { title: string; body: React.ReactNode }[] = [
  {
    title: "Who we are",
    body: (
      <p>
        Amina Stays is a short-stay accommodation business in Mombasa, Kenya, licensed by the Tourism Regulatory Authority. We are the data controller for the
        information described here and are registered with the Office of the Data Protection Commissioner (ODPC) as required by the Data Protection Act, 2019.
        Contact us at <b>karibu@aminastays.co.ke</b> or message Amina from your account.
      </p>
    ),
  },
  {
    title: "What we collect, and why",
    body: (
      <ul>
        <li><b>Your phone number</b> — it is your account on the web, USSD, SMS and voice, and how we send confirmations, directions and your door code (contract).</li>
        <li><b>Name, nationality and ID or passport number</b> — Kenyan tourism law requires every host to keep a guest register (Tourism Enterprises Regulations, 2025). ID numbers are encrypted; staff only ever see the last four digits (legal obligation).</li>
        <li><b>Booking and payment records</b> — dates, amounts and payment references, kept for tax and accounting (legal obligation). We never see or store your card number or PIN.</li>
        <li><b>Messages</b> — your SMS, chat and USSD requests so Amina can help you and keep a record of what was agreed (contract / legitimate interest).</li>
        <li><b>Arrival details and car plate</b> — shared with the gate guard on your arrival day only, as residential estates in Mombasa require a visitor log (legitimate interest).</li>
        <li><b>A SIM-swap check</b> — on arrival morning we check, through our telecoms provider, whether your SIM was recently swapped before sending a door code, to stop fraudsters taking over a booking (legitimate interest).</li>
        <li><b>Offers by SMS</b> — only if you opt in. Never after 6pm; reply STOP at any time (consent).</li>
      </ul>
    ),
  },
  {
    title: "Who we share it with",
    body: (
      <ul>
        <li>Africa&apos;s Talking (SMS, USSD, voice and airtime) and our payment processors — to deliver messages and take payments.</li>
        <li>Amina&apos;s on-site team (cleaner, caretaker, cook, security) — only what they need: e.g. the cook sees breakfast orders, the guard sees the day&apos;s arrivals and plates.</li>
        <li>The authorities, when the law requires it (e.g. the guest register on lawful request).</li>
      </ul>
    ),
  },
  {
    title: "How long we keep it",
    body: (
      <ul>
        <li>Guest-register entries (name, ID, stay dates): <b>5 years</b>, as the tourism regulations require — then ID numbers are erased automatically.</li>
        <li>Payment and tax records: as long as Kenyan tax law requires.</li>
        <li>Everything else (messages, preferences, wishlist): until you ask us to erase it.</li>
      </ul>
    ),
  },
  {
    title: "Your rights",
    body: (
      <>
        <p>Under the Data Protection Act, 2019 you can access, correct, port or erase your data, and object to marketing. From your <Link href="/account">account page</Link> you can:</p>
        <ul>
          <li>Download everything we hold about you (we answer any other access request within 7 days).</li>
          <li>Erase your data (completed within 14 days; the guest register is kept only for its legal period).</li>
          <li>Turn offers on or off — or reply STOP to any SMS.</li>
        </ul>
        <p>If you&apos;re unhappy with how we handle your data you can complain to the Office of the Data Protection Commissioner at <b>odpc.go.ke</b>.</p>
      </>
    ),
  },
  {
    title: "Security & cookies",
    body: (
      <p>
        ID numbers are encrypted at rest, staff access is role-based and logged, and door codes are unique to each stay and expire at checkout. This website uses
        only essential cookies — one to keep you logged in and one to protect forms — and no advertising trackers.
      </p>
    ),
  },
];

export default function PrivacyPage() {
  return (
    <>
      <SiteHeader />
      <main className="container-narrow max-w-[760px] pt-12 pb-24">
        <p className="text-sm font-semibold text-brand-600">Privacy notice · updated November 2026</p>
        <h1 className="mt-2 text-[34px] font-bold tracking-tight">Privacy &amp; your data</h1>
        <p className="mt-4 text-lg text-ink-2">
          The short version: we collect what we need to host you safely and what Kenyan law requires — nothing more — and you&apos;re always in control of the rest.
        </p>
        <div className="mt-12 space-y-12">
          {SECTIONS.map((s) => (
            <section key={s.title}>
              <h2 className="text-[22px] font-bold tracking-tight">{s.title}</h2>
              <div className="mt-3 space-y-3 text-[15px] leading-relaxed text-ink-2 [&_a]:underline [&_b]:text-ink [&_li]:pl-1 [&_ul]:list-disc [&_ul]:space-y-2 [&_ul]:pl-5">{s.body}</div>
            </section>
          ))}
        </div>
      </main>
    </>
  );
}
