import re

def safe_channel_name(name):
    # Solo permite letras, números, guiones, guiones bajos y puntos, y limita a 99 caracteres
    return re.sub(r'[^a-zA-Z0-9_\-\.]', '-', str(name))[:99]