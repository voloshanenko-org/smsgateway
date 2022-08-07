#!/usr/bin/python
# Copyright 2015 Neuhold Markus and Kleinsasser Mario
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import sys
sys.path.insert(0, "..")
from os import path
from common.config import SmsConfig

import base64
import hashlib
from Crypto import Random
from Crypto.Cipher import AES

class GlobalHelper(object):

    @staticmethod
    def encodeAES(raw):
        abspath = path.abspath(path.join(path.dirname(__file__), path.pardir))
        configfile = abspath + '/conf/smsgw.conf'
        cfg = SmsConfig(configfile)
        key = cfg.getvalue('key', '7D8FAA235238F8C2').encode('utf-8')

        raw = _pad(raw)
        iv = Random.new().read(AES.block_size)
        cipher = AES.new(key, AES.MODE_CBC, iv)
        return base64.b64encode(iv + cipher.encrypt(raw.encode()))

    @staticmethod
    def decodeAES(enc):
        abspath = path.abspath(path.join(path.dirname(__file__), path.pardir))
        configfile = abspath + '/conf/smsgw.conf'
        cfg = SmsConfig(configfile)
        key = cfg.getvalue('key', '7D8FAA235238F8C2').encode('utf-8')

        enc = base64.b64decode(enc)
        iv = enc[:AES.block_size]
        cipher = AES.new(key, AES.MODE_CBC, iv)
        return _unpad(cipher.decrypt(enc[AES.block_size:])).decode('utf-8')

    @staticmethod
    def _pad(s):
        bs = AES.block_size
        return s + (bs - len(s) % bs) * chr(bs - len(s) % bs)

    @staticmethod
    def _unpad(s):
        return s[:-ord(s[len(s)-1:])]
