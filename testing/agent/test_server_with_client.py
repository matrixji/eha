
import asyncio
import pytest
from eha.agent.server import Server
from eha.client.client import Client


def test_register_ok(monkeypatch, etcd):

    with monkeypatch.context() as patch:
        patch.setenv('EHA_AGENT_SERVICE_KEEPALIVE_TIMEOUT', '1')
        patch.setenv('EHA_AGENT_ETCD_SERVERS', etcd.address)

        server = Server()

        async def run_client():
            c = Client('test')
            await c.register()
            await server.stop()

        tasks = [asyncio.ensure_future(run_client())]
        tasks.extend(server.run_tasks())
        asyncio.get_event_loop().run_until_complete(asyncio.wait(tasks))


def test_register_for_2_clients(monkeypatch, etcd):

    with monkeypatch.context() as patch:
        patch.setenv('EHA_AGENT_SERVICE_KEEPALIVE_TIMEOUT', '3')
        patch.setenv('EHA_AGENT_ETCD_SERVERS', etcd.address)

        server = Server()

        async def run_client():
            c = Client('test')
            await c.register()
            await asyncio.sleep(1)
            await c.unregister()
            await asyncio.sleep(1)
            await server.stop()  
        
        async def run_2nd_client():
            c = Client('test')
            await asyncio.sleep(0.5)
            with pytest.raises(RuntimeError):
                await c.register()
            await asyncio.sleep(1)
            await c.register()

        async def run_server():
            await server.run()

        tasks = [
            asyncio.ensure_future(run_client()),
            asyncio.ensure_future(run_2nd_client()),
        ]
        tasks.extend(server.run_tasks())
        asyncio.get_event_loop().run_until_complete(asyncio.wait(tasks))


def test_register_after_timeout(monkeypatch, etcd):

    with monkeypatch.context() as patch:
        patch.setenv('EHA_AGENT_SERVICE_KEEPALIVE_TIMEOUT', '1')
        patch.setenv('EHA_AGENT_ETCD_SERVERS', etcd.address)

        server = Server()

        async def run_client():
            c = Client('test')
            await c.register()
            await asyncio.sleep(3)
            await server.stop()

        tasks = [asyncio.ensure_future(run_client())]
        tasks.extend(server.run_tasks())
        asyncio.get_event_loop().run_until_complete(asyncio.wait(tasks))


def test_keepalive_after_timeout(monkeypatch, etcd):

    with monkeypatch.context() as patch:
        patch.setenv('EHA_AGENT_SERVICE_KEEPALIVE_TIMEOUT', '3')
        patch.setenv('EHA_AGENT_ETCD_SERVERS', etcd.address)

        server = Server()

        async def run_client():
            c = Client('test')
            await c.register()
            await asyncio.sleep(1)
            await c.keepalive()
            await asyncio.sleep(1)
            await c.keepalive()
            await asyncio.sleep(1)
            await c.keepalive()
            await asyncio.sleep(4)
            with pytest.raises(RuntimeError):
                await c.keepalive()
            await server.stop()

        tasks = [asyncio.ensure_future(run_client())]
        tasks.extend(server.run_tasks())
        asyncio.get_event_loop().run_until_complete(asyncio.wait(tasks))


def test_fetch_event_events_from_server(monkeypatch, etcd):
    
    with monkeypatch.context() as patch:
        patch.setenv('EHA_AGENT_SERVICE_KEEPALIVE_TIMEOUT', '1')
        patch.setenv('EHA_AGENT_ETCD_SERVERS', etcd.address)

        server = Server()
        client = Client('test')
        events = []

        async def client_fetch_events(events):
            client.subscribe()
            while True:
                event = await client.fetch_event()
                events.append(event)
        fetch_task = asyncio.ensure_future(client_fetch_events(events))

        async def run_client():
            await asyncio.sleep(1)
            await client.register()
            await asyncio.sleep(3)
            await server.stop()
            fetch_task.cancel()

        tasks = [asyncio.ensure_future(run_client()), fetch_task]
        tasks.extend(server.run_tasks())
        asyncio.get_event_loop().run_until_complete(asyncio.wait(tasks))
        assert len(events) == 2
        assert events[0]['event'] == 'CREATE'
        assert events[1]['event'] == 'DELETE'