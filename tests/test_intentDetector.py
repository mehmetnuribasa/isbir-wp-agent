import pytest
from aiChatbot.services.intentDetector import isSimpleGreeting, isPurePriceQuestion, isGoodbye, removeEchoOpening

def test_is_simple_greeting():
    assert isSimpleGreeting("merhaba") == True
    assert isSimpleGreeting("Selam") == True
    assert isSimpleGreeting("günaydın") == True
    assert isSimpleGreeting("hi") == True
    assert isSimpleGreeting("merhaba nasılsın") == True
    
    # Should not be simple greeting if it contains a real question
    assert isSimpleGreeting("merhaba jeneratör fiyatları ne kadar") == False
    assert isSimpleGreeting("selam ürünleriniz nelerdir") == False

def test_is_pure_price_question():
    assert isPurePriceQuestion("Fiyatı ne kadar?") == True
    assert isPurePriceQuestion("kaç para") == True
    assert isPurePriceQuestion("ücreti nedir") == True
    
    # If it contains features, it's not a pure price question
    assert isPurePriceQuestion("10 kVA jeneratör özellikleri ve fiyatı nedir") == False
    assert isPurePriceQuestion("Hangi jeneratör ne kadar") == False

def test_is_goodbye():
    assert isGoodbye("teşekkürler, sağol") == True
    assert isGoodbye("çok tesekkur ederim") == True
    assert isGoodbye("güle güle") == True
    assert isGoodbye("hayır, bu kadar yeterli bye") == True
    
    assert isGoodbye("merhaba bana yardım et") == False

def test_remove_echo_opening():
    # Echoing user's intent should be removed
    text1 = "Jeneratörler hakkında bilgi almak istiyorsunuz. İşbir jeneratörleri 3 çeşittir."
    assert removeEchoOpening(text1) == "İşbir jeneratörleri 3 çeşittir."
    
    text2 = "Tabii, fiyatlar hakkında bilgi vermekten memnuniyet duyarım. Fiyatlarımız donanıma göre değişir."
    assert removeEchoOpening(text2) == "Fiyatlarımız donanıma göre değişir."
    
    # Should not remove normal sentences
    text3 = "Pro jeneratörlerimiz 13 kVA'dan başlamaktadır."
    assert removeEchoOpening(text3) == text3
