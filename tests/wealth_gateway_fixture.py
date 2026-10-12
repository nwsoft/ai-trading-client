"""Isolated real gateway for built-UI tests; no application runtime/providers."""
import socket
import tempfile
from pathlib import Path
from types import SimpleNamespace
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import uvicorn
from trading.insurance_workspace import InsuranceWorkspace
from web_platform.gateway import create_gateway_app
with tempfile.TemporaryDirectory(prefix='noah-wealth-ui-test-') as directory:
    vault=InsuranceWorkspace(Path(directory),'synthetic-built-ui-wealth')
    services=SimpleNamespace(insurance_workspace=lambda:vault,runtime_snapshot=lambda:{},account='synthetic-built-ui-wealth')
    app=create_gateway_app(token='synthetic-gateway-token-wealth-39211',application_services=services)
    @app.post('/qa/lock')
    def qa_lock():
        vault.lock()
        return {'locked':True}
    import threading
    release_busy=threading.Event()
    @app.post('/qa/busy')
    def qa_busy():
        release_busy.clear();started=threading.Event()
        def hold():
            with vault._mutex:
                started.set();release_busy.wait(5)
        threading.Thread(target=hold,daemon=True).start();started.wait(1)
        return {'busy':True}
    @app.post('/qa/release-busy')
    def qa_release_busy():
        release_busy.set()
        return {'released':True}
    sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(128)
    print(sock.getsockname()[1],flush=True)
    try:uvicorn.Server(uvicorn.Config(app,log_level='error',access_log=False)).run(sockets=[sock])
    finally:vault.lock();sock.close()
