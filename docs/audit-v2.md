# Audit-v2 / 審核第二版 / 审核第二版

English: This batch retains 101 models on the current branch. Deployment is excluded. Config-derived counts use the exact configured class with tied parameters counted once; task-head variants have separate counts. BERT: 109,482,240 (BertModel). Arcee: 4,291,496,960 (backbone), 4,619,189,760 (causal LM). Unmapped aliases and unsupported native configurations show unavailable. Pretrained numerical equivalence remains unverified.

繁中：此次保留目前分支與 101 個模型，不部署。設定推導參數量依實際類別計算，共用參數只計一次，任務輸出頭另列。BERT 基底為 109,482,240；Arcee 基底為 4,291,496,960，語言模型為 4,619,189,760。未映射別名及尚不支援的原生設定顯示不可用，未驗證預訓練數值等價。

简中：本次保留当前分支与 101 个模型，不部署。配置推导参数量按实际类别计算，共享参数只计一次，任务输出头另列。BERT 基础模型为 109,482,240；Arcee 基础模型为 4,291,496,960，语言模型为 4,619,189,760。未映射别名及尚不支持的原生配置显示不可用，未验证预训练数值等价。

English: Start with Standard/Both or Professional preset. Expand overview groups to inspect operations. Finder filters tensor, dtype and shape on the same port; Enter/Shift+Enter moves through matches. I/O cards show their own input/output ports and explicit hidden-step gaps. Compare offers differences-only and expandable config fields. Review/export copies links, saves annotations and exports SVG/JSON/CSV. Panel resize handles support arrow keys; Tools exposes controls on small screens.

繁中：預設 Standard／Both，亦可選 Professional。展開概覽群組檢查運算。搜尋的張量、型別及形狀需符合同一埠；Enter／Shift+Enter 切換結果。I/O 顯示本運算輸入輸出及省略步數。比較可只顯示差異與展開設定。Review/export 可複製連結、儲存註記及匯出 SVG／JSON／CSV。面板可用方向鍵調整；小螢幕由 Tools 開啟控制項。

简中：默认 Standard／Both，也可选择 Professional。展开概览分组检查运算。搜索的张量、类型及形状需匹配同一端口；Enter／Shift+Enter 切换结果。I/O 显示本运算输入输出及省略步数。比较可只显示差异与展开配置。Review/export 可复制链接、保存注释及导出 SVG／JSON／CSV。面板可用方向键调整；小屏幕通过 Tools 打开控件。

Checks / 驗證 / 验证:

```bash
npm test
venv/bin/python -m pytest -q test/unit test/uat test/e2e test/audit
venv/bin/python -m src.model_builder.validate --model-code model_code --catalog model.txt --allow-partial
venv/bin/python -m src.model_builder.drift
npm run test:uat
npm run test:uat:check
```
