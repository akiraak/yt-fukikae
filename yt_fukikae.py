#!/usr/bin/env python
import argparse
import subprocess
from pathlib import Path
import shutil
import re
import urllib.request
import urllib.error
import shlex  # for pretty-printing commands
import sys

import yt_dlp

# ===== 設定系 =====

# 作業用のベース出力ディレクトリ（固定）
OUTPUT_BASE_DIR = Path("output")

AUDIO_BASENAME      = "video_audio_src" # ダウンロードした m4a のファイル名
AUDIO_CODEC         = "m4a"             # FFmpegExtractAudio の出力コーデック
AUDIO_SMALL_NAME    = "video_audio_src_small_16k32k.webm"   # サイズ削減版につけるサフィックス

# 無音性分割関連
SILENCE_LOG_FINEMANE    = "video_audio_src_silence.log"
SILENCE_MIN_SEGMENT     = 240   # split_by_silence の --min-segment（秒）
SILENCE_MAX_SEGMENT     = 480   # split_by_silence の --max-segment（秒）
SILENCE_NOISE_DB        = -30   # dB
SILENCE_MIN_LENGTH      = 0.5   # 秒

# 無音分割後のファイル名プレフィックス
VIDEO_AUDIO_SRC_CHANK_PREFIX    = "video_audio_src_chank_"
TRANSCRIPT_TEXT_PREFIX          = "video_transcript_src_"
TRANSCRIPT_JA_PREFIX            = "video_transcript_ja_"
SCRIPT_JA_PREFIX                = "video_script_ja_"
TRANSCRIPT_JA_ALL_FILENAME      = "video_transcript_ja_all.txt"

# 文字起こし用モデル
TRANSCRIBE_MODEL = "gpt-4o-transcribe"

# 日本語訳用モデル
TRANSLATE_MODEL = "gpt-5.1"

# 日本語テキスト分割時の最大文字数
MAX_JA_CHARS = 800

# TTS 用デフォルト
TTS_MODEL_DEFAULT = "gpt-4o-mini-tts"
TTS_VOICE_DEFAULT = "alloy"

# 結合後の日本語音声 / 動画ファイル名
VIDEO_TTS_JA_ALL_FILENAME   = f"video_tts_ja_all.mp3"   # 例: ja.mp3
VIDEO_JA_FINAL_FILENAME     = f"video_ja_final.mp4"

# ベース画像サイズ（固定なら定数でOK）
VIDEO_THUMB_BASE_W = 1920
VIDEO_THUMB_BASE_H = 1080

# サムネ（画面）用テキストオーバーレイ設定
OVERLAY_FONT_PATH       = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
OVERLAY_FONT2_PATH      = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
VIDEO_THUMB_FINAL_NAME  = "video_thumb_final.png"

# ヘッダーテキストの描画設定
OVERLAY_HEADER_POINTSIZE   = 120
OVERLAY_HEADER_FILL        = "#111111"  # 濃いグレー（黒より少し柔らかい）
OVERLAY_HEADER_STROKE      = "#cccccc"  # 白い縁取り
OVERLAY_HEADER_STROKEWIDTH = 20
OVERLAY_HEADER_POS         = "-520+172"    # -gravity North 基準の x+y 位置（そのまま文字列で使用）

# タイトルテキストの描画設定
OVERLAY_TITLE_POINTSIZE    = 160
OVERLAY_TITLE_FILL         = "#ffb347"  # 明るいオレンジ
OVERLAY_TITLE_STROKE       = "#40210f"  # 濃い茶色っぽい枠線
OVERLAY_TITLE_STROKEWIDTH  = 26
# ベース位置は X/Y を分けて持つ（Y にオフセットを加算する）
OVERLAY_TITLE_POS_X        = -520
OVERLAY_TITLE_POS_Y        = 308        # -gravity North 基準のベース Y
OVERLAY_TITLE_LINE_SPACING = 0          # 行間

# URLの描画設定
OVERLAY_URL_POINTSIZE    = 80
OVERLAY_URL_FILL         = "#000000"
OVERLAY_URL_STROKE       = "#cccccc"
OVERLAY_URL_STROKEWIDTH  = 20
OVERLAY_URL_POS         = "-520+1888"

# 取得した YouTube サムネイル画像
VIDEO_THUMB_SRC_FILENAME   = "video_thumb_src.jpg"
OVERLAY_THUMB_RESIZE     = "x810"     # サムネサイズ

# サムネの中心を置きたい座標（画面左上原点）
OVERLAY_THUMB_CENTER_X = 1404
OVERLAY_THUMB_CENTER_Y = 1480

OVERLAY_THUMB_DX = OVERLAY_THUMB_CENTER_X - (VIDEO_THUMB_BASE_W * 2) // 2
OVERLAY_THUMB_DY = OVERLAY_THUMB_CENTER_Y - (VIDEO_THUMB_BASE_H * 2) // 2

OVERLAY_THUMB_GRAVITY = "Center"
OVERLAY_THUMB_GEOMETRY = f"{OVERLAY_THUMB_DX:+d}{OVERLAY_THUMB_DY:+d}"

# 最終 mp4 / 画像 コピー先
FINAL_COPY_DIR = Path(f"{OUTPUT_BASE_DIR}")

VIDEO_THUMB_BG  = "chobi_screen_yt_fukikae_x2.png"


# ===== ユーティリティ関数 =====
def run_command(cmd: list[str], *, stdout=None, stderr=None) -> None:
    """サブプロセスでコマンドを実行する共通関数。"""
    printable = " ".join(shlex.quote(str(c)) for c in cmd)
    print("[RUN]", printable)
    try:
        subprocess.run(cmd, check=True, stdout=stdout, stderr=stderr)
        print("[OK ]", printable)
    except subprocess.CalledProcessError as e:
        print(f"[ERR] returncode={e.returncode}")
        raise


def prepare_output_dir(path_str: str) -> Path:
    """出力ディレクトリを Path 化し、なければ作成して返す。"""
    output_dir = Path(path_str).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


# ===== 音声ダウンロード =====
def download_audio(urls: list[str], output_dir: Path) -> Path:
    """YouTube から音声をダウンロードして original.m4a を作成。"""
    ydl_opts = {
        "format": "m4a/bestaudio/best",
        "outtmpl": str(output_dir / f"{AUDIO_BASENAME}.%(ext)s"),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": AUDIO_CODEC,
            }
        ],
    }

    print("[STEP] Download audio via yt-dlp")
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        _error_code = ydl.download(urls)

    return output_dir / f"{AUDIO_BASENAME}.{AUDIO_CODEC}"


# ===== サムネイル取得 =====
def _extract_video_id(url: str) -> str | None:
    """YouTube URL から 11 桁の動画IDを取り出す。"""
    patterns = [
        r"v=([0-9A-Za-z_-]{11})",          # watch?v=ID
        r"youtu\.be/([0-9A-Za-z_-]{11})",  # youtu.be/ID
        r"shorts/([0-9A-Za-z_-]{11})",     # shorts/ID
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def download_thumbnail(urls: list[str], output_dir: Path) -> Path | None:
    """
    最初の URL から動画IDを取り出し、サムネイル画像を取得する。
    優先順位: maxresdefault -> sddefault -> hqdefault
    保存先: {output_dir}/thumbnail.jpg
    """
    if not urls:
        print("[THUMB] No URLs given, skip thumbnail download.")
        return None

    url = urls[0]
    vid = _extract_video_id(url)
    if not vid:
        print(f"[THUMB] Could not extract video id from URL: {url}")
        return None

    sizes = ["maxresdefault", "sddefault", "hqdefault"]
    dest_path = output_dir / VIDEO_THUMB_SRC_FILENAME

    for size in sizes:
        thumb_url = f"https://img.youtube.com/vi/{vid}/{size}.jpg"
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

        dest_path.write_bytes(data)
        print(f"[THUMB] Saved thumbnail -> {dest_path}")
        return dest_path

    print("[THUMB] No available thumbnail found.")
    return None


# ===== 変換 =====
def convert_to_small_webm(input_file: Path, output_file: Path) -> None:
    """original.m4a を 16kHz/32kbps Opus (webm) に変換（常に上書き）。"""
    print("[STEP] Convert audio to small webm (16kHz / 32kbps / mono)")

    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(input_file),
        "-ac", "1",
        "-ar", "16000",
        "-c:a", "libopus",
        "-b:a", "32k",
        str(output_file),
    ]
    run_command(cmd)
    print("[DONE]", output_file)


# ===== 無音検出 & 分割 =====
def _detect_silence(input_file: Path, log_file: Path) -> None:
    """無音部分を検出し、ログファイルに書き出す（低レベル関数）。"""
    print("[STEP] Detect silence")
    print("[LOG ] ->", log_file)

    silence_filter = (
        f"silencedetect=noise={SILENCE_NOISE_DB}dB:"
        f"d={SILENCE_MIN_LENGTH}"
    )

    cmd = [
        "ffmpeg",
        "-i", str(input_file),
        "-af", silence_filter,
        "-f", "null",
        "-",
    ]

    with log_file.open("w", encoding="utf-8") as f:
        run_command(cmd, stdout=subprocess.DEVNULL, stderr=f)

    print("[DONE] Silence log:", log_file)


def _split_by_silence(input_file: Path, log_file: Path, output_dir: Path) -> None:
    """無音情報ログを使って音声を分割する（低レベル関数）。"""
    print("[STEP] Split audio by silence")
    print("[OUT ] ->", output_dir)

    cmd = [
        "python",
        "split_by_silence.py",
        "-i", str(input_file),
        "-l", str(log_file),
        "-o", str(output_dir),
        "--part-prefix", VIDEO_AUDIO_SRC_CHANK_PREFIX,
        "--min-segment", str(SILENCE_MIN_SEGMENT),
        "--max-segment", str(SILENCE_MAX_SEGMENT),
    ]

    run_command(cmd)
    print("[DONE] Split by silence")


def detect_and_split_by_silence(input_file: Path, output_dir: Path) -> None:
    """無音検出～分割までをひとまとまりで実行する高レベル関数。"""
    log_file = output_dir / SILENCE_LOG_FINEMANE
    _detect_silence(input_file, log_file)
    _split_by_silence(input_file, log_file, output_dir)


# ===== 文字起こし =====
def transcribe_segments(output_dir: Path, model: str = TRANSCRIBE_MODEL) -> None:
    print("[STEP] Transcribe segments with s2t_multi.py")
    cmd = [
        "python",
        "s2t_multi.py",
        str(output_dir),
        "--model",
        model,
        "--part-prefix",
        VIDEO_AUDIO_SRC_CHANK_PREFIX,
        "--text-prefix",
        TRANSCRIPT_TEXT_PREFIX,
    ]
    run_command(cmd)
    print("[DONE] Transcription")


# ===== 日本語訳 =====
def translate_to_japanese(output_dir: Path, model: str = TRANSLATE_MODEL) -> None:
    print("[STEP] Translate English texts to Japanese with translate_2ja_batch.py")
    cmd = [
        "python",
        "translate_to_ja.py",
        str(output_dir),
        "--model",
        model,
        "--text-prefix",
        TRANSCRIPT_TEXT_PREFIX,
        "--translated-prefix",
        TRANSCRIPT_JA_PREFIX,
        "--combined-name",
        TRANSCRIPT_JA_ALL_FILENAME,
    ]
    try:
        run_command(cmd)
    except subprocess.CalledProcessError:
        # ここで「翻訳で失敗したから後続をやらない」と明示
        print("[FATAL] Translation step failed. Abort remaining pipeline.")
        raise
    print("[DONE] Translation")


# ===== 日本語テキスト分割 =====
def split_japanese_texts(output_dir: Path, max_chars: int = MAX_JA_CHARS) -> None:
    print("[STEP] Split Japanese texts with split_combined_ja.py")
    cmd = [
        "python",
        "split_ja.py",
        str(output_dir),
        "--max-chars",
        str(max_chars),
        "--input-name",
        TRANSCRIPT_JA_ALL_FILENAME,
        "--output-basename",
        SCRIPT_JA_PREFIX,
    ]
    run_command(cmd)
    print("[DONE] Split Japanese texts")


# ===== 読み上げファイル生成 =====
def generate_tts_files(output_dir: Path, tts_model: str, tts_voice: str) -> None:
    print("[STEP] Generate TTS audio files with tts_from_parts.py")
    cmd = [
        "python",
        "tts_ja.py",
        str(output_dir),
        "--prefix",
        SCRIPT_JA_PREFIX,
        "--model",
        tts_model,
        "--voice",
        tts_voice,
        "--instructions",
        "落ち着いたニュースキャスターのように、はっきりと読み上げてください。",
    ]
    run_command(cmd)
    print("[DONE] Generate TTS audio files")


# ===== 読み上げファイル結合 =====
def merge_tts_files(output_dir: Path) -> None:
    print("[STEP] Merge TTS audio files with merge_mp3_parts.py")
    cmd = [
        "python",
        "merge_ja_audio.py",
        str(output_dir),
        "--prefix",
        SCRIPT_JA_PREFIX,
        "--output",
        VIDEO_TTS_JA_ALL_FILENAME,
    ]
    run_command(cmd)
    print("[DONE] Merge TTS audio files")


# ===== 画像にテキスト & サムネを焼き込んだコピーを作成 =====
def _format_title_pos(y_offset: int) -> str:
    """
    OVERLAY_TITLE_POS_X, OVERLAY_TITLE_POS_Y と y_offset から
    ImageMagick 用位置文字列（例: '-260+210'）を作る。
    """
    x = OVERLAY_TITLE_POS_X
    y = OVERLAY_TITLE_POS_Y + y_offset
    # %+d で符号付き整数にし、x と y をつなげる（例: -260+210 / -260-50）
    return f"{x:+d}{y:+d}"


def create_video_thumb_final(
    output_dir: Path,
    video_thumb_src_path: Path,
    header_text: str,
    title_text: str,
    title_pointsize: int,
    title_line_spacing: int,
    title_offset_y: int,
    title_strokewidth: int,
    video_url: str | None = None,
) -> Path | None:
    """
    ベースの背景画像にテキストと YouTube サムネを描画した画像を {DIR} 配下に作成する。
    戻り値: 生成した画像パス（失敗時は None）
    """
    print("[STEP] Create overlay image with text & thumbnail")

    base_image = Path(VIDEO_THUMB_BG)
    if not base_image.exists():
        print(f"[WARN] Base image not found: {base_image}")
        return None

    output_image = output_dir / VIDEO_THUMB_FINAL_NAME

    title_pos_str = _format_title_pos(title_offset_y)

    print("[OVERLAY] Base image   :", base_image)
    print("[OVERLAY] Output image :", output_image)
    print("[OVERLAY] Font         :", OVERLAY_FONT_PATH)
    print("[OVERLAY] HEader text  :",
          f"'{header_text}' size={OVERLAY_HEADER_POINTSIZE} pos={OVERLAY_HEADER_POS}")
    print("[OVERLAY] Title text   :",
          f"'{title_text}' size={title_pointsize} pos={title_pos_str}")
    print("[OVERLAY] Title color  :", OVERLAY_TITLE_FILL)
    print("[OVERLAY] Title offsetY:", title_offset_y)
    print("[OVERLAY] Title strokewidth:", title_strokewidth)
    print("[OVERLAY] Thumbnail    :", video_thumb_src_path if video_thumb_src_path.exists() else "NONE")
    if video_url:
        print("[OVERLAY] Video URL    :", video_url)

    cmd: list[str] = [
        "convert",
        str(base_image),
        "-gravity", "North",
    ]

    # ヘッダーテキストがあれば描画
    if header_text:
        cmd.extend([
            "-font", OVERLAY_FONT2_PATH,
            "-pointsize", str(OVERLAY_HEADER_POINTSIZE),
            "-fill", OVERLAY_HEADER_FILL,
            "-stroke", OVERLAY_HEADER_STROKE,
            "-strokewidth", str(OVERLAY_HEADER_STROKEWIDTH),
            "-annotate", OVERLAY_HEADER_POS, header_text,
            "-strokewidth", str(0),
            "-annotate", OVERLAY_HEADER_POS, header_text,
        ])

    # タイトルテキストがあれば描画
    if title_text:
        cmd.extend([
            "-font", OVERLAY_FONT_PATH,
            "-pointsize", str(title_pointsize),
            "-fill", OVERLAY_TITLE_FILL,
            "-stroke", OVERLAY_TITLE_STROKE,
            "-strokewidth", str(title_strokewidth),
            "-interline-spacing", str(title_line_spacing),
            "-annotate", title_pos_str, title_text,
            "-strokewidth", str(0),
            "-annotate", title_pos_str, title_text,
        ])

    # 元動画URLテキスト
    if video_url:
        cmd.extend([
            "-font", OVERLAY_FONT2_PATH,
            "-pointsize", str(OVERLAY_URL_POINTSIZE),
            "-fill", OVERLAY_URL_FILL,
            "-stroke", OVERLAY_URL_STROKE,
            "-strokewidth", str(OVERLAY_URL_STROKEWIDTH),
            "-annotate", OVERLAY_URL_POS, video_url,
            "-strokewidth", str(0),
            "-annotate", OVERLAY_URL_POS, video_url,
        ])

    # サムネイルがあれば左下に合成
    if video_thumb_src_path.exists():
        cmd.extend([
            "(",
            str(video_thumb_src_path),
            "-resize", OVERLAY_THUMB_RESIZE,
            ")",
            "-gravity", OVERLAY_THUMB_GRAVITY,
            "-geometry", OVERLAY_THUMB_GEOMETRY,
            "-composite",
        ])
    else:
        print("[OVERLAY] Thumbnail not found, skip composite.")

    # 最終出力解像度を固定（1920x1080）
    cmd.extend([
        "-filter", "Lanczos",
        "-resize", f"{VIDEO_THUMB_BASE_W}x{VIDEO_THUMB_BASE_H}"
    ])

    cmd.append(str(output_image))

    run_command(cmd)
    print("[DONE] Overlay image:", output_image)
    return output_image


# ===== mp3 + 画像 -> mp4 =====
def create_video_from_audio(
    output_dir: Path,
    header_text: str,
    title_text: str,
    title_pointsize: int,
    title_line_spacing: int,
    title_offset_y: int,
    title_strokewidth: int,
    video_url: str | None = None,
) -> Path | None:
    """
    {DIR}/combined_ja_merged.mp3 と オーバーレイ画像 を使って
    {DIR}/combined_ja_merged.mp4 を生成する。
    戻り値: 生成した mp4 のパス（失敗時は None）
    """
    print("[STEP] Create MP4 video from audio and image")

    audio_file = output_dir / VIDEO_TTS_JA_ALL_FILENAME
    if not audio_file.exists():
        print(f"[WARN] Audio file not found: {audio_file}")
        return None

    video_thumb_final = create_video_thumb_final(
        output_dir,
        Path(output_dir / VIDEO_THUMB_SRC_FILENAME),
        header_text,
        title_text,
        title_pointsize,
        title_line_spacing,
        title_offset_y,
        title_strokewidth,
        video_url=video_url,
    )
    if video_thumb_final is None:
        print("[WARN] Overlay image creation failed. Skip video generation.")
        return None

    output_file = output_dir / VIDEO_JA_FINAL_FILENAME

    cmd = [
        "ffmpeg",
        "-y",
        "-loop", "1",
        "-i", str(video_thumb_final),
        "-i", str(audio_file),
        "-c:v", "libx264",
        "-tune", "stillimage",
        "-c:a", "aac",
        "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-shortest",
        str(output_file),
    ]
    run_command(cmd)
    print("[DONE] Create video:", output_file)
    return output_file, video_thumb_final


# ===== 生成した mp4 をコピー =====
def copy_final_video(output_dir: Path, video_path: Path, final_copy_dir: Path) -> None:
    if not video_path.exists():
        print(f"[WARN] Final video not found, skip copy: {video_path}")
        return

    dir_name = output_dir.name
    dest_dir = final_copy_dir
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest_path = dest_dir / f"{dir_name}_{VIDEO_JA_FINAL_FILENAME}"

    print(f"[STEP] Copy final video to Windows: {dest_path}")
    try:
        shutil.copy2(video_path, dest_path)
        print(f"[DONE] Copied to: {dest_path}")
    except OSError as e:
        print(f"[ERROR] Failed to copy video: {e}")


# ===== 生成した画像を指定のパスにコピー =====
def copy_video_thumb_final(output_dir: Path, image_path: Path, final_copy_dir: Path) -> None:
    if not image_path.exists():
        print(f"[WARN] Overlay image not found, skip copy: {image_path}")
        return

    dir_name = output_dir.name
    dest_dir = final_copy_dir
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest_path = dest_dir / f"{dir_name}_{VIDEO_THUMB_FINAL_NAME}"

    print(f"[STEP] Copy overlay image to Windows: {dest_path}")
    try:
        shutil.copy2(image_path, dest_path)
        print(f"[DONE] Copied overlay image to: {dest_path}")
    except OSError as e:
        print(f"[ERROR] Failed to copy overlay image: {e}")


# ===== 引数処理・エントリポイント =====
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "YouTubeから音声をダウンロードし、変換・無音検出・分割・文字起こし・"
            "日本語訳・テキスト分割・読み上げ生成・結合・mp4生成まで行います。"
        )
    )

    parser.add_argument(
        "video_id",
        help="処理する YouTube 動画のID（例: dQw4w9WgXcQ）",
    )
    parser.add_argument(
        "--name",
        required=True,
        help="output/ 配下に作成する作業ディレクトリ名",
    )
    parser.add_argument(
        "--header-text",
        default="",
        help="サムネイルの上部に載せるテキスト",
    )
    parser.add_argument(
        "--title-text",
        default="",
        help="サムネイルに載せるタイトルテキスト",
    )
    parser.add_argument(
        "--title-pointsize",
        type=int,
        default=OVERLAY_TITLE_POINTSIZE,
        help="タイトル文字のポイントサイズ（デフォルト: %(default)s）",
    )
    parser.add_argument(
        "--title-line-spacing",
        type=int,
        default=OVERLAY_TITLE_LINE_SPACING,
        help="タイトル行間（ImageMagickの -interline-spacing、デフォルト: %(default)s）",
    )
    parser.add_argument(
        "--title-offset-y",
        type=int,
        default=0,
        help="タイトルの上下位置オフセット（ピクセル, 正で下, 負で上）",
    )
    parser.add_argument(
        "--title-strokewidth",
        type=int,
        default=OVERLAY_TITLE_STROKEWIDTH,
        help="タイトル縁取りの太さ（ImageMagick の -strokewidth、デフォルト: %(default)s）",
    )
    parser.add_argument(
        "--no-draw-url",
        action="store_true",
        help="サムネイルにYouTubeのURLを描画しない",
    )
    parser.add_argument(
        "--input-thumbnail",
        type=str,
        help="YouTubeからDLせず、このローカル画像ファイルをサムネイルとして使う（例: /path/to/image.jpg）",
    )
    parser.add_argument(
        "--input-audio",
        type=str,
        help="YouTubeからDLせず、このローカル音声ファイルを入力として使う（例: /path/to/audio.m4a）",
    )
    parser.add_argument(
        "--translate-model",
        default=TRANSLATE_MODEL,
        help="日本語訳に使うモデル名（デフォルト: %(default)s）",
    )
    parser.add_argument(
        "--transcribe-model",
        default=TRANSCRIBE_MODEL,
        help="文字起こしに使うモデル名（デフォルト: %(default)s）",
    )
    parser.add_argument(
        "--tts-model",
        default=TTS_MODEL_DEFAULT,
        help="TTS 音声生成に使うモデル名（デフォルト: %(default)s）",
    )
    parser.add_argument(
        "--tts-voice",
        default=TTS_VOICE_DEFAULT,
        help="TTS 音声生成に使うボイス名（デフォルト: %(default)s）",
    )
    parser.add_argument(
        "--final-copy-dir",
        default=str(FINAL_COPY_DIR),
        help="最終 mp4 / 画像 のコピー先ディレクトリ（デフォルト: %(default)s）",
    )
    parser.add_argument(
        "--image-only",
        action="store_true",
        help="音声処理を行わず、サムネイルだけを生成する",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    final_copy_dir = Path(args.final_copy_dir).expanduser()

    # 動画IDからフルURLと短縮URLを生成
    video_id = args.video_id
    youtube_url = f"https://www.youtube.com/watch?v={video_id}"
    youtube_short_url = f"https://youtu.be/{video_id}"

    # 1. 出力ディレクトリ準備
    output_dir = prepare_output_dir(OUTPUT_BASE_DIR / args.name)

    # Noneを渡すと create_video_thumb_final 側で描画がスキップされる
    url_text_for_thumb = None if args.no_draw_url else youtube_short_url

    # 1.1 すでに存在する場合は丸ごと削除（中身をクリア）
    if output_dir.exists():
        print(f"[CLEAN] Remove existing directory: {output_dir}")
        shutil.rmtree(output_dir)

    # 1.2 再作成（親の output/ がなければ一緒に作られる）
    output_dir = prepare_output_dir(output_dir)

    # 1.5 サムネイル取得（画像だけモードでも使うので先に実行）
    if args.input_thumbnail:
        print(f"[MODE] local-thumbnail: ローカル画像ファイルを使用します: {args.input_thumbnail}")
        src_thumb = Path(args.input_thumbnail).expanduser()
        if not src_thumb.exists():
            raise FileNotFoundError(f"Input thumbnail file not found: {src_thumb}")

        # パイプラインが期待するファイル名 (video_thumb_src.jpg) にリネーム/コピーして配置
        dest_thumb = output_dir / VIDEO_THUMB_SRC_FILENAME
        shutil.copy2(src_thumb, dest_thumb)
        print(f"[COPY] Copied local thumbnail to: {dest_thumb}")
    else:
        # 指定がなければ通常通りYouTubeからDL
        download_thumbnail([youtube_url], output_dir)

    # === 画像だけ作るモード ===================================
    if args.image_only:
        print("[MODE] image-only: オーバーレイ画像だけ生成します。")
        video_thumb_final = create_video_thumb_final(
            output_dir,
            Path(output_dir / VIDEO_THUMB_SRC_FILENAME),
            args.header_text,
            args.title_text,
            args.title_pointsize,
            args.title_line_spacing,
            args.title_offset_y,
            args.title_strokewidth,
            video_url=url_text_for_thumb,
        )
        if video_thumb_final is not None:
            print(f"[RESULT] Overlay image created: {video_thumb_final}")
            copy_video_thumb_final(output_dir, video_thumb_final, final_copy_dir)
        return
    # ========================================================

    # 2. 音声入力の決定
    if args.input_audio:
        print("[MODE] local-audio: ローカル音声ファイルを使用します。")
        original_m4a = Path(args.input_audio).expanduser()
        if not original_m4a.exists():
            raise FileNotFoundError(f"Input audio file not found: {original_m4a}")
    else:
        # YouTube から音声ダウンロード
        # こちらも download_audio が URLのリストを想定しているなら同様にラップ
        original_m4a = download_audio([youtube_url], output_dir)

    # 3. サイズ削減版を作成
    small_webm = output_dir / AUDIO_SMALL_NAME
    convert_to_small_webm(original_m4a, small_webm)

    # 4. 無音検出～分割
    detect_and_split_by_silence(small_webm, output_dir)

    # 5. 文字起こし
    transcribe_segments(output_dir, args.transcribe_model)

    # 6. 日本語訳
    translate_to_japanese(output_dir, args.translate_model)

    # 7. 日本語ファイルを文字数指定で分割
    split_japanese_texts(output_dir, MAX_JA_CHARS)

    # 8. 読み上げファイル生成
    generate_tts_files(output_dir, args.tts_model, args.tts_voice)

    # 9. 読み上げファイルを結合
    merge_tts_files(output_dir)

    # 10. 動画生成
    # ※ create_video_from_audio 側で create_video_thumb_final を呼ぶときに
    #    video_url=youtube_short_url を渡すよう、そちらの定義も合わせて変更すると
    #    通常モードのサムネも短縮URLになります。
    video_final, video_thumb_final = create_video_from_audio(
        output_dir,
        args.header_text,
        args.title_text,
        args.title_pointsize,
        args.title_line_spacing,
        args.title_offset_y,
        args.title_strokewidth,
        video_url=url_text_for_thumb,
    )

    # 11. 最終ファイルをコピー
    if video_final is not None:
        copy_final_video(output_dir, video_final, final_copy_dir)
    if video_thumb_final is not None:
        copy_video_thumb_final(output_dir, video_thumb_final, final_copy_dir)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        # translate_2ja_batch.py が sys.exit(1) したときもここに来る
        print(
            f"[FATAL] サブプロセス実行中にエラーが発生したため処理を中断します。"
            f" returncode={e.returncode}"
        )
        sys.exit(e.returncode or 1)
    except Exception as e:
        # 想定外のエラー（バグ・環境問題など）
        print(f"[FATAL] 予期しないエラーで処理を中断します: {e}")
        sys.exit(1)