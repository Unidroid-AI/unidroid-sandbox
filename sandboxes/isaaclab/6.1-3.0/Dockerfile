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
# Isaac Sim is the NGC image, not the pip wheel. The pip Kit's RTX shaders fault on driver 580
# (Xid 13, SKEDCHECK05_LOCAL_MEMORY_TOTAL_SIZE) and then PhysX cannot read contacts. This base is the
# binary tree the completed eval used. The build logs in to nvcr.io (versions.lock sets NEEDS_NGC=1).
# Build from this directory (CI does this; validators pull the published digest):
#   set -a && . ./versions.lock && set +a
#   docker build -t ghcr.io/unidroid-ai/sandbox-isaaclab:6.1-3.0 \
#     --build-arg BASE_IMAGE --build-arg ISAACLAB_REPO --build-arg ISAACLAB_COMMIT \
#     --build-arg EVAL_REPO_URL --build-arg EVAL_REPO_COMMIT .

ARG BASE_IMAGE=nvcr.io/nvidia/isaac-sim:6.1.0
FROM ${BASE_IMAGE}

ARG ISAACLAB_REPO=https://github.com/isaac-sim/IsaacLab.git
ARG ISAACLAB_COMMIT
ARG EVAL_REPO_URL=https://github.com/Unidroid-AI/isaac-eval.git
ARG EVAL_REPO_COMMIT

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ACCEPT_EULA=Y \
    PRIVACY_CONSENT=Y \
    OMNI_KIT_ACCEPT_EULA=YES \
    ISAACSIM_PATH=/isaac-sim \
    ISAACLAB_PATH=/isaac-lab \
    TERM=xterm \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UNIDROID_SANDBOX=1 \
    HOME=/opt/unidroid/home \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=all \
    CUDA_MODULE_LOADING=LAZY

# isaaclab.sh refuses a virtualenv that was not created from the bundled Kit Python.
ENV VIRTUAL_ENV=

LABEL org.opencontainers.image.source="https://github.com/Unidroid-AI/unidroid-sandbox" \
      org.opencontainers.image.title="sandbox-isaaclab" \
      ai.unidroid.sandbox.engine="isaaclab" \
      ai.unidroid.sandbox.version="6.1-3.0" \
      ai.unidroid.sandbox.contract="1" \
      ai.unidroid.isaacsim.image="${BASE_IMAGE}" \
      ai.unidroid.isaaclab.commit="${ISAACLAB_COMMIT}" \
      ai.unidroid.eval-deps.commit="${EVAL_REPO_COMMIT}"

USER root
WORKDIR /opt/unidroid

RUN test -n "${ISAACLAB_COMMIT}" || (echo "build with --build-arg ISAACLAB_COMMIT=<commit of Isaac Lab> (see versions.lock)" >&2; exit 1)

# git and a compiler are what Isaac Lab's installer uses for the packages that have no wheel.
# Mesa's libGL and libvulkan are not installed: they override the NVIDIA libraries in the NGC image.
RUN mkdir -p /var/lib/apt/lists/partial \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        git cmake build-essential \
    && rm -rf /var/lib/apt/lists/*

# Isaac Lab at the commit in versions.lock, linked at the NGC binary. No separate torch wheel:
# Kit and RTX must stay on the CUDA this image was built with.
# This Lab pin asks for aiohttp>=3.14.3, which is newer than the copy Isaac Sim 6.1 ships. Upgrading it
# deletes that copy and breaks the extensions that share it, so keep the version already installed.
RUN git init "${ISAACLAB_PATH}" \
    && git -C "${ISAACLAB_PATH}" remote add origin "${ISAACLAB_REPO}" \
    && git -C "${ISAACLAB_PATH}" fetch --depth 1 origin "${ISAACLAB_COMMIT}" \
    && git -C "${ISAACLAB_PATH}" checkout --quiet FETCH_HEAD \
    && ln -sfn "${ISAACSIM_PATH}" "${ISAACLAB_PATH}/_isaac_sim" \
    && cd "${ISAACLAB_PATH}" \
    && aiohttp_ver="$("${ISAACSIM_PATH}/python.sh" -c 'import importlib.metadata as m; print(m.version("aiohttp"))' 2>/dev/null || true)" \
    && if [ -n "${aiohttp_ver}" ]; then \
         sed -i "s/aiohttp>=3.14.3/aiohttp==${aiohttp_ver}/" pyproject.toml; \
       fi \
    && ./isaaclab.sh --install

# Build backends for the pinned sources that are installed at start without network or build isolation.
RUN "${ISAACLAB_PATH}/isaaclab.sh" -p -m pip install --no-cache-dir --upgrade pip \
    && "${ISAACLAB_PATH}/isaaclab.sh" -p -m pip install --no-cache-dir setuptools wheel hatchling msgpack

# Dependencies of isaac-eval, including nepher, which reads the benchmark bundle. An empty
# EVAL_REPO_COMMIT clones the default branch. Only the dependencies stay: the run uses /src/eval.
RUN test -n "${EVAL_REPO_URL}" || (echo "set EVAL_REPO_URL in versions.lock" >&2; exit 1) \
    && git clone "${EVAL_REPO_URL}" /opt/unidroid/eval-deps \
    && if [ -n "${EVAL_REPO_COMMIT}" ]; then \
         git -C /opt/unidroid/eval-deps checkout --quiet "${EVAL_REPO_COMMIT}"; \
       fi \
    && "${ISAACLAB_PATH}/isaaclab.sh" -p -m pip install --no-cache-dir /opt/unidroid/eval-deps \
    && name="$("${ISAACSIM_PATH}/python.sh" -c 'import tomllib; print(tomllib.load(open("/opt/unidroid/eval-deps/pyproject.toml","rb"))["project"]["name"])')" \
    && "${ISAACLAB_PATH}/isaaclab.sh" -p -m pip uninstall -y "${name}" \
    && rm -rf /opt/unidroid/eval-deps

# Writable places Kit uses. The container runs without capabilities, so root needs the mode bits.
# HOME is /opt/unidroid/home, so the ov and ComputeCache mounts from the pip image still apply.
RUN mkdir -p \
        /opt/unidroid/home/.cache/ov \
        /opt/unidroid/home/.nv/ComputeCache \
        /opt/unidroid/home/.nvidia-omniverse/logs \
        /opt/unidroid/home/.nvidia-omniverse/config \
        /opt/unidroid/home/.local/share/ov/data \
        /isaac-sim/kit/data \
        /isaac-sim/kit/cache/DerivedDataCache \
        /isaac-sim/kit/cache/nv_shadercache \
        /opt/unidroid/build /src /benchmark /config /out \
    && chmod -R 777 \
        /opt/unidroid/home /opt/unidroid/build /out \
        /isaac-sim/kit/data /isaac-sim/kit/cache

COPY --chmod=755 entrypoint.sh /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
