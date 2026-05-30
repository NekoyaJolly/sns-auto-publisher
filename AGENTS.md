# AGENTS.md

## プロジェクト概要

このリポジトリは、Telegram Bot に送信された画像・動画をPythonで受信し、保存・検証・変換・AI投稿文生成を行い、承認制または自動投稿モードでXへ投稿するためのSNS投稿オーケストレーターである。

このプロジェクトでは、n8nやGitHub Actionsを投稿パイプラインの中核として使わない。GitHubはソースコード管理とCI用途に限定し、メディア保存場所として使わない。

## MVPの目的

スマホからTelegram Botに画像・動画を送るだけで、Pythonアプリが以下を実行できる状態をMVP完成とする。

* Telegram Botから画像を受信できる
* Telegram Botから動画を受信できる
* 複数画像を扱える
* Pythonがメディアファイルをローカルストレージへ保存できる
* SQLiteに投稿ジョブとメディア情報を保存できる
* 画像・動画を検証できる
* 画像・動画を投稿用に変換できる
* AIがcaption / hashtags / alt_textを生成できる
* approval modeでTelegramに投稿プレビューを返せる
* 承認後にXへ投稿できる
* auto modeで検証OK後に自動投稿できる
* dry_run modeでXへ投稿せずに確認できる
* 投稿完了通知をTelegramへ返せる
* 投稿失敗時に理由をDBとTelegramに残せる
* GitHubにメディアを保存しない
* n8nを投稿パイプラインで使わない

## 重要な設計方針

### 1. GitHubにメディアを保存しない

GitHubリポジトリには画像・動画・生成物を保存しない。

禁止:

* `media/raw/` をGitHub管理下に置く
* 投稿用画像・動画をGitHubへpushする
* GitHub Actionsをメディア変換や投稿処理の中核にする

許可:

* ソースコード管理
* テスト
* lint
* CI
* READMEや設計ドキュメントの管理

### 2. MVPの入力元はTelegramのみ

MVPでは入力元をTelegram Botに限定する。

MVPでは実装しない:

* 任意フォルダ監視
* Google Drive監視
* メールボックス監視
* 他メッセンジャー連携
* 複数SNS投稿
* 投稿予約
* 管理画面

ただし、将来拡張しやすいように `inputs/` 配下でInput Adapterを分離する。

### 3. 投稿モードはMVP必須

MVPでは以下3つの投稿モードを必須とする。

* `approval`: Telegramに投稿プレビューを返し、承認ボタン押下後にXへ投稿する
* `auto`: 検証OKかつAI判定OKの場合に自動でXへ投稿する
* `dry_run`: Xへ投稿せず、投稿予定内容だけをTelegramへ返す

初期値は `approval` とする。

### 4. 状態管理を必ずDBに残す

投稿ジョブ、メディアファイル、投稿試行ログ、失敗理由をSQLiteに保存する。

状態管理なしで処理を直列実行するだけの実装は禁止する。

### 5. 実装は小さく、テスト可能に分割する

巨大な `main.py` に全処理を書くことを禁止する。

責務を以下のように分ける。

* `inputs/`: Telegramなどの入力処理
* `services/`: 検証、変換、AI生成、投稿制御
* `publishers/`: Xなど投稿先API
* `storage/`: ファイル保存処理
* `db/`: DBモデル、接続、repository
* `utils/`: MIME判定、ハッシュ計算、メディア解析など

## 推奨ディレクトリ構成

```text
telegram-x-auto-publisher/
  app/
    main.py

    config/
      settings.py

    inputs/
      telegram_input.py

    services/
      ingest_service.py
      validation_service.py
      media_process_service.py
      caption_service.py
      preview_service.py
      publish_service.py
      notify_service.py

    publishers/
      x_publisher.py

    storage/
      local_storage.py

    db/
      models.py
      session.py
      repository.py

    jobs/
      worker.py

    utils/
      file_hash.py
      mime_detect.py
      media_probe.py
      logger.py

  storage/
    raw/
    processed/
    thumbnails/

  data/
    app.sqlite3

  tests/
  docs/
  .env.example
  pyproject.toml
  README.md
```

## コーディング規約

* Python 3.11以上を前提とする
* 型ヒントを可能な限り付ける
* `any` 的な曖昧な型を乱用しない
* unknown型を乱用しない
* 例外を握りつぶさない
* 外部API呼び出しは必ず失敗時のログとDB記録を残す
* ファイル処理はpathlibを優先する
* 設定値は `.env` から読み込む
* 秘密情報をコードに直書きしない
* コメントを書く場合は日本語で書く
* README、docs、設計文書は日本語で書く

## 禁止事項

* GitHubへ画像・動画を保存する実装
* n8n前提の実装
* GitHub Actions前提の投稿処理
* DBなしの一発処理
* Telegram受信とX投稿を同じ関数に詰め込む実装
* 本番投稿APIをテスト中に無条件で叩く実装
* `dry_run` を無視する実装
* 失敗理由をログだけに出してDBに残さない実装
* `.env` に入るべき値をソースコードに直書きする実装

## 必須環境変数

`.env.example` に最低限以下を定義する。

```env
APP_ENV=local
POSTING_MODE=approval

TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_CHAT_IDS=

OPENAI_API_KEY=

X_API_KEY=
X_API_SECRET=
X_ACCESS_TOKEN=
X_ACCESS_TOKEN_SECRET=
X_BEARER_TOKEN=

DATABASE_URL=sqlite:///data/app.sqlite3

STORAGE_ROOT=storage
MAX_IMAGE_SIZE_MB=10
MAX_VIDEO_SIZE_MB=512
MAX_VIDEO_DURATION_SECONDS=140
```

## MVP完了条件

MVP完了は、次を全部満たした状態とする。

1. スマホからTelegram Botに画像を送れる
2. スマホからTelegram Botに動画を送れる
3. 複数画像を送れる
4. Pythonがファイルを保存できる
5. DBに投稿ジョブが残る
6. 画像/動画を検証できる
7. 画像/動画を投稿用に変換できる
8. AIがcaption / hashtags / alt_textを生成できる
9. approval modeでTelegramに投稿プレビューが返る
10. 承認後にXへ投稿できる
11. auto modeで検証OK後に自動投稿できる
12. dry_run modeで投稿せずに確認できる
13. 投稿完了通知がTelegramに返る
14. 投稿失敗時に理由がDBとTelegramに残る
15. GitHubにメディアを保存していない
16. n8nを投稿パイプラインで使っていない

## 実装時の進め方

Codexは、いきなり全MVPを一括実装しないこと。

まず以下を行う。

1. 現在のリポジトリ状態を確認する
2. 不足ファイルを洗い出す
3. MVP完成条件をチェックリスト化する
4. 最初の実装PR相当の範囲を提案する
5. その範囲だけ実装する
6. テストまたは起動確認を行う
7. 変更内容、未完了項目、次PR候補を報告する

## 優先実装順

1. Python基盤、設定、DB、storage
2. Telegram受信、raw保存
3. メディア検証
4. 画像処理
5. 動画処理
6. AI caption / hashtags / alt_text生成
7. Telegramプレビュー
8. approval / auto / dry_run モード管理
9. X投稿
10. 通知、リトライ、重複防止
11. テスト、README、運用ドキュメント

## 返答ルール

Codexは作業後、必ず以下を日本語で報告する。

* 実装した内容
* 変更したファイル
* 実行したコマンド
* テスト結果
* MVP完成条件のうち進んだ項目
* 未完了項目
* 次に実装すべきPR候補
