import re
import subprocess
import sys
import os
import argparse

# ===== 定数定義 =====
# 入力関連
DEFAULT_INPUT_FILE = "NVIDIA.m4a"
DEFAULT_SILENCE_LOG = "silence.log"

# 出力関連
DEFAULT_OUT_DIR = "chunks"
DEFAULT_EXT_FALLBACK = ".webm"  # 入力に拡張子がない場合のデフォルト

# セグメント長
DEFAULT_MIN_SEGMENT = 5 * 60      # 300 秒 (5分)
DEFAULT_MAX_SEGMENT = 15 * 60     # 900 秒 (15分)

# 分割後ファイル名（例: original_01.webm, original_02.webm ...）
DEFAULT_PART_PREFIX = "original_"
PART_INDEX_WIDTH = 2              # 01, 02 ... にしたいので 2


def get_duration(input_file):
    """ffprobeで元ファイルの総時間(秒)を取得"""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            input_file,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def parse_silence_starts(log_path):
    """silence.log から silence_start の時刻(秒)をリストで返す"""
    starts = []
    pattern = re.compile(r"silence_start:\s*([0-9.]+)")
    with open(log_path, "r") as f:
        for line in f:
            m = pattern.search(line)
            if m:
                starts.append(float(m.group(1)))
    return starts


def build_segments(silence_points, total_duration, min_segment, max_segment):
    """
    無音ポイントを使って [start, end) の区間リストを作成する。

    方針:
      - セグメント開始 start から見て、
        - 無音までの長さが min_segment 未満ならスキップ
        - min_segment〜max_segment の範囲なら、その無音でカット
      - 無音の間隔が長すぎて max_segment を超える場合は、
        無音がなくても max_segment ごとに強制カット
      - 最後の余りも min_segment を基準に処理
    """
    segments = []
    start = 0.0

    # 0〜total_duration の範囲にある無音位置だけを対象にし、念のためソート
    silence_points = sorted(
        sp for sp in silence_points
        if 0.0 < sp < total_duration
    )

    for sp in silence_points:
        # 1) 無音 sp までが長すぎる場合、無音が無くても max_segment ごとに強制カット
        while start + max_segment < sp:
            cut = start + max_segment
            if cut - start >= min_segment:
                segments.append((start, cut))
                start = cut
            else:
                break

        # 2) 改めてその無音ポイントで切るかどうか判定
        seg_len = sp - start
        if seg_len >= min_segment:
            segments.append((start, sp))
            start = sp

    # 3) すべての無音を処理したあと、終端 total_duration までを処理
    while start + max_segment < total_duration:
        cut = start + max_segment
        if cut - start >= min_segment:
            segments.append((start, cut))
            start = cut
        else:
            break

    # 4) 残りをどうするか
    tail_len = total_duration - start
    if tail_len >= min_segment:
        segments.append((start, total_duration))
    elif segments:
        last_start, _ = segments[-1]
        segments[-1] = (last_start, total_duration)
    else:
        # 無音はあったが、条件的にどこも切れなかった場合の保険
        segments.append((0.0, total_duration))

    return segments


def split_segments(input_file, segments, out_dir, part_prefix):
    os.makedirs(out_dir, exist_ok=True)

    # 入力ファイルと同じ拡張子で出力する
    _, ext = os.path.splitext(input_file)
    if not ext:
        ext = DEFAULT_EXT_FALLBACK  # 念のため

    for i, (start, end) in enumerate(segments, 1):
        out_name = f"{part_prefix}{i:0{PART_INDEX_WIDTH}d}{ext}"
        out_path = os.path.join(out_dir, out_name)
        duration = end - start
        cmd = [
            "ffmpeg",
            "-y",
            "-i", input_file,
            "-ss", f"{start}",
            "-t", f"{duration}",
            "-c", "copy",
            out_path,
        ]
        print("Running:", " ".join(cmd))
        subprocess.run(cmd, check=True)

    print("Done. Segments saved in:", out_dir)


def main():
    parser = argparse.ArgumentParser(
        description="silencedetect の結果を元に音声ファイルを分割します。"
    )
    parser.add_argument(
        "-i", "--input",
        default=DEFAULT_INPUT_FILE,
        help=f"入力音声ファイルパス（デフォルト: {DEFAULT_INPUT_FILE}）"
    )
    parser.add_argument(
        "-l", "--log",
        default=DEFAULT_SILENCE_LOG,
        help=f"silencedetect のログファイルパス（デフォルト: {DEFAULT_SILENCE_LOG}）"
    )
    parser.add_argument(
        "-o", "--out-dir",
        default=DEFAULT_OUT_DIR,
        help=f"出力ディレクトリ（デフォルト: {DEFAULT_OUT_DIR}）"
    )
    parser.add_argument(
        "--min-segment",
        type=int,
        default=DEFAULT_MIN_SEGMENT,
        help=f"1セグメントの最小長さ（秒）。デフォルト: {DEFAULT_MIN_SEGMENT} 秒"
    )
    parser.add_argument(
        "--max-segment",
        type=int,
        default=DEFAULT_MAX_SEGMENT,
        help=f"1セグメントのおおよその最大長さ（秒）。デフォルト: {DEFAULT_MAX_SEGMENT} 秒"
    )
    parser.add_argument(
        "--part-prefix",
        default=DEFAULT_PART_PREFIX,
        help=f"分割後ファイル名のプレフィックス（デフォルト: {DEFAULT_PART_PREFIX}）"
    )

    args = parser.parse_args()

    input_file = args.input
    silence_log = args.log
    out_dir = args.out_dir
    min_segment = args.min_segment
    max_segment = args.max_segment
    part_prefix = args.part_prefix

    if not os.path.exists(input_file):
        print(f"Input file not found: {input_file}")
        sys.exit(1)
    if not os.path.exists(silence_log):
        print(f"Silence log not found: {silence_log}")
        sys.exit(1)

    total_duration = get_duration(input_file)
    silence_points = parse_silence_starts(silence_log)

    # --- 無音が1つも見つからない場合は、ファイル全体を1セグメントとして扱う ---
    if not silence_points:
        print("No silence points found in log. Using whole file as a single segment.")
        segments = [(0.0, total_duration)]
    else:
        segments = build_segments(silence_points, total_duration, min_segment, max_segment)
        if not segments:
            print("No valid segments built. Fallback to a single segment for the whole file.")
            segments = [(0.0, total_duration)]
    # -------------------------------------------------------------

    split_segments(input_file, segments, out_dir, part_prefix)


if __name__ == "__main__":
    main()
