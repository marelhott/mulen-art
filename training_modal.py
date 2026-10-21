"""Private, bounded SDXL training. Run: modal run --detach training_modal.py"""
from pathlib import Path
import modal

COMMIT = '04ca541746b7667b27eab230db067579f682895e'
app = modal.App('mulen-sdxl-training')
models = modal.Volume.from_name('img2img-models')
data = modal.Volume.from_name('mulen-training-data', create_if_missing=True)
results = modal.Volume.from_name('mulen-training-results', create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version='3.11')
    .apt_install('git', 'libgl1', 'libglib2.0-0')
    .pip_install('torch==2.8.0', 'torchvision==0.23.0')
    .run_commands(
        'git clone https://github.com/kohya-ss/sd-scripts.git /opt/sd-scripts',
        f'cd /opt/sd-scripts && git checkout {COMMIT}',
        'cd /opt/sd-scripts && pip install -r requirements.txt',
        'cd /opt/sd-scripts && python -c "import sdxl_train_network; import sdxl_train"',
    )
    .env({'HF_HOME':'/models/training-hf-cache','TOKENIZERS_PARALLELISM':'false',
          'PYTHONUNBUFFERED':'1','OMP_NUM_THREADS':'4'})
)

@app.function(image=image, gpu='A100-80GB', cpu=4, memory=65536,
              volumes={'/models':models,'/data':data,'/results':results},
              timeout=7200, max_containers=1, retries=0)
def train_variant(kind: str = "lora", steps: int = 300, learning_rate: float = 0.00005, run_id: str = ""):
    import json, subprocess, time, traceback
    from datetime import datetime, timezone
    import torch
    if kind not in {'lora','full','approved','mulen'} or not 1 <= steps <= 3000:
        raise ValueError('Invalid bounded training configuration')
    if not 1e-7 <= learning_rate <= 1e-4:
        raise ValueError('Learning rate outside reviewed range')
    deadline = 1620 if kind == 'lora' and steps <= 300 else 6600
    prefix = {'lora':'lora64','approved':'full-unet-approved','mulen':'full-unet-mulen'}.get(kind,'full-unet')
    run_id = run_id or prefix + '-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    if '/' in run_id or '..' in run_id: raise ValueError('Invalid run ID')
    folder = Path('/results') / run_id
    resume_state = None
    if folder.exists():
        # Modal reschedules a preempted input with the same arguments: continue from the newest saved
        # optimizer state instead of paying for the finished steps again. Completed runs are never touched.
        previous = json.loads((folder/'status.json').read_text()) if (folder/'status.json').exists() else {}
        if previous.get('status') == 'completed': raise RuntimeError('Run already completed; refusing to restart it')
        states = sorted(folder.glob('*-step*-state'))
        resume_state = states[-1] if states else None
        attempt = len(list(folder.glob('train*.log'))) + 1
        if (folder/'train.log').exists(): (folder/'train.log').rename(folder/f'train.attempt{attempt-1}.log')
    else:
        folder.mkdir()
    dataset = '''[general]
caption_extension = ".txt"
shuffle_caption = false
caption_dropout_rate = 0.15

[[datasets]]
resolution = 1024
batch_size = 1
enable_bucket = true
min_bucket_reso = 512
max_bucket_reso = 1536
bucket_reso_steps = 64
bucket_no_upscale = true

[[datasets.subsets]]
image_dir = "/data/dataset-v2/train"
num_repeats = 1
'''
    if kind == 'full':
        regularization = Path('/data/dataset-v1/regularization')
        if len(list(regularization.glob('*.png'))) != 12:
            raise RuntimeError('The 12 reviewed regularization images are required before full training')
        # Ordinary low-frequency replay avoids sd-scripts' automatic class-image balancing.
        # At this pinned commit sdxl_train.py does not apply per-image prior loss weights.
        dataset = dataset.replace('num_repeats = 1', 'num_repeats = 4')
        dataset += '\n[[datasets.subsets]]\nimage_dir = "/data/dataset-v1/regularization"\nnum_repeats = 1\ncaption_dropout_rate = 0.0\n'
    if kind == 'mulen':
        manifest=json.loads(Path('/data/dataset-mulen-v1/manifest.json').read_text())
        if sum(1 for r in manifest if r['used'])!=226: raise RuntimeError('Expected the 226 prepared Mulen Mara paintings')
        # Same recipe as the validated Tuymans run: whole images x4, caption dropout .35, no replay, no crops.
        dataset=dataset.replace('/data/dataset-v2/train','/data/dataset-mulen-v1/whole')
        dataset=dataset.replace('caption_dropout_rate = 0.15','caption_dropout_rate = 0.35')
        dataset=dataset.replace('num_repeats = 1','num_repeats = 4')
    if kind == 'approved':
        manifest=json.loads(Path('/data/dataset-approved-v3/manifest.json').read_text())
        if len(manifest)!=247: raise RuntimeError('Expected all 247 approved sources')
        allowed={'/Users/mulenmara/Pictures/TUY resized-images','/Users/mulenmara/Pictures/Tuymans hi-res'}
        if any(str(Path(r['path']).parent) not in allowed for r in manifest): raise RuntimeError('Unapproved source in manifest')
        dataset=dataset.replace('/data/dataset-v2/train','/data/dataset-approved-v3/whole')
        dataset=dataset.replace('caption_dropout_rate = 0.15','caption_dropout_rate = 0.35')
        dataset=dataset.replace('num_repeats = 1','num_repeats = 4')
        dataset+='\n[[datasets.subsets]]\nimage_dir = "/data/dataset-approved-v3/detail"\nnum_repeats = 1\n'
    (folder/'dataset.toml').write_text(dataset)
    config = {
      'pretrained_model_name_or_path':'/models/checkpoints/sd_xl_base_1.0.safetensors',
      'dataset_config':str(folder/'dataset.toml'),
      'output_dir':str(folder),'output_name':'mvhpaint_lora64',
      'save_model_as':'safetensors','save_precision':'fp16','mixed_precision':'bf16',
      'network_module':'networks.lora','network_dim':64,'network_alpha':32,
      'network_train_unet_only':True,'learning_rate':learning_rate,
      'optimizer_type':'AdamW8bit','lr_scheduler':'constant_with_warmup',
      'lr_warmup_steps':20,'max_train_steps':steps,'gradient_accumulation_steps':4,
      'gradient_checkpointing':True,'cache_latents':True,'cache_latents_to_disk':True,
      'sdpa':True,'no_half_vae':True,'seed':231019,'max_data_loader_n_workers':2,
      'save_every_n_steps':100 if steps <= 300 else 200,'save_state':True,'save_state_on_train_end':True,'save_last_n_steps':steps,
      'logging_dir':str(folder/'logs'),'log_with':'tensorboard',
    }
    if kind in {'full','approved','mulen'}:
        for key in ['network_module','network_dim','network_alpha','network_train_unet_only']:
            config.pop(key)
        config['output_name']='mulen_mara_full_unet' if kind == 'mulen' else 'mvhpaint_full_unet'
        if kind == 'mulen': config['save_every_n_steps']=600  # resume points; only the newest optimizer state is kept
        config['train_text_encoder']=False
        config['lr_warmup_steps']=50
        config['save_last_n_steps_state']=200
    if resume_state:
        # The saved state holds weights, optimizer and scheduler but no step counter at this commit,
        # so run only the steps still missing; the finished ones are already in the weights.
        import re
        done=int(re.search(r'step(\d+)-state$',resume_state.name).group(1))
        if done >= steps: raise RuntimeError('Newest saved state already covers the requested steps')
        config['resume']=str(resume_state); config['max_train_steps']=steps-done
    import toml
    (folder/'train.toml').write_text(toml.dumps(config))
    (folder/'environment.txt').write_text(subprocess.check_output(['pip','freeze'],text=True))
    status={'run_id':run_id,'commit':COMMIT,'config':config,'resumed_from':str(resume_state) if resume_state else None,
            'gpu':torch.cuda.get_device_name(),'started_at':datetime.now(timezone.utc).isoformat(),
            'gpu_hourly_usd':2.4984,'cpu_ram_hourly_usd_estimate':0.700128,
            'timeout_seconds':7200, 'subprocess_deadline_seconds':deadline,'status':'running'}
    def save():
        (folder/'status.json').write_text(json.dumps(status,indent=2)); results.commit()
    save(); started=time.monotonic()
    try:
        with (folder/'train.log').open('w') as log:
            process=subprocess.Popen(['python','sdxl_train_network.py' if kind == 'lora' else 'sdxl_train.py','--config_file',str(folder/'train.toml')],
                cwd='/opt/sd-scripts',stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
            # Reader thread preserves live logs; parent enforces the total training deadline.
            import threading
            def drain():
                for line in process.stdout:
                    print(line,end='',flush=True); log.write(line); log.flush()
            thread=threading.Thread(target=drain,daemon=True); thread.start()
            try: code=process.wait(timeout=deadline)
            except subprocess.TimeoutExpired:
                process.terminate()
                try: process.wait(timeout=15)
                except subprocess.TimeoutExpired: process.kill(); process.wait()
                raise RuntimeError('Bounded training reached its subprocess deadline')
            thread.join(timeout=10)
            if code: raise RuntimeError(f'Training exited with {code}; see train.log')
        status['status']='completed'
        status['artifacts']=[str(p.relative_to(folder)) for p in folder.rglob('*.safetensors')]
    except BaseException:
        status['status']='interrupted_or_failed'; status['error']=traceback.format_exc()
        raise
    finally:
        status['elapsed_seconds']=round(time.monotonic()-started,2)
        status['estimated_compute_usd']=round(status['elapsed_seconds']/3600*(2.4984+.700128),4)
        status['finished_at']=datetime.now(timezone.utc).isoformat(); save()
    return status

@app.local_entrypoint()
def main(kind: str = "lora", steps: int = 300, learning_rate: float = 0.00005, resume_run: str = ""):
    import json
    from datetime import datetime, timezone
    prefix={'lora':'lora64','approved':'full-unet-approved','mulen':'full-unet-mulen'}.get(kind,'full-unet')
    if resume_run:  # continue a preempted run from its newest saved state; the dataset is already uploaded
        print(json.dumps(train_variant.remote(kind, steps, learning_rate, resume_run),indent=2)); return
    # Upload only the prepared private dataset; never publish it or modify source images.
    dataset_name={'approved':'dataset-approved-v3','mulen':'dataset-mulen-v1'}.get(kind,'dataset-v2')
    local=Path(__file__).parent/'outputs/research'/('mulen_mara' if kind == 'mulen' else 'tuymans')/dataset_name
    if not (local/'manifest.json').exists(): raise RuntimeError('Prepare and review dataset first')
    with data.batch_upload(force=True) as upload:
        upload.put_directory(local, '/'+dataset_name)
    run_id=prefix+'-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    print(json.dumps(train_variant.remote(kind, steps, learning_rate, run_id),indent=2))
