# Generating the 101-model scope

The September 2026 update adds exactly 50 families/versions to the existing 51.
`profiles/smallest-21.txt`, `profiles/alphabetical-30-new.txt`, and
`profiles/expansion-50-new.txt` define the complete selection. `model.txt` remains
the full catalog of 563 families and 567 normalized versions. This is a partial
catalog release, not a claim that the entire catalog has been traced.

The new selection uses distinct structures absent from the baseline. Candidates
are ordered by case-insensitive display name among single-version text and
vision families plus Chinese-CLIP, CLIP, CLIPSeg, ViLT, VisualBERT, Wav2Vec2, and
Whisper. Candidates count only after an isolated offline trace and asset
validation succeed. The final include file, rather than retrying candidate
discovery, makes the release selection reproducible.

## Build and validate

Use the existing locked environment. Config prefetch is separate and retains
the original mapping and network policy. This expansion requires no downloads.
The 50 additional versions use compact local configs and carry model-specific
partial-provenance warnings; their dimensions are not official checkpoint sizes.

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
  --model-code model_code --catalog model.txt --allow-partial
./venv/bin/python -m src.model_builder.drift
npm run build-ui -- --model-code model_code --out build
```

The builder replaces its output directory and rematerializes completed traces
from the cache. Use a separate output directory for candidate experiments; do
not interrupt a live build merely because its observer timed out. Cache data is
transient. Commit the complete generated `model_code/` tree, the fixed include
file, and the generated package notices after rebuilding the combined scope.

`--allow-partial` allows this selected catalog scope and explicit provenance
warnings. It does not waive trace, graph, source, semantic integrity, or file
limit validation. Failed candidate attempts are not successful models.

## Acceptance evidence

```bash
npm test
./venv/bin/python -m pytest -q test/unit test/uat
./venv/bin/python -m pytest -q test/e2e
npm run test:coverage:ui
npm run test:coverage:python
npm run test:coverage:check
npm run test:uat:dry
npm run test:uat
npm run test:uat:check
./venv/bin/python -m uat.run --suite all --dry-run
```

The JS catalog test checks exact set equality, preservation of the original 51,
and 50 distinct added structures. The browser smoke test opens every one of the
101 Architecture views. Dedicated browser tests cover persistent URI errors,
valid-link recovery, Favorites storage/keyboard/filter behavior, and search
after scrolling. Shared geometry and contrast tests remain in force.

## Existing target publication

The target is `https://model-vis.pages.dev/`. Keep `.github/workflows/quality.yml`,
network configuration, and deployment methods unchanged. The existing workflow
verifies every branch and deploys successful pushes on `main` or
`tickets/model-vis-260823` through its existing Cloudflare Pages action. A feature
branch passing verification alone does not update the target.

After publishing through that workflow, verify the successful deployment job,
the target's `deployment.json` commit, and `model_code/manifest.v2.json`. Fetch
and validate the target assets and open the new models in the browser. Confirm
all original 51 IDs remain and all 50 new IDs are served. A local 101-model
manifest, a push, or a queued CI run is insufficient evidence of completion.

If network or deployment access fails, record the exact failed step and retain
the ready artifacts. Do not work around it by changing networking or CI/CD.
