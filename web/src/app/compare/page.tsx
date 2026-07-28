import type { Metadata } from "next";
import { Suspense } from "react";

import { CompareView } from "@/components/views/compare";

export const metadata: Metadata = { title: "Compare" };

export default function ComparePage() {
  return (
    <Suspense>
      <CompareView />
    </Suspense>
  );
}
