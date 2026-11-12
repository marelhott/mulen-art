import React, {useEffect, useState} from "react";
import {
  Check,
  Sparkles,
} from "lucide-react";
import { Label, Range, Select } from "./controls";
import { CheckpointPicker } from "./CheckpointPicker";
import { idsForSource } from "../studioTools";
import { API_URL } from "../api";

function AtelierPhotoPicker({atelier, update}) {
  const collection = atelier.photoCollection || "malba";
  const [page, setPage] = useState({items: [], count: 0, has_more: false});
  const [status, setStatus] = useState("loading");
  const [selectedSize, setSelectedSize] = useState(null);
  useEffect(() => {
    setSelectedSize(null);
    if (!atelier.photoId) return;
    const image = new window.Image();
    image.onload = () => setSelectedSize({width: image.naturalWidth, height: image.naturalHeight});
    image.src = `${API_URL}/atelier-photo/${atelier.photoId}`;
    return () => { image.onload = null; };
  }, [atelier.photoId]);
  useEffect(() => {
    let cancelled = false;
    setStatus("loading");
    fetch(`${API_URL}/api/atelier/photos?collection=${collection}&offset=0&limit=48`, {cache: "no-store"})
      .then(response => response.ok ? response.json() : response.json().then(data => Promise.reject(new Error(data.detail || "Fotky se nepodařilo načíst."))))
      .then(data => {if (!cancelled) {setPage(data); setStatus("ready");}})
      .catch(error => {if (!cancelled) {setStatus(error.message || "Fotky se nepodařilo načíst."); setPage({items: [], count: 0, has_more: false});}});
    return () => {cancelled = true;};
  }, [collection]);
  async function loadMore() {
    setStatus("loading-more");
    try {
      const response = await fetch(`${API_URL}/api/atelier/photos?collection=${collection}&offset=${page.items.length}&limit=48`, {cache: "no-store"});
      if (!response.ok) throw new Error("Další fotky se nepodařilo načíst.");
      const next = await response.json();
      setPage(current => ({...next, items: [...current.items, ...next.items]})); setStatus("ready");
    } catch (error) {setStatus(error.message);}
  }
  const selected = atelier.photoId || "";
  return <div className="atelier-photo-picker">
    <div className="atelier-photo-collections" role="group" aria-label="Kolekce fotek">
      {[{id:"malba", label:"Malba"}, {id:"artists", label:"Artists"}].map(item => <button key={item.id} className="text-button" aria-pressed={collection === item.id}
        onClick={() => update({photoCollection: item.id, photoId: ""})}>{item.label}</button>)}
      <button className="text-button" aria-pressed={!selected} onClick={() => update({photoId: ""})}>Náhodná z alba</button>
    </div>
    <p className="help-text">{status === "loading" ? "Načítám náhledy…" : typeof status === "string" && status !== "ready" && status !== "loading-more" ? status : `${page.count} fotek · ${selected ? "vybraná fotka se použije pro všechny zvolené modely" : "náhodná fotka se vybírá samostatně pro každou studii"}`}</p>
    {selectedSize && (() => {
      const longest = Math.max(selectedSize.width, selectedSize.height);
      const automatic = longest < 1000 ? 1016 / longest : 1;
      const sizeFor = cap => {
        const factor = Math.min(automatic * (atelier.inputScale ?? 1), cap / longest);
        return `${Math.max(64, Math.floor(selectedSize.width * factor / 8) * 8)} × ${Math.max(64, Math.floor(selectedSize.height * factor / 8) * 8)}`;
      };
      const target = atelier.ratio === "random" ? `${sizeFor(1024)} nebo ${sizeFor(1216)} podle vylosovaného formátu` : sizeFor(Math.max(atelier.width, atelier.height, 1008));
      return <p className="help-text">Předloha {selectedSize.width} × {selectedSize.height} → pro model {target} px · dodatečně {(atelier.inputScale ?? 1).toFixed(2)}×</p>;
    })()}
    {page.items.length > 0 && <div className="atelier-photo-grid">
      {page.items.map(item => <button key={item.id} className="atelier-photo-thumb" aria-pressed={selected === item.id}
        title={`${item.album || "Photos"} · ${item.filename}`} onClick={() => update({photoId: item.id})}>
        <img src={`${API_URL}${item.thumbnail_url}`} alt={`${item.album || "Photos"}: ${item.filename}`} loading="lazy" />
      </button>)}
    </div>}
    {page.has_more && <button className="text-button" disabled={status === "loading-more"} onClick={loadMore}>{status === "loading-more" ? "Načítám…" : "Načíst dalších 48"}</button>}
    {page.count === 0 && status === "ready" && <p className="help-text">Kolekce je zatím prázdná. Importuj alba Photos MALBA a ARTISTS skriptem `scripts/import_atelier_photos.py` a nahraj je do Modal.</p>}
  </div>;
}

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
    {id: "subject", name: "Automatický námět", description: "Aplikace vybere náhodný námět a vytvoří obraz checkpointem. Nic nepíšeš."},
    {id: "archive", name: "Archiv → fúze", description: "Náhodný archivní obraz slouží jako předloha pro výrazné přemalování vlastním checkpointem. Bez tréninku."},
    {id: "photo", name: "Foto → malba", description: "Použij náhodnou fotografickou předlohu z generátoru, nebo vlastní fotky z Photos. Vybraný checkpoint předlohu přemaluje."},
  ];
  const source = a.source || "single";
  const activeIds = idsForSource(a.modelIds, source);
  const total = Number(a.count || 0) * activeIds.length;
  return <>
    <button className="primary-button generate" disabled={!activeIds.length || !choices.length || (a.mode === "archive" && !archives.some(item => item.id === (a.archive || "hofmann")))} onClick={onGenerate}>
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
      hint={`${a.count} studií × ${activeIds.length} modelů = ${total} výstupů`} />
    <CheckpointPicker label="CHECKPOINTY · MALÍŘSKÉ ZPRACOVÁNÍ" items={choices} selectedIds={a.modelIds}
      onChange={modelIds => update({modelIds})} source={source} onSourceChange={next => update({source: next})}
      mixCandidates={artists} onAddMix={id => onAddMix(id, "atelier")} onRemoveMix={onRemoveMix}
      hint="Každý checkpoint tvoří nezávisle: vlastní náhodný námět a seed. Výsledky se ukládají také na plátno a do knihovny." />
    {["noise", "subject"].includes(a.mode) && <Select label="BAREVNOST" value={String(a.colorLevel ?? 2)} onChange={value => update({colorLevel: Number(value)})}
      items={[{id:"2",name:"Výrazná · pestré palety malíře"},{id:"1",name:"Jako v archivu · tlumené"},{id:"0",name:"Bez úpravy · béžová z modelu"}]} />}
    {["noise", "subject"].includes(a.mode) && <p className="help-text">{(a.colorLevel ?? 2) === 0 ? "Model sám z šumu: všechny obrazy mají podobnou béžovou barevnost." : "Každá studie dostane paletu z náhodného skutečného obrazu malíře (jen barvy, ne motiv). Pokyn působí jen v prvních ~20 % kroků, tah a texturu dokončí model sám, takže styl zůstává."}</p>}
    {a.mode === "archive" && <><Select label="ZDROJOVÝ ARCHIV · OBSAH" value={a.archive || "hofmann"} onChange={archive => update({archive})} items={archives.length ? archives.map(item => ({id:item.id,name:`${item.name} · ${item.count} obrazů`})) : [{id:a.archive || "hofmann",name: archiveStatus === "loading" ? "Načítám archivy…" : "Archiv se nepodařilo načíst"}]} />{archiveStatus === "error" && <button className="text-button" onClick={reloadArchives}>Znovu načíst archivy</button>}<p className="help-text">Archiv vybírá předlohu, checkpoint určuje přemalování. Každý model vybírá vlastní náhodnou předlohu a seed. Zachovává se poměr stran; rozlišení níže je maximální rámeček.</p></>}
    {a.mode === "photo" && <>
      <Label>PŘEDLOHA FOTO → MALBA</Label>
      <div className="atelier-photo-source" role="group" aria-label="Zdroj fotografické předlohy">
        <button className="atelier-mode" aria-pressed={(a.photoSource || "generated") === "generated"} onClick={() => update({photoSource: "generated"})}><span>Náhodná předloha</span><small>Vytvoří ji SDXL Base pro každou studii.</small></button>
        <button className="atelier-mode" aria-pressed={a.photoSource === "library"} onClick={() => update({photoSource: "library"})}><span>Moje fotky · Photos</span><small>Použije fotky z alb MALBA nebo ARTISTS uložené na Modal.</small></button>
      </div>
      {a.photoSource === "library" && <AtelierPhotoPicker atelier={a} update={update} />}
    </>}
    {!["noise", "archive"].includes(a.mode) && <Select label="OKRUH NÁMĚTŮ" value={a.theme} onChange={theme => update({theme})}
      items={[{id:"all",name:"Všechny okruhy"},{id:"face",name:"Tváře a výřezy"},{id:"figure",name:"Celé dospělé postavy"},{id:"nude",name:"Dospělé akty · neexplicitní"},{id:"intimacy",name:"Intimní studie · nesexuální"},{id:"interior",name:"Interiéry"},{id:"object",name:"Předměty"},{id:"landscape",name:"Krajina a stavby"}]} />}
    {(a.mode === "archive" || (a.mode === "photo" && a.photoSource === "library")) && <Range label="DALŠÍ ZVĚTŠENÍ PŘEDLOHY" min={1} max={4} step={0.05} value={a.inputScale ?? 1} onChange={inputScale => update({inputScale})} hint="Předloha pod 1000 px se automaticky zvětší nad 1000 px; další zvětšení omezuje zvolené rozlišení modelu. Poměr stran zůstává zachován." />}
    <Select label="ROZLIŠENÍ PRO MODEL" value={a.ratio === "random" ? "random" : `${a.width}x${a.height}`} onChange={value => {if(value === "random") {update({ratio:"random"}); return;} const [width,height] = value.split("x").map(Number); update({width,height,ratio:"fixed"});}}
      items={[{id:"random",name:"Random · různé poměry stran"},{id:"1024x1024",name:"1024 × 1024 · čtverec"},{id:"832x1216",name:"832 × 1216 · na výšku"},{id:"1216x832",name:"1216 × 832 · na šířku"},{id:"1536x1536",name:"1536 × 1536 · experiment"}]} />
    <Range label="ZVĚTŠENÍ HOTOVÉHO OBRAZU" min={1} max={4} step={0.1} value={a.scale} onChange={scale => update({scale})}
      hint={a.ratio === "random" ? "Náhodné čtvercové, svislé i vodorovné formáty" : a.mode === "archive" ? `${a.scale}× · rozměry podle předlohy` : `${Math.round(a.width*a.scale)} × ${Math.round(a.height*a.scale)} px`} />
    <label className="variants-toggle realsr-toggle">
      <input type="checkbox" checked={Boolean(a.useRealsrgan)} onChange={event => update({useRealsrgan: event.target.checked, ...(event.target.checked ? {useRealEsrgan: false} : {})})} />
      <span><b>Real-SR GAN · SwinIR</b><small>Volitelné AI zvětšení a obnova detailu. Výstup zůstane ve zvoleném rozměru; přidává čas GPU.</small></span>
    </label>
    <label className="variants-toggle realsr-toggle">
      <input type="checkbox" checked={Boolean(a.useRealEsrgan)} onChange={event => update({useRealEsrgan: event.target.checked, ...(event.target.checked ? {useRealsrgan: false} : {})})} />
      <span><b>Real-ESRGAN x4plus</b><small>AI zvětšení a obnova textury. Lze kombinovat s Restormerem.</small></span>
    </label>
    <Select label="RESTORMER · ODSTRANĚNÍ ROZMAZÁNÍ" value={a.restormerMode || 'off'} onChange={restormerMode => update({restormerMode})}
      items={[{id:'off',name:'Vypnuto'},{id:'defocus',name:'Rozostření'},{id:'motion',name:'Pohybové rozmazání'}]} />
    <p className="help-text">Restormer se použije před zvětšením; obě volby prodlouží výpočet na GPU.</p>
    {["photo", "archive"].includes(a.mode) && <p className="help-text">Přemalování používá pouze naučený aktivační token checkpointu, nikoli slovní popis stylu. U modelů s tokenem je CFG nejméně 3; Hofmann používá prázdný prompt. Počet kroků znamená skutečné kroky přemalování.</p>}
    <p className="help-text">Archiv používá náhodně vybrané předlohy. Ostatní automatické náměty čerpají ze startovní sady.</p>
  </>;
}
