from datetime import datetime, timedelta
from app import models
from app import serializers
import json
import pdb
from django.db.models import Q

# statfunctionList = ['rms','peak','peak_to_peak','kurtosis']
signalType = ['acceleration','velocity','displacement']
axes = ['x','y','z']
statfunctionList = ['rms','peak','peak_to_peak','kurtosis','one_amp','two_amp','three_amp','four_amp']
previousDay = datetime.now() - timedelta(days=1)


def calculateIndividualScore():
    for signal in signalType:
        for axis in axes:
            for statfn in statfunctionList:
                kwargs = {'{0}'.format(statfn): None}
                final_data = {"axis":axis, "signal_type": signal}
                allThresholdValues = models.ThresholdValues.objects.filter(signal_type=signal, axis=axis).filter(~Q(**kwargs))
                for singlethresholdData in allThresholdValues:
                    if getattr(singlethresholdData, statfn) != None:
                        if signal == "acceleration":
                            previousDaySignalData = models.AccelerationStatTimeMaster.objects.filter(timestamp__date=previousDay, axis=axis, composite=singlethresholdData.composite)
                        elif signal == "velocity":
                            previousDaySignalData = models.VelocityStatTimeMaster.objects.filter(timestamp__date=previousDay, axis=axis, composite=singlethresholdData.composite)
                        elif signal == "displacement":
                            previousDaySignalData = models.DisplacementStatTimeMaster.objects.filter(timestamp__date=previousDay, axis=axis, composite=singlethresholdData.composite)
                        else:
                            pass
                        total_statfns_count = len(previousDaySignalData)
                        StatFnskwargs = {
                            '{0}__{1}'.format(statfn, 'gte'): getattr(singlethresholdData, statfn),
                        }
                        filteredData = previousDaySignalData.filter(**StatFnskwargs)
                        flagged_statfns_count = len(filteredData)
                        try:
                            statfns_score = (total_statfns_count-flagged_statfns_count)/total_statfns_count
                        except:
                            pass
                        if len(previousDaySignalData) > 0:
                            final_data.update({statfn:round(statfns_score,2),"composite": singlethresholdData.composite.composite_id,"asset_id":singlethresholdData.asset_id, "timestamp":previousDaySignalData[0].timestamp})
                            existingScore = models.KPIScoreMaster.objects.filter(axis=axis,signal_type=signal,composite=singlethresholdData.composite,timestamp=previousDaySignalData[0].timestamp).first()
                            if not existingScore:
                                scoreSerializer = serializers.KPIScoreMasterSerializer(data=final_data, partial=True)
                                if scoreSerializer.is_valid():
                                    scoreSerializer.save()
                            else:
                                if getattr(existingScore, statfn) == None:
                                    updateData = {statfn:round(statfns_score,2)}
                                    KPIScoreMaster = serializers.KPIScoreMasterSerializer(instance=existingScore, data=updateData, partial=True)
                                    if KPIScoreMaster.is_valid():
                                        KPIScoreMaster.save()
                                else:
                                    pass
                        else:
                            return None

def calculateCombinedScore():

    uniqueAssetList = models.KPIScoreMaster.objects.filter(timestamp__date=previousDay).values("asset_id").distinct()
    for asset in uniqueAssetList:
        SingleAssetKpiScores = models.KPIScoreMaster.objects.filter(timestamp__date=previousDay, asset_id=asset.get("asset_id"))
        for row in SingleAssetKpiScores:
            assetLowestScore = 2
            rowScore = 0
            counter = 0
            for statfn in statfunctionList:
                if getattr(row, statfn) != None:
                    rowScore += getattr(row, statfn)
                    counter += 1
            finalScore = round(rowScore/counter,2)
            if finalScore <= assetLowestScore:
                assetLowestScore = finalScore

    return None























