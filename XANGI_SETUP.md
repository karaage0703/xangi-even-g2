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
5. Even Hub companion画面のBridge URLはそのまま使います。プロセスはExtensionが
   管理しますが、G2 clientはTailnet向けlistenerへ直接接続します。

従来のPM2 bridge / STTとManaged Extensionは同じportで同時起動できません。
Extensionを起動する前に、旧processを停止してportが空いたことを確認してください。

bridgeだけを起動し、外部STT endpointまたはcommandを使う場合は
`EVEN_EXTENSION_STT_ENABLED=false`を設定します。

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
