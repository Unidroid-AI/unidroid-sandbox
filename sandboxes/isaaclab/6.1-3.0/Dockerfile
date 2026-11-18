# Unidroid evaluation sandbox: Isaac Sim 6.1 binary + Isaac Lab 3.0 + isaac-eval's dependencies.
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
# The simulator is the Isaac Sim 6.1.0 binary (nvcr.io/nvidia/isaac-sim:6.1.0), not the public isaacsim pip wheel.
# On driver 580 the wheel steps physics, but its RTX cameras do not match the binary: the same policy scored about
# 0 there and about 0.47 here. Do not pip-install isaacsim into this image. The build pulls the binary from nvcr.io,
# so versions.lock sets NEEDS_NGC=1.
# One version of the Isaac Lab sandbox. The image name is ghcr.io/unidroid-ai/sandbox-isaaclab.
# Build from this directory (CI does this; validators pull the published digest):
#   set -a && . ./versions.lock && set +a
#   docker build -t ghcr.io/unidroid-ai/sandbox-isaaclab:6.1-3.0 \
#     --build-arg BASE_IMAGE --build-arg ISAACLAB_REPO --build-arg ISAACLAB_COMMIT \
#     --build-arg EVAL_REPO_URL --build-arg EVAL_REPO_COMMIT .

ARG BASE_IMAGE=nvcr.io/nvidia/isaac-sim:6.1.0
FROM ${BASE_IMAGE}

ARG BASE_IMAGE
ARG ISAACLAB_REPO=https://github.com/isaac-sim/IsaacLab.git
ARG ISAACLAB_COMMIT
ARG EVAL_REPO_URL=https://github.com/Unidroid-AI/isaac-eval.git
ARG EVAL_REPO_COMMIT

# No VIRTUAL_ENV. isaaclab.sh rejects a foreign virtualenv once _isaac_sim is the binary,
# and the binary's python.sh is the interpreter the entrypoint calls.
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
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=all \
    CUDA_MODULE_LOADING=LAZY

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

# git fetches the pinned Lab commit. cmake is what Lab's installer compiles when a wheel is missing.
# The binary already ships the NVIDIA graphics stack, so Mesa's libGL and libvulkan stay uninstalled.
RUN mkdir -p /var/lib/apt/lists/partial \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        git ca-certificates cmake build-essential \
    && rm -rf /var/lib/apt/lists/*

# Isaac Lab at the commit in versions.lock, linked at the NGC binary. --install does not take the
# isaacsim extra, so the pip wheel never replaces /isaac-sim. This Lab pin asks for aiohttp>=3.14.3,
# which is newer than the copy Isaac Sim 6.1 ships. Upgrading it deletes that copy and breaks the
# extensions that share it, so keep the version already installed.
RUN git init "${ISAACLAB_PATH}" \
    && git -C "${ISAACLAB_PATH}" remote add origin "${ISAACLAB_REPO}" \
    && git -C "${ISAACLAB_PATH}" fetch --depth 1 origin "${ISAACLAB_COMMIT}" \
    && git -C "${ISAACLAB_PATH}" checkout --quiet FETCH_HEAD \
    && ln -s /isaac-sim "${ISAACLAB_PATH}/_isaac_sim" \
    && aiohttp_ver="$(/isaac-sim/python.sh -c 'from importlib.metadata import version; print(version("aiohttp"))' 2>/dev/null || true)" \
    && if [ -n "${aiohttp_ver}" ]; then \
         sed -i "s/aiohttp>=3.14.3/aiohttp==${aiohttp_ver}/" "${ISAACLAB_PATH}/pyproject.toml"; \
       fi \
    && cd "${ISAACLAB_PATH}" \
    && ./isaaclab.sh --install \
    && test -e /isaac-sim/python.sh

# Build backends for the pinned sources that are installed at start without network or build isolation.
# brain-comm imports msgpack, and this binary's Python does not ship it. The entrypoint installs
# brain-comm with --no-deps, so the dependency has to already be here.
RUN "${ISAACLAB_PATH}/isaaclab.sh" -p -m ensurepip --upgrade \
    && "${ISAACLAB_PATH}/isaaclab.sh" -p -m pip install --no-cache-dir --upgrade pip \
    && "${ISAACLAB_PATH}/isaaclab.sh" -p -m pip install --no-cache-dir setuptools wheel hatchling msgpack \
    && "${ISAACLAB_PATH}/isaaclab.sh" -p -c "import msgpack"

# Dependencies of isaac-eval, including nepher, which reads the benchmark bundle. An empty
# EVAL_REPO_COMMIT clones the default branch. Only the dependencies stay: the run uses /src/eval.
RUN test -n "${EVAL_REPO_URL}" || (echo "set EVAL_REPO_URL in versions.lock" >&2; exit 1) \
    && git clone "${EVAL_REPO_URL}" /opt/unidroid/eval-deps \
    && if [ -n "${EVAL_REPO_COMMIT}" ]; then \
         git -C /opt/unidroid/eval-deps checkout --quiet "${EVAL_REPO_COMMIT}"; \
       fi \
    && "${ISAACLAB_PATH}/isaaclab.sh" -p -m pip install --no-cache-dir /opt/unidroid/eval-deps \
    && name="$("${ISAACLAB_PATH}/_isaac_sim/python.sh" -c 'import tomllib; print(tomllib.load(open("/opt/unidroid/eval-deps/pyproject.toml","rb"))["project"]["name"])')" \
    && "${ISAACLAB_PATH}/isaaclab.sh" -p -m pip uninstall -y "${name}" \
    && rm -rf /opt/unidroid/eval-deps

# Kit writes caches next to the binary and under the usual XDG paths. The container runs without
# capabilities, so root needs the mode bits. /opt/unidroid/build is the entrypoint's install copy.
RUN mkdir -p \
        /isaac-sim/kit/data \
        /isaac-sim/kit/cache \
        /isaac-sim/.cache \
        /isaac-sim/.nv/ComputeCache \
        /isaac-sim/.nvidia-omniverse/logs \
        /isaac-sim/.nvidia-omniverse/config \
        /isaac-sim/.local/share/ov/data \
        /root/.cache/ov \
        /root/.cache/nvidia/GLCache \
        /root/.nv/ComputeCache \
        /opt/unidroid/build /src /benchmark /config /out \
    && chmod -R 777 \
        /isaac-sim/kit/data \
        /isaac-sim/kit/cache \
        /isaac-sim/.cache \
        /isaac-sim/.nv \
        /isaac-sim/.nvidia-omniverse \
        /isaac-sim/.local \
        /root/.cache \
        /root/.nv \
        /opt/unidroid/build \
        /out

COPY --chmod=755 entrypoint.sh /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
