<#
.SYNOPSIS
  Publish and verify the M1 implementation on a dedicated branch + pull request.

.DESCRIPTION
  Replaces the earlier verify-and-push.ps1 flow. Key differences, all required
  by the current work order:

    * The remote repository ALREADY EXISTS (disdorqin/math-modeling-workstation,
      public, main @ 30a5ebb, 22 commits). This script NEVER creates a
      repository -- it verifies the existing one and fails with instructions if
      it is unreachable.
    * Work lands on a dedicated branch (m1-verification-and-ci) branched from
      the verified remote main, never directly on main.
    * The import is split into six focused, reviewable commits rather than one
      opaque blob.
    * A pull request is opened (not merged).
    * GitHub Actions is watched for the EXACT pushed SHA, not "the latest run".
    * The transcript is written to verification-run.log, which is gitignored and
      never committed.

  Hard stops: high-confidence secret findings, private relay hostnames leaking
  into committable content, any failing test, runtime check, or smoke.

.PARAMETER SkipPush
  Run every verification, stage and commit nothing. Use this first.

.PARAMETER SkipInstall
  Skip `pip install -e` when the environment is already prepared.

.PARAMETER Branch
  Feature branch name. Default m1-verification-and-ci.

.EXAMPLE
  .\scripts\publish-m1-branch.ps1 -SkipPush
  .\scripts\publish-m1-branch.ps1
#>
[CmdletBinding()]
param(
    [switch]$SkipPush,
    [switch]$SkipInstall,
    [string]$Branch   = "m1-verification-and-ci",
    [string]$RepoSlug = "disdorqin/math-modeling-workstation",
    [string]$BaseSha  = "30a5ebbd6d6bdd58683e1c84e9a42db8448c3e28"
)

$ErrorActionPreference = "Stop"
$ProgressPreference    = "SilentlyContinue"

$repoRoot = (Get-Location).Path
$log = Join-Path $repoRoot "verification-run.log"
Start-Transcript -Path $log -Force | Out-Null

function Phase([string]$n) {
    Write-Host ""; Write-Host ("=" * 78) -ForegroundColor Cyan
    Write-Host "  $n" -ForegroundColor Cyan; Write-Host ("=" * 78) -ForegroundColor Cyan
}
function Step([string]$n) { Write-Host "`n--- $n" -ForegroundColor Yellow }
function Fail([string]$m) {
    Write-Host "`nFAILED: $m" -ForegroundColor Red
    Write-Host "Transcript: $log" -ForegroundColor Red
    try { Stop-Transcript | Out-Null } catch { }
    exit 1
}
function Run([string]$what, [scriptblock]$b) {
    Step $what; & $b
    if ($LASTEXITCODE -ne 0 -and $null -ne $LASTEXITCODE) { Fail "$what (exit $LASTEXITCODE)" }
}

try {

# =============================================================== 1. IDENTITY
Phase "1. REPOSITORY IDENTITY (real Windows working tree)"
$top = git rev-parse --show-toplevel 2>&1
if ($LASTEXITCODE -ne 0) { Fail "not a git working tree: $top" }
Write-Host "toplevel   : $top"
Write-Host "remotes    :"; git remote -v
Write-Host "branch     : $(git branch --show-current)"
Write-Host "HEAD       : $(git rev-parse HEAD)"
Write-Host "log -5     :"; git log -5 --oneline
Write-Host "status     :"; git status --short
Write-Host "porcelain  :"; git status --porcelain=v1 | Select-Object -First 40
Write-Host "branch -vv :"; git branch -vv

$originUrl = git remote get-url origin 2>&1
if ($LASTEXITCODE -ne 0) { Fail "no 'origin' remote configured" }
if ($originUrl -notmatch "math-modeling-workstation") {
    Fail "origin '$originUrl' is not the expected repository -- refusing to continue"
}
Write-Host "origin confirmed: $originUrl" -ForegroundColor Green

# ================================================ 2. VERIFY EXISTING REMOTE
Phase "2. VERIFY THE EXISTING REMOTE (this script never creates a repository)"
Run "git fetch origin --prune" { git fetch origin --prune }

Step "remote main"
$remoteMainLine = git ls-remote origin refs/heads/main
if ($LASTEXITCODE -ne 0 -or -not $remoteMainLine) {
    Fail "cannot reach origin. The repository is known to exist; this is an auth/network problem. Run 'gh auth login' (browser flow) and retry. This script will NOT create a repository."
}
$remoteMain = ($remoteMainLine -split "\s+")[0]
Write-Host "remote main SHA : $remoteMain"
Write-Host "expected base   : $BaseSha"
if ($remoteMain -ne $BaseSha) {
    Write-Host "NOTE: remote main has moved since the recorded base. Branching from the CURRENT remote main." -ForegroundColor Yellow
}

$ghCli = Get-Command gh -ErrorAction SilentlyContinue
if ($ghCli) {
    Step "gh auth status (token value never printed)"
    gh auth status 2>&1 | Select-Object -First 8
    Step "gh repo view"
    gh repo view $RepoSlug --json nameWithOwner,url,visibility,defaultBranchRef
} else {
    Fail "gh CLI is required for the PR and Actions phases. Install: winget install --id GitHub.cli, then 'gh auth login' (choose the browser flow -- do not paste a token anywhere)."
}

# ================================================== 3. FEATURE BRANCH SETUP
Phase "3. FEATURE BRANCH"
$localMain = git rev-parse main 2>$null
Write-Host "local main : $localMain"
Write-Host "remote main: $remoteMain"
if ($localMain -ne $remoteMain) {
    Write-Host "local main differs from remote main -- NOT overwriting either history." -ForegroundColor Yellow
    Write-Host "Investigate with: git log --oneline main..origin/main ; git log --oneline origin/main..main" -ForegroundColor Yellow
    Fail "local/remote main divergence -- resolve manually before publishing"
}

$exists = git branch --list $Branch
if ($exists) {
    Step "branch '$Branch' already exists -- inspecting, not resetting"
    git log --oneline "main..$Branch"
    git switch $Branch
} else {
    Step "creating '$Branch' from main"
    git switch main
    git pull --ff-only origin main
    git switch -c $Branch
}
if ($LASTEXITCODE -ne 0) { Fail "could not switch to $Branch" }
Write-Host "on branch: $(git branch --show-current)" -ForegroundColor Green

# ============================================= 4. WORKFLOW PLACEMENT
Phase "4. WORKFLOW FILES"
$tpl = "ci-templates\agent-layer-tests.yml"
$dst = ".github\workflows\agent-layer-tests.yml"
New-Item -ItemType Directory -Force ".github\workflows" | Out-Null
if ((Test-Path $tpl) -and (Test-Path $dst)) {
    Write-Host "both copies exist -- comparing before touching anything"
    $diff = Compare-Object (Get-Content $tpl) (Get-Content $dst)
    if ($diff) { $diff | Format-Table -AutoSize; Copy-Item $tpl $dst -Force; Write-Host "repo copy refreshed from template" }
    else { Write-Host "identical" }
    Remove-Item $tpl -Force
} elseif (Test-Path $tpl) {
    Move-Item $tpl $dst; Write-Host "moved template -> $dst" -ForegroundColor Green
} elseif (-not (Test-Path $dst)) {
    Fail "agent-layer-tests.yml found in neither location"
}
foreach ($wf in @(".github\workflows\ci.yml", $dst)) {
    if (-not (Test-Path $wf)) { Fail "required workflow missing: $wf" }
    Write-Host "present: $wf ($((Get-Item $wf).Length) bytes)"
}
Step "YAML parse check (both workflows)"
python -c "import sys,yaml;[yaml.safe_load(open(p,encoding='utf-8')) for p in ['.github/workflows/ci.yml','.github/workflows/agent-layer-tests.yml']];print('both workflows parse as valid YAML')"
if ($LASTEXITCODE -ne 0) { Fail "workflow YAML invalid (pip install pyyaml if the parser is missing)" }

Step "workflow safety scan"
$wfText = (Get-Content ".github\workflows\ci.yml" -Raw) + (Get-Content $dst -Raw)
if ($wfText -match "continue-on-error")  { Fail "continue-on-error present in a workflow -- mandatory verification must not be suppressed" }
if ($wfText -match "D:\\\\|C:\\\\Users")  { Fail "workflow contains a user-specific absolute path" }
if ($wfText -match '__version__.*langgraph|getattr\(langgraph') { Fail "workflow uses getattr(langgraph,'__version__') -- must use importlib.metadata.version" }
Write-Host "workflow scan clean" -ForegroundColor Green

# ================================================= 5. WORKING-TREE INVENTORY
Phase "5. WORKING-TREE INVENTORY"
Run "git status --short" { git status --short }
Run "git diff --stat"    { git diff --stat }
Step "untracked (exclude-standard)"
git ls-files --others --exclude-standard
Step "counts"
$tracked   = (git ls-files | Measure-Object).Count
$modified  = (git diff --name-only | Measure-Object).Count
$untracked = (git ls-files --others --exclude-standard | Measure-Object).Count
$ignored   = (git ls-files --others --ignored --exclude-standard | Measure-Object).Count
Write-Host "tracked=$tracked modified=$modified untracked=$untracked ignored=$ignored"

# ============================================ 6. SECRET SAFETY (PUBLIC REPO)
Phase "6. SECRET SAFETY -- this repository is PUBLIC"
$needed = @('*.local.json','.env','verification-run.log','artifacts/','ci-artifacts/','output/','logs/','__pycache__/','.venv/')
$gi = Get-Content ".gitignore" -Raw
$missing = @()
foreach ($rule in $needed) { if ($gi -notmatch [regex]::Escape($rule)) { $missing += $rule } }
if ($missing) {
    Write-Host "adding missing ignore rules: $($missing -join ', ')" -ForegroundColor Yellow
    Add-Content ".gitignore" "`n# public-repo safety (added by publish-m1-branch.ps1)"
    foreach ($rule in $missing) { Add-Content ".gitignore" $rule }
    Add-Content ".gitignore" "VERIFICATION_REPORT_*.md`nDELIVERY_STATUS_*.md"
}

Step "credential file must be ignored and untracked"
git check-ignore -v "config/llm-routes.local.json"
if ($LASTEXITCODE -ne 0) { Fail "config/llm-routes.local.json is NOT ignored" }
$t = git ls-files "config/llm-routes.local.json"
if ($t) { Fail "config/llm-routes.local.json is TRACKED -- remove from the index before publishing" }
Write-Host "ignored and untracked" -ForegroundColor Green
git check-ignore -v "verification-run.log" | Out-Null
if ($LASTEXITCODE -ne 0) { Fail "verification-run.log is not ignored -- the transcript must never be committed" }

Step "the credential file must appear in NO commit, on any ref"
$hist = git log --all --oneline -- "config/llm-routes.local.json"
if ($hist) { Fail "credential file appears in git history. STOP. Rotate the credentials and clean history before any further publication." }
Write-Host "absent from all history" -ForegroundColor Green

Step "build the candidate file set actually destined for the commit"
$candidateFiles = @()
foreach ($d in @("src","tests","scripts","docs",".github")) {
    if (Test-Path $d) {
        $candidateFiles += (Get-ChildItem $d -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Extension -in ".py",".md",".yml",".yaml",".toml",".cfg",".ps1",".json",".txt" } |
            Select-Object -ExpandProperty FullName)
    }
}
foreach ($f in @("pyproject.toml",".gitignore")) { if (Test-Path $f) { $candidateFiles += (Resolve-Path $f).Path } }
Write-Host "scanning $($candidateFiles.Count) candidate files (tracked AND untracked -- git grep would miss the untracked M1 import)"

Step "private relay hostname leak check (hostnames read in memory, NEVER printed)"
$routeFile = "config\llm-routes.local.json"
if (Test-Path $routeFile) {
    $hosts = @()
    try {
        $cfg = Get-Content $routeFile -Raw
        foreach ($m in [regex]::Matches($cfg, 'https?://([A-Za-z0-9\.\-]+)')) { $hosts += $m.Groups[1].Value }
        $hosts = $hosts | Sort-Object -Unique | Where-Object { $_ -notmatch '^(localhost|127\.0\.0\.1|api\.openai\.com)$' }
    } catch { Write-Host "could not parse route file (not fatal)" -ForegroundColor Yellow }
    Write-Host "extracted $($hosts.Count) private relay hostname(s) into memory for scanning (values withheld)"
    # NOTE: git grep only searches TRACKED content. The M1 import is largely
    # untracked, so scanning must run over the candidate files ON DISK.
    $leaks = @()
    foreach ($h in $hosts) {
        $m = Select-String -Path $candidateFiles -SimpleMatch -Pattern $h -ErrorAction SilentlyContinue
        foreach ($x in $m) { $leaks += ("{0}:{1}" -f (Resolve-Path -Relative $x.Path), $x.LineNumber) }
    }
    if ($leaks) {
        Write-Host "PRIVATE RELAY HOSTNAME FOUND IN COMMITTABLE CONTENT (locations only):" -ForegroundColor Red
        $leaks | Sort-Object -Unique
        Fail "a private relay hostname appears in content intended for a PUBLIC commit -- redact it first"
    }
    Write-Host "no private relay hostname appears in committable content" -ForegroundColor Green
} else {
    Write-Host "no local route file present -- leak check not applicable"
}

Step "high-confidence secret scan (locations only, values never printed)"
# Same reason as above: scan files on disk, not `git grep` (tracked-only).
$strong = "(gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|://[^/\s:@]+:[^/\s:@]+@)"
$hits = Select-String -Path $candidateFiles -Pattern $strong -ErrorAction SilentlyContinue
if ($hits) {
    Write-Host "HIGH-CONFIDENCE SECRET (locations only, values withheld):" -ForegroundColor Red
    $hits | ForEach-Object { "{0}:{1}" -f (Resolve-Path -Relative $_.Path), $_.LineNumber }
    Fail "secret-shaped value in committable content. Remove it, and rotate the credential if it was ever exposed."
}
Write-Host "clean" -ForegroundColor Green

# ================================================== 7. ENVIRONMENT
Phase "7. WINDOWS DEPENDENCY ENVIRONMENT"
if (-not $SkipInstall) {
    Run "pip upgrade" { python -m pip install --upgrade pip -q }
    Run "install [dev,ui,langgraph]" { python -m pip install -e ".[dev,ui,langgraph]" }
}
Step "versions (record these verbatim in the report)"
python --version
python -m pytest --version
python -c "import streamlit; print('streamlit', streamlit.__version__)"
python -c "import importlib.metadata as m; print('langgraph', m.version('langgraph'))"
python -c "import importlib.metadata as m; [print(p, m.version(p)) for p in ('pydantic','numpy','pandas','scikit-learn','matplotlib')]"

# ================================================== 8. PYTEST
Phase "8. FULL PYTEST ON WINDOWS (no ignores)"
Run "collect-only" { python -m pytest --collect-only -q | Select-Object -Last 6 }
Step "full suite"
python -m pytest -ra -vv --durations=10
$pytestExit = $LASTEXITCODE
Write-Host "pytest exit code: $pytestExit"
if ($pytestExit -ne 0) { Fail "pytest failed on Windows (exit $pytestExit) -- fix before publishing" }

# ================================================== 9. RUNTIME MODES
Phase "9. RUNTIME MODES (builtin / langgraph / auto)"
$rt = Join-Path $env:TEMP "mmw-rt"
Remove-Item $rt -Recurse -Force -ErrorAction SilentlyContinue
$CASE = (python -m mathworkstation.cli --output-root $rt create-case --competition CUMCM --title "runtime identity" --language zh | ConvertFrom-Json).case_id
Write-Host "case: $CASE"
function RuntimeOf([string]$mode) {
    Step "run-agent-pipeline --runtime $mode"
    python -m mathworkstation.cli --output-root $rt run-agent-pipeline --case-id $CASE --runtime $mode | Out-Null
    if ($LASTEXITCODE -ne 0) { Fail "run-agent-pipeline --runtime $mode failed" }
    $s = Get-Content (Join-Path $rt "$CASE\agents\run_summary.json") -Raw | ConvertFrom-Json
    Write-Host ("  requested={0} actual={1} langgraph_available={2} accepted={3} verdicts={4}" -f `
        $mode, $s.runtime, $s.langgraph_available, $s.accepted_count, ($s.verdict_counts | ConvertTo-Json -Compress))
    return $s.runtime
}
$rB = RuntimeOf "builtin"; $rL = RuntimeOf "langgraph"; $rA = RuntimeOf "auto"
if ($rB -ne "builtin")        { Fail "builtin mode recorded runtime='$rB'" }
if ($rL -notmatch "langgraph"){ Fail "langgraph mode recorded runtime='$rL' -- real LangGraph did NOT execute (silent fallback is forbidden)" }
if ($rA -notmatch "langgraph"){ Fail "auto did not select langgraph though it is installed (got '$rA')" }
Write-Host "RUNTIME IDENTITY PROVEN builtin='$rB' langgraph='$rL' auto='$rA'" -ForegroundColor Green

# ================================================== 10. CONFORMANCE
Phase "10. RUNTIME CONFORMANCE"
New-Item -ItemType Directory -Force "artifacts" | Out-Null
python -m mathworkstation.cli --output-root $rt compare-agent-runtimes --case-id $CASE --report "artifacts\runtime-conformance.json"
$cExit = $LASTEXITCODE
Write-Host "compare-agent-runtimes exit: $cExit"
if (Test-Path "artifacts\runtime-conformance.json") { Get-Content "artifacts\runtime-conformance.json" -Raw }
switch ($cExit) {
  0 { Write-Host "CONFORMANT" -ForegroundColor Green }
  1 { Fail "runtimes DIFFER. Classify each difference as (a) semantic defect, (b) nondeterministic ordering needing canonicalization, or (c) legitimate runtime-only metadata; fix and add a regression test. Do NOT weaken the comparator." }
  3 { Fail "LANGGRAPH_UNAVAILABLE -- the extra is not installed here" }
  4 { Fail "wrong runtime actually ran" }
  default { Fail "compare-agent-runtimes exit $cExit" }
}

# ================================================== 11. SMOKES
Phase "11. AGENT MODELING SMOKE (modeling SUBGRAPH only)"
$mRoot = Join-Path $env:TEMP "mmw-modeling"
Remove-Item $mRoot -Recurse -Force -ErrorAction SilentlyContinue
$mCase = (python -m mathworkstation.cli --output-root $mRoot create-case --competition CUMCM --title "modeling smoke" --language zh | ConvertFrom-Json).case_id
$mDs = (python -m mathworkstation.cli --output-root $mRoot register-dataset --case-id $mCase --name diabetes --kind OBSERVED --source "examples\fixtures\diabetes_progression.csv" --description "fixture" | ConvertFrom-Json).dataset_id
$first  = python scripts\run_modeling_fanout_on_case.py $mRoot $mCase $mDs progression age,sex,bmi,bp,s1,s2,s3,s4,s5,s6
if ($LASTEXITCODE -ne 0) { Fail "fan-out first run failed" }
$second = python scripts\run_modeling_fanout_on_case.py $mRoot $mCase $mDs progression age,sex,bmi,bp,s1,s2,s3,s4,s5,s6
if ($LASTEXITCODE -ne 0) { Fail "fan-out second run failed" }
$nComputed = ([regex]::Matches(($first -join "`n"),  "computed")).Count
$nReused   = ([regex]::Matches(($second -join "`n"), "reused")).Count
Write-Host "first-run 'computed'=$nComputed   second-run 'reused'=$nReused"
if ($nComputed -lt 1) { Fail "first run computed nothing" }
if ($nReused   -lt 1) { Fail "second run did not reuse -- compute-level reuse regressed" }

$env:MMW_ROOT = $mRoot; $env:MMW_CASE = $mCase
$promote = @'
import json, os, subprocess, sys
root, case_id = os.environ['MMW_ROOT'], os.environ['MMW_CASE']
sys.path.insert(0, 'src')
from mathworkstation.case_manager import CaseManager
from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.datasets import DatasetRegistry
from mathworkstation.claims import ClaimRegistry
cases = CaseManager(root); artifacts = ArtifactRegistry(cases)
claims = ClaimRegistry(cases, artifacts, DatasetRegistry(cases, artifacts))
active = artifacts.list_artifacts(case_id)
proto = [a for a in active if a['artifact_type']=='modeling_protocol' and a['status']=='ACTIVE'][-1]
comp  = [a for a in active if a['artifact_type']=='model_comparison' and a['status']=='ACTIVE'][-1]
comparison = json.load(open(os.path.join(root, case_id, comp['path'].replace('/', os.sep)), encoding='utf-8'))
for c in comparison['candidates']:
    print('  candidate', c['candidate_id'], c['status'], c.get('metric_name'), c.get('metric_value'))
run = lambda *a: subprocess.run([sys.executable,'-m','mathworkstation.cli','--output-root',root,*a], check=True)
run('assess-modeling-evidence','--case-id',case_id,'--protocol-artifact-id',proto['artifact_id'],'--comparison-artifact-id',comp['artifact_id'])
run('approve-modeling-evidence','--case-id',case_id,'--protocol-artifact-id',proto['artifact_id'],'--comparison-artifact-id',comp['artifact_id'],'--approved-by','local','--note','windows verification')
sel = [c for c in claims.list_claims(case_id) if c['claim_type']=='model_selection' and comp['artifact_id'] in c['evidence_artifact_ids']]
assert len(sel)==1, f'expected exactly one model_selection claim, got {len(sel)}'
run('recheck-claim-evidence','--case-id',case_id,'--claim-id',sel[0]['claim_id'],'--checked-by','local')
final = claims.get(case_id, sel[0]['claim_id'])
assert final['status']=='VERIFIED', f"claim not VERIFIED: {final['status']}"
reg = os.path.join(root, case_id, 'claim_registry.jsonl')
before = len(open(reg, encoding='utf-8').readlines())
run('recheck-claim-evidence','--case-id',case_id,'--claim-id',sel[0]['claim_id'],'--checked-by','local')
after = len(open(reg, encoding='utf-8').readlines())
assert before==after, f'recheck not idempotent: {before} -> {after}'
print('  protocol :', proto['artifact_id'])
print('  comparison:', comp['artifact_id'])
print('  VERIFIED claim:', final['claim_id'])
print('  recheck idempotent, registry lines:', after)
'@
$tmpPy = Join-Path $env:TEMP "mmw-promote.py"
$promote | Set-Content -Path $tmpPy -Encoding UTF8
python $tmpPy
if ($LASTEXITCODE -ne 0) { Fail "evidence promotion / VERIFIED claim check failed" }
Remove-Item $tmpPy -Force -ErrorAction SilentlyContinue
Run "validate-case (modeling smoke)" { python -m mathworkstation.cli --output-root $mRoot validate-case --case-id $mCase }

Phase "12. FULL DETERMINISTIC PAPER SMOKE (whole legal DAG)"
$fRoot = Join-Path $env:TEMP "mmw-full"
Remove-Item $fRoot -Recurse -Force -ErrorAction SilentlyContinue
Run "run_full_deterministic_smoke.py" { python scripts\run_full_deterministic_smoke.py $fRoot }
$fCase = (Get-ChildItem $fRoot -Directory | Select-Object -First 1).Name
$paper = Join-Path $fRoot "$fCase\paper\final.md"
Write-Host "case=$fCase  final.md=$((Get-Item $paper).Length) bytes  embedded figures=$(([regex]::Matches((Get-Content $paper -Raw),'!\[')).Count)"
$latex = Join-Path $fRoot "$fCase\paper\latex\main.tex"
if (Test-Path $latex) { Write-Host "latex includegraphics=$(([regex]::Matches((Get-Content $latex -Raw),'includegraphics')).Count)" }
Write-Host "figure files:"; (Get-ChildItem (Join-Path $fRoot "$fCase\figures") -Recurse -File -Include *.png,*.svg | Measure-Object).Count
Write-Host "claims by status:"
(Get-Content (Join-Path $fRoot "$fCase\claim_registry.jsonl") | ForEach-Object { $_ | ConvertFrom-Json } |
    Group-Object status | Select-Object Name, Count | Format-Table -AutoSize | Out-String)
Write-Host "audit/export files: $((Get-ChildItem (Join-Path $fRoot "$fCase\export") -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count)"

if ($SkipPush) {
    Phase "DRY RUN COMPLETE -- nothing staged, committed, or pushed"
    Write-Host "Transcript: $log" -ForegroundColor Cyan
    Stop-Transcript | Out-Null; exit 0
}

# ============================================ 13. REVIEWABLE COMMITS
Phase "13. SIX FOCUSED COMMITS"
function Commit([string]$msg, [string[]]$paths) {
    Step "commit: $msg"
    $any = $false
    foreach ($p in $paths) { if (Test-Path $p) { git add -- $p; $any = $true } }
    $staged = git diff --cached --name-only
    if (-not $staged) { Write-Host "  (nothing to stage -- skipped)"; return }
    $staged | ForEach-Object { Write-Host "    $_" }
    foreach ($bad in @("output/","logs/",".local.json",".env.local","verification-run.log","artifacts/","VERIFICATION_REPORT_","DELIVERY_STATUS_")) {
        $off = $staged | Where-Object { $_ -like "*$bad*" -and $_ -notlike "*.gitkeep" }
        if ($off) { Fail "refusing to commit -- staged path matches '$bad': $off" }
    }
    git commit -m $msg
    if ($LASTEXITCODE -ne 0) { Fail "commit failed: $msg" }
}

Commit "Secure public repository exclusions" @(".gitignore")
Commit "Add M1 agent contracts and adjudication" @(
    "src/mathworkstation/agents/__init__.py","src/mathworkstation/agents/contracts.py",
    "src/mathworkstation/agents/base.py","src/mathworkstation/agents/adjudicator.py",
    "src/mathworkstation/agents/roster.py","tests/test_agent_layer.py")
Commit "Add modeling fan-out, compute reuse, and evidence promotion" @(
    "src/mathworkstation/agents/modeling.py","src/mathworkstation/paper_ready.py",
    "src/mathworkstation/claims.py","src/mathworkstation/cli.py",
    "tests/test_modeling_fanout.py","tests/test_modeling_evidence_promotion.py")
Commit "Add runtime semantics, conformance tooling, and runtime tests" @(
    "src/mathworkstation/agents/graph.py","src/mathworkstation/agents/runtime.py",
    "src/mathworkstation/agents/semantics.py","tests/test_agent_runtime_semantics.py",
    "tests/test_deterministic_paper_path.py","tests/test_ui_app.py")
Commit "Add deterministic smoke scripts and CI workflows" @(
    "scripts/run_modeling_fanout_on_case.py","scripts/run_full_deterministic_smoke.py",
    "scripts/publish-m1-branch.ps1","scripts/verify-and-push.ps1",
    "tests/test_full_smoke_dag_order.py",
    ".github/workflows/ci.yml",".github/workflows/agent-layer-tests.yml")
Commit "Reconcile M1 architecture and execution documentation" @(
    "docs/multi-agent-architecture.md","docs/端到端实跑报告-2026-07-26.md")

Step "anything still unstaged that should have been included?"
git status --short

# ============================================ 14. PUSH THE BRANCH
Phase "14. PUSH FEATURE BRANCH (never main, never --force)"
$sha = (git rev-parse HEAD).Trim()
git push --set-upstream origin $Branch
if ($LASTEXITCODE -ne 0) { Fail "push failed" }
$remoteLine = git ls-remote origin "refs/heads/$Branch"
$remoteSha = ($remoteLine -split "\s+")[0]
Write-Output "LOCAL=$sha"
Write-Output "REMOTE=$remoteSha"
if ($sha -ne $remoteSha) { Fail "remote branch SHA mismatch" }
Write-Host "gh api sha: $(gh api "repos/$RepoSlug/commits/$Branch" --jq '.sha')"
Write-Host "PUSH VERIFIED: $remoteSha" -ForegroundColor Green

# ============================================ 15. PULL REQUEST
Phase "15. PULL REQUEST (opened, NOT merged)"
$existing = gh pr list --head $Branch --json number,url --jq ".[0].url" 2>$null
if ($existing) {
    Write-Host "PR already exists: $existing"
} else {
    $body = @'
## Scope
Publishes and verifies the M1 multi-agent modeling layer. **M2 is NOT included** —
no `problem_analyst`, no `section_writer`, no LLM providers, no new model families.

## Security exclusions
`config/*.local.json`, `.env*`, `output/`, `logs/`, `artifacts/`,
`verification-run.log` and session reports are gitignored and verified absent
from the commit. The credential route file appears in no commit on any ref.
Private relay hostnames were redacted from committed documentation.

## M1 architecture
Agents propose; only the Adjudicator writes. Bounded modeling fan-out
(3 candidates -> independent evaluation -> judge -> adjudication), immutable
modeling protocol, content-hash proposal replay, compute-level candidate reuse,
and an evidence-promotion path ending in a VERIFIED winning-model claim.

## Local Windows verification
See the PR checks and the run transcript. Full pytest, all three runtime modes
with runtime identity proven from `run_summary.json`, runtime conformance,
the modeling-subgraph smoke (real fits then zero-fit reuse), and the full
deterministic paper smoke (legal DAG order through submission preflight and two
hash-drift-free `validate-case` runs).

## Known limitations
Concurrent fan-out, multi-judge arbitration and multi-round debate remain
design-only. Superseded protocol lineages cannot be re-evaluated. External LLM
provider behaviour is unverified (no LLM path is exercised here).
'@
    $bodyFile = Join-Path $env:TEMP "m1-pr-body.md"
    $body | Set-Content -Path $bodyFile -Encoding UTF8
    gh pr create --base main --head $Branch --title "Verify and publish M1 multi-agent modeling layer" --body-file $bodyFile
    if ($LASTEXITCODE -ne 0) { Fail "gh pr create failed" }
    Remove-Item $bodyFile -Force -ErrorAction SilentlyContinue
}
gh pr view --json number,url,state,headRefName,baseRefName

# ============================================ 16. GITHUB ACTIONS
Phase "16. GITHUB ACTIONS FOR THIS EXACT SHA"
Write-Host "watching runs whose headSha == $sha"
Start-Sleep -Seconds 10
$runs = gh run list --branch $Branch --limit 20 --json databaseId,headSha,name,status,conclusion,url |
        ConvertFrom-Json | Where-Object { $_.headSha -eq $sha }
if (-not $runs) {
    Write-Host "no run yet for this SHA; waiting 30s" -ForegroundColor Yellow
    Start-Sleep -Seconds 30
    $runs = gh run list --branch $Branch --limit 20 --json databaseId,headSha,name,status,conclusion,url |
            ConvertFrom-Json | Where-Object { $_.headSha -eq $sha }
}
if (-not $runs) { Fail "no Actions run appeared for $sha -- check that workflows are enabled for this repository" }
foreach ($r in $runs) {
    Step "run $($r.databaseId) : $($r.name)"
    Write-Host "url: $($r.url)"
    gh run watch $r.databaseId --exit-status
    $rc = $LASTEXITCODE
    gh run view $r.databaseId
    if ($rc -ne 0) {
        Step "FAILED JOB LOGS (run $($r.databaseId))"
        gh run view $r.databaseId --log-failed
        Write-Host "CI FAILED. Fix the root cause, commit, push, and re-run this script." -ForegroundColor Red
    }
}
Step "per-check summary"
gh pr checks
Step "download the conformance artifact"
gh run download --name runtime-conformance --dir ".\ci-artifacts" 2>&1
Get-ChildItem ".\ci-artifacts" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 10 -Property Name, Length

Phase "DONE -- PR is open and NOT merged"
Write-Host "Transcript: $log (gitignored, never committed)" -ForegroundColor Cyan

}
finally { try { Stop-Transcript | Out-Null } catch { } }
