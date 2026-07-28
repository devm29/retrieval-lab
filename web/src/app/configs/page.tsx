import type { Metadata } from "next";

import { ConfigsView } from "@/components/views/configs";

export const metadata: Metadata = { title: "Pipelines" };

export default function ConfigsPage() {
  return <ConfigsView />;
}
