param(
    [Parameter(Mandatory)]
    [ValidatePattern('^[a-z][a-z0-9_]+$')]
    [string] $Id,
    [string[]] $Clips = @()
)

$ErrorActionPreference = 'Stop'
Push-Location (Join-Path $PSScriptRoot '../../..')
try {
    uv -q run --python 3.12 --with Pillow==12.2.0 python pipeline/split/prepare.py $Id
    if ($LASTEXITCODE) { throw 'Part preparation failed.' }
    node pipeline/export/build.mjs $Id @Clips
    if ($LASTEXITCODE) { throw 'Rig or clip export failed.' }
    node tools/qa/check.mjs $Id
    $qaCode = $LASTEXITCODE
    node tools/qa/render.mjs $Id
    if ($LASTEXITCODE) { throw 'Preview rendering failed.' }
    if ($qaCode) { throw 'Animation QA failed. See assets/<id>/qa.' }
} finally {
    Pop-Location
}
