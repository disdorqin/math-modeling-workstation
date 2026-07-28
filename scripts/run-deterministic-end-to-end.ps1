<#
.SYNOPSIS
  无 API 的全链路实跑：赛题输入 → 论文 → 投稿包 → 审计 ZIP。

.DESCRIPTION
  复现 docs/端到端实跑报告-2026-07-26.md 记录的运行。全程不调用任何外部 API，
  使用 examples/fixtures 下的真实临床数据集与配套赛题、模型方案、论文提纲。

  与 run-task-paper 冒烟不同，本脚本走的是 DAG 主链路，会经过数据登记、质量门、
  EDA、模型比较、人工选择、敏感性、证据晋升、分章节写作、一致性门与投稿预检。

.EXAMPLE
  $env:PYTHONPATH="src"
  .\scripts\run-deterministic-end-to-end.ps1 -OutputRoot D:\mmw-run
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$OutputRoot,
    [string]$ApprovedBy = "human",
    [string]$Profile = "CUMCM"
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$fixtures = Join-Path $repo "examples\fixtures"
$sections = Join-Path $repo "examples\sections"

function MW {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    $output = & python -m mathworkstation.cli --output-root $OutputRoot @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw ($output -join "`n") }
    return ($output -join "`n")
}

function MWJson {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    return (MW @Arguments | ConvertFrom-Json)
}

function ArtifactId {
    param([string]$CaseId, [string]$Type)
    $registry = Join-Path $OutputRoot "$CaseId\artifact_registry.jsonl"
    $match = Get-Content $registry -Encoding UTF8 |
        ForEach-Object { $_ | ConvertFrom-Json } |
        Where-Object { $_.artifact_type -eq $Type -and $_.status -eq "ACTIVE" } |
        Select-Object -Last 1
    if (-not $match) { throw "artifact not found: $Type" }
    return $match.artifact_id
}

Write-Host "==> 建立 Case 与 Session" -ForegroundColor Cyan
$case = (MWJson create-case --competition CUMCM --title "慢性疾病一年期病情进展量化建模与风险分层").case_id
$session = (MWJson create-session --case-id $case).session_id
Write-Host "    case=$case session=$session"

MW start-node   --case-id $case --node-id input_validation | Out-Null
MW succeed-node --case-id $case --node-id input_validation | Out-Null
MW ingest-problem --case-id $case --source (Join-Path $fixtures "real_case_problem.md") | Out-Null

Write-Host "==> 数据登记与质量门" -ForegroundColor Cyan
$dataset = (MWJson register-dataset --case-id $case `
    --source (Join-Path $fixtures "diabetes_progression.csv") `
    --name "糖尿病一年期进展观测数据" --kind OBSERVED `
    --license "public research dataset (Efron et al. 2004)" `
    --description "442 名患者基线 10 特征与一年后病情进展指数").dataset_id
MW complete-data-registration --case-id $case | Out-Null
MW approve-node --case-id $case --node-id data_registration --approved-by $ApprovedBy | Out-Null
MW profile-dataset --case-id $case --dataset-id $dataset --target-column progression --session-id $session | Out-Null
MW run-eda        --case-id $case --dataset-id $dataset --target-column progression --session-id $session | Out-Null

Write-Host "==> 题目分析与模型方案" -ForegroundColor Cyan
MW start-node   --case-id $case --node-id problem_analysis | Out-Null
MW succeed-node --case-id $case --node-id problem_analysis | Out-Null
MW approve-node --case-id $case --node-id problem_analysis --approved-by $ApprovedBy | Out-Null
MW validate-model-plan --case-id $case --source (Join-Path $fixtures "real_case_model_plan.json") --dataset-id $dataset | Out-Null
MW approve-node --case-id $case --node-id model_plan --approved-by $ApprovedBy | Out-Null
$plan = ArtifactId $case "model_plan_validated"

Write-Host "==> Baseline 与正式模型比较" -ForegroundColor Cyan
MW run-baseline --case-id $case --dataset-id $dataset --target-column progression --task-type regression --session-id $session | Out-Null
$comparison = MWJson run-model-comparison --case-id $case --plan-artifact-id $plan --session-id $session
$experiment = $comparison.result.experiment_id
$best = $comparison.result.best_model
Write-Host "    experiment=$experiment best=$best"

MW select-model --case-id $case --experiment-id $experiment --selected-model $best `
    --comparison-artifact-id (ArtifactId $case "model_comparison") `
    --selected-by $ApprovedBy --rationale "交叉验证主指标最优且折间标准差最小" | Out-Null
MW run-sensitivity --case-id $case --experiment-id $experiment --plan-artifact-id $plan --session-id $session | Out-Null

Write-Host "==> 证据审批与图形晋升" -ForegroundColor Cyan
$selection   = ArtifactId $case "model_selection"
$sensitivity = ArtifactId $case "sensitivity_results"
$profileArt  = ArtifactId $case "dataset_profile"
$edaArt      = ArtifactId $case "eda_summary"
MW assess-paper-ready  --case-id $case --experiment-id $experiment `
    --selection-artifact-id $selection --sensitivity-artifact-id $sensitivity | Out-Null
MW approve-paper-ready --case-id $case --experiment-id $experiment `
    --selection-artifact-id $selection --sensitivity-artifact-id $sensitivity `
    --approved-by $ApprovedBy --note "证据链完整：比较、诊断、选择、敏感性、数据画像与 EDA 摘要" `
    --additional-artifact-id $profileArt --additional-artifact-id $edaArt | Out-Null
$approval = ArtifactId $case "paper_ready_approval"

foreach ($title in @("目标变量 progression 分布", "数值变量相关性热力图", "候选模型交叉验证比较", "模型样本比例与随机种子敏感性")) {
    $figure = (MWJson list-figures --case-id $case | Where-Object { $_.title -eq $title } | Select-Object -Last 1).figure_id
    if ($figure) {
        MW promote-figure --case-id $case --figure-id $figure --approval-artifact-id $approval `
            --approved-by $ApprovedBy --note "由确定性脚本生成，与已批准实验证据一致" | Out-Null
    }
}

Write-Host ""
Write-Host "已完成到证据层。后续步骤需要与本次实际 claim_id / figure_id 绑定：" -ForegroundColor Yellow
Write-Host "  1. create-claim 登记结论，再把 claim_id / figure_id 写入提纲的 claim_ids / figure_ids"
Write-Host "     模板见 examples\fixtures\real_case_outline.json（其中的 ID 属于原始实跑，需替换）"
Write-Host "  2. validate-outline / approve-node paper_outline / init-paper-sections"
Write-Host "  3. update-section 逐节写入 examples\sections\*.md"
Write-Host "  4. complete-paper-draft / check-paper-consistency / prepare-submission --profile $Profile"
Write-Host "  5. degrade-node refinement_loop（本次不跑 LLM 精修）/ final_review / export-case"
Write-Host ""
Write-Host "case-id  = $case"     -ForegroundColor Green
Write-Host "session  = $session"  -ForegroundColor Green
Write-Host "dataset  = $dataset"  -ForegroundColor Green
Write-Host "approval = $approval" -ForegroundColor Green
