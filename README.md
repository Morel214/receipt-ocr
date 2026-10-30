# Receipt OCR Hub 🧾🤖

A standalone, multi-tenant **Cache-First Two-Stage Receipt OCR & Product Catalog Gateway** with a built-in **Web Dashboard**, dynamic **Telegram Multi-Bot Manager**, and **REST / CSV Export API** designed for Docker homelab deployments.

---

## ✨ How It Works (Cache-First Two-Stage AI Pipeline)

1. **Stage 1 — Vision OCR Model (`OCR_PROVIDER` / `OCR_MODEL`)**:
   - Reads Polish fiscal receipts (`PARAGON FISKALNY`) and foreign receipts, extracting `store_name`, `transaction_date` (`YYYY-MM-DD`), `total_amount`, `currency`, and raw `items` (`name`, `unit` [`pcs`/`kg`/`l`], `quantity`, `unit_price`, `total_price`), while filtering out PTU/VAT summary lines and payment footers.
2. **Shared Catalog Alias Cache Lookup (Zero-Cost Hits)**:
   - Resolves the normalized store chain (`Biedronka`, `Lidl`, `Żabka`, `Dino`, `Auchan`, etc.) and looks up `(store_id, raw_name_norm)` in `product_aliases`.
   - Items found in the cache bypass Stage 2 completely (`match_source: "cache"`). Negative discount lines (`RABAT` / `OPUST`) are handled deterministically (`match_source: "rule"`).
3. **Stage 2 — Text Classifier Model (`CLASSIFIER_PROVIDER` / `CLASSIFIER_MODEL`)**:
   - Invoked **only** for unknown items (`cache miss`), enriched with top typo-tolerant SQLite **FTS5 trigram** catalog candidates (`existing_product_candidates`) and the active global **PL/EN taxonomy**.
   - Outputs bilingual clean product names (`name_pl`, `name_en`), localized `clean_name` (`pl` or `en` per user), `category`, `subcategory`, plus store-level `brand`, `off_search_query` (for Open Food Facts), `pack_amount`, and `pack_unit`.
   - New mappings are committed to the shared catalog upon user confirmation (`/confirm` or `[✅ Confirm]`).

---

## 🌐 Built-in Web Dashboard (`http://<SERVER_IP>:8080/`)

Open `http://<SERVER_IP>:8080/` in your browser:
- **🤖 Bots & OCR Tester**: Register users / API keys (`ocr_live_...`), start/stop `@BotFather` Telegram bots dynamically, choose `pl` or `en` output language, configure the 4 post-confirmation **Delivery Modes** (`hub_db`, `webhook`, `telegram_text`, `telegram_csv`), and run live receipt OCR tests.
- **📦 Product Catalog**:
  - KPI cards for active products, cached store aliases, **Stage 2 Cache Hit Rate**, and pending submissions.
  - **Products Browser**: Search across Polish/English clean names, store receipt aliases, brands, and Open Food Facts queries; edit PL/EN names & subcategories; **1-Click Merge** duplicate products (automatically re-pointing all aliases and saved Hub DB receipt items).
  - **Auto-LLM Review (Optional)**: Optional tidying queue to confirm `auto` LLM-learned products with 1 click.
  - **Manual User Queue**: Admin approval queue (`X-Admin-Key`) for categories, subcategories, and products suggested in Guest Mode (`manual_user`), which remain inactive until approved.
  - **Receipt Aliases & OFF Queries**: Inspect, override, or re-point raw store receipt lines and Open Food Facts search queries.
- **🏷️ Global Taxonomy**: Manage bilingual (`pl` / `en`) top-level categories and subcategories (protected by `ADMIN_API_KEY`).
- **📑 JSON & CSV Schema**: Live interactive reference for API responses, webhook payloads, and CSV exports.

---

## 💬 Telegram Bot Workflow (Preview, Edit & 4 Delivery Modes)

- Send one or more receipt photos to your bot.
- Receive an itemized preview (`clean_name [subcategory] — qty unit × price = total`, cache vs. LLM indicator, and receipt total verification) with inline **`[✅ Confirm]`** and **`[🗑️ Reject]`** buttons.
- Fix any OCR or classification detail before confirming:
  - `/edit <job_id> <item_no> name=<clean_name> sub=<subcategory> qty=<n> unit=<pcs|kg|l> price=<total>`
  - `/edit <job_id> store=<name> date=<YYYY-MM-DD> total=<amount>`
- Export saved receipts anytime via `/export [YYYY-MM-DD] [YYYY-MM-DD]` (when `hub_db` delivery mode is enabled).
- **Privacy Guarantee**: Anonymized product mappings enrich the shared catalog on confirm, whereas personal receipts, dates, and prices are stored on the server **only** for users who opt into `hub_db`.

---

## 🔌 REST API Quick Reference

- `POST /api/ocr` (`X-API-Key`): Parse a receipt photo (`forward_to_webhook`, `save_to_hub_db` optional flags).
- `GET /api/receipts`, `GET /api/receipts/{id}`, `GET /api/receipts/export.csv` (`X-API-Key`): Query or export saved `hub_db` receipts.
- `GET /api/catalog/stats`, `GET /api/catalog/stores`, `GET /api/catalog/products`, `GET /api/catalog/aliases`: Browse/search the shared catalog.
- `POST /api/catalog/products`, `PUT /api/catalog/products/{id}`, `POST /api/catalog/products/{id}/approve`, `POST /api/catalog/products/{id}/merge`, `DELETE /api/catalog/products/{id}`: Manage catalog products & merge duplicates (`X-Admin-Key` required for mutations).
- `GET /api/catalog/manual-queue` (`X-Admin-Key`): List all pending `manual_user` taxonomy & product suggestions.
- `GET /api/taxonomy` & `/api/taxonomy/*`: Bilingual global category/subcategory endpoints.
- Interactive OpenAPI docs: `http://<SERVER_IP>:8080/docs`

```bash
curl -X POST http://<SERVER_IP>:8080/api/ocr \
  -H "X-API-Key: ocr_live_your_api_key" \
  -F "file=@paragon.jpg"
```

---

## 🚀 Quickstart (Docker Compose)

```bash
cp .env.example .env
nano .env
sudo docker compose up -d --build
```
