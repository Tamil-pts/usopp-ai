"""Explicit offline LoRA training from Admin-reviewed Chopper Q&A exports.

Run in a separate training environment. Never changes the serving model.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--device', choices=['cpu', 'cuda'], required=True)
    parser.add_argument('--model', default='Qwen/Qwen2.5-Coder-1.5B-Instruct')
    parser.add_argument('--max-length', type=int, default=4096)
    parser.add_argument('--epochs', type=float, default=2)
    args = parser.parse_args()
    if not 256 <= args.max_length <= 8192 or not 0 < args.epochs <= 10:
        parser.error('Use max-length 256..8192 and epochs greater than 0, at most 10.')
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()): parser.error('Choose an empty output directory; existing training artifacts are preserved.')
    rows, keys = [], set()
    for number, line in enumerate(args.dataset.read_text(encoding='utf-8').splitlines(), 1):
        if not line.strip(): continue
        row = json.loads(line); metadata = row.get('metadata', {})
        messages = row.get('messages', [])
        if metadata.get('reviewed') is not True or not metadata.get('reviewedBy') or not metadata.get('splitGroup'):
            parser.error(f'Row {number} is not an Admin-reviewed project example.')
        if [m.get('role') for m in messages] != ['system', 'user', 'assistant'] or any(not isinstance(m.get('content'), str) or not m['content'].strip() for m in messages):
            parser.error(f'Row {number} needs one system, user and assistant message.')
        key = hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest()
        if key not in keys: rows.append(row); keys.add(key)
    if len(rows) < 50: parser.error('Collect at least 50 distinct reviewed project Q&A examples before a pilot run. This is a collection target, not a guarantee of model quality.')
    groups = sorted({r['metadata']['splitGroup'] for r in rows})
    if len(groups) < 2: parser.error('Use at least two project groups so one can be held out from training.')
    random.Random(42).shuffle(groups)
    held_groups = set(groups[:max(1, len(groups)//5)])
    train = [r for r in rows if r['metadata']['splitGroup'] not in held_groups]
    held = [r for r in rows if r['metadata']['splitGroup'] in held_groups]
    if len(train) < 20: parser.error('The project split leaves fewer than 20 training examples. Add more reviewed projects.')
    try:
        import torch
        from datasets import Dataset
        from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments, set_seed
        from peft import LoraConfig, get_peft_model
    except ImportError:
        parser.error('Install scripts/chopper_training_requirements.txt in a separate training virtual environment.')
    if args.device == 'cuda' and not torch.cuda.is_available(): parser.error('CUDA is unavailable. Install the matching PyTorch build or select --device cpu explicitly.')
    set_seed(42)
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
    if len(encoded) < 20: parser.error('Too few complete examples fit max-length. Use shorter reviewed traces or a larger token limit; answers are never silently truncated.')
    dtype = torch.float32 if args.device == 'cpu' else torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    model = AutoModelForCausalLM.from_pretrained(args.model, torch_dtype=dtype, trust_remote_code=False, use_safetensors=True)
    model.config.use_cache = False
    model = get_peft_model(model, LoraConfig(r=8, lora_alpha=16, lora_dropout=0.05, bias='none',
                                           task_type='CAUSAL_LM', target_modules=['q_proj', 'k_proj', 'v_proj', 'o_proj']))
    model.enable_input_require_grads()
    def collate(items):
        length = max(len(i['input_ids']) for i in items)
        return {key: torch.tensor([i[key]+[fill]*(length-len(i[key])) for i in items], dtype=torch.long)
                for key, fill in [('input_ids', tokenizer.pad_token_id), ('attention_mask', 0), ('labels', -100)]}
    output.mkdir(parents=True, exist_ok=True)
    for name, data in [('held_out.jsonl', held), ('training_rows.jsonl', train), ('skipped_rows.jsonl', rejected)]:
        (output/name).write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in data), encoding='utf-8')
    manifest = {'schemaVersion': 1, 'status': 'training', 'baseModel': args.model, 'device': args.device,
                'createdAt': datetime.now(timezone.utc).isoformat(), 'datasetDigest': hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
                'trainingExamples': len(encoded), 'heldOutExamples': len(held), 'skippedExamples': len(rejected),
                'maxLength': args.max_length, 'epochs': args.epochs, 'evaluated': False, 'servingModelChanged': False}
    def save_manifest(): (output/'training_manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    save_manifest()
    try:
        trainer = Trainer(model=model, train_dataset=Dataset.from_list(encoded), data_collator=collate,
                          args=TrainingArguments(output_dir=str(output/'checkpoints'), use_cpu=args.device=='cpu',
                          per_device_train_batch_size=1, gradient_accumulation_steps=8, num_train_epochs=args.epochs,
                          learning_rate=1e-4, gradient_checkpointing=True, bf16=dtype==torch.bfloat16,
                          fp16=dtype==torch.float16, optim='adamw_torch', logging_steps=5, save_strategy='epoch',
                          save_total_limit=2, report_to='none', push_to_hub=False, dataloader_num_workers=0, seed=42))
        trainer.train()
        model.save_pretrained(output/'adapter'); tokenizer.save_pretrained(output/'adapter')
        manifest['status'] = 'trained; engineering evaluation pending'
    except BaseException:
        manifest['status'] = 'failed or interrupted'; save_manifest(); raise
    save_manifest()
    print(f'Adapter saved: {output / "adapter"}. Serving GGUF unchanged; evaluate before conversion and installation.')


if __name__ == '__main__': main()
