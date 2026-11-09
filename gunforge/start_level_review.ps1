param([string]$Build, [ValidateSet('paper.alley','paper.assault','gallery.intro','orbital.convoy','orbital.siege')][string]$Package='paper.alley', [string]$Godot = $env:GODOT_BIN,[switch]$Candidate,[string]$Proposal)
$ErrorActionPreference = 'Stop'
$levelRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not $Godot) { $Godot = Join-Path $levelRoot '../gunforge_cache/tools/godot-4.6.3/Godot_v4.6.3-stable_win64_console.exe' }
$levelPython = Join-Path $levelRoot '.venv/Scripts/python.exe'
$comparisonArgs = @()
if ($Proposal) {
    if ($Build) { throw 'Specify either -Proposal or -Build' }
    $comparison = & $levelPython (Join-Path $PSScriptRoot 'pipeline/level_design/review_revision.py') preview (Resolve-Path -LiteralPath $Proposal).Path
    if ($LASTEXITCODE) { throw 'Proposal preview could not be built' }
    $comparison = $comparison | ConvertFrom-Json
    $Build = $comparison.candidate
    $Package = $comparison.package
    $comparisonArgs = @("--compare=$($comparison.base)", "--at-tick=$($comparison.tick)")
}
if (-not $Build) {
    if ($Package -in @('paper.alley','paper.assault')) {
        & $levelPython (Join-Path $PSScriptRoot 'pipeline/build_0b.py')
        if ($LASTEXITCODE) { throw 'Native asset preparation failed' }
    }
    $levelScripts=@{'paper.alley'='paper';'paper.assault'='assault';'gallery.intro'='gallery';'orbital.convoy'='protection';'orbital.siege'='siege'}
    $levelName=$levelScripts[$Package]
    & $levelPython (Join-Path $PSScriptRoot "pipeline/level_design/build_$levelName.py")
    if ($LASTEXITCODE) { throw 'Level compilation failed' }
    $levelIndex = Get-Content -Raw -Encoding UTF8 (Join-Path $PSScriptRoot "level_design/reviews/${levelName}_build.json") | ConvertFrom-Json
    $Build = $levelIndex.compiled
    if (-not $Candidate) {
        $levelSelected=& $levelPython (Join-Path $PSScriptRoot 'pipeline/level_design/resolve_launch.py') $Package
        if ($LASTEXITCODE) { throw 'Adopted level resolution failed' }
        if ($levelSelected) { $Build=$levelSelected }
    }
}
$levelReviews = Join-Path $PSScriptRoot 'level_design/reviews/comments'
if ($Package -in @('paper.alley','paper.assault')) {
    & $Godot --headless --editor --import --quit --path (Join-Path $PSScriptRoot 'framework')
    if ($LASTEXITCODE) { throw 'Godot resource import failed' }
}
$levelCache=$env:GUNFORGE_LEVEL_CACHE
if (-not $levelCache) { $levelCache=Join-Path $levelRoot '../gunforge_cache/level_design' }
& $Godot --path (Join-Path $PSScriptRoot 'framework') --script res://tools/level_review.gd -- "--build=$Build" "--assets=$levelRoot" "--reviews=$levelReviews" "--evidence=$(Join-Path $levelCache 'review-evidence')" @comparisonArgs
