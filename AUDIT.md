# Installed-mod extraction audit

Validated on 13 September 2026 against this Steam installation.

| Mod ID | Mod | Unique Chinese entries | Reused English |
|---|---|---:|---:|
| 2814696167 | [无邪]万古神话 | 11,535 | 14 |
| 2814703549 | 【Sorry】Fatury框架 | 13 | 0 |
| 2815004979 | 【软甜废娇媚配音剧情】动态立绘 | 1,644 | 410 |
| 2859071194 | 八荒绝色榜 | 2,052 | 909 |
| 2929042685 | 【Addk1k】三神器全开 | 42 | 0 |
| 2940915818 | [龙猫]☺洪荒世界观 | 6,131 | 0 |
| 2971618983 | 【执余】流派框架 | 67 | 0 |
| 2973271941 | [龙猫]道♥商店 | 139 | 0 |
| 2975199708 | [龙猫]货◎商店 | 133 | 0 |
| GGBH_MOD-6e611701 | GGBH_MOD | 5 | 0 |
| ImmortalCoop-521d21d2 | ImmortalCoop | 5 | 0 |

Total: **21,766 entries** (deduplicated within each mod), including **1,333 existing English translations**. The same source occurring in separate mods counts once in each mod.

Field classification: **18,401 player-text entries**, **3,303 review candidates**, **62 technical identifiers**.

## Validation

- 13 automated workflow tests pass on Windows Python 3.13, including the actual translation pipeline with mocked DeepSeek transport to verify the fixed endpoint/model and placeholder preservation without making paid test requests.
- Windows GUI smoke test passes: startup, discovery, project loading, search and source selection.
- Every one of 39,730 Chinese string values in decoded JSON/cache sources was found in its mod project. This checks stored string coverage, not whether every game UI path is covered.
- All recorded source-file hashes matched after extraction. No input file was changed by this tool.
- Zero unreadable files in the final scan. Nineteen Unity bundles in Eternal Myth contain components without custom field type information and are reported as partial.
- Media and runtime-generated or obfuscated code text still need review. No OCR, speech recognition or in-game runtime capture was performed.
- The extraction tests used the offline dictionary engine. A subsequent DeepSeek V4.1 Flash check successfully translated one sample through the live API using `deepseek-flash`, preserving its markup and placeholder. The saved API settings were unchanged.

## Evidence

- [Full installation audit](projects/installation-audit.json)
- [Windows test output](projects/tests-windows.txt)
- [GUI checks](projects/gui-smoke.json)
- [GUI screenshot](projects/gui-smoke.png)
- [Full extraction log](projects/extraction.log)
- [DeepSeek V4.1 Flash live check](projects/deepseek-v41-check.json)

Per-mod `coverage.json` files contain individual file and Unity object details. Per-mod `strings.csv` and `strings.json` contain the extracted text and locations. See [README.md](README.md) for use and coverage limits.
