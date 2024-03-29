#!/usr/bin/python3
import time
import serial
import sys
import json
import os
import signal
import psutil
import paho.mqtt.client as mqtt
import threading

################################

broker_ip = 'localhost'

gun_event = 0x00

CONTROL_E = 0x01
DATA_E = 0x02

missionPort = ''
status = ''
lib_mqtt_client = ''
data_topic = ''
req = ''
lib = ''
control_topic = ''
req_topic = ''
con = ''
argv = ''


def missionPortOpening(missionportnum, missionbaudrate):
    global missionPort
    global status

    print('Connect to serial...')
    try:
        missionPort = serial.Serial(missionportnum, missionbaudrate, timeout=2)
        if missionPort.isOpen():
            print('missionPort Open. ', missionportnum, 'Data rate: ', missionbaudrate)
            status = 'open'
            send_data_to_msw(status)

    except serial.SerialException as e:
        missionPortError(e)
    except TypeError as e:
        missionPortClose()


def missionPortClose():
    global missionPort
    global status

    status = 'close'
    send_data_to_msw(status)

    print('missionPort closed!')
    missionPort.close()


def missionPortError(err):
    global status
    global lib

    status = 'error'
    if status == 'error':
        send_data_to_msw(status)

    missionPortOpening(lib['serialPortNum'], lib['serialBaudrate'])

    print('[missionPort error]: ', err)


def send_data_to_msw(obj_data):
    global lib_mqtt_client
    global data_topic

    data_topic = '/MUV/data/' + lib["name"] + '/' + lib["data"][0]
    lib_mqtt_client.publish(data_topic, obj_data)


def missionPortData():
    global status

    while True:
        stx = 'A2'
        command = '010000000000000000'
        crc = 0
        for i in range(0, len(command), 2):
            crc ^= int(command[i + 1], 16)
        if crc < 16:
            command += ('0' + str(crc))
        else:
            command += str(crc)
        etx = 'A3'
        command = stx + command + etx

        msdata = bytes.fromhex(command)
        missionPort.write(msdata)

        aliveMsg = missionPort.readline()
        alivemessage = aliveMsg.hex().split('a3')[0]

        if alivemessage[0:2] == 'a2':
            if alivemessage[2:4] == '02':
                status = 'alive'
                send_data_to_msw(status)
            elif alivemessage[2:4] == '04':
                status = 'success'
                send_data_to_msw(status)
            else:
                status = 'board error'
                send_data_to_msw(status)
        else:
            status = 'board error'
            send_data_to_msw(status)

        time.sleep(1)


def msw_mqtt_connect(host):
    global lib
    global lib_mqtt_client
    global control_topic
    global data_topic

    lib_mqtt_client = mqtt.Client()
    lib_mqtt_client.on_connect = on_connect
    lib_mqtt_client.on_disconnect = on_disconnect
    lib_mqtt_client.on_subscribe = on_subscribe
    lib_mqtt_client.on_message = on_message
    lib_mqtt_client.connect(host, 1883)
    control_topic = '/MUV/control/' + lib["name"] + '/' + lib["control"][0]
    lib_mqtt_client.subscribe(control_topic, 0)

    lib_mqtt_client.loop_start()
    return lib_mqtt_client


def on_connect(client, userdata, flags, rc):
    print('[msg_mqtt_connect] connect to ', broker_ip)


def on_disconnect(client, userdata, flags, rc=0):
    print(str(rc))


def on_subscribe(client, userdata, mid, granted_qos):
    print("subscribed: " + str(mid) + " " + str(granted_qos))


def on_message(client, userdata, msg):
    global gun_event
    global data_topic
    global control_topic
    global con

    if msg.topic == control_topic:
        con = msg.payload.decode('utf-8')
        gun_event |= CONTROL_E


def request_to_mission():
    global missionPort
    global con

    try:
        if missionPort is not None:
            if missionPort.isOpen():
                con_arr = con.split(',')
                if (int(con_arr[0]) < 8) and (int(con_arr[1]) < 8):
                    stx = 'A2'
                    command = '030' + con_arr[0] + '0' + con_arr[1] + '000000000000'
                    crc = 0
                    #                     print(command)
                    for i in range(0, len(command), 2):
                        crc ^= int(command[i + 1], 16)
                    if crc < 16:
                        command += ('0' + str(crc))
                    else:
                        command += str(crc)

                    etx = 'A3'
                    command = stx + command + etx

                    msdata = bytes.fromhex(command)
                    missionPort.write(msdata)

    except (ValueError, IndexError, TypeError):
        print('except Error')
        pass


def main():
    global lib
    global lib_mqtt_client
    global missionPort
    global control_topic
    global data_topic
    global argv
    global gun_event
    global con

    my_lib_name = 'lib_sparrow_gun'

    argv = sys.argv
    print('===================================================')
    print(argv)
    print('===================================================')
    cmd = ['./' + my_lib_name, argv[1], argv[2]]
    pid_arr = []
    processWatch = [p.cmdline() for p in psutil.process_iter()].count(cmd)
    if processWatch > 2:
        for p in psutil.process_iter():
            if (p.cmdline() == cmd):
                print(p.pid)
                pid_arr.append(p.pid)
        os.kill(pid_arr[0], signal.SIGKILL)
        os.kill(pid_arr[0] + 1, signal.SIGKILL)

    try:
        lib = dict()
        with open('./' + my_lib_name + '.json', 'r') as f:
            lib = json.load(f)
            lib = json.loads(lib)

    except:
        lib = dict()
        lib["name"] = my_lib_name
        lib["target"] = 'armv6'
        lib["description"] = "[name] [portnum] [baudrate]"
        lib["scripts"] = './' + my_lib_name + ' /dev/ttyAMA1 9600'
        lib["data"] = ['GUN']
        lib["control"] = ['MICRO']
        lib = json.dumps(lib, indent=4)
        lib = json.loads(lib)

        with open('./' + my_lib_name + '.json', 'w', encoding='utf-8') as json_file:
            json.dump(lib, json_file, indent=4)

    lib['serialPortNum'] = argv[1]
    lib['serialBaudrate'] = argv[2]

    control_topic = '/MUV/control/' + lib["name"] + '/' + lib["control"][0]
    data_topic = '/MUV/data/' + lib["name"] + '/' + lib["data"][0]

    msw_mqtt_connect(broker_ip)
    missionPortOpening(lib['serialPortNum'], lib['serialBaudrate'])

    t = threading.Thread(target=missionPortData, )
    t.start()

    while True:
        if gun_event & CONTROL_E:
            gun_event &= (~CONTROL_E)
            request_to_mission()


if __name__ == "__main__":
    main()

# python3 -m PyInstaller -F lib_sparrow_gun.py
