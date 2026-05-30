# Sns Auto Publisher

## プロジェクト概要

Telegram Botに送信された画像・動画をPythonアプリで受信し、ローカル保存、検証、変換、AI投稿文生成、Telegramプレビュー、承認または自動投稿、X投稿、完了通知までを扱うSNS投稿オーケストレーターです。

GitHubはソースコード管理とCI用途に限定し、画像・動画などのメディア実体は保存しません。n8nやGitHub Actionsを投稿パイプラインの中核にはしません。

## MVPの目的

スマホからTelegram Botへ画像・動画を送るだけで、Pythonアプリが投稿ジョブをDBで管理しながら、検証、変換、AI生成、プレビュー、承認、X投稿、完了通知まで進められる状態をMVPとします。

## MVP対象

- Telegram Botからの画像受信
- Telegram Botからの動画受信
- 複数画像対応
- ローカルストレージ保存
- SQLiteによる状態管理
- 画像・動画の検証と投稿用変換
- AIによるcaption / hashtags / alt_text生成
- Telegram投稿プレビュー
- approval / auto / dry_run mode
- X投稿
- 投稿完了・失敗通知

## MVP対象外

- 任意フォルダ監視
- Google Drive監視
- メールボックス監視
- 他メッセンジャー連携
- 複数SNS投稿
- 投稿予約
- 管理画面
- クラウドストレージ移行

## セットアップ手順

Python 3.11以上を用意し、依存関係をインストールします。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

動画処理には `ffmpeg` と `ffprobe` が必要です。macOSではHomebrewで導入できます。

```bash
brew install ffmpeg
```

## `.env` の作り方

`.env.example` をコピーして `.env` を作成します。

```bash
cp .env.example .env
```

初期状態では `POSTING_MODE=approval` です。TelegramからAI生成まで通す場合は `TELEGRAM_BOT_TOKEN` と `OPENAI_API_KEY` を設定してください。X投稿まで通す場合は `X_API_KEY` / `X_API_SECRET` / `X_ACCESS_TOKEN` / `X_ACCESS_TOKEN_SECRET` も設定してください。

## 起動方法

`TELEGRAM_BOT_TOKEN` が未設定の場合は、基盤の起動確認としてstorageディレクトリ作成とSQLiteテーブル作成だけを行って終了します。
Tokenを設定している場合は、Telegram Botのpollingを開始します。

```bash
python -m app.main
```

## テスト方法

```bash
pytest
```

## 現在の実装範囲

PR 8相当まで、以下を実装しています。

- Pythonプロジェクト基盤
- `.env` 読み込みを前提にした設定管理
- SQLite接続とDB初期化
- `post_jobs` / `media_assets` / `post_attempts` / `app_settings` モデル
- `post_job` と `media_asset` を作成できるrepository層
- `storage/raw` / `storage/processed` / `storage/thumbnails` を扱うローカルストレージ基盤
- Telegram Bot入力アダプター
- 許可済みchat_idチェック
- Telegramから受け取った画像・動画のraw保存
- 受信時の `post_jobs` / `media_assets` 登録
- Telegramへの受信通知
- メディアの入口検証
- 画像ファイルの破損検知
- 画像のEXIF除去
- 画像リサイズ
- サムネイル生成
- `ffprobe` による動画メタデータ取得
- 動画のMIME、拡張子、サイズ、秒数検証
- `.mp4` / `.mov` 入力対応
- `ffmpeg` によるH.264/AACのmp4正規化
- `+faststart` 付きmp4出力
- 動画サムネイル生成
- ffmpeg / ffprobe未導入時や変換失敗時のfailed記録
- 全media_assetsの状態に基づくpost_job status更新
- OpenAI Responses APIを使うAI投稿文生成アダプター
- AI出力JSONのSchema検証
- caption / hashtags / alt_text / warningsのDB保存
- `should_post=false` 時のrejected記録
- AI生成失敗時のfailed記録
- Telegram投稿プレビュー送信
- 投稿する / 再生成 / 却下のInline Keyboard callback処理
- 投稿する押下時の `publishing` への状態更新
- 再生成押下時のAI生成やり直しとプレビュー再送
- 却下押下時の `rejected` への状態更新
- `/mode` コマンドによる投稿モード確認
- `/mode approval` / `/mode auto` / `/mode dry_run` による投稿モード変更
- `app_settings` への投稿モード永続化
- approval / auto / dry_run の処理分岐
- X投稿publisher層
- 画像1枚・複数画像・動画の投稿処理
- 投稿成功時の `x_post_id` 保存
- 投稿成功/失敗の `post_attempts` 記録
- 投稿失敗時の `failed` 状態更新
- 検証・処理結果のDB状態更新
- 最小限のpytest

## 動画処理仕様

対応入力形式は `.mp4` と `.mov` です。MIME typeは `video/mp4` と `video/quicktime` を許可します。

動画はrawファイルを上書きせず、以下へ出力します。

```text
storage/processed/<job_id>/<original_stem>.mp4
storage/thumbnails/<job_id>/<original_stem>.jpg
```

変換仕様は、video codecがH.264、audio codecがAAC、mp4のfaststart有効です。秒数上限は `MAX_VIDEO_DURATION_SECONDS`、サイズ上限は `MAX_VIDEO_SIZE_MB` で設定します。

## AI投稿文生成仕様

処理済みメディア情報をもとに、OpenAI Responses APIで以下のJSONを生成します。

```json
{
  "caption": "投稿本文",
  "hashtags": ["#example"],
  "alt_text": "画像や動画の説明",
  "warnings": [],
  "should_post": true
}
```

生成結果はDBの `post_jobs.caption` / `hashtags_json` / `alt_text` / `ai_warnings_json` に保存します。JSON形式が不正な場合やAPI呼び出しに失敗した場合は `failed`、`should_post=false` の場合は `rejected` として理由をDBに残します。

## Telegramプレビュー仕様

`approval` modeでは、AI生成後にTelegramへ投稿プレビューを送信します。プレビューにはcaption、hashtags、alt_text、warningsを含め、以下のボタンを付けます。

- 投稿する
- 再生成
- 却下

`投稿する` は `post_jobs.status` を `publishing` に更新し、X投稿へ進みます。投稿成功時は `published`、失敗時は `failed` に更新します。`再生成` はAI生成をやり直して新しいプレビューを送信します。`却下` は `rejected` に更新します。

## 投稿モード管理

Telegramで `/mode` を送ると現在の投稿モードを確認できます。以下のコマンドでモードを変更できます。

```text
/mode approval
/mode auto
/mode dry_run
```

`approval` はプレビューと承認ボタンを返します。`auto` はAI生成後、warningsがなくcaptionがある場合にX投稿へ進みます。`dry_run` はXへ投稿せず、投稿予定内容だけをTelegramへ返します。

## X投稿仕様

X投稿はTweepyを使い、投稿用メディアをアップロードして取得したmedia_idをPost作成時に添付します。画像は `tweet_image`、動画は `tweet_video` として扱います。動画はchunked uploadを使います。

投稿成功時は `post_jobs.x_post_id` にX側の投稿IDを保存し、`post_jobs.status` を `published` にします。投稿失敗時は `post_attempts` に失敗理由を残し、`post_jobs.status` を `failed` にします。

## 次PR候補

次はPR 9として、通知 + リトライ + 重複防止を実装します。

- 投稿完了通知をTelegramへ返す
- 投稿失敗通知をTelegramへ返す
- file_hashで重複検知する
- 投稿済みjobの二重投稿を防ぐ
- `/retry <job_id>` と `/status <job_id>` を追加する
