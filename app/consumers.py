import json
from channels.generic.websocket import AsyncWebsocketConsumer, AsyncConsumer
from asyncio import sleep
import numpy as np

class ChartConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        print("connecteddddddddddddddddddddd")
        await self.accept()
        # for i in range(1,100,1):
        #     await self.send(text_data = json.dumps({'message': np.round((np.random.random()*100),2)}))
        #     await sleep(1)
    async def disconnect(self, close_code):
        await self.close()
        print("DDDDDDDDDDDDDDDDd")
        pass

    async def receive(self, text_data):
        print("here from the receive in consumersssssssssssss", text_data)
        # text_data_json = json.loads(text_data)
        # message = text_data_json['message']

        await self.send(text_data=json.dumps({
            'message': text_data
        }))

        