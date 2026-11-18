"use client";

import { RotateCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";

/** Inline error for a failed query: what failed, why (from the API, or "start the API"),
 *  and a retry button. Used inside cards, so a failed request never leaves a blank page. */
export function ErrorState({
  title,
  error,
  onRetry,
  retrying = false,
  className,
}: {
  title: string;
  error: unknown;
  onRetry?: () => void;
  retrying?: boolean;
  className?: string;
}) {
  return (
    <div role="alert" className={cn("px-5 py-8 text-center", className)}>
      <p className="font-medium text-red-700">{title}</p>
      <p className="mx-auto mt-1 max-w-prose break-words text-zinc-500">
        {errorMessage(error, "Something went wrong.")}
      </p>
      {onRetry && (
        <Button variant="outline" size="sm" className="mt-3" onClick={onRetry} disabled={retrying}>
          <RotateCw className={cn(retrying && "animate-spin")} aria-hidden />
          Try again
        </Button>
      )}
    </div>
  );
}
