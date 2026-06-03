#!/usr/bin/env python3
import psutil
import time
import csv
import sys
import signal

# Handle graceful shutdown when the bash script sends a termination signal
def handle_sigterm(signum, frame):
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_sigterm)
signal.signal(signal.SIGINT, handle_sigterm)

def access_denied_value(fn):
    try:
        return fn()
    except psutil.AccessDenied:
        return ''

output_file = sys.argv[1]
memory_output_file = sys.argv[2] if len(sys.argv) > 2 else None
memory_pid = int(sys.argv[3]) if len(sys.argv) > 3 else None
num_cores = psutil.cpu_count()
memory_process = psutil.Process(memory_pid) if memory_pid is not None else None

with open(output_file, mode='w', newline='') as f:
    memory_file = open(memory_output_file, mode='w', newline='') if memory_output_file else None
    writer = csv.writer(f)
    memory_writer = csv.writer(memory_file) if memory_file else None

    # Create headers: timestamp, core_0, core_1, ..., core_N, overall
    headers = ['timestamp_unix'] + [f'core_{i}' for i in range(num_cores)] + ['overall']
    writer.writerow(headers)
    if memory_writer:
        memory_writer.writerow([
            'timestamp_unix',
            'rss_mb',
            'vms_mb',
            'num_threads',
            'num_fds',
            'cpu_percent',
        ])

    # Initial call to prime the CPU percentage calculation
    psutil.cpu_percent(interval=None, percpu=True)
    psutil.cpu_percent(interval=None)
    if memory_process:
        memory_process.cpu_percent(interval=None)

    try:
        while True:
            # 100ms sampling interval
            time.sleep(0.1)

            timestamp = time.time()
            per_cpu = psutil.cpu_percent(interval=None, percpu=True)
            overall = psutil.cpu_percent(interval=None)

            writer.writerow([timestamp] + per_cpu + [overall])
            f.flush() # Ensure data is written to disk immediately

            if memory_writer:
                try:
                    mem = memory_process.memory_info()
                    rss_mb = mem.rss / (1024 * 1024)
                    vms_mb = mem.vms / (1024 * 1024)
                except psutil.NoSuchProcess:
                    memory_writer = None
                    continue
                except psutil.AccessDenied:
                    rss_mb = ''
                    vms_mb = ''

                memory_writer.writerow([
                    timestamp,
                    rss_mb,
                    vms_mb,
                    access_denied_value(memory_process.num_threads),
                    access_denied_value(memory_process.num_fds),
                    access_denied_value(lambda: memory_process.cpu_percent(interval=None)),
                ])
                memory_file.flush()

    except KeyboardInterrupt:
        pass
    finally:
        if memory_file:
            memory_file.close()