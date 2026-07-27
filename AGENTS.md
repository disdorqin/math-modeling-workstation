# AGENTS.md — 代码理解指引（写给所有接入本仓库的 AI 智能体）

> 本文件随仓库走。任何打开 / 克隆本仓库的 AI 编程智能体（Claude Code、Cursor、Codex、WorkBuddy 等）都应先读它，并在理解代码前优先查询本地代码知识图谱。

## 接入本仓库的第一步：先查本地代码知识图谱，不要直接 grep / Read 全仓库

本项目已建立 **CodeGraph 本地代码知识图谱**（100% 本地运行、零网络外传、匿名遥测已关闭），索引存于本仓库根目录 `.codegraph/codegraph.db`。图谱预存了「符号 + 调用边 + 跨文件依赖」，你无需靠反复 grep / Read 扫描来理解代码结构。

### 情况 A：你的环境已接入 CodeGraph MCP（工具名以 `codegraph_` 开头）
1. 先调 `codegraph_status`（可带 `projectPath` 指向本仓库）确认图谱就绪、查看规模。
2. 用 `codegraph_explore <与任务相关的关键词>` 一次拿到相关符号的源码 + 调用路径。
3. 需要调用关系：`codegraph_callers <符号>` / `codegraph_callees <符号>` / `codegraph_impact <符号>`。
4. 全局找符号：`codegraph_search` / `codegraph_query`。

### 情况 B：环境没有 CodeGraph MCP，但本机装了 `codegraph` CLI
- `codegraph status` 确认图谱就绪；
- `codegraph explore <关键词>` / `codegraph query <符号>` / `codegraph callers <符号>` 等同效。

### 情况 C：以上都不可用
- 退化为常规 grep / Read，但请优先依托图谱指示的入口，并提醒用户「本仓库有本地代码图谱可加速理解」。

## 为什么必须先用图谱
相比全仓库扫描，用图谱探索可让工具调用 ↓58%、token ↓47%、耗时 ↓22%（CodeGraph 官方实测）。

## 图谱维护
CodeGraph 可在改动代码后自动增量同步；如大幅改动后图谱陈旧，可在本仓库内运行 `codegraph index --force` 重建索引。

---
本指引由共享智能体大脑自动生成 · 项目：math_model（python）· 2026-07-25
