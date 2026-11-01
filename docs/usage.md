# 利用ガイド

## 概要

tlacraftpyは、PythonでTLA+のサブセットに相当する仕様を記述し、TLCで検証するライブラリです。
状態・遷移・時相的な性質を定義し、検証結果と反例をPython側の名前で確認できます。

以下では、一度に1件の要求を受け付けるシステムについて、「要求が来たら、いつか応答する」という性質を記述します。
サンプルのコード全体は[examples/request_response.py](../examples/request_response.py)にあります。
このファイルを`request_response.py`として保存すると、以下のコマンドで実行できます。

## セットアップ

Python 3.11以降と、Java、TLCの`tla2tools.jar`を用意します。
公開版のインストールは[READMEのセットアップ](../README.md#セットアップ)を参照してください。
リポジトリのソースからインストールする場合は、ルートディレクトリで次のコマンドを実行します。

```bash
python -m pip install .
```

TLCのJARとJavaのパスは、プロジェクトの`pyproject.toml`に設定します。
相対パスは`pyproject.toml`のあるディレクトリを基準に解釈します。

```toml
[tool.tlacraftpy]
tlc_jar = "/path/to/tla2tools.jar"
java = "/path/to/java"
```

Javaは`PATH`上の`java`を優先し、見つからない場合に設定ファイルの`java`を使います。

## 要求・応答モデルの仕様

モデルの状態は「待機中」「要求あり」「応答あり」の3つです。
要求の受け付けで「要求あり」、応答で「応答あり」へ進み、次の要求に備えて「待機中」へ戻ります。
仕様は`.py`ファイルに記述します。

### 状態と遷移

`Enum`で状態変数の値域を定義し、`@state`の型注釈で指定します。
各メンバーを仕様上の値として区別し、次状態の値もこのEnumの中から選びます。

```python
from enum import Enum, auto

from tlacraftpy import (
    Specification,
    Status,
    action,
    any_action,
    check,
    initial,
    leads_to,
    state,
    temporal,
    unconstrained,
    unchanged,
    weak_fairness,
)


class Phase(Enum):
    Idle = auto()
    Requested = auto()
    Responded = auto()


@state
class State:
    phase: Phase


@initial
def init(s):
    return s.phase == Phase.Idle


@action
def request(s, t):
    return s.phase == Phase.Idle and t.phase == Phase.Requested


@action
def respond(s, t):
    return s.phase == Phase.Requested and t.phase == Phase.Responded


@action
def reset(s, t):
    return s.phase == Phase.Responded and t.phase == Phase.Idle
```

`@initial`は初期状態、`@action`は状態間の遷移を定義します。
この例では現在状態を`s`、次状態を`t`としています。引数の名前は自由です。

関数の本体は単一の`return`文で記述します。式では`==`、`!=`、`and`、`or`、`not`、
論理値、状態フィールド、宣言したEnumのメンバーを使えます。
比較には同じEnumの値を使います。

### 状態の保持と値の選択

`unchanged(s.phase)`で、次状態でも`phase`の値を保持します。
たとえば、状態を保持するアクションは次のように書けます。

```python
@action
def wait(s, t):
    return unchanged(s.phase)
```

`unconstrained(s.phase)`で、次状態の値をEnumの値域全体から選べることを明示します。
どちらもアクション内で、現在状態のフィールドを一つ指定します。

未指定の次状態フィールドには`UnconstrainedWarning`を出します。
`unchanged`または`unconstrained`で扱いを明示すると、この警告を抑制できます。
警告は式に書かれた次状態フィールドの指定を確認し、`or`では各分岐を調べます。

### 進捗の性質と公平性

`@temporal`で、実行全体について検証する性質を定義します。
`leads_to(P, Q)`は、`P`が成立するたびに、その位置以降のどこかで`Q`が成立することを表します。
引数には状態についての条件式を二つ指定し、複数の`leads_to`式を`and`、`or`、`not`で組み合わせることもできます。

```python
@temporal
def every_request_gets_response(s):
    return leads_to(
        s.phase == Phase.Requested,
        s.phase == Phase.Responded,
    )
```

仕様では、全変数を保持するステップ（stuttering）を許します。
応答の進捗を保証するため、`weak_fairness(respond)`で応答アクションの弱公平性を仮定します。
これは、応答がある時点以降ずっと実行可能であり続けるなら、応答が無限回実行されるという条件です。

初期状態、遷移、公平性を`Specification`にまとめます。
公平性の対象には、`next`に登録したアクションを指定します。

```python
system = Specification(
    state=State,
    init=init,
    next=any_action(request, respond, reset),
    fairness=[weak_fairness(respond)],
)
```

## TLCによるモデル検査

`check`に仕様と検証する性質を渡します。TLA+とTLC設定ファイルを生成し、TLCを実行します。
`timeout`には検証時間の上限を秒単位で指定します。この例では最大30秒間実行します。

```python
result = check(
    system,
    properties=[every_request_gets_response],
    timeout=30,
)
```

サンプルの仕様は、次のコマンドで検証できます。

```bash
python request_response.py
```

TLCのJARは、コマンドの`--tlc-jar`または`check(..., tlc_jar=...)`でも指定できます。
引数での指定は設定ファイルより優先され、相対パスは実行時のカレントディレクトリを基準に解釈します。

```bash
python request_response.py --tlc-jar /path/to/tla2tools.jar
```

公平性の仮定を外したモデルも検証できます。
この場合は、要求後にstutteringし続ける実行が、進捗の性質に違反する反例になります。

```bash
python request_response.py --without-fairness
```

## 検証結果と反例

`check`は検証結果を返し、呼び出し元で結果に応じた処理を記述できます。

| 結果 | 意味 | サンプルの終了コード |
| --- | --- | --- |
| `Status.Passed` | 検証が完了し、指定した性質が成立 | `0` |
| `Status.Violated` | 性質に違反する反例を検出 | `1` |
| `Status.Incomplete` | 時間制限などにより検証が未完了 | `2` |

```python
if result.status is Status.Violated:
    print(result.counterexample)
```

反例では状態変数と値をPythonの名前で表示し、循環の戻り先やstutteringを示します。
`result.property_name`には、特定できた違反の性質名を格納します。`None`は性質名が未特定であることを表します。

仕様の変換に関するエラーは`SpecificationError`、JavaやTLCの設定に関するエラーは`ConfigurationError`、
TLCの実行や結果の読み取りに関するエラーは`TLCError`として通知します。

## 生成ファイルとログ

サンプルの出力先は`.tlacraftpy/request_response/`です。

| ファイル | 内容 |
| --- | --- |
| `RequestResponse.tla` | 変換した仕様 |
| `RequestResponse.cfg` | TLCの設定 |
| `mapping.json` | TLA+の識別子とPythonの名前の対応 |
| `tlc.log` | TLC実行時の標準出力・標準エラー |

変換のみを実行してTLA+ファイルとTLC設定ファイルを確認する場合は、`--export-only`を指定します。

```bash
python request_response.py --export-only
```

生成先は`output_dir=`、TLA+のモジュール名は`module=`で変更できます。
既定の保存先は、仕様のソースから親へ探索して最初に見つかった`pyproject.toml`のある
ディレクトリの`.tlacraftpy/<ソース名>/`です。見つからなければソースのあるディレクトリを基準にします。
同じ出力先を再利用すると生成ファイルとログは上書きされます。
並列に検証する場合は別々の`output_dir`を指定してください。

フォーマット・テスト・CIの実行手順は[CONTRIBUTING.md](../CONTRIBUTING.md)にあります。
