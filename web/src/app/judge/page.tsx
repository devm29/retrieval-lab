import type { Metadata } from "next";

import { JudgeView } from "@/components/views/judge";

export const metadata: Metadata = { title: "Judge calibration" };

export default function JudgePage() {
  return <JudgeView />;
}
