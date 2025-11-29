#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import urllib.request
import urllib.error

from yt_dlp import YoutubeDL


# ========= AUDIO =========
def download_audio(video_id: str, output_path: Path) -> Path | None:
    """
    音声のみをダウンロードして output_path に保存する。
    拡張子が付いていればそれを codec として使う（例: .m4a, .mp3）。
    拡張子が無ければ m4a にする。
    """
    url = f"https://www.youtube.com/watch?v={video_id}"

    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    suffix = output_path.suffix.lstrip(".").lower()
    codec = suffix if suffix else "m4a"

    base = output_path.with_suffix("")  # 拡張子なしベース名

    ydl_opts: dict = {
        "format": "bestaudio/best",
        "noplaylist": True,
        "outtmpl": str(base) + ".%(ext)s",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": codec,
                "preferredquality": "192",
            }
        ],
    }

    final_path = base.with_suffix(f".{codec}")

    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    return final_path if final_path.exists() else None


# ========= VIDEO =========
def download_video(video_id: str, output_path: Path) -> Path | None:
    """
    動画（映像+音声）をダウンロードして MP4 で保存する。
    ユーザーが指定した拡張子は無視して、常に .mp4 で保存。
    """
    url = f"https://www.youtube.com/watch?v={video_id}"

    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    base = output_path.with_suffix("")  # 拡張子なしベース名
    ext = "mp4"

    ydl_opts: dict = {
        "format": "bv*+ba/b",                # 映像+音声
        "noplaylist": True,
        "outtmpl": str(base) + ".%(ext)s",
        "merge_output_format": ext,          # 最終的なコンテナを mp4 に
    }

    final_path = base.with_suffix(f".{ext}")

    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    return final_path if final_path.exists() else None


# ========= THUMBNAIL (直URL版) =========
def download_thumbnail(video_id: str, output_path: Path) -> Path | None:
    """
    サムネイル画像をダウンロードして output_path に保存する。
    優先順位: maxresdefault -> sddefault -> hqdefault

    NOTE:
      YouTube の静的サムネURLを直接叩く方式。
      例: https://img.youtube.com/vi/{video_id}/maxresdefault.jpg
    """
    sizes = ["maxresdefault", "sddefault", "hqdefault"]

    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    for size in sizes:
        thumb_url = f"https://img.youtube.com/vi/{video_id}/{size}.jpg"
        print(f"[THUMB] Try: {thumb_url}")
        try:
            with urllib.request.urlopen(thumb_url) as resp:
                if resp.status != 200:
                    print(f"[THUMB] HTTP {resp.status}, try next size")
                    continue
                data = resp.read()
        except urllib.error.HTTPError as e:
            print(f"[THUMB] HTTPError ({size}): {e}")
            continue
        except urllib.error.URLError as e:
            print(f"[THUMB] URLError: {e}")
            return None

        # ユーザー指定のパスそのままに書き込み（拡張子はそのまま使う）
        output_path.write_bytes(data)
        print(f"[THUMB] Saved thumbnail -> {output_path}")
        return output_path

    print("[THUMB] No available thumbnail found.")
    return None


# ========= CLI 部分 =========
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="YouTube 動画IDから動画・音声・サムネイルをダウンロードします。"
    )

    parser.add_argument(
        "--video-id",
        required=True,
        help="YouTube 動画ID（例: dQw4w9WgXcQ）",
    )
    parser.add_argument(
        "--output-video",
        help="動画ファイルの出力パス（例: outputs/NAME/source_video.mp4）",
    )
    parser.add_argument(
        "--output-audio",
        help="音声ファイルの出力パス（例: outputs/NAME/source_audio.m4a）",
    )
    parser.add_argument(
        "--output-thumb",
        help="サムネイル画像の出力パス（例: outputs/NAME/source_thumb.png）",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not any([args.output_video, args.output_audio, args.output_thumb]):
        raise SystemExit(
            "[ERROR] --output-video / --output-audio / --output-thumb のいずれかを指定してください。"
        )

    video_id = args.video_id

    saved_video = saved_audio = saved_thumb = None

    if args.output_video:
        saved_video = download_video(video_id, Path(args.output_video))

    if args.output_audio:
        saved_audio = download_audio(video_id, Path(args.output_audio))

    if args.output_thumb:
        saved_thumb = download_thumbnail(video_id, Path(args.output_thumb))

    print("\n========== Download Summary ==========")
    print(f"動画ID        : {video_id}")

    if saved_video:
        print(f"[VIDEO]  {saved_video}  ({saved_video.stat().st_size / (1024*1024):.2f} MB)")
    elif args.output_video:
        print("[VIDEO]  ダウンロード失敗")

    if saved_audio:
        print(f"[AUDIO]  {saved_audio}  ({saved_audio.stat().st_size / (1024*1024):.2f} MB)")
    elif args.output_audio:
        print("[AUDIO]  ダウンロード失敗")

    if saved_thumb:
        print(f"[THUMB]  {saved_thumb}  ({saved_thumb.stat().st_size / 1024:.1f} KB)")
    elif args.output_thumb:
        print("[THUMB]  ダウンロード失敗")

    print("======================================\n")


if __name__ == "__main__":
    main()
