import argparse
import os
import re
import sys
import syslog
from openai import OpenAI

# =========================
# 定数・デフォルト設定
# =========================

# 翻訳用システムプロンプト
TRANSLATOR_SYSTEM_PROMPT = (
    "You are a professional translator into Japanese.\n"
    "The user input may contain English, Japanese, or other languages.\n"
    "\n"
    "Rules:\n"
    "1. For parts that are already natural Japanese, output them as-is "
    "(do not paraphrase or rewrite them, unless there are obvious minor typos).\n"
    "2. For parts that are not Japanese, translate them into natural and accurate Japanese.\n"
    "3. Preserve the original structure: line breaks, bullet points, numbering, and overall formatting.\n"
    "4. Do not add explanations or comments.\n"
    "5. Output Japanese text only (plus any non-Japanese terms that should reasonably stay as-is, "
    "such as product names, code, or proper nouns)."
)

# モデル・ファイル名などのデフォルト
DEFAULT_MODEL = "gpt-5.1"
DEFAULT_COMBINED_NAME = "text_ja.txt"

# 対象となるテキストファイルのプレフィックス（text_XX.txt の text_ 部分）
DEFAULT_TEXT_PREFIX = "text_"

# 翻訳後ファイルのプレフィックス（例: text_ja_01.txt の "text_ja_" 部分）
DEFAULT_TRANSLATED_PREFIX = "text_ja_"


def build_text_file_regex(prefix: str) -> str:
    """
    プレフィックスから <prefix>XX.txt に相当する正規表現を生成する。
    例: prefix="text_" -> r"text_\\d+\\.txt$"
    """
    return rf"{re.escape(prefix)}\d+\.txt$"


# デフォルトのパターン（実際に使う値は main 内で引数から上書き）
TEXT_FILE_REGEX = build_text_file_regex(DEFAULT_TEXT_PREFIX)

# プレビュー表示の最大文字数
PREVIEW_LENGTH = 40


# =========================
# 関数群
# =========================

def translate_text(client, text: str, model: str) -> str:
    """多言語→日本語翻訳（既存の自然な日本語は極力そのまま）。"""
    messages = [
        {
            "role": "system",
            "content": TRANSLATOR_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": text,
        },
    ]

    kwargs = {
        "model": model,
        "messages": messages,
    }
    if not model.startswith("gpt-5"):
        kwargs["temperature"] = 0.2

    try:
        response = client.chat.completions.create(**kwargs)
    except Exception as e:
        # ここで明示的に例外を投げる
        raise RuntimeError(f"OpenAI 翻訳API呼び出しに失敗しました: {e}") from e

    if not response.choices or response.choices[0].message.content is None:
        raise RuntimeError("翻訳結果が空でした（choices がありません）。")

    return response.choices[0].message.content.strip()


def process_file(client, input_path: str, output_path: str, model: str) -> str:
    """1ファイル翻訳して保存し、日本語テキストを返す。"""
    with open(input_path, "r", encoding="utf-8") as f:
        source_text = f.read()

    japanese_text = translate_text(client, source_text, model)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(japanese_text)

    return japanese_text


def build_combined_file(
    dir_path: str,
    ja_files: list[str],
    combined_name: str = DEFAULT_COMBINED_NAME,
) -> None:
    """
    翻訳済みファイルを指定順に結合して1ファイルにまとめる。
    余計なヘッダ等は入れず、中身のみを順番に連結。
    """
    combined_path = os.path.join(dir_path, combined_name)

    with open(combined_path, "w", encoding="utf-8") as out:
        for idx, fname in enumerate(ja_files):
            path = os.path.join(dir_path, fname)
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().rstrip("\n")
            out.write(content)
            # 最後のファイル以外は区切りとして空行1つ
            if idx != len(ja_files) - 1:
                out.write("\n\n")

    print(f"結合ファイルを出力しました: {combined_path}")


def short_preview(text: str, length: int = PREVIEW_LENGTH) -> str:
    """翻訳テキストの先頭だけ表示用に切り出す。"""
    preview = text.strip().replace("\n", " ")
    if len(preview) > length:
        preview = preview[:length] + "..."
    return preview


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "ディレクトリ内の text_XX.txt 形式のファイル（または --text-prefix で指定したプレフィックス）を "
            "日本語に翻訳し、翻訳済みファイルおよび結合ファイル（デフォルト: text_ja.txt）を出力します。"
        )
    )
    parser.add_argument(
        "path",
        help="テキストファイルが入ったディレクトリ（例: NVIDIA_work）",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"使用するモデル名（デフォルト: {DEFAULT_MODEL}）",
    )
    parser.add_argument(
        "--text-prefix",
        default=DEFAULT_TEXT_PREFIX,
        help=(
            f"翻訳元となるテキストファイル名のプレフィックス（デフォルト: {DEFAULT_TEXT_PREFIX!r}。"
            f"{DEFAULT_TEXT_PREFIX}01.txt, {DEFAULT_TEXT_PREFIX}02.txt など）"
        ),
    )
    parser.add_argument(
        "--translated-prefix",
        default=DEFAULT_TRANSLATED_PREFIX,
        help=(
            "翻訳後ファイル名のプレフィックス（デフォルト: 'text_ja_'。"
            "例: text_ja_01.txt, text_ja_02.txt など）"
        ),
    )
    parser.add_argument(
        "--combined-name",
        default=DEFAULT_COMBINED_NAME,
        help=(
            f"翻訳済みファイルを結合して出力するファイル名 "
            f"（デフォルト: {DEFAULT_COMBINED_NAME!r}）"
        ),
    )
    args = parser.parse_args()

    target_dir = args.path
    model = args.model
    text_prefix = args.text_prefix
    translated_prefix = args.translated_prefix
    combined_name = args.combined_name

    if not os.path.isdir(target_dir):
        print("指定したパスはディレクトリではありません。ディレクトリを指定してください。")
        return

    client = OpenAI()

    # --- 対象: {text_prefix}XX.txt のみを翻訳 ---
    # 引数で受け取ったプレフィックスから正規表現を組み立てる
    text_file_regex = build_text_file_regex(text_prefix)
    text_pattern = re.compile(text_file_regex, re.IGNORECASE)

    files = [
        f for f in sorted(os.listdir(target_dir))
        if text_pattern.match(f)
    ]

    if not files:
        print(f"対象となる {text_prefix}XX.txt が見つかりませんでした。")
        return

    total = len(files)

    print(f"対象ディレクトリ: {target_dir}")
    print(f"翻訳対象ファイル数: {total}")
    print(f"使用モデル: {model}")
    print(f"翻訳元プレフィックス: {text_prefix!r} （パターン: {text_file_regex}）")
    print(f"翻訳後プレフィックス: {translated_prefix!r}")
    print(f"結合ファイル名: {combined_name!r}")
    for i, f in enumerate(files, 1):
        print(f"  {i}. {f}")
    print("-" * 40)

    # 各 {text_prefix}XX.txt を翻訳（毎回新規生成）
    any_error = False

    for idx, f in enumerate(files, 1):
        input_path = os.path.join(target_dir, f)
        base, ext = os.path.splitext(f)   # 例: base="text_01", ext=".txt"
        index_part = base[len(text_prefix):]  # 例: "01"
        # 例: translated_prefix="text_ja_" -> "text_ja_01.txt"
        output_name = f"{translated_prefix}{index_part}{ext}"
        output_path = os.path.join(target_dir, output_name)

        print(f"[{idx}/{total}] {f} -> {output_name} を {model} で翻訳中...")

        try:
            jp = process_file(client, input_path, output_path, model)
            print(f"  完了: {output_name} | 一部: {short_preview(jp)}")
        except Exception as e:
            print(f"  エラー発生: {f} -> {e}")
            any_error = True
            break

    if any_error:
        print("-" * 40)
        print("翻訳中にエラーが発生したため処理を中断しました。")
        sys.exit(1)

    print("-" * 40)

    # ここから先は「エラーがなかったときだけ」実行される
    # 翻訳済みファイル（translated_prefix + 数字 + .txt）を取得して結合
    translated_regex = build_text_file_regex(translated_prefix)
    translated_pattern = re.compile(translated_regex, re.IGNORECASE)

    ja_files = [
        f for f in sorted(os.listdir(target_dir))
        if translated_pattern.match(f)
    ]

    if not ja_files:
        print(f"結合対象となる翻訳済みファイル（{translated_prefix}XX.txt）がありませんでした。")
        return

    build_combined_file(target_dir, ja_files, combined_name=combined_name)
    print("すべてのファイルの処理が終了しました。")


if __name__ == "__main__":
    main()
