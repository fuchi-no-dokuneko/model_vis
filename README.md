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

The build also writes a schema-validated `semantics/<version>.json` for every successful technical graph. These assets contain topology-ordered stages, exact class/interface tags, technical fallback explanations, tensor journeys, trace-only parameter and operation distributions, and coverage values. Config-derived parameter counts instantiate the recorded entrypoint on the meta device, deduplicate tied parameters, and identify task-head variants. These counts remain separate from approximate memory-preflight estimates and initialized trace counts. Missing or unsupported official mappings remain unavailable, including reused aliases. Every journey step describes its own observed input and output ports.

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

New viewer sessions open in Standard detail, Both labels, and Architecture. The Professional preset restores Standard/Both. Trace exposes the full Modules, Blocks, Operations, runtime, source, and config interface. Detail, label, selection, and stage preferences persist locally; explicit shared route preferences take precedence. Overview groups expand into readable technical nodes.

The finder supports interface, module, tensor ID, dtype and shape filters, a results table, next/previous navigation and an explicit empty state. Tensor filters describe the same observed port. Review/export saves annotated views and downloads selected subgraph SVG plus JSON/CSV facts with provenance. Compare provides missing-data-aware differences and expandable configuration/journey details. Panel widths persist locally; smaller windows expose controls through Tools. See [audit controls and checks](docs/audit-v2.md).

Serve the local build with `venv/bin/python scripts/serve_https.py --directory build --port 8081`. It binds IPv4 `0.0.0.0` using a self-signed certificate under `.local-tool/certs/`; manually accept the certificate in your browser. The audit-v2 task excludes deployment.

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

## 繁體中文

本專案將離線 PyTorch 架構追蹤轉成靜態檢視器，保留 101 個模型；權重為本機初始化，不下載預訓練權重。上述命令可建置、驗證與執行測試。官方設定映射不足或沿用其他模型追蹤時會明確標示，不能視為檢查點驗證。

預設使用 Standard／Both；專業預設、搜尋結果表、逐埠張量旅程、差異比較、可調面板、儲存註記及 SVG／JSON／CSV 匯出均可在介面操作。共享網址的明確模式優先。設定推導參數量與初始化追蹤、記憶體預估分開顯示。

本機服務使用專案內自簽 HTTPS 憑證，監聽 IPv4 `0.0.0.0`；瀏覽器需手動接受憑證。此次審核不需要部署。詳細操作與驗收命令見[審核指南](docs/audit-v2.md)。來源授權仍依第三方聲明與既有發行檢查處理。

## 简体中文

本项目将离线 PyTorch 架构跟踪转为静态查看器，保留 101 个模型；权重为本地初始化，不下载预训练权重。上述命令可构建、验证并运行测试。官方配置映射不足或复用其他模型跟踪时会明确标示，不能视为检查点验证。

默认使用 Standard／Both；专业预设、搜索结果表、逐端口张量旅程、差异比较、可调面板、保存注释及 SVG／JSON／CSV 导出均可在界面操作。共享网址的明确模式优先。配置推导参数量与初始化跟踪、内存预估分别显示。

本地服务使用项目内自签 HTTPS 证书，监听 IPv4 `0.0.0.0`；浏览器需手动接受证书。本次审核无需部署。详细操作与验收命令见[审核指南](docs/audit-v2.md)。源码授权仍按第三方声明与现有发布检查处理。
