import type { Metadata } from "next";

import { ExtrasView } from "@/components/site/extras";

export const metadata: Metadata = { title: "Services for your stay" };

export default function ServicesPage() {
  return <ExtrasView kind="services" />;
}
