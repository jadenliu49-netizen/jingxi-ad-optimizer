# jingxi-ad-optimizer

京喜自营全站营销广告调整技能。装好后在 JoyCode 里说“调整广告”，会按保本投产比自动分桶、改目标、拉黑亏损 SKU、暂停计划、出报告。

## 一键安装（Windows PowerShell）

    irm https://raw.githubusercontent.com/jadenliu49-netizen/jingxi-ad-optimizer/v1/install.ps1 | iex

装完重启 JoyCode，新开对话说“调整广告”。

## 前提

- 已安装 JoyCode。
- 已安装 blacklight 技能，本人京准通能登录。

## 目录

- SKILL.md：流程、分桶、安全边界。
- scripts/ad_ops.py：取数、算动作、执行、出报告。
- references/rules.md：口径、拉黑、红线。
- references/new-plan.md：新 SPU 进池与建计划。
