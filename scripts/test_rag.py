"""
RAG Pipeline Test — İndeksleme ve sorgu testi

Bu script:
1. Knowledge base'i ChromaDB'ye indeksler
2. Örnek sorguları semantik arama ile test eder
3. Sonuçları raporlar
"""

import sys
import os
from pathlib import Path

# Proje kökünü sys.path'e ekle
projectRoot = str(Path(__file__).parent.parent)
sys.path.insert(0, projectRoot)

from google import genai
from src.aiChatbot.services.embeddingService import EmbeddingService
from src.aiChatbot.services.ragService import RAGService


def main():
    # API key
    apiKey = os.environ.get("GEMINI_API_KEY", "")
    if not apiKey:
        # .env'den oku
        envPath = Path(projectRoot) / ".env"
        if envPath.exists():
            for line in envPath.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("GEMINI_API_KEY="):
                    apiKey = line.split("=", 1)[1].strip()
                    break

    if not apiKey:
        print("❌ GEMINI_API_KEY bulunamadı!")
        sys.exit(1)

    print("🚀 RAG Pipeline Test başlatılıyor...\n")

    # 1) Client oluştur
    client = genai.Client(api_key=apiKey)
    embeddingService = EmbeddingService(client=client)

    # 2) RAG servisi oluştur
    chromaPath = str(Path(projectRoot) / "data" / "chroma_db")
    ragService = RAGService(
        embeddingService=embeddingService,
        chromaDbPath=chromaPath,
    )

    # 3) Knowledge base'i indeksle
    kbPath = str(Path(projectRoot) / "data" / "knowledge-base.txt")
    print(f"📄 Knowledge base: {kbPath}")

    indexCount = ragService.indexKnowledgeBase(kbPath, forceReindex=True)
    print(f"✅ İndeksleme tamamlandı: {indexCount} chunk\n")

    # 4) Test sorguları
    testQueries = [
        "İşbir Elektrik ne zaman kuruldu?",
        "Hibrit jeneratör modelleri neler?",
        "Askeri jeneratör ses seviyesi nedir?",
        "İletişim bilgileriniz nedir?",
        "Yetkili servisler nerelerde?",
        "Pro jeneratör güç aralığı ne kadar?",
        "Eco jeneratör motor seçenekleri neler?",
        "Yat jeneratörü sertifikaları neler?",
        "Portatif jeneratör ağırlığı ne kadardır?",
        "TSKGV nedir ve bağlantısı nedir?",
        "Garanti koşulları nelerdir?",
        "Marin jeneratör soğutma sistemi nasıl çalışır?",
        "Bakım hizmetleri nelerdir?",
        "Kalite belgeleriniz nelerdir?",
        "Alternatör çeşitleriniz nelerdir?",
        "Şirket tarihçesi hakkında bilgi verir misiniz?",
        "Arıza destek numarası nedir?",
        "Çok amaçlı afet jeneratörü ne işe yarar?",
        "Işık kulesi jeneratörleri var mı?",
        "Fiyat bilgisi alabilir miyim?",
    ]

    print("=" * 70)
    print("📊 SORGU TEST SONUÇLARI")
    print("=" * 70)

    successCount = 0
    for i, query in enumerate(testQueries, 1):
        print(f"\n🔍 [{i}/{len(testQueries)}] Soru: {query}")

        result = ragService.findRelevantContent(query, topK=3)

        if result:
            # İlk 200 karakteri göster
            preview = result[:200].replace("\n", " ")
            if len(result) > 200:
                preview += "..."
            print(f"   ✅ Sonuç ({len(result)} karakter): {preview}")
            successCount += 1
        else:
            print(f"   ❌ Sonuç bulunamadı")

    print(f"\n{'=' * 70}")
    print(f"📊 SONUÇ: {successCount}/{len(testQueries)} sorgu başarılı")
    print(f"   Başarı oranı: {successCount/len(testQueries)*100:.0f}%")

    stats = ragService.getStats()
    print(f"   Toplam chunk: {stats['totalChunks']}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
