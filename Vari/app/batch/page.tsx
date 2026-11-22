"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  COMFY_DEFAULTS,
  DISTANCE_COPY,
  DISTANCE_VALUES,
  ENGINE_COPY,
  ENGINE_ORDER,
  type Distance,
  type Engine,
} from "@/lib/engines";

type BatchResult = {
  id: string;
  sourceIndex: number;
  url?: string;
  sourceName: string;
  settings: string;
  error?: string;
  pending?: boolean;
};

async function readJsonResponse(response: Response) {
  const text = await response.text();

  if (!text.trim()) {
    return {
      error: response.ok ? null : `Server vrátil prázdnou odpověď (${response.status}).`,
    };
  }

  try {
    return JSON.parse(text);
  } catch {
    return {
      error: `Server nevrátil JSON (${response.status}): ${text.slice(0, 180)}`,
    };
  }
}

export default function BatchPage() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [distance, setDistance] = useState<Distance>("sibling");
  const [engine, setEngine] = useState<Engine>("sd-variation");
  const [perImageCount, setPerImageCount] = useState(2);
  const [results, setResults] = useState<BatchResult[]>([]);
  const [selectedImage, setSelectedImage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [comfyNoise, setComfyNoise] = useState(COMFY_DEFAULTS.sibling.noise);
  const [comfyStrength, setComfyStrength] = useState(COMFY_DEFAULTS.sibling.strength);
  const [sdxlGuidance, setSdxlGuidance] = useState(3.2);
  const [sdxlStrength, setSdxlStrength] = useState(0.5);
  const [sdxlSteps, setSdxlSteps] = useState(36);
  const [zImageCreativity, setZImageCreativity] = useState(0.5);
  const [isLight, setIsLight] = useState(true);

  useEffect(() => {
    const stored = typeof window !== "undefined" ? window.localStorage.getItem("variants:theme") : null;
    if (stored === "dark") setIsLight(false);
    else if (stored === "light") setIsLight(true);
  }, []);

  useEffect(() => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem("variants:theme", isLight ? "light" : "dark");
    }
  }, [isLight]);

  const expectedOutputs = useMemo(() => files.length * perImageCount, [files.length, perImageCount]);

  const theme = {
    page: isLight ? "bg-[#f2f1ed] text-[#26251e]" : "bg-[#11100d] text-[#f2f1ed]",
    shellBorder: isLight ? "border-[rgba(38,37,30,0.1)]" : "border-[rgba(242,241,237,0.12)]",
    sidebar: isLight ? "border-[rgba(38,37,30,0.1)] bg-[#ebeae5]" : "border-[rgba(242,241,237,0.12)] bg-[#171611]",
    card: isLight ? "border-[rgba(38,37,30,0.1)] bg-[#f7f7f4]" : "border-[rgba(242,241,237,0.12)] bg-[#191812]",
    cardAlt: isLight ? "bg-[#ebeae5]" : "bg-[#1d1b16]",
    button: isLight ? "cursor-button border-[rgba(38,37,30,0.1)] bg-[#ebeae5] text-[#26251e]" : "cursor-button border-[rgba(242,241,237,0.12)] bg-[#1d1b16] text-[#f2f1ed]",
    line: isLight ? "border-[rgba(38,37,30,0.1)] text-[rgba(38,37,30,0.62)] hover:border-[rgba(38,37,30,0.2)] hover:text-[#cf2d56]" : "border-[rgba(242,241,237,0.12)] text-[rgba(242,241,237,0.62)] hover:border-[rgba(242,241,237,0.2)] hover:text-[#dfa88f]",
    selectedLine: isLight ? "border-[#26251e] text-[#26251e]" : "border-[#f2f1ed] text-[#f2f1ed]",
    quiet: isLight ? "text-[rgba(38,37,30,0.62)]" : "text-[rgba(242,241,237,0.66)]",
    quiet2: isLight ? "text-[rgba(38,37,30,0.55)]" : "text-[rgba(242,241,237,0.58)]",
    accent: isLight ? "text-[#f54e00]" : "text-[#dfa88f]",
    progressTrack: isLight ? "bg-[rgba(38,37,30,0.1)]" : "bg-[rgba(242,241,237,0.12)]",
    progressFill: isLight ? "bg-[#f54e00]" : "bg-[#dfa88f]",
    borderSoft: isLight ? "border-[rgba(38,37,30,0.1)]" : "border-[rgba(242,241,237,0.12)]",
    imageFrame: isLight ? "bg-[#ebeae5]" : "bg-[#1d1b16]",
    error: "text-[#cf2d56]",
  };

  const openPicker = () => inputRef.current?.click();

  const appendFiles = (incoming: FileList | File[]) => {
    const accepted = Array.from(incoming)
      .filter((file) => file.type.startsWith("image/"))
      .slice(0, 20);

    setFiles((current) => [...current, ...accepted].slice(0, 20));
    setResults([]);
    setError(null);
  };

  const buildSettingsLabel = () => {
    const base = `${ENGINE_COPY[engine]} / ${DISTANCE_COPY[distance]} / ${perImageCount} ks na vstup`;
    if (engine === "z-image") {
      return `${base} / kreativita ${zImageCreativity.toFixed(2)}`;
    }
    if (engine === "comfy-unclip") {
      return `${base} / noise ${comfyNoise.toFixed(2)} / strength ${comfyStrength.toFixed(2)}`;
    }
    if (engine === "sdxl-artistic") {
      return `${base} / guidance ${sdxlGuidance.toFixed(1)} / strength ${sdxlStrength.toFixed(2)} / steps ${Math.round(sdxlSteps)}`;
    }
    return base;
  };

  const updateResult = (id: string, patch: Partial<BatchResult>) => {
    setResults((current) => current.map((item) => (item.id === id ? { ...item, ...patch } : item)));
  };

  // Exponential backoff polling: 1.5s → 3s → 6s → 10s cap. 8 min budget.
  const pollReplicateJob = async (jobId: string): Promise<string[]> => {
    const startedAt = Date.now();
    const steps = [1500, 3000, 6000, 10000];
    const maxMs = 1000 * 60 * 8;
    let attempt = 0;

    while (Date.now() - startedAt < maxMs) {
      const delay = steps[Math.min(attempt, steps.length - 1)];
      attempt += 1;
      await new Promise((resolve) => window.setTimeout(resolve, delay));

      const res = await fetch(`/api/generate/status?jobId=${encodeURIComponent(jobId)}`);
      const data = await readJsonResponse(res);

      if (!res.ok || data.error) {
        throw new Error(data.error || "Kontrola stavu batch jobu selhala");
      }

      if (data.status === "succeeded") {
        return (data.images || []).map((image: { url: string }) => image.url) as string[];
      }

      if (data.status === "failed" || data.status === "canceled") {
        throw new Error(data.error || `Job skončil stavem ${data.status}`);
      }
    }

    throw new Error("Batch job trvá déle než 8 minut.");
  };

  const pollReplicateJobs = async (jobIds: string[]): Promise<string[]> => {
    const settled = await Promise.all(jobIds.map((jobId) => pollReplicateJob(jobId)));
    return settled.flat();
  };

  const runOne = async (file: File) => {
    const form = new FormData();
    form.append("image", file);
    form.append("distance", distance);
    form.append("engine", engine);
    form.append("count", String(perImageCount));
    form.append("comfyNoise", String(comfyNoise));
    form.append("comfyStrength", String(comfyStrength));
    form.append("sdxlGuidance", String(sdxlGuidance));
    form.append("sdxlStrength", String(sdxlStrength));
    form.append("sdxlSteps", String(sdxlSteps));
    form.append("zImageCreativity", String(zImageCreativity));

    const res = await fetch("/api/generate", { method: "POST", body: form });
    const data = await readJsonResponse(res);

    if (!res.ok || data.error) {
      throw new Error(data.error || "Batch generování selhalo");
    }

    const replicateJobIds = Array.isArray(data.jobIds)
      ? data.jobIds.filter((value: unknown): value is string => typeof value === "string")
      : data.jobId && data.provider === "replicate"
        ? [data.jobId]
        : [];

    if (replicateJobIds.length && data.provider === "replicate") {
      return pollReplicateJobs(replicateJobIds);
    }

    return (data.images || []) as string[];
  };

  const generateBatch = async () => {
    if (!files.length) return;

    setLoading(true);
    setError(null);
    setProgress(0);
    setStatus("připravuji dávku");

    const settings = buildSettingsLabel();
    const seeded = files.flatMap((file, fileIndex) =>
      Array.from({ length: perImageCount }, (_, outputIndex) => ({
        id: `${file.name}-${fileIndex}-${outputIndex}-${Date.now()}`,
        sourceIndex: fileIndex,
        sourceName: file.name,
        settings,
        pending: true,
      })),
    );
    setResults(seeded);

    let completed = 0;
    const total = seeded.length;

    try {
      for (let index = 0; index < files.length; index += 1) {
        const file = files[index];
        setStatus(`${index + 1}/${files.length} · ${file.name}`);

        const sourceSlotIds = seeded
          .filter((item) => item.sourceIndex === index)
          .slice(0, perImageCount)
          .map((item) => item.id);

        try {
          const urls = await runOne(file);
          sourceSlotIds.forEach((id, slotIndex) => {
            const url = urls[slotIndex];
            updateResult(id, url ? { url, pending: false } : { pending: false, error: "Model nevrátil obrázek." });
            completed += 1;
          });
        } catch (runError) {
          const message = runError instanceof Error ? runError.message : "Batch generování selhalo";
          sourceSlotIds.forEach((id) => {
            updateResult(id, { pending: false, error: message });
            completed += 1;
          });
        }

        setProgress(Math.round((completed / total) * 100));
      }

      setStatus("hotovo");
    } catch (batchError) {
      setError(batchError instanceof Error ? batchError.message : "Batch generování selhalo");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={`min-h-screen transition-colors ${theme.page}`}>
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        multiple
        className="hidden"
        onChange={(event) => event.target.files && appendFiles(event.target.files)}
      />

      <main className={`mx-auto grid min-h-screen w-full max-w-[1440px] grid-cols-1 border-x lg:grid-cols-[300px_minmax(0,1fr)] ${theme.shellBorder}`}>
        <aside className={`border-b p-4 lg:border-b-0 lg:border-r ${theme.sidebar}`}>
          <div className="flex h-full flex-col gap-4">
            <div className="space-y-3 border-b border-[rgba(38,37,30,0.1)] pb-4">
              <div className={`cursor-micro ${theme.quiet}`}>Batch / Long Runs</div>
              <h1 className="cursor-display-lg text-[32px] leading-[0.95]">Run the whole stack on multiple references.</h1>
              <p className={`cursor-serif text-[16px] leading-[1.45] ${theme.quiet}`}>
                Queue multiple source images, keep one engine profile, and let the archive build out as a warm editorial contact sheet.
              </p>
            </div>
            <div className="space-y-2">
              <button
                onClick={generateBatch}
                disabled={loading || !files.length}
                className={`w-full border px-3 py-3 text-left text-[11px] transition-colors disabled:cursor-not-allowed ${theme.button}`}
              >
                {loading ? "generuji dávku" : "spustit batch"}
              </button>
              <button
                onClick={openPicker}
                className={`w-full border px-3 py-3 text-left text-[11px] transition-colors ${theme.line}`}
              >
                přidat vstupy
              </button>
            </div>

            <div className="space-y-2">
              <div className={`flex items-center justify-between text-[10px] uppercase tracking-[0.22em] ${theme.quiet2}`}>
                <span>vstupů</span>
                <span className={theme.accent}>{files.length}/20</span>
              </div>
              <div className={`max-h-[180px] space-y-1 overflow-y-auto border p-2 ${theme.card}`}>
                {files.length ? (
                  files.map((file, index) => (
                    <div key={`${file.name}-${index}`} className={`truncate border-b py-1 text-[11px] ${theme.borderSoft} ${theme.quiet}`}>
                      {file.name}
                    </div>
                  ))
                ) : (
                  <div className={`py-8 text-center text-[11px] uppercase tracking-[0.18em] ${theme.quiet}`}>
                    zatím bez vstupů
                  </div>
                )}
              </div>
            </div>

            <div>
              <div className={`mb-2 flex items-center justify-between text-[10px] uppercase tracking-[0.22em] ${theme.quiet2}`}>
                <span>výstupů na vstup</span>
                <span className={theme.accent}>{perImageCount}</span>
              </div>
              <input
                type="range"
                min={2}
                max={4}
                step={1}
                value={perImageCount}
                onChange={(event) => setPerImageCount(Number(event.target.value))}
                className="w-full"
              />
              <div className={`mt-2 text-[11px] ${theme.quiet}`}>
                celkem přibližně {expectedOutputs || 0} výstupů
              </div>
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between gap-2">
                <span className={`block cursor-micro ${theme.quiet2}`}>model</span>
                <button
                  onClick={() => setIsLight((current) => !current)}
                  className={`border px-2 py-1 text-[10px] uppercase tracking-[0.18em] transition-colors ${theme.line}`}
                >
                  {isLight ? "dark" : "light"}
                </button>
              </div>
              {ENGINE_ORDER.map((option) => (
                <button
                  key={option}
                  onClick={() => setEngine(option)}
                  className={`w-full border-b px-0 py-2 text-left text-[12px] transition-colors ${
                    engine === option ? theme.selectedLine : theme.line
                  }`}
                >
                  {ENGINE_COPY[option]}
                </button>
              ))}
            </div>

            <div className="space-y-2">
              <span className={`block cursor-micro ${theme.quiet2}`}>volnost</span>
              {DISTANCE_VALUES.map((option) => (
                <button
                  key={option}
                  onClick={() => {
                    setDistance(option);
                    setComfyNoise(COMFY_DEFAULTS[option].noise);
                    setComfyStrength(COMFY_DEFAULTS[option].strength);
                    setSdxlGuidance(
                      option === "locked" ? 3.6 : option === "sibling" ? 3.2 : option === "looser" ? 2.9 : 2.6,
                    );
                    setSdxlStrength(
                      option === "locked" ? 0.42 : option === "sibling" ? 0.5 : option === "looser" ? 0.58 : 0.66,
                    );
                    setSdxlSteps(
                      option === "locked" ? 40 : option === "sibling" ? 36 : option === "looser" ? 32 : 28,
                    );
                    setZImageCreativity(option === "locked" ? 0.36 : option === "sibling" ? 0.5 : option === "looser" ? 0.66 : 0.8);
                  }}
                  className={`w-full border-b px-0 py-2 text-left text-[12px] transition-colors ${
                    distance === option ? theme.selectedLine : theme.line
                  }`}
                >
                  {DISTANCE_COPY[option]}
                </button>
              ))}
            </div>

            {engine === "z-image" ? (
              <div className={`space-y-3 border-t pt-3 ${theme.borderSoft}`}>
                <div>
                  <div className={`mb-2 flex items-center justify-between text-[10px] uppercase tracking-[0.18em] ${theme.quiet2}`}>
                    <span>kreativita</span>
                    <span className={theme.accent}>{zImageCreativity.toFixed(2)}</span>
                  </div>
                  <input
                    type="range"
                    min={0.2}
                    max={0.95}
                    step={0.01}
                    value={zImageCreativity}
                    onChange={(event) => setZImageCreativity(Number(event.target.value))}
                    className="w-full"
                  />
                </div>
              </div>
            ) : null}

            {engine === "comfy-unclip" ? (
              <div className={`space-y-3 border-t pt-3 ${theme.borderSoft}`}>
                <div>
                  <div className={`mb-2 flex items-center justify-between text-[10px] uppercase tracking-[0.18em] ${theme.quiet2}`}>
                    <span>noise augmentation</span>
                    <span className={theme.accent}>{comfyNoise.toFixed(2)}</span>
                  </div>
                  <input
                    type="range"
                    min={0}
                    max={0.35}
                    step={0.01}
                    value={comfyNoise}
                    onChange={(event) => setComfyNoise(Number(event.target.value))}
                    className="w-full"
                  />
                </div>
                <div>
                  <div className={`mb-2 flex items-center justify-between text-[10px] uppercase tracking-[0.18em] ${theme.quiet2}`}>
                    <span>strength</span>
                    <span className={theme.accent}>{comfyStrength.toFixed(2)}</span>
                  </div>
                  <input
                    type="range"
                    min={0.35}
                    max={1}
                    step={0.01}
                    value={comfyStrength}
                    onChange={(event) => setComfyStrength(Number(event.target.value))}
                    className="w-full"
                  />
                </div>
              </div>
            ) : null}

            {engine === "sdxl-artistic" ? (
              <div className={`space-y-3 border-t pt-3 ${theme.borderSoft}`}>
                <div>
                  <div className={`mb-2 flex items-center justify-between text-[10px] uppercase tracking-[0.18em] ${theme.quiet2}`}>
                    <span>guidance</span>
                    <span className={theme.accent}>{sdxlGuidance.toFixed(1)}</span>
                  </div>
                  <input
                    type="range"
                    min={1.5}
                    max={6}
                    step={0.1}
                    value={sdxlGuidance}
                    onChange={(event) => setSdxlGuidance(Number(event.target.value))}
                    className="w-full"
                  />
                </div>
                <div>
                  <div className={`mb-2 flex items-center justify-between text-[10px] uppercase tracking-[0.18em] ${theme.quiet2}`}>
                    <span>strength</span>
                    <span className={theme.accent}>{sdxlStrength.toFixed(2)}</span>
                  </div>
                  <input
                    type="range"
                    min={0.2}
                    max={0.9}
                    step={0.01}
                    value={sdxlStrength}
                    onChange={(event) => setSdxlStrength(Number(event.target.value))}
                    className="w-full"
                  />
                </div>
                <div>
                  <div className={`mb-2 flex items-center justify-between text-[10px] uppercase tracking-[0.18em] ${theme.quiet2}`}>
                    <span>steps</span>
                    <span className={theme.accent}>{Math.round(sdxlSteps)}</span>
                  </div>
                  <input
                    type="range"
                    min={20}
                    max={60}
                    step={1}
                    value={sdxlSteps}
                    onChange={(event) => setSdxlSteps(Number(event.target.value))}
                    className="w-full"
                  />
                </div>
              </div>
            ) : null}

            {error ? <div className={`text-sm ${theme.error}`}>{error}</div> : null}

            <a
              href="/"
              className={`mt-auto block border px-4 py-3 text-center text-[10px] uppercase tracking-[0.24em] transition-colors ${theme.line}`}
            >
              zpět na hlavní režim
            </a>
          </div>
        </aside>

        <section className="flex min-h-screen flex-col gap-4 p-4">
          <div className="space-y-2">
            <div className={`flex items-center justify-between text-[10px] uppercase tracking-[0.24em] ${theme.quiet}`}>
              <span>{status || "dlouhý batch režim"}</span>
              <span>{loading ? `${progress}%` : `${results.length}/${expectedOutputs || 0}`}</span>
            </div>
            <div className={`h-1 w-full overflow-hidden ${theme.progressTrack}`}>
              <div className={`h-full transition-all duration-500 ${theme.progressFill}`} style={{ width: `${progress}%` }} />
            </div>
          </div>

          <div className="grid max-h-[calc(100vh-120px)] min-h-0 flex-1 grid-cols-2 gap-2 overflow-y-auto pr-1 sm:grid-cols-3 xl:grid-cols-5 2xl:grid-cols-6">
            {results.map((result) => (
              <button
                key={result.id}
                onClick={() => result.url && setSelectedImage(result.url)}
                className={`group relative overflow-hidden border text-left ${theme.card}`}
                disabled={!result.url}
                title={result.url ? "Klik pro zvětšení" : result.error || "čeká"}
              >
                {result.url ? (
                  <>
                    <div className={`flex min-h-[180px] items-center justify-center p-2 ${theme.imageFrame}`}>
                      <img
                        src={result.url}
                        alt={result.sourceName}
                        className="max-h-[220px] w-full object-contain transition-transform duration-300 group-hover:scale-[1.02]"
                      />
                    </div>
                    <div className={`border-t p-2 ${theme.borderSoft} ${theme.imageFrame}`}>
                      <div className={`truncate text-[10px] uppercase tracking-[0.16em] ${isLight ? "text-[#2b2114]" : "text-[#f0debb]"}`}>
                        {result.sourceName}
                      </div>
                      <div className={`line-clamp-2 text-[10px] ${theme.quiet}`}>{result.settings}</div>
                    </div>
                  </>
                ) : result.error ? (
                  <div className="flex min-h-[220px] flex-col justify-between p-2">
                    <div className={`truncate text-[10px] uppercase tracking-[0.16em] ${theme.quiet}`}>{result.sourceName}</div>
                    <div className={`text-[11px] uppercase tracking-[0.14em] ${theme.error}`}>selhalo</div>
                    <div className={`text-[10px] leading-4 ${theme.quiet}`}>{result.error}</div>
                  </div>
                ) : (
                  <div className="flex min-h-[220px] flex-col items-center justify-center gap-3">
                    <div className="relative h-10 w-10">
                      <div className={`absolute inset-0 rounded-full border ${isLight ? "border-[#b7aa96]" : "border-[#2f2b25]"}`} />
                      <div className={`absolute inset-0 animate-spin rounded-full border border-transparent ${isLight ? "border-t-[#8b6f3d]" : "border-t-[#d8c39a]"}`} />
                      <div className={`absolute inset-3 rounded-full ${theme.cardAlt}`} />
                    </div>
                    <div className={`px-3 text-center text-[10px] uppercase tracking-[0.16em] ${theme.quiet}`}>
                      {result.sourceName}
                    </div>
                  </div>
                )}
              </button>
            ))}
          </div>
        </section>
      </main>

      {selectedImage ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black p-2" onClick={() => setSelectedImage(null)}>
          <img src={selectedImage} alt="batch preview" className="max-h-[98vh] max-w-[98vw] object-contain" />
        </div>
      ) : null}
    </div>
  );
}
