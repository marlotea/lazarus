"use client";

import { useEffect } from "react";
import Link from "next/link";
import { RotateCw } from "lucide-react";
import { Button } from "@/components/ui/button";

/** Last-resort boundary for a render error, so the page is never left blank. */
export default function ErrorPage({ error, retry }: { error: unknown; retry: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="rounded-lg border border-zinc-200 bg-white px-5 py-14 text-center" role="alert">
      <h1 className="text-[17px] font-semibold text-red-700">Something went wrong</h1>
      <p className="mx-auto mt-1 max-w-prose break-words text-zinc-500">
        {error instanceof Error ? error.message : "The page failed to render."}
      </p>
      <div className="mt-4 flex justify-center gap-2">
        <Button variant="outline" size="sm" onClick={() => retry()}>
          <RotateCw aria-hidden />
          Try again
        </Button>
        <Button variant="ghost" size="sm" asChild>
          <Link href="/experiments">Back to experiments</Link>
        </Button>
      </div>
    </div>
  );
}
