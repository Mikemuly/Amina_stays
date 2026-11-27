"use client";

import { useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { toast } from "sonner";

import { useAuthDialog, useConfig, useMe, usePayOptions } from "@/components/providers";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/overlays";
import { patch } from "@/lib/api";
import { createBrowserStore, readStorage, writeStorage } from "@/lib/browser-store";
import { kes } from "@/lib/format";
import type { Lang, Me } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * Airbnb's "Languages & currency". Guests always pay in KES (by card, or M-Pesa when it's on), so the currency is a display
 * preference kept in this browser; the language is the guest's account setting for Amina's texts and WhatsApps.
 */
export type Currency = "KES" | "USD" | "EUR" | "GBP";

export const CURRENCIES: { code: Currency; name: string; symbol: string }[] = [
  { code: "KES", name: "Kenyan shilling", symbol: "KSh" },
  { code: "USD", name: "United States dollar", symbol: "$" },
  { code: "EUR", name: "Euro", symbol: "€" },
  { code: "GBP", name: "British pound", symbol: "£" },
];

// Mirrors accounts.models.LANGUAGES.
const LANGUAGES: { code: Lang; name: string; region: string }[] = [
  { code: "en", name: "English", region: "Kenya" },
  { code: "sw", name: "Kiswahili", region: "Kenya" },
  { code: "fr", name: "Français", region: "France" },
  { code: "de", name: "Deutsch", region: "Deutschland" },
  { code: "it", name: "Italiano", region: "Italia" },
];

const CURRENCY_KEY = "amina:currency";
const currencyStore = createBrowserStore<Currency>(() => {
  const v = readStorage(CURRENCY_KEY);
  return CURRENCIES.some((c) => c.code === v) ? (v as Currency) : "KES";
});

function setCurrency(code: Currency) {
  writeStorage(CURRENCY_KEY, code);
  currencyStore.notify();
}

/** The guest's display currency; "KES" on the server and while hydrating, so the first render matches the HTML. */
export function useCurrency() {
  return React.useSyncExternalStore(currencyStore.subscribe, currencyStore.read, () => "KES" as Currency);
}

/** Formats a KES amount in the guest's display currency, converted at Amina's rates (falls back to KES). */
export function useMoney() {
  const code = useCurrency();
  const { data: config } = useConfig();
  const rate = code === "KES" ? undefined : config?.currencies?.[code];
  const symbol = CURRENCIES.find((c) => c.code === code)?.symbol ?? "";
  return React.useCallback(
    (n?: number | null) => (rate ? `${symbol}${Math.round((n ?? 0) / rate).toLocaleString("en-KE")}` : kes(n)),
    [rate, symbol],
  );
}

type LocaleTab = "language" | "currency";
let openTab: LocaleTab | null = null;
const dialogStore = createBrowserStore<LocaleTab | null>(() => openTab);
function setOpenTab(tab: LocaleTab | null) {
  openTab = tab;
  dialogStore.notify();
}

/** Opens the Languages & currency dialog (rendered once by the site layout). */
export const openLocaleDialog = (tab: LocaleTab = "language") => setOpenTab(tab);

export function LocaleDialog() {
  const tab = React.useSyncExternalStore(dialogStore.subscribe, dialogStore.read, () => null);
  const close = () => setOpenTab(null);
  return (
    <Dialog open={tab !== null} onOpenChange={(o) => !o && close()}>
      {tab && (
        <DialogContent
          title={<span className="sr-only">Languages and currency</span>}
          description="Choose the language Amina messages you in and the currency prices are shown in"
          size="xl"
          className="[&>div:first-child]:border-b-0"
        >
          <Tabs value={tab} onValueChange={(v) => setOpenTab(v as LocaleTab)}>
            <TabsList className="mx-6 md:mx-8">
              <TabsTrigger value="language" className="font-medium">Language and region</TabsTrigger>
              <TabsTrigger value="currency" className="font-medium">Currency</TabsTrigger>
            </TabsList>
            <TabsContent value="language" className="px-6 pt-8 pb-10 outline-none md:px-8">
              <LanguagePanel onDone={close} />
            </TabsContent>
            <TabsContent value="currency" className="px-6 pt-8 pb-10 outline-none md:px-8">
              <CurrencyPanel onDone={close} />
            </TabsContent>
          </Tabs>
        </DialogContent>
      )}
    </Dialog>
  );
}

function LanguagePanel({ onDone }: { onDone: () => void }) {
  const { data: me } = useMe();
  const { requireLogin } = useAuthDialog();
  const qc = useQueryClient();
  const [saving, setSaving] = React.useState<Lang | null>(null);
  const current: Lang = me?.authenticated ? (me.lang ?? "en") : "en";

  const choose = (l: (typeof LANGUAGES)[number]) => {
    if (l.code === current) return onDone();
    const save = async () => {
      setSaving(l.code);
      try {
        qc.setQueryData(["me"], await patch<Me>("/api/me", { lang: l.code }));
        toast.success(`Amina will message you in ${l.name}`);
        onDone();
      } catch (e) {
        toast.error((e as Error).message);
      } finally {
        setSaving(null);
      }
    };
    if (me?.authenticated) return void save();
    // the language lives on the guest's account (their phone number), so sign in first
    onDone();
    requireLogin(`Log in so Amina can message you in ${l.name}`, save);
  };

  return (
    <>
      <h2 className="text-[22px] leading-[26px] font-semibold tracking-tight">Choose a language and region</h2>
      <p className="mt-2 max-w-2xl text-sm text-ink-2">
        This website is in English. Amina&apos;s texts and WhatsApp messages come in the language you pick — the USSD menu and phone line speak English and Kiswahili.
      </p>
      <div className="mt-6 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
        {LANGUAGES.map((l) => (
          <Option key={l.code} selected={l.code === current} busy={saving === l.code} onClick={() => choose(l)} title={l.name} subtitle={l.region} />
        ))}
      </div>
    </>
  );
}

function CurrencyPanel({ onDone }: { onDone: () => void }) {
  const code = useCurrency();
  const { data: config } = useConfig();
  const { methods } = usePayOptions();
  const rates = config?.currencies ?? {};
  const shown = CURRENCIES.filter((c) => c.code === "KES" || rates[c.code]);
  return (
    <>
      <h2 className="text-[22px] leading-[26px] font-semibold tracking-tight">Choose a currency</h2>
      <div className="mt-6 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
        {shown.map((c) => (
          <Option
            key={c.code}
            selected={c.code === code}
            onClick={() => {
              setCurrency(c.code);
              onDone();
            }}
            title={c.name}
            subtitle={`${c.code} – ${c.symbol}`}
          />
        ))}
      </div>
      <p className="mt-6 max-w-2xl text-sm text-ink-2">
        You always pay in Kenyan shillings, by {methods}. Other currencies are a guide, converted at Amina&apos;s rates
        {shown.length > 1 && <>: {shown.filter((c) => c.code !== "KES").map((c) => `1 ${c.code} = ${kes(rates[c.code])}`).join(" · ")}</>}.
      </p>
    </>
  );
}

function Option({ title, subtitle, selected, busy, onClick }: { title: string; subtitle: string; selected: boolean; busy?: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={busy}
      aria-pressed={selected}
      className={cn(
        "rounded-lg px-3 py-2.5 text-left text-sm leading-[18px] transition-colors hover:bg-surface disabled:opacity-60",
        selected && "ring-1 ring-ink ring-inset",
      )}
    >
      <span className="block text-ink">{title}</span>
      <span className="block text-ink-2">{subtitle}</span>
    </button>
  );
}
