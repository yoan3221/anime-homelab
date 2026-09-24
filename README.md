# Anime Homelab

自架的動漫追番 / 下載 / 播放 / 監控一體化面板。

> 一台家用 Linux 伺服器 + Docker Compose，把「追番 → 下載 → 播放 → 監看 → 管理」整條流程自動化，
> 全部服務只透過一個 HTTP 入口（nginx 反向代理）對內提供，不對外暴露任何管理介面。

---

## 動機

1. **不想再手動找種子** — 新番每週更新，用 ani-rss 訂閱 Mikan，劇場版用 qBittorrent 內建 RSS 規則，
   自動下載、自動重新命名、自動進 Jellyfin 媒體庫。
2. **自己的媒體庫** — Jellyfin + AMD VA-API 硬體轉碼，手機、平板、電視都能順播，不依賴任何雲端服務。
3. **單一入口、單一畫面** — Glance 儀表板整合：服務狀態、下載進度、網速、繼續觀看、天氣、主機狀態、
   Minecraft 伺服器狀態、即時新聞，一眼掌握。
4. **隱私與安全** — BT 走 I2P 混合模式降低真實 IP 暴露；所有容器不對外開 port（僅 nginx 入口），
   遠端存取走 Tailscale；機密（API token）全部用 `.env` 管理，不進版控。
5. **顺手的功能** — IPTV 直播（國家地理/BBC Earth）、網頁測速（LibreSpeed）、Minecraft 伺服器管理（MCSManager）。
6. **好看** — Pixiv 隨機背景圖 + 毛玻璃卡片 + **主色自動適配背景圖**（從圖片萃取色相動態換主題色）。

## 架構

```
                        ┌──────────────────────────────┐
   LAN / Tailscale ───▶ │  nginx :80/:443 (唯一入口)    │
                        │   /            → Glance 面板  │
                        │   /jellyfin/   → Jellyfin     │
                        │   /qb/         → qBittorrent  │
                        │   /ani/        → ani-rss      │
                        │   /mcsm/       → MCSManager   │
                        │   /glances/    → 系統監控      │
                        │   /speedtest/  → LibreSpeed   │
                        │   /live/       → IPTV 清單     │
                        │   /panel/      → 面板增強 JS   │
                        │   /bg/         → 背景圖       │
                        └──────────────┬───────────────┘
                                       │ (內部 Docker 網路)
        ┌──────────────┬───────────────┼──────────────┬─────────────┐
        ▼              ▼               ▼              ▼             ▼
   Jellyfin       qBittorrent      ani-rss        Glance        i2pd
   (媒體伺服器)    (BT 下載)      (追番訂閱)     (儀表板)      (I2P 路由)

   直連（無法反代，僅這兩個對外）：
   - qBittorrent 6881/tcp+udp  BT 對等連線
   - Minecraft   25565         遊戲連線（host 網路）
```

### 服務清單

| 服務 | 映像 | 用途 | 存取 |
|---|---|---|---|
| nginx | nginx:stable-alpine | 反向代理、靜態注入 | `http://<host>/` |
| Glance | glanceapp/glance | 儀表板 | `/` |
| Jellyfin | jellyfin/jellyfin | 媒體庫 / 播放 | `/jellyfin` |
| qBittorrent | lscr.io/linuxserver/qbittorrent | BT 下載 | `/qb` |
| ani-rss | wushuo894/ani-rss | 新番 RSS 訂閱自動下載 | `/ani` |
| i2pd | purplei2p/i2pd | I2P 路由（BT 匿名） | 內部 |
| glances | nicolargo/glances | 主機監控 API | `/glances` |
| LibreSpeed | ghcr.io/librespeed/speedtest | 網頁測速 | `/speedtest` |
| pixiv-bg | python:3.12-alpine | 背景圖抓取/輪換 | 內部（寫入 `/bg`） |
| MCSManager | githubyumao/mcsmanager-* | Minecraft 管理 | `/mcsm` |

## 目錄結構

```
anime/
├── docker-compose.yml        # 主堆疊（9 個服務）
├── .env                      # 機密（不進版控）
├── .env.example              # 機密範本
├── nginx/
│   ├── nginx.conf            # 反代 + sub_filter 注入
│   ├── panel/panel.js        # 面板增強腳本（背景/主色/動態刷新）
│   ├── live/live.m3u         # IPTV 頻道清單
│   └── bg/                   # 背景圖（pixiv-bg 產生，不進版控）
├── glance/
│   ├── config/glance.yml     # 儀表板設定（用 ${ENV} 引用機密）
│   └── assets/user.css       # 自訂樣式
├── librespeed/servers.json   # 測速伺服器設定（子路徑修正）
├── pixiv-bg/pixivbg.py       # 背景圖抓取腳本
└── mcsmanager/docker-compose.yml  # Minecraft 管理堆疊（獨立專案，參考用）
```

## 核心技術

### 1. 反向代理與子路徑

所有服務掛在 nginx 子路徑（`/jellyfin`、`/qb`…），nginx 剝掉前綴再轉發（`proxy_pass http://svc:port/`），
非根路徑的服務（qbt/ani/mcsm/librespeed）在存取時會自動補尾斜線避免相對路徑壞掉。

> 規則：**容器一律不對外開 port**，唯一例外是無法用 HTTP 代理的 BT（6881）與 Minecraft（25565）。

### 2. 面板增強 `nginx/panel/panel.js`

因為 nginx 設定單一參數上限 2048 字元，腳本放在外部檔案，由 `sub_filter` 注入 `<script src="/panel/panel.js" defer>`。

| 功能 | 說明 |
|---|---|
| 背景輪播 + 淡入淡出 | 兩個 `.bg-layer`，換圖時交叉淡入（1.6s）；每次載入隨機抽一張 |
| **主色自動適配** | 圖片載入後縮到 64×64，做「飽和度×亮度加權色相直方圖」（36 格 + 鄰格平滑），取最鮮豔色相 → 動態設定 CSS 變數 |
| 動態刷新 | 每 5 秒重抓 Glance 內容 API，替換「網速／下載中心／Minecraft」三個 widget |
| 相對時間填補 | 刷新後補上 `data-dynamic-relative-time` 的內容（Glance 原生只填載入時的元素） |

主色連動的 CSS 變數：

```css
--color-primary   /* 強調色：標題條、連結、進度條 */
--accent-2        /* 類比色（+38°）：漸層 */
--bgh             /* Glance 文字色相（整體協調） */
--bg-tint         /* 背景遮罩染色 */
--widget-bg       /* 毛玻璃卡背景染色 */
```

### 3. 自動追番流程

```
Mikan RSS（新番）──▶ ani-rss ──▶ qBittorrent ──▶ 重新命名 ──▶ Jellyfin 媒體庫
Nyaa RSS（劇場版）──▶ qBittorrent 內建 RSS 規則 ──▶ /downloads/剧场版 ──▶ Jellyfin
```

- ani-rss 訂閱：番劇自動下載 + 自動改名（`/downloads/番剧`）
- qBittorrent RSS 規則：`剧场版-蜜柑`、`剧场版-Nyaa`（關鍵字：劇場版/剧场版）
- Jellyfin 監看 `./downloads`（番剧 / 剧场版 兩個媒體庫）

### 4. Jellyfin 硬體轉碼（AMD VA-API）

- 裝置：`/dev/dri/renderD128`，容器 `group_add: 991, 44`
- 設定：`vaapi` 解碼 h264/hevc/vp9/av1、`EnableHardwareEncoding`、`AllowHevcEncoding`、`EnableTonemapping`
- 實測：HEVC 硬解 → H.264 硬編全鏈路通過

### 5. 隱私：BT over I2P

i2pd 容器提供 SAM 橋（7656），qBittorrent 設定 I2P 混合模式（`i2p_enabled`），
I2P-only 種子走匿名網路，一般公開種子仍走普通連線（速度不受影響）。

### 6. IPTV 直播

`nginx/live/live.m3u`：國家地理（美/俄/墨）、Nat Geo Wild、BBC Earth 等公開 HLS 源
（來源：iptv-org 精選 + 實測可連），Jellyfin 以 m3u 調諧器載入。

### 7. 網頁測速（LibreSpeed）

- 掛在 `/speedtest/`（子路徑），`librespeed/servers.json` 指向 `/speedtest/backend`
- nginx 調校：`client_max_body_size 0`（上傳測試送 20MB blob）、關閉 request/response buffering

### 8. Minecraft 伺服器狀態

MCSManager OpenAPI（`enableApiKey` + 使用者 apiKey）→ Glance `custom-api` widget：
狀態、玩家數（MCSM MC Ping）、運行時長；滑鼠移上玩家數顯示版本/延遲。

### 9. 主機監控

Glances 以 `host` 網路模式執行，Web/API **只綁 Docker 網關**（區網不可直達），
經 nginx `/glances/` 存取；Glance 面板用 `newRequest` 串接 `/api/4/*` 顯示 CPU/記憶體/溫度/磁碟。

## 部署

```bash
git clone <repo> && cd anime
cp .env.example .env && vim .env        # 填入 QBT_TOKEN / JELLYFIN_API_KEY / MCSM_API_KEY
docker compose up -d
```

首次部署後的設定（無法完全自動化）：

1. **Jellyfin**：建立管理員 → 加入媒體庫（`./downloads/番剧`、`./downloads/剧场版`）→ 建立 API Key
2. **qBittorrent**：設定下載路徑、RSS 訂閱與規則（見 core 技術 3）
3. **ani-rss**：預設帳號 `admin`（登入後修改密碼）
4. **MCSManager**：安裝 daemon → 開啟 OpenAPI → 產生 apiKey
5. **nginx**：`docker exec nginx nginx -t && docker exec nginx nginx -s reload`

## 維護

```bash
docker compose ps                     # 狀態
docker compose logs -f <service>      # 日誌
docker compose pull && docker compose up -d   # 更新
docker exec nginx nginx -t            # 改 nginx 設定後檢查
```

- 背景圖：`pixiv-bg` 每 6 小時抓新圖、保留 6 張（設定在 compose 環境變數）
- 面板樣式/腳本：改 `glance/assets/user.css` 或 `nginx/panel/panel.js` → **Ctrl+F5**（有快取）
- 設定改完免重啟：Glance 會自動熱重載

## 安全設計

- **Port 政策**：容器只出不進，僅 nginx（80/443）、BT（6881）、Minecraft（25565）對外
- **機密管理**：所有 token 以 `${ENV}` 引用，實際值在 `.env`（`.gitignore` 排除）
- **遠端存取**：Tailscale 組網，不開公網 port
- **I2P**：BT 混合模式
- **授權提醒**：本專案僅供個人自架學習；RSS/IPTV 來源皆為公開資源，請自行確認當地法規

## 已知取捨

- 公開 IPTV 源隨時可能失效（無後台監控），失效時更新 `nginx/live/live.m3u`
- 不依賴 PT 站，新番/劇場版皆走公開 RSS（速度取決於做種人數）
- 單機部署，無高可用；資料靠定期備份（`downloads/`、`jellyfin/config/`、`qbittorrent/config/`）
