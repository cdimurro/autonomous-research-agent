import { NextRequest, NextResponse } from "next/server";
import { listArtifacts, readArtifact } from "@/lib/backend";

export async function GET(request: NextRequest) {
  const path = request.nextUrl.searchParams.get("path");

  if (path) {
    // Read a specific artifact
    const content = await readArtifact(path);
    if (content === null) {
      return NextResponse.json(
        { error: "Artifact not found or access denied" },
        { status: 404 }
      );
    }
    // Try to parse as JSON for structured response
    try {
      return NextResponse.json({ data: JSON.parse(content) });
    } catch {
      return NextResponse.json({ data: content });
    }
  }

  // List all artifacts
  const artifacts = await listArtifacts();
  return NextResponse.json({ artifacts });
}
