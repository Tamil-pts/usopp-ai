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
- Fault diagnosis: set/reset writers, interlocks, timers, state/error transitions
  and the live values needed to distinguish a trigger from its physical cause.
- Syntax review: language-specific syntax, declaration scope, compiler settings
  and the distinction between source review and an Automation Studio build.

The repeatable method is in [PROJECT_ANALYSIS_METHOD.md](PROJECT_ANALYSIS_METHOD.md).

Matching a block family is a bounded static heuristic. Custom wrappers, indirect
calls, macros, dynamically constructed mode strings and missing libraries may
need additional source review. This does not simulate a PLC, prove wiring, or
establish that a network connection is working. Scans retain existing project
scope and skip temporary/generated folders. The full project is not placed in
one prompt; large questions should be divided into functions or communication tasks.

**No new model weights have been trained by installing this release.** The CPU
GGUF remains an inference model. Task guidance and retrieved source improve its
inputs, but do not guarantee correct answers on every project.

Development training artifacts are separate from this installed-model statement.
The first local CPU pilot saved an adapter and a separate GGUF. Its sampled
held-out answers still had missing citations and semantic errors, so it was not
made the active Chopper model. A longer continuation run uses the corrected,
compact project-overview example. See the development run's manifest and
comparison report under `local_ai/training/`; those private artifacts are not
bundled into Git or installer defaults.

## Training data: source-derived examples or reviewed chat answers

Manual Admin approval is optional for the initial source-derived training run.
Examples can be authored directly from supplied project code and B&R help,
using the user's informal question style. Label their origin `source-derived`,
retain source excerpts/digests and citations, and set `reviewed: false` unless
someone actually reviewed them. Do not label these as human-approved answers.
The trainer accepts this input with `--allow-source-derived`.

User questions are useful training prompts. The model's previous reply is not
automatically a correct training answer: derive the target answer from source
evidence, especially when a reply failed citation checks. Raw help files alone
are reference material; supervised training uses question/context/answer records.

The existing app review workflow remains available for corrected chat answers:

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
project groups, accepts reviewed Q&A or explicitly selected source-derived rows, and skips overlong rows without silently
cutting off the answer. A minimum of 50 distinct accepted examples is a pilot
collection target, not proof of enough data or adequate quality.

Both inference and adapter training use **CPU only**. The serving llama.cpp
runtime uses zero GPU layers. The optional trainer uses float32, disables GPU
selection and limits CPU compute threads. No Ollama or GPU installation is needed.

Use a separate virtual environment for training dependencies. A virtual
environment does not isolate CPU or RAM: training on the shared server can affect
validations and other users. Prefer another CPU computer; if using the shared
server, schedule training when users are not working and start with two threads.
Thread limits do not cap RAM. A small CPU inference setup does not imply training
will fit or finish quickly. Duration depends on hardware, token length and dataset
size. Training never runs automatically at app startup.

From the source checkout on a training computer:

```powershell
py -3.11 -m venv .venv-training
.\.venv-training\Scripts\python.exe -m pip install --index-url https://download.pytorch.org/whl/cpu "torch>=2.4,<3"
.\.venv-training\Scripts\python.exe -m pip install -r scripts/chopper_training_requirements.txt
.\.venv-training\Scripts\python.exe scripts/train_chopper_adapter.py --dataset C:\Training\chopper_reviewed_project_training.jsonl --output C:\Training\chopper-run-001 --cpu-threads 2
```

Ubuntu CPU equivalent:

```bash
python3.11 -m venv .venv-training
.venv-training/bin/python -m pip install --index-url https://download.pytorch.org/whl/cpu "torch>=2.4,<3"
.venv-training/bin/python -m pip install -r scripts/chopper_training_requirements.txt
.venv-training/bin/python scripts/train_chopper_adapter.py --dataset /home/lmw/training/chopper_reviewed_project_training.jsonl --output /home/lmw/training/chopper-run-001 --cpu-threads 2
```

For a source-derived dataset, add `--allow-source-derived`. The first development
pilot uses one epoch and a 2,048-token limit, keeping complete examples only:

```powershell
.\.venv-training\Scripts\python.exe -u scripts/train_chopper_adapter.py --dataset local_ai/training/seed-20261010/source_derived_project_training.jsonl --output local_ai/training/chopper-next-run --allow-source-derived --cpu-threads 4 --max-length 2048 --epochs 1
```

Choose a new empty output directory for every run. The manifest records preparation,
model loading, training steps and metrics. Preparing a dataset or downloading the
original weights is not a completed training run. Completion is recorded only
after training returns and the adapter/tokenizer are saved.

To continue from a saved adapter, add
`--initial-adapter C:\Training\previous-run\adapter`. This starts a fresh
optimizer; it is not an exact checkpoint resume. Keep the same original base
model and project-family split, and retain the earlier run. The new manifest
records the starting adapter's hash, and `dataset.jsonl` snapshots the full input.

CPU is the default; existing `--device cpu` commands remain valid. The default
thread limit is half the available logical CPUs, with a minimum of one and a
maximum of four. Use `--cpu-threads` to choose a limit from 1 to 64.
The script defaults to 4,096 tokens and two epochs;
use `--max-length` or `--epochs` only after considering memory and examples.
It downloads the original model into the training computer's Hugging Face cache
on its first run. Training dependencies and original model weights are not
installed by the normal uSOPp installer.

Outputs: `adapter/`, `training_manifest.json`, training row snapshots, skipped-row
reasons, and `held_out.jsonl`. The script does not run engineering evaluation,
push anything online, replace GGUF files, or activate an adapter in production.
The training manifest records CPU threads, precision, completion or interruption,
completed microbatches, optimization steps and loss metrics. For a local base-model
directory containing `download_manifest.json`, it also records the pinned model
revision and download hash. Use `--model C:\Training\base-model` to load original
weights already downloaded onto the training computer.

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

For a completed local run, merge into a new HF model folder on CPU:

```powershell
.\.venv-training\Scripts\python.exe scripts/merge_chopper_adapter.py --run C:\Training\chopper-run-001 --base C:\Training\original-hf-model --output C:\Training\merged-hf --cpu-threads 4
```

The merger preserves the serving GGUF and records adapter/base provenance. It
requires the local original model, not a quantized GGUF. Then use the matching
[llama.cpp conversion tools](https://github.com/ggml-org/llama.cpp) to convert
and quantize the merged model:

```powershell
.\.venv-training\Scripts\python.exe C:\Tools\llama.cpp\convert_hf_to_gguf.py C:\Training\merged-hf --outfile C:\Training\chopper-f16.gguf --outtype f16
C:\Tools\llama.cpp\llama-quantize.exe C:\Training\chopper-f16.gguf C:\Training\chopper-q4_k_m.gguf Q4_K_M 4
```

Install the converter's dependencies in the training environment. The local
development conversion used the bundled runtime's `b11475` release, with its
source pinned to `7e8324f5feba1d8be3f966e1791e84107e40cdd7`, plus SentencePiece.
Keep conversion logs and file hashes. Quantization and a small answer comparison
do not establish complete engineering correctness; inspect logical operators,
contacts/coils, types, source scope and unsupported claims as well as citations.

Primary references:

- [PyTorch CPU installation](https://pytorch.org/get-started/locally/)
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
