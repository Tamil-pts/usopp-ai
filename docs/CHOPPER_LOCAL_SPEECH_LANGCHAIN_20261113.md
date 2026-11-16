# Chopper local speech and LangChain — 13 November 2026

Chopper chat now has a microphone button beside the message composer. Choose
Tamil, English, Hindi, Tanglish / Tamil + English, or automatic language detection.
Record audio or upload WAV, WebM, MP3, M4A, MP4, OGG or FLAC. Review and edit the
transcript before choosing **Use transcript**. This appends text to the existing
draft; the user still chooses when to send the message.

14 November update: the same microphone is also available beside Send in the
top-bar Chopper task/help popup, including its Start a task view. Speech text is
appended to that popup's question. Escape closes the speech dialog first and
retains the Chopper popup. The transcript must fit the remaining 4,000-character
question limit; overlong text must be shortened rather than silently truncated.
Popup browser checks passed for real microphone/WebM transcription, five language
selections, review, draft preservation, no automatic send, focus, Escape and
390–1440px toolbar fit. Nine speech API/chain tests, TypeScript and production
build passed. Artifacts: `.build/chopper-popup-voice-*` and
`.build/chopper-popup-voice-20261114/`.

Recordings are limited to 20 MB and five minutes; microphone capture stops after
two minutes. Microphone access requires browser permission and HTTPS or localhost.
Audio upload remains available when browser microphone recording is unavailable.
Tanglish recognizes mixed speech and can produce Tamil script; Latin-script
transliteration is not guaranteed. Numbers, tag names and recognized words need
review before engineering use.

## Architecture review and changes

| Layer | Finding and implementation |
|---|---|
| Neural network / transformer | The installed Qwen2.5-Coder GGUF already supplies local neural inference through llama.cpp. It was retained and tested. Multilingual Whisper Small adds a neural speech-recognition model. No newly trained PLC model or weight training is claimed. |
| LangChain | Added LangChain Core prompt/message templates and JSON output parsing to the existing model transport. Existing endpoint policy, token fitting, inference queue, source citations and engineering fact-selection checks remain in place. |
| Local privacy | LangSmith tracing is explicitly disabled around LangChain calls, including when enabled globally in the environment. No remote LangChain model, automatic tool agent or cloud speech API was added. |
| Engineering graph and RAG | Existing deterministic PLC parsing, SQLite graph, lexical/symbol retrieval and optional local embedding/reranking remain. Adding libraries does not resolve unsupported PLC semantics or prove sequence correctness. |
| Analytics | Existing workbook/report analytics remain. This change does not install duplicate Torch/Transformers inference stacks or claim new anomaly detection, training or dense retrieval configuration. |
| Speech gap | Implemented account-bound asynchronous transcription, cancellation, transcript review, silent-audio handling, local model loading and bounded audio decoding. |

Speech jobs verify account identity and module access. Raw uploaded audio is
deleted when processing finishes, including cancellation/failure. Transcript
access expires after 24 hours; expired temporary folders are cleaned on later
uploads. Cancelling/removing a transcript clears its result. Interrupted jobs
are reported explicitly on access rather than treated as completed.

## Local setup and packaging

This checkout has `langchain-core` and `faster-whisper` installed and the
multilingual model downloaded. Dependencies are listed in
`backend_requirements.txt`. The explicit installer is:

```powershell
.venv/Scripts/python.exe scripts/setup_chopper_speech.py
```

Only this explicit installer downloads model files. It pins
`Systran/faster-whisper-small` to revision
`536b0662742c02347bc0e980a01041f333bce120` (MIT). Inference loads local files only;
model availability requires `model.bin`, `config.json` and `tokenizer.json`.
The engine uses CPU int8 inference and one speech job at a time.

The default model location is `<application data>/local_ai/models/whisper-small`.
`USOPP_CHOPPER_SPEECH_MODEL` selects another local model directory. The existing
`USOPP_PI_WHISPER_MODEL` setting is also accepted as a fallback. Select a
multilingual model, not an English-only variant.

Model weights are excluded from Git, Windows release contents and Docker build
contexts. Windows packaging now collects the speech and LangChain runtime
modules/data. For a container, mount the installed model directory read-only and
set `USOPP_CHOPPER_SPEECH_MODEL` to its container path. No Windows executable or
Docker image build was performed for this change.

API endpoints are under `/api/assist/speech`: `GET /status`,
`POST /transcriptions`, and `GET` / `DELETE /transcriptions/{id}`.
Health capability flags indicate route support; `/status` reports whether the
local speech model is actually available.

## Verification

- 56 targeted tests passed, one optional test skipped: language routing,
  ownership/account-ID reuse, cancellation and busy handling, limits, invalid
  input, silent audio, model completeness, strict JSON parsing, tracing disabled,
  engineering publication boundaries and existing semantic/retrieval behavior.
- Real offline English inference accurately transcribed the synthesized phrase
  “Check the motor speed and review the validation report.” This is a smoke test,
  not a broad accuracy benchmark.
- The installed local Qwen model returned `READY` for a LangChain-built prompt.
- Browser checks cover real audio upload and microphone WebM transcription, editable transcript review, preserved
  draft text, no automatic chat submission, Escape and mobile/desktop dialog fit.
- TypeScript and production Vite build passed; `pip check` passed.

Tamil, Hindi and mixed Tanglish accuracy still require native-speaker recordings.
The language selector tests establish routing, not recognition quality.
Artifacts: `.build/chopper-english-transcript.json`,
`.build/chopper-langchain-local-inference.json`, `.build/chopper-speech-tests.log`,
`.build/chopper-speech-regression.log`, `.build/chopper-speech-browser.log`, and
`.build/chopper-speech-20261113/`.

Implementation references: [LangChain Core prompts](https://reference.langchain.com/python/langchain-core/prompts/prompt/PromptTemplate),
[JSON parser](https://reference.langchain.com/python/langchain-core/output_parsers/json/JsonOutputParser),
and [Faster-Whisper implementation](https://github.com/SYSTRAN/faster-whisper/blob/master/faster_whisper/transcribe.py).
