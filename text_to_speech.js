import "dotenv/config";
import fs from "fs";
import path from "path";
import os from "os"; // 一時ディレクトリ用に追加
import OpenAI from "openai";
import { RecursiveCharacterTextSplitter } from "@langchain/textsplitters";
import ffmpeg from "fluent-ffmpeg";
import { parseArgs } from "node:util";

// ==========================================
//  Configuration (設定)
// ==========================================
const CONFIG = {
  tts: {
    voice: "nova",
    speed: 1.0,
    model: "gpt-4o-mini-tts", // または "tts-1-hd"
  },
  text: {
    chunkSize: 400,
    separators: ["\n\n", "\n", "。", "、", ".", ",", " ", ""],
  },
  audio: {
    normalization: {
      targetI: -16,   // 目標ラウドネス (LUFS)
      targetTP: -1.5, // True Peak
      targetLRA: 11   // Loudness Range
    },
    paddingDuration: 1.0 // 前後の無音秒数
  },
  processing: {
    parallel: 3 // デフォルトの並列実行数
  }
};

// コマンドライン引数の解析
let args = {};
try {
  const { values, positionals } = parseArgs({
    options: {
      voice: { type: "string" },
      speed: { type: "string" },
      model: { type: "string" },
      chunk: { type: "string" },
      output: { type: "string", short: "o" },   // 出力パス (必須)
      "debug-dir": { type: "string" },          // デバッグ用出力ディレクトリ (指定時のみ保存)
      parallel: { type: "string", short: "p" }, // 並列数
    },
    allowPositionals: true,
  });

  args = { ...values, input: positionals[0] };

  // "--debug-dir" を内部名 debugDir にマッピングしておく
  if (values["debug-dir"]) {
    args.debugDir = values["debug-dir"];
  }

  // 引数で指定があればCONFIGを上書き
  if (args.voice) CONFIG.tts.voice = args.voice;
  if (args.speed) CONFIG.tts.speed = parseFloat(args.speed);
  if (args.model) CONFIG.tts.model = args.model;
  if (args.chunk) CONFIG.text.chunkSize = parseInt(args.chunk, 10);
  if (args.parallel) CONFIG.processing.parallel = parseInt(args.parallel, 10);

} catch (e) {
  console.warn("引数解析エラー:", e.message);
  process.exit(1);
}

const openai = new OpenAI();

// ==========================================
//  Services (機能モジュール)
// ==========================================

/**
 * ファイル・ディレクトリ管理クラス
 */
class FileManager {
  constructor(debugOutputDir = null) {
    this.debugOutputDir = debugOutputDir;
    // 作業用の一時ディレクトリパス (OSの一時フォルダ配下に作成)
    this.workDir = path.join(os.tmpdir(), `tts-work-${Date.now()}`);
    this.projectDir = this.workDir; // 作業は常に一時ディレクトリで行う
  }

  /**
   * 作業用ディレクトリを準備する
   */
  prepareWorkspace() {
    if (!fs.existsSync(this.workDir)) {
      fs.mkdirSync(this.workDir, { recursive: true });
    }
    return this.workDir;
  }

  /**
   * 作業ディレクトリ内のファイルパスを取得
   */
  getFilePath(fileName) {
    return path.join(this.workDir, fileName);
  }

  async saveText(fileName, content) {
    await fs.promises.writeFile(this.getFilePath(fileName), content);
  }

  async saveBuffer(fileName, buffer) {
    await fs.promises.writeFile(this.getFilePath(fileName), buffer);
  }

  /**
   * ストリームを使ってファイルを安全にコピーする内部ヘルパー
   */
  _copyFileStream(src, dest) {
    return new Promise((resolve, reject) => {
      const readStream = fs.createReadStream(src);
      const writeStream = fs.createWriteStream(dest);

      readStream.on("error", reject);
      writeStream.on("error", reject);
      
      writeStream.on("finish", resolve);

      readStream.pipe(writeStream);
    });
  }

  /**
   * 処理完了後の保存とクリーンアップ
   * @param {string} finalFileName - 生成された結合ファイルのファイル名
   * @param {string} destPath - ユーザーが指定した最終出力パス
   */
  async finalize(finalFileName, destPath) {
    const sourcePath = this.getFilePath(finalFileName);

    // 1. 最終成果物をユーザー指定のパスへコピー
    console.log(`ファイルを保存中: ${destPath}`);
    await this._copyFileStream(sourcePath, destPath);

    // 2. デバッグ出力先が指定されている場合、作業内容をバックアップ
    if (this.debugOutputDir) {
      const timestamp = new Date().toISOString().replace(/[-:T.]/g, "").slice(0, 14);
      const debugDirName = `tts-debug-${timestamp}`;
      const debugPath = path.join(this.debugOutputDir, debugDirName);
      
      console.log(`[DEBUG] 中間ファイルを保存中: ${debugPath}`);
      await this.copyDirectory(this.workDir, debugPath);
    }

    // 3. 作業ディレクトリの削除 (クリーンアップ)
    await this.cleanup();
  }

  async cleanup() {
    if (fs.existsSync(this.workDir)) {
      try {
        await fs.promises.rm(this.workDir, { recursive: true, force: true });
      } catch (e) {
        console.warn("一時ディレクトリの削除に失敗しました:", e.message);
      }
    }
  }

  // フォルダコピー用のヘルパー
  async copyDirectory(src, dest) {
    await fs.promises.mkdir(dest, { recursive: true });
    const entries = await fs.promises.readdir(src, { withFileTypes: true });

    for (const entry of entries) {
      const srcPath = path.join(src, entry.name);
      const destPath = path.join(dest, entry.name);

      if (entry.isDirectory()) {
        await this.copyDirectory(srcPath, destPath);
      } else {
        // ★修正: copyFile ではなく ストリームコピーを使用
        try {
          await this._copyFileStream(srcPath, destPath);
        } catch (e) {
          console.warn(`[DEBUG] コピー失敗: ${entry.name} - ${e.message}`);
        }
      }
    }
  }
}

/**
 * テキスト処理（読み込み・分割）
 */
const TextProcessor = {
  async readInput(filePath) {
    if (!filePath) throw new Error("Input file path is required");
    const text = await fs.promises.readFile(filePath, "utf-8");
    if (!text.trim()) throw new Error("File content is empty");
    return text;
  },

  async splitText(text, config) {
    const splitter = new RecursiveCharacterTextSplitter({
      chunkSize: config.chunkSize,
      chunkOverlap: 0,
      separators: config.separators,
    });
    return await splitter.createDocuments([text]);
  }
};

/**
 * OpenAI 音声生成
 */
const AudioGenerator = {
  async generate(text, config) {
    const mp3 = await openai.audio.speech.create({
      model: config.model,
      voice: config.voice,
      input: text,
      speed: config.speed,
    });
    return Buffer.from(await mp3.arrayBuffer());
  }
};

/**
 * FFmpeg 音声処理（無音生成・結合・正規化）
 */
const AudioProcessor = {
  createSilence(referenceFile, outputFile, duration) {
    return new Promise((resolve, reject) => {
      ffmpeg(referenceFile)
        .audioFilters('volume=0')
        .duration(duration)
        .save(outputFile)
        .on('end', () => resolve())
        .on('error', reject);
    });
  },

  async mergeAndNormalize(inputFiles, outputPath, config) {
    const silencePath = path.join(path.dirname(outputPath), "silence_padding.mp3");
    
    try {
      console.log(`\nフォーマット調整用の無音ファイルを生成中...`);
      await this.createSilence(inputFiles[0], silencePath, config.paddingDuration);

      const filesToConcat = [silencePath, ...inputFiles, silencePath];
      console.log(`結合・ノーマライズ中... (全${filesToConcat.length}ファイル)`);

      await new Promise((resolve, reject) => {
        const command = ffmpeg();
        filesToConcat.forEach(file => command.input(file));

        const filterInput = filesToConcat.map((_, i) => `[${i}:0]`).join('');
        const norm = config.normalization;
        const complexFilter = `${filterInput}concat=n=${filesToConcat.length}:v=0:a=1[cat];[cat]loudnorm=I=${norm.targetI}:TP=${norm.targetTP}:LRA=${norm.targetLRA}[out]`;

        command
          .complexFilter(complexFilter)
          .map('[out]')
          .audioCodec('libmp3lame')
          .save(outputPath)
          .on('end', resolve)
          .on('error', reject);
      });

    } finally {
      if (fs.existsSync(silencePath)) {
        fs.unlinkSync(silencePath);
      }
    }
  }
};

// ==========================================
//  Main Flow (メイン処理)
// ==========================================
async function main() {
  const fileManager = new FileManager(args.debugDir);

  try {
    const inputFilePath = args.input;
    const outputFilePath = args.output;
    
    // 引数チェック: 入力ファイルと出力先パスを必須とする
    if (!inputFilePath || !outputFilePath) {
      console.error("エラー: 入力ファイルと出力先の指定は必須です。");
      console.error("使用法: node text_to_speech.js <入力ファイル> --output <出力パス> [options]");
      console.error("例: node text_to_speech.js input.txt --output result.mp3 --debug-dir ./debug_output --parallel 5");
      process.exit(1);
    }

    // 1. 初期化と準備
    const workDir = fileManager.prepareWorkspace();
    
    console.log(`=== 開始 ===`);
    console.log(`入力: ${inputFilePath}`);
    console.log(`出力予定: ${outputFilePath}`);
    console.log(`作業ディレクトリ(一時): ${workDir}`);
    if (args.debugDir) console.log(`★デバッグモード有効: 完了後に ${args.debugDir} へログを保存します`);

    console.log(`設定: Model=${CONFIG.tts.model}, Voice=${CONFIG.tts.voice}, Speed=${CONFIG.tts.speed}, Chunk=${CONFIG.text.chunkSize}, Parallel=${CONFIG.processing.parallel}`);

    // 2. テキスト読み込み・分割
    const rawText = await TextProcessor.readInput(inputFilePath);
    const docs = await TextProcessor.splitText(rawText, CONFIG.text);
    console.log(`テキストを ${docs.length} パートに分割しました。`);

    // 結果格納用配列（インデックス順を保持するため確保）
    const chunkResults = new Array(docs.length).fill(null);
    
    // タスクのキュー作成（インデックス情報付き）
    const queue = docs.map((doc, index) => ({ doc, index }));
    
    // 3. 並列処理ロジック
    // 1つのチャンクを処理する関数
    const processChunk = async ({ doc, index }) => {
        const partText = doc.pageContent.trim();
        if (!partText) return;

        const seqNum = String(index + 1).padStart(3, '0');
        console.log(`Part ${index + 1}/${docs.length} 開始... (${partText.length}文字)`);

        // テキスト保存
        const textFileName = `part_${seqNum}.txt`;
        await fileManager.saveText(textFileName, partText);

        // 音声生成・保存
        const audioBuffer = await AudioGenerator.generate(partText, CONFIG.tts);
        const audioFileName = `part_${seqNum}.mp3`;
        await fileManager.saveBuffer(audioFileName, audioBuffer);
        
        // 結果を正しい位置に保存
        chunkResults[index] = fileManager.getFilePath(audioFileName);
        console.log(`Part ${index + 1}/${docs.length} 完了`);
    };

    // ワーカー: キューが空になるまで処理し続ける
    const concurrency = CONFIG.processing.parallel;
    const workers = new Array(Math.min(concurrency, queue.length)).fill(null).map(async (_, workerId) => {
        while (queue.length > 0) {
            const item = queue.shift();
            if (item) {
                try {
                    await processChunk(item);
                } catch (e) {
                    console.error(`[Worker ${workerId}] Chunk ${item.index + 1} Error:`, e.message);
                    throw e; // エラー時は停止（必要に応じてリトライロジックを追加可）
                }
            }
        }
    });

    console.log(`並列実行中 (最大 ${concurrency} 多重)...`);
    await Promise.all(workers);

    // null（スキップされた空行など）を除外
    const audioFileNames = chunkResults.filter(p => p !== null);

    // 4. 結合・仕上げ
    if (audioFileNames.length > 0) {
      const tempFinalName = "combined_temp.mp3";
      const tempFinalPath = fileManager.getFilePath(tempFinalName);

      // 一時ディレクトリ内で結合を実行
      await AudioProcessor.mergeAndNormalize(audioFileNames, tempFinalPath, CONFIG.audio);
      
      // 最終処理 (指定パスへの移動 + デバッグ保存 + 掃除)
      await fileManager.finalize(tempFinalName, outputFilePath);
      
      console.log(`\n=== 完了 ===`);
      console.log(`出力ファイル: ${outputFilePath}`);
    } else {
      console.log("処理可能なテキストがありませんでした。");
      await fileManager.cleanup();
    }

  } catch (error) {
    console.error("エラーが発生しました:", error.message);
    if (error.response) {
       console.error("API Error Detail:", error.response.data);
    }
    // エラー時も掃除を試みる
    await fileManager.cleanup();
    process.exit(1);
  }
}

main();