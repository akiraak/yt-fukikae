import yt_dlp
import argparse
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description='YouTubeから音声をダウンロードします。')
    parser.add_argument('urls', nargs='+', help='ダウンロードするYouTubeのURL')
    parser.add_argument(
        '-o', '--output',
        help='保存先のディレクトリ',
        default='/mnt/c/Users/akira/Downloads'
    )
    args = parser.parse_args()

    # 保存先ディレクトリを Path オブジェクトにして展開
    output_dir = Path(args.output).expanduser()

    # ディレクトリがなければ作成（親ディレクトリもまとめて）
    output_dir.mkdir(parents=True, exist_ok=True)

    ydl_opts = {
        'format': 'm4a/bestaudio/best',
        # ← ファイル名を固定（original.m4a）
        'outtmpl': str(output_dir / 'original.%(ext)s'),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'm4a',
        }]
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        error_code = ydl.download(args.urls)

if __name__ == '__main__':
    main()
