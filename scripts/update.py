#!/usr/bin/env python3
"""Check and patch SmartTube for the custom update channel."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path


UPSTREAM_MANIFEST = (
    "https://github.com/yuliskov/SmartTubeNext/releases/download/latest/"
    "smarttube_stable2.json"
)
TARGET_PACKAGE = "com.google.android.youtube.tv"
USER_AGENT = "smarttube-family-updater/1"


def download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=90) as response:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("wb") as output:
            shutil.copyfileobj(response, output)


def read_json_url(url: str) -> dict | None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


def latest_release(manifest: dict) -> tuple[str, dict]:
    releases = [
        (name, value)
        for name, value in manifest.items()
        if name != "package" and isinstance(value, dict) and "versionCode" in value
    ]
    if not releases:
        raise RuntimeError("No version entries found in update manifest")
    return max(releases, key=lambda item: int(item[1]["versionCode"]))


def set_output(name: str, value: object) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    line = f"{name}={str(value).lower() if isinstance(value, bool) else value}\n"
    if output_path:
        with open(output_path, "a", encoding="utf-8") as output:
            output.write(line)
    else:
        print(line, end="")


def command_check(args: argparse.Namespace) -> None:
    upstream = read_json_url(args.upstream_manifest)
    if upstream is None:
        raise RuntimeError("Upstream update manifest was not found")
    version_name, release = latest_release(upstream)
    upstream_code = int(release["versionCode"])

    custom_url = (
        f"https://github.com/{args.repository}/releases/download/"
        "custom-latest/update.json"
    )
    custom = read_json_url(custom_url)
    custom_code = -1
    if custom:
        _, custom_release = latest_release(custom)
        custom_code = int(custom_release["versionCode"])

    needs_update = upstream_code > custom_code
    urls = upstream.get("package", {}).get("downloadUrlList", [])
    if not urls:
        raise RuntimeError("Upstream ARM download URL is missing")

    Path(args.manifest_output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.manifest_output).write_text(
        json.dumps(upstream, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    set_output("needs_update", needs_update)
    set_output("version_name", version_name)
    set_output("version_code", upstream_code)
    set_output("apk_url", urls[0])
    set_output("update_url", custom_url)


def replace_method(smali: str) -> str:
    signature = (
        r"\.method public onUpdateFound\(Ljava/lang/String;Ljava/util/List;"
        r"Ljava/lang/String;\)V.*?^\.end method"
    )
    replacement = """.method public onUpdateFound(Ljava/lang/String;Ljava/util/List;Ljava/lang/String;)V
    .locals 1

    iget-object v0, p0, Lcom/liskovsoft/smartyoutubetv2/common/app/presenters/dialogs/AppUpdatePresenter;->mUpdateChecker:Lcom/liskovsoft/appupdatechecker2/AppUpdateChecker;

    invoke-virtual {v0}, Lcom/liskovsoft/appupdatechecker2/AppUpdateChecker;->installUpdate()V

    return-void
.end method"""
    updated, count = re.subn(signature, replacement, smali, flags=re.MULTILINE | re.DOTALL)
    if count != 1:
        raise RuntimeError(f"Expected one onUpdateFound method, replaced {count}")
    return updated


def command_patch(args: argparse.Namespace) -> None:
    decoded = Path(args.decoded)
    manifest_path = decoded / "AndroidManifest.xml"
    manifest = manifest_path.read_text(encoding="utf-8")
    manifest, count = re.subn(
        r'(?<=\bpackage=")[^"]+', TARGET_PACKAGE, manifest, count=1
    )
    if count != 1:
        raise RuntimeError("Could not replace manifest package")

    icon_path = Path(args.icon)
    if icon_path.exists():
        target_icon = decoded / "res" / "mipmap-nodpi" / "custom_youtube_icon.png"
        target_icon.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(icon_path, target_icon)
        if re.search(r'android:icon="[^"]+"', manifest):
            manifest = re.sub(
                r'android:icon="[^"]+"',
                'android:icon="@mipmap/custom_youtube_icon"',
                manifest,
                count=1,
            )
    manifest_path.write_text(manifest, encoding="utf-8")

    url_re = re.compile(
        r"https://github\.com/yuliskov/SmartTubeNext/releases/download/latest/"
        r"smarttube_(?:stable|stable2|beta|beta2)\.json"
    )
    replacements = 0
    for xml_path in (decoded / "res").rglob("*.xml"):
        text = xml_path.read_text(encoding="utf-8")
        updated, count = url_re.subn(args.update_url, text)
        if count:
            xml_path.write_text(updated, encoding="utf-8")
            replacements += count
    if replacements == 0:
        raise RuntimeError("Could not find an upstream update URL to replace")

    candidates = list(decoded.glob("smali*/com/liskovsoft/smartyoutubetv2/common/app/presenters/dialogs/AppUpdatePresenter.smali"))
    if len(candidates) != 1:
        raise RuntimeError(f"Expected one AppUpdatePresenter.smali, found {len(candidates)}")
    smali_path = candidates[0]
    smali_path.write_text(
        replace_method(smali_path.read_text(encoding="utf-8")), encoding="utf-8"
    )


def command_manifest(args: argparse.Namespace) -> None:
    manifest = json.loads(Path(args.input).read_text(encoding="utf-8"))
    download_url = (
        f"https://github.com/{args.repository}/releases/download/"
        "custom-latest/custom-smarttube.apk"
    )
    package = manifest.setdefault("package", {})
    for key in list(package):
        if key.startswith("downloadUrlList"):
            package[key] = [download_url]
    package.setdefault("downloadUrlList", [download_url])
    Path(args.output).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def command_apktool(args: argparse.Namespace) -> None:
    api = read_json_url("https://api.github.com/repos/iBotPeaches/Apktool/releases/latest")
    if not api:
        raise RuntimeError("Could not query the latest Apktool release")
    assets = api.get("assets", [])
    jars = [a for a in assets if re.fullmatch(r"apktool_[0-9.]+\.jar", a.get("name", ""))]
    if len(jars) != 1:
        raise RuntimeError(f"Expected one Apktool jar asset, found {len(jars)}")
    download(jars[0]["browser_download_url"], Path(args.output))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    commands = root.add_subparsers(dest="command", required=True)

    check = commands.add_parser("check")
    check.add_argument("--repository", required=True)
    check.add_argument("--manifest-output", required=True)
    check.add_argument("--upstream-manifest", default=UPSTREAM_MANIFEST)
    check.set_defaults(func=command_check)

    patch = commands.add_parser("patch")
    patch.add_argument("--decoded", required=True)
    patch.add_argument("--update-url", required=True)
    patch.add_argument("--icon", default="assets/icon.png")
    patch.set_defaults(func=command_patch)

    manifest = commands.add_parser("manifest")
    manifest.add_argument("--input", required=True)
    manifest.add_argument("--output", required=True)
    manifest.add_argument("--repository", required=True)
    manifest.set_defaults(func=command_manifest)

    apktool = commands.add_parser("download-apktool")
    apktool.add_argument("--output", required=True)
    apktool.set_defaults(func=command_apktool)
    return root


if __name__ == "__main__":
    arguments = parser().parse_args()
    try:
        arguments.func(arguments)
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        raise
