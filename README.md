# tlacraftpy

## 概要

tlacraftpyは、PythonでTLA+のサブセットに相当する仕様を記述し、TLCで検証するライブラリです。
状態・遷移・時相的な性質を定義し、検証結果と反例をPython側の名前で確認できます。

## セットアップ

Python 3.11以降を使います。PyPI公開後は、次のコマンドでインストールできます。

```bash
python -m pip install tlacraftpy
```

手元のwheelからインストールする場合は、ファイルのパスを指定します。

```bash
python -m pip install ./tlacraftpy-0.1.0-py3-none-any.whl
```

Pythonでは、配布名と同じ`tlacraftpy`からAPIを読み込みます。

```python
from tlacraftpy import Specification, check
```

モデル検査にはJavaとTLCの`tla2tools.jar`を用意し、プロジェクトの`pyproject.toml`にパスを設定します。

```toml
[tool.tlacraftpy]
tlc_jar = "/path/to/tla2tools.jar"
java = "/path/to/java"
```

Javaは`PATH`上の`java`を優先し、見つからない場合に設定ファイルの`java`を使います。

## 要求・応答モデルの検証

[要求・応答のサンプル](https://github.com/eldesh/tlacraftpy/blob/master/examples/request_response.py)を
`request_response.py`として保存し、実行します。
「要求が来たら、いつか応答する」という性質と、応答アクションの公平性を記述したサンプルです。

```bash
python request_response.py
```

`check`は成立・反例あり・検証未完了を結果として返します。
生成したTLA+、TLC設定、名前の対応表、実行ログは`.tlacraftpy/request_response/`に保存します。

## ドキュメント

- [利用ガイド：仕様の記述、モデル検査、結果と反例](https://github.com/eldesh/tlacraftpy/blob/master/docs/usage.md)
- [開発手順：フォーマット、テスト、CI](https://github.com/eldesh/tlacraftpy/blob/master/CONTRIBUTING.md)
- [配布：パッケージ形式、ビルド、公開手順](https://github.com/eldesh/tlacraftpy/blob/master/docs/distribution.md)
