import OpenAI from "openai";
import fs from "fs";
import path from "path";
import { spawn } from "child_process";
import "dotenv/config";
import { File } from "node:buffer";

/* =========================
 * 調整用の定数（ここだけいじればOK）
 * ========================= */

// 入出力ファイルのデフォルト
const DEFAULT_INPUT_AUDIO = "input.m4a";
const DEFAULT_OUTPUT_TEXT = "output.txt";

// 分割ファイル関連
const SEGMENTS_DIR = "segments";
const SEGMENT_FILE_PREFIX = "segment_";
const SEGMENT_FILE_EXT = ".m4a";

// 無音検出パラメータ（ffmpeg silencedetect）
const SILENCE_NOISE_DB = "-30dB";  // 無音とみなす音量しきい値
const SILENCE_MIN_DURATION_SEC = 0.5; // これ以上続いた無音を切れ目候補にする
const SILENCE_FILTER = `silencedetect=noise=${SILENCE_NOISE_DB}:d=${SILENCE_MIN_DURATION_SEC}`;

// セグメント長の制約
const MIN_SEGMENT_SEC = 60; // 1区間の最小長（これ未満なら切らない）
const MIN_TAIL_SEC = 1;     // 最後にこの秒数以上残っていたら終端セグメントとして追加

// OpenAI 関連
const TRANSCRIBE_MODEL = "gpt-4o-transcribe";

// ffmpeg / ffprobe コマンド名（必要ならフルパスに変更）
const FFMPEG_BIN = "ffmpeg";
const FFPROBE_BIN = "ffprobe";

// セグメントごとの個別テキスト保存をするか
const SAVE_PER_SEGMENT_TEXT = true;

/* =========================
 * 初期化
 * ========================= */

// Node 18 で File が未定義なケースへの対策
if (!globalThis.File) {
  globalThis.File = File;
}

const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
});

/* =========================
 * ffprobe で音声の総時間を取得
 * ========================= */
function getDurationSec(inputPath) {
  return new Promise((resolve, reject) => {
    const ff = spawn(FFPROBE_BIN, [
      "-v",
      "error",
      "-show_entries",
      "format=duration",
      "-of",
      "default=nk=1:nw=1",
      inputPath,
    ]);

    let out = "";
    let err = "";

    ff.stdout.on("data", (data) => {
      out += data.toString();
    });

    ff.stderr.on("data", (data) => {
      err += data.toString();
    });

    ff.on("close", (code) => {
      if (code !== 0) {
        return reject(new Error(`ffprobe error: ${err}`));
      }
      const sec = parseFloat(out.trim());
      if (Number.isNaN(sec)) {
        return reject(new Error(`duration parse error: ${out}`));
      }
      resolve(sec);
    });

    ff.on("error", (e) => reject(e));
  });
}

/* =========================
 * ffmpeg silencedetect で無音区間を検出
 * ========================= */
function detectSilences(inputPath) {
  return new Promise((resolve, reject) => {
    const ff = spawn(FFMPEG_BIN, [
      "-i",
      inputPath,
      "-af",
      SILENCE_FILTER,
      "-f",
      "null",
      "-",
    ]);

    let stderr = "";

    ff.stderr.on("data", (data) => {
      stderr += data.toString();
    });

    ff.on("close", (code) => {
      if (code !== 0) {
        // silencedetect は成功でも 0 以外を返すことがあるので、ここでは警告だけ
        console.warn("ffmpeg silencedetect exited with code", code);
      }

      const silences = [];
      const lines = stderr.split("\n");
      let lastSilenceStart = null;

      for (const line of lines) {
        const mStart = line.match(/silence_start:\s*([0-9.]+)/);
        if (mStart) {
          lastSilenceStart = parseFloat(mStart[1]);
          continue;
        }
        const mEnd = line.match(/silence_end:\s*([0-9.]+)/);
        if (mEnd && lastSilenceStart != null) {
          const end = parseFloat(mEnd[1]);
          const durMatch = line.match(/silence_duration:\s*([0-9.]+)/);
          const dur = durMatch ? parseFloat(durMatch[1]) : end - lastSilenceStart;
          silences.push({ start: lastSilenceStart, end, duration: dur });
          lastSilenceStart = null;
        }
      }

      resolve(silences);
    });

    ff.on("error", (err) => reject(err));
  });
}

/* =========================
 * 無音情報を使ってセグメントを決めて、実ファイルに分割
 * ========================= */
// strategy:
//   0 秒からスタートし、MIN_SEGMENT_SEC 以上経過した無音 end を区切りとする
async function splitAudioBySilence(inputPath, outDir) {
  const duration = await getDurationSec(inputPath);
  const silences = await detectSilences(inputPath);

  if (!fs.existsSync(outDir)) {
    fs.mkdirSync(outDir, { recursive: true });
  }

  const segments = [];
  let lastCut = 0;

  for (const s of silences) {
    if (s.end - lastCut >= MIN_SEGMENT_SEC) {
      segments.push({ start: lastCut, end: s.end });
      lastCut = s.end;
    }
  }

  // 最後の部分
  if (duration - lastCut > MIN_TAIL_SEC) {
    segments.push({ start: lastCut, end: duration });
  }

  console.log("検出されたセグメント:");
  console.log(segments);

  // 実際にファイルを切り出し
  const segmentPaths = [];

  for (let i = 0; i < segments.length; i++) {
    const seg = segments[i];
    const fileIndex = String(i + 1).padStart(3, "0");
    const outFile = path.join(
      outDir,
      `${SEGMENT_FILE_PREFIX}${fileIndex}${SEGMENT_FILE_EXT}`,
    );

    await new Promise((resolve, reject) => {
      const ff = spawn(FFMPEG_BIN, [
        "-y",
        "-i",
        inputPath,
        "-ss",
        String(seg.start),
        "-to",
        String(seg.end),
        "-c",
        "copy", // 再エンコードなし。問題があれば "aac" などに変更
        outFile,
      ]);

      ff.stderr.on("data", (d) => {
        // デバッグしたいときは表示
        // process.stderr.write(d);
      });

      ff.on("close", (code) => {
        if (code !== 0) {
          return reject(new Error(`ffmpeg segment failed: code ${code}`));
        }
        resolve();
      });

      ff.on("error", reject);
    });

    segmentPaths.push(outFile);
  }

  return segmentPaths;
}

/* =========================
 * 1ファイルを文字起こししてテキストを返す
 * ========================= */
async function transcribeSegment(audioFilePath) {
  console.log(`文字起こし開始: ${audioFilePath}`);

  const transcription = await openai.audio.transcriptions.create({
    file: fs.createReadStream(audioFilePath),
    model: TRANSCRIBE_MODEL,
  });

  return transcription.text;
}

/* =========================
 * メイン処理
 * ========================= */
async function main() {
  try {
    const inputAudioFile = process.argv[2] ?? DEFAULT_INPUT_AUDIO;
    const outputTextFile = process.argv[3] ?? DEFAULT_OUTPUT_TEXT;
    const workDirArg = process.argv[4] ?? null;   // ★ 追加: 作業用ディレクトリ

    if (!fs.existsSync(inputAudioFile)) {
      throw new Error(`音声ファイルが見つかりません: ${inputAudioFile}`);
    }

    // ★ セグメント出力先を決めるロジック
    //    1) 第3引数で workDir が指定されていたらそれを使う
    //    2) 指定が無ければ、従来どおり outputTextFile から派生
    let segmentsDir;
    if (workDirArg) {
      segmentsDir = workDirArg;
    } else {
      const outputDir = path.dirname(outputTextFile);
      const outputBaseName = path.parse(outputTextFile).name;
      segmentsDir = path.join(outputDir, outputBaseName);
    }

    console.log("無音検出＆分割中...");
    const segmentPaths = await splitAudioBySilence(inputAudioFile, segmentsDir);

    if (segmentPaths.length === 0) {
      console.log("無音が検出されなかったので、ファイル全体を1つとして文字起こしします。");
      const text = await transcribeSegment(inputAudioFile);
      fs.writeFileSync(outputTextFile, text, "utf8");
      console.log(`保存先: ${outputTextFile}`);
      return;
    }

    // 各セグメントを順番に文字起こし
    let allText = "";

    for (let i = 0; i < segmentPaths.length; i++) {
      const segPath = segmentPaths[i];
      const segText = await transcribeSegment(segPath);

      allText += segText + "\n\n";

      if (SAVE_PER_SEGMENT_TEXT) {
        const fileIndex = String(i + 1).padStart(3, "0");
        const segTxtPath = path.join(
          segmentsDir,
          `${SEGMENT_FILE_PREFIX}${fileIndex}.txt`,
        );
        fs.writeFileSync(segTxtPath, segText, "utf8");
      }
    }

    fs.writeFileSync(outputTextFile, allText.trim(), "utf8");
    console.log("------------------------------------------------");
    console.log("全セグメントの文字起こしが完了しました！");
    console.log(`結合テキストの保存先: ${outputTextFile}`);
    console.log("セグメント出力ディレクトリ:", segmentsDir);
    console.log("------------------------------------------------");
  } catch (err) {
    console.error("エラーが発生しました:", err);
  }
}

main();