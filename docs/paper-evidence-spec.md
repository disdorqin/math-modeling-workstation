# 论文 Claim、提纲与一致性规范

## Claim

重要事实、数值和模型结论必须登记 Claim，并引用至少一个 Artifact。只有所有证据均 `paper_eligible=true` 时 Claim 才是 `VERIFIED`。引用 SYNTHETIC Dataset 的 Claim 保留 `synthetic_data_claim` 限制，正文必须明确披露。

## 提纲

提纲使用固定章节 ID 和严格 Schema。每节声明允许使用的 Claim ID、Figure ID 和写作目的。提纲验证拒绝未知、未验证 Claim 以及未达到论文就绪的 Figure。

## 分章节工作区

每节拥有独立 `context.json` 和 `draft.md`。Context Pack 只包含该节允许的证据，并强制：数字引用 Claim、图片引用 Figure、缺证据标记、禁止修改其他章节。后续 LLM 适配器只能写当前章节。

## 一致性门

一致性检查扫描：未知/越权/未验证 Claim，未知/越权/未就绪 Figure，占位符，未归因数字，SYNTHETIC 披露缺失及 Artifact 哈希异常。门状态为 `PASS/REVIEW/BLOCK`；有占位符或证据越权时必须 BLOCK。

