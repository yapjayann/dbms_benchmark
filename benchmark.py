import time
import requests
import psycopg2
import docker
from statistics import mean
import random
from datetime import datetime

# === Configuration ===

N = 10000  # Number of records to insert in each database

# --- InfluxDB HTTP API endpoint and headers ---
INFLUX_URL = "http://localhost:8086/api/v2/write?org=myorg&bucket=mybucket&precision=s"
INFLUX_QUERY_URL = "http://localhost:8086/api/v2/query?org=myorg"
INFLUX_TOKEN = "mytoken"
INFLUX_HEADERS = {
    "Authorization": f"Token {INFLUX_TOKEN}",
    "Content-Type": "application/vnd.flux"  # Required for Flux query language
}

# --- TimescaleDB connection parameters ---
POSTGRES_CONFIG = {
    "dbname": "timeseries",
    "user": "postgres",
    "password": "postgres123",
    "host": "localhost",
    "port": 5432
}

# --- QuestDB connection parameters ---
QUESTDB_CONFIG = {
    "dbname": "qdb",
    "user": "admin",
    "password": "quest",
    "host": "localhost",
    "port": 8812
}

# Create a Docker client to collect container statistics
docker_client = docker.from_env()

# === Get CPU and Memory usage for a Docker container ===
def get_stats(container_name):
    cpu_percents = []
    mem_usage = 0

    # Get container object
    container = docker_client.containers.get(container_name)

    # Sample usage over 5 seconds to get average CPU and memory usage
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

        # Calculate delta to get CPU usage %
        cpu_delta = cpu_total_2 - cpu_total_1
        sys_delta = sys_cpu_2 - sys_cpu_1

        if sys_delta > 0.0 and cpu_delta > 0.0:
            cpu_percent = (cpu_delta / sys_delta) * num_cpus * 100.0
            cpu_percents.append(cpu_percent)

    # Average CPU usage over the 5 samples
    avg_cpu = mean(cpu_percents) if cpu_percents else 0
    return avg_cpu, mem_usage

# === Generate sample data for all databases ===
def generate_data(i):
    return {
        "timestamp": int(time.time()),  # Current UNIX timestamp
        "sensor_id": random.randint(1, 10),
        "location": "KLCC",  # Simulated fixed location
        "co2_level": round(random.uniform(350.0, 500.0), 2),  # Simulated CO2
        "noise_level": round(random.uniform(30.0, 100.0), 2),  # Simulated noise
        "temperature": round(random.uniform(25.0, 40.0), 2)  # Simulated temperature
    }

# === Benchmark for InfluxDB ===
def benchmark_influx():
    print("\n--- InfluxDB ---")
    write_latencies = []
    start = time.time()

    for i in range(N):
        data = generate_data(i)

        # Create line protocol string for InfluxDB
        line = (
            f"sensor_data,sensor_id={data['sensor_id']},location={data['location']} "
            f"co2_level={data['co2_level']},noise_level={data['noise_level']},temperature={data['temperature']} "
            f"{data['timestamp']}"
        )

        # Measure write latency
        t0 = time.time()
        requests.post(INFLUX_URL, data=line, headers={"Authorization": f"Token {INFLUX_TOKEN}"})
        write_latencies.append(time.time() - t0)

    write_time = time.time() - start

    # Run simple query to measure read latency
    t0 = time.time()
    query = 'from(bucket:"mybucket") |> range(start: -1m)'
    requests.post(INFLUX_QUERY_URL, headers=INFLUX_HEADERS, data=query)
    read_latency = time.time() - t0

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

    # Reset table
    cur.execute("DROP TABLE IF EXISTS sensor_data;")
    cur.execute("""
        CREATE TABLE sensor_data (
            timestamp TIMESTAMPTZ,
            sensor_id INT,
            location TEXT,
            co2_level DOUBLE PRECISION,
            noise_level DOUBLE PRECISION,
            temperature DOUBLE PRECISION
        );
    """)
    conn.commit()

    write_latencies = []
    start = time.time()

    for i in range(N):
        data = generate_data(i)
        t0 = time.time()
        cur.execute("""
            INSERT INTO sensor_data (timestamp, sensor_id, location, co2_level, noise_level, temperature)
            VALUES (NOW(), %s, %s, %s, %s, %s);
        """, (data["sensor_id"], data["location"], data["co2_level"], data["noise_level"], data["temperature"]))
        write_latencies.append(time.time() - t0)

    conn.commit()
    write_time = time.time() - start

    # Simple read query
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

    # Reset table and use SYMBOL for "location" for performance
    cur.execute("DROP TABLE IF EXISTS sensor_data;")
    cur.execute("""
        CREATE TABLE sensor_data (
            timestamp TIMESTAMP,
            sensor_id INT,
            location SYMBOL,
            co2_level DOUBLE,
            noise_level DOUBLE,
            temperature DOUBLE
        );
    """)
    conn.commit()

    write_latencies = []
    start = time.time()

    for i in range(N):
        data = generate_data(i)
        t0 = time.time()
        cur.execute("""
            INSERT INTO sensor_data (timestamp, sensor_id, location, co2_level, noise_level, temperature)
            VALUES (NOW(), %s, %s, %s, %s, %s);
        """, (data["sensor_id"], data["location"], data["co2_level"], data["noise_level"], data["temperature"]))
        write_latencies.append(time.time() - t0)

    conn.commit()
    write_time = time.time() - start

    # Read 10 rows to test query performance
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

# === Run All Benchmarks and Display Results ===
results = {
    "InfluxDB": benchmark_influx(),
    "TimescaleDB": benchmark_timescale(),
    "QuestDB": benchmark_questdb()
}

# Nicely formatted printout of all metrics
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

