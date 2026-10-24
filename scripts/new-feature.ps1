# new-feature.ps1 — 功能分支工作流（建分支 / 合并打 tag / 放弃）
#
# 用法（在仓库任意子目录均可）：
#   .\scripts\new-feature.ps1 start  <功能名>        # 从 main 建 feature 分支并切换
#   .\scripts\new-feature.ps1 finish [-Tag v0.2] [-Keep]   # 合并回 main，可选打 tag、保留分支
#   .\scripts\new-feature.ps1 discard               # 放弃当前功能，强制删除分支
#   .\scripts\new-feature.ps1 status                # 查看当前分支与改动

[CmdletBinding()]
param(
    [Parameter(Position = 0)][ValidateSet('start', 'finish', 'discard', 'status')][string]$Action,
    [Parameter(Position = 1)][string]$Name,
    [string]$Tag,
    [switch]$Keep
)

function Stop-Message([string]$msg) {
    Write-Host "[错误] $msg" -ForegroundColor Red
    exit 1
}

if (-not $Action) {
    Write-Host "用法: new-feature start <功能名> | finish [-Tag v0.2] [-Keep] | discard | status"
    exit 1
}

# 确认在 git 仓库内，并切到仓库根
git rev-parse --is-inside-work-tree *> $null
if ($LASTEXITCODE -ne 0) { Stop-Message "当前目录不是 git 仓库" }
$root = git rev-parse --show-toplevel
Set-Location $root

switch ($Action) {

    'start' {
        if (-not $Name) { Stop-Message "用法: new-feature start <功能名>" }
        $all = git status --porcelain
        $tracked = $all | Where-Object { $_ -notlike '??*' }
        if ($tracked) { Stop-Message "有已跟踪文件未提交，请先提交或 git stash" }
        if ($all) { Write-Host "提示: 存在未跟踪文件，将原样保留在工作区（不影响建分支）" -ForegroundColor DarkGray }
        git checkout main *> $null
        if ($LASTEXITCODE -ne 0) { Stop-Message "无法切换到 main（是否存在 main 分支？）" }
        $branch = 'feature/' + ($Name -replace '[\s/\\]+', '-')
        git checkout -b $branch *> $null
        if ($LASTEXITCODE -ne 0) { Stop-Message "创建分支失败：$branch（可能已存在）" }
        Write-Host "[OK] 已在分支 $branch 上开发" -ForegroundColor Green
        Write-Host "     完成后运行: .\scripts\new-feature.ps1 finish -Tag v0.2" -ForegroundColor DarkGray
    }

    'finish' {
        $branch = (git rev-parse --abbrev-ref HEAD)
        if ($branch -notlike 'feature/*') { Stop-Message "当前不在 feature 分支（当前: $branch）" }
        $dirty = git status --porcelain | Where-Object { $_ -notlike '??*' }
        if ($dirty) { Stop-Message "分支有未提交修改，请先提交，或用 discard 放弃" }
        git checkout main *> $null
        if ($LASTEXITCODE -ne 0) { Stop-Message "无法切换到 main" }
        git merge --no-ff $branch -m "merge: $branch"
        if ($LASTEXITCODE -ne 0) { Stop-Message "合并出现冲突，请解决后再提交，或 git merge --abort" }
        if ($Tag) {
            git tag -a $Tag -m "release $Tag"
            if ($LASTEXITCODE -ne 0) { Stop-Message "合并成功，但打 tag 失败：$Tag" }
            Write-Host "[OK] 已打标签 $Tag" -ForegroundColor Green
        }
        if ($Keep) {
            Write-Host "[OK] 已合并到 main，保留分支 $branch" -ForegroundColor Green
        }
        else {
            git branch -d $branch *> $null
            Write-Host "[OK] 已合并到 main，并删除分支 $branch" -ForegroundColor Green
        }
    }

    'discard' {
        $branch = (git rev-parse --abbrev-ref HEAD)
        if ($branch -notlike 'feature/*') { Stop-Message "当前不在 feature 分支（当前: $branch）" }
        git checkout main *> $null
        if ($LASTEXITCODE -ne 0) { Stop-Message "无法切换回 main" }
        git branch -D $branch
        Write-Host "[OK] 已放弃并删除分支 $branch" -ForegroundColor Yellow
    }

    'status' {
        Write-Host "当前分支:" -ForegroundColor Cyan
        git branch
        Write-Host "`n改动:" -ForegroundColor Cyan
        $s = git status -s
        if ($s) { $s } else { Write-Host "（工作区干净）" -ForegroundColor DarkGray }
    }
}
