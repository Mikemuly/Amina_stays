import type { Metadata } from "next";

import { HelpView } from "@/components/site/help-view";

export const metadata: Metadata = { title: "Help centre" };

export default function Page() {
  return <HelpView />;
}
