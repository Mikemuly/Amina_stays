"use client";

import { Globe } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { useConfig, usePayOptions } from "@/components/providers";
import { CURRENCIES, openLocaleDialog, useCurrency } from "@/components/site/locale";
import { cn } from "@/lib/utils";

type Item = { title: string; text: string; href: string };

const inspiration = (mpesa: boolean): Record<string, Item[]> => ({
  Neighbourhoods: [
    { title: "Nyali", text: "Beach suburb", href: "/s?area=nyali" },
    { title: "Diani", text: "White sand & reef", href: "/s?area=diani" },
    { title: "Old Town", text: "Swahili heritage", href: "/s?area=old-town" },
    { title: "Bamburi", text: "Family beaches", href: "/s?area=bamburi" },
    { title: "Mtwapa", text: "Creek-side sunsets", href: "/s?area=mtwapa" },
    { title: "The whole coast", text: "Every home", href: "/s" },
  ],
  "Things to do": [
    { title: "Fort Jesus", text: "Old Town · UNESCO site", href: "/guide#fort-jesus" },
    { title: "Haller Park", text: "Bamburi · giraffes & hippos", href: "/guide#haller-park" },
    { title: "Marine Park", text: "Nyali · snorkelling", href: "/guide#mombasa-marine-national-park" },
    { title: "Kisite & Wasini", text: "South coast · dolphins", href: "/guide#kisite-mpunguti-wasini-island" },
    { title: "Sunset dhow cruise", text: "Tudor Creek", href: "/experiences" },
    { title: "Swahili cooking", text: "With Mama Zawadi", href: "/experiences" },
  ],
  "Getting here": [
    { title: "Moi International Airport", text: "Pickup from KES 2,500", href: "/services" },
    { title: "SGR Miritini terminus", text: "Nairobi in about 5 hours", href: "/services" },
    { title: "Likoni ferry", text: "The way to Diani by road", href: "/help" },
    { title: "Ukunda airstrip", text: "10 minutes to Diani", href: "/s?area=diani" },
    // Drivers take M-Pesa even when this site doesn't; the text then names the driver so it isn't read as a way to pay us.
    { title: "Tuk-tuks & taxis", text: mpesa ? "Pay by M-Pesa" : "Cash or M-Pesa to the driver", href: "/help" },
    { title: "Book without data", text: "USSD, SMS or a call", href: "/help#book-your-way" },
  ],
  "Good to know": [
    { title: "Prices in KES", text: "Every fee included", href: "/help#prices" },
    mpesa ? { title: "Pay by M-Pesa", text: "Or card, or 30% now", href: "/help" } : { title: "Pay by card", text: "Or 30% now", href: "/help" },
    { title: "Tourism levy", text: "2%, shown up front", href: "/help#prices" },
    { title: "Guest registration", text: "Required by Kenyan law", href: "/privacy" },
    { title: "24/7 HELP line", text: "Text HELP, Amina calls", href: "/help#safety" },
    { title: "Your data", text: "Kenya Data Protection Act", href: "/privacy" },
  ],
});

export function SiteFooter() {
  const { data: config } = useConfig();
  const { mpesa } = usePayOptions();
  const groups = inspiration(mpesa);
  const code = useCurrency();
  const currency = CURRENCIES.find((x) => x.code === code)!;
  const [tab, setTab] = React.useState("Neighbourhoods");
  const c = config?.channels;
  const columns: { title: string; links: { label: string; href?: string }[] }[] = [
    {
      title: "Support",
      links: [
        { label: "Help Centre", href: "/help" },
        { label: "Safety & emergencies", href: "/help#safety" },
        { label: "Cancellation options", href: "/help#cancellations" },
        { label: "Message Amina", href: "/messages" },
        { label: "Complaints & call-backs", href: "/help#support" },
        { label: "Emergencies: 999 or 112 (free)" },
      ],
    },
    {
      title: "Book your way",
      links: [
        { label: "Website — you're here" },
        { label: c?.ussd_code ? `USSD: ${c.ussd_code} (no data)` : "USSD — no data needed", href: "/help#book-your-way" },
        { label: c?.sms_number ? `SMS “Ask Amina”: ${c.sms_number}` : "SMS “Ask Amina”", href: "/help#book-your-way" },
        { label: c?.voice_number ? `Voice “Call Amina”: ${c.voice_number}` : "Voice “Call Amina”", href: "/help#book-your-way" },
      ],
    },
    {
      title: "Amina Stays",
      links: [
        { label: "Experiences", href: "/experiences" },
        { label: "Services", href: "/services" },
        { label: "Local guide", href: "/guide" },
        { label: "Rewards: airtime & data", href: "/account#rewards" },
        { label: "Privacy & your data", href: "/privacy" },
        { label: "Host console", href: "/host" },
        { label: config?.business.tra_licence ? `TRA licence ${config.business.tra_licence}` : "Licensed by the Tourism Regulatory Authority" },
      ],
    },
  ];
  return (
    <footer className="mt-16 border-t border-line-soft bg-surface pb-20 md:pb-0 print:hidden">
      <div className="container-site pt-12">
        <h2 className="text-[22px] font-semibold tracking-tight">Inspiration for future getaways</h2>
        <div className="no-scrollbar mt-3 flex gap-6 overflow-x-auto border-b border-line" role="tablist">
          {Object.keys(groups).map((t) => (
            <button
              key={t}
              type="button"
              role="tab"
              aria-selected={tab === t}
              onClick={() => setTab(t)}
              className={cn("-mb-px shrink-0 border-b-2 py-3 text-sm font-medium transition-colors", tab === t ? "border-ink text-ink" : "border-transparent text-ink-2 hover:text-ink")}
            >
              {t}
            </button>
          ))}
        </div>
        <ul className="grid grid-cols-2 gap-x-6 gap-y-6 py-8 sm:grid-cols-3 lg:grid-cols-6">
          {groups[tab].map((i) => (
            <li key={i.title}>
              <Link href={i.href} className="group block text-sm">
                <span className="block font-medium group-hover:underline">{i.title}</span>
                <span className="block text-ink-2">{i.text}</span>
              </Link>
            </li>
          ))}
        </ul>
      </div>
      <div className="container-site">
        <div className="grid gap-8 border-t border-line py-12 md:grid-cols-3">
          {columns.map((col) => (
            <div key={col.title}>
              <h3 className="text-sm font-semibold">{col.title}</h3>
              <ul className="mt-3 space-y-3 text-sm">
                {col.links.map((l) => (
                  <li key={l.label}>
                    {l.href ? (
                      <Link href={l.href} className="hover:underline">{l.label}</Link>
                    ) : (
                      <span className="text-ink-2">{l.label}</span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>
      <div className="container-site">
        <div className="flex flex-col-reverse gap-4 border-t border-line py-6 text-sm md:flex-row md:items-center md:justify-between">
          <p className="text-ink">
            © 2026 Amina Stays · Mombasa, Kenya · <Link href="/privacy" className="hover:underline">Privacy</Link> · <Link href="/help" className="hover:underline">Help</Link>
          </p>
          <div className="flex items-center gap-5 font-medium">
            <button type="button" onClick={() => openLocaleDialog("language")} className="flex items-center gap-2 hover:underline"><Globe className="size-4" /> English (KE)</button>
            <button type="button" onClick={() => openLocaleDialog("currency")} className="hover:underline">{currency.symbol} {currency.code}</button>
            <span className="text-ink-2">Built on Africa&apos;s Talking</span>
          </div>
        </div>
      </div>
    </footer>
  );
}
