#!/bin/bash
# Unidroid sandbox entrypoint: install the pinned sources offline, run isaac-eval against the brain, report.
#
# It writes /out/sandbox_status.json so the validator can tell "this host could not run the sandbox" (stage gpu or
# install: never the miner's fault) from "the evaluation ran and produced nothing" (stage eval).
#
# Exit status: 0 when /out/evaluation_result.json exists, whatever Isaac did on shutdown; otherwise 3 (no GPU),
# 4 (install failed) or 1. Never 125-127: the validator reads those as "docker could not run the container".
#
# Environment (set by the validator):
#   UNIDROID_BENCHMARK_ID   id of the benchmark mounted at /benchmark/<id>
#   UNIDROID_EVAL_TIMEOUT   seconds the evaluation may run (default 7200)

set -u

OUT=/out
STATUS="${OUT}/sandbox_status.json"
RESULT="${OUT}/evaluation_result.json"
ISAACLAB_PATH="${ISAACLAB_PATH:-/isaac-lab}"
PY=("${ISAACLAB_PATH}/isaaclab.sh" -p)
BENCHMARK_ID="${UNIDROID_BENCHMARK_ID:-}"
EVAL_TIMEOUT="${UNIDROID_EVAL_TIMEOUT:-7200}"
BUILD=/opt/unidroid/build

status() {  # status <stage> <code> <exit_code>
    printf '{"stage": "%s", "code": %s, "exit_code": %s}\n' "$1" "$2" "$3" > "${STATUS}"
    chmod 0644 "${STATUS}" 2> /dev/null || true
}

stop() {  # stop <stage> <exit status> <message>
    echo "[sandbox] $3" >&2
    status "$1" "$2" "$2"
    exit "$2"
}

rm -f "${RESULT}" "${STATUS}"

[[ "${BENCHMARK_ID}" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$ ]] || stop install 4 "UNIDROID_BENCHMARK_ID is missing or invalid"
[[ "${EVAL_TIMEOUT}" =~ ^[0-9]+$ ]] || stop install 4 "UNIDROID_EVAL_TIMEOUT is not a number"

echo "[sandbox] benchmark ${BENCHMARK_ID}, timeout ${EVAL_TIMEOUT}s"

# ---- 1. GPU
nvidia-smi > /dev/null 2>&1 || stop gpu 3 "no GPU is visible in the sandbox"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader

# ---- 2. Everything the run needs must be mounted
[ -f /src/eval/isaac_eval/scripts/evaluate.py ] || stop install 4 "isaac-eval is not mounted at /src/eval"
[ -f /config/eval.yaml ] || stop install 4 "the eval config is not mounted at /config/eval.yaml"
[ -f "/benchmark/${BENCHMARK_ID}/manifest.yaml" ] || stop install 4 "the benchmark is not mounted at /benchmark/${BENCHMARK_ID}"
[ -d /src/task ] && [ -d /src/brain-comm ] || stop install 4 "the pinned task package or brain-comm is not mounted"

# ---- 3. Install the pinned task package and brain-comm from copies: no network, no dependencies, no build
#         isolation. The mounts are read-only and pip builds in the source tree, so it works on copies.
rm -rf "${BUILD:?}"/*
cp -r /src/brain-comm "${BUILD}/brain-comm" && cp -r /src/task "${BUILD}/task" || stop install 4 "could not copy the pinned sources"
for package in brain-comm task; do
    "${PY[@]}" -m pip install --no-deps --no-build-isolation --no-index --no-cache-dir --quiet "${BUILD}/${package}" \
        || stop install 4 "installing the pinned ${package} package failed"
done
"${PY[@]}" -c "import brain_comm" > /dev/null 2>&1 || stop install 4 "brain_comm cannot be imported after installing it"

# ---- 4. Evaluate. isaac-eval runs from the pinned mount. In `runtime: brain` it starts one Isaac process per GPU
#         and connects to the brain sockets named by the config.
export PYTHONPATH="/src/eval${PYTHONPATH:+:${PYTHONPATH}}"
export ISAAC_EVAL_BUNDLE_DIR="/benchmark/${BENCHMARK_ID}"

# Isaac Sim 6 / Python 3.12 need the 'spawn' start method; the bootstrap also re-routes argv so evaluate.py is __main__.
BOOTSTRAP="import multiprocessing, sys; multiprocessing.set_start_method('spawn', force=True); sys.argv = sys.argv[1:]; import runpy; runpy.run_path(sys.argv[0], run_name='__main__')"

# A non-zero exit after a successful run is common (Isaac hangs or crashes on shutdown, and `timeout` returns 124),
# so the exit code alone decides nothing: the result file does. (No `set -e` here: every step is checked on purpose.)
timeout --kill-after=60 "${EVAL_TIMEOUT}" "${PY[@]}" -c "${BOOTSTRAP}" /src/eval/isaac_eval/scripts/evaluate.py \
    --config /config/eval.yaml \
    --bundle-dir "${ISAAC_EVAL_BUNDLE_DIR}" \
    --output-dir "${OUT}/eval" \
    --result-path "${RESULT}"
EVAL_EXIT=$?

# ---- 5. Report
if [ ! -f "${RESULT}" ] && [ -f "${OUT}/eval/evaluation_result.json" ]; then
    cp "${OUT}/eval/evaluation_result.json" "${RESULT}"
fi
if [ -f "${RESULT}" ]; then
    chmod 0644 "${RESULT}"
    status eval 0 "${EVAL_EXIT}"
    echo "[sandbox] done (evaluation exit ${EVAL_EXIT}); result written"
    exit 0
fi
status eval 0 "${EVAL_EXIT}"
echo "[sandbox] the evaluation ended without a result (exit ${EVAL_EXIT})" >&2
exit 1
