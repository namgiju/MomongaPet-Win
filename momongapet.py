"""MomongaPet (Windows) - 작업표시줄 위와 창 위를 돌아다니는 작은 데스크톱 펫.

실행: pythonw momongapet.py   (콘솔 창 없이)   /   python momongapet.py   (오류 확인용)
"""
import ctypes
import math
import os
import random
import re
import sys
import time
from ctypes import wintypes
from dataclasses import dataclass

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QWidget

# MARK: - 설정
# 사용자 스프라이트 폴더가 있으면 우선, 없으면 프로그램 옆 sprites 폴더 사용
SPRITE_DIR = os.path.join(os.path.expanduser("~"), "MomongaPet", "sprites")
BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
BUNDLED_SPRITE_DIR = os.path.join(BASE_DIR, "sprites")
PET_W, PET_H = 50, 50
ANIM_FPS = 8.0
SLEEP_FPS = 3.0                 # 자는 애니메이션은 느리게
WALK_FPS = 5.0                  # 걷기 애니메이션 (걷는 속도에 맞춰 느리게)
WATCH_FPS = 2.0                 # 쳐다볼 때 눈동자 움직임 (느리게)
WALK_SPEED = 45.0
DIZZY_DURATION = 2.0            # 떨어진 뒤 헤롱거리는 시간(초)

# 창 위에서 마우스 쳐다보기
NOTICE_DURATION = 0.5           # 처음 알아챘을 때 "!" 표시 시간(초)
WATCH_TIMEOUT = 2.0             # 서 있는 창 안에서 마우스가 이만큼 안 움직이면 평소대로
MOUSE_MOVE_THRESHOLD = 2.0      # 이보다 작게 움직이면 무시 (떨림)
GRAVITY = -2200.0               # 속도는 위쪽이 + (화면 좌표는 아래쪽이 +)
JUMP_POWER = 900.0
MAX_THROW = 1500.0
SPRITES_FACE_RIGHT = True       # 원본 이미지가 왼쪽을 보고 있으면 False

# 잠
AWAY_SLEEP_AFTER = 180.0        # 시스템 유휴(키보드·마우스 입력 없음) 이만큼(초) 지나면 잠
NAP_CHANCE = 0.01               # 상태 전환 시 낮잠 확률
NAP_DURATION = (15.0, 30.0)
NAP_COOLDOWN = 600.0            # 깨어난 직후 이 시간 동안은 낮잠 안 잠
WAKE_IDLE_TIME = 1.5            # 깨어나서 멍하니 있는 시간

# 화면 바닥(작업표시줄 위)에서 다닐 가로 범위 (주 화면 기준 px, None이면 화면 전체)
FLOOR_RANGE = None

# 게임·영상 등 전체화면 창이 펫이 있는 화면을 덮으면 숨었다가, 나가면 다시 나타남
HIDE_ON_FULLSCREEN = True

# 창 위로 점프
WINDOW_JUMP_CHANCE = 0.15
WALK_OFF_EDGE_CHANCE = 0.10
JUMP_CLEARANCE = 40.0           # 창 상단보다 이만큼 더 높이 뛰어오름
HOP_RANGE = 60.0                # 창 높이 차가 이보다 작거나 아래 창이면 가볍게 폴짝
HOP_CLEARANCE = 15.0            # 폴짝 뛸 때 더 오르는 높이
JUMP_HEIGHT_LIMIT = 0.95        # 점프 높이(dy+여유)가 화면 높이의 이 비율 미만일 때만 점프
MAX_JUMP_DX = 300.0             # 창까지 가로 거리가 이보다 멀면 걸어서 다가간 뒤 점프
JUMP_REACT_DELAY = (0.6, 1.4)   # 새 창이 뜨고 이만큼(초) 뒤에 반응
SOFT_DROP_LIMIT = 30.0          # 발판이 이보다 조금 내려가면 상태 유지한 채 툭 떨어짐

# 드래그 흔들림
WOBBLE_DEGREES = 10.0
WOBBLE_HZ = 2.0
DRAG_SCALE = (0.95, 1.06)

# 흔들림·늘어남이 잘리지 않도록 창을 펫보다 조금 크게 (투명 여백은 클릭이 통과됨)
PAD_X = math.ceil(PET_H * 0.2)
PAD_TOP = math.ceil(PET_H * 0.1)
WIN_W, WIN_H = PET_W + PAD_X * 2, PET_H + PAD_TOP

STANDING = ("idle", "walk", "sleep", "dizzy", "notice", "watch")


def now():
    return time.monotonic()


# MARK: - 사각형 (화면 좌표: 좌상단 원점, 아래쪽이 +)
@dataclass
class Rect:
    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self): return self.right - self.left

    @property
    def height(self): return self.bottom - self.top

    @property
    def midx(self): return (self.left + self.right) / 2

    def contains(self, x, y): return self.left <= x <= self.right and self.top <= y <= self.bottom

    @staticmethod
    def of(q):
        return Rect(q.x(), q.y(), q.x() + q.width(), q.y() + q.height())


@dataclass
class WinInfo:
    number: int     # HWND
    frame: Rect


# MARK: - Win32
user32 = ctypes.WinDLL("user32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi")
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
WS_EX_NOACTIVATE = 0x08000000
GA_ROOT = 2
DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_CLOAKED = 14
SKIP_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsIconic.argtypes = [wintypes.HWND]
user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND
user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
user32.MonitorFromWindow.restype = wintypes.HMONITOR
user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.c_void_p]
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE
MONITOR_DEFAULTTONEAREST = 2
ERROR_ALREADY_EXISTS = 183


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]
dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def system_idle_seconds():
    """시스템 전체 유휴 시간(마지막 키보드·마우스 입력 이후 초)"""
    info = LASTINPUTINFO(ctypes.sizeof(LASTINPUTINFO), 0)
    if not user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    return ((kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF) / 1000


def window_pid(h):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
    return pid.value


def native_rect(h):
    """창의 보이는 테두리 (Win10/11의 투명한 크기조절 테두리 제외, 물리 픽셀)"""
    r = wintypes.RECT()
    if dwmapi.DwmGetWindowAttribute(h, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(r), ctypes.sizeof(r)) != 0:
        if not user32.GetWindowRect(h, ctypes.byref(r)):
            return None
    return r.left, r.top, r.right, r.bottom


def to_logical(l, t, r, b):
    """물리 픽셀 → Qt 논리 좌표. Qt는 화면 원점은 그대로 두고 크기만 배율로 나눔"""
    cx = (l + r) / 2
    for scr in QGuiApplication.screens():
        g, d = scr.geometry(), scr.devicePixelRatio()
        if g.x() <= cx < g.x() + g.width() * d and g.y() <= t < g.y() + g.height() * d:
            break
    else:
        scr = QGuiApplication.primaryScreen()
        g, d = scr.geometry(), scr.devicePixelRatio()
    x, y = g.x(), g.y()
    return Rect(x + (l - x) / d, y + (t - y) / d, x + (r - x) / d, y + (b - y) / d)


@dataclass
class ScreenWin:
    hwnd: int
    frame: Rect
    normal: bool    # 항상 위·제목 없는 창이 아닌 일반 창 (macOS의 layer 0에 해당)


def on_screen_windows():
    """화면에 보이는 최상위 창 목록 (앞→뒤 순서). 자기 자신·최소화·다른 가상 데스크톱 창은 제외"""
    out, own = [], os.getpid()

    def cb(h, _):
        if not user32.IsWindowVisible(h) or user32.IsIconic(h):
            return True
        ex = user32.GetWindowLongPtrW(h, GWL_EXSTYLE)
        if ex & WS_EX_TOOLWINDOW and not ex & WS_EX_APPWINDOW:
            return True
        cloaked = ctypes.c_int(0)
        dwmapi.DwmGetWindowAttribute(h, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
        if cloaked.value or window_pid(h) == own:
            return True
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(h, cls, 64)
        if cls.value in SKIP_CLASSES:
            return True
        nr = native_rect(h)
        if not nr or nr[2] <= nr[0] or nr[3] <= nr[1]:
            return True
        normal = not ex & WS_EX_TOPMOST and user32.GetWindowTextLengthW(h) > 0
        out.append(ScreenWin(h, to_logical(*nr), normal))
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return out


def standable_window(w):
    """펫이 올라설 수 있는 일반 창이면 반환"""
    f = w.frame
    if not w.normal or f.width < 200:
        return None
    # 상단이 어떤 화면 안에 있어야 하고, 펫이 올라설 공간(화면 위 끝 아래)이 있어야 함
    scr = QGuiApplication.screenAt(QPoint(int(f.midx), int(f.top + 1)))
    if scr is None or f.top - PET_H < scr.availableGeometry().y():
        return None
    return WinInfo(w.hwnd, f)


def fullscreen_rect():
    """맨 앞 창이 모니터 전체를 덮고 있으면 그 모니터 영역(논리 좌표), 아니면 None.
    최대화한 일반 창은 작업표시줄을 비워 두므로 해당 안 됨"""
    h = foreground_hwnd()
    if not h or window_pid(h) == os.getpid():
        return None
    cls = ctypes.create_unicode_buffer(64)
    user32.GetClassNameW(h, cls, 64)
    if cls.value in SKIP_CLASSES:                       # 바탕화면·작업표시줄
        return None
    r = wintypes.RECT()
    if not user32.GetWindowRect(h, ctypes.byref(r)):
        return None
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    if not user32.GetMonitorInfoW(user32.MonitorFromWindow(h, MONITOR_DEFAULTTONEAREST), ctypes.byref(mi)):
        return None
    m = mi.rcMonitor
    if r.left <= m.left and r.top <= m.top and r.right >= m.right and r.bottom >= m.bottom:
        return to_logical(m.left, m.top, m.right, m.bottom)
    return None


def foreground_hwnd():
    h = user32.GetForegroundWindow()
    return user32.GetAncestor(h, GA_ROOT) if h else None


def platform_status(number, lst):
    """서 있는 창의 현재 상태와, 그 창보다 앞에 있는 창들의 영역.
    닫힘·최소화·다른 가상 데스크톱 등으로 화면에 없으면 None"""
    above = []
    for w in lst:
        if w.hwnd == number:
            info = standable_window(w)
            return (info, above) if info else None
        if w.normal:
            above.append(w.frame)
    return None


# MARK: - 윈도우 시작 시 자동 실행 (현재 사용자 레지스트리 Run 키, 관리자 권한 필요 없음)
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "MomongaPet"


def autostart_command():
    if getattr(sys, "frozen", False):                   # exe로 묶었을 때
        return f'"{sys.executable}"'
    exe = sys.executable
    pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")   # 콘솔 창 없이
    return f'"{pyw if os.path.exists(pyw) else exe}" "{os.path.abspath(__file__)}"'


def autostart_enabled():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, RUN_NAME)
        return True
    except OSError:
        return False


def set_autostart(on):
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(k, RUN_NAME)
            except FileNotFoundError:
                pass


# MARK: - 스프라이트 로더
# 파일명 규칙: idle_01.png, walk_01.png, walk_02.png ... (없는 상태는 idle로 대체)
def natural_key(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def png_files(d):
    try:
        names = os.listdir(d)
    except OSError:
        return []
    return sorted((f for f in names if f.lower().endswith(".png")), key=natural_key)


class Sprites:
    def __init__(self, dpr):
        self.dpr = dpr
        self.frames = {}
        for d in (SPRITE_DIR, BUNDLED_SPRITE_DIR):
            self.load(d)
            if self.frames:
                break

    def prepare(self, pix):
        """미리 펫 크기로 부드럽게 줄여 둠 (그릴 때마다 줄이면 거칠어짐)"""
        p = pix.scaled(round(PET_W * self.dpr), round(PET_H * self.dpr),
                       Qt.KeepAspectRatio, Qt.SmoothTransformation)
        p.setDevicePixelRatio(self.dpr)
        return p

    def load(self, d):
        for f in png_files(d):
            base = os.path.splitext(f)[0]
            key = base.split("_")[0].lower()
            pix = QPixmap(os.path.join(d, f))
            if not pix.isNull():
                self.frames.setdefault(key, []).append(self.prepare(pix))

    def named(self, key):
        """이름으로 직접 찾기 (없으면 None)"""
        return self.frames.get(key) or None

    def frames_for(self, s):
        if self.frames.get(s):
            return self.frames[s]
        if s == "jump" and self.frames.get("fall"):
            return self.frames["fall"]
        if self.frames.get("idle"):
            return self.frames["idle"]
        return [self.placeholder()]

    def placeholder(self):
        if not hasattr(self, "_placeholder"):
            img = QPixmap(128, 128)
            img.fill(Qt.transparent)
            p = QPainter(img)
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(QPen(QColor(77, 77, 77), 3))
            p.setBrush(QColor(247, 247, 247))
            p.drawEllipse(QRectF(14, 36, 100, 88))
            p.setPen(Qt.NoPen)
            p.setBrush(Qt.black)
            p.drawEllipse(QRectF(44, 66, 9, 12))
            p.drawEllipse(QRectF(75, 66, 9, 12))
            p.end()
            self._placeholder = self.prepare(img)
        return self._placeholder


# MARK: - 펫
class Pet(QWidget):
    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowDoesNotAcceptFocus | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(WIN_W, WIN_H)
        self.dpr = QGuiApplication.primaryScreen().devicePixelRatio()
        self.sprites = Sprites(self.dpr)

        # 그리기
        self.image = None
        self.mirrored = False
        self.angle = 0.0                # 도
        self.stretch = (1.0, 1.0)

        self.state = "fall"
        self.vx = self.vy = 0.0
        self.frame_idx = 0
        self.anim_acc = 0.0
        self.state_timer = 0.0
        self.jumped = False             # 스스로 뛴 점프면 착지 후 헤롱거리지 않음
        self.facing_left = False

        # 창 위에서 마우스 쳐다보기
        self.last_mouse = QCursor.pos()
        self.last_mouse_move = 0.0      # 서 있는 창 안에서 마우스가 마지막으로 움직인 시각
        self.notice_frame = 0           # notice 시트 칸: 0 idle왼쪽, 1 idle오른쪽, 2 walk왼쪽, 3 walk오른쪽
        self.watch_left = False         # 마우스가 펫 왼쪽에 있음
        self.drag_time = 0.0
        self.last_tick = now()
        self.fullscreen_hidden = False  # 전체화면 창 때문에 숨어 있음
        self.last_fullscreen_poll = 0.0

        # 잠
        self.away_sleep = False         # 자리 비움으로 잠든 건지 (낮잠과 구분)
        self.sys_idle = 0.0
        self.last_idle_poll = 0.0
        self.last_wake = -math.inf

        # 창
        self.front_win = None           # 포어그라운드 창 (캐시)
        self.last_win_query = 0.0
        self.platform = None            # 지금 서 있는 창 (펫이 마지막으로 맞춘 위치)
        self.platform_now = None        # 그 창의 최신 조회 결과 (닫히거나 최소화되면 None)
        self.platform_above = []        # 그 창보다 앞에 있는 창들 (가려짐 판정용)
        self.walk_off_edge = False      # 창 끝에서 돌지 않고 걸어가 떨어지기
        self.pending_jump = False       # 새 창이 앞에 나타남 → 뛸 수 있게 되면 그 창으로
        self.pending_jump_at = 0.0      # 이 시각 이후에 반응
        self.drop_through = None        # 끌려서 움직인 발판 창: 떨어지는 동안 다시 착지 안 함
        self.approaching = False        # 점프하려고 창 쪽으로 걸어가는 중
        self.last_approach_dist = math.inf

        # 마우스
        self.press_location = QPoint()
        self.drag_offset = QPoint()     # 창 원점 기준 잡은 위치
        self.press_is_jump = False
        self.drag_samples = []          # (시각, x, y)

        # 펫 몸통 위치: 왼쪽 x, 발바닥 y (창 위치는 정수라 소수점까지 따로 보관)
        area = Rect.of(QGuiApplication.primaryScreen().availableGeometry())
        self.px = area.midx - PET_W / 2
        self.py = area.top + PET_H
        self.place()
        self.show()
        # 비활성 창: 펫을 클릭해도 포어그라운드 창이 바뀌지 않음
        hwnd = int(self.winId())
        ex = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex | WS_EX_NOACTIVATE)

        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self.timer.start(16)

    # 몸통 위치 → 창 위치
    def place(self):
        self.move(round(self.px - PAD_X), round(self.py - WIN_H))

    @property
    def midx(self): return self.px + PET_W / 2

    @property
    def airborne(self): return self.state in ("fall", "jump")

    def area(self):
        """펫이 있는 화면의 작업 영역 (작업표시줄 제외)"""
        scr = QGuiApplication.screenAt(QPoint(int(self.midx), int(self.py - PET_H / 2)))
        return Rect.of((scr or QGuiApplication.primaryScreen()).availableGeometry())

    def set_state(self, s):
        if s == self.state:
            return
        self.state = s
        self.frame_idx = 0
        self.anim_acc = 0.0

    # MARK: 잠
    @property
    def is_away(self): return self.sys_idle >= AWAY_SLEEP_AFTER

    def sleep(self, away, duration=math.inf):
        self.vx = 0
        self.walk_off_edge = False
        self.away_sleep = away
        self.set_state("sleep")
        self.state_timer = duration

    def wake_up(self):
        """깨어나면 잠깐 멍하니 있다가 평소대로"""
        self.away_sleep = False
        self.last_wake = now()
        self.vx = 0
        self.set_state("idle")
        self.state_timer = WAKE_IDLE_TIME

    def decide(self):
        self.walk_off_edge = False
        self.approaching = False
        if self.is_away:
            self.sleep(True)
            return
        t = now()
        if t - self.last_wake >= NAP_COOLDOWN and random.random() < NAP_CHANCE:
            self.sleep(False, random.uniform(*NAP_DURATION))
            return
        w = self.front_win
        if random.random() < WINDOW_JUMP_CHANCE and w and (self.platform is None or self.platform.number != w.number):
            self.pending_jump = True
            self.pending_jump_at = t                    # 다음 틱에 다가가거나 점프
            self.vx = 0
            self.set_state("idle")
            self.state_timer = 5
            return
        if random.random() < 0.5:
            self.set_state("walk")
            p = self.platform
            if p and random.random() < WALK_OFF_EDGE_CHANCE:
                # 가까운 창 끝 쪽으로 걸어가서 떨어지기
                self.walk_off_edge = True
                self.vx = (-1 if self.midx < p.frame.midx else 1) * WALK_SPEED
                self.state_timer = 30
            else:
                self.vx = random.choice((1, -1)) * WALK_SPEED
                self.state_timer = random.uniform(2, 6)
        else:
            self.set_state("idle")
            self.vx = 0
            self.state_timer = random.uniform(2, 5)

    # MARK: 창 점프
    def on_front(self):
        return self.platform is not None and self.front_win is not None \
            and self.platform.number == self.front_win.number

    def jump_target_x(self, w):
        """몸 전체가 창 안쪽에 오도록 하는 착지 x"""
        return max(w.frame.left, min(self.px, w.frame.right - PET_W))

    def go_to_front_window(self):
        """앞 창으로: 가까우면 점프, 멀면 그쪽으로 걸어감.
        True = 끝(점프했거나 못 뛰는 창이라 포기), False = 아직 다가가는 중"""
        w = self.front_win
        if w is None or self.on_front():
            return True
        dx = self.jump_target_x(w) - self.px
        # 창 끝·화면 끝에 막혀 더 못 다가가면 거기서 뜀
        blocked = self.approaching and self.state == "walk" and abs(dx) >= self.last_approach_dist - 0.01
        if abs(dx) > MAX_JUMP_DX and not blocked:
            if not (self.approaching and self.state == "walk"):
                self.approaching = True
                self.walk_off_edge = False
                self.set_state("walk")
                self.state_timer = 30
            self.vx = (-1 if dx < 0 else 1) * WALK_SPEED
            self.last_approach_dist = abs(dx)
            return False
        was_approaching = self.approaching
        self.approaching = False
        self.last_approach_dist = math.inf
        if self.jump_to_front_window():
            return True
        if was_approaching:
            self.vx = 0
            self.set_state("idle")
            self.state_timer = random.uniform(1, 3)
        return True

    def jump_to_front_window(self):
        w = self.front_win
        if self.state == "sleep" or w is None or self.on_front():
            return False
        area = self.area()
        g = abs(GRAVITY)
        dy = self.py - w.frame.top
        h = JUMP_CLEARANCE if dy > HOP_RANGE else HOP_CLEARANCE   # 높은 창은 크게, 비슷하거나 낮은 창은 가볍게 폴짝 뛰어내림
        # 천장에 부딪혀 궤도 틀어지지 않게
        if not (dy + h < area.height * JUMP_HEIGHT_LIMIT and w.frame.top - h - PET_H >= area.top):
            return False
        tx = self.jump_target_x(w)
        peak = max(dy, 0) + h                                       # 출발점 기준 최고 높이
        self.vy = math.sqrt(2 * g * peak)
        t = (self.vy + math.sqrt(2 * g * (peak - dy))) / g
        self.vx = (tx - self.px) / t
        self.platform = None
        self.drop_through = None
        self.walk_off_edge = False
        self.jumped = True
        self.set_state("jump")
        return True

    def refresh_windows(self):
        lst = on_screen_windows()
        fg = foreground_hwnd()
        if fg and window_pid(fg) != os.getpid():        # 펫 자신이 앞이면 직전 값 유지
            self.front_win = next((standable_window(w) for w in lst if w.hwnd == fg), None)
        # 서 있는 창은 맨 앞이 아니어도 계속 추적
        st = platform_status(self.platform.number, lst) if self.platform else None
        self.platform_now = st[0] if st else None
        self.platform_above = st[1] if st else []

    def land(self, y, w):
        self.py = y
        self.vx = self.vy = 0
        self.drop_through = None
        self.platform = w
        self.platform_now = w
        self.walk_off_edge = False
        if w:
            self.px = max(w.frame.left, min(self.px, w.frame.right - PET_W))
        if self.is_away:
            self.sleep(True)
            return
        if self.jumped:
            self.jumped = False
            self.set_state("idle")
            self.state_timer = random.uniform(1, 3)
        else:
            self.set_state("dizzy")                     # 떨어지거나 던져졌으면 잠깐 헤롱헤롱
            self.state_timer = DIZZY_DURATION

    # MARK: 틱
    def tick(self):
        t = now()
        dt = min(t - self.last_tick, 0.05)
        self.last_tick = t

        # 시스템 유휴 시간 (1초 간격)
        if t - self.last_idle_poll >= 1:
            self.last_idle_poll = t
            prev = self.sys_idle
            self.sys_idle = system_idle_seconds()
            if self.state == "sleep" and self.away_sleep and (self.sys_idle < 1 or self.sys_idle < prev):
                self.wake_up()
            elif self.is_away and self.state in ("idle", "walk", "dizzy", "watch"):
                self.sleep(True)

        # 전체화면 창이 펫이 있는 화면을 덮으면 숨고 멈춤 (0.5초 간격, 잡고 있을 땐 안 함)
        if HIDE_ON_FULLSCREEN and self.state != "drag" and t - self.last_fullscreen_poll >= 0.5:
            self.last_fullscreen_poll = t
            fs = fullscreen_rect()
            covered = fs is not None and fs.contains(self.midx, self.py - 1)
            if covered and not self.fullscreen_hidden:
                self.fullscreen_hidden = True
                self.hide()
            elif not covered and self.fullscreen_hidden:
                self.fullscreen_hidden = False
                self.show()
        if self.fullscreen_hidden:
            return

        # 드래그 중엔 이동·중력·타이머 전부 정지하고 흔들림만
        if self.state == "drag":
            self.drag_time += dt
            self.angle = WOBBLE_DEGREES * math.sin(2 * math.pi * WOBBLE_HZ * self.drag_time)
            self.stretch = DRAG_SCALE
            self.animate(dt)
            return
        self.angle = 0.0
        self.stretch = (1.0, 1.0)

        # 포어그라운드 창 조회 (서 있을 땐 0.15초, 공중에선 0.05초 간격)
        prev_win = self.front_win
        if t - self.last_win_query >= (0.05 if self.airborne else 0.15):
            self.last_win_query = t
            self.refresh_windows()

        # 앞 창이 바뀌면(새 창이 뜨거나 다른 창으로 전환) 잠깐 뒤 확률 없이 그 창으로
        w = self.front_win
        if w and (prev_win is None or w.number != prev_win.number):
            self.pending_jump = True
            self.pending_jump_at = t + random.uniform(*JUMP_REACT_DELAY)
            self.approaching = False
            if self.state in ("idle", "walk", "notice", "watch"):   # 바닥에 있어도 "!"로 알아챔 (헤롱헤롱 중엔 끝난 뒤에)
                self.notice_frame = (2 if self.state == "walk" else 0) + (0 if self.facing_left else 1)
                self.vx = 0
                self.walk_off_edge = False
                self.set_state("notice")
                self.state_timer = self.pending_jump_at - t
        if self.pending_jump and t >= self.pending_jump_at:
            if self.front_win is None or self.on_front():
                self.pending_jump = False               # 이미 그 창 위
                self.approaching = False
            elif self.state == "sleep" and not self.away_sleep:
                self.wake_up()                          # 낮잠이면 깨워서 다음 틱에
            elif self.state in ("idle", "walk", "notice", "watch") and self.go_to_front_window():
                self.pending_jump = False               # 공중이거나 헤롱헤롱 중이면 끝난 뒤 다시 시도

        prev_bottom = self.py
        area = self.area()
        floor = area.bottom
        # 화면 바닥(작업표시줄 위)에서 다닐 수 있는 가로 범위
        floor_lo, floor_hi = area.left, area.right
        if FLOOR_RANGE and QGuiApplication.screenAt(QPoint(int(self.midx), int(self.py - 1))) == QGuiApplication.primaryScreen():
            floor_lo, floor_hi = max(floor_lo, FLOOR_RANGE[0]), min(floor_hi, FLOOR_RANGE[1])

        # 발판 창 추적: 창이 조금이라도 움직이면(끌어서 옮김) 떨어지고, 닫힘·최소화되거나 발밑이 다른 창에 가려져도 떨어짐
        if self.platform and not self.airborne:
            p, w = self.platform, self.platform_now
            if w and w.number == p.number and (abs(w.frame.left - p.frame.left) > 0.5 or abs(w.frame.top - p.frame.top) > 0.5):
                self.platform = None
                self.drop_through = w.number            # 떨어지는 동안 이 창엔 다시 착지 안 함
                self.walk_off_edge = self.approaching = self.jumped = False
                if self.state == "sleep":
                    self.wake_up()
                self.vx = self.vy = 0
                self.set_state("fall")
            p = self.platform
            if w and p and w.number == p.number:
                self.platform = w
                if any(r.contains(self.midx, w.frame.top + 1) for r in self.platform_above):
                    self.platform = None
            else:
                self.platform = None

        # 창 위에 있을 때 그 창 안에서 마우스가 움직이면 "!" 후 쳐다보기 (작업표시줄 위에선 안 함)
        mouse = QCursor.pos()
        if math.hypot(mouse.x() - self.last_mouse.x(), mouse.y() - self.last_mouse.y()) > MOUSE_MOVE_THRESHOLD:
            self.last_mouse = mouse
            p = self.platform
            if p and p.frame.contains(mouse.x(), mouse.y()):
                self.last_mouse_move = t
                if self.state in ("idle", "walk"):
                    self.notice_frame = (2 if self.state == "walk" else 0) + (0 if self.facing_left else 1)
                    self.vx = 0
                    self.walk_off_edge = False
                    self.set_state("notice")
                    self.state_timer = NOTICE_DURATION
        if self.state in ("notice", "watch"):
            self.watch_left = mouse.x() < self.midx
        if self.state == "watch":
            self.facing_left = self.watch_left          # 쳐다보는 쪽 = 보고 있는 방향 (다음 "!" 방향이 어긋나지 않게)

        s = self.state
        if s in ("fall", "jump"):
            self.vy += GRAVITY * dt
            self.px += self.vx * dt
            self.py -= self.vy * dt
            if self.px <= area.left:
                self.px = area.left
                self.vx = abs(self.vx) * 0.5
            if self.px + PET_W >= area.right:
                self.px = area.right - PET_W
                self.vx = -abs(self.vx) * 0.5
            if self.py - PET_H <= area.top:             # 천장
                self.py = area.top + PET_H
                self.vy = min(self.vy, 0)
            if s == "jump" and self.vy < 0:
                self.set_state("fall")

            w = self.front_win
            if self.vy < 0 and self.py >= floor:
                self.land(floor, None)                  # 화면 바닥이 항상 우선
                self.px = max(floor_lo, min(self.px, floor_hi - PET_W))
            elif w and w.number != self.drop_through:
                # 이전 틱 대비 상대 위치로 판정 (펫과 창이 같이 움직여도 통과하지 않게)
                prev_top = prev_win.frame.top if prev_win and prev_win.number == w.number else w.frame.top
                if prev_bottom <= prev_top and self.py >= w.frame.top and w.frame.left <= self.midx <= w.frame.right:
                    self.land(w.frame.top, w)
        elif s == "walk":
            self.px += self.vx * dt
            p = self.platform
            if p and not self.walk_off_edge:
                if self.px <= p.frame.left:
                    self.px = p.frame.left
                    self.vx = abs(self.vx)
                if self.px + PET_W >= p.frame.right:
                    self.px = p.frame.right - PET_W
                    self.vx = -abs(self.vx)
            lo, hi = (floor_lo, floor_hi) if p is None else (area.left, area.right)
            if self.px <= lo:
                self.px = lo
                self.vx = abs(self.vx)
            if self.px + PET_W >= hi:
                self.px = hi - PET_W
                self.vx = -abs(self.vx)
            self.state_timer -= dt
            if self.state_timer <= 0:
                self.decide()
        elif s in ("idle", "dizzy"):
            self.state_timer -= dt
            if self.state_timer <= 0:
                if s == "dizzy" and self.pending_jump:  # 헤롱헤롱 중에 창이 바뀌었으면 정신 차린 뒤 "!"
                    self.pending_jump_at = t + random.uniform(*JUMP_REACT_DELAY)
                    self.notice_frame = 0 if self.facing_left else 1
                    self.set_state("notice")
                    self.state_timer = self.pending_jump_at - t
                else:
                    self.decide()
        elif s == "sleep":
            self.state_timer -= dt
            if self.state_timer <= 0:
                self.wake_up()                          # 낮잠 끝
        elif s == "notice":
            self.state_timer -= dt
            if self.state_timer <= 0:
                if self.pending_jump:                   # 창 알아챈 거면 바로 출발
                    self.vx = 0
                    self.set_state("idle")
                    self.state_timer = 5
                else:
                    self.set_state("watch")
        elif s == "watch":
            if t - self.last_mouse_move >= WATCH_TIMEOUT:   # 2초 조용하면 평소대로
                self.facing_left = self.watch_left
                self.decide()

        # 펫 중심이 창 범위를 벗어나면 발판 해제
        p = self.platform
        if p and not (p.frame.left <= self.midx <= p.frame.right):
            self.platform = None

        # 서 있는 상태: 바닥(창 상단 또는 화면 바닥)에 붙이기
        if self.state in STANDING:
            ground = self.platform.frame.top if self.platform else floor
            gap = ground - self.py
            if gap <= 1:
                self.py = ground                        # 창이 올라오면 즉시 밀어올림
                self.vy = 0
            elif self.state == "sleep":
                self.wake_up()                          # 자다가 발판이 내려가거나 사라지면 깨서 떨어짐
                self.platform = None
                self.set_state("fall")
            elif self.platform and gap < SOFT_DROP_LIMIT:
                # 조금 내려간 발판: 상태 유지한 채 툭 떨어져 다시 착지
                self.vy += GRAVITY * dt
                self.py = min(ground, self.py - self.vy * dt)
                if self.py >= ground:
                    self.vy = 0
            else:
                self.platform = None
                self.walk_off_edge = False
                self.set_state("fall")
        self.px = max(area.left, min(self.px, area.right - PET_W))
        if self.platform is None and self.state in STANDING:
            self.px = max(floor_lo, min(self.px, floor_hi - PET_W))
        self.place()

        if self.vx != 0:
            self.facing_left = self.vx < 0
        self.animate(dt)

    def animate(self, dt):
        s = self.state
        frames = self.sprites.frames_for(s)
        mirror = self.facing_left if SPRITES_FACE_RIGHT else not self.facing_left
        # notice·watch 그림은 방향별로 따로 있어서 뒤집지 않음
        n = self.sprites.named("notice")
        if s == "notice" and n and len(n) >= 4:
            frames, mirror = [n[self.notice_frame]], False
        wf = self.sprites.named("watchleft" if self.watch_left else "watchright")
        if s == "watch" and wf:
            frames, mirror = wf, False
        self.anim_acc += dt
        fps = SLEEP_FPS if s == "sleep" else WALK_FPS if s == "walk" else WATCH_FPS if s == "watch" else ANIM_FPS
        if self.anim_acc >= 1 / fps:
            self.anim_acc = 0.0
            self.frame_idx += 1
        if s == "watch" and len(frames) > 2:
            # 왕복 재생 (1 2 3 2 1 2 3 …): 눈동자가 자연스럽게 오가도록
            period = len(frames) * 2 - 2
            self.frame_idx %= period
            img = frames[self.frame_idx if self.frame_idx < len(frames) else period - self.frame_idx]
        else:
            if self.frame_idx >= len(frames):
                self.frame_idx = len(frames) - 1 if s == "jump" else 0   # 점프는 한 번만 재생
            img = frames[self.frame_idx]
        look = (id(img), mirror, self.angle, self.stretch)
        if look != getattr(self, "_look", None):
            self._look = look
            self.image, self.mirrored = img, mirror
            self.update()

    def paintEvent(self, _):
        img = self.image
        if img is None:
            return
        w, h = img.width() / img.devicePixelRatio(), img.height() / img.devicePixelRatio()
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        # 발 아래 중앙을 기준점으로 회전·스케일·좌우반전
        p.translate(self.width() / 2, self.height())
        p.rotate(self.angle)
        p.scale(self.stretch[0] * (-1 if self.mirrored else 1), self.stretch[1])
        p.drawPixmap(QRectF(-w / 2, -h, w, h), img, QRectF(img.rect()))
        p.end()

    # MARK: 마우스
    def mousePressEvent(self, e):
        if e.button() == Qt.RightButton:
            self.show_menu()
            return
        if e.button() != Qt.LeftButton:
            return
        m = e.globalPosition().toPoint()
        self.press_location = m
        self.drag_offset = m - self.pos()
        self.drag_samples = [(now(), self.pos().x(), self.pos().y())]
        self.press_is_jump = False
        if self.state == "sleep":
            self.wake_up()                              # 콕 찌르면 깸

    def mouseDoubleClickEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        self.press_is_jump = True                       # 더블클릭은 점프만
        if not self.airborne:
            self.vy = JUMP_POWER
            self.vx = 0
            self.platform = None
            self.jumped = True
            self.set_state("jump")

    def mouseMoveEvent(self, e):
        if not e.buttons() & Qt.LeftButton or self.press_is_jump:
            return
        m = e.globalPosition().toPoint()
        if self.state != "drag":
            # 살짝 떨린 클릭은 드래그로 치지 않음
            d = m - self.press_location
            if math.hypot(d.x(), d.y()) <= 3:
                return
            if self.state == "sleep":
                self.wake_up()
            self.set_state("drag")
            self.drag_time = 0.0
            self.vx = self.vy = 0
            self.platform = None
            self.walk_off_edge = False
            self.jumped = False                         # 점프 중 잡혀서 던져지면 헤롱거림
        p = m - self.drag_offset
        t = now()
        self.drag_samples.append((t, p.x(), p.y()))
        self.drag_samples = [s for s in self.drag_samples if t - s[0] <= 0.1]
        self.px, self.py = p.x() + PAD_X, p.y() + WIN_H   # 화면 경계 제한 없음 (모니터 간 이동 가능)
        self.move(p)

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton or self.state != "drag":
            return
        # 최근 0.1초 동안의 이동만으로 던지는 속도 계산 (멈췄다 놓으면 0)
        t = now()
        recent = [s for s in self.drag_samples if t - s[0] <= 0.1]
        self.vx = self.vy = 0
        if len(recent) >= 2 and recent[-1][0] - recent[0][0] > 0.005:
            a, b = recent[0], recent[-1]
            span = b[0] - a[0]
            self.vx = max(-MAX_THROW, min((b[1] - a[1]) / span, MAX_THROW))
            self.vy = max(-MAX_THROW, min(-(b[2] - a[2]) / span, MAX_THROW))
        self.drag_samples = []
        self.set_state("fall")

    # MARK: 메뉴
    def show_menu(self):
        menu = QMenu()
        menu.addAction("스프라이트 폴더 열기", self.open_folder)
        menu.addAction("스프라이트 다시 불러오기", self.reload_sprites)
        menu.addAction("재우기", self.go_sleep)
        auto = menu.addAction("윈도우 시작 시 자동 실행")
        auto.setCheckable(True)
        auto.setChecked(autostart_enabled())
        auto.toggled.connect(set_autostart)
        menu.addSeparator()
        menu.addAction("종료", QApplication.quit)
        menu.exec(QCursor.pos())

    def open_folder(self):
        os.makedirs(SPRITE_DIR, exist_ok=True)
        # 처음 열 때 폴더가 비어 있으면 프로그램에 들어 있는 기본 스프라이트를 복사해 둠 (보고 고치기 쉽게)
        if not png_files(SPRITE_DIR):
            import shutil
            for f in png_files(BUNDLED_SPRITE_DIR):
                shutil.copy2(os.path.join(BUNDLED_SPRITE_DIR, f), os.path.join(SPRITE_DIR, f))
        os.startfile(SPRITE_DIR)

    def reload_sprites(self):
        self.sprites = Sprites(self.dpr)
        self.frame_idx = 0

    def go_sleep(self):
        if not self.airborne and self.state != "drag":
            self.sleep(False, random.uniform(*NAP_DURATION))


def main():
    # 이미 켜져 있으면 그냥 종료 (자동 실행 + 직접 실행으로 펫이 둘 생기지 않게)
    global _instance_mutex
    _instance_mutex = kernel32.CreateMutexW(None, False, "Local\\MomongaPet")
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        return
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    pet = Pet()  # noqa: F841
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
