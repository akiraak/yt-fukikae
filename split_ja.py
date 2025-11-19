import argparse
import os
import re

# ===== 定数定義 =====
DEFAULT_INPUT_NAME = "text_ja.txt"
DEFAULT_MAX_CHARS = 800

# 分割後ファイル名のベース（text_ja_XX.txt の text_ja_ 部分）
OUTPUT_BASENAME = "text_ja_"
# text_ja_XX.txt の X の桁数（2 なら 01, 02, ...）
OUTPUT_INDEX_WIDTH = 2


def split_text(text: str, max_chars: int):
    """
    日本語テキストを「。」と改行を優先して分割し、
    各チャンクが max_chars 以内になるように分割する。
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 「文 + 区切り記号」を単位にする（区切りも含めて保持）
    parts = re.split(r'(。|\n)', text)
    units = []
    for i in range(0, len(parts), 2):
        chunk = parts[i]
        if i + 1 < len(parts):
            chunk += parts[i + 1]  # 「。」または改行を付与
        if chunk:
            units.append(chunk)

    chunks = []
    current = ""

    for u in units:
        if len(current) + len(u) <= max_chars:
            current += u
            continue

        # current が空で u 自体がデカすぎる場合は強制分割
        if not current:
            while len(u) > max_chars:
                chunks.append(u[:max_chars])
                u = u[max_chars:]
            if u:
                current = u
            continue

        # いったん current を確定
        chunks.append(current)
        current = ""

        if len(u) <= max_chars:
            current = u
        else:
            while len(u) > max_chars:
                chunks.append(u[:max_chars])
                u = u[max_chars:]
            if u:
                current = u

    if current.strip():
        chunks.append(current)

    return chunks


def main():
    parser = argparse.ArgumentParser(
        description=(
            f"作業フォルダ内の {DEFAULT_INPUT_NAME}（または指定ファイル）を、"
            "「。」や改行を区切りとして最大文字数ごとに分割します。"
        )
    )
    parser.add_argument(
        "workdir",
        help="作業フォルダのパス"
    )
    parser.add_argument(
        "--input-name",
        default=DEFAULT_INPUT_NAME,
        help=f"作業フォルダ内の入力ファイル名（デフォルト: {DEFAULT_INPUT_NAME}）"
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=DEFAULT_MAX_CHARS,
        help=f"1ファイルあたりの最大文字数（デフォルト: {DEFAULT_MAX_CHARS}）"
    )
    parser.add_argument(
        "--out-dir",
        help="出力先ディレクトリ（未指定なら作業フォルダと同じ）"
    )
    parser.add_argument(
        "--output-basename",
        default=OUTPUT_BASENAME,
        help=f"分割後ファイル名のベース（デフォルト: {OUTPUT_BASENAME}）"
    )
    args = parser.parse_args()

    workdir = args.workdir
    input_name = args.input_name
    max_chars = args.max_chars
    output_basename = args.output_basename

    if not os.path.isdir(workdir):
        print(f"作業フォルダが見つかりません: {workdir}")
        return

    # 入力ファイルパス（デフォルト: workdir/text_ja.txt）
    input_path = os.path.join(workdir, input_name)

    if not os.path.exists(input_path):
        print(f"入力ファイルが見つかりません: {input_path}")
        return

    # 出力ディレクトリ（デフォルト: 作業フォルダ）
    out_dir = args.out_dir if args.out_dir else workdir
    os.makedirs(out_dir, exist_ok=True)

    # テキスト読み込み
    with open(input_path, "r", encoding="utf-8") as f:
        text = f.read()

    chunks = split_text(text, max_chars)

    print(f"入力ファイル: {input_path}")
    print(f"出力ディレクトリ: {out_dir}")
    print(f"max_chars: {max_chars}")
    print(f"分割チャンク数: {len(chunks)}")

    for idx, chunk in enumerate(chunks, 1):
        # 例: text_ja_01.txt, text_ja_02.txt ... の形式で出力
        out_name = f"{output_basename}{idx:0{OUTPUT_INDEX_WIDTH}d}.txt"
        out_path = os.path.join(out_dir, out_name)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(chunk)
        preview = chunk.strip().replace("\n", " ")
        if len(preview) > 40:
            preview = preview[:40] + "..."
        print(f"  [{idx}/{len(chunks)}] {out_name} | 一部: {preview}")

    print("分割完了。")


if __name__ == "__main__":
    main()
