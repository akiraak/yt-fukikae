import argparse
import subprocess
import sys
from pathlib import Path
import shutil
import shlex


# =========================
# 定数
# =========================
OUTPUTS_DIR_NAME = "outputs"

SOURCE_VIDEO_FILENAME = "source_video.mp4"
SOURCE_AUDIO_FILENAME = "source_audio.m4a"
SOURCE_THUMB_FILENAME = "source_thumb.jpg"

TRANSCRIBE_FILENAME = "transcribe.txt"
TRANSCRIBE_WORKDIR_NAME = "_work_transcribe"

TRANSLATED_JA_FILENAME = "translated_ja.txt"
TRANSLATE_WORKDIR_NAME = "_work_translate_to_ja"

# make_final_video.py 側のデフォルト名と揃えておく（内部用に保持）
VIDEO_THUMB_FINAL_NAME = "video_thumb_final.png"

# ここから追加: サムネ & 最終動画生成用
FINAL_AUDIO_JA_FILENAME = "audio_ja.mp3"  # text_to_speech.js の出力 (outputs/[name]/audio_ja.mp3 を想定)
BACKGROUND_IMAGE_PATH = Path("assets/chobi_screen_yt_fukikae_x2.png")

# デフォルトのヘッダーとタイトル（引数で指定がなかった場合に使用）
DEFAULT_HEADER_TEXT = ""
DEFAULT_TITLE_TEXT = ""


def parse_args() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "YouTube から音声・動画・サムネをダウンロードし、"
            "後続処理（文字起こし・翻訳・TTS など）を行うための起点スクリプト"
        )
    )

    parser.add_argument(
        "--name",
        dest="name",
        required=True,
        help="このジョブ/一連の処理・ファイル名につける名前（例: BBC, CNBC_20251125 など）",
    )

    parser.add_argument(
        "--youtube-id",
        dest="youtube_id",
        required=True,
        help="YouTube 動画ID",
    )

    # 追加: ヘッダーテキスト
    parser.add_argument(
        "--header",
        dest="header",
        default=DEFAULT_HEADER_TEXT,
        help=f"動画のヘッダーテキスト（デフォルト: '{DEFAULT_HEADER_TEXT}'）",
    )

    # 追加: タイトルテキスト
    parser.add_argument(
        "--title",
        dest="title",
        default=DEFAULT_TITLE_TEXT,
        help=f"動画のタイトルテキスト（デフォルト: '{DEFAULT_TITLE_TEXT}'）",
    )

    # 最終出力ディレクトリ（動画 & サムネ）
    parser.add_argument(
        "--output-dir",
        dest="output_dir",
        help=(
            "最終的な mp4 とサムネ PNG を保存するディレクトリ。"
            "指定しない場合は ./outputs に保存されます。"
        ),
    )

    # ★サムネだけ作りたいときのフラグ
    parser.add_argument(
        "--image-only",
        action="store_true",
        help="最終動画を作らず、サムネ画像だけ生成する（YouTube からはサムネのみ取得）",
    )

    return parser


def print_command(label: str, cmd: list[str]) -> None:
    """
    実行コマンドを見やすく表示するヘルパー。
    """
    print("\n" + "-" * 60)
    print(f"[STEP] {label}")

    if cmd:
        print(f"  Exec   : {cmd[0]}")
    if len(cmd) > 1:
        print(f"  Script : {cmd[1]}")
    full = " ".join(shlex.quote(str(c)) for c in cmd)
    print("  Command:")
    print(f"    {full}")
    print("-" * 60)


def main() -> None:
    parser = parse_args()
    args = parser.parse_args()

    base_dir = Path(__file__).parent
    outputs_dir = base_dir / OUTPUTS_DIR_NAME
    job_dir = outputs_dir / args.name  # outputs/[--name]

    # 既存の outputs/[name] を削除してから作成
    if job_dir.exists():
        print(f"[INFO] Remove existing job dir : {job_dir}")
        shutil.rmtree(job_dir)

    outputs_dir.mkdir(parents=True, exist_ok=True)
    job_dir.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] Output base dir : {outputs_dir}")
    print(f"[INFO] Job output dir  : {job_dir}")

    # 各出力ファイルパス（中間成果物）
    video_path = job_dir / SOURCE_VIDEO_FILENAME
    audio_path = job_dir / SOURCE_AUDIO_FILENAME
    thumb_path = job_dir / SOURCE_THUMB_FILENAME

    transcribe_path = job_dir / TRANSCRIBE_FILENAME
    transcribe_workdir = job_dir / TRANSCRIBE_WORKDIR_NAME  # outputs/[name]/_work_transcribe/

    translated_ja_path = job_dir / TRANSLATED_JA_FILENAME
    translate_workdir = job_dir / TRANSLATE_WORKDIR_NAME    # outputs/[name]/_work_translate_to_ja/

    # TTS 出力パスはどちらのモードでも先に決めておく
    audio_ja_path = job_dir / FINAL_AUDIO_JA_FILENAME  # outputs/[name]/audio_ja.mp3

    # 最終出力ディレクトリ（サムネ・動画）
    if args.output_dir:
        final_output_dir = Path(args.output_dir).expanduser()
    else:
        # デフォルト: ./outputs
        final_output_dir = outputs_dir

    final_output_dir.mkdir(parents=True, exist_ok=True)
    final_thumb_path = final_output_dir / f"{args.name}_thumb.png"
    final_video_path = final_output_dir / f"{args.name}.mp4"

    print(f"[INFO] Final output dir : {final_output_dir}")
    print(f"[INFO] Final video path : {final_video_path}")
    print(f"[INFO] Final thumb path : {final_thumb_path}")

    # 1) dl_youtube.py で YouTube から取得
    dl_script_path = base_dir / "dl_youtube.py"

    if args.image_only:
        # ★サムネだけ取得
        cmd_dl = [
            sys.executable,
            str(dl_script_path),
            "--video-id", args.youtube_id,
            "--output-thumb", str(thumb_path),
        ]
        print("[INFO] --image-only: YouTube からはサムネイルのみ取得します（動画/音声はダウンロードしません）")
    else:
        # 通常モード: 動画 + 音声 + サムネ
        cmd_dl = [
            sys.executable,
            str(dl_script_path),
            "--video-id", args.youtube_id,
            "--output-video", str(video_path),
            "--output-audio", str(audio_path),
            "--output-thumb", str(thumb_path),
        ]

    print_command("download (dl_youtube.py)", cmd_dl)
    result = subprocess.run(cmd_dl)
    print(f"[INFO] dl_youtube.py returncode = {result.returncode}")
    if result.returncode != 0:
        print("[FATAL] dl_youtube.py failed")
        sys.exit(result.returncode)

    # make_final_video.py で使う共通情報
    make_final_video_path = base_dir / "make_final_video.py"
    youtube_short_url = f"https://youtu.be/{args.youtube_id}"

    if args.image_only:
        # 音声ファイルは存在しなくてよいので、ダミーとして source_audio パスを渡す
        cmd_make_video = [
            sys.executable,
            str(make_final_video_path),
            str(BACKGROUND_IMAGE_PATH),
            str(audio_path),          # 存在しないが --image-only なのでチェックされない
            "--header", args.header,  # 引数を使用
            "--title", args.title,    # 引数を使用
            "--url", youtube_short_url,
            "--embed-thumb", str(thumb_path),
            "--output-thumb", str(final_thumb_path),
            "--image-only",
        ]

        print_command("make_final_video (image-only)", cmd_make_video)
        subprocess.run(cmd_make_video, check=True)

        print(f"[INFO] --image-only 処理が完了しました（サムネ PNG のみ生成）: {final_thumb_path}")
        return

    # ===== ここからは通常モードのみ =====

    # 2) transcribe.js で文字起こし
    transcribe_js_path = base_dir / "transcribe.js"
    cmd_transcribe = [
        "node",
        str(transcribe_js_path),
        str(audio_path),
        str(transcribe_path),
        str(transcribe_workdir),
    ]

    print_command("transcribe (transcribe.js)", cmd_transcribe)
    subprocess.run(cmd_transcribe, check=True)

    # 3) translate_to_ja.js で日本語翻訳
    translate_js_path = base_dir / "translate_to_ja.js"
    cmd_translate = [
        "node",
        str(translate_js_path),
        str(transcribe_path),        # 入力: 英語テキスト
        str(translated_ja_path),     # 出力: 日本語テキスト (translated_ja.txt)
        str(translate_workdir),      # 作業・デバッグ用ディレクトリ
    ]

    print_command("translate_to_ja (translate_to_ja.js)", cmd_translate)
    subprocess.run(cmd_translate, check=True)

    # 4) text_to_speech.js で日本語テキスト → 日本語音声 (audio_ja.mp3)
    tts_js_path = base_dir / "text_to_speech.js"
    cmd_tts = [
        "node",
        str(tts_js_path),
        str(translated_ja_path),   # 入力: translated_ja.txt
        "--output",
        str(audio_ja_path),        # 出力: audio_ja.mp3
    ]

    print_command("text_to_speech (text_to_speech.js)", cmd_tts)
    subprocess.run(cmd_tts, check=True)

    # 5) make_final_video.py で最終動画生成（オリジナル動画を埋め込み）
    cmd_make_video = [
        sys.executable,
        str(make_final_video_path),
        str(BACKGROUND_IMAGE_PATH),
        str(audio_ja_path),
        "--header", args.header,
        "--title", args.title,
        "--url", youtube_short_url,
        "--embed-thumb", str(thumb_path),
        "--embed-video", str(video_path),
        "--output-thumb", str(final_thumb_path),
        "--output-video", str(final_video_path),
    ]

    print_command("make_final_video (make_final_video.py)", cmd_make_video)
    subprocess.run(cmd_make_video, check=True)

    print(f"[INFO] 完了: 動画 = {final_video_path}")
    print(f"[INFO] 完了: サムネ = {final_thumb_path}")


if __name__ == "__main__":
    main()