from datetime import datetime, timedelta
from decimal import Decimal
import os
import re
import logging
import traceback
import uuid
from django.utils import timezone
from django.db.models import Q, Count
from app import models
from app import serializers
import json
import pdb
import pytz
import numpy as np
import math
from django.db import connection
from rest_framework.views import APIView
from rest_framework.parsers import JSONParser
from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import api_view
from datetime import datetime, date
from django.db.models.functions import Trunc
from django.db.models import DateTimeField
from django.db.models import DateTimeField, Max
import redis
import boto3
from .cache import redis_client_rms_batch
from rest_framework.decorators import api_view
from django.db import transaction
from django.conf import settings
from celery import shared_task
from app.auto_diagnostics.impact_diagnostics_v4 import (
    build_impact_axis_feature_cache,
    detect_bearing_fault_frequencies,
    detect_lubrication_issue,
)
from app.auto_diagnostics.bent_shaft_v4 import detect_bent_shaft
from app.auto_diagnostics.cavitation_or_aeration_v4 import detect_cavitation_or_aeration
from app.auto_diagnostics.coupling_related_shaft_v4 import detect_coupling_related_shaft_faults
from app.auto_diagnostics.hydraulic_vane_blade_pass_v4 import detect_hydraulic_vane_blade_pass
from app.auto_diagnostics.mechanical_looseness_v4 import detect_mechanical_looseness
from app.auto_diagnostics.misalignment_v4 import detect_misalignment
from app.auto_diagnostics.unbalance_v4 import detect_unbalance
from app.models import (
    AccelerationStatTimeOptimized,
    BearingFaultFrequenciesMaster,
    RawDataMaster,
    SignalProcessingMaster,
    DeviceMountMaster,
)

logger = logging.getLogger(__name__)

VIBRATION_AXES = ["Axial", "Vertical", "Horizontal"]
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "meta.llama3-70b-instruct-v1:0")
BEDROCK_REGION = os.getenv("AWS_BEDROCK_REGION") or os.getenv("AWS_REGION") or os.getenv("AWS_S3_REGION_NAME") or "us-east-1"


def my_daily_task():
    print("Im runninggggggggg")


def calculateAssetHealthHistory():
    currentDate = datetime.now().date()  # GMT time
    existingData = models.AssetHealthHistoryMaster.objects.filter(creation_date=currentDate)
    if len(existingData):
        assets_to_exclude = [item.asset_id for item in existingData] 
        assetHealthHistory = models.AssetHealthMaster.objects.all().values('asset_id','org_id','status').exclude(asset_id__in=assets_to_exclude)
        if len(assetHealthHistory)>0:
            assetHealthHistoryData = [{"asset_id": row.get("asset_id"), "org_id": row.get("org_id"), "status": row.get("status")} for row in assetHealthHistory]
            assetHealthHistorySerializer = serializers.AssetHealthHistoryMasterSerializer(data=assetHealthHistoryData, many=True)
            if assetHealthHistorySerializer.is_valid():
                assetHealthHistorySerializer.save()
            else:
                print( "pdm, wrong", assetHealthHistorySerializer.errors)
        else:
            pass
    else:
        assetHealthHistory = models.AssetHealthMaster.objects.all().values('asset_id','org_id','status')
        assetHealthHistoryData = [{"asset_id": row.get("asset_id"), "org_id": row.get("org_id"), "status": row.get("status")} for row in assetHealthHistory]
        assetHealthHistorySerializer = serializers.AssetHealthHistoryMasterSerializer(data=assetHealthHistoryData, many=True)
        if assetHealthHistorySerializer.is_valid():
            assetHealthHistorySerializer.save()
        else:
            print("pdm wrong", assetHealthHistorySerializer.errors)


# class CalculateAssetHealthScore(APIView):

#     def get(self, request, *args, **kwargs):
#         axisList = ["Axial", "Vertical", "Horizontal", "temp"]
#         statfunctionList = ['rms', 'peak', 'peak_to_peak', 'kurtosis']
#         signalTypeListT = ['acceleration', 'velocity', 'temp']

#         yesterday = timezone.now() - timedelta(days=60)

#         try:
#             assetList = models.DeviceMountMaster.objects.values("asset_id").distinct()
#             for singleAsset in assetList:
#                 compositeList = models.DeviceMountMaster.objects.filter(asset_id=singleAsset.get("asset_id"))
#                 for compositeKey in compositeList:

#                     try:
#                         existingThreshold = models.ThresholdValues.objects.filter(composite=compositeKey.composite_id)
#                     except:
#                         existingThreshold = []
                    

#                     for signal in signalTypeListT:
#                         if signal == "acceleration":
#                             signalStatData = models.AccelerationStatTimeMaster.objects.filter(composite=compositeKey.composite_id, timestamp__gte=yesterday, timestamp__lt=timezone.now())
#                         elif signal == "velocity":
#                             signalStatData = models.VelocityStatTimeMaster.objects.filter(composite=compositeKey.composite_id, timestamp__gte=yesterday, timestamp__lt=timezone.now())
#                         elif signal == 'temp':
#                             signalStatData = models.TemperatureMaster.objects.filter(composite=compositeKey.composite_id, timestamp__gte=yesterday, timestamp__lt=timezone.now())

                        
#                         if len(signalStatData) > 0 and len(existingThreshold) > 0:


#                             for axis in axisList:
#                                 axisThresholdData = existingThreshold.filter(signal_type = signal, axis= axis)
#                                 if axis in ["Axial", "Vertical", "Horizontal"]:
#                                     axisStatData = [i for i in signalStatData[:10] if i.axis == axis]
#                                 else:
#                                     axisStatData = [i for i in signalStatData[:10] if i.axis == 'temp']
#                                 for statFunction in statfunctionList:
#                                     print("bbbbbbbbbbbbbbbbbb", statFunction)
#                                     functionLevel1 = getattr(axisThresholdData[0], statFunction+'_amp_level_1')
#                                     functionLevel2 = getattr(axisThresholdData[0], statFunction+'_amp_level_2')
#                                     functionLevel3 = getattr(axisThresholdData[0], statFunction+'_amp_level_3')
#                                     functionLevel3Count = len([i for i in signalStatData if getattr(i, statFunction) >= functionLevel3])
#                                     functionLevel2Count = len([i for i in signalStatData if functionLevel3 > getattr(i, statFunction) >= functionLevel2])
#                                     functionLevel1Count = len([i for i in signalStatData if functionLevel2 > getattr(i, statFunction) >= functionLevel1])
#                                     print("functionLevel3Count", axis, functionLevel3Count)
#                                     print("functionLevel2Count", axis, functionLevel2Count)
#                                     print("functionLevel1Count",axis, functionLevel1Count)



#                         else:
#                             print("no data in last 24 hours", compositeKey.composite_id)



#             return Response({"status": True, "message": "All done"}, status=status.HTTP_200_OK) 
#         except:
#             return Response({"status": False, "message": "Something went wrong"}, status=status.HTTP_400_BAD_REQUEST) 



def calculateScore(thresh3, thresh2, thresh1, percent3, percent2, percent1, percent0):

    scale = 10/thresh3
    
    factor3 = 1.5
    factor2 = 1.4
    factor1 = 1.25
    factor0 = 0.05

    scale3 = scale*thresh3
    scale2 = scale*thresh2
    scale1 = scale*thresh1

    weightage = scale3*percent3*factor3 + scale2*percent2*factor2 + scale1*percent1*factor1 + percent0*factor0
    if weightage > 10:
        normalizeScore = 0
    else:
        normalizeScore = 10-weightage

    return round(normalizeScore,4)

def getAssetHealthFlag(score):
    if score != None:
        if 0 < score <= 4:
            res = {"result": True, "flag": "Critical"}
        elif 4 < score <= 6:
            res = {"result": True, "flag": "Danger"}
        elif 6 < score <= 8:
            res = {"result": True, "flag": "Alert"}
        elif 8 < score <= 10:
            res = {"result": True, "flag": "Healthy"}
        else:
            res = {"result": False, "flag": "error"}
    else:
        res = {"result": False, "flag": "error"}
    return res



# def CalculateAssetHealthScore():

# class CalculateAssetHealthScore(APIView):

#     def get(self, request, *args, **kwargs):

#         axisList = ["Axial", "Vertical", "Horizontal"]
#         signalTypeList = ['acceleration', 'velocity']

#         # yesterday = timezone.now() - timedelta(days=1)
#         yesterday = timezone.now() - timedelta(days=150)
#         print("today date", timezone.now())
#         print("yesterday date", yesterday)

#         try:
#             assetList = models.DeviceMountMaster.objects.values("asset_id", "org_id").distinct()
#             for singleAsset in assetList:
#                 EndPointscoreList = []
#                 compositeList = models.DeviceMountMaster.objects.filter(asset_id=singleAsset.get("asset_id"))
#                 for compositeKey in compositeList:
#                     scoreDict = {}
#                     scoreList = []

#                     try:
#                         existingThreshold = models.ThresholdValues.objects.filter(composite=compositeKey.composite_id)
#                     except:
#                         existingThreshold = []
                    
#                     if len(existingThreshold) > 0:
                        
#                         for axis in axisList:
#                             for signal in signalTypeList:
#                                 if signal == 'acceleration':
#                                     signalStatData = models.AccelerationStatTimeMaster.objects.filter(composite=compositeKey.composite_id, axis=axis, timestamp__gte=yesterday, timestamp__lt=timezone.now())
#                                 elif signal == 'velocity':
#                                     signalStatData = models.VelocityStatTimeMaster.objects.filter(composite=compositeKey.composite_id, axis=axis, timestamp__gte=yesterday, timestamp__lt=timezone.now())
#                                 if len(signalStatData) > 0:
#                                     print("len greater than zero")
#                                     emptyData = False
#                                     row = existingThreshold.filter(axis=axis, signal_type=signal)[0]
#                                     rms_level_1 = float(row.rms_amp_level_1)
#                                     rms_level_2 = float(row.rms_amp_level_2)
#                                     rms_level_3 = float(row.rms_amp_level_3)
#                                     rms_result1 = len(signalStatData.filter( Q(rms__gte=rms_level_1) & Q(rms__lt=rms_level_2)).values('rms'))
#                                     rms_result2 = len(signalStatData.filter( Q(rms__gte=rms_level_2) & Q(rms__lt=rms_level_3)).values('rms'))
#                                     rms_result3 = len(signalStatData.filter( Q(rms__gte=rms_level_3)).values('rms'))
#                                     rms_result1_percentage = (rms_result1/len(signalStatData))
#                                     rms_result2_percentage = (rms_result2/len(signalStatData))
#                                     rms_result3_percentage = (rms_result3/len(signalStatData))
#                                     rms_result0_percentage = 1 - rms_result1_percentage + rms_result2_percentage + rms_result3_percentage
#                                     rScore = calculateScore(rms_level_3, rms_level_2, rms_level_1, rms_result3_percentage, rms_result2_percentage, rms_result1_percentage,rms_result0_percentage)
#                                     scoreDict.update({axis+'-'+signal+'-rms': rScore})
#                                     scoreList.append(rScore)


#                                     peak_level_1 = float(row.peak_amp_level_1)
#                                     peak_level_2 = float(row.peak_amp_level_2)
#                                     peak_level_3 = float(row.peak_amp_level_3)
#                                     peak_result1 = len(signalStatData.filter( Q(peak__gte=peak_level_1) & Q(peak__lt=peak_level_2)).values('peak'))
#                                     peak_result2 = len(signalStatData.filter( Q(peak__gte=peak_level_2) & Q(peak__lt=peak_level_3)).values('peak'))
#                                     peak_result3 = len(signalStatData.filter( Q(peak__gte=peak_level_3)).values('peak'))
#                                     peak_result1_percentage = (peak_result1/len(signalStatData))
#                                     peak_result2_percentage = (peak_result2/len(signalStatData))
#                                     peak_result3_percentage = (peak_result3/len(signalStatData))
#                                     peak_result0_percentage = 1- peak_result3_percentage + peak_result2_percentage + peak_result1_percentage
#                                     pScore = calculateScore(peak_level_3, peak_level_2, peak_level_1, peak_result3_percentage, peak_result2_percentage, peak_result1_percentage,peak_result0_percentage)
#                                     scoreDict.update({axis+'-'+signal+'-peak ': pScore})
#                                     scoreList.append(pScore)

#                                     peak_to_peak_level_1 = float(row.peak_to_peak_amp_level_1)
#                                     peak_to_peak_level_2 = float(row.peak_to_peak_amp_level_2)
#                                     peak_to_peak_level_3 = float(row.peak_to_peak_amp_level_3)
#                                     peak_to_peak_result1 = len(signalStatData.filter( Q(peak_to_peak__gte=peak_to_peak_level_1) & Q(peak_to_peak__lt=peak_to_peak_level_2)).values('peak_to_peak'))
#                                     peak_to_peak_result2 = len(signalStatData.filter( Q(peak_to_peak__gte=peak_to_peak_level_2) & Q(peak_to_peak__lt=peak_to_peak_level_3)).values('peak_to_peak'))
#                                     peak_to_peak_result3 = len(signalStatData.filter( Q(peak_to_peak__gte=peak_to_peak_level_3)).values('peak_to_peak'))
#                                     peak_to_peak_result1_percentage = (peak_to_peak_result1/len(signalStatData))
#                                     peak_to_peak_result2_percentage = (peak_to_peak_result2/len(signalStatData))
#                                     peak_to_peak_result3_percentage = (peak_to_peak_result3/len(signalStatData))
#                                     peak_to_peak_result0_percentage = 1 - peak_to_peak_result3_percentage + peak_to_peak_result2_percentage + peak_to_peak_result1_percentage
#                                     p2pScore = calculateScore(peak_to_peak_level_3, peak_to_peak_level_2, peak_to_peak_level_1, peak_to_peak_result3_percentage, peak_to_peak_result2_percentage, peak_to_peak_result1_percentage,peak_to_peak_result0_percentage)
#                                     scoreDict.update({axis+'-'+signal+'-peak2peak': p2pScore})
#                                     scoreList.append(p2pScore)

#                                     kurtosis_level_1 = float(row.kurtosis_amp_level_1)
#                                     kurtosis_level_2 = float(row.kurtosis_amp_level_2)
#                                     kurtosis_level_3 = float(row.kurtosis_amp_level_3)
#                                     kurtosis_result1 = len(signalStatData.filter( Q(kurtosis__gte=kurtosis_level_1) & Q(kurtosis__lt=kurtosis_level_2)).values('kurtosis'))
#                                     kurtosis_result2 = len(signalStatData.filter( Q(kurtosis__gte=kurtosis_level_2) & Q(kurtosis__lt=kurtosis_level_3)).values('kurtosis'))
#                                     kurtosis_result3 = len(signalStatData.filter( Q(kurtosis__gte=kurtosis_level_3)).values('kurtosis'))
#                                     kurtosis_result1_percentage = (kurtosis_result1/len(signalStatData))
#                                     kurtosis_result2_percentage = (kurtosis_result2/len(signalStatData))
#                                     kurtosis_result3_percentage = (kurtosis_result3/len(signalStatData))
#                                     kurtosis_result0_percentage = 1 - kurtosis_result3_percentage + kurtosis_result2_percentage + kurtosis_result1_percentage
#                                     kScore = calculateScore(kurtosis_level_3, kurtosis_level_2, kurtosis_level_1, kurtosis_result3_percentage, kurtosis_result2_percentage, kurtosis_result1_percentage,kurtosis_result0_percentage)
#                                     scoreDict.update({axis+'-'+signal+'-kurtosis': kScore})
#                                     scoreList.append(kScore)
#                                     print("scoreDictscoreDict", scoreDict)
#                                 else:
#                                     emptyData = True


#                                 # print("************************************************", compositeKey.composite_id)
#                                 # print( "rms_result1----", round(rms_result1_percentage, 2), "rms_result2----", round(rms_result2_percentage, 2), "rms_result3----", round(rms_result3_percentage, 2), "peak_result1----", round(peak_result1_percentage, 2), \
#                                 #       "peak_result2----", round(peak_result2_percentage, 2), "peak_result3----", round(peak_result3_percentage, 2), "peak_to_peak_result1----", round(peak_to_peak_result1_percentage, 2), \
#                                 #         "peak_to_peak_result2----", round(peak_to_peak_result2_percentage, 2), "peak_to_peak_result3----", round(peak_to_peak_result3_percentage, 2), "kurtosis_result1----", round(kurtosis_result1_percentage, 2), \
#                                 #             "kurtosis_result2----", round(kurtosis_result2_percentage, 2), "kurtosis_result3----", round(kurtosis_result3_percentage, 2))
#                         if emptyData == False:
#                             worse_4_kpi = sorted(scoreList)[:4]
#                             worse_4_kpi_mean = round(np.mean(worse_4_kpi),2)
#                             EndPointscoreList.append(worse_4_kpi_mean)
#                         else:
#                             EndPointscoreList = [None]
#                     else:
#                         pass
#                 if len(EndPointscoreList) > 0:
#                     print("EndPointscoreListEndPointscoreList", EndPointscoreList)
#                     finalScore = sorted(EndPointscoreList)[0]
#                 else:
#                     finalScore = None
#                 asset_status = getAssetHealthFlag(finalScore)
#                 try:
#                     existingAssetHealthData = models.AssetHealthMaster.objects.get(asset_id=singleAsset.get("asset_id"))
#                     existingAssetHealthData.status = asset_status
#                     existingAssetHealthData.score = finalScore
#                     # print("existingAssetHealthData ")
#                     # existingAssetHealthData.save()
#                 except:
#                     asset_health_data =  {"asset_id": singleAsset.get("asset_id"), "org_id": singleAsset.get("org_id"), "status": asset_status, "score": finalScore}
#                     healthSerializerData = serializers.AssetHealthMasterSerializer(data=asset_health_data)
#                     if healthSerializerData.is_valid():
#                         pass
#                         # print("healthSerializerData valid")
#                         # healthSerializerData.save()
                        
#                 """Saving asset status in asset health history table"""
#                 assetHealthHistoryData = {"asset_id": singleAsset.get("asset_id"), "org_id": singleAsset.get("org_id"), "status": asset_status}
#                 assetHealthHistorySerializer = serializers.AssetHealthHistoryMasterSerializer(data=assetHealthHistoryData)
#                 if assetHealthHistorySerializer.is_valid():
#                     pass
#                     # print("assetHealthHistorySerializer valid")
#                     # assetHealthHistorySerializer.save()
#                 else:
#                     print("Something wrong in saving asset health history data in score calculations")

#             print("All done") 
#         except:
#             print("Something went wrong")




def CalculateAssetHealthScore():
    return True


class CalculateAssetHealthScoreManually(APIView):
        
        def post(self, request, *args, **kwargs):

            yesterday = timezone.now() - timedelta(days=1)
            axisList = ["Axial", "Vertical", "Horizontal"]
            signalTypeList = ['acceleration', 'velocity']

            try:
                assetList = models.DeviceMountMaster.objects.values("asset_id", "org_id").distinct()
                for singleAsset in assetList:
                        print("---------singleAsset----------", singleAsset)
                        # pdb.set_trace()
                    # if singleAsset.get("asset_id") == "64f6cba7f1387352cbd4e2b4":
                        EndPointscoreList = []
                        compositeList = models.DeviceMountMaster.objects.filter(asset_id=singleAsset.get("asset_id"))
                        for compositeKey in compositeList:
                            print("-----------comp--------", compositeKey)
                            scoreDict = {}
                            scoreList = []

                            try:
                                existingThreshold = models.ThresholdValues.objects.filter(composite=compositeKey.composite_id)
                            except:
                                existingThreshold = []
                            if len(existingThreshold) > 0:
                                for singleThres in existingThreshold:
                                    print("---------singleThres-------", singleThres)
                                    axis = getattr(singleThres, "axis")
                                    signal = getattr(singleThres, "signal_type")
                                    if signal == "acceleration":
                                        signalStatData = models.AccelerationStatTimeMaster.objects.filter(composite=compositeKey.composite_id, axis=axis, timestamp__gte=yesterday, timestamp__lt=timezone.now())
                                    elif signal == "velocity":
                                        signalStatData = models.VelocityStatTimeMaster.objects.filter(composite=compositeKey.composite_id, axis=axis, timestamp__gte=yesterday, timestamp__lt=timezone.now())
                                    # elif getattr(singleThres, "signal_type") == "temp":
                                    #     signalStatData = models.TemperatureMaster.objects.filter(composite=compositeKey.composite_id, axis='temp', timestamp__gte=yesterday, timestamp__lt=timezone.now())
                                    #     print("data against single composite", len(signalStatData))
                                    else:
                                        signalStatData = []
                                    if len(signalStatData) > 0:
                                        row = existingThreshold.filter(axis=axis, signal_type=signal)[0]
                                        # pdb.set_trace()
                                        rms_level_1 = float(row.rms_amp_level_1)
                                        rms_level_2 = float(row.rms_amp_level_2)
                                        rms_level_3 = float(row.rms_amp_level_3)
                                        if rms_level_1>0 and rms_level_2>0 and rms_level_3>0:
                                            rms_result1 = len(signalStatData.filter( Q(rms__gte=rms_level_1) & Q(rms__lt=rms_level_2)).values('rms'))
                                            rms_result2 = len(signalStatData.filter( Q(rms__gte=rms_level_2) & Q(rms__lt=rms_level_3)).values('rms'))
                                            rms_result3 = len(signalStatData.filter( Q(rms__gte=rms_level_3)).values('rms'))
                                            rms_result1_percentage = (rms_result1/len(signalStatData))
                                            rms_result2_percentage = (rms_result2/len(signalStatData))
                                            rms_result3_percentage = (rms_result3/len(signalStatData))
                                            rms_result0_percentage = 1 - rms_result1_percentage + rms_result2_percentage + rms_result3_percentage
                                            rScore = calculateScore(rms_level_3, rms_level_2, rms_level_1, rms_result3_percentage, rms_result2_percentage, rms_result1_percentage,rms_result0_percentage)
                                            scoreDict.update({axis+'-'+signal+'-rms': rScore})
                                            scoreList.append(rScore)


                                        peak_level_1 = float(row.peak_amp_level_1)
                                        peak_level_2 = float(row.peak_amp_level_2)
                                        peak_level_3 = float(row.peak_amp_level_3)
                                        if peak_level_1>0 and peak_level_2>0 and peak_level_3>0:
                                            peak_result1 = len(signalStatData.filter( Q(peak__gte=peak_level_1) & Q(peak__lt=peak_level_2)).values('peak'))
                                            peak_result2 = len(signalStatData.filter( Q(peak__gte=peak_level_2) & Q(peak__lt=peak_level_3)).values('peak'))
                                            peak_result3 = len(signalStatData.filter( Q(peak__gte=peak_level_3)).values('peak'))
                                            peak_result1_percentage = (peak_result1/len(signalStatData))
                                            peak_result2_percentage = (peak_result2/len(signalStatData))
                                            peak_result3_percentage = (peak_result3/len(signalStatData))
                                            peak_result0_percentage = 1- peak_result3_percentage + peak_result2_percentage + peak_result1_percentage
                                            pScore = calculateScore(peak_level_3, peak_level_2, peak_level_1, peak_result3_percentage, peak_result2_percentage, peak_result1_percentage,peak_result0_percentage)
                                            scoreDict.update({axis+'-'+signal+'-peak ': pScore})
                                            scoreList.append(pScore)

                                        peak_to_peak_level_1 = float(row.peak_to_peak_amp_level_1)
                                        peak_to_peak_level_2 = float(row.peak_to_peak_amp_level_2)
                                        peak_to_peak_level_3 = float(row.peak_to_peak_amp_level_3)
                                        if peak_to_peak_level_1>0 and peak_to_peak_level_2>0 and peak_to_peak_level_3>0:
                                            peak_to_peak_result1 = len(signalStatData.filter( Q(peak_to_peak__gte=peak_to_peak_level_1) & Q(peak_to_peak__lt=peak_to_peak_level_2)).values('peak_to_peak'))
                                            peak_to_peak_result2 = len(signalStatData.filter( Q(peak_to_peak__gte=peak_to_peak_level_2) & Q(peak_to_peak__lt=peak_to_peak_level_3)).values('peak_to_peak'))
                                            peak_to_peak_result3 = len(signalStatData.filter( Q(peak_to_peak__gte=peak_to_peak_level_3)).values('peak_to_peak'))
                                            peak_to_peak_result1_percentage = (peak_to_peak_result1/len(signalStatData))
                                            peak_to_peak_result2_percentage = (peak_to_peak_result2/len(signalStatData))
                                            peak_to_peak_result3_percentage = (peak_to_peak_result3/len(signalStatData))
                                            peak_to_peak_result0_percentage = 1 - peak_to_peak_result3_percentage + peak_to_peak_result2_percentage + peak_to_peak_result1_percentage
                                            p2pScore = calculateScore(peak_to_peak_level_3, peak_to_peak_level_2, peak_to_peak_level_1, peak_to_peak_result3_percentage, peak_to_peak_result2_percentage, peak_to_peak_result1_percentage,peak_to_peak_result0_percentage)
                                            scoreDict.update({axis+'-'+signal+'-peak2peak': p2pScore})
                                            scoreList.append(p2pScore)
                            
                            worse_4_kpi = sorted(scoreList)[:4]
                            worse_4_kpi_mean = round(np.mean(worse_4_kpi),2)
                            if math.isnan(worse_4_kpi_mean):
                                pass
                            else:
                                EndPointscoreList.append(worse_4_kpi_mean)
                        if len(EndPointscoreList)>0:
                            finalScore = sorted(EndPointscoreList)[0]
                            res = getAssetHealthFlag(finalScore)
                            if res.get("result") == True:
                                asset_status = res.get("flag")
                                try:
                                    existingAssetHealthData = models.AssetHealthMaster.objects.get(asset_id=singleAsset.get("asset_id"))
                                    existingAssetHealthData.status = asset_status
                                    existingAssetHealthData.score = finalScore
                                    existingAssetHealthData.save()
                                except:
                                    asset_health_data =  {"asset_id": singleAsset.get("asset_id"), "org_id": singleAsset.get("org_id"), "status": asset_status, "score": finalScore}
                                    healthSerializerData = serializers.AssetHealthMasterSerializer(data=asset_health_data)
                                    if healthSerializerData.is_valid():
                                        healthSerializerData.save()
                            print("heath stored for {0}".format(singleAsset))
                return Response({"status": "Health score saved."})

            except:
                print("something wrong in main loop")





# class CalculateAssetHealthScoreManually(APIView):

#     def post(self, request, *args, **kwargs):

#         df = JSONParser().parse(request)
#         if not df:
#                 return Response({'message':"Json Data not found."},status=status.HTTP_404_NOT_FOUND)
#         asset_id = df.get("asset_id")
#         org_id = df.get("org_id")

#         yesterday = timezone.now() - timedelta(days=200)
#         axisList = ["Axial", "Vertical", "Horizontal"]
#         signalTypeList = ['acceleration', 'velocity']

#         try:
#             EndPointscoreList = []
#             compositeList = models.DeviceMountMaster.objects.filter(asset_id=asset_id)
#             for compositeKey in compositeList:
#                 mount_id = "_" + compositeKey.composite_id.split("_")[-1]
#                 scoreDict = {}
#                 scoreList = []

#                 try:
#                     existingThreshold = models.ThresholdValues.objects.filter(composite__endswith=mount_id)
#                 except:
#                     existingThreshold = []
#                 if len(existingThreshold) > 0:
#                     for singleThres in existingThreshold:
#                         axis = getattr(singleThres, "axis")
#                         signal = getattr(singleThres, "signal_type")
#                         if signal == "acceleration":
#                             signalStatData = models.AccelerationStatTimeMaster.objects.filter(composite__endswith=mount_id, axis=axis, timestamp__gte=yesterday, timestamp__lt=timezone.now())
#                         elif signal == "velocity":
#                             signalStatData = models.VelocityStatTimeMaster.objects.filter(composite__endswith=mount_id, axis=axis, timestamp__gte=yesterday, timestamp__lt=timezone.now())
#                         # elif getattr(singleThres, "signal_type") == "temp":
#                         #     signalStatData = models.TemperatureMaster.objects.filter(composite=compositeKey.composite_id, axis='temp', timestamp__gte=yesterday, timestamp__lt=timezone.now())
#                         #     print("data against single composite", len(signalStatData))
#                         else:
#                             signalStatData = []
#                         if len(signalStatData) > 0:
#                             row = existingThreshold.filter(axis=axis, signal_type=signal)[0]
#                             # pdb.set_trace()
#                             rms_level_1 = float(row.rms_amp_level_1)
#                             rms_level_2 = float(row.rms_amp_level_2)
#                             rms_level_3 = float(row.rms_amp_level_3)
#                             if rms_level_1>0 and rms_level_2>0 and rms_level_3>0:
#                                 rms_result1 = len(signalStatData.filter( Q(rms__gte=rms_level_1) & Q(rms__lt=rms_level_2)).values('rms'))
#                                 rms_result2 = len(signalStatData.filter( Q(rms__gte=rms_level_2) & Q(rms__lt=rms_level_3)).values('rms'))
#                                 rms_result3 = len(signalStatData.filter( Q(rms__gte=rms_level_3)).values('rms'))
#                                 rms_result1_percentage = (rms_result1/len(signalStatData))
#                                 rms_result2_percentage = (rms_result2/len(signalStatData))
#                                 rms_result3_percentage = (rms_result3/len(signalStatData))
#                                 rms_result0_percentage = 1 - rms_result1_percentage + rms_result2_percentage + rms_result3_percentage
#                                 rScore = calculateScore(rms_level_3, rms_level_2, rms_level_1, rms_result3_percentage, rms_result2_percentage, rms_result1_percentage,rms_result0_percentage)
#                                 scoreDict.update({axis+'-'+signal+'-rms': rScore})
#                                 scoreList.append(rScore)


#                             peak_level_1 = float(row.peak_amp_level_1)
#                             peak_level_2 = float(row.peak_amp_level_2)
#                             peak_level_3 = float(row.peak_amp_level_3)
#                             if peak_level_1>0 and peak_level_2>0 and peak_level_3>0:
#                                 peak_result1 = len(signalStatData.filter( Q(peak__gte=peak_level_1) & Q(peak__lt=peak_level_2)).values('peak'))
#                                 peak_result2 = len(signalStatData.filter( Q(peak__gte=peak_level_2) & Q(peak__lt=peak_level_3)).values('peak'))
#                                 peak_result3 = len(signalStatData.filter( Q(peak__gte=peak_level_3)).values('peak'))
#                                 peak_result1_percentage = (peak_result1/len(signalStatData))
#                                 peak_result2_percentage = (peak_result2/len(signalStatData))
#                                 peak_result3_percentage = (peak_result3/len(signalStatData))
#                                 peak_result0_percentage = 1- peak_result3_percentage + peak_result2_percentage + peak_result1_percentage
#                                 pScore = calculateScore(peak_level_3, peak_level_2, peak_level_1, peak_result3_percentage, peak_result2_percentage, peak_result1_percentage,peak_result0_percentage)
#                                 scoreDict.update({axis+'-'+signal+'-peak ': pScore})
#                                 scoreList.append(pScore)

#                             peak_to_peak_level_1 = float(row.peak_to_peak_amp_level_1)
#                             peak_to_peak_level_2 = float(row.peak_to_peak_amp_level_2)
#                             peak_to_peak_level_3 = float(row.peak_to_peak_amp_level_3)
#                             if peak_to_peak_level_1>0 and peak_to_peak_level_2>0 and peak_to_peak_level_3>0:
#                                 peak_to_peak_result1 = len(signalStatData.filter( Q(peak_to_peak__gte=peak_to_peak_level_1) & Q(peak_to_peak__lt=peak_to_peak_level_2)).values('peak_to_peak'))
#                                 peak_to_peak_result2 = len(signalStatData.filter( Q(peak_to_peak__gte=peak_to_peak_level_2) & Q(peak_to_peak__lt=peak_to_peak_level_3)).values('peak_to_peak'))
#                                 peak_to_peak_result3 = len(signalStatData.filter( Q(peak_to_peak__gte=peak_to_peak_level_3)).values('peak_to_peak'))
#                                 peak_to_peak_result1_percentage = (peak_to_peak_result1/len(signalStatData))
#                                 peak_to_peak_result2_percentage = (peak_to_peak_result2/len(signalStatData))
#                                 peak_to_peak_result3_percentage = (peak_to_peak_result3/len(signalStatData))
#                                 peak_to_peak_result0_percentage = 1 - peak_to_peak_result3_percentage + peak_to_peak_result2_percentage + peak_to_peak_result1_percentage
#                                 p2pScore = calculateScore(peak_to_peak_level_3, peak_to_peak_level_2, peak_to_peak_level_1, peak_to_peak_result3_percentage, peak_to_peak_result2_percentage, peak_to_peak_result1_percentage,peak_to_peak_result0_percentage)
#                                 scoreDict.update({axis+'-'+signal+'-peak2peak': p2pScore})
#                                 scoreList.append(p2pScore)
                
#                 worse_4_kpi = sorted(scoreList)[:4]
#                 worse_4_kpi_mean = round(np.mean(worse_4_kpi),2)
#                 if math.isnan(worse_4_kpi_mean):
#                     pass
#                 else:
#                     EndPointscoreList.append(worse_4_kpi_mean)
#             if len(EndPointscoreList)>0:
#                 finalScore = sorted(EndPointscoreList)[0]
#                 res = getAssetHealthFlag(finalScore)
#                 if res.get("result") == True:
#                     asset_status = res.get("flag")
#                     try:
#                         existingAssetHealthData = models.AssetHealthMaster.objects.get(asset_id=asset_id)
#                         existingAssetHealthData.status = asset_status
#                         existingAssetHealthData.score = finalScore
#                         existingAssetHealthData.save()
#                     except:
#                         asset_health_data =  {"asset_id": asset_id, "org_id": org_id, "status": asset_status, "score": finalScore}
#                         healthSerializerData = serializers.AssetHealthMasterSerializer(data=asset_health_data)
#                         if healthSerializerData.is_valid():
#                             healthSerializerData.save()
#                     return Response({"status": "Health score saved."})
#                 else:
#                     return Response({"status": "Error with get asset health flag."})
#             else:
#                 return Response({"status": "All check, no kpi found against selected asset"}, status=status.HTTP_204_NO_CONTENT)


#         except:
#             print("something wrong in main loop")


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
        thres = np.mean(moving_avg)*1.5
        dataDict = {"result": True, "response": float(round(thres, 2))}
        return dataDict

    elif feature_2 < 0.11:
        thres = (dataMean+dataStd)*1.5
        dataDict = {"result": True, "response": float(round(thres, 2))}
        return dataDict
    
    else:
        if previous_thres:
            thres = previous_thres
            dataDict = {"result": True, "response": float(round(thres, 2))}
            return dataDict
        else:
            thres = np.mean(moving_avg)*1.5
            dataDict = {"result": True, "response": float(round(thres, 2))}
            return dataDict
            


# class CalculateThresholdForDiagnostics(APIView):
def CalculateThresholdForDiagnostics():

    axisList = ["Axial", "Vertical", "Horizontal"]
    functionList = ["one_amp", "two_amp", "three_amp", "four_amp", "five_amp", "six_amp", "seven_amp", "eight_amp", "nine_amp", "ten_amp", "four_to_seven_amp"]
    # pdb.set_trace()
    unique_composites = models.DiagnosticsValuesMaster.objects.values('composite').distinct()

    # Now, retrieve all rows against unique composite values
    if len(unique_composites) > 0:
    
        for composite in unique_composites:
            composite_key = composite['composite']
            rows_for_composite = models.DiagnosticsValuesMaster.objects.filter(composite=composite_key).order_by("-timestamp")
            for single_axis in axisList:

                # check if existing threshold value exists  in database
                try:
                    existingThreshold = models.DiagnosticsDynamicThresholdValuesMaster.objects.get(composite=composite_key, axis=single_axis)
                except:
                    existingThreshold = None

                # if no existing threshold exists, calculate new value of threshold and save for the first time
                if existingThreshold == None:

                    diagnostic_dynamic_object = {"composite": composite_key, "axis": single_axis, "signal_type": 'velocity' }
                    counter_values = {"composite": composite_key, 'axis': single_axis, 'signal_type': 'velocity'}
                    
                    for function in functionList:
                        single_func_data = rows_for_composite.filter(axis=single_axis).values(function, "timestamp", "asset_id")

                        diagnostic_dynamic_object.update({"asset_id": single_func_data[0].get("asset_id")})
                        counter_values.update({'asset_id': single_func_data[0].get("asset_id")})
                        if len(single_func_data) >= 30:   # number of data points to calculate dynamic threshold against
                            
                            ampList = [i.get(function) for i in single_func_data.reverse()]
                            res = CalculateDynamicThreshold(ampList, None)
                            # print("result of ", function , "with composite id", composite_key, " in axis ",single_axis,  " is ", res)
                            if res.get("result") == True and res.get("response")>0:
                                level_one = round(res.get("response"), 3)
                                level_two = round(res.get("response") * 1.5 , 3)
                                level_three = round(res.get("response") * 1.75 , 3)

                                diagnostic_dynamic_object.update({
                                    function+"_level_1": level_one,
                                    function+"_level_2": level_two,
                                    function+"_level_3": level_three
                                    })
                                
                                counter_values.update({
                                    function+"_repetition_level_1" : 5,
                                    function+"_repetition_level_2" : 5,
                                    function+"_repetition_level_3" : 5,
                                    })

                    diagnostic_dynamic_object_serializer = serializers.DiagnosticsDynamicThresholdValuesMasterSerializer(data=diagnostic_dynamic_object)
                    countSer = serializers.DiagnosticThresholdCounterMasterSerializer(data=counter_values)
                    
                    if diagnostic_dynamic_object_serializer.is_valid():
                        if countSer.is_valid():
                            diagnostic_dynamic_object_serializer.save()
                            countSer.save()

                else:
                    # print("here in loop when threshold found for a composite + axis combination")
                    # checking and saving threshold only for function which are 0 i.e not exiting threshold not for existing parameters
                    # diagnostic_dynamic_object = {"composite": composite_key, "axis": single_axis, "signal_type": 'velocity' }
                    for function in functionList:
                        if getattr(existingThreshold, function+"_level_1") == 0:
                            single_func_data = rows_for_composite.filter(axis=single_axis).values(function, "timestamp", "asset_id")
                            if len(single_func_data) >= 30:   # number of data points to calculate dynamic threshold against
                                ampList = [i.get(function) for i in single_func_data.reverse()]
                                res = CalculateDynamicThreshold(ampList, None)
                                # print("result of ", function , "with composite id", composite_key, " in axis ",single_axis,  " is ", res)
                                if res.get("result") == True and res.get("response")>0:
                                    level_one = round(res.get("response"), 3)
                                    level_two = round(res.get("response") * 1.5 , 3)
                                    level_three = round(res.get("response") * 1.75 , 3)

                                    setattr(existingThreshold, function+"_level_1", level_one)
                                    setattr(existingThreshold, function+"_level_2", level_two)
                                    setattr(existingThreshold, function+"_level_3", level_three)
                    existingThreshold.save()




                    # diagnosticSingleData = models.DiagnosticsValuesMaster.objects.get(id=single_row.id)
                    # updateData = {'flag': True}
                    # diagnosticSingleDataSerializer = serializers.AccelerationStatTimeMasterSerializer(instance=diagnosticSingleData, data=updateData, partial=True)
    else:
        return True

# def get_minutes_difference(timestamp1, timestamp2):
#   """
#   This function calculates the difference between two ISO 8601 timestamps in minutes.

#   Args:
#       timestamp1 (str): The first timestamp in ISO 8601 format.
#       timestamp2 (str): The second timestamp in ISO 8601 format.

#   Returns:
#       float: The difference between the timestamps in minutes.
#   """
#   # Convert timestamps to datetime objects
#   dt1 = datetime.strptime(str(timestamp1), "%Y-%m-%d %H:%M:%S.%f%z")
#   dt2 = datetime.strptime(str(timestamp2), "%Y-%m-%d %H:%M:%S.%f%z")

#   # Calculate the difference in seconds
#   time_delta = dt1 - dt2
#   total_seconds = time_delta.total_seconds()

#   # Convert the difference to minutes and return
#   return total_seconds / 60

def get_minutes_difference(timestamp1, timestamp2):
    """
    This function calculates the difference between two ISO 8601 timestamps in minutes.

    Args:
        timestamp1 (str): The first timestamp in ISO 8601 format.
        timestamp2 (str): The second timestamp in ISO 8601 format.

    Returns:
        float: The difference between the timestamps in minutes.
    """
    # Convert timestamps to datetime objects
    if isinstance(timestamp1, datetime):
        dt1 = timestamp1 if timestamp1.tzinfo else pytz.utc.localize(timestamp1)
    else:
        for fmt in ("%Y-%m-%d %H:%M:%S.%f%z", "%Y-%m-%d %H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
            try:
                dt1 = datetime.strptime(str(timestamp1), fmt)
                break
            except ValueError:
                continue

    if isinstance(timestamp2, datetime):
        dt2 = timestamp2 if timestamp2.tzinfo else pytz.utc.localize(timestamp2)
    else:
        for fmt in ("%Y-%m-%d %H:%M:%S.%f%z", "%Y-%m-%d %H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
            try:
                dt2 = datetime.strptime(str(timestamp2), fmt)
                break
            except ValueError:
                continue

    # Calculate the difference in seconds
    time_delta = dt1 - dt2
    total_seconds = time_delta.total_seconds()

    # Convert the difference to minutes and return
    return total_seconds / 60


# @api_view(['GET'])
# def checkSensorLiveStatus(request):
#     if request.method == 'GET':
# def checkSensorLiveStatus():
#         try:
#             activeSensors = models.DeviceMountMaster.objects.filter(is_linked=True).values_list('composite_id', flat=True)
#             if len(activeSensors) > 0:
#                 activeSensorSleepTime = models.FirmwareMaster.objects.filter(composite_id__in=activeSensors).values('composite_id', 'sleep_time')
#                 firmwareComposite = activeSensorSleepTime.values_list('composite_id', flat=True)

#                 if len(firmwareComposite) > 0:
#                     sensorLiveStatusData = models.SensorLiveStatus.objects.filter(composite_id__in=firmwareComposite)
#                     for singelSensor in sensorLiveStatusData:
#                         try:
#                             timeNow = datetime.now(pytz.utc)
#                             lastUpdatedTime = singelSensor.last_update
#                             sleepTimeObject = activeSensorSleepTime.filter(composite_id=singelSensor.composite_id).order_by('-last_update')[0]
#                             sleepTime = sleepTimeObject.get('sleep_time')
#                             total_minutes = get_minutes_difference(timeNow, lastUpdatedTime)
#                             if sleepTime != None:
#                                 if total_minutes > float(sleepTime)*2.25:
#                                     existingNotification, created = models.SensorStatusNotifications.objects.annotate(truncated_date=Trunc('creation_date', 'day', output_field=DateTimeField())
#                                                                         ).get_or_create(truncated_date__date=date.today(), composite_id = singelSensor.composite_id,\
#                                                                                         defaults= {\
#                                                                                                 "mount": models.DeviceMountMaster.objects.get(id=singelSensor.composite_id.split("_")[-1]),\
#                                                                                                 "composite_id": singelSensor.composite_id,\
#                                                                                                 "asset_id": singelSensor.asset_id})
                                    
#                                     if not created:
#                                         existingNotification.online = False
#                                         existingNotification.read = False
#                                         existingNotification.save()
#                                 else:
#                                     existingNotification, created = models.SensorStatusNotifications.objects.annotate(truncated_date=Trunc('creation_date', 'day', output_field=DateTimeField())
#                                                                             ).get_or_create(truncated_date__date=date.today(), composite_id = singelSensor.composite_id,\
#                                                                                             defaults= {\
#                                                                                                 "mount": models.DeviceMountMaster.objects.get(id=singelSensor.composite_id.split("_")[-1]),\
#                                                                                                 "composite_id": singelSensor.composite_id,\
#                                                                                                 "asset_id": singelSensor.asset_id,\
#                                                                                                 "online": True,\
#                                                                                                 "read": False})
                                    
#                                     if not created:
#                                         existingNotification.online = True
#                                         existingNotification.read = False
#                                         existingNotification.save()
                        
#                         except Exception as e:
#                             print("Error occured in except: ", e)
#                             pass
#         except:
#             pass
#         return Response({"message": "All done"}, status=status.HTTP_200_OK)


# def checkSensorLiveStatus():
#         try:
#             # redis_client = redis.StrictRedis(host='localhost', port=6379, db=6)     # for testing server
#             redis_client = redis.StrictRedis(host='localhost', port=6379, db=2)     # for live server

#             # Fetch all keys from Redis
#             keys = redis_client.keys('*')  # Adjust the pattern if needed to fetch specific keys
#             compositeList = []
#             objects = []
#             for key in keys:
#                 try:
#                     data = redis_client.get(key)
#                         # If data is JSON, parse it
#                     if isinstance(data, bytes):  # Redis returns bytes, so decode it
#                         data = data.decode('utf-8')
#                     try:
#                         data_dict = json.loads(data)  # Parse JSON data
#                     except json.JSONDecodeError:
#                         print(f"Skipping invalid JSON data for key: {key}")
#                         continue
#                     compositeList.append(data_dict.get("composite_id"))

#                     # print("----------------data_dict---------------", data_dict)
#                 except Exception as e2:
#                     print("some exception e2 {e2}".format(e2))

#             sensorLiveStatusData = models.SensorLiveStatus.objects.filter(composite_id__in=compositeList)

#             # PRE-FETCH ALL MOUNTS
#             mount_ids = []
#             for sensor in sensorLiveStatusData:
#                 try:
#                     mount_id = sensor.composite_id.split("_")[-1]
#                     mount_ids.append(mount_id)
#                 except (IndexError, AttributeError):
#                     print(f"Invalid composite_id format: {sensor.composite_id}")
            
#             # Single query to fetch all required mounts
#             mounts_queryset = models.DeviceMountMaster.objects.filter(id__in=mount_ids)
#             mounts_dict = {str(mount.id): mount for mount in mounts_queryset}

#             for singelSensor in sensorLiveStatusData:
#                 timeNow = datetime.now(pytz.utc)
#                 lastUpdatedTime = singelSensor.last_update
#                 total_minutes = get_minutes_difference(timeNow, lastUpdatedTime)

#                 # GET MOUNT FROM PRE-FETCHED DICTIONARY
#                 mount_id = singelSensor.composite_id.split("_")[-1]
#                 mount_object = mounts_dict.get(mount_id)
                
#                 if not mount_object:
#                     print(f"Mount not found for composite_id: {singelSensor.composite_id}")
#                     continue

#                 if total_minutes > 1440:    
#                     existingNotification, created = models.SensorStatusNotifications.objects.annotate(truncated_date=Trunc('creation_date', 'day', output_field=DateTimeField())
#                                                         ).get_or_create(truncated_date__date=date.today(), composite_id = singelSensor.composite_id,\
#                                                                         defaults= {\
#                                                                                 "mount": mount_object,\
#                                                                                 "composite_id": singelSensor.composite_id,\
#                                                                                 "asset_id": singelSensor.asset_id})
                    
#                     if not created:
#                         existingNotification.online = False
#                         existingNotification.read = False
#                         existingNotification.save()
#                 else:
#                     existingNotification, created = models.SensorStatusNotifications.objects.annotate(truncated_date=Trunc('creation_date', 'day', output_field=DateTimeField())
#                                                             ).get_or_create(truncated_date__date=date.today(), composite_id = singelSensor.composite_id,\
#                                                                             defaults= {\
#                                                                                 "mount": mount_object,\
#                                                                                 "composite_id": singelSensor.composite_id,\
#                                                                                 "asset_id": singelSensor.asset_id,\
#                                                                                 "online": True,\
#                                                                                 "read": False})
                    
#                     if not created:
#                         existingNotification.online = True
#                         existingNotification.read = False
#                         existingNotification.save()

#         except Exception as e1:
#             return Response({"message": "Some error in checkSensorLiveStatus {0}".format(e1)})


#         return {"message": "Okay", "status": "success"}

def checkSensorLiveStatus():
    try:
        print(f"checkSensorLiveStatus started at {datetime.now(pytz.utc)}")
        redis_client = redis.StrictRedis(host='localhost', port=6379, db=2)     # for live server

        # Fetch composite_* keys and extract composite_id from key name
        keys = redis_client.keys('composite_*')
        compositeList = []

        for key in keys:
            try:
                key_str = key.decode('utf-8') if isinstance(key, bytes) else str(key)
                composite_id = key_str.replace('composite_', '', 1)
                if composite_id not in compositeList:
                    compositeList.append(composite_id)
            except Exception as e2:
                print("some exception e2 {e2}".format(e2=e2))

        # Fallback to DB if Redis returned nothing
        if not compositeList:
            print("No composite IDs found in Redis, fetching from database")
            all_sensors = models.DeviceMountMaster.objects.exclude(
                composite_id__isnull=True
            ).exclude(composite_id__exact='')
            for sensor in all_sensors:
                compositeList.append(sensor.composite_id)

            if not compositeList:
                print("No sensors found in database either")
                return {"message": "No data to process", "status": "success"}

        sensorLiveStatusData = models.SensorLiveStatus.objects.filter(
            composite_id__in=compositeList
        )

        # PRE-FETCH ALL MOUNTS - with validation
        mount_ids = []
        valid_sensors = []

        for sensor in sensorLiveStatusData:
            try:
                parts = sensor.composite_id.split("_")
                if len(parts) >= 4:
                    mount_id_str = parts[-1]
                    if mount_id_str.isdigit():
                        mount_ids.append(int(mount_id_str))
                        valid_sensors.append(sensor)
                    else:
                        print(f"Invalid mount_id format in composite_id: {sensor.composite_id}")
                else:
                    print(f"Unexpected composite_id format: {sensor.composite_id}")
            except (IndexError, AttributeError):
                print(f"Invalid composite_id format: {sensor.composite_id}")

        if not mount_ids:
            print("No valid mount IDs found")
            return {"message": "No valid mount IDs", "status": "success"}

        # Single query to fetch all required mounts
        mounts_queryset = models.DeviceMountMaster.objects.filter(id__in=mount_ids)
        mounts_dict = {str(mount.id): mount for mount in mounts_queryset}

        # Pre-fetch today's existing notifications into dict
        timeNow = datetime.now(pytz.utc)
        today_date = date.today()

        existing_notifications = models.SensorStatusNotifications.objects.annotate(
            truncated_date=Trunc('creation_date', 'day', output_field=DateTimeField())
        ).filter(
            truncated_date__date=today_date,
            composite_id__in=[sensor.composite_id for sensor in valid_sensors]
        )
        existing_notifications_dict = {
            notif.composite_id: notif for notif in existing_notifications
        }

        notifications_to_create = []
        notifications_to_update = []

        for singelSensor in valid_sensors:
            try:
                lastUpdatedTime = singelSensor.last_update
                total_minutes = get_minutes_difference(timeNow, lastUpdatedTime)

                mount_id = singelSensor.composite_id.split("_")[-1]
                mount_object = mounts_dict.get(mount_id)

                if not mount_object:
                    print(f"Mount not found for composite_id: {singelSensor.composite_id}")
                    continue

                is_online = total_minutes <= 1440   # 1 day window, temporary changes

                existingNotification = existing_notifications_dict.get(singelSensor.composite_id)

                if existingNotification:
                    if existingNotification.online != is_online:
                        existingNotification.online = is_online
                        existingNotification.read = False
                        notifications_to_update.append(existingNotification)
                else:
                    notifications_to_create.append(
                        models.SensorStatusNotifications(
                            mount=mount_object,
                            composite_id=singelSensor.composite_id,
                            asset_id=singelSensor.asset_id,
                            online=is_online,
                            read=False
                        )
                    )

            except Exception as e2:
                print("some exception e2 {e2}".format(e2=e2))
                continue

        # Batch DB operations
        with transaction.atomic():
            if notifications_to_create:
                models.SensorStatusNotifications.objects.bulk_create(
                    notifications_to_create,
                    batch_size=100,
                    ignore_conflicts=True
                )
                print(f"Created {len(notifications_to_create)} new notifications")

            if notifications_to_update:
                models.SensorStatusNotifications.objects.bulk_update(
                    notifications_to_update,
                    ['online', 'read'],
                    batch_size=100
                )
                print(f"Updated {len(notifications_to_update)} notifications")

    except Exception as e1:
        return Response({"message": "Some error in checkSensorLiveStatus {0}".format(e1)})

    return {"message": "Okay", "status": "success"}



def convert_seconds(seconds):
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{int(hours):02}:{int(minutes):02}"

def getRunningHours(df):
    sensor_type = df.get("sensor_type")
    operating_value = df.get("operating_value")
    without_load_value = df.get('without_load_value')
    stop_value = df.get('stop_value')
    total_count = df.get('total_count')


    if sensor_type == "w":
        expected_data_sec = 86400
        expected_data_no  = 12336
        
        total_data_collected_sec = round((expected_data_sec/expected_data_no)*total_count)
        total_data_collected = convert_seconds(total_data_collected_sec)
        
        operating_value = round((expected_data_sec/expected_data_no)*operating_value)
        running_condition = convert_seconds(operating_value)
        
        without_load_value = round((expected_data_sec/expected_data_no)*without_load_value)
        ideal_condition = convert_seconds(without_load_value)

        stop_value = round((expected_data_sec/expected_data_no)*stop_value)
        stop_condition = convert_seconds(stop_value)
        
        data_not_collected = expected_data_no - total_count
        power_down_sec = round((expected_data_sec/expected_data_no)*data_not_collected)
        power_down = convert_seconds(power_down_sec)
        
        data = {
            "total_data_collected": total_data_collected,
            "running_condition": running_condition,
            "ideal_condition": ideal_condition,
            "stop_condition": stop_condition,
            "power_down": power_down
        }
    
    return data


def time_to_timedelta(time_str): 
    h, m = map(int, time_str.split(':')) 
    return timedelta(hours=h, minutes=m)


@api_view(['GET'])
def CalculateAssetUtilityScore(request):
    if request.method == 'GET':
        # def CalculateAssetUtilityScore():
        
        today = timezone.now()
        yesterday = timezone.now() - timedelta(days=1)

        composite_list = []
        try:
            assetList = models.DeviceMountMaster.objects.filter(is_linked=True)
            composite_list = [i.composite_id for i in assetList]
            id_list = list({i.id for i in assetList})

            # pdb.set_trace()
            filter_condition = Q()
            for suffix in id_list:
                filter_condition |= Q(composite__endswith=suffix)
            vibrationData = models.AssetRunningVibrationValue.objects.filter(filter_condition)
            if vibrationData:
                filtered_data = []
                for item in vibrationData:
                    # print("---------------------------", item)
                    composite = item.composite
                    # value = item.value
                    stop_value = item.stop_value
                    without_load_value = item.without_load_value
                    operating_value = item.operating_value
                    sensor_type, mac_id, asset_id, mount_id = item.composite.split('_')
                    count_data = models.VelocityStatTimeMaster.objects.filter(composite__endswith=mount_id, axis="Vertical", timestamp__gte=yesterday, timestamp__lt=today).aggregate(
                        operating_value=Count('id', filter=Q(rms__gt=without_load_value)),
                        without_load_value=Count('id', filter=Q(rms__gt=stop_value) & Q(rms__lte=without_load_value)),
                        stop_value=Count('id', filter=Q(rms__lte=stop_value))
                    )
                    data_obj = {
                        'sensor_type': sensor_type,
                        'asset_id': asset_id,
                        'mount_id': mount_id,
                        'operating_value': count_data['operating_value'],
                        'without_load_value': count_data['without_load_value'],
                        'stop_value': count_data['stop_value'],
                        'total_count': count_data['operating_value']+ count_data['without_load_value']+ count_data['stop_value']
                    }
                    utility_data = getRunningHours(data_obj)
                    filtered_data.append({"composite": item.composite, "data": utility_data, "asset_id": item.asset_id})
                    

                

                # Dictionary to store the unique asset_id with the highest total_data_collected 
                unique_data = {} 
                for item in filtered_data: 
                    asset_id = item['asset_id'] 
                    total_data_collected = time_to_timedelta(item['data']['total_data_collected']) 

                    if asset_id not in unique_data:
                        unique_data[asset_id] = item 
                    else: 
                        existing_total_data = time_to_timedelta(unique_data[asset_id]['data']['total_data_collected'])
                        if total_data_collected > existing_total_data:
                            unique_data[asset_id] = item 
                # Get the list of unique items
                unique_items = list(unique_data.values())

                # Create instances of MyModel from data_list
                my_model_instances = [models.AssetUtilityMaster(composite=item.get("composite"), data=item.get("data"), asset_id=item.get("asset_id")) for item in unique_items]
                
                # Use bulk_create to insert all instances in a single query
                models.AssetUtilityMaster.objects.bulk_create(my_model_instances)

            return Response({"message": "Done"}, status=status.HTTP_200_OK)
        except Exception as e:
            print("some exception", e)
            return Response({"message":"Something went wrong{0}".format(e)}, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
def DumpCounterDataToDatabase(request):
    if request.method == 'GET':
        # redis_client = redis.StrictRedis(host='localhost', port=6379, db=9)         # for testing server only
        redis_client = redis.StrictRedis(host='localhost', port=6379, db=5)         # for live server only

        # Fetch all keys from Redis
        keys = redis_client.keys('*')  # Adjust the pattern if needed to fetch specific keys

        objects = []
        for key in keys:
            try:
                data = redis_client.get(key)
                
                # If data is JSON, parse it
                if isinstance(data, bytes):  # Redis returns bytes, so decode it
                    data = data.decode('utf-8')
                try:
                    data_dict = json.loads(data)  # Parse JSON data
                except json.JSONDecodeError:
                    print(f"Skipping invalid JSON data for key: {key}")
                    continue
                # Check if a record with the same primary key exists
                primary_key = data_dict.get('id')  # Replace 'id' with your primary key field
                if primary_key is None:
                    print(f"Skipping record without primary key for key: {key}")
                    continue

                try:
                    obj = models.ThresholdCounterMaster.objects.get(id=primary_key)  # Replace 'id' with the name of your primary key field
                    # Update the existing record
                    for field, value in data_dict.items():
                        setattr(obj, field, value)  # Update fields dynamically
                    obj.save()  # Save changes
                except models.ThresholdCounterMaster.DoesNotExist:
                    # Create a new record if it doesn't exist
                    obj = models.ThresholdCounterMaster(**data_dict)
                    obj.save()
            except Exception as e:
                print("some exceptionnnnnnnnnnnnnnnnnnn", e)
        return Response({"message": "Okay"}, status=status.HTTP_200_OK)



def DumpCounterDataToDatabaseV2():

    # redis_client = redis.StrictRedis(host='localhost', port=6379, db=9)         # for testing server only
    redis_client = redis.StrictRedis(host='localhost', port=6379, db=5)         # for live server only

    # Fetch all keys from Redis
    keys = redis_client.keys('*')  # Adjust the pattern if needed to fetch specific keys

    objects = []
    for key in keys:
        try:
            data = redis_client.get(key)
            # print("-----------------------", data)
            # If data is JSON, parse it
            if isinstance(data, bytes):  # Redis returns bytes, so decode it
                data = data.decode('utf-8')
            try:
                data_dict = json.loads(data)  # Parse JSON data
            except json.JSONDecodeError:
                print(f"Skipping invalid JSON data for key: {key}")
                continue
            # Check if a record with the same primary key exists
            primary_key = data_dict.get('id')  # Replace 'id' with your primary key field
            if primary_key is None:
                print(f"Skipping record without primary key for key: {key}")
                continue

            try:
                obj = models.ThresholdCounterMaster.objects.get(id=primary_key)  # Replace 'id' with the name of your primary key field
                # Update the existing record
                for field, value in data_dict.items():
                    setattr(obj, field, value)  # Update fields dynamically
                obj.save()  # Save changes
            except models.ThresholdCounterMaster.DoesNotExist:
                # Create a new record if it doesn't exist
                obj = models.ThresholdCounterMaster(**data_dict)
                obj.save()
        except Exception as e:
            print("some exceptionnnnnnnnnnnnnnnnnnn", e)
    return Response({"message": "Okay"}, status=status.HTTP_200_OK)


# def updateCounterTable(data_dict):

#     primary_key = data_dict.get('id')
#     try:
#         obj = models.ThresholdCounterMaster.objects.get(id=primary_key)
#         # Update the existing record
#         for field, value in data_dict.items():
#             setattr(obj, field, value)  # Update fields dynamically
#         obj.save()  # Save changes
#     except models.ThresholdCounterMaster.DoesNotExist:
#         # Create a new record if it doesn't exist
#         obj = models.ThresholdCounterMaster(**data_dict)
#         obj.save()
#     return True




@api_view(['GET', 'POST'])
def calculateAutoDiagnostics(request):
    if request.method == 'GET':
        try:
            ################################### checking unbalance ###################################
            print("~~~~~~~~~~~~~~~~~~~~~")
            axisList = ['Axial', 'Vertical', 'Horizontal']
            allDevices = models.DeviceMountMaster.objects.filter(composite_id__isnull=False)
            # print("------------------------allDevices--------------------------", len(allDevices))
            allFaults = {}
            sensorOrientationData = models.SensorPositionMaster.objects.all().values()

            # Get the latest timestamp for each composite
            latest_timestamps = (
                models.VelocityHarmonicsMaster.objects
                .values('composite', 'asset_id')  # Group by composite
                .annotate(latest_timestamp=Max('timestamp'))  # Get the max timestamp for each composite
            )
            # print("------------------latest_timestamps-------------------", latest_timestamps)
            print("----------------------total combinations found----------------------", len(latest_timestamps))

            finalFaultList = []
            for single_device in latest_timestamps:
                # print("----------------------single_device-----------------------", single_device)
                fault_found = False
                faultDetected = {
                    "unbalance": False,
                    "angular_misalignment": False,
                    "prallel_misalignment": False,
                    'rotating_looseness ': False,
                    'structural_looseness': False,
                    'bpfo': False,
                    'bpfi': False,
                    'bsf': False,
                    'ftf': False
                }
                try:
                    # velocityHarmonics = models.VelocityHarmonicsMaster.objects.filter(composite=single_device.composite_id).latest("timestamp")
                    velocityHarmonicsData = models.VelocityHarmonicsMaster.objects.filter(composite=single_device.get('composite'), axis__in=axisList, timestamp=single_device.get('latest_timestamp')).values()
                    # print("######", velocityHarmonicsData)
                    velocityRMSData = models.VelocityStatTimeMaster.objects.filter(composite=single_device.get('composite'), axis__in=axisList, timestamp=single_device.get('latest_timestamp')).values()
                    accelerationBFFData = models.BearingFaultFrequenciesMaster.objects.filter(composite=single_device.get('composite'), axis__in=axisList, timestamp=single_device.get('latest_timestamp'), signal_type="Acceleration").values()

                    ########################################## checking unbalance ##########################################
                    try:
                        if len(velocityHarmonicsData) > 0 and len(velocityRMSData) > 0:
                            for row in velocityHarmonicsData:
                                selectedAxis = row.get("axis")
                                # print("----------------------------------", row.get("composite"), row.get("one_amp"))
                                if selectedAxis in axisList:
                                    axisRms = [i.get("rms") for i in velocityRMSData if i.get("axis")==selectedAxis]
                                    ########## a_1x here represents amplitude of 1x in all direction as per selectedAxis in present loop ##########
                                    a_1x = float(row.get("one_amp", 0))
                                    a_2x = float(row.get("two_amp", 0))
                                    a_3x = float(row.get("three_amp", 0))
                                    axis_rms = float(axisRms[0]) 
                                    if a_1x != 0 and a_2x != 0 and a_3x != 0 and axis_rms != 0:
                                        if a_1x > a_2x and a_1x > a_3x and a_1x > 0.8*axis_rms:
                                            fault_found = True
                                            faultDetected['unbalance'] = True
                                            # print("-------------------unbalance detected-------------", selectedAxis)
                                            # print("dasdsadasdasdasdasdad", faultDetected)
                                        

                    except Exception as e1:
                        print("Exception in unbalance", e1)

                    ########################################## checking misalignment ##########################################
                    try:
                        if len(velocityHarmonicsData) > 0:
                            axialHarmonicData = [i for i in velocityHarmonicsData if i.get("axis") == "Axial"]
                            horizontalHarmonicData = [i for i in velocityHarmonicsData if i.get("axis") == "Horizontal"]
                            verticalHarmonicData = [i for i in velocityHarmonicsData if i.get("axis") == "Vertical"]
                            
                            a_1x = float(axialHarmonicData[0].get("one_amp", 0))
                            a_2x = float(axialHarmonicData[0].get("two_amp", 0))

                            h_1x = float(horizontalHarmonicData[0].get("one_amp", 0))
                            h_2x = float(horizontalHarmonicData[0].get("two_amp", 0))
                            h_3x = float(horizontalHarmonicData[0].get("three_amp", 0))

                            v_1x = float(verticalHarmonicData[0].get("one_amp", 0))
                            v_2x = float(verticalHarmonicData[0].get("two_amp", 0))
                            v_3x = float(verticalHarmonicData[0].get("three_amp", 0))
                            
                            if a_1x !=0 and a_2x !=0 and h_1x !=0 and h_2x !=0 and h_3x !=0 and v_1x !=0 and v_2x !=0 and v_3x !=0:
                                if ( (a_1x >= h_1x) and (a_1x >= v_1x) and (a_2x >= h_2x) and (a_2x >= v_2x) ):
                                    fault_found = True
                                    faultDetected['angular_misalignment'] = True
                                    # print("-------------------Label Angular Misalignment-------------------")
                                if ( ( (h_2x / h_1x) > 1) and ( (v_2x / v_1x) > 1) ) or ( ( (h_3x / h_1x) > 1) and ( (v_3x / v_1x) > 1) ):
                                    fault_found = True
                                    faultDetected['prallel_misalignment'] = True
                                    # print("-------------------Label Parallel Misalignment-------------------")


                    except Exception as e2:
                        print("Exception in misalignment", e2)

                    ########################################## checking looseness ##########################################
                    try:
                        if len(velocityHarmonicsData) > 0 and len(velocityRMSData) > 0:
                            verticalRMS = [i.get("rms") for i in velocityRMSData if i.get("axis")=='Vertical']
                            for row in velocityHarmonicsData:
                                selectedAxis = row.get("axis")
                                if selectedAxis in axisList:
                                    ########## a_1x here represents amplitude of 1x in all direction as per selectedAxis in present loop ##########
                                    a_1x = float(row.get("one_amp", 0))
                                    a_15x = float(row.get("one_half_amp", 0))
                                    a_25x = float(row.get("two_half_amp", 0))
                                    a_4x = float(row.get("four_amp", 0))
                                    a_5x = float(row.get("five_amp", 0))
                                    vertical_rms = float(verticalRMS[0]) 
                                    if a_1x != 0 and a_15x != 0 and a_25x != 0 and a_4x != 0 and a_5x != 0 and vertical_rms != 0:
                                        if a_1x > 0.8*vertical_rms and a_15x > 0.5 and a_25x > 0.5:
                                            fault_found = True
                                            faultDetected['rotating_looseness'] = True
                                            # print("-------------------Rotating looseness detected-------------", selectedAxis)
                                        if a_4x > 0.5 and a_5x > 0.5:
                                            fault_found = True
                                            faultDetected['structural_looseness'] = True
                                            # print("-------------------Structural looseness detected-------------", selectedAxis)
                                        

                    except Exception as e3:
                        print("Exception in Looseness", e3)

                    ########################################## checking bearing faults ##########################################
                    # try:
                    #     # print("---------------------------------aaaaaaaaaaaaaaaaaaaaaaaaaa-----------------------------", accelerationBFFData)
                    #     bffList = ['bpfo', 'bpfi', 'bsf', 'ftf']
                    #     for bff in bffList:
                    #         counter = 0
                    #         for i in accelerationBFFData:
                    #             # print("iiiiiiiiiiiiiii",bff,  i.get(bff+'_amp'))
                    #             a = [j for j in i.get(bff+'_amp') if j > 0.002]
                    #             counter += len(a)
                    #             # print("------------------aaaaaaaaaaaaaaaaaa-----------------", bff, a)
                    #         # print("final counterrrrrrrrrrrrr",bff, counter)
                    #         if counter >= 3:
                    #             fault_found = True
                    #             faultDetected[bff] = True
                    #             # print("-------------------fault detected in bff-------------------", bff, counter)
                    #             # print("------------------", bff)
                    #     pass

                    # except Exception as e4:
                    #     print("exception in bearing fault", e4)
                except Exception as e1:
                    print("exception in velocity harmonic", e1)

                if fault_found:
                    finalFaultList.append(models.RuleBaseDiagnosticsMaster(composite = single_device.get('composite'), asset_id = single_device.get('asset_id'), faults_detected = faultDetected))
                else:
                    pass
            print("-----------finalFaultList-----------", finalFaultList)
            if len(finalFaultList) > 0:
                finalFaultListModel = models.RuleBaseDiagnosticsMaster.objects.bulk_create(finalFaultList)
                print('-----------------', finalFaultListModel)
                return Response({"message": "all data saved"}, status=status.HTTP_200_OK)
        except Exception as e:
            print("some exception", e)
            return Response({"error": e}, status=status.HTTP_200_OK)


# @api_view(['GET'])
# def process_rms_batch(request):
def process_rms_batch():
    # if request.method == 'GET':
        print("---------------Starting process_rms_batch task-----------------")
        try:
            keys_to_process = list(redis_client_rms_batch.scan_iter('rms_batch:*'))

            if not keys_to_process:
                print("No RMS data in batch to process.")
                return {"result": True, "message": "No data in batch."}

            print(f"Gathering {len(keys_to_process)} records for bulk processing.")

            raw_data_batch = redis_client_rms_batch.mget(keys_to_process)
            sensor_data_batch = [json.loads(data) for data in raw_data_batch if data]

            if not sensor_data_batch:
                # print("No valid data found after gathering from Redis. Deleting keys to clear cache.")
                redis_client_rms_batch.delete(*keys_to_process)
                return {"result": True, "message": "No valid data to process."}

            # Separate BLE and Wired data
            ble_data_batch = []
            wired_data_batch = []
            
            for data in sensor_data_batch:
                if data.get('sensor_type') == 'ble':
                    ble_data_batch.append(data)
                else:
                    wired_data_batch.append(data)

            try:
                # print(f"Gathered {len(sensor_data_batch)} valid records from Redis.")
                # print(f"BLE records: {len(ble_data_batch)}, Wired records: {len(wired_data_batch)}")

                with connection.cursor() as cursor:
                    # Process BLE data if any
                    if ble_data_batch:
                        # print(f"Processing {len(ble_data_batch)} BLE records...")
                        cursor.execute("SELECT save_bulk_ble_sensor_data(%s::jsonb)", [json.dumps(ble_data_batch)])
                    
                    # Process Wired data if any
                    if wired_data_batch:
                        # print(f"Processing {len(wired_data_batch)} Wired records...")
                        cursor.execute("SELECT save_bulk_wired_sensor_data(%s::jsonb)", [json.dumps(wired_data_batch)])

                redis_client_rms_batch.delete(*keys_to_process)
                # print(f"Successfully processed and deleted {len(keys_to_process)} keys in a single batch transaction.")
                # return {
                #     "result": True, 
                #     "processed": len(keys_to_process),
                #     "ble_records": len(ble_data_batch),
                #     "wired_records": len(wired_data_batch)
                # }
                return True

            except Exception as e:
                print(f"DATABASE ERROR: Failed to process batch of {len(keys_to_process)} records. Error: {e}")
                return {"result": False, "error": str(e)}
        except Exception as e_main:
            print("exception in main loop", e_main)
        return Response({"message": "all okay"}, status=status.HTTP_200_OK)



# ---------------------------------------------------------------------------
# Asset diagnostics V4 (ported from data_processors, adapted for Abbott schema)
# ---------------------------------------------------------------------------

def _auto_float(value):
    try:
        if value is None:
            return None
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _auto_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _get_signal_processing(asset_id, mount_id):
    return (
        SignalProcessingMaster.objects
        .filter(mount_id=mount_id, asset_id=asset_id)
        .order_by("-last_update", "-creation_date")
        .first()
    )


def _v4_prefetch_signal_processing_map(mounts):
    wanted_keys = set()
    mount_ids = set()
    asset_ids = set()
    for mount in mounts or []:
        mount_id = str(mount.id)
        asset_id = str(mount.asset_id or "").strip()
        if not mount_id or not asset_id:
            continue
        wanted_keys.add((asset_id, mount_id))
        try:
            mount_ids.add(int(mount_id))
        except (TypeError, ValueError):
            mount_ids.add(mount_id)
        asset_ids.add(asset_id)

    if not wanted_keys or not mount_ids or not asset_ids:
        return {}

    signal_map = {}
    rows = (
        SignalProcessingMaster.objects
        .filter(mount_id__in=list(mount_ids), asset_id__in=list(asset_ids))
        .order_by("asset_id", "mount_id", "-last_update", "-creation_date")
    )
    for row in rows:
        key = (str(row.asset_id or "").strip(), str(row.mount_id or "").strip())
        if key in wanted_keys and key not in signal_map:
            signal_map[key] = row
    return signal_map


def _auto_resolve_diagnostic_asset_ids(asset_id):
    requested_asset_id = str(asset_id or "").strip()
    if not requested_asset_id:
        return []

    child_ids = []
    try:
        # Abbott does not ship the newer Mongo helper. Keep support optional so
        # installations that add it still get tree-wide diagnostics.
        from app.mongo.mongo_client import get_asset_ids_with_children
        child_ids = get_asset_ids_with_children([requested_asset_id]) or []
    except Exception:
        child_ids = []

    resolved_ids = [str(item).strip() for item in child_ids if str(item or "").strip()]
    if requested_asset_id not in resolved_ids:
        resolved_ids.insert(0, requested_asset_id)
    return list(dict.fromkeys(resolved_ids))

def _v4_positive_float(value):
    number = _auto_float(value)
    return number if number is not None and number > 0 else None


def _v4_first_positive(values):
    for value in list(values or []):
        number = _v4_positive_float(value)
        if number is not None:
            return number
    return None


def _v4_raw_qs_for_mount(asset_id, mount_id):
    composite_suffix = f"_{mount_id}"
    return RawDataMaster.objects.filter(
        asset_id=asset_id,
        composite__endswith=composite_suffix,
        axis__in=VIBRATION_AXES,
    )


def _v4_latest_raw_records(asset_id, mount_id, prefetched_map=None):
    if prefetched_map is not None:
        cached = prefetched_map.get((str(asset_id or "").strip(), str(mount_id or "").strip()))
        if cached is not None:
            return cached

    stat_rec = (
        AccelerationStatTimeOptimized.objects
        .filter(asset_id=asset_id, mount_id=mount_id, rms_only=False, rms_Vertical__gt=0.08)
        .order_by("-timestamp")
        .first()
    )
    if not stat_rec:
        return {}, None, None

    records = {}
    for axis in VIBRATION_AXES:
        rec = (
            _v4_raw_qs_for_mount(asset_id, mount_id)
            .filter(axis=axis, timestamp=stat_rec.timestamp)
            .order_by("-id")
            .first()
        )
        if rec:
            records[axis] = rec
    return records, stat_rec, None


def _v4_raw_timestamp_freshness_map(wanted_keys, asset_ids, mount_ids):
    latest_raw_ts_map = {}
    if not wanted_keys:
        return {}

    for asset_id, mount_id in wanted_keys:
        rec = _v4_raw_qs_for_mount(asset_id, mount_id).order_by("-timestamp").first()
        if rec:
            latest_raw_ts_map[(asset_id, mount_id)] = rec.timestamp

    freshest_ts = None
    freshest_unix = None
    for ts in latest_raw_ts_map.values():
        if ts is None:
            continue
        ts_unix = to_unix_timestamp(ts)
        if freshest_unix is None or ts_unix > freshest_unix:
            freshest_unix = ts_unix
            freshest_ts = ts

    freshness_map = {}
    for key in wanted_keys:
        latest_ts = latest_raw_ts_map.get(key)
        latest_unix = to_unix_timestamp(latest_ts) if latest_ts else None
        seconds_lag = (freshest_unix - latest_unix) if freshest_unix is not None and latest_unix is not None else None
        is_stale = latest_unix is None or (seconds_lag is not None and seconds_lag > 86400)
        freshness_map[key] = {
            "latest_raw_timestamp": latest_ts,
            "freshest_raw_timestamp": freshest_ts,
            "seconds_behind_freshest": seconds_lag,
            "is_stale": is_stale,
            "status": "stale_raw_data" if is_stale and latest_ts else "no_raw_data" if is_stale else "fresh",
        }
    return freshness_map


def _v4_prefetch_latest_raw_records_map(mounts):
    wanted_keys = set()
    mount_ids = set()
    asset_ids = set()
    for mount in mounts or []:
        mount_id = str(mount.id)
        asset_id = str(mount.asset_id or "").strip()
        if not mount_id or not asset_id:
            continue
        wanted_keys.add((asset_id, mount_id))
        asset_ids.add(asset_id)
        mount_ids.add(mount_id)

    if not wanted_keys:
        return {}

    freshness_map = _v4_raw_timestamp_freshness_map(wanted_keys, asset_ids, mount_ids)
    out = {}
    for asset_id, mount_id in wanted_keys:
        raw_selection_info = freshness_map.get((asset_id, mount_id))
        if raw_selection_info and raw_selection_info.get("is_stale"):
            out[(asset_id, mount_id)] = ({}, None, raw_selection_info)
            continue
        out[(asset_id, mount_id)] = _v4_latest_raw_records(asset_id, mount_id, prefetched_map=None)
    return out


def _v4_latest_bff_records(asset_id, mount_id):
    records = {}
    composite_suffix = f"_{mount_id}"
    for axis in VIBRATION_AXES:
        rec = (
            BearingFaultFrequenciesMaster.objects
            .filter(asset_id=asset_id, composite__endswith=composite_suffix, axis=axis, signal_type__iexact="Acceleration")
            .order_by("-timestamp")
            .first()
        )
        if rec is None:
            rec = (
                BearingFaultFrequenciesMaster.objects
                .filter(asset_id=asset_id, composite__endswith=composite_suffix, axis=axis)
                .order_by("-timestamp")
                .first()
            )
        if rec:
            records[axis] = rec
    return records


def _v4_latest_temperature(asset_id, mount_id, composite_id=None):
    rec = (
        models.TemperatureMaster.objects
        .filter(asset_id=asset_id, mount_id=mount_id)
        .order_by("-timestamp")
        .first()
    )
    if rec and rec.temp is not None:
        return _auto_float(rec.temp), rec.timestamp
    if composite_id:
        live = (
            models.SensorLiveStatus.objects
            .filter(composite_id=composite_id)
            .order_by("-last_update")
            .first()
        )
        if live and getattr(live, "latest_temp", None) is not None:
            return _auto_float(getattr(live, "latest_temp", None)), live.last_update
    return None, None


def _v4_bff_map_from_records(records):
    bff = {}
    sources = {}
    for family in ("bpfo", "bpfi", "bsf", "ftf"):
        for axis, rec in (records or {}).items():
            value = _v4_first_positive(getattr(rec, f"{family}_freq", None))
            if value is not None:
                bff[family.upper()] = value
                sources[family.upper()] = {
                    "axis": axis,
                    "record_id": rec.id,
                    "timestamp": rec.timestamp,
                }
                break
    return bff, sources


def _v4_waveform_from_raw_record(raw_rec, s3_payload_cache=None):
    debug = {
        "raw_record_id": raw_rec.id,
        "timestamp": raw_rec.timestamp,
        "fs_from_record": raw_rec.fs,
        "rpm_from_record": _auto_float(getattr(raw_rec, "rpm", None)),
        "s3_key": None,
        "s3_error": None,
        "waveform_len": 0,
        "rpm_from_s3_payload": None,
    }

    raw_data_field = raw_rec.raw_data or []
    try:
        waveform = [float(item) for item in raw_data_field]
    except Exception as exc:
        raise ValueError(f"RawDataMaster.raw_data contains non-numeric samples: {exc}")
    fs = _v4_positive_float(raw_rec.fs)

    debug["waveform_len"] = len(waveform)
    if not waveform:
        raise ValueError("Acceleration TWF is empty.")
    if not fs:
        raise ValueError("Sampling frequency fs is missing or invalid.")

    return waveform, fs, debug


def _v4_prefetch_s3_payload_cache(latest_raw_records_map):
    return {}


def _v4_build_mount_runtime_context(
    mount,
    signal_processing_map=None,
    latest_raw_records_map=None,
    s3_payload_cache=None,
):
    mount_id = str(mount.id)
    mount_asset_id = str(mount.asset_id or "").strip()
    context = {
        "mount_id": mount_id,
        "asset_id": mount_asset_id,
        "raw_records": {},
        "source_acc_stat": None,
        "axis_waveforms": {},
        "axis_debug": {},
        "warnings": [],
        "missing": [],
        "reason": None,
        "fs_values": [],
        "fs": None,
        "timestamps": [],
        "fault_time": None,
        "rpm": None,
        "rpm_source": None,
        "bearing_fault_frequencies_hz": {},
        "bearing_fault_frequency_sources": {},
        "surface_temperature_c": None,
        "surface_temperature_timestamp": None,
        "component_type": _v4_component_type_from_mount(mount),
        "pump_cfg": None,
    }

    raw_records, source_acc_stat, raw_selection_info = _v4_latest_raw_records(
        mount_asset_id,
        mount_id,
        prefetched_map=latest_raw_records_map,
    )
    context["raw_records"] = raw_records or {}
    context["source_acc_stat"] = source_acc_stat
    context["raw_selection_info"] = raw_selection_info

    if not raw_records:
        if raw_selection_info and raw_selection_info.get("is_stale"):
            context["missing"].append(raw_selection_info.get("status") or "stale_raw_data")
            context["reason"] = (
                "Endpoint skipped because its latest RawDataMaster timestamp is more than 1 day older than the freshest endpoint timestamp in this diagnostic run."
            )
            context["latest_raw_timestamp"] = raw_selection_info.get("latest_raw_timestamp")
            context["freshest_raw_timestamp"] = raw_selection_info.get("freshest_raw_timestamp")
        elif source_acc_stat:
            context["missing"].append("raw_data_master_at_running_timestamp")
            context["reason"] = (
                "A qualifying acceleration_stat_time_optimized timestamp (rms_Vertical > 0.08, rms_only=False) was found, but no matching RawDataMaster acceleration TWF records were found for this mount."
            )
        else:
            context["missing"].append("running_acceleration_stat_time_optimized")
            context["reason"] = (
                "No acceleration_stat_time_optimized record found where rms_Vertical > 0.08 and rms_only is False."
            )
        return context

    rpm_candidates = []
    for axis, raw_rec in raw_records.items():
        try:
            waveform, fs, debug = _v4_waveform_from_raw_record(raw_rec, s3_payload_cache=s3_payload_cache)
            axis_key = axis.lower()
            context["axis_waveforms"][axis_key] = waveform
            context["fs_values"].append(fs)
            context["axis_debug"][axis_key] = debug
            if raw_rec.timestamp:
                context["timestamps"].append(raw_rec.timestamp)
            record_rpm = _v4_positive_float(getattr(raw_rec, "rpm", None))
            if record_rpm is not None:
                rpm_candidates.append(("raw_data_master.rpm", axis, record_rpm))
        except Exception as exc:
            context["warnings"].append(f"{mount_id}/{axis}: {exc}")

    if not context["axis_waveforms"]:
        context["missing"].append("valid_acceleration_twf")
        context["reason"] = "RawDataMaster records exist, but no axis waveform could be loaded."
        return context

    if rpm_candidates:
        rpm_source, rpm_axis, rpm = rpm_candidates[0]
        context["rpm"] = rpm
        context["rpm_source"] = {"source": rpm_source, "axis": rpm_axis}
    else:
        if signal_processing_map is not None:
            sig_proc = signal_processing_map.get((mount_asset_id, mount_id))
        else:
            sig_proc = _get_signal_processing(mount_asset_id, mount_id)
        rpm = _v4_positive_float(getattr(sig_proc, "rpm", None))
        if rpm is not None:
            context["rpm"] = rpm
            context["rpm_source"] = {"source": "signal_processing_master.rpm", "axis": None}
        else:
            context["missing"].append("rpm_raw_data_master_or_signal_processing_master")

    if context["fs_values"]:
        context["fs"] = context["fs_values"][0]
    if not context["fs"]:
        context["missing"].append("sampling_frequency_hz")
    if context["timestamps"]:
        context["fault_time"] = max(context["timestamps"])

    bff_records = _v4_latest_bff_records(mount_asset_id, mount_id)
    bff_map, bff_sources = _v4_bff_map_from_records(bff_records)
    context["bearing_fault_frequencies_hz"] = bff_map
    context["bearing_fault_frequency_sources"] = bff_sources

    surface_temp_c, temp_timestamp = _v4_latest_temperature(mount_asset_id, mount_id, mount.composite_id)
    context["surface_temperature_c"] = surface_temp_c
    context["surface_temperature_timestamp"] = temp_timestamp

    context["pump_cfg"] = (
        models.PumpFanFaultsMaster.objects
        .filter(mount_id=mount_id, asset_id=mount_asset_id)
        .order_by("-last_update", "-creation_date")
        .first()
    )
    return context


def _v4_build_mount_runtime_context_map(mounts):
    signal_processing_map = _v4_prefetch_signal_processing_map(mounts)
    latest_raw_records_map = _v4_prefetch_latest_raw_records_map(mounts)
    s3_payload_cache = _v4_prefetch_s3_payload_cache(latest_raw_records_map)
    context_map = {}
    for mount in mounts:
        context_map[str(mount.id)] = _v4_build_mount_runtime_context(
            mount,
            signal_processing_map=signal_processing_map,
            latest_raw_records_map=latest_raw_records_map,
            s3_payload_cache=s3_payload_cache,
        )
    return context_map


def _v4_endpoint_fault_timestamp_map(mount_runtime_context_map):
    timestamp_map = {}
    for mount_id, ctx in (mount_runtime_context_map or {}).items():
        fault_time = (ctx or {}).get("fault_time")
        if fault_time:
            timestamp_map[str(mount_id)] = fault_time
    return timestamp_map


def _v4_get_mount_runtime_context(mount, mount_runtime_context_map=None):
    mount_id = str(mount.id)
    if mount_runtime_context_map and mount_id in mount_runtime_context_map:
        return mount_runtime_context_map[mount_id]
    return _v4_build_mount_runtime_context(mount)


def _v4_diagnose_mount_impact(mount, payload, mount_runtime_context=None):
    mount_id = str(mount.id)
    mount_asset_id = str(mount.asset_id or "").strip()
    ctx = mount_runtime_context or _v4_build_mount_runtime_context(mount)
    result = {
        "asset_id": mount_asset_id,
        "mount_id": mount_id,
        "point_name": mount.point_name,
        "mount_location": mount.mount_location or "",
        "equipment_type": getattr(mount, "equipment_type", "") or "",
        "result": "skipped",
        "missing": [],
        "warnings": [],
        "axis_debug": {},
        "source_acceleration_stat": None,
        "bearing_fault_frequencies_hz": {},
        "fault_time": None,
        "fault_timestamp": None,
        "surface_temperature_c": None,
        "surface_temperature_timestamp": None,
        "bearing_diagnosis": None,
        "lubrication_diagnosis": None,
        "diagnosis": None,
    }
    source_acc_stat = ctx.get("source_acc_stat")
    if source_acc_stat:
        result["source_acceleration_stat"] = {
            "id": source_acc_stat.id,
            "timestamp": source_acc_stat.timestamp,
            "operating_mode": getattr(source_acc_stat, "operating_mode", None),
            "rms_only": source_acc_stat.rms_only,
        }

    result["axis_debug"] = dict(ctx.get("axis_debug") or {})
    result["warnings"].extend(list(ctx.get("warnings") or []))

    axis_waveforms = dict(ctx.get("axis_waveforms") or {})
    if not axis_waveforms:
        result["missing"].extend(list(ctx.get("missing") or []))
        result["reason"] = ctx.get("reason") or "No valid running acceleration waveform was available for this mount."
        return result

    rpm_source = ctx.get("rpm_source")
    if rpm_source:
        result["rpm_source"] = rpm_source
    rpm = _v4_positive_float(ctx.get("rpm"))
    fs_values = list(ctx.get("fs_values") or [])
    fs = _v4_positive_float(ctx.get("fs"))
    if len({round(float(value), 6) for value in fs_values}) > 1:
        result["warnings"].append("Multiple sampling frequencies found across axes; using first valid fs.")
    if rpm is None:
        result["missing"].append("rpm_raw_data_master_or_signal_processing_master")
    if not fs:
        result["missing"].append("sampling_frequency_hz")

    bff_map = dict(ctx.get("bearing_fault_frequencies_hz") or {})
    bff_sources = dict(ctx.get("bearing_fault_frequency_sources") or {})
    result["bearing_fault_frequencies_hz"] = bff_map
    result["bearing_fault_frequency_sources"] = bff_sources
    missing_families = [family.upper() for family in ("bpfo", "bpfi", "bsf", "ftf") if family.upper() not in bff_map]
    if not bff_map:
        result["warnings"].append(
            "No BPFO/BPFI/BSF/FTF found in bearing_fault_frequencies_master; bearing-frequency detection skipped and lubrication suppression unavailable."
        )
    elif missing_families:
        result["warnings"].append(f"Missing BFF families: {', '.join(missing_families)}")

    surface_temp_c = _auto_float(ctx.get("surface_temperature_c"))
    temp_timestamp = ctx.get("surface_temperature_timestamp")
    result["surface_temperature_c"] = surface_temp_c
    result["surface_temperature_timestamp"] = temp_timestamp

    if result["missing"]:
        result["reason"] = ctx.get("reason") or "Required waveform, sampling frequency, or RPM data is missing; no V4 fault created for this mount."
        return result

    try:
        fault_time = ctx.get("fault_time")
        min_score = float(payload.get("min_score", payload.get("minimum_score", 20.0)))
        target_tolerance_pct = float(payload.get("target_tolerance_pct", 3.0))
        harmonics = int(payload.get("harmonics", 4))
        acceleration_twf = {mount_id: axis_waveforms}
        axis_feature_cache = build_impact_axis_feature_cache(
            acceleration_twf=acceleration_twf,
            sampling_frequency_hz=fs,
            rpm=rpm,
        )

        bearing_diagnosis = None
        if bff_map:
            bearing_diagnosis = detect_bearing_fault_frequencies(
                acceleration_twf=acceleration_twf,
                sampling_frequency_hz=fs,
                rpm=rpm,
                bearing_fault_frequencies=bff_map,
                asset_id=mount_asset_id,
                fault_frequency_units="hz",
                min_score=min_score,
                target_tolerance_pct=target_tolerance_pct,
                harmonics=harmonics,
                axis_feature_cache=axis_feature_cache,
            )

        lubrication_diagnosis = detect_lubrication_issue(
            acceleration_twf=acceleration_twf,
            sampling_frequency_hz=fs,
            rpm=rpm,
            asset_id=mount_asset_id,
            surface_temperature_c=surface_temp_c,
            baseline_temperature_c=payload.get("baseline_temperature_c"),
            temperature_delta_c=payload.get("temperature_delta_c"),
            bearing_fault_frequencies=bff_map or None,
            fault_frequency_units="hz",
            min_score=min_score,
            target_tolerance_pct=target_tolerance_pct,
            harmonics=harmonics,
            axis_feature_cache=axis_feature_cache,
            bearing_diagnosis=bearing_diagnosis,
        )

        possible_faults = []
        for fault in (bearing_diagnosis or {}).get("possible_faults") or []:
            possible_faults.append({
                **fault,
                "diagnostic_family": "bearing_defect",
                "fault_time": fault_time,
                "fault_timestamp": fault_time,
            })
        for fault in (lubrication_diagnosis or {}).get("possible_faults") or []:
            possible_faults.append({
                **fault,
                "diagnostic_family": "lubrication",
                "fault_time": fault_time,
                "fault_timestamp": fault_time,
            })
        possible_faults.sort(key=lambda row: float(row.get("score") or 0.0), reverse=True)
        diagnosis = {
            "primary_fault": possible_faults[0] if possible_faults else None,
            "possible_faults": possible_faults,
            "bearing_diagnosis": bearing_diagnosis,
            "lubrication_diagnosis": lubrication_diagnosis,
            "limitations": list(
                ((bearing_diagnosis or {}).get("limitations") or [])
                + ((lubrication_diagnosis or {}).get("limitations") or [])
            ),
        }
        result["result"] = "ok"
        result["rpm"] = rpm
        result["sampling_frequency_hz"] = fs
        result["fault_time"] = fault_time
        result["fault_timestamp"] = fault_time
        result["bearing_diagnosis"] = bearing_diagnosis
        result["lubrication_diagnosis"] = lubrication_diagnosis
        result["diagnosis"] = diagnosis
        return result
    except Exception as exc:
        result["result"] = "error"
        result["error"] = str(exc)
        result["traceback"] = traceback.format_exc()
        return result


def _v4_aggregate_impact_mount_results(mount_results):
    possible_faults = []
    for mount_result in mount_results:
        diagnosis = mount_result.get("diagnosis") or {}
        for fault in diagnosis.get("possible_faults") or []:
            possible_faults.append({
                **fault,
                "asset_id": mount_result.get("asset_id"),
                "mount_id": mount_result.get("mount_id"),
                "point_name": mount_result.get("point_name"),
                "mount_location": mount_result.get("mount_location"),
                "fault_time": mount_result.get("fault_time"),
                "fault_timestamp": mount_result.get("fault_timestamp"),
            })

    possible_faults.sort(key=lambda row: float(row.get("score") or 0.0), reverse=True)
    primary_fault = possible_faults[0] if possible_faults else None
    return {
        "primary_fault": primary_fault,
        "possible_faults": possible_faults,
        "faults_detected": len(possible_faults),
    }


def _v4_component_type_from_mount(mount):
    text = f"{getattr(mount, 'equipment_type', '') or ''} {getattr(mount, 'asset_type', '') or ''} {mount.point_name or ''} {mount.mount_location or ''}".lower()
    for component in ["motor", "engine", "turbine", "pump", "fan", "blower", "compressor", "chiller"]:
        if component in text:
            return component
    return str(getattr(mount, "equipment_type", None) or getattr(mount, "asset_type", None) or "unknown").strip().lower() or "unknown"


def _v4_installed_on_from_mount(mount):
    text = f"{mount.mount_type or ''} {mount.mount_location or ''} {mount.point_name or ''}".lower()
    if "foundation" in text:
        return "foundation"
    if "base" in text:
        return "base"
    if "pedestal" in text or "pillow" in text:
        return "pedestal"
    if "bearing" in text or "de" in text or "nde" in text:
        return "bearing_housing"
    if "casing" in text or "case" in text:
        return "casing"
    return str(mount.mount_type or mount.mount_location or "unknown").strip().lower() or "unknown"


def _v4_mount_endpoint_metadata(mount, rpm):
    endpoint_role = "DE" if _auto_is_coupling_end(mount) else "unknown"
    text = f"{mount.point_name or ''} {mount.mount_location or ''}".lower().replace("_", " ").replace("-", " ")
    if "nde" in text or "non drive" in text:
        endpoint_role = "NDE"

    return {
        "endpoint_role": endpoint_role,
        "installed_on": _v4_installed_on_from_mount(mount),
        "component_type": _v4_component_type_from_mount(mount),
        "component_id": str(mount.id),
        "shaft_group_id": "asset_train",
        "coupling_id": "",
        "is_coupling_end": endpoint_role == "DE",
        "local_rpm": rpm,
        "location_tag": mount.mount_location or "",
        "endpoint_tag": mount.point_name or "",
        "name": mount.point_name or "",
        "mount_name": mount.point_name or "",
        "composite_id": mount.composite_id or "",
    }


def _v4_rpm_from_raw_or_signal(raw_records, mount_asset_id, mount_id):
    for axis, raw_rec in (raw_records or {}).items():
        record_rpm = _v4_positive_float(getattr(raw_rec, "rpm", None))
        if record_rpm is not None:
            return record_rpm, {"source": "raw_data_master.rpm", "axis": axis}

    sig_proc = _get_signal_processing(mount_asset_id, mount_id)
    rpm = _v4_positive_float(getattr(sig_proc, "rpm", None))
    if rpm is not None:
        return rpm, {"source": "signal_processing_master.rpm", "axis": None}
    return None, None


def _v4_primary_family_score(family_result):
    diagnosis = (family_result or {}).get("diagnosis") or {}
    primary_fault = diagnosis.get("primary_fault") or {}
    return _v4_positive_float(primary_fault.get("score"))


def _v4_max_fault_score(aggregate_result, fault_names):
    wanted = {str(name).strip().lower() for name in (fault_names or [])}
    scores = []
    for fault in (aggregate_result or {}).get("possible_faults") or []:
        if str(fault.get("fault") or "").strip().lower() in wanted:
            score = _v4_positive_float(fault.get("score"))
            if score is not None:
                scores.append(score)
    return max(scores) if scores else None


def _v4_diagnose_mechanical_looseness(mounts, payload, requested_asset_id, mount_runtime_context_map=None):
    result = {
        "result": "skipped",
        "missing": [],
        "warnings": [],
        "endpoint_sources": [],
        "fault_time": None,
        "fault_timestamp": None,
        "diagnosis": None,
    }

    vibration_twf = {}
    endpoint_metadata = {}
    rpm_values = []
    fs_values = []
    timestamps = []
    min_score = float(payload.get("min_score", payload.get("minimum_score", 20.0)))
    target_tolerance_pct = float(payload.get("target_tolerance_pct", 3.0))

    for mount in mounts:
        mount_id = str(mount.id)
        mount_asset_id = str(mount.asset_id or "").strip()
        ctx = _v4_get_mount_runtime_context(mount, mount_runtime_context_map)
        result["warnings"].extend(list(ctx.get("warnings") or []))
        axis_waveforms = dict(ctx.get("axis_waveforms") or {})
        if not axis_waveforms:
            continue

        rpm = _v4_positive_float(ctx.get("rpm"))
        rpm_source = ctx.get("rpm_source")
        if rpm is None:
            result["warnings"].append(f"{mount_id}: skipped for looseness because RPM is missing.")
            continue

        endpoint_fs_values = list(ctx.get("fs_values") or [])
        endpoint_timestamps = list(ctx.get("timestamps") or [])
        source_acc_stat = ctx.get("source_acc_stat")

        endpoint_key = mount_id
        vibration_twf[endpoint_key] = axis_waveforms
        endpoint_metadata[endpoint_key] = _v4_mount_endpoint_metadata(mount, rpm)
        rpm_values.append(rpm)
        fs_values.extend(endpoint_fs_values)
        timestamps.extend(endpoint_timestamps)
        result["endpoint_sources"].append({
            "endpoint_id": endpoint_key,
            "asset_id": mount_asset_id,
            "mount_id": mount_id,
            "point_name": mount.point_name,
            "mount_location": mount.mount_location or "",
            "equipment_type": getattr(mount, "equipment_type", "") or "",
            "rpm": rpm,
            "rpm_source": rpm_source,
            "source_acceleration_stat": {
                "id": source_acc_stat.id,
                "timestamp": source_acc_stat.timestamp,
                "operating_mode": getattr(source_acc_stat, "operating_mode", None),
                "rms_only": source_acc_stat.rms_only,
            } if source_acc_stat else None,
        })

    if not vibration_twf:
        result["missing"].append("asset_wide_acceleration_twf_for_mechanical_looseness")
        result["reason"] = "No valid running acceleration TWF endpoints were available for mechanical looseness detection."
        return result

    fs = fs_values[0] if fs_values else None
    if not fs:
        result["missing"].append("sampling_frequency_hz")
        result["reason"] = "Sampling frequency is missing for mechanical looseness detection."
        return result

    unique_fs = {round(float(value), 6) for value in fs_values}
    if len(unique_fs) > 1:
        result["warnings"].append("Multiple sampling frequencies found across endpoints; mechanical looseness uses the first valid fs.")

    rpm = rpm_values[0] if rpm_values else None
    if not rpm:
        result["missing"].append("rpm_raw_data_master_or_signal_processing_master")
        result["reason"] = "RPM is missing for mechanical looseness detection."
        return result

    try:
        fault_time = max(timestamps) if timestamps else None
        diagnosis = detect_mechanical_looseness(
            vibration_twf=vibration_twf,
            sampling_frequency_hz=fs,
            rpm=rpm,
            asset_id=requested_asset_id,
            signal_type="acceleration",
            acceleration_unit=str(payload.get("acceleration_unit", "g")),
            integration_low_cut_hz=float(payload.get("integration_low_cut_hz", 0.2)),
            endpoint_metadata=endpoint_metadata,
            min_score=min_score,
            target_tolerance_pct=target_tolerance_pct,
            phase_data_available=_auto_bool(payload.get("phase_data_available"), False),
        )

        possible_faults = []
        for fault in diagnosis.get("possible_faults") or []:
            possible_faults.append({
                **fault,
                "diagnostic_family": "mechanical_looseness",
                "fault_time": fault_time,
                "fault_timestamp": fault_time,
            })
        diagnosis["possible_faults"] = possible_faults
        diagnosis["primary_fault"] = possible_faults[0] if possible_faults else None

        result["result"] = "ok"
        result["rpm"] = rpm
        result["sampling_frequency_hz"] = fs
        result["fault_time"] = fault_time
        result["fault_timestamp"] = fault_time
        result["diagnosis"] = diagnosis
        return result
    except Exception as exc:
        result["result"] = "error"
        result["error"] = str(exc)
        result["traceback"] = traceback.format_exc()
        return result


def _v4_diagnose_unbalance(mounts, payload, requested_asset_id, mount_runtime_context_map=None):
    result = {
        "result": "skipped",
        "missing": [],
        "warnings": [],
        "endpoint_sources": [],
        "fault_time": None,
        "fault_timestamp": None,
        "diagnosis": None,
    }

    vibration_twf = {}
    endpoint_metadata = {}
    rpm_values = []
    fs_values = []
    timestamps = []
    min_score = float(payload.get("min_score", payload.get("minimum_score", 20.0)))
    target_tolerance_pct = float(payload.get("target_tolerance_pct", 3.0))

    for mount in mounts:
        mount_id = str(mount.id)
        mount_asset_id = str(mount.asset_id or "").strip()
        ctx = _v4_get_mount_runtime_context(mount, mount_runtime_context_map)
        result["warnings"].extend(list(ctx.get("warnings") or []))
        axis_waveforms = dict(ctx.get("axis_waveforms") or {})
        if not axis_waveforms:
            continue

        rpm = _v4_positive_float(ctx.get("rpm"))
        rpm_source = ctx.get("rpm_source")
        if rpm is None:
            result["warnings"].append(f"{mount_id}: skipped for unbalance because RPM is missing.")
            continue

        endpoint_fs_values = list(ctx.get("fs_values") or [])
        endpoint_timestamps = list(ctx.get("timestamps") or [])
        source_acc_stat = ctx.get("source_acc_stat")

        endpoint_key = mount_id
        vibration_twf[endpoint_key] = axis_waveforms
        endpoint_metadata[endpoint_key] = _v4_mount_endpoint_metadata(mount, rpm)
        rpm_values.append(rpm)
        fs_values.extend(endpoint_fs_values)
        timestamps.extend(endpoint_timestamps)
        result["endpoint_sources"].append({
            "endpoint_id": endpoint_key,
            "asset_id": mount_asset_id,
            "mount_id": mount_id,
            "point_name": mount.point_name,
            "mount_location": mount.mount_location or "",
            "equipment_type": getattr(mount, "equipment_type", "") or "",
            "rpm": rpm,
            "rpm_source": rpm_source,
            "source_acceleration_stat": {
                "id": source_acc_stat.id,
                "timestamp": source_acc_stat.timestamp,
                "operating_mode": getattr(source_acc_stat, "operating_mode", None),
                "rms_only": source_acc_stat.rms_only,
            } if source_acc_stat else None,
        })

    if not vibration_twf:
        result["missing"].append("asset_wide_acceleration_twf_for_unbalance")
        result["reason"] = "No valid running acceleration TWF endpoints were available for unbalance detection."
        return result

    fs = fs_values[0] if fs_values else None
    if not fs:
        result["missing"].append("sampling_frequency_hz")
        result["reason"] = "Sampling frequency is missing for unbalance detection."
        return result

    unique_fs = {round(float(value), 6) for value in fs_values}
    if len(unique_fs) > 1:
        result["warnings"].append("Multiple sampling frequencies found across endpoints; unbalance uses the first valid fs.")

    rpm = rpm_values[0] if rpm_values else None
    if not rpm:
        result["missing"].append("rpm_raw_data_master_or_signal_processing_master")
        result["reason"] = "RPM is missing for unbalance detection."
        return result

    try:
        fault_time = max(timestamps) if timestamps else None
        diagnosis = detect_unbalance(
            vibration_twf=vibration_twf,
            sampling_frequency_hz=fs,
            rpm=rpm,
            asset_id=requested_asset_id,
            signal_type="acceleration",
            acceleration_unit=str(payload.get("acceleration_unit", "g")),
            integration_low_cut_hz=float(payload.get("integration_low_cut_hz", 0.2)),
            endpoint_metadata=endpoint_metadata,
            min_score=min_score,
            target_tolerance_pct=target_tolerance_pct,
            de_pair_enabled=_auto_bool(payload.get("de_pair_enabled"), True),
        )

        possible_faults = []
        for fault in diagnosis.get("possible_faults") or []:
            possible_faults.append({
                **fault,
                "diagnostic_family": "unbalance",
                "fault_time": fault_time,
                "fault_timestamp": fault_time,
            })
        diagnosis["possible_faults"] = possible_faults
        diagnosis["primary_fault"] = possible_faults[0] if possible_faults else None

        result["result"] = "ok"
        result["rpm"] = rpm
        result["sampling_frequency_hz"] = fs
        result["fault_time"] = fault_time
        result["fault_timestamp"] = fault_time
        result["diagnosis"] = diagnosis
        return result
    except Exception as exc:
        result["result"] = "error"
        result["error"] = str(exc)
        result["traceback"] = traceback.format_exc()
        return result


def _v4_diagnose_hydraulic_vane_blade_pass(mounts, payload, requested_asset_id, mount_runtime_context_map=None):
    result = {
        "result": "skipped",
        "missing": [],
        "warnings": [],
        "endpoint_sources": [],
        "fault_time": None,
        "fault_timestamp": None,
        "diagnosis": None,
    }

    vibration_twf = {}
    endpoint_metadata = {}
    hydraulic_elements = []
    surface_temperature_c = {}
    rpm_values = []
    fs_values = []
    timestamps = []
    min_score = float(payload.get("min_score", payload.get("minimum_score", 20.0)))
    target_tolerance_pct = float(payload.get("target_tolerance_pct", 3.0))

    for mount in mounts:
        mount_id = str(mount.id)
        mount_asset_id = str(mount.asset_id or "").strip()
        ctx = _v4_get_mount_runtime_context(mount, mount_runtime_context_map)
        result["warnings"].extend(list(ctx.get("warnings") or []))
        axis_waveforms = dict(ctx.get("axis_waveforms") or {})
        if not axis_waveforms:
            continue

        rpm = _v4_positive_float(ctx.get("rpm"))
        rpm_source = ctx.get("rpm_source")
        if rpm is None:
            result["warnings"].append(f"{mount_id}: skipped for hydraulic vane/blade pass because RPM is missing.")
            continue

        endpoint_fs_values = list(ctx.get("fs_values") or [])
        endpoint_timestamps = list(ctx.get("timestamps") or [])
        source_acc_stat = ctx.get("source_acc_stat")
        component_type = str(ctx.get("component_type") or _v4_component_type_from_mount(mount))
        pump_cfg = ctx.get("pump_cfg")
        payload_pass_count = _auto_float(
            payload.get("hydraulic_pass_count")
            or payload.get("pass_count")
            or payload.get("vane_count")
            or payload.get("blade_count")
        )
        pass_count = (
            _auto_float(getattr(pump_cfg, "vanes_no_lower", None))
            or _auto_float(getattr(pump_cfg, "vanes_no_upper", None))
            or payload_pass_count
        )

        endpoint_key = mount_id
        vibration_twf[endpoint_key] = axis_waveforms
        endpoint_metadata[endpoint_key] = _v4_mount_endpoint_metadata(mount, rpm)
        rpm_values.append(rpm)
        fs_values.extend(endpoint_fs_values)
        timestamps.extend(endpoint_timestamps)

        temp_c = _auto_float(ctx.get("surface_temperature_c"))
        temp_ts = ctx.get("surface_temperature_timestamp")
        if temp_c is not None:
            surface_temperature_c[endpoint_key] = temp_c

        if pass_count and pass_count > 0 and component_type in {"pump", "fan", "blower", "compressor", "chiller"}:
            hydraulic_id = f"hydraulic_{mount_id}"
            endpoint_metadata[endpoint_key]["hydraulic_id"] = hydraulic_id
            hydraulic_elements.append({
                "hydraulic_id": hydraulic_id,
                "component_id": mount_id,
                "component_type": component_type,
                "pass_count": int(pass_count),
                "local_rpm": rpm,
            })

        result["endpoint_sources"].append({
            "endpoint_id": endpoint_key,
            "asset_id": mount_asset_id,
            "mount_id": mount_id,
            "point_name": mount.point_name,
            "mount_location": mount.mount_location or "",
            "equipment_type": getattr(mount, "equipment_type", "") or "",
            "component_type": component_type,
            "rpm": rpm,
            "rpm_source": rpm_source,
            "surface_temperature_c": temp_c,
            "surface_temperature_timestamp": temp_ts,
            "source_acceleration_stat": {
                "id": source_acc_stat.id,
                "timestamp": source_acc_stat.timestamp,
                "operating_mode": getattr(source_acc_stat, "operating_mode", None),
                "rms_only": source_acc_stat.rms_only,
            } if source_acc_stat else None,
        })

    if not vibration_twf:
        result["missing"].append("asset_wide_acceleration_twf_for_hydraulic_vane_blade_pass")
        result["reason"] = "No valid running acceleration TWF endpoints were available for hydraulic vane/blade pass detection."
        return result

    if not hydraulic_elements:
        result["missing"].append("hydraulic_pass_count")
        result["reason"] = "No valid vane/blade count metadata was available for pump/fan style endpoints."
        return result

    fs = fs_values[0] if fs_values else None
    if not fs:
        result["missing"].append("sampling_frequency_hz")
        result["reason"] = "Sampling frequency is missing for hydraulic vane/blade pass detection."
        return result

    unique_fs = {round(float(value), 6) for value in fs_values}
    if len(unique_fs) > 1:
        result["warnings"].append("Multiple sampling frequencies found across endpoints; hydraulic vane/blade pass detection uses the first valid fs.")

    rpm = rpm_values[0] if rpm_values else None
    if not rpm:
        result["missing"].append("rpm_raw_data_master_or_signal_processing_master")
        result["reason"] = "RPM is missing for hydraulic vane/blade pass detection."
        return result

    try:
        fault_time = max(timestamps) if timestamps else None
        diagnosis = detect_hydraulic_vane_blade_pass(
            acceleration_twf=vibration_twf,
            sampling_frequency_hz=fs,
            rpm=rpm,
            hydraulic_elements=hydraulic_elements,
            asset_id=requested_asset_id,
            endpoint_metadata=endpoint_metadata,
            surface_temperature_c=surface_temperature_c or None,
            min_score=min_score,
            target_tolerance_pct=target_tolerance_pct,
            compare_de_endpoints=_auto_bool(payload.get("compare_de_endpoints"), _auto_bool(payload.get("de_pair_enabled"), True)),
        )

        possible_faults = []
        for fault in diagnosis.get("possible_faults") or []:
            possible_faults.append({
                **fault,
                "diagnostic_family": "hydraulic_vane_or_blade_pass",
                "fault_time": fault_time,
                "fault_timestamp": fault_time,
            })
        diagnosis["possible_faults"] = possible_faults
        diagnosis["primary_fault"] = possible_faults[0] if possible_faults else None

        result["result"] = "ok"
        result["rpm"] = rpm
        result["sampling_frequency_hz"] = fs
        result["fault_time"] = fault_time
        result["fault_timestamp"] = fault_time
        result["diagnosis"] = diagnosis
        return result
    except Exception as exc:
        result["result"] = "error"
        result["error"] = str(exc)
        result["traceback"] = traceback.format_exc()
        return result


def _v4_diagnose_cavitation_or_aeration(
    mounts,
    payload,
    requested_asset_id,
    competing_hydraulic_pass_score=None,
    mount_runtime_context_map=None,
):
    result = {
        "result": "skipped",
        "missing": [],
        "warnings": [],
        "endpoint_sources": [],
        "fault_time": None,
        "fault_timestamp": None,
        "diagnosis": None,
    }

    vibration_twf = {}
    endpoint_metadata = {}
    hydraulic_elements = []
    surface_temperature_c = {}
    rpm_values = []
    fs_values = []
    timestamps = []
    min_score = float(payload.get("min_score", payload.get("minimum_score", 20.0)))
    target_tolerance_pct = float(payload.get("target_tolerance_pct", 3.0))

    for mount in mounts:
        mount_id = str(mount.id)
        mount_asset_id = str(mount.asset_id or "").strip()
        ctx = _v4_get_mount_runtime_context(mount, mount_runtime_context_map)
        result["warnings"].extend(list(ctx.get("warnings") or []))
        axis_waveforms = dict(ctx.get("axis_waveforms") or {})
        if not axis_waveforms:
            continue

        rpm = _v4_positive_float(ctx.get("rpm"))
        rpm_source = ctx.get("rpm_source")
        if rpm is None:
            result["warnings"].append(f"{mount_id}: skipped for cavitation/aeration because RPM is missing.")
            continue

        endpoint_fs_values = list(ctx.get("fs_values") or [])
        endpoint_timestamps = list(ctx.get("timestamps") or [])
        source_acc_stat = ctx.get("source_acc_stat")
        component_type = str(ctx.get("component_type") or _v4_component_type_from_mount(mount))
        pump_cfg = ctx.get("pump_cfg")
        payload_pass_count = _auto_float(
            payload.get("hydraulic_pass_count")
            or payload.get("pass_count")
            or payload.get("vane_count")
            or payload.get("blade_count")
        )
        pass_count = (
            _auto_float(getattr(pump_cfg, "vanes_no_lower", None))
            or _auto_float(getattr(pump_cfg, "vanes_no_upper", None))
            or payload_pass_count
        )

        endpoint_key = mount_id
        vibration_twf[endpoint_key] = axis_waveforms
        endpoint_metadata[endpoint_key] = _v4_mount_endpoint_metadata(mount, rpm)
        rpm_values.append(rpm)
        fs_values.extend(endpoint_fs_values)
        timestamps.extend(endpoint_timestamps)

        temp_c = _auto_float(ctx.get("surface_temperature_c"))
        temp_ts = ctx.get("surface_temperature_timestamp")
        if temp_c is not None:
            surface_temperature_c[endpoint_key] = temp_c

        if component_type in {"pump", "fan", "blower", "compressor", "chiller"}:
            hydraulic_id = f"hydraulic_{mount_id}"
            endpoint_metadata[endpoint_key]["hydraulic_id"] = hydraulic_id
            hydraulic_item = {
                "hydraulic_id": hydraulic_id,
                "component_id": mount_id,
                "component_type": component_type,
                "local_rpm": rpm,
            }
            if pass_count and pass_count > 0:
                hydraulic_item["pass_count"] = int(pass_count)
            hydraulic_elements.append(hydraulic_item)

        result["endpoint_sources"].append({
            "endpoint_id": endpoint_key,
            "asset_id": mount_asset_id,
            "mount_id": mount_id,
            "point_name": mount.point_name,
            "mount_location": mount.mount_location or "",
            "equipment_type": getattr(mount, "equipment_type", "") or "",
            "component_type": component_type,
            "rpm": rpm,
            "rpm_source": rpm_source,
            "surface_temperature_c": temp_c,
            "surface_temperature_timestamp": temp_ts,
            "source_acceleration_stat": {
                "id": source_acc_stat.id,
                "timestamp": source_acc_stat.timestamp,
                "operating_mode": getattr(source_acc_stat, "operating_mode", None),
                "rms_only": source_acc_stat.rms_only,
            } if source_acc_stat else None,
        })

    if not vibration_twf:
        result["missing"].append("asset_wide_acceleration_twf_for_cavitation_or_aeration")
        result["reason"] = "No valid running acceleration TWF endpoints were available for cavitation/aeration detection."
        return result

    fs = fs_values[0] if fs_values else None
    if not fs:
        result["missing"].append("sampling_frequency_hz")
        result["reason"] = "Sampling frequency is missing for cavitation/aeration detection."
        return result

    unique_fs = {round(float(value), 6) for value in fs_values}
    if len(unique_fs) > 1:
        result["warnings"].append("Multiple sampling frequencies found across endpoints; cavitation/aeration detection uses the first valid fs.")

    rpm = rpm_values[0] if rpm_values else None
    if not rpm:
        result["missing"].append("rpm_raw_data_master_or_signal_processing_master")
        result["reason"] = "RPM is missing for cavitation/aeration detection."
        return result

    process_evidence = {}
    raw_process_evidence = payload.get("process_evidence")
    if hasattr(raw_process_evidence, "items"):
        process_evidence.update(dict(raw_process_evidence))
    for key in [
        "low_npsh",
        "npsh_margin_low",
        "suction_pressure_low",
        "suction_pressure_drop",
        "air_entrainment",
        "entrained_air",
        "suction_leak",
        "strainer_blocked",
        "valve_throttled",
        "recirculation",
        "minimum_flow_violation",
        "off_design_flow",
    ]:
        if key in payload and key not in process_evidence:
            process_evidence[key] = payload.get(key)

    try:
        fault_time = max(timestamps) if timestamps else None
        diagnosis = detect_cavitation_or_aeration(
            acceleration_twf=vibration_twf,
            sampling_frequency_hz=fs,
            rpm=rpm,
            hydraulic_elements=hydraulic_elements or None,
            asset_id=requested_asset_id,
            endpoint_metadata=endpoint_metadata,
            surface_temperature_c=surface_temperature_c or payload.get("surface_temperature_c"),
            baseline_temperature_c=payload.get("baseline_temperature_c"),
            temperature_delta_c=payload.get("temperature_delta_c"),
            process_evidence=process_evidence or None,
            competing_hydraulic_pass_score=(
                competing_hydraulic_pass_score
                if competing_hydraulic_pass_score is not None
                else payload.get("competing_hydraulic_pass_score")
            ),
            min_score=min_score,
            target_tolerance_pct=target_tolerance_pct,
            compare_de_endpoints=_auto_bool(payload.get("compare_de_endpoints"), _auto_bool(payload.get("de_pair_enabled"), True)),
        )

        possible_faults = []
        for fault in diagnosis.get("possible_faults") or []:
            possible_faults.append({
                **fault,
                "diagnostic_family": "cavitation_or_aeration",
                "fault_time": fault_time,
                "fault_timestamp": fault_time,
            })
        diagnosis["possible_faults"] = possible_faults
        diagnosis["primary_fault"] = possible_faults[0] if possible_faults else None

        result["result"] = "ok"
        result["rpm"] = rpm
        result["sampling_frequency_hz"] = fs
        result["fault_time"] = fault_time
        result["fault_timestamp"] = fault_time
        result["diagnosis"] = diagnosis
        return result
    except Exception as exc:
        result["result"] = "error"
        result["error"] = str(exc)
        result["traceback"] = traceback.format_exc()
        return result


def _v4_diagnose_misalignment(mounts, payload, requested_asset_id, competing_hydraulic_pass_score=None, mount_runtime_context_map=None):
    result = {
        "result": "skipped",
        "missing": [],
        "warnings": [],
        "endpoint_sources": [],
        "fault_time": None,
        "fault_timestamp": None,
        "diagnosis": None,
    }

    vibration_twf = {}
    endpoint_metadata = {}
    rpm_values = []
    fs_values = []
    timestamps = []
    min_score = float(payload.get("min_score", payload.get("minimum_score", 20.0)))
    target_tolerance_pct = float(payload.get("target_tolerance_pct", 3.0))

    for mount in mounts:
        mount_id = str(mount.id)
        mount_asset_id = str(mount.asset_id or "").strip()
        ctx = _v4_get_mount_runtime_context(mount, mount_runtime_context_map)
        result["warnings"].extend(list(ctx.get("warnings") or []))
        axis_waveforms = dict(ctx.get("axis_waveforms") or {})
        if not axis_waveforms:
            continue

        rpm = _v4_positive_float(ctx.get("rpm"))
        rpm_source = ctx.get("rpm_source")
        if rpm is None:
            result["warnings"].append(f"{mount_id}: skipped for misalignment because RPM is missing.")
            continue

        endpoint_fs_values = list(ctx.get("fs_values") or [])
        endpoint_timestamps = list(ctx.get("timestamps") or [])
        source_acc_stat = ctx.get("source_acc_stat")

        endpoint_key = mount_id
        vibration_twf[endpoint_key] = axis_waveforms
        endpoint_metadata[endpoint_key] = _v4_mount_endpoint_metadata(mount, rpm)
        rpm_values.append(rpm)
        fs_values.extend(endpoint_fs_values)
        timestamps.extend(endpoint_timestamps)
        result["endpoint_sources"].append({
            "endpoint_id": endpoint_key,
            "asset_id": mount_asset_id,
            "mount_id": mount_id,
            "point_name": mount.point_name,
            "mount_location": mount.mount_location or "",
            "equipment_type": getattr(mount, "equipment_type", "") or "",
            "rpm": rpm,
            "rpm_source": rpm_source,
            "source_acceleration_stat": {
                "id": source_acc_stat.id,
                "timestamp": source_acc_stat.timestamp,
                "operating_mode": getattr(source_acc_stat, "operating_mode", None),
                "rms_only": source_acc_stat.rms_only,
            } if source_acc_stat else None,
        })

    if not vibration_twf:
        result["missing"].append("asset_wide_acceleration_twf_for_misalignment")
        result["reason"] = "No valid running acceleration TWF endpoints were available for misalignment detection."
        return result

    fs = fs_values[0] if fs_values else None
    if not fs:
        result["missing"].append("sampling_frequency_hz")
        result["reason"] = "Sampling frequency is missing for misalignment detection."
        return result

    unique_fs = {round(float(value), 6) for value in fs_values}
    if len(unique_fs) > 1:
        result["warnings"].append("Multiple sampling frequencies found across endpoints; misalignment uses the first valid fs.")

    rpm = rpm_values[0] if rpm_values else None
    if not rpm:
        result["missing"].append("rpm_raw_data_master_or_signal_processing_master")
        result["reason"] = "RPM is missing for misalignment detection."
        return result

    try:
        fault_time = max(timestamps) if timestamps else None
        diagnosis = detect_misalignment(
            vibration_twf=vibration_twf,
            sampling_frequency_hz=fs,
            rpm=rpm,
            asset_id=requested_asset_id,
            signal_type="acceleration",
            acceleration_unit=str(payload.get("acceleration_unit", "g")),
            integration_low_cut_hz=float(payload.get("integration_low_cut_hz", 0.2)),
            endpoint_metadata=endpoint_metadata,
            min_score=min_score,
            target_tolerance_pct=target_tolerance_pct,
            phase_data_available=_auto_bool(payload.get("phase_data_available"), False),
            competing_hydraulic_pass_score=(
                competing_hydraulic_pass_score
                if competing_hydraulic_pass_score is not None
                else payload.get("competing_hydraulic_pass_score")
            ),
        )

        possible_faults = []
        for fault in diagnosis.get("possible_faults") or []:
            possible_faults.append({
                **fault,
                "diagnostic_family": "misalignment",
                "fault_time": fault_time,
                "fault_timestamp": fault_time,
            })
        diagnosis["possible_faults"] = possible_faults
        diagnosis["primary_fault"] = possible_faults[0] if possible_faults else None

        result["result"] = "ok"
        result["rpm"] = rpm
        result["sampling_frequency_hz"] = fs
        result["fault_time"] = fault_time
        result["fault_timestamp"] = fault_time
        result["diagnosis"] = diagnosis
        return result
    except Exception as exc:
        result["result"] = "error"
        result["error"] = str(exc)
        result["traceback"] = traceback.format_exc()
        return result


def _v4_diagnose_bent_shaft(mounts, payload, requested_asset_id, mount_runtime_context_map=None):
    result = {
        "result": "skipped",
        "missing": [],
        "warnings": [],
        "endpoint_sources": [],
        "fault_time": None,
        "fault_timestamp": None,
        "diagnosis": None,
    }

    vibration_twf = {}
    endpoint_metadata = {}
    rpm_values = []
    fs_values = []
    timestamps = []
    min_score = float(payload.get("min_score", payload.get("minimum_score", 20.0)))
    target_tolerance_pct = float(payload.get("target_tolerance_pct", 3.0))

    for mount in mounts:
        mount_id = str(mount.id)
        mount_asset_id = str(mount.asset_id or "").strip()
        ctx = _v4_get_mount_runtime_context(mount, mount_runtime_context_map)
        result["warnings"].extend(list(ctx.get("warnings") or []))
        axis_waveforms = dict(ctx.get("axis_waveforms") or {})
        if not axis_waveforms:
            continue

        rpm = _v4_positive_float(ctx.get("rpm"))
        rpm_source = ctx.get("rpm_source")
        if rpm is None:
            result["warnings"].append(f"{mount_id}: skipped for bent shaft because RPM is missing.")
            continue

        endpoint_fs_values = list(ctx.get("fs_values") or [])
        endpoint_timestamps = list(ctx.get("timestamps") or [])
        source_acc_stat = ctx.get("source_acc_stat")

        endpoint_key = mount_id
        vibration_twf[endpoint_key] = axis_waveforms
        endpoint_metadata[endpoint_key] = _v4_mount_endpoint_metadata(mount, rpm)
        rpm_values.append(rpm)
        fs_values.extend(endpoint_fs_values)
        timestamps.extend(endpoint_timestamps)
        result["endpoint_sources"].append({
            "endpoint_id": endpoint_key,
            "asset_id": mount_asset_id,
            "mount_id": mount_id,
            "point_name": mount.point_name,
            "mount_location": mount.mount_location or "",
            "equipment_type": getattr(mount, "equipment_type", "") or "",
            "rpm": rpm,
            "rpm_source": rpm_source,
            "source_acceleration_stat": {
                "id": source_acc_stat.id,
                "timestamp": source_acc_stat.timestamp,
                "operating_mode": getattr(source_acc_stat, "operating_mode", None),
                "rms_only": source_acc_stat.rms_only,
            } if source_acc_stat else None,
        })

    if not vibration_twf:
        result["missing"].append("asset_wide_acceleration_twf_for_bent_shaft")
        result["reason"] = "No valid running acceleration TWF endpoints were available for bent-shaft detection."
        return result

    fs = fs_values[0] if fs_values else None
    if not fs:
        result["missing"].append("sampling_frequency_hz")
        result["reason"] = "Sampling frequency is missing for bent-shaft detection."
        return result

    unique_fs = {round(float(value), 6) for value in fs_values}
    if len(unique_fs) > 1:
        result["warnings"].append("Multiple sampling frequencies found across endpoints; bent shaft uses the first valid fs.")

    rpm = rpm_values[0] if rpm_values else None
    if not rpm:
        result["missing"].append("rpm_raw_data_master_or_signal_processing_master")
        result["reason"] = "RPM is missing for bent-shaft detection."
        return result

    try:
        fault_time = max(timestamps) if timestamps else None
        diagnosis = detect_bent_shaft(
            vibration_twf=vibration_twf,
            sampling_frequency_hz=fs,
            rpm=rpm,
            asset_id=requested_asset_id,
            signal_type="acceleration",
            acceleration_unit=str(payload.get("acceleration_unit", "g")),
            integration_low_cut_hz=float(payload.get("integration_low_cut_hz", 0.2)),
            endpoint_metadata=endpoint_metadata,
            min_score=min_score,
            target_tolerance_pct=target_tolerance_pct,
            de_pair_enabled=_auto_bool(payload.get("de_pair_enabled"), True),
            phase_or_runout_available=_auto_bool(payload.get("phase_or_runout_available"), False),
        )

        possible_faults = []
        for fault in diagnosis.get("possible_faults") or []:
            possible_faults.append({
                **fault,
                "diagnostic_family": "bent_shaft_or_bow",
                "fault_time": fault_time,
                "fault_timestamp": fault_time,
            })
        diagnosis["possible_faults"] = possible_faults
        diagnosis["primary_fault"] = possible_faults[0] if possible_faults else None

        result["result"] = "ok"
        result["rpm"] = rpm
        result["sampling_frequency_hz"] = fs
        result["fault_time"] = fault_time
        result["fault_timestamp"] = fault_time
        result["diagnosis"] = diagnosis
        return result
    except Exception as exc:
        result["result"] = "error"
        result["error"] = str(exc)
        result["traceback"] = traceback.format_exc()
        return result


def _v4_diagnose_coupling_related_shaft(
    mounts,
    payload,
    requested_asset_id,
    competing_unbalance_score=None,
    competing_looseness_score=None,
    competing_hydraulic_pass_score=None,
    mount_runtime_context_map=None,
):
    result = {
        "result": "skipped",
        "missing": [],
        "warnings": [],
        "endpoint_sources": [],
        "fault_time": None,
        "fault_timestamp": None,
        "diagnosis": None,
    }

    vibration_twf = {}
    endpoint_metadata = {}
    rpm_values = []
    fs_values = []
    timestamps = []
    min_score = float(payload.get("min_score", payload.get("minimum_score", 20.0)))
    target_tolerance_pct = float(payload.get("target_tolerance_pct", 3.0))

    for mount in mounts:
        mount_id = str(mount.id)
        mount_asset_id = str(mount.asset_id or "").strip()
        ctx = _v4_get_mount_runtime_context(mount, mount_runtime_context_map)
        result["warnings"].extend(list(ctx.get("warnings") or []))
        axis_waveforms = dict(ctx.get("axis_waveforms") or {})
        if not axis_waveforms:
            continue

        rpm = _v4_positive_float(ctx.get("rpm"))
        rpm_source = ctx.get("rpm_source")
        if rpm is None:
            result["warnings"].append(f"{mount_id}: skipped for coupling-related shaft faults because RPM is missing.")
            continue

        endpoint_fs_values = list(ctx.get("fs_values") or [])
        endpoint_timestamps = list(ctx.get("timestamps") or [])
        source_acc_stat = ctx.get("source_acc_stat")

        endpoint_key = mount_id
        vibration_twf[endpoint_key] = axis_waveforms
        endpoint_metadata[endpoint_key] = _v4_mount_endpoint_metadata(mount, rpm)
        rpm_values.append(rpm)
        fs_values.extend(endpoint_fs_values)
        timestamps.extend(endpoint_timestamps)
        result["endpoint_sources"].append({
            "endpoint_id": endpoint_key,
            "asset_id": mount_asset_id,
            "mount_id": mount_id,
            "point_name": mount.point_name,
            "mount_location": mount.mount_location or "",
            "equipment_type": getattr(mount, "equipment_type", "") or "",
            "rpm": rpm,
            "rpm_source": rpm_source,
            "source_acceleration_stat": {
                "id": source_acc_stat.id,
                "timestamp": source_acc_stat.timestamp,
                "operating_mode": getattr(source_acc_stat, "operating_mode", None),
                "rms_only": source_acc_stat.rms_only,
            } if source_acc_stat else None,
        })

    if not vibration_twf:
        result["missing"].append("asset_wide_acceleration_twf_for_coupling_related_shaft_faults")
        result["reason"] = "No valid running acceleration TWF endpoints were available for coupling-related shaft fault detection."
        return result

    fs = fs_values[0] if fs_values else None
    if not fs:
        result["missing"].append("sampling_frequency_hz")
        result["reason"] = "Sampling frequency is missing for coupling-related shaft fault detection."
        return result

    unique_fs = {round(float(value), 6) for value in fs_values}
    if len(unique_fs) > 1:
        result["warnings"].append("Multiple sampling frequencies found across endpoints; coupling-related shaft detection uses the first valid fs.")

    rpm = rpm_values[0] if rpm_values else None
    if not rpm:
        result["missing"].append("rpm_raw_data_master_or_signal_processing_master")
        result["reason"] = "RPM is missing for coupling-related shaft fault detection."
        return result

    try:
        fault_time = max(timestamps) if timestamps else None
        diagnosis = detect_coupling_related_shaft_faults(
            vibration_twf=vibration_twf,
            sampling_frequency_hz=fs,
            rpm=rpm,
            asset_id=requested_asset_id,
            signal_type="acceleration",
            acceleration_unit=str(payload.get("acceleration_unit", "g")),
            integration_low_cut_hz=float(payload.get("integration_low_cut_hz", 0.2)),
            endpoint_metadata=endpoint_metadata,
            min_score=min_score,
            target_tolerance_pct=target_tolerance_pct,
            phase_data_available=_auto_bool(payload.get("phase_data_available"), False),
            alignment_confirmation_available=_auto_bool(payload.get("alignment_confirmation_available"), False),
            competing_unbalance_score=competing_unbalance_score,
            competing_looseness_score=competing_looseness_score,
            competing_hydraulic_pass_score=competing_hydraulic_pass_score,
        )

        possible_faults = []
        for fault in diagnosis.get("possible_faults") or []:
            possible_faults.append({
                **fault,
                "diagnostic_family": "coupling_related_shaft_fault",
                "fault_time": fault_time,
                "fault_timestamp": fault_time,
            })
        diagnosis["possible_faults"] = possible_faults
        diagnosis["primary_fault"] = possible_faults[0] if possible_faults else None

        result["result"] = "ok"
        result["rpm"] = rpm
        result["sampling_frequency_hz"] = fs
        result["fault_time"] = fault_time
        result["fault_timestamp"] = fault_time
        result["diagnosis"] = diagnosis
        return result
    except Exception as exc:
        result["result"] = "error"
        result["error"] = str(exc)
        result["traceback"] = traceback.format_exc()
        return result

def json_serializer(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    return str(obj)

def to_unix_timestamp(value):
    if not value:
        return None

    if isinstance(value, datetime):
        return int(value.timestamp())

    value = str(value).replace("Z", "+00:00")
    return int(datetime.fromisoformat(value).timestamp())

def build_fault_timeline(diagnostic_result):
    endpoint_timeline_map = {}

    for fault in diagnostic_result.get("possible_faults", []):
        ts = fault.get("fault_timestamp") or fault.get("fault_time")
        ts_unix = to_unix_timestamp(ts)
        if not ts_unix:
            continue

        endpoint_id = str(
            fault.get("mount_id")
            or fault.get("best_endpoint")
            or "asset_wide"
        )
        best_axis = fault.get("best_axis")
        fault_name = fault.get("label") or fault.get("family") or fault.get("fault")
        endpoint_details = fault.get("best_endpoint_details") or {}

        endpoint_bucket = endpoint_timeline_map.setdefault(
            endpoint_id,
            {
                "endpoint_id": endpoint_id,
                "mount_id": endpoint_details.get("mount_id") or (endpoint_id if endpoint_id != "asset_wide" else None),
                "composite_id": endpoint_details.get("composite_id") or fault.get("composite_id"),
                "point_name": endpoint_details.get("point_name") or fault.get("point_name"),
                "mount_location": endpoint_details.get("mount_location") or fault.get("mount_location"),
                "endpoint_display_name": endpoint_details.get("endpoint_display_name")
                                         or fault.get("best_endpoint_display_name")
                                         or (
                                             f"{(endpoint_details.get('point_name') or fault.get('point_name') or '').strip()} "
                                             f"{(endpoint_details.get('mount_location') or fault.get('mount_location') or '').strip()}"
                                         ).strip()
                                         or endpoint_id,
                "events_by_ts": {},
            },
        )

        event = endpoint_bucket["events_by_ts"].setdefault(
            ts_unix,
            {
                "timestamp_unix": ts_unix,
                "faults": [],
                "axes": [],
            },
        )
        if fault_name and fault_name not in event["faults"]:
            event["faults"].append(fault_name)
        if best_axis and best_axis not in event["axes"]:
            event["axes"].append(best_axis)

    timeline = []
    for endpoint in endpoint_timeline_map.values():
        events = sorted(endpoint["events_by_ts"].values(), key=lambda x: x["timestamp_unix"], reverse=True)
        timeline.append({
            "endpoint_id": endpoint["endpoint_id"],
            "mount_id": endpoint["mount_id"],
            "composite_id": endpoint["composite_id"],
            "point_name": endpoint["point_name"],
            "mount_location": endpoint["mount_location"],
            "endpoint_display_name": endpoint["endpoint_display_name"],
            "events": events,
        })

    timeline.sort(
        key=lambda x: x["events"][0]["timestamp_unix"] if x.get("events") else 0,
        reverse=True,
    )
    return timeline


def _v4_mount_details_map(mounts):
    details_map = {}
    for mount in mounts or []:
        mount_id = str(mount.id)
        point_name = str(mount.point_name or "").strip()
        mount_location = str(mount.mount_location or "").strip()
        details_map[mount_id] = {
            "mount_id": mount_id,
            "asset_id": str(mount.asset_id or "").strip(),
            "composite_id": str(getattr(mount, "composite_id", "") or "").strip() or None,
            "point_name": point_name or None,
            "mount_location": mount_location or None,
            "endpoint_display_name": (f"{point_name} {mount_location}".strip() or mount_id),
        }
    return details_map


def _v4_endpoint_details(endpoint_id, mount_details):
    if endpoint_id is None:
        return None
    key = str(endpoint_id)
    return dict(mount_details.get(key) or {}) if mount_details else None


def _v4_enrich_fault_with_endpoint_details(fault, mount_details, endpoint_timestamp_map=None):
    out = dict(fault or {})
    best_endpoint_id = out.get("best_endpoint")
    supporting_endpoints = list(out.get("supporting_endpoints") or [])

    best_details = _v4_endpoint_details(best_endpoint_id, mount_details)
    supporting_details = [d for d in (_v4_endpoint_details(eid, mount_details) for eid in supporting_endpoints) if d]

    if best_endpoint_id and not out.get("mount_id"):
        out["mount_id"] = str(best_endpoint_id)
    if best_details:
        out["best_endpoint_details"] = best_details
        out["best_endpoint_display_name"] = best_details.get("endpoint_display_name")
        out["composite_id"] = out.get("composite_id") or best_details.get("composite_id")
        out["point_name"] = out.get("point_name") or best_details.get("point_name")
        out["mount_location"] = out.get("mount_location") or best_details.get("mount_location")
    else:
        out.setdefault("best_endpoint_details", None)
        out.setdefault("best_endpoint_display_name", None)

    timestamp_endpoint_id = best_endpoint_id or out.get("mount_id")
    endpoint_fault_time = None
    if endpoint_timestamp_map and timestamp_endpoint_id is not None:
        endpoint_fault_time = endpoint_timestamp_map.get(str(timestamp_endpoint_id))
    if endpoint_fault_time:
        out["fault_time"] = endpoint_fault_time
        out["fault_timestamp"] = endpoint_fault_time

    out["supporting_endpoint_details"] = supporting_details
    return out


def generate_diagnostic_summary(diagnostic_result):
    print("----------------- Generating Diagnostic Summary using LLM ----------------")
    client_kwargs = {"region_name": BEDROCK_REGION}
    aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID") or getattr(settings, "AWS_ACCESS_KEY_ID", None)
    aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY") or getattr(settings, "AWS_SECRET_ACCESS_KEY", None)
    if aws_access_key_id and aws_secret_access_key:
        client_kwargs["aws_access_key_id"] = aws_access_key_id
        client_kwargs["aws_secret_access_key"] = aws_secret_access_key
    client = boto3.client("bedrock-runtime", **client_kwargs)

    diagnostic_json = json.dumps(
        diagnostic_result,
        indent=2,
        default=json_serializer
    )

    prompt = f"""
    You are a Senior Vibration Analyst, Reliability Engineer, and Predictive Maintenance Specialist with expertise in rotating machinery diagnostics, including motors, pumps, fans, gearboxes, compressors, bearings, couplings, and driven equipment.

    You are analyzing the output of an automated vibration diagnostics system. The diagnostic results may contain primary faults, supporting faults, bearing defect indications, confidence levels, severity levels, and recommended corrective actions.

    Your task is to convert the diagnostic results into a concise, professional maintenance report suitable for plant engineers, maintenance teams, reliability engineers, and industrial asset managers.

    Return ONLY valid JSON in the following schema:

        {{
        "overall_summary": "",
        "observations": [],
        "recommendations": [],
        "severity_assessment": "",
        "maintenance_priority": "",
        "fault_timeline": []
        }}

    Analysis Rules:

    Overall Summary
    Provide a clear explanation of the overall machine condition.
    Focus primarily on the highest-ranked fault.
    Mention supporting faults only when they strengthen or influence the primary diagnosis.
    Use plain industrial maintenance language.
    Limit to 2-4 concise paragraphs.
    Observations
    List the most important findings as bullet-style statements.
    Include primary fault, significant supporting faults, and any noteworthy machine-wide patterns.
    Mention bearing defects only when they have meaningful confidence or severity.
    Avoid repeating the same observation in different wording.
    Maximum 8 observations.
    Add the supporting findings from the input json, like markes responsible for that perticular faults that you list here.
    Recommendations
    Provide practical maintenance actions that can be performed by maintenance personnel.
    Prioritize actions related to the primary fault.
    Include inspection, verification, alignment, balancing, lubrication, mounting, structural, or bearing-related actions when relevant.
    Recommendations should be actionable and prioritized.
    Maximum 8 recommendations.
    Severity Assessment
    Select exactly one:
    Critical
    High
    Medium
    Low

    Severity Guidelines:

    Critical = Immediate risk of equipment damage or unplanned failure.
    High = Significant fault requiring maintenance planning in the near term.
    Medium = Degradation present but equipment can continue operating under monitoring.
    Low = Minor issue requiring observation only.
    Maintenance Priority
    Select exactly one:
    Immediate
    High
    Planned
    Monitor

    Priority Guidelines:

    Immediate = Action required at the earliest safe opportunity.
    High = Schedule maintenance soon.
    Planned = Include in the next planned maintenance window.
    Monitor = Continue condition monitoring and trend review.

    Important Restrictions:

    Do NOT mention vibration amplitudes, RMS values, frequencies, harmonics, spectral peaks, fault frequencies, endpoint IDs, mount IDs, sensor IDs, scores, ratios, or diagnostic calculations.
    Do NOT expose internal diagnostic logic.
    Do NOT mention confidence percentages.
    Do NOT mention competing fault scores.
    Do NOT generate technical vibration-analysis explanations.
    Convert technical findings into maintenance-focused language.
    Avoid speculation beyond the provided evidence.
    Keep the response concise, professional, and suitable for direct display in an industrial monitoring application.

    When multiple faults are present:

    Treat the highest-ranked fault as the primary diagnosis.
    Treat lower-ranked faults as supporting observations.
    Do not present all faults as equally important.
    Prioritize recommendations based on the most likely root cause.

    Diagnostic Result:
    {diagnostic_json}
    """
    system_prompt = """
                    Return ONLY valid JSON.

                    Schema:
                        {
                        "overall_summary": "",
                        "observations": [],
                        "recommendations": [],
                        "severity_assessment": "",
                        "maintenance_priority": ""
                        }
                    """

    response = client.converse(
        modelId=BEDROCK_MODEL_ID,
        system=[
            {
                "text": system_prompt
            }
        ],

        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "text": prompt
                    }
                ]
            }
        ],
        inferenceConfig={
            "maxTokens": 1000,
            "temperature": 0.2,
        },
    )

    result_text = ""
    for block in response.get("output", {}).get("message", {}).get("content", []):
        if "text" in block:
            result_text += block["text"] + "\n"
    result_text = result_text.strip()

    try:
        report = json.loads(result_text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", result_text, re.DOTALL)
        if not match:
            raise ValueError(f"Could not parse JSON from Bedrock response: {result_text}")
        report = json.loads(match.group(0))

    report["fault_timeline"] = build_fault_timeline(diagnostic_result)

    return report

def _v4_json_safe(value):
    return json.loads(json.dumps(value, default=json_serializer))


def save_asset_diagnostic_report(
    asset_id,
    response_data,
    diagnostic_input=None,
    trigger_source="api",
    alarm_history_id=None,
    alarm_queue_id=None,
    alarm_snapshot=None,
    status_override=None,
    error_message=None,
):
    response_data = response_data or {}
    report_json = response_data.get("message") if isinstance(response_data.get("message"), dict) else None
    result = int(response_data.get("result") or 0)
    report_status = status_override
    if report_status is None:
        report_status = "completed" if result == 1 and report_json else "no_faults"

    try:
        return models.AssetDiagnosticReportMaster.objects.create(
            asset_id=str(asset_id or "").strip() or None,
            trigger_source=trigger_source or "api",
            alarm_history_id=alarm_history_id,
            alarm_queue_id=alarm_queue_id,
            alarm_snapshot=_v4_json_safe(alarm_snapshot) if alarm_snapshot is not None else None,
            diagnostic_input=_v4_json_safe(diagnostic_input) if diagnostic_input is not None else None,
            report_json=_v4_json_safe(report_json) if report_json is not None else None,
            response_json=_v4_json_safe(response_data),
            result=result,
            status=report_status,
            error_message=error_message,
        )
    except Exception:
        logger.exception("Failed to save AssetDiagnosticsV4 report for asset_id=%s", asset_id)
        return None


def run_asset_diagnostics_v4(
    asset_id,
    payload=None,
    persist=False,
    trigger_source="api",
    alarm_history_id=None,
    alarm_queue_id=None,
    alarm_snapshot=None,
):
    payload = payload or {}
    asset_id = str(asset_id or payload.get("asset_id", "")).strip()
    if not asset_id:
        return {"result": 0, "message": "asset_id is required."}, status.HTTP_400_BAD_REQUEST, None, None

    try:
        print("-----before _auto_resolve_diagnostic_asset_ids----------")
        diagnostic_asset_ids = _auto_resolve_diagnostic_asset_ids(asset_id)
        print("------after _auto_resolve_diagnostic_asset_ids---------")
        child_asset_ids = [item for item in diagnostic_asset_ids if item != asset_id]
        mounts = list(
            DeviceMountMaster.objects
            .filter(asset_id__in=diagnostic_asset_ids)
            .order_by("asset_id", "id")
        )
        print("------------------------mounts----------------------", mounts)
        if not mounts:
            response_data = {
                "result": 0,
                "message": f"No mounts found for asset_id={asset_id} or its child assets.",
                "requested_asset_id": asset_id,
                "diagnostic_asset_ids": diagnostic_asset_ids,
                "child_asset_ids": child_asset_ids,
            }
            report_obj = None
            if persist:
                report_obj = save_asset_diagnostic_report(
                    asset_id,
                    response_data,
                    trigger_source=trigger_source,
                    alarm_history_id=alarm_history_id,
                    alarm_queue_id=alarm_queue_id,
                    alarm_snapshot=alarm_snapshot,
                    status_override="failed",
                    error_message=response_data["message"],
                )
            return response_data, status.HTTP_404_NOT_FOUND, None, report_obj

        mount_runtime_context_map = _v4_build_mount_runtime_context_map(mounts)
        print("----------------mounts-----------------", mounts)
        mount_results = []
        for mount in mounts:
            mount_result = _v4_diagnose_mount_impact(
                mount,
                payload,
                mount_runtime_context=mount_runtime_context_map.get(str(mount.id)),
            )
            mount_results.append(mount_result)
        aggregate = _v4_aggregate_impact_mount_results(mount_results)

        mechanical_looseness = _v4_diagnose_mechanical_looseness(
            mounts,
            payload,
            asset_id,
            mount_runtime_context_map=mount_runtime_context_map,
        )

        unbalance = _v4_diagnose_unbalance(
            mounts,
            payload,
            asset_id,
            mount_runtime_context_map=mount_runtime_context_map,
        )

        hydraulic_vane_blade_pass = _v4_diagnose_hydraulic_vane_blade_pass(
            mounts,
            payload,
            asset_id,
            mount_runtime_context_map=mount_runtime_context_map,
        )
        hydraulic_pass_score = _v4_primary_family_score(hydraulic_vane_blade_pass)
        cavitation_or_aeration = _v4_diagnose_cavitation_or_aeration(
            mounts,
            payload,
            asset_id,
            competing_hydraulic_pass_score=hydraulic_pass_score,
            mount_runtime_context_map=mount_runtime_context_map,
        )
        misalignment = _v4_diagnose_misalignment(
            mounts,
            payload,
            asset_id,
            competing_hydraulic_pass_score=hydraulic_pass_score,
            mount_runtime_context_map=mount_runtime_context_map,
        )
        bent_shaft = _v4_diagnose_bent_shaft(
            mounts,
            payload,
            asset_id,
            mount_runtime_context_map=mount_runtime_context_map,
        )
        coupling_related_shaft = _v4_diagnose_coupling_related_shaft(
            mounts,
            payload,
            asset_id,
            competing_unbalance_score=_v4_primary_family_score(unbalance),
            competing_looseness_score=_v4_primary_family_score(mechanical_looseness),
            competing_hydraulic_pass_score=hydraulic_pass_score or _v4_max_fault_score(
                aggregate,
                ["hydraulic_vane_or_blade_pass", "cavitation_or_aeration"],
            ),
            mount_runtime_context_map=mount_runtime_context_map,
        )
        overall_faults = list(aggregate.get("possible_faults") or [])
        overall_faults.extend((mechanical_looseness.get("diagnosis") or {}).get("possible_faults") or [])
        overall_faults.extend((unbalance.get("diagnosis") or {}).get("possible_faults") or [])
        overall_faults.extend((hydraulic_vane_blade_pass.get("diagnosis") or {}).get("possible_faults") or [])
        overall_faults.extend((cavitation_or_aeration.get("diagnosis") or {}).get("possible_faults") or [])
        overall_faults.extend((misalignment.get("diagnosis") or {}).get("possible_faults") or [])
        overall_faults.extend((bent_shaft.get("diagnosis") or {}).get("possible_faults") or [])
        overall_faults.extend((coupling_related_shaft.get("diagnosis") or {}).get("possible_faults") or [])
        overall_faults.sort(key=lambda row: float(row.get("score") or 0.0), reverse=True)
        mount_details_map = _v4_mount_details_map(mounts)
        endpoint_timestamp_map = _v4_endpoint_fault_timestamp_map(mount_runtime_context_map)
        overall_faults = [
            _v4_enrich_fault_with_endpoint_details(fault, mount_details_map, endpoint_timestamp_map)
            for fault in overall_faults
        ]
        # overall_faults = [ row for row in overall_faults if float(row.get("score") or 0.0) > 50 ]
        ok_count = sum(1 for row in mount_results if row.get("result") == "ok")
        skipped_count = sum(1 for row in mount_results if row.get("result") == "skipped")
        error_count = sum(1 for row in mount_results if row.get("result") == "error")

        if len(overall_faults) > 0:

            diagnostic_json = {
                    "result": 1,
                    "requested_asset_id": asset_id,
                    "diagnostic_scope": "asset_tree_mountwise_impact_and_assetwide_shaft_faults",
                    "diagnostic_asset_ids": diagnostic_asset_ids,
                    "child_asset_ids": child_asset_ids,
                    "total_mounts": len(mounts),
                    "processed": len(mount_results),
                    "ok": ok_count,
                    "skipped": skipped_count,
                    "errors": error_count,
                    "primary_fault": overall_faults[0] if overall_faults else None,
                    "possible_faults": overall_faults[:5] if len(overall_faults) > 5 else overall_faults,
                    # "impact_family": aggregate,
                    # "mechanical_looseness_family": mechanical_looseness,
                    # "unbalance_family": unbalance,
                    # "misalignment_family": misalignment,
                    # "bent_shaft_family": bent_shaft,
                    # "mounts": mount_results,
                }
            print("--------------------------------diagnostic_json done------------------------------")
            formatted_response = generate_diagnostic_summary(diagnostic_json)
            if not isinstance(formatted_response.get("fault_timeline"), list):
                formatted_response["fault_timeline"] = []
            response_data = {
                "result": 1,
                "message": formatted_response,
                # "requested_asset_id": asset_id,
                # "diagnostic_scope": "asset_tree_mountwise_impact_and_assetwide_shaft_faults",
                # "diagnostic_asset_ids": diagnostic_asset_ids,
                # "child_asset_ids": child_asset_ids,
                "total_mounts": len(mounts),
                "processed": len(mount_results),
                # "ok": ok_count,
                # "skipped": skipped_count,
                # "errors": error_count,
                # "primary_fault": overall_faults[0] if overall_faults else None,
                # "possible_faults": overall_faults,
                # "impact_family": aggregate,
                # "mechanical_looseness_family": mechanical_looseness,
                # "unbalance_family": unbalance,
                # "misalignment_family": misalignment,
                # "bent_shaft_family": bent_shaft,
                # "mounts": mount_results,
            }
            report_obj = None
            if persist:
                report_obj = save_asset_diagnostic_report(
                    asset_id,
                    response_data,
                    diagnostic_input=diagnostic_json,
                    trigger_source=trigger_source,
                    alarm_history_id=alarm_history_id,
                    alarm_queue_id=alarm_queue_id,
                    alarm_snapshot=alarm_snapshot,
                )
            return response_data, status.HTTP_200_OK, diagnostic_json, report_obj
        else:
            response_data = {
                "result": 0,
                "total_mounts": len(mounts),
                "processed": len(mount_results),
                "message": "Analysis completed successfully. No abnormal vibration patterns or fault signatures were identified."
            }
            report_obj = None
            if persist:
                report_obj = save_asset_diagnostic_report(
                    asset_id,
                    response_data,
                    trigger_source=trigger_source,
                    alarm_history_id=alarm_history_id,
                    alarm_queue_id=alarm_queue_id,
                    alarm_snapshot=alarm_snapshot,
                    status_override="no_faults",
                )
            return response_data, status.HTTP_200_OK, None, report_obj
    except Exception as exc:
        if persist:
            save_asset_diagnostic_report(
                asset_id,
                {"result": 0, "message": "Asset diagnostics failed."},
                trigger_source=trigger_source,
                alarm_history_id=alarm_history_id,
                alarm_queue_id=alarm_queue_id,
                alarm_snapshot=alarm_snapshot,
                status_override="failed",
                error_message=str(exc),
            )
        raise


class AssetDiagnosticsV4(APIView):

    def post(self, request):
        payload = request.data or {}
        response_data, response_status, _diagnostic_input, _report_obj = run_asset_diagnostics_v4(
            payload.get("asset_id"),
            payload=payload,
            persist=True,
            trigger_source="api",
        )
        return Response(response_data, status=response_status)


def _diagnostic_test_timestamp(value):
    if isinstance(value, datetime):
        return value if value.tzinfo else pytz.UTC.localize(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else pytz.UTC.localize(parsed)
        except Exception:
            pass
    return timezone.now()


class TestAssetDiagnosticsAlarmFlow(APIView):
    """
    Test endpoint for the real alarm-triggered diagnostics path.

    POST body example:
    {
      "asset_id": "asset123",
      "mount_id": "45",
      "axis": "Vertical",
      "signal_type": "acceleration",
      "stat_function": "rms",
      "level": "3",
      "threshold_value": 1.0,
      "observed_value": 2.5,
      "bypass_mail_suppression": true
    }
    """

    def post(self, request):
        payload = request.data or {}
        asset_id = str(payload.get("asset_id") or "").strip()
        mount_id = str(payload.get("mount_id") or "").strip()
        composite = str(payload.get("composite") or "").strip()

        if not asset_id:
            return Response(
                {"result": 0, "message": "asset_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        mount = None
        if mount_id:
            mount = DeviceMountMaster.objects.filter(id=mount_id, asset_id=asset_id).first()
        elif composite:
            mount = DeviceMountMaster.objects.filter(composite_id=composite, asset_id=asset_id).first()

        if mount is None:
            return Response(
                {
                    "result": 0,
                    "message": "A valid mount_id or composite for the supplied asset_id is required.",
                    "asset_id": asset_id,
                    "mount_id": mount_id or None,
                    "composite": composite or None,
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        mount_id = str(mount.id)
        composite = composite or mount.composite_id or f"{mount.mac_id}_{mount_id}"
        axis = str(payload.get("axis") or "Vertical").strip().title()
        signal_type = str(payload.get("signal_type") or "acceleration").strip().lower()
        stat_function = str(payload.get("stat_function") or "rms").strip().lower()
        level = str(payload.get("level") or "3").strip()
        if level not in {"1", "2", "3"}:
            return Response(
                {"result": 0, "message": "level must be one of '1', '2', or '3'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            threshold_value = float(payload.get("threshold_value", 1.0))
            observed_value = float(payload.get("observed_value", threshold_value + 1.0))
            repetition = int(payload.get("repetition", 1))
            counter_value = int(payload.get("counter_value", repetition))
        except (TypeError, ValueError):
            return Response(
                {"result": 0, "message": "threshold_value, observed_value, repetition, and counter_value must be numeric."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if repetition <= 0:
            repetition = 1
        if counter_value <= 0:
            counter_value = repetition

        domain = str(payload.get("domain") or "time").strip().lower()
        if payload.get("bypass_mail_suppression", True):
            domain_for_counter = f"{domain}_diagnostic_test_{uuid.uuid4().hex[:8]}"
        else:
            domain_for_counter = domain

        timestamp = _diagnostic_test_timestamp(payload.get("timestamp"))
        timestamp_param = f"{stat_function}_amp_repetition_level_{level}_timestamp"
        counter_param = f"{stat_function}_amp_counter_level_{level}"
        repetition_param = f"{stat_function}_amp_repetition_level_{level}"
        threshold_param = f"{stat_function}_amp_level_{level}"
        comp_key = f"{mount_id}-{axis}-{signal_type}-{domain_for_counter}"

        threshold_values = {
            "composite": composite,
            "axis": axis,
            "signal_type": signal_type,
            "domain": domain_for_counter,
            threshold_param: threshold_value,
        }
        counter_values = {
            counter_param: counter_value,
            repetition_param: repetition,
            timestamp_param: timestamp.isoformat(),
        }
        stat_values = {
            "composite": composite,
            "asset_id": asset_id,
            "mount_id": mount_id,
            "timestamp": timestamp,
            stat_function: observed_value,
        }

        from app.task import updateDbSendMail

        updateDbSendMail(
            counter_value,
            repetition,
            comp_key,
            counter_values,
            counter_param,
            threshold_values,
            stat_function,
            stat_values,
            timestamp_param,
            level,
        )

        latest_alarm = (
            models.AlarmHistoryMaster.objects
            .filter(asset_id=asset_id, composite=composite, trend_type=f"{stat_function}_amp")
            .order_by("-creation_date")
            .first()
        )

        return Response(
            {
                "result": 1,
                "message": "Alarm diagnostics flow triggered. Check Celery workers and asset_diagnostic_report_master for the diagnostic result.",
                "asset_id": asset_id,
                "mount_id": mount_id,
                "composite": composite,
                "comp_key": comp_key,
                "alarm_history_id": getattr(latest_alarm, "id", None),
                "queued_mail_and_diagnostics": True,
                "bypass_mail_suppression": bool(payload.get("bypass_mail_suppression", True)),
                "payload_used": {
                    "axis": axis,
                    "signal_type": signal_type,
                    "stat_function": stat_function,
                    "level": level,
                    "threshold_value": threshold_value,
                    "observed_value": observed_value,
                    "repetition": repetition,
                    "counter_value": counter_value,
                    "timestamp": timestamp.isoformat(),
                },
            },
            status=status.HTTP_200_OK,
        )
