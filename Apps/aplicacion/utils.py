import re
import logging

logger = logging.getLogger(__name__)

def safe_channel_name(original_name):

    if original_name is None:
        logger.error("El nombre original es None")
        return None
    
    try:
        # Convertir a string si no lo es
        name_str = str(original_name).strip()
        if not name_str:
            logger.error("Cadena vacía después de la conversión")
            return None
        
        # Reemplazar caracteres no permitidos con guión bajo
        # Permitidos: alfanuméricos, guiones (-), guiones bajos (_) y puntos (.)
        safe_name = re.sub(r'[^a-zA-Z0-9\-_.]', '_', name_str)
        
        # Limitar longitud a 99 caracteres (el límite de Channels es 100)
        safe_name = safe_name[:99]
        
        if safe_name != name_str:
            logger.warning(f"Nombre sanitizado: de '{name_str}' a '{safe_name}'")
        
        return safe_name
    except Exception as e:
        logger.error(f"Error sanitizando nombre de canal: {str(e)}", exc_info=True)
        return None