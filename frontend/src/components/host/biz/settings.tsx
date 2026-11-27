"use client";

import { PageHeader } from "@/components/host/common";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/overlays";

import { AddonsTab } from "./settings-addons";
import { BusinessTab } from "./settings-business";
import { PricingRulesTab } from "./settings-pricing";
import { TeamTab } from "./settings-team";
import { useTabParam } from "./ui";

const TABS = ["business", "team", "addons", "pricing"] as const;

export function SettingsPage() {
  const [tab, setTab] = useTabParam(TABS, "business");
  return (
    <>
      <PageHeader title="Settings" subtitle="Business rules, your team, extras and seasonal pricing — changes apply on every channel straight away." />
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="no-scrollbar mb-6 overflow-x-auto">
          <TabsTrigger value="business" className="shrink-0">Business & policies</TabsTrigger>
          <TabsTrigger value="team" className="shrink-0">Team & staff</TabsTrigger>
          <TabsTrigger value="addons" className="shrink-0">Add-ons & extras</TabsTrigger>
          <TabsTrigger value="pricing" className="shrink-0">Pricing rules</TabsTrigger>
        </TabsList>
        <TabsContent value="business" className="outline-none">
          <BusinessTab />
        </TabsContent>
        <TabsContent value="team" className="outline-none">
          <TeamTab />
        </TabsContent>
        <TabsContent value="addons" className="outline-none">
          <AddonsTab />
        </TabsContent>
        <TabsContent value="pricing" className="outline-none">
          <PricingRulesTab />
        </TabsContent>
      </Tabs>
    </>
  );
}
