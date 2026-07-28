import type { Metadata } from "next";

import { GoldenView } from "@/components/views/golden";

export const metadata: Metadata = { title: "Golden set" };

export default function GoldenPage() {
  return <GoldenView />;
}
