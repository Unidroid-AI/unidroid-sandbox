#!/bin/bash
# MuJoCo sandbox entrypoint. Same contract as the Isaac Lab sandbox: the validator mounts the pinned sources and
# the benchmark, and this script reports through /out/sandbox_status.json.
#
# Exit status: 0 when /out/evaluation_result.json exists; otherwise 4 (install or a mount failed) or 1. Never
# 125-127. Exit 3 is reserved for a sandbox that requires a GPU and cannot see one; MuJoCo does not.
#
# Environment (set by the validator, except the script path, which belongs to this image):
#   UNIDROID_BENCHMARK_ID   id of the benchmark mounted at /benchmark/<id>
#   UNIDROID_EVAL_TIMEOUT   seconds the evaluation may run (default 7200)
#   UNIDROID_EVAL_SCRIPT    eval entrypoint inside the mounted /src/eval (default /src/eval/scripts/evaluate.py)

set -u

OUT=/out
STATUS="${OUT}/sandbox_status.json"
RESULT="${OUT}/evaluation_result.json"
BENCHMARK_ID="${UNIDROID_BENCHMARK_ID:-}"
EVAL_TIMEOUT="${UNIDROID_EVAL_TIMEOUT:-7200}"
EVAL_SCRIPT="${UNIDROID_EVAL_SCRIPT:-/src/eval/scripts/evaluate.py}"
BUILD=/opt/unidroid/build
PY=(python3)

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

[ -f "${EVAL_SCRIPT}" ] || stop install 4 "the eval script is not mounted at ${EVAL_SCRIPT}"
[ -f /config/eval.yaml ] || stop install 4 "the eval config is not mounted at /config/eval.yaml"
[ -f "/benchmark/${BENCHMARK_ID}/manifest.yaml" ] || stop install 4 "the benchmark is not mounted at /benchmark/${BENCHMARK_ID}"
[ -d /src/task ] && [ -d /src/brain-comm ] || stop install 4 "the pinned task package or brain-comm is not mounted"

rm -rf "${BUILD:?}"/*
cp -r /src/brain-comm "${BUILD}/brain-comm" && cp -r /src/task "${BUILD}/task" || stop install 4 "could not copy the pinned sources"
for package in brain-comm task; do
    "${PY[@]}" -m pip install --no-deps --no-build-isolation --no-index --no-cache-dir --quiet "${BUILD}/${package}" \
        || stop install 4 "installing the pinned ${package} package failed"
done
"${PY[@]}" -c "import brain_comm" > /dev/null 2>&1 || stop install 4 "brain_comm cannot be imported after installing it"

export PYTHONPATH="/src/eval${PYTHONPATH:+:${PYTHONPATH}}"
export ISAAC_EVAL_BUNDLE_DIR="/benchmark/${BENCHMARK_ID}"

timeout --kill-after=60 "${EVAL_TIMEOUT}" "${PY[@]}" "${EVAL_SCRIPT}" \
    --config /config/eval.yaml \
    --bundle-dir "${ISAAC_EVAL_BUNDLE_DIR}" \
    --output-dir "${OUT}/eval" \
    --result-path "${RESULT}"
EVAL_EXIT=$?

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
