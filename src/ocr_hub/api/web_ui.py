"""Built-in Web UI Dashboard for managing Telegram bots, destination webhooks, and testing receipt OCR."""

from ocr_hub import config


def render_dashboard_html() -> str:
    """Return the single-page English Web Dashboard HTML."""
    default_subcats = ", ".join(config.DEFAULT_SUBCATEGORIES)
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
      max-width: 1160px;
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
    .bot-item {{
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
      font-size: 0.85rem;
    }}
    table.schema-table th, table.schema-table td {{
      padding: 8px 12px;
      border: 1px solid var(--border);
      text-align: left;
    }}
    table.schema-table th {{
      background: #0b1120;
      color: var(--accent);
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div>
        <h1>🧾 Receipt OCR Hub</h1>
        <div class="sub">
          Active Models: <code>Stage 1 OCR = {config.OCR_PROVIDER}/{config.OCR_MODEL}</code> &rarr;
          <code>Stage 2 Classifier = {config.CLASSIFIER_PROVIDER}/{config.CLASSIFIER_MODEL}</code>
        </div>
      </div>
      <div>
        <a href="/docs" style="color: var(--accent); text-decoration: none; font-weight: 600;">Open Swagger API Docs &rarr;</a>
      </div>
    </header>

    <div class="grid">
      <!-- Left: Add / Edit Bot & Destination Form -->
      <div class="card">
        <h2 id="formTitle">➕ Add or Update Bot / User</h2>
        <div class="sub" style="margin-bottom: 8px;">Configure a Telegram receipt bot and set where the parsed JSON is sent.</div>
        <input type="hidden" id="editBotId" value="" />

        <div class="row2">
          <div>
            <label>User / Bot Name *</label>
            <input type="text" id="botName" placeholder="e.g. Domingo or Alex" required />
          </div>
          <div>
            <label>Default Currency</label>
            <input type="text" id="botCurrency" value="EUR" placeholder="EUR, PLN, USD" />
          </div>
        </div>

        <div class="row2">
          <div>
            <label>Clean Name Language (Stage 2 Classifier)</label>
            <select id="botLanguage">
              <option value="en">English (en)</option>
              <option value="pl">Polish (pl)</option>
              <option value="nl">Dutch (nl)</option>
              <option value="de">German (de)</option>
              <option value="es">Spanish (es)</option>
              <option value="fr">French (fr)</option>
              <option value="it">Italian (it)</option>
            </select>
          </div>
          <div>
            <label>Telegram Bot Token (optional for API-only)</label>
            <input type="text" id="botToken" placeholder="123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ" />
          </div>
        </div>

        <label>Destination Webhook URL (where final receipt JSON is POSTed upon confirmation)</label>
        <input type="text" id="webhookUrl" placeholder="http://100.x.y.z:8000/api/receipts/webhook" />

        <label>Destination Webhook Bearer Secret (optional)</label>
        <input type="text" id="webhookSecret" placeholder="Optional Authorization Bearer token" />

        <label>Allowed Subcategories for this User (comma-separated)</label>
        <div class="sub" style="font-size: 0.78rem; margin-bottom: 4px;">Items on receipts will be strictly categorized into one of these subcategories during Stage 2 classification.</div>
        <input type="text" id="subcategories" value="{default_subcats}" />

        <div class="actions" style="margin-top: 16px;">
          <button onclick="saveBot()">💾 Save &amp; Start Bot</button>
          <button class="secondary" onclick="resetForm()">Clear Form</button>
        </div>
        <div id="formStatus" class="status-msg"></div>
      </div>

      <!-- Right: Live 2-Stage OCR Tester -->
      <div class="card">
        <h2>🧪 Test Receipt OCR</h2>
        <div class="sub">Upload a receipt photo to test OCR &rarr; Item Classification directly in the browser.</div>

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

    <!-- Middle: Final JSON Structure & Webhook Documentation -->
    <div class="card">
      <h2>📑 Final Output JSON Schema (Webhook &amp; API)</h2>
      <div class="sub" style="margin-bottom: 12px;">
        This is the exact JSON structure sent via HTTP <code>POST</code> to your <b>Destination Webhook URL</b> (and returned by <code>POST /api/ocr</code>). Use this format to design your database tables or webhook handler:
      </div>
      <div class="grid" style="margin-bottom: 0;">
        <div>
          <pre><code>{{
  "store_name": "Jumbo",
  "transaction_date": "2026-10-22",
  "total_amount": 6.45,
  "currency": "EUR",
  "items": [
    {{
      "name": "AH HAVERMOUT",
      "clean_name": "rolled oats",
      "subcategory": "grains",
      "quantity": 1.0,
      "unit_price": 0.75,
      "total_price": 0.75
    }},
    {{
      "name": "PLAK JONG GVP",
      "clean_name": "yellow cheese",
      "subcategory": "dairy",
      "quantity": 2.0,
      "unit_price": 3.00,
      "total_price": 6.00
    }},
    {{
      "name": "BONUS AH JONG",
      "clean_name": "Discount",
      "subcategory": null,
      "quantity": 1.0,
      "unit_price": -0.30,
      "total_price": -0.30
    }}
  ]
}}</code></pre>
        </div>
        <div>
          <table class="schema-table">
            <thead>
              <tr><th>Field</th><th>Type</th><th>Description</th></tr>
            </thead>
            <tbody>
              <tr><td><code>store_name</code></td><td>string</td><td>Normalized merchant/store name (e.g. "Lidl", "Jumbo").</td></tr>
              <tr><td><code>transaction_date</code></td><td>string</td><td>Date of purchase strictly formatted as <code>YYYY-MM-DD</code>.</td></tr>
              <tr><td><code>total_amount</code></td><td>float</td><td>Final total amount paid on the receipt.</td></tr>
              <tr><td><code>currency</code></td><td>string</td><td>Three-letter currency code (e.g. "EUR", "PLN", "USD").</td></tr>
              <tr><td><code>items[].name</code></td><td>string</td><td>Exact original printed item text from the receipt.</td></tr>
              <tr><td><code>items[].clean_name</code></td><td>string</td><td>Human-readable generic product name normalized by Stage 2.</td></tr>
              <tr><td><code>items[].subcategory</code></td><td>string | null</td><td>Chosen strictly from the user's allowed subcategories (or null for discounts).</td></tr>
              <tr><td><code>items[].quantity</code></td><td>float</td><td>Quantity or weight (default 1.0).</td></tr>
              <tr><td><code>items[].unit_price</code></td><td>float</td><td>Unit price (negative for discounts/rebates).</td></tr>
              <tr><td><code>items[].total_price</code></td><td>float</td><td>Total line price after quantity (negative for discounts).</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Bottom: Registered Bots & API Keys -->
    <div class="card">
      <h2>🤖 Registered Telegram Bots &amp; API Endpoints</h2>
      <div class="sub" style="margin-bottom: 12px;">
        Direct API usage: <code>curl -X POST http://&lt;HOST&gt;:8080/api/ocr -H "X-API-Key: &lt;API_KEY&gt;" -F "file=@receipt.jpg"</code>
      </div>
      <div id="botsList">Loading...</div>
    </div>
  </div>

  <script>
    let cachedBots = [];

    async function loadBots() {{
      const res = await fetch('/api/bots');
      cachedBots = await res.json();
      const container = document.getElementById('botsList');
      if (!cachedBots.length) {{
        container.innerHTML = '<div class="sub">No bots registered yet. Add one using the form above!</div>';
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
            <div>🌐 Destination Webhook: <code>${{b.webhook_url || 'Not configured'}}</code></div>
            <div>🌐 Clean Name Language: <code>${{b.language || 'en'}}</code> | 🏷️ Allowed Subcategories (${{(b.subcategories || []).length}}): <code>${{(b.subcategories || []).join(', ')}}</code></div>
          </div>
        </div>
      `).join('');
    }}

    function useKey(key) {{
      document.getElementById('testApiKey').value = key;
    }}

    function editBot(id) {{
      const b = cachedBots.find(x => x.id === id);
      if (!b) return;
      document.getElementById('formTitle').innerText = `✏️ Edit Bot #${{b.id}} (${{b.name}})`;
      document.getElementById('editBotId').value = b.id;
      document.getElementById('botName').value = b.name;
      document.getElementById('botCurrency').value = b.default_currency || 'EUR';
      document.getElementById('botLanguage').value = b.language || 'en';
      document.getElementById('botToken').value = '';
      document.getElementById('botToken').placeholder = b.has_telegram_bot ? '(Leave empty to keep existing bot token)' : 'Paste @BotFather token';
      document.getElementById('webhookUrl').value = b.webhook_url || '';
      document.getElementById('webhookSecret').value = '';
      document.getElementById('subcategories').value = (b.subcategories || []).join(', ');
      window.scrollTo({{ top: 0, behavior: 'smooth' }});
    }}

    function resetForm() {{
      document.getElementById('formTitle').innerText = '➕ Add or Update Bot / User';
      document.getElementById('editBotId').value = '';
      document.getElementById('botName').value = '';
      document.getElementById('botCurrency').value = 'EUR';
      document.getElementById('botLanguage').value = 'en';
      document.getElementById('botToken').value = '';
      document.getElementById('botToken').placeholder = '123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ';
      document.getElementById('webhookUrl').value = '';
      document.getElementById('webhookSecret').value = '';
      document.getElementById('subcategories').value = '{default_subcats}';
      document.getElementById('formStatus').innerText = '';
    }}

    async function saveBot() {{
      const editId = document.getElementById('editBotId').value;
      const subcats = document.getElementById('subcategories').value
        .split(',').map(s => s.trim()).filter(Boolean);

      const payload = {{
        name: document.getElementById('botName').value.trim(),
        default_currency: document.getElementById('botCurrency').value.trim() || 'EUR',
        language: document.getElementById('botLanguage').value || 'en',
        webhook_url: document.getElementById('webhookUrl').value.trim() || null,
        subcategories: subcats.length ? subcats : null,
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
        headers: {{ 'Content-Type': 'application/json' }},
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
      await fetch(`/api/bots/${{id}}`, {{ method: 'DELETE' }});
      await loadBots();
    }}

    async function testWebhook(id) {{
      const res = await fetch(`/api/bots/${{id}}/test-webhook`, {{ method: 'POST' }});
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

    loadBots();
  </script>
</body>
</html>
"""
