# チュートリアル：要求・応答モデル

## 目的と準備

一度に1件の要求を受け付けるシステムを記述し、
「要求を受け付けたら、いつか応答する」という性質をTLCで検証します。
公平性を仮定したときの成立と、その仮定を外したときの反例を確認します。

[利用ガイドのインストール](usage.md#インストール)に従い、PythonパッケージとJava・TLCを用意してください。
以下のPythonコードを順に`request_response.py`へ記述します。
実行用オプションを備えたコード全体は、
[リポジトリのサンプル](https://github.com/eldesh/tlacraftpy/blob/master/examples/request_response.py)にもあります。

## 状態と遷移

状態は「待機中」「要求あり」「応答あり」の3つです。
要求の受け付けで「待機中」から「要求あり」へ、応答で「応答あり」へ進み、
次の要求に備えて「待機中」へ戻ります。

`Enum`で状態の値域を定義し、`@state`を付けたクラスのフィールドに指定します。
`@initial`で初期状態、`@action`で現在状態`s`と次状態`t`の関係を定義します。

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
def init(s: State) -> bool:
    return s.phase == Phase.Idle


@action
def request(s: State, t: State) -> bool:
    return s.phase == Phase.Idle and t.phase == Phase.Requested


@action
def respond(s: State, t: State) -> bool:
    return s.phase == Phase.Requested and t.phase == Phase.Responded


@action
def reset(s: State, t: State) -> bool:
    return s.phase == Phase.Responded and t.phase == Phase.Idle
```

`init`は待機中の状態を初期状態として選びます。
`request`、`respond`、`reset`は、それぞれの条件を満たす状態間の遷移を表します。
たとえば`respond`は、現在の`phase`が`Requested`で、次の`phase`が`Responded`となる遷移です。

## 進捗の性質

`@temporal`で、実行全体について検証する性質を定義します。
`leads_to(P, Q)`は、`P`が成立するたびに、その位置以降のどこかで`Q`が成立することを表します。

```python
@temporal
def every_request_gets_response(s: State) -> bool:
    return leads_to(s.phase == Phase.Requested, s.phase == Phase.Responded)
```

この性質は、要求を受け付けた状態に進むたびに、その後いつか応答した状態に進むことを求めます。

## 遷移系と公平性

初期状態と遷移を`Specification`にまとめます。
`any_action`で、次のステップとして選べるアクションを列挙します。

```python
system = Specification(
    state=State,
    init=init,
    next=any_action(request, respond, reset),
    fairness=[weak_fairness(respond)],
)
```

仕様には、全フィールドを保持するステップ（stuttering）も含まれます。
要求後に同じ状態にとどまり続ける実行を除くため、応答に弱公平性を仮定します。
`weak_fairness(respond)`は、ある時点以降ずっと状態を変える応答ステップが実行可能なら、
そのステップが無限回実行されるという条件です。

## 検証と成立の確認

`check`の最初の引数には、検証する仕様`system`を渡します。
`properties`には、検証したい性質を`[every_request_gets_response]`のようなリストで指定します。
`module="RequestResponse"`で生成するTLA+のモジュール名を指定し、`timeout=30`で検証時間を30秒に制限します。

```python
result = check(
    system,
    properties=[every_request_gets_response],
    module="RequestResponse",
    timeout=30,
)
assert result.status is Status.Passed
```

保存したファイルを、Java・TLCを設定したプロジェクト内で実行します。

```bash
python request_response.py
```

検証が完了すると`TLC: passed`と生成ファイルの保存先を表示します。
このモデルでは、弱公平性を満たすすべての実行について、要求がいつか応答されることを確認できます。
TLA+、TLC設定、名前の対応表、ログは`.tlacraftpy/request_response/`に保存されます。

## 公平性を外した場合の反例

同じ状態と遷移を使い、公平性を空にした仕様も検証します。
次のコードを同じファイルの末尾に追加してください。

```python
unfair_system = Specification(
    state=State,
    init=init,
    next=any_action(request, respond, reset),
)

unfair_result = check(
    unfair_system,
    properties=[every_request_gets_response],
    module="RequestResponse",
    output_dir=".tlacraftpy/request_response/unfair",
    timeout=30,
)
assert unfair_result.status is Status.Violated
```

`output_dir`で、最初の検証とは別の保存先を指定しています。

もう一度実行すると、2回目の検証では`TLC: violated`と反例が表示されます。
反例は、要求を受け付けた後、`Phase.Requested`のままstutteringし続ける実行です。
`-> repeat from state ... (stuttering)`が、同じ状態を繰り返す箇所を示します。
これにより、遷移として応答を許すことと、いつか応答することを求める公平性の役割を確認できます。

## 次のモデル

列や量化を使う例は[FIFOモデル](fifo.md)を参照してください。
構文と各演算子の意味は[言語リファレンス](language.md)、検証の設定・結果・生成ファイルは
[利用ガイド](usage.md)にまとめています。
