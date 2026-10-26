# syntax=docker/dockerfile:1
# Build the existing application image first; all services use its accounts/data.
ARG USOPP_IMAGE
FROM ${USOPP_IMAGE}
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg tesseract-ocr tesseract-ocr-eng tesseract-ocr-tam \
    ghostscript qpdf poppler-utils libreoffice-writer libreoffice-calc libreoffice-draw \
    fonts-noto-core fonts-noto-extra fonts-dejavu-core libgl1 \
    && rm -rf /var/lib/apt/lists/*
COPY deploy/intelligence/requirements.txt /opt/usopp/intelligence-requirements.txt
RUN /opt/venv/bin/python -m pip install --no-cache-dir -r /opt/usopp/intelligence-requirements.txt
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/usopp/playwright
RUN /opt/venv/bin/python -m playwright install --with-deps chromium \
    && chmod -R a+rX /opt/usopp/playwright
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 USOPP_PI_WORKER_MODE=external
USER 10001:10001
ENTRYPOINT ["python", "-m", "backend.core.workhub_intelligence.worker"]
