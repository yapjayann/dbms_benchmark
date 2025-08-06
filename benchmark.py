import time
import requests
import psycopg2
import docker
from statistics import mean
from datetime import datetime
import pandas as pd

# === Configuration ===

N = 1000  # Number of records extracted from dataset to insert in each database

# === Load Cleaned Data ===
csv_data = pd.read_csv("cleaned_power_data.csv")
csv_data = csv_data.sample(n=N, random_state=42).reset_index(drop=True)

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


# === Get average CPU and Memory usage for a Docker container ===
def get_stats(container_name):
    cpu_percents = []
    mem_usages = []

    # Get container object
    container = docker_client.containers.get(container_name)

    # Sample usage over 5 seconds to get average CPU and memory usage
    for _ in range(5):
        stats1 = container.stats(stream=False)
        cpu_total_1 = stats1["cpu_stats"]["cpu_usage"]["total_usage"]
        sys_cpu_1 = stats1["cpu_stats"]["system_cpu_usage"]
        num_cpus = stats1["cpu_stats"].get("online_cpus", 1)
        mem_usages.append(stats1["memory_stats"]["usage"])

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

    # Average CPU and memory usage over the 5 samples
    avg_cpu = mean(cpu_percents) if cpu_percents else 0
    avg_mem = mean(mem_usages) if mem_usages else 0

    return avg_cpu, avg_mem


# === Get data from CSV ===
def get_csv_data(i): 
    row = csv_data.iloc[i]
    return {
        "timestamp": pd.to_datetime(row["timestamp"]),
        "gap": float(row["Global_active_power"]),
        "grp": float(row["Global_reactive_power"]),
        "voltage": float(row["Voltage"]),
        "intensity": float(row["Global_intensity"]),
        "sub_1": float(row["Sub_metering_1"]),
        "sub_2": float(row["Sub_metering_2"]),
        "sub_3": float(row["Sub_metering_3"])
    }


# === Benchmark for InfluxDB ===
def benchmark_influx():
    print("\n--- InfluxDB ---")
    write_latencies = []
    start = time.time()

    for i in range(N):
        data = get_csv_data(i)

        ts = int(data["timestamp"].timestamp())  # Convert to UNIX timestamp
        # Create line protocol string for InfluxDB
        line = (
            f"power_data "
            f"global_active_power={data['gap']},"
            f"global_reactive_power={data['grp']},"
            f"voltage={data['voltage']},"
            f"global_intensity={data['intensity']},"
            f"sub_metering_1={data['sub_1']},"
            f"sub_metering_2={data['sub_2']},"
            f"sub_metering_3={data['sub_3']} "
            f"{ts}"
        )

        # Measure write latency
        t0 = time.time()
        requests.post(INFLUX_URL, data=line, headers=INFLUX_HEADERS)
        write_latencies.append(time.time() - t0)

    write_time = time.time() - start

    # Run full table query to measure read latency
    t0 = time.time()
    query = {
    "query": '''
    from(bucket: "mybucket")
    |> range(start: 0)
    |> filter(fn: (r) => r._measurement == "power_data")
    '''
    }
    requests.post(INFLUX_QUERY_URL, headers=INFLUX_HEADERS, json=query)

    read_latency = time.time() - t0


    # Aggregation query: hourly average of global_active_power
    t0 = time.time()
    agg_query = {
    "query": '''
    from(bucket: "mybucket")
    |> range(start: 0)
    |> filter(fn: (r) => r._measurement == "power_data" and r._field == "global_active_power")
    |> aggregateWindow(every: 1h, fn: mean)
    |> yield(name: "mean")
    '''
    
    }
    requests.post(INFLUX_QUERY_URL, headers=INFLUX_HEADERS, json=agg_query)
    agg_latency = time.time() - t0


    cpu, mem = get_stats("influxdb_dbms")

    return {
        "write_throughput": N / write_time,
        "avg_write_latency": mean(write_latencies),
        "total_write_time": write_time,
        "read_latency": read_latency,
        "agg_query_latency": agg_latency,
        "cpu": cpu,
        "mem": mem
    }

# === Benchmark for TimescaleDB ===
def benchmark_timescale():
    print("\n--- TimescaleDB ---")
    conn = psycopg2.connect(**POSTGRES_CONFIG)
    cur = conn.cursor()

    # Reset table
    cur.execute("DROP TABLE IF EXISTS power_data;")
    cur.execute("""
        CREATE TABLE power_data (
            timestamp TIMESTAMPTZ,
            global_active_power DOUBLE PRECISION,
            global_reactive_power DOUBLE PRECISION,
            voltage DOUBLE PRECISION,
            global_intensity DOUBLE PRECISION,
            sub_metering_1 DOUBLE PRECISION,
            sub_metering_2 DOUBLE PRECISION,
            sub_metering_3 DOUBLE PRECISION
        );
    """)

    conn.commit()

    write_latencies = []
    start = time.time()

    for i in range(N):
        data = get_csv_data(i)
        t0 = time.time()
        cur.execute("""
            INSERT INTO power_data (
                timestamp, global_active_power, global_reactive_power,
                voltage, global_intensity,
                sub_metering_1, sub_metering_2, sub_metering_3
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
        """, (
            data["timestamp"], data["gap"], data["grp"], data["voltage"],
            data["intensity"], data["sub_1"], data["sub_2"], data["sub_3"]
        ))
        write_latencies.append(time.time() - t0)

    conn.commit()
    write_time = time.time() - start

    # Simple read query
    t0 = time.time()
    cur.execute("SELECT * FROM power_data;")
    cur.fetchall()
    read_latency = time.time() - t0

    # Aggregation query: hourly average of global_active_power
    t0 = time.time()
    cur.execute("""
        SELECT date_trunc('hour', timestamp) AS hour,
               AVG(global_active_power)
        FROM power_data
        GROUP BY hour
        ORDER BY hour;
    """)
    cur.fetchall()
    agg_latency = time.time() - t0


    cur.close()
    conn.close()

    cpu, mem = get_stats("timescaledb_dbms")

    return {
        "write_throughput": N / write_time,
        "avg_write_latency": mean(write_latencies),
        "total_write_time": write_time,
        "read_latency": read_latency,
        "agg_query_latency": agg_latency,
        "cpu": cpu,
        "mem": mem
    }

# === Benchmark for QuestDB ===
def benchmark_questdb():
    print("\n--- QuestDB ---")
    conn = psycopg2.connect(**QUESTDB_CONFIG)
    cur = conn.cursor()

    # Reset table
    cur.execute("DROP TABLE IF EXISTS power_data;")
    cur.execute("""
        CREATE TABLE power_data (
            timestamp TIMESTAMP,
            global_active_power DOUBLE PRECISION,
            global_reactive_power DOUBLE PRECISION,
            voltage DOUBLE PRECISION,
            global_intensity DOUBLE PRECISION,
            sub_metering_1 DOUBLE PRECISION,
            sub_metering_2 DOUBLE PRECISION,
            sub_metering_3 DOUBLE PRECISION
        );
    """)
    conn.commit()

    write_latencies = []
    start = time.time()

    for i in range(N):
        data = get_csv_data(i)
        t0 = time.time()
        cur.execute("""
            INSERT INTO power_data (
                timestamp, global_active_power, global_reactive_power,
                voltage, global_intensity,
                sub_metering_1, sub_metering_2, sub_metering_3
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
        """, (
            data["timestamp"], data["gap"], data["grp"], data["voltage"],
            data["intensity"], data["sub_1"], data["sub_2"], data["sub_3"]
        ))
        write_latencies.append(time.time() - t0)

    conn.commit()
    write_time = time.time() - start

    # Read whole table test query performance
    t0 = time.time()
    cur.execute("SELECT * FROM power_data;")
    cur.fetchall()
    read_latency = time.time() - t0

    # Aggregation query: hourly average of global_active_power
    t0 = time.time()
    cur.execute("""
        SELECT date_trunc('hour', timestamp) AS hour,
               AVG(global_active_power)
        FROM power_data
        GROUP BY hour
        ORDER BY hour;
    """)
    cur.fetchall()
    agg_latency = time.time() - t0

    
    cur.close()
    conn.close()

    cpu, mem = get_stats("questdb_dbms")

    return {
        "write_throughput": N / write_time,
        "avg_write_latency": mean(write_latencies),
        "total_write_time": write_time,
        "read_latency": read_latency,
        "agg_query_latency": agg_latency,
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

