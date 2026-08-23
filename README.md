# MowerHotUpdate

Mower 的热更新仓库。

热更新是超小滚动件（导航步骤 + 活动关卡），随活动更新。仓库 `main` 维护**构建期输入**，不做版本发布：

- `stage_data.json`：当前活动关（`stageType==ACTIVITY` 子集，含 `endTs:{startTs,endTs}` 窗口），由 [MowerResource](https://github.com/ArkMowers/MowerResource) 资源包管线在每次游戏数据变化后自动推送（SSH deploy key，内容无变化跳过）。
- `key_mapping.json`：物品名映射，供 Release 说明解析掉落中文名（**只进仓库，不进发布 zip**）。
- `nav_steps.json`：官方导航步骤（`{version, stages, patterns}`），由维护者本地录制脚本生成，见下方发布步骤。

**发布**：推 `vYYYY.MM.DD-<hex>` tag（格式与客户端热更版本号一致）时，GitHub Actions 自动打包——把 tag 上的 `stage_data.json` + `nav_steps.json` 打成 `hot_update.zip` 发 GitHub Release（zip 内含生成的 `version.json`），Release 说明列活动关卡+掉落。客户端热更从 `releases/latest/download/hot_update.zip` 拉取。

## 维护者发布步骤（录制导航步骤）

前置：模拟器已连 adb、本机 git 对 MowerHotUpdate 有写权限、已检出 [arknights-mower](https://github.com/NiceAfternoon/arknights-mower) 的 `feat/stage-data-runtime-read` 分支。

1. **录制**（在 mower 仓库根目录）：
   ```bash
   python scripts/record_official_nav_steps.py          # 自动选最新活动关
   # 或显式指定要录制的关卡：
   python scripts/record_official_nav_steps.py PA-1 PA-2
   # --no-ocr：跳过 OCR 初始化（无 OCR 资源时降级，导航可能变慢）
   # -o <path> / --notes-output <path>：自定义 nav_steps.json / release_notes.md 导出路径
   ```
   - 不传关卡时，脚本会拉 MowerHotUpdate 最新 `stage_data.json`，按刷理智周计划同一套规则选最新活动的普通关。
2. **产出**：`nav_steps.json` + `release_notes.md`，并打印推荐发布 tag（`v北京日期-内容哈希`）和 git 命令。
3. **发布**：按脚本打印的命令执行（`git clone` → `cp` → `git commit` → `git push origin main` → `git tag <tag> && git push origin <tag>`）。
4. **发版**：tag 推上去后，本仓库的 Actions 自动打包发 Release，客户端热更即可拉到。

## 版权与授权

本仓库内容为游戏数据资源（json），游戏素材 ©上海鹰角网络科技有限公司，仅用于学习与交流，侵删。
