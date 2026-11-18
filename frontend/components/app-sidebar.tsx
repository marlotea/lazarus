"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { FlaskConical } from "lucide-react";
import { cn } from "@/lib/utils";
import { WorkerStatus } from "@/components/worker-status";

const NAV = [{ href: "/experiments", label: "Experiments", icon: FlaskConical }];

export function AppSidebar() {
  const pathname = usePathname();

  return (
    <aside className="sticky top-0 z-10 flex shrink-0 items-center gap-4 border-b border-zinc-200 bg-white px-4 py-2 md:h-screen md:w-[220px] md:flex-col md:items-stretch md:gap-6 md:border-r md:border-b-0 md:px-3 md:py-4">
      <Link href="/experiments" className="flex items-center gap-2 px-1">
        <span className="flex size-7 items-center justify-center rounded-md bg-zinc-950 font-mono text-[11px] font-semibold text-white">
          448
        </span>
        <span className="font-semibold">Research tracker</span>
      </Link>

      <nav aria-label="Main" className="flex gap-1 md:flex-col">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || pathname.startsWith(`${href}/`);
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

      <div className="ml-auto md:mt-auto md:ml-0">
        <WorkerStatus />
      </div>
    </aside>
  );
}
