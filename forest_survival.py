"""Выживание в лесу - игра на Python/pygame.

Запуск:
    pip install pygame
    python forest_survival.py

Управление:
    WASD / стрелки  - движение
    Space           - действие (рубить/добыть/собрать/атаковать)
    E               - есть (ягоды или жареное мясо у костра)
    R               - пить из реки (стоя рядом)
    F               - развести/подкинуть в костёр (3 дерева + 2 камня)
    T               - спать у костра
    Esc             - выход
"""

import math
import random
import sys

import pygame

W, H = 880, 560
TILE = 40
FPS = 60

DAY_LEN = 90.0
NIGHT_LEN = 60.0
CYCLE = DAY_LEN + NIGHT_LEN

# Палитра
COL_GRASS = (42, 58, 37)
COL_GRASS_DARK = (50, 64, 40)
COL_GRASS_LIGHT = (59, 74, 48)
COL_RIVER = (58, 100, 128)
COL_RIVER_FOAM = (180, 220, 240)
COL_TRUNK = (90, 58, 32)
COL_LEAF_DARK = (45, 90, 45)
COL_LEAF_LIGHT = (58, 112, 64)
COL_STONE_DARK = (119, 119, 119)
COL_STONE_LIGHT = (153, 153, 153)
COL_BUSH = (58, 74, 48)
COL_BUSH_RIPE = (45, 90, 53)
COL_BERRY = (200, 64, 80)
COL_WOLF_DARK = (58, 58, 58)
COL_WOLF_LIGHT = (74, 74, 74)
COL_WOLF_EYE = (255, 224, 102)
COL_PLAYER = (200, 160, 112)
COL_PLAYER_HEAD = (224, 192, 128)
COL_PLAYER_HIT = (255, 80, 80)
COL_TOOL = (160, 96, 48)
COL_FIRE_OUTER = (255, 112, 32)
COL_FIRE_INNER = (255, 208, 64)
COL_TEXT = (232, 232, 232)
COL_TEXT_DIM = (160, 160, 160)
COL_BG_HUD = (0, 0, 0, 170)
COL_HEALTH = (208, 64, 64)
COL_HUNGER = (208, 144, 64)
COL_THIRST = (64, 144, 208)
COL_ENERGY = (208, 208, 64)


def dist(ax, ay, bx, by):
    return math.hypot(ax - bx, ay - by)


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Выживание в лесу")
        self.screen = pygame.display.set_mode((W, H))
        self.clock = pygame.time.Clock()
        try:
            self.font = pygame.font.SysFont("dejavusansmono,couriernew,monospace", 14)
            self.font_big = pygame.font.SysFont("dejavusansmono,couriernew,monospace", 28, bold=True)
            self.font_small = pygame.font.SysFont("dejavusansmono,couriernew,monospace", 11)
        except Exception:
            self.font = pygame.font.Font(None, 16)
            self.font_big = pygame.font.Font(None, 32)
            self.font_small = pygame.font.Font(None, 13)
        self.overlay_visible = True
        self.show_intro = True
        self.reset()

    # ------- world setup -------
    def reset(self):
        self.trees = [
            {"x": random.uniform(20, W - 20), "y": random.uniform(20, H - 20),
             "hp": 3, "r": 14, "wobble": 0.0}
            for _ in range(65)
        ]
        self.stones = [
            {"x": random.uniform(20, W - 20), "y": random.uniform(20, H - 20),
             "hp": 4, "r": 12, "wobble": 0.0}
            for _ in range(18)
        ]
        self.bushes = [
            {"x": random.uniform(20, W - 20), "y": random.uniform(20, H - 20),
             "berries": random.randint(2, 4), "r": 11, "wobble": 0.0, "regrow": 0.0}
            for _ in range(14)
        ]
        self.wolves = []
        self.blood = []
        self.player = {
            "x": W / 2, "y": H / 2, "r": 11, "speed": 105.0,
            "health": 100.0, "hunger": 100.0, "thirst": 100.0, "energy": 100.0,
            "facing": 0.0, "hit_flash": 0.0, "swing": 0.0, "sleeping": False,
        }
        self.inv = {"wood": 0, "stone": 0, "berries": 0, "meat": 0}
        self.campfire = None  # {"x","y","fuel","lit"}
        self.river = {"y": H * 0.78, "amp": 14.0, "w": 28.0}
        self.time = 0.0
        self.day = 1
        self.survived = 0.0
        self.logs = []  # [{"text","t"}]
        self.game_over = False
        self.last_wolf_spawn = 0.0

    # ------- helpers -------
    def is_night(self):
        return (self.time % CYCLE) >= DAY_LEN

    def time_of_day(self):
        t = self.time % CYCLE
        if t < DAY_LEN * 0.25:
            return "Утро"
        if t < DAY_LEN * 0.7:
            return "День"
        if t < DAY_LEN:
            return "Вечер"
        if t < DAY_LEN + NIGHT_LEN * 0.5:
            return "Ночь"
        return "Поздняя ночь"

    def darkness(self):
        t = self.time % CYCLE
        if t < DAY_LEN * 0.7:
            return 0.0
        if t < DAY_LEN:
            return (t - DAY_LEN * 0.7) / (DAY_LEN * 0.3) * 0.7
        if t < DAY_LEN + NIGHT_LEN * 0.5:
            return 0.7 + (t - DAY_LEN) / (NIGHT_LEN * 0.5) * 0.15
        if t < CYCLE - 5:
            return 0.85
        return 0.85 - (t - (CYCLE - 5)) / 5 * 0.85

    def log(self, text):
        self.logs.insert(0, {"text": text, "t": 0.0})
        if len(self.logs) > 6:
            self.logs = self.logs[:6]

    def river_y(self, x):
        return self.river["y"] + math.sin(x * 0.02) * self.river["amp"]

    def near_river(self, x, y):
        return abs(y - self.river_y(x)) < self.river["w"] / 2 + 16

    def in_river(self, x, y):
        return abs(y - self.river_y(x)) < self.river["w"] / 2

    def nearest(self, arr, x, y, rng):
        best = None
        best_d = rng
        for o in arr:
            d = dist(x, y, o["x"], o["y"])
            if d < best_d:
                best_d = d
                best = o
        return best

    # ------- actions -------
    def action(self):
        p = self.player
        if p["sleeping"]:
            p["sleeping"] = False
            self.log("Ты проснулся")
            return
        p["swing"] = 0.25
        ax = p["x"] + math.cos(p["facing"]) * 22
        ay = p["y"] + math.sin(p["facing"]) * 22

        wolf = self.nearest(self.wolves, ax, ay, 30)
        if wolf:
            wolf["hp"] -= 1
            wolf["kb"] = (math.cos(p["facing"]) * 30, math.sin(p["facing"]) * 30)
            if wolf["hp"] <= 0:
                self.inv["meat"] += 2
                self.blood.append({"x": wolf["x"], "y": wolf["y"], "t": 0.0})
                self.wolves.remove(wolf)
                self.log("Волк убит! +2 мяса")
            return

        tree = self.nearest(self.trees, ax, ay, 28)
        if tree:
            tree["hp"] -= 1
            tree["wobble"] = 0.3
            if tree["hp"] <= 0:
                self.inv["wood"] += random.randint(2, 3)
                self.trees.remove(tree)
                self.log("Срубил дерево")
            return

        st = self.nearest(self.stones, ax, ay, 26)
        if st:
            st["hp"] -= 1
            st["wobble"] = 0.3
            if st["hp"] <= 0:
                self.inv["stone"] += random.randint(1, 2)
                self.stones.remove(st)
                self.log("Добыл камень")
            return

        bush = self.nearest(self.bushes, ax, ay, 26)
        if bush and bush["berries"] > 0:
            self.inv["berries"] += bush["berries"]
            self.log(f"Собрал ягод: {bush['berries']}")
            bush["berries"] = 0
            bush["regrow"] = 60.0
            return

    def eat(self):
        p = self.player
        if self.inv["meat"] > 0 and self.campfire and self.campfire["lit"]:
            self.inv["meat"] -= 1
            p["hunger"] = min(100, p["hunger"] + 35)
            p["health"] = min(100, p["health"] + 8)
            self.log("Жареное мясо — сытно!")
            return
        if self.inv["berries"] > 0:
            self.inv["berries"] -= 1
            p["hunger"] = min(100, p["hunger"] + 10)
            p["thirst"] = min(100, p["thirst"] + 3)
            self.log("Съел ягоду")
            return
        if self.inv["meat"] > 0:
            self.log("Нужен костёр чтобы пожарить мясо")
            return
        self.log("Нечего есть")

    def drink(self):
        p = self.player
        if self.near_river(p["x"], p["y"]):
            p["thirst"] = min(100, p["thirst"] + 30)
            self.log("Освежающая вода")
        else:
            self.log("Нужно подойти к реке")

    def campfire_action(self):
        p = self.player
        if self.campfire is None:
            if self.inv["wood"] >= 3 and self.inv["stone"] >= 2:
                self.inv["wood"] -= 3
                self.inv["stone"] -= 2
                self.campfire = {"x": p["x"], "y": p["y"] - 8, "fuel": 40.0, "lit": True}
                self.log("Костёр разведён")
            else:
                self.log("Нужно 3 дерева и 2 камня")
        else:
            if self.inv["wood"] > 0:
                self.inv["wood"] -= 1
                self.campfire["fuel"] = min(120, self.campfire["fuel"] + 25)
                self.campfire["lit"] = True
                self.log("Подкинул в костёр")
            else:
                self.log("Нет дерева для костра")

    def sleep_action(self):
        if not self.campfire or not self.campfire["lit"]:
            self.log("Спать опасно без костра")
            return
        p = self.player
        if dist(p["x"], p["y"], self.campfire["x"], self.campfire["y"]) > 60:
            self.log("Иди ближе к костру")
            return
        p["sleeping"] = True
        self.log("Ты заснул...")

    def spawn_wolf(self):
        side = random.randint(0, 3)
        if side == 0:
            x, y = -20, random.uniform(0, H)
        elif side == 1:
            x, y = W + 20, random.uniform(0, H)
        elif side == 2:
            x, y = random.uniform(0, W), -20
        else:
            x, y = random.uniform(0, W), H + 20
        self.wolves.append({
            "x": x, "y": y, "r": 12,
            "speed": 70.0 + self.day * 4,
            "hp": 2 + self.day // 2,
            "cool": 0.0, "flee": False,
        })

    # ------- update -------
    def update(self, dt, keys):
        if self.game_over:
            return
        p = self.player

        self.time += dt
        self.survived += dt
        new_day = int(self.time // CYCLE) + 1
        if new_day != self.day:
            self.day = new_day
            self.log(f"Настал день {self.day}")

        if p["sleeping"]:
            self.time += dt * 4
            p["energy"] = min(100, p["energy"] + dt * 25)
            p["health"] = min(100, p["health"] + dt * 3)
            if p["energy"] >= 99:
                p["sleeping"] = False
                self.log("Хорошо отдохнул")

        dx, dy = 0, 0
        if not p["sleeping"]:
            if keys[pygame.K_w] or keys[pygame.K_UP]:
                dy -= 1
            if keys[pygame.K_s] or keys[pygame.K_DOWN]:
                dy += 1
            if keys[pygame.K_a] or keys[pygame.K_LEFT]:
                dx -= 1
            if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
                dx += 1
        if dx or dy:
            l = math.hypot(dx, dy)
            dx, dy = dx / l, dy / l
            p["facing"] = math.atan2(dy, dx)
            speed = p["speed"] * (1.0 if p["energy"] > 0 else 0.5)
            if self.in_river(p["x"], p["y"]):
                speed *= 0.5
            p["x"] += dx * speed * dt
            p["y"] += dy * speed * dt
            p["energy"] = max(0, p["energy"] - dt * 1.2)
        elif not p["sleeping"]:
            p["energy"] = min(100, p["energy"] + dt * 0.3)

        p["x"] = clamp(p["x"], p["r"], W - p["r"])
        p["y"] = clamp(p["y"], p["r"], H - p["r"])

        p["hunger"] = max(0, p["hunger"] - dt * 0.9)
        p["thirst"] = max(0, p["thirst"] - dt * 1.2)
        if p["hunger"] <= 0:
            p["health"] -= dt * 2
        if p["thirst"] <= 0:
            p["health"] -= dt * 3

        if self.is_night():
            near_fire = (self.campfire and self.campfire["lit"]
                         and dist(p["x"], p["y"], self.campfire["x"], self.campfire["y"]) < 80)
            if not near_fire:
                p["health"] -= dt * 1.2

        if p["swing"] > 0:
            p["swing"] -= dt
        if p["hit_flash"] > 0:
            p["hit_flash"] -= dt

        for b in self.bushes:
            if b["regrow"] > 0:
                b["regrow"] -= dt
                if b["regrow"] <= 0:
                    b["berries"] = random.randint(2, 4)
            if b["wobble"] > 0:
                b["wobble"] -= dt
        for t in self.trees:
            if t["wobble"] > 0:
                t["wobble"] -= dt
        for s in self.stones:
            if s["wobble"] > 0:
                s["wobble"] -= dt

        if self.campfire:
            self.campfire["fuel"] -= dt
            if self.campfire["fuel"] <= 0:
                self.campfire["lit"] = False
                self.campfire["fuel"] = 0

        if self.is_night():
            self.last_wolf_spawn += dt
            interval = max(5, 14 - self.day)
            max_wolves = min(2 + self.day, 8)
            if self.last_wolf_spawn > interval and len(self.wolves) < max_wolves:
                self.spawn_wolf()
                self.last_wolf_spawn = 0
        else:
            for w in self.wolves:
                if random.random() < dt * 0.3:
                    w["flee"] = True

        for w in self.wolves:
            if "kb" in w:
                kx, ky = w["kb"]
                w["x"] += kx * dt * 6
                w["y"] += ky * dt * 6
                w["kb"] = (kx * 0.7, ky * 0.7)
                if abs(kx) < 1 and abs(ky) < 1:
                    del w["kb"]
            ddx = p["x"] - w["x"]
            ddy = p["y"] - w["y"]
            d = math.hypot(ddx, ddy) or 1
            mult = 1.0
            if w.get("flee"):
                mult = -0.7
            if self.campfire and self.campfire["lit"]:
                fd = dist(w["x"], w["y"], self.campfire["x"], self.campfire["y"])
                if fd < 90:
                    mult = -1.2
            w["x"] += (ddx / d) * w["speed"] * dt * mult
            w["y"] += (ddy / d) * w["speed"] * dt * mult
            if w["cool"] > 0:
                w["cool"] -= dt
            if d < 22 and w["cool"] <= 0:
                p["health"] -= 8 + self.day
                p["hit_flash"] = 0.3
                w["cool"] = 1.0
                self.log("Волк укусил!")

        self.wolves = [w for w in self.wolves
                       if w["hp"] > 0 and -60 < w["x"] < W + 60 and -60 < w["y"] < H + 60]

        for l in self.logs:
            l["t"] += dt

        for b in self.blood:
            b["t"] += dt
        self.blood = [b for b in self.blood if b["t"] < 20]

        if p["health"] <= 0:
            self.game_over = True
            self.overlay_visible = True

    # ------- rendering -------
    def draw_ground(self):
        self.screen.fill(COL_GRASS)
        # детерминированные пучки травы
        for i in range(250):
            x = (i * 137) % W
            y = (i * 91 + 41) % H
            self.screen.fill(COL_GRASS_DARK, (x, y, 2, 2))
        for i in range(150):
            x = (i * 211 + 13) % W
            y = (i * 73 + 17) % H
            self.screen.fill(COL_GRASS_LIGHT, (x, y, 1, 1))

    def draw_river(self):
        r = self.river
        top = [(x, self.river_y(x) - r["w"] / 2) for x in range(0, W + 1, 8)]
        bot = [(x, self.river_y(x) + r["w"] / 2) for x in range(W, -1, -8)]
        pygame.draw.polygon(self.screen, COL_RIVER, top + bot)
        # шум блёсток
        phase = self.time * 2
        pts = []
        for x in range(0, W + 1, 4):
            y = self.river_y(x) + math.sin(x * 0.1 + phase) * 3
            pts.append((x, y))
        if len(pts) > 1:
            pygame.draw.lines(self.screen, COL_RIVER_FOAM, False, pts, 1)

    def draw_tree(self, t):
        wob = math.sin(self.time * 8) * t["wobble"] * 3
        # тень
        shadow = pygame.Surface((t["r"] * 2 + 8, int(t["r"] * 0.8 + 4)), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 80), shadow.get_rect())
        self.screen.blit(shadow, (t["x"] - t["r"] + 4, t["y"] - t["r"] * 0.4 + 6))
        # ствол
        pygame.draw.rect(self.screen, COL_TRUNK,
                         (t["x"] - 3 + wob, t["y"] - 4, 6, 14))
        # крона
        pygame.draw.circle(self.screen, COL_LEAF_DARK,
                           (int(t["x"] + wob), int(t["y"] - 6)), t["r"])
        pygame.draw.circle(self.screen, COL_LEAF_LIGHT,
                           (int(t["x"] - 3 + wob), int(t["y"] - 9)), int(t["r"] * 0.7))

    def draw_stone(self, s):
        wob = math.sin(self.time * 10) * s["wobble"] * 2
        shadow = pygame.Surface((s["r"] * 2 + 4, int(s["r"] * 0.8 + 4)), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 80), shadow.get_rect())
        self.screen.blit(shadow, (s["x"] - s["r"] + 2, s["y"] - s["r"] * 0.4 + 4))
        pygame.draw.circle(self.screen, COL_STONE_DARK,
                           (int(s["x"] + wob), int(s["y"])), s["r"])
        pygame.draw.circle(self.screen, COL_STONE_LIGHT,
                           (int(s["x"] - 3 + wob), int(s["y"] - 3)), int(s["r"] * 0.5))

    def draw_bush(self, b):
        wob = math.sin(self.time * 8) * b["wobble"] * 2
        shadow = pygame.Surface((b["r"] * 2 + 4, int(b["r"] * 0.8 + 4)), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 70), shadow.get_rect())
        self.screen.blit(shadow, (b["x"] - b["r"] + 2, b["y"] - b["r"] * 0.4 + 4))
        col = COL_BUSH_RIPE if b["berries"] > 0 else COL_BUSH
        pygame.draw.circle(self.screen, col,
                           (int(b["x"] + wob), int(b["y"])), b["r"])
        for i in range(b["berries"]):
            a = (i / 5.0) * math.pi * 2 + b["x"] * 0.01
            bx = b["x"] + math.cos(a) * 6 + wob
            by = b["y"] + math.sin(a) * 6
            pygame.draw.circle(self.screen, COL_BERRY, (int(bx), int(by)), 2)

    def draw_wolf(self, w):
        shadow = pygame.Surface((w["r"] * 2 + 4, int(w["r"] * 0.8 + 4)), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 80), shadow.get_rect())
        self.screen.blit(shadow, (w["x"] - w["r"] + 2, w["y"] - w["r"] * 0.4 + 5))
        pygame.draw.circle(self.screen, COL_WOLF_DARK,
                           (int(w["x"]), int(w["y"])), w["r"])
        a = math.atan2(self.player["y"] - w["y"], self.player["x"] - w["x"])
        hx = w["x"] + math.cos(a) * 8
        hy = w["y"] + math.sin(a) * 8
        pygame.draw.circle(self.screen, COL_WOLF_LIGHT,
                           (int(hx), int(hy)), int(w["r"] * 0.6))
        if self.is_night():
            ex = w["x"] + math.cos(a) * 10
            ey = w["y"] + math.sin(a) * 10
            dx, dy = math.cos(a + 0.5) * 2, math.sin(a + 0.5) * 2
            pygame.draw.circle(self.screen, COL_WOLF_EYE, (int(ex + dx), int(ey + dy)), 2)
            pygame.draw.circle(self.screen, COL_WOLF_EYE, (int(ex - dx), int(ey - dy)), 2)

    def draw_player(self):
        p = self.player
        shadow = pygame.Surface((p["r"] * 2 + 4, int(p["r"] * 0.8 + 4)), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 80), shadow.get_rect())
        self.screen.blit(shadow, (p["x"] - p["r"] + 2, p["y"] - p["r"] * 0.4 + 6))
        body_col = COL_PLAYER_HIT if p["hit_flash"] > 0 else COL_PLAYER
        pygame.draw.circle(self.screen, body_col,
                           (int(p["x"]), int(p["y"])), p["r"])
        hx = p["x"] + math.cos(p["facing"]) * 4
        hy = p["y"] + math.sin(p["facing"]) * 4 - 2
        pygame.draw.circle(self.screen, COL_PLAYER_HEAD,
                           (int(hx), int(hy)), int(p["r"] * 0.55))
        # инструмент
        ext = 16 + (6 if p["swing"] > 0 else 0)
        tx = p["x"] + math.cos(p["facing"]) * ext
        ty = p["y"] + math.sin(p["facing"]) * ext
        sx = p["x"] + math.cos(p["facing"]) * 8
        sy = p["y"] + math.sin(p["facing"]) * 8
        pygame.draw.line(self.screen, COL_TOOL, (sx, sy), (tx, ty), 3)
        if p["sleeping"]:
            txt = self.font.render("Zzz", True, (255, 255, 255))
            self.screen.blit(txt, (p["x"] + 10, p["y"] - 22))

    def draw_campfire(self):
        c = self.campfire
        if not c:
            return
        for i in range(5):
            a = (i / 5.0) * math.pi * 2
            sx = c["x"] + math.cos(a) * 11
            sy = c["y"] + math.sin(a) * 11
            pygame.draw.circle(self.screen, (102, 102, 102), (int(sx), int(sy)), 3)
        pygame.draw.rect(self.screen, COL_TRUNK,
                         (c["x"] - 6, c["y"] - 2, 12, 4))
        pygame.draw.rect(self.screen, COL_TRUNK,
                         (c["x"] - 2, c["y"] - 6, 4, 12))
        if c["lit"]:
            f = math.sin(self.time * 12) * 2
            outer = [(c["x"] - 6, c["y"]),
                     (c["x"] - 3, c["y"] - 14 - f),
                     (c["x"], c["y"] - 14),
                     (c["x"] + 3, c["y"] - 16 - f),
                     (c["x"] + 6, c["y"])]
            pygame.draw.polygon(self.screen, COL_FIRE_OUTER, outer)
            inner = [(c["x"] - 3, c["y"]),
                     (c["x"], c["y"] - 10 + f),
                     (c["x"] + 3, c["y"])]
            pygame.draw.polygon(self.screen, COL_FIRE_INNER, inner)

    def draw_darkness(self):
        d = self.darkness()
        if d <= 0:
            return
        dark = pygame.Surface((W, H), pygame.SRCALPHA)
        dark.fill((5, 10, 30, int(d * 255)))
        if d > 0.5:
            # вырезаем свет вокруг игрока и костра
            self._cut_light(dark, self.player["x"], self.player["y"], 70, int(d * 180))
            if self.campfire and self.campfire["lit"]:
                self._cut_light(dark, self.campfire["x"], self.campfire["y"], 130, int(d * 255))
        self.screen.blit(dark, (0, 0))

        # тёплое свечение костра поверх темноты
        if self.campfire and self.campfire["lit"]:
            c = self.campfire
            glow = pygame.Surface((300, 300), pygame.SRCALPHA)
            for r in range(120, 0, -8):
                alpha = int(50 * (1 - r / 120) * d)
                pygame.draw.circle(glow, (255, 180, 80, alpha), (150, 150), r)
            self.screen.blit(glow, (c["x"] - 150, c["y"] - 150),
                             special_flags=pygame.BLEND_RGBA_ADD)

    @staticmethod
    def _cut_light(surf, cx, cy, radius, max_alpha):
        cut = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        for r in range(radius, 0, -4):
            alpha = int(max_alpha * (r / radius))
            pygame.draw.circle(cut, (0, 0, 0, alpha), (radius, radius), r)
        surf.blit(cut, (cx - radius, cy - radius),
                  special_flags=pygame.BLEND_RGBA_SUB)

    def draw_blood(self):
        for b in self.blood:
            alpha = max(0, int(127 * (1 - b["t"] / 20)))
            if alpha <= 0:
                continue
            s = pygame.Surface((20, 20), pygame.SRCALPHA)
            pygame.draw.circle(s, (120, 20, 20, alpha), (10, 10), 8)
            self.screen.blit(s, (b["x"] - 10, b["y"] - 10))

    def draw_hud(self):
        bar_w = 110
        bar_h = 6
        x0 = 8
        y0 = 8
        stats = [
            ("Здоровье", self.player["health"], COL_HEALTH),
            ("Голод", self.player["hunger"], COL_HUNGER),
            ("Жажда", self.player["thirst"], COL_THIRST),
            ("Энергия", self.player["energy"], COL_ENERGY),
        ]
        for i, (name, val, col) in enumerate(stats):
            bx = x0 + i * (bar_w + 8)
            panel = pygame.Surface((bar_w, 30), pygame.SRCALPHA)
            panel.fill((0, 0, 0, 160))
            self.screen.blit(panel, (bx, y0))
            t = self.font_small.render(name, True, COL_TEXT)
            self.screen.blit(t, (bx + 4, y0 + 2))
            pygame.draw.rect(self.screen, (40, 40, 40),
                             (bx + 4, y0 + 18, bar_w - 8, bar_h))
            w = int((bar_w - 8) * max(0, val) / 100)
            pygame.draw.rect(self.screen, col,
                             (bx + 4, y0 + 18, w, bar_h))

        # инвентарь
        inv_lines = [
            f"Дерево: {self.inv['wood']}",
            f"Камень: {self.inv['stone']}",
            f"Ягоды:  {self.inv['berries']}",
            f"Мясо:   {self.inv['meat']}",
        ]
        if self.campfire is None:
            inv_lines.append("Костёр: нет")
        elif self.campfire["lit"]:
            inv_lines.append(f"Костёр: горит ({int(self.campfire['fuel'])})")
        else:
            inv_lines.append("Костёр: погас")
        panel = pygame.Surface((130, len(inv_lines) * 16 + 8), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 180))
        self.screen.blit(panel, (8, H - panel.get_height() - 8))
        for i, line in enumerate(inv_lines):
            t = self.font.render(line, True, COL_TEXT)
            self.screen.blit(t, (12, H - panel.get_height() - 4 + i * 16))

        # инфо
        info_lines = [
            f"День {self.day} · {self.time_of_day()}",
            f"Прожито: {int(self.survived // 60)} мин",
        ]
        info_w = 180
        panel = pygame.Surface((info_w, len(info_lines) * 16 + 8), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 180))
        self.screen.blit(panel, (W - info_w - 8, H - panel.get_height() - 8))
        for i, line in enumerate(info_lines):
            t = self.font.render(line, True, COL_TEXT)
            tw = t.get_width()
            self.screen.blit(t, (W - 12 - tw, H - panel.get_height() - 4 + i * 16))

        # лог справа сверху
        log_x = W - 210
        log_y = 80
        for i, l in enumerate(self.logs):
            if l["t"] >= 6:
                continue
            alpha = max(40, int(255 * (1 - l["t"] / 6)))
            t = self.font_small.render(l["text"], True, COL_TEXT)
            t.set_alpha(alpha)
            self.screen.blit(t, (log_x, log_y + i * 14))

    def draw_overlay(self):
        layer = pygame.Surface((W, H), pygame.SRCALPHA)
        layer.fill((0, 0, 0, 220))
        self.screen.blit(layer, (0, 0))

        if self.game_over:
            title = "ТЫ ПОГИБ"
            lines = [
                f"Дней прожито: {self.day}",
                f"Время выживания: {int(self.survived // 60)} мин {int(self.survived % 60)} сек",
                self._death_reason(),
                "",
                "Нажми ПРОБЕЛ чтобы начать заново   /   Esc — выход",
            ]
        else:
            title = "ВЫЖИВАНИЕ В ЛЕСУ"
            lines = [
                "Ты потерялся в глухом лесу.",
                "Собирай ресурсы, ешь, пей, спи. Не замёрзни ночью.",
                "Берегись волков — они приходят с темнотой.",
                "Костёр греет и отпугивает зверей.",
                "",
                "WASD/стрелки — движение",
                "Space — действие   E — есть   R — пить",
                "F — костёр (3 дерева + 2 камня)   T — спать",
                "",
                "Нажми ПРОБЕЛ чтобы начать",
            ]

        title_surf = self.font_big.render(title, True, (122, 184, 122))
        self.screen.blit(title_surf,
                         ((W - title_surf.get_width()) // 2, 120))
        for i, line in enumerate(lines):
            t = self.font.render(line, True, COL_TEXT)
            self.screen.blit(t, ((W - t.get_width()) // 2, 180 + i * 22))

    def _death_reason(self):
        p = self.player
        if p["hunger"] <= 0:
            return "Голод свёл тебя в могилу."
        if p["thirst"] <= 0:
            return "Жажда оказалась смертельной."
        if self.wolves:
            return "Волки разорвали тебя на части."
        return "Лес поглотил тебя."

    def render(self):
        self.draw_ground()
        self.draw_river()
        self.draw_blood()

        drawables = []
        for t in self.trees:
            drawables.append((t["y"], lambda t=t: self.draw_tree(t)))
        for s in self.stones:
            drawables.append((s["y"], lambda s=s: self.draw_stone(s)))
        for b in self.bushes:
            drawables.append((b["y"], lambda b=b: self.draw_bush(b)))
        for w in self.wolves:
            drawables.append((w["y"], lambda w=w: self.draw_wolf(w)))
        drawables.append((self.player["y"], self.draw_player))
        if self.campfire:
            drawables.append((self.campfire["y"], self.draw_campfire))
        drawables.sort(key=lambda x: x[0])
        for _, fn in drawables:
            fn()

        self.draw_darkness()
        self.draw_hud()

        if self.overlay_visible:
            self.draw_overlay()

    # ------- main loop -------
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
                        running = False
                    elif self.overlay_visible:
                        if event.key == pygame.K_SPACE:
                            if self.game_over:
                                self.reset()
                            self.overlay_visible = False
                            self.log("Ты очнулся в лесу...")
                    else:
                        if event.key == pygame.K_SPACE:
                            self.action()
                        elif event.key == pygame.K_e:
                            self.eat()
                        elif event.key == pygame.K_r:
                            self.drink()
                        elif event.key == pygame.K_f:
                            self.campfire_action()
                        elif event.key == pygame.K_t:
                            self.sleep_action()

            keys = pygame.key.get_pressed()
            if not self.overlay_visible and not self.game_over:
                self.update(dt, keys)
            self.render()
            pygame.display.flip()

        pygame.quit()


def main():
    random.seed()
    Game().run()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pygame.quit()
        sys.exit(0)
