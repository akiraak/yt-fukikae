import "dotenv/config";
import { ChatOpenAI } from "@langchain/openai";
import { ChatPromptTemplate } from "@langchain/core/prompts";
import { StringOutputParser } from "@langchain/core/output_parsers";
import { RunnableSequence } from "@langchain/core/runnables";
import { RecursiveCharacterTextSplitter } from "@langchain/textsplitters";
import fs from "fs/promises";
import path from "path";

// ==========================================
// 設定 (Configuration)
// ==========================================
const CONFIG = {
  MODEL_NAME: "gpt-5.1",
  TEMPERATURE: 0,
  CHUNK_SIZE: 1000,
  CHUNK_OVERLAP: 0,
  CONCURRENCY_LIMIT: 3, // 同時に処理するチャンク数
  MAX_RETRIES: 3,       // エラー時の最大リトライ回数
};

// ==========================================
// プロンプト管理 (Prompts) - All English
// ==========================================
const PROMPTS = {
  DRAFT: ChatPromptTemplate.fromMessages([
    ["system", `You are a professional technical translator.
Translate the input text into Japanese strictly adhering to the following [Constraints].

[Constraints]
1. **Output Language**: Always output in Japanese.
2. **Keep English Terms**: Do not katakana-ize product names, codes, specific proper nouns, or technical terms (e.g., 'iPhone', 'Python', 'API') if the original English spelling is more natural for pronunciation or recognition. Keep them in English.
3. **Maintain Existing Japanese**: If parts of the input text are already in natural Japanese, keep them exactly as they are.
4. **TTS Optimization**: Translate for Text-To-Speech (TTS) purposes. Ensure the Japanese is audibly easy to understand with a natural rhythm. Break up sentences that are too long.
5. **No Superfluous Text**: Do not include explanations, notes, or conversational fillers. Output ONLY the translated text string.`],
    ["user", "{original_text}"]
  ]),

  CRITIQUE: ChatPromptTemplate.fromMessages([
    ["system", `You are a translation quality assurance specialist.
Compare the "Original Text" and the "Translation Draft", and list improvement points based on the following criteria.

[Check Criteria]
1. **Technical Terms**: Are technical terms or library names unnecessarily katakana-ized? (Keep them in English if that is more natural).
2. **TTS Suitability**: Is the rhythm poor when heard via TTS, or are sentences too long causing unnatural pauses?
3. **Accuracy & Naturalness**: Are there mistranslations? Has existing Japanese content been altered unnaturally?

If there are no issues, output only "No issues".`],
    ["user", "Original Text: {original_text}\n\nTranslation Draft: {initial_translation}"]
  ]),

  REFINE: ChatPromptTemplate.fromMessages([
    ["system", `You are a professional editor.
Create the **final translation** optimized for TTS based on the "Original Text", "Initial Translation", and "Critique".
If there are no critiques, output the initial translation as is.`],
    ["user", `Original Text: {original_text}
Initial Translation: {initial_translation}
Critique: {critique}`]
  ])
};

// ==========================================
// ユーティリティ: リトライ処理
// ==========================================
async function withRetry(fn, retries = 3, delay = 1000) {
  try {
    return await fn();
  } catch (error) {
    if (retries <= 0) throw error;
    console.warn(`  ⚠️ エラー発生。リトライします (残り${retries}回): ${error.message}`);
    await new Promise(res => setTimeout(res, delay));
    return withRetry(fn, retries - 1, delay * 2);
  }
}

// ==========================================
// クラス: 翻訳サービス (TranslationService)
// ==========================================
class TranslationService {
  constructor() {
    this.model = new ChatOpenAI({
      modelName: CONFIG.MODEL_NAME,
      temperature: CONFIG.TEMPERATURE
    });
    this.chain = this._buildChain();
  }

  _buildChain() {
    return RunnableSequence.from([
      // Step 1: Draft
      async (input) => {
        const initialTranslation = await PROMPTS.DRAFT
          .pipe(this.model)
          .pipe(new StringOutputParser())
          .invoke(input);
        return { ...input, initial_translation: initialTranslation };
      },
      // Step 2: Critique
      async (input) => {
        const critique = await PROMPTS.CRITIQUE
          .pipe(this.model)
          .pipe(new StringOutputParser())
          .invoke(input);
        return { ...input, critique };
      },
      // Step 3: Refine
      async (input) => {
        const prefix = input.chunk_id ? `[Chunk ${input.chunk_id}]` : "";
        let finalTranslation;

        const critiqueSnippet = input.critique.replace(/\n/g, " ").slice(0, 40);
        
        if (input.critique.includes("No issues") || input.critique.includes("問題なし")) {
          console.log(`  ${prefix} 査読: 問題なし (${critiqueSnippet}...)`);
          finalTranslation = await PROMPTS.REFINE
            .pipe(this.model)
            .pipe(new StringOutputParser())
            .invoke({
              ...input,
              critique: "No changes needed."
            });
        } else {
          console.log(`  ${prefix} 査読: 指摘あり (${critiqueSnippet}...)`);
          finalTranslation = await PROMPTS.REFINE
            .pipe(this.model)
            .pipe(new StringOutputParser())
            .invoke(input);
        }

        return {
          draft: input.initial_translation,
          critique: input.critique,
          refine: finalTranslation
        };
      }
    ]);
  }

  async translateChunk(text, chunkIndex, totalChunks) {
    console.log(`Processing Chunk ${chunkIndex + 1}/${totalChunks}...`);
    return withRetry(async () => {
      const result = await this.chain.invoke({ 
        original_text: text,
        chunk_id: chunkIndex + 1
      });
      console.log(`  ✓ Chunk ${chunkIndex + 1} Done.`);
      return result;
    }, CONFIG.MAX_RETRIES);
  }
}

// ==========================================
// クラス: アプリケーション (App)
// ==========================================
class App {
  /**
   * @param {string} inputPath         - 入力ファイルのパス（例: outputs/BBC/transcribe.txt）
   * @param {string} finalOutputPath   - 最終出力ファイルのパス（例: outputs/BBC/transcribe_ja.txt）
   * @param {string} debugDir          - 一時ファイル・デバッグ用ディレクトリ（例: outputs/BBC/work_translate）
   */
  constructor(inputPath, finalOutputPath, debugDir) {
    this.inputPath = inputPath;

    const finalDir = path.dirname(finalOutputPath);
    const finalBaseName = path.basename(finalOutputPath, path.extname(finalOutputPath));

    this.outputPaths = {
      rootDir: finalDir,                                        // 最終出力のディレクトリ
      final: finalOutputPath,                                   // 最終ファイル
      draft: path.join(debugDir, `${finalBaseName}_draft.txt`), // Draft は debug 側に寄せる
      debugDir,                                                 // チャンクごとの詳細ログ
    };

    this.translator = new TranslationService();
  }

  async run() {
    console.log(`=== 翻訳開始: ${this.inputPath} ===`);

    // 0. 準備: 出力ディレクトリの作成
    try {
      await fs.mkdir(this.outputPaths.rootDir, { recursive: true });
      await fs.mkdir(this.outputPaths.debugDir, { recursive: true });

      console.log(`出力ディレクトリ: ${this.outputPaths.rootDir}`);
      console.log(`デバッグディレクトリ: ${this.outputPaths.debugDir}`);
    } catch (e) {
      console.warn("フォルダ作成警告:", e.message);
    }

    // 1. ファイル読み込み
    let text;
    try {
      text = await fs.readFile(this.inputPath, "utf-8");
      if (!text.trim()) throw new Error("File is empty");
    } catch (e) {
      console.error("❌ ファイル読み込みエラー:", e.message);
      return;
    }

    // 2. 分割
    const splitter = new RecursiveCharacterTextSplitter({
      chunkSize: CONFIG.CHUNK_SIZE,
      chunkOverlap: CONFIG.CHUNK_OVERLAP,
      separators: ["\n\n", "\n", ".", "。", "!", "！", "?", "？"],
    });
    const docs = await splitter.createDocuments([text]);
    console.log(`Total Chunks: ${docs.length}`);

    // 3. バッチ処理
    const results = [];
    for (let i = 0; i < docs.length; i++) results.push(null);

    for (let i = 0; i < docs.length; i += CONFIG.CONCURRENCY_LIMIT) {
      const batch = docs.slice(i, i + CONFIG.CONCURRENCY_LIMIT);
      
      await Promise.all(
        batch.map((doc, idx) => {
          const globalIndex = i + idx;
          return this.translator
            .translateChunk(doc.pageContent, globalIndex, docs.length)
            .then(async (res) => {
              results[globalIndex] = res;

              const chunkId = String(globalIndex + 1).padStart(3, "0");

              // デバッグ用: 各ステップを個別ファイルに保存（debugDir配下）
              await fs.writeFile(
                path.join(this.outputPaths.debugDir, `chunk_${chunkId}_original.txt`),
                doc.pageContent,
                "utf-8"
              );
              await fs.writeFile(
                path.join(this.outputPaths.debugDir, `chunk_${chunkId}_draft.txt`),
                res.draft,
                "utf-8"
              );
              await fs.writeFile(
                path.join(this.outputPaths.debugDir, `chunk_${chunkId}_critique.txt`),
                res.critique,
                "utf-8"
              );
              await fs.writeFile(
                path.join(this.outputPaths.debugDir, `chunk_${chunkId}_refine.txt`),
                res.refine,
                "utf-8"
              );
            })
            .catch((err) => {
              console.error(`❌ Chunk ${globalIndex + 1} Error:`, err.message);
              const errorMsg = `[Error]\n${doc.pageContent}`;
              results[globalIndex] = {
                draft: errorMsg,
                critique: "Error",
                refine: errorMsg,
              };
            });
        })
      );
    }

    // 4. 結果の結合と保存
    const fullDraft = results.map((r) => r.draft).join("\n\n");
    await fs.writeFile(this.outputPaths.draft, fullDraft, "utf-8");

    const fullFinal = results.map((r) => r.refine).join("\n\n");
    await fs.writeFile(this.outputPaths.final, fullFinal, "utf-8");

    console.log(`\n=== 完了 ===`);
    console.log(`  - 最終結果: ${this.outputPaths.final}`);
    console.log(`  - 下訳(Draft): ${this.outputPaths.draft}`);
    console.log(`  - 詳細ログ: ${this.outputPaths.debugDir}/*.txt`);
  }
}

// ==========================================
// エントリーポイント
// ==========================================

// 第1引数: 入力テキスト
const inputFile = process.argv[2] || "input_en.txt";
// 第2引数: 最終出力ファイル
const finalOutputFile = process.argv[3] || "output_ja.txt";
// 第3引数: debug / 一時ファイル用ディレクトリ
const debugDir = process.argv[4] || "outputs/work_translate";

const app = new App(inputFile, finalOutputFile, debugDir);
app.run();
