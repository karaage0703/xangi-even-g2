# 使い方と開発

[English](usage.en.md) | [README](../README.md) | [設計](design.md)

## G2の操作

セッション一覧:

- 上下スクロール: セッション選択
- Discord セッションは通常チャンネルを `#チャンネル名`、スレッドを `T: スレッド名` で表示
- タップ: 選択セッションを開く
- `+ New Session`: 新しい会話を開く（最初の送信時に保存）
- ダブルタップ: 終了

セッション画面:

- 上下スクロール: 履歴・ページ移動
- 履歴の端まで移動すると、前後の履歴を30件ずつ追加取得
- 最初のページから前へ移動すると最新へ、最後のページから次へ移動すると最初へ循環
- xangi が生成した回答候補がある場合は、会話本文の末尾に続く追加ページとして自動表示（固定候補は表示しない）
- 長押し: 押している間だけ録音
- 指を離す: 録音停止、文字起こし確認を表示
- タップ: 従来方式の録音開始
- もう一度タップ: 従来方式の録音停止、文字起こし確認を表示
- 確認画面でタップ: 送信
- 確認画面でダブルタップ: 破棄
- セッション画面でダブルタップ: セッション一覧へ戻る

送信先は開いているセッションのplatformを維持します。Discord セッションは同じDiscord会話をxangiのremote input経路で継続し、Webセッションは同じWebセッションを継続します。Discordの完了本文は先に表示し、その後に同じセッションの履歴を再取得して照合します。

Discordへの送信受付後は会話画面へ戻り、返信取得後に回答を自動表示します。Slackなどは履歴閲覧のみ対応しています。

## `.ehpk` の作成

通常の開発ビルドは Bridge URL / token を埋め込まずに package を作ります。

```bash
npm run pack
```

Bridge URL と token は、iPhone の companion 画面で入力して保存できます。

同じ URL/token を最初から入れた private build を作りたい場合だけ、`pack:configured` を使います。通常利用では必須ではありません。

```bash
BRIDGE_URL=http://100.x.y.z:8791 \
BRIDGE_TOKEN=your-token \
npm run pack:configured -- --output ./xangi-even-g2.ehpk
```

`pack:configured` は build env に URL/token を渡して package を作ります。URL/token は git には書き込まれません。通常は companion 画面で入力すれば足ります。

## アプリ設定

iPhone companion 画面で以下を保存できます。

- `Bridge URL`: 実行中の xangi-even-g2 bridge URL
- `Token`: `EVEN_BRIDGE_TOKEN`
- `Save`: companion WebView localStorage に保存
- `Clear`: 保存値を削除

保存設定はEven側ストレージにも同期されます。設定入りのprivate packageにはtokenが含まれるため公開しないでください。

## 開発コマンド

```bash
npm ci
npm test
npm run build
npm run pack
npm run pack:configured -- --bridge-url http://100.x.y.z:8791 --bridge-token your-token
npm run pack:check
```

配布前は以下の version を揃えます。

- `package.json`
- `package-lock.json`
- `app.json`
- `src/version.ts`

### 起動順の設定

対応するxangiでは、既定でgpuグループ内の初期化を直列化する。CPU運用やSTT無効時に不要ならホストのextensions.jsonの対象レコードで `"startup": null` を指定できる。別GPUを使う場合はexclusiveGroupのラベルを分け、実際のデバイス設定も別途合わせる。タイムアウト時はホストのstatusで所有元と待機理由を確認する。
