# Control-plane image: gRPC server only. Stubs under generated/ are committed
# (see requirements.txt) so no grpcio-tools / C++ toolchain is needed at build time.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --timeout=100 --retries=5 -r requirements.txt

COPY generated/ generated/
COPY server.py cr_builder.py adapters.py ./

RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 50051
ENTRYPOINT ["python", "server.py"]
