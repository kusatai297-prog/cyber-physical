import time
import argparse
from threading import Thread, Lock
import queue
import keyboard
from util.webcam import webcam, img_from_dir
from util.client import Client

try:
    from raspythoncar.wr_lib2wd import WR2WD
except:
    WR2WD = None


# ===============================
# カメラクライアント
# ===============================
class Client_webcam:
    def __init__(self, host='localhost', port=5556, timeout=1000,device=0, file_dir=None, zmq_mode=3):
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
# 壁追従ロジック（センサのみ）
# ===============================
Phase = 0
def Phase1(host, port, device, timeout, file_dir, zmq_mode):
    cam = thread_Client_webcam(
        host=host,
        port=port,
        device=device,
        timeout=timeout,
        file_dir=file_dir,
        zmq_mode=zmq_mode
    )

    global follow_side

    wr = WR2WD()
    wr.led.off()

    # ★ 状態（どちらの壁に沿うか）
    follow_side = None   # 初期値
    pred = None

    while True:
        img, data = cam.get_img_data()
        if data is not None and "pred" in data:
            pred = data["pred"]
        if pred != None:
            break 
            # ---- 認識が来たら「状態だけ」更新 ----
    if pred != None:
        if pred < 0.5:
                follow_side = "left"
                wr.led.blue()
        else:
                follow_side = "right"
                wr.led.red()
    Phase = 2
    return True


def Phase2(wr):
    global bottom0               # old bottom state
    global g_timer               # timer
    global Phase
    if not wr.ps.front():
        if( bottom0 is None ):
            # initial setting for bottom0
            bottom0 = wr.ps.bottom() # bottom sensor output ( True: white, False: black )
            g_timer.start()          # timer start

        bottom = wr.ps.bottom()      # bottom sensor output ( True: white, False: black )
        if( bottom ):
            # bottom is white
            wr.led.blue()            # turn led blue
            wr.mc.front_tl()         # moter front turn left
            if( g_timer.get_time() < 0.1 ):
                wr.mc.front()  
            
        else:
            # bottom is black
            wr.led.red()             # turn led red
            wr.mc.front_tr()         # moter front turn right
            if( g_timer.get_time() > 0.1 ):
                wr.mc.front() 
        bottom0 = bottom             # copy old bottom state

        if wr.ps.front():
            Phase = 3

    return True                  # True -> continue

def Phase3(wr):
    if follow_side == "left":
        if wr.ps.front():
            wr.mc.front.tl()
        else:
            wr.mc.front()
    if follow_side == "right":
        if wr.ps.front():
            wr.mc.front.tr()
        else:
            wr.mc.front()
    if wr.ps.right() and not wr.ps.left():
        Phase = 4
    return True

def Phase4(wr):
        if follow_side == "left":
            if not wr.ps.front():
                wr.mc.left.set(reverse)
                wr.mc.right.set(forward)
            else:
                wr.mc.stop()
        if follow_side == "right":
            if not wr.ps.front():
                wr.mc.right.set(reverse)
                wr.mc.left.set(forward)
            else:
                wr.mc.stop()
        if wr.ps.front():
            Phase = 5

def Phase5(wr):
    global bottom0               # old bottom state
    global g_timer               # timer
    global Phase
    if follow_side == "left":
        if not wr.ps.right():
            if( bottom0 is None ):
                # initial setting for bottom0
                bottom0 = wr.ps.bottom() # bottom sensor output ( True: white, False: black )
                g_timer.start()          # timer start

            bottom = wr.ps.bottom()      # bottom sensor output ( True: white, False: black )
            if( bottom ):
                # bottom is white
                wr.led.blue()            # turn led blue
                wr.mc.front_tl()         # moter front turn left
                if( g_timer.get_time() < 0.1 ):
                    wr.mc.front()  
                
            else:
                # bottom is black
                wr.led.red()             # turn led red
                wr.mc.front_tr()         # moter front turn right
                if( g_timer.get_time() > 0.1 ):
                    wr.mc.front() 
            bottom0 = bottom             # copy old bottom state
            if wr.ps.left():
                Phase = 6
            
    if follow_side == "right":
        if not wr.ps.right():
            if( bottom0 is None ):
                # initial setting for bottom0
                bottom0 = wr.ps.bottom() # bottom sensor output ( True: white, False: black )
                g_timer.start()          # timer start

            bottom = wr.ps.bottom()      # bottom sensor output ( True: white, False: black )
            if( bottom ):
                # bottom is white
                wr.led.blue()            # turn led blue
                wr.mc.front_tl()         # moter front turn left
                if( g_timer.get_time() < 0.1 ):
                    wr.mc.front()  
                
            else:
                # bottom is black
                wr.led.red()             # turn led red
                wr.mc.front_tr()         # moter front turn right
                if( g_timer.get_time() > 0.1 ):
                    wr.mc.front() 
            bottom0 = bottom             # copy old bottom state
        if wr.ps.right():
            Phase = 6

    return True                  # True -> continue
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
        if keyboard.is_pressed("s"):
            break

# ===============================
# main
# ===============================


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
