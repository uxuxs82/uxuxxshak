import os
import signal
import subprocess
import sys
import time

BOT_COUNT = 15
BASE_URL = os.environ.get("ARENA_URL", "https://your-app.up.railway.app")

processes = []


def spawn(i):
    name = f"uxuxx{i}"
    env = os.environ.copy()
    env["BOT_NAME"] = name
    env["ARENA_URL"] = BASE_URL
    p = subprocess.Popen(
        [sys.executable, "client.py"],
        env=env,
        stdout=open(f"log_{name}.txt", "w"),
        stderr=subprocess.STDOUT,
    )
    processes.append((name, p))
    print(f"started {name} pid={p.pid}")


def shutdown(*_):
    print("stopping all bots")
    for name, p in processes:
        try:
            p.terminate()
        except Exception:
            pass
    time.sleep(1)
    for name, p in processes:
        try:
            p.kill()
        except Exception:
            pass
    sys.exit(0)


def main():
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    for i in range(1, BOT_COUNT + 1):
        spawn(i)
        time.sleep(0.5)
    print(f"{BOT_COUNT} bots running. Ctrl+C to stop.")
    while True:
        for name, p in processes:
            if p.poll() is not None:
                print(f"{name} died, restarting")
                spawn(int(name[5:]))
        time.sleep(5)


if __name__ == "__main__":
    main()
