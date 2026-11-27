# One version of the MuJoCo sandbox. The image name is ghcr.io/unidroid-ai/sandbox-mujoco.
#
# It runs the private benchmark and no miner code. It starts with no network, so everything it needs is in this
# image or in the read-only mounts the validator provides at run time:
#
#   /src/eval         the eval package at the commit the challenge pins
#   /src/task         the task package at the commit the challenge pins
#   /benchmark/<id>   the extracted private benchmark
#   /config           eval.yaml
#   /out              evaluation_result.json and sandbox_status.json
#
# brain-comm is part of this image, at the commit in versions.lock, and labelled with its commit and protocol.
# The challenge pins no brain-comm: pinning this image's digest pins its client.
#
# Build from this directory:
#   set -a && . ./versions.lock && set +a
#   docker build -t ghcr.io/unidroid-ai/sandbox-mujoco:4.0.0 \
#     --build-arg BASE_IMAGE --build-arg MUJOCO_VERSION \
#     --build-arg BRAIN_COMM_REPO_URL --build-arg BRAIN_COMM_COMMIT --build-arg BRAIN_COMM_PROTOCOL \
#     --build-arg EVAL_REPO_URL --build-arg EVAL_REPO_COMMIT .
# BRAIN_COMM_PROTOCOL is PROTOCOL_VERSION at BRAIN_COMM_COMMIT; the build fails when the installed package differs.

ARG BASE_IMAGE=python:3.12-slim-bookworm
FROM ${BASE_IMAGE}

ARG MUJOCO_VERSION=4.0.0
ARG EVAL_REPO_URL=
ARG EVAL_REPO_COMMIT=
ARG BRAIN_COMM_REPO_URL=https://github.com/Unidroid-AI/brain-comm.git
ARG BRAIN_COMM_COMMIT
ARG BRAIN_COMM_PROTOCOL

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UNIDROID_SANDBOX=1 \
    UNIDROID_EVAL_SCRIPT=/src/eval/scripts/evaluate.py \
    MUJOCO_GL=egl

LABEL org.opencontainers.image.source="https://github.com/Unidroid-AI/unidroid-sandbox" \
      org.opencontainers.image.title="sandbox-mujoco" \
      ai.unidroid.sandbox.contract="2" \
      ai.unidroid.brain-comm.commit="${BRAIN_COMM_COMMIT}" \
      ai.unidroid.brain-comm.protocol="${BRAIN_COMM_PROTOCOL}" \
      ai.unidroid.sandbox.engine="mujoco" \
      ai.unidroid.sandbox.version="4.0.0" \
      ai.unidroid.mujoco.version="${MUJOCO_VERSION}" \
      ai.unidroid.eval-deps.commit="${EVAL_REPO_COMMIT}"

USER root
WORKDIR /opt/unidroid

RUN test -n "${MUJOCO_VERSION}" || (echo "set MUJOCO_VERSION in versions.lock" >&2; exit 1)

# The base image already provides Python. git fetches an optional eval checkout; the libraries are what the
# MuJoCo wheel loads.
RUN mkdir -p /var/lib/apt/lists/partial \
    && apt-get update \
    && apt-get install -y --no-install-recommends git libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --no-cache-dir --upgrade pip \
    && python3 -m pip install --no-cache-dir "mujoco==${MUJOCO_VERSION}" setuptools wheel hatchling

# brain-comm at the commit in versions.lock, with its dependencies (msgpack, numpy). The build stops when the
# package reports a different protocol than the label this image carries.
RUN test -n "${BRAIN_COMM_COMMIT}" && test -n "${BRAIN_COMM_PROTOCOL}" \
        || (echo "build with --build-arg BRAIN_COMM_COMMIT=<commit> --build-arg BRAIN_COMM_PROTOCOL=<PROTOCOL_VERSION> (see versions.lock)" >&2; exit 1) \
    && git init /opt/unidroid/brain-comm \
    && git -C /opt/unidroid/brain-comm remote add origin "${BRAIN_COMM_REPO_URL}" \
    && git -C /opt/unidroid/brain-comm fetch --depth 1 origin "${BRAIN_COMM_COMMIT}" \
    && git -C /opt/unidroid/brain-comm checkout --quiet FETCH_HEAD \
    && test "$(git -C /opt/unidroid/brain-comm rev-parse HEAD)" = "${BRAIN_COMM_COMMIT}" \
    && python3 -m pip install --no-cache-dir /opt/unidroid/brain-comm \
    && rm -rf /opt/unidroid/brain-comm \
    && test "$(python3 -c 'import brain_comm; print(brain_comm.PROTOCOL_VERSION)')" = "${BRAIN_COMM_PROTOCOL}"

# Optional: dependencies of the eval package named in versions.lock. The package itself is removed, so the
# mounted checkout is what runs.
RUN if [ -n "${EVAL_REPO_COMMIT}" ]; then \
      test -n "${EVAL_REPO_URL}" || (echo "EVAL_REPO_URL is required when EVAL_REPO_COMMIT is set" >&2; exit 1); \
      git clone "${EVAL_REPO_URL}" /opt/unidroid/eval-deps \
      && git -C /opt/unidroid/eval-deps checkout --quiet "${EVAL_REPO_COMMIT}" \
      && git -C /opt/unidroid/eval-deps rev-parse HEAD > /opt/unidroid/eval-deps.commit \
      && python3 -m pip install --no-cache-dir /opt/unidroid/eval-deps \
      && name=$(python3 -c 'import tomllib; print(tomllib.load(open("/opt/unidroid/eval-deps/pyproject.toml","rb"))["project"]["name"])') \
      && python3 -m pip uninstall -y "${name}" \
      && rm -rf /opt/unidroid/eval-deps; \
    fi

RUN mkdir -p /opt/unidroid/build /src /benchmark /config /out \
    && chmod 777 /opt/unidroid/build /out

COPY --chmod=755 entrypoint.sh /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
