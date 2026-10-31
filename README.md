# pytla prototype

Pythonの関数を仕様として読み取り、TLA+へ変換してTLCで検証する最小実装です。
Python 3.11以降を使います。実行時のPython依存パッケージはありません。
JavaとTLCは利用者が用意します。ライブラリによるダウンロードやインストールは行いません。

## まず変換する

このディレクトリで実行します。変換だけならJavaもTLCも不要です。

```bash
PYTHONPATH=src python examples/request_response.py --export-only
```

出力先は`.pytla/request_response/`です。

| ファイル | 内容 |
| --- | --- |
| `RequestResponse.tla` | 変換した仕様 |
| `RequestResponse.cfg` | TLCの設定 |
| `mapping.json` | TLA+の識別子とPythonの名前の対応 |
| `tlc.log` | TLC実行時の標準出力・標準エラー |

通常のPythonパッケージとしてインストールする場合は`python -m pip install -e .`を使えます。
インストール後は`PYTHONPATH=src`の指定を省略できます。

## TLCで検証する

利用者が用意した`tla2tools.jar`のパスを、このプロジェクトの`pyproject.toml`に設定します。
相対パスは`pyproject.toml`のあるディレクトリを基準に解釈します。

```toml
[tool.pytla]
tlc_jar = "/path/to/tla2tools.jar"
java = "/path/to/java"
```

Javaは`PATH`上の`java`を優先します。見つからない場合に、上記の`java`を使います。
TLCのJARは`check(..., tlc_jar=...)`でも指定でき、設定ファイルより優先されます。
引数で渡す相対パスは、実行時のカレントディレクトリが基準です。

```bash
PYTHONPATH=src python examples/request_response.py
```

設定せずにJARのパスを渡すこともできます。

```bash
PYTHONPATH=src python examples/request_response.py --tlc-jar /path/to/tla2tools.jar
```

基準例は「要求が来たら、いつか応答する」を検証します。
応答アクションの弱公平性を仮定した場合は成立し、仮定を外すと要求後にstutteringし続ける反例が期待されます。

```bash
PYTHONPATH=src python examples/request_response.py --without-fairness
```

例のスクリプトの終了コードは、成立が`0`、反例ありが`1`、検証未完了が`2`です。
ライブラリの`check`自体はプロセスを終了させず、結果を返します。

## 仕様の記述

完全な基準例は[examples/request_response.py](examples/request_response.py)にあります。

```python
class Phase(Enum):
    Idle = auto()
    Requested = auto()
    Responded = auto()

@state
class State:
    phase: Phase

@action
def respond(s, t):
    return s.phase == Phase.Requested and t.phase == Phase.Responded

@temporal
def every_request_gets_response(s):
    return leads_to(s.phase == Phase.Requested, s.phase == Phase.Responded)
```

`@initial`と`@temporal`は現在状態の引数を一つ、`@action`は現在と次状態の引数を二つ取ります。
引数の名前は自由です。仕様関数の本体は実行せず、ファイルから取得したASTを解析します。
REPL、Notebook、`exec`で生成した関数は対象外です。

対応する本体は単一の`return`文です。式では`==`、`!=`、`and`、`or`、`not`、
論理値、状態フィールド、宣言したEnumのメンバーを使えます。
異なるEnum間の比較、任意の関数呼び出し、代入、ループなどは変換エラーにします。
`leads_to(P, Q)`の引数は状態述語に限定し、時相演算子の入れ子は未対応です。
複数の`leads_to`式を`and`、`or`、`not`で組み合わせることはできます。

## 値域・保持・未制約

各状態変数の値域は、型注釈に指定したEnumのメンバーです。
初期状態に`TypeOK`、各アクションに`TypeOK'`を加えるので、次状態を未制約にしても値域外には出ません。
EnumのPython側の数値・文字列の値は使わず、メンバーをTLCのモデル値へ変換します。

```python
@action
def respond(s, t):
    return (
        s.phase == Phase.Requested
        and t.phase == Phase.Responded
        and unchanged(s.other)
    )
```

`unchanged(s.other)`は`other' = other`を表します。
`unconstrained(s.other)`は論理式として`TRUE`を出力し、指定漏れの警告を抑制します。
どちらもアクション内で、現在状態のフィールドを一つ指定します。

未指定の次状態フィールドには`UnconstrainedWarning`を出します。
これは構文に基づく補助診断で、式が変数を実質的に制約することの証明ではありません。
`or`では各分岐の指定を調べますが、論理的な同値変形や恒真式までは解析しません。

## TLA+への対応

仕様は次の式に変換します。

```tla
Spec == Init /\ [][Next]_vars /\ WF_vars(Respond)
```

`[][Next]_vars`で全変数を保持するステップを許し、`weak_fairness(respond)`を`WF_vars`へ変換します。
公平性の対象は`next`に登録したアクションに限ります。
`leads_to(P, Q)`は`P ~> Q`に変換します。

初期版ではデッドロック検査を無効にしています。
到達可能なすべての状態と、指定した時相的性質をTLCで検査します。
整数、集合、量化、強公平性、独立した不変条件API、リファインメントは未実装です。

## 結果を使う

```python
result = check(
    system,
    properties=[every_request_gets_response],
    timeout=30,
)

if result.status is Status.Violated:
    print(result.counterexample)
```

`Status.Passed`、`Status.Violated`、`Status.Incomplete`を区別します。
`timeout`の単位は秒で、省略時は時間制限を設けません。
TLCの完了メッセージと正常終了の両方を確認した場合だけ`Passed`を返します。
認識できない出力やTLCのエラーは`TLCError`にし、成立とは扱いません。
変換失敗は`SpecificationError`、Java/TLCの設定不備は`ConfigurationError`です。

反例では状態変数と値をPythonの名前へ戻し、循環の戻り先やstutteringを表示します。
複数の時相的性質を同時に検査した場合、TLCが違反した性質を特定しないことがあります。
その場合は`result.property_name`を`None`とし、名前を推測しません。

生成先は`output_dir=`、TLA+のモジュール名は`module=`で変更できます。
既定の保存先は、仕様のソースから親へ探索して最初に見つかった`pyproject.toml`のある
ディレクトリの`.pytla/<ソース名>/`です。見つからなければソースのあるディレクトリを基準にします。
同じ出力先を再利用すると生成ファイルとログは上書きされます。
並列に検証する場合は別々の`output_dir`を指定してください。

## テストと現在の検証範囲

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

単体テストではASTの拒否・型の検査・値域・フレーム条件・警告・設定の優先順位・
TLC起動引数・結果の分類・反例解析・タイムアウトを確認します。
TLC出力のテストデータはプロトコルに基づく人工データです。

TLC本体を用意したら、実際のTLCで公平性の有無を比較する統合テストを実行できます。

```bash
PYTLA_TLC_JAR=/path/to/tla2tools.jar PYTHONPATH=src \
    python -m unittest discover -s tests -v
```

この作業環境にはJavaはありますがTLCのJARがないため、実際のTLCによる統合テストは未実行です。
TLCのバージョンごとの出力差への対応も、実環境での確認が残っています。
