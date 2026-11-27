"use client";

import { QueryClient, QueryClientProvider, useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { Toaster } from "sonner";

import { get, post } from "@/lib/api";
import type { Config, Me } from "@/lib/types";

let browserClient: QueryClient | undefined;
function getQueryClient() {
  const make = () =>
    new QueryClient({ defaultOptions: { queries: { staleTime: 20_000, refetchOnWindowFocus: false, retry: 1 } } });
  if (typeof window === "undefined") return make();
  browserClient ??= make();
  return browserClient;
}

type AuthDialogState = { open: boolean; reason?: string; then?: () => void };
const AuthCtx = React.createContext<{
  dialog: AuthDialogState;
  requireLogin: (reason?: string, then?: () => void) => void;
  closeLogin: () => void;
} | null>(null);

export function Providers({ children }: { children: React.ReactNode }) {
  const [dialog, setDialog] = React.useState<AuthDialogState>({ open: false });
  const value = React.useMemo(
    () => ({
      dialog,
      requireLogin: (reason?: string, then?: () => void) => setDialog({ open: true, reason, then }),
      closeLogin: () => setDialog({ open: false }),
    }),
    [dialog],
  );
  return (
    <QueryClientProvider client={getQueryClient()}>
      <AuthCtx.Provider value={value}>
        {children}
        <Toaster position="top-center" className="print:hidden" toastOptions={{ className: "!rounded-xl !text-[14px] !font-medium" }} />
      </AuthCtx.Provider>
    </QueryClientProvider>
  );
}

export function useAuthDialog() {
  const ctx = React.useContext(AuthCtx);
  if (!ctx) throw new Error("useAuthDialog outside Providers");
  return ctx;
}

const noopSubscribe = () => () => {};

/** False on the server and while hydrating, true afterwards — keeps the first client render identical to the HTML. */
export function useHydrated() {
  return React.useSyncExternalStore(noopSubscribe, () => true, () => false);
}

// `me` and `config` are shared queries that early-hydrating parts (footer, tab bar) start fetching. A Suspense
// boundary that streams in later would otherwise hydrate with cached data the server HTML never had.
export function hydrationSafe<T extends { data: unknown }>(q: T, hydrated: boolean): T {
  return hydrated ? q : ({ ...q, data: undefined, isLoading: true, isPending: true, isSuccess: false, status: "pending" } as T);
}

export function useMe() {
  const q = useQuery({ queryKey: ["me"], queryFn: () => get<Me>("/api/auth/me"), staleTime: 60_000 });
  return hydrationSafe(q, useHydrated());
}

export function useConfig() {
  const q = useQuery({ queryKey: ["config"], queryFn: () => get<Config>("/api/config"), staleTime: 5 * 60_000 });
  return hydrationSafe(q, useHydrated());
}

/** How guests can pay here. M-Pesa only while the site has it on (MPESA_PROVIDER isn't "off"); until the config
 * has loaded it counts as off, so nothing offers a prompt the site can't send. `methods` is ready for copy:
 * "Pay by {methods}". `cardTest` is Stripe in test mode, where Stripe's test cards work. */
export function usePayOptions() {
  const { data } = useConfig();
  const mpesa = !!data && data.payments.mpesa !== "off";
  return { mpesa, methods: mpesa ? "M-Pesa or card" : "card", cardTest: !!data?.payments.card_test_mode };
}

export function useLogout() {
  const qc = useQueryClient();
  return async () => {
    await post("/api/auth/logout");
    qc.clear();
    window.location.replace(window.location.origin); // full reload: no cached private data survives logout
  };
}
