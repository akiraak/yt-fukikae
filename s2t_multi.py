import argparse
from openai import OpenAI
import os
import re

# ===== 定数定義 =====
DEFAULT_MODEL = "gpt-4o-transcribe"

# 対象とする音声ファイルの拡張子
AUDIO_EXTS = (".webm", ".m4a", ".mp3", ".wav", ".ogg", ".flac")

# 入力ファイル名 / 出力ファイル名のデフォルトプレフィックス
DEFAULT_PART_PREFIX = "original_"
DEFAULT_TEXT_PREFIX = "text_"


def transcribe_file(client, input_path, output_path, model):
    with open(input_path, "rb") as audio_file:
        transcription = client.audio.transcriptions.create(
            model=model,
            file=audio_file,
        )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(transcription.text)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "ディレクトリ内の PREFIX+番号 形式（例: original_01.webm）の音声ファイルを "
            "文字起こしして PREFIX+番号 形式（例: text_01.txt）で保存します。"
        )
    )
    parser.add_argument(
        "path",
        help="音声ファイルが入ったディレクトリ（例: NVIDIA_work）"
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"使用する文字起こしモデル名（デフォルト: {DEFAULT_MODEL}）"
    )
    parser.add_argument(
        "--part-prefix",
        default=DEFAULT_PART_PREFIX,
        help=f"入力音声ファイル名のプレフィックス（デフォルト: {DEFAULT_PART_PREFIX}）"
    )
    parser.add_argument(
        "--text-prefix",
        default=DEFAULT_TEXT_PREFIX,
        help=f"出力テキストファイル名のプレフィックス（デフォルト: {DEFAULT_TEXT_PREFIX}）"
    )
    args = parser.parse_args()

    target_dir = args.path
    model = args.model
    part_prefix = args.part_prefix
    text_prefix = args.text_prefix

    # part_prefix に応じてパターンを生成（例: original_01, original_12 ...）
    part_basename_pattern = re.compile(rf"{re.escape(part_prefix)}(\d+)$")

    # --- ディレクトリチェック ---
    if not os.path.isdir(target_dir):
        print("指定したパスはディレクトリではありません。ディレクトリを指定してください。")
        return

    client = OpenAI()
    print(f"使用モデル: {model}")
    print(f"入力プレフィックス: {part_prefix!r}")
    print(f"出力プレフィックス: {text_prefix!r}")

    # --- PREFIX+番号.* を列挙 ---
    files = []
    for f in sorted(os.listdir(target_dir)):
        if not f.lower().endswith(AUDIO_EXTS):
            continue

        base, _ = os.path.splitext(f)
        # 例: original_01, original_12 など
        if part_basename_pattern.match(base):
            files.append(f)

    if not files:
        print(f"指定ディレクトリに {part_prefix}XX.* 形式の音声ファイルがありませんでした。")
        return

    total = len(files)

    print(f"対象ディレクトリ: {target_dir}")
    print(f"検出ファイル数（{part_prefix}XX.* のみ）: {total}")
    for i, f in enumerate(files, 1):
        print(f"  {i}. {f}")
    print("-" * 40)

    # --- 文字起こしループ ---
    for idx, f in enumerate(files, 1):
        input_path = os.path.join(target_dir, f)
        base, _ = os.path.splitext(f)

        # original_01 → text_01.txt（prefix は引数で指定されたものを使用）
        m = part_basename_pattern.match(base)
        if m:
            num = m.group(1)
            output_name = f"{text_prefix}{num}.txt"
        else:
            # （ここには来ない想定だが保険）
            output_name = base + ".txt"

        output_path = os.path.join(target_dir, output_name)

        print(f"[{idx}/{total}] {f} -> {output_name} を {model} で文字起こし中...")

        try:
            transcribe_file(client, input_path, output_path, model)
            print(f"  完了: {output_name}")
        except Exception as e:
            print(f"  エラー発生: {f} -> {e}")

    print("-" * 40)
    print(f"すべての {part_prefix}XX ファイルの処理が終了しました。")


if __name__ == "__main__":
    main()
