# unidroid-sandbox

The evaluation sandbox images. Each engine and version is its own directory. The image does not contain the evaluator that runs: the validator mounts that checkout and the task package, read-only, and the image's entrypoint installs the task package offline. brain-comm is different: it is part of the image, at the commit in `versions.lock`.

Validators pull a published digest. They do not build these Dockerfiles. The digest is not in the validator's config: each challenge carries it as its `sandbox_image`, next to the task and eval commits, so a new challenge or a new image version needs no validator change. A challenge pins no brain-comm of its own: the digest pins the client, and the challenge's brain image pins the server.

```
ghcr.io/unidroid-ai/sandbox-isaaclab@sha256:<digest of sandboxes/isaaclab/6.1-3.0>
ghcr.io/unidroid-ai/sandbox-mujoco@sha256:<digest of sandboxes/mujoco/4.0.0>
```

A tag is not a pin. The digest selects the engine and the version. Two versions of one engine are two digests of `sandbox-<engine>`. The validator only checks the digest against its allowlist pattern (`sandbox.image_pattern`), pulls it on demand and verifies it.

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

## brain-comm

Every image carries two labels:

| Label | Value |
|---|---|
| `ai.unidroid.brain-comm.commit` | the brain-comm commit installed in the image |
| `ai.unidroid.brain-comm.protocol` | `PROTOCOL_VERSION` at that commit |

`BRAIN_COMM_REF` in `versions.lock` (a tag or a full commit SHA, the same ref as `brain-images/brain-comm.lock`) selects brain-comm. The publish workflow resolves it to a commit, reads `PROTOCOL_VERSION` from that commit, and passes both as build arguments; the image labels record the commit. The Dockerfile fails when the installed package reports another protocol than the label. The brain images carry the same labels. The protocol of the sandbox and of the challenge's brain image must be equal, or the brain refuses `hello`. The backend checks this when a challenge is saved and the validator checks it again before a run.

`ai.unidroid.sandbox.contract` is `2`: the entrypoint no longer installs brain-comm at start, and the validator no longer mounts it. A change of `PROTOCOL_VERSION` means a new sandbox digest, new brain images and new challenges. A brain-comm change that keeps the protocol needs none of that.

`versions.lock` is the input of that version. `EVAL_REPO_COMMIT`, when set, is the commit whose dependencies are installed and then uninstalled. The publish workflow never builds from a moving branch: an empty value is resolved to the default branch's head SHA before the build, so the `ai.unidroid.eval-deps.commit` label always records a real commit (pin it here to make the build reproducible). The challenge's `eval_commit` still selects the code that runs; when the eval repository changes its dependencies, publish a new version of the image and point the challenge at its new digest. Isaac Lab `6.1-3.0` uses the Isaac Sim 6.1.0 binary from `nvcr.io`. It sets `NEEDS_NGC=1`, so the build needs the `NGC_API_KEY` secret. The public `isaacsim` pip wheel is not the simulator in this image.

## Publish

`.github/workflows/publish.yml` runs on a version tag (`v1.2.3`) or when started by hand. The hand start takes one sandbox, such as `mujoco/4.0.0`; an empty value builds every directory.

Isaac Lab pulls `nvcr.io/nvidia/isaac-sim:6.1.0`, so the repository secret `NGC_API_KEY` has to be set before publish. It also needs a runner with enough disk. Set the repository variable `SANDBOX_RUNNER` when the default hosted runner is too small. MuJoCo does not install Isaac Sim.

The log ends with the line to put in the challenge as `sandbox_image`:

```
ghcr.io/unidroid-ai/sandbox-isaaclab@sha256:<64 hex chars>
```

## Contract with the validator

Every entrypoint honors the same contract. The validator starts the container with no arguments and these mounts:

| Mount | What it is |
|---|---|
| `/src/eval` | the challenge's pinned eval package, read-only, run from here |
| `/src/task` | the challenge's pinned task package, read-only |
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
