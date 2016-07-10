# Copyright 2016 Nexenta Systems, Inc.
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

import mock
from mock import patch
from oslo_serialization import jsonutils
from oslo_utils import units
import requests


from manila import context
from manila import exception
from manila.share import configuration as conf
from manila.share.drivers.nexenta.ns5 import jsonrpc
from manila.share.drivers.nexenta.ns5 import nexenta_nas
from manila import test

PATH_TO_RPC = 'manila.share.drivers.nexenta.ns5.jsonrpc.NexentaJSONProxy'
DRV_PATH = 'manila.share.drivers.nexenta.ns5.nexenta_nas.NexentaNasDriver'


class TestNexentaNasDriver(test.TestCase):

    def setUp(self):
        def _safe_get(opt):
            return getattr(self.cfg, opt)
        super(TestNexentaNasDriver, self).setUp()
        self.ctx = context.get_admin_context()
        self.cfg = conf.Configuration(None)
        self.mock_object(
            self.cfg, 'safe_get', mock.Mock(side_effect=_safe_get))
        self.cfg.nexenta_host = '1.1.1.1'
        self.cfg.nexenta_rest_port = 8080
        self.cfg.nexenta_rest_protocol = 'auto'
        self.cfg.nexenta_pool = 'pool1'
        self.cfg.reserved_share_percentage = 0
        self.cfg.nexenta_nfs_share = 'nfs_share'
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

        self.drv = nexenta_nas.NexentaNasDriver(configuration=self.cfg)
        self.drv.do_setup(self.ctx)
        self.mock_rpc = self.mock_class(PATH_TO_RPC)
        self.pool_name = self.cfg.nexenta_pool
        self.fs_prefix = self.cfg.nexenta_nfs_share

    def test_backend_name(self):
        self.assertEqual('NexentaStor5', self.drv.backend_name)

    def test_check_for_setup_error(self):
        self.drv.nef.get.return_value = None
        self.assertRaises(LookupError, self.drv.check_for_setup_error)
        self.drv.nef.get.return_value = {
            'data': [{'filesystem': 'pool1/nfs_share'}]
        }
        self.assertIsNone(self.drv.check_for_setup_error())
        self.drv.nef.get.return_value = {'data': [{'filesystem': 'asd'}]}
        self.assertRaises(LookupError, self.drv.check_for_setup_error)

    def test_create_share(self):
        share = {'name': 'share', 'size': 1}
        self.assertEqual(
            {
                'path': '{}:/{}/{}/{}'.format(
                    self.cfg.nexenta_host, self.pool_name,
                    self.fs_prefix, share['name'])
            },
            self.drv.create_share(self.ctx, share))

    @patch('%s.delete_share' % DRV_PATH)
    @patch('%s._add_permission' % DRV_PATH)
    def test_create_share__error_on_add_permission(
            self, add_permission_mock, delete_share):
        share = {'name': 'share', 'size': 1}
        add_permission_mock.side_effect = exception.NexentaException(
            'An error occurred while adding permission')
        delete_share.side_effect = exception.NexentaException(
            'An error occurred while deleting')
        self.assertRaises(
            exception.NexentaException, self.drv.create_share, self.ctx, share)

    def test_create_share_from_snapshot(self):
        share = {'name': 'share'}
        snapshot = {'name': 'share@first', 'share_name': 'share'}
        self.assertEqual(
            {
                'path': '{}:/{}/{}/{}'.format(
                    self.cfg.nexenta_host, self.pool_name,
                    self.fs_prefix, share['name'])
            },
            self.drv.create_share_from_snapshot(self.ctx, share, snapshot)
        )

        url = ('storage/pools/%(pool)s/'
               'filesystems/%(fs)s/snapshots/%(snap)s/clone') % {
            'pool': self.pool_name,
            'fs': nexenta_nas.PATH_DELIMITER.join(
                [self.fs_prefix, snapshot['share_name']]),
            'snap': snapshot['name']}
        path = '/'.join([self.pool_name, self.fs_prefix, share['name']])
        data = {'targetPath': path}
        self.drv.nef.post.assert_any_call(url, data)

    @patch('%s.delete_share' % DRV_PATH)
    @patch('%s._add_permission' % DRV_PATH)
    def test_create_share_from_snapshot__add_permission_error(
            self, add_permission_mock, delete_share):
        share = {'name': 'share'}
        snapshot = {'share_name': 'share', 'name': 'share@first'}
        delete_share.side_effect = exception.NexentaException(
            'An error occurred while deleting')
        add_permission_mock.side_effect = exception.NexentaException(
            'Some exception')
        self.assertRaises(
            exception.NexentaException, self.drv.create_share_from_snapshot,
            self.ctx, share, snapshot)

    @patch('%s._add_permission' % DRV_PATH)
    def test_create_share_from_snapshot__add_permission_error_error(
            self, add_permission_mock):
        share = {'name': 'share'}
        snapshot = {'share_name': 'share', 'name': 'share@first'}
        add_permission_mock.side_effect = exception.NexentaException(
            'Some exception')
        self.drv.nef.delete.side_effect = exception.NexentaException(
            'Some exception 2')
        self.assertRaises(
            exception.NexentaException, self.drv.create_share_from_snapshot,
            self.ctx, share, snapshot)

    def test_delete_share(self):
        self.mock_rpc.side_effect = exception.NexentaException(
            'err', code='EEXIST')
        share = {'name': 'share'}
        url = 'storage/pools/%(pool)s/filesystems/%(fs)s' % {
            'pool': self.pool_name,
            'fs': nexenta_nas.PATH_DELIMITER.join(
                [self.fs_prefix, share['name']])
        }
        url += '?snapshots=true'
        self.assertIsNone(self.drv.delete_share(self.ctx, share))
        self.mock_rpc.side_effect = exception.NexentaException(
            'err', code='somecode')
        self.assertRaises(
            exception.NexentaException, self.drv.delete_share, self.ctx, share)

    def test_extend_share(self):
        share = {'name': 'share'}
        new_size = 1
        self.drv.extend_share(share, new_size)
        quota = new_size * units.Gi
        data = {
            'reservationSize': quota
        }
        url = 'storage/pools/{}/filesystems/{}%2F{}'.format(
            self.pool_name, self.fs_prefix, share['name'])
        self.drv.nef.post.assert_called_with(url, data)

    def test_shrink_share(self):
        share = {'name': 'share'}
        new_size = 5
        self.drv.shrink_share(share, new_size)
        quota = new_size * units.Gi
        data = {
            'reservationSize': quota
        }
        url = 'storage/pools/{}/filesystems/{}%2F{}'.format(
            self.pool_name, self.fs_prefix, share['name'])
        self.drv.nef.post.assert_called_with(url, data)

    def test_create_snapshot(self):
        snapshot = {'share_name': 'share', 'name': 'share@first'}
        self.drv.create_snapshot(self.ctx, snapshot)
        url = 'storage/pools/%(pool)s/filesystems/%(fs)s/snapshots' % {
            'pool': self.pool_name,
            'fs': nexenta_nas.PATH_DELIMITER.join(
                [self.fs_prefix, snapshot['share_name']])
        }
        data = {'name': snapshot['name']}
        self.drv.nef.post.assert_called_with(url, data)

    def test_delete_snapshot(self):
        self.mock_rpc.side_effect = exception.NexentaException(
            'err', code='ENOENT')
        snapshot = {'share_name': 'share', 'name': 'share@first'}
        self.assertIsNone(self.drv.delete_snapshot(self.ctx, snapshot))
        self.mock_rpc.side_effect = exception.NexentaException(
            'err', code='somecode')
        self.assertRaises(
            exception.NexentaException, self.drv.delete_snapshot,
            self.ctx, snapshot)

    def build_access_security_context(self, level, ip, mask=None):
        ls = [{"allow": True, "etype": "network", "entity": ip}]
        if mask is not None:
            ls[0]['mask'] = mask
        new_sc = {
            "securityModes": ["sys"],
        }
        if level == 'rw':
            new_sc['readWriteList'] = ls
        elif level == 'ro':
            new_sc['readOnlyList'] = ls
        else:
            raise exception.ManilaException('Wrong access level')
        return new_sc

    def test_update_access__unsupported_access_type(self):
        share = {'name': 'share'}
        access = {
            'access_type': 'group',
            'access_to': 'ordinary_users',
            'access_level': 'rw'
        }
        self.assertRaises(exception.InvalidShareAccess, self.drv.update_access,
                          self.ctx, share, [access], None, None)

    def test_update_access__cidr(self):
        share = {'name': 'share'}
        access = {
            'access_type': 'ip',
            'access_to': '1.1.1.1/24',
            'access_level': 'rw'
        }
        url = 'nas/nfs/' + nexenta_nas.PATH_DELIMITER.join(
            (self.pool_name, self.fs_prefix, share['name']))
        self.drv.nef.get.return_value = {}
        self.drv.update_access(self.ctx, share, [access], None, None)
        self.drv.nef.put.assert_called_with(
            url, {'securityContexts': [
                self.build_access_security_context('rw', '1.1.1.1', 24)]})

    def test_update_access__ip(self):
        share = {'name': 'share'}
        access = {
            'access_type': 'ip',
            'access_to': '1.1.1.1',
            'access_level': 'rw'
        }
        url = 'nas/nfs/' + nexenta_nas.PATH_DELIMITER.join(
            (self.pool_name, self.fs_prefix, share['name']))
        self.drv.nef.get.return_value = {}
        self.drv.update_access(self.ctx, share, [access], None, None)
        self.drv.nef.put.assert_called_with(
            url, {'securityContexts': [
                self.build_access_security_context('rw', '1.1.1.1')]})

    def test_update_access__cidr_wrong_mask(self):
        share = {'name': 'share'}
        access = {
            'access_type': 'ip',
            'access_to': '1.1.1.1/aa',
            'access_level': 'rw'
        }
        self.assertRaises(exception.InvalidInput, self.drv.update_access,
                          self.ctx, share, [access], None, None)
        access = {
            'access_type': 'ip',
            'access_to': '1.1.1.1/aa',
            'access_level': 'ro'
        }
        self.assertRaises(exception.InvalidInput, self.drv.update_access,
                          self.ctx, share, [access], None, None)

    def test_update_access__one_ip_ro_add_rule_to_existing(self):
        share = {'name': 'share'}
        access = [
            {
                'access_type': 'ip',
                'access_to': '5.5.5.5',
                'access_level': 'ro'
            },
            {
                'access_type': 'ip',
                'access_to': '1.1.1.1/24',
                'access_level': 'rw'
            }
        ]
        url = 'nas/nfs/' + nexenta_nas.PATH_DELIMITER.join(
            (self.pool_name, self.fs_prefix, share['name']))
        sc = self.build_access_security_context('rw', '1.1.1.1', 24)
        self.drv.nef.get.return_value = {'securityContexts': [sc]}
        self.drv.update_access(self.ctx, share, access, None, None)
        self.drv.nef.put.assert_called_with(
            url, {'securityContexts': [
                sc, self.build_access_security_context('ro', '5.5.5.5')]})

    def test_update_access__one_ip_ro_add_rule_to_existing_wrong_mask(
            self):
        share = {'name': 'share'}
        access = [
            {
                'access_type': 'ip',
                'access_to': '5.5.5.5/aa',
                'access_level': 'ro'
            },
            {
                'access_type': 'ip',
                'access_to': '1.1.1.1/24',
                'access_level': 'rw'
            }
        ]
        sc = self.build_access_security_context('rw', '1.1.1.1', 24)
        self.drv.nef.get.return_value = {'securityContexts': [sc]}
        self.assertRaises(exception.InvalidInput, self.drv.update_access,
                          self.ctx, share, access, None, None)

    @patch('%s._get_capacity_info' % DRV_PATH)
    @patch('manila.share.driver.ShareDriver._update_share_stats')
    def test_update_share_stats(self, super_stats, info):
        info.return_value = (100, 90, 10)
        stats = {
            'vendor_name': 'Nexenta',
            'storage_protocol': 'NFS',
            'total_capacity_gb': 100,
            'free_capacity_gb': 90,
            'provisioned_capacity_gb': 10,
            'max_over_subscription_ratio': 20.0,
            'reserved_percentage': (
                self.cfg.reserved_share_percentage),
            'nfs_mount_point_base': self.cfg.nexenta_mount_point_base,
            'thin_provisioning': self.cfg.nexenta_thin_provisioning,
            'driver_version': '1.0',
            'share_backend_name': self.cfg.share_backend_name
        }
        self.drv._update_share_stats()
        self.assertEqual(stats, self.drv._stats)

    def test_get_capacity_info(self):
        self.drv.nef.get.return_value = {
            'bytesAvailable': 10 * units.Gi, 'bytesUsed': 1 * units.Gi}
        self.assertEqual((10, 9, 1), self.drv._get_capacity_info('path'))


class TestNexentaJSONProxy(test.TestCase):

    def __init__(self, method):
        super(TestNexentaJSONProxy, self).__init__(method)

    @patch('%s.https_auth' % PATH_TO_RPC)
    @patch('requests.Response.close')
    @patch('requests.Session.get')
    @patch('requests.Session.post')
    def test_call(self, post, get, close, auth):
        nef_get = jsonrpc.NexentaJSONProxy(
            'http', '1.1.1.1', '8080', 'user', 'pass', method='get')
        nef_post = jsonrpc.NexentaJSONProxy(
            'https', '1.1.1.1', '8080', 'user', 'pass', method='post')
        data = {'key': 'value'}
        get.return_value = requests.Response()
        post.return_value = requests.Response()

        get.return_value.__setstate__({
            'status_code': 200, '_content': jsonutils.dumps(data)})
        self.assertEqual({'key': 'value'}, nef_get('url'))

        get.return_value.__setstate__({
            'status_code': 201, '_content': ''})
        self.assertIsNone(nef_get('url'))

        data2 = {'links': [{'href': 'redirect_url'}]}
        post.return_value.__setstate__({
            'status_code': 202, '_content': jsonutils.dumps(data2)})
        get.return_value.__setstate__({
            'status_code': 200, '_content': jsonutils.dumps(data)})
        self.assertEqual({'key': 'value'}, nef_post('url'))

        get.return_value.__setstate__({
            'status_code': 200, '_content': ''})
        self.assertIsNone(nef_post('url', data))

        get.return_value.__setstate__({
            'status_code': 400,
            '_content': jsonutils.dumps({'code': 'ENOENT'})})
        self.assertRaises(exception.NexentaException, lambda: nef_get('url'))

        get.return_value.__setstate__({
            'status_code': 401,
            '_content': jsonutils.dumps({'code': 'unauthorized'})})
        self.assertRaises(exception.NexentaException, lambda: nef_get('url'))

        auth.return_value = {'token': 'tok'}
        post.return_value.__setstate__({
            'status_code': 401,
            '_content': jsonutils.dumps({'code': 'unauthorized'})})
        self.assertRaises(exception.NexentaException, lambda: nef_post('url'))

    @patch('requests.Response.close')
    @patch('requests.Session.post')
    def test_auth(self, post, close):
        httpsdata = {'token': 'tok'}
        post.return_value = requests.Response()
        post.return_value.__setstate__({
            'status_code': 200, '_content': jsonutils.dumps(httpsdata)})
        nef_get = jsonrpc.NexentaJSONProxy(
            'http', '1.1.1.1', '8080', 'user', 'pass', method='get')
        https_auth = nef_get.https_auth()
        self.assertEqual('tok', https_auth)
