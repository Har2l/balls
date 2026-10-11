import math
import multiprocessing as mp
import os
import queue
import random
import sys
import time

WIDTH, HEIGHT = 800, 600
RADIUS = 20
FPS = 60

COLORS = [
    (255, 99, 71), (46, 204, 113), (52, 152, 219), (241, 196, 15),
    (155, 89, 182), (230, 126, 34), (26, 188, 156), (255, 192, 203)
]
BLACK = (0, 0, 0)


def printer_process(print_q):
    """The only process that prints. Also counts the active balls."""
    print(f"--> [START] Print process started (pid {os.getpid()}).", flush=True)
    active = 0
    while True:
        msg = print_q.get()
        if msg is None:
            break
        kind, text = msg
        print(text, flush=True)
        if kind in ("ball_start", "ball_end"):
            active += 1 if kind == "ball_start" else -1
            print(f"Current Active Balls: {active}", flush=True)
    print("<-- [END] Print process finished.", flush=True)



def ball_process(ball_id, proposal_q, print_q, stop_event):
    """PROPOSES a position.creates a ball"""
    print_q.put(("ball_start", f"--> [START] Ball-{ball_id} started (pid {os.getpid()})."))
    moves_left = random.randint(20, 50)
    while moves_left > 0 and not stop_event.is_set():
        x = random.randint(RADIUS, WIDTH - RADIUS)
        y = random.randint(RADIUS, HEIGHT - RADIUS)
        proposal_q.put(("move", ball_id, x, y))
        moves_left -= 1
        time.sleep(0.2)
    proposal_q.put(("done", ball_id))
    print_q.put(("ball_end", f"<-- [END] Ball-{ball_id} finished."))

# class BallThread(threading.Thread):
#     def __init__(self, ball_id):
#         super().__init__()
#         self.ball_id = ball_id
#         self.radius = 20
#
#         # Initial random spawn
#         self.x = random.randint(self.radius, WIDTH - self.radius)
#         self.y = random.randint(self.radius, HEIGHT - self.radius)
#
#         self.color = random.choice(COLORS)
#
#         # Reduced moves_left because the sleep time per move is now longer
#         self.moves_left = random.randint(20, 50)
#         self.is_alive = True
#
#     def run(self):
#         print(f"--> [START] Thread-{self.ball_id} started running.")
#         report_active_count()
#
#         while self.moves_left > 0 and self.is_alive:
#             # Change location randomly all over the map
#             self.x = random.randint(self.radius, WIDTH - self.radius)
#             self.y = random.randint(self.radius, HEIGHT - self.radius)
#
#             self.moves_left -= 1
#
#             # Sleep for 0.2 seconds so you can actually see them jump
#             time.sleep(0.2)
#
#         with balls_lock:
#             if self in active_balls:
#                 active_balls.remove(self)
#
#         print(f"<-- [END] Thread-{self.ball_id} has finished.")
#         report_active_count()
def detector_process(num_balls, proposal_q, render_q, print_q):
    print_q.put(("info", f"--> [START] Collision detector started (pid {os.getpid()})."))
    positions = {}
    finished = 0
    last_send = 0
    while True:
        try:
            msg = proposal_q.get(timeout=1 / FPS)
        except queue.Empty:
            msg = False
        if msg is None:
            break



def main():
    import pygame  # only imported here so the other processes never touch pygame

    try:
        num_balls = int(input("How many balls do you want to create? "))
    except ValueError:
        num_balls = 5

    proposal_q, render_q, print_q = mp.Queue(), mp.Queue(), mp.Queue()
    stop_event = mp.Event()

    printer = mp.Process(target=printer_process, args=(print_q,))
    printer.start()
    print_q.put(("info", f"--> [START] Main (graphics) started (pid {os.getpid()})."))
    detector = mp.Process(target=detector_process,
                          args=(num_balls, proposal_q, render_q, print_q))
    detector.start()
    balls = [mp.Process(target=ball_process, args=(i, proposal_q, print_q, stop_event))
             for i in range(1, num_balls + 1)]
    for b in balls:
        b.start()

    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("My Balls")
    clock = pygame.time.Clock()

    positions = {}
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
        try:
            while True:
                data = render_q.get_nowait()
                positions = data["balls"]
                if data["all_done"]:
                    print_q.put(("info", "All balls finished. Closing application."))
                    running = False
        except queue.Empty:
            pass

        screen.fill(BLACK) #Everytime draws the code based on the current x,y of the position
        for ball_id, (x, y) in positions.items():
            pygame.draw.circle(screen, COLORS[ball_id % len(COLORS)], (int(x), int(y)), RADIUS)
        pygame.display.flip()
        clock.tick(FPS)

    # nothing keeps running in the background
    stop_event.set()
    for b in balls:
        b.join()
    proposal_q.put(None)
    detector.join()
    print_q.put(("info", "<-- [END] Main (graphics) finished."))
    print_q.put(None)
    printer.join()
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()

