#!/usr/bin/env python3
"""
make_final_video.py

背景画像 + テキスト + 音声ファイル から 1枚絵の mp4 動画を作成します。
--image-only オプションを付けると、サムネ画像（テキスト合成済みPNG）だけを生成します。

URL を --url オプションで渡すと、画面下部に URL を描画します。

さらに --embed-video で元動画のパスを渡すと、
サムネとURLの間に元動画の映像だけ（音声なし）をピクチャーインピクチャーで埋め込みます。

★追加:
--thumb-image で渡した画像を video_thumb_final.png 内に貼り込みます。
--output-video, --output-thumb で動画とサムネの保存ファイル名を個別に指定できます。
"""

import argparse
import subprocess
import sys
from pathlib import Path
import shlex


# ===== 設定系（このスクリプトで実際に使うものだけ） =====

# 出力解像度
VIDEO_THUMB_BASE_W = 1920
VIDEO_THUMB_BASE_H = 1080

# デフォルトファイル名
VIDEO_THUMB_FINAL_NAME = "video_thumb_final.png"
VIDEO_JA_FINAL_FILENAME = "video_ja_final.mp4"

# フォント
OVERLAY_FONT_PATH = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
# ★修正: ヘッダーも日本語が表示できるように同じフォントを指定します
OVERLAY_FONT2_PATH = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"

# ヘッダーテキストの描画設定
OVERLAY_HEADER_POINTSIZE = 120
OVERLAY_HEADER_FILL = "#111111"   # 濃いグレー（黒より少し柔らかい）
OVERLAY_HEADER_STROKE = "#cccccc" # 白い縁取り
OVERLAY_HEADER_STROKEWIDTH = 20
OVERLAY_HEADER_POS = "-520+172"   # -gravity North 基準の x+y 位置

# タイトルテキストの描画設定
OVERLAY_TITLE_POINTSIZE = 180
OVERLAY_TITLE_FILL = "#ffb347"    # 明るいオレンジ
OVERLAY_TITLE_STROKE = "#40210f"  # 濃い茶色っぽい枠線
OVERLAY_TITLE_STROKEWIDTH = 26
OVERLAY_TITLE_POS_X = -520        # テキストのX中心位置
OVERLAY_TITLE_POS_Y = 320         # -gravity North 基準のベース Y
OVERLAY_TITLE_LINE_SPACING = -30    # 行間

# サムネイル画像のX位置調整（テキスト座標の半分を指定）
OVERLAY_THUMB_POS_X = -260

# URL の描画設定
OVERLAY_URL_POINTSIZE = 80
OVERLAY_URL_FILL = "#000000"
OVERLAY_URL_STROKE = "#cccccc"
OVERLAY_URL_STROKEWIDTH = 20
OVERLAY_URL_POS = "-520+1888"

# ピクチャーインピクチャー用の埋め込み動画サイズ＆位置
EMBED_VIDEO_WIDTH = 720    # 16:9 固定（サムネ用）
EMBED_VIDEO_HEIGHT = 405   # 高さ固定

# Y座標の設定
EMBED_CENTER_Y = 740
EMBED_VIDEO_Y = EMBED_CENTER_Y - EMBED_VIDEO_HEIGHT // 2    # 740 - 202 ≒ 538

# ===== ユーティリティ =====

def run_command(cmd: list[str]) -> None:
    """サブプロセスでコマンドを実行するだけの簡単なヘルパー。"""
    printable = " ".join(shlex.quote(str(c)) for c in cmd)
    print("[RUN]", printable)
    try:
        subprocess.run(cmd, check=True)
        print("[OK ]", printable)
    except subprocess.CalledProcessError as e:
        print(f"[ERR] command failed (returncode={e.returncode})")
        raise


def _format_title_pos(y_offset: int) -> str:
    """
    OVERLAY_TITLE_POS_X, OVERLAY_TITLE_POS_Y と y_offset から
    ImageMagick 用位置文字列（例: '-260+210'）を作る。
    """
    x = OVERLAY_TITLE_POS_X
    y = OVERLAY_TITLE_POS_Y + y_offset
    return f"{x:+d}{y:+d}"


# ===== 背景 + テキスト (+ 画像) → オーバーレイ画像 =====

def create_overlay_image(
    base_image: Path,
    header_text: str,
    title_text: str,
    title_pointsize: int,
    title_line_spacing: int,
    title_offset_y: int,
    title_strokewidth: int,
    output_path: Path,
    video_url: str | None = None,
    thumb_image: Path | None = None,
) -> Path | None:
    """
    ベースの背景画像にヘッダー・タイトル・URLテキストを描画して output_path に保存する。
    thumb_image が指定されていれば、あとから指定位置に貼り込む。

    戻り値: 生成した画像パス（失敗時は None）
    """
    print("[STEP] Create overlay image with text")

    if not base_image.exists():
        print(f"[WARN] Base image not found: {base_image}")
        return None

    title_pos_str = _format_title_pos(title_offset_y)

    print("[OVERLAY] Base image   :", base_image)
    print("[OVERLAY] Output image :", output_path)
    print("[OVERLAY] Font title   :", OVERLAY_FONT_PATH)
    print("[OVERLAY] Font header  :", OVERLAY_FONT2_PATH)
    print("[OVERLAY] Header text  :",
          f"'{header_text}' size={OVERLAY_HEADER_POINTSIZE} pos={OVERLAY_HEADER_POS}")
    print("[OVERLAY] Title text   :",
          f"'{title_text}' size={title_pointsize} pos={title_pos_str}")
    if video_url:
        print("[OVERLAY] Video URL   :",
              f"'{video_url}' size={OVERLAY_URL_POINTSIZE} pos={OVERLAY_URL_POS}")
    print("[OVERLAY] Title color  :", OVERLAY_TITLE_FILL)
    print("[OVERLAY] Title offsetY:", title_offset_y)
    print("[OVERLAY] Title strokewidth:", title_strokewidth)

    # まずは「テキストだけ」を元のやり方で合成
    cmd: list[str] = [
        "convert",
        str(base_image),
        "-gravity", "North",
    ]

    # ヘッダーテキスト
    if header_text:
        cmd.extend([
            "-font", OVERLAY_FONT2_PATH,
            "-pointsize", str(OVERLAY_HEADER_POINTSIZE),
            "-fill", OVERLAY_HEADER_FILL,
            "-stroke", OVERLAY_HEADER_STROKE,
            "-strokewidth", str(OVERLAY_HEADER_STROKEWIDTH),
            "-annotate", OVERLAY_HEADER_POS, header_text,
            "-strokewidth", "0",
            "-annotate", OVERLAY_HEADER_POS, header_text,
        ])

    # タイトルテキスト
    if title_text:
        cmd.extend([
            "-font", OVERLAY_FONT_PATH,
            "-pointsize", str(title_pointsize),
            "-fill", OVERLAY_TITLE_FILL,
            "-stroke", OVERLAY_TITLE_STROKE,
            "-strokewidth", str(title_strokewidth),
            "-interline-spacing", str(title_line_spacing),
            "-annotate", title_pos_str, title_text,
            "-strokewidth", "0",
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
            "-strokewidth", "0",
            "-annotate", OVERLAY_URL_POS, video_url,
        ])

    # 最終出力解像度を固定（1920x1080）
    cmd.extend([
        "-filter", "Lanczos",
        "-resize", f"{VIDEO_THUMB_BASE_W}x{VIDEO_THUMB_BASE_H}",
        str(output_path),
    ])

    run_command(cmd)
    print("[DONE] Overlay image (text only):", output_path)

    # ここから YouTube サムネ画像を貼り込む
    if thumb_image is not None:
        if not thumb_image.exists():
            print(f"[WARN] Thumb image not found: {thumb_image} (サムネ合成をスキップします)")
            return output_path

        print("[STEP] Add thumb image into overlay")
        
        # 定数 OVERLAY_THUMB_POS_X を使用して配置
        cmd2: list[str] = [
            "convert",
            str(output_path),
            "(",
            str(thumb_image),
            "-filter", "Lanczos",
            "-resize", f"{EMBED_VIDEO_WIDTH}x{EMBED_VIDEO_HEIGHT}",
            ")",
            "-gravity", "North", # 背景画像の中心(North基準)
            "-geometry", f"{OVERLAY_THUMB_POS_X:+d}+{EMBED_VIDEO_Y}",
            "-compose", "over",
            "-composite",
            str(output_path),
        ]
        run_command(cmd2)
        print("[DONE] Thumb image composited:", output_path)

    return output_path


# ===== オーバーレイ画像 + （埋め込み動画） + 音声 → 動画 =====

def create_video_from_audio(
    image_path: Path,
    audio_path: Path,
    output_path: Path,
    embed_video_path: Path | None = None,
) -> None:
    """
    1枚絵 image_path と audio_path から mp4 を生成する。
    embed_video_path が指定されていれば、その映像を中央付近にピクチャーインピクチャーで埋め込む。
    （埋め込み動画の音声は使用しない）
    """
    print("[STEP] Create MP4 video from audio and image")

    if embed_video_path is not None and embed_video_path.exists():
        print(f"[INFO] 埋め込み動画を使用します: {embed_video_path}")
        # 0: 背景サムネ（ループ）
        # 1: オリジナル動画（映像だけ使う、ループ）
        # 2: TTS 音声

        # ffmpegの計算式でも OVERLAY_THUMB_POS_X を使用
        # x = (画面中央 + 画像用オフセット) - 動画幅/2
        filter_complex = (
            f"[1:v]scale=-2:{EMBED_VIDEO_HEIGHT}[embed];"
            f"[0:v][embed]overlay="
            f"x=(W/2+{OVERLAY_THUMB_POS_X})-w/2:"
            f"y={EMBED_VIDEO_Y}[outv]"
        )

        cmd = [
            "ffmpeg",
            "-y",
            "-loop", "1",
            "-i", str(image_path),
            "-stream_loop", "-1",
            "-i", str(embed_video_path),
            "-i", str(audio_path),
            "-filter_complex", filter_complex,
            "-map", "[outv]",
            "-map", "2:a",
            "-c:v", "libx264",
            "-tune", "stillimage",
            "-c:a", "aac",
            "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-shortest",
            str(output_path),
        ]
    else:
        if embed_video_path is not None:
            print(f"[WARN] 埋め込み動画が見つかりませんでした: {embed_video_path}  -> 通常の静止画動画として作成します。")

        cmd = [
            "ffmpeg",
            "-y",
            "-loop", "1",
            "-i", str(image_path),
            "-i", str(audio_path),
            "-c:v", "libx264",
            "-tune", "stillimage",
            "-c:a", "aac",
            "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-shortest",
            str(output_path),
        ]

    run_command(cmd)
    print("[DONE] Create video:", output_path)


# ===== 引数処理・エントリポイント =====

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "背景画像にテキストを合成し、その画像と音声から1枚絵のmp4動画を生成します。"
            " --image-only を指定するとサムネ画像だけを生成します。"
        ),
    )

    # 必須: 背景画像 & 音声ファイル
    parser.add_argument(
        "image",
        help="背景画像ファイル (png, jpg など)",
    )
    parser.add_argument(
        "audio",
        help="音声ファイル (mp3, wav, m4a など ffmpeg が読めるもの)",
    )

    # テキスト
    parser.add_argument(
        "--header",
        default="",
        help="ヘッダーテキスト（上部に表示するテキスト）",
    )
    parser.add_argument(
        "--title",
        default="",
        help="タイトルテキスト（中央付近に表示するテキスト）",
    )
    parser.add_argument(
        "--url",
        default="",
        help="サムネに描画するURLテキスト（例: https://youtu.be/XXXXXXX）",
    )

    # サムネに貼り込む画像（YouTubeサムネなど）
    parser.add_argument(
        "--embed-thumb",
        help="video_thumb_final.png に貼り込む別画像ファイルのパス（任意）",
    )

    # 出力ファイル（個別指定）
    parser.add_argument(
        "--output-video",
        help=f"出力する mp4 ファイルパス（省略時は ./ {VIDEO_JA_FINAL_FILENAME}）",
    )
    parser.add_argument(
        "--output-thumb",
        help=f"出力するサムネ画像ファイルパス（省略時は ./ {VIDEO_THUMB_FINAL_NAME}）",
    )

    # 埋め込み動画
    parser.add_argument(
        "--embed-video",
        help="サムネに埋め込む元動画ファイルのパス（映像のみ使用、音声は使用しない）",
    )

    # タイトル描画の細かい調整
    parser.add_argument(
        "--title-pointsize",
        type=int,
        default=OVERLAY_TITLE_POINTSIZE,
        help=f"タイトル文字のポイントサイズ（デフォルト: {OVERLAY_TITLE_POINTSIZE}）",
    )
    parser.add_argument(
        "--title-line-spacing",
        type=int,
        default=OVERLAY_TITLE_LINE_SPACING,
        help=f"タイトル行間（ImageMagick -interline-spacing, デフォルト: {OVERLAY_TITLE_LINE_SPACING}）",
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
        help=f"タイトル縁取りの太さ（デフォルト: {OVERLAY_TITLE_STROKEWIDTH}）",
    )

    # サムネだけ生成するモード
    parser.add_argument(
        "--image-only",
        action="store_true",
        help="動画を作らず、テキスト合成済みのサムネ画像だけ生成する",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    image_path = Path(args.image).expanduser()
    audio_path = Path(args.audio).expanduser()
    thumb_image_path = (
        Path(args.embed_thumb).expanduser()
        if args.embed_thumb
        else None
    )

    if not image_path.exists():
        print(f"[FATAL] 画像が見つかりません: {image_path}")
        sys.exit(1)

    # image-only モードの時は音声はチェックしない（ダミーパスでもOK）
    if not args.image_only:
        if not audio_path.exists():
            print(f"[FATAL] 音声ファイルが見つかりません: {audio_path}")
            sys.exit(1)

    # 動画の出力先
    if args.output_video:
        output_path = Path(args.output_video).expanduser()
    else:
        # デフォルト: カレントディレクトリ/video_ja_final.mp4
        output_path = Path.cwd() / VIDEO_JA_FINAL_FILENAME

    # サムネの出力先
    if args.output_thumb:
        overlay_path = Path(args.output_thumb).expanduser()
    else:
        # デフォルト: カレントディレクトリ/video_thumb_final.png
        overlay_path = Path.cwd() / VIDEO_THUMB_FINAL_NAME

    embed_video_path = Path(args.embed_video).expanduser() if args.embed_video else None

    print("[INFO] 背景画像 :", image_path)
    if not args.image_only:
        print("[INFO] 音声     :", audio_path)
        print("[INFO] 出力動画 :", output_path)
    if embed_video_path is not None:
        print("[INFO] 埋め込み動画 :", embed_video_path)
    if thumb_image_path is not None:
        print("[INFO] 貼り込み画像 :", thumb_image_path)
    print("[INFO] オーバレイ画像 :", overlay_path)
    print("[INFO] Header   :", args.header)
    print("[INFO] Title    :", args.title)
    if args.url:
        print("[INFO] URL      :", args.url)
    if args.image_only:
        print("[INFO] モード   : サムネだけ生成 (--image-only)")

    # 1) 背景 + テキスト + URL (+ 画像) からオーバーレイ画像を作成
    overlay_image = create_overlay_image(
        base_image=image_path,
        header_text=args.header,
        title_text=args.title,
        title_pointsize=args.title_pointsize,
        title_line_spacing=args.title_line_spacing,
        title_offset_y=args.title_offset_y,
        title_strokewidth=args.title_strokewidth,
        output_path=overlay_path,
        video_url=args.url or None,
        thumb_image=thumb_image_path,
    )
    if overlay_image is None:
        print("[FATAL] オーバーレイ画像の作成に失敗しました。")
        sys.exit(1)

    # image-only モードならここで終了
    if args.image_only:
        print(f"[RESULT] サムネ画像のみ生成しました: {overlay_image}")
        return

    # 2) オーバーレイ画像 + （埋め込み動画） + 音声 から動画を作成
    create_video_from_audio(
        image_path=overlay_image,
        audio_path=audio_path,
        output_path=output_path,
        embed_video_path=embed_video_path,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[FATAL] 予期しないエラー: {e}")
        sys.exit(1)