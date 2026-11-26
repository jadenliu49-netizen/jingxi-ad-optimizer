# 京喜广告调整技能 一键安装
$ErrorActionPreference = 'Stop'
$BaseUrl = 'https://raw.githubusercontent.com/USER/REPO/main'
$dst = Join-Path $env:USERPROFILE '.joycode\skills\jingxi-ad-optimizer'
New-Item -ItemType Directory -Force -Path $dst, (Join-Path $dst 'scripts'), (Join-Path $dst 'references'), (Join-Path $dst 'agents') | Out-Null
$files = @(
  'SKILL.md',
  'scripts/ad_ops.py',
  'references/rules.md',
  'references/new-plan.md',
  'agents/openai.yaml'
)
foreach ($f in $files) {
  $url = $BaseUrl + '/' + $f
  $target = Join-Path $dst ($f -replace '/', '\')
  New-Item -ItemType Directory -Force -Path (Split-Path $target) | Out-Null
  Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $target
  Write-Host ('  ok ' + $f)
}
Write-Host ''
Write-Host '已安装到:' $dst -ForegroundColor Green
Write-Host '下一步：重启 JoyCode（或新开一个对话），说“调整广告”。' -ForegroundColor Green
