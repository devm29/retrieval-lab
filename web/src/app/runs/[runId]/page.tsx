import type { Metadata } from "next";

import { RunDetailView } from "@/components/views/run-detail";

export const metadata: Metadata = { title: "Run" };

export default async function RunPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  return <RunDetailView runId={runId} />;
}
