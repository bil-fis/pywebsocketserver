# -*- coding: utf8 -*-

import socket
import time
from threading import Thread
import hashlib
import base64
import struct
import json


class SocketIoThread(Thread):
    def __init__(self, connection, uid, io):
        Thread.__init__(self)
        self.con = connection
        self.isHandleShake = False
        self.uid = uid
        self.io = io
        self.signKey = "ADS#@!D"
        self.online = True

    def run(self):
        while True:
            if not self.isHandleShake:  # 握手
                try:
                    print("握手")
                    header_data = []
                    #已经收到的头大小
                    header_size = 0
                    #最大大小
                    max_skip_size = 4096


                    row = []
                    while True:
                        d = self.con.recv(1)
                        row.append(d)
                        tail_two = ''.join(row[-2:])
                        if tail_two=='\r\n':
                            row_str = ''.join(row[:-2])
                            header_data.append(row_str)
                            row = []
                            if row_str=='':
                                break
                        header_size += 1

                        if header_size > max_skip_size:
                            self.onClose()
                            break

                    header = {}
                    for data in header_data:
                        if ": " in data:
                            unit = data.split(": ")
                            header[unit[0]] = unit[1]
                    secKey = header['Sec-WebSocket-Key'];
                    resKey = base64.encodestring(
                        hashlib.new("sha1", secKey + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest());
                    resKey = resKey.replace('\n', '')
                    response = '''HTTP/1.1 101 Switching Protocols\r\n'''
                    response += '''Upgrade: websocket\r\n'''
                    response += '''Connection: Upgrade\r\n'''
                    response += '''Sec-WebSocket-Accept: %s\r\n\r\n''' % (resKey,)
                    self.con.send(response)
                    self.isHandleShake = True
                    # 返回用户id
                    self.sendData("SETUID")
                    self.io.onConnect(self.uid)
                    print("握手成功")
                except:
                    return
            else:
                try:
                    data_head = self.con.recv(1)
                    if repr(data_head) == '':
                        print("客户端断开链接")
                        self.onClose()
                        return

                    header = struct.unpack("B", data_head)[0]
                    opcode = header & 0b00001111
                    print("操作符号%d" % (opcode,))

                    if opcode == 8:
                        print("客户端断开链接")
                        self.onClose()
                        return

                    data_length = self.con.recv(1)
                    data_lengths = struct.unpack("B", data_length)
                    data_length = data_lengths[0] & 0b01111111
                    masking = data_lengths[0] >> 7
                    if data_length <= 125:
                        payloadLength = data_length
                    elif data_length == 126:
                        payloadLength = struct.unpack("H", self.con.recv(2))[0]
                    elif data_length == 127:
                        payloadLength = struct.unpack("Q", self.con.recv(8))[0]
                    print("字符串长度是:%d" % (data_length,))
                    if masking == 1:
                        maskingKey = self.con.recv(4)
                        self.maskingKey = maskingKey
                    data = self.con.recv(payloadLength)
                    if masking == 1:
                        i = 0
                        true_data = ''
                        for d in data:
                            true_data += chr(ord(d) ^ ord(maskingKey[i % 4]))
                            i += 1
                        self.onData(true_data)
                    else:
                        self.onData(data)
                except:
                    print("err")
                    self.onClose()
                    return

    def onData(self, text):
        try:
            uid, sign, value = text.split("<split>")
            uid = int(uid)
        except:
            print("数据格式不正确")
            self.con.close()
        hashStr = hashlib.new("md5", str(uid) + self.signKey).hexdigest()
        if hashStr != sign:
            print("非法请求")
            self.con.close()
            return
        return self.io.onData(uid, value)

    def onClose(self):
        self.con.close()
        self.online = False
        self.io.onClose(self.uid)

    def packData(self, text):

        sign = hashlib.new("md5", str(self.uid) + self.signKey).hexdigest()
        data = '%s<split>%s<split>%s' % (self.uid, sign, text)
        return data

    def sendData(self, text):

        text = self.packData(text)
        print(text)
        # 头
        self.con.send(struct.pack("!B", 0x81))
        # 计算长度
        length = len(text)
        # masking = 0b00000000;

        if length <= 125:
            self.con.send(struct.pack("!B", length))

        elif length <= 65536:
            self.con.send(struct.pack("!B", 126))
            self.con.send(struct.pack("!H", length))
        else:
            self.con.send(struct.pack("!B", 127))
            self.con.send(struct.pack("!Q", length))

        self.con.send(struct.pack("!%ds" % (length,), text))
