"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronDown, FlaskConical, Globe, MessageSquareText, Phone, Search, ShieldCheck, Siren, Smartphone } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { useAuthDialog, useConfig, useMe, usePayOptions } from "@/components/providers";
import { SiteHeader } from "@/components/site/header";
import { SupportPanel } from "@/components/site/support-panel";
import { Button } from "@/components/ui/button";
import { Icon3D, type Icon3DName } from "@/components/ui/icon3d";
import { Skeleton } from "@/components/ui/misc";
import { get } from "@/lib/api";
import type { FaqItem } from "@/lib/types";
import { cn } from "@/lib/utils";

const CATEGORY: Record<string, string> = {
  booking: "Booking & your ID", payment: "Paying", pricing: "Prices", policies: "Policies & cancellations", check_in: "Check-in & checkout",
  breakfast: "Breakfast", wifi: "Wi-Fi", amenities: "In the home", transport: "Getting here", area: "The area", safety: "Safety",
};
const ORDER = ["booking", "payment", "pricing", "policies", "check_in", "breakfast", "wifi", "amenities", "transport", "area", "safety"];

const priceParts = (methods: string): { icon: Icon3DName; title: string; text: string }[] => [
  { icon: "homes", title: "Nightly rate", text: "Set per home and season — weekends and the festive season cost a little more, weekly stays a little less." },
  { icon: "broom", title: "Cleaning fee", text: "One fixed amount per stay, shown before you book. Fresh linen and towels included." },
  { icon: "classical-building", title: "2% tourism levy", text: "Collected for the Tourism Fund as Kenyan law requires, and listed on every receipt." },
  { icon: "money-bag", title: "No booking fee", text: `Book direct and pay by ${methods} — or 30% now and the balance before arrival.` },
];

export function HelpView() {
  const { data: config } = useConfig();
  const { mpesa, methods } = usePayOptions();
  const { data: faqs, isLoading } = useQuery({ queryKey: ["faqs"], queryFn: () => get<FaqItem[]>("/api/faqs") });
  const [q, setQ] = React.useState("");
  const c = config?.channels;
  const needle = q.trim().toLowerCase();
  const shown = (faqs ?? []).filter((f) => !needle || `${f.question} ${f.answer}`.toLowerCase().includes(needle));
  const groups = ORDER.map((k) => ({ key: k, items: shown.filter((f) => f.category === k) })).concat([{ key: "other", items: shown.filter((f) => !ORDER.includes(f.category)) }]).filter((g) => g.items.length);

  return (
    <>
      <SiteHeader />
      <main>
        <section className="bg-gradient-to-b from-sand-50 to-white">
          <div className="container-narrow max-w-[880px] py-14 text-center sm:py-20">
            <h1 className="text-[34px] font-bold tracking-tight sm:text-[44px]">Hi, how can we help?</h1>
            <div className="relative mx-auto mt-8 max-w-xl">
              <Search className="absolute top-1/2 left-5 size-5 -translate-y-1/2 text-ink-2" />
              <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search: breakfast, Wi-Fi, cancellation…" className="h-14 w-full rounded-full border border-line bg-white pr-5 pl-13 text-[15px] shadow-pill outline-none focus:border-ink" />
            </div>
          </div>
        </section>

        <div className="container-narrow max-w-[1080px] space-y-20 pb-24">
          <section id="book-your-way" className="scroll-mt-24">
            <h2 className="text-[26px] font-bold tracking-tight">Book and manage your way</h2>
            <p className="mt-1 text-ink-2">One phone number, one account — whichever way suits you. Everything stays in sync.</p>
            <div className="mt-6 grid gap-4 md:grid-cols-2">
              <Channel icon={<Globe className="size-6" />} title="Website" tag="You're here">
                Photos, live availability and instant booking {mpesa ? "with M-Pesa or card" : "by card"}. Manage trips, breakfast and check-in from <Link className="underline" href="/trips">Trips</Link>.
              </Channel>
              <Channel icon={<Smartphone className="size-6" />} title="USSD — no data, no smartphone" tag={c?.ussd_code || "Dial our code"}>
                Dial {c?.ussd_code ? <b className="text-ink">{c.ussd_code}</b> : "our USSD code"} from any Kenyan line:
                <ol className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
                  {["Book a stay", "Prices & homes", "My booking", "Breakfast", "Report problem", "Talk to Amina", "Check out", "More: guide, alerts, rewards", "EMERGENCY"].map((x, i) => <li key={x}><b className="text-ink">{i + 1}.</b> {x}</li>)}
                </ol>
              </Channel>
              <Channel icon={<MessageSquareText className="size-6" />} title="SMS — “Ask Amina”" tag={c?.sms_number || "Text our number"}>
                Text in English, Kiswahili, Italian, German or French. Try:
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {["PRICES", "BOOK", "BREAKFAST", "WIFI", "ETA 4pm", "ID 12345678", "LATE", "CODE", "EXPLORE", "ALERTS", "COMPLAIN …", "POINTS", "HELP", "STOP"].map((k) => <code key={k} className="rounded-md bg-surface px-2 py-0.5 text-[13px] font-semibold text-ink">{k}</code>)}
                </div>
              </Channel>
              <Channel icon={<Phone className="size-6" />} title="Voice — “Call Amina”" tag={c?.voice_number || "Call our line"}>
                English or Kiswahili menu: <b className="text-ink">1</b> availability &amp; booking · <b className="text-ink">2</b> prices &amp; breakfast · <b className="text-ink">3</b> your booking &amp; directions · <b className="text-ink">4</b> talk to Amina · <b className="text-ink">5</b> a complaint or problem · <b className="text-ink">6</b> things to do nearby · <b className="text-ink">9</b> urgent help.
              </Channel>
            </div>
            {config?.demo && !c?.ussd_code && (
              <div className="mt-4 flex flex-wrap items-center justify-between gap-4 rounded-2xl bg-ocean-50 p-5">
                <p className="flex items-center gap-3 text-[15px] text-ocean-700"><FlaskConical className="size-5 shrink-0" /> Try the SMS, USSD and voice channels right in your browser.</p>
                <Button asChild variant="ocean"><Link href="/demo">Open the Demo Lab</Link></Button>
              </div>
            )}
          </section>

          <section id="prices" className="scroll-mt-24">
            <h2 className="text-[26px] font-bold tracking-tight">Prices include all fees</h2>
            <p className="mt-1 text-ink-2">The total you see on a home is the total you pay — no booking fee is added at checkout.</p>
            <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {priceParts(methods).map((p) => (
                <div key={p.title} className="rounded-2xl border border-line p-5">
                  <Icon3D name={p.icon} size={36} />
                  <p className="mt-4 font-semibold">{p.title}</p>
                  <p className="mt-1 text-sm text-ink-2">{p.text}</p>
                </div>
              ))}
            </div>
          </section>

          <section id="faq" className="scroll-mt-24">
            <h2 className="text-[26px] font-bold tracking-tight">Frequently asked</h2>
            {isLoading ? (
              <div className="mt-6 space-y-3">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-14" />)}</div>
            ) : !groups.length ? (
              <p className="mt-6 text-ink-2">Nothing matches &ldquo;{q}&rdquo;. <Link href="/messages" className="underline">Ask Amina directly</Link> — she usually replies within the hour.</p>
            ) : (
              <div className="mt-6 grid gap-x-12 gap-y-10 lg:grid-cols-2">
                {groups.map((g) => (
                  <div key={g.key} id={g.key === "policies" ? "cancellations" : undefined} className="scroll-mt-24">
                    <h3 className="text-sm font-bold tracking-wide text-ink-2 uppercase">{CATEGORY[g.key] ?? "More"}</h3>
                    <div className="mt-2 divide-y divide-line-soft border-y border-line-soft">
                      {g.items.map((f) => (
                        <details key={f.id} className="group py-4" open={!!needle}>
                          <summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-semibold [&::-webkit-details-marker]:hidden">
                            {f.question}
                            <ChevronDown className="size-5 shrink-0 transition-transform group-open:rotate-180" />
                          </summary>
                          <p className="mt-2 text-[15px] leading-relaxed text-ink-2">{f.answer}</p>
                        </details>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section id="safety" className="scroll-mt-24 grid gap-6 md:grid-cols-2">
            <div className="rounded-3xl bg-danger-50 p-7">
              <h2 className="flex items-center gap-3 text-[22px] font-bold text-danger"><Siren className="size-6" /> In an emergency</h2>
              <ul className="mt-5 space-y-3 text-[15px]">
                <li className="flex justify-between gap-4"><span>Police / ambulance (free)</span><a href="tel:999" className="font-bold">999 · 112</a></li>
                <li className="flex justify-between gap-4"><span>Kenya Red Cross</span><a href="tel:1199" className="font-bold">1199</a></li>
                <li className="flex justify-between gap-4"><span>E-Plus ambulance</span><a href="tel:1514" className="font-bold">1514</a></li>
                <li className="flex justify-between gap-4"><span>Amina&apos;s team, 24/7</span><span className="font-bold">Text HELP</span></li>
              </ul>
              <p className="mt-5 text-sm text-ink-2">Texting HELP (or pressing 9 on USSD or a call) alerts Amina, the caretaker and security at once. We call you back and keep escalating until someone answers.</p>
            </div>
            <div className="rounded-3xl bg-ocean-50 p-7">
              <h2 className="flex items-center gap-3 text-[22px] font-bold text-ocean-700"><ShieldCheck className="size-6" /> Booking safely</h2>
              <ul className="mt-5 list-disc space-y-2.5 pl-5 text-[15px] text-ink-2">
                <li>We only take payment through {mpesa ? "the official M-Pesa prompt or our secure card page" : "our secure card page"} — <b className="text-ink">never</b> to a personal number.</li>
                <li>Your door code is unique to your stay and stops working at checkout.</li>
                <li>Licensed by the Tourism Regulatory Authority{config?.business.tra_licence ? <> — <b className="text-ink">{config.business.tra_licence}</b></> : null}.</li>
                <li>Prices always include cleaning, the 2% tourism levy and taxes. No surprises.</li>
              </ul>
            </div>
          </section>

          <SupportSection />

          <section className="rounded-3xl border border-line-soft p-8 text-center">
            <h2 className="text-[22px] font-bold">Still need help?</h2>
            <p className="mt-1 text-ink-2">Message Amina — instant answers any time, and a personal reply within the hour.</p>
            <Button asChild size="lg" className="mt-6"><Link href="/messages">Message Amina</Link></Button>
          </section>
        </div>
      </main>
    </>
  );
}

/** Complaints, call-backs and questions with a reference, a reply-by time and a rating at the end. */
function SupportSection() {
  const { data: me } = useMe();
  const { requireLogin } = useAuthDialog();
  const { data: config } = useConfig();
  const c = config?.channels;
  return (
    <section id="support" className="scroll-mt-24">
      <h2 className="text-[26px] font-bold tracking-tight">Support requests</h2>
      <p className="mt-1 text-ink-2">
        Something not right, or rather talk it through? Every request gets a reference and a reply-by time, and if nobody answers in time it goes
        straight to {config?.business.host_name ?? "Amina"}&apos;s phone.
      </p>
      <div className="mt-6">
        {me?.authenticated ? (
          <SupportPanel />
        ) : (
          <div className="rounded-2xl border border-line-soft p-6">
            <p className="text-[15px]">
              Log in with your phone number to raise a request and follow it here - or use any phone: text <b className="font-semibold">COMPLAIN</b> and what
              happened, <b className="font-semibold">CALL ME</b> for a call-back or <b className="font-semibold">TICKETS</b> to check on them
              {c?.sms_number ? <> to <b className="font-semibold">{c.sms_number}</b></> : ""}; dial {c?.ussd_code || "our USSD code"} → Talk to Amina; or call
              us and press 5 to leave a complaint.
            </p>
            <Button className="mt-4" variant="dark" onClick={() => requireLogin()}>Log in</Button>
          </div>
        )}
      </div>
    </section>
  );
}

function Channel({ icon, title, tag, children }: { icon: React.ReactNode; title: string; tag: string; children: React.ReactNode }) {
  return (
    <div className={cn("rounded-2xl border border-line-soft p-6")}>
      <div className="flex items-start justify-between gap-3">
        <span className="grid size-12 place-items-center rounded-2xl bg-sand-100">{icon}</span>
        <span className="rounded-full bg-surface px-3 py-1 text-xs font-bold">{tag}</span>
      </div>
      <h3 className="mt-4 text-lg font-bold">{title}</h3>
      <div className="mt-1 text-[15px] text-ink-2">{children}</div>
    </div>
  );
}
