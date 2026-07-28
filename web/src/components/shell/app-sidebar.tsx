"use client";

import {
  BookCheck,
  FlaskConical,
  GitCompareArrows,
  LayoutDashboard,
  ListChecks,
  type LucideIcon,
  MessageSquareText,
  Scale,
  SlidersHorizontal,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from "@/components/ui/sidebar";

import { HealthIndicator } from "./health-indicator";
import { ThemeToggle } from "./theme-toggle";

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}

const NAV: { label: string; items: NavItem[] }[] = [
  {
    label: "Evaluate",
    items: [
      { href: "/", label: "Overview", icon: LayoutDashboard },
      { href: "/runs", label: "Runs", icon: ListChecks },
      { href: "/compare", label: "Compare", icon: GitCompareArrows },
    ],
  },
  {
    label: "Explore",
    items: [
      { href: "/playground", label: "Playground", icon: MessageSquareText },
      { href: "/golden", label: "Golden set", icon: BookCheck },
    ],
  },
  {
    label: "Calibrate",
    items: [
      { href: "/judge", label: "Judge", icon: Scale },
      { href: "/configs", label: "Pipelines", icon: SlidersHorizontal },
    ],
  },
];

function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}

export function AppSidebar() {
  const pathname = usePathname();

  return (
    <Sidebar collapsible="icon" className="material border-r border-sidebar-border/60">
      <SidebarHeader className="px-3 pt-4 pb-2">
        <Link href="/" className="flex items-center gap-2.5 rounded-lg px-1 py-1 outline-none focus-visible:ring-4 focus-visible:ring-ring">
          <span className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <FlaskConical className="size-4" strokeWidth={2} aria-hidden />
          </span>
          <span className="truncate text-[15px] font-semibold tracking-tight group-data-[collapsible=icon]:hidden">
            Retrieval Lab
          </span>
        </Link>
      </SidebarHeader>
      <SidebarContent>
        {NAV.map((group) => (
          <SidebarGroup key={group.label}>
            <SidebarGroupLabel className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
              {group.label}
            </SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {group.items.map((item) => (
                  <SidebarMenuItem key={item.href}>
                    <SidebarMenuButton
                      asChild
                      isActive={isActive(pathname, item.href)}
                      tooltip={item.label}
                      className="h-8 text-[13px] data-[active=true]:font-medium"
                    >
                      <Link href={item.href}>
                        <item.icon strokeWidth={1.75} aria-hidden />
                        <span>{item.label}</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        ))}
      </SidebarContent>
      <SidebarFooter className="gap-2 p-3">
        <HealthIndicator />
        <ThemeToggle />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}
