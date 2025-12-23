import time
import argparse
from threading import Thread, Lock
import queue

from util.webcam import webcam, img_from_dir
from util.client import Client

try:
    from raspythoncar.wr_lib2wd import WR2WD
except:
    WR2WD = None

from WDT import PerfTimer

# ===============================
# グローバル
# ===============================
Phase = 1
bottom0 = None
g_timer = PerfTimer()
follow_side = None

# ===============================
# カメラクライアント
# ===============================
class Client_webcam:
    def __init__(self, host='localhost', port=5556, timeout=1000, device=0, file_dir=None, zmq_mode=3):
        self.cl = Client(host, port, timeout, zmq_mode)
        if file_dir is None:
            self.cam = webcam(device)
        else:
            self.cam = img_from_dir(file_dir)

    def get_img_data(self):
        img = self.cam.get_img()
        data = self.cl.send_img(img)
        return img, data


class thread_Client_webcam(Thread):
    def __init__(self, **kwargs):
        super().__init__()
        self.daemon = True
        self.webcam = Client_webcam(**kwargs)
        self.lock = Lock()
        self.queue = queue.Queue()
        self.running = True
        self.start()

    def run(self):
        while self.running:
            img, data = self.webcam.get_img_data()
            with self.lock:
                self.queue.put((img, data))
                while self.queue.qsize() > 1:
                    self.queue.get()

    def get_img_data(self):
        with self.lock:
            if self.queue.empty():
                return None, None
            return self.queue.get()

# ===============================
# Phase1: 認識待ち（状態決定のみ）
# ===============================
def Phase1(host, port, device, timeout, file_dir, zmq_mode):
    global Phase, follow_side

    cam = thread_Client_webcam(
        host=host,
        port=port,
        device=device,
        timeout=timeout,
        file_dir=file_dir,
        zmq_mode=zmq_mode
    )

    wr = WR2WD()
    wr.led.off()

    pred = None
    while True:
        img, data = cam.get_img_data()
        if data is not None and "pred" in data:
            pred = data["pred"]
        if pred is not None:
            break

    if pred < 0.5:
        follow_side = "left"
        wr.led.blue()
    else:
        follow_side = "right"
        wr.led.red()

    Phase = 2
    return True

# ===============================
# Phase2: linetrace_hori1（完全同一ロジック）
# ===============================
def Phase2(wr):
    global bottom0, g_timer, Phase

    if( bottom0 is None ):
        bottom0 = wr.ps.bottom()
        g_timer.start()

    bottom = wr.ps.bottom()
    if( bottom ):
        wr.led.blue()
        wr.mc.front_tl()
        if( g_timer.get_time() < 0.1 ):
            wr.mc.front()
    else:
        wr.led.red()
        wr.mc.front_tr()
        if( g_timer.get_time() > 0.1 ):
            wr.mc.front()

    if( bottom == bottom0 ):
        if( g_timer.get_time() > 2 ):
            wr.led.green()
            Phase = 3
    else:
        g_timer.restart()

    bottom0 = bottom
    return True

# ===============================
# Phase3
# ===============================
def Phase3(wr):
    global Phase, follow_side

    if follow_side == "left":
        if wr.ps.front():
            wr.mc.front_tl()
        else:
            wr.mc.front()

    if follow_side == "right":
        if wr.ps.front():
            wr.mc.front_tr()
        else:
            wr.mc.front()

    if wr.ps.front():
        Phase = 4
    return True

# ===============================
# Phase4
# ===============================
def Phase4(wr):
    global Phase, follow_side

    if follow_side == "left":
        if not wr.ps.front():
            wr.mc.left.set(reverse=True)
            wr.mc.right.set(reverse=False)
        else:
            wr.mc.stop()

    if follow_side == "right":
        if not wr.ps.front():
            wr.mc.right.set(reverse=True)
            wr.mc.left.set(reverse=False)
        else:
            wr.mc.stop()

    if wr.ps.front():
        Phase = 5
    return True

# ===============================
# Phase5: linetrace_hori1（完全同一ロジック）
# ===============================
def Phase5(wr):
    global bottom0, g_timer, Phase

    if( bottom0 is None ):
        bottom0 = wr.ps.bottom()
        g_timer.start()

    bottom = wr.ps.bottom()
    if( bottom ):
        wr.led.blue()
        wr.mc.front_tl()
        if( g_timer.get_time() < 0.1 ):
            wr.mc.front()
    else:
        wr.led.red()
        wr.mc.front_tr()
        if( g_timer.get_time() > 0.1 ):
            wr.mc.front()

    bottom0 = bottom
    return True

# ===============================
# main
# ===============================
def main(host, port, device, timeout, file_dir, zmq_mode):
    global Phase
    Phase = 1
    wr = WR2WD()

    while True:
        if Phase == 1:
            Phase1(host, port, device, timeout, file_dir, zmq_mode)
        elif Phase == 2:
            Phase2(wr)
        elif Phase == 3:
            Phase3(wr)
        elif Phase == 4:
            Phase4(wr)
        elif Phase == 5:
            Phase5(wr)

# ===============================
# entry point
# ===============================
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True)
    parser.add_argument("-d", "--device", type=int, default=0)
    parser.add_argument("-t", "--timeout", type=int, default=1000)
    parser.add_argument("-f", "--file_dir", default=None)
    parser.add_argument("-z", "--zmq_mode", type=int, default=3)
    args = parser.parse_args()

    main(**vars(args))
