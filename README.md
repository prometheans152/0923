# AIoT-DA L3 HW1｜台灣即時氣象測站 GIS Dashboard 與 7 日天氣預報

本專案為 AIoT-DA 第三課作業，嚴格依照課堂規劃的 **Five Gates** 驗證流程，建構一套從中央氣象署真實 Open Data 取得、SQLite 本地持久化、GIS 互動視覺化與 7 日天氣預報趨勢、GitHub 版本管理與自動化，到 Vercel 雲端部署的完整資料應用系統。

- **GitHub Repository：** https://github.com/prometheans152/0923
- **Vercel Production：** https://0923-site.vercel.app/
- **GitHub Pages Fallback：** https://prometheans152.github.io/0923/
- **CWA Datasets：**
  - 即時測站：`O-A0003-001`（氣象觀測站－10分鐘綜觀氣象資料，全台 362 站即時 GIS）
  - 7 日預報：`F-C0032-003`（一般天氣預報－七天天氣預報，6 區 7 日氣溫預報，42 筆）
  - 相容備援：`F-A0010-001`（一週農業氣象預報，課程講義舊端點已失效 404，本系統保留解析相容與離線備援）

> **Five Gates 核心路線：**  
> `CWA API (Gate 1) → SQLite (Gate 2) → GIS Dashboard (Gate 3) → GitHub (Gate 4) → Vercel (Gate 5)`

---

## 成果畫面

![台灣即時氣象測站 GIS Dashboard](docs/report-dashboard.png)

---

# 一、作業目的

本作業的核心目的，是透過 AI Agent pair programming 建立一個具備端到端資料流的完整系統，並以「Five Gates（五道關卡）」落實分步驗證，確保每一階段均有可重現、可檢驗的具體證據（Evidence before claims），避免黑箱產生無法運行的程式碼。

具體達成目標如下：
1. **Gate 1（真實資料取得）：** 透過中央氣象署 Open Data API 真實取得 `O-A0003-001` 全台氣象測站 10 分鐘觀測資料，完成資料清洗、無效值（`-99` 等）過濾與統計指標計算，產出 `metadata.build_mode = "live_cwa_api"` 的真實觀測資料集。
2. **Gate 2（資料庫持久化）：** 設計符合前端展示與統計需求的關聯綱要，將觀測資料寫入專案根目錄 SQLite 資料庫（`data.db`），包含獨立 `metadata`、`observations` 與 `snapshots` 表，支援原子化快照替換與去重更新機制，並以 SQL Query 實證資料可被正確檢索。
3. **Gate 3（GIS 前端呈現）：** 以 Leaflet 建立支援 MapTiler 深色/淺色底圖切換的 GIS 前端，首選路徑為呼叫後端 Flask `/api/weather`（背後由 SQLite 提供資料，回傳 `storage = "sqlite"`），在純靜態環境（如 GitHub Pages）則平滑降級為靜態 JSON。
4. **Gate 4（版本管理與 CI/CD）：** 將完整原始碼、測試、設定納入 GitHub 管理，編寫 `.github/workflows/update-and-deploy.yml` 自動化工作流，納入全套 30 項單元與整合測試及 JavaScript 語法檢查。
5. **Gate 5（雲端部署）：** 將 Flask Web App 部署至 Vercel Serverless Function，配置 `vercel.json` 打包 `data.db` 快照，誠實揭露 Serverless 唯讀 SQLite 限制與未來外部持久化資料庫演進方向。
6. **7 日天氣預報功能（課堂教師指定需求）：**
   - **分區與期程：** 整合中央氣象署 7 日氣溫預報，完整涵蓋課程指定之六大預報分區（北部地區、中部地區、南部地區、東北部地區、東部地區、東南部地區），各區包含 7 日之最低溫（MinT）與最高溫（MaxT），共 42 筆預報紀錄。
   - **資料來源與真實性（Live vs Fallback）：**
     - 課程講義教材原本標註使用 `F-A0010-001`（一週農業氣象預報），但經實際驗證該 API 端點目前回傳 HTTP 404 不存在。
     - 經查閱中央氣象署官方 Open Data 規範，目前現行有效之 7 日分區預報正式 Dataset 為 `F-C0032-003`（一般天氣預報－七天天氣預報）。
     - 本專案 Live 資料管線採用官方現行 `F-C0032-003` 真實抓取即時預報，產出之最新驗證資料跨度為 **2026-09-25 至 2026-10-01**，Metadata 誠實標示 `source_dataset = "F-C0032-003"`、`build_mode = "live_cwa_api"`。
     - 同時保留對舊版 `F-A0010-001` JSON 結構之解析相容層與離線 Fixture（`forecast_fixture.json`），僅於網路斷線時作為容錯降級，且明確標註 `fallback_fixture`，絕不偽裝為即時資料。
   - **資料庫持久化：** 在 `data.db` 擴充 `TemperatureForecasts` 資料表（欄位包含 `id`, `regionName`, `dataDate`, `mint`, `maxt` 及 `UNIQUE(regionName, dataDate)`）與 `forecast_metadata`，支援去重與批次原子替換，並確保在觀測站資料更新時互不覆蓋、安全共存。
   - **後端 API：** 提供 `/api/forecast` 端點（支援 `?region=...` 參數過濾），直接由 SQLite 讀取最新預報資料。
   - **前端視覺化 UI：** 儀表板新增「7 日天氣預報」控制面板，包含六大分區下拉選單、7 日日期選單、所選日期氣溫摘要卡、原生 SVG 雙折線圖（最低溫/最高溫趨勢與垂直選取指示），以及完整 7 日數據表格（支援點擊切換日期高亮聯動）。
   - **GIS 完整性保護：** 原有全台 362 站即時氣溫監控 GIS 地圖與詳細資訊面板維持完整運作，完全無功能降級。

---

# 二、系統架構

```mermaid
flowchart TD
    A["中央氣象署 CWA API<br/>O-A0003-001 (即時測站)<br/>F-C0032-003 (7日預報)"] -->|安全 Fetch & Normalize| B["scripts/fetch_and_build.py"]
    B -->|原子化寫入 / 去重| C[("SQLite data.db<br/>observations + metadata + snapshots<br/>TemperatureForecasts + forecast_metadata")]
    B -->|靜態匯出| D["docs/data/<br/>stations.json & forecast.json"]
    C -->|唯讀連線| E["Flask Server (server.py)<br/>/api/weather & /api/forecast & /api/db-check"]
    E -->|GIS 視覺化 + 7日預報面板| F["前端 Dashboard<br/>(Leaflet GIS + 原生 SVG 趨勢圖)"]
    D -.->|靜態降級 Fallback| F
    E -->|程式碼託管 & CI (30 Tests)| G["GitHub Repo + Actions"]
    E -->|Serverless 打包| H["Vercel Production"]
```

### 關鍵技術堆疊

| 層級 | 使用技術 | 角色與職責 |
|---|---|---|
| **公開資料源** | CWA O-A0003-001 & F-C0032-003 | 即時全台測站 10 分鐘觀測資料 + 6 區 7 日氣溫預報（42 列） |
| **相容備援源** | CWA F-A0010-001 (Fixture) | 課程舊版規格解析相容與離線降級備援 |
| **資料管線** | Python 3.12 (`urllib`, `json`) | 安全憑證存取、雙資料集清理、色階判定、統計分析 |
| **持久層** | SQLite 3 (`data.db`) | 根目錄關聯式資料庫，原子化快照、主鍵去重、`TemperatureForecasts` 預報表 |
| **後端 API** | Flask 3.1 | 提供 `/api/weather`、`/api/forecast` 與 `/api/db-check`，唯讀連線 SQLite |
| **GIS 前端** | Leaflet 1.9 + MapTiler SDK | 密集測站標記、氣溫數值 Badge、Popup 詳情、縣市定位 |
| **預報視覺化** | 原生 SVG 雙折線圖 + 互動表格 | 7 日 MinT/MaxT 氣溫趨勢圖、分區選單、日期選單、高亮連動 |
| **底圖切換** | MapTiler Streets v4 / Dark | 依使用者偏好切換深色與淺色向量光柵底圖 |
| **版本管理** | Git + GitHub | 程式碼歷程管理、CI 自動化測試工作流 |
| **雲端部署** | Vercel (`@vercel/python`) | Python Serverless Function，打包唯讀 SQLite 快照 |
| **自動化測試** | pytest (30 tests) + node --check | 覆蓋 Schema、色階、SQLite 綱要、重複寫入、7日預報資料表、Flask API |

---

# 三、開發步驟與 Five Gates 驗證

## Gate 1｜中央氣象署即時觀測資料取得 (CWA Acquisition)

### 工作內容
1. 程式透過環境變數 `CWA_API_KEY` 或本機受保護之 `.env` / `api_key.txt` 檔案載入憑證（絕不在日誌、命令列或終端機中印出金鑰內容）。
2. 發起 HTTP 請求呼叫 `https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0003-001` 取得即時 10 分鐘綜觀氣象資料。
3. 由 `scripts/normalize.py` 處理 CWA 特殊哨兵值（如 `-99`, `-999`, `-9999` 代表儀器故障或缺測，一律正規化為 `None`），解析氣溫、相對濕度、測站氣壓、風速、風向、陣風、降水量與紫外線指數。
4. 計算全台極值指標（最高溫測站、最低溫測站、平均氣溫、最大風速測站）。
5. 寫入標準結構至 `docs/data/stations.json`，並設定 `build_mode = "live_cwa_api"`（離線 fixture 僅作為容錯備援，不作為正式達成指標）。

### 驗證方式
執行建置腳本 `python scripts/fetch_and_build.py`，檢查輸出之建置模式、觀測時間戳、站點統計數據，並驗證產出之 JSON 格式。

### 實際結果
- **建置模式（build_mode）：** `live_cwa_api`
- **主要觀測時間戳：** `2026-09-24T22:50:00+08:00`
- **測站總數：** 362 站（有效氣溫測站 350 站）
- **氣溫極值與均溫：** 最低溫 4.8°C（玉山，南投縣）、最高溫 29.3°C（國一N361K，高雄市）、全台平均 24.2°C
- **最大風速：** 8.6 m/s（恆春工作站，屏東縣）

### 證據（執行輸出）
```text
[INFO] CWA API key detected in the secure environment.
[INFO] Fetching live data from CWA API (O-A0003-001)...
[SUCCESS] Built station JSON -> docs/data/stations.json
[SUCCESS] Persisted snapshot to SQLite -> data.db
          - Mode: live_cwa_api
          - Observation time: 2026-09-24T22:50:00+08:00
          - Snapshot stations: 362 (Valid temp: 350)
          - Temp range: 4.8°C (玉山) ~ 29.3°C (國一N361K)
          - Avg temp: 24.2°C
          - SQLite upserted rows: 362
          - SQLite total observation rows: 362
          - SQLite latest observation: 2026-09-24T22:50:00+08:00
```
- **Gate 1 結論：PASS**

---

## Gate 2｜SQLite 資料庫持久化與 SQL 查詢驗證 (Persistence)

### 工作內容
1. 於專案根目錄維護關聯式資料庫 `data.db`（由 `scripts/database.py` 統一管理）。
2. 資料庫包含三張核心資料表：
   - **`metadata` 表：** 記錄來源名稱、產生時間、觀測時間、總測站數、有效溫度測站數、建置模式與統計資料 JSON。
   - **`observations` 表：** 記錄每個測站的即時數值，以 `station_id` 為 PRIMARY KEY，確保不會產生重複測站列。
   - **`snapshots` 表：** 以 `(obs_time, source_mode)` 為複合主鍵，保存歷次快照摘要。
3. **去重與更新機制（Deduplication & Update）：**
   - 在單次快照重建時，以 SQLite 交易機制原子化寫入，杜絕中途異常造成的殘缺資料。
   - `observations` 表以 `station_id` 為主鍵，採用 `INSERT OR REPLACE` 語意；若輸入批次出現重複測站或執行增量更新，會原地更新該測站觀測數值，保持唯一性。
   - 單元測試 `test_upsert_duplicate_station_behavior` 驗證同測站重複寫入時之更新行為，確保不會產生重複資料列或違反約束。
4. 提供 `scripts/query_db.py` 查詢驗證命令，可安全抽樣指定縣市之資料庫紀錄。

### 資料表 Schema 與去重機制
```sql
CREATE TABLE IF NOT EXISTS metadata (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    source TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    observation_time TEXT NOT NULL,
    total_stations INTEGER NOT NULL,
    valid_temp_stations INTEGER NOT NULL,
    build_mode TEXT NOT NULL,
    stats_json TEXT,
    counties_json TEXT,
    color_scale_json TEXT
);

CREATE TABLE IF NOT EXISTS observations (
    station_id TEXT PRIMARY KEY,
    station_name TEXT NOT NULL,
    county TEXT,
    town TEXT,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    altitude REAL,
    obs_time TEXT NOT NULL,
    weather TEXT,
    temperature REAL,
    humidity REAL,
    pressure REAL,
    wind_speed REAL,
    wind_direction REAL,
    gust_speed REAL,
    precipitation REAL,
    uv_index REAL,
    color TEXT,
    category TEXT,
    has_temp INTEGER NOT NULL DEFAULT 0,
    source_mode TEXT NOT NULL,
    ingested_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_observations_county ON observations(county);
CREATE INDEX IF NOT EXISTS idx_observations_obs_time ON observations(obs_time);
CREATE INDEX IF NOT EXISTS idx_observations_temperature ON observations(temperature);

CREATE TABLE IF NOT EXISTS snapshots (
    obs_time TEXT NOT NULL,
    source_mode TEXT NOT NULL,
    generated_at TEXT,
    station_count INTEGER NOT NULL,
    metadata_json TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    PRIMARY KEY (obs_time, source_mode)
);

-- 7 日氣溫預報資料表（課堂教師指定需求）
CREATE TABLE IF NOT EXISTS TemperatureForecasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    regionName TEXT NOT NULL,
    dataDate TEXT NOT NULL,
    mint REAL,
    maxt REAL,
    UNIQUE(regionName, dataDate)
);

CREATE TABLE IF NOT EXISTS forecast_metadata (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    source TEXT NOT NULL,
    source_dataset TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    total_regions INTEGER NOT NULL,
    total_records INTEGER NOT NULL,
    build_mode TEXT NOT NULL,
    storage TEXT NOT NULL,
    regions_json TEXT NOT NULL
);
```

### 驗證方式
1. 執行 `python scripts/query_db.py --county 新竹縣 --limit 3` 檢驗即時測站 SQL 查詢結果。
2. 執行 SQL 查詢 `SELECT COUNT(*) FROM TemperatureForecasts` 及抽樣 6 區 7 日預報資料。
3. 執行 `pytest tests/test_database.py tests/test_forecast.py` 驗證資料表綱要、列數一致性、原子性替換以及預報去重 upsert 行為。

### 實際結果
- **SQLite 即時測站筆數（COUNT）：** 362（與 `stations.json` 的 362 站完全一致）
- **SQLite 7 日預報筆數（COUNT）：** 42（6 區 × 7 天，精準符合規格）
- **預報日期區間（最新驗證）：** `2026-09-25` 至 `2026-10-01`
- **建置模式：** `live_cwa_api`（真實 CWA F-C0032-003 API）
- **去重更新測試：** `test_upsert_duplicate_station_behavior` 與 `test_forecast_db_helpers` 全數通過，重複鍵值原地更新且約束生效。

### 證據（SQL 查詢輸出）
```text
=== SQLite Verification (data.db: observations) ===
Total stations (COUNT): 362
Observation time:       2026-09-24T22:50:00+08:00
Build mode:             live_cwa_api
Storage backend:        sqlite

Sample query (新竹縣, 3 rows):
  - 五峰站 (72D080) [新竹縣 五峰鄉]: Temp: 19.2°C, RH: 95.0%, Wind: 0.5 m/s, Weather: 晴
  - 國一N077K (CAD020) [新竹縣 湖口鄉]: Temp: 23.5°C, RH: 84.0%, Wind: 1.0 m/s, Weather: 晴
  - 國一S082K (CAD030) [新竹縣 湖口鄉]: Temp: 24.2°C, RH: 83.0%, Wind: 0.5 m/s, Weather: 晴

=== SQLite Verification (data.db: TemperatureForecasts) ===
Total forecast rows:    42
Total regions:          6 (北部地區、中部地區、南部地區、東北部地區、東部地區、東南部地區)
Forecast date span:     2026-09-25 .. 2026-10-01 (7 days)
Source dataset:         F-C0032-003
Build mode:             live_cwa_api

Sample forecast query (北部地區, 2026-09-25):
  - 北部地區 | 2026-09-25: MinT: 22.0°C, MaxT: 34.0°C
```
- **Gate 2 結論：PASS**

---

## Gate 3｜GIS 地圖前端、7 日天氣預報面板與 Flask SQLite API (GIS Frontend & Forecast)

### 工作內容
1. 後端 `server.py` 實作核心路由：
   - `/api/weather`：使用唯讀連線模式開啟 `data.db`，由 `payload_from_db()` 重構標準前端契約，標記 `metadata.storage = "sqlite"` 與 `metadata.build_mode = "live_cwa_api"`。
   - `/api/forecast`：使用唯讀連線模式開啟 `data.db`，支援選填 `?region=...` 參數過濾，由 `forecast_payload_from_db()` 從 `TemperatureForecasts` 表讀取六區 7 日氣溫預報，標記 `storage = "sqlite"` 與 `build_mode = "live_cwa_api"`。
   - `/api/db-check`：執行真實 SQL `SELECT COUNT(*)` 與條件抽樣查詢，回傳 `database = "sqlite"` 與即時樣本。
   - `/` 與靜態路由：回傳 `docs/index.html`、`docs/app.js`、`docs/data/stations.json`、`docs/data/forecast.json`。
2. 前端 `docs/app.js` 多層級降級策略：
   - **Vercel 環境首選：** 優先請求 `/api/weather` 與 `/api/forecast`，直接展示由後端 Flask 讀取 SQLite 的最新即時資料與 7 日預報。
   - **GitHub Pages 靜態備援：** 若 API 回傳失敗（靜態環境），自動捕捉異常並優雅降級讀取 `./data/stations.json` 與 `./data/forecast.json`。
   - **離線備援（Fixture Fallback）：** 預報模組若完全無網路連線，降級使用相容舊格式之 `./data/forecast_fixture.json`，並清楚標示 `fallback_fixture` 狀態。
3. 前端 UI 與 7 日預報視覺化體驗：
   - 台灣全島初始置中視角（Lat 23.75, Lon 120.95, Zoom 8）。
   - 保留 MapTiler Streets v4（淺色）與 Streets v4 Dark（深色）底圖快速切換。
   - 測站氣溫數值 Badge、彈出視窗（Popup）詳細氣象資訊、縣市快速定位篩選、氣溫分級篩選與測站名稱即時搜尋。
   - **7 日天氣預報面板（#forecast-panel）：**
     - 六大預報分區下拉切換（北部、中部、南部、東北部、東部、東南部）。
     - 7 日日期下拉選單，同步連動「所選日期摘要卡」顯示該分區當日最高溫與最低溫。
     - 原生輕量化 SVG 雙折線圖（MinT 藍色 `#60a5fa`、MaxT 紅色 `#f87171`），含垂直選取引導線、數值標註與可點擊欄位。
     - 7 日預報數據表格，顯示完整 7 天日期、MinT、MaxT，點擊表格列即時連動選取日期與折線圖高亮。
     - 頂部導航列包含「📅 7 日天氣預報」展開/收合切換按鈕，支援響應式行動裝置排版。

### 7 段氣溫色階規範

| 溫度範圍 | 代表色 Hex | 類別標籤 | 設計語意 |
|---|---|---|---|
| `< 10°C` | `#2563EB` | 嚴寒 | 藍色（高山/冷氣團） |
| `10 – 15°C` | `#06B6D4` | 寒冷 | 青色 |
| `15 – 20°C` | `#10B981` | 涼爽 | 綠色 |
| `20 – 25°C` | `#EAB308` | 舒適 | 黃色（怡人均溫） |
| `25 – 30°C` | `#F97316` | 溫暖 | 橘色 |
| `30 – 35°C` | `#EF4444` | 炎熱 | 紅色 |
| `> 35°C` | `#991B1B` | 酷熱 | 深紅色（極端高溫警戒） |
| 無資料 / 缺測 | `#94A3B8` | 無資料 | 灰色 |

### 驗證方式
1. 使用 Flask test client 針對 `/`, `/app.js`, `/data/stations.json`, `/data/forecast.json`, `/api/weather`, `/api/forecast`, `/api/db-check` 進行請求測試。
2. 執行 `node --check docs/app.js` 檢查前端程式碼語法。

### 實際結果
- 所有路由回傳 HTTP 200。
- `/api/weather` 成功由 SQLite 提供 362 站資料，包含 `storage: "sqlite"` 與 `build_mode: "live_cwa_api"`。
- `/api/forecast` 成功由 SQLite 提供 6 區 42 筆 7 日預報，包含 `storage: "sqlite"` 與 `source_dataset: "F-C0032-003"`。
- `/api/forecast?region=北部地區` 成功依分區過濾，回傳 7 筆預報紀錄。
- `/api/db-check` 成功執行 SQL 查詢，回傳 `row_count: 362` 與新竹縣 5 筆樣本文檔。
- 前端 JavaScript 語法檢查通過，無任何語法錯誤。

### 證據（本機路由檢驗輸出）
```text
Route /                   -> status 200, content-type: text/html; charset=utf-8
Route /app.js             -> status 200, content-type: text/javascript; charset=utf-8
Route /data/stations.json -> status 200, content-type: application/json
Route /data/forecast.json -> status 200, content-type: application/json
Route /api/weather        -> status 200, content-type: application/json
  storage: sqlite
  build_mode: live_cwa_api
  total_stations: 362
  obs_time: 2026-09-24T22:50:00+08:00
Route /api/forecast       -> status 200, content-type: application/json
  storage: sqlite
  build_mode: live_cwa_api
  source_dataset: F-C0032-003
  total_records: 42
  date_span: 2026-09-25 .. 2026-10-01
Route /api/forecast?region=北部地區 -> status 200 (7 rows filtered)
Route /api/db-check       -> status 200, content-type: application/json
  database: sqlite
  row_count: 362
node --check docs/app.js  -> 結束碼 0 (PASS)
```
- **Gate 3 結論：PASS**

---

## Gate 4｜GitHub 版本管理與 CI/CD 工作流 (GitHub Actions)

### 工作內容
1. 程式碼與版本管理：完整程式碼、測試、靜態資源與設定檔均由 Git 進行追蹤。敏感檔案（如 `.env`, `api_key.txt`）由 `.gitignore` 明確排除，絕不上傳機敏資訊。
2. 撰寫自動化工作流 `.github/workflows/update-and-deploy.yml`：
   - 定時排程（每 30 分鐘執行一次）與手動觸發（`workflow_dispatch`）。
   - 工作流設定為預期讀取 Repository Secret `secrets.CWA_API_KEY`（若遠端 Repository Secret 有配置）；誠實說明：我們未獨立驗證遠端 GitHub Repository Secret 之設定狀態。若未配置該密鑰，建置腳本具備備援容錯機制，不會導致建置崩潰。
   - 自動執行 `fetch_and_build.py` 同步重建 `stations.json`、`forecast.json` 與 `data.db`（同時包含 362 站即時觀測與 42 筆 7 日預報）。
   - 執行品質門檻驗證：`pytest -v`（全套 30 個測試）與 `node --check docs/app.js`。
   - 自動上傳 `docs/` 目錄並發布至 GitHub Pages。

### 驗證方式
1. 本機執行完整測試套件 `pytest -v` 確保所有 30 項測試全部通過。
2. 檢查 `.gitignore` 確保 `.env` 與暫存檔案未被加入 staging。
3. 檢查 Git 提交歷程與遠端關聯。

### 實際結果
- 單元與整合測試共 30 項全部通過（包含氣溫色階、Schema 結構、SQLite 綱要、重複測站處理、列數一致性、Flask API，以及新增之 7 日預報資料表、F-C0032-003 解析、F-A0010-001 相容、資料庫整合與日期間隔驗證測試）。
- `.env` 與 `api_key.txt` 確實被忽略且未追蹤。

### 證據（測試輸出）
```text
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\prometheans\Desktop\AIOT\week3-cwa-station-map
collected 30 items

tests/test_color_scale.py::test_temperature_below_10_is_blue PASSED      [  3%]
tests/test_color_scale.py::test_temperature_20_to_25_is_yellowish PASSED [  6%]
tests/test_color_scale.py::test_temperature_above_35_is_deep_red PASSED  [ 10%]
tests/test_color_scale.py::test_temperature_intermediate_bins PASSED     [ 13%]
tests/test_color_scale.py::test_missing_temperature PASSED               [ 16%]
tests/test_database.py::test_schema_initializes PASSED                   [ 20%]
tests/test_database.py::test_metadata_table_fields PASSED                [ 23%]
tests/test_database.py::test_atomic_snapshot_replacement PASSED          [ 26%]
tests/test_database.py::test_upsert_duplicate_station_behavior PASSED    [ 30%]
tests/test_database.py::test_row_count_matches_json PASSED               [ 33%]
tests/test_database.py::test_query_sample_works PASSED                   [ 36%]
tests/test_database.py::test_latest_payload_reconstruction PASSED        [ 40%]
tests/test_database.py::test_flask_api_weather_uses_sqlite PASSED        [ 43%]
tests/test_database.py::test_flask_routes_all_200 PASSED                 [ 46%]
tests/test_forecast.py::test_temperature_forecasts_table_schema PASSED   [ 50%]
tests/test_forecast.py::test_normalize_forecast_dataset_legacy_fa0010_001 PASSED [ 53%]
tests/test_forecast.py::test_normalize_forecast_dataset_fc0032_003 PASSED [ 56%]
tests/test_forecast.py::test_forecast_db_helpers PASSED                  [ 60%]
tests/test_forecast.py::test_forecast_live_integration_and_current_dates PASSED [ 63%]
tests/test_forecast.py::test_flask_api_forecast_routes PASSED            [ 66%]
tests/test_forecast.py::test_observation_data_preserved_during_forecast_generation PASSED [ 70%]
tests/test_forecast.py::test_honest_fallback_reporting PASSED            [ 73%]
tests/test_normalize.py::test_clean_number_sentinels PASSED              [ 76%]
tests/test_normalize.py::test_clean_number_valid PASSED                  [ 80%]
tests/test_normalize.py::test_clean_number_bounds PASSED                 [ 83%]
tests/test_normalize.py::test_extract_coordinates PASSED                 [ 86%]
tests/test_normalize.py::test_normalize_station_valid PASSED             [ 90%]
tests/test_normalize.py::test_normalize_station_missing_coords_dropped PASSED [ 93%]
tests/test_normalize.py::test_normalize_dataset_summary_stats PASSED     [ 96%]
tests/test_schema.py::test_generated_stations_json_schema PASSED         [100%]

============================= 30 passed in 0.77s ==============================
```
- **Gate 4 結論：PASS**

---

## Gate 5｜Vercel 雲端部署 (Vercel Deployment)

### 工作內容
1. 專案根目錄保留 `vercel.json`，指定使用 `@vercel/python` 建置 Serverless Function：
   ```json
   {
     "version": 2,
     "builds": [
       {
         "src": "api/index.py",
         "use": "@vercel/python",
         "config": {
           "includeFiles": [
             "data.db",
             "docs/**"
           ]
         }
       }
     ],
     "routes": [
       {
         "src": "/api/weather",
         "dest": "/api/index.py"
       },
       {
         "src": "/api/db-check",
         "dest": "/api/index.py"
       },
       {
         "src": "/(.*)",
         "dest": "/api/index.py"
       }
     ]
   }
   ```
2. **`includeFiles` 打包 `data.db`：** 確保 Vercel 建置映像檔時，根目錄的 SQLite 資料庫檔案隨 Function 一同發布。
3. **Serverless SQLite 限制與真實架構說明：**
   - Vercel Serverless Function 為無狀態（Stateless）容器，其執行環境具備唯讀或暫時特性。
   - 本系統遵循設計規範，將隨部署發布的 `data.db` 作為**唯讀快照資料庫（Bundled Read-Only Snapshot）**。後端 Flask 採用唯讀模式（`mode=ro`）直接連線查詢，不進行不可靠的執行期持久化寫入。
   - 若未來需要多實例共享的跨請求歷史觀測持久寫入，應串接外部雲端資料庫（如 PostgreSQL / Supabase / Neon）。
4. **線上實測驗證：** 推送至 `main` 後，對正式部署網址 `https://0923-site.vercel.app/` 進行 HTTP 狀態碼與 JSON 回傳值驗證。

### 驗證方式
對生產環境 URL 發起 HTTP 請求，驗證 `/`, `/app.js`, `/api/weather`, `/api/db-check` 以及 GitHub Pages 站點連線。

### 實際結果
- 線上生產環境所有端點均回傳 HTTP 200。
- 線上 `/api/weather` 確認 `storage = "sqlite"`，`build_mode = "live_cwa_api"`，測站筆數一致。
- 線上 `/api/db-check` 成功執行真實 SQL 查詢，回傳 `database = "sqlite"`，`row_count = 362`。

### 證據（線上端點驗證結果）
| 端點 | HTTP 狀態 | 驗證指標 | 判定 |
|---|:---:|---|:---:|
| `https://0923-site.vercel.app/` | 200 | 首頁儀表板 HTML 正常載入 | **PASS** |
| `https://0923-site.vercel.app/app.js` | 200 | 前端邏輯腳本載入正常 | **PASS** |
| `https://0923-site.vercel.app/data/stations.json` | 200 | 靜態 JSON 降級檔正常 | **PASS** |
| `https://0923-site.vercel.app/api/weather` | 200 | `storage: sqlite`、`build_mode: live_cwa_api`、總站數 362 | **PASS** |
| `https://0923-site.vercel.app/api/db-check?county=新竹縣&limit=3` | 200 | `database: sqlite`、`row_count: 362`、新竹縣 SQL 抽樣正常 | **PASS** |
| `https://prometheans152.github.io/0923/` | 200 | GitHub Pages 備援站台正常 | **PASS** |
| `https://prometheans152.github.io/0923/data/stations.json` | 200 | 靜態 JSON 降級備援正常 | **PASS** |

```text
=== VERCEL PRODUCTION VERIFICATION ===
  GET /                      -> HTTP 200
  GET /app.js                -> HTTP 200
  GET /data/stations.json    -> HTTP 200
  GET /api/weather           -> HTTP 200
  GET /api/db-check          -> HTTP 200

  /api/weather contract:
    - storage:          sqlite
    - build_mode:       live_cwa_api
    - observation_time: 2026-09-24T22:50:00+08:00
    - stations count:   362

  /api/db-check proof:
    - database:         sqlite
    - row_count:        362
    - latest_obs:       2026-09-24T22:50:00+08:00
    - sample rows:
      * 五峰站 (72D080) [新竹縣 五峰鄉]: Temp 19.2°C, RH 95.0%, Wind 0.5 m/s, Weather: 晴
      * 國一N077K (CAD020) [新竹縣 湖口鄉]: Temp 23.5°C, RH 84.0%, Wind 1.0 m/s, Weather: 晴
      * 國一S082K (CAD030) [新竹縣 湖口鄉]: Temp 24.2°C, RH 83.0%, Wind 0.5 m/s, Weather: 晴

=== GITHUB PAGES FALLBACK VERIFICATION ===
  GET /                      -> HTTP 200
  GET /data/stations.json    -> HTTP 200
```

- **Gate 5 結論：PASS**

---

# 四、本機全流程驗證報告

在提交程式碼前，已於本地環境依序執行完整驗證清單：

| 驗證項目 | 驗證命令 / 方法 | 預期標準 | 實際結果 | 狀態 |
|---|---|---|---|:---:|
| **Gate 1 即時 CWA 資料取得** | 安全載入 API Key 執行 `fetch_and_build.py` | 成功取得 O-A0003-001，產出真實資料 | 取得 362 站，觀測時間 22:50，模式 `live_cwa_api` | **PASS** |
| **7 日預報即時 CWA 資料取得** | 安全載入 API Key 執行 `fetch_and_build.py` | 成功取得 F-C0032-003，產出 6 區 7 日資料 | 取得 42 筆，跨度 2026-09-25..10-01，模式 `live_cwa_api` | **PASS** |
| **Gate 2 SQLite 測站持久化** | `row_count('data.db')` | 筆數大於 0 | 筆數 = 362 | **PASS** |
| **Gate 2 SQLite 預報持久化** | `forecast_row_count('data.db')` | 筆數 = 42 (6 區 × 7 天) | 筆數 = 42 | **PASS** |
| **JSON 與 SQLite 筆數一致性** | 比較 `stations.json` 與 `data.db` | 筆數完全一致 | JSON 362 站 == DB 362 筆 | **PASS** |
| **預報 JSON 與 SQLite 一致性** | 比較 `forecast.json` 與 `data.db` | 筆數完全一致 | JSON 42 筆 == DB 42 筆 | **PASS** |
| **SQLite 條件查詢驗證** | `python scripts/query_db.py --county 新竹縣` | 能檢索出新竹縣真實測站與天氣數值 | 檢索出五峰站 (19.2°C)、國一N077K (23.5°C)、國一S082K (24.2°C) | **PASS** |
| **SQLite 重複測站寫入更新** | `test_upsert_duplicate_station_behavior` | 重複測站原地更新，不產生重複列 | 測試通過，筆數維持 1，數值正確更新 | **PASS** |
| **JavaScript 語法檢查** | `node --check docs/app.js` | 無語法或編譯錯誤 | 結束碼 0，無任何警告或錯誤 | **PASS** |
| **單元與整合測試套件** | `pytest -v` | 全部通過（30/30） | 30 passed in 0.77s | **PASS** |
| **Flask GET `/`** | Flask test client 請求首頁 | HTTP 200 | HTTP 200 | **PASS** |
| **Flask GET `/app.js`** | Flask test client 請求腳本 | HTTP 200 | HTTP 200 | **PASS** |
| **Flask GET `/data/stations.json`** | Flask test client 請求降級 JSON | HTTP 200 | HTTP 200 | **PASS** |
| **Flask GET `/data/forecast.json`** | Flask test client 請求預報降級 JSON | HTTP 200 | HTTP 200 | **PASS** |
| **Flask GET `/api/weather`** | Flask test client 請求 API | HTTP 200，資料由 SQLite 提供 | HTTP 200，`storage: "sqlite"`，站數 362 | **PASS** |
| **Flask GET `/api/forecast`** | Flask test client 請求預報 API | HTTP 200，資料由 SQLite 提供 | HTTP 200，`storage: "sqlite"`，筆數 42 | **PASS** |
| **Flask GET `/api/forecast?region=北部地區`** | Flask test client 請求分區過濾 | HTTP 200，過濾 7 筆 | HTTP 200，筆數 7 | **PASS** |
| **Flask GET `/api/db-check`** | Flask test client 請求驗證端點 | HTTP 200，包含資料庫摘要 | HTTP 200，`database: "sqlite"`，筆數 362 | **PASS** |

---

# 五、討論與心得

## 1. Five Gates 管理 AI Coding 的實踐價值
在過往直接透過 Prompt 要求 LLM「寫一個氣象地圖網站」時，模型往往會傾向跳過中間環節，直接產出一個含有假資料（Hardcoded Mock Data）的純前端展示頁面。雖然畫面上看似正常，但資料流根本未與中央氣象署串接，也未經過真正的資料庫持久化。

導入 **Five Gates** 後：
- **每一關皆有專屬驗證指標：** 沒拿到即時 CWA 資料（Gate 1）就不能宣稱完成資料管線；資料庫未能透過 SQL 查詢驗證（Gate 2）就不能宣稱完成後端 API（Gate 3）；未經本機全面驗證與 CI 設定（Gate 4）就不能推進雲端部署（Gate 5）。
- **可除錯性大幅提升：** 若前端地圖顯示異常，能立刻定位是 CWA 來源格式變動、SQLite 查詢問題，還是前端圖層渲染問題，降低排錯成本。

## 2. SQLite 在本地與 Serverless 雲端架構的差異與取捨
本作業在 Gate 2 與 Gate 5 面臨了 SQLite 特性與雲端架構的核心取捨：
- **Local 本地端：** 專案根目錄的 `data.db` 為可寫入資料庫。依現有實作架構，`observations` 表以 `station_id` 為主鍵，維護當前各測站的最新即時觀測快照與原地更新狀態（不無限制持續堆疊所有歷次歷史測站列，避免體積暴增）；而 `snapshots` 表則以 `(obs_time, source_mode)` 為複合主鍵，保存歷次快照的摘要與歷史詮釋資料（Metadata）。
- **Vercel Serverless 端：** Serverless Function 為無狀態（Stateless）容器，其短暫容器重啟或回收後，本地寫入無法持久保存。
- **最佳實踐決策：**
  遵循課堂示範要求，將 `data.db` 定位為**隨專案打包的結構化唯讀快照（Bundled SQLite Snapshot）**。此做法確保了 Serverless 端具備真實的 SQLite 查詢路徑，同時具備極高讀取效能與零額外雲端資料庫維護成本。
  針對長期歷史資料累積（如 24 小時全測站逐時溫度變化圖表、歷年極值分析），未來架構應演進為串接外部託管資料庫（如 PostgreSQL / Supabase / Neon），以達成跨實例、跨容器的持久化寫入。

## 3. 雙層金鑰安全隔離設計
系統涉及兩種不同性質的金鑰，採取了嚴格隔離策略：
1. **CWA API Key（Server-side Secret）：**
   - 屬於私人機密授權碼，絕不上傳 Git。金鑰僅儲存於本機受保護的環境變數、`.env` 或 `api_key.txt` 中（均已納入 `.gitignore` 嚴格保護）。
   - GitHub Actions CI 工作流程設定為**預期讀取 `secrets.CWA_API_KEY`（若遠端 Repository Secret 有配置）**；在此誠實說明：我們並未獨立驗證遠端 GitHub Repository 的 Secret 配置狀態。若遠端未設定該 Secret，腳本亦具備平滑降級為備援資料的容錯機制，確保 CI 測試穩定通過。
   - 資料抓取與後端對 CWA 的請求全部在伺服端完成，前端瀏覽器永遠接觸不到此金鑰。
2. **MapTiler Browser API Key（Client-side Token）：**
   - 用於地圖底圖向量圖資請求，屬於公開客戶端 Key。
   - 透過 MapTiler 雲端後台設定 **Allowed HTTP Origins**，僅允許指定網域與 localhost 呼叫，防止被未授權濫用。

---

# 六、專案結構與本機執行指南

### 目錄結構
```text
week3-cwa-station-map/
├── .github/
│   └── workflows/
│       └── update-and-deploy.yml    # GitHub Actions 自動化工作流
├── api/
│   └── index.py                     # Vercel Serverless Function 入口
├── docs/
│   ├── index.html                   # GIS 地圖主頁面
│   ├── style.css                    # 儀表板樣式
│   ├── app.js                       # Leaflet 地圖互動、7日預報與雙路徑資料載入
│   ├── report-dashboard.png         # 成果畫面截圖
│   └── data/
│       ├── stations.json            # 測站即時資料快照（Pages 備援）
│       ├── stations_fixture.json    # 測站離線測試備用資料
│       ├── forecast.json            # 7 日預報靜態快照（Pages 備援）
│       └── forecast_fixture.json    # 舊版 F-A0010-001 離線測試備用資料
├── scripts/
│   ├── database.py                  # Gate 2: SQLite 模組、資料表維護與 CLI 檢驗
│   ├── fetch_and_build.py           # Gate 1: CWA 雙資料集抓取與建置
│   ├── normalize.py                 # CWA 資料清理、色階計算與預報正規化
│   ├── query_db.py                  # Gate 2: 獨立 SQL 查詢驗證腳本
│   ├── verify_local.py              # 全流程本機自動驗證腳本
│   └── verify_production.py         # 生產環境線上自動驗證腳本
├── tests/
│   ├── test_color_scale.py          # 7 段氣溫色階測試
│   ├── test_database.py             # SQLite 綱要、重複測站處理與 Flask API 整合測試
│   ├── test_forecast.py             # 7 日天氣預報綱要、正規化、API 測試
│   ├── test_normalize.py            # 資料清理與無效值過濾測試
│   └── test_schema.py               # stations.json 綱要規範測試
├── data.db                          # Gate 2: 根目錄 SQLite 快照資料庫 (含測站與預報)
├── server.py                        # Gate 3: Flask Web 伺服器 (SQLite 唯讀，/api/weather & /api/forecast)
├── vercel.json                      # Gate 5: Vercel 打包與路由設定
├── requirements.txt                 # Python 依賴套件
└── README.md                        # 作業完整書面報告
```

### 本機安裝與執行步驟

1. **安裝依賴套件：**
   ```bash
   pip install -r requirements.txt
   ```

2. **安全執行 Gate 1 & Gate 2（CWA 資料取得並寫入 SQLite）：**
   ```powershell
   # 於 PowerShell 安全設定環境變數或建立 .env / api_key.txt 檔案（請勿在命令列印出金鑰）
   # 方法 A：設定工作階段環境變數
   $env:CWA_API_KEY = "您的中央氣象署授權碼"
   python scripts/fetch_and_build.py
   Remove-Item Env:\CWA_API_KEY

   # 方法 B：或建立 .env 檔案（已加入 .gitignore，絕不上傳 Git）
   # CWA_API_KEY=您的中央氣象署授權碼
   python scripts/fetch_and_build.py
   ```

3. **執行 Gate 2 資料庫查詢驗證：**
   ```bash
   python scripts/query_db.py --county 新竹縣 --limit 3
   ```

4. **執行完整測試套件與 JavaScript 檢查：**
   ```bash
   pytest -v
   node --check docs/app.js
   ```

5. **執行本機端全流程驗證：**
   ```bash
   python scripts/verify_local.py
   ```

6. **啟動 Flask Web 伺服器：**
   ```bash
   python server.py
   ```
   瀏覽器開啟：
   - 互動地圖：`http://127.0.0.1:5000/`
   - SQLite API：`http://127.0.0.1:5000/api/weather`
   - 資料庫檢驗：`http://127.0.0.1:5000/api/db-check?county=新竹縣&limit=3`
