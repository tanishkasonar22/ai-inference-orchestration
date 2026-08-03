"""Smoke-test client for the control-plane gRPC API — exercises the exact
pipeline an end user (caller) goes through: deploy, poll status, delete.

Usage:
  python client.py deploy   # DeployInferenceEngine + poll GetDeploymentStatus
  python client.py status   # GetDeploymentStatus once
  python client.py delete   # DeleteDeployment (cleanup)

Assumes a port-forward to the control-plane Service is already running:
  kubectl port-forward svc/<release-name> 50051:50051 -n default
"""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "generated"))

import grpc
import inference_service_pb2 as pb
import inference_service_pb2_grpc as pb_grpc
import model_config_pb2 as mc

# Fresh model_id — deliberately NOT "llama", so this never collides with the
# already-deployed llama/qwen/deepseek InferenceServices. Reuses llama's
# already-staged GCS weights, so no new download/staging is needed.
TEST_MODEL_ID = "llama-e2e-test"
NAMESPACE = "default"


def _stub():
    channel = grpc.insecure_channel("localhost:50051")
    return pb_grpc.InferenceEngineServiceStub(channel)


def _test_config() -> mc.ModelConfig:
    cfg = mc.ModelConfig(
        model_id=TEST_MODEL_ID,
        namespace=NAMESPACE,
        service_account="default",
        source=mc.ModelSource(uri="gs://intern-501105-model-weights/llama"),
        resources=mc.ResourceRequirements(
            cpu="6", memory="24Gi", gpu_count=1, gpu_type="nvidia-l4"
        ),
        replica_count=1,
    )
    cfg.engine_params["max-model-len"] = "8192"
    cfg.engine_params["gpu-memory-utilization"] = "0.90"
    cfg.engine_params["enable-auto-tool-choice"] = ""
    cfg.engine_params["tool-call-parser"] = "llama3_json"
    return cfg


def deploy():
    stub = _stub()

    print("== Deploy: valid vLLM/HF request ==")
    req = pb.DeployInferenceEngineRequest(
        engine_type=pb.ENGINE_TYPE_VLLM_HUGGINGFACE,
        cluster_ref="inference-cluster",
        model_config=_test_config(),
    )
    resp = stub.DeployInferenceEngine(req)
    print("  deployment_id:", resp.deployment_id)
    print("  status:", pb.DeploymentStatus.Name(resp.status))
    print("  message:", resp.message)
    if resp.status != pb.DEPLOYMENT_STATUS_ACCEPTED:
        return

    print("\n== Deploy: invalid request (missing model_id) — should be REJECTED"
          " in-band, not a gRPC error ==")
    bad = pb.DeployInferenceEngineRequest(
        engine_type=pb.ENGINE_TYPE_VLLM_HUGGINGFACE,
        cluster_ref="inference-cluster",
        model_config=mc.ModelConfig(),
    )
    bad_resp = stub.DeployInferenceEngine(bad)
    print("  status:", pb.DeploymentStatus.Name(bad_resp.status))
    print("  message:", bad_resp.message)

    print(f"\n== Polling GetDeploymentStatus for '{TEST_MODEL_ID}' "
          "(Ctrl+C to stop watching) ==")
    for _ in range(40):  # ~10 min at 15s intervals
        status_resp = stub.GetDeploymentStatus(pb.GetDeploymentStatusRequest(
            deployment_id=TEST_MODEL_ID, namespace=NAMESPACE))
        name = pb.DeploymentStatus.Name(status_resp.status)
        print(f"  status={name} message={status_resp.message!r} url={status_resp.url!r}")
        if status_resp.status in (pb.DEPLOYMENT_STATUS_READY, pb.DEPLOYMENT_STATUS_FAILED):
            break
        time.sleep(15)


def status():
    stub = _stub()
    resp = stub.GetDeploymentStatus(pb.GetDeploymentStatusRequest(
        deployment_id=TEST_MODEL_ID, namespace=NAMESPACE))
    print("status:", pb.DeploymentStatus.Name(resp.status))
    print("message:", resp.message)
    print("url:", resp.url)


def delete():
    stub = _stub()
    resp = stub.DeleteDeployment(pb.DeleteDeploymentRequest(
        deployment_id=TEST_MODEL_ID, namespace=NAMESPACE))
    print("deleted:", resp.deleted)
    print("message:", resp.message)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "deploy"
    {"deploy": deploy, "status": status, "delete": delete}[cmd]()
