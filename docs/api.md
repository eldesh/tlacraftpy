# APIドキュメント

## 公開API

`tlacraftpy.__all__`に列挙した関数・型と、戻り値として使う`Definition`・`WeakFairness`の
docstringをAPIの説明として管理します。各APIの説明は、エディタの補完やPythonの`help`で確認できます。

```python
import tlacraftpy

help(tlacraftpy.check)
help(tlacraftpy.Specification)
help(tlacraftpy.CheckResult)
```

## 記述形式

Google形式を使い、先頭にそのAPIの目的を短く記述します。
本文と各セクションには、利用者が呼び出し方と結果を判断するための情報を書きます。

| セクション | 内容 |
| --- | --- |
| `Args` | 引数の意味、値域、既定値、パスの基準 |
| `Returns` | 戻り値の型と意味 |
| `Attributes` | Enumの各メンバーなど、公開属性の意味 |
| `Raises` | 発生する例外の型と条件 |
| `Warns` | 発生する警告とその条件 |
| `Examples` | 典型的な利用例 |

データクラスは、クラスの`Args`でコンストラクタ引数を説明します。
各引数と同名の公開属性に、その値を保持します。

RuffのGoogle形式チェックをCIでも実行し、docstringの有無と記述形式を確認します。

## 例外の発生タイミング

`state`、`Specification`、`any_action`、`weak_fairness`の説明には、
宣言時の検証で発生する例外を記述します。
`initial`・`action`・`temporal`で登録した関数のソースは、
`compile_spec`・`export`・`check`が検証するため、その発生タイミングを本文で説明します。

`unchanged`・`unconstrained`・`leads_to`は仕様関数の式に記述する演算子として説明し、
通常のPython呼び出しとコンパイル時の検証、それぞれの例外条件を記述します。
保存や外部プロセスの起動を伴うAPIには、ファイル操作と設定・実行に関する例外も記述します。

## コードの参照先

- [モデルと仕様の宣言](../src/tlacraftpy/model.py)
- [コンパイルとファイル出力](../src/tlacraftpy/compiler.py)
- [TLCの実行と検証結果](../src/tlacraftpy/runner.py)
