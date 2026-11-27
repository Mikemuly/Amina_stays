"use client";

import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";

import { useMe } from "@/components/providers";
import { SiteHeader } from "@/components/site/header";
import { PhoneLogin } from "@/components/site/phone-login";

function safeNext(next: string | null) {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/trips";
}

export function LoginView() {
  const router = useRouter();
  const params = useSearchParams();
  const next = safeNext(params.get("next"));
  const { data: me } = useMe();
  React.useEffect(() => {
    if (me?.authenticated) router.replace(next);
  }, [me, next, router]);
  return (
    <>
      <SiteHeader />
      <main className="container-narrow grid max-w-[1120px] place-items-center py-16">
        <div className="w-full max-w-[440px] rounded-2xl border border-line-soft p-8 shadow-soft">
          <PhoneLogin
            title={next.startsWith("/host") ? "Host console" : "Log in or sign up"}
            subtitle={next.startsWith("/host") ? "Amina and her team log in with their phone number." : "Your phone number is your account — on the web, USSD, SMS and voice."}
            onDone={() => router.replace(next)}
          />
        </div>
      </main>
    </>
  );
}
