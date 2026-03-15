import { NextRequest, NextResponse } from "next/server";
import { getBrief, updateBriefReview } from "@/lib/backend";
import type { ReviewState } from "@/lib/types";

const VALID_REVIEW_STATES: ReviewState[] = [
  "awaiting_review",
  "approved_for_validation",
  "rejected_by_operator",
  "needs_more_analysis",
  "exported",
];

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const brief = await getBrief(id);
  if (!brief) {
    return NextResponse.json({ error: "Brief not found" }, { status: 404 });
  }
  return NextResponse.json({ brief });
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const body = await request.json();

  const reviewState = body.review_state as string;
  if (!reviewState || !VALID_REVIEW_STATES.includes(reviewState as ReviewState)) {
    return NextResponse.json(
      { error: `Invalid review_state. Valid: ${VALID_REVIEW_STATES.join(", ")}` },
      { status: 400 }
    );
  }

  const reviewNotes = (body.review_notes as string) ?? "";

  const updated = await updateBriefReview(
    id,
    reviewState as ReviewState,
    reviewNotes
  );

  if (!updated) {
    return NextResponse.json({ error: "Brief not found" }, { status: 404 });
  }

  return NextResponse.json({ brief: updated });
}
