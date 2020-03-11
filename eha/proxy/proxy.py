import sys
import argparse
import asyncio
from asyncio import subprocess
import logging
import signal
from logging import getLogger, StreamHandler, WARNING, ERROR, INFO, DEBUG
from logging.handlers import RotatingFileHandler
from asyncio import subprocess
import sdnotify
from ..client.client import Client


def init_log(name, log_file=None):
    logger = getLogger(__name__)
    if log_file:
        filename = log_file
    else:
        filename = '/var/log/eha-proxy-{}.log'.format(name)
    filebytes = 10240000
    count = 10
    log_format = '%(asctime)s %(levelname)s %(filename)s:%(lineno)d %(message)s'
    file_handler = RotatingFileHandler(
        filename, maxBytes=filebytes, backupCount=count)
    stream_handler = StreamHandler(sys.stdout)
    formatter = logging.Formatter(log_format, '%Y-%m-%d %H:%M:%S')
    file_handler.setFormatter(formatter)
    stream_handler.setFormatter(formatter)
    logger.setLevel(INFO)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)


class Runner:
    def __init__(self, name, command, systemd=False):
        self.name = name
        self.command = command
        self.logger = getLogger(__name__)
        self.client = Client(name)
        self.process = None
        self.process_running = False
        self.subscribed = False
        self.systemd = systemd
        self.task_client_run = None

    async def client_wait_service_member_delete(self):
        if not self.subscribed:
            self.client.subscribe()
            self.subscribed = True
        while True:
            try:
                event = await self.client.fetch_event()
                if event['service'] == self.name and event['event'] == 'DELETE':
                    self.logger.info('receive delete event from agent, again ...')
                    return True
            except asyncio.CancelledError:
                return False


    async def wait_process_done(self, future):
        await self.process.wait()
        future.set_result('done')

    async def client_run_keepalive(self):
        """
        return if continue
        """
        while self.process_running:
            # wait process exit
            failure_count = 0
            future = asyncio.Future()
            wait_task = asyncio.ensure_future(self.wait_process_done(future))
            try:
                await asyncio.wait_for(future, timeout=10)
                self.logger.info('process exit.')
                self.process_running = False
            except asyncio.TimeoutError:
                wait_task.cancel()
                try:
                    await self.client.keepalive()
                    failure_count = 0
                except RuntimeError:
                    # keepalive failed.
                    failure_count += 1
                    if failure_count > 3:
                        break
        await self.client.unregister()
        if self.process_running:
            self.logger.info('keepalive failed, but process running, killing ...')
            self.process.terminate()

    async def client_run(self):
        while not self.process:
            try:
                self.logger.info('start to register to eha-agent ...')
                await self.client.register()
                self.logger.info('register success.')
                self.logger.info('run process: %s', self.command)
                self.process = await subprocess.create_subprocess_shell(
                    self.command, stdout=sys.stdout, stderr=sys.stderr
                )
                if self.systemd:
                    sdnotify.SystemdNotifier().notify("READY=1")
                self.process_running = True
                await self.client_run_keepalive()
            except RuntimeError as err:
                self.logger.warning('runtime error: %s', err)
                do_continue = await self.client_wait_service_member_delete()
                if not do_continue:
                    break
            except Exception as error:
                self.logger.error('unexpected error: %s', error)

    def do_exit(self):
        if self.process:
            self.process.terminate()
        elif self.task_client_run:
            self.task_client_run.cancel()

    def run(self):
        if not self.command:
            self.logger.error('command not provided')
            exit(1)
        loop = asyncio.get_event_loop()
        self.task_client_run = asyncio.ensure_future(self.client_run())
        loop.add_signal_handler(signal.SIGTERM, self.do_exit)
        loop.add_signal_handler(signal.SIGINT, self.do_exit)
        loop.run_until_complete(asyncio.wait([
            self.task_client_run,
        ]))


def main():
    parser = argparse.ArgumentParser('eha-proxy')
    parser.add_argument('--name', help='service name')
    parser.add_argument('--log-file', help='log file', default=None)
    parser.add_argument(
        '--systemd', help='using systemd sd_notify',
        default=False, action='store_true')

    parser.add_argument('command', help='command to execute')
    opts = parser.parse_args()
    init_log(opts.name, log_file=opts.log_file)
    Runner(opts.name, opts.command, systemd=opts.systemd).run()