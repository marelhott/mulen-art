import { NextRequest, NextResponse } from "next/server";
import { readGalleryImage } from "@/lib/storage";

export async function GET(req: NextRequest) {
  try {
    const key = req.nextUrl.searchParams.get("key");

    if (!key) {
      return NextResponse.json({ error: "Missing key." }, { status: 400 });
    }

    const image = await readGalleryImage(key);

    return new NextResponse(image.body, {
      headers: {
        "Content-Type": image.contentType,
        "Cache-Control": "public, max-age=31536000, immutable",
      },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Obrázek se nepodařilo načíst.";
    return NextResponse.json({ error: message }, { status: 404 });
  }
}

export const dynamic = "force-dynamic";
