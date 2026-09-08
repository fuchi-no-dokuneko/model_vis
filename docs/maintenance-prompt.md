# Maintenance / 維護 / 维护

English: Read README.md, docs/audit-v2.md and the latest monthly goal log first. Keep the current branch and 101 models; audit-v2 excludes deployment and restructuring. Later instructions prevail.

繁中：先讀 README.md、審核指南與最新每月目標日誌。保留目前分支及 101 模型，不部署、不重整；後續指示優先。

简中：先读 README.md、审核指南与最新每月目标日志。保留当前分支及 101 模型，不部署、不重整；后续指示优先。

English: Use real offline traces and pinned configs. Separate initialized traces, config-derived counts, task scope and preflight estimates. Journeys match observed ports. Show missing mappings and verification limits; avoid per-model browser rules.

繁中：使用真實離線追蹤及固定來源設定，區分初始化追蹤量、設定推導量、任務輸出頭與近似預估。旅程步驟需符合本運算觀測埠，明示缺少映射與科學驗證限制，不加入前端單一模型規則。

简中：使用真实离线跟踪及固定来源配置，区分初始化跟踪量、配置推导量、任务输出头与近似预估。旅程步骤需符合本运算观测端口，明示缺少映射与科学验证限制，不加入前端单一模型规则。

English: Implement all MVPs, test, refine, then run unit, integrity, drift, browser, coverage and UAT checks. Use test/audit for checks. Serve local self-signed HTTPS on IPv4 0.0.0.0. Do not change system networking or CI/CD.

繁中：先完成全部初版，再測試真實流程、精修及完整驗收。test/audit 獨立驗收，保留 CI 時限。本機使用專案內自簽 HTTPS 與 IPv4 0.0.0.0，不修改系統網絡或 CI/CD。

简中：先完成全部初版，再测试真实流程、完善及完整验收。test/audit 独立验收，保留 CI 时限。本地使用项目内自签 HTTPS 与 IPv4 0.0.0.0，不修改系统网络或 CI/CD。

English: Append Traditional Chinese tickets, at most seven content lines; log unexpected bugs and decisions. Log GUI successes with integer minutes and monthly amendments verbatim. Update bilingual todo.txt and text-coverage.txt with module/mocks. Commit per feature using English, Traditional Chinese and a Jira key. Push after five commits, kill at five seconds, and never retry a network failure.

繁中：開發日誌只追加繁中票記，每項最多七行，記錄意外錯誤與決策；真實 GUI 成功里程碑需記整數分鐘。逐字記錄每月指示，更新雙語待辦與涵蓋清單。依功能提交英語、繁中及 Jira 編號；每五次提交推送，五秒終止，網絡失敗不重試。

简中：开发日志只追加繁中票记，每项最多七行，记录意外错误与决策；真实 GUI 成功里程碑需记整数分钟。逐字记录每月指示，更新双语待办与覆盖清单。按功能提交英语、繁中及 Jira 编号；每五次提交推送，五秒终止，网络失败不重试。
