import json
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from .models import BarberQueue, Barbero # Importa ambos modelos

class QueueConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.barber_id = self.scope['url_route']['kwargs']['barber_id']
        self.room_group_name = f'queue_{self.barber_id}'

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

        try:
            barbero_obj = await sync_to_async(Barbero.objects.get)(id=self.barber_id)
            queue_obj = await sync_to_async(BarberQueue.get_or_create_queue_for_barber)(barbero_obj)
            current_num = queue_obj.current_number
            last_issued_num = queue_obj.last_issued_number # <-- Obtener el último emitido
        except Barbero.DoesNotExist:
            current_num = 0
            last_issued_num = 0
            print(f"Barbero con ID {self.barber_id} no encontrado para la cola.")
        except Exception as e:
            current_num = 0
            last_issued_num = 0
            print(f"Error al obtener la cola para barbero {self.barber_id}: {e}")

        await self.send(text_data=json.dumps({
            'type': 'queue_update',
            'barber_id': self.barber_id,
            'number': current_num,
            'last_issued_number': last_issued_num # <-- Enviar también el último emitido
        }))

    async def disconnect(self, close_code):
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
