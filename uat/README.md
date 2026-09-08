# Model Vis acceptance and recording suites

The custom runner provides three executable Gherkin suites:

- `daily` is the human/AI black-box acceptance checklist and produces Sonar generic test execution XML.
- `demo-en` is the timed English product-introduction recording flow.
- `demo-yue` is the timed Traditional Chinese Cantonese product-introduction recording flow.

Validate every feature and binding without opening Chromium:

```bash
venv/bin/python -m uat.run --suite all --dry-run
```

Run the complete daily browser acceptance or one recording flow:

```bash
venv/bin/python -m uat.run --suite daily
venv/bin/python -m uat.run --suite demo-en
venv/bin/python -m uat.run --suite demo-yue
```

Use `--scenario "name fragment"` to rerun one diagnostic scenario without weakening the normal complete-suite command.

A real run builds the static viewer, serves self-signed HTTPS on IPv4 `0.0.0.0` with a repository-local certificate, opens a clean Chromium profile through `127.0.0.1`, and writes `checklist.json`, `sonar-test-execution.xml`, screenshots, and browser LCOV under `artifacts/<suite>/`. A dry result validates syntax and bindings only; it is not a product pass.

## Recording contract

Recording narration waits for the TTS wrapper and then waits any remaining minimum duration declared in the feature. Each optional variable names one executable wrapper; arguments are passed as environment variables rather than command-line text:

- `DEMO_TTS_COMMAND` receives `DEMO_TTS_LANGUAGE`, `DEMO_TTS_TEXT`, and `DEMO_TTS_MIN_SECONDS`.
- `DEMO_RECORD_START_COMMAND` receives `DEMO_SUITE` and `DEMO_REPOSITORY` and must return after recording starts.
- `DEMO_RECORD_STOP_COMMAND` receives the same values and must finalize the recording.

Without wrappers, recording hooks are no-ops and narration is printed and timed. MP4 storage remains the operator's responsibility.

## Feature coverage matrix

| User-visible area | Daily scenario |
| --- | --- |
| Startup defaults, 101-model catalog, graph overlays | Start in the documented professional workspace |
| Search, no-result recovery, category filter, source sort | Search, filter, sort, and recover from no catalog results |
| Invalid and shareable model URIs | Reject an unknown URI and recover with a valid shareable URI |
| Architecture, Family, Modules, Blocks, Operations; detail and labels | Move through every graph mode and detail level |
| Explain, Details, I/O, Source, Runtime, Official/Trace/Diff config | Inspect explanations, tensors, source, runtime, and configurations |
| Graph search, output path, zoom, fit, focus, legend, minimap | Follow graph search, tensor routes, zoom, focus, and overlays |
| Drag, resize, local persistence, reset | Persist a dragged and resized layout and reset it |
| Theme, label, selected-stage, and deep-route persistence | Persist theme, view preferences, selection, and deep route |
| Empty comparison guidance and normalized two-model comparison | Explain comparison selection and compare two model families |
| Partial-record badge and provenance warning | Surface partial model provenance instead of hiding it |
| Module search, keyboard tree, source hierarchy | Navigate modules and source files with search and keyboard |
| Responsive catalog and inspector drawers | Use catalog and inspector drawers on a mobile viewport |
| Tensor Journey and parameter/operation distributions | Run Tensor Journey and inspect generated distributions |
| Annotated SVG/JSON/CSV downloads and saved-view restoration | Save and export an annotated investigation |
| Exact interface filters and panel-width persistence | Find an exact operation and persist panel sizing |
| Scope-aware differences and pinned configuration fields | Compare compatible facts with configuration drilldown |

The English and Cantonese recording suites introduce the catalog, demonstrate semantic stages and Tensor Journey, expose trace/source/config evidence, and finish with normalized cross-family comparison.

## 繁體中文

`daily` 是實際 Chromium 驗收；`demo-en` 與 `demo-yue` 是定時錄製流程。`--suite all --dry-run` 只驗證語法與綁定，不能代替圖形介面驗收。實際執行使用專案內自簽 HTTPS 與全新瀏覽器設定，將清單、截圖和涵蓋率保存在 `artifacts/<suite>/`。預設工作區為 Standard／Both，共 101 個模型；新增審核測試另見 `test/audit/`。

## 简体中文

`daily` 是实际 Chromium 验收；`demo-en` 与 `demo-yue` 是定时录制流程。`--suite all --dry-run` 只验证语法与绑定，不能代替图形界面验收。实际运行使用项目内自签 HTTPS 和全新浏览器配置，将清单、截图和覆盖率保存在 `artifacts/<suite>/`。默认工作区为 Standard／Both，共 101 个模型；新增审核测试另见 `test/audit/`。
