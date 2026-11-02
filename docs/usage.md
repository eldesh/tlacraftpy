# 利用ガイド

仕様の変換・検証に必要な設定、関数の呼び出し方、結果と生成ファイルの扱いを説明します。
仕様を作る手順は[チュートリアル](tutorial.md)、構文と意味は[言語リファレンス](language.md)を参照してください。
以下のコード断片では、定義済みの仕様を`system`、時相的な性質を`responds`、不変条件を`bounded`とします。

## インストール

Python 3.11以降を使います。手元のwheelからインストールする場合は、ファイルのパスを指定します。

```bash
python -m pip install ./tlacraftpy-0.1.0-py3-none-any.whl
```

リポジトリのソースからインストールする場合は、ルートディレクトリで実行します。

```bash
python -m pip install .
```

PyPI公開後は、配布名を指定してインストールできます。

```bash
python -m pip install tlacraftpy
```

モデル検査にはJavaと[TLCのtla2tools.jar](https://github.com/tlaplus/tlaplus/releases/download/v1.7.4/tla2tools.jar)を用意します。
CIではJava 21とTLC 1.7.4を使用しています。

## JavaとTLCの設定

仕様のソースファイルから親ディレクトリを探索して最初に見つかった`pyproject.toml`の、
`[tool.tlacraftpy]`に設定します。見つからない場合は、ソースファイルのディレクトリを基準にします。

```toml
[tool.tlacraftpy]
tlc_jar = "/path/to/tla2tools.jar"
java = "/path/to/java"
```

| 設定 | 選択順 | 相対パスの基準 |
| --- | --- | --- |
| Java | `PATH`上の`java`、次に設定の`java` | 設定ファイルのあるディレクトリ |
| TLC JAR | 呼び出し時の`tlc_jar=`、次に設定の`tlc_jar` | 引数はカレントディレクトリ、設定は設定ファイルのあるディレクトリ |

Javaを`PATH`から取得できる場合、設定ファイルには`tlc_jar`だけを記述できます。

## モデル検査

`check`は、仕様をTLA+に変換し、生成ファイルを書き出してTLCを実行します。
状態の不変条件は`invariants`、時相的な性質は`properties`に指定します。

```python
from tlacraftpy import check

result = check(
    system,
    invariants=[bounded],
    properties=[responds],
    timeout=30,
)
```

| 引数 | 内容 | 既定値 |
| --- | --- | --- |
| `spec` | 検証する`Specification`。最初の位置引数 | 必須 |
| `invariants` | `@invariant`定義のイテラブル | 空 |
| `properties` | `@temporal`定義のイテラブル | 空 |
| `tlc_jar` | TLC JARのパス | プロジェクト設定 |
| `output_dir` | 生成ファイルとログの保存先 | プロジェクト内の`.tlacraftpy/<ソース名>/` |
| `module` | TLA+のモジュール名と生成ファイルの名前 | `"Model"` |
| `timeout` | TLCを待つ時間の上限。正の秒数または`None` | `None`（完了まで待つ） |
| `verbose` | 結果と保存先を標準出力に表示するか | `True` |

`spec`以外はキーワード引数で指定します。
`module`には、ASCII英字で始まり、ASCII英数字とアンダースコアからなる名前を指定します。

## 変換とファイル出力

TLA+とTLC設定のテキストをPython側で取得する場合は、`compile_spec`を使います。

```python
from tlacraftpy import compile_spec

compiled = compile_spec(system, properties=[responds], module="Response")
print(compiled.tla)
print(compiled.cfg)
```

`Compiled`には、`module`、`tla`、`cfg`、名前の対応表`mapping`、初期条件のソースファイルのパス`source`が含まれます。

ファイルへ書き出す場合は`export`を使います。

```python
from tlacraftpy import export

artifacts = export(
    system,
    properties=[responds],
    module="Response",
    output_dir="generated/response",
)
print(artifacts.tla)
print(artifacts.cfg)
```

`compile_spec`と`export`も、`invariants`と`properties`で検証対象を指定します。
`export`は`output_dir`を受け取り、書き出したファイルのパスを`Artifacts`として返します。

## 検証結果と反例

`check`は`CheckResult`を返します。`status`で検証の結果を判断できます。

| 結果 | 意味 |
| --- | --- |
| `Status.Passed` | 検証が完了し、指定した性質が成立 |
| `Status.Violated` | 性質に違反する反例を検出 |
| `Status.Incomplete` | 時間制限や中断により検証が未完了 |

```python
from tlacraftpy import Status

if result.status is Status.Violated:
    print(result.property_name)
    print(result.counterexample)
elif result.status is Status.Incomplete:
    print(result.reason)
```

`property_name`は違反した不変条件のPython名、または検証対象が一つの場合の時相的な性質のPython名です。
`None`は性質名が未特定であることを表します。
`reason`には、時間制限や中断の理由を格納します。
`verbose=False`を指定すると、呼び出し元で表示方法を決められます。

`counterexample`には、初期状態からの状態列`states`を格納します。
各状態の`number`は1から始まる番号、`values`はPythonのフィールド名から表示用の値への辞書、
`label`は遷移や初期条件のラベルです。
列の値は`(Message.A, Message.B)`のようなタプル記法で表示します。

不変条件の反例は違反状態までの有限列です。
時相的な性質の反例には、繰り返しの戻り先を示す`loop_start`があります。
`stuttering=True`は、末尾の状態を保持する繰り返しを表します。
`print(result.counterexample)`で状態列と戻り先をまとめて表示できます。

## 生成ファイルとログ

`result.artifacts`または`export`の戻り値から生成ファイルを参照できます。

| 属性 | ファイル・内容 |
| --- | --- |
| `directory` | 保存先ディレクトリの絶対パス |
| `tla` | `<module>.tla`：変換したTLA+仕様 |
| `cfg` | `<module>.cfg`：TLC設定 |
| `mapping` | `mapping.json`：TLA+の識別子とPythonの名前の対応 |
| `log` | `tlc.log`：`check`が書き込むTLCの標準出力・標準エラー |
| `compiled` | 生成に使用した`Compiled` |

既定の保存先は、初期条件のソースから探索したプロジェクトディレクトリの
`.tlacraftpy/<ソース名>/`です。`request_response.py`の場合は`.tlacraftpy/request_response/`になります。
`output_dir`の相対パスは、カレントディレクトリを基準に解釈します。

同じ出力先では、生成ファイルとTLCログを上書きします。
複数のモデルを並列に検証する場合や結果を残す場合は、別々の`output_dir`を指定してください。

## 警告と例外

| 種類 | 発生時点・内容 |
| --- | --- |
| `UnconstrainedWarning` | 変換時に、次状態のフィールドの指定が暗黙になっている場合 |
| `SpecificationError` | 宣言・構成・変換時に、仕様の型や構文が不正な場合 |
| `ConfigurationError` | 実行準備時に、設定ファイルやJava・TLCのパスが不正な場合 |
| `TLCError` | TLCの起動・実行や、結果・反例の読み取りでエラーが発生した場合 |
| `ValueError` | `check`の`timeout`に0以下を指定した場合 |
| `OSError` | 生成ディレクトリ・ファイル・ログの作成や書き込みに失敗した場合 |

暗黙の次状態の扱いを明示する方法は、[言語リファレンスの次状態の指定と保持](language.md#次状態の指定と保持)を参照してください。
時間制限と性質の違反は、それぞれ`Status.Incomplete`と`Status.Violated`として返します。
`TLCError`の診断では、表示された`tlc.log`の内容を確認できます。

## サンプルの実行オプション

リポジトリの`examples/request_response.py`と`examples/fifo.py`は、次のオプションを持つ実行用スクリプトです。

| オプション | 用途 |
| --- | --- |
| `--tlc-jar PATH` | TLC JARのパスを指定 |
| `--export-only` | TLA+とTLC設定を書き出して、保存先を表示 |
| `--without-fairness` | 公平性の仮定を外して検証 |

```bash
python examples/request_response.py --tlc-jar /path/to/tla2tools.jar
python examples/request_response.py --export-only
python examples/fifo.py --without-fairness --tlc-jar /path/to/tla2tools.jar
```

サンプルは、成立・反例あり・検証未完了に対して、それぞれ終了コード`0`・`1`・`2`を返します。
コード全体は[要求・応答](https://github.com/eldesh/tlacraftpy/blob/master/examples/request_response.py)と
[FIFO](https://github.com/eldesh/tlacraftpy/blob/master/examples/fifo.py)を参照してください。
