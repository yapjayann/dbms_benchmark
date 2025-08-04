import time
import requests
import psycopg2
import docker
from statistics import mean

# === Configuration Variables ===

N = 10000  # Number of records to insert for each database benchmark

# --- InfluxDB configuration (via HTTP API) ---
INFLUX_URL = "http://localhost:8086/api/v2/write?org=myorg&bucket=mybucket&precision=s"
INFLUX_QUERY_URL = "http://localhost:8086/api/v2/query?org=myorg"
INFLUX_TOKEN = "mytoken"
INFLUX_HEADERS = {
    "Authorization": f"Token {INFLUX_TOKEN}",
    "Content-Type": "application/vnd.flux"  # Flux is InfluxDB’s query language
}

# --- TimescaleDB configuration (via psycopg2 + PostgreSQL protocol) ---
POSTGRES_CONFIG = {
    "dbname": "timeseries",
    "user": "postgres",
    "password": "postgres123",
    "host": "localhost",
    "port": 5432
}

# --- QuestDB configuration (also uses PostgreSQL wire protocol) ---
QUESTDB_CONFIG = {
    "dbname": "qdb",
    "user": "admin",
    "password": "quest",
    "host": "localhost",
    "port": 8812
}

# Initialize Docker client to collect container resource usage stats
docker_client = docker.from_env()

# === Function to get container CPU and memory usage ===
def get_stats(container_name):
    cpu_percents = []
    mem_usage = 0

    # Get container object by name
    container = docker_client.containers.get(container_name)

    # Sample CPU and memory usage over a few seconds to get a stable reading
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

        # Calculate CPU percentage based on the delta of CPU usage and system usage
        cpu_delta = cpu_total_2 - cpu_total_1
        sys_delta = sys_cpu_2 - sys_cpu_1

        if sys_delta > 0.0 and cpu_delta > 0.0:
            cpu_percent = (cpu_delta / sys_delta) * num_cpus * 100.0
            cpu_percents.append(cpu_percent)

    # Return average CPU usage and latest memory usage
    avg_cpu = mean(cpu_percents) if cpu_percents else 0
    return avg_cpu, mem_usage

# === Benchmark for InfluxDB ===
def benchmark_influx():
    print("\n--- InfluxDB ---")
    write_latencies = []
    start = time.time()

    # Write N data points using HTTP POST
    for i in range(N):
        point = f"sensor_data,sensor_id=1 value={i} {int(time.time())}"
        t0 = time.time()
        requests.post(INFLUX_URL, data=point, headers={"Authorization": f"Token {INFLUX_TOKEN}"})
        write_latencies.append(time.time() - t0)

    write_time = time.time() - start

    # Run a basic query to measure read latency
    t0 = time.time()
    query = 'from(bucket:"mybucket") |> range(start: -1m)'
    requests.post(INFLUX_QUERY_URL, headers=INFLUX_HEADERS, data=query)
    read_latency = time.time() - t0

    # Get Docker stats for resource usage
    cpu, mem = get_stats("influxdb_dbms")

    return {
        "write_throughput": N / write_time,
        "avg_write_latency": mean(write_latencies),
        "total_write_time": write_time,
        "read_latency": read_latency,
        "cpu": cpu,
        "mem": mem
    }

# === Benchmark for TimescaleDB ===
def benchmark_timescale():
    print("\n--- TimescaleDB ---")
    conn = psycopg2.connect(**POSTGRES_CONFIG)
    cur = conn.cursor()

    # Reset table and create a basic time-series table
    cur.execute("DROP TABLE IF EXISTS sensor_data;")
    cur.execute("CREATE TABLE sensor_data (time TIMESTAMPTZ, value DOUBLE PRECISION);")
    conn.commit()

    write_latencies = []
    start = time.time()

    # Insert N rows one by one and measure latency per row
    for i in range(N):
        t0 = time.time()
        cur.execute("INSERT INTO sensor_data (time, value) VALUES (NOW(), %s);", (i,))
        write_latencies.append(time.time() - t0)
    conn.commit()
    write_time = time.time() - start

    # Measure read latency
    t0 = time.time()
    cur.execute("SELECT * FROM sensor_data LIMIT 10;")
    cur.fetchall()
    read_latency = time.time() - t0

    cur.close()
    conn.close()

    cpu, mem = get_stats("timescaledb_dbms")

    return {
        "write_throughput": N / write_time,
        "avg_write_latency": mean(write_latencies),
        "total_write_time": write_time,
        "read_latency": read_latency,
        "cpu": cpu,
        "mem": mem
    }

# === Benchmark for QuestDB ===
def benchmark_questdb():
    print("\n--- QuestDB ---")
    conn = psycopg2.connect(**QUESTDB_CONFIG)
    cur = conn.cursor()

    # Drop and recreate the table (must match QuestDB's schema expectations)
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

    return {
        "write_throughput": N / write_time,
        "avg_write_latency": mean(write_latencies),
        "total_write_time": write_time,
        "read_latency": read_latency,
        "cpu": cpu,
        "mem": mem
    }

# === Run all benchmarks and report ===

# Run benchmarks and collect results
results = {
    "InfluxDB": benchmark_influx(),
    "TimescaleDB": benchmark_timescale(),
    "QuestDB": benchmark_questdb()
}

# Display results in a clear and formatted way
print("\n\n=== Final Metrics ===")
for db, metrics in results.items():
    print(f"\n{db}:")
    for k, v in metrics.items():
        unit = (
            "s" if "latency" in k or "time" in k
            else "%" if k == "cpu"
            else "records/s" if "throughput" in k
            else "bytes"
        )
        print(f"  {k}: {v:.4f} {unit}")

