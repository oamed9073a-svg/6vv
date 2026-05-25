"""Bot.py - PC horror game.

Ты ночной техник в заброшенном дата-центре. ИИ "BOT" вышел из-под контроля -
он живёт в сети, смотрит через камеры, охотится через коридоры серверных стоек.

Перезагрузи 5 терминалов чтобы восстановить питание и сбежать через шлюз.
Но он услышит каждое нажатие клавиши.

ЗАПУСК:
    pip install pygame
    python Bot.py

УПРАВЛЕНИЕ:
    WASD / стрелки   - движение
    Shift            - бег (быстро, но шумно)
    Ctrl             - красться (тише)
    F                - фонарь (видит тебя в камерах ярче)
    E / Space        - взаимодействие с терминалом
    ESC              - выход

ПОДСКАЗКИ:
    - Камеры (красные конусы) сканируют коридоры. Не попадай в их свет.
    - BOT слышит твой бег и взлом терминалов.
    - Когда экран глючит сильно - он рядом.
    - Свет фонаря в BOT-а на короткое время оглушает.
"""

from __future__ import annotations

import math
import random
import sys
import time

import pygame

# =====================================================================
# Конфиг
# =====================================================================
W, H = 1024, 640
FPS = 60
CELL = 56

# Палитра - "терминальная" зелёная схема с красными акцентами
COL_BG = (4, 6, 8)
COL_FLOOR = (10, 16, 14)
COL_FLOOR_GRID = (16, 28, 22)
COL_WALL = (24, 30, 36)
COL_WALL_TOP = (40, 52, 58)
COL_SCANLINE = (0, 30, 20, 60)
COL_GREEN = (80, 220, 130)
COL_GREEN_DIM = (40, 140, 80)
COL_RED = (220, 40, 40)
COL_RED_DIM = (120, 20, 20)
COL_AMBER = (220, 160, 40)
COL_BLUE = (80, 160, 220)
COL_TERMINAL_OFF = (40, 20, 20)
COL_TERMINAL_ON = (40, 80, 50)
COL_TEXT = (200, 240, 210)
COL_TEXT_DIM = (90, 130, 100)
COL_GLITCH = (220, 60, 200)

# =====================================================================
# Карта дата-центра
# Символы:
#   #  - стена серверной стойки
#   .  - пол
#   S  - спавн игрока
#   D  - дверь шлюза (выход)
#   T  - терминал
#   B  - точка спавна BOT-а
#   C  - камера (направление сегментом ниже)
# =====================================================================
MAP = [
    "##########################",
    "#S........#.....#T.......#",
    "#.........#.....#........#",
    "#..####...#.###.#....###.#",
    "#..#..#...#.#.#.#....#.#.#",
    "#..#T.#...#.#.#......#...#",
    "#..#..#...###.######.#.###",
    "#..#.##...............#..#",
    "#.........############.#.#",
    "#.######B.#..........#.#.#",
    "#.#......##.########.#.#.#",
    "#.#.######..#......#.#...#",
    "#.#.....T#..#.####.#.###.#",
    "#.#######...#..T.#.#.#...#",
    "#...........#.####.#.#.#.#",
    "#####.#######......#.#.#.#",
    "#.....#............#...#.#",
    "#.###.#.#####.######.###.#",
    "#.#T..#.#...........#....#",
    "#.#.###.#.#####.#####.####",
    "#.#.....#.....#.........D#",
    "##########################",
]
ROWS = len(MAP)
COLS = len(MAP[0])
WORLD_W = COLS * CELL
WORLD_H = ROWS * CELL


def cell_at(cx, cy):
    if 0 <= cx < COLS and 0 <= cy < ROWS:
        return MAP[cy][cx]
    return "#"


def is_wall(cx, cy):
    return cell_at(cx, cy) == "#"


def is_wall_px(px, py):
    return is_wall(int(px // CELL), int(py // CELL))


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def dist(ax, ay, bx, by):
    return math.hypot(ax - bx, ay - by)


def lerp(a, b, t):
    return a + (b - a) * t


def line_of_sight(ax, ay, bx, by):
    """True если между точками нет стены."""
    dx, dy = bx - ax, by - ay
    d = math.hypot(dx, dy) or 1
    steps = max(2, int(d / 8))
    for i in range(1, steps):
        t = i / steps
        if is_wall_px(ax + dx * t, ay + dy * t):
            return False
    return True


def bfs_path(fx, fy, tx, ty):
    """Поиск пути по клеткам, возвращает список центров клеток."""
    sx, sy = int(fx // CELL), int(fy // CELL)
    ex, ey = int(tx // CELL), int(ty // CELL)
    if (sx, sy) == (ex, ey):
        return []
    if is_wall(ex, ey):
        return []
    visited = [[False] * COLS for _ in range(ROWS)]
    prev = [[None] * COLS for _ in range(ROWS)]
    queue = [(sx, sy)]
    visited[sy][sx] = True
    head = 0
    found = False
    while head < len(queue):
        cx, cy = queue[head]
        head += 1
        if (cx, cy) == (ex, ey):
            found = True
            break
        for ddx, ddy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = cx + ddx, cy + ddy
            if not (0 <= nx < COLS and 0 <= ny < ROWS):
                continue
            if visited[ny][nx] or is_wall(nx, ny):
                continue
            visited[ny][nx] = True
            prev[ny][nx] = (cx, cy)
            queue.append((nx, ny))
    if not found:
        return []
    path = []
    cur = (ex, ey)
    while cur != (sx, sy):
        cx, cy = cur
        path.append(((cx + 0.5) * CELL, (cy + 0.5) * CELL))
        p = prev[cy][cx]
        if p is None:
            break
        cur = p
    path.reverse()
    return path


# =====================================================================
# Аудио - синтезируем атмосферу через pygame.sndarray
# =====================================================================
class Audio:
    def __init__(self):
        self.enabled = False
        try:
            pygame.mixer.pre_init(22050, -16, 1, 512)
            pygame.mixer.init()
            self.enabled = True
        except Exception:
            return

        self.sounds = {}
        self._make_sounds()
        self.heartbeat_channel = None
        self.heartbeat_intensity = 0.0
        self.heartbeat_next = 0.0

    def _make_buffer(self, samples_fn, duration, volume=0.4):
        try:
            import numpy as np
        except ImportError:
            np = None
        sr = 22050
        n = int(duration * sr)
        if np is not None:
            t = np.linspace(0, duration, n, endpoint=False)
            data = samples_fn(t)
            data = np.clip(data, -1, 1)
            data = (data * volume * 32767).astype(np.int16)
            return pygame.sndarray.make_sound(data)
        # fallback на pure python (медленнее)
        import array
        buf = array.array("h")
        for i in range(n):
            v = samples_fn(i / sr)
            v = max(-1.0, min(1.0, v))
            buf.append(int(v * volume * 32767))
        return pygame.mixer.Sound(buffer=buf.tobytes())

    def _make_sounds(self):
        try:
            import numpy as np
            HAVE_NP = True
        except ImportError:
            HAVE_NP = False

        # Биение сердца (короткий "thump")
        def heartbeat(t):
            if HAVE_NP:
                import numpy as np
                env = np.exp(-t * 18)
                tone = np.sin(2 * math.pi * (60 - t * 200) * t)
                return tone * env
            return math.sin(2 * math.pi * (60 - t * 200) * t) * math.exp(-t * 18)

        # Глитч-шум
        def glitch(t):
            if HAVE_NP:
                import numpy as np
                noise = (np.random.rand(len(t)) * 2 - 1)
                env = np.exp(-t * 8) * (1 - np.exp(-t * 60))
                return noise * env
            import random as r
            return (r.random() * 2 - 1) * math.exp(-t * 8)

        # Подбор / нажатие клавиши
        def click(t):
            if HAVE_NP:
                import numpy as np
                env = np.exp(-t * 80)
                tone = np.sin(2 * math.pi * 800 * t) + np.sin(2 * math.pi * 1200 * t) * 0.5
                return tone * env * 0.5
            return (math.sin(2 * math.pi * 800 * t) +
                    math.sin(2 * math.pi * 1200 * t) * 0.5) * math.exp(-t * 80) * 0.5

        # Сигнал терминала "успех"
        def success(t):
            if HAVE_NP:
                import numpy as np
                env = np.exp(-t * 6)
                f = 600 + 400 * np.clip(t * 3, 0, 1)
                return np.sin(2 * math.pi * f * t) * env * 0.5
            f = 600 + 400 * min(t * 3, 1)
            return math.sin(2 * math.pi * f * t) * math.exp(-t * 6) * 0.5

        # Рык / алерт BOT-а
        def alert(t):
            if HAVE_NP:
                import numpy as np
                env = np.exp(-t * 3)
                base = np.sin(2 * math.pi * 50 * t) + np.sin(2 * math.pi * 65 * t) * 0.6
                noise = (np.random.rand(len(t)) * 2 - 1) * 0.3
                return (base + noise) * env * 0.7
            return (math.sin(2 * math.pi * 50 * t) +
                    math.sin(2 * math.pi * 65 * t) * 0.6) * math.exp(-t * 3) * 0.7

        # Скрим (поимка)
        def scream(t):
            if HAVE_NP:
                import numpy as np
                f = 200 * np.exp(-t * 1.5) + 40
                env = np.exp(-t * 1.2)
                noise = (np.random.rand(len(t)) * 2 - 1) * 0.4
                tone = np.sin(2 * math.pi * f * t)
                return (tone * 0.7 + noise) * env
            return math.sin(2 * math.pi * (200 * math.exp(-t * 1.5) + 40) * t) * math.exp(-t * 1.2)

        # Дверь / шлюз открывается
        def door(t):
            if HAVE_NP:
                import numpy as np
                env = np.exp(-t * 2) * (1 - np.exp(-t * 10))
                tone = np.sin(2 * math.pi * 80 * t) + np.sin(2 * math.pi * 120 * t) * 0.5
                return tone * env * 0.6
            env = math.exp(-t * 2) * (1 - math.exp(-t * 10))
            return (math.sin(2 * math.pi * 80 * t) +
                    math.sin(2 * math.pi * 120 * t) * 0.5) * env * 0.6

        try:
            self.sounds["heartbeat"] = self._make_buffer(heartbeat, 0.3, 0.5)
            self.sounds["glitch"] = self._make_buffer(glitch, 0.25, 0.4)
            self.sounds["click"] = self._make_buffer(click, 0.08, 0.35)
            self.sounds["success"] = self._make_buffer(success, 0.5, 0.45)
            self.sounds["alert"] = self._make_buffer(alert, 0.8, 0.6)
            self.sounds["scream"] = self._make_buffer(scream, 2.0, 0.8)
            self.sounds["door"] = self._make_buffer(door, 1.2, 0.6)
        except Exception:
            self.enabled = False

        # Дрон-амбиент
        try:
            import numpy as np
            sr = 22050
            dur = 4.0
            n = int(sr * dur)
            t = np.linspace(0, dur, n, endpoint=False)
            drone = (np.sin(2 * math.pi * 55 * t) * 0.4 +
                     np.sin(2 * math.pi * 78 * t) * 0.3 +
                     np.sin(2 * math.pi * 110.7 * t) * 0.15)
            mod = 0.5 + 0.5 * np.sin(2 * math.pi * 0.07 * t)
            drone = drone * mod * 0.15
            data = (np.clip(drone, -1, 1) * 32767).astype(np.int16)
            self.ambient = pygame.sndarray.make_sound(data)
            self.ambient_channel = self.ambient.play(loops=-1)
            if self.ambient_channel:
                self.ambient_channel.set_volume(0.5)
        except Exception:
            self.ambient = None
            self.ambient_channel = None

    def play(self, name, volume=1.0):
        if not self.enabled:
            return
        s = self.sounds.get(name)
        if s is None:
            return
        ch = s.play()
        if ch:
            ch.set_volume(volume)

    def update_heartbeat(self, dt, intensity):
        if not self.enabled:
            return
        self.heartbeat_intensity = intensity
        if intensity < 0.08:
            return
        self.heartbeat_next -= dt
        if self.heartbeat_next <= 0:
            self.play("heartbeat", intensity)
            self.heartbeat_next = max(0.32, 0.95 - intensity * 0.65)


# =====================================================================
# Сущности
# =====================================================================
class Player:
    def __init__(self, x, y):
        self.x, self.y = x, y
        self.r = 12
        self.speed_walk = 130.0
        self.speed_run = 200.0
        self.speed_sneak = 70.0
        self.facing = 0.0
        self.battery = 100.0
        self.health = 100.0
        self.light_on = False
        self.noise = 0.0
        self.running = False
        self.sneaking = False
        self.hit_flash = 0.0


class Terminal:
    def __init__(self, x, y):
        self.x, self.y = x, y
        self.done = False
        self.in_progress = False
        self.progress = 0.0  # 0..1
        self.hack_code = ""
        self.hack_typed = ""


class Camera:
    def __init__(self, x, y, base_angle):
        self.x, self.y = x, y
        self.base_angle = base_angle
        self.angle = base_angle
        self.sweep_t = random.uniform(0, math.tau)
        self.range = 200
        self.fov = 0.6
        self.alerted = False
        self.alert_timer = 0.0

    def update(self, dt):
        self.sweep_t += dt * 0.7
        self.angle = self.base_angle + math.sin(self.sweep_t) * 0.7
        if self.alert_timer > 0:
            self.alert_timer -= dt
            if self.alert_timer <= 0:
                self.alerted = False

    def sees(self, px, py):
        d = dist(self.x, self.y, px, py)
        if d > self.range:
            return False
        ang = math.atan2(py - self.y, px - self.x)
        diff = abs(((ang - self.angle + math.pi * 3) % (math.pi * 2)) - math.pi)
        if diff > self.fov:
            return False
        return line_of_sight(self.x, self.y, px, py)


class Bot:
    def __init__(self, x, y):
        self.x, self.y = x, y
        self.r = 14
        self.speed = 105.0
        self.state = "patrol"  # patrol / investigate / chase
        self.target = None
        self.path = []
        self.path_timer = 0.0
        self.patrol_timer = 0.0
        self.stunned = 0.0
        self.growl_timer = 0.0
        self.glitch_phase = 0.0

    def update(self, dt, player, game):
        self.glitch_phase += dt * 4
        if self.stunned > 0:
            self.stunned -= dt
            return

        d = dist(self.x, self.y, player.x, player.y)

        # Детекция игрока:
        detect = False
        # 1) Зрение по прямой
        if d < 360 and line_of_sight(self.x, self.y, player.x, player.y):
            ang = math.atan2(player.y - self.y, player.x - self.x)
            face_ang = math.atan2(player.y - self.y, player.x - self.x) if not self.path else (
                math.atan2(self.path[0][1] - self.y, self.path[0][0] - self.x))
            diff = abs(((ang - face_ang + math.pi * 3) % (math.pi * 2)) - math.pi)
            if d < 100 or diff < 0.9:
                detect = True
        # 2) Слух (шум игрока)
        hear_radius = 60 + player.noise * 380
        if d < hear_radius and line_of_sight(self.x, self.y, player.x, player.y):
            detect = True
        # 3) Камера видит игрока => BOT идёт туда
        for cam in game.cameras:
            if cam.alerted and dist(self.x, self.y, cam.x, cam.y) > 50:
                if self.state != "chase":
                    self.target = (player.x, player.y)
                    self.path = []
                    self.state = "investigate"

        if detect:
            if self.state != "chase":
                game.audio.play("alert", 0.9)
            self.state = "chase"
            self.target = (player.x, player.y)
            self.path = []
            self.growl_timer -= dt
            if self.growl_timer <= 0:
                game.audio.play("alert", 0.4)
                self.growl_timer = 2.0 + random.random() * 1.5
        elif self.state == "chase":
            if self.target and dist(self.target[0], self.target[1], self.x, self.y) < 24:
                self.state = "investigate"
                self.target = None
                self.patrol_timer = 0

        if self.state in ("patrol", "investigate"):
            self.patrol_timer -= dt
            if self.target is None or self.patrol_timer <= 0:
                self.target = game.random_floor_pos()
                self.path = []
                self.patrol_timer = 7.0 + random.random() * 4

        # Пересчёт пути
        self.path_timer -= dt
        if self.target and (not self.path or self.path_timer <= 0):
            self.path = bfs_path(self.x, self.y, self.target[0], self.target[1])
            self.path_timer = 0.4

        if self.path:
            tx, ty = self.path[0]
            dx, dy = tx - self.x, ty - self.y
            dd = math.hypot(dx, dy)
            if dd < 8:
                self.path.pop(0)
            else:
                spd = self.speed * (1.6 if self.state == "chase" else 0.8)
                step_x = (dx / dd) * spd * dt
                step_y = (dy / dd) * spd * dt
                # Движение с коллизией по осям
                nx = self.x + step_x
                if not is_wall_px(nx - self.r, self.y) and not is_wall_px(nx + self.r, self.y):
                    self.x = nx
                ny = self.y + step_y
                if not is_wall_px(self.x, ny - self.r) and not is_wall_px(self.x, ny + self.r):
                    self.y = ny

        # Свет фонаря в лицо BOT-а -> стан
        if player.light_on:
            ang = math.atan2(self.y - player.y, self.x - player.x)
            diff = abs(((ang - player.facing + math.pi * 3) % (math.pi * 2)) - math.pi)
            if diff < 0.4 and d < 220 and line_of_sight(player.x, player.y, self.x, self.y):
                self.stunned = max(self.stunned, 0.06)


# =====================================================================
# Игра
# =====================================================================
class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Bot.py")
        self.screen = pygame.display.set_mode((W, H))
        self.clock = pygame.time.Clock()
        try:
            self.font = pygame.font.SysFont("dejavusansmono,consolas,courier", 14)
            self.font_big = pygame.font.SysFont("dejavusansmono,consolas,courier", 28, bold=True)
            self.font_small = pygame.font.SysFont("dejavusansmono,consolas,courier", 11)
            self.font_mono = pygame.font.SysFont("dejavusansmono,consolas,courier", 18, bold=True)
        except Exception:
            self.font = pygame.font.Font(None, 18)
            self.font_big = pygame.font.Font(None, 32)
            self.font_small = pygame.font.Font(None, 14)
            self.font_mono = pygame.font.Font(None, 22)

        # CRT scanlines overlay
        self.scanlines = pygame.Surface((W, H), pygame.SRCALPHA)
        for y in range(0, H, 2):
            pygame.draw.line(self.scanlines, (0, 0, 0, 60), (0, y), (W, y))

        # Vignette
        self.vignette = pygame.Surface((W, H), pygame.SRCALPHA)
        cx, cy = W // 2, H // 2
        max_r = math.hypot(cx, cy)
        for r in range(int(max_r), 0, -16):
            a = int(140 * (r / max_r) ** 3)
            pygame.draw.circle(self.vignette, (0, 0, 0, a), (cx, cy), r)

        self.audio = Audio()
        self.scene = "menu"
        self.message = ""
        self.message_timer = 0.0
        self.boot_log = []
        self.last_boot_t = 0
        self.boot_messages = [
            "BOOT> kernel modules loaded.",
            "BOOT> network: 192.168.0.13 ASSIGNED",
            "BOOT> camera array: ONLINE (4 nodes)",
            "BOOT> autonomous unit BOT.py: SPAWNED",
            "BOOT> WARNING: emergency shutdown sequence required",
            "BOOT> 5 terminals must be rebooted",
            "BOOT> good luck, technician.",
        ]
        self.init_game()

    def init_game(self):
        self.player = None
        self.bot = None
        self.terminals = []
        self.cameras = []
        spawn = (CELL * 1.5, CELL * 1.5)
        bot_spawn = (CELL * (COLS - 2), CELL * (ROWS - 2))
        self.exit_door = None

        for y in range(ROWS):
            for x in range(COLS):
                c = MAP[y][x]
                px, py = (x + 0.5) * CELL, (y + 0.5) * CELL
                if c == "S":
                    spawn = (px, py)
                elif c == "B":
                    bot_spawn = (px, py)
                elif c == "T":
                    self.terminals.append(Terminal(px, py))
                elif c == "D":
                    self.exit_door = (px, py)

        # Камеры расставим вручную в подходящих местах
        self.cameras = [
            Camera(CELL * 12.5, CELL * 2.5, math.pi * 0.75),
            Camera(CELL * 20.5, CELL * 5.5, math.pi),
            Camera(CELL * 6.5, CELL * 14.5, 0.0),
            Camera(CELL * 18.5, CELL * 16.5, math.pi * 1.25),
            Camera(CELL * 11.5, CELL * 18.5, math.pi * 0.25),
        ]

        self.player = Player(*spawn)
        self.bot = Bot(*bot_spawn)
        self.terminals_done = 0
        self.win = False
        self.dead = False
        self.shake = 0.0
        self.flash = 0.0
        self.glitch_amount = 0.0
        self.cam_x = 0.0
        self.cam_y = 0.0
        self.time = 0.0
        self.boot_log = []
        self.last_boot_t = 0
        self.active_terminal = None
        self.hack_target = ""
        self.hack_typed = ""
        self.hack_timer = 0.0
        self.boot_log_idx = 0

    # =================================================================
    def random_floor_pos(self):
        for _ in range(100):
            x = random.randint(1, COLS - 2)
            y = random.randint(1, ROWS - 2)
            if not is_wall(x, y):
                return ((x + 0.5) * CELL, (y + 0.5) * CELL)
        return (WORLD_W / 2, WORLD_H / 2)

    def show_message(self, text, duration=3.0):
        self.message = text
        self.message_timer = duration

    def boot_log_push(self, text):
        self.boot_log.append((text, time.time()))
        if len(self.boot_log) > 8:
            self.boot_log.pop(0)

    # =================================================================
    # Hacking mini-game
    # =================================================================
    def start_hack(self, term):
        self.active_terminal = term
        term.in_progress = True
        # Сгенерируем "код" - случайные буквы
        chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        self.hack_target = "".join(random.choice(chars) for _ in range(6))
        self.hack_typed = ""
        self.hack_timer = 12.0
        self.show_message(f"ВЗЛОМ ТЕРМИНАЛА - набери: {self.hack_target}", 12)

    def hack_input(self, ch):
        if not self.active_terminal:
            return
        idx = len(self.hack_typed)
        if idx < len(self.hack_target):
            if ch == self.hack_target[idx]:
                self.hack_typed += ch
                self.audio.play("click", 0.4)
                self.player.noise = max(self.player.noise, 0.4)
                if self.hack_typed == self.hack_target:
                    self.complete_hack()
            else:
                # ошибка - сброс прогресса
                self.hack_typed = ""
                self.glitch_amount = max(self.glitch_amount, 0.4)
                self.audio.play("glitch", 0.4)

    def cancel_hack(self):
        if self.active_terminal:
            self.active_terminal.in_progress = False
            self.active_terminal = None
            self.show_message("Взлом прерван", 2)

    def complete_hack(self):
        term = self.active_terminal
        if not term:
            return
        term.done = True
        term.in_progress = False
        self.active_terminal = None
        self.terminals_done += 1
        self.audio.play("success", 0.8)
        self.show_message(
            f"ТЕРМИНАЛ {self.terminals_done}/5 ПЕРЕЗАГРУЖЕН", 3)
        self.boot_log_push(f"TERMINAL {self.terminals_done}/5: RESTART OK")
        # BOT становится агрессивнее
        if self.terminals_done >= 3:
            self.bot.state = "investigate"
            self.bot.target = (self.player.x, self.player.y)
        if self.terminals_done >= 5:
            self.boot_log_push("GATEWAY DOOR: UNLOCKED")
            self.show_message("ШЛЮЗ ОТКРЫТ. Беги к выходу!", 4)

    # =================================================================
    # Update
    # =================================================================
    def update(self, dt):
        if self.scene != "play":
            return
        if self.dead or self.win:
            return
        self.time += dt
        keys = pygame.key.get_pressed()
        p = self.player

        # Затухание шума игрока
        p.noise *= math.pow(0.3, dt)

        if self.active_terminal:
            # Во время взлома можно двигаться, но медленно
            self.hack_timer -= dt
            if self.hack_timer <= 0:
                self.cancel_hack()

        # Движение
        mx, my = 0, 0
        if keys[pygame.K_w] or keys[pygame.K_UP]:
            my -= 1
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            my += 1
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            mx -= 1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            mx += 1

        moving = (mx != 0 or my != 0)
        if moving:
            ll = math.hypot(mx, my)
            mx, my = mx / ll, my / ll
            p.facing = math.atan2(my, mx)

        p.running = bool(keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]) and moving and not self.active_terminal
        p.sneaking = bool(keys[pygame.K_LCTRL] or keys[pygame.K_RCTRL]) and moving

        if moving:
            if self.active_terminal:
                speed = p.speed_sneak * 0.5
            elif p.running:
                speed = p.speed_run
            elif p.sneaking:
                speed = p.speed_sneak
            else:
                speed = p.speed_walk
            nx = p.x + mx * speed * dt
            if not is_wall_px(nx - p.r, p.y) and not is_wall_px(nx + p.r, p.y):
                p.x = nx
            ny = p.y + my * speed * dt
            if not is_wall_px(p.x, ny - p.r) and not is_wall_px(p.x, ny + p.r):
                p.y = ny

            if p.running:
                p.noise = max(p.noise, 1.0)
            elif p.sneaking:
                p.noise = max(p.noise, 0.12)
            else:
                p.noise = max(p.noise, 0.35)

        p.x = clamp(p.x, p.r, WORLD_W - p.r)
        p.y = clamp(p.y, p.r, WORLD_H - p.r)

        # Камера
        target_cam_x = p.x - W / 2
        target_cam_y = p.y - H / 2
        self.cam_x = lerp(self.cam_x, target_cam_x, min(1.0, dt * 6))
        self.cam_y = lerp(self.cam_y, target_cam_y, min(1.0, dt * 6))
        self.cam_x = clamp(self.cam_x, 0, max(0, WORLD_W - W))
        self.cam_y = clamp(self.cam_y, 0, max(0, WORLD_H - H))

        # Фонарь
        if p.light_on and p.battery > 0:
            p.battery = max(0, p.battery - dt * 0.9)
            if p.battery == 0:
                p.light_on = False
                self.show_message("Батарея фонаря разряжена!", 2.5)
            # Свет привлекает - даёт небольшой шум "электрический"
            p.noise = max(p.noise, 0.1)

        # Камеры наблюдают
        for cam in self.cameras:
            cam.update(dt)
            if cam.sees(p.x, p.y):
                # Свет фонаря засветит даже сильнее
                if p.light_on or not p.sneaking:
                    cam.alerted = True
                    cam.alert_timer = 4.0
                    p.noise = max(p.noise, 0.3)

        # BOT
        self.bot.update(dt, p, self)
        d_bot = dist(p.x, p.y, self.bot.x, self.bot.y)

        # Глитч-эффект от близости BOT-а
        if d_bot < 320 and line_of_sight(p.x, p.y, self.bot.x, self.bot.y):
            target_g = clamp((1 - d_bot / 320), 0, 1)
        elif d_bot < 200:
            target_g = clamp((1 - d_bot / 200) * 0.5, 0, 0.5)
        else:
            target_g = 0
        if self.bot.state == "chase":
            target_g = max(target_g, 0.4)
        self.glitch_amount = lerp(self.glitch_amount, target_g, dt * 4)

        # Сердцебиение
        self.audio.update_heartbeat(dt, max(0, target_g - 0.05))

        # Поимка
        if d_bot < p.r + self.bot.r - 2:
            self.trigger_death()

        # Сообщения
        if self.message_timer > 0:
            self.message_timer -= dt
            if self.message_timer <= 0:
                self.message = ""

        # shake/flash
        if self.shake > 0:
            self.shake -= dt
        if self.flash > 0:
            self.flash -= dt * 3

        # Выход через шлюз
        if self.exit_door and self.terminals_done >= 5:
            if dist(p.x, p.y, self.exit_door[0], self.exit_door[1]) < 36:
                self.trigger_win()

    def trigger_death(self):
        if self.dead:
            return
        self.dead = True
        self.shake = 1.0
        self.flash = 1.0
        self.audio.play("scream", 1.0)
        self.boot_log_push("CRITICAL: technician disconnected")

    def trigger_win(self):
        if self.win:
            return
        self.win = True
        self.audio.play("door", 1.0)
        self.boot_log_push("EVAC OK: returning to surface")

    # =================================================================
    # Render
    # =================================================================
    def render(self):
        if self.scene == "menu":
            self.render_menu()
        elif self.scene == "play":
            self.render_play()
        elif self.scene == "dead":
            self.render_dead()
        elif self.scene == "win":
            self.render_win()
        # CRT overlay
        self.screen.blit(self.scanlines, (0, 0))
        self.screen.blit(self.vignette, (0, 0))

        # Глобальный глитч-сдвиг
        if self.scene == "play" and self.glitch_amount > 0.15:
            self.apply_screen_glitch(self.glitch_amount)

        # Flash
        if self.flash > 0:
            surf = pygame.Surface((W, H))
            surf.fill((200, 0, 0))
            surf.set_alpha(int(self.flash * 200))
            self.screen.blit(surf, (0, 0))

    def render_menu(self):
        self.screen.fill(COL_BG)
        # Лого
        title = self.font_big.render("Bot.py", True, COL_GREEN)
        sub = self.font.render("> a horror in five terminals <", True, COL_GREEN_DIM)
        self.screen.blit(title, ((W - title.get_width()) // 2, 120))
        self.screen.blit(sub, ((W - sub.get_width()) // 2, 165))

        # Boot log progressive reveal
        if time.time() - self.last_boot_t > 0.5 and self.boot_log_idx < len(self.boot_messages):
            self.boot_log_push(self.boot_messages[self.boot_log_idx])
            self.boot_log_idx += 1
            self.last_boot_t = time.time()
            if self.audio.enabled:
                self.audio.play("click", 0.2)

        y0 = 220
        for i, (line, t) in enumerate(self.boot_log):
            txt = self.font.render(line, True, COL_GREEN)
            self.screen.blit(txt, (W // 2 - 250, y0 + i * 22))

        # Подсказка
        if self.boot_log_idx >= len(self.boot_messages):
            blink = (math.sin(time.time() * 4) > 0)
            if blink:
                msg = self.font.render(
                    "ENTER - войти   ESC - выход", True, COL_AMBER)
                self.screen.blit(msg, ((W - msg.get_width()) // 2, H - 80))

        ctrls = [
            "WASD/стрелки - движение     Shift - бег     Ctrl - красться",
            "F - фонарь    E/Space - терминал    ESC - выход",
        ]
        for i, c in enumerate(ctrls):
            t = self.font_small.render(c, True, COL_TEXT_DIM)
            self.screen.blit(t, ((W - t.get_width()) // 2, H - 50 + i * 16))

    def render_dead(self):
        self.screen.fill((20, 0, 0))
        title = self.font_big.render("CONNECTION LOST", True, COL_RED)
        self.screen.blit(title, ((W - title.get_width()) // 2, H // 2 - 80))
        info = self.font.render(
            f"Терминалов перезагружено: {self.terminals_done}/5", True, COL_TEXT)
        self.screen.blit(info, ((W - info.get_width()) // 2, H // 2 - 20))
        msg = self.font.render(
            "BOT.py получил полный контроль над сетью.", True, COL_RED_DIM)
        self.screen.blit(msg, ((W - msg.get_width()) // 2, H // 2 + 10))
        blink = (math.sin(time.time() * 4) > 0)
        if blink:
            hint = self.font.render("R - попробовать снова    ESC - выход",
                                    True, COL_AMBER)
            self.screen.blit(hint, ((W - hint.get_width()) // 2, H - 90))

    def render_win(self):
        self.screen.fill((4, 12, 8))
        title = self.font_big.render("EVACUATION COMPLETE", True, COL_GREEN)
        self.screen.blit(title, ((W - title.get_width()) // 2, H // 2 - 100))
        lines = [
            "Шлюз закрылся за спиной.",
            "Лифт со скрипом потащил тебя на поверхность.",
            "На мониторе - последняя строчка лога:",
            "",
            "  BOT> see you soon, technician.",
        ]
        for i, l in enumerate(lines):
            col = COL_AMBER if i == 4 else COL_TEXT
            t = self.font.render(l, True, col)
            self.screen.blit(t, ((W - t.get_width()) // 2, H // 2 - 40 + i * 22))
        blink = (math.sin(time.time() * 4) > 0)
        if blink:
            hint = self.font.render(
                "R - сыграть ещё    ESC - выход", True, COL_GREEN_DIM)
            self.screen.blit(hint, ((W - hint.get_width()) // 2, H - 90))

    def render_play(self):
        self.screen.fill(COL_BG)
        shake_x = (random.random() - 0.5) * self.shake * 14
        shake_y = (random.random() - 0.5) * self.shake * 14

        cx = -self.cam_x + shake_x
        cy = -self.cam_y + shake_y

        # Пол + сетка
        screen_x0 = int(self.cam_x // CELL)
        screen_y0 = int(self.cam_y // CELL)
        screen_x1 = int((self.cam_x + W) // CELL) + 1
        screen_y1 = int((self.cam_y + H) // CELL) + 1
        for y in range(max(0, screen_y0), min(ROWS, screen_y1 + 1)):
            for x in range(max(0, screen_x0), min(COLS, screen_x1 + 1)):
                c = MAP[y][x]
                px = x * CELL + cx
                py = y * CELL + cy
                if c == "#":
                    pygame.draw.rect(self.screen, COL_WALL,
                                     (px, py, CELL, CELL))
                    pygame.draw.rect(self.screen, COL_WALL_TOP,
                                     (px, py, CELL, 6))
                    # лампочки серверов
                    if (x * 7 + y * 13) % 4 == 0:
                        col = (40, 200, 100) if (x + y) % 2 == 0 else (200, 200, 60)
                        pygame.draw.rect(self.screen, col,
                                         (px + 8, py + 14, 4, 4))
                        pygame.draw.rect(self.screen, col,
                                         (px + 8, py + 24, 4, 4))
                else:
                    pygame.draw.rect(self.screen, COL_FLOOR,
                                     (px, py, CELL, CELL))
                    pygame.draw.rect(self.screen, COL_FLOOR_GRID,
                                     (px, py, CELL, CELL), 1)

        # Терминалы
        for term in self.terminals:
            self.draw_terminal(term, cx, cy)

        # Камеры
        for cam in self.cameras:
            self.draw_camera(cam, cx, cy)

        # Дверь шлюза
        if self.exit_door:
            ex, ey = self.exit_door
            open_door = self.terminals_done >= 5
            color = COL_GREEN if open_door else COL_RED_DIM
            pygame.draw.rect(self.screen, color,
                             (ex + cx - 22, ey + cy - 28, 44, 56))
            inner = COL_TERMINAL_ON if open_door else COL_TERMINAL_OFF
            pygame.draw.rect(self.screen, inner,
                             (ex + cx - 18, ey + cy - 24, 36, 48))
            label = self.font_small.render(
                "EXIT" if open_door else "LOCKED", True, COL_TEXT)
            self.screen.blit(label, (ex + cx - label.get_width() / 2,
                                     ey + cy - 6))

        # Конусы видимости камер (красные) - над полом, под BOT-ом
        for cam in self.cameras:
            self.draw_camera_cone(cam, cx, cy)

        # BOT
        self.draw_bot(cx, cy)

        # Игрок
        self.draw_player(cx, cy)

        # Конус фонаря (вырезает темноту)
        self.draw_darkness(cx, cy)

        # HUD
        self.draw_hud()

    def draw_terminal(self, term, cx, cy):
        x, y = term.x + cx, term.y + cy
        col = COL_TERMINAL_ON if term.done else COL_TERMINAL_OFF
        # стойка
        pygame.draw.rect(self.screen, (30, 36, 40),
                         (x - 16, y - 22, 32, 44))
        # экран
        pygame.draw.rect(self.screen, col, (x - 12, y - 18, 24, 18))
        # светящийся знак
        if term.done:
            t = self.font_small.render("OK", True, COL_GREEN)
        elif term.in_progress:
            blink = (math.sin(self.time * 8) > 0)
            t = self.font_small.render("...", True, COL_AMBER if blink else COL_TEXT_DIM)
        else:
            t = self.font_small.render("?", True, COL_RED)
        self.screen.blit(t, (x - t.get_width() / 2, y - 16))

        # маленький "корпус" внизу
        pygame.draw.rect(self.screen, (60, 70, 80),
                         (x - 14, y + 4, 28, 16))

    def draw_camera(self, cam, cx, cy):
        x, y = cam.x + cx, cam.y + cy
        col = COL_RED if cam.alerted else (140, 140, 150)
        # корпус
        pygame.draw.circle(self.screen, col, (int(x), int(y)), 6)
        # "глаз"
        ex = x + math.cos(cam.angle) * 8
        ey = y + math.sin(cam.angle) * 8
        pygame.draw.circle(self.screen, COL_RED if cam.alerted else (200, 60, 60),
                           (int(ex), int(ey)), 3)

    def draw_camera_cone(self, cam, cx, cy):
        # Конус видимости как полупрозрачный полигон
        x, y = cam.x + cx, cam.y + cy
        rng = cam.range
        col = (220, 30, 30, 50) if cam.alerted else (180, 30, 30, 25)
        surf = pygame.Surface((W, H), pygame.SRCALPHA)
        steps = 16
        pts = [(x, y)]
        for i in range(steps + 1):
            a = cam.angle - cam.fov + (i / steps) * cam.fov * 2
            dxr = math.cos(a)
            dyr = math.sin(a)
            d = 0
            while d < rng:
                wx = cam.x + dxr * d
                wy = cam.y + dyr * d
                if is_wall_px(wx, wy):
                    break
                d += 6
            pts.append((x + dxr * d, y + dyr * d))
        pygame.draw.polygon(surf, col, pts)
        self.screen.blit(surf, (0, 0))

    def draw_bot(self, cx, cy):
        b = self.bot
        bx, by = b.x + cx, b.y + cy
        # тень
        shadow = pygame.Surface((b.r * 3, int(b.r * 1.4)), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 100), shadow.get_rect())
        self.screen.blit(shadow, (bx - b.r * 1.5, by - 2))

        # тело - "глитч-силуэт": несколько смещённых копий разными цветами
        wob = math.sin(self.time * 6) * 1.5
        for off, col in [((2, 0), (180, 30, 200)), ((-2, 0), (50, 200, 180)), ((0, 0), (10, 10, 14))]:
            pygame.draw.circle(self.screen, col,
                               (int(bx + off[0]), int(by + off[1] + wob)), b.r)
        # цифровые "узлы" вокруг
        for i in range(6):
            a = self.time * 1.5 + i / 6 * math.tau
            ox = math.cos(a) * (b.r + 6)
            oy = math.sin(a) * (b.r + 6)
            pygame.draw.rect(self.screen, COL_GLITCH,
                             (bx + ox - 1, by + oy - 1, 2, 2))
        # глаза
        if b.state == "chase":
            pygame.draw.circle(self.screen, COL_RED, (int(bx - 4), int(by - 3)), 2)
            pygame.draw.circle(self.screen, COL_RED, (int(bx + 4), int(by - 3)), 2)
        else:
            pygame.draw.circle(self.screen, (200, 80, 80), (int(bx - 4), int(by - 3)), 1)
            pygame.draw.circle(self.screen, (200, 80, 80), (int(bx + 4), int(by - 3)), 1)
        # символ
        ch = "B" if b.state != "chase" else "X"
        t = self.font_small.render(ch, True, (255, 255, 255))
        self.screen.blit(t, (bx - t.get_width() / 2, by + 2))

    def draw_player(self, cx, cy):
        p = self.player
        px, py = p.x + cx, p.y + cy
        shadow = pygame.Surface((p.r * 3, int(p.r * 1.4)), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 110), shadow.get_rect())
        self.screen.blit(shadow, (px - p.r * 1.5, py - 2))
        # тело
        pygame.draw.circle(self.screen, (90, 130, 110),
                           (int(px), int(py)), p.r)
        # голова
        hx = px + math.cos(p.facing) * 4
        hy = py + math.sin(p.facing) * 4 - 2
        pygame.draw.circle(self.screen, (180, 200, 170),
                           (int(hx), int(hy)), int(p.r * 0.55))
        # фонарь
        if p.light_on:
            fx = px + math.cos(p.facing) * 12
            fy = py + math.sin(p.facing) * 12
            pygame.draw.circle(self.screen, COL_AMBER, (int(fx), int(fy)), 3)

    def draw_darkness(self, cx, cy):
        # Тёмная маска со светом фонаря и небольшим ореолом вокруг игрока
        p = self.player
        px, py = p.x + cx, p.y + cy
        dark = pygame.Surface((W, H), pygame.SRCALPHA)
        dark.fill((0, 0, 0, 215))

        # Cut-out: ambient halo
        ambient_r = 80
        for r in range(ambient_r, 0, -8):
            alpha = int(220 * (r / ambient_r))
            pygame.draw.circle(dark, (0, 0, 0, alpha),
                               (int(px), int(py)), r,
                               special_flags=0)
        # subtract via blend
        cut = pygame.Surface((ambient_r * 2, ambient_r * 2), pygame.SRCALPHA)
        for r in range(ambient_r, 0, -4):
            a = int(220 * (r / ambient_r))
            pygame.draw.circle(cut, (0, 0, 0, a), (ambient_r, ambient_r), r)
        dark.blit(cut, (px - ambient_r, py - ambient_r),
                  special_flags=pygame.BLEND_RGBA_SUB)

        # Cut-out: flashlight cone
        if p.light_on:
            rng = 320
            ang = p.facing
            half = 0.45
            steps = 24
            pts = [(px, py)]
            for i in range(steps + 1):
                a = ang - half + (i / steps) * half * 2
                dxr = math.cos(a)
                dyr = math.sin(a)
                d = 0
                stepl = 6
                while d < rng:
                    wx = p.x + dxr * d
                    wy = p.y + dyr * d
                    if is_wall_px(wx, wy):
                        break
                    d += stepl
                pts.append((px + dxr * d, py + dyr * d))
            cone = pygame.Surface((W, H), pygame.SRCALPHA)
            pygame.draw.polygon(cone, (0, 0, 0, 230), pts)
            # Сделаем градиент через мягкий blur-аналог: несколько полигонов меньше с большей альфой
            dark.blit(cone, (0, 0), special_flags=pygame.BLEND_RGBA_SUB)
            # Теплый оттенок света
            warm = pygame.Surface((W, H), pygame.SRCALPHA)
            for shrink, col in [(0, (255, 220, 140, 35)),
                                (8, (255, 200, 100, 30))]:
                shrunk_pts = []
                for pt in pts:
                    pdx = pt[0] - px
                    pdy = pt[1] - py
                    ll = math.hypot(pdx, pdy)
                    if ll > shrink:
                        shrunk_pts.append((pt[0] - pdx / ll * shrink,
                                           pt[1] - pdy / ll * shrink))
                    else:
                        shrunk_pts.append(pt)
                pygame.draw.polygon(warm, col, shrunk_pts)
            self.screen.blit(warm, (0, 0),
                             special_flags=pygame.BLEND_RGB_ADD)

        # BOT в темноте - тёмно-фиолетовое сияние, видно издалека
        b = self.bot
        bd = dist(p.x, p.y, b.x, b.y)
        if bd < 600 and line_of_sight(p.x, p.y, b.x, b.y):
            bx, by = b.x + cx, b.y + cy
            glow = pygame.Surface((100, 100), pygame.SRCALPHA)
            for r in range(50, 0, -4):
                a = int(60 * (1 - r / 50))
                pygame.draw.circle(glow, (180, 30, 200, a), (50, 50), r)
            dark.blit(glow, (bx - 50, by - 50),
                      special_flags=pygame.BLEND_RGBA_SUB)

        self.screen.blit(dark, (0, 0))

    def apply_screen_glitch(self, amount):
        # Сдвиг горизонтальных полос
        if amount < 0.15:
            return
        try:
            screen_copy = self.screen.copy()
            for _ in range(int(amount * 8)):
                y = random.randint(0, H - 12)
                h = random.randint(2, 10)
                dx = random.randint(-int(20 * amount), int(20 * amount))
                slice_rect = pygame.Rect(0, y, W, h)
                slice_surf = screen_copy.subsurface(slice_rect).copy()
                self.screen.blit(slice_surf, (dx, y))
            # Цветовой сдвиг (RGB split)
            if amount > 0.4:
                tint = pygame.Surface((W, H), pygame.SRCALPHA)
                tint.fill((int(40 * amount), 0, int(40 * amount), 80))
                self.screen.blit(tint, (int(amount * 4), 0),
                                 special_flags=pygame.BLEND_RGB_ADD)
        except Exception:
            pass

    def draw_hud(self):
        # Полоски сверху-слева
        pad = pygame.Surface((250, 84), pygame.SRCALPHA)
        pad.fill((0, 0, 0, 140))
        self.screen.blit(pad, (10, 10))

        def bar(y, label, val, col):
            t = self.font_small.render(label, True, COL_TEXT_DIM)
            self.screen.blit(t, (18, y))
            pygame.draw.rect(self.screen, (30, 30, 30),
                             (90, y + 2, 150, 10))
            pygame.draw.rect(self.screen, col,
                             (90, y + 2, int(150 * val / 100), 10))

        bar(16, "БАТАРЕЯ", self.player.battery, COL_AMBER)
        bar(32, "ШУМ",
            min(100, self.player.noise * 100),
            COL_RED if self.player.noise > 0.6 else COL_BLUE)
        bar(48, "БОТ",
            min(100, self.glitch_amount * 100),
            COL_GLITCH)

        st = self.font_small.render(f"BOT.state = {self.bot.state}",
                                    True, COL_TEXT_DIM)
        self.screen.blit(st, (18, 66))

        # Терминалы справа сверху
        right_pad = pygame.Surface((220, 50), pygame.SRCALPHA)
        right_pad.fill((0, 0, 0, 140))
        self.screen.blit(right_pad, (W - 230, 10))
        title = self.font.render(
            f"ТЕРМИНАЛЫ {self.terminals_done}/5", True, COL_GREEN)
        self.screen.blit(title, (W - 220, 16))
        for i in range(5):
            col = COL_GREEN if i < self.terminals_done else COL_TERMINAL_OFF
            pygame.draw.rect(self.screen, col,
                             (W - 220 + i * 32, 40, 26, 10))

        # Сообщение в центре
        if self.message:
            txt = self.font.render(self.message, True, COL_AMBER)
            rect = txt.get_rect(center=(W // 2, H - 60))
            pad = pygame.Surface((rect.width + 24, rect.height + 12),
                                 pygame.SRCALPHA)
            pad.fill((0, 0, 0, 200))
            self.screen.blit(pad, (rect.x - 12, rect.y - 6))
            self.screen.blit(txt, rect)

        # Hacking UI
        if self.active_terminal:
            self.draw_hack_ui()

        # Лог справа внизу
        if self.boot_log:
            y0 = H - 30 - len(self.boot_log) * 16
            for i, (line, t) in enumerate(self.boot_log[-5:]):
                col = COL_GREEN_DIM
                txt = self.font_small.render(line, True, col)
                self.screen.blit(txt, (12, y0 + i * 16))

    def draw_hack_ui(self):
        box_w = 460
        box_h = 120
        x = (W - box_w) // 2
        y = H // 2 - box_h // 2 - 40
        pad = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
        pad.fill((0, 0, 0, 210))
        pygame.draw.rect(pad, COL_GREEN, pad.get_rect(), 2)
        self.screen.blit(pad, (x, y))

        title = self.font.render("> TERMINAL HACK <", True, COL_GREEN)
        self.screen.blit(title, (x + (box_w - title.get_width()) // 2, y + 8))

        # Цель
        target = self.font_mono.render(self.hack_target, True, COL_TEXT_DIM)
        # Набранное (зелёное поверх)
        typed = self.font_mono.render(self.hack_typed, True, COL_GREEN)
        tx = x + (box_w - target.get_width()) // 2
        self.screen.blit(target, (tx, y + 40))
        self.screen.blit(typed, (tx, y + 40))

        # Таймер
        t_w = int((box_w - 40) * max(0, self.hack_timer / 12))
        pygame.draw.rect(self.screen, (40, 40, 40), (x + 20, y + 90, box_w - 40, 6))
        pygame.draw.rect(self.screen, COL_AMBER, (x + 20, y + 90, t_w, 6))

        hint = self.font_small.render(
            "Набирай по буквам. ESC - отмена. Каждое нажатие = шум.",
            True, COL_TEXT_DIM)
        self.screen.blit(hint, (x + (box_w - hint.get_width()) // 2, y + 102))

    # =================================================================
    # Главный цикл
    # =================================================================
    def run(self):
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000.0
            if dt > 0.1:
                dt = 0.1

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        if self.scene == "play" and self.active_terminal:
                            self.cancel_hack()
                        else:
                            running = False
                    elif self.scene == "menu":
                        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                            self.scene = "play"
                            self.show_message("Найди 5 терминалов и сбеги.", 4)
                    elif self.scene in ("dead", "win"):
                        if event.key == pygame.K_r:
                            self.init_game()
                            self.scene = "play"
                            self.show_message("Найди 5 терминалов и сбеги.", 4)
                    elif self.scene == "play":
                        if self.active_terminal:
                            # буква по букве
                            if event.unicode and event.unicode.upper().isalnum():
                                self.hack_input(event.unicode.upper())
                        else:
                            if event.key == pygame.K_f:
                                if self.player.battery > 0:
                                    self.player.light_on = not self.player.light_on
                            elif event.key in (pygame.K_e, pygame.K_SPACE):
                                # взаимодействие
                                self.try_interact()

            self.update(dt)
            self.render()
            pygame.display.flip()

            if self.scene == "play":
                if self.dead and self.shake <= 0 and self.flash <= 0:
                    self.scene = "dead"
                elif self.win:
                    # маленькая задержка для звука двери
                    self.scene = "win"

        pygame.quit()

    def try_interact(self):
        p = self.player
        best = None
        best_d = 50
        for t in self.terminals:
            if t.done:
                continue
            d = dist(p.x, p.y, t.x, t.y)
            if d < best_d:
                best_d = d
                best = t
        if best:
            self.start_hack(best)
        else:
            if self.exit_door and dist(p.x, p.y, *self.exit_door) < 50:
                if self.terminals_done >= 5:
                    self.trigger_win()
                else:
                    self.show_message(
                        f"Шлюз закрыт. Перезагружено {self.terminals_done}/5", 3)
            else:
                self.show_message("Здесь ничего нет.", 1.5)


# =====================================================================
def main():
    random.seed()
    Game().run()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pygame.quit()
        sys.exit(0)
