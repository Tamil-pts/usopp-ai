# syntax=docker/dockerfile:1
FROM node:24-bookworm-slim AS frontend
WORKDIR /build
COPY package*.json ./
COPY nami/package*.json ./nami/
RUN npm ci --no-audit --no-fund && npm --prefix nami ci --no-audit --no-fund
COPY index.html tsconfig*.json vite.config.ts ./
COPY src ./src
COPY nami ./nami
COPY scripts/build_nami.mjs ./scripts/build_nami.mjs
RUN npm run build

# Same pinned llama.cpp CPU release used by the Windows runtime.
FROM debian:bookworm-slim AS llama_cpu
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates git cmake build-essential && rm -rf /var/lib/apt/lists/*
WORKDIR /llama
RUN git init && git remote add origin https://github.com/ggml-org/llama.cpp.git \
    && git fetch --depth 1 origin 7e8324f5feba1d8be3f966e1791e84107e40cdd7 \
    && git checkout --detach FETCH_HEAD
RUN cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=OFF \
    -DGGML_AVX=OFF -DGGML_AVX2=OFF -DGGML_FMA=OFF -DGGML_F16C=OFF \
    -DBUILD_SHARED_LIBS=OFF -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_SERVER=ON \
    -DLLAMA_OPENSSL=OFF -DLLAMA_BUILD_APP=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_USE_PREBUILT_UI=OFF \
    && cmake --build build --target llama-server -j 2

FROM python:3.12-slim-bookworm AS compiler
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends build-essential pkg-config libcairo2-dev && rm -rf /var/lib/apt/lists/*
COPY backend_requirements.txt ./
RUN python -m venv /opt/venv && /opt/venv/bin/python -m pip install --no-cache-dir -r backend_requirements.txt
COPY backend ./backend
COPY python_engine ./python_engine
COPY scripts/package_container.py scripts/container_bootstrap.py scripts/container_maintenance.py ./scripts/
COPY knowledge/master ./knowledge/master
COPY knowledge/data_models ./knowledge/data_models
COPY knowledge/chopper ./knowledge/chopper
COPY knowledge/help_index ./knowledge/help_index
COPY rules ./rules
COPY src/usopp_logo.png src/petrus_logo.png ./src/
COPY local_ai/MODEL_LICENSE.txt local_ai/MODEL_CARD.md ./local_ai/
COPY package.json ./
COPY --from=frontend /build/dist ./dist
RUN /opt/venv/bin/python scripts/package_container.py --output /compiled

FROM python:3.12-slim-bookworm AS runtime
ARG APP_VERSION
LABEL org.opencontainers.image.title="uSOPp.ai" org.opencontainers.image.version="${APP_VERSION}"
RUN apt-get update && apt-get install -y --no-install-recommends libcairo2 fonts-dejavu-core libgomp1 libstdc++6 ca-certificates && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 usopp && useradd --uid 10001 --gid usopp --home-dir /data --no-create-home usopp \
    && mkdir /data && chown usopp:usopp /data
COPY --from=compiler /opt/venv /opt/venv
COPY --from=compiler /compiled /opt/usopp
COPY --from=llama_cpu /llama/build/bin/llama-server /opt/usopp/local_ai/runtime/llama-server
COPY --from=llama_cpu /llama/LICENSE /opt/usopp/local_ai/runtime/LICENSE.txt
COPY --chmod=755 deploy/container/entrypoint.sh /usr/local/bin/usopp-start
ENV PATH="/opt/venv/bin:$PATH" PYTHONPATH="/opt/usopp:/opt/usopp/python_engine" PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    USOPP_DATA_ROOT=/data HOME=/data USOPP_MAX_USERS=6 USOPP_MAX_PARALLEL_TESTS=5
WORKDIR /opt/usopp
USER 10001:10001
EXPOSE 8200
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8200/api/health', timeout=4)" || exit 1
ENTRYPOINT ["usopp-start"]
