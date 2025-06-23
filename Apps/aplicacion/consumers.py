import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from .models import BarberQueue, Barbero
from .utils import safe_channel_name  # Importación desde utils.py

logger = logging.getLogger(__name__)

class QueueConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.barber_id = None
        try:
            self.barber_id = self.scope['url_route']['kwargs']['barber_id']
            self.barber_id = str(self.barber_id) 
        except KeyError:
            logger.error("ERROR: 'barber_id' no encontrado en los kwargs de la URL del WebSocket.", exc_info=True)
            await self.close(code=4000)
            return
        
        # Usar la función importada desde utils
        cleaned_barber_id = safe_channel_name(self.barber_id)
        if not cleaned_barber_id:
            logger.error(f"ERROR: No se pudo crear un nombre seguro para barber_id: '{self.barber_id}'")
            await self.close(code=4001)
            return

        self.room_group_name = f'queue_{cleaned_barber_id}'
        logger.info(f"Conectando - barber_id: {self.barber_id}, group: {self.room_group_name}")

        try:
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            await self.accept()
            logger.info(f"Conexión WebSocket aceptada para barbero {self.barber_id}")

            # Enviar estado inicial
            await self.send_initial_queue_state()
            
        except TypeError as e:
            logger.critical(f"Error en group_add: {str(e)}", exc_info=True)
            await self.close(code=4002)
        except Exception as e:
            logger.error(f"Error inesperado durante la conexión: {str(e)}", exc_info=True)
            await self.close(code=4003)

    async def send_initial_queue_state(self):
        """Envía el estado inicial de la cola al cliente"""
        current_num = 0
        last_issued_num = 0
        
        try:
            barbero_obj = await sync_to_async(Barbero.objects.get)(id=self.barber_id)
            queue_obj = await sync_to_async(BarberQueue.get_or_create_queue_for_barber)(barbero_obj)
            current_num = queue_obj.current_number
            last_issued_num = queue_obj.last_issued_number
        except Barbero.DoesNotExist:
            logger.warning(f"Barbero con ID {self.barber_id} no encontrado")
        except Exception as e:
            logger.error(f"Error obteniendo estado inicial: {str(e)}", exc_info=True)

        try:
            await self.send(text_data=json.dumps({
                'type': 'queue_update',
                'barber_id': self.barber_id,
                'number': current_num,
                'last_issued_number': last_issued_num
            }))
        except Exception as e:
            logger.error(f"Error enviando estado inicial: {str(e)}", exc_info=True)

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name') and hasattr(self, 'channel_name'):
            logger.info(f"Desconectando del grupo {self.room_group_name}")
            try:
                await self.channel_layer.group_discard(
                    self.room_group_name,
                    self.channel_name
                )
            except Exception as e:
                logger.error(f"Error al abandonar el grupo: {str(e)}", exc_info=True)

    async def queue_update(self, event):
        """Maneja mensajes de actualización de cola enviados al grupo"""
        try:
            await self.send(text_data=json.dumps({
                'type': 'queue_update',
                'barber_id': event['barber_id'],
                'number': event['number'],
                'last_issued_number': event.get('last_issued_number', 0)
            }))
        except Exception as e:
            logger.error(f"Error enviando queue_update: {str(e)}", exc_info=True)

    async def receive(self, text_data):
        """Maneja mensajes recibidos del cliente WebSocket"""
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get('type')

            if message_type == 'reset_counter':
                barber_id = text_data_json.get('barber_id')
                if barber_id:
                    await self.reset_barber_queue(barber_id)
                else:
                    logger.error("Mensaje de reinicio sin barber_id")
                    await self.send_error("Se requiere un 'barber_id' para reiniciar el contador")
        except json.JSONDecodeError:
            logger.error("Mensaje recibido no es JSON válido")
            await self.send_error("Formato de mensaje inválido")
        except Exception as e:
            logger.error(f"Error procesando mensaje: {str(e)}", exc_info=True)
            await self.send_error("Error interno del servidor")

    async def reset_barber_queue(self, barber_id):
        """Reinicia la cola del barbero y notifica al grupo"""
        try:
            # Usar la función safe_channel_name importada
            safe_barber_id = safe_channel_name(barber_id)
            if not safe_barber_id:
                logger.error(f"Barber_id inválido en reset: {barber_id}")
                await self.send_error("ID de barbero inválido")
                return

            barbero_obj = await sync_to_async(Barbero.objects.get)(id=barber_id)
            queue_obj = await sync_to_async(BarberQueue.get_or_create_queue_for_barber)(barbero_obj)
            await sync_to_async(queue_obj.reset_queue)()

            logger.info(f"Cola reiniciada para barbero {barber_id}")

            await self.channel_layer.group_send(
                f'queue_{safe_barber_id}',
                {
                    'type': 'queue_update',
                    'barber_id': barber_id,
                    'number': queue_obj.current_number,
                    'last_issued_number': queue_obj.last_issued_number
                }
            )
        except Barbero.DoesNotExist:
            logger.error(f"Barbero {barber_id} no encontrado")
            await self.send_error(f"Barbero {barber_id} no encontrado")
        except Exception as e:
            logger.error(f"Error reiniciando cola: {str(e)}", exc_info=True)
            await self.send_error("Error reiniciando la cola")

    async def send_error(self, message):
        """Envía un mensaje de error al cliente"""
        try:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': message
            }))
        except Exception as e:
            logger.error(f"No se pudo enviar mensaje de error: {str(e)}")