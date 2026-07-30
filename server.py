import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "generated"))

from concurrent import futures
import grpc

import inference_service_pb2 as pb
import inference_service_pb2_grpc as pb_grpc


class InferenceEngineServicer(pb_grpc.InferenceEngineServiceServicer):
    def DeployInferenceEngine(self, request, context):
        # REQ-1.1: reject unknown/unspecified engine types at validation.
        if request.engine_type == pb.ENGINE_TYPE_UNSPECIFIED:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details("engine_type is required and must be a supported type")
            return pb.DeployInferenceEngineResponse()

        if request.engine_type != pb.ENGINE_TYPE_VLLM:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details("unsupported engine_type")
            return pb.DeployInferenceEngineResponse()

        # Basic validation of required fields.
        if not request.model_config.model_id:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details("model_config.model_id is required")
            return pb.DeployInferenceEngineResponse()

        # Happy path: pretend-deploy and report PENDING.
        # (Phase 3 will replace this with a real Kubernetes deployment.)
        deployment_id = f"{request.model_config.model_id}-deployment"
        print(f"[server] Deploy requested: {deployment_id} "
              f"engine=vLLM cluster={request.cluster_ref}")

        return pb.DeployInferenceEngineResponse(
            deployment_id=deployment_id,
            status=pb.DEPLOYMENT_STATUS_PENDING,
            message="Deployment accepted (stub — no real cluster action yet)",
        )


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    pb_grpc.add_InferenceEngineServiceServicer_to_server(
        InferenceEngineServicer(), server
    )
    server.add_insecure_port("[::]:50051")
    print("[server] Listening on :50051")
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
