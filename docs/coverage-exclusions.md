# Coverage scope and reviewed exclusions

Reviewed by the repository owner on 2026-08-23 for ADR-254. The enforced core
contains deterministic catalog, configuration provenance, guard, registry,
serialization, data-store, and graph-projection code. Every included report must
clear 95% line and branch coverage independently.

The following maintained files are excluded from the instrumented Sonar coverage
gate but remain covered by named real tests:

| Files | Reason | Required evidence |
| --- | --- | --- |
| `src/ui/app.js` | Browser event orchestration; Chromium precise coverage has no stable semantic JavaScript branch IDs. | Full Selenium suite, ten visual cases, four reviewed viewports, and daily real Gherkin run. |
| `src/model_builder/builder.py`, `factory.py`, `tracing.py`, `introspection.py`, `blocks.py` | Model construction and tracing deliberately replace Python frame tracing and execute native Torch/Transformers paths. | Real generated-artifact, tracing/block, catalog, drift, and packaged-site tests. |
| `src/model_builder/semantics.py`, `staged.py`, `hf_config.py` | Generated semantic/catalog integration is validated as parsed artifacts and across all published models. | Semantic, staged, configuration, schema, deterministic generation, browser, and UAT tests. |
| `src/model_builder/validate.py`, `drift.py`, `__main__.py` | CLI and full-catalog integration paths operate on the checked-in runtime catalog. | Real CLI fixture tests plus the mandatory full drift command in CI. |
| `src/__init__.py`, `src/model_builder/__init__.py` | Package markers and schema constant contain no decision logic. | Import and build tests. |

## Release tooling classification

Release scripts are maintained test and delivery infrastructure, not shipped
product source, so they remain outside `sonar.sources=src`. Their required
evidence is classified explicitly instead of counting the tools' own execution
as product coverage.

| File | Classification | Required evidence |
| --- | --- | --- |
| `scripts/audit-node.mjs` | Release dependency policy | Real `package-lock.json` release audit and zero installed JavaScript package assertion. |
| `scripts/audit-python.py` | Release dependency policy | Exact-lock, severity, alias, and exception unit fixtures plus the IPv4-only live OSV release audit. |
| `scripts/build-ui.mjs` | Release build tooling | Real generated catalog builds in browser, visual, UAT, and deployable-site checks. |
| `scripts/check-coverage.py` | Coverage gate tooling | Valid, malformed, missing, and sub-threshold report unit fixtures plus the real coverage gate. |
| `scripts/check-uat-report.py` | Acceptance gate tooling | Valid, dry-run, missing-artifact, and failed-scenario report unit fixtures plus the real UAT report gate. |
| `scripts/lock-python.py` | Administrative lock generator | Reviewed lockfile diff, exact-lock policy tests, clean locked install, and release audit after regeneration. |
| `scripts/run-ui-coverage.mjs` | Coverage harness | Real Node test instrumentation producing independently gated data-store and graph-model LCOV reports. |

An exclusion may be removed only when its replacement report preserves real model
execution and supplies stable line and branch identifiers. Changes to this table
require review in the same pull request as the coverage configuration.

## Audit-v2 coverage additions

The Python core report now includes `parameter_counts.py`, `meta_parameters.py`
and `journey_facts.py`, exercised with real pinned configurations and canonical
graphs. Browser LCOV discovers every shipped UI JavaScript module. Daily UAT
also exercises review downloads/restoration, finder filters, panel sizing and
configuration comparison. The existing exclusions and independent 95% report
thresholds are unchanged; the extended `test/audit` matrix is additional evidence.

## 繁體中文

核心報告各自維持 95% 行與分支涵蓋率；既有排除清單未變更。新增參數計算、meta 模型及旅程埠模組納入 Python 核心報告，使用真實設定與圖形。瀏覽器涵蓋率收集全部前端 JavaScript，每日 UAT 新增下載、還原、搜尋、面板尺寸及設定比較；完整審核矩陣另行提供證據。

## 简体中文

核心报告各自维持 95% 行与分支覆盖率；现有排除清单未变更。新增参数计算、meta 模型及旅程端口模块纳入 Python 核心报告，使用真实配置与图形。浏览器覆盖率收集全部前端 JavaScript，每日 UAT 新增下载、恢复、搜索、面板尺寸及配置比较；完整审核矩阵另行提供证据。
