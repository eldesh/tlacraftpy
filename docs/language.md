# 言語リファレンス

- [仕様の記述形式](#仕様の記述形式)
- [状態の型と値域](#状態の型と値域)
- [定義の種類と状態参照](#定義の種類と状態参照)
- [値と式](#値と式)
- [次状態の指定と保持](#次状態の指定と保持)
- [量化](#量化)
- [不変条件と時相的な性質](#不変条件と時相的な性質)
- [遷移系と公平性](#遷移系と公平性)
- [変換時の診断](#変換時の診断)

## 仕様の記述形式

tlacraftpyの仕様は、状態の値域、初期状態、状態間の遷移、検証する性質をPythonで記述します。
デコレータを付けた関数のソースを読み取り、その式をTLA+へ変換します。
仕様内の`and`や`==`などは、TLA+の論理演算や等式として解釈します。

仕様を定義する関数は、ソースを取得できる`.py`ファイルに置きます。
関数本体は、一つの`return`文と、その前に任意で置くdocstringから構成します。
`return`の値には論理式を指定します。引数名は自由で、型注釈も付けられます。

```python
@action
def receive(current: State, following: State) -> bool:
    """キューの先頭を取り出す。"""
    return (
        len(current.q) > 0
        and following.last == head(current.q)
        and following.q == tail(current.q)
    )
```

状態型や`Specification`の組み立てには通常のPythonを使います。
`head`、`exists`、`unchanged`などのDSL演算子は、仕様関数の式内に記述します。
変換・検証の呼び出し方は[利用ガイド](usage.md)を参照してください。

## 状態の型と値域

`@state`を付けたクラスの型注釈で、1個以上の状態フィールドと値域を宣言します。
値域には、メンバーを持つ`Enum`、またはそのEnumを要素とする最大長付きの列を指定します。
初期状態と各遷移の次状態は、宣言した値域に制限されます。

```python
from enum import Enum, auto
from typing import Annotated

from tlacraftpy import MaxLen, state


class Message(Enum):
    A = auto()
    B = auto()


CAPACITY = 2


@state
class State:
    q: Annotated[tuple[Message, ...], MaxLen(CAPACITY)]
    last: Message
```

以降の式の例では、この`Message`、`State`、`CAPACITY`を使います。
`s`は現在状態、`t`は次状態を表します。

| 型注釈 | 値域 |
| --- | --- |
| `Message` | `Message.A`、`Message.B` |
| `Annotated[tuple[Message, ...], MaxLen(2)]` | `Message`の値からなる長さ0〜2の列 |
| `Annotated[tuple[Message, ...], MaxLen(0)]` | 空列のみ |

`MaxLen`には0以上の整数を指定します。
各EnumのメンバーはTLA+のモデル値に変換します。
たとえば`IntEnum`を用いても、異なるEnumの値は別の値域として扱います。
同じEnumで同じ値を持つ別名のメンバーは、同じモデル値を表します。

## 定義の種類と状態参照

| デコレータ | 引数 | 戻り値の式 | 用途 |
| --- | --- | --- | --- |
| `@initial` | 現在状態の1引数 | 初期状態を選ぶ論理式 | `Specification.init` |
| `@action` | 現在状態、次状態の2引数 | 両状態の関係を表す論理式 | `Specification.next` |
| `@invariant` | 現在状態の1引数 | 各状態で成立すべき論理式 | `invariants=[...]` |
| `@temporal` | 現在状態の1引数 | `leads_to`を含む時相論理式 | `properties=[...]` |

引数はデフォルト値のない位置引数として定義します。
`s.q`や`t.last`のように、状態引数から宣言済みのフィールドを参照します。
TLA+では現在状態の参照は変数`q`、次状態の参照はプライム付き変数`q'`に対応します。

`@initial`は論理式を満たすすべての状態を初期状態にします。
あるフィールドについて条件を指定しない場合、そのフィールドには宣言した値域のどの値も許します。
`@action`も、式を満たすすべての現在状態と次状態の組を表します。

`@invariant`には状態についての条件を書きます。
`@temporal`では、その条件から`leads_to`で実行全体についての性質を記述します。

## 値と式

式の値には、論理値、整数、Enumのメンバー、Enumを要素とする列があります。
整数は、列の長さや長さの上限などの条件を記述するために使います。

| 記述 | 意味・型 | 例 |
| --- | --- | --- |
| `True`、`False` | 論理値 | `True` |
| 整数リテラル | 整数 | `0`、`2` |
| グローバル変数またはクロージャ内の整数定数 | 整数 | `CAPACITY` |
| `Enum名.メンバー名` | そのEnumの値 | `Message.A` |
| `状態引数.フィールド名` | 宣言したフィールドの値 | `s.last`、`t.q` |
| 量化のlambda引数 | 量化対象のEnumの値 | `msg` |
| `()` | 空列 | `t.q == ()` |
| `(要素,)`、`(要素1, 要素2)` | 同じEnumの値からなる列 | `(Message.A, Message.B)` |

整数定数の値は変換時に読み取ります。負の整数は、`LOWER = -1`のように
通常のPythonで定義した定数を式から参照できます。
Enum名や整数定数、DSL演算子名も、関数のグローバル変数やクロージャから解決します。

### 論理演算と比較

| Pythonの記述 | TLA+での意味 | オペランド |
| --- | --- | --- |
| `P and Q` | 論理積`P /\ Q` | 論理式 |
| `P or Q` | 論理和`P \/ Q` | 論理式 |
| `not P` | 否定`~P` | 論理式 |
| `x == y` | 等式`x = y` | 同じ値域の値 |
| `x != y` | 不等式`x # y` | 同じ値域の値 |
| `x < y`、`x <= y`、`x > y`、`x >= y` | 大小比較 | 整数 |

列の比較では、要素が同じEnumに属する列同士を比較します。
空列は、各Enumの列と比較できます。
時相論理式は`and`、`or`、`not`で組み合わせます。

演算子の優先順位と括弧はPythonに従います。
たとえば`not s.last == Message.A or len(s.q) > 0`は、
`(not (s.last == Message.A)) or (len(s.q) > 0)`として解釈します。
連鎖比較`0 <= len(s.q) <= CAPACITY`は、隣り合う値の比較を論理積で結びます。

### 列の演算

| Pythonの記述 | 結果 | TLA+の対応 |
| --- | --- | --- |
| `q1 + q2` | 2つの列の連結 | `q1 \o q2` |
| `append(q, msg)` | 末尾に要素を追加した列 | `Append(q, msg)` |
| `len(q)` | 列の長さ（整数） | `Len(q)` |
| `head(q)` | 列の先頭要素 | `Head(q)` |
| `tail(q)` | 先頭要素を除いた列 | `Tail(q)` |

連結する列と追加する要素には、同じEnumの値を使います。
`head`と`tail`は、非空の列に対して使います。
次のように、長さの条件に続けて取り出しを記述できます。

```python
@action
def take(s: State, t: State) -> bool:
    return len(s.q) > 0 and t.last == head(s.q) and t.q == tail(s.q)
```

`MaxLen`は状態フィールドの値域を定めます。
たとえば最大長2のキューで長さ3の列を次状態に指定すると、その遷移は値域の条件を満たさなくなります。
容量があるときの追加は、`len(s.q) < CAPACITY`の条件で表せます。

## 次状態の指定と保持

`@action`では、次状態への等式や条件で各フィールドの変化を指定します。
`t.last == head(s.q)`は、取り出した要素を次状態の`last`にする条件です。
各条件は、同じ1ステップの現在状態と次状態について同時に成立する関係を表します。

| 記述 | 次状態の意味 |
| --- | --- |
| `t.last == Message.A` | `last`が`Message.A`になる |
| `t.last != s.last` | `last`が現在と異なる値になる |
| `unchanged(s.last)` | `last`が現在と同じ値になる |
| `unconstrained(s.last)` | `last`に宣言した値域内の任意の値を許す |

`unchanged`と`unconstrained`には、現在状態のフィールドを一つ渡します。
保持を明示する`unchanged(s.last)`は、TLA+の`UNCHANGED last`に対応します。

次状態を指定しなかったフィールドも、値域内の任意の値を取れます。
その場合は変換時に`UnconstrainedWarning`を出します。
値を保持するときは`unchanged`、自由な選択を意図するときは`unconstrained`で明示できます。

この警告では、式に含まれる次状態への参照と明示指定を調べます。
`and`では各条件の指定を合わせ、`or`では全分岐に共通する指定を確認します。
たとえば次の式では、両方の分岐で`q`と`last`の扱いが明示されています。

```python
@action
def put_or_wait(s: State, t: State) -> bool:
    return (
        len(s.q) < CAPACITY and t.q == append(s.q, Message.A) and unchanged(s.last)
    ) or (unchanged(s.q) and unchanged(s.last))
```

警告の有無は構文上の指定に基づきます。実際に許される値は、アクション内の条件全体で決まります。

## 量化

`exists`と`forall`は、状態フィールドまたは列の要素型として宣言したEnumを対象に量化します。
Enum名と、引数を一つ持つlambdaを位置引数で渡します。
lambdaの本体は論理式です。

| 記述 | 意味 | TLA+の対応 |
| --- | --- | --- |
| `exists(Message, lambda msg: P)` | `P`を満たす`msg`が存在する | `\E msg \in Message : P` |
| `forall(Message, lambda msg: P)` | すべての`msg`で`P`が成立する | `\A msg \in Message : P` |

`Message`は、表ではそのEnumのモデル値を集めた集合を表します。
たとえば、任意のメッセージを選んでキューに追加するアクションは次のように書けます。

```python
@action
def put(s: State, t: State) -> bool:
    return len(s.q) < CAPACITY and exists(
        Message,
        lambda msg: t.q == append(s.q, msg) and unchanged(s.last),
    )
```

量化は入れ子にできます。lambdaの引数は、その本体内で対象のEnumの値を表します。
引数名には状態引数と異なる名前を使い、量化対象のEnumは外側のPythonスコープの名前で指定します。
量化した式の状態・遷移・時相の区別は、lambda本体の式に従います。

## 不変条件と時相的な性質

`@invariant`は、到達可能なすべての状態で成立すべき条件を定義します。
`invariants`に指定した条件をTLCが各状態で検査します。

```python
@invariant
def bounded(s: State) -> bool:
    return len(s.q) <= CAPACITY
```

`@temporal`は、実行全体について成立すべき性質を定義します。
`leads_to(P, Q)`は、`P`が成立するたびに、その位置以降のどこかで`Q`が成立することを表します。
`P`と`Q`には現在状態についての論理式を指定します。
TLA+の`P ~> Q`に対応し、`P`が成立した位置で`Q`も成立していれば条件を満たします。

```python
@temporal
def each_head_served(s: State) -> bool:
    return forall(
        Message,
        lambda msg: leads_to(len(s.q) > 0 and head(s.q) == msg, s.last == msg),
    )
```

この性質は、あるメッセージがキューの先頭にあるなら、いつか`last`がその値になることを表します。
複数の時相論理式は`and`、`or`、`not`で組み合わせ、Enumについて量化することもできます。

## 遷移系と公平性

`Specification`に、状態型、初期条件、遷移の選択肢、公平性の仮定をまとめます。
`any_action`には1個以上の異なる`@action`定義を渡し、いずれかのアクションが成立する遷移を許します。

```python
@initial
def init(s: State) -> bool:
    return s.q == () and s.last == Message.A


system = Specification(
    state=State,
    init=init,
    next=any_action(put, take),
    fairness=[weak_fairness(take)],
)
```

実行には、状態全体を保持するステップ（stuttering）も含みます。
`weak_fairness(take)`は、ある時点以降ずっと状態を変える`take`のステップが実行可能なら、
そのステップが無限回実行されるという弱公平性の仮定です。
対象には、`next`に登録したものと同じアクション定義を指定します。
`fairness`の既定値は空で、公平性を追加する場合に仮定を列挙します。

全フィールドの組を`vars`、各アクションの論理和を`Next`とすると、仕様は次のTLA+式に対応します。

```tla
Init /\ [][Next]_vars /\ WF_vars(Take)
```

ここで`Take`は説明用のアクション名です。
`[][Next]_vars`が各ステップで`Next`または状態全体の保持を許し、`WF_vars(Take)`が弱公平性を表します。

定義した性質は、次のように検証対象へ指定します。

```python
result = check(
    system,
    invariants=[bounded],
    properties=[each_head_served],
)
```

この文書のコード断片で使うデコレータとDSL演算子、構成・検証の関数は、
すべて`tlacraftpy`からインポートできます。
モデルのコード全体と実行例は、[要求・応答モデル](https://github.com/eldesh/tlacraftpy/blob/master/examples/request_response.py)と
[FIFOモデル](fifo.md)を参照してください。

## 変換時の診断

状態の型注釈は`@state`を適用するとき、仕様の構造は`Specification`を組み立てるときに検査します。
関数の引数、式の構文、値域、演算子の使用箇所は、`compile_spec`、`export`、`check`による変換時に検査します。
不正な定義は`SpecificationError`として通知し、式に関する診断には関数名・ファイル名・行番号を付けます。

DSL演算子を通常のPythonコードとして直接呼び出した場合も`SpecificationError`になります。
TLCによる検証結果、反例、実行時のエラーは[利用ガイドの検証結果と反例](usage.md#検証結果と反例)を参照してください。
