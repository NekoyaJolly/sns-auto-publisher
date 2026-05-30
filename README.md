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

初期状態では `POSTING_MODE=approval` です。まず安全に動作確認する場合は `POSTING_MODE=dry_run` に変更してください。dry_runではXへ投稿せず、投稿予定内容だけをTelegramへ返します。

主な環境変数は以下です。秘密情報は `.env` にだけ保存し、コードやREADMEへ直接書かないでください。
ChatGPTやCodexのプロンプトにも貼らないでください。`.env` はGit管理対象外です。

| 変数 | 用途 |
| --- | --- |
| `APP_ENV` | 実行環境名。ローカルでは `local` |
| `POSTING_MODE` | `approval` / `auto` / `dry_run` |
| `TELEGRAM_BOT_TOKEN` | Telegram BotのToken |
| `TELEGRAM_ALLOWED_CHAT_IDS` | 許可chat_id。複数指定はカンマ区切り |
| `OPENAI_API_KEY` | caption / hashtags / alt_text生成用 |
| `OPENAI_MODEL` | AI生成で使うOpenAIモデル |
| `X_API_KEY` / `X_API_SECRET` | X APIのConsumer Key / Secret |
| `X_ACCESS_TOKEN` / `X_ACCESS_TOKEN_SECRET` | X APIのAccess Token / Secret |
| `X_BEARER_TOKEN` | 将来拡張用のBearer Token |
| `DATABASE_URL` | SQLite接続先。既定は `sqlite:///data/app.sqlite3` |
| `STORAGE_ROOT` | raw / processed / thumbnails の保存root |
| `MAX_IMAGE_SIZE_MB` | 画像サイズ上限 |
| `MAX_VIDEO_SIZE_MB` | 動画サイズ上限 |
| `MAX_VIDEO_DURATION_SECONDS` | 動画秒数上限 |

`.env` の検収向けチェックは以下で実行できます。秘密情報の値は表示せず、設定済み/未設定だけを表示します。

```bash
python -m app.tools.check_env
```

`POSTING_MODE=dry_run` ではX API Key類が未設定でもOKです。`approval` / `auto` では `X_API_KEY` / `X_API_SECRET` / `X_ACCESS_TOKEN` / `X_ACCESS_TOKEN_SECRET` が必須です。

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

## dry_run確認手順

Xへ投稿せずにMVPの主要経路を確認する手順です。

1. `.env` で `POSTING_MODE=dry_run` にします。
2. `TELEGRAM_BOT_TOKEN` と `OPENAI_API_KEY` を設定します。
3. 必要に応じて `TELEGRAM_ALLOWED_CHAT_IDS` に自分のchat_idを設定します。
4. `python -m app.main` でBotを起動します。
5. Telegram Botへ画像または動画を送ります。
6. Telegramに投稿予定内容が返り、DBの `post_jobs.status` が `preview_sent` になることを確認します。

dry_runではX API認証情報が未設定でもX投稿は実行されません。

## Telegram Bot設定手順

1. TelegramでBotFatherを開き、新しいBotを作成します。
2. 発行されたTokenを `.env` の `TELEGRAM_BOT_TOKEN` に設定します。
3. `python -m app.tools.telegram_chat_id --write-env` を実行します。
4. 画面の案内に従って、Telegramで対象Botへ `/start` または `test` を送ります。
5. 検出された `chat_id` が `.env` の `TELEGRAM_ALLOWED_CHAT_IDS` に自動反映されます。
6. `python -m app.main` でpollingを開始します。

許可chat_idを空にすると、MVPではすべてのchat_idを許可します。実運用では必ず許可chat_idを設定してください。

### `TELEGRAM_ALLOWED_CHAT_IDS` の自動取得

Bot Tokenを `.env` に設定した後、以下を実行するとTelegramのJSONを手で読まずに `chat_id` を確認できます。

```bash
python -m app.tools.telegram_chat_id
```

`.env` の `TELEGRAM_ALLOWED_CHAT_IDS` まで更新する場合は `--write-env` を付けます。

```bash
python -m app.tools.telegram_chat_id --write-env
```

必要に応じて待機時間やpolling間隔も変更できます。

```bash
python -m app.tools.telegram_chat_id --write-env --timeout 120 --poll-interval 2
```

通常はWebhook設定を変更しません。Webhookを使っていたBotで `getUpdates` が使えない場合だけ、明示的に以下を実行してください。

```bash
python -m app.tools.telegram_chat_id --clear-webhook
```

`python -m app.main` でBotがすでに起動中の場合、updatesが先に消費されて `chat_id` を検出できないことがあります。その場合はBotを停止し、TelegramでBotに `/start` または `test` を送ってから再実行してください。

Bot起動後にTelegram上で確認したい場合は、以下のコマンドも使えます。

```text
/whoami
```

返答例:

```text
chat_id=123456789
user_id=987654321
```

`/whoami` は許可リストを作るための確認コマンドなので、`TELEGRAM_ALLOWED_CHAT_IDS` が未設定、または自分のchat_idがまだ許可されていない状態でも実行できます。

秘密情報である `TELEGRAM_BOT_TOKEN` やAPI KeyはChatGPT/Codexのプロンプトに貼らず、`.env` にだけ保存してください。`.env` はGit管理対象外です。

## X API設定手順

X投稿を実行する場合は、X Developer Portalで投稿権限のあるアプリを用意し、以下を `.env` に設定します。

```env
X_API_KEY=
X_API_SECRET=
X_ACCESS_TOKEN=
X_ACCESS_TOKEN_SECRET=
X_BEARER_TOKEN=
```

このアプリではTweepyを使い、画像は通常アップロード、動画はchunked uploadで投稿します。`approval` modeではTelegramの「投稿する」ボタン押下後、`auto` modeではAI判定OK後にX投稿を実行します。

## 運用コマンド

Telegramから以下のコマンドを使えます。

```text
/mode
/mode approval
/mode auto
/mode dry_run
/whoami
/status <job_id>
/retry <job_id>
```

`/retry` は `failed` 状態で、captionと処理済みメディアが残っているjobだけを再投稿します。検証前や却下済みのjobは再投稿しません。

## 現在の実装範囲

MVPとCaption Quality Phaseとして、以下を実装しています。

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
- `/whoami` コマンドによるchat_id / user_id確認
- `python -m app.tools.check_env` によるMVP検収向けenv確認
- `python -m app.tools.telegram_chat_id` によるchat_id取得補助
- `python -m app.tools.telegram_chat_id --write-env` による `TELEGRAM_ALLOWED_CHAT_IDS` 自動更新
- `app_settings` への投稿モード永続化
- approval / auto / dry_run の処理分岐
- X投稿publisher層
- 画像1枚・複数画像・動画の投稿処理
- 投稿成功時の `x_post_id` 保存
- 投稿成功/失敗の `post_attempts` 記録
- 投稿失敗時の `failed` 状態更新
- Telegramへの投稿完了通知
- Telegramへの投稿失敗通知
- `file_hash` による重複メディア検知
- 投稿済みまたは投稿待ちjobの二重投稿防止
- `/retry <job_id>` によるfailed jobの再投稿
- `/status <job_id>` によるjob状態確認
- dry_run / Telegram Bot / X API設定手順
- MVP完成条件チェックリスト
- 画像・動画正常系とrejected/failed異常系を含むpytest
- 検証・処理結果のDB状態更新
- MVP向けpytest
- captionジャンル設定 `config/caption_genres.yaml`
- Telegram caption欄からのジャンル番号 / ジャンルキー抽出
- 複数ジャンル指定に対応したcaption生成prompt
- ジャンル別ハッシュタグ候補と上限の適用
- 不明ジャンル時の利用可能ジャンル一覧返信

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

caption生成のプロンプト本文はコードから外部化し、以下のMarkdownで管理します。

```text
app/prompts/caption/system.ja.md
app/prompts/caption/user.ja.md
```

投稿文の観察ルール、文体、禁止事項を調整する場合は、Pythonコードではなく上記Markdownを編集してください。`user.ja.md` では `{posting_mode}` / `{media_summary}` / `{genre_instruction}` をplaceholderとして使えます。

## スロット投稿向けジャンル指定

Telegramで画像や動画を送るとき、caption欄にジャンル番号またはジャンルキーだけを入れると、そのジャンル向けの投稿ルールでcaptionを生成します。ユーザーが毎回 `tone`、`goal`、`memo` などを書く必要はありません。

入力例:

```text
1
```

```text
slot_result
```

```text
genre=slot_result
```

```text
g=2
```

複数ジャンルを合わせたい場合は、スペース、カンマ、スラッシュ区切りで指定できます。

```text
1 2
```

```text
g=2,3
```

```text
genre=slot_result,slot_moment
```

ジャンル未指定の場合は `default_genre` の `slot_daily` を使います。不明なジャンルが指定された場合は投稿処理へ進まず、Telegramへ利用可能ジャンル一覧を返します。

利用可能ジャンル:

```text
1 = slot_daily / 稼働日記
2 = slot_result / 実戦結果
3 = slot_moment / 出目・演出
4 = machine_impression / 機種所感
5 = data_review / データ振り返り
6 = hall_observation / 店舗状況メモ
7 = new_machine_note / 新台・初打ち
8 = play_log / 立ち回り記録
9 = slot_funny / ネタ・雑談
10 = announcement / 告知
```

ジャンル別ルールは `config/caption_genres.yaml` で編集できます。ハッシュタグはジャンルごとの候補としてAIに渡しますが、固定で挿入するものではありません。画像や動画内容に合う場合だけ使い、ジャンルごとの上限を超えないように扱います。

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

## 通知・リトライ・重複防止

投稿成功時はTelegramへ `job_id` と `x_post_id` を通知します。投稿失敗時はDBの `post_jobs.error_message` と `post_attempts.error_message` に理由を残し、Telegramにも失敗理由を通知します。

同一ファイルの二重投稿を避けるため、raw保存時に `file_hash` を計算し、既存のcaption済み・プレビュー待ち・投稿中・投稿済みjobと一致する場合は新しいjobを `rejected` にします。

運用補助コマンドとして以下を追加しています。

```text
/status <job_id>
/retry <job_id>
```

`/status` は投稿モード、job status、media status、最新投稿試行を返します。`/retry` は `failed` 状態かつ処理済みメディアとcaptionが残っているjobを再度X投稿へ進めます。

## MVP完成条件チェックリスト

- [x] スマホからTelegram Botに画像を送れる入力経路がある
- [x] スマホからTelegram Botに動画を送れる入力経路がある
- [x] 複数画像を扱えるDB/storage設計がある
- [x] Pythonがファイルをローカルストレージへ保存できる
- [x] DBに投稿ジョブが残る
- [x] 画像/動画を検証できる
- [x] 画像/動画を投稿用に変換できる
- [x] AIがcaption / hashtags / alt_textを生成できる
- [x] approval modeでTelegramに投稿プレビューが返る
- [x] 承認後にXへ投稿できる
- [x] auto modeで検証OK後に自動投稿できる
- [x] dry_run modeで投稿せずに確認できる
- [x] 投稿完了通知がTelegramに返る
- [x] 投稿失敗時に理由がDBとTelegramに残る
- [x] GitHubにメディアを保存しない `.gitignore` になっている
- [x] n8nを投稿パイプラインで使っていない

## PR10時点の注意点

- 実際のTelegram / OpenAI / X疎通には各サービス側の認証情報と権限が必要です。
- テストでは外部APIを叩かず、モックと一時ファイルで正常系・異常系を確認します。
- メディア実体とSQLite DBは `storage/` と `data/` に置かれ、Git管理対象外です。

## 次PR候補

MVP後の候補です。

- CIでのpytest実行
- DB migration管理
- 投稿予約
- クラウドストレージ移行
- 管理画面
