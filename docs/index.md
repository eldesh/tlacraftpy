# tlacraftpy

tlacraftpyは、PythonでTLA+のサブセットに相当する仕様を記述し、TLCで検証するライブラリです。
状態・遷移・時相的な性質を定義し、検証結果と反例をPython側の名前で確認できます。

## はじめのモデル

[チュートリアル](tutorial.md)では、要求・応答モデルを作り、
「要求が来たら、いつか応答する」という性質を検証します。
公平性を仮定した場合の成立と、仮定を外した場合の反例を確認できます。
準備するPythonパッケージとJava・TLCについては、[利用ガイド](usage.md#インストール)に記載しています。

## 使い方と記述できる仕様

- [利用ガイド](usage.md)
- [言語リファレンス](language.md)
- [FIFOモデル](fifo.md)

## 開発と配布

- [開発手順](development.md)
- [パッケージの配布](distribution.md)

ソースコードとサンプルは[GitHubリポジトリ](https://github.com/eldesh/tlacraftpy)で管理しています。
