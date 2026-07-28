import { ChevronLeft } from "lucide-react";
import Link from "next/link";

import { SidebarTrigger } from "@/components/ui/sidebar";
import { cn } from "@/lib/utils";

interface PageProps {
  title: string;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
  back?: { href: string; label: string };
  width?: "default" | "wide" | "reading";
  children: React.ReactNode;
}

const WIDTHS = { default: "max-w-6xl", wide: "max-w-[1400px]", reading: "max-w-4xl" } as const;

export function Page({ title, subtitle, actions, back, width = "default", children }: PageProps) {
  return (
    <>
      <header className="material sticky top-0 z-30 flex h-13 items-center gap-2 border-b border-border/60 bg-background/72 px-4 backdrop-blur-xl backdrop-saturate-[1.8]">
        <SidebarTrigger className="-ml-1 size-8" aria-label="Toggle sidebar" />
        {back ? (
          <Link
            href={back.href}
            className="flex items-center gap-0.5 rounded-md px-1.5 py-1 text-[13px] text-primary outline-none hover:bg-accent/60 focus-visible:ring-4 focus-visible:ring-ring"
          >
            <ChevronLeft className="size-4" strokeWidth={2} aria-hidden />
            {back.label}
          </Link>
        ) : null}
        <p className="truncate text-[15px] font-semibold">{title}</p>
        {actions ? <div className="ml-auto flex items-center gap-2">{actions}</div> : null}
      </header>
      <main className={cn("mx-auto w-full px-4 py-8 sm:px-6 lg:px-8", WIDTHS[width])}>
        <div className="mb-8 space-y-1">
          <h1 className="text-[28px] leading-[34px] font-bold tracking-tight sm:text-[34px] sm:leading-[41px]">{title}</h1>
          {subtitle ? <div className="text-[15px] text-muted-foreground">{subtitle}</div> : null}
        </div>
        {children}
      </main>
    </>
  );
}

export function Section({
  title,
  description,
  actions,
  children,
  className,
}: {
  title: string;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("space-y-3", className)}>
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 className="text-[17px] leading-[22px] font-semibold tracking-tight">{title}</h2>
          {description ? <p className="text-[13px] text-muted-foreground">{description}</p> : null}
        </div>
        {actions}
      </div>
      {children}
    </section>
  );
}
