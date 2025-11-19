import argparse
import os
import re
from openai import OpenAI

# =========================
# 定数・デフォルト設定
# =========================

DEFAULT_PREFIX = "text_ja_"
DEFAULT_EXT = ".txt"
DEFAULT_TTS_MODEL = "gpt-4o-mini-tts"
DEFAULT_VOICE = "alloy"
DEFAULT_AUDIO_FORMAT = "mp3"  # TTSの出力フォーマット
PREVIEW_LENGTH = 40  # short_preview で使う表示用の最大文字数

# response_format -> 拡張子 の対応表
AUDIO_EXT_MAP = {
    "mp3": ".mp3",
    "wav": ".wav",
    "flac": ".flac",
    "opus": ".opus",
    "aac": ".aac",
    "pcm": ".pcm",  # 生PCMの場合
}


# =========================
# 関数
# =========================

def short_preview(text: str, length: int = PREVIEW_LENGTH) -> str:
    preview = text.strip().replace("\n", " ")
    if len(preview) > length:
        preview = preview[:length] + "..."
    return preview


def main():
    parser = argparse.ArgumentParser(
        description=(
            "作業フォルダ内の text_ja_XXX.txt を読み込み、"
            "Text-to-Speech API で音声ファイルを一括生成します。"
        )
    )
    parser.add_argument(
        "workdir",
        help="作業フォルダのパス（例: NVIDIA_work）"
    )
    parser.add_argument(
        "--prefix",
        default=DEFAULT_PREFIX,
        help=f"入力テキストファイル名のプレフィックス（デフォルト: {DEFAULT_PREFIX}）"
    )
    parser.add_argument(
        "--ext",
        default=DEFAULT_EXT,
        help=f"入力テキストファイルの拡張子（デフォルト: {DEFAULT_EXT}）"
    )
    parser.add_argument(
        "--out-dir",
        help="音声ファイルの出力先ディレクトリ（未指定なら作業フォルダと同じ）"
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_TTS_MODEL,
        help=f"使用する TTS モデル名（デフォルト: {DEFAULT_TTS_MODEL}）"
    )
    parser.add_argument(
        "--voice",
        default=DEFAULT_VOICE,
        help=f"使用するボイス名（デフォルト: {DEFAULT_VOICE}）"
    )
    parser.add_argument(
        "--response-format",
        default=DEFAULT_AUDIO_FORMAT,
        help=(
            "TTSの出力フォーマット（mp3, wav, flac, opus, aac, pcm など。"
            f"デフォルト: {DEFAULT_AUDIO_FORMAT}）"
        ),
    )
    parser.add_argument(
        "--speed",
        type=float,
        help=(
            "読み上げ速度（0.25〜4.0 の範囲を推奨。"
            "1.0 が標準速度。モデルによっては無視される場合があります）"
        ),
    )
    parser.add_argument(
        "--instructions",
        help=(
            "読み上げスタイルの指示（例: "
            "『落ち着いたニュースキャスターのように』『元気よく』など）。"
            "特に gpt-4o-mini-tts ではトーンやテンポの調整に有効です。"
        ),
    )
    args = parser.parse_args()

    workdir = args.workdir
    prefix = args.prefix
    ext = args.ext
    out_dir = args.out_dir if args.out_dir else workdir
    model = args.model
    voice = args.voice
    response_format = args.response_format
    speed = args.speed
    instructions = args.instructions

    if not os.path.isdir(workdir):
        print(f"作業フォルダが見つかりません: {workdir}")
        return

    os.makedirs(out_dir, exist_ok=True)

    # text_ja_XX.txt を検出
    pattern = re.compile(rf"^{re.escape(prefix)}(\d{{2}}){re.escape(ext)}$")
    files = []
    for name in sorted(os.listdir(workdir)):
        m = pattern.match(name)
        if m:
            idx = int(m.group(1))
            files.append((idx, name))

    if not files:
        print(f"{workdir} 内に {prefix}XX{ext} 形式のファイルが見つかりません。")
        return

    client = OpenAI()

    total = len(files)
    print(f"対象フォルダ   : {workdir}")
    print(f"出力フォルダ   : {out_dir}")
    print(f"TTSモデル      : {model}")
    print(f"ボイス         : {voice}")
    print(f"音声フォーマット : {response_format}")
    if speed is not None:
        print(f"読み上げ速度   : {speed}（モデルによっては無視される場合があります）")
    if instructions:
        print(f"スタイル指示   : {instructions}")
    print(f"対象ファイル数 : {total}")
    for i, (_, name) in enumerate(files, 1):
        print(f"  {i}. {name}")
    print("-" * 40)

    # 出力拡張子を response_format から決定
    audio_ext = AUDIO_EXT_MAP.get(response_format, "." + response_format)

    for idx, (num, filename) in enumerate(files, 1):
        input_path = os.path.join(workdir, filename)
        base = os.path.splitext(filename)[0]
        out_name = f"{base}{audio_ext}"
        out_path = os.path.join(out_dir, out_name)

        # テキスト読み込み
        with open(input_path, "r", encoding="utf-8") as f:
            text = f.read().strip()

        if not text:
            print(f"[{idx}/{total}] {filename} は空のためスキップします。")
            continue

        print(f"[{idx}/{total}] {filename} -> {out_name} を生成中...")
        print(f"  テキスト一部: {short_preview(text)}")

        try:
            # API用の引数をまとめる
            request_args = {
                "model": model,
                "voice": voice,
                "input": text,
                "response_format": response_format,
            }
            if speed is not None:
                request_args["speed"] = speed
            #if instructions:
            #    request_args["instructions"] = instructions

            # 推奨スタイル: ストリーミングで直接ファイルに保存
            with client.audio.speech.with_streaming_response.create(
                **request_args
            ) as response:
                response.stream_to_file(out_path)

            print(f"  完了: {out_name}")
        except Exception as e:
            print(f"  エラー発生: {filename} -> {e}")

    print("-" * 40)
    print("すべての音声ファイルの生成が終了しました。")


if __name__ == "__main__":
    main()
