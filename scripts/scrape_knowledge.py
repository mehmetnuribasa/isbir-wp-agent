"""
İşbir Elektrik Web Scraper — Knowledge Base Güncelleme Scripti

Bu script isbirelektrik.com.tr web sitesindeki sayfaları sitemap üzerinden bulur,
içeriklerini çeker, menü/footer gibi tekrar eden elementleri temizler ve
data/knowledge-base.txt dosyasını güncellenmiş bilgilerle yeniden oluşturur.

Kullanım:
    python scripts/scrape_knowledge.py
    python scripts/scrape_knowledge.py --dry-run   # Dosyaya yazmadan önizleme
    python scripts/scrape_knowledge.py --output data/knowledge-base-new.txt
"""

import argparse
import logging
import re
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup, Tag

# ─── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ─── Sabitler ──────────────────────────────────────────────────────────────────
BASE_URL = "https://www.isbirelektrik.com.tr"
SITEMAP_INDEX_URL = f"{BASE_URL}/sitemap.xml"

# Çekilmeyecek sayfalar (sepet, demo, anket gibi)
SKIP_URL_PATTERNS = [
    "/sepet/",
    "/55-demo/",
    "/ssh_anket/",
    "/magaza/",
    "/urun-1/",          # Test ürünü
    "/kisisel-verilerin-korunmasi-kanunu/",  # KVKK — hukuki metin, chatbot için gereksiz
]

# Sayfa türleri ve başlık atamaları (URL slug → başlık)
PAGE_TITLE_MAP = {
    "hakkimizda": "Hakkımızda",
    "tarihce": "Tarihçe",
    "politikamiz": "Politikamız — Vizyon ve Misyon",
    "etik-ilkeler": "Etik İlkeler",
    "kalite-belgelerimiz": "Kalite Belgeleri ve Sertifikalar",
    "insan-kaynaklari": "İnsan Kaynakları",
    "kurumsal-kimlik": "Kurumsal Kimlik",
    "yonetim-kurulumuz": "Yönetim Kurulu",
    "referanslar": "Referanslar ve Müşteriler",
    "iletisim": "İletişim Bilgileri",
    "yetkili-servisler": "Yetkili Servisler",
    "ariza-destek": "Arıza Destek",
    "garanti": "Garanti Koşulları",
    "bakim": "Bakım Hizmetleri",
    "ucretsiz-yer-ve-guc-tespiti": "Ücretsiz Yer ve Güç Tespiti",
    "satis-sonrasi-hizmetlerimiz": "Satış Sonrası Hizmetler",
    "arge": "AR-GE Merkezi",
    "pro-jeneratorler": "Pro Jeneratörler",
    "eco-jeneratorler": "Eco Jeneratörler",
    "yat-jeneratorleri": "Yat ve Marin Jeneratörleri",
    "isik-kulesi": "Işık Kulesi",
    "cok-amacli-afet-jeneratoru": "Çok Amaçlı Afet Jeneratörü",
    "hibrit-jeneratorler": "Hibrit Jeneratörler (HBR Serisi)",
    "portatif-jeneratorler": "Portatif Jeneratörler",
}

# HTTP istemci ayarları
REQUEST_TIMEOUT = 30
REQUEST_DELAY = 1.0  # Saniye — sunucuyu yormamak için istekler arası bekleme
USER_AGENT = "IsbirKnowledgeBot/1.0 (internal knowledge base builder)"


# ─── Veri Modeli ───────────────────────────────────────────────────────────────
@dataclass
class ScrapedPage:
    """Çekilen sayfa verisi"""
    url: str
    title: str
    content: str
    page_type: str  # "page" veya "product"
    meta_description: str = ""


# ─── Yardımcı Fonksiyonlar ─────────────────────────────────────────────────────

def should_skip_url(url: str) -> bool:
    """URL'nin atlanıp atlanmayacağını kontrol eder."""
    for pattern in SKIP_URL_PATTERNS:
        if pattern in url:
            return True
    # Ana sayfa — bilgi içeriğinde tekrar çıkacak, atlayalım
    if url.rstrip("/") == BASE_URL:
        return True
    return False


def get_title_from_url(url: str) -> str:
    """URL slug'ından Türkçe başlık üretir."""
    path = urlparse(url).path.strip("/")
    # Ürün sayfası
    if path.startswith("urun/"):
        slug = path.replace("urun/", "")
        return slug.replace("-", " ").title()
    # Sayfa — map'ten bak
    slug = path.rstrip("/").split("/")[-1]
    if slug in PAGE_TITLE_MAP:
        return PAGE_TITLE_MAP[slug]
    # Bilinmeyen sayfa — slug'ı düzelt
    return slug.replace("-", " ").title()


def clean_text(text: str) -> str:
    """Metni temizler: fazla boşluklar, tab, satır sonları."""
    # Tab → boşluk
    text = text.replace("\t", " ")
    # Çoklu boşlukları tek boşluğa indirge
    text = re.sub(r" {2,}", " ", text)
    # 3+ satır sonunu 2'ye indirge
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Satır başı/sonu boşluklarını temizle
    lines = [line.strip() for line in text.split("\n")]
    return "\n".join(lines).strip()


# ─── Sitemap Parser ───────────────────────────────────────────────────────────

def fetch_sitemap_urls(client: httpx.Client) -> list[str]:
    """Sitemap index'ten tüm sayfa ve ürün URL'lerini çeker."""
    all_urls = []

    # 1) Sitemap index'i çek
    logger.info(f"Sitemap index çekiliyor: {SITEMAP_INDEX_URL}")
    resp = client.get(SITEMAP_INDEX_URL)
    resp.raise_for_status()

    # XML namespace
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

    root = ET.fromstring(resp.text)
    sub_sitemaps = []
    for sitemap_el in root.findall("sm:sitemap", ns):
        loc = sitemap_el.find("sm:loc", ns)
        if loc is not None and loc.text:
            # Sadece page ve product sitemap'leri al
            if "page-sitemap" in loc.text or "product-sitemap" in loc.text:
                sub_sitemaps.append(loc.text)

    # 2) Her sub-sitemap'ten URL'leri çek
    for sitemap_url in sub_sitemaps:
        logger.info(f"Sub-sitemap çekiliyor: {sitemap_url}")
        resp = client.get(sitemap_url)
        resp.raise_for_status()

        root = ET.fromstring(resp.text)
        for url_el in root.findall("sm:url", ns):
            loc = url_el.find("sm:loc", ns)
            if loc is not None and loc.text:
                url = loc.text.strip()
                if not should_skip_url(url):
                    all_urls.append(url)

        time.sleep(0.5)

    # Tekrar edenleri kaldır, sırala
    unique_urls = sorted(set(all_urls))
    logger.info(f"Toplam {len(unique_urls)} benzersiz URL bulundu")
    return unique_urls


# ─── İçerik Çekme ve Temizleme ────────────────────────────────────────────────

def extract_page_content(html: str, url: str) -> Optional[ScrapedPage]:
    """
    HTML'den ana içeriği çıkarır. Menü, footer, sidebar gibi
    tekrar eden elementleri temizler.
    """
    soup = BeautifulSoup(html, "lxml")

    # Meta description
    meta_desc = ""
    meta_tag = soup.find("meta", attrs={"name": "description"})
    if meta_tag and meta_tag.get("content"):
        meta_desc = str(meta_tag["content"]).strip()

    # Sayfa başlığı — <title> tag'inden veya URL'den
    page_title = ""
    title_tag = soup.find("title")
    if title_tag and title_tag.string:
        page_title = title_tag.string.strip()
        # " - İşbir Elektrik Sanayi A.Ş." kısmını kaldır
        page_title = re.sub(r"\s*[-–—]\s*İşbir.*$", "", page_title).strip()

    if not page_title:
        page_title = get_title_from_url(url)

    # Sayfa türü
    page_type = "product" if "/urun/" in url else "page"

    # ── Gereksiz elementleri kaldır ──
    # Navigasyon, footer, sidebar, script, style
    selectors_to_remove = [
        "nav", "header", "footer",
        ".menu", ".navigation", ".nav-menu", ".site-header", ".site-footer",
        ".sidebar", ".widget", ".breadcrumb", ".breadcrumbs",
        "#masthead", "#colophon", "#secondary",
        ".woocommerce-breadcrumb",
        ".related", ".upsells",  # İlgili ürünler
        "script", "style", "noscript",
        "iframe",
        ".wp-block-buttons",  # WP buton blokları
        ".elementor-widget-heading .elementor-heading-title",  # Bazen menü tekrar eder
        '[class*="menu"]',
        '[class*="footer"]',
        '[class*="header"]',
        '[class*="nav-"]',
        '[class*="sidebar"]',
        '[id*="menu"]',
        '[id*="footer"]',
        '[id*="header"]',
        ".cookie-notice",
        ".popup",
        ".modal",
        # WhatsApp widget
        '[class*="whatsapp"]',
        '[class*="wa-"]',
    ]

    for selector in selectors_to_remove:
        try:
            for el in soup.select(selector):
                el.decompose()
        except Exception:
            continue

    # ── Ana içerik alanını bul ──
    main_content = None

    # WordPress / Elementor yapısı — önce bunlara bak
    content_selectors = [
        ".entry-content",
        ".page-content",
        ".post-content",
        ".elementor-widget-container",
        "article",
        ".product-description",
        ".woocommerce-product-details__short-description",
        "main",
        "#content",
        ".content-area",
        '[role="main"]',
    ]

    for selector in content_selectors:
        found = soup.select(selector)
        if found:
            # Tüm eşleşenlerin metnini birleştir
            texts = []
            for el in found:
                t = _extract_element_text(el)
                if t and len(t) > 30:  # Çok kısa olanları atla
                    texts.append(t)
            if texts:
                main_content = "\n\n".join(texts)
                break

    if not main_content:
        # Son çare — body'nin tüm metnini al
        body = soup.find("body")
        if body:
            main_content = _extract_element_text(body)

    if not main_content or len(main_content.strip()) < 20:
        logger.warning(f"İçerik bulunamadı veya çok kısa: {url}")
        return None

    # ── İçerik temizleme ──
    content = clean_text(main_content)

    # Menü linkleri gibi tekrar eden metinleri tespit edip kaldır
    content = _remove_navigation_noise(content)

    # Çok kısa olduysa atla
    if len(content.strip()) < 30:
        return None

    return ScrapedPage(
        url=url,
        title=page_title,
        content=content,
        page_type=page_type,
        meta_description=meta_desc,
    )


def _extract_element_text(element: Tag) -> str:
    """Bir HTML elementinden temiz metin çıkarır."""
    # Her text node'u satır satır al
    lines = []
    for text in element.stripped_strings:
        text = text.strip()
        if text:
            lines.append(text)
    return "\n".join(lines)


def _remove_navigation_noise(content: str) -> str:
    """
    İçerikteki navigasyon menüsü gürültüsünü tespit edip kaldırır.
    Örn: Tekrar eden "Pro Jeneratörler\nEco Jeneratörler\n..." blokları.
    """
    lines = content.split("\n")
    cleaned_lines = []

    # Navigasyon sinyalleri — bu kelimeler peş peşe gelen satırlarda
    # tekrar ediyorsa navigasyondur
    nav_keywords = {
        "hakkımızda", "vizyon", "misyon", "tarihçe", "yönetim kurulu",
        "politikamız", "etik ilkeler", "kalite belgelerimiz",
        "kurumsal kimlik", "kvkk", "insan kaynakları",
        "pro jeneratörler", "eco jeneratörler", "yat jeneratörleri",
        "ışık kulesi", "hibrit jeneratörler", "portatif jeneratörler",
        "askeri jeneratörler", "alternatörler",
        "yetkili servisler", "arıza destek", "garanti",
        "referanslar", "katalog", "iletişim",
        "bakım", "satış sonrası", "arge",
        "taktik sessiz", "portatif dizel", "mobil jeneratörler",
        "askeri kombine", "marin jeneratör",
        "dc alternatör", "monofaz", "trifaz",
        "kurumsal", "jeneratörler", "hizmetlerimiz",
        "eng", "frh",
    }

    # Sliding window — peş peşe 5+ nav keyword bulursan o bloğu atla
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        line_lower = line.lower()

        # Boş satır — geçir
        if not line:
            cleaned_lines.append("")
            i += 1
            continue

        # Nav keyword zinciri kontrolü
        nav_count = 0
        j = i
        while j < len(lines) and j - i < 30:  # Max 30 satır ileriye bak
            check_line = lines[j].strip().lower()
            if not check_line:
                j += 1
                continue
            is_nav = False
            for kw in nav_keywords:
                if kw in check_line and len(check_line) < 60:
                    is_nav = True
                    break
            if is_nav:
                nav_count += 1
                j += 1
            else:
                break

        if nav_count >= 4:
            # Nav bloğu tespit edildi — atla
            i = j
            continue

        # Normal satır
        cleaned_lines.append(line)
        i += 1

    return "\n".join(cleaned_lines)


# ─── Knowledge Base Formatlama ─────────────────────────────────────────────────

def format_knowledge_base(pages: list[ScrapedPage]) -> str:
    """Çekilen sayfaları knowledge-base.txt formatında biçimlendirir."""
    sections = []

    # Önce kurumsal sayfalar, sonra ürünler
    corporate_pages = [p for p in pages if p.page_type == "page"]
    product_pages = [p for p in pages if p.page_type == "product"]

    # Sabit bilgiler — her zaman en üstte
    sections.append(_get_static_header())

    # Kurumsal sayfalar
    for page in corporate_pages:
        section = f"### {page.title}\n{page.content}"
        if page.meta_description:
            section = f"### {page.title}\n{page.meta_description}\n{page.content}"
        sections.append(section)

    # Ürün sayfaları
    if product_pages:
        for page in product_pages:
            section = f"### Ürün: {page.title}\n{page.content}"
            sections.append(section)

    # Sabit alt bilgiler
    sections.append(_get_static_footer())

    return "\n\n".join(sections) + "\n"


def _get_static_header() -> str:
    """Değişmeyen temel şirket bilgileri (manuel)."""
    return """### İşbir Elektrik Hakkında — Genel
İşbir Elektrik Sanayi A.Ş. 1977'den beri jeneratör ve enerji çözümleri üretmektedir.
TSKGV (Türk Silahlı Kuvvetlerini Güçlendirme Vakfı) bünyesinde faaliyet göstermektedir.
600'den fazla müşteri ve 10,000'den fazla proje deneyimine sahibiz.
Slogan: "Yaşamla Kesintisiz İşbirliği"
46+ yıllık deneyim ile Türkiye'nin en köklü jeneratör üreticilerinden biriyiz.

### TSKGV Bağlantısı
İşbir Elektrik, TSKGV (Türk Silahlı Kuvvetlerini Güçlendirme Vakfı) kuruluşudur.
TSKGV bağlı diğer ortaklıklar: ASELSAN, HAVELSAN, TUSAŞ, ROKETSAN, ASPİLSAN
Askeri standartlarda üretim yapma yetkinliğimiz bu bağlantıdan gelmektedir.

### İletişim Bilgileri
Fabrika ve Genel Müdürlük:
Adres: Gaziosmanpaşaosb Mah. 7. Cad. No: 11/1 Altıeylül / BALIKESİR
Telefon: +90 (266) 283 0050 (Pbx)
Çağrı Merkezi: 444 09 10
E-posta: isbir@isbirelektrik.com.tr
KEP: isbir@hs01.kep.tr

Ankara Büro:
Adres: Remzi Oğuz Arık Mah. Paris Cad. No:43 Çankaya / ANKARA
Telefon: +90 (312) 473 2600

Arıza Destek WhatsApp: +90 530 919 61 83"""


def _get_static_footer() -> str:
    """Değişmeyen fiyat/destek bilgileri (manuel)."""
    return """### Fiyatlandırma Politikası
Fiyatlarımız donanım ve projeye göre değişiklik göstermektedir.
Her proje için özel teklif hazırlanır.
Detaylı fiyat teklifi için lütfen iletişime geçin:
Telefon: 444 09 10
E-posta: isbir@isbirelektrik.com.tr
Satış ekibimiz size en uygun teklifi sunmak için hazırdır.

### Teknik Destek ve Hizmetler
7/24 teknik destek hizmeti sunulmaktadır.
Ücretsiz yer ve güç tespiti yapılır.
Profesyonel kurulum ve devreye alma hizmeti mevcuttur.
Periyodik bakım hizmetleri sağlanır.
Orijinal yedek parça tedariki yapılır.
Hızlı arıza müdahale ekipleri vardır."""


# ─── Ana Scraping Akışı ───────────────────────────────────────────────────────

def scrape_all(dry_run: bool = False, output_path: Optional[str] = None) -> None:
    """Tüm scraping akışını yönetir."""
    project_root = Path(__file__).parent.parent
    default_output = project_root / "data" / "knowledge-base.txt"
    output_file = Path(output_path) if output_path else default_output

    # HTTP client
    headers = {"User-Agent": USER_AGENT}
    with httpx.Client(
        headers=headers,
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    ) as client:

        # 1) Sitemap'ten URL'leri çek
        urls = fetch_sitemap_urls(client)
        logger.info(f"Toplam {len(urls)} sayfa çekilecek")

        # 2) Her sayfayı çek ve parse et
        scraped_pages: list[ScrapedPage] = []
        failed_urls: list[str] = []

        for i, url in enumerate(urls, 1):
            logger.info(f"[{i}/{len(urls)}] Çekiliyor: {url}")

            try:
                resp = client.get(url)
                resp.raise_for_status()

                page = extract_page_content(resp.text, url)
                if page:
                    scraped_pages.append(page)
                    logger.info(f"  ✅ {page.title} — {len(page.content)} karakter")
                else:
                    logger.warning(f"  ⚠️ İçerik çıkarılamadı")
                    failed_urls.append(url)

            except httpx.HTTPStatusError as e:
                logger.error(f"  ❌ HTTP hatası: {e.response.status_code}")
                failed_urls.append(url)
            except Exception as e:
                logger.error(f"  ❌ Hata: {e}")
                failed_urls.append(url)

            # Rate limiting
            time.sleep(REQUEST_DELAY)

        # 3) Sonuçları formatla
        logger.info(f"\n{'='*60}")
        logger.info(f"Başarılı: {len(scraped_pages)} sayfa")
        logger.info(f"Başarısız: {len(failed_urls)} sayfa")

        if failed_urls:
            logger.warning("Başarısız URL'ler:")
            for url in failed_urls:
                logger.warning(f"  - {url}")

        # 4) Knowledge base dosyasını oluştur
        kb_content = format_knowledge_base(scraped_pages)

        if dry_run:
            logger.info("\n[DRY RUN] Dosyaya yazılmadı. Önizleme:")
            print("=" * 60)
            # İlk 3000 karakteri göster
            preview = kb_content[:3000]
            print(preview)
            if len(kb_content) > 3000:
                print(f"\n... ({len(kb_content)} karakter toplam, {kb_content.count(chr(10))} satır)")
            print("=" * 60)
        else:
            # Mevcut dosyayı yedekle
            if output_file.exists():
                backup_path = output_file.with_suffix(".txt.bak")
                output_file.rename(backup_path)
                logger.info(f"Mevcut dosya yedeklendi: {backup_path}")

            # Yeni dosyayı yaz
            output_file.write_text(kb_content, encoding="utf-8")
            logger.info(f"✅ Knowledge base güncellendi: {output_file}")
            logger.info(f"   Toplam: {len(kb_content)} karakter, {kb_content.count(chr(10))} satır")
            logger.info(f"   Toplam section: {kb_content.count('### ')}")


# ─── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="İşbir Elektrik web sitesinden bilgi tabanı güncelleme scripti"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dosyaya yazmadan önizleme yap",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Çıktı dosyası yolu (varsayılan: data/knowledge-base.txt)",
    )
    args = parser.parse_args()

    logger.info("🚀 İşbir Elektrik Web Scraper başlatılıyor...")
    logger.info(f"   Hedef site: {BASE_URL}")

    try:
        scrape_all(dry_run=args.dry_run, output_path=args.output)
    except KeyboardInterrupt:
        logger.info("\n⚠️ Kullanıcı tarafından iptal edildi")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Beklenmeyen hata: {e}", exc_info=True)
        sys.exit(1)

    logger.info("🏁 Scraping tamamlandı!")


if __name__ == "__main__":
    main()
