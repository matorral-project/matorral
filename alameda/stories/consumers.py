from asgiref.sync import async_to_sync

from channels.generic.websocket import WebsocketConsumer

import ujson


class InteractionsConsumer(WebsocketConsumer):
    def connect(self):
        async_to_sync(self.channel_layer.group_add)("interactions", self.channel_name)
        self.user = self.scope["user"]
        self.accept()

    def disconnect(self, close_code):
        async_to_sync(self.channel_layer.group_discard)("interactions", self.channel_name)

    def receive(self, text_data):
        text_data_json = ujson.loads(text_data)
        print('Received:', text_data_json)

    def notification(self, event):
        # Send message to WebSocket
        self.send(text_data=ujson.dumps({
            'message': event['message']
        }))

# From a celery task or django view or command I can do:
# ------
# from asgiref.sync import async_to_sync
# from channels.layers import get_channel_layer
# channel_layer = get_channel_layer()
# async_to_sync(channel_layer.group_send)('interactions', {"type": "notification", "message": 'ok'})
