# Copyright (c) 2026, Unidroid
# All rights reserved.
#
# SPDX-License-Identifier: BSD-3-Clause

"""The sandbox entrypoint's control flow, run for real with stubs for nvidia-smi, Isaac Lab and the evaluation.

It cannot run Isaac here; what it must get right is what it reports: ``sandbox_status.json`` and an exit code the
validator maps to Deferred (this host cannot run the sandbox) or failed (the evaluation produced nothing).
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "sandboxes" / "isaaclab" / "6.1-3.0" / "entrypoint.sh"
BENCHMARK_ID = "franka-tabletop-v13"

FAKE_ISAACLAB = """#!/bin/bash
# stands in for isaaclab.sh: `-p -m pip install ...`, `-p -c "import brain_comm"`, `-p -c <bootstrap> evaluate.py ...`
shift  # -p
if [ "$1" = "-m" ]; then
    [ -n "${FAKE_PIP_FAIL:-}" ] && exit 1
    echo "pip $*" >> "${FAKE_LOG}"
    exit 0
fi
if [ "$1" = "-c" ] && [[ "$2" == import\\ brain_comm* ]]; then
    [ -n "${FAKE_IMPORT_FAIL:-}" ] && exit 1
    exit 0
fi
shift 2  # -c <bootstrap>
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
if [ -n "${FAKE_RESULT_IN_OUTPUT_DIR:-}" ]; then echo '{"score": 0.4}' > "${OUTPUT_DIR}/evaluation_result.json"; fi
if [ -z "${FAKE_NO_RESULT:-}" ] && [ -z "${FAKE_RESULT_IN_OUTPUT_DIR:-}" ]; then echo '{"score": 0.7}' > "${RESULT_PATH}"; fi
exit "${FAKE_EVAL_EXIT:-0}"
"""

FAKE_NVIDIA_SMI = """#!/bin/bash
[ -n "${FAKE_GPU_FAIL:-}" ] && exit 9
echo "NVIDIA RTX, 24576 MiB"
exit 0
"""


def find_bash():
    candidates = [shutil.which("bash"), r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files\Git\usr\bin\bash.exe"]
    for candidate in candidates:
        if not candidate or not Path(candidate).exists():
            continue
        try:
            probe = subprocess.run([candidate, "-c", "echo ok"], capture_output=True, text=True, timeout=20, check=False)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if probe.stdout.strip() == "ok":  # not the WSL stub, which prints a notice instead
            return candidate
    return None


BASH = find_bash()
pytestmark = pytest.mark.skipif(BASH is None, reason="no working bash")


class Sandbox:
    """The container's fixed paths, redirected into a temp directory."""

    def __init__(self, tmp_path):
        self.root = tmp_path
        p = tmp_path.as_posix()
        for sub in ("out", "src/eval/isaac_eval/scripts", "src/task", "src/brain-comm", "config", "build", "bin",
                    "isaac-lab", f"benchmark/{BENCHMARK_ID}"):
            (tmp_path / sub).mkdir(parents=True)
        (tmp_path / "src/eval/isaac_eval/scripts/evaluate.py").write_text("# stub\n")
        (tmp_path / "config/eval.yaml").write_text("runtime: brain\n")
        (tmp_path / f"benchmark/{BENCHMARK_ID}/manifest.yaml").write_text("id: x\n")
        self.write_executable(tmp_path / "isaac-lab/isaaclab.sh", FAKE_ISAACLAB)
        self.write_executable(tmp_path / "bin/nvidia-smi", FAKE_NVIDIA_SMI)
        text = SCRIPT.read_text(encoding="utf-8")
        for fixed in ("/src/", "/config/", "/benchmark/"):
            text = text.replace(fixed, f"{p}{fixed}")
        text = text.replace("OUT=/out", f"OUT={p}/out").replace("BUILD=/opt/unidroid/build", f"BUILD={p}/build")
        text = text.replace("-d /src/", f"-d {p}/src/")
        assert "/opt/unidroid" not in text.replace("/opt/unidroid/build", "")
        self.script = tmp_path / "entrypoint.sh"
        self.write_executable(self.script, text)
        self.log = tmp_path / "calls.log"
        self.log.write_text("")

    @staticmethod
    def write_executable(path, text):
        path.write_text(text, encoding="utf-8", newline="\n")
        path.chmod(0o755)

    def run(self, **env):
        base = {**os.environ, "ISAACLAB_PATH": (self.root / "isaac-lab").as_posix(),
                "PATH": f"{self.root / 'bin'}{os.pathsep}{os.environ['PATH']}", "FAKE_LOG": self.log.as_posix(),
                "UNIDROID_BENCHMARK_ID": BENCHMARK_ID, "UNIDROID_EVAL_TIMEOUT": "60"}
        base.update(env)
        done = subprocess.run([BASH, self.script.as_posix()], env=base, capture_output=True, text=True, timeout=120,
                              check=False)
        return done

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


def test_a_good_run_writes_the_result_and_exits_zero(box):
    done = box.run()
    assert done.returncode == 0, done.stderr
    assert box.result == {"score": 0.7}
    assert box.status() == {"stage": "eval", "code": 0, "exit_code": 0}


def test_the_evaluation_is_run_from_the_pinned_mount_with_the_benchmark_bundle(box):
    box.run()
    log = box.log.read_text()
    assert f"PYTHONPATH={box.root.as_posix()}/src/eval" in log
    assert f"BUNDLE={box.root.as_posix()}/benchmark/{BENCHMARK_ID}" in log
    assert "--config" in log and "/config/eval.yaml" in log and "--result-path" in log and "--output-dir" in log
    assert "--viz" not in log and "--headless" not in log, "brain mode's orchestrator takes neither"


def test_both_pinned_packages_are_installed_offline_without_dependencies(box):
    box.run()
    installs = [line for line in box.log.read_text().splitlines() if line.startswith("pip")]
    assert len(installs) == 2
    for line in installs:
        assert all(flag in line for flag in ("--no-deps", "--no-index", "--no-build-isolation"))
    assert "brain-comm" in installs[0] and "task" in installs[1]
    assert not (box.root / "src/task/build").exists(), "the read-only mount is never built in: copies are"


def test_a_valid_result_counts_even_if_isaac_exits_badly(box):
    done = box.run(FAKE_EVAL_EXIT="124")
    assert done.returncode == 0 and box.result == {"score": 0.7}
    assert box.status()["exit_code"] == 124


def test_a_result_left_in_the_output_dir_is_collected(box):
    assert box.run(FAKE_RESULT_IN_OUTPUT_DIR="1").returncode == 0
    assert box.result == {"score": 0.4}


def test_no_result_is_reported_as_an_evaluation_that_produced_nothing(box):
    done = box.run(FAKE_NO_RESULT="1", FAKE_EVAL_EXIT="2")
    assert done.returncode == 1 and box.result is None
    assert box.status() == {"stage": "eval", "code": 0, "exit_code": 2}


def test_a_stale_result_is_removed_before_the_run(box):
    (box.root / "out" / "evaluation_result.json").write_text('{"score": 1.0}')
    done = box.run(FAKE_NO_RESULT="1")
    assert done.returncode == 1 and box.result is None, "an old result must never be mistaken for this run's"


def test_no_gpu_is_reported_as_the_hosts_problem(box):
    done = box.run(FAKE_GPU_FAIL="1")
    assert done.returncode == 3 and box.status()["stage"] == "gpu" and box.result is None
    assert "eval" not in box.log.read_text()


def test_an_install_failure_is_reported_as_the_hosts_problem(box):
    done = box.run(FAKE_PIP_FAIL="1")
    assert done.returncode == 4 and box.status()["stage"] == "install" and box.result is None
    assert "eval" not in box.log.read_text()


def test_a_package_that_cannot_be_imported_is_an_install_failure(box):
    done = box.run(FAKE_IMPORT_FAIL="1")
    assert done.returncode == 4 and box.status()["stage"] == "install"


@pytest.mark.parametrize("remove", ["src/eval/isaac_eval/scripts/evaluate.py", "config/eval.yaml",
                                    f"benchmark/{BENCHMARK_ID}/manifest.yaml"])
def test_a_missing_mount_is_an_install_failure(box, remove):
    (box.root / remove).unlink()
    done = box.run()
    assert done.returncode == 4 and box.status()["stage"] == "install" and box.log.read_text() == ""


def test_a_missing_package_mount_is_an_install_failure(box):
    shutil.rmtree(box.root / "src/task")
    assert box.run().returncode == 4


@pytest.mark.parametrize("env", [{"UNIDROID_BENCHMARK_ID": ""}, {"UNIDROID_BENCHMARK_ID": "../etc"},
                                 {"UNIDROID_BENCHMARK_ID": "a b"}, {"UNIDROID_EVAL_TIMEOUT": "soon"}])
def test_invalid_settings_are_an_install_failure_not_a_crash(box, env):
    done = box.run(**env)
    assert done.returncode == 4 and box.status()["stage"] == "install"


def test_the_exit_code_is_never_one_the_validator_reads_as_docker_failing(box):
    codes = set()
    for env in ({}, {"FAKE_GPU_FAIL": "1"}, {"FAKE_PIP_FAIL": "1"}, {"FAKE_NO_RESULT": "1", "FAKE_EVAL_EXIT": "127"},
                {"FAKE_NO_RESULT": "1", "FAKE_EVAL_EXIT": "126"}, {"FAKE_EVAL_EXIT": "125"}, {"UNIDROID_BENCHMARK_ID": "!"}):
        for leftover in (box.root / "out").glob("*"):
            leftover.unlink() if leftover.is_file() else shutil.rmtree(leftover)
        codes.add(box.run(**env).returncode)
    assert codes.isdisjoint({125, 126, 127}), codes


def test_the_status_file_is_valid_json_the_validator_can_read(box):
    box.run(FAKE_NO_RESULT="1", FAKE_EVAL_EXIT="3")
    data = json.loads((box.root / "out" / "sandbox_status.json").read_text())
    assert isinstance(data["exit_code"], int) and data["stage"] in {"gpu", "install", "eval"}
