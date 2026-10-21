import React, { useEffect, useState } from "react";
import {
  Clock3,
} from "lucide-react";
import { duration } from "../shared";
import { Label } from "./controls";

export function Progress({
  progress,
  job,
  generating,
  startedAt,
  ready,
  total,
  submitting,
  submitted,
  planned,
  onCancel,
}) {
  const [elapsed, setElapsed] = useState(0);
  const effectiveStart =
    startedAt || (job.started_at ? Date.parse(job.started_at) : null);
  const finishedDuration =
    job.finished_at && job.started_at
      ? (Date.parse(job.finished_at) - Date.parse(job.started_at)) / 1000
      : null;
  const shownElapsed =
    job.status === "idle"
      ? 0
      : !generating && finishedDuration !== null
        ? finishedDuration
        : elapsed;
  useEffect(() => {
    if (!generating || !effectiveStart) return;
    const tick = () =>
      setElapsed(Math.max(0, (Date.now() - effectiveStart) / 1000));
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [generating, effectiveStart]);
  return (
    <section className={`progress-card ${generating ? "is-active" : ""}`}>
      <div className="progress-heading">
        <div>
          <Label>
            {submitting
              ? "ODESÍLÁNÍ DÁVKY"
              : generating
                ? job.status === "idle"
                  ? "OBNOVUJI DÁVKU"
                  : "GENERUJI OBRÁZKY"
                : job.status === "completed"
                  ? "DOKONČENO"
                  : job.status === "cancelled"
                    ? "ZRUŠENO"
                    : job.status === "failed"
                    ? "ÚLOHA PŘERUŠENA"
                    : "PŘIPRAVENO TVOŘIT"}
          </Label>
          <p>
            {generating || job.status !== "idle"
              ? `${ready} / ${total} obrázků hotovo`
              : "Cloudové studio · SDXL"}
          </p>
        </div>
        <strong>
          {progress}
          <small>%</small>
        </strong>
      </div>
      <div className="sampling-progress" aria-label="Průběh výpočtových kroků">
        <Label>VÝPOČTOVÉ KROKY</Label>
        {job.active_steps?.length ? job.active_steps.map((step, index) => {
          const percent = Math.round(step.current / step.total * 100);
          return <div className="sampling-job" key={step.id}>
            <div className="sampling-count"><span>{job.active_steps.length > 1 ? `GPU ${index + 1} · ` : ""}{step.current} / {step.total} kroků</span><strong>{percent}%</strong></div>
            <div className="sampling-track" role="progressbar" aria-label={`Výpočtové kroky úlohy ${index + 1}`} aria-valuenow={step.current} aria-valuemax={step.total} aria-valuemin={0}>
              <div style={{width: `${percent}%`}} />
            </div>
          </div>;
        }) : <p className="sampling-wait">{generating ? "Čekání na výpočet · načítání GPU" : job.status === "completed" ? "Výpočet dokončen" : "Kroky se zobrazí při generování"}</p>}
      </div>
      <Label>CELKOVÝ POSTUP FRONTY</Label>
      <div
        className="progress-track"
        role="progressbar"
        aria-label="Průběh generování"
        aria-valuenow={progress}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div style={{ width: `${progress}%` }} />
      </div>
      <div className="progress-foot">
        <span>
          <Clock3 size={11} />
          {duration(shownElapsed)}
        </span>
        <span>
          {submitting
            ? `Ve frontě ${submitted} / ${planned}`
            : generating
              ? "GPU / fronta"
              : job.status === "completed"
                ? "Vše uloženo"
                : "Připraveno"}
        </span>
      </div>
      {generating && (
        <p className="progress-status" role="status">
          {job.message}
        </p>
      )}
      {generating && !submitting && onCancel && (
        <button type="button" className="progress-cancel" onClick={onCancel}>
          Zrušit zbývající úlohy
        </button>
      )}
    </section>
  );
}
