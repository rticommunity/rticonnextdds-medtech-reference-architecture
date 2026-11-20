"""Render an allowlist of canonical Markdown pages; do not publish the output."""

import argparse
import os
import re
import shutil
import subprocess
import tempfile
import textwrap
import tomllib
from pathlib import Path
from urllib.parse import quote, urlsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LINK = re.compile(r"(!?\[[^\]\n]*\])\(([^()\s]+)\)")
PLATFORM_TABS = re.compile(
    r"<!-- platform-tabs:start -->\n(.*?)<!-- platform-tabs:end -->", re.DOTALL
)
PLATFORM_HEADING = re.compile(r"^#### (Linux|macOS|Windows)\n", re.MULTILINE)


def platform_tabs(markdown: str) -> str:
    groups = list(PLATFORM_TABS.finditer(markdown))
    if (
        len(groups) != 2
        or markdown.count("<!-- platform-tabs:start -->") != 2
        or markdown.count("<!-- platform-tabs:end -->") != 2
    ):
        raise ValueError("README must contain two complete platform tab groups")

    def convert(match: re.Match[str]) -> str:
        content = match.group(1)
        headings = list(PLATFORM_HEADING.finditer(content))
        if [heading.group(1) for heading in headings] != ["Linux", "macOS", "Windows"]:
            raise ValueError("Platform tab groups must contain Linux, macOS, and Windows")
        if content[: headings[0].start()].strip():
            raise ValueError("Unexpected content before platform headings")
        tabs = []
        for index, heading in enumerate(headings):
            end = headings[index + 1].start() if index + 1 < len(headings) else len(content)
            body = content[heading.end() : end].strip()
            if not body:
                raise ValueError(f"Empty {heading.group(1)} platform tab")
            tabs.append(f'=== "{heading.group(1)}"\n\n{textwrap.indent(body, "    ")}\n')
        return "\n".join(tabs)

    return PLATFORM_TABS.sub(convert, markdown)


def pages(nav: list) -> list[str]:
    return [
        page
        for item in nav
        for value in item.values()
        for page in ([value] if isinstance(value, str) else pages(value))
    ]


def build_site(output: Path, ref: str) -> None:
    config = HERE / "zensical.toml"
    project = tomllib.loads(config.read_text(encoding="utf-8"))["project"]
    sources = {"README.md" if name == "index.md" else name: name for name in pages(project["nav"])}
    with tempfile.TemporaryDirectory(prefix="medtech-docs-") as temp:
        work = Path(temp)
        content = work / project["docs_dir"]
        for source, destination in sources.items():
            path = ROOT / source
            dest = content / destination
            dest.parent.mkdir(parents=True, exist_ok=True)

            def rewrite(match: re.Match[str]) -> str:
                label, url = match.groups()
                target = urlsplit(url)
                if target.scheme or not target.path or target.netloc:
                    return match[0]
                local = (path.parent / target.path).resolve()
                relative = local.relative_to(ROOT).as_posix()
                if local.is_dir() and f"{relative}/README.md" in sources:
                    relative += "/README.md"
                fragment = f"#{target.fragment}" if target.fragment else ""
                if relative in sources:
                    href = os.path.relpath(content / sources[relative], dest.parent).replace(
                        os.sep, "/"
                    )
                elif not local.exists():
                    raise ValueError(f"{source}: broken link to {url}")
                elif label.startswith("!") and relative.startswith("docs/assets/"):
                    asset = content / relative
                    asset.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(local, asset)
                    href = os.path.relpath(asset, dest.parent).replace(os.sep, "/")
                else:
                    kind = "tree" if local.is_dir() else "blob"
                    href = f"{project['repo_url']}/{kind}/{quote(ref, safe='')}/{quote(relative)}"
                return f"{label}({href}{fragment})"

            markdown = path.read_text(encoding="utf-8")
            if source == "README.md":
                markdown = platform_tabs(markdown)
            dest.write_text(LINK.sub(rewrite, markdown), encoding="utf-8")
        shutil.copytree(HERE / "theme", content / "theme")
        shutil.copyfile(config, work / config.name)
        subprocess.run(["zensical", "build", "--clean"], cwd=work, check=True)
        shutil.copytree(work / "site", output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="New directory for the rendered site")
    parser.add_argument("--ref", default="main", help="Git ref for source-code links")
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"Output directory already exists: {args.output}")
    build_site(args.output.resolve(), args.ref)
