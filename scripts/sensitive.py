"""Detect access-data shapes without containing operational values."""
import re
RULES = {
 'access link': r'RequestKey(?:=|%3D|%253D)[A-Za-z0-9%+/]',
 'safelinks wrapper': r'https?://[\w.-]*safelinks\.protection\.outlook\.com/',
 'door code': r'\b(?:door\s+)?(?:code|kod)\s+\**\d{3,8}',
 'insurance agreement number': r'\b(?:Avtalsnummer|agreement number)\s*:\s*\**\d+',
 'insurance control code': r'\b(?:Kontrollkod|control code)\s*:\s*\**\d+',
}
def find_sensitive(text):
    return [(n,kind) for n,line in enumerate(text.splitlines(),1) for kind,pattern in RULES.items() if re.search(pattern,line,re.I)]
