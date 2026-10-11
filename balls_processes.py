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
    """Same logic as the old BallThread, but it only PROPOSES a position."""
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


def detector_process(num_balls, proposal_q, render_q, print_q):
    """Gets proposed positions, pushes overlapping balls apart, sends final positions to main."""
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

        if msg and msg[0] == "move":
            _, bid, x, y = msg
            def overlaps(px, py):
                return [(ox, oy) for oid, (ox, oy) in positions.items()
                        if oid != bid and math.hypot(px - ox, py - oy) < 2 * RADIUS]

            for _ in range(20):  # push away from every ball we overlap with
                hits = overlaps(x, y)
                if not hits:
                    break
                for ox, oy in hits:
                    dist = math.hypot(x - ox, y - oy) or 0.01
                    push = 2 * RADIUS - dist + 1
                    x += (x - ox) / dist * push
                    y += (y - oy) / dist * push
                x = min(max(x, RADIUS), WIDTH - RADIUS)
                y = min(max(y, RADIUS), HEIGHT - RADIUS)
            for _ in range(200):  # pushing failed (e.g. stuck at a wall) - take a free spot
                if not overlaps(x, y):
                    break
                x = random.randint(RADIUS, WIDTH - RADIUS)
                y = random.randint(RADIUS, HEIGHT - RADIUS)
            positions[bid] = (x, y)
        elif msg and msg[0] == "done":
            positions.pop(msg[1], None)
            finished += 1

        if time.time() - last_send >= 1 / FPS or finished == num_balls:
            render_q.put({"balls": dict(positions), "all_done": finished == num_balls})
            last_send = time.time()

    print_q.put(("info", "<-- [END] Collision detector finished."))
    render_q.cancel_join_thread()


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
    pygame.display.set_caption("My Jumping Balls - Processes")
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

        screen.fill(BLACK)
        for ball_id, (x, y) in positions.items():
            pygame.draw.circle(screen, COLORS[ball_id % len(COLORS)], (int(x), int(y)), RADIUS)
        pygame.display.flip()
        clock.tick(FPS)

    # nothing may keep running in the background
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
