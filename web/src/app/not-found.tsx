import { Compass } from "lucide-react";
import Link from "next/link";

import { EmptyState } from "@/components/metrics/states";
import { Page } from "@/components/shell/page";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <Page title="Not found">
      <EmptyState
        icon={Compass}
        title="This page doesn't exist"
        description="The run or question may have been removed, or the link is mistyped."
        action={
          <Button asChild>
            <Link href="/">Back to overview</Link>
          </Button>
        }
      />
    </Page>
  );
}
