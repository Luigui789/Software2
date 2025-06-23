import json
import logging 
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from .models import BarberQueue, Barbero # Importa ambos modelos
import re

logger = logging.getLogger(__name__) 

class QueueConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.barber_id = None # Inicializa para seguridad
        try:
            # Intenta obtener el barber_id de los kwargs de la URL
            self.barber_id = self.scope['url_route']['kwargs']['barber_id']
            # Convierte a string para asegurar que no sea un int, None o algo más
            self.barber_id = str(self.barber_id) 
        except KeyError:
            # Registra un error si barber_id no se encuentra en la URL
            logger.error("ERROR: 'barber_id' no encontrado en los kwargs de la URL del WebSocket. Asegúrate de que tu routing.py lo configure y que la URL del cliente sea correcta.")
            await self.close(code=4000) # Código de cierre personalizado para error
            return # Detiene la ejecución del método connect
        
        # --- LÓGICA DE LIMPIEZA Y VALIDACIÓN DEL NOMBRE DEL CANAL/GRUPO ---
        # Remueve cualquier caracter que no sea alfanumérico, guion, guion bajo o punto
        # y reemplázalo con un guion. Trunca a 99 caracteres.
        cleaned_barber_id = re.sub(r'[^a-zA-Z0-9\-_.]', '-', self.barber_id)
        cleaned_barber_id = cleaned_barber_id[:99] # Trunca para cumplir el límite de < 100

        if not cleaned_barber_id: # Si después de la limpieza queda vacío
            logger.error(f"ERROR: 'barber_id' original '{self.barber_id}' se convirtió en vacío o inválido después de la limpieza. No se puede crear un nombre de grupo válido.")
            await self.close(code=4001) # Código de cierre personalizado para ID inválido
            return

        self.room_group_name = f'queue_{cleaned_barber_id}'

        # --- Logs de depuración (¡muy importantes para ver en Railway!) ---
        logger.info(f"DEBUG CHANNELS: Intentando conectar. original_barber_id='{self.barber_id}', cleaned_barber_id='{cleaned_barber_id}', room_group_name='{self.room_group_name}'")
        logger.info(f"DEBUG CHANNELS: channel_name='{self.channel_name}'")

        try:
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
        except TypeError as e:
            logger.critical(f"CRITICAL ERROR CHANNELS: Falló channel_layer.group_add para room_group_name='{self.room_group_name}' con error: {e}")
            await self.close(code=4002) # Código de cierre personalizado para error de group_add
            return

        await self.accept() # Si todo lo anterior fue bien, acepta la conexión

        # ... (el resto de tu código de connect) ...
        try:
            barbero_obj = await sync_to_async(Barbero.objects.get)(id=self.barber_id)
            queue_obj = await sync_to_async(BarberQueue.get_or_create_queue_for_barber)(barbero_obj)
            current_num = queue_obj.current_number
            last_issued_num = queue_obj.last_issued_number
        except Barbero.DoesNotExist:
            current_num = 0
            last_issued_num = 0
            logger.warning(f"Barbero con ID {self.barber_id} no encontrado para la cola. Initializing with 0.")
        except Exception as e:
            current_num = 0
            last_issued_num = 0
            logger.error(f"Error general al obtener la cola para barbero {self.barber_id}: {e}", exc_info=True) # exc_info=True para el traceback completo

        await self.send(text_data=json.dumps({
            'type': 'queue_update',
            'barber_id': self.barber_id,
            'number': current_num,
            'last_issued_number': last_issued_num
        }))

    async def disconnect(self, close_code):
        logger.info(f"DEBUG CHANNELS: Desconectando del grupo {self.room_group_name} con código {close_code}")
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def queue_update(self, event):
        number = event['number']
        barber_id = event['barber_id']
        last_issued_number = event.get('last_issued_number', 0) # <-- Recibir también
        await self.send(text_data=json.dumps({
            'type': 'queue_update',
            'barber_id': barber_id,
            'number': number,
            'last_issued_number': last_issued_number # <-- Enviar también
        }))

    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message_type = text_data_json.get('type')

        if message_type == 'reset_counter':
            barber_id = text_data_json.get('barber_id')
            if barber_id:
                await self.reset_barber_queue(barber_id)
            else:
                print("Error: Se recibió un mensaje de reinicio sin barber_id.")
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': "Mensaje de reinicio requiere un 'barber_id'."
                }))

    async def reset_barber_queue(self, barber_id):
        """
        Lógica para reiniciar ambos contadores de la cola de un barbero específico.
        """
        try:
            barbero_obj = await sync_to_async(Barbero.objects.get)(id=barber_id)
            queue_obj = await sync_to_async(BarberQueue.get_or_create_queue_for_barber)(barbero_obj)

            # Usa el nuevo método reset_queue del modelo
            await sync_to_async(queue_obj.reset_queue)() 

            print(f"Contador y último número emitido para barbero {barber_id} reseteado a 0.")

            # Notificar a todos los clientes en el grupo de este barbero
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'queue_update',
                    'barber_id': barber_id,
                    'number': queue_obj.current_number, # Será 0
                    'last_issued_number': queue_obj.last_issued_number # Será 0
                }
            )

        except Barbero.DoesNotExist:
            print(f"Error: Barbero con ID {barber_id} no encontrado para resetear la cola.")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f"Barbero {barber_id} no encontrado para resetear la cola."
            }))
        except Exception as e:
            print(f"Error general al resetear la cola del barbero {barber_id}: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f"Error al resetear la cola para barbero {barber_id}: {str(e)}"
            }))
