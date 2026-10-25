# xangi Extension セットアップ

このリポジトリは、Even G2 bridge とローカル Whisper を xangi の Managed
Extension として起動できます。

## Extensionをセットアップする

1. Python 環境を作成します。

   ```bash
   cd bridge
   uv sync
   cp .env.example .env
   ```

2. `bridge/.env` を編集します。`EVEN_BRIDGE_TOKEN` は外部へ公開しないでください。
   Managed runtime は親 xangi の Web URL を自動利用するため、`XANGI_BASE_URL` は
   単体起動時のfallbackです。
3. リポジトリrootでExtensionを登録・起動します。

   ```bash
   xangi extension link ./xangi-extension.json
   xangi extension start xangi-even-g2
   xangi extension status xangi-even-g2
   xangi extension doctor xangi-even-g2
   ```

   `start`だけで完了とせず、`doctor`でbridgeとSTTがreadyになることを確認します。
4. `xangi extension list`で`xangi-even-g2`がautostartとして登録されたことを確認します。
5. Managed Extensionでは、Bridge URLには下記手順で作る短いHTTPS URLを設定します。内部の転送先は`http://<xangi-host>:<xangi-port>/api/devices/xangi-even-g2`です。この入口に対応したxangi本体が必要です。専用tokenは`EVEN_BRIDGE_TOKEN`（`DEVICE_BRIDGE_TOKEN`も利用可）を使います。bridgeとSTTはloopbackの自動割当ポートで起動し、設定済みのHOST/PORTは単体起動時だけ使います。内部ポートをcompanionへ設定しないでください。

旧PM2プロセスは移行確認後に停止してください。既存の8791番URLは共通入口へ変更する必要があります。

bridgeだけを起動し、外部STT endpointまたはcommandを使う場合は
`EVEN_EXTENSION_STT_ENABLED=false`を設定します。

## 短いHTTPS URLで接続する（推奨）

iPhoneとxangiを動かすパソコンを、同じTailscaleのプライベートネットワーク（Tailnet）に接続します。この方法では、そのネットワークで接続を許可された端末だけがアクセスできます。インターネット全体には公開しません。G2を使う間はiPhoneのTailscaleをONにしてください。G2の接続には専用トークンも必要です。

### xangiを動かすパソコンで設定する

次の例は、パソコン内でxangiが `http://127.0.0.1:18888` で動いている場合です。別のポートを使っている場合は、以下の `18888` をすべて置き換えてください。

**すでに別の端末からHTTPでxangiを開いている場合、この設定で接続先がHTTPSに変わります。** ブックマーク、iPhoneのショートカット、連携アプリのURLも変更してください。このパソコンでTailscaleの接続設定を済ませている場合は、先に下の「既存のTailscale設定から移行する場合」を確認してください。

```bash
tailscale serve --bg --https=18888 http://127.0.0.1:18888
tailscale serve --bg --https=18888 --set-path=/eveng2 http://127.0.0.1:18888/api/devices/xangi-even-g2
```

### iPhoneで設定する

上のコマンドが表示したホスト名を使い、companionアプリの **Bridge URL** に次のURLを保存します。トークン欄には自分の専用トークンを設定します。

```text
https://<自分のマシン>.<自分のTailnet>.ts.net:18888/eveng2
```

xangiの画面を開くときは、末尾の `/eveng2` を除いたURLを使います。HTTPSの証明書はホスト名に対して発行されるため、`100.x.x.x` のIPアドレスではなく、このホスト名を使ってください。G2でセッション一覧が表示されれば接続できています。トークンは他人に共有しないでください。

<details>
<summary>既存のTailscale設定から移行する場合</summary>

変更前に `tailscale serve status --json` の結果を保存・確認します。18888番に `127.0.0.1:18888` への `TCPForward` がある場合は、`tailscale serve --tcp=18888 off` で停止してから上の2つの設定コマンドを実行します。切替中は別の端末から一時的に接続できなくなります。パソコン内部のloopback HTTP接続は変わりません。

18888番を別サービスが使っている場合や、Tailscale Funnelでインターネットに公開している場合は、この手順で上書きせず、既存設定を確認してください。同じポートの中で、URLのパスごとにインターネット公開とプライベート接続を分けることはできません。この設定のために他のポートを変更する必要はありません。

以前G2用に別ポートやインターネット公開の経路を設定した場合は、新URLで接続を確認した後、その古い経路だけを削除します。認証を確認する場合、G2にトークンなしでアクセスするとHTTP 401になります。設定の詳細は[Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve)を参照してください。

</details>

## workspace skillを追加・更新する

初回setupまたはExtension更新後に、同梱skill
`skills/xs-xangi-even-g2/SKILL.md`とworkspace内の同名skillを比較します。

- workspaceの既存配置規則を優先し、規則がなければ`skills/xs-xangi-even-g2/`を提案します。
- API、運用手順、失敗時の扱いに実質差分がある場合だけ、理由・対象path・変更概要を提示します。
- Extensionのsetupや更新の許可はworkspace変更の許可を兼ねません。利用者の承認後にだけ最小差分を反映します。
- repository全体をworkspaceの`skills/`直下へcloneせず、Extension sourceとworkspace skillを分けて管理します。

## 更新

repository管理Extensionの更新では、manifestの`update.prepare`が
`bridge/uv.lock`どおりに`uv sync --frozen`を実行します。更新後は`status`と
`doctor`を再確認し、必要なら同梱skillの実質差分を別途提案します。

## ログ

Managed Extensionのbridge/STTログはworkspaceの`.xangi/logs/xangi-even-g2/bridge.log`と`stt.log`へ保存します。各5 MiB、過去3世代を保持します。音声受信・認識完了・HTTP応答書込を記録し、文字起こし本文は保存しません。HTTP応答書込はG2画面への表示成功を保証しません。

モデルは`bridge/.env`の`EVEN_STT_MODEL`で指定します。親プロセスの同名環境変数がある場合はそちらが優先されます。変更はEven G2拡張の再起動後に有効です。
