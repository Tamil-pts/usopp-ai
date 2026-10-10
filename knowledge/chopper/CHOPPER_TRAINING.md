# Chopper project analysis and training

## What this release implements

The backend understands common request spellings such as `machien fuction`,
`communction`, `RS 485`, and `suggection`, while preserving quoted names, paths
and PLC identifiers. It selects a task guide, decodes the chosen project's active
configuration, retrieves source evidence, resolves communication block instances
through local declarations, and supplies bounded traces to the installed model.

Supported analysis paths:

- Machine functions: task ownership, modes, start/stop, interlocks, output actions,
  alarm/reset evidence and the limits of inferred operating sequences.
- Communication: TCP, UDP, ICMP ping, Modbus serial/TCP, DVFrame serial frames,
  CAN API candidates, literal serial mode settings and nearby status/settings traces.
- RS485 review: distinguish physical interface from protocol, trace device/mode
  strings, baud/parity/stop bits, open/handle, busy/error, timeout/retry and recovery.
- Improvement review: source-located candidates for state handling, timeout units,
  buffer/pointer usage and stop/fault interlocks. A candidate is not a proven defect.
- Focused source/feature lookup with source evidence and B&R reference help.

Matching a block family is a bounded static heuristic. Custom wrappers, indirect
calls, macros, dynamically constructed mode strings and missing libraries may
need additional source review. This does not simulate a PLC, prove wiring, or
establish that a network connection is working. Scans retain existing project
scope and skip temporary/generated folders. The full project is not placed in
one prompt; large questions should be divided into functions or communication tasks.

**No new model weights have been trained by installing this release.** The CPU
GGUF remains an inference model. Task guidance and retrieved source improve its
inputs, but do not guarantee correct answers on every project.

## Build a reviewed dataset in the app

1. Attach/select a project and ask Chopper a question. Both accepted model replies
   and local source replies with evidence are saved as pending drafts.
2. Open **KnowHub → Project answer training**. Users see their own drafts; Admin
   sees all drafts. The record includes the original informal question, answer,
   source excerpts, ownership, reference help and evidence digest.
3. Admin checks the complete source and corrects the answer. Keep exact names,
   valid `[S1]` project citations and `[H1]` help citations. Describe unknowns.
4. Choose **Approve corrected answer**. Citation identities are checked; engineering
   correctness still requires the reviewer. Wrong or incomplete answers can be
   rejected or left pending.
5. Admin chooses **Export approved Q&A**. The new export contains only approved
   project examples, with source context. Legacy rule-feedback exports are separate.
6. Collect diverse examples: machine operation, ST/AB/C/ladder, normal/error serial
   paths, Modbus RTU/ASCII/TCP, HMI binding, multiple targets, missing evidence,
   unsafe-looking but legitimate code, and typo-heavy questions. Include explicit
   counterexamples such as Modbus without proof of RS485. Do not use an AI answer
   as engineering ground truth without review.

Records are in `application.sqlite3` under the persistent `USOPP_DATA_ROOT`.
They survive container/application updates when that data volume is preserved.
Keep them with the usual database backup. Approved exports contain source text;
do not publish them in Git or distribute them with installer defaults.

## Run actual adapter training separately

The optional script trains a LoRA adapter on the original Hugging Face
`Qwen/Qwen2.5-Coder-1.5B-Instruct`, not directly on the installed GGUF.
It masks system/user tokens from the loss, deduplicates examples, holds out whole
project groups, refuses unreviewed rows, and skips overlong rows without silently
cutting off the answer. A minimum of 50 distinct reviewed examples is a pilot
collection target, not proof of enough data or adequate quality.

Use a separate development/training environment so training does not consume
the serving model's CPU/RAM or interrupt validations. An NVIDIA GPU is preferable
for training. Explicit CPU training is supported, but can require substantial RAM
and time; a small CPU inference setup does not imply training will fit or finish
quickly. Training duration depends on hardware, token length and dataset size.

From the source checkout on a training computer:

```powershell
py -3.11 -m venv .venv-training
.\.venv-training\Scripts\python.exe -m pip install -r scripts/chopper_training_requirements.txt
.\.venv-training\Scripts\python.exe scripts/train_chopper_adapter.py --dataset C:\Training\chopper_reviewed_project_training.jsonl --output C:\Training\chopper-run-001 --device cpu
```

Ubuntu CPU equivalent:

```bash
python3.11 -m venv .venv-training
.venv-training/bin/python -m pip install -r scripts/chopper_training_requirements.txt
.venv-training/bin/python scripts/train_chopper_adapter.py --dataset /home/lmw/training/chopper_reviewed_project_training.jsonl --output /home/lmw/training/chopper-run-001 --device cpu
```

For NVIDIA use the PyTorch build appropriate to its CUDA environment, then
select `--device cuda`. The script defaults to 4,096 tokens and two epochs;
use `--max-length` or `--epochs` only after considering memory and examples.
It downloads the original model into the training computer's Hugging Face cache
on its first run. Training dependencies and original model weights are not
installed by the normal uSOPp installer.

Outputs: `adapter/`, `training_manifest.json`, training row snapshots, skipped-row
reasons, and `held_out.jsonl`. The script does not run engineering evaluation,
push anything online, replace GGUF files, or activate an adapter in production.
The training manifest records completion or interruption honestly.

## Evaluate and deploy later

Review behavior on held-out projects before deployment: citation accuracy,
unsupported feature claims, active-task/target scope, timeout units, RS485/protocol
distinctions, error/recovery paths and safe handling of missing evidence. Compare
to the original model with the same retrieved context. A successful training loss
does not establish engineering correctness.

After evaluation, merge/convert the adapter using tooling compatible with the
base model and the installed llama.cpp runtime. Keep the existing GGUF for
rollback, then select the separately named new GGUF in **Settings → Chopper**.
This release prepares training/export; conversion and deployment are not
automatic. New weights do not replace the source decoder or B&R reference index.

Primary references:

- [Hugging Face PEFT LoRA](https://huggingface.co/docs/peft/package_reference/lora)
- [Hugging Face Transformers Trainer](https://huggingface.co/docs/transformers/main_classes/trainer)
- [Qwen2.5-Coder model family](https://github.com/QwenLM/Qwen2.5-Coder)

## Suggested questions

- `say that machien fuction in this project`
- `what communction is used here and which task calls it`
- `RS485 commncation block check that logic timeout and recovery`
- `any improvment in this project give suggestion with source`
- `Step is 100, TcpOpen_0.status is 0, TcpIoctl_0.status is 32604; trace the failing call`

Live-state questions need the numeric state/status and the relevant source.
Names and task presence alone do not establish the cause of a runtime error.
