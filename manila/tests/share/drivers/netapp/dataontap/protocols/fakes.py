# Copyright (c) 2015 Clinton Knight.  All rights reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.


SHARE_NAME = 'fake_share'
SHARE_ID = '9dba208c-9aa7-11e4-89d3-123b93f75cba'
SHARE_ADDRESS = '10.10.10.10'
CLIENT_ADDRESS_1 = '20.20.20.10'
CLIENT_ADDRESS_2 = '20.20.20.20'

CIFS_SHARE = {
    'export_location': '//%s/%s' % (SHARE_ADDRESS, SHARE_NAME),
    'id': SHARE_ID
}

NFS_SHARE_PATH = '/%s' % SHARE_NAME
NFS_SHARE = {
    'export_location': '%s:%s' % (SHARE_ADDRESS, NFS_SHARE_PATH),
    'id': SHARE_ID
}

NFS_ACCESS_HOSTS = [CLIENT_ADDRESS_1]

ACCESS = {
    'access_type': 'user',
    'access_to': NFS_ACCESS_HOSTS
}
