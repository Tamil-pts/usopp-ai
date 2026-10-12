"""Merge a completed CPU-trained Chopper adapter into a separate HF model folder."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cpu-threads', type=int, default=4)
    args = parser.parse_args()
    if not 1 <= args.cpu_threads <= 64: parser.error('Use CPU threads 1..64.')
    run, base, output = args.run.resolve(), args.base.resolve(), args.output.resolve()
    manifest = json.loads((run/'training_manifest.json').read_text(encoding='utf-8'))
    if not manifest.get('status', '').startswith('trained;'):
        parser.error('The run must have saved a completed adapter before merging.')
    adapter = run/'adapter'
    weights = adapter/'adapter_model.safetensors'
    if not weights.is_file(): parser.error('Completed adapter weights are missing.')
    if not (base/'config.json').is_file(): parser.error('Choose the local original HF base model directory.')
    # Ensure the supplied original model matches the run when provenance exists.
    recorded = manifest.get('baseModelDownload')
    if recorded:
        actual = json.loads((base/'download_manifest.json').read_text(encoding='utf-8'))
        if any(actual.get(k) != recorded.get(k) for k in ('repository', 'revision', 'sha256')):
            parser.error('Base model provenance differs from this training run.')
    if output.exists() and any(output.iterdir()): parser.error('Choose a new empty model folder.')
    output.mkdir(parents=True, exist_ok=True)
    os.environ['CUDA_VISIBLE_DEVICES'] = ''
    os.environ['OMP_NUM_THREADS'] = str(args.cpu_threads)
    os.environ['MKL_NUM_THREADS'] = str(args.cpu_threads)
    os.environ['TOKENIZERS_PARALLELISM'] = 'false'
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel
    torch.set_num_threads(args.cpu_threads)
    torch.set_num_interop_threads(1)
    print('Loading original CPU model and trained adapter.', flush=True)
    model = AutoModelForCausalLM.from_pretrained(str(base), torch_dtype=torch.float32,
                                              use_safetensors=True, trust_remote_code=False)
    adapted = PeftModel.from_pretrained(model, str(adapter), is_trainable=False)
    merged = adapted.merge_and_unload(safe_merge=True)
    merged.config.use_cache = True
    merged.save_pretrained(output, safe_serialization=True, max_shard_size='2GB')
    AutoTokenizer.from_pretrained(str(adapter), trust_remote_code=False).save_pretrained(output)
    summary = {'schemaVersion': 1, 'status': 'merged HF model; GGUF conversion pending',
               'createdAt': datetime.now(timezone.utc).isoformat(), 'device': 'cpu',
               'trainingRun': str(run), 'datasetDigest': manifest['datasetDigest'],
               'baseModelDownload': recorded, 'adapterSHA256': hashlib.sha256(weights.read_bytes()).hexdigest(),
               'servingModelChanged': False}
    (output/'merge_manifest.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(f'Merged model saved: {output}. Convert and quantize it separately for llama.cpp.', flush=True)


if __name__ == '__main__': main()
