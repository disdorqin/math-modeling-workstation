param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string[]] $Arguments,
    [string] $Image = "mathworkstation:local",
    [string] $EnvFile = ".env.local",
    [string] $ProjectRoot = "$PWD",
    [string] $OutputRoot = "$(Join-Path $PWD "output")"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $EnvFile -PathType Leaf)) {
    throw "Missing env file: $EnvFile"
}

docker image inspect $Image *> $null
if ($LASTEXITCODE -ne 0) {
    docker build --tag $Image .
    if ($LASTEXITCODE -ne 0) { throw "Docker image build failed" }
}

New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null
$hostRoot = (Resolve-Path -LiteralPath $OutputRoot).Path
$hostProject = (Resolve-Path -LiteralPath $ProjectRoot).Path
$containerArgs = @(
    "run", "--rm",
    "--env-file", (Resolve-Path -LiteralPath $EnvFile).Path,
    "-v", "${hostProject}:/workspace",
    "-v", "${hostRoot}:/work",
    $Image
) + $Arguments

& docker @containerArgs
exit $LASTEXITCODE
