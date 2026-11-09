param([ValidateSet('paper.alley','paper.assault','paper.station','gallery.intro','orbital.convoy','orbital.siege')][string]$Package='paper.alley',[string]$Build,[string]$Godot=$env:GODOT_BIN,[double]$QuitAfter=0,[switch]$Candidate)
$ErrorActionPreference='Stop'
$levelRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$levelPython=Join-Path $levelRoot '.venv/Scripts/python.exe'
if (-not $Godot) { $Godot=Join-Path $levelRoot '../gunforge_cache/tools/godot-4.6.3/Godot_v4.6.3-stable_win64_console.exe' }
if (-not $Build) {
    if ($Package -in @('paper.alley','paper.assault','paper.station')) {
        & $levelPython (Join-Path $PSScriptRoot 'pipeline/build_0b.py')
        if ($LASTEXITCODE) { throw 'Native asset preparation failed' }
    }
    $levelNames=@{'paper.alley'='paper';'paper.assault'='assault';'paper.station'='station';'gallery.intro'='gallery';'orbital.convoy'='protection';'orbital.siege'='siege'}
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
if ($Package -in @('paper.alley','paper.assault','paper.station')) {
    & $Godot --headless --editor --import --quit --path (Join-Path $PSScriptRoot 'framework')
    if ($LASTEXITCODE) { throw 'Godot resource import failed' }
}
& $Godot --path (Join-Path $PSScriptRoot 'framework') --script res://tools/level_player.gd -- "--build=$Build" "--assets=$levelRoot" "--quit-after=$QuitAfter"
