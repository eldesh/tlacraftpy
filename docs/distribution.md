# パッケージの配布

## 配布形式

配布名とimport名は`tlacraftpy`です。Python 3.11以降を対象に、
setuptoolsと`pyproject.toml`による標準的なPythonパッケージとして配布します。

公開用のファイルは、wheelとソース配布物（sdist）の2種類です。

| ファイル | 用途 |
| --- | --- |
| `tlacraftpy-0.1.0-py3-none-any.whl` | 利用者がpipでインストールするPythonパッケージ |
| `tlacraftpy-0.1.0.tar.gz` | ソース、ドキュメント、サンプル、テストを含む配布物 |

wheelの`py3-none-any`は、対応するPython 3でOSに依存せずインストールできる形式を示します。
JavaとTLCは、モデル検査を実行する環境に用意し、`[tool.tlacraftpy]`でパスを設定します。

## ライセンス

MITライセンスで配布します。条文と著作権表示は[LICENSE](../LICENSE)にあります。
wheelとソース配布物にLICENSEを同梱し、パッケージ情報の`License-Expression`に`MIT`を記録します。

## ビルドと検査

プロジェクトのルートで、配布用のツールをインストールします。

```bash
python -m pip install -e '.[release]'
```

配布用のファイルは`dist/`に生成します。
`build`はソース配布物を作り、そのソース配布物からwheelをビルドします。

```bash
python -m build
python -m twine check --strict dist/*
```

Twineの検査では、パッケージ情報とPyPIに掲載するREADMEの形式を確認します。
公開するファイルのハッシュは次のコマンドで確認できます。

```bash
sha256sum dist/tlacraftpy-0.1.0*
```

## 配布物からの動作確認

新しい仮想環境にwheelをインストールし、importとテストを確認します。

```bash
python -m venv /tmp/tlacraftpy-wheel
/tmp/tlacraftpy-wheel/bin/python -m pip install dist/tlacraftpy-0.1.0-py3-none-any.whl
/tmp/tlacraftpy-wheel/bin/python -c "import tlacraftpy; print(tlacraftpy.__file__)"
TLACRAFTPY_TLC_JAR=/path/to/tla2tools.jar \
    /tmp/tlacraftpy-wheel/bin/python -m unittest discover -s tests -v
```

ソース配布物も、別の仮想環境にインストールして同じテストを実行します。

```bash
python -m venv /tmp/tlacraftpy-sdist
/tmp/tlacraftpy-sdist/bin/python -m pip install dist/tlacraftpy-0.1.0.tar.gz
TLACRAFTPY_TLC_JAR=/path/to/tla2tools.jar \
    /tmp/tlacraftpy-sdist/bin/python -m unittest discover -s tests -v
```

CIではPython 3.11〜3.14で配布物をビルド・検査し、wheelをインストールして、
単体テスト、実TLCによる統合テスト、サンプルを実行します。

## PyPIへの公開

公開作業は利用者の承認後に行います。対象のバージョン、ライセンス、配布ファイルのハッシュ、
検査結果を確認し、承認されたwheelとソース配布物をPyPIへ登録します。
バージョン番号は`pyproject.toml`の`[project].version`で管理します。

公開時にはPyPIのプロジェクト所有者として認証し、承認されたファイルを指定してTwineで登録します。
認証情報は公開作業用の環境で管理します。

利用者は公開後、次のコマンドでインストールできます。

```bash
python -m pip install tlacraftpy
```

## 参考資料

- [Python Packaging User Guide: Packaging Python Projects](https://packaging.python.org/en/latest/tutorials/packaging-projects/)
- [Python Packaging User Guide: Writing your pyproject.toml](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/)
