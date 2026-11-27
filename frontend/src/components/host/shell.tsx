"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarDays, ChefHat, ClipboardCheck, ClipboardList, FlaskConical, Gift, House, LifeBuoy, LogOut, MapPinned, Megaphone, Menu as MenuIcon, MessageSquare,
  MessageSquareText, Phone, Plane, Radio, Settings, ShieldCheck, Siren, Star, Sun, TrendingUp, Users, Wallet, type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import * as React from "react";

import { useConfig, useLogout, useMe, usePayOptions } from "@/components/providers";
import { BrandLink, BrandMark } from "@/components/site/brand";
import { PhoneLogin } from "@/components/site/phone-login";
import { Button } from "@/components/ui/button";
import { Icon3D, type Icon3DName } from "@/components/ui/icon3d";
import { Avatar, Spinner } from "@/components/ui/misc";
import { Dropdown, DropdownContent, DropdownItem, DropdownSeparator, DropdownTrigger } from "@/components/ui/overlays";
import { get, post } from "@/lib/api";
import { ago } from "@/lib/format";
import { cn } from "@/lib/utils";

type AlertRow = { id: number; kind: string; severity: string; status: string; summary: string; phone: string; created_at: string; booking: string | null };

export function HostShell({ children }: { children: React.ReactNode }) {
  const { data: me, isLoading } = useMe();
  if (isLoading) {
    return (
      <div className="grid min-h-dvh place-items-center">
        <Spinner className="size-7" />
      </div>
    );
  }
  if (!me?.authenticated) return <HostLogin />;
  if (!me.is_host) return <NotHost name={me.name} />;
  return <Shell>{children}</Shell>;
}

function HostLogin() {
  return (
    <div className="grid min-h-dvh lg:grid-cols-2">
      <div className="flex items-center justify-center p-8">
        <div className="w-full max-w-sm">
          <div className="mb-10 flex items-center gap-2">
            <BrandLink />
            <span className="text-sm text-ink-2">· Hosting</span>
          </div>
          <PhoneLogin title="Host console" subtitle="Log in with your registered host phone number." cta="Send code" />
        </div>
      </div>
      <div className="relative hidden overflow-hidden bg-ocean-700 lg:block">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="https://images.unsplash.com/photo-1602002418082-a4443e081dd1?auto=format&fit=crop&w=1400&q=80" alt="" className="absolute inset-0 size-full object-cover opacity-60" />
        <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/70 p-12 text-white">
          <p className="text-3xl font-semibold tracking-tight">Every guest, every channel, one console.</p>
          <p className="mt-3 max-w-md text-white/80">Bookings from the web, USSD, SMS and voice land here — with payments, door codes, breakfast, housekeeping and safety alerts in one place.</p>
        </div>
      </div>
    </div>
  );
}

function NotHost({ name }: { name?: string }) {
  const logout = useLogout();
  return (
    <div className="grid min-h-dvh place-items-center p-8 text-center">
      <div>
        <h1 className="text-2xl font-bold">Hi {name || "there"} — this area is for Amina&apos;s team</h1>
        <p className="mt-2 text-ink-2">Your trips and messages are on the guest site.</p>
        <div className="mt-6 flex justify-center gap-3">
          <Button asChild variant="dark"><Link href="/trips">Go to my trips</Link></Button>
          <Button variant="soft" onClick={logout}>Log out</Button>
        </div>
      </div>
    </div>
  );
}

export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn("grid size-8 place-items-center rounded-lg bg-brand-500 text-white", className)} aria-hidden>
      <svg viewBox="0 0 32 32" className="size-[62%]" fill="none">
        <path d="M7.5 19.5 17.2 3.4c.3-.5 1-.5 1.3 0 3 5 5.4 10 7 15.3.2.5-.2.8-.7.8H7.5Z" fill="currentColor" />
        <path d="M3 25.2c2.2-1.6 4.4-1.6 6.5 0s4.3 1.6 6.5 0 4.3-1.6 6.5 0 4.3 1.6 6.5 0" stroke="currentColor" strokeWidth="2.8" strokeLinecap="round" />
      </svg>
    </span>
  );
}

type Badge = "inbox" | "alerts" | "support";

// Airbnb's hosting mode: four destinations plus Menu, the same on desktop (top bar) and phones (bottom bar).
const TABS: { href: string; label: string; icon: LucideIcon; badge?: Badge }[] = [
  { href: "/host", label: "Today", icon: Sun },
  { href: "/host/calendar", label: "Calendar", icon: CalendarDays },
  { href: "/host/listings", label: "Listings", icon: House },
  { href: "/host/inbox", label: "Messages", icon: MessageSquare, badge: "inbox" },
];

export const HOST_MENU: {
  group: string;
  items: { href: string; label: string; text: string; cardOnlyText?: string; icon: Icon3DName; lucide: LucideIcon; badge?: Badge; demoOnly?: boolean }[];
}[] = [
  {
    group: "Business",
    items: [
      { href: "/host/reservations", label: "Reservations", text: "Every booking from every channel, in one list", icon: "clipboard", lucide: ClipboardList },
      { href: "/host/payments", label: "Earnings & payments", text: "M-Pesa, cards, refunds and balances due", cardOnlyText: "Card payments, refunds and balances due", icon: "money-bag", lucide: Wallet },
      { href: "/host/insights", label: "Insights", text: "Occupancy, nightly rates, channels and demand", icon: "bar-chart", lucide: TrendingUp },
      { href: "/host/reviews", label: "Reviews", text: "Ratings, replies and what guests mention", icon: "star", lucide: Star },
      { href: "/host/guests", label: "Guests", text: "Profiles, stays, preferences and IDs", icon: "guests", lucide: Users },
      { href: "/host/support", label: "Support desk", text: "Complaints, call-backs and requests, with reply-by times", icon: "services", lucide: LifeBuoy, badge: "support" },
      { href: "/host/rewards", label: "Rewards & airtime", text: "Points, referrals, airtime and data top-ups", icon: "trophy", lucide: Gift },
    ],
  },
  {
    group: "Operations",
    items: [
      { href: "/host/tasks", label: "Housekeeping & tasks", text: "Turnovers, inspections and repairs", icon: "broom", lucide: ClipboardCheck },
      { href: "/host/kitchen", label: "Breakfast & kitchen", text: "Who eats what, when — and the shopping list", icon: "cooking", lucide: ChefHat },
      { href: "/host/messaging", label: "Messaging & automations", text: "Templates, the guest timeline, FAQ and broadcasts", icon: "speech-balloon", lucide: MessageSquareText },
      { href: "/host/notices", label: "Service alerts", text: "Outages and maintenance, texted to the guests affected", icon: "megaphone", lucide: Megaphone },
      { href: "/host/guide", label: "Local guide", text: "Places and events guests get by USSD, SMS and voice", icon: "palm-tree", lucide: MapPinned },
    ],
  },
  {
    group: "Compliance & channels",
    items: [
      { href: "/host/safety", label: "Safety & compliance", text: "SOS alerts, guest register and TRA returns", icon: "shield", lucide: ShieldCheck, badge: "alerts" },
      { href: "/host/channels", label: "Africa's Talking", text: "SMS, USSD, voice and airtime — live status", icon: "antenna", lucide: Radio },
    ],
  },
  {
    group: "Account",
    items: [
      { href: "/host/settings", label: "Settings", text: "Business details, team, pricing and extras", icon: "gear", lucide: Settings },
      { href: "/demo", label: "Demo Lab", text: "Simulated phones for USSD, SMS and voice", icon: "test-tube", lucide: FlaskConical, demoOnly: true },
    ],
  },
];

function useBadges(): Record<Badge, number> {
  const { data: inbox } = useQuery({
    queryKey: ["host", "inbox-count"],
    queryFn: () => get<unknown[]>("/api/host/inbox?filter=needs_reply"),
    refetchInterval: 15_000,
  });
  const { data: alerts } = useQuery({
    queryKey: ["host", "alerts", "active"],
    queryFn: () => get<AlertRow[]>("/api/host/alerts?status=active"),
    refetchInterval: 10_000,
  });
  // same query (key and URL) as the support desk's "Open" list, so the two share one cache entry
  const { data: support } = useQuery({
    queryKey: ["host", "support", "tickets", "open", ""],
    queryFn: () => get<{ counts: { overdue: number } }>("/api/host/support/tickets?status=open"),
    refetchInterval: 15_000,
  });
  return { inbox: inbox?.length ?? 0, alerts: alerts?.filter((a) => a.status === "open").length ?? 0, support: support?.counts.overdue ?? 0 };
}

const isActive = (pathname: string, href: string) => (href === "/host" ? pathname === "/host" : pathname.startsWith(href));

function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const badges = useBadges();
  const menuActive = pathname.startsWith("/host/menu") || HOST_MENU.some((g) => g.items.some((i) => isActive(pathname, i.href)));
  // the inbox sizes itself to the screen; this bottom padding is the gap its height leaves above the tab bar (phones)
  // or the window edge (md+), so the page only scrolls when the inbox hits its minimum height
  const fullHeight = pathname.startsWith("/host/inbox");
  return (
    <div className="min-h-dvh bg-white">
      <header className="sticky top-0 z-40 hidden border-b border-line-soft bg-white md:block">
        <div className="mx-auto grid h-20 max-w-[1400px] grid-cols-[1fr_auto_1fr] items-center gap-4 px-6 md:px-10">
          <Link href="/host" aria-label="Today" className="flex items-center gap-1.5 text-brand-500">
            <BrandMark className="size-[34px]" />
          </Link>
          <nav className="flex items-center gap-1" aria-label="Hosting">
            {TABS.map((t) => {
              const on = isActive(pathname, t.href);
              const n = t.badge ? badges[t.badge] : 0;
              return (
                <Link
                  key={t.href}
                  href={t.href}
                  aria-current={on ? "page" : undefined}
                  className={cn("relative flex h-10 items-center rounded-full px-4 text-[15px] font-medium transition-colors hover:bg-chip", on ? "text-ink" : "text-ink-2 hover:text-ink")}
                >
                  {t.label}
                  {n > 0 && <span className="ml-1.5 grid h-[18px] min-w-[18px] place-items-center rounded-full bg-brand-500 px-1 text-[10px] font-semibold text-white">{n}</span>}
                  {on && <span className="absolute inset-x-4 -bottom-[19px] h-0.5 rounded-full bg-ink" />}
                </Link>
              );
            })}
          </nav>
          <div className="flex items-center justify-end gap-2">
            <Link href="/" className="hidden h-10 items-center rounded-full px-4 text-sm font-medium whitespace-nowrap transition-colors hover:bg-chip lg:flex">
              Switch to traveling
            </Link>
            <MenuDropdown badges={badges} active={menuActive} />
          </div>
        </div>
      </header>
      <SosBanner />
      <main className={cn("mx-auto w-full max-w-[1400px] px-5 pt-6 pb-28 sm:px-8 md:px-10 md:pt-10 md:pb-16", fullHeight && "pb-20 md:pb-6")}>{children}</main>
      <BottomBar pathname={pathname} badges={badges} menuActive={menuActive} />
    </div>
  );
}

function MenuDropdown({ badges, active }: { badges: Record<Badge, number>; active: boolean }) {
  const { data: me } = useMe();
  const { data: config } = useConfig();
  const router = useRouter();
  const logout = useLogout();
  return (
    <Dropdown>
      <DropdownTrigger
        className={cn("relative flex h-10 items-center gap-2 rounded-full bg-chip pr-1 pl-3 outline-none transition-colors hover:bg-line-soft data-[state=open]:bg-line-soft", active && "bg-line-soft shadow-[inset_0_0_0_1px_var(--color-line)]")}
        aria-label="Menu"
      >
        <MenuIcon className="size-[18px]" strokeWidth={2.2} />
        <Avatar name={me?.name || me?.phone} size={32} className="bg-ink! text-[13px]!" />
        {badges.alerts > 0 && <span className="absolute -top-0.5 -right-0.5 size-3 rounded-full bg-danger ring-2 ring-white" />}
      </DropdownTrigger>
      <DropdownContent className="max-h-[80dvh] w-[300px] overflow-y-auto rounded-2xl border-0 py-2 shadow-pop">
        <div className="px-5 py-3">
          <p className="truncate text-sm font-semibold">{me?.name || "Host"}</p>
          <p className="truncate text-xs text-ink-2 capitalize">{me?.role} · {me?.phone}</p>
        </div>
        {HOST_MENU.map((g) => (
          <React.Fragment key={g.group}>
            <DropdownSeparator />
            <p className="px-5 pt-1 pb-1 text-[11px] font-semibold tracking-wide text-ink-3 uppercase">{g.group}</p>
            {g.items
              .filter((i) => !i.demoOnly || config?.demo)
              .map((i) => (
                <DropdownItem key={i.href} onSelect={() => router.push(i.href)} className="gap-3 px-5 py-2.5">
                  <i.lucide className="size-[18px]" />
                  <span className="flex-1">{i.label}</span>
                  {i.badge && badges[i.badge] > 0 && <span className="grid h-5 min-w-5 place-items-center rounded-full bg-danger px-1.5 text-[11px] font-semibold text-white">{badges[i.badge]}</span>}
                </DropdownItem>
              ))}
          </React.Fragment>
        ))}
        <DropdownSeparator />
        <DropdownItem onSelect={() => router.push("/")} className="gap-3 px-5 py-2.5 font-medium"><Plane className="size-[18px]" /> Switch to traveling</DropdownItem>
        <DropdownItem onSelect={logout} className="gap-3 px-5 py-2.5"><LogOut className="size-[18px]" /> Log out</DropdownItem>
      </DropdownContent>
    </Dropdown>
  );
}

function BottomBar({ pathname, badges, menuActive }: { pathname: string; badges: Record<Badge, number>; menuActive: boolean }) {
  const items = [
    ...TABS.slice(0, 2),
    TABS[2],
    TABS[3],
    { href: "/host/menu", label: "Menu", icon: MenuIcon, badge: "alerts" as Badge },
  ];
  return (
    <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-line-soft bg-white pb-[env(safe-area-inset-bottom)] md:hidden" aria-label="Hosting">
      <div className="mx-auto flex max-w-md justify-around">
        {items.map((t) => {
          const on = t.href === "/host/menu" ? menuActive : isActive(pathname, t.href);
          const n = t.badge ? badges[t.badge] : 0;
          return (
            <Link key={t.href} href={t.href} className={cn("relative flex min-w-16 flex-col items-center gap-1 pt-2.5 pb-2 text-[10px] font-medium", on ? "text-ink" : "text-ink-2")}>
              <t.icon className={cn("size-6", on ? "text-brand-500" : "text-ink-2")} strokeWidth={on ? 2.2 : 1.6} />
              {t.label}
              {n > 0 && <span className="absolute top-1.5 left-[calc(50%+6px)] grid h-4 min-w-4 place-items-center rounded-full bg-brand-500 px-1 text-[9px] font-semibold text-white">{n}</span>}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}

/** The Menu destination (a full page on phones, also reachable on desktop): grouped cards, like Airbnb's account hub. */
export function HostMenuPage() {
  const { data: me } = useMe();
  const { data: config } = useConfig();
  const { mpesa } = usePayOptions();
  const badges = useBadges();
  const logout = useLogout();
  return (
    <div className="mx-auto max-w-[1080px]">
      <h1 className="text-[32px] leading-tight font-semibold tracking-tight">Menu</h1>
      <div className="mt-6 flex items-center gap-4 rounded-2xl p-5 shadow-[0_6px_16px_rgb(0_0_0/0.12)]">
        <Avatar name={me?.name || me?.phone} size={56} className="bg-ink! text-xl!" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-lg font-semibold">{me?.name || "Host"}</p>
          <p className="truncate text-sm text-ink-2 capitalize">{me?.role} · {me?.phone}</p>
        </div>
        <Button asChild variant="soft" className="hidden sm:inline-flex"><Link href="/">Switch to traveling</Link></Button>
      </div>
      {HOST_MENU.map((g) => (
        <section key={g.group} className="mt-10">
          <h2 className="text-lg font-semibold">{g.group}</h2>
          <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {g.items
              .filter((i) => !i.demoOnly || config?.demo)
              .map((i) => (
                <Link key={i.href} href={i.href} className="group relative rounded-2xl p-5 shadow-[0_6px_16px_rgb(0_0_0/0.12)] transition-shadow hover:shadow-[0_8px_28px_rgb(0_0_0/0.18)]">
                  <Icon3D name={i.icon} size={40} />
                  <p className="mt-6 font-semibold">{i.label}</p>
                  <p className="mt-1 text-sm text-ink-2">{(!mpesa && i.cardOnlyText) || i.text}</p>
                  {i.badge && badges[i.badge] > 0 && (
                    <span className="absolute top-5 right-5 grid h-6 min-w-6 place-items-center rounded-full bg-danger px-2 text-xs font-semibold text-white">{badges[i.badge]}</span>
                  )}
                </Link>
              ))}
          </div>
        </section>
      ))}
      <div className="mt-12 flex flex-wrap gap-3 border-t border-line pt-8">
        <Button asChild size="lg"><Link href="/"><Plane className="size-4" /> Switch to traveling</Link></Button>
        <Button variant="soft" size="lg" onClick={logout}><LogOut className="size-4" /> Log out</Button>
      </div>
    </div>
  );
}

function SosBanner() {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["host", "alerts", "active"],
    queryFn: () => get<AlertRow[]>("/api/host/alerts?status=active"),
    refetchInterval: 10_000,
  });
  const sos = data?.filter((a) => a.kind === "sos" && a.status === "open") ?? [];
  const showing = sos.length > 0;
  const ref = React.useRef<HTMLDivElement>(null);
  // full-height pages (the inbox) subtract --sos-banner-h, so the banner never pushes them under the tab bar
  React.useEffect(() => {
    const el = ref.current;
    const root = document.documentElement;
    if (!el) return;
    const ro = new ResizeObserver(() => root.style.setProperty("--sos-banner-h", `${el.offsetHeight}px`));
    ro.observe(el);
    return () => {
      ro.disconnect();
      root.style.removeProperty("--sos-banner-h");
    };
  }, [showing]);
  if (!showing) return null;
  const a = sos[0];
  return (
    <div ref={ref} className="sticky top-0 z-30 border-b border-danger/30 bg-danger text-white md:top-20">
      <div className="mx-auto flex max-w-[1400px] flex-wrap items-center gap-3 px-5 py-3 sm:px-8 md:px-10">
        <span className="grid size-9 shrink-0 place-items-center rounded-full bg-white/20 animate-pulse-ring">
          <Siren className="size-5" />
        </span>
        <div className="min-w-0 flex-1 basis-48">
          <p className="font-bold">Guest needs urgent help{sos.length > 1 ? ` (+${sos.length - 1} more)` : ""}</p>
          <p className="truncate text-sm text-white/85">{a.summary} · {ago(a.created_at)}</p>
        </div>
        <Button asChild size="sm" className="bg-white text-danger hover:bg-white/90">
          <a href={`tel:${a.phone}`}><Phone className="size-4" /> Call guest</a>
        </Button>
        <Button
          size="sm"
          variant="outline"
          className="border-white/60 bg-transparent text-white hover:bg-white/10"
          onClick={async () => {
            await post(`/api/host/alerts/${a.id}/ack`);
            qc.invalidateQueries({ queryKey: ["host"] });
          }}
        >
          I&apos;m handling it
        </Button>
      </div>
    </div>
  );
}
