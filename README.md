# Receipt OCR Hub 🧾🤖

Niezależny, wielodostępny (multi-tenant) mikroserwis **OCR i klasyfikacji paragonów** z dynamicznym menedżerem wielu botów Telegrama (**Multi-Bot Manager**) oraz elastycznym **REST API Gateway** gotowym do wdrożenia w Dockerze na własnym homelabie — **bez n8n**.

---

## ✨ Główne możliwości

- **Natywny Chmurowy OCR + Klasyfikator AI (Zamiast n8n)**:
  - Bezpośrednia integracja z **OpenAI** (`gpt-4o-mini`, `gpt-4o`), **Google Gemini** (`gemini-2.5-flash`, `gemini-2.5-pro`) oraz dowolnym API kompatybilnym z OpenAI (np. **OpenRouter**, **Groq**, **LiteLLM** przez `OPENAI_BASE_URL`).
  - Jednoczesny odczyt nagłówka (`store_name`, `transaction_date`, `total_amount`, `currency`, `confidence`), pozycji z paragonu, tłumaczenie/czyszczenie nazw produktów (`clean_name`, np. `"PLAK JONG GVP"` ➔ `"ser żółty"`, `"STATIEGELD"` ➔ `"kaucja"`, promocje ➔ `"Rabat"`) oraz klasyfikacja do `subcategory`.
- **Środowisko dla Własnych Botów na Telegramie (`BotManager`)**:
  - Każdy znajomy/użytkownik ma **własnego bota** utworzonego w `@BotFather`.
  - Dodawanie nowych botów działa **w locie (bez restartu kontenera Docker)** przez endpoint administracyjny lub CLI.
- **Konfiguracja "Swojej Bazy" prosto z Telegrama**:
  - Użytkownik sam ustawia w swoim bocie komendą `/set_webhook <url> [secret_token]` miejsce, gdzie po `/confirm` mają trafiać przetworzone paragony.
  - Komenda `/test_webhook` od razu weryfikuje połączenie z bazą/API użytkownika.
  - Komenda `/set_model <openai|gemini> <model>` pozwala w locie przełączać i testować różne modele AI.
- **Elastyczny Endpoint API dla Znajomych (`POST /api/v1/ocr/parse`)**:
  - Każdy użytkownik otrzymuje indywidualny klucz `ocr_live_...`, którym może bezpośrednio wysyłać zdjęcia paragonów ze swoich skryptów/aplikacji i od razu odbierać ustrukturyzowany JSON.

---

## 🚀 Szybki Start w Dockerze (Homelab)

### 1. Konfiguracja `.env`

```bash
cd c:/Projects/Python/receipt-ocr-hub
copy .env.example .env
```

Uzupełnij w `.env`:
- `ADMIN_API_KEY` — Twój główny klucz administratora do dodawania nowych użytkowników/botów.
- `OPENAI_API_KEY` i/lub `GEMINI_API_KEY` — klucze do chmurowych modeli Vision.
- *(Opcjonalnie)* `DEFAULT_TELEGRAM_BOT_TOKEN` oraz `DEFAULT_WEBHOOK_URL` — automatycznie utworzy Twojego głównego bota przy pierwszym starcie kontenera.

### 2. Uruchomienie kontenera

```bash
docker compose up -d --build
```

Dokumentacja Swagger UI jest dostępna pod adresem: `http://localhost:8080/docs`.

---

## 👥 Dodawanie Nowych Botów dla Znajomych

### Opcja A: Przez CLI w kontenerze
```bash
docker exec -it receipt-ocr-hub ocr-hub add-tenant \
  --name "Kamil" \
  --bot-token "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ" \
  --currency "PLN"
```

### Opcja B: Przez REST API (uruchamia nowego bota natychmiast w tle!)
```bash
curl -X POST http://localhost:8080/api/v1/admin/tenants \
  -H "X-Admin-Key: twoj-admin-secret" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Kamil",
    "telegram_bot_token": "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ",
    "default_currency": "PLN"
  }'
```
W odpowiedzi otrzymasz wygenerowany `api_key` (np. `ocr_live_a1b2c3...`), który znajomy zobaczy również po wpisaniu `/my_config` w swoim bocie na Telegramie.

---

## 💬 Komendy w Bocie Telegrama

| Komenda | Działanie |
| :--- | :--- |
| *(Wysłanie zdjęć)* | Grupuje zdjęcia w paczkę, uruchamia OCR + klasyfikację i wyświetla podsumowanie. |
| `/pending` | Wyświetla paragony oczekujące na decyzję. |
| `/items <id>` | Pokazuje szczegółową listę odczytanych produktów, czystych nazw i podkategorii. |
| `/confirm <id\|all>` | Zatwierdza paragon(y) i wysyła ustrukturyzowany JSON (`POST`) do bazy użytkownika. |
| `/reject <id\|all>` | Odrzuca i usuwa paragon(y) z kolejki. |
| `/set_webhook <url> [token]` | Ustawia adres docelowy (`POST`) oraz opcjonalny `Bearer token` dla wyników użytkownika. |
| `/test_webhook` | Wysyła testowy ping do skonfigurowanego webhooka i zwraca kod odpowiedzi HTTP. |
| `/set_model <provider> <model>` | Przełącza model OCR w locie (np. `/set_model gemini gemini-2.5-flash` lub `/set_model openai gpt-4o`). |
| `/set_categories <lista>` | Pozwala użytkownikowi ustawić własną listę podkategorii (lub `default`). |
| `/my_config` | Pokazuje aktualny klucz REST API (`api_key`), webhook, model oraz podkategorie. |

---

## 🔌 Korzystanie z Endpointu API (`POST /api/v1/ocr/parse`)

Znajomy może wysłać zdjęcie paragonu z dowolnego narzędzia (Python, Node.js, cURL, skróty iOS) i od razu otrzymać rozpoznany JSON:

```bash
curl -X POST http://localhost:8080/api/v1/ocr/parse \
  -H "Authorization: Bearer ocr_live_twoj_klucz_api" \
  -F "file=@paragon.jpg" \
  -F "provider=openai" \
  -F "model=gpt-4o-mini" \
  -F "forward_to_webhook=false"
```
