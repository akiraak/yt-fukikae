## 🎙️ このスクリプトでできること

海外のYouTube動画を、ほぼワンコマンドで「日本語吹き替え動画」に変換するためのスクリプトです。  

- 🎧 YouTube動画 → 文字起こし → 日本語訳 → 合成音声
- 🎬 元動画のサムネ + テキスト + 背景画像を合成して MP4 を生成

海外の動画を日本語で聞きたい人におすすめです。英語以外にもスペイン語、アラビア語、韓国語でも問題なく吹替できました。

---

## 🛠️ 必要なもの（環境・APIキーなど）

### 環境

- Linux / WSL2 などのシェル環境
- Python 3.10+ 推奨
- 外部コマンド
  - `ffmpeg`
  - `convert`（ImageMagick）
- フォント（デフォルト設定）
  - `NotoSansCJK-Bold.ttc`
  - `DejaVuSans-Bold.ttf`
- OpenAI API Key
  - `export OPENAI_API_KEY="sk-p..."`


## 🚀 クイックスタート

git が入っていて、ffmpeg / ImageMagick / Python / フォント が使える環境を前提にした最短パターンです。

```bash
git clone git@github.com:akiraak/yt-fukikae.git
cd yt-fukikae
pip install -r requirements.txt

export OPENAI_API_KEY="sk-p..."

python yt_fukikae.py \
  UF8uR6Z6KLc \
  --name JOBS \
  --header-text '@stanford' \
  --title-text 'スティーブ・ジョブズ\n2005年スタンフォード大学\n卒業式スピーチ'
```

`output/JOBS/` に `video_ja_final.mp4` が作成されます。

[![日本語吹替: スティーブ・ジョブズ 2005年スタンフォード大学卒業式スピーチ](https://img.youtube.com/vi/s6Y1qyQfYr0/maxresdefault.jpg)](https://www.youtube.com/watch?v=s6Y1qyQfYr0)


## ⚙️ オプション一覧

```
$ python yt_fukikae.py --help
usage: yt_fukikae.py [-h] --name NAME [--header-text HEADER_TEXT] [--title-text TITLE_TEXT] [--title-pointsize TITLE_POINTSIZE]
                     [--title-line-spacing TITLE_LINE_SPACING] [--title-offset-y TITLE_OFFSET_Y] [--title-strokewidth TITLE_STROKEWIDTH] [--no-draw-url]
                     [--input-thumbnail INPUT_THUMBNAIL] [--input-audio INPUT_AUDIO] [--translate-model TRANSLATE_MODEL]
                     [--transcribe-model TRANSCRIBE_MODEL] [--tts-model TTS_MODEL] [--tts-voice TTS_VOICE] [--final-copy-dir FINAL_COPY_DIR]
                     [--image-only]
                     video_id

YouTubeから音声をダウンロードし、変換・無音検出・分割・文字起こし・日本語訳・テキスト分割・読み上げ生成・結合・mp4生成まで行います。

positional arguments:
  video_id              処理する YouTube 動画のID（例: dQw4w9WgXcQ）

options:
  -h, --help            show this help message and exit
  --name NAME           output/ 配下に作成する作業ディレクトリ名
  --header-text HEADER_TEXT
                        サムネイルの上部に載せるテキスト
  --title-text TITLE_TEXT
                        サムネイルに載せるタイトルテキスト
  --title-pointsize TITLE_POINTSIZE
                        タイトル文字のポイントサイズ（デフォルト: 160）
  --title-line-spacing TITLE_LINE_SPACING
                        タイトル行間（ImageMagickの -interline-spacing、デフォルト: 0）
  --title-offset-y TITLE_OFFSET_Y
                        タイトルの上下位置オフセット（ピクセル, 正で下, 負で上）
  --title-strokewidth TITLE_STROKEWIDTH
                        タイトル縁取りの太さ（ImageMagick の -strokewidth、デフォルト: 26）
  --no-draw-url         サムネイルにYouTubeのURLを描画しない
  --input-thumbnail INPUT_THUMBNAIL
                        YouTubeからDLせず、このローカル画像ファイルをサムネイルとして使う（例: /path/to/image.jpg）
  --input-audio INPUT_AUDIO
                        YouTubeからDLせず、このローカル音声ファイルを入力として使う（例: /path/to/audio.m4a）
  --translate-model TRANSLATE_MODEL
                        日本語訳に使うモデル名（デフォルト: gpt-5.1）
  --transcribe-model TRANSCRIBE_MODEL
                        文字起こしに使うモデル名（デフォルト: gpt-4o-transcribe）
  --tts-model TTS_MODEL
                        TTS 音声生成に使うモデル名（デフォルト: gpt-4o-mini-tts）
  --tts-voice TTS_VOICE
                        TTS 音声生成に使うボイス名（デフォルト: alloy）
  --final-copy-dir FINAL_COPY_DIR
                        最終 mp4 / 画像 のコピー先ディレクトリ（デフォルト: output）
  --image-only          音声処理を行わず、サムネイルだけを生成する
```