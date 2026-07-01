# Model Structure Viewer

This repository compiles PyTorch architecture metadata into a static Cloudflare Pages viewer. Models use random CPU initialization and never call `from_pretrained`, download weights, execute remote code, or serialize model tensors.

## Build

Resolve the complete catalog without inference:

```bash
./venv/bin/python -m src.model_builder --catalog model.txt --scope-out model_scope.generated.yaml --plan-only
```

Prefetch only the 21 pinned official Hugging Face `config.json` files on a network-enabled host:

```bash
./venv/bin/python -m src.model_builder.hf_config \
  --mapping profiles/hf-config-mapping.v1.json \
  --out official_configs
```

The pinned mapping is human-reviewable. Jais2 and DINOv3 currently require Hub authorization; without credentials their exact model records are published as partial with a visible warning.
For an account that has accepted those repository terms, `HF_TOKEN` may be supplied to the prefetch process; the token is sent only as an authorization header and is never written to generated metadata.

Run the resumable offline trace build:

```bash
./venv/bin/python -m src.model_builder \
  --catalog model.txt \
  --scope-out model_scope.generated.yaml \
  --out model_code \
  --cache build_cache \
  --official-config-mapping profiles/hf-config-mapping.v1.json \
  --official-config-dir official_configs \
  --resume
```

An automatic preflight compares estimated official-model peak memory with currently available host memory. Models that fit execute a complete official-configuration forward. Larger models execute one compact, shape-valid representative of every distinct layer structure, including later MoE or hybrid variants. Each model trace runs in a separate process so allocator state cannot accumulate across the release. Every version stores the raw pinned official config, the effective trace config, and a field-level diff.

## Redistributed source code

The static viewer includes unmodified copies of installed Python source files referenced by captured model traces so the Source panel works offline. Every generated source asset records its package, installed version, content hash, license metadata, and a pinned official-repository URL when one is available. Copyright remains with the respective package authors and contributors. Required package notices are maintained in `license/THIRD_PARTY_NOTICES.md` and `license/dependency_licenses.json`; source text must not be added to a release unless the license gate records redistribution as permitted.

Build the static UI without downloading npm dependencies:

```bash
npm run build-ui -- --model-code model_code --out build
```

## Viewer controls

Graph nodes can be moved by dragging their header and resized from the lower-right handle in every graph mode. Layout changes are stored locally per model, mode, and module scope; Reset restores generated positions and the default `248 x 168` node size. Empty-canvas dragging pans without selecting page text.

With a graph node selected, `Alt+Shift+M` copies its module name, `Alt+Shift+P` copies its qualified module path, and `Alt+Shift+S` copies only its referenced source range. The top-bar theme control switches between light and dark themes and preserves the choice locally.

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
  --official-config-mapping profiles/hf-config-mapping.v1.json \
  --official-config-dir official_configs \
  --resume

./venv/bin/python -m src.model_builder.validate \
  --model-code model_code \
  --catalog model.txt \
  --allow-partial
```

`--resume` reuses the canonical structure record and rematerializes trace assets from `build_cache/assets/` when the output directory is new. Aliases and later builds with the same `structure_key` never execute another forward pass. The trace/static stages run under a network guard and consume only local pinned configs.

When the build host has no package-network access, prepare a wheelhouse on a networked host:

```bash
python -m pip download -d wheelhouse -r requirements-admin.txt
./venv/bin/python -m pip install --no-index --find-links=/path/to/wheelhouse -r requirements-admin.txt
```

`torchaudio` must be the CPU wheel matching the installed `torch` version. The viewer and non-audio model builds work without it; audio-family builds require it.
