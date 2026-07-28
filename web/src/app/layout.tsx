import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";

import { AppSidebar } from "@/components/shell/app-sidebar";
import { Providers } from "@/components/providers";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";

import "./globals.css";

const plexSans = IBM_Plex_Sans({ variable: "--font-plex-sans", subsets: ["latin"], weight: ["400", "500", "600", "700"], display: "swap" });
const plexMono = IBM_Plex_Mono({ variable: "--font-plex-mono", subsets: ["latin"], weight: ["400", "500"], display: "swap" });

export const metadata: Metadata = {
  title: { default: "Retrieval Lab", template: "%s · Retrieval Lab" },
  description: "Hybrid retrieval, grounded answers and the evaluation harness that keeps them honest.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${plexSans.variable} ${plexMono.variable}`} suppressHydrationWarning>
      <body>
        <Providers>
          <SidebarProvider>
            <AppSidebar />
            <SidebarInset className="bg-canvas">{children}</SidebarInset>
          </SidebarProvider>
        </Providers>
      </body>
    </html>
  );
}
