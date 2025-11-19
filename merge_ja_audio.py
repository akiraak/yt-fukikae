import argparse
import os
import re
import subprocess
import tempfile

# ===== デフォルト値・定数 =====
DEFAULT_PREFIX = "text_ja_"
DEFAULT_EXT = ".mp3"
DEFAULT_OUTPUT_NAME = "ja.mp3"

# 無音のデフォルト長さ（ミリ秒）
DEFAULT_SILENCE_HEAD_MS = 1000
DEFAULT_SILENCE_TAIL_MS = 1000

# loudnorm のターゲット値
LOUDNORM_I = -16
LOUDNORM_LRA = 11
LOUDNORM_TP = -1.5

# 出力 MP3 のビットレート
LAME_BITRATE = "192k"

# ffmpeg のパス（必要なら書き換え）
FFMPEG_BIN = "ffmpeg"


def main():
    parser = argparse.ArgumentParser(
        description=(
            "作業フォルダ内の combined_ja_part_XX.mp3 を結合して1つの mp3 にします。"
        )
    )
    parser.add_argument(
        "workdir",
        help="作業フォルダのパス（例: NVIDIA_work）"
    )
    parser.add_argument(
        "--prefix",
        default=DEFAULT_PREFIX,
        help=f"入力ファイル名のプレフィックス（デフォルト: {DEFAULT_PREFIX}）"
    )
    parser.add_argument(
        "--ext",
        default=DEFAULT_EXT,
        help=f"入力ファイルの拡張子（デフォルト: {DEFAULT_EXT}）"
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT_NAME,
        help=f"出力ファイル名（デフォルト: {DEFAULT_OUTPUT_NAME}）"
    )
    parser.add_argument(
        "--silence-head-ms",
        type=int,
        default=DEFAULT_SILENCE_HEAD_MS,
        help=f"先頭に追加する無音の長さ (ミリ秒, デフォルト: {DEFAULT_SILENCE_HEAD_MS})"
    )
    parser.add_argument(
        "--silence-tail-ms",
        type=int,
        default=DEFAULT_SILENCE_TAIL_MS,
        help=f"末尾に追加する無音の長さ (ミリ秒, デフォルト: {DEFAULT_SILENCE_TAIL_MS})"
    )
    args = parser.parse_args()

    workdir = args.workdir
    prefix = args.prefix
    ext = args.ext
    output_name = args.output
    output_path = os.path.join(workdir, output_name)
    silence_head = max(args.silence_head_ms, 0)
    silence_tail = max(args.silence_tail_ms, 0)

    if not os.path.isdir(workdir):
        print(f"作業フォルダが見つかりません: {workdir}")
        return

    # combined_ja_part_XXX.mp3 を番号順に取得
    pattern = re.compile(rf"^{re.escape(prefix)}(\d{{2}}){re.escape(ext)}$")
    files = []
    for name in sorted(os.listdir(workdir)):
        m = pattern.match(name)
        if m:
            idx = int(m.group(1))
            files.append((idx, name))

    if not files:
        print(f"{workdir} 内に {prefix}XXX{ext} 形式のファイルが見つかりません。")
        return

    files.sort(key=lambda x: x[0])

    print(f"対象フォルダ   : {workdir}")
    print(f"結合対象数     : {len(files)}")
    print(f"出力ファイル名 : {output_name}")
    for i, (_, name) in enumerate(files, 1):
        print(f"  {i}. {name}")
    print("-" * 40)

    # 一時ファイルに concat 用リストを作成
    with tempfile.NamedTemporaryFile(mode="w", delete=False, dir=workdir, suffix=".txt") as tf:
        list_path = tf.name
        for _, name in files:
            tf.write(f"file '{name}'\n")

    try:
        # ffmpeg concat demuxer で結合 + 正規化 + 前後無音
        filter_chain = f"loudnorm=I={LOUDNORM_I}:LRA={LOUDNORM_LRA}:TP={LOUDNORM_TP}"
        if silence_head > 0:
            # 先頭に無音 (adelay はミリ秒指定, all=1 で全チャンネルに適用)
            filter_chain += f",adelay={silence_head}|all=1"
        if silence_tail > 0:
            # 末尾に無音 (apad の pad_dur は秒指定)
            pad_sec = silence_tail / 1000.0
            filter_chain += f",apad=pad_dur={pad_sec}"

        cmd = [
            FFMPEG_BIN,
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", list_path,
            "-af", filter_chain,
            "-c:a", "libmp3lame",
            "-b:a", LAME_BITRATE,
            output_path,
        ]
        print("実行コマンド:", " ".join(cmd))
        subprocess.run(cmd, check=True)
        print("結合＋正規化＋無音付加が完了しました。")
        print(f"最終出力ファイル: {output_path}")
    except subprocess.CalledProcessError as e:
        print("ffmpeg 実行中にエラーが発生しました:", e)
    finally:
        # 一時リストファイル削除
        try:
            os.remove(list_path)
        except OSError:
            pass


if __name__ == "__main__":
    main()
