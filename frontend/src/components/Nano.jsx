import React from "react";
import { Layers3, Combine } from "lucide-react";
import { Label, Range, Select } from "./controls";
import { GLITCH_OPS, GLITCH_UNTIL, glitchOp } from "../glitchTools";
import { COLLAGE_MAX_SOURCES, VARI_CHAINS, NANO_DISTANCES, NANO_MAX_PER_MODEL, clampCount, forCollage, isFused, takesImages, usableModels } from "../nanoTools";

// Model picker shared by Vari and Koláž: a model whose provider key is missing is shown but cannot be chosen, with the reason.
export function ModelPicker({models, value, update}) {
  const toggle = id => update({models: value.includes(id) ? value.filter(item => item !== id) : [...value, id]});
  const usable = usableModels(value, models).length;
  return <div className="control-block">
    <div className="label-row"><Label>MODELY</Label><span>{usable}</span></div>
    <div className="nano-models" role="group" aria-label="Modely">
      {models.map(model => <button key={model.id} type="button" className="nano-model" aria-pressed={value.includes(model.id) && model.available && takesImages(model)}
        disabled={!model.available || !takesImages(model)} onClick={() => toggle(model.id)}
        title={!takesImages(model) ? "Generuje jen z textu, z obrázku sourozence ani koláž neudělá" : model.available ? model.model : `Chybí ${model.missing} (nastav v Modalu v secretu nano-keys)`}>
        <b>{model.title}</b>
        <small>{!takesImages(model) ? "jen text" : model.available ? (model.min_inputs > 0 ? "editor" : "generátor") : "chybí klíč"}</small>
      </button>)}
    </div>
    {!models.length && <span className="help-text">Seznam modelů se načítá.</span>}
  </div>;
}

function PromptField({value, update, placeholder, hint}) {
  return <label className="control-block">
    <Label>VLASTNÍ PROMPT (VOLITELNÉ)</Label>
    <textarea aria-label="Vlastní prompt" rows={3} value={value} placeholder={placeholder} onChange={event => update({prompt: event.target.value})} />
    {hint && <span className="help-text">{hint}</span>}
  </label>;
}

function CountField({value, update, label, hint}) {
  const count = clampCount(value);
  return <div className="control-block">
    <div className="label-row"><Label>{label}</Label><span>{count}</span></div>
    <div className="segmented" role="group" aria-label={label}>
      {Array.from({length: NANO_MAX_PER_MODEL}, (_, index) => index + 1).map(n =>
        <button key={n} aria-pressed={count === n} onClick={() => update({count: n})}>{n}</button>)}
    </div>
    {hint && <span className="help-text">{hint}</span>}
  </div>;
}

export function VariControls({value, update, models, inputCount, generating, onGenerate, inputBlock, showModels = true}) {
  const picked = usableModels(value.models, models).length;
  const count = clampCount(value.count);
  const total = inputCount * picked * count;
  const distance = NANO_DISTANCES.find(item => item.id === value.distance) || NANO_DISTANCES[1];
  return <>
    <button className="primary-button generate" disabled={!inputCount || !picked} onClick={onGenerate}>
      <Layers3 size={16} />{generating ? "PŘIDAT DO FRONTY" : "VYTVOŘIT VARIANTY"}
    </button>
    {inputBlock}
    {showModels && <ModelPicker models={models} value={value.models} update={update} />}
    <div className="control-block">
      <Label>VZDÁLENOST OD PŘEDLOHY</Label>
      <div className="segmented" role="group" aria-label="Vzdálenost od předlohy">
        {NANO_DISTANCES.map(item => <button key={item.id} aria-pressed={value.distance === item.id} onClick={() => update({distance: item.id})}>{item.name}</button>)}
      </div>
      <span className="help-text">{distance.hint}</span>
    </div>
    <div className="control-block">
      <Label>NEJDŘÍV UNCLIP</Label>
      <div className="segmented" role="group" aria-label="Nejdřív unCLIP">
        {VARI_CHAINS.map(item => <button key={item.id || "off"} aria-pressed={(value.chain || "") === item.id} onClick={() => update({chain: item.id})}>{item.name}</button>)}
      </div>
      <span className="help-text">{value.chain ? "Obrázek se nejdřív přepíše modelem unCLIP na GPU (každá varianta zvlášť), z toho vznikne výsledek. Zdroj se víc rozbije, trvá to déle." : "Volitelný mezikrok: nejdřív přepsat obraz unCLIPem, pak teprve Posun."}</span>
    </div>
    {value.chain && <div className="control-block">
      <Select label="ROZPAD UNCLIPU" value={value.glitch || ""} onChange={glitch => update({glitch})} items={GLITCH_OPS.map(item => ({id: item.id, name: item.name}))} />
      <span className="help-text">{value.glitch ? glitchOp(value.glitch).hint + " Týká se jen unCLIP mezikroku; modely Nano Pro a Gemini se rozbít nedají." : "Volitelné: unCLIP se v prvních krocích záměrně poškodí, než ho zdravý model dokončí."}</span>
      {value.glitch && <Range label="ROZPAD · PRVNÍCH % KROKŮ" min={GLITCH_UNTIL.min} max={GLITCH_UNTIL.max} step={GLITCH_UNTIL.step} value={value.glitchUntil ?? GLITCH_UNTIL.default}
        onChange={glitchUntil => update({glitchUntil})} hint={`${Math.round((value.glitchUntil ?? GLITCH_UNTIL.default) * 100)} % kroků je poškozených`} />}
    </div>}
    <CountField value={value.count} update={update} label="POČET NA MODEL A OBRÁZEK"
      hint={!inputCount ? "Přidej obrázek, ze kterého se varianty odvodí." : !picked ? "Vyber alespoň jeden model." : `${inputCount} × ${picked} × ${count} = ${total} obrázků`} />
    <PromptField value={value.prompt} update={update} placeholder="Prázdné = ověřený prompt pro zvolenou vzdálenost" hint="Vlastní prompt se pošle tak, jak je (u Blíž až Divně se k němu přidá jedna věta o vzdálenosti)." />
    <p className="help-text">Modely z Mulen Nano přes OpenRouter a Venice. Qwen dostane místo obecného promptu krátký pokyn, jiný pro každou variantu.</p>
  </>;
}

export function CollageControls({value, update, models: allModels, inputCount, generating, onGenerate, inputBlock}) {
  const models = allModels.filter(forCollage);
  const picked = usableModels(value.models, models).length;
  const fused = isFused(value, inputCount);
  const count = clampCount(value.count);
  const total = fused ? picked : inputCount * picked * count;
  const tooMany = inputCount > COLLAGE_MAX_SOURCES;
  return <>
    <button className="primary-button generate" disabled={!inputCount || !picked || tooMany} onClick={onGenerate}>
      <Combine size={16} />{generating ? "PŘIDAT DO FRONTY" : "VYTVOŘIT KOLÁŽ"}
    </button>
    {inputBlock}
    {inputCount >= 2 && <div className="control-block">
      <Label>ZPRACOVÁNÍ VSTUPŮ</Label>
      <div className="segmented" role="group" aria-label="Zpracování vstupů">
        <button aria-pressed={value.fuse} onClick={() => update({fuse: true})}>Spojit do jednoho</button>
        <button aria-pressed={!value.fuse} onClick={() => update({fuse: false})}>Každý zvlášť</button>
      </div>
    </div>}
    <ModelPicker models={models} value={value.models} update={update} />
    {!fused && <CountField value={value.count} update={update} label="POČET NA MODEL A VSTUP" />}
    <PromptField value={value.prompt} update={update} placeholder="Prázdné = ověřený prompt pro splynutí" hint="Každý model dostane jiné místo vstupu a jinou techniku." />
    <p className="help-text">{tooMany ? `Nejvýš ${COLLAGE_MAX_SOURCES} vstupních obrázků.`
      : !inputCount ? "Přidej aspoň jeden obrázek."
      : !picked ? "Vyber alespoň jeden model."
      : fused ? `${inputCount} vstupů → 1 výstup × ${picked} modelů = ${total}` : `${inputCount} vstupů × ${picked} modelů × ${count} = ${total}`}</p>
  </>;
}
