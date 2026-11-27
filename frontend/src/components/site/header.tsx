"use client";

import { CircleHelp, CircleUserRound, Gift, Globe, Heart, LogOut, MapPinned, Menu, MessageSquare, Search, Settings, UserRound } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import * as React from "react";

import { useAuthDialog, useConfig, useLogout, useMe } from "@/components/providers";
import { BrandLink, BrandMark } from "@/components/site/brand";
import { openLocaleDialog } from "@/components/site/locale";
import { PhoneLogin } from "@/components/site/phone-login";
import { CompactSearch, MobileSearch, SearchBar, type Segment } from "@/components/site/search-bar";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Icon3D, type Icon3DName } from "@/components/ui/icon3d";
import { Avatar } from "@/components/ui/misc";
import { Dropdown, DropdownContent, DropdownItem, DropdownSeparator, DropdownTrigger } from "@/components/ui/overlays";
import { cn } from "@/lib/utils";

export type SiteTab = "all" | "homes" | "hotels" | "experiences" | "services";

export const SITE_TABS: { id: SiteTab; href: string; label: string; icon: Icon3DName }[] = [
  { id: "all", href: "/", label: "All", icon: "globe" },
  { id: "homes", href: "/homes", label: "Homes", icon: "homes" },
  { id: "hotels", href: "/hotels", label: "Hotels", icon: "hotel" },
  { id: "experiences", href: "/experiences", label: "Experiences", icon: "sailboat" },
  { id: "services", href: "/services", label: "Services", icon: "services" },
];

// Desktop heights, as measured on Airbnb: the expanded home header is a 200px band (an 80px top row — 96px
// from 1440px — over the search bar) that collapses into an 80px row with the compact search pill.
const ROW = 80;
const EXPANDED = 200;

/**
 * The site header, modelled on Airbnb's 2025 header.
 * - mode "home": a tall header (tabs + full search bar on a soft band) that collapses into the
 *   compact search pill once you scroll; it's fixed with a spacer, so collapsing never shifts content.
 * - mode "compact": the pill only (inner pages). Clicking it expands the full search over the page.
 * - mode "minimal": just the logo (checkout), so nothing competes with finishing the booking.
 * On phones the header is just the "Start your search" pill (when `mobileSearch`), as on Airbnb.
 */
export function SiteHeader({
  mode = "compact", tab = "homes", width = "site", mobileSearch = false, children,
}: {
  mode?: "home" | "compact" | "minimal";
  tab?: SiteTab;
  width?: "site" | "narrow";
  mobileSearch?: boolean;
  children?: React.ReactNode;
}) {
  const isHome = mode === "home";
  const [atTop, setAtTop] = React.useState(true);
  const [overlay, setOverlay] = React.useState<Segment | null>(null);
  const [overlayKey, setOverlayKey] = React.useState(0);

  React.useEffect(() => {
    const on = () => {
      if (isHome) setAtTop(window.scrollY < EXPANDED - ROW);
      setOverlay(null);
    };
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, [isHome]);

  const openOverlay = (seg: Segment) => {
    setOverlayKey((k) => k + 1);
    setOverlay(seg);
  };
  const tall = isHome && atTop;
  const container = width === "narrow" ? "container-narrow" : "container-site";

  if (mode === "minimal") {
    return (
      <header className="z-40 border-b border-line-soft bg-white max-md:hidden">
        <div className={cn(container, "flex h-20 items-center")}>
          <BrandLink />
        </div>
      </header>
    );
  }

  const topRow = (expanded: boolean) => (
    <div className={cn(container, "grid h-20 grid-cols-[1fr_auto_1fr] items-center gap-4", expanded && "min-[1440px]:h-24")}>
      <BrandLink compact className="justify-self-start" />
      <div className="flex justify-center">
        {expanded ? (
          <Tabs active={tab} />
        ) : (
          <React.Suspense fallback={<div className="h-12 w-[380px] rounded-full border border-line-soft shadow-pill" />}>
            <CompactSearch onOpen={openOverlay} />
          </React.Suspense>
        )}
      </div>
      <UserMenu />
    </div>
  );
  const searchRow = (initial: Segment | null) => (
    <div className={cn(container, "pt-3.5 pb-10 min-[1440px]:pt-1.5 min-[1440px]:pb-8")}>
      <React.Suspense fallback={<div className="mx-auto h-[66px] max-w-[850px] rounded-full border border-line bg-white shadow-search" />}>
        <SearchBar key={overlayKey} initial={initial} onClose={() => setOverlay(null)} />
      </React.Suspense>
    </div>
  );

  return (
    <>
      <header
        className={cn(
          "z-40 bg-white",
          isHome ? "sticky top-0 md:fixed md:inset-x-0" : "sticky top-0",
          !mobileSearch && "max-md:hidden",
        )}
      >
        {/* phones */}
        {mobileSearch && (
          <div className="bg-white px-6 pt-3 pb-3 md:hidden">
            <React.Suspense fallback={<div className="h-14 rounded-full border border-line-soft shadow-pill" />}>
              <MobileSearch />
            </React.Suspense>
          </div>
        )}
        {/* desktop & tablet */}
        <div className={cn("relative hidden border-b border-line-soft md:block", tall ? "hero-band" : "bg-white")}>
          {topRow(tall)}
          {tall && searchRow(null)}
          {overlay !== null && !tall && (
            <div className="hero-band absolute inset-x-0 top-0 z-10 border-b border-line-soft animate-fade-in">
              {topRow(true)}
              {searchRow(overlay)}
            </div>
          )}
        </div>
        {children}
      </header>
      {isHome && <div aria-hidden className="hidden md:block" style={{ height: EXPANDED }} />}
      {overlay !== null && !tall && <div className="fixed inset-0 z-30 bg-black/25 animate-fade-in max-md:hidden" onClick={() => setOverlay(null)} />}
    </>
  );
}

/** Airbnb's category tabs: icon over label on tablets, side by side from 1128px, a square 3px bar under the active one. */
function Tabs({ active }: { active: SiteTab }) {
  return (
    <nav className="flex items-center gap-7 lg:gap-10" aria-label="Browse">
      {SITE_TABS.map((t) => {
        const on = t.id === active;
        return (
          <Link
            key={t.id}
            href={t.href}
            aria-current={on ? "page" : undefined}
            className={cn(
              "group relative flex flex-col items-center gap-1.5 text-sm leading-[18px] font-medium whitespace-nowrap transition-colors min-[1128px]:h-9 min-[1128px]:flex-row min-[1128px]:gap-2.5",
              on ? "text-ink" : "text-ink-2 hover:text-ink",
            )}
          >
            {/* drawn at 40px inside Airbnb's 36px icon box: the PNGs carry a little transparent padding */}
            <Icon3D name={t.icon} size={40} eager className="-m-0.5 max-w-none transition-transform duration-300 group-hover:scale-110 group-hover:-rotate-3" />
            {t.label}
            <span
              aria-hidden
              className={cn(
                "absolute inset-x-0 top-full mt-1.5 h-[3px] bg-ink transition-[opacity,transform] duration-200 min-[1128px]:inset-x-[3px] min-[1128px]:mt-2",
                on ? "opacity-100" : "scale-x-50 opacity-0",
              )}
            />
          </Link>
        );
      })}
    </nav>
  );
}

/** Mobile tab chips (All · Homes · Hotels · Experiences · Services) shown under the search pill. */
export function MobileTabs({ active, className }: { active: SiteTab; className?: string }) {
  return (
    <nav className={cn("no-scrollbar flex gap-2 overflow-x-auto border-b border-line-soft px-6 pt-1.5 pb-4 md:hidden", className)} aria-label="Browse">
      {SITE_TABS.map((t) => (
        <Link
          key={t.id}
          href={t.href}
          aria-current={t.id === active ? "page" : undefined}
          className={cn(
            // Airbnb's "pillow" chip: layered drop shadow plus a soft top highlight
            "flex h-10 shrink-0 items-center gap-1.5 rounded-full pr-3.5 pl-2 text-sm text-ink shadow-[0_3px_2.5px_rgb(0_0_0/0.1),0_1px_1px_rgb(0_0_0/0.15),0_0.8px_0.4px_rgb(0_0_0/0.15),inset_0_1px_0_rgb(255_255_255/0.9)] transition-colors",
            t.id === active ? "bg-chip font-medium" : "bg-white",
          )}
        >
          <Icon3D name={t.icon} size={28} eager />
          {t.label}
        </Link>
      ))}
    </nav>
  );
}

function UserMenu() {
  const { data: me } = useMe();
  const { data: config } = useConfig();
  const { requireLogin } = useAuthDialog();
  const logout = useLogout();
  const router = useRouter();
  const c = config?.channels;
  return (
    <div className="flex items-center justify-end gap-3">
      {me?.is_host ? (
        <Link href="/host" className="hidden h-10 items-center rounded-full px-4 text-sm font-medium whitespace-nowrap transition-colors hover:bg-chip xl:flex">
          Switch to hosting
        </Link>
      ) : (
        <Link href="/help#book-your-way" className="hidden h-10 items-center rounded-full px-4 text-sm font-medium whitespace-nowrap transition-colors hover:bg-chip xl:flex">
          Book without data
        </Link>
      )}
      <button
        type="button"
        onClick={() => (me?.authenticated ? router.push("/account") : requireLogin())}
        aria-label={me?.authenticated ? "Your profile" : "Log in"}
        className="grid size-10 place-items-center rounded-full bg-chip transition-colors hover:bg-line-soft"
      >
        {me?.authenticated ? <Avatar name={me.name || me.phone} size={32} className="bg-ink! text-[13px]!" /> : <CircleUserRound className="size-5" strokeWidth={1.8} />}
      </button>
      <Dropdown>
        <DropdownTrigger className="grid size-10 place-items-center rounded-full bg-chip transition-colors outline-none hover:bg-line-soft data-[state=open]:bg-line-soft" aria-label="Main menu">
          <Menu className="size-[18px]" strokeWidth={2.2} />
        </DropdownTrigger>
        <DropdownContent sideOffset={20} className="w-[265px] rounded-xl border-0 py-3 shadow-pop">
          {me?.authenticated ? (
            <>
              <MenuItem onSelect={() => router.push("/wishlists")} icon={Heart}>Wishlists</MenuItem>
              <MenuItem onSelect={() => router.push("/trips")} icon={BrandMark}>Trips</MenuItem>
              <MenuItem onSelect={() => router.push("/messages")} icon={MessageSquare}>Messages</MenuItem>
              <MenuItem onSelect={() => router.push("/account")} icon={UserRound}>Profile</MenuItem>
              <MenuItem onSelect={() => router.push("/account#rewards")} icon={Gift}>Rewards</MenuItem>
              <MenuSeparator />
              <MenuItem onSelect={() => router.push("/account")} icon={Settings}>Account &amp; privacy</MenuItem>
              <MenuItem onSelect={() => openLocaleDialog()} icon={Globe}>Languages &amp; currency</MenuItem>
              <MenuItem onSelect={() => router.push("/guide")} icon={MapPinned}>Local guide</MenuItem>
              <MenuItem onSelect={() => router.push("/help")} icon={CircleHelp}>Help Centre</MenuItem>
              <MenuSeparator />
              {me.is_host ? (
                <PromoItem onSelect={() => router.push("/host")} icon="key" title="Switch to hosting" text="Today, calendar, inbox and the team." />
              ) : (
                <PromoItem onSelect={() => router.push("/help#book-your-way")} icon="mobile-phone" title="Book without data" text={c?.ussd_code ? `Dial ${c.ussd_code} or text Amina — English or Kiswahili.` : "Book by USSD, SMS or a phone call."} />
              )}
              <MenuSeparator />
              <MenuItem onSelect={logout} icon={LogOut}>Log out</MenuItem>
            </>
          ) : (
            <>
              <MenuItem onSelect={() => openLocaleDialog()} icon={Globe}>Languages &amp; currency</MenuItem>
              <MenuItem onSelect={() => router.push("/guide")} icon={MapPinned}>Local guide</MenuItem>
              <MenuItem onSelect={() => router.push("/help")} icon={CircleHelp}>Help Centre</MenuItem>
              <MenuSeparator />
              <PromoItem onSelect={() => router.push("/help#book-your-way")} icon="mobile-phone" title="Book without data" text={c?.ussd_code ? `Dial ${c.ussd_code} or text Amina — English or Kiswahili.` : "Book by USSD, SMS or a phone call."} />
              <MenuSeparator />
              <MenuItem onSelect={() => router.push("/host")}>Host console</MenuItem>
              <MenuItem onSelect={() => router.push("/demo")}>Demo Lab</MenuItem>
              <MenuSeparator />
              <MenuItem onSelect={() => requireLogin()}>Log in or sign up</MenuItem>
            </>
          )}
        </DropdownContent>
      </Dropdown>
    </div>
  );
}

// Airbnb's menu rhythm: 36px rows with 24px side padding, 16px icons and hairlines inset to the text.
function MenuItem({ icon: Icon, children, onSelect, className }: {
  icon?: React.ComponentType<{ className?: string; strokeWidth?: number }>; children: React.ReactNode; onSelect: () => void; className?: string;
}) {
  return (
    <DropdownItem onSelect={onSelect} className={cn("gap-2.5 px-6 py-[9px] text-sm leading-[18px]", className)}>
      {Icon && <Icon className="size-4 shrink-0" strokeWidth={1.8} />}
      {children}
    </DropdownItem>
  );
}

const MenuSeparator = () => <DropdownSeparator className="mx-6 bg-line" />;

function PromoItem({ icon, title, text, onSelect }: { icon: Icon3DName; title: string; text: string; onSelect: () => void }) {
  return (
    <DropdownItem onSelect={onSelect} className="gap-2.5 px-6 py-1">
      <span className="min-w-0 flex-1">
        <span className="block text-sm leading-[18px] font-medium">{title}</span>
        <span className="block text-xs leading-4 text-ink-2">{text}</span>
      </span>
      <Icon3D name={icon} size={48} />
    </DropdownItem>
  );
}

export function LoginDialog() {
  const { dialog, closeLogin } = useAuthDialog();
  return (
    <Dialog open={dialog.open} onOpenChange={(o) => !o && closeLogin()}>
      <DialogContent title="Log in or sign up" size="sm">
        <div className="p-6">
          <PhoneLogin
            title="Karibu to Amina Stays"
            subtitle={dialog.reason ?? "Your phone number is your account — on the web, USSD, SMS and voice."}
            onDone={() => {
              const then = dialog.then;
              closeLogin();
              then?.();
            }}
          />
        </div>
      </DialogContent>
    </Dialog>
  );
}

const TAB_BAR_PAGES = ["/", "/homes", "/hotels", "/s", "/experiences", "/services", "/guide", "/trips", "/wishlists", "/messages", "/account", "/help"];

/** Phone bottom navigation; slides away while scrolling down, returns on scroll up. */
export function MobileTabBar() {
  const pathname = usePathname();
  const { data: me } = useMe();
  const { requireLogin } = useAuthDialog();
  const [hidden, setHidden] = React.useState(false);
  React.useEffect(() => {
    let last = window.scrollY;
    const on = () => {
      const y = window.scrollY;
      if (Math.abs(y - last) > 6) setHidden(y > last && y > 120);
      last = y;
    };
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);
  if (!TAB_BAR_PAGES.includes(pathname)) return null;
  const authed = !!me?.authenticated;
  const tabs: { href: string; label: string; icon: React.ComponentType<{ className?: string; strokeWidth?: number }>; auth?: boolean; match?: string[] }[] = [
    { href: "/", label: "Explore", icon: Search, match: ["/", "/homes", "/hotels", "/s", "/experiences", "/services", "/guide"] },
    { href: "/wishlists", label: "Wishlists", icon: Heart, auth: true },
    ...(authed
      ? [
          { href: "/trips", label: "Trips", icon: BrandMark },
          { href: "/messages", label: "Messages", icon: MessageSquare },
          { href: "/account", label: "Profile", icon: CircleUserRound },
        ]
      : [{ href: "/account", label: "Log in", icon: CircleUserRound, auth: true }]),
  ];
  return (
    // suppressHydrationWarning: a dialog opened before this streams in marks it aria-hidden (Radix), which React would report
    <nav
      suppressHydrationWarning
      className={cn(
        "fixed inset-x-0 bottom-0 z-40 border-t border-line-soft bg-white pb-[env(safe-area-inset-bottom)] transition-transform duration-300 md:hidden print:hidden",
        hidden && "translate-y-full",
      )}
    >
      <div className="mx-auto flex max-w-md justify-around">
        {tabs.map((t) => {
          const active = t.match ? t.match.includes(pathname) : pathname.startsWith(t.href);
          const Icon = t.icon;
          return (
            <Link
              key={t.label}
              href={t.href}
              onClick={(e) => {
                if (t.auth && !authed) {
                  e.preventDefault();
                  requireLogin();
                }
              }}
              className={cn("flex min-w-16 flex-col items-center gap-1 pt-2.5 pb-2 text-[10px]", active ? "font-medium text-brand-600" : "text-ink-2")}
            >
              <Icon className={cn("size-6", !active && t.icon === BrandMark && "text-ink-3")} strokeWidth={active ? 2.2 : 1.6} />
              {t.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
