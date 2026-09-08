# Audit results / 審核結果 / 审核结果

English: F01–F14 and R01–R08 are implemented and locally verified on the current branch, retaining 101 models. Deployment is excluded. The GitHub push was stopped after five seconds and was not retried under the user's rule; the commits remain local.

繁中：F01–F14 與 R01–R08 已在目前分支完成並通過本機驗證，保留 101 個模型，不部署。GitHub 推送依使用者規則於五秒終止且不重試，提交保留於本機。

简中：F01–F14 与 R01–R08 已在当前分支完成并通过本地验证，保留 101 个模型，不部署。GitHub 推送按用户规则于五秒终止且不重试，提交保留在本地。

| Check / 檢查 / 检查 | Result / 結果 / 结果 |
| --- | --- |
| Python | 74 passed / 通過 / 通过 |
| JavaScript | 47 passed / 通過 / 通过 |
| Existing browser regressions / 既有瀏覽器回歸 / 现有浏览器回归 | 30 passed, 108 s |
| Extended audit / 完整審核 / 完整审核 | 84 passed, 335 s |
| Daily GUI UAT / 每日圖形驗收 / 每日图形验收 | 16 passed, 26 s |
| Catalog integrity / 目錄完整性 / 目录完整性 | 101 models; no errors / 無錯誤 / 无错误 |
| Determinism / 重現性 / 重现性 | 210 managed files; no drift / 無漂移 / 无漂移 |
| Existing coverage gates / 既有涵蓋率 / 现有覆盖率 | Each report ≥95% lines and branches |
| Dependency audit / 依賴審核 / 依赖审核 | Passed / 通過 / 通过 |

| Requirements / 需求 | Evidence / 證據 / 证据 |
| --- | --- |
| F01–F03, R01, R04 | `test/unit/test_parameter_counts.py`, `test_journey_ports.py`; audit identity/journey tests |
| F04–F08, R02 | Audit geometry, drawers, journeys, overview and layouts; 52 viewports and 36 I/O layouts |
| F09–F11, R05 | Audit comparison and configuration detail tests; all three pairs × five views |
| F12–F13, R03, R08 | Audit preferences/finder tests; real graph projection and tensor filter tests |
| F14 | Audit delayed navigation, recovery, source/config recovery and empty-scope tests |
| R06–R07 | Audit review downloads, clipboard, saved views, drawer and keyboard tests; daily UAT |

English: Local machine-readable evidence is under `artifacts/audit-v2/`: `requirements.json`, `final-checks.json`, `audit-complete.xml`, `e2e-complete.xml`, and screenshots. Daily GUI evidence is `artifacts/uat/checklist.json`. Missing mappings and unverified pretrained numerics remain explicitly disclosed.

繁中：本機證據位於 `artifacts/audit-v2/`，含需求清單、結果、測試報告與截圖；每日 GUI 證據為 `artifacts/uat/checklist.json`。缺少映射及未驗證的預訓練數值均明確揭露。

简中：本地证据位于 `artifacts/audit-v2/`，包含需求清单、结果、测试报告与截图；每日 GUI 证据为 `artifacts/uat/checklist.json`。缺少映射及未验证的预训练数值均明确披露。
