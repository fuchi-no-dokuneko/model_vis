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

Each canonical `structure_key` executes once through Torchview. Catalog aliases and later versions with the same constructor/config structure point to that execution record.

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

The verified 20-structure baseline is reproducible without retyping model names:

```bash
./venv/bin/python -m src.model_builder \
  --catalog model.txt \
  --scope-out model_scope.generated.yaml \
  --out model_code \
  --cache build_cache \
  --include-file profiles/smallest-20.txt \
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
