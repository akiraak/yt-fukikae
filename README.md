## 🚀 このスクリプトでできること

海外のYouTube動画を、ほぼワンコマンドで「日本語吹き替え動画」に変換するためのスクリプトです。  

- 🎧 YouTube動画 → 文字起こし → 日本語訳 → 合成音声
- 🎬 元動画のサムネ + テキスト + 背景画像を合成して MP4 を生成

海外の動画を日本語で聞きたい人におすすめです。英語以外にもスペイン語、アラビア語、韓国語でも問題なく吹替できました。

---

## 🧩 必要なもの（環境・APIキーなど）

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


## ⚙️ クイックスタート

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

