import sys
import shutil
from time import sleep
from subprocess import Popen, PIPE
from os.path import join, dirname, abspath
import pytest

source_dir = join(dirname(abspath(__file__)), 'src')
if source_dir not in sys.path:
    sys.path.insert(0, source_dir)


@pytest.fixture(name='etcd')
def etcd_fixtures():
    class Etcd:
        def __init__(self):
            self.test_data = join(dirname(abspath(__file__)), 'test.data')
            shutil.rmtree(self.test_data, ignore_errors=True)
            self.port = 52379
            self.fp = Popen([
                'etcd',
                '--data-dir',
                self.test_data,
                '--advertise-client-urls',
                'http://127.0.0.1:{}'.format(self.port),
                '--listen-peer-urls',
                'http://127.0.0.1:52380',
                '--listen-client-urls',
                'http://127.0.0.1:{}'.format(self.port)],
                stdout=PIPE, stderr=PIPE
                )

        @property
        def address(self):
            return '127.0.0.1:{}'.format(self.port)

        def __del__(self):
            shutil.rmtree(self.test_data, ignore_errors=True)

    etcd_instance = Etcd()
    sleep(0.5)
    yield etcd_instance
    etcd_instance.fp.kill()
    etcd_instance.fp.wait()
