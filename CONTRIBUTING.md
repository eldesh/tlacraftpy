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

## テスト

Javaと[TLC 1.7.4のJAR](https://github.com/tlaplus/tlaplus/releases/download/v1.7.4/tla2tools.jar)を用意し、
`TLACRAFTPY_TLC_JAR`にJARのパスを指定して、単体テストと統合テストを実行します。

```bash
TLACRAFTPY_TLC_JAR=/path/to/tla2tools.jar python -m unittest discover -s tests -v
```

TLCの統合テストでは、要求・応答モデルについて、公平性を仮定した場合の成立と、
仮定を外した場合の反例を確認します。
複数のEnumを使うモデルでは、値の保持と値域全体からの選択を比較します。
TLCがエラーを返した場合は、テストの出力にTLCのログを表示します。

## GitHub Actions

[Testsワークフロー](.github/workflows/tests.yml)は、pushとpull requestを契機に実行します。
Actions画面のRun workflowからも起動できます。

Python formattingジョブで、Ruffによるフォーマットチェックを実行します。

Python 3.11・3.12・3.13・3.14、Java 21、TLC 1.7.4を使い、配布物のビルド・検査とwheelのインストール、
単体テスト、TLC統合テスト、要求・応答サンプルの実行を確認します。
TLCのダウンロード時にはSHA-256を照合します。

サンプルが生成したTLA+、TLC設定、名前の対応表、TLCログは、
各ジョブの`request-response-python-<バージョン>`アーティファクトから取得できます。

パッケージ形式とビルド・公開の手順は[配布ドキュメント](docs/distribution.md)にあります。
