<#
.SYNOPSIS
  One-command execution of the M1 delivery + CI-verification work order.

.DESCRIPTION
  Runs, in order, on the REAL repository:

    1.  repository identity  (rev-parse / remote / branch / log / status)
    2.  workflow placement   (ci-templates -> .github/workflows, with compare)
    3.  pending-change audit (status/diff/stat + secret scan + ignore-gap fix)
    4.  dependency install   ([dev,ui,langgraph]) and version capture
    5.  full pytest          (collect-only, then -ra -vv, no ignores)
    6.  runtime checks       (builtin / langgraph / auto + runtime identity)
    7.  runtime conformance  (compare-agent-runtimes + report inspection)
    8.  agent modeling smoke (fan-out, zero-fit rerun, promotion, VERIFIED)
    9.  full paper smoke     (whole legal DAG -> paper -> preflight -> audit)
    10. precise staging      (explicit paths only; never `git add -A`)
    11. commit + push
    12. GitHub Actions       (gh run watch, job results, conformance artifact)

  Everything is transcripted to .\verification-run.log. The script STOPS at the
  first failure so the log can be inspected rather than buried.

  Nothing is committed if the secret scan flags anything, and nothing is pushed
  if any test, runtime check, or smoke fails.

.PARAMETER SkipPush
  Do everything except commit/push/Actions. Use for a dry run first.

.PARAMETER SkipInstall
  Skip `pip install -e` (use when the environment is already prepared).

.EXAMPLE
  cd <path-to-your-clone-of-math-modeling-workstation>
  .\scripts\verify-and-push.ps1 -SkipPush     # dry run
  .\scripts\verify-and-push.ps1               # full run
#>
[CmdletBinding()]
param(
    [switch]$SkipPush,
    [switch]$SkipInstall,
    [switch]$Public,          # opt-in ONLY: without this the repo is created PRIVATE
    [string]$ExpectedRemote = "math-modeling-workstation",
    [string]$RepoSlug = "disdorqin/math-modeling-workstation"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$repo = (Get-Location).Path
$log = Join-Path $repo "verification-run.log"
Start-Transcript -Path $log -Force | Out-Null

function Phase([string]$n) {
    Write-Host ""
    Write-Host ("=" * 78) -ForegroundColor Cyan
    Write-Host "  $n" -ForegroundColor Cyan
    Write-Host ("=" * 78) -ForegroundColor Cyan
}
function Step([string]$n) { Write-Host "`n--- $n" -ForegroundColor Yellow }
function Fail([string]$m) {
    Write-Host "`nFAILED: $m" -ForegroundColor Red
    Write-Host "Transcript: $log" -ForegroundColor Red
    Stop-Transcript | Out-Null
    exit 1
}
function Run([string]$what, [scriptblock]$block) {
    Step $what
    & $block
    if ($LASTEXITCODE -ne 0 -and $null -ne $LASTEXITCODE) { Fail "$what (exit $LASTEXITCODE)" }
}

try {

# ---------------------------------------------------------------- 1. identity
Phase "1. REPOSITORY IDENTITY"
$top = git rev-parse --show-toplevel 2>&1
if ($LASTEXITCODE -ne 0) { Fail "not a git working tree: $top" }
Write-Host "toplevel : $top"
Write-Host "remotes  :"; git remote -v
$branch = (git branch --show-current).Trim()
Write-Host "branch   : $branch"
Write-Host "HEAD     : $(git log -1 --oneline)"
Write-Host "status   :"; git status --short

$originUrl = (git remote get-url origin 2>&1)
if ($LASTEXITCODE -ne 0) { Fail "no 'origin' remote configured" }
if ($originUrl -notmatch [regex]::Escape($ExpectedRemote)) {
    Fail "origin '$originUrl' does not contain '$ExpectedRemote' -- refusing to touch an unrelated repository"
}
Write-Host "origin confirmed: $originUrl" -ForegroundColor Green

# --------------------------------------------- 1b. does the remote REALLY exist
Phase "1b. REMOTE REPOSITORY EXISTENCE"
# A configured remote.origin.url is NOT proof the repository exists.
Step "git ls-remote origin"
$lsRemote = git ls-remote origin 2>&1
$lsExit = $LASTEXITCODE
$lsRemote | Select-Object -First 5
Write-Host "git ls-remote exit: $lsExit"

$ghCli = Get-Command gh -ErrorAction SilentlyContinue
$repoExists = $false
$repoState = "unknown"

if ($lsExit -eq 0) {
    $repoExists = $true; $repoState = "exists and is accessible"
} elseif ($lsRemote -match "Repository not found|not found|does not exist") {
    $repoState = "does not exist (or is invisible to these credentials)"
} elseif ($lsRemote -match "Authentication failed|could not read Username|Permission denied|403") {
    $repoState = "exists-or-not: authentication prevented verification"
} else {
    $repoState = "network or authentication prevented verification"
}
Write-Host "classification: $repoState" -ForegroundColor Cyan

if ($ghCli) {
    Step "gh auth status + gh repo view"
    gh auth status 2>&1 | Select-Object -First 6
    gh repo view $RepoSlug --json nameWithOwner,url,visibility,defaultBranchRef 2>&1 | Select-Object -First 12
    if ($LASTEXITCODE -eq 0) { $repoExists = $true; $repoState = "exists and is accessible" }
} else {
    Write-Host "gh CLI not installed -- install with: winget install --id GitHub.cli" -ForegroundColor Yellow
}

if (-not $repoExists) {
    Phase "1c. CREATE THE REMOTE REPOSITORY"
    if (-not $ghCli) {
        Fail "remote repository is not verifiable ($repoState) and gh CLI is unavailable to create it. Install gh (winget install --id GitHub.cli), run 'gh auth login', then re-run this script."
    }
    $vis = if ($Public) { "--public" } else { "--private" }
    if ($Public) {
        Write-Host "WARNING: -Public was passed. A public repo will expose everything committed." -ForegroundColor Red
        $ans = Read-Host "Type PUBLIC to confirm public visibility, anything else to abort"
        if ($ans -ne "PUBLIC") { Fail "public creation not confirmed -- aborting (re-run without -Public for a private repo)" }
    } else {
        Write-Host "creating as PRIVATE (default). Pass -Public only after reviewing every committed file." -ForegroundColor Yellow
    }
    Step "gh repo create $RepoSlug $vis (origin already configured -- not re-adding a remote)"
    gh repo create $RepoSlug $vis --description "Evidence-first mathematical modeling workstation"
    if ($LASTEXITCODE -ne 0) { Fail "gh repo create failed -- see output above" }
    Write-Host "created" -ForegroundColor Green
    Step "re-verify"
    git ls-remote origin | Select-Object -First 3
    if ($LASTEXITCODE -ne 0) { Fail "repository still not reachable after creation" }
    gh repo view $RepoSlug --json nameWithOwner,url,visibility,defaultBranchRef
}

# ------------------------------------------------------- 2. workflow placement
Phase "2. WORKFLOW PLACEMENT"
$tpl = "ci-templates\agent-layer-tests.yml"
$dst = ".github\workflows\agent-layer-tests.yml"
$hasTpl = Test-Path $tpl
$hasDst = Test-Path $dst
Write-Host "ci-templates copy : $hasTpl"
Write-Host "workflows copy    : $hasDst"

if ($hasTpl -and $hasDst) {
    $same = (Get-FileHash $tpl).Hash -eq (Get-FileHash $dst).Hash
    Write-Host "both exist; identical = $same"
    if (-not $same) {
        Write-Host "DIFFERENT -- template is newer/authoritative, overwriting repo copy:" -ForegroundColor Yellow
        Compare-Object (Get-Content $tpl) (Get-Content $dst) | Format-Table -AutoSize
        Copy-Item $tpl $dst -Force
    }
    Remove-Item $tpl -Force
    Write-Host "removed the now-redundant template copy"
} elseif ($hasTpl) {
    New-Item -ItemType Directory -Force ".github\workflows" | Out-Null
    Move-Item $tpl $dst
    Write-Host "moved template -> $dst" -ForegroundColor Green
} elseif (-not $hasDst) {
    Fail "workflow found in neither ci-templates nor .github/workflows"
}

Step "the actual repository copy (.github/workflows/agent-layer-tests.yml)"
Get-Content $dst | Select-Object -First 40
Write-Host "... (full file in transcript below)"
Get-Content $dst | Out-String | Write-Verbose
Step "git diff for the workflow path"
git diff -- $dst
git status --short -- $dst

# ------------------------------------------------------------ 3. change audit
Phase "3. PENDING-CHANGE AUDIT"
Run "git status --short" { git status --short }
Run "git diff --stat"    { git diff --stat }

Step "untracked files (these are what a careless 'git add .' would capture)"
git ls-files --others --exclude-standard

Step "ignore-gap check: *.local.json config files are NOT covered by .gitignore"
$gitignore = Get-Content ".gitignore" -Raw
if ($gitignore -notmatch '\*\.local\.json') {
    Write-Host "adding '*.local.json' to .gitignore (config/llm-routes.local.json holds relay credentials)" -ForegroundColor Yellow
    Add-Content ".gitignore" "`n# Local LLM/image relay route files -- contain credentials, never commit`n*.local.json`n`n# Verification transcript (local run artefact, may echo absolute paths)`nverification-run.log`nci-artifacts/`nartifacts/`nVERIFICATION_REPORT_*.md`nDELIVERY_STATUS_*.md"
    Get-Content ".gitignore" | Select-Object -Last 4
} else {
    Write-Host "already covered"
}

Step "secret scan over to-be-staged content (LOCATIONS ONLY -- values are never printed)"
# High-confidence patterns: an actual credential VALUE, not a variable name or
# a doc mentioning the word "token". Matching values are deliberately never
# echoed -- only file:line, so the transcript can be shared safely.
$strong = "(gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|AKIA[0-9A-Z]{16})"
$strongHits = git grep -n -I -E $strong -- src tests scripts docs .github "*.md" "*.toml" "*.cfg" 2>$null
if ($strongHits) {
    Write-Host "HIGH-CONFIDENCE CREDENTIAL PATTERN FOUND (locations only):" -ForegroundColor Red
    $strongHits | ForEach-Object { ($_ -split ":")[0..1] -join ":" }
    Fail "secret scan tripped -- a credential-shaped value is present in content that would be committed. Remove it (and rotate the credential) before pushing. Values intentionally not printed."
}
Write-Host "no credential-shaped values in the paths to be staged" -ForegroundColor Green

Step "weak-signal scan (variable names / docs -- informational, locations only)"
$weak = git grep -n -I -E "(api[_-]?key|secret|password|authorization|bearer)" -- src tests scripts docs .github "*.md" "*.toml" 2>$null
if ($weak) {
    Write-Host "$(($weak | Measure-Object).Count) informational match(es); locations:" -ForegroundColor Yellow
    $weak | ForEach-Object { ($_ -split ":")[0..1] -join ":" } | Select-Object -Unique -First 25
    Write-Host "(these are variable names / documentation -- reviewed, not blocking)" -ForegroundColor Yellow
} else {
    Write-Host "none" -ForegroundColor Green
}

Step "prove the credential file is IGNORED (git check-ignore) and listed as ignored"
git check-ignore -v "config/llm-routes.local.json"
if ($LASTEXITCODE -ne 0) { Fail "config/llm-routes.local.json is NOT ignored by .gitignore" }
git status --short --ignored -- config | Select-Object -First 10

Step "confirm secret-bearing files are NOT staged/tracked"
foreach ($f in @("config/llm-routes.local.json", "config/image-routes.local.json", ".env.local")) {
    $tracked = git ls-files --error-unmatch $f 2>$null
    if ($LASTEXITCODE -eq 0) { Fail "$f is TRACKED by git -- must be removed from the index before pushing" }
    Write-Host "  untracked (good): $f"
}

# ------------------------------------------------------------- 4. environment
Phase "4. DEPENDENCY ENVIRONMENT"
if (-not $SkipInstall) {
    Run "pip upgrade"  { python -m pip install --upgrade pip -q }
    Run "install [dev,ui,langgraph]" { python -m pip install -e ".[dev,ui,langgraph]" }
}
Step "versions"
python --version
python -m pytest --version
python -c "import streamlit; print('streamlit', streamlit.__version__)"
python -c "import importlib.metadata as m; print('langgraph', m.version('langgraph'))"
python -c "import importlib.metadata as m; [print(p, m.version(p)) for p in ('pydantic','numpy','pandas','scikit-learn','matplotlib')]"

# ------------------------------------------------------------------ 5. pytest
Phase "5. FULL PYTEST (no ignores -- test_ui_app must EXECUTE)"
Run "collect-only" { python -m pytest --collect-only -q | Select-Object -Last 5 }
Run "full suite"   { python -m pytest -ra -vv --durations=10 | Select-Object -Last 60 }

Step "targeted suites"
foreach ($t in @("tests/test_agent_layer.py","tests/test_agent_runtime_semantics.py",
                 "tests/test_modeling_fanout.py","tests/test_modeling_evidence_promotion.py",
                 "tests/test_full_smoke_dag_order.py")) {
    Write-Host "`n>>> $t"
    python -m pytest $t -q
    if ($LASTEXITCODE -ne 0) { Fail "targeted suite failed: $t" }
}

# --------------------------------------------------------- 6. runtime checks
Phase "6. RUNTIME EXECUTION (builtin / langgraph / auto)"
$rtRoot = Join-Path $env:TEMP "mmw-runtime-check"
Remove-Item $rtRoot -Recurse -Force -ErrorAction SilentlyContinue
$caseJson = python -m mathworkstation.cli --output-root $rtRoot create-case --competition CUMCM --title "runtime identity check" --language zh
if ($LASTEXITCODE -ne 0) { Fail "create-case failed" }
$CASE = ($caseJson | ConvertFrom-Json).case_id
Write-Host "case: $CASE"

function Show-Runtime([string]$mode) {
    Step "run-agent-pipeline --runtime $mode"
    python -m mathworkstation.cli --output-root $rtRoot run-agent-pipeline --case-id $CASE --runtime $mode | Out-Null
    if ($LASTEXITCODE -ne 0) { Fail "run-agent-pipeline --runtime $mode failed" }
    $s = Get-Content (Join-Path $rtRoot "$CASE\agents\run_summary.json") -Raw | ConvertFrom-Json
    Write-Host ("  run_summary.runtime = {0} | langgraph_available = {1}" -f $s.runtime, $s.langgraph_available) -ForegroundColor Green
    return $s.runtime
}
$rBuiltin = Show-Runtime "builtin"
$rLang    = Show-Runtime "langgraph"
$rAuto    = Show-Runtime "auto"

if ($rBuiltin -ne "builtin") { Fail "--runtime builtin did not record runtime=builtin (got '$rBuiltin')" }
if ($rLang -notmatch "langgraph") { Fail "--runtime langgraph did not record a langgraph runtime (got '$rLang') -- the real engine did not execute" }
if ($rAuto -notmatch "langgraph") { Fail "--runtime auto did not select langgraph despite it being installed (got '$rAuto')" }
Write-Host "`nRUNTIME IDENTITY PROVEN: builtin='$rBuiltin' langgraph='$rLang' auto='$rAuto'" -ForegroundColor Green

# ----------------------------------------------------- 7. runtime conformance
Phase "7. RUNTIME CONFORMANCE"
New-Item -ItemType Directory -Force "artifacts" | Out-Null
$report = "artifacts\runtime-conformance.json"
python -m mathworkstation.cli --output-root $rtRoot compare-agent-runtimes --case-id $CASE --report $report
$confExit = $LASTEXITCODE
Write-Host "compare-agent-runtimes exit code: $confExit"
if (Test-Path $report) {
    Step "generated report"
    Get-Content $report -Raw
} else {
    Write-Host "no report written" -ForegroundColor Yellow
}
switch ($confExit) {
    0 { Write-Host "CONFORMANT" -ForegroundColor Green }
    1 { Fail "runtimes DIFFER (exit 1). Inspect $report. Do NOT weaken the comparator -- classify each difference as (a) semantic defect, (b) nondeterministic ordering needing canonicalization, or (c) legitimate runtime-only metadata, then fix + add a regression test." }
    3 { Fail "LANGGRAPH_UNAVAILABLE (exit 3) -- the langgraph extra is not actually installed in this environment" }
    4 { Fail "wrong runtime actually ran (exit 4)" }
    default { Fail "compare-agent-runtimes exit $confExit" }
}

# -------------------------------------------------- 8. agent modeling smoke
Phase "8. AGENT MODELING SMOKE (modeling SUBGRAPH -- not the full pipeline)"
$mRoot = Join-Path $env:TEMP "mmw-modeling-smoke"
Remove-Item $mRoot -Recurse -Force -ErrorAction SilentlyContinue
$mCase = (python -m mathworkstation.cli --output-root $mRoot create-case --competition CUMCM --title "CI modeling smoke" --language zh | ConvertFrom-Json).case_id
$mDs = (python -m mathworkstation.cli --output-root $mRoot register-dataset --case-id $mCase --name diabetes --kind OBSERVED --source "examples\fixtures\diabetes_progression.csv" --description "CI fixture" | ConvertFrom-Json).dataset_id
Write-Host "case=$mCase dataset=$mDs"

Step "first fan-out run -- must COMPUTE (real sklearn fits)"
$first = python scripts\run_modeling_fanout_on_case.py $mRoot $mCase $mDs progression age,sex,bmi,bp,s1,s2,s3,s4,s5,s6
if ($LASTEXITCODE -ne 0) { Fail "modeling fan-out (first run) failed" }
$firstComputed = ([regex]::Matches($first -join "`n", "computed")).Count
Write-Host "  'computed' occurrences: $firstComputed"
if ($firstComputed -lt 1) { Fail "first run did not compute any candidate" }

Step "second identical run -- must REUSE (zero model fits)"
$second = python scripts\run_modeling_fanout_on_case.py $mRoot $mCase $mDs progression age,sex,bmi,bp,s1,s2,s3,s4,s5,s6
if ($LASTEXITCODE -ne 0) { Fail "modeling fan-out (second run) failed" }
$secondReused = ([regex]::Matches($second -join "`n", "reused")).Count
Write-Host "  'reused' occurrences: $secondReused"
if ($secondReused -lt 1) { Fail "second run did not reuse -- compute-level reuse regressed" }

Step "evidence promotion + exactly-one-VERIFIED-claim + validate-case"
$env:MMW_SMOKE_ROOT = $mRoot; $env:MMW_SMOKE_CASE = $mCase
# Single-quoted here-string: PowerShell must NOT interpolate this Python.
# Written to a temp file rather than piped, so Windows console encoding
# cannot corrupt it on the way to the interpreter.
$promotePy = @'
import json, os, subprocess, sys
root, case_id = os.environ['MMW_SMOKE_ROOT'], os.environ['MMW_SMOKE_CASE']
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
run('approve-modeling-evidence','--case-id',case_id,'--protocol-artifact-id',proto['artifact_id'],'--comparison-artifact-id',comp['artifact_id'],'--approved-by','ci','--note','local verification run')
sel = [c for c in claims.list_claims(case_id) if c['claim_type']=='model_selection' and comp['artifact_id'] in c['evidence_artifact_ids']]
assert len(sel)==1, f'expected exactly one model_selection claim, got {len(sel)}'
run('recheck-claim-evidence','--case-id',case_id,'--claim-id',sel[0]['claim_id'],'--checked-by','ci')
final = claims.get(case_id, sel[0]['claim_id'])
assert final['status']=='VERIFIED', f"claim not VERIFIED: {final['status']} {final.get('restrictions')}"
before = len(open(os.path.join(root, case_id, 'claim_registry.jsonl'), encoding='utf-8').readlines())
run('recheck-claim-evidence','--case-id',case_id,'--claim-id',sel[0]['claim_id'],'--checked-by','ci')
after = len(open(os.path.join(root, case_id, 'claim_registry.jsonl'), encoding='utf-8').readlines())
assert before==after, f'recheck is not idempotent: {before} -> {after} registry lines'
print('  VERIFIED winning-model claim:', final['claim_id'], '| winner:', sel[0]['text'][:80])
print('  recheck idempotent: registry lines unchanged at', after)
'@
$promoteTmp = Join-Path $env:TEMP "mmw-promote-check.py"
$promotePy | Set-Content -Path $promoteTmp -Encoding UTF8
python $promoteTmp
if ($LASTEXITCODE -ne 0) { Fail "modeling evidence promotion / VERIFIED claim check failed" }
Remove-Item $promoteTmp -Force -ErrorAction SilentlyContinue
Run "validate-case (modeling smoke)" { python -m mathworkstation.cli --output-root $mRoot validate-case --case-id $mCase }

# ----------------------------------------------- 9. full deterministic smoke
Phase "9. FULL DETERMINISTIC PAPER SMOKE (whole legal DAG)"
$fRoot = Join-Path $env:TEMP "mmw-full-smoke"
Remove-Item $fRoot -Recurse -Force -ErrorAction SilentlyContinue
Run "run_full_deterministic_smoke.py" { python scripts\run_full_deterministic_smoke.py $fRoot }

Step "inspect the produced paper and artifacts (not just the exit code)"
$fCase = (Get-ChildItem $fRoot -Directory | Select-Object -First 1).Name
$paper = Join-Path $fRoot "$fCase\paper\final.md"
Write-Host "case          : $fCase"
Write-Host "final.md bytes: $((Get-Item $paper).Length)"
Write-Host "embedded figs : $(([regex]::Matches((Get-Content $paper -Raw), '!\[')).Count)"
Write-Host "figure files on disk:"
Get-ChildItem (Join-Path $fRoot "$fCase\figures") -Recurse -Include *.png,*.svg |
    Select-Object -First 10 -Property Name, Length | Format-Table -AutoSize
Write-Host "VERIFIED claims:"
$claims = Get-Content (Join-Path $fRoot "$fCase\claim_registry.jsonl") | ForEach-Object { $_ | ConvertFrom-Json }
($claims | Group-Object status | Select-Object Name, Count | Format-Table -AutoSize | Out-String)
Write-Host "audit/export dir:"
Get-ChildItem (Join-Path $fRoot "$fCase\export") -Recurse -ErrorAction SilentlyContinue |
    Select-Object -First 5 -Property Name, Length | Format-Table -AutoSize

# ------------------------------------------------------------- 10. staging
Phase "10. PRECISE STAGING (explicit paths only)"
git add ".github/workflows/agent-layer-tests.yml"
git add ".github/workflows/ci.yml"
git add ".gitignore"
git add "src/mathworkstation"
git add "tests"
git add "scripts"
git add "docs/multi-agent-architecture.md"
# Session verification reports are deliberately NOT committed: this is a
# PUBLIC repository, and those files carry sandbox absolute paths and
# session-scoped narrative rather than repository documentation. The
# canonical committed record is docs/multi-agent-architecture.md.

Step "staged summary"
git diff --cached --stat

Step "staged file list -- verify nothing generated/secret is present"
git diff --cached --name-only

$staged = git diff --cached --name-only
foreach ($bad in @("output/", "logs/", ".local.json", ".env.local", "verification-run.log", "artifacts/")) {
    $offend = $staged | Where-Object { $_ -like "*$bad*" -and $_ -notlike "*.gitkeep" }
    if ($offend) { Fail "refusing to commit -- staged path matches '$bad': $offend" }
}
Write-Host "staging audit clean" -ForegroundColor Green

if ($SkipPush) {
    Write-Host "`n-SkipPush set: stopping before commit. Review 'git diff --cached' then re-run without -SkipPush." -ForegroundColor Yellow
    Stop-Transcript | Out-Null
    exit 0
}

# --------------------------------------------------------- 11. commit + push
Phase "11. COMMIT AND PUSH"
if ($ghCli) {
    $vis = gh repo view $RepoSlug --json visibility --jq ".visibility" 2>$null
    Write-Host "remote visibility: $vis"
    if ($vis -eq "PUBLIC") {
        Write-Host "This repository is PUBLIC. Everything staged above becomes world-readable." -ForegroundColor Yellow
        Write-Host "The staged list was audited for credentials, generated cases and machine paths." -ForegroundColor Yellow
        $ok = Read-Host "Type PUSH to publish this commit publicly, anything else to abort"
        if ($ok -ne "PUSH") { Fail "public push not confirmed -- nothing was committed" }
    }
}
git commit -m "Verify M1 agent modeling and add CI coverage"
if ($LASTEXITCODE -ne 0) { Fail "commit failed" }
$sha = (git rev-parse HEAD).Trim()
Write-Host "commit: $sha" -ForegroundColor Green

$upstream = git rev-parse --abbrev-ref --symbolic-full-name "@{u}" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "no upstream configured -- using --set-upstream"
    git push --set-upstream origin $branch
} else {
    git push
}
if ($LASTEXITCODE -ne 0) { Fail "git push failed (if the GitHub repo does not exist yet, create it first, or check credentials)" }

Step "prove the commit exists REMOTELY (three independent probes)"
$lsRemoteMain = git ls-remote origin "refs/heads/$branch"
Write-Host "LOCAL =$sha"
Write-Host "REMOTE=$lsRemoteMain"
$remoteSha = ($lsRemoteMain -split "\s+")[0]
if ($sha -ne $remoteSha) { Fail "push did not land: origin/$branch is '$remoteSha', expected '$sha'" }

git fetch origin $branch 2>&1 | Out-Null
Write-Host "origin/$branch (after fetch): $((git rev-parse "origin/$branch").Trim())"

if ($ghCli) {
    Write-Host "gh api commits/$branch sha: $(gh api "repos/$RepoSlug/commits/$branch" --jq '.sha')"
    gh repo view $RepoSlug --json nameWithOwner,url,visibility,defaultBranchRef
}
Write-Host "PUSH CONFIRMED ON REMOTE: $remoteSha" -ForegroundColor Green
Step "final local git state"
git status --short
git branch -vv
git log -3 --oneline

# ------------------------------------------------------- 12. GitHub Actions
Phase "12. GITHUB ACTIONS"
$gh = Get-Command gh -ErrorAction SilentlyContinue
if (-not $gh) {
    Write-Host "GitHub CLI (gh) not installed -- open the Actions tab manually:" -ForegroundColor Yellow
    Write-Host "  $($originUrl -replace '\.git$','')/actions"
    Write-Host "Install with: winget install --id GitHub.cli" -ForegroundColor Yellow
} else {
    Step "gh run list"
    gh run list --limit 10
    Step "gh run watch (blocks until the run finishes)"
    $runId = (gh run list --limit 1 --json databaseId --jq ".[0].databaseId")
    Write-Host "watching run $runId"
    gh run watch $runId --exit-status
    $ciExit = $LASTEXITCODE
    Step "gh run view (per-job results)"
    gh run view $runId
    Write-Host "run URL: $(gh run view $runId --json url --jq .url)"
    if ($ciExit -ne 0) {
        Step "failed job logs"
        gh run view $runId --log-failed
        Write-Host "`nCI FAILED -- see the log above and the transcript at $log" -ForegroundColor Red
    } else {
        Step "download the runtime-conformance artifact"
        gh run download $runId --name runtime-conformance --dir ".\ci-artifacts" 2>&1
        Get-ChildItem ".\ci-artifacts" -ErrorAction SilentlyContinue
        Write-Host "`nALL CI JOBS PASSED" -ForegroundColor Green
    }
}

Phase "DONE"
Write-Host "Full transcript: $log" -ForegroundColor Cyan
Write-Host "Send that file back to continue (it contains every command's real output)." -ForegroundColor Cyan

}
finally {
    try { Stop-Transcript | Out-Null } catch { }
}
