import type { Metadata } from "next";

import { DemoLab } from "@/components/demo/demo-lab";

export const metadata: Metadata = { title: "Demo Lab — SMS, USSD & Voice", robots: { index: false } };

export default function Page() {
  return <DemoLab />;
}
