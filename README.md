# Sensor SFC v2 Installation & Operation Guide

Welcome to the unified Sensor SFC deployment system. We have simplified the process into a clear, numbered workflow.

---

## ⚡ Web Quick Start (Recommended — 2 Steps)

For a brand-new Raspberry Pi 5, this is the fastest path. No file transfers, no zip files. Just a MicroSD card and a one-line command.

### Step A — Image the MicroSD card (on your PC)

1. Install **Raspberry Pi Imager** from https://www.raspberrypi.com/software/
2. Insert your MicroSD card into your PC.
3. In Imager, click **CHOOSE DEVICE → "Raspberry Pi 5"**.
4. Click **CHOOSE OS → "Raspberry Pi OS (64-bit)"**.
5. Click **CHOOSE STORAGE** and select your MicroSD.
6. Click **NEXT → "EDIT SETTINGS"**, and fill in:
    * **Hostname:** something memorable, e.g. `sodat-s01`
    * **Username / Password:** anything you like — REMEMBER THESE
    * **Wi‑Fi:** your SSID and password
    * **Locale:** your timezone / keyboard
    * **Services tab:** turn ON **"Enable SSH"** (use password auth)
7. Click **SAVE → YES → YES** to write. This takes ~5 minutes.
8. Eject the card, insert it into the Pi, and power on. Wait ~2 minutes for first boot.

### Step B — Install Sodat (one line)

From your PC, SSH into the Pi (use the hostname and username you just set):

```bash
ssh <username>@sodat-s01.local
```

Then paste this single line and press Enter:

```bash
curl -fsSL https://raw.githubusercontent.com/hiroyuki-nobutomo/sodat_control/main/bootstrap.sh | sudo bash
```

The installer sets up everything (drivers, I2C, services, Python environment), then asks you two short questions on the same console:

1. **Device ID** — pick a code for this Pi (e.g. `S01`, `A01`). Press Enter on the other prompts to accept defaults.
2. **Run a sensor test now?** — say **Yes** to verify the hardware.

### Step C — Place the Google OAuth token (one-time, per device)

The system needs `secrets/token.json` to upload data to Google Drive / Sheets. Until this file exists the Pi will still collect data locally, but uploads will fail.

For now, copy the token from your PC (we'll replace this with a web-based flow soon):

```bash
# From your PC (where token.json lives):
scp token.json <username>@sodat-s01.local:~/sensor_sfc/secrets/

# Then on the Pi, restart the service to pick it up:
./04_start_service.sh --stop && ./04_start_service.sh
```

> 💡 **Even simpler (optional, advanced):** see `firstrun_append.sh.example` for a snippet you can paste into Pi Imager's auto-generated `firstrun.sh` to make the Pi install Sodat **completely on its own** the first time it boots — no SSH, no commands.

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

## ⚡ Web クイックスタート (推奨・2 ステップ)

新品の Raspberry Pi 5 に対する最速の手順です。**zip ファイルの転送は不要**。MicroSD カードと、SSH からの 1 行コマンドだけで完了します。

### ステップ A — MicroSD カードを焼く (PC 側)

1. PC に **Raspberry Pi Imager** をインストールします: https://www.raspberrypi.com/software/
2. MicroSD カードを PC に挿入します。
3. Imager を起動し、**「デバイスを選ぶ」 → "Raspberry Pi 5"** を選択。
4. **「OS を選ぶ」 → "Raspberry Pi OS (64‑bit)"** を選択。
5. **「ストレージを選ぶ」** で MicroSD を指定。
6. **「次へ」 → 「設定を編集する」** をクリックし、以下を入力:
    * **ホスト名:** わかりやすい名前 (例: `sodat-s01`)
    * **ユーザー名 / パスワード:** 任意 — **必ず覚えておいてください**
    * **Wi‑Fi:** SSID とパスワード
    * **ロケール:** タイムゾーン / キーボード
    * **「サービス」タブ:** **「SSH を有効化」を ON** (パスワード認証で OK)
7. **「保存」 → 「はい」 → 「はい」** で書き込み開始。約 5 分。
8. カードを取り出し、Pi に挿して電源 ON。初回起動の完了まで約 2 分待ちます。

### ステップ B — Sodat をインストール (1 行)

PC から SSH で Pi に接続します (ホスト名とユーザー名は手順 A で設定したもの):

```bash
ssh <ユーザー名>@sodat-s01.local
```

接続したら、以下の 1 行をそのままコピペして Enter:

```bash
curl -fsSL https://raw.githubusercontent.com/hiroyuki-nobutomo/sodat_control/main/bootstrap.sh | sudo bash
```

インストーラがドライバ・I2C・サービス・Python 環境などをすべて構築し、最後に **同じコンソール上で** 2 つだけ質問してきます:

1. **Device ID** — この Pi の機器名 (例: `S01`, `A01`) を選択。それ以外の項目は Enter で既定値でも OK。
2. **センサーテストを実行しますか？** — **Yes** でハードウェア動作確認まで自動実行。

### ステップ C — Google OAuth トークンを配置 (デバイスごとに 1 回)

Google Drive / Sheets へのアップロードには `secrets/token.json` が必要です。ファイルが無くてもデータはローカル DB に蓄積されますが、クラウドへのアップロードは失敗します。

当面は PC から token をコピーしてください (将来 Web からの取得フローに置き換えます):

```bash
# PC 側 (token.json が手元にある PC):
scp token.json <ユーザー名>@sodat-s01.local:~/sensor_sfc/secrets/

# 次に Pi 側でサービスを再起動して反映:
./04_start_service.sh --stop && ./04_start_service.sh
```

> 💡 **さらに簡単 (上級者向け・オプション):** `firstrun_append.sh.example` を参照してください。Pi Imager が自動生成する `firstrun.sh` に貼り付けるスニペットで、**初回起動時に Sodat が自動でインストールされる完全ゼロタッチ**になります (SSH 操作不要)。

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