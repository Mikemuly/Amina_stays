import type { Metadata } from "next";

import { AccountView } from "@/components/site/account-view";

export const metadata: Metadata = { title: "Account & privacy" };

export default function Page() {
  return <AccountView />;
}
