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
docker build -t inference-control-plane:0.2.0 .
helm install control-plane ./charts/inference-control-plane \
  --set image.repository=inference-control-plane --set image.tag=0.2.0
```

## API auth (mTLS)
The gRPC API (:50051) is unauthenticated by default (`tls.enabled=false`) so
a fresh install doesn't require certs to exist first. Set `tls.enabled=true`
to require a valid client cert on every connection (self-signed CA -> server
cert + client cert, all via cert-manager, covers all four RPCs at the
transport layer — see `charts/inference-control-plane/templates/certificates.yaml`).
After enabling, extract your client cert (commands in `helm install`'s NOTES
output) and point `client.py` at it via `TLS_CERT_DIR` (and
`TLS_SERVER_NAME_OVERRIDE` if connecting through a port-forward rather than
the in-cluster Service name).

## GetDeploymentStatus URL
Returns the real in-cluster predictor URL (`http://<id>-predictor.<ns>.svc.cluster.local/...`),
not KServe's own placeholder `.status.url` (which is a non-resolvable
`*.example.com` host while external ingress is disabled).
