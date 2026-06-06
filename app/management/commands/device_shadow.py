from paho.mqtt import client as mqtt_client
import datetime
import sys
import zlib
import json
import random


shadow_sub_topic = "$aws/things/+/shadow/get"
# shadow_publish_topic = "$aws/things/ble_" + ID + "/shadow/get/accepted"
 
broker = "cua119013p.oneabbott.com"
port = 1883
username = 'abbott'
password = 'p5NVT2fPw83UnJ'

shadow_payload = {"state": {
    "desired": {
      "fftDataAcquisitionStartTime": [
        "09:00"
      ],
      "sensitivity": 8,
      "samplingFrequency": 12800,
      "fftBlockSize": 16384,
      "sleepTime": "30",
      "getFFT": False,
      "rmsFreq": "10",
      "egdeParams": {
        "sensitivity": 8,
        "samplingFrequency": 4096,
        "sleepTime": "10",
        "xThreshold": 16,
        "yThreshold": 16,
        "zThreshold": 16,
        "counter": 3,
        "alarmTimeout": "4"
      }
    }
   }
  }

    

def publish(client, topic, msg):

    result = client.publish(topic, msg)
    # result: [0, 1]
    status = result[0]
    if status != 0:
        print(f"Failed to send timestamp to topic {topic}")

def connect_mqtt():
    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print("Connected to MQTT Broker!")
        else:
            print("Failed to connect, return code %d\n", rc)
    # Set Connecting Client ID
    client = mqtt_client.Client()
    client.username_pw_set(username, password) 
    client.on_connect = on_connect
    client.connect(broker, port)
    return client

def subscribe(client: mqtt_client):
    def on_message(client, userdata, msg):
        # print("received message on shadow topic", msg.topic)
        shadow_publish_topic = msg.topic+"/accepted"
        payload = json.dumps(shadow_payload)
        publish(client, shadow_publish_topic, payload)
    client.subscribe([(shadow_sub_topic,0)])
    client.on_message = on_message
    
client = connect_mqtt()
subscribe(client)
client.loop_forever()