# Inference Orchestration

gRPC control plane for deploying inference engines (vLLM, etc.) on Kubernetes.

## Status
Early development — building the control plane per the Stage 1 requirements.

## Local dev
Local inference runs via Ollama in Docker (CPU) as a stand-in for vLLM.
See docker-compose.ollama.yml.

## Packaging (REQ-1.3)
- `Dockerfile` builds the control-plane image (gRPC server only; committed
  `generated/` stubs, no build-time protoc step).
- `charts/inference-control-plane/` is the Helm chart. It assumes KServe +
  cert-manager are already installed on the target cluster (see the build
  log) — it only deploys the control-plane Deployment/Service/RBAC, scoped to
  `inferenceservices.serving.kserve.io` in the configured namespaces (no
  cluster-admin).

```
docker build -t inference-control-plane:0.1.0 .
helm install control-plane ./charts/inference-control-plane \
  --set image.repository=inference-control-plane --set image.tag=0.1.0
```
