# WORKFLOW.md - 開発ワークフロー

> **対象**: 実装エージェント (Claude Code / Cursor / Gemini 等)、リポジトリオーナー
> **位置づけ**: 運用ドキュメント。設計書ではない。
> **前提**: GitHub + GitHub Copilot (PR レビュー bot) 利用。GitHub Actions を CI で使う想定。

このドキュメントは個人開発・小規模チーム向けの「AI エージェントがほぼ自走で PR を回し、リポジトリオーナーはマージ判断だけ行う」ワークフローを定義する。

---

## 1. 基本フロー

```
[Code] 実装
  ↓
[Code] PR 作成 (または main 直接 commit)
  ↓
[Copilot bot] レビュー (PR の場合)
  ↓
[Code] レビュー対応 (修正 → commit → push → サマリコメント投稿)
  ↓
[Code] マージ自動確認 polling 開始 (背景タスク)
  ↓
[Owner] マージ判断 (GitHub UI / スマホ等から)
  ↓
[Code] polling が MERGED を検出 → 次 Phase へ自動着手
```

**Owner の役割**: マージ判断のみ。コードは書かない。マージ完了の口頭報告も不要 (Code が自動検出する)。

---

## 2. PR vs main 直接 commit の判断基準

### PR が必要な作業 (= 重め)

- 多段 Phase 構成の Phase 完了
- 複数ファイル / 複数ロジックに渡るコード変更
- 設計判断や仕様変更を伴う
- 本番動作に影響する変更
- Owner が明示的に PR を求めた作業

### main 直接 commit で OK (= 軽量)

- ドキュメント 1 つの追加・更新
- 軽微なタイポ / 表記揺れ修正
- 設計書のクロージング作業 (サマリー作成等)
- Code 側から「軽い」と判断できる作業

**迷ったら Owner に確認**。全てを PR にすると重たくなる。

---

## 3. PR ワークフロー詳細

### 3.1 PR 作成

```bash
git checkout -b <type>/<scope>-<detail>   # 例: feature/login-form, fix/oauth-redirect
# 実装 → 段階的 commit
git push -u origin <branch>
gh pr create --base main --head <branch> --title "..." --body "..."
```

**コミットメッセージ形式**:
- 通常実装: `feat(scope): 内容` / `fix(scope): 内容` / `refactor(scope): 内容` / `test(scope): 内容` / `docs(scope): 内容` / `chore(scope): 内容`
- レビュー対応: `fix(review): Copilot レビュー対応 (PR #N)`

### 3.2 Copilot レビュー対応 (PR 作成と同ターンで実行)

`gh pr create` 完了後、**Owner へ応答を返さず同じターン内で連続実行**:

1. **30〜60 秒間隔で Copilot レビュー polling**
   ```bash
   gh api repos/{owner}/{repo}/pulls/{N}/reviews    # overview
   gh api repos/{owner}/{repo}/pulls/{N}/comments   # inline 指摘
   ```
   `user.login` が `copilot-pull-request-reviewer` または `Copilot` のもの。
2. **最大 10 分待機**。timeout したら PR コメントで「未着、次回確認時に対応」と残して終了
3. レビューが届いたら **inline で対応** (専用 Skill / hook を起動しない):
   - 各指摘を分類: 軽微 (typo / lint / 小さなロジック) / 設計判断 (大きな変更要求)
   - 軽微: `edit → commit → push`
   - 設計判断: **修正せず保留**、サマリで「Owner 確認待ち」と明示
4. **`suppressed (low confidence)` 指摘も内容を見て対応する** (実態としてしばしば正当な指摘)
5. ローカル検証 (型チェック + テスト) を commit 前に実行
6. **サマリコメント 1 件投稿** (フォーマットは §3.3 参照)

#### Stop hook / UserPromptSubmit / Skill 起動を経由しない

過去の実験で hook / Skill 経由は timing 不安定だった。エージェントが Owner 入力を待たずに自分で polling して処理する運用が安定する。

### 3.3 サマリコメントの統一フォーマット

```markdown
## Copilot レビュー N 件 → 対応完了 (commit <短縮sha>)

| # | 指摘 | 対応 |
|---|---|---|
| (1) | <Copilot 指摘の要約 1 行> | <修正内容 or 判断理由 1-2 行> |
| (2) | ... | ... |

## ローカル検証
- 型チェック: クリーン
- 単体テスト: XX/XX PASS
```

### 3.4 マージ自動確認 polling (★ 自走の核)

サマリコメント投稿後、**Owner のマージを待たず**に自動 polling を仕掛ける:

```bash
PR_NUMBER=<N>
while true; do
  state=$(gh pr view $PR_NUMBER --json state --jq .state 2>/dev/null || echo "")
  if [ "$state" = "MERGED" ]; then
    echo "MERGED at $(date)"; exit 0
  elif [ "$state" = "CLOSED" ]; then
    echo "CLOSED_WITHOUT_MERGE at $(date)"; exit 0
  fi
  sleep 60
done
```

**実行方法**: 背景タスクとして起動し、10 分程度のタイムアウトで運用。タイムアウトしたら同じ polling を再起動して延長。

#### 通知結果に応じた分岐

| 通知 | 意味 | Code の対応 |
|------|------|------------|
| `MERGED` | Owner が承認マージ | 次 PR / 次 Phase に自動着手 |
| `CLOSED` (without merge) | Owner が問題を見つけて閉じた | **停止して Owner に報告** |
| `TIMEOUT` (10 min 未マージ) | Owner がまだマージしていない | **同じ polling を再起動**して延長 |

#### TIMEOUT 延長戦略

- 最大回数の制限なし (Owner が外出から戻るまで)
- 1 分間隔の `gh API` 呼び出しのみで負荷は極小
- Code は notification 待ちで他作業可能

### 3.5 マージ後の次 Phase 着手

```bash
git checkout main
git pull --ff-only origin main
git checkout -b <next-branch>   # 次 Phase
# 実装着手
```

多段 Phase 全 PR が完了するまで自走可能。

---

## 4. なぜこの形か (Why)

### 4.1 Owner が外出中でも進行する

スマホ等から `gh pr merge` または GitHub UI でマージするだけで Code が検出して次 PR へ進む。ローカル環境前にいる必要がない。

### 4.2 「マージ完了」の手動報告不要

Owner が Code に対して「マージ完了」と打ち込まなくても、polling で自動検出する。Owner の認知負荷を最小化。

### 4.3 マージ判断の主体は Owner

Code は「マージされたか」を**検出するだけ**。マージ可否の判断 (内容を読む / Copilot レビューを確認 / 他作業との優先度) は GitHub 上で Owner が行う。

### 4.4 軽量作業まで PR にしない

ドキュメント 1 つの追加で PR を作るのは過剰。main 直接 commit で十分。判断は Code 側で行う (迷ったら確認)。

---

## 5. 禁止事項

- **`git push --force` / `git reset --hard origin/...` で履歴を上書きする** (Owner が明示指示した場合のみ)
- **`--no-verify` で pre-commit hook をスキップする**
- **Copilot 指摘の設計判断系を独断で修正する** (必ず保留してサマリで明示)
- **Owner 承認なしに PR をマージする**
- **Stop hook / UserPromptSubmit hook に polling を委ねる** (timing 不安定、§3.2 参照)
- **`.env` ファイル / API キーをコミット**

---

## 6. 軽量作業 (main 直接 commit) の手順

```bash
git checkout main && git pull --ff-only origin main
# 編集
git add <files>
git commit -m "<type>(<scope>): <内容>"
git push origin main
```

PR と違って Copilot レビューは走らない。push 後の CI fail には注意。

---

## 7. 自動 lint 修正ワークフロー (Copilot Coding Agent、任意)

実装 PR が main にマージされたタイミングで、変更ファイルの周辺 (1 階層親ディレクトリ等) の ESLint / 型違反を **Copilot Coding Agent** に自動修正させる仕組み。Owner 負担ゼロで継続的に lint 違反を減らせる。

> **テンプレに含めていないもの**: 本機能の実体である `.github/workflows/lint-fix-on-merge.yml` 等の GitHub Actions YAML はテンプレに含めていない (リポジトリの言語・lint ツール構成に強く依存するため)。本節は「こういう運用が可能」という指針のみを示す。

### 7.1 目的

実装 PR ごとに少しずつ lint 修正 PR が自動生成され、Owner はマージ判断だけで継続的に lint 違反が減る。

### 7.2 フロー

```
[実装 PR が main にマージ]
  ↓ GH Actions trigger
  ↓ (excludes copilot/* and chore/lint-fix-*)
[Action が PR diff から TS/JS ファイルを抽出 → 1 階層親ディレクトリ算出]
  ↓
[Action が Issue 自動作成]
  - title: "[lint-fix] PR #N の影響範囲を lint 修正"
  - body: 対象ディレクトリ + 厳守事項 + 検証手順
  - assignee: Copilot ← Coding Agent
  ↓
[Copilot Coding Agent が PR 作成]
  - branch: copilot/lint-fix-N (デフォルト命名)
  ↓
[Copilot レビュー + Owner マージ判断]
```

### 7.3 修正範囲・深さ

| 項目 | 採用 |
|------|------|
| 修正範囲 | マージ PR が触れたファイルの **1 階層親ディレクトリのみ** (作りながら段階拡張) |
| 修正の深さ | lint auto-fixable + 型注釈追加 (any 残置 / 戻り値型欠落) + 未使用 import 削除 |
| 対象外 | `unknown` の具体型化 (人間判断が必要)、設計判断を伴うリファクタ |

### 7.4 Copilot への厳守事項 (Issue body にテンプレ化)

- **既存機能・ロジック・テスト結果を一切変更しない**
- **デザイン・UI の見た目を一切変更しない**
- **フォーマット規約・命名規約も変更しない**
- **修正前後でテストが同じ結果になること**
- **直せなかったもの** (unknown 残置、副作用が読めなかったもの) は **PR description にレポート**

### 7.5 無限ループ予防 (3 重)

| 予防 | 条件 |
|------|------|
| (1) close-only を除外 | `pull_request.merged == true` のみトリガー |
| (2) Copilot 自身の PR を除外 | `head.ref` が `copilot/` で始まらないこと |
| (3) 手動 lint-fix PR を除外 | `head.ref` が `chore/lint-fix-` で始まらないこと |

→ Copilot Coding Agent が出す lint 修正 PR (`copilot/lint-fix-N`) がマージされても、もう一度 lint エージェントは起動しない。

### 7.6 起動条件

- マージされた PR に **対象ファイル変更が 1 件以上ある** こと
- 0 件なら Issue を作らずに workflow 終了 (無駄起動の予防)

---

## 8. Production Deployment 失敗の早期検出フロー (任意)

CD パイプライン (Production Deployment 等) がある場合、deploy 失敗を merge から数 PR 分見逃す事故を避けるため、**pre-merge 強化 + post-merge 瞬間チェック** の 2 段構えで早期検出する。

### 8.1 目的

- 各 PR の merge 後に走る Production Deployment の失敗を、**次 Phase 着手前に検出**する
- ただし、毎 PR で deploy success まで待つと数分〜十数分 / PR の追加待機が発生するため、待ち時間を最小化する

### 8.2 pre-merge ゲート (`docker build` を CI Pipeline 内で実行)

`.github/workflows/ci.yml` の `docker-build` ジョブで `docker build .` を実行する (Docker ベースのデプロイの場合)。

- ローカル `npm ci` / `tsc` / `jest` は通るが Docker 内の `npm ci` で落ちるような **ローカル / Docker context の食い違い** を pre-merge で捕捉する
- 例: `.npmrc` の `legacy-peer-deps=true` がローカルでは効くが Docker COPY 漏れで効かないケース
- ジョブ追加による CI 時間増加は GitHub Actions cache (`type=gha`) で最小化

### 8.3 post-merge 瞬間チェック (次 Phase 着手時)

各 Phase の作業着手の **冒頭**で、最新 Production Deployment の状態を 2 秒で確認する。

```bash
gh run list --workflow=deploy.yml --limit=1 --json conclusion,number,headSha,status,createdAt
```

判定:

| 最新 deploy の状態 | 着手判断 |
|------------------|----------|
| `success` | ✅ 次 Phase 着手 OK |
| `in_progress` | ✅ 次 Phase 着手 OK (後で見直す。並走で別 Phase を進める間に結果が出るのが普通) |
| `failure` で headSha が直近 1〜2 commit 以内 | ❌ **次 Phase 着手せず Owner に即時報告**。原因調査 PR を先行 |
| `failure` だが headSha が古い (= 既に修正済み or 失敗が放置されていない) | 状況を Owner に確認 |

これにより、deploy 失敗の検出遅延は **最大で 1 Phase ぶん (= 次 PR まで)** に抑えられる。

### 8.4 §3.4 (merge polling) との関係

§3.4 の merge polling は引き続き「MERGED 検出 → 次 Phase へ自動着手」のままで変更しない。本 §8.3 の瞬間チェックは「次 Phase 着手の冒頭ステップ」として追加される。

合算した流れ:

```
[Code] サマリコメント投稿 → merge polling 起動
  ↓
[Owner] merge
  ↓
[Code] polling MERGED 検出
  ↓
[Code] git checkout main && git pull --ff-only origin main
  ↓
[Code] ★ 最新 deploy 状態を瞬間チェック (本 §8.3)
  ↓ success / in_progress
[Code] git checkout -b <next-phase-branch>
  ↓
[Code] 次 Phase 実装着手
```

### 8.5 採用しなかった案 (記録)

| 案 | 採否 | 理由 |
|---|------|------|
| 毎 PR で deploy success まで完全待機 | ❌ | 各 PR で数分〜十数分追加、ビルド時間延長で累積 |
| Step 完了 PR (最終 PR) のみ deploy success まで待つ | ❌ | 途中 Phase で壊れた場合 Step 末尾まで検出が遅れる |
| 全 PR で CI Pipeline のみ待つ | ❌ | Production Deploy 自体の失敗は検出できない |
| post-merge polling を background で常時走らせる | ❌ | 失敗時の判断 (継続 / 停止) が曖昧、通知混入で混乱しやすい |
| **採用**: pre-merge `docker build` + 次 Phase 着手時瞬間チェック | ✅ | 待ち時間ゼロ近く、検出遅延 1 Phase 以内 |

---

## 9. 関連ドキュメント / リソース

| リソース | 内容 |
|---------|------|
| `/AGENTS.md` | 全エージェント共通ルール (正本) |
| `.github/workflows/` | CI / lint-fix / deploy 等の workflow YAML (本テンプレには含めていない、プロジェクトごとに作成) |

---

> **テンプレについて**: 本ドキュメントは個人開発 + GitHub + Copilot ベースの実プロジェクト運用から汎用化したもの。具体 PR 番号 / 過去事案 / プロジェクト固有の数値 (lint 違反 N 件等) は意図的に除いている。実プロジェクトで使う場合は、本ドキュメントを参考に「履歴」セクションを追加して固有事案を積んでいく形が想定運用。
