$ErrorActionPreference = 'Stop'

$ffmpeg = 'C:\ffmpeg\ffmpeg-7.1-essentials_build\bin\ffmpeg.exe'
$playlist = 'https://lex.infosysapps.com/apis/authContent//content-store/Infosys/Infosys_Ltd/Public/lex_auth_014670690393743360761/assets/media-services-content/1790855816663/TechCohere_Session-20261001_143307-Meeting_Recording_low_vid_640p.m3u8'
$referer = 'https://lex.infosysapps.com/web/en/author/viewer/video/lex_auth_014670690393743360761'
$output = Join-Path $PSScriptRoot 'Lex-video.mp4'

if (-not (Test-Path -LiteralPath $ffmpeg)) {
    throw "FFmpeg was not found at $ffmpeg"
}
if (Test-Path -LiteralPath $output) {
    throw "Output already exists: $output"
}

$cookie = (Get-Clipboard -Raw).Trim()
if (-not $cookie -or $cookie -match '[\r\n]' -or $cookie -notmatch '=') {
    throw 'Copy only the Cookie request-header value from Chrome DevTools, then run this script again.'
}

try {
    & $ffmpeg -nostdin -hide_banner -headers "Cookie: $cookie`r`n" -referer $referer -i $playlist -c copy -n $output
    if ($LASTEXITCODE -ne 0) {
        throw "FFmpeg exited with code $LASTEXITCODE"
    }
    Get-Item -LiteralPath $output | Select-Object FullName, Length
}
finally {
    $cookie = $null
}
