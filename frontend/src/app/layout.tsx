import type { Metadata, Viewport } from "next";
import { Figtree } from "next/font/google";

import { Providers } from "@/components/providers";

import "./globals.css";

// Figtree: the closest open-licence match to Airbnb Cereal's friendly geometric forms.
const figtree = Figtree({ subsets: ["latin", "latin-ext"], variable: "--font-figtree", display: "swap" });

export const metadata: Metadata = {
  title: { default: "Amina Stays · Coastal homes in Mombasa", template: "%s · Amina Stays" },
  description:
    "Book thoughtfully hosted apartments, cottages and family homes in Nyali, Diani, Old Town, Bamburi and Mtwapa — on the web, by SMS, USSD or a phone call.",
  applicationName: "Amina Stays",
  openGraph: { siteName: "Amina Stays", type: "website", locale: "en_KE" },
};

export const viewport: Viewport = {
  themeColor: "#ffffff",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={figtree.variable}>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
