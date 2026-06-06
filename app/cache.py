from django.db import connection
import redis
import json
from app import models

# Configure Redis connection live
redis_client_mount = redis.StrictRedis(host='localhost', port=6379, db=2)
redis_client_orientation = redis.StrictRedis(host='localhost', port=6379, db=3)
redis_client_threshold = redis.StrictRedis(host='localhost', port=6379, db=4)
redis_client_threshold_counter = redis.StrictRedis(host='localhost', port=6379, db=5)
redis_client_rms_batch = redis.StrictRedis(host='localhost', port=6379, db=7, decode_responses=True)
redis_client_alarm_timestamp = redis.StrictRedis(host='localhost', port=6379, db=11, decode_responses=False)

# Configure Redis connection test
# redis_client_mount_test = redis.StrictRedis(host='localhost', port=6379, db=6)
# redis_client_orientation_test = redis.StrictRedis(host='localhost', port=6379, db=7)
# redis_client_threshold_test = redis.StrictRedis(host='localhost', port=6379, db=8)
# redis_client_threshold_counter_test = redis.StrictRedis(host='localhost', port=6379, db=9)


######################################## Save device mount master in cache ########################################
def load_mount_data_mapping():
    redis_client_mount.flushdb()   # clearing existing database to load updated mapping 
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM device_mount_master where is_linked=True")
        mappings = cursor.fetchall()
        for id, composite_id, is_linked, point_name, mount_location, mount_type, mount_material, mount_direction, creation_date, asset_id, org_id, mac_id, image, last_update, online, timezone in mappings:
            data = json.dumps({
                "id" : id, 
                "composite_id" : composite_id, 
                "is_linked" : is_linked, 
                "point_name" : point_name, 
                "mount_location" : mount_location, 
                "mount_type" : mount_type, 
                "mount_material" : mount_material, 
                "mount_direction" : mount_direction, 
                "creation_date" : creation_date.isoformat() if creation_date else None, 
                "asset_id" : asset_id, 
                "org_id" : org_id, 
                "mac_id" : mac_id, 
                "image" : image, 
                "last_update" : last_update.isoformat() if last_update else None, 
                "online" : online
                })
            redis_client_mount.set(mac_id, data)  # Store each mac_id as key with asset_id as value
        return mappings

def get_mount_data(mac_id):
    mount_data = redis_client_mount.get(mac_id)
    if mount_data:
        return json.loads(mount_data.decode("utf-8"))  # Redis returns bytes, so decode it
    else:
        try:
            mapping = models.DeviceMountMaster.objects.get(mac_id=mac_id, is_linked=True)
            data = json.dumps({
                    "id" : mapping.id, 
                    "composite_id" : mapping.composite_id, 
                    "is_linked" : mapping.is_linked, 
                    "point_name" : mapping.point_name, 
                    "mount_location" : mapping.mount_location, 
                    "mount_type" : mapping.mount_type, 
                    "mount_material" : mapping.mount_material, 
                    "mount_direction" : mapping.mount_direction, 
                    "creation_date" : mapping.creation_date.isoformat() if mapping.creation_date else None, 
                    "asset_id" : mapping.asset_id, 
                    "org_id" : mapping.org_id, 
                    "mac_id" : mapping.mac_id, 
                    "image" : mapping.image, 
                    "last_update" : mapping.last_update.isoformat() if mapping.last_update else None, 
                    "online" : mapping.online
                    })
            redis_client_mount.set(mac_id, data)
            mount_data_2 = redis_client_mount.get(mac_id)
            if mount_data_2:
                return json.loads(mount_data_2.decode("utf-8"))  # Redis returns bytes, so decode it
            else:
                return None
        except Exception as e1:
            print("some exception in get_mount_data for sensor ", mac_id, e1)
            return None


######################################## Save device orientation in cache ########################################
def load_sensor_orientation_mapping():
    redis_client_orientation.flushdb()   # clearing existing database to load updated sensor orientations 
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM sensor_position_master")
        mappings = cursor.fetchall()
        for id, sensor_type, orientation, last_update in mappings:
            data = json.dumps({
                "id" : id, 
                "sensor_type" : sensor_type, 
                "orientation" : orientation, 
                "last_update" : last_update.isoformat() if last_update else None, 
                })
            redis_client_orientation.set(sensor_type, data)  # Store each sensor type as key with data as value
        return mappings
    

def get_sensor_orientation_data(sensor_type, sensorOrientation, axis):
    sensor_data = redis_client_orientation.get(sensor_type)
    if sensor_data:
        decoded_data = json.loads(sensor_data.decode("utf-8"))  # Redis returns bytes, so decode it
        orient_data = json.loads(decoded_data.get("orientation"))
        axisOrientation = orient_data.get(sensorOrientation).get(axis)
        return axisOrientation
    else:
        try:
            mapping = models.SensorPositionMaster.objects.get(sensor_type=sensor_type)
            sensor_data = json.dumps({
                    "id" : mapping.id, 
                    "sensor_type" : sensor_type, 
                    "orientation" : mapping.orientation, 
                    "last_update" : mapping.last_update.isoformat() if mapping.last_update else None, 
                    })
            redis_client_orientation.set(sensor_type, sensor_data)  # Store it in Redis for future lookups
            sensor_data_2 = redis_client_orientation.get(sensor_type)
            if sensor_data_2:
                decoded_data = json.loads(sensor_data_2.decode("utf-8"))  # Redis returns bytes, so decode it
                orient_data = json.loads(decoded_data.get("orientation"))
                axisOrientation = orient_data.get(sensorOrientation).get(axis)
                return axisOrientation
            else:
                return None
        except Exception as e2:
            print("some exception in get_sensor_orientation_data for sensor type", sensor_type, e2)
            return None

######################################## get orientation data for rms only function via mqtt ########################################
def get_sensor_orientation_data_rms_only(sensor_type, sensorOrientation):
    try:
        sensor_data = redis_client_orientation.get(sensor_type)
        if sensor_data:
            decoded_data = json.loads(sensor_data.decode("utf-8"))  # Redis returns bytes, so decode it
            orient_data = json.loads(decoded_data.get("orientation"))
            axisOrientation = orient_data.get(sensorOrientation)
            return axisOrientation
    except Exception as e3:
        print("some exception in get_sensor_orientation_data_rms_only for sensor type", sensor_type, e3)




######################################## Save composite id threshold values master in cache ########################################
def load_threshold_data_mapping():
    redis_client_threshold.flushdb()   # clearing existing database to load updated mapping 
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT 
                id, composite, rms_amp_level_1, peak_amp_level_1, peak_to_peak_amp_level_1, kurtosis_amp_level_1,
                one_amp_level_1, two_amp_level_1, three_amp_level_1, four_amp_level_1, temp_amp_level_1,
                rms_amp_level_2, peak_amp_level_2, peak_to_peak_amp_level_2, kurtosis_amp_level_2,
                one_amp_level_2, two_amp_level_2, three_amp_level_2, four_amp_level_2, temp_amp_level_2,
                rms_amp_level_3, peak_amp_level_3, peak_to_peak_amp_level_3, kurtosis_amp_level_3,
                one_amp_level_3, two_amp_level_3, three_amp_level_3, four_amp_level_3, temp_amp_level_3,
                axis, signal_type, domain, asset_id, creation_date, mount_id, last_update
            FROM threshold_values
        """)
        thresholdValues = cursor.fetchall()
        # for id, composite_id, is_linked, point_name, mount_location, mount_type, mount_material, mount_direction, creation_date, asset_id, org_id, mac_id, image, last_update, online in mappings:
        for id, composite, rms_amp_level_1, peak_amp_level_1, peak_to_peak_amp_level_1, kurtosis_amp_level_1, \
            one_amp_level_1, two_amp_level_1, three_amp_level_1, four_amp_level_1, temp_amp_level_1, \
            rms_amp_level_2, peak_amp_level_2, peak_to_peak_amp_level_2, kurtosis_amp_level_2, \
            one_amp_level_2, two_amp_level_2, three_amp_level_2, four_amp_level_2, temp_amp_level_2, \
            rms_amp_level_3, peak_amp_level_3, peak_to_peak_amp_level_3, kurtosis_amp_level_3, \
            one_amp_level_3, two_amp_level_3, three_amp_level_3, four_amp_level_3, temp_amp_level_3, \
            axis, signal_type, domain, asset_id, creation_date, mount_id, last_update in thresholdValues:
            data = json.dumps({
                "id": id,
                "rms_amp_level_1": float(rms_amp_level_1),
                "peak_amp_level_1": float(peak_amp_level_1),
                "peak_to_peak_amp_level_1": float(peak_to_peak_amp_level_1),
                "kurtosis_amp_level_1": float(kurtosis_amp_level_1),
                "one_amp_level_1": float(one_amp_level_1),
                "two_amp_level_1": float(two_amp_level_1),
                "three_amp_level_1": float(three_amp_level_1),
                "four_amp_level_1": float(four_amp_level_1),
                "rms_amp_level_2": float(rms_amp_level_2),
                "peak_amp_level_2": float(peak_amp_level_2),
                "peak_to_peak_amp_level_2": float(peak_to_peak_amp_level_2),
                "kurtosis_amp_level_2": float(kurtosis_amp_level_2),
                "one_amp_level_2": float(one_amp_level_2),
                "two_amp_level_2": float(two_amp_level_2),
                "three_amp_level_2": float(three_amp_level_2),
                "four_amp_level_2": float(four_amp_level_2),
                "rms_amp_level_3": float(rms_amp_level_3),
                "peak_amp_level_3": float(peak_amp_level_3),
                "peak_to_peak_amp_level_3": float(peak_to_peak_amp_level_3),
                "kurtosis_amp_level_3": float(kurtosis_amp_level_3),
                "one_amp_level_3": float(one_amp_level_3),
                "two_amp_level_3": float(two_amp_level_3),
                "three_amp_level_3": float(three_amp_level_3),
                "four_amp_level_3": float(four_amp_level_3),
                "axis": axis,
                "signal_type": signal_type,
                "domain": domain,
                "asset_id": asset_id,
                "creation_date": creation_date.isoformat() if creation_date else None,
                "mount_id": mount_id,
                "composite": composite,
                "temp_amp_level_1": float(temp_amp_level_1),
                "temp_amp_level_2": float(temp_amp_level_2),
                "temp_amp_level_3": float(temp_amp_level_3),
                "last_update": last_update.isoformat() if last_update else None
                })
            comp_key = str(mount_id) + '-' + str(axis) + '-' + str(signal_type) + '-' + str(domain)
            redis_client_threshold.set(comp_key, data)
        return thresholdValues
    

def get_threshold_data(mount_id, axis, signal_type, domain):
    comp_key = str(mount_id) + '-' + str(axis) + '-' + str(signal_type) + '-' + str(domain)
    threshold_data = redis_client_threshold.get(comp_key)
    if threshold_data:
        return json.loads(threshold_data.decode("utf-8"))  # Redis returns bytes, so decode it
    else:
        try:
            # mapping = models.DeviceMountMaster.objects.get(mac_id=composite, is_linked=True)
            thresh = models.ThresholdValues.objects.get(mount_id=mount_id, axis=axis, signal_type=signal_type, domain=domain)
            data = json.dumps({
                        "id" : thresh.id, 
                        "composite" : thresh.composite,
                        "rms_amp_level_1" : float(thresh.rms_amp_level_1),
                        "peak_amp_level_1" : float(thresh.peak_amp_level_1),
                        "peak_to_peak_amp_level_1" : float(thresh.peak_to_peak_amp_level_1),
                        "kurtosis_amp_level_1" : float(thresh.kurtosis_amp_level_1),
                        "one_amp_level_1" : float(thresh.one_amp_level_1),
                        "two_amp_level_1" : float(thresh.two_amp_level_1),
                        "three_amp_level_1" : float(thresh.three_amp_level_1),
                        "four_amp_level_1" : float(thresh.four_amp_level_1),
                        "temp_amp_level_1" : float(thresh.temp_amp_level_1),
                        "rms_amp_level_2" : float(thresh.rms_amp_level_2),
                        "peak_amp_level_2" : float(thresh.peak_amp_level_2),
                        "peak_to_peak_amp_level_2" : float(thresh.peak_to_peak_amp_level_2),
                        "kurtosis_amp_level_2" : float(thresh.kurtosis_amp_level_2),
                        "one_amp_level_2" : float(thresh.one_amp_level_2),
                        "two_amp_level_2" : float(thresh.two_amp_level_2),
                        "three_amp_level_2" : float(thresh.three_amp_level_2),
                        "four_amp_level_2" : float(thresh.four_amp_level_2),
                        "temp_amp_level_2" : float(thresh.temp_amp_level_2),
                        "rms_amp_level_3" : float(thresh.rms_amp_level_3),
                        "peak_amp_level_3" : float(thresh.peak_amp_level_3),
                        "peak_to_peak_amp_level_3" : float(thresh.peak_to_peak_amp_level_3),
                        "kurtosis_amp_level_3" : float(thresh.kurtosis_amp_level_3),
                        "one_amp_level_3" : float(thresh.one_amp_level_3),
                        "two_amp_level_3" : float(thresh.two_amp_level_3),
                        "three_amp_level_3" : float(thresh.three_amp_level_3),
                        "four_amp_level_3" : float(thresh.four_amp_level_3),
                        "temp_amp_level_3" : float(thresh.temp_amp_level_3),
                        "axis" : thresh.axis,
                        "signal_type" : thresh.signal_type,
                        "domain" : thresh.domain,
                        "asset_id" : thresh.asset_id,
                        "creation_date" : thresh.creation_date.isoformat() if thresh.creation_date else None,
                        "last_update" : thresh.last_update.isoformat() if thresh.last_update else None
                    })
            redis_client_threshold.set(comp_key, data)
            thresh_data_2 = redis_client_threshold.get(comp_key)
            if thresh_data_2:
                return json.loads(thresh_data_2.decode("utf-8"))  # Redis returns bytes, so decode it
            else:
                return None
        except:
            return None
        

######################################## Save composite id threshold counter master in cache ########################################
def load_threshold_counter_data_mapping():
    redis_client_threshold_counter.flushdb()   # clearing existing database to load updated mapping 
    with connection.cursor() as cursor:
        cursor.execute("""SELECT 
            id,
            composite,
            rms_amp_repetition_level_1,
            rms_amp_counter_level_1,
            peak_amp_repetition_level_1,
            peak_amp_counter_level_1,
            peak_to_peak_amp_repetition_level_1,
            peak_to_peak_amp_counter_level_1,
            kurtosis_amp_repetition_level_1,
            kurtosis_amp_counter_level_1,
            one_amp_repetition_level_1,
            one_amp_counter_level_1,
            two_amp_repetition_level_1,
            two_amp_counter_level_1,
            three_amp_repetition_level_1,
            three_amp_counter_level_1,
            four_amp_repetition_level_1,
            four_amp_counter_level_1,
            temp_amp_repetition_level_1,
            temp_amp_counter_level_1,
            rms_amp_repetition_level_2,
            rms_amp_counter_level_2,
            peak_amp_repetition_level_2,
            peak_amp_counter_level_2,
            peak_to_peak_amp_repetition_level_2,
            peak_to_peak_amp_counter_level_2,
            kurtosis_amp_repetition_level_2,
            kurtosis_amp_counter_level_2,
            one_amp_repetition_level_2,
            one_amp_counter_level_2,
            two_amp_repetition_level_2,
            two_amp_counter_level_2,
            three_amp_repetition_level_2,
            three_amp_counter_level_2,
            four_amp_repetition_level_2,
            four_amp_counter_level_2,
            temp_amp_repetition_level_2,
            temp_amp_counter_level_2,
            rms_amp_repetition_level_3,
            rms_amp_counter_level_3,
            peak_amp_repetition_level_3,
            peak_amp_counter_level_3,
            peak_to_peak_amp_repetition_level_3,
            peak_to_peak_amp_counter_level_3,
            kurtosis_amp_repetition_level_3,
            kurtosis_amp_counter_level_3,
            one_amp_repetition_level_3,
            one_amp_counter_level_3,
            two_amp_repetition_level_3,
            two_amp_counter_level_3,
            three_amp_repetition_level_3,
            three_amp_counter_level_3,
            four_amp_repetition_level_3,
            four_amp_counter_level_3,
            temp_amp_repetition_level_3,
            temp_amp_counter_level_3,
            axis,
            signal_type,
            domain,
            asset_id,
            creation_date,
            last_update,
            rms_amp_repetition_level_1_timestamp,
            peak_amp_repetition_level_1_timestamp,
            peak_to_peak_amp_repetition_level_1_timestamp,
            kurtosis_amp_repetition_level_1_timestamp,
            one_amp_repetition_level_1_timestamp,
            two_amp_repetition_level_1_timestamp,
            three_amp_repetition_level_1_timestamp,
            four_amp_repetition_level_1_timestamp,
            temp_amp_repetition_level_1_timestamp,
            rms_amp_repetition_level_2_timestamp,
            peak_amp_repetition_level_2_timestamp,
            peak_to_peak_amp_repetition_level_2_timestamp,
            kurtosis_amp_repetition_level_2_timestamp,
            one_amp_repetition_level_2_timestamp,
            two_amp_repetition_level_2_timestamp,
            three_amp_repetition_level_2_timestamp,
            four_amp_repetition_level_2_timestamp,
            temp_amp_repetition_level_2_timestamp,
            rms_amp_repetition_level_3_timestamp,
            peak_amp_repetition_level_3_timestamp,
            peak_to_peak_amp_repetition_level_3_timestamp,
            kurtosis_amp_repetition_level_3_timestamp,
            one_amp_repetition_level_3_timestamp,
            two_amp_repetition_level_3_timestamp,
            three_amp_repetition_level_3_timestamp,
            four_amp_repetition_level_3_timestamp,
            temp_amp_repetition_level_3_timestamp,
            mount_id,
            values
        FROM threshold_counter_master""")
        thresh_counter = cursor.fetchall()
        try:
            for id, composite, rms_amp_repetition_level_1, rms_amp_counter_level_1, peak_amp_repetition_level_1, peak_amp_counter_level_1, peak_to_peak_amp_repetition_level_1, \
                peak_to_peak_amp_counter_level_1, kurtosis_amp_repetition_level_1, kurtosis_amp_counter_level_1, one_amp_repetition_level_1, one_amp_counter_level_1, \
                    two_amp_repetition_level_1, two_amp_counter_level_1, three_amp_repetition_level_1, three_amp_counter_level_1, four_amp_repetition_level_1, \
                        four_amp_counter_level_1, temp_amp_repetition_level_1, temp_amp_counter_level_1, rms_amp_repetition_level_2, rms_amp_counter_level_2, \
                            peak_amp_repetition_level_2, peak_amp_counter_level_2, peak_to_peak_amp_repetition_level_2, peak_to_peak_amp_counter_level_2, \
                                kurtosis_amp_repetition_level_2, kurtosis_amp_counter_level_2, one_amp_repetition_level_2, one_amp_counter_level_2, \
                                    two_amp_repetition_level_2, two_amp_counter_level_2, three_amp_repetition_level_2, three_amp_counter_level_2, \
                                        four_amp_repetition_level_2, four_amp_counter_level_2, temp_amp_repetition_level_2, temp_amp_counter_level_2, \
                                            rms_amp_repetition_level_3, rms_amp_counter_level_3, peak_amp_repetition_level_3, peak_amp_counter_level_3, \
                                                peak_to_peak_amp_repetition_level_3, peak_to_peak_amp_counter_level_3, kurtosis_amp_repetition_level_3, \
                                                    kurtosis_amp_counter_level_3, one_amp_repetition_level_3, one_amp_counter_level_3, two_amp_repetition_level_3, \
                                                        two_amp_counter_level_3, three_amp_repetition_level_3, three_amp_counter_level_3, four_amp_repetition_level_3, \
                                                            four_amp_counter_level_3, temp_amp_repetition_level_3, temp_amp_counter_level_3, axis, signal_type, \
                                                                domain, asset_id, creation_date, last_update, rms_amp_repetition_level_1_timestamp, \
                                                                    peak_amp_repetition_level_1_timestamp, peak_to_peak_amp_repetition_level_1_timestamp, \
                                                                        kurtosis_amp_repetition_level_1_timestamp, one_amp_repetition_level_1_timestamp, \
                                                                            two_amp_repetition_level_1_timestamp, three_amp_repetition_level_1_timestamp, \
                                                                                four_amp_repetition_level_1_timestamp, temp_amp_repetition_level_1_timestamp, \
                                                                                    rms_amp_repetition_level_2_timestamp, peak_amp_repetition_level_2_timestamp, \
                                                                                        peak_to_peak_amp_repetition_level_2_timestamp, kurtosis_amp_repetition_level_2_timestamp, \
                                                                                            one_amp_repetition_level_2_timestamp, two_amp_repetition_level_2_timestamp, \
                                                                                                three_amp_repetition_level_2_timestamp, four_amp_repetition_level_2_timestamp, \
                                                                                                    temp_amp_repetition_level_2_timestamp, rms_amp_repetition_level_3_timestamp, \
                                                                                                        peak_amp_repetition_level_3_timestamp, peak_to_peak_amp_repetition_level_3_timestamp, \
                                                                                                            kurtosis_amp_repetition_level_3_timestamp, one_amp_repetition_level_3_timestamp, \
                                                                                                                two_amp_repetition_level_3_timestamp, three_amp_repetition_level_3_timestamp, \
                                                                                                                    four_amp_repetition_level_3_timestamp, temp_amp_repetition_level_3_timestamp, \
                                                                                                                        mount_id, values in thresh_counter:
                data = json.dumps({
                    "id": id,
                    "composite": composite,
                    "rms_amp_repetition_level_1": float(rms_amp_repetition_level_1),
                    "rms_amp_counter_level_1": float(rms_amp_counter_level_1),
                    "peak_amp_repetition_level_1": float(peak_amp_repetition_level_1),
                    "peak_amp_counter_level_1": float(peak_amp_counter_level_1),
                    "peak_to_peak_amp_repetition_level_1": float(peak_to_peak_amp_repetition_level_1),
                    "peak_to_peak_amp_counter_level_1": float(peak_to_peak_amp_counter_level_1),
                    "kurtosis_amp_repetition_level_1": float(kurtosis_amp_repetition_level_1),
                    "kurtosis_amp_counter_level_1": float(kurtosis_amp_counter_level_1),
                    "one_amp_repetition_level_1": float(one_amp_repetition_level_1),
                    "one_amp_counter_level_1": float(one_amp_counter_level_1),
                    "two_amp_repetition_level_1": float(two_amp_repetition_level_1),
                    "two_amp_counter_level_1": float(two_amp_counter_level_1),
                    "three_amp_repetition_level_1": float(three_amp_repetition_level_1),
                    "three_amp_counter_level_1": float(three_amp_counter_level_1),
                    "four_amp_repetition_level_1": float(four_amp_repetition_level_1),
                    "four_amp_counter_level_1": float(four_amp_counter_level_1),
                    "temp_amp_repetition_level_1": float(temp_amp_repetition_level_1),
                    "temp_amp_counter_level_1": float(temp_amp_counter_level_1),
                    "rms_amp_repetition_level_2": float(rms_amp_repetition_level_2),
                    "rms_amp_counter_level_2": float(rms_amp_counter_level_2),
                    "peak_amp_repetition_level_2": float(peak_amp_repetition_level_2),
                    "peak_amp_counter_level_2": float(peak_amp_counter_level_2),
                    "peak_to_peak_amp_repetition_level_2": float(peak_to_peak_amp_repetition_level_2),
                    "peak_to_peak_amp_counter_level_2": float(peak_to_peak_amp_counter_level_2),
                    "kurtosis_amp_repetition_level_2": float(kurtosis_amp_repetition_level_2),
                    "kurtosis_amp_counter_level_2": float(kurtosis_amp_counter_level_2),
                    "one_amp_repetition_level_2": float(one_amp_repetition_level_2),
                    "one_amp_counter_level_2": float(one_amp_counter_level_2),
                    "two_amp_repetition_level_2": float(two_amp_repetition_level_2),
                    "two_amp_counter_level_2": float(two_amp_counter_level_2),
                    "three_amp_repetition_level_2": float(three_amp_repetition_level_2),
                    "three_amp_counter_level_2": float(three_amp_counter_level_2),
                    "four_amp_repetition_level_2": float(four_amp_repetition_level_2),
                    "four_amp_counter_level_2": float(four_amp_counter_level_2),
                    "temp_amp_repetition_level_2": float(temp_amp_repetition_level_2),
                    "temp_amp_counter_level_2": float(temp_amp_counter_level_2),
                    "rms_amp_repetition_level_3": float(rms_amp_repetition_level_3),
                    "rms_amp_counter_level_3": float(rms_amp_counter_level_3),
                    "peak_amp_repetition_level_3": float(peak_amp_repetition_level_3),
                    "peak_amp_counter_level_3": float(peak_amp_counter_level_3),
                    "peak_to_peak_amp_repetition_level_3": float(peak_to_peak_amp_repetition_level_3),
                    "peak_to_peak_amp_counter_level_3": float(peak_to_peak_amp_counter_level_3),
                    "kurtosis_amp_repetition_level_3": float(kurtosis_amp_repetition_level_3),
                    "kurtosis_amp_counter_level_3": float(kurtosis_amp_counter_level_3),
                    "one_amp_repetition_level_3": float(one_amp_repetition_level_3),
                    "one_amp_counter_level_3": float(one_amp_counter_level_3),
                    "two_amp_repetition_level_3": float(two_amp_repetition_level_3),
                    "two_amp_counter_level_3": float(two_amp_counter_level_3),
                    "three_amp_repetition_level_3": float(three_amp_repetition_level_3),
                    "three_amp_counter_level_3": float(three_amp_counter_level_3),
                    "four_amp_repetition_level_3": float(four_amp_repetition_level_3),
                    "four_amp_counter_level_3": float(four_amp_counter_level_3),
                    "temp_amp_repetition_level_3": float(temp_amp_repetition_level_3),
                    "temp_amp_counter_level_3": float(temp_amp_counter_level_3),
                    "axis": axis,
                    "signal_type": signal_type,
                    "domain": domain,
                    "asset_id": asset_id,
                    "creation_date": creation_date.isoformat() if creation_date else None,
                    "last_update": last_update.isoformat() if last_update else None,
                    "rms_amp_repetition_level_1_timestamp": rms_amp_repetition_level_1_timestamp.isoformat() if rms_amp_repetition_level_1_timestamp else None,
                    "peak_amp_repetition_level_1_timestamp": peak_amp_repetition_level_1_timestamp.isoformat() if peak_amp_repetition_level_1_timestamp else None,
                    "peak_to_peak_amp_repetition_level_1_timestamp": peak_to_peak_amp_repetition_level_1_timestamp.isoformat() if peak_to_peak_amp_repetition_level_1_timestamp else None,
                    "kurtosis_amp_repetition_level_1_timestamp": kurtosis_amp_repetition_level_1_timestamp.isoformat() if kurtosis_amp_repetition_level_1_timestamp else None,
                    "one_amp_repetition_level_1_timestamp": one_amp_repetition_level_1_timestamp.isoformat() if one_amp_repetition_level_1_timestamp else None,
                    "two_amp_repetition_level_1_timestamp": two_amp_repetition_level_1_timestamp.isoformat() if two_amp_repetition_level_1_timestamp else None,
                    "three_amp_repetition_level_1_timestamp": three_amp_repetition_level_1_timestamp.isoformat() if three_amp_repetition_level_1_timestamp else None,
                    "four_amp_repetition_level_1_timestamp": four_amp_repetition_level_1_timestamp.isoformat() if four_amp_repetition_level_1_timestamp else None,
                    "temp_amp_repetition_level_1_timestamp": temp_amp_repetition_level_1_timestamp.isoformat() if temp_amp_repetition_level_1_timestamp else None,
                    "rms_amp_repetition_level_2_timestamp": rms_amp_repetition_level_2_timestamp.isoformat() if rms_amp_repetition_level_2_timestamp else None,
                    "peak_amp_repetition_level_2_timestamp": peak_amp_repetition_level_2_timestamp.isoformat() if peak_amp_repetition_level_2_timestamp else None,
                    "peak_to_peak_amp_repetition_level_2_timestamp": peak_to_peak_amp_repetition_level_2_timestamp.isoformat() if peak_to_peak_amp_repetition_level_2_timestamp else None,
                    "kurtosis_amp_repetition_level_2_timestamp": kurtosis_amp_repetition_level_2_timestamp.isoformat() if kurtosis_amp_repetition_level_2_timestamp else None,
                    "one_amp_repetition_level_2_timestamp": one_amp_repetition_level_2_timestamp.isoformat() if one_amp_repetition_level_2_timestamp else None,
                    "two_amp_repetition_level_2_timestamp": two_amp_repetition_level_2_timestamp.isoformat() if two_amp_repetition_level_2_timestamp else None,
                    "three_amp_repetition_level_2_timestamp": three_amp_repetition_level_2_timestamp.isoformat() if three_amp_repetition_level_2_timestamp else None,
                    "four_amp_repetition_level_2_timestamp": four_amp_repetition_level_2_timestamp.isoformat() if four_amp_repetition_level_2_timestamp else None,
                    "temp_amp_repetition_level_2_timestamp": temp_amp_repetition_level_2_timestamp.isoformat() if temp_amp_repetition_level_2_timestamp else None,
                    "rms_amp_repetition_level_3_timestamp": rms_amp_repetition_level_3_timestamp.isoformat() if rms_amp_repetition_level_3_timestamp else None,
                    "peak_amp_repetition_level_3_timestamp": peak_amp_repetition_level_3_timestamp.isoformat() if peak_amp_repetition_level_3_timestamp else None,
                    "peak_to_peak_amp_repetition_level_3_timestamp": peak_to_peak_amp_repetition_level_3_timestamp.isoformat() if peak_to_peak_amp_repetition_level_3_timestamp else None,
                    "kurtosis_amp_repetition_level_3_timestamp": kurtosis_amp_repetition_level_3_timestamp.isoformat() if kurtosis_amp_repetition_level_3_timestamp else None,
                    "one_amp_repetition_level_3_timestamp": one_amp_repetition_level_3_timestamp.isoformat() if one_amp_repetition_level_3_timestamp else None,
                    "two_amp_repetition_level_3_timestamp": two_amp_repetition_level_3_timestamp.isoformat() if two_amp_repetition_level_3_timestamp else None,
                    "three_amp_repetition_level_3_timestamp": three_amp_repetition_level_3_timestamp.isoformat() if three_amp_repetition_level_3_timestamp else None,
                    "four_amp_repetition_level_3_timestamp": four_amp_repetition_level_3_timestamp.isoformat() if four_amp_repetition_level_3_timestamp else None,
                    "temp_amp_repetition_level_3_timestamp": temp_amp_repetition_level_3_timestamp.isoformat() if temp_amp_repetition_level_3_timestamp else None,
                    "mount_id": mount_id,
                    "values": json.loads(values) if values else None
                    })
                comp_key = str(mount_id) + '-' + str(axis) + '-' + str(signal_type) + '-' + str(domain)
                redis_client_threshold_counter.set(comp_key, data) 
        except Exception as e:
            print("------some exception in threshold counter------", e)
        return thresh_counter
    


def get_threshold_counter_data(mount_id, axis, signal_type, domain):
    comp_key = str(mount_id) + '-' + str(axis) + '-' + str(signal_type) + '-' + str(domain)
    thresh_count_data = redis_client_threshold_counter.get(comp_key)
    if thresh_count_data:
        return json.loads(thresh_count_data.decode("utf-8"))  # Redis returns bytes, so decode it
    else:
        try:
            thresh_counter_data = models.ThresholdCounterMaster.objects.get(composite=mount_id, axis=axis, signal_type=signal_type, domain=domain)
            data = json.dumps({
                    "id": thresh_counter_data.id, 
                    'composite': thresh_counter_data.composite,
                    'rms_amp_repetition_level_1': float(thresh_counter_data.rms_amp_repetition_level_1),
                    'rms_amp_counter_level_1': float(thresh_counter_data.rms_amp_counter_level_1),
                    'peak_amp_repetition_level_1': float(thresh_counter_data.peak_amp_repetition_level_1),
                    'peak_amp_counter_level_1': float(thresh_counter_data.peak_amp_counter_level_1),
                    'peak_to_peak_amp_repetition_level_1': float(thresh_counter_data.peak_to_peak_amp_repetition_level_1),
                    'peak_to_peak_amp_counter_level_1': float(thresh_counter_data.peak_to_peak_amp_counter_level_1),
                    'kurtosis_amp_repetition_level_1': float(thresh_counter_data.kurtosis_amp_repetition_level_1),
                    'kurtosis_amp_counter_level_1': float(thresh_counter_data.kurtosis_amp_counter_level_1),
                    'one_amp_repetition_level_1': float(thresh_counter_data.one_amp_repetition_level_1),
                    'one_amp_counter_level_1': float(thresh_counter_data.one_amp_counter_level_1),
                    'two_amp_repetition_level_1': float(thresh_counter_data.two_amp_repetition_level_1),
                    'two_amp_counter_level_1': float(thresh_counter_data.two_amp_counter_level_1),
                    'three_amp_repetition_level_1': float(thresh_counter_data.three_amp_repetition_level_1),
                    'three_amp_counter_level_1': float(thresh_counter_data.three_amp_counter_level_1),
                    'four_amp_repetition_level_1': float(thresh_counter_data.four_amp_repetition_level_1),
                    'four_amp_counter_level_1': float(thresh_counter_data.four_amp_counter_level_1),
                    'temp_amp_repetition_level_1': float(thresh_counter_data.temp_amp_repetition_level_1),
                    'temp_amp_counter_level_1': float(thresh_counter_data.temp_amp_counter_level_1),
                    'rms_amp_repetition_level_2': float(thresh_counter_data.rms_amp_repetition_level_2),
                    'rms_amp_counter_level_2': float(thresh_counter_data.rms_amp_counter_level_2),
                    'peak_amp_repetition_level_2': float(thresh_counter_data.peak_amp_repetition_level_2),
                    'peak_amp_counter_level_2': float(thresh_counter_data.peak_amp_counter_level_2),
                    'peak_to_peak_amp_repetition_level_2': float(thresh_counter_data.peak_to_peak_amp_repetition_level_2),
                    'peak_to_peak_amp_counter_level_2': float(thresh_counter_data.peak_to_peak_amp_counter_level_2),
                    'kurtosis_amp_repetition_level_2': float(thresh_counter_data.kurtosis_amp_repetition_level_2),
                    'kurtosis_amp_counter_level_2': float(thresh_counter_data.kurtosis_amp_counter_level_2),
                    'one_amp_repetition_level_2': float(thresh_counter_data.one_amp_repetition_level_2),
                    'one_amp_counter_level_2': float(thresh_counter_data.one_amp_counter_level_2),
                    'two_amp_repetition_level_2': float(thresh_counter_data.two_amp_repetition_level_2),
                    'two_amp_counter_level_2': float(thresh_counter_data.two_amp_counter_level_2),
                    'three_amp_repetition_level_2': float(thresh_counter_data.three_amp_repetition_level_2),
                    'three_amp_counter_level_2': float(thresh_counter_data.three_amp_counter_level_2),
                    'four_amp_repetition_level_2': float(thresh_counter_data.four_amp_repetition_level_2),
                    'four_amp_counter_level_2': float(thresh_counter_data.four_amp_counter_level_2),
                    'temp_amp_repetition_level_2': float(thresh_counter_data.temp_amp_repetition_level_2),
                    'temp_amp_counter_level_2': float(thresh_counter_data.temp_amp_counter_level_2),
                    'rms_amp_repetition_level_3': float(thresh_counter_data.rms_amp_repetition_level_3),
                    'rms_amp_counter_level_3': float(thresh_counter_data.rms_amp_counter_level_3),
                    'peak_amp_repetition_level_3': float(thresh_counter_data.peak_amp_repetition_level_3),
                    'peak_amp_counter_level_3': float(thresh_counter_data.peak_amp_counter_level_3),
                    'peak_to_peak_amp_repetition_level_3': float(thresh_counter_data.peak_to_peak_amp_repetition_level_3),
                    'peak_to_peak_amp_counter_level_3': float(thresh_counter_data.peak_to_peak_amp_counter_level_3),
                    'kurtosis_amp_repetition_level_3': float(thresh_counter_data.kurtosis_amp_repetition_level_3),
                    'kurtosis_amp_counter_level_3': float(thresh_counter_data.kurtosis_amp_counter_level_3),
                    'one_amp_repetition_level_3': float(thresh_counter_data.one_amp_repetition_level_3),
                    'one_amp_counter_level_3': float(thresh_counter_data.one_amp_counter_level_3),
                    'two_amp_repetition_level_3': float(thresh_counter_data.two_amp_repetition_level_3),
                    'two_amp_counter_level_3': float(thresh_counter_data.two_amp_counter_level_3),
                    'three_amp_repetition_level_3': float(thresh_counter_data.three_amp_repetition_level_3),
                    'three_amp_counter_level_3': float(thresh_counter_data.three_amp_counter_level_3),
                    'four_amp_repetition_level_3': float(thresh_counter_data.four_amp_repetition_level_3),
                    'four_amp_counter_level_3': float(thresh_counter_data.four_amp_counter_level_3),
                    'temp_amp_repetition_level_3': float(thresh_counter_data.temp_amp_repetition_level_3),
                    'temp_amp_counter_level_3': float(thresh_counter_data.temp_amp_counter_level_3),
                    'axis': thresh_counter_data.axis,
                    'signal_type': thresh_counter_data.signal_type,
                    'domain': thresh_counter_data.domain,
                    'asset_id': thresh_counter_data.asset_id,
                    'creation_date': thresh_counter_data.creation_date.isoformat() if thresh_counter_data.creation_date else None,
                    'last_update': thresh_counter_data.last_update.isoformat() if thresh_counter_data.last_update else None,
                    'rms_amp_repetition_level_1_timestamp': thresh_counter_data.rms_amp_repetition_level_1_timestamp.isoformat() if thresh_counter_data.rms_amp_repetition_level_1_timestamp else None,
                    'peak_amp_repetition_level_1_timestamp': thresh_counter_data.peak_amp_repetition_level_1_timestamp.isoformat() if thresh_counter_data.peak_amp_repetition_level_1_timestamp else None,
                    'peak_to_peak_amp_repetition_level_1_timestamp': thresh_counter_data.peak_to_peak_amp_repetition_level_1_timestamp.isoformat() if thresh_counter_data.peak_to_peak_amp_repetition_level_1_timestamp else None,
                    'kurtosis_amp_repetition_level_1_timestamp': thresh_counter_data.kurtosis_amp_repetition_level_1_timestamp.isoformat() if thresh_counter_data.kurtosis_amp_repetition_level_1_timestamp else None,
                    'one_amp_repetition_level_1_timestamp': thresh_counter_data.one_amp_repetition_level_1_timestamp.isoformat() if thresh_counter_data.one_amp_repetition_level_1_timestamp else None,
                    'two_amp_repetition_level_1_timestamp': thresh_counter_data.two_amp_repetition_level_1_timestamp.isoformat() if thresh_counter_data.two_amp_repetition_level_1_timestamp else None,
                    'three_amp_repetition_level_1_timestamp': thresh_counter_data.three_amp_repetition_level_1_timestamp.isoformat() if thresh_counter_data.three_amp_repetition_level_1_timestamp else None,
                    'four_amp_repetition_level_1_timestamp': thresh_counter_data.four_amp_repetition_level_1_timestamp.isoformat() if thresh_counter_data.four_amp_repetition_level_1_timestamp else None,
                    'temp_amp_repetition_level_1_timestamp': thresh_counter_data.temp_amp_repetition_level_1_timestamp.isoformat() if thresh_counter_data.temp_amp_repetition_level_1_timestamp else None,
                    'rms_amp_repetition_level_2_timestamp': thresh_counter_data.rms_amp_repetition_level_2_timestamp.isoformat() if thresh_counter_data.rms_amp_repetition_level_2_timestamp else None,
                    'peak_amp_repetition_level_2_timestamp': thresh_counter_data.peak_amp_repetition_level_2_timestamp.isoformat() if thresh_counter_data.peak_amp_repetition_level_2_timestamp else None,
                    'peak_to_peak_amp_repetition_level_2_timestamp': thresh_counter_data.peak_to_peak_amp_repetition_level_2_timestamp.isoformat() if thresh_counter_data.peak_to_peak_amp_repetition_level_2_timestamp else None,
                    'kurtosis_amp_repetition_level_2_timestamp': thresh_counter_data.kurtosis_amp_repetition_level_2_timestamp.isoformat() if thresh_counter_data.kurtosis_amp_repetition_level_2_timestamp else None,
                    'one_amp_repetition_level_2_timestamp': thresh_counter_data.one_amp_repetition_level_2_timestamp.isoformat() if thresh_counter_data.one_amp_repetition_level_2_timestamp else None,
                    'two_amp_repetition_level_2_timestamp': thresh_counter_data.two_amp_repetition_level_2_timestamp.isoformat() if thresh_counter_data.two_amp_repetition_level_2_timestamp else None,
                    'three_amp_repetition_level_2_timestamp': thresh_counter_data.three_amp_repetition_level_2_timestamp.isoformat() if thresh_counter_data.three_amp_repetition_level_2_timestamp else None,
                    'four_amp_repetition_level_2_timestamp': thresh_counter_data.four_amp_repetition_level_2_timestamp.isoformat() if thresh_counter_data.four_amp_repetition_level_2_timestamp else None,
                    'temp_amp_repetition_level_2_timestamp': thresh_counter_data.temp_amp_repetition_level_2_timestamp.isoformat() if thresh_counter_data.temp_amp_repetition_level_2_timestamp else None,
                    'rms_amp_repetition_level_3_timestamp': thresh_counter_data.rms_amp_repetition_level_3_timestamp.isoformat() if thresh_counter_data.rms_amp_repetition_level_3_timestamp else None,
                    'peak_amp_repetition_level_3_timestamp': thresh_counter_data.peak_amp_repetition_level_3_timestamp.isoformat() if thresh_counter_data.peak_amp_repetition_level_3_timestamp else None,
                    'peak_to_peak_amp_repetition_level_3_timestamp': thresh_counter_data.peak_to_peak_amp_repetition_level_3_timestamp.isoformat() if thresh_counter_data.peak_to_peak_amp_repetition_level_3_timestamp else None,
                    'kurtosis_amp_repetition_level_3_timestamp': thresh_counter_data.kurtosis_amp_repetition_level_3_timestamp.isoformat() if thresh_counter_data.kurtosis_amp_repetition_level_3_timestamp else None,
                    'one_amp_repetition_level_3_timestamp': thresh_counter_data.one_amp_repetition_level_3_timestamp.isoformat() if thresh_counter_data.one_amp_repetition_level_3_timestamp else None,
                    'two_amp_repetition_level_3_timestamp': thresh_counter_data.two_amp_repetition_level_3_timestamp.isoformat() if thresh_counter_data.two_amp_repetition_level_3_timestamp else None,
                    'three_amp_repetition_level_3_timestamp': thresh_counter_data.three_amp_repetition_level_3_timestamp.isoformat() if thresh_counter_data.three_amp_repetition_level_3_timestamp else None,
                    'four_amp_repetition_level_3_timestamp': thresh_counter_data.four_amp_repetition_level_3_timestamp.isoformat() if thresh_counter_data.four_amp_repetition_level_3_timestamp else None,
                    'temp_amp_repetition_level_3_timestamp': thresh_counter_data.temp_amp_repetition_level_3_timestamp.isoformat() if thresh_counter_data.temp_amp_repetition_level_3_timestamp else None,
                    'values': json.loads(thresh_counter_data.values),
                    })
            redis_client_threshold_counter.set(comp_key, data)
            thresh_count_data2 = redis_client_threshold_counter.get(comp_key)
            if thresh_count_data2:
                return json.loads(thresh_count_data2.decode("utf-8"))  # Redis returns bytes, so decode it
            else:
                return None
        except:
            return None


def updateThreshCounterDB(comp_key, counter_obj):
    try:
        redis_client_threshold_counter.set(comp_key, json.dumps(counter_obj))
    except Exception as e:
        return {"status": False, "message": "Something wrong with counter update function {}".format(e)}


########################################UPDATE THRESHOLD AND COUNTER DATA NEW LOGIC########################################
def update_threshold_data_mapping_key(redis_key, mount_id, axis, signal_type, domain):
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT 
                id, composite, rms_amp_level_1, peak_amp_level_1, peak_to_peak_amp_level_1, kurtosis_amp_level_1,
                one_amp_level_1, two_amp_level_1, three_amp_level_1, four_amp_level_1, temp_amp_level_1,
                rms_amp_level_2, peak_amp_level_2, peak_to_peak_amp_level_2, kurtosis_amp_level_2,
                one_amp_level_2, two_amp_level_2, three_amp_level_2, four_amp_level_2, temp_amp_level_2,
                rms_amp_level_3, peak_amp_level_3, peak_to_peak_amp_level_3, kurtosis_amp_level_3,
                one_amp_level_3, two_amp_level_3, three_amp_level_3, four_amp_level_3, temp_amp_level_3,
                axis, signal_type, domain, asset_id, creation_date, mount_id, last_update
            FROM threshold_values
            WHERE mount_id = %s AND axis = %s AND signal_type = %s AND domain = %s
        """, [mount_id, axis, signal_type, domain])
        thresholdValue = cursor.fetchone()
        
        if thresholdValue:
            id, composite, rms_amp_level_1, peak_amp_level_1, peak_to_peak_amp_level_1, kurtosis_amp_level_1, \
            one_amp_level_1, two_amp_level_1, three_amp_level_1, four_amp_level_1, temp_amp_level_1, \
            rms_amp_level_2, peak_amp_level_2, peak_to_peak_amp_level_2, kurtosis_amp_level_2, \
            one_amp_level_2, two_amp_level_2, three_amp_level_2, four_amp_level_2, temp_amp_level_2, \
            rms_amp_level_3, peak_amp_level_3, peak_to_peak_amp_level_3, kurtosis_amp_level_3, \
            one_amp_level_3, two_amp_level_3, three_amp_level_3, four_amp_level_3, temp_amp_level_3, \
            axis, signal_type, domain, asset_id, creation_date, mount_id, last_update = thresholdValue
            
            data = json.dumps({
                "id": id,
                "rms_amp_level_1": float(rms_amp_level_1),
                "peak_amp_level_1": float(peak_amp_level_1),
                "peak_to_peak_amp_level_1": float(peak_to_peak_amp_level_1),
                "kurtosis_amp_level_1": float(kurtosis_amp_level_1),
                "one_amp_level_1": float(one_amp_level_1),
                "two_amp_level_1": float(two_amp_level_1),
                "three_amp_level_1": float(three_amp_level_1),
                "four_amp_level_1": float(four_amp_level_1),
                "rms_amp_level_2": float(rms_amp_level_2),
                "peak_amp_level_2": float(peak_amp_level_2),
                "peak_to_peak_amp_level_2": float(peak_to_peak_amp_level_2),
                "kurtosis_amp_level_2": float(kurtosis_amp_level_2),
                "one_amp_level_2": float(one_amp_level_2),
                "two_amp_level_2": float(two_amp_level_2),
                "three_amp_level_2": float(three_amp_level_2),
                "four_amp_level_2": float(four_amp_level_2),
                "rms_amp_level_3": float(rms_amp_level_3),
                "peak_amp_level_3": float(peak_amp_level_3),
                "peak_to_peak_amp_level_3": float(peak_to_peak_amp_level_3),
                "kurtosis_amp_level_3": float(kurtosis_amp_level_3),
                "one_amp_level_3": float(one_amp_level_3),
                "two_amp_level_3": float(two_amp_level_3),
                "three_amp_level_3": float(three_amp_level_3),
                "four_amp_level_3": float(four_amp_level_3),
                "axis": axis,
                "signal_type": signal_type,
                "domain": domain,
                "asset_id": asset_id,
                "creation_date": creation_date.isoformat() if creation_date else None,
                "mount_id": mount_id,
                "composite": composite,
                "temp_amp_level_1": float(temp_amp_level_1),
                "temp_amp_level_2": float(temp_amp_level_2),
                "temp_amp_level_3": float(temp_amp_level_3),
                "last_update": last_update.isoformat() if last_update else None
                })
            redis_client_threshold.set(redis_key, data)


def update_threshold_counter_data_mapping_key(redis_key, mount_id, axis, signal_type, domain):
    """Update specific threshold counter data key in Redis instead of full reload"""
    with connection.cursor() as cursor:
        cursor.execute("""SELECT 
            id,
            composite,
            rms_amp_repetition_level_1,
            rms_amp_counter_level_1,
            peak_amp_repetition_level_1,
            peak_amp_counter_level_1,
            peak_to_peak_amp_repetition_level_1,
            peak_to_peak_amp_counter_level_1,
            kurtosis_amp_repetition_level_1,
            kurtosis_amp_counter_level_1,
            one_amp_repetition_level_1,
            one_amp_counter_level_1,
            two_amp_repetition_level_1,
            two_amp_counter_level_1,
            three_amp_repetition_level_1,
            three_amp_counter_level_1,
            four_amp_repetition_level_1,
            four_amp_counter_level_1,
            temp_amp_repetition_level_1,
            temp_amp_counter_level_1,
            rms_amp_repetition_level_2,
            rms_amp_counter_level_2,
            peak_amp_repetition_level_2,
            peak_amp_counter_level_2,
            peak_to_peak_amp_repetition_level_2,
            peak_to_peak_amp_counter_level_2,
            kurtosis_amp_repetition_level_2,
            kurtosis_amp_counter_level_2,
            one_amp_repetition_level_2,
            one_amp_counter_level_2,
            two_amp_repetition_level_2,
            two_amp_counter_level_2,
            three_amp_repetition_level_2,
            three_amp_counter_level_2,
            four_amp_repetition_level_2,
            four_amp_counter_level_2,
            temp_amp_repetition_level_2,
            temp_amp_counter_level_2,
            rms_amp_repetition_level_3,
            rms_amp_counter_level_3,
            peak_amp_repetition_level_3,
            peak_amp_counter_level_3,
            peak_to_peak_amp_repetition_level_3,
            peak_to_peak_amp_counter_level_3,
            kurtosis_amp_repetition_level_3,
            kurtosis_amp_counter_level_3,
            one_amp_repetition_level_3,
            one_amp_counter_level_3,
            two_amp_repetition_level_3,
            two_amp_counter_level_3,
            three_amp_repetition_level_3,
            three_amp_counter_level_3,
            four_amp_repetition_level_3,
            four_amp_counter_level_3,
            temp_amp_repetition_level_3,
            temp_amp_counter_level_3,
            axis,
            signal_type,
            domain,
            asset_id,
            creation_date,
            last_update,
            rms_amp_repetition_level_1_timestamp,
            peak_amp_repetition_level_1_timestamp,
            peak_to_peak_amp_repetition_level_1_timestamp,
            kurtosis_amp_repetition_level_1_timestamp,
            one_amp_repetition_level_1_timestamp,
            two_amp_repetition_level_1_timestamp,
            three_amp_repetition_level_1_timestamp,
            four_amp_repetition_level_1_timestamp,
            temp_amp_repetition_level_1_timestamp,
            rms_amp_repetition_level_2_timestamp,
            peak_amp_repetition_level_2_timestamp,
            peak_to_peak_amp_repetition_level_2_timestamp,
            kurtosis_amp_repetition_level_2_timestamp,
            one_amp_repetition_level_2_timestamp,
            two_amp_repetition_level_2_timestamp,
            three_amp_repetition_level_2_timestamp,
            four_amp_repetition_level_2_timestamp,
            temp_amp_repetition_level_2_timestamp,
            rms_amp_repetition_level_3_timestamp,
            peak_amp_repetition_level_3_timestamp,
            peak_to_peak_amp_repetition_level_3_timestamp,
            kurtosis_amp_repetition_level_3_timestamp,
            one_amp_repetition_level_3_timestamp,
            two_amp_repetition_level_3_timestamp,
            three_amp_repetition_level_3_timestamp,
            four_amp_repetition_level_3_timestamp,
            temp_amp_repetition_level_3_timestamp,
            mount_id,
            values
        FROM threshold_counter_master
        WHERE mount_id = %s AND axis = %s AND signal_type = %s AND domain = %s
        """, [mount_id, axis, signal_type, domain])
        
        thresh_counter_record = cursor.fetchone()
        
        if thresh_counter_record:
            try:
                id, composite, rms_amp_repetition_level_1, rms_amp_counter_level_1, peak_amp_repetition_level_1, peak_amp_counter_level_1, peak_to_peak_amp_repetition_level_1, \
                peak_to_peak_amp_counter_level_1, kurtosis_amp_repetition_level_1, kurtosis_amp_counter_level_1, one_amp_repetition_level_1, one_amp_counter_level_1, \
                    two_amp_repetition_level_1, two_amp_counter_level_1, three_amp_repetition_level_1, three_amp_counter_level_1, four_amp_repetition_level_1, \
                        four_amp_counter_level_1, temp_amp_repetition_level_1, temp_amp_counter_level_1, rms_amp_repetition_level_2, rms_amp_counter_level_2, \
                            peak_amp_repetition_level_2, peak_amp_counter_level_2, peak_to_peak_amp_repetition_level_2, peak_to_peak_amp_counter_level_2, \
                                kurtosis_amp_repetition_level_2, kurtosis_amp_counter_level_2, one_amp_repetition_level_2, one_amp_counter_level_2, \
                                    two_amp_repetition_level_2, two_amp_counter_level_2, three_amp_repetition_level_2, three_amp_counter_level_2, \
                                        four_amp_repetition_level_2, four_amp_counter_level_2, temp_amp_repetition_level_2, temp_amp_counter_level_2, \
                                            rms_amp_repetition_level_3, rms_amp_counter_level_3, peak_amp_repetition_level_3, peak_amp_counter_level_3, \
                                                peak_to_peak_amp_repetition_level_3, peak_to_peak_amp_counter_level_3, kurtosis_amp_repetition_level_3, \
                                                    kurtosis_amp_counter_level_3, one_amp_repetition_level_3, one_amp_counter_level_3, two_amp_repetition_level_3, \
                                                        two_amp_counter_level_3, three_amp_repetition_level_3, three_amp_counter_level_3, four_amp_repetition_level_3, \
                                                            four_amp_counter_level_3, temp_amp_repetition_level_3, temp_amp_counter_level_3, axis, signal_type, \
                                                                domain, asset_id, creation_date, last_update, rms_amp_repetition_level_1_timestamp, \
                                                                    peak_amp_repetition_level_1_timestamp, peak_to_peak_amp_repetition_level_1_timestamp, \
                                                                        kurtosis_amp_repetition_level_1_timestamp, one_amp_repetition_level_1_timestamp, \
                                                                            two_amp_repetition_level_1_timestamp, three_amp_repetition_level_1_timestamp, \
                                                                                four_amp_repetition_level_1_timestamp, temp_amp_repetition_level_1_timestamp, \
                                                                                    rms_amp_repetition_level_2_timestamp, peak_amp_repetition_level_2_timestamp, \
                                                                                        peak_to_peak_amp_repetition_level_2_timestamp, kurtosis_amp_repetition_level_2_timestamp, \
                                                                                            one_amp_repetition_level_2_timestamp, two_amp_repetition_level_2_timestamp, \
                                                                                                three_amp_repetition_level_2_timestamp, four_amp_repetition_level_2_timestamp, \
                                                                                                    temp_amp_repetition_level_2_timestamp, rms_amp_repetition_level_3_timestamp, \
                                                                                                        peak_amp_repetition_level_3_timestamp, peak_to_peak_amp_repetition_level_3_timestamp, \
                                                                                                            kurtosis_amp_repetition_level_3_timestamp, one_amp_repetition_level_3_timestamp, \
                                                                                                                two_amp_repetition_level_3_timestamp, three_amp_repetition_level_3_timestamp, \
                                                                                                                    four_amp_repetition_level_3_timestamp, temp_amp_repetition_level_3_timestamp, \
                                                                                                                        mount_id, values = thresh_counter_record
                data = json.dumps({
                    "id": id,
                    "composite": composite,
                    "rms_amp_repetition_level_1": float(rms_amp_repetition_level_1),
                    "rms_amp_counter_level_1": float(rms_amp_counter_level_1),
                    "peak_amp_repetition_level_1": float(peak_amp_repetition_level_1),
                    "peak_amp_counter_level_1": float(peak_amp_counter_level_1),
                    "peak_to_peak_amp_repetition_level_1": float(peak_to_peak_amp_repetition_level_1),
                    "peak_to_peak_amp_counter_level_1": float(peak_to_peak_amp_counter_level_1),
                    "kurtosis_amp_repetition_level_1": float(kurtosis_amp_repetition_level_1),
                    "kurtosis_amp_counter_level_1": float(kurtosis_amp_counter_level_1),
                    "one_amp_repetition_level_1": float(one_amp_repetition_level_1),
                    "one_amp_counter_level_1": float(one_amp_counter_level_1),
                    "two_amp_repetition_level_1": float(two_amp_repetition_level_1),
                    "two_amp_counter_level_1": float(two_amp_counter_level_1),
                    "three_amp_repetition_level_1": float(three_amp_repetition_level_1),
                    "three_amp_counter_level_1": float(three_amp_counter_level_1),
                    "four_amp_repetition_level_1": float(four_amp_repetition_level_1),
                    "four_amp_counter_level_1": float(four_amp_counter_level_1),
                    "temp_amp_repetition_level_1": float(temp_amp_repetition_level_1),
                    "temp_amp_counter_level_1": float(temp_amp_counter_level_1),
                    "rms_amp_repetition_level_2": float(rms_amp_repetition_level_2),
                    "rms_amp_counter_level_2": float(rms_amp_counter_level_2),
                    "peak_amp_repetition_level_2": float(peak_amp_repetition_level_2),
                    "peak_amp_counter_level_2": float(peak_amp_counter_level_2),
                    "peak_to_peak_amp_repetition_level_2": float(peak_to_peak_amp_repetition_level_2),
                    "peak_to_peak_amp_counter_level_2": float(peak_to_peak_amp_counter_level_2),
                    "kurtosis_amp_repetition_level_2": float(kurtosis_amp_repetition_level_2),
                    "kurtosis_amp_counter_level_2": float(kurtosis_amp_counter_level_2),
                    "one_amp_repetition_level_2": float(one_amp_repetition_level_2),
                    "one_amp_counter_level_2": float(one_amp_counter_level_2),
                    "two_amp_repetition_level_2": float(two_amp_repetition_level_2),
                    "two_amp_counter_level_2": float(two_amp_counter_level_2),
                    "three_amp_repetition_level_2": float(three_amp_repetition_level_2),
                    "three_amp_counter_level_2": float(three_amp_counter_level_2),
                    "four_amp_repetition_level_2": float(four_amp_repetition_level_2),
                    "four_amp_counter_level_2": float(four_amp_counter_level_2),
                    "temp_amp_repetition_level_2": float(temp_amp_repetition_level_2),
                    "temp_amp_counter_level_2": float(temp_amp_counter_level_2),
                    "rms_amp_repetition_level_3": float(rms_amp_repetition_level_3),
                    "rms_amp_counter_level_3": float(rms_amp_counter_level_3),
                    "peak_amp_repetition_level_3": float(peak_amp_repetition_level_3),
                    "peak_amp_counter_level_3": float(peak_amp_counter_level_3),
                    "peak_to_peak_amp_repetition_level_3": float(peak_to_peak_amp_repetition_level_3),
                    "peak_to_peak_amp_counter_level_3": float(peak_to_peak_amp_counter_level_3),
                    "kurtosis_amp_repetition_level_3": float(kurtosis_amp_repetition_level_3),
                    "kurtosis_amp_counter_level_3": float(kurtosis_amp_counter_level_3),
                    "one_amp_repetition_level_3": float(one_amp_repetition_level_3),
                    "one_amp_counter_level_3": float(one_amp_counter_level_3),
                    "two_amp_repetition_level_3": float(two_amp_repetition_level_3),
                    "two_amp_counter_level_3": float(two_amp_counter_level_3),
                    "three_amp_repetition_level_3": float(three_amp_repetition_level_3),
                    "three_amp_counter_level_3": float(three_amp_counter_level_3),
                    "four_amp_repetition_level_3": float(four_amp_repetition_level_3),
                    "four_amp_counter_level_3": float(four_amp_counter_level_3),
                    "temp_amp_repetition_level_3": float(temp_amp_repetition_level_3),
                    "temp_amp_counter_level_3": float(temp_amp_counter_level_3),
                    "axis": axis,
                    "signal_type": signal_type,
                    "domain": domain,
                    "asset_id": asset_id,
                    "creation_date": creation_date.isoformat() if creation_date else None,
                    "last_update": last_update.isoformat() if last_update else None,
                    "rms_amp_repetition_level_1_timestamp": rms_amp_repetition_level_1_timestamp.isoformat() if rms_amp_repetition_level_1_timestamp else None,
                    "peak_amp_repetition_level_1_timestamp": peak_amp_repetition_level_1_timestamp.isoformat() if peak_amp_repetition_level_1_timestamp else None,
                    "peak_to_peak_amp_repetition_level_1_timestamp": peak_to_peak_amp_repetition_level_1_timestamp.isoformat() if peak_to_peak_amp_repetition_level_1_timestamp else None,
                    "kurtosis_amp_repetition_level_1_timestamp": kurtosis_amp_repetition_level_1_timestamp.isoformat() if kurtosis_amp_repetition_level_1_timestamp else None,
                    "one_amp_repetition_level_1_timestamp": one_amp_repetition_level_1_timestamp.isoformat() if one_amp_repetition_level_1_timestamp else None,
                    "two_amp_repetition_level_1_timestamp": two_amp_repetition_level_1_timestamp.isoformat() if two_amp_repetition_level_1_timestamp else None,
                    "three_amp_repetition_level_1_timestamp": three_amp_repetition_level_1_timestamp.isoformat() if three_amp_repetition_level_1_timestamp else None,
                    "four_amp_repetition_level_1_timestamp": four_amp_repetition_level_1_timestamp.isoformat() if four_amp_repetition_level_1_timestamp else None,
                    "temp_amp_repetition_level_1_timestamp": temp_amp_repetition_level_1_timestamp.isoformat() if temp_amp_repetition_level_1_timestamp else None,
                    "rms_amp_repetition_level_2_timestamp": rms_amp_repetition_level_2_timestamp.isoformat() if rms_amp_repetition_level_2_timestamp else None,
                    "peak_amp_repetition_level_2_timestamp": peak_amp_repetition_level_2_timestamp.isoformat() if peak_amp_repetition_level_2_timestamp else None,
                    "peak_to_peak_amp_repetition_level_2_timestamp": peak_to_peak_amp_repetition_level_2_timestamp.isoformat() if peak_to_peak_amp_repetition_level_2_timestamp else None,
                    "kurtosis_amp_repetition_level_2_timestamp": kurtosis_amp_repetition_level_2_timestamp.isoformat() if kurtosis_amp_repetition_level_2_timestamp else None,
                    "one_amp_repetition_level_2_timestamp": one_amp_repetition_level_2_timestamp.isoformat() if one_amp_repetition_level_2_timestamp else None,
                    "two_amp_repetition_level_2_timestamp": two_amp_repetition_level_2_timestamp.isoformat() if two_amp_repetition_level_2_timestamp else None,
                    "three_amp_repetition_level_2_timestamp": three_amp_repetition_level_2_timestamp.isoformat() if three_amp_repetition_level_2_timestamp else None,
                    "four_amp_repetition_level_2_timestamp": four_amp_repetition_level_2_timestamp.isoformat() if four_amp_repetition_level_2_timestamp else None,
                    "temp_amp_repetition_level_2_timestamp": temp_amp_repetition_level_2_timestamp.isoformat() if temp_amp_repetition_level_2_timestamp else None,
                    "rms_amp_repetition_level_3_timestamp": rms_amp_repetition_level_3_timestamp.isoformat() if rms_amp_repetition_level_3_timestamp else None,
                    "peak_amp_repetition_level_3_timestamp": peak_amp_repetition_level_3_timestamp.isoformat() if peak_amp_repetition_level_3_timestamp else None,
                    "peak_to_peak_amp_repetition_level_3_timestamp": peak_to_peak_amp_repetition_level_3_timestamp.isoformat() if peak_to_peak_amp_repetition_level_3_timestamp else None,
                    "kurtosis_amp_repetition_level_3_timestamp": kurtosis_amp_repetition_level_3_timestamp.isoformat() if kurtosis_amp_repetition_level_3_timestamp else None,
                    "one_amp_repetition_level_3_timestamp": one_amp_repetition_level_3_timestamp.isoformat() if one_amp_repetition_level_3_timestamp else None,
                    "two_amp_repetition_level_3_timestamp": two_amp_repetition_level_3_timestamp.isoformat() if two_amp_repetition_level_3_timestamp else None,
                    "three_amp_repetition_level_3_timestamp": three_amp_repetition_level_3_timestamp.isoformat() if three_amp_repetition_level_3_timestamp else None,
                    "four_amp_repetition_level_3_timestamp": four_amp_repetition_level_3_timestamp.isoformat() if four_amp_repetition_level_3_timestamp else None,
                    "temp_amp_repetition_level_3_timestamp": temp_amp_repetition_level_3_timestamp.isoformat() if temp_amp_repetition_level_3_timestamp else None,
                    "mount_id": mount_id,
                    "values": json.loads(values) if values else None
                    })
                redis_client_threshold_counter.set(redis_key, data) 
            except Exception as e:
                print("------some exception in threshold counter key update------", e)

# ######################################## update or create last mail sent timestamp ########################################
def check_last_mail_timestamp(key, timestamp):
    try:
        time_res = redis_client_alarm_timestamp.get(key)
        if time_res:
            existing_timestamp = json.loads(time_res.decode("utf-8"))
            time_diff_sec = round((timestamp - existing_timestamp), 2)
            time_diff_hours = round(time_diff_sec/3600, 2)
            if time_diff_hours > 24:                  # checking if last mail was 24 hours earlier
                redis_client_alarm_timestamp.set(key, timestamp)
                return {"status": True}
            else:
                return {"status": False}
        else:
            redis_client_alarm_timestamp.set(key, timestamp)      # setting new timestamp in redisdb if no timestamp found. New entry so send mail
            return {"status": True}
    except Exception as e:
        print("------------e------------", e)
        return {"status": False}