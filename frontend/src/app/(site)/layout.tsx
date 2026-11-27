import { Suspense } from "react";

import { SiteFooter } from "@/components/site/footer";
import { LoginDialog, MobileTabBar } from "@/components/site/header";
import { LocaleDialog } from "@/components/site/locale";

export default function SiteLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      {children}
      <SiteFooter />
      <Suspense fallback={null}>
        <MobileTabBar />
      </Suspense>
      <LoginDialog />
      <LocaleDialog />
    </>
  );
}
