import React from "react";
import {
  Check,
  Sparkles,
  X,
} from "lucide-react";
import { Label, Range, Select } from "./controls";
import { MixBuilder } from "./MixBuilder";

export function AtelierQueue({p}) {
  const counts = p.job.queue_counts || {};
  const active = p.isGenerating;
  const waiting = active && !p.isSubmitting && !(counts.running > 0);
  const failed = p.job.status === "failed";
  const done = p.job.status === "completed";
  const total = Math.max(p.outputCount, p.plannedOutputs || 0);
  const accepted = Math.max(p.submittedOutputs || 0, (counts.queued || 0) + (counts.running || 0) + (counts.completed || 0) + (counts.failed || 0));
  const title = p.isSubmitting ? "Přijímám tvoje zadání" : waiting ? "Zadání přijato · čekáme na GPU" : active ? "Ateliér právě tvoří" : failed ? "Část úloh se nepodařila" : done ? "Studie jsou hotové" : "Připraveno tvořit";
  return <section className={`atelier-queue ${active ? "is-active" : ""} ${waiting || p.isSubmitting ? "is-waiting" : ""} ${failed ? "has-error" : ""}`} aria-label="Stav fronty Ateliéru">
    <div className="atelier-queue-heading">
      <div className="atelier-queue-symbol">{active ? <Sparkles size={23} /> : <Check size={23} />}</div>
      <div className="atelier-queue-title" role="status" aria-live="polite"><span>FRONTA ATELIÉRU</span><h2>{title}</h2><p>{p.isSubmitting ? `${accepted} z ${total} výstupů potvrzeno serverem. Můžeš přidávat další zadání.` : waiting ? "Požadavky jsou uložené ve frontě. Nezadávej je znovu; výpočet začne po přidělení GPU." : active ? "Hotové obrazy se průběžně objevují níže a ukládají do knihovny." : failed ? "Podrobnosti chyby najdeš v průběhu úloh. Hotové obrazy zůstávají uložené." : done ? "Všechny úspěšné výsledky jsou na plátně a v knihovně." : "Vyber způsob tvorby a klikni na Vytvořit studie. Přijetí zadání uvidíš zde."}</p></div>
      <div className="atelier-queue-number"><strong>{active || done || failed ? p.progressValue : 0}</strong><span>%</span></div>
    </div>
    <div className="atelier-queue-track" role="progressbar" aria-label={p.isSubmitting ? "Přijetí zadání" : waiting ? "Čekání na přidělení GPU" : "Celkový průběh Ateliéru"} aria-valuemin={0} aria-valuemax={100} aria-valuenow={waiting ? undefined : p.isSubmitting ? Math.round(accepted / Math.max(total, 1) * 100) : p.progressValue} aria-valuetext={waiting ? "Zadání přijato, čekání na GPU; výpočet ještě nezačal" : undefined}>
      <div className="atelier-queue-fill" style={{width: `${p.isSubmitting ? accepted / Math.max(total, 1) * 100 : p.progressValue}%`}} />
      {(waiting || p.isSubmitting) && <div className="atelier-queue-scan" />}
    </div>
    <div className="atelier-queue-stats">
      <span><i className="queue-dot" />Přijato <b>{accepted}</b></span>
      <span>Čeká <b>{counts.queued || 0}</b></span>
      <span>Počítá se <b>{counts.running || 0}</b></span>
      <span>Hotovo <b>{p.readyCount} / {total}</b></span>
      {counts.failed > 0 && <span className="queue-failed">Chyba <b>{counts.failed}</b></span>}
    </div>
    {p.job.active_steps?.length > 0 && <div className="atelier-queue-steps">{p.job.active_steps.map((step, i) => <div key={step.id}><span>Výpočet {i + 1} · {step.current} / {step.total} kroků</span><div className="atelier-step-track"><div style={{width: `${step.current / step.total * 100}%`}} /></div></div>)}</div>}
  </section>;
}

const isArtistId = id => id.startsWith("tuymans_") || ["tuy_small", "hofmann_sdxl", "mulen_mara"].includes(id);

export function AtelierControls({atelier: a, update, models, archives = [], archiveStatus, reloadArchives, generating, onGenerate, onAddMix, onRemoveMix}) {
  const artists = models.filter(model => model.kind !== "mix" && isArtistId(model.id));
  // A mix is offered here only when every checkpoint in it is an artist checkpoint.
  const choices = models.filter(model => (model.kind === "mix" ? model.parts.every(part => isArtistId(part.id)) : isArtistId(model.id)));
  const modes = [
    {id: "noise", name: "Volná studie", description: "Nový obraz přímo z šumu. Bez námětu i bez promptu; obsah vybírá samotný checkpoint."},
    {id: "subject", name: "Automatický námět", description: "Aplikace vybere střídmý námět a vytvoří obraz checkpointem. Nic nepíšeš."},
    {id: "archive", name: "Archiv → fúze", description: "Náhodný obraz ze zdrojového archivu přemaluje libovolný zvolený checkpoint. Jeden obraz na výstup, bez tréninku."},
    {id: "photo", name: "Foto → malba", description: "SDXL Base vytvoří fotografický předobraz a vybraný checkpoint jej přemaluje. Dva průchody GPU; denoise až 0,99."},
  ];
  const total = Number(a.count || 0) * a.modelIds.length;
  return <>
    <button className="primary-button generate" disabled={!a.modelIds.length || !choices.length || (a.mode === "archive" && !archives.some(item => item.id === (a.archive || "hofmann")))} onClick={onGenerate}>
      <Sparkles size={16} />{generating ? "PŘIDAT STUDIE DO FRONTY" : "VYTVOŘIT STUDIE"}
    </button>
    <div className="control-block atelier-modes">
      <Label>ZPŮSOB TVORBY</Label>
      {modes.map(mode => <button key={mode.id} className="atelier-mode" aria-pressed={a.mode === mode.id} onClick={() => update({mode: mode.id})}>
        <span>{mode.name}</span><small>{mode.description}</small>
      </button>)}
    </div>
    <Range label="POČET STUDIÍ NA MODEL" min={1} max={10} step={1} value={a.count}
      onChange={count => update({count})}
      hint={`${a.count} studií × ${a.modelIds.length} modelů = ${total} výstupů`} />
    {a.mode === "archive" && <><Select label="ZDROJOVÝ ARCHIV · OBSAH" value={a.archive || "hofmann"} onChange={archive => update({archive})} items={archives.length ? archives.map(item => ({id:item.id,name:`${item.name} · ${item.count} obrazů`})) : [{id:a.archive || "hofmann",name: archiveStatus === "loading" ? "Načítám archivy…" : "Archiv se nepodařilo načíst"}]} />{archiveStatus === "error" && <button className="text-button" onClick={reloadArchives}>Znovu načíst archivy</button>}<p className="help-text">Archiv vybírá předlohu, checkpoint určuje přemalování. Stejná předloha i seed pro všechny modely. Zachovává se poměr stran; rozlišení níže je maximální rámeček.</p></>}
    {!["noise", "archive"].includes(a.mode) && <Select label="OKRUH NÁMĚTŮ" value={a.theme} onChange={theme => update({theme})}
      items={[{id:"all",name:"Všechny okruhy"},{id:"face",name:"Tváře a výřezy"},{id:"figure",name:"Postavy a gesta"},{id:"interior",name:"Interiéry"},{id:"object",name:"Předměty"},{id:"landscape",name:"Krajina a stavby"}]} />}
    <div className="control-block"><Label>CHECKPOINTY · MALÍŘSKÉ ZPRACOVÁNÍ</Label>
      <div className="checkpoint-options" role="group" aria-label="Modely Ateliéru">{choices.map(model => <div key={model.id} className={`checkpoint-row ${model.kind === "mix" ? "is-mix" : ""}`}>
        <button aria-pressed={a.modelIds.includes(model.id)} onClick={() => update({modelIds: a.modelIds.includes(model.id) ? (a.modelIds.length > 1 ? a.modelIds.filter(id => id !== model.id) : a.modelIds) : [...a.modelIds, model.id]})}>
          <span>{model.kind === "mix" && <i className="mix-tag">FÚZE</i>}{model.kind === "mix" ? model.name.replace(/^Fúze: /, "") : model.name}</span>{a.modelIds.includes(model.id) && <Check size={14} />}
        </button>
        {model.kind === "mix" && <button type="button" className="mix-remove" aria-label={`Odebrat fúzi ${model.name}`} title="Odebrat fúzi" onClick={() => onRemoveMix(model.id)}><X size={12} /></button>}
      </div>)}</div>
      <MixBuilder candidates={artists} onAdd={id => onAddMix(id, "atelier")} />
      <p className="help-text">Každý námět i seed se použije na všechny vybrané modely. Výsledky se ukládají také na plátno a do knihovny.</p>
    </div>
    <Select label="ROZLIŠENÍ PRO MODEL" value={a.ratio === "random" ? "random" : `${a.width}x${a.height}`} onChange={value => {if(value === "random") {update({ratio:"random"}); return;} const [width,height] = value.split("x").map(Number); update({width,height,ratio:"fixed"});}}
      items={[{id:"random",name:"Random · různé poměry stran"},{id:"1024x1024",name:"1024 × 1024 · čtverec"},{id:"832x1216",name:"832 × 1216 · na výšku"},{id:"1216x832",name:"1216 × 832 · na šířku"},{id:"1536x1536",name:"1536 × 1536 · experiment"}]} />
    <Range label="ZVĚTŠENÍ HOTOVÉHO OBRAZU" min={1} max={4} step={0.1} value={a.scale} onChange={scale => update({scale})}
      hint={a.ratio === "random" ? "Náhodné čtvercové, svislé i vodorovné formáty · bez AI zvětšování" : a.mode === "archive" ? `${a.scale}× Lanczos po přemalování · rozměry podle předlohy, bez AI dokreslení` : `${Math.round(a.width*a.scale)} × ${Math.round(a.height*a.scale)} px · pouze Lanczos, bez AI dokreslení`} />
    <p className="help-text">Archiv používá náhodně vybrané předlohy. Ostatní automatické náměty čerpají ze startovní sady.</p>
  </>;
}
