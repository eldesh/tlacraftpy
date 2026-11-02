# 開発手順

## セットアップ

Python 3.11以降とGNU Makeを用意し、リポジトリのルートでパッケージと開発用ツールをインストールします。

```bash
python -m pip install -e '.[dev]'
```

ツールの依存関係と設定は`pyproject.toml`、実行コマンドは`Makefile`で管理します。
Makefileは`python`を使います。別のPythonを使う場合は`PYTHON`を指定します。

```bash
make type-check PYTHON=.venv/bin/python
```

## コードの検査

フォーマット、docstring、型、テストをまとめて検査します。
`make`の既定ターゲットも`check`です。

```bash
make check
```

個別に実行する場合は、次のターゲットを指定します。

| ターゲット | 内容 |
| --- | --- |
| `format` | Ruffによる整形 |
| `format-check` | 整形状態の確認 |
| `docstring-check` | 公開APIと型のGoogle形式docstringの検査 |
| `type-check` | ライブラリ本体とサンプルのmypyによる型検査 |
| `test` | unittestによるテストの実行 |

## TLC統合テスト

`make test`は単体テストを実行します。
TLC統合テストも実行する場合は、Javaと
[TLC 1.7.4のJAR](https://github.com/tlaplus/tlaplus/releases/download/v1.7.4/tla2tools.jar)を用意し、
`TLACRAFTPY_TLC_JAR`にJARのパスを指定します。`make check`でも同じ環境変数を使います。

```bash
TLACRAFTPY_TLC_JAR=/path/to/tla2tools.jar make test
```

TLCの統合テストでは、要求・応答とFIFOの安全性・進捗・反例を検査し、
FIFOの元のTLA+仕様とPython版の状態遷移を比較します。
TLCがエラーを返した場合は、テストの出力にTLCのログを表示します。

## ドキュメントの構成

サイトの原稿は`docs/`、ナビゲーションと表示の設定は`mkdocs.yml`に置きます。
文書を追加・更新するときは、その内容の目的に合わせて配置を見直します。

| 文書 | 内容 |
| --- | --- |
| `index.md` | プロジェクトの概要と各文書への入口 |
| `tutorial.md` | 一つのモデルを記述し、成立と反例を確認する手順 |
| `usage.md` | 設定、検証・変換、結果、生成ファイルの扱い |
| `language.md` | 記述できる構文と演算子の意味 |
| `fifo.md` | FIFOの仕様と元のTLA+仕様との対応 |
| `development.md` | 開発時の検査、ドキュメントの生成・公開 |
| `distribution.md` | Pythonパッケージのビルド・検査・公開 |

サイト内の文書はMarkdownファイルへの相対リンクで参照します。
ソースコードなどリポジトリ上のファイルには、GitHubのURLでリンクします。

## ドキュメントの生成とプレビュー

リポジトリのルートで、MkDocsをインストールします。サイトはMkDocs標準テーマを使います。

```bash
python -m pip install -e '.[docs]'
make docs-serve
```

表示されたローカルURLをブラウザで開くと、編集に合わせてサイトを確認できます。
公開用のHTMLは次のコマンドで`site/`に生成します。

```bash
make docs
```

ビルドでは、ナビゲーション、文書間のリンク、見出しへのリンクを検査します。
警告もエラーとして扱います。
生成元のMarkdownは、GitHub上でも閲覧できます。

## GitHub Pagesへの公開

公開先は`https://eldesh.github.io/tlacraftpy/`です。
リポジトリのSettings → Pages → Build and deploymentで、SourceにGitHub Actionsを指定します。

[Documentationワークフロー](https://github.com/eldesh/tlacraftpy/blob/master/.github/workflows/docs.yml)は、
`docs/`、`mkdocs.yml`、`Makefile`、`pyproject.toml`、公開ワークフローの変更を対象に動作します。
pull requestではサイトのビルドとリンク検査を実行します。
Pagesを有効にしたリポジトリでは、`master`へのpushで生成したサイトを`github-pages`環境へデプロイします。

手動で公開する場合は、Actions → Documentation → Run workflowで`master`を選んで実行します。
ビルドの成功と公開先のURLは、ワークフローの実行結果から確認できます。

## GitHub Actions

CIもMakefileのターゲットを使用します。
[Testsワークフロー](https://github.com/eldesh/tlacraftpy/blob/master/.github/workflows/tests.yml)で
コードの検査と配布物の検査、TLC統合テストを実行し、
[Documentationワークフロー](https://github.com/eldesh/tlacraftpy/blob/master/.github/workflows/docs.yml)で
サイトを生成します。実行環境とサンプルの検証内容は各ワークフローに定義しています。

サンプルが生成したTLA+、TLC設定、名前の対応表、TLCログは、
Testsワークフローの`examples-python-<バージョン>`アーティファクトから取得できます。

パッケージ形式とビルド・公開の手順は「[パッケージの配布](distribution.md)」にあります。
