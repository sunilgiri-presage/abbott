import paho.mqtt.client as mqtt
from django.core.management.base import BaseCommand
# from app.models import CurrentDataMaster  # Import your model
from app import models, serializers
from rest_framework.response import Response
from rest_framework import status
import json
# from app import serializers
import pytz
import datetime
from struct import *
from app.dashboard.process_save_data import saveData
from app.cache import get_mount_data, get_sensor_orientation_data, get_sensor_orientation_data_rms_only
from app.task import saveDataAsync, saveDataAcousticAsync, saveRMSData

username = 'abbott'
password = 'p5NVT2fPw83UnJ'
url = 'localhost'
port = 1883


local_tz = pytz.timezone("Asia/Kolkata") 
    
def get_error_msg(message):
    try:
        errorData = json.loads(json.dumps(message))
        try:
            errorList = []
            count = 1
            for key in sorted(errorData.keys()):
                try:
                    errorList.append("{0}. {1} : {2} <br>".format(count, key.replace('_',' '), errorData[key][0]))
                except:
                    errorList.append("{0}. {1} : {2} <br>".format(count, key.replace('_',' '), errorData[key]))
                count += 1

            errorMsg = "".join(errorList)
            return errorMsg
        except:
            try:
                return str(errorData)
            except:
                return errorData
    except:
        return message
    
    
    
def construct_metadata_format_string():
    f_string = '<'              # little endian
    f_string += 'c' * 18        # macId
    f_string += 'd'             # timestamp
    f_string += 'i'             # blockSize
    f_string += 'f'             # samplingRate
    f_string += 'i'             # sensitivity
    f_string += 'c'             # axis
    f_string += 'f'             #temp
    return f_string


def saveRawData(raw_payload, sensor_type):

    macId_size = 18
    timestamp_size = 8
    blockSize_size = 4
    sampling_rate_size = 4
    sensitivity_size = 4
    axis_size = 1
    temp_size = 4
    total_metadata_size = macId_size + sensitivity_size + timestamp_size + blockSize_size + sampling_rate_size + axis_size + temp_size



    scaling_factor = 1
    g = 9.8

    f_string = construct_metadata_format_string()
    metadata = raw_payload[:total_metadata_size]

    
    decoded_metadata = unpack(f_string, metadata)

    mac_id = "".join(x.decode('utf-8') for x in decoded_metadata[0 : macId_size]).rstrip('\0')
    timestamp = decoded_metadata[-6]
    block_size = decoded_metadata[-5]
    sampling_rate = decoded_metadata[-4]
    sensitivity = decoded_metadata[-3]
    axis = decoded_metadata[-2].decode('utf-8')
    temp = decoded_metadata[-1]
    
    raw_data_format_string = 'h' * block_size
    decoded_raw_data = unpack(raw_data_format_string, raw_payload[total_metadata_size :])
    # print("sensitivity for mac_id ", mac_id, " is ", sensitivity)

    if sensitivity == 8:
        scaling_factor = float(2 ** 12)
    elif sensitivity == 16:
        scaling_factor = float(2 ** 11)
    elif sensitivity == 32:
        scaling_factor = float(2 ** 10)
    elif sensitivity == 64:
        scaling_factor = float(2 ** 9)
        
    if mac_id == "E8:31:CD:38:F4:34":
        scaling_factor = 1
    

        
    raw_values = list(map(float, decoded_raw_data)) 
    raw_values = [x / scaling_factor for x in raw_values]
    #raw_values = [x * g for x in raw_values]
    raw_values = [round(x, 3) for x in raw_values]

    data =  {
        'raw_data'      : raw_values,
        'mac_id'        : sensor_type+'_'+str(mac_id),
        'timestamp'     : timestamp,
        'no_of_samples' : int(block_size),
        'fs'            : int(sampling_rate),
        'axis'          : axis.lower(),
        'temp'          : float(temp)
    }

    macID = data.get("mac_id")
    sensorType = macID.split("_")[0]
    axis = data.get('axis')
    rData = data.get('raw_data')
    samplingFrequency = int(data.get('fs'))
    no_of_samples = int(data.get("no_of_samples"))
    temp = data.get("temp")
    try:
        utc_dt = datetime.datetime.utcfromtimestamp(data.get("timestamp")).replace(tzinfo=pytz.utc)
        local_dt = local_tz.normalize(utc_dt.astimezone(local_tz))
    except:
        res = {"result": False, "message": "Unable to convert timestamp", "mac_id": macID}
        return res
        # return Response({'message':"Unable to convert timestamp."},status=status.HTTP_404_NOT_FOUND)
    data.update({'timestamp':local_dt})

    try:
        # device_data = models.DeviceMountMaster.objects.get(mac_id=macID, is_linked=True)
        # asset_id = device_data.asset_id
        # composite_key = device_data.composite_id
        # mount_id = device_data.id
        # sensorOrientation = device_data.mount_direction


        device_data = get_mount_data(macID)
        # print("here in raw data loop", device_data)
        asset_id = device_data.get('asset_id')
        composite_key = device_data.get('composite_id')
        mount_id = device_data.get('id')
        sensorOrientation = device_data.get('mount_direction')


        # sesnorOrientData = models.SensorPositionMaster.objects.get(sensor_type=sensorType)
        # axisOrientation = sesnorOrientData.orientation.get(sensorOrientation).get(axis)
        axisOrientation = get_sensor_orientation_data(sensorType, sensorOrientation, axis)

    except Exception as e5:
        res = {"result": False, "message": "Unable to fetech device. Contact admin...", "mac_id": macID}
        return res
    
    
    if axis in ['x', 'y', 'z']:
        data.update({'asset_id':asset_id, "composite": composite_key, "axis": axisOrientation})
        saveDataAsync.delay(data, axis, rData, composite_key, samplingFrequency, local_dt, asset_id, no_of_samples, axisOrientation, mount_id, temp)
        res = {"result": True, "message": "Sent to celery", "mac_id": macID}    #need to add acceleration/velocity rms data, data will return from 'saveData' function. Need to update on all occurrence
    elif axis in ['a']:
        data.update({'asset_id':asset_id, "composite": composite_key, "axis": "a"})
        # api_message, api_status = saveDataAcoustic(data, rData, samplingFrequency)
        # return Response({'message':api_message}, status=api_status)
        saveDataAcousticAsync.delay(data, rData, samplingFrequency)
        return Response({'message': 'Saving acoustic data'}, status=status.HTTP_200_OK)
    return res
    



    
def publish(client, topic, msg):

    result = client.publish(topic, msg)
    # result: [0, 1]
    status = result[0]
    if status != 0:
        print(f"Failed to send timestamp to topic {topic}")
    # else:
    #     print(f"Failed to send message to topic {topic}")



class Command(BaseCommand):
    help = 'Listen to MQTT messages and save them to the database'

    def handle(self, *args, **kwargs):
        # Define the MQTT callback function to handle incoming messages
        
        def on_message(client, userdata, message):
            print("----------------------", message.topic)
            if message.topic.startswith("wired/rms/timestamp"):
                # print("here in timestamp loop")
                currentTime = datetime.datetime.now().timestamp()
                payload = {"timestamp": round(currentTime)}
                timestamp_payload = json.dumps(payload)
                publish_topic = "wired/rms/timestamp/accepted"
                publish(client, publish_topic, timestamp_payload)

            elif message.topic.startswith("ble/rms/timestamp"):
                currentTime = datetime.datetime.now().timestamp()
                payload = {"timestamp": round(currentTime)}
                timestamp_payload = json.dumps(payload)
                publish_topic1 = "ble/rms/timestamp/accepted"
                publish(client, publish_topic1, timestamp_payload)


            elif message.topic.startswith("wired/rms/"):
                try:
                    data = json.loads(message.payload.decode())
                    # print("saving rms data", data.get("mac"))
                except:
                    print("Some error in decording data payload")
                    return
                
                response = saveRMSData.delay(data, 'w')

            elif message.topic.startswith("ble/rms/"):
                try:
                    data = json.loads(message.payload.decode())
                    # print("saving rms data", data.get("mac"))
                except:
                    print("Some error in decording data payload")
                    return
                
                response = saveRMSData.delay(data, 'ble')

                # if response.get("result") == False:
                #     print(response.get("message"), "for sensor", response.get("mac_id"))
                # if response.get("result") == True:
                #     macId = response.get("mac_id")
                #     publish_topic = "wired/rms/data/accepted/" + macId
                #     # print("topic to publish data", publish_topic)
                #     payload = json.dumps(response.get("data"))
                #     # print("ooooooooooooooooo", payload)
                #     publish(client, publish_topic, payload)


            elif message.topic.startswith("wired/rawdata/"):
                response = saveRawData(message.payload, 'w')
                if response.get("result") == False:
                    print("error from raw data save function", response.get("message"), "for sensor", response.get("mac_id"))

            elif message.topic.startswith("ble/rawdata/"):
                response = saveRawData(message.payload, 'ble')
                if response.get("result") == False:
                    print("error from raw data save function", response.get("message"), "for sensor", response.get("mac_id"))
            

            elif message.topic.startswith("raw/wireless/"):
                response = saveRawData(message.payload, 'wl')
                if response.get("result") == False:
                    print("error from raw data save function", response.get("message"), "for sensor", response.get("mac_id"))
                

        # Connect to the MQTT broker
        print("Connecting to mqtt client")
        client = mqtt.Client()
        client.username_pw_set(username, password)
        client.connect(url, port)  # need abbott mqtt server details
        print("Connected")  
        client.on_message = on_message


        topic_prefix1 = "wired/rms/"
        wildcard_topic1 = f"{topic_prefix1}+"  # + is the wildcard to match one level

        topic_prefix2 = "wired/rawdata/"
        wildcard_topic2 = f"{topic_prefix2}+"  # + is the wildcard to match one level
    
        topic_prefix3 = "raw/wireless/"
        wildcard_topic3 = f"{topic_prefix3}+"  # + is the wildcard to match one level

        topic_prefix4 = "ble/rms/"
        wildcard_topic4 = f"{topic_prefix4}+"  # + is the wildcard to match one level

        topic_prefix5 = "ble/rawdata/"
        wildcard_topic5 = f"{topic_prefix5}+"  # + is the wildcard to match one level


        client.subscribe([(wildcard_topic1,0), (wildcard_topic2, 0), (wildcard_topic3, 0), (wildcard_topic4, 0), (wildcard_topic5, 0)])

        # client.subscribe([(topic1,0), (topic2, 0)])

        # Start the MQTT client loop to listen for messages
        client.loop_forever()

