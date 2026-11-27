import type { Metadata } from "next";

import { GuideView } from "@/components/site/guide-view";

export const metadata: Metadata = {
  title: "Local guide",
  description: "What to see, where to eat and how to get around on the Kenyan coast - also by USSD, SMS and phone.",
};

export default function GuidePage() {
  return <GuideView />;
}
