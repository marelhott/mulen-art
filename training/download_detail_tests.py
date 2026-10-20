"""Download private detail tests and prepare lossless crops and an offline gallery."""
import json,time,html,traceback
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from PIL import Image,ImageDraw
import modal
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/research/tuymans'

def build_gallery(folder):
 manifest=json.loads((folder/'manifest.json').read_text());status=json.loads((folder/'status.json').read_text());inputs=status['inputs']
 assert len(manifest)==108
 details=folder/'details';details.mkdir(exist_ok=True)
 titles={'2400':'2400 kroků','1600':'1600 kroků','800':'800 kroků','dreamlook':'Dreamlook'}
 selected={item['index']:item for item in inputs};centers={1:(.5,.3),4:(.5,.2),6:(.48,.25),7:(.52,.3),9:(.5,.3),11:(.5,.26),13:(.6,.34),14:(.45,.35),15:(.5,.38),17:(.5,.4),20:(.5,.4),21:(.5,.4)}
 for item in inputs:
  idx=item['index'];paths=[('Vstup',folder/f'input-{idx:02d}-1536.png')]+[(titles[v],folder/f'input-{idx:02d}-{v}-1536-d55.png') for v in ['dreamlook','800','1600','2400']]
  sheet=Image.new('RGB',(5*512,552),'#eceae4');draw=ImageDraw.Draw(sheet)
  for col,(title,path) in enumerate(paths):
   with Image.open(path) as raw:
    im=raw.convert('RGB');cx,cy=centers[idx];x=min(max(0,round(im.width*cx)-256),im.width-512);y=min(max(0,round(im.height*cy)-256),im.height-512)
    assert min(im.size)>=512
    crop=im.crop((x,y,x+512,y+512));crop.save(details/f'input-{idx:02d}-{col}-crop.png');sheet.paste(crop,(col*512,40))
   draw.text((col*512+10,12),title+' | 512 x 512 | 1:1',fill='#222222')
  sheet.save(details/f'input-{idx:02d}-comparison-1to1.png')
 # Compact previews are explicitly separate from the full-resolution outputs.
 for start in range(0,len(inputs),3):
  sheet=Image.new('RGB',(1500,3*345),'#eceae4');draw=ImageDraw.Draw(sheet)
  for row,item in enumerate(inputs[start:start+3]):
   idx=item['index'];paths=[('Vstup',folder/f'input-{idx:02d}-1536.png')]+[(titles[v],folder/f'input-{idx:02d}-{v}-1536-d55.png') for v in ['dreamlook','800','1600','2400']]
   for col,(title,path) in enumerate(paths):
    with Image.open(path) as raw:
     im=raw.convert('RGB');im.thumbnail((292,305));sheet.paste(im,(col*300+(300-im.width)//2,row*345+30))
    draw.text((col*300+7,row*345+7),f'{idx:02d} | '+title,fill='#222222')
  sheet.save(folder/f'overview-{start//3+1}.jpg',quality=93)
 sections=[]
 for item in inputs:
  idx=item['index'];cards=[]
  for title,file in [('Vstup připravený pro generování',f'input-{idx:02d}-1536.png')]+[(titles[v],f'input-{idx:02d}-{v}-1536-d55.png') for v in ['dreamlook','800','1600','2400']]:
   cards.append(f'<figure><a href="{file}" target="_blank"><img loading="lazy" src="{file}"></a><figcaption>{title}<br><a href="{file}" target="_blank">Plné PNG</a></figcaption></figure>')
  links=' · '.join(f'<a href="input-{idx:02d}-{v}-1536-d50.png" target="_blank">{titles[v]} / 0,50</a>' for v in ['800','1600','2400'])
  controls=' · '.join(f'<a href="input-{idx:02d}-{v}-1024-d55.png" target="_blank">{titles[v]} / 1024 px</a>' for v in ['800','2400'])
  sections.append(f'<section><h2>Vstup {idx:02d}: {html.escape(item["label"])}</h2><div class="grid">'+''.join(cards)+f'</div><p><a href="details/input-{idx:02d}-comparison-1to1.png" target="_blank">Otevřít nezmenšené výřezy 1:1 — 2560 × 552 px</a> · <a href="input-{idx:02d}-original.png" target="_blank">Původní vstup</a></p><p>Denoise 0,50: {links}</p><p>Kontrola při 1024 px: {controls}</p></section>')
 page='''<!doctype html><html lang="cs"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Tuymans — detailní testy</title><style>body{background:#151713;color:#e7e8dc;font:16px system-ui;margin:0;padding:36px}h1{font-size:32px}p{line-height:1.6;color:#bfc4b2}a{color:#c9dca4}section{padding:28px 0;border-top:1px solid #444a3c}.grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:14px}figure{margin:0}img{width:100%;height:320px;object-fit:contain;background:#10120f}figcaption{padding:8px 0;font-size:14px}@media(max-width:900px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}</style><h1>Tuymans — detailní testy</h1><p>108 výstupů na 12 nových vstupech. Bez promptů, CFG 0,5, 28 nastavených kroků, seed 231020. Hlavní srovnání níže: denoise 0,55 a generování při delší straně 1536 px. Kliknutí otevře samostatné PNG, které lze v prohlížeči prohlížet ve skutečné velikosti. Přehledové miniatury nejsou určeny pro hodnocení struktury.</p><p>Výřezy mají 512 × 512 původních výstupních pixelů, bez resamplingu. Žádné následné AI zvětšování nebo doostřování. Menší vstupy byly před generováním běžně převzorkovány Lanczosem; to nevytváří skutečné zdrojové detaily. Větší diffusion canvas může změnit styl i kompozici, proto jsou přiložené kontroly 1024 px.</p>'''+''.join(sections)+'</html>'
 viewer="""<style>#detailviewer{background:#10120f;color:#e7e8dc;border:1px solid #515a45;width:96vw;height:94vh;max-width:none;max-height:none;padding:0}#detailviewer::backdrop{background:#000d}#detailviewer .bar{position:sticky;top:0;z-index:2;background:#171b14;padding:12px;display:flex;gap:14px;align-items:center}#detailviewer .pixels{height:calc(100% - 55px);overflow:auto}#detailviewer img{width:auto;height:auto;max-width:none;object-fit:initial;display:block}button{cursor:pointer;padding:8px 14px;background:#c9dca4;color:#17200f;border:0;border-radius:6px}</style><dialog id="detailviewer"><div class="bar"><button id="closeview">Zavřít</button><span id="sizelabel"></span><input id="zoomview" type="range" min="25" max="200" value="100"><span id="zoomlabel">100 % — 1:1</span><a id="savepng" download>Stáhnout PNG</a></div><div class="pixels"><img id="largeimage" alt="Detail v plném rozlišení"></div></dialog><script>const dialog=document.getElementById('detailviewer'),large=document.getElementById('largeimage'),zoom=document.getElementById('zoomview');document.querySelectorAll('a[href$=".png"]').forEach(link=>link.addEventListener('click',e=>{if(e.metaKey||e.ctrlKey||e.shiftKey)return;e.preventDefault();zoom.value=100;large.style.width='auto';large.src=link.getAttribute('href');document.getElementById('savepng').href=large.src;document.getElementById('zoomlabel').textContent='100 % — 1:1';large.onload=()=>{document.getElementById('sizelabel').textContent=large.naturalWidth+' × '+large.naturalHeight+' px';};dialog.showModal();}));document.getElementById('closeview').onclick=()=>dialog.close();large.onclick=()=>dialog.close();zoom.oninput=()=>{large.style.width=Math.round(large.naturalWidth*zoom.value/100)+'px';document.getElementById('zoomlabel').textContent=zoom.value+' %'+(zoom.value==100?' — 1:1':'');};</script>"""
 page=page.replace('</html>',viewer+'</html>')
 (folder/'index.html').write_text(page)
 (folder/'README.md').write_text('# Detailní testy\n\n108 PNG výstupů, 12 nových vstupů, checkpointy 800 / 1600 / 2400 a Dreamlook. Prázdné prompty, CFG 0,5, 28 kroků, denoise 0,50 / 0,55, seed 231020. Výstupy při delší straně 1536 px a kontrolní 1024 px. Bez AI postprocessingu. Výřezy 512 × 512 v details/ jsou bez změny pixelů. Galerie index.html odkazuje na plná PNG. Autorství tréninkových dat není testovacími vstupy změněno; tyto obrázky se nepoužívají k učení.\n')

def main():
 active=json.loads((OUT/'detail-tests-active.json').read_text());run=active['run_id'];folder=OUT/run;folder.mkdir(exist_ok=True);volume=modal.Volume.from_name('mulen-training-results');deadline=time.monotonic()+7200
 state={'run_id':run,'phase':'waiting_for_generation'}
 def save(): (folder/'download-status.json').write_text(json.dumps(state,indent=2))
 save();errors=0
 def download(entry):
  path=folder/Path(entry.path).name
  if path.exists() and path.stat().st_size==entry.size:return
  temp=path.with_suffix(path.suffix+'.part')
  with temp.open('wb') as f:
   for chunk in volume.read_file(entry.path):f.write(chunk)
  if temp.stat().st_size!=entry.size:raise ValueError('Incomplete download')
  if path.suffix=='.png':
   with Image.open(temp) as im:im.verify()
  temp.replace(path)
 while time.monotonic()<deadline:
  try:status=json.loads(b''.join(volume.read_file(run+'/status.json')));errors=0
  except Exception:
   errors+=1
   if errors>30:raise
   time.sleep(10);continue
  (folder/'status.json').write_text(json.dumps(status,indent=2));state.update(generated=status['completed_outputs'],cloud_phase=status['phase']);save()
  if status['completed_outputs']==0 and status['phase']!='completed':
   time.sleep(20);continue
  listing=list(volume.iterdir(run,recursive=False));names={Path(x.path).name for x in listing}
  entries=[x for x in listing if Path(x.path).suffix in {'.png','.json'} and Path(x.path).name!='status.json' and (Path(x.path).suffix!='.png' or '-original.png' in x.path or Path(x.path).stem.endswith(('-1024','-1536')) or Path(x.path).stem+'.json' in names)]
  with ThreadPoolExecutor(6) as pool:list(pool.map(download,entries))
  if status['phase']=='completed':break
  if status['phase']=='interrupted_or_failed':
   state['last_cloud_error']=status.get('error');save()
  time.sleep(20)
 else:raise TimeoutError('Detail tests exceeded two-hour download wait')
 build_gallery(folder);state.update(phase='ready',outputs=108,gallery=str(folder/'index.html'),finished_unix=time.time());save()
 print(json.dumps(state,indent=2))

if __name__=='__main__':
 try:main()
 except Exception:
  import sys
  traceback.print_exc();sys.exit(1)
