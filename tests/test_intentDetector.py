import pytest
from aiChatbot.services.intentDetector import isSimpleGreeting

def test_is_simple_greeting():
    assert isSimpleGreeting("merhaba") == True
    assert isSimpleGreeting("Selam") == True
    assert isSimpleGreeting("günaydın") == True
    assert isSimpleGreeting("hi") == True
    assert isSimpleGreeting("good morning") == True
    
    # Should not be simple greeting if it contains a real question
    assert isSimpleGreeting("merhaba jeneratör fiyatları ne kadar") == False
    assert isSimpleGreeting("selam ürünleriniz nelerdir") == False

