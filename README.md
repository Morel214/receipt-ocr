# Receipt OCR Hub 🧾🤖

A standalone, multi-tenant **Two-Stage Receipt OCR & Classification Gateway** with a built-in **Web Dashboard**, dynamic **Telegram Multi-Bot Manager**, and simplified **REST API** designed for Docker homelab deployments.

---

## ✨ How It Works (Two-Stage AI Pipeline)

1. **Stage 1 — Vision OCR Model (`OCR_PROVIDER` / `OCR_MODEL`)**:
   - Reads the receipt image and outputs pure JSON containing `store_name`, `transaction_date` (`YYYY-MM-DD`), `total_amount`, `currency`, and raw `items` (`name`, `quantity`, `unit_price`, `total_price`) with `clean_name: ""` and `subcategory: null`.
2. **Stage 2 — Text Classifier Model (`CLASSIFIER_PROVIDER` / `CLASSIFIER_MODEL`)**:
   - Receives the Stage 1 JSON and fills in `clean_name` and `subcategory` for every item.
   - Both models can be independently configured in `.env` (or per-bot in the Web Dashboard) across **OpenAI**, **Google Gemini**, **DeepSeek**, or **OpenRouter**.

---

## 🌐 Built-in Web Dashboard (`http://<SERVER_IP>:8080/`)

Open `http://<SERVER_IP>:8080/` in your browser to:
- **Add / Edit Telegram Bots**: Paste a `@BotFather` token and start a dedicated receipt photo bot in the background without restarting Docker.
- **Set Destination Webhook URL**: Choose where the final classified JSON is POSTed when receipts are confirmed.
- **Select Stage 1 & Stage 2 Models**: Override the OCR Vision model and the Text Classifier model per bot/user.
- **Live OCR Tester**: Upload a receipt image directly in the browser to preview the JSON output.

---

## 💬 Telegram Bot (Photo Intake Only)

Each user's Telegram bot is dedicated purely to sending receipt photos:
- Send one or more receipt photos to the bot.
- Use `/pending`, `/items <id>`, `/confirm <id|all>`, `/reject <id|all>`, `/status`, `/history`.
- Upon `/confirm`, the final JSON is automatically POSTed to the user's configured Destination Webhook URL.

---

## 🔌 Simple API Usage (`POST /api/ocr`)

Share an API key (`ocr_live_...`) from the Web Dashboard with friends so they can parse receipts with a single HTTP request:

```bash
curl -X POST http://<SERVER_IP>:8080/api/ocr \
  -H "X-API-Key: ocr_live_your_api_key" \
  -F "file=@receipt.jpg"
```

### Example JSON Response
```json
{
  "store_name": "Jumbo",
  "transaction_date": "2026-10-22",
  "total_amount": 6.45,
  "currency": "EUR",
  "items": [
    {
      "name": "AH HAVERMOUT",
      "clean_name": "rolled oats",
      "subcategory": "grains",
      "quantity": 1.0,
      "unit_price": 0.75,
      "total_price": 0.75
    }
  ]
}
```

---

## 🚀 Quickstart (Docker)

```bash
cp .env.example .env
nano .env
docker compose up -d --build
```
