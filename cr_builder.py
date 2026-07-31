"""ModelConfig (+ engine_type) -> KServe InferenceService dict.

Governed core assembled identically for every engine; engine-specifics delegated
to the adapter. Autopilot Finding 5 (explicit GPU node selector) applied here.
"""

from __future__ import annotations
import model_config_pb2 as mc
from adapters import get_adapter

GKE_ACCEL_KEY = "cloud.google.com/gke-accelerator"
GKE_ACCEL_COUNT_KEY = "cloud.google.com/gke-accelerator-count"


def _resources(cfg: mc.ModelConfig) -> dict:
    limits: dict[str, str] = {}
    if cfg.resources.cpu:
        limits["cpu"] = cfg.resources.cpu
    if cfg.resources.memory:
        limits["memory"] = cfg.resources.memory
    if cfg.resources.gpu_count > 0:
        limits["nvidia.com/gpu"] = str(cfg.resources.gpu_count)
    return {"limits": dict(limits), "requests": dict(limits)}


def build_inference_service(engine_type: int, cfg: mc.ModelConfig) -> dict:
    """Return a KServe InferenceService dict. Raises UnsupportedEngineError for
    an unspecified/unknown engine (REQ-1.1). engine_type comes from the request,
    not from ModelConfig (matches the reconciled API shape)."""
    adapter = get_adapter(engine_type)  # boundary validation

    model_spec: dict = {"modelFormat": {"name": adapter.model_format}}
    if adapter.protocol_version:
        model_spec["protocolVersion"] = adapter.protocol_version

    model_spec["storageUri"] = cfg.source.uri
    model_spec["resources"] = _resources(cfg)

    params = dict(cfg.engine_params)
    args = adapter.render_args(params)
    if args:
        model_spec["args"] = args
    env = adapter.model_env(params)
    if env:
        model_spec["env"] = env

    predictor: dict = {"model": model_spec}
    if cfg.replica_count:
        predictor["minReplicas"] = cfg.replica_count
        predictor["maxReplicas"] = cfg.replica_count
    if cfg.service_account:
        predictor["serviceAccountName"] = cfg.service_account
    if cfg.resources.gpu_type:
        predictor["nodeSelector"] = {
            GKE_ACCEL_KEY: cfg.resources.gpu_type,
            GKE_ACCEL_COUNT_KEY: str(max(cfg.resources.gpu_count, 1)),
        }

    namespace = cfg.namespace or "default"
    return {
        "apiVersion": "serving.kserve.io/v1beta1",
        "kind": "InferenceService",
        "metadata": {"name": cfg.model_id, "namespace": namespace},
        "spec": {"predictor": predictor},
    }
