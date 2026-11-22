import { NextRequest, NextResponse } from "next/server";
import { deleteGalleryImage, listGalleryImages } from "@/lib/storage";

export async function GET() {
  try {
    const images = await listGalleryImages();
    return NextResponse.json({ images });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Galerii se nepodařilo načíst.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

export async function DELETE(req: NextRequest) {
  try {
    const body = await req.json();
    const url = typeof body.url === "string" ? body.url : "";
    await deleteGalleryImage(url);

    return NextResponse.json({ ok: true });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Smazání selhalo.";
    return NextResponse.json({ error: message }, { status: 400 });
  }
}

export const dynamic = "force-dynamic";
