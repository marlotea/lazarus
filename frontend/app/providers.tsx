"use client";

import { useState } from "react";
import { QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { toast } from "sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/sonner";
import { ApiError, errorMessage } from "@/lib/api";

/** Client errors (4xx) will not change on a retry; network and server errors might. */
function shouldRetry(failureCount: number, err: unknown): boolean {
  if (err instanceof ApiError && err.status >= 400 && err.status < 500) return false;
  return failureCount < 1;
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        // Every failed query also shows a toast (the page shows its own inline error state).
        // A 404 or 422 (bad id in the URL) is shown as "not found" by the page itself, and
        // `meta.silent` opts a query out (the health poll: the sidebar shows "Worker offline").
        queryCache: new QueryCache({
          onError: (err, query) => {
            if (query.meta?.silent) return;
            if (err instanceof ApiError && (err.status === 404 || err.status === 422)) return;
            const message = errorMessage(err, "Could not load data");
            // Same id for the same message: an API outage shows one toast, not one per query.
            toast.error(message, { id: `query-error:${message}` });
          },
        }),
        defaultOptions: {
          queries: { staleTime: 5_000, refetchOnWindowFocus: false, retry: shouldRetry },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        {children}
        <Toaster theme="light" position="bottom-right" />
      </TooltipProvider>
    </QueryClientProvider>
  );
}
