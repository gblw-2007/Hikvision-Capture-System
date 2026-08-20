import os
import sys
import ctypes
from ctypes import *
import json
import datetime
import traceback
# ==============================================================
# 💡 全局路径锁定：彻底解决 EXE 打包后的路径漂移和权限崩溃问题
# ==============================================================
if getattr(sys, 'frozen', False):
    # 打包为 EXE 时的真实物理目录
    APP_BASE_DIR = os.path.dirname(sys.executable)
else:
    # VSC 源码运行时的目录
    APP_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ==============================================================
# 海康 C++ 结构体映射 (ctypes)
# ==============================================================
class NET_DVR_ALARM_ISAPI_PICDATA(Structure):
    _fields_ = [("dwPicLen", c_uint32), ("byPicType", c_byte), ("byRes", c_byte * 3),
                ("szFilename", c_char * 256), ("pPicData", POINTER(c_byte))]

class NET_DVR_ALARM_ISAPI_INFO(Structure):
    _fields_ = [("pAlarmData", POINTER(c_byte)), ("dwAlarmDataLen", c_uint32),
                ("byDataType", c_byte), ("byPicturesNumber", c_byte), ("byRes", c_byte * 2),
                ("pPicPackData", POINTER(NET_DVR_ALARM_ISAPI_PICDATA)),
                ("dwPicPackDataLen", c_uint32), ("byRes1", c_byte * 32)]

class NET_DVR_USER_LOGIN_INFO(Structure):
    _fields_ = [("sDeviceAddress", c_char * 129), ("byUseTransport", c_byte), ("wPort", c_uint16),
                ("sUserName", c_char * 64), ("sPassword", c_char * 64), ("cbLoginResult", c_void_p),
                ("pUser", c_void_p), ("bUseAsynLogin", c_bool), ("byProxyType", c_byte),
                ("byUseUTCTime", c_byte), ("byLoginMode", c_byte), ("byHttps", c_byte),
                ("iProxyID", c_long), ("byVerifyMode", c_byte), ("byRes3", c_byte * 119)]

class NET_DVR_DEVICEINFO_V40(Structure):
    _fields_ = [("struDeviceV30", c_byte * 38), ("bySupportLock", c_byte), ("byRetryLoginTime", c_byte),
                ("byPasswordLevel", c_byte), ("byProxyType", c_byte), ("dwSurplusLockTime", c_uint32),
                ("byCharEncodeType", c_byte), ("bySupportDev5", c_byte), ("bySupport", c_byte),
                ("byLoginMode", c_byte), ("dwOEMCode", c_uint32), ("iResidualValidity", c_int32),
                ("byResidualValidity", c_byte), ("bySingleStartMicroSec", c_byte), ("byRes2", c_byte * 238)]

class NET_DVR_SETUPALARM_PARAM(Structure):
    _fields_ = [("dwSize", c_uint32), ("byLevel", c_byte), ("byAlarmInfoType", c_byte),
                ("byRetAlarmTypeV40", c_byte), ("byRetDevInfoVersion", c_byte),
                ("byRetVQDAlarmType", c_byte), ("byFaceAlarmDetection", c_byte),
                ("bySupport", c_byte), ("byBrokenNetHttp", c_byte), ("wTaskNo", c_uint16),
                ("byDeployType", c_byte), ("byRes1", c_byte * 3), ("byAlarmTypeURL", c_byte),
                ("byCustomCtrl", c_byte)]

class NET_DVR_ALARMER(Structure):
    _fields_ = [("byUserIDValid", c_byte), ("bySerialValid", c_byte), ("byVersionValid", c_byte),
                ("byDeviceNameValid", c_byte), ("byMacAddrValid", c_byte), ("byLinkPortValid", c_byte),
                ("byDeviceIPValid", c_byte), ("bySocketIPValid", c_byte), ("lUserID", c_int32),
                ("sSerialNumber", c_byte * 48), ("byDeviceVersion", c_uint32), ("sDeviceName", c_char * 32),
                ("byMacAddr", c_byte * 6), ("wLinkPort", c_uint16), ("sDeviceIP", c_char * 128),
                ("sSocketIP", c_char * 128), ("byIpProtocol", c_byte), ("byRes1", c_byte * 2),
                ("bJSONALarm", c_byte), ("byRes2", c_byte * 4)]

MSGCallBack = WINFUNCTYPE(c_bool, c_long, c_void_p, c_void_p, c_uint32, c_void_p)

# ==============================================================
# 核心驱动类
# ==============================================================
class HikSDKEngine:
    _sdk_initialized = False
    _hksdk = None
    _global_callback = None
    _app_context = None

    @classmethod
    def safe_log(cls, msg, level="INFO", tag="SYSTEM"):
        """安全日志器：彻底屏蔽 print，防止 --noconsole 模式下瞬间闪退"""
        if cls._app_context and 'log_callback' in cls._app_context:
            try:
                cls._app_context['log_callback'](msg, level, tag)
            except:
                pass # UI 未就绪或发生错误时，绝对静默丢弃

    @classmethod
    def init_sdk(cls, app_context):
        if cls._sdk_initialized: return True
        cls._app_context = app_context
        
        # 智能 DLL 路径嗅探
        sdk_paths = [
            os.path.join(APP_BASE_DIR, 'hik_sdk'),
            os.path.join(APP_BASE_DIR, '_internal', 'hik_sdk'),
            os.path.join(getattr(sys, '_MEIPASS', APP_BASE_DIR), 'hik_sdk')
        ]
        
        sdk_dir = None
        for p in sdk_paths:
            if os.path.exists(os.path.join(p, 'HCNetSDK.dll')):
                sdk_dir = p
                break
                
        if not sdk_dir:
            cls.safe_log("❌ 找不到 HCNetSDK.dll，请确认 hik_sdk 文件夹位置！", "ERROR", "ERROR")
            return False

        original_cwd = os.getcwd()
        try:
            os.chdir(sdk_dir)
            if hasattr(os, 'add_dll_directory'): 
                os.add_dll_directory(sdk_dir)
            cls._hksdk = ctypes.windll.LoadLibrary(os.path.join(sdk_dir, 'HCNetSDK.dll'))
            cls.safe_log("✅ 成功加载 HCNetSDK.dll 核心驱动", "INFO", "SYSTEM")
        except Exception as e:
            cls.safe_log(f"❌ 加载 HCNetSDK.dll 失败: {e}", "ERROR", "ERROR")
            os.chdir(original_cwd)
            return False
        finally:
            os.chdir(original_cwd)

        try:
            cls._hksdk.NET_DVR_Init()
            cls._hksdk.NET_DVR_SetConnectTime(2000, 1)
            cls._hksdk.NET_DVR_SetReconnect(10000, True)
            
            cls._global_callback = MSGCallBack(cls._alarm_callback)
            cls._hksdk.NET_DVR_SetDVRMessageCallBack_V31(cls._global_callback, None)
            cls._sdk_initialized = True
            return True
        except Exception as e:
            cls.safe_log(f"❌ SDK 初始化发生异常: {e}", "ERROR", "ERROR")
            return False

    @classmethod
    def _alarm_callback(cls, lCommand, pAlarmer, pAlarmInfo, dwBufLen, pUser):
        # 💡 终极防弹衣：拦截回调函数内部的一切异常，绝对不让其漏到 C++ 导致闪退
        try:
            log_cb = cls._app_context.get('log_callback') if cls._app_context else None
            def safe_log(msg, lvl, tag):
                if log_cb:
                    try: log_cb(msg, lvl, tag)
                    except: pass

            dev_ip = "未知IP"
            if pAlarmer:
                try:
                    alarmer = cast(pAlarmer, POINTER(NET_DVR_ALARMER)).contents
                    dev_ip = alarmer.sDeviceIP.decode('utf-8', errors='ignore').strip('\x00')
                except: pass

            if lCommand == 0x4993:
                timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S%f")
                # 使用绝对物理路径
                base_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
                save_dir = os.path.join(base_dir, "LiveCaptures")
                
                try:
                    os.makedirs(save_dir, exist_ok=True)
                except Exception as e:
                    safe_log(f"⚠️ 创建图片文件夹失败 (可能是C盘权限问题): {e}", "ERROR", "SYSTEM")
                    return True # 权限拒绝直接返回，防止后续报错闪退

                image_paths = {}
                json_str = "{}"

                if dwBufLen > 0 and pAlarmInfo:
                    raw_data = string_at(pAlarmInfo, dwBufLen)
                    
                    # 1. 完美无损 JSON 提取
                    first_jpeg_idx = raw_data.find(b'\xff\xd8')
                    if first_jpeg_idx == -1:
                        first_jpeg_idx = len(raw_data)
                        
                    header_area = raw_data[:first_jpeg_idx]
                    json_start = header_area.find(b'{')
                    json_end = header_area.rfind(b'}')
                    
                    if json_start != -1 and json_end != -1 and json_end > json_start:
                        json_str = header_area[json_start:json_end+1].decode('utf-8', errors='ignore')

                    # 2. 动态多图切片器
                    if b'"Human"' in header_area:
                        roles = ["人员全景大图", "人员特写", "人脸特征"]
                        target_tag = "HUMAN"
                    elif b'"Vehicle"' in header_area:
                        roles = ["车辆全景大图", "车辆特写", "车牌特征"]
                        target_tag = "VEHICLE"
                    elif b'"NonMotor"' in header_area:
                        roles = ["非机动车全景", "非机动车特写", "人员特征"]
                        target_tag = "HUMAN"
                    else:
                        roles = ["全景抓拍图", "特写抓拍1", "特写抓拍2"]
                        target_tag = "SYSTEM"

                    pos = 0
                    pic_index = 0
                    while True:
                        start_idx = raw_data.find(b'\xff\xd8', pos)
                        if start_idx == -1: break
                        end_idx = raw_data.find(b'\xff\xd9', start_idx)
                        if end_idx == -1: break
                        
                        img_data = raw_data[start_idx:end_idx+2]
                        role_name = roles[pic_index] if pic_index < len(roles) else f"附加图_{pic_index+1}"
                        file_path = os.path.join(save_dir, f"Live_{timestamp}_{dev_ip}_{role_name}.jpg")
                        
                        try:
                            with open(file_path, 'wb') as f: 
                                f.write(img_data)
                            image_paths[role_name] = file_path
                        except:
                            pass # 忽略单张图片写入失败
                            
                        pic_index += 1
                        pos = end_idx + 2

                # 3. 安全推入队列
                if cls._app_context and 'queue' in cls._app_context:
                    try:
                        cls._app_context['queue'].put({
                            'raw_json': json_str,
                            'images': image_paths,
                            'timestamp': timestamp,
                            'device_ip': dev_ip
                        })
                    except:
                        pass
                
                safe_log(f"🎯 0x4993 [满血 JSON + {pic_index}图] 提取成功 | IP: {dev_ip}", "INFO", target_tag)

        except Exception as e:
            # 最后一层防线：吃掉所有未知错误，绝不崩溃
            pass 
            
        return True
    
    def __init__(self, app_context):
        self.app_context = app_context
        self.user_id = -1
        self.alarm_handle = -1
        HikSDKEngine.init_sdk(app_context)

    def login_and_listen(self, ip, port, user, pwd):
        if not self._sdk_initialized: 
            self.safe_log(f"❌ SDK 未正确初始化，无法登录设备 {ip}", "ERROR", "ERROR")
            return False
            
        login_info = NET_DVR_USER_LOGIN_INFO()
        login_info.sDeviceAddress = ip.encode('utf-8')
        login_info.wPort = port
        login_info.sUserName = user.encode('utf-8')
        login_info.sPassword = pwd.encode('utf-8')
        login_info.bUseAsynLogin = False
        
        device_info = NET_DVR_DEVICEINFO_V40()
        self.user_id = self._hksdk.NET_DVR_Login_V40(byref(login_info), byref(device_info))
        if self.user_id < 0:
            self.safe_log(f"❌ 登录摄像机 {ip} 失败，错误码: {self._hksdk.NET_DVR_GetLastError()}", "ERROR", "ERROR")
            return False

        setup_param = NET_DVR_SETUPALARM_PARAM()
        setup_param.dwSize = sizeof(NET_DVR_SETUPALARM_PARAM)
        setup_param.byLevel = 1
        setup_param.byAlarmInfoType = 1 
        setup_param.byDeployType = 1

        self.alarm_handle = self._hksdk.NET_DVR_SetupAlarmChan_V41(self.user_id, byref(setup_param))
        if self.alarm_handle < 0:
            self.safe_log(f"❌ 摄像机 {ip} 布防失败，错误码: {self._hksdk.NET_DVR_GetLastError()}", "ERROR", "ERROR")
            return False

        self.safe_log(f"🚀 {ip} SDK 报警已布防，准备接收数据！", "INFO", "SYSTEM")
        return True
