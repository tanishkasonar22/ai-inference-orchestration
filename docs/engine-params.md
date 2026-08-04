# Engine-specific parameters (`engine_params`) — REQ-2.2

`ModelConfig.engine_params` (protobuf `map<string, string>`) carries engine-specific
knobs that are **not** part of the governed, engine-agnostic core (model id, source,
resources, replica count, namespace, service account, credentials). Each supported
engine's adapter (`adapters.py`) decides how a key/value pair is applied to that
engine's native configuration.

## Rules (all engines)

- **Key = the native flag name, without a leading `--`.** The adapter adds the `--`.
  Example: `max-model-len` → `--max-model-len`.
- **Empty value = a boolean flag.** `enable-auto-tool-choice: ""` renders as
  `--enable-auto-tool-choice` (no `=`). A non-empty value renders `--key=value`.
- **Do not put governed fields in `engine_params`.** CPU/memory/GPU, replica count,
  model id, storage URI, namespace, and service account are typed fields in the
  standard schema; the passthrough map must not override them (REQ-2.2 constraint).
- **Passthrough is open, not allow-listed.** The control plane hands these straight
  to the engine. A key the target engine does not recognize is still passed through
  and may cause the predictor to fail at container start (surfaced as the
  InferenceService not reaching `READY`), rather than being rejected up front. Prefer
  the known keys below.

## vLLM — `ENGINE_TYPE_VLLM_HUGGINGFACE` (`modelFormat: huggingface`)

Every `engine_params` entry is flattened into the predictor container args (vLLM
OpenAI-server flags). Known params exercised on this platform:

| Key | Example | Renders as | Purpose |
| --- | --- | --- | --- |
| `max-model-len` | `8192` | `--max-model-len=8192` | Max context length. Lives here (not in the governed core) because it is vLLM-specific. |
| `gpu-memory-utilization` | `0.90` | `--gpu-memory-utilization=0.90` | Fraction of GPU memory vLLM may use. |
| `enable-auto-tool-choice` | `` (empty) | `--enable-auto-tool-choice` | Enable tool-calling; required when Open Web UI sends `tool_choice: "auto"`. |
| `tool-call-parser` | `llama3_json` / `hermes` | `--tool-call-parser=llama3_json` | Tool-call parser, model-appropriate: `llama3_json` for Llama, `hermes` for Qwen-based (Qwen, DeepSeek). |

Any other vLLM OpenAI-server flag can be passed by the same rule (e.g. `dtype`,
`max-num-seqs`); the four above are the ones the platform uses.

## NVIDIA Triton — `ENGINE_TYPE_TRITON` (`modelFormat: triton`, `protocolVersion: v2`)

Triton's adapter splits `engine_params` two ways:

- **Environment variables** — keys in the adapter's env set (`_ENV_KEYS`) become
  container env, not args. Current env keys: `OMP_NUM_THREADS`, `MKL_NUM_THREADS`.
- **Server args** — every other key is flattened to `--key[=value]` on the
  `tritonserver` command line.

| Key | Example | Applied as | Purpose |
| --- | --- | --- | --- |
| `OMP_NUM_THREADS` | `1` | env var | OpenMP thread cap (CPU-side ops). |
| `MKL_NUM_THREADS` | `1` | env var | Intel MKL thread cap. |
| `log-verbose` | `1` | `--log-verbose=1` (arg) | Triton verbose logging level. |

Other `tritonserver` flags follow the same arg rule. To route a new key to env
instead of args, add it to `_ENV_KEYS` in `adapters.py` — a one-line change, no
schema change.

## Adding an engine

A new engine is one `EngineAdapter` subclass in `adapters.py` (its `model_format`,
optional `protocol_version`, `render_args`, and optional `model_env`). No `.proto`
or `cr_builder.py` change is required — this is the extensibility property that
REQ-2.2 and Objective 4 rely on.