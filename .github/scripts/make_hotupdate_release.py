#!/usr/bin/env python3
"""MowerHotUpdate 热更包打包发布脚本（tag 触发，在 GitHub Actions 内运行）。

推 ``vYYYY.MM.DD-<hex>`` tag 时，把该 tag 上的 ``stage_data.json`` +
``nav_steps.json`` 打成 ``hot_update.zip`` 发 GitHub Release（notes 列关卡+掉落）。
zip 根目录至少 stage_data.json / nav_steps.json 之一（客户端 _HOTUPDATE_MARKERS 校验）。

运行环境（由 workflow 提供）:
  GITHUB_WORKSPACE   MowerHotUpdate 检出（tag commit，仓库根 = 打包目标）
  GITHUB_REF         refs/tags/<tag>
  GH_TOKEN           gh CLI（建 Release / 传资产）
"""

import json
import os
import re
import subprocess
import sys
import time
import zipfile
from pathlib import Path

# 与客户端 hot_update.py 的 _TAG_RE 一致，避免发不合规 tag 的 Release
TAG_RE = re.compile(r"^v(\d{4})\.(\d{2})\.(\d{2})-([0-9a-fA-F]{6,40})$")
ZIP_NAME = "hot_update.zip"  # 资产名稳定，客户端 releases/latest/download 拉
DATA_FILES = ("stage_data.json", "nav_steps.json")  # zip 根目录的热更数据文件
VERSION_FILE = "version.json"  # 手动通道 _version_tag_from_zip 用的版本文件
KEY_MAPPING = "key_mapping.json"  # 掉落名映射，只进仓库供打包读，不进 zip
NOTES_FILE = "release_notes.md"  # #199 可选预生成，存在则原样用


def workspace() -> Path:
    return Path(os.environ["GITHUB_WORKSPACE"])


def run(cmd: list, check=True):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"命令失败 {cmd}: {result.stdout} {result.stderr}")
    return result


def current_tag() -> str:
    ref = os.environ.get("GITHUB_REF", "")
    tag = ref.removeprefix("refs/tags/") if ref else ""
    if not tag or tag == ref:
        raise RuntimeError(f"GITHUB_REF 不是 tag: {ref or '(未设置)'}")
    return tag


def load_json(path: Path) -> dict | list:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_zip(out_zip: Path, tag: str, include: list[Path]) -> None:
    """打 hot_update.zip：热更数据文件 + 生成的 version.json（条目用源 mtime）。"""
    now = time.localtime()[:6]
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in include:
            st = p.stat()
            zi = zipfile.ZipInfo(p.name, date_time=time.localtime(st.st_mtime)[:6])
            zi.compress_type = zipfile.ZIP_DEFLATED
            with open(p, "rb") as fh:
                zf.writestr(zi, fh.read())
        zi = zipfile.ZipInfo(VERSION_FILE, date_time=now)
        zi.compress_type = zipfile.ZIP_DEFLATED
        zf.writestr(
            zi, json.dumps({"version": tag}, ensure_ascii=False).encode("utf-8")
        )


def drop_names(drop, key_mapping: dict | None) -> list[str]:
    """掉落物中文名（MATERIAL + NORMAL，与客户端 weekly_stage 语义一致）；无映射回退 id。"""
    names = []
    for d in drop or []:
        if d.get("type") != "MATERIAL" or d.get("dropType") != "NORMAL":
            continue
        item_id = d.get("id", "")
        entry = key_mapping.get(item_id) if key_mapping else None
        name = (
            entry[2]
            if isinstance(entry, list) and len(entry) > 2 and entry[2]
            else item_id
        )
        if name not in names:
            names.append(name)
    return names


def build_notes(tag: str, stage_data: list, key_mapping: dict | None) -> str:
    """从 stage_data（ACTIVITY 子集）生成 Release notes：活动分组 + 关卡 + 掉落。"""
    groups = {}
    for s in stage_data:
        if s.get("stageType") != "ACTIVITY":
            continue
        activity = s.get("zoneNameSecond") or s.get("zoneId") or "未知活动"
        groups.setdefault(activity, []).append(s)
    lines = [f"# 热更包 {tag}", ""]
    if not groups:
        lines.append("仅导航步骤更新，无活动关卡数据。")
    else:
        lines.append("本次热更包含以下活动关卡与掉落：")
        for activity, stages in groups.items():
            lines.append("")
            lines.append(f"### {activity}")
            for s in stages:
                code = s.get("id") or s.get("name") or ""
                name = s.get("name") or ""
                drops = drop_names(s.get("drop"), key_mapping)
                if drops:
                    lines.append(f"- {code} {name}：{'、'.join(drops)}")
                else:
                    lines.append(f"- {code} {name}")
    lines += ["", "数据 ©上海鹰角网络科技有限公司，仅用于学习与交流，侵删。"]
    return "\n".join(lines)


def main(argv: list) -> int:
    ws = workspace()
    tag = current_tag()
    if not TAG_RE.match(tag):
        raise RuntimeError(f"tag 格式不合法: {tag}（需 vYYYY.MM.DD-<hex>）")

    data = [ws / name for name in DATA_FILES if (ws / name).exists()]
    if not data:
        raise RuntimeError(f"tag 上没有可打包的热更数据（缺 {DATA_FILES} 任一）")

    key_mapping = {}
    if (ws / KEY_MAPPING).exists():
        loaded = load_json(ws / KEY_MAPPING)
        if isinstance(loaded, dict):
            key_mapping = loaded

    out_zip = ws / ZIP_NAME
    build_zip(out_zip, tag, data)

    notes_file = ws / NOTES_FILE
    if notes_file.exists():
        notes = notes_file.read_text(encoding="utf-8")
    else:
        stage_data = []
        if (ws / "stage_data.json").exists():
            loaded = load_json(ws / "stage_data.json")
            stage_data = loaded if isinstance(loaded, list) else []
        notes = build_notes(tag, stage_data, key_mapping)
    notes_file.write_text(notes, encoding="utf-8")

    # 幂等重跑：先删旧 Release（不带 --cleanup-tag，保留 tag），再建
    run(["gh", "release", "delete", tag, "--yes"], check=False)
    run(
        [
            "gh",
            "release",
            "create",
            tag,
            str(out_zip),
            "--title",
            f"热更包 {tag}",
            "--notes-file",
            str(notes_file),
        ]
    )
    print(f"已发布热更包 {tag}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as e:  # 让 CI 步骤失败可见
        print(f"热更包发布失败: {e}", file=sys.stderr)
        sys.exit(1)
