"""CPU-only offline LoRA training from reviewed Q&A or source-derived examples.

Run in a separate training environment. Never changes the serving model.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--device', choices=['cpu'], default='cpu', help='CPU only; --device cpu remains accepted.')
    parser.add_argument('--cpu-threads', type=int, default=min(4, max(1, (os.cpu_count() or 2)//2)),
                        help='CPU compute threads (1..64); defaults to at most four, using half the available logical CPUs.')
    parser.add_argument('--model', default='Qwen/Qwen2.5-Coder-1.5B-Instruct')
    parser.add_argument('--allow-source-derived', action='store_true',
                        help='Train source-derived examples without claiming human review.')
    parser.add_argument('--max-length', type=int, default=4096)
    parser.add_argument('--epochs', type=float, default=2)
    args = parser.parse_args()
    if not 256 <= args.max_length <= 8192 or not 0 < args.epochs <= 10:
        parser.error('Use max-length 256..8192 and epochs greater than 0, at most 10.')
    if not 1 <= args.cpu_threads <= 64:
        parser.error('Use cpu-threads 1..64.')
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()): parser.error('Choose an empty output directory; existing training artifacts are preserved.')
    rows, keys = [], set()
    for number, line in enumerate(args.dataset.read_text(encoding='utf-8').splitlines(), 1):
        if not line.strip(): continue
        row = json.loads(line); metadata = row.get('metadata', {})
        messages = row.get('messages', [])
        reviewed = metadata.get('reviewed') is True and bool(metadata.get('reviewedBy'))
        source_derived = args.allow_source_derived and metadata.get('origin') == 'source-derived' and bool(metadata.get('evidenceDigest'))
        if not (reviewed or source_derived) or not metadata.get('splitGroup'):
            parser.error(f'Row {number} needs reviewed Q&A or --allow-source-derived with source evidence and a project group.')
        if [m.get('role') for m in messages] != ['system', 'user', 'assistant'] or any(not isinstance(m.get('content'), str) or not m['content'].strip() for m in messages):
            parser.error(f'Row {number} needs one system, user and assistant message.')
        key = hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest()
        if key not in keys: rows.append(row); keys.add(key)
    if len(rows) < 50: parser.error('Use at least 50 distinct project Q&A examples for a pilot run. This collection target does not guarantee model quality.')
    groups = sorted({r['metadata']['splitGroup'] for r in rows})
    if len(groups) < 2: parser.error('Use at least two project groups so one can be held out from training.')
    random.Random(42).shuffle(groups)
    held_groups = set(groups[:max(1, len(groups)//5)])
    train = [r for r in rows if r['metadata']['splitGroup'] not in held_groups]
    held = [r for r in rows if r['metadata']['splitGroup'] in held_groups]
    if len(train) < 20: parser.error('The project split leaves fewer than 20 training examples. Add more project examples.')
    output.mkdir(parents=True, exist_ok=True)
    manifest = {'schemaVersion': 2, 'status': 'preparing', 'baseModel': args.model, 'device': args.device,
                'cpuThreads': args.cpu_threads, 'precision': 'float32',
                'createdAt': datetime.now(timezone.utc).isoformat(), 'datasetDigest': hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
                'trainingExamples': len(train), 'heldOutExamples': len(held), 'skippedExamples': 0,
                'sourceDerivedExamples': sum(r['metadata'].get('origin') == 'source-derived' for r in rows),
                'maxLength': args.max_length, 'epochs': args.epochs, 'evaluated': False, 'servingModelChanged': False}
    def save_manifest(): (output/'training_manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    save_manifest()
    print(f'CPU preparation: {len(train)} training examples, {len(held)} held-out examples, {args.cpu_threads} threads.', flush=True)
    # Apply limits before importing libraries or loading the original model.
    # These limit compute threads; training still shares the host's RAM/CPU.
    os.environ['CUDA_VISIBLE_DEVICES'] = ''
    os.environ['OMP_NUM_THREADS'] = str(args.cpu_threads)
    os.environ['MKL_NUM_THREADS'] = str(args.cpu_threads)
    os.environ['TOKENIZERS_PARALLELISM'] = 'false'
    try:
        import torch
        from datasets import Dataset
        from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainerCallback, TrainingArguments, set_seed
        from peft import LoraConfig, get_peft_model
    except ImportError:
        parser.error('Install CPU PyTorch and scripts/chopper_training_requirements.txt as described in knowledge/chopper/CHOPPER_TRAINING.md.')
    torch.set_num_threads(args.cpu_threads)
    torch.set_num_interop_threads(1)
    set_seed(42)
    manifest['status'] = 'loading tokenizer'; save_manifest()
    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=False)
    tokenizer.pad_token = tokenizer.pad_token or tokenizer.eos_token
    encoded, rejected = [], []
    for row in train:
        messages = row['messages']
        prefix = tokenizer.apply_chat_template(messages[:-1], tokenize=True, add_generation_prompt=True)
        tokens = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=False)
        if tokens[:len(prefix)] != prefix: parser.error('Chat template prefix is incompatible with assistant-only masking. Update the trainer for this model template.')
        if len(tokens) > args.max_length:
            rejected.append({'id': row['metadata']['id'], 'reason': 'over token limit', 'tokens': len(tokens)}); continue
        encoded.append({'input_ids': tokens, 'attention_mask': [1]*len(tokens), 'labels': [-100]*len(prefix)+tokens[len(prefix):]})
    if len(encoded) < 20:
        manifest['status'] = 'too few complete examples fit token limit'; save_manifest()
        parser.error('Too few complete examples fit max-length. Use shorter source traces or a larger token limit; answers are never silently truncated.')
    manifest.update(status='loading base model', trainingExamples=len(encoded), skippedExamples=len(rejected)); save_manifest()
    print(f'Loading base model on CPU; {len(encoded)} complete examples fit the token limit.', flush=True)
    model = AutoModelForCausalLM.from_pretrained(args.model, torch_dtype=torch.float32, trust_remote_code=False, use_safetensors=True)
    model.config.use_cache = False
    model = get_peft_model(model, LoraConfig(r=8, lora_alpha=16, lora_dropout=0.05, bias='none',
                                           task_type='CAUSAL_LM', target_modules=['q_proj', 'k_proj', 'v_proj', 'o_proj']))
    model.enable_input_require_grads()
    def collate(items):
        length = max(len(i['input_ids']) for i in items)
        return {key: torch.tensor([i[key]+[fill]*(length-len(i[key])) for i in items], dtype=torch.long)
                for key, fill in [('input_ids', tokenizer.pad_token_id), ('attention_mask', 0), ('labels', -100)]}
    for name, data in [('held_out.jsonl', held), ('training_rows.jsonl', train), ('skipped_rows.jsonl', rejected)]:
        (output/name).write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in data), encoding='utf-8')
    manifest['status'] = 'training'; save_manifest()
    class Progress(TrainerCallback):
        def on_step_end(self, args, state, control, **kwargs):
            manifest.update(step=state.global_step, totalSteps=state.max_steps, epoch=state.epoch,
                            updatedAt=datetime.now(timezone.utc).isoformat())
            save_manifest()
        def on_log(self, args, state, control, logs=None, **kwargs):
            if logs: manifest['metrics'] = logs; save_manifest()
    try:
        trainer = Trainer(model=model, train_dataset=Dataset.from_list(encoded), data_collator=collate, callbacks=[Progress()],
                          args=TrainingArguments(output_dir=str(output/'checkpoints'), use_cpu=True,
                          per_device_train_batch_size=1, gradient_accumulation_steps=8, num_train_epochs=args.epochs,
                          learning_rate=1e-4, gradient_checkpointing=True, bf16=False,
                          fp16=False, optim='adamw_torch', logging_steps=1, save_strategy='epoch',
                          save_total_limit=2, report_to='none', push_to_hub=False, dataloader_num_workers=0, seed=42))
        result = trainer.train()
        manifest['trainingMetrics'] = result.metrics
        model.save_pretrained(output/'adapter'); tokenizer.save_pretrained(output/'adapter')
        manifest['status'] = 'trained; engineering evaluation pending'
    except BaseException:
        manifest['status'] = 'failed or interrupted'; save_manifest(); raise
    save_manifest()
    print(f'Adapter saved: {output / "adapter"}. Serving GGUF unchanged; evaluate before conversion and installation.')


if __name__ == '__main__': main()
