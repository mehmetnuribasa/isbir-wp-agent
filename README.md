# İşbir WhatsApp AI Chatbot

İşbir Elektrik için WhatsApp üzerinden çalışan yapay zeka destekli müşteri temsilcisi chatbot'u.

## Özellikler

- **Gemini AI**: Google Gemini 2.5 Flash ile doğal dil işleme
- **Clean Architecture**: Interface-based modüler yapı
- **Interactive Menüler**: WhatsApp buton ve liste menüleri
- **Message Queue**: Worker pool ile asenkron mesaj işleme
- **Debouncing**: Spam koruması
- **Business Hours**: Mesai saatleri kontrolü
- **Keyword-based Knowledge Base**: Hızlı bilgi arama
- **Structured Logging**: Cloud Run uyumlu JSON logging

## Hızlı Başlangıç

1. `.env.example` dosyasını `.env` olarak kopyalayın:
   ```bash
   cp .env.example .env
   ```

2. `.env` dosyasına API anahtarlarınızı girin:
   - `GEMINI_API_KEY` — Google AI Studio'dan alın
   - `WHATSAPP_ACCESS_TOKEN` — Meta Developer Portal'dan alın
   - `WHATSAPP_PHONE_NUMBER_ID` — WhatsApp Business API'den alın

3. Bağımlılıkları yükleyin:
   ```bash
   pip install -e .
   ```

4. Çalıştırın:
   ```bash
   python -m aiChatbot.main
   ```

## Proje Yapısı

```
isbir-wp-agent/
├── src/aiChatbot/
│   ├── interfaces/          # Abstract base classes
│   │   ├── aiService.py
│   │   ├── channelAdapter.py
│   │   ├── messageProcessor.py
│   │   └── embeddingService.py
│   ├── models/              # Pydantic data models
│   │   ├── botConfig.py
│   │   ├── chatSession.py
│   │   └── standardMessage.py
│   ├── services/            # Business logic
│   │   ├── geminiAIService.py
│   │   ├── sessionManager.py
│   │   ├── messageProcessorService.py
│   │   ├── channelManager.py
│   │   ├── serviceFactory.py
│   │   ├── messageQueue.py
│   │   ├── knowledgeBase.py
│   │   ├── businessHours.py
│   │   └── intentDetector.py
│   ├── adapters/            # Channel implementations
│   │   └── whatsappAdapter.py
│   ├── api/                 # FastAPI endpoints
│   │   └── app.py
│   ├── utils/               # Utilities
│   │   ├── loggingConfig.py
│   │   ├── languageDetector.py
│   │   └── promptManager.py
│   ├── main.py
│   └── asgi.py
├── data/
│   ├── prompts.json
│   └── knowledge-base.txt
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

## Docker

```bash
docker compose up --build
```

## Webhook Kurulumu

1. ngrok veya benzeri bir tunnel aracı ile localhost:8000'i dışarıya açın
2. Meta Developer Portal'da webhook URL'sini ayarlayın: `https://your-domain/webhook/whatsapp`
3. Verify token'ı `.env` dosyasındaki `WHATSAPP_WEBHOOK_VERIFY_TOKEN` ile eşleştiğinden emin olun
