import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "generated"))

import logging
from concurrent import futures

import grpc
from kubernetes import client, config
from kubernetes.client.rest import ApiException

import inference_service_pb2 as pb
import inference_service_pb2_grpc as pb_grpc
import model_config_pb2 as mc  # noqa: F401  (kept for symmetry / type clarity)

from cr_builder import build_inference_service
from adapters import UnsupportedEngineError

log = logging.getLogger("control-plane")
GROUP, VERSION, PLURAL = "serving.kserve.io", "v1beta1", "inferenceservices"


def _load_kube():
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()


def _ready_status(cr: dict) -> tuple[int, str]:
    for cond in (cr.get("status", {}) or {}).get("conditions", []):
        if cond.get("type") == "Ready":
            if cond.get("status") == "True":
                return pb.DEPLOYMENT_STATUS_READY, "predictor Running and serving"
            return pb.DEPLOYMENT_STATUS_ACCEPTED, cond.get("message", "reconciling")
    return pb.DEPLOYMENT_STATUS_ACCEPTED, "reconciling (no Ready condition yet)"


# Predictor path suffix by engine: vLLM/HF exposes an OpenAI frontend; Triton v2.
_ENGINE_PATH = {"huggingface": "/openai/v1", "triton": "/v2"}


def _predictor_url(cr: dict) -> str:
    """In-cluster predictor URL the caller actually uses.

    KServe's status.url reports the EXTERNAL config-domain host
    (http://<name>-<ns>.example.com), which is a placeholder on our cluster-local
    setup. Per the build log's Finding 6 the model is reachable at
    <name>-predictor.<ns>.svc.cluster.local from the moment the pod runs; the path
    suffix derives from the engine (modelFormat), not from status.url.
    """
    meta = cr.get("metadata") or {}
    name = meta.get("name")
    if not name:
        return ""
    ns = meta.get("namespace") or "default"
    model = ((cr.get("spec") or {}).get("predictor") or {}).get("model") or {}
    fmt = (model.get("modelFormat") or {}).get("name", "")
    return f"http://{name}-predictor.{ns}.svc.cluster.local{_ENGINE_PATH.get(fmt, '')}"


class InferenceEngineServicer(pb_grpc.InferenceEngineServiceServicer):
    def __init__(self):
        _load_kube()
        self.api = client.CustomObjectsApi()

    def DeployInferenceEngine(self, request, context):
        cfg = request.model_config
        if not cfg.model_id:
            return pb.DeployInferenceEngineResponse(
                status=pb.DEPLOYMENT_STATUS_REJECTED,
                message="model_config.model_id is required")
        try:
            cr = build_inference_service(request.engine_type, cfg)
        except UnsupportedEngineError as e:
            return pb.DeployInferenceEngineResponse(
                deployment_id=cfg.model_id,
                status=pb.DEPLOYMENT_STATUS_REJECTED, message=str(e))
        ns = cfg.namespace or "default"
        try:
            self.api.create_namespaced_custom_object(GROUP, VERSION, ns, PLURAL, cr)
            return pb.DeployInferenceEngineResponse(
                deployment_id=cfg.model_id, status=pb.DEPLOYMENT_STATUS_ACCEPTED,
                message="InferenceService applied; reconcile in progress")
        except ApiException as e:
            return pb.DeployInferenceEngineResponse(
                deployment_id=cfg.model_id, status=pb.DEPLOYMENT_STATUS_FAILED,
                message=f"apply failed ({e.status}): {e.reason}")

    def ConfigureModel(self, request, context):
        cfg = request.model_config
        ns = request.namespace or cfg.namespace or "default"
        try:
            existing = self.api.get_namespaced_custom_object(
                GROUP, VERSION, ns, PLURAL, request.deployment_id)
        except ApiException as e:
            if e.status == 404:
                return pb.ConfigureModelResponse(
                    deployment_id=request.deployment_id,
                    status=pb.DEPLOYMENT_STATUS_NOT_FOUND, message="no such deployment")
            raise
        cur_fmt = existing["spec"]["predictor"]["model"]["modelFormat"]["name"]
        try:
            new_cr = build_inference_service(request.engine_type, cfg) \
                if hasattr(request, "engine_type") else None
        except UnsupportedEngineError as e:
            return pb.ConfigureModelResponse(
                deployment_id=request.deployment_id,
                status=pb.DEPLOYMENT_STATUS_REJECTED, message=str(e))
        # ConfigureModel carries no engine_type in the reconciled schema; keep the
        # existing engine and rebuild from its format. Guard against silent change.
        if new_cr is None:
            engine = (pb.ENGINE_TYPE_TRITON if cur_fmt == "triton"
                      else pb.ENGINE_TYPE_VLLM_HUGGINGFACE)
            new_cr = build_inference_service(engine, cfg)
        if new_cr["spec"]["predictor"]["model"]["modelFormat"]["name"] != cur_fmt:
            return pb.ConfigureModelResponse(
                deployment_id=request.deployment_id,
                status=pb.DEPLOYMENT_STATUS_REJECTED,
                message="engine change is breaking; delete and redeploy")
        try:
            self.api.patch_namespaced_custom_object(
                GROUP, VERSION, ns, PLURAL, request.deployment_id, new_cr)
            return pb.ConfigureModelResponse(
                deployment_id=request.deployment_id,
                status=pb.DEPLOYMENT_STATUS_ACCEPTED,
                message="patched; pods roll if the template changed")
        except ApiException as e:
            return pb.ConfigureModelResponse(
                deployment_id=request.deployment_id,
                status=pb.DEPLOYMENT_STATUS_FAILED,
                message=f"patch failed ({e.status}): {e.reason}")

    def GetDeploymentStatus(self, request, context):
        ns = request.namespace or "default"
        try:
            cr = self.api.get_namespaced_custom_object(
                GROUP, VERSION, ns, PLURAL, request.deployment_id)
        except ApiException as e:
            if e.status == 404:
                return pb.GetDeploymentStatusResponse(
                    deployment_id=request.deployment_id,
                    status=pb.DEPLOYMENT_STATUS_NOT_FOUND, message="no such deployment")
            raise
        status, msg = _ready_status(cr)
        url = _predictor_url(cr) if status == pb.DEPLOYMENT_STATUS_READY else ""
        return pb.GetDeploymentStatusResponse(
            deployment_id=request.deployment_id, status=status, message=msg, url=url)

    def DeleteDeployment(self, request, context):
        ns = request.namespace or "default"
        try:
            self.api.delete_namespaced_custom_object(
                GROUP, VERSION, ns, PLURAL, request.deployment_id)
            return pb.DeleteDeploymentResponse(
                deployment_id=request.deployment_id, deleted=True, message="deleted")
        except ApiException as e:
            if e.status == 404:
                return pb.DeleteDeploymentResponse(
                    deployment_id=request.deployment_id, deleted=False,
                    message="already absent")
            return pb.DeleteDeploymentResponse(
                deployment_id=request.deployment_id, deleted=False,
                message=f"delete failed: {e.reason}")


def serve():
    logging.basicConfig(level=logging.INFO)
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    pb_grpc.add_InferenceEngineServiceServicer_to_server(
        InferenceEngineServicer(), server)
    server.add_insecure_port("[::]:50051")
    log.info("InferenceEngineService listening on :50051")
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    serve()