# DESIGN.md — StockMarket 篩選系統

## 1. Objective

讓使用者在高密度股票篩選結果中，快速比較機會與風險。介面應像穩定、可信的分析工具，重要數字一眼可辨，但不以裝飾干擾判斷。

## 2. Product Context

- **What the product does:** 從 A 股日線資料執行策略並展示候選股票。
- **Who it's for:** 每日查看技術面篩選結果的個人投資研究者。
- **Adjacent brands:** Linear、Datawrapper、東方財富的資料密度。
- **Distant brand:** 行銷型金融落地頁，不需要情緒化視覺或轉化話術。
- **Cultural register:** 技術、克制、資料優先。

## 3. Visual Foundations

### 3a. Color

- **Neutral scale:** `#ffffff / #fafafa / #f0f2f5 / #d9d9d9 / #888888 / #333333`
- **Accent:** `#1677ff` 用於導航與連結；`#cf1322` 用於上漲；`#389e0d` 用於低回撤。
- **Usage rules:** 顏色只編碼互動或數值意義，不作大面積裝飾。

### 3b. Typography

- **Display/body:** `-apple-system, "Microsoft YaHei", "Segoe UI", sans-serif`
- **Data:** `"Cascadia Code", Consolas, monospace`
- **Type scale:** `12 / 13 / 14 / 16 / 22 / 28`
- **Weight discipline:** 400 正文、600 標題與核心數字。

### 3c. Spacing & rhythm

- **Base unit:** 4px。
- **Spacing scale:** `4 / 8 / 12 / 16 / 20 / 24 / 32 / 48`。
- **Density:** 桌面表格行高約 44px；手機版維持最小 44px 點擊區。

### 3d. Component seeds

- **Buttons:** 每個視圖僅一個填色主按鈕，其他操作使用文字或表頭按鈕。
- **Containers:** 8px 圓角、1px 邊線，不疊加多層陰影。
- **Data bars:** 漲幅與回撤以文字為主、橫條為輔，保留精確數值。

## 4. Accessibility

- 正文對比至少 4.5:1；所有可排序表頭有可見 focus ring。
- 不依賴顏色單獨傳達數值；手機允許表格水平捲動。
- 無非必要動畫。

## 5. Voice & Tone

- **Register:** 直接、技術、簡短。
- **Words used:** 交易日、漲幅、最大回撤、趨勢擬合度。
- **Words refused:** 智能推薦、穩賺、潛力股、財富密碼。
- **Address:** 不使用第二人稱，直接描述資料狀態。

## 6. Implementation Practices

- 使用既有 Jinja2 模板與原生 CSS/JavaScript。
- 延續現有色彩、圓角與表格模式；不引入外部字體或套件。
- 響應式斷點 720px，資料表保持完整並可水平捲動。

## 7. Anti-Patterns

- **不增加 KPI 卡片列。** 新策略的核心是逐股比較，不是摘要數字堆疊。
- **不使用圖表取代精確表格。** 41 支股票需要查找、排序與外連。
- **不使用多色漸層。** 顏色只代表漲幅、回撤和互動狀態。
- **不隱藏空狀態原因。** 無結果時明示完整篩選條件。

## 8. Decision-Making

1. 可比較性優先於裝飾。
2. 精確數值優先於視覺摘要。
3. 既有介面一致性優先於新穎風格。
4. 桌面密度與手機可用性並重。

## 9. Workflow

1. 先定義資料欄位與排序。
2. 使用既有 token 與元件模式。
3. 補齊載入、空白及錯誤狀態。
4. 驗證桌面與 375px 寬度。
5. 驗證鍵盤、對比與數值格式。
