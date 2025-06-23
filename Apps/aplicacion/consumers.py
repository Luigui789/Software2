import json
import logging 
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from .models import BarberQueue, Barbero 
from .utils import safe_channel_name  # Asegúrate de que esta función esté definida en utils.py

logger = logging.getLogger(__name__) 

class QueueConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.barber_id = None
        try:
            self.barber_id = self.scope['url_route']['kwargs']['barber_id']
            self.barber_id = str(self.barber_id) 
        except KeyError:
            logger.error("ERROR: 'barber_id' no encontrado en los kwargs de la URL del WebSocket. Asegúrate de que tu routing.py lo configure y que la URL del cliente sea correcta.", exc_info=True)
            await self.close(code=4000)
            return
        
        cleaned_barber_id = safe_channel_name(self.barber_id)

        if not cleaned_barber_id:
            logger.error(f"ERROR: 'barber_id' original '{self.barber_id}' se convirtió en vacío o inválido después de la limpieza. No se puede crear un nombre de grupo válido.", exc_info=True)
            await self.close(code=4001)
            return

        self.room_group_name = f'queue_{cleaned_barber_id}'

        logger.info(f"DEBUG CHANNELS: Intentando conectar. original_barber_id='{self.barber_id}', cleaned_barber_id='{cleaned_barber_id}', room_group_name='{self.room_group_name}'")
        logger.info(f"DEBUG CHANNELS: channel_name='{self.channel_name}'")

        try:
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
        except TypeError as e:
            logger.critical(f"CRITICAL ERROR CHANNELS: Falló channel_layer.group_add para room_group_name='{self.room_group_name}' con error: {e}", exc_info=True)
            await self.close(code=4002)
            return

        await self.accept() # Si todo lo anterior fue bien, acepta la conexión
        logger.info(f"DEBUG CHANNELS: WebSocket aceptado para barbero {self.barber_id}.")

        current_num = 0
        last_issued_num = 0
        try:
            barbero_obj = await sync_to_async(Barbero.objects.get)(id=self.barber_id)
            logger.info(f"DEBUG CHANNELS: Objeto Barbero {barbero_obj.id} obtenido.")

            queue_obj = await sync_to_async(BarberQueue.get_or_create_queue_for_barber)(barbero_obj)
            logger.info(f"DEBUG CHANNELS: Objeto BarberQueue {queue_obj.id} obtenido/creado. Current: {queue_obj.current_number}, Last Issued: {queue_obj.last_issued_number}")
            
            current_num = queue_obj.current_number
            last_issued_num = queue_obj.last_issued_number
            
        except Barbero.DoesNotExist:
            logger.warning(f"Barbero con ID {self.barber_id} no encontrado para la cola. Inicializando con 0.", exc_info=True)
        except Exception as e:
            logger.error(f"ERROR GENERAL al obtener la cola para barbero {self.barber_id}: {e}", exc_info=True)
        
        try:
            await self.send(text_data=json.dumps({
                'type': 'queue_update',
                'barber_id': self.barber_id,
                'number': current_num,
                'last_issued_number': last_issued_num
            }))
            logger.info(f"DEBUG CHANNELS: Estado inicial de cola enviado al cliente para barbero {self.barber_id}.")
        except Exception as e:
            logger.error(f"ERROR al enviar el estado inicial de la cola al cliente para barbero {self.barber_id}: {e}", exc_info=True)
            await self.close(code=4003)

    async def disconnect(self, close_code):
        logger.info(f"DEBUG CHANNELS: Desconectando del grupo {self.room_group_name} con código {close_code}")
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def queue_update(self, event):
        number = event['number']
        barber_id = event['barber_id']
        last_issued_number = event.get('last_issued_number', 0) 
        await self.send(text_data=json.dumps({
            'type': 'queue_update',
            'barber_id': barber_id,
            'number': number,
            'last_issued_number': last_issued_number 
        }))

    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message_type = text_data_json.get('type')

        if message_type == 'reset_counter':
            barber_id = text_data_json.get('barber_id')
            if barber_id:
                await self.reset_barber_queue(barber_id)
            else:
                logger.error("Error: Se recibió un mensaje de reinicio sin barber_id.") 
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': "Mensaje de reinicio requiere un 'barber_id'."
                }))

    async def reset_barber_queue(self, barber_id):
        try:
            barbero_obj = await sync_to_async(Barbero.objects.get)(id=barber_id)
            queue_obj = await sync_to_async(BarberQueue.get_or_create_queue_for_barber)(barbero_obj)

            await sync_to_async(queue_obj.reset_queue)() 

            logger.info(f"Contador y último número emitido para barbero {barber_id} reseteado a 0.")

            # Usa el mismo método de sanitización para el nombre del grupo
            cleaned_barber_id = safe_channel_name(barber_id)
            room_group_name = f'queue_{cleaned_barber_id}'

            await self.channel_layer.group_send(
                room_group_name,
                {
                    'type': 'queue_update',
                    'barber_id': barber_id,
                    'number': queue_obj.current_number, 
                    'last_issued_number': queue_obj.last_issued_number 
                }
            )

        except Barbero.DoesNotExist:
            logger.error(f"Error: Barbero con ID {barber_id} no encontrado para resetear la cola.", exc_info=True)
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f"Barbero {barber_id} no encontrado para resetear la cola."
            }))
        except Exception as e:
            logger.error(f"Error general al resetear la cola del barbero {barber_id}: {e}", exc_info=True)
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f"Error al resetear la cola para barbero {barber_id}: {str(e)}"
            }))