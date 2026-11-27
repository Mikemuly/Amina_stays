import type { Metadata } from "next";

import { ExtrasView } from "@/components/site/extras";

export const metadata: Metadata = { title: "Experiences on the coast" };

export default function ExperiencesPage() {
  return <ExtrasView kind="experiences" />;
}
