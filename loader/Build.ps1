param([string]$GameRoot = (Join-Path $PSScriptRoot '../..'), [switch]$Test)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$GameRoot = (Resolve-Path $GameRoot).Path
$dotnet = Join-Path $env:ProgramFiles 'dotnet/dotnet.exe'
$sdk = (& $dotnet --list-sdks | Select-Object -Last 1).Split(' ')[0]
$compiler = Join-Path $env:ProgramFiles "dotnet/sdk/$sdk/Roslyn/bincore/csc.dll"
$framework = Join-Path ${env:ProgramFiles(x86)} 'Reference Assemblies/Microsoft/Framework/.NETFramework/v4.7.2'
$output = Join-Path $root 'runtime'
New-Item -ItemType Directory -Force $output | Out-Null
$refs = @('mscorlib.dll','System.dll','System.Core.dll','System.Web.Extensions.dll') | ForEach-Object { Join-Path $framework $_ }
$gameRefs = @('UnhollowerBaseLib.dll','Il2Cppmscorlib.dll','UnityEngine.CoreModule.dll','UnityEngine.UI.dll','Unity.TextMeshPro.dll','UnityEngine.TextRenderingModule.dll') | ForEach-Object { Join-Path $GameRoot "MelonLoader/Managed/$_" }
$gameRefs += Join-Path $GameRoot 'MelonLoader/MelonLoader.dll'
$gameRefs += Join-Path $GameRoot 'MelonLoader/0Harmony.dll'
function Compile($name, $sources, $references, $target) {
    $arguments = @('/nologo','/nostdlib+','/langversion:latest','/optimize+','/deterministic+',"/target:$target",('/out:"' + $output + '/' + $name + '"'))
    $arguments += $references | ForEach-Object { '/reference:"' + $_ + '"' }
    $arguments += $sources | ForEach-Object { '"' + $_ + '"' }
    $response = Join-Path $output "$name.rsp"
    [IO.File]::WriteAllLines($response, $arguments)
    & $dotnet $compiler /noconfig "@$response"
    if ($LASTEXITCODE -ne 0) { throw "Compilation failed: $name" }
}
Compile 'GuiguModTranslation.dll' @((Join-Path $PSScriptRoot 'TranslationCatalog.cs'),(Join-Path $PSScriptRoot 'TranslationMod.cs')) ($refs + $gameRefs) 'library'
$hash = (Get-FileHash (Join-Path $output 'GuiguModTranslation.dll') -Algorithm SHA256).Hash.ToLowerInvariant()
[IO.File]::WriteAllText((Join-Path $output 'manifest.json'), (@{version='1.0.0';sha256=$hash;melonloader='0.5.x'} | ConvertTo-Json))
if ($Test) {
    Compile 'CatalogTests.exe' @((Join-Path $PSScriptRoot 'TranslationCatalog.cs'),(Join-Path $root 'tests/CatalogTests.cs')) $refs 'exe'
    & (Join-Path $output 'CatalogTests.exe')
    if ($LASTEXITCODE -ne 0) { throw 'Catalog tests failed.' }
    Compile 'GuiguTranslationProbe.dll' @((Join-Path $root 'tests/RuntimeProbe.cs')) ($refs + $gameRefs + @((Join-Path $GameRoot 'MelonLoader/Managed/UnityEngine.UIModule.dll'))) 'library'
}
Write-Output "Built $output/GuiguModTranslation.dll"
