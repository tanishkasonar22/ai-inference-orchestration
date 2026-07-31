import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "generated"))

import yaml
import inference_service_pb2 as pb
import model_config_pb2 as mc
from cr_builder import build_inference_service
from adapters import UnsupportedEngineError


def llama_cfg() -> mc.ModelConfig:
    c = mc.ModelConfig(
        model_id="llama",
        source=mc.ModelSource(uri="gs://intern-501105-model-weights/llama"),
        resources=mc.ResourceRequirements(cpu="6", memory="24Gi",
                                          gpu_count=1, gpu_type="nvidia-l4"),
        replica_count=1, namespace="default", service_account="default",
    )
    c.engine_params["max-model-len"] = "8192"
    c.engine_params["gpu-memory-utilization"] = "0.90"
    c.engine_params["enable-auto-tool-choice"] = ""
    c.engine_params["tool-call-parser"] = "llama3_json"
    return c


def triton_cfg() -> mc.ModelConfig:
    c = mc.ModelConfig(
        model_id="bert-triton",
        source=mc.ModelSource(uri="gs://intern-501105-model-weights/bert/model_repository"),
        resources=mc.ResourceRequirements(cpu="1", memory="8Gi",
                                          gpu_count=1, gpu_type="nvidia-l4"),
        replica_count=1, namespace="default", service_account="default",
    )
    c.engine_params["log-verbose"] = "1"
    c.engine_params["OMP_NUM_THREADS"] = "1"
    return c


def dump(title, cr):
    print(f"\n{'='*70}\n{title}\n{'='*70}")
    print(yaml.safe_dump(cr, sort_keys=False))


if __name__ == "__main__":
    dump("vLLM/HF (llama)",
         build_inference_service(pb.ENGINE_TYPE_VLLM_HUGGINGFACE, llama_cfg()))
    dump("Triton (bert — same governed core, different engine_params)",
         build_inference_service(pb.ENGINE_TYPE_TRITON, triton_cfg()))
    print(f"\n{'='*70}\nboundary: ENGINE_TYPE_UNSPECIFIED\n{'='*70}")
    try:
        build_inference_service(pb.ENGINE_TYPE_UNSPECIFIED, llama_cfg())
        print("FAIL: unspecified engine was NOT rejected")
    except UnsupportedEngineError as e:
        print(f"OK rejected -> {e}")
