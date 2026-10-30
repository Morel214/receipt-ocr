"""Built-in Web UI Dashboard for managing Telegram bots, shared Product Catalog, global taxonomy, webhooks, and testing receipt OCR."""

from ocr_hub import config


def render_dashboard_html() -> str:
    """Return the single-page English Web Dashboard HTML."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Receipt OCR Hub — Web Dashboard</title>
  <style>
    :root {{
      --bg: #0f172a;
      --card: #1e293b;
      --border: #334155;
      --text: #f8fafc;
      --muted: #94a3b8;
      --accent: #38bdf8;
      --accent-hover: #0284c7;
      --success: #22c55e;
      --warning: #f59e0b;
      --danger: #ef4444;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
      padding: 24px;
    }}
    .container {{
      max-width: 1240px;
      margin: 0 auto;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 12px;
      margin-bottom: 16px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--border);
    }}
    h1 {{ margin: 0; font-size: 1.6rem; }}
    h2 {{ margin-top: 0; font-size: 1.2rem; }}
    h3 {{ margin: 0 0 8px 0; font-size: 1rem; }}
    .sub {{ color: var(--muted); font-size: 0.9rem; }}
    .nav-tabs {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-bottom: 20px;
      padding-bottom: 12px;
      border-bottom: 1px solid var(--border);
    }}
    .tab-btn {{
      margin-top: 0;
      padding: 9px 16px;
      border-radius: 9px;
      background: #162033;
      color: var(--muted);
      border: 1px solid var(--border);
      font-weight: 600;
      font-size: 0.88rem;
      display: inline-flex;
      align-items: center;
      gap: 7px;
    }}
    .tab-btn:hover {{
      background: #1e293b;
      color: var(--text);
    }}
    .tab-btn.active {{
      background: var(--accent);
      color: #0f172a;
      border-color: var(--accent);
    }}
    .sub-tabs {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-bottom: 16px;
    }}
    .sub-tab-btn {{
      margin-top: 0;
      padding: 7px 13px;
      border-radius: 999px;
      background: #0b1120;
      color: var(--muted);
      border: 1px solid var(--border);
      font-size: 0.82rem;
      font-weight: 600;
    }}
    .sub-tab-btn.active {{
      background: rgba(56, 189, 248, 0.18);
      color: var(--accent);
      border-color: var(--accent);
    }}
    .tab-panel {{ display: none; }}
    .tab-panel.active {{ display: block; }}
    .grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 20px;
      margin-bottom: 24px;
    }}
    .kpi-grid {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 14px;
      margin-bottom: 18px;
    }}
    @media (max-width: 920px) {{
      .grid {{ grid-template-columns: 1fr; }}
      .kpi-grid {{ grid-template-columns: 1fr 1fr; }}
    }}
    @media (max-width: 560px) {{
      .kpi-grid {{ grid-template-columns: 1fr; }}
    }}
    .kpi-card {{
      background: #0b1120;
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 14px 16px;
    }}
    .kpi-value {{
      font-size: 1.55rem;
      font-weight: 700;
      color: var(--text);
      line-height: 1.2;
      margin: 4px 0;
    }}
    .kpi-label {{
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--muted);
    }}
    .card {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 20px;
      margin-bottom: 20px;
    }}
    label {{
      display: block;
      font-size: 0.82rem;
      color: var(--muted);
      margin-bottom: 4px;
      margin-top: 10px;
    }}
    input, select, textarea {{
      width: 100%;
      padding: 9px 11px;
      border-radius: 8px;
      border: 1px solid var(--border);
      background: #0b1120;
      color: var(--text);
      font-size: 0.9rem;
    }}
    .row2 {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }}
    .row3 {{
      display: grid;
      grid-template-columns: 2fr 1fr 1fr;
      gap: 10px;
      align-items: end;
    }}
    .row4 {{
      display: grid;
      grid-template-columns: 1fr 1fr 1fr auto;
      gap: 10px;
      align-items: end;
    }}
    .row5 {{
      display: grid;
      grid-template-columns: 1fr 1fr 1fr 1fr auto;
      gap: 10px;
      align-items: end;
    }}
    @media (max-width: 860px) {{
      .row3, .row4, .row5 {{ grid-template-columns: 1fr; }}
    }}
    button {{
      margin-top: 14px;
      padding: 9px 15px;
      border-radius: 8px;
      border: none;
      background: var(--accent);
      color: #0f172a;
      font-weight: 600;
      cursor: pointer;
      font-size: 0.88rem;
    }}
    button:hover {{ background: var(--accent-hover); color: #fff; }}
    button.secondary {{
      background: #334155;
      color: var(--text);
    }}
    button.success {{
      background: rgba(34, 197, 94, 0.22);
      color: #4ade80;
      border: 1px solid rgba(34, 197, 94, 0.35);
    }}
    button.success:hover {{
      background: var(--success);
      color: #0f172a;
    }}
    button.danger {{
      background: var(--danger);
      color: #fff;
    }}
    button.small {{
      margin-top: 0;
      padding: 4px 9px;
      font-size: 0.76rem;
    }}
    .bot-item, .cat-box {{
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 14px;
      margin-bottom: 12px;
      background: #0b1120;
    }}
    .bot-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }}
    .badge {{
      display: inline-block;
      padding: 2px 8px;
      border-radius: 999px;
      font-size: 0.75rem;
      font-weight: 600;
    }}
    .badge.ok {{ background: rgba(34,197,94,0.18); color: #4ade80; }}
    .badge.warn {{ background: rgba(245,158,11,0.2); color: #fbbf24; }}
    .badge.auto {{ background: rgba(56,189,248,0.18); color: #38bdf8; }}
    .badge.off {{ background: rgba(148,163,184,0.18); color: #cbd5e1; }}
    code {{
      background: #1e293b;
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 0.82rem;
      word-break: break-all;
    }}
    pre {{
      background: #0b1120;
      border: 1px solid var(--border);
      padding: 12px;
      border-radius: 8px;
      overflow-x: auto;
      font-size: 0.82rem;
      max-height: 380px;
      color: #e2e8f0;
    }}
    .actions {{
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
      margin-top: 8px;
    }}
    .actions button {{ margin-top: 0; padding: 6px 11px; font-size: 0.8rem; }}
    .status-msg {{
      margin-top: 10px;
      font-size: 0.85rem;
      color: var(--accent);
    }}
    .table-wrap {{
      overflow-x: auto;
      margin-top: 12px;
    }}
    table.schema-table, table.catalog-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.84rem;
    }}
    table.schema-table th, table.schema-table td,
    table.catalog-table th, table.catalog-table td {{
      padding: 8px 10px;
      border: 1px solid var(--border);
      text-align: left;
      vertical-align: middle;
    }}
    table.schema-table th, table.catalog-table th {{
      background: #0b1120;
      color: var(--accent);
      white-space: nowrap;
    }}
    table.catalog-table tr:hover td {{
      background: rgba(15, 23, 42, 0.55);
    }}
    .subcat-grid {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 10px;
    }}
    .subcat-chip {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 5px 10px;
      background: #162033;
      font-size: 0.82rem;
    }}
    .subcat-chip.inactive {{
      opacity: 0.5;
    }}
    .modes-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin-top: 6px;
    }}
    @media (max-width: 600px) {{
      .modes-grid {{ grid-template-columns: 1fr; }}
    }}
    .mode-option {{
      display: flex;
      align-items: flex-start;
      gap: 8px;
      padding: 8px 10px;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: #0b1120;
      font-size: 0.83rem;
      color: var(--text);
      margin: 0;
      cursor: pointer;
    }}
    .mode-option input {{
      width: auto;
      margin-top: 3px;
    }}
    .info-banner {{
      border: 1px solid rgba(56, 189, 248, 0.35);
      background: rgba(56, 189, 248, 0.08);
      border-radius: 10px;
      padding: 10px 14px;
      font-size: 0.84rem;
      color: #e2e8f0;
      margin-bottom: 14px;
    }}
    .modal-backdrop {{
      display: none;
      position: fixed;
      inset: 0;
      background: rgba(2, 6, 23, 0.76);
      z-index: 1000;
      align-items: center;
      justify-content: center;
      padding: 16px;
    }}
    .modal-backdrop.open {{
      display: flex;
    }}
    .modal-box {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 20px;
      width: 100%;
      max-width: 540px;
      max-height: 90vh;
      overflow-y: auto;
    }}
    .candidate-list {{
      max-height: 220px;
      overflow-y: auto;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: #0b1120;
      margin-top: 8px;
    }}
    .candidate-row {{
      padding: 8px 11px;
      border-bottom: 1px solid var(--border);
      cursor: pointer;
      font-size: 0.84rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    .candidate-row:last-child {{ border-bottom: none; }}
    .candidate-row:hover {{ background: #162033; }}
    .candidate-row.selected {{
      background: rgba(56, 189, 248, 0.2);
      border-left: 3px solid var(--accent);
    }}
    .link-btn {{
      background: none;
      border: none;
      color: var(--accent);
      padding: 0;
      margin: 0;
      font-size: 0.82rem;
      cursor: pointer;
      text-decoration: underline;
    }}
    .link-btn:hover {{
      background: none;
      color: #7dd3fc;
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div>
        <h1>🧾 Receipt OCR Hub</h1>
        <div class="sub">
          Global Server Models: <code>Stage 1 OCR = {config.OCR_PROVIDER}/{config.OCR_MODEL}</code> &rarr;
          <code>Stage 2 Classifier = {config.CLASSIFIER_PROVIDER}/{config.CLASSIFIER_MODEL}</code>
        </div>
      </div>
      <div style="display:flex; align-items:center; gap:10px; flex-wrap:wrap;">
        <span id="adminStatusBadge" class="badge off">🔒 Guest Mode</span>
        <input type="password" id="adminKeyInput" placeholder="Admin Key"
               style="width:180px; padding:6px 10px; font-size:0.8rem;"
               onchange="saveAdminKey()" />
        <a href="/docs" style="color: var(--accent); text-decoration: none; font-weight: 600;">Swagger API Docs &rarr;</a>
      </div>
    </header>

    <!-- Main Top-Level Navigation Tabs -->
    <nav class="nav-tabs">
      <button id="nav-bots" class="tab-btn active" onclick="switchMainTab('bots')">
        🤖 Bots &amp; OCR Tester
      </button>
      <button id="nav-catalog" class="tab-btn" onclick="switchMainTab('catalog')">
        📦 Product Catalog
        <span id="catalogNavBadge" class="badge warn" style="display:none;">0</span>
      </button>
      <button id="nav-taxonomy" class="tab-btn" onclick="switchMainTab('taxonomy')">
        🏷️ Global Taxonomy
      </button>
      <button id="nav-schema" class="tab-btn" onclick="switchMainTab('schema')">
        📑 JSON &amp; CSV Schema
      </button>
    </nav>

    <!-- ================================================================== -->
    <!-- TAB 1: BOTS & LIVE OCR TESTER                                      -->
    <!-- ================================================================== -->
    <div id="panel-bots" class="tab-panel active">
      <div class="grid">
        <!-- Left: Add / Edit Bot & Destination Form -->
        <div class="card">
          <h2 id="formTitle">➕ Add or Update Bot / User</h2>
          <div class="sub" style="margin-bottom: 8px;">
            Configure a user API key / Telegram bot. Product classification uses the shared Global Taxonomy &amp; Catalog.
          </div>
          <input type="hidden" id="editBotId" value="" />

          <div class="row2">
            <div>
              <label>User / Bot Name *</label>
              <input type="text" id="botName" placeholder="e.g. Domingo or Alex" required />
            </div>
            <div>
              <label>Default Currency</label>
              <input type="text" id="botCurrency" value="PLN" placeholder="PLN, EUR, USD" />
            </div>
          </div>

          <div class="row2">
            <div>
              <label>Clean Product Name Language</label>
              <select id="botLanguage">
                <option value="pl">Polish (pl)</option>
                <option value="en">English (en)</option>
              </select>
            </div>
            <div>
              <label>Telegram Bot Token (optional for API-only)</label>
              <input type="text" id="botToken" placeholder="123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ" />
            </div>
          </div>

          <label>Allowed Telegram Chat IDs (optional, comma-separated; leave empty to allow any chat)</label>
          <input type="text" id="allowedChatIds" placeholder="e.g. 123456789, 987654321" />

          <label>Destination Webhook URL (optional — where confirmed receipt JSON is POSTed)</label>
          <input type="text" id="webhookUrl" placeholder="http://100.x.y.z:8000/api/receipts/webhook" />

          <label>Destination Webhook Bearer Secret (optional)</label>
          <input type="text" id="webhookSecret" placeholder="Optional Authorization Bearer token" />

          <label>Post-Confirmation Delivery Modes (choose any combination)</label>
          <div class="modes-grid">
            <label class="mode-option">
              <input type="checkbox" id="modeHubDb" value="hub_db" checked />
              <span><b>🗄️ Save to Hub DB</b><br/><span class="sub" style="font-size:0.75rem;">Enables <code>/api/receipts</code> &amp; <code>/export</code></span></span>
            </label>
            <label class="mode-option">
              <input type="checkbox" id="modeWebhook" value="webhook" checked />
              <span><b>🔗 Send Webhook JSON</b><br/><span class="sub" style="font-size:0.75rem;">POSTs payload to Webhook URL</span></span>
            </label>
            <label class="mode-option">
              <input type="checkbox" id="modeTgText" value="telegram_text" />
              <span><b>📋 Telegram Copyable Text</b><br/><span class="sub" style="font-size:0.75rem;">Sends <code>&lt;pre&gt;</code> CSV block in chat</span></span>
            </label>
            <label class="mode-option">
              <input type="checkbox" id="modeTgCsv" value="telegram_csv" />
              <span><b>📄 Telegram CSV File</b><br/><span class="sub" style="font-size:0.75rem;">Attaches <code>.csv</code> file in chat</span></span>
            </label>
          </div>
          <div class="sub" style="font-size:0.76rem; margin-top:6px;">
            🔒 Privacy: Anonymized product names always teach the shared catalog on confirm, while personal receipts &amp; prices are stored on this server <b>only</b> if <code>Save to Hub DB</code> is checked.
          </div>

          <div class="actions" style="margin-top: 16px;">
            <button onclick="saveBot()">💾 Save User / Bot</button>
            <button class="secondary" onclick="resetForm()">Clear Form</button>
          </div>
          <div id="formStatus" class="status-msg"></div>
        </div>

        <!-- Right: Live 2-Stage OCR Tester -->
        <div class="card">
          <h2>🧪 Test Receipt OCR</h2>
          <div class="sub">Upload a receipt photo to test Stage 1 Vision OCR &rarr; Cache Lookup &rarr; Stage 2 Classification directly in the browser.</div>

          <label>API Key (select a user below or paste key)</label>
          <input type="text" id="testApiKey" placeholder="ocr_live_..." />

          <label>Receipt Photo (JPEG / PNG / WEBP)</label>
          <input type="file" id="testFile" accept="image/jpeg,image/png,image/webp" />

          <label style="display:flex; align-items:center; gap:8px; margin-top:12px;">
            <input type="checkbox" id="testSendWebhook" style="width:auto;" />
            Also forward final JSON to this user's Destination Webhook URL
          </label>
          <label style="display:flex; align-items:center; gap:8px; margin-top:8px;">
            <input type="checkbox" id="testSaveHubDb" style="width:auto;" />
            Also save parsed receipt into Hub DB (<code>GET /api/receipts</code>)
          </label>

          <button onclick="runOcrTest()">🚀 Parse Receipt Now</button>
          <div id="ocrStatus" class="status-msg"></div>
          <pre id="ocrOutput">JSON output will appear here...</pre>
        </div>
      </div>

      <!-- Registered Bots & API Keys -->
      <div class="card">
        <h2>🤖 Registered Users &amp; Telegram Bots</h2>
        <div class="sub" style="margin-bottom: 12px;">
          Direct API usage: <code>curl -X POST http://&lt;HOST&gt;:8080/api/ocr -H "X-API-Key: &lt;API_KEY&gt;" -F "file=@receipt.jpg"</code>
        </div>
        <div id="botsList">Loading...</div>
      </div>
    </div>

    <!-- ================================================================== -->
    <!-- TAB 2: SHARED PRODUCT CATALOG & REVIEW QUEUES                      -->
    <!-- ================================================================== -->
    <div id="panel-catalog" class="tab-panel">
      <div class="kpi-grid">
        <div class="kpi-card">
          <div class="kpi-label">Active Catalog Products</div>
          <div class="kpi-value" id="kpiProductsActive">0</div>
          <div class="sub" style="font-size:0.78rem;" id="kpiProductsSub">0 confirmed · 0 auto (LLM)</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">Cached Store Aliases</div>
          <div class="kpi-value" id="kpiAliasesTotal">0</div>
          <div class="sub" style="font-size:0.78rem;" id="kpiAliasesSub">0 confirmed · 0 auto across 0 stores</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">Stage 2 Cache Hit Rate</div>
          <div class="kpi-value" id="kpiHitRate">0%</div>
          <div class="sub" style="font-size:0.78rem;" id="kpiHitsSub">0 repeat cache hits (0 total lookups)</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">Manual User Queue</div>
          <div class="kpi-value" id="kpiManualPending">0</div>
          <div class="sub" style="font-size:0.78rem;" id="kpiManualSub">Inactive until Admin approves</div>
        </div>
      </div>

      <div class="card">
        <div class="bot-header" style="margin-bottom: 12px;">
          <div>
            <h2 style="margin-bottom: 2px;">📦 Shared Product &amp; Alias Catalog</h2>
            <div class="sub">
              Two-level Polish/English catalog: generic clean products for statistics + store-specific aliases &amp; Open Food Facts queries.
            </div>
          </div>
          <button class="secondary small" onclick="refreshCatalogAll()">🔄 Refresh</button>
        </div>

        <div class="sub-tabs">
          <button id="subtab-products" class="sub-tab-btn active" onclick="switchCatalogMode('products')">
            🔎 Products Browser
          </button>
          <button id="subtab-auto_review" class="sub-tab-btn" onclick="switchCatalogMode('auto_review')">
            🤖 Auto-LLM Review (Optional) <span id="badgeAutoCount" class="badge auto">0</span>
          </button>
          <button id="subtab-manual_user" class="sub-tab-btn" onclick="switchCatalogMode('manual_user')">
            👤 Manual User Queue <span id="badgeManualCount" class="badge warn">0</span>
          </button>
          <button id="subtab-aliases" class="sub-tab-btn" onclick="switchCatalogMode('aliases')">
            🏪 Receipt Aliases &amp; OFF Queries
          </button>
        </div>

        <!-- SUBVIEW A: PRODUCTS & AUTO-LLM REVIEW -->
        <div id="catViewProducts">
          <div id="autoReviewBanner" class="info-banner" style="display:none;">
            💡 <b>Optional Tidying Queue:</b> All <code>auto</code> products learned from confirmed receipts already work automatically in the cache!
            Whenever you feel like cleaning up, you can confirm them with 1 click, rename PL/EN labels, or merge duplicates.
          </div>

          <div style="border: 1px solid var(--border); border-radius: 10px; padding: 14px; margin-bottom: 14px; background: #0b1120;">
            <h3>➕ Add Clean Product to Catalog</h3>
            <div class="row5">
              <div>
                <label>Clean Name (Polish) *</label>
                <input type="text" id="newProdPl" placeholder="e.g. twaróg półtłusty" />
              </div>
              <div>
                <label>Clean Name (English) *</label>
                <input type="text" id="newProdEn" placeholder="e.g. semi-fat quark" />
              </div>
              <div>
                <label>Subcategory</label>
                <select id="newProdSubcat"></select>
              </div>
              <div>
                <label>Default Unit</label>
                <select id="newProdUnit">
                  <option value="pcs">pcs (szt.)</option>
                  <option value="kg">kg</option>
                  <option value="l">l</option>
                </select>
              </div>
              <div>
                <button style="margin-top:0;" onclick="addCatalogProduct()">Add Product</button>
              </div>
            </div>
            <div id="prodAddStatus" class="status-msg"></div>
          </div>

          <div class="row3" style="margin-bottom: 10px;">
            <div>
              <label>Search Products, Brands, or Receipt Aliases (FTS5 typo-tolerant)</label>
              <input type="text" id="prodSearchInput" placeholder="e.g. jajka, twarog, moja kurka, łaciate..."
                     oninput="debouncedLoadProducts()" />
            </div>
            <div>
              <label>Filter Subcategory</label>
              <select id="prodFilterSubcat" onchange="loadCatalogProducts()">
                <option value="">All Subcategories</option>
              </select>
            </div>
            <div id="prodStatusFilterBox">
              <label>Filter Status</label>
              <select id="prodFilterStatus" onchange="loadCatalogProducts()">
                <option value="">All Active (Confirmed + Auto)</option>
                <option value="confirmed">Confirmed Only</option>
                <option value="auto">Auto (LLM) Only</option>
              </select>
            </div>
          </div>

          <div id="productsTableContainer" class="table-wrap">Loading products...</div>
        </div>

        <!-- SUBVIEW B: MANUAL USER APPROVAL QUEUE -->
        <div id="catViewManual" style="display:none;">
          <div class="info-banner">
            🛡️ <b>Manual User Approval Queue:</b> Categories, subcategories, and products submitted without an Admin Key stay
            completely inactive (excluded from Stage 2 prompts &amp; FTS5 cache) until approved here by Admin.
          </div>
          <div id="manualQueueContainer">Loading manual user queue...</div>
        </div>

        <!-- SUBVIEW C: RECEIPT ALIASES & OPEN FOOD FACTS QUERIES -->
        <div id="catViewAliases" style="display:none;">
          <div class="bot-header" style="margin-bottom: 8px;">
            <div id="aliasProductFilterChip"></div>
            <div id="adminAddAliasBtnWrap"></div>
          </div>
          <div class="row3" style="margin-bottom: 10px;">
            <div>
              <label>Search Raw Receipt Text, Brand, OFF Query, or Clean Product</label>
              <input type="text" id="aliasSearchInput" placeholder="e.g. JAJA MOJA KURKA, LACIATE, gouda..."
                     oninput="debouncedLoadAliases()" />
            </div>
            <div>
              <label>Filter Store Chain</label>
              <select id="aliasFilterStore" onchange="loadCatalogAliases()">
                <option value="">All Stores</option>
              </select>
            </div>
            <div>
              <label>Filter Status</label>
              <select id="aliasFilterStatus" onchange="loadCatalogAliases()">
                <option value="">All (Confirmed + Auto)</option>
                <option value="confirmed">Confirmed Only</option>
                <option value="auto">Auto (LLM) Only</option>
              </select>
            </div>
          </div>
          <div id="aliasesTableContainer" class="table-wrap">Loading aliases...</div>
        </div>
      </div>
    </div>

    <!-- ================================================================== -->
    <!-- TAB 3: GLOBAL CATEGORIES & SUBCATEGORIES TAXONOMY                  -->
    <!-- ================================================================== -->
    <div id="panel-taxonomy" class="tab-panel">
      <div class="card">
        <h2>🏷️ Global Categories &amp; Subcategories (Shared Catalog Taxonomy)</h2>
        <div class="sub" style="margin-bottom: 14px;">
          Verify, rename (PL / EN), toggle, or add categories and subcategories shared across all users and the product catalog.
        </div>

        <div style="border: 1px solid var(--border); border-radius: 10px; padding: 14px; margin-bottom: 14px; background: #0b1120;">
          <h3>➕ Add Top-Level Category</h3>
          <div class="row4">
            <div>
              <label>Category Code (e.g. FOOD, PETS)</label>
              <input type="text" id="newCatCode" placeholder="PETS" />
            </div>
            <div>
              <label>Name (Polish)</label>
              <input type="text" id="newCatPl" placeholder="Zwierzęta" />
            </div>
            <div>
              <label>Name (English)</label>
              <input type="text" id="newCatEn" placeholder="Pets" />
            </div>
            <div>
              <button style="margin-top:0;" onclick="addCategory()">Add Category</button>
            </div>
          </div>

          <h3 style="margin-top: 16px;">➕ Add Subcategory</h3>
          <div class="row5">
            <div>
              <label>Parent Category</label>
              <select id="newSubCatParent"></select>
            </div>
            <div>
              <label>Subcategory Code</label>
              <input type="text" id="newSubCode" placeholder="pet_food" />
            </div>
            <div>
              <label>Name (Polish)</label>
              <input type="text" id="newSubPl" placeholder="karma dla zwierząt" />
            </div>
            <div>
              <label>Name (English)</label>
              <input type="text" id="newSubEn" placeholder="pet food" />
            </div>
            <div>
              <button style="margin-top:0;" onclick="addSubcategory()">Add Subcategory</button>
            </div>
          </div>
          <div id="taxStatus" class="status-msg"></div>
        </div>

        <div id="taxonomyContainer">Loading taxonomy...</div>
      </div>
    </div>

    <!-- ================================================================== -->
    <!-- TAB 4: FINAL OUTPUT JSON & CSV SCHEMA                              -->
    <!-- ================================================================== -->
    <div id="panel-schema" class="tab-panel">
      <div class="card">
        <h2>📑 Final Output JSON &amp; CSV Schema (Webhook, API &amp; Telegram)</h2>
        <div class="sub" style="margin-bottom: 12px;">
          Exact output format returned by <code>POST /api/ocr</code>, delivered to your <b>Destination Webhook URL</b>, or exported as CSV:
        </div>
        <div class="grid" style="margin-bottom: 0;">
          <div>
            <pre><code>{{
  "store_name": "Biedronka",
  "transaction_date": "2026-10-28",
  "total_amount": 21.48,
  "currency": "PLN",
  "cache_hits": 1,
  "llm_classified_count": 1,
  "items": [
    {{
      "name": "JAJA MOJA KURKA M 10",
      "clean_name": "jajka",
      "category": "FOOD",
      "subcategory": "eggs",
      "unit": "pcs",
      "quantity": 1.0,
      "unit_price": 8.99,
      "total_price": 8.99,
      "product_id": 1,
      "brand": "Moja Kurka",
      "off_search_query": "Moja Kurka jaja M 10 szt",
      "match_source": "cache"
    }},
    {{
      "name": "MLEKO LACIATE 3,2% 1L",
      "clean_name": "mleko 3.2%",
      "category": "FOOD",
      "subcategory": "dairy",
      "unit": "pcs",
      "quantity": 3.0,
      "unit_price": 4.49,
      "total_price": 13.47,
      "product_id": 2,
      "brand": "Łaciate",
      "off_search_query": "Łaciate mleko 3.2% 1L",
      "match_source": "llm"
    }},
    {{
      "name": "RABAT MLEKO 3W2",
      "clean_name": "Rabat",
      "category": null,
      "subcategory": null,
      "unit": "pcs",
      "quantity": 1.0,
      "unit_price": -0.98,
      "total_price": -0.98,
      "product_id": null,
      "brand": null,
      "off_search_query": null,
      "match_source": "rule"
    }}
  ]
}}</code></pre>
            <div class="sub" style="font-size:0.8rem; margin-top:8px;">
              <b>CSV Export Columns:</b> <code>date, store, raw_name, clean_name, category, subcategory, quantity, unit, unit_price, total_price, currency</code>
            </div>
          </div>
          <div>
            <table class="schema-table">
              <thead>
                <tr><th>Field</th><th>Type</th><th>Description</th></tr>
              </thead>
              <tbody>
                <tr><td><code>store_name</code></td><td>string</td><td>Normalized store chain name (e.g. "Biedronka", "Lidl", "Żabka").</td></tr>
                <tr><td><code>transaction_date</code></td><td>string</td><td>Purchase date strictly formatted as <code>YYYY-MM-DD</code>.</td></tr>
                <tr><td><code>total_amount</code></td><td>float</td><td>Final total amount paid on the receipt.</td></tr>
                <tr><td><code>currency</code></td><td>string</td><td>Three-letter currency code (e.g. "PLN", "EUR").</td></tr>
                <tr><td><code>cache_hits</code></td><td>int</td><td>Items matched directly from catalog cache (skipping Stage 2 LLM).</td></tr>
                <tr><td><code>items[].name</code></td><td>string</td><td>Exact original printed item text from the receipt.</td></tr>
                <tr><td><code>items[].clean_name</code></td><td>string</td><td>Generic clean product name in user's chosen language (<code>pl</code> or <code>en</code>).</td></tr>
                <tr><td><code>items[].category / subcategory</code></td><td>string | null</td><td>Codes from the shared Global Taxonomy (<code>null</code> for discounts).</td></tr>
                <tr><td><code>items[].unit</code></td><td>string</td><td>Normalized unit: <code>"pcs"</code>, <code>"kg"</code>, or <code>"l"</code>.</td></tr>
                <tr><td><code>items[].quantity / unit_price / total_price</code></td><td>float</td><td>Quantity, unit price, and total line price (negative for discounts).</td></tr>
                <tr><td><code>items[].product_id</code></td><td>int | null</td><td>Shared catalog product ID.</td></tr>
                <tr><td><code>items[].off_search_query</code></td><td>string | null</td><td>Decoded brand + specific product phrase for Open Food Facts lookup.</td></tr>
                <tr><td><code>items[].match_source</code></td><td>string</td><td><code>"cache"</code>, <code>"llm"</code>, <code>"rule"</code> (discounts), or <code>"user"</code>.</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- ================================================================== -->
  <!-- MODAL 1: EDIT PRODUCT                                              -->
  <!-- ================================================================== -->
  <div id="editProductModal" class="modal-backdrop">
    <div class="modal-box">
      <h3 id="editProdTitle">✏️ Edit Catalog Product</h3>
      <input type="hidden" id="editProdId" />
      <div class="row2">
        <div>
          <label>Clean Name (Polish)</label>
          <input type="text" id="editProdPl" />
        </div>
        <div>
          <label>Clean Name (English)</label>
          <input type="text" id="editProdEn" />
        </div>
      </div>
      <div class="row2">
        <div>
          <label>Subcategory</label>
          <select id="editProdSubcat"></select>
        </div>
        <div>
          <label>Default Unit</label>
          <select id="editProdUnit">
            <option value="pcs">pcs (szt.)</option>
            <option value="kg">kg</option>
            <option value="l">l</option>
          </select>
        </div>
      </div>
      <label>Status</label>
      <select id="editProdStatus">
        <option value="confirmed">confirmed</option>
        <option value="auto">auto</option>
      </select>
      <div id="editProdMsg" class="status-msg"></div>
      <div class="actions" style="margin-top:16px; justify-content:flex-end;">
        <button class="secondary" onclick="closeModal('editProductModal')">Cancel</button>
        <button onclick="saveEditedProduct()">💾 Save &amp; Confirm</button>
      </div>
    </div>
  </div>

  <!-- ================================================================== -->
  <!-- MODAL 2: MERGE DUPLICATE PRODUCT                                   -->
  <!-- ================================================================== -->
  <div id="mergeProductModal" class="modal-backdrop">
    <div class="modal-box">
      <h3>🔀 Merge Duplicate Product</h3>
      <div class="sub" id="mergeSourceDesc" style="margin-bottom:10px;"></div>
      <input type="hidden" id="mergeSourceId" />
      <input type="hidden" id="mergeTargetId" />

      <label>Search Canonical Target Product (all aliases &amp; receipts will move to it)</label>
      <input type="text" id="mergeSearchInput" placeholder="Type product name, e.g. jajka..."
             oninput="searchMergeCandidates()" />
      <div id="mergeCandidatesList" class="candidate-list"></div>
      <div id="mergeMsg" class="status-msg"></div>
      <div class="actions" style="margin-top:16px; justify-content:flex-end;">
        <button class="secondary" onclick="closeModal('mergeProductModal')">Cancel</button>
        <button onclick="executeProductMerge()">🔀 Merge Duplicate Now</button>
      </div>
    </div>
  </div>

  <!-- ================================================================== -->
  <!-- MODAL 3: EDIT OR ADD RECEIPT ALIAS                                 -->
  <!-- ================================================================== -->
  <div id="aliasModal" class="modal-backdrop">
    <div class="modal-box">
      <h3 id="aliasModalTitle">✏️ Edit Receipt Alias</h3>
      <input type="hidden" id="editAliasId" />
      <div class="row2">
        <div>
          <label>Store Chain</label>
          <select id="aliasModalStore"></select>
        </div>
        <div>
          <label>Raw Receipt Name *</label>
          <input type="text" id="aliasModalRawName" placeholder="e.g. JAJA MOJA KURKA M 10" />
        </div>
      </div>

      <label>Mapped Clean Product * (search &amp; click below)</label>
      <input type="hidden" id="aliasModalProductId" />
      <div id="aliasSelectedProductLabel" class="sub" style="margin-bottom:4px; color:var(--accent);"></div>
      <input type="text" id="aliasProductSearch" placeholder="Search clean product..."
             oninput="searchAliasProductCandidates()" />
      <div id="aliasProductCandidates" class="candidate-list" style="max-height:150px;"></div>

      <div class="row2">
        <div>
          <label>Brand (optional)</label>
          <input type="text" id="aliasModalBrand" placeholder="e.g. Moja Kurka" />
        </div>
        <div>
          <label>Open Food Facts Search Query</label>
          <input type="text" id="aliasModalOff" placeholder="e.g. Moja Kurka jaja M 10 szt" />
        </div>
      </div>
      <div class="row2">
        <div>
          <label>Pack Amount (optional)</label>
          <input type="number" step="any" id="aliasModalPackAmt" placeholder="e.g. 10 or 0.4" />
        </div>
        <div>
          <label>Pack Unit (optional)</label>
          <input type="text" id="aliasModalPackUnit" placeholder="pcs, g, kg, ml, l" />
        </div>
      </div>
      <div id="aliasModalMsg" class="status-msg"></div>
      <div class="actions" style="margin-top:16px; justify-content:flex-end;">
        <button class="secondary" onclick="closeModal('aliasModal')">Cancel</button>
        <button onclick="saveAliasModal()">💾 Save Confirmed Alias</button>
      </div>
    </div>
  </div>

  <script>
    let cachedBots = [];
    let cachedCategories = [];
    let cachedProducts = [];
    let cachedAliases = [];
    let cachedStores = [];
    let isAdmin = false;
    let currentMainTab = 'bots';
    let currentCatalogMode = 'products';
    let aliasFilterProductId = null;
    let prodDebounceTimer = null;
    let aliasDebounceTimer = null;

    function escHtml(val) {{
      if (val === null || val === undefined) return '';
      return String(val)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    }}

    function getAdminHeaders(extra = {{}}) {{
      const key = localStorage.getItem('ocr_admin_key') || '';
      const headers = {{ ...extra }};
      if (key) headers['X-Admin-Key'] = key;
      return headers;
    }}

    function switchMainTab(tab) {{
      currentMainTab = tab;
      ['bots', 'catalog', 'taxonomy', 'schema'].forEach(t => {{
        document.getElementById(`nav-${{t}}`).classList.toggle('active', t === tab);
        document.getElementById(`panel-${{t}}`).classList.toggle('active', t === tab);
      }});
      if (tab === 'catalog') {{
        refreshCatalogAll();
      }}
    }}

    function switchCatalogMode(mode) {{
      currentCatalogMode = mode;
      ['products', 'auto_review', 'manual_user', 'aliases'].forEach(m => {{
        document.getElementById(`subtab-${{m}}`).classList.toggle('active', m === mode);
      }});
      document.getElementById('catViewProducts').style.display =
        (mode === 'products' || mode === 'auto_review') ? 'block' : 'none';
      document.getElementById('catViewManual').style.display =
        mode === 'manual_user' ? 'block' : 'none';
      document.getElementById('catViewAliases').style.display =
        mode === 'aliases' ? 'block' : 'none';

      document.getElementById('autoReviewBanner').style.display =
        mode === 'auto_review' ? 'block' : 'none';
      document.getElementById('prodStatusFilterBox').style.display =
        mode === 'auto_review' ? 'none' : 'block';

      if (mode === 'products' || mode === 'auto_review') {{
        loadCatalogProducts();
      }} else if (mode === 'manual_user') {{
        loadManualUserQueue();
      }} else if (mode === 'aliases') {{
        loadCatalogAliases();
      }}
    }}

    function closeModal(id) {{
      document.getElementById(id).classList.remove('open');
    }}

    async function refreshAdminStatus() {{
      const badge = document.getElementById('adminStatusBadge');
      try {{
        const res = await fetch('/api/admin/status', {{ headers: getAdminHeaders() }});
        const data = await res.json();
        isAdmin = Boolean(data.is_admin);
        if (isAdmin) {{
          badge.className = 'badge ok';
          badge.innerText = '🟢 Admin Unlocked';
        }} else if (!data.admin_key_configured) {{
          badge.className = 'badge off';
          badge.innerText = '🔒 Set ADMIN_API_KEY in .env for Admin Edits';
        }} else {{
          badge.className = 'badge off';
          badge.innerText = '🔒 Guest Mode';
        }}
      }} catch (e) {{
        isAdmin = false;
      }}
    }}

    async function saveAdminKey() {{
      const val = document.getElementById('adminKeyInput').value.trim();
      localStorage.setItem('ocr_admin_key', val);
      await refreshAdminStatus();
      await loadBots();
      await loadTaxonomy();
      await refreshCatalogAll();
    }}

    // =========================================================================
    // BOTS & TESTER
    // =========================================================================

    async function loadBots() {{
      const res = await fetch('/api/bots', {{ headers: getAdminHeaders() }});
      if (!res.ok) {{
        document.getElementById('botsList').innerHTML =
          '<div class="sub">⚠️ Enter valid Admin Key in the top-right corner to manage bots.</div>';
        return;
      }}
      cachedBots = await res.json();
      const container = document.getElementById('botsList');
      if (!cachedBots.length) {{
        container.innerHTML = '<div class="sub">No users/bots registered yet. Add one using the form above!</div>';
        return;
      }}
      const testKeyInput = document.getElementById('testApiKey');
      if (!testKeyInput.value && cachedBots[0]) {{
        testKeyInput.value = cachedBots[0].api_key;
      }}
      container.innerHTML = cachedBots.map(b => `
        <div class="bot-item">
          <div class="bot-header">
            <div>
              <strong>#${{b.id}} ${{escHtml(b.name)}}</strong>
              <span class="badge ${{b.bot_running ? 'ok' : 'off'}}">
                ${{b.bot_running ? '🟢 Telegram Bot Running' : (b.has_telegram_bot ? '🟡 Bot Stopped' : '🔌 API Only')}}
              </span>
            </div>
            <div class="actions">
              <button class="secondary" onclick="useKey('${{escHtml(b.api_key)}}')">Use in Tester</button>
              <button class="secondary" onclick="testWebhook(${{b.id}})">Ping Webhook</button>
              <button class="secondary" onclick="editBot(${{b.id}})">Edit</button>
              <button class="danger" onclick="deleteBot(${{b.id}})">Delete</button>
            </div>
          </div>
          <div class="sub" style="margin-top: 8px;">
            <div>🔑 API Key: <code>${{escHtml(b.api_key)}}</code></div>
            <div>🌐 Language: <code>${{escHtml(b.language || 'pl')}}</code> | 💰 Currency: <code>${{escHtml(b.default_currency || 'PLN')}}</code> | 💬 Allowed Chats: <code>${{(b.allowed_chat_ids && b.allowed_chat_ids.length) ? b.allowed_chat_ids.join(', ') : 'Any'}}</code></div>
            <div>📤 Delivery Modes: ${{(b.delivery_modes && b.delivery_modes.length) ? b.delivery_modes.map(m => `<code>${{escHtml(m)}}</code>`).join(' ') : '<code>none (catalog only)</code>'}}</div>
            <div>🔗 Destination Webhook: <code>${{escHtml(b.webhook_url || 'Not configured')}}</code></div>
          </div>
        </div>
      `).join('');
    }}

    function useKey(key) {{
      document.getElementById('testApiKey').value = key;
    }}

    function setDeliveryModeCheckboxes(modes) {{
      const set = new Set(modes || []);
      document.getElementById('modeHubDb').checked = set.has('hub_db');
      document.getElementById('modeWebhook').checked = set.has('webhook');
      document.getElementById('modeTgText').checked = set.has('telegram_text');
      document.getElementById('modeTgCsv').checked = set.has('telegram_csv');
    }}

    function collectDeliveryModes() {{
      const modes = [];
      if (document.getElementById('modeHubDb').checked) modes.push('hub_db');
      if (document.getElementById('modeWebhook').checked) modes.push('webhook');
      if (document.getElementById('modeTgText').checked) modes.push('telegram_text');
      if (document.getElementById('modeTgCsv').checked) modes.push('telegram_csv');
      return modes;
    }}

    function editBot(id) {{
      const b = cachedBots.find(x => x.id === id);
      if (!b) return;
      document.getElementById('formTitle').innerText = `✏️ Edit User / Bot #${{b.id}} (${{b.name}})`;
      document.getElementById('editBotId').value = b.id;
      document.getElementById('botName').value = b.name;
      document.getElementById('botCurrency').value = b.default_currency || 'PLN';
      document.getElementById('botLanguage').value = (b.language === 'en' ? 'en' : 'pl');
      document.getElementById('botToken').value = '';
      document.getElementById('botToken').placeholder = b.has_telegram_bot ? '(Leave empty to keep existing bot token)' : 'Paste @BotFather token';
      document.getElementById('allowedChatIds').value = (b.allowed_chat_ids || []).join(', ');
      document.getElementById('webhookUrl').value = b.webhook_url || '';
      document.getElementById('webhookSecret').value = '';
      setDeliveryModeCheckboxes(b.delivery_modes || ['webhook']);
      window.scrollTo({{ top: 0, behavior: 'smooth' }});
    }}

    function resetForm() {{
      document.getElementById('formTitle').innerText = '➕ Add or Update Bot / User';
      document.getElementById('editBotId').value = '';
      document.getElementById('botName').value = '';
      document.getElementById('botCurrency').value = 'PLN';
      document.getElementById('botLanguage').value = 'pl';
      document.getElementById('botToken').value = '';
      document.getElementById('botToken').placeholder = '123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ';
      document.getElementById('allowedChatIds').value = '';
      document.getElementById('webhookUrl').value = '';
      document.getElementById('webhookSecret').value = '';
      setDeliveryModeCheckboxes(['hub_db', 'webhook']);
      document.getElementById('formStatus').innerText = '';
    }}

    async function saveBot() {{
      const editId = document.getElementById('editBotId').value;
      const chatIds = document.getElementById('allowedChatIds').value
        .split(',')
        .map(s => s.trim())
        .filter(s => /^-?\\d+$/.test(s))
        .map(s => parseInt(s, 10));

      const payload = {{
        name: document.getElementById('botName').value.trim(),
        default_currency: document.getElementById('botCurrency').value.trim() || 'PLN',
        language: document.getElementById('botLanguage').value || 'pl',
        delivery_modes: collectDeliveryModes(),
        allowed_chat_ids: chatIds,
        webhook_url: document.getElementById('webhookUrl').value.trim() || null,
      }};

      const tokenVal = document.getElementById('botToken').value.trim();
      if (tokenVal || !editId) payload.telegram_bot_token = tokenVal || null;

      const secretVal = document.getElementById('webhookSecret').value.trim();
      if (secretVal || !editId) payload.webhook_secret = secretVal || null;

      const statusEl = document.getElementById('formStatus');
      statusEl.innerText = 'Saving...';

      const url = editId ? `/api/bots/${{editId}}` : '/api/bots';
      const method = editId ? 'PUT' : 'POST';
      const res = await fetch(url, {{
        method,
        headers: getAdminHeaders({{ 'Content-Type': 'application/json' }}),
        body: JSON.stringify(payload),
      }});
      const data = await res.json();
      if (!res.ok) {{
        statusEl.innerText = '❌ Error: ' + (data.detail || JSON.stringify(data));
        return;
      }}
      statusEl.innerText = `✅ Saved '${{data.name}}'! API Key: ${{data.api_key}}`;
      resetForm();
      await loadBots();
    }}

    async function deleteBot(id) {{
      if (!confirm(`Delete bot #${{id}}?`)) return;
      await fetch(`/api/bots/${{id}}`, {{
        method: 'DELETE',
        headers: getAdminHeaders(),
      }});
      await loadBots();
    }}

    async function testWebhook(id) {{
      const res = await fetch(`/api/bots/${{id}}/test-webhook`, {{
        method: 'POST',
        headers: getAdminHeaders(),
      }});
      const data = await res.json();
      alert(data.ok
        ? `✅ Webhook OK (HTTP ${{data.status_code}}): ${{data.detail}}`
        : `❌ Webhook Failed: ${{data.detail}}`
      );
    }}

    async function runOcrTest() {{
      const apiKey = document.getElementById('testApiKey').value.trim();
      const fileInput = document.getElementById('testFile');
      const sendWebhook = document.getElementById('testSendWebhook').checked;
      const saveHubDb = document.getElementById('testSaveHubDb').checked;
      const statusEl = document.getElementById('ocrStatus');
      const outEl = document.getElementById('ocrOutput');

      if (!apiKey) {{ statusEl.innerText = '❌ Enter or select an API key first.'; return; }}
      if (!fileInput.files.length) {{ statusEl.innerText = '❌ Choose a receipt image first.'; return; }}

      const formData = new FormData();
      formData.append('file', fileInput.files[0]);
      formData.append('forward_to_webhook', sendWebhook ? 'true' : 'false');
      formData.append('save_to_hub_db', saveHubDb ? 'true' : 'false');

      statusEl.innerText = '⏳ Running Stage 1 (Vision OCR) -> Cache Lookup -> Stage 2 (Classifier)...';
      outEl.innerText = '';

      const res = await fetch('/api/ocr', {{
        method: 'POST',
        headers: {{ 'X-API-Key': apiKey }},
        body: formData,
      }});
      const data = await res.json();
      statusEl.innerText = res.ok ? '✅ Completed!' : `❌ Error (HTTP ${{res.status}})`;
      outEl.innerText = JSON.stringify(data, null, 2);
      if (res.ok) loadCatalogStats();
    }}

    // =========================================================================
    // TAXONOMY (CATEGORIES & SUBCATEGORIES)
    // =========================================================================

    function populateSubcategoryDropdowns() {{
      const activeSubs = [];
      for (const cat of cachedCategories) {{
        if (!cat.is_active || cat.status === 'pending') continue;
        for (const sub of (cat.subcategories || [])) {{
          if (sub.is_active && sub.status !== 'pending') {{
            activeSubs.push({{ code: sub.code, label: `${{cat.code}} / ${{sub.code}} (${{sub.name_pl}} · ${{sub.name_en}})` }});
          }}
        }}
      }}
      const optsHtml = activeSubs.map(s => `<option value="${{escHtml(s.code)}}">${{escHtml(s.label)}}</option>`).join('');
      const newProdSelect = document.getElementById('newProdSubcat');
      const editProdSelect = document.getElementById('editProdSubcat');
      const filterSubSelect = document.getElementById('prodFilterSubcat');
      if (newProdSelect) newProdSelect.innerHTML = optsHtml;
      if (editProdSelect) editProdSelect.innerHTML = `<option value="">(None)</option>` + optsHtml;
      if (filterSubSelect) {{
        const cur = filterSubSelect.value;
        filterSubSelect.innerHTML = `<option value="">All Subcategories</option>` + optsHtml;
        filterSubSelect.value = cur;
      }}
    }}

    async function loadTaxonomy() {{
      const res = await fetch('/api/taxonomy?include_inactive=true', {{ headers: getAdminHeaders() }});
      const data = await res.json();
      isAdmin = Boolean(data.is_admin);
      cachedCategories = data.categories || [];
      populateSubcategoryDropdowns();

      const parentSelect = document.getElementById('newSubCatParent');
      parentSelect.innerHTML = cachedCategories
        .filter(c => c.status !== 'pending' || isAdmin)
        .map(c => `<option value="${{c.id}}">${{escHtml(c.code)}} (${{escHtml(c.name_pl)}} / ${{escHtml(c.name_en)}})</option>`)
        .join('');

      const container = document.getElementById('taxonomyContainer');
      if (!cachedCategories.length) {{
        container.innerHTML = '<div class="sub">No categories defined.</div>';
        return;
      }}

      container.innerHTML = cachedCategories.map(cat => {{
        const catPending = cat.status === 'pending';
        const catAdminActions = isAdmin ? `
          <div class="actions">
            ${{catPending ? `<button class="success small" onclick="approveCategory(${{cat.id}})">✅ Approve</button>` : ''}}
            <button class="secondary small" onclick="renameCategory(${{cat.id}})">Edit Names</button>
            <button class="secondary small" onclick="toggleCategory(${{cat.id}}, ${{!cat.is_active}})">
              ${{cat.is_active ? 'Disable' : 'Enable'}}
            </button>
            <button class="danger small" onclick="removeCategory(${{cat.id}}, '${{escHtml(cat.code)}}')">Delete</button>
          </div>
        ` : '';

        return `
          <div class="cat-box">
            <div class="bot-header">
              <div>
                <strong><code>${{escHtml(cat.code)}}</code> — PL: ${{escHtml(cat.name_pl)}} | EN: ${{escHtml(cat.name_en)}}</strong>
                <span class="badge ${{cat.is_active && !catPending ? 'ok' : (catPending ? 'warn' : 'off')}}">
                  ${{catPending ? '⏳ manual_user pending' : (cat.is_active ? 'Active' : 'Inactive')}}
                </span>
              </div>
              ${{catAdminActions}}
            </div>
            <div class="subcat-grid">
              ${{(cat.subcategories || []).map(sub => {{
                const subPending = sub.status === 'pending';
                const subAdminBtns = isAdmin ? `
                  ${{subPending ? `<button class="success small" title="Approve manual_user suggestion" onclick="approveSubcategory(${{sub.id}})">✅</button>` : ''}}
                  <button class="secondary small" title="Edit PL/EN names" onclick="renameSubcategory(${{sub.id}})">✏️</button>
                  <button class="secondary small" title="Toggle active" onclick="toggleSubcategory(${{sub.id}}, ${{!sub.is_active}})">
                    ${{sub.is_active ? '⏸' : '▶️'}}
                  </button>
                  <button class="danger small" title="Delete subcategory" onclick="removeSubcategory(${{sub.id}}, '${{escHtml(sub.code)}}')">✕</button>
                ` : '';
                return `
                  <div class="subcat-chip ${{(sub.is_active && !subPending) ? '' : 'inactive'}}">
                    <span>
                      <code>${{escHtml(sub.code)}}</code> · <b>PL:</b> ${{escHtml(sub.name_pl)}} · <b>EN:</b> ${{escHtml(sub.name_en)}}
                      ${{subPending ? ' <i>(⏳ manual_user)</i>' : ''}}
                    </span>
                    ${{subAdminBtns}}
                  </div>
                `;
              }}).join('') || '<span class="sub">No subcategories in this category.</span>'}}
            </div>
          </div>
        `;
      }}).join('');
    }}

    async function approveCategory(catId) {{
      const res = await fetch(`/api/taxonomy/categories/${{catId}}/approve`, {{
        method: 'POST',
        headers: getAdminHeaders(),
      }});
      if (res.ok) {{
        await loadTaxonomy();
        await refreshCatalogAll();
      }}
    }}

    async function approveSubcategory(subId) {{
      const res = await fetch(`/api/taxonomy/subcategories/${{subId}}/approve`, {{
        method: 'POST',
        headers: getAdminHeaders(),
      }});
      if (res.ok) {{
        await loadTaxonomy();
        await refreshCatalogAll();
      }}
    }}

    async function addCategory() {{
      const code = document.getElementById('newCatCode').value.trim();
      const name_pl = document.getElementById('newCatPl').value.trim();
      const name_en = document.getElementById('newCatEn').value.trim();
      const statusEl = document.getElementById('taxStatus');
      if (!code || !name_pl || !name_en) {{
        statusEl.innerText = '❌ Fill in category code, Polish name, and English name.';
        return;
      }}
      const res = await fetch('/api/taxonomy/categories', {{
        method: 'POST',
        headers: getAdminHeaders({{ 'Content-Type': 'application/json' }}),
        body: JSON.stringify({{ code, name_pl, name_en }}),
      }});
      const data = await res.json();
      if (!res.ok) {{
        statusEl.innerText = '❌ Error: ' + (data.detail || JSON.stringify(data));
        return;
      }}
      document.getElementById('newCatCode').value = '';
      document.getElementById('newCatPl').value = '';
      document.getElementById('newCatEn').value = '';
      statusEl.innerText = data.status === 'pending'
        ? `⏳ Submitted '${{data.code}}' (manual_user) — queued in Catalog -> Manual User Queue until Admin approves.`
        : `✅ Added active category ${{data.code}}`;
      await loadTaxonomy();
      await loadCatalogStats();
    }}

    async function renameCategory(catId) {{
      const cat = cachedCategories.find(c => c.id === catId);
      if (!cat) return;
      const name_pl = prompt(`Polish name for category ${{cat.code}}:`, cat.name_pl);
      if (name_pl === null) return;
      const name_en = prompt(`English name for category ${{cat.code}}:`, cat.name_en);
      if (name_en === null) return;
      const res = await fetch(`/api/taxonomy/categories/${{catId}}`, {{
        method: 'PUT',
        headers: getAdminHeaders({{ 'Content-Type': 'application/json' }}),
        body: JSON.stringify({{ name_pl, name_en }}),
      }});
      if (res.ok) await loadTaxonomy();
    }}

    async function toggleCategory(catId, isActive) {{
      await fetch(`/api/taxonomy/categories/${{catId}}`, {{
        method: 'PUT',
        headers: getAdminHeaders({{ 'Content-Type': 'application/json' }}),
        body: JSON.stringify({{ is_active: isActive }}),
      }});
      await loadTaxonomy();
    }}

    async function removeCategory(catId, code) {{
      if (!confirm(`Delete category '${{code}}' and all its subcategories?`)) return;
      await fetch(`/api/taxonomy/categories/${{catId}}`, {{
        method: 'DELETE',
        headers: getAdminHeaders(),
      }});
      await loadTaxonomy();
      await refreshCatalogAll();
    }}

    async function addSubcategory() {{
      const category_id = parseInt(document.getElementById('newSubCatParent').value, 10);
      const code = document.getElementById('newSubCode').value.trim();
      const name_pl = document.getElementById('newSubPl').value.trim();
      const name_en = document.getElementById('newSubEn').value.trim();
      const statusEl = document.getElementById('taxStatus');
      if (!category_id || !code || !name_pl || !name_en) {{
        statusEl.innerText = '❌ Fill in parent category, subcategory code, Polish name, and English name.';
        return;
      }}
      const res = await fetch('/api/taxonomy/subcategories', {{
        method: 'POST',
        headers: getAdminHeaders({{ 'Content-Type': 'application/json' }}),
        body: JSON.stringify({{ category_id, code, name_pl, name_en }}),
      }});
      const data = await res.json();
      if (!res.ok) {{
        statusEl.innerText = '❌ Error: ' + (data.detail || JSON.stringify(data));
        return;
      }}
      document.getElementById('newSubCode').value = '';
      document.getElementById('newSubPl').value = '';
      document.getElementById('newSubEn').value = '';
      statusEl.innerText = data.status === 'pending'
        ? `⏳ Submitted '${{data.code}}' (manual_user) — queued in Catalog -> Manual User Queue until Admin approves.`
        : `✅ Added active subcategory ${{data.code}}`;
      await loadTaxonomy();
      await loadCatalogStats();
    }}

    async function renameSubcategory(subId) {{
      let target = null;
      for (const c of cachedCategories) {{
        const found = (c.subcategories || []).find(s => s.id === subId);
        if (found) {{ target = found; break; }}
      }}
      if (!target) return;
      const name_pl = prompt(`Polish name for subcategory '${{target.code}}':`, target.name_pl);
      if (name_pl === null) return;
      const name_en = prompt(`English name for subcategory '${{target.code}}':`, target.name_en);
      if (name_en === null) return;
      const res = await fetch(`/api/taxonomy/subcategories/${{subId}}`, {{
        method: 'PUT',
        headers: getAdminHeaders({{ 'Content-Type': 'application/json' }}),
        body: JSON.stringify({{ name_pl, name_en }}),
      }});
      if (res.ok) await loadTaxonomy();
    }}

    async function toggleSubcategory(subId, isActive) {{
      await fetch(`/api/taxonomy/subcategories/${{subId}}`, {{
        method: 'PUT',
        headers: getAdminHeaders({{ 'Content-Type': 'application/json' }}),
        body: JSON.stringify({{ is_active: isActive }}),
      }});
      await loadTaxonomy();
    }}

    async function removeSubcategory(subId, code) {{
      if (!confirm(`Delete subcategory '${{code}}'?`)) return;
      await fetch(`/api/taxonomy/subcategories/${{subId}}`, {{
        method: 'DELETE',
        headers: getAdminHeaders(),
      }});
      await loadTaxonomy();
      await refreshCatalogAll();
    }}

    // =========================================================================
    // PHASE 5: PRODUCT CATALOG, ALIASES, MERGE & MANUAL USER QUEUE
    // =========================================================================

    async function loadCatalogStats() {{
      try {{
        const res = await fetch('/api/catalog/stats');
        if (!res.ok) return;
        const s = await res.json();
        document.getElementById('kpiProductsActive').innerText = s.products_active ?? 0;
        document.getElementById('kpiProductsSub').innerText =
          `${{s.products_confirmed ?? 0}} confirmed · ${{s.products_auto ?? 0}} auto (LLM)`;
        document.getElementById('kpiAliasesTotal').innerText = s.aliases_total ?? 0;
        document.getElementById('kpiAliasesSub').innerText =
          `${{s.aliases_confirmed ?? 0}} confirmed · ${{s.aliases_auto ?? 0}} auto across ${{s.stores_total ?? 0}} stores`;
        document.getElementById('kpiHitRate').innerText = `${{s.cache_hit_rate_pct ?? 0}}%`;
        document.getElementById('kpiHitsSub').innerText =
          `${{s.repeat_cache_hits ?? 0}} Stage 2 calls saved (${{s.total_alias_hits ?? 0}} total hits)`;
        document.getElementById('kpiManualPending').innerText = s.manual_user_pending_total ?? 0;
        document.getElementById('kpiManualSub').innerText =
          `${{s.pending_taxonomy_count ?? 0}} taxonomy · ${{s.products_pending ?? 0}} products pending`;

        document.getElementById('badgeAutoCount').innerText = s.products_auto ?? 0;
        document.getElementById('badgeManualCount').innerText = s.manual_user_pending_total ?? 0;

        const navBadge = document.getElementById('catalogNavBadge');
        const manualCount = s.manual_user_pending_total ?? 0;
        if (manualCount > 0) {{
          navBadge.style.display = 'inline-block';
          navBadge.innerText = manualCount;
        }} else {{
          navBadge.style.display = 'none';
        }}
      }} catch (e) {{}}
    }}

    async function loadCatalogStores() {{
      try {{
        const res = await fetch('/api/catalog/stores');
        if (!res.ok) return;
        const data = await res.json();
        cachedStores = data.stores || [];
        const filterSel = document.getElementById('aliasFilterStore');
        const curVal = filterSel.value;
        filterSel.innerHTML = `<option value="">All Stores</option>` +
          cachedStores.map(st => `<option value="${{st.id}}">${{escHtml(st.display_name)}}</option>`).join('');
        filterSel.value = curVal;

        const modalSel = document.getElementById('aliasModalStore');
        modalSel.innerHTML = `<option value="">Global (any store)</option>` +
          cachedStores.map(st => `<option value="${{st.id}}">${{escHtml(st.display_name)}}</option>`).join('');
      }} catch (e) {{}}
    }}

    async function refreshCatalogAll() {{
      await loadCatalogStats();
      await loadCatalogStores();
      if (currentCatalogMode === 'products' || currentCatalogMode === 'auto_review') {{
        await loadCatalogProducts();
      }} else if (currentCatalogMode === 'manual_user') {{
        await loadManualUserQueue();
      }} else if (currentCatalogMode === 'aliases') {{
        await loadCatalogAliases();
      }}
    }}

    function debouncedLoadProducts() {{
      clearTimeout(prodDebounceTimer);
      prodDebounceTimer = setTimeout(() => loadCatalogProducts(), 200);
    }}

    function debouncedLoadAliases() {{
      clearTimeout(aliasDebounceTimer);
      aliasDebounceTimer = setTimeout(() => loadCatalogAliases(), 200);
    }}

    async function loadCatalogProducts() {{
      const q = document.getElementById('prodSearchInput').value.trim();
      const sub = document.getElementById('prodFilterSubcat').value;
      const status = currentCatalogMode === 'auto_review'
        ? 'auto'
        : document.getElementById('prodFilterStatus').value;

      const params = new URLSearchParams();
      if (q) params.set('q', q);
      if (sub) params.set('subcategory', sub);
      if (status) params.set('status', status);
      params.set('limit', '150');

      const res = await fetch(`/api/catalog/products?${{params.toString()}}`, {{
        headers: getAdminHeaders(),
      }});
      const data = await res.json();
      cachedProducts = data.products || [];
      const container = document.getElementById('productsTableContainer');

      if (!cachedProducts.length) {{
        container.innerHTML = '<div class="sub" style="padding:12px 0;">No matching products found.</div>';
        return;
      }}

      container.innerHTML = `
        <table class="catalog-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Polish Name (PL)</th>
              <th>English Name (EN)</th>
              <th>Category / Subcategory</th>
              <th>Unit</th>
              <th>Aliases &amp; Cache Hits</th>
              <th>Status</th>
              ${{isAdmin ? '<th>Admin Actions</th>' : ''}}
            </tr>
          </thead>
          <tbody>
            ${{cachedProducts.map(p => {{
              const isAuto = p.status === 'auto';
              const badgeCls = p.status === 'confirmed' ? 'ok' : (isAuto ? 'auto' : 'warn');
              const taxLabel = p.subcategory_code
                ? `<code>${{escHtml(p.category_code || '—')}}</code> &rarr; <code>${{escHtml(p.subcategory_code)}}</code>`
                : '<span class="sub">Uncategorized</span>';
              const adminBtns = isAdmin ? `
                <td>
                  <div class="actions" style="margin-top:0;">
                    ${{isAuto ? `<button class="success small" onclick="approveProduct(${{p.id}})">✅ Confirm</button>` : ''}}
                    <button class="secondary small" onclick="openEditProductModal(${{p.id}})">✏️ Edit</button>
                    <button class="secondary small" onclick="openMergeProductModal(${{p.id}})">🔀 Merge</button>
                    <button class="danger small" onclick="deleteProduct(${{p.id}})">🗑️</button>
                  </div>
                </td>
              ` : '';
              return `
                <tr>
                  <td><code>#${{p.id}}</code></td>
                  <td><strong>${{escHtml(p.name_pl)}}</strong></td>
                  <td>${{escHtml(p.name_en)}}</td>
                  <td>${{taxLabel}}</td>
                  <td><code>${{escHtml(p.default_unit || 'pcs')}}</code></td>
                  <td>
                    <button class="link-btn" onclick="jumpToProductAliases(${{p.id}})">
                      ${{p.alias_count ?? 0}} alias(es) · ${{p.total_hits ?? 0}} hit(s)
                    </button>
                  </td>
                  <td><span class="badge ${{badgeCls}}">${{escHtml(p.status)}} (${{escHtml(p.source || 'llm')}})</span></td>
                  ${{adminBtns}}
                </tr>
              `;
            }}).join('')}}
          </tbody>
        </table>
      `;
    }}

    async function addCatalogProduct() {{
      const name_pl = document.getElementById('newProdPl').value.trim();
      const name_en = document.getElementById('newProdEn').value.trim();
      const subcategory_code = document.getElementById('newProdSubcat').value || null;
      const default_unit = document.getElementById('newProdUnit').value || 'pcs';
      const statusEl = document.getElementById('prodAddStatus');

      if (!name_pl || !name_en) {{
        statusEl.innerText = '❌ Provide both Polish and English clean product names.';
        return;
      }}
      const res = await fetch('/api/catalog/products', {{
        method: 'POST',
        headers: getAdminHeaders({{ 'Content-Type': 'application/json' }}),
        body: JSON.stringify({{ name_pl, name_en, subcategory_code, default_unit }}),
      }});
      const data = await res.json();
      if (!res.ok) {{
        statusEl.innerText = '❌ Error: ' + (data.detail || JSON.stringify(data));
        return;
      }}
      document.getElementById('newProdPl').value = '';
      document.getElementById('newProdEn').value = '';
      statusEl.innerText = data.status === 'pending'
        ? `⏳ Submitted '${{data.name_pl}}' to Manual User Queue — inactive until Admin approves.`
        : `✅ Added confirmed product #${{data.id}} (${{data.name_pl}} / ${{data.name_en}})!`;
      await refreshCatalogAll();
    }}

    async function approveProduct(productId) {{
      const res = await fetch(`/api/catalog/products/${{productId}}/approve`, {{
        method: 'POST',
        headers: getAdminHeaders(),
      }});
      if (res.ok) await refreshCatalogAll();
    }}

    async function deleteProduct(productId) {{
      const prod = cachedProducts.find(p => p.id === productId);
      const label = prod ? `#${{prod.id}} (${{prod.name_pl}})` : `#${{productId}}`;
      if (!confirm(`Delete product ${{label}} and its cached store aliases?`)) return;
      const res = await fetch(`/api/catalog/products/${{productId}}`, {{
        method: 'DELETE',
        headers: getAdminHeaders(),
      }});
      if (res.ok) await refreshCatalogAll();
    }}

    function openEditProductModal(productId) {{
      const prod = cachedProducts.find(p => p.id === productId);
      if (!prod) return;
      document.getElementById('editProdTitle').innerText = `✏️ Edit Product #${{prod.id}}`;
      document.getElementById('editProdId').value = prod.id;
      document.getElementById('editProdPl').value = prod.name_pl || '';
      document.getElementById('editProdEn').value = prod.name_en || '';
      document.getElementById('editProdSubcat').value = prod.subcategory_code || '';
      document.getElementById('editProdUnit').value = prod.default_unit || 'pcs';
      document.getElementById('editProdStatus').value =
        prod.status === 'auto' ? 'confirmed' : (prod.status === 'confirmed' ? 'confirmed' : 'confirmed');
      document.getElementById('editProdMsg').innerText = '';
      document.getElementById('editProductModal').classList.add('open');
    }}

    async function saveEditedProduct() {{
      const id = document.getElementById('editProdId').value;
      const payload = {{
        name_pl: document.getElementById('editProdPl').value.trim(),
        name_en: document.getElementById('editProdEn').value.trim(),
        subcategory_code: document.getElementById('editProdSubcat').value || null,
        default_unit: document.getElementById('editProdUnit').value,
        status: document.getElementById('editProdStatus').value,
      }};
      const msgEl = document.getElementById('editProdMsg');
      const res = await fetch(`/api/catalog/products/${{id}}`, {{
        method: 'PUT',
        headers: getAdminHeaders({{ 'Content-Type': 'application/json' }}),
        body: JSON.stringify(payload),
      }});
      const data = await res.json();
      if (!res.ok) {{
        msgEl.innerText = '❌ Error: ' + (data.detail || JSON.stringify(data));
        return;
      }}
      closeModal('editProductModal');
      await refreshCatalogAll();
    }}

    function openMergeProductModal(sourceId) {{
      const src = cachedProducts.find(p => p.id === sourceId);
      if (!src) return;
      document.getElementById('mergeSourceId').value = src.id;
      document.getElementById('mergeTargetId').value = '';
      document.getElementById('mergeSourceDesc').innerHTML =
        `Merging duplicate <b>#${{src.id}} ${{escHtml(src.name_pl)}} (${{escHtml(src.name_en)}})</b> into another product. ` +
        `All ${{src.alias_count ?? 0}} alias(es) and saved receipts will re-point to the target product, and #${{src.id}} will be removed.`;
      document.getElementById('mergeSearchInput').value = src.name_pl.split(' ')[0] || '';
      document.getElementById('mergeMsg').innerText = '';
      document.getElementById('mergeProductModal').classList.add('open');
      searchMergeCandidates();
    }}

    async function searchMergeCandidates() {{
      const sourceId = parseInt(document.getElementById('mergeSourceId').value, 10);
      const q = document.getElementById('mergeSearchInput').value.trim();
      const params = new URLSearchParams({{ limit: '25' }});
      if (q) params.set('q', q);
      const res = await fetch(`/api/catalog/products?${{params.toString()}}`, {{
        headers: getAdminHeaders(),
      }});
      const data = await res.json();
      const candidates = (data.products || []).filter(p => p.id !== sourceId && p.status !== 'pending');
      const selectedId = parseInt(document.getElementById('mergeTargetId').value || '0', 10);
      const listEl = document.getElementById('mergeCandidatesList');

      if (!candidates.length) {{
        listEl.innerHTML = '<div class="sub" style="padding:10px;">No other products match this search.</div>';
        return;
      }}
      listEl.innerHTML = candidates.map(c => `
        <div class="candidate-row ${{c.id === selectedId ? 'selected' : ''}}"
             onclick="selectMergeTarget(${{c.id}})">
          <div>
            <code>#${{c.id}}</code> <strong>${{escHtml(c.name_pl)}}</strong>
            <span class="sub">(${{escHtml(c.name_en)}}) · [${{escHtml(c.subcategory_code || '—')}}]</span>
          </div>
          <span class="badge ${{c.status === 'confirmed' ? 'ok' : 'auto'}}">${{c.total_hits ?? 0}} hits</span>
        </div>
      `).join('');
    }}

    function selectMergeTarget(targetId) {{
      document.getElementById('mergeTargetId').value = targetId;
      searchMergeCandidates();
    }}

    async function executeProductMerge() {{
      const sourceId = parseInt(document.getElementById('mergeSourceId').value, 10);
      const targetId = parseInt(document.getElementById('mergeTargetId').value || '0', 10);
      const msgEl = document.getElementById('mergeMsg');
      if (!targetId) {{
        msgEl.innerText = '❌ Click a target product from the list above first.';
        return;
      }}
      const res = await fetch(`/api/catalog/products/${{sourceId}}/merge`, {{
        method: 'POST',
        headers: getAdminHeaders({{ 'Content-Type': 'application/json' }}),
        body: JSON.stringify({{ target_product_id: targetId }}),
      }});
      const data = await res.json();
      if (!res.ok) {{
        msgEl.innerText = '❌ Error: ' + (data.detail || JSON.stringify(data));
        return;
      }}
      closeModal('mergeProductModal');
      await refreshCatalogAll();
    }}

    // =========================================================================
    // MANUAL USER QUEUE (PENDING CATEGORIES, SUBCATEGORIES, PRODUCTS)
    // =========================================================================

    async function loadManualUserQueue() {{
      const container = document.getElementById('manualQueueContainer');
      if (!isAdmin) {{
        container.innerHTML =
          '<div class="sub">🔒 Enter a valid Admin Key in the top-right corner to inspect and approve Manual User submissions.</div>';
        return;
      }}
      const res = await fetch('/api/catalog/manual-queue', {{ headers: getAdminHeaders() }});
      if (!res.ok) {{
        container.innerHTML = '<div class="sub">⚠️ Could not load manual user queue.</div>';
        return;
      }}
      const data = await res.json();
      const cats = data.categories || [];
      const subs = data.subcategories || [];
      const prods = data.products || [];

      if (!cats.length && !subs.length && !prods.length) {{
        container.innerHTML = '<div class="sub">🎉 Manual User Queue is empty — no pending items awaiting approval!</div>';
        return;
      }}

      let html = '';
      if (cats.length) {{
        html += `<h3>⏳ Pending Top-Level Categories (${{cats.length}})</h3><div class="table-wrap" style="margin-bottom:16px;"><table class="catalog-table">
          <thead><tr><th>Code</th><th>Polish Name</th><th>English Name</th><th>Actions</th></tr></thead><tbody>` +
          cats.map(c => `<tr>
            <td><code>${{escHtml(c.code)}}</code></td>
            <td>${{escHtml(c.name_pl)}}</td>
            <td>${{escHtml(c.name_en)}}</td>
            <td>
              <div class="actions" style="margin-top:0;">
                <button class="success small" onclick="approveCategory(${{c.id}})">✅ Approve</button>
                <button class="danger small" onclick="removeCategory(${{c.id}}, '${{escHtml(c.code)}}')">🗑️ Reject</button>
              </div>
            </td>
          </tr>`).join('') + `</tbody></table></div>`;
      }}

      if (subs.length) {{
        html += `<h3>⏳ Pending Subcategories (${{subs.length}})</h3><div class="table-wrap" style="margin-bottom:16px;"><table class="catalog-table">
          <thead><tr><th>Parent Category</th><th>Subcategory Code</th><th>Polish Name</th><th>English Name</th><th>Actions</th></tr></thead><tbody>` +
          subs.map(s => `<tr>
            <td><code>${{escHtml(s.category_code)}}</code></td>
            <td><code>${{escHtml(s.code)}}</code></td>
            <td>${{escHtml(s.name_pl)}}</td>
            <td>${{escHtml(s.name_en)}}</td>
            <td>
              <div class="actions" style="margin-top:0;">
                <button class="success small" onclick="approveSubcategory(${{s.id}})">✅ Approve</button>
                <button class="danger small" onclick="removeSubcategory(${{s.id}}, '${{escHtml(s.code)}}')">🗑️ Reject</button>
              </div>
            </td>
          </tr>`).join('') + `</tbody></table></div>`;
      }}

      if (prods.length) {{
        html += `<h3>⏳ Pending Manual Products (${{prods.length}})</h3><div class="table-wrap"><table class="catalog-table">
          <thead><tr><th>ID</th><th>Polish Name</th><th>English Name</th><th>Subcategory</th><th>Unit</th><th>Actions</th></tr></thead><tbody>` +
          prods.map(p => `<tr>
            <td><code>#${{p.id}}</code></td>
            <td><strong>${{escHtml(p.name_pl)}}</strong></td>
            <td>${{escHtml(p.name_en)}}</td>
            <td><code>${{escHtml(p.subcategory_code || '—')}}</code></td>
            <td><code>${{escHtml(p.default_unit || 'pcs')}}</code></td>
            <td>
              <div class="actions" style="margin-top:0;">
                <button class="success small" onclick="approveProduct(${{p.id}})">✅ Approve</button>
                <button class="danger small" onclick="rejectPendingProduct(${{p.id}})">🗑️ Reject</button>
              </div>
            </td>
          </tr>`).join('') + `</tbody></table></div>`;
      }}

      container.innerHTML = html;
    }}

    async function rejectPendingProduct(productId) {{
      if (!confirm(`Reject and delete pending manual_user product #${{productId}}?`)) return;
      const res = await fetch(`/api/catalog/products/${{productId}}`, {{
        method: 'DELETE',
        headers: getAdminHeaders(),
      }});
      if (res.ok) await refreshCatalogAll();
    }}

    // =========================================================================
    // RECEIPT ALIASES & OPEN FOOD FACTS QUERIES
    // =========================================================================

    function jumpToProductAliases(productId) {{
      aliasFilterProductId = productId;
      switchCatalogMode('aliases');
    }}

    function clearAliasProductFilter() {{
      aliasFilterProductId = null;
      loadCatalogAliases();
    }}

    async function loadCatalogAliases() {{
      const q = document.getElementById('aliasSearchInput').value.trim();
      const storeId = document.getElementById('aliasFilterStore').value;
      const status = document.getElementById('aliasFilterStatus').value;

      const chipEl = document.getElementById('aliasProductFilterChip');
      if (aliasFilterProductId) {{
        chipEl.innerHTML = `<span class="badge auto">Filtered to Product #${{aliasFilterProductId}}
          <button class="link-btn" style="margin-left:6px;" onclick="clearAliasProductFilter()">✕ Clear</button></span>`;
      }} else {{
        chipEl.innerHTML = '';
      }}

      document.getElementById('adminAddAliasBtnWrap').innerHTML = isAdmin
        ? `<button class="small" onclick="openAddAliasModal()">➕ Add / Override Alias</button>`
        : '';

      const params = new URLSearchParams({{ limit: '150' }});
      if (q) params.set('q', q);
      if (storeId) params.set('store_id', storeId);
      if (status) params.set('status', status);
      if (aliasFilterProductId) params.set('product_id', String(aliasFilterProductId));

      const res = await fetch(`/api/catalog/aliases?${{params.toString()}}`);
      const data = await res.json();
      cachedAliases = data.aliases || [];
      const container = document.getElementById('aliasesTableContainer');

      if (!cachedAliases.length) {{
        container.innerHTML = '<div class="sub" style="padding:12px 0;">No receipt aliases match the current filters.</div>';
        return;
      }}

      container.innerHTML = `
        <table class="catalog-table">
          <thead>
            <tr>
              <th>Store</th>
              <th>Raw Receipt Name</th>
              <th>Mapped Clean Product</th>
              <th>Brand &amp; Open Food Facts Query</th>
              <th>Hits</th>
              <th>Status</th>
              ${{isAdmin ? '<th>Admin Actions</th>' : ''}}
            </tr>
          </thead>
          <tbody>
            ${{cachedAliases.map(a => {{
              const isAuto = a.alias_status === 'auto';
              const storeLabel = a.store_display_name ? escHtml(a.store_display_name) : '<span class="sub">Global</span>';
              const offInfo = [
                a.brand ? `<b>Brand:</b> ${{escHtml(a.brand)}}` : '',
                a.off_search_query ? `<b>OFF:</b> <code>${{escHtml(a.off_search_query)}}</code>` : '',
                a.pack_amount ? `<b>Pack:</b> ${{a.pack_amount}} ${{escHtml(a.pack_unit || '')}}` : ''
              ].filter(Boolean).join('<br/>') || '<span class="sub">—</span>';

              const adminBtns = isAdmin ? `
                <td>
                  <div class="actions" style="margin-top:0;">
                    ${{isAuto ? `<button class="success small" onclick="approveAlias(${{a.alias_id}})">✅ Confirm</button>` : ''}}
                    <button class="secondary small" onclick="openEditAliasModal(${{a.alias_id}})">✏️ Edit</button>
                    <button class="danger small" onclick="deleteAlias(${{a.alias_id}})">🗑️</button>
                  </div>
                </td>
              ` : '';

              return `
                <tr>
                  <td>${{storeLabel}}</td>
                  <td><code>${{escHtml(a.raw_name_original)}}</code></td>
                  <td>
                    <code>#${{a.product_id}}</code> <strong>${{escHtml(a.name_pl)}}</strong>
                    <span class="sub">(${{escHtml(a.name_en)}}) [${{escHtml(a.subcategory_code || '—')}}]</span>
                  </td>
                  <td style="font-size:0.8rem;">${{offInfo}}</td>
                  <td><code>${{a.hit_count}}x</code></td>
                  <td>
                    <span class="badge ${{a.alias_status === 'confirmed' ? 'ok' : 'auto'}}">
                      ${{escHtml(a.alias_status)}} (${{escHtml(a.alias_source)}})
                    </span>
                  </td>
                  ${{adminBtns}}
                </tr>
              `;
            }}).join('')}}
          </tbody>
        </table>
      `;
    }}

    async function approveAlias(aliasId) {{
      const res = await fetch(`/api/catalog/aliases/${{aliasId}}/approve`, {{
        method: 'POST',
        headers: getAdminHeaders(),
      }});
      if (res.ok) await refreshCatalogAll();
    }}

    async function deleteAlias(aliasId) {{
      if (!confirm(`Delete cached receipt alias #${{aliasId}}?`)) return;
      const res = await fetch(`/api/catalog/aliases/${{aliasId}}`, {{
        method: 'DELETE',
        headers: getAdminHeaders(),
      }});
      if (res.ok) await refreshCatalogAll();
    }}

    function openAddAliasModal() {{
      document.getElementById('aliasModalTitle').innerText = '➕ Add / Override Receipt Alias';
      document.getElementById('editAliasId').value = '';
      document.getElementById('aliasModalStore').value = '';
      document.getElementById('aliasModalStore').disabled = false;
      document.getElementById('aliasModalRawName').value = '';
      document.getElementById('aliasModalRawName').disabled = false;
      document.getElementById('aliasModalProductId').value = '';
      document.getElementById('aliasSelectedProductLabel').innerText = 'No product selected yet';
      document.getElementById('aliasProductSearch').value = '';
      document.getElementById('aliasModalBrand').value = '';
      document.getElementById('aliasModalOff').value = '';
      document.getElementById('aliasModalPackAmt').value = '';
      document.getElementById('aliasModalPackUnit').value = '';
      document.getElementById('aliasModalMsg').innerText = '';
      document.getElementById('aliasModal').classList.add('open');
      searchAliasProductCandidates();
    }}

    function openEditAliasModal(aliasId) {{
      const a = cachedAliases.find(x => x.alias_id === aliasId);
      if (!a) return;
      document.getElementById('aliasModalTitle').innerText = `✏️ Edit Alias #${{a.alias_id}}`;
      document.getElementById('editAliasId').value = a.alias_id;
      document.getElementById('aliasModalStore').value = a.store_id ? String(a.store_id) : '';
      document.getElementById('aliasModalStore').disabled = true;
      document.getElementById('aliasModalRawName').value = a.raw_name_original || '';
      document.getElementById('aliasModalRawName').disabled = true;
      document.getElementById('aliasModalProductId').value = a.product_id;
      document.getElementById('aliasSelectedProductLabel').innerText =
        `Selected: #${{a.product_id}} ${{a.name_pl}} (${{a.name_en}})`;
      document.getElementById('aliasProductSearch').value = a.name_pl || '';
      document.getElementById('aliasModalBrand').value = a.brand || '';
      document.getElementById('aliasModalOff').value = a.off_search_query || '';
      document.getElementById('aliasModalPackAmt').value = a.pack_amount ?? '';
      document.getElementById('aliasModalPackUnit').value = a.pack_unit || '';
      document.getElementById('aliasModalMsg').innerText = '';
      document.getElementById('aliasModal').classList.add('open');
      searchAliasProductCandidates();
    }}

    async function searchAliasProductCandidates() {{
      const q = document.getElementById('aliasProductSearch').value.trim();
      const params = new URLSearchParams({{ limit: '20' }});
      if (q) params.set('q', q);
      const res = await fetch(`/api/catalog/products?${{params.toString()}}`, {{
        headers: getAdminHeaders(),
      }});
      const data = await res.json();
      const prods = (data.products || []).filter(p => p.status !== 'pending');
      const selectedPid = parseInt(document.getElementById('aliasModalProductId').value || '0', 10);
      const listEl = document.getElementById('aliasProductCandidates');

      if (!prods.length) {{
        listEl.innerHTML = '<div class="sub" style="padding:8px;">No matching active products.</div>';
        return;
      }}
      listEl.innerHTML = prods.map(p => `
        <div class="candidate-row ${{p.id === selectedPid ? 'selected' : ''}}"
             onclick="selectAliasTargetProduct(${{p.id}}, '${{escHtml(p.name_pl)}}', '${{escHtml(p.name_en)}}')">
          <div>
            <code>#${{p.id}}</code> <strong>${{escHtml(p.name_pl)}}</strong>
            <span class="sub">(${{escHtml(p.name_en)}}) [${{escHtml(p.subcategory_code || '—')}}]</span>
          </div>
          <span class="badge ${{p.status === 'confirmed' ? 'ok' : 'auto'}}">${{escHtml(p.status)}}</span>
        </div>
      `).join('');
    }}

    function selectAliasTargetProduct(pid, namePl, nameEn) {{
      document.getElementById('aliasModalProductId').value = pid;
      document.getElementById('aliasSelectedProductLabel').innerText =
        `Selected: #${{pid}} ${{namePl}} (${{nameEn}})`;
      searchAliasProductCandidates();
    }}

    async function saveAliasModal() {{
      const editAliasId = document.getElementById('editAliasId').value;
      const productId = parseInt(document.getElementById('aliasModalProductId').value || '0', 10);
      const storeVal = document.getElementById('aliasModalStore').value;
      const rawName = document.getElementById('aliasModalRawName').value.trim();
      const brand = document.getElementById('aliasModalBrand').value.trim() || null;
      const off_search_query = document.getElementById('aliasModalOff').value.trim() || null;
      const packRaw = document.getElementById('aliasModalPackAmt').value.trim();
      const pack_amount = packRaw ? parseFloat(packRaw) : null;
      const pack_unit = document.getElementById('aliasModalPackUnit').value.trim() || null;
      const msgEl = document.getElementById('aliasModalMsg');

      if (!productId) {{
        msgEl.innerText = '❌ Select a target clean product first.';
        return;
      }}

      let res;
      if (editAliasId) {{
        res = await fetch(`/api/catalog/aliases/${{editAliasId}}`, {{
          method: 'PUT',
          headers: getAdminHeaders({{ 'Content-Type': 'application/json' }}),
          body: JSON.stringify({{
            product_id: productId,
            brand,
            off_search_query,
            pack_amount,
            pack_unit,
            status: 'confirmed',
          }}),
        }});
      }} else {{
        if (!rawName) {{
          msgEl.innerText = '❌ Enter the raw receipt item name.';
          return;
        }}
        res = await fetch('/api/catalog/aliases', {{
          method: 'POST',
          headers: getAdminHeaders({{ 'Content-Type': 'application/json' }}),
          body: JSON.stringify({{
            raw_name: rawName,
            product_id: productId,
            store_id: storeVal ? parseInt(storeVal, 10) : null,
            brand,
            off_search_query,
            pack_amount,
            pack_unit,
          }}),
        }});
      }}
      const data = await res.json();
      if (!res.ok) {{
        msgEl.innerText = '❌ Error: ' + (data.detail || JSON.stringify(data));
        return;
      }}
      closeModal('aliasModal');
      await refreshCatalogAll();
    }}

    document.getElementById('adminKeyInput').value = localStorage.getItem('ocr_admin_key') || '';
    (async () => {{
      await refreshAdminStatus();
      await loadBots();
      await loadTaxonomy();
      await loadCatalogStats();
    }})();
  </script>
</body>
</html>
"""
