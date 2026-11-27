# MSclips Maker backend (API + worker share this image).
# Ubuntu 24.04 ships FFmpeg 6.1 with libass, the version the renderer is tested against.
FROM ubuntu:24.04

RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-venv ffmpeg fontconfig ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /venv
ENV PATH=/venv/bin:$PATH

WORKDIR /app
COPY pyproject.toml ./
COPY msclips ./msclips
COPY alembic ./alembic
COPY alembic.ini ./
RUN pip install --no-cache-dir .

ENV MSCLIPS_DATA_DIR=/data \
    HF_HOME=/models \
    HF_HUB_DISABLE_XET=1 \
    PYTHONUNBUFFERED=1
VOLUME ["/data", "/models"]
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn msclips.api.main:app --host 0.0.0.0 --port 8000"]
