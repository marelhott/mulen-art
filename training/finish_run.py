"""Bounded local coordinator. Wait for the cloud pipeline, then download. No local inference/training."""
import argparse, hashlib, json, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import modal

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'outputs/research/tuymans'

def write_state(path,state):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(state,indent=2));temp.replace(path)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('run_id');args=parser.parse_args()
    if not args.run_id.startswith('full-unet-') or '/' in args.run_id: raise ValueError('Invalid run id')
    run=args.run_id;volume=modal.Volume.from_name('mulen-training-results')
    local=REPORT/run;local.mkdir(exist_ok=True)
    state={'run_id':run,'phase':'waiting_for_cloud_pipeline','evaluations':[],'started_unix':time.time()}
    state_path=local/'coordinator-status.json';write_state(state_path,state)
    deadline=time.monotonic()+3*3600
    errors=0
    while time.monotonic()<deadline:
        try:
            pipeline=json.loads(b''.join(volume.read_file(f'{run}/pipeline-status.json')))
            errors=0
            write_state(local/'pipeline-status.json',pipeline)
            if pipeline['phase'] in {'ready_for_visual_review','failed'}: break
        except Exception as exc:
            errors+=1;state['last_read_error']=str(exc);write_state(state_path,state)
            if errors>=10: raise RuntimeError('Repeated remote status failures; stopping coordinator')
        time.sleep(60)
    else: raise TimeoutError('Coordinator training wait reached three-hour deadline')
    training=json.loads(b''.join(volume.read_file(f'{run}/status.json')))
    write_state(local/'training-status.json',training)
    files={Path(x.path).name:x.path for x in volume.iterdir(run) if x.path.endswith('.safetensors')}
    selected=[f'mvhpaint_full_unet-step{step:08d}.safetensors' for step in ([800,1600,2400] if run.startswith('full-unet-approved-') else [400,800,1200])]
    selected=[name for name in selected if name in files]
    if not selected:
        selected=sorted(name for name in files if '-step' in name)[-1:]
    if not selected: raise RuntimeError('Training produced no complete candidate checkpoint')
    state['evaluations']=pipeline.get('evaluations',[])
    state['training_status']=training['status']
    state['cloud_pipeline_phase']=pipeline['phase']
    state['phase']='downloading_artifacts';write_state(state_path,state)
    paths=[x.path for x in volume.iterdir(run,recursive=True)
           if ('/evaluation-' in x.path and Path(x.path).suffix in {'.png','.json'})
           or Path(x.path).name in {'status.json','dataset.toml','train.toml','environment.txt','train.log','pipeline-status.json'}]
    def download(remote):
        target=local/Path(remote).relative_to(run);target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('wb') as stream:
            for chunk in volume.read_file(remote): stream.write(chunk)
    with ThreadPoolExecutor(6) as pool: list(pool.map(download,paths))
    latest=selected[-1]
    model_dir=Path('/Users/mulenmara/CODE_DISK/models/Tuymans_Modal');model_dir.mkdir(exist_ok=True)
    target=model_dir/(run+'-'+latest)
    if target.exists(): raise RuntimeError('Refusing to overwrite existing downloaded model')
    temp=target.with_suffix('.download');digest=hashlib.sha256();count=0
    with temp.open('wb') as stream:
        for chunk in volume.read_file(files[latest]):
            stream.write(chunk);digest.update(chunk);count+=len(chunk)
    if count < 1024**3: raise RuntimeError('Full checkpoint unexpectedly small')
    temp.replace(target)
    # Structural header check, without importing Torch or running inference on the Mac.
    import struct
    with target.open('rb') as stream:
        length=struct.unpack('<Q',stream.read(8))[0]
        if not 1 <= length <= 100_000_000: raise RuntimeError('Invalid safetensors header length')
        header=json.loads(stream.read(length))
    state.update(phase='ready_for_visual_review',candidate_model=str(target),model_bytes=count,
                 model_sha256=digest.hexdigest(),tensor_count=len(header)-int('__metadata__' in header),
                 finished_unix=time.time(),note='Latest candidate is not automatically the best model. Visual comparison required.')
    write_state(state_path,state)
    print(json.dumps(state,indent=2),flush=True)

if __name__=='__main__':
    try: main()
    except Exception:
        import traceback
        traceback.print_exc();sys.exit(1)
