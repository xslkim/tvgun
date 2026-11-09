param([ValidateSet('paper.alley','paper.assault','paper.station','paper.stall','gallery.intro','orbital.convoy','orbital.siege')][string]$Package='paper.alley',[string]$Build,[string]$Godot=$env:GODOT_BIN,[double]$QuitAfter=0,[switch]$Candidate,[string]$Proposal)
$ErrorActionPreference='Stop'
$levelRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$levelPython=Join-Path $levelRoot '.venv/Scripts/python.exe'
if (-not $Godot) { $Godot=Join-Path $levelRoot '../gunforge_cache/tools/godot-4.6.3/Godot_v4.6.3-stable_win64_console.exe' }
if ($Proposal) {
    if ($Build -or $Candidate) { throw '-Proposal selects an exact candidate. Omit -Build and -Candidate.' }
    $proposalPath = (Resolve-Path -LiteralPath $Proposal).Path
    $revisionTool = Join-Path $PSScriptRoot 'pipeline/level_design/review_revision.py'
    $Package = & $levelPython $revisionTool package $proposalPath
    if ($LASTEXITCODE) { throw 'Cannot identify the proposal package' }
}
if (-not $Build -and $Package -in @('paper.alley','paper.assault','paper.station','paper.stall')) {
    & $levelPython (Join-Path $PSScriptRoot 'pipeline/build_0b.py')
    if ($LASTEXITCODE) { throw 'Native asset preparation failed' }
}
if ($Proposal) {
    $comparison = & $levelPython $revisionTool preview $proposalPath
    if ($LASTEXITCODE) { throw 'Proposal could not be built' }
    $Build = ($comparison | ConvertFrom-Json).candidate
} elseif (-not $Build) {
    $levelNames=@{'paper.alley'='paper';'paper.assault'='assault';'paper.station'='station';'paper.stall'='stall';'gallery.intro'='gallery';'orbital.convoy'='protection';'orbital.siege'='siege'}
    $levelName=$levelNames[$Package]
    & $levelPython (Join-Path $PSScriptRoot "pipeline/level_design/build_$levelName.py")
    if ($LASTEXITCODE) { throw 'Level compilation failed' }
    $Build=(Get-Content -Raw -Encoding UTF8 (Join-Path $PSScriptRoot "level_design/reviews/${levelName}_build.json") | ConvertFrom-Json).compiled
    if (-not $Candidate) {
        $levelSelected=& $levelPython (Join-Path $PSScriptRoot 'pipeline/level_design/resolve_launch.py') $Package
        if ($LASTEXITCODE) { throw 'Adopted level resolution failed' }
        if ($levelSelected) { $Build=$levelSelected }
    }
}
if ($Package -in @('paper.alley','paper.assault','paper.station','paper.stall')) {
    & $Godot --headless --editor --import --quit --path (Join-Path $PSScriptRoot 'framework')
    if ($LASTEXITCODE) { throw 'Godot resource import failed' }
}
& $Godot --path (Join-Path $PSScriptRoot 'framework') --script res://tools/level_player.gd -- "--build=$Build" "--assets=$levelRoot" "--quit-after=$QuitAfter"
exit $LASTEXITCODE
