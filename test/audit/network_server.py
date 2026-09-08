from contextlib import contextmanager
from pathlib import Path
from threading import Thread
from time import sleep

from scripts.serve_https import https_server
from test.e2e.conftest import QuietHandler


@contextmanager
def fault_server():
    fault={"path":"", "status":None, "delay":0, "hits":0}
    class Handler(QuietHandler):
        def do_GET(self):
            if fault["path"] and fault["path"] in self.path:
                fault["hits"]+=1
                delay,status=fault["delay"],fault["status"]
                if delay: sleep(delay)
                if status:
                    self.send_error(status,"Injected acceptance failure")
                    return
            super().do_GET()
    server=https_server(Path(__file__).parents[2]/"build",handler=Handler)
    worker=Thread(target=server.serve_forever,daemon=True);worker.start()
    try:yield f"https://127.0.0.1:{server.server_port}/",fault
    finally:server.shutdown();server.server_close();worker.join(timeout=5)
