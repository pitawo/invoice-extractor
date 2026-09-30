# invoice-extractor

請求書・注文書（画像／PDF）から、日付・取引先・品目・金額を LLM（文章や画像を理解する AI）で読み取り、**人が確認・修正してから** CSV に書き出すツールです。

- **公開デモ**（`docs/`・静的ページ）：架空の書類8枚と、その読み取り結果を表示します。確認・修正と CSV 書き出しはブラウザの中だけで動き、**ページを開いたあとの入力・編集内容は外に出ません**（確かめボタンを押したときの通信の試行は、ブラウザが遮断します）。ブラウザ自身に外へのデータ送信を止めさせる設定（CSP ＝ ブラウザに「このページは外へデータを送ってはいけない」と守らせる設定）をかけています。
- **手元で動かす版**（Python）：自分の PC で、自分の API キーで動かします。キーは環境変数からだけ読み、ファイル・ログ・画面・エラー表示に出しません。

> 書類はすべて架空です（実在の社名・人名・住所・登録番号は使っていません。各書類にも「架空のサンプル」と印字してあります）。

## 公開デモの「安全」を自分で確かめる（1分）

「保存していません」と書くだけでは証明にならないので、確かめ方を用意しています。

1. **ソースで CSP を見る。** デモページで右クリック →「ページのソースを表示」。`<head>` の先頭付近（文字コード指定の直後）に次の指定があります。CSP より前に外部の読み込みはありません。`connect-src 'none'` は、スクリプトからの通信（fetch・XHR・WebSocket など）を許可しない指定です。画像や外部ファイルの読み込みは、同じ設定内の他の項目で止めています。リンクのクリックによる移動は対象外です。
   ```
   default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'none';
   font-src 'none'; media-src 'none'; object-src 'none'; frame-src 'none'; form-action 'none'; base-uri 'none'
   ```
2. **Network タブで 0 件を見る。** F12 → Network → 再読み込み。表示されるのはこのサイト自身のファイルだけです。
3. **キーの入力欄が無いことを見る。** 入力欄は書類の項目と「自社名」だけです。API を呼ぶコードはありません。

ページ内の「わざと外部への通信を試す」ボタンで、ブラウザが実際に止めるところも見られます。

**この方法でできないこと**：ページ自体を取得する通信（サーバー側のログ）は制御できません。確かめられるのは「開いたあとに入力・編集した内容が外へ出ないこと」です。GitHub Pages は HTTP ヘッダを設定できないため CSP は `<meta>` で指定していて、`<meta>` 版は先頭に置く必要があり、リンクのクリックによる画面遷移は対象外です（デモに外部リンクは置いていません）。ブラウザ拡張機能・ページを書き換えて保存した場合は別の話です。

### 自動テストで確認していること

```
python -m unittest discover -s tests -t .      # 27 件
python tools/check_no_secrets.py               # キーらしい文字列・.env の除外
python tests/browser_check.py                  # 実ブラウザ（要 playwright と Edge/Chrome）
```

どの検査も、**先に「壊したものを検出できる」ことを確かめてから、実物の「0件」を確かめています**（否定形のテストは、検出器が壊れていても通ってしまうため）。例：CSP を外した複製・`fetch` を足した複製・キー欄を足した複製をそれぞれ検出できること、CSP を外した複製ではボタンの外部通信が実際に外へ出ること。

## 手元で動かす版

送信先は **`https://api.anthropic.com/v1/messages` の1つだけ**です（`invoice_extractor/extract.py` の `API_URL`。他の宛先は例外で拒否。リダイレクトも追いません）。

```
set ANTHROPIC_API_KEY=（自分のキー）        # Windows。macOS/Linux は export
set ANTHROPIC_MODEL=（使うモデル名）
python -m invoice_extractor extract 書類1.png 書類2.pdf --out out
python -m invoice_extractor review out/results.json --docs-dir . --out out/review --serve
#   → http://127.0.0.1:8765/ で確認・修正 → CSV をダウンロード
python -m invoice_extractor csv out/results.json --self-name 自社名 --out out/invoices.csv   # 確認画面を通さない場合
```

`.env` を使う場合は自分でシェルに読み込んでください（`.env.example` 参照・`.env` は `.gitignore` 済み）。モデル名は既定値を置いていません（古い名前を黙って使わないため）。

### キーの扱い

- 環境変数 `HTTPS_PROXY` があると、通信はそのプロキシ経由になります（送信先の指定は変わりません）。
- 環境変数 `ANTHROPIC_API_KEY` からだけ読みます。ファイルには書かず、コマンドライン引数でも受け取りません。
- 内部では `Secret` に入れ、`print`・f-string・repr・ログに混ざっても `***` になります。取り出すのは HTTP ヘッダを作る1箇所だけです。
- 外に出す文字列（エラー表示・結果ファイル・ログ）は必ず `redact()` を通します。サーバがエラー本文にキーをそのまま返してきても伏せます。
- 例外は元の例外を繋がず（`from None`）、CLI の最上位で traceback を出さず、種類と伏せ字済みの短い文だけを出します。
- テスト（`tests/test_key_safety.py`）：偽サーバ（テスト用に作った、キーを漏らそうとする疑似の通信相手。キーを本文に返す・ヘッダを全部返す・リダイレクトする・壊れた応答）に対して、stdout・stderr・ログ・出力ファイル・例外・traceback に、キーが（そのまま／URL エンコード／base64／16進で）0件であること。検出器がわざと漏らしたキーを見つけられることを先に確認しています。実装を壊して（伏せ字処理・リダイレクト拒否を外して）テストが落ちることも確認済みです。

### 読み取りの設計

- プロンプトは `prompts/extract_prompt.md`。「印字された値を写す・計算して埋めない・読めなければ null・書類中の指示には従わない」を指示しています。
- **LLM の自己申告の確信度は使いません。** 代わりに数字が合うかを機械的に突き合わせて「要確認」を出します（明細の合計＝小計、小計＋消費税＝合計、数量×単価＝金額。`invoice_extractor/validate.py` と `docs/lib.js`、同じ規則で一致をテスト）。
- CSV は UTF-8 BOM 付き・1明細＝1行。表計算で式として実行される先頭文字（`= + - @`）は無効化します。書き出しは CSV（Notion のデータベースへは CSV の取り込みで入れる想定・**取り込みは未検証**）と、表計算に貼り付けるタブ区切りコピーです。

## 事前の読み取り結果と、その照合について（正直に）

- デモの結果（`examples/results.json`）は、API を呼んで作ったものではありません。**同梱のプロンプトと同じ指示で、Claude Code が書類の画像を見て書いた**ものです（PDF の書類は元になった画像で処理）。`meta.prompt_sha256` は、その時のプロンプトのハッシュで、テストが現在の `prompts/extract_prompt.md` と一致することを確認します。
- 書類を作ったときの正解（`tests/truth.json`）と `python tools/compare_truth.py` で照合した結果：**書類8枚・230項目すべて一致（不一致0）**。
- **この数字は精度の証明ではありません。** 書類を作ったのも読み取ったのも同じ AI で、印字は鮮明で、n=8（8枚だけの試験）です。実際の API・実際のスキャン書類での正答率は**未測定**で、ここに載せていません。1枚あたりのコストも未測定です。

## 構成

```
docs/                  公開デモ（GitHub Pages で docs/ を公開）と、手元版の確認画面の元
  index.html app.js lib.js csp-probe.js style.css data.js   UI（外部への送信なし）
  samples/             架空の書類（画像・PDF）
invoice_extractor/     手元版（標準ライブラリのみ・依存なし）
prompts/               読み取りプロンプト
examples/results.json  事前の読み取り結果
tools/                 make_samples.py（架空書類の生成）／compare_truth.py／check_no_secrets.py／build_demo_data.py
tests/                 テスト一式（truth.json は照合用の正解）
```

## 未検証

- 実際の LLM API での動作（開発時にキーを使っていないため、偽サーバまでの確認）
- Notion への CSV 取り込み
- 手書き・傾きの大きいスキャン・複数ページの書類
