import random
from dataclasses import dataclass

WIDTH = 30
HEIGHT = 30
INITIAL_LENGTH = 5

DIRECTIONS = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
}


@dataclass
class Snake:
    name: str
    body: list
    direction: str
    alive: bool = True

    @property
    def head(self):
        return self.body[0]

    def to_dict(self):
        return {"name": self.name, "body": self.body, "alive": self.alive}


class Game:
    def __init__(self):
        self.red = Snake(
            "red",
            [(10, 15), (9, 15), (8, 15), (7, 15), (6, 15)],
            direction="right",
        )
        self.blue = Snake(
            "blue",
            [(19, 15), (20, 15), (21, 15), (22, 15), (23, 15)],
            direction="left",
        )
        self.apple = self._spawn_apple()
        self.tick = 0
        self.winner = None
        self.finished = False
        self.history = []

    def _spawn_apple(self):
        occupied = set(self.red.body) | set(self.blue.body)
        free = [
            (x, y)
            for x in range(WIDTH)
            for y in range(HEIGHT)
            if (x, y) not in occupied
        ]
        return random.choice(free) if free else None

    def state(self):
        return {
            "tick": self.tick,
            "red": self.red.to_dict(),
            "blue": self.blue.to_dict(),
            "apple": self.apple,
            "winner": self.winner,
            "finished": self.finished,
        }

    def step(self, red_dir, blue_dir):
        if self.finished:
            return False
        self.tick += 1

        if red_dir in DIRECTIONS:
            self.red.direction = red_dir
        if blue_dir in DIRECTIONS:
            self.blue.direction = blue_dir

        rdx, rdy = DIRECTIONS[self.red.direction]
        bdx, bdy = DIRECTIONS[self.blue.direction]
        new_red = (self.red.head[0] + rdx, self.red.head[1] + rdy)
        new_blue = (self.blue.head[0] + bdx, self.blue.head[1] + bdy)

        def oob(p):
            return not (0 <= p[0] < WIDTH and 0 <= p[1] < HEIGHT)

        red_wall = oob(new_red)
        blue_wall = oob(new_blue)
        red_self = new_red in self.red.body
        blue_self = new_blue in self.blue.body
        head_on_head = new_red == new_blue
        red_hits_blue = (new_red in self.blue.body) or head_on_head
        blue_hits_red = (new_blue in self.red.body) or head_on_head

        red_dead = red_wall or red_self or red_hits_blue
        blue_dead = blue_wall or blue_self or blue_hits_red

        if red_dead and blue_dead:
            if len(self.red.body) > len(self.blue.body):
                blue_dead = False
            else:
                red_dead = False

        if red_dead or blue_dead:
            if red_dead:
                self.red.alive = False
                self.winner = "blue"
            else:
                self.blue.alive = False
                self.winner = "red"
            self.finished = True
            self.history.append(self.state())
            return False

        self.red.body.insert(0, new_red)
        self.blue.body.insert(0, new_blue)

        red_ate = new_red == self.apple
        blue_ate = new_blue == self.apple
        if red_ate and blue_ate:
            if len(self.red.body) >= len(self.blue.body):
                blue_ate = False
            else:
                red_ate = False

        if red_ate or blue_ate:
            self.apple = self._spawn_apple()
        else:
            self.red.body.pop()
            self.blue.body.pop()

        self.history.append(self.state())
        return True
