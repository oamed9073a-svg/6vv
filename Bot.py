"""Bot.py - терминальный PC-хоррор на чистом Python stdlib (curses).

Ты ночной техник в дата-центре. ИИ "BOT" живёт в сети объекта и охотится
через коридоры серверных стоек. Перезагрузи 5 терминалов, чтобы открылся
шлюз, и сбеги.

ЗАПУСК:
    python Bot.py

ТРЕБОВАНИЯ:
    - терминал минимум 80x24
    - на Windows может потребоваться `pip install windows-curses`
    - никаких других зависимостей не нужно

УПРАВЛЕНИЕ:
    w / a / s / d  или стрелки   - шаг (1 клетка)
    W / A / S / D  (Shift+wasd)  - быстрый шаг (2 клетки, громче)
    c                            - переключить "красться" (тише, реже шаги)
    f                            - фонарь ВКЛ/ВЫКЛ
    e / Space                    - взаимодействие / взлом терминала
    q / Esc                      - выход

В мини-игре взлома набирай показанный код по буквам.
Esc прерывает взлом.

ПОДСКАЗКИ:
    - Камеры красным конусом сканируют коридоры. Попадёшься - BOT идёт
      на твою позицию.
    - Бег = много шума. Красться = почти тихо. Фонарь = тоже шум.
    - Когда BOT рядом - экран начинает глючить, символы заменяются мусором.
    - Свети фонарём BOT-у в лицо - на секунду он зависнет.
"""

from __future__ import annotations

import curses
import math
import os
import random
import sys
import time


# =====================================================================
# Карта (используем символы #..STBD)
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


def cell_at(x, y):
    if 0 <= x < COLS and 0 <= y < ROWS:
        return MAP[y][x]
    return "#"


def is_wall(x, y):
    return cell_at(x, y) == "#"


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def los(ax, ay, bx, by):
    """Линия видимости по клеточной сетке (Bresenham). True если нет стен между."""
    dx = abs(bx - ax)
    dy = abs(by - ay)
    sx = 1 if ax < bx else -1
    sy = 1 if ay < by else -1
    err = dx - dy
    x, y = ax, ay
    while (x, y) != (bx, by):
        e2 = err * 2
        if e2 > -dy:
            err -= dy
            x += sx
        if e2 < dx:
            err += dx
            y += sy
        if (x, y) == (bx, by):
            break
        if is_wall(x, y):
            return False
    return True


def bfs(sx, sy, tx, ty):
    if (sx, sy) == (tx, ty):
        return []
    if is_wall(tx, ty):
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
        if (cx, cy) == (tx, ty):
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
    cur = (tx, ty)
    while cur != (sx, sy):
        path.append(cur)
        p = prev[cur[1]][cur[0]]
        if p is None:
            break
        cur = p
    path.reverse()
    return path


def random_floor():
    for _ in range(200):
        x = random.randint(1, COLS - 2)
        y = random.randint(1, ROWS - 2)
        if not is_wall(x, y):
            return (x, y)
    return (1, 1)


# =====================================================================
# Сущности
# =====================================================================
class Player:
    def __init__(self, x, y):
        self.x, self.y = x, y
        self.fdx, self.fdy = 1, 0  # facing
        self.battery = 100.0
        self.light_on = True
        self.sneaking = False
        self.noise = 0.0
        self.alive = True
        self.move_cooldown = 0.0


class Terminal:
    def __init__(self, x, y):
        self.x, self.y = x, y
        self.done = False
        self.in_progress = False


class Camera:
    def __init__(self, x, y, base_angle):
        self.x, self.y = x, y
        self.base_angle = base_angle
        self.angle = base_angle
        self.sweep = random.random() * math.tau
        self.range = 9
        self.fov = 0.6
        self.alerted = False
        self.alert_t = 0.0

    def update(self, dt):
        self.sweep += dt * 0.9
        self.angle = self.base_angle + math.sin(self.sweep) * 0.7
        if self.alert_t > 0:
            self.alert_t -= dt
            if self.alert_t <= 0:
                self.alerted = False

    def sees(self, px, py):
        d = math.hypot(px - self.x, py - self.y)
        if d > self.range:
            return False
        ang = math.atan2(py - self.y, px - self.x)
        diff = abs(((ang - self.angle + math.pi * 3) % (math.pi * 2)) - math.pi)
        if diff > self.fov:
            return False
        return los(int(self.x), int(self.y), int(px), int(py))

    def cone_cells(self):
        """Список клеток в конусе видимости (для отрисовки)."""
        cells = []
        for r in range(1, self.range + 1):
            steps = max(3, int(r * self.fov * 4))
            for i in range(-steps, steps + 1):
                a = self.angle + (i / max(1, steps)) * self.fov
                cx = int(round(self.x + math.cos(a) * r))
                cy = int(round(self.y + math.sin(a) * r))
                if 0 <= cx < COLS and 0 <= cy < ROWS:
                    if not is_wall(cx, cy) and los(int(self.x), int(self.y), cx, cy):
                        cells.append((cx, cy))
        return cells


class Bot:
    def __init__(self, x, y):
        self.x, self.y = x, y
        self.state = "patrol"  # patrol | investigate | chase
        self.target = None
        self.path = []
        self.path_t = 0.0
        self.patrol_t = 0.0
        self.stunned = 0.0
        self.move_cd = 0.0
        self.move_interval = 0.18  # секунд на 1 клетку (chase = быстрее)
        self.glyph_cycle = 0

    def update(self, dt, player, game):
        self.glyph_cycle = (self.glyph_cycle + 1) % 4
        if self.stunned > 0:
            self.stunned -= dt
            return

        d = math.hypot(player.x - self.x, player.y - self.y)

        # Детекция
        detected = False
        # Зрение по прямой
        if d <= 14 and los(self.x, self.y, player.x, player.y):
            if d <= 3:
                detected = True
            else:
                # учитываем направление BOT-а (если есть путь)
                if self.path:
                    px_dx = self.path[0][0] - self.x
                    px_dy = self.path[0][1] - self.y
                    face_a = math.atan2(px_dy, px_dx) if (px_dx or px_dy) else 0
                    ang = math.atan2(player.y - self.y, player.x - self.x)
                    diff = abs(((ang - face_a + math.pi * 3) % (math.pi * 2)) - math.pi)
                    if diff < 1.2:
                        detected = True
                else:
                    detected = True
        # Слух
        hear_r = 1.5 + player.noise * 9
        if d <= hear_r and los(self.x, self.y, player.x, player.y):
            detected = True
        # Через камеры
        for cam in game.cameras:
            if cam.alerted and self.state != "chase":
                self.target = (player.x, player.y)
                self.state = "investigate"
                self.path = []

        if detected:
            was = self.state
            self.state = "chase"
            self.target = (player.x, player.y)
            if was != "chase":
                game.glitch_event("> SIGNAL_ACQUIRED")
            self.path = []

        elif self.state == "chase":
            if self.target and (self.x, self.y) == self.target:
                self.state = "investigate"
                self.target = None
                self.patrol_t = 0

        if self.state in ("patrol", "investigate"):
            self.patrol_t -= dt
            if self.target is None or self.patrol_t <= 0:
                self.target = random_floor()
                self.path = []
                self.patrol_t = 6 + random.random() * 4

        # Пересчёт пути
        self.path_t -= dt
        if self.target and (not self.path or self.path_t <= 0):
            self.path = bfs(self.x, self.y, self.target[0], self.target[1])
            self.path_t = 0.4

        # Шаг
        self.move_cd -= dt
        if self.path and self.move_cd <= 0:
            nx, ny = self.path[0]
            if not is_wall(nx, ny):
                self.x, self.y = nx, ny
            self.path.pop(0)
            self.move_cd = (0.12 if self.state == "chase" else 0.22)

        # Свет фонаря в лицо -> стан
        if player.light_on:
            face_a = math.atan2(player.fdy, player.fdx)
            ang = math.atan2(self.y - player.y, self.x - player.x)
            diff = abs(((ang - face_a + math.pi * 3) % (math.pi * 2)) - math.pi)
            if diff < 0.5 and d < 12 and los(player.x, player.y, self.x, self.y):
                self.stunned = max(self.stunned, 0.5)
                game.glitch_event("> BOT.stalled")


# =====================================================================
# Игра
# =====================================================================
class Game:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.has_color = curses.has_colors()
        if self.has_color:
            curses.start_color()
            curses.use_default_colors()
            try:
                self._init_colors()
            except Exception:
                self.has_color = False
        stdscr.nodelay(True)
        stdscr.keypad(True)
        curses.curs_set(0)
        try:
            curses.cbreak()
            curses.noecho()
        except Exception:
            pass

        self.scene = "menu"
        self.menu_t = 0.0
        self.boot_messages = [
            "BOOT> kernel modules loaded",
            "BOOT> network: 192.168.0.13 ASSIGNED",
            "BOOT> camera array: ONLINE (5 nodes)",
            "BOOT> autonomous unit BOT.py: SPAWNED",
            "BOOT> WARNING: emergency shutdown required",
            "BOOT> 5 terminals must be rebooted",
            "BOOT> good luck, technician.",
        ]
        self.boot_revealed = 0
        self.last_boot_t = 0
        self.death_reason = ""
        self.init_game()

    # -------- colors --------
    P_WALL = 1
    P_FLOOR = 2
    P_PLAYER = 3
    P_BOT = 4
    P_TERM_OFF = 5
    P_TERM_ON = 6
    P_DOOR_LOCKED = 7
    P_DOOR_OPEN = 8
    P_CAM = 9
    P_CAM_ALERT = 10
    P_CONE = 11
    P_CONE_ALERT = 12
    P_LIGHT = 13
    P_UI_DIM = 14
    P_UI_AMBER = 15
    P_UI_RED = 16
    P_GLITCH = 17

    def _init_colors(self):
        curses.init_pair(self.P_WALL, curses.COLOR_BLACK, -1)
        curses.init_pair(self.P_FLOOR, 8, -1)  # bright black if supported
        curses.init_pair(self.P_PLAYER, curses.COLOR_WHITE, -1)
        curses.init_pair(self.P_BOT, curses.COLOR_MAGENTA, -1)
        curses.init_pair(self.P_TERM_OFF, curses.COLOR_RED, -1)
        curses.init_pair(self.P_TERM_ON, curses.COLOR_GREEN, -1)
        curses.init_pair(self.P_DOOR_LOCKED, curses.COLOR_RED, -1)
        curses.init_pair(self.P_DOOR_OPEN, curses.COLOR_GREEN, -1)
        curses.init_pair(self.P_CAM, curses.COLOR_CYAN, -1)
        curses.init_pair(self.P_CAM_ALERT, curses.COLOR_RED, -1)
        curses.init_pair(self.P_CONE, -1, -1)
        curses.init_pair(self.P_CONE_ALERT, curses.COLOR_RED, -1)
        curses.init_pair(self.P_LIGHT, curses.COLOR_YELLOW, -1)
        curses.init_pair(self.P_UI_DIM, 8, -1)
        curses.init_pair(self.P_UI_AMBER, curses.COLOR_YELLOW, -1)
        curses.init_pair(self.P_UI_RED, curses.COLOR_RED, -1)
        curses.init_pair(self.P_GLITCH, curses.COLOR_MAGENTA, -1)

    def attr(self, pair, *flags):
        a = 0
        if self.has_color:
            try:
                a = curses.color_pair(pair)
            except Exception:
                a = 0
        for f in flags:
            a |= f
        return a

    # -------- init --------
    def init_game(self):
        self.player = None
        self.bot = None
        self.terminals = []
        self.cameras = []
        spawn = (1, 1)
        bot_spawn = (COLS - 2, ROWS - 2)
        self.exit_door = None

        for y in range(ROWS):
            for x in range(COLS):
                c = MAP[y][x]
                if c == "S":
                    spawn = (x, y)
                elif c == "B":
                    bot_spawn = (x, y)
                elif c == "T":
                    self.terminals.append(Terminal(x, y))
                elif c == "D":
                    self.exit_door = (x, y)

        self.cameras = [
            Camera(12, 2, math.pi * 0.75),
            Camera(20, 5, math.pi),
            Camera(6, 14, 0.0),
            Camera(18, 16, math.pi * 1.25),
            Camera(11, 18, math.pi * 0.25),
        ]

        self.player = Player(*spawn)
        self.bot = Bot(*bot_spawn)
        self.terminals_done = 0
        self.win = False
        self.dead = False
        self.shake = 0.0
        self.glitch_amount = 0.0
        self.cam_x = 0
        self.cam_y = 0
        self.time = 0.0
        self.message = ""
        self.message_t = 0.0
        self.boot_log = []
        self.active_term = None
        self.hack_target = ""
        self.hack_typed = ""
        self.hack_t = 0.0
        self.tick = 0
        self.flash_t = 0.0
        self.last_render_buf = None

    def boot_log_push(self, line):
        self.boot_log.append(line)
        if len(self.boot_log) > 6:
            self.boot_log.pop(0)

    def show_message(self, text, duration=3.0):
        self.message = text
        self.message_t = duration

    def glitch_event(self, line=None):
        self.glitch_amount = min(1.0, self.glitch_amount + 0.4)
        if line:
            self.boot_log_push(line)

    # -------- hacking minigame --------
    def start_hack(self, term):
        self.active_term = term
        term.in_progress = True
        chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        self.hack_target = "".join(random.choice(chars) for _ in range(6))
        self.hack_typed = ""
        self.hack_t = 14.0
        self.show_message(f"взлом - набери: {self.hack_target}", 14)

    def hack_input(self, ch):
        if not self.active_term:
            return
        idx = len(self.hack_typed)
        if idx < len(self.hack_target):
            if ch == self.hack_target[idx]:
                self.hack_typed += ch
                self.player.noise = max(self.player.noise, 0.45)
                if self.hack_typed == self.hack_target:
                    self.complete_hack()
            else:
                self.hack_typed = ""
                self.glitch_event()

    def cancel_hack(self):
        if self.active_term:
            self.active_term.in_progress = False
            self.active_term = None
            self.show_message("взлом прерван", 2)

    def complete_hack(self):
        term = self.active_term
        if not term:
            return
        term.done = True
        term.in_progress = False
        self.active_term = None
        self.terminals_done += 1
        self.show_message(f"ТЕРМИНАЛ {self.terminals_done}/5 ПЕРЕЗАГРУЖЕН", 3)
        self.boot_log_push(f"TERMINAL {self.terminals_done}/5: RESTART OK")
        if self.terminals_done >= 3:
            self.bot.state = "investigate"
            self.bot.target = (self.player.x, self.player.y)
        if self.terminals_done >= 5:
            self.boot_log_push("GATEWAY DOOR: UNLOCKED")
            self.show_message("ШЛЮЗ ОТКРЫТ. БЕГИ К ВЫХОДУ!", 5)

    # -------- input --------
    def handle_input(self, dt):
        try:
            ch = self.stdscr.getch()
        except Exception:
            ch = -1
        if ch == -1:
            return False
        # Drain extra queued keys
        extras = []
        for _ in range(6):
            try:
                c2 = self.stdscr.getch()
            except Exception:
                c2 = -1
            if c2 == -1:
                break
            extras.append(c2)

        all_keys = [ch] + extras
        if self.scene == "menu":
            for c in all_keys:
                if c in (27, ord("q"), ord("Q")):
                    return True
                if c in (10, 13, ord(" "), curses.KEY_ENTER):
                    self.scene = "play"
                    self.show_message("Найди 5 терминалов и сбеги.", 4)
                    return False
            return False

        if self.scene in ("dead", "win"):
            for c in all_keys:
                if c in (27, ord("q"), ord("Q")):
                    return True
                if c in (ord("r"), ord("R")):
                    self.init_game()
                    self.scene = "play"
                    self.show_message("Найди 5 терминалов и сбеги.", 4)
                    return False
            return False

        # play
        for c in all_keys:
            if c == -1:
                continue
            if c == 27:  # ESC
                if self.active_term:
                    self.cancel_hack()
                else:
                    return True
            elif c in (ord("q"), ord("Q")):
                return True
            elif self.active_term:
                # Hack mode: только буквы/цифры
                if 32 <= c < 127:
                    self.hack_input(chr(c).upper())
            else:
                self.handle_play_key(c, dt)
        return False

    def handle_play_key(self, c, dt):
        p = self.player
        moved = False
        run = False
        dx, dy = 0, 0
        # Стрелки
        if c == curses.KEY_UP:
            dy = -1
        elif c == curses.KEY_DOWN:
            dy = 1
        elif c == curses.KEY_LEFT:
            dx = -1
        elif c == curses.KEY_RIGHT:
            dx = 1
        elif c == ord("w"):
            dy = -1
        elif c == ord("s"):
            dy = 1
        elif c == ord("a"):
            dx = -1
        elif c == ord("d"):
            dx = 1
        elif c == ord("W"):
            dy = -1; run = True
        elif c == ord("S"):
            dy = 1; run = True
        elif c == ord("A"):
            dx = -1; run = True
        elif c == ord("D"):
            dx = 1; run = True
        elif c in (ord("f"), ord("F")):
            if p.battery > 0:
                p.light_on = not p.light_on
                self.show_message("фонарь ВКЛ" if p.light_on else "фонарь ВЫКЛ", 1.2)
            return
        elif c in (ord("c"), ord("C")):
            p.sneaking = not p.sneaking
            self.show_message("режим: красться" if p.sneaking else "режим: ходьба", 1.2)
            return
        elif c in (ord("e"), ord("E"), ord(" ")):
            self.try_interact()
            return

        if dx == 0 and dy == 0:
            return

        steps = 2 if run else 1
        for _ in range(steps):
            nx, ny = p.x + dx, p.y + dy
            if 0 <= nx < COLS and 0 <= ny < ROWS and not is_wall(nx, ny):
                p.x, p.y = nx, ny
                p.fdx, p.fdy = dx, dy
                moved = True
            else:
                break
        if moved:
            if run:
                p.noise = max(p.noise, 1.0)
            elif p.sneaking:
                p.noise = max(p.noise, 0.1)
            else:
                p.noise = max(p.noise, 0.4)

    def try_interact(self):
        p = self.player
        # Терминалы рядом
        for t in self.terminals:
            if t.done:
                continue
            if abs(t.x - p.x) <= 1 and abs(t.y - p.y) <= 1:
                self.start_hack(t)
                return
        # Дверь
        if self.exit_door:
            ex, ey = self.exit_door
            if abs(ex - p.x) <= 1 and abs(ey - p.y) <= 1:
                if self.terminals_done >= 5:
                    self.trigger_win()
                else:
                    self.show_message(
                        f"Шлюз закрыт. {self.terminals_done}/5 терминалов",
                        2.5)
                return
        self.show_message("здесь ничего нет", 1.2)

    # -------- update --------
    def update(self, dt):
        if self.scene == "menu":
            self.menu_t += dt
            now = time.time()
            if (self.boot_revealed < len(self.boot_messages)
                    and now - self.last_boot_t > 0.4):
                self.boot_log_push(self.boot_messages[self.boot_revealed])
                self.boot_revealed += 1
                self.last_boot_t = now
            return

        if self.scene != "play":
            return
        if self.dead or self.win:
            return

        self.time += dt
        self.tick += 1
        p = self.player

        p.noise *= math.pow(0.25, dt)

        if self.active_term:
            self.hack_t -= dt
            if self.hack_t <= 0:
                self.cancel_hack()

        if p.light_on and p.battery > 0:
            p.battery = max(0, p.battery - dt * 1.0)
            if p.battery == 0:
                p.light_on = False
                self.show_message("Батарея фонаря разряжена!", 2.5)
            p.noise = max(p.noise, 0.07)

        # Камеры
        for cam in self.cameras:
            cam.update(dt)
            if cam.sees(p.x, p.y):
                # фонарь засветит ярче и не-красться - сразу тревога
                if p.light_on or not p.sneaking:
                    cam.alerted = True
                    cam.alert_t = 4.0
                    p.noise = max(p.noise, 0.3)

        # BOT
        self.bot.update(dt, p, self)
        d_bot = math.hypot(p.x - self.bot.x, p.y - self.bot.y)

        # Глитч
        target_g = 0.0
        if d_bot <= 14 and los(p.x, p.y, self.bot.x, self.bot.y):
            target_g = clamp(1 - d_bot / 14, 0, 1)
        elif d_bot <= 8:
            target_g = clamp(1 - d_bot / 8, 0, 0.6) * 0.5
        if self.bot.state == "chase":
            target_g = max(target_g, 0.45)
        self.glitch_amount = self.glitch_amount * 0.85 + target_g * 0.15

        # Поимка
        if d_bot < 1.2:
            self.trigger_death("BOT.py получил контроль")

        if self.message_t > 0:
            self.message_t -= dt
            if self.message_t <= 0:
                self.message = ""
        if self.shake > 0:
            self.shake -= dt
        if self.flash_t > 0:
            self.flash_t -= dt

        # Выход через шлюз
        if self.exit_door and self.terminals_done >= 5:
            ex, ey = self.exit_door
            if abs(ex - p.x) <= 1 and abs(ey - p.y) <= 1:
                self.trigger_win()

    def trigger_death(self, reason):
        if self.dead:
            return
        self.dead = True
        self.death_reason = reason
        self.flash_t = 0.6
        self.shake = 0.6
        # Звуковой сигнал
        try:
            sys.stdout.write("\a")
            sys.stdout.flush()
        except Exception:
            pass

    def trigger_win(self):
        if self.win:
            return
        self.win = True

    # -------- rendering --------
    def render(self):
        self.stdscr.erase()
        try:
            self.maxy, self.maxx = self.stdscr.getmaxyx()
        except Exception:
            self.maxy, self.maxx = 24, 80

        if self.scene == "menu":
            self.render_menu()
        elif self.scene == "play":
            self.render_play()
        elif self.scene == "dead":
            self.render_dead()
        elif self.scene == "win":
            self.render_win()

        try:
            self.stdscr.refresh()
        except Exception:
            pass

    def safe_addstr(self, y, x, s, attr=0):
        try:
            if 0 <= y < self.maxy and 0 <= x < self.maxx:
                if x + len(s) > self.maxx:
                    s = s[: self.maxx - x]
                self.stdscr.addstr(y, x, s, attr)
        except Exception:
            pass

    def safe_addch(self, y, x, ch, attr=0):
        try:
            if 0 <= y < self.maxy - 1 and 0 <= x < self.maxx - 1:
                self.stdscr.addstr(y, x, ch, attr)
        except Exception:
            pass

    def render_menu(self):
        title = " Bot.py "
        sub = "> a horror in five terminals <"
        ty = max(2, self.maxy // 2 - 8)
        self.safe_addstr(ty, (self.maxx - len(title)) // 2, title,
                         self.attr(self.P_TERM_ON, curses.A_BOLD))
        self.safe_addstr(ty + 1, (self.maxx - len(sub)) // 2, sub,
                         self.attr(self.P_UI_DIM))
        for i, line in enumerate(self.boot_log):
            self.safe_addstr(ty + 4 + i, max(2, self.maxx // 2 - 25), line,
                             self.attr(self.P_TERM_ON))
        if self.boot_revealed >= len(self.boot_messages):
            if int(time.time() * 2) % 2 == 0:
                hint = "ENTER - войти    Q - выход"
                self.safe_addstr(self.maxy - 3,
                                 (self.maxx - len(hint)) // 2, hint,
                                 self.attr(self.P_UI_AMBER, curses.A_BOLD))
        ctrls = "wasd - движение   WASD - бег   c - красться   f - фонарь   e/space - терминал"
        self.safe_addstr(self.maxy - 1, max(0, (self.maxx - len(ctrls)) // 2),
                         ctrls, self.attr(self.P_UI_DIM))

    def render_dead(self):
        title = "CONNECTION LOST"
        self.safe_addstr(self.maxy // 2 - 4, (self.maxx - len(title)) // 2,
                         title, self.attr(self.P_UI_RED, curses.A_BOLD))
        msg = f"Терминалов перезагружено: {self.terminals_done}/5"
        self.safe_addstr(self.maxy // 2 - 1, (self.maxx - len(msg)) // 2, msg,
                         self.attr(self.P_PLAYER))
        reason = self.death_reason
        self.safe_addstr(self.maxy // 2, (self.maxx - len(reason)) // 2, reason,
                         self.attr(self.P_UI_DIM))
        if int(time.time() * 2) % 2 == 0:
            hint = "R - попробовать снова    Q - выход"
            self.safe_addstr(self.maxy - 2, (self.maxx - len(hint)) // 2,
                             hint, self.attr(self.P_UI_AMBER))

    def render_win(self):
        title = "EVACUATION COMPLETE"
        self.safe_addstr(self.maxy // 2 - 5, (self.maxx - len(title)) // 2,
                         title, self.attr(self.P_DOOR_OPEN, curses.A_BOLD))
        lines = [
            "Шлюз закрылся за спиной.",
            "Лифт со скрипом потащил тебя на поверхность.",
            "На мониторе - последняя строчка лога:",
            "",
            "  BOT> see you soon, technician.",
        ]
        for i, l in enumerate(lines):
            attr = self.attr(self.P_UI_AMBER, curses.A_BOLD) if i == 4 else \
                   self.attr(self.P_PLAYER)
            self.safe_addstr(self.maxy // 2 - 2 + i,
                             (self.maxx - len(l)) // 2, l, attr)
        if int(time.time() * 2) % 2 == 0:
            hint = "R - сыграть ещё    Q - выход"
            self.safe_addstr(self.maxy - 2, (self.maxx - len(hint)) // 2,
                             hint, self.attr(self.P_DOOR_OPEN))

    def render_play(self):
        p = self.player
        # viewport
        view_w = max(20, self.maxx - 22)
        view_h = max(15, self.maxy - 2)
        view_w = min(view_w, COLS)
        view_h = min(view_h, ROWS)
        # центр на игроке
        cx = clamp(p.x - view_w // 2, 0, max(0, COLS - view_w))
        cy = clamp(p.y - view_h // 2, 0, max(0, ROWS - view_h))

        # shake
        shake_dx = 0
        shake_dy = 0
        if self.shake > 0:
            shake_dx = random.randint(-1, 1)
            shake_dy = random.randint(-1, 1)

        # Видимость: список клеток в свете
        visible = self.compute_visible()

        # Конусы камер
        cam_cells = {}  # (x,y) -> alerted?
        for cam in self.cameras:
            for cc in cam.cone_cells():
                cam_cells[cc] = cam_cells.get(cc, False) or cam.alerted

        for sy in range(view_h):
            for sx in range(view_w):
                wx = cx + sx
                wy = cy + sy
                ch = MAP[wy][wx]
                vis = (wx, wy) in visible
                attr = 0
                rendered = " "

                if not vis:
                    # вне видимости - почти пусто
                    if ch == "#":
                        rendered = " "
                    else:
                        rendered = " "
                    attr = self.attr(self.P_WALL)
                else:
                    if ch == "#":
                        rendered = "#"
                        attr = self.attr(self.P_WALL, curses.A_DIM)
                    else:
                        rendered = "."
                        attr = self.attr(self.P_FLOOR, curses.A_DIM)

                # Конус камеры
                if vis and (wx, wy) in cam_cells:
                    alerted = cam_cells[(wx, wy)]
                    if ch != "#":
                        rendered = ":"
                        attr = self.attr(self.P_CAM_ALERT if alerted else self.P_CAM)

                # Терминалы
                for t in self.terminals:
                    if t.x == wx and t.y == wy and vis:
                        rendered = "T" if not t.done else "t"
                        attr = self.attr(
                            self.P_TERM_ON if t.done else self.P_TERM_OFF,
                            curses.A_BOLD)
                # Дверь
                if self.exit_door and self.exit_door == (wx, wy) and vis:
                    rendered = "D"
                    attr = self.attr(
                        self.P_DOOR_OPEN if self.terminals_done >= 5
                        else self.P_DOOR_LOCKED, curses.A_BOLD)

                # Камеры
                for cam in self.cameras:
                    if int(cam.x) == wx and int(cam.y) == wy and vis:
                        rendered = "o"
                        attr = self.attr(
                            self.P_CAM_ALERT if cam.alerted else self.P_CAM,
                            curses.A_BOLD)

                # BOT - может быть виден даже за пределами фонаря если очень близко
                if (self.bot.x == wx and self.bot.y == wy
                        and (vis or math.hypot(p.x - wx, p.y - wy) < 3)):
                    glyphs = "?&#%XR$@"
                    if self.bot.state == "chase":
                        rendered = "X"
                    else:
                        rendered = glyphs[self.bot.glyph_cycle % len(glyphs)]
                    attr = self.attr(self.P_BOT, curses.A_BOLD)

                # Игрок
                if p.x == wx and p.y == wy:
                    rendered = "@"
                    attr = self.attr(self.P_PLAYER, curses.A_BOLD)

                # Глитч - случайная замена символа
                if vis and self.glitch_amount > 0.2:
                    if random.random() < self.glitch_amount * 0.05:
                        rendered = random.choice("!@#$%&?*/+\\<>|=:;")
                        attr = self.attr(self.P_GLITCH, curses.A_BOLD)

                self.safe_addch(sy + shake_dy, sx + shake_dx, rendered, attr)

        # Глитч-сдвиг полос
        if self.glitch_amount > 0.5:
            self._glitch_lines(view_h, view_w)

        # Flash при поимке
        if self.flash_t > 0:
            self._flash_fill()

        # HUD
        self.render_hud(view_w)

        # Hack overlay
        if self.active_term:
            self.render_hack_overlay()

    def compute_visible(self):
        p = self.player
        visible = set()
        visible.add((p.x, p.y))
        # маленький ореол всегда
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                wx = p.x + dx
                wy = p.y + dy
                if 0 <= wx < COLS and 0 <= wy < ROWS:
                    if math.hypot(dx, dy) <= 2.2:
                        if los(p.x, p.y, wx, wy):
                            visible.add((wx, wy))
        if p.light_on:
            rng = 12
            half = 0.55
            face_a = math.atan2(p.fdy, p.fdx)
            for dy in range(-rng, rng + 1):
                for dx in range(-rng, rng + 1):
                    if dx == 0 and dy == 0:
                        continue
                    d = math.hypot(dx, dy)
                    if d > rng:
                        continue
                    ang = math.atan2(dy, dx)
                    diff = abs(((ang - face_a + math.pi * 3) % (math.pi * 2)) - math.pi)
                    if diff > half:
                        continue
                    wx = p.x + dx
                    wy = p.y + dy
                    if 0 <= wx < COLS and 0 <= wy < ROWS:
                        if los(p.x, p.y, wx, wy):
                            visible.add((wx, wy))
        return visible

    def _glitch_lines(self, view_h, view_w):
        # Не реализуем через перестановку clipping - просто перерисуем
        # случайные клетки случайными символами поверх.
        amount = self.glitch_amount
        for _ in range(int(amount * 12)):
            y = random.randint(0, view_h - 1)
            x = random.randint(0, view_w - 1)
            ch = random.choice("!@#$%^&*?/\\|=~;:.<>")
            self.safe_addch(y, x, ch,
                            self.attr(self.P_GLITCH, curses.A_BOLD))

    def _flash_fill(self):
        attr = self.attr(self.P_UI_RED, curses.A_REVERSE | curses.A_BOLD)
        for y in range(self.maxy - 1):
            self.safe_addstr(y, 0, " " * (self.maxx - 1), attr)

    def render_hud(self, view_w):
        # Правая колонка
        x0 = view_w + 1
        if x0 + 18 > self.maxx:
            return
        y = 0
        p = self.player

        self.safe_addstr(y, x0, "::: BOT.py :::",
                         self.attr(self.P_TERM_ON, curses.A_BOLD)); y += 2

        self.safe_addstr(y, x0, "BAT",
                         self.attr(self.P_UI_DIM))
        self._draw_bar(y, x0 + 5, 14, p.battery / 100,
                       self.attr(self.P_UI_AMBER)); y += 1
        self.safe_addstr(y, x0, "NSE",
                         self.attr(self.P_UI_DIM))
        self._draw_bar(y, x0 + 5, 14, min(1, p.noise),
                       self.attr(self.P_UI_RED if p.noise > 0.5
                                 else self.P_CAM)); y += 1
        self.safe_addstr(y, x0, "BOT",
                         self.attr(self.P_UI_DIM))
        self._draw_bar(y, x0 + 5, 14, self.glitch_amount,
                       self.attr(self.P_GLITCH)); y += 2

        st = f"state={self.bot.state}"
        self.safe_addstr(y, x0, st[:20], self.attr(self.P_UI_DIM)); y += 1
        light_s = "LIGHT: ON " if p.light_on else "LIGHT: off"
        sneak_s = "SNEAK: ON " if p.sneaking else "SNEAK: off"
        self.safe_addstr(y, x0, light_s, self.attr(
            self.P_LIGHT if p.light_on else self.P_UI_DIM)); y += 1
        self.safe_addstr(y, x0, sneak_s, self.attr(
            self.P_TERM_ON if p.sneaking else self.P_UI_DIM)); y += 2

        self.safe_addstr(y, x0,
                         f"TERMS {self.terminals_done}/5",
                         self.attr(self.P_TERM_ON, curses.A_BOLD)); y += 1
        slots = ""
        for i in range(5):
            slots += "[x]" if i < self.terminals_done else "[ ]"
        self.safe_addstr(y, x0, slots,
                         self.attr(self.P_TERM_ON)); y += 2

        # лог
        self.safe_addstr(y, x0, "log:", self.attr(self.P_UI_DIM)); y += 1
        for i, line in enumerate(self.boot_log[-5:]):
            if y + i >= self.maxy - 1:
                break
            line = line[:max(0, self.maxx - x0 - 1)]
            self.safe_addstr(y + i, x0, line,
                             self.attr(self.P_UI_DIM))

        # сообщение внизу
        if self.message:
            msg = " " + self.message + " "
            mx = max(0, (self.maxx - len(msg)) // 2)
            self.safe_addstr(self.maxy - 1, mx, msg,
                             self.attr(self.P_UI_AMBER,
                                       curses.A_BOLD | curses.A_REVERSE))

    def _draw_bar(self, y, x, width, frac, attr):
        frac = clamp(frac, 0, 1)
        filled = int(width * frac)
        self.safe_addstr(y, x, "[" + "#" * filled +
                         "." * (width - filled) + "]", attr)

    def render_hack_overlay(self):
        bw = max(40, len(self.hack_target) + 24)
        bh = 7
        bx = (self.maxx - bw) // 2
        by = (self.maxy - bh) // 2
        attr = self.attr(self.P_TERM_ON, curses.A_BOLD)
        # рамка
        self.safe_addstr(by, bx, "+" + "-" * (bw - 2) + "+", attr)
        for i in range(1, bh - 1):
            self.safe_addstr(by + i, bx, "|", attr)
            self.safe_addstr(by + i, bx + bw - 1, "|", attr)
            self.safe_addstr(by + i, bx + 1, " " * (bw - 2),
                             self.attr(self.P_FLOOR))
        self.safe_addstr(by + bh - 1, bx, "+" + "-" * (bw - 2) + "+", attr)

        title = "> TERMINAL HACK <"
        self.safe_addstr(by + 1, bx + (bw - len(title)) // 2, title, attr)

        # код
        tx = bx + (bw - len(self.hack_target)) // 2
        self.safe_addstr(by + 3, tx, self.hack_target,
                         self.attr(self.P_UI_DIM, curses.A_BOLD))
        self.safe_addstr(by + 3, tx, self.hack_typed,
                         self.attr(self.P_TERM_ON, curses.A_BOLD))

        # таймер
        bar_w = bw - 6
        frac = clamp(self.hack_t / 14, 0, 1)
        filled = int(bar_w * frac)
        self.safe_addstr(by + 5, bx + 3,
                         "[" + "#" * filled + "." * (bar_w - filled) + "]",
                         self.attr(self.P_UI_AMBER))
        hint = "наберите буквы по очереди, ESC - отмена"
        self.safe_addstr(by + bh, bx + max(0, (bw - len(hint)) // 2),
                         hint, self.attr(self.P_UI_DIM))

    # -------- main loop --------
    def run(self):
        last = time.time()
        target_fps = 24
        while True:
            now = time.time()
            dt = now - last
            if dt < 1.0 / target_fps:
                time.sleep(1.0 / target_fps - dt)
                now = time.time()
                dt = now - last
            last = now
            if dt > 0.2:
                dt = 0.2

            quit_req = self.handle_input(dt)
            if quit_req:
                return

            self.update(dt)
            self.render()

            # переход сцены после death/win с задержкой
            if self.scene == "play":
                if self.dead and self.flash_t <= 0:
                    self.scene = "dead"
                elif self.win:
                    self.scene = "win"


# =====================================================================
def main(stdscr):
    random.seed()
    try:
        curses.curs_set(0)
    except Exception:
        pass
    Game(stdscr).run()


if __name__ == "__main__":
    # Минимальная проверка размера терминала
    try:
        size = os.get_terminal_size()
        if size.columns < 60 or size.lines < 20:
            print("Терминал слишком маленький. Нужно минимум 60x20 (рекомендуется 100x30).")
            sys.exit(1)
    except OSError:
        pass

    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass
