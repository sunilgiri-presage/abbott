# from turtle import pd
from functools import partial
from django.db.models.base import ModelStateFieldsCacheDescriptor
from rest_framework.parsers import JSONParser
from app import models
from app import serializers
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
import json
import pdb
import numpy as np
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from django.core.serializers.json import DjangoJSONEncoder
import boto3
from datetime import datetime
from pytz import timezone
import pytz
from app.cache import load_mount_data_mapping, load_sensor_orientation_mapping

local_tz = pytz.timezone("Asia/Kolkata")
utc_tz = pytz.utc


AccessID = "AKIAQ3URSO77ADTAF4FT"
SecretKey = "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"
region = "ap-south-1"

iotClient = boto3.client('iot',
                        aws_access_key_id=AccessID,
                        aws_secret_access_key= SecretKey,
                        region_name=region)

shadowClient = boto3.client('iot-data',
                        aws_access_key_id=AccessID,
                        aws_secret_access_key= SecretKey,
                        region_name=region)



#************************************IoT core functions start***********************************

# def createThing(device, org):
#     thingName = "RB_" + device
#     response = iotClient.create_thing(
#         thingName=thingName,
#         )
#     iotData = {
#             'device':device,
#             'thingName':response.get("thingName"),
#             'thingArn':response.get("thingArn"),
#             'thingId':response.get("thingId"),
#             'asset_id_org':org
#                 }
#     return iotData


def updateDeviceShadow(data):
    shadowPayload = data.get("shadowData")
    thing_name = data.get("thingName")
    response = shadowClient.update_thing_shadow(thingName = thing_name, payload = json.dumps(shadowPayload))
    return response

#************************************IoT core functions end***********************************


# Create your views here.

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



#************************************Device Fucntions***********************************
"""changing asset_id and asset_id for new integrated config app (cmms)"""
@api_view(['POST'])
def device_list(request):
    if request.method == 'POST':
        # pdb.set_trace()
        data = JSONParser().parse(request)
        if not data:
            return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
        asset_id = data.get('asset_id')
        comp_code = data.get('comp_id')
        # if comp_code:
        #     device_data_comp_code = models.DeviceModelMaster.objects.filter(org_id=comp_code)
        # else:
        #     pass
        # ********************* handle request from cmms application *********************
        if asset_id:
            device_data = models.DeviceModelMaster.objects.filter(asset_id=asset_id)
            if not device_data:
                return Response({'message':'Device data not found'},status=status.HTTP_404_NOT_FOUND)
        # ********************* handle request from configuration application *********************
        elif not asset_id:
            device_data = models.DeviceModelMaster.objects.filter(org_id=comp_code)
            if not device_data:
                return Response({'message':'Device data not found'},status=status.HTTP_404_NOT_FOUND)
        unlinked_devices = []
        linked_devices = []
        for singleDevice in device_data:
            composite_key = singleDevice.composite_id
            if singleDevice.is_linked:
                # if singleDevice.asset_id == asset_id:
                try:
                    mount_data = models.DeviceMountMaster.objects.get(composite=composite_key)
                except models.DeviceMountMaster.DoesNotExist:
                    continue
                data_serializer = serializers.DeviceMountMasterSerializer(mount_data)
                linked_data = data_serializer.data
                jsondata = json.loads(json.dumps(linked_data))
                linked_devices.append({'mac_id':singleDevice.mac_id,\
                        'mount_location':jsondata['mount_location'],\
                            'mount_type':jsondata['mount_type'],\
                                'mount_material':jsondata['mount_material'],\
                                    'mount_direction':jsondata['mount_direction'],\
                                        'asset_id':singleDevice.asset_id,\
                                            'composite_key':singleDevice.composite_id,\
                                                'is_linked': singleDevice.is_linked})

            else:
                try:
                    mount_data = models.DeviceMountMaster.objects.get(composite=composite_key)
                except models.DeviceMountMaster.DoesNotExist:
                    continue
                data_serializer = serializers.DeviceMountMasterSerializer(mount_data)
                linked_data = data_serializer.data
                jsondata = json.loads(json.dumps(linked_data))
                unlinked_devices.append({'mac_id':singleDevice.mac_id,\
                        'mount_location':jsondata['mount_location'],\
                            'mount_type':jsondata['mount_type'],\
                                'mount_material':jsondata['mount_material'],\
                                    'mount_direction':jsondata['mount_direction'],\
                                        'asset_id':singleDevice.asset_id,\
                                            'composite_key':singleDevice.composite_id,\
                                                'is_linked': singleDevice.is_linked})
        return Response({'unlinked_devices':unlinked_devices,'linked_devices':linked_devices})
        


@api_view(['POST','PUT','DELETE'])
def devices_update(request):
    # pdb.set_trace()
    data = JSONParser().parse(request)
    if not data:
        return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
    try:
        device_data = models.DeviceModelMaster.objects.get(mac_id=data.get('mac_id'))
        data.update({"mac":device_data.mac_id})
    except models.DeviceModelMaster.DoesNotExist:
        return Response({'message':"Device Data not found"},status=status.HTTP_404_NOT_FOUND)
    if request.method == 'POST':
        # try:
        device_data.asset_id = data.get('asset_id')
        try:
            device_mount = models.DeviceMountMaster.objects.get(mac=device_data.mac_id)
            serializer = serializers.DeviceMountMasterSerializer(device_mount, data=data)
        except models.DeviceMountMaster.DoesNotExist:
            serializer = serializers.DeviceMountMasterSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            device_data.save()
            return Response({'message':'Device Added'},status=status.HTTP_200_OK)
        return Response({'message':get_error_msg(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)

        # except:
        #     return Response({'message':'Something went wrong'}, status=status.HTTP_400_BAD_REQUEST)
    elif request.method == 'PUT':
        device_data.asset_id = data.get('asset_id')
        try:
            device_mount = models.DeviceMountMaster.objects.get(mac=device_data.mac_id)
        except models.DeviceMountMaster.DoesNotExist:
            return Response({'message':'Device Mount not found'},status=status.HTTP_404_NOT_FOUND)
        serializer = serializers.DeviceMountMasterSerializer(device_mount, data=data)
        if serializer.is_valid():
            serializer.save()
            device_data.save()
            return Response({'message':'Device Updated'},status=status.HTTP_200_OK)
        return Response({'message':get_error_msg(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        device_data.asset_id = None
        try:
            device_mount = models.DeviceMountMaster.objects.get(mac=device_data.mac_id)
        except models.DeviceMountMaster.DoesNotExist:
            return Response({'message':'Device Mount not found'},status=status.HTTP_404_NOT_FOUND)
        device_data.save()
        device_mount.delete()
        return Response({'message':'Device unlinked successfully'},status=status.HTTP_204_NO_CONTENT)

@api_view(['GET', 'POST'])
def add_devices(request):
    if request.method == 'GET':
        devices = models.DeviceModelMaster.objects.all()
        serializer = serializers.DeviceModelMasterSerializer(devices, many=True)
        return Response(serializer.data)

    elif request.method == 'POST':
        data = JSONParser().parse(request)
        serializer = serializers.DeviceModelMasterSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response({'message':get_error_msg(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
def check_device(request):
    if request.method == 'POST':
        data = JSONParser().parse(request)
        try:
            deviceData = models.DeviceModelMaster.objects.get(composite_id=data.get("composite_key"), is_linked=True)
            return Response({'found':True},status=status.HTTP_200_OK)
        except:
            return Response({'found':False}, status=status.HTTP_400_BAD_REQUEST)


#************************************Hardware Fucntions***********************************

@api_view(['GET', 'POST'])
def hardware_list(request):
    if request.method == 'GET':
        hardwares = models.HardwareMaster.objects.all()
        serializer = serializers.HardwareMasterSerializer(hardwares, many=True)
        return Response(serializer.data)

    elif request.method == 'POST':
        data = JSONParser().parse(request)
        serializer = serializers.HardwareMasterSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response({'message':get_error_msg(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET', 'PUT', 'DELETE'])
def hardware_detail(request, pk):

    try:
        hardware = models.HardwareMaster.objects.get(pk=pk)
    except models.HardwareMaster.DoesNotExist:
        return Response({'message':'Hardware not found'},status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        serializer = serializers.HardwareMasterSerializer(hardware)
        return Response(serializer.data)

    elif request.method == 'PUT':
        data = JSONParser().parse(request)
        serializer = serializers.HardwareMasterSerializer(hardware, data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response({'message':get_error_msg(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        hardware.delete()
        return Response({'message':'Hardware Deleted'},status=status.HTTP_204_NO_CONTENT)


#************************************Device Configuration Fucntions***********************************

@api_view(['POST'])
def device_config(request):
    if request.method == 'POST':
        # try:
            
            data = JSONParser().parse(request)
            if not data:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
            mount_data = data.get('mount_data')
            hardware_data = data.get('hardware')
            firmware_data = data.get('firmware')
            signal_processing_data = data.get('signal_processing')
            fault_data = data.get('faults')
            # bearing_data = fault_data.get('bearing_details')
            gear_data = fault_data.get('gear')
            ac_motor_data = fault_data.get('ac_motor')
            pump_fan_data = fault_data.get('pump_fan')
            # threshold_data = data.get('threshold')
            bearing_details = data.get("bearing_details")
            composite_key = data.get("composite_key")
            mount_id = data.get("mount_id")
            if composite_key:
                [sensorType, macId, asset_id, mount_id]  = composite_key.split('_')
                thingName = sensorType + '_' + macId
                if sensorType == 'ble':
                    edge_data = data.get('ble_edge_params')
                else:
                    edge_data = data.get('edge_params')

            # thres_final_data = {'velocity_rms':threshold_data.get('velocity').get('rms'),'velocity_peak':threshold_data.get('velocity').get('peak'),\
            #     'velocity_peak_to_peak':threshold_data.get('velocity').get('peak_to_peak'),'velocity_kurtosis':threshold_data.get('velocity').get('kurtosis'),\
            #         'acceleration_rms':threshold_data.get('acceleration').get('rms'),'acceleration_peak':threshold_data.get('acceleration').get('peak'),\
            #     'acceleration_peak_to_peak':threshold_data.get('acceleration').get('peak_to_peak'),'acceleration_kurtosis':threshold_data.get('acceleration').get('kurtosis'),\
            #         'displacement_rms':threshold_data.get('displacement').get('rms'),'displacement_peak':threshold_data.get('displacement').get('peak'),\
            #     'displacement_peak_to_peak':threshold_data.get('displacement').get('peak_to_peak'),'displacement_kurtosis':threshold_data.get('displacement').get('kurtosis')}
            try:
                deviceData = models.DeviceMountMaster.objects.get(id=mount_id)
            except:
                return Response({'message':"Mount point not found."},status=status.HTTP_404_NOT_FOUND)
        
            

            mount_data.update({'mount': mount_id, "composite_id":composite_key,'asset_id':deviceData.asset_id})
            edge_data.update({'mount': mount_id, "composite_id":composite_key,'asset_id':deviceData.asset_id})
            hardware_data.update({'mount': mount_id, "composite_id":composite_key,'asset_id':deviceData.asset_id})
            firmware_data.update({'mount': mount_id, "composite_id":composite_key,'asset_id':deviceData.asset_id})
            signal_processing_data.update({'mount': mount_id, "composite_id":composite_key,'asset_id':deviceData.asset_id})
            # bearing_data.update({'mount': mount_id, "composite_id":composite_key,'asset_id':deviceData.asset_id})
            gear_data.update({'mount': mount_id, "composite_id":composite_key,'asset_id':deviceData.asset_id})
            ac_motor_data.update({'mount': mount_id, "composite_id":composite_key,'asset_id':deviceData.asset_id})
            pump_fan_data.update({'mount': mount_id, "composite_id":composite_key,'asset_id':deviceData.asset_id})
            bearing_details.update({'mount': mount_id, "composite_id":composite_key,'asset_id':deviceData.asset_id})
            # thres_final_data.update({"composite":composite_key,'asset_id':deviceData.asset_id})

            # try:
            #     # pdb.set_trace()
            #     thingData = models.AwsIotThingMaster.objects.get(mac_id=data.get('mac_id'))
            # except:
            #     pass

            if firmware_data.get("upload_time"):
                hr = int(firmware_data.get("upload_time").split(":")[0])
                min = int(firmware_data.get("upload_time").split(":")[1])
                localDT = datetime.now(local_tz).replace(hour=hr, minute=min)
                # localDT = utc_tz.normalize(istDT.astimezone(local_tz))
                utcDT = localDT.astimezone(utc_tz)
                formatTime = utcDT.strftime("%H:%M").split(':')
                updateTime = str(formatTime[0]) + ':' +str(formatTime[1])
                firmware_data.update({"upload_time": updateTime})

            if composite_key:
                shadowUpdateData = {
                    "shadowData": {
                        "state": {
                            "desired": {
                                "egdeParams": {

                                }
                            }
                        }
                    },
                    "thingName": thingName
                    }
                if sensorType == 'wl':
                    if firmware_data.get("upload_time"):
                        # next_upload_utC_date = utC_date.replace(hour=utC_date.time().hour+4)  #sleep time for 4 hours static
                        # gmtNHR = next_upload_utC_date.time().hour
                        # gmtNMin = next_upload_utC_date.time().minute
                        # next_upload = str(gmtNHR) + ':' +str(gmtNMin)
                        shadowUpdateData.get('shadowData').get('state').get('desired').update({'fftDataAcquisitionStartTime': updateTime})
                        # shadowUpdateData.get('shadowData').get('state').get('desired').update({'next_upload': next_upload})
                    else:
                        pass
                    if firmware_data.get("sensitivity"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').update({'sensitivity': firmware_data.get("sensitivity")})
                    else:
                        pass
                    if firmware_data.get("sampling_rate"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').update({'samplingFrequency': firmware_data.get("sampling_rate")})
                    else:
                        pass
                    if firmware_data.get("no_of_samples"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').update({'fftBlockSize': firmware_data.get("no_of_samples")})
                    else:
                        pass
                    if firmware_data.get("sleep_time"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').update({'sleepTime': firmware_data.get("sleep_time")})
                        shadowUpdateData.get('shadowData').get('state').get('desired').update({'demo': False})
                    else:
                        pass
                    if firmware_data.get("sampling_rate_edge"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').update({'samplingFrequencyEdge': firmware_data.get("sampling_rate_edge")})
                    else:
                        pass
                    if firmware_data.get("no_of_samples_edge"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').update({'fftBlockSizeEdge': firmware_data.get("no_of_samples_edge")})
                    else:
                        pass

                    ## Setting Edge Paramaters
                    if edge_data.get("alarm_timeout"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').get('egdeParams').update({'alarmTimeout': edge_data.get("alarm_timeout")})
                    else:
                        pass
                    if edge_data.get("counter"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').get('egdeParams').update({'counter': edge_data.get("counter")})
                    else:
                        pass
                    if edge_data.get("sampling_rate"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').get('egdeParams').update({'samplingFrequency': edge_data.get("sampling_rate")})
                    else:
                        pass
                    if edge_data.get("sensitivity"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').get('egdeParams').update({'sensitivity': edge_data.get("sensitivity")})
                    else:
                        pass
                    if edge_data.get("sleep_time"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').get('egdeParams').update({'sleepTime': edge_data.get("sleep_time")})
                    else:
                        pass
                    if edge_data.get("x_threshold"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').get('egdeParams').update({'xThreshold': edge_data.get("x_threshold")})
                    else:
                        pass
                    if edge_data.get("y_threshold"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').get('egdeParams').update({'yThreshold': edge_data.get("y_threshold")})
                    else:
                        pass
                    if edge_data.get("z_threshold"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').get('egdeParams').update({'zThreshold': edge_data.get("z_threshold")})
                    else:
                        pass

                elif sensorType == 'ble':
                    if firmware_data.get("upload_time"):
                        # next_upload_utC_date = utC_date.replace(hour=utC_date.time().hour+4)  #sleep time for 4 hours static
                        # gmtNHR = next_upload_utC_date.time().hour
                        # gmtNMin = next_upload_utC_date.time().minute
                        # next_upload = str(gmtNHR) + ':' +str(gmtNMin)
                        shadowUpdateData.get('shadowData').get('state').get('desired').update({'fftDataAcquisitionStartTime': updateTime})
                        # shadowUpdateData.get('shadowData').get('state').get('desired').update({'next_upload': next_upload})
                    else:
                        pass
                    if firmware_data.get("sensitivity"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').update({'sensitivity': firmware_data.get("sensitivity")})
                    else:
                        pass
                    if firmware_data.get("sampling_rate"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').update({'samplingFrequency': firmware_data.get("sampling_rate")})
                    else:
                        pass
                    if firmware_data.get("no_of_samples"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').update({'fftBlockSize': firmware_data.get("no_of_samples")})
                    else:
                        pass
                    if firmware_data.get("sleep_time"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').update({'sleepTime': firmware_data.get("sleep_time")})
                        shadowUpdateData.get('shadowData').get('state').get('desired').update({'demo': False})
                    else:
                        pass
                    if firmware_data.get("sampling_rate_edge"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').update({'samplingFrequencyEdge': firmware_data.get("sampling_rate_edge")})
                    else:
                        pass
                    if firmware_data.get("no_of_samples_edge"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').update({'fftBlockSizeEdge': firmware_data.get("no_of_samples_edge")})
                    else:
                        pass
                    if firmware_data.get("bleRangeMode"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').update({'bleRangeMode': firmware_data.get("bleRangeMode")})
                    else:
                        pass
                    
                    ## Setting Edge Paramaters


                    ## ------------------------------------------ ##

                    if firmware_data.get("sensitivity"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').get('egdeParams').update({'sensitivity': firmware_data.get("sensitivity")})
                    else:
                        pass
                    if firmware_data.get("sampling_rate_edge"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').get('egdeParams').update({'samplingFrequency': firmware_data.get("sampling_rate_edge")})
                    else:
                        pass
                    if firmware_data.get("rms_data_interval"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').get('egdeParams').update({'sleepTime': firmware_data.get("rms_data_interval")})
                    else:
                        pass
                    if edge_data.get("counter"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').get('egdeParams').update({'counter': edge_data.get("counter")})
                    else:
                        pass
                    if edge_data.get("edgeAlarmTimeOut"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').get('egdeParams').update({'alarmTimeout': edge_data.get("edgeAlarmTimeOut")})
                    else:
                        pass
                    if edge_data.get("acc_rms_x"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').get('egdeParams').update({'acc_rms_x': edge_data.get("acc_rms_x")})
                    else:
                        pass
                    if edge_data.get("acc_rms_y"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').get('egdeParams').update({'acc_rms_y': edge_data.get("acc_rms_y")})
                    else:
                        pass
                    if edge_data.get("acc_rms_z"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').get('egdeParams').update({'acc_rms_z': edge_data.get("acc_rms_z")})
                    else:
                        pass
                    if edge_data.get("velocity_x"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').get('egdeParams').update({'vxrmsThreshold': edge_data.get("velocity_x")})
                    else:
                        pass
                    if edge_data.get("velocity_y"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').get('egdeParams').update({'vyrmsThreshold': edge_data.get("velocity_y")})
                    else:
                        pass
                    if edge_data.get("velocity_z"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').get('egdeParams').update({'vzrmsThreshold': edge_data.get("velocity_z")})
                    else:
                        pass
                    if edge_data.get("temp"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').get('egdeParams').update({'temperature': edge_data.get("temp")})
                    else:
                        pass
                    if edge_data.get("acc_pp_x"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').get('egdeParams').update({'axp2pThreshold': edge_data.get("acc_pp_x")})
                    else:
                        pass
                    if edge_data.get("acc_pp_y"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').get('egdeParams').update({'ayp2pThreshold': edge_data.get("acc_pp_y")})
                    else:
                        pass
                    if edge_data.get("acc_pp_z"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').get('egdeParams').update({'azp2pThreshold': edge_data.get("acc_pp_z")})
                    else:
                        pass
                    if firmware_data.get("sampling_rate_edge"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').get('egdeParams').update({'vibsamplingFrequency': firmware_data.get("sampling_rate_edge")})
                    else:
                        pass
                    if firmware_data.get("acoustic_sampling_rate"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').get('egdeParams').update({'UltramicsamplingFrequency': firmware_data.get("acoustic_sampling_rate")})
                    else:
                        pass


                elif sensorType == 'w':
                    if firmware_data.get("upload_time"):
                        # next_upload_utC_date = utC_date.replace(hour=utC_date.time().hour+4)  #sleep time for 4 hours static
                        # gmtNHR = next_upload_utC_date.time().hour
                        # gmtNMin = next_upload_utC_date.time().minute
                        # next_upload = str(gmtNHR) + ':' +str(gmtNMin)
                        shadowUpdateData.get('shadowData').get('state').get('desired').update({'fftDataAcquisitionStartTime': updateTime})
                        # shadowUpdateData.get('shadowData').get('state').get('desired').update({'next_upload': next_upload})
                    else:
                        pass
                    if firmware_data.get("sensitivity"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').update({'sensitivity': firmware_data.get("sensitivity")})
                    else:
                        pass
                    if firmware_data.get("sampling_rate"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').update({'samplingFrequency': firmware_data.get("sampling_rate")})
                    else:
                        pass
                    if firmware_data.get("no_of_samples"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').update({'fftBlockSize': firmware_data.get("no_of_samples")})
                    else:
                        pass
                    if firmware_data.get("sleep_time"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').update({'sleepTime': firmware_data.get("sleep_time")})
                    else:
                        pass
                    if firmware_data.get("wired_rms_freq"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').update({'rmsFreq': firmware_data.get("wired_rms_freq")})
                    else:
                        pass

                    ## Setting Edge Paramaters
                    if edge_data.get("alarm_timeout"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').get('egdeParams').update({'alarmTimeout': edge_data.get("alarm_timeout")})
                    else:
                        pass
                    if edge_data.get("counter"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').get('egdeParams').update({'counter': edge_data.get("counter")})
                    else:
                        pass
                    if edge_data.get("sampling_rate"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').get('egdeParams').update({'samplingFrequency': edge_data.get("sampling_rate")})
                    else:
                        pass
                    if edge_data.get("sensitivity"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').get('egdeParams').update({'sensitivity': edge_data.get("sensitivity")})
                    else:
                        pass
                    if edge_data.get("sleep_time"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').get('egdeParams').update({'sleepTime': edge_data.get("sleep_time")})
                    else:
                        pass
                    if edge_data.get("x_threshold"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').get('egdeParams').update({'xThreshold': edge_data.get("x_threshold")})
                    else:
                        pass
                    if edge_data.get("y_threshold"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').get('egdeParams').update({'yThreshold': edge_data.get("y_threshold")})
                    else:
                        pass
                    if edge_data.get("z_threshold"):
                        shadowUpdateData.get('shadowData').get('state').get('desired').get('egdeParams').update({'zThreshold': edge_data.get("z_threshold")})
                    else:
                        pass


            # pdb.set_trace()
            try:
                mountData = models.DeviceMountMaster.objects.get(id=mount_id)
                mountSerializer = serializers.DeviceMountMasterSerializer(mountData, data=mount_data)
            except:
                mountSerializer = serializers.DeviceMountMasterSerializer(data=mount_data)

            try:
                try:
                    edgeData = models.EdgeCalculationParams.objects.filter(composite_id=composite_key).order_by('-last_update')[0]
                    edgeSerializer = serializers.EdgeCalculationParamsSerializer(edgeData, data=edge_data)
                except:
                    edgeData = models.EdgeCalculationParams.objects.filter(mount=mount_id).order_by('-last_update')[0]
                    edgeSerializer = serializers.EdgeCalculationParamsSerializer(edgeData, data=edge_data)
            except:
                edgeSerializer = serializers.EdgeCalculationParamsSerializer(data=edge_data)

            try:
                try:
                    hardwareData = models.HardwareMaster.objects.filter(composite_id=composite_key).order_by('-last_update')[0]
                    hardwareSerializer = serializers.HardwareMasterSerializer(hardwareData, data=hardware_data)
                except:
                    hardwareData = models.HardwareMaster.objects.filter(mount=mount_id).order_by('-last_update')[0]
                    hardwareSerializer = serializers.HardwareMasterSerializer(hardwareData, data=hardware_data)
            except:
                hardwareSerializer = serializers.HardwareMasterSerializer(data=hardware_data)

            try:
                try:
                    firmwareData = models.FirmwareMaster.objects.filter(composite_id=composite_key).order_by('-last_update')[0]
                    firmwareSerializer = serializers.FirmwareMasterSerializer(firmwareData, data=firmware_data)
                except:
                    firmwareData = models.FirmwareMaster.objects.filter(mount=mount_id).order_by('-last_update')[0]
                    firmwareSerializer = serializers.FirmwareMasterSerializer(firmwareData, data=firmware_data)
            except:
                firmwareSerializer = serializers.FirmwareMasterSerializer(data=firmware_data)

            try:
                try:
                    signalData = models.SignalProcessingMaster.objects.filter(composite_id=composite_key).order_by('-last_update')[0]
                    signalSerializer = serializers.SignalProcessingMasterSerializer(signalData, data=signal_processing_data)
                except:
                    signalData = models.SignalProcessingMaster.objects.filter(mount=mount_id).order_by('-last_update')[0]
                    signalSerializer = serializers.SignalProcessingMasterSerializer(signalData, data=signal_processing_data)
            except:
                signalSerializer = serializers.SignalProcessingMasterSerializer(data=signal_processing_data)

            try:
                try:
                    bearingData = models.BearingDetailMaster.objects.filter(composite_id=composite_key).order_by('-last_update')[0]
                    bearingSerializer = serializers.BearingDetailMasterSerializer(bearingData, data=bearing_details)
                except:
                    bearingData = models.BearingDetailMaster.objects.filter(mount=mount_id).order_by('-last_update')[0]
                    bearingSerializer = serializers.BearingDetailMasterSerializer(bearingData, data=bearing_details)
            except:
                bearingSerializer = serializers.BearingDetailMasterSerializer(data=bearing_details)

            try:
                try:
                    gearData = models.GearFaultsMaster.objects.filter(composite_id=composite_key).order_by('-last_update')[0]
                    gearSerializer = serializers.GearFaultsMasterSerializer(gearData, data=gear_data)
                except:
                    gearData = models.GearFaultsMaster.objects.filter(mount=mount_id).order_by('-last_update')[0]
                    gearSerializer = serializers.GearFaultsMasterSerializer(gearData, data=gear_data)
            except:
                gearSerializer = serializers.GearFaultsMasterSerializer(data=gear_data)

            try:
                try:
                    acMotorData = models.ACMotorFaultsMaster.objects.filter(composite_id=composite_key).order_by('-last_update')[0]
                    acMotorSerializer = serializers.ACMotorFaultsMasterSerializer(acMotorData, data=ac_motor_data)
                except:
                    acMotorData = models.ACMotorFaultsMaster.objects.filter(mount=mount_id).order_by('-last_update')[0]
                    acMotorSerializer = serializers.ACMotorFaultsMasterSerializer(acMotorData, data=ac_motor_data)
            except:
                acMotorSerializer = serializers.ACMotorFaultsMasterSerializer(data=ac_motor_data)

            try:
                try:
                    pumpFanData = models.PumpFanFaultsMaster.objects.filter(composite_id=composite_key).order_by('-last_update')[0]
                    pumpFanSerializer = serializers.PumpFanFaultsMasterSerializer(pumpFanData, data=pump_fan_data)
                except:
                    pumpFanData = models.PumpFanFaultsMaster.objects.filter(mount=mount_id).order_by('-last_update')[0]
                    pumpFanSerializer = serializers.PumpFanFaultsMasterSerializer(pumpFanData, data=pump_fan_data)
            except:
                pumpFanSerializer = serializers.PumpFanFaultsMasterSerializer(data=pump_fan_data)

            if hardwareSerializer.is_valid():
                if firmwareSerializer.is_valid():
                    if signalSerializer.is_valid():
                        if bearingSerializer.is_valid():
                            if gearSerializer.is_valid():
                                if acMotorSerializer.is_valid():
                                    if pumpFanSerializer.is_valid():
                                        if mountSerializer.is_valid():
                                            if edgeSerializer.is_valid():
                                                hardwareSerializer.save()
                                                firmwareSerializer.save()
                                                signalSerializer.save()
                                                bearingSerializer.save()
                                                gearSerializer.save()
                                                acMotorSerializer.save()
                                                pumpFanSerializer.save()
                                                mountSerializer.save()
                                                edgeSerializer.save()
                                                if composite_key:
                                                    updateDeviceShadow(shadowUpdateData)
                                                return Response({'message':"Device Configuration Completed!"}, status=status.HTTP_201_CREATED)
                                            return Response(get_error_msg(edgeSerializer.errors), status=status.HTTP_400_BAD_REQUEST)
                                        return Response(get_error_msg(mountSerializer.errors), status=status.HTTP_400_BAD_REQUEST)
                                    return Response(get_error_msg(pumpFanSerializer.errors), status=status.HTTP_400_BAD_REQUEST)
                                return Response(get_error_msg(acMotorSerializer.errors), status=status.HTTP_400_BAD_REQUEST)
                            return Response(get_error_msg(gearSerializer.errors), status=status.HTTP_400_BAD_REQUEST)
                        return Response(get_error_msg(bearingSerializer.errors), status=status.HTTP_400_BAD_REQUEST)
                    return Response(get_error_msg(signalSerializer.errors), status=status.HTTP_400_BAD_REQUEST)
                return Response(get_error_msg(firmwareSerializer.errors), status=status.HTTP_400_BAD_REQUEST)
            return Response(get_error_msg(hardwareSerializer.errors), status=status.HTTP_400_BAD_REQUEST)
        # except:
        #      return Response({'message':"Something went wrong, kindly try again later."},status=status.HTTP_404_NOT_FOUND)

@api_view(['POST'])
def get_device_config(request):
    if request.method == 'POST':
        # pdb.set_trace()
        data = JSONParser().parse(request)
        if not data:
            return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
        composite_key = data.get("composite_key")
        mountForeignKey = data.get("mount_id")


        finalData = {"composite_key":composite_key, "mountForeignKey":mountForeignKey}
        # pdb.set_trace()
        ########################### end point is created and sensor is mapped ###########################
        # if composite_key:
        #     try:
        #         deviceData = models.DeviceModelMaster.objects.get(composite_id=composite_key)
        #     except:
        #         return Response({'message':"Device not found."},status=status.HTTP_404_NOT_FOUND)
        #     try:
        #         mountData = models.DeviceMountMaster.objects.get(composite_id=composite_key)
        #         mountSerializer = serializers.DeviceMountMasterSerializer(mountData)
        #         jsondata = json.loads(json.dumps(mountSerializer.data))
        #         del jsondata['asset_id']
        #         finalData.update({'mount':jsondata})
        #     except:
        #         jsondata = {"mount_location":"", "mount_type":"", "mount_material": "", "mount_direction": ""}
        #         finalData.update({'mount':jsondata})

        #     try:
        #         edgeData = models.EdgeCalculationParams.objects.get(composite_id=composite_key)
        #         edgeSerializer = serializers.EdgeCalculationParamsSerializer(edgeData)
        #         jsondata = json.loads(json.dumps(edgeSerializer.data))
        #         del jsondata['asset_id']
        #         finalData.update({'edge':jsondata})
        #     except:
        #         jsondata = {"sampling_rate": "","sleep_time": "","sensitivity": "","x_threshold": "","y_threshold": "",\
        #                         "z_threshold": "","counter": "","alarm_timeout": "", "wired_rms_freq": ""}
        #         finalData.update({'edge':jsondata})


        #     try:
        #         hardwareData = models.HardwareMaster.objects.get(composite_id=composite_key)
        #         hardwareSerializer = serializers.HardwareMasterSerializer(hardwareData)
        #         jsondata = json.loads(json.dumps(hardwareSerializer.data))
        #         del jsondata['asset_id']
        #         finalData.update({'hardware':jsondata})
        #     except:
        #         jsondata = {"hardware_type":"","hardware_components":[]}
        #         finalData.update({'hardware':jsondata})
        #     try:
        #         firmwareData = models.FirmwareMaster.objects.get(composite_id=composite_key)
        #         firmwareSerializer = serializers.FirmwareMasterSerializer(firmwareData)
        #         jsondata = json.loads(json.dumps(firmwareSerializer.data))


        #         hr = int(jsondata.get("upload_time").split(":")[0])
        #         min = int(jsondata.get("upload_time").split(":")[1])
        #         istDT = datetime.now(pytz.timezone('UTC')).replace(hour=hr, minute=min)
        #         # localDT = utc_tz.normalize(istDT.astimezone(local_tz))
        #         localDT = istDT.astimezone(local_tz)
        #         formatTime = localDT.strftime("%H:%M").split(':')
        #         # gmtHR = localDT.time().hour
        #         # gmtMin = localDT.time().minute
        #         updateTime = str(formatTime[0]) + ':' +str(formatTime[1])
        #         jsondata.update({"upload_time": updateTime})

        #         del jsondata['asset_id']
        #         finalData.update({'firmware':jsondata})
        #     except:
        #         jsondata = {"sampling_rate":None,"no_of_samples":None,"upload_time":None,"sleep_time":None, "sensitivity":None, "wired_rms_freq": None}
        #         finalData.update({'firmware':jsondata})

        #     try:
        #         signalData = models.SignalProcessingMaster.objects.get(composite_id=composite_key)
        #         signalSerializer = serializers.SignalProcessingMasterSerializer(signalData)
        #         jsondata = json.loads(json.dumps(signalSerializer.data))
        #         del jsondata['asset_id']
        #         finalData.update({'signal_processing':jsondata})
        #     except:
        #         jsondata = {"high_pass":None,"low_pass":None,"vibration_twf":"",\
        #             "vib_fcutoff":"","vib_sampling_rate":None,"vib_fmax":None,\
        #                 "vib_no_of_samples":None,"vib_freq_resolution":None,"freq_spec_waterfall":None,\
        #                     "acc_fcutoff":"","acc_sampling_rate":None,"acc_fmax":None,\
        #                         "acc_no_of_samples":None,"acc_freq_resolution":None,"acc_rms":None,\
        #                             "rpm":None,"battery_cut_off":None,"battery_unstable_current":None,\
        #                                 "battery_unstable_samples":None,"battery_max_cycle":None,\
        #                                     "rul_power_coeff":"","rul_bound_limit":"",\
        #                                         "rul_ffa_rpm":None,"rul_ffa_ffr":None,"rul_ffa_max_har_count":None,\
        #                                             "rul_ffa_min_accp_rpm":None,"rul_ffa_max_accp_rpm":None,\
        #                                                 "rul_learning_cond":None}
        #         finalData.update({'signal_processing':jsondata})

        #     faultsData = {}
        #     try:
        #         bearingData = models.BearingFaultsMaster.objects.get(composite_id=composite_key)
        #         bearingSerializer = serializers.BearingFaultsMasterSerializer(bearingData)
        #         jsondata = json.loads(json.dumps(bearingSerializer.data))
        #         del jsondata['asset_id']
        #         faultsData.update({'bearing':jsondata})
        #     except:
        #         jsondata = {"fault":False,"misalignment_unbalance":False,"looseness":False,"speed":"constant",\
        #             "bpfo":None,"bpfi":None,"bsf":None,"ftf":None,"fault_amp_thres":None,"bpfo_coeff":None,\
        #                 "bpfi_coeff":None,"bsf_coeff":None,"misalig_amp_thres":None,"unbalance_amp_thres":None,\
        #                     "looseness_amp_thres":None}
        #         faultsData.update({'bearing':jsondata})
        #     try:
        #         gearData = models.GearFaultsMaster.objects.get(composite_id=composite_key)
        #         gearSerializer = serializers.GearFaultsMasterSerializer(gearData)
        #         jsondata = json.loads(json.dumps(gearSerializer.data))
        #         del jsondata['asset_id']
        #         faultsData.update({'gear':jsondata})
        #     except:
        #         jsondata = {"fault":False,"misalignment_unbalance":False,"looseness":False,"constant_speed":False,\
        #             "no_of_gear_teeth":None,"gear_ratio":None,"gmp":None,"misalig_amp_thres":None,\
        #                 "unbalance_amp_thres":None,"looseness_amp_thres":None}
        #         faultsData.update({'gear':jsondata})
        #     try:
        #         acMotorData = models.ACMotorFaultsMaster.objects.get(composite_id=composite_key)
        #         acMotorSerializer = serializers.ACMotorFaultsMasterSerializer(acMotorData)
        #         jsondata = json.loads(json.dumps(acMotorSerializer.data))
        #         del jsondata['asset_id']
        #         faultsData.update({'ac_motor':jsondata})
        #     except:
        #         jsondata = {"fault":False,"misalignment_unbalance":False,"looseness":False,"line_freq":None,\
        #             "rotor_amp_thres":None,"stator_amp_thres":None,"misalig_amp_thres":None,"unbalance_amp_thres":None,\
        #                 "looseness_amp_thres":None}
        #         faultsData.update({'ac_motor':jsondata})
        #     try:
        #         pumpFanData = models.PumpFanFaultsMaster.objects.get(composite_id=composite_key)
        #         pumpFanSerializer = serializers.PumpFanFaultsMasterSerializer(pumpFanData)
        #         jsondata = json.loads(json.dumps(pumpFanSerializer.data))
        #         del jsondata['asset_id']
        #         faultsData.update({'pump_fan':jsondata})
        #     except:
        #         jsondata = {"fault":False,"misalignment_unbalance":False,"looseness":False,"vanes_no_lower":None,\
        #             "vanes_no_upper":None,"vpf_amp_thres":None,"vane_fault_amp_thres":None,"misalig_amp_thres":None,\
        #                 "unbalance_amp_thres":None,"looseness_amp_thres":None}
        #         faultsData.update({'pump_fan':jsondata})

        #     try:
        #         bearingData = models.BearingDetailMaster.objects.get(composite_id=composite_key)
        #         bearingDataSerializer = serializers.BearingDetailMasterSerializer(bearingData)
        #         jsondata = json.loads(json.dumps(bearingDataSerializer.data))
        #         del jsondata['asset_id']
        #         faultsData.update({'bearing_details':jsondata})
        #     except:
        #         jsondata = {'bpfo':None, 'bpfi':None, 'bsf':None, 'ftf':None, 'bearing_number':None}
        #         faultsData.update({'bearing_details':jsondata})
            
        #     finalData.update({'faults':faultsData})
        #     return Response({'config':finalData}, status=status.HTTP_200_OK)

        ########################### end point is created but sensor not mapped ###########################
        if mountForeignKey:
            try:
                try:
                    mountData = models.DeviceMountMaster.objects.get(id=mountForeignKey)
                    mountData.online = mountData.sensorstatusnotifications_set.all()
                    sensorStatusObject =  mountData.sensorstatusnotifications_set.all()
                    if len(sensorStatusObject) > 0:
                        mountData.online = sensorStatusObject.order_by('-creation_date')[0].online
                    else:
                        mountData.online = "Status not available"
                    mountSerializer = serializers.DeviceMountMasterSerializer(mountData)
                    jsondata = json.loads(json.dumps(mountSerializer.data))
                    del jsondata['asset_id']
                    finalData.update({'mount':jsondata})
                except:
                    mountData = models.DeviceMountMaster.objects.get(composite_id=composite_key)
                    mountData.online = mountData.sensorstatusnotifications_set.all()
                    sensorStatusObject =  mountData.sensorstatusnotifications_set.all()
                    if len(sensorStatusObject) > 0:
                        mountData.online = sensorStatusObject.order_by('-creation_date')[0].online
                    else:
                        mountData.online = "Status not available"
                    mountSerializer = serializers.DeviceMountMasterSerializer(mountData)
                    jsondata = json.loads(json.dumps(mountSerializer.data))
                    del jsondata['asset_id']
                    finalData.update({'mount':jsondata})
            except:
                jsondata = {"mount_location":None, "mount_type":None, "mount_material": None, "mount_direction": None}
                finalData.update({'mount':jsondata})

            try:
                try:
                    edgeData = models.EdgeCalculationParams.objects.get(mount=mountForeignKey)
                    edgeSerializer = serializers.EdgeCalculationParamsSerializer(edgeData)
                    jsondataStr = json.dumps(edgeSerializer.data, cls=DjangoJSONEncoder)
                    jsondata = json.loads(jsondataStr)
                    # jsondata = json.loads(json.dumps(edgeSerializer.data))
                    del jsondata['asset_id']
                    finalData.update({'edge':jsondata})
                except:
                    edgeData = models.EdgeCalculationParams.objects.filter(composite_id=composite_key).order_by('-last_update')[0]
                    edgeSerializer = serializers.EdgeCalculationParamsSerializer(edgeData)
                    jsondataStr = json.dumps(edgeSerializer.data, cls=DjangoJSONEncoder)
                    jsondata = json.loads(jsondataStr)
                    # jsondata = json.loads(json.dumps(edgeSerializer.data))
                    del jsondata['asset_id']
                    finalData.update({'edge':jsondata})
            except:
                jsondata = {"sampling_rate": None,"sleep_time": None,"sensitivity": None,"x_threshold": None,"y_threshold": None,\
                                "z_threshold": None,"counter": None,"alarm_timeout": None, "wired_rms_freq": None}
                finalData.update({'edge':jsondata})

            try:
                try:
                    hardwareData = models.HardwareMaster.objects.get(mount=mountForeignKey)
                    hardwareSerializer = serializers.HardwareMasterSerializer(hardwareData)
                    jsondataStr = json.dumps(hardwareSerializer.data, cls=DjangoJSONEncoder)
                    jsondata = json.loads(jsondataStr)
                    # jsondata = json.loads(json.dumps(hardwareSerializer.data))
                    del jsondata['asset_id']
                    finalData.update({'hardware':jsondata})
                except:
                    hardwareData = models.HardwareMaster.objects.filter(composite_id=composite_key).order_by('-last_update')[0]
                    hardwareSerializer = serializers.HardwareMasterSerializer(hardwareData)
                    jsondataStr = json.dumps(hardwareSerializer.data, cls=DjangoJSONEncoder)
                    jsondata = json.loads(jsondataStr)
                    # jsondata = json.loads(json.dumps(hardwareSerializer.data))
                    del jsondata['asset_id']
                    finalData.update({'hardware':jsondata})
            except:
                jsondata = {"hardware_type":None,"hardware_components":[]}
                finalData.update({'hardware':jsondata})

            try:
                try:
                    firmwareData = models.FirmwareMaster.objects.get(mount=mountForeignKey)
                    firmwareSerializer = serializers.FirmwareMasterSerializer(firmwareData)
                    jsondataStr = json.dumps(firmwareSerializer.data, cls=DjangoJSONEncoder)
                    jsondata = json.loads(jsondataStr)
                    # jsondata = json.loads(json.dumps(firmwareSerializer.data))

                    if jsondata.get("upload_time"):
                        hr = int(jsondata.get("upload_time").split(":")[0])
                        min = int(jsondata.get("upload_time").split(":")[1])
                        istDT = datetime.now(pytz.timezone('UTC')).replace(hour=hr, minute=min)
                        # localDT = utc_tz.normalize(istDT.astimezone(local_tz))
                        localDT = istDT.astimezone(local_tz)
                        formatTime = localDT.strftime("%H:%M").split(':')
                        # gmtHR = localDT.time().hour
                        # gmtMin = localDT.time().minute
                        updateTime = str(formatTime[0]) + ':' +str(formatTime[1])
                        jsondata.update({"upload_time": updateTime})
                    else:
                        jsondata.update({"upload_time": None})

                    del jsondata['asset_id']
                    finalData.update({'firmware':jsondata})
                except:
                    firmwareData = models.FirmwareMaster.objects.filter(composite_id=composite_key).order_by('-last_update')[0]
                    firmwareSerializer = serializers.FirmwareMasterSerializer(firmwareData)
                    jsondataStr = json.dumps(firmwareSerializer.data, cls=DjangoJSONEncoder)
                    jsondata = json.loads(jsondataStr)
                    # jsondata = json.loads(json.dumps(firmwareSerializer.data))

                    if jsondata.get("upload_time"):
                        hr = int(jsondata.get("upload_time").split(":")[0])
                        min = int(jsondata.get("upload_time").split(":")[1])
                        istDT = datetime.now(pytz.timezone('UTC')).replace(hour=hr, minute=min)
                        # localDT = utc_tz.normalize(istDT.astimezone(local_tz))
                        localDT = istDT.astimezone(local_tz)
                        formatTime = localDT.strftime("%H:%M").split(':')
                        # gmtHR = localDT.time().hour
                        # gmtMin = localDT.time().minute
                        updateTime = str(formatTime[0]) + ':' +str(formatTime[1])
                        jsondata.update({"upload_time": updateTime})
                    else:
                        jsondata.update({"upload_time": None})

                    del jsondata['asset_id']
                    finalData.update({'firmware':jsondata})
            except:
                jsondata = {"sampling_rate":None,"no_of_samples":None,"upload_time":None,"sleep_time":None, "sensitivity":None, "wired_rms_freq": None}
                finalData.update({'firmware':jsondata})
                
            try:
                try:
                    signalData = models.SignalProcessingMaster.objects.get(mount=mountForeignKey)
                    signalSerializer = serializers.SignalProcessingMasterSerializer(signalData)
                    jsondataStr = json.dumps(signalSerializer.data, cls=DjangoJSONEncoder)
                    jsondata = json.loads(jsondataStr)
                    # jsondata = json.loads(json.dumps(signalSerializer.data))
                    del jsondata['asset_id']
                    finalData.update({'signal_processing':jsondata})
                except:
                    signalData = models.SignalProcessingMaster.objects.filter(composite_id=composite_key).order_by('-last_update')[0]
                    signalSerializer = serializers.SignalProcessingMasterSerializer(signalData)
                    jsondataStr = json.dumps(signalSerializer.data, cls=DjangoJSONEncoder)
                    jsondata = json.loads(jsondataStr)
                    # jsondata = json.loads(json.dumps(signalSerializer.data))
                    del jsondata['asset_id']
                    finalData.update({'signal_processing':jsondata})
            except:
                jsondata = {"high_pass":None,"low_pass":None,"vibration_twf":None,\
                    "vib_fcutoff":None,"vib_sampling_rate":None,"vib_fmax":None,\
                        "vib_no_of_samples":None,"vib_freq_resolution":None,"freq_spec_waterfall":None,\
                            "acc_fcutoff":None,"acc_sampling_rate":None,"acc_fmax":None,\
                                "acc_no_of_samples":None,"acc_freq_resolution":None,"acc_rms":None,\
                                    "rpm":None,"battery_cut_off":None,"battery_unstable_current":None,\
                                        "battery_unstable_samples":None,"battery_max_cycle":None,\
                                            "rul_power_coeff":None,"rul_bound_limit":None,\
                                                "rul_ffa_rpm":None,"rul_ffa_ffr":None,"rul_ffa_max_har_count":None,\
                                                    "rul_ffa_min_accp_rpm":None,"rul_ffa_max_accp_rpm":None,\
                                                        "rul_learning_cond":None}
                finalData.update({'signal_processing':jsondata})

            faultsData = {}
            try:
                try:
                    bearingData = models.BearingFaultsMaster.objects.get(mount_id=mountForeignKey)
                    bearingSerializer = serializers.BearingFaultsMasterSerializer(bearingData)
                    jsondataStr = json.dumps(bearingSerializer.data, cls=DjangoJSONEncoder)
                    jsondata = json.loads(jsondataStr)
                    # jsondata = json.loads(json.dumps(bearingSerializer.data))
                    del jsondata['asset_id']
                    faultsData.update({'bearing':jsondata})
                except:
                    bearingData = models.BearingFaultsMaster.objects.filter(composite_id=composite_key).order_by('-last_update')[0]
                    bearingSerializer = serializers.BearingFaultsMasterSerializer(bearingData)
                    jsondataStr = json.dumps(bearingSerializer.data, cls=DjangoJSONEncoder)
                    jsondata = json.loads(jsondataStr)
                    # jsondata = json.loads(json.dumps(bearingSerializer.data))
                    del jsondata['asset_id']
                    faultsData.update({'bearing':jsondata})
            except:
                jsondata = {"fault":False,"misalignment_unbalance":False,"looseness":False,"speed":"constant",\
                    "bpfo":None,"bpfi":None,"bsf":None,"ftf":None,"fault_amp_thres":None,"bpfo_coeff":None,\
                        "bpfi_coeff":None,"bsf_coeff":None,"misalig_amp_thres":None,"unbalance_amp_thres":None,\
                            "looseness_amp_thres":None}
                faultsData.update({'bearing':jsondata})

            try:
                try:
                    gearData = models.GearFaultsMaster.objects.get(mount=mountForeignKey)
                    gearSerializer = serializers.GearFaultsMasterSerializer(gearData)
                    jsondataStr = json.dumps(gearSerializer.data, cls=DjangoJSONEncoder)
                    jsondata = json.loads(jsondataStr)
                    # jsondata = json.loads(json.dumps(gearSerializer.data))
                    del jsondata['asset_id']
                    faultsData.update({'gear':jsondata})
                except:
                    gearData = models.GearFaultsMaster.objects.filter(composite_id=composite_key).order_by('-last_update')[0]
                    gearSerializer = serializers.GearFaultsMasterSerializer(gearData)
                    jsondataStr = json.dumps(gearSerializer.data, cls=DjangoJSONEncoder)
                    jsondata = json.loads(jsondataStr)
                    # jsondata = json.loads(json.dumps(gearSerializer.data))
                    del jsondata['asset_id']
                    faultsData.update({'gear':jsondata})
            except:
                jsondata = {"fault":False,"misalignment_unbalance":False,"looseness":False,"constant_speed":False,\
                    "no_of_gear_teeth":None,"gear_ratio":None,"gmp":None,"misalig_amp_thres":None,\
                        "unbalance_amp_thres":None,"looseness_amp_thres":None}
                faultsData.update({'gear':jsondata})

            try:
                try:
                    acMotorData = models.ACMotorFaultsMaster.objects.get(mount=mountForeignKey)
                    acMotorSerializer = serializers.ACMotorFaultsMasterSerializer(acMotorData)
                    jsondataStr = json.dumps(acMotorSerializer.data, cls=DjangoJSONEncoder)
                    jsondata = json.loads(jsondataStr)
                    # jsondata = json.loads(json.dumps(acMotorSerializer.data))
                    del jsondata['asset_id']
                    faultsData.update({'ac_motor':jsondata})
                except:
                    acMotorData = models.ACMotorFaultsMaster.objects.filter(composite_id=composite_key).order_by('-last_update')[0]
                    acMotorSerializer = serializers.ACMotorFaultsMasterSerializer(acMotorData)
                    jsondataStr = json.dumps(acMotorSerializer.data, cls=DjangoJSONEncoder)
                    jsondata = json.loads(jsondataStr)
                    # jsondata = json.loads(json.dumps(acMotorSerializer.data))
                    del jsondata['asset_id']
                    faultsData.update({'ac_motor':jsondata})
            except:
                jsondata = {"fault":False,"misalignment_unbalance":False,"looseness":False,"line_freq":None,\
                    "rotor_amp_thres":None,"stator_amp_thres":None,"misalig_amp_thres":None,"unbalance_amp_thres":None,\
                        "looseness_amp_thres":None}
                faultsData.update({'ac_motor':jsondata})

            try:
                try:
                    pumpFanData = models.PumpFanFaultsMaster.objects.get(mount=mountForeignKey)
                    pumpFanSerializer = serializers.PumpFanFaultsMasterSerializer(pumpFanData)
                    jsondataStr = json.dumps(pumpFanSerializer.data, cls=DjangoJSONEncoder)
                    jsondata = json.loads(jsondataStr)
                    # jsondata = json.loads(json.dumps(pumpFanSerializer.data))
                    del jsondata['asset_id']
                    faultsData.update({'pump_fan':jsondata})
                except:
                    pumpFanData = models.PumpFanFaultsMaster.objects.filter(composite_id=composite_key).order_by('-last_update')[0]
                    pumpFanSerializer = serializers.PumpFanFaultsMasterSerializer(pumpFanData)
                    jsondataStr = json.dumps(pumpFanSerializer.data, cls=DjangoJSONEncoder)
                    jsondata = json.loads(jsondataStr)
                    # jsondata = json.loads(json.dumps(pumpFanSerializer.data))
                    del jsondata['asset_id']
                    faultsData.update({'pump_fan':jsondata})
            except:
                jsondata = {"fault":False,"misalignment_unbalance":False,"looseness":False,"vanes_no_lower":None,\
                    "vanes_no_upper":None,"vpf_amp_thres":None,"vane_fault_amp_thres":None,"misalig_amp_thres":None,\
                        "unbalance_amp_thres":None,"looseness_amp_thres":None}
                faultsData.update({'pump_fan':jsondata})

            try:
                try:
                    bearingData = models.BearingDetailMaster.objects.get(mount=mountForeignKey)
                    bearingDataSerializer = serializers.BearingDetailMasterSerializer(bearingData)
                    jsondataStr = json.dumps(bearingDataSerializer.data, cls=DjangoJSONEncoder)
                    jsondata = json.loads(jsondataStr)
                    del jsondata['asset_id']

                    finalData.update({'bearing_details':jsondata})
                except:
                    bearingData = models.BearingDetailMaster.objects.filter(composite_id=composite_key).order_by('-last_update')[0]
                    bearingDataSerializer = serializers.BearingDetailMasterSerializer(bearingData)
                    jsondataStr = json.dumps(bearingDataSerializer.data, cls=DjangoJSONEncoder)
                    jsondata = json.loads(jsondataStr)
                    del jsondata['asset_id']
                    finalData.update({'bearing_details':jsondata})
            except:
                jsondata = {'bpfo':None, 'bpfi':None, 'bsf':None, 'ftf':None, 'bearing_number':None}
                finalData.update({'bearing_details':jsondata})
            
            finalData.update({'faults':faultsData})
            return Response({'config':finalData}, status=status.HTTP_200_OK)
        return Response({'message':'Data coolection point not correct'}, status=status.HTTP_409_CONFLICT)
        
        

@api_view(['GET', 'POST'])
def get_firmware_config(request):
    if request.method == 'GET':
        # Sampling rate, time of fetching data, no.of samples, sleep time
        data = {
            "sampling_rate": 25600,
            "data_fetch_time" : "12:30",
            "no_of_samples": 25600,
            "data_fetch_freq": 5
        }
        return Response(data, status=status.HTTP_200_OK)
    else:
        return Response({'message':'Something went Wrong'},status=status.HTTP_404_NOT_FOUND)


# @api_view(['POST', 'PUT'])
# def add_sensor(request):
#     if request.method == 'POST':
#         try:
#             # pdb.set_trace()
#             data = JSONParser().parse(request)
#             if not data:
#                 return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
#             if data.get("sensor_type") == 'wireless':
#                 macID = 'wl_' + data.get('mac_id')
#             elif data.get("sensor_type") == 'wired':
#                 macID = 'w_' + data.get('mac_id')
            
#             composite_key = macID + '_' + data.get("asset_id")
#             sensorData = {"composite_id":composite_key, "mac_id": macID, "asset_id": data.get("asset_id"), "org_id": data.get("org_id"), \
#                             "is_linked": True}
#             mountData = {"composite":composite_key, "asset_id": data.get("asset_id"), 'mount_location': data.get("mount_location"), \
#                             'mount_type': data.get("mount_type"),'mount_material': data.get("mount_material"),\
#                                 'mount_direction': data.get("mount_direction")}
#             existingCompositeKey = models.DeviceModelMaster.objects.filter(composite_id=composite_key)
#             if not existingCompositeKey:
#                 # compositeKeyRow = existingCompositeKey[0]
#                 sensorSerializer = serializers.DeviceModelMasterSerializer(data=sensorData)
#                 mountSerializer = serializers.DeviceMountMasterSerializer(data=mountData)
#                 if sensorSerializer.is_valid():
#                     sensorSerializer.save()
#                 else:
#                     return Response({'message':get_error_msg(sensorSerializer.errors)}, status=status.HTTP_400_BAD_REQUEST)  
#                 if mountSerializer.is_valid():
#                     mountSerializer.save()
#                 else:
#                     return Response({'message':get_error_msg(mountSerializer.errors)}, status=status.HTTP_400_BAD_REQUEST) 
#                 # return Response(mountSerializer.data, status=status.HTTP_201_CREATED)
#             else:
#                 pass

#             existingSensor = models.DeviceModelMaster.objects.filter(mac_id=macID)
#             if existingSensor:
#                 for row in existingSensor:
#                     de_link = {"is_linked": False}
#                     existingModelSerializerDeLink = serializers.DeviceModelMasterSerializer(row, data=de_link, partial=True)
#                     if existingModelSerializerDeLink.is_valid():
#                         existingModelSerializerDeLink.save()
#                 for compositeRow in existingSensor:
#                     if compositeRow.composite_id == composite_key:
#                         re_link = {"is_linked": True}
#                         updatemountData = mountData
#                         del updatemountData['composite']
#                         existingMountModel = models.DeviceMountMaster.objects.get(composite=composite_key)
#                         existingMountSerializer = serializers.DeviceMountMasterSerializer(existingMountModel, data=updatemountData, partial=True)
#                         existingModelSerializerReLink = serializers.DeviceModelMasterSerializer(compositeRow, data=re_link, partial=True)
#                         if existingModelSerializerReLink.is_valid():
#                             existingModelSerializerReLink.save()
#                         else:
#                             return Response({'message':get_error_msg(existingModelSerializerReLink.errors)}, status=status.HTTP_400_BAD_REQUEST)                            
#                         if existingMountSerializer.is_valid():
#                             existingMountSerializer.save()
#                             return Response(existingMountSerializer.data, status=status.HTTP_201_CREATED)
#                         else:
#                             return Response({'message':get_error_msg(existingMountSerializer.errors)}, status=status.HTTP_400_BAD_REQUEST)  
#         except:
#             return Response({'message':'Something went worong, please try after sometime'},status=status.HTTP_404_NOT_FOUND)


@api_view(['POST', 'PUT'])
def add_sensor(request):
    if request.method == 'POST':
        try:
            # pdb.set_trace()
            data = JSONParser().parse(request)
            if not data:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
            mount_id = data.get("mount_id")
            sensor_type = data.get("sensor_type")
            mac_id = data.get('mac_id')
            org_id = data.get("comp_id")
            asset_id = data.get("asset_id")
            mount_type = data.get("mount_type")
            mount_material = data.get("mount_material")
            mount_direction = data.get("mount_direction")

            if sensor_type == 'wireless':
                composite_key = 'wl_' + mac_id + '_' + asset_id + '_' + str(mount_id)
                macId = 'wl_' + mac_id
                sampling_rate = 12800
                no_of_samples = 16384
                sleep_time = '5'
                sensitivity = 8
                edge_sleep_time = '2'
                egde_counter = 3 
                egde_alarm_timeout = '4'
                egde_sampling_rate = 12800
                egde_sensitivity = 8
                x_threshold = 2
                y_threshold = 2
                z_threshold = 2
                wired_rms_freq = None
                
            elif sensor_type == 'wired':
                composite_key = 'w_' + mac_id + '_' + asset_id + '_' + str(mount_id)
                macId = 'w_' + mac_id
                sampling_rate = 12800
                no_of_samples = 16384
                sleep_time = '4'
                sensitivity = 8
                edge_sleep_time = '10'
                egde_counter = 3 
                egde_alarm_timeout = '4'
                egde_sampling_rate = 4096
                egde_sensitivity = 8
                x_threshold = 2
                y_threshold = 2
                z_threshold = 2
                wired_rms_freq = '10'

            elif sensor_type == 'portable':
                composite_key = 'p_' + mac_id + '_' + asset_id + '_' + str(mount_id)
                macId = 'p_' + mac_id
                sampling_rate = 12800
                no_of_samples = 16384
                sleep_time = '5'
                sensitivity = 8
                edge_sleep_time = '2'
                egde_counter = 3 
                egde_alarm_timeout = '4'
                egde_sampling_rate = 12800
                egde_sensitivity = 8
                x_threshold = 2
                y_threshold = 2
                z_threshold = 2
                wired_rms_freq = None

            elif sensor_type == 'bluetooth':
                composite_key = 'ble_' + mac_id + '_' + asset_id + '_' + str(mount_id)
                macId = 'ble_' + mac_id
                sampling_rate = 12800
                no_of_samples = 16384
                sleep_time = '5'
                sensitivity = 8
                edge_sleep_time = '2'
                egde_counter = 3 
                egde_alarm_timeout = '4'
                egde_sampling_rate = 12800
                egde_sensitivity = 8
                x_threshold = 2
                y_threshold = 2
                z_threshold = 2
                wired_rms_freq = None

            existingSensor = models.DeviceMountMaster.objects.filter(mac_id=macId)
            if existingSensor:
                for row in existingSensor:
                    row.is_linked = False
                    row.save()
            
            try:
                existingMountData = models.DeviceMountMaster.objects.get(id=mount_id)
                existingMountData.mount_type = mount_type
                existingMountData.mount_material = mount_material
                existingMountData.mount_direction = mount_direction
                existingMountData.composite_id = composite_key
                existingMountData.is_linked = True
                existingMountData.mac_id = macId
                existingMountData.save()
            except:
                result = load_mount_data_mapping()
                return Response({'message':'Something went wrong while saving sensor mount data.'},status=status.HTTP_404_NOT_FOUND)

            # saving composite key against existing rpm high pass/low pass filter and bearing data if available
            try:
                existingSignalProcessingData = models.SignalProcessingMaster.objects.get(mount_id=mount_id)
                existingSignalProcessingData.composite_id = composite_key
                existingSignalProcessingData.high_pass = 10
                existingSignalProcessingData.low_pass = 6000
                existingSignalProcessingData.save()
            except:
                pass

            try:
                existingBearingDetail = models.BearingDetailMaster.objects.get(mount_id = mount_id)
                existingBearingDetail.composite_id = composite_key
                existingBearingDetail.save()
            except:
                pass

            # finding existing last saved config settings against given mac_id
            try:
                macLookup = "_{0}_".format(mac_id)
                existingFirmwareData = models.FirmwareMaster.objects.filter(composite_id__contains=macLookup).order_by('-last_update')
                lastSavedFirmwareData = existingFirmwareData[0]
                sampling_rate = lastSavedFirmwareData.sampling_rate
                no_of_samples = lastSavedFirmwareData.no_of_samples
                sensitivity = lastSavedFirmwareData.sensitivity
                sleep_time = lastSavedFirmwareData.sleep_time
                wired_rms_freq = lastSavedFirmwareData.wired_rms_freq
            except:
                pass

            try:
                macLookup = "_{0}_".format(mac_id)
                existingEdgeData = models.EdgeCalculationParams.objects.filter(composite_id__contains=macLookup).order_by('-last_update')
                lastSavedEdgeData = existingEdgeData[0]
                edge_sleep_time = lastSavedEdgeData.sleep_time
                egde_counter = lastSavedEdgeData.counter
                egde_alarm_timeout = lastSavedEdgeData.alarm_timeout
                egde_sampling_rate = lastSavedEdgeData.sampling_rate
                egde_sensitivity = lastSavedEdgeData.sensitivity
                x_threshold = lastSavedEdgeData.x_threshold
                y_threshold = lastSavedEdgeData.y_threshold
                z_threshold = lastSavedEdgeData.z_threshold
            except:
                pass
            
            try:
                existingFirmwareCompositeData = models.FirmwareMaster.objects.filter(composite_id=composite_key)
                if len(existingFirmwareCompositeData) > 0:
                    result = load_mount_data_mapping()
                    return Response({"message": "Sensor attached successfully."}, status=status.HTTP_200_OK)
                else:

                    # saving default configuration setting as per device shadow created while registring sensor
                    try:
                        firmwareData = {
                            'composite_id': composite_key,
                            'sampling_rate': sampling_rate,
                            'no_of_samples': no_of_samples, 
                            'sensitivity': sensitivity,
                            'sleep_time': sleep_time,
                            'asset_id': asset_id,
                            'mount': mount_id,
                            'wired_rms_freq': wired_rms_freq
                            }
                    except:
                        result = load_mount_data_mapping()
                        return Response({'message':'Something went wrong with firmware data.'},status=status.HTTP_404_NOT_FOUND)
                    
                    try:
                        edgeData = {
                            'composite_id': composite_key,
                            'sleep_time': edge_sleep_time,
                            'counter': egde_counter,
                            'alarm_timeout': egde_alarm_timeout ,
                            'sampling_rate': egde_sampling_rate, 
                            'sensitivity': egde_sensitivity,
                            'x_threshold': x_threshold,
                            'y_threshold': y_threshold,
                            'z_threshold': z_threshold,
                            'asset_id': asset_id, 
                            'mount': mount_id
                            }
                    except:
                        result = load_mount_data_mapping()
                        return Response({'message':'Something went wrong with edge firmware data.'},status=status.HTTP_404_NOT_FOUND)

                firmwareDataSerializer = serializers.FirmwareMasterSerializer(data=firmwareData)
                if firmwareDataSerializer.is_valid():
                    edgeDataSerializer = serializers.EdgeCalculationParamsSerializer(data=edgeData)
                    if edgeDataSerializer.is_valid():
                        edgeDataSerializer.save()
                        firmwareDataSerializer.save()
                        result = load_mount_data_mapping()
                        return Response({"message": "Sensor attached successfully.", "composite_id": existingMountData.composite_id}, status=status.HTTP_200_OK)
                    result = load_mount_data_mapping()
                    return Response({'message':get_error_msg(edgeDataSerializer.errors)},status=status.HTTP_404_NOT_FOUND)
                result = load_mount_data_mapping()
                return Response({'message':get_error_msg(firmwareDataSerializer.errors)},status=status.HTTP_404_NOT_FOUND)
            except:
                result = load_mount_data_mapping()
                return Response({'message':'Something went wrong, please try after sometime.'},status=status.HTTP_404_NOT_FOUND)
        except:
            result = load_mount_data_mapping()
            return Response({'message':'Something went wrong, please try after sometime.'},status=status.HTTP_404_NOT_FOUND)



@api_view(['POST', 'PUT'])
def unmapMapSensor(request):
    if request.method == 'POST':
        try:
            # pdb.set_trace()
            data = JSONParser().parse(request)
            if not data:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
            mac_id = data.get("mac_id")
            composite_key  = data.get("composite_key")
            asset_id = data.get("asset_id")
            mount_location = data.get("mount_location")
            point_name = data.get("point_name")
            mount_id = data.get("mount_id")
            mount_direction = data.get("mount_direction")

            existingSensor = models.DeviceMountMaster.objects.filter(mac_id=mac_id)
            
            try:
                unMapObject = existingSensor.update(is_linked=False)
            except:
                pass
            existingMountData = models.DeviceMountMaster.objects.get(id=mount_id)
            if existingMountData:
                existingMountData.composite_id = composite_key
                existingMountData.mount_direction = mount_direction
                existingMountData.mount_location = mount_location
                existingMountData.is_linked = True
                existingMountData.mac_id = mac_id
                existingMountData.save()
            
            return Response({'message': 'sensor mapped successfully'},status=status.HTTP_200_OK)

        except:
            return Response({'message':'Something went wrong, please try after sometime'},status=status.HTTP_404_NOT_FOUND)



@api_view(['POST'])
def GetAssetCount(request):
    try:
        data = JSONParser().parse(request)
        if not data:
            return Response({'message': 'Json data not found'}, status=status.HTTP_404_NOT_FOUND)
        account_id = data.get("account_id")
        try:
            # pdb.set_trace()
            mapped_sensors = models.DeviceModelMaster.objects.filter(org_id=account_id, is_linked=True)
            sen_count = mapped_sensors.count()
            asset_count = mapped_sensors.distinct("asset_id").count()
            final_data = {"sensor_count": sen_count, "asset_count": asset_count}
            return Response({"data":final_data}, status=status.HTTP_200_OK)
        except:
            return Response({'message':'No data found'}, status=status.HTTP_404_NOT_FOUND)

    except:
        return Response({'message':'Something went wrong. Contact admin...'},status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
def GetSensorConfigurations(request):
    try:
        data = JSONParser().parse(request)
        if not data:
            return Response({'message': 'Json data not found'}, status=status.HTTP_404_NOT_FOUND)
        composite_key = data.get("composite_key")
        try:
            # pdb.set_trace()
            mapped_sensors = models.DeviceMountMaster.objects.get(composite_id=composite_key)
            final_data = serializers.DeviceMountMasterSerializer(mapped_sensors)
            jsondata = json.loads(json.dumps(final_data.data))
            return Response({"data":jsondata}, status=status.HTTP_200_OK)
        except:
            return Response({'message':'No data found'}, status=status.HTTP_404_NOT_FOUND)

    except:
        return Response({'message':'Something went wrong. Contact admin...'},status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
def UpdateSensorConfigurations(request):
    try:
        data = JSONParser().parse(request)
        if not data:
            return Response({'message': 'Json data not found'}, status=status.HTTP_404_NOT_FOUND)
    except:
        pass


@api_view(['POST'])
def EndPointAPI(request):
    if request.method == 'POST':
        data = JSONParser().parse(request)
        if not data:
            return Response({'message': 'Json data not found'}, status=status.HTTP_404_NOT_FOUND)
        pointName = data.get("point_name")
        mountLocation = data.get("mount_location")
        mountType = data.get("mount_type")
        mountMaterial = data.get("mount_material")
        mountDirection = data.get("mount_direction")
        assetId = data.get("asset_id")
        orgId = data.get("org_id")
        rpm = data.get("rpm")
        bpfo = data.get("bpfo")
        bpfi = data.get("bpfi")
        bsf = data.get("bsf")
        ftf = data.get("ftf")
        bearing_number = data.get("bearing_number")
        try:
            endPointData = {'point_name':pointName, 'mount_location': mountLocation, 'mount_type': mountType,\
                'mount_material': mountMaterial, 'mount_direction': mountDirection, 'asset_id': assetId, 'org_id': orgId}
        except:
            return Response({'message':'Something went wrong with endpoint data.'},status=status.HTTP_404_NOT_FOUND)
        
        try:
            bearingData = {'bpfo':bpfo, 'bpfi':bpfi, 'bsf':bsf, 'ftf':ftf, 'bearing_number':bearing_number, 'asset_id': assetId}
        except:
            return Response({'message':'Something went wrong with bearing data.'},status=status.HTTP_404_NOT_FOUND)  
         
        try:
            rpmData = {'rpm':rpm, 'high_pass': None, 'low_pass': None, 'asset_id': assetId}
        except:
            return Response({'message':'Something went wrong with rpm data.'},status=status.HTTP_404_NOT_FOUND) 
        

        try:
            existingData = models.DeviceMountMaster.objects.get(point_name=pointName, mount_location=mountLocation, asset_id=assetId)
        except:
            existingData = None
        if existingData:
            return Response({'message':'Data collection point with similar name already exits on this asset, kindly input some other name or change measuring point location to proceed.'}, status=status.HTTP_409_CONFLICT)
        else:
            # endPointSerializer = serializers.DeviceMountMasterSerializer(data=endPointData)
            # if endPointSerializer.is_valid():
            # endPointSerializer.save()
            # print("-------------", endPointSerializer.data)
            item = models.DeviceMountMaster(point_name= pointName, mount_location= mountLocation, mount_type= mountType,\
                mount_material= mountMaterial, mount_direction= mountDirection, asset_id= assetId, org_id= orgId)
            item.save()
            savedData = models.DeviceMountMaster.objects.get(point_name=pointName, mount_location=mountLocation, asset_id=assetId)
            mountForeignKey = savedData.id
            bearingData.update({'mount': mountForeignKey})
            rpmData.update({'mount':mountForeignKey})
            bearingDataSerializer = serializers.BearingDetailMasterSerializer(data=bearingData)
            if bearingDataSerializer.is_valid():
                rpmDataSerializer = serializers.SignalProcessingMasterSerializer(data=rpmData)
                if rpmDataSerializer.is_valid():
                    bearingDataSerializer.save()
                    rpmDataSerializer.save()
                    return Response({"message": "End Point created successfully.", "endpoint_id": item.id}, status=status.HTTP_200_OK)
                return Response({'message':get_error_msg(rpmDataSerializer.errors)},status=status.HTTP_404_NOT_FOUND)
            return Response({'message':get_error_msg(bearingDataSerializer.errors)},status=status.HTTP_404_NOT_FOUND)
            # else:
                # return Response({'message':get_error_msg(endPointSerializer.errors)},status=status.HTTP_404_NOT_FOUND)
    


@api_view(['DELETE'])
def DeleteEndPointAPI(request, pk):
    if request.method == 'DELETE':
        endPointData = models.DeviceMountMaster.objects.get(id=pk)
        endPointData.delete()
        return Response({"message": "End Point deleted successfully."}, status=status.HTTP_200_OK)



@api_view(['POST'])
def getAllEndPoints(request):
    if request.method == 'POST':
        data = JSONParser().parse(request)
        if not data:
            return Response({'message': 'Json data not found'}, status=status.HTTP_404_NOT_FOUND)
        asset_id_list = data.get("asset_id")
        deviceData = models.DeviceMountMaster.objects.filter(asset_id__in = asset_id_list).order_by('id')

        if len(deviceData) > 0:
            final_data = []
            for single_device in deviceData:

                try:
                    latest_status = single_device.sensorstatusnotifications_set.latest('last_update')
                    single_device.online = latest_status.online
                except models.SensorStatusNotifications.DoesNotExist:
                    single_device.online = "Status not available"

                serial_data = serializers.DeviceMountMasterSerializer(single_device)
                jsondata = json.loads(json.dumps(serial_data.data))
                jsondata.update({"id":single_device.id})
                final_data.append(jsondata)
        else:
            return Response({'message': "No end points found against selected asset."},status=status.HTTP_404_NOT_FOUND)

        jsondata = json.loads(json.dumps(data))
        return Response({"data":final_data}, status=status.HTTP_200_OK)
    


@api_view(['POST'])
def getAllEndPointsMobile(request):
    if request.method == 'POST':
        data = JSONParser().parse(request)
        if not data:
            return Response({'message': 'Json data not found'}, status=status.HTTP_404_NOT_FOUND)
        asset_id_list = data.get("asset_id")
        deviceData = models.DeviceMountMaster.objects.filter(asset_id__in = asset_id_list).order_by('id')

        if len(deviceData) > 0:
            final_data = [{"composite_id": row.composite_id, "point_name": row.point_name,\
                          "mount_location": row.mount_location, "mount_direction": row.mount_direction,\
                            "asset_id": row.asset_id, "mac_id": row.mac_id, "mount_id": row.id, "image": row.image} for row in deviceData]
            # for single_device in deviceData:

                # if single_device.composite_id:
                #     serial_data = serializers.DeviceMountMasterSerializer(single_device)
                #     jsondata = json.loads(json.dumps(serial_data.data))
                #     jsondata.update({"id":single_device.id})
                #     final_data.append(jsondata)

        else:
            final_data = []
        # jsondata = json.loads(json.dumps(data))

        return Response({"data":final_data}, status=status.HTTP_200_OK)
    

# @api_view(['POST', 'GET'])
# def SensorOrientation(request):
#     if request.method == 'POST':
#         data = JSONParser().parse(request)
#         if not data:
#             return Response({'message': 'Json data not found'}, status=status.HTTP_404_NOT_FOUND)

#         sensor_orient_data = data
#         sensor_orient_data_serializer = serializers.SensorOrientationMasterSerializer(data=sensor_orient_data)

#         if sensor_orient_data_serializer.is_valid():
#             sensor_orient_data_serializer.save()
#             return Response({'message':"All Data Saved"}, status=status.HTTP_201_CREATED)
#         return Response({'message':get_error_msg(sensor_orient_data_serializer.errors)},status=status.HTTP_404_NOT_FOUND)


#     elif request.method == 'GET':
#         orient_data = models.SensorOrientationMaster.objects.all().values()
#         return Response({"data":orient_data}, status=status.HTTP_200_OK)
    


@api_view(['POST', 'GET'])
def SensorOrientation(request):
    if request.method == 'POST':
        data = JSONParser().parse(request)
        if not data:
            return Response({'message': 'Json data not found'}, status=status.HTTP_404_NOT_FOUND)

        sensor_orient_data = data
        sensor_orient_data_serializer = serializers.SensorPositionMasterSerializer(data=sensor_orient_data)

        if sensor_orient_data_serializer.is_valid():
            sensor_orient_data_serializer.save()
            mapping = load_sensor_orientation_mapping()
            return Response({'message':"All Data Saved"}, status=status.HTTP_201_CREATED)
        return Response({'message':get_error_msg(sensor_orient_data_serializer.errors)},status=status.HTTP_404_NOT_FOUND)


    elif request.method == 'GET':
        orient_data = models.SensorOrientationMaster.objects.all().values()
        return Response({"data":orient_data}, status=status.HTTP_200_OK)
        


@api_view(['POST'])
def GetRMSDataPortable(request):
    if request.method == 'POST':
        try:
            data = JSONParser().parse(request)
            if not data:
                return Response({'message': 'Json data not found'}, status=status.HTTP_404_NOT_FOUND)
            composite_key = data.get("composite_key")
            thing_name = '_'.join(composite_key.split('_')[:2])

            shadowData = {
                "state": {
                    "desired": {
                        "getFFT": "true",
                    }
                }
            }

            shadowResponse = shadowClient.update_thing_shadow(thingName = thing_name, payload = json.dumps(shadowData))

            if shadowResponse.get('ResponseMetadata').get('HTTPStatusCode') == 200:
                return Response({'message': 'Device shadow update'}, status=status.HTTP_200_OK)
            else:
                return Response({'message': 'Something went wrong, kindly contact admin.'}, status=status.HTTP_404_NOT_FOUND)
        except:
            return Response({'message': 'Something went wrong, kindly contact admin.'}, status=status.HTTP_404_NOT_FOUND)

    

@api_view(['POST'])
def updateEndPointImage(request):
    if request.method == 'POST':
        try:
            data = JSONParser().parse(request)
            if not data:
                return Response({'message': 'Json data not found'}, status=status.HTTP_404_NOT_FOUND)
            
            imagePath = data.get("imagePath")
            mount_id = data.get("mount_id")

            existingMountData = models.DeviceMountMaster.objects.get(id=mount_id)
            if existingMountData:
                existingMountData.image = imagePath
                existingMountData.save()

            return Response({'message': 'Image updated successfully.'},status=status.HTTP_200_OK)
        except:
            return Response({'message': 'Something went wrong, kindly contact admin.'}, status=status.HTTP_404_NOT_FOUND)



@api_view(['PATCH'])
def updateEndPointName(request):
    if request.method == 'PATCH':
        try:
            data = JSONParser().parse(request)
            if not data:
                return Response({'message': 'Json data not found'}, status=status.HTTP_404_NOT_FOUND)
            
            name = data.get("name")
            location = data.get("location")
            mount_id = data.get("mount_id")
            requestedName = name + '-' + location

            existingMountData = models.DeviceMountMaster.objects.get(id=mount_id)
            if existingMountData:
                allEndpointsData = models.DeviceMountMaster.objects.filter(asset_id=existingMountData.asset_id)
                existingEndpointName = [i.point_name+'-'+i.mount_location for i in allEndpointsData]
                if requestedName in existingEndpointName:
                    return Response({'message': 'Endpoint with similar name and mount location already exists for this asset, kindly input some unique name'}, status=status.HTTP_409_CONFLICT)
                else:
                    existingMountData.point_name = name
                    existingMountData.mount_location = location
                    existingMountData.save()
                return Response({'message': 'Endpoint updated successfully.'},status=status.HTTP_200_OK)
        except:
            return Response({'message': 'Something went wrong, kindly contact admin.'}, status=status.HTTP_404_NOT_FOUND)



class SaveGatewayDevices(APIView):

    def post(self, request, *args, **kwargs):
        df = JSONParser().parse(request)
        if not df:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
        gatewayMacId = df.get("gateway_mac_id")
        deviceList = df.get("device_list")
        locationId = df.get("location_id")
        accountId = df.get("account_id")
        thingName = 'g_' + str(gatewayMacId)
        shadowUpdateData = {
                    "shadowData": {
                        "state": {
                            "desired": {
                                "deviceList": deviceList
                            }
                        }
                    },
                    "thingName": thingName
                    }
        # pdb.set_trace()
        try:
            existingGatewayData = models.GatewayMountMaster.objects.get(gateway_mac_id=gatewayMacId)

            try:
                existingsensors = models.GatewayMountMaster.objects.filter(device_list__overlap=deviceList)
                for row in existingsensors:
                    row.device_list = [item for item in row.device_list if item not in deviceList]
                models.GatewayMountMaster.objects.bulk_update(existingsensors, ['device_list'])
            except:
                return Response({'message': 'Something went wrong while mapping sensors, kindly contact admin.'}, status=status.HTTP_400_BAD_REQUEST)
            
            existingGatewayData.device_list = deviceList
            existingGatewayData.location_id = locationId
            existingGatewayData.org_id = accountId
            existingGatewayData.save()
            res = updateDeviceShadow(shadowUpdateData)
            return Response({'message': "Gateway device list updated successfully."}, status=status.HTTP_200_OK)
        except:
            try:
                try:
                    existingsensors = models.GatewayMountMaster.objects.filter(device_list__overlap=deviceList)
                    for row in existingsensors:
                        row.device_list = [item for item in row.device_list if item not in deviceList]
                    models.GatewayMountMaster.objects.bulk_update(existingsensors, ['device_list'])
                except:
                    return Response({'message': 'Something went wrong while mapping sensors, kindly contact admin.'}, status=status.HTTP_400_BAD_REQUEST)
            
                gatewayData = {"gateway_mac_id": gatewayMacId, "device_list": deviceList, "location_id": locationId, "org_id": accountId}
                gatewaySerializerData = serializers.GatewayMountMasterSerializer(data=gatewayData)
                if gatewaySerializerData.is_valid():
                    gatewaySerializerData.save()
                    res = updateDeviceShadow(shadowUpdateData)
                    return Response({'message': "Devices mapped to gateway successfully."}, status=status.HTTP_201_CREATED)
                return Response({'message': 'Something went wrong with the gateway serializer, kindly try after sometime.'}, status=status.HTTP_400_BAD_REQUEST)
            except:
                return Response({'message': 'Something went wrong, kindly try after sometime.'}, status=status.HTTP_400_BAD_REQUEST)





class SaveAssetRunningVibrationValue(APIView):

    def post(self, request, *args, **kwargs):
        df = JSONParser().parse(request)
        if not df:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
        try:
            dataSerializer = serializers.AssetRunningVibrationValueSerializer(data=df)
            if dataSerializer.is_valid():
                dataSerializer.save()
                return Response({'message': "Data saved successfully."}, status=status.HTTP_201_CREATED)
            return Response({'message': 'Something went wrong, kindly try after sometime.'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            print("some exception in SaveAssetRunningVibrationValue function", e)
            return Response({"Something went wrong, kindly try after sometime."}, status=status.HTTP_400_BAD_REQUEST)





