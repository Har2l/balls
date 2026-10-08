import threading
import pygame
import sys
import random
import time

pygame.init()

WIDTH, HEIGHT = 800, 600
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("My Jumping Balls")

COLORS = [
    (255, 99, 71),  # Tomato Red
    (46, 204, 113),  # Emerald Green
    (52, 152, 219),  # Sky Blue
    (241, 196, 15),  # Yellow
    (155, 89, 182),  # Purple
    (230, 126, 34),  # Orange
    (26, 188, 156),  # Turquoise
    (255, 192, 203)  # Pink
]
BLACK = (0, 0, 0)

active_balls = []
balls_lock = threading.Lock()


def report_active_count():
    with balls_lock:
        print(f"Current Active Threads/Balls: {len(active_balls)}")


class BallThread(threading.Thread):
    def __init__(self, ball_id):
        super().__init__()
        self.ball_id = ball_id
        self.radius = 20


        self.x = random.randint(self.radius, WIDTH - self.radius)
        self.y = random.randint(self.radius, HEIGHT - self.radius)
        self.speed_x = random.choice([-5, -4, -3, 3, 4, 5])
        self.speed_y = random.choice([-5, -4, -3, 3, 4, 5])
        self.color = random.choice(COLORS)
        self.moves_left = random.randint(500, 1500)
        self.is_alive = True

    def run(self):

        print(f"--> [START] Thread-{self.ball_id} started running.")
        report_active_count()


        while self.moves_left > 0 and self.is_alive:
            self.x += self.speed_x
            self.y += self.speed_y
            self.moves_left -= 1


            if self.x - self.radius <= 0:
                self.x = self.radius
                self.speed_x = -self.speed_x
            elif self.x + self.radius >= WIDTH:
                self.x = WIDTH - self.radius
                self.speed_x = -self.speed_x

            if self.y - self.radius <= 0:
                self.y = self.radius
                self.speed_y = -self.speed_y
            elif self.y + self.radius >= HEIGHT:
                self.y = HEIGHT - self.radius
                self.speed_y = -self.speed_y


            time.sleep(1 / 60)


        with balls_lock:
            if self in active_balls:
                active_balls.remove(self)


        print(f"<-- [END] Thread-{self.ball_id} has finished.")
        report_active_count()



try:
    num_balls = int(input("How many balls do you want to create? "))
except ValueError:
    num_balls = 5

for i in range(num_balls):
    ball = BallThread(ball_id=i + 1)
    active_balls.append(ball)
    ball.start()

clock = pygame.time.Clock()
FPS = 60

running = True
initial_creation_done = True

while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
            for ball in active_balls:
                ball.is_alive = False

    with balls_lock:
        if len(active_balls) == 0 and initial_creation_done:
            print("All threads finished. Closing application.")
            running = False

    screen.fill(BLACK)

    with balls_lock:
        for ball in active_balls:
            pygame.draw.circle(screen, ball.color, (int(ball.x), int(ball.y)), ball.radius)

    pygame.display.flip()
    clock.tick(FPS)

pygame.quit()
sys.exit()
