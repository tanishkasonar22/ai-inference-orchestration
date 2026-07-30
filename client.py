import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "generated"))

import grpc
import inference_service_pb2 as pb
import inference_service_pb2_grpc as pb_grpc
import model_config_pb2 as mc


def main():
    channel = grpc.insecure_channel("localhost:50051")
    stub = pb_grpc.InferenceEngineServiceStub(channel)

    # ---- Test 1: a valid request ----
    print("== Test 1: valid vLLM deploy ==")
    req = pb.DeployInferenceEngineRequest(
        engine_type=pb.ENGINE_TYPE_VLLM,
        cluster_ref="inference-cluster",
        model_config=mc.ModelConfig(
            model_id="llama",
            source=mc.ModelSource(uri="gs://intern-501105-model-weights/llama"),
            resources=mc.ResourceRequirements(
                cpu="2", memory="10Gi", gpu_count=1, gpu_type="nvidia-l4"
            ),
            replica_count=1,
            max_model_len=8192,
            engine_params={"tool-call-parser": "llama3_json"},
        ),
    )
    resp = stub.DeployInferenceEngine(req)
    print("  deployment_id:", resp.deployment_id)
    print("  status:", pb.DeploymentStatus.Name(resp.status))
    print("  message:", resp.message)

    # ---- Test 2: an invalid request (no engine type) ----
    print("\n== Test 2: missing engine_type (should be rejected) ==")
    bad = pb.DeployInferenceEngineRequest(cluster_ref="inference-cluster")
    try:
        stub.DeployInferenceEngine(bad)
    except grpc.RpcError as e:
        print("  rejected with code:", e.code().name)
        print("  detail:", e.details())


if __name__ == "__main__":
    main()
