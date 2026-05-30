# MVP実装指示書

## プロジェクト名

Sns Auto Publisher

## 概要

Telegram Botに送信された画像・動画をPythonで受信し、保存、検証、変換、AI投稿文生成、Telegramプレビュー、承認または自動投稿、X投稿、完了通知までを行う。

n8nとGitHub Actionsは投稿パイプラインから外す。GitHubはソースコード管理とCIに限定し、メディア保存先として使わない。

## MVPスコープ

### MVPに含める

* Telegram Botによる画像受信
* Telegram Botによる動画受信
* 複数画像対応
* ローカルストレージ保存
* SQLiteによる状態管理
* 画像バリデーション
* 動画バリデーション
* 画像変換
* 動画変換
* FFmpeg連携
* サムネイル生成
* AIによるcaption生成
* AIによるhashtags生成
* AIによるalt_text生成
* Telegram投稿プレビュー
* approval mode
* auto mode
* dry_run mode
* X投稿
* Telegram完了通知
* 失敗理由のDB保存
* 失敗理由のTelegram通知

### MVPに含めない

* 任意フォルダ監視
* Google Drive監視
* メールボックス監視
* 他メッセンジャー対応
* 複数SNS投稿
* 投稿予約
* 管理画面
* チーム権限管理
* 分析ダッシュボード
* クラウドストレージ移行

## アーキテクチャ

```text
スマホ
  ↓
Telegram Bot
  ↓
Python App
  ↓
保存・DB登録
  ↓
検証
  ↓
画像/動画変換
  ↓
AI投稿文生成
  ↓
Telegramプレビュー
  ↓
approval / auto / dry_run 分岐
  ↓
X投稿
  ↓
Telegram完了通知
```

## ディレクトリ構成

```text
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
```

## DB設計

### post_jobs

投稿単位のジョブを管理する。

```text
id
source_type
source_chat_id
source_user_id
mode
status
caption
hashtags_json
alt_text
ai_warnings_json
x_post_id
error_message
created_at
updated_at
```

### media_assets

画像・動画ファイル単位の情報を管理する。

```text
id
post_job_id
original_path
processed_path
thumbnail_path
media_type
mime_type
file_hash
file_size
width
height
duration_seconds
status
error_message
created_at
updated_at
```

### post_attempts

X投稿など外部投稿APIの試行ログを管理する。

```text
id
post_job_id
provider
request_payload_json
response_payload_json
status
error_message
created_at
```

### app_settings

アプリ設定を管理する。

```text
key
value
updated_at
```

## status定義

### post_jobs.status

```text
received
validating
validated
processing
processed
captioning
captioned
preview_sent
waiting_approval
publishing
published
rejected
failed
```

### media_assets.status

```text
received
validated
processed
rejected
failed
```

## 投稿モード仕様

### approval

Telegramに投稿プレビューを返し、ユーザーが承認した場合のみXへ投稿する。

必要なボタン:

```text
投稿する
再生成
却下
```

### auto

検証OK、AI生成OK、重大警告なしの場合に自動でXへ投稿する。

自動投稿条件:

```text
メディア検証OK
AI生成JSONが正しい
captionが空ではない
should_post = true
重大なwarningsがない
許可済みchat_idである
```

### dry_run

Xへ投稿しない。投稿予定内容だけTelegramへ返し、DBにはdry_runとして記録する。

## AI出力形式

AI出力は必ずJSONとして扱う。

```json
{
  "caption": "投稿本文",
  "hashtags": ["#example"],
  "alt_text": "画像や動画の説明",
  "warnings": [],
  "should_post": true
}
```

JSONとしてパースできない場合は `failed` とする。

## 実装PR計画

### PR 1: 基盤 + DB + storage

目的:

* Pythonプロジェクト基盤を作る
* `.env` 読み込み
* SQLite接続
* DBモデル作成
* ローカルストレージ保存基盤作成

完了条件:

* アプリが起動できる
* DBに接続できる
* `post_jobs` を作成できる
* `media_assets` を作成できる
* raw / processed / thumbnails ディレクトリを扱える

### PR 2: Telegram受信 + raw保存

目的:

* Telegram Botで画像・動画を受け取る
* ファイルをローカルへ保存する
* DBにジョブを登録する

完了条件:

* スマホから画像を送ると保存される
* スマホから動画を送ると保存される
* DBにpost_jobとmedia_assetが作られる
* Telegramに受信通知が返る

### PR 3: 検証 + 画像処理

目的:

* 画像を検証し、投稿用に変換する

完了条件:

* 画像/動画以外を拒否できる
* 壊れた画像をfailedにできる
* EXIF削除ができる
* 画像リサイズができる
* サムネイルを生成できる

### PR 4: 動画処理

目的:

* 動画を検証し、投稿用mp4へ変換する

完了条件:

* iPhone動画をmp4化できる
* Android動画をmp4化できる
* 秒数とサイズを検証できる
* 動画サムネイルを生成できる
* FFmpeg失敗時にfailedへできる

### PR 5: AI生成

目的:

* caption / hashtags / alt_text をAIで生成する

完了条件:

* AI出力をJSONとして受け取れる
* captionをDBに保存できる
* hashtagsをDBに保存できる
* alt_textをDBに保存できる
* should_post=falseの場合は投稿へ進まない

### PR 6: Telegramプレビュー + 承認

目的:

* Telegramへ投稿プレビューを返し、承認・再生成・却下を扱う

完了条件:

* プレビューをTelegramに返せる
* 投稿するボタンでpublishingへ進む
* 再生成ボタンでAI生成をやり直せる
* 却下ボタンでrejectedにできる

### PR 7: 投稿モード管理

目的:

* approval / auto / dry_run を切り替えられるようにする

完了条件:

* `/mode` で現在モードを確認できる
* `/mode approval` でapprovalへ変更できる
* `/mode auto` でautoへ変更できる
* `/mode dry_run` でdry_runへ変更できる
* 各モードで処理分岐が正しく動く

### PR 8: X投稿

目的:

* 処理済みメディアをXへ投稿する

完了条件:

* 画像1枚をXへ投稿できる
* 複数画像をXへ投稿できる
* 動画をXへ投稿できる
* 投稿成功時にx_post_idを保存できる
* 投稿失敗時にpost_attemptsへ記録できる

### PR 9: 通知 + リトライ + 重複防止

目的:

* 実運用に必要な通知、再実行、二重投稿防止を入れる

完了条件:

* 投稿完了通知をTelegramへ返せる
* 投稿失敗通知をTelegramへ返せる
* file_hashで重複検知できる
* 投稿済みjobの二重投稿を防げる
* `/retry <job_id>` で失敗jobを再実行できる
* `/status <job_id>` で状態確認できる

### PR 10: テスト + README

目的:

* 新規環境で起動できる状態にする
* MVP完成条件を確認できる状態にする

完了条件:

* READMEが日本語で整備されている
* `.env.example` が整備されている
* dry_run手順が書かれている
* Telegram Bot設定手順が書かれている
* X API設定手順が書かれている
* 画像正常系テストがある
* 動画正常系テストがある
* rejected/failedの異常系テストがある

## MVP完成条件チェックリスト

* [x] スマホからTelegram Botに画像を送れる入力経路がある
* [x] スマホからTelegram Botに動画を送れる入力経路がある
* [x] 複数画像を扱えるDB/storage設計がある
* [x] Pythonがファイルを保存できる
* [x] DBに投稿ジョブが残る
* [x] 画像/動画を検証できる
* [x] 画像/動画を投稿用に変換できる
* [x] AIがcaption / hashtags / alt_textを生成できる
* [x] approval modeでTelegramに投稿プレビューが返る
* [x] 承認後にXへ投稿できる
* [x] auto modeで検証OK後に自動投稿できる
* [x] dry_run modeで投稿せずに確認できる
* [x] 投稿完了通知がTelegramに返る
* [x] 投稿失敗時に理由がDBとTelegramに残る
* [x] GitHubにメディアを保存していない
* [x] n8nを投稿パイプラインで使っていない
