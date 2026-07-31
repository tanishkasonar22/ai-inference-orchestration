"""Per-engine adapters: engine-agnostic config -> engine-specific CR fields.

  - governed core   -> handled identically by cr_builder
  - engine-DERIVED  -> modelFormat / protocolVersion, from the enum, here
  - passthrough     -> engine_params flattened here, per each engine's style

Adding an engine = one Adapter subclass. No schema or cr_builder change.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
import inference_service_pb2 as pb


class EngineAdapter(ABC):
    model_format: str = ""
    protocol_version: str | None = None

    @abstractmethod
    def render_args(self, engine_params: dict[str, str]) -> list[str]:
        raise NotImplementedError

    def model_env(self, engine_params: dict[str, str]) -> list[dict]:
        return []


class VllmHuggingFaceAdapter(EngineAdapter):
    model_format = "huggingface"
    protocol_version = None  # HF/vLLM serves the OpenAI protocol; field omitted

    def render_args(self, engine_params: dict[str, str]) -> list[str]:
        args: list[str] = []
        for key, value in engine_params.items():
            args.append(f"--{key}" if value == "" else f"--{key}={value}")
        return args


class TritonAdapter(EngineAdapter):
    model_format = "triton"
    protocol_version = "v2"
    _ENV_KEYS = {"OMP_NUM_THREADS", "MKL_NUM_THREADS"}

    def render_args(self, engine_params: dict[str, str]) -> list[str]:
        args: list[str] = []
        for key, value in engine_params.items():
            if key in self._ENV_KEYS:
                continue
            args.append(f"--{key}" if value == "" else f"--{key}={value}")
        return args

    def model_env(self, engine_params: dict[str, str]) -> list[dict]:
        return [{"name": k, "value": v}
                for k, v in engine_params.items() if k in self._ENV_KEYS]


_ADAPTERS: dict[int, EngineAdapter] = {
    pb.ENGINE_TYPE_VLLM_HUGGINGFACE: VllmHuggingFaceAdapter(),
    pb.ENGINE_TYPE_TRITON: TritonAdapter(),
}


class UnsupportedEngineError(ValueError):
    pass


def get_adapter(engine: int) -> EngineAdapter:
    """REQ-1.1 boundary validation: reject unknown engines here."""
    adapter = _ADAPTERS.get(engine)
    if adapter is None:
        name = pb.EngineType.Name(engine) if engine in pb.EngineType.values() else engine
        raise UnsupportedEngineError(f"unsupported or unspecified engine: {name}")
    return adapter
