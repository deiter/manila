# Copyright 2019 Nexenta Systems, Inc.
# All Rights Reserved.
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

import ddt
import mock
from mock import patch
from oslo_utils import units

from manila import context
from manila import exception
from manila.share import configuration as conf
from manila.share.drivers.nexenta.ns5 import jsonrpc
from manila.share.drivers.nexenta.ns5 import nexenta_nas
from manila import test

RPC_PATH = 'manila.share.drivers.nexenta.ns5.jsonrpc'
DRV_PATH = 'manila.share.drivers.nexenta.ns5.nexenta_nas.NexentaNasDriver'
DRIVER_VERSION = '1.1'
SHARE = {'share_id': 'uuid', 'size': 1, 'share_proto': 'NFS'}
SHARE_PATH = 'pool1/nfs_share/share-uuid'


@ddt.ddt
class TestNexentaNasDriver(test.TestCase):

    def setUp(self):
        def _safe_get(opt):
            return getattr(self.cfg, opt)
        super(TestNexentaNasDriver, self).setUp()
        self.cfg = conf.Configuration(None)
        self.cfg.nexenta_nas_host = '1.1.1.1'
        self.cfg.nexenta_rest_address = '2.2.2.2'
        self.ctx = context.get_admin_context()
        self.mock_object(
            self.cfg, 'safe_get', mock.Mock(side_effect=_safe_get))
        self.cfg.nexenta_rest_port = 8080
        self.cfg.nexenta_rest_protocol = 'auto'
        self.cfg.nexenta_pool = 'pool1'
        self.cfg.nexenta_dataset_record_size = 131072
        self.cfg.reserved_share_percentage = 0
        self.cfg.nexenta_folder = 'nfs_share'
        self.cfg.nexenta_user = 'user'
        self.cfg.share_backend_name = 'NexentaStor5'
        self.cfg.nexenta_password = 'password'
        self.cfg.nexenta_thin_provisioning = False
        self.cfg.nexenta_mount_point_base = 'mnt'
        self.cfg.enabled_share_protocols = 'NFS'
        self.cfg.nexenta_mount_point_base = '$state_path/mnt'
        self.cfg.nexenta_dataset_compression = 'on'
        self.cfg.network_config_group = 'DEFAULT'
        self.cfg.admin_network_config_group = (
            'fake_admin_network_config_group')
        self.cfg.driver_handles_share_servers = False
        self.cfg.safe_get = self.fake_safe_get
        self.nef_mock = mock.Mock()
        self.mock_object(jsonrpc, 'NefRequest')
        self.drv = nexenta_nas.NexentaNasDriver(configuration=self.cfg)
        self.drv.do_setup(self.ctx)

    def fake_safe_get(self, key):
        try:
            value = getattr(self.cfg, key)
        except AttributeError:
            value = None
        return value

    def test_backend_name(self):
        self.assertEqual('NexentaStor5', self.drv.share_backend_name)

    @mock.patch('%s._get_provisioned_capacity' % DRV_PATH)
    @mock.patch('manila.share.drivers.nexenta.ns5.'
                'jsonrpc.NefServices.get')
    @mock.patch('manila.share.drivers.nexenta.ns5.'
                'jsonrpc.NefFilesystems.set')
    @mock.patch('manila.share.drivers.nexenta.ns5.'
                'jsonrpc.NefFilesystems.get')
    def test_check_for_setup_error(self, get_filesystem, set_filesystem,
                                   get_service, prov_capacity):
        prov_capacity.return_value = 1
        get_filesystem.return_value = {
            'mountPoint': '/path/to/volume',
            'nonBlockingMandatoryMode': False,
            'smartCompression': False,
            'isMounted': True
        }
        get_service.return_value = {
            'state': 'online'
        }
        self.assertIsNone(self.drv.check_for_setup_error())
        get_filesystem.assert_called_with(self.drv.root_path)
        set_filesystem.assert_not_called()
        get_service.assert_called_with('nfs')
        get_filesystem.return_value = {
            'mountPoint': '/path/to/volume',
            'nonBlockingMandatoryMode': True,
            'smartCompression': True,
            'isMounted': True
        }
        set_filesystem.return_value = {}
        payload = {
            'nonBlockingMandatoryMode': False,
            'smartCompression': False
        }
        self.assertIsNone(self.drv.check_for_setup_error())
        get_filesystem.assert_called_with(self.drv.root_path)
        set_filesystem.assert_called_with(self.drv.root_path, payload)
        get_service.assert_called_with('nfs')
        get_filesystem.return_value = {
            'mountPoint': '/path/to/volume',
            'nonBlockingMandatoryMode': False,
            'smartCompression': True,
            'isMounted': True
        }
        payload = {
            'smartCompression': False
        }
        set_filesystem.return_value = {}
        self.assertIsNone(self.drv.check_for_setup_error())
        get_filesystem.assert_called_with(self.drv.root_path)
        set_filesystem.assert_called_with(self.drv.root_path, payload)
        get_service.assert_called_with('nfs')
        get_filesystem.return_value = {
            'mountPoint': '/path/to/volume',
            'nonBlockingMandatoryMode': True,
            'smartCompression': False,
            'isMounted': True
        }
        payload = {
            'nonBlockingMandatoryMode': False
        }
        set_filesystem.return_value = {}
        self.assertIsNone(self.drv.check_for_setup_error())
        get_filesystem.assert_called_with(self.drv.root_path)
        set_filesystem.assert_called_with(self.drv.root_path, payload)
        get_service.assert_called_with('nfs')
        get_filesystem.return_value = {
            'mountPoint': 'none',
            'nonBlockingMandatoryMode': False,
            'smartCompression': False,
            'isMounted': False
        }
        self.assertRaises(jsonrpc.NefException,
                          self.drv.check_for_setup_error)
        get_filesystem.return_value = {
            'mountPoint': '/path/to/volume',
            'nonBlockingMandatoryMode': False,
            'smartCompression': False,
            'isMounted': False
        }
        self.assertRaises(jsonrpc.NefException,
                          self.drv.check_for_setup_error)
        get_service.return_value = {
            'state': 'online'
        }
        self.assertRaises(jsonrpc.NefException,
                          self.drv.check_for_setup_error)

    @patch('%s.NefFilesystems.get' % RPC_PATH)
    def test__get_provisioned_capacity(self, fs_get):
        fs_get.return_value = {
            'path': 'pool1/nfs_share/123',
            'referencedQuotaSize': 1 * units.Gi
        }

        self.drv._get_provisioned_capacity()

        self.assertEqual(1 * units.Gi, self.drv.provisioned_capacity)

    @patch('%s._mount_filesystem' % DRV_PATH)
    @patch('%s.NefFilesystems.create' % RPC_PATH)
    @patch('%s.NefFilesystems.delete' % RPC_PATH)
    def test_create_share(self, delete_fs, create_fs, mount_fs):
        mount_path = '%s:/%s' % (self.cfg.nexenta_nas_host, SHARE_PATH)
        mount_fs.return_value = mount_path
        size = int(1 * units.Gi * 1.1)
        self.assertEqual(
            [{
                'path': mount_path,
                'id': 'share-uuid'
            }],
            self.drv.create_share(self.ctx, SHARE))

        payload = {
            'recordSize': 131072,
            'compressionMode': self.cfg.nexenta_dataset_compression,
            'path': SHARE_PATH,
            'referencedQuotaSize': size,
            'nonBlockingMandatoryMode': False,
            'referencedReservationSize': size
        }
        self.drv.nef.filesystems.create.assert_called_with(payload)

        mount_fs.side_effect = jsonrpc.NefException('some error')
        self.assertRaises(jsonrpc.NefException,
                          self.drv.create_share, self.ctx, SHARE)
        delete_payload = {'force': True}
        self.drv.nef.filesystems.delete.assert_called_with(
            SHARE_PATH, delete_payload)

    @patch('%s.NefFilesystems.mount' % RPC_PATH)
    @patch('%s.NefFilesystems.get' % RPC_PATH)
    def test_mount_filesystem(self, fs_get, fs_mount):
        mount_path = '%s:/%s' % (self.cfg.nexenta_nas_host, SHARE_PATH)
        fs_get.return_value = {
            'mountPoint': '/%s' % SHARE_PATH, 'isMounted': False}
        self.assertEqual(mount_path, self.drv._mount_filesystem(SHARE))
        self.drv.nef.filesystems.mount.assert_called_with(SHARE_PATH)

    def parse_fqdn(self, fqdn):
        address_mask = fqdn.strip().split('/', 1)
        address = address_mask[0]
        ls = {"allow": True, "etype": "fqdn", "entity": address}
        if len(address_mask) == 2:
            ls['mask'] = address_mask[1]
            ls['etype'] = 'network'
        return ls

    @ddt.data({'key': 'value'}, {})
    @patch('%s.NefNfs.list' % RPC_PATH)
    @patch('%s.NefNfs.set' % RPC_PATH)
    @patch('%s.NefFilesystems.acl' % RPC_PATH)
    def test_update_nfs_access(self, acl, nfs_set, nfs_list, list_data):
        security_contexts = {'securityModes': ['sys']}
        nfs_list.return_value = list_data
        rw_list = ['1.1.1.1/24', '2.2.2.2']
        ro_list = ['3.3.3.3', '4.4.4.4/30']
        security_contexts['readWriteList'] = []
        security_contexts['readOnlyList'] = []
        for fqdn in rw_list:
            ls = self.parse_fqdn(fqdn)
            if ls.get('mask'):
                ls['mask'] = int(ls['mask'])
            security_contexts['readWriteList'].append(ls)
        for fqdn in ro_list:
            ls = self.parse_fqdn(fqdn)
            if ls.get('mask'):
                ls['mask'] = int(ls['mask'])
            security_contexts['readOnlyList'].append(ls)

        self.assertIsNone(self.drv._update_nfs_access(SHARE, rw_list, ro_list))
        payload = {
            'flags': ['file_inherit', 'dir_inherit'],
            'permissions': ['full_set'],
            'principal': 'everyone@',
            'type': 'allow'
        }
        self.drv.nef.filesystems.acl.assert_called_with(SHARE_PATH, payload)
        payload = {'securityContexts': [security_contexts]}
        if list_data:
            self.drv.nef.nfs.set.assert_called_with(SHARE_PATH, payload)
        else:
            payload['filesystem'] = SHARE_PATH
            self.drv.nef.nfs.create.assert_called_with(payload)

    def test_update_nfs_access_bad_mask(self):
        security_contexts = {'securityModes': ['sys']}
        rw_list = ['1.1.1.1/24', '2.2.2.2/1a']
        ro_list = ['3.3.3.3', '4.4.4.4/30']
        security_contexts['readWriteList'] = []
        security_contexts['readOnlyList'] = []
        for fqdn in rw_list:
            security_contexts['readWriteList'].append(self.parse_fqdn(fqdn))
        for fqdn in ro_list:
            security_contexts['readOnlyList'].append(self.parse_fqdn(fqdn))

        self.assertRaises(exception.InvalidInput, self.drv._update_nfs_access,
                          SHARE, rw_list, ro_list)

    @patch('%s._update_nfs_access' % DRV_PATH)
    def test_update_access__ip_rw(self, update_nfs_access):
        access = {
            'access_type': 'ip',
            'access_to': '1.1.1.1',
            'access_level': 'rw'
        }

        self.assertIsNone(self.drv.update_access(
            self.ctx, SHARE, [access], None, None))
        self.drv._update_nfs_access.assert_called_with(SHARE, ['1.1.1.1'], [])

    @patch('%s._update_nfs_access' % DRV_PATH)
    def test_update_access__ip_ro(self, update_nfs_access):
        access = {
            'access_type': 'ip',
            'access_to': '1.1.1.1',
            'access_level': 'ro'
        }

        self.assertIsNone(self.drv.update_access(
            self.ctx, SHARE, [access], None, None))
        self.drv._update_nfs_access.assert_called_with(SHARE, [], ['1.1.1.1'])

    @ddt.data('rw', 'ro')
    def test_update_access__not_ip(self, access_level):
        access = {
            'access_type': 'username',
            'access_to': 'some_user',
            'access_level': access_level
        }
        self.assertRaises(exception.InvalidShareAccess, self.drv.update_access,
                          self.ctx, SHARE, [access], None, None)

    @patch('%s._get_capacity_info' % DRV_PATH)
    @patch('manila.share.driver.ShareDriver._update_share_stats')
    def test_update_share_stats(self, super_stats, info):
        info.return_value = (100, 90, 10)
        stats = {
            'vendor_name': 'Nexenta',
            'storage_protocol': 'NFS',
            'nfs_mount_point_base': self.cfg.nexenta_mount_point_base,
            'create_share_from_snapshot_support': True,
            'revert_to_snapshot_support': True,
            'snapshot_support': True,
            'driver_version': DRIVER_VERSION,
            'share_backend_name': self.cfg.share_backend_name,
            'pools': [{
                'compression': True,
                'pool_name': 'pool1',
                'total_capacity_gb': 100,
                'free_capacity_gb': 90,
                'provisioned_capacity_gb': 0,
                'max_over_subscription_ratio': 20.0,
                'reserved_percentage': (
                    self.cfg.reserved_share_percentage),
                'thin_provisioning': self.cfg.nexenta_thin_provisioning,
            }],
        }

        self.drv._update_share_stats()

        self.assertEqual(stats, self.drv._stats)

    def test_get_capacity_info(self):
        self.drv.nef.get.return_value = {
            'bytesAvailable': 9 * units.Gi, 'bytesUsed': 1 * units.Gi}

        self.assertEqual((10, 9, 1), self.drv._get_capacity_info())

    @patch('%s._set_reservation' % DRV_PATH)
    @patch('%s._set_quota' % DRV_PATH)
    @patch('%s.NefFilesystems.rename' % RPC_PATH)
    @patch('%s.NefFilesystems.get' % RPC_PATH)
    def test_manage_existing(self, fs_get, fs_rename, set_res, set_quota):
        fs_get.return_value = {'referencedQuotaSize': 1073741824}
        old_path = '%s:/%s' % (self.cfg.nexenta_nas_host, 'path_to_fs')
        new_path = '%s:/%s' % (self.cfg.nexenta_nas_host, SHARE_PATH)
        SHARE['export_locations'] = [{'path': old_path}]
        expected = {'size': 2, 'export_locations': [{
            'path': new_path
        }]}
        self.assertEqual(expected, self.drv.manage_existing(SHARE, None))
        fs_rename.assert_called_with('path_to_fs', {'newPath': SHARE_PATH})
        set_res.assert_called_with(SHARE, 2)
        set_quota.assert_called_with(SHARE, 2)
