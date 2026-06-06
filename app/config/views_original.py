# from turtle import pd
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
import boto3
from datetime import datetime
from pytz import timezone
import pytz

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

def createThing(device, org):
    thingName = "RB_" + device
    response = iotClient.create_thing(
        thingName=thingName,
        )
    iotData = {
            'device':device,
            'thingName':response.get("thingName"),
            'thingArn':response.get("thingArn"),
            'thingId':response.get("thingId"),
            'cmms_org':org
                }
    return iotData


def updateDeviceShadow(data):
    shadowPayload = data.get("shadowData")
    thing_name = data.get("thingName")
    response = shadowClient.update_thing_shadow(thingName = thing_name, payload = json.dumps(shadowPayload))
    print(json.load(response.get("payload")))
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

#************************************Company Fucntions***********************************

@api_view(['GET', 'POST'])
def company_list(request):

    if request.method == 'GET':
        companies = models.CompanyMaster.objects.all().order_by('-id')
        serializer = serializers.CompanyMasterSerializer(companies, many=True)
        return Response(serializer.data)

    elif request.method == 'POST':
        data = JSONParser().parse(request)

        # if data.get('comp_id_cmms'):
        #     try:
        #         comp_id_cmms = data.get('comp_id_cmms')
        #         compDetails = models.CompanyMaster.objects.get(comp_id_cmms=comp_id_cmms)
        #         compSerializer = serializers.CompanyMasterSerializer(compDetails)
        #         return Response(compSerializer.data,status=status.HTTP_200_OK)
        #     except:
        #         return Response({'message':"Something went wrong while fetching company data."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = serializers.CompanyMasterSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response({'message':"data saved"}, status=status.HTTP_201_CREATED)

        return Response({'message':get_error_msg(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)




@api_view(['GET', 'PUT', 'DELETE'])
def company_detail(request, pk):

    try:
        company = models.CompanyMaster.objects.get(pk=pk)
    except models.CompanyMaster.DoesNotExist:
        return Response({'message':'Company not found'},status=status.HTTP_404_NOT_FOUND)


    if request.method == 'GET':
        serializer = serializers.CompanyMasterSerializer(company)
        return Response(serializer.data)

    elif request.method == 'PUT':
        data = JSONParser().parse(request)
        serializer = serializers.CompanyMasterSerializer(company, data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response({'message':get_error_msg(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        company.delete()
        return Response({'message':'Company Deleted'},status=status.HTTP_200_OK)


#************************************Location Fucntions***********************************

@api_view(['GET', 'POST'])
def location_list(request):
    if request.method == 'GET':
        locations = models.LocationMaster.objects.all()
        serializer = serializers.LocationMasterSerializer(locations, many=True)
        return Response(serializer.data)

    elif request.method == 'POST':
        data = JSONParser().parse(request)
        serializer = serializers.LocationMasterSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response({'message':get_error_msg(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET', 'PUT', 'DELETE'])
def location_detail(request, pk):

    try:
        location = models.LocationMaster.objects.get(pk=pk)
    except models.LocationMaster.DoesNotExist:
        return Response({'Message':'Location not found'},status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        serializer = serializers.LocationMasterSerializer(location)
        return Response(serializer.data)

    elif request.method == 'PUT':
        data = JSONParser().parse(request)
        serializer = serializers.LocationMasterSerializer(location, data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response({'message':get_error_msg(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        location.delete()
        return Response({'Message':'Location Deleted'},status=status.HTTP_204_NO_CONTENT)


#************************************Area Fucntions***********************************

@api_view(['GET', 'POST'])
def area_list(request):
    if request.method == 'GET':
        areas = models.AreaMaster.objects.all()
        serializer = serializers.AreaMasterSerializer(areas, many=True)
        return Response(serializer.data)

    elif request.method == 'POST':
        data = JSONParser().parse(request)
        serializer = serializers.AreaMasterSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response({'message':get_error_msg(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET', 'PUT', 'DELETE'])
def area_detail(request, pk):

    try:
        area = models.AreaMaster.objects.get(pk=pk)
    except models.AreaMaster.DoesNotExist:
        return Response({'Message':'Area not found'},status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        serializer = serializers.AreaMasterSerializer(area)
        return Response(serializer.data)

    elif request.method == 'PUT':
        data = JSONParser().parse(request)
        serializer = serializers.AreaMasterSerializer(area, data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response({'message':get_error_msg(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        area.delete()
        return Response({'Message':'Area Deleted'},status=status.HTTP_204_NO_CONTENT)


#************************************Equipment Fucntions***********************************

@api_view(['GET', 'POST'])
def equipment_list(request):
    if request.method == 'GET':
        equipments = models.EquipmentMaster.objects.all()
        serializer = serializers.EquipmentMasterSerializer(equipments, many=True)
        return Response(serializer.data)

    elif request.method == 'POST':
        data = JSONParser().parse(request)
        serializer = serializers.EquipmentMasterSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response({'message':get_error_msg(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET', 'PUT', 'DELETE'])
def equipment_detail(request, pk):

    try:
        equipment = models.EquipmentMaster.objects.get(pk=pk)
    except models.EquipmentMaster.DoesNotExist:
        return Response({'Message':'Equipment not found'},status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        serializer = serializers.EquipmentMasterSerializer(equipment)
        return Response(serializer.data)

    elif request.method == 'PUT':
        data = JSONParser().parse(request)
        serializer = serializers.EquipmentMasterSerializer(equipment, data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response({'message':get_error_msg(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        equipment.delete()
        return Response({'Message':'Equipment Deleted'},status=status.HTTP_204_NO_CONTENT)


#************************************Asset Fucntions***********************************

@api_view(['GET', 'POST'])
def asset_list(request):
    if request.method == 'GET':
        assets = models.AssetMaster.objects.all()
        serializer = serializers.AssetMasterSerializer(assets, many=True)
        return Response(serializer.data)

    elif request.method == 'POST':
        data = JSONParser().parse(request)
        serializer = serializers.AssetMasterSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response({'message':get_error_msg(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)

class AssetImage(APIView):
    parser_classes = (MultiPartParser, FormParser)
    def post(self, request, *args, **kwargs):
        try:
            asset_data = models.AssetImage.objects.get(asset=request.data.get('asset'))
            asset_data.file = request.data.get('file')
            asset_data.save()
            return Response({'message':'file updated'}, status=status.HTTP_200_OK)
        except models.AssetImage.DoesNotExist:
            file_serializer = serializers.AssetImageSerializer(data=request.data)
            if file_serializer.is_valid():
                file_serializer.save()
                return Response(file_serializer.data, status=status.HTTP_201_CREATED)
            else:
                return Response(file_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET', 'PUT', 'DELETE'])
def asset_detail(request, pk):

    try:
        asset = models.AssetMaster.objects.get(pk=pk)
    except models.AssetMaster.DoesNotExist:
        return Response({'Message':'Asset not found'},status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        serializer = serializers.AssetMasterSerializer(asset)
        return Response(serializer.data)

    elif request.method == 'PUT':
        data = JSONParser().parse(request)
        serializer = serializers.AssetMasterSerializer(asset, data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response({'message':get_error_msg(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        asset.delete()
        return Response({'Message':'Asset Deleted'},status=status.HTTP_204_NO_CONTENT)


#************************************Device Fucntions***********************************
"""changing org_id and asset_id for new integrated config app (cmms)"""
@api_view(['POST'])
def device_list(request):
    if request.method == 'POST':
        # pdb.set_trace()
        data = JSONParser().parse(request)
        if not data:
            return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
        asset_id = data.get('asset_id')
        comp_id = data.get('comp_id')
        device_data = models.DeviceModelMaster.objects.filter(cmms_org=comp_id)
        if not device_data:
            return Response({'message':'Device data not found'},status=status.HTTP_404_NOT_FOUND)
        unlinked_devices = []
        linked_devices = []
        if not asset_id:
            for singleDevice in device_data:
                if singleDevice.asset_id:
                    try:
                        mount_data = models.DeviceMountMaster.objects.get(device=singleDevice.device_key)
                    except models.DeviceMountMaster.DoesNotExist:
                        continue
                    data_serializer = serializers.DeviceMountMasterSerializer(mount_data)
                    linked_data = data_serializer.data
                    jsondata = json.loads(json.dumps(linked_data))
                    linked_devices.append({'device_key':singleDevice.device_key,\
                        'device_value':singleDevice.device_value,\
                            'mount_location':jsondata['mount_location'],\
                                'mount_type':jsondata['mount_type'],\
                                    'mount_material':jsondata['mount_material'],\
                                        'mount_direction':jsondata['mount_direction'],\
                                            'asset_id':singleDevice.asset_id,\
                                                'org_id':singleDevice.cmms_org.id})

                else:
                    unlinked_devices.append({'device_key':singleDevice.device_key,\
                        'device_value':singleDevice.device_value}) 
            return Response({'unlinked_devices':unlinked_devices,'linked_devices':linked_devices})
        else:
            for singleDevice in device_data:
                if singleDevice.asset_id:
                    if singleDevice.asset_id == asset_id:
                        try:
                            mount_data = models.DeviceMountMaster.objects.get(device=singleDevice.device_key)
                        except models.DeviceMountMaster.DoesNotExist:
                            continue
                        data_serializer = serializers.DeviceMountMasterSerializer(mount_data)
                        linked_data = data_serializer.data
                        jsondata = json.loads(json.dumps(linked_data))
                        linked_devices.append({'device_key':singleDevice.device_key,\
                            'device_value':singleDevice.device_value,\
                                'mount_location':jsondata['mount_location'],\
                                    'mount_type':jsondata['mount_type'],\
                                        'mount_material':jsondata['mount_material'],\
                                            'mount_direction':jsondata['mount_direction'],\
                                                'asset_id':singleDevice.asset_id,\
                                                    'org_id':singleDevice.cmms_org.id})

                else:
                    unlinked_devices.append({'device_key':singleDevice.device_key,\
                        'device_value':singleDevice.device_value}) 
            return Response({'unlinked_devices':unlinked_devices,'linked_devices':linked_devices})


@api_view(['POST','PUT','DELETE'])
def devices_update(request):
    # pdb.set_trace()
    data = JSONParser().parse(request)
    print("DDDDDDDDDDDDDDD", data)
    if not data:
        return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
    try:
        device_data = models.DeviceModelMaster.objects.get(device_value=data.get('device_value'))
        data.update({'device':device_data.device_key})
    except models.DeviceModelMaster.DoesNotExist:
        return Response({'message':"Device Data not found"},status=status.HTTP_404_NOT_FOUND)
    if request.method == 'POST':
        # try:
        device_data.asset_id = data.get('asset_id')
        try:
            device_mount = models.DeviceMountMaster.objects.get(device=device_data.device_key)
            serializer = serializers.DeviceMountMasterSerializer(device_mount, data=data)
        except models.DeviceMountMaster.DoesNotExist:
            serializer = serializers.DeviceMountMasterSerializer(data=data)
        if serializer.is_valid():
            iotData = createThing(data.get("device_value"), data.get("org_id"))
            thingSerializer = serializers.AwsIotThingMasterSerializer(data = iotData)
            if thingSerializer.is_valid():
                serializer.save()
                device_data.save()
                thingSerializer.save()

                return Response({'message':'Device Added'},status=status.HTTP_200_OK)
            return Response({'message':get_error_msg(thingSerializer.errors)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'message':get_error_msg(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)

        # except:
        #     return Response({'message':'Something went wrong'}, status=status.HTTP_400_BAD_REQUEST)
    elif request.method == 'PUT':
        device_data.asset_id = data.get('asset_id')
        try:
            device_mount = models.DeviceMountMaster.objects.get(device=device_data.device_key)
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
            device_mount = models.DeviceMountMaster.objects.get(device=device_data.device_key)
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
        print("data for device reg is", data)
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
            deviceData = models.DeviceModelMaster.objects.get(device_key=data.get("device"))
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


#************************************Role Fucntions***********************************

@api_view(['GET', 'POST'])
def role_list(request):
    if request.method == 'GET':
        roles = models.RoleMaster.objects.all()
        serializer = serializers.RoleMasterSerializer(roles, many=True)
        return Response(serializer.data)

    elif request.method == 'POST':
        data = JSONParser().parse(request)
        serializer = serializers.RoleMasterSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response({'message':get_error_msg(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET', 'PUT', 'DELETE'])
def role_detail(request, pk):

    try:
        role = models.RoleMaster.objects.get(pk=pk)
    except models.RoleMaster.DoesNotExist:
        return Response({'message':'Role not found'},status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        serializer = serializers.RoleMasterSerializer(role)
        return Response(serializer.data)

    elif request.method == 'PUT':
        data = JSONParser().parse(request)
        serializer = serializers.RoleMasterSerializer(role, data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response({'message':get_error_msg(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        role.delete()
        return Response({'message':'Role Deleted'},status=status.HTTP_204_NO_CONTENT)


#************************************ISO Flags Master Fucntions***********************************

@api_view(['GET', 'POST'])
def iso_flags_list(request):
    if request.method == 'GET':
        velocity = models.ISOFlagsMaster.objects.all()
        serializer = serializers.ISOFlagsMasterSerializer(velocity, many=True)
        return Response(serializer.data)

    elif request.method == 'POST':
        data = JSONParser().parse(request)
        serializer = serializers.ISOFlagsMasterSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response({'message':get_error_msg(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)

#************************************Time Wave Fucntions***********************************

@api_view(['GET', 'POST'])
def timewave_list(request):
    if request.method == 'GET':
        asset_health_score = models.TimeWaveMaster.objects.all()
        serializer = serializers.TimeWaveMasterSerializer(asset_health_score, many=True)
        return Response(serializer.data)

    elif request.method == 'POST':
        data = JSONParser().parse(request)
        if not data:
            return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
        try:
            time_data = models.TimeWaveMaster.objects.get(device=data.get('device'))
            serializer = serializers.TimeWaveMasterSerializer(time_data, data=data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response({'message':get_error_msg(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)
        except models.TimeWaveMaster.DoesNotExist:
            serializer = serializers.TimeWaveMasterSerializer(data=data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response({'message':get_error_msg(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)

#************************************Frequency Wave Fucntions***********************************

@api_view(['GET', 'POST'])
def frequencywave_list(request):
    if request.method == 'GET':
        asset_health_score = models.FrequencyWaveMaster.objects.all()
        serializer = serializers.FrequencyWaveMasterSerializer(asset_health_score, many=True)
        return Response(serializer.data)

    elif request.method == 'POST':
        data = JSONParser().parse(request)
        if not data:
            return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
        try:
            freq_data = models.FrequencyWaveMaster.objects.get(device=data.get('device'))
            serializer = serializers.FrequencyWaveMasterSerializer(freq_data, data=data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response({'message':get_error_msg(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)
        except models.FrequencyWaveMaster.DoesNotExist:
            serializer = serializers.FrequencyWaveMasterSerializer(data=data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response({'message':get_error_msg(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)

#************************************Device Configuration Fucntions***********************************

@api_view(['POST'])
def device_config(request):
    if request.method == 'POST':
        # try:
            # pdb.set_trace()
            data = JSONParser().parse(request)
            if not data:
                return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)

            hardware_data = data.get('hardware')
            firmware_data = data.get('firmware')
            signal_processing_data = data.get('signal_processing')
            fault_data = data.get('faults')
            bearing_data = fault_data.get('bearing')
            gear_data = fault_data.get('gear')
            ac_motor_data = fault_data.get('ac_motor')
            pump_fan_data = fault_data.get('pump_fan')
            threshold_data = data.get('threshold')

            # thres_final_data = {'velocity_rms':threshold_data.get('velocity').get('rms'),'velocity_peak':threshold_data.get('velocity').get('peak'),\
            #     'velocity_peak_to_peak':threshold_data.get('velocity').get('peak_to_peak'),'velocity_kurtosis':threshold_data.get('velocity').get('kurtosis'),\
            #         'acceleration_rms':threshold_data.get('acceleration').get('rms'),'acceleration_peak':threshold_data.get('acceleration').get('peak'),\
            #     'acceleration_peak_to_peak':threshold_data.get('acceleration').get('peak_to_peak'),'acceleration_kurtosis':threshold_data.get('acceleration').get('kurtosis'),\
            #         'displacement_rms':threshold_data.get('displacement').get('rms'),'displacement_peak':threshold_data.get('displacement').get('peak'),\
            #     'displacement_peak_to_peak':threshold_data.get('displacement').get('peak_to_peak'),'displacement_kurtosis':threshold_data.get('displacement').get('kurtosis')}
            try:
                deviceData = models.DeviceModelMaster.objects.get(device_key=data.get('device_key'))
                print("deviceeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee", deviceData.cmms_org.comp_id_cmms)
            except:
                return Response({'message':"Device does not found."},status=status.HTTP_404_NOT_FOUND)

            hardware_data.update({'device':data.get('device_key'),'cmms_org':deviceData.cmms_org.comp_id_cmms})
            firmware_data.update({'device':data.get('device_key'),'cmms_org':deviceData.cmms_org.comp_id_cmms})
            signal_processing_data.update({'device':data.get('device_key'),'cmms_org':deviceData.cmms_org.comp_id_cmms})
            bearing_data.update({'device':data.get('device_key'),'cmms_org':deviceData.cmms_org.comp_id_cmms})
            gear_data.update({'device':data.get('device_key'),'cmms_org':deviceData.cmms_org.comp_id_cmms})
            ac_motor_data.update({'device':data.get('device_key'),'cmms_org':deviceData.cmms_org.comp_id_cmms})
            pump_fan_data.update({'device':data.get('device_key'),'cmms_org':deviceData.cmms_org.comp_id_cmms})
            # thres_final_data.update({'device':data.get('device_key'),'org_id':deviceData.cmms_org})

            try:
                # pdb.set_trace()
                thingData = models.AwsIotThingMaster.objects.get(device_id=data.get('device_key'))
            except:
                pass

            shadowUpdateData = {
                "shadowData": {
                    "state": {
                        "desired": {
                        }
                    }
                },
                "thingName": thingData.thingName
                }
            if firmware_data.get("upload_time"):
                print("data upload time issssssssssssss", firmware_data.get("upload_time"))
                hr = int(firmware_data.get("upload_time").split(":")[0])
                min = int(firmware_data.get("upload_time").split(":")[1])
                localDT = datetime.now().replace(hour=hr, minute=min)
                print("local date", localDT)
                utC_date = utc_tz.normalize(localDT.astimezone(local_tz))
                print("utc date", utC_date)
                gmtHR = utC_date.time().hour
                gmtMin = utC_date.time().minute
                updateTime = str(gmtHR) + ':' +str(gmtMin)
                next_upload_utC_date = utC_date.replace(hour=utC_date.time().hour+4)  #sleep time for 4 hours static
                gmtNHR = next_upload_utC_date.time().hour
                gmtNMin = next_upload_utC_date.time().minute
                next_upload = str(gmtNHR) + ':' +str(gmtNMin)
                print("data upload time gmttttttttttttt", updateTime)
                shadowUpdateData.get('shadowData').get('state').get('desired').update({'fftDataAcquisitionStartTime': updateTime})
                shadowUpdateData.get('shadowData').get('state').get('desired').update({'next_upload': next_upload})
            else:
                pass
                # shadowUpdateData.get('shadowData').get('state').get('desired').update({'fftDataAcquisitionStartTime': "14:30"})
            if signal_processing_data.get("sensitivity"):
                shadowUpdateData.get('shadowData').get('state').get('desired').update({'sensitivity': signal_processing_data.get("sensitivity")})
            else:
                pass
                # shadowUpdateData.get('shadowData').get('state').get('desired').update({'sensitivity': 8})
            if signal_processing_data.get("vib_sampling_rate"):
                shadowUpdateData.get('shadowData').get('state').get('desired').update({'samplingFrequency': signal_processing_data.get("vib_sampling_rate")})
            else:
                pass
                # shadowUpdateData.get('shadowData').get('state').get('desired').update({'samplingFrequency': 12480})
            if signal_processing_data.get("vib_no_of_samples"):
                shadowUpdateData.get('shadowData').get('state').get('desired').update({'fftBlockSize': signal_processing_data.get("vib_no_of_samples")})
            else:
                pass
                # shadowUpdateData.get('shadowData').get('state').get('desired').update({'fftBlockSize': 16384})
            if firmware_data.get("sleep_time"):
                shadowUpdateData.get('shadowData').get('state').get('desired').update({'sleepTime': firmware_data.get("sleep_time")})
            else:
                pass
                # shadowUpdateData.get('shadowData').get('state').get('desired').update({'sleepTime': float(240)})
            

            # pdb.set_trace()
            if (signal_processing_data.get('vib_no_of_samples') and signal_processing_data.get('vib_sampling_rate')):

                timewave_data = {'device':data.get('device_key'),'cmms_org':deviceData.cmms_org.comp_id_cmms,\
                    'data':np.linspace(0, (int(float(signal_processing_data.get('vib_no_of_samples'))))\
                    /int(float(signal_processing_data.get('vib_sampling_rate'))),int(float(signal_processing_data.get('vib_no_of_samples'))))}

                freqwave_data = {'device':data.get('device_key'),'cmms_org':deviceData.cmms_org.comp_id_cmms,\
                    'data':(int(float(signal_processing_data.get('vib_sampling_rate')))/2)\
                        *np.linspace(0,1,int(int(float(signal_processing_data.get('vib_no_of_samples')))/2))}
            
            else:

                timewave_data = {'device':data.get('device_key'),'cmms_org':deviceData.cmms_org.comp_id_cmms,\
                    'data':None}

                freqwave_data = {'device':data.get('device_key'),'cmms_org':deviceData.cmms_org.comp_id_cmms,\
                    'data':None}

            try:
                print("final hard ware data", hardware_data)
                hardwareData = models.HardwareMaster.objects.get(device=data.get('device_key'))
                hardwareSerializer = serializers.HardwareMasterSerializer(hardwareData, data=hardware_data)
            except:
                hardwareSerializer = serializers.HardwareMasterSerializer(data=hardware_data)

            try:
                # pdb.set_trace()
                firmwareData = models.FirmwareMaster.objects.get(device=data.get('device_key'))
                firmwareSerializer = serializers.FirmwareMasterSerializer(firmwareData, data=firmware_data)
            except:
                firmwareSerializer = serializers.FirmwareMasterSerializer(data=firmware_data)

            try:
                signalData = models.SignalProcessingMaster.objects.get(device=data.get('device_key'))
                signalSerializer = serializers.SignalProcessingMasterSerializer(signalData, data=signal_processing_data)
            except:
                signalSerializer = serializers.SignalProcessingMasterSerializer(data=signal_processing_data)

            try:
                bearingData = models.BearingFaultsMaster.objects.get(device=data.get('device_key'))
                bearingSerializer = serializers.BearingFaultsMasterSerializer(bearingData, data=bearing_data)
            except:
                bearingSerializer = serializers.BearingFaultsMasterSerializer(data=bearing_data)

            try:
                gearData = models.GearFaultsMaster.objects.get(device=data.get('device_key'))
                gearSerializer = serializers.GearFaultsMasterSerializer(gearData, data=gear_data)
            except:
                gearSerializer = serializers.GearFaultsMasterSerializer(data=gear_data)

            try:
                acMotorData = models.ACMotorFaultsMaster.objects.get(device=data.get('device_key'))
                acMotorSerializer = serializers.ACMotorFaultsMasterSerializer(acMotorData, data=ac_motor_data)
            except:
                acMotorSerializer = serializers.ACMotorFaultsMasterSerializer(data=ac_motor_data)

            try:
                pumpFanData = models.PumpFanFaultsMaster.objects.get(device=data.get('device_key'))
                pumpFanSerializer = serializers.PumpFanFaultsMasterSerializer(pumpFanData, data=pump_fan_data)
            except:
                pumpFanSerializer = serializers.PumpFanFaultsMasterSerializer(data=pump_fan_data)

            try:
                time_data = models.TimeWaveMaster.objects.get(device=data.get('device_key'))
                timewaveSerializer = serializers.TimeWaveMasterSerializer(time_data, data=timewave_data)
            except models.TimeWaveMaster.DoesNotExist:
                timewaveSerializer = serializers.TimeWaveMasterSerializer(data=timewave_data)

            try:
                freq_data = models.FrequencyWaveMaster.objects.get(device=data.get('device_key'))
                freqSerializer = serializers.FrequencyWaveMasterSerializer(freq_data, data=freqwave_data)
            except models.FrequencyWaveMaster.DoesNotExist:
                freqSerializer = serializers.FrequencyWaveMasterSerializer(data=freqwave_data)

            # try:
            #     thres_data = models.ThresholdValues.objects.get(device=data.get('device_key'))
            #     thresSerializer = serializers.ThresholdValuesSerializer(thres_data, data=thres_final_data)
            # except models.ThresholdValues.DoesNotExist:
            #     thresSerializer = serializers.ThresholdValuesSerializer(data=thres_final_data)
            if hardwareSerializer.is_valid():
                if firmwareSerializer.is_valid():
                    if signalSerializer.is_valid():
                        if bearingSerializer.is_valid():
                            if gearSerializer.is_valid():
                                if acMotorSerializer.is_valid():
                                    if pumpFanSerializer.is_valid():
                                        if timewaveSerializer.is_valid():
                                            if freqSerializer.is_valid():
                                                # if thresSerializer.is_valid():
                                                    hardwareSerializer.save()
                                                    firmwareSerializer.save()
                                                    signalSerializer.save()
                                                    bearingSerializer.save()
                                                    gearSerializer.save()
                                                    acMotorSerializer.save()
                                                    pumpFanSerializer.save()
                                                    timewaveSerializer.save()
                                                    freqSerializer.save()
                                                    # thresSerializer.save()
                                                    print("saving shadow data", shadowUpdateData)
                                                    updateDeviceShadow(shadowUpdateData)
                                                    return Response({'message':"Device Configuration Completed!"}, status=status.HTTP_201_CREATED)
                                                # return Response(get_error_msg(thresSerializer.errors), status=status.HTTP_400_BAD_REQUEST)
                                            return Response(get_error_msg(freqSerializer.errors), status=status.HTTP_400_BAD_REQUEST)
                                        return Response(get_error_msg(timewaveSerializer.errors), status=status.HTTP_400_BAD_REQUEST)
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
        print("data from config api", data)
        if not data:
            return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)

        try:
            deviceData = models.DeviceModelMaster.objects.get(device_key=data.get('device_key'))
        except:
            return Response({'message':"Device not found."},status=status.HTTP_404_NOT_FOUND)


        finalData = {"device_key":data.get('device_key')}

        try:
            hardwareData = models.HardwareMaster.objects.get(device=data.get('device_key'))
            hardwareSerializer = serializers.HardwareMasterSerializer(hardwareData)
            jsondata = json.loads(json.dumps(hardwareSerializer.data))
            print("json data of serializer", jsondata)
            del jsondata['device']
            del jsondata['cmms_org']
            finalData.update({'hardware':jsondata})
            print("final data after del", finalData)
        except:
            jsondata = {"hardware_type":"","hardware_components":[]}
            finalData.update({'hardware':jsondata})
        try:
            firmwareData = models.FirmwareMaster.objects.get(device=data.get('device_key'))
            firmwareSerializer = serializers.FirmwareMasterSerializer(firmwareData)
            jsondata = json.loads(json.dumps(firmwareSerializer.data))
            del jsondata['device']
            del jsondata['cmms_org']
            finalData.update({'firmware':jsondata})
        except:
            jsondata = {"firmware_version":None,"no_of_samples":None,"no_of_files":None,"upload_time":None,\
                "machine_running":""}
            finalData.update({'firmware':jsondata})
        try:
            signalData = models.SignalProcessingMaster.objects.get(device=data.get('device_key'))
            signalSerializer = serializers.SignalProcessingMasterSerializer(signalData)
            jsondata = json.loads(json.dumps(signalSerializer.data))
            del jsondata['device']
            del jsondata['cmms_org']
            finalData.update({'signal_processing':jsondata})
        except:
            jsondata = {"vibration_rms":None,"overall_rms":None,"vibration_twf":"",\
                "vib_fcutoff":"","vib_sampling_rate":None,"vib_fmax":None,\
                    "vib_no_of_samples":None,"vib_freq_resolution":None,"freq_spec_waterfall":None,\
                        "acc_fcutoff":"","acc_sampling_rate":None,"acc_fmax":None,\
                            "acc_no_of_samples":None,"acc_freq_resolution":None,"acc_rms":None,\
                                "temperature":None,"battery_cut_off":None,"battery_unstable_current":None,\
                                    "battery_unstable_samples":None,"battery_max_cycle":None,\
                                        "rul_power_coeff":"","rul_bound_limit":"",\
                                            "rul_ffa_rpm":None,"rul_ffa_ffr":None,"rul_ffa_max_har_count":None,\
                                                "rul_ffa_min_accp_rpm":None,"rul_ffa_max_accp_rpm":None,\
                                                    "rul_learning_cond":None}
            finalData.update({'signal_processing':jsondata})

        faultsData = {}
        try:
            bearingData = models.BearingFaultsMaster.objects.get(device=data.get('device_key'))
            bearingSerializer = serializers.BearingFaultsMasterSerializer(bearingData)
            jsondata = json.loads(json.dumps(bearingSerializer.data))
            del jsondata['device']
            del jsondata['cmms_org']
            faultsData.update({'bearing':jsondata})
        except:
            jsondata = {"fault":False,"misalignment_unbalance":False,"looseness":False,"speed":"constant",\
                "bpfo":None,"bpfi":None,"bsf":None,"ftf":None,"fault_amp_thres":None,"bpfo_coeff":None,\
                    "bpfi_coeff":None,"bsf_coeff":None,"misalig_amp_thres":None,"unbalance_amp_thres":None,\
                        "looseness_amp_thres":None}
            faultsData.update({'bearing':jsondata})
        try:
            gearData = models.GearFaultsMaster.objects.get(device=data.get('device_key'))
            gearSerializer = serializers.GearFaultsMasterSerializer(gearData)
            jsondata = json.loads(json.dumps(gearSerializer.data))
            del jsondata['device']
            del jsondata['cmms_org']
            faultsData.update({'gear':jsondata})
        except:
            jsondata = {"fault":False,"misalignment_unbalance":False,"looseness":False,"constant_speed":False,\
                "no_of_gear_teeth":None,"gear_ratio":None,"gmp":None,"misalig_amp_thres":None,\
                    "unbalance_amp_thres":None,"looseness_amp_thres":None}
            faultsData.update({'gear':jsondata})
        try:
            acMotorData = models.ACMotorFaultsMaster.objects.get(device=data.get('device_key'))
            acMotorSerializer = serializers.ACMotorFaultsMasterSerializer(acMotorData)
            jsondata = json.loads(json.dumps(acMotorSerializer.data))
            del jsondata['device']
            del jsondata['cmms_org']
            faultsData.update({'ac_motor':jsondata})
        except:
            jsondata = {"fault":False,"misalignment_unbalance":False,"looseness":False,"line_freq":None,\
                "rotor_amp_thres":None,"stator_amp_thres":None,"misalig_amp_thres":None,"unbalance_amp_thres":None,\
                    "looseness_amp_thres":None}
            faultsData.update({'ac_motor':jsondata})
        try:
            pumpFanData = models.PumpFanFaultsMaster.objects.get(device=data.get('device_key'))
            pumpFanSerializer = serializers.PumpFanFaultsMasterSerializer(pumpFanData)
            jsondata = json.loads(json.dumps(pumpFanSerializer.data))
            del jsondata['device']
            del jsondata['cmms_org']
            faultsData.update({'pump_fan':jsondata})
        except:
            jsondata = {"fault":False,"misalignment_unbalance":False,"looseness":False,"vanes_no_lower":None,\
                "vanes_no_upper":None,"vpf_amp_thres":None,"vane_fault_amp_thres":None,"misalig_amp_thres":None,\
                    "unbalance_amp_thres":None,"looseness_amp_thres":None}
            faultsData.update({'pump_fan':jsondata})
        finalData.update({'faults':faultsData})
        # try:
        #     thresholdData = models.ThresholdValues.objects.get(device=data.get('device_key'))
        #     thresholdSerializer = serializers.ThresholdValuesSerializer(thresholdData)
        #     jsondata = json.loads(json.dumps(thresholdSerializer.data))
        #     del jsondata['device']
        #     del jsondata['org_id']
        #     finaljsondata = {"velocity":{"rms":jsondata['velocity_rms'],"peak":jsondata['velocity_peak'],"peak_to_peak":jsondata['velocity_peak_to_peak'],\
        #         "kurtosis":jsondata['velocity_kurtosis']},
        #     "displacement":{"rms":jsondata['displacement_rms'],"peak":jsondata['displacement_peak'],"peak_to_peak":jsondata['displacement_peak_to_peak'],\
        #         "kurtosis":jsondata['displacement_kurtosis']},
        #     "acceleration":{"rms":jsondata['acceleration_rms'],"peak":jsondata['acceleration_peak'],"peak_to_peak":jsondata['acceleration_peak_to_peak'],\
        #         "kurtosis":jsondata['acceleration_kurtosis']}}
        #     finalData.update({'threshold':finaljsondata})
        # except:
        #     jsondata = {"velocity":{"rms":None,"peak":None,"peak_to_peak":None,"kurtosis":None},
        #     "displacement":{"rms":None,"peak":None,"peak_to_peak":None,"kurtosis":None},
        #     "acceleration":{"rms":None,"peak":None,"peak_to_peak":None,"kurtosis":None}}
        #     finalData.update({'threshold':jsondata})
        return Response({'config':finalData}, status=status.HTTP_201_CREATED)

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
        return Response({'Message':'Something went Wrong'},status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
def add_sensor(request):
    if request.method == 'POST':
        data = JSONParser().parse(request)
        sensorData = {"device_key": data.get('device_key'), "device_value": data.get("device_value"), "asset_id": data.get("asset_id"), "cmms_org": data.get("org_id")}
        mountData = {'device': data.get("device_key"), 'mount_location': data.get("mount_location"), 'mount_type': data.get("mount_type"),'mount_material': data.get("mount_material"),'mount_direction': data.get("mount_direction")}
        sensorSerializer = serializers.DeviceModelMasterSerializer(data=sensorData)
        mountSerializer = serializers.DeviceMountMasterSerializer(data=mountData)
        # pdb.set_trace()
        # if sensorSerializer.is_valid():
        #     if mountSerializer.is_valid():
        #         sensorSerializer.save()
        #         mountSerializer.save()
        #         iotData = createThing(data.get("device_key"), data.get("org_id"))
        #         thingSerializer = serializers.AwsIotThingMasterSerializer(data = iotData)
        #         if thingSerializer.is_valid():
        #             thingSerializer.save()
        #         return Response({'message':get_error_msg(thingSerializer.errors)}, status=status.HTTP_400_BAD_REQUEST)
        #     return Response({'message':get_error_msg(mountSerializer.errors)}, status=status.HTTP_400_BAD_REQUEST)
        # return Response({'message':get_error_msg(sensorSerializer.errors)}, status=status.HTTP_400_BAD_REQUEST)



        if sensorSerializer.is_valid():
            if mountSerializer.is_valid():
                sensorSerializer.save()
                mountSerializer.save()
                return Response(mountSerializer.data, status=status.HTTP_201_CREATED)
            return Response({'message':get_error_msg(mountSerializer.errors)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'message':get_error_msg(sensorSerializer.errors)}, status=status.HTTP_400_BAD_REQUEST)
