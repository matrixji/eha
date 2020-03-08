"""
"""

from uuid import uuid4
import asyncio
import json
from logging import getLogger
from socket import gethostname
from zmq import REQ, SUB, SUBSCRIBE
from zmq.asyncio import Context


class Client:

    def __init__(self, name):
        self.name = name
        self.logger = getLogger(__name__)
        self.context = Context()
        self.req_sock = self.context.socket(REQ)
        self.sub_sock = self.context.socket(SUB)
        self.connect_req_sock()
        self.uuid = str(uuid4())

    def connect_req_sock(self):
        self.logger.debug('client start to connect ...')
        self.req_sock.connect("tcp://127.0.0.1:40085")
        self.logger.debug('client connected')

    async def register(self, active_count=1):
        msg = dict(
            action='register',
            name=self.name,
            uuid=self.uuid,
            active_count=active_count)
        await self.req_sock.send_json(msg)
        resp = await self.req_sock.recv_json()
        if resp.get('error') != 0:
            raise RuntimeError(str(resp))

    async def keepalive(self):
        msg = dict(
            action='keepalive',
            name=self.name,
            uuid=self.uuid)
        await self.req_sock.send_json(msg)
        self.logger.debug('waiting keepalive resp ...')
        resp = await self.req_sock.recv_json()
        self.logger.debug('resp for keepalive: %s', resp)
        if resp.get('error') != 0:
            raise RuntimeError(str(resp))

    async def unregister(self):
        msg = dict(
            action='unregister',
            name=self.name,
            uuid=self.uuid)
        await self.req_sock.send_json(msg)
        await self.req_sock.recv_json()

    def subscribe(self, topic=None):
        if not topic:
            topic = self.name
        self.sub_sock.connect("tcp://127.0.0.1:40086")
        self.sub_sock.setsockopt_string(SUBSCRIBE, topic)
        self.logger.info('subscribe with topic: %s', topic)

    async def fetch_event(self):
        _, msg = await self.sub_sock.recv_multipart()
        self.logger.info('event: %s', msg)
        event = json.loads(msg.decode('utf-8'))
        self.logger.info('event: %s', event)
        return event
