"use client";

import { useEffect, useState } from "react";

type GalleryImage = {
  id: string;
  url: string;
  jobId: string;
  name: string;
  createdAt: string;
  size: number;
};

function formatBytes(size: number) {
  if (size < 1024 * 1024) return `${Math.max(1, Math.round(size / 1024))} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

async function readJsonResponse(response: Response) {
  const text = await response.text();
  if (!text.trim()) {
    return { error: response.ok ? null : `Server vrátil prázdnou odpověď (${response.status}).` };
  }
  try {
    return JSON.parse(text);
  } catch {
    return { error: `Server nevrátil JSON (${response.status}): ${text.slice(0, 180)}` };
  }
}

export default function GalleryPage() {
  const [images, setImages] = useState<GalleryImage[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedImage, setSelectedImage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadGallery = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/gallery", { cache: "no-store" });
      const data = await readJsonResponse(response);
      if (!response.ok || data.error) throw new Error(data.error || "Galerii se nepodařilo načíst.");
      setImages(data.images || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Galerii se nepodařilo načíst.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadGallery();
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setSelectedImage(null);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const download = async (image: GalleryImage) => {
    const response = await fetch(image.url);
    const blob = await response.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = image.name;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const remove = async (image: GalleryImage) => {
    const previous = images;
    setImages((items) => items.filter((item) => item.id !== image.id));
    const response = await fetch("/api/gallery", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: image.url }),
    });
    if (!response.ok) {
      setImages(previous);
      const data = await response.json().catch(() => ({}));
      setError(data.error || "Smazání selhalo.");
    }
  };

  return (
    <main className="min-h-screen bg-[#f2f1ed] px-4 py-5 text-[#26251e] sm:px-6">
      <div className="mx-auto flex max-w-[1600px] flex-col gap-6">
        <header className="grid gap-4 border-b border-[rgba(38,37,30,0.1)] pb-5 lg:grid-cols-[1.2fr_0.8fr] lg:items-end">
          <div className="space-y-3">
            <div className="cursor-micro text-[rgba(38,37,30,0.62)]">Archive / Generated Frames</div>
            <h1 className="cursor-display-lg text-[44px] leading-[0.96]">A warm archive of every generated branch.</h1>
          </div>
          <div className="flex flex-col gap-4 lg:items-end">
            <p className="cursor-serif max-w-[460px] text-[17px] leading-[1.45] text-[rgba(38,37,30,0.62)] lg:text-right">
              Browse output history like an editorial contact sheet. Open, compare, prune, and keep only the frames that still feel like the same world.
            </p>
            <button onClick={loadGallery} className="cursor-button w-full border px-4 py-3 text-[11px] lg:w-auto">
              obnovit galerii
            </button>
          </div>
        </header>

        {error ? <p className="text-sm text-[#cf2d56]">{error}</p> : null}

        {loading ? (
          <div className="cursor-card grid min-h-[60vh] place-items-center p-10">
            <div className="h-10 w-10 animate-spin rounded-full border border-[rgba(38,37,30,0.14)] border-t-[#f54e00]" />
          </div>
        ) : images.length ? (
          <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {images.map((image) => (
              <article key={image.id} className="cursor-card-elevated overflow-hidden">
                <button
                  onClick={() => setSelectedImage(image.url)}
                  className="flex aspect-[4/4.4] w-full items-center justify-center bg-[#ebeae5] p-3"
                  title="Klik pro zvětšení"
                >
                  <img src={image.url} alt={image.name} className="h-full w-full object-contain" />
                </button>
                <div className="border-t border-[rgba(38,37,30,0.1)] p-4">
                  <div className="cursor-micro text-[rgba(38,37,30,0.55)]">{image.jobId}</div>
                  <div className="mt-2 flex items-center justify-between gap-4">
                    <div className="cursor-serif text-[15px] text-[rgba(38,37,30,0.62)]">{formatBytes(image.size)}</div>
                    <div className="cursor-micro text-[rgba(38,37,30,0.36)]">{new Date(image.createdAt).toLocaleDateString("cs-CZ")}</div>
                  </div>
                  <div className="mt-4 grid grid-cols-2 gap-2">
                    <button onClick={() => download(image)} className="cursor-button border px-3 py-2 text-[11px]">
                      stáhnout
                    </button>
                    <button onClick={() => remove(image)} className="cursor-button border border-[rgba(207,45,86,0.2)] px-3 py-2 text-[11px] text-[#cf2d56]">
                      smazat
                    </button>
                  </div>
                </div>
              </article>
            ))}
          </section>
        ) : (
          <div className="cursor-card grid min-h-[60vh] place-items-center p-10">
            <div className="space-y-3 text-center">
              <div className="cursor-micro text-[rgba(38,37,30,0.36)]">archive empty</div>
              <div className="cursor-display text-[30px]">Galerie je zatím prázdná.</div>
            </div>
          </div>
        )}
      </div>

      {selectedImage ? (
        <div className="fixed inset-0 z-50 flex cursor-zoom-out items-center justify-center bg-[rgba(38,37,30,0.84)] p-4" onClick={() => setSelectedImage(null)}>
          <img src={selectedImage} alt="large gallery item" className="max-h-[98vh] max-w-[98vw] rounded-[10px] border border-[rgba(242,241,237,0.16)] bg-[#f2f1ed] p-2 object-contain shadow-[rgba(0,0,0,0.2)_0px_28px_70px]" />
        </div>
      ) : null}
    </main>
  );
}
