import type { Metadata } from "next";

import { HostMenuPage } from "@/components/host/shell";

export const metadata: Metadata = { title: "Menu" };

export const instant = false;

export default function MenuPage() {
  return <HostMenuPage />;
}
