"""Discover this approved training run, launch its cloud evaluation once, then downloader."""
import json, subprocess, time
from pathlib import Path
import modal
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/research/tuymans'
v=modal.Volume.from_name('mulen-training-results')
state_path=OUT/'approved-dispatcher-status.json'
state={'phase':'waiting_for_upload_and_training_start'}
def save():state_path.write_text(json.dumps(state,indent=2))
save()
try:
    deadline=time.monotonic()+1200
    while time.monotonic()<deadline:
        candidates=[Path(x.path).name for x in v.iterdir('/',recursive=False) if Path(x.path).name.startswith('full-unet-approved-')]
        if len(candidates)>1:raise RuntimeError('Ambiguous approved runs; refusing duplicate evaluation')
        if candidates:
            run=candidates[0]
            try:training=json.loads(b''.join(v.read_file(run+'/status.json')))
            except Exception:time.sleep(15);continue
            break
        time.sleep(15)
    else:raise TimeoutError('No approved training status after 20 minutes')
    state.update(run_id=run,phase='starting_followup');save()
    with (OUT/'approved-cloud-coordinator.log').open('ab') as log:
        cloud=subprocess.Popen([str(ROOT/'.venv/bin/modal'),'run','--detach','training/evaluate_modal.py','--watch-run',run],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    with (OUT/'approved-download-coordinator.log').open('ab') as log:
        download=subprocess.Popen([str(ROOT/'.venv/bin/python'),'training/finish_run.py',run],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    state.update(phase='followup_dispatched',cloud_pid=cloud.pid,download_pid=download.pid);save()
except Exception:
    import traceback
    state.update(phase='failed',error=traceback.format_exc());save();raise
