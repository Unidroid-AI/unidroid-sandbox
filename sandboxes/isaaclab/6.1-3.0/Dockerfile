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
# Isaac Sim comes from the public pip index (pypi.nvidia.com). That index does not require an NGC API key.
# One version of the Isaac Lab sandbox. The image name is ghcr.io/unidroid-ai/sandbox-isaaclab.
# Build from this directory (CI does this; validators pull the published digest):
#   set -a && . ./versions.lock && set +a
#   docker build -t ghcr.io/unidroid-ai/sandbox-isaaclab:6.1-3.0 \
#     --build-arg BASE_IMAGE --build-arg ISAACSIM_SPEC --build-arg TORCH_VERSION \
#     --build-arg TORCHVISION_VERSION --build-arg TORCH_INDEX \
#     --build-arg ISAACLAB_REPO --build-arg ISAACLAB_COMMIT \
#     --build-arg EVAL_REPO_URL --build-arg EVAL_REPO_COMMIT .

ARG BASE_IMAGE=python:3.12-bookworm
FROM ${BASE_IMAGE}

ARG ISAACSIM_SPEC=isaacsim[all,extscache]==6.1.0.0
ARG TORCH_VERSION=2.11.0
ARG TORCHVISION_VERSION=0.26.0
ARG TORCH_INDEX=https://download.pytorch.org/whl/cu130
ARG ISAACLAB_REPO=https://github.com/isaac-sim/IsaacLab.git
ARG ISAACLAB_COMMIT
ARG EVAL_REPO_URL=https://github.com/Unidroid-AI/isaac-eval.git
ARG EVAL_REPO_COMMIT

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ACCEPT_EULA=Y \
    PRIVACY_CONSENT=Y \
    OMNI_KIT_ACCEPT_EULA=YES \
    VIRTUAL_ENV=/opt/isaaclab-venv \
    ISAACLAB_PATH=/isaac-lab \
    TERM=xterm \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_EXTRA_INDEX_URL=https://pypi.nvidia.com \
    UNIDROID_SANDBOX=1 \
    HOME=/opt/unidroid/home

ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"

LABEL org.opencontainers.image.source="https://github.com/Unidroid-AI/unidroid-sandbox" \
      org.opencontainers.image.title="sandbox-isaaclab" \
      ai.unidroid.sandbox.engine="isaaclab" \
      ai.unidroid.sandbox.version="6.1-3.0" \
      ai.unidroid.sandbox.contract="1" \
      ai.unidroid.isaacsim.spec="${ISAACSIM_SPEC}" \
      ai.unidroid.isaaclab.commit="${ISAACLAB_COMMIT}" \
      ai.unidroid.eval-deps.commit="${EVAL_REPO_COMMIT}"

USER root
WORKDIR /opt/unidroid

RUN test -n "${ISAACLAB_COMMIT}" || (echo "build with --build-arg ISAACLAB_COMMIT=<commit of Isaac Lab> (see versions.lock)" >&2; exit 1)
RUN test -n "${EVAL_REPO_COMMIT}" || (echo "set EVAL_REPO_COMMIT in versions.lock to the isaac-eval commit whose dependencies this image installs" >&2; exit 1)
RUN test -n "${ISAACSIM_SPEC}" || (echo "set ISAACSIM_SPEC in versions.lock" >&2; exit 1)

# Bookworm's glibc is new enough for the Isaac Sim wheels. The libraries are what those wheels load;
# cmake and a compiler are what Isaac Lab's installer uses for the packages that have no wheel.
RUN mkdir -p /var/lib/apt/lists/partial \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        git cmake build-essential \
        libglib2.0-0 libgl1 libglu1-mesa libegl1 libgles2 libgomp1 \
        libsm6 libxext6 libxrender1 libx11-6 libxt6 libxxf86vm1 \
        libxrandr2 libxinerama1 libxcursor1 libxi6 \
        libvulkan1 libusb-1.0-0 \
    && ln -sf /usr/bin/python3 /usr/bin/python \
    && rm -rf /var/lib/apt/lists/*

# Public Isaac Sim, in its own environment so isaaclab.sh -p uses this interpreter.
# Torch is the CUDA build Isaac Lab pins; installing it first keeps pip from pulling a CPU wheel.
RUN python3 -m venv "${VIRTUAL_ENV}" \
    && pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir \
        "torch==${TORCH_VERSION}" "torchvision==${TORCHVISION_VERSION}" \
        --index-url "${TORCH_INDEX}" \
    && pip install --no-cache-dir "${ISAACSIM_SPEC}" --extra-index-url https://pypi.nvidia.com \
    && python -c "from importlib.metadata import version; assert version('isaacsim')"

# Isaac Lab at the commit in versions.lock. No _isaac_sim link: that path is the NGC binary layout.
RUN git init "${ISAACLAB_PATH}" \
    && git -C "${ISAACLAB_PATH}" remote add origin "${ISAACLAB_REPO}" \
    && git -C "${ISAACLAB_PATH}" fetch --depth 1 origin "${ISAACLAB_COMMIT}" \
    && git -C "${ISAACLAB_PATH}" checkout --quiet FETCH_HEAD \
    && cd "${ISAACLAB_PATH}" \
    && ./isaaclab.sh --install

# Build backends for the pinned sources that are installed at start without network or build isolation.
RUN "${ISAACLAB_PATH}/isaaclab.sh" -p -m pip install --no-cache-dir --upgrade pip \
    && "${ISAACLAB_PATH}/isaaclab.sh" -p -m pip install --no-cache-dir setuptools wheel hatchling msgpack

# Dependencies of isaac-eval (and of `nepher`, which it uses to read the benchmark bundle) at the locked commit.
# Only the dependencies stay: the run uses /src/eval.
RUN git clone "${EVAL_REPO_URL}" /opt/unidroid/eval-deps \
    && git -C /opt/unidroid/eval-deps checkout --quiet "${EVAL_REPO_COMMIT}" \
    && "${ISAACLAB_PATH}/isaaclab.sh" -p -m pip install --no-cache-dir /opt/unidroid/eval-deps \
    && "${ISAACLAB_PATH}/isaaclab.sh" -p -m pip uninstall -y isaac-eval \
    && rm -rf /opt/unidroid/eval-deps

# Writable places Kit uses when the container runs without the NGC image's /isaac-sim tree.
# The container runs without capabilities, so root needs the mode bits.
RUN mkdir -p \
        /opt/unidroid/home/.cache/ov \
        /opt/unidroid/home/.nv/ComputeCache \
        /opt/unidroid/home/.nvidia-omniverse/logs \
        /opt/unidroid/home/.nvidia-omniverse/config \
        /opt/unidroid/home/.local/share/ov/data \
        /opt/unidroid/build /src /benchmark /config /out \
    && chmod -R 777 /opt/unidroid/home /opt/unidroid/build /out

COPY --chmod=755 entrypoint.sh /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
