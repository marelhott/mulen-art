import React from "react";
import { SlidersHorizontal, Trash2 } from "lucide-react";
import { Progress } from "./Progress";
import { IconButton, Label, Range, Select } from "./controls";

// Right-hand panel: job progress, generation settings, saved presets and the activity log.
export function SettingsPanel({ p, isAtelier, updateAtelier, progressState }) {
  return (
  <aside className="right-panel control-panel">
    <Progress
      progress={progressState.progressValue}
      job={progressState.job}
      generating={p.isGenerating}
      startedAt={p.startedAt}
      ready={progressState.readyCount}
      total={progressState.outputCount}
      submitting={p.isSubmitting}
      submitted={progressState.submittedOutputs}
      planned={progressState.plannedOutputs}
      onCancel={p.handleCancel}
    />
    <div className="settings-heading">
      <SlidersHorizontal size={13} />
      <Label>NASTAVENÍ GENEROVÁNÍ</Label>
    </div>
    <p className="engine-hint">{(() => {
      const a = isAtelier ? p.atelier : { useRealEsrgan: p.useRealEsrgan, useRealsrgan: p.useRealsrgan, restormerMode: p.restormerMode };
      const method = a.useRealEsrgan ? "Real-ESRGAN" : a.useRealsrgan ? "SwinIR" : "";
      const finish = method ? `Hotový výsledek se zvětšuje pomocí ${method} (AI)` : "Hotový výsledek se zvětšuje pouze interpolací Lanczos, bez AI dokreslování";
      const restore = a.restormerMode && a.restormerMode !== "off" ? " a před zvětšením se opraví rozmazání (Restormer)" : "";
      return isAtelier
        ? `Ateliér tvoří nové obrazy. ${finish}${restore}. Každý checkpoint tvoří nezávisle. Foto a archiv používají naučený token modelu a plný počet kroků přemalování.`
        : `Původní generování v jednom průchodu. ${finish}${restore}.`;
    })()}</p>
    {(!isAtelier || ["photo", "archive"].includes(p.atelier.mode)) && <Range
      label={isAtelier ? "SÍLA PŘEMALOVÁNÍ" : "DENOISE"}
      min={0.05}
      max={isAtelier ? 0.99 : 1}
      step={0.01}
      value={isAtelier ? p.atelier.denoise : p.denoise}
      onChange={value => isAtelier ? updateAtelier({denoise: value}) : p.setDenoise(value)}
      hint={isAtelier ? "Výchozí 0,82: výrazné přemalování · nízké hodnoty zachovají fotografii či původní obraz · velmi vysoké mění i kompozici" : "Méně zachová předlohu · více ji promění"}
    />}
    <Range
      label="CFG"
      min={0.5}
      max={20}
      step={0.1}
      value={isAtelier ? p.atelier.cfg : p.cfg}
      onChange={value => isAtelier ? updateAtelier({cfg: value}) : p.setCfg(value)}
    />
    <Range
      label="KROKY"
      min={1}
      max={80}
      step={1}
      value={isAtelier ? p.atelier.steps : p.steps}
      onChange={value => isAtelier ? updateAtelier({steps: value}) : p.setSteps(value)}
    />
    <Select label="SAMPLER" value={isAtelier ? p.atelier.sampler : p.engine.sampler}
      onChange={(sampler) => isAtelier ? updateAtelier({sampler, schedule: ["euler_a","ddim"].includes(sampler) ? "normal" : p.atelier.schedule}) : p.setEngine((e)=>({...e, sampler, schedule: ["euler_a","ddim"].includes(sampler) ? "normal" : e.schedule}))}
      items={[{id:"dpmpp_2m",name:"DPM++ 2M"},{id:"dpmpp_2m_sde",name:"DPM++ 2M SDE"},{id:"euler_a",name:"Euler a"},{id:"ddim",name:"DDIM"}]} />
    {["dpmpp_2m", "dpmpp_2m_sde"].includes(isAtelier ? p.atelier.sampler : p.engine.sampler) && <Select label="ROZVRH ŠUMU" value={isAtelier ? p.atelier.schedule : p.engine.schedule}
      onChange={(schedule)=>isAtelier ? updateAtelier({schedule}) : p.setEngine((e)=>({...e,schedule}))}
      items={[{id:"karras",name:"Karras"},{id:"normal",name:"Normal"}]} />}
    <label className="control-block engine-field"><Label>SEED · −1 = NÁHODNÝ</Label>
      <input aria-label="Seed" type="number" min="-1" max="4294967295" step="1" value={isAtelier ? p.atelier.seed : p.engine.seed}
        onChange={(event)=>isAtelier ? updateAtelier({seed:event.target.value}) : p.setEngine((e)=>({...e,seed:event.target.value}))} />
    </label>
    <section className="control-block preset-block">
      <Label>ULOŽENÁ NASTAVENÍ</Label>
      <select
        aria-label="Uložená nastavení"
        value={p.selectedPresetId}
        onChange={p.handlePresetSelect}
      >
        <option value="">Vybrat nastavení</option>
        {p.presets.map((item) => (
          <option key={item.id} value={item.id}>
            {item.name}
          </option>
        ))}
      </select>
      <input
        aria-label="Název nastavení"
        value={p.presetName}
        onChange={(event) => p.setPresetName(event.target.value)}
        placeholder="Název nastavení"
      />
      <div className="preset-actions">
        <button className="toolbar-button" onClick={p.handleSavePreset}>
          ULOŽIT
        </button>
        <IconButton
          label="Odstranit nastavení"
          disabled={!p.selectedPresetId}
          onClick={p.handleDeletePreset}
        >
          <Trash2 />
        </IconButton>
      </div>
    </section>
    <details className="activity-log">
      <summary>
        PRŮBĚH ÚLOH <span>{p.visibleLogs.length}</span>
      </summary>
      {p.visibleLogs.length ? (
        p.visibleLogs.map((entry, index) => (
          <div key={index}>
            <time>
              {new Date(entry.timestamp).toLocaleTimeString("cs-CZ")}
            </time>
            <span>{entry.message}</span>
          </div>
        ))
      ) : (
        <p>Žádná aktivní úloha</p>
      )}
    </details>

    <div className="cloud-note">
      <span className="online-dot" />
      <p>
        Výpočty běží na Modalu.
        <br />
        GPU se po nečinnosti vypíná.
        {p.usageText && (<><br /><span className="usage-text">{p.usageText}</span></>)}
      </p>
    </div>
  </aside>
  );
}
