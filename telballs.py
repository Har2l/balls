"""
Ball exercise 3 - IPC with separate processes (multiprocessing.Queue + Event)

Processes:
  1. main (graphics)   - the ONLY process that touches pygame
  2. Ball x N          - each ball is its own process, computes its next position
  3. Collision Detector- gets proposed positions, resolves collisions, sends
                         corrections back to balls and final positions to main
  4. Print process     - the ONLY process allowed to print to the console

Queues:
  proposal_q : balls     -> detector   ("move", id, x, y, dx, dy, epoch) / ("done", id)
  inboxes[i] : detector  -> ball i     (x, y, dx, dy, epoch)   corrected state
  render_q   : detector  -> main       {"balls": {id: (x, y)}, "all_done": bool}
  print_q    : everyone  -> printer    (kind, text)

Event:
  stop_event : main -> balls           tells all balls to stop (window closed)
"""
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
STEP_DELAY = 0.02  # a ball proposes a new position every 20ms

COLORS = [
    (255, 99, 71),   # Tomato Red
    (46, 204, 113),  # Emerald Green
    (52, 152, 219),  # Sky Blue
    (241, 196, 15),  # Yellow
    (155, 89, 182),  # Purple
    (230, 126, 34),  # Orange
    (26, 188, 156),  # Turquoise
    (255, 192, 203)  # Pink
]
BLACK = (0, 0, 0)


# ----------------------------------------------------------------------------
# Print process - the only one that prints
# ----------------------------------------------------------------------------
def printer_process(print_q):
    print(f"--> [START] Print process started (pid {os.getpid()}).", flush=True)
    active_balls = 0
    while True:
        msg = print_q.get()
        if msg is None:
            break
        kind, text = msg
        if kind == "ball_start":
            active_balls += 1
            print(f"--> [START] {text}", flush=True)
            print(f"Current Active Balls: {active_balls}", flush=True)
        elif kind == "ball_end":
            active_balls -= 1
            print(f"<-- [END] {text}", flush=True)
            print(f"Current Active Balls: {active_balls}", flush=True)
        else:
            print(text, flush=True)
    print("<-- [END] Print process finished.", flush=True)


# Ball process
def ball_process(ball_id, inbox, proposal_q, print_q, stop_event):
    print_q.put(("ball_start", f"Ball-{ball_id} process started (pid {os.getpid()})."))

    x = random.randint(RADIUS, WIDTH - RADIUS)
    y = random.randint(RADIUS, HEIGHT - RADIUS)
    dx = random.choice([-1, 1]) * random.randint(2, 5)
    dy = random.choice([-1, 1]) * random.randint(2, 5)
    epoch = 0  
    moves_left = random.randint(150, 400)

    while moves_left > 0 and not stop_event.is_set():
        # 1. Apply the latest correction from the collision detector (if any)
        try:
            while True:
                x, y, dx, dy, epoch = inbox.get_nowait()
        except queue.Empty:
            pass

        # 2. Calculate the new position (bounce off the walls)
        x += dx
        y += dy
        if x < RADIUS:
            x, dx = RADIUS, abs(dx)
        elif x > WIDTH - RADIUS:
            x, dx = WIDTH - RADIUS, -abs(dx)
        if y < RADIUS:
            y, dy = RADIUS, abs(dy)
        elif y > HEIGHT - RADIUS:
            y, dy = HEIGHT - RADIUS, -abs(dy)

        # 3. Propose the position to the collision detector
        proposal_q.put(("move", ball_id, x, y, dx, dy, epoch))
        moves_left -= 1
        time.sleep(STEP_DELAY)

    proposal_q.put(("done", ball_id))
    print_q.put(("ball_end", f"Ball-{ball_id} process finished."))


# ----------------------------------------------------------------------------
# Collision detector process
# ----------------------------------------------------------------------------
def resolve_collisions(bid, states):
    """Check ball `bid` against all other balls. Returns the set of ids that changed."""
    changed = set()
    a = states[bid]
    for oid, b in states.items():
        if oid == bid:
            continue
        ddx, ddy = a[0] - b[0], a[1] - b[1]
        dist = math.hypot(ddx, ddy)
        if dist >= 2 * RADIUS:
            continue

        # Collision / overlap: normal vector between the centers
        if dist == 0:
            ddx, ddy, dist = 1.0, 0.0, 1.0
        nx, ny = ddx / dist, ddy / dist

        # push both balls back a little, so they no longer overlap
        push = (2 * RADIUS - dist) / 2 + 0.5
        a[0] += nx * push
        a[1] += ny * push
        b[0] -= nx * push
        b[1] -= ny * push

        # new direction: exchange the velocity component along the normal
        rel = (a[2] - b[2]) * nx + (a[3] - b[3]) * ny
        if rel < 0:  # only if they are moving towards each other
            a[2] -= rel * nx
            a[3] -= rel * ny
            b[2] += rel * nx
            b[3] += rel * ny

        changed.add(bid)
        changed.add(oid)

    # keep the pushed balls inside the window
    for cid in changed:
        s = states[cid]
        s[0] = min(max(s[0], RADIUS), WIDTH - RADIUS)
        s[1] = min(max(s[1], RADIUS), HEIGHT - RADIUS)
    return changed


def detector_process(num_balls, proposal_q, inboxes, render_q, print_q):
    print_q.put(("info", f"--> [START] Collision detector process started (pid {os.getpid()})."))

    states = {}      # ball_id -> [x, y, dx, dy]  (only balls that are alive)
    epochs = {}      # ball_id -> current version of the ball's state
    finished = 0
    last_send = 0.0
    final_sent = False

    while True:
        try:
            msg = proposal_q.get(timeout=1 / FPS)
        except queue.Empty:
            msg = False

        if msg is None:  # sentinel from main - shut down
            break

        if msg:
            if msg[0] == "move":
                _, bid, x, y, dx, dy, ep = msg
                if ep < epochs.get(bid, 0):
                    # stale proposal (made before the ball read my correction) - ignore
                    continue
                states[bid] = [x, y, dx, dy]
                for cid in resolve_collisions(bid, states):
                    epochs[cid] = epochs.get(cid, 0) + 1
                    s = states[cid]
                    inboxes[cid].put((s[0], s[1], s[2], s[3], epochs[cid]))
            elif msg[0] == "done":
                states.pop(msg[1], None)
                finished += 1

        # send the final positions to the graphics process (~60 times per second)
        now = time.time()
        all_done = finished == num_balls
        if now - last_send >= 1 / FPS or (all_done and not final_sent):
            render_q.put({
                "balls": {i: (s[0], s[1]) for i, s in states.items()},
                "all_done": all_done,
            })
            last_send = now
            final_sent = final_sent or all_done

    print_q.put(("info", "<-- [END] Collision detector process finished."))
    # don't block process exit on data nobody is going to read anymore
    render_q.cancel_join_thread()
    for q in inboxes.values():
        q.cancel_join_thread()


# ----------------------------------------------------------------------------
# Main process - graphics only
# ----------------------------------------------------------------------------
def main():

    import pygame

    try:
        num_balls = int(input("How many balls do you want to create? "))
    except ValueError:
        num_balls = 5

    proposal_q = mp.Queue()
    render_q = mp.Queue()
    print_q = mp.Queue()
    inboxes = {i: mp.Queue() for i in range(1, num_balls + 1)}
    stop_event = mp.Event()

    printer = mp.Process(target=printer_process, args=(print_q,))
    printer.start()
    print_q.put(("info", f"--> [START] Main (graphics) process started (pid {os.getpid()})."))

    detector = mp.Process(target=detector_process,
                          args=(num_balls, proposal_q, inboxes, render_q, print_q))
    detector.start()

    balls = []
    for i in range(1, num_balls + 1):
        p = mp.Process(target=ball_process,
                       args=(i, inboxes[i], proposal_q, print_q, stop_event))
        balls.append(p)
        p.start()

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

        # take the latest final positions from the collision detector
        try:
            while True:
                data = render_q.get_nowait()
                positions = data["balls"]
                if data["all_done"]:
                    print_q.put(("info", "All ball processes finished. Closing application."))
                    running = False
        except queue.Empty:
            pass

        screen.fill(BLACK)
        for ball_id, (x, y) in positions.items():
            pygame.draw.circle(screen, COLORS[ball_id % len(COLORS)],
                               (int(x), int(y)), RADIUS)
        pygame.display.flip()
        clock.tick(FPS)


    stop_event.set()
    for p in balls:
        p.join(timeout=2)
        if p.is_alive():
            p.terminate()
            p.join()

    proposal_q.put(None)
    detector.join(timeout=2)
    if detector.is_alive():
        detector.terminate()
        detector.join()

    print_q.put(("info", "<-- [END] Main (graphics) process finished."))
    print_q.put(None)             # tell the printer to stop
    printer.join(timeout=2)
    if printer.is_alive():
        printer.terminate()
        printer.join()

    render_q.cancel_join_thread()
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    mp.freeze_support()
    main()