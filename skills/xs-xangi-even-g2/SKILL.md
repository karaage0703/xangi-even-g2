---
name: xs-xangi-even-g2
description: Even Realities G2用xangiクライアントをManaged Extensionとして導入・運用し、EHPKのbuildやEven Hub配布も行う。「G2をセットアップして」「bridgeを確認して」「Even Hubへ配布して」で使用。
---

# xangi-even-g2

Even G2アプリ、bridge、Whisper STTをセットアップし、xangi Managed Extensionとして運用する。

`[SKILL_DIR]`はこのSKILL.mdのdirectory、`[REPOSITORY]`は`[SKILL_DIR]/../..`を解決したrepository rootを表す。

## 実行フロー

### Step 1: 依頼範囲を固定する

次の操作を分けて扱う。

- Extensionの導入・更新・起動・停止
- `.ehpk`のbuild
- Even Hubへのupload、Beta昇格、Public申請

buildだけの依頼では外部uploadを行わない。Extension更新の許可はworkspace skillや`AGENTS.md`変更の許可を兼ねない。

### Step 2: 現在状態を確認する

```bash
cd [REPOSITORY]
git status --short
xangi extension status xangi-even-g2
xangi extension doctor xangi-even-g2
```

未登録ならStep 3へ進む。登録済みならcheckout、`bridge/.env`、旧PM2 process、8791/8792番portの使用状況を確認してから変更する。

### Step 3: Managed Extensionをセットアップする

```bash
cd [REPOSITORY]/bridge
uv sync --frozen
cp .env.example .env
```

`bridge/.env`で最低限次を設定する。

- `EVEN_BRIDGE_TOKEN`: G2 clientとの認証token
- `EVEN_BRIDGE_HOST`: Tailnetから直接接続する場合は`0.0.0.0`
- `EVEN_STT_MODEL`: 標準は`medium`、memoryが厳しい場合は`base`
- `EVEN_EXTENSION_STT_ENABLED`: 外部STTを使う場合だけ`false`

Managed runtimeは親xangiのWeb URLを受け取るため、`XANGI_BASE_URL`は単体起動時のfallbackとして扱う。

旧PM2版が同じportを使っている場合は、対象processを特定して停止し、port解放を確認する。定義はrollbackが必要なら残す。

```bash
cd [REPOSITORY]
xangi extension link ./xangi-extension.json
xangi extension start xangi-even-g2
xangi extension status xangi-even-g2
xangi extension doctor xangi-even-g2
```

`status`の起動成功だけで完了とせず、`doctor`でbridgeとSTTの`ready`、STT model/deviceまで確認する。

### Step 4: G2実機で確認する

Even Hub companion画面へBridge URLとtokenを設定し、次を確認する。

- session一覧と`+ New Session`が表示される
- リング長押し中だけ`Listening`表示とanimationが出る
- 指を離すと文字起こし確認へ進む
- tap開始・tap停止も利用できる
- 送信後に応答本文と回答候補を閲覧できる
- build labelが意図したversionになっている

### Step 5: 更新する

repository管理Extensionでは、xangiのExtensions画面または現行xangiが提供するExtension更新機能を使う。`xangi-extension.json`の`update.prepare`が`bridge`のlockfileどおりに環境を同期する。

更新後は同梱の`skills/xs-xangi-even-g2/SKILL.md`とworkspace側の同名skillを比較し、APIや運用手順に実質差分がある場合だけ更新を提案する。workspaceの既存指示を保持し、承認前に変更しない。

### Step 6: `.ehpk`をbuildする

```bash
cd [REPOSITORY]
npm ci
npm test
npm run build
npm run pack
```

配布前に`package.json`、`package-lock.json`、`app.json`、`src/version.ts`のversionが一致することを確認する。

private検証用にBridge URL/tokenを初期値として入れる場合だけ次を使う。生成物は秘密情報を含むものとして扱う。

```bash
cd [REPOSITORY]
BRIDGE_URL=http://100.x.y.z:8791 \
BRIDGE_TOKEN=your-token \
npm run pack:configured -- --output ./xangi-even-g2.ehpk
```

### Step 7: Even Hubへ配布する

uploadや配布状態変更を明示依頼された場合に限り、Even Hub Developer Portalで対象projectと現在の配布状態を確認する。

1. `.ehpk`のapp名、package ID、versionを確認する。
2. buildをuploadし、内容に合うchangelogを入力する。
3. 依頼がBeta配布ならBetaへ昇格する。Public申請は別の許可として扱う。
4. project画面を再読込し、新旧buildのversionと状態を確認する。

認証が必要な場合は利用者にbrowser上で完了してもらい、passwordや確認codeをchatへ書かせない。

## 単体起動とrollback

Managed Extensionを使えない環境だけ、`bridge/README.md`の単体起動またはPM2手順を使う。rollback時はExtensionを停止して8791/8792番portの解放を確認してから、保持していた旧PM2 processを起動する。

## Gotchas / よくある失敗

- repositoryをworkspaceの`skills/`直下へ丸ごと置くと、Extension sourceとworkspace skillの所有が混ざる。同梱skillは`skills/xs-xangi-even-g2/`から必要な差分だけworkspaceへ反映する。
- Managed Extensionと旧PM2版は同じbridge/STT portで同時起動できない。起動前にprocessとportの両方を確認する。
- G2 clientは親xangiのloopback proxyではなくTailnet向けbridge listenerへ接続する。管理用の動的portをcompanion画面へ設定しない。
- `doctor`がwarming upなら、Whisper modelの初期化完了または具体的なerrorを確認する。
- configured `.ehpk`、`bridge/.env`、token、個人用URLをcommitや公開ログへ含めない。

## 完了報告

```text
xangi-even-g2作業完了。
- Extension: <status / doctor結果>
- G2実機: <確認済み / 未確認>
- Build: <version / 未実施>
- Even Hub: <配布状態 / 未変更>
- 変更・URL: <commit、PR、portal URLなど>
```

## 使用例

```text
xangi-even-g2をManaged Extensionとしてセットアップして
G2のbridgeとWhisperが正常か確認して
EHPKをbuildして
Even HubのBetaを更新して
```

## 完了前チェックリスト

- [ ] 依頼範囲外のupload、配布状態変更、再起動を行っていない
- [ ] `status`と`doctor`を確認した
- [ ] runtime変更時はG2実機の成功条件を確認した
- [ ] build時は4つのversion sourceと生成物を確認した
- [ ] 外部配布時はportalを再読込して状態を確認した
- [ ] 秘密情報が出力・commit・配布物へ意図せず入っていない
- [ ] 結果を整形して本体テキストで報告した
