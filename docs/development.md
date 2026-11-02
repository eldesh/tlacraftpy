# 開発手順

## セットアップ

プロジェクトのルートで、パッケージと開発用ツールをインストールします。

```bash
python -m pip install -e '.[dev]'
```

## フォーマット

Pythonコードの整形にはRuff 0.17.3を使います。
設定は`pyproject.toml`の`[tool.ruff]`にあり、Python 3.11を対象に、行の長さを88文字として整形します。

```bash
ruff format .
```

整形状態の確認には、次のコマンドを使います。

```bash
ruff format --check .
```

## docstring

公開APIと型のdocstringはGoogle形式で記述します。

Google形式のdocstringチェックは、次のコマンドで実行します。

```bash
ruff check --select D src/tlacraftpy
```

## 型チェック

ライブラリ本体とサンプルの型注釈をmypyで検査します。
検査対象とstrictモードの設定は`pyproject.toml`の`[tool.mypy]`にあります。

```bash
mypy
```

## テスト

Javaと[TLC 1.7.4のJAR](https://github.com/tlaplus/tlaplus/releases/download/v1.7.4/tla2tools.jar)を用意し、
`TLACRAFTPY_TLC_JAR`にJARのパスを指定して、単体テストと統合テストを実行します。

```bash
TLACRAFTPY_TLC_JAR=/path/to/tla2tools.jar python -m unittest discover -s tests -v
```

TLCの統合テストでは、要求・応答モデルについて、公平性を仮定した場合の成立と、
仮定を外した場合の反例を確認します。
複数のEnumを使うモデルでは、値の保持と値域全体からの選択を比較します。
FIFOの統合テストでは、列操作・量化・不変条件と進捗を検査し、
元のTLA+仕様とPython版の到達可能な状態・初期状態・遷移を比較します。
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
mkdocs serve
```

表示されたローカルURLをブラウザで開くと、編集に合わせてサイトを確認できます。
公開用のHTMLは次のコマンドで`site/`に生成します。

```bash
mkdocs build --strict
```

ビルドでは、ナビゲーション、文書間のリンク、見出しへのリンクを検査します。
警告もエラーとして扱います。
生成元のMarkdownは、GitHub上でも閲覧できます。

## GitHub Pagesへの公開

公開先は`https://eldesh.github.io/tlacraftpy/`です。
リポジトリのSettings → Pages → Build and deploymentで、SourceにGitHub Actionsを指定します。

[Documentationワークフロー](https://github.com/eldesh/tlacraftpy/blob/master/.github/workflows/docs.yml)は、
`docs/`、`mkdocs.yml`、`pyproject.toml`、公開ワークフローの変更を対象に動作します。
pull requestではサイトのビルドとリンク検査を実行します。
Pagesを有効にしたリポジトリでは、`master`へのpushで生成したサイトを`github-pages`環境へデプロイします。

手動で公開する場合は、Actions → Documentation → Run workflowで`master`を選んで実行します。
ビルドの成功と公開先のURLは、ワークフローの実行結果から確認できます。

## GitHub Actions

[Testsワークフロー](https://github.com/eldesh/tlacraftpy/blob/master/.github/workflows/tests.yml)は、pushとpull requestを契機に実行します。
Actions画面のRun workflowからも起動できます。

Python formatting and typesジョブで、Ruffによるフォーマット・docstringのチェックと、
mypyによる型チェックを実行します。

Python 3.11・3.12・3.13・3.14、Java 21、TLC 1.7.4を使い、配布物のビルド・検査とwheelのインストール、
単体テスト、TLC統合テスト、要求・応答とFIFOのサンプルの実行を確認します。
TLCのダウンロード時にはSHA-256を照合します。

サンプルが生成したTLA+、TLC設定、名前の対応表、TLCログは、
各ジョブの`examples-python-<バージョン>`アーティファクトから取得できます。

パッケージ形式とビルド・公開の手順は[配布ドキュメント](distribution.md)にあります。
