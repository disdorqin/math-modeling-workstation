#!/usr/bin/env pwsh
# ============================================================
# freebuff_task_poller.ps1 — 后台任务/邮箱自动轮询器 v3（健壮版，自动执行版）
# ------------------------------------------------------------
# 在 freebuff 会话期间后台运行，定期轮询 fleet/tasks + fleet/mailbox，
# 发现派给自己(freebuff)的新任务时【自动执行】：
#   1. 自动 task_claim（领取 → doing）
#   2. 调用 chat_inject.py 把任务说明注入 freebuff 聊天会话，触发执行
#   3. 检测到任务完成(doing→done)后，自动上报导师（claude_code 邮箱 + 广播）
#
# v3 健壮性改造：
#   - 兼容 Windows PowerShell 5.1 与 PowerShell 7：不再依赖 -AsHashtable，
#     用统一的 ConvertTo-Hashtable 助手解析 JSON（修掉 "property cannot be
#     found" / "claimed_at 无法设置" 的时断时错）。
#   - 任务状态迁移改为原子写：先写目标文件（tmp + rename），成功后再删源，
#     杜绝 "Move-Item 成功但 Set-Content 失败 → 任务丢失/状态错乱"。
#   - 状态文件读写全部容错；inbox_count 等字段用索引赋值，PS5.1/7 通吃。
#   - 依赖 chat_inject v3 的 delivered 校验：只有真的发进聊天框才算注入成功。
#
# 用法(通常在接入桥中作为后台 job 启动)：
#   Start-Job -FilePath D:\Program\freebuff\freebuff_task_poller.ps1
# 单次运行（测试用）：
#   pwsh -File D:\Program\freebuff\freebuff_task_poller.ps1 -Once
#
# 依赖: HTTP 服务 http://127.0.0.1:9870 (ai_memory_hub, 可选) + 文件回退
# 轮询间隔: 120 秒(可通过 $env:POLL_SEC 覆盖)
# ============================================================
param(
    [switch]$Once          # 只跑一轮(测试用)
)

$ErrorActionPreference = "Continue"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

$HUB        = "http://127.0.0.1:9870"
$AGENT      = "freebuff"
$BRIEF      = "D:\Program\freebuff\freebuff_session_brief.md"
$MAILBOX    = "D:\AI_Memory\fleet\mailbox\freebuff.jsonl"
$TASK_DIR   = "D:\AI_Memory\fleet\tasks"
$STATE_FILE = "D:\AI_Memory\shared_memory\poller_state.json"
$LOG_FILE   = "D:\AI_Memory\shared_memory\poller.log"
$CHAT_INJECT = "D:\AI_Memory\shared_memory\chat_inject.py"
$PY         = "python"
$POLL_SEC   = if ($env:POLL_SEC) { [int]$env:POLL_SEC } else { 120 }

# ── 解析 Python(与 notify_bridge 一致) ──────────────────────
$v = & py -3.11 -c "import sys;print(sys.executable)" 2>$null
if ($LASTEXITCODE -eq 0 -and $v) { $PY = $v.Trim() }
elseif (-not $PY) {
    $v = & python -c "import sys;print(sys.executable)" 2>$null
    if ($LASTEXITCODE -eq 0 -and $v) { $PY = $v.Trim() }
}

function Write-Log {
    param([string]$Msg, [ConsoleColor]$Color = [ConsoleColor]::DarkGray)
    $ts = Get-Date -Format "HH:mm:ss"
    $line = "[$ts] $Msg"
    Write-Host $line -ForegroundColor $Color
    try { Add-Content -Path $LOG_FILE -Value $line -Encoding UTF8 } catch {}
}

function Send-Hub {
    param([string]$Method, [string]$Path, $Body)
    try {
        if ($Body) {
            $json = $Body | ConvertTo-Json -Compress
            return Invoke-RestMethod -Method $Method -Uri "$HUB$Path" -ContentType "application/json" -Body $json -TimeoutSec 10
        } else {
            return Invoke-RestMethod -Method $Method -Uri "$HUB$Path" -TimeoutSec 10
        }
    } catch {
        return $null
    }
}

# ── 通用 JSON → Hashtable 助手(PS 5.1 + PS7 通吃) ──────────────
function ConvertTo-Hashtable {
    param($Obj)
    if ($null -eq $Obj) { return @{} }
    if ($Obj -is [System.Collections.IDictionary]) { return $Obj }
    $ht = @{}
    foreach ($p in $Obj.PSObject.Properties) { $ht[$p.Name] = $p.Value }
    return $ht
}

function Read-JsonFile {
    param([string]$Path)
    try {
        $raw = Get-Content $Path -Raw -Encoding UTF8
        if ([string]::IsNullOrWhiteSpace($raw)) { return $null }
        $parsed = $raw | ConvertFrom-Json
        return (ConvertTo-Hashtable $parsed)
    } catch {
        return $null
    }
}

# 原子写 JSON（先写 tmp 再 rename，绝不写坏目标文件）
# 注意：必须用无 BOM 的 UTF-8（WriteAllText + UTF8Encoding($false)）。
# Windows PowerShell 5.1 的 Set-Content -Encoding UTF8 会写 BOM，
# 导致 hub 的 json.load(encoding="utf-8") 直接 JSONDecodeError（任务单变不可读）。
function Write-JsonAtomic {
    param([string]$Path, $Data)
    $tmp = "$Path.tmp"
    $json = $Data | ConvertTo-Json -Depth 8
    [System.IO.File]::WriteAllText($tmp, $json, (New-Object System.Text.UTF8Encoding($false)))
    Move-Item -Path $tmp -Destination $Path -Force
}

# ── 状态读写(记住已处理任务,避免重复 claim/注入/上报) ──────
function Get-State {
    $s = Read-JsonFile $STATE_FILE
    if ($null -eq $s) { $s = @{} }
    if (-not $s.ContainsKey("claimed")) { $s["claimed"] = @() }
    if (-not $s.ContainsKey("injected")) { $s["injected"] = @() }
    if (-not $s.ContainsKey("reported")) { $s["reported"] = @() }
    if (-not $s.ContainsKey("inbox_count")) { $s["inbox_count"] = 0 }
    return $s
}

function Save-State {
    param($S)
    try { Write-JsonAtomic -Path $STATE_FILE -Data $S } catch {}
}

# ── 文件回退 task_claim(pending → doing)，原子迁移 ──────────
function Claim-TaskFile {
    param([string]$TaskId)
    $src = Join-Path "$TASK_DIR\pending" "$TaskId.json"
    if (-not (Test-Path $src)) { return $null }
    try {
        $raw = Read-JsonFile $src
        if ($null -eq $raw) { return $null }
        if ($raw["assigned_to"] -ne $AGENT) { return $null }   # 不越权
        $raw["status"] = "doing"
        $raw["claimed_at"] = (Get-Date).ToString("o")
        $dst = Join-Path "$TASK_DIR\doing" "$TaskId.json"
        # 原子迁移：先写目标文件（成功），再删源（失败也无损）
        Write-JsonAtomic -Path $dst -Data $raw
        Remove-Item -Path $src -Force -ErrorAction SilentlyContinue
        return $raw
    } catch {
        Write-Log "claim 失败 $TaskId : $_" -Color Yellow
        return $null
    }
}

# ── 文件回退 task_submit(doing → done)，原子迁移 ──────────────
# 说明: 正常流程是 freebuff 会话(本 agent)执行完任务后调用 hub /task/submit;
# 此函数仅在 hub 不可用时为会话提供文件级回退(由 agent 在会话内按需调用)。
function Submit-TaskFile {
    param([string]$TaskId, [string]$Result)
    $src = Join-Path "$TASK_DIR\doing" "$TaskId.json"
    if (-not (Test-Path $src)) { return $null }
    try {
        $raw = Read-JsonFile $src
        if ($null -eq $raw) { return $null }
        $raw["status"] = "done"
        $raw["completed_at"] = (Get-Date).ToString("o")
        $raw["result"] = $Result
        $dst = Join-Path "$TASK_DIR\done" "$TaskId.json"
        Write-JsonAtomic -Path $dst -Data $raw
        Remove-Item -Path $src -Force -ErrorAction SilentlyContinue
        return $raw
    } catch {
        Write-Log "submit 失败 $TaskId : $_" -Color Yellow
        return $null
    }
}

# ── 注入 freebuff 聊天会话(CDP,失败回退剪贴板) ─────────────
function Inject-ToFreebuff {
    param([string]$Text)
    try {
        # PowerShell 直接把 $Text 作为单个参数传给 python, 无需/不应转义引号
        $out = & $PY $CHAT_INJECT --clipboard-fallback $Text 2>&1
        $code = $LASTEXITCODE
        $msg = ($out | Out-String).Trim()
        return [PSCustomObject]@{ exit = $code; output = $msg }
    } catch {
        return [PSCustomObject]@{ exit = -1; output = "注入异常: $_" }
    }
}

# ── 上报导师(claude_code 邮箱 + 广播) ───────────────────────
function Notify-Mentor {
    param([string]$TaskId, [string]$Subject, [string]$Body)
    $ts = (Get-Date).ToUniversalTime().ToString("o")
    $midSource = "$AGENT|claude_code|$Subject|$Body|$ts"
    $md5 = [System.Security.Cryptography.MD5]::Create()
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($midSource)
    $mid = -join ($md5.ComputeHash($bytes) | ForEach-Object { $_.ToString("x2") })
    $entry = [ordered]@{
        timestamp = $ts
        from      = $AGENT
        to        = "claude_code"
        subject   = $Subject
        body      = $Body
        targets   = @("claude_code")
        msg_id    = $mid.Substring(0, 16)
        type      = "mail"
    }
    $json = ($entry | ConvertTo-Json -Compress) + "`n"
    try {
        # 无 BOM 追加（PS5.1 的 Add-Content -Encoding UTF8 会写 BOM，破坏 JSONL）
        $enc = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::AppendAllText("D:\AI_Memory\fleet\mailbox\claude_code.jsonl", $json, $enc)
        [System.IO.File]::AppendAllText("D:\AI_Memory\fleet\notify\broadcast.jsonl", $json, $enc)
        return $true
    } catch {
        Write-Log "上报导师失败: $_" -Color Yellow
        return $false
    }
}

Write-Log "=== Freebuff 任务轮询器 v3(健壮版)启动, 间隔 ${POLL_SEC}s ===" -Color Cyan

# ── 首次读 session_brief ─────────────────────────────────────
if (Test-Path $BRIEF) {
    Write-Log "已读取 $BRIEF(开场仪式指引)" -Color Green
} else {
    Write-Log "WARN: $BRIEF 不存在,按默认规则轮询" -Color Yellow
}

do {
    $S = Get-State
    try {
        # ── 1. 轮询待领任务(HTTP + 文件系统双重检测) ─────────
        $newTasks = @()
        $taskRaw = Send-Hub -Method GET -Path "/task/list?state=pending&agent=$AGENT"
        if ($taskRaw) {
            try {
                $tasks = $taskRaw.tasks
                if ($tasks) { foreach ($t in $tasks) { $newTasks += $t } }
            } catch { }
        }
        if ($newTasks.Count -eq 0 -and (Test-Path "$TASK_DIR\pending")) {
            try {
                Get-ChildItem "$TASK_DIR\pending" -Filter "*.json" | ForEach-Object {
                    $t = Read-JsonFile $_.FullName
                    if ($null -ne $t) { $newTasks += $t }
                }
            } catch { }
        }

        foreach ($t in $newTasks) {
            $id = $t["task_id"]
            if (-not $id) { continue }
            if ($S["claimed"] -contains $id) { continue }   # 已处理过
            if ($t["assigned_to"] -ne $AGENT) { continue }  # 只处理派给自己的

            Write-Host ""
            Write-Host "╔══════════════════════════════════════════════════╗" -ForegroundColor Magenta
            Write-Host "║  🚀 新任务: $id  $($t["title"])" -ForegroundColor Magenta
            Write-Host "╚══════════════════════════════════════════════════╝" -ForegroundColor Magenta
            Write-Log "派发人: $($t["assigned_by"]) | 验收: $($t["acceptance_criteria"])" -Color Gray

            # 1) 自动领取
            $claimed = $null
            if ($taskRaw) {
                try {
                    $claimed = Send-Hub -Method POST -Path "/task/claim" -Body @{ agent = $AGENT; task_id = $id }
                } catch { $claimed = $null }
            }
            if (-not $claimed) { $claimed = Claim-TaskFile $id }
            if ($claimed) {
                $S["claimed"] += $id
                Save-State $S
                Write-Log "✅ 已自动领取: $id → doing" -Color Green

                # 2) 注入 freebuff 会话触发执行
                $injectText = "【舰队任务自动派发】请执行任务 $id ：$($t["title"])。任务单见 fleet\tasks\doing\$id.json ，按验收标准完成，完成后 task_submit 并自动上报导师。"
                $inj = Inject-ToFreebuff $injectText
                if ($inj.exit -eq 0) {
                    Write-Log "💬 已注入 freebuff 会话: $($inj.output)" -Color Green
                } elseif ($inj.exit -eq 2) {
                    Write-Log "⚠️ CDP 注入失败，已复制到剪贴板（需手动粘贴）: $($inj.output)" -Color Yellow
                    Write-Log "任务说明已就绪: fleet\tasks\doing\$id.json" -Color Yellow
                } else {
                    Write-Log "⚠️ 注入未成功(CDP 不可用?): $($inj.output)" -Color Yellow
                    Write-Log "任务说明已就绪: fleet\tasks\doing\$id.json" -Color Yellow
                }
            } else {
                Write-Log "⚠️ 领取失败 $id (可能已被他人领取或非本 agent 任务)" -Color Yellow
            }
        }

        # ── 2. 检测已领取任务的完成(doing → done)并自动上报 ──
        # 铁律: 只上报【本轮询器自己领取过】(claimed 里)的任务, 绝不误报历史任务/他人任务
        if (Test-Path "$TASK_DIR\done") {
            Get-ChildItem "$TASK_DIR\done" -Filter "*.json" | ForEach-Object {
                try {
                    $t = Read-JsonFile $_.FullName
                    if ($null -eq $t) { return }
                    $id = $t["task_id"]
                    if (-not $id) { return }
                    if ($t["assigned_to"] -ne $AGENT) { return }
                    if ($S["reported"] -contains $id) { return }
                    if ($S["claimed"] -contains $id) {   # 只有我们 claim 过的才上报
                        $S["reported"] += $id
                        Save-State $S
                        $subject = "✅ [$id] 任务完成 - freebuff(自动上报)"
                        $body = "任务 $id ($($t["title"])) 已完成。结果: $($t["result"])"
                        $ok = Notify-Mentor $id $subject $body
                        if ($ok) { Write-Log "📨 已自动上报导师: $id" -Color Green }
                    }
                } catch { }
            }
        }

        # ── 3. 轮询收件箱, 打印新增消息(提示; 消息本身由 inbox_bridge 投递) ──
        $lastInboxCount = [int]$S["inbox_count"]
        $currentCount = 0
        $newMessages = @()
        $inboxRaw = Send-Hub -Method GET -Path "/agent/inbox?agent=$AGENT&mark_read=1"
        if ($inboxRaw) {
            try {
                $currentCount = [int]$inboxRaw.count
                if ($inboxRaw.messages) { $newMessages = $inboxRaw.messages }
            } catch { $currentCount = 0 }
        } else {
            if (Test-Path $MAILBOX) {
                try { $currentCount = (Get-Content $MAILBOX -Encoding UTF8 -ErrorAction SilentlyContinue).Count } catch { $currentCount = 0 }
            }
        }
        if ($currentCount -gt $lastInboxCount -and $newMessages.Count -gt 0) {
            Write-Host ""
            Write-Host "┌─ 新消息 ───────────────────────────────┐" -ForegroundColor DarkCyan
            $newMessages | Select-Object -Last ($currentCount - $lastInboxCount) | ForEach-Object {
                Write-Host "  from[$($_.from)] $($_.subject)" -ForegroundColor DarkCyan
                Write-Host "  $($_.body)" -ForegroundColor Gray
            }
            Write-Host "└────────────────────────────────────────┘" -ForegroundColor DarkCyan
        }
        $S["inbox_count"] = $currentCount
        Save-State $S

    } catch {
        Write-Log "轮询异常(容错继续): $_" -Color Yellow
    }

    if ($Once) { break }
    Start-Sleep -Seconds $POLL_SEC
} while ($true)

Write-Log "轮询器退出" -Color DarkGray
