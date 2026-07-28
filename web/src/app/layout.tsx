import type { Metadata } from "next";
import { Inter } from "next/font/google";

import { AppSidebar } from "@/components/shell/app-sidebar";
import { Providers } from "@/components/providers";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";

import "./globals.css";

const inter = Inter({ variable: "--font-inter", subsets: ["latin"], display: "swap" });

export const metadata: Metadata = {
  title: { default: "Retrieval Lab", template: "%s · Retrieval Lab" },
  description: "Hybrid retrieval, grounded answers and the evaluation harness that keeps them honest.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={inter.variable} suppressHydrationWarning>
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
