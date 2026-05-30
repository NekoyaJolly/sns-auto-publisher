<!--
このファイルは `last-mile-shared-context` プロトコルの AGENTS.md 挿入用テンプレ。

由来:
  本 `agents-md-template` の姉妹リポジトリ `last-mile-shared-context`
  (https://github.com/NekoyaJolly/last-mile-shared-context) で運用している
  `templates/AGENTS.last-mile.md` を、agents-md-template 側にも同期配置したもの。
  両リポジトリで内容は同一を保つ (= 一方を更新したらもう片方に反映する)。

利用手順:
  1. 対象プロジェクトの AGENTS.md (またはルート CLAUDE.md) のドメイン原則セクションに
     本ファイルの「## Last-Mile Shared Context Rule」セクション以下をコピー&ペーストする
  2. プロジェクト固有の Domain ID / 主要画面 / ボタン名を必要に応じて追記する
  3. 既存ルールと重複する箇所は省略してよい (中核ルールは省略しないこと)

このテンプレを使うには:
  - 対象プロジェクトに `last-mile-shared-context` をインストール (CLI / MCP / Bridge 等)
  - 設定の詳細は https://github.com/NekoyaJolly/last-mile-shared-context の各 docs 参照
-->

## Last-Mile Shared Context Rule

UI・UX・API 連携・DB 状態・Job 状態に関する **ラストマイル修正** では、コードだけで判断してはならない。

修正前に必ず **Last-Mile Bundle** を確認する。

### 1. 必ず確認する 9 項目

| # | 確認対象 | 取得元 |
|---|---|---|
| 1 | 対象画面 | `page.url` / `page.title` / `debugContext.screen` |
| 2 | 操作手順 | `userObservation.lastAction` (人間が書く) |
| 3 | 期待値 | `userObservation.expected` (人間が書く) |
| 4 | 実際の挙動 | `userObservation.actual` (人間が書く) |
| 5 | Console | `console.errors` / `console.warnings` |
| 6 | Network | `network.failedRequests` / `network.recentRequests` |
| 7 | AI Debug Context | `debugContext` (= アプリ側 `window.__AI_DEBUG_CONTEXT__`) |
| 8 | Domain ID | `debugContext.target.id` / `debugContext.target.relatedIds` |
| 9 | Server log | `server.errors` / `server.hints` |

### 2. 取得手段

- **CLI**: `pnpm lastmile collect --last-action "..." --expected "..." --actual "..."`
- **MCP**: `collect_last_mile_bundle` tool を AI から呼ぶ
- **手動**: アプリの **Copy AI Context** ボタン → AI へ貼り付け + UI Issue Report テンプレ記入

### 3. 原因分類 (Bundle を見て決める)

| 兆候 | 分類 |
|---|---|
| `server.errors[]` あり | Server |
| `network.failedRequests[]` に status>=500 | API |
| `network.failedRequests[]` で 5xx 以外 | Network |
| `console.errors[]` あり | UI |
| 上記なし & `userObservation.expected !== actual` | UX |
| 何もなし | NoIssue / Unknown |

`@last-mile-context/core` の `classifyIssue(bundle)` で雛形分類が得られる。

### 4. 守るべき原則

1. **原因分類なしに修正してはならない**: Bundle を見ずに「ここっぽい」で修正しない
2. **修正後に再収集して回帰確認**: 同じ Bundle 観点で改善を確認する
3. **再発防止のため Playwright spec / checklist 化**: 解決したラストマイル issue は再現手順またはテスト雛形に落とす
4. **`window.__AI_DEBUG_CONTEXT__` に token / 個人情報を入れない**: アプリ側で最初から入れない (redaction は最終防衛線)
5. **Bundle に含まれる Authorization / Cookie / JWT は redaction で自動マスク**: ただし、AI に渡す前に `lastmile mask <path> --strict` で再確認すると安全

### 5. ログイン前提画面の扱い

- Chrome を `--remote-debugging-port=9222 --user-data-dir=.chrome-lastmile` で起動し、開発者が事前にそのプロファイルへログインしておく
- collector は既存セッションを共有して認証済ページを取得する
- Playwright を使う場合は `storageState` で認証済セッションを保存し、各テストで読み込む
- Bundle に含まれる token / Authorization は redaction で必ずマスクされる

### 6. 参照ドキュメント

last-mile-shared-context リポジトリ (https://github.com/NekoyaJolly/last-mile-shared-context) 内:

- `docs/LAST_MILE_PROTOCOL.md` — プロトコル全体規約
- `docs/AI_DEBUG_CONTEXT.md` — `window.__AI_DEBUG_CONTEXT__` 仕様
- `docs/CLI_USAGE.md` — `lastmile` CLI コマンド
- `docs/MCP_USAGE.md` — MCP server 設定 / tool 仕様
- `docs/SECURITY.md` — Redaction / 機密マスク
- `docs/PROJECT_INTEGRATION_GUIDE.md` — 既存プロジェクトへの導入手順
