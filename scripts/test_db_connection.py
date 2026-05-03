"""
Hızlı PostgreSQL bağlantı testi.
Çalıştır: python scripts/test_db_connection.py
"""

import asyncio
import os
import sys
from pathlib import Path

# src dizinini path'e ekle
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from aiChatbot.database.connection import DatabaseManager
from aiChatbot.database.repository import ChatRepository


async def test_connection():
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        print("❌ DATABASE_URL bulunamadı! .env dosyasını kontrol edin.")
        return

    # Şifreyi logda gösterme
    safe_url = database_url.split("@")[1] if "@" in database_url else database_url
    print(f"🔌 Bağlanılıyor: ...@{safe_url}")

    db = DatabaseManager()

    try:
        # 1. Bağlantı + tablo oluşturma
        await db.init(database_url, echo=False)
        await db.create_tables()
        print("✅ PostgreSQL bağlantısı başarılı!")
        print("✅ Tablolar oluşturuldu/doğrulandı!")

        # 2. Kullanıcı oluşturma testi
        async with db.session() as session:
            repo = ChatRepository(session)
            user = await repo.get_or_create_user(
                phone_number="905550000000",
                channel_type="whatsapp",
                language="tr",
            )
            print(f"✅ Test kullanıcısı: id={user.id}, phone={user.phone_number}")

        # 3. Oturum oluşturma testi
        async with db.session() as session:
            repo = ChatRepository(session)
            user = await repo.get_or_create_user("905550000000", "whatsapp")
            db_session, is_new = await repo.get_or_create_active_session(
                user_id=user.id,
                channel_id="905550000000",
            )
            print(f"✅ Test oturumu: id={db_session.id}, uuid={db_session.session_uuid[:8]}..., new={is_new}")

        # 4. Mesaj kaydetme testi
        async with db.session() as session:
            repo = ChatRepository(session)
            user = await repo.get_or_create_user("905550000000", "whatsapp")
            db_session, _ = await repo.get_or_create_active_session(user.id, "905550000000")
            msg = await repo.save_message(db_session.id, "user", "Merhaba, bu bir test mesajıdır!")
            print(f"✅ Test mesajı kaydedildi: id={msg.id}, role={msg.role}")

        # 5. Mesajları okuma testi
        async with db.session() as session:
            repo = ChatRepository(session)
            user = await repo.get_or_create_user("905550000000", "whatsapp")
            db_session, _ = await repo.get_or_create_active_session(user.id, "905550000000")
            messages = await repo.get_session_messages(db_session.id)
            print(f"✅ Oturum mesajları: {len(messages)} mesaj bulundu")
            for m in messages:
                print(f"   [{m.role}] {m.content[:60]}")

        print("\n🎉 Tüm testler başarılı! PostgreSQL entegrasyonu çalışıyor.")

    except Exception as e:
        print(f"❌ Hata: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(test_connection())
