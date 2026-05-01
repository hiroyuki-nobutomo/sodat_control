# Sensor SFC v2 Installation & Operation Guide

Welcome to the unified Sensor SFC deployment system. We have simplified the process into a clear, numbered workflow.

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
*   **Options:** You can set Device ID, Sensing Interval (seconds), Upload Interval (seconds), and Local Retention (days).
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
*   **設定項目:** Device ID、計測間隔、アップロード間隔、ローカルデータ保持期間。
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