# Model Structure Viewer

This repository compiles PyTorch architecture metadata into a static Cloudflare Pages viewer. Model constructors use compact random initialization on CPU. They never call `from_pretrained`, download weights, or serialize model tensors.

## Build

Resolve the complete catalog without inference:

```bash
./venv/bin/python -m src.model_builder --catalog model.txt --scope-out model_scope.generated.yaml --plan-only
```

Run the resumable Stage 1 build:

```bash
./venv/bin/python -m src.model_builder \
  --catalog model.txt \
  --scope-out model_scope.generated.yaml \
  --out model_code \
  --cache build_cache \
  --device cpu \
  --require-forward \
  --allow-staged-large-models \
  --resume \
  --fetch-policy source-config-only \
  --forbid-weight-downloads
```

Each canonical `structure_key` executes one deterministic CPU forward through the canonical dispatch/lineage tracer. Catalog aliases and later versions with the same constructor/config structure point to that execution record.

## Redistributed source code

The static viewer includes unmodified copies of installed Python source files referenced by captured model traces so the Source panel works offline. Every generated source asset records its package, installed version, content hash, license metadata, and a pinned official-repository URL when one is available. Copyright remains with the respective package authors and contributors. Required package notices are maintained in `license/THIRD_PARTY_NOTICES.md` and `license/dependency_licenses.json`; source text must not be added to a release unless the license gate records redistribution as permitted.

Build the static UI without downloading npm dependencies:

```bash
npm run build-ui -- --model-code model_code --out build
```

Validate and test:

```bash
./venv/bin/python -m src.model_builder.validate --model-code model_code --catalog model.txt
./venv/bin/python -m pytest
npm test
npm run test:e2e
npm run test:visual
```

Partial development builds can use `--include BERT` or `--limit 5`. They are intentionally rejected by full-catalog validation.

The amended 21-model development scope (the verified 20-structure baseline plus BERT) is reproducible without retyping model names:

```bash
./venv/bin/python -m src.model_builder \
  --catalog model.txt \
  --scope-out model_scope.generated.yaml \
  --out model_code \
  --cache build_cache \
  --include-file profiles/smallest-21.txt \
  --resume \
  --require-forward \
  --forbid-weight-downloads

./venv/bin/python -m src.model_builder.validate \
  --model-code model_code \
  --catalog model.txt \
  --allow-partial
```

`--resume` reuses the canonical structure record and rematerializes trace assets from `build_cache/assets/` when the output directory is new. Aliases and later builds with the same `structure_key` never execute another forward pass.

When the build host has no package-network access, prepare a wheelhouse on a networked host:

```bash
python -m pip download -d wheelhouse -r requirements-admin.txt
./venv/bin/python -m pip install --no-index --find-links=/path/to/wheelhouse -r requirements-admin.txt
```

`torchaudio` must be the CPU wheel matching the installed `torch` version. The viewer and non-audio model builds work without it; audio-family builds require it.
