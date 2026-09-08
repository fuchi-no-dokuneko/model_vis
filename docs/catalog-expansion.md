# Generating the 101-model scope

The September 2026 update adds exactly 50 families/versions to the existing 51.
`profiles/smallest-21.txt`, `profiles/alphabetical-30-new.txt`, and
`profiles/expansion-50-new.txt` define the complete selection. `model.txt` remains
the full catalog of 563 families and 567 normalized versions. This is a partial
catalog release, not a claim that the entire catalog has been traced.

The audit-v2 maintenance batch on 2026-09-08 retains these 101 models on
`feat/viewer-model-expansion-101`. The user explicitly excludes deployment.
Local validation and browser evidence describe local artifacts. They do not
claim a new remote release or deployment. Existing CI/CD files remain unchanged.

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
./venv/bin/python -m pytest -q test/audit
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

The separate audit suite verifies 52 viewports, breakpoint neighbors, 12 I/O
models at three sizes, comparison routes and keyboard focus, provenance,
exports, saved views, filters, and recovery from real HTTPS failures and delays.
Config-derived counts and every journey port are checked against actual model
classes and canonical graphs. See [the audit guide](audit-v2.md).

## 繁體中文

固定三份 include 清單保留原有 51 個模型並增加 50 個不同結構，共 101 個；完整目錄為 563 個家族與 567 個版本。這是部分目錄範圍，未宣稱全部已追蹤。新增模型使用精簡本機設定，缺少官方映射時明確標示。

上述建置命令可從快取恢復既有追蹤；完整驗證仍檢查圖形、來源、語意與檔案限制。`--allow-partial` 只允許選定範圍及明確的來源限制。單元、漂移、涵蓋率、101 模型載入與獨立審核套件共同提供本機驗收證據。

2026-09-08 審核沿用目前分支，不部署，亦不修改 CI/CD 或系統網絡。瀏覽器使用專案內自簽 HTTPS。舊部署狀態不屬此次完成條件；本機結果不代表遠端發行。

## 简体中文

固定三份 include 清单保留原有 51 个模型并增加 50 个不同结构，共 101 个；完整目录为 563 个家族与 567 个版本。这是部分目录范围，未声称全部已跟踪。新增模型使用精简本地配置，缺少官方映射时明确标示。

上述构建命令可从缓存恢复现有跟踪；完整验证仍检查图形、源码、语义与文件限制。`--allow-partial` 只允许选定范围及明确的来源限制。单元、漂移、覆盖率、101 模型加载与独立审核套件共同提供本地验收证据。

2026-09-08 审核沿用当前分支，不部署，也不修改 CI/CD 或系统网络。浏览器使用项目内自签 HTTPS。本次完成条件不包含旧部署状态；本地结果不代表远程发布。
