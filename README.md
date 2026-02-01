## 🎙️ このスクリプトでできること

海外のYouTube動画を、ほぼワンコマンドで「日本語吹き替え動画」に変換するためのスクリプトです。

  - 🎧 YouTube動画 → 音声分離（ffmpeg）→ 文字起こし → 日本語訳 → 合成音声
  - 🎬 元動画のサムネ + テキスト + 背景画像を合成して MP4 を生成

## 🛠️ 必要なもの（環境・APIキーなど）

### 環境
  - Linux / WSL2 などのシェル環境
  - Python 3.10+
  - Node.js (文字起こし・翻訳・TTS処理に使用)
  - 外部コマンド
    - ffmpeg
    - convert（ImageMagick）
  - フォント（デフォルト設定）
    - NotoSansCJK-Bold.ttc
    - DejaVuSans-Bold.ttf
  - OpenAI API Key
    - プロジェクトルートに .env ファイルを作成し、以下の形式で保存してください。
      ```
      OPENAI_API_KEY="sk-p..."
      ```

### セットアップ

```Bash
git clone git@github.com:akiraak/yt-fukikae.git
cd yt-fukikae
pip install -r requirements.txt
npm install  # Node.js依存パッケージのインストールが必要な場合
```

## 🚀 クイックスタート

git が入っていて、ffmpeg / ImageMagick / Python / Node.js / フォント が使える環境を前提にした最短パターンです。

事前に .env ファイルに API Key を設定しておいてください。

```bash
# .env ファイルの作成例
echo 'OPENAI_API_KEY="sk-p..."' > .env

python yt_fukikae.py \
  --name JOBS \
  --youtube-id UF8uR6Z6KLc \
  --header '@stanford' \
  --title 'スティーブ・ジョブズ\n2005年スタンフォード大学\n卒業式スピーチ'
```

デフォルトでは ./outputs ディレクトリに以下のファイルが生成されます。
  - outputs/JOBS.mp4 (最終動画)
  - outputs/JOBS_thumb.png (サムネイル)

[![日本語吹替: スティーブ・ジョブズ 2005年スタンフォード大学卒業式スピーチ](https://img.youtube.com/vi/s6Y1qyQfYr0/maxresdefault.jpg)](https://www.youtube.com/watch?v=s6Y1qyQfYr0)


## ⚙️ オプション一覧

```
$ python yt_fukikae.py --help
usage: yt_fukikae.py [-h] --name NAME --youtube-id YOUTUBE_ID [--header HEADER] [--title TITLE] [--output-dir OUTPUT_DIR] [--image-only]

YouTube から音声・動画・サムネをダウンロードし、後続処理（文字起こし・翻訳・TTS など）を行うための起点スクリプト

options:
  -h, --help            show this help message and exit
  --name NAME           このジョブ/一連の処理・ファイル名につける名前（例: BBC, CNBC_20251125 など）
  --youtube-id YOUTUBE_ID
                        YouTube 動画ID
  --header HEADER       動画のヘッダーテキスト（デフォルト: ''）
  --title TITLE         動画のタイトルテキスト（デフォルト: ''）
  --output-dir OUTPUT_DIR
                        最終的な mp4 とサムネ PNG を保存するディレクトリ。指定しない場合は ./outputs に保存されます。
  --image-only          最終動画を作らず、サムネ画像だけ生成する（YouTube からはサムネのみ取得）
```