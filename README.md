# 全台即時氣象測站觀測網 (Taiwan CWA Weather Station Dashboard)

AIoT 課程 Week 3 / L3-HW1 獨立專案：結合 **AirBox (EdiGreen)** 與 **台灣即時氣象地圖 (Taiwan Weather Map)** 優勢之全台即時氣象觀測儀表板。

---

## 專案亮點與參考範例融合

本專案深度分析老師於 Notion 提供的兩大指標性即時觀測範例，萃取核心 UI/UX 優勢並融合成高資訊密度且專業的監控儀表板：

### 1. 汲取自 AirBox 空氣盒子 (https://airbox.edimaxcloud.com/)
* **Map-First 全景視覺**：地圖鋪滿整個可視視窗（Full Viewport Canvas），突顯宏觀空間地理分佈。
* **高密度測站分佈 (High Density Spatial Visualization)**：呈現全台 362 個自動氣象測站，平原、山區（如玉山、阿里山、合歡山）、離島（澎湖、金門、馬祖、東沙）一目了然。
* **側邊浮動控制台 (Control Sidebar)**：提供測站即時搜尋、縣市篩選、氣溫區間過濾、標籤切換與底圖切換。

### 2. 汲取自 台灣即時氣象地圖 (https://taiwan-weather-map.vercel.app/)
* **氣象要素可讀性 (Meteorological Clarity)**：測站標記直接標示即時氣溫數值（如 `28°`, `7°`），無須逐一逐點點擊即可迅速獲取氣溫資訊。
* **直覺連續氣溫色階 (Continuous Temperature Scale)**：完全符合評分驗收標準：
  * `< 10°C`：深藍色（高山寒冷）
  * `20 - 25°C`：黃色系（舒適宜人）
  * `> 35°C`：深紅色（酷熱警戒）
* **頂部總覽指標看板 (Summary Metric Ticker)**：即時統計測站總數、最高溫（測站/縣市）、最低溫、全台均溫與最大風速。
* **豐富測站詳情面板 (Station Detail Card)**：點擊測站彈出包含測站代碼、縣市鄉鎮、海拔高度、天氣現象、氣溫、相對濕度、風向風速、瞬間陣風、降水量、氣壓與觀測時間等完整數據。

---

## 系統架構與安全設計

```
[ Central Weather Administration (CWA) ]
                |  (API Dataset: O-A0003-001)
                v
[ GitHub Actions Server-Side Cron Runner ]  <--- Secrets.CWA_API_KEY (安全隔離，絕不外流)
                |
                | (執行 scripts/fetch_and_build.py & pytest 驗證)
                v
[ Sanitized Static Artifact: docs/data/stations.json ]
                |
                v
[ GitHub Pages Static Hosting (docs/) ]
                |
                v
[ End-User Browser Client (Leaflet.js + Vanilla JS) ]
```

* **零金鑰外洩 (Zero-Secret Leakage)**：
  * 前端 JavaScript 與 HTML **絕對不包含**任何 CWA API Key。
  * 由伺服端（GitHub Actions 或本機 build script）攜帶金鑰請求 CWA API，解析清洗後僅輸出無敏感資訊的 `docs/data/stations.json`。
  * Git 歷史紀錄與遠端倉庫完全排除 `.env` 檔案。
* **健壯容錯機制 (Robust Fallback & Sanitization)**：
  * 針對 CWA 的 `-99`、`-999`、空字串或 null 等哨兵值（Sentinel Values）進行過濾轉換，避免前端圖表破圖或計算錯誤。
  * 內建 362 站真實備用資料集（`docs/data/stations_fixture.json`），即使無金鑰或離線環境，本機仍可完整預覽與測試。

---

## 目錄結構

```
week3-cwa-station-map/
├── .github/
│   └── workflows/
│       └── update-and-deploy.yml    # GitHub Actions 排程抓取與 Pages 自動發布
├── docs/                             # GitHub Pages 發布目錄
│   ├── index.html                    # 儀表板主頁面
│   ├── style.css                     # 深色高科技監控主題樣式
│   ├── app.js                        # 地圖互動、搜尋、篩選與面板控制邏輯
│   └── data/
│       ├── stations.json             # 前端讀取的標準化氣象站資料
│       └── stations_fixture.json     # 全台 362 站本機安全備用資料集
├── scripts/
│   ├── fetch_and_build.py            # 資料抓取、安全金鑰讀取與建立腳本
│   └── normalize.py                  # 資料清洗、座標校驗與氣溫色階核心模組
├── tests/
│   ├── test_color_scale.py           # 氣溫色階測試（符合 <10 藍, 20-25 黃, >35 深紅）
│   ├── test_normalize.py             # 哨兵值清理與資料正規化測試
│   └── test_schema.py                # 前端 JSON Schema 結構與座標驗證
├── .env.example                      # 安全金鑰範本
├── .gitignore                        # Git 忽略設定（排除 .env 與快取）
├── requirements.txt                  # 測試依賴 (pytest)
└── README.md                         # 專案完整說明文件
```

---

## 本機快速啟動指南

### 1. 執行測試
本專案使用 Python 標準庫進行資料處理，只需安裝 `pytest` 即可執行所有自動化驗證：
```bash
pip install -r requirements.txt
pytest -v
```

### 2. 產製/更新測站資料
* **無金鑰模式（使用內建 362 站真實備用集）**：
  ```bash
  python scripts/fetch_and_build.py
  ```
* **即時連線模式（若您有 CWA 金鑰）**：
  複製 `.env.example` 為 `.env` 並填入您的 CWA API Key：
  ```bash
  copy .env.example .env
  # 在 .env 中填寫 CWA_API_KEY=您的金鑰
  python scripts/fetch_and_build.py
  ```

### 3. 開啟本機網頁預覽
啟動靜態伺服器並以瀏覽器開啟：
```bash
python -m http.server 8000 -d docs
```
在瀏覽器網址列輸入：`http://localhost:8000`

---

## 部署至 GitHub Pages 指南

1. **建立 GitHub Repository** 並將本專案代碼推送到 `main` 分支。
2. **設定 CWA API 金鑰**：
   * 前往 GitHub Repository 的 **Settings** -> **Secrets and variables** -> **Actions**。
   * 點選 **New repository secret**。
   * Name 輸入：`CWA_API_KEY`
   * Value 輸入：您的中央氣象署授權碼。
3. **開啟 GitHub Pages**：
   * 前往 **Settings** -> **Pages**。
   * 在 **Build and deployment** 下方的 **Source** 選擇 **GitHub Actions**。
4. **自動更新排程**：
   * 內建的 `.github/workflows/update-and-deploy.yml` 每 30 分鐘自動執行一次，抓取最新 O-A0003-001 資料，產製並部署最新靜態站點。亦可於 Actions 頁籤隨時手動點擊「Run workflow」即時更新。
