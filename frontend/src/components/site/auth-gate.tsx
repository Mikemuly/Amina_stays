"use client";

import * as React from "react";

import { useMe } from "@/components/providers";
import { SiteHeader } from "@/components/site/header";
import { PhoneLogin } from "@/components/site/phone-login";
import { Skeleton } from "@/components/ui/misc";

/** Guest pages that need a session: shows the phone-number login in place until the guest is signed in. */
export function AuthGate({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  const { data: me, isLoading } = useMe();
  if (isLoading || !me) {
    return (
      <>
        <SiteHeader />
        <main className="container-narrow max-w-[1120px] py-10">
          <Skeleton className="h-9 w-48" />
          <Skeleton className="mt-8 h-64 rounded-2xl" />
        </main>
      </>
    );
  }
  if (!me.authenticated) {
    return (
      <>
        <SiteHeader />
        <main className="container-narrow grid max-w-[1120px] place-items-center py-16">
          <div className="w-full max-w-[440px] rounded-2xl border border-line-soft p-8 shadow-soft">
            <PhoneLogin title={title} subtitle={subtitle ?? "Log in with the phone number you booked with — on the web, USSD, SMS or a call."} />
          </div>
        </main>
      </>
    );
  }
  return <>{children}</>;
}
