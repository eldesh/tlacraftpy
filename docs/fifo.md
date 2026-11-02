# FIFOモデル

## 移植元

Lamportの『Specifying Systems』に付属する
[InnerFIFO.tla](https://github.com/tlaplus/Examples/blob/0e32a039a4286cc3e1b0f70c00eaff3178d49f85/specifications/SpecifyingSystems/FIFO/InnerFIFO.tla)と
[Channel.tla](https://github.com/tlaplus/Examples/blob/0e32a039a4286cc3e1b0f70c00eaff3178d49f85/specifications/SpecifyingSystems/FIFO/Channel.tla)
をPythonで記述した例です。
入力チャネルで受け取ったメッセージをキューに追加し、先頭から出力チャネルへ送ります。

Python版は[examples/fifo.py](https://github.com/eldesh/tlacraftpy/blob/master/examples/fifo.py)にあります。
メッセージは`Message.A`と`Message.B`の2種類、キューの容量は2です。
入力・出力チャネルは、送信側と受信側が2値のフラグを交互に切り替えるハンドシェイクで同期します。

## 状態と遷移の対応

元のチャネルレコードの各フィールドを、Python版では個別の状態変数として定義します。

| 元のTLA+ | Python版 |
| --- | --- |
| `in.val`、`in.rdy`、`in.ack` | `in_value`、`in_ready`、`in_ack` |
| `out.val`、`out.rdy`、`out.ack` | `out_value`、`out_ready`、`out_ack` |
| `q` | `q` |
| フラグの`0`、`1` | `Bit.Zero`、`Bit.One` |
| `SSend(msg)` | `ssend`内の`exists(Message, lambda msg: ...)` |
| `BufRcv` | `buf_rcv` |
| `BufSend` | `buf_send` |
| `RRcv` | `rrcv` |

2値のフラグでは、次状態の値を現在と異なる値にする条件が、元の`1 - flag`に対応します。
初期状態は両チャネルのreadyとackが一致し、キューが空の状態です。
メッセージ値とフラグの初期値には、それぞれのEnumの値域から選択を許します。

## 列の値域と操作

列の状態変数には、`Annotated`で要素のEnumと最大長を指定します。

```python
from typing import Annotated

from tlacraftpy import MaxLen, state


@state
class State:
    q: Annotated[tuple[Message, ...], MaxLen(2)]
```

この値域には空の列、長さ1の列、長さ2の列が含まれます。
Pythonのタプル記法で列を表し、TLA+の列操作へ変換します。

| Pythonの記述 | TLA+での意味 |
| --- | --- |
| `()` | 空列`<<>>` |
| `(msg,)` | 1要素の列`<<msg>>` |
| `s.q + (msg,)` | 列の連結`q \o <<msg>>` |
| `append(s.q, msg)` | `Append(q, msg)` |
| `len(s.q)` | `Len(q)` |
| `head(s.q)` | `Head(q)` |
| `tail(s.q)` | `Tail(q)` |

`head`と`tail`は、`len(s.q) > 0`などの条件に続けて使います。
FIFOの取り出しでは、先頭を出力値にし、残りを次状態のキューにします。

```python
return len(s.q) > 0 and t.out_value == head(s.q) and t.q == tail(s.q)
```

## 量化

`exists`と`forall`は、状態の値域に宣言したEnumを対象に量化します。
第2引数のlambdaに、対象の値を表す引数を一つ指定します。

```python
exists(Message, lambda msg: t.in_value == msg)
forall(Message, lambda msg: exists(Message, lambda other: other == msg))
```

`exists`は条件を満たす値の存在を、`forall`はすべての値についての成立を表します。
`ssend`では、入力チャネルへ送るメッセージを存在量化で選びます。

## 不変条件と進捗

`@invariant`で、到達可能なすべての状態で成立する条件を定義します。

```python
from tlacraftpy import invariant


@invariant
def bounded(s):
    return len(s.q) <= CAPACITY
```

検査する不変条件は`check`または`export`の`invariants`に指定します。
違反時は、初期状態から違反状態までの有限の状態列を返します。
列の値は`(Message.A, Message.B)`のようなPythonのタプル記法で表示します。

Python版のFIFOは、元の状態遷移に弱公平性の仮定を加えて、入力・出力のハンドシェイクが
いつかacknowledgeされることも検証します。
`buf_rcv`、`buf_send`、`rrcv`に弱公平性を仮定します。

## 実行

プロジェクトのルートで実行します。

```bash
python examples/fifo.py --tlc-jar /path/to/tla2tools.jar
```

公平性の仮定を外すと、要求を放置して同じ状態を繰り返す反例を確認できます。

```bash
python examples/fifo.py --without-fairness --tlc-jar /path/to/tla2tools.jar
```

変換結果は次のコマンドで確認できます。

```bash
python examples/fifo.py --export-only
```

生成ファイルとTLCのログは`.tlacraftpy/fifo/`に保存します。

## 元の仕様との比較

比較テストでは、元のTLA+仕様とPython版の両方に、メッセージ2種類・キュー容量2という条件を指定します。
元の`BufRcv`に容量のガードを加えた有限モデルを使います。
両者をTLCで探索し、フラグとフィールド名を対応づけた上で、初期状態・到達可能な状態・遷移の集合を比較します。

一致するグラフは初期状態16、到達可能な状態344、遷移648です。
この比較は、指定した有限モデルでの状態遷移の対応を確認します。
キューの残りを捨てる誤った取り出し操作についても、比較テストで遷移の差を検出します。

元のファイルと比較用ラッパーは[tests/fixtures/fifo](https://github.com/eldesh/tlacraftpy/tree/master/tests/fixtures/fifo)にあります。
元のTLA+ファイルのMITライセンス表示も同梱しています。
