import { NextRequest, NextResponse } from "next/server";
import { saveRemoteImage } from "@/lib/storage";
import { getReplicatePrediction } from "@/lib/providers/replicate";

export async function GET(req: NextRequest) {
  const jobId = req.nextUrl.searchParams.get("jobId");
  const limit = Math.max(1, Number(req.nextUrl.searchParams.get("limit") || 999));
  if (!jobId) {
    return NextResponse.json({ error: "Missing jobId." }, { status: 400 });
  }

  try {
    const prediction = await getReplicatePrediction(jobId, { signal: req.signal });

    const output = Array.isArray(prediction.output)
      ? prediction.output
      : prediction.output
        ? [prediction.output]
        : [];
    const remoteUrls = output
      .filter((url: unknown): url is string => typeof url === "string")
      .slice(0, limit);

    const localUrls =
      prediction.status === "succeeded"
        ? await Promise.all(
            remoteUrls.map((url, index) => saveRemoteImage(url, jobId, index)),
          )
        : remoteUrls;

    return NextResponse.json({
      id: prediction.id,
      status: prediction.status,
      error:
        prediction.error ||
        (prediction.status === "failed" ? prediction.logs : null),
      logs: prediction.logs,
      images: localUrls.map((url) => ({ url })),
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Replicate status failed.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
