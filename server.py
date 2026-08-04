from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
import json
import uvicorn
import asyncio
import os

app = FastAPI()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# Global State Variables
agent_connection: WebSocket = None
web_clients = set()
last_server_config = None

@app.get("/", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    # Render giao diện Web Dashboard
    return templates.TemplateResponse(request=request, name="index.html")

@app.websocket("/ws/web")
async def websocket_web(websocket: WebSocket):
    global agent_connection, last_server_config
    # Endpoint cho trình duyệt Web kết nối tới
    await websocket.accept()
    web_clients.add(websocket)
    
    # ⚡ Yêu cầu Agent gửi lại toàn bộ cấu hình & thống kê lập tức cho tab Web mới mở
    if agent_connection:
        try:
            await agent_connection.send_text(json.dumps({"type": "get_config"}))
            await agent_connection.send_text(json.dumps({"type": "get_code_stats"}))
        except Exception:
            pass

    try:
        while True:
            # Nhận lệnh từ giao diện Web (VD: bấm nút Chạy GĐ1)
            data = await websocket.receive_text()
            
            try:
                msg = json.loads(data)
                if msg.get("type") == "save_config" and msg.get("config"):
                    last_server_config = msg.get("config")
                elif msg.get("type") == "get_config" and not agent_connection:
                    if last_server_config:
                        await websocket.send_text(json.dumps({"type": "config", "data": last_server_config}))
            except Exception:
                pass

            # Gửi lệnh đó thẳng về Agent (nếu Agent đang online)
            if agent_connection:
                await agent_connection.send_text(data)
            else:
                await websocket.send_text(json.dumps({"type": "log", "data": "\n\r\033[1;31m[!] Lỗi: Máy tính ở nhà (Agent) chưa kết nối tới Server!\033[0m\n\r"}))
    except WebSocketDisconnect:
        web_clients.discard(websocket)
    except Exception:
        web_clients.discard(websocket)

@app.websocket("/ws/agent")
async def websocket_agent(websocket: WebSocket):
    # Endpoint cho file agent.py ở nhà kết nối tới
    global agent_connection, last_server_config
    await websocket.accept()
    agent_connection = websocket
    
    # Báo cho Web biết Agent đã online
    for web in list(web_clients):
        try:
            await web.send_text(json.dumps({"type": "log", "data": "\n\r\033[1;32m[+] Máy tính Agent đã kết nối thành công!\033[0m\n\r"}))
        except Exception:
            web_clients.discard(web)
    
    try:
        while True:
            # Nhận dữ liệu (log, status, screenshot) từ Agent
            data = await websocket.receive_text()
            
            try:
                msg = json.loads(data)
                if msg.get("type") == "config" and msg.get("data"):
                    last_server_config = msg.get("data")
            except Exception:
                pass

            # Broadcast dữ liệu đó cho tất cả các tab Web đang mở
            for web in list(web_clients):
                try:
                    await web.send_text(data)
                except Exception:
                    web_clients.discard(web)
    except WebSocketDisconnect:
        agent_connection = None
        for web in list(web_clients):
            try:
                await web.send_text(json.dumps({"type": "log", "data": "\n\r\033[1;31m[-] Máy tính Agent đã ngắt kết nối!\033[0m\n\r"}))
            except Exception:
                web_clients.discard(web)
    except Exception:
        agent_connection = None

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
