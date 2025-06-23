import re

def safe_channel_name(original_name):
    """
    Sanitiza nombres para canales/grupos. 
    Retorna None si no es válido.
    """
    if not original_name:
        return None
    
    try:
        name_str = str(original_name).strip()
        # Permite letras, números, guiones, puntos y underscores
        safe_name = re.sub(r'[^a-zA-Z0-9\-_.]', '_', name_str)
        safe_name = safe_name[:99]  # Límite de longitud
        
        return safe_name if safe_name else None
    except Exception:
        return None