"use client";

import { Suspense } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { FlaskConical } from "lucide-react";
import { cn } from "@/lib/utils";
import { WorkerStatus } from "@/components/worker-status";

const NAV = [{ href: "/experiments", label: "Experiments", icon: FlaskConical }];

function NavLinks({ pathname }: { pathname: string | null }) {
  return (
    <nav aria-label="Main" className="flex gap-1 md:flex-col">
      {NAV.map(({ href, label, icon: Icon }) => {
        const active = pathname !== null && (pathname === href || pathname.startsWith(`${href}/`));
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex items-center gap-2 rounded-md px-2 py-1.5 text-zinc-600 hover:bg-zinc-100 hover:text-zinc-950",
              active && "bg-zinc-100 font-medium text-zinc-950",
            )}
          >
            <Icon className="size-4" aria-hidden />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}

function ActiveNavLinks() {
  return <NavLinks pathname={usePathname()} />;
}

export function AppSidebar() {
  return (
    <aside className="sticky top-0 z-10 flex shrink-0 flex-wrap items-center gap-x-4 gap-y-1 border-b border-zinc-200 bg-white px-4 py-2 md:h-screen md:w-[220px] md:flex-col md:flex-nowrap md:items-stretch md:gap-6 md:border-r md:border-b-0 md:px-3 md:py-4">
      <Link href="/experiments" className="flex items-center gap-2 px-1">
        <span className="flex size-7 items-center justify-center rounded-md bg-zinc-950 font-mono text-[11px] font-semibold text-white">
          448
        </span>
        <span className="font-semibold">Research tracker</span>
      </Link>

      {/* The pathname is request data on dynamic routes (Cache Components), so it streams in;
          the fallback is the same nav without the active highlight. */}
      <Suspense fallback={<NavLinks pathname={null} />}>
        <ActiveNavLinks />
      </Suspense>

      <div className="ml-auto md:mt-auto md:ml-0">
        <WorkerStatus />
      </div>
    </aside>
  );
}
