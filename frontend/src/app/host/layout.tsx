import type { Metadata } from "next";

import { HostShell } from "@/components/host/shell";

export const metadata: Metadata = { title: "Host console", robots: { index: false } };

// The console renders after a client-side login check, so navigations into it aren't expected to be instant.
export const instant = false;

export default function HostLayout({ children }: { children: React.ReactNode }) {
  return <HostShell>{children}</HostShell>;
}
