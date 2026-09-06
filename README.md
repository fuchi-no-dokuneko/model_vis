# Model Structure Viewer

This repository compiles PyTorch architecture metadata into a static Cloudflare Pages viewer. Models use random CPU initialization and never call `from_pretrained`, download weights, execute remote code, or serialize model tensors.

## Build

Resolve the complete catalog without inference:

```bash
./venv/bin/python -m src.model_builder --catalog model.txt --scope-out model_scope.generated.yaml --plan-only
```

Prefetch the original 21 pinned official Hugging Face `config.json` files on a network-enabled host:

```bash
./venv/bin/python -m src.model_builder.hf_config \
  --mapping profiles/hf-config-mapping.v1.json \
  --out official_configs
```

The pinned mapping is human-reviewable and covers the original 21 versions. Jais2 and DINOv3 require Hub authorization; without credentials their exact model records are published as partial with a visible warning. The subsequent 30-model and 50-model expansions use deterministic compact local configurations and are also published with explicit partial-status warnings. A successful trace does not imply official configuration coverage.
For an account that has accepted those repository terms, `HF_TOKEN` may be supplied to the prefetch process; the token is sent only as an authorization header and is never written to generated metadata.

Run the resumable offline trace build:

```bash
./venv/bin/python -m src.model_builder \
  --catalog model.txt \
  --scope-out model_scope.generated.yaml \
  --out model_code \
  --cache build_cache \
  --include-file profiles/smallest-21.txt \
  --include-file profiles/alphabetical-30-new.txt \
  --include-file profiles/expansion-50-new.txt \
  --official-config-mapping profiles/hf-config-mapping.v1.json \
  --official-config-dir official_configs \
  --resume
```

An automatic preflight compares estimated official-model peak memory with currently available host memory. Models that fit execute a complete official-configuration forward. Larger models execute one compact, shape-valid representative of every distinct layer structure, including later MoE or hybrid variants. Each model trace runs in a separate process so allocator state cannot accumulate across the release. Every version stores the raw pinned official config, the effective trace config, and a field-level diff.

## Deterministic semantic assets

The build also writes a schema-validated `semantics/<version>.json` for every successful technical graph. These assets contain topology-ordered stages, exact class/interface tags, technical fallback explanations, tensor journeys, trace-only parameter and operation distributions, and coverage values. Official parameter estimates remain separate and are never distributed across trace stages. Every semantic asset records the semantic generator version and a shared generation timestamp.

The fixed tag vocabulary and exact matching registry live in `profiles/interface-tags.v1.json`; reusable architecture-family stage packs live in `profiles/semantic-stage-rules.v1.json`. Rules match exact classes, base classes/interfaces, or verified signatures. Unknown classes remain publishable as `other` with a technical fallback—do not add fuzzy class-name rules or browser-side per-model mappings. The static tree publishes canonical copies at `contracts/interface-tags.v1.json` and `contracts/semantic-model.schema.json`; `manifest.v2.json` links both contracts, the semantic index, and `indexes/semantic-report.v1.json`.

To improve coverage for a new architecture:

1. Add a reusable exact identity to the appropriate registry tag or stage rule.
2. Run `./venv/bin/python -m src.model_builder.semantics --model-code model_code` to rematerialize existing assets without tracing models again.
3. Run partial validation and the semantic unit tests. The machine-readable coverage and outcome dashboard is `model_code/indexes/semantic-report.v1.json`.

Every semantic module, operation, tensor, stage, journey shape, tag, and distribution total is cross-checked against its canonical graph during validation. The report distinguishes passed, technical-fallback, partial, and failed generation. It also reports selected/generated proportions against the complete catalog instead of presenting models outside a development scope as failures. The checked-in scope covers 101 of 563 catalog families and 101 of 567 normalized versions; the browser smoke batch opens all 101 in case-insensitive alphabetical order.

## Redistributed source code

The static viewer includes unmodified copies of installed Python source files referenced by captured model traces so the Source panel works offline. Every generated source asset records its package, installed version, content hash, license metadata, and a pinned official-repository URL when one is available. Copyright remains with the respective package authors and contributors. Required package notices are maintained in `license/THIRD_PARTY_NOTICES.md` and `license/dependency_licenses.json`; source text must not be added to a release unless the license gate records redistribution as permitted.

Build the static UI without downloading npm dependencies:

```bash
npm run build-ui -- --model-code model_code --out build
```

## Viewer controls

Use the star beside a model to save it to Favorites. The Favorites filter combines with search and category filters; stars persist in this browser across reloads. Comparison checkboxes remain independent. If browser storage is unavailable, favorites work for the current session and a message explains the limitation. Filtering resets the catalog scroll position so matching models remain visible.

Invalid model locations remain visible in the graph status while zooming, fitting, or resizing. The address field identifies the error to assistive technology. Opening a valid model location clears the diagnostic.

On phones, the catalog and inspector drawers open above the backdrop and close one another so their controls remain reachable.

Graph nodes can be moved by dragging their header and resized from the lower-right handle in every graph mode. Layout changes are stored locally per model, mode, and module scope; Reset restores generated positions and the default `248 x 168` technical-node or `248 x 196` semantic-stage size. Empty-canvas dragging pans without selecting page text.

New viewer sessions open in Beginner detail, Semantic labels, and Architecture. Standard combines semantic and source labels; Trace exposes the full Modules, Blocks, Operations, runtime, source, and config interface. Detail, label, selection, and stage preferences persist locally and explicit choices are encoded in shareable routes.

With a graph node selected, `Alt+Shift+M` copies its module name, `Alt+Shift+P` copies its qualified module path, and `Alt+Shift+S` copies only its referenced source range. The top-bar theme control switches between light and dark themes and preserves the choice locally.

Validate and test:

```bash
./venv/bin/python -m src.model_builder.validate --model-code model_code --catalog model.txt --allow-partial
./venv/bin/python -m pytest
npm test
npm run test:e2e
npm run test:visual
```

## Quality and release

The enforced coverage scope and reviewed integration-only exclusions are listed
in `docs/coverage-exclusions.md`. Regenerate and enforce the independent 95%
line and branch gates with:

```bash
npm run test:coverage:ui
npm run test:coverage:python
npm run test:coverage:check
```

Run the daily feature binding check and real Chromium acceptance flow with:

```bash
npm run test:uat:dry
npm run test:uat
npm run test:uat:check
venv/bin/python -m uat.run --suite all --dry-run
venv/bin/python -m uat.run --suite demo-en
venv/bin/python -m uat.run --suite demo-yue
```

The real run writes a boolean checklist, screenshots, browser LCOV, and Sonar
generic test execution XML under `artifacts/uat/`. `.github/workflows/quality.yml`
runs locked installs, release audits, unit/coverage/drift/browser/UAT checks, and
the SonarQube Cloud quality gate on pushes, pull requests, and daily schedule.
Cloudflare Pages deployment runs only after that job succeeds on `main` or the existing `tickets/model-vis-260823` branch. Other branches run verification without deploying.
The complete feature matrix and TTS/recording wrapper contract are documented in
`uat/README.md`; recording suites are product walkthroughs and are not quality-gate evidence.

Partial development builds can use `--include BERT` or `--limit 5`. They are intentionally rejected by full-catalog validation.

The 101-model development scope preserves the original 21-model baseline and the first 30-model expansion, and adds 50 distinct structures validated through isolated offline traces. The fixed include files define the published selection; failed candidates are not included. See [the current generation guide](docs/catalog-expansion.md) and [the reusable maintenance prompt](docs/maintenance-prompt.md).

```bash
./venv/bin/python -m src.model_builder \
  --catalog model.txt \
  --scope-out model_scope.generated.yaml \
  --out model_code \
  --cache build_cache \
  --include-file profiles/smallest-21.txt \
  --include-file profiles/alphabetical-30-new.txt \
  --include-file profiles/expansion-50-new.txt \
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
