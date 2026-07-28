"use client";

import { ErrorState } from "@/components/metrics/states";
import { Page } from "@/components/shell/page";

export default function ErrorBoundary({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <Page title="Something went wrong">
      <ErrorState error={error} onRetry={reset} />
    </Page>
  );
}
