import asyncio
import ctypes
import json
import time
import websockets

# Windows標準のXInput構造体定義（外部ドライバ不要）
class XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [
        ("wButtons", ctypes.c_ushort),
        ("bLeftTrigger", ctypes.c_ubyte),
        ("bRightTrigger", ctypes.c_ubyte),
        ("sThumbLX", ctypes.c_short),
        ("sThumbLY", ctypes.c_short),
        ("sThumbRX", ctypes.c_short),
        ("sThumbRY", ctypes.c_short),
    ]

class XINPUT_STATE(ctypes.Structure):
    _fields_ = [
        ("dwPacketNumber", ctypes.c_ulong),
        ("Gamepad", XINPUT_GAMEPAD),
    ]

def load_xinput():
    for dll_name in ("xinput1_4.dll", "xinput1_3.dll", "xinput9_1_0.dll"):
        try:
            return ctypes.WinDLL(dll_name)
        except OSError:
            continue
    raise RuntimeError("XInput DLLが見つかりませんでした。")

xinput = load_xinput()
xinput.XInputGetState.argtypes = [ctypes.c_ulong, ctypes.POINTER(XINPUT_STATE)]
xinput.XInputGetState.restype = ctypes.c_ulong

# XInputのビットマスク → Web標準Gamepad APIのボタン番号(0〜15)対応表
XINPUT_TO_STANDARD_BUTTONS = [
    (0x1000, 0),   # A / ×
    (0x2000, 1),   # B / ○
    (0x4000, 2),   # X / □
    (0x8000, 3),   # Y / △
    (0x0100, 4),   # LB / L1
    (0x0200, 5),   # RB / R1
    # 6(LT), 7(RT) はトリガーアナログ値から判定
    (0x0020, 8),   # Back / Select / Share
    (0x0010, 9),   # Start / Options
    (0x0040, 10),  # L3
    (0x0080, 11),  # R3
    (0x0001, 12),  # D-Pad 上
    (0x0002, 13),  # D-Pad 下
    (0x0004, 14),  # D-Pad 左
    (0x0008, 15),  # D-Pad 右
]

def read_active_controller():
    state = XINPUT_STATE()
    # 0〜3番ポートの中で接続中のコントローラーを探す
    for user_idx in range(4):
        if xinput.XInputGetState(user_idx, ctypes.byref(state)) == 0:
            gp = state.Gamepad
            pressed = []

            for mask, btn_idx in XINPUT_TO_STANDARD_BUTTONS:
                if gp.wButtons & mask:
                    pressed.append(btn_idx)

            # LT(6) / RT(7) の押し込み判定
            if gp.bLeftTrigger > 120:
                pressed.append(6)
            if gp.bRightTrigger > 120:
                pressed.append(7)

            # 左アナログスティック入力の正規化 (-1.0 〜 1.0)
            lx = round(gp.sThumbLX / 32768.0, 2) if abs(gp.sThumbLX) > 8000 else 0.0
            ly = round(-gp.sThumbLY / 32768.0, 2) if abs(gp.sThumbLY) > 8000 else 0.0

            return {
                "connected": True,
                "port": user_idx,
                "buttons": sorted(pressed),
                "axes": [lx, ly],
            }

    return {"connected": False, "port": -1, "buttons": [], "axes": [0.0, 0.0]}

connected_clients = set()

async def ws_handler(websocket):
    connected_clients.add(websocket)
    print(f"[接続] ブラウザと接続しました（現在の接続数: {len(connected_clients)}）")
    try:
        async for _ in websocket:
            pass
    finally:
        connected_clients.discard(websocket)
        print(f"[切断] ブラウザが切断されました（現在の接続数: {len(connected_clients)}）")

async def poll_loop():
    target_interval = 1.0 / 60.0
    while True:
        start = time.perf_counter()
        if connected_clients:
            data = read_active_controller()
            payload = json.dumps(data)
            # 接続中の全ブラウザタブへ送信
            websockets.broadcast(connected_clients, payload)

        elapsed = time.perf_counter() - start
        sleep_time = max(0.001, target_interval - elapsed)
        await asyncio.sleep(sleep_time)

async def main():
    print("==================================================")
    print(" Combo Rhythm - トレモ裏録音ヘルパー (v1.2)")
    print(" 待機ポート: ws://127.0.0.1:8765")
    print(" ※ゲーム画面が前面でもコントローラー入力をブラウザへ転送します")
    print(" ※終了する時はこのウィンドウを閉じるか Ctrl+C を押してください")
    print("==================================================")

    async with websockets.serve(ws_handler, "127.0.0.1", 8765):
        await poll_loop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nヘルパーを終了しました。")