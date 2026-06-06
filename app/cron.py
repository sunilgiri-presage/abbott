from datetime import datetime, timedelta
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
from .cache import redis_client_rms_batch
from rest_framework.decorators import api_view
from django.db import transaction


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

        # PRE-FETCH ALL MOUNTS — with validation
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


