# agents-md-template

複数 AI コーディングエージェント (Claude Code / Cursor / Gemini 等) を 1 プロジェクトで運用するための **AGENTS.md 系ルールセットのテンプレート**。

`AGENTS.md` を正本とし、各 AI 固有のシム (`CLAUDE.md` / `.cursorrules` / `GEMINI.md`) が同じルールを参照する構造になっています。実プロジェクトで使い倒した結果を抽出してテンプレ化したもので、初期セットアップから「ルール分散による認識ズレ」「ファイル増殖」「ドキュメント増殖」を抑えられます。

## 含まれるもの

| ファイル | 内容 |
|---|---|
| `AGENTS.md` | 全エージェント共通ルールの正本テンプレ (§1 読み込み義務 / §2 型安全 / §3 コード品質 / §4 言語規約 / §5 ドキュメント運用 / §6 PR・コミット規約 + ドメイン原則のプレースホルダー + AI 推論品質ガイドライン) |
| `CLAUDE.md` | Claude Code 固有シム (作業着手前宣言、チケット commit 規約) |
| `.cursorrules` | Cursor 固有シム (Composer 確認、any/unknown 補完拒否) |
| `GEMINI.md` | Gemini 固有シム (共通規約遵守、将来追記スロット) |
| `scripts/README.md` | `scripts/` ディレクトリの登録表 + 用途分類 + one-shot 制限 |
| `docs/architecture/WORKFLOW.md` | 自走 PR ワークフロー (Copilot inline 対応 / merge polling / post-merge 瞬間チェック / 自動 lint 修正) |
| `templates/last-mile-rule.md` | Last-Mile Shared Context Protocol を採用するプロジェクト向けの AGENTS.md 挿入テンプレ ([姉妹リポジトリ](https://github.com/NekoyaJolly/last-mile-shared-context) の `templates/AGENTS.last-mile.md` と内容同期) |
| `LICENSE` | MIT |

## 主な思想

- **正本 1 つ、シムは誘導**: ルールは `AGENTS.md` に集約。シムは「正本を読め」と誘導するだけ。AI ごとに微妙に違うルールセットを書かない
- **新規ファイル作成は最終手段**: 「作業の副産物」ではなく「設計上の追加物」として扱う (§5.3)。PR 説明に責務 / 統合しなかった理由 / 寿命 / 削除条件を必須化
- **ドキュメントはローリング運用**: 正本 + 現在進行中フェーズの指示書 + サマリー 1 件 の 3 種類だけ。完了したフェーズノートは正本に統合してアーカイブ / 削除する (§5.0)
- **`any` / `unknown` 禁止 (本番コード)**: 外部入力はスキーマで narrow。型チェック抑止コメントの濫用も禁止 (§2)

## 使い方

### A. GitHub Template repository として使う (推奨)

1. GitHub 上で「Use this template」ボタンを押して新規リポジトリを作成
2. 新リポジトリを `git clone`
3. このリポジトリの `README.md` (本ファイル) を **新プロジェクトの README に上書き**
4. `AGENTS.md` 冒頭のコメント指示に従い、プレースホルダーを埋める
   - `<PROJECT_NAME>`: プロジェクト名
   - `<DOMAIN>`: ドメイン名 (例: 自律トレーディング AI / SaaS 課金システム)
   - `<PRIMARY_LANGUAGE>`: 主要言語 (例: 日本語 / English)
   - 「ドメイン原則」セクション: プロジェクト固有の不変ルールを書く
   - 「開発運用情報」セクション: コマンド / 構造 / 技術スタックをプロジェクトのものに書き換える
5. 不要なシムを削除 (例: Cursor を使わないなら `.cursorrules` を削除)
6. `scripts/` を使い始める時に `scripts/README.md` の登録表に追記
7. 初回コミット

### B. 既存リポジトリに導入する

1. このリポジトリを `git clone` し、必要なファイルを既存リポジトリにコピー
2. 上記 A の §4 〜 §6 と同じ作業

## プレースホルダー一覧

テンプレ化のために以下を残しています。実プロジェクトでは置換してください。

| プレースホルダー | 置換例 |
|---|---|
| `<PROJECT_NAME>` | `MyAwesomeApp` |
| `<DOMAIN>` | `EC サイト` / `自律トレーディング AI` |
| `<PRIMARY_LANGUAGE>` | `日本語` / `English` |
| `<対象領域>` | サブディレクトリ AGENTS.md を作る時の領域名 |
| `<build command>` | `npm run build` / `cargo build` 等 |
| `<test command>` | `npm test` / `pytest` 等 |
| `<dev command>` | `npm run dev` / `python manage.py runserver` 等 |


## ライセンス

[MIT](./LICENSE)
