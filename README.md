# unidroid-sandbox

The evaluation sandbox images. Each engine and version is its own directory. The image does not contain the evaluator that runs: the validator mounts that checkout, the task package, and brain-comm, read-only, and the image's entrypoint installs the last two offline.

Validators pull a published digest. They do not build these Dockerfiles.

```yaml
sandbox:
  image: ghcr.io/unidroid-ai/sandbox-isaaclab@sha256:<digest of sandboxes/isaaclab/6.1-3.0>
```

```yaml
sandbox:
  image: ghcr.io/unidroid-ai/sandbox-mujoco@sha256:<digest of sandboxes/mujoco/4.0.0>
```

A tag is not a pin. The digest selects the engine and the version. Two versions of one engine are two digests of `sandbox-<engine>`.

## Layout

```
sandboxes/<engine>/<version>/
  Dockerfile
  entrypoint.sh
  versions.lock
```

| Directory | Image |
|---|---|
| `sandboxes/isaaclab/6.1-3.0` | `ghcr.io/unidroid-ai/sandbox-isaaclab` |
| `sandboxes/mujoco/4.0.0` | `ghcr.io/unidroid-ai/sandbox-mujoco` |

A new version is a new directory. A new engine is a new directory under `sandboxes/` with the same three files. The publish workflow finds them; the image name is `sandbox-` plus the engine directory name.

`versions.lock` is the input of that version. `EVAL_REPO_COMMIT`, when set, is the commit whose dependencies are installed and then uninstalled. An empty value clones that repository's default branch. The validator's `pins.repos` still selects the code that runs. Isaac Lab `6.1-3.0` installs Isaac Sim with pip from `pypi.nvidia.com`, so the build does not use an NGC API key. A sandbox that still pulls from `nvcr.io` sets `NEEDS_NGC=1` and then needs the `NGC_API_KEY` secret.

## Publish

`.github/workflows/publish.yml` runs on a version tag (`v1.2.3`) or when started by hand. The hand start takes one sandbox, such as `mujoco/4.0.0`; an empty value builds every directory.

Isaac Lab installs the public Isaac Sim pip package, so it does not need `NGC_API_KEY`. It does need a runner with enough disk. Set the repository variable `SANDBOX_RUNNER` when the default hosted runner is too small. MuJoCo does not install Isaac Sim.

The log ends with the line to put in the validator config:

```
ghcr.io/unidroid-ai/sandbox-isaaclab@sha256:<64 hex chars>
```

## Contract with the validator

Every entrypoint honors the same contract. The validator starts the container with no arguments and these mounts:

| Mount | What it is |
|---|---|
| `/src/eval` | pinned eval package, read-only, run from here |
| `/src/task` | pinned task package, read-only |
| `/src/brain-comm` | pinned brain-comm, read-only |
| `/benchmark/<id>` | the private benchmark, read-only |
| `/config/eval.yaml` | the challenge eval config, read-only |
| `/out` | `evaluation_result.json` and `sandbox_status.json` |

Environment from the validator: `UNIDROID_BENCHMARK_ID`, `UNIDROID_EVAL_TIMEOUT`. Exit status is `0` when a result file was written, `3` when a sandbox that needs a GPU cannot see one, `4` when install or a mount failed, and `1` when the evaluation produced nothing. It is never `125`, `126`, or `127`.

Isaac Lab runs `/src/eval/isaac_eval/scripts/evaluate.py` through Isaac Lab's Python. MuJoCo runs `/src/eval/scripts/evaluate.py` through its own Python and does not require a GPU.

## Tests

```bash
pip install -e ".[dev]"
pytest
```

The tests run the entrypoints with stubs. They do not build the images or start a simulator.
