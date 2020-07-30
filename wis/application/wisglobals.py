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

smsgatewayabspath = None

watchdogThread = None
watchdogThreadNotify = None
# For route-based watchdogs
watchdogRouteThread = {}
watchdogRouteThreadNotify = {}
watchdogRouteThreadQueue = {}

routerThread = None
rdb = None
cleanupseconds = None

wisid = None
wisport = None
wisipaddress = None

pissendtimeout = None

ldapenabled = None
ldapserver = None
ldapbasedn = None
ldapusers = None

sslenabled = None
sslcertificate = None
sslprivatekey = None
sslcertificatechain = None

validusernameregex = None
validusernamelength = None

version = None
