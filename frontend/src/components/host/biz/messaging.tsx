"use client";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/overlays";
import { PageHeader } from "@/components/host/common";

import { BroadcastsTab } from "./messaging-broadcasts";
import { KnowledgeTab } from "./messaging-kb";
import { TemplatesTab } from "./messaging-templates";
import { TimelineTab } from "./messaging-timeline";
import { useTabParam } from "./ui";

const TABS = ["timeline", "templates", "knowledge", "broadcasts"] as const;

export function MessagingPage() {
  const [tab, setTab] = useTabParam(TABS, "timeline");
  return (
    <>
      <PageHeader
        title="Messaging & automations"
        subtitle="Every SMS your guests get — when it goes out, what it says in five languages, and what Ask Amina answers on its own."
      />
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="no-scrollbar mb-6 overflow-x-auto">
          <TabsTrigger value="timeline" className="shrink-0">Guest timeline</TabsTrigger>
          <TabsTrigger value="templates" className="shrink-0">Message templates</TabsTrigger>
          <TabsTrigger value="knowledge" className="shrink-0">Knowledge base</TabsTrigger>
          <TabsTrigger value="broadcasts" className="shrink-0">Broadcasts</TabsTrigger>
        </TabsList>
        <TabsContent value="timeline" className="outline-none">
          <TimelineTab />
        </TabsContent>
        <TabsContent value="templates" className="outline-none">
          <TemplatesTab />
        </TabsContent>
        <TabsContent value="knowledge" className="outline-none">
          <KnowledgeTab />
        </TabsContent>
        <TabsContent value="broadcasts" className="outline-none">
          <BroadcastsTab />
        </TabsContent>
      </Tabs>
    </>
  );
}
