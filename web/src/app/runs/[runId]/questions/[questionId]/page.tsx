import type { Metadata } from "next";

import { QuestionDetailView } from "@/components/views/question-detail";

export const metadata: Metadata = { title: "Question" };

export default async function QuestionPage({ params }: { params: Promise<{ runId: string; questionId: string }> }) {
  const { runId, questionId } = await params;
  return <QuestionDetailView runId={runId} questionId={questionId} />;
}
