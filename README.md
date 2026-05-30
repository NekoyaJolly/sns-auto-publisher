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

## `.env` の作り方

`.env.example` をコピーして `.env` を作成します。

```bash
cp .env.example .env
```

初期状態では `POSTING_MODE=approval` です。APIキーやBotトークンは後続PRで実API連携を入れるまでは未設定のままで構いません。

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

PR 3相当まで、以下を実装しています。

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
- 検証・処理結果のDB状態更新
- 最小限のpytest

## 次PR候補

次はPR 4として、動画処理を実装します。

- iPhone動画のmp4化
- Android動画のmp4化
- 動画秒数とサイズの検証
- 動画サムネイル生成
- FFmpeg失敗時のfailed記録
