import type { Metadata } from "next";
import { Suspense } from "react";

import { RunsView } from "@/components/views/runs";

export const metadata: Metadata = { title: "Runs" };

export default function RunsPage() {
  return (
    <Suspense>
      <RunsView />
    </Suspense>
  );
}
