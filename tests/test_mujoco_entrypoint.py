# Copyright (c) 2026, Unidroid
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

"""The MuJoCo entrypoint's control flow, run with a stub python. It must report the same status file and exit
codes as the Isaac Lab entrypoint, and it must run without a GPU."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "sandboxes" / "mujoco" / "4.0.0" / "entrypoint.sh"
BENCHMARK_ID = "franka-tabletop-v13"

FAKE_PYTHON = """#!/bin/bash
if [ "$1" = "-m" ]; then
    [ -n "${FAKE_PIP_FAIL:-}" ] && exit 1
    echo "pip $*" >> "${FAKE_LOG}"
    exit 0
fi
if [ "$1" = "-c" ]; then
    [ -n "${FAKE_IMPORT_FAIL:-}" ] && exit 1
    exit 0
fi
echo "eval $*" >> "${FAKE_LOG}"
echo "PYTHONPATH=${PYTHONPATH}" >> "${FAKE_LOG}"
echo "BUNDLE=${ISAAC_EVAL_BUNDLE_DIR}" >> "${FAKE_LOG}"
while [ $# -gt 0 ]; do
    case "$1" in
        --result-path) RESULT_PATH="$2"; shift ;;
        --output-dir) OUTPUT_DIR="$2"; shift ;;
    esac
    shift
done
mkdir -p "${OUTPUT_DIR}"
if [ -z "${FAKE_NO_RESULT:-}" ]; then echo '{"score": 0.7}' > "${RESULT_PATH}"; fi
exit "${FAKE_EVAL_EXIT:-0}"
"""


def find_bash():
    candidate = shutil.which("bash")
    if not candidate:
        return None
    try:
        probe = subprocess.run([candidate, "-c", "echo ok"], capture_output=True, text=True, timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return candidate if probe.stdout.strip() == "ok" else None


BASH = find_bash()
pytestmark = pytest.mark.skipif(BASH is None, reason="no working bash")


class Sandbox:
    def __init__(self, tmp_path):
        self.root = tmp_path
        p = tmp_path.as_posix()
        for sub in ("out", "src/eval/scripts", "src/task", "src/brain-comm", "config", "build", "bin",
                    f"benchmark/{BENCHMARK_ID}"):
            (tmp_path / sub).mkdir(parents=True)
        (tmp_path / "src/eval/scripts/evaluate.py").write_text("# stub\n")
        (tmp_path / "config/eval.yaml").write_text("runtime: brain\n")
        (tmp_path / f"benchmark/{BENCHMARK_ID}/manifest.yaml").write_text("id: x\n")
        self.write_executable(tmp_path / "bin/python3", FAKE_PYTHON)
        text = SCRIPT.read_text(encoding="utf-8")
        for fixed in ("/src/", "/config/", "/benchmark/"):
            text = text.replace(fixed, f"{p}{fixed}")
        text = text.replace("OUT=/out", f"OUT={p}/out").replace("BUILD=/opt/unidroid/build", f"BUILD={p}/build")
        self.script = tmp_path / "entrypoint.sh"
        self.write_executable(self.script, text)
        self.log = tmp_path / "calls.log"
        self.log.write_text("")

    @staticmethod
    def write_executable(path, text):
        path.write_text(text, encoding="utf-8", newline="\n")
        path.chmod(0o755)

    def run(self, **env):
        base = {**os.environ, "PATH": f"{self.root / 'bin'}{os.pathsep}{os.environ['PATH']}",
                "FAKE_LOG": self.log.as_posix(), "UNIDROID_BENCHMARK_ID": BENCHMARK_ID,
                "UNIDROID_EVAL_TIMEOUT": "60"}
        base.update(env)
        return subprocess.run([BASH, self.script.as_posix()], env=base, capture_output=True, text=True, timeout=120,
                              check=False)

    def status(self):
        path = self.root / "out" / "sandbox_status.json"
        return json.loads(path.read_text()) if path.exists() else None

    @property
    def result(self):
        path = self.root / "out" / "evaluation_result.json"
        return json.loads(path.read_text()) if path.exists() else None


@pytest.fixture
def box(tmp_path):
    return Sandbox(tmp_path)


def test_a_good_run_needs_no_gpu_and_writes_the_result(box):
    done = box.run()
    assert done.returncode == 0, done.stderr
    assert box.result == {"score": 0.7}
    assert box.status() == {"stage": "eval", "code": 0, "exit_code": 0}
    log = box.log.read_text()
    assert f"PYTHONPATH={box.root.as_posix()}/src/eval" in log
    assert f"BUNDLE={box.root.as_posix()}/benchmark/{BENCHMARK_ID}" in log


def test_both_pinned_packages_are_installed_offline_without_dependencies(box):
    box.run()
    installs = [line for line in box.log.read_text().splitlines() if line.startswith("pip")]
    assert len(installs) == 2
    for line in installs:
        assert all(flag in line for flag in ("--no-deps", "--no-index", "--no-build-isolation"))
    assert "brain-comm" in installs[0] and "task" in installs[1]


def test_an_install_failure_is_the_hosts_problem(box):
    done = box.run(FAKE_PIP_FAIL="1")
    assert done.returncode == 4 and box.status()["stage"] == "install" and box.result is None


def test_no_result_is_an_evaluation_that_produced_nothing(box):
    done = box.run(FAKE_NO_RESULT="1", FAKE_EVAL_EXIT="2")
    assert done.returncode == 1 and box.result is None
    assert box.status() == {"stage": "eval", "code": 0, "exit_code": 2}


def test_a_missing_eval_script_is_an_install_failure(box):
    (box.root / "src/eval/scripts/evaluate.py").unlink()
    done = box.run()
    assert done.returncode == 4 and box.status()["stage"] == "install" and box.log.read_text() == ""


def test_the_exit_code_is_never_one_the_validator_reads_as_docker_failing(box):
    codes = set()
    for env in ({}, {"FAKE_PIP_FAIL": "1"}, {"FAKE_NO_RESULT": "1", "FAKE_EVAL_EXIT": "127"},
                {"FAKE_NO_RESULT": "1", "FAKE_EVAL_EXIT": "125"}):
        for leftover in (box.root / "out").glob("*"):
            leftover.unlink() if leftover.is_file() else shutil.rmtree(leftover)
        codes.add(box.run(**env).returncode)
    assert codes.isdisjoint({125, 126, 127}), codes
