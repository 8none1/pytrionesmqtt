# pytrionesmqtt
MQTT to BTLE Triones LED lights written in Python


## Background

Triones make some kind of generic LED controller which is found in many low cost LED lights on Amazon, such as this one I bought for my kids.
![image](https://user-images.githubusercontent.com/6552931/126961723-b64c8e99-0da0-4924-b254-b4c116330f11.png)

They come with a typical cheapo membrane IR remote, but what I didnt realise when I bought it was that they also provide a BTLE interface and an app called HappyLighting.  When I read the box more carefully and saw "Bluetooth" I figured this was worth investigating more.

Luckily I didn't have to sniff the BTLE traffic as Madhead has already done all the hard work.  The protocol is defined in good detail here:  https://github.com/madhead/saberlight/blob/master/protocols/Triones/protocol.md

I still had a poke around in the BTLE services to see what was what.  A simplified service map looks like this:
![image](https://user-images.githubusercontent.com/6552931/126961615-4c39e4a5-c65b-41e7-82f2-86fe7f73660d.png)

Based on Madhead's work and poking around we can reach the following conclusions about the BTLE service:
 - The main service used is `0xFFD5`
 - The main write characteristic is `0xFFD9`
 - The device is generally "fire and forget" - don't expect to get timely acknowledgements from the controller
 - The "status" service responds from `0xFFD4`
 - There are a number of statically defined "commands"
 - There is an easily understood pattern to the more dynamic commands (set colour, etc)

## What this code does
 - Connects to an existing MQTT server
 - Listens for commands on a topic
 - Issues status updates on a different topic
 - Expects and produces JSON formatted payloads

## How to use it
 - Prerequisites
   - bluepy https://github.com/IanHarvey/bluepy
   - paho-mqtt https://github.com/eclipse/paho.mqtt.python
 - Configure your MQTT server and topic information
   - The default subscription topic for controlling the lights is `triones/control` and the default reporting topic is `triones/status`.
   - To change this, edit the code.  These are defined right up the top.
 - You will need to know the MAC address of your device.  There is a scanner class included which can help you find your devices.  Simply run: `TODO`
 - To get the status of your device send a JSON payload to the control topic:
   - Send to `triones/control` the payload `{"mac":"aa:bb:cc:11:22:33", "status":true}`
   - Receive : `example TODO`
 - To set your lights to red:
   - Send to `triones/control` the payload `{"mac":"aa:bb:cc:11:22:33, "rgb": [255,0,0]}`
 - To power on your lights:
   - Send to `triones/control` the payload `{"mac":"aa:bb:cc:11:22:33, "power":true}`

## Things still to do
 - There is minimal validation on anything
 - Add support for modes
 - Probably doesn't deal with devices going away very well
 - Test it


## Support this project
 - Contributions welcome
 - If you're going to buy some lights, use this affiliate link to the version I bought: https://amzn.to/2V7f2u6  I'm no Big Clive but I took the top of the power-supply-come-controller and it's pretty well made.  Nice seperation between the high voltage and low voltage side, and what looks like decent power supply circuitry.  
 - Test it and log bugs
