#!/usr/bin/env python3
"""提取不可变原件的文字，输出到对应的 extracted 路径。"""

import argparse
import hashlib
import json
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract(vault, source, correct_conversion=False, original_name=None, origin=None):
    vault = Path(vault).resolve()
    raw = vault / "raw"
    extracted = vault / "extracted"
    if raw.is_symlink() or extracted.is_symlink():
        raise ValueError("来源或提取根目录不能是符号链接")
    source = Path(source)
    if source.is_symlink():
        raise ValueError("来源文件不能是符号链接")
    source = source.resolve()
    relative = source.relative_to(raw.resolve())
    target = extracted / relative.parent / (relative.name + ".md")
    if not target.resolve().is_relative_to(extracted.resolve()):
        raise ValueError("提取输出越出了 extracted 目录")
    if target.is_symlink():
        raise ValueError("提取输出不能是符号链接")
    if target.exists() and not correct_conversion:
        raise FileExistsError("已有提取版；仅在对照原件纠错时使用 --correct-conversion")
    before = digest(source)
    suffix = source.suffix.lower()
    notes = []
    assets = []
    if suffix in (".md", ".markdown"):
        content = source.read_bytes()
        notes.append("Markdown 原文按字节复制，来源记录在相邻 JSON 中。")
    elif suffix == ".txt":
        content = source.read_text(encoding="utf-8-sig").encode("utf-8")
    elif suffix == ".pdf":
        import pymupdf as fitz

        parts = []
        with fitz.open(source) as document:
            for number, page in enumerate(document, 1):
                parts.append(f"## 原件第 {number} 页\n\n")
                text = page.get_text("text")
                parts.append(text if text.strip() else "[本页无可提取文字层，需要回查原件或另行 OCR。]\n")
                for index, image in enumerate(page.get_images(full=True), 1):
                    item = document.extract_image(image[0])
                    asset = extracted / "assets" / before / f"page-{number}-image-{index}.{item['ext']}"
                    if asset.is_symlink() or not asset.resolve().is_relative_to(extracted.resolve()):
                        raise ValueError("图片附件越出了 extracted 目录")
                    asset.parent.mkdir(parents=True, exist_ok=True)
                    if asset.exists():
                        if asset.read_bytes() != item["image"]:
                            raise ValueError("已有附件与原件提取结果不同")
                    else:
                        asset.write_bytes(item["image"])
                    assets.append(asset.relative_to(vault).as_posix())
                    parts.append(f"\n![[{asset.relative_to(vault).as_posix()}|第 {number} 页图片 {index}]]\n")
                parts.append("\n")
        content = "".join(parts).encode("utf-8")
        notes.append("文字层按页提取；表格、公式、版面和图片内容仍需依据原件核对。")
    elif suffix in (".html", ".htm"):
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(source.read_bytes(), "html.parser")
        messages = soup.select("[data-chatgpt-search-unit-key]")
        if messages:
            parts = []
            for message in messages:
                key = message.get("data-chatgpt-search-unit-key", "")
                if not key.endswith((":user", ":assistant")):
                    continue
                for tag in message.select("script, style, button, svg, nav, aside"):
                    tag.decompose()
                for tag in message.find_all(["p", "li", "h1", "h2", "h3", "h4", "pre", "blockquote"]):
                    tag.insert_after("\n\n")
                for tag in message.find_all("br"):
                    tag.replace_with("\n")
                role = "用户" if key.endswith(":user") else "助手"
                parts.append(f"## {role}\n\n{message.get_text(separator='').strip()}\n")
            text = "\n".join(parts)
        else:
            for tag in soup.select("script, style, nav, aside, button"):
                tag.decompose()
            body = soup.find("main") or soup.body or soup
            text = body.get_text(separator="\n", strip=True)
        content = text.encode("utf-8")
        notes.append("HTML 可见文字提取；表格、代码排版及图片附件需回查原页面。")
    else:
        raise ValueError("当前脚本支持 PDF、Markdown、UTF-8 文本及 HTML；其他格式另行处理")
    if digest(source) != before:
        raise ValueError("提取期间原件发生变化，已停止输出")
    metadata = target.with_name(target.name + ".source.json")
    if metadata.is_symlink():
        raise ValueError("来源记录不能是符号链接")
    target.parent.mkdir(parents=True, exist_ok=True)
    mode = "wb" if correct_conversion else "xb"
    with target.open(mode) as output:
        output.write(content)
    record = {
        "source_path": source.relative_to(vault).as_posix(),
        "source_sha256": before,
        "stored_name": relative.name,
        "original_name": original_name,
        "origin": origin,
        "extracted_path": target.relative_to(vault).as_posix(),
        "status": "unverified",
        "notes": notes,
        "assets": assets,
    }
    metadata.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--correct-conversion", action="store_true")
    parser.add_argument("--original-name")
    parser.add_argument("--origin")
    args = parser.parse_args()
    print(json.dumps(extract(args.vault, args.source, args.correct_conversion, args.original_name, args.origin), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
