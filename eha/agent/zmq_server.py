"""
"""

import traceback
from logging import getLogger
from zmq import REP, PUB, SNDMORE
from zmq.asyncio import Context

class Server:

    transaction = 0

    def __init__(self):
        self.logger = getLogger(__name__)
        self.context = Context()
        self.pub_sock = self.context.socket(PUB)
        self.pub_sock.bind("tcp://127.0.0.1:40086")
        self.running = True
        self.handlers = {}

    async def recv_rep_and_process(self):
        rep_sock = self.context.socket(REP)
        rep_sock.bind("tcp://127.0.0.1:40085")
        while self.running:
            if await rep_sock.poll(timeout=10) and self.running:
                msg = await rep_sock.recv_json()
                resp = await self.handle_req(msg)
                self.logger.debug('resp: %s', resp)
                await rep_sock.send_json(resp)
        rep_sock.close()

    def stop(self):
        self.logger.info('stopping zmq server ...')
        self.running = False
        self.pub_sock.close()

    async def handle_req(self, msg):
        action = msg.get('action', '')
        del msg['action']
        self.__class__.transaction += 1
        seq = self.__class__.transaction
        if action in self.handlers:
            self.logger.info('handle(seq: %d) %s, with %s', seq, action, msg)
            try:
                resp = await self.handlers[action](**msg)
                self.logger.info(
                    'handle(seq: %d) %s, return %s', seq, action, resp)
                return resp
            except RuntimeError as err:
                self.logger.error(
                    'error while handle(seq: %d) %s:\n%s',
                    seq, action, traceback.format_exc())
                return dict(error=1, message=str(err))
            except Exception as ex:
                self.logger.error(type(ex))
        else:
            self.logger.error('register with action: %s not exist', action)
            return dict(error=1, message='Invalud action: {}'.format(action))

    def register_callback(self, action, func):
        self.handlers[action] = func

    async def notify_service_event(self, service, data):
        await self.pub_sock.send_string(service, flags=SNDMORE)
        self.logger.debug('publish: %s', data)
        await self.pub_sock.send_json(data)
