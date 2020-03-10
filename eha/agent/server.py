"""
The server class for eha agent.
"""

import sys
import signal
from socket import gethostname
import logging
from logging import getLogger, StreamHandler, WARNING, ERROR, INFO, DEBUG
from logging.handlers import RotatingFileHandler
import asyncio
from asyncio import AbstractEventLoop, get_event_loop, wait, ensure_future
from aioetcd3.client import client as etcd_client
from aioetcd3 import transaction
from aioetcd3.kv import KV
from aioetcd3.help import range_prefix
from .config import load as load_config
from .zmq_server import Server as ZmqServer


class ServiceAgent:
    def __init__(self, name, uuid, etcd_client, active_count, timeout=30):
        self.logger = getLogger(__name__)
        self.name = name
        self.uuid = uuid
        self.etcd_client = etcd_client
        self.active_count = active_count
        self.timeout = timeout
        self.lease = None

    async def etcd_avaliable(self):
        try:
            await self.etcd_client.status()
            return True
        except Exception:
            return False

    async def register(self):
        """
        try register to etcd, if ok for create, return True

        etcd path:

        /eha/services/<name>/<index>/current:
            current service instance node
        """
        if not await self.etcd_avaliable():
            return True
        for index in range(self.active_count):
            key_curr = '/eha/service/{}/{}/current'.format(self.name, index)
            self.lease = await self.etcd_client.grant_lease(ttl=self.timeout)
            success, _ = await self.etcd_client.txn(compare=[
                transaction.Version(key_curr) > 0,
                transaction.Value(key_curr) != self.uuid
            ], success=[
            ], fail=[
                KV.put.txn(key_curr, self.uuid, lease=self.lease)
            ])
            if not success:
                self.logger.info('created etcd %s: %s', key_curr, self.uuid)
                # means key write success, confirm with read
                value, _ = await self.etcd_client.get(key_curr)
                if value.decode('utf-8') == self.uuid:
                    self.logger.info(
                        'service register with index=%d, uuid=%s, timeout=%d',
                        index, self.uuid, self.timeout)
                    return True
        return False

    async def keepalive(self):
        if await self.etcd_avaliable():
            await self.etcd_client.refresh_lease(self.lease)
            for index in range(self.active_count):
                key_curr = '/eha/service/{}/{}/current'.format(self.name, index)
                value, _ = await self.etcd_client.get(key_curr)
                if value and value.decode('utf-8') == self.uuid:
                    self.logger.info('keepalive for %s success', self.uuid)
                    return
            raise RuntimeError('Keepalive failed, maybe already expired')

    async def unregister(self):
        if await self.etcd_avaliable():
            for index in range(self.active_count):
                key_curr = '/eha/service/{}/{}/current'.format(self.name, index)
                success, _ = await self.etcd_client.txn(compare=[
                    transaction.Version(key_curr) > 0,
                    transaction.Value(key_curr) == self.uuid
                ], success=[
                    KV.delete.txn(key_curr)
                ], fail=[
                ])
                if success:
                    self.logger.info(
                        'service unregister: index=%d, uuid=%s', index, self.uuid)


class Server:
    def __init__(self, node=None):
        self.logger = getLogger(__name__)
        self.cfg = load_config()
        self.zmq_server = ZmqServer()
        self.node = node
        if not self.node:
            self.node = gethostname()
        self.services = dict()
        self.init_zmq_handlers()
        self.etcd_client = self.connect_etcd()
        self.watch_task = None

    def init_zmq_handlers(self):
        self.zmq_server.register_callback(
            'register', self.handler_zmq_register)
        self.zmq_server.register_callback(
            'unregister', self.handler_zmq_unregister)
        self.zmq_server.register_callback(
            'keepalive', self.handler_zmq_keepalive)

    def connect_etcd(self):
        servers = self.cfg.get('etcd_servers', '127.0.0.1:2379')
        self.logger.info('Using etcd server with: %s ...', servers)
        return etcd_client(
            endpoint=servers, timeout=int(self.cfg.get('etcd_timeout', 3)))

    async def watch_service_event(self):
        etcd_client = self.connect_etcd()
        prefix = range_prefix('/eha/service/')
        while True:
            try:
                async with etcd_client.watch_scope(prefix) as resp:
                    async for event in resp:
                        await self.handle_service_event(event)
            except asyncio.CancelledError:
                break
            except Exception:
                self.logger.warning('seems etcd not avaliable, wait 5 seconds')
                await asyncio.sleep(5)

    async def handle_service_event(self, event):
        key_path = event.key.decode('utf-8')
        keys = list(filter(len, key_path.split('/')))
        if len(keys) != 5 or keys[-1] != 'current':
            self.logger.warning('ignore key event for: %s', key_path)
            return
        service = keys[2]
        index = int(keys[3])
        self.logger.info('service: %s#%d %s', service, index, event.type)
        uuid = event.value.decode('utf-8')
        await self.zmq_server.notify_service_event(service, dict(
            service=service, uuid=uuid, event=event.type, index=index
        ))

    async def stop(self):
        self.logger.info('stopping server ...')
        self.zmq_server.stop()
        await self.etcd_client.close()
        self.etcd_client = None
        if self.watch_task:
            self.watch_task.cancel()

    def run_tasks(self):
        task = ensure_future(self.zmq_server.recv_rep_and_process())
        self.watch_task = ensure_future(self.watch_service_event())
        return task, self.watch_task

    def run(self):
        loop = get_event_loop()
        loop.run_until_complete(wait(self.run_tasks()))

    def cleanup_services(self):
        service_names_to_remove = []
        for name, svcs in self.services.items():
            if not svcs:
                service_names_to_remove.append(name)
        for name in service_names_to_remove:
            del self.services[name]

    async def handler_zmq_register(self, name, uuid, active_count=1):
        """
        register service to etcd:
        """
        if name in self.services and uuid in self.services[name]:
            service = self.services[name][uuid]
        else:
            service = ServiceAgent(
                name, uuid, self.etcd_client, active_count,
                timeout=int(self.cfg.get('service_keepalive_timeout', 30)))
        if await service.register():
            self.services.setdefault(name, dict())
            self.services[name][uuid] = service
            return await self.handler_zmq_keepalive(name, uuid)
        raise RuntimeError('Register failed, maybe already exists')

    async def handler_zmq_keepalive(self, name, uuid):
        """
        """
        if name in self.services and uuid in self.services[name]:
            service = self.services[name][uuid]
            try:
                await service.keepalive()
                return dict(error=0, message='success')
            except RuntimeError as err:
                del self.services[name][uuid]
                self.cleanup_services()
                raise err
        raise RuntimeError('Keepalive failed, seems service not exist')

    async def handler_zmq_unregister(self, name, uuid):
        if name in self.services and uuid in self.services[name]:
            service = self.services[name][uuid]
            del self.services[name][uuid]
            self.cleanup_services()
            await service.unregister()
            return dict(error=0, message='success')


def init_log():
    level_mapping = {
        'info': INFO,
        'debug': DEBUG,
        'warning': WARNING,
        'error': WARNING,
    }
    cfg = load_config()
    logger = getLogger(__name__)
    filename = cfg.get('log_file_path', '/var/log/eha-agent.log')
    filebytes = int(cfg.get('log_file_size', 10240000))
    count = int(cfg.get('log_file_count', 10))
    level = cfg.get('log_level', 'info').lower()
    log_format = cfg.get(
        'log_format',
        '%(asctime)s %(levelname)s %(filename)s:%(lineno)d %(message)s')
    file_handler = RotatingFileHandler(
        filename, maxBytes=filebytes, backupCount=count)
    stream_handler = StreamHandler(sys.stdout)
    formatter = logging.Formatter(log_format, '%Y-%m-%d %H:%M:%S')
    file_handler.setFormatter(formatter)
    stream_handler.setFormatter(formatter)
    logger.setLevel(level_mapping.get(level, INFO))
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)


def main():
    init_log()
    server = Server()
    server.run()
