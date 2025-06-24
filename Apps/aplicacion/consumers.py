from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from .models import BarberQueue, Barbero
from .utils import safe_channel_name
import json
import logging
import re

logger = logging.getLogger(__name__)

class QueueConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        """Maneja la conexión WebSocket con validación mejorada"""
        try:
            # 1. Validación mejorada del barber_id
            self.barber_id = self._validate_barber_id()
            if not self.barber_id:
                return await self._close_with_error("ID de barbero inválido", 4001)

            # 2. Configuración segura del grupo
            self.room_group_name = f'queue_{self.barber_id}'
            if not self._validate_group_name():
                return await self._close_with_error("Nombre de grupo inválido", 4002)

            # 3. Unión al grupo con verificación
            await self._join_group()
            
            # 4. Enviar estado inicial con manejo de errores
            await self.send_initial_state()

        except Exception as e:
            logger.error(f"Error en conexión: {str(e)}", exc_info=True)
            await self._close_with_error("Error interno del servidor", 4003)

    def _validate_barber_id(self):
        """Valida y limpia el barber_id"""
        try:
            raw_id = str(self.scope['url_route']['kwargs']['barber_id'])
            return safe_channel_name(raw_id)
        except (KeyError, ValueError):
            return None

    def _validate_group_name(self):
        """Valida el nombre del grupo"""
        return re.match(r'^queue_[a-zA-Z0-9\-_\.]{1,100}$', self.room_group_name)

    async def _join_group(self):
        """Maneja la unión al grupo con verificación"""
        if not hasattr(self, 'channel_name') or not isinstance(self.channel_name, str):
            raise ValueError("Channel_name inválido")
        
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()
        logger.info(f"Conexión exitosa al grupo: {self.room_group_name}")

    async def _close_with_error(self, message, code):
        """Cierra la conexión con un mensaje de error"""
        logger.error(f"{message} (código: {code})")
        await self.close(code=code)

    async def send_initial_state(self):
        """Envía el estado inicial con manejo mejorado de errores"""
        try:
            barbero = await sync_to_async(self._get_barber)()
            queue = await sync_to_async(BarberQueue.get_or_create_queue_for_barber)(barbero)
            
            await self._send_queue_state(queue)
            
        except Barbero.DoesNotExist:
            await self._send_error("Barbero no encontrado")
        except Exception as e:
            logger.error(f"Error enviando estado inicial: {str(e)}")
            await self._send_error("Error al obtener estado inicial")

    def _get_barber(self):
        """Obtiene el barbero con validación adicional"""
        return Barbero.objects.get(id=self.barber_id)

    async def _send_queue_state(self, queue):
        """Envía el estado de la cola"""
        await self.send(text_data=json.dumps({
            'type': 'queue_update',
            'barber_id': self.barber_id,
            'number': queue.current_number,
            'last_issued_number': queue.last_issued_number,
            'status': 'success'
        }))

    async def _send_error(self, message):
        """Envía un mensaje de error estandarizado"""
        await self.send(text_data=json.dumps({
            'type': 'error',
            'message': message,
            'status': 'error'
        }))
        await self.close(code=4004)

    async def disconnect(self, close_code):
        """Maneja la desconexión con limpieza mejorada"""
        try:
            if hasattr(self, 'room_group_name'):
                await self.channel_layer.group_discard(
                    self.room_group_name,
                    self.channel_name
                )
            logger.info(f"Desconexión limpia. Código: {close_code}")
        except Exception as e:
            logger.error(f"Error durante desconexión: {str(e)}")

    async def queue_update(self, event):
        """Maneja actualizaciones de cola con validación"""
        try:
            if not all(key in event for key in ['barber_id', 'number']):
                raise ValueError("Datos de evento incompletos")
                
            await self._send_queue_state_update(event)
        except Exception as e:
            logger.error(f"Error procesando actualización: {str(e)}")

    async def _send_queue_state_update(self, event):
        """Envía actualización de estado estandarizada"""
        await self.send(text_data=json.dumps({
            'type': 'queue_update',
            'barber_id': event['barber_id'],
            'number': event['number'],
            'last_issued_number': event.get('last_issued_number', 0),
            'status': 'success'
        }))

    async def receive(self, text_data):
        """Maneja mensajes entrantes con estructura mejorada"""
        try:
            data = json.loads(text_data)
            action = data.get('action')
            
            if action == 'reset_counter':
                await self._handle_reset(data)
            else:
                await self._send_error("Acción no soportada")
                
        except json.JSONDecodeError:
            await self._send_error("JSON inválido")
        except Exception as e:
            logger.error(f"Error procesando mensaje: {str(e)}")
            await self._send_error("Error interno")

    async def _handle_reset(self, data):
        """Maneja el reinicio de cola con validación"""
        barber_id = data.get('barber_id')
        if not barber_id or barber_id != self.barber_id:
            return await self._send_error("ID de barbero inválido")
            
        try:
            await self._reset_queue(barber_id)
        except Exception as e:
            logger.error(f"Error reiniciando cola: {str(e)}")
            await self._send_error("Error al reiniciar cola")

    async def _reset_queue(self, barber_id):
        """Lógica de reinicio de cola encapsulada"""
        barbero = await sync_to_async(Barbero.objects.get)(id=barber_id)
        queue = await sync_to_async(BarberQueue.get_or_create_queue_for_barber)(barbero)
        await sync_to_async(queue.reset_queue)()
        
        await self.channel_layer.group_send(
            f'queue_{barber_id}',
            {
                'type': 'queue_update',
                'barber_id': barber_id,
                'number': queue.current_number,
                'last_issued_number': queue.last_issued_number
            }
        )