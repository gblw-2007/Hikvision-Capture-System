import sys
import os

try:
    from PyQt5 import sip
except ImportError:
    import sip # type: ignore

def resource_path(relative_path):
    if getattr(sys, 'frozen', False):
        base_path = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

json_path = resource_path('vehicleLogo.json')
try:
    with open(json_path, 'r', encoding='utf-8') as f:
        vehicle_logo_dict = json.load(f)
except Exception as e:
    vehicle_logo_dict = {} 
    

# ==========================================
# 💡 核心升级：绝对穿透的流捕获器 (修复无控制台打包闪退)
# 直接对接 sys.__stdout__，并增加 None 类型安全校验！
# ==========================================
class StreamCatcher:
    def __init__(self, is_stderr=False):
        self.cache = []
        self.signal_emitter = None
        self.is_stderr = is_stderr
        
    def write(self, text):
        # 1. 强制写入真实的底层操作系统控制台（增加 None 校验，防止 noconsole 打包闪退）
        try:
            if self.is_stderr and sys.__stderr__ is not None:
                sys.__stderr__.write(text)
                sys.__stderr__.flush()
            elif not self.is_stderr and sys.__stdout__ is not None:
                sys.__stdout__.write(text)
                sys.__stdout__.flush()
        except Exception:
            pass
            
        # 2. 拦截并缓存给 UI 界面的虚拟控制台
        if text and text.strip():
            self.cache.append(text)
            if len(self.cache) > 2000:
                self.cache.pop(0)
            if self.signal_emitter:
                try:
                    self.signal_emitter.emit(text)
                except: pass
                
    def flush(self):
        try:
            if self.is_stderr and sys.__stderr__ is not None:
                sys.__stderr__.flush()
            elif not self.is_stderr and sys.__stdout__ is not None:
                sys.__stdout__.flush()
        except Exception:
            pass

# 挂载双向捕获钩子
sys_stdout_catcher = StreamCatcher(is_stderr=False)
sys_stderr_catcher = StreamCatcher(is_stderr=True)
sys.stdout = sys_stdout_catcher
sys.stderr = sys_stderr_catcher

import re
import json
import threading
import datetime
import time
import shutil
import subprocess
import platform
import psutil  
import queue  
import socket

try:
    from hik_engine import HikSDKEngine
except ImportError:
    HikSDKEngine = None
    pass

from PyQt5.QtWidgets import (QApplication, QMainWindow, QFrame, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QScrollArea, QWidget, QGridLayout, 
                             QSplitter, QStackedWidget, QCheckBox, QComboBox, 
                             QDateTimeEdit, QLineEdit, QDialog, QTextEdit, QFileDialog, 
                             QMessageBox, QSizePolicy, QGraphicsView, QGraphicsScene,
                             QListWidget, QListWidgetItem, QProgressBar, QInputDialog)
from PyQt5.QtCore import (Qt, QTimer, pyqtSignal, pyqtSlot, QObject, QDateTime, 
                          QCoreApplication, QThread, QMetaObject, Q_ARG)
from PyQt5.QtGui import QFont, QPixmap, QImage, QCursor, QPainter, QTextCursor

import matplotlib
matplotlib.use('Qt5Agg')

if hasattr(Qt, 'AA_UseDesktopOpenGL'): QCoreApplication.setAttribute(Qt.AA_UseDesktopOpenGL, True)
if hasattr(Qt, 'AA_EnableHighDpiScaling'): QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
if hasattr(Qt, 'AA_UseHighDpiPixmaps'): QCoreApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

# ==========================================
# 基础属性翻译字典 
# ==========================================
VEHICLE_DICT = vehicle_logo_dict

ATTR_TRANS = {
    "white": "白色", "black": "黑色", "red": "红色", "blue": "蓝色", 
    "green": "绿色", "yellow": "黄色", "silver": "银色", "gray": "灰色",
    "brown": "棕色", "pink": "粉色", "purple": "紫色",
    "newenergy": "新能源", "92typecivil": "92式民用",
    "suvmpv": "SUV/MPV", "car": "小型轿车", "truck": "货车", "vehicle": "机动车",
    "lighttruck": "轻型货车", "minibus": "面包车", "midibus": "中型客车", "largebus": "大型客车",
    "nonmotorvehicle": "非机动车", "twowheelvehicle": "两轮车", "tricycle": "三轮车", "threewheelvehicle": "三轮车",
    "male": "男性", "female": "女性", "unknown": "未知",
    "yes": "是", "no": "否", 
    "shortsleeve": "短袖", "longsleeve": "长袖", 
    "shorthair": "短发", "longhair": "长发", 
    "shorttrousers": "短裤", "longtrousers": "长裤", "skirt": "裙子",
    "leftward": "向左", "rightward": "向右", "forward": "向前", "backward": "向后",
    "prime": "青年", "middle": "中年", "old": "老年", "young": "少年", "child": "儿童",
    "sad": "悲伤", "happy": "高兴", "neutral": "平静", "angry": "愤怒", "surprise": "惊讶", "fear": "害怕",
    "oneperson": "单人", "twopersons": "双人", "morepersons": "多人", "helmet": "头盔", "nohelmet": "无头盔",
    "other": "其他"
}

KEY_TRANS = {
    "jacketColor": "上衣颜色", "jacketType": "上衣款式", 
    "trousersColor": "下衣颜色", "trousersType": "下衣款式",
    "gender": "性别", "glass": "眼镜", "mask": "口罩", 
    "hat": "帽子", "bag": "背包", "things": "拎东西", 
    "hairStyle": "发型", "direction": "行进方向", "ageGroup": "年龄段",
    "plateNo": "车牌", "vehicleColor": "车身", "vehicleType": "车型",
    "plateColor": "牌色", "plateType": "牌型",
    "faceExpression": "表情", "age": "年龄",
    "ride": "骑车", "cyclingPersonNumber": "骑车人数", "hatStyle": "帽子款式", "nonMotorType": "非机动车类"
}

IGNORE_FIELDS = ["vehicleLogo", "vehicleSublogo", "vehicleModel", "confidence", "score", "age"]

class UICommSignals(QObject):
    log_emitted = pyqtSignal(dict)                  
    scan_completed = pyqtSignal()  
    capture_signal = pyqtSignal(dict)
    cmd_log_signal = pyqtSignal(str) 

# ==========================================
# UI 组件
# ==========================================
class ZoomableView(QGraphicsView):
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff) 
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)   
        self.setDragMode(QGraphicsView.ScrollHandDrag)           
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse) 
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setStyleSheet("background-color: #000; border: none;")

    def wheelEvent(self, event):
        if event.angleDelta().y() > 0: self.scale(1.15, 1.15) 
        else: self.scale(1.0 / 1.15, 1.0 / 1.15) 

class ClickableImageLabel(QLabel):
    def __init__(self, img_path, title, parent=None):
        super().__init__(parent)
        self.img_path = img_path
        self.title = title
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("💡 双击查看原始高清大图")
        self.setAlignment(Qt.AlignCenter)

    def mouseDoubleClickEvent(self, event):
        if not os.path.exists(self.img_path): return
        dlg = QDialog(self.window())
        dlg.setWindowTitle(f"高清原图查阅 - {self.title}")
        dlg.resize(1000, 700)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        scene = QGraphicsScene()
        item = scene.addPixmap(QPixmap(self.img_path))
        view = ZoomableView(scene)
        lay.addWidget(view)
        dlg.show()
        view.fitInView(item, Qt.KeepAspectRatio)
        dlg.exec_()

class CardFrame(QFrame):
    clicked_sig = pyqtSignal(str)
    def __init__(self, timestamp, evt, img_paths, parent=None):
        super().__init__(parent)
        self.timestamp = str(timestamp) 
        
        evt_type = evt.get('type', '')
        if "人脸" in evt_type or "非机动车" in evt_type: 
            self.setMinimumHeight(200)  # 👈 核心修改：大幅拉高卡片底板，为海量标签腾出空间
            img_w, img_h = (100, 160) if len(img_paths) == 2 else (140, 160) # 👈 同步把图片拉高变大
            tag_cols = 4
        elif "人员" in evt_type: 
            self.setMinimumHeight(240)  # 👈 核心修改：大幅拉高卡片底板，给 7 行以上的标签留足空间
            img_w, img_h = 140, 200     # 👈 图片同步放大拉长，让人体特写更清晰
            tag_cols = 2
        else: 
            self.setMinimumHeight(135)
            img_w, img_h = 110, 110
            tag_cols = 2

        self.setMinimumWidth(220) 
        self.setStyleSheet("""
            CardFrame { background-color: #242526; border-radius: 6px; border: 1px solid #333; }
            CardFrame:hover { border: 1px solid #1DA1F2; background-color: #2A2B2C;}
        """)
        self.setCursor(Qt.PointingHandCursor)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)
        
        img_container = QHBoxLayout()
        img_container.setContentsMargins(0,0,0,0)
        img_container.setSpacing(4)
        self.img_labels = []
        
        for path in img_paths:
            lbl = QLabel("加载中")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("background-color: #1A1A1A; color: #666; border-radius: 4px; border:none;")
            lbl.setFixedSize(img_w, img_h) 
            img_container.addWidget(lbl)
            self.img_labels.append((lbl, path))
            
        layout.addLayout(img_container)
        
        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)
        info_layout.setContentsMargins(0,0,0,0)
        
        top_hbox = QHBoxLayout()
        lbl_type = QLabel(evt.get('type', '未知'))
        lbl_type.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        lbl_type.setStyleSheet("color: #E0E0E0; border:none; background:transparent;")
        top_hbox.addWidget(lbl_type)
        
        info_text = evt.get('info', '')
        if info_text and info_text not in ["未识别", "人员抓拍", "目标抓拍", "人脸抓拍", "非机动车"]:
            lbl_info = QLabel(f"[{info_text}]")
            lbl_info.setFont(QFont("Microsoft YaHei", 9, QFont.Bold))
            lbl_info.setStyleSheet("color: #1DA1F2; border:none; background:transparent;")
            top_hbox.addWidget(lbl_info)
        top_hbox.addStretch()
        info_layout.addLayout(top_hbox)
            
        time_str = f"{self.timestamp[:4]}-{self.timestamp[4:6]}-{self.timestamp[6:8]} {self.timestamp[8:10]}:{self.timestamp[10:12]}:{self.timestamp[12:14]}" if len(self.timestamp)>=14 else self.timestamp
        lbl_time = QLabel(time_str)
        lbl_time.setFont(QFont("Consolas", 9))
        lbl_time.setStyleSheet("color: #AAAAAA; border:none; background:transparent;")
        info_layout.addWidget(lbl_time)
        
        dev_name = evt.get('dev_name', evt.get('folder', '未知设备'))
        lbl_folder = QLabel(f"📍 {dev_name}")
        lbl_folder.setFont(QFont("Microsoft YaHei", 9))
        lbl_folder.setStyleSheet("color: #D4AC0D; border:none; background:transparent;")
        info_layout.addWidget(lbl_folder)
        
        if evt.get('attributes'):
            tags_layout = QGridLayout()
            tags_layout.setSpacing(4)
            tags_layout.setContentsMargins(0,4,0,0)
            
            for i, tag in enumerate(evt['attributes']): 
                lbl_tag = QLabel(tag)
                lbl_tag.setFont(QFont("Microsoft YaHei", 8))
                if "品牌:" in tag or "车系:" in tag:
                    lbl_tag.setStyleSheet("background-color: #2FA572; color: #FFFFFF; border-radius: 3px; padding: 3px 5px; border:none;")
                else:
                    lbl_tag.setStyleSheet("background-color: #1E3D59; color: #E8EEF2; border-radius: 3px; padding: 3px 5px; border:none;")
                tags_layout.addWidget(lbl_tag, i // tag_cols, i % tag_cols)
            info_layout.addLayout(tags_layout)
            
        info_layout.addStretch()
        layout.addLayout(info_layout, stretch=1)

    def mousePressEvent(self, event):
        self.clicked_sig.emit(self.timestamp)
        super().mousePressEvent(event)

class ModernCaptureViewer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("智能抓拍事件检索中心 - V1.0)")
        self.resize(1800, 1000)
        self.setMinimumSize(1200, 700)
        self.is_running = True
        
        self.quota_gb = self._load_quota_config()
        self.offline_sorted_keys = [] 
        self.offline_filter_index = 0 
        
        self.setStyleSheet("""
            QMainWindow, QWidget, QDialog { background-color: #121212; color: #E8EEF2; }
            QFrame { background-color: #18191A; border-radius: 4px; }
            QPushButton { background-color: #242526; border: 1px solid #333; color: #E8EEF2; border-radius: 4px; padding: 4px; font-family: "Microsoft YaHei"; font-size: 13px;}
            QPushButton:hover { background-color: #3A3B3C; }
            QLabel { color: #E8EEF2; font-family: "Microsoft YaHei"; background: transparent;}
            QScrollArea { border: none; background-color: transparent; }
            QScrollArea > QWidget > QWidget { background-color: transparent; }
            QScrollBar:vertical { background-color: #121212; width: 10px; }
            QScrollBar::handle:vertical { background-color: #3A3B3C; border-radius: 5px; min-height: 20px; }
            QTextEdit { background-color: #000000; color: #00FF00; font-family: Consolas; border: 1px solid #333; border-radius: 4px;}
            QLineEdit { background-color: #1E1E1E; color: white; border: 1px solid #333; padding: 4px; border-radius: 4px; }
            QComboBox { background-color: #1E1E1E; color: white; border: 1px solid #333; padding: 2px 6px; border-radius: 4px; }
            QComboBox QAbstractItemView { background-color: #1E1E1E; color: white; selection-background-color: #1DA1F2; outline: none; }
            QDateTimeEdit { background-color: #1E1E1E; color: white; border: 1px solid #333; padding: 2px 6px; border-radius: 4px; }
            QCheckBox { color: #E8EEF2; font-family: "Microsoft YaHei"; font-size: 13px; background: transparent;}
            QSplitter::handle { background-color: #2D2D2D; margin: 2px; border-radius: 2px;}
        """)
        
        self.online_events = {}   
        self.offline_events = {}  
        self.current_mode = "ONLINE" 
        
        self.folders = [None] * 4
        self.filtered_events = {}
        self.filtered_sorted_keys = [] 
        
        self.rendered_cards_vehicle = []
        self.rendered_cards_human = []
        self.rendered_cards_face = []
        self.rendered_cards_nonmotor = []
        self.rendered_count = 0        
        self.view_mode = "grid" 
        
        self.thumbnail_cache = {} 
        self.MAX_CACHE_SIZE = 1000
        
        self.active_devices = {}
        self.archive_dir = os.path.abspath(os.path.join(os.getcwd(), "LiveArchives"))
        self.capture_dir = os.path.abspath(os.path.join(os.getcwd(), "LiveCaptures"))
        os.makedirs(self.archive_dir, exist_ok=True)
        os.makedirs(self.capture_dir, exist_ok=True)
        
        self.log_file_lock = threading.Lock()
        self.log_messages_cache = []
        
        self.comm = UICommSignals()
        self.comm.log_emitted.connect(self._handle_new_log)
        self.comm.scan_completed.connect(self._on_scan_complete) 
        self.comm.capture_signal.connect(self._process_single_raw_capture)
        
        sys_stdout_catcher.signal_emitter = self.comm.cmd_log_signal
        sys_stderr_catcher.signal_emitter = self.comm.cmd_log_signal
        self.comm.cmd_log_signal.connect(self._append_cmd_log)
        
        try:
            self.last_net_io = psutil.net_io_counters()
            self.last_disk_io = psutil.disk_io_counters()
            self.last_stat_time = time.time()
        except: pass

        self.app_queue = queue.Queue()
        self.app_context = {'queue': self.app_queue, 'is_receiving': True, 'log_callback': self.log_system_info}
        
        self.camera_configs = []
        self.sdk_engines = [] 
        self._load_camera_configs()

        self.ping_thread = threading.Thread(target=self._ping_devices_loop, daemon=True)
        self.ping_thread.start()
        
        self.setup_ui()
        self._load_local_history()
        
        for cam in self.camera_configs:
            self.connect_sdk_camera(cam['ip'], cam['port'], cam['user'], cam['pwd'])
        
        self.timer_live = QTimer(self)
        self.timer_live.timeout.connect(self._poll_queue_to_signal)
        self.timer_live.start(100)
        
        self.timer_stats = QTimer(self)
        self.timer_stats.timeout.connect(self._update_system_stats)
        self.timer_stats.start(1000)

        self.timer_render = QTimer(self)
        self.timer_render.timeout.connect(self._process_render_queue)
        self.render_queue = []
        self.is_rendering = False
        
        self.quota_counter = 58 
        print(">>> 界面 UI 引擎及底层组件加载完毕。等待数据接入...")

    def _load_camera_configs(self):
        config_path = os.path.join(os.getcwd(), "cameras.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    self.camera_configs = json.load(f)
            except Exception: pass

    def _save_camera_configs(self):
        config_path = os.path.join(os.getcwd(), "cameras.json")
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(self.camera_configs, f, ensure_ascii=False, indent=4)
        except Exception: pass

    def _load_quota_config(self):
        config_path = os.path.join(os.getcwd(), "quota.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    return json.load(f).get("quota_gb", 50)
            except: pass
        return 50

    def _save_quota_config(self):
        config_path = os.path.join(os.getcwd(), "quota.json")
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump({"quota_gb": self.quota_gb}, f)
        except: pass

    def set_quota_dialog(self):
        num, ok = QInputDialog.getInt(self, "存储配额设置", "请输入最大占用空间 (GB):\n(超过此值将自动删除最旧的文件)", self.quota_gb, 5, 2000, 5)
        if ok:
            self.quota_gb = num
            self._save_quota_config()
            self.log_system_info(f"存储配额已更新为: {self.quota_gb} GB", "INFO", "SYSTEM")
            threading.Thread(target=self._bg_calc_and_enforce_quota, daemon=True).start()

    def _bg_calc_and_enforce_quota(self):
        try:
            total_bytes = 0
            files_list = []
            for d in [self.archive_dir, self.capture_dir]:
                if not os.path.exists(d): continue
                for root, _, files in os.walk(d):
                    for f in files:
                        fp = os.path.join(root, f)
                        sz = os.path.getsize(fp)
                        total_bytes += sz
                        files_list.append((os.path.getmtime(fp), fp, sz))
            
            used_gb = total_bytes / (1024**3)
            QMetaObject.invokeMethod(self.lbl_quota, "setText", Qt.QueuedConnection, 
                                     Q_ARG(str, f"存储使用: {used_gb:.2f}GB / {self.quota_gb}GB"))
            
            quota_bytes = self.quota_gb * 1024 * 1024 * 1024
            if total_bytes > quota_bytes:
                files_list.sort(key=lambda x: x[0])
                bytes_to_free = total_bytes - quota_bytes + (500 * 1024 * 1024) 
                freed = 0
                for _, fp, sz in files_list:
                    try:
                        os.remove(fp)
                        freed += sz
                        if freed >= bytes_to_free: break
                    except: pass
                self.log_system_info(f"触发清理，释放 {freed/1024/1024:.1f} MB", "INFO", "SYSTEM")
        except: pass

    def connect_sdk_camera(self, ip, port, user, pwd):
        if not HikSDKEngine: return False
        engine = HikSDKEngine(self.app_context)
        success = engine.login_and_listen(ip, port, user, pwd)
        if success:
            self.sdk_engines.append(engine)
            self.active_devices[ip] = {'mac': 'SDK验证', 'name': ip, 'latency': 'TCP长连', 'status': '🟢 在线', 'last_seen': datetime.datetime.now()}
        else:
            self.active_devices[ip] = {'mac': 'SDK验证', 'name': ip, 'latency': '断连', 'status': '🔴 离线', 'last_seen': datetime.datetime.now()}
        return success

    def log_system_info(self, msg, level="INFO", category="SYSTEM"):
        time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{time_str}] [{level}] [{category}] {msg}"
        print(log_line) 
        with self.log_file_lock:
            try:
                with open("system_run.log", "a", encoding="utf-8") as f:
                    f.write(log_line + "\n")
            except: pass
        log_obj = {'line': log_line, 'category': category, 'level': level}
        self.comm.log_emitted.emit(log_obj)

    @pyqtSlot(dict)
    def _handle_new_log(self, log_obj):
        self.log_messages_cache.append(log_obj)
        if len(self.log_messages_cache) > 1500: self.log_messages_cache.pop(0)
        if hasattr(self, 'log_dialog') and self.log_dialog.isVisible() and self.filter_vars.get(log_obj['category'], True):
            color = {"SYSTEM": "#E0E0E0", "VEHICLE": "#2FA572", "HUMAN": "#1DA1F2", "IGNORED": "#888888", "ERROR": "#D9534F"}.get(log_obj['category'], "#E0E0E0")
            self.log_textbox.append(f"<span style='color:{color}; font-size: 12px;'>{log_obj['line']}</span>")

    def _update_system_stats(self):
        if not self.is_running: return
        self.quota_counter += 1
        if self.quota_counter >= 60: 
            self.quota_counter = 0
            threading.Thread(target=self._bg_calc_and_enforce_quota, daemon=True).start()

        try:
            self.lbl_cpu.setText(f"CPU: {psutil.cpu_percent(interval=None):.1f}%")
            ram = psutil.virtual_memory()
            self.lbl_ram.setText(f"RAM: {ram.used / (1024**3):.1f}G / {ram.total / (1024**3):.1f}G")
            
            current_time = time.time()
            dt = current_time - getattr(self, 'last_stat_time', current_time - 1)
            if dt > 0 and hasattr(self, 'last_net_io'):
                net_io, disk_io = psutil.net_io_counters(), psutil.disk_io_counters()
                up_bps = (net_io.bytes_sent - self.last_net_io.bytes_sent) / dt
                dl_bps = (net_io.bytes_recv - self.last_net_io.bytes_recv) / dt
                dw_bps = (disk_io.write_bytes - self.last_disk_io.write_bytes) / dt
                def fmt(bps):
                    if bps < 1024: return f"{bps:.0f} B/s"
                    elif bps < 1024**2: return f"{bps/1024:.1f} K/s"
                    else: return f"{bps/(1024**2):.1f} M/s"
                self.lbl_net.setText(f"Net: ↑{fmt(up_bps)} ↓{fmt(dl_bps)}")
                self.lbl_disk.setText(f"Disk W: {fmt(dw_bps)}")
                self.last_net_io, self.last_disk_io, self.last_stat_time = net_io, disk_io, current_time
        except: pass

    def _ping_devices_loop(self):
        is_win = platform.system().lower() == 'windows'
        while True:
            if not getattr(self, 'is_running', True): break
            for ip in list(self.active_devices.keys()):
                old = self.active_devices[ip].get('status')
                try:
                    param = '-n' if is_win else '-c'
                    cmd = ['ping', param, '1', '-w', '1000' if is_win else '1', ip]
                    if is_win:
                        si = subprocess.STARTUPINFO()
                        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                        out = subprocess.check_output(cmd, startupinfo=si, stderr=subprocess.STDOUT, text=True, encoding='gbk', errors='ignore')
                    else: out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True, errors='ignore')
                    match = re.search(r"时间[=<]\s*(\d+\s*ms)", out) or re.search(r"time[=<]\s*(\d+\s*ms)", out)
                    if match:
                        self.active_devices[ip]['latency'] = match.group(1).replace(" ", "")
                        self.active_devices[ip]['status'] = "🟢 实时在线"
                    else:
                        self.active_devices[ip]['latency'] = "超时"
                        self.active_devices[ip]['status'] = "🟡 网络拥堵"
                except:
                    self.active_devices[ip]['latency'] = "断连"
                    self.active_devices[ip]['status'] = "🔴 离线断网"
            time.sleep(5)

    def _load_local_history(self):
        try:
            files = sorted([f for f in os.listdir(self.archive_dir) if f.endswith('.jsonl')])
            if not files: return
            latest_file = os.path.join(self.archive_dir, files[-1])
            temp_events = {}
            with open(latest_file, 'r', encoding='utf-8') as f:
                lines = [line for line in f if line.strip()]
                for line in lines[-500:]:
                    temp_events.update(json.loads(line.strip()))
            self.online_events = temp_events
            self.apply_filter()
        except: pass

    def _archive_event(self, timestamp, evt_data):
        try:
            day_str = str(timestamp)[:8]
            filepath = os.path.join(self.archive_dir, f"EventArchive_{day_str}.jsonl")
            with open(filepath, 'a', encoding='utf-8') as f:
                f.write(json.dumps({timestamp: evt_data}, ensure_ascii=False) + '\n')
        except: pass

    def _poll_queue_to_signal(self):
        if not getattr(self, 'is_running', True): return
        if not self.app_context.get('is_receiving', True):
            while not self.app_queue.empty(): self.app_queue.get_nowait()
            return
            
        process_count = 0
        while not self.app_queue.empty() and process_count < 15:
            self.comm.capture_signal.emit(self.app_queue.get_nowait())
            process_count += 1

    @pyqtSlot(dict)
    def _process_single_raw_capture(self, new_evt):
        try:
            t = str(new_evt.get('timestamp', ''))
            dev_ip = new_evt.get('device_ip', '未知设备')
            
            raw_str = new_evt.get('raw_json', '{}')
            try: data = json.loads(raw_str)
            except: data = {}
                
            channel_name = data.get('channelName', dev_ip) if isinstance(data, dict) else dev_ip

            if dev_ip not in self.active_devices:
                self.active_devices[dev_ip] = {'mac': 'SDK设备', 'name': channel_name, 'latency': '<1ms', 'status': '🟢 在线', 'last_seen': datetime.datetime.now()}
            else:
                self.active_devices[dev_ip]['name'] = channel_name
                self.active_devices[dev_ip]['last_seen'] = datetime.datetime.now()

            evt_type, info_text, attributes = "⚠️ 未知事件", "目标抓拍", []
            images_dict = new_evt.get('images', {})
            
            if isinstance(data, dict) and data.get('CaptureResult'):
                target_node = data['CaptureResult'][0]
                raw_props = []
                
                if 'Face' in target_node:
                    evt_type, info_text = "👤 人脸抓拍", "人脸抓拍"
                    raw_props.extend(target_node['Face'].get('Property', []))
                    if 'Human' in target_node:
                        raw_props.extend(target_node['Human'].get('Property', []))
                        
                elif 'NonMotor' in target_node:
                    evt_type, info_text = "🚲 非机动车", "非机动车"
                    raw_props.extend(target_node['NonMotor'].get('Property', []))
                    if 'Human' in target_node:
                        raw_props.extend(target_node['Human'].get('Property', []))
                        
                elif 'Human' in target_node:
                    evt_type, info_text = "🚶 人员抓拍", "人员抓拍"
                    raw_props = target_node['Human'].get('Property', [])
                    
                elif 'Vehicle' in target_node:
                    evt_type, info_text = "🚗 车辆抓拍", "车辆抓拍"
                    raw_props = target_node['Vehicle'].get('Property', [])
                else: 
                    props = []
                
                seen_desc = set()
                unique_props = []
                for p in raw_props:
                    desc = p.get('description', '')
                    if desc not in seen_desc:
                        seen_desc.add(desc)
                        unique_props.append(p)
                
                main_id, sub_id = "", ""
                for p in unique_props:
                    desc, val = p.get('description', ''), str(p.get('value', ''))
                    if desc == 'vehicleLogo': main_id = val
                    if desc == 'vehicleSublogo': sub_id = val
                    if desc in IGNORE_FIELDS or val.lower() in ["", "unknown", "other", "score"]: continue
                    
                    translated_val = ATTR_TRANS.get(val.lower(), val)
                    trans_desc = KEY_TRANS.get(desc, desc)
                    if desc == 'plateNo': info_text = translated_val
                    else: attributes.append(f"{trans_desc}:{translated_val}")
                    
                if "车辆" in evt_type and main_id and main_id != "0":
                    brand = VEHICLE_DICT.get("mainLogo", {}).get(main_id, "")
                    model_full = VEHICLE_DICT.get("subLogo", {}).get(main_id, {}).get(sub_id, "")
                    if brand: attributes.insert(0, f"品牌:{brand}")
                    if model_full: 
                        clean_model = model_full.split("-")[-1] if "-" in model_full else model_full
                        attributes.insert(1, f"车系:{clean_model}")
                        if not info_text or info_text == "未知": info_text = model_full

            if not attributes: attributes.append("基础目标抓拍")

            evt_object = {
                'type': evt_type, 'info': info_text, 
                'images': images_dict, 
                'folder': dev_ip,
                'dev_name': channel_name,  
                'attributes': attributes
            }
            
            self._archive_event(t, evt_object)
            self.online_events[t] = evt_object
            
            while len(self.online_events) > 1000:
                oldest_t = min(self.online_events.keys())
                self.online_events.pop(oldest_t)
                if self.current_mode == "ONLINE":
                    self.filtered_events.pop(oldest_t, None)
                    if oldest_t in self.filtered_sorted_keys: 
                        self.filtered_sorted_keys.remove(oldest_t)

            if self.current_mode == "ONLINE" and self._matches_filters(t, evt_object):
                self.filtered_events[t] = evt_object
                if t not in self.filtered_sorted_keys:
                    self.filtered_sorted_keys.insert(0, t)
                    card = self.build_card_widget(t, evt_object)
                    
                    if "车辆" in evt_type:
                        self.rendered_cards_vehicle.insert(0, card)
                        cols = 1 if self.view_mode == "split" else 3
                        self._refresh_grid_layout(self.vehicle_layout, self.rendered_cards_vehicle, columns=cols)
                        if len(self.rendered_cards_vehicle) > 40:
                            old = self.rendered_cards_vehicle.pop()
                            old.deleteLater()
                    elif "人脸" in evt_type:
                        self.rendered_cards_face.insert(0, card)
                        self._refresh_grid_layout(self.face_layout, self.rendered_cards_face, columns=1)
                        if len(self.rendered_cards_face) > 40:
                            old = self.rendered_cards_face.pop()
                            old.deleteLater()
                    elif "非机动车" in evt_type:
                        self.rendered_cards_nonmotor.insert(0, card)
                        self._refresh_grid_layout(self.nonmotor_layout, self.rendered_cards_nonmotor, columns=1)
                        if len(self.rendered_cards_nonmotor) > 40:
                            old = self.rendered_cards_nonmotor.pop()
                            old.deleteLater()
                    else:
                        self.rendered_cards_human.insert(0, card)
                        cols = 1 if self.view_mode == "split" else 3
                        self._refresh_grid_layout(self.human_layout, self.rendered_cards_human, columns=cols)
                        if len(self.rendered_cards_human) > 40:
                            old = self.rendered_cards_human.pop()
                            old.deleteLater()
                            
                self.update_top_counters()
        except Exception as e:
            self.log_system_info(f"UI接收处理异常: {e}", "ERROR", "SYSTEM")

    def _matches_filters(self, t, e):
        search_query = self.search_entry.text().strip().upper()
        target_filter = self.target_combo.currentText()
        query_parts = search_query.split() if search_query else []

        if target_filter == "车辆" and "车辆" not in e.get('type', ''): return False
        if target_filter == "人员" and "人员" not in e.get('type', ''): return False
        if target_filter == "人脸" and "人脸" not in e.get('type', ''): return False
        if target_filter == "非机动车" and "非机动车" not in e.get('type', ''): return False

        for part in query_parts:
            part_found = False
            if part in e.get('info', '').upper(): part_found = True
            elif part in e.get('dev_name', '').upper(): part_found = True
            else:
                for tag in e.get('attributes', []):
                    if part in tag.upper():
                        part_found = True
                        break
            if not part_found: return False

        if hasattr(self, 'use_time_cb') and self.use_time_cb.isChecked():
            start_str = self.dt_start.dateTime().toString("yyyyMMddHHmmss")
            end_str = self.dt_end.dateTime().toString("yyyyMMddHHmmss")
            if t[:14] < start_str: return False
            if t[:14] > end_str: return False
            
        return True

    def build_card_widget(self, timestamp, evt):
        imgs = evt.get('images', {})
        thumb_paths = []
        
        evt_type = evt.get('type', '')
        if imgs:
            if "人脸" in evt_type:
                face_img = imgs.get('faceImage') or imgs.get('人脸特写')
                body_img = imgs.get('humanImage') or imgs.get('humanBackgroundImage') or imgs.get('人员全景')
                
                if face_img and body_img and os.path.exists(face_img) and os.path.exists(body_img):
                    thumb_paths = [body_img, face_img] 
                else:
                    valid_imgs = [p for p in imgs.values() if os.path.exists(p)]
                    valid_imgs.sort(key=os.path.getsize)
                    if len(valid_imgs) >= 2:
                        thumb_paths = [valid_imgs[-1], valid_imgs[0]]
                    elif valid_imgs:
                        thumb_paths = [valid_imgs[0]]
            elif "非机动车" in evt_type:
                target_img = imgs.get('nonMotorImage') or imgs.get('非机动车图')
                bg_img = imgs.get('nonMotorBackgroundImage') or imgs.get('humanBackgroundImage') or imgs.get('非机动车全景')
                if target_img and bg_img and os.path.exists(target_img) and os.path.exists(bg_img):
                    thumb_paths = [bg_img, target_img]
                else:
                    valid_imgs = [p for p in imgs.values() if os.path.exists(p)]
                    valid_imgs.sort(key=os.path.getsize)
                    if len(valid_imgs) >= 2:
                        thumb_paths = [valid_imgs[-1], valid_imgs[0]]
                    elif valid_imgs:
                        thumb_paths = [valid_imgs[0]]
            else:
                valid_imgs = [p for p in imgs.values() if os.path.exists(p)]
                if valid_imgs:
                    filtered_imgs = [p for p in valid_imgs if os.path.getsize(p) > 15360]
                    if not filtered_imgs: filtered_imgs = valid_imgs
                    thumb_paths = [min(filtered_imgs, key=os.path.getsize)]

        card = CardFrame(timestamp, evt, thumb_paths)
        card.clicked_sig.connect(self.switch_to_split)
        
        for lbl, path in card.img_labels:
            if path in self.thumbnail_cache:
                lbl.setPixmap(self.thumbnail_cache[path])
                lbl.setText("")
            else:
                try:
                    pixmap = QPixmap(path)
                    if not pixmap.isNull():
                        if "人脸" in evt_type or "非机动车" in evt_type:
                            # 👈 同步修改高清渲染尺寸，防止图片拉伸模糊
                            scaled_w, scaled_h = (100, 160) if len(thumb_paths) == 2 else (140, 160)
                        elif "人员" in evt_type:
                            scaled_w, scaled_h = 140, 200 # 👈 渲染尺寸必须与上方设置的完全同步
                        else:
                            scaled_w, scaled_h = 110, 110
                            
                        pixmap = pixmap.scaled(scaled_w, scaled_h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                        self.thumbnail_cache[path] = pixmap
                        if len(self.thumbnail_cache) > self.MAX_CACHE_SIZE:
                            oldest_key = next(iter(self.thumbnail_cache))
                            del self.thumbnail_cache[oldest_key]
                        lbl.setPixmap(pixmap)
                        lbl.setText("")
                except Exception: pass
        return card

    # ================= UI 布局 =================
    def setup_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ====== 左侧边栏 ======
        self.sidebar_frame = QFrame()
        self.sidebar_frame.setFixedWidth(200)
        self.sidebar_frame.setStyleSheet("background-color: #18191A; border-right: 1px solid #222;")
        sidebar_layout = QVBoxLayout(self.sidebar_frame)
        sidebar_layout.setContentsMargins(15,30,15,15)
        
        lbl_logo = QLabel("安防 AI 中心")
        lbl_logo.setFont(QFont("Microsoft YaHei", 18, QFont.Bold))
        lbl_logo.setStyleSheet("color: #1DA1F2; border:none;")
        lbl_logo.setAlignment(Qt.AlignCenter)
        sidebar_layout.addWidget(lbl_logo)
        sidebar_layout.addSpacing(30)

        self.btn_online = QPushButton("🟢 在线监控")
        self.btn_online.setStyleSheet("background-color: #1F7A52; border:none; padding:8px; font-size:14px;")
        self.btn_online.clicked.connect(lambda: self.switch_mode("ONLINE"))
        sidebar_layout.addWidget(self.btn_online)

        self.btn_offline = QPushButton("📁 离线分析")
        self.btn_offline.setStyleSheet("padding:8px; font-size:14px;")
        self.btn_offline.clicked.connect(lambda: self.switch_mode("OFFLINE"))
        sidebar_layout.addWidget(self.btn_offline)
        
        sidebar_layout.addSpacing(20)
        line = QFrame(); line.setFixedHeight(1); line.setStyleSheet("background-color: #333; border:none;")
        sidebar_layout.addWidget(line)
        sidebar_layout.addSpacing(10)

        btn_dev = QPushButton("📷 设备管理")
        btn_dev.setStyleSheet("padding:8px;")
        btn_dev.clicked.connect(self.open_device_dialog)
        sidebar_layout.addWidget(btn_dev)

        btn_log = QPushButton("📜 系统日志")
        btn_log.setStyleSheet("padding:8px;")
        btn_log.clicked.connect(self.open_log_dialog)
        sidebar_layout.addWidget(btn_log)

        btn_cmd = QPushButton("🖨️ 底层控制台")
        btn_cmd.setStyleSheet("padding:8px; color: #F39C12;")
        btn_cmd.clicked.connect(self.open_cmd_dialog)
        sidebar_layout.addWidget(btn_cmd)

        sidebar_layout.addStretch()

        self.sys_monitor_frame = QFrame()
        self.sys_monitor_frame.setStyleSheet("background-color: #242526; border:none; border-radius: 4px;")
        sys_layout = QVBoxLayout(self.sys_monitor_frame)
        sys_layout.setContentsMargins(10,10,10,10)
        lbl_sys = QLabel("🖥️ 状态与配额")
        lbl_sys.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        lbl_sys.setStyleSheet("color: #1DA1F2; border:none;")
        sys_layout.addWidget(lbl_sys)
        
        self.lbl_cpu = QLabel("CPU: --")
        self.lbl_ram = QLabel("RAM: --")
        self.lbl_disk = QLabel("Disk W: --")
        self.lbl_net = QLabel("Net: --")
        self.lbl_quota = QLabel(f"存储使用: 探测中 / {self.quota_gb}GB")
        
        for l in [self.lbl_cpu, self.lbl_ram, self.lbl_disk, self.lbl_net]:
            l.setFont(QFont("Consolas", 8))
            l.setStyleSheet("color: #AAA; border:none;")
            sys_layout.addWidget(l)
            
        self.lbl_quota.setStyleSheet("color: #F39C12; border:none; font-size:10px; margin-top:5px;")
        sys_layout.addWidget(self.lbl_quota)
        
        btn_quota = QPushButton("⚙️ 设置配额")
        btn_quota.setStyleSheet("background-color: #333; color:#AAA; font-size:10px; padding:2px;")
        btn_quota.clicked.connect(self.set_quota_dialog)
        sys_layout.addWidget(btn_quota)
        
        sidebar_layout.addWidget(self.sys_monitor_frame)
        main_layout.addWidget(self.sidebar_frame)

        # ====== 主内容区 ======
        content_widget = QWidget()
        self.content_layout = QVBoxLayout(content_widget)
        self.content_layout.setContentsMargins(15, 10, 15, 10)
        main_layout.addWidget(content_widget, stretch=1)

        self.top_stack = QStackedWidget()
        self.top_stack.setFixedHeight(30)
        self.content_layout.addWidget(self.top_stack)
        
        # 在线顶部
        self.online_top_frame = QFrame()
        self.online_top_frame.setStyleSheet("background-color: transparent;")
        on_layout = QHBoxLayout(self.online_top_frame)
        on_layout.setContentsMargins(0, 0, 0, 0)
        lbl_on_title = QLabel("📡 实时监控池")
        lbl_on_title.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        lbl_on_title.setStyleSheet("color: #F39C12;")
        on_layout.addWidget(lbl_on_title)
        on_layout.addStretch()
        
        self.lbl_totals = QLabel("检索统计 | 车辆: 0 | 人员: 0 | 人脸: 0 | 非机动车: 0")
        self.lbl_totals.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        self.lbl_totals.setStyleSheet("color: #3498DB; padding-right: 20px;")
        on_layout.addWidget(self.lbl_totals)
        
        self.status_label = QLabel("接收中")
        self.status_label.setStyleSheet("color: #2FA572; font-weight: bold; font-size: 11px;")
        on_layout.addWidget(self.status_label)
        self.live_cb = QCheckBox("挂机接收")
        self.live_cb.setChecked(True)
        self.live_cb.stateChanged.connect(self.toggle_live_receive)
        on_layout.addWidget(self.live_cb)
        self.top_stack.addWidget(self.online_top_frame)

        # 离线顶部
        self.offline_top_frame = QFrame()
        self.offline_top_frame.setStyleSheet("background-color: transparent;")
        off_layout = QHBoxLayout(self.offline_top_frame)
        off_layout.setContentsMargins(0, 0, 0, 0)
        btn_load_arc = QPushButton("加载归档区")
        btn_load_arc.setStyleSheet("background-color: #1E3D59;")
        btn_load_arc.clicked.connect(self.load_archive_dir)
        off_layout.addWidget(btn_load_arc)
        btn_sel = QPushButton("选择目录")
        btn_sel.clicked.connect(lambda: self.select_folder(0))
        off_layout.addWidget(btn_sel)
        self.folder_combo = QComboBox()
        self.folder_combo.setFixedWidth(150)
        self.folder_combo.addItem("选择目录...")
        self.folder_combo.currentTextChanged.connect(self.on_folder_switch)
        off_layout.addWidget(self.folder_combo)
        off_layout.addStretch()
        
        self.lbl_offline_totals = QLabel("检索统计 | 车辆: 0 | 人员: 0 | 人脸: 0 | 非机动车: 0")
        self.lbl_offline_totals.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        self.lbl_offline_totals.setStyleSheet("color: #3498DB; padding-right: 20px;")
        off_layout.addWidget(self.lbl_offline_totals)
        
        self.offline_status_label = QLabel("冷数据分析")
        self.offline_status_label.setStyleSheet("color: #888;")
        off_layout.addWidget(self.offline_status_label)
        self.top_stack.addWidget(self.offline_top_frame)

        # 搜索过滤条
        self.filter_frame = QFrame()
        self.filter_frame.setStyleSheet("background-color: #18191A;")
        filter_layout = QHBoxLayout(self.filter_frame)
        filter_layout.setContentsMargins(8, 4, 8, 4)
        
        self.use_time_cb = QCheckBox("时间段")
        filter_layout.addWidget(self.use_time_cb)
        self.dt_start = QDateTimeEdit(QDateTime.currentDateTime().addDays(-1))
        self.dt_start.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.dt_end = QDateTimeEdit(QDateTime.currentDateTime())
        self.dt_end.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        filter_layout.addWidget(self.dt_start)
        filter_layout.addWidget(QLabel("-"))
        filter_layout.addWidget(self.dt_end)

        filter_layout.addWidget(QLabel(" 🎯 目标:"))
        self.target_combo = QComboBox()
        self.target_combo.addItems(["全部", "车辆", "人员", "人脸", "非机动车"])
        self.target_combo.currentTextChanged.connect(self.apply_filter)
        filter_layout.addWidget(self.target_combo)
        
        self.search_entry = QLineEdit()
        self.search_entry.setPlaceholderText("关键字检索 (IP/名称/颜色/特征)")
        self.search_entry.returnPressed.connect(self.apply_filter)
        filter_layout.addWidget(self.search_entry)

        btn_search = QPushButton("实时检索")
        btn_search.setStyleSheet("background-color: #2FA572; padding: 2px 10px;")
        btn_search.clicked.connect(self.apply_filter)
        filter_layout.addWidget(btn_search)
        
        self.content_layout.addWidget(self.filter_frame)

        # ====================================================
        # 💡 核心升级：严格复刻非对称视觉黄金比例
        # ====================================================
        self.main_columns_splitter = QSplitter(Qt.Horizontal)
        self.content_layout.addWidget(self.main_columns_splitter, stretch=1)

        self.left_v_splitter = QSplitter(Qt.Vertical)
        self.right_v_splitter = QSplitter(Qt.Vertical)
        
        self.human_col_widget, self.human_layout, self.human_sa = self._create_grid_column("🚶 人员抓拍", "#F39C12")
        self.vehicle_col_widget, self.vehicle_layout, self.vehicle_sa = self._create_grid_column("🚗 车辆抓拍", "#3498DB")
        self.face_col_widget, self.face_layout, self.face_sa = self._create_grid_column("👤 人脸抓拍", "#E74C3C")
        self.nonmotor_col_widget, self.nonmotor_layout, self.nonmotor_sa = self._create_grid_column("🚲 非机动车", "#2ECC71")

        self.left_v_splitter.addWidget(self.human_col_widget)
        self.left_v_splitter.addWidget(self.vehicle_col_widget)
        
        self.right_v_splitter.addWidget(self.face_col_widget)
        self.right_v_splitter.addWidget(self.nonmotor_col_widget)

        self.main_columns_splitter.addWidget(self.left_v_splitter)
        self.main_columns_splitter.addWidget(self.right_v_splitter)

        # 强制非对称分割：左边横跨度极大，右边收窄。左边人员高，右边非机动车高
        self.main_columns_splitter.setSizes([1100, 600]) 
        self.left_v_splitter.setSizes([550, 400])
        self.right_v_splitter.setSizes([350, 600])

        self.human_sa.verticalScrollBar().valueChanged.connect(self.on_vscroll)
        self.vehicle_sa.verticalScrollBar().valueChanged.connect(self.on_vscroll)
        self.face_sa.verticalScrollBar().valueChanged.connect(self.on_vscroll)
        self.nonmotor_sa.verticalScrollBar().valueChanged.connect(self.on_vscroll)

        # ====== 右侧详情预览区 ======
        self.right_panel = QFrame()
        self.right_panel.setStyleSheet("background-color: #121212; border-left: 1px solid #333;")
        rp_layout = QVBoxLayout(self.right_panel)
        rp_layout.setContentsMargins(0,0,0,0)
        
        rp_top = QHBoxLayout()
        rp_top.setContentsMargins(10,10,10,0)
        lbl_detail = QLabel("🖼️ 抓拍详情")
        lbl_detail.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        rp_top.addWidget(lbl_detail)
        rp_top.addStretch()
        btn_close = QPushButton("✖ 返回卡片墙")
        btn_close.setStyleSheet("background-color: #D9534F; padding: 4px 10px; border:none;")
        btn_close.clicked.connect(self.switch_to_grid)
        rp_top.addWidget(btn_close)
        rp_layout.addLayout(rp_top)

        self.right_scroll = QScrollArea()
        self.right_scroll.setWidgetResizable(True)
        self.preview_container = QWidget()
        self.preview_layout = QVBoxLayout(self.preview_container)
        self.preview_layout.setAlignment(Qt.AlignTop)
        self.right_scroll.setWidget(self.preview_container)
        rp_layout.addWidget(self.right_scroll)

        self.main_columns_splitter.addWidget(self.right_panel)
        self.right_panel.hide()

    def on_vscroll(self, value):
        sender = self.sender()
        if sender and value >= sender.maximum() - 10:
            if self.rendered_count < len(self.filtered_sorted_keys):
                self.load_next_batch()

    def toggle_live_receive(self, state):
        is_active = (state == Qt.Checked)
        self.app_context['is_receiving'] = is_active
        if is_active:
            self.status_label.setText("接收中")
            self.status_label.setStyleSheet("color: #2FA572; font-weight: bold; font-size: 11px;")
        else:
            self.status_label.setText("已暂停")
            self.status_label.setStyleSheet("color: #F39C12; font-weight: bold; font-size: 11px;")

    def _create_grid_column(self, title, color):
        outer_widget = QWidget()
        outer_layout = QVBoxLayout(outer_widget)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        
        lbl = QLabel(title)
        lbl.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        lbl.setStyleSheet(f"color: {color}; padding: 8px; border: 1px solid {color}; border-bottom: none; background-color: #1A1A1A; border-top-left-radius: 4px; border-top-right-radius: 4px;")
        lbl.setAlignment(Qt.AlignCenter)
        outer_layout.addWidget(lbl)
        
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setStyleSheet(f"QScrollArea {{ border: 1px solid {color}; background-color: #1A1A1A; border-bottom-left-radius: 4px; border-bottom-right-radius: 4px; }}")
        
        container = QWidget()
        container.setStyleSheet("background-color: transparent;")
        grid_lay = QGridLayout(container)
        grid_lay.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        grid_lay.setSpacing(10)
        grid_lay.setContentsMargins(5, 5, 5, 5)
        
        sa.setWidget(container)
        outer_layout.addWidget(sa)
        
        return outer_widget, grid_lay, sa

    def _refresh_grid_layout(self, layout, cards_list, columns=3): 
        layout.parentWidget().setUpdatesEnabled(False)
        for card in cards_list:
            layout.removeWidget(card)
        for i, card in enumerate(cards_list):
            row, col = i // columns, i % columns
            layout.addWidget(card, row, col)
            card.show()
        layout.parentWidget().setUpdatesEnabled(True)

    def update_top_counters(self):
        v_c = sum(1 for e in self.filtered_events.values() if "车辆" in e.get('type',''))
        h_c = sum(1 for e in self.filtered_events.values() if "人员" in e.get('type',''))
        f_c = sum(1 for e in self.filtered_events.values() if "人脸" in e.get('type',''))
        n_c = sum(1 for e in self.filtered_events.values() if "非机动车" in e.get('type',''))
        text = f"检索统计 | 车辆: {v_c} | 人员: {h_c} | 人脸: {f_c} | 非机动车: {n_c}"
        if self.current_mode == "ONLINE":
            self.lbl_totals.setText(text)
        else:
            self.lbl_offline_totals.setText(text)

    def apply_filter(self):
        self.filtered_events.clear()
        self.filtered_sorted_keys = []
        
        for lay, lst in [(self.vehicle_layout, self.rendered_cards_vehicle), 
                         (self.human_layout, self.rendered_cards_human), 
                         (self.face_layout, self.rendered_cards_face),
                         (self.nonmotor_layout, self.rendered_cards_nonmotor)]:
            for card in lst:
                lay.removeWidget(card) 
                card.hide()
                card.deleteLater()
            lst.clear()
            
        self.rendered_count = 0
        self.render_queue.clear()
        self.is_rendering = False
        self.switch_to_grid()
        
        source_events = self.online_events if self.current_mode == "ONLINE" else self.offline_events
        for t, e in source_events.items():
            if self._matches_filters(t, e):
                self.filtered_events[t] = e
                
        self.filtered_sorted_keys = sorted(self.filtered_events.keys(), reverse=True)
        self.update_top_counters() 
        self.load_next_batch()     

    def load_next_batch(self):
        if not getattr(self, 'is_running', True) or self.rendered_count >= len(self.filtered_sorted_keys): return 
        next_limit = min(self.rendered_count + 30, len(self.filtered_sorted_keys))
        
        batch_keys = self.filtered_sorted_keys[self.rendered_count : next_limit]
        for t in batch_keys:
            self.render_queue.append((t, self.filtered_events[t]))

        self.rendered_count = next_limit 
        if not self.is_rendering:
            self.is_rendering = True
            self.timer_render.start(5)

    def _process_render_queue(self):
        if not self.render_queue:
            self.timer_render.stop()
            self.is_rendering = False
            
            cols_human = 1 if self.view_mode == "split" else 3
            cols_vehicle = 1 if self.view_mode == "split" else 3
            
            self._refresh_grid_layout(self.human_layout, self.rendered_cards_human, columns=cols_human)
            self._refresh_grid_layout(self.vehicle_layout, self.rendered_cards_vehicle, columns=cols_vehicle)
            self._refresh_grid_layout(self.face_layout, self.rendered_cards_face, columns=1)
            self._refresh_grid_layout(self.nonmotor_layout, self.rendered_cards_nonmotor, columns=1)
            return
            
        batch = self.render_queue[:10] 
        self.render_queue = self.render_queue[10:]
        
        for t, evt in batch:
            card = self.build_card_widget(t, evt)
            etype = evt.get('type', '')
            if "车辆" in etype:
                self.rendered_cards_vehicle.append(card)
            elif "人脸" in etype:
                self.rendered_cards_face.append(card)
            elif "非机动车" in etype:
                self.rendered_cards_nonmotor.append(card)
            else:
                self.rendered_cards_human.append(card)

    def switch_to_grid(self):
        self.view_mode = "grid"
        self.right_panel.hide()
        
        self.human_col_widget.show()
        self.vehicle_col_widget.show()
        self.face_col_widget.show()
        self.nonmotor_col_widget.show()
        
        self.left_v_splitter.show()
        self.right_v_splitter.show()
        
        # 恢复默认田字格非对称排布
        self.main_columns_splitter.setSizes([1100, 600, 0])
        self._refresh_grid_layout(self.human_layout, self.rendered_cards_human, columns=3)
        self._refresh_grid_layout(self.vehicle_layout, self.rendered_cards_vehicle, columns=3)

    def switch_to_split(self, timestamp):
        self.view_mode = "split"
        self.right_panel.show()
        
        evt_type = self.filtered_events.get(timestamp, {}).get('type', '')
        
        self.human_col_widget.hide()
        self.vehicle_col_widget.hide()
        self.face_col_widget.hide()
        self.nonmotor_col_widget.hide()
        
        if "人员" in evt_type:
            self.human_col_widget.show()
            self.left_v_splitter.show()
            self.right_v_splitter.hide()
            self.main_columns_splitter.setSizes([450, 0, 1000])
            self._refresh_grid_layout(self.human_layout, self.rendered_cards_human, columns=1)
        elif "车辆" in evt_type:
            self.vehicle_col_widget.show()
            self.left_v_splitter.show()
            self.right_v_splitter.hide()
            self.main_columns_splitter.setSizes([450, 0, 1000])
            self._refresh_grid_layout(self.vehicle_layout, self.rendered_cards_vehicle, columns=1)
        elif "人脸" in evt_type:
            self.face_col_widget.show()
            self.left_v_splitter.hide()
            self.right_v_splitter.show()
            self.main_columns_splitter.setSizes([0, 450, 1000])
        elif "非机动车" in evt_type:
            self.nonmotor_col_widget.show()
            self.left_v_splitter.hide()
            self.right_v_splitter.show()
            self.main_columns_splitter.setSizes([0, 450, 1000])
            
        self.render_preview(timestamp)

    def render_preview(self, timestamp):
        evt_data = self.filtered_events.get(timestamp)
        if not evt_data: return
        
        while self.preview_layout.count():
            item = self.preview_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        
        details_frame = QFrame()
        details_frame.setStyleSheet("background-color: #1E1E1E; border-radius: 6px;")
        df_layout = QVBoxLayout(details_frame)
        
        time_str = f"{timestamp[:4]}-{timestamp[4:6]}-{timestamp[6:8]} {timestamp[8:10]}:{timestamp[10:12]}:{timestamp[12:14]}" if len(timestamp)>=14 else timestamp
        df_layout.addWidget(QLabel(f"事件类型: {evt_data.get('type', '未知')}"))
        if evt_data.get('info') and evt_data.get('info') not in ["未识别", "人员抓拍", "目标抓拍", "人脸抓拍", "非机动车"]:
            df_layout.addWidget(QLabel(f"特征对象: {evt_data['info']}"))
        dev_name = evt_data.get('dev_name', evt_data.get('folder', '未知'))
        df_layout.addWidget(QLabel(f"时间: {time_str}   设备: {dev_name}"))
        
        if evt_data.get('attributes'):
            tags_w = QWidget()
            tags_lay = QGridLayout(tags_w)
            tags_lay.setContentsMargins(0,0,0,0)
            for i, tag in enumerate(evt_data['attributes']): 
                lbl_tag = QLabel(tag)
                lbl_tag.setStyleSheet("background-color: #1E3D59; color: #E8EEF2; padding: 3px 6px; border-radius:3px;")
                tags_lay.addWidget(lbl_tag, i // 6, i % 6)
            df_layout.addWidget(tags_w)

        self.preview_layout.addWidget(details_frame)

        images_w = QWidget()
        img_lay = QGridLayout(images_w)
        img_lay.setContentsMargins(0,0,0,0)
        
        valid_imgs = []
        for role, img_path in evt_data.get('images', {}).items():
            if os.path.exists(img_path):
                valid_imgs.append((role, img_path, os.path.getsize(img_path)))
                
        valid_imgs.sort(key=lambda x: x[2]) 
        
        display_list = []
        if len(valid_imgs) >= 2:
            display_list.append(("🗺️ 场景全景大图", valid_imgs[-1][1])) 
            display_list.append(("📸 目标特写图", valid_imgs[0][1]))    
        elif len(valid_imgs) == 1:
            display_list.append(("📸 抓拍图片", valid_imgs[0][1]))
            
        for i, (title, img_path) in enumerate(display_list):
            frame = QFrame()
            frame.setStyleSheet("background-color: #1A1A1A; border: 1px solid #333; border-radius: 4px;")
            f_lay = QVBoxLayout(frame)
            lbl_title = QLabel(title)
            lbl_title.setAlignment(Qt.AlignCenter)
            lbl_title.setStyleSheet("color:#AAA; font-size:14px; font-weight:bold; border:none; padding-bottom:5px;")
            f_lay.addWidget(lbl_title)
            
            lbl_img = ClickableImageLabel(img_path, title)
            try:
                pixmap = QPixmap(img_path)
                pixmap = pixmap.scaled(650, 450, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                lbl_img.setPixmap(pixmap)
            except Exception: pass
            f_lay.addWidget(lbl_img)
            
            img_lay.addWidget(frame, 0, i)

        self.preview_layout.addWidget(images_w)

    def switch_mode(self, mode):
        self.current_mode = mode
        if mode == "ONLINE":
            self.btn_online.setStyleSheet("background-color: #1F7A52; border:none; padding:8px; font-size:14px;")
            self.btn_offline.setStyleSheet("background-color: transparent; border: 1px solid #333; padding:8px; font-size:14px;")
            self.top_stack.setCurrentIndex(0)
        else:
            self.btn_offline.setStyleSheet("background-color: #1E3D59; border:none; padding:8px; font-size:14px;")
            self.btn_online.setStyleSheet("background-color: transparent; border: 1px solid #333; padding:8px; font-size:14px;")
            self.top_stack.setCurrentIndex(1)
        self.apply_filter()

    # ==========================================
    # 底层 CMD 运行日志截获面板
    # ==========================================
    def open_cmd_dialog(self):
        self.cmd_dialog = QDialog(self)
        self.cmd_dialog.setWindowTitle("底层引擎与终端控制台 (Python / C++ SDK 原生实时输出)")
        self.cmd_dialog.resize(1000, 600)
        layout = QVBoxLayout(self.cmd_dialog)
        
        top_bar = QHBoxLayout()
        lbl = QLabel("⚠️ 此面板实时显示 Python 引擎的输出。若需开启海康 C++ SDK 原生底层日志，请在代码中调用 NET_DVR_SetLogToFile。")
        lbl.setStyleSheet("color: #F39C12; font-weight: bold;")
        top_bar.addWidget(lbl)
        top_bar.addStretch()
        
        btn_clear = QPushButton("🗑️ 清空控制台")
        btn_clear.clicked.connect(self._clear_cmd_log)
        top_bar.addWidget(btn_clear)
        layout.addLayout(top_bar)
        
        self.cmd_textbox = QTextEdit()
        self.cmd_textbox.setReadOnly(True)
        self.cmd_textbox.setStyleSheet("background-color: #050505; color: #00FF00; font-family: Consolas; font-size: 13px;")
        
        self.cmd_textbox.setPlainText("".join(sys_stdout_catcher.cache + sys_stderr_catcher.cache))
        self.cmd_textbox.moveCursor(QTextCursor.End)
        
        layout.addWidget(self.cmd_textbox)
        self.cmd_dialog.show()

    def _clear_cmd_log(self):
        sys_stdout_catcher.cache.clear()
        sys_stderr_catcher.cache.clear()
        if hasattr(self, 'cmd_textbox'):
            self.cmd_textbox.clear()

    @pyqtSlot(str)
    def _append_cmd_log(self, text):
        if hasattr(self, 'cmd_dialog') and self.cmd_dialog.isVisible():
            self.cmd_textbox.insertPlainText(text)
            self.cmd_textbox.moveCursor(QTextCursor.End)

    # ==========================================
    # 设备与连接管理
    # ==========================================
    def open_device_dialog(self):
        self.dev_dialog = QDialog(self)
        self.dev_dialog.setWindowTitle("摄像机连接与管理")
        self.dev_dialog.resize(950, 600)
        layout = QVBoxLayout(self.dev_dialog)
        
        add_group = QFrame()
        add_group.setStyleSheet("border: 1px solid #333; border-radius: 4px; padding: 5px; background-color: #1E1E1E;")
        add_layout = QHBoxLayout(add_group)
        
        self.ip_input = QLineEdit(); self.ip_input.setPlaceholderText("IP 地址")
        self.port_input = QLineEdit("8000"); self.port_input.setFixedWidth(50)
        self.user_input = QLineEdit("admin"); self.user_input.setFixedWidth(70)
        self.pwd_input = QLineEdit(); self.pwd_input.setPlaceholderText("密码"); self.pwd_input.setEchoMode(QLineEdit.Password)
        
        btn_add_cam = QPushButton("➕ 添加/连接")
        btn_add_cam.setStyleSheet("background-color: #1DA1F2; font-weight:bold;")
        btn_add_cam.clicked.connect(self.on_add_sdk_camera)
        
        for w in [QLabel("IP:"), self.ip_input, QLabel("端口:"), self.port_input, 
                  QLabel("账号:"), self.user_input, QLabel("密码:"), self.pwd_input, btn_add_cam]:
            add_layout.addWidget(w)
        layout.addWidget(add_group)
        
        self.dev_scroll = QScrollArea()
        self.dev_scroll.setWidgetResizable(True)
        self.dev_content = QWidget()
        self.dev_layout = QVBoxLayout(self.dev_content)
        self.dev_layout.setAlignment(Qt.AlignTop)
        self.dev_scroll.setWidget(self.dev_content)
        layout.addWidget(self.dev_scroll)
        
        self.dev_timer = QTimer(self.dev_dialog)
        self.dev_timer.timeout.connect(self._refresh_dev_dialog)
        self.dev_timer.start(2000)
        self._refresh_dev_dialog()
        self.dev_dialog.show()

    def on_add_sdk_camera(self):
        ip = self.ip_input.text().strip()
        port_text = self.port_input.text().strip()
        user = self.user_input.text().strip()
        pwd = self.pwd_input.text().strip()
        
        if not ip or not pwd:
            QMessageBox.warning(self.dev_dialog, "错误", "IP地址和密码不能为空！")
            return
            
        port = int(port_text) if port_text.isdigit() else 8000
        for c in self.camera_configs:
            if c['ip'] == ip:
                QMessageBox.warning(self.dev_dialog, "错误", "该 IP 设备已经存在列表中！")
                return
                
        cam_info = {'ip': ip, 'port': port, 'user': user, 'pwd': pwd}
        self.camera_configs.append(cam_info)
        self._save_camera_configs()
        
        self.active_devices[ip] = {'mac': 'SDK直连', 'name': ip, 'latency': '连接中...', 'status': '🟡 正在验证', 'last_seen': datetime.datetime.now()}
        self._refresh_dev_dialog()
        
        def bg_connect():
            self.connect_sdk_camera(ip, port, user, pwd)
        threading.Thread(target=bg_connect, daemon=True).start()

    def _refresh_dev_dialog(self):
        while self.dev_layout.count():
            item = self.dev_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
            
        if not self.active_devices:
            lbl = QLabel("暂无设备接入。")
            lbl.setAlignment(Qt.AlignCenter)
            self.dev_layout.addWidget(lbl)
        else:
            for ip, info in self.active_devices.items():
                card = QFrame()
                card.setStyleSheet("background-color: #1A1A1A; border: 1px solid #333;")
                cl = QHBoxLayout(card)
                cl.addWidget(QLabel(f"📷 {info.get('name', ip)}"))
                cl.addWidget(QLabel(f"IP: {ip}"))
                lat = info.get('latency', 'N/A')
                lat_lbl = QLabel(f"延迟: {lat}")
                lat_lbl.setStyleSheet("color: #2FA572;" if "ms" in lat or "TCP" in lat else "color: #D9534F;")
                cl.addWidget(lat_lbl)
                status = info.get('status', '未知')
                st_lbl = QLabel(status)
                st_lbl.setStyleSheet("color: #2FA572; font-weight: bold;" if "在线" in status else "color: #D9534F; font-weight: bold;")
                cl.addWidget(st_lbl)
                
                btn_del = QPushButton("🗑️ 移除")
                btn_del.setStyleSheet("background-color: #D9534F; border:none;")
                btn_del.clicked.connect(lambda checked, pip=ip: self.remove_camera(pip))
                cl.addWidget(btn_del)
                
                self.dev_layout.addWidget(card)

    def remove_camera(self, ip):
        reply = QMessageBox.question(self.dev_dialog, "确认", f"确定要移除设备 {ip} 吗？", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.camera_configs = [c for c in self.camera_configs if c['ip'] != ip]
            self._save_camera_configs()
            if ip in self.active_devices: del self.active_devices[ip]
            self._refresh_dev_dialog()

    def open_log_dialog(self):
        self.log_dialog = QDialog(self)
        self.log_dialog.setWindowTitle("抓拍事件拦截日志")
        self.log_dialog.resize(1100, 700)
        layout = QVBoxLayout(self.log_dialog)
        top_bar = QHBoxLayout()
        self.filter_vars = {}
        for cat, name, color in [("SYSTEM", "系统网络", "#E0E0E0"), ("VEHICLE", "车辆事件", "#2FA572"), ("HUMAN", "人员事件", "#1DA1F2"), ("IGNORED", "拦截/忽略", "#888888"), ("ERROR", "报错异常", "#D9534F")]:
            cb = QCheckBox(name)
            cb.setChecked(True)
            cb.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 13px;")
            self.filter_vars[cat] = True
            cb.stateChanged.connect(lambda state, c=cat: self.filter_vars.update({c: state == Qt.Checked}))
            cb.stateChanged.connect(self.refresh_log_view)
            top_bar.addWidget(cb)
        layout.addLayout(top_bar)
        self.log_textbox = QTextEdit()
        self.log_textbox.setReadOnly(True)
        layout.addWidget(self.log_textbox)
        self.refresh_log_view()
        self.log_dialog.show()

    def refresh_log_view(self):
        self.log_textbox.clear()
        for log_obj in self.log_messages_cache:
            if self.filter_vars.get(log_obj['category'], True):
                color = {"SYSTEM": "#E0E0E0", "VEHICLE": "#2FA572", "HUMAN": "#1DA1F2", "IGNORED": "#888888", "ERROR": "#D9534F"}.get(log_obj['category'], "#E0E0E0")
                self.log_textbox.append(f"<span style='color:{color}; font-size: 12px;'>{log_obj['line']}</span>")

    def select_folder(self, index):
        folder = QFileDialog.getExistingDirectory(self, "选择离线数据目录")
        if folder:
            self.folders[index] = folder
            self.update_folder_dropdown()
            self.folder_combo.setCurrentText(folder)

    def load_archive_dir(self):
        self.folders[2] = self.archive_dir
        self.update_folder_dropdown()
        self.folder_combo.setCurrentText(self.archive_dir)

    def update_folder_dropdown(self):
        valid_folders = [f for f in self.folders if f]
        self.folder_combo.clear()
        if valid_folders: self.folder_combo.addItems(valid_folders)

    def on_folder_switch(self, value):
        tv = self.folder_combo.currentText()
        if not tv or tv == "选择目录...": return
        self.offline_status_label.setText("⏳ 正在探测总数据量...")
        self.folder_combo.setEnabled(False)
        self.thumbnail_cache.clear()
        threading.Thread(target=self._bg_scan_files, args=([tv],), daemon=True).start()

    def _bg_scan_files(self, targets):
        temp_events = {}
        for target_folder in targets:
            folder_name = os.path.basename(os.path.normpath(target_folder))
            for root_dir, _, files in os.walk(target_folder):
                for file in files:
                    file_lower = file.lower()
                    if file_lower.endswith('.jsonl'):
                        try:
                            with open(os.path.join(root_dir, file), 'r', encoding='utf-8') as f:
                                for line in f:
                                    if not line.strip(): continue
                                    data = json.loads(line.strip())
                                    for k, v in data.items():
                                        if k not in temp_events:
                                            temp_events[k] = v
                        except: pass
                    elif file_lower.endswith(('.jpg', '.jpeg', '.png')):
                        parts = os.path.splitext(file)[0].split('_')
                        evt_type, timestamp, info, img_role = "历史抓拍", "", "历史记录", "抓拍图"
                        if len(parts) >= 5 and "机动车" in parts[0]:
                            timestamp, info, img_role, evt_type = parts[3], parts[2], parts[1], "🚗 车辆抓拍"
                        elif len(parts) >= 4 and "车牌" in parts[0]:
                            timestamp, info, img_role, evt_type = parts[2], parts[1], "车牌特写", "🚗 车辆抓拍"
                        elif len(parts) >= 4 and "人脸" in parts[0]:
                            timestamp, img_role, evt_type = parts[2], f"{parts[0]}_{parts[1]}", "👤 人脸抓拍"
                        elif len(parts) >= 4 and ("人体" in parts[0] or "人员" in parts[0]):
                            timestamp, img_role, evt_type = parts[2], f"{parts[0]}_{parts[1]}", "🚶 人员抓拍"
                        elif len(parts) >= 3 and "Live" in parts[0]: 
                            timestamp, info, img_role = parts[1], parts[2], parts[-1]
                        elif len(parts) >= 2: 
                            timestamp = parts[-1] if parts[-1].isdigit() else parts[0]
                            if not timestamp.isdigit(): timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
                        
                        if not timestamp or not timestamp.isdigit(): continue
                        
                        if timestamp not in temp_events:
                            temp_events[timestamp] = {'type': evt_type, 'info': info, 'images': {}, 'folder': folder_name, 'dev_name': folder_name, 'attributes': []}
                        
                        temp_events[timestamp]['images'][img_role] = os.path.join(root_dir, file)
        
        self._temp_scanned_data = temp_events 
        QMetaObject.invokeMethod(self, "_on_scan_complete", Qt.QueuedConnection)

    @pyqtSlot()  
    def _on_scan_complete(self):
        self.offline_events = getattr(self, '_temp_scanned_data', {})
        self.offline_sorted_keys = sorted(self.offline_events.keys(), reverse=True)
        self.folder_combo.setEnabled(True)
        self.offline_status_label.setText(f"✅ 索引完毕 (总计 {len(self.offline_events)} 条)")
        self.apply_filter()
        self._temp_scanned_data = {} 

    def closeEvent(self, event):
        self.is_running = False
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    viewer = ModernCaptureViewer()
    viewer.show()
    sys.exit(app.exec_())
