"""Built-in Web UI Dashboard for managing Telegram bots, global taxonomy, webhooks, and testing receipt OCR."""

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
      max-width: 1200px;
      margin: 0 auto;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 12px;
      margin-bottom: 24px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--border);
    }}
    h1 {{ margin: 0; font-size: 1.6rem; }}
    h2 {{ margin-top: 0; font-size: 1.2rem; }}
    h3 {{ margin: 0 0 8px 0; font-size: 1rem; }}
    .sub {{ color: var(--muted); font-size: 0.9rem; }}
    .grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 20px;
      margin-bottom: 24px;
    }}
    @media (max-width: 860px) {{
      .grid {{ grid-template-columns: 1fr; }}
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
      .row4, .row5 {{ grid-template-columns: 1fr; }}
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
      gap: 8px;
      flex-wrap: wrap;
      margin-top: 8px;
    }}
    .actions button {{ margin-top: 0; padding: 6px 11px; font-size: 0.8rem; }}
    .status-msg {{
      margin-top: 10px;
      font-size: 0.85rem;
      color: var(--accent);
    }}
    table.schema-table {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 10px;
      font-size: 0.84rem;
    }}
    table.schema-table th, table.schema-table td {{
      padding: 7px 10px;
      border: 1px solid var(--border);
      text-align: left;
    }}
    table.schema-table th {{
      background: #0b1120;
      color: var(--accent);
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

    <div class="grid">
      <!-- Left: Add / Edit Bot & Destination Form -->
      <div class="card">
        <h2 id="formTitle">➕ Add or Update Bot / User</h2>
        <div class="sub" style="margin-bottom: 8px;">
          Configure a user API key / Telegram bot. Product classification uses the shared Global Taxonomy below.
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

        <div class="actions" style="margin-top: 16px;">
          <button onclick="saveBot()">💾 Save User / Bot</button>
          <button class="secondary" onclick="resetForm()">Clear Form</button>
        </div>
        <div id="formStatus" class="status-msg"></div>
      </div>

      <!-- Right: Live 2-Stage OCR Tester -->
      <div class="card">
        <h2>🧪 Test Receipt OCR</h2>
        <div class="sub">Upload a receipt photo to test Stage 1 Vision OCR &rarr; Stage 2 Classification directly in the browser.</div>

        <label>API Key (select a user below or paste key)</label>
        <input type="text" id="testApiKey" placeholder="ocr_live_..." />

        <label>Receipt Photo (JPEG / PNG / WEBP)</label>
        <input type="file" id="testFile" accept="image/jpeg,image/png,image/webp" />

        <label style="display:flex; align-items:center; gap:8px; margin-top:12px;">
          <input type="checkbox" id="testSendWebhook" style="width:auto;" />
          Also forward final JSON to this user's Destination Webhook URL
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

    <!-- Global Categories & Subcategories (Taxonomy Verification & Management) -->
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

    <!-- Final JSON & CSV Output Structure Documentation -->
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
  "items": [
    {{
      "name": "JAJA MOJA KURKA M 10",
      "clean_name": "jajka",
      "subcategory": "eggs",
      "quantity": 1.0,
      "unit_price": 8.99,
      "total_price": 8.99
    }},
    {{
      "name": "MLEKO LACIATE 3,2% 1L",
      "clean_name": "mleko 3.2%",
      "subcategory": "dairy",
      "quantity": 3.0,
      "unit_price": 4.49,
      "total_price": 13.47
    }},
    {{
      "name": "RABAT MLEKO 3W2",
      "clean_name": "Rabat",
      "subcategory": null,
      "quantity": 1.0,
      "unit_price": -0.98,
      "total_price": -0.98
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
              <tr><td><code>items[].name</code></td><td>string</td><td>Exact original printed item text from the receipt.</td></tr>
              <tr><td><code>items[].clean_name</code></td><td>string</td><td>Generic clean product name in user's chosen language (<code>pl</code> or <code>en</code>).</td></tr>
              <tr><td><code>items[].subcategory</code></td><td>string | null</td><td>Code from the shared Global Taxonomy (or <code>null</code> for discounts).</td></tr>
              <tr><td><code>items[].quantity</code></td><td>float</td><td>Quantity or weight (default 1.0).</td></tr>
              <tr><td><code>items[].unit_price</code></td><td>float</td><td>Unit price (negative for discounts/rebates).</td></tr>
              <tr><td><code>items[].total_price</code></td><td>float</td><td>Total line price after quantity (negative for discounts).</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>

  <script>
    let cachedBots = [];
    let cachedCategories = [];
    let isAdmin = false;

    function getAdminHeaders(extra = {{}}) {{
      const key = localStorage.getItem('ocr_admin_key') || '';
      const headers = {{ ...extra }};
      if (key) headers['X-Admin-Key'] = key;
      return headers;
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
    }}

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
              <strong>#${{b.id}} ${{b.name}}</strong>
              <span class="badge ${{b.bot_running ? 'ok' : 'off'}}">
                ${{b.bot_running ? '🟢 Telegram Bot Running' : (b.has_telegram_bot ? '🟡 Bot Stopped' : '🔌 API Only')}}
              </span>
            </div>
            <div class="actions">
              <button class="secondary" onclick="useKey('${{b.api_key}}')">Use in Tester</button>
              <button class="secondary" onclick="testWebhook(${{b.id}})">Ping Webhook</button>
              <button class="secondary" onclick="editBot(${{b.id}})">Edit</button>
              <button class="danger" onclick="deleteBot(${{b.id}})">Delete</button>
            </div>
          </div>
          <div class="sub" style="margin-top: 8px;">
            <div>🔑 API Key: <code>${{b.api_key}}</code></div>
            <div>🌐 Language: <code>${{b.language || 'pl'}}</code> | 💰 Currency: <code>${{b.default_currency || 'PLN'}}</code> | 💬 Allowed Chats: <code>${{(b.allowed_chat_ids && b.allowed_chat_ids.length) ? b.allowed_chat_ids.join(', ') : 'Any'}}</code></div>
            <div>🔗 Destination Webhook: <code>${{b.webhook_url || 'Not configured'}}</code></div>
          </div>
        </div>
      `).join('');
    }}

    async function loadTaxonomy() {{
      const res = await fetch('/api/taxonomy?include_inactive=true', {{ headers: getAdminHeaders() }});
      const data = await res.json();
      isAdmin = Boolean(data.is_admin);
      cachedCategories = data.categories || [];

      const parentSelect = document.getElementById('newSubCatParent');
      parentSelect.innerHTML = cachedCategories
        .filter(c => c.status !== 'pending' || isAdmin)
        .map(c => `<option value="${{c.id}}">${{c.code}} (${{c.name_pl}} / ${{c.name_en}})</option>`)
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
            ${{catPending ? `<button class=" small" onclick="approveCategory(${{cat.id}})">✅ Approve</button>` : ''}}
            <button class="secondary small" onclick="renameCategory(${{cat.id}})">Edit Names</button>
            <button class="secondary small" onclick="toggleCategory(${{cat.id}}, ${{!cat.is_active}})">
              ${{cat.is_active ? 'Disable' : 'Enable'}}
            </button>
            <button class="danger small" onclick="removeCategory(${{cat.id}}, '${{cat.code}}')">Delete</button>
          </div>
        ` : '';

        return `
          <div class="cat-box">
            <div class="bot-header">
              <div>
                <strong><code>${{cat.code}}</code> — PL: ${{cat.name_pl}} | EN: ${{cat.name_en}}</strong>
                <span class="badge ${{cat.is_active && !catPending ? 'ok' : 'off'}}">
                  ${{catPending ? '⏳ manual_user pending' : (cat.is_active ? 'Active' : 'Inactive')}}
                </span>
              </div>
              ${{catAdminActions}}
            </div>
            <div class="subcat-grid">
              ${{(cat.subcategories || []).map(sub => {{
                const subPending = sub.status === 'pending';
                const subAdminBtns = isAdmin ? `
                  ${{subPending ? `<button class="small" title="Approve manual_user suggestion" onclick="approveSubcategory(${{sub.id}})">✅</button>` : ''}}
                  <button class="secondary small" title="Edit PL/EN names" onclick="renameSubcategory(${{sub.id}})">✏️</button>
                  <button class="secondary small" title="Toggle active" onclick="toggleSubcategory(${{sub.id}}, ${{!sub.is_active}})">
                    ${{sub.is_active ? '⏸' : '▶️'}}
                  </button>
                  <button class="danger small" title="Delete subcategory" onclick="removeSubcategory(${{sub.id}}, '${{sub.code}}')">✕</button>
                ` : '';
                return `
                  <div class="subcat-chip ${{(sub.is_active && !subPending) ? '' : 'inactive'}}">
                    <span>
                      <code>${{sub.code}}</code> · <b>PL:</b> ${{sub.name_pl}} · <b>EN:</b> ${{sub.name_en}}
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
      if (res.ok) await loadTaxonomy();
    }}

    async function approveSubcategory(subId) {{
      const res = await fetch(`/api/taxonomy/subcategories/${{subId}}/approve`, {{
        method: 'POST',
        headers: getAdminHeaders(),
      }});
      if (res.ok) await loadTaxonomy();
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
        ? `⏳ Submitted '${{data.code}}' (manual_user) — inactive until approved by Admin in Catalog.`
        : `✅ Added active category ${{data.code}}`;
      await loadTaxonomy();
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
        ? `⏳ Submitted '${{data.code}}' (manual_user) — inactive until approved by Admin in Catalog.`
        : `✅ Added active subcategory ${{data.code}}`;
      await loadTaxonomy();
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
    }}

    function useKey(key) {{
      document.getElementById('testApiKey').value = key;
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
      const statusEl = document.getElementById('ocrStatus');
      const outEl = document.getElementById('ocrOutput');

      if (!apiKey) {{ statusEl.innerText = '❌ Enter or select an API key first.'; return; }}
      if (!fileInput.files.length) {{ statusEl.innerText = '❌ Choose a receipt image first.'; return; }}

      const formData = new FormData();
      formData.append('file', fileInput.files[0]);
      formData.append('forward_to_webhook', sendWebhook ? 'true' : 'false');

      statusEl.innerText = '⏳ Running Stage 1 (Vision OCR) -> Stage 2 (Classifier)...';
      outEl.innerText = '';

      const res = await fetch('/api/ocr', {{
        method: 'POST',
        headers: {{ 'X-API-Key': apiKey }},
        body: formData,
      }});
      const data = await res.json();
      statusEl.innerText = res.ok ? '✅ Completed!' : `❌ Error (HTTP ${{res.status}})`;
      outEl.innerText = JSON.stringify(data, null, 2);
    }}

    document.getElementById('adminKeyInput').value = localStorage.getItem('ocr_admin_key') || '';
    (async () => {{
      await refreshAdminStatus();
      await loadBots();
      await loadTaxonomy();
    }})();
  </script>
</body>
</html>
"""
