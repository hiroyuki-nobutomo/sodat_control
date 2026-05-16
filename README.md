# Sensor SFC v2 Installation & Operation Guide

Welcome to the unified Sensor SFC deployment system. We have simplified the process into a clear, numbered workflow.

---

## ⚡ Web Quick Start (Recommended)

The easiest way to provision a new device is the **web setup page**, which walks you through making one microSD card. After you insert it into the Pi and power on, everything (install, service-account key, device-id from hostname, systemd service) happens automatically.

👉 **Open the web setup:** https://sodat-control.vercel.app/

What the page covers:
1. Install Raspberry Pi Imager (one-time, on your PC)
2. Flash Raspberry Pi OS Lite (64-bit) to a microSD with hostname `sodat-sNN`, Wi-Fi, and your SSH user (all done inside Pi Imager's customisation panel)
3. Use the in-browser tool to generate a `firstrun.sh` snippet that embeds the project's `service_account.json` as base64 (the key never leaves your PC — pure client-side JavaScript)
4. Paste the snippet into the SD card's `firstrun.sh`, eject, boot the Pi — done

The `device_id` (`S01`, `S02`, ...) is auto-derived from the hostname you set in Pi Imager, so there's no per-device config edit.

> 🛠️ **One-time project setup (do this once for the whole study, not per device):**
> 1. In Google Cloud Console, create a Service Account, then generate a JSON key.
> 2. Note its email (`xxx@xxx.iam.gserviceaccount.com`).
> 3. Share the target Google Drive folder(s) and Spreadsheet with that email, granting **Editor** access.
> 4. Keep that JSON file secret — distribute it to project members via a secure channel (1Password, encrypted email, lab share). Each researcher feeds it into the web setup tool on their own PC.

---

## 🖥️ Manual install (fallback)

If the web setup isn't available, you can still install over SSH after flashing a stock Pi OS image with Pi Imager's customisation:

```bash
ssh <username>@sodat-s01.local
curl -fsSL https://raw.githubusercontent.com/hiroyuki-nobutomo/sodat_control/main/bootstrap.sh | sudo bash
```

The installer sets up everything (drivers, I2C, services, Python environment), then asks two short questions:

1. **Device ID** — pick a code for this Pi (e.g. `S01`, `A01`). Press Enter on the other prompts to accept defaults.
2. **Run a sensor test now?** — say **Yes** to verify the hardware.

Then place the service-account key manually:

```bash
# From your PC (where service_account.json lives):
scp service_account.json <username>@sodat-s01.local:~/sensor_sfc/secrets/

# On the Pi, restart the service to pick it up:
./04_start_service.sh --stop && ./04_start_service.sh
```

---

## 🚀 Unified Workflow (The 1-2-3-4 Path)

Regardless of whether your SD card is blank or has old code, follow these steps in order:

### Step 0: Stop Running Services (Safety First)
If you are updating an existing device, ensure the old service is stopped before unzipping.
```bash
./04_start_service.sh --stop
```
*(If you don't have this script yet, just proceed to Step 1)*

### Step 1: Install or Update
Run this script from any location. It will automatically discover existing installations or establish a new one in your home directory (e.g., `/home/$USER/sensor_sfc/`).
```bash
sudo ./01_install_update.sh
```
*   **What it does:** Automatically fixes permissions, installs drivers, handles path reconciliation, and merges your configuration.
*   **Interactive Test:** At the end, it will ask if you want to run the sensor test immediately. Say **Yes**!

### Step 2: Verify Hardware (Optional)
Prove that the Pi can "see" your sensors. You can run this repeatedly while plugging devices in.
```bash
./02_check_hardware.sh
```

### Step 3: Test Sensors
To perform a 3-minute rapid sensing and cloud-upload test:
```bash
./03_test_sensors.sh
```

### Step 4: Start Production
Go into background recording mode.
```bash
./04_start_service.sh
```

---

## 🛠 Operation Tips

### Adjusting Settings (IDs, Intervals, Retention)
If you want to change the Device ID (e.g., S01, A01) or adjust how often data is recorded/uploaded, use the interactive configuration tool:
```bash
./05_configure.sh
```
*   **Purpose:** Safely updates your `config.yaml` without manual text editing.
*   **Options:** Device ID, Sensing Interval (s), Camera Interval (s), Upload Interval (s), Upload Start Offset (s), and Local Retention (days).
*   **When to use:** Run this *after* the initial installation if you need to customize settings for a specific deployment.

### Hot-Plugging Sensors
You can unplug and move USB sensors (Camera, Arduino, Tokyo Devices) to different ports while the system is running. The system will auto-discover the new ports on the next sensing cycle.

### Management Commands
*   **Check WiFi:**   `./test_wifi.sh`.
*   **Live Logs:**    `./04_start_service.sh --log`.

---

## ⚠️ Special Hardware: Arduino UNO R4
Due to a Pi 5 hardware limitation, you must flash the Arduino via **PC or Mac**.
1. Open `arduino/gravity_node/gravity_node.ino` in the Arduino IDE on your computer.
2. Select board **"Arduino UNO R4 Minima"** and click **Upload**.
3. Once flashed, connect it to the Raspberry Pi.

---
---

# Sensor SFC v2 インストール & 運用ガイド (日本語)

新しい統合デプロイメントシステムへようこそ。手順を明確な番号順に整理しました。

---

## ⚡ Web クイックスタート (推奨)

新しい機器を立ち上げる最も簡単な方法は **Web セットアップページ**です。1 枚の microSD を作る手順を順に案内してくれます。SD を Pi に挿して電源を入れれば、インストール・service_account.json 配置・ホスト名からの device_id 自動設定・systemd サービス起動まで全て自動です。

👉 **Web セットアップを開く:** https://sodat-control.vercel.app/

ページでカバーする内容:
1. Raspberry Pi Imager をインストール (PC 側、1 回のみ)
2. Pi Imager で Raspberry Pi OS Lite (64-bit) を microSD に書き込み、Pi Imager のカスタマイズ画面でホスト名 `sodat-sNN` / Wi-Fi / SSH ユーザを設定
3. ブラウザ内ツールで `service_account.json` を base64 化して埋め込んだ `firstrun.sh` snippet を生成 (鍵は PC から外に出ません — 完全クライアントサイド処理)
4. snippet を SD カード上の `firstrun.sh` に貼り付け、取り出して Pi を起動 — 以上

`device_id` (`S01`, `S02`, ...) は Pi Imager で設定したホスト名から自動導出されるので、機器ごとに config を編集する必要はありません。

> 🛠️ **プロジェクト初回セットアップ (研究全体で 1 回だけ、機器ごとではありません):**
> 1. Google Cloud Console で Service Account を作成し、JSON キーを発行
> 2. その Service Account のメールアドレス (`xxx@xxx.iam.gserviceaccount.com`) を控える
> 3. 出力先の Google Drive フォルダおよびスプレッドシートを、そのメールアドレスに **編集者**権限で共有
> 4. その JSON キーは機密情報。プロジェクトメンバーには 1Password・暗号化メール・ラボ内共有など安全な経路で配布。各研究者は自分の PC で Web セットアップツールにそのファイルを投入

---

## 🖥️ 手動インストール (フォールバック)

Web セットアップが使えない場合は、Pi Imager のカスタマイズで標準 Pi OS を焼いた後、SSH 経由でインストールできます:

```bash
ssh <ユーザー名>@sodat-s01.local
curl -fsSL https://raw.githubusercontent.com/hiroyuki-nobutomo/sodat_control/main/bootstrap.sh | sudo bash
```

インストーラがドライバ・I2C・サービス・Python 環境などをすべて構築し、最後に 2 つだけ質問してきます:

1. **Device ID** — この Pi の機器名 (例: `S01`, `A01`) を選択。
2. **センサーテストを実行しますか?** — **Yes** でハードウェア動作確認まで自動実行。

その後、service_account.json を手動配置:

```bash
# PC 側 (service_account.json が手元にある PC):
scp service_account.json <ユーザー名>@sodat-s01.local:~/sensor_sfc/secrets/

# Pi 側でサービスを再起動して反映:
./04_start_service.sh --stop && ./04_start_service.sh
```

---

## 🚀 統合ワークフロー (1-2-3-4 ステップ)

以下のステップに従うだけで完了します。

### ステップ 0: サービスの停止
アップデートの場合は、作業前に必ずサービスを停止してください。
```bash
./04_start_service.sh --stop
```

### ステップ 1: インストール / アップデート (Install/Update)
解凍したフォルダの中で以下のコマンドを実行してください。プロジェクトは自動的にホームディレクトリ (`/home/$USER/sensor_sfc/`) にインストールされます。
```bash
sudo ./01_install_update.sh
```
*   **何をするか:** パーミッション修正、ドライバインストール、パス整理、設定の引継ぎを自動で行います。
*   **テスト:** 最後に「テストを実行しますか？」と聞かれるので、**Yes** と答えてください。

### ステップ 2: ハードウェア確認 (Check Hardware)
Pi がセンサーを認識しているか確認します。デバイスを接続しながら何度でも実行可能です。
```bash
./02_check_hardware.sh
```

### ステップ 3: 動作テスト (Test Sensors)
3分間の高速計測とクラウドへのアップロードを確認します。
```bash
./03_test_sensors.sh
```

### ステップ 4: 本番稼働の開始 (Start Service)
バックグラウンドでの自動記録を開始します。
```bash
./04_start_service.sh
```

---

## 🛠 運用のコツ

### 設定の変更 (ID、記録間隔、データ保持期間)
Device ID (例: S01, A01) の変更や、記録/アップロードの間隔を調整したい場合は、以下の対話型設定ツールを使用してください。
```bash
./05_configure.sh
```
*   **目的:** `config.yaml` を直接編集することなく、安全に設定を更新できます。
*   **設定項目:** Device ID、計測間隔、カメラ間隔、アップロード間隔、アップロード開始オフセット、ローカルデータ保持期間。
*   **いつ使うか:** インストール完了後、特定の設置場所に合わせて設定をカスタマイズしたい時に実行してください。

### センサーの抜き差し (Hot-Plug)
稼働中に USB センサー（カメラ、Arduino、東京デバイス製品）を抜いたり、別のポートに差し替えたりしても大丈夫です。システムが自動的に新しいポートを検出し、次の計測タイミングで復旧します。

### 管理用コマンド
*   **WiFi 確認:** `./test_wifi.sh`。
*   **ログ確認:** `./04_start_service.sh --log`。

---

## ⚠️ ハードウェアに関する注意: Arduino UNO R4
Pi 5 の制限により、Arduino へのプログラム書き込みは **PC または Mac** で行う必要があります。
1. PCの Arduino IDE で、本パッケージの `arduino/gravity_node/gravity_node.ino` を開きます。
2. ボードに **"Arduino UNO R4 Minima"** を選択して **Upload** します。
3. 書き込み後、Arduino を Pi に接続してください。