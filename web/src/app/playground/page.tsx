import type { Metadata } from "next";

import { PlaygroundView } from "@/components/views/playground";

export const metadata: Metadata = { title: "Playground" };

export default function PlaygroundPage() {
  return <PlaygroundView />;
}
