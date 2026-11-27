"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import * as React from "react";

import { hydrationSafe, useConfig, useHydrated, usePayOptions } from "@/components/providers";
import { MobileTabs, SiteHeader } from "@/components/site/header";
import { Photo } from "@/components/site/listing-card";
import { useMoney } from "@/components/site/locale";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Icon3D, type Icon3DName } from "@/components/ui/icon3d";
import { get } from "@/lib/api";
import { kes } from "@/lib/format";
import type { Addon } from "@/lib/types";
import { cn } from "@/lib/utils";

// Text keywords the SMS concierge understands for each extra (see backend apps/comms/smsbot.py).
const SMS_KEYWORD: Record<string, string> = {
  breakfast: "BREAKFAST", airport_pickup: "PICKUP", sgr_pickup: "PICKUP", early_checkin: "EARLY", late_checkout: "LATE", mid_stay_clean: "CLEAN",
};

const GROUPS: { category: string; title: string; subtitle: string }[] = [
  { category: "breakfast", title: "Breakfast, made fresh", subtitle: "Cooked each morning by Mama Zawadi and served on your veranda" },
  { category: "transport", title: "Getting here", subtitle: "Met at the airport or the SGR with your name on a sign" },
  { category: "flexibility", title: "Arrive early, leave late", subtitle: "More beach, less waiting around with luggage" },
  { category: "cleaning", title: "Housekeeping", subtitle: "Fresh linen and towels in the middle of longer stays" },
  { category: "comfort", title: "Little comforts", subtitle: "A stocked fridge and kit for the little ones" },
];

export function useAddons() {
  const q = useQuery({ queryKey: ["addons"], queryFn: () => get<Addon[]>("/api/addons"), staleTime: 10 * 60_000 });
  return hydrationSafe(q, useHydrated());
}

export const addonPrice = (a: Addon, money: (n: number) => string = kes) => (a.price ? `${money(a.price)} ${a.pricing_label}` : "Free on request");

export function ExtraCard({ addon: a, onOpen, size = "md" }: { addon: Addon; onOpen: () => void; size?: "md" | "lg" }) {
  const money = useMoney();
  return (
    <button type="button" onClick={onOpen} className="group block w-full text-left outline-none">
      <div className={cn("relative overflow-hidden rounded-card bg-surface", size === "lg" ? "aspect-[4/3]" : "aspect-[20/19]")}>
        <Photo src={a.photo_url} alt={a.name} className="size-full transition-transform duration-500 group-hover:scale-[1.03]" sizes={size === "lg" ? "(min-width: 768px) 45vw, 90vw" : "(min-width: 1280px) 16vw, 45vw"} />
        {a.category === "experience" ? (
          <span className="absolute top-3 left-3 rounded-[14px] bg-white/90 px-2.5 py-1 text-[11px] font-semibold shadow-badge backdrop-blur-sm">Hosted by our team</span>
        ) : a.requires_approval ? (
          <span className="absolute top-3 left-3 rounded-[14px] bg-white/90 px-2.5 py-1 text-[11px] font-semibold shadow-badge backdrop-blur-sm">On request</span>
        ) : null}
      </div>
      {size === "lg" ? (
        <>
          <h3 className="mt-3 text-[17px] font-semibold">{a.name}</h3>
          <p className="mt-0.5 line-clamp-2 text-[15px] text-ink-2">{a.short}</p>
          <p className="mt-1.5 text-[15px]"><span className="font-semibold">{addonPrice(a, money)}</span></p>
        </>
      ) : (
        <>
          <h3 className="mt-2 truncate text-[13px] font-medium">{a.name}</h3>
          <p className="truncate text-xs text-ink-2">{addonPrice(a, money)}</p>
        </>
      )}
    </button>
  );
}

export function ExtraDialog({ addon: a, onClose }: { addon: Addon | null; onClose: () => void }) {
  const { data: config } = useConfig();
  const { methods } = usePayOptions();
  const money = useMoney();
  const sms = config?.channels.sms_number;
  const keyword = a ? SMS_KEYWORD[a.code] : undefined;
  const steps: { icon: Icon3DName; title: string; text: React.ReactNode }[] = [
    { icon: "homes", title: "When you book a home", text: `Pick it on the checkout page — it's added to the same ${methods} payment.` },
    { icon: "key", title: "Already booked?", text: <>Open your trip and add it any time before or during your stay. <Link href="/trips" className="font-medium underline">Your trips</Link></> },
    keyword
      ? { icon: "speech-balloon", title: "By SMS, no data needed", text: <>Text <b className="font-semibold text-ink">{keyword}</b>{sms ? <> to <b className="font-semibold text-ink">{sms}</b></> : ""} and Amina&apos;s concierge does the rest.</> }
      : { icon: "speech-balloon", title: "Or just ask", text: <>Text Amina{sms ? <> on <b className="font-semibold text-ink">{sms}</b></> : ""} in English or Kiswahili and she&apos;ll arrange it.</> },
  ];
  return (
    <Dialog open={!!a} onOpenChange={(o) => !o && onClose()}>
      {a && (
        <DialogContent
          title={a.category === "experience" ? "Experience" : "Service"}
          size="md"
          footer={
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-base font-semibold">{addonPrice(a, money)}</p>
                {a.requires_approval && <p className="text-xs text-ink-2">Confirmed by Amina once she&apos;s checked the calendar</p>}
              </div>
              <Button variant="brand" size="lg" asChild>
                <Link href="/s">Find a home</Link>
              </Button>
            </div>
          }
        >
          <div className="p-6">
            <div className="aspect-[16/9] overflow-hidden rounded-2xl bg-surface">
              <Photo src={a.photo_url} alt={a.name} className="size-full" sizes="600px" priority />
            </div>
            <h2 className="mt-6 text-[26px] leading-tight font-semibold tracking-tight">{a.name}</h2>
            <p className="mt-1 text-ink-2">{a.short}</p>
            {a.description && <p className="mt-4 text-[15px] leading-relaxed">{a.description}</p>}
            {(a.options.styles?.length || a.options.dietary?.length) && (
              <div className="mt-5 flex flex-wrap gap-2">
                {[...(a.options.styles ?? []), ...(a.options.dietary ?? [])].map((o) => (
                  <span key={o} className="rounded-full border border-line px-3 py-1 text-[13px] capitalize">{o}</span>
                ))}
              </div>
            )}
            <h3 className="mt-8 text-lg font-semibold">How to add it</h3>
            <ul className="mt-2 divide-y divide-line-soft">
              {steps.map((s) => (
                <li key={s.title} className="flex gap-4 py-4">
                  <Icon3D name={s.icon} size={36} />
                  <div>
                    <p className="font-medium">{s.title}</p>
                    <p className="mt-0.5 text-sm text-ink-2">{s.text}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </DialogContent>
      )}
    </Dialog>
  );
}

export function ExtrasView({ kind }: { kind: "experiences" | "services" }) {
  const { data: addons, isLoading } = useAddons();
  const [open, setOpen] = React.useState<Addon | null>(null);
  const experiences = (addons ?? []).filter((a) => a.category === "experience");
  const services = (addons ?? []).filter((a) => a.category !== "experience");
  return (
    <>
      <SiteHeader mode="home" tab={kind} mobileSearch />
      <MobileTabs active={kind} />
      <main className="container-site pb-16">
        {kind === "experiences" ? (
          <>
            <Intro title="Experiences on the coast" text="Hosted by Amina's own team and added to any stay — sail Tudor Creek at sunset or cook a Swahili feast with Mama Zawadi." />
            <div className="mt-6 grid gap-x-6 gap-y-10 sm:grid-cols-2 xl:grid-cols-3">
              {isLoading
                ? Array.from({ length: 2 }).map((_, i) => <div key={i} className="aspect-[4/3] animate-pulse rounded-card bg-line-soft" />)
                : experiences.map((a) => <ExtraCard key={a.code} addon={a} size="lg" onOpen={() => setOpen(a)} />)}
            </div>
            <HowItWorks />
          </>
        ) : (
          <>
            <Intro title="Services for your stay" text="Everything is arranged by the people who look after your home — booked with your stay, from your trip page, or with a one-word SMS." />
            {GROUPS.map((g) => {
              const items = services.filter((a) => a.category === g.category);
              if (!items.length) return null;
              return (
                <section key={g.category} className="pt-10">
                  <h2 className="text-xl font-semibold tracking-[-0.18px]">{g.title}</h2>
                  <p className="mt-0.5 text-sm text-ink-2">{g.subtitle}</p>
                  <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-6">
                    {items.map((a) => <ExtraCard key={a.code} addon={a} onOpen={() => setOpen(a)} />)}
                  </div>
                </section>
              );
            })}
            <HowItWorks />
          </>
        )}
      </main>
      <ExtraDialog addon={open} onClose={() => setOpen(null)} />
    </>
  );
}

export function Intro({ title, text }: { title: string; text: string }) {
  return (
    <div className="max-w-2xl pt-8 md:pt-10">
      <h1 className="text-[26px] leading-tight font-semibold tracking-tight md:text-[32px]">{title}</h1>
      <p className="mt-2 text-base text-ink-2">{text}</p>
    </div>
  );
}

function HowItWorks() {
  const { methods } = usePayOptions();
  const steps: { icon: Icon3DName; title: string; text: string }[] = [
    { icon: "homes", title: "Book a home", text: "On the web, by USSD, SMS or a phone call — your number is your account." },
    { icon: "sparkles", title: "Add what you like", text: "At checkout, from your trip page, or by replying to our SMS. Some extras need Amina's OK first." },
    { icon: "money-bag", title: "One simple bill", text: `Extras join your stay total. Pay by ${methods} — no surprises at the door.` },
  ];
  return (
    <section className="mt-16 rounded-3xl bg-surface px-6 py-10 md:px-12">
      <h2 className="text-[22px] font-semibold tracking-tight">How extras work</h2>
      <div className="mt-6 grid gap-8 md:grid-cols-3">
        {steps.map((s) => (
          <div key={s.title}>
            <Icon3D name={s.icon} size={48} />
            <h3 className="mt-3 font-semibold">{s.title}</h3>
            <p className="mt-1 text-[15px] leading-relaxed text-ink-2">{s.text}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
