from functools import partial
from app import models
from app import serializers
import pdb
from django.db.models import DateTimeField, Q
from django.db.models.functions import Trunc
from django.conf import settings
from django.core.mail import send_mail
from datetime import datetime, date, timedelta
from twilio.rest import Client
from rest_framework.views import APIView
from rest_framework.parsers import JSONParser
from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import api_view
import requests
import json
import numpy as np
import pytz
ist_timezone = pytz.timezone('Asia/Kolkata')
utc_timezone = pytz.timezone('UTC')
import redis
from app.cache import load_mount_data_mapping, get_threshold_counter_data, get_mount_data, updateThreshCounterDB, load_sensor_orientation_mapping, get_sensor_orientation_data, load_threshold_data_mapping, get_threshold_data, load_threshold_counter_data_mapping
from app.task import sendMailSingle
from django.utils import timezone
from django.db import transaction


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


statfunctionList = ['rms', 'peak', 'peak_to_peak', 'kurtosis', 'temp']
signalTypeList = ['acceleration', 'velocity', 'displacement', 'temp']

# *********************************** Acceleration Stat Function ***********************************

harmonicsList = ['one_amp', 'two_amp', 'three_amp', 'four_amp']

def sendmessage(alarmHistoryData, apiData):

    asset_name = apiData.get("asset_name")
    location_name = apiData.get("location_name")
    top_asset_name = apiData.get("top_asset_name")

    if alarmHistoryData.get("signal_type") == 'temp':
        # fault_location =  alarmHistoryData.get("sensor_location")
        # date = alarmHistoryData.get("timestamp")
        signal_type = 'Temperature'
        trend_type = 'Temperature'
        # axis =  '-'
        # set_threshold =  alarmHistoryData.get("threshold_value")
        # observed_value = alarmHistoryData.get("observed_value")
    else:
        # fault_location = alarmHistoryData.get("sensor_location")
        # date = alarmHistoryData.get("timestamp")
        signal_type = alarmHistoryData.get("signal_type").capitalize()
        trend_type = ' '.join(alarmHistoryData.get(
            "trend_type").split('_')[:-1]).capitalize()
        # axis = alarmHistoryData.get("axis").capitalize()
        # set_threshold = alarmHistoryData.get("threshold_value")
        # observed_value = alarmHistoryData.get("observed_value")

    alarmLevel = alarmHistoryData.get("priority")

    account_sid = "AC77d2eaf2de3341ebf6152efc5dbd5e03"
    auth_token = "47f1c48221bb4c7beb18b787a1e4fe85"
    client = Client(account_sid, auth_token)
    users_list = apiData.get("users")

    for user in users_list:
        message = client.messages.create(
            from_='+16073604813',
            body="ALERT Level: {0},   Location Name: {1},     Equipment Name: {2},    Asset Name: {3},    Signal: {4},    Trend: {5}\
                    ".format(alarmLevel, location_name, top_asset_name, asset_name, signal_type, trend_type),
            to=user.get("contact_number")
        )
    return True


# *********************************** check threshold counter function to check 3 level notification counter ***********************************

def checkAllLevelCounter(row, func, level):

    if level == '1':
        priority = "Alert"
    elif level == '2':
        priority = "Danger"
    elif level == '3':
        priority = "Critical"

    existingAlarm = models.AlarmHistoryMaster.objects.annotate(truncated_date=Trunc('creation_date', 'day', output_field=DateTimeField())
                                                                       ).filter(truncated_date__date=date.today(), priority=priority, composite = row.get("composite"), fault_flag=False)
    if len(existingAlarm) == 0:    #checking if single mail is being sent on same day
        print("-------------no existing alarm found--------------------", row.get("composite"))
        if (row.get(func+'_counter_level_'+level) >= row.get(func+'_repetition_level_'+level)) and row.get(func+'_counter_level_'+level) > 0 and row.get(func+'_repetition_level_'+level) > 0:
            threshold_counter_data = get_threshold_counter_data(row.get("mount_id"), row.get("axis"), row.get("signal_type"), row.get("domain"))
            counter_param = func + '_counter_level_' + level
            threshold_counter_data[counter_param] = 0

            try:
                comp_key = str(row.get("mount_id")) + '-' + row.get("axis") + '-' + row.get("signal_type") + '-' + row.get("domain")
                result = updateThreshCounterDB(comp_key, threshold_counter_data)
            except Exception as e1:
                print("Exception in updateThreshCounterDB functions", e1)

            updateCount = {func+'_counter_level_'+level: 0}
            single_row = models.ThresholdCounterMaster.objects.get(
                id=row.get('id'))
            threshold_counter_serializer = serializers.ThresholdCounterMasterSerializer(
                instance=single_row, data=updateCount, partial=True)
            
            # print("condition true for", row)
            data_dict = row.get("values")
            if isinstance(data_dict, str):
                data_dict = data_dict.replace("'", '"')
                data_dict = data_dict.replace("None", "null")
                data_dict = json.loads(data_dict)
            try:
                macID = "_".join(row.get("composite").split("_")[:2])
                deviceMountData = get_mount_data(macID)
                device_composite = deviceMountData.get("composite_id")
                device_location = deviceMountData.get("point_name")+'-'+deviceMountData.get("mount_location")
                device_asset_id = deviceMountData.get("asset_id")
                # print("deviceMountData from cache", deviceMountData)
            except:
                try:
                    deviceMountData = models.DeviceMountMaster.objects.get(composite_id=row.get("composite"))
                    device_composite = deviceMountData.composite_id
                    device_location = deviceMountData.point_name+'-'+deviceMountData.mount_location
                    device_asset_id = deviceMountData.asset_id
                    # print("deviceMountData from query", deviceMountData)
                except:
                    return


            # "two_amp_repetition_level_2_timestamp"
            # pdb.set_trace()
            timestamp = row.get(func+'_repetition_level_'+level+'_timestamp', '-')
            value = data_dict.get(func+'_level_'+level, '-')
            threshold_data = get_threshold_data(row.get('mount_id'), row.get('axis'), row.get('signal_type'), row.get('domain'))
            threshValue = threshold_data.get(func+"_level_"+level)

            if row.get("signal_type") != 'temp':
                sensorAxis = row.get("axis")
            else:
                sensorAxis = '-'

            alarmHistoryData = {"composite": device_composite, "signal_type": row.get("signal_type"), "trend_type": func, "axis": sensorAxis, "priority": priority,
                                "sensor_location": device_location, "asset_id": device_asset_id,
                                "timestamp": timestamp, "threshold_value": threshValue, "observed_value": value}
            print("----alarm history data----", alarmHistoryData)
            alarmHistoryDataSerializer = serializers.AlarmHistoryMasterSerializer(data=alarmHistoryData)
            # try:
            #     if alarmHistoryDataSerializer.is_valid():
            #         alarmHistoryDataSerializer.save()
            #         if threshold_counter_serializer.is_valid():
            #             threshold_counter_serializer.save()
            #             print("started sending email")
            #             sendMailSingle.delay(alarmHistoryData)
            #         else:
            #             print("error in saving threshold counter", get_error_msg(threshold_counter_serializer.errors))
            #     else:
            #         print("error in saving alarmhistorydata", get_error_msg(alarmHistoryDataSerializer.errors))
            #         if threshold_counter_serializer.is_valid():
            #             threshold_counter_serializer.save()
            # except  Exception as e1:
            #     print("some error occured while saving alarm history master", e1)
            #     pass


    return True


# *********************************** check threshold counter ***********************************
functionList = ['rms_amp', 'peak_amp', 'peak_to_peak_amp', 'kurtosis_amp',
                'one_amp', 'two_amp', 'three_amp', 'four_amp', 'temp_amp']


# def checkThresholdCounter():
#     print("--------------im triggered------------")
#     threshCounter = models.ThresholdCounterMaster.objects.all().values()
#     for row in threshCounter:
#         for func in functionList:
#             if row.get(func+'_counter_level_3') != 0:
#                 checkAllLevelCounter(row, func, '3')
#             if row.get(func+'_counter_level_2') != 0:
#                 checkAllLevelCounter(row, func, '2')
#             if row.get(func+'_counter_level_1') != 0:
#                 checkAllLevelCounter(row, func, '1')
#     return True


@api_view(['GET'])
def checkThresholdCounterAPI(request):
    if request.method == 'GET':
        print("--------------im triggered------------")
        threshCounter = models.ThresholdCounterMaster.objects.all().values()
        for row in threshCounter:
            for func in functionList:
                if row.get(func+'_counter_level_3') != 0:
                    print("---------3---------")
                    checkAllLevelCounter(row, func, '3')
                if row.get(func+'_counter_level_2') != 0:
                    print("---------2---------")
                    checkAllLevelCounter(row, func, '2')
                if row.get(func+'_counter_level_1') != 0:
                    print("---------1---------")
                    checkAllLevelCounter(row, func, '1')
    return Response({"message": "Okay"}, status=status.HTTP_200_OK)


# @api_view(['GET'])
# def checkThresholdCounterAPI(request):
#     if request.method == 'GET':
#         # Fetch all keys from Redis
#         keys = redis_client.keys('*')  # Adjust the pattern if needed to fetch specific keys
#         print("---------------keys----------------", keys)

#         objects = []
#         for key in keys:
#             data = redis_client.get(key)
#             if isinstance(data, bytes):
#                 data = data.decode('utf-8')
#             data_dict = json.loads(data)
#             objects.append(data_dict)

#         for row in objects:
#             print("-----------row---------------", row)
#         return Response({"message": "Okay"}, status=status.HTTP_200_OK)




def CalculateDynamicThreshold(data, previous_thres, window=5):


    # if len(data) < 30:
    #     dataDict = {"result": False, "response": "Data not sufficient, calculating threshold"}
    #     return dataDict
    
    window_size = window
    moving_avg = []
    for i in range(0, len(data)):
        moving_avg.append(float(np.mean(data[i:window_size+i])))
    
    first = int(len(moving_avg)/2)

    dataMean = np.mean(moving_avg)
    dataStd = np.std(moving_avg)

    feature_1 = dataStd/dataMean
    feature_2 = (np.mean(moving_avg[first:]) - np.mean(moving_avg[:first]))/dataMean


    if feature_1 < 0.065 and feature_2 < 0.11:
        thres = np.mean(moving_avg)*2.2
        dataDict = {"result": True, "response": float(round(thres, 2))}
        return dataDict

    elif feature_2 < 0.11:
        thres = (dataMean+dataStd)*2.2
        dataDict = {"result": True, "response": float(round(thres, 2))}
        return dataDict
    
    else:
        if previous_thres:
            thres = previous_thres*1.5
            dataDict = {"result": True, "response": float(round(thres, 2))}
            return dataDict
        else:
            thres = np.mean(moving_avg)*2.2
            dataDict = {"result": True, "response": float(round(thres, 2))}
            return dataDict
            

# class CheckDynamicThreshold(APIView):


#     """//////////////////////////////// logic for automate threshold calculations ////////////////////////////////"""
    
#     # threshAssetList = models.ThresholdValues.objects.all().values("composite").distinct()
#     # compositeList = [i.get("composite") for i in threshAssetList]
#     # print("compositeList List", compositeList)
#     # # pdb.set_trace()
#     # assetList = models.DeviceMountMaster.objects.filter(~Q(composite_id__in=compositeList) & ~Q(composite_id__isnull=True)).values("asset_id", "composite_id").distinct()

#     def post(self, request, *args, **kwargs):

#         statfunctionList = ['rms', 'peak', 'peak_to_peak', 'kurtosis']
#         signalTypeListT = ['acceleration', 'velocity', 'temp']
#         axisList = ['Axial', 'Vertical', 'Horizontal']

#         df = JSONParser().parse(request)
#         if not df:
#                 return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
        
#         composite_key = df.get("composite_key")
#         mount_id = "_" + composite_key.split("_")[-1]
#         asset_id = df.get("asset_id")
#         fromDate = df.get("from_date")
#         toDate = df.get("to_date")
#         # pdb.set_trace()
#         try:
#             thresholdData = models.DynamicThresholdType.objects.get(asset_id=asset_id)
#             isDynamic = thresholdData.is_dynamic
#         except:
#             try:
#                 signalThresholdStatData = models.ThresholdValues.objects.filter(asset_id = asset_id)
#                 if len(signalThresholdStatData) == 0:
#                     dataObject = {"asset_id": asset_id, "is_dynamic": True}
#                     thresSerialize = serializers.DynamicThresholdTypeSerializer(data=dataObject)
#                     if thresSerialize.is_valid():
#                         thresSerialize.save()
#                         return Response({'message':"New asset, flag set to dynamic"},status=status.HTTP_201_CREATED)

#                 else:
#                     dataObject = {"asset_id": asset_id, "is_dynamic": False}
#                     thresSerialize = serializers.DynamicThresholdTypeSerializer(data=dataObject)
#                     if thresSerialize.is_valid():
#                         thresSerialize.save()
#                         return Response({'message':"Existing asset, flag set to not dynamic"},status=status.HTTP_201_CREATED)

#             except:
#                 return Response({'message':"Something went wrong while setting flag for dynamic threshold."},status=status.HTTP_404_NOT_FOUND)

#         if isDynamic:
#                 for signal in signalTypeListT:
#                     for selectedAxis in axisList:
#                         rms_function_filter = Q(**{'rms__lte': 45}) & Q(**{'rms__isnull': False})
#                         temp_function_filter = Q(**{'temp__lte': 145}) & Q(**{'temp__isnull': False})
#                         if fromDate and toDate:
#                             try:
#                                 newFromDate = datetime.fromtimestamp(fromDate)
#                                 newToDate = datetime.fromtimestamp(toDate)
#                                 # newFromDate = datetime.strptime(fromDate, '%Y-%m-%dT%H:%M:%S.%fZ')
#                                 # newToDate = datetime.strptime(toDate, '%Y-%m-%dT%H:%M:%S.%fZ')

                                
#                                 # for local database
#                                 # datetime_from = ist_timezone.localize(newFromDate)
#                                 # datetime_to = ist_timezone.localize(newToDate)

#                                 # for live database
#                                 datetime_from = utc_timezone.localize(newFromDate)
#                                 datetime_to = utc_timezone.localize(newToDate)
#                             except:
#                                 return Response({'message':"Something went wrong while converting timestamp."},status=status.HTTP_404_NOT_FOUND)

#                             if signal == 'acceleration':
#                                 signalStatData = models.AccelerationStatTimeMaster.objects.filter(
#                                     Q(composite__endswith=mount_id)& 
#                                     Q(timestamp__range=[datetime_from,datetime_to])&
#                                     Q(axis=selectedAxis)&
#                                     rms_function_filter
#                                     ).order_by("timestamp")
#                                 # signalStatData = models.AccelerationStatTimeMaster.objects.filter(composite=composite_key, timestamp__gte=thirty_days_ago, axis=selectedAxis).order_by("timestamp")[:30]
#                             elif signal == 'velocity':
#                                 signalStatData = models.VelocityStatTimeMaster.objects.filter(
#                                     Q(composite__endswith=mount_id)&
#                                     Q(timestamp__range=[datetime_from,datetime_to])&
#                                     Q(axis=selectedAxis)&
#                                     rms_function_filter
#                                     ).order_by("timestamp")
#                                 # signalStatData = models.VelocityStatTimeMaster.objects.filter(composite=composite_key, timestamp__gte=thirty_days_ago, axis=selectedAxis).order_by("timestamp")[:30]
#                             elif signal == 'temp':
#                                 selectedAxis = 'temp'
#                                 tempSignalStatData = models.TemperatureMaster.objects.filter(
#                                     Q(composite__endswith=mount_id)&
#                                     Q(timestamp__range=[datetime_from,datetime_to])&
#                                     Q(axis=selectedAxis)&
#                                     temp_function_filter
#                                     ).order_by("timestamp")
#                                 # tempSignalStatData = models.TemperatureMaster.objects.filter(composite=composite_key, timestamp__gte=thirty_days_ago, axis=selectedAxis).order_by("timestamp")[:30]
#                             else:
#                                 return True
#                         else:
#                             thirty_days_ago = (datetime.now() - timedelta(days=2)).replace(tzinfo=pytz.utc)
#                             # thirty_days_ago = (datetime.now() - timedelta(days=200)).replace(tzinfo=pytz.utc)
#                             """Need to remove this 30 day slicing in below lines. Need to add dynamic thresholding calculations as per date range."""
#                             if signal == 'acceleration':
#                                 signalStatData = models.AccelerationStatTimeMaster.objects.filter(
#                                     Q(composite__endswith=mount_id)&
#                                     Q(timestamp__gte=thirty_days_ago)&
#                                     Q(axis=selectedAxis)&
#                                     rms_function_filter
#                                     ).order_by("timestamp")
#                                 # signalStatData = models.AccelerationStatTimeMaster.objects.filter(composite=composite_key, timestamp__gte=thirty_days_ago, axis=selectedAxis).order_by("timestamp")[:30]
#                             elif signal == 'velocity':
#                                 signalStatData = models.VelocityStatTimeMaster.objects.filter(
#                                     Q(composite__endswith=mount_id)&
#                                     Q(timestamp__gte=thirty_days_ago)&
#                                     Q(axis=selectedAxis)&
#                                     rms_function_filter
#                                     ).order_by("timestamp")
#                                 # signalStatData = models.VelocityStatTimeMaster.objects.filter(composite=composite_key, timestamp__gte=thirty_days_ago, axis=selectedAxis).order_by("timestamp")[:30]
#                             elif signal == 'temp':
#                                 selectedAxis = 'temp'
#                                 tempSignalStatData = models.TemperatureMaster.objects.filter(
#                                     Q(composite__endswith=mount_id)&
#                                     Q(timestamp__gte=thirty_days_ago)&
#                                     Q(axis=selectedAxis)&
#                                     temp_function_filter
#                                     ).order_by("timestamp")
#                                 # tempSignalStatData = models.TemperatureMaster.objects.filter(composite=composite_key, timestamp__gte=thirty_days_ago, axis=selectedAxis).order_by("timestamp")[:30]
#                             else:
#                                 return True
#                         if len(signalStatData) >= 20:
#                             try:
#                                 existingDynamicThreshold = models.ThresholdValues.objects.get(composite__endswith=mount_id, axis=selectedAxis, signal_type=signal, domain='time')
#                             except:
#                                 existingDynamicThreshold = None
#                                 newDynamicThreshold = {"composite": composite_key, 'axis': selectedAxis, 'signal_type': signal, 'domain': 'time', 'asset_id': asset_id}

#                             if signal in ['acceleration', 'velocity']:
#                                 for statfunction in statfunctionList:
#                                     try:
#                                         previousValue = getattr(existingDynamicThreshold, statfunction+'_amp_level_1')
#                                     except:
#                                         previousValue = None

#                                     dataList = [getattr(row, statfunction) for row in signalStatData if getattr(row, statfunction) != None]
#                                     if len(dataList) > 0:
#                                         result = CalculateDynamicThreshold(dataList, previousValue, window=5)
#                                         thresh1 = result.get("response")
#                                         thresh2 = round(thresh1 * 1.55, 2)    #1.45
#                                         thresh3 = round(thresh1 * 2, 2)    #1.95
#                                         if existingDynamicThreshold != None:
#                                             setattr(existingDynamicThreshold, statfunction + '_amp_level_1', thresh1)
#                                             setattr(existingDynamicThreshold, statfunction + '_amp_level_2', thresh2)
#                                             setattr(existingDynamicThreshold, statfunction + '_amp_level_3', thresh3)
#                                         else:
#                                             newDynamicThreshold[statfunction + '_amp_level_1'] = thresh1
#                                             newDynamicThreshold[statfunction + '_amp_level_2'] = thresh2
#                                             newDynamicThreshold[statfunction + '_amp_level_3'] = thresh3
                                            

#                             elif signal == 'temp':
#                                 try:
#                                     previousValue = getattr(existingDynamicThreshold, statfunction+'_amp_level_1')
#                                 except:
#                                     previousValue = None
                                
#                                 dataList = [getattr(row, 'temp') for row in tempSignalStatData if getattr(row, 'temp') != None]

#                                 if len(dataList) > 0:
#                                     result = CalculateDynamicThreshold(dataList, previousValue, window=5)
#                                     thresh1 = result.get("response")
#                                     thresh2 = round(thresh1 * 1.55, 2)      #1.45
#                                     thresh3 = round(thresh1 * 2, 2)      #1.95
#                                     if existingDynamicThreshold != None:
#                                         setattr(existingDynamicThreshold, 'temp_amp_level_1', thresh1)
#                                         setattr(existingDynamicThreshold, 'temp_amp_level_2', thresh2)
#                                         setattr(existingDynamicThreshold, 'temp_amp_level_3', thresh3)
#                                     else:
#                                         newDynamicThreshold['temp_amp_level_1'] = thresh1
#                                         newDynamicThreshold['temp_amp_level_2'] = thresh2
#                                         newDynamicThreshold['temp_amp_level_3'] = thresh3

#                             if existingDynamicThreshold != None:
#                                 existingDynamicThreshold.save()
#                             else:
#                                 updatedNewDynamicThresholdSerializer = serializers.ThresholdValuesSerializer(data = newDynamicThreshold)
#                                 if updatedNewDynamicThresholdSerializer.is_valid():
#                                         updatedNewDynamicThresholdSerializer.save()

#                             try:    
#                                 existingCount = models.ThresholdCounterMaster.objects.get(composite = composite_key, axis = selectedAxis, signal_type = signal, domain = "time")
#                                 pass
#                             except models.ThresholdCounterMaster.DoesNotExist:
#                                 counter_values = {
#                                     "composite": composite_key, 'axis': selectedAxis, 'signal_type': signal, 'domain': 'time', \
#                                         "rms_amp_repetition_level_1": 3 ,"peak_amp_repetition_level_1": 3 ,"peak_to_peak_amp_repetition_level_1": 3 ,\
#                                             "kurtosis_amp_repetition_level_1": 3 ,"temp_amp_repetition_level_1": 3 ,"rms_amp_repetition_level_2": 3 ,\
#                                                 "peak_amp_repetition_level_2": 3 ,"peak_to_peak_amp_repetition_level_2": 3 ,"kurtosis_amp_repetition_level_2": 3 ,\
#                                                     "temp_amp_repetition_level_2": 3 ,"rms_amp_repetition_level_3": 3 ,"peak_amp_repetition_level_3": 3 ,\
#                                                         "peak_to_peak_amp_repetition_level_3": 3 ,"kurtosis_amp_repetition_level_3": 3 ,"temp_amp_repetition_level_3": 3, \
#                                                             'asset_id': asset_id
#                                             }
#                                 countSer = serializers.ThresholdCounterMasterSerializer(data=counter_values)
#                                 if countSer.is_valid():
#                                     countSer.save()
                                    
#                             # countSer = serializers.ThresholdCounterMasterSerializer(data=counter_values, partial=True)
#                             # if countSer.is_valid():
#                             #     print("here before saving counter values")
#                             #     countSer.save()
#                         else:
#                             return Response({'message':"Data not sufficient for calculations. Requires minimum 30 data points."},status=status.HTTP_204_NO_CONTENT)
#                 return Response({'message':"Dynamic thresholds saved."},status=status.HTTP_201_CREATED)
#         else:
#             return Response({'message':"Threshold type not set to dynamic."},status=status.HTTP_404_NOT_FOUND)
        



class CheckDynamicThreshold(APIView):


    """//////////////////////////////// logic for automate threshold calculations ////////////////////////////////"""
    
    # threshAssetList = models.ThresholdValues.objects.all().values("composite").distinct()
    # compositeList = [i.get("composite") for i in threshAssetList]
    # print("compositeList List", compositeList)
    # # pdb.set_trace()
    # assetList = models.DeviceMountMaster.objects.filter(~Q(composite_id__in=compositeList) & ~Q(composite_id__isnull=True)).values("asset_id", "composite_id").distinct()

    def post(self, request, *args, **kwargs):

        try:

            # statfunctionList = ['rms', 'peak', 'peak_to_peak']
            signalTypeListT = ['acceleration', 'velocity', 'temp']
            axisList = ['Axial', 'Vertical', 'Horizontal']

            df = JSONParser().parse(request)
            if not df:
                    return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
            
            assetList = df.get("assetList")
            acc_value = df.get("acc_val")
            vel_value = df.get("vel_val")
            # threshold calculation logic
            for asset_id in assetList:
                print("--------asset_id---------", asset_id)
                compObj = models.DeviceMountMaster.objects.filter(asset_id=asset_id).values("composite_id")
                for single_comp in compObj:
                    if single_comp.get("composite_id"):
                        # print("compoooooooooooooooo", single_comp.get("composite_id"))
                        composite_key = single_comp.get("composite_id")
                        mount_id = "_" + composite_key.split("_")[-1]
                        newMount = composite_key.split("_")[-1]
                        temp_function_filter = Q(**{'temp__lte': 145}) & Q(**{'temp__isnull': False})
                        # thirty_days_ago = (datetime.now() - timedelta(days=400)).replace(tzinfo=pytz.utc)
                        # thirty_days_ago = (datetime.now() - timedelta(days=180)).replace(tzinfo=pytz.utc)
                        # timestampList = models.TemperatureMaster.objects.filter(
                        #                 Q(mount_id=newMount)&
                        #                 Q(timestamp__gte=thirty_days_ago)&
                        #                 Q(axis='temp')&
                        #                 temp_function_filter
                        #                 ).order_by("timestamp").values_list('timestamp', flat=True)
                        # print("-------------------stat data-----------------", timestampList)


                        for signal in signalTypeListT:
                            for selectedAxis in axisList:

                                # thirty_days_ago = timezone.now() - timedelta(days=600)
                                # thirty_days_ago = (datetime.now() - timedelta(days=200)).replace(tzinfo=pytz.utc)
                                """Need to remove this 30 day slicing in below lines. Need to add dynamic thresholding calculations as per date range."""
                                if signal == 'acceleration':
                                    print("---acc---")
                                    # try:
                                    #     rms_function_filter2 = Q(**{'rms'+'_'+selectedAxis+'__lte': 45}) & Q(**{'rms'+'_'+selectedAxis+'__gt': 0.1}) & Q(**{'rms'+'_'+selectedAxis+'__isnull': False})
                                        
                                    #     signalStatData = models.AccelerationStatTimeOptimized.objects.filter(
                                    #         Q(mount_id=newMount)& 
                                    #         Q(timestamp__gte=thirty_days_ago)& 
                                    #         Q(timestamp__lt=timezone.now())&
                                    #         Q(rms_function_filter2)
                                    #         )
                                    # except Exception as e:
                                    #     print("------------e--------------", e)


                                    try:
                                        rms_function_filter2 = Q(**{'rms'+'_'+selectedAxis+'__lte': 45}) & Q(**{'rms'+'_'+selectedAxis+'__gt': acc_value}) & Q(**{'rms'+'_'+selectedAxis+'__isnull': False})
                                        signalStatData = models.AccelerationStatTimeOptimized.objects.filter(
                                            Q(mount_id=newMount) & 
                                            rms_function_filter2
                                        )[:3000]
                                        print("---acc data---", signalStatData)
                                    except Exception as e:
                                        print("------------e--------------", e)

                                        
                                        
                                elif signal == 'velocity':
                                    print("---vel---")
                                    # try:
                                    #     rms_function_filter2 = Q(**{'rms'+'_'+selectedAxis+'__lte': 45}) & Q(**{'rms'+'_'+selectedAxis+'__gt': 0.1}) & Q(**{'rms'+'_'+selectedAxis+'__isnull': False})
                                        
                                    #     signalStatData = models.AccelerationStatTimeOptimized.objects.filter(
                                    #         Q(mount_id=newMount)& 
                                    #         Q(timestamp__gte=thirty_days_ago)& 
                                    #         Q(timestamp__lt=timezone.now())&
                                    #         Q(rms_function_filter2)
                                    #         )
                                    # except Exception as e:
                                    #     print("------------e--------------", e)

                                    try:
                                        rms_function_filter2 = Q(**{'rms'+'_'+selectedAxis+'__lte': 45}) & Q(**{'rms'+'_'+selectedAxis+'__gt': vel_value}) & Q(**{'rms'+'_'+selectedAxis+'__isnull': False})
                                        signalStatData = models.VelocityStatTimeOptimized.objects.filter(
                                            Q(mount_id=newMount) & 
                                            rms_function_filter2
                                        )[:3000]
                                        print("---vel data---", signalStatData)
                                    except Exception as e:
                                        print("------------e--------------", e)



                                elif signal == 'temp':
                                    print("---temp---")
                                    selectedAxis = 'temp'
                                    # tempSignalStatData = models.TemperatureMaster.objects.filter(
                                    #     Q(mount_id=newMount)&
                                    #     Q(timestamp__in=timestampList)
                                    #     ).order_by("timestamp")
                                    # tempSignalStatData = models.TemperatureMaster.objects.filter(composite=composite_key, timestamp__gte=thirty_days_ago, axis=selectedAxis).order_by("timestamp")[:30]
                                    try:
                                        tempSignalStatData = models.TemperatureMaster.objects.filter(mount_id=newMount, axis=selectedAxis)[:3000]
                                        print("---temp data---", tempSignalStatData)
                                    except Exception as e:
                                        print("------------e--------------", e)
                                
                                else:
                                    return True
                                if len(signalStatData) >= 20:
                                    # try:
                                        # existingDynamicThreshold = models.ThresholdValues.objects.get(composite__endswith=mount_id, axis=selectedAxis, signal_type=signal, domain='time')
                                    # except:
                                        # existingDynamicThreshold = None
                                    DynamicThreshold = {"composite": composite_key, 'axis': selectedAxis, 'signal_type': signal, 'domain': 'time', 'asset_id': asset_id}
                                    # DynamicThresholdCounter = {"composite": composite_key, 'axis': selectedAxis, 'signal_type': signal, 'domain': 'time', 'asset_id': asset_id}

                                    if signal in ['acceleration', 'velocity']:
                                        if signal == 'acceleration':
                                            statfunctionList = ['rms', 'peak_to_peak']
                                        else:
                                            statfunctionList = ['rms']
                                        for statfunction in statfunctionList:
                                            try:
                                                # previousValue = getattr(existingDynamicThreshold, statfunction+'_amp_level_1')
                                                previousValue = DynamicThreshold.get(statfunction+'_amp_level_1')
                                            except:
                                                previousValue = None

                                            # dataList = [getattr(row, statfunction) for row in signalStatData if getattr(row, statfunction) != None]
                                            dataList = [getattr(row, statfunction+"_"+selectedAxis) for row in signalStatData if getattr(row, statfunction+"_"+selectedAxis) != None]
                                            # print("--------------------newMount---------------------", newMount)
                                            # print("--------------------dataList2---------------------", dataList)
                                            if len(dataList) > 0:
                                                result = CalculateDynamicThreshold(dataList, previousValue, window=5)
                                                thresh1 = result.get("response")
                                                thresh2 = round(thresh1 * 2, 2)    #1.45
                                                thresh3 = round(thresh1 * 2.5, 2)    #1.95
                                                # if existingDynamicThreshold != None:
                                                #     setattr(existingDynamicThreshold, statfunction + '_amp_level_1', thresh1)
                                                #     setattr(existingDynamicThreshold, statfunction + '_amp_level_2', thresh2)
                                                #     setattr(existingDynamicThreshold, statfunction + '_amp_level_3', thresh3)
                                                # else:
                                                DynamicThreshold[statfunction + '_amp_level_1'] = thresh1
                                                DynamicThreshold[statfunction + '_amp_level_2'] = thresh2
                                                DynamicThreshold[statfunction + '_amp_level_3'] = thresh3
                                    elif signal == 'temp':
                                        try:
                                            previousValue = DynamicThreshold.get(statfunction+'_amp_level_1')
                                        except:
                                            previousValue = None
                                        
                                        dataList = [getattr(row, 'temp') for row in tempSignalStatData if getattr(row, 'temp') != None]

                                        if len(dataList) > 0:
                                            result = CalculateDynamicThreshold(dataList, previousValue, window=5)
                                            thresh1 = result.get("response")
                                            thresh2 = round(thresh1 * 2, 2)      #1.45
                                            thresh3 = round(thresh1 * 2.5, 2)      #1.95
                                            # if existingDynamicThreshold != None:
                                            #     setattr(existingDynamicThreshold, 'temp_amp_level_1', thresh1)
                                            #     setattr(existingDynamicThreshold, 'temp_amp_level_2', thresh2)
                                            #     setattr(existingDynamicThreshold, 'temp_amp_level_3', thresh3)
                                            # else:
                                            DynamicThreshold['temp_amp_level_1'] = thresh1
                                            DynamicThreshold['temp_amp_level_2'] = thresh2
                                            DynamicThreshold['temp_amp_level_3'] = thresh3
                                    try:
                                        with transaction.atomic():
                                            obj1, created1 = models.ThresholdValues.objects.update_or_create(
                                                            composite=composite_key,
                                                            axis=selectedAxis,
                                                            signal_type=signal,
                                                            asset_id=asset_id,
                                                            mount_id=newMount,
                                                            defaults=DynamicThreshold
                                                        )
                                            print("--------------------obj1---------------------", obj1, created1)
                                            DynamicThresholdCounter = {"composite": composite_key, 'axis': selectedAxis, 'signal_type': signal, 'domain': 'time', \
                                                "rms_amp_repetition_level_1": 10 ,"peak_amp_repetition_level_1": 10 ,"peak_to_peak_amp_repetition_level_1": 10 ,\
                                                    "kurtosis_amp_repetition_level_1": 10 ,"temp_amp_repetition_level_1": 10 ,"rms_amp_repetition_level_2": 10 ,\
                                                        "peak_amp_repetition_level_2": 10 ,"peak_to_peak_amp_repetition_level_2": 10 ,"kurtosis_amp_repetition_level_2": 10 ,\
                                                            "temp_amp_repetition_level_2": 10 ,"rms_amp_repetition_level_3": 10 ,"peak_amp_repetition_level_3": 10 ,\
                                                                "peak_to_peak_amp_repetition_level_3": 10 ,"kurtosis_amp_repetition_level_3": 10 ,"temp_amp_repetition_level_3": 10, \
                                                                    'asset_id': asset_id}
                                            obj2, created2 = models.ThresholdCounterMaster.objects.update_or_create(
                                                            composite=composite_key,
                                                            axis=selectedAxis,
                                                            signal_type=signal,
                                                            asset_id=asset_id,
                                                            mount_id=newMount,
                                                            defaults=DynamicThresholdCounter
                                                        )
                                            print("--------------------obj2---------------------", obj2, created2)
                                    except Exception as e:
                                        print("----------sdfdsfdsfsdfsdf-----------", e)
                                    # # pdb.set_trace()
                                    # if existingDynamicThreshold != None:
                                    #     existingDynamicThreshold.save()
                                    # else:
                                    #     updatedNewDynamicThresholdSerializer = serializers.ThresholdValuesSerializer(data = newDynamicThreshold)
                                    #     counter_values = {
                                    #         "composite": composite_key, 'axis': selectedAxis, 'signal_type': signal, 'domain': 'time', \
                                    #             "rms_amp_repetition_level_1": 3 ,"peak_amp_repetition_level_1": 3 ,"peak_to_peak_amp_repetition_level_1": 3 ,\
                                    #                 "kurtosis_amp_repetition_level_1": 3 ,"temp_amp_repetition_level_1": 3 ,"rms_amp_repetition_level_2": 3 ,\
                                    #                     "peak_amp_repetition_level_2": 3 ,"peak_to_peak_amp_repetition_level_2": 3 ,"kurtosis_amp_repetition_level_2": 3 ,\
                                    #                         "temp_amp_repetition_level_2": 3 ,"rms_amp_repetition_level_3": 3 ,"peak_amp_repetition_level_3": 3 ,\
                                    #                             "peak_to_peak_amp_repetition_level_3": 3 ,"kurtosis_amp_repetition_level_3": 3 ,"temp_amp_repetition_level_3": 3, \
                                    #                                 'asset_id': asset_id
                                    #                 }
                                    #     print("-----------------------counter_values----------------------", counter_values)
                                    #     countSer = serializers.ThresholdCounterMasterSerializer(data=counter_values)
                                    #     if countSer.is_valid():
                                    #         if updatedNewDynamicThresholdSerializer.is_valid():
                                    #             updatedNewDynamicThresholdSerializer.save()
                                    #             countSer.save()
                                    # print("data save for composite {0}".format(composite_key) )
        except Exception as ee:
            print("-------eeeeeeeeeeeee-------", ee)

        return Response({'message':"All Done"},status=status.HTTP_200_OK)
                








