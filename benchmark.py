import time
import requests
import psycopg2
import docker
import subprocess
from statistics import mean

# === Configuration Variables ===

# Number of data points to write to each DB
N = 100

# InfluxDB configuration
INFLUX_URL = "http://localhost:8086/api/v2/write?org=myorg&bucket=mybucket&precision=s"
INFLUX_QUERY_URL = "http://localhost:8086/api/v2/query?org=myorg"
INFLUX_TOKEN = "mytoken"
INFLUX_HEADERS = {
    "Authorization": f"Token {INFLUX_TOKEN}",
    "Content-Type": "application/vnd.flux"
}

# TimescaleDB (PostgreSQL) configuration
POSTGRES_CONFIG = {
    "dbname": "timeseries",
    "user": "postgres",
    "password": "postgres123",
    "host": "localhost",
    "port": 5432
}

# QuestDB configuration
QUESTDB_CONFIG = {
    "dbname": "qdb",
    "user": "admin",
    "password": "quest",
    "host": "localhost",
    "port": 8812
}

# Connect to Docker
docker_client = docker.from_env()

# === Helper Functions ===

# Get CPU % and memory usage for a Docker container by sampling over 5 seconds
def get_stats(container_name):
    cpu_percents = []
    mem_usage = 0

    container = docker_client.containers.get(container_name)

    for _ in range(5):
        stats1 = container.stats(stream=False)
        cpu_total_1 = stats1["cpu_stats"]["cpu_usage"]["total_usage"]
        sys_cpu_1 = stats1["cpu_stats"]["system_cpu_usage"]
        num_cpus = stats1["cpu_stats"].get("online_cpus", 1)
        mem_usage = stats1["memory_stats"]["usage"]
        time.sleep(1)
        stats2 = container.stats(stream=False)
        cpu_total_2 = stats2["cpu_stats"]["cpu_usage"]["total_usage"]
        sys_cpu_2 = stats2["cpu_stats"]["system_cpu_usage"]

        cpu_delta = cpu_total_2 - cpu_total_1
        sys_delta = sys_cpu_2 - sys_cpu_1

        if sys_delta > 0.0 and cpu_delta > 0.0:
            cpu_percent = (cpu_delta / sys_delta) * num_cpus * 100.0
            cpu_percents.append(cpu_percent)

    avg_cpu = mean(cpu_percents) if cpu_percents else 0
    return avg_cpu, mem_usage

# Estimate disk usage
def get_volume_size(volume_name):
    try:
        result = subprocess.run(
            ['docker', 'run', '--rm', '-v', f'{volume_name}:/data', 'alpine', 'du', '-s', '/data'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        size_kb = int(result.stdout.split()[0])
        return size_kb * 1024
    except Exception as e:
        print(f"Error checking volume {volume_name}: {e}")
        return None

# === Benchmark Functions ===

def benchmark_influx():
    print("\n--- InfluxDB ---")
    write_latencies = []
    start = time.time()

    for i in range(N):
        point = f"sensor_data,sensor_id=1 value={i} {int(time.time())}"
        t0 = time.time()
        requests.post(INFLUX_URL, data=point, headers={"Authorization": f"Token {INFLUX_TOKEN}"})
        write_latencies.append(time.time() - t0)
    write_time = time.time() - start

    t0 = time.time()
    query = 'from(bucket:"mybucket") |> range(start: -1m)'
    requests.post(INFLUX_QUERY_URL, headers=INFLUX_HEADERS, data=query)
    read_latency = time.time() - t0

    cpu, mem = get_stats("influxdb_dbms")
    disk = get_volume_size("influxdb-data")

    return {
        "write_throughput": N / write_time,
        "avg_write_latency": mean(write_latencies),
        "read_latency": read_latency,
        "disk_mb": disk / 1024 / 1024 if disk else 0,
        "cpu": cpu,
        "mem": mem
    }

def benchmark_timescale():
    print("\n--- TimescaleDB ---")
    conn = psycopg2.connect(**POSTGRES_CONFIG)
    cur = conn.cursor()

    cur.execute("DROP TABLE IF EXISTS sensor_data;")
    cur.execute("CREATE TABLE sensor_data (time TIMESTAMPTZ, value DOUBLE PRECISION);")
    conn.commit()

    write_latencies = []
    start = time.time()
    for i in range(N):
        t0 = time.time()
        cur.execute("INSERT INTO sensor_data (time, value) VALUES (NOW(), %s);", (i,))
        write_latencies.append(time.time() - t0)
    conn.commit()
    write_time = time.time() - start

    t0 = time.time()
    cur.execute("SELECT * FROM sensor_data LIMIT 10;")
    cur.fetchall()
    read_latency = time.time() - t0

    cur.close()
    conn.close()

    cpu, mem = get_stats("timescaledb_dbms")
    disk = get_volume_size("timescaledb-data")

    return {
        "write_throughput": N / write_time,
        "avg_write_latency": mean(write_latencies),
        "read_latency": read_latency,
        "disk_mb": disk / 1024 / 1024 if disk else 0,
        "cpu": cpu,
        "mem": mem
    }

def benchmark_questdb():
    print("\n--- QuestDB ---")
    conn = psycopg2.connect(**QUESTDB_CONFIG)
    cur = conn.cursor()

    cur.execute("DROP TABLE IF EXISTS sensor_data;")
    cur.execute("CREATE TABLE sensor_data (ts TIMESTAMP, value DOUBLE);")
    conn.commit()

    write_latencies = []
    start = time.time()
    for i in range(N):
        t0 = time.time()
        cur.execute("INSERT INTO sensor_data VALUES (NOW(), %s);", (i,))
        write_latencies.append(time.time() - t0)
    conn.commit()
    write_time = time.time() - start

    t0 = time.time()
    cur.execute("SELECT * FROM sensor_data LIMIT 10;")
    cur.fetchall()
    read_latency = time.time() - t0

    cur.close()
    conn.close()

    cpu, mem = get_stats("questdb_dbms")
    disk = get_volume_size("questdb-data")

    return {
        "write_throughput": N / write_time,
        "avg_write_latency": mean(write_latencies),
        "read_latency": read_latency,
        "disk_mb": disk / 1024 / 1024 if disk else 0,
        "cpu": cpu,
        "mem": mem
    }

# === Run All Benchmarks ===

results = {
    "InfluxDB": benchmark_influx(),
    "TimescaleDB": benchmark_timescale(),
    "QuestDB": benchmark_questdb()
}

# === Final Summary ===
print("\n\n=== Final Metrics ===")
for db, metrics in results.items():
    print(f"\n{db}:")
    for k, v in metrics.items():
        unit = "MB" if "disk" in k else "%" if k == "cpu" else "s" if "latency" in k else "records/s" if "throughput" in k else "bytes"
        print(f"  {k}: {v:.4f} {unit}")
