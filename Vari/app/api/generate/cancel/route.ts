import { NextRequest, NextResponse } from "next/server";
import { cancelReplicatePrediction } from "@/lib/providers/replicate";

export async function POST(req: NextRequest) {
  try {
    const { jobId, jobIds } = await req.json().catch(() => ({ jobId: null, jobIds: [] }));
    const ids = Array.isArray(jobIds)
      ? jobIds.filter((value: unknown): value is string => typeof value === "string")
      : typeof jobId === "string"
        ? [jobId]
        : [];
    if (!ids.length) {
      return NextResponse.json({ error: "Missing jobId." }, { status: 400 });
    }
    await Promise.all(ids.map((id) => cancelReplicatePrediction(id)));
    return NextResponse.json({ ok: true });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Cancel failed.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
