# Unidroid evaluation sandbox: Isaac Sim 6.1 + Isaac Lab 3.0 + the dependencies of isaac-eval.
#
# It runs the private benchmark and no miner code (the miner's brain runs in a separate container). It starts with
# no network, so everything it needs is in this image or in the read-only mounts the validator provides at run time:
#
#   /src/eval         isaac-eval at the commit pinned in the validator config   (run from here, never from this image)
#   /src/task         the task package at its pinned commit                     (installed at start, offline)
#   /src/brain-comm   brain-comm at the validator's pin                         (installed at start, offline)
#   /benchmark/<id>   the extracted private benchmark
#   /config           eval.yaml, the challenge's eval config, unchanged
#   /out              evaluation_result.json and sandbox_status.json are written here
#
# Pins for Sim, Lab and the dependency set live in versions.lock, not in the validator. This image installs only
# what those sources depend on. The isaac-eval copy below is used to pull in its dependencies and is then removed,
# so a stale copy can never run.
#
# One version of the Isaac Lab sandbox. The image name is ghcr.io/unidroid-ai/sandbox-isaaclab.
# Build from this directory (CI does this; validators pull the published digest):
#   set -a && . ./versions.lock && set +a
#   docker build -t ghcr.io/unidroid-ai/sandbox-isaaclab:6.1-3.0 \
#     --build-arg ISAACSIM_IMAGE --build-arg ISAACLAB_REPO --build-arg ISAACLAB_COMMIT \
#     --build-arg EVAL_REPO_URL --build-arg EVAL_REPO_COMMIT .

ARG ISAACSIM_IMAGE=nvcr.io/nvidia/isaac-sim:6.1.0
FROM ${ISAACSIM_IMAGE}

ARG ISAACLAB_REPO=https://github.com/isaac-sim/IsaacLab.git
ARG ISAACLAB_COMMIT
ARG EVAL_REPO_URL=https://github.com/Unidroid-AI/isaac-eval.git
ARG EVAL_REPO_COMMIT

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ACCEPT_EULA=Y \
    PRIVACY_CONSENT=Y \
    ISAACSIM_PATH=/isaac-sim \
    ISAACLAB_PATH=/isaac-lab \
    TERM=xterm \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UNIDROID_SANDBOX=1

LABEL org.opencontainers.image.source="https://github.com/Unidroid-AI/unidroid-sandbox" \
      org.opencontainers.image.title="sandbox-isaaclab" \
      ai.unidroid.sandbox.engine="isaaclab" \
      ai.unidroid.sandbox.version="6.1-3.0" \
      ai.unidroid.sandbox.contract="1" \
      ai.unidroid.isaaclab.commit="${ISAACLAB_COMMIT}" \
      ai.unidroid.eval-deps.commit="${EVAL_REPO_COMMIT}"

USER root
WORKDIR /opt/unidroid

RUN test -n "${ISAACLAB_COMMIT}" || (echo "build with --build-arg ISAACLAB_COMMIT=<commit of Isaac Lab> (see versions.lock)" >&2; exit 1)
RUN test -n "${EVAL_REPO_COMMIT}" || (echo "set EVAL_REPO_COMMIT in versions.lock to the isaac-eval commit whose dependencies this image installs" >&2; exit 1)

RUN mkdir -p /var/lib/apt/lists/partial \
    && apt-get update \
    && apt-get install -y --no-install-recommends git python3 \
    && ln -sf /usr/bin/python3 /usr/bin/python \
    && rm -rf /var/lib/apt/lists/*

# Isaac Lab at the commit in versions.lock, on top of the binary Isaac Sim.
RUN git init "${ISAACLAB_PATH}" \
    && git -C "${ISAACLAB_PATH}" remote add origin "${ISAACLAB_REPO}" \
    && git -C "${ISAACLAB_PATH}" fetch --depth 1 origin "${ISAACLAB_COMMIT}" \
    && git -C "${ISAACLAB_PATH}" checkout --quiet FETCH_HEAD \
    && ln -s "${ISAACSIM_PATH}" "${ISAACLAB_PATH}/_isaac_sim" \
    && cd "${ISAACLAB_PATH}" \
    && ./isaaclab.sh --install

# Build backends for the pinned sources that are installed at start without network or build isolation.
RUN "${ISAACLAB_PATH}/isaaclab.sh" -p -m ensurepip --upgrade \
    && "${ISAACLAB_PATH}/isaaclab.sh" -p -m pip install --no-cache-dir --upgrade pip \
    && "${ISAACLAB_PATH}/isaaclab.sh" -p -m pip install --no-cache-dir setuptools wheel hatchling msgpack

# Dependencies of isaac-eval (and of `nepher`, which it uses to read the benchmark bundle) at the locked commit.
# Only the dependencies stay: the run uses /src/eval.
RUN git clone "${EVAL_REPO_URL}" /opt/unidroid/eval-deps \
    && git -C /opt/unidroid/eval-deps checkout --quiet "${EVAL_REPO_COMMIT}" \
    && "${ISAACLAB_PATH}/isaaclab.sh" -p -m pip install --no-cache-dir /opt/unidroid/eval-deps \
    && "${ISAACLAB_PATH}/isaaclab.sh" -p -m pip uninstall -y isaac-eval \
    && rm -rf /opt/unidroid/eval-deps

# Writable places Isaac Sim / Kit need. The container runs without capabilities, so root needs the mode bits.
RUN mkdir -p \
        /isaac-sim/kit/data /isaac-sim/kit/cache/DerivedDataCache /isaac-sim/kit/cache/nv_shadercache \
        /isaac-sim/.cache /isaac-sim/.nv/ComputeCache /isaac-sim/.nvidia-omniverse/logs \
        /isaac-sim/.nvidia-omniverse/config /isaac-sim/.local/share/ov/data /isaac-sim/.local/share/ov/pkg \
        /opt/unidroid/build /src /benchmark /config /out \
    && chmod -R 777 /isaac-sim/kit/data /isaac-sim/kit/cache /isaac-sim/.cache /isaac-sim/.nv \
        /isaac-sim/.nvidia-omniverse /isaac-sim/.local /opt/unidroid/build

COPY --chmod=755 entrypoint.sh /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
