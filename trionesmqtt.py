#!/usr/bin/env python3

'''
Talks to cheapo LED BTLE controllers, typically named Triones
Requires bluepy from pip or https://github.com/IanHarvey/bluepy


W Cooke - 2021
@8none1
https://github.com/8none1

Thanks to this page for the protocol: https://github.com/madhead/saberlight/blob/master/protocols/Triones/protocol.md
If you don't want to run this script as root you need to read: https://github.com/IanHarvey/bluepy/issues/313

'''

from bluepy.btle import *
import paho.mqtt.client as mqtt
import json
import sys
import time
import random


debug = True # Prints messages to stdout. Once things are working set this to False
mqtt_server = None
mqtt_server_ip = "mqtt" # Change to the IP address of your MQTT server.  If you need an MQTT server, look at Mosquitto.
mqtt_subscription_topic = "triones/control" # Where we will listen for messages to act on.
mqtt_reporting_topic = "triones/status" # Where we will send status messages
num_retries = 10

WORK_LIST = {}

# Triones constants
MAIN_SERVICE         = 0xFFD5 # Service which provides the characteristics 
MAIN_CHARACTERISTIC  = 0xFFD9 # Where all our commands go
GET_STATUS           = bytearray.fromhex("EF 01 77")
SET_POWER_ON         = bytearray.fromhex("CC 23 33")
SET_POWER_OFF        = bytearray.fromhex("CC 24 33")
SET_COLOUR_BASE      = bytearray.fromhex("56 ff ff ff 00 F0 AA")
SET_MODE             = bytearray.fromhex("BB 27 7F 44")
#  MODE from MODES_DICT ---------------------^ 
#  SPEED from 01 to FF ------------------------ ^ HIGHER IS SLOWER!

# Some other examples if you need them...
#SET_STATIC_COL_RED   = bytearray.fromhex("56 ff 00 00 00 F0 AA")
#SET_STATIC_COL_GREEN = bytearray.fromhex("56 00 ff 00 00 F0 AA")
#SET_STATIC_COL_BLUE  = bytearray.fromhex("56 00 00 ff 00 F0 AA")
#SET_STATIC_COL_WHITE = bytearray.fromhex("56 00 00 00 FF 0F AA")
# MODES_DICT = {
# 37 : 0x25: "Seven color cross fade",
# 38 : 0x26: "Red gradual change",
# 39 : 0x27: "Green gradual change",
# 40 : 0x28: "Blue gradual change",
# 41 : 0x29: "Yellow gradual change",
# 42 : 0x2A: "Cyan gradual change",
# 43 : 0x2B: "Purple gradual change",
# 44 : 0x2C: "White gradual change",
# 45 : 0x2D: "Red, Green cross fade",
# 46 : 0x2E: "Red blue cross fade",
# 47 : 0x2F: "Green blue cross fade",
# 48 : 0x30: "Seven color strobe flash",
# 49 : 0x31: "Red strobe flash",
# 50 : 0x32: "Green strobe flash",
# 51 : 0x33: "Blue strobe flash",
# 52 : 0x34: "Yellow strobe flash",
# 53 : 0x35: "Cyan strobe flash",
# 54 : 0x36: "Purple strobe flash",
# 55 : 0x37: "White strobe flash",
# 56 : 0x38: "Seven color jumping change"
# }


def logger(message):
    if debug: print(message)

class ScanDelegate(DefaultDelegate):
    def __init__(self):
        DefaultDelegate.__init__(self)
    def handleDiscovery(self, dev, isNewDev, isNewData):
        if isNewDev:
            logger(f"Discovered device: {dev.addr}")

class DataDelegate(DefaultDelegate):
    def __init__(self,mqtt_client, mac):
        DefaultDelegate.__init__(self)
        self.mqtt_client = mqtt_client
        self.mac = mac
    
    def handleNotification(self, cHandle, data):
        logger(f"Notification from device: {self.mac}")
        if cHandle == 12:
            # The protocol for my devices looks like 0x66,0x4,power,mode,0x20,speed,red,green,blue,white,0x3,0x99
            # This is a response to a status update
            # Hex response looks like
            # Off (but red)
            # ['0x66', '0x4', '0x24', '0x41', '0x20', '0x1', '0xff', '0x0', '0x0', '0x0', '0x3', '0x99']
            # Off but blue
            # ['0x66', '0x4', '0x24', '0x41', '0x20', '0x1', '0x0', '0x0', '0xff', '0x0', '0x3', '0x99']
            # On but green
            # ['0x66', '0x4', '0x23', '0x41', '0x20', '0x1', '0x0', '0xff', '0x0', '0x0', '0x3', '0x99']

            data = [hex(x) for x in data]
            logger("Response received: "+str(data))
            if data[0] == "0x66" and data[1] == "0x4" and data[11] == "0x99":
                # Probably what we're looking for
                power = True if data[2] == "0x23" else False
                mode  = int(data[3], base=16)
                speed = int(data[5], base=16)
                rgb   = [int(data[6], base=16), int(data[7], base=16), int(data[8], base=16)]
                # white = data[9] # My LEDs dont have white
                json_status = json.dumps({"mac":self.mac, "power":power, "rgb":rgb, "speed": speed, "mode":mode})# json_status?  Wasn't he in Fast and Furious?
                logger(json_status)
                send_mqtt(self.mqtt_client, json_status)
            else:
                logger("Didn't understand the response data.")
        else:
            logger(f"Got a different handle: {cHandle}")

def mqtt_on_connect(client, userdata, flags, rc):
    logger("MQTT Connected")
    client.subscribe(mqtt_subscription_topic)

def send_mqtt(mqtt_client,value):
    logger("MQTT: Sending value: %s to topic %s" % (value, mqtt_reporting_topic))
    mqtt_client.publish(mqtt_reporting_topic, value)

def mqtt_message_received(client, userdata, message):
    global WORK_LIST
    logger("Adding request to queue")
    logger(message.payload)
    if message.topic == mqtt_subscription_topic:
        try:
            request = json.loads(message.payload.decode('utf-8'))
        except:
            logger(f"Failed to parse work request")
            return
        if "mac" in request.keys():
            mac = request['mac']
            # If we have work on the queue for a given mac, and we receive another request for the same mac
            # the we replace the old job with the new one.  Seems fine.  You want the most recent request to
            # be what happens.
            WORK_LIST[mac] = request
            if "count" not in request.keys():
                WORK_LIST[mac]['count'] = num_retries
        else:
            logger("Failed to get mac for request")
            return

def triones(client, work):
    if len(work) > 0:
        message = next(iter(work))
        message = work[message]
    else:
        return

    mac = message['mac']
    if message['count'] > 0:
        message['count'] -= 1
    else:
        logger(f"{mac}    No more tries left. Removing.")
        del work[mac]
        return
    
    # Set up a connection to the device
    # These devices seem really flaky, they either connect straight away, or not at all. 
    # Some of this is, I expect, because they return invalid error codes which BlueZ
    # doesn't deal with.  
    # https://github.com/Depau/consmart-ble-mqtt/blob/master/0001-Workaround-for-non-compliant-BLE-lights.patch
    # Update: I built a patched Bluez, didn't help.
    #connected = False
    logger(f"{mac}    Connect attempts remaining {message['count']}/10")
    try:
        trione = Peripheral(mac, timeout=5)
        connected = True
        logger(f"{mac}    Connected!")
    except BTLEDisconnectError:
        logger(f"{mac}    Failed to connect to device.")
        return False
    
    # If we get here, it should be connected.  But not for long, the life span of a connection seems very short.
    trione.withDelegate(DataDelegate(client, mac))
    service = trione.getServiceByUUID(MAIN_SERVICE)
    characteristic = service.getCharacteristics(MAIN_CHARACTERISTIC)[0]
    keys = message.keys()
    
    if "status" in keys:
        logger(f"{mac}    Requesting status")
        characteristic.write(GET_STATUS)
        client.loop()
        trione.waitForNotifications(2)
   
    if "power" in keys:
        power = SET_POWER_ON if message["power"] == True else SET_POWER_OFF
        logger(f"{mac}    Setting power to {message['power']}")
        characteristic.write(power)
        client.loop()

    if "rgb_colour" in keys:
        r,g,b = message["rgb_colour"]
        if "percentage" in keys:
            scale_factor = int(message["percentage"])/100
        else:
            scale_factor = 1
        colour_message = SET_COLOUR_BASE
        colour_message[1] = int(r * scale_factor)
        colour_message[2] = int(g * scale_factor)
        colour_message[3] = int(b * scale_factor)
        logger(f"{mac}    Setting colour to ({r},{g},{b})")
        characteristic.write(colour_message)
        client.loop()
        
    if "mode" in keys and "speed" in keys:
        # I guess you need to set a mode and a speed at the same time, and can't set one without the other?
        # Haven't done any testing on that.
        mode = message["mode"]
        speed = message["speed"]
        if mode >= 37 and mode <= 56:
            mode_message = SET_MODE
            mode_message[1] = mode
            mode_message[2] = speed
            logger(f"{mac}    Setting mode {mode} speed {speed}")
            characteristic.write(mode_message)
        client.loop()

    # We're going to assume that if we got this far then everything worked and we can remove it from the queue.

    logger(f"{mac}    Completed conversation with device.  Disconnecting.\n\n\n")
    trione.disconnect()
    del work[mac]


        
def find_devices():
    triones={}
    scanner = Scanner().withDelegate(ScanDelegate())
    devices = scanner.scan(10.0)

    for dev in devices:
        for (adtype, desc, value) in dev.getScanData():
            if desc == "Complete Local Name" and value.startswith("Triones:"):
                triones[dev.addr] = dev.rssi
    if len(triones) > 0:
        triones = dict(sorted(triones.items(), key=lambda item:item[1], reverse=True))
        print("\n\n")
        for key, value in triones.items():
            print(f"Triones device - MAC address: {key}   RSSI: {value}")
    else:
        print("None found :(")


def server(run_mode=None):
   
    if mqtt_server_ip is not None:
        mqtt_client = mqtt.Client()
        mqtt_client.on_connect = mqtt_on_connect
        mqtt_client.on_message = mqtt_message_received
        mqtt_client.connect(mqtt_server_ip, 1883, 60)
    else:
        raise NameError("No MQTT Server configured")
    
    while True:
        try:
            mqtt_client.loop()
            triones(mqtt_client, WORK_LIST)

        except KeyboardInterrupt:
            logger("Exiting...")
            mqtt_client.disconnect()
            raise
        except BTLEDisconnectError:
            logger("Device has gone away..")
            send_mqtt(mqtt_client, '{"connect":"False"}')
        except:
            raise

            #raise
            # I read something which suggests that these devices sometimes return data which is invalid
            # and this causes BlueZ to choke. The upshot is that if this happens when we're trying to
            # read status information no information will be returned, but then next time, two status
            # messages get returned.  Maybe we could do a wait for messages as the first thing we do...
            # might slow us down a bit, but :shrug: 
            # I tried to patch the version of Bluez on the Pi to work around this.  First off, Bluez on the pi
            # doesn't build successfully from the source packages!  But once I found a patch for that, I also
            # applied the patch to fix this as well.  There are some debs in a tarball in the repo if you want
            # to test it.  It made little difference in my tests.  All things considered, these lights are crap.
            # But cheap!


if len(sys.argv) > 1 and sys.argv[1] == "--scan":
        find_devices()
        sys.exit(0)

else:
    logger("Starting")
    server()
