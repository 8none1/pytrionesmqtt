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
import colorsys
import platform
import time
import logging
import os

debug = True # Prints messages to stdout. Once things are working set this to False
mqtt_server = None
mqtt_server_ip = "mqtt" # Change to the IP address of your MQTT server.  If you need an MQTT server, look at Mosquitto.
mqtt_subscription_topic = "triones/control" # Where we will listen for messages to act on.
mqtt_reporting_topic = "triones/status" # Where we will send status messages

# client/server status tracking.  There is probably a better way, but this will do for now
worker_registered = False

# Triones constants
MAIN_SERVICE         = 0xFFD5 # Service which provides the characteristics 
MAIN_CHARACTERISTIC  = 0xFFD9 # Where all our commands go
GET_STATUS           = bytearray.fromhex("EF 01 77")
SET_POWER_ON         = bytearray.fromhex("CC 23 33")
SET_POWER_OFF        = bytearray.fromhex("CC 24 33")
SET_COLOUR_BASE      = bytearray.fromhex("56 ff ff ff 00 F0 AA")
SET_MODE             = bytearray.fromhex("BB 27 7F 44")
#  MODE from MODES_DICT ---------------------^ 
#  SPEED from 01 to FF ------------------------ ^ 

# Some other examples if you need them...
#SET_STATIC_COL_RED   = bytearray.fromhex("56 ff 00 00 00 F0 AA")
#SET_STATIC_COL_GREEN = bytearray.fromhex("56 00 ff 00 00 F0 AA")
#SET_STATIC_COL_BLUE  = bytearray.fromhex("56 00 00 ff 00 F0 AA")
#SET_STATIC_COL_WHITE = bytearray.fromhex("56 00 00 00 FF 0F AA")
# MODES_DICT = {
# 0x25: "Seven color cross fade",
# 0x26: "Red gradual change",
# 0x27: "Green gradual change",
# 0x28: "Blue gradual change",
# 0x29: "Yellow gradual change",
# 0x2A: "Cyan gradual change",
# 0x2B: "Purple gradual change",
# 0x2C: "White gradual change",
# 0x2D: "Red, Green cross fade",
# 0x2E: "Red blue cross fade",
# 0x2F: "Green blue cross fade",
# 0x30: "Seven color stobe flash",
# 0x31: "Red strobe flash",
# 0x32: "Green strobe flash",
# 0x33: "Blue strobe flash",
# 0x34: "Yellow strobe flash",
# 0x35: "Cyan strobe flash",
# 0x36: "Purple strobe flash",
# 0x37: "White strobe flash",
# 0x38: "Seven color jumping change"
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
    if message.topic == mqtt_subscription_topic:
        # get status
        # set mode
        # set speed
        
        try:
            json_request = json.loads(message.payload)

            if "mac" in json_request.keys():
                mac = json_request["mac"]
                logger(f"{mac}    Received Triones request for device")
                logger(json.dumps(json_request, indent=4, sort_keys=True))
            elif "ack" in json_request.keys():
                logger("Received ack from server.")
                global worker_registered
                worker_registered = True
                return True
            else:
                logger("Received unhandled request.  Doing nothing.")
                return False
        except:
            logger("Failed to parse payload JSON.  Giving up")
            return False

        # Set up a connection to the device
        # These devices seem really picky, so let's try to connect 3 times before we give up.
        # It seems that they either connect straight away, or not at all. 
        connected = False
        for a in range(10):
            # These lights are super flaky. It seems hard to get a connection a lot of the time.
            # Some of this is, I expect, because they return invalid error codes which BlueZ
            # doesn't deal with.  
            # https://github.com/Depau/consmart-ble-mqtt/blob/master/0001-Workaround-for-non-compliant-BLE-lights.patch
            # I've tried to build BlueZ on a Pi from the deb source, but it doesn't compile (!!) So I gave up and just
            # retry a bunch of times.  This is annoying but, meh, whatdyagonnado?
            print(f"{mac}    Connect attempt {a+1}/10")
            try:
                trione = Peripheral(mac, timeout=5)
                connected = True
                logger(f"{mac}    Connected!")
                break
            except BTLEDisconnectError:
                logger(f"{mac}    Failed to connect to device.")
                time.sleep(2)
        if connected == False:
            # We tried, but it ain't happening.
            logger(f"{mac}    Unable to connect.  Giving up.")
            message = '{"mac": "'+mac+'", "connect": false}'
            send_mqtt(client, message)
            return False
        # If we get here, it should be connected.  But not for long, the life span of a connection seems very short.
        trione.withDelegate(DataDelegate(client, mac))
        service = trione.getServiceByUUID(MAIN_SERVICE)
        characteristic = service.getCharacteristics(MAIN_CHARACTERISTIC)[0]
        keys = json_request.keys()
        if "status" in keys:
            logger(f"{mac}    Requesting status")
            characteristic.write(GET_STATUS)
            trione.waitForNotifications(2)
        
        if "power" in keys:
            power = SET_POWER_ON if json_request["power"] == True else SET_POWER_OFF
            logger(f"{mac}    Setting power to {json_request['power']}")
            characteristic.write(power)

        if "rgb_colour" in keys:
            r,g,b = json_request["rgb_colour"]
            if "percentage" in keys:
                scale_factor = int(json_request["percentage"])/100
            else:
                scale_factor = 1
            colour_message = SET_COLOUR_BASE
            colour_message[1] = int(r * scale_factor)
            colour_message[2] = int(g * scale_factor)
            colour_message[3] = int(b * scale_factor)
            logger(f"{mac}    Setting colour to ({r},{g},{b})")
            characteristic.write(colour_message)
        
        if "mode" in keys:
            # I guess you need to set a mode and a speed at the same time, and can't set one without the other?
            # Haven't done any testing on that.
            mode = json_request["mode"]
            speed = json_request["speed"]
            if mode >= 37 and mode <= 56:
                mode_message = SET_MODE
                mode_message[1] = mode
                mode_message[2] = speed
                logger(f"{mac}    Setting mode {mode} speed {speed}")
                characteristic.write(mode_message)
        logger(f"{mac}    Completed conversation with device.  Disconnecting.\n\n\n")
        trione.disconnect()


        
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
    # On reflection using the word "server" here was wrong.  Oh well.
    # run_mode "worker" tells us that we are part of a collective not stand-alone.
    if run_mode == "worker":
        global mqtt_subscription_topic
        hostname = platform.node()
        logger(f"Setting controller topic to: {mqtt_subscription_topic}")
        mqtt_controller_topic = mqtt_subscription_topic
        mqtt_subscription_topic = mqtt_subscription_topic+'/'+hostname
        logger(f"Set sub topic to: {mqtt_subscription_topic}")
    
    if mqtt_server_ip is not None:
        mqtt_client = mqtt.Client()
        mqtt_client.on_connect = mqtt_on_connect
        mqtt_client.on_message = mqtt_message_received
        mqtt_client.connect(mqtt_server_ip, 1883, 60)
    else:
        raise NameError("No MQTT Server configured")
    
    if run_mode == "worker":
        # We are now connected to MQTT so we can tell everyone we're ready for work.
        global worker_registered
        logger("In worker mode, so need to clock on:")
        loop = 0
        while True:
            mqtt_client.loop()
            logger(f"Trying to register with server...")
            payload = json.dumps({"register":True, "hostname":hostname})
            mqtt_client.publish(mqtt_controller_topic, payload)
            mqtt_client.loop()
            if loop > 10:
                raise NameError("Failed to talk to server. Giving up.  Maybe try again later?")
            else:
                loop += 1
            if worker_registered == True:
                logger("Have successfully registered.")
                break
            time.sleep(2)

    while True:
        try:
            mqtt_client.loop_forever()
        except KeyboardInterrupt:
            logger("Exiting...")
            mqtt_client.disconnect()
            raise
        except BTLEDisconnectError:
            logger("Device has gone away..")
            #send_mqtt(mqtt_client, '{"connect":"False"}')
            raise
            # I read something which suggests that these devices sometimes return data which is invalid
            # and this causes BlueZ to choke. The upshot is that if this happens when we're trying to
            # read status information no information will be returned, but then next time, two status
            # messages get returned.  Maybe we could do a wait for messages as the first thing we do...
            # might slow us down a bit, but :shrug: 

if len(sys.argv) > 1 and sys.argv[1] == "--scan":
        find_devices()
        sys.exit(0)
if len(sys.argv) > 1 and sys.argv[1] == "--worker":
    # Run with `--worker` to run as a distributed worker to a main controller
    logger("Running in worker mode")
    server(run_mode="worker")
else:
    logger("Running in stand-alone server mode")
    server()
