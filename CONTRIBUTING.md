# テストとCI

## テスト

プロジェクトのルートでパッケージをインストールします。

```bash
python -m pip install -e .
```

Javaと[TLC 1.7.4のJAR](https://github.com/tlaplus/tlaplus/releases/download/v1.7.4/tla2tools.jar)を用意し、
`PYTLA_TLC_JAR`にJARのパスを指定して、単体テストと統合テストを実行します。

```bash
PYTLA_TLC_JAR=/path/to/tla2tools.jar python -m unittest discover -s tests -v
```

TLCの統合テストでは、要求・応答モデルについて、公平性を仮定した場合の成立と、
仮定を外した場合の反例を確認します。
複数のEnumを使うモデルでは、値の保持と値域全体からの選択を比較します。
TLCがエラーを返した場合は、テストの出力にTLCのログを表示します。

## GitHub Actions

[Testsワークフロー](.github/workflows/tests.yml)は、pushとpull requestを契機に実行します。
Actions画面のRun workflowからも起動できます。

Python 3.11・3.12・3.13・3.14、Java 21、TLC 1.7.4を使い、パッケージのインストール、
単体テスト、TLC統合テスト、要求・応答サンプルの実行を確認します。
TLCのダウンロード時にはSHA-256を照合します。

サンプルが生成したTLA+、TLC設定、名前の対応表、TLCログは、
各ジョブの`request-response-python-<バージョン>`アーティファクトから取得できます。
