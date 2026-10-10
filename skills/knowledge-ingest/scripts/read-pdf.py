#!/usr/bin/env python3
"""只读原件并输出指定 PDF 页；页面图像可缓存到仓库之外。"""

import argparse
import hashlib
import json
from pathlib import Path

import pymupdf


def selected_pages(specification, page_count):
    if specification is None:
        return list(range(1, min(page_count, 3) + 1))
    selected = set()
    for item in specification.split(","):
        interval = item.strip().split("-")
        if not 1 <= len(interval) <= 2 or any(not part.strip().isdigit() for part in interval):
            raise ValueError("页码格式为 1-3,7，使用从 1 开始的 PDF 实际页序")
        start, end = int(interval[0]), int(interval[-1])
        if start < 1 or end < start or end > page_count:
            raise ValueError(f"页码越界或范围颠倒：{item}；文件共 {page_count} 页")
        selected.update(range(start, end + 1))
    return sorted(selected)


def read_pdf(vault, source, pages=None, render_dir=None):
    vault = Path(vault).resolve()
    raw = vault / "raw"
    source = Path(source)
    if not source.is_absolute():
        source = vault / source
    if raw.is_symlink() or source.is_symlink():
        raise ValueError("原件根目录及文件不能是符号链接")
    source = source.resolve(strict=True)
    if not source.is_relative_to(raw.resolve()) or source.suffix.lower() != ".pdf":
        raise ValueError("需要提供本仓库 raw/ 中的 PDF 原件")
    relative = source.relative_to(vault).as_posix()
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    cache = None
    if render_dir is not None:
        cache = Path(render_dir).expanduser().resolve()
        if cache.is_relative_to(vault):
            raise ValueError("页面阅读缓存须位于知识仓库之外")

    with pymupdf.open(source) as document:
        if document.needs_pass:
            raise ValueError("原件需要密码，请提供可读取的副本")
        selected = selected_pages(pages, len(document))
        result = {"source_path": relative, "source_sha256": before,
                  "page_count": len(document), "displayed_pdf_pages": selected,
                  "reading_scope": "selected-pages", "pages": []}
        for number in selected:
            page = document[number - 1]
            text = page.get_text("text")
            entry = {"pdf_page": number,
                     "citation": f"[[{relative}#page={number}|原件第 {number} 页]]",
                     "text_layer_present": bool(text.strip()), "text": text}
            if cache is not None:
                target = cache / before / f"page-{number}.png"
                if target.is_symlink() or not target.resolve().is_relative_to(cache):
                    raise ValueError("页面图像缓存路径异常")
                content = page.get_pixmap(dpi=150).tobytes("png")
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    if target.read_bytes() != content:
                        raise ValueError("已有页面缓存不一致，请使用新的缓存目录")
                else:
                    with target.open("xb") as output:
                        output.write(content)
                entry["rendered_image"] = str(target)
            result["pages"].append(entry)
    if hashlib.sha256(source.read_bytes()).hexdigest() != before:
        raise ValueError("读取期间原件发生变化，请重新核对")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--pages", help="PDF 文件实际页序，从 1 开始，例如 1-3,7")
    parser.add_argument("--render-dir", help="可选：仓库外的指定页图像缓存目录")
    args = parser.parse_args()
    print(json.dumps(read_pdf(args.vault, args.source, args.pages, args.render_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
